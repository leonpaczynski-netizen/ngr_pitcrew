"""Tests for data/recommendation_scoring.py — OFR-1 pure scoring logic.

Covers:
  - Module purity: no PyQt6, sqlite3, open(), tyre_radius
  - classify_why_text keyword detection + None-safety
  - aggregate_lap_window clean/compound/rates
  - compute_verdict_and_confidence: honesty gates, verdict matrix, boundaries,
    mixed-signal→neutral, attribution split, feedback bonus, lap deductions
  - format_performance_block: threshold filtering, insufficient_data omitted,
    empty→'', malformed rows safe
"""
from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from data.recommendation_scoring import (
    LapWindow,
    ScoringResult,
    aggregate_lap_window,
    classify_why_text,
    compute_verdict_and_confidence,
    format_performance_block,
)


# ---------------------------------------------------------------------------
# Module purity scan
# ---------------------------------------------------------------------------

def _load_source() -> str:
    return (REPO / "data" / "recommendation_scoring.py").read_text(encoding="utf-8")


def _get_import_names(src: str) -> set[str]:
    """Return the set of top-level module names imported in the source."""
    tree = ast.parse(src)
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                names.add(node.module.split(".")[0])
    return names


def test_module_no_pyqt6():
    """recommendation_scoring.py must not import PyQt6."""
    imports = _get_import_names(_load_source())
    assert "PyQt6" not in imports, "recommendation_scoring must not import PyQt6"


def test_module_no_sqlite3():
    """recommendation_scoring.py must not import sqlite3."""
    imports = _get_import_names(_load_source())
    assert "sqlite3" not in imports, "recommendation_scoring must not import sqlite3"


def test_module_no_open():
    """recommendation_scoring.py must not use open() for file I/O."""
    src = _load_source()
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id == "open":
                pytest.fail("recommendation_scoring must not call open()")


def test_module_no_tyre_radius():
    """recommendation_scoring.py must not reference tyre_radius fields."""
    src = _load_source()
    assert "tyre_radius" not in src, "tyre_radius must not appear in recommendation_scoring"


# ---------------------------------------------------------------------------
# classify_why_text
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("why,expected", [
    ("understeer at apex", "handling"),
    ("too much oversteer on exit", "handling"),
    ("wheelspin under acceleration", "handling"),
    ("improve traction out of slow corners", "handling"),
    ("better stability under braking", "handling"),
    ("lock-up at T1 braking zone", "handling"),
    ("lockup under trail braking", "handling"),
    ("locking rear wheels", "handling"),
    ("snap oversteer", "handling"),
    ("bottoming on kerbs", "handling"),
    ("improve rotation mid-corner", "handling"),
    ("better grip overall", "handling"),
    ("reduce lap time by 0.5 seconds", "laptime"),
    ("improve overall speed", "laptime"),
    ("UNDERSTEER at apex", "handling"),         # case-insensitive
    ("", "laptime"),                             # empty string
    ("   ", "laptime"),                          # whitespace only
])
def test_classify_why_text_keywords(why, expected):
    assert classify_why_text(why) == expected


def test_classify_why_text_none_safe():
    """classify_why_text must not raise on None."""
    result = classify_why_text(None)  # type: ignore[arg-type]
    assert result == "laptime"


# ---------------------------------------------------------------------------
# aggregate_lap_window helpers
# ---------------------------------------------------------------------------

def _make_lap(
    lap_time_ms: int = 90_000,
    is_pit_lap: int = 0,
    is_out_lap: int = 0,
    compound: str = "RM",
    lock_up_count: int = 1,
    wheelspin_count: int = 2,
    oversteer_count: int = 0,
    oversteer_throttle_on: int = 0,
    bottoming_count: int = 0,
    brake_consistency_m: float = 5.0,
) -> dict:
    return {
        "lap_time_ms": lap_time_ms,
        "is_pit_lap": is_pit_lap,
        "is_out_lap": is_out_lap,
        "compound": compound,
        "lock_up_count": lock_up_count,
        "wheelspin_count": wheelspin_count,
        "oversteer_count": oversteer_count,
        "oversteer_throttle_on": oversteer_throttle_on,
        "bottoming_count": bottoming_count,
        "brake_consistency_m": brake_consistency_m,
    }


