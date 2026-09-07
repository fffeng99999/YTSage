"""
Async Download Manager for YTSage Web UI.
Builds yt-dlp command lines matching official DownloadThread logic,
but runs via asyncio.create_subprocess_exec (no PySide6 dependency).

Progress events are pushed to the shared event bus for WebSocket broadcast.

Official parity notes:
  - build_ytdlp_command mirrors DownloadThread._build_yt_dlp_command
    (ytsage/core/ytsage_downloader.py L241-484)
  - pause is cooperative: process keeps running, read loop suspends
    (official L556-557)
  - cancel kills the whole process tree and cleans partial files
    (official _terminate_process_tree L160-205, cleanup_partial_files L125-133)
  - completed downloads write to the shared HistoryManager
    (official ytsage_gui_main.py download_finished L1004-1042)
"""

import asyncio
import gc
import locale
import logging
import re
import shlex
import sys
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from .event_bus import bus, throttled
from .official_bridge import cfg_get
from .yt_dlp_finder import get_yt_dlp_path

# Safe imports: these have NO PySide6 dependency
try:
    from ytsage.utils.ytsage_constants import (
        SUBPROCESS_CREATIONFLAGS,
        VIDEO_EXTENSIONS,
        AUDIO_EXTENSIONS,
        SUBTITLE_EXTENSIONS,
        MEDIA_EXTENSIONS,
    )
except ImportError:
    SUBPROCESS_CREATIONFLAGS = 0
    VIDEO_EXTENSIONS = {".mp4", ".mkv", ".webm", ".mov", ".avi", ".flv"}
    AUDIO_EXTENSIONS = {".mp3", ".m4a", ".wav", ".flac", ".aac", ".ogg", ".opus"}
    SUBTITLE_EXTENSIONS = {".vtt", ".srt", ".ass", ".ssa"}
    MEDIA_EXTENSIONS = VIDEO_EXTENSIONS | AUDIO_EXTENSIONS | {".mkv", ".webm"}

# Use standard logging instead of loguru (avoids extra dep)
logger = logging.getLogger("ytsage.webui")
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

# On Windows, the frozen yt-dlp exe writes non-ASCII output (e.g. CJK file
# names) using the system ANSI codepage (cp936 on zh_CN), NOT UTF-8, and
# PYTHONIOENCODING has no effect on it. Note cp936 byte pairs often form
# *valid* UTF-8 accidentally, so on Windows we must try ANSI first.
# locale.getpreferredencoding() can return "utf-8" under modern Python
# UTF-8 mode, so read the real ACP via ctypes (GetACP).
def _detect_output_encoding() -> str:
    if sys.platform == "win32":
        try:
            import ctypes
            acp = ctypes.windll.kernel32.GetACP()
            return f"cp{acp}"
        except Exception:
            pass
    try:
        enc = locale.getpreferredencoding(False)
        if enc and enc.lower().replace("-", "") not in ("utf8",):
            return enc
    except Exception:
        pass
    return "utf-8"


_ANSI_ENCODING = _detect_output_encoding()


def decode_output(data: bytes) -> str:
    if sys.platform == "win32":
        try:
            return data.decode(_ANSI_ENCODING)
        except (UnicodeDecodeError, LookupError):
            return data.decode("utf-8", errors="replace")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode(_ANSI_ENCODING, errors="replace")


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class DownloadJob:
    """Represents a single download task."""
    job_id: str
    url: str
    path: str
    format_id: Optional[str] = None
    is_audio_only: bool = False
    format_has_audio: bool = False
    audio_format_ids: List[str] = field(default_factory=list)
    subtitle_langs: List[str] = field(default_factory=list)
    is_playlist: bool = False
    merge_subs: bool = False
    enable_sponsorblock: bool = False
    sponsorblock_categories: List[str] = field(default_factory=lambda: ["sponsor"])
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
    force_output_format: bool = False
    preferred_output_format: str = "mp4"
    force_audio_format: bool = False
    preferred_audio_format: str = "best"
    audio_normalization: bool = False
    filename_format: Optional[str] = None
    concurrent_fragments: int = 1

    # History metadata (official writes history from video_info)
    title: Optional[str] = None
    channel: Optional[str] = None
    duration: Optional[str] = None
    thumbnail_url: Optional[str] = None

    # Runtime state
    status: str = "pending"
    progress: float = 0.0
    current_filename: Optional[str] = None
    last_file_path: Optional[str] = None
    error: Optional[str] = None
    error_key: Optional[str] = None
    speed: str = ""
    eta: str = ""
    stage: str = ""
    file_exists: bool = False
    history_id: Optional[str] = None

    # Process control
    _process: Optional[asyncio.subprocess.Process] = field(default=None, repr=False)
    _paused: bool = False
    _cancelled: bool = False
    _subtitle_files_before: set = field(default_factory=set, repr=False)


