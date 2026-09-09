"""
YTSage Sync - Engine
====================
The actual sync work: given a profile (and optionally specific targets),
pull the flat playlist (playlists / liked / channel / subscriptions),
apply dedup + exclude rules, then enqueue downloads via download_manager.
Final file existence is resolved after the job finishes (event-bus hook).

Folder layout (mirrors dysync):
  <profile.root_path>/<profile.name>/<kind>/<target.title>/<file>

Dedup (per dysync): one video_id present in several targets downloads only
once - the target with the highest priority (profile.dedup_priority) wins.
"""

import asyncio
import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ..analysis_service import _sync_run
from ..download_manager import download_manager
from ..event_bus import bus
from ..yt_dlp_finder import get_yt_dlp_path
from . import store

logger = logging.getLogger("ytsage.webui.sync")

_VIDEO_ID_RE = re.compile(r"[?&]v=([A-Za-z0-9_-]{11})")

# Default target URLs for cookie-only kinds (user does not paste a URL)
KIND_URLS = {
    "liked": "https://www.youtube.com/playlist?list=LL",
    "favorites": "https://www.youtube.com/playlist?list=FL",
    "subscriptions": "https://www.youtube.com/feed/subscriptions",
}


def _extract_video_id(url: Optional[str]) -> Optional[str]:
    if not url:
        return None
    m = _VIDEO_ID_RE.search(url)
    if m:
        return m.group(1)
    if "youtu.be/" in url:
        try:
            return url.split("youtu.be/")[1].split("?")[0][:11]
        except Exception:
            return None
    return None


def _build_auth_options(profile: Dict[str, Any]) -> List[str]:
    if profile.get("cookie_source") == "file" and profile.get("cookie_file_path"):
        return ["--cookies", str(profile["cookie_file_path"])]
    if profile.get("cookie_source") == "browser":
        b = profile.get("cookie_browser") or "chrome"
        p = profile.get("cookie_browser_profile") or ""
        return ["--cookies-from-browser", f"{b}:{p}" if p else b]
    if profile.get("cookie_source") == "global":
        # Reuse the app-wide cookie configured on the Tools page.
        try:
            from ..settings_service import get_active_cookie
            c = get_active_cookie()
            if c.get("cookie_file"):
                return ["--cookies", str(c["cookie_file"])]
            if c.get("browser_cookies"):
                return ["--cookies-from-browser", str(c["browser_cookies"])]
        except Exception:
            pass
    return ["--extractor-args", "youtube:player_client=web_embedded,default"]


def _target_url(t: Dict[str, Any]) -> str:
    return (t.get("url") or KIND_URLS.get(t.get("kind")) or "").strip()


def _list_entries(url: str, auth_opts: List[str], playlist_end: Optional[int]) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    """Flat playlist listing. Returns (entries, error)."""
    cmd = [get_yt_dlp_path(), "--dump-single-json", "--flat-playlist", "--no-warnings"]
    if playlist_end:
        cmd += ["--playlist-end", str(playlist_end)]
    cmd += auth_opts + [url]
    try:
        result = _sync_run(cmd, timeout=300)
    except Exception as e:
        return [], f"sync.error: {e}"
    if result.returncode != 0:
        return [], (result.stderr or "").strip() or "yt-dlp failed"
    lines = [l.strip() for l in (result.stdout or "").strip().split("\n") if l.strip()]
    if not lines:
        return [], "no data"
    try:
        info = json.loads(lines[0])
    except json.JSONDecodeError:
        return [], "parse failed"
    if info.get("_type") != "playlist":
        return [], "not a playlist"
    return [e for e in (info.get("entries") or []) if e], None


def _target_folder(profile: Dict[str, Any], target: Dict[str, Any]) -> Path:
    # Per-target save_path overrides the default <root>/<profile>/<kind>/<title>
    # layout (dysync: each follow / collection can pick its own folder).
    override = (target.get("save_path") or "").strip()
    if override:
        return Path(override)
    root = Path(profile.get("root_path") or "")
    name = (profile.get("name") or "sync").strip()
    kind = target.get("kind") or "playlist"
    title = target.get("folder") or target.get("title") or kind
    return root / name / kind / str(title)


