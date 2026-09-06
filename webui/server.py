"""
YTSage Web UI - FastAPI Server
==============================
REST API + WebSocket for controlling YTSage downloads from a browser.

Run: python -m webui.server
     or: uvicorn webui.server:app --host 0.0.0.0 --port 8765

IMPORTANT: This file NEVER modifies official ytsage code.
All official-package access goes through webui.official_bridge.
"""

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import Depends, FastAPI, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from . import analysis_service, cookie_store, history_service, playlist_export, system_service, updater_service
from .auth import create_token, set_password, verify_password, verify_token
from .command_service import command_service
from .download_manager import download_manager
from .event_bus import bus
from .official_bridge import (
    APP_LOG_DIR,
    APP_VERSION,
    HAS_CONFIG,
    HAS_HISTORY,
    LANGUAGES_DIR,
    SOUND_PATH,
    USER_HOME_DIR,
    cfg_get,
    cfg_set,
)
from .schemas import (
    AnalyzeRequest,
    CommandRunRequest,
    CookieApplyRequest,
    DownloadRequest,
    LoginRequest,
    OpenFolderRequest,
    PasswordChangeRequest,
    PlaylistExportRequest,
    RevealRequest,
    YtdlpAutoUpdateRequest,
    YtdlpChannelRequest,
)
from .settings_service import build_download_defaults, get_all_settings, update_settings
from .thumbnail_service import fetch_thumbnail
from .url_utils import validate_video_url
from .yt_dlp_finder import get_yt_dlp_path

# Standard logging (no loguru dependency)
logger = logging.getLogger("ytsage.webui")
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

# Updater needs to know about active downloads (mutual exclusion)
updater_service.set_active_jobs_provider(download_manager.active_count)

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

app = FastAPI(
    title="YTSage Web UI",
    version="1.0.0",
    description="Web control interface for YTSage YouTube downloader",
)

# Dev-only CORS (Vite on 5173). Production serves SPA same-origin.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme)):
    """Validate bearer token. Returns payload dict or raises 401."""
    if credentials is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    payload = verify_token(credentials.credentials)
    if payload is None:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return payload


def _ensure_not_updating() -> None:
    """Official blocks analyze/download while yt-dlp is updating."""
    if updater_service.updating_ytdlp:
        raise HTTPException(status_code=409, detail="update.updating")


# ---------------------------------------------------------------------------
# Auth routes
# ---------------------------------------------------------------------------

@app.post("/api/auth/login")
async def login(req: LoginRequest):
    if verify_password(req.password):
        return {"token": create_token(), "expires_in": 7 * 24 * 3600}
    raise HTTPException(status_code=401, detail="Invalid password")


@app.get("/api/auth/verify")
async def verify(auth: dict = Depends(get_current_user)):
    return {"valid": True}


@app.post("/api/auth/change-password")
async def change_password(req: PasswordChangeRequest, auth: dict = Depends(get_current_user)):
    if not verify_password(req.current_password):
        raise HTTPException(status_code=401, detail="Current password incorrect")
    if len(req.new_password) < 4:
        raise HTTPException(status_code=400, detail="New password too short (min 4 chars)")
    set_password(req.new_password)
    return {"ok": True}


# ---------------------------------------------------------------------------
# Analysis / download routes
# ---------------------------------------------------------------------------

@app.post("/api/analyze")
async def analyze(req: AnalyzeRequest, auth: dict = Depends(get_current_user)):
    """Analyze a URL. Config defaults (proxy/cookies) injected like official GUI."""
    _ensure_not_updating()
    generic = cfg_get("generic_mode")
    generic = True if generic is None else bool(generic)
    ok, err_key = validate_video_url(req.url, generic)
    if not ok:
        raise HTTPException(status_code=400, detail=err_key)

    defaults = await asyncio.to_thread(build_download_defaults)
    try:
        result = await analysis_service.analyze_url_async(
            url=req.url,
            cookie_file=req.cookie_file or defaults["cookie_file"],
            browser_cookies=req.browser_cookies or defaults["browser_cookies"],
            proxy_url=req.proxy_url or defaults["proxy_url"],
            geo_proxy_url=req.geo_proxy_url or defaults["geo_proxy_url"],
        )
        return result
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/analysis/{analysis_id}")
async def get_analysis(analysis_id: str, auth: dict = Depends(get_current_user)):
    result = await analysis_service.cache_get(analysis_id)
    if not result:
        raise HTTPException(status_code=404, detail="Analysis expired or not found")
    return result


