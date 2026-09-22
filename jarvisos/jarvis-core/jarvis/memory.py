"""Lightweight local memory: plain JSON, no database, disableable.

Stores small preferences/facts ("call me X", "my wifi is Y", "I use Blender").
AI providers may receive relevant facts only when memory is enabled.
"""
from __future__ import annotations

import json
import os
import re
import time

MEMORY_FILE = os.path.join(
    os.path.expanduser("~"), ".config", "jarvisos", "memory.json")


class Memory:
    def __init__(self, path=None, enabled=True):
        self.path = path or MEMORY_FILE
        self.enabled = enabled
        self._data = {"facts": [], "prefs": {}}
        self._load()

    def _load(self):
        try:
            with open(self.path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            if isinstance(data, dict):
                self._data = {"facts": data.get("facts", []),
                              "prefs": data.get("prefs", {})}
        except (OSError, ValueError):
            pass

    def _save(self):
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(self._data, fh, indent=2)
            os.replace(tmp, self.path)
        except OSError:
            pass

    # -- API -----------------------------------------------------------
    def remember(self, fact):
        """Store a fact string. Returns False when disabled/empty."""
        if not self.enabled or not (fact or "").strip():
            return False
        fact = fact.strip()[:280]
        if fact not in self._data["facts"]:
            self._data["facts"].append(fact)
            self._data["facts"] = self._data["facts"][-200:]
            self._save()
        return True

    def set_pref(self, key, value):
        if not self.enabled:
            return False
        self._data["prefs"][str(key)[:64]] = str(value)[:280]
        self._save()
        return True

    def recall(self, query="", limit=8):
        """Return up to `limit` facts/prefs relevant to query (or newest)."""
        if not self.enabled:
            return []
        facts = list(self._data["facts"])
        if query:
            words = set(re.findall(r"[a-z0-9]+", query.lower()))
            scored = sorted(
                facts,
                key=lambda f: len(words & set(re.findall(r"[a-z0-9]+", f.lower()))),
                reverse=True)
            facts = [f for f in scored if
                     words & set(re.findall(r"[a-z0-9]+", f.lower()))][:limit]
        else:
            facts = facts[-limit:]
        prefs = ["%s: %s" % (k, v) for k, v in self._data["prefs"].items()]
        return (prefs + facts)[:limit]

    def forget(self, snippet):
        before = len(self._data["facts"])
        low = snippet.lower()
        self._data["facts"] = [f for f in self._data["facts"]
                               if low not in f.lower()]
        self._save()
        return before - len(self._data["facts"])

    def clear(self):
        self._data = {"facts": [], "prefs": {}}
        self._save()

    def learn_from_command(self, text):
        """Capture 'remember …', 'my name is …', 'call me …' automatically."""
        if not self.enabled:
            return None
        low = (text or "").strip()
        m = re.match(r"(?:jarvis,?\s*)?remember (?:that )?(.+)", low, re.I)
        if m:
            self.remember(m.group(1))
            return "Remembered."
        m = re.match(r"(?:jarvis,?\s*)?(?:my name is|call me) (.+)", low, re.I)
        if m:
            self.set_pref("name", m.group(1).strip(" ."))
            return "Got it, %s." % m.group(1).strip(" .")
        return None
