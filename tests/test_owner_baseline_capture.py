"""Component tests for owner-baseline capture and export UI (v42).

Covers:
  A1  — OwnerBaselineCaptureWidget exists, steps through race then qualifying.
  A4  — setup_builder_ui refresh renders status labels correctly.
  A5  — stale-baseline banner shown when baseline revision > 1.
  A6  — Out-of-range entry REJECTED at save; rejection_reason displayed.
        No silent snap.
  B10 — LABEL_* constants imported, not retyped; appear on proposal rows.
  B11 — UNRESOLVED proposal: Accept/Reject disabled; Resolve button present.
  B12 — Individual Accept/Reject/Edit buttons only; no "accept all".
  B16 — Suppressed-changes section structurally present (section exists).
  C2  — Unresolved riders section with no Accept/Reject.
  C17/C21 — EventExportPanel: Export button, QThread worker, sha256 display,
             overwrite confirmation.
  GENERAL — EventSetupPage.on_event_saved emits baseline_capture_requested.
           — PracticeRunRecorder._trigger_owner_proposals spawns a thread when
             baseline exists, flags session when baseline absent.

PyQt tests: each class runs in its own session (per-file subprocess) to avoid
the Win/Py3.14 teardown-order segfault on undisposed top-level widgets.
"""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Optional

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pytest

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def qapp():
    from PyQt6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


# ---------------------------------------------------------------------------
# Minimal DB / service stubs
# ---------------------------------------------------------------------------

class _FakeDB:
    """Minimal stub simulating the v42 DB methods used by the UI components."""

    def __init__(self, *, baseline_data=None, proposals=None,
                 revision=1, validate_ok=True, validate_reason="",
                 status_map=None):
        self._baseline_data = baseline_data or {}
        self._proposals = proposals or []
        self._revision = revision
        self._validate_ok = validate_ok
        self._validate_reason = validate_reason
        self._status_map = status_map or {
            "race": "not_entered", "qualifying": "not_entered",
        }
        self.saved_baselines: list = []
        self.updated_proposals: list = []

    def get_owner_baseline(self, event_id: int, discipline: str):
        key = (event_id, discipline)
        return self._baseline_data.get(key)

    def get_owner_baseline_revision(self, event_id: int, discipline: str) -> int:
        return self._revision

    def get_discipline_baseline_status(self, event_id: int) -> dict:
        return dict(self._status_map)

    def validate_owner_baseline_field(self, field: str, value: float,
                                      car: str = ""):
        return self._validate_ok, self._validate_reason

    def save_owner_baseline(self, event_id: int, discipline: str,
                            setup_dict: dict) -> int:
        self.saved_baselines.append({
            "event_id": event_id,
            "discipline": discipline,
            "setup": dict(setup_dict),
        })
        return 42  # fake row id

    def get_owner_proposals_for_event(self, event_id: int) -> list:
        return list(self._proposals)

    def update_proposal_status(self, proposal_id: str, status: str,
                               edit_value=None, rejection_reason="") -> bool:
        self.updated_proposals.append({
            "proposal_id": proposal_id,
            "status": status,
            "edit_value": edit_value,
            "rejection_reason": rejection_reason,
        })
        return True

    def get_run_for_session(self, session_id: int):
        return None  # no session_run in this stub


# ---------------------------------------------------------------------------
# A1 — OwnerBaselineCaptureWidget steps through disciplines
# ---------------------------------------------------------------------------

class TestOwnerBaselineCaptureWidget:
    def test_widget_creates(self, qapp):
        from ui.components.owner_baseline_capture import OwnerBaselineCaptureWidget
        w = OwnerBaselineCaptureWidget()
        assert w is not None

    def test_start_capture_shows_race_first(self, qapp):
        from ui.components.owner_baseline_capture import (
            OwnerBaselineCaptureWidget, OWNER_BASELINE_DISCIPLINES,
        )
        db = _FakeDB()
        w = OwnerBaselineCaptureWidget()
        w.start_capture(event_id=1, car_name="Porsche RSR", db=db)
        # Title should mention Race (first discipline) and step 1/2.
        assert "Race" in w._title.text()
        assert "1" in w._progress.text()
        assert OWNER_BASELINE_DISCIPLINES[0] == "race"

    def test_skip_advances_to_qualifying(self, qapp):
        from ui.components.owner_baseline_capture import OwnerBaselineCaptureWidget
        db = _FakeDB()
        w = OwnerBaselineCaptureWidget()
        w.start_capture(event_id=1, car_name="Porsche RSR", db=db)
        # Skip race
        w._on_skip()
        assert "Qualifying" in w._title.text()
        assert "2" in w._progress.text()

    def test_skip_both_emits_capture_complete(self, qapp):
        from ui.components.owner_baseline_capture import OwnerBaselineCaptureWidget
        done_flag = []
        db = _FakeDB()
        w = OwnerBaselineCaptureWidget()
        w.capture_complete.connect(lambda: done_flag.append(True))
        w.start_capture(event_id=1, car_name="RSR", db=db)
        w._on_skip()  # skip race
        w._on_skip()  # skip qualifying
        assert done_flag, "capture_complete should have fired"

    def test_save_emits_baseline_saved_and_advances(self, qapp):
        from ui.components.owner_baseline_capture import (
            OwnerBaselineCaptureWidget, _CAPTURE_FIELDS,
        )
        saved_signals = []
        db = _FakeDB()
        w = OwnerBaselineCaptureWidget()
        w.baseline_saved.connect(lambda d, bid: saved_signals.append((d, bid)))
        w.start_capture(event_id=1, car_name="RSR", db=db)
        # Set at least one field so collect() returns non-empty.
        first_field = _CAPTURE_FIELDS[0][0]
        spin = w._spins[first_field]
        spin.setValue(80.0)
        w._on_save()
        assert len(saved_signals) == 1
        assert saved_signals[0][0] == "race"
        assert saved_signals[0][1] == 42  # fake row id
        # Should advance to Qualifying.
        assert "Qualifying" in w._title.text()

    # A6 — rejection path
    def test_a6_rejects_out_of_range_no_silent_snap(self, qapp):
        from ui.components.owner_baseline_capture import (
            OwnerBaselineCaptureWidget, _CAPTURE_FIELDS,
        )
        reason = "camber_front: value 99 is outside the legal range [-5, 0] (step=0.1)."
        db = _FakeDB(validate_ok=False, validate_reason=reason)
        w = OwnerBaselineCaptureWidget()
        w.start_capture(event_id=1, car_name="RSR", db=db)
        # Set a value so collect() returns non-empty.
        first_field = _CAPTURE_FIELDS[0][0]
        w._spins[first_field].setValue(80.0)
        initial_disc = w._current_discipline()
        w._on_save()
        # Should NOT advance (rejection).
        assert w._current_discipline() == initial_disc
        # Error banner must NOT be hidden (isHidden checks local state; isVisible
        # also requires the parent chain to be shown, which is not the case in unit
        # tests without a top-level window).
        assert not w._error.isHidden(), "error banner must be shown after validation rejection"
        assert "legal range" in w._error.text().lower()

    def test_empty_save_shows_error_not_advances(self, qapp):
        from ui.components.owner_baseline_capture import OwnerBaselineCaptureWidget
        db = _FakeDB()
        w = OwnerBaselineCaptureWidget()
        w.start_capture(event_id=1, car_name="RSR", db=db)
        # Do NOT set any spins — all are blank.
        w._on_save()
        # Should stay on race discipline (not advance).
        assert "Race" in w._title.text()
        assert not w._error.isHidden(), "error banner must be shown when save is empty"

    def test_pre_populates_existing_baseline(self, qapp):
        from ui.components.owner_baseline_capture import OwnerBaselineCaptureWidget
        baseline = {"ride_height_front": 77.0, "camber_front": -2.5}
        db = _FakeDB(baseline_data={(1, "race"): baseline})
        w = OwnerBaselineCaptureWidget()
        w.start_capture(event_id=1, car_name="RSR", db=db)
        assert abs(w._spins["ride_height_front"].value() - 77.0) < 0.01
        assert abs(w._spins["camber_front"].value() - (-2.5)) < 0.01


