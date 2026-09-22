"""Batch automation engine with safety validator + emergency stop.

Execution model (per batch of 10–30 actions):
    validate every action  →  run each (stop flag checked between)  →
    report per-action results. ESC / engine.stop() halts immediately.

Backends:
    RealBackend — pyautogui/xdotool/nmcli… on the live system.
    MockBackend — records calls for tests and dry-runs.
"""
from __future__ import annotations

import subprocess
import threading
import time

from .. import permissions as _perm
from ..system import display as _display


class StopRequested(Exception):
    pass


class MockBackend:
    """Records actions instead of executing them (tests / dry-run)."""

    def __init__(self, width=1920, height=1080):
        self.calls = []
        self.width = width
        self.height = height

    def _rec(self, name, **kw):
        self.calls.append({"call": name, **kw})
        return True, "mock:%s" % name

    def open_app(self, app):
        return self._rec("open_app", app=app)

    def focus_app(self, app):
        return self._rec("focus_app", app=app)

    def close_app(self, app):
        return self._rec("close_app", app=app)

    def click(self, x, y, button="left"):
        return self._rec("click", x=x, y=y, button=button)

    def move(self, x, y):
        return self._rec("move", x=x, y=y)

    def scroll(self, dx, dy):
        return self._rec("scroll", dx=dx, dy=dy)

    def key(self, key):
        return self._rec("key", key=key)

    def hotkey(self, keys):
        return self._rec("hotkey", keys=keys)

    def type_text(self, text):
        return self._rec("type", text=text[:80])

    def open_url(self, url):
        return self._rec("open_url", url=url)

    def open_path(self, path):
        return self._rec("open_path", path=path)

    def shell(self, command, args):
        return self._rec("shell", command=command, args=args)

    def screenshot(self):
        return self._rec("screenshot")


