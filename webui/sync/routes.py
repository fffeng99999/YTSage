"""
YTSage Sync - API routes
========================
FastAPI router for the YT sync center, mounted under /api/sync in server.py.
"""

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field

from .. import history_service
from . import scheduler, store
from .engine import engine as sync_engine
from . import streaming, nfo_service, subscription_service

logger = logging.getLogger("ytsage.webui.sync")

router = APIRouter(prefix="/api/sync", tags=["sync"])

# Stream endpoints are consumed by <video> tags, which cannot send an
# Authorization header. This router is mounted in server.py with the
# query-token-permitting dependency instead of the strict bearer one.
stream_router = APIRouter(prefix="/api/sync", tags=["sync-stream"])

# Share links (dysync "分享"): HMAC-signed, time-limited, anonymous playback
# URLs. Mounted in server.py WITHOUT any auth dependency.
share_router = APIRouter(prefix="/api/sync", tags=["sync-share"])

_SHARE_TTL = 7 * 86400


def _share_secret() -> str:
    from ..auth import _get_secret
    return _get_secret()


def _make_share_token(video_id: str, ttl: int = _SHARE_TTL) -> str:
    import hashlib
    import hmac as _hmac
    exp = int(time.time()) + ttl
    msg = f"{video_id}:{exp}"
    sig = _hmac.new(_share_secret().encode(), msg.encode(), hashlib.sha256).hexdigest()[:24]
    return f"{video_id}.{exp}.{sig}"


def _verify_share_token(token: str) -> Optional[str]:
    import hashlib
    import hmac as _hmac
    try:
        video_id, exp, sig = token.rsplit(".", 2)
        if int(exp) < time.time():
            return None
        msg = f"{video_id}:{exp}"
        expected = _hmac.new(_share_secret().encode(), msg.encode(), hashlib.sha256).hexdigest()[:24]
        if _hmac.compare_digest(sig, expected):
            return video_id
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class CreateProfile(BaseModel):
    name: str
    cookie_source: str = "browser"
    cookie_browser: str = "chrome"
    cookie_browser_profile: str = ""
    cookie_file_path: Optional[str] = None
    root_path: str = ""
    only_recent: bool = False
    recent_limit: int = 20
    folder_by_title: bool = True
    enabled: bool = True
    dedup_priority: Optional[List[str]] = None


class UpdateProfile(BaseModel):
    name: Optional[str] = None
    cookie_source: Optional[str] = None
    cookie_browser: Optional[str] = None
    cookie_browser_profile: Optional[str] = None
    cookie_file_path: Optional[str] = None
    root_path: Optional[str] = None
    only_recent: Optional[bool] = None
    recent_limit: Optional[int] = None
    folder_by_title: Optional[bool] = None
    enabled: Optional[bool] = None
    dedup_priority: Optional[List[str]] = None


class CreateTarget(BaseModel):
    kind: str = Field(pattern=r"^(playlist|liked|channel|subscriptions|favorites)$")
    url: str = ""
    title: Optional[str] = None
    folder: Optional[str] = None
    enabled: bool = True


class UpdateTarget(BaseModel):
    kind: Optional[str] = None
    url: Optional[str] = None
    title: Optional[str] = None
    folder: Optional[str] = None
    enabled: Optional[bool] = None


class CreateSchedule(BaseModel):
    profile_id: int
    mode: str = Field(pattern=r"^(interval|daily|weekly)$")
    interval_min: int = 60
    hour: int = 0
    minute: int = 0
    weekday: int = 1
    enabled: bool = True


class UpdateSchedule(BaseModel):
    mode: Optional[str] = None
    interval_min: Optional[int] = None
    hour: Optional[int] = None
    minute: Optional[int] = None
    weekday: Optional[int] = None
    enabled: Optional[bool] = None


class RunRequest(BaseModel):
    profile_id: int
    target_ids: Optional[List[int]] = None


class ReSyncRequest(BaseModel):
    record_ids: List[int] = Field(default_factory=list)


class ExcludeRequest(BaseModel):
    video_id: str
    reason: str = "manual"


# ---------------------------------------------------------------------------
# Profiles
# ---------------------------------------------------------------------------

