"""
Updater service for YTSage Web UI - full parity with the official desktop
updater (ytsage_dialogs_updater.py + ytsage_utils.py + ytsage_deno.py).

Components:
  - yt-dlp : check (PyPI), update (binary replace / -U), channel switch
             (stable/nightly), auto-update schedule (startup/daily/weekly)
  - ffmpeg : check (gyan.dev .ver), install (reuse official core when available)
  - deno   : check (GitHub), upgrade (deno upgrade)
  - app    : check (PyPI ytsage + GitHub changelog, beta via GitHub releases)

Progress/state is broadcast on the event bus as:
  {"type":"updater","component":"ytdlp|ffmpeg|deno|app","state":..., ...}

Mutual exclusion (Windows file locks): a global `updating_ytdlp` flag blocks
analyze/download (409) while updating; active downloads block binary updates.
"""

import asyncio
import logging
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional

import requests
from packaging import version as _pkg_version

from .event_bus import bus
from .official_bridge import (
    APP_BIN_DIR,
    DENO_APP_BIN_PATH,
    FFMPEG_ZIP_DOWNLOAD_URL,
    HAS_FFMPEG_CORE,
    OS_NAME,
    SUBPROCESS_CREATIONFLAGS,
    YTDLP_APP_BIN_PATH,
    cfg_get,
    cfg_set,
)
from .yt_dlp_finder import get_yt_dlp_path

logger = logging.getLogger("ytsage.webui")

if HAS_FFMPEG_CORE:
    from ytsage.core import ytsage_ffmpeg as _ffcore

# Global flags (mirrors official is_updating_ytdlp)
updating_ytdlp: bool = False
_active_jobs_provider = None  # set by server.py: callable() -> int


def set_active_jobs_provider(fn) -> None:
    global _active_jobs_provider
    _active_jobs_provider = fn


def _active_job_count() -> int:
    if _active_jobs_provider is None:
        return 0
    try:
        return int(_active_jobs_provider())
    except Exception:
        return 0


def _emit(component: str, **payload: Any) -> None:
    bus.publish({"type": "updater", "component": component, **payload})


def _run(cmd, timeout=120):
    kwargs = {"capture_output": True, "text": True, "timeout": timeout}
    if sys.platform == "win32":
        kwargs["creationflags"] = SUBPROCESS_CREATIONFLAGS
    return subprocess.run(cmd, **kwargs)


def _busy_guard() -> None:
    """Raise if active downloads would conflict with a binary update."""
    if _active_job_count() > 0:
        raise RuntimeError("downloads_active")


# ---------------------------------------------------------------------------
# yt-dlp
# ---------------------------------------------------------------------------

def ytdlp_current_version() -> str:
    path = get_yt_dlp_path()
    if not path or path == "yt-dlp":
        return "Not found"
    try:
        r = _run([path, "--version"], timeout=15)
        return r.stdout.strip() if r.returncode == 0 else "Error"
    except Exception as e:
        return f"Error: {e}"


def ytdlp_latest_version() -> Optional[str]:
    """Official: ytsage_utils.check_and_update_ytdlp_auto (L597)."""
    try:
        resp = requests.get("https://pypi.org/pypi/yt-dlp/json", timeout=10)
        resp.raise_for_status()
        return resp.json()["info"]["version"]
    except Exception as e:
        logger.warning(f"[WebUI] yt-dlp latest check failed: {e}")
        return None


def ytdlp_check() -> Dict[str, Any]:
    current = ytdlp_current_version()
    latest = ytdlp_latest_version()
    available = False
    try:
        available = bool(latest) and _pkg_version.parse(latest.replace("_", ".")) > _pkg_version.parse(current.replace("_", "."))
    except Exception:
        available = bool(latest) and latest != current
    return {"current": current, "latest": latest or "Unknown", "update_available": available}


async def ytdlp_check_async() -> Dict[str, Any]:
    return await asyncio.to_thread(ytdlp_check)


