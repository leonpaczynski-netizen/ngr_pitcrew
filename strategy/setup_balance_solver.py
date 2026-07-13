"""Multi-complaint balance solver (pure, Qt-free) — author instead of defer.

The audit (docs/AUDIT_setup_brain_engineer_evolution.md, Gap 6) found that when a
driver reports SEVERAL conflicting handling problems (e.g. entry understeer + mid
push + rear loose on power + rear locks under braking), the single-field rule engine
evaluates each in isolation, the per-field safety contraindications empty the
proposed set, and the coherence gate returns ``evidence_required`` with NO setup.

A real engineer does not ask for more evidence there — that is a coherent *balance*
problem. This module solves the whole car at once: it frees the front so it turns in,
plants the rear so it drives off the corner, moves the brake bias forward so the rear
stops locking, and refuses to add the moves that would make it worse — producing a
coordinated, conservative, safety-respecting compromise to VALIDATE on track.

Authority + safety (unchanged):
  * DETERMINISTIC and rule-first — this is an engineer's reasoning, not AI. The AI
    audit stays advisory-only.
  * It PROPOSES; the existing ``validate_setup_engineering_structured`` funnel + Apply
    gate still DISPOSE. Every move is one conservative step, range-clamped downstream.
  * It never violates a safety invariant it knows about: brake bias only moves FORWARD
    (never rearward) under braking instability; LSD acceleration lock is never
    INCREASED when the rear is loose on power. Ambiguous levers (LSD braking) are left
    to a targeted test rather than moved in a guessed direction.
  * It is honestly framed as a *coordinated balance change to test*, not a certainty.
"""
from __future__ import annotations

from dataclasses import dataclass, field as _dc_field
from typing import Optional


# Sign conventions (verified against strategy/setup_baseline._PROFILE_BIAS_TABLE and
# the safety validator):
#   arb_*      higher = stiffer = LESS grip on that axle
#   aero_*     higher = more downforce = MORE grip on that axle
#   toe_front  lower/more-negative = toe-OUT = sharper turn-in (front bite)
#   toe_rear   higher/more-positive = toe-IN = rear stability
#   brake_bias lower = more FORWARD (front); higher = rearward
#   lsd_accel  higher = more accel lock (can worsen power oversteer on a driven rear)

# One conservative "engineering step" per field. The solver only ever moves a field
# by a single step; the per-car range clamp bounds the result.
_STEP: dict[str, float] = {
    "arb_front": 1.0, "arb_rear": 1.0,
    "aero_front": 30.0, "aero_rear": 30.0,
    "toe_front": 0.03, "toe_rear": 0.05,
    "brake_bias": 1.0,
    "lsd_accel": 2.0,
}

# Handling complaints the solver understands, grouped by balance axis.
_UNDERSTEER = ("entry_understeer", "mid_corner_understeer", "floaty_front")
_POWER_OVERSTEER = ("rear_loose_on_exit", "snap_oversteer_exit")
_BRAKING = ("rear_loose_under_braking", "braking_instability")


@dataclass(frozen=True)
class BalanceMove:
    field: str
    direction: int             # -1 / +1
    delta: float               # signed step (range-clamped downstream)
    from_value: Optional[float]
    to_value: Optional[float]
    reason: str                # engineer's why
    addresses: tuple           # complaint keys this move treats
    axis: str                  # entry / exit / braking

    def as_change_dict(self) -> dict:
        """Shape mirrors strategy.setup_baseline._make_change_dict so the balance set
        can flow through the SAME validator/finaliser/renderer as any other change."""
        return {
            "setting": self.field.replace("_", " ").title(),
            "field": self.field,
            "from": "" if self.from_value is None else str(self.from_value),
            "to": str(self.to_value),
            "to_clamped": self.to_value,
            "delta": self.delta,
            "symptom": ", ".join(self.addresses),
            "evidence": list(self.addresses),
            "rule_id": "balance_solver",
            "rationale": self.reason,
            "why": self.reason,
            "rejected_alternatives": [],
            "risk_level": "medium",
            "confidence_level": "medium",
            "driver_style_alignment": "aligned",
            "source_label": "coordinated balance change",
            "session_influence": "",
            "car_drivetrain_influence": "",
            "pack": "balance",
            "learning_influence": "",
            "fuel_influence": "",
        }


