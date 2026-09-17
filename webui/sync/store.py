"""
YTSage Sync - Store
===================
SQLite persistence for the YT sync center (dysync.net-inspired, but targeted
at YouTube). DB lives at APP_DATA_DIR/ytsage_sync.db, separate from the
official history db. Single writer connection guarded by an RLock.

Tables:
  profiles     - sync sources (an "account": cookie + root path + options)
  targets      - per-profile items to sync (playlist / liked / channel / subs)
  records      - sync records (dedup + per-video status)
  excludes     - permanently ignored video ids
  schedules    - cron-like periodic sync jobs
  sync_settings- key/value for the sync center itself
"""

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..official_bridge import APP_DATA_DIR

DB_FILE = APP_DATA_DIR / "ytsage_sync.db"

_lock = threading.RLock()
_conn: Optional[sqlite3.Connection] = None

_SCHEMA = """
CREATE TABLE IF NOT EXISTS profiles (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  cookie_source TEXT DEFAULT 'browser',
  cookie_browser TEXT DEFAULT 'chrome',
  cookie_browser_profile TEXT DEFAULT '',
  cookie_file_path TEXT,
  root_path TEXT NOT NULL,
  only_recent INTEGER DEFAULT 0,
  recent_limit INTEGER DEFAULT 20,
  folder_by_title INTEGER DEFAULT 1,
  enabled INTEGER DEFAULT 1,
  dedup_priority TEXT DEFAULT '["liked","favorites","playlist","channel","subscriptions"]',
  created_at REAL,
  updated_at REAL
);
CREATE TABLE IF NOT EXISTS targets (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  profile_id INTEGER NOT NULL,
  kind TEXT NOT NULL,          -- playlist | liked | channel | subscriptions
  url TEXT NOT NULL,
  title TEXT,
  folder TEXT,
  enabled INTEGER DEFAULT 1,
  sort_index INTEGER DEFAULT 0,
  created_at REAL,
  sync_mode TEXT DEFAULT 'sync',
  save_path TEXT,
  channel_id TEXT,
  avatar_url TEXT,
  last_sync_at REAL
);
CREATE TABLE IF NOT EXISTS records (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  video_id TEXT NOT NULL UNIQUE,
  video_title TEXT,
  channel TEXT,
  url TEXT,
  kind TEXT,
  profile_id INTEGER,
  target_id INTEGER,
  file_path TEXT,
  size INTEGER DEFAULT 0,
  duration REAL,
  status TEXT DEFAULT 'downloaded', -- downloaded | excluded | failed | missing
  last_sync REAL, first_sync REAL,
  download_job_id TEXT,
  thumbnail_url TEXT,
  deleted_at REAL,
  nfo_generated INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS excludes (
  video_id TEXT PRIMARY KEY,
  reason TEXT,
  created_at REAL
);
CREATE TABLE IF NOT EXISTS schedules (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  profile_id INTEGER NOT NULL,
  mode TEXT DEFAULT 'interval',  -- interval | daily | weekly
  interval_min INTEGER DEFAULT 60,
  hour INTEGER DEFAULT 0,
  minute INTEGER DEFAULT 0,
  weekday INTEGER DEFAULT 1,
  enabled INTEGER DEFAULT 1,
  last_run REAL, next_run REAL,
  created_at REAL
);
CREATE TABLE IF NOT EXISTS sync_runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_at REAL, finished_at REAL,
  profile_id INTEGER, kind TEXT,
  total INTEGER DEFAULT 0, new_count INTEGER DEFAULT 0,
  skipped INTEGER DEFAULT 0, failed INTEGER DEFAULT 0,
  summary TEXT
);
CREATE TABLE IF NOT EXISTS sync_settings (
  key TEXT PRIMARY KEY,
  value TEXT
);
CREATE TABLE IF NOT EXISTS sync_daily_stats (
  date TEXT PRIMARY KEY,
  total_videos INTEGER DEFAULT 0,
  total_size INTEGER DEFAULT 0,
  liked_count INTEGER DEFAULT 0,
  playlist_count INTEGER DEFAULT 0,
  channel_count INTEGER DEFAULT 0,
  subs_count INTEGER DEFAULT 0,
  new_synced INTEGER DEFAULT 0
);
"""


