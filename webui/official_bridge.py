"""
Official ytsage package bridge for YTSage Web UI.
=================================================
Centralizes ALL imports from the official `ytsage` package with graceful
fallbacks. Nothing in this module may modify official source files; imports
are read-only. Long-running official singletons (ConfigManager, HistoryManager)
are synchronous + RLock-based, so every call is wrapped with asyncio.to_thread.

Capability flags:
  HAS_CONSTANTS  - ytsage.utils.ytsage_constants importable
  HAS_CONFIG     - official ConfigManager usable
  HAS_HISTORY    - official HistoryManager usable (SQLite, shared with desktop)
  HAS_FFMPEG_CORE- ytsage.core.ytsage_ffmpeg usable (needs requests, no PySide6)
"""

import asyncio
import logging
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger("ytsage.webui")

# ---------------------------------------------------------------------------
# Constants (no PySide6 dependency)
# ---------------------------------------------------------------------------

HAS_CONSTANTS = False
try:
    from ytsage.utils.ytsage_constants import (  # noqa: F401
        APP_BIN_DIR,
        APP_DATA_DIR,
        APP_DIR,
        APP_LOG_DIR,
        APP_THUMBNAILS_DIR,
        AUDIO_EXTENSIONS,
        MEDIA_EXTENSIONS,
        OS_NAME,
        SOUND_PATH,
        SUBPROCESS_CREATIONFLAGS,
        SUBTITLE_EXTENSIONS,
        USER_HOME_DIR,
        VIDEO_EXTENSIONS,
        DENO_APP_BIN_PATH,
        FFMPEG_ZIP_DOWNLOAD_URL,
        FFMPEG_ZIP_VERSION_URL,
        YTDLP_APP_BIN_PATH,
        YTDLP_DOCS_URL,
    )
    HAS_CONSTANTS = True
except ImportError:
    import os
    import subprocess
    import sys

    OS_NAME = "Windows" if sys.platform == "win32" else ("Darwin" if sys.platform == "darwin" else "Linux")
    USER_HOME_DIR = Path.home()
    if OS_NAME == "Windows":
        APP_DIR = Path(os.environ.get("LOCALAPPDATA", USER_HOME_DIR / "AppData" / "Local")) / "YTSage"
    elif OS_NAME == "Darwin":
        APP_DIR = USER_HOME_DIR / "Library" / "Application Support" / "YTSage"
    else:
        APP_DIR = USER_HOME_DIR / ".local" / "share" / "YTSage"
    APP_BIN_DIR = APP_DIR / "bin"
    APP_DATA_DIR = APP_DIR / "data"
    APP_LOG_DIR = APP_DIR / "logs"
    APP_THUMBNAILS_DIR = APP_DATA_DIR / "thumbnails"
    YTDLP_APP_BIN_PATH = APP_BIN_DIR / ("yt-dlp.exe" if OS_NAME == "Windows" else "yt-dlp")
    DENO_APP_BIN_PATH = APP_BIN_DIR / ("deno.exe" if OS_NAME == "Windows" else "deno")
    _dl_name = {"Windows": "yt-dlp.exe", "Darwin": "yt-dlp_macos"}.get(OS_NAME, "yt-dlp")
    YTDLP_DOWNLOAD_URL = f"https://github.com/yt-dlp/yt-dlp/releases/latest/download/{_dl_name}"
    SOUND_PATH = Path(__file__).parent.parent / "ytsage" / "assets" / "sound" / "notification.mp3"
    SUBPROCESS_CREATIONFLAGS = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    VIDEO_EXTENSIONS = frozenset({".mp4", ".webm", ".mkv", ".avi", ".mov", ".flv"})
    AUDIO_EXTENSIONS = frozenset({".mp3", ".m4a", ".aac", ".wav", ".ogg", ".opus", ".flac"})
    SUBTITLE_EXTENSIONS = frozenset({".vtt", ".srt", ".ass", ".ssa"})
    MEDIA_EXTENSIONS = VIDEO_EXTENSIONS | AUDIO_EXTENSIONS
    YTDLP_DOCS_URL = "https://github.com/yt-dlp/yt-dlp?tab=readme-ov-file#usage-and-options"
    FFMPEG_ZIP_DOWNLOAD_URL = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
    FFMPEG_ZIP_VERSION_URL = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip.ver"

