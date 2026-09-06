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
from urllib.parse import urlparse

import requests

from .official_bridge import APP_THUMBNAILS_DIR

logger = logging.getLogger("ytsage.webui")

_ALLOWED_HOST_SUFFIXES = (".youtube.com", ".ytimg.com", ".googlevideo.com")


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
    """Download (or reuse cached) thumbnail; returns local path or None."""
    if not is_allowed_thumbnail_url(url):
        return None
    target = cache_path_for(url)
    if target.exists() and target.stat().st_size > 0:
        return target
    try:
        resp = requests.get(url, timeout=15, stream=True)
        resp.raise_for_status()
        tmp = target.with_suffix(".tmp")
        with open(tmp, "wb") as f:
            for chunk in resp.iter_content(65536):
                f.write(chunk)
        tmp.replace(target)
        return target
    except Exception as e:
        logger.warning(f"[WebUI] thumbnail fetch failed: {e}")
        try:
            target.with_suffix(".tmp").unlink(missing_ok=True)
        except Exception:
            pass
        return None


def sanitize_filename(name: str) -> str:
    """Official: ytsage_gui_video_info.py L471-473."""
    return re.sub(r'[\\/*?:"<>|]', "", name).strip()[:75]


def save_thumbnail_to_dir(thumbnail_url: str, download_path: str, title: str) -> Optional[Path]:
    """Save thumbnail to <download_path>/Thumbnails/<sanitized title>.jpg.

    Official: ytsage_gui_video_info.py L426-469.
    """
    try:
        src = fetch_thumbnail(thumbnail_url) if thumbnail_url else None
        if not src:
            return None
        thumb_dir = Path(download_path) / "Thumbnails"
        thumb_dir.mkdir(parents=True, exist_ok=True)
        dest = thumb_dir / f"{sanitize_filename(title or 'thumbnail')}.jpg"
        dest.write_bytes(src.read_bytes())
        return dest
    except Exception as e:
        logger.warning(f"[WebUI] save_thumbnail failed: {e}")
        return None
