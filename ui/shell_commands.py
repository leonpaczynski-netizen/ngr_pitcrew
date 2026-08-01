"""Typed shell command vocabulary (Program 3 §10).

The canonical, typed set of intents a page may issue instead of ad-hoc signal
names. Each command carries canonical identities (event/session-plan/session-run/
setup-snapshot ids), so the command surface is auditable and a single dispatch
point (``LiveShellBridge.dispatch``) can context-stamp or validate it.

This module is the *vocabulary*; the bridge's ``dispatch`` routes each command to
the canonical operation. It is ADDITIVE — the existing widget→signal→bridge-slot
wiring is unchanged — so it introduces the typed surface without churning (or
risking) the working command handlers. Commands whose underlying operation is
built in a later phase are defined here so the vocabulary is complete, but
``dispatch`` refuses them explicitly rather than mapping them onto a
semantically-different existing handler.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Union


@dataclass(frozen=True)
class SelectEvent:
    event_id: str = ""
    event_name: str = ""


@dataclass(frozen=True)
class SelectSession:
    session_plan_id: str = ""


@dataclass(frozen=True)
class StartSessionRun:
    session_plan_id: str = ""
    session_type: str = ""


@dataclass(frozen=True)
class ResumeSessionRun:
    session_run_id: str = ""


@dataclass(frozen=True)
class CompleteSessionRun:
    session_run_id: str = ""
    status: str = "complete"


@dataclass(frozen=True)
class ApplySetup:
    setup_snapshot_id: str = ""
    discipline: str = "race"


@dataclass(frozen=True)
class StartTelemetryCapture:
    session_run_id: str = ""


@dataclass(frozen=True)
class RecordDriverFeedback:
    session_run_id: str = ""
    feedback: dict = field(default_factory=dict)


@dataclass(frozen=True)
class CompleteLap:
    session_run_id: str = ""
    lap_id: str = ""


@dataclass(frozen=True)
class ReportRaceIncident:
    session_run_id: str = ""
    incident: str = ""


@dataclass(frozen=True)
class AcceptLearningProposal:
    learning_proposal_id: str = ""


@dataclass(frozen=True)
class RejectLearningProposal:
    learning_proposal_id: str = ""


Command = Union[
    SelectEvent, SelectSession, StartSessionRun, ResumeSessionRun,
    CompleteSessionRun, ApplySetup, StartTelemetryCapture, RecordDriverFeedback,
    CompleteLap, ReportRaceIncident, AcceptLearningProposal, RejectLearningProposal,
]

__all__ = [
    "SelectEvent", "SelectSession", "StartSessionRun", "ResumeSessionRun",
    "CompleteSessionRun", "ApplySetup", "StartTelemetryCapture", "RecordDriverFeedback",
    "CompleteLap", "ReportRaceIncident", "AcceptLearningProposal", "RejectLearningProposal",
    "Command",
]