# ---------------------------------------------------------------------------
# Command builder (mirrors official DownloadThread._build_yt_dlp_command)
# ---------------------------------------------------------------------------

def build_ytdlp_command(job: DownloadJob) -> List[str]:
    """Build yt-dlp command line. Adapted from official DownloadThread."""
    yt_dlp_path = get_yt_dlp_path()
    cmd: List[str] = [yt_dlp_path]

    # Force progress lines to end with \n instead of \r-overwrite.
    # Required because asyncio StreamReader.readline() only splits on \n;
    # the official GUI gets this for free via text-mode universal newlines.
    cmd.append("--newline")

    if job.concurrent_fragments:
        cmd.extend(["-N", str(job.concurrent_fragments)])

    # --- Format selection ---
    if job.is_playlist:
        if job.is_audio_only:
            cmd.extend(["-f", "bestaudio/best"])
        elif job.format_id:
            clean = job.format_id.split("-drc")[0] if "-drc" in job.format_id else job.format_id
            cmd.extend(["-f", clean])
        else:
            try:
                if job.resolution and job.resolution != "default":
                    h = min(map(int, job.resolution.split("x"))) if "x" in job.resolution else int(job.resolution)
                    cmd.extend(["-S", f"res:{h}"])
                else:
                    cmd.extend(["-f", "bestvideo+bestaudio/best"])
            except ValueError:
                cmd.extend(["-f", "bestvideo+bestaudio/best"])
    elif job.format_id:
        clean = job.format_id.split("-drc")[0] if "-drc" in job.format_id else job.format_id

        if job.is_audio_only and job.audio_format_ids:
            clean_audio_ids = [a.split("-drc")[0] if "-drc" in a else a for a in job.audio_format_ids]
            merged = "+".join([clean] + clean_audio_ids)
            cmd.extend(["-f", merged])
            cmd.append("--audio-multistreams")
        elif job.is_audio_only:
            cmd.extend(["-f", clean])
        elif job.audio_format_ids:
            clean_audio_ids = [a.split("-drc")[0] if "-drc" in a else a for a in job.audio_format_ids]
            merged = "+".join([clean] + clean_audio_ids)
            cmd.extend(["-f", merged])
            cmd.append("--audio-multistreams")
        elif job.format_has_audio:
            cmd.extend(["-f", clean])
        else:
            cmd.extend(["-f", f"{clean}+bestaudio/best"])
    else:
        res = job.resolution or "720"
        cmd.extend(["-S", f"res:{res}"])

    # --- Output format forcing ---
    if job.force_output_format and not job.is_audio_only:
        if job.format_has_audio and not job.audio_format_ids:
            cmd.extend(["--remux-video", job.preferred_output_format])
        else:
            cmd.extend(["--merge-output-format", job.preferred_output_format])

    # --- Audio-only format conversion ---
    if job.is_audio_only and job.force_audio_format:
        cmd.append("--extract-audio")
        if job.preferred_audio_format and job.preferred_audio_format != "best":
            cmd.extend(["--audio-format", job.preferred_audio_format])
            if job.preferred_audio_format == "aac":
                cmd.extend(["--remux-video", "aac"])

    # --- Audio normalization ---
    if job.audio_normalization and job.is_audio_only:
        if not job.force_audio_format or job.preferred_audio_format == "best":
            if "--extract-audio" not in cmd:
                cmd.append("--extract-audio")
            cmd.extend(["--audio-format", "mp3"])
        norm_args = "-af loudnorm=I=-16:LRA=11:TP=-1.5"
        if job.force_audio_format and job.preferred_audio_format in ("aac", "m4a"):
            norm_args = "-c:a aac " + norm_args
        elif job.force_audio_format and job.preferred_audio_format != "best":
            norm_args = f"-c:a {job.preferred_audio_format} " + norm_args
        cmd.extend(["--postprocessor-args", f"ExtractAudio:{norm_args}"])

    # --- Output template ---
    base_path = Path(job.path).as_posix()
    filename_part = job.filename_format or "%(title)s_%(resolution)s_[%(id)s].%(ext)s"
    # Each video gets its own folder named after the title so that related
    # files (video, .description, subtitles, .info.json) stay together.
    if job.is_playlist:
        output_template = f"{base_path}/%(playlist_title)s/%(title)s/{filename_part}"
    else:
        filename_part = re.sub(r'%\(playlist_index[^)]*\)[a-zA-Z0-9]*\s*(?:[-_]\s*)?', '', filename_part)
        output_template = f"{base_path}/%(title)s/{filename_part}"
    cmd.extend(["-o", output_template])
    cmd.append("--force-overwrites")

    # --- Playlist items ---
    if job.is_playlist and job.playlist_items:
        cmd.extend(["--playlist-items", job.playlist_items])

    # --- Subtitles ---
    if job.subtitle_langs:
        cmd.append("--write-subs")
        lang_codes: List[str] = []
        has_auto = False
        for sel in job.subtitle_langs:
            try:
                lang_codes.append(sel.split(" - ")[0])
                if "Auto-generated" in sel:
                    has_auto = True
            except Exception:
                pass
        if lang_codes:
            cmd.extend(["--sub-langs", ",".join(lang_codes)])
            if has_auto:
                cmd.append("--write-auto-subs")
            if job.merge_subs:
                cmd.append("--embed-subs")

    # --- SponsorBlock ---
    if job.enable_sponsorblock and job.sponsorblock_categories:
        cmd.append("--sponsorblock-remove")
        cmd.append(",".join(job.sponsorblock_categories))

    # --- Metadata options ---
    if job.save_description:
        cmd.append("--write-description")
    if job.embed_chapters:
        cmd.append("--embed-chapters")
    if job.embed_metadata:
        cmd.append("--embed-metadata")
    if job.embed_thumbnail:
        cmd.append("--embed-thumbnail")

    # --- Cookies ---
    has_cookies = False
    if job.cookie_file:
        cmd.extend(["--cookies", str(job.cookie_file)])
        has_cookies = True
    elif job.browser_cookies:
        cmd.extend(["--cookies-from-browser", job.browser_cookies])
        has_cookies = True
    if not has_cookies:
        cmd.extend(["--extractor-args", "youtube:player_client=web_embedded,default"])

    # --- Proxy ---
    if job.proxy_url:
        cmd.extend(["--proxy", job.proxy_url])
    if job.geo_proxy_url:
        cmd.extend(["--geo-verification-proxy", job.geo_proxy_url])

    # --- Rate limit ---
    if job.rate_limit:
        cmd.extend(["-r", job.rate_limit])

    # --- Download section ---
    if job.download_section:
        cmd.extend(["--download-sections", job.download_section])
        if job.force_keyframes:
            cmd.append("--force-keyframes-at-cuts")

    # --- URL ---
    if job.is_playlist:
        cmd.append("--ignore-errors")
        cmd.append("--no-abort-on-error")
    cmd.append(job.url)

    return cmd


