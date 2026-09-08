"""
Cookie storage for YTSage Web UI.

The user pastes Netscape-format cookie text in the browser; we save it to a
server-side file and register that path in the official ConfigManager
(`cookie_file_path`), so both the Web UI and the desktop app can use it.

Location: %APPDATA%/YTSage/cookies.txt (same dir as webui_config.json).

Security (module 4.3): cookie contents are credentials. The API layer must
NEVER echo them back; use cookie_status() for a metadata-only view.
"""

import time
from pathlib import Path
from typing import Any, Dict

from .auth import WEBUI_CONFIG_DIR

COOKIE_FILE = WEBUI_CONFIG_DIR / "cookies.txt"

# Minimal sanity check for Netscape cookie format:
# tab-separated lines, 7 fields, first field domain (or "#HttpOnly_" prefixed).
def validate_netscape(content: str) -> bool:
    seen_data_line = False
    for raw in content.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) < 7:
            return False
        # fields: domain, flag, path, secure, expiry, name, value
        if not parts[0] or not parts[5]:
            return False
        try:
            int(parts[4])
        except ValueError:
            if parts[4].lower() != "true":
                return False
        seen_data_line = True
    return seen_data_line


def save_cookie_content(content: str) -> Path:
    """Write cookie text to disk with private permissions. Returns the path."""
    content = content.strip() + "\n"
    WEBUI_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    COOKIE_FILE.write_text(content, encoding="utf-8")
    try:
        COOKIE_FILE.chmod(0o600)
    except Exception:
        pass
    return COOKIE_FILE


def load_cookie_content() -> str:
    if COOKIE_FILE.exists():
        try:
            return COOKIE_FILE.read_text(encoding="utf-8")
        except Exception:
            return ""
    return ""


def cookie_status() -> Dict[str, Any]:
    """Metadata-only view of the stored cookie file (module 4.3).

    Never returns cookie contents - only existence, size, import time,
    and a domain-count summary so the UI can show what is loaded.
    """
    if not COOKIE_FILE.exists():
        return {"exists": False, "imported_at": None, "size": 0, "entries": 0}
    try:
        stat = COOKIE_FILE.stat()
        content = COOKIE_FILE.read_text(encoding="utf-8")
        entries = sum(
            1 for line in content.splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        )
        return {
            "exists": True,
            "imported_at": stat.st_mtime,
            "imported_at_iso": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(stat.st_mtime)),
            "size": stat.st_size,
            "entries": entries,
        }
    except Exception:
        return {"exists": True, "imported_at": None, "size": 0, "entries": 0}


def delete_cookie_file() -> None:
    try:
        COOKIE_FILE.unlink(missing_ok=True)
    except Exception:
        pass
