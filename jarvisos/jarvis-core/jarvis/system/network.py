"""Wi-Fi / networking via NetworkManager (nmcli), with /sys fallbacks."""
from __future__ import annotations

import os
import re

from . import _sh


def available():
    return _sh.have("nmcli")


def status():
    """Return dict(online, wifi_on, ssid, signal, ip)."""
    out = {"online": False, "wifi_on": False, "ssid": "",
           "signal": 0, "ip": ""}
    if not available():
        out["online"] = os.path.exists("/sys/class/net/wlan0") or \
            os.path.exists("/sys/class/net/eth0")
        return out
    rc, txt = _sh.run(["nmcli", "-t", "-f", "WIFI", "radio"])
    out["wifi_on"] = txt.strip().lower() == "enabled"
    rc, txt = _sh.run(["nmcli", "-t", "-f",
                       "ACTIVE,SSID,SIGNAL", "device", "wifi", "list",
                       "--rescan", "no"])
    for line in txt.splitlines():
        parts = line.split(":")
        if len(parts) >= 3 and parts[0].lower().startswith("yes"):
            out["ssid"] = parts[1]
            try:
                out["signal"] = int(parts[2])
            except ValueError:
                pass
            out["online"] = True
    rc, txt = _sh.run(["nmcli", "-t", "-f", "IP4.ADDRESS", "device", "show",
                       "--active"])
    m = re.search(r"(\d+\.\d+\.\d+\.\d+)", txt)
    if m:
        out["ip"] = m.group(1)
        out["online"] = True
    return out


def wifi(on):
    if not available():
        return False, "NetworkManager (nmcli) is not available."
    rc, _ = _sh.run(["nmcli", "radio", "wifi", "on" if on else "off"])
    return (True, "Wi-Fi on." if on else "Wi-Fi off.") if rc == 0 else \
        (False, "Could not switch Wi-Fi (radio control blocked?).")


def list_networks():
    if not available():
        return []
    _, txt = _sh.run(
        ["nmcli", "-t", "-f", "SSID,SIGNAL,SECURITY", "device", "wifi",
         "list", "--rescan", "yes"], timeout=20)
    nets = []
    seen = set()
    for line in txt.splitlines():
        parts = line.split(":")
        if len(parts) >= 2 and parts[0] and parts[0] not in seen:
            seen.add(parts[0])
            try:
                sig = int(parts[1])
            except ValueError:
                sig = 0
            nets.append({"ssid": parts[0], "signal": sig,
                         "security": parts[2] if len(parts) > 2 else ""})
    return sorted(nets, key=lambda n: n["signal"], reverse=True)[:20]


def connect(ssid, password=None):
    """Connect to SSID. Returns (ok, message)."""
    ssid = (ssid or "").strip()
    if not ssid:
        return False, "Which Wi-Fi network should I connect to?"
    if not available():
        return False, "NetworkManager (nmcli) is not available."
    # First try known connection (no password needed).
    rc, _ = _sh.run(["nmcli", "connection", "up", ssid], timeout=25)
    if rc == 0:
        return True, "Connected to %s." % ssid
    argv = ["nmcli", "device", "wifi", "connect", ssid]
    if password:
        argv += ["password", password]
    rc, txt = _sh.run(argv, timeout=30)
    if rc == 0:
        return True, "Connected to %s." % ssid
    if "password" in txt.lower() or "secrets" in txt.lower():
        return False, "That network needs a password — " \
            "please connect once via the network menu."
    return False, "Could not connect to %s." % ssid


def disconnect():
    if not available():
        return False, "NetworkManager (nmcli) is not available."
    st = status()
    if not st["ssid"]:
        return True, "Wi-Fi is already disconnected."
    rc, _ = _sh.run(["nmcli", "connection", "down", st["ssid"]])
    return (True, "Disconnected from %s." % st["ssid"]) if rc == 0 else \
        (False, "Could not disconnect.")