def _connect() -> sqlite3.Connection:
    global _conn
    with _lock:
        if _conn is None:
            APP_DATA_DIR.mkdir(parents=True, exist_ok=True)
            _conn = sqlite3.connect(str(DB_FILE), check_same_thread=False, timeout=10)
            _conn.row_factory = sqlite3.Row
            _conn.execute("PRAGMA journal_mode=WAL;")
            _conn.execute("PRAGMA busy_timeout=5000;")
            _conn.executescript(_SCHEMA)
            _migrate(_conn)
            _conn.commit()
        return _conn


def _migrate(conn: sqlite3.Connection) -> None:
    """Add new columns to existing tables (for database upgrades)."""
    migrations = [
        ("targets", "sync_mode", "TEXT DEFAULT 'sync'"),
        ("targets", "save_path", "TEXT"),
        ("targets", "channel_id", "TEXT"),
        ("targets", "avatar_url", "TEXT"),
        ("targets", "last_sync_at", "REAL"),
        ("records", "thumbnail_url", "TEXT"),
        ("records", "deleted_at", "REAL"),
        ("records", "nfo_generated", "INTEGER DEFAULT 0"),
        # dysync parity: cookie expiry is watched automatically, not only when
        # the user opens the cookie page.
        ("profiles", "cookie_invalid", "INTEGER DEFAULT 0"),
        ("profiles", "cookie_checked_at", "REAL"),
        ("profiles", "cookie_check_error", "TEXT"),
    ]
    for table, column, col_type in migrations:
        try:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")
        except sqlite3.OperationalError:
            pass  # Column already exists


def _empty_row():
    return {}


def now() -> float:
    return time.time()


def _rows(sql: str, params: tuple = ()) -> List[Dict[str, Any]]:
    with _lock:
        cur = _connect().execute(sql, params)
        return [dict(r) for r in cur.fetchall()]


def _row(sql: str, params: tuple = ()) -> Optional[Dict[str, Any]]:
    with _lock:
        cur = _connect().execute(sql, params)
        r = cur.fetchone()
        return dict(r) if r else None


def _exec(sql: str, params: tuple = ()) -> int:
    with _lock:
        cur = _connect().execute(sql, params)
        _connect().commit()
        return cur.lastrowid


def _execmany(sql: str, seq) -> None:
    with _lock:
        _connect().executemany(sql, seq)
        _connect().commit()


def _table_columns(table: str) -> set:
    """Real column names of ``table`` (read fresh so migrations are picked up)."""
    return {r["name"] for r in _rows(f"PRAGMA table_info({table})")}


def _assignments(table: str, data: Dict[str, Any]):
    """Build a whitelisted "col=?, col=?" SET clause.

    Several update helpers are fed caller-supplied dicts (import_data accepts
    arbitrary JSON), so column names must never reach the SQL string before
    being checked against the live table schema.
    """
    cols = _table_columns(table)
    items = [(k, v) for k, v in data.items() if k in cols]
    if not items:
        return "", ()
    return ", ".join(f"{k}=?" for k, _ in items), tuple(v for _, v in items)


# ---------------------------------------------------------------------------
# Profiles
# ---------------------------------------------------------------------------

DEFAULT_DEDUP_PRIORITY = ["liked", "favorites", "playlist", "channel", "subscriptions"]


def _normalize_dedup_priority(value: Any) -> str:
    """Serialize dedup_priority to JSON text, accepting list OR str.

    Import/export round-trips pass an already-encoded string. The old code
    ran json.dumps on it unconditionally, producing a JSON string inside a
    JSON string - after importing, json.loads returned a str and the engine's
    list() split it into single characters, silently breaking dedup priority.
    """
    if value is None:
        items = DEFAULT_DEDUP_PRIORITY
    elif isinstance(value, str):
        s = value.strip()
        if not s:
            items = DEFAULT_DEDUP_PRIORITY
        else:
            try:
                parsed = json.loads(s)
                items = parsed if isinstance(parsed, list) else DEFAULT_DEDUP_PRIORITY
            except (json.JSONDecodeError, ValueError):
                items = [p.strip() for p in s.split(",") if p.strip()] or DEFAULT_DEDUP_PRIORITY
    elif isinstance(value, (list, tuple)):
        items = list(value)
    else:
        items = DEFAULT_DEDUP_PRIORITY
    return json.dumps(items, ensure_ascii=False)


