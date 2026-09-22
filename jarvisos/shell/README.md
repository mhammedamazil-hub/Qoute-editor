# JARVIS shell

Lightweight desktop shell on X11 + Openbox (no GNOME/KDE):

| File | Window |
|---|---|
| `hud.py` | Center: arc-core + “What would you like me to do?” + text/mic |
| `core_widget.py` | Cairo arc-reactor (animated / static in Performance mode) |
| `panels.py` | Left launcher · right status · bottom dock |
| `client.py` | stdlib socket client to `jarvis-core` (unit-tested) |
| `main.py` | assembly + placement + performance-mode policy |

- Normal Linux windows keep working: Openbox manages them; the shell is
  just four frameless windows + hotkeys (`filesystem/.../rc.xml`).
- ESC anywhere in the HUD stops automation (`client.stop()`).
- Session entry: `bin/jarvis-session` (lightdm `Exec=` target).
