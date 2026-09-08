"""
Settings service for YTSage Web UI.

Full whitelist of official ConfigManager keys (mirrors
ytsage/utils/ytsage_config_manager.py _default_config L72-106) with
per-key type/range validation, plus `build_download_defaults()` which
replicates the official GUI's config-injection behavior:
  - proxy/geo:            ytsage_gui_main.py L252-253
  - cookies restore:      ytsage_gui_main.py L355-380 (_initialize_cookie_settings_from_config)
  - speed limit convert:  ytsage_gui_main.py L879-891
  - filename/concurrent:  ytsage_gui_main.py L905-906
"""

import re
from pathlib import Path
from typing import Any, Dict, Optional

from .official_bridge import USER_HOME_DIR, cfg_get, cfg_set

# (key -> validator) - validators raise ValueError with i18n-able messages.
_BOOL = lambda v: bool(v)
_STR_OR_NONE = lambda v: None if v is None else str(v)
_STR = lambda v: str(v)


def _int_range(lo: int, hi: int):
    def check(v: Any) -> int:
        v = int(v)
        if not (lo <= v <= hi):
            raise ValueError(f"must be between {lo} and {hi}")
        return v
    return check


def _in_choices(*choices: str):
    def check(v: Any) -> str:
        v = str(v)
        if v not in choices:
            raise ValueError(f"must be one of: {', '.join(choices)}")
        return v
    return check


def _positive_number_or_none(v: Any) -> Optional[str]:
    if v is None or v == "":
        return None
    f = float(v)
    if f <= 0:
        raise ValueError("must be a positive number")
    return str(v)


def _proxy_scheme_or_none(v: Any) -> Optional[str]:
    if v is None or v == "":
        return None
    v = str(v)
    if not re.match(r"^(https?|socks5(?:_hostd)?|socks4)://", v):
        raise ValueError("proxy must start with http://, https://, socks5:// or socks4://")
    return v


def _bool_default_true(v: Any) -> bool:
    return not (v is False)


# Video codec priority (drag-order list in Settings -> Format tab)
CODEC_CHOICES = ("av01", "vp09", "avc1")
DEFAULT_CODEC_PRIORITY = ["av01", "vp09", "avc1"]


def _codec_priority_or_none(v: Any) -> Optional[list]:
    """Validate a codec-priority list: unique subset of CODEC_CHOICES, in order.

    Empty / None means "use the default order".
    """
    if v is None or v == "":
        return None
    if not isinstance(v, list):
        raise ValueError("must be a list of codecs")
    out = [str(x) for x in v]
    if len(set(out)) != len(out):
        raise ValueError("duplicate codecs")
    for c in out:
        if c not in CODEC_CHOICES:
            raise ValueError(f"unknown codec: {c} (expected one of {', '.join(CODEC_CHOICES)})")
    return out or None


# Full settings whitelist: key -> (validator, default)
SETTINGS_SCHEMA: Dict[str, Any] = {
    "download_path": (_STR, str(USER_HOME_DIR / "Downloads")),
    "generic_mode": (_BOOL, True),
    "speed_limit_value": (_positive_number_or_none, None),
    "speed_limit_unit_index": (_int_range(0, 1), 0),
    "cookie_source": (_in_choices("browser", "file"), "browser"),
    "cookie_browser": (_STR, "chrome"),
    "cookie_browser_profile": (_STR_OR_NONE, ""),
    "cookie_file_path": (_STR_OR_NONE, None),
    "cookie_active": (_BOOL, False),
    "cookie_remember": (_BOOL, True),
    "last_used_cookie_file": (_STR_OR_NONE, None),
    "proxy_url": (_proxy_scheme_or_none, None),
    "geo_proxy_url": (_proxy_scheme_or_none, None),
    "auto_update_ytdlp": (_BOOL, True),
    "auto_update_frequency": (_in_choices("startup", "daily", "weekly"), "daily"),
    "check_app_updates": (_BOOL, True),
    "check_beta_updates": (_BOOL, False),
    "last_update_check": (lambda v: float(v or 0), 0),
    # Global cap on how many download jobs run at the same time (server-side
    # queue). Replaces the old per-page batch concurrency selector.
    "max_concurrent_downloads": (_int_range(1, 10), 1),
    "play_notification_sound": (_BOOL, True),
    "language": (_in_choices("en", "zh"), "en"),
    "ytdlp_channel": (_in_choices("stable", "nightly"), "stable"),
    "force_output_format": (_BOOL, False),
    "preferred_output_format": (_in_choices("mp4", "webm", "mkv"), "mp4"),
    "force_audio_format": (_BOOL, False),
    "preferred_audio_format": (
        _in_choices("best", "aac", "mp3", "flac", "wav", "opus", "m4a", "vorbis"),
        "best",
    ),
    "audio_normalization": (_BOOL, False),
    "filename_format": (_STR, "%(title)s_%(resolution)s_[%(id)s].%(ext)s"),
    "default_video_quality": (_STR_OR_NONE, None),
    "default_subtitle_language": (_STR_OR_NONE, None),
    "codec_priority": (_codec_priority_or_none, list(DEFAULT_CODEC_PRIORITY)),
    # Optional explicit binary paths (top of the finder resolution chain).
    # Empty/None means "auto-detect" (env var -> app bin -> system PATH).
    "ytdlp_path": (_STR_OR_NONE, None),
    "ffmpeg_path": (_STR_OR_NONE, None),
    # Network resilience defaults (module 7.3). 10 = yt-dlp's own default.
    "download_retries": (_int_range(0, 100), 10),
    "fragment_retries": (_int_range(0, 100), 10),
}

