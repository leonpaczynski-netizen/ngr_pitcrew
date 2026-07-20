"""End-to-end event-programme certification (Program 2, Phase 56).

An explicit, honest certification of the complete NGR event journey. It records per-area evidence,
findings, blockers and limitations, and computes an overall certification level bounded by the weakest
area. Certification levels are strictly evidence-gated:

  * automated evidence cannot award visual, live-GT7, or operational readiness;
  * offscreen Qt evidence cannot award visual validation;
  * replay evidence cannot award live-GT7 validation;
  * operational readiness requires live-GT7 evidence AND an explicit human grant, and never while a
    critical blocker remains.

Purity: Qt-free, DB-free, offline, deterministic, no wall-clock, never raises. It grants nothing on its
own — it reports what the recorded evidence supports.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Sequence, Tuple

EVENT_PROGRAMME_CERTIFICATION_VERSION = "event_programme_certification_v1"


def _norm(v) -> str:
    return str(v if v is not None else "").strip()


def _fp(payload) -> str:
    return (f"{EVENT_PROGRAMME_CERTIFICATION_VERSION}:"
            + hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"),
                                        ensure_ascii=True, default=str).encode()).hexdigest()[:24])


class EvidenceType(str, Enum):
    NONE = "none"
    AUTOMATED = "automated"
    OFFSCREEN = "offscreen"
    REPLAY = "replay"
    VISUAL_PARTIAL = "visual_partial"
    VISUAL = "visual"
    LIVE_PARTIAL = "live_partial"
    LIVE = "live"


class CertificationLevel(str, Enum):
    NOT_TESTED = "not_tested"
    AUTOMATED_ONLY = "automated_only"
    OFFSCREEN_VALIDATED = "offscreen_validated"
    REPLAY_VALIDATED = "replay_validated"
    VISUAL_UAT_PARTIAL = "visual_uat_partial"
    VISUAL_UAT_VALIDATED = "visual_uat_validated"
    LIVE_GT7_PARTIAL = "live_gt7_partial"
    LIVE_GT7_VALIDATED = "live_gt7_validated"
    OPERATIONALLY_READY_WITH_LIMITATIONS = "operationally_ready_with_limitations"
    OPERATIONALLY_READY = "operationally_ready"


_LEVEL_ORDER = (
    CertificationLevel.NOT_TESTED, CertificationLevel.AUTOMATED_ONLY,
    CertificationLevel.OFFSCREEN_VALIDATED, CertificationLevel.REPLAY_VALIDATED,
    CertificationLevel.VISUAL_UAT_PARTIAL, CertificationLevel.VISUAL_UAT_VALIDATED,
    CertificationLevel.LIVE_GT7_PARTIAL, CertificationLevel.LIVE_GT7_VALIDATED,
    CertificationLevel.OPERATIONALLY_READY_WITH_LIMITATIONS, CertificationLevel.OPERATIONALLY_READY,
)

# the maximum level a given evidence type can award (the strict caps)
_EVIDENCE_MAX = {
    EvidenceType.NONE: CertificationLevel.NOT_TESTED,
    EvidenceType.AUTOMATED: CertificationLevel.AUTOMATED_ONLY,
    EvidenceType.OFFSCREEN: CertificationLevel.OFFSCREEN_VALIDATED,
    EvidenceType.REPLAY: CertificationLevel.REPLAY_VALIDATED,
    EvidenceType.VISUAL_PARTIAL: CertificationLevel.VISUAL_UAT_PARTIAL,
    EvidenceType.VISUAL: CertificationLevel.VISUAL_UAT_VALIDATED,
    EvidenceType.LIVE_PARTIAL: CertificationLevel.LIVE_GT7_PARTIAL,
    EvidenceType.LIVE: CertificationLevel.LIVE_GT7_VALIDATED,
}


class FindingSeverity(str, Enum):
    INFO = "info"
    LIMITATION = "limitation"
    BLOCKER = "blocker"


@dataclass(frozen=True)
class CertificationFinding:
    kind: str
    severity: FindingSeverity
    message: str

    def as_payload(self) -> dict:
        return {"kind": _norm(self.kind), "severity": self.severity.value, "message": _norm(self.message)}


@dataclass(frozen=True)
class CertificationArea:
    name: str
    evidence_type: EvidenceType
    last_scenario: str = ""
    findings: Tuple[CertificationFinding, ...] = field(default_factory=tuple)

    @property
    def has_blocker(self) -> bool:
        return any(f.severity == FindingSeverity.BLOCKER for f in self.findings)

    @property
    def effective_level(self) -> CertificationLevel:
        if self.has_blocker:
            return CertificationLevel.NOT_TESTED   # a blocker withholds any award for this area
        return _EVIDENCE_MAX.get(self.evidence_type, CertificationLevel.NOT_TESTED)

    def as_payload(self) -> dict:
        return {"name": _norm(self.name), "evidence_type": self.evidence_type.value,
                "effective_level": self.effective_level.value, "last_scenario": _norm(self.last_scenario),
                "findings": [f.as_payload() for f in self.findings]}


@dataclass(frozen=True)
class EventProgrammeCertification:
    overall_level: CertificationLevel
    areas: Tuple[CertificationArea, ...]
    weakest_area: str
    blockers: Tuple[str, ...]
    limitations: Tuple[str, ...]
    note: str
    fingerprint: str = ""

    def as_payload(self) -> dict:
        return {"overall_level": self.overall_level.value,
                "areas": [a.as_payload() for a in sorted(self.areas, key=lambda a: _norm(a.name))],
                "weakest_area": _norm(self.weakest_area),
                "blockers": sorted(self.blockers), "limitations": sorted(self.limitations),
                "note": _norm(self.note)}


def build_event_programme_certification(
    areas: Sequence[CertificationArea], *, operationally_ready_granted: bool = False,
) -> EventProgrammeCertification:
    """Aggregate per-area evidence into the honest overall level (bounded by the weakest area's effective
    level). Operational readiness requires a human grant AND every area at a live level AND no blocker."""
    areas = tuple(areas)
    if not areas:
        return EventProgrammeCertification(CertificationLevel.NOT_TESTED, (), "", (), (),
                                           "no certification areas", _fp({"empty": True}))
    weakest = min(areas, key=lambda a: _LEVEL_ORDER.index(a.effective_level))
    overall = weakest.effective_level

    blockers = tuple(f"{a.name}: {f.message}" for a in areas for f in a.findings
                     if f.severity == FindingSeverity.BLOCKER)
    limitations = tuple(f"{a.name}: {f.message}" for a in areas for f in a.findings
                        if f.severity == FindingSeverity.LIMITATION)

    if operationally_ready_granted and not blockers:
        min_idx = _LEVEL_ORDER.index(weakest.effective_level)
        if min_idx >= _LEVEL_ORDER.index(CertificationLevel.LIVE_GT7_VALIDATED):
            overall = CertificationLevel.OPERATIONALLY_READY
        elif min_idx >= _LEVEL_ORDER.index(CertificationLevel.LIVE_GT7_PARTIAL):
            overall = CertificationLevel.OPERATIONALLY_READY_WITH_LIMITATIONS
        # a grant with only automated/offscreen/replay/visual evidence is ignored (never fabricated)

    note = (f"overall bounded by weakest area '{weakest.name}' ({weakest.effective_level.value}). "
            "Automated evidence cannot award visual/live/operational; offscreen cannot award visual; "
            "replay cannot award live-GT7. "
            + ("BLOCKERS present — operational readiness withheld." if blockers else ""))
    cert = EventProgrammeCertification(overall, areas, weakest.name, blockers, limitations, note, "")
    return EventProgrammeCertification(cert.overall_level, cert.areas, cert.weakest_area, cert.blockers,
                                       cert.limitations, cert.note, _fp(cert.as_payload()))


# the 23 certification areas of the NGR event journey (task section 9)
CERTIFICATION_AREAS: Tuple[str, ...] = (
    "active_event_selection", "home_command_centre", "timeline", "next_action_accuracy",
    "activity_start", "setup_verification", "live_practice", "live_qualifying", "live_race",
    "telemetry_loss", "session_end_detection", "explicit_session_binding", "immediate_debrief",
    "cumulative_learning", "setup_convergence", "setup_lock", "strategy_finalisation", "event_revision",
    "restart_recovery", "voice_gating", "db_and_config_safety", "visual_clarity", "ngr_immersion",
)


def current_slice_certification() -> "EventProgrammeCertification":
    """The HONEST self-certification of the Phase 54-56 slice: each area at the evidence type actually
    achieved. Domain logic = automated; UI panels = offscreen; replay/shadow-tested areas = replay; the
    live GT7 and visual areas were NOT run headlessly = NONE (NOT_TESTED). The overall level is therefore
    bounded by the untested live/visual areas — no live or operational certification is claimed."""
    A = EvidenceType
    spec = {
        "active_event_selection": A.AUTOMATED, "home_command_centre": A.OFFSCREEN, "timeline": A.OFFSCREEN,
        "next_action_accuracy": A.AUTOMATED, "activity_start": A.AUTOMATED, "setup_verification": A.AUTOMATED,
        "live_practice": A.NONE, "live_qualifying": A.NONE, "live_race": A.NONE,
        "telemetry_loss": A.AUTOMATED, "session_end_detection": A.AUTOMATED,
        "explicit_session_binding": A.AUTOMATED, "immediate_debrief": A.AUTOMATED,
        "cumulative_learning": A.AUTOMATED, "setup_convergence": A.AUTOMATED, "setup_lock": A.AUTOMATED,
        "strategy_finalisation": A.AUTOMATED, "event_revision": A.AUTOMATED, "restart_recovery": A.AUTOMATED,
        "voice_gating": A.AUTOMATED, "db_and_config_safety": A.AUTOMATED, "visual_clarity": A.NONE,
        "ngr_immersion": A.NONE,
    }
    live_note = "not run in this headless environment (requires live GT7 / visual UAT)"
    areas = []
    for name in CERTIFICATION_AREAS:
        ev = spec.get(name, A.AUTOMATED)
        findings = ()
        if ev == A.NONE:
            findings = (CertificationFinding("not_run", FindingSeverity.LIMITATION, live_note),)
        areas.append(CertificationArea(name, ev, last_scenario="phase54-56 automated suite",
                                       findings=findings))
    return build_event_programme_certification(areas)
