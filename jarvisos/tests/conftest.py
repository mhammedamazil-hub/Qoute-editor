"""Shared fixtures: isolated HOME + importable jarvis package.

IMPORTANT: HOME is redirected at import time (before `jarvis.*` modules
compute their paths), so tests never touch the real ~/.config.
"""
import os
import sys
import tempfile

_TMP_HOME = tempfile.mkdtemp(prefix="jarvis-test-home-")
os.environ["HOME"] = _TMP_HOME

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.join(ROOT, "jarvis-core"))

import pytest  # noqa: E402


@pytest.fixture()
def tmp_home(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    return tmp_path


@pytest.fixture()
def config(tmp_path):
    from jarvis.config import Config
    factory = os.path.join(ROOT, "settings", "defaults.json")
    return Config(factory_path=factory,
                  user_path=str(tmp_path / "config.json"),
                  secrets_path=str(tmp_path / "secrets.json"))


@pytest.fixture()
def core(config, tmp_path):
    from jarvis import Core
    from jarvis.memory import Memory
    mem = Memory(path=str(tmp_path / "memory.json"), enabled=True)
    return Core(config=config, memory=mem)
