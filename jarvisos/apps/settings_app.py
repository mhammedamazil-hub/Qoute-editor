#!/usr/bin/env python3
"""jarvis-settings — every JARVISOS setting in one place (GTK3).

Appearance · AI Providers · Voice · Clap/Gestures · Shortcuts ·
Applications · Network · Bluetooth · Audio · Display · Privacy ·
Automation · Performance · System. All controls read/write the real
config + call the real backends.
"""
import os
import sys
import threading

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

from jarvis.config import get_config  # noqa: E402

CSS = b""".jarvis-win { background-color: #060f1c; }
.jarvis-win * { color: #cfeeff; }
.jarvis-title { color: #c8f4ff; font-size: 14px; letter-spacing: 6px; }
.jarvis-h { color: #8cf4ff; font-size: 13px; font-weight: bold; }"""


class Settings(Gtk.Window):
    def __init__(self, section=""):
        super().__init__(title="JARVIS Settings")
        self.set_default_size(760, 560)
        self.config = get_config()
        css = Gtk.CssProvider()
        css.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(), css,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        self.get_style_context().add_class("jarvis-win")

        self.stack = Gtk.Stack()
        self.stack.set_transition_type(
            Gtk.StackTransitionType.SLIDE_LEFT_RIGHT)
        nav = Gtk.ListBox()
        nav.set_size_request(180, -1)
        self._rows = {}
        for key, label, builder in self._sections():
            page = builder()
            page.set_border_width(12)
            scroll = Gtk.ScrolledWindow()
            scroll.add(page)
            self.stack.add_titled(scroll, key, label)
            row = Gtk.Label(label=label, xalign=0)
            box = Gtk.ListBoxRow()
            box.add(row)
            nav.add(box)
            self._rows[key] = box
        nav.connect("row-selected", self._on_nav)
        paned = Gtk.Paned()
        paned.pack1(nav, False, False)
        paned.pack2(self.stack, True, False)
        title = Gtk.Label(label="J A R V I S   S E T T I N G S")
        title.get_style_context().add_class("jarvis-title")
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        root.pack_start(title, False, False, 4)
        root.pack_start(paned, True, True, 0)
        self.add(root)
        if section:
            for key in self._rows:
                if key.startswith(section.lower()):
                    nav.select_row(self._rows[key])
                    break

    # -- widgets -----------------------------------------------------------
    def _sections(self):
        return [
            ("appearance", "Appearance", self._pg_appearance),
            ("ai", "AI Providers", self._pg_ai),
            ("voice", "Voice", self._pg_voice),
            ("clap", "Clap / Gestures", self._pg_clap),
            ("shortcuts", "Shortcuts", self._pg_shortcuts),
            ("applications", "Applications", self._pg_apps),
            ("network", "Network", self._pg_network),
            ("bluetooth", "Bluetooth", self._pg_bluetooth),
            ("audio", "Audio", self._pg_audio),
            ("display", "Display", self._pg_display),
            ("privacy", "Privacy", self._pg_privacy),
            ("automation", "Automation", self._pg_automation),
            ("performance", "Performance", self._pg_performance),
            ("system", "System", self._pg_system),
        ]

    def _on_nav(self, _box, row):
        if row is None:
            return
        for key, box in self._rows.items():
            if box is row:
                self.stack.set_visible_child_name(key)

    def _head(self, box, text):
        lab = Gtk.Label(label=text, xalign=0)
        lab.get_style_context().add_class("jarvis-h")
        box.pack_start(lab, False, False, 6)

    def _row(self, box, label, widget):
        row = Gtk.Box(spacing=8)
        lab = Gtk.Label(label=label, xalign=0)
        lab.set_size_request(220, -1)
        row.pack_start(lab, False, False, 0)
        row.pack_start(widget, True, True, 0)
        box.pack_start(row, False, False, 4)
        return row

    def _switch(self, box, label, key, default=True):
        sw = Gtk.Switch()
        sw.set_active(bool(self.config.get(key, default)))
        sw.connect("notify::active",
                   lambda s, p: self.config.set(key, s.get_active()))
        self._row(box, label, sw)
        return sw

    def _combo(self, box, label, key, options, default):
        cb = Gtk.ComboBoxText()
        for opt in options:
            cb.append_text(opt)
        cur = str(self.config.get(key, default))
        cb.set_active(options.index(cur) if cur in options else 0)
        cb.connect("changed",
                   lambda c: self.config.set(key, c.get_active_text()))
        self._row(box, label, cb)
        return cb

    def _spin(self, box, label, key, lo, hi, step, default):
        adj = Gtk.Adjustment(value=float(self.config.get(key, default)),
                             lower=lo, upper=hi, step_increment=step)
        sp = Gtk.SpinButton(adjustment=adj, digits=1 if step < 1 else 0)
        sp.connect("value-changed",
                   lambda s: self.config.set(key, s.get_value()))
        self._row(box, label, sp)
        return sp

    def _note(self, box, text):
        lab = Gtk.Label(label=text, xalign=0)
        lab.set_line_wrap(True)
        box.pack_start(lab, False, False, 4)

    # -- pages ---------------------------------------------------------------
    def _pg_appearance(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self._head(box, "Appearance")
        self._combo(box, "Theme", "appearance.theme", ["jarvis-dark"],
                    "jarvis-dark")
        entry = Gtk.Entry()
        entry.set_text(str(self.config.get("appearance.accent", "#35e0ff")))
        entry.connect("changed",
                      lambda e: self.config.set("appearance.accent",
                                                e.get_text()[:16]))
        self._row(box, "Accent color", entry)
        self._switch(box, "Animations", "appearance.animations", True)
        self._switch(box, "Glass transparency", "appearance.transparency",
                     True)
        self._note(box, "Changes apply to newly opened shell windows. "
                        "Restart the shell from System to apply everywhere.")
        return box

    def _pg_ai(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self._head(box, "AI Providers (cloud, modular)")
        self._combo(box, "Preferred provider", "ai.provider",
                    ["gemini", "openrouter", "huggingface"], "gemini")
        self.status_ai = Gtk.Label(label="", xalign=0)
        self.status_ai.set_line_wrap(True)
        for prov, label, keyname in (
                ("gemini", "Gemini API key", "ai.gemini_model"),
                ("openrouter", "OpenRouter key", "ai.openrouter_model"),
                ("huggingface", "Hugging Face token",
                 "ai.huggingface_model")):
            entry = Gtk.Entry()
            entry.set_visibility(False)
            entry.set_placeholder_text("Stored only in ~/.config/jarvisos/ "
                                       "(0600)" if not self.config.has_secret(
                                           prov) else "●●● saved — paste to replace")
            entry.connect(
                "changed",
                lambda e, p=prov: self.config.set_secret(p, e.get_text())
                if e.get_text().strip() else None)
            self._row(box, label, entry)
            model = Gtk.Entry()
            model.set_text(str(self.config.get(keyname, "")))
            model.connect("changed",
                          lambda e, k=keyname: self.config.set(k, e.get_text()[:80]))
            self._row(box, "  model", model)
        btn = Gtk.Button(label="Test connection")
        btn.connect("clicked", self._ai_test)
        box.pack_start(btn, False, False, 6)
        box.pack_start(self.status_ai, False, False, 4)
        self._note(box, "Get keys: Google AI Studio (Gemini), openrouter.ai, "
                        "huggingface.co/settings/tokens. Without any key the "
                        "whole OS still works offline — only AI answers and "
                        "screen automation are unavailable.")
        return box

    def _ai_test(self, _b):
        self.status_ai.set_text("Testing…")

        def _run():
            try:
                from jarvis.ai.manager import AIManager
                mgr = AIManager(config=self.config)
                if not mgr.configured:
                    GLib.idle_add(self.status_ai.set_text,
                                  "No provider key saved yet.")
                    return
                answer = mgr.ask("Reply with exactly: JARVIS online.")
                GLib.idle_add(self.status_ai.set_text,
                              "Providers: %s\nReply: %s" % (
                                  ",".join(mgr.configured_providers),
                                  answer[:200]))
            except Exception as exc:
                GLib.idle_add(self.status_ai.set_text,
                              "Failed: %s" % exc)

        threading.Thread(target=_run, daemon=True).start()

    def _pg_voice(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self._head(box, "Voice")
        self._combo(box, "Speech engine", "voice.stt_engine",
                    ["auto", "vosk", "cloud"], "auto")
        entry = Gtk.Entry()
        entry.set_text(str(self.config.get("voice.vosk_model", "")))
        entry.connect("changed", lambda e: self.config.set(
            "voice.vosk_model", e.get_text()[:200]))
        self._row(box, "Vosk tiny model dir", entry)
        self._switch(box, "Speak replies aloud", "voice.speak_replies", True)
        self._spin(box, "Speech rate", "voice.rate", 80, 300, 5, 175)
        self._spin(box, "Listen seconds", "voice.push_to_talk_seconds", 3,
                   20, 1, 6)
        btn = Gtk.Button(label="Test microphone (6 s)")
        btn.connect("clicked", self._mic_test)
        box.pack_start(btn, False, False, 6)
        self.mic_lab = Gtk.Label(label="", xalign=0)
        box.pack_start(self.mic_lab, False, False, 4)
        return box

    def _mic_test(self, _b):
        self.mic_lab.set_text("Listening… speak now.")

        def _run():
            try:
                from jarvis.voice import stt
                text, engine = stt.listen_once(6, self.config)
                GLib.idle_add(self.mic_lab.set_text,
                              "Heard (%s): %s" % (engine, text or "(nothing)"))
            except Exception as exc:
                GLib.idle_add(self.mic_lab.set_text, "Failed: %s" % exc)

        threading.Thread(target=_run, daemon=True).start()

    def _pg_clap(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self._head(box, "Clap / Gestures (local, no cloud)")
        self._switch(box, "Enable clap detection",
                     "gestures.clap_enabled", True)
        self._spin(box, "Sensitivity (higher = louder claps needed)",
                   "gestures.sensitivity", 1.5, 6.0, 0.1, 3.0)
        self._spin(box, "Double-clap window (ms)",
                   "gestures.double_window_ms", 300, 1200, 50, 700)
        self._spin(box, "Cooldown (ms)", "gestures.cooldown_ms", 500, 5000,
                   100, 1800)
        for pattern, label in (("single", "👏 Single clap → command"),
                               ("double", "👏👏 Double clap → command"),
                               ("triple", "👏👏👏 Triple clap → command")):
            entry = Gtk.Entry()
            entry.set_text(str((self.config.get("gestures.clap_map", {})
                                or {}).get(pattern, "")))
            entry.connect("changed", self._clap_map_changed, pattern)
            self._row(box, label, entry)
        self._note(box, "Commands run through the same safety layer as "
                        "typed commands. Test: clap, then check the "
                        "notification bubble.")
        return box

    def _clap_map_changed(self, entry, pattern):
        mapping = dict(self.config.get("gestures.clap_map", {}) or {})
        mapping[pattern] = entry.get_text()[:120]
        self.config.set("gestures.clap_map", mapping)

    def _pg_shortcuts(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self._head(box, "Keyboard shortcuts")
        for action, keys in (("JARVIS command bar", "Super + Space"),
                             ("Voice mode", "Super + V"),
                             ("Application launcher", "Super + A"),
                             ("JARVIS files", "Super + F"),
                             ("Stop automation (emergency)", "ESC"),
                             ("Terminal", "Ctrl + Alt + T")):
            self._row(box, action, Gtk.Label(label=keys, xalign=0))
        self._note(box, "Bindings live in ~/.config/openbox/rc.xml "
                        "(JARVIS session) — edit there to customize.")
        return box

    def _pg_apps(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self._head(box, "Applications")
        btn = Gtk.Button(label="Open App Manager (install / update)")
        btn.connect("clicked", lambda b: __import__("subprocess").Popen(
            ["jarvis-appmanager"]))
        box.pack_start(btn, False, False, 6)
        self._note(box, "Default handlers: .txt/.md → jarvis-editor, "
                        "folders → jarvis-files, web → Firefox (Brave "
                        "installable). Say 'install …' any time.")
        return box

    def _pg_network(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self._head(box, "Network / Wi-Fi")
        self.wifi_lab = Gtk.Label(label="", xalign=0)
        box.pack_start(self.wifi_lab, False, False, 4)
        row = Gtk.Box(spacing=6)
        for label, cb in (("Refresh", self._net_refresh),
                          ("Wi-Fi on", lambda b: self._net_set(True)),
                          ("Wi-Fi off", lambda b: self._net_set(False))):
            btn = Gtk.Button(label=label)
            btn.connect("clicked", cb)
            row.pack_start(btn, False, False, 0)
        box.pack_start(row, False, False, 4)
        self.net_list = Gtk.ListBox()
        scroll = Gtk.ScrolledWindow()
        scroll.set_min_content_height(180)
        scroll.add(self.net_list)
        box.pack_start(scroll, True, True, 4)
        self._net_refresh(None)
        return box

    def _net_refresh(self, _b):
        for child in self.net_list.get_children():
            self.net_list.remove(child)
        self.wifi_lab.set_text("Scanning…")

        def _run():
            try:
                from jarvis.system import network as N
                st, nets = N.status(), N.list_networks()
                GLib.idle_add(self._net_paint, st, nets)
            except Exception as exc:
                GLib.idle_add(self.wifi_lab.set_text, "Failed: %s" % exc)

        threading.Thread(target=_run, daemon=True).start()

    def _net_paint(self, st, nets):
        self.wifi_lab.set_text(
            "Wi-Fi: %s   now: %s (%s%%)   IP: %s" % (
                "on" if st["wifi_on"] else "off", st["ssid"] or "—",
                st["signal"], st["ip"] or "—"))
        for net in nets[:15]:
            row = Gtk.Box(spacing=8)
            row.pack_start(Gtk.Label(label="%s  (%d%%)" % (
                net["ssid"], net["signal"]), xalign=0), True, True, 0)
            btn = Gtk.Button(label="Connect")
            btn.connect("clicked", self._net_connect, net["ssid"])
            row.pack_start(btn, False, False, 0)
            box = Gtk.ListBoxRow()
            box.add(row)
            self.net_list.add(box)
        self.net_list.show_all()
        return False

    def _net_connect(self, _b, ssid):
        def _run():
            from jarvis.system import network as N
            ok, msg = N.connect(ssid)
            GLib.idle_add(self.wifi_lab.set_text, msg)
            if ok:
                GLib.idle_add(lambda: self._net_refresh(None) or False)

        threading.Thread(target=_run, daemon=True).start()

    def _net_set(self, on):
        def _run():
            from jarvis.system import network as N
            ok, msg = N.wifi(on)
            GLib.idle_add(self.wifi_lab.set_text, msg)

        threading.Thread(target=_run, daemon=True).start()

    def _pg_bluetooth(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self._head(box, "Bluetooth")
        self.bt_lab = Gtk.Label(label="", xalign=0)
        box.pack_start(self.bt_lab, False, False, 4)
        row = Gtk.Box(spacing=6)
        for label, cb in (("Refresh", self._bt_refresh),
                          ("Turn on", lambda b: self._bt_set(True)),
                          ("Turn off", lambda b: self._bt_set(False))):
            btn = Gtk.Button(label=label)
            btn.connect("clicked", cb)
            row.pack_start(btn, False, False, 0)
        box.pack_start(row, False, False, 4)
        self.bt_list = Gtk.ListBox()
        scroll = Gtk.ScrolledWindow()
        scroll.set_min_content_height(180)
        scroll.add(self.bt_list)
        box.pack_start(scroll, True, True, 4)
        self._bt_refresh(None)
        return box

    def _bt_refresh(self, _b):
        for child in self.bt_list.get_children():
            self.bt_list.remove(child)
        self.bt_lab.set_text("Scanning…")

        def _run():
            try:
                from jarvis.system import bluetooth as B
                devs = B.scan(timeout=5) if B.powered() else B.devices()
                GLib.idle_add(self._bt_paint, B.powered(), devs)
            except Exception as exc:
                GLib.idle_add(self.bt_lab.set_text, "Failed: %s" % exc)

        threading.Thread(target=_run, daemon=True).start()

    def _bt_paint(self, powered, devs):
        self.bt_lab.set_text("Bluetooth: %s (%d devices)" % (
            "on" if powered else "off", len(devs)))
        for dev in devs[:15]:
            row = Gtk.Box(spacing=8)
            row.pack_start(Gtk.Label(label=dev["name"], xalign=0),
                           True, True, 0)
            btn = Gtk.Button(label="Connect")
            btn.connect("clicked", self._bt_connect, dev["name"])
            row.pack_start(btn, False, False, 0)
            box = Gtk.ListBoxRow()
            box.add(row)
            self.bt_list.add(box)
        self.bt_list.show_all()
        return False

    def _bt_connect(self, _b, name):
        def _run():
            from jarvis.system import bluetooth as B
            ok, msg = B.connect(name)
            GLib.idle_add(self.bt_lab.set_text, msg)

        threading.Thread(target=_run, daemon=True).start()

    def _bt_set(self, on):
        def _run():
            from jarvis.system import bluetooth as B
            ok, msg = B.set_power(on)
            GLib.idle_add(self.bt_lab.set_text, msg)

        threading.Thread(target=_run, daemon=True).start()

    def _pg_audio(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self._head(box, "Audio")
        self.vol = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0,
                                            100, 1)
        try:
            from jarvis.system import audio as AU
            pct, muted = AU.volume()
            self.vol.set_value(pct)
        except Exception:
            pass
        self.vol.connect("value-changed", self._vol_changed)
        self._row(box, "Output volume", self.vol)
        row = Gtk.Box(spacing=6)
        for label, on in (("Mute", True), ("Unmute", False)):
            btn = Gtk.Button(label=label)
            btn.connect("clicked", lambda b, o=on: self._mute(o))
            row.pack_start(btn, False, False, 0)
        mic = Gtk.Button(label="Toggle mic mute")
        mic.connect("clicked", lambda b: self._mute_mic())
        row.pack_start(mic, False, False, 0)
        box.pack_start(row, False, False, 4)
        self.audio_lab = Gtk.Label(label="", xalign=0)
        box.pack_start(self.audio_lab, False, False, 4)
        return box

    def _vol_changed(self, scale):
        from jarvis.system import audio as AU
        AU.set_volume(scale.get_value())

    def _mute(self, on):
        from jarvis.system import audio as AU
        ok, msg = AU.mute(on)
        self.audio_lab.set_text(msg)

    def _mute_mic(self):
        from jarvis.system import audio as AU
        ok, msg = AU.mic_mute_toggle()
        self.audio_lab.set_text(msg)

    def _pg_display(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self._head(box, "Display")
        self.bri = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 1,
                                            100, 1)
        try:
            from jarvis.system import display as D
            cur = D.brightness()
            if cur:
                self.bri.set_value(cur)
        except Exception:
            pass
        self.bri.connect("value-changed", self._bri_changed)
        self._row(box, "Brightness", self.bri)
        row = Gtk.Box(spacing=6)
        for label, on in (("Night mode on", True), ("Night mode off", False)):
            btn = Gtk.Button(label=label)
            btn.connect("clicked", lambda b, o=on: self._night(o))
            row.pack_start(btn, False, False, 0)
        box.pack_start(row, False, False, 4)
        self.disp_lab = Gtk.Label(label="", xalign=0)
        box.pack_start(self.disp_lab, False, False, 4)
        try:
            from jarvis.system import display as D2
            w, h = D2.resolution()
            if w:
                self._note(box, "Resolution: %dx%d." % (w, h))
        except Exception:
            pass
        return box

    def _bri_changed(self, scale):
        from jarvis.system import display as D
        D.set_brightness(scale.get_value())

    def _night(self, on):
        from jarvis.system import display as D
        ok, msg = D.night_mode(on)
        self.disp_lab.set_text(msg)

    def _pg_privacy(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self._head(box, "Privacy")
        self._switch(box, "Allow screenshots to cloud AI",
                     "privacy.send_screenshots_to_ai", True)
        self._switch(box, "Allow voice to cloud STT",
                     "privacy.send_voice_to_cloud", True)
        self._switch(box, "Local AI memory (JSON, on this PC)",
                     "memory.enabled", True)
        btn = Gtk.Button(label="Erase my AI memory")
        btn.connect("clicked", self._mem_erase)
        box.pack_start(btn, False, False, 6)
        self._note(box, "Clap detection is always local. API keys never "
                        "leave ~/.config/jarvisos/secrets.json except to "
                        "the provider you chose.")
        return box

    def _mem_erase(self, _b):
        from jarvis.memory import Memory
        Memory().clear()
        dlg = Gtk.MessageDialog(transient_for=self, flags=0,
                                message_type=Gtk.MessageType.INFO,
                                buttons=Gtk.ButtonsType.OK,
                                text="AI memory erased.")
        dlg.run()
        dlg.destroy()

    def _pg_automation(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self._head(box, "Automation permissions")
        self._switch(box, "Always confirm before screen control",
                     "automation.confirm_first_batch", True)
        self._spin(box, "Max actions per batch",
                   "automation.max_batch_actions", 5, 30, 1, 25)
        btn = Gtk.Button(label="⛔ STOP running automation now")
        btn.connect("clicked", self._auto_stop)
        box.pack_start(btn, False, False, 6)
        self._note(box, "The AI can only emit structured actions. Shell, "
                        "installs, deletes and power actions always need "
                        "confirmation. ESC stops everything instantly.")
        return box

    def _auto_stop(self, _b):
        import subprocess
        subprocess.Popen(["jarvis", "stop"])

    def _pg_performance(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self._head(box, "Performance mode")
        self._combo(box, "Mode", "appearance.performance_mode",
                    ["auto", "cinematic", "performance"], "auto")
        try:
            from jarvis.system import stats as ST
            mem = ST.mem()
            self._note(box, "This PC: %d MB RAM, %d cores. 'auto' uses "
                            "Performance mode below 5120 MB." % (
                                mem["total_mb"], ST.cpu_count()))
        except Exception:
            pass
        self._note(box, "Performance: static core, no transparency, slower "
                        "polling, no compositor. Cinematic: animations, "
                        "glass panels, picom compositor. See docs/"
                        "performance.md.")
        return box

    def _pg_system(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self._head(box, "System")
        try:
            from jarvis.system import stats as ST2
            mem = ST2.mem()
            disk = ST2.disk("/")
            info = "RAM %d MB · Disk %.1f/%.1f GB · %d cores" % (
                mem["total_mb"], disk["used_gb"], disk["total_gb"],
                ST2.cpu_count())
        except Exception:
            info = "stats unavailable"
        try:
            with open("/etc/jarvisos-release", encoding="utf-8") as fh:
                info = fh.read().strip() + "\n" + info
        except OSError:
            pass
        self._note(box, info)
        for label, cmd in (("Restart JARVIS shell", ["pkill", "-f",
                                                    "jarvis-shell"]),
                           ("Update system", ["jarvis", "update the system"]),
                           ("Install JARVISOS to disk", ["jarvis-install"])):
            btn = Gtk.Button(label=label)
            btn.connect("clicked", lambda b, c=cmd:
                        __import__("subprocess").Popen(c))
            box.pack_start(btn, False, False, 4)
        return box


def main():
    if not HAVE_GTK:
        print("jarvis-settings needs GTK3.", file=sys.stderr)
        return 1
    section = sys.argv[1] if len(sys.argv) > 1 else ""
    win = Settings(section=section)
    win.connect("destroy", Gtk.main_quit)
    win.show_all()
    Gtk.main()
    return 0


if __name__ == "__main__":
    sys.exit(main())
