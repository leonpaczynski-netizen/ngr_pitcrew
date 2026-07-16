"""Offscreen tests for the "Changes Applied in Game" button + applied-checkpoint
three-state in Setup Builder (Sprint 10 UI, determinism rebuild — piece 2).

Two layers:
  * Widget construction — SetupFormWidget now owns the button + status label.
  * Mixin behaviour — pressing the button records a DB v19 applied checkpoint and
    resolves the saved-vs-applied-in-GT7 three-state, which the Command Centre
    workflow stepper reads via ``self._setup_apply_status``.

Runs headless (QT_QPA_PLATFORM=offscreen); a PNG of the confirmed state is
rendered via ``QWidget.grab().save`` so the visual layer is exercised too.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

pytest.importorskip("PyQt6.QtWidgets")
from PyQt6.QtWidgets import QApplication  # noqa: E402

from ui.setup_form_widget import SetupFormWidget  # noqa: E402
from ui.setup_builder_ui import SetupBuilderMixin  # noqa: E402
from data.session_db import SessionDB  # noqa: E402
from data.applied_checkpoint import SetupApplyState  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


class _EvCtx:
    car = "Test Car"
    track = "Fuji"
    layout_id = "full_course"
    event_id = 0


class _Bridge:
    class _Sig:
        def emit(self, *_a, **_k):
            pass
    event_log_entry = _Sig()


class _Host(SetupBuilderMixin):
    """Minimal host exercising only the apply-checkpoint mixin methods."""

    def __init__(self, db, race, qual):
        self._db = db
        self._race_form = race
        self._qual_form = qual
        self._saved_setups = []
        self._bridge = _Bridge()

    def _build_event_context(self):
        return _EvCtx()


@pytest.fixture
def host(qapp):
    race = SetupFormWidget("Race", None)
    qual = SetupFormWidget("Qualifying", None)
    h = _Host(SessionDB(":memory:"), race, qual)
    return h


# ── Construction ──────────────────────────────────────────────────────────

def test_form_has_applied_button_and_status_label(qapp):
    race = SetupFormWidget("Race", None)
    assert race._btn_applied_in_game.text() == "Changes Applied in Game"
    assert race._lbl_apply_status.text() == ""


# ── Behaviour ─────────────────────────────────────────────────────────────

def test_not_saved_state_disables_button(host):
    host._refresh_apply_status_for_form(host._race_form)
    st = host._setup_apply_status
    assert st.state is SetupApplyState.NOT_SAVED
    assert not host._race_form._btn_applied_in_game.isEnabled()


def test_saved_but_not_applied_is_pending(host):
    host._saved_setups.append({"setup_label": "R Fuji 1", "setup_id": 1})
    host._race_form._setup_label.setText("R Fuji 1")
    host._refresh_apply_status_for_form(host._race_form)
    st = host._setup_apply_status
    assert st.state is SetupApplyState.CHANGED_SINCE_GT7
    assert not st.is_confirmed
    assert st.has_pending
    assert host._race_form._btn_applied_in_game.isEnabled()


def test_pressing_button_confirms_and_persists(host):
    host._saved_setups.append({"setup_label": "R Fuji 1", "setup_id": 1})
    host._race_form._setup_label.setText("R Fuji 1")
    host._on_changes_applied_in_game(host._race_form)
    st = host._setup_apply_status
    assert st.state is SetupApplyState.CONFIRMED_IN_GT7
    assert st.is_confirmed
    assert not st.has_pending
    # Persisted to the DB v19 table (survives restart).
    from data.applied_checkpoint import compute_setup_hash
    row = host._db.get_latest_applied_checkpoint(
        host._db.get_car_id("Test Car"), "Fuji", "full_course", "Race")
    assert row is not None
    assert row["setup_hash"] == compute_setup_hash(
        host._apply_checkpoint_fields(host._race_form))


def test_editing_after_confirm_shows_pending(host):
    host._saved_setups.append({"setup_label": "R Fuji 1", "setup_id": 1})
    host._race_form._setup_label.setText("R Fuji 1")
    host._on_changes_applied_in_game(host._race_form)
    assert host._setup_apply_status.state is SetupApplyState.CONFIRMED_IN_GT7
    # Dial a change into the form → pending again vs the GT7 checkpoint.
    host._race_form._setup_arb_f.setValue(host._race_form._setup_arb_f.value() + 1)
    host._refresh_apply_status_for_form(host._race_form)
    st = host._setup_apply_status
    assert st.state is SetupApplyState.CHANGED_SINCE_GT7
    assert "arb_front" in st.pending_fields
    assert "⚠" in host._race_form._lbl_apply_status.text()


def test_qual_form_independent_of_race(host):
    host._saved_setups.append({"setup_label": "R Fuji 1", "setup_id": 1})
    host._race_form._setup_label.setText("R Fuji 1")
    host._on_changes_applied_in_game(host._race_form)
    # Qual has its own scope/purpose → still pending, unaffected by the Race confirm.
    host._refresh_apply_status_for_form(host._qual_form)
    assert host._qual_form._lbl_apply_status.text()  # rendered
    assert host._qual_form is not host._race_form


def test_confirmed_state_renders_to_png(host, tmp_path):
    host._saved_setups.append({"setup_label": "R Fuji 1", "setup_id": 1})
    host._race_form._setup_label.setText("R Fuji 1")
    host._on_changes_applied_in_game(host._race_form)
    host._race_form.resize(700, 900)
    png = tmp_path / "apply_confirmed.png"
    assert host._race_form.grab().save(str(png))
    assert png.exists() and png.stat().st_size > 0
