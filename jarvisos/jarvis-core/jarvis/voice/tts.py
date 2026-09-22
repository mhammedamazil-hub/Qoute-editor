"""Text-to-speech replies (espeak-ng; optional piper). Async + stoppable."""
from __future__ import annotations

import shutil
import subprocess
import threading

_lock = threading.Lock()
_current = None


def available():
    return bool(shutil.which("espeak-ng") or shutil.which("espeak") or
                shutil.which("piper"))


def speak(text, config=None, blocking=False):
    """Speak text in the background. Returns immediately unless blocking."""
    text = (text or "").strip()
    if not text:
        return False
    if config is not None and not config.get("voice.speak_replies", True):
        return False
    argv = None
    if shutil.which("espeak-ng"):
        rate = 175
        if config is not None:
            rate = int(config.get("voice.rate", 175) or 175)
        argv = ["espeak-ng", "-s", str(rate), text]
    elif shutil.which("espeak"):
        argv = ["espeak", text]
    if argv is None:
        return False

    def _run():
        global _current
        try:
            proc = subprocess.Popen(argv, stdout=subprocess.DEVNULL,
                                    stderr=subprocess.DEVNULL,
                                    stdin=subprocess.DEVNULL)
            with _lock:
                _current = proc
            proc.wait(timeout=60)
        except (OSError, subprocess.SubprocessError):
            pass
        finally:
            with _lock:
                _current = None

    if blocking:
        _run()
        return True
    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    return True


def stop_speaking():
    with _lock:
        proc = _current
    if proc is not None:
        try:
            proc.terminate()
        except (OSError, subprocess.SubprocessError):
            pass