PUBLIC_KEYS = list(SETTINGS_SCHEMA.keys())


def get_all_settings() -> Dict[str, Any]:
    """Read every whitelisted key (sync; wrap in to_thread for async)."""
    out: Dict[str, Any] = {}
    for key, (_validator, default) in SETTINGS_SCHEMA.items():
        val = cfg_get(key)
        out[key] = default if val is None else val
    if not out.get("download_path"):
        out["download_path"] = str(USER_HOME_DIR / "Downloads")
    return out


def update_settings(data: Dict[str, Any]) -> Dict[str, Any]:
    """Validate + write settings. Raises ValueError on unknown/invalid key.

    Returns the full settings snapshot after the update.
    """
    for key, value in data.items():
        if key not in SETTINGS_SCHEMA:
            raise ValueError(f"unknown setting: {key}")
        validator, _default = SETTINGS_SCHEMA[key]
        try:
            validated = validator(value)
        except (ValueError, TypeError) as e:
            raise ValueError(f"{key}: {e}")
        cfg_set(key, validated)
    return get_all_settings()


# ---------------------------------------------------------------------------
# Download defaults injection (mirrors official GUI start_download flow)
# ---------------------------------------------------------------------------

def convert_speed_limit(value: Any, unit_index: int) -> Optional[str]:
    """Convert stored speed limit to bytes/s string.

    Mirrors ytsage_gui_main.py L879-891 (0=KB/s, 1=MB/s).
    """
    if value is None or value == "":
        return None
    try:
        limit_value = float(value)
    except (ValueError, TypeError):
        return None
    if int(unit_index or 0) == 0:
        return str(int(limit_value * 1024))
    return str(int(limit_value * 1024 * 1024))


def get_active_cookie() -> Dict[str, Optional[str]]:
    """Resolve active cookies the way official GUI does.

    Mirrors ytsage_gui_main.py L355-380:
      - only when cookie_active AND remember (remember defaults True)
      - file source: path must still exist, else deactivate
      - browser source: "browser:profile" when profile set
    """
    result = {"cookie_file": None, "browser_cookies": None}
    remember = cfg_get("cookie_remember")
    should_remember = True if remember is None else bool(remember)
    if not cfg_get("cookie_active") or not should_remember:
        if not should_remember:
            cfg_set("cookie_active", False)
        return result

    source = cfg_get("cookie_source") or "browser"
    if source == "file":
        saved = cfg_get("cookie_file_path")
        if saved and Path(saved).exists():
            result["cookie_file"] = str(saved)
        else:
            cfg_set("cookie_active", False)
    else:
        browser = cfg_get("cookie_browser")
        if browser:
            profile = cfg_get("cookie_browser_profile") or ""
            result["browser_cookies"] = f"{browser}:{profile}" if profile else browser
    return result


def build_download_defaults() -> Dict[str, Any]:
    """Config-derived defaults for analyze/download (official injection flow)."""
    cookies = get_active_cookie()
    return {
        "proxy_url": cfg_get("proxy_url"),
        "geo_proxy_url": cfg_get("geo_proxy_url"),
        "rate_limit": convert_speed_limit(
            cfg_get("speed_limit_value"), cfg_get("speed_limit_unit_index") or 0
        ),
        "cookie_file": cookies["cookie_file"],
        "browser_cookies": cookies["browser_cookies"],
        "filename_format": cfg_get("filename_format"),
        "force_output_format": bool(cfg_get("force_output_format")),
        "preferred_output_format": cfg_get("preferred_output_format") or "mp4",
        "force_audio_format": bool(cfg_get("force_audio_format")),
        "preferred_audio_format": cfg_get("preferred_audio_format") or "best",
        "audio_normalization": bool(cfg_get("audio_normalization")),
        "generic_mode": cfg_get("generic_mode"),
        "download_path": cfg_get("download_path") or str(USER_HOME_DIR / "Downloads"),
    }
