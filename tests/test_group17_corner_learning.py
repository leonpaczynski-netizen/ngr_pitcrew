"""Tests for Group 16 (user naming) / Group 17 (internal) — Corner-Level Telemetry Learning.

Covers:
  - CornerIssue dataclass and helpers
  - PATH A detection from event_positions_json
  - PATH B detection from frame dicts
  - Issue merge (PATH A + PATH B)
  - Fix verification (fixed/improved/unchanged/worse/not_enough_data)
  - AI prompt summary builder
  - Setup advice bridge
  - SessionDB schema v4 (corner_issues table)
  - Safe degradation with missing data
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from dataclasses import dataclass

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from data.corner_learning import (
    CornerIssue,
    ISSUE_TYPES,
    SETUP_ADVICE_MAP,
    FIX_STATUS_FIXED,
    FIX_STATUS_IMPROVED,
    FIX_STATUS_UNCHANGED,
    FIX_STATUS_WORSE,
    FIX_STATUS_INSUFFICIENT,
    _corner_id_from_xyz,
    detect_issues_from_lap_records,
    detect_corner_events_from_frames,
    detect_issues_from_frame_data,
    merge_issues,
    verify_fix,
    build_corner_summary_for_prompt,
    get_setup_advice,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _make_laps(positions_per_lap: list[dict], n_laps: int | None = None) -> list[dict]:
    """Build synthetic lap records with event_positions_json for testing."""
    if n_laps is None:
        n_laps = len(positions_per_lap)
    result = []
    for i, pos_dict in enumerate(positions_per_lap):
        result.append({
            "lap_num": i + 1,
            "event_positions_json": json.dumps(pos_dict),
        })
    return result


def _issue(corner_id="P500_-200", issue_type="brake_lock", lap_count=3, total_laps=5,
           car_id=1, track="Suzuka") -> CornerIssue:
    return CornerIssue(
        car_id=car_id, track=track, corner_id=corner_id,
        lap_count=lap_count, total_laps=total_laps,
        issue_type=issue_type, phase="braking",
        severity=0.3, confidence=0.8,
        evidence="test", session_id=1, detected_at="2026-01-01T00:00:00+00:00",
    )


# ---------------------------------------------------------------------------
# 1. CornerIssue model and constants
# ---------------------------------------------------------------------------
class TestCornerIssueModel:
    def test_dataclass_fields_accessible(self):
        iss = _issue()
        assert iss.car_id == 1
        assert iss.track == "Suzuka"
        assert iss.corner_id == "P500_-200"
        assert iss.issue_type == "brake_lock"

    def test_issue_types_set_contains_expected(self):
        for t in ("brake_lock", "rear_wheelspin", "poor_drive_out",
                  "exit_gear_too_low", "early_limiter_on_straight"):
            assert t in ISSUE_TYPES

    def test_corner_id_from_xyz_bucket_snap(self):
        assert _corner_id_from_xyz(450.0, -180.0) == "P400_-200"
        assert _corner_id_from_xyz(550.0, 250.0) == "P600_200"

    def test_corner_id_from_xyz_exact_boundary(self):
        assert _corner_id_from_xyz(500.0, -200.0) == "P500_-200"

    def test_corner_id_from_xyz_negative_x(self):
        cid = _corner_id_from_xyz(-350.0, 100.0)
        assert cid == "P-400_100"


# ---------------------------------------------------------------------------
# 2. PATH A — detect from event_positions_json
# ---------------------------------------------------------------------------
class TestDetectFromLapRecords:
    def test_no_laps_returns_empty(self):
        result = detect_issues_from_lap_records([], car_id=1, track="T")
        assert result == []

    def test_single_event_below_threshold_ignored(self):
        # 1 event on 1 of 5 laps = 20% < 30% AND count 1 < 3 → below both thresholds
        laps = _make_laps([
            {"lock_up": [[500, 10, -200]]},
            {"lock_up": []},
            {"lock_up": []},
            {"lock_up": []},
            {"lock_up": []},
        ])
        result = detect_issues_from_lap_records(laps, car_id=1, track="T")
        assert result == []  # only 1 lap with event, total=5, 20% < 30%

    def test_three_laps_same_corner_flagged(self):
        pos = [500, 10, -200]
        laps = _make_laps([
            {"lock_up": [pos]},
            {"lock_up": [pos]},
            {"lock_up": [pos]},
        ])
        result = detect_issues_from_lap_records(laps, car_id=1, track="T")
        assert len(result) == 1
        assert result[0].issue_type == "brake_lock"
        assert result[0].lap_count == 3

    def test_30_percent_threshold_triggers_with_fewer_laps(self):
        # 3 laps, event on 1 lap: 33% ≥ 30% so should be detected
        # But also below _MIN_LAP_COUNT=3, so 30% with < 3 occurrences... let's check
        # Actually: 3/10 = 30%, 3 laps is the min count so it would need 3 laps
        # Let's do: 10 laps total, event on 3 → 30% with 3 laps = flagged
        pos = [500, 10, -200]
        laps = _make_laps(
            [{"lock_up": [pos]}] * 3 + [{"lock_up": []}] * 7
        )
        result = detect_issues_from_lap_records(laps, car_id=1, track="T")
        assert len(result) == 1

    def test_two_events_below_threshold_not_flagged(self):
        pos = [500, 10, -200]
        laps = _make_laps(
            [{"lock_up": [pos]}] * 2 + [{"lock_up": []}] * 8
        )
        result = detect_issues_from_lap_records(laps, car_id=1, track="T")
        # 2/10 = 20% < 30%, and 2 < 3 min count
        assert result == []

    def test_wheelspin_detected(self):
        pos = [600, 5, 300]
        laps = _make_laps([{"wheelspin": [pos]}] * 4)
        result = detect_issues_from_lap_records(laps, car_id=1, track="T")
        assert any(r.issue_type == "rear_wheelspin" for r in result)

    def test_oversteer_detected(self):
        pos = [700, 5, 100]
        laps = _make_laps([{"oversteer": [pos]}] * 4)
        result = detect_issues_from_lap_records(laps, car_id=1, track="T")
        assert any(r.issue_type == "rear_oversteer" for r in result)

    def test_different_corners_create_separate_issues(self):
        laps = _make_laps([
            {"lock_up": [[100, 5, 200], [800, 5, -300]]},
            {"lock_up": [[100, 5, 200], [800, 5, -300]]},
            {"lock_up": [[100, 5, 200], [800, 5, -300]]},
        ])
        result = detect_issues_from_lap_records(laps, car_id=1, track="T")
        corner_ids = {r.corner_id for r in result}
        assert len(corner_ids) == 2

    def test_malformed_json_skipped_not_raised(self):
        laps = [
            {"lap_num": 1, "event_positions_json": "not valid json"},
            {"lap_num": 2, "event_positions_json": json.dumps({"lock_up": [[500, 5, -200]]})},
        ]
        # Should not raise — bad JSON is skipped
        result = detect_issues_from_lap_records(laps, car_id=1, track="T")
        assert isinstance(result, list)

    def test_car_id_and_track_propagated(self):
        pos = [500, 10, -200]
        laps = _make_laps([{"lock_up": [pos]}] * 3)
        result = detect_issues_from_lap_records(laps, car_id=99, track="Monza")
        assert result[0].car_id == 99
        assert result[0].track == "Monza"

    def test_severity_increases_with_lap_count(self):
        pos = [500, 10, -200]
        laps3 = _make_laps([{"lock_up": [pos]}] * 3)
        laps8 = _make_laps([{"lock_up": [pos]}] * 8)
        r3 = detect_issues_from_lap_records(laps3, car_id=1, track="T")
        r8 = detect_issues_from_lap_records(laps8, car_id=1, track="T")
        assert r8[0].severity >= r3[0].severity

    def test_duplicate_position_same_lap_counts_as_one(self):
        """Multiple events at same corner on same lap should count as 1 occurrence."""
        pos = [500, 10, -200]
        laps = _make_laps([
            {"lock_up": [pos, pos, pos]},  # 3 events, same lap
            {"lock_up": [pos, pos, pos]},
            {"lock_up": [pos, pos, pos]},
        ])
        result = detect_issues_from_lap_records(laps, car_id=1, track="T")
        assert len(result) == 1
        assert result[0].lap_count == 3  # 3 unique laps, not 9 events


# ---------------------------------------------------------------------------
# 3. PATH B — frame-level detection helpers
# ---------------------------------------------------------------------------
def _brake_frame(pos=(500, 10, -200), speed=80, brake=0.8):
    """Frame with heavy braking and locked wheels."""
    return {
        "pos_x": pos[0], "pos_y": pos[1], "pos_z": pos[2],
        "speed_kmh": speed, "brake": brake, "throttle": 0.0, "gear": 3, "rpm": 6000,
        "wheel_rps": [0.0, 0.0, 0.0, 0.0],     # all wheels stopped = lock
        "tyre_radius": [0.32, 0.32, 0.32, 0.32],
        "rev_limiter": False,
    }


def _throttle_frame(pos=(500, 10, -200), speed=40, gear=2, wheelspin=False):
    """Frame transitioning from brake to throttle."""
    wheel_mult = 1.5 if wheelspin else 0.95
    speed_ms = speed / 3.6
    rps = speed_ms * wheel_mult / (0.32 * 2 * 3.14159)
    return {
        "pos_x": pos[0], "pos_y": pos[1], "pos_z": pos[2],
        "speed_kmh": speed, "brake": 0.0, "throttle": 0.8, "gear": gear, "rpm": 5000,
        "wheel_rps": [rps * 0.95, rps * 0.95, rps, rps],
        "tyre_radius": [0.32, 0.32, 0.32, 0.32],
        "rev_limiter": False,
    }


class TestDetectCornerEventsFromFrames:
    def test_empty_frames_returns_empty(self):
        assert detect_corner_events_from_frames([]) == []

    def test_brake_lock_detected_when_wheels_stopped(self):
        frames = [_brake_frame(speed=80, brake=0.9)] * 3
        events = detect_corner_events_from_frames(frames)
        lock_events = [e for e in events if e["issue_type"] == "brake_lock"]
        assert len(lock_events) >= 1

    def test_corner_exit_wheelspin_detected(self):
        prev = _brake_frame(brake=0.5, speed=50)
        curr = _throttle_frame(speed=40, gear=2, wheelspin=True)
        curr["brake"] = 0.0
        prev["brake"] = 0.2
        frames = [prev, curr]
        events = detect_corner_events_from_frames(frames)
        spin_events = [e for e in events if "wheelspin" in e["issue_type"] or e["issue_type"] == "exit_gear_too_low"]
        assert len(spin_events) >= 1

    def test_no_false_positive_at_low_speed(self):
        """No brake lock detected below 5 km/h."""
        frames = [_brake_frame(speed=3, brake=0.9)] * 3
        events = detect_corner_events_from_frames(frames)
        assert all(e["issue_type"] != "brake_lock" for e in events)


class TestDetectIssuesFromFrameData:
    def test_empty_per_lap_events_returns_empty(self):
        result = detect_issues_from_frame_data([], car_id=1, track="T")
        assert result == []

    def test_repeated_issue_across_laps_flagged(self):
        ev = [{"corner_id": "P500_-200", "issue_type": "brake_lock",
               "phase": "braking", "gear": 3, "rpm": 6000, "speed_kmh": 80,
               "wheelspin": False}]
        per_lap = [ev, ev, ev]  # same event on 3 laps
        result = detect_issues_from_frame_data(per_lap, car_id=1, track="T")
        assert len(result) >= 1

    def test_one_off_event_below_threshold_ignored(self):
        ev = [{"corner_id": "P500_-200", "issue_type": "brake_lock",
               "phase": "braking", "gear": 3, "rpm": 6000, "speed_kmh": 80,
               "wheelspin": False}]
        # 1 event on 1 of 5 laps = 20% < 30% AND count=1 < _MIN_LAP_COUNT=3
        per_lap = [ev, [], [], [], []]
        result = detect_issues_from_frame_data(per_lap, car_id=1, track="T")
        assert result == []

    def test_strong_drive_confirmed_excluded_from_issues(self):
        ev = [{"corner_id": "P500_-200", "issue_type": "strong_drive_confirmed",
               "phase": "exit", "gear": 3, "rpm": 5000, "speed_kmh": 60,
               "wheelspin": False}]
        per_lap = [ev, ev, ev]
        result = detect_issues_from_frame_data(per_lap, car_id=1, track="T")
        assert all(r.issue_type != "strong_drive_confirmed" for r in result)


# ---------------------------------------------------------------------------
# 4. Merge PATH A + PATH B
# ---------------------------------------------------------------------------
class TestMergeIssues:
    def test_path_b_overwrites_path_a_for_same_key(self):
        a = [_issue(corner_id="P500_-200", issue_type="brake_lock")]
        a[0] = _issue(corner_id="P500_-200", issue_type="brake_lock")

        b_issue = _issue(corner_id="P500_-200", issue_type="brake_lock")
        object.__setattr__(b_issue, "evidence", "from path B [frames]")
        merged = merge_issues(a, [b_issue])
        assert len(merged) == 1
        assert "frames" in merged[0].evidence

    def test_unique_issues_from_both_paths_combined(self):
        a = [_issue(corner_id="P100_200", issue_type="brake_lock")]
        b = [_issue(corner_id="P500_-200", issue_type="rear_wheelspin")]
        merged = merge_issues(a, b)
        assert len(merged) == 2

    def test_empty_path_b_returns_path_a(self):
        a = [_issue()]
        assert len(merge_issues(a, [])) == 1


# ---------------------------------------------------------------------------
# 5. Fix verification
# ---------------------------------------------------------------------------
class TestVerifyFix:
    def _prev(self, corner_id="P500_-200", issue_type="brake_lock", lc=5, total=10):
        return {"corner_id": corner_id, "issue_type": issue_type,
                "lap_count": lc, "total_laps": total}

    def test_issue_absent_in_current_is_fixed(self):
        prev = [self._prev()]
        curr = []
        result = verify_fix(prev, curr)
        assert result["P500_-200:brake_lock"] == FIX_STATUS_FIXED

    def test_issue_rate_halved_is_improved(self):
        prev = [self._prev(lc=5, total=10)]  # 50%
        curr = [_issue(lap_count=2, total_laps=10)]  # 20% ≤ 50% * 0.5 = 25%
        result = verify_fix(prev, curr)
        assert result["P500_-200:brake_lock"] == FIX_STATUS_IMPROVED

    def test_issue_rate_unchanged_stays_unchanged(self):
        prev = [self._prev(lc=5, total=10)]  # 50%
        curr = [_issue(lap_count=5, total_laps=10)]  # 50% → unchanged
        result = verify_fix(prev, curr)
        assert result["P500_-200:brake_lock"] == FIX_STATUS_UNCHANGED

    def test_issue_rate_worsened(self):
        prev = [self._prev(lc=2, total=10)]  # 20%
        curr = [_issue(lap_count=7, total_laps=10)]  # 70% ≥ 20% * 1.5 = 30%
        result = verify_fix(prev, curr)
        assert result["P500_-200:brake_lock"] == FIX_STATUS_WORSE

    def test_insufficient_laps_in_current(self):
        prev = [self._prev(lc=5, total=10)]
        curr = [_issue(lap_count=1, total_laps=2)]  # only 2 laps — too few
        result = verify_fix(prev, curr)
        assert result["P500_-200:brake_lock"] == FIX_STATUS_INSUFFICIENT

    def test_different_car_or_track_not_matched(self):
        prev = [self._prev(corner_id="P999_999", issue_type="brake_lock")]
        curr = [_issue(corner_id="P500_-200", issue_type="brake_lock")]
        result = verify_fix(prev, curr)
        assert "P999_999:brake_lock" in result
        assert result["P999_999:brake_lock"] == FIX_STATUS_FIXED  # no longer seen

    def test_empty_previous_returns_empty(self):
        curr = [_issue()]
        result = verify_fix([], curr)
        assert result == {}

    def test_rate_exactly_at_fixed_threshold(self):
        # prev_frac = 50%, curr_frac = 5% ≤ 50% * 0.10 = 5.0% → FIXED
        prev = [self._prev(lc=5, total=10)]
        curr = [_issue(lap_count=1, total_laps=20)]  # 5%
        result = verify_fix(prev, curr)
        assert result["P500_-200:brake_lock"] == FIX_STATUS_FIXED


# ---------------------------------------------------------------------------
# 6. AI prompt summary builder
# ---------------------------------------------------------------------------
class TestBuildCornerSummaryForPrompt:
    def test_empty_issues_returns_empty_string(self):
        assert build_corner_summary_for_prompt([]) == ""

    def test_summary_contains_issue_type(self):
        issues = [_issue(issue_type="brake_lock")]
        text = build_corner_summary_for_prompt(issues)
        assert "brake lock" in text.lower()

    def test_summary_contains_corner_id(self):
        issues = [_issue(corner_id="P500_-200")]
        text = build_corner_summary_for_prompt(issues)
        assert "P500_-200" in text

    def test_summary_includes_fix_status(self):
        issues = [_issue()]
        verifications = {"P500_-200:brake_lock": FIX_STATUS_IMPROVED}
        text = build_corner_summary_for_prompt(issues, verifications)
        assert "improved" in text.lower()

    def test_max_issues_limits_output(self):
        issues = [_issue(corner_id=f"P{i*100}_{i*100}", issue_type="brake_lock") for i in range(10)]
        text = build_corner_summary_for_prompt(issues, max_issues=3)
        # Should show "… and N further" when truncated
        assert "further" in text.lower() or text.count("P") <= 5

    def test_summary_includes_setup_focus(self):
        issues = [_issue(issue_type="brake_lock")]
        text = build_corner_summary_for_prompt(issues)
        # setup advice for brake_lock should appear
        assert "brake" in text.lower()

    def test_summary_has_header(self):
        issues = [_issue()]
        text = build_corner_summary_for_prompt(issues)
        assert "## Repeated Corner Issues" in text

    def test_percentage_shown(self):
        issues = [_issue(lap_count=3, total_laps=5)]  # 60%
        text = build_corner_summary_for_prompt(issues)
        assert "60%" in text


# ---------------------------------------------------------------------------
# 7. Setup advice bridge
# ---------------------------------------------------------------------------
class TestGetSetupAdvice:
    def test_brake_lock_returns_list(self):
        advice = get_setup_advice("brake_lock")
        assert isinstance(advice, list)
        assert len(advice) > 0

    def test_rear_wheelspin_advice_mentions_lsd(self):
        advice = get_setup_advice("rear_wheelspin")
        assert any("LSD" in a or "lsd" in a.lower() for a in advice)

    def test_poor_drive_out_advice_mentions_gear(self):
        advice = get_setup_advice("poor_drive_out")
        assert any("gear" in a.lower() for a in advice)

    def test_exit_gear_too_low_advice(self):
        advice = get_setup_advice("exit_gear_too_low")
        assert len(advice) > 0

    def test_unknown_type_returns_empty_list(self):
        advice = get_setup_advice("totally_unknown_issue_xyz")
        assert advice == []

    def test_early_limiter_on_straight_in_map(self):
        advice = get_setup_advice("early_limiter_on_straight")
        assert len(advice) > 0


# ---------------------------------------------------------------------------
# 8. SessionDB — schema v4 integration
# ---------------------------------------------------------------------------
class TestSessionDBCornerIssues:
    def _make_db(self):
        from data.session_db import SessionDB
        tmp = tempfile.mktemp(suffix=".db")
        db = SessionDB(tmp)
        return db, tmp

    def test_corner_issues_table_created(self):
        db, tmp = self._make_db()
        try:
            with db._lock:
                tables = {
                    r[0] for r in db._conn.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    ).fetchall()
                }
            assert "corner_issues" in tables
        finally:
            db.close()
            os.unlink(tmp)

    def test_schema_version_is_4(self):
        db, tmp = self._make_db()
        try:
            with db._lock:
                version = db._conn.execute("PRAGMA user_version").fetchone()[0]
            assert version >= 4  # updated to 5 after Group 18B migration
        finally:
            db.close()
            os.unlink(tmp)

    def test_save_and_retrieve_corner_issues(self):
        db, tmp = self._make_db()
        try:
            issues = [_issue(car_id=5, track="Monza")]
            db.save_corner_issues(issues)
            rows = db.get_corner_issues(car_id=5, track="Monza")
            assert len(rows) == 1
            assert rows[0]["issue_type"] == "brake_lock"
            assert rows[0]["corner_id"] == "P500_-200"
        finally:
            db.close()
            os.unlink(tmp)

    def test_get_corner_issues_filters_by_car(self):
        db, tmp = self._make_db()
        try:
            db.save_corner_issues([_issue(car_id=1, track="Suzuka")])
            db.save_corner_issues([_issue(car_id=2, track="Suzuka")])
            rows = db.get_corner_issues(car_id=1, track="Suzuka")
            assert all(r["car_id"] == 1 for r in rows)
        finally:
            db.close()
            os.unlink(tmp)

    def test_get_corner_issues_filters_by_track(self):
        db, tmp = self._make_db()
        try:
            db.save_corner_issues([_issue(car_id=1, track="Suzuka")])
            db.save_corner_issues([_issue(car_id=1, track="Monza")])
            rows = db.get_corner_issues(car_id=1, track="Suzuka")
            assert all(r["track"] == "Suzuka" for r in rows)
        finally:
            db.close()
            os.unlink(tmp)

    def test_get_previous_corner_issues_excludes_current_session(self):
        db, tmp = self._make_db()
        try:
            issues_prev = [_issue(car_id=1, track="T")]
            issues_prev[0] = CornerIssue(
                car_id=1, track="T", corner_id="P500_-200",
                lap_count=3, total_laps=5, issue_type="brake_lock", phase="braking",
                severity=0.3, confidence=0.8, evidence="prev",
                session_id=1, detected_at="2026-01-01T00:00:00+00:00",
            )
            issues_curr = [CornerIssue(
                car_id=1, track="T", corner_id="P500_-200",
                lap_count=2, total_laps=5, issue_type="brake_lock", phase="braking",
                severity=0.2, confidence=0.7, evidence="curr",
                session_id=2, detected_at="2026-01-02T00:00:00+00:00",
            )]
            db.save_corner_issues(issues_prev)
            db.save_corner_issues(issues_curr)
            # Exclude session_id=2 → should only return session_id=1
            prev_rows = db.get_previous_corner_issues(car_id=1, track="T", exclude_session_id=2)
            assert len(prev_rows) == 1
            assert prev_rows[0]["session_id"] == 1
        finally:
            db.close()
            os.unlink(tmp)

    def test_get_previous_corner_issues_different_car_not_returned(self):
        db, tmp = self._make_db()
        try:
            db.save_corner_issues([CornerIssue(
                car_id=99, track="T", corner_id="P500_-200",
                lap_count=3, total_laps=5, issue_type="brake_lock", phase="braking",
                severity=0.3, confidence=0.8, evidence="",
                session_id=1, detected_at="2026-01-01T00:00:00+00:00",
            )])
            rows = db.get_previous_corner_issues(car_id=1, track="T", exclude_session_id=0)
            assert rows == []
        finally:
            db.close()
            os.unlink(tmp)

    def test_save_accepts_dict_input(self):
        """save_corner_issues must accept plain dicts (for test convenience)."""
        db, tmp = self._make_db()
        try:
            d = {
                "car_id": 1, "track": "T", "corner_id": "P500_-200",
                "issue_type": "brake_lock", "phase": "braking",
                "lap_count": 3, "total_laps": 5,
                "severity": 0.3, "confidence": 0.8, "evidence": "test",
                "session_id": 1, "detected_at": "2026-01-01T00:00:00+00:00",
            }
            db.save_corner_issues([d])
            rows = db.get_corner_issues(car_id=1, track="T")
            assert len(rows) == 1
        finally:
            db.close()
            os.unlink(tmp)

    def test_save_empty_list_no_error(self):
        db, tmp = self._make_db()
        try:
            db.save_corner_issues([])  # must not raise
        finally:
            db.close()
            os.unlink(tmp)


# ---------------------------------------------------------------------------
# 9. Safe degradation
# ---------------------------------------------------------------------------
class TestSafeDegradation:
    def test_detect_from_lap_records_missing_json_field_ok(self):
        laps = [{"lap_num": 1}]  # no event_positions_json key
        result = detect_issues_from_lap_records(laps, car_id=1, track="T")
        assert result == []

    def test_detect_from_frame_data_missing_pos_fields(self):
        # Frame with no pos_x/pos_z → should not raise
        frame = {"speed_kmh": 80, "brake": 0.9, "throttle": 0.0, "gear": 3, "rpm": 6000}
        frames = [frame] * 3
        events = detect_corner_events_from_frames(frames)
        assert isinstance(events, list)

    def test_detect_from_frame_data_missing_wheel_fields(self):
        frame = {
            "pos_x": 500, "pos_y": 10, "pos_z": -200,
            "speed_kmh": 80, "brake": 0.9, "throttle": 0.0, "gear": 3, "rpm": 6000,
            # no wheel_rps or tyre_radius
        }
        events = detect_corner_events_from_frames([frame, frame])
        assert isinstance(events, list)

    def test_verify_fix_with_missing_fields_does_not_raise(self):
        prev = [{"corner_id": "P500_-200", "issue_type": "brake_lock"}]
        curr = [_issue()]
        result = verify_fix(prev, curr)
        assert isinstance(result, dict)

    def test_build_summary_with_no_verifications(self):
        issues = [_issue()]
        text = build_corner_summary_for_prompt(issues, verifications=None)
        assert "brake lock" in text.lower()
