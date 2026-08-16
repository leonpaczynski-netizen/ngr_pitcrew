"""What every haptic effect actually delivers, over laps he really drove.

Tuning by feel needs a number to argue with. This replays recorded laps
through **the real derivers and the real gain chain** - `VehicleModel`,
`EffectDeriver` and `HapticMix`, the same objects the running app uses - and
prints the amplitude each effect reaches, so "a little strong" and "can't feel
it" can be checked against what the mix was doing at the time rather than
answered with another guess.

The earlier version of this tool reimplemented the derivers in numpy. That is
how it came to be measuring a slightly different system from the one being
driven, and it is why this one drives the real objects a frame at a time
instead. It is slower and it cannot drift.

**What is approximated, and it is stated here because it bounds the answers.**
The lap store keeps 37 channels and the packet has more, so three inputs are
reconstructed:

  * wheel rates come back from the stored slip ratios and tyre radius rather
    than from `wheel_rps`, which is exact to the precision the ratios were
    rounded to;
  * world velocity is not stored, so the heading the sideslip model needs is
    differenced from position over a +-50 ms stencil. Live it comes from the
    velocity vector and needs no differencing, so the rotation numbers here
    are a floor rather than an estimate;
  * `vel_x/y/z` therefore cannot drive the collision detector, so the impact
    channel here carries the kerb strike, the suspension strike, the landing
    and the compression only.

    python tools/rig_levels.py [--laps N] [--db PATH]
"""
from __future__ import annotations

import argparse
import math
import sqlite3
from collections import Counter

import numpy as np

from pitcrew.rig import transducer
from pitcrew.rig.effects import EffectDeriver
from pitcrew.rig.synth import (
    DUCK_ATTACK_S,
    DUCK_CRITICAL,
    DUCK_DEPTH,
    DUCK_RELEASE_S,
    PROFILE,
    UNLOAD_ATTACK_S,
    UNLOAD_DUCK,
    UNLOAD_RELEASE_S,
    HapticMix,
)
from pitcrew.store.db import DEFAULT_DB_PATH, Store

WHEELS = ("fl", "fr", "rl", "rr")
DT = 1.0 / 60.0

# Short of a lap. The rack marks these excluded and so does this - a 192-frame
# fragment claiming a full lap time is what a phantom lap looks like.
MIN_FRAMES = 3000

# Half-width of the stencil the path heading is taken over. Positions are
# stored to the centimetre and the car covers about 1.3 m per frame, so a
# single-frame difference is 1% noise; +-3 frames measured a correlation of
# -0.994 against the yaw rate and +-5 gave -0.9985.
HEADING_STENCIL = 3


class _Frame:
    """Enough of a `GT7Packet` for the real derivers, from a stored frame."""

    __slots__ = ("speed_ms", "speed_kmh", "throttle", "brake", "angvel_y",
                 "vel_x", "vel_y", "vel_z", "current_gear", "engine_rpm",
                 "rpm_alert_max", "rev_limiter_active", "surface_types",
                 "steering_norm", "car_on_track", "paused",
                 "wheel_rps_fl", "wheel_rps_fr", "wheel_rps_rl",
                 "wheel_rps_rr", "tyre_radius_fl", "tyre_radius_fr",
                 "tyre_radius_rl", "tyre_radius_rr", "suspension_fl",
                 "suspension_fr", "suspension_rl", "suspension_rr")


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


def _number(row: dict, key: str, default: float = 0.0) -> float:
    value = row.get(key)
    return default if value is None else float(value)


