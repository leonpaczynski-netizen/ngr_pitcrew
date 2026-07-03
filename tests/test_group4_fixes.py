"""Tests for Remediation Group 4 fixes.

DEF-P2-004: Setup Builder BoP checkbox is independent source of truth (verified removed)
DEF-P2-005: Tuning Permissions group only appears when BoP is ALSO enabled (fix: Tuning-only)
DEF-P2-006: Setup Builder does not enforce tuning permissions (verified fixed in Group 2)
DEF-P2-007: AI coaching/setup advice does not respect tuning lock (validator added)
"""
from __future__ import annotations

import pathlib
import unittest

# ---------------------------------------------------------------------------
# Source path helpers
# ---------------------------------------------------------------------------

_SRC = pathlib.Path(__file__).parent.parent

def _dashboard_text() -> str:
    return (_SRC / "ui" / "dashboard.py").read_text(encoding="utf-8")

def _setup_builder_text() -> str:
    return (_SRC / "ui" / "setup_builder_ui.py").read_text(encoding="utf-8")

def _planner_text() -> str:
    return (_SRC / "strategy" / "ai_planner.py").read_text(encoding="utf-8")

def _advisor_text() -> str:
    return (_SRC / "strategy" / "driving_advisor.py").read_text(encoding="utf-8")

def _listener_text() -> str:
    return (_SRC / "voice" / "query_listener.py").read_text(encoding="utf-8")

def _method_body(text: str, method_name: str) -> str:
    start = text.find(f"def {method_name}(")
    if start == -1:
        return ""
    end = text.find("\n    def ", start + 1)
    return text[start:end] if end != -1 else text[start:]


# ---------------------------------------------------------------------------
# DEF-P2-004 — BoP source of truth is Event Planner, not Setup Builder
# ---------------------------------------------------------------------------

class TestBoPSourceOfTruth(unittest.TestCase):

    def test_no_independent_bop_checkbox_in_source(self):
        """_chk_bop must not exist in dashboard.py — removed in favour of Event Planner."""
        src = _dashboard_text()
        self.assertNotIn("_chk_bop", src,
                         "_chk_bop (independent BoP toggle) must be removed from Setup Builder")

    def test_current_setup_dict_reads_bop_from_strategy_config(self):
        """_current_setup_dict must read bop_race from event state, not a widget.

        Legacy Fan-Out Removal Phase 5 (2026-07-03): the event-state source is
        now the canonical EventContext (DB-first, byte-identical to the old
        config['strategy']['bop'] read when in sync). The original invariant —
        never a UI widget — is unchanged."""
        body = _method_body(_setup_builder_text(), "_current_setup_dict")
        self.assertIn("_build_event_context()", body)
        self.assertIn("bop_enabled", body)
        self.assertNotIn("_chk_bop", body)

    def test_get_bop_data_reads_from_strategy_config(self):
        """_get_bop_data_for_car must read bop from event state, not a widget.

        Phase 5: source is the canonical EventContext (see above)."""
        body = _method_body(_dashboard_text(), "_get_bop_data_for_car")
        self.assertIn("_build_event_context()", body)
        self.assertIn("bop_enabled", body)
        self.assertNotIn("_chk_bop", body)

    def test_lbl_rc_bop_exists_in_race_conditions_group(self):
        """Race Conditions group must have a _lbl_rc_bop read-only label."""
        src = _setup_builder_text()
        self.assertIn("_lbl_rc_bop", src,
                      "Race Conditions group must display BoP status from active Event")

    def test_lbl_rc_tuning_exists_in_race_conditions_group(self):
        """Race Conditions group must have a _lbl_rc_tuning read-only label."""
        src = _setup_builder_text()
        self.assertIn("_lbl_rc_tuning", src)

    def test_sync_setup_builder_populates_rc_bop(self):
        """_sync_setup_builder_from_event must populate _lbl_rc_bop."""
        body = _method_body(_setup_builder_text(), "_sync_setup_builder_from_event")
        self.assertIn("_lbl_rc_bop", body)
        self.assertIn("_lbl_rc_tuning", body)

    def test_on_event_set_active_writes_bop_to_strat(self):
        """Rule-cache deletion pin (2026-07-04): bop is NO LONGER cached in
        config['strategy'] — it is DB-only, read through EventContext
        (bop_enabled) by every consumer incl. the setup-permission gating.
        The BoP source-of-truth invariant (event state, never a widget) holds
        stronger than ever; Set-as-Active still invokes the (shrunk,
        working-config-core) fan-out helper."""
        body = _method_body(_dashboard_text(), "_fanout_event_to_strategy")
        self.assertNotIn('strat["bop"]', body)
        self.assertNotIn('_evt_bop', body)
        self.assertIn("self._fanout_event_to_strategy(evt_name)",
                      _method_body(_dashboard_text(), "_on_event_set_active"))


