"""Sprint 8 — deterministic race strategy: ranking, determinism, untested exclusion.

The deterministic total-race-time engine already exists (generate_candidates /
score_candidates / recommend_strategy). This locks in the Sprint 8 guarantees:
  * identical inputs → identical output;
  * ranked by total race time (ascending);
  * UNTESTED compounds never enter a recommended/legal candidate — they may only
    appear as unvalidated alternatives.
"""
from __future__ import annotations

from strategy.race_strategy_evidence import RaceStrategyEvidence
from strategy.race_strategy_candidates import generate_candidates, legal_candidates
from strategy.race_strategy_scorer import score_candidates, recommend_strategy


def _evidence(**over):
    base = dict(
        car_id=1, track="fuji", layout_id="fuji__full", race_laps=20,
        fuel_multiplier=1.0, tyre_multiplier=1.0, refuel_rate_lps=5.0,
        pit_loss_seconds=22.0, starting_fuel_pct=100.0,
        available_compounds=("RS", "RM"),
        lap_time_samples=tuple([100.0] * 10),
        fuel_use_samples=tuple([2.5] * 10),
        tyre_wear_samples=tuple([0.1] * 10),
        compound_samples={"RS": [98.0] * 8, "RM": [99.0] * 8},
    )
    base.update(over)
    return RaceStrategyEvidence(**base)


def test_determinism_identical_inputs_identical_output():
    ev = _evidence()
    a = score_candidates(generate_candidates(ev), ev)
    b = score_candidates(generate_candidates(ev), ev)
    assert [s.candidate_id for s in a] == [s.candidate_id for s in b]
    assert [s.estimated_total_time_seconds for s in a] == [s.estimated_total_time_seconds for s in b]
    r1 = recommend_strategy(ev)
    r2 = recommend_strategy(ev)
    assert r1 == r2


def test_ranked_by_total_race_time_ascending():
    ev = _evidence()
    scored = score_candidates(generate_candidates(ev), ev)
    assert scored, "expected at least one scored candidate"
    times = [s.estimated_total_time_seconds for s in scored]
    assert times == sorted(times)
    assert scored[0].rank == 1


def test_untested_compound_never_in_a_legal_candidate():
    # RH is available but has NO measured samples → untested.
    ev = _evidence(available_compounds=("RS", "RM", "RH"),
                   compound_samples={"RS": [98.0] * 8, "RM": [99.0] * 8})
    legal = legal_candidates(generate_candidates(ev))
    assert legal, "expected legal candidates"
    for c in legal:
        assert "RH" not in c.compound_plan, f"untested RH leaked into {c.candidate_id}: {c.compound_plan}"


def test_tested_second_compound_still_used_for_switch():
    # When a tested alternative exists, a compound-switch candidate may use it.
    ev = _evidence(available_compounds=("RS", "RM"),
                   compound_samples={"RS": [98.0] * 8, "RM": [99.0] * 8})
    cands = generate_candidates(ev)
    switch = [c for c in cands if "compound_switch" in c.candidate_id]
    # A switch candidate, if generated, only uses tested compounds.
    for c in switch:
        assert set(c.compound_plan) <= {"RS", "RM"}


def test_no_candidates_when_race_length_unknown():
    ev = _evidence(race_laps=0, race_duration_minutes=0.0)
    assert generate_candidates(ev) == []
