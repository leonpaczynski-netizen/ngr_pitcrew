"""Track Truth Calibration Wizard — Group 18A.

Multi-stage wizard controller for capturing geometry sessions and building a
validated TrackTruthModel from centreline + edge calibration runs.

Pure Python — no PyQt6 dependency.

Wizard stage transitions
------------------------
NOT_STARTED → CAPTURE_CENTRELINE (when track_id + layout_id set)
CAPTURE_CENTRELINE → CAPTURE_LEFT_EDGE (centreline_session set)
CAPTURE_LEFT_EDGE → CAPTURE_RIGHT_EDGE (left_edge_session set)
CAPTURE_RIGHT_EDGE → OPTIONAL_HOT_LAP (right_edge_session set)
CAPTURE_RIGHT_EDGE → BUILD_PROPOSED (skip hot lap)
OPTIONAL_HOT_LAP → BUILD_PROPOSED
BUILD_PROPOSED → VALIDATE (build_result.can_generate is True)
VALIDATE → ACCEPT (validation_result.is_accepted is True)
VALIDATE → CAPTURE_CENTRELINE (retry)
ACCEPT → NOT_STARTED (reset)
ANY → NOT_STARTED via abandon()

Public API
----------
TrackTruthWizardStage   (str, Enum)
TrackTruthWizardState   (dataclass)
TrackTruthCalibrationWizard (controller class)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional

from data.track_truth import (
    TrackTruthModel,
    TrackTruthValidationResult,
    validate_track_truth_model,
)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class TrackTruthWizardStage(str, Enum):
    NOT_STARTED       = "NOT_STARTED"
    CAPTURE_CENTRELINE = "CAPTURE_CENTRELINE"
    CAPTURE_LEFT_EDGE  = "CAPTURE_LEFT_EDGE"
    CAPTURE_RIGHT_EDGE = "CAPTURE_RIGHT_EDGE"
    OPTIONAL_HOT_LAP   = "OPTIONAL_HOT_LAP"
    BUILD_PROPOSED     = "BUILD_PROPOSED"
    VALIDATE           = "VALIDATE"
    ACCEPT             = "ACCEPT"


# ---------------------------------------------------------------------------
# State dataclass
# ---------------------------------------------------------------------------

@dataclass
class TrackTruthWizardState:
    """Mutable state carried through the calibration wizard stages."""
    stage:             TrackTruthWizardStage  = TrackTruthWizardStage.NOT_STARTED
    track_id:          str                    = ""
    layout_id:         str                    = ""
    centreline_session: Optional[Any]         = None
    left_edge_session:  Optional[Any]         = None
    right_edge_session: Optional[Any]         = None
    hot_lap_session:    Optional[Any]         = None
    build_result:       Optional[Any]         = None
    validation_result:  Optional[TrackTruthValidationResult] = None
    proposed_model:     Optional[TrackTruthModel]            = None
    error:              str                   = ""


# ---------------------------------------------------------------------------
# Defensive geometry build wrapper
# ---------------------------------------------------------------------------

def _build_geometry_safe(
    centreline_session: Any,
    track_id: str,
    layout_id: str,
    manifest_lap_length_m: float,
) -> Any:
    """Wrap build_seed_geometry from data/track_geometry_builder in try/except.

    Returns a GeometryBuildResult on success, or a failure-shaped object
    (can_generate=False) on any error.  Never raises.
    """
    try:
        from data.track_geometry_builder import build_seed_geometry, GeometryBuildResult
        result = build_seed_geometry(
            session               = centreline_session,
            manifest_lap_length_m = manifest_lap_length_m,
            track_location_id     = track_id,
            layout_id             = layout_id,
        )
        return result
    except Exception as exc:
        # Return a failure object that has the minimal shape callers expect
        class _FailResult:
            can_generate         = False
            seed_map             = None
            accepted_lap_indices = []
            rejected_laps        = []
            confidence           = "low"
            station_count        = 0
            closure_gap_m        = 0.0
            error_detail         = str(exc)

        return _FailResult()


# ---------------------------------------------------------------------------
# Wizard controller
# ---------------------------------------------------------------------------

class TrackTruthCalibrationWizard:
    """Controller for the Track Truth calibration wizard.

    Usage::

        wizard = TrackTruthCalibrationWizard()
        wizard.start("daytona_international_speedway",
                     "daytona_international_speedway__road_course")
        wizard.set_centreline_session(session_obj)
        wizard.advance()   # → CAPTURE_LEFT_EDGE
        ...
        wizard.validate()
        wizard.accept()
    """

    def __init__(self) -> None:
        self.state = TrackTruthWizardState()

    # ── Setters ────────────────────────────────────────────────────────────

    def set_centreline_session(self, session: Any) -> None:
        """Store the centreline calibration session."""
        self.state.centreline_session = session
        self.state.error = ""

    def set_left_edge_session(self, session: Any) -> None:
        """Store the left-edge calibration session."""
        self.state.left_edge_session = session
        self.state.error = ""

    def set_right_edge_session(self, session: Any) -> None:
        """Store the right-edge calibration session."""
        self.state.right_edge_session = session
        self.state.error = ""

    def set_hot_lap_session(self, session: Any) -> None:
        """Store the optional hot-lap session."""
        self.state.hot_lap_session = session
        self.state.error = ""

    # ── Start ──────────────────────────────────────────────────────────────

    def start(self, track_id: str, layout_id: str) -> TrackTruthWizardState:
        """Initialise the wizard for a specific track/layout.

        Transitions NOT_STARTED → CAPTURE_CENTRELINE when both IDs are non-empty.
        Returns the current state.
        """
        if not track_id or not layout_id:
            self.state.error = "track_id and layout_id must both be non-empty to start"
            return self.state

        self.state.track_id  = track_id
        self.state.layout_id = layout_id
        self.state.error = ""

        if self.state.stage == TrackTruthWizardStage.NOT_STARTED:
            self.state.stage = TrackTruthWizardStage.CAPTURE_CENTRELINE

        return self.state

    # ── Advance ────────────────────────────────────────────────────────────

    def advance(self, target_stage: Optional[TrackTruthWizardStage] = None) -> TrackTruthWizardState:
        """Advance to the next (or a specified target) wizard stage.

        Illegal transitions are a no-op — state.stage is left unchanged and
        state.error is set to a descriptive message.
        """
        current = self.state.stage
        self.state.error = ""

        # Determine where we want to go
        if target_stage is not None:
            desired = target_stage
        else:
            # Default next-stage map
            _next = {
                TrackTruthWizardStage.NOT_STARTED:        TrackTruthWizardStage.CAPTURE_CENTRELINE,
                TrackTruthWizardStage.CAPTURE_CENTRELINE: TrackTruthWizardStage.CAPTURE_LEFT_EDGE,
                TrackTruthWizardStage.CAPTURE_LEFT_EDGE:  TrackTruthWizardStage.CAPTURE_RIGHT_EDGE,
                TrackTruthWizardStage.CAPTURE_RIGHT_EDGE: TrackTruthWizardStage.OPTIONAL_HOT_LAP,
                TrackTruthWizardStage.OPTIONAL_HOT_LAP:   TrackTruthWizardStage.BUILD_PROPOSED,
                TrackTruthWizardStage.BUILD_PROPOSED:      TrackTruthWizardStage.VALIDATE,
                TrackTruthWizardStage.VALIDATE:            TrackTruthWizardStage.ACCEPT,
                TrackTruthWizardStage.ACCEPT:              TrackTruthWizardStage.NOT_STARTED,
            }
            desired = _next.get(current, current)

        ok, msg = self._check_transition(current, desired)
        if not ok:
            self.state.error = msg
            return self.state

        # VALIDATE→ACCEPT must always go through accept() so geometry is persisted
        if desired == TrackTruthWizardStage.ACCEPT:
            return self.accept()

        self.state.stage = desired
        return self.state

    def _check_transition(
        self,
        frm: TrackTruthWizardStage,
        to:  TrackTruthWizardStage,
    ) -> tuple:
        """Return (True, "") if the transition is legal, else (False, reason)."""
        S = TrackTruthWizardStage
        s = self.state

        # Enumerate legal transitions and their pre-conditions
        if frm == S.NOT_STARTED and to == S.CAPTURE_CENTRELINE:
            if not s.track_id or not s.layout_id:
                return False, "Cannot start: track_id and layout_id must be set"
            return True, ""

        if frm == S.CAPTURE_CENTRELINE and to == S.CAPTURE_LEFT_EDGE:
            if s.centreline_session is None:
                return False, "Cannot advance: centreline_session is not set"
            return True, ""

        if frm == S.CAPTURE_LEFT_EDGE and to == S.CAPTURE_RIGHT_EDGE:
            if s.left_edge_session is None:
                return False, "Cannot advance: left_edge_session is not set"
            return True, ""

        if frm == S.CAPTURE_RIGHT_EDGE and to == S.OPTIONAL_HOT_LAP:
            if s.right_edge_session is None:
                return False, "Cannot advance: right_edge_session is not set"
            return True, ""

        if frm == S.CAPTURE_RIGHT_EDGE and to == S.BUILD_PROPOSED:
            # Skipping hot lap
            if s.right_edge_session is None:
                return False, "Cannot skip to BUILD_PROPOSED: right_edge_session is not set"
            return True, ""

        if frm == S.OPTIONAL_HOT_LAP and to == S.BUILD_PROPOSED:
            return True, ""

        if frm == S.BUILD_PROPOSED and to == S.VALIDATE:
            if s.build_result is None:
                return False, "Cannot advance to VALIDATE: build() has not been run yet"
            if not getattr(s.build_result, "can_generate", False):
                return False, "Cannot advance to VALIDATE: build_result.can_generate is False"
            return True, ""

        if frm == S.VALIDATE and to == S.ACCEPT:
            if s.validation_result is None:
                return False, "Cannot advance to ACCEPT: validate() has not been run"
            if not s.validation_result.is_accepted:
                return False, "Cannot advance to ACCEPT: validation_result.is_accepted is False"
            return True, ""

        if frm == S.VALIDATE and to == S.CAPTURE_CENTRELINE:
            # Retry path
            return True, ""

        if frm == S.ACCEPT and to == S.NOT_STARTED:
            return True, ""

        return (
            False,
            f"Illegal transition {frm.value} → {to.value}",
        )

    # ── Skip hot lap convenience ───────────────────────────────────────────

    def skip_hot_lap(self) -> TrackTruthWizardState:
        """Advance from CAPTURE_RIGHT_EDGE directly to BUILD_PROPOSED (skip hot lap)."""
        return self.advance(target_stage=TrackTruthWizardStage.BUILD_PROPOSED)

    # ── Build ──────────────────────────────────────────────────────────────

    def build(self, manifest_lap_length_m: float = 0.0) -> TrackTruthWizardState:
        """Run geometry build at BUILD_PROPOSED stage.

        Uses the centreline session to generate a SeedCoordinateMap via the
        defensive wrapper _build_geometry_safe (wraps track_geometry_builder).
        On success, stores build_result and advances to VALIDATE if can_generate.
        On failure, sets state.error but does not raise.
        """
        if self.state.stage != TrackTruthWizardStage.BUILD_PROPOSED:
            self.state.error = (
                f"build() called from wrong stage ({self.state.stage.value}); "
                f"must be at BUILD_PROPOSED"
            )
            return self.state

        if self.state.centreline_session is None:
            self.state.error = "build() called but centreline_session is None"
            return self.state

        result = _build_geometry_safe(
            centreline_session    = self.state.centreline_session,
            track_id              = self.state.track_id,
            layout_id             = self.state.layout_id,
            manifest_lap_length_m = manifest_lap_length_m,
        )
        self.state.build_result = result

        if not getattr(result, "can_generate", False):
            err = getattr(result, "error_detail", "")
            self.state.error = f"Geometry build failed: {err}" if err else "Geometry build failed"
        else:
            self.state.error = ""

        return self.state

    # ── Validate ───────────────────────────────────────────────────────────

    def validate(self) -> TrackTruthWizardState:
        """Run validate_track_truth_model on proposed_model at VALIDATE stage.

        Stores the result in state.validation_result.
        No-op (with error set) if called from wrong stage or no proposed_model.
        """
        if self.state.stage != TrackTruthWizardStage.VALIDATE:
            self.state.error = (
                f"validate() called from wrong stage ({self.state.stage.value}); "
                f"must be at VALIDATE"
            )
            return self.state

        if self.state.proposed_model is None:
            self.state.error = "validate() called but proposed_model is None"
            return self.state

        try:
            result = validate_track_truth_model(self.state.proposed_model)
            self.state.validation_result = result
            self.state.error = ""
        except Exception as exc:
            self.state.error = f"Validation error: {exc}"

        return self.state

    # ── Accept ─────────────────────────────────────────────────────────────

    def accept(self, base_dir: Optional[Path] = None) -> TrackTruthWizardState:
        """Persist the accepted model to the track library.

        Only allowed when validation_result.is_accepted is True.
        Calls save_seed_geometry_to_library from track_geometry_builder.
        On failure, sets state.error — does not crash.
        No partial writes when validation fails.
        """
        if self.state.stage != TrackTruthWizardStage.VALIDATE:
            self.state.error = (
                f"accept() called from wrong stage ({self.state.stage.value}); "
                f"must be at VALIDATE"
            )
            return self.state

        if (
            self.state.validation_result is None
            or not self.state.validation_result.is_accepted
        ):
            self.state.error = "Cannot accept: validation has not passed (is_accepted is False)"
            return self.state

        # Retrieve the seed_map from build_result for persistence
        seed_map = None
        if self.state.build_result is not None:
            seed_map = getattr(self.state.build_result, "seed_map", None)

        if seed_map is not None:
            try:
                from data.track_geometry_builder import save_seed_geometry_to_library
                save_result = save_seed_geometry_to_library(
                    seed_map   = seed_map,
                    track_id   = self.state.track_id,
                    layout_id  = self.state.layout_id,
                    base_dir   = base_dir,
                )
                if save_result.error:
                    self.state.error = f"Save failed: {save_result.error}"
                    return self.state
            except Exception as exc:
                self.state.error = f"Accept/save error: {exc}"
                return self.state

        # Transition to ACCEPT
        self.state.stage = TrackTruthWizardStage.ACCEPT
        self.state.error = ""
        return self.state

    # ── Abandon ────────────────────────────────────────────────────────────

    def abandon(self) -> TrackTruthWizardState:
        """Reset the wizard to NOT_STARTED from any stage.

        Clears all session data, build/validation results, proposed model, and error.
        Does not write any files.
        """
        self.state.stage              = TrackTruthWizardStage.NOT_STARTED
        self.state.centreline_session = None
        self.state.left_edge_session  = None
        self.state.right_edge_session = None
        self.state.hot_lap_session    = None
        self.state.build_result       = None
        self.state.validation_result  = None
        self.state.proposed_model     = None
        self.state.error              = ""
        return self.state

    # ── Backwards-compat hook ─────────────────────────────────────────────

    def review_segments(self) -> None:
        """Backwards-compatibility hook for segment review UI.

        Callable at BUILD_PROPOSED or VALIDATE stages; no-op elsewhere.
        """
        valid_stages = {
            TrackTruthWizardStage.BUILD_PROPOSED,
            TrackTruthWizardStage.VALIDATE,
        }
        if self.state.stage not in valid_stages:
            return   # no-op outside relevant stages
        # No logic required — hook exists for future UI to attach behaviour
