"""Tests for the LiveShellBridge (read side + apply/revert routing).

Uses a duck-typed fake window/services so the bridge is exercised without a live
GT7 session. Confirms the shell's view-models are fed from the (fake) real services
and that Apply/Revert route back to the window's existing apply path.
"""

import pytest

from PyQt6.QtWidgets import QApplication

from ui.live_shell_bridge import LiveShellBridge
from ui.pit_crew_controller import PitCrewController
from ui.pit_crew_shell import PitCrewShell
from data.event_context import build_event_context
from data.session_context import build_session_context


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def _config():
    """A realistic config. The setup engine resolves car/track from the DB + config —
    NOT from the window — so a setup is always scoped to a real car at a real track."""
    return {"strategy": {"car": "GT-R", "track": "Fuji Speedway"}}


class _Auth:
    """Mirrors the REAL ActiveSetupAuthority contract.

    The previous fake took no arguments and exposed ``label``/``applied`` attributes —
    none of which ``ActiveSetupAuthority``/``ActiveSetup`` actually have, so this test
    passed while the shipped shell could never read an active setup (UAT-2 V-9).
    """

    class _Active:
        def label(self):
            return "Race v2"

        @property
        def is_active_on_car(self):
            return True

    def active_setup(self, identity, purpose="Race"):
        return self._Active() if purpose == "Race" else None


class _Form:
    def __init__(self):
        self.applied_with = None
    def current_setup_dict(self):
        return {"ride_height_front": 60, "ride_height_rear": 74, "arb_front": 5,
                "arb_rear": 4, "aero_front": 430, "aero_rear": 590,
                "tyre_front": "Racing: Hard", "tyre_rear": "Racing: Hard"}
    def apply_ai_fields(self, fields):
        self.applied_with = dict(fields)


class _FakeWindow:
    def __init__(self, connected=True):
        self._connected = connected
        self._race_form = _Form()
        self._setup_authority = _Auth()
        self.reverted = False
    def _build_event_context(self):
        return build_event_context(event={"id": 3, "name": "Round 3"},
                                   strategy={"car": "GT-R", "track_location_id": "fuji"})
    def _build_session_context(self):
        return build_session_context(connected=self._connected, packet_count=9, laps_recorded=7)
    def _build_strategy_context(self):
        return None
    def _autosave_applied_setup(self, form):
        pass
    def _revert_last_change_for_form(self, form):
        self.reverted = True


class TestBridgeReadSide:
    def test_refresh_feeds_appstate_and_garage(self, qapp):
        ctrl = PitCrewController()
        shell = PitCrewShell(ctrl)
        win = _FakeWindow(connected=True)
        b = LiveShellBridge(shell, ctrl, window=win, config=_config())
        b.refresh()
        st = ctrl.state()
        assert st.car == "GT-R"
        assert st.connected is True
        assert st.active_setup_label == "Race v2"
        # The Garage sheet is fed from the STORE now. The classic form's in-progress
        # setup is SEEDED into it once, so nothing the driver had is lost on the switch.
        assert b._setups.sheet("race").get("arb_rear") == 4.0
        assert shell.garage_page._sheet._empty.isHidden() is True

    def test_disconnected_state(self, qapp):
        ctrl = PitCrewController()
        shell = PitCrewShell(ctrl)
        win = _FakeWindow(connected=False)
        b = LiveShellBridge(shell, ctrl, window=win, config=_config())
        b.refresh()
        assert ctrl.state().connected is False

    def test_none_window_is_safe(self, qapp):
        ctrl = PitCrewController()
        shell = PitCrewShell(ctrl)
        b = LiveShellBridge(shell, ctrl, window=None, config=_config())
        b.refresh()   # must not raise
        assert ctrl.state().has_active_event is False


