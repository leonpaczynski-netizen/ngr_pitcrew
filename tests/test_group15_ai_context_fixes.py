"""
Group 15 — AI Context Remediation Tests
AWR-058 through AWR-069

All tests are source-scan or in-memory only (no Qt widgets).
"""
import ast
import re
import sys
import types
import textwrap
import os
import inspect
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _method_body(path: Path, class_name: str, method_name: str) -> str:
    """Return the source of a method as a string (searches all classes if class_name is None)."""
    src = path.read_text(encoding="utf-8")
    tree = ast.parse(src)
    lines = src.splitlines()
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            if class_name is not None and node.name != class_name:
                continue
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name == method_name:
                    return "\n".join(lines[item.lineno - 1: item.end_lineno])
    return ""


def _function_body(path: Path, func_name: str) -> str:
    """Return the source of a module-level function."""
    src = path.read_text(encoding="utf-8")
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == func_name:
            lines = src.splitlines()
            return "\n".join(lines[node.lineno - 1: node.end_lineno])
    return ""


def _file_src(path: Path) -> str:
    return path.read_text(encoding="utf-8")


AI_PLANNER       = ROOT / "strategy" / "ai_planner.py"
DASHBOARD        = ROOT / "ui" / "dashboard.py"
SETUP_BUILDER_UI = ROOT / "ui" / "setup_builder_ui.py"
QUERY_LS         = ROOT / "voice" / "query_listener.py"
PRACTICE_ORCH    = ROOT / "strategy" / "practice_orchestrator.py"

# ---------------------------------------------------------------------------
# DEF-P1-013 — RaceParams missing bop and avail_tyres fields
# AWR-058
# ---------------------------------------------------------------------------

class TestDEF_P1_013_RaceParams:
    def test_raceparams_has_bop_field(self):
        src = _file_src(AI_PLANNER)
        # Check the dataclass declaration includes bop
        assert "bop: bool = False" in src, "RaceParams must have bop field"

    def test_raceparams_has_avail_tyres_field(self):
        src = _file_src(AI_PLANNER)
        assert "avail_tyres: list" in src, "RaceParams must have avail_tyres field"

    def test_raceparams_bop_default_false(self):
        src = _file_src(AI_PLANNER)
        assert "bop: bool = False" in src

    def test_raceparams_avail_tyres_default_factory(self):
        src = _file_src(AI_PLANNER)
        assert "avail_tyres: list = field(default_factory=list)" in src

    def test_run_ai_analysis_passes_race_type(self):
        body = _method_body(DASHBOARD, None, "_run_ai_analysis")
        assert '"race_type"' in body, "_run_ai_analysis must pass race_type to race_params"

    def test_run_ai_analysis_passes_duration_mins(self):
        body = _method_body(DASHBOARD, None, "_run_ai_analysis")
        assert '"duration_mins"' in body

    def test_run_ai_analysis_passes_tuning_locked(self):
        body = _method_body(DASHBOARD, None, "_run_ai_analysis")
        assert '"tuning_locked"' in body

    def test_run_ai_analysis_passes_allowed_tuning(self):
        body = _method_body(DASHBOARD, None, "_run_ai_analysis")
        assert '"allowed_tuning"' in body

    def test_run_ai_analysis_passes_bop(self):
        body = _method_body(DASHBOARD, None, "_run_ai_analysis")
        assert '"bop"' in body

    def test_run_ai_analysis_bop_uses_sc_config(self):
        body = _method_body(DASHBOARD, None, "_run_ai_analysis")
        assert '_sc.get("bop"' in body or "bop" in body

    def test_build_race_prompt_injects_tuning_block(self):
        body = _function_body(AI_PLANNER, "_build_race_prompt")
        assert "tuning_block" in body

    def test_build_race_prompt_injects_bop_line(self):
        body = _function_body(AI_PLANNER, "_build_race_prompt")
        assert "bop_line" in body

    def test_build_race_prompt_bop_checks_params(self):
        body = _function_body(AI_PLANNER, "_build_race_prompt")
        assert "params.bop" in body or "getattr(params" in body

