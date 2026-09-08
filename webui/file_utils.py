"""
Atomic JSON writes + cross-process file locking for WebUI config files.

Prevents two failure modes:
  - Torn writes: a crash mid-write used to leave an empty/partial JSON file.
    We now write to a temp file in the same directory, fsync, validate the
    JSON round-trips, then os.replace() (atomic on both NTFS and POSIX).
  - Cross-process races: the desktop app and the WebUI (or two WebUI
    instances) can write the same file concurrently. An exclusive advisory
    lock (msvcrt on Windows, fcntl elsewhere) serialises writers.
"""

import json
import os
import sys
import tempfile
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Iterator, Optional

# In-process mutex: the lock files below are per-path OS locks, but threads
# in this process must not interleave read-modify-write either.
_thread_lock = threading.RLock()


@contextmanager
def _file_lock(path: Path) -> Iterator[None]:
    """Best-effort exclusive advisory lock on <path>.lock.

    If locking is impossible (read-only dir, unsupported FS) we proceed
    without the lock rather than breaking startup.
    """
    lock_path = path.with_suffix(path.suffix + ".lock")
    fd: Optional[int] = None
    try:
        fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR, 0o600)
    except OSError:
        yield
        return
    try:
        if sys.platform == "win32":
            import msvcrt

            # Blocking byte-range lock on the first byte (0-0 read as 1 byte).
            try:
                msvcrt.locking(fd, msvcrt.LK_LOCK, 1)
            except OSError:
                # LK_LOCK retries ~10x then raises; fall through unlocked.
                pass
        else:
            import fcntl

            try:
                fcntl.flock(fd, fcntl.LOCK_EX)
            except OSError:
                pass
    except Exception:
        pass
    try:
        yield
    finally:
        try:
            if sys.platform == "win32":
                import msvcrt

                try:
                    os.lseek(fd, 0, os.SEEK_SET)
                    msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
                except OSError:
                    pass
            else:
                import fcntl

                fcntl.flock(fd, fcntl.LOCK_UN)
        except Exception:
            pass
        try:
            os.close(fd)
        except OSError:
            pass


def read_json_locked(path: Path, default: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Read a JSON file; return `default` (fresh dict) on any problem."""
    with _thread_lock:
        if not path.exists():
            return dict(default or {})
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return dict(default or {})


def write_json_atomic(path: Path, data: Dict[str, Any]) -> None:
    """Serialize `data` and replace `path` atomically under a file lock.

    Raises on failure so callers can log; the existing file is left intact
    if anything goes wrong before os.replace().
    """
    payload = json.dumps(data, indent=2, ensure_ascii=False)
    # Validate before touching the real file - a non-serializable structure
    # must never blank an existing config.
    json.loads(payload)
    with _thread_lock:
        path.parent.mkdir(parents=True, exist_ok=True)
        with _file_lock(path):
            fd, tmp_name = tempfile.mkstemp(
                dir=str(path.parent), prefix=path.name + ".", suffix=".tmp"
            )
            try:
                with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
                    f.write(payload)
                    f.flush()
                    os.fsync(f.fileno())
                os.replace(tmp_name, path)
            except Exception:
                try:
                    os.unlink(tmp_name)
                except OSError:
                    pass
                raise
