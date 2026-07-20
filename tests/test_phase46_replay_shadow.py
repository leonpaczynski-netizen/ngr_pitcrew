"""Phase 46 — telemetry replay, timing budget, shadow-mode advisory validation."""
from strategy.telemetry_replay import replay_telemetry, TelemetryReplayClock
from strategy.prompt_timing import assess_prompt_timing, estimate_spoken_seconds
from strategy.shadow_advisory import run_shadow_replay, voice_gate_allows, LiveValidationReadiness


_PLAN = {"content_fingerprint": "pfp", "run_structure": {"minimum_clean_laps": 3, "warm_up_laps": 2}}
_COACH = {"priorities": [{"corner": "T2", "technique_focus": "progressive throttle",
                          "why_it_matters": "exit drive", "confidence": "high"}]}


def _frames(**over):
    base = [
        {"dt": 0.2, "lap": 1, "run_active": True, "segment_type": "straight", "workload": "low",
         "telemetry_fresh": True, "approaching_corner": "T2", "clean_laps": 0},
        {"dt": 0.2, "lap": 3, "run_active": True, "segment_type": "braking", "workload": "high",
         "telemetry_fresh": True, "approaching_corner": "T2", "clean_laps": 1},
        {"dt": 2.0, "lap": 4, "run_active": True, "segment_type": "straight", "workload": "low",
         "telemetry_fresh": True, "clean_laps": 2},
    ]
    return base


# ---- 13. replay adapter --------------------------------------------------------------------- #
def test_replay_deterministic_and_events():
    r = replay_telemetry(_frames())
    assert r.lap_count >= 1 and r.stale_gap_count == 1
    assert r.content_fingerprint == replay_telemetry(_frames()).content_fingerprint


def test_replay_speed_independent_semantics():
    a = replay_telemetry(_frames(), playback_speed=1.0)
    b = replay_telemetry(_frames(), playback_speed=8.0)
    assert a.content_fingerprint == b.content_fingerprint          # decisions identical
    assert a.cycles[-1]["monotonic"] != b.cycles[-1]["monotonic"]  # wall time scales with speed


def test_replay_clock_injected():
    c = TelemetryReplayClock(start_monotonic=10.0, playback_speed=2.0)
    assert c.advance(4.0) == 12.0 and c.now() == 12.0


# ---- 16/17. message-duration budget --------------------------------------------------------- #
def test_short_cue_fits_long_defers():
    short = {"priority": 5, "prompt_class": "informational", "message": "T2 progressive throttle"}
    long = {"priority": 5, "prompt_class": "informational",
            "message": " ".join(["word"] * 40)}
    assert assess_prompt_timing(short, 3.0).fits
    assert assess_prompt_timing(long, 3.0).verdict == "too_long_for_class"


def test_stop_critical_immediate():
    p = {"priority": 1, "prompt_class": "stop_critical", "message": "Run invalid stop"}
    a = assess_prompt_timing(p, 0.0)
    assert a.verdict == "immediate" and a.fits


def test_estimate_scales_with_words():
    assert estimate_spoken_seconds("one two three") < estimate_spoken_seconds(" ".join(["w"] * 20))


# ---- 15/18/25. shadow decisions + workload + readiness -------------------------------------- #
def test_shadow_no_high_workload_or_stale_delivery():
    r = replay_telemetry(_frames())
    s = run_shadow_replay(r.to_dict(), context_fingerprint="cfp", run_plan=_PLAN,
                          coaching_plan=_COACH, workflow={"state": "run_active"})
    assert s.high_workload_deliveries == 0 and s.stale_deliveries == 0
    assert s.readiness == LiveValidationReadiness.SHADOW_READY.value
    assert not voice_gate_allows(s.readiness)   # voice unavailable below the voice-eligible gate


def test_voice_eligible_requires_live_shadow_confirmation():
    r = replay_telemetry(_frames())
    s = run_shadow_replay(r.to_dict(), context_fingerprint="cfp", run_plan=_PLAN,
                          coaching_plan=_COACH, workflow={"state": "run_active"},
                          live_shadow_confirmed=True)
    assert s.readiness == LiveValidationReadiness.VOICE_ELIGIBLE.value
    assert voice_gate_allows(s.readiness)


# ---- property: shadow == voice-eligible selection ------------------------------------------- #
def test_shadow_matches_direct_engine():
    from strategy.runtime_snapshot import build_runtime_snapshot
    from strategy.live_advisory import build_candidate_prompts
    from strategy.live_advisory_engine import evaluate_live_advisories
    frame = _frames()[0]
    snap = build_runtime_snapshot(context_fingerprint="cfp", run_plan=_PLAN,
                                  workflow={"state": "run_active"}, telemetry=frame)
    direct = evaluate_live_advisories(build_candidate_prompts(snap, _PLAN, {"state": "run_active"},
                                      _COACH), snap, now_monotonic=0.2, state={})
    r = replay_telemetry([{**frame, "dt": 0.2}])
    s = run_shadow_replay(r.to_dict(), context_fingerprint="cfp", run_plan=_PLAN,
                          coaching_plan=_COACH, workflow={"state": "run_active"})
    # shadow's first shadow-delivered prompt equals the engine's direct decision
    if direct.delivered:
        assert s.records and s.records[0]["suppression_key"] == direct.delivered["suppression_key"]


def test_stale_gap_no_duplicate_on_resume():
    frames = [{"dt": 0.2, "lap": 3, "run_active": True, "segment_type": "straight", "workload": "low",
               "telemetry_fresh": True, "clean_laps": 1},
              {"dt": 2.0, "lap": 3, "run_active": True, "segment_type": "straight", "workload": "low",
               "telemetry_fresh": True, "clean_laps": 1}]   # stale gap
    r = replay_telemetry(frames)
    s = run_shadow_replay(r.to_dict(), context_fingerprint="cfp", run_plan=_PLAN,
                          coaching_plan=_COACH, workflow={"state": "run_active"})
    assert s.stale_deliveries == 0
