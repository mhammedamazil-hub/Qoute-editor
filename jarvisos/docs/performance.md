# Performance modes

## Cinematic vs Performance

| | Cinematic | Performance (default < 5 GB) |
|---|---|---|
| HUD core | animated 20 fps Cairo rings | single static frame |
| Panels | RGBA glass transparency | opaque (still dark/cyan) |
| Compositor | `picom` (fades, shadows) | none (direct X11 = fastest) |
| Status polling | 2.5 s | 5 s |
| Boot entry | `JARVISOS Live` | `JARVISOS Live (Performance mode)` |
| Idle cost | ~+40 MB, ~1–3% CPU blips | baseline |

Select in Settings → Performance (`auto`/`cinematic`/`performance`) or via
the boot menu; `auto` picks Performance when RAM < 5120 MB. The kernel flag
`jarvis.performance=1` forces it (used by the boot-menu entry).

## Why it stays light

- No GNOME/KDE daemons, no Electron, no local LLM, no file indexer.
- Python daemons idle at ~0% (blocking socket/mic reads, no busy loops).
- GTK3 + Openbox + X11: the lightest credible modern-Linux desktop stack
  that still runs Firefox, VS Code, Blender.

## Measuring

- `free -m` after 2 min idle → target **< 700 MB used** (minimal profile).
- `jarvis-monitor` → TOP PROCESSES; `systemd-cgtop` for services.
- Clap DSP cost: `top -p $(pgrep -f jarvis-clapd)` → expect ~1–2%.
- If idle RAM is high in a VM: video drivers + guest tools account for
  ~100 MB — measure on bare metal for the real number.
