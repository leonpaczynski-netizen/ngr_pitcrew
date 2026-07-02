"""
Group 37 — Relative-Compound Tyre Degradation Point (pure unit tests)

Tests for strategy/relative_degradation.py::compute_relative_degradation.

All tests are deterministic — no API calls, no Qt, no file I/O.

Coverage
--------
* Skipped-tier: RS+RH present, RM absent → RS compares to RH baseline
* Next-harder priority: RS+RM+RH all present → RS uses RM (not RH)
* Boundary: run at laps 5&6 → optimal=4 (D=5, D-1=4)
* Never-degrades: RS never crosses harder baseline → optimal=0, not_yet_degraded=True
* Outlier: lap below baseline between two >= laps does NOT trigger run
* Single compound → cliff_detection
* Hardest compound → cliff_detection
* Wet compound → cliff_detection
* Mean-baseline contract: harder_baseline_ms == mean of harder compound's laps
* Degrades from lap 1 (laps 1&2 over baseline) → optimal=0 (not viable)
* RS crosses RH baseline at laps 8&9 → optimal_stint_race=7
* RS crosses RM baseline at laps 6&7 → optimal=5
"""
from __future__ import annotations

import statistics
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from strategy.relative_degradation import compute_relative_degradation


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ms(s: float) -> float:
    """Convert seconds to milliseconds (float)."""
    return s * 1000.0


# ---------------------------------------------------------------------------
# Skipped-tier test (RS+RH present, RM absent)
# ---------------------------------------------------------------------------

class TestSkippedTier:
    """RS+RH practised, RM skipped.
    RS crosses RH baseline first at laps 8&9 → RS optimal_stint_race=7.
    """

    def _make_sequences(self) -> dict[str, list[float]]:
        # RH mean = 97.000s = 97000ms
        rh_laps = [_ms(97.0)] * 5

        # RS: laps 1-7 under 97s, laps 8 & 9 at/above 97s
        rs_laps = (
            [_ms(90.0)] * 7        # laps 1-7: fast, well below RH baseline
            + [_ms(97.1), _ms(97.2)]  # laps 8-9: above RH mean
        )
        return {"RS": rs_laps, "RH": rh_laps}

    def test_rs_optimal_stint_race_is_7(self):
        result = compute_relative_degradation(self._make_sequences())
        assert result["RS"]["optimal_stint_race"] == 7

    def test_rs_method_is_relative_baseline(self):
        result = compute_relative_degradation(self._make_sequences())
        assert result["RS"]["degradation_method"] == "relative_baseline"

    def test_rs_harder_baseline_ms_equals_mean_of_rh(self):
        seqs = self._make_sequences()
        result = compute_relative_degradation(seqs)
        expected_baseline = statistics.mean(seqs["RH"])
        assert abs(result["RS"]["harder_baseline_ms"] - expected_baseline) < 1e-6

    def test_rh_uses_cliff_detection_as_hardest_present(self):
        result = compute_relative_degradation(self._make_sequences())
        assert result["RH"]["degradation_method"] == "cliff_detection"

    def test_rh_harder_baseline_ms_is_none(self):
        result = compute_relative_degradation(self._make_sequences())
        assert result["RH"]["harder_baseline_ms"] is None

    def test_rs_not_yet_degraded_is_false(self):
        result = compute_relative_degradation(self._make_sequences())
        assert result["RS"]["not_yet_degraded"] is False


# ---------------------------------------------------------------------------
# Next-harder priority (RS+RM+RH all present, RS uses RM not RH)
# ---------------------------------------------------------------------------