def ytdlp_update_sync(progress_cb=None) -> bool:
    """Official: ytsage_utils.update_yt_dlp (L432) + YTDLPUpdateDialog UpdateThread.

    App-managed binary -> direct download+replace; otherwise `yt-dlp -U`.
    """
    global updating_ytdlp
    _busy_guard()
    path = Path(get_yt_dlp_path())
    try:
        is_app_managed = False
        try:
            if path.exists() and YTDLP_APP_BIN_PATH.exists():
                is_app_managed = path.samefile(YTDLP_APP_BIN_PATH)
            elif str(path) == str(YTDLP_APP_BIN_PATH):
                is_app_managed = True
        except OSError:
            is_app_managed = False

        if progress_cb:
            progress_cb(20)

        from .official_bridge import YTDLP_DOWNLOAD_URL

        if is_app_managed:
            resp = requests.get(YTDLP_DOWNLOAD_URL, stream=True, timeout=120)
            if resp.status_code != 200:
                return False
            temp = f"{path}.new"
            with open(temp, "wb") as f:
                for chunk in resp.iter_content(8192):
                    f.write(chunk)
            if progress_cb:
                progress_cb(90)
            if OS_NAME != "Windows":
                os.chmod(temp, 0o755)
            if OS_NAME == "Windows" and path.exists():
                path.unlink(missing_ok=True)
            Path(temp).rename(path)
            if progress_cb:
                progress_cb(100)
            return True
        else:
            # Fallback: yt-dlp self-update
            r = _run([str(path), "-U"], timeout=300)
            if progress_cb:
                progress_cb(100)
            if OS_NAME != "Windows":
                try:
                    os.chmod(path, 0o755)
                except Exception:
                    pass
            return r.returncode == 0
    except Exception as e:
        logger.error(f"[WebUI] ytdlp_update error: {e}")
        return False


async def ytdlp_update_async() -> Dict[str, Any]:
    global updating_ytdlp
    if updating_ytdlp:
        raise RuntimeError("already_updating")
    updating_ytdlp = True
    _emit("ytdlp", state="updating", progress=10)
    loop = asyncio.get_running_loop()

    def cb(pct):
        loop.call_soon_threadsafe(_emit, "ytdlp", state="updating", progress=pct)

    try:
        ok = await asyncio.to_thread(ytdlp_update_sync, cb)
        _emit("ytdlp", state="done" if ok else "failed", progress=100 if ok else None)
        return {"success": ok}
    finally:
        updating_ytdlp = False


def ytdlp_switch_channel(new_channel: str) -> Dict[str, Any]:
    """Official: UpdaterTabWidget._on_channel_changed/switch_channel (L736-876)."""
    global updating_ytdlp
    _busy_guard()
    current_channel = cfg_get("ytdlp_channel") or "stable"
    if new_channel == current_channel:
        return {"success": True, "channel": new_channel, "unchanged": True}

    updating_ytdlp = True
    _emit("ytdlp", state="switching_channel", channel=new_channel)
    try:
        path = get_yt_dlp_path()
        update_target = new_channel
        if new_channel == "stable" and current_channel == "nightly":
            try:
                resp = requests.get("https://pypi.org/pypi/yt-dlp/json", timeout=10)
                resp.raise_for_status()
                tag = resp.json()["info"]["version"]
                parts = tag.split(".")
                if len(parts) == 3:
                    tag = f"{parts[0]}.{int(parts[1]):02d}.{int(parts[2]):02d}"
                update_target = f"stable@{tag}"
            except Exception:
                pass
        try:
            r = _run([path, "--update-to", update_target], timeout=180)
        except subprocess.TimeoutExpired:
            return {"success": False, "error": "Timeout", "reverted_to": current_channel}
        if r.returncode == 0:
            cfg_set("ytdlp_channel", new_channel)
            if OS_NAME != "Windows":
                try:
                    os.chmod(path, 0o755)
                except Exception:
                    pass
            _emit("ytdlp", state="channel_switched", channel=new_channel)
            return {"success": True, "channel": new_channel}
        err = (r.stderr or r.stdout or "Unknown error").strip()
        return {"success": False, "error": err, "reverted_to": current_channel}
    finally:
        updating_ytdlp = False