def test_aggregate_lap_window_excludes_pit():
    laps = [
        _make_lap(lap_time_ms=80_000),
        _make_lap(lap_time_ms=85_000, is_pit_lap=1),
    ]
    w = aggregate_lap_window(laps)
    assert w.clean_count == 1
    assert w.best_clean_ms == 80_000


def test_aggregate_lap_window_excludes_out():
    laps = [
        _make_lap(lap_time_ms=80_000),
        _make_lap(lap_time_ms=95_000, is_out_lap=1),
    ]
    w = aggregate_lap_window(laps)
    assert w.clean_count == 1


def test_aggregate_lap_window_majority_compound():
    laps = [
        _make_lap(compound="RM"),
        _make_lap(compound="RM"),
        _make_lap(compound="RS"),
    ]
    w = aggregate_lap_window(laps)
    assert w.compound == "RM"


def test_aggregate_lap_window_mixed_compound_empty():
    """50/50 split → no clear majority → compound=''."""
    laps = [_make_lap(compound="RM"), _make_lap(compound="RS")]
    w = aggregate_lap_window(laps)
    assert w.compound == ""


def test_aggregate_lap_window_rates():
    laps = [
        _make_lap(lock_up_count=2, wheelspin_count=4),
        _make_lap(lock_up_count=0, wheelspin_count=2),
    ]
    w = aggregate_lap_window(laps)
    assert w.avg_lock_up == pytest.approx(1.0)
    assert w.avg_wheelspin == pytest.approx(3.0)


def test_aggregate_lap_window_empty_input():
    w = aggregate_lap_window([])
    assert w.clean_count == 0
    assert w.best_clean_ms == 0


def test_aggregate_lap_window_missing_keys():
    """Rows with missing keys must not raise."""
    w = aggregate_lap_window([{"lap_time_ms": 90_000}])
    assert w.clean_count == 1  # no is_pit/is_out → treated as clean


# ---------------------------------------------------------------------------
# Helpers for compute_verdict tests
# ---------------------------------------------------------------------------

def _window(clean_count: int = 5, best_ms: int = 90_000, **kwargs) -> LapWindow:
    """Build a minimal LapWindow for testing."""
    defaults = dict(
        laps=[],
        clean_count=clean_count,
        compound="RM",
        best_clean_ms=best_ms,
        avg_lock_up=kwargs.pop("avg_lock_up", 1.0),
        avg_wheelspin=kwargs.pop("avg_wheelspin", 1.0),
        avg_oversteer=kwargs.pop("avg_oversteer", 0.0),
        avg_oversteer_throttle=kwargs.pop("avg_oversteer_throttle", 0.0),
        avg_bottoming=kwargs.pop("avg_bottoming", 0.0),
        avg_brake_consistency=kwargs.pop("avg_brake_consistency", 5.0),
    )
    return LapWindow(**defaults)


def _rec(
    rec_id: int = 1,
    before_metrics: dict | None = None,
    rec_text: str = "{}",
) -> dict:
    bm = json.dumps(before_metrics) if before_metrics is not None else "{}"
    return {
        "id": rec_id,
        "before_metrics": bm,
        "recommendation_text": rec_text,
    }


# ---------------------------------------------------------------------------
# Honesty gates
# ---------------------------------------------------------------------------

def test_gate_no_before_metrics_no_rows():
    """Gate 1: missing before_metrics and 0 clean laps → insufficient_data."""
    before = _window(clean_count=0, best_ms=0)
    after  = _window(clean_count=5, best_ms=89_000)
    result = compute_verdict_and_confidence(_rec(), before, after)
    assert result.verdict == "insufficient_data"
    assert result.confidence == 0.0


def test_gate_before_metrics_present_but_no_rows():
    """Gate 1 passes if before_metrics is present even with 0 before lap rows."""
    before = _window(clean_count=0, best_ms=0)
    after  = _window(clean_count=5, best_ms=89_000)
    rec    = _rec(before_metrics={"best_lap_ms": 90_000, "lap_count": 5})
    # After window meets the 3-lap threshold; before has 0 rows → gate 1 passes.
    # But gate 2 fires: before_window.clean_count=0 < 3.
    result = compute_verdict_and_confidence(rec, before, after)
    assert result.verdict == "insufficient_data"
    assert result.confidence == 0.0


