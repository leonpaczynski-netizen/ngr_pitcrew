"""UAT round 2 (2026-07-23) on the rebuilt shell — the shell/bridge half.

  V-1 Changed fields listed in an arbitrary order, not GT7's tuning-menu order.
  V-5/7 "Start practice run" navigated away and recorded nothing, so nine laps of
        practice never reached the event programme.
  V-8  The Pit Crew Engineer never changed, because no evidence could ever accumulate.
  V-9  "Apply recommendation" never registered an active setup — the authority read
       called ``active_setup()`` with no arguments (TypeError into a bare except).
  V-10 The Engineering Library opened the classic dashboard window.
"""

import json

import pytest

from PyQt6.QtWidgets import QApplication, QTabWidget, QWidget

from strategy.run_brief import brief_for_domain as _brief
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


class _ResultBox:
    """Stands in for the classic Setup Builder's result box."""

    def __init__(self, text=""):
        self.text = text

    def toPlainText(self):
        return self.text


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

    def get_practice_sessions_for_cycle(self, cycle_id):
        by_id = {a["activity_id"]: a for a in self.activities}
        return [{"session_id": sid, "activity_id": aid,
                 "activity_type": (by_id.get(aid) or {}).get("activity_type", ""),
                 "total_laps": 9, "track": "", "car_name": ""}
                for aid, sid in self.bindings]


class _Win:
    def __init__(self, qapp=None):
        self._race_form = _Form()
        self._qual_form = _Form({"body_height_front": 60})
        self._dispatcher = _Dispatcher()
        self._setup_authority = _Authority({"Race": _ActiveSetup()})
        self._driving_advisor = _Advisor()
        self._setup_result_text = _ResultBox()
        self.confirmed = []
        self.analysed = []
        self.baseline_built = 0
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

    def _setup_analyse_ai(self):
        self.analysed.append("race")

    def _setup_analyse_ai_for_form(self, form):
        self.analysed.append("qualifying" if form is self._qual_form else "other")

    def _generate_baseline_setup_both(self):
        self.baseline_built += 1


BASELINE_JSON = json.dumps({"setup_fields": {"arb_front": 6, "arb_rear": 5,
                                             "springs_front": 3.4}})
RECOMMENDATION_JSON = json.dumps({
    "analysis": "Front washes out on entry.",
    "changes": [{"field": "arb_front", "from": 6, "to": 5, "reason": "reduce understeer"}],
    "setup_fields": {"arb_front": 5}, "recommendation_status": "approved"})
NO_CHANGE_JSON = json.dumps({"analysis": "Inside its window.", "changes": [],
                             "setup_fields": {}, "recommendation_status": "approved"})


class _Advisor:
    """Stands in for DrivingAdvisor — both entry points return a JSON string."""

    def __init__(self, baseline=BASELINE_JSON, combined=NO_CHANGE_JSON):
        self.baseline, self.combined = baseline, combined
        self.analysed = []

    def build_baseline_setup_response(self, **kw):
        if isinstance(self.baseline, Exception):
            raise self.baseline
        return self.baseline

    def build_combined_setup_response(self, setup, **kw):
        self.analysed.append(kw.get("purpose"))
        if isinstance(self.combined, Exception):
            raise self.combined
        return self.combined


def _cfg():
    return {"active_cycle_id": "c1", "voice": {"enabled": True},
            "strategy": {"car": "Porsche Cayman GT4",
                         "track": "Watkins Glen International",
                         # A real event has a length; without one the plan is
                         # legitimately refused.
                         "race_type": "lap", "laps": 25}}


