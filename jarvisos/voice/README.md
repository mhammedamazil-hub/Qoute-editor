# Voice control

- Library: `jarvis-core/jarvis/voice/` (`stt.py`, `tts.py`)
- Push-to-talk: `Super+V` (or the mic button) → records N seconds →
  transcribes → same Core pipeline as text → optional spoken reply.
- STT chain: local Vosk tiny model (if downloaded in Settings) → Hugging
  Face cloud Whisper (uses the HF token). No always-on ML process.
- TTS: `espeak-ng`, async, stoppable; disable in Settings → Voice.

CLI: `bin/jarvis-listen [--seconds 6]` — record once, print transcript,
send to Core, print + speak the answer. Used by the `Super+V` hotkey.
