# JARVIS Core

The single command pipeline for the whole OS. Library in `jarvis/`:

| Module | Job |
|---|---|
| `bus.py` | `Core`: text/voice/clap/GUI → intent → safety → execute |
| `intents.py` | offline NL parser (full OS coverage, fuzzy apps) |
| `permissions.py` | SAFE / CONFIRM / DENY policy + allowlisted shell |
| `config.py` | layered config + 0600 secrets |
| `memory.py` | tiny local JSON memory (disableable) |
| `notify.py` | desktop bubbles + log the shell tails |
| `automation/` | batch engine + safety validator + screen helpers |
| `ai/` | Gemini / OpenRouter / Hugging Face + batch planner |
| `voice/` | STT (Vosk-tiny / HF cloud) + TTS |
| `gestures/` | local clap detector DSP |
| `system/` | stats, network, bluetooth, audio, display, power |
| `control/` | app registry/launcher/install recipes, safe file ops |

- Daemon: `jarvisd.py` → `/usr/bin/jarvis-core` (Unix-socket JSON-RPC).
- CLI: `bin/jarvis` (talks to the daemon; falls back to in-process Core).

Run the test suite from `jarvisos/`: `pytest tests/ -q`.
