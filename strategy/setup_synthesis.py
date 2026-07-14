"""Complete setup synthesis (pure, Qt-free) — Engineering-Brain Phase 3.

The plan's "major transformation from rule stack to engineering brain": instead of
correcting one symptom at a time, define the TARGET handling the car should have, then
generate several COMPLETE candidate setups, evaluate how each field's move interacts
with the handling targets (reason in systems, not isolated sliders), score the
candidates for the objective, and select the best — all values chosen from the
Phase-2 working windows (a range with evidence), with per-field provenance.

Layers implemented here:
  * Layer 2 — `TargetHandlingModel` + `build_target_handling_model` (driver × car ×
    track × objective × current diagnosis → the desired car behaviour).
  * Layer 3 — `PARAMETER_INTERACTIONS`: how raising each field moves each handling
    target (the coupled dependency graph).
  * Layer 5 — `generate_candidates`: several full-field candidates from different
    engineering lenses, each value selected within its working window.
  * Layer 7 — `score_candidate` + `synthesize_setup`: coupled scoring against the
    target (objective-weighted) + a coherence penalty, then select the best.

It authors no value outside the legal working windows and calls no AI. It is the
deterministic engineer that builds a whole car toward a goal.
"""
from __future__ import annotations

from dataclasses import dataclass, field as _dc_field
from typing import Optional


# ---------------------------------------------------------------------------
# Layer 2 — the handling targets (desired car behaviour). Each axis is a signed
# target in roughly [-1, +1]: + = "want more of this", - = "want less".
# ---------------------------------------------------------------------------
HANDLING_AXES = (
    "entry_rotation",           # rotate the car on the way in
    "apex_front_support",       # planted, supportive front at the apex
    "exit_traction",            # drive off the corner
    "power_oversteer_resistance",  # resist the rear stepping out on power
    "trail_braking_stability",  # stable rear under trail braking
    "high_speed_stability",     # calm at speed / quick direction change
    "kerb_compliance",          # ride the kerbs cleanly
    "tyre_preservation",        # protect the tyre over a stint
    "fuel_efficiency",          # low drag / fuel burn
    "consistency",              # low lap-time variance
)


@dataclass(frozen=True)
class TargetHandlingModel:
    objective: str
    targets: dict               # axis -> signed target
    drivers: list               # human-readable "why" lines

    def get(self, axis: str) -> float:
        return float(self.targets.get(axis, 0.0))

    def as_json(self) -> dict:
        return {"objective": self.objective,
                "targets": {k: round(v, 2) for k, v in self.targets.items()},
                "drivers": list(self.drivers)}


def _bump(t: dict, axis: str, delta: float) -> None:
    t[axis] = max(-1.0, min(1.0, t.get(axis, 0.0) + delta))


