"""Natural-language command understanding (local, offline, fast).

parse(text) → Intent(name, slots, raw, confidence). No network, no ML model:
deterministic rules + fuzzy app matching, so basic control works offline and
in milliseconds on weak CPUs. Anything not understood falls back to
'ai.ask' / 'automation.run_task' when a cloud provider is configured.
"""
from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field

# Canonical app ids → match aliases. Launch details live in control/apps.py.
APP_ALIASES = {
    "files": ("files", "file manager", "filemanager", "folders", "thunar"),
    "terminal": ("terminal", "console", "shell", "command line", "lxterminal"),
    "vscode": ("vs code", "vscode", "code", "visual studio code", "vscodium"),
    "brave": ("brave", "brave browser"),
    "firefox": ("firefox", "browser", "web browser", "firefox esr"),
    "discord": ("discord",),
    "blender": ("blender",),
    "settings": ("settings", "system settings", "preferences", "control panel"),
    "monitor": ("system monitor", "task manager", "monitor", "htop"),
    "editor": ("text editor", "editor", "notepad", "mousepad"),
    "camera": ("camera", "webcam", "cheese"),
    "store": ("app store", "app manager", "software", "software center"),
}

FOLDER_ALIASES = {
    "home": ("home", "home folder"),
    "documents": ("documents", "docs", "my documents"),
    "downloads": ("downloads", "download", "my downloads"),
    "pictures": ("pictures", "images", "photos", "my pictures"),
    "music": ("music", "my music"),
    "videos": ("videos", "movies", "my videos"),
    "desktop": ("desktop",),
    "trash": ("trash", "recycle bin", "bin"),
}


@dataclass
class Intent:
    name: str
    slots: dict = field(default_factory=dict)
    raw: str = ""
    confidence: float = 1.0

    def __repr__(self):  # pragma: no cover - debugging helper
        return "Intent(%s, %s, conf=%.2f)" % (self.name, self.slots, self.confidence)


def _norm(text):
    text = (text or "").strip().lower()
    text = re.sub(r"^(jarvis|hey jarvis|ok jarvis)[, ]*", "", text).strip()
    text = re.sub(r"[?!.,]+$", "", text).strip()
    return re.sub(r"\s+", " ", text)


def match_app(text):
    """Return canonical app id for free text, or '' if none matches."""
    text = _norm(text)
    for app_id, aliases in APP_ALIASES.items():
        for alias in aliases:
            if alias in text:
                return app_id
    # fuzzy fallback on single words
    words = text.split()
    candidates = [(a, i) for i, als in APP_ALIASES.items() for a in als]
    for word in words:
        if len(word) < 4:
            continue
        names = [c[0] for c in candidates]
        hit = difflib.get_close_matches(word, names, n=1, cutoff=0.85)
        if hit:
            for alias, app_id in candidates:
                if alias == hit[0]:
                    return app_id
    return ""


def match_folder(text):
    text = _norm(text)
    for folder, aliases in FOLDER_ALIASES.items():
        for alias in aliases:
            if re.search(r"\b%s\b" % re.escape(alias), text):
                return folder
    return ""


def _num(text, default=None):
    m = re.search(r"(\d{1,3})\s*%?", text)
    if m:
        return max(0, min(100, int(m.group(1))))
    return default