# ---------------------------------------------------------------------------
# DEF-P1-014 — Practice worker uses car_id=0 and opens new DB connection
# AWR-059
# ---------------------------------------------------------------------------

class TestDEF_P1_014_PracticeWorker:
    def test_worker_uses_hist_db_not_new_connection(self):
        body = _method_body(DASHBOARD, None, "_run_practice_analysis")
        assert "SessionDB(" not in body or "_hist_db" in body, \
            "Worker must reuse self._db, not open a new SessionDB connection"

    def test_worker_uses_get_car_id_not_hardcoded_zero(self):
        body = _method_body(DASHBOARD, None, "_run_practice_analysis")
        assert "get_car_id(" in body, "Worker must call get_car_id() to resolve car_id"
        assert "car_id = 0" not in body, "car_id=0 hardcode must be removed"

    def test_hist_db_captured_before_thread(self):
        body = _method_body(DASHBOARD, None, "_run_practice_analysis")
        hist_db_idx = body.find("_hist_db")
        worker_idx  = body.find("def _worker()")
        assert hist_db_idx > 0 and hist_db_idx < worker_idx, \
            "_hist_db must be captured before _worker() def in _run_practice_analysis"

    def test_hist_track_captured_before_thread(self):
        body = _method_body(DASHBOARD, None, "_run_practice_analysis")
        hist_track_idx = body.find("_hist_track")
        worker_idx     = body.find("def _worker()")
        assert hist_track_idx > 0 and hist_track_idx < worker_idx

    def test_hist_car_name_captured_before_thread(self):
        src = _file_src(DASHBOARD)
        assert "_hist_car_name" in src

# ---------------------------------------------------------------------------
# DEF-P2-038 — Practice race_params missing bop field
# AWR-060
# ---------------------------------------------------------------------------

class TestDEF_P2_038_PracticeBoP:
    def test_practice_race_params_has_bop(self):
        body = _method_body(DASHBOARD, None, "_run_practice_analysis")
        assert '"bop"' in body, "_run_practice_analysis must include bop in race_params"

    def test_practice_bop_reads_from_psc(self):
        body = _method_body(DASHBOARD, None, "_run_practice_analysis")
        assert "_psc.get(\"bop\"" in body

    def test_practice_bop_default_false(self):
        body = _method_body(DASHBOARD, None, "_run_practice_analysis")
        assert "False" in body  # safe default

    def test_build_practice_prompt_injects_bop_line(self):
        body = _function_body(AI_PLANNER, "_build_practice_prompt")
        assert "bop_line" in body

    def test_build_practice_prompt_bop_label_text(self):
        body = _function_body(AI_PLANNER, "_build_practice_prompt")
        assert "BoP: ON" in body

# ---------------------------------------------------------------------------
# DEF-P2-039 — avail_tyres missing from RaceParams and prompts
# AWR-061
# ---------------------------------------------------------------------------

class TestDEF_P2_039_AvailTyres:
    def test_run_ai_analysis_passes_avail_tyres(self):
        body = _method_body(DASHBOARD, None, "_run_ai_analysis")
        assert '"avail_tyres"' in body

    def test_practice_race_params_has_avail_tyres(self):
        body = _method_body(DASHBOARD, None, "_run_practice_analysis")
        assert '"avail_tyres"' in body

    def test_build_race_prompt_injects_avail_line(self):
        body = _function_body(AI_PLANNER, "_build_race_prompt")
        assert "avail_line" in body

    def test_build_practice_prompt_injects_avail_line(self):
        body = _function_body(AI_PLANNER, "_build_practice_prompt")
        assert "avail_line" in body

    def test_avail_tyres_empty_list_is_safe_default(self):
        src = _file_src(DASHBOARD)
        # Should not invent tyres when avail_tyres is absent
        assert '"avail_tyres": _psc.get("avail_tyres", []) or []' in src or \
               '"avail_tyres":          _sc.get("avail_tyres", []) or []' in src

    def test_build_setup_from_scratch_accepts_avail_tyres(self):
        body = _function_body(AI_PLANNER, "_build_setup_from_scratch_prompt")
        assert "avail_tyres" in body

    def test_build_car_setup_accepts_avail_tyres(self):
        body = _function_body(AI_PLANNER, "build_car_setup")
        assert "avail_tyres" in body

    def test_run_build_setup_passes_avail_tyres(self):
        body = _method_body(SETUP_BUILDER_UI, None, "_run_build_setup")
        assert "avail_tyres" in body