def list_profiles() -> List[Dict[str, Any]]:
    return _rows("SELECT * FROM profiles ORDER BY id")


def get_profile(pid: int) -> Optional[Dict[str, Any]]:
    return _row("SELECT * FROM profiles WHERE id=?", (pid,))


def create_profile(data: Dict[str, Any]) -> int:
    return _exec(
        """INSERT INTO profiles
           (name,cookie_source,cookie_browser,cookie_browser_profile,cookie_file_path,
            root_path,only_recent,recent_limit,folder_by_title,enabled,dedup_priority,created_at,updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            data.get("name") or "未命名源",
            data.get("cookie_source") or "browser",
            data.get("cookie_browser") or "chrome",
            data.get("cookie_browser_profile") or "",
            data.get("cookie_file_path"),
            data.get("root_path") or "",
            int(bool(data.get("only_recent"))),
            int(data.get("recent_limit") or 20),
            int(data.get("folder_by_title", 1)),
            int(data.get("enabled", 1)),
            _normalize_dedup_priority(data.get("dedup_priority")),
            now(), now(),
        ),
    )


def update_profile(pid: int, data: Dict[str, Any]) -> None:
    allowed = dict(data)
    allowed.pop("id", None)
    if "dedup_priority" in allowed:
        allowed["dedup_priority"] = _normalize_dedup_priority(allowed["dedup_priority"])
    for b in ("only_recent", "folder_by_title", "enabled"):
        if b in allowed:
            allowed[b] = int(bool(allowed[b]))
    sets, values = _assignments("profiles", allowed)
    if sets:
        _exec(f"UPDATE profiles SET {sets}, updated_at=? WHERE id=?", (*values, now(), pid))


def delete_profile(pid: int) -> None:
    _exec("DELETE FROM targets WHERE profile_id=?", (pid,))
    _exec("DELETE FROM schedules WHERE profile_id=?", (pid,))
    _exec("DELETE FROM records WHERE profile_id=?", (pid,))
    _exec("DELETE FROM profiles WHERE id=?", (pid,))


# ---------------------------------------------------------------------------
# Targets
# ---------------------------------------------------------------------------

def list_targets(profile_id: Optional[int] = None) -> List[Dict[str, Any]]:
    if profile_id is None:
        return _rows("SELECT * FROM targets ORDER BY profile_id, sort_index")
    return _rows("SELECT * FROM targets WHERE profile_id=? ORDER BY sort_index", (profile_id,))


def get_target(tid: int) -> Optional[Dict[str, Any]]:
    return _row("SELECT * FROM targets WHERE id=?", (tid,))


def create_target(profile_id: int, data: Dict[str, Any]) -> int:
    # Persist every column (incl. sync_mode / save_path / channel_id / avatar_url)
    # so imported and subscription-added targets keep their configuration.
    return _exec(
        """INSERT INTO targets (profile_id,kind,url,title,folder,enabled,sort_index,created_at,
                                sync_mode,save_path,channel_id,avatar_url)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (profile_id, data.get("kind") or "playlist", data.get("url") or "", data.get("title"),
         data.get("folder"), int(data.get("enabled", 1)), int(data.get("sort_index", 0)), now(),
         data.get("sync_mode") or "sync", data.get("save_path"),
         data.get("channel_id"), data.get("avatar_url")),
    )


def update_target(tid: int, data: Dict[str, Any]) -> None:
    allowed = dict(data)
    allowed.pop("id", None)
    if "enabled" in allowed:
        allowed["enabled"] = int(bool(allowed["enabled"]))
    sets, values = _assignments("targets", allowed)
    if sets:
        _exec(f"UPDATE targets SET {sets} WHERE id=?", (*values, tid))


def delete_target(tid: int) -> None:
    _exec("DELETE FROM targets WHERE id=?", (tid,))


# ---------------------------------------------------------------------------
# Records
# ---------------------------------------------------------------------------