def build_target_handling_model(context) -> TargetHandlingModel:
    """Derive the desired car behaviour from the intersection of driver needs, car
    characteristics, track demands, the setup objective and any current feedback."""
    t: dict = {a: 0.0 for a in HANDLING_AXES}
    drivers: list[str] = []
    obj = str(getattr(context, "objective", "base")).lower()
    vehicle = getattr(context, "vehicle", None)
    track = getattr(context, "track_profile", None)
    corner = getattr(context, "corner_profile", None)
    driver = getattr(context, "driver", None)
    diag = getattr(context, "diagnosis", None) or {}
    flags = diag.get("driver_feel_flags", {}) or {}

    # ---- Vehicle nature ----
    bal = str(getattr(vehicle, "balance_tendency", "")) if vehicle else ""
    if bal == "entry_understeer_power_oversteer":       # rear-engined (RR)
        _bump(t, "apex_front_support", 0.5); _bump(t, "entry_rotation", 0.3)
        _bump(t, "power_oversteer_resistance", 0.5); _bump(t, "trail_braking_stability", 0.4)
        drivers.append("rear-engined car: needs front support on entry and a resisted, "
                       "planted rear on power/brakes")
    elif bal == "strong_understeer":                    # FF
        _bump(t, "entry_rotation", 0.5); _bump(t, "apex_front_support", 0.4)
        drivers.append("front-drive car: needs help rotating")
    if getattr(vehicle, "high_power_to_weight", False):
        _bump(t, "exit_traction", 0.3)
        drivers.append("high power-to-weight: traction matters")

    # ---- Track demands ----
    if track and getattr(track, "trustworthy", False):
        sf = getattr(track, "straight_fraction", None)
        cd = getattr(track, "corner_density_per_km", None)
        if sf is not None and sf >= 0.22:
            _bump(t, "high_speed_stability", 0.4); _bump(t, "fuel_efficiency", 0.2)
            drivers.append("straight-heavy circuit: high-speed stability and low drag")
        elif cd is not None and cd >= 6.0:
            _bump(t, "entry_rotation", 0.3); _bump(t, "exit_traction", 0.2)
            drivers.append("corner-dense circuit: rotation and drive off slow corners")
    if corner and getattr(corner, "kerb_heavy", False):
        _bump(t, "kerb_compliance", 0.5)
        drivers.append("kerb-heavy circuit: ride the kerbs")

    # ---- Driver preferences ----
    if getattr(driver, "prefers_front_bite", False):
        _bump(t, "apex_front_support", 0.4); _bump(t, "entry_rotation", 0.2)
    if getattr(driver, "prefers_rear_stability", False):
        _bump(t, "power_oversteer_resistance", 0.4); _bump(t, "high_speed_stability", 0.2)
    if getattr(driver, "trail_braker", False):
        _bump(t, "trail_braking_stability", 0.4)
    if getattr(driver, "dislikes_snap_exit", False):
        _bump(t, "power_oversteer_resistance", 0.3)
    if driver is not None and (getattr(driver, "prefers_front_bite", False)
                               or getattr(driver, "prefers_rear_stability", False)):
        drivers.append("driver style: front bite with a planted, no-snap rear")

    # ---- Current feedback (analyse path) ----
    if flags.get("mid_corner_understeer") or flags.get("entry_understeer") or flags.get("floaty_front"):
        _bump(t, "apex_front_support", 0.5); _bump(t, "entry_rotation", 0.3)
    if flags.get("rear_loose_on_exit") or flags.get("snap_oversteer_exit"):
        _bump(t, "power_oversteer_resistance", 0.5)
    if flags.get("rear_loose_under_braking") or flags.get("braking_instability"):
        _bump(t, "trail_braking_stability", 0.5)

    # ---- Objective shaping ----
    if obj == "qualifying":
        _bump(t, "entry_rotation", 0.4); _bump(t, "apex_front_support", 0.3)
        _bump(t, "tyre_preservation", -0.5); _bump(t, "fuel_efficiency", -0.3)
        _bump(t, "consistency", -0.3)
        drivers.append("qualifying: peak one-lap grip and rotation; tyre/fuel ignored")
    elif obj == "race":
        _bump(t, "tyre_preservation", 0.5); _bump(t, "fuel_efficiency", 0.3)
        _bump(t, "consistency", 0.5); _bump(t, "exit_traction", 0.3)
        _bump(t, "power_oversteer_resistance", 0.2)
        drivers.append("race: minimise total race time — traction, tyre life, consistency")
    else:
        drivers.append("base: balanced platform to learn from")

    return TargetHandlingModel(obj, t, drivers)


# ---------------------------------------------------------------------------
# Layer 3 — parameter interaction graph. For each field, the effect of RAISING it on
# each handling axis (+1 helps, -1 hurts). Direction-only; magnitudes are equal weight.
# Sign conventions match the rest of the engine (arb higher=stiffer=less grip; aero
# higher=more grip; toe_rear higher=toe-in/stability; brake_bias higher=rearward;
# lsd_accel higher=more accel lock; ride height higher=more clearance).
# ---------------------------------------------------------------------------
PARAMETER_INTERACTIONS: dict = {
    "arb_front": {"entry_rotation": -1, "apex_front_support": -1, "high_speed_stability": +1},
    "arb_rear": {"entry_rotation": +1, "power_oversteer_resistance": -1, "exit_traction": -1,
                 "high_speed_stability": +1},
    "aero_front": {"apex_front_support": +1, "entry_rotation": +1, "high_speed_stability": +1,
                   "fuel_efficiency": -1},
    "aero_rear": {"exit_traction": +1, "power_oversteer_resistance": +1,
                  "high_speed_stability": +1, "fuel_efficiency": -1},
    "toe_front": {"entry_rotation": -1, "apex_front_support": +1, "tyre_preservation": -1},
    "toe_rear": {"power_oversteer_resistance": +1, "high_speed_stability": +1,
                 "exit_traction": -1, "tyre_preservation": -1},
    "lsd_accel": {"exit_traction": +1, "power_oversteer_resistance": -1},
    "lsd_decel": {"trail_braking_stability": +1, "entry_rotation": -1},
    "lsd_initial": {"apex_front_support": +1, "exit_traction": +1, "entry_rotation": -1},
    "brake_bias": {"entry_rotation": +1, "trail_braking_stability": -1},   # raise = rearward
    "ride_height_front": {"kerb_compliance": +1, "apex_front_support": -1},
    "ride_height_rear": {"kerb_compliance": +1, "high_speed_stability": -1},
    "springs_front": {"kerb_compliance": -1, "apex_front_support": +1},
    "springs_rear": {"kerb_compliance": -1, "exit_traction": +1},
    "camber_front": {"apex_front_support": +1, "tyre_preservation": -1, "high_speed_stability": -1},
    "camber_rear": {"exit_traction": +1, "power_oversteer_resistance": +1, "tyre_preservation": -1},
    "aero_front_ratio": {},
}


