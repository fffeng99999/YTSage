"""
Playlist export for YTSage Web UI.

Replicates official save_playlist_to_file (ytsage_gui_main.py L1649-1720)
for txt / m3u / csv / json. Returns (filename, content_bytes, mime).
"""

import csv
import io
import json
from typing import Any, Dict, List, Tuple

from .thumbnail_service import sanitize_filename


def _fmt_duration(duration: Any) -> str:
    """Official duration formatting (ytsage_gui_main.py L1670-1681)."""
    if not duration:
        return ""
    try:
        m, s = divmod(int(duration), 60)
        h, m = divmod(m, 60)
        if h > 0:
            return f" [{h}:{m:02d}:{s:02d}]"
        return f" [{m:02d}:{s:02d}]"
    except (ValueError, TypeError):
        return ""


def _entry_url(entry: Dict[str, Any]) -> str:
    url = entry.get("url") or ""
    if not url and entry.get("id"):
        url = f"https://www.youtube.com/watch?v={entry['id']}"
    return url


def export_playlist(entries: List[Dict[str, Any]], fmt: str, title: str = "playlist") -> Tuple[str, bytes, str]:
    base = sanitize_filename(title) or "playlist"
    if fmt == "txt":
        lines = []
        for index, entry in enumerate(entries):
            t = entry.get("title") or f"Video {index + 1}"
            lines.append(f"{index + 1}. {t}{_fmt_duration(entry.get('duration'))} - {_entry_url(entry)}\n")
        name = f"{base}.txt"
        return name, "".join(lines).encode("utf-8"), "text/plain; charset=utf-8"

    if fmt == "m3u":
        out = ["#EXTM3U\n"]
        for entry in entries:
            duration = int(entry.get("duration") or 0) if entry.get("duration") else 0
            t = entry.get("title") or "Unknown Title"
            out.append(f"#EXTINF:{duration},{t}\n{_entry_url(entry)}\n")
        return f"{base}.m3u", "".join(out).encode("utf-8"), "audio/x-mpegurl; charset=utf-8"

    if fmt == "csv":
        buf = io.StringIO()
        writer = csv.writer(buf, lineterminator="\n")
        writer.writerow(["Playlist Index", "Title", "URL", "Duration", "Uploader"])
        for index, entry in enumerate(entries):
            t = entry.get("title") or f"Video {index + 1}"
            formatted = f"{index + 1}. {t}{_fmt_duration(entry.get('duration'))}"
            writer.writerow([index + 1, formatted, _entry_url(entry), entry.get("duration") or "", entry.get("uploader") or ""])
        return f"{base}.csv", buf.getvalue().encode("utf-8-sig"), "text/csv; charset=utf-8"

    # json
    payload = json.dumps(entries, indent=4, ensure_ascii=False)
    return f"{base}.json", payload.encode("utf-8"), "application/json; charset=utf-8"
