"""
Credential helpers for oneprompt cloud authentication.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def _config_dir() -> Path:
    """Return the OS-specific oneprompt config directory."""
    custom_dir = os.getenv("ONEPROMPT_CONFIG_DIR", "").strip()
    if custom_dir:
        return Path(custom_dir).expanduser().resolve()

    if os.name == "nt":
        app_data = os.getenv("APPDATA", "").strip()
        if app_data:
            return Path(app_data) / "oneprompt"
        return Path.home() / ".oneprompt"

    xdg_dir = os.getenv("XDG_CONFIG_HOME", "").strip()
    if xdg_dir:
        return Path(xdg_dir).expanduser().resolve() / "oneprompt"
    return Path.home() / ".config" / "oneprompt"


def credentials_path() -> Path:
    """Return the path to the local credentials file."""
    return _config_dir() / "credentials.json"


def load_oneprompt_api_key() -> str:
    """Load ONEPROMPT API key from secure local credentials storage."""
    path = credentials_path()
    if not path.exists():
        return ""

    try:
        payload: Any = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return ""

    if not isinstance(payload, dict):
        return ""
    return str(payload.get("oneprompt_api_key", "")).strip()


def save_oneprompt_api_key(api_key: str) -> Path:
    """Persist ONEPROMPT API key to secure local credentials storage."""
    key = api_key.strip()
    if not key:
        raise ValueError("API key cannot be empty")

    cfg_dir = _config_dir()
    cfg_dir.mkdir(parents=True, exist_ok=True)
    if os.name != "nt":
        cfg_dir.chmod(0o700)

    path = credentials_path()
    payload: dict[str, str] = {}
    if path.exists():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                payload = {k: str(v) for k, v in loaded.items()}
        except Exception:
            payload = {}

    payload["oneprompt_api_key"] = key

    tmp_path = path.with_suffix(".tmp")
    tmp_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    tmp_path.replace(path)
    if os.name != "nt":
        path.chmod(0o600)
    return path