def _frames(rows: list[dict]) -> list[_Frame]:
    count = len(rows)
    xs = np.array([_number(r, "pos_x") for r in rows])
    zs = np.array([_number(r, "pos_z") for r in rows])
    k = HEADING_STENCIL
    dx = np.zeros(count)
    dz = np.zeros(count)
    if count > 2 * k:
        dx[k:count - k] = xs[2 * k:] - xs[:count - 2 * k]
        dz[k:count - k] = zs[2 * k:] - zs[:count - 2 * k]
        dx[:k], dz[:k] = dx[k], dz[k]
        dx[count - k:], dz[count - k:] = dx[count - k - 1], dz[count - k - 1]

    top_rpm = max((_number(r, "rpm") for r in rows), default=0.0) or 1.0
    out = []
    for index, row in enumerate(rows):
        frame = _Frame()
        frame.speed_kmh = _number(row, "speed_kph")
        frame.speed_ms = frame.speed_kmh / 3.6
        frame.throttle = _number(row, "throttle_pct") / 100.0
        frame.brake = _number(row, "brake_pct") / 100.0
        frame.angvel_y = _number(row, "yaw_rate")
        # The heading the model wants comes from the velocity vector; here it
        # comes from where the car actually went, which is the same direction.
        frame.vel_x = float(dx[index])
        frame.vel_z = float(dz[index])
        frame.vel_y = 0.0
        radius = _number(row, "tyre_radius_m", 0.355) or 0.355
        for wheel in WHEELS:
            slip = row.get(f"slip_{wheel}")
            slip = 1.0 if slip is None else float(slip)
            setattr(frame, f"wheel_rps_{wheel}", slip * frame.speed_ms / radius)
            setattr(frame, f"tyre_radius_{wheel}", radius)
            setattr(frame, f"suspension_{wheel}",
                    _number(row, f"susp_mm_{wheel}") / 1000.0)
        frame.current_gear = int(_number(row, "gear"))
        frame.engine_rpm = _number(row, "rpm")
        # The store does not keep the car's own limiter, so the highest rev
        # seen in the lap stands in for it. It moves the engine bed's absolute
        # level slightly and nothing else.
        frame.rpm_alert_max = top_rpm
        frame.rev_limiter_active = _number(row, "rev_limiter") > 0.5
        frame.surface_types = tuple((row.get(f"surf_{w}") or "T")
                                    for w in WHEELS)
        frame.steering_norm = _number(row, "steering_norm")
        frame.car_on_track = True
        frame.paused = False
        out.append(frame)
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--laps", type=int, default=8)
    parser.add_argument("--db", default=str(DEFAULT_DB_PATH))
    args = parser.parse_args()

    laps = _load(args.db, args.laps)
    if not laps:
        raise SystemExit("no recorded laps in that database")

    deriver = EffectDeriver()
    mix = HapticMix(block=512)
    width = len(deriver.NAMES)
    raw: list[np.ndarray] = []
    states = []
    # **Not reset between laps.** The app resets between sessions, and the
    # learned references are most of the point - resetting per lap would
    # measure a system permanently in its first four seconds.
    for rows in laps:
        for frame in _frames(rows):
            raw.append(deriver.update(frame).copy())
            states.append(deriver.state)
    values = np.stack(raw)
    frames = len(values)

    # The gain chain, per frame, exactly as `HapticMix.render` applies it.
    shaped = np.zeros((frames, width))
    for index, spec in enumerate(PROFILE):
        shaped[:, index] = [spec.shape(float(v)) for v in values[:, index]]
    priority = np.array([spec.priority for spec in PROFILE])
    critical = priority == 0
    transient = priority == 1
    background = priority >= 2

    duck = np.ones(frames)
    unload_duck = np.ones(frames)
    held, light = 1.0, 1.0
    for i in range(frames):
        event = shaped[i, transient].max() if transient.any() else 0.0
        worst = shaped[i, critical].max() if critical.any() else 0.0
        aim = 1.0 - max(DUCK_DEPTH * event, DUCK_CRITICAL * worst)
        tau = DUCK_ATTACK_S if aim < held else DUCK_RELEASE_S
        held += (aim - held) * min(1.0, DT / tau)
        duck[i] = held
        want = 1.0 - UNLOAD_DUCK * float(values[i, width])
        tau = UNLOAD_ATTACK_S if want < light else UNLOAD_RELEASE_S
        light += (want - light) * min(1.0, DT / tau)
        unload_duck[i] = light

    amplitude = shaped * np.asarray(mix._scale)
    amplitude[:, background] *= (duck * unload_duck)[:, None]

    print(f"{frames} frames over {len(laps)} laps "
          f"({frames / 3600.0:.1f} minutes)\n")
    print(f"{'effect':15s} {'class':>9} {'Hz':>9} {'felt':>5} {'median':>8} "
          f"{'p99':>8} {'peak':>8} {'peak dB':>8} {'live':>6}")
    labels = ("CRITICAL", "TRANSIENT", "STATE", "BED")
    for index, spec in enumerate(PROFILE):
        amp = amplitude[:, index]
        top = spec.freq_hi or spec.freq_lo
        band = (f"{spec.freq_lo:.0f}-{top:.0f}" if spec.freq_hi
                else f"{spec.freq_lo:.0f}")
        peak = float(amp.max())
        decibels = 20.0 * math.log10(peak) if peak > 0 else float("-inf")
        print(f"{spec.name:15s} {labels[spec.priority]:>9} {band:>9} "
              f"{transducer.felt_response(spec.centre_hz):5.1f} "
              f"{np.median(amp):8.4f} {np.percentile(amp, 99):8.4f} "
              f"{peak:8.4f} {decibels:8.1f} "
              f"{100.0 * float((amp > 0.001).mean()):5.0f}%")

    print(f"\nthe background sits at a median of {np.median(duck):.2f} of full "
          f"and a minimum of {duck.min():.2f};\nthe unload modifier takes it "
          f"to {unload_duck.min():.2f} at its deepest")

    print("\nAn event has to beat the bed it lands on, and with one piston "
          "the bed is\neverything else playing at that instant. Compared in "
          "FELT strength, not\namplitude: this rig delivers 3.0 at 45 Hz and "
          "2.0 at 95, a factor of 1.5.")
    for event in ("driveline", "impact", "brake_limit", "rear_traction"):
        index = deriver.NAMES.index(event)
        column = values[:, index]
        when = column >= max(column.max() * 0.9, 1e-6)
        if not when.any():
            continue
        spec = PROFILE[index]
        mine = float(np.median(amplitude[when, index]))
        felt_mine = mine * transducer.felt_response(spec.centre_hz)
        decibels = 20 * math.log10(mine) if mine > 0 else float("-inf")
        print(f"\n  {event} fires at {mine:.4f} ({decibels:.1f} dBFS), "
              f"{spec.centre_hz:.0f} Hz, felt {felt_mine:.4f}")
        for other_index, other in enumerate(PROFILE):
            if other_index == index:
                continue
            bed = float(np.median(amplitude[when, other_index]))
            felt_bed = bed * transducer.felt_response(other.centre_hz)
            shared = (min(spec.freq_hi or spec.freq_lo,
                          other.freq_hi or other.freq_lo)
                      >= max(spec.freq_lo, other.freq_lo))
            mark = "   SAME BAND" if shared else ""
            if felt_bed < 1e-4:
                print(f"    over {other.name:15s} {bed:8.4f}    silent{mark}")
                continue
            print(f"    over {other.name:15s} {bed:8.4f}  x"
                  f"{felt_mine / felt_bed:7.2f} felt{mark}")

    print("\nWhat the driver was told, as a fraction of the laps:")
    for label, seen in (("traction", Counter(s.traction for s in states)),
                        ("brake", Counter(s.brake_state for s in states)),
                        ("rotation", Counter(s.rotation for s in states))):
        parts = ", ".join(f"{name} {100.0 * n / frames:.1f}%"
                          for name, n in seen.most_common())
        print(f"  {label:9s} {parts}")


if __name__ == "__main__":
    main()
