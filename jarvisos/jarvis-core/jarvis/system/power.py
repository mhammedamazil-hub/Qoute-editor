"""Power & session: lock, suspend, reboot, shutdown, logout."""
from __future__ import annotations

from . import _sh


def lock():
    # lightdm lock → dm-tool; fallbacks for robustness
    for argv in (["dm-tool", "lock"],
                ["loginctl", "lock-session"],
                ["slock"]):
        if _sh.have(argv[0]):
            rc, _ = _sh.run(argv)
            if rc == 0 or argv[0] == "slock":
                return True, "Screen locked."
    return False, "Could not lock the screen."


def suspend():
    if _sh.have("systemctl"):
        _sh.run(["systemctl", "suspend"])
        return True, "Suspending."
    return False, "Suspend is not available."


def reboot():
    if _sh.have("systemctl"):
        _sh.run(["systemctl", "reboot"])
        return True, "Rebooting."
    return False, "Reboot is not available."


def shutdown():
    if _sh.have("systemctl"):
        _sh.run(["systemctl", "poweroff"])
        return True, "Shutting down."
    return False, "Shutdown is not available."


def logout():
    if _sh.have("openbox"):
        _sh.run(["openbox", "--exit"])
        return True, "Logging out."
    if _sh.have("loginctl"):
        _sh.run(["loginctl", "terminate-user", "jarvis"])
        return True, "Logging out."
    return False, "Logout is not available."