def list_records(
    page: int = 1, limit: int = 20, keyword: Optional[str] = None,
    status: Optional[str] = None, profile_id: Optional[int] = None,
    kind: Optional[str] = None, channel: Optional[str] = None,
    date_from: Optional[float] = None, date_to: Optional[float] = None,
    include_deleted: bool = False,
) -> Dict[str, Any]:
    where, params = [], []
    if not include_deleted:
        where.append("deleted_at IS NULL")
    if keyword:
        like = f"%{keyword}%"
        where.append("(video_title LIKE ? OR channel LIKE ? OR video_id LIKE ?)")
        params += [like, like, like]
    if status:
        where.append("status=?")
        params.append(status)
    if profile_id:
        where.append("profile_id=?")
        params.append(profile_id)
    if kind:
        where.append("kind=?")
        params.append(kind)
    if channel:
        where.append("channel LIKE ?")
        params.append(f"%{channel}%")
    if date_from:
        where.append("last_sync >= ?")
        params.append(date_from)
    if date_to:
        where.append("last_sync <= ?")
        params.append(date_to)
    w = ("WHERE " + " AND ".join(where)) if where else ""
    params.append(limit)
    params.append((page - 1) * limit)
    total = _row(f"SELECT COUNT(*) c FROM records {w}", params[:-2])["c"]
    rows = _rows(
        f"SELECT * FROM records {w} ORDER BY last_sync DESC LIMIT ? OFFSET ?", tuple(params)
    )
    return {"entries": rows, "total": total, "page": page, "limit": limit}


def get_record(video_id: str, profile_id: Optional[int] = None) -> Optional[Dict[str, Any]]:
    """Look up a record by video id, optionally scoped to one profile.

    records.video_id is UNIQUE, so a video synced by two accounts is stored
    once. Passing profile_id lets callers detect that the existing row belongs
    to another account instead of silently re-owning it (dysync keeps each
    account's library separate).
    """
    if profile_id is None:
        return _row("SELECT * FROM records WHERE video_id=?", (video_id,))
    return _row("SELECT * FROM records WHERE video_id=? AND profile_id=?", (video_id, profile_id))


def set_cookie_status(pid: int, invalid: bool, error: str = "") -> None:
    """Persist the outcome of a cookie probe (dysync: Cookie 过期提醒)."""
    _exec(
        "UPDATE profiles SET cookie_invalid=?, cookie_checked_at=?, cookie_check_error=?, updated_at=? WHERE id=?",
        (int(bool(invalid)), now(), (error or "")[:500], now(), pid),
    )


def list_cookie_watch_profiles() -> List[Dict[str, Any]]:
    """Profiles whose cookie is configured and worth auto-checking."""
    return _rows(
        "SELECT * FROM profiles WHERE enabled=1 AND cookie_source IN ('file','browser','global')"
    )


def list_failed_records(profile_id: Optional[int] = None, limit: int = 20) -> List[Dict[str, Any]]:
    """Records whose download failed - dysync 批量重下 re-queues these."""
    sql = "SELECT * FROM records WHERE status='failed' AND deleted_at IS NULL"
    params: List[Any] = []
    if profile_id is not None:
        sql += " AND profile_id=?"
        params.append(profile_id)
    sql += " ORDER BY id LIMIT ?"
    params.append(max(1, int(limit)))
    return _rows(sql, tuple(params))


def count_target_records(target_id: int, include_deleted: bool = False) -> int:
    """Records already filed under a target - used for S01E01 episode numbers."""
    where = "WHERE target_id=?" if include_deleted else "WHERE target_id=? AND deleted_at IS NULL"
    row = _row(f"SELECT COUNT(*) c FROM records {where}", (target_id,))
    return int(row["c"]) if row else 0


def get_record_by_db_id(rid: int) -> Optional[Dict[str, Any]]:
    return _row("SELECT * FROM records WHERE id=?", (rid,))