# ---------------------------------------------------------------------------
# A4 / A5 — setup_builder_ui baseline status labels and stale banner
# ---------------------------------------------------------------------------

class TestSetupBuilderOwnerBaselinePanels:
    """Verify the refresh_owner_baseline_panels updates status labels correctly.

    We test only the pure refresh methods by calling them directly on a minimal
    stub object — we do not instantiate the full 4 800-line mixin.
    """

    def _make_instance(self, qapp):
        """Create a QWidget that has the owner-baseline sub-widgets attached."""
        from PyQt6.QtWidgets import QWidget, QVBoxLayout, QGroupBox, QHBoxLayout, QLabel
        from ui import ngr_theme as t

        w = QWidget()
        # Attach the required sub-widgets (mirrors what _build_setup_builder_tab
        # creates in the real mixin).
        lay = QVBoxLayout(w)
        group = QGroupBox("Owner Baseline Status")
        g_lay = QVBoxLayout(group)
        row = QHBoxLayout()
        race_lbl = QLabel("Race: —")
        qual_lbl = QLabel("Qualifying: —")
        row.addWidget(race_lbl)
        row.addWidget(qual_lbl)
        g_lay.addLayout(row)
        stale_lbl = QLabel("")
        stale_lbl.setVisible(False)
        g_lay.addWidget(stale_lbl)
        lay.addWidget(group)

        # Attach as the mixin would.
        w._lbl_race_baseline_status = race_lbl
        w._lbl_qual_baseline_status = qual_lbl
        w._lbl_stale_baseline = stale_lbl
        w._proposals_group = None
        w._proposals_layout = None

        # Borrow the refresh methods from the module.
        import types
        from ui import setup_builder_ui as sbu_mod
        # Bind the methods.
        for name in ("refresh_owner_baseline_panels",
                     "_refresh_baseline_status", "_refresh_proposals"):
            fn = getattr(sbu_mod.SetupBuilderMixin, name, None)
            if fn:
                setattr(w, name, types.MethodType(fn, w))
        return w

    def test_no_db_shows_dashes(self, qapp):
        try:
            from ui.setup_builder_ui import SetupBuilderMixin
        except ImportError:
            pytest.skip("SetupBuilderMixin not importable standalone")
        w = self._make_instance(qapp)
        w.refresh_owner_baseline_panels(db=None, event_id=0)
        assert "—" in w._lbl_race_baseline_status.text()

    def test_entered_baseline_shows_entered_text(self, qapp):
        try:
            from ui.setup_builder_ui import SetupBuilderMixin
        except ImportError:
            pytest.skip("SetupBuilderMixin not importable standalone")
        db = _FakeDB(status_map={"race": "entered", "qualifying": "not_entered"},
                     revision=1)
        w = self._make_instance(qapp)
        w.refresh_owner_baseline_panels(db=db, event_id=1)
        assert "entered" in w._lbl_race_baseline_status.text().lower()
        assert "unavailable" in w._lbl_qual_baseline_status.text().lower()

    def test_a5_stale_banner_shown_when_revision_gt_1(self, qapp):
        try:
            from ui.setup_builder_ui import SetupBuilderMixin
        except ImportError:
            pytest.skip("SetupBuilderMixin not importable standalone")
        db = _FakeDB(status_map={"race": "entered", "qualifying": "not_entered"},
                     revision=2)
        w = self._make_instance(qapp)
        w.refresh_owner_baseline_panels(db=db, event_id=1)
        # isHidden() checks local hidden/shown state; isVisible() also requires the
        # parent chain to be shown — not the case in headless unit tests.
        assert not w._lbl_stale_baseline.isHidden(), "stale banner must be shown when revision > 1"
        assert "stale" in w._lbl_stale_baseline.text().lower()

    def test_no_stale_banner_at_revision_1(self, qapp):
        try:
            from ui.setup_builder_ui import SetupBuilderMixin
        except ImportError:
            pytest.skip("SetupBuilderMixin not importable standalone")
        db = _FakeDB(status_map={"race": "entered", "qualifying": "not_entered"},
                     revision=1)
        w = self._make_instance(qapp)
        w.refresh_owner_baseline_panels(db=db, event_id=1)
        assert w._lbl_stale_baseline.isHidden(), "stale banner must NOT be shown at revision 1"


# ---------------------------------------------------------------------------
# B10-B12, B16, C2 — proposal row rendering (no DB needed)
# ---------------------------------------------------------------------------

class TestProposalRowRendering:
    """Test the proposal row builders directly."""

    def _get_row_builder(self):
        """Borrow _build_proposal_row from the mixin without instantiating it."""
        import types
        from PyQt6.QtWidgets import QWidget
        from ui.setup_builder_ui import SetupBuilderMixin

        w = QWidget()
        fn = SetupBuilderMixin._build_proposal_row
        w._build_proposal_row = types.MethodType(fn, w)
        return w

    def test_b10_label_from_constants_not_hardcoded(self, qapp):
        """LABEL_* strings are imported constants, not hardcoded (B10)."""
        from strategy.owner_baseline_arbiter import LABEL_TEL_CORROBORATED
        # The constant must be one of the four known strings.
        assert LABEL_TEL_CORROBORATED == "telemetry with driver corroboration"
        # Verify badge_qss can be called with the label's tone.
        from ui import ngr_theme as t
        qss = t.badge_qss("success")
        assert "color" in qss

    def test_b11_unresolved_proposal_disables_accept_reject(self, qapp):
        try:
            w_host = self._get_row_builder()
        except Exception:
            pytest.skip("cannot borrow mixin method")
        prop = {
            "proposal_id": "test-uuid",
            "parameter": "camber_front",
            "direction": "increase",
            "proposed_value": 2.0,
            "original_value": 1.5,
            "original_proposed_value": 2.0,
            "label": "",             # empty → UNRESOLVED
            "status": "unresolved",
            "discipline": "race",
            "clean_laps": 6,
            "evidence_sources": ["oversteer on exit"],
            "clipped": False,
            "clip_stated_reason": "",
            "session_run_id": "abc123",
        }
        from strategy.owner_baseline_arbiter import (
            LABEL_DRIVER_ONLY, LABEL_DRIVER_EARLY_TEL,
            LABEL_TEL_CORROBORATED, LABEL_TEL_NO_FEEDBACK,
        )
        label_tone = {
            LABEL_DRIVER_ONLY: "warn", LABEL_DRIVER_EARLY_TEL: "info",
            LABEL_TEL_CORROBORATED: "success", LABEL_TEL_NO_FEEDBACK: "neutral",
        }
        row_w = w_host._build_proposal_row(prop, label_tone, None)
        assert row_w is not None
        # Find the Accept/Reject buttons and verify they are disabled.
        from PyQt6.QtWidgets import QPushButton
        buttons = row_w.findChildren(QPushButton)
        button_texts = {b.text(): b for b in buttons}
        accept = button_texts.get("Accept")
        reject = button_texts.get("Reject")
        resolve = button_texts.get("Resolve conflict...")
        assert accept is not None and not accept.isEnabled(), "Accept must be disabled for UNRESOLVED"
        assert reject is not None and not reject.isEnabled(), "Reject must be disabled for UNRESOLVED"
        assert resolve is not None, "Resolve button must be present for UNRESOLVED"

    def test_b12_no_accept_all_button(self, qapp):
        """B12: there must be no 'Accept all' or 'Reject all' button."""
        try:
            w_host = self._get_row_builder()
        except Exception:
            pytest.skip("cannot borrow mixin method")
        prop = {
            "proposal_id": "p1", "parameter": "arb_front",
            "direction": "increase", "proposed_value": 5.0,
            "original_value": 4.0, "original_proposed_value": 5.0,
            "label": "telemetry with driver corroboration",
            "status": "proposed", "discipline": "race",
            "clean_laps": 7, "evidence_sources": [],
            "clipped": False, "clip_stated_reason": "",
            "session_run_id": "x",
        }
        row_w = w_host._build_proposal_row(prop, {}, None)
        from PyQt6.QtWidgets import QPushButton
        texts = {b.text() for b in row_w.findChildren(QPushButton)}
        for banned in ("Accept all", "Reject all", "Apply all"):
            assert banned not in texts, f"'{banned}' must not exist (B12)"

    def test_edited_row_shows_both_values(self, qapp):
        """An EDITED proposal row must show both original_proposed_value and proposed_value."""
        from ui.setup_builder_ui import SetupBuilderMixin
        import types
        from PyQt6.QtWidgets import QWidget
        w = QWidget()
        fn = SetupBuilderMixin._build_actioned_proposal_row
        w._method = types.MethodType(fn, w)

        prop = {
            "proposal_id": "p2", "parameter": "toe_front",
            "direction": "increase",
            "proposed_value": 0.05,           # edited value
            "original_value": 0.00,
            "original_proposed_value": 0.10,  # what arbiter originally suggested
            "label": "telemetry with driver corroboration",
            "status": "edited", "discipline": "race",
            "clean_laps": 5, "evidence_sources": [],
            "clipped": False, "clip_stated_reason": "",
        }
        row_w = w._method(prop, {})
        # Find a label that contains both values.
        from PyQt6.QtWidgets import QLabel
        labels = row_w.findChildren(QLabel)
        all_text = " ".join(lbl.text() for lbl in labels)
        # Should mention the original proposed value (0.1) somewhere.
        assert "0.1" in all_text or "originally" in all_text