class TestBridgeWriteSide:
    """Apply and revert go through the headless setup engine, not the classic form."""

    def _wired(self, qapp):
        ctrl = PitCrewController()
        shell = PitCrewShell(ctrl)
        win = _FakeWindow()
        b = LiveShellBridge(shell, ctrl, window=win, config=_config())
        b.refresh()          # seeds the store from the classic form
        return shell, win, b

    def test_apply_writes_the_sheet(self, qapp):
        _shell, _win, b = self._wired(qapp)
        b._on_apply({"arb_rear": 4, "brake_bias_front": 52})
        sheet = b._setups.sheet("race")
        assert sheet.get("arb_rear") == 4.0
        assert sheet.get("brake_bias_front") == 52.0

    def test_apply_via_garage_signal(self, qapp):
        shell, _win, b = self._wired(qapp)
        shell.garage_page.apply_requested.emit({"arb_rear": 3})
        assert b._setups.sheet("race").get("arb_rear") == 3.0

    def test_the_classic_form_is_kept_in_step_while_it_still_exists(self, qapp):
        """Transitional, removed in stage 6: the old window must never display numbers
        that disagree with the real sheet."""
        _shell, win, b = self._wired(qapp)
        b._on_apply({"arb_rear": 4})
        assert win._race_form.applied_with is not None
        assert win._race_form.applied_with["arb_rear"] == 4.0

    def test_revert_undoes_the_last_apply(self, qapp):
        _shell, _win, b = self._wired(qapp)
        before = b._setups.sheet("race").get("arb_rear")
        b._on_apply({"arb_rear": 4})
        b._on_revert("n2")
        assert b._setups.sheet("race").get("arb_rear") == before

    def test_revert_with_nothing_to_undo_is_safe(self, qapp):
        _shell, _win, b = self._wired(qapp)
        b._on_revert("n2")          # must not raise
        assert b._setups.sheet("race").get("arb_rear") == 4.0

    def test_empty_apply_changes_nothing(self, qapp):
        _shell, _win, b = self._wired(qapp)
        before = b._setups.sheet("race").as_dict()
        b._on_apply({})
        assert b._setups.sheet("race").as_dict() == before


class _Announcer:
    def __init__(self):
        self.mode = None
    def set_session_mode(self, mode):
        self.mode = mode


