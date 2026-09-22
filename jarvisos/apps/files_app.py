#!/usr/bin/env python3
"""jarvis-files — futuristic but real file manager (GTK3).

Sidebar, navigation, copy/cut/paste, rename, new folder, trash, search,
sorting, previews, keyboard navigation. .txt/.md open in jarvis-editor.
"""
import os
import shutil
import subprocess
import sys

sys.path.insert(0, "/usr/lib/jarvisos")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "jarvis-core"))

try:
    import gi
    gi.require_version("Gtk", "3.0")
    from gi.repository import Gtk, Gdk, GdkPixbuf, GLib
    HAVE_GTK = True
except (ImportError, ValueError):
    HAVE_GTK = False

try:
    from jarvis.control import filesops as F
except ImportError:  # pragma: no cover
    F = None

PLACES = [("Home", "home"), ("Documents", "documents"),
          ("Downloads", "downloads"), ("Pictures", "pictures"),
          ("Music", "music"), ("Videos", "videos"), ("Trash", "trash")]

CSS = b"""
.jarvis-win { background-color: #060f1c; }
.jarvis-win * { color: #cfeeff; }
.jarvis-title { color: #c8f4ff; font-size: 15px; letter-spacing: 6px; }
.jarvis-bar { background-color: rgba(53,224,255,0.08); }
"""


