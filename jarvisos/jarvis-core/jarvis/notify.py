"""Lightweight notifications: desktop bubble + persistent log.

Order: notify-send (Dunst) → log file + stdout. Never blocks, never raises.
The shell's right panel tails the same log file.
"""
from __future__ import annotations

import datetime
import os
import shutil
import subprocess

LOG_PATH = os.path.join(
    os.path.expanduser("~"), ".local", "share", "jarvisos", "notifications.log")


def send(title, body="", icon="jarvis", urgency="normal"):
    """Send a notification. Returns True if a desktop bubble was shown."""
    line = "%s [%s] %s\n" % (
        datetime.datetime.now().strftime("%H:%M:%S"), title, body)
    try:
        os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
        with open(LOG_PATH, "a", encoding="utf-8") as fh:
            fh.write(line)
        # keep the log bounded (last ~500 lines)
        try:
            with open(LOG_PATH, "r", encoding="utf-8") as fh:
                lines = fh.readlines()
            if len(lines) > 500:
                with open(LOG_PATH, "w", encoding="utf-8") as fh:
                    fh.writelines(lines[-500:])
        except OSError:
            pass
    except OSError:
        pass

    if shutil.which("notify-send"):
        try:
            subprocess.Popen(
                ["notify-send", "--app-name=JARVIS", "--icon=%s" % icon,
                 "--urgency=%s" % urgency, str(title), str(body)],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL, start_new_session=True)
            return True
        except OSError:
            pass
    return False


def recent(limit=20):
    try:
        with open(LOG_PATH, "r", encoding="utf-8") as fh:
            return fh.readlines()[-limit:]
    except OSError:
        return []