@pytest.fixture
def wired(qapp):
    ctrl = PitCrewController()
    shell = PitCrewShell(ctrl)
    win = _Win()
    db = _DB()
    # Workers run INLINE: a real thread emitting into a QObject under teardown aborts
    # the process, and inline keeps the assertions deterministic.
    bridge = LiveShellBridge(shell, ctrl, window=win, config=_cfg(), db=db,
                             spawn=lambda fn: fn())
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

    def test_confirming_in_gt7_marks_the_setup_active(self, wired):
        """The confirmation now goes straight to the setup authority — the ONLY thing
        that can make a setup active, because only the driver can change GT7."""
        shell, win, _db, bridge = wired
        recorded = []
        win._setup_authority.mark_applied = lambda ident, **kw: (
            recorded.append(kw["purpose"]) or _ActiveSetup())
        shell.garage_page._baseline.click()          # author a sheet to confirm
        shell.garage_page.applied_in_game_confirmed.emit("race")
        assert recorded == ["Race"]
        # The driver is told which setup is now on the car. Whether that reads as
        # "registered as the active setup" or "already on the car" depends on whether
        # the sheet actually changed — see TestV20 for that distinction.
        status = shell.garage_page._status.text().lower()
        assert "race baseline · rev 2" in status
        assert "active setup" in status or "on the car" in status

    def test_confirming_on_qualifying_is_a_separate_scope(self, wired):
        shell, win, _db, _bridge = wired
        recorded = []
        win._setup_authority.mark_applied = lambda ident, **kw: (
            recorded.append(kw["purpose"]) or _ActiveSetup())
        shell.garage_page._baseline.click()
        shell.garage_page._selector._buttons["qualifying"].click()
        shell.garage_page.applied_in_game_confirmed.emit("qualifying")
        assert recorded == ["Qualifying"]

    def test_an_empty_sheet_cannot_be_confirmed(self, wired):
        shell, _win, _db, _bridge = wired
        shell.garage_page.applied_in_game_confirmed.emit("race")
        assert "no setup on it" in shell.garage_page._status.text()


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
        shell, _win, _db, bridge = wired
        shell.garage_page._baseline.click()      # a sheet must exist to be shown
        bridge._setups.apply("race", {"tyre_front": "Racing Medium",
                                      "tyre_rear": "Racing Medium"})
        bridge.refresh()
        idx = shell.garage_page._tyre.currentIndex()
        assert shell.garage_page._tyre_codes[idx] == "RM"

    def test_choosing_hard_writes_both_axles_to_the_sheet(self, wired):
        shell, _win, _db, bridge = wired
        bridge.refresh()
        codes = list(shell.garage_page._tyre_codes)
        shell.garage_page._tyre.setCurrentIndex(codes.index("RH"))
        shell.garage_page._tyre.activated.emit(codes.index("RH"))
        sheet = bridge._setups.sheet("race")
        assert sheet.get("tyre_front") == "Racing Hard"
        assert sheet.get("tyre_rear") == "Racing Hard"
        assert "Racing Hard" in shell.garage_page._status.text()
        assert "entered this in GT7" in shell.garage_page._status.text()

    def test_the_qualifying_sheet_is_the_one_changed_on_that_tab(self, wired):
        shell, _win, _db, bridge = wired
        shell.garage_page._selector._buttons["qualifying"].click()
        codes = list(shell.garage_page._tyre_codes)
        shell.garage_page._tyre.activated.emit(codes.index("RS"))
        assert bridge._setups.sheet("qualifying").get("tyre_front") == "Racing Soft"
        assert bridge._setups.sheet("race").get("tyre_front") != "Racing Soft"

    def test_qualifying_names_the_softest_allowed(self, wired):
        shell, _win, _db, bridge = wired
        shell.garage_page._selector._buttons["qualifying"].click()
        note = shell.garage_page._tyre_note.text()
        assert "Racing Soft" in note

    def test_race_explains_that_compounds_must_be_compared(self, wired):
        shell, _win, _db, bridge = wired
        bridge.refresh()
        assert "recorded runs settle" in shell.garage_page._tyre_note.text()


class TestV14GarageFlowOrder:
    """UAT-5: drop the Base tab (there is no third sheet); the bottom-left action is
    "Build initial setup"; Analyse is the NEXT step, once a run has been recorded."""

    def test_only_the_two_real_sheets_are_offered(self, wired):
        shell, _win, _db, _bridge = wired
        assert [k for k, _ in
                __import__("ui.components.setup_workspace", fromlist=["x"]).DISCIPLINES] \
            == ["race", "qualifying"]
        assert set(shell.garage_page._selector._buttons) == {"race", "qualifying"}

    def test_analyse_is_locked_until_a_run_is_recorded(self, wired):
        shell, _win, db, bridge = wired
        db.get_practice_sessions_for_cycle = lambda cid: []
        bridge.refresh()
        assert shell.garage_page._analyse.isEnabled() is False
        assert "recorded a practice run" in shell.garage_page._analyse.toolTip()

    def test_analyse_unlocks_once_a_run_exists(self, wired):
        shell, _win, db, bridge = wired
        db.get_practice_sessions_for_cycle = lambda cid: [{"session_id": "7"}]
        bridge.refresh()
        assert shell.garage_page._analyse.isEnabled() is True
        assert shell.garage_page._analyse.toolTip() == ""

    def test_with_no_setup_the_empty_state_points_at_build(self, wired):
        shell, win, db, bridge = wired
        db.get_practice_sessions_for_cycle = lambda cid: []
        win._race_form.values = {}
        bridge.refresh()
        assert "Build initial setup" in shell.garage_page._empty.text()

    def test_the_build_button_reflects_whether_a_setup_exists(self, wired):
        shell, _win, _db, bridge = wired
        bridge.refresh()
        assert shell.garage_page._baseline.text() == "Build initial setup"
        shell.garage_page._baseline.click()          # authors both sheets
        bridge.refresh()
        assert shell.garage_page._baseline.text() == "Rebuild initial setup"


