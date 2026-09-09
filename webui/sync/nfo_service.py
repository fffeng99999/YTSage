"""
YTSage Sync - NFO Generation Service
=====================================
Generate Emby/Jellyfin-compatible NFO metadata files for synced videos,
mirroring dysync.net's NfoFileGenerator:
  - per-video:  <title>.nfo   (movie root, plot, premiered, studio, actor,
                               uniqueid youtube, tag) + <title>-poster.jpg
  - playlists:  tvshow.nfo in the target folder (once), each video gets an
                episodedetails-style .nfo is skipped in favour of movie NFO
                because YouTube syncs are flat (no S01E01 renumbering).
"""

import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional
from xml.etree.ElementTree import Element, SubElement, tostring, indent

from . import store

logger = logging.getLogger("ytsage.webui.sync.nfo")


def _sanitize(name: str) -> str:
    """Windows/Linux-safe file stem (dysync DouyinFileNameHelper)."""
    name = re.sub(r'[\\/:*?"<>|]', "_", name or "").strip()
    return (name[:80]) or "video"


def _description_text(record: Dict[str, Any]) -> str:
    """Read the .description sidecar yt-dlp wrote next to the media file."""
    fp = record.get("file_path")
    if not fp:
        return ""
    try:
        p = Path(fp)
        for cand in (p.with_suffix(".description.txt"), p.with_suffix(".description"),
                     p.parent / f"{p.stem}.description"):
            if cand.is_file():
                return cand.read_text(encoding="utf-8", errors="replace")[:4000]
    except Exception:
        pass
    return ""


def generate_nfo(record: Dict[str, Any], output_dir: Path) -> bool:
    """Write <video_stem>.nfo (+ poster) for one record into its folder."""
    try:
        video_id = record.get("video_id")
        title = record.get("video_title") or "Unknown"
        channel = record.get("channel") or "Unknown"
        url = record.get("url") or ""
        kind = record.get("kind") or "video"
        first_sync = record.get("first_sync")
        file_path = record.get("file_path") or ""
        stem = _sanitize(Path(file_path).stem if file_path else video_id or title)

        root = Element("movie")
        SubElement(root, "title").text = title
        SubElement(root, "originaltitle").text = title
        plot = _description_text(record)
        SubElement(root, "plot").text = plot
        SubElement(root, "outline").text = plot[:300]
        if first_sync:
            SubElement(root, "dateadded").text = datetime.fromtimestamp(first_sync).strftime("%Y-%m-%d %H:%M:%S")
            SubElement(root, "premiered").text = datetime.fromtimestamp(first_sync).strftime("%Y-%m-%d")
        SubElement(root, "studio").text = channel
        actor = SubElement(root, "actor")
        SubElement(actor, "name").text = channel
        SubElement(actor, "role").text = "Channel"
        SubElement(root, "tag").text = (kind or "video").capitalize()
        uid = SubElement(root, "uniqueid")
        uid.set("type", "youtube")
        uid.set("default", "true")
        uid.text = video_id
        if url:
            SubElement(root, "website").text = url
        if file_path:
            SubElement(root, "filenameandpath").text = file_path

        indent(root)
        xml_str = '<?xml version="1.0" encoding="utf-8" standalone="yes"?>\n' + tostring(root, encoding="unicode")
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / f"{stem}.nfo").write_text(xml_str, encoding="utf-8")

        _save_poster(record, output_dir, stem)

        store._exec("UPDATE records SET nfo_generated=1 WHERE video_id=?", (video_id,))
        logger.info(f"[sync] Generated NFO for {video_id} in {output_dir}")
        return True
    except Exception as e:
        logger.error(f"[sync] Failed to generate NFO for {record.get('video_id')}: {e}")
        return False


def _save_poster(record: Dict[str, Any], output_dir: Path, stem: str) -> Optional[Path]:
    """Fetch the video thumbnail through the local thumbnail proxy and store
    it as <stem>-poster.jpg (dysync: 文件名-poster.jpg)."""
    thumb = record.get("thumbnail_url")
    if not thumb:
        return None
    try:
        from ..thumbnail_service import fetch_thumbnail
        src = fetch_thumbnail(thumb)
        if not src:
            return None
        dest = output_dir / f"{stem}-poster.jpg"
        dest.write_bytes(src.read_bytes())
        return dest
    except Exception as e:
        logger.warning(f"[sync] poster save failed for {record.get('video_id')}: {e}")
        return None


def generate_tvshow_nfo(target: Dict[str, Any], folder: Path) -> bool:
    """Playlists map to Emby TV shows: one tvshow.nfo per playlist folder."""
    try:
        folder.mkdir(parents=True, exist_ok=True)
        root = Element("tvshow")
        title = target.get("title") or target.get("folder") or "Playlist"
        SubElement(root, "title").text = title
        uid = SubElement(root, "uniqueid")
        uid.set("type", "youtube_playlist")
        uid.set("default", "true")
        uid.text = (target.get("url") or "").split("list=")[-1].split("&")[0] or title
        SubElement(root, "studio").text = "YouTube"
        indent(root)
        xml_str = '<?xml version="1.0" encoding="utf-8" standalone="yes"?>\n' + tostring(root, encoding="unicode")
        (folder / "tvshow.nfo").write_text(xml_str, encoding="utf-8")
        return True
    except Exception as e:
        logger.warning(f"[sync] tvshow.nfo failed for target {target.get('id')}: {e}")
        return False


def generate_nfo_for_video(video_id: str) -> bool:
    record = store.get_record(video_id)
    if not record:
        logger.warning(f"[sync] Cannot generate NFO: record not found for {video_id}")
        return False
    file_path = record.get("file_path")
    if not file_path:
        logger.warning(f"[sync] Cannot generate NFO: no file path for {video_id}")
        return False
    return generate_nfo(record, Path(file_path).parent)


def generate_nfo_batch(video_ids: list) -> Dict[str, Any]:
    success = failed = 0
    for video_id in video_ids:
        if generate_nfo_for_video(video_id):
            success += 1
        else:
            failed += 1
    return {"success": success, "failed": failed}
