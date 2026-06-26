"""Tests for Remediation Group 9: AI Debug / AI Log tab visibility (DEF-P1-010).

Root cause: when GT7_AI_DEBUG=1 is set, call_api() raises RuntimeError before
reaching the try/except block that calls _fire_log_hook(). Result: DB is not
written, bridge signal is not emitted, AI Log tab shows nothing.

Fix: _fire_log_hook() is now called with a dry-run AILogEntry (success=False,
error_msg="AI_DEBUG mode active...") BEFORE raising RuntimeError, so every
intercepted call appears in the AI Log tab regardless of debug mode.
"""
from __future__ import annotations

import pathlib
import unittest

_SRC = pathlib.Path(__file__).parent.parent


def _ai_client_text() -> str:
    return (_SRC / "strategy" / "_ai_client.py").read_text(encoding="utf-8")


def _dashboard_text() -> str:
    return (_SRC / "ui" / "dashboard.py").read_text(encoding="utf-8")


def _call_api_body(text: str) -> str:
    """Extract the body of the call_api function."""
    start = text.find("\ndef call_api(")
    if start == -1:
        return ""
    end = text.find("\ndef ", start + 1)
    return text[start:end] if end != -1 else text[start:]


def _debug_block(body: str) -> str:
    """Extract the if _AI_DEBUG: block from call_api body."""
    start = body.find("if _AI_DEBUG:")
    if start == -1:
        return ""
    # Block ends at the `try:` that starts the real API call path
    end = body.find("\n    try:", start)
    return body[start:end] if end != -1 else body[start:]


def _method_body(text: str, method_name: str) -> str:
    start = text.find(f"def {method_name}(")
    if start == -1:
        return ""
    end = text.find("\n    def ", start + 1)
    return text[start:end] if end != -1 else text[start:]


# ---------------------------------------------------------------------------
# Source-scan tests — call_api() debug branch fires log hook
# ---------------------------------------------------------------------------

class TestCallApiDebugFiresLogHook(unittest.TestCase):

    def setUp(self):
        self._body = _call_api_body(_ai_client_text())
        self._debug = _debug_block(self._body)

    def test_debug_block_exists(self):
        """_AI_DEBUG branch must be present in call_api."""
        self.assertIn("if _AI_DEBUG:", self._body,
                      "call_api must have an if _AI_DEBUG: branch")

    def test_fire_log_hook_called_in_debug_block(self):
        """DEF-P1-010: _fire_log_hook() must be called inside the _AI_DEBUG block."""
        self.assertIn("_fire_log_hook(", self._debug,
                      "_fire_log_hook must be called before raise RuntimeError in debug block")

    def test_fire_log_hook_before_raise(self):
        """_fire_log_hook must appear BEFORE raise RuntimeError in the debug block."""
        hook_pos = self._debug.find("_fire_log_hook(")
        raise_pos = self._debug.find("raise RuntimeError(")
        self.assertGreater(hook_pos, -1,
                           "_fire_log_hook call must be in debug block")
        self.assertGreater(raise_pos, hook_pos,
                           "raise RuntimeError must come AFTER _fire_log_hook call")

    def test_debug_entry_success_false(self):
        """Dry-run log entry must have success=False."""
        self.assertIn("success=False", self._debug,
                      "debug AILogEntry must set success=False")

    def test_debug_entry_has_error_msg(self):
        """Dry-run log entry must have a non-empty error_msg."""
        self.assertIn("error_msg=", self._debug,
                      "debug AILogEntry must set error_msg")
        # The error_msg must not be an empty string
        self.assertNotIn('error_msg=""', self._debug,
                         "debug AILogEntry error_msg must not be empty")

    def test_debug_entry_uses_feature_and_model(self):
        """Dry-run log entry must use the feature and effective_model variables."""
        self.assertIn("feature=feature", self._debug,
                      "debug AILogEntry must pass feature=feature")
        self.assertIn("model=effective_model", self._debug,
                      "debug AILogEntry must pass model=effective_model")

    def test_debug_entry_includes_prompt(self):
        """Dry-run log entry must capture the prompt so it appears in AI Log detail view."""
        self.assertIn("prompt=prompt", self._debug,
                      "debug AILogEntry must pass prompt=prompt")

    def test_real_api_path_also_fires_hook_on_success(self):
        """Success path (real API call) must also call _fire_log_hook."""
        # Find position after the debug block in the full body
        after_debug = self._body[self._body.find("    try:") :]
        self.assertIn("_fire_log_hook(entry)", after_debug,
                      "real API success path must call _fire_log_hook(entry)")

    def test_real_api_path_fires_hook_on_failure(self):
        """Failure path (real API call) must also call _fire_log_hook."""
        except_pos = self._body.rfind("except Exception")
        self.assertGreater(except_pos, -1, "call_api must have an except Exception block")
        after_except = self._body[except_pos:]
        self.assertIn("_fire_log_hook(entry)", after_except,
                      "real API failure path must call _fire_log_hook(entry)")


# ---------------------------------------------------------------------------
# Source-scan tests — dashboard signal wiring
# ---------------------------------------------------------------------------

