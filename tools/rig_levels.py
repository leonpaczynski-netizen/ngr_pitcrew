"""What every haptic effect actually delivers, over laps he really drove.

Tuning by feel needs a number to argue with. This replays recorded laps
through the real derivers' own constants and the real gain chain, and prints
the amplitude each effect reaches - so "a little strong" and "can't feel it"
can be checked against what the mix was doing at the time, rather than
answered with another guess.

Two channels are approximated and say so: wheel-spin uses the recorded slip
ratios rather than re-deriving them from wheel speed, and the impact channel
is the kerb thump only, because world velocity is not recorded per frame. The
kerb thump is the whole of that channel in practice anyway.

    python tools/rig_levels.py [--laps N] [--db PATH]
"""
from __future__ import annotations

import argparse
import sqlite3

import numpy as np

from pitcrew.rig import effects as fx
from pitcrew.rig import transducer
from pitcrew.rig.synth import (
    DUCK_ATTACK_S,
    DUCK_DEPTH,
    DUCK_RELEASE_S,
    PORSCHE_RSR_17,
    HapticMix,
)
from pitcrew.store.db import DEFAULT_DB_PATH, Store

WHEELS = ("fl", "fr", "rl", "rr")
DT = 1.0 / 60.0


# Short of a lap. The rack marks these excluded and so does this - a 192-frame
# fragment claiming a full lap time is what a phantom lap looks like.
MIN_FRAMES = 3000


def _load(path: str, count: int) -> list[list[dict]]:
    """Laps through `Store`, NOT straight off the blob.

    The store repairs on read: laps recorded before the 2pi fix have slip
    ratios 6.2832 times too large, and reading the blob directly gets those
    raw. Doing exactly that here put wheel-spin at full scale for 54% of the
    lap and very nearly had it reported as a live defect - the live path uses
    the fixed `_slip_ratios` and was always correct.
    """
    store = Store(path)
    ids = sqlite3.connect(f"file:{path}?mode=ro", uri=True).execute(
        "SELECT lap_id FROM lap_frames ORDER BY lap_id DESC").fetchall()
    laps = []
    for (lap_id,) in ids:
        payload = store.get_lap_frames(lap_id)
        if not payload or len(payload["frames"]) < MIN_FRAMES:
            continue
        laps.append(payload["frames"])
        if len(laps) >= count:
            break
    return laps


def _decay_pulse(fires: np.ndarray, level: np.ndarray, tau: float) -> np.ndarray:
    """A pulse that jumps on an edge and decays, as the derivers do it."""
    out = np.zeros(len(fires))
    factor = float(np.exp(-DT / tau))
    held = 0.0
    for i in range(len(fires)):
        held *= factor
        if fires[i]:
            held = max(held, float(level[i]))
        out[i] = held
    return out


def _intensities(rows: list[dict]) -> dict[str, np.ndarray]:
    def col(name: str) -> np.ndarray:
        # `None` is "not measured" everywhere in this app, and slip is null
        # below walking pace. Zero is the wrong stand-in for a ratio whose
        # zero means "locked solid", so those frames become 1.0 - rolling
        # true, which is what the car was doing.
        default = 1.0 if name.startswith("slip_") else 0.0
        return np.array([default if r.get(name) is None else r[name]
                         for r in rows], dtype=float)

    surf = [tuple((r.get(f"surf_{c}") or "T") for c in WHEELS) for r in rows]
    speed, lat_g = col("speed_kph"), np.abs(col("lat_g"))
    throttle, brake = col("throttle_pct") / 100.0, col("brake_pct") / 100.0
    slow = speed / 3.6 < fx.SLIP_MIN_SPEED_MS

    # Road texture, as `_rumble` derives it. Suspension is metres in the
    # packet and millimetres in the recording, hence the thousand.
    susp = np.stack([col(f"susp_mm_{c}") / 1000.0 for c in WHEELS], axis=1)
    velocity = np.zeros(len(rows))
    velocity[1:] = np.abs(np.diff(susp, axis=0)).sum(axis=1) / (4.0 * DT)
    texture = np.clip(velocity / fx.TEXTURE_FULL_MS, 0.0, 1.0)
    texture *= np.minimum(1.0, speed / fx.TEXTURE_FULL_SPEED_KPH)
    on_kerb = np.array([any(s == "C" for s in f) for f in surf])
    off = np.array([any(s in ("D", "G", "S", "s") for s in f) for f in surf])
    texture = np.where(
        on_kerb, np.minimum(1.0, texture + fx.KERB_BOOST),
        np.where(off, np.minimum(1.0, texture + fx.OFF_SURFACE_BOOST), texture))

    lateral = np.clip((lat_g - fx.LAT_G_ONSET)
                      / (fx.LAT_G_FULL - fx.LAT_G_ONSET), 0.0, 1.0)
    lateral[slow] = 0.0

    arrived = np.zeros(len(rows), dtype=bool)
    for i in range(1, len(rows)):
        arrived[i] = any(now == "C" and was == "T"
                         for now, was in zip(surf[i], surf[i - 1]))
    thump = _decay_pulse(arrived, np.full(len(rows), fx.KERB_THUMP),
                         fx.KERB_THUMP_DECAY_S)

    gear, rpm = col("gear"), col("rpm")
    fraction = np.clip(rpm / max(rpm.max(), 1.0), 0.0, 1.0)
    shifted = np.zeros(len(rows), dtype=bool)
    shifted[1:] = (gear[1:] != gear[:-1]) & (gear[1:] > 0) & (gear[:-1] > 0)
    scale = np.clip((fraction - fx.GEAR_RPM_MIN)
                    / (fx.GEAR_RPM_MAX - fx.GEAR_RPM_MIN), 0.0, 1.0)
    pulse = _decay_pulse(shifted, 0.35 + 0.65 * scale, fx.GEAR_DECAY_S)

    revs = np.interp(fraction * 100.0, [x for x, _ in fx.RPM_CURVE],
                     [y for _, y in fx.RPM_CURVE]) / 100.0

    slip = np.stack([col(f"slip_{c}") for c in WHEELS], axis=1)
    spin = np.clip((slip.max(axis=1) - 1.0 - fx.SPIN_ONSET)
                   / (fx.SPIN_FULL - fx.SPIN_ONSET), 0.0, 1.0)
    lock = np.clip((1.0 - slip.min(axis=1) - fx.LOCK_ONSET)
                   / (fx.LOCK_FULL - fx.LOCK_ONSET), 0.0, 1.0)
    lock[brake < fx.PEDAL_ON] = 0.0
    spin[throttle < fx.PEDAL_ON] *= 0.5
    spin_lock = np.maximum(spin, lock)
    spin_lock[slow] = 0.0

    return {"wheels_spin_lock": spin_lock, "gear": pulse,
            "wheels_rumble": texture, "lateral_load": lateral,
            "wheels_impact": thump, "rpm": revs}