@router.get("/profiles")
async def list_profiles():
    return {"profiles": await asyncio.to_thread(store.list_profiles)}


@router.post("/profiles")
async def create_profile(req: CreateProfile):
    pid = await asyncio.to_thread(store.create_profile, req.model_dump())
    return {"id": pid}


@router.get("/profiles/{pid}")
async def get_profile(pid: int):
    p = await asyncio.to_thread(store.get_profile, pid)
    if not p:
        raise HTTPException(404, "Profile not found")
    return {"profile": p, "targets": await asyncio.to_thread(store.list_targets, pid)}


@router.put("/profiles/{pid}")
async def update_profile(pid: int, req: UpdateProfile):
    await asyncio.to_thread(store.update_profile, pid, {k: v for k, v in req.model_dump().items() if v is not None})
    return {"ok": True}


@router.delete("/profiles/{pid}")
async def delete_profile(pid: int):
    p = await asyncio.to_thread(store.get_profile, pid)
    if not p:
        raise HTTPException(404, "Profile not found")
    await asyncio.to_thread(store.delete_profile, pid)
    return {"ok": True}


# ---------------------------------------------------------------------------
# Targets
# ---------------------------------------------------------------------------

@router.post("/profiles/{pid}/targets")
async def create_target(pid: int, req: CreateTarget):
    tid = await asyncio.to_thread(store.create_target, pid, req.model_dump())
    return {"id": tid}


@router.put("/targets/{tid}")
async def update_target(tid: int, req: UpdateTarget):
    await asyncio.to_thread(store.update_target, tid, {k: v for k, v in req.model_dump().items() if v is not None})
    return {"ok": True}


@router.delete("/targets/{tid}")
async def delete_target(tid: int):
    await asyncio.to_thread(store.delete_target, tid)
    return {"ok": True}


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

@router.post("/run")
async def run_sync(req: RunRequest):
    if sync_engine.is_running():
        raise HTTPException(409, "A sync is already running")
    result = await sync_engine.run_profile(req.profile_id, req.target_ids)
    if not result.get("ok"):
        raise HTTPException(400, result.get("error", "run failed"))
    return result


@router.get("/runs/latest")
async def latest_runs():
    return {"runs": await asyncio.to_thread(store.list_sync_runs)}


# ---------------------------------------------------------------------------
# Records
# ---------------------------------------------------------------------------

@router.get("/records")
async def list_records(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=200),
    q: Optional[str] = None,
    status: Optional[str] = None,
    profile_id: Optional[int] = None,
    kind: Optional[str] = None,
    channel: Optional[str] = None,
    date_from: Optional[float] = None,
    date_to: Optional[float] = None,
):
    return await asyncio.to_thread(
        store.list_records, page, limit, q, status, profile_id,
        kind, channel, date_from, date_to,
    )


@router.get("/records/channels")
async def list_record_channels():
    """Distinct channel names for the records filter dropdown."""
    return {"channels": await asyncio.to_thread(store.list_channels)}


class PermanentDeleteRequest(BaseModel):
    ids: List[int]
    delete_files: bool = False
    also_exclude: bool = True


@router.post("/records/permanent-delete")
async def permanent_delete_records(req: PermanentDeleteRequest):
    """dysync 永久删除: hard-delete records, optionally remove files on disk,
    and blacklist the ids so future syncs never re-download them."""
    if not req.ids:
        raise HTTPException(400, "No records selected")
    if req.delete_files:
        for rid in req.ids:
            rec = await asyncio.to_thread(store.get_record_by_db_id, rid)
            fp = (rec or {}).get("file_path")
            if fp:
                try:
                    from pathlib import Path as _P
                    _P(fp).unlink(missing_ok=True)
                except Exception:
                    pass
    removed = await asyncio.to_thread(store.real_delete_records, req.ids, req.also_exclude)
    return {"removed": removed}


@router.post("/records/scan-missing")
async def scan_missing():
    """dysync removeInvalid: flag downloaded records whose file is gone."""
    missing = await asyncio.to_thread(store.scan_missing_records)
    return {"missing": missing}


class RemoveMissingRequest(BaseModel):
    delete_files: bool = False


