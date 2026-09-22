"""Left launcher, right status panel, bottom dock (one file, three windows).

All three are lightweight: launcher/dock are static buttons; the status
panel pollscheap /proc stats + daemon status every few seconds.
"""
from __future__ import annotations

import os
import threading

try:
    import gi
    gi.require_version("Gtk", "3.0")
    from gi.repository import Gtk, GLib, Gdk
    HAVE_GTK = True
except (ImportError, ValueError):
    HAVE_GTK = False

import client  # noqa: E402

LAUNCHERS = [
    ("Files", "files", "open files"),
    ("Terminal", "terminal", "open terminal"),
    ("VS Code", "vscode", "open vs code"),
    ("Brave", "brave", "open brave"),
    ("Discord", "discord", "open discord"),
    ("Blender", "blender", "open blender"),
    ("Settings", "settings", "open settings"),
]

PANEL_CSS = b"""
.jarvis-panel { background-color: rgba(4, 12, 24, 0.66); border-radius: 14px;
  border: 1px solid rgba(53, 224, 255, 0.28); }
.jarvis-app-btn { background: transparent; border: none; color: #c8f4ff;
  font-size: 12px; padding: 10px 6px; }
.jarvis-app-btn:hover { background: rgba(53, 224, 255, 0.15); }
.jarvis-stat { color: #9fe8ff; font-size: 12px; font-family: monospace; }
.jarvis-stat-hi { color: #ffb35c; }
.jarvis-head { color: #c8f4ff; font-size: 13px; font-weight: bold; }
"""


def _apply_css():
    if not HAVE_GTK:
        return
    css = Gtk.CssProvider()
    css.load_from_data(PANEL_CSS)
    Gtk.StyleContext.add_provider_for_screen(
        Gdk.Screen.get_default(), css,
        Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)


