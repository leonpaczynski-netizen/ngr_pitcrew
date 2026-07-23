"""UAT round 2 (2026-07-23) on the rebuilt shell — the shell/bridge half.

  V-1 Changed fields listed in an arbitrary order, not GT7's tuning-menu order.
  V-5/7 "Start practice run" navigated away and recorded nothing, so nine laps of
        practice never reached the event programme.
  V-8  The Pit Crew Engineer never changed, because no evidence could ever accumulate.
  V-9  "Apply recommendation" never registered an active setup — the authority read
       called ``active_setup()`` with no arguments (TypeError into a bare except).
  V-10 The Engineering Library opened the classic dashboard window.
"""

import pytest

from PyQt6.QtWidgets import QApplication, QTabWidget, QWidget

from ui.live_shell_bridge import LiveShellBridge, _active_setup
from ui.pit_crew_controller import PitCrewController
from ui.pit_crew_shell import PitCrewShell


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


# --------------------------------------------------------------------------- fakes
def _event_context():
    """A REAL EventContext — the shell chrome reads its full contract."""
    from data.event_context import build_event_context
    return build_event_context(
        event={"name": "GR Enduro Rd2", "track": "Watkins Glen International",
               "layout_id": "long_course"},
        strategy={"car": "Porsche Cayman GT4", "track": "Watkins Glen International"})


class _ActiveSetup:
    def __init__(self, name="Race baseline", revision=2, active=True):
        self.name, self.revision, self._active = name, revision, active

    def label(self):
        return f"{self.name} · rev {self.revision}"

    @property
    def is_active_on_car(self):
        return self._active


class _Authority:
    def __init__(self, per_purpose=None):
        self.per_purpose = per_purpose or {}

    def active_setup(self, identity, purpose="Race"):
        return self.per_purpose.get(purpose)


class _Form:
    def __init__(self, values=None):
        self.values = dict(values or {"body_height_front": 80})

    def current_setup_dict(self):
        return dict(self.values)

    def apply_ai_fields(self, fields):
        self.values.update(fields)


class _Dispatcher:
    _session_id = 7


class _DB:
    def __init__(self):
        self.activities, self.bindings = [], []

    def list_preparation_activities(self, cycle_id):
        return [a for a in self.activities if a.get("cycle_id") == cycle_id]

    def get_preparation_cycle(self, cycle_id):
        return {"cycle_id": cycle_id, "car": "Porsche Cayman GT4",
                "track": "Watkins Glen International"}

    def upsert_preparation_activity(self, row):
        for i, a in enumerate(self.activities):
            if a["activity_id"] == row["activity_id"]:
                self.activities[i] = dict(row)
                return row["activity_id"]
        self.activities.append(dict(row))
        return row["activity_id"]

    def bind_session_to_activity(self, activity_id, session_id, cycle_id="", created_at=""):
        self.bindings.append((activity_id, str(session_id)))
        return True

    def get_session_meta(self, session_id):
        if not session_id:
            return None
        return {"id": session_id, "total_laps": 9, "car_name": "Porsche Cayman GT4",
                "track": "Watkins Glen International"}


class _Win:
    def __init__(self, qapp=None):
        self._race_form = _Form()
        self._qual_form = _Form({"body_height_front": 60})
        self._dispatcher = _Dispatcher()
        self._setup_authority = _Authority({"Race": _ActiveSetup()})
        self.confirmed = []
        # A stand-in classic tab widget so the Library can borrow a real page.
        self._tabs = QTabWidget()
        self._dev_page = QWidget()
        self._tabs.addTab(QWidget(), "Home")
        self._tabs.addTab(self._dev_page, "Development History")

    def _build_event_context(self):
        return _event_context()

    def get_tab_index(self, key):
        return 1 if key == "development_history" else -1

    def _on_changes_applied_in_game(self, form):
        self.confirmed.append(form)


def _cfg():
    return {"active_cycle_id": "c1", "voice": {"enabled": True}}


@pytest.fixture
def wired(qapp):
    ctrl = PitCrewController()
    shell = PitCrewShell(ctrl)
    win = _Win()
    db = _DB()
    bridge = LiveShellBridge(shell, ctrl, window=win, config=_cfg(), db=db)
    return shell, win, db, bridge


