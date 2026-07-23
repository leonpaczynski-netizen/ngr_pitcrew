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