class Browser(Gtk.Window):
    def __init__(self, start=None):
        super().__init__(title="JARVIS Files")
        self.set_default_size(960, 600)
        css = Gtk.CssProvider()
        css.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(), css,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        self.get_style_context().add_class("jarvis-win")
        self.history, self.future = [], []
        self.clipboard, self.clip_cut = [], False
        self.current = os.path.abspath(os.path.expanduser(
            start or "~"))

        # toolbar
        bar = Gtk.Box(spacing=6)
        bar.get_style_context().add_class("jarvis-bar")
        bar.set_border_width(6)
        for label, cb in (("◀", self._back), ("▶", self._forward),
                          ("▲", self._up), ("＋ Folder", self._new_folder),
                          ("🔍", None)):
            btn = Gtk.Button(label=label)
            if cb:
                btn.connect("clicked", cb)
            else:
                btn.connect("clicked", lambda b: self.search.grab_focus())
            bar.pack_start(btn, False, False, 0)
        self.path_entry = Gtk.Entry()
        self.path_entry.connect("activate", self._on_path)
        bar.pack_start(self.path_entry, True, True, 0)
        self.search = Gtk.SearchEntry()
        self.search.set_placeholder_text("Search here…")
        self.search.connect("search-changed", lambda e: self._list())
        bar.pack_start(self.search, False, False, 0)

        # sidebar
        self.places = Gtk.ListBox()
        for label, key in PLACES:
            row = Gtk.Label(label="  " + label, xalign=0)
            box = Gtk.ListBoxRow()
            box.add(row)
            box.place_key = key
            self.places.add(box)
        self.places.connect("row-selected", self._on_place)
        side = Gtk.ScrolledWindow()
        side.set_size_request(150, -1)
        side.add(self.places)

        # main listing
        self.store = Gtk.ListStore(str, str, str, str)  # icon,name,size,full
        self.tree = Gtk.TreeView(model=self.store)
        for i, title in enumerate((" ", "Name", "Size")):
            col = Gtk.TreeViewColumn(title, Gtk.CellRendererText(), text=i)
            col.set_sort_column_id(i + 1 if i else 1)
            self.tree.append_column(col)
        self.tree.connect("row-activated", self._on_open)
        self.tree.connect("button-press-event", self._on_right_click)
        self.connect("key-press-event", self._on_key)
        mid = Gtk.ScrolledWindow()
        mid.set_vexpand(True)
        mid.add(self.tree)

        # preview
        self.preview = Gtk.Label(label="")
        self.preview.set_line_wrap(True)
        self.preview.set_size_request(220, -1)
        self.preview.set_valign(Gtk.Align.START)
        self.tree.get_selection().connect("changed", self._on_select)
        prev_scroll = Gtk.ScrolledWindow()
        prev_scroll.add(self.preview)

        paned = Gtk.Paned()
        paned.pack1(side, False, False)
        paned.pack2(mid, True, False)
        paned2 = Gtk.Paned()
        paned2.pack1(paned, True, False)
        paned2.pack2(prev_scroll, False, False)

        self.status = Gtk.Label(label="", xalign=0)
        title = Gtk.Label(label="J A R V I S   F I L E S")
        title.get_style_context().add_class("jarvis-title")

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        root.pack_start(title, False, False, 4)
        root.pack_start(bar, False, False, 0)
        root.pack_start(paned2, True, True, 0)
        root.pack_start(self.status, False, False, 4)
        self.add(root)
        self._list()

    # -- listing ---------------------------------------------------------
    def _list(self):
        self.store.clear()
        query = self.search.get_text().strip().lower()
        try:
            names = sorted(os.listdir(self.current),
                           key=lambda n: (not os.path.isdir(
                               os.path.join(self.current, n)), n.lower()))
        except OSError:
            names = []
        shown = 0
        for name in names:
            if query and query not in name.lower():
                continue
            full = os.path.join(self.current, name)
            isdir = os.path.isdir(full)
            size = ""
            if not isdir:
                try:
                    size = "%d KB" % (os.path.getsize(full) // 1024 + 1)
                except OSError:
                    pass
            self.store.append(["📁" if isdir else "📄", name, size, full])
            shown += 1
        self.path_entry.set_text(self.current)
        self.status.set_text("%d items — %s" % (shown, self.current))

    def _go(self, path):
        path = os.path.abspath(path)
        if path != self.current and os.path.isdir(path):
            self.history.append(self.current)
            self.future.clear()
            self.current = path
            self.search.set_text("")
            self._list()

    def _selected(self):
        model, rows = self.tree.get_selection().get_selected_rows()
        return [model[r][3] for r in rows]

    # -- actions -----------------------------------------------------------
    def _on_open(self, _tree, path, _col):
        full = self.store[path][3]
        if os.path.isdir(full):
            self._go(full)
        else:
            self._launch(full)

    def _launch(self, full):
        ext = os.path.splitext(full)[1].lower()
        if ext in (".txt", ".md", ".json", ".py", ".sh", ".log", ".ini",
                   ".cfg", ".csv"):
            argv = ["jarvis-editor", full]
        else:
            argv = ["xdg-open", full]
        try:
            subprocess.Popen(argv, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL,
                             stdin=subprocess.DEVNULL,
                             start_new_session=True)
        except OSError:
            self.status.set_text("Could not open %s" % full)

    def _back(self, _b):
        if self.history:
            self.future.append(self.current)
            self.current = self.history.pop()
            self._list()

    def _forward(self, _b):
        if self.future:
            self.history.append(self.current)
            self.current = self.future.pop()
            self._list()

    def _up(self, _b):
        parent = os.path.dirname(self.current)
        if parent != self.current:
            self._go(parent)

    def _on_path(self, entry):
        path = os.path.abspath(os.path.expanduser(entry.get_text()))
        if os.path.isdir(path):
            self._go(path)
        else:
            entry.set_text(self.current)

    def _on_place(self, _box, row):
        if row is not None and F is not None:
            self._go(F.folder_path(row.place_key))

    def _new_folder(self, _b):
        dlg = Gtk.Dialog(title="New folder", transient_for=self, flags=0)
        dlg.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
                        Gtk.STOCK_OK, Gtk.ResponseType.OK)
        entry = Gtk.Entry()
        entry.set_text("New Folder")
        dlg.get_content_area().pack_start(entry, True, True, 8)
        dlg.show_all()
        if dlg.run() == Gtk.ResponseType.OK and F is not None:
            ok, msg = F.new_folder(entry.get_text(), parent=self.current)
            self.status.set_text(msg)
            self._list()
        dlg.destroy()

    def _rename(self):
        sel = self._selected()
        if len(sel) != 1:
            return
        dlg = Gtk.Dialog(title="Rename", transient_for=self, flags=0)
        dlg.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
                        Gtk.STOCK_OK, Gtk.ResponseType.OK)
        entry = Gtk.Entry()
        entry.set_text(os.path.basename(sel[0]))
        dlg.get_content_area().pack_start(entry, True, True, 8)
        dlg.show_all()
        if dlg.run() == Gtk.ResponseType.OK:
            dest = os.path.join(os.path.dirname(sel[0]), entry.get_text())
            try:
                os.rename(sel[0], dest)
            except OSError:
                self.status.set_text("Rename failed.")
            self._list()
        dlg.destroy()

    def _copy(self, cut=False):
        self.clipboard, self.clip_cut = self._selected(), cut
        self.status.set_text("%d item(s) %s." % (
            len(self.clipboard), "cut" if cut else "copied"))

    def _paste(self):
        for src in self.clipboard:
            dest = os.path.join(self.current, os.path.basename(src))
            if os.path.abspath(src) == dest:
                continue
            try:
                if os.path.isdir(src):
                    shutil.copytree(src, dest) if not self.clip_cut else \
                        shutil.move(src, dest)
                else:
                    shutil.copy2(src, dest) if not self.clip_cut else \
                        shutil.move(src, dest)
            except (OSError, shutil.Error):
                self.status.set_text("Paste failed for %s." %
                                     os.path.basename(src))
        if self.clip_cut:
            self.clipboard = []
        self._list()

    def _trash(self):
        if F is None:
            return
        for src in self._selected():
            F.move_to_trash(src)
        self._list()

    def _on_right_click(self, _tree, event):
        if event.button != 3:
            return False
        menu = Gtk.Menu()
        for label, cb in (("Open", lambda m: [self._launch(s) for s in
                                              self._selected()][:1]),
                          ("Copy", lambda m: self._copy(False)),
                          ("Cut", lambda m: self._copy(True)),
                          ("Paste", lambda m: self._paste()),
                          ("Rename", lambda m: self._rename()),
                          ("Move to trash", lambda m: self._trash())):
            item = Gtk.MenuItem(label=label)
            item.connect("activate", cb)
            menu.append(item)
        menu.show_all()
        menu.popup_at_pointer(event)
        return True

    def _on_key(self, _w, event):
        ctrl = event.state & Gdk.ModifierType.CONTROL_MASK
        key = Gdk.keyval_name(event.keyval)
        if ctrl and key == "c":
            self._copy(False)
        elif ctrl and key == "x":
            self._copy(True)
        elif ctrl and key == "v":
            self._paste()
        elif key == "Delete":
            self._trash()
        elif key == "F2":
            self._rename()
        elif key == "BackSpace":
            self._up(None)
        elif key == "Home":
            self._go(os.path.expanduser("~"))
        else:
            return False
        return True

    def _on_select(self, selection):
        model, rows = selection.get_selected_rows()
        if not rows:
            self.preview.set_text("")
            return
        full = model[rows[0]][3]
        if os.path.isdir(full):
            try:
                n = len(os.listdir(full))
            except OSError:
                n = 0
            self.preview.set_text("Folder\n%d items" % n)
            return
        ext = os.path.splitext(full)[1].lower()
        if ext in (".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"):
            try:
                pix = GdkPixbuf.Pixbuf.new_from_file_at_size(full, 200, 200)
                self.preview.set_text("Image\n%sx%s" % (pix.get_width(),
                                                        pix.get_height()))
            except GLib.Error:
                self.preview.set_text("Image (unreadable)")
            return
        try:
            with open(full, encoding="utf-8", errors="replace") as fh:
                head = "".join([fh.readline() for _ in range(24)])
            self.preview.set_text(head[:1200] or "(empty file)")
        except OSError:
            self.preview.set_text("(binary file)")


def main():
    if not HAVE_GTK:
        print("jarvis-files needs GTK3.", file=sys.stderr)
        return 1
    start = sys.argv[1] if len(sys.argv) > 1 else None
    win = Browser(start=start)
    win.connect("destroy", Gtk.main_quit)
    win.show_all()
    Gtk.main()
    return 0


if __name__ == "__main__":
    sys.exit(main())
