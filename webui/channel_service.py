"""
Batch & Channel analysis service for YTSage Web UI.

Adds two capabilities on top of analysis_service (existing single-URL
analysis is untouched):

1. analyze_batch()  - parse many URLs at once (bounded concurrency),
   return a compact per-URL summary suitable for a selection table.
2. analyze_channel() - parse a YouTube channel/homepage URL
   (@handle / channel/UC.. / c/.. / user/..) for a given tab
   (videos / shorts / streams) with a count limit, using
   `yt-dlp --flat-playlist --playlist-end N`.

Channel downloads then reuse the EXISTING playlist download path:
POST /api/download with is_playlist=true + playlist_items="1,3-5" on the
normalized tab URL (build_ytdlp_command already supports this).
"""

import asyncio
import json
import re
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

from .analysis_service import (
    _sync_run,
    analyze_url_async,
    build_auth_options,
    cache_put,
)
from .url_utils import YOUTUBE_DOMAINS, parse_yt_dlp_error_key, validate_video_url
from .yt_dlp_finder import get_yt_dlp_path

BATCH_MAX_URLS = 50
BATCH_CONCURRENCY = 3

CHANNEL_TABS = ("videos", "shorts", "streams")
# Suffixes that make sense to strip when normalizing a channel URL
_TAB_SUFFIXES = ("videos", "shorts", "streams", "playlists", "community", "featured", "about")


def _is_youtube_host(url: str) -> bool:
    try:
        host = urlparse(url).netloc.lower().split(":")[0]
    except Exception:
        return False
    return any(host == d or host.endswith("." + d) for d in YOUTUBE_DOMAINS)


def normalize_channel_url(url: str, tab: str) -> Tuple[Optional[str], Optional[str]]:
    """Normalize a channel URL to https://www.youtube.com/<handle-or-id>/{tab}.

    Returns (normalized_url, error_i18n_key). Exactly one is None.
    Accepts @handle, /channel/UC.., /c/.., /user/.. forms.
    """
    url = (url or "").strip()
    if not url:
        return None, "url_validation.empty_url"
    if not re.match(r"^https?://", url):
        url = "https://" + url
    if not _is_youtube_host(url):
        return None, "url_validation.unsupported_platform"

    try:
        parsed = urlparse(url)
    except Exception:
        return None, "url_validation.invalid_format"
    path = parsed.path or ""

    # Reject URLs that are clearly not a channel homepage
    if "/watch" in path:
        return None, "web.channel_err.watch_url"
    if "youtu.be" in parsed.netloc.lower():
        return None, "web.channel_err.watch_url"
    if "/playlist" in path:
        return None, "web.channel_err.playlist_url"

    # Extract the channel identifier part: @handle, /channel/UC.., /c/.., /user/..
    m = re.search(r"(/@[^/?#]+|/channel/[^/?#]+|/c/[^/?#]+|/user/[^/?#]+)", path)
    if m:
        ident = m.group(1)
    elif re.match(r"^/[^/]+$", path) and not path.rstrip("/").lower() in ("/watch", "/playlist", "/results", "/shorts", "/live", "/feed"):
        # Bare single-segment path (e.g. youtube.com/handle without /c/) - treat as channel
        ident = path
    else:
        return None, "web.channel_err.invalid_channel_url"

    if tab not in CHANNEL_TABS:
        return None, "web.channel_err.invalid_tab"

    base = f"{parsed.scheme}://{parsed.netloc}{ident.rstrip('/')}"
    return f"{base}/{tab}", None


def _entry_thumbnail(entry: Dict[str, Any]) -> Optional[str]:
    """Best-effort thumbnail URL for a flat-playlist entry.

    Flat entries often lack a top-level 'thumbnail'; prefer a whitelisted
    i.ytimg.com URL derived from the video id.
    """
    vid = entry.get("id")
    if vid:
        return f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg"
    thumbs = entry.get("thumbnails") or []
    for th in reversed(thumbs):
        u = th.get("url")
        if u:
            return u
    return entry.get("thumbnail")


