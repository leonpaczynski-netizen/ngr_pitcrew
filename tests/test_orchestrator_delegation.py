"""AC4 / AC5 — dashboard worker delegation and no-Qt import tests.

AC4: _run_practice_analysis and _run_ai_analysis in ui/dashboard.py must
     delegate to the orchestrator functions (no inline DB queries or AI calls
     remaining in the worker bodies).

AC5: strategy.practice_orchestrator and strategy.strategy_orchestrator must
     be importable without pulling in any Qt module.
"""
from __future__ import annotations

import ast
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DASHBOARD = os.path.join(ROOT, "ui", "dashboard.py")
_PRACTICE_ORCH = os.path.join(ROOT, "strategy", "practice_orchestrator.py")
_STRATEGY_ORCH = os.path.join(ROOT, "strategy", "strategy_orchestrator.py")

sys.path.insert(0, ROOT)


# ---------------------------------------------------------------------------
# Helpers (matches style in test_group16_per_lap_telemetry.py)
# ---------------------------------------------------------------------------

def _method_body(module_path: str, class_name: str, method_name: str) -> str:
    with open(module_path, encoding="utf-8") as f:
        source = f.read()
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name == method_name:
                    return ast.get_source_segment(source, item) or ""
    raise AttributeError(f"{class_name}.{method_name} not found in {module_path}")


def _module_source(path: str) -> str:
    with open(path, encoding="utf-8") as f:
        return f.read()


# ---------------------------------------------------------------------------
# AC4 — delegation checks (source scan, no Qt needed)
# ---------------------------------------------------------------------------

class TestAC4WorkerDelegation:

    def test_run_practice_analysis_calls_orchestrator_function(self):
        """_run_practice_analysis worker body must call run_practice_analysis
        from strategy.practice_orchestrator."""
        body = _method_body(_DASHBOARD, "MainWindow", "_run_practice_analysis")
        assert "run_practice_analysis(" in body, (
            "_run_practice_analysis must delegate to run_practice_analysis() "
            "from strategy.practice_orchestrator"
        )

    def test_run_practice_analysis_imports_from_practice_orchestrator(self):
        """_run_practice_analysis must import from strategy.practice_orchestrator."""
        body = _method_body(_DASHBOARD, "MainWindow", "_run_practice_analysis")
        assert "practice_orchestrator" in body, (
            "_run_practice_analysis must import from strategy.practice_orchestrator"
        )

    def test_run_ai_analysis_calls_orchestrator_function(self):
        """_run_ai_analysis worker body must call run_strategy_analysis
        from strategy.strategy_orchestrator."""
        body = _method_body(_DASHBOARD, "MainWindow", "_run_ai_analysis")
        assert "run_strategy_analysis(" in body, (
            "_run_ai_analysis must delegate to run_strategy_analysis() "
            "from strategy.strategy_orchestrator"
        )

    def test_run_ai_analysis_imports_from_strategy_orchestrator(self):
        """_run_ai_analysis must import from strategy.strategy_orchestrator."""
        body = _method_body(_DASHBOARD, "MainWindow", "_run_ai_analysis")
        assert "strategy_orchestrator" in body, (
            "_run_ai_analysis must import from strategy.strategy_orchestrator"
        )

    def test_run_practice_analysis_worker_has_no_raw_analyse_practice_session_call(self):
        """After delegation, the worker body must NOT call analyse_practice_session
        directly — that is the orchestrator's job."""
        body = _method_body(_DASHBOARD, "MainWindow", "_run_practice_analysis")
        assert "analyse_practice_session(" not in body, (
            "_run_practice_analysis should not call analyse_practice_session() "
            "directly; delegate via run_practice_analysis() instead"
        )

    def test_run_ai_analysis_worker_has_no_raw_analyse_strategy_call(self):
        """After delegation, the worker body must NOT call analyse_strategy
        directly — that is the orchestrator's job."""
        body = _method_body(_DASHBOARD, "MainWindow", "_run_ai_analysis")
        assert "analyse_strategy(" not in body, (
            "_run_ai_analysis should not call analyse_strategy() directly; "
            "delegate via run_strategy_analysis() instead"
        )


# ---------------------------------------------------------------------------
# AC5 — no Qt on import of orchestrator modules
# ---------------------------------------------------------------------------

class TestAC5NoQtOnImport:

    def test_practice_orchestrator_no_qt(self):
        """Importing strategy.practice_orchestrator must not pull in Qt."""
        qt_before = {k for k in sys.modules if "PyQt" in k or "PySide" in k}
        import strategy.practice_orchestrator  # noqa: F401
        qt_after = {k for k in sys.modules if "PyQt" in k or "PySide" in k}
        new_qt = qt_after - qt_before
        assert not new_qt, (
            f"strategy.practice_orchestrator imported Qt modules: {new_qt}"
        )

    def test_strategy_orchestrator_no_qt(self):
        """Importing strategy.strategy_orchestrator must not pull in Qt."""
        qt_before = {k for k in sys.modules if "PyQt" in k or "PySide" in k}
        import strategy.strategy_orchestrator  # noqa: F401
        qt_after = {k for k in sys.modules if "PyQt" in k or "PySide" in k}
        new_qt = qt_after - qt_before
        assert not new_qt, (
            f"strategy.strategy_orchestrator imported Qt modules: {new_qt}"
        )

    def test_practice_analysis_module_no_qt(self):
        """Importing data.practice_analysis must not pull in Qt (mirrors existing
        test but placed here for completeness as AC5 coverage)."""
        qt_before = {k for k in sys.modules if "PyQt" in k or "PySide" in k}
        import data.practice_analysis  # noqa: F401
        qt_after = {k for k in sys.modules if "PyQt" in k or "PySide" in k}
        new_qt = qt_after - qt_before
        assert not new_qt, (
            f"data.practice_analysis imported Qt modules: {new_qt}"
        )
