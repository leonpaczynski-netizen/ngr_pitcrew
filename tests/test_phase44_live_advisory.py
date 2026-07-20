"""Phase 44 — live advisory generation, priority arbitration, safe windows, suppression."""
from strategy.live_advisory import build_candidate_prompts, PromptPriority
from strategy.live_advisory_engine import evaluate_live_advisories


_PLAN = {"content_fingerprint": "pfp", "run_structure": {"minimum_clean_laps": 3, "warm_up_laps": 2}}
_COACH = {"priorities": [{"corner": "T2", "technique_focus": "progressive throttle",
                          "why_it_matters": "exit drive", "confidence": "high"}]}


def _snap(**kw):
    base = dict(context_fingerprint="cfp", run_plan_fingerprint="pfp", run_active=True, lap=3,
                clean_laps=1, telemetry_fresh=True, plan_current=True, session_active=True,
                segment_type="straight", workload="low", approaching_corner="T2")
    base.update(kw)
    return base


def _decide(snap, *, now=100.0, state=None, wf=None):
    cands = build_candidate_prompts(snap, _PLAN, wf or {"state": "run_active"}, _COACH)
    return evaluate_live_advisories(cands, snap, now_monotonic=now, state=state or {})


# ---- 17. live advisory generation ----------------------------------------------------------- #
def test_generates_applicable_candidates_only():
    cands = build_candidate_prompts(_snap(), _PLAN, {"state": "run_active"}, _COACH)
    assert cands and all(1 <= c.priority <= 8 for c in cands)


def test_no_applicable_prompt_emits_nothing():
    idle = {"context_fingerprint": "cfp", "run_active": False, "telemetry_fresh": True,
            "plan_current": True, "session_active": False, "segment_type": "pit", "workload": "low"}
    assert build_candidate_prompts(idle, _PLAN, {"state": "plan_ready"}, {}) == []


# ---- 18. priority arbitration --------------------------------------------------------------- #
def test_context_mismatch_supersedes_coaching():
    snap = _snap(segment_type="pit", in_pit=True, context_trust="reference_only",
                 mismatch_reason="wrong compound")
    d = _decide(snap)
    assert d.delivered["priority"] == PromptPriority.CONTEXT_SETUP_MISMATCH.value
    assert any("superseded" in s["reason"] for s in d.suppressed if "coach" in s["suppression_key"])


def test_stop_critical_delivers_in_high_workload():
    snap = _snap(segment_type="braking", workload="high", run_invalidated=True)
    d = evaluate_live_advisories(build_candidate_prompts(snap, _PLAN, {"state": "invalid",
                                 "blockers": ["wrong setup"]}, _COACH), snap, now_monotonic=100.0,
                                 state={})
    assert d.delivered["prompt_class"] == "stop_critical"


# ---- 19. safe-window delivery --------------------------------------------------------------- #
def test_high_workload_suppresses_coaching():
    snap = _snap(segment_type="braking", workload="high")
    d = _decide(snap)
    assert d.delivered is None or d.delivered.get("prompt_class") == "stop_critical"
    assert any("high-workload" in s["reason"] for s in d.suppressed)


# ---- 20. cooldown + deduplication (injected clock) ------------------------------------------ #
def _clean_snap(**kw):
    # a recurring "insufficient clean laps" prompt (no coaching): fires at the finish line each lap.
    base = _snap(approaching_corner="", at_finish_line=True, clean_laps=1, lap=4)
    base.update(kw)
    return base


def _clean_decide(snap, *, now, state):
    cands = build_candidate_prompts(snap, _PLAN, {"state": "run_active"}, {})
    return evaluate_live_advisories(cands, snap, now_monotonic=now, state=state)


def test_cooldown_deterministic_under_test_clock():
    d1 = _clean_decide(_clean_snap(lap=4), now=100.0, state={})
    assert d1.delivered and d1.delivered["suppression_key"] == "clean_laps"
    d2 = _clean_decide(_clean_snap(lap=4), now=105.0, state=d1.state)   # within cooldown, same lap
    assert d2.delivered is None and any(s["reason"] == "within cooldown" for s in d2.suppressed)
    d3 = _clean_decide(_clean_snap(lap=5), now=500.0, state=d1.state)   # after cooldown, new lap
    assert d3.delivered and d3.delivered["suppression_key"] == "clean_laps"


def test_per_lap_repetition_limit():
    d1 = _clean_decide(_clean_snap(lap=4), now=100.0, state={})
    # same lap, cooldown elapsed but the per-lap limit is reached
    d2 = _clean_decide(_clean_snap(lap=4), now=1000.0, state=d1.state)
    assert d2.delivered is None and any("per-lap" in s["reason"] for s in d2.suppressed)


# ---- 21/22. stale telemetry + stale plan suppression ---------------------------------------- #
def test_stale_telemetry_suppresses_all():
    d = _decide(_snap(telemetry_fresh=False))
    assert d.delivered is None and all("stale" in s["reason"] for s in d.suppressed)


def test_stale_plan_suppresses():
    d = _decide(_snap(plan_current=False))
    assert d.delivered is None


def test_passed_corner_suppresses_coaching():
    d = _decide(_snap(passed_corners=["T2"]))
    assert not any(s for s in [d.delivered] if s and s.get("suppression_key") == "coach:T2")


# ---- 24/25. stop conditions + strategy limits ----------------------------------------------- #
def test_enough_evidence_prompts_completion():
    snap = _snap(clean_laps=4, at_finish_line=True)
    d = _decide(snap)
    types = [d.delivered["prompt_type"]] if d.delivered else []
    assert "enough_evidence" in types or any(s["suppression_key"] == "enough_evidence"
                                             for s in d.suppressed)


def test_strategy_awareness_is_low_priority_only():
    cands = build_candidate_prompts(_snap(event_is_near=True, run_active=False, session_active=False,
                                          segment_type="pit"), _PLAN, {"state": "plan_ready"}, {})
    strat = [c for c in cands if c.prompt_type == "deadline_protect"]
    assert strat and strat[0].priority == PromptPriority.STRATEGY_AWARENESS.value


# ---- 23. coaching objective limits ---------------------------------------------------------- #
def test_only_one_coaching_objective_active():
    two = {"priorities": [{"corner": "T2", "technique_focus": "a", "confidence": "high"},
                          {"corner": "T3", "technique_focus": "b", "confidence": "high"}]}
    cands = build_candidate_prompts(_snap(), _PLAN, {"state": "run_active"}, two)
    coaching = [c for c in cands if c.prompt_type == "coaching_objective"]
    assert len(coaching) <= 1   # only the approaching corner's single objective


# ---- property: higher priority suppresses lower; now_monotonic not in fingerprint ----------- #
def test_now_monotonic_not_in_fingerprint():
    a = _decide(_snap(), now=1.0, state={}).content_fingerprint
    b = _decide(_snap(), now=9999.0, state={}).content_fingerprint
    assert a == b


def test_shuffled_candidates_stable():
    snap = _snap(segment_type="pit", in_pit=True, context_trust="reference_only")
    cands = build_candidate_prompts(snap, _PLAN, {"state": "run_active"}, _COACH)
    a = evaluate_live_advisories(cands, snap, now_monotonic=100.0, state={}).content_fingerprint
    b = evaluate_live_advisories(list(reversed(cands)), snap, now_monotonic=100.0,
                                 state={}).content_fingerprint
    assert a == b
