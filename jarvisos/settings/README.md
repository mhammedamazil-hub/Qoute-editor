# JARVISOS settings schema

Factory defaults: [defaults.json](defaults.json) → installed to
`/etc/jarvisos/defaults.json`. The Settings app and `jarvis config`
edit `~/.config/jarvisos/config.json` (same dotted keys).

| Key | Type | Meaning |
|---|---|---|
| `appearance.theme` | string | `jarvis-dark` (only theme in 0.1) |
| `appearance.accent` | color | neon accent, default `#35e0ff` |
| `appearance.performance_mode` | auto/cinematic/performance | effect level; `auto` = performance when RAM < 5 GB |
| `appearance.animations` | bool | shell animations on/off |
| `appearance.transparency` | bool | glass panels on/off |
| `ai.provider` | gemini/openrouter/huggingface | preferred provider (others are fallbacks) |
| `ai.*_model` | string | model id per provider |
| `voice.stt_engine` | auto/vosk/cloud | speech recognition engine |
| `voice.vosk_model` | path | local tiny-model dir (optional download) |
| `voice.speak_replies` | bool | TTS for JARVIS replies |
| `gestures.clap_enabled` | bool | clap daemon master switch |
| `gestures.sensitivity` | 1.5–6.0 | clap energy threshold multiplier (higher = needs louder claps) |
| `gestures.double_window_ms` | int | max gap grouping onsets |
| `gestures.cooldown_ms` | int | quiet period after an event |
| `gestures.clap_map` | object | single/double/triple → command strings |
| `hotkeys.*` | string | informational (Openbox `rc.xml` holds the real bindings) |
| `memory.enabled` | bool | local JSON memory on/off |
| `automation.confirm_first_batch` | bool | always confirm AI screen-control first |
| `privacy.send_screenshots_to_ai` | bool | master switch for vision calls |
| `privacy.send_voice_to_cloud` | bool | master switch for cloud STT |

Secrets (`secrets.json`, mode 0600): `gemini`, `openrouter`, `huggingface`
API keys. Managed only via Settings → AI Providers.