@app.post("/api/download")
async def start_download(req: DownloadRequest, auth: dict = Depends(get_current_user)):
    """Start a new download. Returns job_id. Unset fields use config defaults."""
    _ensure_not_updating()
    defaults = await asyncio.to_thread(build_download_defaults)
    data = req.model_dump(exclude_none=True)
    # Only inject when the client omitted the field (None means "use config")
    for key in ("proxy_url", "geo_proxy_url", "rate_limit", "cookie_file",
                "browser_cookies", "filename_format"):
        if data.get(key) in (None, ""):
            data[key] = defaults[key]
    for key in ("force_output_format", "preferred_output_format", "force_audio_format",
                "preferred_audio_format", "audio_normalization", "concurrent_fragments"):
        if data.get(key) is None:
            data[key] = defaults[key]
    try:
        job_id = await download_manager.start_download(data)
        return {"job_id": job_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/jobs")
async def list_jobs(auth: dict = Depends(get_current_user)):
    return {"jobs": download_manager.list_jobs()}


@app.get("/api/jobs/{job_id}")
async def get_job(job_id: str, auth: dict = Depends(get_current_user)):
    job = download_manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@app.post("/api/jobs/{job_id}/cancel")
async def cancel_job(job_id: str, auth: dict = Depends(get_current_user)):
    if not await download_manager.cancel(job_id):
        raise HTTPException(status_code=404, detail="Job not found or cannot cancel")
    return {"ok": True}


@app.post("/api/jobs/{job_id}/pause")
async def pause_job(job_id: str, auth: dict = Depends(get_current_user)):
    if not await download_manager.pause(job_id):
        raise HTTPException(status_code=404, detail="Job not found or cannot pause")
    return {"ok": True}


@app.post("/api/jobs/{job_id}/resume")
async def resume_job(job_id: str, auth: dict = Depends(get_current_user)):
    if not await download_manager.resume(job_id):
        raise HTTPException(status_code=404, detail="Job not found or cannot resume")
    return {"ok": True}


@app.delete("/api/jobs/{job_id}")
async def remove_job(job_id: str, auth: dict = Depends(get_current_user)):
    if not await download_manager.remove_job(job_id):
        raise HTTPException(status_code=404, detail="Job not found")
    return {"ok": True}


# ---------------------------------------------------------------------------
# Settings routes
# ---------------------------------------------------------------------------

@app.get("/api/settings")
async def settings_get(auth: dict = Depends(get_current_user)):
    return await asyncio.to_thread(get_all_settings)


@app.post("/api/settings")
async def settings_update(data: Dict[str, Any], auth: dict = Depends(get_current_user)):
    try:
        return await asyncio.to_thread(update_settings, data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ---------------------------------------------------------------------------
# History routes (shared SQLite with desktop app)
# ---------------------------------------------------------------------------

@app.get("/api/history")
async def history_list(q: Optional[str] = Query(None), auth: dict = Depends(get_current_user)):
    if not HAS_HISTORY:
        return {"entries": [], "available": False}
    entries = await history_service.list_entries(q)
    return {"entries": entries, "available": True}


@app.get("/api/history/{entry_id}")
async def history_get(entry_id: str, auth: dict = Depends(get_current_user)):
    entry = await history_service.get_entry(entry_id)
    if not entry:
        raise HTTPException(status_code=404, detail="History entry not found")
    return entry


@app.delete("/api/history/{entry_id}")
async def history_delete(entry_id: str, auth: dict = Depends(get_current_user)):
    return {"ok": await history_service.remove_entry(entry_id)}


@app.delete("/api/history")
async def history_clear(auth: dict = Depends(get_current_user)):
    return {"removed": await history_service.clear_history()}


# ---------------------------------------------------------------------------
# Thumbnail / sound / playlist export
# ---------------------------------------------------------------------------

@app.get("/api/thumbnail")
async def thumbnail(url: str = Query(...)):
    """Public: <img> tags cannot send Authorization headers.
    Only proxies whitelisted image hosts, so no path exposure."""
    path = await asyncio.to_thread(fetch_thumbnail, url)
    if not path:
        raise HTTPException(status_code=404, detail="Thumbnail unavailable")
    return FileResponse(path, media_type="image/jpeg")


@app.get("/api/sound/notification")
async def notification_sound(auth: dict = Depends(get_current_user)):
    if not SOUND_PATH.exists():
        raise HTTPException(status_code=404, detail="Sound file not found")
    return FileResponse(str(SOUND_PATH), media_type="audio/mpeg")


@app.post("/api/playlist/export")
async def export_playlist(req: PlaylistExportRequest, auth: dict = Depends(get_current_user)):
    entries = req.entries
    if not entries and req.analysis_id:
        cached = await analysis_service.cache_get(req.analysis_id)
        if cached:
            entries = cached.get("playlist_entries")
    if not entries:
        raise HTTPException(status_code=400, detail="No playlist entries provided")
    name, content, mime = await asyncio.to_thread(
        playlist_export.export_playlist, entries, req.format, req.title or "playlist"
    )
    from urllib.parse import quote
    return Response(
        content=content,
        media_type=mime,
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(name)}"},
    )


# ---------------------------------------------------------------------------
# System routes
# ---------------------------------------------------------------------------

@app.get("/api/system/status")
async def system_status(auth: dict = Depends(get_current_user)):
    return await asyncio.to_thread(system_service.system_status)


@app.post("/api/system/reveal")
async def system_reveal(req: RevealRequest, auth: dict = Depends(get_current_user)):
    ok = await asyncio.to_thread(system_service.reveal_in_folder, req.path)
    if not ok:
        raise HTTPException(status_code=400, detail="File not found or path not allowed")
    return {"ok": True}


@app.post("/api/system/open-folder")
async def system_open_folder(req: OpenFolderRequest, auth: dict = Depends(get_current_user)):
    ok = await asyncio.to_thread(system_service.open_folder, req.path)
    if not ok:
        raise HTTPException(status_code=400, detail="Folder not found or path not allowed")
    return {"ok": True}


@app.post("/api/system/open-logs")
async def system_open_logs(auth: dict = Depends(get_current_user)):
    ok = await asyncio.to_thread(system_service.open_logs)
    if not ok:
        raise HTTPException(status_code=400, detail="Could not open logs folder")
    return {"ok": True}


# ---------------------------------------------------------------------------
# Cookies (CustomOptionsDialog parity)
# ---------------------------------------------------------------------------

@app.get("/api/cookies/status")
async def cookies_status(auth: dict = Depends(get_current_user)):
    active = bool(cfg_get("cookie_active"))
    source = cfg_get("cookie_source") or "browser"
    detail = None
    if active:
        if source == "file":
            detail = cfg_get("cookie_file_path")
        else:
            browser = cfg_get("cookie_browser") or "chrome"
            profile = cfg_get("cookie_browser_profile") or ""
            detail = f"{browser}:{profile}" if profile else browser
    return {"active": active, "source": source, "detail": detail}


@app.get("/api/cookies/content")
async def cookies_content(auth: dict = Depends(get_current_user)):
    """Return the saved cookie text (for prefilling the Tools page)."""
    return {"content": await asyncio.to_thread(cookie_store.load_cookie_content)}


@app.post("/api/cookies/apply")
async def cookies_apply(req: CookieApplyRequest, auth: dict = Depends(get_current_user)):
    if req.source == "file":
        content = (req.file_content or "").strip()
        if not content:
            raise HTTPException(status_code=400, detail="web.cookies_empty")
        if not cookie_store.validate_netscape(content):
            raise HTTPException(status_code=400, detail="web.cookies_invalid")
        path = await asyncio.to_thread(cookie_store.save_cookie_content, content)
        cfg_set("cookie_source", "file")
        cfg_set("cookie_file_path", str(path))
        cfg_set("last_used_cookie_file", str(path))
    else:
        browser = req.browser or "chrome"
        cfg_set("cookie_source", "browser")
        cfg_set("cookie_browser", browser)
        cfg_set("cookie_browser_profile", req.profile or "")
    cfg_set("cookie_remember", req.remember)
    cfg_set("cookie_active", True)
    return {"ok": True, "active": True}


@app.post("/api/cookies/clear")
async def cookies_clear(auth: dict = Depends(get_current_user)):
    cfg_set("cookie_active", False)
    await asyncio.to_thread(cookie_store.delete_cookie_file)
    return {"ok": True, "active": False}


# ---------------------------------------------------------------------------
# Custom command (CustomOptionsDialog parity)
# ---------------------------------------------------------------------------

@app.post("/api/command/run")
async def command_run(req: CommandRunRequest, auth: dict = Depends(get_current_user)):
    _ensure_not_updating()
    path = req.path or await asyncio.to_thread(system_service.get_download_path)
    exec_id = await command_service.run(req.command, req.url, path)
    return {"exec_id": exec_id}


@app.post("/api/command/{exec_id}/cancel")
async def command_cancel(exec_id: str, auth: dict = Depends(get_current_user)):
    ok = await command_service.cancel(exec_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Command not running")
    return {"ok": True}


# ---------------------------------------------------------------------------
# Updater (full parity with UpdaterTabWidget + update dialogs)
# ---------------------------------------------------------------------------

@app.get("/api/updater/state")
async def updater_state(auth: dict = Depends(get_current_user)):
    return await updater_service.state()


@app.post("/api/updater/ytdlp/check")
async def updater_ytdlp_check(auth: dict = Depends(get_current_user)):
    return await updater_service.ytdlp_check_async()


@app.post("/api/updater/ytdlp/update")
async def updater_ytdlp_update(auth: dict = Depends(get_current_user)):
    try:
        return await updater_service.ytdlp_update_async()
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e))