def _view(headline="Build setup_base evidence"):
    return {"ok": True, "resolution_state": "one_active_event",
            "event": {"event_name": "GR Enduro Rd2"},
            "next_action": {"headline": headline, "detail": "d", "target_surface": "practice"},
            "attention": [], "readiness": [], "progress": {}, "candidates": [],
            "recent_learning": [], "fingerprint": "fp"}


# --------------------------------------------------------------------------- tests
class TestV1Gt7FieldOrder:
    def test_changed_fields_read_in_gt7_menu_order(self, wired):
        shell, _win, _db, _bridge = wired
        from ui.setup_recommendation_vm import build_recommendation_vm
        # Deliberately supplied out of order (aero before suspension before tyres).
        vm = build_recommendation_vm({"status": "approved", "changes": [
            {"field": "aero_rear", "from": 600, "to": 620, "reason": "r"},
            {"field": "toe_rear", "from": 0.05, "to": 0.10, "reason": "r"},
            {"field": "ride_height_front", "from": 80, "to": 75, "reason": "r"},
            {"field": "arb_front", "from": 5, "to": 4, "reason": "r"},
        ]})
        shell.garage_page.set_recommendation(vm, setup_values={"ride_height_front": 80})
        # Suspension (body height → ARB → toe) comes before aero, exactly as in GT7 —
        # not the order the domain happened to emit them.
        assert shell.garage_page.displayed_fields() == (
            "ride_height_front", "arb_front", "toe_rear", "aero_rear")
        assert shell.garage_page._table.rowCount() == 4

    def test_unknown_fields_sort_last_and_are_never_dropped(self, wired):
        shell, _win, _db, _bridge = wired
        from ui.setup_recommendation_vm import build_recommendation_vm
        vm = build_recommendation_vm({"status": "approved", "changes": [
            {"field": "some_future_field", "from": 1, "to": 2, "reason": "r"},
            {"field": "camber_front", "from": 1.0, "to": 1.4, "reason": "r"},
        ]})
        shell.garage_page.set_recommendation(vm, setup_values={"camber_front": 1.0})
        assert shell.garage_page.displayed_fields() == ("camber_front", "some_future_field")


class TestV9ActiveSetupRegisters:
    def test_authority_is_read_with_the_right_signature(self, wired):
        _shell, win, _db, _bridge = wired
        label, applied = _active_setup(win, "Race")
        assert label == "Race baseline · rev 2"
        assert applied is True

    def test_qualifying_scope_is_separate(self, wired):
        _shell, win, _db, _bridge = wired
        assert _active_setup(win, "Qualifying") == ("", False)

    def test_header_shows_the_active_setup(self, wired):
        shell, _win, _db, bridge = wired
        bridge.refresh()
        assert bridge._controller.state().active_setup_label == "Race baseline · rev 2"

    def test_confirming_in_gt7_routes_to_the_gated_classic_path(self, wired):
        shell, win, _db, _bridge = wired
        shell.garage_page.applied_in_game_confirmed.emit("race")
        assert win.confirmed == [win._race_form]
        assert "active setup" in shell.garage_page._status.text().lower()

    def test_confirming_on_qualifying_targets_the_qualifying_sheet(self, wired):
        shell, win, _db, _bridge = wired
        shell.garage_page._selector._buttons["qualifying"].click()
        shell.garage_page.applied_in_game_confirmed.emit("qualifying")
        assert win.confirmed == [win._qual_form]


