"""NL parser coverage: every OS-control category."""
from jarvis import intents as I


def n(text):
    return I.parse(text).name


def test_apps_open_close_focus():
    assert n("open VS Code") == "apps.open"
    assert I.parse("open VS Code").slots["app"] == "vscode"
    assert n("Jarvis, open Blender.") == "apps.open"
    assert n("open discord") == "apps.open"
    assert n("launch the terminal") == "apps.open"
    assert n("close firefox") == "apps.close"
    assert n("switch to files") == "apps.focus"
    assert n("blender") == "apps.open"


def test_folders_and_files():
    assert I.parse("open Downloads").slots.get("folder") == "downloads"
    assert n("show my recent files") == "files.recent"
    p = I.parse("search my files for presentation")
    assert p.name == "files.search" and "presentation" in p.slots["query"]
    assert n("empty the trash") == "files.empty_trash"
    assert n("delete old-notes.txt") == "files.delete"


def test_stats():
    assert n("what is using my RAM?") == "system.ram"
    assert n("show cpu usage") == "system.cpu"
    assert n("how much disk space is free?") == "system.disk"
    assert n("battery status") == "system.battery"
    assert n("cpu temperature") == "system.temperature"


def test_network():
    assert n("connect Bluetooth") == "bluetooth.on"
    assert n("turn off wifi") == "network.wifi_off"
    p = I.parse("connect to wifi Home-5G")
    assert p.name == "network.wifi_connect" and p.slots["ssid"] == "home-5g"
    assert n("list wifi networks") == "network.wifi_list"
    assert n("am i online") == "network.status"


def test_bluetooth():
    assert n("turn on bluetooth") == "bluetooth.on"
    assert n("disable bluetooth") == "bluetooth.off"
    p = I.parse("pair my headphones")
    assert p.name == "bluetooth.connect"


def test_audio_display():
    assert I.parse("set volume to 40").slots["level"] == 40
    assert n("volume up") == "audio.volume_up"
    assert n("mute") == "audio.mute"
    assert n("take a screenshot") == "display.screenshot"
    assert I.parse("set brightness 70").slots["level"] == 70


def test_power_and_session():
    assert n("shut down the computer") == "power.shutdown"
    assert n("reboot") == "power.reboot"
    assert n("lock the screen") == "power.lock"
    assert n("log out") == "session.logout"


def test_install_and_update():
    p = I.parse("install blender")
    assert p.name == "apps.install" and p.slots["app"] == "blender"
    assert n("update the system") == "apps.update_system"


def test_ai_and_automation():
    assert n("what is on my screen?") == "ai.analyze_screen"
    assert n("do my homework for me please") == "automation.run_task"
    assert n("stop automation") == "automation.stop"
    assert n("what is the capital of France?") == "ai.ask"


def test_dangerous_and_unknown():
    assert n("format my disk") == "disk.format"
    assert n("what can you do?") == "system.help"
    assert I.parse("blorple the fnord").name == "system.unknown"


def test_match_app_fuzzy():
    assert I.match_app("vscode") == "vscode"
    assert I.match_app("browse the web") == "firefox"
    assert I.match_app("something random xyz") == ""