def upsert_record(rec: Dict[str, Any]) -> None:
    row = _row("SELECT id FROM records WHERE video_id=?", (rec["video_id"],))
    if row:
        _exec(
            """UPDATE records SET video_title=?, channel=?, url=?, kind=?, profile_id=?,
               target_id=?, status=?, last_sync=?, thumbnail_url=? WHERE video_id=?""",
            (rec.get("video_title"), rec.get("channel"), rec.get("url"), rec.get("kind"),
             rec.get("profile_id"), rec.get("target_id"), rec.get("status", "downloaded"),
             now(), rec.get("thumbnail_url"), rec["video_id"]),
        )
    else:
        _exec(
            """INSERT INTO records (video_id,video_title,channel,url,kind,profile_id,target_id,
               file_path,size,duration,status,last_sync,first_sync,download_job_id,thumbnail_url)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (rec["video_id"], rec.get("video_title"), rec.get("channel"), rec.get("url"),
             rec.get("kind"), rec.get("profile_id"), rec.get("target_id"), rec.get("file_path"),
             int(rec.get("size") or 0), rec.get("duration"), rec.get("status", "downloaded"),
             now(), now(), rec.get("download_job_id"), rec.get("thumbnail_url")),
        )


def update_record_file(video_id: str, file_path: str, size: int) -> None:
    _exec("UPDATE records SET file_path=?, size=?, status='downloaded', last_sync=? WHERE video_id=?",
          (file_path, size, now(), video_id))


def delete_record(rid: int) -> None:
    _exec("DELETE FROM records WHERE id=?", (rid,))


def delete_records(ids: List[int]) -> int:
    if not ids:
        return 0
    q = ",".join("?" * len(ids))
    _exec(f"DELETE FROM records WHERE id IN ({q})", tuple(ids))
    return len(ids)


def delete_records_by_author(channel: str) -> int:
    """Delete all records of one author/channel (dysync: DeleteByAuthor)."""
    # Goes through _exec: the previous version used the raw connection and
    # therefore ran outside _lock, racing with every other writer.
    cur = None
    with _lock:
        conn = _connect()
        cur = conn.execute("DELETE FROM records WHERE channel=?", (channel,))
        conn.commit()
    return cur.rowcount or 0


def count_records() -> int:
    return _row("SELECT COUNT(*) c FROM records")["c"]


def list_channels() -> List[str]:
    """Distinct channel names (for the records filter dropdown)."""
    rows = _rows(
        "SELECT DISTINCT channel FROM records "
        "WHERE deleted_at IS NULL AND channel IS NOT NULL AND channel != '' ORDER BY channel"
    )
    return [r["channel"] for r in rows]


def real_delete_records(ids: List[int], also_exclude: bool = True) -> int:
    """Permanent delete (dysync 永久删除): hard-delete records and, when
    also_exclude, add their video ids to the excludes blacklist so future
    sync runs never download them again."""
    if not ids:
        return 0
    q = ",".join("?" * len(ids))
    rows = _rows(f"SELECT video_id FROM records WHERE id IN ({q})", tuple(ids))
    if also_exclude:
        for r in rows:
            exclude_video(r["video_id"], "permanent_delete")
    _exec(f"DELETE FROM records WHERE id IN ({q})", tuple(ids))
    return len(ids)


def scan_missing_records() -> int:
    """Mark downloaded records whose file no longer exists as 'missing'
    (dysync removeInvalid). Returns how many rows were flipped."""
    rows = _rows("SELECT id, file_path FROM records WHERE status='downloaded' AND file_path IS NOT NULL")
    missing = [r["id"] for r in rows if not r["file_path"] or not Path(r["file_path"]).exists()]
    if missing:
        q = ",".join("?" * len(missing))
        _exec(f"UPDATE records SET status='missing' WHERE id IN ({q})", tuple(missing))
    return len(missing)


def remove_missing_records(delete_files: bool = False) -> int:
    """Delete records currently flagged 'missing' (dysync removeInvalid cleanup)."""
    rows = _rows("SELECT id, file_path FROM records WHERE status='missing'")
    if not rows:
        return 0
    ids = [r["id"] for r in rows]
    if delete_files:
        for r in rows:
            if r["file_path"]:
                try:
                    Path(r["file_path"]).unlink(missing_ok=True)
                except Exception:
                    pass
    q = ",".join("?" * len(ids))
    _exec(f"DELETE FROM records WHERE id IN ({q})", tuple(ids))
    return len(ids)


# ---------------------------------------------------------------------------
# Excludes (permanent skip)
# ---------------------------------------------------------------------------

def list_excludes() -> List[Dict[str, Any]]:
    return _rows("SELECT * FROM excludes ORDER BY created_at DESC")


def is_excluded(video_id: str) -> bool:
    return _row("SELECT 1 FROM excludes WHERE video_id=?", (video_id,)) is not None


def exclude_video(video_id: str, reason: str = "manual") -> None:
    _exec("INSERT OR IGNORE INTO excludes (video_id,reason,created_at) VALUES (?,?,?)",
          (video_id, reason, now()))
    _exec("UPDATE records SET status='excluded' WHERE video_id=?", (video_id,))


def remove_exclude(video_id: str) -> None:
    _exec("DELETE FROM excludes WHERE video_id=?", (video_id,))


# ---------------------------------------------------------------------------
# Schedules
# ---------------------------------------------------------------------------

def list_schedules() -> List[Dict[str, Any]]:
    return _rows("SELECT * FROM schedules ORDER BY id")


def get_schedule(sid: int) -> Optional[Dict[str, Any]]:
    return _row("SELECT * FROM schedules WHERE id=?", (sid,))


def create_schedule(data: Dict[str, Any]) -> int:
    nowt = now()
    return _exec(
        """INSERT INTO schedules (profile_id,mode,interval_min,hour,minute,weekday,enabled,last_run,next_run,created_at)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (data.get("profile_id"), data.get("mode") or "interval", int(data.get("interval_min") or 60),
         int(data.get("hour") or 0), int(data.get("minute") or 0), int(data.get("weekday") or 1),
         int(data.get("enabled", 1)), None, None, nowt),
    )