@router.post("/records/remove-missing")
async def remove_missing(req: RemoveMissingRequest):
    removed = await asyncio.to_thread(store.remove_missing_records, req.delete_files)
    return {"removed": removed}


@router.delete("/records/{rid}")
async def delete_record(rid: int):
    await asyncio.to_thread(store.delete_record, rid)
    return {"ok": True}


@router.delete("/records")
async def delete_records(ids: List[int] = Query(...)):
    removed = await asyncio.to_thread(store.delete_records, ids)
    return {"removed": removed}


@router.post("/records/resync")
async def resync_records(req: ReSyncRequest):
    """Batch re-sync: requeue selected records via their record urls."""
    if not req.record_ids:
        raise HTTPException(400, "No records selected")
    if sync_engine.is_running():
        raise HTTPException(409, "A sync is already running")
    requeued = 0
    for rid in req.record_ids:
        rec = await asyncio.to_thread(store.get_record_by_db_id, rid)
        if not rec:
            continue
        profile = None
        if rec.get("profile_id"):
            profile = await asyncio.to_thread(store.get_profile, rec["profile_id"])
        target = None
        if rec.get("target_id"):
            target = await asyncio.to_thread(store.get_target, rec["target_id"])
        await sync_engine._enqueue_download(
            profile or {"name": "_manual", "cookie_source": "none"},
            target or {"kind": rec.get("kind"), "title": rec.get("video_title") or "resync", "folder": None},
            rec["video_id"],
        )
        requeued += 1
    return {"requeued": requeued}


# ---------------------------------------------------------------------------
# Excludes
# ---------------------------------------------------------------------------

@router.get("/excludes")
async def list_excludes():
    return {"excludes": await asyncio.to_thread(store.list_excludes)}


@router.post("/excludes")
async def add_exclude(req: ExcludeRequest):
    await asyncio.to_thread(store.exclude_video, req.video_id, req.reason)
    return {"ok": True}


@router.delete("/excludes/{video_id}")
async def remove_exclude(video_id: str):
    await asyncio.to_thread(store.remove_exclude, video_id)
    return {"ok": True}


# ---------------------------------------------------------------------------
# Schedules
# ---------------------------------------------------------------------------

@router.get("/schedules")
async def list_schedules():
    scheds = await asyncio.to_thread(store.list_schedules)
    return {"schedules": scheds}


@router.post("/schedules")
async def create_schedule(req: CreateSchedule):
    sid = await asyncio.to_thread(store.create_schedule, req.model_dump())
    await asyncio.to_thread(scheduler.refresh_next_runs)
    return {"id": sid}


@router.put("/schedules/{sid}")
async def update_schedule(sid: int, req: UpdateSchedule):
    await asyncio.to_thread(store.update_schedule, sid, {k: v for k, v in req.model_dump().items() if v is not None})
    # reset next_run so the scheduler recomputes it deterministically
    await asyncio.to_thread(store.set_schedule_next_run, sid, None)
    return {"ok": True}


@router.delete("/schedules/{sid}")
async def delete_schedule(sid: int):
    await asyncio.to_thread(store.delete_schedule, sid)
    return {"ok": True}


# ---------------------------------------------------------------------------
# Settings / logs / export-import / status
# ---------------------------------------------------------------------------

@router.get("/settings")
async def get_settings():
    return await asyncio.to_thread(store.get_all_settings)


@router.post("/settings")
async def set_settings(data: Dict[str, Any]):
    await asyncio.to_thread(store.set_settings, data)
    return {"ok": True}


@router.post("/logs/clear")
async def clear_logs():
    """Clear sync logs now (dysync: clear logs button)."""
    await asyncio.to_thread(store.clear_sync_runs)
    return {"ok": True}


@router.post("/logs/prune")
async def prune_logs():
    removed = await scheduler.prune_old_logs()
    return {"removed": removed}


@router.get("/export")
async def export():
    return await asyncio.to_thread(store.export_all)


@router.post("/import")
async def import_data(data: Dict[str, Any]):
    result = await asyncio.to_thread(store.import_all, data)
    return result


