"""Phase 72 — UAT candidate identity + evidence-to-candidate binding (DEF-UAT-072-001).

Proves manual evidence is CANDIDATE-SCOPED: readiness ignores observations from a different candidate;
a code change (new commit) does not inherit operational certification; a failed area stays failed until an
explicit passing retest for the SAME candidate; historical evidence is viewable but does not count; there is
no optimistic fallback; and every observation records the candidate commit.
"""
from __future__ import annotations

from strategy.manual_uat_evidence import (
    ManualUatLedger, make_observation, ManualUatStatus, required_physical_live_areas,
)
from strategy.release_candidate_manifest import (
    evaluate_manual_uat_readiness, build_release_candidate_manifest, ManualUatReadiness,
)

OLD = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
NEW = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"


def _all_physical_pass(commit: str) -> ManualUatLedger:
    led = ManualUatLedger()
    for a in required_physical_live_areas():
        led = led.append(make_observation(a, ManualUatStatus.PASS, candidate_commit=commit))
    return led


def test_def_uat_072_001_old_evidence_cannot_certify_new_candidate():
    led = _all_physical_pass(OLD)
    r = evaluate_manual_uat_readiness(automated_tests_passed=True, bench_ready=True, ledger=led,
                                      operationally_granted=True, active_candidate_commit=NEW)
    assert r.readiness != ManualUatReadiness.OPERATIONALLY_CERTIFIED
    assert r.historical_observation_count == len(required_physical_live_areas())


def test_matching_candidate_evidence_does_certify():
    led = _all_physical_pass(OLD)
    r = evaluate_manual_uat_readiness(automated_tests_passed=True, bench_ready=True, ledger=led,
                                      operationally_granted=True, active_candidate_commit=OLD)
    assert r.readiness == ManualUatReadiness.OPERATIONALLY_CERTIFIED
    assert r.historical_observation_count == 0


def test_manifest_scopes_readiness_to_its_own_commit():
    led = _all_physical_pass(OLD)
    m = build_release_candidate_manifest(branch="master", commit=NEW, db_version=28,
                                         rule_engine_version="46.0", automated_tests_passed=10347,
                                         automated_tests_failed=0, bench_total=67, bench_passed=67,
                                         bench_ready=True, ledger=led, operationally_granted=True)
    assert m.readiness.readiness != ManualUatReadiness.OPERATIONALLY_CERTIFIED
    # per-area results in the manifest are scoped to NEW → the OLD passes show as not_run
    statuses = {r["area"]: r["status"] for r in m.manual_results}
    for a in required_physical_live_areas():
        assert statuses[a] == "not_run"


def test_code_change_does_not_inherit_certification():
    # certified at OLD, then the candidate advances to NEW (a code change) → certification not inherited
    led = _all_physical_pass(OLD)
    at_old = evaluate_manual_uat_readiness(automated_tests_passed=True, bench_ready=True, ledger=led,
                                           operationally_granted=True, active_candidate_commit=OLD)
    at_new = evaluate_manual_uat_readiness(automated_tests_passed=True, bench_ready=True, ledger=led,
                                           operationally_granted=True, active_candidate_commit=NEW)
    assert at_old.readiness == ManualUatReadiness.OPERATIONALLY_CERTIFIED
    assert at_new.readiness != ManualUatReadiness.OPERATIONALLY_CERTIFIED


def test_area_shows_not_run_for_new_candidate_after_change():
    led = ManualUatLedger().append(make_observation("physical_tts", ManualUatStatus.PASS,
                                                     candidate_commit=OLD))
    assert led.status_of("physical_tts", OLD) == ManualUatStatus.PASS
    assert led.status_of("physical_tts", NEW) == ManualUatStatus.NOT_RUN


def test_failed_area_stays_failed_until_explicit_retest_same_candidate():
    led = ManualUatLedger().append(make_observation("keyboard_ptt", ManualUatStatus.FAIL,
                                                     candidate_commit=NEW))
    assert led.status_of("keyboard_ptt", NEW) == ManualUatStatus.FAIL
    # a PASS recorded against a DIFFERENT candidate must not clear the NEW-candidate FAIL
    led = led.append(make_observation("keyboard_ptt", ManualUatStatus.PASS, candidate_commit=OLD))
    assert led.status_of("keyboard_ptt", NEW) == ManualUatStatus.FAIL
    # only an explicit PASS retest for the SAME candidate clears it
    led = led.append(make_observation("keyboard_ptt", ManualUatStatus.PASS, candidate_commit=NEW))
    assert led.status_of("keyboard_ptt", NEW) == ManualUatStatus.PASS


def test_supersede_is_within_same_candidate_scope():
    led = ManualUatLedger()
    led = led.append(make_observation("physical_tts", ManualUatStatus.FAIL, candidate_commit=OLD))
    led = led.append(make_observation("physical_tts", ManualUatStatus.PASS, candidate_commit=NEW))
    a_new = led.active("physical_tts", NEW)
    # the NEW observation does not supersede the OLD one (different candidate scope)
    assert not a_new.supersedes
    # both remain in the viewable history
    assert len(led.history("physical_tts")) == 2


def test_historical_evidence_viewable_but_not_counted():
    led = _all_physical_pass(OLD)
    # history is fully viewable
    assert all(len(led.history(a)) == 1 for a in required_physical_live_areas())
    assert set(led.candidates()) == {OLD}
    # but nothing counts for NEW
    assert all(led.status_of(a, NEW) == ManualUatStatus.NOT_RUN for a in required_physical_live_areas())


def test_no_optimistic_fallback_blank_candidate():
    # evidence stamped with a real commit does NOT count for a blank/unknown candidate
    led = _all_physical_pass(OLD)
    r = evaluate_manual_uat_readiness(automated_tests_passed=True, bench_ready=True, ledger=led,
                                      operationally_granted=True, active_candidate_commit="")
    assert r.readiness != ManualUatReadiness.OPERATIONALLY_CERTIFIED


def test_every_observation_records_candidate_commit():
    o = make_observation("physical_tts", ManualUatStatus.PASS, candidate_commit="ecf922c")
    assert o.candidate_commit == "ecf922c"
    assert o.to_dict()["candidate_commit"] == "ecf922c"


def test_repo_identity_resolves_running_commit():
    from data.repo_identity import resolve_repo_commit, resolve_repo_branch, short_commit
    import subprocess
    sha = resolve_repo_commit(".")
    # match `git rev-parse HEAD` exactly
    expected = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    assert sha == expected
    assert short_commit(sha) == expected[:7]
    assert resolve_repo_branch(".")  # a branch name is present in this checkout


def test_repo_identity_defensive_on_non_repo(tmp_path):
    from data.repo_identity import resolve_repo_commit, resolve_repo_branch
    assert resolve_repo_commit(tmp_path) == ""
    assert resolve_repo_branch(tmp_path) == ""
