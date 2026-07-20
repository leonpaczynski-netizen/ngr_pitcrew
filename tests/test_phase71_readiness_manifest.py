"""Phase 71 — readiness evaluator + release-candidate manifest: honest decisions, no optimistic default,
OPERATIONALLY_CERTIFIED impossible from software evidence, and the manifest keeps the evidence tiers
separate."""
from __future__ import annotations

from strategy.manual_uat_evidence import (
    ManualUatLedger, make_observation, ManualUatStatus, required_physical_live_areas,
)
from strategy.release_candidate_manifest import (
    evaluate_manual_uat_readiness, build_release_candidate_manifest, ManualUatReadiness,
)


def _all_physical_pass():
    led = ManualUatLedger()
    for a in required_physical_live_areas():
        led = led.append(make_observation(a, ManualUatStatus.PASS))
    return led


def test_pre_physical_is_ready_not_certified():
    r = evaluate_manual_uat_readiness(automated_tests_passed=True, bench_ready=True)
    assert r.readiness == ManualUatReadiness.READY_FOR_MANUAL_UAT


def test_green_tests_alone_cannot_certify():
    # green tests but no bench and no physical evidence → NOT_READY, never certified
    r = evaluate_manual_uat_readiness(automated_tests_passed=True, bench_ready=False)
    assert r.readiness == ManualUatReadiness.NOT_READY_FOR_MANUAL_UAT
    assert r.readiness != ManualUatReadiness.OPERATIONALLY_CERTIFIED


def test_green_bench_alone_cannot_certify():
    r = evaluate_manual_uat_readiness(automated_tests_passed=True, bench_ready=True,
                                      ledger=ManualUatLedger())
    assert r.readiness != ManualUatReadiness.OPERATIONALLY_CERTIFIED


def test_failed_safety_is_not_ready():
    r = evaluate_manual_uat_readiness(automated_tests_passed=True, bench_ready=True, safety_checks_ok=False)
    assert r.readiness == ManualUatReadiness.NOT_READY_FOR_MANUAL_UAT
    assert any("safety" in b for b in r.blockers)


def test_telemetry_and_strategy_integrity_failures_block():
    r1 = evaluate_manual_uat_readiness(automated_tests_passed=True, bench_ready=True,
                                       telemetry_integrity_ok=False)
    r2 = evaluate_manual_uat_readiness(automated_tests_passed=True, bench_ready=True,
                                       strategy_authority_ok=False)
    assert r1.readiness == ManualUatReadiness.NOT_READY_FOR_MANUAL_UAT
    assert r2.readiness == ManualUatReadiness.NOT_READY_FOR_MANUAL_UAT


def test_cert_integrity_failure_blocks():
    r = evaluate_manual_uat_readiness(automated_tests_passed=True, bench_ready=True,
                                      bench_certification_integrity_failures=1)
    assert r.readiness == ManualUatReadiness.NOT_READY_FOR_MANUAL_UAT


def test_operationally_certified_requires_all_physical_pass_and_grant():
    led = _all_physical_pass()
    granted = evaluate_manual_uat_readiness(automated_tests_passed=True, bench_ready=True, ledger=led,
                                            operationally_granted=True)
    assert granted.readiness == ManualUatReadiness.OPERATIONALLY_CERTIFIED
    ungranted = evaluate_manual_uat_readiness(automated_tests_passed=True, bench_ready=True, ledger=led,
                                              operationally_granted=False)
    assert ungranted.readiness == ManualUatReadiness.CONDITIONAL_FOR_MANUAL_UAT


def test_operationally_certified_impossible_with_one_missing_physical_area():
    req = required_physical_live_areas()
    led = ManualUatLedger()
    for a in req[:-1]:                       # deliberately leave one physical/live area untested
        led = led.append(make_observation(a, ManualUatStatus.PASS))
    r = evaluate_manual_uat_readiness(automated_tests_passed=True, bench_ready=True, ledger=led,
                                      operationally_granted=True)
    assert r.readiness != ManualUatReadiness.OPERATIONALLY_CERTIFIED


def test_manual_fail_blocks_readiness():
    led = ManualUatLedger().append(make_observation("physical_tts", ManualUatStatus.FAIL))
    r = evaluate_manual_uat_readiness(automated_tests_passed=True, bench_ready=True, ledger=led)
    assert r.readiness == ManualUatReadiness.NOT_READY_FOR_MANUAL_UAT


def test_no_optimistic_default_with_no_facts():
    # with nothing supplied, the default must be NOT_READY (never optimistic)
    r = evaluate_manual_uat_readiness(automated_tests_passed=False)
    assert r.readiness == ManualUatReadiness.NOT_READY_FOR_MANUAL_UAT


def test_manifest_keeps_evidence_tiers_separate():
    m = build_release_candidate_manifest(
        branch="b", commit="c1", parent_commit="p", db_version=28, rule_engine_version="46.0",
        automated_tests_passed=10277, automated_tests_skipped=27, automated_tests_failed=0,
        bench_total=67, bench_passed=67, bench_ready=True)
    d = m.to_dict()
    tiers = d["evidence_tiers"]
    assert "automated_regression" in tiers and "bench_uat" in tiers
    assert tiers["operational_certification"] == "ready_for_manual_uat"
    # a pre-physical build is at most READY_FOR_MANUAL_UAT
    assert m.readiness.readiness == ManualUatReadiness.READY_FOR_MANUAL_UAT
    assert m.db_version == 28 and m.rule_engine_version == "46.0"


def test_manifest_deterministic():
    kw = dict(branch="b", commit="c1", db_version=28, rule_engine_version="46.0",
              automated_tests_passed=100, bench_total=67, bench_passed=67, bench_ready=True)
    assert build_release_candidate_manifest(**kw).fingerprint == build_release_candidate_manifest(**kw).fingerprint