@router.get("/status")
async def sync_status():
    """Overview data for the sync landing page."""
    profiles = await asyncio.to_thread(store.list_profiles)
    records = await asyncio.to_thread(store.list_records, 1, 1)
    runs = await asyncio.to_thread(store.list_sync_runs, 5)
    # cookie validity heuristic: liked/subscriptions targets need cookies
    needs_cookie = 0
    for p in profiles:
        for t in await asyncio.to_thread(store.list_targets, p.get("id")):
            if t.get("kind") in ("liked", "favorites", "subscriptions"):
                needs_cookie += 1
    history_avail = bool(history_service._available())
    return {
        "profiles": len(profiles),
        "targets": sum(len(store.list_targets(p.get("id"))) for p in profiles),
        "record_count": records.get("total", 0),
        "recent_runs": runs,
        "running": sync_engine.is_running(),
        "needs_cookie_targets": needs_cookie,
        "history_available": history_avail,
    }


# ---------------------------------------------------------------------------
# Video Streaming (mounted with query-token auth in server.py)
# ---------------------------------------------------------------------------

@stream_router.get("/stream/{video_id}")
async def stream_video(video_id: str, request: Request):
    """Stream a video file with HTTP Range support."""
    range_header = request.headers.get("range")
    return await streaming.stream_video(video_id, range_header)


@stream_router.head("/stream/{video_id}")
async def stream_video_head(video_id: str):
    """Return HEAD response for a video."""
    return await streaming.get_video_head(video_id)


# ---------------------------------------------------------------------------
# Share links (anonymous, HMAC-signed; dysync "分享")
# ---------------------------------------------------------------------------

@router.post("/records/{video_id}/share")
async def create_share_link(video_id: str):
    """Create a time-limited anonymous playback link for a synced video."""
    settings = await asyncio.to_thread(store.get_all_settings)
    if not settings.get("share_link_enabled"):
        raise HTTPException(403, "Share links are disabled in sync settings")
    rec = await asyncio.to_thread(store.get_record, video_id)
    if not rec:
        raise HTTPException(404, "Record not found")
    token = _make_share_token(video_id)
    return {"token": token, "url": f"/api/sync/share/{token}", "ttl": _SHARE_TTL}


@share_router.get("/share/{token}")
async def share_play(token: str, request: Request):
    """Anonymous playback via a signed share token."""
    video_id = _verify_share_token(token)
    if not video_id:
        raise HTTPException(403, "Invalid or expired share link")
    range_header = request.headers.get("range")
    return await streaming.stream_video(video_id, range_header)


# ---------------------------------------------------------------------------
# NFO Generation
# ---------------------------------------------------------------------------

class NFOBatchRequest(BaseModel):
    video_ids: List[str]


@router.post("/nfo/generate/{video_id}")
async def generate_nfo(video_id: str):
    """Generate NFO file for a specific video."""
    success = await asyncio.to_thread(nfo_service.generate_nfo_for_video, video_id)
    if not success:
        raise HTTPException(400, "Failed to generate NFO")
    return {"ok": True}


@router.post("/nfo/generate-batch")
async def generate_nfo_batch(req: NFOBatchRequest):
    """Generate NFO files for multiple videos."""
    result = await asyncio.to_thread(nfo_service.generate_nfo_batch, req.video_ids)
    return result


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------

@router.get("/statistics")
async def get_statistics():
    """Get overall sync statistics."""
    return await asyncio.to_thread(store.get_statistics)


@router.get("/statistics/trend")
async def get_daily_stats(days: int = Query(7, ge=1, le=30)):
    """Get per-day newly synced counts by kind for the past N days."""
    return {"trend": await asyncio.to_thread(store.get_trend_stats, days)}


@router.get("/statistics/authors")
async def get_author_statistics(
    page: int = Query(1, ge=1),
    limit: int = Query(30, ge=1, le=100),
):
    """Get authors ranked by video count (paginated, dysync author grid)."""
    return await asyncio.to_thread(store.get_author_statistics, limit, (page - 1) * limit)


@router.delete("/statistics/authors/{channel}")
async def delete_author_records(channel: str):
    """Delete all synced records of one author (dysync: DeleteByAuthor)."""
    removed = await asyncio.to_thread(store.delete_records_by_author, channel)
    return {"removed": removed}


# ---------------------------------------------------------------------------
# Records Enhancements
# ---------------------------------------------------------------------------

