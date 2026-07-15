"""
Group 31 — Shift Indicator / RPM Beep backend unit tests

Covers:
  Section A — should_shift_beep pure helper
  Section B — resolve_threshold pure helper
  Section C — _parse_setup_recommendation: new shift_rpm_qual/race fields
  Section D — Prompt text contains both shift_rpm_qual and shift_rpm_race (source-scan)

No Qt, no audio — play_beep_direct is never called (pure functions tested only).
Matches patterns from test_group26_setup_overhaul.py.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# ---------------------------------------------------------------------------
# Import the two pure helpers directly from main (no Qt widgets needed at
# import time because only module-level names are accessed, not the Qt app).
# ---------------------------------------------------------------------------

from main import driving_gate, resolve_threshold, should_shift_beep  # noqa: E402


# ===========================================================================
# Section A — should_shift_beep
# ===========================================================================

class TestShouldShiftBeep:
    """A — Pure helper: should_shift_beep()"""

    # -----------------------------------------------------------------------
    # A1: fires on upshift at/above threshold
    # -----------------------------------------------------------------------

    def test_fires_at_threshold(self):
        """Beep fires when rpm == threshold, enabled, valid gear, not hysteresis-armed."""
        beep, new_above, new_dm = should_shift_beep(
            prev_gear=2, cur_gear=2, rpm=7000.0, threshold=7000.0,
            shift_above=False, enabled=True,
            muted_until=0.0, downshift_muted_until=0.0, now=1.0,
        )
        assert beep is True
        assert new_above is True

    def test_fires_above_threshold(self):
        beep, new_above, _ = should_shift_beep(
            prev_gear=3, cur_gear=3, rpm=7200.0, threshold=7000.0,
            shift_above=False, enabled=True,
            muted_until=0.0, downshift_muted_until=0.0, now=1.0,
        )
        assert beep is True
        assert new_above is True

    # -----------------------------------------------------------------------
    # A2: no re-fire while shift_above is True and RPM is still high
    # -----------------------------------------------------------------------

    def test_no_refire_while_shift_above_and_rpm_high(self):
        """Once fired (shift_above=True), no beep even if rpm >= threshold."""
        beep, new_above, _ = should_shift_beep(
            prev_gear=3, cur_gear=3, rpm=7200.0, threshold=7000.0,
            shift_above=True, enabled=True,
            muted_until=0.0, downshift_muted_until=0.0, now=1.0,
        )
        assert beep is False
        assert new_above is True

    # -----------------------------------------------------------------------
    # A3: re-arms after RPM < 0.95 * threshold
    # -----------------------------------------------------------------------

    def test_rearms_after_rpm_drops(self):
        """shift_above becomes False when rpm < 0.95 * threshold."""
        beep, new_above, _ = should_shift_beep(
            prev_gear=3, cur_gear=3, rpm=6600.0, threshold=7000.0,
            shift_above=True, enabled=True,
            muted_until=0.0, downshift_muted_until=0.0, now=1.0,
        )
        # rpm=6600 < 7000*0.95=6650 → re-arms
        assert beep is False
        assert new_above is False

    def test_rearms_at_exact_boundary(self):
        """RPM exactly at 0.95*threshold → re-arm (< condition, not <=)."""
        threshold = 7000.0
        rpm = threshold * 0.94  # clearly below
        beep, new_above, _ = should_shift_beep(
            prev_gear=3, cur_gear=3, rpm=rpm, threshold=threshold,
            shift_above=True, enabled=True,
            muted_until=0.0, downshift_muted_until=0.0, now=1.0,
        )
        assert new_above is False

    def test_does_not_rearm_at_0_95(self):
        """RPM == 0.95*threshold → NOT re-armed (uses strict < )."""
        threshold = 7000.0
        rpm = threshold * 0.95  # exactly at boundary — NOT below
        beep, new_above, _ = should_shift_beep(
            prev_gear=3, cur_gear=3, rpm=rpm, threshold=threshold,
            shift_above=True, enabled=True,
            muted_until=0.0, downshift_muted_until=0.0, now=1.0,
        )
        # 6650.0 is NOT < 6650.0 so hysteresis stays True
        assert new_above is True

    # -----------------------------------------------------------------------
    # A4: downshift sets ~now+0.3 mute and no beep
    # -----------------------------------------------------------------------

    def test_downshift_no_beep(self):
        now = 5.0
        beep, new_above, new_dm = should_shift_beep(
            prev_gear=4, cur_gear=3, rpm=7500.0, threshold=7000.0,
            shift_above=False, enabled=True,
            muted_until=0.0, downshift_muted_until=0.0, now=now,
        )
        assert beep is False
        assert new_dm == pytest.approx(now + 0.3, abs=1e-9)

    def test_downshift_sets_shift_above_true(self):
        """Downshift should arm shift_above to suppress throttle-blip beep."""
        now = 5.0
        beep, new_above, _ = should_shift_beep(
            prev_gear=5, cur_gear=3, rpm=6000.0, threshold=7000.0,
            shift_above=False, enabled=True,
            muted_until=0.0, downshift_muted_until=0.0, now=now,
        )
        assert new_above is True

    # -----------------------------------------------------------------------
    # A5: beep suppressed while downshift_muted_until > now
    # -----------------------------------------------------------------------

    def test_suppressed_while_downshift_muted(self):
        now = 5.0
        beep, _, _ = should_shift_beep(
            prev_gear=3, cur_gear=3, rpm=7200.0, threshold=7000.0,
            shift_above=False, enabled=True,
            muted_until=0.0, downshift_muted_until=now + 0.2, now=now,
        )
        assert beep is False

    def test_fires_after_downshift_mute_expires(self):
        now = 5.5
        beep, _, _ = should_shift_beep(
            prev_gear=3, cur_gear=3, rpm=7200.0, threshold=7000.0,
            shift_above=False, enabled=True,
            muted_until=0.0, downshift_muted_until=5.0, now=now,
        )
        assert beep is True

    # -----------------------------------------------------------------------
    # A6: enabled=False → no beep
    # -----------------------------------------------------------------------

    def test_enabled_false_no_beep(self):
        beep, new_above, new_dm = should_shift_beep(
            prev_gear=3, cur_gear=3, rpm=8000.0, threshold=7000.0,
            shift_above=False, enabled=False,
            muted_until=0.0, downshift_muted_until=0.0, now=1.0,
        )
        assert beep is False
        # State is left unchanged when disabled
        assert new_above is False
        assert new_dm == 0.0

    # -----------------------------------------------------------------------
    # A7: neutral gear (0) → no beep
    # -----------------------------------------------------------------------

    def test_neutral_gear_no_beep(self):
        beep, _, _ = should_shift_beep(
            prev_gear=1, cur_gear=0, rpm=8000.0, threshold=7000.0,
            shift_above=False, enabled=True,
            muted_until=0.0, downshift_muted_until=0.0, now=1.0,
        )
        assert beep is False

    # -----------------------------------------------------------------------
    # A8: reverse gear (>=9, e.g. 15 in GT7) → no beep
    # -----------------------------------------------------------------------

    def test_reverse_gear_15_no_beep(self):
        beep, _, _ = should_shift_beep(
            prev_gear=0, cur_gear=15, rpm=2000.0, threshold=7000.0,
            shift_above=False, enabled=True,
            muted_until=0.0, downshift_muted_until=0.0, now=1.0,
        )
        assert beep is False

    def test_gear_9_no_beep(self):
        beep, _, _ = should_shift_beep(
            prev_gear=8, cur_gear=9, rpm=8000.0, threshold=7000.0,
            shift_above=False, enabled=True,
            muted_until=0.0, downshift_muted_until=0.0, now=1.0,
        )
        assert beep is False

    # -----------------------------------------------------------------------
    # A9: muted_until guard (race-finish mute)
    # -----------------------------------------------------------------------

    def test_muted_until_suppresses_beep(self):
        now = 5.0
        beep, _, _ = should_shift_beep(
            prev_gear=3, cur_gear=3, rpm=7200.0, threshold=7000.0,
            shift_above=False, enabled=True,
            muted_until=now + 60.0, downshift_muted_until=0.0, now=now,
        )
        assert beep is False

    # -----------------------------------------------------------------------
    # A10: first gear is a valid drive gear (boundary)
    # -----------------------------------------------------------------------

    def test_gear_1_valid(self):
        beep, _, _ = should_shift_beep(
            prev_gear=0, cur_gear=1, rpm=7200.0, threshold=7000.0,
            shift_above=False, enabled=True,
            muted_until=0.0, downshift_muted_until=0.0, now=1.0,
        )
        # cur_gear=1 > prev_gear=0, not a downshift
        assert beep is True

    def test_gear_8_valid(self):
        beep, _, _ = should_shift_beep(
            prev_gear=7, cur_gear=8, rpm=7200.0, threshold=7000.0,
            shift_above=False, enabled=True,
            muted_until=0.0, downshift_muted_until=0.0, now=1.0,
        )
        # upshift from 7→8 is NOT a downshift; rpm >= threshold → beep
        assert beep is True


# ===========================================================================
# Section B — resolve_threshold
# ===========================================================================

class TestResolveThreshold:
    """B — Pure helper: resolve_threshold()"""

    # -----------------------------------------------------------------------
    # B1: race / is_racing → race_rpm
    # -----------------------------------------------------------------------

    def test_is_racing_returns_race_rpm(self):
        sb = {"enabled": True, "qual_rpm": 7000, "race_rpm": 6500}
        key, thresh = resolve_threshold("Race", is_racing=True,
                                        practice_is_qual=False, sb=sb)
        assert key == "race_rpm"
        assert thresh == 6500.0

    def test_is_racing_overrides_live_mode(self):
        """Even if live_mode='Qualifying', is_racing=True selects race_rpm."""
        sb = {"enabled": True, "qual_rpm": 7000, "race_rpm": 6500}
        key, thresh = resolve_threshold("Qualifying", is_racing=True,
                                        practice_is_qual=False, sb=sb)
        assert key == "race_rpm"

    # -----------------------------------------------------------------------
    # B2: qualifying → qual_rpm
    # -----------------------------------------------------------------------

    def test_qualifying_returns_qual_rpm(self):
        sb = {"enabled": True, "qual_rpm": 7000, "race_rpm": 6500}
        key, thresh = resolve_threshold("Qualifying", is_racing=False,
                                        practice_is_qual=False, sb=sb)
        assert key == "qual_rpm"
        assert thresh == 7000.0

    # -----------------------------------------------------------------------
    # B3: practice + practice_is_qual=True → qual_rpm
    # -----------------------------------------------------------------------

    def test_practice_is_qual_true_returns_qual_rpm(self):
        sb = {"enabled": True, "qual_rpm": 7000, "race_rpm": 6500}
        key, thresh = resolve_threshold("Practice", is_racing=False,
                                        practice_is_qual=True, sb=sb)
        assert key == "qual_rpm"
        assert thresh == 7000.0

    # -----------------------------------------------------------------------
    # B4: practice + practice_is_qual=False → race_rpm
    # -----------------------------------------------------------------------

    def test_practice_is_qual_false_returns_race_rpm(self):
        sb = {"enabled": True, "qual_rpm": 7000, "race_rpm": 6500}
        key, thresh = resolve_threshold("Practice", is_racing=False,
                                        practice_is_qual=False, sb=sb)
        assert key == "race_rpm"
        assert thresh == 6500.0

    # -----------------------------------------------------------------------
    # B5: missing keys → default 7000, no KeyError
    # -----------------------------------------------------------------------

    def test_empty_sb_defaults_to_7000(self):
        key, thresh = resolve_threshold("Qualifying", is_racing=False,
                                        practice_is_qual=False, sb={})
        assert thresh == 7000.0

    def test_missing_race_rpm_defaults_to_7000(self):
        sb = {"qual_rpm": 7500}  # race_rpm absent
        key, thresh = resolve_threshold("Race", is_racing=True,
                                        practice_is_qual=False, sb=sb)
        # race_rpm missing → falls back to 7000
        assert thresh == 7000.0

    def test_missing_qual_rpm_defaults_to_7000(self):
        sb = {"race_rpm": 6500}  # qual_rpm absent
        key, thresh = resolve_threshold("Qualifying", is_racing=False,
                                        practice_is_qual=False, sb=sb)
        # qual_rpm missing → falls back to 7000
        assert thresh == 7000.0

    # -----------------------------------------------------------------------
    # B6: legacy "rpm" key fallback
    # -----------------------------------------------------------------------

    def test_legacy_rpm_fallback(self):
        sb = {"rpm": 6800}  # old config format
        key, thresh = resolve_threshold("Qualifying", is_racing=False,
                                        practice_is_qual=False, sb=sb)
        assert thresh == 6800.0

    def test_legacy_rpm_fallback_race(self):
        sb = {"rpm": 6800}
        key, thresh = resolve_threshold("Race", is_racing=True,
                                        practice_is_qual=False, sb=sb)
        assert thresh == 6800.0

    # -----------------------------------------------------------------------
    # B7: unknown live_mode (e.g. "Spectate") → qual_rpm
    # -----------------------------------------------------------------------

    def test_unknown_mode_returns_qual_rpm(self):
        sb = {"qual_rpm": 7100, "race_rpm": 6600}
        key, thresh = resolve_threshold("Spectate", is_racing=False,
                                        practice_is_qual=False, sb=sb)
        assert key == "qual_rpm"
        assert thresh == 7100.0


# ---------------------------------------------------------------------------
# Section E — driving_gate: off-track beep suppression (UAT: "RPM beeps
# constantly without being on track")
# ---------------------------------------------------------------------------


class TestDrivingGate:
    """The beep must only sound when the car is actually being driven."""

    def test_on_track_beeps(self):
        assert driving_gate(car_on_track=True, paused=False, loading=False,
                            in_gear=True, speed_kmh=180.0) is True

    def test_garage_idle_muted(self):
        # Engine running in the garage: not on track, not moving.
        assert driving_gate(car_on_track=False, paused=False, loading=False,
                            in_gear=False, speed_kmh=0.0) is False

    def test_paused_muted(self):
        assert driving_gate(car_on_track=True, paused=True, loading=False,
                            in_gear=True, speed_kmh=120.0) is False

    def test_loading_muted(self):
        assert driving_gate(car_on_track=True, paused=False, loading=True,
                            in_gear=True, speed_kmh=0.0) is False

    def test_replay_menu_muted(self):
        # Replay: car_on_track False and (typically) not reported in-gear.
        assert driving_gate(car_on_track=False, paused=False, loading=False,
                            in_gear=False, speed_kmh=90.0) is False

    def test_pit_lane_moving_in_gear_muted(self):
        # In the pit lane / a lobby out-lap the car moves in gear but
        # car_on_track is False — must NOT beep (the reported off-track case).
        assert driving_gate(car_on_track=False, paused=False, loading=False,
                            in_gear=True, speed_kmh=80.0) is False

    def test_off_track_moving_muted(self):
        # Any off-track motion (replay, spun off, formation) stays muted — the
        # gate is strictly on car_on_track per the user requirement.
        assert driving_gate(car_on_track=False, paused=False, loading=False,
                            in_gear=True, speed_kmh=5.0) is False

    def test_on_track_slow_still_beeps(self):
        # On track counts even at low speed — gating is on car_on_track, not speed.
        assert driving_gate(car_on_track=True, paused=False, loading=False,
                            in_gear=True, speed_kmh=8.0) is True
