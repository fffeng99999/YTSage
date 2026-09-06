"""
Async facade over the official HistoryManager (SQLite, shared with desktop).

All calls run in worker threads (official manager uses a persistent sqlite3
connection + RLock). Includes retry for cross-process "database is locked"
(when the desktop app writes concurrently).
"""

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional

from .official_bridge import HAS_HISTORY, _OfficialHistoryManager

logger = logging.getLogger("ytsage.webui")

_MAX_RETRIES = 3


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
