"""Engineering-Brain Phase 5 — working-window domain + update-engine tests (pure)."""
from __future__ import annotations

from pathlib import Path

import pytest

from strategy.working_window import (
    WORKING_WINDOW_VERSION, WindowContextKey, WindowEvidence, WindowContribution,
    WindowConfidence, Direction, DirectionEffect, LearnedWorkingWindow,
    outcome_to_window_evidence, recompute_working_window,
)

ROOT = Path(__file__).resolve().parents[1]


def _ctx(field="rear_arb"):
    return WindowContextKey(scope_fingerprint="eck_v1:scope:x", car="RSR",
                            track="Fuji", layout_id="full", discipline="Race",
                            field=field)


def _exp(field="rear_arb", frm="6", to="5", compound_extra=None):
    changes = [{"field": field, "from_value": frm, "to_value": to, "role": "primary",
                "delta_magnitude": 1.0, "symptom": "mid_understeer"}]
    if compound_extra:
        changes.append({"field": compound_extra, "from_value": "3", "to_value": "4",
                        "role": "supporting"})
    return {"id": "1", "scope_fingerprint": "eck_v1:scope:x",
            "applied_checkpoint_id": "cp1", "changes": changes}


def _oc(status, oid="10", corners=None):
    return {"id": oid, "status": status, "test_session_id": "200",
            "corners": corners or []}


def _ev(status, field="rear_arb", frm="6", to="5", oid="10", compound=None):
    return outcome_to_window_evidence(
        _exp(field, frm, to, compound), _oc(status, oid), context=_ctx(field))


# --- 12.1 domain -----------------------------------------------------------
def test_unknown_window():
    w = recompute_working_window((), _ctx())
    assert w.confidence == WindowConfidence.NONE and not w.is_evidenced


def test_provisional_window_one_success():
    w = recompute_working_window(_ev("confirmed_improvement"), _ctx(), legal_low=1, legal_high=7)
    assert w.confidence == WindowConfidence.PROVISIONAL
    assert w.successful_values == (5.0,) and w.preferred_center == 5.0
    assert any("provisional" in x for x in w.warnings)


def test_multiple_successful_points_raise_confidence():
    ev = _ev("confirmed_improvement", to="5", oid="10") \
        + _ev("confirmed_improvement", to="5", oid="11") \
        + _ev("confirmed_improvement", to="4", oid="12")
    w = recompute_working_window(ev, _ctx(), legal_low=1, legal_high=7)
    assert w.valid_experiment_count == 3
    assert w.confidence in (WindowConfidence.MEDIUM, WindowConfidence.HIGH)


def test_conflicting_outcomes_reduce_confidence():
    ev = _ev("confirmed_improvement", frm="6", to="7", oid="10") \
        + _ev("regression", frm="6", to="7", oid="11") \
        + _ev("confirmed_improvement", frm="6", to="7", oid="12")
    w = recompute_working_window(ev, _ctx(), legal_low=1, legal_high=7)
    assert w.contradiction
    assert w.confidence == WindowConfidence.LOW    # contradiction caps confidence


def test_regression_records_unsuccessful_and_locks_direction():
    w = recompute_working_window(
        _ev("regression", frm="22", to="26", field="lsd_accel"),
        _ctx("lsd_accel"), legal_low=0, legal_high=60)
    assert 26.0 in w.unsuccessful_values
    assert "increase" in w.locked_directions()


def test_unchanged_result_is_ineffective_not_learning():
    w = recompute_working_window(
        _ev("no_meaningful_change", field="lsd_accel", frm="22", to="26"),
        _ctx("lsd_accel"))
    assert w.improvement_count == 0 and w.regression_count == 0
    assert w.unchanged_count == 1 and 26.0 in w.ineffective_values


@pytest.mark.parametrize("status", ["confounded", "insufficient_evidence"])
def test_inconclusive_invalid_does_not_learn(status):
    w = recompute_working_window(_ev(status), _ctx())
    assert w.valid_experiment_count == 0 and w.inconclusive_count == 1
    assert not w.successful_values and not w.unsuccessful_values


def test_cross_track_prior_flagged_lower_confidence():
    ev = outcome_to_window_evidence(_exp(), _oc("confirmed_improvement"), context=_ctx())
    ev = (ev[0].__class__(**{**ev[0].to_dict(),
          "direction": ev[0].direction, "contribution": ev[0].contribution,
          "is_direct": False}),)  # rebuild w/ is_direct False
    # simpler: construct directly
    e = WindowEvidence(context_key=_ctx().key(), experiment_id="9", outcome_id="99",
                       field="rear_arb", from_value="6", to_value="5",
                       direction=Direction.DECREASE, magnitude=1.0,
                       outcome_status="confirmed_improvement",
                       contribution=WindowContribution.SUCCESSFUL, is_compound=False,
                       attribution_confidence="high", is_direct=False)
    w = recompute_working_window((e,), _ctx(), legal_low=1, legal_high=7)
    assert not w.has_direct_evidence
    assert any("inherited" in x for x in w.warnings)


