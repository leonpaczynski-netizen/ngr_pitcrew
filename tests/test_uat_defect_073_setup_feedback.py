"""UAT remediation — DEF-UAT-073-009 (partial): Setup Builder recommendation actions give visible feedback.

The Apply-in-Game / Values-Entered / Start-Validation actions previously only reached an off-screen event
log, so the buttons looked dead. The recommendation view now shows an explicit, visible confirmation line
when an action fires, and clears it when a fresh recommendation is rendered.
"""
from __future__ import annotations

import os

import pytest


@pytest.fixture(scope="module")
def qapp():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    try:
        from PyQt6.QtWidgets import QApplication
    except Exception:
        pytest.skip("PyQt6 not available")
    return QApplication.instance() or QApplication([])


def test_action_feedback_is_visible(qapp):
    from ui.setup_recommendation_view import SetupRecommendationView
    v = SetupRecommendationView()
    assert hasattr(v, "_action_feedback_lbl")
    v.show_action_feedback("Applied in game — active baseline.")
    assert "Applied in game" in v._action_feedback_lbl.text()


def test_feedback_clears_on_new_recommendation(qapp):
    from ui.setup_recommendation_view import SetupRecommendationView
    from ui.setup_recommendation_vm import build_recommendation_vm, HeaderInfo
    v = SetupRecommendationView()
    v.show_action_feedback("Validation started.")
    assert v._action_feedback_lbl.text()
    v.set_vm(build_recommendation_vm({}, header=HeaderInfo(
        car="c", track="t", layout="l", setup_name="s", revision="1", active_setup=""),
        status_approved=False))
    assert v._action_feedback_lbl.text() == ""   # stale confirmation cleared


def test_show_action_feedback_never_raises(qapp):
    from ui.setup_recommendation_view import SetupRecommendationView
    v = SetupRecommendationView()
    v.show_action_feedback(None)          # defensive
    v.show_action_feedback("x", "bogus-tone")


def test_all_actions_disabled_without_a_recommendation(qapp):
    # DEF-073-009: with nothing loaded, EVERY action must be disabled (they used to
    # look clickable but do nothing).
    from ui.setup_recommendation_view import SetupRecommendationView
    v = SetupRecommendationView()
    for b in (v._btn_apply, v._btn_values, v._btn_validate,
              v._btn_feedback, v._btn_reject, v._btn_lock):
        assert b.isEnabled() is False


def test_all_actions_enabled_with_a_recommendation(qapp):
    from ui.setup_recommendation_view import SetupRecommendationView
    v = SetupRecommendationView()
    v._set_actions_enabled(True)
    for b in (v._btn_apply, v._btn_values, v._btn_validate,
              v._btn_feedback, v._btn_reject, v._btn_lock):
        assert b.isEnabled() is True


def test_mark_validation_started_makes_an_in_view_change(qapp):
    # DEF-073-009: Start Validation must visibly move the workflow — header Status
    # reads 'Validating' and the view focuses the Test Plan tab.
    from ui.setup_recommendation_view import SetupRecommendationView
    v = SetupRecommendationView()
    v.mark_validation_started()
    assert "Validating" in v._h_labels["Status"].text()
    assert v._tabs.tabText(v._tabs.currentIndex()) == "Test Plan"