class RealBackend:
    """Executes actions on the real X11 desktop."""

    def __init__(self):
        self._pag = None
        try:
            import pyautogui  # optional; hook installs it
            pyautogui.FAILSAFE = True
            pyautogui.PAUSE = 0.15
            self._pag = pyautogui
        except Exception:
            self._pag = None
        w, h = _display.resolution()
        self.width, self.height = w or 1920, h or 1080
        if self._pag:
            try:
                self.width, self.height = self._pag.size()
            except Exception:
                pass

    # -- helpers -------------------------------------------------------
    def _check_xy(self, x, y):
        ok, cx, cy = _perm.validate_coordinates(
            x, y, self.width, self.height)
        if not ok:
            return False, "coordinates out of screen bounds"
        return True, (cx, cy)

    def open_app(self, app):
        from ..control import apps as _apps
        return _apps.launch(app)

    def focus_app(self, app):
        from ..control import apps as _apps
        return _apps.focus(app)

    def close_app(self, app):
        from ..control import apps as _apps
        return _apps.close(app)

    def click(self, x, y, button="left"):
        good, res = self._check_xy(x, y)
        if not good:
            return False, res
        cx, cy = res
        if self._pag:
            try:
                self._pag.click(cx, cy, button=button)
                return True, "clicked %d,%d" % (cx, cy)
            except Exception as exc:
                return False, str(exc)
        # xdotool fallback
        btn = {"left": "1", "middle": "2", "right": "3"}.get(button, "1")
        try:
            subprocess.run(["xdotool", "mousemove", str(cx), str(cy),
                            "click", btn], check=True, timeout=10)
            return True, "clicked %d,%d" % (cx, cy)
        except (OSError, subprocess.SubprocessError) as exc:
            return False, "no input backend: %s" % exc

    def move(self, x, y):
        good, res = self._check_xy(x, y)
        if not good:
            return False, res
        cx, cy = res
        if self._pag:
            try:
                self._pag.moveTo(cx, cy)
                return True, "moved"
            except Exception as exc:
                return False, str(exc)
        try:
            subprocess.run(["xdotool", "mousemove", str(cx), str(cy)],
                           check=True, timeout=10)
            return True, "moved"
        except (OSError, subprocess.SubprocessError) as exc:
            return False, "no input backend: %s" % exc

    def scroll(self, dx, dy):
        if self._pag:
            try:
                self._pag.scroll(int(dy or 0) * 40)
                self._pag.hscroll(int(dx or 0) * 40)
                return True, "scrolled"
            except Exception as exc:
                return False, str(exc)
        btn = "4" if int(dy or 0) > 0 else "5"
        try:
            subprocess.run(["xdotool", "click", btn], check=True, timeout=10)
            return True, "scrolled"
        except (OSError, subprocess.SubprocessError) as exc:
            return False, "no input backend: %s" % exc

    def key(self, key):
        allowed = {
            "enter", "tab", "esc", "escape", "space", "backspace", "delete",
            "up", "down", "left", "right", "home", "end", "pageup",
            "pagedown", "f1", "f2", "f3", "f4", "f5", "f6", "f7", "f8",
            "f9", "f10", "f11", "f12",
        }
        k = str(key).lower()
        if len(k) == 1:
            pass  # single chars are fine
        elif k not in allowed:
            return False, "key '%s' is not allowed" % key
        if self._pag:
            try:
                self._pag.press(k if k != "esc" else "esc")
                return True, "pressed %s" % k
            except Exception as exc:
                return False, str(exc)
        try:
            subprocess.run(["xdotool", "key", k], check=True, timeout=10)
            return True, "pressed %s" % k
        except (OSError, subprocess.SubprocessError) as exc:
            return False, "no input backend: %s" % exc

    def hotkey(self, keys):
        keys = [str(k).lower() for k in (keys or [])][:4]
        if not keys or len(keys) > 4:
            return False, "bad hotkey"
        dangerous = {"ctrl+alt+f1", "ctrl+alt+f2", "ctrl+alt+delete"}
        if "+".join(keys) in dangerous:
            return False, "hotkey blocked by safety policy"
        if self._pag:
            try:
                self._pag.hotkey(*keys)
                return True, "hotkey %s" % "+".join(keys)
            except Exception as exc:
                return False, str(exc)
        try:
            subprocess.run(["xdotool", "key", "+".join(keys)], check=True,
                           timeout=10)
            return True, "hotkey %s" % "+".join(keys)
        except (OSError, subprocess.SubprocessError) as exc:
            return False, "no input backend: %s" % exc

    def type_text(self, text):
        text = str(text or "")[:500]
        for bad in _perm.DENY_SUBSTRINGS:
            if bad in text.lower():
                return False, "typed text blocked by safety policy"
        if self._pag:
            try:
                self._pag.write(text, interval=0.01)
                return True, "typed %d chars" % len(text)
            except Exception as exc:
                return False, str(exc)
        try:
            subprocess.run(["xdotool", "type", "--delay", "5", text],
                           check=True, timeout=30)
            return True, "typed %d chars" % len(text)
        except (OSError, subprocess.SubprocessError) as exc:
            return False, "no input backend: %s" % exc

    def open_url(self, url):
        url = str(url or "")
        if not (url.startswith("http://") or url.startswith("https://")):
            return False, "only http(s) URLs may be opened"
        try:
            subprocess.Popen(["xdg-open", url], stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL,
                             stdin=subprocess.DEVNULL,
                             start_new_session=True)
            return True, "opened URL"
        except OSError as exc:
            return False, str(exc)

    def open_path(self, path):
        import os
        from ..control import filesops as _files
        p = os.path.abspath(os.path.expanduser(str(path or "")))
        if not _files._allowed(p):
            return False, "path is outside allowed roots"
        try:
            subprocess.Popen(["xdg-open", p], stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL,
                             stdin=subprocess.DEVNULL,
                             start_new_session=True)
            return True, "opened path"
        except OSError as exc:
            return False, str(exc)

    def shell(self, command, args):
        argv_tmpl, _ = _perm.SHELL_ALLOWLIST.get(command, (None, None))
        if argv_tmpl is None:
            return False, "shell command not allowlisted"
        argv = []
        for tok in argv_tmpl:
            if tok == "{ssid}":
                ssid = str((args or {}).get("ssid", "")).strip()
                if not ssid or len(ssid) > 64 or any(
                        c in ssid for c in ";|&$`\\\"'"):
                    return False, "bad ssid argument"
                argv.append(ssid)
            elif tok == "{pkg}":
                pkg = str((args or {}).get("pkg", "")).strip()
                if not pkg or len(pkg) > 64 or any(
                        c in pkg for c in ";|&$`\\\"' /"):
                    return False, "bad pkg argument"
                argv.append(pkg)
            else:
                argv.append(tok)
        try:
            proc = subprocess.run(argv, capture_output=True, text=True,
                                  timeout=120)
            out = (proc.stdout or "")[-500:]
            return (proc.returncode == 0,
                    out or ("exit %d" % proc.returncode))
        except (OSError, subprocess.SubprocessError) as exc:
            return False, str(exc)

    def screenshot(self):
        from ..system import display as _display
        p = _display.screenshot()
        return (bool(p), p or "screenshot failed")