def update_schedule(sid: int, data: Dict[str, Any]) -> None:
    allowed = dict(data)
    allowed.pop("id", None)
    if "enabled" in allowed:
        allowed["enabled"] = int(bool(allowed["enabled"]))
    sets, values = _assignments("schedules", allowed)
    if sets:
        _exec(f"UPDATE schedules SET {sets} WHERE id=?", (*values, sid))


def delete_schedule(sid: int) -> None:
    _exec("DELETE FROM schedules WHERE id=?", (sid,))


def set_schedule_next_run(sid: int, ts: Optional[float]) -> None:
    _exec("UPDATE schedules SET next_run=?, last_run=? WHERE id=?",
          (ts, now(), sid))


# ---------------------------------------------------------------------------
# Sync runs (operation log)
# ---------------------------------------------------------------------------

def add_sync_run(profile_id: Optional[int], kind: str) -> int:
    return _exec("INSERT INTO sync_runs (run_at, profile_id, kind) VALUES (?,?,?)",
                 (now(), profile_id, kind))


def finish_sync_run(run_id: int, total: int, new_count: int, skipped: int, failed: int, summary: str) -> None:
    _exec("UPDATE sync_runs SET finished_at=?, total=?, new_count=?, skipped=?, failed=?, summary=? WHERE id=?",
          (now(), total, new_count, skipped, failed, summary[:2000], run_id))


def list_sync_runs(limit: int = 50) -> List[Dict[str, Any]]:
    return _rows("SELECT * FROM sync_runs ORDER BY run_at DESC LIMIT ?", (limit,))


def clear_sync_runs(before_ts: Optional[float] = None) -> int:
    if before_ts:
        _exec("DELETE FROM sync_runs WHERE run_at < ?", (before_ts,))
    else:
        _exec("DELETE FROM sync_runs")
    return 0


# ---------------------------------------------------------------------------
# Settings (sync center key/value)
# ---------------------------------------------------------------------------

DEFAULT_SETTINGS = {
    "log_retention_days": 30,     # keep sync_runs / app logs for N days
    "only_recent_default": 0,
    "recent_limit_default": 20,
    "max_sync_per_run": 50,       # cap new downloads per manual/scheduled run
    "nfo_enabled": False,         # generate NFO files after download
    "video_naming_template": "%(title)s_[%(id)s].%(ext)s",
    "share_link_enabled": False,  # enable share link generation
    "auto_distinct": True,        # dedup across kinds by priority (dysync AutoDistinct)
    "auto_clean_logs": False,     # scheduler prunes old logs daily
    "resolution": "1080",         # sync download quality cap (px)
    "save_thumbnail": True,       # keep per-video thumbnail next to the file
    "save_description": False,    # write a .description sidecar
    # --- dysync parity: anti-bot / rate control -------------------------
    "anti_bot_enabled": True,     # spread requests + sleep like dysync does
    "sleep_min": 2,               # seconds (dysync uses random 2-9s)
    "sleep_max": 9,
    "ua_disguise": True,          # send a browser User-Agent (dysync UA 伪装)
    "user_agent": "",             # empty -> built-in default UA
    # --- dysync parity: episode / series handling -----------------------
    "episode_naming": True,       # S01E01 prefix for series/mix targets
    "retry_failed": True,         # re-queue failed records on the next run
}