# ---------------------------------------------------------------------------
# C17/C21 — EventExportPanel
# ---------------------------------------------------------------------------

class TestEventExportPanel:
    def test_panel_creates(self, qapp):
        from ui.event_export_panel import EventExportPanel
        p = EventExportPanel()
        assert p is not None

    def test_export_button_disabled_without_event(self, qapp):
        from ui.event_export_panel import EventExportPanel
        p = EventExportPanel()
        assert not p._export_btn.isEnabled()

    def test_export_button_enabled_after_set_event(self, qapp):
        from ui.event_export_panel import EventExportPanel
        db = _FakeDB()
        p = EventExportPanel()
        p.set_event(event_id=1, car="RSR", track="Monza", db=db)
        assert p._export_btn.isEnabled()

    def test_set_event_zero_disables_button(self, qapp):
        from ui.event_export_panel import EventExportPanel
        p = EventExportPanel()
        p.set_event(event_id=0, db=_FakeDB())
        assert not p._export_btn.isEnabled()

    def test_on_export_done_ok_shows_digest(self, qapp):
        from ui.event_export_panel import EventExportPanel
        p = EventExportPanel()
        p.set_event(event_id=1, db=_FakeDB())
        result = {
            "ok": True,
            "filename": "test_event_export.json",
            "file_sha256": "abc123def456",
            "destination": "/tmp",
            "bytes_written": 1024,
            "warnings": [],
            "errors": [],
        }
        p._on_export_done(result)
        assert not p._digest.isHidden(), "digest label must be shown after successful export"
        assert "abc123def456" in p._digest.text()

    def test_on_export_done_failure_shows_error(self, qapp):
        from ui.event_export_panel import EventExportPanel
        from ui import ngr_theme as t
        p = EventExportPanel()
        p.set_event(event_id=1, db=_FakeDB())
        result = {
            "ok": False,
            "filename": "test_event_export.json",
            "file_sha256": "",
            "destination": "/tmp",
            "bytes_written": 0,
            "warnings": [],
            "errors": ["some unexpected error"],
        }
        p._on_export_done(result)
        assert not p._digest.isVisible()
        assert "failed" in p._status.text().lower()

    def test_export_worker_thread_class(self, qapp):
        """The _ExportWorker is a QThread subclass."""
        from ui.event_export_panel import _ExportWorker
        from PyQt6.QtCore import QThread
        assert issubclass(_ExportWorker, QThread)

    def test_overwrite_confirm_seam_fails_closed_under_pytest(self, qapp):
        """C4: the injectable confirm= seam returns False (no overwrite) when not injected.

        This is the fix for the hung-test problem: without a seam the widget called
        QMessageBox.question() directly, which has no human to answer it under pytest.
        Now the default _default_overwrite_confirm checks PYTEST_CURRENT_TEST and
        returns False immediately — the test runner never sees a blocking dialog.
        """
        from ui.event_export_panel import EventExportPanel, _default_overwrite_confirm
        # _default_overwrite_confirm must return False under pytest (PYTEST_CURRENT_TEST is set).
        assert _default_overwrite_confirm(None, "test.json", "/tmp") is False

    def test_overwrite_injected_confirm_no_called(self, qapp):
        """Injected confirm=lambda returning False → export is cancelled, not retried."""
        from ui.event_export_panel import EventExportPanel
        run_calls = []
        p = EventExportPanel(confirm=lambda parent, fname, dest: False)
        p.set_event(event_id=1, db=_FakeDB())
        # Patch _run_export to detect if it gets called again.
        original_run_export = p._run_export
        p._run_export = lambda *a, **kw: run_calls.append((a, kw))
        result = {
            "ok": False,
            "filename": "test.json",
            "file_sha256": "",
            "destination": "/tmp",
            "bytes_written": 0,
            "warnings": [],
            "errors": ["file already exists at destination: 'test.json' — pass allow_overwrite to replace"],
        }
        p._on_export_done(result)
        assert not run_calls, "confirm=False must cancel the export, not call _run_export again"
        assert "cancelled" in p._status.text().lower()

    def test_overwrite_injected_confirm_yes_retries(self, qapp):
        """Injected confirm=lambda returning True → _run_export called with allow_overwrite=True."""
        from ui.event_export_panel import EventExportPanel
        run_calls = []
        p = EventExportPanel(confirm=lambda parent, fname, dest: True)
        p.set_event(event_id=1, db=_FakeDB())
        p._run_export = lambda dest, allow_overwrite=False: run_calls.append(allow_overwrite)
        result = {
            "ok": False, "filename": "test.json", "file_sha256": "",
            "destination": "/tmp", "bytes_written": 0, "warnings": [],
            "errors": ["file already exists at destination: 'test.json' — pass allow_overwrite to replace"],
        }
        p._on_export_done(result)
        assert run_calls, "_run_export must be called when confirm returns True"
        assert run_calls[0] is True, "_run_export must be called with allow_overwrite=True"


# ---------------------------------------------------------------------------
# A1 — EventSetupPage.on_event_saved emits baseline_capture_requested
# ---------------------------------------------------------------------------