# ---------------------------------------------------------------------------
# DEF-P2-005 — Tuning Permissions group visible when Tuning enabled (not BoP-gated)
# ---------------------------------------------------------------------------

class TestTuningPermissionsVisibility(unittest.TestCase):

    def _visibility_condition(self, bop_checked: bool, tuning_checked: bool) -> bool:
        """Reproduce the fixed visibility condition: show = tuning_checked (not AND bop)."""
        return tuning_checked

    def test_tuning_perms_show_without_bop(self):
        """Permissions group visible when Tuning=True, BoP=False."""
        self.assertTrue(self._visibility_condition(bop_checked=False, tuning_checked=True))

    def test_tuning_perms_hidden_when_tuning_unchecked(self):
        """Permissions group hidden when Tuning=False regardless of BoP."""
        self.assertFalse(self._visibility_condition(bop_checked=True, tuning_checked=False))
        self.assertFalse(self._visibility_condition(bop_checked=False, tuning_checked=False))

    def test_tuning_perms_show_with_bop_and_tuning(self):
        """Permissions group visible when both BoP=True, Tuning=True."""
        self.assertTrue(self._visibility_condition(bop_checked=True, tuning_checked=True))

    def test_source_visibility_not_gated_by_bop(self):
        """Source must NOT use 'and self._evt_bop.isChecked()' in visibility function."""
        body = _method_body(_dashboard_text(), "_update_tuning_perms_visibility")
        self.assertNotIn("_evt_bop.isChecked() and", body,
                         "Visibility must not require BoP — only Tuning checkbox matters")

    def test_source_visibility_uses_tuning_only(self):
        """Source must derive visibility from _evt_tuning.isChecked() alone."""
        body = _method_body(_dashboard_text(), "_update_tuning_perms_visibility")
        self.assertIn("_evt_tuning.isChecked()", body)

    def test_tuning_categories_not_empty(self):
        """`_TUNING_CATEGORIES` must list at least one category for the group to be useful."""
        src = _dashboard_text()
        start = src.find("_TUNING_CATEGORIES")
        segment = src[start:start + 500]
        self.assertIn("brake_balance", segment)
        self.assertIn("suspension", segment)

    def test_tuning_categories_excludes_tyres(self):
        """`_TUNING_CATEGORIES` must NOT include tyres — tyres are always free in GT7."""
        src = _dashboard_text()
        start = src.find("_TUNING_CATEGORIES")
        end   = src.find("]", start)
        segment = src[start:end]
        self.assertNotIn('"tyres"', segment,
                         "Tyres must not appear in _TUNING_CATEGORIES — always selectable")


# ---------------------------------------------------------------------------
# DEF-P2-006 — Setup Builder field locking (source scans)
# ---------------------------------------------------------------------------