class TestLiveSessionMode:
    """UAT: 'Begin quali doesn't start quali' and 'the race strat wasn't loaded'. The
    shell must actually assert the live session mode (Qualifying / Race) that drives the
    shift-beep RPM and the announcer, instead of always saying Practice."""

    def _wired(self, qapp):
        ctrl = PitCrewController()
        shell = PitCrewShell(ctrl)
        win = _FakeWindow()
        # The runtime shift-beep refs + announcer the bridge writes into.
        win._practice_is_qual_ref = [False]
        win._live_mode_ref = ["Race"]
        win._announcer = _Announcer()
        b = LiveShellBridge(shell, ctrl, window=win, config=_config())
        b.refresh()
        return shell, win, b

    def test_plain_practice_follows_the_selected_discipline(self, qapp):
        _shell, win, b = self._wired(qapp)
        b._on_discipline("qualifying")
        assert win._live_mode_ref[0] == "Practice"
        assert win._practice_is_qual_ref[0] is True
        b._on_discipline("race")
        assert win._practice_is_qual_ref[0] is False

    def test_begin_qualifying_enters_qualifying_mode(self, qapp):
        shell, win, b = self._wired(qapp)
        b._on_begin_qualifying()
        assert b._live_session_mode == "qualifying"
        assert b._discipline == "qualifying"
        assert win._live_mode_ref[0] == "Qualifying"
        assert win._practice_is_qual_ref[0] is True
        assert win._announcer.mode == "qualifying"
        # It shows the live surface.
        assert shell.current_destination() == "live_pit_wall"

    def test_qualifying_mode_survives_a_refresh(self, qapp):
        """The 750ms refresh used to stomp the mode back to Practice every tick."""
        _shell, win, b = self._wired(qapp)
        b._on_begin_qualifying()
        b.refresh()
        assert win._live_mode_ref[0] == "Qualifying"
        assert win._practice_is_qual_ref[0] is True

    def _author_quali(self, b):
        # The compound rule only touches an AUTHORED qualifying sheet (never authors an
        # empty one), so give it a real setup first.
        b._setups.apply("qualifying", {"arb_front": 5, "arb_rear": 4,
                                       "aero_front": 400, "aero_rear": 500})

    def test_begin_qualifying_fits_the_softest_allowed_compound(self, qapp):
        """Rule: qualifying always runs the softest allowed compound. With no tyre
        restriction the softest dry racing compound (RS) is applied to the quali sheet."""
        _shell, _win, b = self._wired(qapp)
        self._author_quali(b)
        b._on_begin_qualifying()
        target, current, target_name, _cur_name, is_wet = b._qualifying_tyre_state()
        assert target == "RS"                  # default-available softest dry
        assert current == "RS"                 # Begin Qualifying applied it
        assert is_wet is False and "Soft" in target_name

    def test_track_wet_toggle_switches_qualifying_to_the_rain_tyre(self, qapp):
        _shell, _win, b = self._wired(qapp)
        self._author_quali(b)
        b._on_begin_qualifying()               # dry: RS on the quali sheet
        b._on_track_wet_toggled(True)          # driver says the track is wet
        target, current, _tn, _cn, is_wet = b._qualifying_tyre_state()
        assert is_wet is True and target == "IM"   # rain tyre
        assert current == "IM"                     # applied to the sheet
        b._on_track_wet_toggled(False)             # track dried again
        assert b._qualifying_tyre_state()[0] == "RS"

    def test_telemetry_never_auto_asserts_race_mode(self, qapp):
        """A RACING phase must NOT flip the app into race mode — a practice/qualifying
        session can look like RACING, and race start is now an explicit driver action."""
        _shell, win, b = self._wired(qapp)
        b._on_race_state("RACING")
        assert b._live_session_mode is None
        # But the phase is captured so the pit wall can show IN PIT.
        b._on_race_state("IN PIT")
        assert b._live_race_phase == "IN PIT"

    def test_start_race_enters_race_mode_explicitly(self, qapp):
        shell, win, b = self._wired(qapp)
        b._enter_race()
        assert b._live_session_mode == "race"
        assert b._discipline == "race"
        assert win._live_mode_ref[0] == "Race"
        assert win._practice_is_qual_ref[0] is False
        assert win._announcer.mode == "race"
        assert shell.current_destination() == "live_pit_wall"

    def test_race_mode_survives_a_refresh(self, qapp):
        _shell, win, b = self._wired(qapp)
        b._enter_race()
        b.refresh()
        assert win._live_mode_ref[0] == "Race"

    def test_race_finished_releases_race_mode_only(self, qapp):
        _shell, _win, b = self._wired(qapp)
        b._enter_race()
        b._on_race_state("FINISHED")
        assert b._live_session_mode is None

    def test_race_readiness_lists_open_stages(self, qapp):
        _shell, _win, b = self._wired(qapp)
        ready, blockers = b._race_readiness()
        # A fresh fake session has no approved plan / recorded run, so it is not ready
        # but still reports what is open rather than hard-blocking.
        assert ready is False
        assert any("plan" in x for x in blockers)


