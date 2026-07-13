"""Evidence-scaled driver-fit layer (pure, Qt-free).

The audit (docs/AUDIT_setup_brain_engineer_evolution.md, Gap 3) found the driver
profile applied a handful of FIXED one-click nudges (two of which cancel), scaled to
nothing (not the car's range, not how far the current car is from what the driver
wants), and touched no value on the telemetry path.

A real engineer tailors the car to the driver *in proportion to how far it is from
what they like* — and leaves it alone when it already fits. This module does that:

  * each driver preference maps to a TARGET ZONE on the relevant fields (as a
    fraction of the car's legal range) with a STRENGTH;
  * the adjustment is EVIDENCE-SCALED — proportional to the gap between the current
    value and the driver's target, weighted by strength, expressed as a fraction of
    the field's range (so one "click" means the same thing on a 1–10 and a 1–40 bar);
  * it is ZERO inside a dead-zone (the car already suits the driver — don't fix what
    fits);
  * opposing preferences on the same field are NET-resolved into one intentional
    target (e.g. "rotation without snap" vs "consistency" on the braking diff), not
    an accidental cancellation.

It authors no value the range clamp/validator would not, calls no AI, and never
auto-applies — it produces bounded intents that flow through the same pipeline as any
other bias.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional


# Each driver preference is a DIRECTION + a COMFORT THRESHOLD (as a fraction of the
# car's legal range), NOT an absolute target — so the nudge only fires when the car
# actively VIOLATES the preference and stops once the field is on the driver's side.
# This is what keeps driver-fit from fighting a legitimate car/track engineering value.
#
#   direction -1 = the driver wants this field LOWER (at/below the threshold)
#   direction +1 = the driver wants this field HIGHER (at/above the threshold)
#
# Sign conventions (verified against setup_baseline / the validator):
#   arb_*      lower = softer = MORE grip on that axle
#   aero_*     higher = more downforce = MORE grip
#   toe_front  lower = toe-OUT = front bite / turn-in
#   toe_rear   higher = toe-IN = rear stability
#   brake_bias lower = FORWARD (front)
#   lsd_accel  lower = less accel lock (less snap on power)
#   lsd_decel  lower = freer coast diff (more entry rotation)
# flag -> (strength 0..1, {field: (direction, comfort_threshold_fraction)})
_DRIVER_PREFS: dict[str, tuple] = {
    "prefers_front_bite":     (0.9, {"arb_front": (-1, 0.45), "toe_front": (-1, 0.45),
                                     "aero_front": (+1, 0.45)}),
    "dislikes_floaty_front":  (0.7, {"aero_front": (+1, 0.50)}),
    "prefers_rear_stability": (0.9, {"toe_rear": (+1, 0.50), "aero_rear": (+1, 0.45)}),
    "protects_downforce":     (0.6, {"aero_rear": (+1, 0.40), "aero_front": (+1, 0.35)}),
    "trail_braker":           (0.8, {"brake_bias": (-1, 0.50)}),
    "dislikes_snap_exit":     (0.9, {"lsd_accel": (-1, 0.55)}),
    # Opposing prefs on lsd_decel form a comfort BAND [0.45, 0.55]: below → pull up
    # for consistency, above → free it for entry rotation, inside → leave alone.
    "rotation_without_snap":  (0.6, {"lsd_decel": (-1, 0.55)}),
    "race_values_consistency": (0.6, {"lsd_decel": (+1, 0.45)}),
}

# Readable "why" per flag.
_FLAG_REASON = {
    "prefers_front_bite": "you want immediate front bite",
    "dislikes_floaty_front": "you dislike a floaty front",
    "prefers_rear_stability": "you want a planted, stable rear",
    "protects_downforce": "you don't run minimum downforce",
    "trail_braker": "you trail-brake and rotate on brake release",
    "dislikes_snap_exit": "you want a predictable, no-snap exit",
    "rotation_without_snap": "you want entry rotation without snap",
    "race_values_consistency": "you value consistency over one-lap peak",
}

# Inside this fraction of the range from the driver's target, the car already fits —
# no change. Beyond it, the move scales with the gap up to the cap.
_DEADZONE = 0.06
_MAX_MOVE_FRAC = 0.15    # a driver-fit move never exceeds 15% of the field's range


@dataclass(frozen=True)
class DriverFitIntent:
    field: str
    delta: float
    from_value: float
    to_value: float
    target_fraction: float      # where in the range the driver wants this field
    gap: float                  # signed distance current->target (fraction of range)
    strength: float
    confidence: str
    reason: str
    drivers: tuple              # the profile flags that produced this

    def as_json(self) -> dict:
        return {"field": self.field, "delta": round(self.delta, 3),
                "from": self.from_value, "to": self.to_value,
                "target_fraction": round(self.target_fraction, 2),
                "gap": round(self.gap, 3), "strength": round(self.strength, 2),
                "confidence": self.confidence, "reason": self.reason,
                "drivers": list(self.drivers)}

    def as_change_dict(self) -> dict:
        """Shape mirrors setup_baseline._make_change_dict so a driver-fit move can flow
        through the SAME engineering validator / finaliser / renderer as any change."""
        return {
            "setting": self.field.replace("_", " ").title(),
            "field": self.field,
            "from": str(self.from_value),
            "to": str(self.to_value),
            "to_clamped": self.to_value,
            "delta": self.delta,
            "symptom": "driver fit",
            "evidence": list(self.drivers),
            "rule_id": "driver_fit",
            "rationale": self.reason,
            "why": self.reason,
            "rejected_alternatives": [],
            "risk_level": "low",
            "confidence_level": self.confidence,
            "driver_style_alignment": "aligned",
            "source_label": "tailored to your driving style",
            "session_influence": "",
            "car_drivetrain_influence": "",
            "pack": "driver_fit",
            "learning_influence": "",
            "fuel_influence": "",
        }


def _num(v) -> Optional[float]:
    try:
        f = float(v)
        return f if f == f and f not in (float("inf"), float("-inf")) else None
    except (TypeError, ValueError):
        return None


def _round(field: str, v: float) -> float:
    if field in ("toe_front", "toe_rear"):
        return round(v, 2)
    if field in ("aero_front", "aero_rear", "arb_front", "arb_rear", "brake_bias",
                 "lsd_accel", "lsd_decel"):
        return int(round(v))
    return round(v, 2)


def derive_driver_fit(profile, current_setup: dict, ranges: dict) -> list:
    """Return evidence-scaled driver-fit intents against ``current_setup``.

    For the from-scratch baseline pass ``current_setup`` = the neutral seeds (so the
    base is tailored to the driver from a neutral start); for the analyse path pass
    the real current setup. Empty when the profile is neutral or the car already fits.
    """
    setup = current_setup or {}
    ranges = ranges or {}
    if profile is None:
        return []

    # Accumulate per-field VIOLATION pressure: each active preference contributes only
    # when the current value is on the wrong side of its comfort threshold, scaled by
    # how far past it sits and by the preference strength. Opposing prefs net out.
    acc: dict[str, list] = {}   # field -> [signed_pressure, strength_of_firing, {flags}, thr_ref]
    for flag, (strength, fields) in _DRIVER_PREFS.items():
        if not getattr(profile, flag, False):
            continue
        for f, (direction, thr) in fields.items():
            if f not in ranges:
                continue
            lo, hi = ranges[f]
            if hi <= lo:
                continue
            cur = _num(setup.get(f))
            if cur is None:
                continue
            cur = max(lo, min(hi, cur))
            cur_frac = (cur - lo) / (hi - lo)
            # Overshoot = how far past the threshold on the wrong side (>0 fires).
            overshoot = (cur_frac - thr) if direction < 0 else (thr - cur_frac)
            if overshoot <= _DEADZONE:
                continue                              # already on the driver's side
            a = acc.setdefault(f, [0.0, 0.0, set(), thr])
            a[0] += direction * overshoot * strength  # signed pressure toward the driver
            a[1] += strength
            a[2].add(flag)

    out: list[DriverFitIntent] = []
    for f, (pressure, sw, flags, thr) in acc.items():
        if abs(pressure) < 1e-6:
            continue                                  # opposing prefs cancelled → in-band
        lo, hi = ranges[f]
        cur = max(lo, min(hi, _num(setup.get(f))))
        cur_frac = (cur - lo) / (hi - lo)
        move_frac = min(abs(pressure), _MAX_MOVE_FRAC)
        delta = math.copysign(move_frac * (hi - lo), pressure)
        to = _round(f, max(lo, min(hi, cur + delta)))
        if to == _round(f, cur):
            continue                                  # rounds to a no-op
        eff_strength = min(1.0, sw)
        conf = "high" if eff_strength >= 0.85 else "medium" if eff_strength >= 0.6 else "low"
        drivers = tuple(sorted(flags))
        why = " and ".join(_FLAG_REASON.get(fl, fl) for fl in drivers)
        reason = (f"{why} — the current {f.replace('_', ' ')} works against that, so move "
                  "it toward your window (scaled to how far off it is)")
        out.append(DriverFitIntent(
            field=f, delta=_round(f, delta), from_value=_round(f, cur), to_value=to,
            target_fraction=thr, gap=pressure, strength=eff_strength,
            confidence=conf, reason=reason, drivers=drivers))
    out.sort(key=lambda i: (-i.strength, i.field))
    return out


def driver_fit_bias(intents: list) -> dict:
    """field -> summed delta, ready to merge into a build_baseline_setup bias dict."""
    out: dict = {}
    for i in intents:
        out[i.field] = out.get(i.field, 0.0) + i.delta
    return out


def driver_fit_reasoning(profile, intents: list) -> dict:
    """A surface for the UI: what the driver profile changed, why, and how confidently."""
    tags = list(getattr(profile, "style_tags", []) or []) if profile is not None else []
    return {
        "style_tags": tags,
        "intents": [i.as_json() for i in intents],
        "note": ("Setup tailored to your stated style, scaled to how far the base sat "
                 "from your preferred window — fields already in your window are left "
                 "unchanged."),
    }
