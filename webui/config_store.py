"""
Web UI own configuration: first-run setup state + standalone settings store.

Design (per user requirement): the Web UI must NOT default to reading the
desktop GUI's config directory (on Linux that is ~/.local/share/YTSage and
may already contain old desktop settings). Instead:

  - webui_config.json (platform config dir, managed by auth.py) also stores:
      setup_complete: bool          - first-run wizard finished?
      config_mode: "standalone"|"shared"
  - standalone settings live in settings.json next to webui_config.json
  - "shared" mode (explicit user choice in the wizard) uses the official
    ConfigManager so desktop and web stay in sync

official_bridge.cfg_get/cfg_set pick the backend at call time from config_mode.
"""

import json
import threading
from pathlib import Path
from typing import Any, Dict, Optional

from .auth import WEBUI_CONFIG_DIR, WEBUI_CONFIG_FILE, set_password

STANDALONE_SETTINGS_FILE = WEBUI_CONFIG_DIR / "settings.json"

_lock = threading.RLock()


def _load_webui_config() -> dict:
    if WEBUI_CONFIG_FILE.exists():
        try:
            return json.loads(WEBUI_CONFIG_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _save_webui_config(cfg: dict) -> None:
    WEBUI_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    WEBUI_CONFIG_FILE.write_text(json.dumps(cfg, indent=2), encoding="utf-8")


def get_setup_state() -> Dict[str, Any]:
    cfg = _load_webui_config()
    if "setup_complete" not in cfg:
        # Backward-compat migration: an existing install that already has a
        # password hash or signing secret predates the wizard - treat it as
        # completed in "shared" mode (that is where its settings already are).
        if cfg.get("password_hash") or cfg.get("secret"):
            cfg["setup_complete"] = True
            cfg["config_mode"] = "shared"
            _save_webui_config(cfg)
            return {"setup_complete": True, "config_mode": "shared"}
        return {"setup_complete": False, "config_mode": "standalone"}
    return {
        "setup_complete": bool(cfg.get("setup_complete", False)),
        "config_mode": cfg.get("config_mode", "standalone"),
    }


def config_mode() -> str:
    return get_setup_state()["config_mode"]


class StandaloneSettings:
    """JSON-file settings store with the same dotted-key API as ConfigManager."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._data: Optional[Dict[str, Any]] = None

    def _load(self) -> Dict[str, Any]:
        if self._data is None:
            if self._path.exists():
                try:
                    self._data = json.loads(self._path.read_text(encoding="utf-8"))
                except Exception:
                    self._data = {}
            else:
                self._data = {}
        return self._data

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps(self._data, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    def get(self, key: str) -> Any:
        with _lock:
            d = self._load()
            for part in key.split("."):
                if isinstance(d, dict) and part in d:
                    d = d[part]
                else:
                    return None
            return d

    def set(self, key: str, value: Any) -> None:
        with _lock:
            d = self._load()
            parts = key.split(".")
            for part in parts[:-1]:
                d = d.setdefault(part, {})
            d[parts[-1]] = value
            self._save()

    def update(self, mapping: Dict[str, Any]) -> None:
        with _lock:
            for k, v in mapping.items():
                self.set(k, v)


standalone = StandaloneSettings(STANDALONE_SETTINGS_FILE)


def complete_setup(
    password: str,
    mode: str,
    download_path: str,
    language: str,
    import_desktop: bool,
    seed_defaults: Optional[Dict[str, Any]] = None,
) -> None:
    """Persist wizard results. Imports desktop settings when asked."""
    set_password(password)

    cfg = _load_webui_config()
    cfg["setup_complete"] = True
    cfg["config_mode"] = mode
    _save_webui_config(cfg)

    if mode == "standalone":
        seed: Dict[str, Any] = dict(seed_defaults or {})
        if import_desktop:
            # Lazy import to avoid module cycle (official_bridge -> config_store)
            from .official_bridge import HAS_CONFIG, _OfficialConfigManager
            from .settings_service import PUBLIC_KEYS

            if HAS_CONFIG and _OfficialConfigManager is not None:
                for k in PUBLIC_KEYS:
                    v = _OfficialConfigManager.get(k)
                    if v is not None:
                        seed[k] = v
        seed["download_path"] = download_path
        seed["language"] = language
        standalone.update(seed)
    else:
        # Shared mode: write the wizard choices straight into the official config
        from .official_bridge import HAS_CONFIG, _OfficialConfigManager

        if HAS_CONFIG and _OfficialConfigManager is not None:
            # Migrate anything already saved in standalone mode first
            existing = standalone._load()
            for k, v in existing.items():
                if _OfficialConfigManager.get(k) is None:
                    _OfficialConfigManager.set(k, v)
            if download_path:
                _OfficialConfigManager.set("download_path", download_path)
            _OfficialConfigManager.set("language", language)
