"""Tests for Group 12c: AI Log display fixes (DEF-P2-021).

DEF-P2-021 (updated from Group 11): Three issues remained after Group 11:
  1. Timestamp: entry.timestamp[11:19] showed only HH:MM:SS — lost the date.
     Fix: entry.timestamp[:19].replace("T", " ") → YYYY-MM-DD HH:MM:SS.
  2. Status: "✓"/"✗" too terse. Fix: "✓ OK" / "✗ FAIL" / "⊘ DRY-RUN".
     DRY-RUN detected when duration_ms==0 and "AI_DEBUG" in error_msg.
  3. Auto-select: setCurrentRow() on a hidden widget has no visual effect.
     Fix: _ai_log_pending_select flag set in _on_ai_log_entry(); flushed
     via _flush_ai_log_pending_select() when AI Log tab (index 11) becomes active.
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
# 12c-1 — Timestamp shows full date+time
# ---------------------------------------------------------------------------

class TestAiLogTimestampFormat(unittest.TestCase):

    def setUp(self):
        self._body = _method_body(_dashboard_text(), "_add_ai_log_list_item")

    def test_timestamp_uses_replace_T(self):
        """DEF-P2-021: timestamp must replace 'T' separator for YYYY-MM-DD HH:MM:SS format."""
        self.assertIn('replace("T", " ")', self._body,
                      '_add_ai_log_list_item must call .replace("T", " ") on timestamp')

    def test_timestamp_uses_slice_19(self):
        """DEF-P2-021: timestamp slice must use [:19] to include date portion."""
        self.assertIn("[:19]", self._body,
                      '_add_ai_log_list_item must use timestamp[:19] to include YYYY-MM-DD')

    def test_timestamp_not_uses_11_19_slice(self):
        """DEF-P2-021: must NOT use [11:19] which strips the date."""
        self.assertNotIn("[11:19]", self._body,
                         '_add_ai_log_list_item must not use [11:19] — that hides the date')


# ---------------------------------------------------------------------------
# 12c-2 — Status text is descriptive
# ---------------------------------------------------------------------------

class TestAiLogStatusText(unittest.TestCase):

    def setUp(self):
        self._body = _method_body(_dashboard_text(), "_add_ai_log_list_item")

    def test_status_ok_text(self):
        """DEF-P2-021: success status must read '✓ OK' not bare '✓'."""
        self.assertIn("✓ OK", self._body,
                      '_add_ai_log_list_item status for success must be "✓ OK"')

    def test_status_fail_text(self):
        """DEF-P2-021: failure status must read '✗ FAIL' not bare '✗'."""
        self.assertIn("✗ FAIL", self._body,
                      '_add_ai_log_list_item status for failure must be "✗ FAIL"')

    def test_status_dry_run_text(self):
        """DEF-P2-021: dry-run status must read '⊘ DRY-RUN'."""
        self.assertIn("⊘ DRY-RUN", self._body,
                      '_add_ai_log_list_item must distinguish dry-run calls with "⊘ DRY-RUN"')

    def test_dry_run_detected_via_ai_debug_in_error(self):
        """DEF-P2-021: dry-run detection must check for 'AI_DEBUG' in error_msg."""
        self.assertIn("AI_DEBUG", self._body,
                      '_add_ai_log_list_item must check error_msg for "AI_DEBUG" to detect dry-run')

    def test_dry_run_detected_via_zero_duration(self):
        """DEF-P2-021: dry-run detection must also check duration_ms == 0."""
        self.assertIn("duration_ms == 0", self._body,
                      '_add_ai_log_list_item must check duration_ms == 0 for dry-run detection')


# ---------------------------------------------------------------------------
# 12c-3 — Pending select flag and flush
# ---------------------------------------------------------------------------

class TestAiLogPendingSelect(unittest.TestCase):

    def setUp(self):
        self._text = _dashboard_text()

    def test_on_ai_log_entry_sets_pending_flag(self):
        """DEF-P2-021: _on_ai_log_entry must set _ai_log_pending_select=True."""
        body = _method_body(self._text, "_on_ai_log_entry")
        self.assertIn("_ai_log_pending_select", body,
                      "_on_ai_log_entry must set _ai_log_pending_select flag for deferred select")

    def test_flush_method_exists(self):
        """DEF-P2-021: _flush_ai_log_pending_select helper must exist."""
        body = _method_body(self._text, "_flush_ai_log_pending_select")
        self.assertTrue(body,
                        "_flush_ai_log_pending_select method must exist to apply deferred selection")

    def test_flush_reads_pending_flag(self):
        """DEF-P2-021: flush must check _ai_log_pending_select before acting."""
        body = _method_body(self._text, "_flush_ai_log_pending_select")
        self.assertIn("_ai_log_pending_select", body,
                      "_flush_ai_log_pending_select must read _ai_log_pending_select flag")

    def test_flush_calls_set_current_row(self):
        """DEF-P2-021: flush must call setCurrentRow to apply the deferred selection."""
        body = _method_body(self._text, "_flush_ai_log_pending_select")
        self.assertIn("setCurrentRow", body,
                      "_flush_ai_log_pending_select must call setCurrentRow(count-1)")

    def test_on_tab_changed_calls_flush_for_ai_log_tab(self):
        """DEF-P2-021: _on_tab_changed must flush pending select when the AI Log
        tab is opened. (Tab Navigation Refactor 2026-07-03: dispatch is now by
        stable tab key TAB_AI_LOG instead of the old hard-coded index 11 —
        same invariant, key-based home.)"""
        body = _method_body(self._text, "_on_tab_changed")
        self.assertIn("TAB_AI_LOG", body,
                      "_on_tab_changed must handle the AI Log tab (TAB_AI_LOG key)")
        self.assertIn("_flush_ai_log_pending_select", body,
                      "_on_tab_changed must call _flush_ai_log_pending_select for the AI Log tab")

    def test_flush_clears_flag_after_running(self):
        """DEF-P2-021: flush must reset _ai_log_pending_select to False to avoid re-selecting."""
        body = _method_body(self._text, "_flush_ai_log_pending_select")
        self.assertIn("False", body,
                      "_flush_ai_log_pending_select must set _ai_log_pending_select=False after flush")


if __name__ == "__main__":
    unittest.main()