def should_check_for_auto_update() -> bool:
    """Official: ytsage_utils.should_check_for_auto_update (L552-579)."""
    if not cfg_get("auto_update_ytdlp"):
        return False
    frequency = cfg_get("auto_update_frequency") or "daily"
    last = cfg_get("last_update_check") or 0
    diff = time.time() - float(last)
    thresholds = {"startup": 3600, "daily": 86400, "weekly": 604800}
    return diff > thresholds.get(frequency, 86400)


async def auto_update_if_due() -> Optional[Dict[str, Any]]:
    """Official: check_and_update_ytdlp_auto (L582)."""
    if not await asyncio.to_thread(should_check_for_auto_update):
        return None
    if updating_ytdlp or _active_job_count() > 0:
        return None
    try:
        info = await ytdlp_check_async()
        if info["update_available"]:
            result = await ytdlp_update_async()
            cfg_set("last_update_check", time.time())
            return {"updated": result["success"], **info}
        cfg_set("last_update_check", time.time())
        return {"updated": False, **info}
    except Exception as e:
        logger.warning(f"[WebUI] auto-update skipped: {e}")
        return None


# ---------------------------------------------------------------------------
# FFmpeg
# ---------------------------------------------------------------------------

def ffmpeg_latest_version() -> Optional[str]:
    """Official: get_latest_ffmpeg_version (ytsage_dialogs_updater.py L48)."""
    url = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip.ver"
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        v = resp.text.strip()
        if re.match(r"^\d+\.\d+(\.\d+)?$", v):
            return v
    except Exception as e:
        logger.warning(f"[WebUI] ffmpeg latest check failed: {e}")
    return None


def ffmpeg_current_version() -> str:
    from .system_service import get_ffmpeg_version
    return get_ffmpeg_version()


def ffmpeg_check() -> Dict[str, Any]:
    current = ffmpeg_current_version()
    installed = current not in ("Not found",) and not current.startswith("Error")
    latest = ffmpeg_latest_version()
    available = False
    # current looks like "9.0.1-essentials_build-www.gyan.dev" -> compare only
    # the leading numeric version, otherwise every check reports an update.
    m = re.match(r"(\d+(?:\.\d+)*)", current or "")
    cur_v = m.group(1) if m else ""
    if installed and latest and cur_v:
        try:
            available = _pkg_version.parse(latest) > _pkg_version.parse(cur_v)
        except Exception:
            available = latest != cur_v
    return {"installed": installed, "current": current, "latest": latest or "Unknown", "update_available": available}


async def ffmpeg_check_async() -> Dict[str, Any]:
    return await asyncio.to_thread(ffmpeg_check)


def ffmpeg_install_sync(progress_cb=None) -> bool:
    """Reuse official auto_install_ffmpeg when available (needs requests, no Qt)."""
    _busy_guard()
    if HAS_FFMPEG_CORE and hasattr(_ffcore, "auto_install_ffmpeg"):
        def cb(msg):
            if progress_cb:
                progress_cb(str(msg))
        try:
            return bool(_ffcore.auto_install_ffmpeg(progress_callback=cb))
        except Exception as e:
            logger.error(f"[WebUI] ffmpeg install via official core failed: {e}")
            return False
    raise RuntimeError("ffmpeg_install_unavailable")


def _ffmpeg_pick_latest_bin(extract_dir: Path) -> Optional[Path]:
    """Newest ffmpeg-*-essentials_build/bin under extract_dir (version-aware sort).

    Official get_ffmpeg_install_path() sorts by NAME, which breaks for
    two-digit majors (ffmpeg-9 > ffmpeg-10). Parse versions properly here.
    """
    best = None
    best_key = None
    for item in extract_dir.glob("ffmpeg-*-essentials_build"):
        if not item.is_dir():
            continue
        bin_dir = item / "bin"
        if not (bin_dir / "ffmpeg.exe").exists():
            continue
        m = re.search(r"ffmpeg-(\d+)\.(\d+)(?:\.(\d+))?", item.name)
        key = tuple(int(x or 0) for x in (m.groups() if m else (0, 0, 0)))
        if best_key is None or key > best_key:
            best, best_key = bin_dir, key
    return best


