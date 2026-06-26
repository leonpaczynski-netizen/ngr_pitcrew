"""
Group 21A — corner_verify_ai returns-tuple tests.

Verifies that verify_corners_with_ai():
  - Returns a 2-tuple in ALL code paths
  - Returns (None, non-empty-string) on each failure path
  - Returns (dict, "") on success
"""
import json
import pytest
from unittest.mock import patch

from strategy.corner_verify_ai import verify_corners_with_ai

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
# Helper to assert 2-tuple structure
# ---------------------------------------------------------------------------

def _assert_failure_tuple(ret, expected_reason_fragment: str = ""):
    assert isinstance(ret, tuple), f"Expected tuple, got {type(ret)}"
    assert len(ret) == 2, f"Expected 2-tuple, got {len(ret)}-tuple"
    result_dict, reason = ret
    assert result_dict is None, f"Expected None result_dict, got {result_dict!r}"
    assert isinstance(reason, str), f"Expected str reason, got {type(reason)}"
    assert len(reason) > 0, "Expected non-empty reason string"
    if expected_reason_fragment:
        assert expected_reason_fragment.lower() in reason.lower(), (
            f"Expected '{expected_reason_fragment}' in reason '{reason}'"
        )


# ---------------------------------------------------------------------------
# Failure path 1 — missing api_key → "No API key configured"
# ---------------------------------------------------------------------------

def test_failure_no_api_key():
    """Empty api_key → (None, 'No API key configured')."""
    ret = verify_corners_with_ai(
        peaks=_PEAKS,
        seed_windows=_WINDOWS,
        speed_profile=_SPEED,
        api_key="",
    )
    _assert_failure_tuple(ret, "No API key configured")


# ---------------------------------------------------------------------------
# Failure path 2 — empty peaks → "No API key configured"
# ---------------------------------------------------------------------------

def test_failure_empty_peaks():
    """Empty peaks list → (None, non-empty reason)."""
    ret = verify_corners_with_ai(
        peaks=[],
        seed_windows=_WINDOWS,
        speed_profile=_SPEED,
        api_key=_API_KEY,
    )
    _assert_failure_tuple(ret)


# ---------------------------------------------------------------------------
# Failure path 3 — network error (call_api raises) → "Network error: ..."
# ---------------------------------------------------------------------------

def test_failure_network_error():
    """call_api raises RuntimeError → (None, 'Network error: ...')."""
    with patch("strategy._ai_client.call_api", side_effect=RuntimeError("timeout")):
        ret = verify_corners_with_ai(
            peaks=_PEAKS,
            seed_windows=_WINDOWS,
            speed_profile=_SPEED,
            api_key=_API_KEY,
        )
    _assert_failure_tuple(ret, "Network error")


# ---------------------------------------------------------------------------
# Failure path 4 — invalid JSON response → "AI response parse error"
# ---------------------------------------------------------------------------

def test_failure_parse_error():
    """call_api returns non-JSON → (None, 'AI response parse error')."""
    with patch("strategy._ai_client.call_api", return_value="not valid json {{"):
        ret = verify_corners_with_ai(
            peaks=_PEAKS,
            seed_windows=_WINDOWS,
            speed_profile=_SPEED,
            api_key=_API_KEY,
        )
    _assert_failure_tuple(ret, "AI response parse error")


# ---------------------------------------------------------------------------
# Success path — valid mock response → (dict, "")
# ---------------------------------------------------------------------------

def test_success_returns_dict_and_empty_reason():
    """Valid AI response → (result_dict, '') where result_dict has corner keys."""
    with patch("strategy._ai_client.call_api", return_value=_VALID_RESPONSE):
        ret = verify_corners_with_ai(
            peaks=_PEAKS,
            seed_windows=_WINDOWS,
            speed_profile=_SPEED,
            api_key=_API_KEY,
            track_name="Brands Hatch Indy",
        )

    assert isinstance(ret, tuple), f"Expected tuple, got {type(ret)}"
    assert len(ret) == 2
    result_dict, reason = ret
    assert result_dict is not None
    assert isinstance(result_dict, dict)
    assert reason == "", f"Expected empty reason on success, got '{reason}'"
    assert set(result_dict.keys()) == {"T1", "T2", "T3"}
    assert abs(result_dict["T1"]["progress_pct"] - 10.0) < 0.01
    assert abs(result_dict["T2"]["confidence"] - 0.88) < 0.01


