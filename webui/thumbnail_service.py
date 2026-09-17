"""
Thumbnail service for YTSage Web UI.

- Proxies thumbnail fetches through the server (browser img tags can be
  blocked by referer policies) with disk cache in APP_THUMBNAILS_DIR,
  mirroring official HistoryDelegate caching (ytsage_dialogs_history.py).
- save_thumbnail_to_dir(): replicates official download_thumbnail_file
  (ytsage_gui_video_info.py L426-469) but writes raw JPEG bytes instead of
  PIL re-encoding (no pillow dependency).
"""

import hashlib
import logging
import re
from pathlib import Path
from typing import Optional
from urllib.parse import urljoin, urlparse

import requests

from .official_bridge import APP_THUMBNAILS_DIR

logger = logging.getLogger("ytsage.webui")

_ALLOWED_HOST_SUFFIXES = (".youtube.com", ".ytimg.com", ".googlevideo.com")
_MAX_THUMBNAIL_BYTES = 8 * 1024 * 1024


def is_allowed_thumbnail_url(url: str) -> bool:
    try:
        parsed = urlparse(url)
    except Exception:
        return False
    if parsed.scheme not in ("http", "https"):
        return False
    host = (parsed.netloc or "").lower().split(":")[0]
    return any(host == s.lstrip(".") or host.endswith(s) for s in _ALLOWED_HOST_SUFFIXES)


def cache_path_for(url: str) -> Path:
    digest = hashlib.sha1(url.encode("utf-8")).hexdigest()
    return APP_THUMBNAILS_DIR / f"{digest}.jpg"


def fetch_thumbnail(url: str) -> Optional[Path]:
    """Download (or reuse cached) thumbnail; returns local path or None.

    Redirects are followed manually and re-validated at every hop: an open
    redirect on a whitelisted host would otherwise turn this public endpoint
    into an SSRF probe. The body is capped so it cannot fill the disk.
    """
    if not is_allowed_thumbnail_url(url):
        return None
    target = cache_path_for(url)
    if target.exists() and target.stat().st_size > 0:
        return target
    tmp = target.with_suffix(".tmp")
    try:
        current = url
        resp = None
        for _ in range(4):
            resp = requests.get(current, timeout=15, stream=True, allow_redirects=False)
            if resp.status_code in (301, 302, 303, 307, 308):
                location = resp.headers.get("Location")
                if not location:
                    break
                current = urljoin(current, location)
                if not is_allowed_thumbnail_url(current):
                    logger.warning("[WebUI] thumbnail redirect left the host whitelist")
                    return None
                continue
            break
        if resp is None:
            return None
        resp.raise_for_status()
        declared = resp.headers.get("Content-Length")
        if declared and declared.isdigit() and int(declared) > _MAX_THUMBNAIL_BYTES:
            logger.warning("[WebUI] thumbnail rejected: content too large")
            return None
        written = 0
        with open(tmp, "wb") as f:
            for chunk in resp.iter_content(65536):
                written += len(chunk)
                if written > _MAX_THUMBNAIL_BYTES:
                    raise ValueError("thumbnail exceeds size limit")
                f.write(chunk)
        tmp.replace(target)
        return target
    except Exception as e:
        logger.warning(f"[WebUI] thumbnail fetch failed: {e}")
        try:
            tmp.unlink(missing_ok=True)
        except Exception:
            pass
        return None


def sanitize_filename(name: str) -> str:
    """Official: ytsage_gui_video_info.py L471-473."""
    return re.sub(r'[\\/*?:"<>|]', "", name).strip()[:75]


def save_thumbnail_to_dir(thumbnail_url: str, download_path: str, title: str) -> Optional[Path]:
    """Save thumbnail as <download_path>/<sanitized title>.jpg.

    download_path is the per-video folder created by yt-dlp (the parent of
    the downloaded media file), so all files related to one video stay
    together in the same folder.
    """
    try:
        src = fetch_thumbnail(thumbnail_url) if thumbnail_url else None
        if not src:
            return None
        thumb_dir = Path(download_path)
        thumb_dir.mkdir(parents=True, exist_ok=True)
        dest = thumb_dir / f"{sanitize_filename(title or 'thumbnail')}.jpg"
        dest.write_bytes(src.read_bytes())
        return dest
    except Exception as e:
        logger.warning(f"[WebUI] save_thumbnail failed: {e}")
        return None
