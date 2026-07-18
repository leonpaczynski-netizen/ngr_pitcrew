"""Holistic brain — Phase 3: cross-session setup verdict."""
from __future__ import annotations

from strategy.setup_session_verdict import (
    SetupRunSummary, compare_setups, SetupOverall, FeedbackAgreement,
)


def _run(label, laps, best, avg, apex, spin=1.0, lock=1.0):
    return SetupRunSummary(label=label, laps=laps, best_ms=best, avg_ms=avg,
                           per_corner_apex_kmh=apex, avg_wheelspin=spin,
                           avg_lockup=lock)


def test_improved_verdict_with_reasons():
    prev = _run("R rev1", 5, 90000, 90800,
                {"Turn 1": 120, "Turn 4": 95, "Turn 7": 140}, spin=2.0)
    cur = _run("R rev2", 5, 89690, 90400,
               {"Turn 1": 118, "Turn 4": 101, "Turn 7": 144}, spin=1.1)
    v = compare_setups(
        prev, cur,
        changes=[{"setting": "Rear ARB", "from": 5, "to": 4},
                 {"setting": "Front wing", "from": 3, "to": 5}],
        feedback_vs_previous="better")
    assert v.overall is SetupOverall.IMPROVED
    assert v.best_lap_delta_ms == -310
    # T4 +6, T7 +4 gained; T1 -2 lost.
    names_better = {c.corner_name for c in v.better_corners}
    assert "Turn 4" in names_better and "Turn 7" in names_better
    assert "Turn 1" in {c.corner_name for c in v.worse_corners}
    assert v.feedback_agreement is FeedbackAgreement.AGREES
    joined = " ".join(v.reasons)
    assert "Rear ARB" in joined and "wheelspin down" in joined.lower()
    assert "telemetry agrees" in joined.lower()


def test_worsened_verdict():
    prev = _run("R rev1", 5, 89500, 90000, {"Turn 1": 120})
    cur = _run("R rev2", 5, 90200, 90900, {"Turn 1": 116})
    v = compare_setups(prev, cur)
    assert v.overall is SetupOverall.WORSENED
    assert v.best_lap_delta_ms == 700


def test_contradicting_feedback():
    prev = _run("R rev1", 5, 89500, 90000, {"Turn 1": 120})
    cur = _run("R rev2", 5, 90300, 90800, {"Turn 1": 118})  # slower
    v = compare_setups(prev, cur, feedback_vs_previous="better")
    assert v.overall is SetupOverall.WORSENED
    assert v.feedback_agreement is FeedbackAgreement.CONTRADICTS
    assert any("opposite" in r.lower() for r in v.reasons)


def test_insufficient_laps():
    prev = _run("R rev1", 1, 90000, 90000, {})
    cur = _run("R rev2", 5, 89000, 90000, {})
    v = compare_setups(prev, cur)
    assert v.overall is SetupOverall.INSUFFICIENT
    assert any("not enough laps" in r.lower() for r in v.reasons)


def test_mixed_verdict():
    # Best improved but average worsened -> mixed.
    prev = _run("R rev1", 5, 90000, 90000, {"Turn 1": 120})
    cur = _run("R rev2", 5, 89800, 90400, {"Turn 1": 120})
    v = compare_setups(prev, cur)
    assert v.overall is SetupOverall.MIXED


def test_headline():
    prev = _run("R rev1", 5, 90000, 90500, {})
    cur = _run("R rev2", 5, 89600, 90100, {})
    v = compare_setups(prev, cur)
    assert "best lap -0.40s" in v.headline()
    assert "improved" in v.headline()
