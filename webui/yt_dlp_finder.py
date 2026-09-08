"""
Lightweight yt-dlp / ffmpeg path finder for YTSage Web UI.
Does NOT import from ytsage.core (which may require PySide6).

Resolution chain (module 3.2), first hit wins:
  1. WebUI custom setting  (settings keys `ytdlp_path` / `ffmpeg_path`)
  2. Environment variables (YTSAGE_YTDLP_PATH / YTSAGE_FFMPEG_PATH)
  3. App-managed bin dir   (where the official GUI installs binaries)
  4. shutil.which on the system PATH

When nothing is found, get_*_status() returns a structured
"environment missing" payload instead of crashing the backend.
"""

import os
import shutil
import sys
from pathlib import Path
from typing import Dict, Optional

# Safe import: ytsage_constants has NO PySide6 dependency
try:
    from ytsage.utils.ytsage_constants import YTDLP_APP_BIN_PATH, OS_NAME
except ImportError:
    OS_NAME = sys.platform
    if sys.platform == "win32":
        YTDLP_APP_BIN_PATH = Path.home() / "AppData" / "Local" / "YTSage" / "bin" / "yt-dlp.exe"
    elif sys.platform == "darwin":
        YTDLP_APP_BIN_PATH = Path.home() / "Library" / "Application Support" / "YTSage" / "bin" / "yt-dlp"
    else:
        YTDLP_APP_BIN_PATH = Path.home() / ".local" / "share" / "ytsage" / "bin" / "yt-dlp"

APP_BIN_DIR = YTDLP_APP_BIN_PATH.parent


def _cfg_path(key: str) -> Optional[Path]:
    """Read a custom binary path from WebUI settings (lazy import: the
    settings backend itself resolves yt-dlp through this module)."""
    try:
        from .official_bridge import cfg_get
        raw = cfg_get(key)
        if raw and str(raw).strip():
            p = Path(str(raw).strip())
            if p.is_file():
                return p
    except Exception:
        pass
    return None


def _resolve(name: str, cfg_key: str, env_key: str, bin_name: str) -> Dict[str, Optional[str]]:
    """Shared resolution chain. Returns {path, source}; path None if missing."""
    # 1. WebUI custom setting
    p = _cfg_path(cfg_key)
    if p:
        return {"path": str(p), "source": "setting"}
    # 2. Environment variable
    env = os.environ.get(env_key, "").strip()
    if env:
        pe = Path(env)
        if pe.is_file():
            return {"path": str(pe), "source": "env"}
    # 3. App-managed bin directory
    cand = APP_BIN_DIR / bin_name
    if cand.exists():
        return {"path": str(cand), "source": "app_bin"}
    # 4. System PATH
    which = shutil.which(bin_name) or shutil.which(name)
    if which:
        return {"path": which, "source": "system_path"}
    return {"path": None, "source": None}


def get_yt_dlp_status() -> Dict[str, Optional[str]]:
    """Structured detection result for yt-dlp (never raises)."""
    bin_name = "yt-dlp.exe" if sys.platform == "win32" else "yt-dlp"
    return _resolve("yt-dlp", "ytdlp_path", "YTSAGE_YTDLP_PATH", bin_name)


def get_ffmpeg_status() -> Dict[str, Optional[str]]:
    """Structured detection result for ffmpeg (never raises)."""
    bin_name = "ffmpeg.exe" if sys.platform == "win32" else "ffmpeg"
    return _resolve("ffmpeg", "ffmpeg_path", "YTSAGE_FFMPEG_PATH", bin_name)


def get_yt_dlp_path() -> str:
    """Find yt-dlp executable. Falls back to the bare name 'yt-dlp'
    (subprocess will then fail with a clear FileNotFoundError, and the
    structured reason is available via get_yt_dlp_status())."""
    status = get_yt_dlp_status()
    return status["path"] or "yt-dlp"


def get_ffmpeg_path() -> Optional[str]:
    """Find ffmpeg executable, or None when the environment lacks it."""
    return get_ffmpeg_status()["path"]


def missing_binaries() -> Dict[str, Dict[str, Optional[str]]]:
    """Env-missing summary for /api/health and the frontend banner."""
    out: Dict[str, Dict[str, Optional[str]]] = {}
    for tool, status in (("yt_dlp", get_yt_dlp_status()), ("ffmpeg", get_ffmpeg_status())):
        if not status["path"]:
            out[tool] = {
                "found": False,
                "hint_key": f"web.env_missing.{tool}",
                "checked": "setting > env > app_bin > PATH",
            }
    return out
