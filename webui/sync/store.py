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
from . import db

# Kept for backwards compatibility (default SQLite location).
DB_FILE = APP_DATA_DIR / "ytsage_sync.db"

_lock = threading.RLock()
_conn = None
_dialect = None


def dialect():
    """Active SQL dialect (sqlite / mysql / postgresql)."""
    global _dialect
    if _dialect is None:
        _dialect = db.get_dialect(db.load_config().get("type"))
    return _dialect


def _adapt(sql: str) -> str:
    """Rewrite `?` placeholders for drivers that want `%s`.

    Every statement in this module is written with `?`; no string literal in
    them contains a question mark, so a plain replace is safe.
    """
    d = dialect()
    return sql if d.placeholder == "?" else sql.replace("?", d.placeholder)


def _connect():
    """Open (once) the connection described by the database configuration."""
    global _conn, _dialect
    with _lock:
        if _conn is None:
            cfg = db.load_config()
            _dialect = db.get_dialect(cfg.get("type"))
            APP_DATA_DIR.mkdir(parents=True, exist_ok=True)
            _conn = db.connect(cfg)
            db.create_schema(_conn, _dialect)
            _migrate(_conn)
            _conn.commit()
        return _conn


def reset_connection() -> None:
    """Drop the cached connection (used after switching database engine)."""
    global _conn, _dialect
    with _lock:
        if _conn is not None:
            try:
                _conn.close()
            except Exception:  # noqa: BLE001
                pass
        _conn = None
        _dialect = None


def _migrate(conn) -> None:
    """Add new columns to existing tables (works on all three engines).

    Types are generic so the dialect can emit something valid - MySQL rejects a
    DEFAULT on a TEXT column, hence VARCHAR for the short string columns.
    """
    d = dialect()
    migrations = [
        ("targets", "sync_mode", "STR", "DEFAULT 'sync'"),
        ("targets", "save_path", "STR", ""),
        ("targets", "channel_id", "STR", ""),
        ("targets", "avatar_url", "STR", ""),
        ("targets", "last_sync_at", "REAL", ""),
        ("records", "thumbnail_url", "STR", ""),
        ("records", "deleted_at", "REAL", ""),
        ("records", "nfo_generated", "INT", "DEFAULT 0"),
        # dysync parity: cookie expiry is watched automatically, not only when
        # the user opens the cookie page.
        ("profiles", "cookie_invalid", "INT", "DEFAULT 0"),
        ("profiles", "cookie_checked_at", "REAL", ""),
        ("profiles", "cookie_check_error", "TEXT", ""),
        # dysync parity: 会员内容 (members-only) needs a logged-in cookie.
        ("records", "is_members", "INT", "DEFAULT 0"),
    ]
    for table, column, kind, extra in migrations:
        if not d.supports_default_on_text and kind == "TEXT" and "DEFAULT" in extra.upper():
            extra = ""
        col_type = d.column_type(kind)
        try:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type} {extra}".strip())
            conn.commit()
        except Exception:  # noqa: BLE001 - column already exists on all engines
            try:
                conn.rollback()
            except Exception:  # noqa: BLE001
                pass


def _empty_row():
    return {}


def now() -> float:
    return time.time()


def _rows(sql: str, params: tuple = ()) -> List[Dict[str, Any]]:
    with _lock:
        cur = _connect().execute(_adapt(sql), tuple(params))
        try:
            return db.dict_rows(cur)
        finally:
            try:
                cur.close()
            except Exception:  # noqa: BLE001
                pass


def _row(sql: str, params: tuple = ()) -> Optional[Dict[str, Any]]:
    rows = _rows(sql, params)
    return rows[0] if rows else None


def _exec(sql: str, params: tuple = ()) -> int:
    with _lock:
        conn = _connect()
        cur = conn.execute(_adapt(sql), tuple(params))
        conn.commit()
        # Only INSERTs can produce a meaningful id, and psycopg2 has no
        # lastrowid at all - the dialect knows how to ask.
        last = dialect().last_insert_id(cur) if sql.lstrip().upper().startswith("INSERT") else 0
        try:
            cur.close()
        except Exception:  # noqa: BLE001
            pass
        return last


def _execmany(sql: str, seq) -> None:
    with _lock:
        conn = _connect()
        cur = conn.executemany(_adapt(sql), list(seq))
        conn.commit()
        try:
            cur.close()
        except Exception:  # noqa: BLE001
            pass


