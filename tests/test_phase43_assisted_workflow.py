"""Phase 43 — assisted workflow transitions, setup verification, session binding, outcome capture."""
from strategy.assisted_run_workflow import (
    evaluate_assisted_run_workflow, verify_setup, WorkflowState, SetupVerification,
)
from strategy.session_binding import rank_candidate_sessions
from strategy.assisted_outcome_capture import build_assisted_outcome_review, CaptureReadiness


_PLAN = {"content_fingerprint": "pfp", "controlled_change": {"changes": [{"field": "lsd_initial"}]}}
_PF_OK = {"ok": True, "blockers": []}
_SID = {"car": "P", "track": "Fuji"}


def _wf(**kw):
    base = dict(run_plan=_PLAN, preflight=_PF_OK, session_identity=_SID,
                expected_setup={"setup_hash": "B"},
                applied_setup={"setup_hash": "B", "fields": {"lsd_initial": "40"}},
                parent_setup={"fields": {"lsd_initial": "20"}},
                confirmations={"setup_confirmed": True}, lifecycle="ready_to_run")
    base.update(kw)
    return evaluate_assisted_run_workflow(**base)


# ---- 9. setup fingerprint verification ------------------------------------------------------ #
def test_setup_fingerprint_mismatch_blocks():
    w = _wf(applied_setup={"setup_hash": "A", "fields": {"lsd_initial": "20"}})
    assert w.state == WorkflowState.INVALID.value
    assert w.setup_check["verification"] == SetupVerification.MISMATCH.value


def test_unexpected_field_change_confounds():
    w = _wf(applied_setup={"setup_hash": "B", "fields": {"lsd_initial": "40", "arb_rear": "8"}},
            parent_setup={"fields": {"lsd_initial": "20", "arb_rear": "6"}})
    assert w.state == WorkflowState.INVALID.value
    assert w.setup_check["verification"] == SetupVerification.UNEXPECTED_CHANGE.value
    assert "arb_rear" in w.setup_check["unexpected_changed_fields"]


def test_setup_without_fingerprint_is_unverifiable():
    c = verify_setup({}, {"fields": {"lsd_initial": "40"}}, ["lsd_initial"],
                     {"fields": {"lsd_initial": "20"}})
    assert c.verification == SetupVerification.UNVERIFIABLE.value


# ---- 10/11. transitions + preflight blocking ------------------------------------------------ #
def test_correct_run_reaches_ready_to_run():
    assert _wf().state == WorkflowState.READY_TO_RUN.value


def test_preflight_blocker_blocks():
    w = _wf(preflight={"ok": False, "blockers": ["unresolved diagnosis"]})
    assert w.state == WorkflowState.INVALID.value


def test_setup_not_confirmed_stays_at_confirmation():
    w = _wf(confirmations={"setup_confirmed": False}, lifecycle="setup_confirmation_required")
    assert w.state == WorkflowState.SETUP_CONFIRMATION_REQUIRED.value


def test_stale_plan_fingerprint_blocks():
    w = _wf(plan_fingerprint_current="DIFFERENT")
    assert w.state == WorkflowState.INVALID.value


# ---- property: changing the active setup invalidates the run plan --------------------------- #
def test_changing_active_setup_changes_readiness():
    good = _wf()
    changed = _wf(applied_setup={"setup_hash": "C", "fields": {"lsd_initial": "40"}})
    assert good.state == WorkflowState.READY_TO_RUN.value
    assert changed.state == WorkflowState.INVALID.value
    assert good.content_fingerprint != changed.content_fingerprint


# ---- 13. session candidate ranking ---------------------------------------------------------- #
def test_two_equal_sessions_ambiguous_not_auto_newest():
    ctx = {"car": "Porsche", "track": "Fuji", "layout_id": "fc", "compound": "RH"}
    sessions = [{"session_id": "s_a", "car": "Porsche", "track": "Fuji", "layout_id": "fc",
                 "compound": "RH", "applied_setup_fingerprint": "B", "clean_laps": 5, "start": "10:00"},
                {"session_id": "s_b", "car": "Porsche", "track": "Fuji", "layout_id": "fc",
                 "compound": "RH", "applied_setup_fingerprint": "B", "clean_laps": 5, "start": "11:00"}]
    r = rank_candidate_sessions(sessions, ctx, expected_setup_fingerprint="B", min_clean_laps=3)
    assert r.auto_bind_forbidden and r.requires_explicit_selection and r.ambiguous


def test_wrong_compound_session_flagged():
    ctx = {"car": "Porsche", "track": "Fuji", "compound": "RH"}
    r = rank_candidate_sessions([{"session_id": "s", "car": "Porsche", "track": "Fuji",
                                  "compound": "RM", "clean_laps": 5}], ctx, min_clean_laps=3)
    assert any("compound" in m for m in r.candidates[0]["mismatches"])


# ---- 15/16. explicit outcome confirmation + canonical reuse --------------------------------- #
_OBS = dict(candidate_tested=True, applied_setup_matches_plan=True, context_matches_plan=True,
            telemetry_complete=True, clean_laps=5, min_clean_required=3, compound_used="RH",
            planned_compound="RH", target_metric_improved=True, lap_time_delta=-0.2,
            consistency_effect="better", telemetry_session="s_a")
_RP = {"content_fingerprint": "pfp",
       "controlled_change": {"changes": [{"field": "lsd_initial", "why": "reduce wheelspin"}]},
       "expected_result": {"primary_expected_outcome": "less wheelspin"}}


def test_no_outcome_until_explicit_confirmation():
    unconfirmed = build_assisted_outcome_review(_OBS, _RP, {"discipline": "race"}, session_bound=True,
                                                outcome_confirmed=False)
    assert unconfirmed.readiness == CaptureReadiness.REVIEW_REQUIRED.value
    confirmed = build_assisted_outcome_review(_OBS, _RP, {"discipline": "race"}, session_bound=True,
                                              outcome_confirmed=True, confirmed_by="Leon")
    assert confirmed.readiness == CaptureReadiness.READY_TO_RECORD.value
    assert "canonical" in confirmed.canonical_write_path or "workflow" in confirmed.canonical_write_path


def test_unbound_session_cannot_produce_outcome():
    r = build_assisted_outcome_review(_OBS, _RP, {}, session_bound=False)
    assert r.readiness == CaptureReadiness.NOT_READY.value and not r.review


def test_invalid_run_outcome_blocked():
    bad = dict(_OBS, compound_used="RM")  # wrong compound => confounded => not counted
    r = build_assisted_outcome_review(bad, _RP, {"discipline": "race"}, session_bound=True,
                                      outcome_confirmed=True)
    assert r.readiness == CaptureReadiness.BLOCKED.value
