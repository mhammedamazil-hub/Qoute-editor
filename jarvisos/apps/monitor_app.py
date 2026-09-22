#!/usr/bin/env python3
"""jarvis-monitor — lightweight system monitor (GTK3).

CPU/RAM/swap/disk/network/battery/temperature + top processes.
Polls cheap /proc readers every 2 s; the monitor itself stays tiny.
"""
import os
import sys

sys.path.insert(0, "/usr/lib/jarvisos")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "jarvis-core"))

try:
    import gi
    gi.require_version("Gtk", "3.0")
    from gi.repository import Gtk, Gdk, GLib
    HAVE_GTK = True
except (ImportError, ValueError):
    HAVE_GTK = False

from jarvis.system import stats as S  # noqa: E402

CSS = b""".jarvis-win { background-color: #060f1c; }
.jarvis-win * { color: #cfeeff; font-family: monospace; }
.jarvis-title { color: #c8f4ff; font-size: 14px; letter-spacing: 6px; }"""


class Monitor(Gtk.Window):
    def __init__(self):
        super().__init__(title="JARVIS System Monitor")
        self.set_default_size(560, 520)
        css = Gtk.CssProvider()
        css.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(), css,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        self.get_style_context().add_class("jarvis-win")
        self.bars = {}
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        root.set_border_width(10)
        title = Gtk.Label(label="J A R V I S   M O N I T O R")
        title.get_style_context().add_class("jarvis-title")
        root.pack_start(title, False, False, 2)
        for key, label in (("cpu", "CPU"), ("ram", "RAM"), ("swap", "Swap"),
                           ("disk", "Disk /")):
            row = Gtk.Box(spacing=8)
            lab = Gtk.Label(label="%-6s" % label, xalign=0)
            lab.set_size_request(60, -1)
            bar = Gtk.ProgressBar()
            bar.set_show_text(True)
            bar.set_hexpand(True)
            row.pack_start(lab, False, False, 0)
            row.pack_start(bar, True, True, 0)
            root.pack_start(row, False, False, 0)
            self.bars[key] = bar
        self.info = Gtk.Label(label="", xalign=0)
        root.pack_start(self.info, False, False, 4)
        root.pack_start(Gtk.Label(label="TOP PROCESSES (by memory)",
                                  xalign=0), False, False, 0)
        self.store = Gtk.ListStore(int, str, float)
        tree = Gtk.TreeView(model=self.store)
        for i, t in enumerate(("PID", "Name", "MB")):
            tree.append_column(Gtk.TreeViewColumn(
                t, Gtk.CellRendererText(), text=i))
        scroll = Gtk.ScrolledWindow()
        scroll.set_vexpand(True)
        scroll.add(tree)
        root.pack_start(scroll, True, True, 0)
        self.add(root)
        self._refresh()
        GLib.timeout_add(2000, self._tick)

    def _tick(self):
        self._refresh()
        return True

    def _refresh(self):
        cpu = S.cpu_percent(interval=0.05)
        mem = S.mem()
        disk = S.disk("/")
        swap_pct = (100.0 * mem["swap_used_mb"] / mem["swap_total_mb"]
                    if mem["swap_total_mb"] else 0.0)
        self.bars["cpu"].set_fraction(cpu / 100)
        self.bars["cpu"].set_text("%.1f%%" % cpu)
        self.bars["ram"].set_fraction(mem["percent"] / 100)
        self.bars["ram"].set_text("%d/%d MB" % (mem["used_mb"],
                                                mem["total_mb"]))
        self.bars["swap"].set_fraction(swap_pct / 100)
        self.bars["swap"].set_text("%d/%d MB" % (mem["swap_used_mb"],
                                                 mem["swap_total_mb"]))
        self.bars["disk"].set_fraction(disk["percent"] / 100)
        self.bars["disk"].set_text("%.1f/%.1f GB" % (disk["used_gb"],
                                                     disk["total_gb"]))
        batt = S.battery()
        temp = S.temperature()
        self.info.set_text("battery: %s   temp: %s   load: %s" % (
            "%d%% (%s)" % (batt["percent"], batt["state"]) if batt else "--",
            "%s°C" % temp if temp is not None else "--",
            " ".join(map(str, S.loadavg()))))
        self.store.clear()
        for proc in S.top_processes(14):
            self.store.append([proc["pid"], proc["name"][:32],
                               proc["rss_mb"]])


def main():
    if not HAVE_GTK:
        print("jarvis-monitor needs GTK3.", file=sys.stderr)
        return 1
    win = Monitor()
    win.connect("destroy", Gtk.main_quit)
    win.show_all()
    Gtk.main()
    return 0


if __name__ == "__main__":
    sys.exit(main())
