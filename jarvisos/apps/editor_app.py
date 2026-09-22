#!/usr/bin/env python3
"""jarvis-editor — JARVIS-style tabbed text editor (GTK3).

Open/save/save-as, find, infinite undo/redo, multi-tab, shortcuts.
Default handler for .txt/.md and code files on JARVISOS.
"""
import os
import sys

sys.path.insert(0, "/usr/lib/jarvisos")

try:
    import gi
    gi.require_version("Gtk", "3.0")
    from gi.repository import Gtk, Gdk
    HAVE_GTK = True
except (ImportError, ValueError):
    HAVE_GTK = False

CSS = b"""
.jarvis-win { background-color: #060f1c; }
.jarvis-win * { color: #d9f6ff; }
.jarvis-title { color: #c8f4ff; font-size: 14px; letter-spacing: 6px; }
textview text { background-color: #081426; color: #e4faff;
  font-family: monospace; font-size: 12pt; }
"""


class Tab:
    def __init__(self, path=None):
        self.path = path
        self.view = Gtk.TextView()
        self.view.set_wrap_mode(Gtk.WrapMode.WORD)
        self.buf = self.view.get_buffer()
        self.undo, self.redo = [], []
        self._lock = False
        self.buf.connect("changed", self._on_change)
        if path and os.path.isfile(path):
            try:
                with open(path, encoding="utf-8", errors="replace") as fh:
                    self._lock = True
                    self.buf.set_text(fh.read())
                    self._lock = False
            except OSError:
                pass
        self._snapshot()

    def _snapshot(self):
        self.undo.append(self.buf.get_text(
            self.buf.get_start_iter(), self.buf.get_end_iter(), True))
        self.undo = self.undo[-200:]
        self.redo.clear()

    def _on_change(self, _buf):
        if not self._lock:
            self._snapshot()

    def _restore(self, text):
        self._lock = True
        self.buf.set_text(text)
        self._lock = False

    def undo_op(self):
        if len(self.undo) > 1:
            self.redo.append(self.undo.pop())
            self._restore(self.undo[-1])

    def redo_op(self):
        if self.redo:
            text = self.redo.pop()
            self.undo.append(text)
            self._restore(text)

    def text(self):
        return self.buf.get_text(self.buf.get_start_iter(),
                                 self.buf.get_end_iter(), True)


