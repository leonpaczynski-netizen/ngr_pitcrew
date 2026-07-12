"""Phase 13 — controlled test sequencing (pure, Qt-free).

A pro race engineer never changes six things then guesses which one helped. Given
the FINAL proposed changes, this orders them into a one-at-a-time test programme:
highest-confidence / lowest-risk / biggest-effect first, each stage carrying an
explicit success criterion and a rollback. When two adjacent stages act on the same
balance axis it flags that they must be isolated (test one, settle, then the next).

Pure ordering + templating over the changes already proposed. It authors NO setup
values, invents no telemetry, and applies nothing.
"""
from __future__ import annotations

from dataclasses import dataclass

from strategy.setup_arbitration import _OVERSTEER_EFFECT

_CONF_RANK = {"high": 2, "med": 1, "medium": 1, "low": 0}
_RISK_RANK = {"low": 0, "med": 1, "medium": 1, "high": 2}


@dataclass(frozen=True)
class TestStage:
    order: int
    field: str
    change_summary: str
    success_criterion: str
    rollback: str
    rationale: str
    confidence: str
    risk: str
    isolate_note: str = ""


@dataclass(frozen=True)
class TestSequence:
    stages: list
    note: str

    def is_empty(self) -> bool:
        return not self.stages


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _sort_key(ch: dict):
    conf = _CONF_RANK.get(str(ch.get("confidence_level", "")).lower(), 1)
    risk = _RISK_RANK.get(str(ch.get("risk_level", "")).lower(), 1)
    delta = _num(ch.get("delta"))
    mag = abs(delta) if delta is not None else 0.0
    # Highest confidence first, then lowest risk, then biggest effect, then field
    # name for a stable deterministic order.
    return (-conf, risk, -mag, str(ch.get("field", "")))


def _direction_word(delta) -> str:
    d = _num(delta)
    if d is None or d == 0:
        return "adjust"
    return "raise" if d > 0 else "lower"


def build_test_sequence(changes: "list[dict]", diagnosis: "dict | None" = None) -> TestSequence:
    """Order the proposed ``changes`` into a controlled one-change-at-a-time test
    programme. Each stage states what to change, how to know it worked, and how to
    roll back. Adjacent stages on the same balance axis are flagged for isolation."""
    real = []
    for ch in changes or []:
        field = ch.get("field")
        if not field:
            continue
        if _num(ch.get("delta")) in (None, 0):
            continue
        real.append(ch)

    if not real:
        return TestSequence([], "No changes to test.")

    real.sort(key=_sort_key)

    stages = []
    prev_axis_effect = None
    for i, ch in enumerate(real, start=1):
        field = ch.get("field")
        symptom = (ch.get("symptom") or "").strip()
        frm, to = ch.get("from"), ch.get("to")
        direction = _direction_word(ch.get("delta"))

        summary = f"{direction} {field}"
        if frm is not None and to is not None:
            summary += f" ({frm} → {to})"

        if symptom:
            success = (f"Confirm '{symptom}' eases without a new problem at the other "
                       "end of the car; lap time no worse.")
        else:
            success = ("Confirm the intended change is felt without a new problem "
                       "elsewhere; lap time no worse.")

        if frm is not None:
            rollback = f"If it feels worse or lap time drops, revert {field} to {frm}."
        else:
            rollback = f"If it feels worse or lap time drops, revert {field}."

        rationale = (f"{str(ch.get('confidence_level', 'med')).lower()} confidence, "
                     f"{str(ch.get('risk_level', 'low')).lower()} risk")

        # Same-axis isolation flag: if this change and the previous one both move the
        # front/rear balance, they must be tested separately, not lumped together.
        isolate = ""
        axis_effect = _OVERSTEER_EFFECT.get(field)
        if axis_effect is not None and prev_axis_effect is not None:
            isolate = ("Isolate from the previous stage — it also moves the front/rear "
                       "balance; settle and re-check before applying this one.")
        if axis_effect is not None:
            prev_axis_effect = axis_effect

        stages.append(TestStage(
            order=i, field=field, change_summary=summary, success_criterion=success,
            rollback=rollback, rationale=rationale,
            confidence=str(ch.get("confidence_level", "")).lower(),
            risk=str(ch.get("risk_level", "")).lower(), isolate_note=isolate,
        ))

    note = ("Apply one change at a time and complete a clean, representative lap before "
            "the next. Keep a change only if its success criterion is met.")
    return TestSequence(stages, note)


def test_sequence_to_json(seq: TestSequence) -> dict:
    """Serialise a TestSequence to the response dict shape."""
    return {
        "note": seq.note,
        "stages": [
            {"order": s.order, "field": s.field, "change": s.change_summary,
             "success_criterion": s.success_criterion, "rollback": s.rollback,
             "rationale": s.rationale, "confidence": s.confidence, "risk": s.risk,
             "isolate_note": s.isolate_note}
            for s in seq.stages
        ],
    }
