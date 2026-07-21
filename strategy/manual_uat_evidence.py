"""Manual UAT Evidence — pure domain (Program 2, Phase 71).

WHY IT EXISTS
  Physical microphone, wheel/keyboard PTT, physical TTS, PSVR2 and live-GT7 operation can ONLY be certified
  by the user's real-world testing. This module is the deterministic domain for recording that evidence: one
  ``ManualUatObservation`` per test, an append-only auditable ledger, latest-supersedes-prior precedence,
  and the alignment of manual areas with the existing Phase-68 certification taxonomy (never a second,
  incompatible one).

DOCTRINE
  Deterministic, offline, Qt-free, DB-free; never raises. A PASS observation is created ONLY by an explicit
  user action — no unit or bench test can synthesise one. Prior evidence is never silently overwritten; a new
  observation supersedes the prior one and the ledger preserves both. No wall clock (timestamps are injected
  by the caller).
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

MANUAL_UAT_EVIDENCE_VERSION = "manual_uat_evidence_v1"


def _norm(v) -> str:
    return str(v if v is not None else "").strip()


def _fp(payload) -> str:
    return (f"{MANUAL_UAT_EVIDENCE_VERSION}:"
            + hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"),
                                        ensure_ascii=True, default=str).encode()).hexdigest()[:24])


class ManualUatStatus(str, Enum):
    NOT_RUN = "not_run"
    PASS = "pass"
    FAIL = "fail"
    BLOCKED = "blocked"
    NOT_APPLICABLE = "not_applicable"


# --------------------------------------------------------------------------- #
# Manual areas — aligned to the Phase-68 certification taxonomy (one source of truth)
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class ManualUatArea:
    key: str
    label: str
    cert_area: str        # the aligned Phase-68 live_vr_certification area ("" if desktop-only)
    category: str         # desktop | telemetry | strategy | audio | physical | psvr2 | live


# ordered; categories physical/psvr2/live are the ones that gate operational certification.
MANUAL_UAT_AREAS: Tuple[ManualUatArea, ...] = (
    ManualUatArea("application_startup", "Application startup", "", "desktop"),
    ManualUatArea("desktop_visual_layout", "Desktop visual layout", "visual_fallback", "desktop"),
    ManualUatArea("windows_scaling", "Windows scaling", "", "desktop"),
    ManualUatArea("live_dashboard_readability", "Live dashboard readability", "live_tab_strategy_card", "desktop"),
    ManualUatArea("telemetry_connection", "Telemetry connection", "session_binding", "telemetry"),
    ManualUatArea("telemetry_reconnect", "Telemetry reconnect", "telemetry_loss", "telemetry"),
    ManualUatArea("session_transition", "Session transition", "session_binding", "telemetry"),
    ManualUatArea("fuel_mapping", "Fuel mapping", "fuel_burn", "strategy"),
    ManualUatArea("pace_mapping", "Pace mapping", "pace_divergence", "strategy"),
    ManualUatArea("race_clock", "Race clock", "race_clock", "strategy"),
    ManualUatArea("lap_rollover", "Lap rollover", "real_tracker_mapping", "strategy"),
    ManualUatArea("pit_entry", "Pit entry", "pit_detection", "strategy"),
    ManualUatArea("pit_stop", "Pit stop", "pit_detection", "strategy"),
    ManualUatArea("pit_exit", "Pit exit", "pit_detection", "strategy"),
    ManualUatArea("tyre_age_proxy", "Tyre-age proxy", "tyre_proxy", "strategy"),
    ManualUatArea("lap_count_adaptive_strategy", "Lap-count adaptive strategy", "lap_count_strategy", "strategy"),
    ManualUatArea("time_certain_adaptive_strategy", "Time-certain adaptive strategy", "time_certain_strategy", "strategy"),
    ManualUatArea("strategy_explanation_quality", "Strategy explanation quality", "revised_candidate_ranking", "strategy"),
    ManualUatArea("audio_priority", "Audio priority", "workload_aware_delivery", "audio"),
    ManualUatArea("audio_cooldown", "Audio cooldown", "repeated_replanning", "audio"),
    ManualUatArea("recognition_confidence", "Recognition confidence", "microphone_recognition", "audio"),
    ManualUatArea("ambiguous_speech", "Ambiguous speech", "command_grammar", "audio"),
    ManualUatArea("confirmation_flow", "Confirmation flow", "driver_report_confirmation", "audio"),
    ManualUatArea("physical_tts", "Physical TTS", "physical_tts", "physical"),
    ManualUatArea("physical_microphone", "Physical microphone", "microphone_recognition", "physical"),
    ManualUatArea("keyboard_ptt", "Keyboard PTT", "keyboard_ptt", "physical"),
    ManualUatArea("wheel_joystick_ptt", "Wheel / joystick PTT", "wheel_ptt", "physical"),
    ManualUatArea("psvr2_audibility", "PSVR2 audibility", "psvr2_race", "psvr2"),
    ManualUatArea("psvr2_timing", "PSVR2 timing", "psvr2_race", "psvr2"),
    ManualUatArea("psvr2_driver_workload", "PSVR2 driver workload", "psvr2_race", "psvr2"),
    ManualUatArea("live_gt7_operational_suitability", "Live GT7 operational suitability", "cumulative_learning", "live"),
)

_AREA_BY_KEY: Dict[str, ManualUatArea] = {a.key: a for a in MANUAL_UAT_AREAS}
_REQUIRED_PHYSICAL_LIVE_CATEGORIES = frozenset({"physical", "psvr2", "live"})


def manual_uat_area_keys() -> Tuple[str, ...]:
    return tuple(a.key for a in MANUAL_UAT_AREAS)


def required_physical_live_areas() -> Tuple[str, ...]:
    """The manual areas whose PASS is required before any operational-certification claim (physical device,
    PSVR2 and live-GT7 categories). These can ONLY be satisfied by real user evidence."""
    return tuple(a.key for a in MANUAL_UAT_AREAS if a.category in _REQUIRED_PHYSICAL_LIVE_CATEGORIES)


def is_valid_area(key: str) -> bool:
    return key in _AREA_BY_KEY


# --------------------------------------------------------------------------- #
# One manual observation
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class ManualUatObservation:
    area: str
    status: ManualUatStatus
    tested_at: str = ""                 # injected timestamp string (no wall clock here)
    candidate_commit: str = ""
    notes: str = ""
    expected_behaviour: str = ""
    observed_behaviour: str = ""
    defect_reference: str = ""
    evidence_reference: str = ""        # user-entered metadata (path / link); not read here
    hardware_context: str = ""
    retest_required: bool = False
    supersedes: str = ""                # fingerprint of the observation this one replaces
    fingerprint: str = ""

    def as_payload(self) -> dict:
        return {"area": _norm(self.area), "status": self.status.value, "tested_at": _norm(self.tested_at),
                "candidate_commit": _norm(self.candidate_commit), "notes": _norm(self.notes),
                "expected_behaviour": _norm(self.expected_behaviour),
                "observed_behaviour": _norm(self.observed_behaviour),
                "defect_reference": _norm(self.defect_reference),
                "evidence_reference": _norm(self.evidence_reference),
                "hardware_context": _norm(self.hardware_context),
                "retest_required": bool(self.retest_required), "supersedes": _norm(self.supersedes)}

    def to_dict(self) -> dict:
        d = self.as_payload()
        d["fingerprint"] = self.fingerprint
        return d

    @classmethod
    def from_dict(cls, d: Optional[Mapping]) -> "ManualUatObservation":
        c = d if isinstance(d, Mapping) else {}
        try:
            status = ManualUatStatus(_norm(c.get("status")) or "not_run")
        except ValueError:
            status = ManualUatStatus.NOT_RUN
        obs = cls(area=_norm(c.get("area")), status=status, tested_at=_norm(c.get("tested_at")),
                  candidate_commit=_norm(c.get("candidate_commit")), notes=_norm(c.get("notes")),
                  expected_behaviour=_norm(c.get("expected_behaviour")),
                  observed_behaviour=_norm(c.get("observed_behaviour")),
                  defect_reference=_norm(c.get("defect_reference")),
                  evidence_reference=_norm(c.get("evidence_reference")),
                  hardware_context=_norm(c.get("hardware_context")),
                  retest_required=bool(c.get("retest_required", False)),
                  supersedes=_norm(c.get("supersedes")))
        return stamp_observation(obs)


def stamp_observation(obs: ManualUatObservation) -> ManualUatObservation:
    return replace(obs, fingerprint=_fp(obs.as_payload()))


def make_observation(area: str, status, *, tested_at: str = "", candidate_commit: str = "", notes: str = "",
                     expected_behaviour: str = "", observed_behaviour: str = "", defect_reference: str = "",
                     evidence_reference: str = "", hardware_context: str = "", retest_required: bool = False,
                     supersedes: str = "") -> ManualUatObservation:
    """Build a stamped observation. A FAIL/BLOCKED sets retest_required by default (a failed area must be
    re-tested). Never raises."""
    try:
        st = status if isinstance(status, ManualUatStatus) else ManualUatStatus(_norm(status) or "not_run")
    except ValueError:
        st = ManualUatStatus.NOT_RUN
    if st in (ManualUatStatus.FAIL, ManualUatStatus.BLOCKED):
        retest_required = True
    return stamp_observation(ManualUatObservation(
        area=_norm(area), status=st, tested_at=_norm(tested_at), candidate_commit=_norm(candidate_commit),
        notes=_norm(notes), expected_behaviour=_norm(expected_behaviour),
        observed_behaviour=_norm(observed_behaviour), defect_reference=_norm(defect_reference),
        evidence_reference=_norm(evidence_reference), hardware_context=_norm(hardware_context),
        retest_required=bool(retest_required), supersedes=_norm(supersedes)))


# --------------------------------------------------------------------------- #
# The append-only ledger (precedence: latest supersedes prior)
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class ManualUatLedger:
    observations: Tuple[ManualUatObservation, ...] = ()

    def append(self, obs: ManualUatObservation) -> "ManualUatLedger":
        """Return a NEW ledger with ``obs`` appended, wired to supersede the current active observation for
        its area WITHIN THE SAME CANDIDATE SCOPE (the prior one is preserved for audit; an observation from a
        different candidate commit is never superseded — it stays historical). Explicit user action only."""
        prior = self.active(obs.area, obs.candidate_commit)
        wired = obs
        if prior is not None and prior.fingerprint and not obs.supersedes:
            wired = stamp_observation(replace(obs, supersedes=prior.fingerprint))
        return ManualUatLedger(observations=self.observations + (wired,))

    def active(self, area: str, candidate_commit=None) -> Optional[ManualUatObservation]:
        """The latest observation for ``area`` (append order = chronological). When ``candidate_commit`` is
        given (a string, possibly ""), ONLY observations recorded against that exact candidate count —
        evidence from a different commit is ignored (DEF-UAT-072-001: evidence is candidate-scoped). When
        ``candidate_commit`` is None the latest observation is returned regardless (used for display/history).
        """
        latest = None
        for o in self.observations:
            if o.area != area:
                continue
            if candidate_commit is not None and _norm(o.candidate_commit) != _norm(candidate_commit):
                continue
            latest = o
        return latest

    def active_by_area(self, candidate_commit=None) -> Dict[str, ManualUatObservation]:
        out: Dict[str, ManualUatObservation] = {}
        for o in self.observations:
            if candidate_commit is not None and _norm(o.candidate_commit) != _norm(candidate_commit):
                continue
            out[o.area] = o
        return out

    def status_of(self, area: str, candidate_commit=None) -> ManualUatStatus:
        a = self.active(area, candidate_commit)
        return a.status if a is not None else ManualUatStatus.NOT_RUN

    def history(self, area: str) -> Tuple[ManualUatObservation, ...]:
        """Every observation for ``area`` across ALL candidates (viewable audit trail; scoping does not hide
        history — it only governs what COUNTS toward the active candidate)."""
        return tuple(o for o in self.observations if o.area == area)

    def candidates(self) -> Tuple[str, ...]:
        """The distinct candidate commits present in the ledger (for visibility of cross-candidate history)."""
        seen = []
        for o in self.observations:
            c = _norm(o.candidate_commit)
            if c and c not in seen:
                seen.append(c)
        return tuple(seen)

    def to_payload(self) -> dict:
        return {"version": MANUAL_UAT_EVIDENCE_VERSION,
                "observations": [o.to_dict() for o in self.observations]}

    @classmethod
    def from_payload(cls, payload: Optional[Mapping]) -> "ManualUatLedger":
        c = payload if isinstance(payload, Mapping) else {}
        obs = tuple(ManualUatObservation.from_dict(o) for o in (c.get("observations") or [])
                    if isinstance(o, Mapping))
        return cls(observations=obs)


def manual_uat_evidence_versions() -> dict:
    return {"manual_uat_evidence": MANUAL_UAT_EVIDENCE_VERSION}