class TestV15AnalyseAlwaysSettles:
    """UAT-5: 'clicking analyse setup just sits on this, nothing is returned.' The
    classic path reported into a QTextEdit, so a run that finished with no proposed
    change and a run that failed both looked exactly like a run still going. Every
    outcome is now a result object, and every one of them is reported."""

    def _built(self, wired):
        shell, win, _db, bridge = wired
        shell.garage_page._baseline.click()     # a sheet to analyse
        return shell, win, bridge

    def test_finishing_with_no_change_is_reported_as_a_result(self, wired):
        shell, win, bridge = self._built(wired)
        win._driving_advisor.combined = NO_CHANGE_JSON
        shell.garage_page.analyse_requested.emit()
        assert "No change recommended" in shell.garage_page._status.text()
        assert bridge._pending_work == ""

    def test_a_failed_analysis_surfaces_its_error(self, wired):
        shell, win, bridge = self._built(wired)
        win._driving_advisor.combined = RuntimeError("no telemetry baseline")
        shell.garage_page.analyse_requested.emit()
        assert "no telemetry baseline" in shell.garage_page._status.text()
        assert bridge._pending_work == ""

    def test_an_unreadable_reply_is_never_shown_raw(self, wired):
        shell, win, bridge = self._built(wired)
        win._driving_advisor.combined = '{"analysis": "truncated mid'
        shell.garage_page.analyse_requested.emit()
        assert "incomplete" in shell.garage_page._status.text()

    def test_a_real_recommendation_is_reported_and_rendered(self, wired):
        shell, win, bridge = self._built(wired)
        win._driving_advisor.combined = RECOMMENDATION_JSON
        shell.garage_page.analyse_requested.emit()
        assert "1 change recommended." in shell.garage_page._status.text()
        assert shell.garage_page.displayed_fields() == ("arb_front",)

    def test_a_race_recommendation_never_renders_under_qualifying(self, wired):
        shell, win, bridge = self._built(wired)
        win._driving_advisor.combined = RECOMMENDATION_JSON
        shell.garage_page.analyse_requested.emit()
        assert shell.garage_page.displayed_fields() == ("arb_front",)
        shell.garage_page._selector._buttons["qualifying"].click()
        assert shell.garage_page.displayed_fields() == ()

    def test_analysing_an_empty_sheet_explains_the_order_of_work(self, wired):
        shell, _win, _db, _bridge = wired
        shell.garage_page.analyse_requested.emit()
        assert "build the initial setup first" in shell.garage_page._status.text()


class TestV16InitialSetupConfirmsBothSheets:
    """UAT-5: 'not convinced qualifying is getting a setup.' The engine reports each
    sheet individually, so one that did not build is never implied to have built."""

    def test_both_sheets_are_confirmed_when_both_build(self, wired):
        shell, _win, _db, bridge = wired
        shell.garage_page._baseline.click()
        status = shell.garage_page._status.text()
        assert "Race sheet ✓" in status and "Qualifying sheet ✓" in status
        assert bridge._setups.sheet("race").is_authored is True
        assert bridge._setups.sheet("qualifying").is_authored is True
        assert bridge._pending_work == ""

    def test_a_qualifying_sheet_that_never_lands_is_not_claimed(self, wired):
        shell, win, _db, bridge = wired
        calls = {"n": 0}

        def _only_race(**kw):
            calls["n"] += 1
            return BASELINE_JSON if kw["session_type"].startswith("Race") else "{}"

        win._driving_advisor.build_baseline_setup_response = _only_race
        shell.garage_page._baseline.click()
        status = shell.garage_page._status.text()
        assert "Race sheet built" in status or "Race sheet ✓" in status
        assert "Qualifying sheet ✓" not in status
        assert bridge._setups.sheet("qualifying").is_authored is False

    def test_the_classic_form_is_kept_in_step_while_it_still_exists(self, wired):
        """Transitional, removed in stage 6."""
        shell, win, _db, _bridge = wired
        shell.garage_page._baseline.click()
        assert win._race_form.values["arb_front"] == 6.0
        assert win._qual_form.values["arb_front"] == 6.0


