"""
Pydantic request/response models for YTSage Web UI.
"""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    password: str


class PasswordChangeRequest(BaseModel):
    current_password: str
    new_password: str


class AnalyzeRequest(BaseModel):
    url: str
    cookie_file: Optional[str] = None
    browser_cookies: Optional[str] = None
    proxy_url: Optional[str] = None
    geo_proxy_url: Optional[str] = None


class DownloadRequest(BaseModel):
    """All fields mirror official DownloadThread.__init__ (ytsage_downloader.py L60-123).

    Optional fields left as None fall back to ConfigManager values at
    download start (mirrors how the desktop GUI injects settings).
    """
    url: str
    path: str
    format_id: Optional[str] = None
    is_audio_only: bool = False
    format_has_audio: bool = False
    audio_format_ids: Optional[List[str]] = None
    subtitle_langs: Optional[List[str]] = None
    is_playlist: bool = False
    merge_subs: bool = False
    enable_sponsorblock: bool = False
    sponsorblock_categories: Optional[List[str]] = None
    resolution: str = ""
    playlist_items: Optional[str] = None
    save_description: bool = False
    save_thumbnail: bool = False
    embed_chapters: bool = False
    embed_metadata: bool = False
    embed_thumbnail: bool = False
    cookie_file: Optional[str] = None
    browser_cookies: Optional[str] = None
    rate_limit: Optional[str] = None
    download_section: Optional[str] = None
    force_keyframes: bool = False
    proxy_url: Optional[str] = None
    geo_proxy_url: Optional[str] = None
    force_output_format: Optional[bool] = None
    preferred_output_format: Optional[str] = None
    force_audio_format: Optional[bool] = None
    preferred_audio_format: Optional[str] = None
    audio_normalization: Optional[bool] = None
    filename_format: Optional[str] = None
    concurrent_fragments: Optional[int] = None
    # Metadata for history entries (official writes history from video_info)
    title: Optional[str] = None
    channel: Optional[str] = None
    duration: Optional[str] = None
    thumbnail_url: Optional[str] = None
    analysis_id: Optional[str] = None


class PlaylistExportRequest(BaseModel):
    analysis_id: Optional[str] = None
    entries: Optional[List[Dict[str, Any]]] = None
    format: str = Field(pattern=r"^(txt|m3u|csv|json)$")
    title: Optional[str] = None


class RevealRequest(BaseModel):
    path: str


class OpenFolderRequest(BaseModel):
    path: str


class CookieApplyRequest(BaseModel):
    source: str = Field(pattern=r"^(browser|file)$")
    browser: Optional[str] = None
    profile: Optional[str] = None
    # Netscape cookie file content pasted by the user (saved server-side)
    file_content: Optional[str] = None
    remember: bool = True


class CommandRunRequest(BaseModel):
    command: str
    url: Optional[str] = None
    path: Optional[str] = None


class YtdlpChannelRequest(BaseModel):
    channel: str = Field(pattern=r"^(stable|nightly)$")


class YtdlpAutoUpdateRequest(BaseModel):
    enabled: bool
    frequency: str = Field(pattern=r"^(startup|daily|weekly)$")


class SetupCompleteRequest(BaseModel):
    password: str
    mode: str = "standalone"  # "standalone" | "shared"
    download_path: Optional[str] = None
    language: str = "en"
    import_desktop: bool = False
