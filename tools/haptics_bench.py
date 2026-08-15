"""Bring the tactile transducer up, with the driver in the seat to feel it.

The ButtKicker is a 150 W amp driving a 1 lb piston, so this is deliberately
step-by-step and starts quiet. Nothing here is loud by default; the amp has its
own volume and the point of `calibrate` is to set it once against a known
reference rather than by ear against whatever happened to be playing.

    python tools/haptics_bench.py devices
    python tools/haptics_bench.py exclusive      # can we own the card?
    python tools/haptics_bench.py channel left   # which one reaches the piston
    python tools/haptics_bench.py channel right
    python tools/haptics_bench.py channel both
    python tools/haptics_bench.py band           # what the amp actually passes
    python tools/haptics_bench.py calibrate      # the reference level

Every tone is faded in and out. A sine gated on and off is a click, and a
click through this amp is a thump.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from pitcrew.engineer import audio_devices  # noqa: E402

DEVICE = "Speakers (ButtKicker PRO)"
RATE = 48000
# -18 dBFS. Quiet enough to be safe into an amp whose volume we did not set,
# loud enough to feel with the knob at a normal position.
DEFAULT_AMPLITUDE = 0.125
FADE_S = 0.05


def _tone(freq: float, seconds: float, amplitude: float,
          *, left: bool, right: bool) -> np.ndarray:
    """One faded sine, as a stereo block."""
    n = int(RATE * seconds)
    t = np.arange(n, dtype=np.float32) / RATE
    wave = np.sin(2 * np.pi * freq * t).astype(np.float32) * amplitude

    fade = max(1, int(RATE * FADE_S))
    ramp = np.linspace(0.0, 1.0, fade, dtype=np.float32)
    wave[:fade] *= ramp
    wave[-fade:] *= ramp[::-1]

    block = np.zeros((n, 2), dtype=np.float32)
    if left:
        block[:, 0] = wave
    if right:
        block[:, 1] = wave
    return block


def _play(block: np.ndarray, *, exclusive: bool = True) -> str:
    """Write a block to the transducer. Returns how it was opened."""
    import sounddevice as sd

    if exclusive:
        try:
            stream = audio_devices.open_exclusive_output(
                DEVICE, RATE, channels=2, dtype="float32")
            how = f"WASAPI exclusive, {stream.latency * 1000:.1f} ms"
        except Exception as exc:                            # noqa: BLE001
            print(f"  exclusive open refused ({exc}) - falling back to shared "
                  f"for this test only")
            stream = audio_devices.open_output(
                RATE, channels=2, dtype="float32", device=DEVICE)
            how = "shared"
    else:
        stream = audio_devices.open_output(
            RATE, channels=2, dtype="float32", device=DEVICE)
        how = "shared"
    try:
        stream.write(block)
    finally:
        stream.stop()
        stream.close()
    return how


def _play_metered(block: np.ndarray, *, exclusive: bool = True) -> str:
    """Play, and ask Windows whether the card actually rendered it.

    Added after a bench session went sideways: a 40 Hz tone rated "strong"
    read as nothing a few minutes later, and there was no way to tell whether
    the amp had stopped, the stream had stopped, or the driver's attention
    had. Asking a man in a seat to distinguish those is not an experiment.

    `IAudioMeterInformation` reports the peak the **endpoint** rendered, which
    settles it without a human in the loop: a real peak means the signal left
    the PC and anything after that is the amp or the transducer; 0.0000 means
    it never got that far and the fault is ours.
    """
    from pitcrew.engineer import endpoint_meter

    heard, detail = endpoint_meter.confirm_reached_endpoint(
        lambda: _play(block, exclusive=exclusive), device=DEVICE)
    if heard is True:
        return f"the card rendered it - {detail}"
    if heard is False:
        return f"** THE CARD RENDERED NOTHING ** - {detail}"
    return f"could not measure the endpoint - {detail}"


def cmd_devices(_args) -> int:
    """Every route to the transducer, and what each one can do."""
    import sounddevice as sd

    apis = {i: a["name"] for i, a in enumerate(sd.query_hostapis())}
    print(f"{'idx':>4} {'host API':<22} {'out':>4} {'rate':>7} {'lat':>7}  name")
    for index, info in enumerate(sd.query_devices()):
        if info["max_output_channels"] <= 0:
            continue
        if "buttkicker" not in info["name"].lower():
            continue
        print(f"{index:>4} {apis[info['hostapi']]:<22} "
              f"{info['max_output_channels']:>4} "
              f"{info['default_samplerate']:>7.0f} "
              f"{info['default_low_output_latency'] * 1000:>6.1f}ms  "
              f"{info['name']}")
    default = sd.query_devices(sd.default.device[1])["name"]
    print(f"\nWindows default output: {default}")
    if "buttkicker" in default.lower():
        print("  ** WARNING ** the transducer is the system default, so every")
        print("  notification and every other app will play through the seat.")
        return 1
    print("  Good - stray sounds go there, not through the seat.")
    return 0


def cmd_exclusive(args) -> int:
    """Can we own the card outright? Silent - this opens and closes."""
    try:
        stream = audio_devices.open_exclusive_output(
            DEVICE, RATE, channels=2, dtype="float32")
    except Exception as exc:                                # noqa: BLE001
        print(f"exclusive open FAILED: {exc}")
        print("\nShared mode would work, but every other sound on the PC")
        print("could then reach the transducer, and Windows' Bass Management")
        print("and Loudness Equalization would both still be in the path.")
        return 1
    try:
        print(f"  exclusive       yes")
        print(f"  latency         {stream.latency * 1000:.1f} ms")
        print(f"  samplerate      {stream.samplerate:.0f} Hz")
        print(f"  channels        {stream.channels}")
        print(f"\nHolding it for {args.seconds:.0f}s. Nothing should be felt -")
        print("this is silence, not a signal.")
        time.sleep(args.seconds)
    finally:
        stream.stop()
        stream.close()
    print("released.")
    return 0


def cmd_channel(args) -> int:
    """Which channel actually reaches the piston.

    The amp is one unit fed by a stereo USB DAC, and nothing says whether the
    piston is driven by the left channel, the right, or a sum of both. It
    matters: SimHub's author warns that feeding a mono amp the same signal on
    both channels causes gain aberrations and saturation from the content
    arriving twice. Better to know than to assume and then wonder why the mix
    clips early.
    """
    sides = {"left": (True, False), "right": (False, True),
             "both": (True, True)}
    left, right = sides[args.side]
    block = _tone(args.freq, args.seconds, args.amplitude,
                  left=left, right=right)
    print(f"{args.side.upper()}: {args.freq:.0f} Hz at "
          f"{20 * np.log10(args.amplitude):.0f} dBFS for {args.seconds:.0f}s")
    how = _play(block)
    print(f"  played ({how}). Felt anything?")
    return 0


def cmd_band(args) -> int:
    """One frequency, so the answer can be attributed to it.

    This ran eleven tones back to back the first time, which was useless: the
    labels only reach the operator after the whole sweep has finished, so the
    man in the seat feels a series of buzzes with no way to say which was
    which. One tone per invocation instead - the caller announces the
    frequency, plays it, and asks. Slower, and the only version that produces
    an answer worth having.

    Context for what is being looked for: the BKA-PRO has a fixed 25 Hz
    low-cut and a user-selectable high-cut from 40 to 160 Hz, both
    12 dB/octave. Where the high-cut sits decides the whole effect layout, and
    nothing in software can read the switch.

    On this rig it did not need finding by ear - the amp has a display, and it
    reads **160 Hz**, the maximum. Kept anyway, because it is the way to check
    a setting that has been changed, and because a felt response is a
    different claim from a switch position.
    """
    print(f"{args.freq:.0f} Hz at {20 * np.log10(args.amplitude):.0f} dBFS "
          f"for {args.seconds:.0f}s.")
    block = _tone(args.freq, args.seconds, args.amplitude,
                  left=True, right=True)
    print(f"  {_play_metered(block, exclusive=not args.shared)}")
    print("  0 nothing, 1 faint, 2 clear, 3 strong?")
    return 0


def cmd_calibrate(args) -> int:
    """The reference level, so the amp's knob is set once and left.

    Everything the haptics layer emits is a fraction of this. Set the amp so
    this is strong but the piston does not knock, back off one step, and note
    the number on the amp's display - then the app's mix means the same thing
    tomorrow.
    """
    print(f"Reference tone: {args.freq:.0f} Hz at "
          f"{20 * np.log10(args.amplitude):.0f} dBFS, {args.seconds:.0f}s.")
    print("This is the loudest sustained output the app will ever produce.")
    print("Raise the amp until it is strong but does not knock, then back off")
    print("one step and note the number on the display.\n")
    block = _tone(args.freq, args.seconds, args.amplitude,
                  left=True, right=True)
    how = _play(block)
    print(f"  played ({how}).")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest="command", required=True)

    subs.add_parser("devices", help="routes, and whether it is the default"
                    ).set_defaults(run=cmd_devices)

    exc = subs.add_parser("exclusive", help="can we own the card - silent")
    exc.add_argument("--seconds", type=float, default=3.0)
    exc.set_defaults(run=cmd_exclusive)

    chan = subs.add_parser("channel", help="which channel drives the piston")
    chan.add_argument("side", choices=["left", "right", "both"])
    chan.add_argument("--freq", type=float, default=45.0)
    chan.add_argument("--seconds", type=float, default=3.0)
    chan.add_argument("--amplitude", type=float, default=DEFAULT_AMPLITUDE)
    chan.set_defaults(run=cmd_channel)

    band = subs.add_parser("band", help="one tone, so the answer names it")
    band.add_argument("--freq", type=float, required=True)
    band.add_argument("--seconds", type=float, default=3.0)
    band.add_argument("--amplitude", type=float, default=DEFAULT_AMPLITUDE)
    band.add_argument("--shared", action="store_true",
                      help="shared mode, where the endpoint meter is valid")
    band.set_defaults(run=cmd_band)

    cal = subs.add_parser("calibrate", help="set the amp against a reference")
    cal.add_argument("--freq", type=float, default=40.0)
    cal.add_argument("--seconds", type=float, default=10.0)
    cal.add_argument("--amplitude", type=float, default=0.5)
    cal.set_defaults(run=cmd_calibrate)

    args = parser.parse_args()
    return args.run(args)


if __name__ == "__main__":
    raise SystemExit(main())
