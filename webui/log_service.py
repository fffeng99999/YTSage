"""
Log viewer service for YTSage Web UI.

Reads the official loguru files (APP_LOG_DIR/ytsage.log + ytsage_error.log)
with incremental byte offsets, so the frontend can poll for new lines and
render a dynamic ("live tail") log view. Rotated archives (.zip, loguru
compresses rotated files) are listed but not readable.

Path safety: names are resolved inside APP_LOG_DIR only (no traversal).
"""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from .official_bridge import APP_LOG_DIR

logger = logging.getLogger("ytsage.webui")

# Upper bound for a single read call (bytes). Frontend polls every ~2s.
READ_CHUNK = 64 * 1024


def _safe_path(name: str) -> Optional[Path]:
    """Resolve a log file name inside APP_LOG_DIR; None if unsafe/blank."""
    if not name:
        return None
    try:
        target = (APP_LOG_DIR / name).resolve()
        target.relative_to(APP_LOG_DIR.resolve())
    except (ValueError, OSError):
        return None
    return target


def ensure_log_dir() -> None:
    """Make sure the log directory exists (must already, but be safe)."""
    try:
        APP_LOG_DIR.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass


def list_log_files() -> List[Dict[str, Any]]:
    """Enumerate log files: current .log plus rotated archives (.zip)."""
    ensure_log_dir()
    files: List[Dict[str, Any]] = []
    for p in sorted(APP_LOG_DIR.glob("*"), key=lambda x: x.name.lower()):
        if not p.is_file():
            continue
        try:
            stat = p.stat()
            size, mtime = stat.st_size, stat.st_mtime
        except OSError:
            size, mtime = 0, 0
        pickable = p.suffix.lower() == ".log"
        files.append({
            "name": p.name,
            "size": size,
            "mtime": mtime,
            "compressed": not pickable,
            "pickable": pickable,
        })
    return files


def read_log(name: str, offset: int = 0, max_bytes: int = READ_CHUNK) -> Dict[str, Any]:
    """Read a log file incrementally from a byte offset.

    Returns the raw chunk (utf-8, errors replaced) plus the next offset.
    When the caller's offset is beyond the current file size the file has
    been rotated - the response marks it with `rotated: True` so the
    frontend can reset its offset and clear the buffer.
    """
    p = _safe_path(name)
    if p is None or not p.is_file() or not p.name.lower().endswith(".log"):
        raise FileNotFoundError(f"Log file '{name}' not found")

    size = p.stat().st_size
    offset = max(0, int(offset))
    if offset > size:
        return {
            "name": name, "content": "", "offset": 0, "size": size,
            "eof": True, "rotated": True,
        }

    start = offset
    want = max(8, min(int(max_bytes), READ_CHUNK))
    with open(p, "rb") as f:
        f.seek(start)
        chunk = f.read(want)

    text = chunk.decode("utf-8", errors="replace")
    new_offset = start + len(chunk)
    return {
        "name": name,
        "content": text,
        "offset": new_offset,
        "size": size,
        "eof": new_offset >= size,
        "rotated": False,
    }