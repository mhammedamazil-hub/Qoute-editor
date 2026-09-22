# Troubleshooting

## Boot problems

| Symptom | Likely cause → fix |
|---|---|
| USB not listed | rewrite with DD mode (Rufus) / `dd`; try another port; enable USB boot |
| “Secure Boot violation” | disable Secure Boot in firmware (no shim signature in 0.1) |
| Black screen after GRUB | boot the **failsafe** entry; add `nomodeset` via `e` on exotic GPUs |
| Stuck at splash | failsafe entry → `journalctl -xb` after boot; check ISO sha256 |
| Boots to `grub>` prompt | ISO write corrupted → re-verify sha256 and rewrite |

## Desktop / shell

- **No HUD, only black + mouse**: `Ctrl+Alt+T` → `jarvis-shell &`; if GTK
  errors appear, reinstall `gir1.2-gtk-3.0 python3-gi`.
- **No windows decorations**: `openbox --replace &`.
- **Hotkeys dead**: Openbox reads `~/.config/openbox/rc.xml` —
  `openbox --reconfigure`; check `jarvis-hud-focus` is on PATH.
- **No notifications**: `dunst &`; tail `~/.local/share/jarvisos/notifications.log`.

## JARVIS Core / AI / voice / clap

- `jarvis status` says daemon offline → `jarvis-core &` (session normally
  starts it; check `~/.xsession-errors`).
- AI always fails → Settings → AI Providers → Test; check key + network;
  `privacy.send_screenshots_to_ai` must be on for vision.
- Mic silent → Settings → Audio (unmute input), `pavucontrol` source
  selection; VM: enable mic passthrough.
- Claps ignored → lower `sensitivity` to ~2.5, check `clap_enabled`, clap
  closer/louder; false triggers → raise to ~4–5.

## Apps & system

- `install X` fails → connect to internet first; vendor scripts need HTTPS
  to the vendor; read the visible terminal output.
- No Wi-Fi hardware → `rfkill list`; firmware lives in the image, but USB
  tethering works as a fallback for installs.
- Forgot password (installed) → boot live USB → mount root → `chroot` →
  `passwd <user>`.

## Collecting logs

```bash
journalctl -xb --no-pager | tail -100     # boot
cat ~/.xsession-errors                    # X session
tail ~/.local/share/jarvisos/notifications.log
jarvis --local "what is using my ram?"    # core sanity
```