for _d in (APP_DATA_DIR, APP_THUMBNAILS_DIR):
    try:
        _d.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass

# ---------------------------------------------------------------------------
# App version
# ---------------------------------------------------------------------------

HAS_APP = False
try:
    from ytsage import __version__ as APP_VERSION
    HAS_APP = True
except ImportError:
    APP_VERSION = "webui-only"

# ---------------------------------------------------------------------------
# ConfigManager (official, thread-safe singleton)
# ---------------------------------------------------------------------------

HAS_CONFIG = False
try:
    from ytsage.utils.ytsage_config_manager import ConfigManager as _OfficialConfigManager
    HAS_CONFIG = True
except ImportError:
    _OfficialConfigManager = None

# Fallback JSON config shim (used only when official package unavailable)
_FALLBACK_CONFIG_FILE = Path(__file__).parent.parent / "webui" / ".fallback_config.json"


class _FallbackConfig:
    """Minimal JSON-file-backed config shim mirroring ConfigManager API."""

    def __init__(self) -> None:
        self._data: Optional[Dict[str, Any]] = None

    def _load(self) -> Dict[str, Any]:
        if self._data is None:
            if _FALLBACK_CONFIG_FILE.exists():
                import json
                try:
                    self._data = json.loads(_FALLBACK_CONFIG_FILE.read_text(encoding="utf-8"))
                except Exception:
                    self._data = {}
            else:
                self._data = {}
        return self._data

    def get(self, key: str) -> Any:
        d = self._load()
        for part in key.split("."):
            if isinstance(d, dict) and part in d:
                d = d[part]
            else:
                return None
        return d

    def set(self, key: str, value: Any) -> None:
        import json
        d = self._load()
        parts = key.split(".")
        for part in parts[:-1]:
            d = d.setdefault(part, {})
        d[parts[-1]] = value
        try:
            _FALLBACK_CONFIG_FILE.write_text(json.dumps(self._data, indent=2), encoding="utf-8")
        except Exception as e:
            logger.warning(f"[WebUI] fallback config save failed: {e}")


_config_shim = _FallbackConfig()


def cfg_get(key: str) -> Any:
    """Read a config value (sync; call via to_thread in async contexts)."""
    if _OfficialConfigManager is not None:
        return _OfficialConfigManager.get(key)
    return _config_shim.get(key)


def cfg_set(key: str, value: Any) -> None:
    if _OfficialConfigManager is not None:
        _OfficialConfigManager.set(key, value)
    else:
        _config_shim.set(key, value)


async def cfg_get_async(key: str) -> Any:
    return await asyncio.to_thread(cfg_get, key)


async def cfg_set_async(key: str, value: Any) -> None:
    await asyncio.to_thread(cfg_set, key, value)


# ---------------------------------------------------------------------------
# HistoryManager (official SQLite, shared with desktop app)
# ---------------------------------------------------------------------------

HAS_HISTORY = False
try:
    from ytsage.utils.ytsage_history_manager import HistoryManager as _OfficialHistoryManager
    HAS_HISTORY = True
except ImportError:
    _OfficialHistoryManager = None

# ---------------------------------------------------------------------------
# FFmpeg core (ytsage.core.ytsage_ffmpeg - only needs requests, no PySide6)
# ---------------------------------------------------------------------------

HAS_FFMPEG_CORE = False
try:
    from ytsage.core import ytsage_ffmpeg as _official_ffmpeg_core
    HAS_FFMPEG_CORE = True
except ImportError:
    _official_ffmpeg_core = None

# ---------------------------------------------------------------------------
# Languages directory (official JSON files, read as data - not imported)
# ---------------------------------------------------------------------------

LANGUAGES_DIR = Path(__file__).parent.parent / "ytsage" / "languages"
if not LANGUAGES_DIR.exists():
    LANGUAGES_DIR = Path(APP_DATA_DIR) / "languages"


async def run_blocking(fn: Callable, *args: Any) -> Any:
    """Run a blocking callable in a worker thread."""
    return await asyncio.to_thread(fn, *args)