# ---------------------------------------------------------------------------
# Partial-file cleanup (official: ytsage_downloader.py L125-158)
# ---------------------------------------------------------------------------

def _safe_delete_with_retry(file_path: Path, max_retries: int = 3, delay: float = 1.0) -> None:
    for attempt in range(max_retries):
        try:
            gc.collect()
            if file_path.exists():
                file_path.unlink(missing_ok=True)
            return
        except PermissionError:
            if attempt < max_retries - 1:
                time.sleep(delay)
                delay = min(delay * 1.5, 5.0)
            else:
                logger.warning(f"[WebUI] could not delete {file_path.name} (locked)")
        except Exception as e:
            logger.warning(f"[WebUI] delete error {file_path.name}: {e}")
            return


def cleanup_partial_files(path: str) -> None:
    """Official: cleanup_partial_files (L125-133): .part + .f<digits>.

    Recursive because each video now downloads into its own subfolder.
    """
    try:
        pattern = re.compile(r"\.f\d+\.")
        base = Path(path)
        if not base.exists():
            return
        for file_path in base.rglob("*"):
            if file_path.is_file() and (file_path.suffix == ".part" or pattern.search(file_path.name)):
                _safe_delete_with_retry(file_path)
    except Exception as e:
        logger.warning(f"[WebUI] partial cleanup error: {e}")


