"""Engineering-Brain Phase 5 — canonical lap-validity caller migration (12.6)."""
from __future__ import annotations

from pathlib import Path

import pytest

from strategy.practice_capture import resolve_clean_lap
from strategy.engineering_lap_validity import (
    evaluate_engineering_lap, LapPurpose, policy_for, LapValidityStatus)

ROOT = Path(__file__).resolve().parents[1]


# --- behaviour preserved (compatibility adapter over the authority) ---------
def test_valid_within_ratio_clean():
    assert resolve_clean_lap(95000, 94000) is True


def test_pace_outlier_rejected():
    assert resolve_clean_lap(110000, 95000) is False


def test_no_best_is_provisionally_clean():
    assert resolve_clean_lap(95000, 0) is True


def test_invalid_flag_rejected():
    assert resolve_clean_lap(95000, 94000, valid=False) is False


def test_zero_time_rejected():
    assert resolve_clean_lap(0, 94000) is False


def test_custom_outlier_ratio():
    # 96000 within 95000*1.05 (=99750) → clean; 100000 outside → not clean
    assert resolve_clean_lap(96000, 95000, outlier_ratio=1.05) is True
    assert resolve_clean_lap(100000, 95000, outlier_ratio=1.05) is False


# --- migration: resolve_clean_lap delegates to the ONE authority ------------
def test_resolve_clean_lap_delegates_to_authority():
    src = (ROOT / "strategy" / "practice_capture.py").read_text(encoding="utf-8")
    assert "engineering_lap_validity" in src
    assert "evaluate_engineering_lap" in src
    assert "LapPurpose.PRACTICE_PATTERN" in src


def test_perfect_lap_pipeline_uses_resolve_clean_lap():
    # the perfect-lap live path calls resolve_clean_lap (now authority-backed)
    src = (ROOT / "strategy" / "perfect_lap_pipeline.py").read_text(encoding="utf-8")
    assert "resolve_clean_lap" in src


# --- purpose-specific policies intact ---------------------------------------
def test_setup_engineering_strict():
    v = evaluate_engineering_lap({"lap_time_ms": 110000, "off_track_count": 1},
                                 purpose=LapPurpose.SETUP_ENGINEERING, best_lap_ms=95000)
    assert v.status == LapValidityStatus.INVALID    # pace outlier + off-track


def test_outcome_comparison_strict():
    assert policy_for(LapPurpose.OUTCOME_COMPARISON).reject_pace_outlier is True


def test_practice_pattern_policy():
    p = policy_for(LapPurpose.PRACTICE_PATTERN)
    assert p.reject_pace_outlier is False and p.off_track_limitation_max == 1


def test_perfect_lap_reference_policy():
    assert policy_for(LapPurpose.PERFECT_LAP_REFERENCE).pace_outlier_ratio == 1.05


def test_race_strategy_fuel_focused_policy():
    p = policy_for(LapPurpose.RACE_STRATEGY)
    assert p.reject_pace_outlier is False and p.reject_off_track is False


def test_race_strategy_tolerates_what_engineering_rejects():
    lap = {"lap_time_ms": 110000, "off_track_count": 1}
    eng = evaluate_engineering_lap(lap, purpose=LapPurpose.SETUP_ENGINEERING, best_lap_ms=95000)
    strat = evaluate_engineering_lap(lap, purpose=LapPurpose.RACE_STRATEGY, best_lap_ms=95000)
    assert eng.status == LapValidityStatus.INVALID and strat.accepted


def test_rejection_reasons_preserved():
    v = evaluate_engineering_lap({"lap_time_ms": 0, "is_pit_lap": 1})
    assert v.rejection_reasons and v.primary_rejection_reason
