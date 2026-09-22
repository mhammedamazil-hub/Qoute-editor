"""Lightweight clap detector — pure stdlib DSP, ~1-2% CPU.

How it works:
- Mic PCM (16 kHz mono s16le) is sliced into 20 ms frames.
- Each frame's RMS energy is compared against an adaptive noise floor
  (slow-moving average). A sharp attack (energy jump × sensitivity within
  1-2 frames) with a bright spectrum (high zero-crossing rate) and short
  duration (40–300 ms) counts as ONE clap onset.
- A state machine groups onsets: 1 onset → 'single' (after the double
  window expires), 2 onsets within double_window_ms → 'double', 3 → 'triple'.
- Cooldown + minimum-quiet rules suppress false positives (speech, doors).

No ML, no network, tiny RAM. Raw audio never leaves the process.
"""
from __future__ import annotations

import array
import math
import time


class ClapDetector:
    def __init__(self, sensitivity=3.0, double_window_ms=700,
                 cooldown_ms=1800, min_quiet_ms=120,
                 sample_rate=16000, frame_ms=20):
        self.sensitivity = float(sensitivity)      # energy jump multiplier
        self.double_window = double_window_ms / 1000.0
        self.cooldown = cooldown_ms / 1000.0
        self.min_quiet = min_quiet_ms / 1000.0
        self.sample_rate = sample_rate
        self.frame_len = int(sample_rate * frame_ms / 1000)
        self.enabled = True
        self.reset()

    def reset(self):
        self.noise_floor = 60.0        # adaptive RMS floor
        self._prev_energy = 0.0
        self._loud_since = None        # start ts of current loud burst
        self._burst_frames = 0
        self._onsets = []              # onset timestamps in current group
        self._last_event_ts = 0.0      # cooldown anchor
        self._last_frame_ts = 0.0
        self._pending_single_deadline = None

    # -- DSP -------------------------------------------------------------
    def _frame_stats(self, samples):
        n = len(samples)
        if n == 0:
            return 0.0, 0.0
        energy = 0.0
        crossings = 0
        prev = samples[0]
        for s in samples:
            energy += s * s
            if (s >= 0) != (prev >= 0):
                crossings += 1
            prev = s
        rms = math.sqrt(energy / n)
        zcr = crossings / n  # 0..~1; claps are bright: >0.2 typically
        return rms, zcr

    def feed(self, pcm_bytes, now=None):
        """Feed raw s16le mono PCM. Returns list of events
        ('single'|'double'|'triple'). Call continuously with small chunks."""
        events = []
        if not self.enabled or not pcm_bytes:
            return events
        now = time.monotonic() if now is None else now
        try:
            samples = array.array("h")
            samples.frombytes(pcm_bytes)
        except (ValueError, TypeError):
            return events
        if len(samples) < self.frame_len // 2:
            return events

        # process in fixed frames
        total = len(samples)
        step = self.frame_len
        frame_dt = step / self.sample_rate
        t = now - (total / self.sample_rate)
        for off in range(0, total - step + 1, step):
            t += frame_dt
            frame = samples[off:off + step]
            rms, zcr = self._frame_stats(frame)
            events += self._ingest_frame(rms, zcr, t)
        # time-based flush (single clap confirmed after window expires)
        events += self._flush(now)
        return events

    def _ingest_frame(self, rms, zcr, t):
        events = []
        # adapt noise floor slowly toward quiet frames
        if rms < self.noise_floor * 1.5:
            self.noise_floor += (rms - self.noise_floor) * 0.02
            self.noise_floor = max(25.0, self.noise_floor)
        loud = rms > max(self.noise_floor * self.sensitivity, 220.0)
        bright = zcr > 0.18

        if loud and bright:
            if self._loud_since is None:
                self._loud_since = t
                self._burst_frames = 1
                # sharp attack? compare with previous frame energy
                attack = rms > max(self._prev_energy * 2.2, 300.0)
                if attack:
                    events += self._register_onset(t)
            else:
                self._burst_frames += 1
                # too long → speech/music, not a clap: cancel burst
                if (t - self._loud_since) > 0.35:
                    self._loud_since = None
        else:
            if self._loud_since is not None:
                dur = t - self._loud_since
                # very short blips (<40ms) are clicks/pops → ignore
                gap = (t - self._onsets[-1]) if self._onsets else 9.0
                if 0 <= dur < 0.04 and 0 <= gap < 0.05:
                    self._onsets.pop()
                self._loud_since = None
        self._prev_energy = rms
        return events

    def _register_onset(self, t):
        # cooldown: ignore onsets right after an emitted event
        if (t - self._last_event_ts) < self.cooldown:
            return []
        # minimum quiet between onsets in a group (debounce echoes)
        if self._onsets and (t - self._onsets[-1]) < 0.12:
            return []
        # gap too big → previous group resolves first
        if self._onsets and (t - self._onsets[-1]) > self.double_window:
            events = self._resolve_group()
            self._onsets = [t]
            self._pending_single_deadline = t + self.double_window
            return events
        self._onsets.append(t)
        if len(self._onsets) == 1:
            self._pending_single_deadline = t + self.double_window
            return []
        if len(self._onsets) == 2:
            # wait a bit: could become triple
            self._pending_single_deadline = t + 0.45
            return []
        # 3+ → triple immediately
        self._onsets = []
        self._pending_single_deadline = None
        self._last_event_ts = t
        return ["triple"]

    def _resolve_group(self):
        n = len(self._onsets)
        self._last_event_ts = self._onsets[-1] if self._onsets else 0.0
        self._pending_single_deadline = None
        if n == 1:
            return ["single"]
        if n == 2:
            return ["double"]
        if n >= 3:
            return ["triple"]
        return []

    def _flush(self, now):
        if self._pending_single_deadline is not None and \
                now >= self._pending_single_deadline and self._onsets:
            events = self._resolve_group()
            self._onsets = []
            return events
        # stale group cleanup
        if self._onsets and (now - self._onsets[-1]) > self.double_window:
            events = self._resolve_group()
            self._onsets = []
            return events
        return []

    # -- live loop ---------------------------------------------------------
    def listen_forever(self, on_event, stop_flag, chunk_ms=100):
        """Read mic via parecord/arecord and emit events until stop_flag set.

        on_event(name) is called for 'single'/'double'/'triple'.
        """
        import shutil
        import subprocess
        if shutil.which("parecord"):
            argv = ["parecord", "--rate=%d" % self.sample_rate,
                   "--channels=1", "--format=s16le", "--latency-msec=50"]
        elif shutil.which("arecord"):
            argv = ["arecord", "-q", "-r", str(self.sample_rate), "-c", "1",
                   "-f", "S16_LE", "-t", "raw"]
        else:
            raise RuntimeError("no mic recorder (parecord/arecord) found")
        chunk = int(self.sample_rate * chunk_ms / 1000) * 2
        proc = subprocess.Popen(argv, stdout=subprocess.PIPE,
                                stderr=subprocess.DEVNULL)
        try:
            while not stop_flag.is_set():
                data = proc.stdout.read(chunk)
                if not data:
                    break
                for event in self.feed(data):
                    on_event(event)
        finally:
            try:
                proc.terminate()
            except OSError:
                pass