def _table_columns(table: str) -> set:
    """Real column names of ``table`` (read fresh so migrations are picked up).

    PRAGMA table_info is SQLite-only, so the dialect supplies the equivalent
    information_schema query for MySQL / PostgreSQL.
    """
    d = dialect()
    sql, params = d.table_columns_sql(table)
    return d.table_columns_from_rows(_rows(sql, tuple(params)))


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


def mark_members_only(video_id: str) -> None:
    """Flag a record as members-only (needs a logged-in cookie to download)."""
    _exec("UPDATE records SET is_members=1 WHERE video_id=?", (video_id,))


def list_members_videos(channel: str, limit: int = 100) -> List[Dict[str, Any]]:
    """All records of one channel/author, across every sync source."""
    return _rows(
        "SELECT * FROM records WHERE channel=? AND deleted_at IS NULL "
        "ORDER BY last_sync DESC LIMIT ?",
        (channel, max(1, int(limit))),
    )


def _merge_sync_mode(modes: List[str]) -> str:
    """Collapse a member's per-target modes into one summary value."""
    modes = [m or "sync" for m in modes]
    if not modes:
        return "none"
    if all(m == "off" for m in modes):
        return "off"
    if all(m == "full_sync" for m in modes):
        return "full_sync"
    if all(m == "sync" for m in modes):
        return "sync"
    return "mixed"


def list_members() -> List[Dict[str, Any]]:
    """dysync parity: 关注列表 aggregated across every sync source.

    Channels live in `targets` per profile, so the same author in two accounts
    is two unrelated rows. This folds them into one "member" entry that keeps
    the underlying target ids, so bulk actions can still be applied.
    """
    members: Dict[str, Dict[str, Any]] = {}

    def _blank(key: str, name: str) -> Dict[str, Any]:
        return {
            "key": key, "channel_id": "", "name": name, "avatar_url": "",
            "profile_ids": [], "target_ids": [], "sync_modes": [],
            "save_paths": [], "enabled": False,
            "video_count": 0, "total_size": 0, "is_members": 0,
        }

    for t in _rows("SELECT * FROM targets WHERE kind='channel'"):
        key = "id:" + str(t.get("channel_id") or t.get("title") or t.get("url") or t["id"])
        m = members.setdefault(key, _blank(key, t.get("title") or t.get("channel_id") or key))
        m["channel_id"] = t.get("channel_id") or ""
        m["name"] = t.get("title") or m["name"]
        m["avatar_url"] = t.get("avatar_url") or ""
        m["profile_ids"].append(t.get("profile_id"))
        m["target_ids"].append(t.get("id"))
        m["sync_modes"].append(t.get("sync_mode") or "sync")
        if t.get("save_path"):
            m["save_paths"].append(t.get("save_path"))
        if t.get("enabled"):
            m["enabled"] = True

    # Fold in authors known only from records (e.g. synced via a playlist).
    for r in _rows(
        "SELECT channel, COUNT(*) c, SUM(size) s, MAX(is_members) mm "
        "FROM records WHERE deleted_at IS NULL GROUP BY channel"
    ):
        name = (r.get("channel") or "").strip()
        if not name:
            continue
        hit = next((m for m in members.values() if m["name"] == name), None)
        if hit is None:
            key = "name:" + name
            hit = members.setdefault(key, _blank(key, name))
        hit["video_count"] = int(r["c"] or 0)
        hit["total_size"] = int(r["s"] or 0)
        hit["is_members"] = int(r["mm"] or 0)

    for m in members.values():
        m["sync_mode"] = _merge_sync_mode(m["sync_modes"])
        m["profile_count"] = len({p for p in m["profile_ids"] if p})
        m["save_path"] = m["save_paths"][0] if m["save_paths"] else ""
        m["target_count"] = len(m["target_ids"])
    return sorted(members.values(),
                  key=lambda x: (-(x.get("video_count") or 0), x["name"]))


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
    _exec(dialect().insert_or_ignore("excludes", ("video_id", "reason", "created_at")),
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
    # Mirror sync downloads into the shared history db. Off by default: a large
    # archive would flood the desktop app's history (it loads every entry with
    # a thumbnail). Synced items live in `records` regardless.
    "write_history": False,
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


def set_setting(key: str, value: Any) -> None:
    """Insert-or-update one sync setting, dialect aware.

    Callers used to hard-code "INSERT OR REPLACE", which PostgreSQL rejects.
    """
    _exec(dialect().insert_or_replace("sync_settings", ("key", "value")),
          (key, json.dumps(value)))


def set_settings(data: Dict[str, Any]) -> None:
    for k, v in data.items():
        if k not in DEFAULT_SETTINGS:
            continue
        set_setting(k, v)


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