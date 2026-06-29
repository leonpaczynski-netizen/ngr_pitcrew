"""Ownership guard tests — SetupBuilderMixin extraction from dashboard.py."""
import os, re, ast

ROOT = os.path.dirname(os.path.dirname(__file__))

def _src(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return f.read()

_METHODS = [
    "_build_car_setup_group", "_current_setup_dict", "_fill_setup_fields",
    "_load_car_specs_for_current", "_apply_setup_permissions",
    "_refresh_setup_combo", "_generate_setup_name", "_setup_save",
    "_setup_load_selected", "_setup_analyse_ai", "_display_setup_result",
    "_apply_and_save_ai_setup", "_run_build_setup", "_display_build_setup_result",
    "_apply_build_setup_result", "_sync_setup_builder_from_event",
    "_build_setup_builder_tab", "_refresh_setup_history_combo",
    "_on_setup_history_selected",
]

def test_methods_absent_from_dashboard():
    src = _src("ui/dashboard.py")
    for m in ["_build_setup_builder_tab", "_fill_setup_fields"]:
        assert f"def {m}" not in src, f"def {m} still in dashboard.py"

def test_methods_present_in_mixin():
    src = _src("ui/setup_builder_ui.py")
    for m in _METHODS:
        assert f"def {m}" in src, f"def {m} missing from setup_builder_ui.py"

def test_init_not_in_mixin():
    src = _src("ui/setup_builder_ui.py")
    assert "def __init__" not in src

def test_init_attrs_in_dashboard():
    src = _src("ui/dashboard.py")
    assert "self._setup_result_queue" in src
    assert "self._build_setup_queue" in src
