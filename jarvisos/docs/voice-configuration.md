# Voice configuration

## Push-to-talk (primary)

- Press **Super+V** or the 🎙 button → speak for N seconds (Settings →
  Voice → Listen seconds, default 6) → transcript runs through the same
  Core pipeline as typed text → reply shown (+ spoken if enabled).

## Engines (Settings → Voice → Speech engine)

| Engine | How | Needs |
|---|---|---|
| `auto` (default) | local Vosk tiny model if present, else HF cloud | — |
| `vosk` | 100% offline transcription | tiny model dir (~50 MB, see below) |
| `cloud` | Hugging Face Whisper inference | HF token in AI Providers |

### Installing the offline model (optional)

```bash
mkdir -p ~/.local/share/jarvisos && cd ~/.local/share/jarvisos
curl -L -o vosk.zip https://alphacephei.com/vosk/models/vosk-model-tiny-en-us-0.15.zip
unzip vosk.zip && mv vosk-model-tiny-en-us-0.15 vosk-model
```

Then set engine to `auto`/`vosk`. Transcription stays on-device.

## Replies

- `Speak replies aloud` (default on) via `espeak-ng`; rate adjustable.
- `jarvis stop` / ESC also silences speech + automation.

## Troubleshooting

- “I didn't hear anything”: Settings → Voice → Test microphone; check the
  input isn't muted (`alsamixer` / Settings → Audio → mic toggle); in a VM,
  enable microphone passthrough.
- Cloud STT fails: check HF token + `privacy.send_voice_to_cloud`.
- Wrong mic: `pactl list short sources`, then set default in `pavucontrol`.