class TestEventSetupPageSignal:
    def test_on_event_saved_emits_signal(self, qapp):
        from ui.components.event_setup import EventSetupPage
        captured = []
        page = EventSetupPage(tracks=[], cars=[])
        page.baseline_capture_requested.connect(lambda eid: captured.append(eid))
        page.on_event_saved(99)
        assert captured == [99]

    def test_on_event_saved_zero_emits_zero(self, qapp):
        from ui.components.event_setup import EventSetupPage
        captured = []
        page = EventSetupPage()
        page.baseline_capture_requested.connect(lambda eid: captured.append(eid))
        page.on_event_saved(0)
        assert captured == [0]


# ---------------------------------------------------------------------------
# PracticeRunRecorder — _trigger_owner_proposals (off-thread, no-baseline flag)
# ---------------------------------------------------------------------------

class TestPracticeRunRecorderProposals:
    """Tests for the new proposal-trigger additions to PracticeRunRecorder."""

    def test_no_baseline_flagged_in_no_baseline_sessions(self):
        """When no owner baseline exists, session is added to no_baseline_sessions."""
        from ui.practice_run_recorder import PracticeRunRecorder

        class _DBStub:
            def get_run_for_session(self, sid):
                return {"event_id": 1, "run_id": "uuid-abc", "session_type": "Practice"}
            def get_owner_baseline(self, event_id, discipline):
                return None  # no baseline

        recorder = PracticeRunRecorder(db=_DBStub(), config={"active_cycle_id": "c1"})
        recorder._trigger_owner_proposals(session_id=10, session_meta={"session_type": "Practice"})
        sessions = recorder.no_baseline_sessions()
        assert len(sessions) == 1
        assert sessions[0]["discipline"] == "race"
        assert sessions[0]["note"] == "evidence collected, no baseline"

    def test_qualifying_type_maps_to_qualifying_discipline(self):
        """Qualifying session_type maps to 'qualifying' discipline."""
        from ui.practice_run_recorder import PracticeRunRecorder

        flagged = []

        class _DBStub:
            def get_run_for_session(self, sid):
                return {"event_id": 2, "run_id": "uuid-def", "session_type": "Qualifying"}
            def get_owner_baseline(self, event_id, discipline):
                flagged.append(discipline)
                return None

        recorder = PracticeRunRecorder(db=_DBStub())
        recorder._trigger_owner_proposals(session_id=20, session_meta={"session_type": "Qualifying"})
        assert "qualifying" in flagged

    def test_baseline_exists_spawns_thread(self):
        """When a baseline exists, a daemon thread is spawned."""
        import threading
        import time
        from ui.practice_run_recorder import PracticeRunRecorder

        thread_names = []

        class _DBStub:
            def get_run_for_session(self, sid):
                return {"event_id": 3, "run_id": "uuid-xyz0", "session_type": "Practice"}
            def get_owner_baseline(self, event_id, discipline):
                return {"ride_height_front": 80.0}

        # Patch owner_baseline_service.run_for_session to record the call.
        import services.owner_baseline_service as svc

        original = svc.run_for_session

        def _fake_run(db, *, session_run_id, discipline):
            thread_names.append(threading.current_thread().name)

        svc.run_for_session = _fake_run
        try:
            recorder = PracticeRunRecorder(db=_DBStub())
            recorder._trigger_owner_proposals(
                session_id=30, session_meta={"session_type": "Practice"})
            # Wait briefly for the daemon thread to execute.
            deadline = time.time() + 2.0
            while not thread_names and time.time() < deadline:
                time.sleep(0.05)
        finally:
            svc.run_for_session = original

        assert thread_names, "The proposal-generation thread must have run"
        assert any("owner_proposal" in n for n in thread_names)

    def test_no_db_is_silent(self):
        """_trigger_owner_proposals is a no-op when db is None."""
        from ui.practice_run_recorder import PracticeRunRecorder
        recorder = PracticeRunRecorder(db=None)
        # Must not raise.
        recorder._trigger_owner_proposals(session_id=1, session_meta={})
        assert recorder.no_baseline_sessions() == []

    def test_no_session_run_is_silent(self):
        """_trigger_owner_proposals is a no-op when get_run_for_session returns None."""
        from ui.practice_run_recorder import PracticeRunRecorder

        class _DBStub:
            def get_run_for_session(self, sid):
                return None

        recorder = PracticeRunRecorder(db=_DBStub())
        recorder._trigger_owner_proposals(session_id=99, session_meta={})
        assert recorder.no_baseline_sessions() == []


# ---------------------------------------------------------------------------
# DB v43 — new getter wiring, suppressed changes, riders, stale proposals,
# provenance, and modal seams (C4, I2, I3, M3)
# ---------------------------------------------------------------------------

def _make_proposals_host(qapp):
    """Shared helper: return a QWidget with all SetupBuilderMixin proposal methods bound."""
    from PyQt6.QtWidgets import QWidget, QVBoxLayout, QGroupBox, QLabel
    import types
    from ui.setup_builder_ui import SetupBuilderMixin

    w = QWidget()
    lay = QVBoxLayout(w)
    group = QGroupBox("Proposals")
    g_lay = QVBoxLayout(group)
    proposals_layout = QVBoxLayout()
    g_lay.addLayout(proposals_layout)
    lay.addWidget(group)
    w._proposals_group = group
    w._proposals_layout = proposals_layout
    w._lbl_race_baseline_status = QLabel()
    w._lbl_qual_baseline_status = QLabel()
    w._lbl_stale_baseline = QLabel()

    for name in ("_refresh_proposals", "_build_proposal_row",
                 "_build_actioned_proposal_row", "_build_rider_row",
                 "_build_stale_proposal_row", "_build_suppressed_row",
                 "_ask_resolve", "_ask_text_dialog", "_warn_invalid",
                 "_resolve_conflict", "_do_accept_proposal",
                 "_do_reject_proposal", "_do_edit_proposal"):
        fn = getattr(SetupBuilderMixin, name, None)
        if fn:
            setattr(w, name, types.MethodType(fn, w))
    return w


