"""One continuous knock-test sequence, for recording on an external device.

The laptop mic array failed its negative control (120 Hz, clean by ear, read
crest 41 / kurtosis 489 at 10x the level of the other runs), so nothing it
measured can be used. This plays the whole set as ONE buffer instead, with a
marker and fixed gaps, so a phone recording can be segmented exactly rather
than by eye.

Structure, at a fixed level, amp position unchanged throughout:

    0.0 - 1.2 s   marker: three 200 ms bursts at 120 Hz, 200 ms apart
    3.2 - 8.2 s   40 Hz
   10.2 -15.2 s   60 Hz
   17.2 -22.2 s   85 Hz
   24.2 -29.2 s   100 Hz
   31.2 -36.2 s   120 Hz

The silences are the reference: knock is judged against the gap either side of
its own tone, so a bump or a word during a gap voids that tone rather than the
whole run.
"""
from __future__ import annotations

import sys

import numpy as np
import sounddevice as sd

OUT = "Speakers (ButtKicker PRO)"
RATE = 48000
FADE_S = 0.05
LEVEL = 0.5          # -6 dBFS, the sustained ceiling
TONE_S = 5.0
GAP_S = 2.0
LEAD_S = 2.0
MARKER_HZ = 120.0
TONES = (40.0, 60.0, 85.0, 100.0, 120.0)


def _sine(freq: float, seconds: float, amplitude: float) -> np.ndarray:
    n = int(RATE * seconds)
    t = np.arange(n, dtype=np.float32) / RATE
    wave = (np.sin(2 * np.pi * freq * t) * amplitude).astype(np.float32)
    fade = max(1, int(RATE * min(FADE_S, seconds / 4)))
    ramp = np.linspace(0.0, 1.0, fade, dtype=np.float32)
    wave[:fade] *= ramp
    wave[-fade:] *= ramp[::-1]
    return wave


def _silence(seconds: float) -> np.ndarray:
    return np.zeros(int(RATE * seconds), dtype=np.float32)


def build() -> tuple[np.ndarray, list[tuple[float, float, float]]]:
    parts = [_silence(0.2)]
    for _ in range(3):
        parts.append(_sine(MARKER_HZ, 0.2, LEVEL))
        parts.append(_silence(0.2))
    parts.append(_silence(LEAD_S - 0.2))

    schedule = []
    elapsed = sum(len(p) for p in parts) / RATE
    for freq in TONES:
        start = elapsed
        parts.append(_sine(freq, TONE_S, LEVEL))
        parts.append(_silence(GAP_S))
        elapsed += TONE_S + GAP_S
        schedule.append((freq, start, start + TONE_S))

    mono = np.concatenate(parts)
    return np.column_stack([mono, mono]) * 0.5, schedule


def main() -> int:
    for i, dev in enumerate(sd.query_devices()):
        if (sd.query_hostapis(dev["hostapi"])["name"] == "Windows WASAPI"
                and dev["max_output_channels"] > 0
                and dev["name"].startswith(OUT[:28])):
            out_i = i
            break
    else:
        print(f"no WASAPI output named {OUT!r}")
        return 1

    block, schedule = build()
    total = len(block) / RATE
    print(f"{total:.1f}s sequence at {20 * np.log10(LEVEL):.0f} dBFS")
    print("  marker: three 120 Hz bursts, then")
    for freq, start, end in schedule:
        print(f"  {start:5.1f} - {end:5.1f}s   {freq:5.0f} Hz")
    print("\nplaying now - do not move or talk")
    sd.play(block, samplerate=RATE, device=out_i, blocking=True)
    sd.wait()
    print("done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
