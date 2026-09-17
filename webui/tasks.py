"""
YTSage Web UI - task database
=============================
Own store for batch downloads and a unified task index, kept apart from the
other two databases:

  * ``ytsage_history.db``  - shared with the desktop app; its structure is
                             never altered (see history_service)
  * the sync database      - the sync centre's records / profiles / targets

So "normal / batch / sync" downloads are separated two ways:
  * here, by the ``source`` / ``source_id`` columns,
  * inside history ``options`` (JSON) - the only place that can be extended
    without changing the shared table layout.

Kept on SQLite for now; the DDL goes through the sync dialect layer so it can
follow if the task store ever needs another engine.
"""

import json
import logging
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .official_bridge import APP_DATA_DIR
from .sync import db as syncdb

logger = logging.getLogger("ytsage.webui.tasks")

DB_FILE = APP_DATA_DIR / "ytsage_webui.db"

SOURCE_SINGLE = "single"
SOURCE_BATCH = "batch"
SOURCE_SYNC = "sync"

_lock = threading.RLock()
_conn = None


TABLE_DEFS: Dict[str, List[Tuple[str, str, str]]] = {
    "batches": [
        ("id", "PK", ""),
        ("name", "STR", ""),
        ("created_at", "REAL", ""),
        ("finished_at", "REAL", ""),
        ("total", "INT", "DEFAULT 0"),
        ("done", "INT", "DEFAULT 0"),
        ("failed", "INT", "DEFAULT 0"),
        ("download_path", "STR", ""),
        ("options_json", "TEXT", ""),
        ("status", "STR", "DEFAULT 'running'"),  # running | done | cancelled
    ],
    "batch_items": [
        ("id", "PK", ""),
        ("batch_id", "INT", "NOT NULL"),
        ("url", "STR", ""),
        ("title", "STR", ""),
        ("video_id", "STR", ""),
        ("job_id", "STR", ""),
        ("status", "STR", "DEFAULT 'queued'"),
        ("file_path", "STR", ""),
        ("history_id", "STR", ""),
        ("error", "TEXT", ""),
        # Full download payload per row (format / subtitles / ...). Stored when
        # the row is queued so "retry this batch" can replay the exact options.
        ("payload_json", "TEXT", ""),
        ("updated_at", "REAL", ""),
    ],
    "task_index": [
        ("id", "PK", ""),
        ("source", "STR", ""),          # single | batch | sync
        ("source_id", "STR", ""),       # batch_id / profile_id
        ("source_ref", "STR", ""),      # target_id (sync only)
        ("job_id", "STR", ""),
        ("video_id", "STR", ""),
        ("history_id", "STR", ""),
        ("status", "STR", ""),
        ("created_at", "REAL", ""),
    ],
}

# Columns added after the first release - applied on connect so an existing
# database is upgraded in place.
EXTRA_COLUMNS = [
    ("batch_items", "payload_json", "TEXT"),
]

INDEXES = [
    ("idx_batch_items_batch", "batch_items", ("batch_id",)),
    ("idx_batch_items_job", "batch_items", ("job_id",)),
    ("idx_task_index_source", "task_index", ("source",)),
    ("idx_task_index_job", "task_index", ("job_id",)),
]


# ---------------------------------------------------------------------------
# low level
# ---------------------------------------------------------------------------

def _connect() -> sqlite3.Connection:
    global _conn
    with _lock:
        if _conn is None:
            APP_DATA_DIR.mkdir(parents=True, exist_ok=True)
            _conn = sqlite3.connect(str(DB_FILE), check_same_thread=False, timeout=10)
            _conn.row_factory = sqlite3.Row
            _conn.execute("PRAGMA journal_mode=WAL;")
            _conn.execute("PRAGMA busy_timeout=5000;")
            syncdb.create_schema(
                _conn, syncdb.get_dialect("sqlite"), TABLE_DEFS, INDEXES
            )
            _migrate(_conn)
            _conn.commit()
        return _conn


def _migrate(conn: sqlite3.Connection) -> None:
    """Add columns introduced after the database was first created."""
    for table, column, col_type in EXTRA_COLUMNS:
        try:
            cols = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}
        except Exception:  # noqa: BLE001
            continue
        if column not in cols:
            try:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")
            except Exception as e:  # noqa: BLE001
                logger.warning(f"[WebUI] tasks: cannot add {table}.{column}: {e}")


def _rows(sql: str, params: tuple = ()) -> List[Dict[str, Any]]:
    with _lock:
        cur = _connect().execute(sql, tuple(params))
        try:
            return [dict(r) for r in cur.fetchall()]
        finally:
            cur.close()