class TestNextHarderPriority:
    """RS+RM+RH all practised. RS crosses RM baseline first at laps 6&7 → optimal=5."""

    def _make_sequences(self) -> dict[str, list[float]]:
        # RM mean = 95.000s = 95000ms
        rm_laps = [_ms(95.0)] * 5

        # RH mean = 97.000s = 97000ms
        rh_laps = [_ms(97.0)] * 5

        # RS: laps 1-5 under 95s, laps 6&7 at/above RM mean
        rs_laps = (
            [_ms(90.0)] * 5          # laps 1-5: fast
            + [_ms(95.1), _ms(95.2)] # laps 6-7: above RM mean, below RH mean
        )
        return {"RS": rs_laps, "RM": rm_laps, "RH": rh_laps}

    def test_rs_optimal_stint_is_5(self):
        result = compute_relative_degradation(self._make_sequences())
        assert result["RS"]["optimal_stint_race"] == 5

    def test_rs_uses_rm_baseline_not_rh(self):
        seqs = self._make_sequences()
        result = compute_relative_degradation(seqs)
        expected_rm_baseline = statistics.mean(seqs["RM"])
        assert abs(result["RS"]["harder_baseline_ms"] - expected_rm_baseline) < 1e-6

    def test_rs_method_is_relative_baseline(self):
        result = compute_relative_degradation(self._make_sequences())
        assert result["RS"]["degradation_method"] == "relative_baseline"

    def test_rm_compares_to_rh_baseline(self):
        seqs = self._make_sequences()
        result = compute_relative_degradation(seqs)
        expected_rh_baseline = statistics.mean(seqs["RH"])
        assert abs(result["RM"]["harder_baseline_ms"] - expected_rh_baseline) < 1e-6

    def test_rm_method_is_relative_baseline(self):
        result = compute_relative_degradation(self._make_sequences())
        assert result["RM"]["degradation_method"] == "relative_baseline"


# ---------------------------------------------------------------------------
# Boundary test: run at laps 5&6 → optimal=4
# ---------------------------------------------------------------------------

class TestBoundaryLap5And6:
    """Run starts at laps 5&6 → D=5 → optimal_stint_race = D-1 = 4."""

    def _make_sequences(self) -> dict[str, list[float]]:
        rh_laps = [_ms(97.0)] * 5

        # RS: laps 1-4 fast (under baseline), laps 5&6 at/above baseline
        rs_laps = (
            [_ms(90.0)] * 4
            + [_ms(97.1), _ms(97.2)]
        )
        return {"RS": rs_laps, "RH": rh_laps}

    def test_optimal_is_4(self):
        result = compute_relative_degradation(self._make_sequences())
        assert result["RS"]["optimal_stint_race"] == 4

    def test_method_is_relative_baseline(self):
        result = compute_relative_degradation(self._make_sequences())
        assert result["RS"]["degradation_method"] == "relative_baseline"


# ---------------------------------------------------------------------------
# Never degrades: RS never crosses harder baseline
# ---------------------------------------------------------------------------

class TestNeverDegrades:
    """RS never crosses the harder baseline → optimal=0, not_yet_degraded=True, confidence=low."""

    def _make_sequences(self) -> dict[str, list[float]]:
        rh_laps = [_ms(97.0)] * 5
        # RS stays fast throughout, never reaches 97s
        rs_laps = [_ms(90.0)] * 6
        return {"RS": rs_laps, "RH": rh_laps}

    def test_optimal_is_0(self):
        result = compute_relative_degradation(self._make_sequences())
        assert result["RS"]["optimal_stint_race"] == 0

    def test_not_yet_degraded_is_true(self):
        result = compute_relative_degradation(self._make_sequences())
        assert result["RS"]["not_yet_degraded"] is True

    def test_confidence_is_low(self):
        result = compute_relative_degradation(self._make_sequences())
        assert result["RS"]["confidence"] == "low"

    def test_method_is_relative_baseline(self):
        result = compute_relative_degradation(self._make_sequences())
        assert result["RS"]["degradation_method"] == "relative_baseline"

    def test_harder_baseline_ms_is_set(self):
        seqs = self._make_sequences()
        result = compute_relative_degradation(seqs)
        expected = statistics.mean(seqs["RH"])
        assert result["RS"]["harder_baseline_ms"] is not None
        assert abs(result["RS"]["harder_baseline_ms"] - expected) < 1e-6


