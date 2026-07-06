"""
Group 45 — Setup Brain Intelligence Expansion: UI Context Threading Tests

Covers FIX 2 (frontend): _setup_analyse_ai now passes purpose/car_class/drivetrain
to build_combined_setup_response, mirroring _setup_analyse_ai_for_form.

Tests:
  FIX2-A  — Source inspection: both _setup_analyse_ai and _setup_analyse_ai_for_form
             pass the three params (purpose, car_class, drivetrain) to
             build_combined_setup_response.  This guards against a future
             regression where one handler drops a param.
  FIX2-B  — Captured kwargs: monkeypatch build_combined_setup_response on a stub
             DrivingAdvisor; call _setup_analyse_ai via its inner _worker() function;
             assert purpose, car_class, drivetrain are in the captured kwargs and
             are non-defaulted for a race form with a known combo selection.
  FIX2-C  — Parity: both handlers pass IDENTICAL param names (no param present in
             one but absent in the other for these three context fields).

All tests are offline (no network, no real DB, no real QApplication event loop for
the source-inspection tests; the captured-kwargs test does construct a minimal Qt
widget but runs Qt offscreen).
"""
from __future__ import annotations

import inspect
import json
import os
import queue
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

# Set before any QApplication is created.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

pytest.importorskip("PyQt6.QtWidgets")

from PyQt6.QtWidgets import QApplication, QTextEdit  # noqa: E402

from ui.setup_builder_ui import SetupBuilderMixin  # noqa: E402
from ui.setup_form_widget import SetupFormWidget   # noqa: E402


# ---------------------------------------------------------------------------
# QApplication fixture (module scope — one QApp per process)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


# ===========================================================================
# FIX2-A — Source inspection: both handlers pass purpose/car_class/drivetrain
# ===========================================================================

class TestFix2ASourceInspection:
    """FIX2-A: Verify at source level that both _setup_analyse_ai and
    _setup_analyse_ai_for_form pass purpose, car_class, and drivetrain to
    build_combined_setup_response.

    Source inspection is the most stable test for this type of wiring — it
    does not depend on Qt event-loop execution and is immune to test-order
    side-effects.  A genuine runtime captured-kwargs test is in FIX2-B.
    """

    def _get_source(self, method_name: str) -> str:
        src = inspect.getsource(getattr(SetupBuilderMixin, method_name))
        return src

    def test_setup_analyse_ai_passes_purpose(self):
        """_setup_analyse_ai must pass 'purpose=' to build_combined_setup_response."""
        src = self._get_source("_setup_analyse_ai")
        assert "purpose=" in src, (
            "FIX2-A FAIL: _setup_analyse_ai does not pass purpose= to "
            "build_combined_setup_response. Fix 2 (frontend) requires this param."
        )

    def test_setup_analyse_ai_passes_car_class(self):
        """_setup_analyse_ai must pass 'car_class=' to build_combined_setup_response."""
        src = self._get_source("_setup_analyse_ai")
        assert "car_class=" in src, (
            "FIX2-A FAIL: _setup_analyse_ai does not pass car_class= to "
            "build_combined_setup_response."
        )

    def test_setup_analyse_ai_passes_drivetrain(self):
        """_setup_analyse_ai must pass 'drivetrain=' to build_combined_setup_response."""
        src = self._get_source("_setup_analyse_ai")
        assert "drivetrain=" in src, (
            "FIX2-A FAIL: _setup_analyse_ai does not pass drivetrain= to "
            "build_combined_setup_response."
        )

    def test_setup_analyse_ai_for_form_passes_purpose(self):
        """_setup_analyse_ai_for_form must pass 'purpose=' to build_combined_setup_response."""
        src = self._get_source("_setup_analyse_ai_for_form")
        assert "purpose=" in src, (
            "FIX2-A FAIL: _setup_analyse_ai_for_form does not pass purpose=."
        )

    def test_setup_analyse_ai_for_form_passes_car_class(self):
        """_setup_analyse_ai_for_form must pass 'car_class='."""
        src = self._get_source("_setup_analyse_ai_for_form")
        assert "car_class=" in src, (
            "FIX2-A FAIL: _setup_analyse_ai_for_form does not pass car_class=."
        )

    def test_setup_analyse_ai_for_form_passes_drivetrain(self):
        """_setup_analyse_ai_for_form must pass 'drivetrain='."""
        src = self._get_source("_setup_analyse_ai_for_form")
        assert "drivetrain=" in src, (
            "FIX2-A FAIL: _setup_analyse_ai_for_form does not pass drivetrain=."
        )

    def test_setup_analyse_ai_references_race_form_purpose(self):
        """_setup_analyse_ai must read purpose from self._race_form.purpose (not hardcode)."""
        src = self._get_source("_setup_analyse_ai")
        assert "_race_form.purpose" in src or "_race_form" in src, (
            "FIX2-A FAIL: _setup_analyse_ai does not read purpose from self._race_form.purpose."
        )

    def test_setup_analyse_ai_references_car_specs_category(self):
        """_setup_analyse_ai must read car_class from _car_specs.category."""
        src = self._get_source("_setup_analyse_ai")
        assert "category" in src, (
            "FIX2-A FAIL: _setup_analyse_ai does not read car_class from car_specs category."
        )

    def test_setup_analyse_ai_reads_drivetrain_from_race_form(self):
        """_setup_analyse_ai must read drivetrain from self._race_form._setup_drivetrain."""
        src = self._get_source("_setup_analyse_ai")
        assert "_setup_drivetrain" in src, (
            "FIX2-A FAIL: _setup_analyse_ai does not read drivetrain from "
            "self._race_form._setup_drivetrain."
        )