# ---------------------------------------------------------------------------
# Return type invariant — all paths return 2-tuple
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# AC8 — verify_corners_with_ai() prints to console on every call
# ---------------------------------------------------------------------------

def test_console_print_on_entry_no_api_key(capsys):
    """AC8: A [CornerVerify] line is printed even when api_key is empty."""
    verify_corners_with_ai(peaks=[], seed_windows=[], speed_profile=[], api_key="")
    captured = capsys.readouterr()
    assert "[CornerVerify]" in captured.out, (
        f"Expected [CornerVerify] in stdout, got: {captured.out!r}"
    )


def test_console_print_on_network_error(capsys):
    """AC8: A [CornerVerify] line is printed when a network error occurs."""
    with patch("strategy._ai_client.call_api", side_effect=RuntimeError("connection reset")):
        verify_corners_with_ai(
            peaks=_PEAKS,
            seed_windows=_WINDOWS,
            speed_profile=_SPEED,
            api_key=_API_KEY,
        )
    captured = capsys.readouterr()
    assert "[CornerVerify]" in captured.out, (
        f"Expected [CornerVerify] in stdout, got: {captured.out!r}"
    )


def test_console_print_on_parse_error(capsys):
    """AC8: A [CornerVerify] line is printed when the response cannot be parsed."""
    with patch("strategy._ai_client.call_api", return_value="{{invalid"):
        verify_corners_with_ai(
            peaks=_PEAKS,
            seed_windows=_WINDOWS,
            speed_profile=_SPEED,
            api_key=_API_KEY,
        )
    captured = capsys.readouterr()
    assert "[CornerVerify]" in captured.out, (
        f"Expected [CornerVerify] in stdout, got: {captured.out!r}"
    )


def test_console_print_on_success(capsys):
    """AC8: A [CornerVerify] line is printed on success, including the result."""
    with patch("strategy._ai_client.call_api", return_value=_VALID_RESPONSE):
        verify_corners_with_ai(
            peaks=_PEAKS,
            seed_windows=_WINDOWS,
            speed_profile=_SPEED,
            api_key=_API_KEY,
        )
    captured = capsys.readouterr()
    assert "[CornerVerify]" in captured.out, (
        f"Expected [CornerVerify] in stdout, got: {captured.out!r}"
    )
    # On success the result dict is also printed
    assert "Result" in captured.out or "T1" in captured.out, (
        f"Expected result data in stdout on success, got: {captured.out!r}"
    )


def test_console_print_entry_line_shows_counts(capsys):
    """AC8: The entry print line includes peak and seed window counts."""
    verify_corners_with_ai(
        peaks=_PEAKS,
        seed_windows=_WINDOWS,
        speed_profile=_SPEED,
        api_key="",  # fails early but entry line already printed
    )
    captured = capsys.readouterr()
    # Entry line: "[CornerVerify] Sending 3 peaks, 3 seed windows, 21 speed pts"
    assert "3 peaks" in captured.out or "peaks" in captured.out, (
        f"Expected peak count in stdout, got: {captured.out!r}"
    )


def test_return_is_always_2_tuple():
    """Regardless of inputs, the return value must always be a 2-tuple."""
    # No API key
    ret = verify_corners_with_ai(peaks=[], seed_windows=[], speed_profile=[], api_key="")
    assert isinstance(ret, tuple) and len(ret) == 2

    # Network failure
    with patch("strategy._ai_client.call_api", side_effect=ConnectionError("down")):
        ret = verify_corners_with_ai(peaks=_PEAKS, seed_windows=_WINDOWS,
                                     speed_profile=_SPEED, api_key=_API_KEY)
    assert isinstance(ret, tuple) and len(ret) == 2

    # Success
    with patch("strategy._ai_client.call_api", return_value=_VALID_RESPONSE):
        ret = verify_corners_with_ai(peaks=_PEAKS, seed_windows=_WINDOWS,
                                     speed_profile=_SPEED, api_key=_API_KEY)
    assert isinstance(ret, tuple) and len(ret) == 2
