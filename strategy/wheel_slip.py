"""Per-axle / per-wheel slip classification from one live telemetry frame (pure, Qt-free).

Generalises the per-lap, four-wheel-averaged wheelspin/lockup counters in
``telemetry.recorder._compute_stats`` to a per-sample, per-axle classification the
Phase-5 corner diagnosis can actually consume — the ``_CORNER_CAUSES`` table asks for
"rear wheel-slip by wheel" and "per-axle brake lock", which the four-wheel average
cannot supply.

The ratio thresholds mirror ``telemetry.recorder`` so live and per-lap detection agree;
the only change is that they are applied to each axle separately (and wheelspin is
attributed to the DRIVEN axle) instead of the four-wheel mean.

Authors no setup values, calls no AI, touches no Qt/DB/files.
"""
from __future__ import annotations

from dataclasses import dataclass

_TWO_PI = 6.283185307  # 2π — avoids importing math (matches recorder._TWO_PI)

# Thresholds — keep in sync with telemetry.recorder._compute_stats.
SPIN_THROTTLE_MIN = 0.7     # throttle fraction to consider wheelspin
SPIN_SPEED_RATIO = 1.3      # driven-wheel linear speed > 130% of ground speed
LOCK_BRAKE_MIN = 0.3        # brake fraction to consider lockup
LOCK_SPEED_RATIO = 0.5      # wheel linear speed < 50% of ground speed
MIN_SPEED_MS = 2.0          # ignore near-stationary frames

# Wheel order in the packet tuples is FL, FR, RL, RR.
_FRONT = (0, 1)
_REAR = (2, 3)


def _axle_speed_ms(rps, radius, idx) -> float:
    """Mean linear tyre speed (m/s) for the wheels at ``idx`` (rps × radius × 2π)."""
    vals = []
    for i in idx:
        try:
            vals.append(abs(float(rps[i])) * float(radius[i]) * _TWO_PI)
        except (TypeError, ValueError, IndexError):
            continue
    return sum(vals) / len(vals) if vals else 0.0


def driven_axle(drivetrain: str) -> str:
    """The driven axle for wheelspin attribution. Unknown/rear-engined default to rear."""
    dt = (drivetrain or "").strip().upper()
    if dt == "FF":
        return "front"
    if dt in ("AWD", "4WD"):
        return "all"
    return "rear"   # FR, MR, RR, and unknown → rear-driven


@dataclass(frozen=True)
class SlipSample:
    kind: str          # "wheelspin" | "lockup" | "clean"
    axle: str          # "front" | "rear" | "all" | ""
    slip_ratio: float  # wheel_speed / ground_speed (>1 spinning, <1 locked); 0 when clean

    def as_json(self) -> dict:
        return {"kind": self.kind, "axle": self.axle,
                "slip_ratio": round(self.slip_ratio, 3)}


_CLEAN = SlipSample("clean", "", 0.0)


def classify_wheel_slip(wheel_rps, tyre_radius, speed_ms: float,
                        throttle: float, brake: float,
                        drivetrain: str = "") -> SlipSample:
    """Classify a single frame as driven-axle wheelspin, per-axle lockup, or clean.

    Wheelspin is only attributed to the DRIVEN axle (so a RWD car's front wheels
    turning faster than the ground under braking is not mistaken for power oversteer).
    Lockup is checked on whichever axle drops below the ground speed under braking.
    Never raises — degrades to "clean" on malformed input.
    """
    try:
        speed_ms = float(speed_ms)
    except (TypeError, ValueError):
        return _CLEAN
    if speed_ms <= MIN_SPEED_MS:
        return _CLEAN
    front_ms = _axle_speed_ms(wheel_rps, tyre_radius, _FRONT)
    rear_ms = _axle_speed_ms(wheel_rps, tyre_radius, _REAR)

    # Wheelspin — driven axle turning faster than the ground under throttle.
    if float(throttle or 0.0) >= SPIN_THROTTLE_MIN:
        driven = driven_axle(drivetrain)
        candidates = []
        if driven in ("front", "all"):
            candidates.append(("front", front_ms))
        if driven in ("rear", "all"):
            candidates.append(("rear", rear_ms))
        spun = [(ax, ms / speed_ms) for ax, ms in candidates
                if ms > speed_ms * SPIN_SPEED_RATIO]
        if spun:
            ax, ratio = max(spun, key=lambda t: t[1])
            return SlipSample("wheelspin", "all" if len(spun) > 1 else ax, ratio)

    # Lockup — an axle dropping well below the ground speed under braking.
    if float(brake or 0.0) >= LOCK_BRAKE_MIN:
        locked = [(ax, ms / speed_ms) for ax, ms in (("front", front_ms), ("rear", rear_ms))
                  if ms < speed_ms * LOCK_SPEED_RATIO]
        if locked:
            ax, ratio = min(locked, key=lambda t: t[1])
            return SlipSample("lockup", "all" if len(locked) > 1 else ax, ratio)

    return _CLEAN