def test_gate2_before_too_few_laps():
    """Gate 2: < 3 clean laps before → insufficient_data."""
    before = _window(clean_count=2, best_ms=90_000)
    after  = _window(clean_count=5, best_ms=89_000)
    rec    = _rec(before_metrics={"best_lap_ms": 90_000})
    result = compute_verdict_and_confidence(rec, before, after)
    assert result.verdict == "insufficient_data"


def test_gate2_after_too_few_laps():
    """Gate 2: < 3 clean laps after → insufficient_data."""
    before = _window(clean_count=5, best_ms=90_000)
    after  = _window(clean_count=1, best_ms=89_000)
    rec    = _rec(before_metrics={"best_lap_ms": 90_000})
    result = compute_verdict_and_confidence(rec, before, after)
    assert result.verdict == "insufficient_data"


# ---------------------------------------------------------------------------
# Verdict matrix — laptime target
# ---------------------------------------------------------------------------

def test_laptime_improved_boundary():
    """Δt exactly −201 ms → improved (strictly below −200)."""
    before = _window(clean_count=5, best_ms=90_000)
    after  = _window(clean_count=5, best_ms=89_799)  # 90000 - 89799 = 201 improvement
    rec    = _rec()
    result = compute_verdict_and_confidence(rec, before, after)
    assert result.verdict == "improved"


def test_laptime_at_minus_200_not_improved():
    """Δt exactly −200 ms → NOT improved (must be < −200, not ≤)."""
    before = _window(clean_count=5, best_ms=90_000)
    after  = _window(clean_count=5, best_ms=89_800)   # delta = -200
    rec    = _rec()
    result = compute_verdict_and_confidence(rec, before, after)
    assert result.verdict != "improved"


def test_laptime_worsened_boundary():
    """Δt exactly +301 ms → worsened (strictly above +300)."""
    before = _window(clean_count=5, best_ms=90_000)
    after  = _window(clean_count=5, best_ms=90_301)
    rec    = _rec()
    result = compute_verdict_and_confidence(rec, before, after)
    assert result.verdict == "worsened"


def test_laptime_at_300_not_worsened():
    """Δt exactly +300 ms → NOT worsened (must be > +300, not ≥)."""
    before = _window(clean_count=5, best_ms=90_000)
    after  = _window(clean_count=5, best_ms=90_300)
    rec    = _rec()
    result = compute_verdict_and_confidence(rec, before, after)
    assert result.verdict != "worsened"


def test_laptime_neutral():
    """Δt between −200 and +300 → neutral."""
    before = _window(clean_count=5, best_ms=90_000)
    after  = _window(clean_count=5, best_ms=90_100)  # +100 ms
    rec    = _rec()
    result = compute_verdict_and_confidence(rec, before, after)
    assert result.verdict == "neutral"


# ---------------------------------------------------------------------------
# Verdict matrix — handling target
# ---------------------------------------------------------------------------

def _handling_rec() -> dict:
    payload = json.dumps({
        "changes": [
            {"field": "ARB front", "from": 4, "to": 3, "why": "reduce understeer"}
        ]
    })
    return _rec(rec_text=payload)


def test_handling_improved_high_agreement_small_laptime_delta():
    """Handling target: agreement ≥ 0.6 AND Δt ≤ +100 → improved."""
    # All handling metrics improved (lower = better, after < before)
    before = _window(
        clean_count=5, best_ms=90_000,
        avg_lock_up=2.0, avg_wheelspin=3.0,
        avg_oversteer=1.0, avg_oversteer_throttle=0.5,
        avg_bottoming=1.0, avg_brake_consistency=8.0,
    )
    after = _window(
        clean_count=5, best_ms=90_050,   # +50 ms (≤ +100)
        avg_lock_up=1.0, avg_wheelspin=1.5,
        avg_oversteer=0.5, avg_oversteer_throttle=0.2,
        avg_bottoming=0.5, avg_brake_consistency=4.0,
    )
    result = compute_verdict_and_confidence(_handling_rec(), before, after)
    assert result.verdict == "improved"


