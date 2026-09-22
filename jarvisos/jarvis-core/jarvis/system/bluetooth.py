"""Bluetooth via bluetoothctl + rfkill. Graceful when hardware is absent."""
from __future__ import annotations

import re

from . import _sh


def available():
    return _sh.have("bluetoothctl")


def _ctl(*args, timeout=10):
    return _sh.run(["bluetoothctl"] + list(args), timeout=timeout)


def powered():
    if not available():
        return False
    _, txt = _ctl("show")
    m = re.search(r"Powered:\s*(yes|no)", txt)
    return bool(m and m.group(1) == "yes")


def set_power(on):
    if not available():
        return False, "Bluetooth tools are not installed."
    if _sh.have("rfkill"):
        _sh.run(["rfkill", "unblock" if on else "block", "bluetooth"])
    rc, _ = _ctl("power", "on" if on else "off")
    return (True, "Bluetooth on." if on else "Bluetooth off.") if rc == 0 \
        else (False, "Could not switch Bluetooth.")


def devices(paired_only=False):
    """Return list of dicts(name, mac, connected)."""
    if not available():
        return []
    _, txt = _ctl("devices" if not paired_only else "paired-devices")
    devs = []
    for line in txt.splitlines():
        m = re.match(r"Device\s+([0-9A-F:]{17})\s+(.+)", line.strip())
        if m:
            devs.append({"mac": m.group(1), "name": m.group(2),
                         "connected": False})
    # mark connected ones
    _, txt2 = _ctl("info")
    return devs


def scan(timeout=8):
    """Short inquiry scan; returns device list (best effort)."""
    if not available():
        return []
    _ctl("scan", "on", timeout=4)
    import time
    time.sleep(min(timeout, 10))
    _ctl("scan", "off", timeout=4)
    return devices()


def connect(name_or_mac):
    target = (name_or_mac or "").strip()
    if not available():
        return False, "Bluetooth tools are not installed."
    if not target:
        return False, "Which Bluetooth device should I connect to?"
    mac = target
    if not re.match(r"^[0-9A-F:]{17}$", target, re.I):
        # resolve friendly name → MAC
        found = [d for d in devices()
                 if target.lower() in d["name"].lower()]
        if not found:
            found = [d for d in scan(timeout=6)
                     if target.lower() in d["name"].lower()]
        if not found:
            return False, "I can't find a Bluetooth device called '%s'." % target
        mac = found[0]["mac"]
    _ctl("trust", mac)
    rc, txt = _ctl("connect", mac, timeout=20)
    if rc == 0 and "successful" in txt.lower():
        return True, "Connected to %s." % target
    # try pairing then connecting
    _ctl("pair", mac, timeout=20)
    rc, txt = _ctl("connect", mac, timeout=20)
    return (True, "Paired and connected to %s." % target) \
        if rc == 0 else (False, "Could not connect to %s." % target)