def _thumb_url(video_id: str) -> str:
    """Flat-playlist entries carry no reliable top-level thumbnail, so derive
    it from the id (matches the project's known proxy whitelist)."""
    return f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"


def _format_selector(resolution: str) -> str:
    """Build a codec-priority format string honoring the global codec_priority
    setting (av01 > vp09 > avc1 by default), mirroring the Batch page chain."""
    try:
        from ..settings_service import get_all_settings as global_settings
        gs = global_settings()
        order = gs.get("codec_priority") or ["av01", "vp09", "avc1"]
    except Exception:
        order = ["av01", "vp09", "avc1"]
    order = [c for c in ("av01", "vp09", "avc1") if c in order] + \
            [c for c in order if c not in ("av01", "vp09", "avc1")]
    h = f"[height<={int(resolution)}]" if resolution and resolution.isdigit() else ""
    parts = [f"bv*[vcodec^={c}]{h}+ba/b*[vcodec^={c}]{h}" for c in order]
    parts.append("bv*+ba/b")
    return "/".join(parts)


def _find_existing_file(profile: Dict[str, Any], video_id: str) -> Optional[str]:
    """Search all profile folders for an already-downloaded file of this id."""
    seen: set = set()
    root = (Path(profile.get("root_path") or "") / (profile.get("name") or "sync")).resolve()
    try:
        if not root.exists():
            return None
        for cand in root.rglob("*"):
            if cand.is_file() and f"[{video_id}]" in cand.stem:
                return str(cand)
    except Exception:
        pass
    return None


_KIND_RANK_DEFAULT = ("liked", "favorites", "playlist", "channel", "subscriptions")