class AutomationEngine:
    """Validates + executes structured action batches. Thread-safe stop."""

    MAX_BATCH = 30

    def __init__(self, backend=None, config=None):
        self.backend = backend or MockBackend()
        self.config = config
        self._stop = threading.Event()
        self.running = False
        self.last_report = {}

    # -- control -------------------------------------------------------
    def stop(self):
        """Emergency stop — safe to call from any thread (ESC handler)."""
        self._stop.set()

    def reset(self):
        self._stop.clear()
        self.running = False

    @property
    def stop_requested(self):
        return self._stop.is_set()

    def use_real_backend(self):
        self.backend = RealBackend()

    # -- execution ------------------------------------------------------
    def run_batch(self, actions, task="", require_confirm=False,
                  confirm_callback=None):
        """Validate + execute a batch. Returns a report dict.

        require_confirm: CONFIRM-level actions pause for confirm_callback
        (fn(question) → bool). When no callback is given, CONFIRM actions
        are skipped and reported as 'needs_confirm'.
        """
        self.reset()
        self.running = True
        actions = list(actions or [])[: self.MAX_BATCH]
        report = {"task": task, "total": len(actions), "done": 0,
                  "skipped": 0, "failed": 0, "denied": [],
                  "needs_confirm": [], "results": [], "stopped": False,
                  "say": ""}
        try:
            for action in actions:
                if self.stop_requested:
                    raise StopRequested()
                verdict = _perm.classify_action(action)
                atype = str(action.get("type", ""))
                if verdict.level == _perm.DENY:
                    report["denied"].append(
                        {"action": action, "reason": verdict.reason})
                    report["failed"] += 1
                    continue
                if verdict.level == _perm.CONFIRM and require_confirm:
                    if confirm_callback is None:
                        report["needs_confirm"].append(action)
                        report["skipped"] += 1
                        continue
                    try:
                        approved = bool(confirm_callback(
                            "Allow automation action: %s?" % atype))
                    except Exception:
                        approved = False
                    if not approved:
                        report["skipped"] += 1
                        report["results"].append(
                            {"action": atype, "ok": False,
                             "say": "not approved"})
                        continue
                ok, say = self._execute_one(action)
                report["results"].append(
                    {"action": atype, "ok": ok, "say": say})
                if ok:
                    report["done"] += 1
                else:
                    report["failed"] += 1
        except StopRequested:
            report["stopped"] = True
        finally:
            self.running = False

        if report["stopped"]:
            report["say"] = "Stopped. %d of %d actions done." % (
                report["done"], report["total"])
        elif report["needs_confirm"]:
            report["say"] = ("%d actions need your confirmation first." %
                             len(report["needs_confirm"]))
        elif report["failed"]:
            report["say"] = "%d of %d actions done, %d failed." % (
                report["done"], report["total"], report["failed"])
        else:
            report["say"] = "Done — %d actions executed." % report["done"]
        self.last_report = report
        return report

    def _execute_one(self, action):
        from ..system import audio as _audio
        from ..system import display as _display
        from ..system import network as _net
        from ..system import bluetooth as _bt
        from ..system import power as _power
        from .. import notify as _notify

        atype = str(action.get("type", "")).lower()
        b = self.backend
        if atype == "open_app":
            return b.open_app(str(action.get("app", "")))
        if atype == "focus_app":
            return b.focus_app(str(action.get("app", "")))
        if atype == "close_app":
            return b.close_app(str(action.get("app", "")))
        if atype == "wait":
            secs = min(30.0, max(0.1, float(action.get("seconds", 1))))
            end = time.time() + secs
            while time.time() < end:
                if self.stop_requested:
                    raise StopRequested()
                time.sleep(0.05)
            return True, "waited %.1fs" % secs
        if atype == "click":
            return b.click(action.get("x", 0), action.get("y", 0),
                           str(action.get("button", "left")))
        if atype == "move":
            return b.move(action.get("x", 0), action.get("y", 0))
        if atype == "scroll":
            return b.scroll(action.get("dx", 0), action.get("dy", -3))
        if atype == "key":
            return b.key(str(action.get("key", "enter")))
        if atype == "hotkey":
            return b.hotkey(action.get("keys", []))
        if atype == "type":
            return b.type_text(str(action.get("text", "")))
        if atype == "screenshot":
            return b.screenshot()
        if atype == "notify":
            ok = _notify.send(str(action.get("title", "JARVIS")),
                              str(action.get("body", "")))
            return True, "notified" if ok else "logged"
        if atype == "set_volume":
            return _audio.set_volume(action.get("level", 50))
        if atype == "mute":
            return _audio.mute(bool(action.get("on", True)))
        if atype == "set_brightness":
            return _display.set_brightness(action.get("level", 70))
        if atype == "wifi_on":
            return _net.wifi(True)
        if atype == "wifi_off":
            return _net.wifi(False)
        if atype == "bluetooth_on":
            return _bt.set_power(True)
        if atype == "bluetooth_off":
            return _bt.set_power(False)
        if atype == "lock_screen":
            return _power.lock()
        if atype == "open_url":
            return b.open_url(str(action.get("url", "")))
        if atype == "open_path":
            return b.open_path(str(action.get("path", "")))
        if atype == "shell":
            return b.shell(str(action.get("command", "")),
                           action.get("args", {}))
        return False, "unsupported action '%s'" % atype