def get_all_settings() -> Dict[str, Any]:
    out = dict(DEFAULT_SETTINGS)
    for row in _rows("SELECT key, value FROM sync_settings"):
        v = row["value"]
        try:
            out[row["key"]] = json.loads(v)
        except Exception:
            out[row["key"]] = v
    return out


def set_settings(data: Dict[str, Any]) -> None:
    for k, v in data.items():
        if k not in DEFAULT_SETTINGS:
            continue
        _exec("INSERT OR REPLACE INTO sync_settings (key,value) VALUES (?,?)",
              (k, json.dumps(v)))


# ---------------------------------------------------------------------------
# Export / import (config + profiles + targets + excludes, no records)
# ---------------------------------------------------------------------------

def export_all() -> Dict[str, Any]:
    return {
        "version": 2,
        "exported_at": now(),
        "settings": get_all_settings(),
        "profiles": [
            {**p, "targets": [t for t in list_targets(p["id"])]}
            for p in list_profiles()
        ],
        "schedules": list_schedules(),
        "excludes": list_excludes(),
    }


def import_all(data: Dict[str, Any]) -> Dict[str, Any]:
    imported = {"profiles": 0, "targets": 0, "schedules": 0, "excludes": 0}
    if data.get("settings"):
        set_settings(data["settings"])
    for p in data.get("profiles") or []:
        targets = p.pop("targets", [])
        p.pop("id", None)
        pid = create_profile(p)
        for t in targets:
            t.pop("id", None)
            t.pop("profile_id", None)
            create_target(pid, t)
        imported["profiles"] += 1
        imported["targets"] += len(targets)
    for s in data.get("schedules") or []:
        s = {k: v for k, v in s.items() if k != "id"}
        if s.get("profile_id"):
            create_schedule(s)
            imported["schedules"] += 1
    for e in data.get("excludes") or []:
        if e.get("video_id"):
            exclude_video(e["video_id"], e.get("reason") or "imported")
            imported["excludes"] += 1
    return imported


# ---------------------------------------------------------------------------
# Soft delete / restore
# ---------------------------------------------------------------------------

def soft_delete_record(video_id: str) -> None:
    _exec("UPDATE records SET deleted_at=? WHERE video_id=?", (now(), video_id))


def soft_delete_records(ids: List[int]) -> int:
    if not ids:
        return 0
    q = ",".join("?" * len(ids))
    _exec(f"UPDATE records SET deleted_at=? WHERE id IN ({q})", (now(), *ids))
    return len(ids)


def restore_record(video_id: str) -> None:
    _exec("UPDATE records SET deleted_at=NULL WHERE video_id=?", (video_id,))


def list_deleted_records(page: int = 1, limit: int = 20) -> Dict[str, Any]:
    where = "WHERE deleted_at IS NOT NULL"
    total = _row(f"SELECT COUNT(*) c FROM records {where}")["c"]
    offset = (page - 1) * limit
    rows = _rows(
        f"SELECT * FROM records {where} ORDER BY deleted_at DESC LIMIT ? OFFSET ?",
        (limit, offset),
    )
    return {"entries": rows, "total": total, "page": page, "limit": limit}


# ---------------------------------------------------------------------------
# Daily statistics
# ---------------------------------------------------------------------------

def upsert_daily_stats(date_str: str, data: Dict[str, Any]) -> None:
    cols_known = _table_columns("sync_daily_stats")
    safe = {k: v for k, v in data.items() if k in cols_known}
    if not safe:
        return
    existing = _row("SELECT date FROM sync_daily_stats WHERE date=?", (date_str,))
    if existing:
        sets = ", ".join(f"{k}=?" for k in safe)
        _exec(f"UPDATE sync_daily_stats SET {sets} WHERE date=?", (*safe.values(), date_str))
    else:
        cols = ", ".join(safe.keys())
        placeholders = ", ".join("?" * len(safe))
        _exec(f"INSERT INTO sync_daily_stats (date, {cols}) VALUES (?, {placeholders})",
              (date_str, *safe.values()))


def get_daily_stats(days: int = 7) -> List[Dict[str, Any]]:
    from datetime import datetime, timedelta
    start = (datetime.now() - timedelta(days=days - 1)).strftime("%Y-%m-%d")
    return _rows("SELECT * FROM sync_daily_stats WHERE date >= ? ORDER BY date", (start,))


