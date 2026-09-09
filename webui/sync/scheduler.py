"""
YTSage Sync - Scheduler
=======================
Background asyncio loop that runs periodic syncs (interval / daily / weekly)
and prunes old sync-run logs + app log files (log retention).

Schedule semantics:
  - interval: every N minutes (min 10)
  - daily:    every day at HH:MM
  - weekly:   every `weekday` (1=Mon..7=Sun) at HH:MM
"""

import asyncio
import logging
import time
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from ..official_bridge import APP_LOG_DIR
from . import store
from .engine import engine

logger = logging.getLogger("ytsage.webui.sync")

CHECK_EVERY = 30  # seconds
_LAST_CLEAN_KEY = "_last_log_clean_date"


def _next_run(s: Dict[str, Any], now_ts: float) -> float:
    n = datetime.fromtimestamp(now_ts)
    mode = s.get("mode")
    hh, mm = int(s.get("hour") or 0), int(s.get("minute") or 0)
    if mode == "interval":
        mins = max(10, int(s.get("interval_min") or 60))
        last = s.get("last_run")
        if not last:
            return now_ts + 60
        return last + mins * 60
    if mode == "daily":
        target = n.replace(hour=hh, minute=mm, second=0, microsecond=0)
        if target <= n:
            from datetime import timedelta
            target += timedelta(days=1)
        return target.timestamp()
    if mode == "weekly":
        wd = int(s.get("weekday") or 1) % 7  # python: Mon=0
        days_ahead = (wd - n.weekday()) % 7
        from datetime import timedelta
        target = n.replace(hour=hh, minute=mm, second=0, microsecond=0) + timedelta(days=days_ahead)
        if target <= n:
            target += timedelta(days=7)
        return target.timestamp()
    return now_ts + 3600


async def _runner() -> None:
    while True:
        try:
            now_ts = time.time()
            for s in store.list_schedules():
                if not s.get("enabled"):
                    continue
                next_run = s.get("next_run")
                if next_run is None or float(next_run) <= now_ts:
                    logger.info(f"[sync] schedule #{s['id']} triggering profile {s['profile_id']}")
                    store.set_schedule_next_run(s["id"], None)
                    # run in a separate task so one slow sync doesn't stall others
                    asyncio.create_task(_run_schedule(s.copy()))
            await _maybe_daily_clean(now_ts)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[sync] scheduler tick failed: {e}")
        await asyncio.sleep(CHECK_EVERY)


def _clean_marker() -> Optional[str]:
    row = store._row("SELECT value FROM sync_settings WHERE key=?", (_LAST_CLEAN_KEY,))
    return row["value"] if row else None


async def _maybe_daily_clean(now_ts: float) -> None:
    """Auto log cleanup once per day (dysync LogFileCleaner), gated by the
    auto_clean_logs setting. Records the date it last ran in sync_settings."""
    settings = store.get_all_settings()
    if not settings.get("auto_clean_logs"):
        return
    today = datetime.fromtimestamp(now_ts).strftime("%Y-%m-%d")
    if _clean_marker() == today:
        return
    store._exec("INSERT OR REPLACE INTO sync_settings (key,value) VALUES (?,?)",
                (_LAST_CLEAN_KEY, json.dumps(today)))
    removed = await prune_old_logs()
    logger.info(f"[sync] daily log auto-clean removed {removed} file(s)")


async def _run_schedule(s: Dict[str, Any]) -> None:
    try:
        result = await engine.run_profile(s["profile_id"])
        if result.get("ok"):
            store.set_schedule_next_run(s["id"], _next_run(s, time.time()))
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[sync] scheduled run for schedule #{s['id']} failed: {e}")
        store.set_schedule_next_run(s["id"], _next_run(s, time.time()))


def _prune_app_logs(retention_days: int) -> int:
    """Delete rotated/app log files older than retention (dysync: clear logs)."""
    removed = 0
    cutoff = time.time() - int(retention_days or 30) * 86400
    try:
        for p in APP_LOG_DIR.glob("*"):
            try:
                if p.is_file() and p.stat().st_mtime < cutoff:
                    p.unlink(missing_ok=True)
                    removed += 1
            except Exception:
                continue
    except Exception:
        pass
    return removed


async def prune_old_logs() -> int:
    """Prune sync runs + app log files per log_retention_days setting."""
    days = int(store.get_all_settings().get("log_retention_days") or 30)
    before = time.time() - days * 86400
    store.clear_sync_runs(before)
    return await asyncio.to_thread(_prune_app_logs, days)


def start_scheduler() -> None:
    loop = asyncio.get_event_loop()
    loop.create_task(_runner())


def refresh_next_runs() -> None:
    """Recompute next_run for enabled schedules (called after any schedule CRUD)."""
    now_ts = time.time()
    for s in store.list_schedules():
        if not s.get("enabled"):
            continue
        if s.get("next_run") is None:
            store.set_schedule_next_run(s["id"], _next_run(s, now_ts))
        else:
            # keep the stored one; only fill nulls
            pass