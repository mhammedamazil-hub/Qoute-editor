"""Assemble the JARVIS desktop shell: HUD + launcher + status + dock.

Performance policy: when total RAM < 5 GB (or forced by config /
`jarvis.performance=1` on the kernel cmdline) the shell runs static:
no core animation, no transparency, 5 s status polling.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, "/usr/lib/jarvisos")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "jarvis-core"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    import gi
    gi.require_version("Gtk", "3.0")
    from gi.repository import Gtk, Gdk
    HAVE_GTK = True
except (ImportError, ValueError):
    HAVE_GTK = False


def performance_mode(config=None):
    """True when the shell should minimize effects."""
    if config is None:
        try:
            from jarvis.config import get_config
            config = get_config()
        except Exception:
            config = None
    mode = ""
    if config is not None:
        try:
            mode = (config.get("appearance.performance_mode", "auto") or
                    "auto").lower()
        except Exception:
            mode = "auto"
    if mode == "performance":
        return True
    if mode == "cinematic":
        return False
    # auto: kernel flag wins, then RAM size
    try:
        with open("/proc/cmdline", encoding="utf-8") as fh:
            if "jarvis.performance=1" in fh.read():
                return True
    except OSError:
        pass
    try:
        from jarvis.system import stats as _stats
        return _stats.mem()["total_mb"] < 5120
    except Exception:
        return True


def main():
    if not HAVE_GTK:
        print("jarvis-shell needs GTK3 (python3-gi + gir1.2-gtk-3.0).",
              file=sys.stderr)
        return 1
    from hud import HudWindow
    from panels import LauncherBar, StatusPanel, Dock

    perf = performance_mode()
    hud = HudWindow(animated=not perf, transparent=not perf)
    launcher = LauncherBar()
    status = StatusPanel(interval_ms=5000 if perf else 2500)
    dock = Dock()
    dock.attach_hud(hud)

    # placement: launcher left, status right, dock bottom-center, hud center
    display = Gdk.Display.get_default()
    monitor = display.get_primary_monitor() or display.get_monitor(0)
    geo = monitor.get_geometry()
    hud.set_default_size(min(560, geo.width - 40),
                         min(560, geo.height - 40))
    hud.move(geo.x + (geo.width - 560) // 2, geo.y + (geo.height - 560) // 2)
    launcher.move(geo.x + 12, geo.y + (geo.height - 420) // 2)
    status.move(geo.x + geo.width - 232, geo.y + (geo.height - 420) // 2)
    dock.move(geo.x + (geo.width - 420) // 2, geo.y + geo.height - 90)

    for window in (hud, launcher, status, dock):
        window.show_all()
    print("jarvis-shell started (performance=%s)" % perf, flush=True)
    Gtk.main()
    return 0


if __name__ == "__main__":
    sys.exit(main())
