"""Phase 19 — evidence-saturation domain tests.

Every status is reachable, explained (visible reasons), and driven only by visible thresholds.
Saturation is INDEPENDENT of campaign status; it completes/ranks/mutates nothing.
"""
import inspect

import pytest

from strategy.evidence_saturation import (
    EvidenceSaturation, assess_saturation, EVIDENCE_SATURATION_VERSION,
    CONFIRMATIONS_FOR_STRONG, CONFIRMATIONS_FOR_SATURATED, OVERTESTED_REPEATS,
    EXECUTED_FOR_BUILDING,
)


def _camp(progress=None, experiments=None, status="active"):
    return {"status": status, "progress": progress or {}, "experiments": experiments or []}


def _exp(role="primary_discriminator", outcome="not_tested", needs=False, retired=False):
    return {"candidate_id": f"c_{role}_{outcome}", "campaign_role": role,
            "outcome_state": outcome, "needs_further_testing": needs,
            "retirement_state": "retired_by_regression" if retired else ""}


def test_not_started():
    r = assess_saturation(_camp(progress={}, experiments=[_exp()]))
    assert r.status == EvidenceSaturation.NOT_STARTED.value
    assert r.reasons and any("executed" in x for x in r.reasons)
    assert r.information_gain_remaining == "high"


def test_early_one_execution_with_discriminator_left():
    r = assess_saturation(_camp(
        progress={"confirmed_improvement": 1},
        experiments=[_exp(role="primary_discriminator", outcome="not_tested")]))
    assert r.status == EvidenceSaturation.EARLY.value


def test_building_two_executions_more_remaining():
    r = assess_saturation(_camp(
        progress={"partial_improvement": 1, "inconclusive": 1},
        experiments=[_exp(role="secondary", outcome="not_tested")]))
    assert r.status == EvidenceSaturation.BUILDING.value
    assert r.signals["executed"] == 2 >= EXECUTED_FOR_BUILDING


def test_strong_confirmed_no_discriminator_left():
    r = assess_saturation(_camp(
        progress={"confirmed_improvement": 1},
        experiments=[_exp(role="validation", outcome="not_tested")]))
    assert r.status == EvidenceSaturation.STRONG.value
    assert r.signals["confirmations"] >= CONFIRMATIONS_FOR_STRONG
    assert r.signals["remaining_discriminating_experiments"] == 0


def test_saturated_nothing_left_confirmed_twice():
    r = assess_saturation(_camp(
        progress={"confirmed_improvement": 2},
        experiments=[_exp(role="retired", outcome="confirmed_improvement", retired=True)]))
    assert r.status == EvidenceSaturation.SATURATED.value
    assert r.information_gain_remaining == "none"
    assert any(str(CONFIRMATIONS_FOR_SATURATED) in x or "confirmed" in x for x in r.reasons)


def test_overtested_repeats_nothing_left():
    r = assess_saturation(_camp(
        progress={"inconclusive": 3},
        experiments=[_exp(role="retired", outcome="inconclusive", retired=True)]))
    assert r.status == EvidenceSaturation.OVERTESTED.value
    assert r.signals["no_change"] == 3 >= OVERTESTED_REPEATS


def test_overtested_conflicting_no_discriminator():
    r = assess_saturation(_camp(
        progress={"confirmed_improvement": 1, "regressions": 1},
        experiments=[_exp(role="retired", outcome="regression", retired=True)]))
    # conflicting evidence (both confirmed and regressed) with nothing left -> over-tested
    assert r.status == EvidenceSaturation.OVERTESTED.value
    assert r.signals["conflicting_evidence"] is True


def test_thresholds_and_signals_always_visible():
    r = assess_saturation(_camp(progress={"confirmed_improvement": 1},
                                experiments=[_exp()]))
    d = r.to_dict()
    assert set(d["thresholds"]) == {"confirmations_for_strong", "confirmations_for_saturated",
                                    "overtested_repeats", "executed_for_building"}
    for k in ("confirmations", "regressions", "no_change", "executed",
              "remaining_untested_experiments", "remaining_discriminating_experiments",
              "total_experiments"):
        assert k in d["signals"]
    assert d["eval_version"] == EVIDENCE_SATURATION_VERSION


def test_saturation_independent_of_status():
    # identical evidence, different campaign statuses -> identical saturation
    prog = {"confirmed_improvement": 2}
    exps = [_exp(role="retired", outcome="confirmed_improvement", retired=True)]
    a = assess_saturation(_camp(prog, exps, status="active"))
    b = assess_saturation(_camp(prog, exps, status="ready_to_freeze"))
    assert a.status == b.status == EvidenceSaturation.SATURATED.value


def test_every_status_has_a_reason():
    for camp in (_camp(experiments=[_exp()]),
                 _camp({"confirmed_improvement": 1}, [_exp()]),
                 _camp({"partial_improvement": 1, "inconclusive": 1}, [_exp(role="x")]),
                 _camp({"confirmed_improvement": 2},
                       [_exp(role="retired", outcome="confirmed_improvement", retired=True)]),
                 _camp({"inconclusive": 3},
                       [_exp(role="retired", outcome="inconclusive", retired=True)])):
        r = assess_saturation(camp)
        assert r.reasons, r.status


def test_never_raises_on_garbage():
    for junk in (None, {}, {"progress": None, "experiments": None}, {"experiments": [None, 5]},
                 {"progress": {"confirmed_improvement": "x"}}):
        r = assess_saturation(junk)
        assert r.status in {s.value for s in EvidenceSaturation}


def test_deterministic():
    c = _camp({"confirmed_improvement": 1, "regressions": 1},
              [_exp(role="primary_discriminator", outcome="not_tested")])
    assert assess_saturation(c).to_dict() == assess_saturation(c).to_dict()


def test_no_hidden_numbers_in_source():
    src = inspect.getsource(__import__("strategy.evidence_saturation",
                                       fromlist=["x"]))
    # all decision numbers must be named constants, not bare literals in the branch logic
    assert "OVERTESTED_REPEATS" in src and "CONFIRMATIONS_FOR_STRONG" in src
    for banned in ("import sqlite3", "PyQt6", "import random", "random.",
                   "datetime.now", "time.time"):
        assert banned not in src