class TestV17CoachingRunIsStartable:
    """UAT-5: 'clicking start a coaching run takes me to an empty practice page.' With
    no setup recommendation to validate the run card was blank, so nothing could be
    started — but the engineer's objective IS a run plan."""

    def _coaching_view(self):
        v = _view("Build driver_coaching evidence")
        v["next_action"]["detail"] = "driver_coaching is the weakest domain."
        return v

    def test_the_objective_becomes_the_run_plan(self, wired):
        shell, _win, _db, bridge = wired
        bridge._last_guidance_view = self._coaching_view()
        bridge.refresh()
        vm = shell.run_card._vm
        assert vm.has_plan is True
        # The card is now written from the coaching BRIEF rather than the domain's
        # machine name, so it reads as a run the driver can actually go and do.
        assert "coaching run" in vm.objective.lower()
        assert vm.purpose == "coaching"
        assert vm.how_to_drive and vm.reports
        assert shell.run_card._start.isVisibleTo(shell.run_card) is True

    def test_a_long_run_objective_asks_for_more_laps(self, wired):
        shell, _win, _db, bridge = wired
        bridge._last_guidance_view = _view("Build setup_race evidence")
        bridge.refresh()
        # A race run is a full stint on race fuel — not a fixed lap count, and
        # emphatically not the same short run a coaching lap-set asks for.
        assert shell.run_card._vm.target_laps == "A full stint"
        assert "full" in shell.run_card._vm.fuel.lower()
        assert (shell.run_card._vm.target_laps
                != _brief("driver_coaching").target_laps)

    def test_that_run_can_actually_be_started(self, wired):
        shell, _win, db, bridge = wired
        bridge._last_guidance_view = self._coaching_view()
        bridge.refresh()
        shell.run_card.start_requested.emit()
        assert len(db.activities) == 1
        assert db.activities[0]["activity_type"] == "coaching_run"

    def test_no_objective_still_says_so_rather_than_showing_a_fake_plan(self, wired):
        shell, _win, _db, bridge = wired
        bridge._last_guidance_view = {"ok": True, "next_action": {}}
        bridge.refresh()
        assert shell.run_card._vm.has_plan is False
        assert shell.run_card._empty.isVisibleTo(shell.run_card) is True



class TestV18RaceStrategyCanBuildItsOwnPlan:
    """The strategy page could only DISPLAY a plan the classic tab had built, so in the
    new shell it stayed empty forever with no way to fill it."""

    def test_the_page_offers_building_before_approving(self, wired):
        shell, _win, _db, bridge = wired
        bridge.refresh()
        page = shell.strategy_page
        assert page._build.text() == "Build the race plan"
        # Approving a plan that does not exist is meaningless — one primary at a time.
        assert page._approve.isVisibleTo(page) is False

    def test_building_with_no_recorded_run_says_how_to_get_one(self, wired):
        shell, _win, _db, _bridge = wired
        shell.strategy_page.build_requested.emit()
        assert "End run & record" in shell.strategy_page._status.text()

    def test_a_built_plan_reaches_the_page_and_enables_approving(self, wired, monkeypatch):
        shell, _win, db, bridge = wired
        db.get_practice_sessions_for_cycle = lambda cid: [
            {"session_id": "7", "total_laps": 9}]
        monkeypatch.setattr(
            "strategy.race_strategy_pipeline.recommend_strategy_from_session",
            lambda _db, **kw: {"raw": True})
        monkeypatch.setattr(
            "ui.race_strategy_vm.build_race_plan_view_model",
            lambda r: _PlanVM())
        shell.strategy_page.build_requested.emit()
        assert "Race plan built from session 7" in shell.strategy_page._status.text()
        assert bridge._plans.last_plan.ok is True
        bridge.refresh()
        assert shell.strategy_page._approve.isVisibleTo(shell.strategy_page) is True

    def test_the_plan_is_built_from_the_recorded_run(self, wired, monkeypatch):
        shell, _win, db, bridge = wired
        db.get_practice_sessions_for_cycle = lambda cid: [
            {"session_id": "4", "total_laps": 9}, {"session_id": "7", "total_laps": 9}]
        seen = {}
        monkeypatch.setattr(
            "strategy.race_strategy_pipeline.recommend_strategy_from_session",
            lambda _db, **kw: seen.update(kw) or {"raw": True})
        monkeypatch.setattr("ui.race_strategy_vm.build_race_plan_view_model",
                            lambda r: _PlanVM())
        shell.strategy_page.build_requested.emit()
        assert seen["session_id"] == 7          # most recently recorded


