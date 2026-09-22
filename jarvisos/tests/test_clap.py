"""Clap DSP on synthetic PCM: claps detected, speech/noise ignored."""
import array
import math
import random

from jarvis.gestures import ClapDetector

SR = 16000


def silence(seconds):
    return array.array("h", [0] * int(SR * seconds)).tobytes()


def clap_burst(ms=120, amp=9000):
    """Short loud broadband burst with sharp attack (clap-like)."""
    n = int(SR * ms / 1000)
    rng = random.Random(7)
    out = array.array("h")
    for i in range(n):
        env = min(1.0, i / (n * 0.02)) * (1.0 - i / n)  # attack + decay
        # broadband: random sign flips → high zero-crossing rate
        out.append(int(rng.choice([-1, 1]) * amp * env))
    return out.tobytes()


def speech_like(seconds=1.0):
    """Sustained low-frequency tone wobble (speech-like, long + tonal)."""
    n = int(SR * seconds)
    out = array.array("h")
    for i in range(n):
        t = i / SR
        out.append(int(2500 * math.sin(2 * math.pi * 140 * t) *
                       (0.6 + 0.4 * math.sin(2 * math.pi * 3 * t))))
    return out.tobytes()


def feed_all(det, chunks, start=1000.0):
    events = []
    t = start
    for chunk in chunks:
        t += len(chunk) / 2 / SR
        events += det.feed(chunk, now=t)  # now = end of this chunk
    events += det.feed(silence(1.5), now=t + 2.0)  # flush windows
    return events


def test_single_clap():
    det = ClapDetector()
    events = feed_all(det, [silence(0.5), clap_burst(), silence(0.5)])
    assert events == ["single"], events


def test_double_clap():
    det = ClapDetector()
    events = feed_all(det, [silence(0.5), clap_burst(), silence(0.35),
                            clap_burst(), silence(0.5)])
    assert events == ["double"], events


def test_triple_clap():
    det = ClapDetector()
    events = feed_all(det, [silence(0.5), clap_burst(), silence(0.3),
                            clap_burst(), silence(0.3), clap_burst(),
                            silence(0.5)])
    assert events == ["triple"], events


def test_speech_ignored():
    det = ClapDetector()
    events = feed_all(det, [silence(0.5), speech_like(1.5), silence(0.5)])
    assert events == [], events


def test_silence_ignored():
    det = ClapDetector()
    assert feed_all(det, [silence(3.0)]) == []


def test_cooldown_and_disable():
    det = ClapDetector(cooldown_ms=1800)
    chunks = [clap_burst(), silence(0.4), clap_burst(), silence(2.5),
              clap_burst()]
    events = feed_all(det, chunks)
    assert events.count("single") <= 2, events
    det.enabled = False
    assert det.feed(clap_burst()) == []