# ---------------------------------------------------------------------------
# Outlier test: single outlier lap below baseline does NOT trigger run
# ---------------------------------------------------------------------------

class TestOutlierBreaksRun:
    """Lap 5 >= baseline, lap 6 < baseline (outlier), lap 7 >= baseline.
    With consecutive_laps=2, the run at laps 5 & 6 is broken by lap 6 < baseline.
    Should NOT trigger at lap 5. Needs a genuine 2-consecutive-lap run later or none.
    """

    def _make_sequences(self) -> dict[str, list[float]]:
        rh_laps = [_ms(97.0)] * 5  # RH mean = 97000ms

        # RS:
        # laps 1-4: fast (below baseline)
        # lap 5: 97.1s >= baseline
        # lap 6: 90.0s < baseline (outlier — breaks the run)
        # lap 7: 97.2s >= baseline (but no consecutive partner after)
        rs_laps = [
            _ms(90.0),  # lap 1
            _ms(90.0),  # lap 2
            _ms(90.0),  # lap 3
            _ms(90.0),  # lap 4
            _ms(97.1),  # lap 5 >= baseline
            _ms(90.0),  # lap 6 < baseline — BREAKS THE RUN
            _ms(97.2),  # lap 7 >= baseline (only 1, no pair)
        ]
        return {"RS": rs_laps, "RH": rh_laps}

    def test_does_not_trigger_at_lap_5(self):
        """optimal_stint_race must NOT be 4 (which would indicate run triggered at lap 5)."""
        result = compute_relative_degradation(self._make_sequences())
        # If it triggered at lap 5, optimal = D-1 = 4
        assert result["RS"]["optimal_stint_race"] != 4

    def test_not_triggered_is_0_or_later(self):
        """Either not_yet_degraded=True (optimal=0) or a run was found starting at lap 7+."""
        result = compute_relative_degradation(self._make_sequences())
        rs = result["RS"]
        # No 2-consecutive run exists, so should be not_yet_degraded
        assert rs["not_yet_degraded"] is True
        assert rs["optimal_stint_race"] == 0

    def test_method_is_relative_baseline(self):
        result = compute_relative_degradation(self._make_sequences())
        assert result["RS"]["degradation_method"] == "relative_baseline"


class TestOutlierWithLaterRun:
    """Similar outlier, but a genuine 2-consecutive run exists later (laps 8&9).
    Ensures the outlier at lap 6 does NOT trigger at lap 5, but lap 8 does trigger.
    """

    def _make_sequences(self) -> dict[str, list[float]]:
        rh_laps = [_ms(97.0)] * 5

        rs_laps = [
            _ms(90.0),  # lap 1
            _ms(90.0),  # lap 2
            _ms(90.0),  # lap 3
            _ms(90.0),  # lap 4
            _ms(97.1),  # lap 5 >= baseline
            _ms(90.0),  # lap 6 < baseline — breaks the run
            _ms(90.0),  # lap 7 < baseline
            _ms(97.3),  # lap 8 >= baseline
            _ms(97.4),  # lap 9 >= baseline — first genuine consecutive run
        ]
        return {"RS": rs_laps, "RH": rh_laps}

    def test_triggers_at_lap_8_not_lap_5(self):
        """D=8 → optimal = D-1 = 7."""
        result = compute_relative_degradation(self._make_sequences())
        assert result["RS"]["optimal_stint_race"] == 7

    def test_not_yet_degraded_is_false(self):
        result = compute_relative_degradation(self._make_sequences())
        assert result["RS"]["not_yet_degraded"] is False


# ---------------------------------------------------------------------------
# Single compound → cliff_detection
# ---------------------------------------------------------------------------

