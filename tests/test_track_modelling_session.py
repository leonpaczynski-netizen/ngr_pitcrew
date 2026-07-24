"""Track Modelling's working state, headless.

Confirmed as a surface that must be CARRIED ACROSS to the new shell rather than retired
— not every track is modelled yet. Its state machine (data.track_modelling_coordinator)
and its formatting layer (ui.track_modelling_vm) were already pure; only the INPUTS to
them were trapped in Qt combo boxes and mixin attributes. This is that extraction.
"""

from data.track_modelling_coordinator import TrackModellingState as S
from data.track_modelling_session import (
    TrackModellingSession, capture_flags, session_from_capture,
)


class _Ctrl:
    def __init__(self, name):
        self._state = type("St", (), {"name": name})()


class TestIdentity:
    def test_nothing_selected_is_no_track(self):
        assert TrackModellingSession().identity_known is False
        assert TrackModellingSession().state is S.NO_TRACK

    def test_a_partial_selection_is_not_an_identity(self):
        assert TrackModellingSession(location_id="watkins").identity_known is False

    def test_selecting_both_identifies_the_track(self):
        s = TrackModellingSession().select("watkins_glen", "long_course")
        assert s.identity_known is True
        assert s.state is S.IDENTIFIED

    def test_selection_is_whitespace_normalised(self):
        s = TrackModellingSession().select("  watkins  ", " long ")
        assert (s.location_id, s.layout_id) == ("watkins", "long")

    def test_reselecting_the_same_track_keeps_the_job(self):
        s = TrackModellingSession().select("a", "b").with_(has_station_map=True)
        assert s.select("a", "b") is s
        assert s.select("a", "b").has_station_map is True

    def test_changing_track_clears_the_previous_job(self):
        """Carrying a station map onto another layout would model the wrong circuit."""
        s = (TrackModellingSession().select("a", "b")
             .with_(has_station_map=True, has_segments=True, review_complete=True))
        moved = s.select("c", "d")
        assert moved.has_station_map is False
        assert moved.has_segments is False
        assert moved.review_complete is False
        assert moved.state is S.IDENTIFIED


class TestStateDerivation:
    def _sel(self, **kw):
        return TrackModellingSession().select("loc", "lay").with_(**kw)

    def test_capturing(self):
        assert self._sel(capturing=True).state is S.CAPTURING

    def test_captured_laps_await_a_build(self):
        assert self._sel(has_captured_laps=True).state is S.CAPTURE_COMPLETE

    def test_segments_awaiting_review(self):
        assert self._sel(has_segments=True).state is S.REVIEW_REQUIRED

    def test_reviewed_segments_are_a_draft_model(self):
        assert self._sel(has_segments=True, review_complete=True).state is S.DRAFT_MODEL

    def test_validated(self):
        assert self._sel(has_segments=True, review_complete=True,
                         validation_passed=True).state is S.VALIDATED

    def test_an_approved_model_on_disk_lands_straight_in_active(self):
        assert self._sel(model_active=True).state is S.ACTIVE

    def test_error_wins_over_everything(self):
        assert self._sel(model_active=True, error=True).state is S.ERROR

    def test_the_inputs_handed_to_the_coordinator_match_the_session(self):
        s = self._sel(has_station_map=True, review_complete=True)
        inp = s.to_inputs()
        assert inp.identity_known is True
        assert inp.has_station_map is True
        assert inp.review_complete is True


class TestCaptureFolding:
    def test_recording_reads_as_capturing(self):
        capturing, captured = capture_flags(_Ctrl("RECORDING"))
        assert capturing is True and captured is False

    def test_stopped_and_built_read_as_captured(self):
        assert capture_flags(_Ctrl("STOPPED"))[1] is True
        assert capture_flags(_Ctrl("BUILT"))[1] is True

    def test_no_controller_is_safe(self):
        assert capture_flags(None) == (False, False)

    def test_a_restored_session_counts_as_captured(self):
        assert capture_flags(None, restored_session=object())[1] is True

    def test_folding_updates_the_session(self):
        s = TrackModellingSession().select("loc", "lay")
        assert session_from_capture(s, _Ctrl("RECORDING")).state is S.CAPTURING
        assert session_from_capture(s, _Ctrl("STOPPED")).state is S.CAPTURE_COMPLETE


class TestArtefacts:
    def test_attaching_a_station_map_sets_its_flag(self):
        s = TrackModellingSession().select("l", "y").with_artefact("station_map", {"x": 1})
        assert s.has_station_map is True
        assert s.artefact("station_map") == {"x": 1}

    def test_clearing_an_artefact_clears_its_flag(self):
        s = (TrackModellingSession().select("l", "y")
             .with_artefact("station_map", {"x": 1}).with_artefact("station_map", None))
        assert s.has_station_map is False

    def test_detection_and_reference_path_map_to_their_flags(self):
        s = (TrackModellingSession().select("l", "y")
             .with_artefact("detection", object()).with_artefact("reference_path", object()))
        assert s.has_segments is True and s.has_reference_path is True

    def test_an_unmapped_artefact_is_carried_without_inventing_a_flag(self):
        s = TrackModellingSession().select("l", "y").with_artefact("alignment", object())
        assert s.artefact("alignment") is not None
        assert s.has_segments is False


class TestErrors:
    def test_failing_records_the_reason_and_stops_building(self):
        s = TrackModellingSession().select("l", "y").with_(building=True).failed("no usable laps")
        assert s.state is S.ERROR
        assert s.error_message == "no usable laps"
        assert s.building is False

    def test_clearing_the_error_restores_the_derived_state(self):
        s = TrackModellingSession().select("l", "y").failed("x").cleared_error()
        assert s.state is S.IDENTIFIED
        assert s.error_message == ""


class TestImmutability:
    def test_with_returns_a_new_value(self):
        a = TrackModellingSession().select("l", "y")
        b = a.with_(has_segments=True)
        assert a.has_segments is False and b.has_segments is True

    def test_unknown_fields_are_ignored_rather_than_raising(self):
        a = TrackModellingSession()
        assert a.with_(not_a_field=1) is a
