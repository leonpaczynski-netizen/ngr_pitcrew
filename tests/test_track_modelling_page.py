"""The guided track-modelling page + service (stage 4b).

Not the classic tab rebuilt: one step live at a time, one primary action, and the
step's own controls only where they are the point.
"""

import pytest

from PyQt6.QtWidgets import QApplication

from data.track_modelling_session import TrackModellingSession
from services.track_modelling import TrackModellingService
from ui.components.track_modelling import TrackModellingPage


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def page(qapp):
    p = TrackModellingPage()
    p.set_tracks(locations=[("watkins_glen", "Watkins Glen International")],
                 layouts=[("watkins_glen__long", "Long Course")])
    return p


def _sel(**kw):
    return TrackModellingSession().select("watkins_glen", "watkins_glen__long").with_(**kw)


class TestOneStepAtATime:
    def test_it_opens_asking_for_a_track(self, page):
        page.set_session(TrackModellingSession())
        assert page._picker.isVisibleTo(page) is True
        assert page._corners_card.isVisibleTo(page) is False
        assert page._primary.isVisibleTo(page) is False      # nothing to do but choose

    def test_choosing_a_track_asks_you_to_drive(self, page):
        page.set_session(_sel())
        assert page._headline.text() == "Ready to drive"
        assert page._primary.text() == "Start recording laps"
        assert page._corners_card.isVisibleTo(page) is False

    def test_recording_shows_the_lap_count_and_only_offers_stopping(self, page):
        page.set_session(_sel(capturing=True), laps_captured=3)
        assert "3 clean laps captured" in page._capture.text()
        assert page._primary.text() == "Stop recording"

    def test_a_single_lap_is_not_pluralised(self, page):
        page.set_session(_sel(capturing=True), laps_captured=1)
        assert "1 clean lap captured" in page._capture.text()

    def test_the_corner_list_appears_only_when_there_are_corners_to_check(self, page):
        page.set_session(_sel(has_captured_laps=True))
        assert page._corners_card.isVisibleTo(page) is False
        page.set_session(_sel(has_segments=True),
                         corners=[{"number": 1, "name": "Turn 1", "type": "slow"}])
        assert page._corners_card.isVisibleTo(page) is True
        assert page._corners.rowCount() == 1

    def test_a_finished_model_offers_no_primary_action(self, page):
        page.set_session(_sel(model_active=True))
        assert page._headline.text() == "This track is modelled"
        assert page._primary.isVisibleTo(page) is False


class TestProgressIsAlwaysVisible:
    def test_six_steps_are_shown(self, page):
        assert len(page._chip_labels) == 6

    def test_completed_steps_are_ticked(self, page):
        page.set_session(_sel(has_captured_laps=True))
        assert page._chip_labels[0].text().startswith("✓")
        assert page._chip_labels[2].text() == "Build the model"     # current, no tick


class TestActionsAreEmitted:
    def test_the_primary_emits_its_coordinator_action(self, page):
        seen = []
        page.action_requested.connect(seen.append)
        page.set_session(_sel())
        page._primary.click()
        assert seen == ["start_capture"]

    def test_an_escape_emits_its_own_action(self, page):
        seen = []
        page.action_requested.connect(seen.append)
        page.set_session(_sel())
        page._secondaries[0].click()
        assert seen == ["clear_track"]

    def test_choosing_both_pickers_emits_the_selection(self, page):
        seen = []
        page.track_selected.connect(lambda a, b: seen.append((a, b)))
        page._location.setCurrentIndex(1)
        page._location.activated.emit(1)          # circuit chosen → layouts appear
        page._layout_combo.setCurrentIndex(1)
        page._layout_combo.activated.emit(1)
        assert seen[-1] == ("watkins_glen", "watkins_glen__long")


class TestLayoutsAreScopedToTheChosenCircuit:
    """UAT-6: "when selecting a track only the relevant layouts should appear" — the
    combo showed every layout of every circuit (six unrelated "Full Course" entries)."""

    def _multi(self, qapp):
        p = TrackModellingPage()
        p.set_tracks(
            locations=[("watkins_glen", "Watkins Glen International"),
                       ("fuji", "Fuji Speedway")],
            layouts={
                "watkins_glen": [("watkins_glen__long", "Long Course"),
                                 ("watkins_glen__short", "Short Course")],
                "fuji": [("fuji__gp", "Grand Prix"), ("fuji__full", "Full Course")],
            })
        return p

    def test_no_layouts_are_shown_until_a_circuit_is_chosen(self, qapp):
        p = self._multi(qapp)
        # Only the "Choose a layout…" placeholder — not 4 layouts from 2 circuits.
        assert p._layout_combo.count() == 1
        assert p._layout_combo.isEnabled() is False

    def test_choosing_a_circuit_shows_only_its_layouts(self, qapp):
        p = self._multi(qapp)
        p._location.setCurrentIndex(p._location.findData("watkins_glen"))
        p._location.activated.emit(p._location.currentIndex())
        labels = [p._layout_combo.itemText(i) for i in range(1, p._layout_combo.count())]
        assert labels == ["Long Course", "Short Course"]
        assert "Grand Prix" not in labels and "Full Course" not in labels

    def test_switching_circuit_replaces_the_layout_list(self, qapp):
        p = self._multi(qapp)
        p._location.setCurrentIndex(p._location.findData("watkins_glen"))
        p._location.activated.emit(p._location.currentIndex())
        p._location.setCurrentIndex(p._location.findData("fuji"))
        p._location.activated.emit(p._location.currentIndex())
        ids = [p._layout_combo.itemData(i) for i in range(1, p._layout_combo.count())]
        assert ids == ["fuji__gp", "fuji__full"]

    def test_switching_circuit_clears_a_stale_layout_selection(self, qapp):
        """A layout from the old circuit must not stay selected against the new one."""
        p = self._multi(qapp)
        p._location.setCurrentIndex(p._location.findData("watkins_glen"))
        p._location.activated.emit(p._location.currentIndex())
        p._layout_combo.setCurrentIndex(1)                     # Long Course
        p._location.setCurrentIndex(p._location.findData("fuji"))
        p._location.activated.emit(p._location.currentIndex())
        assert p._layout_combo.currentData() == ""             # back to placeholder

    def test_a_corner_edit_names_its_row(self, page):
        seen = []
        page.segment_action.connect(lambda r, a: seen.append((r, a)))
        page.set_session(_sel(has_segments=True),
                         corners=[{"number": 1, "name": "T1"}, {"number": 2, "name": "T2"}])
        page._corners.setCurrentCell(1, 0)
        page._edit_buttons["reject"].click()
        assert seen == [(1, "reject")]


