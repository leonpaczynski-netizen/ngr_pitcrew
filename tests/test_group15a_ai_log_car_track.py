"""Group 15A — DEF-P3-013: AILogEntry car_id/track fields and call_api threading.

Verifies that:
  1. AILogEntry supports car_id and track fields with safe defaults.
  2. call_api() accepts and threads car_id/track through to every AILogEntry.
  3. Logged AI interactions can be retrieved by get_recent_ai_recommendations.
  4. analyse_strategy(), analyse_practice_session(), build_car_setup() accept car_id.
  5. driving_advisor call_api() calls pass car_id and track.
  6. dashboard callers resolve and pass car_id.

All tests are source-scan or pure-unit (no Qt, no real API calls).
"""
from __future__ import annotations

import ast
import sys
import types
import unittest
from pathlib import Path

REPO = Path(__file__).parent.parent
AI_CLIENT  = REPO / "strategy" / "_ai_client.py"
AI_PLANNER = REPO / "strategy" / "ai_planner.py"
DA         = REPO / "strategy" / "driving_advisor.py"
DASHBOARD        = REPO / "ui" / "dashboard.py"
SETUP_BUILDER_UI = REPO / "ui" / "setup_builder_ui.py"


def _src(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _function_body(path: Path, name: str) -> str:
    src = _src(path)
    tree = ast.parse(src)
    lines = src.splitlines()
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return "\n".join(lines[node.lineno - 1: node.end_lineno])
    return ""


def _method_body(path: Path, class_name, method_name: str) -> str:
    src = _src(path)
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


# ---------------------------------------------------------------------------
# 1. AILogEntry dataclass fields
# ---------------------------------------------------------------------------

class TestAILogEntryFields(unittest.TestCase):

    def test_ailogentry_has_car_id_field(self):
        src = _src(AI_CLIENT)
        self.assertIn("car_id", src)

    def test_ailogentry_has_track_field(self):
        src = _src(AI_CLIENT)
        # Ensure 'track' appears as a field in AILogEntry (dataclass body)
        self.assertIn("track: str", src)

    def test_ailogentry_car_id_default_zero(self):
        src = _src(AI_CLIENT)
        self.assertIn("car_id: int = 0", src)

    def test_ailogentry_track_default_empty(self):
        src = _src(AI_CLIENT)
        self.assertIn('track: str = ""', src)

    def test_ailogentry_instantiation_with_defaults(self):
        from strategy._ai_client import AILogEntry
        entry = AILogEntry(
            timestamp="2026-06-23T00:00:00",
            feature="Test",
            model="claude-opus-4-8",
            prompt="p",
            structured_payload="{}",
            response="r",
            success=True,
            duration_ms=0,
            prompt_tokens=0,
            response_tokens=0,
            estimated_cost=0.0,
            error_msg="",
        )
        self.assertEqual(entry.car_id, 0)
        self.assertEqual(entry.track, "")

    def test_ailogentry_accepts_car_id_and_track(self):
        from strategy._ai_client import AILogEntry
        entry = AILogEntry(
            timestamp="2026-06-23T00:00:00",
            feature="Practice Analysis",
            model="claude-opus-4-8",
            prompt="p",
            structured_payload="{}",
            response="r",
            success=True,
            duration_ms=100,
            prompt_tokens=10,
            response_tokens=20,
            estimated_cost=0.001,
            error_msg="",
            car_id=42,
            track="Suzuka Circuit",
        )
        self.assertEqual(entry.car_id, 42)
        self.assertEqual(entry.track, "Suzuka Circuit")


# ---------------------------------------------------------------------------
# 2. call_api() signature and AILogEntry wiring
# ---------------------------------------------------------------------------

class TestCallApiCarIdTrack(unittest.TestCase):

    def test_call_api_accepts_car_id_kwarg(self):
        body = _function_body(AI_CLIENT, "call_api")
        self.assertIn("car_id", body)

    def test_call_api_accepts_track_kwarg(self):
        body = _function_body(AI_CLIENT, "call_api")
        self.assertIn("track", body)

    def test_call_api_car_id_default_zero(self):
        body = _function_body(AI_CLIENT, "call_api")
        self.assertIn("car_id: int = 0", body)

    def test_call_api_track_default_empty(self):
        body = _function_body(AI_CLIENT, "call_api")
        self.assertIn('track: str = ""', body)

    def test_success_ailogentry_includes_car_id(self):
        # The success AILogEntry block must pass car_id=car_id
        body = _function_body(AI_CLIENT, "call_api")
        self.assertIn("car_id=car_id", body)

    def test_success_ailogentry_includes_track(self):
        body = _function_body(AI_CLIENT, "call_api")
        self.assertIn("track=track", body)

    def test_debug_ailogentry_includes_car_id(self):
        body = _function_body(AI_CLIENT, "call_api")
        # Both debug and failure paths must also set car_id
        self.assertGreaterEqual(body.count("car_id=car_id"), 3,
            "car_id=car_id must appear in all three AILogEntry blocks (debug, success, failure)")

    def test_failure_ailogentry_includes_track(self):
        body = _function_body(AI_CLIENT, "call_api")
        self.assertGreaterEqual(body.count("track=track"), 3,
            "track=track must appear in all three AILogEntry blocks (debug, success, failure)")

    def test_call_api_live_fires_log_hook_with_car_id(self):
        """Unit test: call_api in debug mode logs an AILogEntry with the passed car_id."""
        captured: list = []
        from strategy._ai_client import set_log_hook, _AI_DEBUG
        import strategy._ai_client as _c

        original_debug = _c._AI_DEBUG
        original_hook = _c._log_hook
        try:
            _c._AI_DEBUG = True
            set_log_hook(lambda e: captured.append(e))
            try:
                _c.call_api("test", "fake_key", feature="Test Feature",
                            car_id=99, track="Brands Hatch")
            except RuntimeError:
                pass
        finally:
            _c._AI_DEBUG = original_debug
            _c._log_hook = original_hook

        self.assertEqual(len(captured), 1)
        self.assertEqual(captured[0].car_id, 99)
        self.assertEqual(captured[0].track, "Brands Hatch")

    def test_call_api_defaults_preserve_zero_car_id(self):
        """call_api with no car_id logs car_id=0."""
        captured: list = []
        import strategy._ai_client as _c
        original_debug = _c._AI_DEBUG
        original_hook = _c._log_hook
        try:
            _c._AI_DEBUG = True
            _c.set_log_hook(lambda e: captured.append(e))
            try:
                _c.call_api("test", "fake_key", feature="Test Feature")
            except RuntimeError:
                pass
        finally:
            _c._AI_DEBUG = original_debug
            _c._log_hook = original_hook

        self.assertEqual(len(captured), 1)
        self.assertEqual(captured[0].car_id, 0)
        self.assertEqual(captured[0].track, "")


# ---------------------------------------------------------------------------
# 3. ai_planner.py function signatures
# ---------------------------------------------------------------------------

class TestAiPlannerSignatures(unittest.TestCase):

    def test_analyse_strategy_accepts_car_id(self):
        body = _function_body(AI_PLANNER, "analyse_strategy")
        self.assertIn("car_id", body)

    def test_analyse_strategy_car_id_default_zero(self):
        body = _function_body(AI_PLANNER, "analyse_strategy")
        self.assertIn("car_id: int = 0", body)

    def test_analyse_strategy_passes_car_id_to_call_api(self):
        body = _function_body(AI_PLANNER, "analyse_strategy")
        self.assertIn("car_id=car_id", body)

    def test_analyse_strategy_passes_track_to_call_api(self):
        body = _function_body(AI_PLANNER, "analyse_strategy")
        self.assertIn("track=params.track", body)

    def test_analyse_practice_session_accepts_car_id(self):
        body = _function_body(AI_PLANNER, "analyse_practice_session")
        self.assertIn("car_id", body)

    def test_analyse_practice_session_car_id_default_zero(self):
        body = _function_body(AI_PLANNER, "analyse_practice_session")
        self.assertIn("car_id: int = 0", body)

    def test_analyse_practice_session_passes_car_id_to_call_api(self):
        body = _function_body(AI_PLANNER, "analyse_practice_session")
        self.assertIn("car_id=car_id", body)

    def test_analyse_practice_session_passes_track_to_call_api(self):
        body = _function_body(AI_PLANNER, "analyse_practice_session")
        self.assertIn("track=params.track", body)

    def test_build_car_setup_accepts_car_id(self):
        body = _function_body(AI_PLANNER, "build_car_setup")
        self.assertIn("car_id", body)

    def test_build_car_setup_car_id_default_zero(self):
        body = _function_body(AI_PLANNER, "build_car_setup")
        self.assertIn("car_id: int = 0", body)

    def test_build_car_setup_passes_car_id_to_call_api(self):
        body = _function_body(AI_PLANNER, "build_car_setup")
        self.assertIn("car_id=car_id", body)

    def test_build_car_setup_passes_track_to_call_api(self):
        body = _function_body(AI_PLANNER, "build_car_setup")
        self.assertIn("track=track", body)


# ---------------------------------------------------------------------------
# 4. driving_advisor.py — car_id and track passed from self
# ---------------------------------------------------------------------------

class TestDrivingAdvisorCarIdTrack(unittest.TestCase):

    def test_coaching_passes_car_id_ref(self):
        body = _method_body(DA, "DrivingAdvisor", "build_coaching_response")
        self.assertIn("car_id=self._car_id_ref[0]", body)

    def test_coaching_passes_track(self):
        body = _method_body(DA, "DrivingAdvisor", "build_coaching_response")
        self.assertIn("track=_track_da", body)

    def test_setup_advice_passes_car_id_ref(self):
        body = _method_body(DA, "DrivingAdvisor", "build_setup_advice_response")
        self.assertIn("car_id=self._car_id_ref[0]", body)

    def test_setup_advice_passes_track(self):
        body = _method_body(DA, "DrivingAdvisor", "build_setup_advice_response")
        self.assertIn("track=_track_da", body)

    def test_combined_setup_passes_car_id_ref(self):
        body = _method_body(DA, "DrivingAdvisor", "build_combined_setup_response")
        self.assertIn("car_id=self._car_id_ref[0]", body)

    def test_combined_setup_passes_track(self):
        body = _method_body(DA, "DrivingAdvisor", "build_combined_setup_response")
        self.assertIn("track=_track_da", body)

    def test_handling_analysis_passes_car_id_ref(self):
        body = _method_body(DA, "DrivingAdvisor", "build_driver_feeling_response")
        self.assertIn("car_id=self._car_id_ref[0]", body)

    def test_handling_analysis_passes_track(self):
        body = _method_body(DA, "DrivingAdvisor", "build_driver_feeling_response")
        self.assertIn("track=_track_da", body)

    def test_coaching_reads_track_from_config(self):
        body = _method_body(DA, "DrivingAdvisor", "build_coaching_response")
        self.assertIn('_track_da = self._config.get("strategy", {}).get("track", "")', body)


# ---------------------------------------------------------------------------
# 5. dashboard.py callers resolve and pass car_id
# ---------------------------------------------------------------------------

class TestDashboardCarIdResolution(unittest.TestCase):

    def test_run_ai_analysis_resolves_car_id(self):
        body = _method_body(DASHBOARD, None, "_run_ai_analysis")
        self.assertIn("get_car_id", body)

    def test_run_ai_analysis_uses_car_id_strat(self):
        body = _method_body(DASHBOARD, None, "_run_ai_analysis")
        self.assertIn("_car_id_strat", body)

    def test_run_ai_analysis_passes_car_id_to_analyse_strategy(self):
        body = _method_body(DASHBOARD, None, "_run_ai_analysis")
        self.assertIn("car_id=_car_id_strat", body)

    def test_run_ai_analysis_car_id_resolved_before_worker(self):
        body = _method_body(DASHBOARD, None, "_run_ai_analysis")
        strat_pos = body.find("_car_id_strat")
        worker_pos = body.find("def _worker()")
        self.assertGreater(worker_pos, strat_pos,
            "_car_id_strat must be resolved before def _worker()")

    def test_practice_worker_passes_car_id_hist_to_analyse(self):
        body = _method_body(DASHBOARD, None, "_run_practice_analysis")
        self.assertIn("car_id=_car_id_hist", body)

    def test_run_build_setup_resolves_car_id(self):
        body = _method_body(SETUP_BUILDER_UI, None, "_run_build_setup")
        self.assertIn("_car_id_build", body)

    def test_run_build_setup_uses_get_car_id(self):
        body = _method_body(SETUP_BUILDER_UI, None, "_run_build_setup")
        self.assertIn("get_car_id", body)

    def test_run_build_setup_passes_car_id_to_build_car_setup(self):
        body = _method_body(SETUP_BUILDER_UI, None, "_run_build_setup")
        self.assertIn("car_id=_car_id_build", body)

    def test_run_build_setup_car_id_resolved_before_worker(self):
        body = _method_body(SETUP_BUILDER_UI, None, "_run_build_setup")
        build_pos = body.find("_car_id_build")
        worker_pos = body.find("def _worker()")
        self.assertGreater(worker_pos, build_pos,
            "_car_id_build must be resolved before def _worker()")

    def test_run_ai_analysis_safe_default_when_no_db(self):
        body = _method_body(DASHBOARD, None, "_run_ai_analysis")
        self.assertIn("else 0", body)

    def test_run_build_setup_safe_default_when_no_db(self):
        body = _method_body(SETUP_BUILDER_UI, None, "_run_build_setup")
        self.assertIn("else 0", body)


# ---------------------------------------------------------------------------
# 6. DB round-trip: log with real car_id/track → retrieved by get_recent_ai_recommendations
# ---------------------------------------------------------------------------

class TestAiLogCarIdTrackDbRoundTrip(unittest.TestCase):

    def setUp(self):
        from data.session_db import SessionDB
        self.db = SessionDB(":memory:")

    def tearDown(self):
        self.db.close()

    def test_log_with_car_id_and_track_stored(self):
        self.db.log_ai_interaction({
            "timestamp": "2026-06-23T10:00:00",
            "feature": "Practice Analysis",
            "model": "claude-opus-4-8",
            "prompt": "test",
            "structured_payload": "{}",
            "response": "result text",
            "success": 1,
            "duration_ms": 100,
            "prompt_tokens": 10,
            "response_tokens": 20,
            "estimated_cost": 0.001,
            "error_msg": "",
            "validation_warnings": "[]",
            "car_id": 7,
            "track": "Nurburgring",
        })
        rows = self.db.get_ai_interactions(limit=1)
        self.assertEqual(rows[0]["car_id"], 7)
        self.assertEqual(rows[0]["track"], "Nurburgring")

    def test_get_recent_ai_recommendations_returns_matching_row(self):
        self.db.log_ai_interaction({
            "timestamp": "2026-06-23T10:00:00",
            "feature": "Practice Analysis",
            "model": "claude-opus-4-8",
            "prompt": "p",
            "structured_payload": "{}",
            "response": "previous AI advice text",
            "success": 1,
            "duration_ms": 100,
            "prompt_tokens": 10,
            "response_tokens": 20,
            "estimated_cost": 0.001,
            "error_msg": "",
            "validation_warnings": "[]",
            "car_id": 5,
            "track": "Suzuka Circuit",
        })
        results = self.db.get_recent_ai_recommendations(
            "Practice Analysis", 5, "Suzuka Circuit", limit=2)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0], "previous AI advice text")

    def test_get_recent_ai_recommendations_empty_when_car_id_zero(self):
        self.db.log_ai_interaction({
            "timestamp": "2026-06-23T10:00:00",
            "feature": "Practice Analysis",
            "model": "claude-opus-4-8",
            "prompt": "p",
            "structured_payload": "{}",
            "response": "some advice",
            "success": 1,
            "duration_ms": 100,
            "prompt_tokens": 10,
            "response_tokens": 20,
            "estimated_cost": 0.001,
            "error_msg": "",
            "validation_warnings": "[]",
            "car_id": 0,
            "track": "Suzuka Circuit",
        })
        results = self.db.get_recent_ai_recommendations(
            "Practice Analysis", 3, "Suzuka Circuit", limit=2)
        self.assertEqual(results, [])

    def test_get_recent_ai_recommendations_empty_when_track_mismatch(self):
        self.db.log_ai_interaction({
            "timestamp": "2026-06-23T10:00:00",
            "feature": "Practice Analysis",
            "model": "claude-opus-4-8",
            "prompt": "p",
            "structured_payload": "{}",
            "response": "some advice",
            "success": 1,
            "duration_ms": 100,
            "prompt_tokens": 10,
            "response_tokens": 20,
            "estimated_cost": 0.001,
            "error_msg": "",
            "validation_warnings": "[]",
            "car_id": 5,
            "track": "Suzuka Circuit",
        })
        results = self.db.get_recent_ai_recommendations(
            "Practice Analysis", 5, "Monza", limit=2)
        self.assertEqual(results, [])

    def test_get_recent_ai_recommendations_empty_for_failed_entries(self):
        self.db.log_ai_interaction({
            "timestamp": "2026-06-23T10:00:00",
            "feature": "Practice Analysis",
            "model": "claude-opus-4-8",
            "prompt": "p",
            "structured_payload": "{}",
            "response": "error advice",
            "success": 0,
            "duration_ms": 0,
            "prompt_tokens": 0,
            "response_tokens": 0,
            "estimated_cost": 0.0,
            "error_msg": "API failed",
            "validation_warnings": "[]",
            "car_id": 5,
            "track": "Suzuka Circuit",
        })
        results = self.db.get_recent_ai_recommendations(
            "Practice Analysis", 5, "Suzuka Circuit", limit=2)
        self.assertEqual(results, [])

    def test_get_recent_ai_recommendations_respects_feature_filter(self):
        self.db.log_ai_interaction({
            "timestamp": "2026-06-23T10:00:00",
            "feature": "Driver Coaching",
            "model": "claude-opus-4-8",
            "prompt": "p",
            "structured_payload": "{}",
            "response": "coaching text",
            "success": 1,
            "duration_ms": 100,
            "prompt_tokens": 10,
            "response_tokens": 20,
            "estimated_cost": 0.001,
            "error_msg": "",
            "validation_warnings": "[]",
            "car_id": 5,
            "track": "Suzuka Circuit",
        })
        results = self.db.get_recent_ai_recommendations(
            "Practice Analysis", 5, "Suzuka Circuit", limit=2)
        self.assertEqual(results, [])

    def test_get_recent_ai_recommendations_respects_limit(self):
        for i in range(4):
            self.db.log_ai_interaction({
                "timestamp": f"2026-06-23T10:0{i}:00",
                "feature": "Practice Analysis",
                "model": "claude-opus-4-8",
                "prompt": "p",
                "structured_payload": "{}",
                "response": f"advice {i}",
                "success": 1,
                "duration_ms": 100,
                "prompt_tokens": 10,
                "response_tokens": 20,
                "estimated_cost": 0.001,
                "error_msg": "",
                "validation_warnings": "[]",
                "car_id": 5,
                "track": "Suzuka Circuit",
            })
        results = self.db.get_recent_ai_recommendations(
            "Practice Analysis", 5, "Suzuka Circuit", limit=2)
        self.assertEqual(len(results), 2)

    def test_ailogentry_asdict_includes_car_id_and_track(self):
        """_asdict(AILogEntry) must include car_id and track for log_ai_interaction."""
        from dataclasses import asdict
        from strategy._ai_client import AILogEntry
        entry = AILogEntry(
            timestamp="2026-06-23T00:00:00",
            feature="Practice Analysis",
            model="claude-opus-4-8",
            prompt="p",
            structured_payload="{}",
            response="r",
            success=True,
            duration_ms=0,
            prompt_tokens=0,
            response_tokens=0,
            estimated_cost=0.0,
            error_msg="",
            car_id=12,
            track="Spa-Francorchamps",
        )
        d = asdict(entry)
        self.assertEqual(d["car_id"], 12)
        self.assertEqual(d["track"], "Spa-Francorchamps")


if __name__ == "__main__":
    unittest.main()
