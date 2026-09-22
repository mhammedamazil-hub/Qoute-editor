# JARVISOS — a bootable AI operating system

JARVISOS is a real, bootable, lightweight Linux operating system (x86_64, UEFI)
with a futuristic JARVIS-style experience layered on top of a fully usable
normal desktop.

> **REAL FUNCTIONALITY > VISUAL DEMO · LOW RAM > EFFECTS · SAFETY > AUTOMATION**

- **Base:** Debian stable (`bookworm`) via `live-build` — see
  [docs/architecture.md](docs/architecture.md) for the full rationale.
- **Desktop:** X11 + Openbox + custom JARVIS shell (GTK3, ~light).
  Normal Linux windows, menus, drag & drop, hotkeys all work.
- **AI layer:** JARVIS Core — text, voice, clap/gesture input → cloud AI
  (Gemini / OpenRouter / Hugging Face, user-provided keys) → structured,
  safety-validated automation. No local LLM required. Fully usable offline.
- **Target:** older laptops — 4 GB RAM, older Intel CPU + iGPU, UEFI.

## Quick links

| Document | Contents |
|---|---|
| [docs/architecture.md](docs/architecture.md) | system architecture, base choice, component map |
| [docs/iso-creation.md](docs/iso-creation.md) | reproducible ISO build instructions |
| [docs/vm-testing.md](docs/vm-testing.md) | boot & test the ISO in QEMU/VirtualBox |
| [docs/usb-installation.md](docs/usb-installation.md) | write to USB, live boot, install to disk |
| [docs/installation.md](docs/installation.md) | installer guide (live + disk install) |
| [docs/hardware.md](docs/hardware.md) | requirements, 4 GB tuning |
| [docs/ai-configuration.md](docs/ai-configuration.md) | Gemini / OpenRouter / HF API keys |
| [docs/voice-configuration.md](docs/voice-configuration.md) | microphone, STT/TTS setup |
| [docs/clap-configuration.md](docs/clap-configuration.md) | clap/gesture mappings |
| [docs/troubleshooting.md](docs/troubleshooting.md) | common problems & fixes |
| [docs/performance.md](docs/performance.md) | Cinematic vs Performance mode |
| [docs/roadmap.md](docs/roadmap.md) | implemented / partial / future (honest status) |

## Repository layout

```
jarvisos/
├── build.sh            # one-command ISO builder → dist/JARVISOS.iso
├── build/              # live-build driver (staging + lb config + hooks)
├── packages/           # package lists (base / desktop / jarvis / full)
├── filesystem/         # root-filesystem overlay (installed into the live system)
├── iso/                # bootloader config (BIOS isolinux + UEFI GRUB)
├── boot/               # boot splash, Plymouth + GRUB themes, motd/issue
├── jarvis-core/        # JARVIS Core: bus, intents, permissions, notify, memory
├── automation/         # structured action engine + safety validator + screen
├── ai-providers/       # Gemini / OpenRouter / Hugging Face clients + vision
├── voice/              # speech-to-text, text-to-speech, wake word
├── gestures/           # lightweight local clap detector
├── shell/              # desktop shell: HUD core, launcher, status panel, dock
├── apps/               # files, editor, terminal theme, monitor, settings, app manager
├── settings/           # config schemas + factory defaults
├── themes/             # GTK + Openbox + icon theme sources
├── scripts/            # qemu-test.sh, validate-iso.sh, dev helpers
├── tests/              # pytest suite (runs on any Linux, no display needed)
└── docs/               # documentation (see table above)
```

All Python component logic is **standard-library only** so it runs on the
minimal base and is unit-testable headlessly. GTK is used only by UI entry
points and is imported lazily/guarded.

## Build the ISO

```bash
cd jarvisos
./build.sh            # → dist/JARVISOS.iso (+ dist/JARVISOS.iso.sha256)
```

Requires a Debian/Ubuntu build host with `live-build` and Debian-mirror
network access (see [docs/iso-creation.md](docs/iso-creation.md)).
No internet? A GitHub Actions workflow (`.github/workflows/jarvisos-iso.yml`)
builds the ISO in CI and uploads it as an artifact.

## Test without building an ISO

```bash
cd jarvisos
python3 -m venv .venv && . .venv/bin/activate
pip install pytest
pytest tests/ -q
./scripts/smoke-test.sh     # headless end-to-end: core → intents → automation
```

## Install / run on the target

Boot `dist/JARVISOS.iso` from USB (UEFI), try the live session, then run the
**Install JARVISOS** icon (Calamares on the full image, or the guided
`jarvis-install` TUI). Details: [docs/installation.md](docs/installation.md).

## Control every part of the OS with JARVIS

Press `Super+Space`, type or speak (`Super+V`), or clap. Examples:

```
open vs code · open blender · open discord · open brave
open downloads · show recent files · search files for presentation
what is using my ram? · connect bluetooth · connect wifi home-5G
set volume to 40 · set brightness 70 · take a screenshot
install blender · update the system · lock the screen · reboot
```

Full command coverage: [docs/architecture.md](docs/architecture.md#command-coverage).

## Security model (short version)

- No API keys in the image or in git — keys live in
  `~/.config/jarvisos/secrets.json` (`0600`), entered via Settings.
- The AI **never** runs raw shell. It emits **structured actions** which pass
  a safety validator; dangerous actions need explicit confirmation.
- **ESC** instantly halts any running automation.
- Details: [docs/architecture.md](docs/architecture.md#safety-model).

## Version

Current version: see [VERSION](VERSION). Built ISOs embed the version in
`/etc/jarvisos-release` and the bootloader menu.
