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

    # AI Snapshot Migration: the DEF-P1-005 derivation moved into
    # build_practice_analysis_snapshot (data/ai_context_snapshot.py). These
    # tests keep guarding the same invariants at their new home: the method
    # routes through the snapshot, and an absent tuning key still means LOCKED.

    def test_tuning_locked_uses_false_default(self):
        """DEF-P1-005: absent tuning key → tuning_locked=True (safe default)."""
        from data.ai_context_snapshot import build_practice_analysis_snapshot
        rp = build_practice_analysis_snapshot(
            legacy_strategy={"track": "T"},  # no "tuning" key anywhere
            fuel_burn_override=2.5).race_params_dict()
        self.assertTrue(rp["tuning_locked"],
                        'practice analysis must treat an absent tuning flag as LOCKED')

    def test_tuning_locked_not_uses_true_default(self):
        """DEF-P1-005: the practice path must not silently unlock when key absent."""
        self.assertNotIn('_psc.get("tuning", True)', self._body,
                         '_run_practice_analysis must not use get("tuning", True) as default')
        # And behaviourally: tuning=False must stay locked, tuning=True unlocked.
        from data.ai_context_snapshot import build_practice_analysis_snapshot
        locked = build_practice_analysis_snapshot(
            legacy_strategy={"track": "T", "tuning": False},
            fuel_burn_override=2.5).race_params_dict()
        unlocked = build_practice_analysis_snapshot(
            legacy_strategy={"track": "T", "tuning": True},
            fuel_burn_override=2.5).race_params_dict()
        self.assertTrue(locked["tuning_locked"])
        self.assertFalse(unlocked["tuning_locked"])

    def test_tuning_locked_key_is_in_race_params(self):
        """tuning_locked must be built into race_params for prompt injection."""
        from data.ai_context_snapshot import build_practice_analysis_snapshot
        rp = build_practice_analysis_snapshot(
            legacy_strategy={"track": "T"}, fuel_burn_override=2.5).race_params_dict()
        self.assertIn("tuning_locked", rp)

    def test_allowed_tuning_key_is_in_race_params(self):
        """allowed_tuning must be passed to the AI prompt builder."""
        from data.ai_context_snapshot import build_practice_analysis_snapshot
        rp = build_practice_analysis_snapshot(
            legacy_strategy={"track": "T", "allowed_tuning_categories": ["aero"]},
            fuel_burn_override=2.5).race_params_dict()
        self.assertEqual(rp["allowed_tuning"], ["aero"])


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
    """Verify the Set-as-Active fan-out writes tuning into config via a reference.

    Legacy Fan-Out Removal Phase 4 (2026-07-03): the strat-write block moved
    verbatim from _on_event_set_active into _fanout_event_to_strategy (invoked
    by both Set-as-Active and the save-path re-sync). Same invariants, new home.
    """

    def setUp(self):
        self._body = _method_body(_dashboard_text(), "_fanout_event_to_strategy")

    def test_uses_setdefault_for_strat(self):
        """strat must be obtained via setdefault() so it IS a reference into _config."""
        self.assertIn('setdefault("strategy", {})', self._body,
                      "the fan-out must use setdefault to get a reference, not .get()")

    def test_tuning_written_to_strat(self):
        """Rule-cache deletion pin (2026-07-04): tuning is NO LONGER cached.

        The original reason ("so the key exists for _run_practice_analysis")
        is obsolete — practice analysis reads the frozen AI snapshot, whose
        CONTEXTS source takes tuning DB-first from EventContext whenever an
        event is active; the LEGACY_ONLY fallback only fires with no event, in
        which case the fan-out never ran anyway."""
        self.assertNotIn('strat["tuning"]', self._body,
                         "tuning must not be re-cached in config['strategy']")

    def test_bop_written_to_strat(self):
        """Rule-cache deletion pin (2026-07-04): bop is NO LONGER cached
        (DB-only via EventContext — same reasoning as tuning)."""
        self.assertNotIn('strat["bop"]', self._body,
                         "bop must not be re-cached in config['strategy']")


if __name__ == "__main__":
    unittest.main()