class TestV20ReconfirmingAnUnchangedSetup:
    """UAT-6: "even when setup isn't changed if I click I have entered this in GT7 to
    activate current setup it saves it as a new setup"."""

    def test_the_driver_is_told_it_is_unchanged_rather_than_newly_saved(self, wired):
        shell, _win, _db, bridge = wired
        seen = []

        class _Auth:
            def active_setup(self, _i, _p="Race"):
                return _ActiveSetup(revision=4) if seen else None

            def mark_applied(self, _i, **kw):
                seen.append(kw["purpose"])
                return _ActiveSetup(revision=4)

        bridge._setups._authority = _Auth()
        shell.garage_page._baseline.click()
        shell.garage_page.applied_in_game_confirmed.emit("race")   # first: new
        assert "active setup" in shell.garage_page._status.text().lower()
        shell.garage_page.applied_in_game_confirmed.emit("race")   # again: unchanged
        status = shell.garage_page._status.text().lower()
        assert "already on the car" in status
        assert "rev 4" in status and "rev 5" not in status


class TestV21GatherMoreDataDoesSomething:
    """UAT-6: "practice outcome what does gather more data do? - not much on this page".

    It navigated to Practice — the page the driver was already standing on.
    """

    def _after_a_coaching_run(self, shell, bridge):
        v = _view("Build driver_coaching evidence")
        bridge._last_guidance_view = v
        bridge.refresh()
        shell.run_card.start_requested.emit()
        shell.run_card.record_requested.emit()
        bridge.refresh()

    def test_it_opens_another_run_of_the_same_kind(self, wired):
        shell, _win, db, bridge = wired
        self._after_a_coaching_run(shell, bridge)
        assert [a["activity_type"] for a in db.activities] == ["coaching_run"]

        shell.practice_outcome.action_requested.emit("gather")
        # A SECOND coaching run is open — the repeat the inconclusive verdict asked for.
        assert [a["activity_type"] for a in db.activities] == ["coaching_run", "coaching_run"]
        assert db.activities[-1]["state"] == "in_progress"

    def test_it_puts_the_driver_on_the_run_card(self, wired):
        shell, _win, _db, bridge = wired
        self._after_a_coaching_run(shell, bridge)
        shell._practice_stack.setCurrentIndex(2)
        shell.practice_outcome.action_requested.emit("gather")
        assert shell.current_destination() == "practice"
        assert shell._practice_stack.currentIndex() == 0
        assert "coaching run" in shell.run_card._status.text().lower()

    def test_it_never_opens_a_second_run_on_top_of_an_open_one(self, wired):
        shell, _win, db, bridge = wired
        v = _view("Build driver_coaching evidence")
        bridge._last_guidance_view = v
        bridge.refresh()
        shell.run_card.start_requested.emit()          # a run is already open
        shell.practice_outcome.action_requested.emit("gather")
        assert len(db.activities) == 1
        assert "already open" in shell.run_card._status.text().lower()


class TestV22TheComparisonSurvivesARestart:
    """UAT-6 (seen in the outcome screenshot): every launch reported the newest run as
    "the first recorded run for this setup" — the pair lived in two in-memory ints."""

    def test_the_recorded_pair_comes_from_the_programme(self, wired):
        shell, win, db, bridge = wired
        bridge._last_guidance_view = _view("Build consistency evidence")
        bridge.refresh()
        for sid in (4, 7):
            win._dispatcher._session_id = sid
            shell.run_card.start_requested.emit()
            shell.run_card.record_requested.emit()
        win._dispatcher._session_id = 0
        bridge.refresh()
        assert bridge._recorded_pair() == (7, 4)

    def test_a_fresh_bridge_still_finds_both_runs(self, wired, qapp):
        shell, win, db, bridge = wired
        bridge._last_guidance_view = _view("Build consistency evidence")
        bridge.refresh()
        for sid in (4, 7):
            win._dispatcher._session_id = sid
            shell.run_card.start_requested.emit()
            shell.run_card.record_requested.emit()
        win._dispatcher._session_id = 0

        # A brand-new bridge over the same DB — the restart case. Nothing is carried
        # over in memory, so this is the pair the programme itself knows about.
        ctrl2 = PitCrewController()
        shell2 = PitCrewShell(ctrl2)
        fresh = LiveShellBridge(shell2, ctrl2, window=win, config=_cfg(), db=db,
                                spawn=lambda fn: fn())
        fresh.refresh()
        assert fresh._recorded_pair() == (7, 4)

    def test_the_review_names_the_kind_of_run_it_is_showing(self, wired):
        shell, win, _db, bridge = wired
        bridge._last_guidance_view = _view("Build tyre_model evidence")
        bridge.refresh()
        shell.run_card.start_requested.emit()
        shell.run_card.record_requested.emit()
        win._dispatcher._session_id = 0
        bridge.refresh()
        assert "tyre test" in shell.run_laps._kind.text().lower()


