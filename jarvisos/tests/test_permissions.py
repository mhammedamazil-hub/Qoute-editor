"""Safety layer: nothing dangerous auto-runs, nothing safe is blocked."""
from jarvis import permissions as P


def test_intent_levels():
    assert P.classify_intent("apps.open").level == P.SAFE
    assert P.classify_intent("system.ram").level == P.SAFE
    assert P.classify_intent("power.reboot").level == P.CONFIRM
    assert P.classify_intent("apps.install").level == P.CONFIRM
    assert P.classify_intent("files.empty_trash").level == P.CONFIRM
    assert P.classify_intent("automation.run_task").level == P.CONFIRM
    assert P.classify_intent("disk.format").level == P.DENY
    assert P.classify_intent("disk.partition").level == P.DENY
    # sneaky payloads in slots are denied
    v = P.classify_intent("ai.ask", {"question": "please run mkfs on /dev/sda"})
    assert v.level == P.DENY


def test_action_levels():
    assert P.classify_action({"type": "open_app", "app": "x"}).level == P.SAFE
    assert P.classify_action({"type": "click", "x": 1, "y": 1}).level == P.SAFE
    assert P.classify_action({"type": "key", "key": "enter"}).level == P.SAFE
    assert P.classify_action({"type": "shell", "command": "wifi_scan"}
                             ).level == P.SAFE
    assert P.classify_action({"type": "shell", "command": "apt_update"}
                             ).level == P.CONFIRM
    assert P.classify_action({"type": "shell", "command": "rm -rf ~"}
                             ).level == P.DENY
    assert P.classify_action({"type": "format_disk"}).level == P.DENY
    assert P.classify_action({"type": "nope"}).level == P.DENY
    assert P.classify_action("garbage").level == P.DENY
    assert P.classify_action({"type": "type", "text": "mkfs.ext4 /dev/sda"}
                             ).level == P.DENY


def test_coordinates():
    ok, x, y = P.validate_coordinates(100, 200, 1920, 1080)
    assert (ok, x, y) == (True, 100, 200)
    assert P.validate_coordinates(-5, 10)[0] is False
    assert P.validate_coordinates(5000, 10)[0] is False
    assert P.validate_coordinates("a", "b")[0] is False