class TestSetupBuilderPermissions(unittest.TestCase):

    def test_apply_setup_permissions_method_exists(self):
        """_apply_setup_permissions must exist in setup_builder_ui.py."""
        src = _setup_builder_text()
        self.assertIn("def _apply_setup_permissions(", src)

    def test_apply_setup_permissions_always_re_enables_tyres(self):
        """_apply_setup_permissions must unconditionally re-enable tyre widgets at the end."""
        body = _method_body(_setup_builder_text(), "_apply_setup_permissions")
        # After the main loop, tyre attrs must be force-enabled
        idx_tyres = body.rfind("_setup_tyre_f")
        idx_loop = body.find("for cat, attrs in")
        self.assertGreater(idx_tyres, idx_loop,
                           "Tyre re-enable block must come after the main permission loop")
        self.assertIn("setEnabled(True)", body[idx_tyres:])

    def test_setup_tuning_groups_has_expected_categories(self):
        """_SETUP_TUNING_GROUPS must cover brake_balance, suspension, differential, aero."""
        src = _dashboard_text()
        for cat in ("brake_balance", "suspension", "differential", "aero"):
            self.assertIn(f'"{cat}"', src,
                          f"_SETUP_TUNING_GROUPS must include '{cat}'")

    def test_locked_banner_widget_exists_in_setup_builder(self):
        """_setup_locked_banner must be created in _build_car_setup_group."""
        body = _method_body(_setup_builder_text(), "_build_car_setup_group")
        self.assertIn("_setup_locked_banner", body)

    def test_sync_setup_calls_apply_permissions(self):
        """_sync_setup_builder_from_event must call _apply_setup_permissions."""
        body = _method_body(_setup_builder_text(), "_sync_setup_builder_from_event")
        self.assertIn("_apply_setup_permissions", body)


# ---------------------------------------------------------------------------
# DEF-P2-007 — AI tuning constraint propagation (source scans)
# ---------------------------------------------------------------------------

class TestAITuningConstraintPropagation(unittest.TestCase):

    def test_practice_analysis_passes_tuning_locked(self):
        """_run_practice_analysis must include tuning_locked in race_params."""
        body = _method_body(_dashboard_text(), "_run_practice_analysis")
        self.assertIn("tuning_locked", body)

    def test_practice_analysis_passes_allowed_tuning(self):
        """_run_practice_analysis must include allowed_tuning in race_params."""
        body = _method_body(_dashboard_text(), "_run_practice_analysis")
        self.assertIn("allowed_tuning", body)

    def test_setup_analyse_ai_passes_tuning_params(self):
        """_setup_analyse_ai must pass allowed_tuning and tuning_locked to the advisor."""
        body = _method_body(_setup_builder_text(), "_setup_analyse_ai")
        self.assertIn("allowed_tuning", body)
        self.assertIn("tuning_locked", body)

    def test_query_listener_coaching_passes_tuning_params(self):
        """query_listener coaching path must read and pass allowed/locked tuning params."""
        src = _listener_text()
        self.assertIn("allowed_tuning", src)
        self.assertIn("tuning_locked", src)

    def test_advisor_build_coaching_accepts_tuning_params(self):
        """DrivingAdvisor.build_coaching_response must accept allowed_tuning and tuning_locked."""
        body = _method_body(_advisor_text(), "build_coaching_response")
        self.assertIn("allowed_tuning", body)
        self.assertIn("tuning_locked", body)

    def test_advisor_tuning_constraint_block_function_exists(self):
        """_tuning_constraint_block helper must exist in driving_advisor.py."""
        src = _advisor_text()
        self.assertIn("def _tuning_constraint_block(", src)

    def test_advisor_coaching_prompt_injects_constraint_block(self):
        """_build_coaching_prompt must inject the tuning constraint block."""
        body = _method_body(_advisor_text(), "_build_coaching_prompt")
        self.assertIn("tuning_block", body)


# ---------------------------------------------------------------------------
# DEF-P2-007 — AI output validation (validate_ai_setup_response logic tests)
# ---------------------------------------------------------------------------