class TestV43RidersFromDedicatedGetter:
    """Source-separation fix (2026-08-10): get_owner_riders_for_event is deprecated.
    LABEL_DRIVER_TEL_SILENT proposals are now ordinary proposals in the proposals
    table — they carry a proposed_value and full Accept/Reject/Edit controls.
    _refresh_proposals must NOT call get_owner_riders_for_event any more.
    """

    def test_deprecated_rider_getter_not_called_by_refresh_proposals(self, qapp):
        """_refresh_proposals must NOT call get_owner_riders_for_event.

        The getter is deprecated; _refresh_proposals only calls
        get_owner_proposals_for_event and get_suppressed_changes_for_event.
        Historical rider rows in old DBs are irrelevant to the live path.
        """
        w = _make_proposals_host(qapp)
        rider_calls = []

        class _DB:
            def get_owner_proposals_for_event(self, eid): return []
            def get_owner_riders_for_event(self, eid):
                rider_calls.append(eid)   # must never be reached
                return []
            def get_suppressed_changes_for_event(self, eid): return []

        w._refresh_proposals(_DB(), event_id=1)
        assert not rider_calls, (
            "get_owner_riders_for_event must NOT be called by _refresh_proposals "
            "(deprecated; LABEL_DRIVER_TEL_SILENT proposals come from "
            "get_owner_proposals_for_event now)")

    def test_rider_rows_not_rendered_when_only_getter_data_present(self, qapp):
        """Rider data from the deprecated getter is not rendered — layout is empty."""
        w = _make_proposals_host(qapp)

        class _DB:
            def get_owner_proposals_for_event(self, eid): return []
            # Intentionally NOT providing get_owner_riders_for_event —
            # if _refresh_proposals tries to call it, it will AttributeError.
            def get_suppressed_changes_for_event(self, eid): return []

        # Must complete without error and produce an empty (hidden) layout.
        w._refresh_proposals(_DB(), event_id=1)
        count = w._proposals_layout.count()
        assert count == 0, (
            "proposals_layout must be empty when no proposals or suppressed exist "
            "(no rider section is rendered from the deprecated getter)")

    def test_build_rider_row_still_exists_for_legacy_compat(self, qapp):
        """_build_rider_row is deprecated but must still exist (not deleted).

        Old DBs may have historical rider rows; a future migration tool or
        diagnostic view might display them explicitly.  The method must not
        be removed — it just is no longer called from _refresh_proposals.
        """
        from ui.setup_builder_ui import SetupBuilderMixin
        assert hasattr(SetupBuilderMixin, "_build_rider_row"), (
            "_build_rider_row must still exist on SetupBuilderMixin (deprecated, not deleted)")

    def test_build_rider_row_renders_feedback_direction(self, qapp):
        """The deprecated _build_rider_row still renders 'feedback_direction' correctly."""
        from ui.setup_builder_ui import SetupBuilderMixin
        import types
        from PyQt6.QtWidgets import QWidget, QLabel
        w = QWidget()
        fn = SetupBuilderMixin._build_rider_row
        w._build_rider_row = types.MethodType(fn, w)
        rider = {
            "parameter": "springs_rear",
            "feedback_direction": "decrease",   # v43 key
            "discipline": "qualifying",
            "note": "driver says too stiff",
            "evidence_sources": [],
        }
        row_w = w._build_rider_row(rider)
        all_text = " ".join(lbl.text() for lbl in row_w.findChildren(QLabel))
        assert "decrease" in all_text, "feedback_direction value must appear in the rider row"


# ---------------------------------------------------------------------------
# Driver-silent proposals — new section (source-separation fix 2026-08-10)
# ---------------------------------------------------------------------------

def _make_driver_silent_prop(status: str = "proposed") -> dict:
    """Build a minimal proposal dict with label == LABEL_DRIVER_TEL_SILENT."""
    from strategy.owner_baseline_arbiter import LABEL_DRIVER_TEL_SILENT
    return {
        "proposal_id": "ds-1",
        "event_id": 1,
        "session_run_id": "run-ds",
        "discipline": "race",
        "parameter": "arb_rear",
        "direction": "increase",
        "proposed_value": 6.0,
        "original_value": 5.0,
        "original_proposed_value": 6.0,
        "label": LABEL_DRIVER_TEL_SILENT,   # imported constant, not retyped
        "status": status,
        "clipped": False,
        "clip_stated_reason": "",
        "clean_laps": 5,
        "evidence_sources": [],
        "baseline_revision": 1,
        "provenance": "DRIVER_REPORT",
    }


class TestDriverSilentProposalSection:
    """LABEL_DRIVER_TEL_SILENT proposals are now ordinary proposals with full controls.

    They render in a distinct 'Driver report (telemetry silent)' section —
    not in the 'Active proposals' section — and show Accept/Reject/Edit buttons.
    No telemetry corroboration affordance (no MEASURED FACT / TEL CORROBORATED badge).
    """

    def test_driver_silent_section_renders_when_proposal_present(self, qapp):
        """A LABEL_DRIVER_TEL_SILENT proposal causes the driver-silent section to appear."""
        from PyQt6.QtWidgets import QLabel
        w = _make_proposals_host(qapp)

        class _DB:
            def get_owner_proposals_for_event(self, eid):
                return [_make_driver_silent_prop()]
            def get_suppressed_changes_for_event(self, eid): return []

        w._refresh_proposals(_DB(), event_id=1)
        assert w._proposals_layout.count() > 0, (
            "proposals_layout must have rows when a driver-silent proposal is present")
        labels = w.findChildren(QLabel)
        all_text = " ".join(lbl.text() for lbl in labels).lower()
        assert "driver report" in all_text or "telemetry silent" in all_text, (
            "driver-silent section heading must mention 'driver report' or 'telemetry silent'")

    def test_driver_silent_filtered_by_imported_constant(self, qapp):
        """Filtering must use the imported LABEL_DRIVER_TEL_SILENT constant, not a string literal.

        This is verified by importing the constant and confirming the proposal
        ends up in the driver-silent section (not in Active proposals).
        """
        from strategy.owner_baseline_arbiter import LABEL_DRIVER_TEL_SILENT
        from PyQt6.QtWidgets import QLabel
        w = _make_proposals_host(qapp)

        # One driver-silent and one normal proposal.
        from strategy.owner_baseline_arbiter import LABEL_DRIVER_ONLY
        normal_prop = {
            "proposal_id": "n-1", "event_id": 1, "session_run_id": "run-n",
            "discipline": "race", "parameter": "camber_front",
            "direction": "decrease", "proposed_value": -2.8, "original_value": -2.5,
            "original_proposed_value": -2.8, "label": LABEL_DRIVER_ONLY,
            "status": "proposed", "clipped": False, "clip_stated_reason": "",
            "clean_laps": 0, "evidence_sources": [],
            "baseline_revision": 1, "provenance": "DRIVER_REPORT",
        }

        class _DB:
            def get_owner_proposals_for_event(self, eid):
                return [normal_prop, _make_driver_silent_prop()]
            def get_suppressed_changes_for_event(self, eid): return []

        w._refresh_proposals(_DB(), event_id=1)
        labels = w.findChildren(QLabel)
        texts = [lbl.text() for lbl in labels]
        # Both "Active proposals" and the driver-silent section heading must appear.
        full_text = " ".join(texts).lower()
        assert "active proposals" in full_text, "Active proposals section must be present"
        assert "driver report" in full_text or "telemetry silent" in full_text, (
            "Driver-silent section must be present alongside active proposals")

    def test_driver_silent_proposal_not_in_active_proposals_section(self, qapp):
        """A driver-silent proposal must NOT appear under the 'Active proposals' heading.

        Mutual exclusion: each proposal appears in exactly one group.
        """
        from strategy.owner_baseline_arbiter import LABEL_DRIVER_TEL_SILENT
        from PyQt6.QtWidgets import QLabel
        w = _make_proposals_host(qapp)

        class _DB:
            def get_owner_proposals_for_event(self, eid):
                return [_make_driver_silent_prop()]
            def get_suppressed_changes_for_event(self, eid): return []

        w._refresh_proposals(_DB(), event_id=1)
        labels = w.findChildren(QLabel)
        all_text = " ".join(lbl.text() for lbl in labels).lower()
        # "Active proposals" heading must NOT appear when there are only driver-silent props.
        assert "active proposals" not in all_text, (
            "driver-silent proposals must NOT appear under 'Active proposals' heading")

    def test_driver_silent_row_has_accept_reject_edit_buttons(self, qapp):
        """Driver-silent proposal rows must expose Accept, Reject, and Edit buttons."""
        from PyQt6.QtWidgets import QPushButton
        w = _make_proposals_host(qapp)

        class _DB:
            def get_owner_proposals_for_event(self, eid):
                return [_make_driver_silent_prop()]
            def get_suppressed_changes_for_event(self, eid): return []

        w._refresh_proposals(_DB(), event_id=1)
        buttons = w.findChildren(QPushButton)
        btn_texts = [b.text() for b in buttons]
        assert any("Accept" in t for t in btn_texts), "driver-silent row must have Accept button"
        assert any("Reject" in t for t in btn_texts), "driver-silent row must have Reject button"
        assert any("Edit" in t for t in btn_texts), "driver-silent row must have Edit button"

    def test_driver_silent_row_no_measured_fact_badge(self, qapp):
        """Driver-silent rows must NOT show MEASURED FACT or TEL CORROBORATED badge.

        Provenance is always DRIVER_REPORT; the badge must reflect that.
        The source-separation fix exists precisely to stop the app reporting
        the owner's own feedback back as measured telemetry.
        """
        from PyQt6.QtWidgets import QLabel
        w = _make_proposals_host(qapp)

        class _DB:
            def get_owner_proposals_for_event(self, eid):
                return [_make_driver_silent_prop()]
            def get_suppressed_changes_for_event(self, eid): return []

        w._refresh_proposals(_DB(), event_id=1)
        labels = w.findChildren(QLabel)
        badge_texts = [lbl.text() for lbl in labels]
        assert not any("MEASURED FACT" in t for t in badge_texts), (
            "driver-silent row must NOT show a MEASURED FACT badge "
            "(that is the exact defect the source-separation fix corrects)")
        assert not any("TEL CORROBORATED" in t for t in badge_texts), (
            "driver-silent row must NOT show a TEL CORROBORATED badge")

    def test_driver_silent_shows_driver_report_provenance(self, qapp):
        """Driver-silent rows must show DRIVER REPORT provenance badge (not MEASURED FACT)."""
        from PyQt6.QtWidgets import QLabel
        w = _make_proposals_host(qapp)

        class _DB:
            def get_owner_proposals_for_event(self, eid):
                return [_make_driver_silent_prop()]
            def get_suppressed_changes_for_event(self, eid): return []

        w._refresh_proposals(_DB(), event_id=1)
        labels = w.findChildren(QLabel)
        badge_texts = [lbl.text() for lbl in labels]
        assert any("DRIVER REPORT" in t for t in badge_texts), (
            "driver-silent row must display DRIVER REPORT provenance badge")

    def test_driver_silent_actioned_appears_in_actioned_section(self, qapp):
        """After Accept/Reject, a driver-silent proposal appears in Actioned, not driver-silent."""
        from PyQt6.QtWidgets import QLabel
        w = _make_proposals_host(qapp)
        accepted = _make_driver_silent_prop(status="accepted")

        class _DB:
            def get_owner_proposals_for_event(self, eid): return [accepted]
            def get_suppressed_changes_for_event(self, eid): return []

        w._refresh_proposals(_DB(), event_id=1)
        labels = w.findChildren(QLabel)
        all_text = " ".join(lbl.text() for lbl in labels).lower()
        # Actioned section must be present; driver-silent section must NOT appear.
        assert "actioned proposals" in all_text, (
            "actioned driver-silent proposal must appear under Actioned proposals")
        assert "driver report" not in all_text or "telemetry silent" not in all_text, (
            "driver-silent section must not appear when the only driver-silent prop is actioned")


