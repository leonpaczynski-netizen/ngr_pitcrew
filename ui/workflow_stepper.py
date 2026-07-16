"""Guided workflow stepper state — "follow the bouncing ball" (pure, Qt-free).

Sprint 10 of the determinism rebuild. The 12-stage engineering journey existed
only as static data; nothing computed, at any moment, where the driver is, what
is done, what is blocked, and the single next action. This module turns the
canonical state (event/car, track readiness, saved-vs-applied setup, practice
evidence, driver feedback, the engineering decision, strategy readiness) into an
explicit stepper the UI renders.

Pure and deterministic: no Qt, no I/O. The Qt layer maps ``WorkflowState`` to a
stepper widget and a single prominent "next action" button.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional, Tuple


class StageStatus(str, Enum):
    DONE = "done"
    CURRENT = "current"
    BLOCKED = "blocked"
    PENDING = "pending"


@dataclass(frozen=True)
class WorkflowStage:
    index: int
    key: str
    title: str
    status: StageStatus
    detail: str = ""
    blocker: str = ""
    next_action: str = ""


@dataclass(frozen=True)
class WorkflowState:
    stages: Tuple[WorkflowStage, ...]
    current_index: int
    next_action: str
    next_tab: str = ""

    @property
    def done_count(self) -> int:
        return sum(1 for s in self.stages if s.status is StageStatus.DONE)

    @property
    def total(self) -> int:
        return len(self.stages)

    @property
    def complete(self) -> bool:
        return self.done_count == self.total

    def stage(self, key: str) -> Optional[WorkflowStage]:
        for s in self.stages:
            if s.key == key:
                return s
        return None


@dataclass(frozen=True)
class WorkflowInputs:
    """Booleans + light context describing the current engineering state."""
    event_ready: bool = False           # car + track + rules selected
    track_ready: bool = False           # TrackReadinessResult.is_ready
    track_blocker: str = ""             # readiness blocker text when not ready
    setup_saved: bool = False           # a setup exists / saved in Pit Crew
    setup_applied_in_gt7: bool = False  # confirmed applied via checkpoint
    setup_pending_changes: int = 0      # saved-but-not-applied field count
    practice_captured: bool = False     # representative laps recorded
    feedback_present: bool = False      # driver feedback submitted
    engineering_reviewed: bool = False  # a setup decision was produced
    controlled_test_required: bool = False
    controlled_test_done: bool = False
    race_setup_locked: bool = False
    strategy_evidence_ready: bool = False   # PracticeEvidenceBundle.is_ready_for_strategy
    race_plan_built: bool = False
    live_review_available: bool = False


# (key, title, next-tab-key) in order.
_STAGES = [
    ("event_car", "Event & Car", "event_planner"),
    ("track_ready", "Track Readiness", "track_modelling"),
    ("build_setup", "Build or Load Setup", "setup_builder"),
    ("apply_setup", "Apply Setup in GT7", "setup_builder"),
    ("capture_practice", "Capture Practice", "live"),
    ("driver_feedback", "Driver Feedback", "practice_review"),
    ("engineering_review", "Engineering Review", "setup_builder"),
    ("controlled_test", "Controlled Test", "live"),
    ("lock_setup", "Lock Race Setup", "setup_builder"),
    ("build_strategy", "Build Race Strategy", "strategy_builder"),
    ("race_plan", "Race Plan Ready", "strategy_builder"),
    ("live_review", "Live Race Review", "live"),
]


def _stage_done(key: str, i: "WorkflowInputs") -> bool:
    return {
        "event_car": i.event_ready,
        "track_ready": i.track_ready,
        "build_setup": i.setup_saved,
        "apply_setup": i.setup_applied_in_gt7,
        "capture_practice": i.practice_captured,
        "driver_feedback": i.feedback_present,
        "engineering_review": i.engineering_reviewed,
        # The controlled-test stage is "done" when either not required or done.
        "controlled_test": (not i.controlled_test_required) or i.controlled_test_done,
        "lock_setup": i.race_setup_locked,
        "build_strategy": i.strategy_evidence_ready,
        "race_plan": i.race_plan_built,
        "live_review": i.live_review_available,
    }.get(key, False)


def _stage_blocker(key: str, i: "WorkflowInputs") -> str:
    if key == "track_ready" and i.event_ready and not i.track_ready:
        return i.track_blocker or "Track model is not ready."
    if key == "apply_setup" and i.setup_saved and not i.setup_applied_in_gt7:
        n = i.setup_pending_changes
        return (f"{n} change(s) saved but not yet confirmed applied in GT7."
                if n else "Setup saved but not confirmed applied in GT7.")
    if key == "build_strategy" and i.race_setup_locked and not i.strategy_evidence_ready:
        return "Practice evidence is incomplete for a race plan."
    return ""


def _stage_next_action(key: str, i: "WorkflowInputs") -> str:
    return {
        "event_car": "Select the event, car, and track in Event Planner.",
        "track_ready": "Open Track Modelling to complete the track model."
                       if not i.track_ready else "Track ready — load or build a setup.",
        "build_setup": "Build or load a race setup in Setup Builder.",
        "apply_setup": "Apply the highlighted changes in GT7, then press "
                       "“Changes Applied in Game”.",
        "capture_practice": "Run representative practice laps to record telemetry.",
        "driver_feedback": "Submit driver feedback for the run in Practice Review.",
        "engineering_review": "Run Setup Analysis to get the engineering decision.",
        "controlled_test": "Complete the prescribed controlled test.",
        "lock_setup": "Lock the approved race setup.",
        "build_strategy": "Build the race plan from this practice.",
        "race_plan": "Review the race plan.",
        "live_review": "Review the live race.",
    }.get(key, "")


def build_workflow_state(inputs: WorkflowInputs) -> WorkflowState:
    """Compute the guided workflow state. The first not-done stage is CURRENT
    (or BLOCKED if it has an active blocker); earlier stages are DONE; later
    stages PENDING."""
    stages: list[WorkflowStage] = []
    current_index = len(_STAGES)  # default: all done
    found_current = False

    for idx, (key, title, _tab) in enumerate(_STAGES):
        done = _stage_done(key, inputs)
        blocker = _stage_blocker(key, inputs)
        if done:
            status = StageStatus.DONE
        elif not found_current:
            status = StageStatus.BLOCKED if blocker else StageStatus.CURRENT
            current_index = idx
            found_current = True
        else:
            status = StageStatus.PENDING
        stages.append(WorkflowStage(
            index=idx, key=key, title=title, status=status,
            blocker=blocker if status in (StageStatus.CURRENT, StageStatus.BLOCKED) else "",
            next_action=_stage_next_action(key, inputs) if status in (
                StageStatus.CURRENT, StageStatus.BLOCKED) else "",
        ))

    if found_current:
        cur = stages[current_index]
        next_action = cur.next_action
        next_tab = _STAGES[current_index][2]
    else:
        next_action = "All stages complete."
        next_tab = ""

    return WorkflowState(stages=tuple(stages), current_index=current_index,
                         next_action=next_action, next_tab=next_tab)