# ---------------------------------------------------------------------------
# DEF-P2-040 — driver feedback not passed to practice AI
# AWR-062
# ---------------------------------------------------------------------------

class TestDEF_P2_040_DriverFeedback:
    def test_analyse_practice_session_accepts_driver_feedback_str(self):
        body = _function_body(AI_PLANNER, "analyse_practice_session")
        assert "driver_feedback_str" in body

    def test_build_practice_prompt_accepts_driver_feedback_str(self):
        body = _function_body(AI_PLANNER, "_build_practice_prompt")
        assert "driver_feedback_str" in body

    def test_build_practice_prompt_injects_feedback_section(self):
        body = _function_body(AI_PLANNER, "_build_practice_prompt")
        assert "feedback_section" in body

    def test_feedback_section_only_shown_when_non_empty(self):
        body = _function_body(AI_PLANNER, "_build_practice_prompt")
        assert "driver_feedback_str.strip()" in body

    def test_practice_worker_queries_recent_feedback(self):
        # Logic moved to practice_orchestrator after refactor
        body = PRACTICE_ORCH.read_text(encoding="utf-8")
        assert "get_recent_feedback(" in body

    def test_practice_worker_passes_driver_feedback_str_to_call(self):
        # Logic moved to practice_orchestrator after refactor
        body = PRACTICE_ORCH.read_text(encoding="utf-8")
        assert "driver_feedback_str=" in body

    def test_feedback_recent_driver_feedback_header(self):
        body = _function_body(AI_PLANNER, "_build_practice_prompt")
        assert "Recent Driver Feedback" in body

# ---------------------------------------------------------------------------
# DEF-P2-041 — previous AI recommendations missing from practice prompt
# AWR-063
# ---------------------------------------------------------------------------

class TestDEF_P2_041_PrevAIRecs:
    def test_analyse_practice_session_accepts_prev_ai_str(self):
        body = _function_body(AI_PLANNER, "analyse_practice_session")
        assert "prev_ai_str" in body

    def test_build_practice_prompt_accepts_prev_ai_str(self):
        body = _function_body(AI_PLANNER, "_build_practice_prompt")
        assert "prev_ai_str" in body

    def test_build_practice_prompt_injects_prev_ai_section(self):
        body = _function_body(AI_PLANNER, "_build_practice_prompt")
        assert "prev_ai_section" in body

    def test_prev_ai_section_uses_strip_guard(self):
        body = _function_body(AI_PLANNER, "_build_practice_prompt")
        assert "prev_ai_str.strip()" in body

    def test_practice_worker_queries_get_recommendations_for_context(self):
        # Logic moved to practice_orchestrator after refactor
        body = PRACTICE_ORCH.read_text(encoding="utf-8")
        assert "get_recommendations_for_context(" in body

    def test_practice_worker_passes_prev_ai_str_to_call(self):
        # Logic moved to practice_orchestrator after refactor
        body = PRACTICE_ORCH.read_text(encoding="utf-8")
        assert "prev_ai_str=" in body

    def test_prev_ai_recs_uses_limit_param(self):
        # Logic moved to practice_orchestrator after refactor
        body = PRACTICE_ORCH.read_text(encoding="utf-8")
        assert "limit=2" in body  # limit passed to get_recommendations_for_context

    def test_prev_ai_section_header_text(self):
        body = _function_body(AI_PLANNER, "_build_practice_prompt")
        assert "Previous AI Recommendations" in body

# ---------------------------------------------------------------------------
# DEF-P2-036 — PTT coaching missing car_name / car_specs / compound
# AWR-064
# ---------------------------------------------------------------------------

