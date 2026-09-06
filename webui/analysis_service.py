"""
URL Analysis Service for YTSage Web UI.
Uses yt-dlp CLI via asyncio subprocess (no PySide6 dependency).

Results are cached by analysis_id (TTL 1h, LRU 20) so follow-up calls
(playlist export, re-download) don't need to re-run yt-dlp.
"""

import asyncio
import json
import subprocess
import sys
import time
import uuid
from collections import OrderedDict
from pathlib import Path
from typing import Any, Dict, List, Optional

from .yt_dlp_finder import get_yt_dlp_path

# ---------------------------------------------------------------------------
# Analysis result cache
# ---------------------------------------------------------------------------

_CACHE_TTL = 3600
_CACHE_MAX = 20
_cache: "OrderedDict[str, tuple]" = OrderedDict()
_cache_lock = asyncio.Lock()


def cache_put(result: Dict[str, Any]) -> str:
    analysis_id = uuid.uuid4().hex[:12]
    _cache[analysis_id] = (time.time(), result)
    _cache.move_to_end(analysis_id)
    while len(_cache) > _CACHE_MAX:
        _cache.popitem(last=False)
    return analysis_id


async def cache_get(analysis_id: str) -> Optional[Dict[str, Any]]:
    async with _cache_lock:
        item = _cache.get(analysis_id)
        if not item:
            return None
        ts, result = item
        if time.time() - ts > _CACHE_TTL:
            _cache.pop(analysis_id, None)
            return None
        return result


def _normalize_subtitles(video_info: Dict[str, Any]) -> List[Dict[str, str]]:
    """Merge manual + auto captions into [{code, type, name}] (deduped)."""
    out: List[Dict[str, str]] = []
    seen = set()
    for code in (video_info.get("subtitles") or {}):
        if code not in seen:
            seen.add(code)
            out.append({"code": code, "type": "manual"})
    for code in (video_info.get("automatic_captions") or {}):
        if code not in seen:
            seen.add(code)
            out.append({"code": code, "type": "auto"})
    return out


def _trim_format(fmt: Dict[str, Any]) -> Dict[str, Any]:
    """Strip huge fields (url/manifest) from format entries."""
    keep = ("format_id", "ext", "width", "height", "fps", "vcodec", "acodec",
            "filesize", "filesize_approx", "abr", "tbr", "format_note",
            "language", "language_code", "dynamic_range", "asr", "container")
    return {k: fmt.get(k) for k in keep if fmt.get(k) is not None}

# Safe import for SUBPROCESS_CREATIONFLAGS
try:
    from ytsage.utils.ytsage_constants import SUBPROCESS_CREATIONFLAGS
except ImportError:
    SUBPROCESS_CREATIONFLAGS = 0  # Default on non-Windows; or STARTF_USESHOWWINDOW on Windows


def _sync_run(cmd: List[str], timeout: int = 300) -> subprocess.CompletedProcess:
    """Run a command synchronously with proper flags."""
    kwargs = {"capture_output": True, "text": True, "timeout": timeout}
    if sys.platform == "win32":
        kwargs["creationflags"] = SUBPROCESS_CREATIONFLAGS
    return subprocess.run(cmd, **kwargs)


def build_auth_options(
    cmd: List[str],
    cookie_file: Optional[str] = None,
    browser_cookies: Optional[str] = None,
    proxy_url: Optional[str] = None,
    geo_proxy_url: Optional[str] = None,
) -> None:
    """Add authentication and proxy options to a yt-dlp command list."""
    has_cookies = False
    if cookie_file:
        cmd.extend(["--cookies", str(cookie_file)])
        has_cookies = True
    elif browser_cookies:
        cmd.extend(["--cookies-from-browser", browser_cookies])
        has_cookies = True

    if not has_cookies:
        cmd.extend(["--extractor-args", "youtube:player_client=web_embedded,default"])

    if proxy_url:
        cmd.extend(["--proxy", proxy_url])
    if geo_proxy_url:
        cmd.extend(["--geo-verification-proxy", geo_proxy_url])