def analyze_channel(
    url: str,
    tab: str = "videos",
    limit: int = 100,
    cookie_file: Optional[str] = None,
    browser_cookies: Optional[str] = None,
    proxy_url: Optional[str] = None,
    geo_proxy_url: Optional[str] = None,
) -> Dict[str, Any]:
    """Parse a channel tab URL into a list of videos (flat, fast)."""
    norm_url, err_key = normalize_channel_url(url, tab)
    if err_key:
        raise RuntimeError(err_key)

    yt_dlp_path = get_yt_dlp_path()
    limit = max(1, min(int(limit or 100), 1000))

    cmd = [
        yt_dlp_path, "--dump-single-json", "--flat-playlist", "--no-warnings",
        "--playlist-end", str(limit), norm_url,
    ]
    build_auth_options(cmd, cookie_file, browser_cookies, proxy_url, geo_proxy_url)

    result = _sync_run(cmd, timeout=300)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "yt-dlp failed")

    json_lines = [l.strip() for l in (result.stdout or "").strip().split("\n") if l.strip()]
    if not json_lines:
        raise RuntimeError("web.channel_err.empty_channel")
    info = json.loads(json_lines[0])

    if info.get("_type") != "playlist":
        # A single video was returned (e.g. URL resolved to one item)
        raise RuntimeError("web.channel_err.not_a_channel")

    raw_entries = [e for e in (info.get("entries") or []) if e]
    # index = array position (1-based): this is what --playlist-items selects on
    # the same tab URL, so it must match the order we show in the table.
    entries = []
    for i, e in enumerate(raw_entries):
        entries.append({
            "index": i + 1,
            "id": e.get("id"),
            "title": e.get("title"),
            "url": e.get("url") or (f"https://www.youtube.com/watch?v={e.get('id')}" if e.get("id") else None),
            "duration": e.get("duration"),
            "thumbnail": _entry_thumbnail(e),
        })

    channel_result: Dict[str, Any] = {
        "channel_info": {
            "title": info.get("title") or info.get("channel") or info.get("uploader"),
            "id": info.get("id"),
            "uploader": info.get("uploader") or info.get("channel"),
            "tab": tab,
            "normalized_url": norm_url,
        },
        "entries": entries,
        "total": len(entries),
    }
    channel_result["analysis_id"] = cache_put(channel_result)
    return channel_result


async def analyze_channel_async(
    url: str,
    tab: str = "videos",
    limit: int = 100,
    cookie_file: Optional[str] = None,
    browser_cookies: Optional[str] = None,
    proxy_url: Optional[str] = None,
    geo_proxy_url: Optional[str] = None,
) -> Dict[str, Any]:
    return await asyncio.to_thread(
        analyze_channel, url, tab, limit,
        cookie_file, browser_cookies, proxy_url, geo_proxy_url,
    )


async def _analyze_one(
    url: str,
    semaphore: asyncio.Semaphore,
    generic_mode: bool,
    cookie_file: Optional[str],
    browser_cookies: Optional[str],
    proxy_url: Optional[str],
    geo_proxy_url: Optional[str],
) -> Dict[str, Any]:
    """Analyze a single URL for the batch table; never raises."""
    ok, err_key = validate_video_url(url, generic_mode)
    if not ok:
        return {"url": url, "ok": False, "error": "", "error_key": err_key}

    async with semaphore:
        try:
            res = await analyze_url_async(
                url=url,
                cookie_file=cookie_file,
                browser_cookies=browser_cookies,
                proxy_url=proxy_url,
                geo_proxy_url=geo_proxy_url,
            )
        except RuntimeError as e:
            err = str(e)
            error_key, params = parse_yt_dlp_error_key(err)
            return {"url": url, "ok": False, "error": err, "error_key": error_key,
                    "error_params": params}
        except Exception as e:  # noqa: BLE001 - per-row failure must not break the batch
            err = str(e)
            error_key, params = parse_yt_dlp_error_key(err)
            return {"url": url, "ok": False, "error": err, "error_key": error_key,
                    "error_params": params}

    # Compact summary only (formats stay in the server-side cache)
    if res.get("is_playlist"):
        pl_info = res.get("playlist_info") or {}
        entries = res.get("playlist_entries") or []
        summary = {
            "title": pl_info.get("title"),
            "channel": pl_info.get("uploader") or pl_info.get("channel"),
            "thumbnail": res.get("thumbnail_url"),
            "duration_string": None,
            "count": len(entries),
        }
    else:
        vs = res.get("video_summary") or {}
        summary = {
            "title": vs.get("title"),
            "channel": vs.get("channel"),
            "thumbnail": vs.get("thumbnail") or res.get("thumbnail_url"),
            "duration_string": vs.get("duration_string"),
            "count": None,
        }
    return {
        "url": url,
        "ok": True,
        "is_playlist": bool(res.get("is_playlist")),
        "analysis_id": res.get("analysis_id"),
        "summary": summary,
    }


async def analyze_batch(
    urls: List[str],
    cookie_file: Optional[str] = None,
    browser_cookies: Optional[str] = None,
    proxy_url: Optional[str] = None,
    geo_proxy_url: Optional[str] = None,
    generic_mode: bool = False,
) -> List[Dict[str, Any]]:
    """Analyze many URLs with bounded concurrency. Returns per-URL results."""
    cleaned: List[str] = []
    seen = set()
    for u in urls:
        u = (u or "").strip()
        if u and u not in seen:
            seen.add(u)
            cleaned.append(u)
    if len(cleaned) > BATCH_MAX_URLS:
        raise RuntimeError(f"Too many URLs (max {BATCH_MAX_URLS})")

    semaphore = asyncio.Semaphore(BATCH_CONCURRENCY)
    tasks = [
        _analyze_one(u, semaphore, generic_mode, cookie_file, browser_cookies,
                     proxy_url, geo_proxy_url)
        for u in cleaned
    ]
    return await asyncio.gather(*tasks)
