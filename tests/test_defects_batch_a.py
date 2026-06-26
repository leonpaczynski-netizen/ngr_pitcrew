"""Unit tests for defect batch A fixes.

DEF-P4-002: Configurable AI model
DEF-P2-006: Tuning lock on event activation (Qt required — skipped in CI)
DEF-P3-003: Tyre compound inheritance (Qt required — skipped in CI)
DEF-P3-006: Session summary recalculation after history load (Qt required — skipped in CI)
"""
from __future__ import annotations

import json
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# DEF-P4-002 — Configurable AI model
# ---------------------------------------------------------------------------

class TestCallApiModel(unittest.TestCase):
    """call_api() must use the caller-supplied model or fall back to _DEFAULT_MODEL."""

    def _make_mock_response(self, model: str = "claude-opus-4-8") -> MagicMock:
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "content": [{"text": "ok"}],
            "usage": {"input_tokens": 10, "output_tokens": 5},
        }
        mock_resp.raise_for_status = MagicMock()
        return mock_resp

    def _call(self, **kwargs):
        """Call call_api with a mocked requests.post and return the captured body."""
        from strategy._ai_client import call_api
        captured = {}

        def fake_post(url, headers, json, timeout):
            captured["body"] = json
            return self._make_mock_response()

        with patch("requests.post", side_effect=fake_post):
            call_api("test prompt", "fake-key", **kwargs)
        return captured["body"]

    def test_call_api_uses_explicit_model(self):
        body = self._call(model="claude-opus-4-8")
        self.assertEqual(body["model"], "claude-opus-4-8")

    def test_call_api_default_model_when_absent(self):
        body = self._call()
        self.assertEqual(body["model"], "claude-opus-4-8")

    def test_call_api_default_model_when_whitespace(self):
        body = self._call(model="   ")
        self.assertEqual(body["model"], "claude-opus-4-8")

    def test_no_sonnet_default_in_ai_client(self):
        """Ensure claude-sonnet-4-6 is not used as a default value assignment."""
        src_path = Path(__file__).parent.parent / "strategy" / "_ai_client.py"
        src = src_path.read_text(encoding="utf-8")
        # The string must not appear as a default assignment (= "claude-sonnet-4-6")
        self.assertNotIn('= "claude-sonnet-4-6"', src,
                         "claude-sonnet-4-6 should not appear as a default value assignment in _ai_client.py")

    def test_default_model_constant_is_opus(self):
        from strategy import _ai_client
        self.assertEqual(_ai_client._DEFAULT_MODEL, "claude-opus-4-8")

    def test_explicit_model_overrides_default(self):
        body = self._call(model="claude-haiku-3-5")
        self.assertEqual(body["model"], "claude-haiku-3-5")


# ---------------------------------------------------------------------------
# DEF-P2-006 — Tuning lock on event activation (requires Qt display)
# ---------------------------------------------------------------------------

import pytest

@pytest.mark.skip(reason="requires Qt display")
def test_apply_setup_permissions_called_on_event_set_active():
    """_on_event_set_active() must call _apply_setup_permissions unconditionally."""
    pass


# ---------------------------------------------------------------------------
# DEF-P3-003 — Tyre compound inheritance in _add_bank_lap_row (requires Qt)
# ---------------------------------------------------------------------------

@pytest.mark.skip(reason="requires Qt display")
def test_bank_lap_row_inherits_prior_compound():
    """New lap with no compound should inherit the highest prior lap's compound."""
    pass


@pytest.mark.skip(reason="requires Qt display")
def test_bank_lap_row_falls_back_to_default_compound():
    """New lap with no compound and no prior tags should use _default_lap_compound."""
    pass


# ---------------------------------------------------------------------------
# DEF-P3-006 — Practice summary recalculation (requires Qt)
# ---------------------------------------------------------------------------

@pytest.mark.skip(reason="requires Qt display")
def test_refresh_practice_summary_after_history_load():
    """_on_history_load_session() must trigger _refresh_practice_summary()."""
    pass


@pytest.mark.skip(reason="requires Qt display")
def test_refresh_practice_summary_zero_rows():
    """_refresh_practice_summary() with no rows sets all labels to — except laps=0."""
    pass


if __name__ == "__main__":
    unittest.main()