class BatchDeleteRequest(BaseModel):
    ids: List[int]


class BatchRedownloadRequest(BaseModel):
    ids: List[int]


@router.post("/records/batch-delete")
async def batch_delete_records(req: BatchDeleteRequest):
    """Soft delete multiple records."""
    removed = await asyncio.to_thread(store.soft_delete_records, req.ids)
    return {"removed": removed}


@router.post("/records/{video_id}/restore")
async def restore_record(video_id: str):
    """Restore a soft-deleted record."""
    await asyncio.to_thread(store.restore_record, video_id)
    return {"ok": True}


@router.get("/records/deleted")
async def list_deleted_records(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=200),
):
    """List soft-deleted records."""
    return await asyncio.to_thread(store.list_deleted_records, page, limit)


@router.post("/records/batch-redownload")
async def batch_redownload_records(req: BatchRedownloadRequest):
    """Batch re-download multiple records."""
    if not req.ids:
        raise HTTPException(400, "No records selected")
    if sync_engine.is_running():
        raise HTTPException(409, "A sync is already running")

    requeued = 0
    for rid in req.ids:
        rec = await asyncio.to_thread(store.get_record_by_db_id, rid)
        if not rec:
            continue
        profile = None
        if rec.get("profile_id"):
            profile = await asyncio.to_thread(store.get_profile, rec["profile_id"])
        target = None
        if rec.get("target_id"):
            target = await asyncio.to_thread(store.get_target, rec["target_id"])
        # Prefer the original file's folder so re-downloads land in place.
        dest = None
        if rec.get("file_path"):
            from pathlib import Path as _P
            dest = str(_P(rec["file_path"]).parent)
        await sync_engine._enqueue_download(
            profile or {"name": "_manual", "cookie_source": "none"},
            target or {"kind": rec.get("kind"), "title": rec.get("video_title") or "redownload", "folder": None},
            rec["video_id"],
            dest_folder=dest,
        )
        requeued += 1
    return {"requeued": requeued}


# ---------------------------------------------------------------------------
# Subscription Management
# ---------------------------------------------------------------------------

class AddSubscriptionRequest(BaseModel):
    profile_id: int
    channel_url: str
    channel_name: Optional[str] = None


class UpdateSyncModeRequest(BaseModel):
    sync_mode: str = Field(pattern=r"^(off|sync|full_sync)$")


class UpdateSavePathRequest(BaseModel):
    save_path: str


@router.get("/subscriptions/{profile_id}")
async def list_subscriptions(profile_id: int):
    """List all channel subscriptions for a profile."""
    return await asyncio.to_thread(subscription_service.list_subscriptions, profile_id)


@router.post("/subscriptions/pull")
async def pull_subscriptions(profile_id: int = Query(...)):
    """Pull YouTube subscriptions list for a profile."""
    result = await asyncio.to_thread(subscription_service.pull_subscriptions, profile_id)
    if "error" in result:
        raise HTTPException(400, result["error"])
    return result


@router.post("/subscriptions/add")
async def add_subscription(req: AddSubscriptionRequest):
    """Manually add a channel subscription."""
    result = await asyncio.to_thread(
        subscription_service.add_subscription,
        req.profile_id, req.channel_url, req.channel_name
    )
    if "error" in result:
        raise HTTPException(400, result["error"])
    return result


@router.put("/targets/{tid}/sync-mode")
async def update_target_sync_mode(tid: int, req: UpdateSyncModeRequest):
    """Update sync mode for a subscription target."""
    success = await asyncio.to_thread(
        subscription_service.update_subscription_sync_mode, tid, req.sync_mode
    )
    if not success:
        raise HTTPException(400, "Invalid sync mode")
    return {"ok": True}


@router.put("/targets/{tid}/save-path")
async def update_target_save_path(tid: int, req: UpdateSavePathRequest):
    """Update save path for a subscription target."""
    success = await asyncio.to_thread(
        subscription_service.update_subscription_save_path, tid, req.save_path
    )
    if not success:
        raise HTTPException(400, "Failed to update save path")
    return {"ok": True}


