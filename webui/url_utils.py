"""
URL validation & yt-dlp error parsing for YTSage Web UI.
Ported from official ytsage/core/ytsage_utils.py:
  - validate_video_url  (official L735-820)
  - parse_yt_dlp_error  (official L667-732)

Differences from official: errors are returned as i18n KEYS (e.g.
"ytdlp_errors.private_video") so the Vue frontend can translate them with
the same language files the desktop app uses.
"""

from typing import Tuple
from urllib.parse import urlparse

import re as _re

# C0/C1 control chars + NUL + DEL. yt-dlp receives every argument as an argv
# array (never shell=True), but control characters in a filename template or
# URL can still smuggle newlines into logs/ANSI terminals, so we strip them
# at the API boundary.
_CONTROL_CHARS = _re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]")


def strip_control_chars(value: str) -> str:
    """Remove control characters (\\n, \\r, \\0, etc.) from user input."""
    if not isinstance(value, str):
        return value
    return _CONTROL_CHARS.sub("", value).replace("\r", "").replace("\n", "")

# Mirrors official parse_yt_dlp_error keyword table (ytsage_utils.py L677-732)
_ERROR_RULES = [
    (("private video", "login_required", "sign in if you"), "ytdlp_errors.private_video"),
    (("age restricted", "age-restricted", "confirm your age"), "ytdlp_errors.age_restricted"),
    (
        (
            "not available in your country",
            "geo-blocked",
            "video is not available",
            "not made this video available in your country",
        ),
        "ytdlp_errors.geo_blocked",
    ),
    (
        ("video unavailable", "this video has been removed", "video does not exist"),
        "ytdlp_errors.video_unavailable",
    ),
    (("live stream", "livestream", "is live"), "ytdlp_errors.live_stream"),
    (("playlist", "no entries"), "ytdlp_errors.playlist_error"),
    (
        ("network error", "connection", "timeout", "unable to download"),
        "ytdlp_errors.network_error",
    ),
    (("invalid url", "unsupported url", "no video found"), "ytdlp_errors.invalid_url"),
    (
        ("youtube premium", "premium", "members only"),
        "ytdlp_errors.premium_content",
    ),
    (("copyright", "dmca", "blocked"), "ytdlp_errors.copyright_blocked"),
    (
        ("unable to extract", "extraction failed"),
        "ytdlp_errors.extraction_failed",
    ),
    # Postprocessing (ffmpeg merge/remux/subtitle-embed) failures happen AFTER
    # the download finished - they must NOT be reported as "cannot extract
    # video info / check your link", which sends users looking at the URL.
    (
        (
            "postprocessing",
            "error opening input files",
            "result too large",
            "conversion failed",
            "merging formats",
        ),
        "web.errors.postprocessing_failed",
    ),
]


def parse_yt_dlp_error_key(error_message: str) -> Tuple[str, dict]:
    """Map a raw yt-dlp error to (i18n_key, params).

    Official: ytsage_utils.parse_yt_dlp_error (L667).
    """
    error_str = error_message.lower()
    for keywords, key in _ERROR_RULES:
        if any(kw in error_str for kw in keywords):
            return key, {}
    return "ytdlp_errors.generic_error", {"error": error_message}


# Structured error codes for machine-readable handling (module 5.3).
# Checked in order; first match wins. Keys are stable API contract labels,
# independent of i18n evolution.
_ERROR_CODE_RULES = [
    (("no space left on device", "not enough disk space", "disk full"), "DISK_FULL"),
    (
        (
            "http error 429", "too many requests", "sign in to confirm",
            "not a bot", "captcha", "bot verification",
        ),
        "BOT_VERIFICATION",
    ),
    (
        (
            "not available in your country", "geo-blocked", "geo restricted",
            "video is not available in your country",
        ),
        "GEO_BLOCKED",
    ),
    (
        (
            "private video", "members-only", "members only",
            "this video is private", "login required",
        ),
        "PRIVATE_VIDEO",
    ),
    (
        (
            "video unavailable", "has been removed", "does not exist",
            "no longer available",
        ),
        "VIDEO_UNAVAILABLE",
    ),
    (
        (
            "network error", "connection", "timed out", "timeout",
            "unable to download", "getaddrinfo failed", "temporary failure",
        ),
        "NETWORK",
    ),
    (
        (
            "ffmpeg", "postprocessing", "conversion failed",
            "error opening input files", "result too large",
        ),
        "POSTPROCESSING",
    ),
]


def classify_error_code(error_message: str) -> str:
    """Map a raw error line to a stable structured code (or GENERIC)."""
    error_str = (error_message or "").lower()
    for keywords, code in _ERROR_CODE_RULES:
        if any(kw in error_str for kw in keywords):
            return code
    return "GENERIC"


# Mirrors official validate_video_url (ytsage_utils.py L735)
YOUTUBE_DOMAINS = [
    "youtube.com",
    "www.youtube.com",
    "youtu.be",
    "m.youtube.com",
    "music.youtube.com",
    "gaming.youtube.com",
]


def validate_video_url(url: str, generic_mode: bool = False) -> Tuple[bool, str]:
    """Return (is_valid, i18n_error_key). Empty key means valid."""
    if not url or not url.strip():
        return False, "url_validation.empty_url"

    url = url.strip()
    try:
        parsed = urlparse(url)
    except Exception:
        return False, "url_validation.invalid_format"

    if parsed.scheme not in ("http", "https"):
        return False, "url_validation.invalid_scheme"
    if not parsed.netloc:
        return False, "url_validation.missing_domain"

    if generic_mode:
        return True, ""

    netloc_lower = parsed.netloc.lower()
    # strip port
    netloc_host = netloc_lower.split(":")[0]
    is_youtube = any(
        netloc_host == d or netloc_host.endswith("." + d) for d in YOUTUBE_DOMAINS
    )
    if not is_youtube:
        return False, "url_validation.unsupported_platform"
    return True, ""
