"""Display: brightness, night mode, wallpaper, screenshots, resolution."""
from __future__ import annotations

import datetime
import glob
import os

from . import _sh


def _backlight():
    devs = sorted(glob.glob("/sys/class/backlight/*"))
    return devs[0] if devs else ""


def brightness():
    bl = _backlight()
    if not bl:
        return None
    try:
        with open(os.path.join(bl, "brightness")) as fh:
            cur = int(fh.read().strip())
        with open(os.path.join(bl, "max_brightness")) as fh:
            mx = int(fh.read().strip())
        return int(round(100.0 * cur / mx)) if mx else None
    except (OSError, ValueError):
        return None


def set_brightness(level):
    level = max(1, min(100, int(level)))
    bl = _backlight()
    if not bl:  # desktop without backlight → try xrandr gamma fallback
        if _sh.have("xrandr"):
            g = 0.3 + 0.7 * (level / 100.0)
            rc, _ = _sh.run(["xrandr", "--output",
                             _primary_output(), "--brightness", str(g)])
            return (True, "Brightness %d%%." % level) if rc == 0 else \
                (False, "Could not set brightness.")
        return False, "No adjustable backlight found."
    try:
        with open(os.path.join(bl, "max_brightness")) as fh:
            mx = int(fh.read().strip())
        value = str(int(mx * level / 100))
        # direct write first (works when udev grants video-group access)…
        try:
            with open(os.path.join(bl, "brightness"), "w") as fh:
                fh.write(value)
            return True, "Brightness %d%%." % level
        except OSError:
            pass
        # …then the root helper via sudoers (live + installed systems).
        if _sh.have("jarvis-privileged"):
            prefix = [] if os.geteuid() == 0 else ["sudo", "-n"]
            rc, _ = _sh.run(prefix + ["jarvis-privileged", "backlight",
                                      value])
            return (True, "Brightness %d%%." % level) if rc == 0 else \
                (False, "Could not set brightness.")
        return False, "Could not set brightness (permission denied?)."
    except (OSError, ValueError):
        return False, "Could not set brightness (permission denied?)."


def brightness_step(delta):
    cur = brightness()
    if cur is None:
        return set_brightness(70)
    return set_brightness(cur + delta)


def _primary_output():
    _, txt = _sh.run(["xrandr", "--query"])
    for line in txt.splitlines():
        if " connected primary" in line:
            return line.split()[0]
    for line in txt.splitlines():
        if " connected" in line:
            return line.split()[0]
    return ""


def resolution():
    """Return (width, height) of primary screen, or (0, 0)."""
    if _sh.have("xrandr"):
        _, txt = _sh.run(["xrandr", "--query"])
        import re
        m = re.search(r" connected primary (\d+)x(\d+)", txt)
        if not m:
            m = re.search(r" connected (\d+)x(\d+)", txt)
        if m:
            return int(m.group(1)), int(m.group(2))
    # tkinter fallback (headless-safe: fails → (0,0))
    try:
        import tkinter as tk
        root = tk.Tk()
        root.withdraw()
        w, h = root.winfo_screenwidth(), root.winfo_screenheight()
        root.destroy()
        return w, h
    except Exception:
        return 0, 0


def screenshot(path=None):
    """Take a screenshot, return path or ''. Prefers scrot, then PIL/mss."""
    if path is None:
        pics = os.path.join(os.path.expanduser("~"), "Pictures")
        os.makedirs(pics, exist_ok=True)
        stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        path = os.path.join(pics, "jarvis-screenshot-%s.png" % stamp)
    if _sh.have("scrot"):
        rc, _ = _sh.run(["scrot", path])
        if rc == 0:
            return path
    try:
        from PIL import ImageGrab  # pillow is in the base image
        img = ImageGrab.grab()
        img.save(path)
        return path
    except Exception:
        pass
    try:
        import mss  # optional, installed by chroot hook
        with mss.mss() as sct:
            sct.shot(output=path)
        return path
    except Exception:
        return ""
    return path


def night_mode(on):
    if not _sh.have("redshift"):
        return False, "Night mode needs the 'redshift' package."
    # redshift -O temp sets; -x clears. Manage via pkill for simplicity.
    if on:
        _sh.run(["pkill", "redshift"])
        _sh.run(["redshift", "-O", "3500"])
        return True, "Night mode on."
    _sh.run(["pkill", "redshift"])
    _sh.run(["redshift", "-x"])
    return True, "Night mode off."


def set_wallpaper(path):
    if not os.path.isfile(path):
        return False, "Wallpaper not found: %s" % path
    if _sh.have("feh"):
        _sh.run(["feh", "--bg-fill", path])
        return True, "Wallpaper updated."
    return False, "Wallpaper tool (feh) is not installed."