class SaveSubscriptionsRequest(BaseModel):
    profile_id: int
    channels: List[Dict[str, Any]]
    sync_mode: str = Field(default="off", pattern=r"^(off|sync|full_sync)$")


@router.post("/subscriptions/save")
async def save_subscriptions(req: SaveSubscriptionsRequest):
    """Persist pulled subscription channels as channel targets (skip existing).

    New entries default to sync_mode='off' like dysync, so the user explicitly
    enables which channels to sync."""
    result = await asyncio.to_thread(
        subscription_service.save_subscriptions, req.profile_id, req.channels, req.sync_mode
    )
    return result


@router.get("/subscriptions/{profile_id}/stats")
async def get_subscription_stats(profile_id: int):
    """Get subscription statistics for a profile."""
    return await asyncio.to_thread(subscription_service.get_subscription_stats, profile_id)


# ---------------------------------------------------------------------------
# Cookie Management
# ---------------------------------------------------------------------------

_COOKIE_CACHE_KEY = "_cookie_check_cache"


def _cookie_cache() -> Dict[str, Any]:
    row = store._row("SELECT value FROM sync_settings WHERE key=?", (_COOKIE_CACHE_KEY,))
    if not row:
        return {}
    import json as _json
    try:
        return _json.loads(row["value"])
    except Exception:
        return {}


def _cookie_cache_set(profile_id: int, valid: Optional[bool], error: str = "") -> None:
    import json as _json
    cache = _cookie_cache()
    cache[str(profile_id)] = {"valid": valid, "checked_at": time.time(), "error": error}
    store._exec("INSERT OR REPLACE INTO sync_settings (key,value) VALUES (?,?)",
                (_COOKIE_CACHE_KEY, _json.dumps(cache)))


@router.get("/cookies/status")
async def get_cookie_status():
    """Per-profile cookie source + last validity check (dysync cookie 过期提醒)."""
    profiles = await asyncio.to_thread(store.list_profiles)
    cache = _cookie_cache()
    out = []
    for p in profiles:
        source = p.get("cookie_source")
        status = {
            "profile_id": p["id"],
            "profile_name": p["name"],
            "cookie_source": source,
            "cookie_browser": p.get("cookie_browser"),
            "cookie_file_path": p.get("cookie_file_path"),
            "has_cookie": False,
            "cookie_valid": None,
            "checked_at": None,
            "check_error": "",
        }
        if source == "file" and p.get("cookie_file_path"):
            from pathlib import Path
            status["has_cookie"] = Path(p["cookie_file_path"]).exists()
        elif source == "browser":
            status["has_cookie"] = True
        elif source == "global":
            status["has_cookie"] = True  # uses the app-wide cookie in Tools
        hit = cache.get(str(p["id"]))
        if hit:
            status["cookie_valid"] = hit.get("valid")
            status["checked_at"] = hit.get("checked_at")
            status["check_error"] = hit.get("error", "")
        out.append(status)
    return {"cookies": out}


@router.post("/cookies/check/{profile_id}")
async def check_cookie(profile_id: int):
    """Probe cookie validity by listing the account's Liked playlist (LL)."""
    from ..analysis_service import _sync_run
    from ..yt_dlp_finder import get_yt_dlp_path
    from .engine import _build_auth_options

    profile = await asyncio.to_thread(store.get_profile, profile_id)
    if not profile:
        raise HTTPException(404, "Profile not found")

    auth_opts = _build_auth_options(profile)
    cmd = [get_yt_dlp_path(), "--dump-single-json", "--no-warnings",
           "--playlist-items", "1", "--flat-playlist"]
    cmd += auth_opts + ["https://www.youtube.com/playlist?list=LL"]

    try:
        result = await asyncio.to_thread(_sync_run, cmd, 40)
        valid = result.returncode == 0
        err = "" if valid else (result.stderr or "").strip()[-400:]
        await asyncio.to_thread(_cookie_cache_set, profile_id, valid, err)
        return {"profile_id": profile_id, "cookie_valid": valid, "error": err,
                "checked_at": time.time()}
    except Exception as e:
        await asyncio.to_thread(_cookie_cache_set, profile_id, False, str(e))
        return {"profile_id": profile_id, "cookie_valid": False, "error": str(e),
                "checked_at": time.time()}