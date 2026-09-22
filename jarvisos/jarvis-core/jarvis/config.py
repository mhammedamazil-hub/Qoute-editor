"""Layered configuration + secrets for JARVISOS.

Layers (low → high precedence):
  1. factory defaults  (/etc/jarvisos/defaults.json, or settings/defaults.json)
  2. user config       (~/.config/jarvisos/config.json)
Secrets (API keys) live ONLY in ~/.config/jarvisos/secrets.json (mode 0600)
and are never logged, never committed, never baked into the ISO.
"""
from __future__ import annotations

import json
import os
import tempfile

APP_NAME = "jarvisos"
USER_DIR = os.path.join(os.path.expanduser("~"), ".config", APP_NAME)
USER_CONFIG = os.path.join(USER_DIR, "config.json")
SECRETS_FILE = os.path.join(USER_DIR, "secrets.json")

_FACTORY_CANDIDATES = (
    "/etc/jarvisos/defaults.json",
    os.path.join(os.path.dirname(__file__), "..", "..", "settings", "defaults.json"),
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "defaults.json"),
)


def _read_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, default.__class__) else default
    except (OSError, ValueError):
        return default


def _atomic_write_json(path, obj, mode=None):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path) or ".", prefix=".tmp-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(obj, fh, indent=2, sort_keys=True)
            fh.write("\n")
        if mode is not None:
            os.chmod(tmp, mode)
        os.replace(tmp, path)
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass


def _deep_merge(base, override):
    out = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def find_factory_defaults():
    for cand in _FACTORY_CANDIDATES:
        cand = os.path.normpath(cand)
        if os.path.isfile(cand):
            return cand
    return None


class Config:
    """Layered config. Reads factory defaults + user overrides."""

    def __init__(self, factory_path=None, user_path=None, secrets_path=None):
        self.factory_path = factory_path or find_factory_defaults()
        self.user_path = user_path or USER_CONFIG
        self.secrets_path = secrets_path or SECRETS_FILE
        self._factory = _read_json(self.factory_path, {}) if self.factory_path else {}
        self._user = _read_json(self.user_path, {})
        self._secrets = _read_json(self.secrets_path, {})

    # -- reads ---------------------------------------------------------
    def get(self, dotted, default=None):
        node = _deep_merge(self._factory, self._user)
        for part in dotted.split("."):
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return node

    def get_all(self):
        return _deep_merge(self._factory, self._user)

    def get_secret(self, provider):
        """Return stored API key for provider or '' (never raises)."""
        try:
            return str(self._secrets.get(provider, "") or "")
        except Exception:
            return ""

    def has_secret(self, provider):
        return bool(self.get_secret(provider))

    # -- writes --------------------------------------------------------
    def set(self, dotted, value):
        node = self._user
        parts = dotted.split(".")
        for part in parts[:-1]:
            child = node.get(part)
            if not isinstance(child, dict):
                child = {}
                node[part] = child
            node = child
        node[parts[-1]] = value
        _atomic_write_json(self.user_path, self._user, mode=0o600)

    def set_secret(self, provider, value):
        self._secrets[provider] = value or ""
        _atomic_write_json(self.secrets_path, self._secrets, mode=0o600)

    def reload(self):
        self._user = _read_json(self.user_path, {})
        self._secrets = _read_json(self.secrets_path, {})


_config_singleton = None


def get_config():
    global _config_singleton
    if _config_singleton is None:
        _config_singleton = Config()
    return _config_singleton