def _ffmpeg_persist_path_windows(bin_dir: Path) -> None:
    """Persist the new ffmpeg bin on the USER PATH (registry), NOT via setx.

    `setx PATH <merged>` silently truncates to 1024 chars and would flatten
    system+user PATH into the user key - both are environment corruption.
    Writing HKCU\\Environment\\Path keeps the two scopes separate and has no
    length limit. A WM_SETTINGCHANGE broadcast wakes up Explorer shells.
    """
    try:
        import winreg
    except ImportError:
        logger.warning("[WebUI] winreg unavailable, PATH not persisted")
        return
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment", 0, winreg.KEY_READ | winreg.KEY_WRITE) as key:
            try:
                user_path, _ = winreg.QueryValueEx(key, "Path")
            except FileNotFoundError:
                user_path = ""
        entries = [p for p in str(user_path).split(os.pathsep) if p.strip()]
        cleaned = [p for p in entries if "ffmpeg" not in p.lower()]
        cleaned.insert(0, str(bin_dir))
        new_user_path = os.pathsep.join(cleaned)
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment", 0, winreg.KEY_WRITE) as key:
            winreg.SetValueEx(key, "Path", 0, winreg.REG_EXPAND_SZ, new_user_path)
        # Broadcast so already-running Explorer picks it up
        try:
            import ctypes
            HWND_BROADCAST = 0xFFFF
            WM_SETTINGCHANGE = 0x1A
            SMTO_ABORTIFHUNG = 0x0002
            ctypes.windll.user32.SendMessageTimeoutW(
                HWND_BROADCAST, WM_SETTINGCHANGE, 0, "Environment",
                SMTO_ABORTIFHUNG, 5000,
            )
        except Exception:
            pass
        logger.info(f"[WebUI] User PATH updated with {bin_dir}")
    except Exception as e:
        logger.warning(f"[WebUI] failed to persist user PATH: {e}")


def ffmpeg_update_sync(progress_cb=None) -> bool:
    """Force-update FFmpeg on Windows (official installer no-ops when installed).

    Downloads the latest essentials build zip from gyan.dev, extracts it next
    to the existing install, then puts the NEW bin directory first on PATH
    (session + persistent via setx, mirroring the official installer).
    """
    _busy_guard()
    if OS_NAME != "Windows":
        # Non-Windows: fall back to the official installer (brew/apt based)
        return ffmpeg_install_sync(progress_cb=progress_cb)

    import tempfile
    import zipfile

    def say(msg):
        if progress_cb:
            progress_cb(str(msg))

    try:
        extract_dir = Path(os.getenv("LOCALAPPDATA")) / "ffmpeg"
        extract_dir.mkdir(exist_ok=True)

        say("⬇ Downloading FFmpeg update (zip)...")
        temp = tempfile.NamedTemporaryFile(delete=False, suffix=".zip").name
        try:
            resp = requests.get(FFMPEG_ZIP_DOWNLOAD_URL, stream=True, timeout=120)
            resp.raise_for_status()
            total = int(resp.headers.get("content-length") or 0)
            done = 0
            last_pct = -10
            with open(temp, "wb") as f:
                for chunk in resp.iter_content(65536):
                    f.write(chunk)
                    done += len(chunk)
                    if total:
                        pct = int(done * 100 / total)
                        if pct - last_pct >= 10:
                            say(f"  {pct}%")
                            last_pct = pct
            if HAS_FFMPEG_CORE and hasattr(_ffcore, "verify_sha256"):
                try:
                    say("🔐 Verifying download integrity...")
                    if not _ffcore.verify_sha256(temp, _ffcore.FFMPEG_ZIP_SHA256_URL):
                        say("⚠️ SHA-256 verification failed, proceeding anyway...")
                except Exception:
                    pass
            say("⚙ Extracting FFmpeg...")
            with zipfile.ZipFile(temp, "r") as zf:
                zf.extractall(extract_dir)
        finally:
            try:
                Path(temp).unlink(missing_ok=True)
            except Exception:
                pass

        bin_dir = _ffmpeg_pick_latest_bin(extract_dir)
        if not bin_dir:
            say("❌ Could not locate extracted FFmpeg bin directory")
            return False

        say("🔧 Updating PATH...")
        _ffmpeg_persist_path_windows(bin_dir)
        # Session PATH: prepend the new bin so this process (and the yt-dlp
        # subprocesses it spawns) immediately use the updated ffmpeg.
        parts = os.environ.get("PATH", "").split(os.pathsep)
        cleaned = [p for p in parts if "ffmpeg" not in p.lower()]
        cleaned.insert(0, str(bin_dir))
        os.environ["PATH"] = os.pathsep.join(cleaned)

        say("✅ Verifying update...")
        r = _run([str(bin_dir / "ffmpeg.exe"), "-version"], timeout=15)
        ok = r.returncode == 0
        say("✅ FFmpeg update completed!" if ok else "❌ FFmpeg update verification failed")
        return ok
    except Exception as e:
        logger.error(f"[WebUI] ffmpeg update failed: {e}")
        say(f"❌ FFmpeg update failed: {e}")
        return False