def test_handling_worsened_low_agreement_positive_delta():
    """Handling target: agreement < 0.3 AND Δt > 0 → worsened."""
    # All handling metrics worsened (higher = worse, after > before)
    before = _window(
        clean_count=5, best_ms=90_000,
        avg_lock_up=0.5, avg_wheelspin=0.5,
        avg_oversteer=0.5, avg_oversteer_throttle=0.1,
        avg_bottoming=0.1, avg_brake_consistency=3.0,
    )
    after = _window(
        clean_count=5, best_ms=90_150,  # +150 ms (> 0, ≤ 300)
        avg_lock_up=2.0, avg_wheelspin=2.0,
        avg_oversteer=2.0, avg_oversteer_throttle=1.0,
        avg_bottoming=1.0, avg_brake_consistency=9.0,
    )
    result = compute_verdict_and_confidence(_handling_rec(), before, after)
    assert result.verdict == "worsened"


def test_handling_neutral_mixed_mid_agreement():
    """Handling target with ~50% agreement and small delta → neutral."""
    before = _window(
        clean_count=5, best_ms=90_000,
        avg_lock_up=1.0, avg_wheelspin=1.0,
        avg_oversteer=1.0, avg_oversteer_throttle=0.0,
        avg_bottoming=0.0, avg_brake_consistency=5.0,
    )
    after = _window(
        clean_count=5, best_ms=90_050,   # neutral
        avg_lock_up=0.5, avg_wheelspin=1.5,   # mixed
        avg_oversteer=0.5, avg_oversteer_throttle=0.0,
        avg_bottoming=0.0, avg_brake_consistency=5.0,
    )
    result = compute_verdict_and_confidence(_handling_rec(), before, after)
    # Agreement = 2/4 relevant = 0.5 → not ≥ 0.6, not < 0.3 → neutral
    assert result.verdict == "neutral"


def test_handling_mixed_signal_laptime_improved_handling_worsened():
    """Mixed signal: Δt < −200 but handling agreement < 0.3 → neutral."""
    before = _window(
        clean_count=5, best_ms=90_000,
        avg_lock_up=0.5, avg_wheelspin=0.5,
        avg_oversteer=0.5, avg_oversteer_throttle=0.1,
        avg_bottoming=0.1, avg_brake_consistency=3.0,
    )
    after = _window(
        clean_count=5, best_ms=89_700,   # −300 ms (lt_improved=True)
        avg_lock_up=2.0, avg_wheelspin=2.0,
        avg_oversteer=2.0, avg_oversteer_throttle=1.0,
        avg_bottoming=1.0, avg_brake_consistency=9.0,
    )
    result = compute_verdict_and_confidence(_handling_rec(), before, after)
    # lt_improved=True but handling_agreement < 0.3 → mixed → neutral
    assert result.verdict == "neutral"


def test_handling_at_100ms_delta_is_eligible():
    """Handling target with Δt exactly +100 ms (≤ +100) is eligible for improved."""
    before = _window(
        clean_count=5, best_ms=90_000,
        avg_lock_up=2.0, avg_wheelspin=2.0,
        avg_oversteer=1.0, avg_oversteer_throttle=0.5,
        avg_bottoming=0.5, avg_brake_consistency=6.0,
    )
    after = _window(
        clean_count=5, best_ms=90_100,   # exactly +100
        avg_lock_up=1.0, avg_wheelspin=1.0,
        avg_oversteer=0.5, avg_oversteer_throttle=0.2,
        avg_bottoming=0.2, avg_brake_consistency=3.0,
    )
    result = compute_verdict_and_confidence(_handling_rec(), before, after)
    assert result.verdict == "improved"


# ---------------------------------------------------------------------------
# Confidence deductions
# ---------------------------------------------------------------------------

