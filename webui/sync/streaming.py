"""
YTSage Sync - Video Streaming Service
======================================
HTTP Range request support for in-browser video playback.
"""

import os
from pathlib import Path
from typing import Optional

from fastapi import HTTPException
from fastapi.responses import StreamingResponse, FileResponse

from . import store
from ..system_service import is_path_allowed


def _get_video_path(video_id: str) -> Path:
    """Get the file path for a video by its ID."""
    record = store.get_record(video_id)
    if not record:
        raise HTTPException(status_code=404, detail="Video not found")
    
    file_path = record.get("file_path")
    if not file_path:
        raise HTTPException(status_code=404, detail="Video file path not recorded")
    
    path = Path(file_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Video file not found on disk")
    
    if not is_path_allowed(path):
        raise HTTPException(status_code=403, detail="Access denied")
    
    return path


def _get_content_type(path: Path) -> str:
    """Determine MIME type from file extension."""
    ext = path.suffix.lower()
    mime_map = {
        ".mp4": "video/mp4",
        ".webm": "video/webm",
        ".mkv": "video/x-matroska",
        ".avi": "video/x-msvideo",
        ".mov": "video/quicktime",
    }
    return mime_map.get(ext, "application/octet-stream")


async def stream_video(video_id: str, range_header: Optional[str] = None):
    """
    Stream a video file with HTTP Range support.
    
    Args:
        video_id: The video ID to stream
        range_header: HTTP Range header value (e.g., "bytes=0-1023")
    
    Returns:
        StreamingResponse or FileResponse
    """
    path = _get_video_path(video_id)
    content_type = _get_content_type(path)
    file_size = path.stat().st_size
    
    # Parse Range header if present
    if range_header:
        try:
            # Format: "bytes=START-END"
            range_spec = range_header.replace("bytes=", "")
            start_str, end_str = range_spec.split("-")
            
            start = int(start_str) if start_str else 0
            end = int(end_str) if end_str else file_size - 1
            
            # Validate range
            if start < 0 or start >= file_size:
                raise HTTPException(status_code=416, detail="Invalid range start")
            if end >= file_size:
                end = file_size - 1
            if start > end:
                raise HTTPException(status_code=416, detail="Invalid range")
            
            content_length = end - start + 1
            
            def iter_file():
                with open(path, "rb") as f:
                    f.seek(start)
                    remaining = content_length
                    chunk_size = 8192
                    while remaining > 0:
                        chunk = f.read(min(chunk_size, remaining))
                        if not chunk:
                            break
                        remaining -= len(chunk)
                        yield chunk
            
            headers = {
                "Content-Range": f"bytes {start}-{end}/{file_size}",
                "Accept-Ranges": "bytes",
                "Content-Length": str(content_length),
            }
            
            return StreamingResponse(
                iter_file(),
                status_code=206,
                media_type=content_type,
                headers=headers,
            )
        except (ValueError, IndexError):
            raise HTTPException(status_code=416, detail="Invalid range header")
    
    # No Range header - return full file
    return FileResponse(
        path,
        media_type=content_type,
        headers={"Accept-Ranges": "bytes"},
    )


async def get_video_head(video_id: str):
    """
    Return HEAD response for a video (size, type, etc.).
    
    Args:
        video_id: The video ID
    
    Returns:
        dict with file metadata
    """
    path = _get_video_path(video_id)
    content_type = _get_content_type(path)
    file_size = path.stat().st_size
    
    return {
        "content_type": content_type,
        "content_length": file_size,
        "accept_ranges": "bytes",
    }