async def ffmpeg_install_async() -> Dict[str, Any]:
    """Install when missing, force-update when a newer build is available."""
    info = await ffmpeg_check_async()
    is_update = bool(info.get("installed") and info.get("update_available"))
    if info.get("installed") and not is_update:
        return {"success": True, "noop": True, "updated": False}

    fn = ffmpeg_update_sync if is_update else ffmpeg_install_sync
    _emit("ffmpeg", state="installing", message="update start" if is_update else "start")
    loop = asyncio.get_running_loop()

    def cb(msg):
        loop.call_soon_threadsafe(_emit, "ffmpeg", state="installing", message=msg)

    try:
        ok = await asyncio.to_thread(fn, cb)
        _emit("ffmpeg", state="done" if ok else "failed", updated=is_update)
        return {"success": ok, "updated": is_update}
    except Exception as e:
        _emit("ffmpeg", state="failed", message=str(e))
        return {"success": False, "updated": is_update, "error": str(e)}


# ---------------------------------------------------------------------------
# Deno
# ---------------------------------------------------------------------------

def deno_latest_version() -> Optional[str]:
    """Official: get_latest_deno_version (ytsage_deno.py L614)."""
    try:
        resp = requests.get("https://api.github.com/repos/denoland/deno/releases/latest", timeout=10)
        resp.raise_for_status()
        tag = resp.json().get("tag_name", "")
        return tag[1:] if tag.startswith("v") else tag
    except Exception as e:
        logger.warning(f"[WebUI] deno latest check failed: {e}")
        return None


def deno_current_version() -> str:
    from .system_service import get_deno_version
    return get_deno_version()


def _cmp_tuple(s: str):
    m = re.search(r"(\d+\.\d+\.\d+)", s or "")
    v = m.group(1) if m else (s or "0")
    return tuple(int(p) for p in v.split(".") if p.isdigit())


def deno_check() -> Dict[str, Any]:
    current = deno_current_version()
    installed = current not in ("Not found",) and not current.startswith("Error")
    latest = deno_latest_version()
    available = False
    if installed and latest:
        try:
            available = _cmp_tuple(latest) > _cmp_tuple(current)
        except Exception:
            available = False
    return {"installed": installed, "current": current, "latest": latest or "Unknown", "update_available": available}


async def deno_check_async() -> Dict[str, Any]:
    return await asyncio.to_thread(deno_check)