if HAVE_GTK:

    class _Frameless(Gtk.Window):
        def __init__(self):
            super().__init__(title="jarvis-panel")
            self.set_decorated(False)
            self.set_keep_below(True)
            self.set_skip_taskbar_hint(True)
            self.set_skip_pager_hint(True)
            self.set_type_hint(Gdk.WindowTypeHint.DOCK)
            screen = self.get_screen()
            visual = screen.get_rgba_visual()
            if visual:
                self.set_visual(visual)
            _apply_css()

    class LauncherBar(_Frameless):
        """Left edge: one-click app launcher."""

        def __init__(self):
            super().__init__()
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            box.set_border_width(8)
            for label, _app, command in LAUNCHERS:
                btn = Gtk.Button(label=label)
                btn.get_style_context().add_class("jarvis-app-btn")
                btn.connect("clicked", self._launch, command)
                box.pack_start(btn, False, False, 0)
            frame = Gtk.Box()
            frame.get_style_context().add_class("jarvis-panel")
            frame.pack_start(box, True, True, 0)
            self.add(frame)

        def _launch(self, _btn, command):
            threading.Thread(target=client.text_command, args=(command,),
                             daemon=True).start()

    class StatusPanel(_Frameless):
        """Right edge: CPU/RAM/Wi-Fi/BT/battery + notifications + status."""

        def __init__(self, interval_ms=2500):
            super().__init__()
            self.labels = {}
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
            box.set_border_width(10)
            head = Gtk.Label(label="SYSTEM")
            head.get_style_context().add_class("jarvis-head")
            box.pack_start(head, False, False, 0)
            for key in ("cpu", "ram", "disk", "wifi", "bluetooth",
                        "battery", "temp"):
                lab = Gtk.Label(label="%s: …" % key.upper())
                lab.set_xalign(0.0)
                lab.get_style_context().add_class("jarvis-stat")
                box.pack_start(lab, False, False, 0)
                self.labels[key] = lab
            sep = Gtk.Separator()
            box.pack_start(sep, False, False, 4)
            head2 = Gtk.Label(label="JARVIS")
            head2.get_style_context().add_class("jarvis-head")
            box.pack_start(head2, False, False, 0)
            self.status_lab = Gtk.Label(label="core: …")
            self.status_lab.set_xalign(0.0)
            self.status_lab.get_style_context().add_class("jarvis-stat")
            box.pack_start(self.status_lab, False, False, 0)
            self.notif_lab = Gtk.Label(label="")
            self.notif_lab.set_xalign(0.0)
            self.notif_lab.set_line_wrap(True)
            self.notif_lab.set_max_width_chars(26)
            self.notif_lab.get_style_context().add_class("jarvis-stat")
            box.pack_start(self.notif_lab, False, False, 0)
            frame = Gtk.Box()
            frame.get_style_context().add_class("jarvis-panel")
            frame.pack_start(box, True, True, 0)
            self.add(frame)
            self._refresh()
            GLib.timeout_add(interval_ms, self._tick)

        def _tick(self):
            threading.Thread(target=self._refresh_async, daemon=True).start()
            return True

        def _refresh_async(self):
            data = client.stats().get("data", {})
            status = client.status()
            GLib.idle_add(self._paint, data, status)

        def _refresh(self):
            self._refresh_async()

        def _paint(self, data, status):
            if not data:
                self.status_lab.set_text("core: offline")
                return False
            self.labels["cpu"].set_text("CPU  %s%%" % data.get(
                "cpu_percent", "?"))
            self.labels["ram"].set_text("RAM  %s%% (%s/%s MB)" % (
                data.get("mem_percent", "?"), data.get("mem_used_mb", "?"),
                data.get("mem_total_mb", "?")))
            self.labels["disk"].set_text("DISK %s%% (%s GB free)" % (
                data.get("disk_percent", "?"), data.get("disk_free_gb", "?")))
            wifi = "off"
            try:
                from jarvis.system import network as _net
                st = _net.status()
                wifi = st["ssid"] or ("on" if st["wifi_on"] else "off")
            except Exception:
                pass
            self.labels["wifi"].set_text("WIFI %s" % wifi)
            bt = "off"
            try:
                from jarvis.system import bluetooth as _bt
                bt = "on" if _bt.powered() else "off"
            except Exception:
                pass
            self.labels["bluetooth"].set_text("BT   %s" % bt)
            batt = data.get("battery_percent")
            self.labels["battery"].set_text(
                "BATT %s%%" % batt if batt is not None else "BATT --")
            temp = data.get("temp_c")
            self.labels["temp"].set_text(
                "TEMP %s°C" % temp if temp is not None else "TEMP --")
            ai = "AI: %s" % (",".join(status.get("ai_providers", []))
                             or "offline")
            self.status_lab.set_text("core: online · %s" % ai)
            try:
                log = os.path.join(os.path.expanduser("~"), ".local",
                                   "share", "jarvisos", "notifications.log")
                with open(log, encoding="utf-8") as fh:
                    lines = fh.readlines()[-2:]
                self.notif_lab.set_text("".join(lines)[-160:])
            except OSError:
                pass
            return False

    class Dock(_Frameless):
        """Bottom center: quick actions + running-window shortcuts."""

        def __init__(self):
            super().__init__()
            box = Gtk.Box(spacing=4)
            box.set_border_width(8)
            for label, command in (
                    ("◉ Command", None), ("🎙 Voice", "voice"),
                    ("▦ Apps", "open app manager"), ("🔒 Lock", "lock the screen"),
                    ("⏻ Power", None)):
                btn = Gtk.Button(label=label)
                btn.get_style_context().add_class("jarvis-app-btn")
                if command == "voice":
                    btn.connect("clicked", self._voice)
                elif command:
                    btn.connect("clicked", self._run, command)
                else:
                    btn.connect("clicked", self._focus_hud
                                if label.startswith("◉") else self._power)
                box.pack_start(btn, False, False, 0)
            frame = Gtk.Box()
            frame.get_style_context().add_class("jarvis-panel")
            frame.pack_start(box, True, True, 0)
            self.add(frame)
            self._hud = None

        def attach_hud(self, hud):
            self._hud = hud

        def _run(self, _btn, command):
            threading.Thread(target=client.text_command, args=(command,),
                             daemon=True).start()

        def _voice(self, _btn):
            import subprocess
            subprocess.Popen(["jarvis-listen", "--seconds", "6"],
                             stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL,
                             stdin=subprocess.DEVNULL,
                             start_new_session=True)

        def _focus_hud(self, _btn):
            if self._hud is not None:
                self._hud.present()
                self._hud.entry.grab_focus()

        def _power(self, _btn):
            threading.Thread(
                target=client.text_command, args=("shut down the computer",),
                daemon=True).start()

else:  # pragma: no cover

    class LauncherBar:  # type: ignore
        def __init__(self, *a, **k):
            raise RuntimeError("GTK3 is required")

    class StatusPanel:  # type: ignore
        def __init__(self, *a, **k):
            raise RuntimeError("GTK3 is required")

    class Dock:  # type: ignore
        def __init__(self, *a, **k):
            raise RuntimeError("GTK3 is required")
