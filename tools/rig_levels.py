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
  * world velocity **is** stored from 16 Aug onward and is used when present,
    so the sideslip model sees what it sees live. Laps recorded before that
    fall back to differencing position over a +-50 ms stencil, and their
    rotation numbers are a floor rather than an estimate.

    That fallback used to be unconditional, and it hid a finding: a claim that
    a quarter of Road Atlanta reading `rotation` UNKNOWN was an artefact of
    the stencil. Measured with the stored vector it is 26.6% rather than
    23.8% - worse, not better - so the UNKNOWN is the car, not the tool, and a
    cue exempting itself on those frames exempts itself in the field too;
  * `vel_x/y/z` therefore cannot drive the collision detector, so the impact
    channel here carries the kerb strike, the suspension strike, the landing
    and the compression only.

    python tools/rig_levels.py [--laps N] [--db PATH]
                              [--sessions 50,51,52] [--game-version 1.70]

`--sessions` and `--game-version` are what a controlled comparison needs: the
same car at the same track either side of a game update is two replays of the
same tool, and the difference between them is only readable if each side is
the laps it says it is.
"""
from __future__ import annotations

import argparse
import math
import os
import sqlite3
import sys
from collections import Counter

import numpy as np


def _profile_from_argv() -> str:
    """`--profile` has to be read BEFORE `synth` is imported.

    The duck constants are fixed when the module loads, from the same selector
    as the profile, and a replay that took one from the new tune and the other
    from the old would grade a mix that exists nowhere - the defect that nearly
    sent a half-applied Rev A out on 13 Sep 2026.
    """
    for i, arg in enumerate(sys.argv):
        if arg == "--profile" and i + 1 < len(sys.argv):
            return sys.argv[i + 1]
        if arg.startswith("--profile="):
            return arg.split("=", 1)[1]
    return ""


_CHOSEN = _profile_from_argv().strip().upper()
if _CHOSEN in ("A", "B", "C", "D"):
    os.environ["PITCREW_RIG_REV"] = _CHOSEN
elif _CHOSEN == "DEFAULT":
    os.environ.pop("PITCREW_RIG_REV", None)
    os.environ.pop("PITCREW_RIG_REV_A", None)

from pitcrew.rig import transducer  # noqa: E402
from pitcrew.rig.effects import EffectDeriver  # noqa: E402
from pitcrew.rig.synth import (  # noqa: E402
    DUCK_ATTACK_S,
    DUCK_CRITICAL,
    DUCK_DEPTH,
    DUCK_RELEASE_S,
    UNLOAD_ATTACK_S,
    UNLOAD_DUCK,
    UNLOAD_RELEASE_S,
    HapticMix,
    profile_name,
)
from pitcrew.store.db import DEFAULT_DB_PATH, Store  # noqa: E402

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
                 "road_plane_y",
                 "tyre_radius_rl", "tyre_radius_rr", "suspension_fl",
                 "suspension_fr", "suspension_rl", "suspension_rr")


def _load(path: str, count: int, sessions: list[int] | None = None,
          game_version: str = "") -> list[list[dict]]:
    """Laps through `Store`, NOT straight off the blob.

    The store repairs on read: laps recorded before the 2pi fix have slip
    ratios 6.2832 times too large, and reading the blob directly gets those
    raw. Doing exactly that here put wheel-spin at full scale for 54% of the
    lap and very nearly had it reported as a live defect - the live path uses
    the fixed `_slip_ratios` and was always correct.

    **A selection is replayed in the order it was DRIVEN.** The learned
    references - the slip curve, the ABS plateau, the ride-height neutral -
    are not reset between laps, so a session replayed backwards is a system
    that never existed. The unfiltered default keeps its most-recent-first
    order, because "the last eight laps" is what it means.
    """
    store = Store(path)
    # Excluded laps are the rack's own verdict on the same thing MIN_FRAMES
    # catches from the other end, and a phantom lap is not evidence.
    where, params = ["l.excluded = 0"], []
    if sessions:
        where.append(f"l.session_id IN ({','.join('?' * len(sessions))})")
        params.extend(sessions)
    if game_version:
        where.append("s.game_version = ?")
        params.append(game_version)
    order = "ASC" if len(where) > 1 else "DESC"
    ids = sqlite3.connect(f"file:{path}?mode=ro", uri=True).execute(
        "SELECT f.lap_id FROM lap_frames f "
        "JOIN laps l ON l.id = f.lap_id "
        "JOIN sessions s ON s.id = l.session_id "
        f"WHERE {' AND '.join(where)} ORDER BY f.lap_id {order}",
        params).fetchall()
    laps = []
    for (lap_id,) in ids:
        payload = store.get_lap_frames(lap_id)
        if not payload or len(payload["frames"]) < MIN_FRAMES:
            continue
        laps.append(payload["frames"])
        if count and len(laps) >= count:
            break
    return laps


def _floor_dbfs(freq: float) -> float:
    """The driver's measured detection floor at `freq`, held flat outside the
    four frequencies a staircase was run at - a measurement, not a model."""
    points = transducer.PERCEPTION_FLOOR_DBFS
    if freq <= points[0][0]:
        return points[0][1]
    if freq >= points[-1][0]:
        return points[-1][1]
    for (lo_hz, lo), (hi_hz, hi) in zip(points, points[1:]):
        if lo_hz <= freq <= hi_hz:
            return lo + (hi - lo) * (freq - lo_hz) / (hi_hz - lo_hz)
    return points[-1][1]


def _masking_report(specs, amplitude: np.ndarray) -> None:
    """What each cue has to beat at every instant it is live, not at its peak.

    **Written after Rev A failed in the seat** (13 Sep 2026, session 163).
    Every effect in Rev A cleared the driver's floor and stayed under the knock
    curve when checked ALONE, and the mix still buried the traction cue, the
    ripple strip and the gear change under `chassis_load` - because one piston
    sums everything and the check never asked what else was playing. The live
    log caught it at the cue's ONSET (USEFUL_SLIP, 0.14), not at its peak, and
    the older "has to beat the bed" table above only looks at the top tenth of
    an event's own maximum, which is where a cue is least likely to be lost.

    Every voice is put on one scale - dB above the driver's floor at its own
    centre frequency - so a quiet 60 Hz voice and a louder 95 Hz one compare
    the way he feels them. A cue is "live" wherever it clears his floor on its
    own; its margin is how far it stands above the strongest OTHER voice at
    that instant. Below zero it is not the strongest thing on the piston, which
    is what "buried" meant from the seat.

    Stated approximations: centre frequency rather than the swept one, and a
    floor measured with pure tones in silence. Masking between cues in the
    literature is stronger than this assumes, not weaker - lower-frequency,
    continuous voices dominate - so a margin near zero here is worse in the car.
    """
    floors = np.array([_floor_dbfs(spec.centre_hz) for spec in specs])
    with np.errstate(divide="ignore"):
        above = 20.0 * np.log10(np.maximum(amplitude, 1e-9)) - floors
    felt = above > 0.0

    print("\nOver the driver's floor, and what each cue must beat while it is "
          "live:\n")
    print(f"  {'effect':14s} {'felt %':>7}")
    for index, spec in enumerate(specs):
        print(f"  {spec.name:14s} {100.0 * float(felt[:, index].mean()):6.1f}%")

    print(f"\n  {'cue':14s} {'live %':>7} {'median':>7} {'worst10':>8} "
          f"{'buried':>7}  most often under")
    for index, spec in enumerate(specs):
        if spec.priority > 1:          # CRITICAL and TRANSIENT only
            continue
        live = felt[:, index]
        if not live.any():
            print(f"  {spec.name:14s} {'never':>7}")
            continue
        others = above[live].copy()
        others[:, index] = -np.inf
        strongest = others.max(axis=1)
        margin = above[live, index] - strongest
        buried = margin < 0.0
        who = Counter(specs[int(k)].name for k in
                      others[buried].argmax(axis=1)) if buried.any() else Counter()
        masker = ", ".join(f"{n} {100.0 * c / buried.sum():.0f}%"
                           for n, c in who.most_common(2)) or "-"
        print(f"  {spec.name:14s} {100.0 * float(live.mean()):6.2f}% "
              f"{float(np.median(margin)):+6.1f} "
              f"{float(np.percentile(margin, 10)):+7.1f} "
              f"{100.0 * float(buried.mean()):6.1f}%  {masker}")
    print("\n  median / worst10 = dB the cue stands above the strongest other "
          "voice;\n  buried = share of its live time something else is "
          "stronger")


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
        # **The stored velocity vector where there is one.** Differencing
        # position is a good direction and a poor derivative: it smooths the
        # heading over 100 ms, which flatters `_HeadingCheck`'s correlation and
        # therefore its trust. An instrument that makes the model look more
        # certain than it is will hide exactly the faults it exists to find.
        vx, vz = row.get("vel_x"), row.get("vel_z")
        if vx is None or vz is None:
            frame.vel_x = float(dx[index])
            frame.vel_z = float(dz[index])
        else:
            frame.vel_x = float(vx)
            frame.vel_z = float(vz)
        frame.vel_y = float(row.get("vel_y") or 0.0)
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
        # **The road plane, so the rotation witness can refuse on banking.**
        # Without it every replayed lap looks level and the tool measures a
        # system the car never runs.
        frame.road_plane_y = row.get("road_plane_y")
        frame.car_on_track = True
        frame.paused = False
        out.append(frame)
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--laps", type=int, default=0)
    parser.add_argument("--db", default=str(DEFAULT_DB_PATH))
    parser.add_argument("--sessions", default="",
                        help="comma-separated session ids")
    parser.add_argument("--game-version", default="",
                        help="every framed lap recorded on this version")
    # **Without this every replay silently measures the ABS-on branch.**
    # `EffectDeriver` starts with no assist declared, so it falls back to
    # ABS_ON - and a replay of ABS-Off laps then reports numbers for code that
    # will never run on them. That is exactly how a 0.31% -> 0.77% improvement
    # turned out to be a 0.35% -> 0.21% regression when it was finally
    # exercised properly.
    parser.add_argument("--abs", default="", choices=["", "Off", "Weak",
                                                      "Default"],
                        help="the assist declared on the event these laps "
                             "were driven under; omit only for laps whose "
                             "assist you do not know")
    parser.add_argument("--profile", default="",
                        choices=["", "default", "A", "B", "C", "D", "a", "b", "c", "d"],
                        help="replay a trial tune instead of the selected one")
    args = parser.parse_args()

    sessions = [int(part) for part in args.sessions.split(",") if part.strip()]
    # A selection replays all of itself - taking eight of ninety-seven laps
    # and calling it a session is how a comparison goes wrong quietly - while
    # an unselected run keeps the old default of the eight most recent.
    count = args.laps or (0 if (sessions or args.game_version) else 8)

    laps = _load(args.db, count, sessions, args.game_version)
    if not laps:
        raise SystemExit("no recorded laps in that database")

    deriver = EffectDeriver()
    deriver.set_abs(args.abs or None)
    mix = HapticMix(block=512)
    # **The profile the mix was built with, not `synth.PROFILE`.** This read
    # the module default for shaping and priority while `_scale` came from the
    # mix, so any trial tune was graded half as itself and half as the default.
    specs = mix.specs
    print(f"profile {profile_name(specs)} - duck {DUCK_DEPTH:.2f} / "
          f"critical {DUCK_CRITICAL:.2f}")
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
    for index, spec in enumerate(specs):
        shaped[:, index] = [spec.shape(float(v)) for v in values[:, index]]
    priority = np.array([spec.priority for spec in specs])
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
    for index, spec in enumerate(specs):
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
        spec = specs[index]
        mine = float(np.median(amplitude[when, index]))
        felt_mine = mine * transducer.felt_response(spec.centre_hz)
        decibels = 20 * math.log10(mine) if mine > 0 else float("-inf")
        print(f"\n  {event} fires at {mine:.4f} ({decibels:.1f} dBFS), "
              f"{spec.centre_hz:.0f} Hz, felt {felt_mine:.4f}")
        for other_index, other in enumerate(specs):
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

    _masking_report(specs, amplitude)

    print("\nWhat the driver was told, as a fraction of the laps:")
    for label, seen in (("traction", Counter(s.traction for s in states)),
                        ("brake", Counter(s.brake_state for s in states)),
                        ("rotation", Counter(s.rotation for s in states))):
        parts = ", ".join(f"{name} {100.0 * n / frames:.1f}%"
                          for name, n in seen.most_common())
        print(f"  {label:9s} {parts}")


if __name__ == "__main__":
    main()