# ---------------------------------------------------------------------------
# Layer 5 — candidate generation. Each candidate selects, per field, a value within
# its working window in the direction that best serves the target model, under a lens.
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class SetupCandidate:
    lens: str
    values: dict                # field -> value (within its working window)
    provenance: dict            # field -> short source string
    score: float = 0.0
    score_breakdown: dict = _dc_field(default_factory=dict)

    def as_json(self) -> dict:
        return {"lens": self.lens, "values": dict(self.values),
                "provenance": dict(self.provenance),
                "score": round(self.score, 3),
                "score_breakdown": {k: round(v, 3) for k, v in self.score_breakdown.items()}}


# Lens = (name, target_weight, history_pull). target_weight scales how far a field moves
# toward the target-desired direction; history_pull biases toward the proven value.
_LENSES = (
    ("balance",          1.0, 0.3),   # follow the target model, respect proven windows
    ("driver_history",   0.6, 0.8),   # start near what worked for this driver
    ("aggressive",       1.3, 0.1),   # push toward the target harder (quali-attack)
)


def _field_desired_direction(field: str, target: TargetHandlingModel) -> float:
    """Net signed direction (raise>0 / lower<0) this field should move to serve the
    target model, from the interaction graph."""
    inter = PARAMETER_INTERACTIONS.get(field, {})
    return sum(sign * target.get(axis) for axis, sign in inter.items())


import math as _math


def _round(field: str, v: float) -> float:
    if field in ("toe_front", "toe_rear"):
        return round(v, 2)
    if field in ("springs_front", "springs_rear", "camber_front", "camber_rear"):
        return round(v, 1)
    if field.startswith("gear_") or field == "final_drive":
        return round(v, 3)
    return int(round(v))


def _place_in_window(field: str, v: float, lo: float, hi: float) -> float:
    """Round to the field's natural precision but guarantee the result stays inside the
    legal window [lo, hi] (rounding an int field can otherwise escape a fractional bound)."""
    r = _round(field, max(lo, min(hi, v)))
    if r > hi:
        r = _round(field, _math.floor(hi) if isinstance(r, int) else hi)
        r = max(lo, min(hi, r))
    if r < lo:
        r = _round(field, _math.ceil(lo) if isinstance(r, int) else lo)
        r = max(lo, min(hi, r))
    return r


def generate_candidates(context, target: TargetHandlingModel) -> list:
    """Build a full-field candidate per lens. Every field with a working window gets a
    value chosen within that window toward the target-desired direction (or the proven
    value for the history lens)."""
    windows = getattr(context, "working_windows", {}) or {}
    out: list[SetupCandidate] = []
    for lens, tw, hp in _LENSES:
        values: dict = {}
        prov: dict = {}
        for field, w in windows.items():
            lo, hi = float(w.low), float(w.high)
            if hi <= lo:
                values[field] = _place_in_window(field, lo, lo, hi)
                prov[field] = "locked" if getattr(w, "locked", False) else "fixed"
                continue
            centre = w.preferred if w.preferred is not None else (lo + hi) / 2.0
            direction = _field_desired_direction(field, target)
            half = (hi - lo) / 2.0
            # Move from the centre toward the target-desired direction, scaled by lens.
            step = max(-1.0, min(1.0, direction)) * tw * half
            # History pull keeps a proven field near its proven value.
            if w.preferred is not None:
                target_val = centre + step * (1.0 - hp)
            else:
                target_val = centre + step
            val = _place_in_window(field, target_val, lo, hi)
            values[field] = val
            if w.preferred is not None and abs(val - w.preferred) < (hi - lo) * 0.05:
                prov[field] = f"proven {w.preferred:g}"
            elif abs(direction) > 0.05:
                prov[field] = ("raised for " if direction > 0 else "lowered for ") + \
                    ",".join(a for a in PARAMETER_INTERACTIONS.get(field, {})
                             if abs(target.get(a)) > 0.05)[:40]
            else:
                prov[field] = "window centre"
        out.append(SetupCandidate(lens, values, prov))
    return out