class SyncEngine:
    def __init__(self) -> None:
        self._running: Dict[int, bool] = {}
        self._subscribed = False

    # -- event hook: finalize record when a queued download finishes --------

    def ensure_subscribe(self) -> None:
        if self._subscribed:
            return
        self._subscribed = True
        loop = asyncio.get_event_loop()

        async def _listen():
            q = bus.subscribe()
            try:
                while True:
                    ev = await q.get()
                    if ev.get("type") == "job_finished" and ev.get("job"):
                        self._finalize_job(ev["job"])
            except Exception:
                pass
            finally:
                bus.unsubscribe(q)

        loop.create_task(_listen())

    def _finalize_job(self, job: Dict[str, Any]) -> None:
        video_id = _extract_video_id(job.get("url"))
        if not video_id:
            return
        rec = store.get_record(video_id)
        if not rec:
            return
        ok = job.get("status") == "completed"
        store.upsert_record({
            "video_id": video_id,
            "video_title": job.get("title") or rec.get("video_title"),
            "channel": job.get("channel") or rec.get("channel"),
            "url": job.get("url") or rec.get("url"),
            "kind": rec.get("kind"),
            "profile_id": rec.get("profile_id"),
            "target_id": rec.get("target_id"),
            "status": "downloaded" if ok else "failed",
            "download_job_id": job.get("job_id"),
            # keep the thumbnail captured at queue time (upsert overwrites it)
            "thumbnail_url": rec.get("thumbnail_url") or job.get("thumbnail_url") or _thumb_url(video_id),
        })
        if ok and job.get("last_file_path"):
            size = 0
            try:
                from pathlib import Path as _P
                p = _P(job["last_file_path"])
                if p.is_file():
                    size = p.stat().st_size
            except Exception:
                pass
            store.update_record_file(video_id, job["last_file_path"], size)

            # Generate NFO if enabled
            settings = store.get_all_settings()
            if settings.get("nfo_enabled"):
                try:
                    from . import nfo_service
                    nfo_service.generate_nfo_for_video(video_id)
                except Exception as e:
                    logger.warning(f"[sync] NFO generation failed for {video_id}: {e}")

    # -- status --------------------------------------------------------------

    def is_running(self) -> bool:
        return any(self._running.values())

    def running_run_ids(self) -> List[int]:
        return [k for k, v in self._running.items() if v]

    # -- run ----------------------------------------------------------------

    async def run_profile(
        self,
        profile_id: int,
        target_ids: Optional[List[int]] = None,
        run_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        profile = store.get_profile(profile_id)
        if not profile:
            return {"ok": False, "error": "profile not found"}

        # sync_mode 'off' targets never run automatically (dysync per-follow
        # switch); an explicit target_ids list is a manual override and runs
        # regardless of mode. 'full_sync' overrides the "only recent" cap.
        targets = [t for t in store.list_targets(profile_id) if t.get("enabled")]
        if target_ids:
            ids = set(target_ids or [])
            targets = [t for t in targets if t["id"] in ids]
        else:
            targets = [t for t in targets if (t.get("sync_mode") or "sync") != "off"]
        if not targets:
            return {"ok": False, "error": "no enabled targets"}

        self.ensure_subscribe()
        vid = run_id or store.add_sync_run(profile_id, "mixed")
        self._running[vid] = True

        total = new_count = skipped = failed = 0
        try:
            # Dedup priority: a video seen in several targets downloads once,
            # under the target whose kind ranks highest.
            priority = json.loads(profile.get("dedup_priority") or '[]')
            priority = list(priority) + [k for k in _KIND_RANK_DEFAULT if k not in priority]
            kind_rank = {k: i for i, k in enumerate(priority)}
            targets.sort(key=lambda t: kind_rank.get(t.get("kind"), 99))

            settings = store.get_all_settings()
            auto_distinct = bool(settings.get("auto_distinct", True))

            # 1) collect flat entries per target
            target_entries: Dict[int, List[Dict[str, Any]]] = {}
            for t in targets:
                url = _target_url(t)
                if not url:
                    continue
                recent_limit = None
                if (t.get("sync_mode") or "sync") != "full_sync" and profile.get("only_recent"):
                    recent_limit = int(profile.get("recent_limit") or 20)
                entries, err = _list_entries(url, _build_auth_options(profile), recent_limit)
                if err:
                    logger.warning(f"[sync] target #{t['id']} ({t.get('title')}) failed: {err}")
                    failed += 1
                    continue
                target_entries[t["id"]] = entries
                store.update_target_last_sync(t["id"])

            # 2) dedup: video_id -> chosen target (first = highest priority)
            chosen: Dict[str, Tuple[Dict[str, Any], Dict[str, Any]]] = {}  # vid -> (target, entry)
            for t in targets:
                for e in target_entries.get(t["id"], []):
                    vid_id = e.get("id") or _extract_video_id(e.get("url"))
                    if not vid_id:
                        continue
                    if vid_id not in chosen:
                        chosen[vid_id] = (t, e)

            # 3) decide download / skip
            max_new = int(settings.get("max_sync_per_run") or 50)
            for vid_id, (t, entry) in chosen.items():
                total += 1
                if store.is_excluded(vid_id):
                    skipped += 1
                    continue
                rec = store.get_record(vid_id)
                if rec and rec.get("deleted_at"):
                    # soft-deleted: keep it hidden, don't re-download silently
                    skipped += 1
                    continue
                if rec and rec.get("status") in ("downloaded", "queued", "running"):
                    # dysync AutoDistinct: a higher-priority kind claims the
                    # video first; re-queue under the new target when the
                    # existing record came from a lower-priority kind.
                    if (auto_distinct and rec.get("status") == "downloaded"
                            and kind_rank.get(t.get("kind"), 99) < kind_rank.get(rec.get("kind"), 99)):
                        store.upsert_record({
                            "video_id": vid_id,
                            "video_title": entry.get("title") or rec.get("video_title"),
                            "channel": entry.get("channel") or entry.get("uploader") or rec.get("channel"),
                            "url": f"https://www.youtube.com/watch?v={vid_id}",
                            "kind": t.get("kind"), "profile_id": profile_id,
                            "target_id": t.get("id"), "status": "queued",
                            "thumbnail_url": _thumb_url(vid_id),
                        })
                        await self._enqueue_download(profile, t, vid_id)
                        new_count += 1
                    else:
                        skipped += 1
                    continue
                if _find_existing_file(profile, vid_id):
                    store.upsert_record({
                        "video_id": vid_id,
                        "video_title": entry.get("title"),
                        "channel": entry.get("channel") or entry.get("uploader"),
                        "url": f"https://www.youtube.com/watch?v={vid_id}",
                        "kind": t.get("kind"), "profile_id": profile_id,
                        "target_id": t.get("id"), "status": "downloaded",
                        "thumbnail_url": _thumb_url(vid_id),
                    })
                    skipped += 1
                    continue
                if new_count >= max_new:
                    skipped += 1
                    continue

                store.upsert_record({
                    "video_id": vid_id,
                    "video_title": entry.get("title"),
                    "channel": entry.get("channel") or entry.get("uploader"),
                    "url": f"https://www.youtube.com/watch?v={vid_id}",
                    "kind": t.get("kind"), "profile_id": profile_id,
                    "target_id": t.get("id"), "status": "queued",
                    "thumbnail_url": _thumb_url(vid_id),
                })
                await self._enqueue_download(profile, t, vid_id)
                new_count += 1

            store.finish_sync_run(
                vid, total, new_count, skipped, failed,
                f"targets={len(targets)} new={new_count} skip={skipped}",
            )
            
            # Archive daily statistics
            self._archive_daily_stats()
        except Exception as e:  # noqa: BLE001
            logger.exception(f"[sync] run #{vid} failed: {e}")
            store.finish_sync_run(vid, total, new_count, skipped, failed, f"error: {e}")
        finally:
            self._running.pop(vid, None)

        return {"ok": True, "run_id": vid, "total": total, "new": new_count,
                "skipped": skipped, "failed": failed}
    
    def _archive_daily_stats(self):
        """Archive daily statistics to sync_daily_stats table."""
        from datetime import datetime
        try:
            stats = store.get_statistics()
            date_str = datetime.now().strftime("%Y-%m-%d")
            store.upsert_daily_stats(date_str, {
                "total_videos": stats["total_videos"],
                "total_size": stats["total_size"],
                "liked_count": stats["liked_count"],
                "playlist_count": stats["playlist_count"],
                "channel_count": stats["channel_count"],
                "subs_count": stats["subs_count"],
            })
        except Exception as e:
            logger.warning(f"[sync] Failed to archive daily stats: {e}")

    async def _enqueue_download(
        self,
        profile: Dict[str, Any],
        target: Dict[str, Any],
        video_id: str,
        dest_folder: Optional[str] = None,
    ) -> None:
        if dest_folder:
            folder = Path(dest_folder)
        else:
            folder = _target_folder(profile, target)
        try:
            folder.mkdir(parents=True, exist_ok=True)
        except Exception:
            logger.warning(f"[sync] cannot mkdir {folder}")
        cookie_file = profile.get("cookie_file_path") if profile.get("cookie_source") == "file" else None
        browser_cookies = None
        if profile.get("cookie_source") == "browser" and profile.get("cookie_browser"):
            p = profile.get("cookie_browser_profile") or ""
            browser_cookies = f"{profile['cookie_browser']}:{p}" if p else profile["cookie_browser"]
        if profile.get("cookie_source") == "global" and not cookie_file and not browser_cookies:
            try:
                from ..settings_service import get_active_cookie
                c = get_active_cookie()
                cookie_file = c.get("cookie_file")
                browser_cookies = c.get("browser_cookies")
            except Exception:
                pass
        settings = store.get_all_settings()
        naming = settings.get("video_naming_template") or "%(title)s_[%(id)s].%(ext)s"
        await download_manager.start_download({
            "url": f"https://www.youtube.com/watch?v={video_id}",
            "path": str(folder),
            "format_id": _format_selector(str(settings.get("resolution") or "1080")),
            "resolution": "",
            "filename_format": naming,
            "concurrent_fragments": 1,
            "save_thumbnail": bool(settings.get("save_thumbnail", True)),
            "save_description": bool(settings.get("save_description", False)),
            "cookie_file": cookie_file,
            "browser_cookies": browser_cookies,
        })


engine = SyncEngine()