class TestErrorsAreExplained:
    def test_an_error_shows_the_cause_and_a_way_out(self, page):
        page.set_session(_sel().failed("no usable laps"))
        assert page._detail.isVisibleTo(page) is True
        assert page._detail.text() == "no usable laps"
        assert page._primary.text() == "Start again"


class TestService:
    def test_selecting_a_track_needs_both_parts(self):
        svc = TrackModellingService()
        assert svc.select_track("nonexistent_circuit", "").ok is False
        assert svc.select_track("nonexistent_circuit", "nonexistent_circuit__nope").ok is True
        assert svc.session.identity_known is True

    def test_an_illegal_action_is_refused_rather_than_performed(self):
        """The page hides illegal actions, but a service that trusts its caller can be
        driven into an impossible state."""
        svc = TrackModellingService()
        result = svc.perform("build_model")
        assert result.ok is False
        assert "not available at this point" in result.reason

    def test_starting_and_stopping_capture(self):
        class _Ctrl:
            def __init__(self):
                self.started = self.stopped = False

            def start(self):
                self.started = True

            def stop(self):
                self.stopped = True

        ctrl = _Ctrl()
        svc = TrackModellingService(capture_controller=ctrl)
        svc.select_track("nonexistent_circuit", "nonexistent_circuit__nope")
        assert svc.perform("start_capture").ok is True
        assert ctrl.started is True and svc.session.capturing is True
        assert svc.perform("stop_capture").ok is True
        assert ctrl.stopped is True and svc.session.has_captured_laps is True

    def test_a_capture_failure_becomes_an_error_with_its_reason(self):
        class _Boom:
            def start(self):
                raise RuntimeError("no telemetry")

        svc = TrackModellingService(capture_controller=_Boom())
        svc.select_track("nonexistent_circuit", "nonexistent_circuit__nope")
        result = svc.perform("start_capture")
        assert result.ok is False
        assert "no telemetry" in svc.session.error_message

    def test_recalibrating_discards_the_derived_work(self):
        """Validating new laps against a model built from the OLD ones would report
        agreement that was never tested."""
        svc = TrackModellingService()
        svc.select_track("nonexistent_circuit", "nonexistent_circuit__nope")
        svc._session = svc.session.with_(has_captured_laps=True, has_segments=True,
                                         review_complete=True)
        assert svc.perform("recalibrate").ok is True
        assert svc.session.has_segments is False
        assert svc.session.review_complete is False
        assert svc.session.location_id == "nonexistent_circuit"   # the track is kept

    def test_you_cannot_recalibrate_a_model_you_just_validated(self):
        """The coordinator does not allow it from VALIDATED — activate or edit first.
        The service must honour that rather than quietly doing it."""
        svc = TrackModellingService()
        svc.select_track("nonexistent_circuit", "nonexistent_circuit__nope")
        svc._session = svc.session.with_(has_captured_laps=True, has_segments=True,
                                         review_complete=True, validation_passed=True)
        result = svc.perform("recalibrate")
        assert result.ok is False
        assert svc.session.has_segments is True          # untouched

    def test_an_injected_builder_performs_the_step(self):
        def _build(session):
            return session.with_artefact("station_map", {"ok": True})

        svc = TrackModellingService(builders={"build_model": _build})
        svc.select_track("nonexistent_circuit", "nonexistent_circuit__nope")
        svc._session = svc.session.with_(has_captured_laps=True)
        assert svc.perform("build_model").ok is True
        assert svc.session.has_station_map is True

    def test_a_builder_that_throws_becomes_an_error_not_a_crash(self):
        def _boom(session):
            raise RuntimeError("detector failed")

        svc = TrackModellingService(builders={"build_model": _boom})
        svc.select_track("nonexistent_circuit", "nonexistent_circuit__nope")
        svc._session = svc.session.with_(has_captured_laps=True)
        result = svc.perform("build_model")
        assert result.ok is False
        assert "detector failed" in svc.session.error_message

    def test_an_unknown_action_is_refused(self):
        assert TrackModellingService().perform("nonsense").ok is False