# ---------------------------------------------------------------------------
# Layer 7 — scoring + selection. Predict a candidate's handling from its field values
# (relative to each window's centre) and score how well it matches the target, weighted
# by the objective, minus a coherence penalty for fighting itself.
# ---------------------------------------------------------------------------
# Objective weights emphasise the axes that matter for that discipline.
_OBJECTIVE_WEIGHTS = {
    "qualifying": {"entry_rotation": 1.4, "apex_front_support": 1.4, "exit_traction": 1.1,
                   "tyre_preservation": 0.2, "fuel_efficiency": 0.2, "consistency": 0.3,
                   "high_speed_stability": 1.0},
    "race": {"tyre_preservation": 1.4, "consistency": 1.4, "exit_traction": 1.3,
             "power_oversteer_resistance": 1.2, "fuel_efficiency": 1.1,
             "trail_braking_stability": 1.1, "high_speed_stability": 1.0},
    "base": {a: 1.0 for a in HANDLING_AXES},
}


def _predicted_handling(candidate: SetupCandidate, context) -> dict:
    """Estimate the candidate's handling as the sum of each field's deviation-from-centre
    times its interaction effects (normalised to roughly [-1,1] per axis)."""
    windows = getattr(context, "working_windows", {}) or {}
    pred: dict = {a: 0.0 for a in HANDLING_AXES}
    for field, val in candidate.values.items():
        w = windows.get(field)
        if w is None or w.high <= w.low:
            continue
        centre = w.preferred if w.preferred is not None else (w.low + w.high) / 2.0
        norm = (float(val) - centre) / ((w.high - w.low) / 2.0)   # -1..+1
        for axis, sign in PARAMETER_INTERACTIONS.get(field, {}).items():
            pred[axis] = pred.get(axis, 0.0) + sign * norm
    # squash
    return {a: max(-1.0, min(1.0, v)) for a, v in pred.items()}


def score_candidate(candidate: SetupCandidate, target: TargetHandlingModel, context) -> SetupCandidate:
    """Objective-weighted match between predicted and target handling, minus a coherence
    penalty. Returns a copy of the candidate with score + breakdown filled in."""
    pred = _predicted_handling(candidate, context)
    weights = _OBJECTIVE_WEIGHTS.get(target.objective, _OBJECTIVE_WEIGHTS["base"])
    match = 0.0
    breakdown: dict = {}
    for axis in HANDLING_AXES:
        tgt = target.get(axis)
        w = weights.get(axis, 1.0)
        # Reward moving the axis toward the target; penalise moving it away.
        contrib = w * (pred[axis] * tgt)
        match += contrib
        if abs(tgt) > 0.05:
            breakdown[axis] = contrib
    # Coherence penalty: a candidate that pushes an axis hard the WRONG way vs a strong
    # target is internally fighting itself.
    penalty = sum(1.0 for axis in HANDLING_AXES
                  if target.get(axis) > 0.3 and pred[axis] < -0.3
                  or target.get(axis) < -0.3 and pred[axis] > 0.3)
    total = match - 0.5 * penalty
    breakdown["_coherence_penalty"] = -0.5 * penalty
    return SetupCandidate(candidate.lens, candidate.values, candidate.provenance,
                          score=total, score_breakdown=breakdown)


@dataclass(frozen=True)
class SynthesisResult:
    objective: str
    target: TargetHandlingModel
    best: Optional[SetupCandidate]
    candidates: list
    confidence: str

    def as_json(self) -> dict:
        return {
            "objective": self.objective,
            "target_handling": self.target.as_json(),
            "best": self.best.as_json() if self.best else None,
            "candidates": [c.as_json() for c in self.candidates],
            "confidence": self.confidence,
        }


# ---------------------------------------------------------------------------
# Synthesis-as-primary reconciliation. The complete-setup synthesis becomes the
# PRIMARY author for the handling fields it reasons about — but only where the
# evidence supports it (confidence-gated), and never over a proven personal value.
# ---------------------------------------------------------------------------
# The handling domain synthesis reasons about (its interaction-graph fields). It does
# NOT author gearing / tyres / ECU / ballast — those stay with the baseline generator.
SYNTHESIS_PRIMARY_FIELDS = frozenset({
    "arb_front", "arb_rear", "aero_front", "aero_rear",
    "toe_front", "toe_rear", "lsd_accel", "lsd_decel", "lsd_initial",
    "brake_bias", "ride_height_front", "ride_height_rear",
    "springs_front", "springs_rear", "camber_front", "camber_rear",
})
_STRONG_CONFIDENCE = frozenset({"high", "medium"})
# A from-scratch baseline is a starting point, not a max-attack setup. When synthesis
# authors a NON-proven field (full-range window), temper its move toward the target to
# this fraction of the distance from the window centre — keeps the directional intent
# without slamming a legal-but-edgy range extreme onto the driver.
_PRIMARY_MODERATION = 0.6


