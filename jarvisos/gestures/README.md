# Clap / gesture control

- Library: `jarvis-core/jarvis/gestures/clap.py` — pure-stdlib onset DSP,
  adaptive noise floor, ~1–2% CPU, tiny RAM. No ML, no cloud; raw mic
  audio never leaves the process.
- Daemon: `bin/jarvis-clapd` — listens continuously (when enabled in
  Settings → Clap/Gestures), maps `single`/`double`/`triple` patterns to
  command strings via `gestures.clap_map`, and forwards them to Core.
- Defaults: 👏 → `open discord`, 👏👏 → `open vs code`, 👏👏👏 → stop.
- Tuning: `gestures.sensitivity` (louder room → higher), `double_window_ms`,
  `cooldown_ms`. See [docs/clap-configuration.md](../docs/clap-configuration.md).

Future gestures (hand tracking etc.) plug in here as additional detectors
feeding the same `Core.handle_clap()`-style entry points.