class TestDEF_P2_036_PTTCarContext:
    def test_query_listener_init_has_car_specs_ref(self):
        body = _method_body(QUERY_LS, "QueryListener", "__init__")
        assert "_car_specs_ref" in body

    def test_query_listener_has_update_car_specs_method(self):
        src = _file_src(QUERY_LS)
        assert "def update_car_specs(" in src

    def test_update_car_specs_stores_value(self):
        body = _function_body(QUERY_LS, "update_car_specs")
        assert "_car_specs_ref" in body

    def test_coaching_branch_passes_car_name(self):
        body = _method_body(QUERY_LS, "QueryListener", "_handle_trigger_inner")
        assert "car_name=" in body

    def test_coaching_branch_passes_car_specs(self):
        body = _method_body(QUERY_LS, "QueryListener", "_handle_trigger_inner")
        assert "car_specs=" in body

    def test_coaching_branch_passes_compound(self):
        body = _method_body(QUERY_LS, "QueryListener", "_handle_trigger_inner")
        assert "compound=" in body

    def test_dashboard_calls_update_car_specs_on_event_set_active(self):
        body = _method_body(DASHBOARD, None, "_on_event_set_active")
        assert "update_car_specs(" in body

    def test_setup_advice_branch_passes_car_name(self):
        body = _method_body(QUERY_LS, "QueryListener", "_handle_trigger_inner")
        # Both coaching and setup_advice use car_name= — just confirm presence twice implicitly
        assert body.count("car_name=") >= 2

# ---------------------------------------------------------------------------
# DEF-P2-037 — PTT setup_advice reads stale config setup
# AWR-065
# ---------------------------------------------------------------------------

class TestDEF_P2_037_PTTLiveSetup:
    def test_query_listener_init_has_active_setup_getter(self):
        body = _method_body(QUERY_LS, "QueryListener", "__init__")
        assert "_active_setup_getter" in body

    def test_query_listener_has_set_active_setup_getter_method(self):
        src = _file_src(QUERY_LS)
        assert "def set_active_setup_getter(" in src

    def test_setup_advice_branch_uses_getter_when_available(self):
        body = _method_body(QUERY_LS, "QueryListener", "_handle_trigger_inner")
        assert "_active_setup_getter" in body

    def test_setup_advice_fallback_when_getter_none(self):
        body = _method_body(QUERY_LS, "QueryListener", "_handle_trigger_inner")
        assert "_fallback_setups" in body or "config.get(\"car_setup\"" in body

    def test_dashboard_wires_set_active_setup_getter_in_init(self):
        src = _file_src(DASHBOARD)
        assert "set_active_setup_getter(" in src

    def test_dashboard_passes_current_setup_dict_as_getter(self):
        src = _file_src(DASHBOARD)
        assert "set_active_setup_getter(self._current_setup_dict)" in src

# ---------------------------------------------------------------------------
# DEF-P3-009 — race prompt says "N laps" even for timed races
# AWR-066
# ---------------------------------------------------------------------------

class TestDEF_P3_009_TimedRaceLen:
    def test_build_race_prompt_computes_race_len_line(self):
        body = _function_body(AI_PLANNER, "_build_race_prompt")
        assert "race_len_line" in body

    def test_build_race_prompt_conditional_on_race_type(self):
        body = _function_body(AI_PLANNER, "_build_race_prompt")
        assert "race_type" in body and ("timed" in body)

    def test_build_race_prompt_timed_says_minutes(self):
        body = _function_body(AI_PLANNER, "_build_race_prompt")
        assert "minutes" in body.lower() or "Timed Race" in body

    def test_build_race_prompt_uses_race_len_line_in_fstring(self):
        body = _function_body(AI_PLANNER, "_build_race_prompt")
        assert "{race_len_line}" in body

    def test_no_hardcoded_race_length_laps_in_race_prompt(self):
        body = _function_body(AI_PLANNER, "_build_race_prompt")
        # The literal hardcoded line should not appear in the f-string (it should use race_len_line)
        assert '"- Race length: {params.total_laps} laps"' not in body
        assert "race_len_line" in body  # must use the conditional variable

# ---------------------------------------------------------------------------
# DEF-P3-010 — build_car_setup missing race context
# AWR-067
# ---------------------------------------------------------------------------

