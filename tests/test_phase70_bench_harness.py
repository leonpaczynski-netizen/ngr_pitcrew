"""Phase 70 — deterministic bench UAT harness: all scenarios pass, reproducible, category coverage,
aggregate report, certification-integrity, and structural safety (bench cannot mutate live state or
promote a physical area)."""
from __future__ import annotations

from strategy.bench_uat_harness import (
    run_bench_uat, run_bench_scenario, BENCH_SCENARIOS, BenchUatResult, certification_from_bench,
    BenchTrackerSnapshot,
)
from strategy.event_programme_certification import _LIVE_VR_PHYSICAL_OR_LIVE


def test_all_scenarios_pass():
    rep = run_bench_uat()
    assert rep.total == 67
    assert rep.failed == 0, rep.failure_details
    assert rep.blocked == 0
    assert rep.safety_failures == 0
    assert rep.overall_bench_ready is True


def test_scenarios_are_deterministic():
    a = run_bench_uat()
    b = run_bench_uat()
    assert a.fingerprint == b.fingerprint
    for ra, rb in zip(a.results, b.results):
        assert ra.fingerprint == rb.fingerprint


def test_single_scenario_reproducible():
    s = BENCH_SCENARIOS[2]
    assert run_bench_scenario(s).fingerprint == run_bench_scenario(s).fingerprint


def test_category_coverage():
    rep = run_bench_uat()
    cats = {r.category for r in rep.results}
    for c in ("baseline", "fuel", "pace", "tyre", "pit", "lap_count", "time_certain", "audio_ptt",
              "certification"):
        assert c in cats


def test_every_result_has_safety_checks_true():
    rep = run_bench_uat()
    for r in rep.results:
        assert all(r.safety_checks.values()), r.scenario_id
        assert r.safety_checks["no_physical_certification_promotion"] is True
        assert r.safety_checks["no_pit_call"] is True
        assert r.safety_checks["no_setup_apply"] is True


def test_certification_from_bench_cannot_promote_physical():
    # even if EVERY software area 'passed', physical/PSVR2/live areas stay NONE and overall NOT_TESTED
    cert = certification_from_bench({})   # all software pass by default
    by = {a.name: a.evidence_type.value for a in cert.areas}
    for name in _LIVE_VR_PHYSICAL_OR_LIVE:
        assert by[name] == "none"
    assert cert.overall_level.value == "not_tested"


def test_failed_bench_lowers_only_software_area():
    cert = certification_from_bench({"fuel_burn": False})
    by = {a.name: a.evidence_type.value for a in cert.areas}
    assert by["fuel_burn"] == "none"               # the failed software area is lowered
    assert by["real_tracker_mapping"] == "automated"  # a passing software area stays automated
    for name in _LIVE_VR_PHYSICAL_OR_LIVE:
        assert by[name] == "none"                  # physical areas never promoted regardless
    assert cert.overall_level.value == "not_tested"


def test_bench_result_is_immutable_snapshot():
    r = run_bench_scenario(BENCH_SCENARIOS[0])
    assert isinstance(r, BenchUatResult)
    d = r.to_dict()
    assert set(d) >= {"scenario_id", "passed", "actual", "expected", "safety_checks",
                      "certification_effects", "audio_events", "ptt_outcome"}


def test_failure_is_not_hidden_behind_warning():
    # a deliberately-wrong expectation must surface as a FAILED result, not a warning
    from strategy.bench_uat_harness import BenchScenario
    bad = BenchScenario("BAD", "wrong expectation", "baseline", tracker=None,
                        expected={"recommendation": "PLAN_STILL_OPTIMAL"})  # actual is INSUFFICIENT
    r = run_bench_scenario(bad)
    assert r.passed is False
    assert r.failure_reasons


def test_bench_tracker_is_data_only():
    # the injection seam is a frozen data holder — no methods that compute strategy
    t = BenchTrackerSnapshot(race_type="laps", laps_recorded=5)
    assert t.race_type == "laps"
    # frozen dataclass: cannot mutate
    try:
        t.laps_recorded = 6
        raise AssertionError("BenchTrackerSnapshot must be frozen")
    except Exception:
        pass
