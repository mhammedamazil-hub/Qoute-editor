"""Application registry, launcher, and installer recipes.

Design rules:
- Launching uses .desktop files first, then executable names. Never shell.
- NOTHING proprietary is bundled or redistributed. Install recipes either
  use Debian apt (free software) or guide the user to the vendor's official
  source (VS Code / Brave / Discord) with explicit confirmation.
- All installs need CONFIRM (see permissions.py) and run in a terminal so
  the user sees exactly what happens.
"""
from __future__ import annotations

import os
import shutil
import subprocess

# app_id → {name, desktop ids, execs, install recipe}
# recipe kinds: apt | vendor-script:<helper> | none
REGISTRY = {
    "files":    {"name": "Files", "desktop": ["thunar", "org.xfce.thunar"],
                 "execs": ["jarvis-files", "thunar"], "install": None},
    "terminal": {"name": "Terminal", "desktop": ["lxterminal", "org.lxde.lxterminal"],
                 "execs": ["jarvis-terminal", "lxterminal", "xterm"],
                 "install": None},
    "vscode":   {"name": "VS Code", "desktop": ["code", "visual-studio-code"],
                 "execs": ["code", "code-insiders"],
                 "install": ("vendor-script", "vscode")},
    "brave":    {"name": "Brave", "desktop": ["brave-browser", "brave"],
                 "execs": ["brave-browser", "brave"],
                 "install": ("vendor-script", "brave")},
    "firefox":  {"name": "Firefox", "desktop": ["firefox-esr", "firefox"],
                 "execs": ["firefox-esr", "firefox"], "install": ("apt", "firefox-esr")},
    "discord":  {"name": "Discord", "desktop": ["discord", "Discord"],
                 "execs": ["Discord", "discord"],
                 "install": ("vendor-script", "discord")},
    "blender":  {"name": "Blender", "desktop": ["blender"],
                 "execs": ["blender"], "install": ("apt", "blender")},
    "settings": {"name": "Settings", "desktop": ["jarvis-settings"],
                 "execs": ["jarvis-settings"], "install": None},
    "monitor":  {"name": "System Monitor", "desktop": ["jarvis-monitor"],
                 "execs": ["jarvis-monitor", "htop"], "install": None},
    "editor":   {"name": "Text Editor", "desktop": ["jarvis-editor", "mousepad"],
                 "execs": ["jarvis-editor", "mousepad"], "install": None},
    "camera":   {"name": "Camera", "desktop": ["cheese", "org.gnome.Cheese"],
                 "execs": ["cheese"], "install": ("apt", "cheese")},
    "store":    {"name": "App Manager", "desktop": ["jarvis-appmanager"],
                 "execs": ["jarvis-appmanager"], "install": None},
    "vlc":      {"name": "VLC", "desktop": ["vlc"], "execs": ["vlc"],
                 "install": ("apt", "vlc")},
    "gimp":     {"name": "GIMP", "desktop": ["gimp"], "execs": ["gimp"],
                 "install": ("apt", "gimp")},
    "git":      {"name": "Git", "desktop": [], "execs": ["git"],
                 "install": ("apt", "git")},
    "python":   {"name": "Python", "desktop": [], "execs": ["python3"],
                 "install": ("apt", "python3")},
}

# Friendly names users might say → app_id
NAME_INDEX = {}
for _aid, _meta in REGISTRY.items():
    NAME_INDEX[_aid] = _aid
    NAME_INDEX[_meta["name"].lower()] = _aid


def resolve(name):
    """Resolve free text to an app_id, or '' when unknown."""
    if not name:
        return ""
    key = str(name).strip().lower()
    if key in REGISTRY:
        return key
    if key in NAME_INDEX:
        return NAME_INDEX[key]
    # executable present on PATH counts as launchable too
    if shutil.which(key):
        return key
    return ""


def is_installed(app_id):
    meta = REGISTRY.get(app_id)
    if meta:
        for exe in meta["execs"]:
            if shutil.which(exe):
                return True
        return False
    return bool(shutil.which(app_id))


def _launch_argv(app_id):
    meta = REGISTRY.get(app_id)
    if meta:
        for exe in meta["execs"]:
            if shutil.which(exe):
                return [exe]
        # try gio/gtk-launch of desktop file as last resort
        for desk in meta["desktop"]:
            if shutil.which("gtk-launch"):
                return ["gtk-launch", desk]
    elif shutil.which(app_id):
        return [app_id]
    return []