@app.post("/api/updater/ytdlp/channel")
async def updater_ytdlp_channel(req: YtdlpChannelRequest, auth: dict = Depends(get_current_user)):
    try:
        result = await asyncio.to_thread(updater_service.ytdlp_switch_channel, req.channel)
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e))
    if not result.get("success"):
        raise HTTPException(status_code=500, detail=result.get("error", "channel switch failed"))
    return result


@app.post("/api/updater/ytdlp/auto")
async def updater_ytdlp_auto(req: YtdlpAutoUpdateRequest, auth: dict = Depends(get_current_user)):
    cfg_set("auto_update_ytdlp", req.enabled)
    cfg_set("auto_update_frequency", req.frequency)
    return {"ok": True}


@app.post("/api/updater/ffmpeg/check")
async def updater_ffmpeg_check(auth: dict = Depends(get_current_user)):
    return await updater_service.ffmpeg_check_async()


@app.post("/api/updater/ffmpeg/install")
async def updater_ffmpeg_install(auth: dict = Depends(get_current_user)):
    return await updater_service.ffmpeg_install_async()


@app.post("/api/updater/deno/check")
async def updater_deno_check(auth: dict = Depends(get_current_user)):
    return await updater_service.deno_check_async()


@app.post("/api/updater/deno/update")
async def updater_deno_update(auth: dict = Depends(get_current_user)):
    return await updater_service.deno_upgrade_async()