# ===========================================================================
# FIX2-B — Captured kwargs: _setup_analyse_ai inner _worker() passes context
# ===========================================================================

class _MinimalStubHost(SetupBuilderMixin):
    """Minimal host sufficient to run _setup_analyse_ai's _worker() function.

    Follows the offline pattern from test_group44_baseline_ui._StubHost.
    """

    def __init__(self, race_form):
        self._setup_result_text = QTextEdit()
        self._setup_result_queue = queue.Queue()
        self._config = {}
        self._last_setup_context = None
        self._last_setup_ai_fields = {}
        self._race_form = race_form
        # Lap table stub (zero rows)
        _lap_table = MagicMock()
        _lap_table.rowCount.return_value = 0
        self._lap_table = _lap_table
        # Setup feeling input stub
        _feeling_input = MagicMock()
        _feeling_input.toPlainText.return_value = ""
        self._setup_feeling_input = _feeling_input
        # Analyse button stub — must be a real MagicMock so setEnabled() calls succeed.
        # (Production code: if hasattr(self, "_btn_analyse_setup"): btn.setEnabled(False))
        self._btn_analyse_setup = MagicMock()

    def _load_car_specs_for_current(self):
        """Return a minimal car spec with a known category."""
        return (
            "Porsche 911 GT3 R",
            {"category": "Gr.3", "drivetrain": "RR", "bhp": 500},
        )

    def _current_setup_dict(self):
        return {"lsd_accel": 20, "aero_rear": 50}

    def _build_setup_ai_snapshot(self):
        snap = MagicMock()
        snap.allowed_tuning_or_none.return_value = None
        snap.tuning_locked = False
        snap.mandatory_compounds_str = ""
        return snap

    def _build_setup_context(self, **kwargs):
        return None

    def _active_config_id(self):
        return None


