"""Engineering-Brain Phase 5 — runtime wiring + threading + architecture safety."""
from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


# --- 12.8 UI + threading (structural) --------------------------------------
def test_review_worker_uses_review_and_learn():
    src = (ROOT / "ui" / "setup_builder_ui.py").read_text(encoding="utf-8")
    assert "db.review_and_learn(" in src
    assert "threading.Thread(target=_worker, daemon=True)" in src   # off-thread


def test_outcome_render_shows_next_experiment_and_learning():
    src = (ROOT / "ui" / "setup_builder_ui.py").read_text(encoding="utf-8")
    assert "next_experiment" in src and "Learned working windows" in src
    assert "No safe next experiment" in src                        # no-selection state


def test_no_apply_or_revert_from_review_path():
    src = (ROOT / "ui" / "setup_builder_ui.py").read_text(encoding="utf-8")
    # the review worker body must not apply/revert a setup
    start = src.index("def _review_experiment_outcome")
    end = src.index("def _ensure_outcome_queue")
    body = src[start:end]
    assert "mark_applied" not in body
    assert "apply_revert_to_setup" not in body


def test_no_udp_or_db_work_added_to_ui_thread():
    # review_and_learn is called on the worker thread, not the Qt tick
    src = (ROOT / "ui" / "setup_builder_ui.py").read_text(encoding="utf-8")
    disp_start = src.index("def _display_outcome_result")
    disp_end = src.index("def _refresh_apply_status_for_form")
    disp = src[disp_start:disp_end]
    assert "review_and_learn" not in disp        # heavy work stays off the render tick
    assert "evaluate_setup_experiment" not in disp


# --- 12.9 safety and architecture ------------------------------------------
_PURE_MODULES = ("working_window", "experiment_selection")


def test_pure_modules_no_qt_db_network_ai():
    for mod in _PURE_MODULES:
        src = (ROOT / "strategy" / f"{mod}.py").read_text(encoding="utf-8")
        for banned in ("PyQt6", "PyQt5", "from ui.", "import sqlite3",
                       "from data.session_db", "requests", "urllib", "anthropic",
                       "openai", "api_key"):
            assert banned not in src, f"{mod}: {banned}"


def test_pure_modules_no_file_writes():
    for mod in _PURE_MODULES:
        src = (ROOT / "strategy" / f"{mod}.py").read_text(encoding="utf-8")
        assert "open(" not in src and ".write(" not in src


def test_pure_modules_no_wallclock_ordering():
    for mod in _PURE_MODULES:
        src = (ROOT / "strategy" / f"{mod}.py").read_text(encoding="utf-8")
        assert "datetime.now" not in src and "time.time" not in src


def test_selector_module_no_db_import():
    src = (ROOT / "strategy" / "experiment_selection.py").read_text(encoding="utf-8")
    assert "sqlite3" not in src and "session_db" not in src


def test_phase1_fingerprint_not_recomputed():
    for mod in ("working_window", "experiment_selection"):
        src = (ROOT / "strategy" / f"{mod}.py").read_text(encoding="utf-8")
        assert "compute_config_id" not in src
        assert "def scope_fingerprint" not in src


def test_resolve_setup_decision_is_runtime_authority():
    # the review render routes through the canonical decision authority
    src = (ROOT / "ui" / "setup_builder_ui.py").read_text(encoding="utf-8")
    assert "resolve_setup_decision" in src


def test_no_new_fanout_or_apply_gate_change():
    from tests.test_legacy_fanout_phase_5 import _scan_inventory, FROZEN_ALLOWLIST
    assert _scan_inventory() == FROZEN_ALLOWLIST
    src = (ROOT / "ui" / "setup_builder_ui.py").read_text(encoding="utf-8")
    assert "_status_approved: bool = (not _is_legacy) and (_rec_status in _APPROVED_STATUSES)" in src
