"""
Simple token-based authentication for YTSage Web UI.
Uses HMAC-SHA256 signed tokens (no external JWT dependency).
"""

import hashlib
import hmac
import json
import os
import secrets
import time
from pathlib import Path
from typing import Optional

# Default password - user should change it via settings
DEFAULT_PASSWORD = "ytsage"
TOKEN_TTL_SECONDS = 7 * 24 * 3600  # 7 days

# Config file for web UI settings (separate from official ytsage config)
WEBUI_CONFIG_DIR = Path(os.environ.get("APPDATA", Path.home() / ".config")) / "YTSage"
WEBUI_CONFIG_FILE = WEBUI_CONFIG_DIR / "webui_config.json"


def _ensure_config_dir() -> None:
    WEBUI_CONFIG_DIR.mkdir(parents=True, exist_ok=True)


def _load_config() -> dict:
    _ensure_config_dir()
    if WEBUI_CONFIG_FILE.exists():
        try:
            with open(WEBUI_CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def _save_config(cfg: dict) -> None:
    _ensure_config_dir()
    with open(WEBUI_CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)


def get_password_hash() -> str:
    cfg = _load_config()
    return cfg.get("password_hash", _hash_password(DEFAULT_PASSWORD))


def set_password(password: str) -> None:
    cfg = _load_config()
    cfg["password_hash"] = _hash_password(password)
    _save_config(cfg)


def _hash_password(password: str) -> str:
    """Hash password with salt using SHA-256."""
    salted = f"ytsage_webui_{password}".encode("utf-8")
    return hashlib.sha256(salted).hexdigest()


def verify_password(password: str) -> bool:
    """Verify a password against stored hash."""
    stored = get_password_hash()
    return _hash_password(password) == stored


def _get_secret() -> str:
    """Get or create a signing secret."""
    cfg = _load_config()
    secret = cfg.get("secret")
    if not secret:
        secret = secrets.token_hex(32)
        cfg["secret"] = secret
        _save_config(cfg)
    return secret


def create_token() -> str:
    """Create a signed auth token."""
    secret = _get_secret()
    payload = {
        "exp": int(time.time()) + TOKEN_TTL_SECONDS,
        "iat": int(time.time()),
    }
    payload_json = json.dumps(payload, separators=(",", ":"))
    sig = hmac.new(secret.encode(), payload_json.encode(), hashlib.sha256).hexdigest()
    return f"{payload_json}.{sig}"


def verify_token(token: str) -> Optional[dict]:
    """Verify a token and return its payload, or None if invalid."""
    try:
        payload_json, sig = token.rsplit(".", 1)
        secret = _get_secret()
        expected = hmac.new(secret.encode(), payload_json.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected):
            return None
        payload = json.loads(payload_json)
        if payload.get("exp", 0) < time.time():
            return None
        return payload
    except Exception:
        return None
