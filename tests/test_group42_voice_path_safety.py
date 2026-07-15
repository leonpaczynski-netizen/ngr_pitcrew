"""
Group 42 — Rule-First Setup Brain: Voice Path Safety Acceptance Tests

Covers:
  test_voice_path_strips_ai_setup_fields — build_setup_advice_response always returns
    changes==[] and setup_fields=={} regardless of AI output.
  test_voice_strip_helper_removes_canonical_fields — _strip_actionable_for_voice
    zeroes changes/setup_fields but preserves analysis/primary_issue.

All tests are pure/offline — no network, no Qt event loop, no QApplication.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import strategy.driving_advisor as da
from strategy._setup_constants import APPROVED_STATUSES
from strategy.driving_advisor import _strip_actionable_for_voice


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_lap(
    bottoming_count: int = 0,
    wheelspin_count: int = 0,
    snap_throttle_count: int = 0,
    lock_up_count: int = 0,
    rev_limiter_by_gear: dict | None = None,
    max_speed_kmh: float = 200.0,
    brake_consistency_m: float = 5.0,
    oversteer_count: int = 0,
    oversteer_throttle_on_count: int = 0,
    kerb_count: int = 0,
    max_lat_g: float = 1.5,
) -> SimpleNamespace:
    rlbg = rev_limiter_by_gear or {}
    return SimpleNamespace(
        bottoming_count=bottoming_count,
        wheelspin_count=wheelspin_count,
        snap_throttle_count=snap_throttle_count,
        lock_up_count=lock_up_count,
        rev_limiter_by_gear=rlbg,
        max_speed_kmh=max_speed_kmh,
        brake_consistency_m=brake_consistency_m,
        oversteer_count=oversteer_count,
        oversteer_throttle_on_count=oversteer_throttle_on_count,
        kerb_count=kerb_count,
        max_lat_g=max_lat_g,
        rev_limiter_count=sum(rlbg.values()),
        lock_up_positions=[],
        wheelspin_positions=[],
        oversteer_positions=[],
        snap_throttle_positions=[],
        over_braking_positions=[],
        over_braking_count=0,
        abrupt_release_count=0,
        car_max_speed_theoretical_kmh=0.0,
        avg_tyre_radius={},
        off_track_count=0,
        frames=[],
    )


def _make_recorder_stub(laps):
    return SimpleNamespace(recent_laps=lambda n: laps)


def _make_voice_advisor(event_ctx: dict, laps: list) -> da.DrivingAdvisor:
    """Advisor configured for voice-path testing (requires api_key to not short-circuit)."""
    adv = da.DrivingAdvisor.__new__(da.DrivingAdvisor)
    adv._recorder = _make_recorder_stub(laps)
    adv._tracker = None
    adv._config = {"anthropic": {"api_key": "fake-key-for-test"}}
    adv._db = None
    adv._car_id_ref = [0]
    adv._event_ctx = event_ctx
    adv._session_id_getter = lambda: 0
    adv._summarize_new_telemetry = lambda laps: ""
    adv._car_track_header = lambda *a, **k: ""
    adv._get_driver_feedback_context = lambda: ""
    adv._get_previous_ai_context = lambda *a, **k: ""
    adv._get_track_intelligence_context = lambda: ""
    adv._get_enriched_issue_context = lambda laps: ""
    adv._get_live_segment_context = lambda live: ""
    adv._get_history_context = lambda: ""
    adv._DATA_QUALITY_NOTE = ""
    return adv


def _full_ai_tune_json() -> str:
    """Return a full AI tune response with real canonical setup fields."""
    return json.dumps({
        "analysis": "The car has several setup issues that need attention.",
        "primary_issue": "wheelspin",
        "issue_classification": {"wheelspin": "present"},
        "changes": [
            {"setting": "LSD Accel", "field": "lsd_accel",
             "from": "20", "to": 25, "why": "Increase traction"},
            {"setting": "ARB Rear", "field": "arb_rear",
             "from": "4", "to": 3, "why": "Soften rear platform"},
            {"setting": "Ride Height Rear", "field": "ride_height_rear",
             "from": "82", "to": 85, "why": "More clearance"},
        ],
        "setup_fields": {
            "lsd_accel": 25,
            "arb_rear": 3,
            "ride_height_rear": 85,
        },
        "validation_targets": {"rear_stability": "must remain stable"},
        "confidence": {"overall": "high", "reason": "clear signals"},
    })


# ===========================================================================
# Voice path narration — build_setup_advice_response is now a deterministic
# spoken-text narrator (no JSON, no AI). It reuses the rule-engine result from
# build_combined_setup_response and narrates only APPROVED changes. The old
# "strip AI setup fields from the voice JSON" contract is gone (there is no AI
# and no actionable JSON on this path), so those JSON-contract tests were
# removed. The narration is verified to be a plain string below.
# ===========================================================================

class TestVoicePathNarration:
    """build_setup_advice_response returns a plain-text spoken narration string."""

    def test_voice_path_returns_plain_string(self):
        laps = [_make_lap(wheelspin_count=15)]
        setup = {"lsd_accel": 20, "arb_rear": 4, "ride_height_rear": 82}
        adv = _make_voice_advisor({}, laps)
        result = adv.build_setup_advice_response(setup_dict=setup, car_name="")
        assert isinstance(result, str) and result.strip(), (
            f"Voice path must return a non-empty narration string; got {result!r}"
        )

    def test_voice_path_no_laps_is_safe_string(self):
        adv = _make_voice_advisor({}, [_make_lap()])
        result = adv.build_setup_advice_response(setup_dict={}, car_name="")
        assert isinstance(result, str), "Voice path must always return a string"


# ===========================================================================
# test_voice_strip_helper_removes_canonical_fields
# ===========================================================================

class TestVoiceStripHelper:
    """Unit tests for _strip_actionable_for_voice."""

    def test_strip_zeroes_changes(self):
        """_strip_actionable_for_voice zeroes changes regardless of input."""
        data = {
            "analysis": "Good analysis text.",
            "primary_issue": "wheelspin",
            "changes": [
                {"field": "lsd_accel", "to": 25, "setting": "LSD Accel", "why": "test"},
                {"field": "arb_rear", "to": 3, "setting": "ARB Rear", "why": "test"},
            ],
            "setup_fields": {"lsd_accel": 25, "arb_rear": 3},
        }

        result = _strip_actionable_for_voice(data)

        assert result["changes"] == [], (
            f"_strip_actionable_for_voice must zero changes; got {result['changes']!r}"
        )

    def test_strip_zeroes_setup_fields(self):
        """_strip_actionable_for_voice zeroes setup_fields."""
        data = {
            "analysis": "Good analysis.",
            "primary_issue": "wheelspin",
            "changes": [],
            "setup_fields": {"lsd_accel": 25, "arb_rear": 3},
        }

        result = _strip_actionable_for_voice(data)

        assert result["setup_fields"] == {}, (
            f"_strip_actionable_for_voice must zero setup_fields; "
            f"got {result['setup_fields']!r}"
        )

    def test_strip_preserves_analysis(self):
        """_strip_actionable_for_voice preserves analysis text."""
        analysis_text = "This is an important analysis for narration."
        data = {
            "analysis": analysis_text,
            "primary_issue": "wheelspin",
            "changes": [{"field": "lsd_accel", "to": 25}],
            "setup_fields": {"lsd_accel": 25},
        }

        result = _strip_actionable_for_voice(data)

        assert result["analysis"] == analysis_text, (
            f"_strip_actionable_for_voice must preserve analysis; "
            f"got {result['analysis']!r}"
        )

    def test_strip_preserves_primary_issue(self):
        """_strip_actionable_for_voice preserves primary_issue."""
        data = {
            "analysis": "Analysis.",
            "primary_issue": "wheelspin and traction loss",
            "changes": [{"field": "lsd_accel", "to": 25}],
            "setup_fields": {"lsd_accel": 25},
        }

        result = _strip_actionable_for_voice(data)

        assert result["primary_issue"] == "wheelspin and traction loss", (
            f"_strip_actionable_for_voice must preserve primary_issue; "
            f"got {result['primary_issue']!r}"
        )

    def test_strip_does_not_mutate_original(self):
        """_strip_actionable_for_voice must not mutate the input dict."""
        data = {
            "analysis": "Good.",
            "primary_issue": "wheelspin",
            "changes": [{"field": "lsd_accel", "to": 25}],
            "setup_fields": {"lsd_accel": 25},
        }
        original_changes_len = len(data["changes"])
        original_sf_keys = set(data["setup_fields"].keys())

        _strip_actionable_for_voice(data)

        # Original must be unchanged
        assert len(data["changes"]) == original_changes_len, (
            "_strip_actionable_for_voice must not mutate original changes list"
        )
        assert set(data["setup_fields"].keys()) == original_sf_keys, (
            "_strip_actionable_for_voice must not mutate original setup_fields"
        )

    def test_strip_handles_empty_input(self):
        """_strip_actionable_for_voice handles empty input dict gracefully."""
        result = _strip_actionable_for_voice({})
        assert result["changes"] == []
        assert result["setup_fields"] == {}

    def test_strip_handles_no_changes_key(self):
        """_strip_actionable_for_voice handles dict without changes key."""
        data = {"analysis": "OK.", "primary_issue": "none"}
        result = _strip_actionable_for_voice(data)
        assert result["changes"] == []
        assert result["setup_fields"] == {}