class TestSingleCompound:
    def test_single_rm_uses_cliff_detection(self):
        seqs = {"RM": [_ms(95.0)] * 6}
        result = compute_relative_degradation(seqs)
        assert result["RM"]["degradation_method"] == "cliff_detection"

    def test_single_rm_optimal_is_0(self):
        seqs = {"RM": [_ms(95.0)] * 6}
        result = compute_relative_degradation(seqs)
        assert result["RM"]["optimal_stint_race"] == 0

    def test_single_rm_harder_baseline_is_none(self):
        seqs = {"RM": [_ms(95.0)] * 6}
        result = compute_relative_degradation(seqs)
        assert result["RM"]["harder_baseline_ms"] is None

    def test_single_rm_not_yet_degraded_is_false(self):
        seqs = {"RM": [_ms(95.0)] * 6}
        result = compute_relative_degradation(seqs)
        assert result["RM"]["not_yet_degraded"] is False


# ---------------------------------------------------------------------------
# Hardest practised compound → cliff_detection
# ---------------------------------------------------------------------------

class TestHardestCompound:
    """RH is the hardest Racing compound — no harder compound to compare against."""

    def _make_sequences(self) -> dict[str, list[float]]:
        return {
            "RS": [_ms(90.0)] * 5,
            "RH": [_ms(97.0)] * 6,
        }

    def test_rh_uses_cliff_detection(self):
        result = compute_relative_degradation(self._make_sequences())
        assert result["RH"]["degradation_method"] == "cliff_detection"

    def test_rh_harder_baseline_is_none(self):
        result = compute_relative_degradation(self._make_sequences())
        assert result["RH"]["harder_baseline_ms"] is None

    def test_rh_optimal_is_0(self):
        result = compute_relative_degradation(self._make_sequences())
        assert result["RH"]["optimal_stint_race"] == 0


# ---------------------------------------------------------------------------
# Wet compound → cliff_detection
# ---------------------------------------------------------------------------

class TestWetCompound:
    """IM (Intermediate) and HW (Heavy Wet) must always use cliff_detection."""

    def test_im_uses_cliff_detection_with_dry_peers(self):
        seqs = {
            "RM": [_ms(95.0)] * 5,
            "IM": [_ms(100.0)] * 5,
        }
        result = compute_relative_degradation(seqs)
        assert result["IM"]["degradation_method"] == "cliff_detection"

    def test_im_harder_baseline_is_none(self):
        seqs = {
            "RM": [_ms(95.0)] * 5,
            "IM": [_ms(100.0)] * 5,
        }
        result = compute_relative_degradation(seqs)
        assert result["IM"]["harder_baseline_ms"] is None

    def test_hw_uses_cliff_detection(self):
        seqs = {
            "RM": [_ms(95.0)] * 5,
            "HW": [_ms(105.0)] * 5,
        }
        result = compute_relative_degradation(seqs)
        assert result["HW"]["degradation_method"] == "cliff_detection"

    def test_im_alone_uses_cliff_detection(self):
        seqs = {"IM": [_ms(100.0)] * 5}
        result = compute_relative_degradation(seqs)
        assert result["IM"]["degradation_method"] == "cliff_detection"


# ---------------------------------------------------------------------------
# Mean-baseline contract
# ---------------------------------------------------------------------------

class TestMeanBaselineContract:
    """harder_baseline_ms must equal the arithmetic mean of the harder compound's laps.

    Includes slower laps — not best, not median, but arithmetic mean.
    """

    def test_harder_baseline_equals_mean_including_slow_laps(self):
        # RH laps include a slower lap at the end — mean must include it
        rh_laps = [_ms(97.0), _ms(97.0), _ms(97.0), _ms(99.0), _ms(98.0)]
        rs_laps = [_ms(90.0)] * 3 + [_ms(97.5), _ms(97.6)]
        seqs = {"RS": rs_laps, "RH": rh_laps}
        result = compute_relative_degradation(seqs)
        expected_mean = statistics.mean(rh_laps)
        assert abs(result["RS"]["harder_baseline_ms"] - expected_mean) < 1e-6

    def test_harder_baseline_is_mean_not_best(self):
        # Best RH lap is 96.0s but mean is higher due to slower laps
        rh_laps = [_ms(96.0), _ms(98.0), _ms(99.0), _ms(98.0), _ms(97.0)]
        rs_laps = [_ms(90.0)] * 3 + [_ms(97.5), _ms(97.6)]
        seqs = {"RS": rs_laps, "RH": rh_laps}
        result = compute_relative_degradation(seqs)
        expected_mean = statistics.mean(rh_laps)
        best_rh = min(rh_laps)
        # Must use mean, not best
        assert result["RS"]["harder_baseline_ms"] != best_rh
        assert abs(result["RS"]["harder_baseline_ms"] - expected_mean) < 1e-6


