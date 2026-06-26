"""Tests for Group 12a: BoP/tuning runtime propagation fix (DEF-P1-005).

DEF-P1-005: _run_practice_analysis() used _psc.get("tuning", True) as the
            default when the "tuning" key was absent from config["strategy"].
            This caused tuning_locked=False (unlocked) even when the event had
            Tuning=Off — because not bool(True) == False.
            Fix: default changed to False so absent key → tuning_locked=True
            (safe/locked default rather than accidentally unlocked).
"""
from __future__ import annotations

import pathlib
import unittest

_SRC = pathlib.Path(__file__).parent.parent


def _dashboard_text() -> str:
    return (_SRC / "ui" / "dashboard.py").read_text(encoding="utf-8")


def _method_body(text: str, method_name: str) -> str:
    start = text.find(f"def {method_name}(")
    if start == -1:
        return ""
    end = text.find("\n    def ", start + 1)
    return text[start:end] if end != -1 else text[start:]


# ---------------------------------------------------------------------------
# 12a-1 — default=False fix in _run_practice_analysis()
# ---------------------------------------------------------------------------

class TestTuningLockedDefault(unittest.TestCase):

    def setUp(self):
        self._body = _method_body(_dashboard_text(), "_run_practice_analysis")

    def test_tuning_locked_uses_false_default(self):
        """DEF-P1-005: default must be False so absent key → tuning_locked=True (safe)."""
        self.assertIn('_psc.get("tuning", False)', self._body,
                      '_run_practice_analysis must use get("tuning", False) not True')

    def test_tuning_locked_not_uses_true_default(self):
        """DEF-P1-005: must NOT have get("tuning", True) which unlocks when key absent."""
        self.assertNotIn('_psc.get("tuning", True)', self._body,
                         '_run_practice_analysis must not use get("tuning", True) as default')

    def test_tuning_locked_key_is_in_race_params(self):
        """tuning_locked must be built into race_params for prompt injection."""
        self.assertIn('"tuning_locked"', self._body,
                      '_run_practice_analysis must include "tuning_locked" in race_params')

    def test_allowed_tuning_key_is_in_race_params(self):
        """allowed_tuning must be passed to the AI prompt builder."""
        self.assertIn('"allowed_tuning"', self._body,
                      '_run_practice_analysis must include "allowed_tuning" in race_params')


# ---------------------------------------------------------------------------
# 12a-2 — silent except replaced with traceback logging
# ---------------------------------------------------------------------------

class TestOnEventSetActiveExceptionLogging(unittest.TestCase):

    def setUp(self):
        self._body = _method_body(_dashboard_text(), "_on_event_set_active")

    def test_no_bare_except_pass(self):
        """DEF-P1-005: _on_event_set_active must not silently swallow exceptions."""
        lines = self._body.splitlines()
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped == "pass":
                prev = lines[i - 1].strip() if i > 0 else ""
                self.assertFalse(
                    prev.startswith("except Exception"),
                    "_on_event_set_active must not have bare 'except Exception: pass' — "
                    "silent swallowing hides the root cause of DEF-P1-005"
                )

    def test_except_logs_traceback(self):
        """DEF-P1-005: exception handler must log a traceback for diagnosability."""
        self.assertIn("traceback", self._body,
                      "_on_event_set_active except block must call traceback.print_exc()")


# ---------------------------------------------------------------------------
# 12a-3 — strat reference vs copy (regression guard)
# ---------------------------------------------------------------------------

class TestStratIsReference(unittest.TestCase):
    """Verify _on_event_set_active() writes tuning into config via a reference."""

    def setUp(self):
        self._body = _method_body(_dashboard_text(), "_on_event_set_active")

    def test_uses_setdefault_for_strat(self):
        """strat must be obtained via setdefault() so it IS a reference into _config."""
        self.assertIn('setdefault("strategy", {})', self._body,
                      "_on_event_set_active must use setdefault to get a reference, not .get()")

    def test_tuning_written_to_strat(self):
        """strat["tuning"] must be written so the key exists for _run_practice_analysis."""
        self.assertIn('strat["tuning"]', self._body,
                      '_on_event_set_active must write strat["tuning"] so the key is present')

    def test_bop_written_to_strat(self):
        """strat["bop"] must be written alongside tuning."""
        self.assertIn('strat["bop"]', self._body,
                      '_on_event_set_active must write strat["bop"]')


# ---------------------------------------------------------------------------
# 12a-4 — GT7_AI_DEBUG context print
# ---------------------------------------------------------------------------

class TestDebugContextPrint(unittest.TestCase):

    def setUp(self):
        self._body = _method_body(_dashboard_text(), "_run_practice_analysis")

    def test_debug_guard_checks_gt7_ai_debug_env(self):
        """Debug output must be gated by GT7_AI_DEBUG environment variable."""
        self.assertIn("GT7_AI_DEBUG", self._body,
                      "_run_practice_analysis must gate debug output on GT7_AI_DEBUG env var")

    def test_debug_prints_tuning_locked(self):
        """Debug output must include tuning_locked value."""
        self.assertIn("tuning_locked", self._body,
                      "_run_practice_analysis debug block must show tuning_locked")

    def test_debug_prints_bop(self):
        """Debug output must include bop value."""
        self.assertIn("bop", self._body,
                      "_run_practice_analysis debug block must show bop flag")


if __name__ == "__main__":
    unittest.main()