@dataclass(frozen=True)
class BalanceSolution:
    solved: bool
    complaints: tuple                 # the confirmed complaints the solver addressed
    moves: list                       # list[BalanceMove]
    tradeoffs: list                   # human-readable trade-off notes
    targeted_tests: list              # levers left to a controlled test (ambiguous)
    summary: str
    test_protocol: str

    def as_change_dicts(self) -> list:
        return [m.as_change_dict() for m in self.moves]

    def setup_fields(self) -> dict:
        return {m.field: m.to_value for m in self.moves if m.to_value is not None}

    def as_json(self) -> dict:
        return {
            "solved": self.solved,
            "complaints": list(self.complaints),
            "moves": [
                {"field": m.field, "delta": m.delta, "from": m.from_value,
                 "to": m.to_value, "reason": m.reason, "addresses": list(m.addresses),
                 "axis": m.axis}
                for m in self.moves
            ],
            "tradeoffs": list(self.tradeoffs),
            "targeted_tests": list(self.targeted_tests),
            "summary": self.summary,
            "test_protocol": self.test_protocol,
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
                 "lsd_accel"):
        return int(round(v))
    return round(v, 2)


def confirmed_handling_complaints(diagnosis: dict) -> list:
    """The handling complaints (driver-confirmed, plus severe telemetry wheelspin) the
    solver treats. Fuel and 'entry balance good' are excluded."""
    flags = (diagnosis or {}).get("driver_feel_flags", {}) or {}
    out = [f for f in (_UNDERSTEER + _POWER_OVERSTEER + _BRAKING) if flags.get(f)]
    ws = str((diagnosis or {}).get("wheelspin_band", "low"))
    if ws in ("major", "severe") and "rear_loose_on_exit" not in out \
            and "snap_oversteer_exit" not in out:
        out.append("wheelspin")   # severe traction loss → treat like a rear-grip problem
    return out