def parse(raw):
    """Parse user text into an Intent. Never raises, never blocks."""
    text = _norm(raw or "")
    if not text:
        return Intent("system.noop", {}, raw, 1.0)

    # --- help ----------------------------------------------------------------
    if re.search(r"\b(what can you do|help|commands|how do i)\b", text):
        return Intent("system.help", {}, raw, 1.0)

    # --- stop / emergency ------------------------------------------------------
    if re.search(r"\b(stop|halt|cancel|abort|enough|shut up)\b", text) and \
            re.search(r"\b(automation|task|that|it|everything|music|speaking)\b|\bstop\b", text):
        return Intent("automation.stop", {}, raw, 0.95)

    # --- power -----------------------------------------------------------------
    if re.search(r"\b(shut ?down|power off|turn off (the )?(computer|pc|laptop|system))\b", text):
        return Intent("power.shutdown", {}, raw, 1.0)
    if re.search(r"\b(restart|reboot)\b", text):
        return Intent("power.reboot", {}, raw, 1.0)
    if re.search(r"\b(suspend|sleep|hibernate)\b", text):
        return Intent("power.suspend", {}, raw, 0.95)
    if re.search(r"\b(lock( the)? (screen|computer|pc|laptop)?|lock screen)\b", text):
        return Intent("power.lock", {}, raw, 1.0)
    if re.search(r"\b(log ?out|sign ?out)\b", text):
        return Intent("session.logout", {}, raw, 1.0)

    # --- stats / status ----------------------------------------------------------
    if re.search(r"\b(what('| i)s|what is|show|how much|check)\b.*\b(ram|memory)\b", text) or \
            re.search(r"\b(ram|memory) (usage|use|status)\b", text):
        return Intent("system.ram", {}, raw, 0.95)
    if re.search(r"\b(temperature|temps?|how hot|overheat)\b", text):
        return Intent("system.temperature", {}, raw, 0.9)
    if re.search(r"\bcpu\b", text) and re.search(r"\b(usage|use|load|status|using|hot|temp)", text):
        return Intent("system.cpu", {}, raw, 0.95)
    if re.search(r"\b(disk|storage|space)\b", text) and re.search(r"\b(usage|use|free|left|status|full)\b", text):
        return Intent("system.disk", {}, raw, 0.95)
    if re.search(r"\b(battery|charge|power level)\b", text):
        return Intent("system.battery", {}, raw, 0.95)
    if re.search(r"\b(processes|task manager|what('| i)s running|top processes)\b", text):
        return Intent("system.processes", {}, raw, 0.9)

    # --- wifi ---------------------------------------------------------------------
    if re.search(r"\bwifi\b.*\b(off|disable|turn off)\b|\b(turn off|disable) wifi\b", text):
        return Intent("network.wifi_off", {}, raw, 1.0)
    if re.search(r"\bwifi\b.*\b(on|enable|turn on)\b|\b(turn on|enable) wifi\b", text):
        return Intent("network.wifi_on", {}, raw, 1.0)
    m = re.search(r"\bconnect (to )?wifi (.+)", text)
    if m or (re.search(r"\bwifi\b", text) and re.search(r"\bconnect\b", text)):
        ssid = (m.group(2).strip() if m else "")
        return Intent("network.wifi_connect", {"ssid": ssid}, raw, 0.9)
    if re.search(r"\b(list|scan|show|find).*(wifi|networks)|wifi networks\b", text):
        return Intent("network.wifi_list", {}, raw, 0.95)
    if re.search(r"\b(disconnect|forget).*(wifi|network)|wifi.*disconnect\b", text):
        return Intent("network.wifi_disconnect", {}, raw, 0.9)
    if re.search(r"\b(ip address|my ip|network status|internet status|am i online)\b", text):
        return Intent("network.status", {}, raw, 0.9)

    # --- bluetooth ------------------------------------------------------------------
    if re.search(r"\bbluetooth\b.*\b(off|disable|turn off)\b|\b(turn off|disable) bluetooth\b", text):
        return Intent("bluetooth.off", {}, raw, 1.0)
    if re.search(r"\bbluetooth\b.*\b(on|enable|turn on)\b|\b(turn on|enable|connect) bluetooth\b", text):
        return Intent("bluetooth.on", {}, raw, 1.0)
    if re.search(r"\bbluetooth\b", text) and re.search(r"\b(pair|connect)\b", text):
        dev = re.sub(r".*\b(pair|connect)\b", "", text).strip(" .")
        dev = re.sub(r"^(to|with|my)\s+", "", dev)
        return Intent("bluetooth.connect", {"device": dev}, raw, 0.85)
    if re.search(r"\bbluetooth\b", text) and re.search(r"\b(list|scan|show|devices|find)\b", text):
        return Intent("bluetooth.list", {}, raw, 0.95)
    # pair/connect without the keyword ("pair my headphones") → bluetooth
    if re.search(r"\b(pair|connect)\b", text) and not re.search(r"\bwifi\b", text):
        dev = re.sub(r".*\b(pair|connect)\b", "", text).strip(" .")
        dev = re.sub(r"^(to|with|my)\s+", "", dev)
        if dev and not re.search(r"\b(screen|monitor|display)\b", text):
            return Intent("bluetooth.connect", {"device": dev}, raw, 0.8)

    # --- audio ------------------------------------------------------------------------
    if re.search(r"\b(mute|unmute).*(mic|microphone)|mic.*mute\b", text):
        return Intent("audio.mic_mute_toggle", {}, raw, 0.9)
    if re.search(r"\b(mute|silence)(\b| the)", text) and not re.search(r"mic", text):
        return Intent("audio.mute", {}, raw, 0.95)
    if re.search(r"\bunmute\b", text):
        return Intent("audio.unmute", {}, raw, 0.95)
    if re.search(r"\b(volume|sound|louder|quieter)\b", text):
        if re.search(r"\b(up|louder|increase|raise|higher)\b", text):
            return Intent("audio.volume_up", {}, raw, 0.95)
        if re.search(r"\b(down|quieter|decrease|lower|softer)\b", text):
            return Intent("audio.volume_down", {}, raw, 0.95)
        n = _num(text)
        if n is not None or re.search(r"\b(set|to)\b", text):
            return Intent("audio.volume_set", {"level": n if n is not None else 50}, raw, 0.9)

    # --- display -------------------------------------------------------------------------
    if re.search(r"\b(brightness|bright|dim|screen light)\b", text):
        if re.search(r"\b(up|brighter|increase|raise|higher|max)\b", text):
            return Intent("display.brightness_up", {}, raw, 0.9)
        if re.search(r"\b(down|dimmer|decrease|lower|darker|min)\b", text):
            return Intent("display.brightness_down", {}, raw, 0.9)
        n = _num(text)
        return Intent("display.brightness_set", {"level": n if n is not None else 70}, raw, 0.85)
    if re.search(r"\b(screenshot|screen ?shot|capture (the )?screen|take a picture of.*screen)\b", text):
        return Intent("display.screenshot", {}, raw, 1.0)
    if re.search(r"\b(night (light|mode)|blue light|redshift)\b", text):
        mode = "off" if re.search(r"\b(off|disable)\b", text) else "on"
        return Intent("display.night_mode", {"mode": mode}, raw, 0.9)
    if re.search(r"\b(wallpaper|background)\b", text):
        return Intent("display.wallpaper", {}, raw, 0.85)

    # --- files -----------------------------------------------------------------------------
    if re.search(r"\b(recent files|recently (opened|used)|my recent)\b", text):
        return Intent("files.recent", {}, raw, 1.0)
    m = re.search(r"\b(search|find|look for).*(files?|folders?|documents?).*for (.+)", text)
    if m:
        return Intent("files.search", {"query": m.group(3).strip()}, raw, 0.95)
    m = re.search(r"\b(find|search|locate) (.+)", text)
    if m and not re.search(r"\b(wifi|bluetooth|web|google|online)\b", text):
        return Intent("files.search", {"query": m.group(2).strip()}, raw, 0.7)
    if re.search(r"\b(empty|clear).*(trash|bin|recycle)\b", text):
        return Intent("files.empty_trash", {}, raw, 0.95)
    if re.search(r"\b(delete|remove|trash|throw away)\b", text):
        target = re.sub(r".*\b(delete|remove|trash|throw away)\b", "", text).strip(" .")
        return Intent("files.delete", {"target": target}, raw, 0.8)
    m = re.search(r"\b(create|make|new) (a )?(new )?(folder|directory)( (called|named) (.+))?", text)
    if m:
        return Intent("files.new_folder", {"name": (m.group(6) or "").strip()}, raw, 0.9)
    folder = match_folder(text)
    if folder and re.search(r"\b(open|show|go to|browse)\b", text):
        return Intent("files.open_folder", {"folder": folder}, raw, 0.95)
    if re.search(r"\b(open|show).*(home|file manager|files)\b", text):
        return Intent("files.open_folder", {"folder": "home"}, raw, 0.85)

    # --- app install/remove -------------------------------------------------------------------
    m = re.search(r"\b(install|get|download|add) ([a-z0-9+_.\- ]+)", text)
    if m and not re.search(r"\b(update|upgrade)\b", text):
        app = match_app(m.group(2)) or m.group(2).strip()
        return Intent("apps.install", {"app": app}, raw, 0.85)
    m = re.search(r"\b(uninstall|remove) ([a-z0-9+_.\- ]+)", text)
    if m:
        app = match_app(m.group(2)) or m.group(2).strip()
        return Intent("apps.remove", {"app": app}, raw, 0.85)
    if re.search(r"\b(update|upgrade).*(system|everything|all|os)|system update\b", text):
        return Intent("apps.update_system", {}, raw, 0.9)

    # --- open / close / focus apps ---------------------------------------------------------------
    app = match_app(text)
    if app:
        if re.search(r"\b(close|quit|exit|kill)\b", text):
            return Intent("apps.close", {"app": app}, raw, 0.95)
        if re.search(r"\b(switch to|focus|bring|go to)\b", text):
            return Intent("apps.focus", {"app": app}, raw, 0.9)
        if re.search(r"\b(open|launch|start|run|show)\b", text) or len(text.split()) <= 3:
            return Intent("apps.open", {"app": app}, raw, 0.95)
        # bare app mention ("blender", "discord please") → open
        if len(text.split()) <= 4:
            return Intent("apps.open", {"app": app}, raw, 0.75)

    # --- settings sections ----------------------------------------------------------------------------
    m = re.search(r"\bopen (.*)?settings( (for|of) (.+))?", text)
    if m or text in ("settings", "open settings"):
        section = (m.group(4).strip() if m and m.group(4) else "")
        return Intent("settings.open", {"section": section}, raw, 0.9)

    # --- AI vision / automation ----------------------------------------------------------------------------
    if re.search(r"\b(look at|analyze|analyse|describe|what('| i)s on|read).*(screen|display|window)\b", text):
        return Intent("ai.analyze_screen", {}, raw, 0.95)
    if re.search(r"\b(do|perform|automate|handle|take care of)\b", text) and len(text.split()) > 2:
        task = re.sub(r"^(please\s+)?(jarvis\s+)?(can you\s+)?", "", text).strip()
        return Intent("automation.run_task", {"task": task}, raw, 0.7)

    # --- questions → AI chat ----------------------------------------------------------------------------------
    if re.search(r"^(what|who|when|where|why|how|which|whose|whom|is|are|can|could|should|would|will|do|does|did|tell me|explain|define|search the web for|google)\b", text):
        return Intent("ai.ask", {"question": raw.strip()}, raw, 0.6)

    # --- dangerous patterns → explicit deny intents --------------------------------------------------------------
    if re.search(r"\b(format|wipe|erase).*(disk|drive|usb|partition)|factory reset\b", text):
        return Intent("disk.format", {}, raw, 0.9)
    if re.search(r"\bpartition\b", text):
        return Intent("disk.partition", {}, raw, 0.8)

    return Intent("system.unknown", {"text": raw.strip()}, raw, 0.0)
