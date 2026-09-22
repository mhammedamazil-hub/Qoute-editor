# Roadmap — honest status (v0.1.0-dev)

## Implemented (built + tested here)

- Reproducible ISO build: `build.sh` → `dist/JARVISOS.iso` (live-build,
  UEFI+BIOS hybrid, staged + validated; binary hook renders boot menus).
- JARVIS Core pipeline: offline NL parser (full OS coverage), SAFE/CONFIRM/
  DENY safety layer, daemon + CLI + socket clients.
- Automation: structured batches (≤30), validator, Mock/Real backends,
  ESC/`jarvis stop` emergency halt.
- Cloud AI: Gemini/OpenRouter/Hugging Face providers, fallback chain,
  vision batch planner with strict-JSON extraction + validator pass.
- Voice: push-to-talk STT (Vosk-tiny/HF cloud) + espeak TTS.
- Clap: local DSP detector (single/double/triple), daemon, mappings.
- Shell: HUD + launcher + status + dock, Performance/Cinematic policy.
- Apps: files, editor, terminal theme, monitor, 14-section settings,
  app manager (apt + official vendor scripts).
- Boot/login: Plymouth splash, GRUB theme, greeter theme, issue/motd.
- Installer: guided TUI (`jarvis-install`) + Calamares (full profile).
- Tests: 50 pytest cases + 6-stage `smoke-test.sh`, all green.

## Partially implemented (works, needs live-system validation)

- ISO boot on real hardware/VM (buildable here up to `lb build`; final
  binary + boot test run in CI / on a mirror-connected host).
- Plymouth/GRUB visual polish (functional themes; pixel-tweaking pending).
- Vosk model auto-download (manual install documented; one-click pending).
- Vendor install scripts (standard vendor procedures; need per-release
  re-verification as vendors change URLs/keys).

## Future (not started)

- Wake-word (“Hey Jarvis”) passive listening (needs tiny keyword model).
- Hand/gesture camera control beyond claps.
- Persistent live-USB overlay option.
- Secure Boot signed shim.
- Multi-language STT/TTS + localized shell.
- Delta updates / A-B partitions.
- App sandboxing profiles for automation (Firejail/Flatpak integration).

## How to contribute a feature

1. Add the intent/backend in `jarvis-core/jarvis/` (stdlib only).
2. Gate anything risky in `permissions.py` (+ tests).
3. Expose it in shell/apps/settings as needed.
4. Extend `tests/` + `smoke-test.sh`; keep `pytest` green.
