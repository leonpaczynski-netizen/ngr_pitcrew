"""The track-modelling job as a guided flow (single-system stage 4b).

The classic Track Modelling tab shows fourteen sections at once — search, seed facts,
readiness, calibration, path building, station map, segment table, alignment, track
truth, resolver, refinement, lap offset, AI verify, file audit. Everything is visible
whether or not it applies, so the driver cannot tell what to do next.

The state machine underneath already knows. ``TrackModellingCoordinator`` defines six
steps, ten states and exactly one next message per state; this module turns that into
the view a guided page renders: where you are, what is happening, the ONE thing to do
next, and the legal escapes.

It invents nothing — every headline comes from the coordinator, and an action is only
offered when the coordinator says it is legal. Pure, no Qt, never raises.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Tuple

from data.track_modelling_coordinator import (
    TrackModellingAction as A,
    TrackModellingCoordinator,
    TrackModellingState as S,
    WorkflowStep,
)
from data.track_modelling_session import TrackModellingSession


#: The six steps, in order, each with what it is FOR in the driver's terms.
STEPS: Tuple[Tuple[WorkflowStep, str, str], ...] = (
    (WorkflowStep.IDENTIFY, "Pick the track",
     "Which circuit and layout are you modelling?"),
    (WorkflowStep.CAPTURE, "Drive it",
     "Clean laps so the app can learn the racing line."),
    (WorkflowStep.BUILD, "Build the model",
     "Turn those laps into a reference path and corner map."),
    (WorkflowStep.REVIEW, "Check the corners",
     "Confirm the detected corners match the real track."),
    (WorkflowStep.VALIDATE, "Validate",
     "Check the model lines up with the track before trusting it."),
    (WorkflowStep.ACTIVATE, "Use it",
     "Make it the model live features read."),
)

_STEP_ORDER = {step: i for i, (step, _t, _p) in enumerate(STEPS)}

#: What the driver is looking at, per state — plainer than the state name.
_HEADLINE = {
    S.NO_TRACK: "No track selected",
    S.IDENTIFIED: "Ready to drive",
    S.CAPTURING: "Recording your laps",
    S.CAPTURE_COMPLETE: "Laps captured",
    S.BUILDING: "Building the model",
    S.DRAFT_MODEL: "Corners detected",
    S.REVIEW_REQUIRED: "Some corners need a look",
    S.VALIDATED: "Model checks out",
    S.ACTIVE: "This track is modelled",
    S.ERROR: "That didn't work",
}

#: The ONE action offered per state, and how it reads on the button.
_PRIMARY = {
    S.IDENTIFIED: (A.START_CAPTURE, "Start recording laps"),
    S.CAPTURING: (A.STOP_CAPTURE, "Stop recording"),
    S.CAPTURE_COMPLETE: (A.BUILD_MODEL, "Build the model"),
    S.DRAFT_MODEL: (A.VALIDATE, "Validate the model"),
    S.REVIEW_REQUIRED: (A.VALIDATE, "Validate the model"),
    S.VALIDATED: (A.ACTIVATE, "Use this model"),
    S.ERROR: (A.RESET, "Start again"),
}

#: Escapes offered alongside the primary, when the coordinator allows them.
#: RESET is deliberately NOT here — it is the recovery action in ERROR, where it is the
#: PRIMARY. Offering "Start again" next to a working model, or before anything has
#: started, reads as a threat rather than a choice.
_SECONDARY_LABEL = {
    A.RECALIBRATE: "Re-record the laps",
    A.CLEAR_TRACK: "Pick a different track",
    A.START_CAPTURE: "Record more laps",
}

#: States where the driver is waiting on something rather than deciding.
_BUSY = frozenset({S.BUILDING, S.CAPTURING})


@dataclass(frozen=True)
class GuidedAction:
    action: str = ""
    label: str = ""


@dataclass(frozen=True)
class GuidedView:
    """Everything a guided track-modelling page renders."""
    state: str = S.NO_TRACK.value
    step: str = WorkflowStep.IDENTIFY.value
    step_index: int = 0
    step_title: str = ""
    step_purpose: str = ""
    headline: str = ""
    next_step: str = ""
    detail: str = ""
    primary: Optional[GuidedAction] = None
    secondary: Tuple[GuidedAction, ...] = field(default_factory=tuple)
    busy: bool = False
    done: bool = False
    #: True only where the step's own controls are the point (track pickers, the
    #: corner list). Everything else is a headline and one button.
    shows_track_picker: bool = False
    shows_capture_status: bool = False
    shows_corner_list: bool = False

    @property
    def total_steps(self) -> int:
        return len(STEPS)


def build_guided_view(session: Optional[TrackModellingSession]) -> GuidedView:
    """The guided view for a modelling session. Never raises."""
    try:
        return _build(session if isinstance(session, TrackModellingSession)
                      else TrackModellingSession())
    except Exception:  # pragma: no cover - defensive
        return GuidedView()


def _build(session: TrackModellingSession) -> GuidedView:
    # The coordinator is the authority on state, step, the next message and which
    # actions are legal. This module only decides how to SAY it.
    coordinator = TrackModellingCoordinator(session.to_inputs())
    snap = coordinator.snapshot(error_message=session.error_message)
    state, step = snap.state, snap.step
    index = _STEP_ORDER.get(step, 0)
    title, purpose = "", ""
    for s, t, p in STEPS:
        if s is step:
            title, purpose = t, p
            break

    legal = set(snap.available_actions)
    primary = None
    if state in _PRIMARY:
        action, label = _PRIMARY[state]
        if action in legal:
            primary = GuidedAction(action.value, label)

    secondary = []
    for action, label in _SECONDARY_LABEL.items():
        if action in legal and (primary is None or action.value != primary.action):
            secondary.append(GuidedAction(action.value, label))

    return GuidedView(
        state=state.value, step=step.value, step_index=index,
        step_title=title, step_purpose=purpose,
        headline=_HEADLINE.get(state, ""),
        next_step=snap.primary_next_step,
        detail=session.error_message if state is S.ERROR else "",
        primary=primary, secondary=tuple(secondary),
        busy=state in _BUSY,
        done=state is S.ACTIVE,
        shows_track_picker=state in (S.NO_TRACK, S.IDENTIFIED, S.ERROR),
        shows_capture_status=state in (S.CAPTURING, S.CAPTURE_COMPLETE),
        shows_corner_list=state in (S.DRAFT_MODEL, S.REVIEW_REQUIRED, S.VALIDATED),
    )


def step_states(session: Optional[TrackModellingSession]) -> Tuple[Tuple[str, str], ...]:
    """(step title, "done"|"current"|"todo") for the progress rail."""
    view = build_guided_view(session)
    out = []
    for i, (_s, title, _p) in enumerate(STEPS):
        if view.done:
            status = "done"
        elif i < view.step_index:
            status = "done"
        elif i == view.step_index:
            status = "current"
        else:
            status = "todo"
        out.append((title, status))
    return tuple(out)
