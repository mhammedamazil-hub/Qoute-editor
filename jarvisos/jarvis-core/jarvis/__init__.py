"""JARVISOS core library.

Everything (shell, voice, clap, automation, apps) talks to JARVIS Core.
Standard-library only — no third-party imports in this package's logic.
UI (GTK) and hardware backends live in their own entry points and import
*from* here, never the other way around.
"""

__version__ = "0.1.0-dev"

from .config import Config, get_config  # noqa: F401
from .bus import Core, Result, Intent  # noqa: F401
