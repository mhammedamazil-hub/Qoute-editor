# Clap / gesture configuration

The clap detector (`jarvis-clapd`) is **local DSP, no AI, no cloud**:
adaptive noise floor + sharp-attack + brightness + duration checks,
~1–2% CPU. Raw audio never leaves the process.

## Default mappings (Settings → Clap/Gestures)

| Pattern | Default command |
|---|---|
| 👏 single | `open discord` |
| 👏👏 double | `open vs code` |
| 👏👏👏 triple | `stop automation` |

Any mapping can be any JARVIS command (`set volume to 30`, `lock the
screen`, …) — mapped commands pass the same safety layer (dangerous ones
still need confirmation).

## Tuning

| Setting | Key | Guidance |
|---|---|---|
| Enable | `gestures.clap_enabled` | master switch (applies live, no restart) |
| Sensitivity | `gestures.sensitivity` (1.5–6.0) | noisy room → raise; missed claps → lower |
| Double window | `gestures.double_window_ms` | gap that groups claps (300–1200) |
| Cooldown | `gestures.cooldown_ms` | quiet period after an event (anti-repeat) |

Tips: clap crisply ~1 m from the mic; doors/speech are rejected by the
duration + brightness gates, but very loud environments may need
sensitivity 4–5. Test with notifications on — every detection posts one.

## How it works (short)

16 kHz mic → 20 ms frames → RMS vs adaptive floor → onset on sharp
bright attacks → state machine groups single/double/triple → Core.
See `jarvis-core/jarvis/gestures/clap.py` and `tests/test_clap.py`
(synthetic claps/speech/silence fixtures).

## Future gestures

Hand-tracking etc. plug into `gestures/` as new detectors feeding the same
Core entry points; the config schema already reserves the namespace.