def deno_upgrade_sync(progress_cb=None) -> Dict[str, Any]:
    """Official: upgrade_deno (ytsage_deno.py L686-752)."""
    _busy_guard()
    if not DENO_APP_BIN_PATH.exists():
        return {"success": False, "error": f"Deno not found at {DENO_APP_BIN_PATH}"}
    proc = subprocess.Popen(
        [str(DENO_APP_BIN_PATH), "upgrade"],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding="utf-8", errors="replace", bufsize=1,
        creationflags=SUBPROCESS_CREATIONFLAGS if sys.platform == "win32" else 0,
    )
    out_lines = []
    while True:
        line = proc.stdout.readline()
        if not line and proc.poll() is not None:
            break
        if line:
            s = line.strip()
            if s:
                out_lines.append(s)
                if progress_cb:
                    progress_cb(s)
    rc = proc.poll()
    return {"success": rc == 0, "output": "\n".join(out_lines)}


async def deno_upgrade_async() -> Dict[str, Any]:
    _emit("deno", state="upgrading")
    loop = asyncio.get_running_loop()

    def cb(msg):
        loop.call_soon_threadsafe(_emit, "deno", state="upgrading", message=msg)

    try:
        result = await asyncio.to_thread(deno_upgrade_sync, cb)
        _emit("deno", state="done" if result["success"] else "failed")
        return result
    except Exception as e:
        _emit("deno", state="failed", message=str(e))
        return {"success": False, "error": str(e)}


# ---------------------------------------------------------------------------
# App self-update
# ---------------------------------------------------------------------------

def app_check() -> Dict[str, Any]:
    """Official: UpdateCheckThread (ytsage_gui_main.py). PyPI stable or GitHub beta."""
    from .official_bridge import APP_VERSION
    current = APP_VERSION
    beta = bool(cfg_get("check_beta_updates"))
    try:
        if beta:
            resp = requests.get("https://api.github.com/repos/oop7/YTSage/releases", timeout=10)
            resp.raise_for_status()
            releases = resp.json()
            latest = None
            url = ""
            notes = ""
            if releases:
                def _key(r):
                    tag = r.get("tag_name", "0")
                    return _cmp_tuple(tag.lstrip("v"))
                best = max(releases, key=_key)
                latest = best.get("tag_name", "").lstrip("v")
                url = best.get("html_url", "")
                notes = best.get("body", "")
        else:
            resp = requests.get("https://pypi.org/pypi/ytsage/json", timeout=10)
            resp.raise_for_status()
            latest = resp.json()["info"]["version"]
            url = "https://github.com/oop7/YTSage/releases"
            notes = ""
            try:
                gr = requests.get("https://api.github.com/repos/oop7/YTSage/releases/latest", timeout=10)
                if gr.status_code == 200:
                    notes = gr.json().get("body", "")
            except Exception:
                pass
        available = False
        try:
            available = _pkg_version.parse(latest) > _pkg_version.parse(current)
        except Exception:
            available = latest != current
        return {"current": current, "latest": latest, "update_available": available,
                "release_url": url, "changelog": notes, "beta": beta}
    except Exception as e:
        return {"current": current, "latest": "Unknown", "update_available": False, "error": str(e), "beta": beta}


async def app_check_async() -> Dict[str, Any]:
    return await asyncio.to_thread(app_check)


# ---------------------------------------------------------------------------
# Aggregate state
# ---------------------------------------------------------------------------

async def state() -> Dict[str, Any]:
    ytdlp = await asyncio.to_thread(ytdlp_check)
    ffmpeg = await asyncio.to_thread(ffmpeg_check)
    deno = await asyncio.to_thread(deno_check)
    return {
        "updating_ytdlp": updating_ytdlp,
        "ytdlp": {**ytdlp, "channel": cfg_get("ytdlp_channel") or "stable"},
        "ffmpeg": ffmpeg,
        "deno": deno,
        "auto_update": {
            "enabled": bool(cfg_get("auto_update_ytdlp")),
            "frequency": cfg_get("auto_update_frequency") or "daily",
            "last_check": cfg_get("last_update_check") or 0,
        },
        "app_updates": {
            "check_app_updates": not (cfg_get("check_app_updates") is False),
            "check_beta_updates": bool(cfg_get("check_beta_updates")),
        },
    }