def _row(sql: str, params: tuple = ()) -> Optional[Dict[str, Any]]:
    rows = _rows(sql, params)
    return rows[0] if rows else None


def _exec(sql: str, params: tuple = ()) -> int:
    with _lock:
        conn = _connect()
        cur = conn.execute(sql, tuple(params))
        conn.commit()
        last = cur.lastrowid or 0
        cur.close()
        return int(last)


def now() -> float:
    return time.time()


# ---------------------------------------------------------------------------
# batches
# ---------------------------------------------------------------------------

def create_batch(
    urls: List[str],
    name: str = "",
    download_path: str = "",
    options: Optional[Dict[str, Any]] = None,
) -> int:
    """Create a batch + one item per URL. Returns the batch id."""
    urls = [u for u in (urls or []) if u]
    bid = _exec(
        "INSERT INTO batches (name,created_at,total,download_path,options_json,status) "
        "VALUES (?,?,?,?,?,'running')",
        (name or "", now(), len(urls), download_path or "",
         json.dumps(options or {}, ensure_ascii=False)),
    )
    for u in urls:
        _exec(
            "INSERT INTO batch_items (batch_id,url,status,updated_at) VALUES (?,?,'queued',?)",
            (bid, u, now()),
        )
    return bid


def list_batches(limit: int = 30, offset: int = 0) -> List[Dict[str, Any]]:
    return _rows(
        "SELECT * FROM batches ORDER BY created_at DESC LIMIT ? OFFSET ?",
        (max(1, int(limit)), max(0, int(offset))),
    )


def get_batch(batch_id: int) -> Optional[Dict[str, Any]]:
    b = _row("SELECT * FROM batches WHERE id=?", (batch_id,))
    if not b:
        return None
    b["items"] = _rows(
        "SELECT * FROM batch_items WHERE batch_id=? ORDER BY id", (batch_id,)
    )
    try:
        b["options"] = json.loads(b.get("options_json") or "{}")
    except Exception:  # noqa: BLE001
        b["options"] = {}
    return b


def set_batch_job(batch_id: int, url: str, job_id: str) -> None:
    _exec(
        "UPDATE batch_items SET job_id=?, status='queued', updated_at=? "
        "WHERE batch_id=? AND url=? AND (job_id IS NULL OR job_id='')",
        (job_id, now(), batch_id, url),
    )


def save_item_payload(batch_id: int, url: str, payload: Dict[str, Any]) -> None:
    """Persist the row's download options so a retry can replay them."""
    try:
        blob = json.dumps(payload or {}, ensure_ascii=False)
    except Exception:  # noqa: BLE001
        blob = "{}"
    row = _row("SELECT id FROM batch_items WHERE batch_id=? AND url=? AND (job_id IS NULL OR job_id='') ORDER BY id LIMIT 1",
               (batch_id, url))
    if row:
        _exec("UPDATE batch_items SET payload_json=?, updated_at=? WHERE id=?",
              (blob, now(), row["id"]))
        return
    _exec("UPDATE batch_items SET payload_json=?, updated_at=? WHERE batch_id=? AND url=?",
          (blob, now(), batch_id, url))


def retryable_items(batch_id: int) -> List[Dict[str, Any]]:
    """Unfinished rows with a stored payload - ready to be re-queued."""
    rows = _rows(
        "SELECT id, url, payload_json FROM batch_items WHERE batch_id=? "
        "AND status<>'completed' AND payload_json IS NOT NULL AND payload_json<>'' "
        "ORDER BY id",
        (batch_id,),
    )
    out = []
    for r in rows:
        try:
            payload = json.loads(r["payload_json"] or "{}")
        except Exception:  # noqa: BLE001
            payload = {}
        if not payload.get("url"):
            payload["url"] = r["url"]
        out.append({"id": r["id"], "url": r["url"], "payload": payload})
    return out


def update_item_by_job(
    job_id: str,
    status: Optional[str] = None,
    title: Optional[str] = None,
    file_path: Optional[str] = None,
    history_id: Optional[str] = None,
    error: Optional[str] = None,
) -> None:
    """Reflect a download job's outcome onto its batch item (if any)."""
    if not job_id:
        return
    sets, params = [], []
    for col, val in (("status", status), ("title", title), ("file_path", file_path),
                     ("history_id", history_id), ("error", error)):
        if val is not None:
            sets.append(f"{col}=?")
            params.append(val)
    if not sets:
        return
    sets.append("updated_at=?")
    params.append(now())
    params.append(job_id)
    _exec(f"UPDATE batch_items SET {', '.join(sets)} WHERE job_id=?", tuple(params))
    _refresh_batch_counts()


