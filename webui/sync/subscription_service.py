"""
YTSage Sync - Subscription Management Service
==============================================
Manage YouTube channel subscriptions and sync modes.
"""

import logging
from typing import Dict, Any, List, Optional

from . import store

logger = logging.getLogger("ytsage.webui.sync.subscription")


def pull_subscriptions(profile_id: int) -> Dict[str, Any]:
    """
    Pull YouTube subscriptions list for a profile.
    
    Args:
        profile_id: Sync profile ID
    
    Returns:
        Dict with subscription list and stats
    """
    from ..analysis_service import _sync_run
    from ..yt_dlp_finder import get_yt_dlp_path
    import json
    
    profile = store.get_profile(profile_id)
    if not profile:
        return {"error": "Profile not found", "subscriptions": []}
    
    # Build auth options
    auth_opts = []
    if profile.get("cookie_source") == "file" and profile.get("cookie_file_path"):
        auth_opts = ["--cookies", profile["cookie_file_path"]]
    elif profile.get("cookie_source") == "browser":
        browser = profile.get("cookie_browser") or "chrome"
        browser_profile = profile.get("cookie_browser_profile") or ""
        auth_opts = ["--cookies-from-browser", f"{browser}:{browser_profile}" if browser_profile else browser]
    
    # Fetch subscriptions feed
    url = "https://www.youtube.com/feed/subscriptions"
    cmd = [get_yt_dlp_path(), "--flat-playlist", "--dump-single-json", "--no-warnings"]
    cmd += auth_opts + [url]
    
    try:
        result = _sync_run(cmd, timeout=120)
        if result.returncode != 0:
            logger.error(f"[sync] Failed to pull subscriptions: {result.stderr}")
            return {"error": result.stderr or "Failed to fetch subscriptions", "subscriptions": []}
        
        # Parse output
        lines = [l.strip() for l in (result.stdout or "").strip().split("\n") if l.strip()]
        if not lines:
            return {"error": "No output from yt-dlp", "subscriptions": []}
        
        data = json.loads(lines[0])
        entries = data.get("entries", [])
        
        # Extract unique channels
        channels = {}
        for entry in entries:
            channel_id = entry.get("channel_id") or entry.get("uploader_id")
            channel_name = entry.get("channel") or entry.get("uploader") or "Unknown"
            avatar_url = entry.get("channel_thumbnail") or entry.get("thumbnail")
            
            if channel_id and channel_id not in channels:
                channels[channel_id] = {
                    "channel_id": channel_id,
                    "channel_name": channel_name,
                    "avatar_url": avatar_url,
                    "url": f"https://www.youtube.com/channel/{channel_id}",
                }
        
        subscriptions = list(channels.values())
        logger.info(f"[sync] Pulled {len(subscriptions)} subscriptions for profile {profile_id}")
        
        return {"subscriptions": subscriptions, "count": len(subscriptions)}
    except Exception as e:
        logger.error(f"[sync] Exception pulling subscriptions: {e}")
        return {"error": str(e), "subscriptions": []}


def add_subscription(profile_id: int, channel_url: str, channel_name: Optional[str] = None) -> Dict[str, Any]:
    """
    Manually add a channel subscription.
    
    Args:
        profile_id: Sync profile ID
        channel_url: YouTube channel URL
        channel_name: Optional channel name
    
    Returns:
        Dict with target ID
    """
    # Extract channel ID from URL
    channel_id = None
    if "/channel/" in channel_url:
        channel_id = channel_url.split("/channel/")[-1].split("/")[0].split("?")[0]
    elif "/@" in channel_url:
        # Handle @username format
        channel_id = channel_url.split("/@")[-1].split("/")[0].split("?")[0]
    
    if not channel_id:
        return {"error": "Invalid channel URL"}
    
    # Create target
    target_data = {
        "kind": "channel",
        "url": channel_url,
        "title": channel_name or f"Channel {channel_id[:8]}",
        "folder": channel_name or f"channel_{channel_id[:8]}",
        "enabled": True,
        "sync_mode": "sync",
        "channel_id": channel_id,
    }
    
    target_id = store.create_target(profile_id, target_data)
    logger.info(f"[sync] Added subscription {channel_id} to profile {profile_id}")
    
    return {"target_id": target_id, "channel_id": channel_id}


def save_subscriptions(profile_id: int, channels: List[Dict[str, Any]],
                       sync_mode: str = "off") -> Dict[str, Any]:
    """Persist pulled subscription channels as channel targets, skipping ones
    already present (matched by channel_id). dysync: new follows default to
    sync=false until the user enables them."""
    existing = {t.get("channel_id") for t in store.list_targets(profile_id) if t.get("channel_id")}
    added = 0
    for c in channels or []:
        cid = c.get("channel_id")
        if not cid or cid in existing:
            continue
        name = c.get("channel_name") or f"Channel {cid[:8]}"
        store.create_target(profile_id, {
            "kind": "channel",
            "url": c.get("url") or f"https://www.youtube.com/channel/{cid}",
            "title": name,
            "folder": name,
            "enabled": True,
            "sync_mode": sync_mode if sync_mode in ("off", "sync", "full_sync") else "off",
            "channel_id": cid,
            "avatar_url": c.get("avatar_url"),
        })
        existing.add(cid)
        added += 1
    logger.info(f"[sync] saved {added} new subscriptions for profile {profile_id}")
    return {"added": added, "skipped": len(channels or []) - added}


def update_subscription_sync_mode(target_id: int, sync_mode: str) -> bool:
    """
    Update sync mode for a subscription target.
    
    Args:
        target_id: Target ID
        sync_mode: 'off', 'sync', or 'full_sync'
    
    Returns:
        True if successful
    """
    if sync_mode not in ("off", "sync", "full_sync"):
        logger.error(f"[sync] Invalid sync mode: {sync_mode}")
        return False
    
    store.update_target_sync_mode(target_id, sync_mode)
    logger.info(f"[sync] Updated target {target_id} sync mode to {sync_mode}")
    return True


def update_subscription_save_path(target_id: int, save_path: str) -> bool:
    """
    Update save path for a subscription target.
    
    Args:
        target_id: Target ID
        save_path: New save path
    
    Returns:
        True if successful
    """
    store.update_target_save_path(target_id, save_path)
    logger.info(f"[sync] Updated target {target_id} save path to {save_path}")
    return True


def list_subscriptions(profile_id: int) -> List[Dict[str, Any]]:
    """
    List all channel subscriptions for a profile.
    
    Args:
        profile_id: Sync profile ID
    
    Returns:
        List of target dicts (channel subscriptions only)
    """
    all_targets = store.list_targets(profile_id)
    # Filter to channel kind only
    return [t for t in all_targets if t.get("kind") == "channel"]


def get_subscription_stats(profile_id: int) -> Dict[str, Any]:
    """
    Get subscription statistics for a profile.
    
    Args:
        profile_id: Sync profile ID
    
    Returns:
        Dict with subscription stats
    """
    subscriptions = list_subscriptions(profile_id)
    
    total = len(subscriptions)
    active = sum(1 for s in subscriptions if s.get("sync_mode") != "off")
    full_sync = sum(1 for s in subscriptions if s.get("sync_mode") == "full_sync")
    
    return {
        "total": total,
        "active": active,
        "full_sync": full_sync,
        "inactive": total - active,
    }