# ---------------------------------------------------------------------------
# Degrades from lap 1 (laps 1&2 at/above baseline) → optimal=0 (not viable)
# ---------------------------------------------------------------------------

class TestDegradeFromLap1:
    """Consecutive run starts at lap 1 (laps 1&2 both >= baseline).
    D=1 → optimal_stint_race = D-1 = 0 (not viable). Do NOT force minimum of 1.
    """

    def _make_sequences(self) -> dict[str, list[float]]:
        rh_laps = [_ms(97.0)] * 5
        # RS is ABOVE the baseline from the very first lap
        rs_laps = [_ms(97.5), _ms(97.6)] + [_ms(97.7)] * 4
        return {"RS": rs_laps, "RH": rh_laps}

    def test_optimal_is_0(self):
        result = compute_relative_degradation(self._make_sequences())
        assert result["RS"]["optimal_stint_race"] == 0

    def test_not_yet_degraded_is_false(self):
        """Degrades from lap 1 — it DID degrade, not "not yet"."""
        result = compute_relative_degradation(self._make_sequences())
        assert result["RS"]["not_yet_degraded"] is False

    def test_method_is_relative_baseline(self):
        result = compute_relative_degradation(self._make_sequences())
        assert result["RS"]["degradation_method"] == "relative_baseline"


# ---------------------------------------------------------------------------
# Confidence levels
# ---------------------------------------------------------------------------

class TestConfidenceLevels:
    def _rh_laps(self) -> list[float]:
        return [_ms(97.0)] * 5

    def test_high_confidence_with_8_or_more_laps(self):
        # RS: 8 laps, crosses threshold at laps 7&8
        rs_laps = [_ms(90.0)] * 6 + [_ms(97.1), _ms(97.2)]
        result = compute_relative_degradation({"RS": rs_laps, "RH": self._rh_laps()})
        assert result["RS"]["confidence"] == "high"

    def test_medium_confidence_with_4_to_7_laps(self):
        # RS: 5 laps, crosses threshold at laps 4&5
        rs_laps = [_ms(90.0)] * 3 + [_ms(97.1), _ms(97.2)]
        result = compute_relative_degradation({"RS": rs_laps, "RH": self._rh_laps()})
        assert result["RS"]["confidence"] == "medium"

    def test_low_confidence_with_fewer_than_4_laps(self):
        # RS: 3 laps total — never crosses threshold
        rs_laps = [_ms(90.0)] * 3
        result = compute_relative_degradation({"RS": rs_laps, "RH": self._rh_laps()})
        assert result["RS"]["confidence"] == "low"


# ---------------------------------------------------------------------------
# Empty input
# ---------------------------------------------------------------------------

class TestEmptyInput:
    def test_empty_sequences_returns_empty_dict(self):
        result = compute_relative_degradation({})
        assert result == {}

    def test_compound_with_empty_laps_handled(self):
        # RS has data, RM has no laps
        seqs = {"RS": [_ms(90.0)] * 5, "RM": []}
        # Should not crash; RS has no harder compound with valid baseline
        result = compute_relative_degradation(seqs)
        assert "RS" in result
        # RM is present in lap_sequences with empty list — compound_means won't include it
        # so RM won't be a valid harder baseline for RS
        # RS should fall back to cliff detection since RM has no valid mean
        assert result["RS"]["degradation_method"] == "cliff_detection"