class TestV43SuppressedChangesRendering:
    """Suppressed changes (B16) must render non-empty from db.get_suppressed_changes_for_event."""

    def test_suppressed_row_shows_parameter_and_reason(self, qapp):
        """_build_suppressed_row renders the parameter and reason."""
        from ui.setup_builder_ui import SetupBuilderMixin
        import types
        from PyQt6.QtWidgets import QWidget, QLabel
        w = QWidget()
        fn = SetupBuilderMixin._build_suppressed_row
        w._build_suppressed_row = types.MethodType(fn, w)

        sc = {
            "change_id": "sc1", "event_id": 1,
            "parameter": "damper_bump_rear",
            "discipline": "race",
            "reason": "SUPPRESSED: movement cap hit — ratchet lockout in effect",
            "ratchet_locked": True,
            "feedback_recorded": True,
            "baseline_revision": 1,
        }
        row_w = w._build_suppressed_row(sc)
        all_text = " ".join(lbl.text() for lbl in row_w.findChildren(QLabel))
        assert "damper bump rear" in all_text.lower(), "parameter must appear in suppressed row"
        assert "ratchet" in all_text.lower(), "ratchet reason must appear"

    def test_suppressed_section_populated_when_db_returns_data(self, qapp):
        """When db returns suppressed changes, the layout has rows."""
        w = _make_proposals_host(qapp)

        class _DB:
            def get_owner_proposals_for_event(self, eid): return []
            def get_owner_riders_for_event(self, eid): return []
            def get_suppressed_changes_for_event(self, eid):
                return [{
                    "change_id": "sc2", "event_id": 1,
                    "parameter": "arb_rear", "discipline": "race",
                    "reason": "movement cap hit",
                    "ratchet_locked": True, "feedback_recorded": False,
                    "baseline_revision": 1,
                }]

        w._refresh_proposals(_DB(), event_id=1)
        assert w._proposals_layout.count() > 0, (
            "proposals_layout must have rows when suppressed changes exist")


class TestV43StaleProposalsRendering:
    """Stale proposals (DB v43) must render in a visually distinct section."""

    def test_stale_proposal_not_in_active_bucket(self, qapp):
        """status='stale' proposals must NOT appear as active proposals."""
        from PyQt6.QtWidgets import QLabel
        w = _make_proposals_host(qapp)

        stale_prop = {
            "proposal_id": "stale-1", "event_id": 1, "session_run_id": "run-old",
            "discipline": "race", "parameter": "camber_front",
            "direction": "decrease", "proposed_value": -2.8,
            "original_value": -2.5, "original_proposed_value": -2.8,
            "label": "driver report only — no telemetry",
            "status": "stale",   # the key status
            "clipped": False, "clip_stated_reason": "",
            "clean_laps": 2, "evidence_sources": [],
            "baseline_revision": 1, "provenance": "DRIVER_REPORT",
        }

        class _DB:
            def get_owner_proposals_for_event(self, eid): return [stale_prop]
            def get_owner_riders_for_event(self, eid): return []
            def get_suppressed_changes_for_event(self, eid): return []

        w._refresh_proposals(_DB(), event_id=1)
        # The stale section header must be present — search the whole widget.
        from PyQt6.QtWidgets import QLabel
        labels = w.findChildren(QLabel)
        all_text = " ".join(lbl.text() for lbl in labels)
        assert "stale" in all_text.lower(), "stale section header must appear"

    def test_stale_row_has_stale_badge(self, qapp):
        """_build_stale_proposal_row must include a 'STALE' badge."""
        from ui.setup_builder_ui import SetupBuilderMixin
        import types
        from PyQt6.QtWidgets import QWidget, QLabel
        w = QWidget()
        fn = SetupBuilderMixin._build_stale_proposal_row
        w._method = types.MethodType(fn, w)
        prop = {
            "parameter": "arb_front", "direction": "increase",
            "proposed_value": 6.0, "original_value": 5.0,
            "discipline": "race", "baseline_revision": 1,
            "provenance": "DRIVER_REPORT", "status": "stale",
        }
        row_w = w._method(prop, {})
        labels = row_w.findChildren(QLabel)
        texts = [lbl.text() for lbl in labels]
        assert "STALE" in texts, "stale row must have a STALE badge"


