# JARVISOS architecture

## Why Debian stable + live-build (base choice)

| Requirement (4 GB, old Intel iGPU, UEFI) | Decision |
|---|---|
| Stable, low-RAM base with huge HW support | **Debian `bookworm` minimal** via `live-build` (mature UEFI + hybrid ISO tooling, reproducible) |
| No heavy desktop | **X11 + Openbox** (~50 MB) + custom JARVIS shell; no GNOME/KDE/Xfce session |
| X11, not Wayland | screen automation (PyAutoGUI/xdotool) and global hotkeys are reliable on X11; Wayland would break them |
| No local LLM | **cloud AI only** (Gemini/OpenRouter/HF) — a 4 GB machine cannot host a useful local model |
| Offline-first core | deterministic local NL parser + backends; cloud is an enhancement layer |
| Fast boot, small image | `minimal` profile ≈ core desktop + JARVIS; heavy apps install on demand |

Alternatives considered: Arch-based (less stable for beginners, weaker live tooling),
Ubuntu + GNOME (too heavy), Alpine (musl breaks many desktop apps, no live-build),
Buildroot/Yocto from scratch (months of work, worse hardware support).

## Component map

```
keyboard/voice(hotkey)/clap/GUI
        │  (all speak JSON-RPC to the daemon)
        ▼
┌────────────── jarvis-core (daemon) ──────────────┐
│ Core pipeline:  text → intents → permissions →   │
│                 execute (apps/files/system/… )   │
│ Subsystems: AI manager · automation engine ·    │
│ memory · notify · config/secrets                │
└──────┬────────┬────────┬──────────┬──────┬───────┘
       ▼        ▼        ▼          ▼      ▼
   apps/files system   AI cloud  automation notify/
   control  backends  providers  (batch +   shell
   (launch, (nmcli,   Gemini/    validator,  panel
   install  bt, audio  OpenRouter batch,     (dunst
   recipes) display…)  HF)       ESC stop)   + log)
```

Key files: `jarvis-core/jarvis/bus.py` (Core), `intents.py` (parser),
`permissions.py` (policy), `automation/engine.py` (executor),
`ai/manager.py` (providers), `system/*` (backends), `control/*`.

### Shell & session

`jarvis-session` (lightdm target) → `openbox-session` + `jarvis-core`
daemon + `jarvis-clapd` + `jarvis-shell` (HUD/launcher/status/dock) +
dunst + polkit. Ordinary Openbox windows behave normally: focus, resize,
right-click menus, Alt-Tab, workspaces.

### Configuration

`/etc/jarvisos/defaults.json` (factory) ← overridden by
`~/.config/jarvisos/config.json`; secrets in `~/.config/jarvisos/secrets.json`
(0600). Schema: `settings/README.md`.

## Safety model

1. **AI never runs shell.** It emits JSON from a fixed action vocabulary
   (`automation/engine.py`); unknown types are denied.
2. **Three levels** (`permissions.py`): SAFE runs; CONFIRM needs explicit
   approval (reboot, install, delete, any AI screen-control batch);
   DENY never runs (formats, partitions, bootloader, non-allowlisted shell,
   destructive typed text).
3. **Allowlisted shell**: only `wifi_scan`, `wifi_connect{ssid}`,
   `apt_update`, `apt_install{pkg}` with strict argument validation.
4. **ESC / `jarvis stop`** halts automation between any two actions.
5. **No secrets in git/ISO**: keys live only in the user's 0600 file.

## Command coverage

Full-OS control offline: apps (open/close/focus/install), folders, recent
files, file search, RAM/CPU/disk/battery/temp/processes, Wi-Fi
(on/off/list/connect/disconnect), Bluetooth (on/off/list/pair/connect),
volume/mute/mic, brightness/screenshots/night mode, lock/suspend/reboot/
shutdown/logout, settings sections, system update, help. With an AI key:
free-form Q&A, screen description, and confirmed screen-control batches.
Parser: `jarvis-core/jarvis/intents.py` (+ `tests/test_intents.py`).

## Performance design

- Core/voice/clap/automation are stdlib-Python; idle cost ≈ 0 (no polling
  loops except 2–5 s status refresh and mic read in `jarvis-clapd`).
- Shell: static core + no compositor in Performance mode (default < 5 GB).
- Expected idle: ~450–650 MB RAM live session (measured target; see
  `docs/vm-testing.md`). No LLMs, no Electron, no GNOME daemons.
