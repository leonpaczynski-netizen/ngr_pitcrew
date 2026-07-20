"""Phase 51 — active-cycle resolution + Event Command Centre domain (task test items 4-11)."""
from __future__ import annotations

from strategy.active_cycle_resolution import (
    CycleCandidate, ActiveCycleResolutionState as R, resolve_active_cycle,
)
from strategy.event_command_centre import (
    build_event_command_centre, NextActionCategory as NA, QUICK_ACTION_SURFACES,
)


def _c(cid, **kw):
    return CycleCandidate(cycle_id=cid, **kw)


# --- active-cycle resolution -----------------------------------------------

def test_no_candidates_is_no_active_event():
    r = resolve_active_cycle([])
    assert r.state == R.NO_ACTIVE_EVENT and r.resolved_cycle_id == ""


def test_only_completed_is_no_active_event():
    r = resolve_active_cycle([_c("a", explicit_state="complete"), _c("b", explicit_state="abandoned")])
    assert r.state == R.NO_ACTIVE_EVENT


def test_single_active_resolves_to_it():
    r = resolve_active_cycle([_c("a", explicit_state="active", event_name="Cup R3")])
    assert r.state == R.ONE_ACTIVE_EVENT and r.resolved_cycle_id == "a"
    assert r.selection_required is False


def test_multiple_active_requires_explicit_selection_never_newest():
    cands = [_c("older", explicit_state="active", official_race_date="2026-06-21"),
             _c("newer", explicit_state="active", official_race_date="2026-07-21")]
    r = resolve_active_cycle(cands)
    assert r.state == R.EVENT_REQUIRES_SELECTION
    assert r.selection_required is True
    assert r.resolved_cycle_id == ""  # never silently picks newest


def test_explicit_selection_wins():
    cands = [_c("a", explicit_state="active"), _c("b", explicit_state="active")]
    r = resolve_active_cycle(cands, selected_cycle_id="b")
    assert r.state == R.ONE_ACTIVE_EVENT and r.resolved_cycle_id == "b"


def test_paused_event_resolves_paused():
    r = resolve_active_cycle([_c("a", explicit_state="paused")])
    assert r.state == R.PAUSED_EVENT


def test_upcoming_event_when_prep_not_open():
    r = resolve_active_cycle([_c("a", explicit_state="active", prep_open_date="2026-08-01")],
                             now_date="2026-06-01")
    assert r.state == R.UPCOMING_EVENT


def test_context_changed_and_blocked_flags():
    assert resolve_active_cycle([_c("a", explicit_state="active", context_changed=True)]).state \
        == R.EVENT_CONTEXT_CHANGED
    assert resolve_active_cycle([_c("a", explicit_state="active", blocked=True)]).state == R.EVENT_BLOCKED


def test_resolution_fingerprint_excludes_now_date():
    cands = [_c("a", explicit_state="active", official_race_date="2026-06-21")]
    early = resolve_active_cycle(cands, now_date="2026-06-01")
    late = resolve_active_cycle(cands, now_date="2026-06-20")
    assert early.fingerprint == late.fingerprint  # now_date is not semantic identity


def test_selection_does_not_change_candidate_evidence_fingerprint():
    cands = [_c("a", explicit_state="active"), _c("b", explicit_state="active")]
    unresolved = resolve_active_cycle(cands)
    selected = resolve_active_cycle(cands, selected_cycle_id="a")
    # resolved identity differs, but the candidate membership payload is identical
    assert unresolved.as_semantic_payload()["candidates"] == selected.as_semantic_payload()["candidates"]


# --- Event Command Centre --------------------------------------------------

def _report(**kw):
    base = {"ok": True, "cycle": {"event_name": "Porsche Cup R3", "series": "NGR Porsche Cup",
                                  "round": "R3", "state": "active", "current_phase": "setup_development",
                                  "official_race_date": "2026-06-21"},
            "next_action": {"headline": "Build race_setup evidence", "rationale": "weakest domain"},
            "timeline": [{"name": "Event opens", "date": "2026-06-01", "state": "done"}],
            "progress": {"valid_laps": 142, "practice_sessions": 6, "setup_experiments": 3,
                         "coaching_runs": 2, "tyre_samples": 4, "fuel_samples": 2, "race_simulations": 1},
            "readiness": [["race_setup", "developing", "2 exact"], ["fuel_evidence", "missing", "none"]],
            "setup": {"base": "improving", "qualifying": "provisional", "race": "stable_with_uncertainty"},
            "strategy": {"maturity": "developing", "missing": ["validated long run"]}}
    base.update(kw)
    return base


def test_command_centre_no_active_event_prompts_create():
    r = resolve_active_cycle([])
    cc = build_event_command_centre(r, None)
    assert cc.next_action.category == NA.CREATE_EVENT
    assert cc.next_action.target_surface == "no_event"


def test_command_centre_requires_selection():
    r = resolve_active_cycle([_c("a", explicit_state="active"), _c("b", explicit_state="active")])
    cc = build_event_command_centre(r, None)
    assert cc.next_action.category == NA.SELECT_EVENT
    assert len(cc.candidates) == 2


def test_command_centre_single_primary_action_priority():
    r = resolve_active_cycle([_c("a", explicit_state="active")], selected_cycle_id="a")
    # pending binding beats everything else in-cycle
    cc = build_event_command_centre(r, _report(), pending_binding=True, strategy_final_ready=True,
                                    lock_ready_disciplines=["race"])
    assert cc.next_action.category == NA.BIND_SESSION
    # without binding/debrief, strategy finalisation beats lock
    cc2 = build_event_command_centre(r, _report(), strategy_final_ready=True,
                                     lock_ready_disciplines=["race"])
    assert cc2.next_action.category == NA.FINALISE_STRATEGY
    # only lock ready
    cc3 = build_event_command_centre(r, _report(), lock_ready_disciplines=["race"])
    assert cc3.next_action.category == NA.LOCK_SETUP and "race" in cc3.next_action.headline
    # else the cumulative objective
    cc4 = build_event_command_centre(r, _report())
    assert cc4.next_action.category == NA.NEXT_ACTIVITY


def test_command_centre_attention_flags_missing_required_setup():
    r = resolve_active_cycle([_c("a", explicit_state="active")], selected_cycle_id="a")
    rep = _report(readiness=[["race_setup", "missing", "none"]])
    cc = build_event_command_centre(r, rep, pending_binding=True)
    kinds = {a.kind for a in cc.attention_items}
    assert "missing_evidence" in kinds and "pending_binding" in kinds


def test_command_centre_progress_and_quick_actions():
    r = resolve_active_cycle([_c("a", explicit_state="active")], selected_cycle_id="a")
    cc = build_event_command_centre(r, _report())
    assert cc.progress.valid_laps == 142 and cc.progress.practice_sessions == 6
    assert len(cc.quick_actions) == len(QUICK_ACTION_SURFACES)


def test_command_centre_countdown_excluded_from_fingerprint():
    r = resolve_active_cycle([_c("a", explicit_state="active")], selected_cycle_id="a")
    early = build_event_command_centre(r, _report(), now_date="2026-06-01")
    late = build_event_command_centre(r, _report(), now_date="2026-06-20")
    assert early.days_until_race == 20 and late.days_until_race == 1
    assert early.fingerprint == late.fingerprint


def test_command_centre_deterministic():
    r = resolve_active_cycle([_c("a", explicit_state="active")], selected_cycle_id="a")
    a = build_event_command_centre(r, _report())
    b = build_event_command_centre(r, _report())
    assert a.fingerprint == b.fingerprint