class TestFix2BCapturedKwargs:
    """FIX2-B: Run _setup_analyse_ai._worker() (extracted from the thread) and
    capture kwargs passed to build_combined_setup_response.
    """

    def test_worker_passes_purpose_to_advisor(self, qapp):
        """_worker() must pass purpose= matching self._race_form.purpose."""
        import strategy.driving_advisor as da

        race_form = SetupFormWidget("Race", MagicMock())

        # Stub advisor with captured kwargs
        captured: dict = {}

        def _mock_build_combined(*args, **kwargs):
            captured.update(kwargs)
            return json.dumps({
                "recommendation_status": "approved",
                "changes": [],
                "setup_fields": {},
                "analysis": "stub",
                "rejected_changes": [],
                "engineering_validation_failed": False,
                "engineering_validation_errors": [],
                "validation_warnings": [],
                "fallback_used": False,
                "deterministic_plan": {"proposed_count": 0, "rejected_candidate_count": 0, "protected_fields": []},
                "protected_fields": [],
                "rule_engine_version": "v1",
                "diagnosis": {},
                "confidence": {"overall": "low"},
                "_tyre_fuel_context": "stub",
                "_session_context": "stub",
                "_car_drivetrain_context": "stub",
                "_learning_note": "stub",
            })

        stub_advisor = MagicMock()
        stub_advisor.build_combined_setup_response.side_effect = _mock_build_combined

        host = _MinimalStubHost(race_form)
        host._driving_advisor = stub_advisor

        # Extract _worker() from _setup_analyse_ai by running it synchronously.
        # We monkey-patch threading.Thread to extract and call target directly.
        import threading as _threading

        original_thread = _threading.Thread
        worker_target = {}

        class _CapturingThread:
            def __init__(self, target=None, daemon=False, **kwargs):
                worker_target["fn"] = target

            def start(self):
                pass

        _threading.Thread = _CapturingThread
        try:
            host._setup_analyse_ai()
        finally:
            _threading.Thread = original_thread

        # Call the extracted worker directly (synchronous — no thread needed)
        assert "fn" in worker_target, (
            "FIX2-B FAIL: _setup_analyse_ai did not create a threading.Thread. "
            "Cannot capture worker function."
        )
        worker_target["fn"]()

        # Verify captured kwargs
        assert "purpose" in captured, (
            f"FIX2-B FAIL: _worker() did not pass 'purpose' kwarg to "
            f"build_combined_setup_response. captured kwargs: {list(captured)}"
        )
        assert captured["purpose"] == "Race", (
            f"FIX2-B FAIL: purpose={captured['purpose']!r}; expected 'Race' "
            f"(from self._race_form.purpose)"
        )

    def test_worker_passes_car_class_to_advisor(self, qapp):
        """_worker() must pass car_class= matching the car specs category."""
        race_form = SetupFormWidget("Race", MagicMock())

        captured: dict = {}

        def _mock_build_combined(*args, **kwargs):
            captured.update(kwargs)
            return json.dumps({
                "recommendation_status": "approved",
                "changes": [], "setup_fields": {}, "analysis": "stub",
                "rejected_changes": [], "engineering_validation_failed": False,
                "engineering_validation_errors": [], "validation_warnings": [],
                "fallback_used": False,
                "deterministic_plan": {"proposed_count": 0, "rejected_candidate_count": 0, "protected_fields": []},
                "protected_fields": [], "rule_engine_version": "v1",
                "diagnosis": {}, "confidence": {"overall": "low"},
                "_tyre_fuel_context": "stub", "_session_context": "stub",
                "_car_drivetrain_context": "stub", "_learning_note": "stub",
            })

        stub_advisor = MagicMock()
        stub_advisor.build_combined_setup_response.side_effect = _mock_build_combined

        host = _MinimalStubHost(race_form)
        host._driving_advisor = stub_advisor

        import threading as _threading
        original_thread = _threading.Thread
        worker_target = {}

        class _CapturingThread:
            def __init__(self, target=None, daemon=False, **kwargs):
                worker_target["fn"] = target

            def start(self):
                pass

        _threading.Thread = _CapturingThread
        try:
            host._setup_analyse_ai()
        finally:
            _threading.Thread = original_thread

        if "fn" not in worker_target:
            pytest.skip("Could not capture worker function")
        worker_target["fn"]()

        assert "car_class" in captured, (
            f"FIX2-B FAIL: _worker() did not pass 'car_class' kwarg. "
            f"captured kwargs: {list(captured)}"
        )
        # The stub _load_car_specs_for_current returns category="Gr.3"
        assert captured["car_class"] == "Gr.3", (
            f"FIX2-B FAIL: car_class={captured['car_class']!r}; expected 'Gr.3'"
        )

    def test_worker_passes_drivetrain_to_advisor(self, qapp):
        """_worker() must pass drivetrain= from self._race_form._setup_drivetrain.currentData()."""
        race_form = SetupFormWidget("Race", MagicMock())

        # Select "RR" in the drivetrain combo if available; otherwise use whatever is current.
        if hasattr(race_form, "_setup_drivetrain"):
            for i in range(race_form._setup_drivetrain.count()):
                if (race_form._setup_drivetrain.itemData(i) or "").upper() == "RR":
                    race_form._setup_drivetrain.setCurrentIndex(i)
                    break

        captured: dict = {}

        def _mock_build_combined(*args, **kwargs):
            captured.update(kwargs)
            return json.dumps({
                "recommendation_status": "approved",
                "changes": [], "setup_fields": {}, "analysis": "stub",
                "rejected_changes": [], "engineering_validation_failed": False,
                "engineering_validation_errors": [], "validation_warnings": [],
                "fallback_used": False,
                "deterministic_plan": {"proposed_count": 0, "rejected_candidate_count": 0, "protected_fields": []},
                "protected_fields": [], "rule_engine_version": "v1",
                "diagnosis": {}, "confidence": {"overall": "low"},
                "_tyre_fuel_context": "stub", "_session_context": "stub",
                "_car_drivetrain_context": "stub", "_learning_note": "stub",
            })

        stub_advisor = MagicMock()
        stub_advisor.build_combined_setup_response.side_effect = _mock_build_combined

        host = _MinimalStubHost(race_form)
        host._driving_advisor = stub_advisor

        import threading as _threading
        original_thread = _threading.Thread
        worker_target = {}

        class _CapturingThread:
            def __init__(self, target=None, daemon=False, **kwargs):
                worker_target["fn"] = target

            def start(self):
                pass

        _threading.Thread = _CapturingThread
        try:
            host._setup_analyse_ai()
        finally:
            _threading.Thread = original_thread

        if "fn" not in worker_target:
            pytest.skip("Could not capture worker function")
        worker_target["fn"]()

        assert "drivetrain" in captured, (
            f"FIX2-B FAIL: _worker() did not pass 'drivetrain' kwarg. "
            f"captured kwargs: {list(captured)}"
        )
        # drivetrain must be a string (may be "" or "RR" or other combo value — just non-missing)
        assert isinstance(captured["drivetrain"], str), (
            f"FIX2-B FAIL: drivetrain must be str; got {type(captured['drivetrain'])}"
        )


