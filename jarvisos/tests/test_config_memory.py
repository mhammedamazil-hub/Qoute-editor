"""Layered config + secrets + local memory."""
import json
import os


def test_layered_config(config, tmp_path):
    # factory default visible
    assert config.get("gestures.cooldown_ms") == 1800
    assert config.get("missing.key", "dflt") == "dflt"
    # user override wins + persists
    config.set("gestures.sensitivity", 4.5)
    assert config.get("gestures.sensitivity") == 4.5
    with open(tmp_path / "config.json") as fh:
        assert json.load(fh)["gestures"]["sensitivity"] == 4.5


def test_secrets_0600(config, tmp_path):
    config.set_secret("gemini", "KEY-123")
    assert config.get_secret("gemini") == "KEY-123"
    assert config.has_secret("gemini") is True
    assert config.has_secret("openrouter") is False
    mode = oct(os.stat(tmp_path / "secrets.json").st_mode & 0o777)
    assert mode == "0o600"


def test_memory(tmp_path):
    from jarvis.memory import Memory
    mem = Memory(path=str(tmp_path / "m.json"), enabled=True)
    assert mem.learn_from_command("remember that my wifi is Home-5G") == \
        "Remembered."
    assert mem.learn_from_command("call me Ada") == "Got it, Ada."
    assert any("Home-5G" in f for f in mem.recall("wifi"))
    assert mem.forget("home-5g") == 1
    mem.set_pref("editor", "vscode")
    assert any("vscode" in f for f in mem.recall())
    mem.clear()
    assert mem.recall() == []


def test_memory_disabled(tmp_path):
    from jarvis.memory import Memory
    mem = Memory(path=str(tmp_path / "m.json"), enabled=False)
    assert mem.remember("x") is False
    assert mem.recall("x") == []