class TestV23ShiftBeepLivesWithTheSetup:
    """UAT-6: "shift beep is in settings but should be in garage as part of the car
    setup … depending on which setup is loaded and what session I am doing that beep
    indicator should be active." The RPM now travels with each discipline's sheet and
    projects into the config the beep loop already reads."""

    def test_editing_the_garage_rpm_writes_the_sheet_and_projects_to_config(self, wired):
        shell, win, _db, bridge = wired
        win.config_path = ""                      # keep _persist_config a no-op in tests
        bridge.refresh()
        shell.garage_page._shift_rpm.setValue(7000)
        shell.garage_page._on_shift_rpm_edited()
        assert bridge._setups.shift_rpm("race") == 7000
        # resolve_threshold reads race_rpm/qual_rpm from config; the beep follows the sheet.
        assert int(bridge._config["shift_beep"]["race_rpm"]) == 7000

    def test_race_and_qualifying_keep_separate_points(self, wired):
        shell, win, _db, bridge = wired
        win.config_path = ""
        bridge.refresh()
        shell.garage_page._shift_rpm.setValue(7000)
        shell.garage_page._on_shift_rpm_edited()
        shell.garage_page._selector._buttons["qualifying"].click()
        shell.garage_page._shift_rpm.setValue(7600)
        shell.garage_page._on_shift_rpm_edited()
        assert bridge._setups.shift_rpm("race") == 7000
        assert bridge._setups.shift_rpm("qualifying") == 7600
        assert int(bridge._config["shift_beep"]["race_rpm"]) == 7000
        assert int(bridge._config["shift_beep"]["qual_rpm"]) == 7600

    def test_the_beep_threshold_follows_the_session(self, wired):
        """The end-to-end contract: which sheet's RPM the live beep uses is decided by
        the session, via the unchanged resolve_threshold."""
        from main import resolve_threshold
        shell, win, _db, bridge = wired
        win.config_path = ""
        bridge.refresh()
        shell.garage_page._shift_rpm.setValue(7000)
        shell.garage_page._on_shift_rpm_edited()
        shell.garage_page._selector._buttons["qualifying"].click()
        shell.garage_page._shift_rpm.setValue(7600)
        shell.garage_page._on_shift_rpm_edited()
        sb = bridge._config["shift_beep"]
        _k, race = resolve_threshold("Race", True, False, sb)
        _k, qual = resolve_threshold("Qualifying", False, False, sb)
        assert race == 7000 and qual == 7600

    def test_the_garage_shows_the_saved_config_value_until_a_sheet_has_one(self, wired):
        shell, win, _db, bridge = wired
        bridge._config.setdefault("shift_beep", {})["race_rpm"] = 6800
        win.config_path = ""
        bridge.refresh()
        # No sheet value yet → the driver's existing saved RPM is shown, not blank.
        assert shell.garage_page._shift_rpm.value() == 6800

    def test_recommend_fills_both_sheets_from_the_car(self, wired):
        shell, win, _db, bridge = wired
        win.config_path = ""
        win._last_packet = type("P", (), {"rpm_alert_max": 7500})()
        bridge.refresh()
        shell.garage_page.shift_rpm_recommend_requested.emit()
        assert bridge._setups.shift_rpm("qualifying") == 7500
        # Race is a touch below the qualifying point for engine/fuel margin.
        assert 0 < bridge._setups.shift_rpm("race") <= 7500

    def test_recommend_with_no_car_data_asks_the_driver_to_drive(self, wired):
        shell, win, _db, bridge = wired
        win.config_path = ""
        win._last_packet = None
        bridge.refresh()
        shell.garage_page.shift_rpm_recommend_requested.emit()
        assert bridge._setups.shift_rpm("race") == 0     # nothing fabricated
        assert "no usable car data" in shell.garage_page._status.text().lower()


