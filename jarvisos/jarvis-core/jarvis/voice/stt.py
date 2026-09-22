"""Speech-to-text. Chain: local Vosk tiny model (if installed) → HF cloud.

Recording uses parecord/arecord (already on the image) — no always-on
Python audio stack required. Nothing here runs continuously: capture only
happens while the user holds push-to-talk (or during a wake window).
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import urllib.request


def _recorder():
    if shutil.which("parecord"):
        return ["parecord", "--rate=16000", "--channels=1",
                "--format=s16le"]
    if shutil.which("arecord"):
        return ["arecord", "-q", "-r", "16000", "-c", "1", "-f", "S16_LE",
                "-t", "raw"]
    return []


def record_seconds(seconds=5, path="/tmp/jarvis-voice.raw"):
    """Record raw 16 kHz mono PCM. Returns path or '' on failure."""
    argv = _recorder()
    if not argv:
        return ""
    try:
        with open(path, "wb") as fh:
            subprocess.run(argv + ["--latency-msec=50"] if argv[0] == "parecord"
                           else argv + ["-d", str(int(seconds))],
                           stdout=fh, stderr=subprocess.DEVNULL,
                           timeout=seconds + 5)
        return path if os.path.getsize(path) > 3200 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def _raw_to_wav(raw_path):
    """Wrap raw s16le/16k/mono in a WAV header. Returns wav path or ''."""
    import struct
    try:
        with open(raw_path, "rb") as fh:
            pcm = fh.read()
        if not pcm:
            return ""
        wav_path = raw_path + ".wav"
        with open(wav_path, "wb") as fh:
            fh.write(b"RIFF")
            fh.write(struct.pack("<I", 36 + len(pcm)))
            fh.write(b"WAVEfmt ")
            fh.write(struct.pack("<IHHIIHH", 16, 1, 1, 16000,
                                 16000 * 2, 2, 16))
            fh.write(b"data")
            fh.write(struct.pack("<I", len(pcm)))
            fh.write(pcm)
        return wav_path
    except OSError:
        return ""


def transcribe_vosk(raw_path, model_dir):
    """Offline STT with a Vosk tiny model (~50 MB). Returns text or ''."""
    try:
        from vosk import Model, KaldiRecognizer
    except ImportError:
        return ""
    if not os.path.isdir(model_dir):
        return ""
    try:
        import wave
        wav_path = _raw_to_wav(raw_path)
        if not wav_path:
            return ""
        model = Model(model_dir)
        with wave.open(wav_path, "rb") as wf:
            rec = KaldiRecognizer(model, wf.getframerate())
            while True:
                data = wf.readframes(4000)
                if not data:
                    break
                rec.AcceptWaveform(data)
        result = json.loads(rec.FinalResult())
        return (result.get("text") or "").strip()
    except Exception:
        return ""


def transcribe_hf_cloud(raw_path, api_key,
                        model="openai/whisper-tiny"):
    """Cloud STT via Hugging Face inference (tiny data, fast)."""
    if not api_key:
        return ""
    wav_path = _raw_to_wav(raw_path)
    if not wav_path:
        return ""
    try:
        with open(wav_path, "rb") as fh:
            audio = fh.read()
        url = "https://router.huggingface.co/hf-inference/models/%s" % model
        req = urllib.request.Request(url, data=audio, method="POST")
        req.add_header("Authorization", "Bearer " + api_key)
        req.add_header("Content-Type", "audio/wav")
        with urllib.request.urlopen(req, timeout=60) as resp:
            body = json.loads(resp.read().decode("utf-8", "replace"))
        if isinstance(body, dict):
            return (body.get("text") or "").strip()
        return ""
    except Exception:
        return ""


def transcribe_file(raw_path, config=None):
    """Best-available transcription. Returns (text, engine_name)."""
    if config is None:
        from ..config import get_config
        config = get_config()
    engine = (config.get("voice.stt_engine", "auto") or "auto").lower()
    model_dir = os.path.expanduser(
        config.get("voice.vosk_model", "~/.local/share/jarvisos/vosk-model"))
    tried = []
    if engine in ("auto", "vosk"):
        text = transcribe_vosk(raw_path, model_dir)
        if text:
            return text, "vosk-local"
        tried.append("vosk")
    if engine in ("auto", "cloud"):
        key = config.get_secret("huggingface")
        text = transcribe_hf_cloud(raw_path, key)
        if text:
            return text, "hf-cloud"
        tried.append("hf-cloud")
    return "", "none (%s)" % ",".join(tried)


def listen_once(seconds=5, config=None):
    """Push-to-talk helper: record → transcribe. Returns (text, engine)."""
    raw = record_seconds(seconds)
    if not raw:
        return "", "no-mic"
    return transcribe_file(raw, config)