def solve_balance(
    diagnosis: dict,
    current_setup: dict,
    ranges: dict,
    *,
    locked_fields=None,
    min_complaints: int = 2,
) -> BalanceSolution:
    """Author a coordinated, safety-respecting balance compromise from the confirmed
    complaint set. Requires at least ``min_complaints`` confirmed handling problems
    (a single problem is the rule engine's job). Returns ``solved=False`` when there is
    nothing coherent to solve.
    """
    flags = (diagnosis or {}).get("driver_feel_flags", {}) or {}
    ws_band = str((diagnosis or {}).get("wheelspin_band", "low"))
    setup = current_setup or {}
    locked = {f for f in (locked_fields or ())}

    complaints = confirmed_handling_complaints(diagnosis)
    understeer = any(flags.get(f) for f in _UNDERSTEER)
    power_os = any(flags.get(f) for f in _POWER_OVERSTEER) or ws_band in ("major", "severe")
    braking = any(flags.get(f) for f in _BRAKING)

    if len(complaints) < min_complaints:
        return BalanceSolution(False, tuple(complaints), [], [], [],
                               "Not a multi-complaint balance problem — the single-issue "
                               "rule engine handles this.", "")

    moves: list[BalanceMove] = []
    tradeoffs: list[str] = []
    tests: list[str] = []

    def _emit(field: str, direction: int, reason: str, addresses: tuple, axis: str):
        if field in locked:
            tests.append(f"{field.replace('_', ' ')} is locked by event rules — cannot "
                         f"be used to {('free' if direction < 0 else 'add')} grip here")
            return
        step = _STEP.get(field)
        if step is None:
            return
        cur = _num(setup.get(field))
        delta = direction * step
        to = _round(field, (cur if cur is not None else 0.0) + delta)
        # If the field is at/над the relevant range edge, note it and skip a no-op.
        if field in ranges and cur is not None:
            lo, hi = ranges[field]
            to = _round(field, max(lo, min(hi, cur + delta)))
            if to == _round(field, cur):
                tests.append(f"{field.replace('_', ' ')} is already at its useful limit — "
                             "cannot move further in the needed direction")
                return
        moves.append(BalanceMove(field, direction, _round(field, delta),
                                 cur, to, reason, addresses, axis))

    # ---- ENTRY / MID understeer: FREE THE FRONT (never at the rear's expense) ----
    if understeer:
        us = tuple(f for f in _UNDERSTEER if flags.get(f))
        _emit("arb_front", -1,
              "car won't turn in — soften the front bar to free the front and cure the "
              "understeer", us, "entry")
        _emit("toe_front", -1,
              "add a little front toe-out for sharper, more immediate turn-in", us, "entry")
        _emit("aero_front", +1,
              "more front downforce plants the nose through the mid-corner push", us, "entry")

    # ---- CORNER EXIT power oversteer: PLANT THE REAR (grip, not accel lock) ----
    if power_os:
        po = tuple(f for f in _POWER_OVERSTEER if flags.get(f)) or ("wheelspin",)
        _emit("aero_rear", +1,
              "rear steps out under power — more rear downforce for exit traction", po, "exit")
        _emit("toe_rear", +1,
              "add rear toe-in so the rear is planted on corner exit and in a straight line",
              po, "exit")
        _emit("arb_rear", -1,
              "soften the rear bar for mechanical rear grip on power (rotate the car with "
              "the freed FRONT, not a stiff rear)", po, "exit")
        # SAFETY: never add accel lock when the rear is already loose on power.
        tests.append("LSD Acceleration: do NOT add lock (it would worsen power oversteer) — "
                     "test a small REDUCTION only if traction is still poor after the aero/toe "
                     "change")

    # ---- BRAKING instability: STABLE STOP (brake bias forward, never rearward) ----
    if braking:
        br = tuple(f for f in _BRAKING if flags.get(f))
        _emit("brake_bias", -1,
              "rear locks/steps out under braking — move brake bias FORWARD for a stable, "
              "repeatable stop (never rearward during instability)", br, "braking")
        tests.append("LSD Braking Sensitivity: confirm straight-line vs trail-braking lock "
                     "over 3 laps before changing coast lock (direction is ambiguous from "
                     "the data)")

    # ---- Coherence trade-off note: the understeer/power-oversteer resolution ----
    if understeer and power_os:
        tradeoffs.append(
            "Understeer AND power oversteer together: the car is freed at the FRONT "
            "(softer front bar, front toe-out, more front aero) and PLANTED at the REAR "
            "(more rear aero + toe-in, softer rear bar) — so it rotates on entry but "
            "drives off the corner. The rear bar is softened for grip, NOT stiffened for "
            "rotation, because the rear is already loose on power."
        )

    if not moves:
        return BalanceSolution(False, tuple(complaints), [], tradeoffs, tests,
                               "Every balance lever the complaints need is locked or at its "
                               "limit — run the targeted tests instead.", "")

    addressed_axes = sorted({m.axis for m in moves})
    summary = (
        f"Coordinated balance change addressing {len(complaints)} confirmed problems "
        f"({', '.join(complaints)}) across {', '.join(addressed_axes)}. "
        "This is an engineer's balanced starting point — apply the set together and "
        "validate on track."
    )
    protocol = (
        "Apply the whole set, then drive 3 clean laps. If the car now over-rotates on "
        "entry, back off the front (raise the front bar one step / reduce front toe-out) "
        "before touching the rear. If the rear is still loose on power, run the LSD "
        "Acceleration test noted above. Re-check braking stability after the bias move."
    )
    return BalanceSolution(True, tuple(complaints), moves, tradeoffs, tests, summary, protocol)