def _num_eq(a, b, tol: float = 1e-6) -> bool:
    try:
        return abs(float(a) - float(b)) <= tol
    except (TypeError, ValueError):
        return a == b


def reconcile_synthesis_primary(baseline_setup_fields: dict, synthesis_result,
                                context, fields=SYNTHESIS_PRIMARY_FIELDS) -> dict:
    """Confidence-gated merge that makes synthesis the PRIMARY author for the handling
    fields where the evidence supports it.

    A field is authored by synthesis only when ALL hold:
      * it is in the handling domain (``fields``) and the best candidate assigned a value;
      * its working window is present and not event-locked;
      * it carries NO proven personal value (``preferred``) — a proven value already IS
        the strongest evidence and stays primary (synthesis never overrides it);
      * the track model's ``setup_shaping`` confidence is high/medium (the evidence that
        makes synthesis's track-coupled value trustworthy for a non-proven field);
      * synthesis actually took a directional view (moved the field off the neutral
        window centre), and that value differs from the baseline's.

    Pure and Qt-free — proposes only values synthesis already chose inside the legal
    working window. Returns ``{overrides, provenance, applied, skipped, kept_proven,
    reason}``; the caller feeds the overrides through the SAME validation + Apply gate.
    """
    out = {"overrides": {}, "provenance": {}, "applied": [], "skipped": [],
           "kept_proven": [], "reason": ""}
    best = getattr(synthesis_result, "best", None)
    if best is None or not getattr(best, "values", None):
        out["reason"] = "no synthesis candidate"
        return out
    tconf = getattr(context, "track_confidence", {}) or {}
    shaping = str(tconf.get("setup_shaping", "none")).lower()
    if shaping not in _STRONG_CONFIDENCE:
        out["reason"] = (f"track shaping confidence '{shaping}' is too low for "
                         "synthesis-primary — baseline authoring stands")
        return out
    windows = getattr(context, "working_windows", {}) or {}
    base = baseline_setup_fields or {}
    for f in fields:
        if f not in best.values:
            continue
        w = windows.get(f)
        if w is None or getattr(w, "locked", False):
            out["skipped"].append(f)
            continue
        if getattr(w, "preferred", None) is not None:
            out["kept_proven"].append(f)        # proven anchor — never overridden
            continue
        lo, hi = float(w.low), float(w.high)
        if hi <= lo:
            out["skipped"].append(f)
            continue
        sv = best.values[f]
        centre = (lo + hi) / 2.0
        if abs(float(sv) - centre) < (hi - lo) * 0.05:
            out["skipped"].append(f)            # no directional view — leave baseline
            continue
        # Temper the move toward the target so a from-scratch baseline never ships a
        # range extreme; keeps the direction, drops the aggression.
        val = _place_in_window(f, centre + (float(sv) - centre) * _PRIMARY_MODERATION,
                               lo, hi)
        if _num_eq(base.get(f), val):
            continue                            # already equal — nothing to change
        out["overrides"][f] = val
        out["provenance"][f] = best.provenance.get(f, "synthesis")
        out["applied"].append(f)
    out["reason"] = (
        f"synthesis authored {len(out['applied'])} handling field(s) as primary "
        f"(track shaping {shaping}); {len(out['kept_proven'])} proven value(s) kept"
        if out["applied"] else
        "no non-proven handling field met the synthesis-primary evidence bar")
    return out


def synthesize_setup(context) -> SynthesisResult:
    """Build the target handling model, generate scored full-field candidates, and select
    the best for the objective — the complete-setup-synthesis path."""
    target = build_target_handling_model(context)
    cands = [score_candidate(c, target, context)
             for c in generate_candidates(context, target)]
    cands.sort(key=lambda c: c.score, reverse=True)
    best = cands[0] if cands else None
    # Confidence tracks the evidence behind the windows + track model.
    tc = getattr(context, "track_confidence", {}) or {}
    has_hist = bool(getattr(context, "history_prior", {}))
    if tc.get("setup_shaping") in ("high", "medium") and has_hist:
        conf = "medium"
    elif has_hist or tc.get("setup_shaping") in ("high", "medium"):
        conf = "low"
    else:
        conf = "low"
    return SynthesisResult(target.objective, target, best, cands, conf)