class TestV5RunRecording:
    def test_start_opens_a_run_with_the_engineers_objective(self, wired):
        shell, _win, db, bridge = wired
        shell.set_guidance_view(_view())
        bridge._last_guidance_view = _view()
        shell.run_card.start_requested.emit()
        assert len(db.activities) == 1
        assert db.activities[0]["activity_type"] == "baseline_practice"
        assert db.activities[0]["objective"] == "Build setup_base evidence"
        assert shell.current_destination() == "live_pit_wall"

    def test_the_run_card_shows_it_is_recording(self, wired):
        shell, _win, _db, bridge = wired
        bridge._last_guidance_view = _view()
        shell.run_card.start_requested.emit()
        assert shell.run_card.is_recording() is True
        assert "RECORDING" in shell.run_card._recording.text()
        assert "9 laps so far" in shell.run_card._recording.text()

    def test_ending_the_run_binds_the_session(self, wired):
        shell, _win, db, bridge = wired
        bridge._last_guidance_view = _view()
        shell.run_card.start_requested.emit()
        shell.run_card.record_requested.emit()
        assert db.bindings == [("c1::baseline_practice::1", "7")]
        assert db.activities[0]["state"] == "completed"
        assert "Run recorded" in shell.run_card._status.text()
        assert shell.run_card.is_recording() is False

    def test_recording_without_starting_is_refused_with_a_reason(self, wired):
        shell, _win, db, bridge = wired
        shell.run_card.record_requested.emit()
        assert db.bindings == []
        assert "Start practice run" in shell.run_card._status.text()

    def test_discard_records_nothing(self, wired):
        shell, _win, db, bridge = wired
        bridge._last_guidance_view = _view()
        shell.run_card.start_requested.emit()
        shell.run_card.discard_requested.emit()
        assert db.bindings == []
        assert db.activities[0]["state"] == "cancelled"

    def test_no_active_event_reports_instead_of_silently_doing_nothing(self, qapp):
        ctrl = PitCrewController()
        shell = PitCrewShell(ctrl)
        db = _DB()
        bridge = LiveShellBridge(shell, ctrl, window=_Win(), config={}, db=db)
        bridge._last_guidance_view = _view()
        shell.run_card.start_requested.emit()
        assert db.activities == []
        assert "activate" in shell.run_card._status.text().lower()


class TestV10LibraryIsNative:
    def test_opening_an_area_hosts_the_panel_in_the_shell(self, wired):
        shell, win, _db, _bridge = wired
        classic_shown = []
        shell.classic_ui_requested.connect(lambda: classic_shown.append(True))
        shell.library_page.open_requested.emit("knowledge_graph")
        assert classic_shown == []                     # the old window never opens
        assert shell.library_page.showing_detail() is True
        assert shell.library_page._hosted is win._dev_page

    def test_back_returns_the_page_to_the_classic_tabs(self, wired):
        shell, win, _db, _bridge = wired
        shell.library_page.open_requested.emit("certification")
        assert win._tabs.count() == 1                  # borrowed
        shell.library_page._back.click()
        assert win._tabs.count() == 2                  # handed back, same place
        assert win._tabs.widget(1) is win._dev_page
        assert shell.library_page.showing_detail() is False

    def test_a_missing_panel_explains_itself(self, qapp):
        ctrl = PitCrewController()
        shell = PitCrewShell(ctrl)

        class _Bare:
            pass

        LiveShellBridge(shell, ctrl, window=_Bare(), config={}, db=None)
        shell.library_page.open_requested.emit("rule_traces")
        assert shell.library_page.showing_detail() is True
        assert shell.library_page._hosted is None
        assert "not available" in shell.library_page._detail_note.text()