class TestShiftTelemetryCalibration:
    """Phase 2: 'Calibrate from telemetry' reads recorded laps, calibrates the torque
    curve, and stores telemetry engine data that lifts the strategy off manual entry."""

    def _wired(self, qapp, laps):
        ctrl = PitCrewController()
        shell = PitCrewShell(ctrl)
        win = _FakeWindow()
        win._current_car_id = lambda: 7
        win._build_event_context = lambda: build_event_context(
            event={"id": 3, "name": "Round 3"},
            strategy={"car": "GT-R", "track_location_id": "fuji", "track": "Fuji Speedway"})
        b = LiveShellBridge(shell, ctrl, window=win, config=_config())
        b.refresh()

        class _DB:
            def get_laps_with_telemetry(self, car_id, track, **kw):
                return laps
        b._db = _DB()
        return shell, win, b

    def _pull(self):
        # Reuse the synthetic wide-open-throttle pull from the calibration tests.
        import sys, os
        sys.path.insert(0, os.path.dirname(__file__))
        from test_shift_torque_calibration import _wot_pull, _lap
        return [_lap(_wot_pull())]

    def test_calibrate_stores_telemetry_engine_data(self, qapp):
        shell, _win, b = self._wired(qapp, self._pull())
        b._on_shift_calibrate_requested()
        scope = str(b._setups.inputs().scope or "")
        assert scope
        stored = b._shift_store.get(scope) or {}
        ed = stored.get("calibrated_engine_data") or {}
        assert ed.get("source") == "telemetry"
        assert ed.get("calibration_confidence") == "high"
        assert ed.get("peak_power_rpm") and ed.get("redline")

    def test_calibrate_reports_success_on_the_view(self, qapp):
        shell, _win, b = self._wired(qapp, self._pull())
        b._on_shift_calibrate_requested()
        status = shell.garage_page.shift_strategy_view._lbl_calib.text()
        assert "Calibrated from telemetry" in status

    def test_seeded_engine_data_persists_even_when_strategy_compute_fails(self, qapp, monkeypatch):
        # Seeding engine data is usually needed EXACTLY when the car's specs are unknown —
        # i.e. when the strategy computation is insufficient. The seeded values must persist
        # regardless (they used to be dropped because the save came after a failing compute).
        import strategy.shift_strategy_engine as eng

        def _boom(*a, **k):
            raise RuntimeError("insufficient inputs")

        monkeypatch.setattr(eng, "compute_shift_strategy", _boom)
        shell, _win, b = self._wired(qapp, self._pull())
        scope = str(b._setups.inputs().scope or "")
        assert scope
        seed = {"peak_power_rpm": 7000, "peak_torque_rpm": 5200, "redline": 7600}
        b._on_shift_engine_seeded(seed)
        stored = b._shift_store.get(scope) or {}
        assert stored.get("manual_engine_data") == seed

    def test_no_telemetry_database_is_reported_not_crashed(self, qapp):
        shell, _win, b = self._wired(qapp, self._pull())
        b._db = None
        b._on_shift_calibrate_requested()          # must not raise
        status = shell.garage_page.shift_strategy_view._lbl_calib.text()
        assert "database" in status.lower()

    def test_thin_telemetry_does_not_claim_a_calibration(self, qapp):
        # No wide-open-throttle frames → no calibration, honest status, nothing stored.
        thin = [{"frames": [{"throttle": 0.3, "rpm": 4000, "gear": 3,
                             "speed_kmh": 100, "elapsed_ms": i * 100, "brake": 0.0}
                            for i in range(20)]}]
        shell, _win, b = self._wired(qapp, thin)
        b._on_shift_calibrate_requested()
        scope = str(b._setups.inputs().scope or "")
        stored = b._shift_store.get(scope) or {}
        assert "calibrated_engine_data" not in stored


class TestRegulationBOP:
    """A series-regulated weight/power entered in the Garage persists onto BOTH
    disciplines and overrides the stock spec the vehicle model reasons from."""

    def _wired(self, qapp):
        ctrl = PitCrewController()
        shell = PitCrewShell(ctrl)
        win = _FakeWindow()
        win._current_car_id = lambda: 7
        win._build_event_context = lambda: build_event_context(
            event={"id": 3, "name": "Round 3"},
            strategy={"car": "GT-R", "track_location_id": "fuji", "track": "Fuji Speedway"})
        b = LiveShellBridge(shell, ctrl, window=win, config=_config())
        b.refresh()
        return b

    def test_regulation_persists_to_both_disciplines_and_feeds_the_specs(self, qapp):
        from strategy.setup_engineering import effective_car_specs
        b = self._wired(qapp)
        b._on_regulation_changed({"weight_kg": 1335, "power_hp": 606})   # Supercars BOP
        for disc in ("race", "qualifying"):
            sheet = b._setups.sheet(disc).as_dict()
            assert sheet.get("weight_kg") == 1335 and sheet.get("power_hp") == 606
        eff = effective_car_specs("GT-R", b._setups.sheet("race").as_dict())
        assert eff.get("weight_kg") == 1335 and eff.get("power_hp") == 606


