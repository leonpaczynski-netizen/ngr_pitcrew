"""Engineering-Brain Phase 4 — canonical lap-validity authority tests (pure)."""
from __future__ import annotations

from pathlib import Path

import pytest

from strategy.engineering_lap_validity import (
    LapValidityStatus, LapPurpose, evaluate_engineering_lap, evaluate_session_laps,
    policy_for, R_PIT_LAP, R_OUT_LAP, R_OFF_TRACK, R_INCOMPLETE, R_PACE_OUTLIER,
    R_SETUP_MISMATCH, R_LAYOUT_MISMATCH, ENG_LAP_VALIDITY_VERSION,
)

ROOT = Path(__file__).resolve().parents[1]


def _lap(**kw):
    base = {"id": 1, "lap_num": 3, "session_id": 10, "lap_time_ms": 95000,
            "is_pit_lap": 0, "is_out_lap": 0, "off_track_count": 0, "track": "Fuji"}
    base.update(kw)
    return base


# 1
def test_valid_clean_engineering_lap():
    v = evaluate_engineering_lap(_lap(), best_lap_ms=94000, expected_track="Fuji")
    assert v.status == LapValidityStatus.VALID and v.accepted
    assert v.track_layout_confidence == "high"
    assert v.eval_version == ENG_LAP_VALIDITY_VERSION


# 2
def test_out_lap_rejected():
    v = evaluate_engineering_lap(_lap(lap_num=1, is_out_lap=1))
    assert v.status == LapValidityStatus.INVALID
    assert R_OUT_LAP in v.rejection_reasons


# 3
def test_in_lap_rejected():
    v = evaluate_engineering_lap(_lap(is_in_lap=1))
    assert not v.accepted and v.is_in_lap


# 4
def test_pit_lap_rejected():
    v = evaluate_engineering_lap(_lap(is_pit_lap=1))
    assert R_PIT_LAP in v.rejection_reasons


# 5
def test_incomplete_lap_rejected():
    v = evaluate_engineering_lap(_lap(lap_time_ms=0))
    assert v.primary_rejection_reason == R_INCOMPLETE
    assert v.lap_time_plausible == "no"


# 6
def test_off_track_rejected():
    v = evaluate_engineering_lap(_lap(off_track_count=2))
    assert R_OFF_TRACK in v.rejection_reasons


# 7
def test_major_incident_rejected():
    v = evaluate_engineering_lap(_lap(incident=1))
    assert v.incident and not v.accepted


# 8
def test_missing_telemetry_limitation():
    v = evaluate_engineering_lap(_lap(), telemetry_sample_count=0)
    assert v.telemetry_completeness == "missing"
    assert v.status == LapValidityStatus.VALID_WITH_LIMITATIONS


# 9
def test_setup_mismatch_rejected():
    v = evaluate_engineering_lap(_lap(), setup_id="A", expected_setup_id="B")
    assert v.primary_rejection_reason == R_SETUP_MISMATCH
    assert v.setup_identity_confidence == "low"


# 10
def test_track_layout_mismatch_rejected():
    v = evaluate_engineering_lap(_lap(track="Spa"), expected_track="Fuji")
    assert R_LAYOUT_MISMATCH in v.rejection_reasons


# 11
def test_valid_with_limitations():
    v = evaluate_engineering_lap(
        _lap(off_track_count=1), purpose=LapPurpose.PRACTICE_PATTERN)
    assert v.status == LapValidityStatus.VALID_WITH_LIMITATIONS


# 12
def test_purpose_specific_policy():
    # race strategy tolerates a pace outlier + off-track that engineering rejects
    lap = _lap(lap_time_ms=110000, off_track_count=1)
    eng = evaluate_engineering_lap(lap, best_lap_ms=95000,
                                   purpose=LapPurpose.SETUP_ENGINEERING)
    strat = evaluate_engineering_lap(lap, best_lap_ms=95000,
                                     purpose=LapPurpose.RACE_STRATEGY)
    assert eng.status == LapValidityStatus.INVALID
    assert strat.accepted
    assert policy_for(LapPurpose.RACE_STRATEGY).reject_pace_outlier is False


# 13
def test_all_rejection_reasons_retained():
    v = evaluate_engineering_lap(
        _lap(is_pit_lap=1, off_track_count=3, lap_time_ms=130000),
        setup_id="A", expected_setup_id="B", best_lap_ms=95000)
    assert R_SETUP_MISMATCH in v.rejection_reasons
    assert R_PIT_LAP in v.rejection_reasons
    assert R_OFF_TRACK in v.rejection_reasons
    assert len(v.rejection_reasons) >= 3


# 14
def test_deterministic_result():
    a = evaluate_engineering_lap(_lap(), best_lap_ms=94000)
    b = evaluate_engineering_lap(_lap(), best_lap_ms=94000)
    assert a.to_dict() == b.to_dict()


# 15
def test_no_ordinary_missing_evidence_raises():
    assert evaluate_engineering_lap("not a row").status == LapValidityStatus.UNRESOLVED
    assert evaluate_engineering_lap({}).status in (
        LapValidityStatus.INVALID, LapValidityStatus.UNRESOLVED)


# session summary + pace outlier (self-consistent)
def test_session_summary_and_pace_outlier():
    rows = [_lap(lap_num=1, lap_time_ms=99000, is_out_lap=1),
            _lap(lap_num=2, lap_time_ms=95000, id=2),
            _lap(lap_num=3, lap_time_ms=95200, id=3),
            _lap(lap_num=4, lap_time_ms=95100, id=4),
            _lap(lap_num=5, lap_time_ms=130000, id=5),   # pace outlier
            _lap(lap_num=6, lap_time_ms=95300, id=6)]
    verds, summ = evaluate_session_laps(rows, purpose=LapPurpose.SETUP_ENGINEERING)
    assert summ.valid_laps == 4
    assert summ.rejected_laps == 2
    assert R_PACE_OUTLIER in summ.rejection_distribution
    assert summ.valid_lap_numbers == (2, 3, 4, 6)


# property: adding an invalid lap cannot improve readiness (usable-lap count)
def test_adding_invalid_lap_cannot_increase_usable():
    rows = [_lap(lap_num=n, lap_time_ms=95000, id=n) for n in (1, 2, 3)]
    _, s1 = evaluate_session_laps(rows)
    _, s2 = evaluate_session_laps(rows + [_lap(lap_num=4, is_pit_lap=1, id=4)])
    assert s2.usable_laps == s1.usable_laps


def test_order_independent_summary():
    rows = [_lap(lap_num=n, lap_time_ms=95000 + n, id=n) for n in (2, 3, 4, 5)]
    _, a = evaluate_session_laps(rows)
    _, b = evaluate_session_laps(list(reversed(rows)))
    assert a.valid_laps == b.valid_laps and a.rejected_laps == b.rejected_laps


# safety: purity
def test_module_pure():
    src = (ROOT / "strategy" / "engineering_lap_validity.py").read_text(encoding="utf-8")
    for banned in ("PyQt6", "PyQt5", "from ui.", "import sqlite3",
                   "from data.session_db", "requests", "anthropic", "openai",
                   "datetime.now", "random"):
        assert banned not in src, banned
