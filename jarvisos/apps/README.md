# JARVIS apps (all GTK3, all JARVIS-styled)

| App | Launcher | File |
|---|---|---|
| Files | `jarvis-files` | `files_app.py` — sidebar, nav, copy/cut/paste, rename, trash, search, sort, previews, shortcuts |
| Text Editor | `jarvis-editor` | `editor_app.py` — tabs, find, undo/redo, save-as; default for .txt/.md/code |
| Terminal | `jarvis-terminal` | `bin/jarvis-terminal` — real bash in lxterminal with JARVIS theme + prompt |
| System Monitor | `jarvis-monitor` | `monitor_app.py` — CPU/RAM/swap/disk/battery/temp/processes |
| Settings | `jarvis-settings` | `settings_app.py` — all 14 sections, wired to real backends |
| App Manager | `jarvis-appmanager` | `appmanager_app.py` — on-demand installs + system update |

Other file types reuse solid Linux apps inside the JARVIS theme:
images → Eye of GNOME, PDF → Evince, archives → File Roller, media → VLC
(on-demand), web → Firefox ESR (Brave on-demand).
