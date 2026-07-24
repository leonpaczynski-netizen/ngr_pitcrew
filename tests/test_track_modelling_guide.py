"""Track modelling as a guided flow (single-system stage 4b).

The classic tab showed fourteen sections at once whether or not they applied, so nothing
told the driver what to do next. The state machine already knew — these tests pin that
the guide says exactly what it says, and never offers an action it has not allowed.
"""

from data.track_modelling_coordinator import TrackModellingAction as A
from data.track_modelling_guide import STEPS, build_guided_view, step_states
from data.track_modelling_session import TrackModellingSession


def _sel(**kw):
    return TrackModellingSession().select("watkins_glen", "long_course").with_(**kw)


class TestSixSteps:
    def test_the_flow_is_six_named_steps(self):
        titles = [t for _s, t, _p in STEPS]
        assert titles == ["Pick the track", "Drive it", "Build the model",
                          "Check the corners", "Validate", "Use it"]

    def test_every_step_says_what_it_is_for(self):
        assert all(purpose for _s, _t, purpose in STEPS)

    def test_the_progress_rail_marks_done_current_and_todo(self):
        states = dict(step_states(_sel(has_captured_laps=True)))
        assert states["Pick the track"] == "done"
        assert states["Build the model"] == "current"
        assert states["Use it"] == "todo"

    def test_a_finished_model_shows_every_step_done(self):
        assert {s for _t, s in step_states(_sel(model_active=True))} == {"done"}


class TestOneStepAtATime:
    def test_nothing_selected_asks_for_a_track_and_offers_no_actions(self):
        v = build_guided_view(TrackModellingSession())
        assert v.step_index == 0
        assert v.shows_track_picker is True
        assert v.primary is None
        assert v.secondary == ()          # nothing has started; nothing to escape from
        assert "Select the track" in v.next_step

    def test_a_selected_track_asks_you_to_drive(self):
        v = build_guided_view(_sel())
        assert v.step_title == "Drive it"
        assert v.primary.action == A.START_CAPTURE.value
        assert v.primary.label == "Start recording laps"
        assert [a.label for a in v.secondary] == ["Pick a different track"]

    def test_recording_offers_only_stopping(self):
        v = build_guided_view(_sel(capturing=True))
        assert v.primary.action == A.STOP_CAPTURE.value
        assert v.busy is True
        assert v.shows_capture_status is True

    def test_captured_laps_ask_for_a_build(self):
        v = build_guided_view(_sel(has_captured_laps=True))
        assert v.step_title == "Build the model"
        assert v.primary.action == A.BUILD_MODEL.value
        assert "Record more laps" in [a.label for a in v.secondary]

    def test_detected_corners_ask_to_be_checked(self):
        v = build_guided_view(_sel(has_segments=True))
        assert v.step_title == "Check the corners"
        assert v.shows_corner_list is True
        assert v.primary.action == A.VALIDATE.value

    def test_a_validated_model_asks_to_be_used(self):
        v = build_guided_view(_sel(has_segments=True, review_complete=True,
                                   validation_passed=True))
        assert v.step_title == "Validate"
        assert v.primary.action == A.ACTIVATE.value
        assert v.primary.label == "Use this model"

    def test_an_active_model_is_done_and_asks_nothing(self):
        v = build_guided_view(_sel(model_active=True))
        assert v.done is True
        assert v.primary is None
        assert v.headline == "This track is modelled"


class TestOnlyLegalActionsAreOffered:
    def test_the_guide_never_offers_what_the_coordinator_forbids(self):
        """Every action the guide shows must be one the coordinator allows."""
        from data.track_modelling_coordinator import TrackModellingCoordinator
        for session in (TrackModellingSession(), _sel(), _sel(capturing=True),
                        _sel(has_captured_laps=True), _sel(has_segments=True),
                        _sel(has_segments=True, review_complete=True,
                             validation_passed=True),
                        _sel(model_active=True), _sel().failed("x")):
            view = build_guided_view(session)
            allowed = {a.value for a in
                       TrackModellingCoordinator(session.to_inputs()).available_actions()}
            offered = {a.action for a in view.secondary}
            if view.primary:
                offered.add(view.primary.action)
            assert offered <= allowed, view.state

    def test_start_again_is_never_offered_beside_a_working_model(self):
        """RESET is the recovery action in ERROR, where it is the PRIMARY. Beside a
        finished model it reads as a threat, not a choice."""
        labels = [a.label for a in build_guided_view(_sel(model_active=True)).secondary]
        assert "Start again" not in labels

    def test_start_again_is_not_offered_before_anything_has_started(self):
        labels = [a.label for a in build_guided_view(TrackModellingSession()).secondary]
        assert "Start again" not in labels


class TestErrors:
    def test_an_error_says_what_went_wrong_and_how_to_recover(self):
        v = build_guided_view(_sel().failed("no usable laps"))
        assert v.headline == "That didn't work"
        assert v.detail == "no usable laps"
        assert v.primary.action == A.RESET.value
        assert v.primary.label == "Start again"

    def test_the_error_step_returns_to_the_beginning(self):
        assert build_guided_view(_sel().failed("x")).step_index == 0


class TestNeverRaises:
    def test_garbage_yields_the_first_step_rather_than_an_error(self):
        v = build_guided_view(None)
        assert v.step_index == 0
        assert v.total_steps == 6
