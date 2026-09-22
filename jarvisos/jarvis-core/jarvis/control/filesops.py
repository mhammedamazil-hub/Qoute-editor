"""Safe file operations for JARVIS commands.

Rules:
- Operates inside the user's home + /tmp + mounted media only. Anything
  else is refused (system paths need the interactive file manager).
- Delete = move to trash (never unlink). Empty-trash needs CONFIRM.
- Search = fast os.scandir walk with sane skip rules (no `find /`).
"""
from __future__ import annotations

import datetime
import fnmatch
import os
import shutil

FOLDERS = {
    "home": "~",
    "documents": "~/Documents",
    "downloads": "~/Downloads",
    "pictures": "~/Pictures",
    "music": "~/Music",
    "videos": "~/Videos",
    "desktop": "~/Desktop",
    "trash": "~/.local/share/Trash/files",
}

SKIP_DIRS = frozenset({
    ".cache", ".mozilla", ".config/google-chrome", "node_modules", ".git",
    "__pycache__", ".local/share/Trash", ".thumbnails",
})

MAX_SEARCH_RESULTS = 50
MAX_SEARCH_DIRS = 4000


def folder_path(name):
    return os.path.abspath(os.path.expanduser(FOLDERS.get(name, "~")))


def _allowed(path):
    """True when path is inside an allowed root."""
    path = os.path.abspath(os.path.expanduser(path))
    roots = [os.path.abspath(os.path.expanduser("~")), "/tmp",
             "/media", "/mnt"]
    return any(path == r or path.startswith(r + os.sep) for r in roots)


def recent_files(limit=15):
    """Parse GTK RecentManager history (used by file choosers & thunar)."""
    path = os.path.expanduser("~/.local/share/recently-used.xbel")
    items = []
    try:
        import xml.etree.ElementTree as ET
        tree = ET.parse(path)
        for bm in tree.getroot().iter("bookmark"):
            href = bm.get("href", "")
            if href.startswith("file://"):
                local = href[7:]
                items.append({"path": local,
                              "modified": bm.get("modified", "")})
    except (OSError, ValueError):
        pass
    items.sort(key=lambda i: i["modified"], reverse=True)
    return [i for i in items if os.path.exists(i["path"])][:limit]


def search(query, root="~", limit=MAX_SEARCH_RESULTS):
    """Case-insensitive filename search under root. Returns [paths]."""
    query = (query or "").strip().lower()
    if not query:
        return []
    root = os.path.abspath(os.path.expanduser(root))
    if not _allowed(root):
        return []
    hits = []
    seen_dirs = 0
    patterns = ["*%s*" % query]
    for dirpath, dirnames, filenames in os.walk(root):
        seen_dirs += 1
        if seen_dirs > MAX_SEARCH_DIRS:
            break
        dirnames[:] = [d for d in dirnames
                       if d not in SKIP_DIRS and not d.startswith(".")]
        for name in filenames + dirnames:
            if any(fnmatch.fnmatch(name.lower(), p) for p in patterns):
                hits.append(os.path.join(dirpath, name))
                if len(hits) >= limit:
                    return hits
    return hits


def new_folder(name=None, parent="~"):
    parent = os.path.abspath(os.path.expanduser(parent))
    if not _allowed(parent):
        return False, "That location is protected."
    base = (name or "New Folder").strip()[:64] or "New Folder"
    # sanitize: no path separators / hidden tricks
    base = base.replace("/", "_").replace("\\", "_").strip(". ") or "New Folder"
    target = os.path.join(parent, base)
    n = 1
    while os.path.exists(target):
        n += 1
        target = os.path.join(parent, "%s %d" % (base, n))
    try:
        os.makedirs(target)
        return True, "Created folder '%s'." % os.path.basename(target)
    except OSError:
        return False, "Could not create the folder."


def move_to_trash(target):
    """Move a file/folder to the freedesktop trash. Returns (ok, message)."""
    path = os.path.abspath(os.path.expanduser(target or ""))
    if not path or not os.path.exists(path):
        return False, "I can't find '%s'." % (target or "?")
    if not _allowed(path):
        return False, "That location is protected."
    if shutil.which("gio"):
        import subprocess
        try:
            rc = subprocess.run(["gio", "trash", path], capture_output=True,
                                timeout=30).returncode
            return (True, "Moved '%s' to trash." % os.path.basename(path)) \
                if rc == 0 else (False, "Could not trash that item.")
        except (OSError, subprocess.SubprocessError):
            pass
    # manual trash fallback
    try:
        trash = folder_path("trash")
        os.makedirs(trash, exist_ok=True)
        dest = os.path.join(trash, os.path.basename(path))
        n = 1
        while os.path.exists(dest):
            n += 1
            dest = os.path.join(trash, "%s.%d" % (os.path.basename(path), n))
        shutil.move(path, dest)
        return True, "Moved '%s' to trash." % os.path.basename(path)
    except (OSError, shutil.Error):
        return False, "Could not trash that item."


def empty_trash():
    trash = folder_path("trash")
    count = 0
    try:
        for name in os.listdir(trash):
            p = os.path.join(trash, name)
            if os.path.isdir(p) and not os.path.islink(p):
                shutil.rmtree(p, ignore_errors=True)
            else:
                try:
                    os.unlink(p)
                except OSError:
                    pass
            count += 1
        # also clear trashinfo
        info = os.path.expanduser("~/.local/share/Trash/info")
        shutil.rmtree(info, ignore_errors=True)
        os.makedirs(info, exist_ok=True)
        return True, "Trash emptied (%d item%s)." % (
            count, "" if count == 1 else "s")
    except OSError:
        return False, "Could not empty the trash."