def get_trend_stats(days: int = 7) -> List[Dict[str, Any]]:
    """Per-day newly synced counts by kind, derived from records.first_sync.

    Returns one row per day (gaps filled with zeros) so the frontend chart
    always has a continuous x-axis:
      {date, liked, playlist, channel, subscriptions, total}
    """
    from datetime import datetime, timedelta

    kinds_of = ("liked", "favorites", "playlist", "channel", "subscriptions")
    cutoff = time.time() - (days - 1) * 86400
    rows = _rows(
        "SELECT first_sync, kind FROM records "
        "WHERE deleted_at IS NULL AND first_sync IS NOT NULL AND first_sync >= ?",
        (cutoff,),
    )
    buckets: Dict[str, Dict[str, int]] = {}
    today = datetime.now()
    for i in range(days):
        d = (today - timedelta(days=days - 1 - i)).strftime("%Y-%m-%d")
        buckets[d] = {k: 0 for k in kinds_of}
    for r in rows:
        d = datetime.fromtimestamp(r["first_sync"]).strftime("%Y-%m-%d")
        k = r["kind"] if r["kind"] in buckets.get(d, {}) else None
        if k:
            buckets[d][k] += 1
    out = []
    for d, kinds in buckets.items():
        out.append({"date": d, **kinds, "total": sum(kinds.values())})
    return out


# ---------------------------------------------------------------------------
# Statistics queries
# ---------------------------------------------------------------------------

def get_statistics() -> Dict[str, Any]:
    total = _row("SELECT COUNT(*) c, COALESCE(SUM(size),0) s FROM records WHERE deleted_at IS NULL")
    by_kind = _rows(
        "SELECT kind, COUNT(*) c, COALESCE(SUM(size),0) s FROM records "
        "WHERE deleted_at IS NULL GROUP BY kind"
    )
    kind_count = {r["kind"]: r["c"] for r in by_kind if r["kind"]}
    kind_size = {r["kind"]: r["s"] for r in by_kind if r["kind"]}
    authors = _row(
        "SELECT COUNT(DISTINCT channel) c FROM records "
        "WHERE deleted_at IS NULL AND channel IS NOT NULL AND channel != ''"
    )
    return {
        "total_videos": total["c"],
        "total_size": total["s"],
        "author_count": authors["c"] if authors else 0,
        "liked_count": kind_count.get("liked", 0),
        "favorites_count": kind_count.get("favorites", 0),
        "playlist_count": kind_count.get("playlist", 0),
        "channel_count": kind_count.get("channel", 0),
        "subs_count": kind_count.get("subscriptions", 0),
        "liked_size": kind_size.get("liked", 0),
        "favorites_size": kind_size.get("favorites", 0),
        "playlist_size": kind_size.get("playlist", 0),
        "channel_size": kind_size.get("channel", 0),
        "subs_size": kind_size.get("subscriptions", 0),
    }


def get_author_statistics(limit: int = 10, offset: int = 0) -> Dict[str, Any]:
    total = _row(
        "SELECT COUNT(DISTINCT channel) c FROM records "
        "WHERE deleted_at IS NULL AND channel IS NOT NULL AND channel != ''"
    )
    rows = _rows(
        "SELECT channel, COUNT(*) as video_count, COALESCE(SUM(size),0) as total_size "
        "FROM records WHERE deleted_at IS NULL AND channel IS NOT NULL AND channel != '' "
        "GROUP BY channel ORDER BY video_count DESC LIMIT ? OFFSET ?",
        (limit, offset),
    )
    return {"authors": rows, "total": (total["c"] if total else 0)}


# ---------------------------------------------------------------------------
# Target enhancements
# ---------------------------------------------------------------------------

def update_target_sync_mode(tid: int, sync_mode: str) -> None:
    _exec("UPDATE targets SET sync_mode=? WHERE id=?", (sync_mode, tid))


def update_target_save_path(tid: int, save_path: str) -> None:
    _exec("UPDATE targets SET save_path=? WHERE id=?", (save_path, tid))


def update_target_last_sync(tid: int) -> None:
    _exec("UPDATE targets SET last_sync_at=? WHERE id=?", (now(), tid))


def list_targets_by_sync_mode(profile_id: int, sync_mode: str) -> List[Dict[str, Any]]:
    return _rows("SELECT * FROM targets WHERE profile_id=? AND sync_mode=?", (profile_id, sync_mode))