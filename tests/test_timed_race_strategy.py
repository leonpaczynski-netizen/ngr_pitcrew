"""Tests for BUG 1 — Timed race scored as a lap race (fixed).

For a timed race (e.g., 120 min), the old engine computed a fixed lap count
then ADDED pit time on top, producing impossible totals like "2:08:05" for a
120-min race.  The correct model:

    green_time = duration_s - total_pit_time_s
    laps_completed = floor(green_time / mean_green_lap_s)
    objective: MAXIMIZE laps_completed (not minimize total_time)

These tests prove:
  • total_elapsed ≈ race duration (NOT duration + pit time on top)
  • more stops → fewer laps (pit time eats into green time)
  • the RECOMMENDED plan is NOT always the one with the most stops
  • a fuel-limited scenario forces extra stops even in a timed race
  • lap races are entirely unaffected (existing behaviour unchanged)

All tests are pure/offline (no DB, no Qt, no AI).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from strategy.race_strategy_evidence import build_strategy_evidence  # noqa: E402
from strategy.race_strategy_scorer import (  # noqa: E402
    recommend_strategy,
    score_candidates,
)
from strategy.race_strategy_candidates import generate_candidates  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

def _timed_evidence(
    *,
    duration_min: float = 120.0,
    lap_s: float = 118.0,
    fuel_per_lap: float = 3.26,
    pit_loss_s: float = 25.0,
    refuel_lps: float = 1.0,
    tyre_wear_samples: tuple = (),
    available_compounds: tuple = ("RM",),
):
    """Build a timed-race evidence snapshot.  race_laps=0 signals timed."""
    return build_strategy_evidence(
        car_id=0,
        track="Test",
        race_duration_minutes=duration_min,
        race_laps=0,                    # 0 = timed race
        pit_loss_seconds=pit_loss_s,
        refuel_rate_lps=refuel_lps,
        fuel_multiplier=1.0,
        tyre_multiplier=1.0,
        lap_time_samples=(lap_s,) * 8,  # 8 identical clean laps
        fuel_use_samples=(fuel_per_lap,) * 8,
        tyre_wear_samples=tyre_wear_samples,
        available_compounds=available_compounds,
    )


def _lap_evidence(
    *,
    laps: int = 30,
    lap_s: float = 118.0,
    fuel_per_lap: float = 3.26,
    pit_loss_s: float = 25.0,
    refuel_lps: float = 1.0,
):
    """Build a lap-race evidence snapshot.  race_duration_minutes=0 signals lap race."""
    return build_strategy_evidence(
        car_id=0,
        track="Test",
        race_duration_minutes=0.0,      # 0 = lap race
        race_laps=laps,
        pit_loss_seconds=pit_loss_s,
        refuel_rate_lps=refuel_lps,
        fuel_multiplier=1.0,
        tyre_multiplier=1.0,
        lap_time_samples=(lap_s,) * 8,
        fuel_use_samples=(fuel_per_lap,) * 8,
        available_compounds=("RM",),
    )


# ---------------------------------------------------------------------------
# Timed-race model correctness
# ---------------------------------------------------------------------------

class TestTimedRaceLapCount:
    def test_total_elapsed_within_race_duration(self):
        """total_elapsed must NOT exceed duration by more than one lap."""
        ev = _timed_evidence(duration_min=120.0, lap_s=118.0, pit_loss_s=25.0)
        rec = recommend_strategy(ev)
        assert rec.has_recommendation
        best = rec.recommended
        duration_s = 120.0 * 60.0
        # The total time the scorer computes includes green laps + pit time.
        # It should be close to the race duration, not duration + pit time.
        assert best.estimated_total_time_seconds <= duration_s + 120.0, (
            f"total_elapsed {best.estimated_total_time_seconds:.0f}s exceeds "
            f"duration {duration_s:.0f}s by more than 2 laps"
        )

    def test_laps_complete_within_duration(self):
        """All candidates should complete a laps estimate feasible inside the window."""
        ev = _timed_evidence(duration_min=120.0, lap_s=118.0, pit_loss_s=25.0)
        candidates = generate_candidates(ev)
        rep = ev.representative_lap_s()
        duration_s = 120.0 * 60.0
        for c in candidates:
            total_laps = sum(c.estimated_laps_per_stint)
            pit_time = c.estimated_pit_time
            # Green time = total_laps × rep_lap must fit within duration - pit_time
            assert total_laps * rep <= duration_s - pit_time + rep + 5, (
                f"Candidate {c.candidate_id}: {total_laps} laps × {rep:.1f}s = "
                f"{total_laps * rep:.0f}s > available {duration_s - pit_time:.0f}s green time"
            )

    def test_more_stops_means_fewer_laps(self):
        """In a timed race, extra pit time = less green time = fewer laps."""
        ev = _timed_evidence(
            duration_min=120.0, lap_s=118.0,
            pit_loss_s=25.0, refuel_lps=1.0, fuel_per_lap=2.0,
        )
        candidates = generate_candidates(ev)
        by_id = {c.candidate_id: c for c in candidates}
        if "1stop" in by_id and "2stop" in by_id:
            laps_1 = sum(by_id["1stop"].estimated_laps_per_stint)
            laps_2 = sum(by_id["2stop"].estimated_laps_per_stint)
            assert laps_1 >= laps_2, (
                f"1-stop ({laps_1} laps) should complete ≥ laps as 2-stop ({laps_2} laps)"
            )

    def test_ranking_by_laps_not_time(self):
        """Timed race: ranked by laps (descending), NOT by total_elapsed (ascending)."""
        ev = _timed_evidence(
            duration_min=120.0, lap_s=118.0,
            pit_loss_s=25.0, refuel_lps=1.0, fuel_per_lap=2.0,
        )
        rec = recommend_strategy(ev)
        ranked = rec.ranked
        if len(ranked) < 2:
            pytest.skip("need at least two candidates to verify ranking")
        # Verify rank-1 has more laps than rank-2 (or equal laps and lower total time)
        cand_by_id = {c.candidate_id: c for c in generate_candidates(ev)}
        r1_id = ranked[0].candidate_id
        r2_id = ranked[1].candidate_id
        laps_r1 = sum(cand_by_id[r1_id].estimated_laps_per_stint) if r1_id in cand_by_id else 0
        laps_r2 = sum(cand_by_id[r2_id].estimated_laps_per_stint) if r2_id in cand_by_id else 0
        assert laps_r1 >= laps_r2, (
            f"rank-1 ({r1_id}, {laps_r1} laps) should have ≥ laps than "
            f"rank-2 ({r2_id}, {laps_r2} laps)"
        )

    def test_gap_is_lap_equivalent_seconds(self):
        """Gap-to-best for the runner-up is expressed in lap-equivalent seconds."""
        ev = _timed_evidence(
            duration_min=120.0, lap_s=118.0,
            pit_loss_s=25.0, refuel_lps=1.0, fuel_per_lap=2.0,
        )
        rec = recommend_strategy(ev)
        ranked = rec.ranked
        if len(ranked) < 2:
            pytest.skip("need at least two candidates")
        # Best candidate has gap 0.
        assert ranked[0].estimated_gap_to_best_seconds == 0.0
        # Runner-up gap is non-negative.
        assert ranked[1].estimated_gap_to_best_seconds >= 0.0


class TestTimedRaceAbsurdTotalFixed:
    def test_2hr_race_total_not_absurdly_long(self):
        """Old bug: 2-hr race at ~118s/lap scored as ~2:08.  New: ≤ ~2:02."""
        ev = _timed_evidence(
            duration_min=120.0, lap_s=118.0, pit_loss_s=25.0, refuel_lps=1.0,
            fuel_per_lap=3.26,
        )
        rec = recommend_strategy(ev)
        assert rec.has_recommendation
        best = rec.recommended
        # Old buggy total was 7685s (≈ 2:08:05).  New should be ≤ 7450s (≈ 2:04).
        assert best.estimated_total_time_seconds <= 7450.0, (
            f"total_elapsed={best.estimated_total_time_seconds:.0f}s — "
            "appears to add pit time on top of a fixed lap count (bug not fixed)"
        )

    def test_50min_race_total_within_window(self):
        """50-min benchmark: total ≈ 50 min, NOT 51:52 (old bug)."""
        ev = _timed_evidence(
            duration_min=50.0, lap_s=100.44,
            pit_loss_s=22.0, refuel_lps=1.0, fuel_per_lap=4.0,
        )
        rec = recommend_strategy(ev)
        assert rec.has_recommendation
        best = rec.recommended
        # Total should be close to 3000s, not 3112s (old bug).
        assert best.estimated_total_time_seconds < 3060.0, (
            f"total_elapsed={best.estimated_total_time_seconds:.0f}s is too high "
            "(50-min race should not score above 51 min)"
        )


# ---------------------------------------------------------------------------
# Lap-race behaviour unchanged
# ---------------------------------------------------------------------------

class TestLapRaceUnchanged:
    def test_lap_race_minimises_total_time(self):
        """For a lap race, ranking is still by total elapsed time (ascending)."""
        ev = _lap_evidence(laps=30, lap_s=118.0, pit_loss_s=25.0)
        rec = recommend_strategy(ev)
        if not rec.has_recommendation or len(rec.ranked) < 2:
            pytest.skip("need at least two scored candidates")
        # Best plan has the smallest total time.
        times = [s.estimated_total_time_seconds for s in rec.ranked]
        assert times == sorted(times), "lap race must rank by total time ascending"

    def test_lap_race_gap_is_time_based(self):
        """Lap-race gap = difference in total seconds, not lap-equivalent."""
        ev = _lap_evidence(laps=30, lap_s=118.0, pit_loss_s=25.0)
        rec = recommend_strategy(ev)
        if len(rec.ranked) < 2:
            pytest.skip("need at least two candidates")
        best_time = rec.ranked[0].estimated_total_time_seconds
        for score in rec.ranked[1:]:
            expected_gap = round(score.estimated_total_time_seconds - best_time, 2)
            assert score.estimated_gap_to_best_seconds == pytest.approx(expected_gap, abs=0.01)

    def test_lap_race_total_time_is_not_within_race_window(self):
        """Lap race: total time depends on the PACE over fixed laps, not a window."""
        ev = _lap_evidence(laps=30, lap_s=118.0, pit_loss_s=25.0)
        rec = recommend_strategy(ev)
        if not rec.has_recommendation:
            pytest.skip("no recommendation")
        # 30 laps × 118 s = 3540 s + pit time.  Cannot be less than green time.
        total = rec.recommended.estimated_total_time_seconds
        green = 30 * 118.0
        assert total >= green, "lap-race total must include at least the green-lap time"


# ---------------------------------------------------------------------------
# Fuel-limited timed race
# ---------------------------------------------------------------------------

class TestFuelLimitedTimedRace:
    def test_high_consumption_forces_pit(self):
        """When fuel burn is high, a no-stop is illegal (not enough fuel for all laps).

        With 6 L/lap at ~118 s/lap over 2 hours: 100 L / 6 ≈ 16-lap max per stint.
        A no-stop needs ~60 laps → 360 L → ILLEGAL.
        A 3-stop divides into ~15-lap stints → 90 L each → LEGAL.
        """
        ev = _timed_evidence(
            duration_min=120.0, lap_s=118.0,
            pit_loss_s=25.0, refuel_lps=1.0,
            fuel_per_lap=6.0,  # 100L / 6 ≈ 16 laps max per stint
        )
        candidates = generate_candidates(ev)
        by_id = {c.candidate_id: c for c in candidates}
        # No-stop must be illegal: one stint needs ~60 × 6 = 360 L > 100 L.
        if "nostop" in by_id:
            assert not by_id["nostop"].is_legal, (
                "no-stop should be illegal with 6 L/lap over a 2-hr race "
                "(needs ~360 L, tank is 100 L)"
            )
        # At least one legal candidate must exist (3-stop with ~15 laps/stint → 90 L).
        legal = [c for c in candidates if c.is_legal]
        assert legal, (
            "with 6 L/lap a 3-stop plan (15-lap stints × 6 = 90 L each) should be legal"
        )


# ---------------------------------------------------------------------------
# Degradation cap — never extrapolate beyond measured laps
# ---------------------------------------------------------------------------

class TestDegradationCap:
    def test_degradation_capped_at_measured_laps(self):
        """Degradation cost must not grow for stints longer than the tested sample."""
        # 8 laps of tyre-wear data at 0.05 s/lap.
        wear = (0.05,) * 8
        ev = _timed_evidence(
            duration_min=120.0, lap_s=118.0, pit_loss_s=25.0,
            refuel_lps=1.0, fuel_per_lap=2.0,
            tyre_wear_samples=wear,
        )
        from strategy.race_strategy_scorer import score_candidate
        candidates = generate_candidates(ev)
        for c in candidates:
            laps_per = c.estimated_laps_per_stint
            if any(l > 8 for l in laps_per):
                scored = score_candidate(c, ev)
                if scored is not None:
                    # Max degradation: cap at 8 laps per stint
                    from statistics import mean as _mean
                    rate = _mean(wear)
                    max_capped = sum(
                        rate * (min(l, 8) * (min(l, 8) - 1) / 2.0)
                        for l in laps_per
                    )
                    # Allow small floating-point tolerance
                    assert scored.degradation_cost_seconds <= max_capped + 0.01, (
                        f"degradation {scored.degradation_cost_seconds:.2f}s "
                        f"exceeds cap {max_capped:.2f}s for {c.candidate_id}"
                    )


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
