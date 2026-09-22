"""Voice input/output: push-to-talk STT (local-tiny or cloud) + TTS replies."""
from .stt import transcribe_file, listen_once  # noqa: F401
from .tts import speak, stop_speaking  # noqa: F401
