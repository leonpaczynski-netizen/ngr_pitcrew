"""Live activity modes — Practice / Qualifying / Race views (Program 2, Phase 52).

Three deliberately low-density live views built over the activity execution context and the EXISTING live
advisory authorities (referenced, never re-implemented). Practice is focused; Qualifying is minimal and
urgent (no Practice experiment detail); Race is safety- and strategy-focused and issues NO pit/tyre/fuel
commands. These are display/orchestration views — they change no state and author no setup value.

Purity: Qt-free, DB-free, offline, deterministic, no wall-clock, never raises.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Sequence, Tuple

LIVE_ACTIVITY_MODES_VERSION = "live_activity_modes_v1"


def _norm(v) -> str:
    return str(v if v is not None else "").strip()


def _dumps(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str, ensure_ascii=True,
                      allow_nan=False)


def _fp(payload) -> str:
    return (f"{LIVE_ACTIVITY_MODES_VERSION}:"
            + hashlib.sha256(_dumps(payload).encode("utf-8")).hexdigest()[:24])


class LiveMode(str, Enum):
    PRACTICE = "practice"
    QUALIFYING = "qualifying"
    RACE = "race"


class LiveDensity(str, Enum):
    FOCUSED = "focused"        # Practice
    MINIMAL = "minimal"        # Qualifying
    SAFETY = "safety"          # Race


@dataclass(frozen=True)
class PracticeLiveView:
    mode: LiveMode
    density: LiveDensity
    activity_title: str
    objective: str
    active_setup_fingerprint: str
    target_laps: int
    valid_laps: int
    target_corners: Tuple[str, ...]
    evidence_collected: Tuple[str, ...]
    evidence_missing: Tuple[str, ...]
    current_advisory: str
    stop_condition: str
    return_to_garage: bool
    fingerprint: str = ""

    def as_stable_payload(self) -> dict:
        # live counters + advisory text are display; the stable identity is the configuration
        return {"mode": self.mode.value, "activity_title": _norm(self.activity_title),
                "objective": _norm(self.objective),
                "active_setup_fingerprint": _norm(self.active_setup_fingerprint),
                "target_laps": int(self.target_laps),
                "target_corners": [_norm(c) for c in self.target_corners],
                "evidence_missing": sorted(_norm(e) for e in self.evidence_missing if _norm(e)),
                "stop_condition": _norm(self.stop_condition)}


@dataclass(frozen=True)
class QualifyingLiveView:
    mode: LiveMode
    density: LiveDensity
    setup_confirmation: str
    tyre_preparation: str
    out_lap_status: str
    lap_validity: str
    attempt_number: int
    target_info: str
    current_advisory: str
    session_complete: bool
    fingerprint: str = ""

    def as_stable_payload(self) -> dict:
        return {"mode": self.mode.value, "setup_confirmation": _norm(self.setup_confirmation),
                "tyre_preparation": _norm(self.tyre_preparation), "target_info": _norm(self.target_info)}


@dataclass(frozen=True)
class RaceLiveView:
    mode: LiveMode
    density: LiveDensity
    race_setup_match: bool
    primary_strategy: str
    plan_status: str
    tyre_awareness: str
    fuel_awareness: str
    pit_window_awareness: str
    car_condition: str
    current_advisory: str
    voice_state: str
    critical_warnings: Tuple[str, ...]
    issues_commands: bool         # ALWAYS False — no unsupported pit/tyre/fuel commands
    fingerprint: str = ""

    def as_stable_payload(self) -> dict:
        return {"mode": self.mode.value, "race_setup_match": bool(self.race_setup_match),
                "primary_strategy": _norm(self.primary_strategy),
                "issues_commands": bool(self.issues_commands)}


def build_practice_live_view(*, activity_title="", objective="", active_setup_fingerprint="",
                             target_laps=0, valid_laps=0, target_corners=(), evidence_collected=(),
                             evidence_missing=(), current_advisory="", stop_condition="",
                             return_to_garage=False) -> PracticeLiveView:
    v = PracticeLiveView(
        mode=LiveMode.PRACTICE, density=LiveDensity.FOCUSED, activity_title=_norm(activity_title),
        objective=_norm(objective), active_setup_fingerprint=_norm(active_setup_fingerprint),
        target_laps=int(target_laps), valid_laps=int(valid_laps), target_corners=tuple(target_corners),
        evidence_collected=tuple(evidence_collected), evidence_missing=tuple(evidence_missing),
        current_advisory=_norm(current_advisory), stop_condition=_norm(stop_condition),
        return_to_garage=bool(return_to_garage), fingerprint="")
    return PracticeLiveView(**{**v.__dict__, "fingerprint": _fp(v.as_stable_payload())})


def build_qualifying_live_view(*, setup_confirmation="", tyre_preparation="", out_lap_status="",
                               lap_validity="", attempt_number=0, target_info="", current_advisory="",
                               session_complete=False) -> QualifyingLiveView:
    v = QualifyingLiveView(
        mode=LiveMode.QUALIFYING, density=LiveDensity.MINIMAL, setup_confirmation=_norm(setup_confirmation),
        tyre_preparation=_norm(tyre_preparation), out_lap_status=_norm(out_lap_status),
        lap_validity=_norm(lap_validity), attempt_number=int(attempt_number), target_info=_norm(target_info),
        current_advisory=_norm(current_advisory), session_complete=bool(session_complete), fingerprint="")
    return QualifyingLiveView(**{**v.__dict__, "fingerprint": _fp(v.as_stable_payload())})


def build_race_live_view(*, race_setup_match=False, primary_strategy="", plan_status="", tyre_awareness="",
                         fuel_awareness="", pit_window_awareness="", car_condition="", current_advisory="",
                         voice_state="disabled", critical_warnings=()) -> RaceLiveView:
    v = RaceLiveView(
        mode=LiveMode.RACE, density=LiveDensity.SAFETY, race_setup_match=bool(race_setup_match),
        primary_strategy=_norm(primary_strategy), plan_status=_norm(plan_status),
        tyre_awareness=_norm(tyre_awareness), fuel_awareness=_norm(fuel_awareness),
        pit_window_awareness=_norm(pit_window_awareness), car_condition=_norm(car_condition),
        current_advisory=_norm(current_advisory), voice_state=_norm(voice_state),
        critical_warnings=tuple(critical_warnings), issues_commands=False, fingerprint="")
    return RaceLiveView(**{**v.__dict__, "fingerprint": _fp(v.as_stable_payload())})