class TestV24ProgrammeMapShowsWhereYouAre:
    """UAT-6: "I feel like we are going in circles now." Nothing showed how many runs
    each evidence area needs or how many remain, so every screen looked identical after
    every run. The Programme page turns the readiness the CC already produces into a map."""

    def _view_with_readiness(self):
        v = _view("Build driver_coaching evidence")
        v["readiness"] = [
            ["base_setup", "developing", "2 exact / 0 labelled sample(s)"],
            ["driver_coaching", "developing", "2 exact / 0 labelled sample(s)"],
            ["race_pace", "adequate", "3 exact / 0 labelled sample(s)"],
            ["consistency", "strong", "5 exact / 0 labelled sample(s)"],
        ]
        v["next_action"]["domain"] = "driver_coaching"
        return v

    def test_the_programme_page_is_fed_from_command_centre_readiness(self, wired):
        shell, _win, _db, bridge = wired
        bridge._last_guidance_view = self._view_with_readiness()
        bridge.refresh()
        page = shell.programme_page
        assert page._map.has_programme
        assert page._map.domains_total == 4
        assert page._map.domains_ready == 2               # race_pace + consistency
        # The engineer's current objective is flagged on the map.
        coaching = next(d for d in page._map.domains if d.key == "driver_coaching")
        assert coaching.is_next is True

    def test_home_links_to_the_programme_page(self, wired):
        shell, _win, _db, _bridge = wired
        shell.home_page._see_programme.click()
        assert shell.current_destination() == "programme"

    def test_starting_the_next_run_from_the_map_opens_that_run(self, wired):
        shell, _win, db, bridge = wired
        bridge._last_guidance_view = self._view_with_readiness()
        bridge.refresh()
        shell.programme_page.start_next_requested.emit("driver_coaching")
        assert [a["activity_type"] for a in db.activities] == ["coaching_run"]
        assert shell.current_destination() == "practice"


class TestV25SetupRevisionLineage:
    """UAT-7: blank Lineage tab + "no way to load previous settings to activate that's
    the settings I'm running in GT7." The bridge never fed lineage_nodes and there was
    no revision history. Both are now driven by the recorded applied revisions."""

    def _with_real_authority(self, bridge):
        """Swap the service onto a real authority + history so revisions are minted."""
        from data.setup_state_authority import ActiveSetupAuthority
        from data.active_setup_store import InMemoryActiveSetupStore
        from services.setup_history_store import SetupHistoryStore
        bridge._setups._authority = ActiveSetupAuthority(store=InMemoryActiveSetupStore())
        bridge._setups._history = SetupHistoryStore()
        scope = bridge._setups.inputs().scope
        bridge._setups._store.set(scope, "race",
                                  {"arb_front": 5, "setup_label": "Setup 1",
                                   "ride_height_front": 70})

    def test_confirmations_build_the_lineage(self, wired):
        shell, _win, _db, bridge = wired
        self._with_real_authority(bridge)
        bridge._setups.confirm_applied_in_game("race")            # rev 1
        bridge._setups.apply("race", {"arb_front": 4})
        bridge._setups.confirm_applied_in_game("race")            # rev 2
        nodes = bridge._lineage_nodes("Setup 1 · rev 2")
        assert [n.node_id for n in nodes] == ["rev2", "rev1"]     # newest first
        assert nodes[0].is_current is True and nodes[1].is_current is False
        assert "Changed" in nodes[0].summary                       # what changed vs rev1

    def test_the_lineage_tab_is_no_longer_blank(self, wired):
        shell, _win, _db, bridge = wired
        self._with_real_authority(bridge)
        bridge._setups.confirm_applied_in_game("race")
        bridge._feed_garage()
        assert shell.garage_page._lineage._body.count() >= 1
        assert shell.garage_page._lineage._empty.isHidden() is True

    def test_loading_a_past_revision_restores_its_values(self, wired):
        shell, _win, _db, bridge = wired
        self._with_real_authority(bridge)
        bridge._setups.confirm_applied_in_game("race")            # rev 1: arb_front 5
        bridge._setups.apply("race", {"arb_front": 4})
        bridge._setups.confirm_applied_in_game("race")            # rev 2: arb_front 4
        shell.garage_page._lineage.revert_requested.emit("rev1")
        assert bridge._setups.sheet("race").get("arb_front") == 5.0
        assert "Loaded rev 1" in shell.garage_page._status.text()

    def test_an_empty_node_id_is_still_the_one_step_undo(self, wired):
        shell, _win, _db, bridge = wired
        self._with_real_authority(bridge)
        bridge._setups.confirm_applied_in_game("race")
        bridge._setups.apply("race", {"arb_front": 4})           # a change to undo
        bridge._on_revert("")                                     # Outcome-page revert
        assert bridge._setups.sheet("race").get("arb_front") == 5.0