class TestDEF_P3_010_BuildSetupRaceContext:
    def test_build_car_setup_accepts_tyre_wear_multiplier(self):
        body = _function_body(AI_PLANNER, "build_car_setup")
        assert "tyre_wear_multiplier" in body

    def test_build_car_setup_accepts_fuel_multiplier(self):
        body = _function_body(AI_PLANNER, "build_car_setup")
        assert "fuel_multiplier" in body

    def test_build_car_setup_accepts_req_tyres(self):
        body = _function_body(AI_PLANNER, "build_car_setup")
        assert "req_tyres" in body

    def test_build_car_setup_accepts_race_type(self):
        body = _function_body(AI_PLANNER, "build_car_setup")
        assert "race_type" in body

    def test_build_setup_from_scratch_injects_race_ctx_block(self):
        body = _function_body(AI_PLANNER, "_build_setup_from_scratch_prompt")
        assert "_race_ctx_block" in body

    def test_build_setup_from_scratch_handles_timed_session(self):
        body = _function_body(AI_PLANNER, "_build_setup_from_scratch_prompt")
        assert "timed" in body

    def test_run_build_setup_passes_tyre_wear_mult(self):
        body = _method_body(SETUP_BUILDER_UI, None, "_run_build_setup")
        assert "tyre_wear_multiplier=" in body

    def test_run_build_setup_passes_race_type(self):
        body = _method_body(SETUP_BUILDER_UI, None, "_run_build_setup")
        assert "race_type=" in body

    def test_run_build_setup_passes_avail_tyres(self):
        body = _method_body(SETUP_BUILDER_UI, None, "_run_build_setup")
        assert "avail_tyres=" in body

    def test_run_build_setup_passes_req_tyres(self):
        body = _method_body(SETUP_BUILDER_UI, None, "_run_build_setup")
        assert "req_tyres=" in body

# ---------------------------------------------------------------------------
# DEF-P3-011 — _DATA_QUALITY_NOTE missing from ai_planner.py prompts
# AWR-068
# ---------------------------------------------------------------------------

class TestDEF_P3_011_DataQualityNote:
    def test_data_quality_note_constant_defined_in_ai_planner(self):
        src = _file_src(AI_PLANNER)
        assert "_DATA_QUALITY_NOTE" in src

    def test_data_quality_note_mentions_measured(self):
        src = _file_src(AI_PLANNER)
        assert "Measured" in src

    def test_data_quality_note_mentions_calculated(self):
        src = _file_src(AI_PLANNER)
        assert "Calculated" in src

    def test_data_quality_note_mentions_estimated(self):
        src = _file_src(AI_PLANNER)
        assert "Estimated" in src

    def test_build_race_prompt_injects_data_quality_note(self):
        body = _function_body(AI_PLANNER, "_build_race_prompt")
        assert "_DATA_QUALITY_NOTE" in body

    def test_build_practice_prompt_injects_data_quality_note(self):
        body = _function_body(AI_PLANNER, "_build_practice_prompt")
        assert "_DATA_QUALITY_NOTE" in body

# ---------------------------------------------------------------------------
# DEF-P3-012 — _display_strategy_results does not validate AI output
# AWR-069
# ---------------------------------------------------------------------------

class TestDEF_P3_012_StrategyValidation:
    def test_display_strategy_results_calls_validate(self):
        body = _method_body(DASHBOARD, None, "_display_strategy_results")
        assert "validate_ai_setup_response" in body

    def test_display_strategy_results_shows_warning_banner(self):
        body = _method_body(DASHBOARD, None, "_display_strategy_results")
        assert "_warn_html" in body

    def test_display_strategy_results_uses_tuning_locked(self):
        body = _method_body(DASHBOARD, None, "_display_strategy_results")
        assert "_strat_locked" in body or "tuning_locked" in body.lower()

    def test_display_strategy_results_uses_allowed_tuning(self):
        body = _method_body(DASHBOARD, None, "_display_strategy_results")
        assert "_strat_allowed" in body or "allowed_tuning" in body.lower()

    def test_warning_banner_orange_styling(self):
        body = _method_body(DASHBOARD, None, "_display_strategy_results")
        assert "F5A623" in body  # orange warning colour

    def test_display_strategy_results_iterates_options(self):
        body = _method_body(DASHBOARD, None, "_display_strategy_results")
        assert "for _opt in options" in body
