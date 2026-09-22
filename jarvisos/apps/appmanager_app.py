#!/usr/bin/env python3
"""jarvis-appmanager — install on-demand apps (GTK3).

Nothing proprietary is bundled: Debian packages come from apt, vendor apps
(VS Code / Brave / Discord) via their official vendor scripts — always with
explicit confirmation, always in a visible terminal.
"""
import os
import sys
import threading

sys.path.insert(0, "/usr/lib/jarvisos")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "jarvis-core"))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "shell"))

try:
    import gi
    gi.require_version("Gtk", "3.0")
    from gi.repository import Gtk, Gdk, GLib
    HAVE_GTK = True
except (ImportError, ValueError):
    HAVE_GTK = False

from jarvis.control import apps as A  # noqa: E402
import client  # noqa: E402

CSS = b""".jarvis-win { background-color: #060f1c; }
.jarvis-win * { color: #cfeeff; }
.jarvis-title { color: #c8f4ff; font-size: 14px; letter-spacing: 6px; }"""

SHOWCASE = ["vscode", "brave", "discord", "blender", "firefox", "vlc",
            "gimp", "git", "python"]


class Manager(Gtk.Window):
    def __init__(self):
        super().__init__(title="JARVIS App Manager")
        self.set_default_size(560, 480)
        css = Gtk.CssProvider()
        css.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(), css,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        self.get_style_context().add_class("jarvis-win")
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        root.set_border_width(10)
        title = Gtk.Label(label="J A R V I S   A P P S")
        title.get_style_context().add_class("jarvis-title")
        root.pack_start(title, False, False, 2)
        hint = Gtk.Label(
            label="Base ISO stays light — install what you need. "
                  "Or say: 'Jarvis, install Blender.'")
        hint.set_line_wrap(True)
        root.pack_start(hint, False, False, 0)
        self.rows = Gtk.ListBox()
        scroll = Gtk.ScrolledWindow()
        scroll.set_vexpand(True)
        scroll.add(self.rows)
        root.pack_start(scroll, True, True, 0)
        upd = Gtk.Button(label="⟳ Update entire system")
        upd.connect("clicked", self._update)
        root.pack_start(upd, False, False, 0)
        self.status = Gtk.Label(label="", xalign=0)
        self.status.set_line_wrap(True)
        root.pack_start(self.status, False, False, 0)
        self.add(root)
        self._rebuild()

    def _rebuild(self):
        for child in self.rows.get_children():
            self.rows.remove(child)
        for app_id in SHOWCASE:
            meta = A.REGISTRY[app_id]
            installed = A.is_installed(app_id)
            row = Gtk.Box(spacing=8)
            row.set_border_width(6)
            lab = Gtk.Label(label="%s  %s" % (
                meta["name"], "● installed" if installed else "○ not installed"),
                xalign=0)
            lab.set_hexpand(True)
            row.pack_start(lab, True, True, 0)
            if installed:
                btn = Gtk.Button(label="Open")
                btn.connect("clicked", self._open, app_id)
            else:
                btn = Gtk.Button(label="Install")
                btn.connect("clicked", self._install, app_id)
            row.pack_start(btn, False, False, 0)
            container = Gtk.ListBoxRow()
            container.add(row)
            self.rows.add(container)
        self.rows.show_all()

    def _open(self, _b, app_id):
        threading.Thread(target=A.launch, args=(app_id,), daemon=True).start()

    def _install(self, _b, app_id):
        kind, _detail, steps = A.install_plan(app_id)
        label = A.REGISTRY[app_id]["name"]
        if kind == "none":
            self.status.set_text(" ".join(steps))
            return
        dlg = Gtk.MessageDialog(
            transient_for=self, flags=0, message_type=Gtk.MessageType.QUESTION,
            buttons=Gtk.ButtonsType.YES_NO,
            text="Install %s? %s" % (label, " ".join(steps)))
        ok = dlg.run() == Gtk.ResponseType.YES
        dlg.destroy()
        if not ok:
            return
        self.status.set_text("Installing %s — watch the terminal…" % label)

        def _run():
            good, msg = A.install(app_id)
            GLib.idle_add(self._done, good, msg)

        threading.Thread(target=_run, daemon=True).start()

    def _done(self, _good, msg):
        self.status.set_text(msg)
        self._rebuild()
        return False

    def _update(self, _b):
        resp = client.text_command("update the system")
        if resp.get("needs_confirm"):
            dlg = Gtk.MessageDialog(
                transient_for=self, flags=0,
                message_type=Gtk.MessageType.QUESTION,
                buttons=Gtk.ButtonsType.YES_NO,
                text=resp.get("confirm_question", "Update everything?"))
            ok = dlg.run() == Gtk.ResponseType.YES
            dlg.destroy()
            if ok:
                resp = client.confirm(resp["confirm_token"], True)
                self.status.set_text(resp.get("say", ""))
        else:
            self.status.set_text(resp.get("say", ""))


def main():
    if not HAVE_GTK:
        print("jarvis-appmanager needs GTK3.", file=sys.stderr)
        return 1
    win = Manager()
    win.connect("destroy", Gtk.main_quit)
    win.show_all()
    Gtk.main()
    return 0


if __name__ == "__main__":
    sys.exit(main())
