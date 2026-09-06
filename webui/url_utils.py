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