class TestV11EvidenceIsExplained:
    """UAT-3: 'I clicked I entered this in GT7 and it still won't accept my base setup.'

    It DID accept it — the header read "Setup 1 · rev 6 (applied)". But a setup being on
    the car is not evidence FOR it: base_setup readiness comes only from a recorded run.
    The card said "Base Setup has no evidence yet" and its CTA sent the driver back to
    the Garage they were already standing in, so there was no way out of the loop.
    """

    def _evidence_view(self):
        return {"ok": True, "resolution_state": "one_active_event",
                "event": {"event_name": "GR Enduro Rd2"},
                "next_action": {"headline": "Build setup_base evidence",
                                "detail": "setup_base is the weakest domain (confidence: none).",
                                "target_surface": "setup", "tone": "warn"},
                "attention": [{"message": "Base Setup has no evidence yet.", "tone": "warn"}],
                "readiness": [["base_setup", "missing", "no evidence collected"]],
                "progress": {}, "candidates": [], "recent_learning": [], "fingerprint": "fp-ev"}

    def test_the_applied_setup_is_acknowledged(self, wired):
        shell, _win, _db, bridge = wired
        bridge.refresh()
        shell.set_guidance_view(self._evidence_view())
        assert "Setup 1" not in shell.guidance._active_setup.text()  # fake is "Race baseline"
        assert shell.guidance._active_setup.text() == "✓ On the car: Race baseline · rev 2 (applied)"
        assert shell.guidance._active_setup.isVisibleTo(shell.guidance) is True

    def test_the_card_says_what_actually_builds_the_evidence(self, wired):
        shell, _win, _db, bridge = wired
        bridge.refresh()
        shell.set_guidance_view(self._evidence_view())
        msg = shell.guidance._message.text()
        assert "is on the car" in msg
        assert "baseline run" in msg
        assert "End run & record" in msg

    def test_the_cta_leads_to_the_run_not_back_to_the_garage(self, wired):
        shell, _win, _db, bridge = wired
        bridge.refresh()
        shell.set_guidance_view(self._evidence_view())
        assert shell.guidance._primary.text() == "Start a baseline run"
        shell.guidance._primary.click()
        assert shell.current_destination() == "practice"

    def test_warning_is_restated_in_the_drivers_terms(self, wired):
        shell, _win, _db, _bridge = wired
        shell.set_guidance_view(self._evidence_view())
        assert "no recorded runs yet" in shell.guidance._warnings.text()
        assert "no evidence yet" not in shell.guidance._warnings.text()

    def test_without_a_setup_it_says_apply_one_first(self, qapp):
        from ui.components.guidance_vm import EngineerGuidanceVM
        vm = EngineerGuidanceVM.from_command_centre(self._evidence_view())
        assert "Apply a setup" in vm.message
        assert vm.active_setup == ""

    def test_readiness_note_no_longer_reads_as_a_rejection(self, wired):
        shell, _win, _db, _bridge = wired
        shell.set_guidance_view(self._evidence_view())
        row = shell.home_page._readiness_box.itemAt(0).widget()
        texts = [row.layout().itemAt(i).widget().text() for i in range(row.layout().count())]
        assert "No runs yet" in texts
        assert "no runs recorded for this yet" in texts

    def test_a_non_evidence_objective_keeps_its_own_routing(self, wired):
        shell, _win, _db, _bridge = wired
        view = self._evidence_view()
        view["next_action"] = {"headline": "Approve the race strategy", "detail": "d",
                               "target_surface": "strategy", "tone": "info"}
        view["fingerprint"] = "fp-other"
        shell.set_guidance_view(view)
        assert shell.guidance._primary.text() == "Approve the race strategy"
        shell.guidance._primary.click()
        assert shell.current_destination() == "race_strategy"


class TestV11GarageExplainsValidation:
    def test_the_validation_pill_names_what_is_missing(self, wired):
        shell, _win, _db, bridge = wired
        bridge.refresh()
        pill = shell.garage_page._pill_valid
        assert pill.text().strip().endswith("No run recorded yet")
        assert "recording the run" in pill.toolTip()