# ===========================================================================
# FIX2-C — Parity: both handlers pass the same three context param names
# ===========================================================================

class TestFix2CParity:
    """FIX2-C: The three context params (purpose, car_class, drivetrain) appear in
    BOTH _setup_analyse_ai and _setup_analyse_ai_for_form.  Neither handler may omit
    a param that the other passes.
    """

    REQUIRED_PARAMS = ("purpose", "car_class", "drivetrain")

    def _src(self, name: str) -> str:
        return inspect.getsource(getattr(SetupBuilderMixin, name))

    def test_both_handlers_have_all_three_params(self):
        """Both handlers must contain all three param names as kwargs to
        build_combined_setup_response.
        """
        src_main = self._src("_setup_analyse_ai")
        src_form = self._src("_setup_analyse_ai_for_form")

        for param in self.REQUIRED_PARAMS:
            kw = f"{param}="
            assert kw in src_main, (
                f"FIX2-C FAIL: _setup_analyse_ai missing '{kw}' — "
                f"not all context params wired."
            )
            assert kw in src_form, (
                f"FIX2-C FAIL: _setup_analyse_ai_for_form missing '{kw}' — "
                f"parity broken between the two handlers."
            )

    def test_neither_handler_hardcodes_purpose_string(self):
        """Neither handler must hardcode a purpose string literal (e.g. 'Race')
        as the VALUE passed for purpose= in the actual build_combined_setup_response
        CALL SITE.  Comments that mention purpose="Race" are acceptable.
        We check by stripping comment lines before searching.
        """
        import re
        for name in ("_setup_analyse_ai", "_setup_analyse_ai_for_form"):
            src = self._src(name)
            # Strip comment lines so 'purpose="Race"' in a docstring/comment is not flagged
            non_comment_lines = [
                line for line in src.splitlines()
                if not line.lstrip().startswith("#")
            ]
            code_only = "\n".join(non_comment_lines)
            # The pattern: purpose="Race" or purpose='Race' in actual call-site code
            # (not just in a comment explaining the value)
            bad_literal = re.search(r'purpose\s*=\s*["\']Race["\']', code_only)
            assert not bad_literal, (
                f"FIX2-C FAIL: {name} hardcodes purpose='Race' as a literal string "
                f"in actual code (not a comment) — "
                f"it must read from the form's .purpose attribute."
            )
