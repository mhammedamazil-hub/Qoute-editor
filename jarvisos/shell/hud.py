"""Center HUD: J A R V I S core + 'What would you like me to do?' + input.

Text entry and mic button share one pipeline (Core via socket). Replies
appear below; confirmations render inline Yes/No buttons.
"""
from __future__ import annotations

import threading

try:
    import gi
    gi.require_version("Gtk", "3.0")
    from gi.repository import Gtk, GLib, Gdk
    HAVE_GTK = True
except (ImportError, ValueError):
    HAVE_GTK = False

from core_widget import CoreWidget  # noqa: E402  (installed alongside)
import client  # noqa: E402


CSS = b"""
.jarvis-hud { background-color: rgba(4, 12, 24, 0.72); border-radius: 18px;
  border: 1px solid rgba(53, 224, 255, 0.35); }
.jarvis-title { color: #c8f4ff; font-size: 28px; letter-spacing: 14px;
  font-weight: 300; }
.jarvis-sub { color: #7fd4ea; font-size: 14px; }
.jarvis-entry { background-color: rgba(10, 30, 50, 0.9); color: #eafcff;
  border: 1px solid rgba(53, 224, 255, 0.5); border-radius: 12px;
  padding: 10px 14px; font-size: 15px; }
.jarvis-reply { color: #d9f6ff; font-size: 13px; }
.jarvis-mic { background: rgba(53, 224, 255, 0.12); border-radius: 12px;
  border: 1px solid rgba(53, 224, 255, 0.5); color: #c8f4ff; font-size: 18px; }
"""


if HAVE_GTK:

    class HudWindow(Gtk.Window):
        def __init__(self, animated=True, transparent=True):
            super().__init__(title="JARVIS")
            self.set_default_size(560, 560)
            self.set_position(Gtk.WindowPosition.CENTER)
            self.set_keep_below(True)
            self.set_skip_taskbar_hint(True)
            self.set_decorated(False)
            if transparent:
                screen = self.get_screen()
                visual = screen.get_rgba_visual()
                if visual:
                    self.set_visual(visual)
            css = Gtk.CssProvider()
            css.load_from_data(CSS)
            Gtk.StyleContext.add_provider_for_screen(
                Gdk.Screen.get_default(), css,
                Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

            self.core = CoreWidget(size=190, animated=animated)
            self.entry = Gtk.Entry()
            self.entry.set_placeholder_text("Type or speak…")
            self.entry.get_style_context().add_class("jarvis-entry")
            self.entry.connect("activate", self._on_submit)
            self.entry.set_width_chars(34)

            self.mic_btn = Gtk.Button(label="🎙")
            self.mic_btn.get_style_context().add_class("jarvis-mic")
            self.mic_btn.set_tooltip_text("Voice command (Super+V)")
            self.mic_btn.connect("clicked", self._on_mic)

            self.reply = Gtk.Label(label="")
            self.reply.set_line_wrap(True)
            self.reply.set_max_width_chars(52)
            self.reply.get_style_context().add_class("jarvis-reply")

            self.confirm_bar = Gtk.Box(spacing=8)
            self.confirm_bar.set_halign(Gtk.Align.CENTER)

            title = Gtk.Label(label="J A R V I S")
            title.get_style_context().add_class("jarvis-title")
            sub = Gtk.Label(label="What would you like me to do?")
            sub.get_style_context().add_class("jarvis-sub")

            input_row = Gtk.Box(spacing=8)
            input_row.pack_start(self.entry, True, True, 0)
            input_row.pack_start(self.mic_btn, False, False, 0)

            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
            box.set_border_width(22)
            for widget in (title, self.core, sub, input_row, self.reply,
                           self.confirm_bar):
                box.pack_start(widget, False, False, 0)
            frame = Gtk.Box()
            frame.get_style_context().add_class("jarvis-hud")
            frame.pack_start(box, True, True, 0)
            self.add(frame)
            self._pending_token = ""
            self.connect("key-press-event", self._on_key)

        def _on_key(self, _w, event):
            if event.keyval == Gdk.KEY_Escape:
                threading.Thread(target=client.stop, daemon=True).start()
                self._say("Automation stopped.")
                return True
            return False

        def _say(self, text):
            self.reply.set_text(text)
            self.core.pulse(0.9)

        def _on_submit(self, _entry):
            text = self.entry.get_text().strip()
            if not text:
                return
            self.entry.set_text("")
            self._say("Working…")
            self.core.pulse(1.0)
            threading.Thread(target=self._ask_core, args=(text,),
                             daemon=True).start()

        def _ask_core(self, text):
            resp = client.text_command(text)
            GLib.idle_add(self._show_response, resp)

        def _show_response(self, resp):
            for child in self.confirm_bar.get_children():
                self.confirm_bar.remove(child)
            self._say(resp.get("say", ""))
            if resp.get("needs_confirm"):
                self._pending_token = resp.get("confirm_token", "")
                yes = Gtk.Button(label="✓ Confirm")
                no = Gtk.Button(label="✕ Cancel")
                yes.connect("clicked", self._answer, True)
                no.connect("clicked", self._answer, False)
                self.confirm_bar.pack_start(yes, False, False, 0)
                self.confirm_bar.pack_start(no, False, False, 0)
                self.confirm_bar.show_all()
            return False

        def _answer(self, _btn, yes):
            for child in self.confirm_bar.get_children():
                self.confirm_bar.remove(child)
            token = self._pending_token
            self._pending_token = ""
            threading.Thread(target=self._confirm_async, args=(token, yes),
                             daemon=True).start()

        def _confirm_async(self, token, yes):
            resp = client.confirm(token, yes)
            GLib.idle_add(self._say, resp.get("say", ""))

        def _on_mic(self, _btn):
            import subprocess
            self._say("Listening… speak now.")
            self.core.pulse(1.0)

            def _listen():
                try:
                    proc = subprocess.run(
                        ["jarvis-listen", "--seconds", "6"],
                        capture_output=True, text=True, timeout=60)
                    heard = ""
                    for line in proc.stdout.splitlines():
                        if line.startswith("Heard"):
                            heard = line.split(":", 1)[1].strip()
                    GLib.idle_add(self._mic_done, heard.strip("' "),
                                  proc.stdout.strip().splitlines()[-1]
                                  if proc.stdout.strip() else "")
                except (OSError, subprocess.SubprocessError):
                    GLib.idle_add(self._say, "Voice input is unavailable.")

            threading.Thread(target=_listen, daemon=True).start()

        def _mic_done(self, heard, say):
            self._say(say or ("Heard: %s" % heard if heard else
                              "I didn't hear anything."))
            return False

else:  # pragma: no cover

    class HudWindow:  # type: ignore
        def __init__(self, *a, **k):
            raise RuntimeError("GTK3 is required for the shell")