class TestV12ReviewShowsTheRun:
    """UAT-4: 'I recorded practice — nothing shows me my lap times or fuel per lap',
    and 'submitting feedback takes me to a blank outcome screen'."""

    @staticmethod
    def _laps(*times, fuel=3.0):
        return [{"lap_num": i, "lap_time_ms": t, "fuel_used": fuel, "compound": "RM"}
                for i, t in enumerate(times, 1)]

    def _with_laps(self, wired, *times):
        shell, _win, db, bridge = wired
        db.get_session_laps = lambda sid: self._laps(*times)
        bridge._review_cache.clear()
        return shell, db, bridge

    def test_the_review_tab_lists_the_recorded_laps(self, wired):
        shell, _db, bridge = self._with_laps(wired, 92500, 92100, 92800)
        bridge.refresh()
        table = shell.run_laps._table
        assert table.rowCount() == 3
        assert table.item(1, 1).text() == "1:32.100"          # best lap
        assert table.item(0, 3).text() == "3.00 L"            # fuel per lap
        assert shell.run_laps._empty.isVisibleTo(shell.run_laps) is False

    def test_the_summary_gives_pace_and_fuel(self, wired):
        shell, _db, bridge = self._with_laps(wired, 92500, 92100, 92800)
        bridge.refresh()
        summary = shell.run_laps._summary.text()
        assert "Best 1:32.100" in summary
        assert "3.00 L/lap" in summary
        assert "per tank" in summary

    def test_with_no_run_it_explains_how_to_get_one(self, wired):
        shell, _win, db, bridge = wired
        db.get_session_laps = lambda sid: []
        bridge._review_cache.clear()
        bridge.refresh()
        assert shell.run_laps._table.isVisibleTo(shell.run_laps) is False
        assert "End run & record" in shell.run_laps._empty.text()

    def test_submitting_feedback_produces_a_real_outcome(self, wired):
        shell, _db, _bridge = self._with_laps(wired, 92500, 92100, 92800)
        shell.feedback_form.submitted.emit({"overall": "better", "traction": "Excellent"})
        out = shell.practice_outcome
        assert out._vm.has_outcome is True
        assert out._empty.isVisibleTo(out) is False
        assert "first recorded run" in out._vm.verdict_summary
        assert any("Best lap" in f for f in out._vm.telemetry_findings)
        assert "traction: Excellent" in out._vm.feedback_summary

    def test_the_outcome_compares_against_the_previous_recorded_run(self, wired):
        shell, _win, db, bridge = wired
        fast, slow = self._laps(92500, 92100, 92800), self._laps(93500, 93600, 93400)
        db.get_session_laps = lambda sid: fast if sid == 7 else slow
        bridge._review_cache.clear()
        bridge._previous_recorded_session_id = 4
        shell.feedback_form.submitted.emit({"overall": "better"})
        assert shell.practice_outcome._vm.verdict == "improved"
        assert shell.practice_outcome._vm.primary_action_key == "keep"
        assert shell.practice_outcome._vm.agreements

    def test_recording_a_run_points_the_driver_at_the_review(self, wired):
        shell, _win, _db, bridge = wired
        bridge._last_guidance_view = _view()
        shell.run_card.start_requested.emit()
        shell.run_card.record_requested.emit()
        assert "Open Review" in shell.run_card._status.text()
        assert bridge._last_recorded_session_id == 7


class TestV13TyreCompoundControl:
    """UAT-4: 'still can't see a way to change my tyres from medium to hard for the
    2 hour endurance race.' The Garage had no tyre control at all."""

    def test_the_garage_offers_the_events_allowed_compounds(self, wired):
        shell, _win, _db, bridge = wired
        bridge.refresh()
        combo = shell.garage_page._tyre
        assert combo.count() >= 2
        assert shell.garage_page._tyre_codes  # populated from the event regulations

    def test_the_current_compound_is_preselected(self, wired):
        shell, win, _db, bridge = wired
        win._race_form.values.update({"tyre_front": "Racing Medium",
                                      "tyre_rear": "Racing Medium"})
        bridge.refresh()
        idx = shell.garage_page._tyre.currentIndex()
        assert shell.garage_page._tyre_codes[idx] == "RM"

    def test_choosing_hard_writes_both_axles_to_the_sheet(self, wired):
        shell, win, _db, bridge = wired
        bridge.refresh()
        codes = list(shell.garage_page._tyre_codes)
        shell.garage_page._tyre.setCurrentIndex(codes.index("RH"))
        shell.garage_page._tyre.activated.emit(codes.index("RH"))
        assert win._race_form.values["tyre_front"] == "Racing Hard"
        assert win._race_form.values["tyre_rear"] == "Racing Hard"
        assert "Racing Hard" in shell.garage_page._status.text()
        assert "entered this in GT7" in shell.garage_page._status.text()

    def test_the_qualifying_sheet_is_the_one_changed_on_that_tab(self, wired):
        shell, win, _db, bridge = wired
        shell.garage_page._selector._buttons["qualifying"].click()
        codes = list(shell.garage_page._tyre_codes)
        shell.garage_page._tyre.activated.emit(codes.index("RS"))
        assert win._qual_form.values["tyre_front"] == "Racing Soft"
        assert "tyre_front" not in win._race_form.values

    def test_qualifying_names_the_softest_allowed(self, wired):
        shell, _win, _db, bridge = wired
        shell.garage_page._selector._buttons["qualifying"].click()
        note = shell.garage_page._tyre_note.text()
        assert "Racing Soft" in note

    def test_race_explains_that_compounds_must_be_compared(self, wired):
        shell, _win, _db, bridge = wired
        bridge.refresh()
        assert "recorded runs settle" in shell.garage_page._tyre_note.text()
