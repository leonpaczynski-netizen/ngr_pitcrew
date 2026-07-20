"""Shared helpers for the Phase 36-38 Race-Engineer Activation tests (not collected by pytest)."""
from __future__ import annotations

from strategy.engineering_context_scope import build_engineering_context_scope

CAR = "Porsche 911 RSR (991) '17"


def scope(*, car=CAR, discipline="race", gt7="1.49", driver="Leon", track="Fuji",
          layout="full_course", compound="RH", event="E1", rule="46.0"):
    return build_engineering_context_scope({
        "programme": {"car": car, "discipline": discipline, "gt7_version": gt7, "driver": driver},
        "track": track, "layout_id": layout, "compound": compound, "event_id": event,
        "rule_engine_version": rule, "db_schema_version": "26"})


def ctx(*, car=CAR, discipline="race", gt7="1.49", driver="Leon", track="Fuji",
        layout="full_course", compound="RH"):
    return {"car": car, "discipline": discipline, "gt7_version": gt7, "driver": driver,
            "track": track, "layout_id": layout, "compound": compound}


def record(record_key, *, changes=None, outcome="confirmed_improvement", confidence="high",
           at="2026-01-01", session="s1", context=None, residuals=None, protected=None,
           improvements=None, regressions=None, windows=None, protected_knowledge=None,
           experiment_id=None, outcome_id=None):
    """Build a DevelopmentRecord-shaped dict (as returned by the knowledge chain 'records')."""
    return {
        "record_key": record_key,
        "experiment_id": experiment_id or record_key,
        "outcome_id": outcome_id or ("o" + record_key),
        "context": context or ctx(),
        "changes": [dict(c) for c in (changes or [])],
        "outcome_status": outcome, "confidence_level": confidence,
        "recorded_at": at, "session_date": at, "test_session_id": session,
        "residual_states": [dict(r) for r in (residuals or [])],
        "confirmed_improvements": [dict(i) for i in (improvements or [])],
        "new_regressions": [dict(r) for r in (regressions or [])],
        "protected_behaviours": [dict(p) for p in (protected or [])],
        "working_window_snapshot": [dict(w) for w in (windows or [])],
        "protected_knowledge": [dict(k) for k in (protected_knowledge or [])],
    }


def change(field, to_value="1", direction="increase", from_value="0", subsystem=""):
    return {"field": field, "to_value": to_value, "direction": direction,
            "from_value": from_value, "subsystem": subsystem}


def residual(issue_type, *, phase="entry", corner="T1", state="present", family="",
             is_new=False, is_regression=False, confidence="high"):
    return {"issue_type": issue_type, "family": family or issue_type, "phase": phase,
            "corner_name": corner, "segment_id": corner, "residual_state": state,
            "is_new": is_new, "is_regression": is_regression, "still_present": state != "resolved",
            "protected_good": False, "confidence": confidence}