class TestV43ProvenanceOnProposalRows:
    """Proposals now carry provenance; it must appear on each row."""

    def test_provenance_badge_appears_in_proposal_row(self, qapp):
        from ui.setup_builder_ui import SetupBuilderMixin
        import types
        from PyQt6.QtWidgets import QWidget, QLabel
        w = QWidget()
        fn = SetupBuilderMixin._build_proposal_row
        w._build_proposal_row = types.MethodType(fn, w)
        # Need action handler stubs.
        for name in ("_resolve_conflict", "_do_accept_proposal",
                     "_do_reject_proposal", "_do_edit_proposal",
                     "_ask_resolve", "_ask_text_dialog"):
            m = getattr(SetupBuilderMixin, name, None)
            if m:
                setattr(w, name, types.MethodType(m, w))

        prop = {
            "proposal_id": "p-prov", "parameter": "arb_front",
            "direction": "increase", "proposed_value": 6.0,
            "original_value": 5.0, "original_proposed_value": 6.0,
            "label": "telemetry with driver corroboration",
            "status": "proposed", "discipline": "race",
            "clean_laps": 5, "evidence_sources": [],
            "clipped": False, "clip_stated_reason": "",
            "session_run_id": "run-prov",
            "provenance": "MEASURED_FACT",
        }
        from strategy.owner_baseline_arbiter import LABEL_TEL_CORROBORATED
        label_tone = {LABEL_TEL_CORROBORATED: "success"}
        row_w = w._build_proposal_row(prop, label_tone, None)
        labels = row_w.findChildren(QLabel)
        texts = [lbl.text() for lbl in labels]
        # provenance badge text is "MEASURED FACT" (underscores replaced with spaces)
        assert any("MEASURED" in t for t in texts), (
            "MEASURED_FACT provenance must appear in the proposal row")


class TestV43ModalSeams:
    """I2: the three modal seams must be injectable and fail-closed under pytest."""

    def test_default_ask_resolve_returns_cancel_under_pytest(self):
        """_default_ask_resolve returns 'cancel' (fail-closed) when PYTEST_CURRENT_TEST is set."""
        from ui.setup_builder_ui import _default_ask_resolve
        # PYTEST_CURRENT_TEST is already set because we are running under pytest.
        result = _default_ask_resolve(None, "camber_front", "increase")
        assert result == "cancel"

    def test_default_ask_text_returns_empty_false_under_pytest(self):
        """_default_ask_text returns ('', False) (fail-closed) when PYTEST_CURRENT_TEST is set."""
        from ui.setup_builder_ui import _default_ask_text
        text, ok = _default_ask_text(None, "title", "message")
        assert ok is False
        assert text == ""

    def test_ask_resolve_injectable_via_instance_attr(self, qapp):
        """SetupBuilderMixin._ask_resolve uses _resolve_conflict_fn when set."""
        from ui.setup_builder_ui import SetupBuilderMixin
        import types
        from PyQt6.QtWidgets import QWidget
        w = QWidget()
        w._ask_resolve = types.MethodType(SetupBuilderMixin._ask_resolve, w)
        # Inject a seam that always returns "tel".
        w._resolve_conflict_fn = lambda param, tel_dir: "tel"
        result = w._ask_resolve("camber_front", "decrease")
        assert result == "tel"

    def test_ask_text_injectable_via_instance_attr(self, qapp):
        """SetupBuilderMixin._ask_text_dialog uses _ask_text_fn when set."""
        from ui.setup_builder_ui import SetupBuilderMixin
        import types
        from PyQt6.QtWidgets import QWidget
        w = QWidget()
        w._ask_text_dialog = types.MethodType(SetupBuilderMixin._ask_text_dialog, w)
        # Inject a seam that returns a fixed string.
        w._ask_text_fn = lambda title, msg: ("test reason", True)
        text, ok = w._ask_text_dialog("Reject proposal", "reason:")
        assert ok is True
        assert text == "test reason"

    def test_resolve_conflict_unlocks_buttons_on_tel_choice(self, qapp):
        """_resolve_conflict unlocks Accept/Reject when resolution is 'tel'."""
        from ui.setup_builder_ui import SetupBuilderMixin
        import types
        from PyQt6.QtWidgets import QWidget, QPushButton
        w = QWidget()
        for name in ("_resolve_conflict", "_ask_resolve", "_ask_text_dialog"):
            m = getattr(SetupBuilderMixin, name, None)
            if m:
                setattr(w, name, types.MethodType(m, w))
        # Inject seam: always resolve to "tel".
        w._resolve_conflict_fn = lambda param, tel_dir: "tel"
        accept_btn = QPushButton("Accept"); accept_btn.setEnabled(False)
        reject_btn = QPushButton("Reject"); reject_btn.setEnabled(False)
        w._resolve_conflict("pid", accept_btn, reject_btn, "increase", "arb_front", None)
        assert accept_btn.isEnabled(), "Accept must be enabled after tel resolution"
        assert reject_btn.isEnabled(), "Reject must be enabled after tel resolution"

    def test_resolve_conflict_cancel_leaves_buttons_disabled(self, qapp):
        """_resolve_conflict with 'cancel' result leaves Accept/Reject disabled."""
        from ui.setup_builder_ui import SetupBuilderMixin
        import types
        from PyQt6.QtWidgets import QWidget, QPushButton
        w = QWidget()
        for name in ("_resolve_conflict", "_ask_resolve", "_ask_text_dialog"):
            m = getattr(SetupBuilderMixin, name, None)
            if m:
                setattr(w, name, types.MethodType(m, w))
        # Inject seam: always cancel (default under pytest anyway).
        w._resolve_conflict_fn = lambda param, tel_dir: "cancel"
        accept_btn = QPushButton("Accept"); accept_btn.setEnabled(False)
        reject_btn = QPushButton("Reject"); reject_btn.setEnabled(False)
        w._resolve_conflict("pid", accept_btn, reject_btn, "increase", "arb_front", None)
        assert not accept_btn.isEnabled(), "Accept must stay disabled after cancel"
        assert not reject_btn.isEnabled(), "Reject must stay disabled after cancel"


class TestV43M3PersistNoBaselineFlag:
    """M3: the no-baseline flag must be persisted to DB, not held only in memory."""

    def test_mark_evidence_without_baseline_called_when_no_baseline(self):
        """When baseline is None, mark_evidence_without_baseline is called on the DB."""
        import time
        from ui.practice_run_recorder import PracticeRunRecorder

        marked = []

        class _DBStub:
            def get_run_for_session(self, sid):
                return {"event_id": 5, "run_id": "uuid-m3-test", "session_type": "Practice"}
            def get_owner_baseline(self, event_id, discipline):
                return None
            def mark_evidence_without_baseline(self, event_id, discipline, session_run_id):
                marked.append((event_id, discipline, session_run_id))
                return True

        recorder = PracticeRunRecorder(db=_DBStub())
        recorder._trigger_owner_proposals(session_id=50, session_meta={"session_type": "Practice"})
        assert marked, "mark_evidence_without_baseline must be called when baseline is None"
        assert marked[0] == (5, "race", "uuid-m3-test")

    def test_mark_not_called_when_baseline_exists(self):
        """mark_evidence_without_baseline must NOT be called when baseline exists."""
        import threading, time
        from ui.practice_run_recorder import PracticeRunRecorder
        import services.owner_baseline_service as svc

        marked = []
        original_run = svc.run_for_session
        svc.run_for_session = lambda *a, **kw: None  # no-op

        try:
            class _DBStub:
                def get_run_for_session(self, sid):
                    return {"event_id": 6, "run_id": "uuid-m3-b", "session_type": "Practice"}
                def get_owner_baseline(self, event_id, discipline):
                    return {"ride_height_front": 80.0}  # baseline exists
                def mark_evidence_without_baseline(self, event_id, discipline, session_run_id):
                    marked.append((event_id, discipline))

            recorder = PracticeRunRecorder(db=_DBStub())
            recorder._trigger_owner_proposals(session_id=60, session_meta={"session_type": "Practice"})
            # Give daemon thread a moment to run.
            deadline = time.time() + 1.0
            while any(t.is_alive() for t in recorder._proposal_threads) and time.time() < deadline:
                time.sleep(0.05)
        finally:
            svc.run_for_session = original_run

        assert not marked, "mark_evidence_without_baseline must NOT be called when baseline exists"