class TestDashboardAiLogWiring(unittest.TestCase):

    def test_ai_log_signal_connected_in_connect_signals(self):
        """bridge.ai_log_entry must be connected to _on_ai_log_entry in _connect_signals."""
        body = _method_body(_dashboard_text(), "_connect_signals")
        self.assertIn("ai_log_entry.connect", body,
                      "_connect_signals must connect the ai_log_entry signal")
        self.assertIn("_on_ai_log_entry", body,
                      "_connect_signals must connect to _on_ai_log_entry slot")

    def test_build_ai_log_tab_loads_db_history(self):
        """_build_ai_log_tab must load DB history via get_ai_interactions on startup."""
        body = _method_body(_dashboard_text(), "_build_ai_log_tab")
        self.assertIn("get_ai_interactions", body,
                      "_build_ai_log_tab must call get_ai_interactions to load history")

    def test_on_ai_log_entry_appends_to_list(self):
        """_on_ai_log_entry must append the entry to _ai_log_entries."""
        body = _method_body(_dashboard_text(), "_on_ai_log_entry")
        self.assertIn("_ai_log_entries", body,
                      "_on_ai_log_entry must reference _ai_log_entries")
        self.assertIn("append(entry)", body,
                      "_on_ai_log_entry must append the entry to the list")

    def test_on_ai_log_entry_calls_add_list_item(self):
        """_on_ai_log_entry must delegate display to _add_ai_log_list_item."""
        body = _method_body(_dashboard_text(), "_on_ai_log_entry")
        self.assertIn("_add_ai_log_list_item", body,
                      "_on_ai_log_entry must call _add_ai_log_list_item")


# ---------------------------------------------------------------------------
# DB round-trip tests — log_ai_interaction and get_ai_interactions
# ---------------------------------------------------------------------------

class TestAiInteractionsDbRoundTrip(unittest.TestCase):

    def setUp(self):
        from data.session_db import SessionDB
        self.db = SessionDB(":memory:")

    def tearDown(self):
        self.db.close()

    def test_log_ai_interaction_returns_id(self):
        """log_ai_interaction must return the new row id (integer > 0)."""
        row_id = self.db.log_ai_interaction({
            "timestamp": "2026-06-22T10:00:00",
            "feature": "Strategy Analysis",
            "model": "claude-opus-4-8",
            "prompt": "test prompt",
            "structured_payload": "{}",
            "response": "test response",
            "success": 1,
            "duration_ms": 1234,
            "prompt_tokens": 100,
            "response_tokens": 200,
            "estimated_cost": 0.003,
            "error_msg": "",
            "validation_warnings": "[]",
        })
        self.assertIsInstance(row_id, int)
        self.assertGreater(row_id, 0)

    def test_get_ai_interactions_reads_back_all_fields(self):
        """All required fields must survive the log→retrieve round-trip."""
        self.db.log_ai_interaction({
            "timestamp": "2026-06-22T10:00:00",
            "feature": "Driver Coaching",
            "model": "claude-opus-4-8",
            "prompt": "my prompt",
            "structured_payload": '{"key": "val"}',
            "response": "my response",
            "success": 1,
            "duration_ms": 999,
            "prompt_tokens": 50,
            "response_tokens": 75,
            "estimated_cost": 0.001,
            "error_msg": "",
            "validation_warnings": "[]",
        })
        rows = self.db.get_ai_interactions(limit=1)
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["feature"], "Driver Coaching")
        self.assertEqual(row["model"], "claude-opus-4-8")
        self.assertEqual(row["prompt"], "my prompt")
        self.assertEqual(row["response"], "my response")
        self.assertEqual(row["success"], 1)
        self.assertEqual(row["duration_ms"], 999)

    def test_failed_entry_round_trip(self):
        """DEF-P1-010: a failed/debug entry (success=False, error_msg set) must persist correctly."""
        self.db.log_ai_interaction({
            "timestamp": "2026-06-22T10:01:00",
            "feature": "Practice Analysis",
            "model": "claude-opus-4-8",
            "prompt": "intercepted prompt",
            "structured_payload": "{}",
            "response": "[AI_DEBUG dry-run — no API call made]",
            "success": 0,
            "duration_ms": 0,
            "prompt_tokens": 0,
            "response_tokens": 0,
            "estimated_cost": 0.0,
            "error_msg": "AI_DEBUG mode active — prompt intercepted, no API call made",
            "validation_warnings": "[]",
        })
        rows = self.db.get_ai_interactions(limit=1)
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["success"], 0,
                         "success=False must be stored as 0")
        self.assertIn("AI_DEBUG", row["error_msg"],
                      "error_msg must contain the AI_DEBUG description")
        self.assertEqual(row["duration_ms"], 0,
                         "dry-run entry must have duration_ms=0")

    def test_get_ai_interactions_returns_newest_first(self):
        """get_ai_interactions must return rows in newest-first order."""
        for i in range(3):
            self.db.log_ai_interaction({
                "timestamp": f"2026-06-22T10:0{i}:00",
                "feature": f"Feature{i}",
                "model": "claude-opus-4-8",
                "prompt": "", "structured_payload": "{}",
                "response": "", "success": 1,
                "duration_ms": i * 100,
                "prompt_tokens": 0, "response_tokens": 0,
                "estimated_cost": 0.0, "error_msg": "",
                "validation_warnings": "[]",
            })
        rows = self.db.get_ai_interactions(limit=10)
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0]["feature"], "Feature2",
                         "get_ai_interactions must return newest first")
        self.assertEqual(rows[2]["feature"], "Feature0")

    def test_get_ai_interactions_respects_limit(self):
        """get_ai_interactions limit parameter must cap the result set."""
        for i in range(5):
            self.db.log_ai_interaction({
                "timestamp": f"2026-06-22T10:0{i}:00",
                "feature": "F", "model": "m",
                "prompt": "", "structured_payload": "{}",
                "response": "", "success": 1,
                "duration_ms": 0,
                "prompt_tokens": 0, "response_tokens": 0,
                "estimated_cost": 0.0, "error_msg": "",
                "validation_warnings": "[]",
            })
        rows = self.db.get_ai_interactions(limit=2)
        self.assertEqual(len(rows), 2)


if __name__ == "__main__":
    unittest.main()
