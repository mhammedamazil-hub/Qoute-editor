"""Audio via PipeWire (wpctl) → PulseAudio (pactl) → ALSA (amixer)."""
from __future__ import annotations

import re

from . import _sh


def _backend():
    if _sh.have("wpctl"):
        return "wpctl"
    if _sh.have("pactl"):
        return "pactl"
    if _sh.have("amixer"):
        return "amixer"
    return ""


def available():
    return bool(_backend())


def volume():
    """Return (percent, muted)."""
    be = _backend()
    if be == "wpctl":
        _, txt = _sh.run(["wpctl", "get-volume", "@DEFAULT_AUDIO_SINK@"])
        m = re.search(r"(\d+\.\d+)", txt)
        pct = int(float(m.group(1)) * 100) if m else 0
        return pct, "[MUTED]" in txt
    if be == "pactl":
        _, txt = _sh.run(["pactl", "get-sink-volume", "@DEFAULT_SINK@"])
        m = re.search(r"(\d+)%", txt)
        pct = int(m.group(1)) if m else 0
        _, txt2 = _sh.run(["pactl", "get-sink-mute", "@DEFAULT_SINK@"])
        return pct, txt2.strip().lower().endswith("yes")
    if be == "amixer":
        _, txt = _sh.run(["amixer", "get", "Master"])
        m = re.search(r"\[(\d+)%\].*\[(on|off)\]", txt)
        if m:
            return int(m.group(1)), m.group(2) == "off"
    return 0, False


def set_volume(level):
    level = max(0, min(100, int(level)))
    be = _backend()
    if be == "wpctl":
        rc, _ = _sh.run(["wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@",
                         "%d%%" % level])
    elif be == "pactl":
        rc, _ = _sh.run(["pactl", "set-sink-volume", "@DEFAULT_SINK@",
                         "%d%%" % level])
    elif be == "amixer":
        rc, _ = _sh.run(["amixer", "set", "Master", "%d%%" % level])
    else:
        return False, "No audio control tool found."
    return (True, "Volume %d%%." % level) if rc == 0 else \
        (False, "Could not set volume.")


def volume_step(delta):
    pct, _ = volume()
    return set_volume(pct + delta)


def mute(on=True):
    be = _backend()
    if be == "wpctl":
        rc, _ = _sh.run(["wpctl", "set-mute", "@DEFAULT_AUDIO_SINK@",
                         "1" if on else "0"])
    elif be == "pactl":
        rc, _ = _sh.run(["pactl", "set-sink-mute", "@DEFAULT_SINK@",
                         "1" if on else "0"])
    elif be == "amixer":
        rc, _ = _sh.run(["amixer", "set", "Master",
                         "mute" if on else "unmute"])
    else:
        return False, "No audio control tool found."
    return (True, "Muted." if on else "Unmuted.") if rc == 0 else \
        (False, "Could not change mute state.")


def mic_mute_toggle():
    be = _backend()
    if be == "wpctl":
        rc, _ = _sh.run(["wpctl", "set-mute", "@DEFAULT_AUDIO_SOURCE@",
                         "toggle"])
    elif be == "pactl":
        _, src = _sh.run(["pactl", "get-default-source"])
        rc, _ = _sh.run(["pactl", "set-source-mute", src or "@DEFAULT_SOURCE@",
                         "toggle"])
    else:
        return False, "Microphone control is not available."
    return (True, "Microphone mute toggled.") if rc == 0 else \
        (False, "Could not toggle the microphone.")


def microphones():
    """List input sources (best effort)."""
    be = _backend()
    if be == "wpctl":
        _, txt = _sh.run(["wpctl", "status"])
        return [l.strip() for l in txt.splitlines()
                if "Audio/Source" in l or " microphone" in l.lower()][:8]
    if be == "pactl":
        _, txt = _sh.run(["pactl", "list", "short", "sources"])
        return txt.splitlines()[:8]
    return []