class TestConfirmInGameAppliesRecommendation:
    """"I've entered this in GT7" must write the shown recommendation onto the sheet
    first, so the next Analyse doesn't re-recommend the changes the driver just made."""

    def _wired(self, qapp):
        ctrl = PitCrewController()
        shell = PitCrewShell(ctrl)
        win = _FakeWindow()
        b = LiveShellBridge(shell, ctrl, window=win, config=_config())
        b.refresh()   # seeds the sheet from the classic form (arb_rear = 4)
        return b

    def test_confirm_in_game_writes_recommendation_and_consumes_it(self, qapp):
        from services.setup_service import AnalysisResult
        b = self._wired(qapp)
        assert b._setups.sheet("race").as_dict().get("arb_rear") == 4.0
        # A pending recommendation the driver has read and typed into GT7: arb_rear 4 -> 6.
        b._last_analysis = AnalysisResult(
            ok=True, discipline="race",
            changes=({"field": "arb_rear", "from": 4, "to": 6, "to_clamped": 6},),
            setup_fields={"arb_rear": 6})
        b._on_applied_in_game("race")
        # The sheet now matches what is on the car, and the recommendation is consumed.
        assert b._setups.sheet("race").as_dict().get("arb_rear") == 6.0
        assert b._last_analysis is None


class TestPracticeCompoundFromAppliedSetup:
    """The Practice run-card tyre selector must default to the compound on the APPLIED
    setup — Practice runs the tyre the driver put on the car — not an arbitrary
    un-sampled compound the driver could confirm by mistake and mis-tag the run."""

    def _selected_code(self, rc):
        idx = rc._compound_combo.currentIndex()
        codes = list(rc._compound_codes)
        return codes[idx].upper() if 0 <= idx < len(codes) else ""

    def _wired(self, qapp):
        ctrl = PitCrewController()
        shell = PitCrewShell(ctrl)
        win = _FakeWindow()
        b = LiveShellBridge(shell, ctrl, window=win, config=_config())
        b.refresh()   # seeds the store from the classic form (Racing: Hard -> RH)
        return b, shell

    def test_selector_defaults_to_the_applied_compound(self, qapp):
        b, shell = self._wired(qapp)
        # The seeded/applied setup is on Racing: Hard.
        assert b._setups.sheet("race").as_dict().get("tyre_front") == "Racing: Hard"
        rc = shell.run_card
        b._feed_run_compound_options(rc)
        assert self._selected_code(rc) == "RH", "Practice must default to the applied RH"

    def test_driver_pick_override_still_wins(self, qapp):
        b, shell = self._wired(qapp)
        rc = shell.run_card
        b._feed_run_compound_options(rc)
        # Driver explicitly picks a different compound on the run card.
        b._on_test_compound_change("RS")
        b._feed_run_compound_options(rc)
        assert self._selected_code(rc) == "RS", "an explicit pick must not be overwritten"

    def test_falls_back_to_unsampled_only_when_no_applied_compound(self, qapp):
        b, shell = self._wired(qapp)
        # Blank the sheet compound so there is no applied compound to honour.
        b._setups.apply("race", {"tyre_front": "", "tyre_rear": ""})
        rc = shell.run_card
        b._feed_run_compound_options(rc)
        # With no applied compound, the cover-all-compounds nudge is allowed to pick.
        assert self._selected_code(rc) in {"RH", "RM", "RS", ""}


