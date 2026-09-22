"""Cloud AI providers (modular). No local LLM — 4 GB RAM target.

Providers read keys from Config secrets only. All HTTP uses stdlib urllib
with short timeouts so a dead network fails fast and the OS stays usable.
"""
from .manager import AIManager  # noqa: F401