def launch(app_id, args=None):
    """Launch an app detached. Returns (ok, message). No shell involved."""
    argv = _launch_argv(app_id)
    if not argv:
        meta = REGISTRY.get(app_id, {})
        label = meta.get("name", app_id)
        if meta.get("install"):
            return False, "%s is not installed. Say 'install %s' to install it." % (
                label, label)
        return False, "I can't find %s." % label
    try:
        subprocess.Popen(argv + list(args or []),
                         stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL,
                         stdin=subprocess.DEVNULL,
                         start_new_session=True)
        label = REGISTRY.get(app_id, {}).get("name", app_id)
        return True, "%s opened." % label
    except OSError:
        return False, "Could not start %s." % app_id


def close(app_id):
    """Close app instances via pkill on known exec names (safe, no -9)."""
    meta = REGISTRY.get(app_id)
    names = (meta["execs"] if meta else [app_id])
    if not shutil.which("pkill"):
        return False, "Process control (pkill) is not available."
    closed = False
    for exe in names:
        base = os.path.basename(exe)
        try:
            rc = subprocess.run(["pkill", "-x", base],
                                capture_output=True, timeout=5).returncode
            closed = closed or (rc == 0)
        except (OSError, subprocess.SubprocessError):
            pass
    label = meta["name"] if meta else app_id
    return (True, "%s closed." % label) if closed else \
        (False, "%s doesn't seem to be running." % label)


def focus(app_id):
    """Raise app window via wmctrl/xdotool when available."""
    meta = REGISTRY.get(app_id, {})
    label = meta.get("name", app_id)
    if shutil.which("wmctrl"):
        try:
            subprocess.run(["wmctrl", "-a", label], capture_output=True,
                           timeout=5)
            return True, "Switched to %s." % label
        except (OSError, subprocess.SubprocessError):
            pass
    if shutil.which("xdotool"):
        try:
            proc = subprocess.run(
                ["xdotool", "search", "--onlyvisible", "--name", label],
                capture_output=True, text=True, timeout=5)
            wins = proc.stdout.strip().split()
            if wins:
                subprocess.run(["xdotool", "windowactivate", wins[0]],
                               capture_output=True, timeout=5)
                return True, "Switched to %s." % label
        except (OSError, subprocess.SubprocessError):
            pass
    # fallback: launching usually focuses the existing instance
    return launch(app_id)


def install_plan(app_id):
    """Return (kind, detail, human_steps) describing how install works."""
    meta = REGISTRY.get(app_id)
    if not meta or not meta.get("install"):
        if is_installed(app_id):
            return ("none", "", ["%s is already installed." % app_id])
        return ("none", "", ["I don't know how to install '%s' yet." % app_id])
    kind, detail = meta["install"]
    if kind == "apt":
        return ("apt", detail, [
            "I will run: sudo apt-get update && sudo apt-get install -y %s" % detail,
            "from the official Debian repositories."])
    scripts = {
        "vscode": [
            "Adds Microsoft's official VS Code apt repository,",
            "then installs the 'code' package."],
        "brave": [
            "Adds Brave's official apt repository (brave-browser-apt-release),",
            "then installs the 'brave-browser' package."],
        "discord": [
            "Downloads the official Discord .deb from discord.com,",
            "verifies it is a Debian package, then installs it."],
    }
    return ("vendor-script", detail, scripts.get(detail, ["Vendor install."]))


def install(app_id, passwordless=False):
    """Run the install recipe in a visible terminal. Returns (ok, message).

    Must only be called AFTER user confirmation (Core enforces this).
    """
    kind, detail, _ = install_plan(app_id)
    label = REGISTRY.get(app_id, {}).get("name", app_id)
    if kind == "none":
        return False, "I don't know how to install '%s'." % app_id
    helper = shutil.which("jarvis-app-install") or \
        "/usr/lib/jarvisos/helpers/jarvis-app-install"
    if not (os.path.isfile(helper) and os.access(helper, os.X_OK)):
        return False, "Installer helper is missing from this system."
    term = shutil.which("lxterminal") or shutil.which("xterm")
    cmd = [helper, kind, detail]
    try:
        if term:
            subprocess.Popen([term, "-e"] + cmd,
                             stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL,
                             stdin=subprocess.DEVNULL,
                             start_new_session=True)
        else:  # headless fallback: run directly, capture output
            proc = subprocess.run(cmd, capture_output=True, text=True,
                                  timeout=600)
            return (True, "%s installed." % label) if proc.returncode == 0 \
                else (False, "Install failed: %s" % proc.stderr[-300:])
        return True, "Installing %s — watch the terminal window." % label
    except (OSError, subprocess.SubprocessError):
        return False, "Could not start the installer."