class TestSaveFrontWeightDist:
    """_on_save_front_weight_dist routes to CarWeightDistStore and invalidates the cache.

    Uses a fake store injected after construction so no filesystem is touched and
    the test stays fast/offline.
    """

    class _FakeStore:
        def __init__(self):
            self.calls: list = []

        def set(self, car_name: str, frac: float) -> bool:
            self.calls.append((car_name, frac))
            return True

    def _wired(self, qapp):
        ctrl = PitCrewController()
        shell = PitCrewShell(ctrl)
        win = _FakeWindow()
        b = LiveShellBridge(shell, ctrl, window=win, config=_config())
        b.refresh()
        return b, shell

    def test_save_calls_store_and_invalidates(self, qapp, monkeypatch):
        b, _shell = self._wired(qapp)
        fake_store = self._FakeStore()
        b._car_wt_store = fake_store
        invalidated = []
        monkeypatch.setattr(b._car_wt_mod, "invalidate", lambda: invalidated.append(True))
        b._front_weight_dist_pct = 42.0
        monkeypatch.setattr(
            b._setups, "inputs",
            lambda: type("I", (), {"car": "Porsche 911 RSR (991) '17"})())
        b._on_save_front_weight_dist()
        assert len(fake_store.calls) == 1
        assert fake_store.calls[0][0] == "Porsche 911 RSR (991) '17"
        assert abs(fake_store.calls[0][1] - 0.42) < 0.001
        assert len(invalidated) == 1

    def test_no_car_name_does_not_save(self, qapp, monkeypatch):
        b, _shell = self._wired(qapp)
        fake_store = self._FakeStore()
        b._car_wt_store = fake_store
        b._front_weight_dist_pct = 42.0
        monkeypatch.setattr(
            b._setups, "inputs",
            lambda: type("I", (), {"car": ""})())
        b._on_save_front_weight_dist()
        assert fake_store.calls == []

    def test_zero_pct_does_not_save(self, qapp, monkeypatch):
        b, _shell = self._wired(qapp)
        fake_store = self._FakeStore()
        b._car_wt_store = fake_store
        b._front_weight_dist_pct = None
        monkeypatch.setattr(
            b._setups, "inputs",
            lambda: type("I", (), {"car": "Porsche 911 RSR (991) '17"})())
        b._on_save_front_weight_dist()
        assert fake_store.calls == []

    def test_status_reported_on_success(self, qapp, monkeypatch):
        b, shell = self._wired(qapp)
        fake_store = self._FakeStore()
        b._car_wt_store = fake_store
        monkeypatch.setattr(b._car_wt_mod, "invalidate", lambda: None)
        b._front_weight_dist_pct = 38.0
        monkeypatch.setattr(
            b._setups, "inputs",
            lambda: type("I", (), {"car": "Toyota GR86"})())
        b._on_save_front_weight_dist()
        # garage_page.set_status should have received a confirmation message.
        status = shell.garage_page._status.text()
        assert "38" in status and "Toyota GR86" in status


class TestBuildInputsBallast:
    """_build_inputs injects ballast_kg / ballast_position from the active discipline sheet.

    Mirrors the TestBridgeWriteSide/_build_inputs pattern: wire a real bridge (no
    filesystem, seeded from the fake _Form), write ballast onto the sheet via the same
    _on_ballast_changed path the real Garage uses, then confirm _build_inputs returns the
    expected SetupInputs values.
    """

    def _wired(self, qapp):
        ctrl = PitCrewController()
        shell = PitCrewShell(ctrl)
        win = _FakeWindow()
        b = LiveShellBridge(shell, ctrl, window=win, config=_config())
        b.refresh()   # seeds the store from the classic form
        return b

    def test_ballast_injected_when_nonzero(self, qapp):
        b = self._wired(qapp)
        b._on_ballast_changed({"ballast_kg": 60, "ballast_position": 30})
        inp = b._build_inputs()
        assert inp.ballast_kg == 60.0
        assert inp.ballast_position == 30.0

    def test_ballast_defaults_to_zero_when_not_set(self, qapp):
        b = self._wired(qapp)
        # No ballast written — sheet has no ballast_kg key; result must be 0.0 (no-op).
        inp = b._build_inputs()
        assert inp.ballast_kg == 0.0
        assert inp.ballast_position == 0.0

    def test_zero_ballast_kg_does_not_inject(self, qapp):
        b = self._wired(qapp)
        # Explicitly writing ballast_kg=0 must still give 0.0 on SetupInputs (no replace).
        b._on_ballast_changed({"ballast_kg": 0, "ballast_position": 25})
        inp = b._build_inputs()
        assert inp.ballast_kg == 0.0
