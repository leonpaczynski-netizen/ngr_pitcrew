"""Phase 10 — cross-symptom arbitration over the proposed set (pure, Qt-free).

The rule engine resolves same-FIELD contests (setup_rule_engine conflict machinery
records the beaten rule in each winner's rejected_alternatives). This module handles
the orthogonal question: given the FINAL proposed set, do several changes push the
same balance axis together (compounding — overshoot risk) or against each other
(partially offsetting — the net effect is smaller than any single change looks)?

It reasons ONLY over the changes actually proposed, using a small table of
well-established, monotonic balance directions (front/rear aero + ARB). It invents
no magnitudes and touches nothing outside that table — fields it doesn't understand
are simply ignored. It authors NO setup values and applies nothing.
"""
from __future__ import annotations

from dataclasses import dataclass, field as _dc_field
from typing import Optional

# Effect of RAISING a field on oversteer tendency (+1 = looser/more rotation,
# -1 = more stable/understeer). Classic, direction-only relationships; magnitudes
# are deliberately NOT modelled.
_OVERSTEER_EFFECT = {
    "aero_front": +1,   # more front grip -> more rotation
    "aero_rear": -1,    # more rear grip  -> more stable
    "arb_front": -1,    # stiffer front   -> less front grip -> understeer
    "arb_rear": +1,     # stiffer rear    -> less rear grip  -> oversteer
}
_AXIS_LABEL = "front/rear balance"


@dataclass(frozen=True)
class ArbitrationResult:
    """Interaction analysis over the proposed set. ``notes`` is human-readable;
    ``compounding`` is True when ≥2 changes push the same balance direction."""
    compounding: bool
    offsetting: bool
    net_direction: str            # "looser" | "more stable" | "neutral"
    contributors: list            # list[str] field names that touch the axis
    notes: list = _dc_field(default_factory=list)

    def as_note(self) -> str:
        return " ".join(self.notes) if self.notes else ""


def _signed_effect(change: dict) -> Optional[int]:
    """+1/-1 = this change's push on oversteer tendency, or None if off-axis/no-op."""
    field = change.get("field")
    base = _OVERSTEER_EFFECT.get(field)
    if base is None:
        return None
    try:
        delta = float(change.get("delta", 0) or 0)
    except (TypeError, ValueError):
        return None
    if delta == 0:
        return None
    return base if delta > 0 else -base


def analyse_change_interactions(proposed: "list[dict]") -> ArbitrationResult:
    """Assess how the proposed changes combine on the front/rear balance axis.

    Compounding (≥2 changes the same direction) → an overshoot-caution note so the
    driver applies them incrementally. Offsetting (both directions present) → a note
    that the net balance move is smaller than any single change reads. Off-axis
    changes are ignored. Never fabricates a magnitude."""
    contributors, pluses, minuses = [], 0, 0
    for ch in proposed or []:
        eff = _signed_effect(ch)
        if eff is None:
            continue
        contributors.append(ch.get("field"))
        if eff > 0:
            pluses += 1
        else:
            minuses += 1

    total = pluses + minuses
    if total == 0:
        return ArbitrationResult(False, False, "neutral", [], [])

    net = pluses - minuses
    net_dir = "looser" if net > 0 else "more stable" if net < 0 else "neutral"
    compounding = (pluses >= 2 or minuses >= 2) and not (pluses and minuses)
    offsetting = pluses >= 1 and minuses >= 1

    notes = []
    if compounding:
        notes.append(
            f"Balance note: {len(contributors)} changes "
            f"({', '.join(contributors)}) all push the {_AXIS_LABEL} the same way "
            f"({net_dir}) — apply them one at a time and re-check, as together they "
            "can overshoot."
        )
    elif offsetting:
        notes.append(
            f"Balance note: these changes ({', '.join(contributors)}) act on the "
            f"{_AXIS_LABEL} in opposite directions, so the net move is "
            + (f"{net_dir}" if net else "roughly neutral")
            + " — smaller than any single change looks in isolation."
        )
    return ArbitrationResult(compounding, offsetting, net_dir, contributors, notes)
