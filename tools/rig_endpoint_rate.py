"""Pre-flight: is the ButtKicker endpoint running at rate, or degraded?

Renders SILENCE for ten seconds and counts what the endpoint actually pulls.
Nothing is felt and nothing is heard - this is only the rate.

A healthy endpoint pulls ~48000 f/s. A degraded one sits near 30500 (one block
per 15.625 ms Windows tick), survives across processes, and only a reboot
clears it. Rating tones on a degraded endpoint blames the remount for the
audio bug - see docs/RIG-RETUNE_REMOUNT.md section 1.

Single-threaded on purpose: the GIL work of 22 Aug showed eight app threads
drag a healthy card to 30.7k, so a threaded harness cannot answer this.
"""
from __future__ import annotations

import sys
import time

import numpy as np
import sounddevice as sd

DEVICE = "Speakers (ButtKicker PRO)"
RATE = 48000
SECONDS = 10.0

sys.setswitchinterval(0.0005)


def main() -> int:
    index = None
    for i, dev in enumerate(sd.query_devices()):
        api = sd.query_hostapis(dev["hostapi"])["name"]
        if dev["name"] == DEVICE and api == "Windows WASAPI":
            index = i
            break
    if index is None:
        print(f"no WASAPI endpoint named {DEVICE!r}")
        return 1

    frames = 0
    blocks = 0
    dac_first = None
    dac_last = None

    def callback(out, n, time_info, status):
        nonlocal frames, blocks, dac_first, dac_last
        out[:] = 0.0
        frames += n
        blocks += 1
        dac = getattr(time_info, "outputBufferDacTime", 0.0)
        if dac:
            if dac_first is None:
                dac_first = dac
            dac_last = dac

    stream = sd.OutputStream(device=index, samplerate=RATE, channels=2,
                             dtype="float32", callback=callback)
    with stream:
        start = time.perf_counter()
        while time.perf_counter() - start < SECONDS:
            time.sleep(0.05)
        wall = time.perf_counter() - start

    ours = frames / wall
    print(f"  delivered   {ours:8.0f} f/s   ({ours / RATE * 100:.1f}% of nominal)")
    print(f"  blocks      {blocks / wall:8.1f} /s   ({frames / max(blocks, 1):.0f} frames each)")

    if dac_first is not None and dac_last is not None and dac_last > dac_first:
        # The card's own clock, not ours. WASAPI never reports underflows, so
        # this is the only thing that distinguishes "we fed it slowly" from
        # "it is pulling slowly".
        dac_hz = frames / (dac_last - dac_first)
        print(f"  DAC clock   {dac_hz:8.0f} f/s   (PortAudio stream clock)")
    else:
        print("  DAC clock        n/a   (host API does not fill it)")

    print()
    if ours >= RATE * 0.95:
        print("  AT RATE - the endpoint is healthy, go ahead and sweep.")
        return 0
    if ours <= RATE * 0.75:
        print("  DEGRADED - this is the ~30.5k wedge. REBOOT before rating any")
        print("  tone, then re-run this. Do not sweep on it.")
        return 2
    print("  MARGINAL - between healthy and the known wedge. Re-run once; if it")
    print("  repeats, reboot rather than sweep on it.")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
