"""Safety / permission layer between AI (or voice) and the OS.

Every Intent and every automation Action is classified:

  SAFE    — runs immediately (open apps, queries, volume, screenshots…)
  CONFIRM — needs explicit user confirmation (install, reboot, delete…)
  DENY    — never runs (partition edits, bootloader, raw dangerous shell…)

The AI NEVER executes shell directly: only allowlisted `shell` templates with
validated arguments may run, and destructive ones always CONFIRM.
"""
from __future__ import annotations

from dataclasses import dataclass

SAFE = "safe"
CONFIRM = "confirm"
DENY = "deny"

# Intents that always need a confirmation click/voice-yes.
CONFIRM_INTENTS = frozenset({
    "power.reboot",
    "power.shutdown",
    "power.suspend",
    "session.logout",
    "apps.install",
    "apps.remove",
    "apps.update_system",
    "files.delete",
    "files.empty_trash",
    "files.move_to_trash",
    "system.factory_reset",
    "automation.run_task",   # AI screen-control always confirms first
})

# Intents that are never executable via JARVIS (must use dedicated tools).
DENY_INTENTS = frozenset({
    "disk.format",
    "disk.partition",
    "bootloader.modify",
    "system.factory_reset",
})

DENY_SUBSTRINGS = (
    "mkfs", "fdisk", "parted", "gdisk", "dd ", "dd\t", ":(){", "mkswap",
    "bootloader", "grub-install", "/dev/sd", "/dev/nvme", "/dev/vd",
    "rm -rf /", "rm -rf ~", "rm -rf .", "chmod -R 777",
)

# Structured automation actions allowed to auto-run.
SAFE_ACTIONS = frozenset({
    "open_app", "focus_app", "close_app", "wait", "click", "move", "scroll",
    "key", "hotkey", "type", "screenshot", "notify", "set_volume",
    "mute", "set_brightness", "wifi_on", "wifi_off", "bluetooth_on",
    "bluetooth_off", "lock_screen", "open_url", "open_path",
})

# Structured actions needing confirmation each batch.
CONFIRM_ACTIONS = frozenset({
    "shell", "install_app", "remove_app", "delete_path", "move_to_trash",
    "reboot", "shutdown", "suspend", "logout", "system_update",
})

DENY_ACTIONS = frozenset({
    "format_disk", "partition", "raw_shell", "disable_safety",
})

# Allowlisted shell templates: name → (argv template, risk). Only these may
# ever be executed through the `shell` action; arguments are validated.
SHELL_ALLOWLIST = {
    # connectivity
    "wifi_scan": (["nmcli", "device", "wifi", "list"], SAFE),
    "wifi_connect": (["nmcli", "device", "wifi", "connect", "{ssid}"], CONFIRM),
    # bluetooth read-only helpers are read via bluetoothctl scripts in backend
    # packages / updates
    "apt_update": (["apt-get", "update"], CONFIRM),
    "apt_install": (["apt-get", "install", "-y", "{pkg}"], CONFIRM),
}


@dataclass
class Verdict:
    level: str           # SAFE | CONFIRM | DENY
    reason: str = ""
    confirm_token: str = ""  # filled by Core when CONFIRM is issued


def classify_intent(name, slots=None):
    slots = slots or {}
    lname = (name or "").lower()
    if lname in DENY_INTENTS:
        return Verdict(DENY, "action '%s' is blocked by the safety policy" % name)
    blob = (lname + " " + " ".join(str(v) for v in slots.values())).lower()
    for bad in DENY_SUBSTRINGS:
        if bad in blob:
            return Verdict(DENY, "blocked pattern in request")
    if lname in CONFIRM_INTENTS:
        return Verdict(CONFIRM, "action '%s' needs confirmation" % name)
    return Verdict(SAFE, "ok")


def classify_action(action):
    """Classify a structured automation action dict."""
    if not isinstance(action, dict):
        return Verdict(DENY, "action must be an object")
    atype = str(action.get("type", "")).lower()
    if atype in DENY_ACTIONS:
        return Verdict(DENY, "action type '%s' is blocked" % atype)
    if atype == "shell":
        cmd = str(action.get("command", ""))
        if cmd not in SHELL_ALLOWLIST:
            return Verdict(DENY, "shell command '%s' is not allowlisted" % cmd)
        return Verdict(SHELL_ALLOWLIST[cmd][1], "allowlisted shell: %s" % cmd)
    if atype in CONFIRM_ACTIONS:
        return Verdict(CONFIRM, "action '%s' needs confirmation" % atype)
    if atype in SAFE_ACTIONS:
        # extra guard: typing must not contain destructive pastes
        if atype == "type":
            text = str(action.get("text", "")).lower()
            for bad in DENY_SUBSTRINGS:
                if bad in text:
                    return Verdict(DENY, "typed text contains blocked pattern")
        return Verdict(SAFE, "ok")
    return Verdict(DENY, "unknown action type '%s'" % atype)


def validate_coordinates(x, y, width=1920, height=1080):
    """Clamp/validate click coordinates; returns (ok, x, y)."""
    try:
        x = float(x)
        y = float(y)
    except (TypeError, ValueError):
        return False, 0, 0
    if width <= 0 or height <= 0:
        return False, 0, 0
    if not (0 <= x < width and 0 <= y < height):
        return False, 0, 0
    return True, int(x), int(y)