def test_deterministic_ordering_and_serialisation():
    ev = _ev("confirmed_improvement", oid="10") + _ev("regression", frm="6", to="7", oid="11")
    a = recompute_working_window(ev, _ctx(), legal_low=1, legal_high=7)
    b = recompute_working_window(tuple(reversed(ev)), _ctx(), legal_low=1, legal_high=7)
    assert a.to_dict() == b.to_dict()


def test_full_provenance_retained():
    w = recompute_working_window(_ev("confirmed_improvement"), _ctx(), legal_low=1, legal_high=7)
    assert w.supporting_experiment_ids == ("1",)
    assert w.supporting_checkpoint_ids == ("cp1",)
    assert w.provenance


# --- 12.2 update engine ----------------------------------------------------
def test_idempotent_replay_no_double_count():
    ev = _ev("confirmed_improvement")
    w = recompute_working_window(ev + ev, _ctx(), legal_low=1, legal_high=7)
    assert w.valid_experiment_count == 1          # de-duped by (experiment, outcome)


def test_out_of_order_replay_same_result():
    ev = _ev("confirmed_improvement", oid="10") + _ev("no_meaningful_change", frm="5", to="4", oid="11")
    a = recompute_working_window(ev, _ctx(), legal_low=1, legal_high=7)
    b = recompute_working_window(ev[::-1], _ctx(), legal_low=1, legal_high=7)
    assert a.to_dict() == b.to_dict()


def test_compound_experiment_low_attribution():
    ev = outcome_to_window_evidence(
        _exp("rear_arb", "6", "5", compound_extra="arb_front"),
        _oc("regression"), context=_ctx())
    assert all(e.is_compound and e.attribution_confidence == "low" for e in ev)


def test_regression_not_averaged_away():
    ev = _ev("confirmed_improvement", frm="4", to="5", oid="10") \
        + _ev("regression", frm="4", to="6", oid="11")
    w = recompute_working_window(ev, _ctx(), legal_low=1, legal_high=7)
    assert 6.0 in w.unsuccessful_values          # regression preserved, not smoothed
    assert w.regression_count == 1


def test_lockout_needs_no_compatible_improvement():
    # a strong single-field regression locks; an improvement in the same direction lifts it
    reg = _ev("regression", field="lsd_accel", frm="22", to="26", oid="10")
    w1 = recompute_working_window(reg, _ctx("lsd_accel"), legal_low=0, legal_high=60)
    assert "increase" in w1.locked_directions()
    imp = outcome_to_window_evidence(
        _exp("lsd_accel", "22", "24"), _oc("confirmed_improvement", "11"),
        context=_ctx("lsd_accel"))
    w2 = recompute_working_window(reg + imp, _ctx("lsd_accel"), legal_low=0, legal_high=60)
    assert "increase" not in w2.locked_directions()  # improvement lifts the lockout


# --- property / metamorphic ------------------------------------------------
def test_replay_cannot_increase_counts():
    ev = _ev("confirmed_improvement")
    one = recompute_working_window(ev, _ctx(), legal_low=1, legal_high=7)
    many = recompute_working_window(ev * 5, _ctx(), legal_low=1, legal_high=7)
    assert many.valid_experiment_count == one.valid_experiment_count == 1


def test_adding_invalid_evidence_cannot_increase_confidence():
    base = recompute_working_window(
        _ev("confirmed_improvement", oid="10") + _ev("confirmed_improvement", to="5", oid="11"),
        _ctx(), legal_low=1, legal_high=7)
    noisy = recompute_working_window(
        _ev("confirmed_improvement", oid="10") + _ev("confirmed_improvement", to="5", oid="11")
        + _ev("confounded", oid="12") + _ev("insufficient_evidence", oid="13"),
        _ctx(), legal_low=1, legal_high=7)
    order = {"none": 0, "provisional": 1, "low": 2, "medium": 3, "high": 4}
    assert order[noisy.confidence.value] <= order[base.confidence.value]


def test_regression_cannot_strengthen_failed_direction():
    ev = _ev("regression", field="lsd_accel", frm="22", to="26", oid="10")
    w = recompute_working_window(ev, _ctx("lsd_accel"), legal_low=0, legal_high=60)
    inc = [d for d in w.directional if d.direction == "increase"][0]
    assert inc.effect == DirectionEffect.WORSENED and inc.improved_count == 0


def test_inconclusive_cannot_create_successful_value():
    w = recompute_working_window(_ev("confounded"), _ctx())
    assert not w.successful_values


# --- purity ----------------------------------------------------------------
def test_module_pure():
    src = (ROOT / "strategy" / "working_window.py").read_text(encoding="utf-8")
    for banned in ("PyQt6", "from ui.", "import sqlite3", "from data.session_db",
                   "requests", "anthropic", "openai", "datetime.now", "random"):
        assert banned not in src, banned