@app.post("/api/updater/app/check")
async def updater_app_check(auth: dict = Depends(get_current_user)):
    return await updater_service.app_check_async()


# ---------------------------------------------------------------------------
# i18n (zh/en from official language files)
# ---------------------------------------------------------------------------

_LANG_CACHE: Dict[str, Any] = {}


@app.get("/api/i18n/{lang}")
async def i18n(lang: str):
    """Public: language files are needed by the login page before auth."""
    if lang not in ("zh", "en"):
        raise HTTPException(status_code=400, detail="Only zh/en supported")
    if lang in _LANG_CACHE:
        return _LANG_CACHE[lang]
    f = LANGUAGES_DIR / f"{lang}.json"
    if not f.exists():
        raise HTTPException(status_code=404, detail=f"Language file {lang}.json not found")
    try:
        data = json.loads(f.read_text(encoding="utf-8"))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    _LANG_CACHE[lang] = data
    return data


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@app.get("/api/health")
async def health():
    ytdlp_path = get_yt_dlp_path()
    ytdlp_version = "unknown"
    try:
        import subprocess
        result = subprocess.run([str(ytdlp_path), "--version"], capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            ytdlp_version = result.stdout.strip()
    except Exception as e:
        ytdlp_version = f"error: {e}"

    return {
        "status": "ok",
        "app_version": APP_VERSION,
        "ytdlp_path": str(ytdlp_path),
        "ytdlp_version": ytdlp_version,
        "official_available": HAS_CONFIG,
        "history_available": HAS_HISTORY,
    }


# ---------------------------------------------------------------------------
# WebSocket (token required)
# ---------------------------------------------------------------------------

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    """Real-time event stream (jobs, commands, updater). Token required."""
    token = ws.query_params.get("token")
    if not token or verify_token(token) is None:
        await ws.close(code=1008, reason="Authentication required")
        return

    await ws.accept()
    q = bus.subscribe()

    async def _pump() -> None:
        try:
            while True:
                event = await q.get()
                await ws.send_json(event)
        except Exception:
            pass

    pump = asyncio.create_task(_pump())
    try:
        async for _ in ws.iter_text():
            pass
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        pump.cancel()
        bus.unsubscribe(q)


# ---------------------------------------------------------------------------
# Static frontend serving
# ---------------------------------------------------------------------------

_CLIENT_DIST = Path(__file__).parent / "client" / "dist"


@app.get("/", include_in_schema=False)
async def serve_index():
    if _CLIENT_DIST.exists():
        return FileResponse(_CLIENT_DIST / "index.html")
    return JSONResponse(
        {"error": "Frontend not built. Run 'cd webui/client && npm run build' first."},
        status_code=503,
    )


@app.get("/{full_path:path}", include_in_schema=False)
async def serve_static(full_path: str):
    """Serve SPA files. Unknown /api/* paths return JSON 404, not index.html."""
    if full_path.startswith("api/"):
        return JSONResponse({"detail": "Not Found"}, status_code=404)

    if not _CLIENT_DIST.exists():
        raise HTTPException(status_code=503, detail="Frontend not built")

    target = (_CLIENT_DIST / full_path).resolve()
    # Prevent path traversal
    try:
        target.relative_to(_CLIENT_DIST.resolve())
    except ValueError:
        raise HTTPException(status_code=404)
    if target.is_file():
        return FileResponse(target)

    index = _CLIENT_DIST / "index.html"
    if index.exists():
        return FileResponse(index)

    raise HTTPException(status_code=404)


# ---------------------------------------------------------------------------
# Startup hooks
# ---------------------------------------------------------------------------

@app.on_event("startup")
async def startup_hooks():
    """Auto-update check in background (official: _perform_startup_checks)."""
    asyncio.create_task(_auto_update_hook())


async def _auto_update_hook():
    try:
        await asyncio.sleep(2)
        result = await updater_service.auto_update_if_due()
        if result:
            logger.info(f"[WebUI] yt-dlp auto-update result: {result}")
    except Exception as e:
        logger.warning(f"[WebUI] auto-update hook failed: {e}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    """Run the server directly: python -m webui.server"""
    import uvicorn
    host = os.environ.get("YTSAGE_WEBUI_HOST", "0.0.0.0")
    port = int(os.environ.get("YTSAGE_WEBUI_PORT", "8765"))
    logger.info(f"Starting YTSage Web UI on http://{host}:{port}")
    uvicorn.run("webui.server:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    main()