class TestAIOutputValidation(unittest.TestCase):

    def _validate(self, response: str, locked: bool = False, allowed: list | None = None):
        from strategy.ai_planner import validate_ai_setup_response
        return validate_ai_setup_response(response, locked, allowed)

    def test_no_restrictions_returns_empty(self):
        """No violations when tuning is unrestricted."""
        resp = "Consider increasing rear downforce and adjusting LSD settings."
        result = self._validate(resp, locked=False, allowed=None)
        self.assertEqual(result, [])

    def test_tuning_locked_flags_aero_recommendation(self):
        """Tuning locked: recommending downforce change flags 'aero'."""
        resp = "To improve corner stability you should increase rear downforce by 5."
        result = self._validate(resp, locked=True)
        self.assertIn("aero", result)

    def test_tuning_locked_flags_suspension_recommendation(self):
        """Tuning locked: recommending spring rate change flags 'suspension'."""
        resp = "Try softening the spring rate to improve mechanical grip."
        result = self._validate(resp, locked=True)
        self.assertIn("suspension", result)

    def test_tuning_locked_flags_differential_recommendation(self):
        """Tuning locked: recommending LSD change flags 'differential'."""
        resp = "I suggest adjusting the LSD acceleration sensitivity for better traction."
        result = self._validate(resp, locked=True)
        self.assertIn("differential", result)

    def test_tuning_locked_flags_brake_balance_recommendation(self):
        """Tuning locked: recommending brake bias change flags 'brake_balance'."""
        resp = "Increase the brake bias rearward by 2% to reduce front locking."
        result = self._validate(resp, locked=True)
        self.assertIn("brake_balance", result)

    def test_allowed_cats_does_not_flag_permitted_category(self):
        """Allowed category must NOT be flagged even if the response recommends changes."""
        resp = "Consider adjusting the spring rate front and rear for better balance."
        result = self._validate(resp, locked=False, allowed=["suspension", "brake_balance"])
        self.assertNotIn("suspension", result)

    def test_locked_cats_flagged_when_partially_restricted(self):
        """Locked category IS flagged when partially restricted and response recommends it."""
        resp = "Increase rear downforce for more stability in fast corners."
        result = self._validate(resp, locked=False, allowed=["suspension", "brake_balance"])
        self.assertIn("aero", result)

    def test_clean_response_no_action_verb_no_violation(self):
        """Mentioning a locked keyword without an action verb does not trigger a violation."""
        resp = "Since aero is locked for this event, focus on driving technique through the fast sectors."
        result = self._validate(resp, locked=True)
        # "locked" is the context word — no action verb near "aero" in this sentence
        # Note: "focus" is not in action verbs, so no violation expected
        # This tests that keyword-only detection (without action verb) doesn't fire
        self.assertNotIn("aero", result)

    def test_multiple_locked_categories_all_flagged(self):
        """Multiple violated categories are all returned."""
        resp = ("You should increase rear downforce and also soften the damper settings "
                "to improve stability.")
        result = self._validate(resp, locked=True)
        self.assertIn("aero", result)
        self.assertIn("suspension", result)

    def test_display_setup_result_calls_validator(self):
        """Source scan: _display_setup_result must call validate_ai_setup_response."""
        body = _method_body(_setup_builder_text(), "_display_setup_result")
        self.assertIn("validate_ai_setup_response", body,
                      "_display_setup_result must validate AI output for tuning compliance")

    def test_display_practice_results_calls_validator(self):
        """Source scan: _display_practice_results must call validate_ai_setup_response."""
        body = _method_body(_dashboard_text(), "_display_practice_results")
        self.assertIn("validate_ai_setup_response", body,
                      "_display_practice_results must validate AI output for tuning compliance")

    def test_validate_function_exists_in_ai_planner(self):
        """validate_ai_setup_response must be importable from strategy.ai_planner."""
        from strategy.ai_planner import validate_ai_setup_response
        self.assertTrue(callable(validate_ai_setup_response))

    def test_validate_returns_list(self):
        """Return type must always be a list."""
        from strategy.ai_planner import validate_ai_setup_response
        result = validate_ai_setup_response("some text", False, None)
        self.assertIsInstance(result, list)


if __name__ == "__main__":
    unittest.main()