def analyze_url(
    url: str,
    cookie_file: Optional[str] = None,
    browser_cookies: Optional[str] = None,
    proxy_url: Optional[str] = None,
    geo_proxy_url: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Analyze a YouTube URL and return video/playlist info.
    Mirrors the logic of official AnalysisThread but without PySide6.
    """
    yt_dlp_path = get_yt_dlp_path()
    if not yt_dlp_path or yt_dlp_path == "yt-dlp":
        # Verify yt-dlp actually works
        try:
            subprocess.run([yt_dlp_path, "--version"], capture_output=True, timeout=10)
        except (FileNotFoundError, subprocess.TimeoutExpired):
            raise RuntimeError("yt-dlp executable not found. Please install yt-dlp first.")

    # Clean up URL for playlist detection
    clean_url = url
    if "list=" in url and "watch?v=" in url:
        playlist_id = url.split("list=")[1].split("&")[0]
        clean_url = f"https://www.youtube.com/playlist?list={playlist_id}"

    # Step 1: basic playlist/video info
    cmd = [yt_dlp_path, "--dump-single-json", "--flat-playlist", "--no-warnings", clean_url]
    build_auth_options(cmd, cookie_file, browser_cookies, proxy_url, geo_proxy_url)

    result = _sync_run(cmd, timeout=300)
    if result.returncode != 0:
        error = result.stderr.strip() or "yt-dlp failed"
        raise RuntimeError(error)

    json_lines = [l.strip() for l in result.stdout.strip().split("\n") if l.strip()]
    if not json_lines:
        raise RuntimeError("No data returned from yt-dlp")

    first_info = json.loads(json_lines[0])

    analysis_result: Dict[str, Any] = {
        "is_playlist": False,
        "playlist_info": None,
        "playlist_entries": [],
        "video_info": None,
        "all_formats": [],
        "available_subtitles": {},
        "available_automatic_subtitles": {},
        "thumbnail_url": None,
    }

    if first_info.get("_type") == "playlist":
        analysis_result["is_playlist"] = True
        analysis_result["playlist_info"] = first_info
        playlist_entries = first_info.get("entries", [])
        analysis_result["playlist_entries"] = playlist_entries

        if not playlist_entries:
            raise RuntimeError("Playlist contains no valid videos")

        # Fetch full info for the first video to get formats
        first_video_url = playlist_entries[0].get("url")
        if first_video_url:
            cmd_single = [yt_dlp_path, "--dump-single-json", "--no-warnings", first_video_url]
            build_auth_options(cmd_single, cookie_file, browser_cookies, proxy_url, geo_proxy_url)
            try:
                result_single = _sync_run(cmd_single, timeout=60)
                if result_single.returncode == 0:
                    analysis_result["video_info"] = json.loads(result_single.stdout)
                else:
                    analysis_result["video_info"] = first_video_url
            except subprocess.TimeoutExpired:
                analysis_result["video_info"] = first_video_url
    else:
        analysis_result["is_playlist"] = False
        analysis_result["video_info"] = first_info

    # Extract formats, subtitles, thumbnail
    video_info = analysis_result.get("video_info")
    if isinstance(video_info, dict):
        analysis_result["all_formats"] = [_trim_format(f) for f in video_info.get("formats", [])]
        analysis_result["available_subtitles"] = video_info.get("subtitles", {})
        analysis_result["available_automatic_subtitles"] = video_info.get("automatic_captions", {})
        analysis_result["subtitles"] = _normalize_subtitles(video_info)
        # Compact video summary for the info card
        analysis_result["video_summary"] = {
            "title": video_info.get("title"),
            "channel": video_info.get("channel") or video_info.get("uploader"),
            "view_count": video_info.get("view_count"),
            "like_count": video_info.get("like_count"),
            "upload_date": video_info.get("upload_date"),
            "duration": video_info.get("duration"),
            "duration_string": video_info.get("duration_string"),
            "thumbnail": video_info.get("thumbnail"),
            "webpage_url": video_info.get("webpage_url") or video_info.get("url"),
        }
    else:
        analysis_result["subtitles"] = []

    playlist_info = analysis_result.get("playlist_info") or {}
    analysis_result["thumbnail_url"] = (
        playlist_info.get("thumbnail") or
        (video_info.get("thumbnail") if isinstance(video_info, dict) else None)
    )

    # Compact playlist entries (strip huge fields)
    if analysis_result["playlist_entries"]:
        analysis_result["playlist_entries"] = [
            {k: e.get(k) for k in ("index", "title", "url", "id", "duration", "uploader", "channel") if e.get(k) is not None}
            for e in analysis_result["playlist_entries"]
        ]

    # Cache full result and attach id
    analysis_result["analysis_id"] = cache_put(analysis_result)
    return analysis_result


async def analyze_url_async(
    url: str,
    cookie_file: Optional[str] = None,
    browser_cookies: Optional[str] = None,
    proxy_url: Optional[str] = None,
    geo_proxy_url: Optional[str] = None,
) -> Dict[str, Any]:
    """Async wrapper for analyze_url."""
    return await asyncio.to_thread(
        analyze_url, url, cookie_file, browser_cookies, proxy_url, geo_proxy_url
    )