def _snapshot_subtitle_files(path: str) -> set:
    try:
        return {p for p in Path(path).rglob("*") if p.suffix in SUBTITLE_EXTENSIONS and p.is_file()}
    except Exception:
        return set()


def cleanup_merged_subtitle_files(path: str, before: set) -> None:
    """Official: cleanup_subtitle_files - delete newly created subtitle files
    after they have been embedded into the video."""
    try:
        now = {p for p in Path(path).rglob("*") if p.suffix in SUBTITLE_EXTENSIONS and p.is_file()}
        for p in now - before:
            _safe_delete_with_retry(p)
    except Exception as e:
        logger.warning(f"[WebUI] subtitle cleanup error: {e}")


# ---------------------------------------------------------------------------
# Download Manager
# ---------------------------------------------------------------------------

class DownloadManager:
    """
    Manages async downloads and broadcasts progress events on the shared bus.
    """

    def __init__(self) -> None:
        self._jobs: Dict[str, DownloadJob] = {}
        # FIFO of job_ids waiting for a free slot in the global concurrency
        # cap (max_concurrent_downloads setting).
        self._queue: List[str] = []

    # -- concurrency scheduling ---------------------------------------------

    @staticmethod
    def _max_concurrent() -> int:
        try:
            n = int(cfg_get("max_concurrent_downloads") or 1)
        except (TypeError, ValueError):
            n = 1
        return max(1, min(10, n))

    def _running_count(self) -> int:
        # 'pending' covers jobs whose task was just launched by _pump but has
        # not flipped to 'running' yet, so slots are reserved immediately.
        # Paused jobs keep their yt-dlp process alive (cooperative pause),
        # so they still occupy a concurrency slot.
        return sum(1 for j in self._jobs.values() if j.status in ("pending", "running", "paused"))

    def _pump(self) -> None:
        """Start queued jobs while slots are free."""
        limit = self._max_concurrent()
        while self._queue and self._running_count() < limit:
            job_id = self._queue.pop(0)
            job = self._jobs.get(job_id)
            if not job or job.status != "queued":
                continue
            job.status = "pending"
            asyncio.create_task(self._run_download(job))

    # -- introspection ------------------------------------------------------

    def active_count(self) -> int:
        return sum(1 for j in self._jobs.values() if j.status in ("queued", "pending", "running", "paused"))

    def is_updating_blocked(self) -> bool:
        return self.active_count() > 0

    def list_jobs(self) -> List[Dict[str, Any]]:
        return [self._job_to_dict(j) for j in self._jobs.values()]

    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        job = self._jobs.get(job_id)
        return self._job_to_dict(job) if job else None

    @staticmethod
    def _job_to_dict(job: DownloadJob) -> Dict[str, Any]:
        return {
            "job_id": job.job_id,
            "url": job.url,
            "path": job.path,
            "status": job.status,
            "progress": round(job.progress, 2),
            "current_filename": job.current_filename,
            "last_file_path": job.last_file_path,
            "speed": job.speed,
            "eta": job.eta,
            "stage": job.stage,
            "error": job.error,
            "error_key": job.error_key,
            "file_exists": job.file_exists,
            "is_audio_only": job.is_audio_only,
            "is_playlist": job.is_playlist,
            "title": job.title,
            "channel": job.channel,
            "duration": job.duration,
            "thumbnail_url": job.thumbnail_url,
            "history_id": job.history_id,
        }

    # -- lifecycle ----------------------------------------------------------

    async def start_download(self, job_data: Dict[str, Any]) -> str:
        """Create a new download job and enqueue it. Returns job_id.

        The job starts immediately when a slot is free under the global
        max_concurrent_downloads cap, otherwise it waits with status 'queued'.
        """
        job_id = uuid.uuid4().hex[:12]
        path = Path(job_data.get("path") or Path.home() / "Downloads")
        path.mkdir(parents=True, exist_ok=True)
        job_data["path"] = str(path)
        job_data["job_id"] = job_id

        job = DownloadJob(**{k: v for k, v in job_data.items() if k in DownloadJob.__dataclass_fields__})
        job.status = "queued"
        self._jobs[job_id] = job
        self._queue.append(job_id)

        job._subtitle_files_before = _snapshot_subtitle_files(job.path)

        bus.publish({"type": "job_created", "job": self._job_to_dict(job)})
        self._pump()
        return job_id

    async def cancel(self, job_id: str) -> bool:
        job = self._jobs.get(job_id)
        if not job:
            return False
        job._cancelled = True
        job._paused = False
        if job_id in self._queue:
            # Never started: drop it from the queue and finish it here.
            self._queue.remove(job_id)
            job.status = "cancelled"
            throttled.flush(job_id, {"type": "job_update", "job": self._job_to_dict(job)})
            bus.publish({
                "type": "job_finished",
                "job": self._job_to_dict(job),
                "success": False,
            })
            throttled.cleanup(job_id)
            return True
        if job._process and job._process.returncode is None:
            await self._terminate_process_tree(job._process)
            await asyncio.to_thread(cleanup_partial_files, job.path)
        job.status = "cancelled"
        throttled.flush(job_id, {"type": "job_update", "job": self._job_to_dict(job)})
        return True

    async def pause(self, job_id: str) -> bool:
        job = self._jobs.get(job_id)
        if not job or job.status != "running":
            return False
        job._paused = True
        job.status = "paused"
        throttled.flush(job_id, {"type": "job_update", "job": self._job_to_dict(job)})
        return True

    async def resume(self, job_id: str) -> bool:
        job = self._jobs.get(job_id)
        if not job or job.status != "paused":
            return False
        job._paused = False
        job.status = "running"
        throttled.flush(job_id, {"type": "job_update", "job": self._job_to_dict(job)})
        return True

    async def remove_job(self, job_id: str) -> bool:
        job = self._jobs.get(job_id)
        if not job:
            return False
        # Kill first if still active (prevents orphan processes)
        if job.status in ("queued", "pending", "running", "paused"):
            await self.cancel(job_id)
        if job_id in self._queue:
            self._queue.remove(job_id)
        throttled.cleanup(job_id)
        del self._jobs[job_id]
        bus.publish({"type": "job_removed", "job_id": job_id})
        self._pump()
        return True

    @staticmethod
    async def _terminate_process_tree(process: asyncio.subprocess.Process) -> None:
        """Official: _terminate_process_tree (ytsage_downloader.py L160-205)."""
        pid = process.pid
        try:
            if sys.platform == "win32":
                proc = await asyncio.create_subprocess_exec(
                    "taskkill", "/F", "/T", "/PID", str(pid),
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL,
                    creationflags=SUBPROCESS_CREATIONFLAGS,
                )
                await asyncio.wait_for(proc.wait(), timeout=10)
            else:
                import os
                import signal
                try:
                    os.killpg(os.getpgid(pid), signal.SIGTERM)
                    await asyncio.sleep(0.5)
                    os.killpg(os.getpgid(pid), signal.SIGKILL)
                except (ProcessLookupError, PermissionError):
                    pass
        except Exception as e:
            logger.warning(f"[WebUI] terminate tree failed: {e}")
            try:
                process.kill()
            except Exception:
                pass

    # -- execution ----------------------------------------------------------

    async def _run_download(self, job: DownloadJob) -> None:
        if job._cancelled:
            throttled.cleanup(job.job_id)
            return
        job.status = "running"
        cmd = build_ytdlp_command(job)
        cmd_str = " ".join(shlex.quote(a) for a in cmd)
        logger.info(f"[WebUI] Starting download: {cmd_str}")

        kwargs: Dict[str, Any] = {
            "stdout": asyncio.subprocess.PIPE,
            "stderr": asyncio.subprocess.STDOUT,
        }
        if sys.platform == "win32":
            kwargs["creationflags"] = SUBPROCESS_CREATIONFLAGS
        else:
            kwargs["start_new_session"] = True  # own process group for killpg

        job._process = await asyncio.create_subprocess_exec(*cmd, **kwargs)
        throttled.flush(job.job_id, {"type": "job_update", "job": self._job_to_dict(job)})

        try:
            assert job._process.stdout is not None
            while True:
                if job._cancelled:
                    break

                # Cooperative pause (official: process keeps running, only the
                # read loop suspends - ytsage_downloader.py L556-557)
                while job._paused and not job._cancelled:
                    await asyncio.sleep(0.2)
                if job._cancelled:
                    break

                try:
                    line = await asyncio.wait_for(job._process.stdout.readline(), timeout=1.0)
                except asyncio.TimeoutError:
                    continue
                if not line:
                    break
                text = decode_output(line).strip()
                if text:
                    await self._parse_line(job, text)
        except Exception as e:
            logger.error(f"[WebUI] Download loop error: {e}")
            job.error = str(e)
            job.status = "error"

        # Ensure process is gone
        if job._process and job._process.returncode is None:
            if job._cancelled:
                await self._terminate_process_tree(job._process)
            else:
                try:
                    await asyncio.wait_for(job._process.wait(), timeout=5)
                except asyncio.TimeoutError:
                    await self._terminate_process_tree(job._process)

        rc = job._process.returncode if job._process else -1

        if job._cancelled:
            job.status = "cancelled"
            await asyncio.to_thread(cleanup_partial_files, job.path)
        elif rc == 0 or (job.is_playlist and rc != 0 and job.current_filename is not None):
            job.status = "completed"
            job.progress = 100.0
            self._find_final_file(job)
            # Save thumbnail into the per-video folder (official: ytsage_gui_main.py L894-901)
            if job.save_thumbnail and job.thumbnail_url and job.last_file_path:
                try:
                    from .thumbnail_service import save_thumbnail_to_dir
                    await asyncio.to_thread(
                        save_thumbnail_to_dir,
                        job.thumbnail_url,
                        str(Path(job.last_file_path).parent),
                        job.title or "thumbnail",
                    )
                except Exception as e:
                    logger.warning(f"[WebUI] save thumbnail failed: {e}")
            if job.merge_subs and job.subtitle_langs:
                await asyncio.to_thread(cleanup_merged_subtitle_files, job.path, job._subtitle_files_before)
            await self._write_history(job)
        else:
            job.status = "error"
            if not job.error:
                job.error = f"yt-dlp exited with code {rc}"

        throttled.flush(job.job_id, {"type": "job_update", "job": self._job_to_dict(job)})
        bus.publish({
            "type": "job_finished",
            "job": self._job_to_dict(job),
            "success": job.status == "completed",
        })
        throttled.cleanup(job.job_id)
        # Slot released: start the next queued job, if any.
        self._pump()

    async def _write_history(self, job: DownloadJob) -> None:
        """Official: download_finished -> HistoryManager.add_entry (main.py L1004-1042)."""
        try:
            if not job.last_file_path or not Path(job.last_file_path).exists():
                return
            from . import history_service
            download_options = {
                "format_id": job.format_id,
                "subtitle_langs": job.subtitle_langs,
                "merge_subs": job.merge_subs,
                "enable_sponsorblock": job.enable_sponsorblock,
                "sponsorblock_categories": job.sponsorblock_categories,
                "save_description": job.save_description,
                "embed_chapters": job.embed_chapters,
                "embed_metadata": job.embed_metadata,
                "embed_thumbnail": job.embed_thumbnail,
                "download_section": job.download_section,
                "force_keyframes": job.force_keyframes,
            }
            hid = await history_service.add_entry(
                title=job.title or (Path(job.last_file_path).stem),
                url=job.url,
                thumbnail_url=job.thumbnail_url,
                file_path=str(job.last_file_path),
                format_id=job.format_id,
                is_audio_only=job.is_audio_only,
                resolution=job.resolution or "",
                channel=job.channel,
                duration=job.duration,
                download_options=download_options,
            )
            job.history_id = hid or None
        except Exception as e:
            logger.error(f"[WebUI] history write failed: {e}")

    def _find_final_file(self, job: DownloadJob) -> None:
        """Find the most recent downloaded file in the output directory."""
        try:
            path = Path(job.path)
            candidates: List[Path] = []
            for ext in MEDIA_EXTENSIONS:
                candidates.extend(path.rglob(f"*{ext}"))
            if candidates:
                most_recent = max(candidates, key=lambda p: p.stat().st_mtime)
                if time.time() - most_recent.stat().st_mtime < 120:
                    job.last_file_path = str(most_recent)
                    if not job.current_filename:
                        job.current_filename = most_recent.name
        except Exception as e:
            logger.debug(f"[WebUI] Final file search: {e}")

    # -- output parsing (official: _parse_output_line L667-886) -------------

    async def _parse_line(self, job: DownloadJob, line: str) -> None:
        now = time.time()
        dirty = False

        # Error capture -> friendly i18n key
        if "ERROR:" in line:
            from .url_utils import parse_yt_dlp_error_key
            key, params = parse_yt_dlp_error_key(line)
            if not job.error:
                job.error = line.split("ERROR:", 1)[1].strip()
                job.error_key = key
            dirty = True

        # Already downloaded (file_exists)
        if "has already been downloaded" in line:
            job.file_exists = True
            m = re.search(r"has already been downloaded", line)
            dest = re.search(r"\[download\]\s+(.*?)\s+has already", line)
            if dest:
                job.last_file_path = dest.group(1).strip()
                job.current_filename = Path(job.last_file_path).name
            dirty = True

        # Destination filename
        dest_match = re.search(r"^\[download\] Destination:\s*(.*)", line)
        if dest_match:
            filepath = dest_match.group(1).strip()
            job.current_filename = Path(filepath).name
            job.last_file_path = filepath
            dirty = True

        # Merging
        merger_match = re.search(r'Merging formats into "(.*?)"', line)
        if merger_match:
            job.last_file_path = merger_match.group(1)
            job.current_filename = Path(merger_match.group(1)).name
            job.stage = "merging"
            job.progress = 95.0
            dirty = True
        elif "SponsorBlock" in line and "Removing" in line:
            job.stage = "sponsorblock"
            job.progress = 97.0
            dirty = True
        elif "Deleting original file" in line:
            job.stage = "cleanup"
            job.progress = 98.0
            dirty = True
        elif "Finished downloading" in line:
            job.stage = "finished"
            job.progress = 100.0
            dirty = True

        # Progress % (robust: optional decimals)
        pct_match = re.search(r"(\d{1,3}(?:\.\d+)?)%", line)
        if pct_match and "[Merger]" not in line:
            try:
                pct = float(pct_match.group(1))
                if 0 <= pct <= 100:
                    job.progress = pct
                    dirty = True
            except ValueError:
                pass

        # Speed / ETA (robust: integer speeds, hour ETAs, N/A)
        if "[download]" in line.lower() and "%" in line:
            speed_m = re.search(r"at\s+([\d.]+(?:\.\d+)?\s*[KMG]?i?B/s|N/A)", line)
            eta_m = re.search(r"ETA\s+(\d{1,2}:\d{2}(?::\d{2})?|Unknown ETA|N/A)", line)
            if speed_m:
                job.speed = speed_m.group(1).replace(" ", "")
            if eta_m:
                job.eta = eta_m.group(1)
            dirty = True

        # Downloading subtitle/audio/video labels for stage
        if "[Subs]" in line or "Writing video subtitles" in line:
            job.stage = "subtitles"
        elif "[ExtractAudio]" in line:
            job.stage = "audio_convert"

        if dirty:
            throttled.publish(
                job.job_id,
                {"type": "job_update", "job": self._job_to_dict(job)},
                now,
            )


# ---------------------------------------------------------------------------
# Global singleton
# ---------------------------------------------------------------------------

download_manager = DownloadManager()