def _refresh_batch_counts() -> None:
    for b in _rows("SELECT id FROM batches"):
        bid = b["id"]
        done = _row(
            "SELECT COUNT(*) c FROM batch_items WHERE batch_id=? AND status='completed'",
            (bid,),
        )["c"]
        failed = _row(
            "SELECT COUNT(*) c FROM batch_items WHERE batch_id=? AND status IN ('error','failed','cancelled')",
            (bid,),
        )["c"]
        total = _row("SELECT COUNT(*) c FROM batch_items WHERE batch_id=?", (bid,))["c"]
        status = "running"
        if total and (done + failed) >= total:
            status = "done"
        _exec(
            "UPDATE batches SET done=?, failed=?, total=?, status=?, finished_at=? WHERE id=?",
            (done, failed, total, status,
             now() if status == "done" else None, bid),
        )


def failed_item_urls(batch_id: int) -> List[str]:
    rows = _rows(
        "SELECT url FROM batch_items WHERE batch_id=? AND status IN ('error','failed','cancelled') "
        "ORDER BY id",
        (batch_id,),
    )
    return [r["url"] for r in rows if r.get("url")]


def pending_job_ids(batch_id: int) -> List[str]:
    """Job ids that are still queued/running - used to cancel the remainder."""
    rows = _rows(
        "SELECT job_id FROM batch_items WHERE batch_id=? "
        "AND status IN ('queued','pending','running','paused')",
        (batch_id,),
    )
    return [r["job_id"] for r in rows if r.get("job_id")]


def reset_batch(batch_id: int) -> int:
    """Re-queue every unfinished item before a retry. Returns the count."""
    n = _exec(
        "UPDATE batch_items SET status='queued', error=NULL, job_id=NULL, updated_at=? "
        "WHERE batch_id=? AND status<>'completed'",
        (now(), batch_id),
    )
    _exec("UPDATE batches SET status='running', finished_at=NULL WHERE id=?", (batch_id,))
    return n


def cancel_batch(batch_id: int) -> None:
    _exec(
        "UPDATE batch_items SET status='cancelled', updated_at=? "
        "WHERE batch_id=? AND status IN ('queued','pending','running','paused')",
        (now(), batch_id),
    )
    _exec("UPDATE batches SET status='cancelled', finished_at=? WHERE id=?",
          (now(), batch_id))


def delete_batch(batch_id: int) -> bool:
    _exec("DELETE FROM batch_items WHERE batch_id=?", (batch_id,))
    _exec("DELETE FROM batches WHERE id=?", (batch_id,))
    _exec("DELETE FROM task_index WHERE source=? AND source_id=?",
          (SOURCE_BATCH, str(batch_id)))
    return True


# ---------------------------------------------------------------------------
# unified task index
# ---------------------------------------------------------------------------

def record_task(
    source: str,
    job_id: str,
    video_id: str = "",
    source_id: str = "",
    source_ref: str = "",
) -> None:
    _exec(
        "INSERT INTO task_index (source,source_id,source_ref,job_id,video_id,status,created_at) "
        "VALUES (?,?,?,?,?,'queued',?)",
        (source, str(source_id or ""), str(source_ref or ""), job_id, video_id, now()),
    )


def update_task(
    job_id: str,
    status: Optional[str] = None,
    history_id: Optional[str] = None,
    video_id: Optional[str] = None,
) -> None:
    if not job_id:
        return
    sets, params = [], []
    for col, val in (("status", status), ("history_id", history_id), ("video_id", video_id)):
        if val is not None:
            sets.append(f"{col}=?")
            params.append(val)
    if not sets:
        return
    params.append(job_id)
    _exec(f"UPDATE task_index SET {', '.join(sets)} WHERE job_id=?", tuple(params))


def list_tasks(
    source: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> Dict[str, Any]:
    where, params = [], []
    if source:
        where.append("source=?")
        params.append(source)
    w = ("WHERE " + " AND ".join(where)) if where else ""
    total = _row(f"SELECT COUNT(*) c FROM task_index {w}", tuple(params))["c"]
    params += [max(1, int(limit)), max(0, int(offset))]
    rows = _rows(
        f"SELECT * FROM task_index {w} ORDER BY created_at DESC LIMIT ? OFFSET ?",
        tuple(params),
    )
    return {"entries": rows, "total": total, "limit": limit, "offset": offset}


def task_sources() -> Dict[str, int]:
    """Counts per source - powers the "where did this come from" filter."""
    out = {SOURCE_SINGLE: 0, SOURCE_BATCH: 0, SOURCE_SYNC: 0}
    for r in _rows("SELECT source, COUNT(*) c FROM task_index GROUP BY source"):
        out[r["source"] or SOURCE_SINGLE] = r["c"]
    return out
