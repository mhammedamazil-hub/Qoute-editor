"""JARVIS Core — the single command pipeline for the whole OS.

Keyboard / Voice / Clap / GUI  →  Core  →  AI · Apps · Files · System ·
Automation · Notifications, all gated by the Permission/Safety layer.

Typical flow:
    core = Core()
    result = core.handle_text("open blender")
    if result.needs_confirm:
        result = core.confirm(result.confirm_token, yes=True)
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field

from . import intents as _intents
from . import permissions as _perm
from .config import get_config
from .memory import Memory
from . import notify as _notify

Intent = _intents.Intent


@dataclass
class Result:
    ok: bool
    say: str = ""
    intent: Intent | None = None
    needs_confirm: bool = False
    confirm_token: str = ""
    confirm_question: str = ""
    data: dict = field(default_factory=dict)
    source: str = "text"


class Core:
    def __init__(self, config=None, engine=None, ai=None, memory=None):
        self.config = config or get_config()
        self._engine = engine      # AutomationEngine (lazy)
        self._ai = ai              # AIManager (lazy)
        self._memory = memory      # Memory (lazy)
        self._pending = {}         # token → {"intent": Intent, "ts": float}
        self.listeners = []        # fn(event_dict) for shell/voice feedback

    # -- lazy subsystems -------------------------------------------------
    @property
    def engine(self):
        if self._engine is None:
            from .automation.engine import AutomationEngine
            self._engine = AutomationEngine(config=self.config)
        return self._engine

    @property
    def ai(self):
        if self._ai is None:
            from .ai.manager import AIManager
            self._ai = AIManager(config=self.config)
        return self._ai

    @property
    def memory(self):
        if self._memory is None:
            self._memory = Memory(
                enabled=bool(self.config.get("memory.enabled", True)))
        return self._memory

    def on_event(self, fn):
        self.listeners.append(fn)

    def _emit(self, kind, text="", **kw):
        event = {"kind": kind, "text": text, "ts": time.time()}
        event.update(kw)
        for fn in list(self.listeners):
            try:
                fn(event)
            except Exception:
                pass

    # -- entry points ----------------------------------------------------
    def handle_text(self, text, source="text"):
        text = (text or "").strip()
        if not text:
            return Result(False, "I didn't catch that.", source=source)
        # memory learning hooks ("remember …", "call me …")
        try:
            learned = self.memory.learn_from_command(text)
        except Exception:
            learned = None
        if learned:
            self._emit("say", learned)
            return Result(True, learned,
                          intent=Intent("memory.learn", {}, text, 1.0),
                          source=source)
        try:
            intent = _intents.parse(text)
        except Exception:
            intent = Intent("system.unknown", {"text": text}, text, 0.0)
        verdict = _perm.classify_intent(intent.name, intent.slots)
        if verdict.level == _perm.DENY:
            say = "I can't do that — %s." % verdict.reason
            self._emit("deny", say, intent=intent.name)
            return Result(False, say, intent=intent, source=source)
        if verdict.level == _perm.CONFIRM:
            token = uuid.uuid4().hex[:8]
            self._pending[token] = {"intent": intent, "ts": time.time()}
            question = self._confirm_question(intent)
            self._emit("confirm", question, token=token,
                       intent=intent.name)
            return Result(False, question, intent=intent, needs_confirm=True,
                          confirm_token=token, confirm_question=question,
                          source=source)
        return self._execute(intent, source)

    def handle_voice(self, transcript):
        return self.handle_text(transcript, source="voice")

    def handle_clap(self, pattern):
        """Route a detected clap pattern (e.g. 'double') to its mapping."""
        mappings = self.config.get("gestures.clap_map", {}) or {}
        action = mappings.get(pattern, "")
        self._emit("clap", pattern, action=action)
        if not action:
            return Result(False, "No action mapped to '%s' clap." % pattern,
                          source="clap")
        # mapped value is itself a command string → same pipeline
        result = self.handle_text(action, source="clap")
        result.source = "clap"
        return result

    def handle_gui(self, command):
        """Shell buttons/dock call into the same pipeline."""
        return self.handle_text(command, source="gui")

    def confirm(self, token, yes):
        pending = self._pending.pop(token, None)
        if pending is None:
            return Result(False, "That confirmation expired.")
        if not yes:
            self._emit("say", "Cancelled.")
            return Result(True, "Cancelled.",
                          intent=pending["intent"])
        self._emit("confirmed", "", intent=pending["intent"].name)
        return self._execute(pending["intent"], "confirm")

    # -- execution -------------------------------------------------------
    def _confirm_question(self, intent):
        name, slots = intent.name, intent.slots
        if name == "power.shutdown":
            return "Shut down the computer now?"
        if name == "power.reboot":
            return "Restart the computer now?"
        if name == "power.suspend":
            return "Suspend the computer now?"
        if name == "session.logout":
            return "Log out now?"
        if name == "apps.install":
            from .control import apps as _apps
            _, _, steps = _apps.install_plan(
                _apps.resolve(slots.get("app", "")) or slots.get("app", ""))
            return "Install %s? %s" % (slots.get("app", "that"), " ".join(steps))
        if name == "apps.remove":
            return "Uninstall %s?" % slots.get("app", "that")
        if name == "apps.update_system":
            return "Update all system packages now? This may take a while."
        if name == "files.delete":
            return "Move '%s' to trash?" % (slots.get("target") or "that")
        if name == "files.empty_trash":
            return "Permanently delete everything in the trash?"
        if name == "automation.run_task":
            return "Let JARVIS control the screen to: '%s'? Press ESC anytime to stop." % slots.get("task", "")
        return "Do '%s'?" % name

    def _execute(self, intent, source):
        from .control import apps as _apps
        from .control import filesops as _files
        from .system import stats as _stats
        from .system import network as _net
        from .system import bluetooth as _bt
        from .system import audio as _audio
        from .system import display as _display
        from .system import power as _power

        name, s = intent.name, intent.slots
        ok, say, data = True, "", {}

        try:
            # -- apps ---------------------------------------------------
            if name == "apps.open":
                aid = _apps.resolve(s.get("app", "")) or "files"
                ok, say = _apps.launch(aid)
            elif name == "apps.close":
                ok, say = _apps.close(_apps.resolve(s.get("app", "")))
            elif name == "apps.focus":
                ok, say = _apps.focus(_apps.resolve(s.get("app", "")))
            elif name == "apps.install":
                ok, say = _apps.install(_apps.resolve(s.get("app", ""))
                                        or s.get("app", ""))
            elif name == "apps.remove":
                ok, say = _apps.close(_apps.resolve(s.get("app", "")))
                say = "Uninstall is managed in the App Manager — " \
                    "opening it now." if ok else say
                if ok:
                    _apps.launch("store")
            elif name == "apps.update_system":
                ok, say = self._system_update()
            # -- files --------------------------------------------------
            elif name == "files.open_folder":
                ok, say = self._open_folder(s.get("folder", "home"))
            elif name == "files.recent":
                items = _files.recent_files()
                data["files"] = items
                say = ("I couldn't find recent files." if not items else
                       "Recent: " + ", ".join(
                           __import__("os").path.basename(i["path"])
                           for i in items[:5]))
            elif name == "files.search":
                hits = _files.search(s.get("query", ""))
                data["files"] = hits
                say = ("No files matching '%s'." % s.get("query", "")) \
                    if not hits else \
                    "Found %d file%s: %s" % (
                        len(hits), "" if len(hits) == 1 else "s",
                        ", ".join(__import__("os").path.basename(h)
                                  for h in hits[:5]))
            elif name == "files.new_folder":
                ok, say = _files.new_folder(s.get("name"))
            elif name == "files.delete":
                ok, say = _files.move_to_trash(s.get("target", ""))
            elif name == "files.empty_trash":
                ok, say = _files.empty_trash()
            # -- stats --------------------------------------------------
            elif name == "system.ram":
                m = _stats.mem()
                say = "RAM: %d of %d MB in use (%s%%). %d MB free." % (
                    m["used_mb"], m["total_mb"], m["percent"], m["avail_mb"])
                data = m
            elif name == "system.cpu":
                pct = _stats.cpu_percent()
                l1, l5, l15 = _stats.loadavg()
                say = "CPU at %s%%. Load average %s, %s, %s on %d cores." % (
                    pct, l1, l5, l15, _stats.cpu_count())
                data = {"cpu_percent": pct}
            elif name == "system.disk":
                d = _stats.disk()
                say = "Disk: %s of %s GB used (%s%%). %s GB free." % (
                    d["used_gb"], d["total_gb"], d["percent"], d["free_gb"])
                data = d
            elif name == "system.battery":
                b = _stats.battery()
                say = "No battery detected." if not b else \
                    "Battery at %d%% (%s)." % (b["percent"], b["state"])
                data = b or {}
            elif name == "system.temperature":
                t = _stats.temperature()
                say = "Temperature sensors unavailable." if t is None else \
                    "CPU temperature is %s°C." % t
                data = {"temp_c": t}
            elif name == "system.processes":
                procs = _stats.top_processes(5)
                data["processes"] = procs
                say = "Top memory: " + ", ".join(
                    "%s (%s MB)" % (p["name"], p["rss_mb"]) for p in procs)
            # -- network ------------------------------------------------
            elif name == "network.wifi_on":
                ok, say = _net.wifi(True)
            elif name == "network.wifi_off":
                ok, say = _net.wifi(False)
            elif name == "network.wifi_connect":
                ok, say = _net.connect(s.get("ssid", ""))
            elif name == "network.wifi_list":
                nets = _net.list_networks()
                data["networks"] = nets
                say = "No Wi-Fi networks found." if not nets else \
                    "Strongest: " + ", ".join(
                        "%s (%d%%)" % (n["ssid"], n["signal"]) for n in nets[:5])
            elif name == "network.wifi_disconnect":
                ok, say = _net.disconnect()
            elif name == "network.status":
                st = _net.status()
                data = st
                say = ("Offline." if not st["online"] else
                       "Connected to %s (%d%%)%s." % (
                           st["ssid"] or "wired", st["signal"],
                           (", IP " + st["ip"]) if st["ip"] else ""))
            # -- bluetooth ----------------------------------------------
            elif name == "bluetooth.on":
                ok, say = _bt.set_power(True)
            elif name == "bluetooth.off":
                ok, say = _bt.set_power(False)
            elif name == "bluetooth.connect":
                ok, say = _bt.connect(s.get("device", ""))
            elif name == "bluetooth.list":
                devs = _bt.devices()
                data["devices"] = devs
                say = "No Bluetooth devices known." if not devs else \
                    "Devices: " + ", ".join(d["name"] for d in devs[:6])
            # -- audio --------------------------------------------------
            elif name == "audio.volume_set":
                ok, say = _audio.set_volume(s.get("level", 50))
            elif name == "audio.volume_up":
                ok, say = _audio.volume_step(+10)
            elif name == "audio.volume_down":
                ok, say = _audio.volume_step(-10)
            elif name == "audio.mute":
                ok, say = _audio.mute(True)
            elif name == "audio.unmute":
                ok, say = _audio.mute(False)
            elif name == "audio.mic_mute_toggle":
                ok, say = _audio.mic_mute_toggle()
            # -- display ------------------------------------------------
            elif name == "display.brightness_set":
                ok, say = _display.set_brightness(s.get("level", 70))
            elif name == "display.brightness_up":
                ok, say = _display.brightness_step(+10)
            elif name == "display.brightness_down":
                ok, say = _display.brightness_step(-10)
            elif name == "display.screenshot":
                path = _display.screenshot()
                ok = bool(path)
                say = "Screenshot saved to %s." % path if ok else \
                    "Could not take a screenshot."
                data["path"] = path
            elif name == "display.night_mode":
                ok, say = _display.night_mode(s.get("mode", "on") == "on")
            elif name == "display.wallpaper":
                ok, say = _apps.launch("settings")
                say = "Wallpaper lives in Settings → Appearance."
            # -- power --------------------------------------------------
            elif name == "power.lock":
                ok, say = _power.lock()
            elif name == "power.suspend":
                ok, say = _power.suspend()
            elif name == "power.reboot":
                ok, say = _power.reboot()
            elif name == "power.shutdown":
                ok, say = _power.shutdown()
            elif name == "session.logout":
                ok, say = _power.logout()
            # -- settings -----------------------------------------------
            elif name == "settings.open":
                ok, say = _apps.launch("settings")
                data["section"] = s.get("section", "")
            # -- automation ----------------------------------------------
            elif name == "automation.stop":
                self.engine.stop()
                say = "Automation stopped."
            elif name == "automation.run_task":
                say = self._start_task(s.get("task", ""))
            # -- AI -------------------------------------------------------
            elif name == "ai.analyze_screen":
                say = self._analyze_screen()
            elif name == "ai.ask":
                say = self._ask_ai(s.get("question", ""))
            # -- misc ------------------------------------------------------
            elif name == "system.help":
                say = self._help_text()
            elif name == "system.noop":
                say = "How can I help?"
            elif name == "memory.learn":
                say = "Noted."
            else:
                # unknown → AI fallback when available, else honest help
                say = self._fallback(intent)
                ok = not say.startswith("I don't")
        except Exception as exc:  # never crash the desktop on a command
            ok, say = False, "Something went wrong: %s" % exc

        self._emit("say" if ok else "error", say, intent=name)
        if source in ("voice", "clap") or name.startswith("power."):
            try:
                _notify.send("JARVIS", say)
            except Exception:
                pass
        return Result(ok, say, intent=intent, data=data, source=source)

    # -- helpers ---------------------------------------------------------
    def _open_folder(self, folder):
        import subprocess
        from .control import filesops as _files
        path = _files.folder_path(folder)
        for argv in (["jarvis-files", path], ["thunar", path],
                    ["xdg-open", path]):
            try:
                subprocess.Popen(argv, stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL,
                                 stdin=subprocess.DEVNULL,
                                 start_new_session=True)
                return True, "Opened %s." % folder
            except OSError:
                continue
        return False, "Could not open %s." % folder

    def _system_update(self):
        import shutil
        import subprocess
        helper = shutil.which("jarvis-app-install")
        term = shutil.which("lxterminal") or shutil.which("xterm")
        if helper and term:
            subprocess.Popen([term, "-e", helper, "update", ""],
                             stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL,
                             stdin=subprocess.DEVNULL,
                             start_new_session=True)
            return True, "Updating the system — watch the terminal window."
        return False, "System updater is not available."

    def _start_task(self, task):
        if not self.ai.configured:
            return ("Screen automation needs a cloud AI key — "
                    "open Settings → AI Providers first.")
        self._emit("task_start", task)
        batch = self.ai.plan_from_screen(task)
        if not batch.get("actions"):
            return "I couldn't build a safe plan for that. %s" % batch.get(
                "say", "")
        report = self.engine.run_batch(batch["actions"], task=task,
                                       require_confirm=True,
                                       confirm_callback=None)
        if report.get("needs_confirm"):
            token = uuid.uuid4().hex[:8]
            self._pending[token] = {
                "intent": Intent("automation.run_task_confirmed",
                                 {"actions": batch["actions"],
                                  "task": task}, task, 1.0),
                "ts": time.time()}
            return ("Plan ready: %d actions. %s" % (
                len(batch["actions"]), batch.get("say", "")))
        return report.get("say", "Done.")

    def _analyze_screen(self):
        if not self.ai.configured:
            return ("Screen analysis needs a cloud AI key — "
                    "open Settings → AI Providers first.")
        from .system import display as _display
        path = _display.screenshot()
        if not path:
            return "Could not capture the screen."
        return self.ai.describe_image(path, "Describe this screen for the user.")

    def _ask_ai(self, question):
        if not self.ai.configured:
            return ("AI answers need a cloud API key — open Settings → AI "
                    "Providers. Meanwhile I can still control the whole OS "
                    "offline: try 'what can you do?'.")
        facts = self.memory.recall(question)
        return self.ai.ask(question, context=facts)

    def _fallback(self, intent):
        if self.ai.configured:
            facts = self.memory.recall(intent.raw)
            return self.ai.ask(intent.raw, context=facts)
        return ("I don't know how to do that yet. Try 'what can you do?' "
                "for the offline command list, or add an AI key in Settings "
                "for anything else.")

    def _help_text(self):
        return (
            "You can control the whole OS. Try: 'open blender', "
            "'open downloads', 'show recent files', 'what is using my ram?', "
            "'connect wifi Home-5G', 'connect bluetooth', 'set volume to 40', "
            "'take a screenshot', 'install vlc', 'lock the screen'. "
            "Speak with Super+V, stop automation with ESC.")
