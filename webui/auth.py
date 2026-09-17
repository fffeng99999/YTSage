"""
Token-based authentication for YTSage Web UI.

Password hashing uses PBKDF2-HMAC-SHA256 with a per-password random salt.
Legacy SHA-256 hashes produced by older builds are still accepted, but are
transparently re-hashed with the stronger scheme on the next successful login.

Tokens are HMAC-SHA256 signed and carry a ``ver`` (token epoch) claim. The
epoch is bumped whenever the password changes, which invalidates every token
that was issued before it.
"""

import hashlib
import hmac
import json
import os
import secrets
import threading
import time
from pathlib import Path
from typing import Optional, Tuple

# Default password - user should change it via settings
DEFAULT_PASSWORD = "ytsage"
TOKEN_TTL_SECONDS = 7 * 24 * 3600  # 7 days

# PBKDF2 parameters. 600k iterations is the OWASP floor for PBKDF2-HMAC-SHA256.
_PBKDF2_ITERATIONS = 600_000
_PBKDF2_SALT_BYTES = 16
_PBKDF2_PREFIX = "pbkdf2_sha256"
_LEGACY_SALT_PREFIX = "ytsage_webui_"

# --- login throttling (in-process; a restart resets it, which is fine for a
# --- single-user self-hosted app whose real defence is a strong password) ---
MAX_FAILED_ATTEMPTS = 5
LOCKOUT_SECONDS = 60
_throttle_lock = threading.Lock()
_failed_attempts: dict = {}
_lockout_until: dict = {}

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
    # Lazy import: file_utils is standalone, but keep module load order flat.
    from .file_utils import write_json_atomic

    write_json_atomic(WEBUI_CONFIG_FILE, cfg)


# ---------------------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------------------

def _hash_password(password: str) -> str:
    """PBKDF2-HMAC-SHA256 with a fresh random salt."""
    salt = secrets.token_bytes(_PBKDF2_SALT_BYTES)
    dk = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, _PBKDF2_ITERATIONS
    )
    return f"{_PBKDF2_PREFIX}${_PBKDF2_ITERATIONS}${salt.hex()}${dk.hex()}"


def _legacy_hash(password: str) -> str:
    """Pre-hardening hash. Kept only so existing installs keep working."""
    return hashlib.sha256(f"{_LEGACY_SALT_PREFIX}{password}".encode("utf-8")).hexdigest()


def verify_against_hash(stored: str, password: str) -> bool:
    """Constant-time check of ``password`` against a stored hash (any scheme)."""
    if not stored:
        return False
    if stored.startswith(f"{_PBKDF2_PREFIX}$"):
        try:
            _prefix, iterations, salt_hex, hash_hex = stored.split("$")
            dk = hashlib.pbkdf2_hmac(
                "sha256",
                password.encode("utf-8"),
                bytes.fromhex(salt_hex),
                int(iterations),
            )
            return hmac.compare_digest(dk.hex(), hash_hex)
        except (ValueError, TypeError):
            return False
    return hmac.compare_digest(_legacy_hash(password), stored)


def get_password_hash() -> str:
    cfg = _load_config()
    return cfg.get("password_hash", _hash_password(DEFAULT_PASSWORD))


def set_password(password: str, rotate_secret: bool = True) -> None:
    """Store a new password.

    ``rotate_secret`` bumps the token epoch so every previously issued token
    stops working (used on an explicit password change, not on hash migration).
    """
    cfg = _load_config()
    cfg["password_hash"] = _hash_password(password)
    if rotate_secret:
        cfg["secret"] = secrets.token_hex(32)
        cfg["token_epoch"] = int(cfg.get("token_epoch", 0)) + 1
    _save_config(cfg)


def verify_password(password: str) -> bool:
    """Verify a password against the stored hash."""
    stored = get_password_hash()
    if not verify_against_hash(stored, password):
        return False
    # Transparent upgrade: legacy hashes are re-written in the strong scheme.
    # No secret rotation here - that would log the user out mid-session.
    if not stored.startswith(f"{_PBKDF2_PREFIX}$"):
        try:
            set_password(password, rotate_secret=False)
        except Exception:
            pass
    return True


def is_default_password() -> bool:
    """True when the well-known default password is still active."""
    return verify_against_hash(get_password_hash(), DEFAULT_PASSWORD)


# ---------------------------------------------------------------------------
# Login throttling
# ---------------------------------------------------------------------------

def lockout_remaining(key: str) -> int:
    """Seconds left before ``key`` may try again (0 = not locked)."""
    with _throttle_lock:
        remaining = _lockout_until.get(key, 0) - time.time()
    return int(remaining) + 1 if remaining > 0 else 0


def register_failed_attempt(key: str) -> int:
    """Record a failed login. Returns the lockout seconds just applied (0 if none)."""
    now = time.time()
    with _throttle_lock:
        if _lockout_until.get(key, 0) > now:
            return int(_lockout_until[key] - now) + 1
        count = _failed_attempts.get(key, 0) + 1
        _failed_attempts[key] = count
        if count >= MAX_FAILED_ATTEMPTS:
            _lockout_until[key] = now + LOCKOUT_SECONDS
            _failed_attempts[key] = 0
            return LOCKOUT_SECONDS
    return 0


def clear_attempts(key: str) -> None:
    """Call after a successful login."""
    with _throttle_lock:
        _failed_attempts.pop(key, None)
        _lockout_until.pop(key, None)


# ---------------------------------------------------------------------------
# LAN / security posture
# ---------------------------------------------------------------------------

LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}


def host_is_loopback(host: str) -> bool:
    return (host or "").strip() in LOOPBACK_HOSTS


def security_state(host: str) -> dict:
    """Public summary used for the LAN warning banner (no secrets exposed)."""
    return {
        "default_password": is_default_password(),
        "lan_exposed": not host_is_loopback(host),
        "require_custom_password": os.environ.get(
            "YTSAGE_REQUIRE_CUSTOM_PASSWORD", ""
        ).lower() in ("1", "true", "yes"),
    }


# ---------------------------------------------------------------------------
# Tokens
# ---------------------------------------------------------------------------

def _get_auth_state() -> Tuple[str, int]:
    """Return (signing secret, token epoch), creating the secret on first use."""
    cfg = _load_config()
    secret = cfg.get("secret")
    if not secret:
        secret = secrets.token_hex(32)
        cfg["secret"] = secret
        _save_config(cfg)
    return secret, int(cfg.get("token_epoch", 0))


def create_token() -> str:
    """Create a signed auth token."""
    secret, epoch = _get_auth_state()
    now = int(time.time())
    payload = {
        "exp": now + TOKEN_TTL_SECONDS,
        "iat": now,
        "ver": epoch,
    }
    payload_json = json.dumps(payload, separators=(",", ":"))
    sig = hmac.new(secret.encode(), payload_json.encode(), hashlib.sha256).hexdigest()
    return f"{payload_json}.{sig}"


def verify_token(token: str) -> Optional[dict]:
    """Verify a token and return its payload, or None if invalid/expired/revoked."""
    try:
        payload_json, sig = token.rsplit(".", 1)
        secret, epoch = _get_auth_state()
        expected = hmac.new(secret.encode(), payload_json.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected):
            return None
        payload = json.loads(payload_json)
        if not isinstance(payload, dict):
            return None
        if int(payload.get("exp", 0)) < time.time():
            return None
        # A password change bumps the epoch -> all older tokens are revoked.
        if int(payload.get("ver", 0)) != epoch:
            return None
        return payload
    except Exception:
        return None
