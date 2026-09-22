"""Tiny subprocess helper shared by backends."""
from __future__ import annotations

import shutil
import subprocess


def have(cmd):
    return shutil.which(cmd) is not None


def run(argv, timeout=10):
    """Run argv, return (returncode, stdout stripped). Never raises."""
    try:
        proc = subprocess.run(
            argv, capture_output=True, text=True, timeout=timeout)
        return proc.returncode, (proc.stdout or "").strip()
    except (OSError, subprocess.SubprocessError):
        return 127, ""