class TestV26LockTheBaseSetup:
    """UAT-7: "how do I 'lock the base setup'?" The guidance CTA "Lock the base setup"
    routed to the Garage but nothing there locked — the write path never existed."""

    def _bridge_with_real_db(self, qapp):
        from data.session_db import SessionDB
        db = SessionDB(":memory:")
        db.upsert_preparation_cycle({
            "cycle_id": "c1", "event_name": "E", "car": "Porsche Cayman GT4",
            "track": "Watkins Glen International", "layout": "long",
            "disciplines": ["race", "qualifying"]})
        ctrl = PitCrewController()
        shell = PitCrewShell(ctrl)
        win = _Win()
        bridge = LiveShellBridge(shell, ctrl, window=win, config={"active_cycle_id": "c1"},
                                 db=db, spawn=lambda fn: fn())
        return shell, db, bridge

    def test_the_garage_lock_button_locks_the_active_cycle(self, qapp):
        shell, db, _bridge = self._bridge_with_real_db(qapp)
        shell.garage_page.lock_requested.emit("race", True)
        assert db.setup_locks("c1") == ("race",)
        assert "locked" in shell.garage_page._status.text().lower()

    def test_the_locked_state_is_fed_back_to_the_garage(self, qapp):
        shell, _db, bridge = self._bridge_with_real_db(qapp)
        shell.garage_page.lock_requested.emit("race", True)
        bridge._feed_lock(shell.garage_page)
        assert shell.garage_page._pill_locked.isHidden() is False
        assert shell.garage_page._lock_btn.text() == "Reopen setup"

    def test_reopening_unlocks_it(self, qapp):
        shell, db, _bridge = self._bridge_with_real_db(qapp)
        shell.garage_page.lock_requested.emit("race", True)
        shell.garage_page.lock_requested.emit("race", False)
        assert db.setup_locks("c1") == ()

    def test_locking_needs_an_active_event(self, qapp):
        ctrl = PitCrewController()
        shell = PitCrewShell(ctrl)
        from data.session_db import SessionDB
        bridge = LiveShellBridge(shell, ctrl, window=_Win(), config={}, db=SessionDB(":memory:"),
                                 spawn=lambda fn: fn())
        shell.garage_page.lock_requested.emit("race", True)
        assert "activate an event" in shell.garage_page._status.text().lower()


class TestV27QualiPracticeUsesQualiBeep:
    """UAT-8: "running quali practice it was giving me race RPM beep not quali." The new
    shell never told the live runtime which discipline was being practised, so the beep
    loop used the race RPM. The Garage discipline now drives the runtime refs the beep
    reads."""

    def _with_refs(self, win):
        win._practice_is_qual_ref = [False]
        win._live_mode_ref = ["Race"]
        return win

    def test_selecting_qualifying_flips_the_runtime_to_qual(self, wired):
        shell, win, _db, _bridge = wired
        self._with_refs(win)
        shell.garage_page._selector._buttons["qualifying"].click()
        assert win._practice_is_qual_ref[0] is True
        assert win._live_mode_ref[0] == "Practice"

    def test_selecting_race_flips_it_back(self, wired):
        shell, win, _db, _bridge = wired
        self._with_refs(win)
        shell.garage_page._selector._buttons["qualifying"].click()
        shell.garage_page._selector._buttons["race"].click()
        assert win._practice_is_qual_ref[0] is False

    def test_the_beep_threshold_follows_the_selected_discipline(self, wired):
        from main import resolve_threshold
        shell, win, _db, _bridge = wired
        self._with_refs(win)
        sb = {"qual_rpm": 8000, "race_rpm": 7760, "enabled": True}
        shell.garage_page._selector._buttons["qualifying"].click()
        _k, qual = resolve_threshold(win._live_mode_ref[0], False,
                                     win._practice_is_qual_ref[0], sb)
        shell.garage_page._selector._buttons["race"].click()
        _k, race = resolve_threshold(win._live_mode_ref[0], False,
                                     win._practice_is_qual_ref[0], sb)
        assert qual == 8000 and race == 7760

    def test_a_window_without_the_refs_never_raises(self, wired):
        # The bridge must tolerate a window that doesn't expose the beep refs.
        _shell, _win, _db, bridge = wired
        bridge._window._practice_is_qual_ref = None
        bridge._push_practice_mode("qualifying")   # must not raise


class _PlanVM:
    """Minimal stand-in for the race-plan view model the adapter reads."""
    has_recommendation = True
    stint_plan_rows = [{"laps": 12, "compound": "RM"}]
    candidate_comparison_rows = []
    risks = ()
    replan_triggers = ()
    inputs_rows = []