def _duck(joined: dict[str, np.ndarray], mix: HapticMix) -> np.ndarray:
    """The gain the sustained effects are under, frame by frame.

    `HapticMix.render` does this per block; at 512 samples that is 10.7 ms
    against a frame's 16.7, so doing it per frame here is within a frame of
    the real thing and needs no audio clock.
    """
    events = np.zeros(len(joined["rpm"]))
    for spec in PORSCHE_RSR_17:
        if not spec.transient:
            continue
        shaped = np.array([spec.shape(float(v)) for v in joined[spec.name]])
        events = np.maximum(events, shaped)
    out = np.ones(len(events))
    held = 1.0
    for i, event in enumerate(events):
        aim = 1.0 - DUCK_DEPTH * float(event)
        tau = DUCK_ATTACK_S if aim < held else DUCK_RELEASE_S
        held += (aim - held) * min(1.0, DT / tau)
        out[i] = held
    return out


def _amplitude(mix: HapticMix, name: str, raw: np.ndarray,
               duck: np.ndarray | None = None) -> np.ndarray:
    index = mix.names.index(name)
    spec = mix.specs[index]
    amplitude = np.array([spec.shape(float(v)) for v in raw]) * float(mix._scale[index])
    if duck is not None and not spec.transient:
        amplitude = amplitude * duck
    return amplitude


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--laps", type=int, default=6)
    parser.add_argument("--db", default=str(DEFAULT_DB_PATH))
    args = parser.parse_args()

    laps = _load(args.db, args.laps)
    if not laps:
        raise SystemExit("no recorded laps in that database")
    per = [_intensities(rows) for rows in laps]
    joined = {name: np.concatenate([p[name] for p in per]) for name in per[0]}
    frames = len(joined["rpm"])
    mix = HapticMix(block=512)
    duck = _duck(joined, mix)

    print(f"{frames} frames over {len(laps)} laps "
          f"({frames / 3600.0:.1f} minutes)\n")
    print(f"{'effect':18s} {'Hz':>9} {'felt':>5} {'median':>8} {'p99':>8} "
          f"{'peak':>8} {'peak dB':>8} {'live':>6}")
    for spec in PORSCHE_RSR_17:
        amp = _amplitude(mix, spec.name, joined[spec.name], duck)
        top = spec.freq_hi or spec.freq_lo
        band = f"{spec.freq_lo:.0f}-{top:.0f}" if spec.freq_hi else f"{spec.freq_lo:.0f}"
        peak = float(amp.max())
        decibels = 20.0 * np.log10(peak) if peak > 0 else float("-inf")
        print(f"{spec.name:18s} {band:>9} "
              f"{transducer.felt_response((spec.freq_lo + top) / 2.0):5.1f} "
              f"{np.median(amp):8.4f} {np.percentile(amp, 99):8.4f} "
              f"{peak:8.4f} {decibels:8.1f} "
              f"{100.0 * float((amp > 0.001).mean()):5.0f}%")

    print(f"
the bed ducks to a median of {np.median(duck):.2f}, a minimum of {duck.min():.2f}")
    print("\nAn event has to beat the bed it lands on, and with one piston "
          "the bed\nis everything else playing at that instant:")
    for event in ("gear", "wheels_impact"):
        raw = joined[event]
        when = raw >= raw.max() * 0.9
        if not when.any():
            continue
        mine = float(np.median(_amplitude(mix, event, raw)[when]))
        spec = mix.specs[mix.names.index(event)]
        print(f"\n  {event} fires at {mine:.4f} "
              f"({20 * np.log10(mine):.1f} dBFS), {spec.freq_lo:.0f} Hz")
        for other in mix.names:
            if other == event:
                continue
            bed = float(np.median(_amplitude(mix, other, joined[other],
                                             duck)[when]))
            ospec = mix.specs[mix.names.index(other)]
            shared = (min(spec.freq_hi or spec.freq_lo, ospec.freq_hi or ospec.freq_lo)
                      >= max(spec.freq_lo, ospec.freq_lo))
            over = 20.0 * np.log10(mine / bed) if bed > 0 else float("inf")
            print(f"    over {other:18s} {bed:8.4f} {over:+7.1f} dB"
                  f"{'   SAME REGION' if shared else ''}")


if __name__ == "__main__":
    main()