def test_confidence_deduction_thin_laps_before():
    """3 clean laps before (shortfall 3 → −0.3) and 6 after → conf deducted vs 6+6 baseline."""
    # Use all-zero handling metrics so no direction-disagree penalty fires.
    before = _window(
        clean_count=3, best_ms=90_000,
        avg_lock_up=0.0, avg_wheelspin=0.0,
        avg_oversteer=0.0, avg_oversteer_throttle=0.0,
        avg_bottoming=0.0, avg_brake_consistency=0.0,
    )
    after = _window(
        clean_count=6, best_ms=89_500,
        avg_lock_up=0.0, avg_wheelspin=0.0,
        avg_oversteer=0.0, avg_oversteer_throttle=0.0,
        avg_bottoming=0.0, avg_brake_consistency=0.0,
    )
    rec    = _rec()
    result = compute_verdict_and_confidence(rec, before, after)
    # verdict should be improved (Δt = −500 < −200)
    assert result.verdict == "improved"
    # conf = 1.0 − 0.3 (before shortfall 3×0.1) − 0.0 (after) = 0.7
    assert result.confidence == pytest.approx(0.7, abs=0.01)


def test_confidence_deduction_thin_laps_both_sides():
    """3 clean laps on each side → conf = 1.0 − 0.3 − 0.3 = 0.4."""
    before = _window(
        clean_count=3, best_ms=90_000,
        avg_lock_up=0.0, avg_wheelspin=0.0,
        avg_oversteer=0.0, avg_oversteer_throttle=0.0,
        avg_bottoming=0.0, avg_brake_consistency=0.0,
    )
    after = _window(
        clean_count=3, best_ms=89_500,
        avg_lock_up=0.0, avg_wheelspin=0.0,
        avg_oversteer=0.0, avg_oversteer_throttle=0.0,
        avg_bottoming=0.0, avg_brake_consistency=0.0,
    )
    rec    = _rec()
    result = compute_verdict_and_confidence(rec, before, after)
    assert result.confidence == pytest.approx(0.4, abs=0.01)


def test_confidence_not_below_zero():
    """Confidence is clamped to [0, 1] — deductions cannot produce negative values."""
    before = _window(clean_count=3, best_ms=90_000)
    after  = _window(clean_count=3, best_ms=89_000)
    rec    = _rec()
    result = compute_verdict_and_confidence(rec, before, after, multi_rec_count=10)
    assert result.confidence >= 0.0


def test_confidence_feedback_bonus():
    """has_driver_feedback=True adds +0.1 before clamping."""
    before = _window(clean_count=6, best_ms=90_000)
    after  = _window(clean_count=6, best_ms=89_500)
    rec    = _rec()

    base_result = compute_verdict_and_confidence(rec, before, after)
    fb_result   = compute_verdict_and_confidence(
        rec, before, after, has_driver_feedback=True
    )
    # Feedback adds 0.1 (clamped at 1.0)
    assert fb_result.confidence == pytest.approx(
        min(1.0, base_result.confidence + 0.1), abs=0.01
    )


def test_confidence_attribution_split():
    """2 recs → confidence ≤ single-rec / 2."""
    before = _window(clean_count=6, best_ms=90_000)
    after  = _window(clean_count=6, best_ms=89_500)
    rec    = _rec()

    single   = compute_verdict_and_confidence(rec, before, after, multi_rec_count=1)
    two_recs = compute_verdict_and_confidence(rec, before, after, multi_rec_count=2)
    assert two_recs.confidence == pytest.approx(single.confidence / 2, abs=0.01)


# ---------------------------------------------------------------------------
# ScoringResult details dict
# ---------------------------------------------------------------------------

def test_scoring_result_details_json_serialisable():
    """ScoringResult.details must be JSON-serialisable."""
    before = _window(clean_count=5, best_ms=90_000)
    after  = _window(clean_count=5, best_ms=89_500)
    rec    = _rec()
    result = compute_verdict_and_confidence(rec, before, after)
    serialised = json.dumps(result.details)   # must not raise
    assert serialised


def test_scoring_result_before_source_documented():
    """Details must document before_source = 'creation_session'."""
    before = _window(clean_count=5, best_ms=90_000)
    after  = _window(clean_count=5, best_ms=89_500)
    rec    = _rec()
    result = compute_verdict_and_confidence(rec, before, after)
    assert result.details.get("before_source") == "creation_session"


# ---------------------------------------------------------------------------
# format_performance_block
# ---------------------------------------------------------------------------

