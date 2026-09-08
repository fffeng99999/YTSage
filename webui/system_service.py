"""
System status & OS integration for YTSage Web UI.

- /api/system/status: yt-dlp / ffmpeg / deno versions + Deno integration
  (mirrors AboutDialog SystemInfoThread and official version helpers,
  ytsage_utils.py L244-300, ytsage_yt_dlp.py L717-754)
- reveal/open-folder: mirrors open_download_folder (ytsage_gui_main.py L1050-1096)
  with a path whitelist (download_path + APP dirs) to prevent arbitrary
  filesystem probing from the browser.
"""

import logging
import subprocess
import sys
from pathlib import Path
from typing import Optional

import requests

from .official_bridge import (
    APP_LOG_DIR,
    DENO_APP_BIN_PATH,
    SUBPROCESS_CREATIONFLAGS,
    USER_HOME_DIR,
    cfg_get,
)
from .yt_dlp_finder import get_ffmpeg_path, get_yt_dlp_path

logger = logging.getLogger("ytsage.webui")


def _run(cmd, timeout=10):
    kwargs = {"capture_output": True, "text": True, "timeout": timeout}
    if sys.platform == "win32":
        kwargs["creationflags"] = SUBPROCESS_CREATIONFLAGS
    return subprocess.run(cmd, **kwargs)


def get_ytdlp_version() -> str:
    """Official: ytsage_utils.get_ytdlp_version_direct (L244)."""
    path = get_yt_dlp_path()
    if not path or path == "yt-dlp":
        return "Not found"
    try:
        result = _run([path, "--version"])
        return result.stdout.strip() if result.returncode == 0 else "Error getting version"
    except Exception as e:
        return f"Error: {e}"


def get_ffmpeg_version() -> str:
    """Official: ytsage_utils.get_ffmpeg_version_direct (L267)."""
    try:
        result = _run(["ffmpeg", "-version"])
        if result.returncode == 0:
            first = result.stdout.split("\n")[0]
            parts = first.split()
            for i, part in enumerate(parts):
                if part == "version" and i + 1 < len(parts):
                    return parts[i + 1]
            return first
        return "Not found"
    except Exception:
        return "Not found"


def get_deno_version() -> str:
    """Official: ytsage_deno.get_deno_version_direct (L479) - app bin only."""
    if not DENO_APP_BIN_PATH.exists():
        return "Not found"
    try:
        result = _run([str(DENO_APP_BIN_PATH), "--version"])
        if result.returncode == 0:
            first = result.stdout.strip().split("\n")[0]
            return first.replace("deno ", "").strip()
    except Exception:
        pass
    return "Error getting version"


def check_deno_integration() -> bool:
    """Official: ytsage_yt_dlp.check_ytdlp_deno_integration (L717)."""
    path = get_yt_dlp_path()
    if not path or path == "yt-dlp":
        return False
    try:
        result = _run([path, "--verbose"], timeout=15)
        output = result.stderr or ""
        return "[debug] JS runtimes:" in output and "deno" in output
    except Exception:
        return False


def system_status() -> dict:
    ytdlp_path = get_yt_dlp_path()
    return {
        "ytdlp": {
            "installed": ytdlp_path != "yt-dlp" or _which_ok("yt-dlp"),
            "version": get_ytdlp_version(),
            "path": str(ytdlp_path),
        },
        "ffmpeg": {
            "installed": get_ffmpeg_version() not in ("Not found",),
            "version": get_ffmpeg_version(),
        },
        "deno": {
            "installed": DENO_APP_BIN_PATH.exists(),
            "version": get_deno_version(),
            "path": str(DENO_APP_BIN_PATH),
            "integrated_with_ytdlp": check_deno_integration(),
        },
        "log_dir": str(APP_LOG_DIR),
    }


def _which_ok(name: str) -> bool:
    import shutil
    return bool(shutil.which(name))


# ---------------------------------------------------------------------------
# Path whitelist + reveal
# ---------------------------------------------------------------------------

def _allowed_roots() -> list:
    roots = [USER_HOME_DIR, APP_LOG_DIR, Path(get_download_path())]
    try:
        from .official_bridge import APP_DIR
        roots.append(APP_DIR)
    except Exception:
        pass
    return [r.resolve() for r in roots if r]


def get_download_path() -> str:
    return cfg_get("download_path") or str(USER_HOME_DIR / "Downloads")


def is_path_allowed(target: Path) -> bool:
    try:
        resolved = target.resolve()
    except Exception:
        return False
    for root in _allowed_roots():
        try:
            resolved.relative_to(root)
            return True
        except ValueError:
            continue
    return False


def reveal_in_folder(file_path: str) -> bool:
    """Open file location. Official: ytsage_gui_main.py L1050-1096."""
    p = Path(file_path)
    if not p.exists() or not is_path_allowed(p):
        return False
    if sys.platform == "win32":
        subprocess.run(["explorer", "/select,", str(p)], creationflags=SUBPROCESS_CREATIONFLAGS)
    elif sys.platform == "darwin":
        subprocess.run(["open", "-R", str(p)])
    else:
        subprocess.run(["xdg-open", str(p.parent)])
    return True


def open_folder(dir_path: str) -> bool:
    p = Path(dir_path)
    if not p.is_dir() or not is_path_allowed(p):
        return False
    if sys.platform == "win32":
        subprocess.run(["explorer", str(p)], creationflags=SUBPROCESS_CREATIONFLAGS)
    elif sys.platform == "darwin":
        subprocess.run(["open", str(p)])
    else:
        subprocess.run(["xdg-open", str(p)])
    return True


def open_logs() -> bool:
    APP_LOG_DIR.mkdir(parents=True, exist_ok=True)
    return open_folder(str(APP_LOG_DIR))
