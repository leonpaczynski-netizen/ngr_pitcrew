"""Map where the transducer runs out of travel, frequency by frequency.

The knock threshold is the constraint that actually binds this rig, and until
now it was four scattered points measured by asking a man in a seat. This maps
it as a curve, unattended, because a machine can hear knock.

**The detector, and why this one.** Knock is a nonlinearity: the mass hits its
stop and stops dead, which sprays broadband energy that a linear system driving
a sine does not produce. So the measurement is the energy well above the tone
(>800 Hz, clear of every fundamental here and its first five harmonics)
normalised against the tone's OWN fundamental. Below the stops that ratio is
roughly constant with level - a linear system scales everything together.
Above them it climbs, and the level where it starts climbing is the threshold.

**Normalising within the tone is not a detail, it is the whole reason this
works.** Three instruments failed on 12 Sep 2026 before this one:

  * the JBL jack read -71 dBFS - nothing plugged into it;
  * a mic endpoint handed back exact zeros for seconds after the stream opened,
    which is indistinguishable from a dead microphone;
  * the laptop array failed its negative control outright - 120 Hz, clean by
    ear, read crest 41 / kurtosis 489 - because beamforming, AGC and noise
    suppression reshape exactly the transients being measured;
  * the USB mic has a NOISE GATE. Its silence reads -126 to -149 dBFS, which is
    not a room, so measuring a tone against the gap beside it measures the
    depth of the gate. The gate is OPEN while a tone plays, so tone-to-tone and
    level-to-level comparison is valid and tone-to-silence is not.

Normalised within the tone, the metric passed both controls: 120 Hz measured
clean, and 60 Hz showed the loudest fundamental by 18 dB, matching the driver's
off-scale rating by a completely separate route.

**It climbs from quiet and stops at onset**, rather than bisecting, so the unit
is never driven far past its stops to find out where they are.

    python tools/rig_knock_curve.py [--amp 35] [--quick]

The amp position is recorded, not read - nothing in software can see the knob,
and the curve is only meaningful with it. The knob is a global offset: measure
once at a position where the thresholds are reachable, and any other position
shifts the whole curve.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import sounddevice as sd

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

OUT = "Speakers (ButtKicker PRO)"
MIC = "Microphone (2- Usb Audio Device)"
RATE = 48000

# Above every fundamental tested and its first five harmonics, so the tone
# itself contributes nothing to the numerator at any frequency and all rows
# are measured in one band.
CUT_HZ = 800.0

TONE_S = 4.0   # long enough for a RARE thump to land in the window
GAP_S = 0.6
FADE_S = 0.05

# Finer through 45-70, where the reaction mass's own resonance sits and the
# threshold moves fastest.
FREQS = (30.0, 35.0, 40.0, 45.0, 50.0, 55.0, 60.0, 65.0, 70.0, 80.0,
         90.0, 100.0, 110.0, 120.0, 135.0, 150.0)
QUICK_FREQS = (30.0, 40.0, 50.0, 60.0, 70.0, 85.0, 100.0, 120.0, 150.0)

# -39 dBFS up to -3, the transient ceiling. Nothing is ever driven above the
# loudest thing the app itself can emit.
LEVELS_DB = tuple(float(d) for d in range(-39, -2, 3))

# A rise of this much over the level's own quiet baseline is knock. Chosen
# well above the run-to-run spread seen on 12 Sep (about 2 dB) and well below
# the 15-20 dB steps the knee actually produced.
RISE_DB = 8.0
BASELINE_MIN = 3          # levels of quiet evidence before a rise can be called

# **Two thumps in ten seconds is a knock.** The driver heard exactly that at
# 40 Hz where the ratio detector read clean, so the bar is set below it: a cue
# that fires occasionally is worse in the car than one that fires always,
# because it cannot be learned.
IMPULSE_PER_S = 0.24   # one event in a 4 s tone
# **Impulses only get a vote when the tone is cleanly above the noise.**
# Without this the detector fired at 120 Hz / -36 dBFS and 150 Hz / -33 - two
# levels the driver had already shown clean 30 dB louder - because at low
# drive the microphone is mostly hearing itself and a robust threshold on
# noise finds "impulses" in it. The giveaway was the ratio: those false hits
# read +5.5 and -11.4, i.e. the high band was as loud as the tone, while the
# genuine intermittent hit at 100 Hz read -31.7.
#
# The gate is sound rather than a fudge, because it follows from what
# intermittent knock IS: rare events barely move an average, so real
# intermittent knock always coexists with a good ratio. A tone whose ratio has
# already risen is sustained knock, and the other detector owns that case.
IMPULSE_SNR_DB = -18.0
# Below this the microphone is not hearing the tone and the row is not
# evidence of anything - see `sweep_one`.
FUND_FLOOR_DB = 10.0


def _device(name: str, *, want_input: bool) -> int:
    for i, dev in enumerate(sd.query_devices()):
        if sd.query_hostapis(dev["hostapi"])["name"] != "Windows WASAPI":
            continue
        key = "max_input_channels" if want_input else "max_output_channels"
        if dev[key] > 0 and dev["name"].startswith(name[:26]):
            return i
    raise SystemExit(f"no WASAPI device matching {name!r}")


def _tone(freq: float, seconds: float, amplitude: float) -> np.ndarray:
    n = int(RATE * seconds)
    t = np.arange(n, dtype=np.float32) / RATE
    wave = (np.sin(2 * np.pi * freq * t) * amplitude).astype(np.float32)
    fade = max(1, int(RATE * FADE_S))
    ramp = np.linspace(0.0, 1.0, fade, dtype=np.float32)
    wave[:fade] *= ramp
    wave[-fade:] *= ramp[::-1]
    return np.column_stack([wave, wave]) * 0.5


def _highpass(x: np.ndarray) -> np.ndarray:
    spec = np.fft.rfft(x)
    k = int(CUT_HZ / (RATE / 2) * (len(spec) - 1))
    spec[:k] = 0.0
    return np.fft.irfft(spec, n=len(x))


def impulse_rate(x: np.ndarray) -> float:
    """Discrete knocks per second, which an AVERAGE cannot see.

    **This exists because the ratio detector missed a real knock.** At 40 Hz
    the driver heard two distinct thuds in a ten-second tone - 400 cycles, two
    contacts - and the ratio came back textbook flat, because two impulses
    diluted across 400 cycles barely move an RMS. At 60 Hz the mass hits its
    stop on every cycle, which is sustained and trivially detectable by an
    average. Same mechanism, completely different statistics.

    So "no sustained knock" is not "no knock", and an intermittent contact is
    the more dangerous of the two in the car: a cue that fires occasionally is
    a cue the driver cannot learn.

    Counted off a robust (median/MAD) threshold so the tone's own harmonics
    set the floor, with a refractory gap so one thud is one event.
    """
    hp = _highpass(x)
    env = np.abs(hp)
    med = float(np.median(env))
    mad = float(np.median(np.abs(env - med))) + 1e-12
    above = np.flatnonzero(env > med + 8.0 * 1.4826 * mad)
    if not len(above):
        return 0.0
    refractory = int(0.02 * RATE)
    count, last = 1, int(above[0])
    for i in above[1:]:
        if int(i) - last > refractory:
            count += 1
            last = int(i)
    return count / (len(x) / RATE)


def ratio_db(seg: np.ndarray, freq: float) -> tuple[float, float, float, float]:
    """What the microphone heard of one tone.

    Returns (ratio_db, fundamental_db, peak, impulses_per_second). The ratio
    catches SUSTAINED knock, the impulse rate catches INTERMITTENT knock, and
    the fundamental says whether the microphone could hear the tone at all -
    without which a row of pure noise reads as a huge ratio and poisons the
    baseline it is compared against.
    """
    x = seg.mean(axis=1).astype(np.float64)
    n = len(x)
    if n < 2048:
        return float("nan"), float("nan"), 0.0, 0.0
    spec = np.abs(np.fft.rfft(x * np.hanning(n))) ** 2
    bins = np.fft.rfftfreq(n, 1 / RATE)
    lo = (bins >= freq * 0.9) & (bins <= freq * 1.1)
    hi = bins >= CUT_HZ
    e_lo = float(np.sum(spec[lo]))
    e_hi = float(np.sum(spec[hi]))
    peak = float(np.max(np.abs(x)))
    if e_lo <= 0 or e_hi <= 0:
        return float("nan"), float("nan"), peak, 0.0
    return (10 * np.log10(e_hi / e_lo), 10 * np.log10(e_lo), peak,
            impulse_rate(x))


class Rig:
    """Plays a tone and hands back what the microphone heard of it."""

    def __init__(self) -> None:
        self.out = _device(OUT, want_input=False)
        self.mic = _device(MIC, want_input=True)
        self._buf: list[np.ndarray] = []
        self._stream = sd.InputStream(
            device=self.mic, samplerate=RATE, channels=2, dtype="float32",
            callback=lambda d, f, t, s: self._buf.append(d.copy()))

    def __enter__(self) -> "Rig":
        self._stream.start()
        time.sleep(0.5)
        return self

    def __exit__(self, *_exc) -> None:
        self._stream.stop()
        self._stream.close()

    def measure(self, freq: float, db: float) -> tuple[float, float, float, float]:
        amp = float(10 ** (db / 20))
        block = _tone(freq, TONE_S, amp)
        self._buf.clear()
        # Skip the fade-in and the settle; measure the steady middle only.
        sd.play(block, samplerate=RATE, device=self.out, blocking=True)
        sd.wait()
        time.sleep(0.15)
        if not self._buf:
            return float("nan"), float("nan"), 0.0, 0.0
        rec = np.concatenate(self._buf, axis=0)
        edge = int(RATE * 0.3)
        if len(rec) > 3 * edge:
            rec = rec[edge:-edge]
        time.sleep(GAP_S)
        return ratio_db(rec, freq)


def sweep_one(rig: Rig, freq: float, levels: tuple[float, ...],
              *, use_impulses: bool = False) -> dict:
    """Climb from quiet until EITHER detector fires, then stop.

    Two detectors because there are two presentations of one fault, and the
    first version of this tool had only the detector that misses the worse
    one. Whichever fires first sets the threshold.
    """
    rows: list[dict] = []
    baseline: list[float] = []
    threshold = None
    kind = None
    for db in levels:
        ratio, fund, peak, impulses = rig.measure(freq, db)
        rows.append({"db": db, "ratio_db": ratio, "fund_db": fund,
                     "peak": peak, "impulses_per_s": impulses})
        flag = "  CLIPPED - move the mic back" if peak > 0.95 else ""
        if not np.isfinite(ratio):
            print(f"    {db:+5.0f} dBFS   (nothing measurable){flag}")
            continue
        # **A row the microphone could not hear is not evidence of quiet.**
        # Below this the fundamental is buried and the ratio is pure noise -
        # tens of dB positive - which drags the baseline it will later be
        # compared against and can mask a real knee.
        if fund < FUND_FLOOR_DB:
            print(f"    {db:+5.0f} dBFS   (mic cannot hear the tone, "
                  f"fund {fund:.0f}){flag}")
            continue
        if use_impulses and impulses >= IMPULSE_PER_S and ratio <= IMPULSE_SNR_DB:
            threshold, kind = db, "intermittent"
            print(f"    {db:+5.0f} dBFS   ratio {ratio:+6.1f}   "
                  f"{impulses:.1f} thumps/s   <-- KNOCK (intermittent){flag}")
            break
        if len(baseline) >= BASELINE_MIN:
            quiet = float(np.median(baseline))
            if ratio > quiet + RISE_DB:
                threshold, kind = db, "sustained"
                print(f"    {db:+5.0f} dBFS   ratio {ratio:+6.1f}  "
                      f"(baseline {quiet:+.1f})   <-- KNOCK (sustained){flag}")
                break
        print(f"    {db:+5.0f} dBFS   ratio {ratio:+6.1f}   fund {fund:6.1f}"
              f"   {impulses:4.1f} thumps/s{flag}")
        baseline.append(ratio)
    return {"freq": freq, "threshold_db": threshold, "kind": kind,
            "rows": rows,
            "baseline_db": float(np.median(baseline)) if baseline else None}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--amp", type=int, default=35,
                        help="the amp's knob position, recorded not read")
    parser.add_argument("--quick", action="store_true",
                        help="nine frequencies instead of sixteen")
    # **OFF because it does not work.** Measured against its own output on
    # 12 Sep 2026 it fired on 80% of rows that passed the SNR gate and 69% of
    # those that did not - it fires on nearly everything, so it carries no
    # information. It was validated on SYNTHETIC signals (clean sine 0.00/s,
    # two clicks 0.20/s, every cycle 40/s) and passed perfectly; real
    # microphone noise is not Gaussian, and an 8-sigma MAD threshold finds one
    # or two outliers in almost any 4 s window of it. Testing a detector on
    # the noise it will not meet is not testing it.
    #
    # The count is still measured and recorded on every row, because the
    # intermittent knock it was built for is REAL - the driver heard two thuds
    # in ten seconds at 40 Hz where the ratio read textbook flat. It needs a
    # detector with a measured false-alarm rate before it may vote again.
    parser.add_argument("--impulses", action="store_true",
                        help="let the impulse count set thresholds - see the "
                             "note in the source; it has a ~70%% false-alarm "
                             "rate on this microphone")
    args = parser.parse_args()

    freqs = QUICK_FREQS if args.quick else FREQS
    est = len(freqs) * len(LEVELS_DB) * (TONE_S + GAP_S + 0.4) / 60
    print(f"Knock curve, amp recorded as {args.amp}.")
    print(f"{len(freqs)} frequencies x up to {len(LEVELS_DB)} levels, "
          f"{est:.0f} min worst case (less - each stops at onset).")
    print("Mic 20-30 cm from the unit, not touching the rig. Quiet room.\n")

    results = []
    with Rig() as rig:
        # Control first: a frequency measured now and again at the end. If the
        # two disagree the rig or the mic moved and the run is void - the same
        # check that caught a drifting rating on 12 Sep.
        print("  control (50 Hz, -18 dBFS) ...")
        ctl_before = rig.measure(50.0, -18.0)
        print(f"    ratio {ctl_before[0]:+.1f}  fund {ctl_before[1]:.1f}  "
              f"peak {ctl_before[2]:.3f}  {ctl_before[3]:.1f} thumps/s")
        if ctl_before[2] > 0.95:
            print("  CLIPPING at -18 dBFS - move the mic back and re-run.")
            return 1
        if not np.isfinite(ctl_before[0]):
            print("  the microphone is not hearing the unit - check placement.")
            return 1

        for freq in freqs:
            print(f"\n  {freq:.0f} Hz")
            results.append(sweep_one(rig, freq, LEVELS_DB,
                                     use_impulses=args.impulses))

        print("\n  control again (50 Hz, -18 dBFS) ...")
        ctl_after = rig.measure(50.0, -18.0)
        print(f"    ratio {ctl_after[0]:+.1f}  fund {ctl_after[1]:.1f}")

    drift = abs(ctl_after[0] - ctl_before[0])
    print(f"\n  control drift {drift:.1f} dB", end="")
    print("  - fine" if drift < 4.0 else "  - TOO LARGE, treat this run as void")

    print(f"\n  {'Hz':>5}  {'knock at':>9}  {'baseline':>9}")
    for r in results:
        th = f"{r['threshold_db']:+.0f} dBFS" if r["threshold_db"] is not None \
            else "clean to -3"
        base = f"{r['baseline_db']:+.1f}" if r["baseline_db"] is not None else "-"
        print(f"  {r['freq']:5.0f}  {th:>9}  {base:>9}")

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = REPO / "docs" / f"knock-curve_{stamp}.json"
    out.write_text(json.dumps({
        "measured_utc": stamp,
        "amp_volume": args.amp,
        "cut_hz": CUT_HZ,
        "rise_db": RISE_DB,
        "tone_s": TONE_S,
        "control_before": ctl_before[0],
        "control_after": ctl_after[0],
        "control_drift_db": drift,
        "curve": results,
    }, indent=2), encoding="utf-8")
    print(f"\n  written to {out.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