def _scored_rec(
    verdict: str = "improved",
    confidence: float = 0.7,
    rec_id: int = 1,
    details_override: dict | None = None,
) -> dict:
    details = {
        "target": "laptime",
        "delta_ms": -350,
        "before_best_ms": 90_000,
        "after_best_ms": 89_650,
        "before_clean_laps": 5,
        "after_clean_laps": 5,
        "before_compound": "RM",
        "after_compound": "RM",
        "handling_agreement": 0.5,
        "relevant_metrics": 2,
        "improved_metrics": 1,
        "lock_up_before": 1.5,
        "lock_up_after": 0.8,
        "lock_up_delta": -0.7,
        "assumptions_note": "before_session = rec creation session",
    }
    if details_override:
        details.update(details_override)

    rec_text = json.dumps({
        "changes": [
            {
                "field": "ARB front",
                "from": 4,
                "to": 3,
                "why": "reduce understeer",
            }
        ]
    })
    return {
        "id": rec_id,
        "score_verdict": verdict,
        "score_confidence": confidence,
        "score_details": json.dumps(details),
        "recommendation_text": rec_text,
    }


def test_format_performance_block_returns_string():
    recs = [_scored_rec()]
    result = format_performance_block(recs)
    assert isinstance(result, str)
    assert len(result) > 0


def test_format_performance_block_contains_header():
    result = format_performance_block([_scored_rec()])
    assert "Performance of Previous Recommendations" in result


def test_format_performance_block_contains_verdict():
    result = format_performance_block([_scored_rec(verdict="improved", confidence=0.78)])
    assert "improved" in result
    assert "0.78" in result


def test_format_performance_block_contains_change_desc():
    result = format_performance_block([_scored_rec()])
    assert "ARB front" in result


def test_format_performance_block_empty_when_no_recs():
    """Empty input → empty string."""
    assert format_performance_block([]) == ""


def test_format_performance_block_filters_below_threshold():
    """Rec with confidence below threshold is excluded."""
    low_conf = _scored_rec(confidence=0.3)
    result = format_performance_block([low_conf], confidence_threshold=0.5)
    assert result == ""


def test_format_performance_block_threshold_boundary():
    """Exactly at threshold (0.5) is included; 0.499 is excluded."""
    at_threshold = _scored_rec(confidence=0.5)
    just_below   = _scored_rec(confidence=0.499)
    assert format_performance_block([at_threshold], confidence_threshold=0.5) != ""
    assert format_performance_block([just_below], confidence_threshold=0.5) == ""


def test_format_performance_block_omits_insufficient_data():
    """insufficient_data verdict is excluded even if above threshold."""
    rec = _scored_rec(verdict="insufficient_data", confidence=0.9)
    result = format_performance_block([rec])
    assert result == ""


def test_format_performance_block_omits_empty_verdict():
    """Empty verdict is excluded (unscored row)."""
    rec = _scored_rec(verdict="")
    result = format_performance_block([rec])
    assert result == ""


def test_format_performance_block_malformed_row_safe():
    """Malformed rows must not raise and must be silently skipped."""
    malformed = {"score_verdict": None, "score_confidence": "not_a_float", "score_details": "{{{"}
    result = format_performance_block([malformed])
    # Must not raise; malformed rows are skipped → empty
    assert result == ""


def test_format_performance_block_mixed_valid_and_malformed():
    """Valid recs render; malformed ones are silently skipped."""
    recs = [
        {"score_verdict": None, "score_confidence": "bad", "score_details": ""},
        _scored_rec(verdict="improved", confidence=0.8),
    ]
    result = format_performance_block(recs)
    assert "improved" in result


def test_format_performance_block_worsened():
    result = format_performance_block([_scored_rec(verdict="worsened", confidence=0.7)])
    assert "worsened" in result


def test_format_performance_block_neutral():
    result = format_performance_block([_scored_rec(verdict="neutral", confidence=0.6)])
    assert "neutral" in result


def test_format_performance_block_lap_delta_displayed():
    """Lap time delta should appear in the output."""
    result = format_performance_block([_scored_rec()])
    # The details have delta_ms = -350 → -0.35s
    assert "lap" in result.lower()


def test_format_performance_block_never_raises_on_none_input():
    """None input is handled gracefully."""
    result = format_performance_block(None)  # type: ignore[arg-type]
    assert result == ""
