"""
Lightweight yt-dlp path finder for YTSage Web UI.
Does NOT import from ytsage.core (which requires PySide6).
Follows the same search logic as official get_yt_dlp_path().
"""

import shutil
import sys
from pathlib import Path

# Safe import: ytsage_constants has NO PySide6 dependency
try:
    from ytsage.utils.ytsage_constants import YTDLP_APP_BIN_PATH, OS_NAME
except ImportError:
    # Fallbacks if ytsage package not importable
    OS_NAME = sys.platform
    if sys.platform == "win32":
        YTDLP_APP_BIN_PATH = Path.home() / "AppData" / "Local" / "YTSage" / "bin" / "yt-dlp.exe"
    elif sys.platform == "darwin":
        YTDLP_APP_BIN_PATH = Path.home() / "Library" / "Application Support" / "YTSage" / "bin" / "yt-dlp"
    else:
        YTDLP_APP_BIN_PATH = Path.home() / ".local" / "share" / "ytsage" / "bin" / "yt-dlp"


def get_yt_dlp_path() -> str:
    """
    Find yt-dlp executable. Search order:
    1. App-managed bin directory (where official GUI downloads it)
    2. System PATH (yt-dlp installed via pip or package manager)
    """
    # 1. Check app bin directory
    if YTDLP_APP_BIN_PATH.exists():
        return str(YTDLP_APP_BIN_PATH)

    # 2. Check system PATH
    system_path = shutil.which("yt-dlp") or shutil.which("yt-dlp.exe")
    if system_path:
        return system_path

    # 3. Fallback: assume it's in PATH and will be found by subprocess
    return "yt-dlp"
