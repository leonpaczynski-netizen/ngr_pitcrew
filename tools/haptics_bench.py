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

and for learning the tactile vocabulary rather than testing the hardware, the
two that play the REAL mix rather than a bare tone:

    python tools/haptics_bench.py cue rear_traction --level 0.4
    python tools/haptics_bench.py cue brake_limit --sweep
    python tools/haptics_bench.py pair rear_traction road

`cue` plays one effect through the real `HapticMix` - its own band, its own
gain chain, its own modulation - which is the only way to learn what a cue
means without a car in front of it. `pair` plays the second effect as a
background and then brings the first in on top, which is the question that
matters on a single piston: not "can I feel it" but "can I still tell it
apart".

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


def _play(block: np.ndarray, *, exclusive: bool = False) -> str:
    # Shared by default since 15 Aug 2026: exclusive mode opens on this
    # transducer, reports 21.3 ms, and renders nothing. Opting in is still
    # possible - `exclusive` - because the next device may be different, but
    # it is no longer what happens by accident.
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


def _play_metered(block: np.ndarray, *, exclusive: bool = False) -> str:
    """Play, and ask Windows whether the card actually rendered it.

    **Shared by default, because exclusive renders NOTHING on this device.**
    This defaulted to exclusive until 12 Sep 2026, which put every tone it
    played into the one mode `transducer.EXCLUSIVE = False` exists to record as
    broken: the stream opens, reports a sensible latency, and the piston stays
    dead. A whole response sweep would have come back rated 0 with the rig
    working perfectly - and the endpoint meter below would have said so, in a
    line nobody reads until the ratings make no sense. Caught before the first
    tone of the post-remount sweep; the default is the measured fact now, and
    exclusive is opt-in for the day a different device behaves differently.

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
    if getattr(args, "shared", False):
        print("  (--shared is the default now; the flag does nothing)")
    print(f"  {_play_metered(block, exclusive=args.exclusive)}")
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
          f"{20 * np.log10(args.amplitude):.0f} dBFS for {args.seconds:.0f}s.")
    print("This is the loudest sustained output the app will ever produce.")
    print("Every effect gain is a fraction of it, so once the amp is set")
    print("against this the mix means the same thing tomorrow.\n")
    print("TURN THE AMP DOWN FIRST, then bring it up while this plays:")
    print("  strong, but the piston must not knock. Back off one step.")
    print("  Then note the number on the amp's display.\n")
    block = _tone(args.freq, args.seconds, args.amplitude,
                  left=True, right=True)
    print(f"  {_play_metered(block)}")
    return 0


def cmd_cue(args) -> int:
    """One effect, through the real mix, so the driver can learn it.

    Not a bare tone. A bare tone at 95 Hz is not what the traction cue feels
    like: the real one carries band-limited noise, a pulse rate that rises
    with severity, and a gain chain with a threshold and a minimum force. A
    driver who learns the tone and then goes out has learned the wrong thing.
    """
    from pitcrew.rig.synth import MODIFIERS, PROFILE, HapticMix, to_stereo

    names = [spec.name for spec in PROFILE]
    if args.effect not in names:
        print(f"unknown effect {args.effect!r}. one of: {', '.join(names)}")
        return 2
    index = names.index(args.effect)
    spec = PROFILE[index]

    block = 512
    mix = HapticMix(block=block, master=args.master)
    values = np.zeros(len(PROFILE) + len(MODIFIERS), dtype=np.float32)
    frames = int(RATE * args.seconds)
    mono = np.zeros(frames, dtype=np.float32)
    stereo = np.zeros((frames, 2), dtype=np.float32)
    for start in range(0, frames - block, block):
        # A sweep walks the effect from nothing to full over the whole call, so
        # the driver hears the pitch and the pulse rate climb together - which
        # is the part that carries severity and the part a fixed level cannot
        # teach.
        values[index] = (start / frames if args.sweep else args.level)
        mono[start:start + block] = mix.render(values, block)
    to_stereo(mono, stereo, frames)
    fade = max(1, int(RATE * FADE_S))
    ramp = np.linspace(0.0, 1.0, fade, dtype=np.float32)[:, None]
    stereo[:fade] *= ramp
    stereo[-fade:] *= ramp[::-1]

    top = spec.freq_hi or spec.freq_lo
    print(f"{spec.name}: {spec.freq_lo:.0f}-{top:.0f} Hz, gain {spec.gain:.2f}, "
          f"trim {spec.felt_trim:.2f}"
          + (f", pulsing {spec.am_lo:.0f}-{spec.am_hi:.0f} Hz at depth "
             f"{spec.am_depth:.2f}" if spec.am_depth else ", unmodulated"))
    print("sweeping nothing to full" if args.sweep
          else f"held at {args.level:.2f}")
    print(_play(stereo))
    return 0


def cmd_pair(args) -> int:
    """A cue against a background, which is the only question that matters.

    With one piston everything sums, so "can he feel it" is the easy half.
    The hard half is whether he can still tell it apart from whatever else is
    playing - and the ducking design exists precisely to answer it. This plays
    the background alone, then the cue on top of it, so the difference is the
    thing being judged rather than the level.
    """
    from pitcrew.rig.synth import MODIFIERS, PROFILE, HapticMix, to_stereo

    names = [spec.name for spec in PROFILE]
    for name in (args.effect, args.against):
        if name not in names:
            print(f"unknown effect {name!r}. one of: {', '.join(names)}")
            return 2
    cue, bed = names.index(args.effect), names.index(args.against)

    block = 512
    mix = HapticMix(block=block, master=args.master)
    values = np.zeros(len(PROFILE) + len(MODIFIERS), dtype=np.float32)
    values[bed] = args.background
    frames = int(RATE * args.seconds)
    mono = np.zeros(frames, dtype=np.float32)
    stereo = np.zeros((frames, 2), dtype=np.float32)
    # A third of the call is background alone, then the cue comes in.
    entry = frames // 3
    for start in range(0, frames - block, block):
        values[cue] = args.level if start >= entry else 0.0
        mono[start:start + block] = mix.render(values, block)
    to_stereo(mono, stereo, frames)
    fade = max(1, int(RATE * FADE_S))
    ramp = np.linspace(0.0, 1.0, fade, dtype=np.float32)[:, None]
    stereo[:fade] *= ramp
    stereo[-fade:] *= ramp[::-1]

    print(f"{args.against} at {args.background:.2f} for "
          f"{entry / RATE:.1f} s, then {args.effect} at {args.level:.2f} "
          f"on top of it")
    print("the question is not whether the second one is loud. "
          "It is whether you could name it "
          "without being told which it was.")
    print(_play(stereo))
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
    band.add_argument("--exclusive", action="store_true",
                      help="exclusive mode - renders NOTHING on this rig, "
                           "kept only for testing a different device")
    # Accepted and ignored: shared is the default now, and the sweep of
    # 12 Sep 2026 is written up as having been run with this flag. Erroring
    # on it would make that record look wrong; ignoring it silently would be
    # its own trap, so it says so.
    band.add_argument("--shared", action="store_true",
                      help=argparse.SUPPRESS)
    band.set_defaults(run=cmd_band)

    cal = subs.add_parser("calibrate", help="set the amp against a reference")
    cal.add_argument("--freq", type=float, default=40.0)
    cal.add_argument("--seconds", type=float, default=10.0)
    cal.add_argument("--amplitude", type=float, default=0.5)
    cal.set_defaults(run=cmd_calibrate)

    cue = subs.add_parser("cue", help="one effect, through the real mix")
    cue.add_argument("effect")
    cue.add_argument("--level", type=float, default=0.5)
    cue.add_argument("--sweep", action="store_true",
                     help="walk it from nothing to full instead")
    cue.add_argument("--seconds", type=float, default=6.0)
    cue.add_argument("--master", type=float, default=1.0)
    cue.set_defaults(run=cmd_cue)

    pair = subs.add_parser("pair", help="a cue against a background")
    pair.add_argument("effect")
    pair.add_argument("against")
    pair.add_argument("--level", type=float, default=0.6)
    pair.add_argument("--background", type=float, default=0.7)
    pair.add_argument("--seconds", type=float, default=9.0)
    pair.add_argument("--master", type=float, default=1.0)
    pair.set_defaults(run=cmd_pair)

    args = parser.parse_args()
    return args.run(args)


if __name__ == "__main__":
    raise SystemExit(main())
