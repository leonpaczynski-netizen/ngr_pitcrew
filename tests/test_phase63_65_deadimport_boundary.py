"""PR #75 correction — explicit positive/negative boundary tests for the dead-import check.

The Phase 60-62 slice fixed ``test_diagnostic_tab_cleanup.test_dead_imports_removed`` from a plain-substring
check (which false-positived on the live ``_btn_seg_rename`` / ``_tm_seg_rename`` controls) to a leading
word-boundary check. These tests pin that boundary behaviour so a future regression cannot silently
reintroduce either failure mode.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).parent.parent

# the same aliases the diagnostic-cleanup test guards.
_DEAD_ALIASES = ("_get_review_btns", "_seg_confirm", "_seg_rename", "_seg_reject", "_seg_needs_laps",
                 "_seg_split", "_seg_merge", "_export_seg_review", "_rev_btn_")


def _boundary_hit(alias: str, src: str) -> bool:
    """The corrected check: a leading word boundary before the alias."""
    return bool(re.search(rf"\b{re.escape(alias)}", src))


# --- negative: live controls must NOT be flagged --- #
def test_live_controls_are_not_false_positives():
    # these are the current, wired Track Modelling controls/handlers that merely CONTAIN a guarded substring
    for live in ("_btn_seg_rename", "self._tm_seg_rename", "_btn_seg_reject", "_btn_seg_split",
                 "_btn_seg_merge"):
        src = f"        {live} = QPushButton('x')\n        {live}.clicked.connect(lambda: None)\n"
        for alias in ("_seg_rename", "_seg_reject", "_seg_split", "_seg_merge"):
            # the alias appears only as a trailing substring of the longer live identifier
            if alias in live:
                assert _boundary_hit(alias, src) is False, (
                    f"live control {live!r} must not be flagged by dead-alias {alias!r}")


# --- positive: genuine standalone dead aliases MUST be caught --- #
def test_genuine_dead_aliases_are_detected():
    for alias in _DEAD_ALIASES:
        src = f"from ui.legacy import {alias}\n{alias}()\n"
        assert _boundary_hit(alias, src) is True, f"dead alias {alias!r} must be detected"


# --- the real file: still passes the corrected check --- #
def test_track_modelling_ui_has_no_standalone_dead_aliases():
    tm = (ROOT / "ui" / "track_modelling_ui.py").read_text(encoding="utf-8")
    for alias in _DEAD_ALIASES:
        assert not _boundary_hit(alias, tm), (
            f"standalone dead alias {alias!r} unexpectedly present in track_modelling_ui.py")


def test_live_seg_controls_still_present_in_track_modelling_ui():
    # sanity: the live controls that caused the original false positive are genuinely there
    tm = (ROOT / "ui" / "track_modelling_ui.py").read_text(encoding="utf-8")
    assert "_btn_seg_rename" in tm and "_tm_seg_rename" in tm