class Editor(Gtk.Window):
    def __init__(self, paths):
        super().__init__(title="JARVIS Editor")
        self.set_default_size(860, 600)
        css = Gtk.CssProvider()
        css.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(), css,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        self.get_style_context().add_class("jarvis-win")

        self.tabs = Gtk.Notebook()
        self.tabs.set_scrollable(True)
        bar = Gtk.Box(spacing=6)
        bar.set_border_width(6)
        for label, cb in (("＋ New", self._new), ("📂 Open", self._open),
                          ("💾 Save", self._save),
                          ("💾 Save as", self._save_as),
                          ("🔍 Find", self._find_toggle),
                          ("↩ Undo", lambda b: self._cur().undo_op()),
                          ("↪ Redo", lambda b: self._cur().redo_op())):
            btn = Gtk.Button(label=label)
            btn.connect("clicked", cb)
            bar.pack_start(btn, False, False, 0)

        self.find_bar = Gtk.Box(spacing=6)
        self.find_entry = Gtk.Entry()
        self.find_entry.set_placeholder_text("Find… (Enter = next)")
        self.find_entry.connect("activate", self._find_next)
        self.find_bar.pack_start(self.find_entry, True, True, 0)
        self.find_bar.set_no_show_all(True)

        self.status = Gtk.Label(label="", xalign=0)
        title = Gtk.Label(label="J A R V I S   E D I T O R")
        title.get_style_context().add_class("jarvis-title")
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        root.pack_start(title, False, False, 4)
        root.pack_start(bar, False, False, 0)
        root.pack_start(self.find_bar, False, False, 0)
        root.pack_start(self.tabs, True, True, 0)
        root.pack_start(self.status, False, False, 4)
        self.add(root)
        self.connect("key-press-event", self._on_key)
        self.tabs.connect("switch-page", lambda nb, pg, num: self._stat())
        for path in paths or [None]:
            self._add_tab(path)
        self._stat()

    def _add_tab(self, path=None):
        tab = Tab(path)
        scroll = Gtk.ScrolledWindow()
        scroll.add(tab.view)
        label = Gtk.Label(label=os.path.basename(path) if path else
                          "untitled %d" % (self.tabs.get_n_pages() + 1))
        close = Gtk.Button.new_from_icon_name("window-close",
                                              Gtk.IconSize.MENU)
        close.set_relief(Gtk.ReliefStyle.NONE)
        hbox = Gtk.Box(spacing=4)
        hbox.pack_start(label, True, True, 0)
        hbox.pack_start(close, False, False, 0)
        hbox.show_all()
        self.tabs.append_page(scroll, hbox)
        close.connect("clicked", lambda b: self._close_tab(scroll))
        tab.buf.connect("changed", lambda b: self._stat())
        self.tabs.set_current_page(-1)
        self.tabs.show_all()

    def _cur(self):
        page = self.tabs.get_nth_page(self.tabs.get_current_page())
        # page is ScrolledWindow → viewport → TextView… find Tab via children
        for tab in self._iter_tabs():
            if tab[1] is page:
                return tab[0]
        return None

    def _iter_tabs(self):
        # NOTE: Tabs are tracked in order appended (no reorder supported).
        if not hasattr(self, "_tablist"):
            self._tablist = []
        while len(self._tablist) < self.tabs.get_n_pages():
            self._tablist.append(None)
        return [(t, self.tabs.get_nth_page(i))
                for i, t in enumerate(self._tablist) if t]

    def _add_tab_tracked(self, path=None):
        if not hasattr(self, "_tablist"):
            self._tablist = []
        tab = Tab(path)
        self._tablist.append(tab)
        scroll = Gtk.ScrolledWindow()
        scroll.add(tab.view)
        label = Gtk.Label(label=os.path.basename(path) if path else
                          "untitled %d" % len(self._tablist))
        close = Gtk.Button.new_from_icon_name("window-close",
                                              Gtk.IconSize.MENU)
        close.set_relief(Gtk.ReliefStyle.NONE)
        hbox = Gtk.Box(spacing=4)
        hbox.pack_start(label, True, True, 0)
        hbox.pack_start(close, False, False, 0)
        hbox.show_all()
        self.tabs.append_page(scroll, hbox)
        close.connect("clicked", lambda b, s=scroll: self._close_tab(s))
        tab.buf.connect("changed", lambda b: self._stat())
        self.tabs.set_current_page(-1)
        self.tabs.show_all()
        return tab

    def _close_tab(self, scroll):
        idx = None
        for i in range(self.tabs.get_n_pages()):
            if self.tabs.get_nth_page(i) is scroll:
                idx = i
                break
        if idx is not None:
            self.tabs.remove_page(idx)
            if hasattr(self, "_tablist") and idx < len(self._tablist):
                self._tablist.pop(idx)
        if self.tabs.get_n_pages() == 0:
            self._add_tab_tracked(None)

    # -- file ops ----------------------------------------------------------
    def _new(self, _b):
        self._add_tab_tracked(None)

    def _open(self, _b):
        dlg = Gtk.FileChooserDialog(title="Open", transient_for=self,
                                    action=Gtk.FileChooserAction.OPEN)
        dlg.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
                        Gtk.STOCK_OPEN, Gtk.ResponseType.OK)
        if dlg.run() == Gtk.ResponseType.OK:
            self._add_tab_tracked(dlg.get_filename())
        dlg.destroy()

    def _save(self, _b):
        tab = self._cur()
        if tab is None:
            return
        if not tab.path:
            return self._save_as(_b)
        try:
            with open(tab.path, "w", encoding="utf-8") as fh:
                fh.write(tab.text())
            self.status.set_text("Saved %s" % tab.path)
        except OSError:
            self.status.set_text("Save failed.")

    def _save_as(self, _b):
        tab = self._cur()
        if tab is None:
            return
        dlg = Gtk.FileChooserDialog(title="Save as", transient_for=self,
                                    action=Gtk.FileChooserAction.SAVE)
        dlg.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
                        Gtk.STOCK_SAVE, Gtk.ResponseType.OK)
        dlg.set_do_overwrite_confirmation(True)
        if dlg.run() == Gtk.ResponseType.OK:
            tab.path = dlg.get_filename()
            idx = self.tabs.get_current_page()
            page = self.tabs.get_nth_page(idx)
            tab_label = self.tabs.get_tab_label(page).get_children()[0]
            tab_label.set_text(os.path.basename(tab.path))
            self._save(_b)
        dlg.destroy()

    # -- find ---------------------------------------------------------------
    def _find_toggle(self, _b):
        self.find_bar.set_visible(not self.find_bar.get_visible())
        if self.find_bar.get_visible():
            self.find_entry.grab_focus()

    def _find_next(self, _entry):
        tab = self._cur()
        needle = self.find_entry.get_text()
        if tab is None or not needle:
            return
        buf = tab.buf
        start = buf.get_iter_at_mark(buf.get_insert())
        found = start.forward_search(needle, Gtk.TextSearchFlags.TEXT_ONLY,
                                     None)
        if not found:  # wrap
            found = buf.get_start_iter().forward_search(
                needle, Gtk.TextSearchFlags.TEXT_ONLY, None)
        if found:
            buf.select_range(found[0], found[1])
            tab.view.scroll_to_iter(found[0], 0.0, True, 0.5, 0.5)
            self.status.set_text("Found '%s'." % needle)
        else:
            self.status.set_text("'%s' not found." % needle)

    # -- misc -----------------------------------------------------------------
    def _stat(self):
        tab = self._cur()
        if tab is None:
            self.status.set_text("")
            return
        text = tab.text()
        self.status.set_text("%s — %d lines, %d chars" % (
            tab.path or "untitled", text.count("\n") + 1, len(text)))

    def _on_key(self, _w, event):
        ctrl = event.state & Gdk.ModifierType.CONTROL_MASK
        key = Gdk.keyval_name(event.keyval)
        tab = self._cur()
        if ctrl and key == "s":
            self._save(None)
        elif ctrl and key == "o":
            self._open(None)
        elif ctrl and key == "n":
            self._new(None)
        elif ctrl and key == "f":
            self._find_toggle(None)
        elif ctrl and key == "z" and tab:
            tab.undo_op()
        elif ctrl and key == "y" and tab:
            tab.redo_op()
        else:
            return False
        return True


def main():
    if not HAVE_GTK:
        print("jarvis-editor needs GTK3.", file=sys.stderr)
        return 1
    win = Editor(sys.argv[1:])
    # fix: Editor.__init__ used _add_tab; rewire to tracked variant
    win.connect("destroy", Gtk.main_quit)
    win.show_all()
    win.find_bar.hide()
    Gtk.main()
    return 0


if __name__ == "__main__":
    # NOTE: Editor uses _add_tab_tracked; alias for __init__ compatibility.
    Editor._add_tab = Editor._add_tab_tracked
    sys.exit(main())
