"""Cross-field physics invariants (pure, Qt-free) — UAT 2026-08-07 defect A1.

Per-field reasoning cannot see relationships BETWEEN fields. The synthesis interaction
graph scores each slider against handling axes independently, so nothing stopped it
authoring more camber on the rear axle than the front — the exact inversion the UAT
found on a Gr.3, and the opposite of every vetted setup in ``data/proven_setups.json``.

This module holds the small set of relationships that are true of essentially every
setup a competent engineer signs off, and repairs a violation by moving the field with
the WEAKER provenance. A proven value is never moved to satisfy an invariant: if the
driver has actually validated a setup on track, the invariant is what is wrong, not
the setup, and the violation is reported rather than silently corrected.

This is deliberately a short list. It is not a setup engine and it must not become
one — anything that needs car-specific data belongs in the car model, and anything
that needs telemetry belongs in the rule engine. An invariant earns its place here
only if violating it is obviously wrong for any car, at any track, in any discipline.

Pure: no Qt, no DB, no network, no AI, no wall-clock, no randomness. Never raises.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from strategy.setup_anchor import (
    TIER_ARCHETYPE, TIER_GENERIC, TIER_OWNER_AUTHORED,
    TIER_PROVEN, TIER_STOCK, TIER_TRANSFERRED,
)

#: Provenance strength, strongest first. Only used to decide which side of a violated
#: relationship gives way. OWNER_AUTHORED is the strongest tier: a value entered
#: directly by the driver (from external preparation) must never be moved to satisfy
#: an invariant — the invariant is reported as a violation instead.
_TIER_STRENGTH = {
    TIER_OWNER_AUTHORED: 6,
    TIER_PROVEN: 5, TIER_TRANSFERRED: 4, "ENGINEERED": 3,
    TIER_STOCK: 3, TIER_ARCHETYPE: 2, TIER_GENERIC: 1, "": 0,
}


@dataclass(frozen=True)
class InvariantResult:
    """What the invariant pass changed, and what it could not."""
    fields: dict                 # the repaired setup values
    corrections: tuple           # human-readable "I moved X because Y"
    violations: tuple            # violations left in place (a proven value blocked it)

    @property
    def changed(self) -> bool:
        return bool(self.corrections)

    def as_json(self) -> dict:
        return {"corrections": list(self.corrections),
                "violations": list(self.violations)}


def _num(v) -> Optional[float]:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f == f and f not in (float("inf"), float("-inf")) else None


def _strength(tier: str) -> int:
    return _TIER_STRENGTH.get(str(tier or "").upper(), 0)


def _clamp_to_window(field: str, value: float, context) -> float:
    """Keep a repaired value inside the field's legal range."""
    w = None
    try:
        w = (getattr(context, "working_windows", {}) or {}).get(field)
    except Exception:
        w = None
    if w is None:
        return value
    try:
        return max(float(w.low), min(float(w.high), value))
    except (TypeError, ValueError, AttributeError):
        return value


def _tier_of(field: str, context) -> str:
    try:
        anchors = getattr(context, "anchor_set", None)
        if anchors is not None:
            return anchors.tier(field)
    except Exception:
        pass
    try:
        w = (getattr(context, "working_windows", {}) or {}).get(field)
        if w is not None and getattr(w, "preferred", None) is not None:
            return TIER_PROVEN
        return str(getattr(w, "anchor_tier", "") or "")
    except Exception:
        return ""


def _order_pair(fields: dict, high_field: str, low_field: str, context,
                reason: str, corrections: list, violations: list,
                min_gap: float = 0.0) -> None:
    """Enforce ``fields[high_field] >= fields[low_field] + min_gap``.

    The weaker-provenance side moves. When both sides are proven, nothing moves and the
    violation is reported — a validated setup outranks a general rule.
    """
    hi_v, lo_v = _num(fields.get(high_field)), _num(fields.get(low_field))
    if hi_v is None or lo_v is None:
        return
    if hi_v >= lo_v + min_gap:
        return

    hi_t, lo_t = _tier_of(high_field, context), _tier_of(low_field, context)
    hi_s, lo_s = _strength(hi_t), _strength(lo_t)

    if hi_s >= _TIER_STRENGTH[TIER_PROVEN] and lo_s >= _TIER_STRENGTH[TIER_PROVEN]:
        violations.append(
            f"{high_field} ({hi_v:g}) is below {low_field} ({lo_v:g}) — {reason}. "
            f"Both values are proven, so neither was changed. Worth a look.")
        return

    if lo_s > hi_s:                       # the LOW field is better evidenced — raise HIGH
        new = _clamp_to_window(high_field, lo_v + min_gap, context)
        if new != hi_v:
            fields[high_field] = new
            corrections.append(
                f"Raised {high_field} to {new:g} to keep it at or above "
                f"{low_field} ({lo_v:g}) — {reason}.")
            return
    new = _clamp_to_window(low_field, hi_v - min_gap, context)
    if new != lo_v:
        fields[low_field] = new
        corrections.append(
            f"Lowered {low_field} to {new:g} to keep it at or below "
            f"{high_field} ({hi_v:g}) — {reason}.")
        return
    violations.append(
        f"{high_field} ({hi_v:g}) is below {low_field} ({lo_v:g}) — {reason}. "
        f"The legal range left no room to correct it.")


def enforce_invariants(fields: dict, context=None) -> InvariantResult:
    """Repair cross-field violations in a setup. Never raises.

    ``fields`` is not mutated; a repaired copy is returned.
    """
    out = dict(fields or {})
    corrections: list = []
    violations: list = []

    # 1. Camber: the front axle carries at least as much as the rear. Every vetted
    #    setup in the proven library runs 2.4-2.8 front against 1.8-2.2 rear. Rear
    #    camber above front makes the car turn in on the rear axle, which is the
    #    inversion the UAT found (1.4 front / 4.8 rear on a Gr.3).
    _order_pair(out, "camber_front", "camber_rear", context,
                "the front axle needs at least as much camber as the rear",
                corrections, violations)

    # 2. Rake: the rear rides at or above the front on any car generating downforce.
    #    Nose-down rake seals the floor; nose-up is aerodynamically backwards. Applied
    #    only when there is rear downforce to speak of, so it does not fire on a road
    #    car with no wing.
    if (_num(out.get("aero_rear")) or 0) > 0:
        _order_pair(out, "ride_height_rear", "ride_height_front", context,
                    "the car needs rake — the rear rides above the front",
                    corrections, violations)

    # 3. Aero balance: rear downforce at or above front. A front-biased wing map makes
    #    the car unstable at speed on every layout in the game. True of all six vetted
    #    setups and all six class archetypes.
    _order_pair(out, "aero_rear", "aero_front", context,
                "rear downforce must not sit below front downforce",
                corrections, violations)

    return InvariantResult(fields=out, corrections=tuple(corrections),
                           violations=tuple(violations))
