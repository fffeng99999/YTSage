"""
Async facade over the official HistoryManager (SQLite, shared with desktop).

All calls run in worker threads (official manager uses a persistent sqlite3
connection + RLock). Includes retry for cross-process "database is locked"
(when the desktop app writes concurrently).
"""

import asyncio
import logging
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from .official_bridge import APP_DATA_DIR, HAS_HISTORY, _OfficialHistoryManager

logger = logging.getLogger("ytsage.webui")

_MAX_RETRIES = 3

# The official HistoryManager owns the schema and shares ytsage_history.db
# with the desktop app. We never alter its structure; for paged reads we open
# our own short-lived connection to the SAME file with WAL + busy_timeout so
# large lists stream via LIMIT/OFFSET instead of loading the whole table.
_DB_FILE = APP_DATA_DIR / "ytsage_history.db"


def _row_to_entry(row: sqlite3.Row) -> Dict[str, Any]:
    entry = dict(row)
    entry["is_audio_only"] = bool(entry.get("is_audio_only"))
    try:
        import json as _json
        entry["download_options"] = _json.loads(entry["options"]) if entry.get("options") else {}
    except Exception:
        entry["download_options"] = {}
    entry.pop("options", None)
    return entry


def _connect_readonly() -> Optional[sqlite3.Connection]:
    if not _DB_FILE.exists():
        return None
    try:
        conn = sqlite3.connect(f"file:{_DB_FILE.as_posix()}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA journal_mode=WAL;")
        except sqlite3.Error:
            pass
        conn.execute("PRAGMA busy_timeout=5000;")
        return conn
    except sqlite3.Error as e:
        logger.warning(f"[WebUI] history readonly connect failed: {e}")
        return None


def ensure_wal_mode() -> bool:
    """Enable WAL + busy_timeout on the shared history DB once at startup.

    journal_mode is stored in the DB header, so this also benefits the
    desktop app's connection. Returns True when WAL is active.
    """
    if not _DB_FILE.exists():
        return False
    try:
        conn = sqlite3.connect(str(_DB_FILE), timeout=5)
        try:
            conn.execute("PRAGMA busy_timeout=5000;")
            mode = conn.execute("PRAGMA journal_mode=WAL;").fetchone()[0]
            return str(mode).lower() == "wal"
        finally:
            conn.close()
    except sqlite3.Error as e:
        logger.warning(f"[WebUI] could not enable WAL on history db: {e}")
        return False


def _list_paged_sync(page: int, limit: int, keyword: Optional[str]) -> Dict[str, Any]:
    conn = _connect_readonly()
    if conn is None:
        return {"entries": [], "total": 0, "page": page, "limit": limit, "available": False}
    try:
        cur = conn.cursor()
        where = ""
        params: List[Any] = []
        if keyword:
            where = "WHERE (title LIKE ? OR channel LIKE ? OR url LIKE ?)"
            like = f"%{keyword}%"
            params = [like, like, like]
        cur.execute(f"SELECT COUNT(*) AS c FROM history {where}", params)
        total = cur.fetchone()["c"]
        offset = max(0, (page - 1) * limit)
        cur.execute(
            f"SELECT * FROM history {where} ORDER BY timestamp DESC LIMIT ? OFFSET ?",
            params + [limit, offset],
        )
        entries = [_row_to_entry(r) for r in cur.fetchall()]
        return {"entries": entries, "total": total, "page": page, "limit": limit, "available": True}
    except sqlite3.Error as e:
        logger.warning(f"[WebUI] paged history query failed: {e}")
        return {"entries": [], "total": 0, "page": page, "limit": limit, "available": False}
    finally:
        try:
            conn.close()
        except Exception:
            pass


async def list_paged(page: int = 1, limit: int = 20, keyword: Optional[str] = None) -> Dict[str, Any]:
    """Paged history query (module 2.1). Falls back to the official manager
    when our own read-only connection cannot open the shared DB."""
    page = max(1, int(page))
    limit = max(1, min(200, int(limit)))
    if not _available():
        return {"entries": [], "total": 0, "page": page, "limit": limit, "available": False}
    result = await asyncio.to_thread(_list_paged_sync, page, limit, keyword)
    if not result["available"] and result["total"] == 0:
        # DB not yet created or unreadable via ro URI: use the manager once.
        entries = await list_entries(keyword)
        start = (page - 1) * limit
        result = {
            "entries": entries[start:start + limit],
            "total": len(entries),
            "page": page,
            "limit": limit,
            "available": True,
        }
    return result


def _is_locked_error(e: Exception) -> bool:
    return "locked" in str(e).lower()


def _with_retry(fn, *args):
    last: Optional[Exception] = None
    for attempt in range(_MAX_RETRIES):
        try:
            return fn(*args)
        except Exception as e:
            last = e
            if not _is_locked_error(e):
                raise
            delay = 0.2 * (2**attempt)
            logger.warning(f"[WebUI] history db locked, retry in {delay}s ({e})")
            time.sleep(delay)
    raise last or RuntimeError("history operation failed")


def _available() -> bool:
    return HAS_HISTORY and _OfficialHistoryManager is not None


async def list_entries(query: Optional[str] = None) -> List[Dict[str, Any]]:
    if not _available():
        return []
    if query:
        return await asyncio.to_thread(_with_retry, _OfficialHistoryManager.search_entries, query)
    return await asyncio.to_thread(_with_retry, _OfficialHistoryManager.get_all_entries)


async def get_entry(entry_id: str) -> Optional[Dict[str, Any]]:
    if not _available():
        return None
    return await asyncio.to_thread(_with_retry, _OfficialHistoryManager.get_entry, entry_id)


async def remove_entry(entry_id: str) -> bool:
    if not _available():
        return False
    return await asyncio.to_thread(_with_retry, _OfficialHistoryManager.remove_entry, entry_id)


async def clear_history() -> int:
    if not _available():
        return 0
    return await asyncio.to_thread(_with_retry, _OfficialHistoryManager.clear_history)


async def add_entry(
    title: str,
    url: str,
    thumbnail_url: Optional[str],
    file_path: str,
    format_id: Optional[str],
    is_audio_only: bool,
    resolution: str,
    channel: Optional[str] = None,
    duration: Optional[str] = None,
    download_options: Optional[Dict[str, Any]] = None,
) -> str:
    """Add a history entry. download_options keys must match official
    ytsage_gui_main.py L1013-1025 so the desktop app can read them."""
    if not _available():
        return ""
    return await asyncio.to_thread(
        _with_retry,
        _OfficialHistoryManager.add_entry,
        title,
        url,
        thumbnail_url,
        file_path,
        format_id or "",
        is_audio_only,
        resolution or "",
        None,
        channel,
        duration,
        download_options,
    )
