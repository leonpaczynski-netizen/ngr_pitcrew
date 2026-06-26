"""
Group 20A — AI Corner Verification tests.
"""
import json
import pytest
from unittest.mock import patch

from strategy.corner_verify_ai import verify_corners_with_ai

# Sample data used across tests
_PEAKS = [
    (10.0, 0.02, False),
    (25.0, 0.05, True),
    (50.0, 0.03, False),
]
_WINDOWS = [
    ("T1", 8.0, 15.0),
    ("T2", 22.0, 30.0),
    ("T3", 45.0, 55.0),
]
_SPEED = [(float(i), 120.0 - i * 0.5) for i in range(0, 101, 5)]
_API_KEY = "sk-test-fake-key"

_VALID_RESPONSE = json.dumps({
    "T1": {"progress_pct": 10.0, "confidence": 0.91},
    "T2": {"progress_pct": 25.0, "confidence": 0.88},
    "T3": {"progress_pct": 50.0, "confidence": 0.75},
})


# ---------------------------------------------------------------------------
# Test 1 — successful AI response returns structured dict
# ---------------------------------------------------------------------------

def test_verify_success():
    """mock call_api returns valid JSON → result contains expected corner keys."""
    with patch("strategy._ai_client.call_api", return_value=_VALID_RESPONSE):
        result, reason = verify_corners_with_ai(
            peaks=_PEAKS,
            seed_windows=_WINDOWS,
            speed_profile=_SPEED,
            api_key=_API_KEY,
            track_name="Brands Hatch Indy",
        )

    assert result is not None
    assert reason == ""
    assert set(result.keys()) == {"T1", "T2", "T3"}
    assert abs(result["T1"]["progress_pct"] - 10.0) < 0.01
    assert abs(result["T2"]["confidence"] - 0.88) < 0.01


# ---------------------------------------------------------------------------
# Test 2 — call_api raises RuntimeError → returns None (graceful fallback)
# ---------------------------------------------------------------------------

def test_verify_api_failure():
    """mock call_api raises RuntimeError → verify_corners_with_ai returns (None, reason)."""
    with patch("strategy._ai_client.call_api", side_effect=RuntimeError("API error")):
        result, reason = verify_corners_with_ai(
            peaks=_PEAKS,
            seed_windows=_WINDOWS,
            speed_profile=_SPEED,
            api_key=_API_KEY,
        )

    assert result is None
    assert reason != ""


# ---------------------------------------------------------------------------
# Test 3 — call_api returns invalid JSON → returns None
# ---------------------------------------------------------------------------

def test_verify_bad_json():
    """mock call_api returns non-JSON text → verify_corners_with_ai returns (None, reason)."""
    with patch("strategy._ai_client.call_api", return_value="not json at all"):
        result, reason = verify_corners_with_ai(
            peaks=_PEAKS,
            seed_windows=_WINDOWS,
            speed_profile=_SPEED,
            api_key=_API_KEY,
        )

    assert result is None
    assert reason != ""