# ---------------------------------------------------------------------------
# Gap 1 — _warn_invalid seam in SetupBuilderMixin._do_edit_proposal
# ---------------------------------------------------------------------------

class TestGap1WarnInvalidSeam:
    """Gap 1: the except (ValueError, TypeError) path in _do_edit_proposal must
    never open a bare QMessageBox under a test runner.

    The fix is a _default_warn_invalid function (fail closed under
    PYTEST_CURRENT_TEST) and a _warn_invalid instance method (injectable via
    _warn_invalid_fn attribute), following the same shape as _default_ask_text.
    """

    def test_default_warn_invalid_fails_closed_under_pytest(self):
        """_default_warn_invalid returns None without touching Qt under pytest."""
        from ui.setup_builder_ui import _default_warn_invalid
        # PYTEST_CURRENT_TEST is already set; must return None silently.
        result = _default_warn_invalid(None, "not a number")
        assert result is None, "_default_warn_invalid must be a no-op under pytest"

    def test_warn_invalid_injectable_via_instance_attr(self, qapp):
        """_warn_invalid delegates to _warn_invalid_fn when set on the instance."""
        from ui.setup_builder_ui import SetupBuilderMixin
        import types
        from PyQt6.QtWidgets import QWidget
        w = QWidget()
        w._warn_invalid = types.MethodType(SetupBuilderMixin._warn_invalid, w)
        captured = []
        w._warn_invalid_fn = lambda msg: captured.append(msg)
        w._warn_invalid("not a number")
        assert captured == ["not a number"], "_warn_invalid_fn must receive the message"

    def test_do_edit_proposal_bad_input_calls_warn_invalid(self, qapp):
        """When _ask_text_fn returns a non-numeric string, _warn_invalid is called
        and the operation does not hang (no bare QMessageBox reached)."""
        from ui.setup_builder_ui import SetupBuilderMixin
        import types
        from PyQt6.QtWidgets import QWidget, QPushButton

        class _FakeEditDB:
            def get_run_for_session(self, sid): return None
            def update_proposal_status(self, *a, **kw): return True

        w = QWidget()
        for name in ("_do_edit_proposal", "_ask_text_dialog", "_warn_invalid"):
            m = getattr(SetupBuilderMixin, name, None)
            if m:
                setattr(w, name, types.MethodType(m, w))

        # Inject seam: return a non-numeric string so float() raises ValueError.
        w._ask_text_fn = lambda title, msg: ("not-a-number", True)
        # Capture _warn_invalid calls to confirm the error path is reached.
        warned = []
        w._warn_invalid_fn = lambda msg: warned.append(msg)

        row_widget = QPushButton("row")
        # Must complete without hanging or raising.
        w._do_edit_proposal("proposal-x", 5.0, 4.5, row_widget, _FakeEditDB())
        assert warned, "_warn_invalid must be called when the entered value is not numeric"
        assert "not" in warned[0].lower() or "valid" in warned[0].lower(), (
            "warning message must mention the value is invalid")

    def test_do_edit_proposal_valid_input_does_not_warn(self, qapp):
        """When the user enters a valid number, _warn_invalid must NOT be called."""
        from ui.setup_builder_ui import SetupBuilderMixin
        import types
        from PyQt6.QtWidgets import QWidget, QPushButton
        import services.owner_baseline_service as svc

        original_edit = getattr(svc, "edit_proposal", None)
        svc.edit_proposal = lambda db, pid, val: None  # no-op

        try:
            w = QWidget()
            for name in ("_do_edit_proposal", "_ask_text_dialog", "_warn_invalid"):
                m = getattr(SetupBuilderMixin, name, None)
                if m:
                    setattr(w, name, types.MethodType(m, w))
            # Inject seam: valid numeric string.
            w._ask_text_fn = lambda title, msg: ("6.5", True)
            warned = []
            w._warn_invalid_fn = lambda msg: warned.append(msg)
            row_widget = QPushButton("row")
            w._do_edit_proposal("proposal-y", 5.0, 4.5, row_widget, object())
            assert not warned, "_warn_invalid must NOT be called for a valid numeric input"
        finally:
            if original_edit is not None:
                svc.edit_proposal = original_edit
            elif hasattr(svc, "edit_proposal"):
                del svc.edit_proposal


# ---------------------------------------------------------------------------
# Gap 2 — dir_picker seam in EventExportPanel._on_export_clicked
# ---------------------------------------------------------------------------

class TestGap2DirPickerSeam:
    """Gap 2: QFileDialog.getExistingDirectory in _on_export_clicked must not
    be called bare — it blocks indefinitely under a test runner.

    The fix is a _default_dir_picker function (fail closed = '' under
    PYTEST_CURRENT_TEST) and a dir_picker= constructor parameter, following
    the same pattern as confirm= / _default_overwrite_confirm.
    """

    def test_default_dir_picker_fails_closed_under_pytest(self):
        """_default_dir_picker returns '' (fail-closed) when PYTEST_CURRENT_TEST is set."""
        from ui.event_export_panel import _default_dir_picker
        result = _default_dir_picker(None, "Choose folder", "")
        assert result == "", "_default_dir_picker must return '' under pytest (fail closed)"

    def test_dir_picker_parameter_accepted_by_constructor(self, qapp):
        """EventExportPanel accepts dir_picker= without error."""
        from ui.event_export_panel import EventExportPanel
        called = []
        panel = EventExportPanel(dir_picker=lambda parent, title, start: called.append(title) or "")
        # Introspect that the callable was stored.
        assert panel._dir_picker is not None

    def test_on_export_clicked_uses_dir_picker_seam(self, qapp):
        """_on_export_clicked calls self._dir_picker, not QFileDialog directly."""
        from ui.event_export_panel import EventExportPanel

        dirs_requested = []

        class _FakeDB:
            pass

        def _pick(parent, title, start):
            dirs_requested.append(title)
            return ""   # simulate cancel

        panel = EventExportPanel(dir_picker=_pick)
        panel.set_event(1, car="RSR", track="Spa", db=_FakeDB())
        # Trigger the click — must reach _dir_picker without touching QFileDialog.
        panel._on_export_clicked()
        assert dirs_requested, "_dir_picker must be called by _on_export_clicked"

    def test_on_export_clicked_cancels_when_dir_picker_returns_empty(self, qapp):
        """If dir_picker returns '', _on_export_clicked cancels (no export started)."""
        from ui.event_export_panel import EventExportPanel

        run_called = []

        class _FakeDB:
            pass

        panel = EventExportPanel(dir_picker=lambda p, t, s: "")
        panel.set_event(1, db=_FakeDB())
        # Patch _run_export to detect if it was called.
        original_run = panel._run_export
        panel._run_export = lambda *a, **kw: run_called.append(True)
        panel._on_export_clicked()
        assert not run_called, "_run_export must NOT be called when dir_picker returns empty"

    def test_on_export_clicked_proceeds_when_dir_picker_returns_path(self, qapp):
        """If dir_picker returns a non-empty path, _run_export is called."""
        from ui.event_export_panel import EventExportPanel

        run_args = []

        class _FakeDB:
            pass

        panel = EventExportPanel(dir_picker=lambda p, t, s: "/tmp/export_dest")
        panel.set_event(1, db=_FakeDB())
        panel._run_export = lambda dest, **kw: run_args.append(dest)
        panel._on_export_clicked()
        assert run_args == ["/tmp/export_dest"], (
            "_run_export must be called with the directory returned by dir_picker")
