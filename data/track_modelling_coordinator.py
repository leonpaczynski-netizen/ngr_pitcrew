"""Canonical Track Modelling workflow coordinator (pure, Qt-free).

UAT Finding 4. Track Modelling state used to be scattered across ~15
``_tm_*`` attributes on the UI mixin, mutated directly in button handlers, with
no single notion of "where am I in the workflow" and no enforcement of which
actions are legal. Illegal actions failed silently or half-ran.

This module introduces ONE canonical state machine over the guided six-step
workflow (Identify → Capture → Build → Review → Validate → Activate) and a
single result object every surface can read (map rendering, segment review,
Live Race Engineer, Practice Analysis, corner identity).

Design:
  * ``TrackModellingState`` — the 10 canonical states.
  * ``TrackModellingAction`` — the user/async actions that drive transitions.
  * ``WorkflowStep`` — the six guided steps the UI walks the user through.
  * ``TrackModellingInputs`` — the external truth (identity resolved? capture
    state? which artifacts exist? validation passed? model active?) derived from
    the existing readiness/capture/alignment/review layers.
  * ``derive_state`` — maps inputs → canonical state, so selecting a track with
    an approved model on disk lands directly in ACTIVE (auto-load), and a fresh
    track lands in IDENTIFIED.
  * ``TrackModellingCoordinator`` — holds the state, exposes the legal actions
    (a static transition table intersected with data-readiness preconditions),
    and refuses illegal actions loudly (``IllegalTrackModellingAction``) so the
    UI can *disable* them rather than let them half-run.

Pure and deterministic: no Qt, no file I/O. The UI mixin builds
``TrackModellingInputs`` from disk audits and feeds them in.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Optional, Tuple


class TrackModellingState(str, Enum):
    NO_TRACK = "no_track"
    IDENTIFIED = "identified"
    CAPTURING = "capturing"
    CAPTURE_COMPLETE = "capture_complete"
    BUILDING = "building"
    DRAFT_MODEL = "draft_model"
    REVIEW_REQUIRED = "review_required"
    VALIDATED = "validated"
    ACTIVE = "active"
    ERROR = "error"


class TrackModellingAction(str, Enum):
    SELECT_TRACK = "select_track"       # (re)identify the track/layout
    CLEAR_TRACK = "clear_track"
    START_CAPTURE = "start_capture"
    STOP_CAPTURE = "stop_capture"
    BUILD_MODEL = "build_model"         # start the (async) build
    BUILD_SUCCEEDED = "build_succeeded"  # async completion
    BUILD_FAILED = "build_failed"        # async completion
    EDIT_SEGMENT = "edit_segment"        # rename/renumber/merge/split/reject/approve
    VALIDATE = "validate"
    ACTIVATE = "activate"
    RECALIBRATE = "recalibrate"
    RESET = "reset"
    FAIL = "fail"


class WorkflowStep(str, Enum):
    IDENTIFY = "identify"
    CAPTURE = "capture"
    BUILD = "build"
    REVIEW = "review"
    VALIDATE = "validate"
    ACTIVATE = "activate"


# Which guided step each state belongs to.
_STATE_STEP: Dict[TrackModellingState, WorkflowStep] = {
    TrackModellingState.NO_TRACK: WorkflowStep.IDENTIFY,
    TrackModellingState.IDENTIFIED: WorkflowStep.CAPTURE,
    TrackModellingState.CAPTURING: WorkflowStep.CAPTURE,
    TrackModellingState.CAPTURE_COMPLETE: WorkflowStep.BUILD,
    TrackModellingState.BUILDING: WorkflowStep.BUILD,
    TrackModellingState.DRAFT_MODEL: WorkflowStep.REVIEW,
    TrackModellingState.REVIEW_REQUIRED: WorkflowStep.REVIEW,
    TrackModellingState.VALIDATED: WorkflowStep.VALIDATE,
    TrackModellingState.ACTIVE: WorkflowStep.ACTIVATE,
    TrackModellingState.ERROR: WorkflowStep.IDENTIFY,
}


# The single primary next-step message per state (UI shows one at a time).
_NEXT_STEP: Dict[TrackModellingState, str] = {
    TrackModellingState.NO_TRACK: "Select the track and layout you're modelling.",
    TrackModellingState.IDENTIFIED: "Start calibration and drive clean laps to capture the track.",
    TrackModellingState.CAPTURING: "Drive clean laps, then stop calibration when you have enough.",
    TrackModellingState.CAPTURE_COMPLETE: "Build the track model from the captured laps.",
    TrackModellingState.BUILDING: "Building the model…",
    TrackModellingState.DRAFT_MODEL: "Review the detected corners and segments.",
    TrackModellingState.REVIEW_REQUIRED: "Resolve the flagged segments, then validate the model.",
    TrackModellingState.VALIDATED: "Activate the validated model so live features use it.",
    TrackModellingState.ACTIVE: "Model is active. Recalibrate only if the track feels wrong.",
    TrackModellingState.ERROR: "Something went wrong — reset and reselect the track to try again.",
}


# Static legal transition table: state -> {action -> next state}.
# Every state additionally allows SELECT_TRACK (re-derive) and RESET; those are
# injected in ``_legal_targets`` rather than repeated here.
_TRANSITIONS: Dict[TrackModellingState, Dict[TrackModellingAction, TrackModellingState]] = {
    TrackModellingState.NO_TRACK: {
        TrackModellingAction.SELECT_TRACK: TrackModellingState.IDENTIFIED,
    },
    TrackModellingState.IDENTIFIED: {
        TrackModellingAction.START_CAPTURE: TrackModellingState.CAPTURING,
        TrackModellingAction.CLEAR_TRACK: TrackModellingState.NO_TRACK,
    },
    TrackModellingState.CAPTURING: {
        TrackModellingAction.STOP_CAPTURE: TrackModellingState.CAPTURE_COMPLETE,
        TrackModellingAction.FAIL: TrackModellingState.ERROR,
    },
    TrackModellingState.CAPTURE_COMPLETE: {
        TrackModellingAction.BUILD_MODEL: TrackModellingState.BUILDING,
        TrackModellingAction.START_CAPTURE: TrackModellingState.CAPTURING,
    },
    TrackModellingState.BUILDING: {
        TrackModellingAction.BUILD_SUCCEEDED: TrackModellingState.DRAFT_MODEL,
        TrackModellingAction.BUILD_FAILED: TrackModellingState.ERROR,
        TrackModellingAction.FAIL: TrackModellingState.ERROR,
    },
    TrackModellingState.DRAFT_MODEL: {
        TrackModellingAction.EDIT_SEGMENT: TrackModellingState.REVIEW_REQUIRED,
        TrackModellingAction.VALIDATE: TrackModellingState.VALIDATED,
        TrackModellingAction.RECALIBRATE: TrackModellingState.CAPTURING,
    },
    TrackModellingState.REVIEW_REQUIRED: {
        TrackModellingAction.EDIT_SEGMENT: TrackModellingState.REVIEW_REQUIRED,
        TrackModellingAction.VALIDATE: TrackModellingState.VALIDATED,
        TrackModellingAction.RECALIBRATE: TrackModellingState.CAPTURING,
    },
    TrackModellingState.VALIDATED: {
        TrackModellingAction.ACTIVATE: TrackModellingState.ACTIVE,
        TrackModellingAction.EDIT_SEGMENT: TrackModellingState.REVIEW_REQUIRED,
        TrackModellingAction.FAIL: TrackModellingState.ERROR,
    },
    TrackModellingState.ACTIVE: {
        TrackModellingAction.RECALIBRATE: TrackModellingState.CAPTURING,
        TrackModellingAction.EDIT_SEGMENT: TrackModellingState.REVIEW_REQUIRED,
    },
    TrackModellingState.ERROR: {
        TrackModellingAction.RESET: TrackModellingState.NO_TRACK,
    },
}


class IllegalTrackModellingAction(Exception):
    """Raised when an action is dispatched that is not legal in the current state."""


@dataclass(frozen=True)
class TrackModellingInputs:
    """External truth the coordinator derives its state from.

    Built by the UI from the existing disk audit / readiness / capture /
    alignment / review layers — the coordinator never touches disk itself.
    """
    identity_known: bool = False
    capturing: bool = False
    has_captured_laps: bool = False
    has_reference_path: bool = False
    has_station_map: bool = False
    has_segments: bool = False
    review_complete: bool = False      # all flagged segments resolved (AI-ready)
    validation_passed: bool = False
    model_active: bool = False         # an approved/accepted model is active on disk
    building: bool = False
    error: bool = False


def derive_state(inp: TrackModellingInputs) -> TrackModellingState:
    """Map external truth to the canonical state.

    Auto-load: an active approved model lands directly in ACTIVE; a fresh
    identified track lands in IDENTIFIED. This is what makes selecting a track
    with an approved model on disk skip straight to "active" without manual steps.
    """
    if inp.error:
        return TrackModellingState.ERROR
    if not inp.identity_known:
        return TrackModellingState.NO_TRACK
    if inp.model_active:
        return TrackModellingState.ACTIVE
    if inp.building:
        return TrackModellingState.BUILDING
    if inp.capturing:
        return TrackModellingState.CAPTURING
    # Has a built model (reference path or station map + segments)?
    if inp.has_segments or inp.has_station_map or inp.has_reference_path:
        if inp.validation_passed:
            return TrackModellingState.VALIDATED
        if inp.has_segments and not inp.review_complete:
            return TrackModellingState.REVIEW_REQUIRED
        if inp.has_segments and inp.review_complete:
            return TrackModellingState.DRAFT_MODEL
        # Reference path / station map only, corners not detected yet.
        return TrackModellingState.DRAFT_MODEL
    if inp.has_captured_laps:
        return TrackModellingState.CAPTURE_COMPLETE
    return TrackModellingState.IDENTIFIED


def _preconditions_ok(action: TrackModellingAction, inp: TrackModellingInputs) -> bool:
    """Data-readiness gate on top of the static state table."""
    if action is TrackModellingAction.BUILD_MODEL:
        return inp.has_captured_laps or inp.has_reference_path
    if action is TrackModellingAction.EDIT_SEGMENT:
        return inp.has_segments
    if action is TrackModellingAction.VALIDATE:
        return inp.has_segments or inp.has_reference_path or inp.has_station_map
    if action is TrackModellingAction.ACTIVATE:
        return inp.validation_passed
    return True


@dataclass(frozen=True)
class TrackModellingSnapshot:
    """The single canonical result object every Track Modelling surface reads."""
    state: TrackModellingState
    step: WorkflowStep
    available_actions: Tuple[TrackModellingAction, ...]
    primary_next_step: str
    identity_label: str = ""
    confidence: str = "none"           # high | medium | low | none
    blocked_reason: str = ""
    error_message: str = ""

    def can(self, action: TrackModellingAction) -> bool:
        return action in self.available_actions


class TrackModellingCoordinator:
    """Owns the canonical Track Modelling state and enforces legal transitions."""

    def __init__(self, inputs: Optional[TrackModellingInputs] = None):
        self._inputs = inputs or TrackModellingInputs()
        self._state = derive_state(self._inputs)

    # ------------------------------------------------------------------ state
    @property
    def state(self) -> TrackModellingState:
        return self._state

    @property
    def inputs(self) -> TrackModellingInputs:
        return self._inputs

    @property
    def step(self) -> WorkflowStep:
        return _STATE_STEP[self._state]

    def sync_from_inputs(self, inputs: TrackModellingInputs) -> TrackModellingState:
        """Re-derive the state from fresh external truth (e.g. after selecting a
        track, finishing a build, or editing segments). This is how an approved
        model auto-loads to ACTIVE on selection."""
        self._inputs = inputs
        self._state = derive_state(inputs)
        return self._state

    # ---------------------------------------------------------------- actions
    def _legal_targets(self) -> Dict[TrackModellingAction, TrackModellingState]:
        targets = dict(_TRANSITIONS.get(self._state, {}))
        # SELECT_TRACK and RESET are always legal (re-identify / recover).
        targets.setdefault(TrackModellingAction.SELECT_TRACK, TrackModellingState.IDENTIFIED)
        targets.setdefault(TrackModellingAction.RESET, TrackModellingState.NO_TRACK)
        return targets

    def available_actions(self) -> Tuple[TrackModellingAction, ...]:
        """Actions that are BOTH legal in this state AND have their data
        preconditions met — everything else the UI must disable."""
        out = []
        for action in self._legal_targets():
            if _preconditions_ok(action, self._inputs):
                out.append(action)
        # Stable ordering by enum definition order.
        order = list(TrackModellingAction)
        out.sort(key=order.index)
        return tuple(out)

    def can(self, action: TrackModellingAction) -> bool:
        return action in self.available_actions()

    def dispatch(self, action: TrackModellingAction) -> TrackModellingState:
        """Apply an action. Raises IllegalTrackModellingAction if it is not
        currently available (illegal in this state, or preconditions unmet)."""
        if not self.can(action):
            raise IllegalTrackModellingAction(
                f"Action {action.value!r} is not legal in state {self._state.value!r}")
        self._state = self._legal_targets()[action]
        return self._state

    # ---------------------------------------------------------------- snapshot
    def snapshot(self, *, identity_label: str = "", confidence: str = "none",
                error_message: str = "") -> TrackModellingSnapshot:
        blocked = ""
        if self._state is TrackModellingState.ERROR:
            blocked = error_message or "The workflow hit an error."
        return TrackModellingSnapshot(
            state=self._state,
            step=self.step,
            available_actions=self.available_actions(),
            primary_next_step=_NEXT_STEP.get(self._state, ""),
            identity_label=identity_label,
            confidence=confidence,
            blocked_reason=blocked,
            error_message=error_message,
        )
