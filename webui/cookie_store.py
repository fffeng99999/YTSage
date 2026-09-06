"""
Cookie storage for YTSage Web UI.

The user pastes Netscape-format cookie text in the browser; we save it to a
server-side file and register that path in the official ConfigManager
(`cookie_file_path`), so both the Web UI and the desktop app can use it.

Location: %APPDATA%/YTSage/cookies.txt (same dir as webui_config.json).
"""

from pathlib import Path

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


def delete_cookie_file() -> None:
    try:
        COOKIE_FILE.unlink(missing_ok=True)
    except Exception:
        pass
