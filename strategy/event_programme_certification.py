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


# ---------------------------------------------------------------------------
# Phase 59 — full live-event journey certification (per-area, with required-next-evidence)
# ---------------------------------------------------------------------------

# the ~30 areas of the complete NGR event experience (task section 9)
LIVE_CERTIFICATION_AREAS: Tuple[str, ...] = (
    "active_event_selection", "command_centre", "next_action", "preparation_timeline",
    "activity_selection", "start_readiness", "practice_runtime", "qualifying_runtime", "race_runtime",
    "telemetry_freshness", "context_match", "setup_match", "advisory_delivery", "voice_gating",
    "telemetry_dropout", "session_end_detection", "session_binding", "debrief", "cumulative_setup_learning",
    "driver_development_learning", "tyre_and_fuel_maturity", "strategy_maturity", "setup_lock",
    "strategy_finalisation", "restart_recovery", "event_revision", "visual_clarity", "ngr_immersion",
    "db_safety", "config_safety", "runtime_performance",
)

# areas that fundamentally require a live GT7 feed or a human viewing the UI (cannot exceed NONE here)
_LIVE_OR_VISUAL_AREAS = frozenset({
    "practice_runtime", "qualifying_runtime", "race_runtime", "telemetry_freshness", "advisory_delivery",
    "telemetry_dropout", "visual_clarity", "ngr_immersion", "runtime_performance",
})

_REQUIRED_NEXT_EVIDENCE = {
    "practice_runtime": "live GT7 Practice UAT", "qualifying_runtime": "live GT7 Qualifying UAT",
    "race_runtime": "live GT7 Race UAT", "telemetry_freshness": "live GT7 feed",
    "advisory_delivery": "live GT7 advisory delivery UAT", "telemetry_dropout": "live telemetry-loss UAT",
    "visual_clarity": "manual visual UAT", "ngr_immersion": "manual visual UAT",
    "runtime_performance": "live runtime profiling", "voice_gating": "physical voice UAT",
    "command_centre": "manual visual UAT", "session_binding": "live session-binding UAT",
    "debrief": "live debrief UAT",
}


def required_next_evidence(area_name: str) -> str:
    return _REQUIRED_NEXT_EVIDENCE.get(_norm(area_name), "")


def live_event_certification() -> "EventProgrammeCertification":
    """The HONEST self-certification of the full NGR live-event journey after Phase 57-59. Domain logic =
    automated; UI panels = offscreen; live-GT7 / visual / voice areas = NONE (not run headlessly). Per-
    area detail is preserved; the overall level is bounded by the untested live areas (NOT reduced to one
    undifferentiated NOT_TESTED)."""
    A = EvidenceType
    automated = {
        "next_action", "activity_selection", "start_readiness", "context_match", "setup_match",
        "session_end_detection", "cumulative_setup_learning", "driver_development_learning",
        "tyre_and_fuel_maturity", "strategy_maturity", "setup_lock", "strategy_finalisation",
        "restart_recovery", "event_revision", "db_safety", "config_safety", "preparation_timeline",
        "active_event_selection", "session_binding",
    }
    offscreen = {"command_centre"}
    areas = []
    for name in LIVE_CERTIFICATION_AREAS:
        if name in _LIVE_OR_VISUAL_AREAS or name in ("debrief",):
            ev = A.NONE
        elif name in offscreen:
            ev = A.OFFSCREEN
        elif name in automated:
            ev = A.AUTOMATED
        else:
            ev = A.AUTOMATED
        findings = ()
        if ev == A.NONE:
            nxt = required_next_evidence(name) or "live GT7 / visual UAT"
            findings = (CertificationFinding("not_run", FindingSeverity.LIMITATION,
                                             f"not run headlessly — needs {nxt}"),)
        areas.append(CertificationArea(name, ev, last_scenario="phase57-59 automated suite",
                                       findings=findings))
    return build_event_programme_certification(areas)


@dataclass(frozen=True)
class CertificationRun:
    """A deterministic certification-run export (a report, NOT a new DB table). Certification evidence
    never alters engineering state."""
    scenario: str
    certification: "EventProgrammeCertification"
    captured_label: str = ""          # an optional injected label (never a wall-clock read)

    def as_report(self) -> dict:
        return {"scenario": _norm(self.scenario), "captured_label": _norm(self.captured_label),
                "certification": self.certification.as_payload(),
                "fingerprint": self.certification.fingerprint}


# ---------------------------------------------------------------------------
# Phase 62 — production event certification + real-tracker field limitations
# ---------------------------------------------------------------------------

# the 28 areas of the production event experience (task section 8)
PRODUCTION_CERTIFICATION_AREAS: Tuple[str, ...] = (
    "event_command_centre", "activity_briefing", "live_tab_navigation", "tracker_connection",
    "activity_match", "setup_match", "track_and_layout_match", "practice_mode", "qualifying_mode",
    "race_mode", "track_map", "live_advisory", "voice_gating", "telemetry_dropout", "telemetry_recovery",
    "session_end_detection", "candidate_binding", "explicit_binding", "debrief", "cumulative_update",
    "return_to_command_centre", "restart_recovery", "event_switching", "db_safety", "config_safety",
    "thread_safety", "visual_clarity", "ngr_immersion",
)

# areas requiring a live GT7 feed, a human viewing the UI, or physical audio (cannot exceed NONE headlessly)
_PRODUCTION_LIVE_OR_VISUAL = frozenset({
    "tracker_connection", "activity_match", "setup_match", "track_and_layout_match", "practice_mode",
    "qualifying_mode", "race_mode", "track_map", "live_advisory", "telemetry_dropout",
    "telemetry_recovery", "visual_clarity", "ngr_immersion", "voice_gating",
})


def production_event_certification() -> "EventProgrammeCertification":
    """The HONEST self-certification of the Phase 60-62 production workflow. Domain logic (event loop,
    binding, debrief, cumulative update, restart, event switching, DB/config/thread safety) = automated;
    Live-tab construction = offscreen; live-GT7 / visual / voice areas = NONE (not run headlessly). Per-
    area detail is preserved; the overall level is bounded by the untested live areas."""
    A = EvidenceType
    offscreen = {"event_command_centre", "activity_briefing", "live_tab_navigation"}
    areas = []
    for name in PRODUCTION_CERTIFICATION_AREAS:
        if name in _PRODUCTION_LIVE_OR_VISUAL:
            ev = A.NONE
        elif name in offscreen:
            ev = A.OFFSCREEN
        else:
            ev = A.AUTOMATED
        findings = ()
        if ev == A.NONE:
            findings = (CertificationFinding("not_run", FindingSeverity.LIMITATION,
                                             f"needs {required_next_evidence(name) or 'live GT7 / visual UAT'}"),)
        areas.append(CertificationArea(name, ev, last_scenario="phase60-62 automated suite", findings=findings))
    return build_event_programme_certification(areas)


class RuntimeFieldStatus(str, Enum):
    EXACT = "exact"
    INFERRED = "inferred"           # composed from canonical local state
    LIMITED = "limited"             # partial / can be unreliable
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class RuntimeFieldLimitation:
    field: str
    status: RuntimeFieldStatus
    source: str
    blocks: Tuple[str, ...]
    note: str

    def as_payload(self) -> dict:
        return {"field": _norm(self.field), "status": self.status.value, "source": _norm(self.source),
                "blocks": sorted(_norm(b) for b in self.blocks if _norm(b)), "note": _norm(self.note)}


def runtime_field_limitations() -> Tuple[RuntimeFieldLimitation, ...]:
    """The honest per-field runtime limitation record (Audit B). Records which fields are exact / inferred
    from canonical local state / limited / unavailable, and what each limitation blocks. Not disguised."""
    F = RuntimeFieldStatus
    return (
        RuntimeFieldLimitation("car", F.EXACT, "GT7 telemetry via RaceStateTracker", (), "tracker-provided"),
        RuntimeFieldLimitation("track", F.EXACT, "GT7 telemetry via tracker", (), "tracker-provided"),
        RuntimeFieldLimitation("layout", F.LIMITED, "map-match / track model",
                               ("exact_layout_confidence",),
                               "confirmed only with sufficient map-match confidence"),
        RuntimeFieldLimitation("event_context", F.INFERRED, "composed from resolved car+track+layout",
                               (), "live context digest composed locally (Phase 60)"),
        RuntimeFieldLimitation("setup_discipline", F.INFERRED, "selected activity", (), "resolved"),
        RuntimeFieldLimitation("expected_setup_fingerprint", F.INFERRED, "Event Preparation + active setup",
                               (), "resolved (canonical)"),
        RuntimeFieldLimitation("applied_setup_fingerprint", F.LIMITED, "local ActiveSetupAuthority (PROXY)",
                               ("exact_setup_identity", "setup_attribution"),
                               "GT7 does not broadcast the setup; an unrecorded in-game change is undetectable"),
        RuntimeFieldLimitation("tyre_compound", F.LIMITED, "GT7 telemetry (partial)",
                               ("tyre_modelling_confidence",), "may be unknown before the first flying lap"),
        RuntimeFieldLimitation("fuel_state", F.EXACT, "GT7 telemetry", (), "tracker-provided"),
        RuntimeFieldLimitation("run_plan", F.INFERRED, "selected activity", (), "resolved"),
        RuntimeFieldLimitation("selected_activity", F.INFERRED, "Event Preparation state", (), "resolved"),
        RuntimeFieldLimitation("session_purpose", F.INFERRED, "selected activity (never telemetry)", (),
                               "resolved"),
        RuntimeFieldLimitation("telemetry_freshness", F.EXACT, "injected monotonic clock", (), "derived"),
        RuntimeFieldLimitation("map_match_confidence", F.EXACT, "segment resolver / tracker", (),
                               "tracker-provided"),
    )


# ---------------------------------------------------------------------------
# Phases 63-65 — PSVR2 audio-first / PTT / adaptive-strategy certification
# ---------------------------------------------------------------------------

# the per-area certification of the audio-first + PTT + adaptive-strategy experience (task section 11)
AUDIO_STRATEGY_CERTIFICATION_AREAS: Tuple[str, ...] = (
    "psvr2_audio_first_mode", "physical_tts", "message_prioritisation", "workload_aware_delivery",
    "ptt_input_binding", "offline_speech_recognition", "command_grammar", "read_back",
    "driver_confirmation", "transcript_ambiguity", "tts_ptt_interruption", "live_strategy_state",
    "fuel_divergence", "pace_divergence", "tyre_divergence", "time_certain_optimisation",
    "revised_strategy_delivery", "acknowledgement", "repeated_replanning", "audio_telemetry_loss",
    "unavailable_weather_or_damage", "audio_visual_fallback", "physical_hardware_testing",
)

# areas that need real physical audio, a microphone, a wheel/controller button, PSVR2 usage, or a live GT7
# race — none of which an automated suite can grant (they can never exceed NONE headlessly).
_AUDIO_PHYSICAL_OR_LIVE = frozenset({
    "psvr2_audio_first_mode", "physical_tts", "ptt_input_binding", "offline_speech_recognition",
    "physical_hardware_testing", "audio_visual_fallback", "workload_aware_delivery",
})
# domain areas fully exercised by deterministic unit / property tests (no hardware needed).
_AUDIO_AUTOMATED = frozenset({
    "message_prioritisation", "command_grammar", "read_back", "driver_confirmation",
    "transcript_ambiguity", "tts_ptt_interruption", "live_strategy_state", "fuel_divergence",
    "pace_divergence", "tyre_divergence", "time_certain_optimisation", "revised_strategy_delivery",
    "acknowledgement", "repeated_replanning", "audio_telemetry_loss", "unavailable_weather_or_damage",
})

_AUDIO_NEXT_EVIDENCE = {
    "psvr2_audio_first_mode": "PSVR2 driving UAT (wear and use the headset while driving)",
    "physical_tts": "physical TTS UAT on a real audio device",
    "ptt_input_binding": "physical PTT UAT on a real keyboard/controller/wheel button",
    "offline_speech_recognition": "physical microphone UAT with a local offline recogniser",
    "physical_hardware_testing": "physical hardware UAT",
    "audio_visual_fallback": "manual visual UAT of the audio failure fallback",
    "workload_aware_delivery": "live GT7 telemetry UAT of workload windows",
    "live_strategy_state": "live GT7 race-strategy UAT",
    "fuel_divergence": "live GT7 race-strategy UAT",
    "pace_divergence": "live GT7 race-strategy UAT",
    "tyre_divergence": "live GT7 race-strategy UAT",
    "time_certain_optimisation": "live GT7 time-certain race UAT",
    "revised_strategy_delivery": "physical voice UAT during a live race",
}


def audio_strategy_certification() -> "EventProgrammeCertification":
    """The HONEST per-area certification of the Phases 63-65 audio-first / PTT / adaptive-strategy work.

    Deterministic domain areas (priority, grammar, read-back, confirmation, strategy state, divergence,
    time-certain optimisation, acknowledgement, monitoring) are AUTOMATED. Physical-audio, microphone,
    wheel-button, PSVR2 and live-GT7-race areas are NONE — an automated suite can never grant physical
    voice, microphone, wheel-button, PSVR2 usability or live GT7 race-strategy certification. The overall
    level is bounded by those untested areas; per-area detail is preserved (not collapsed)."""
    A = EvidenceType
    areas = []
    for name in AUDIO_STRATEGY_CERTIFICATION_AREAS:
        if name in _AUDIO_PHYSICAL_OR_LIVE:
            ev = A.NONE
        elif name in _AUDIO_AUTOMATED:
            ev = A.AUTOMATED
        else:
            ev = A.AUTOMATED
        findings = ()
        if ev == A.NONE:
            nxt = _AUDIO_NEXT_EVIDENCE.get(name, "physical / live GT7 UAT")
            findings = (CertificationFinding("not_run", FindingSeverity.LIMITATION, f"needs {nxt}"),)
        areas.append(CertificationArea(name, ev, last_scenario="phase63-65 automated suite",
                                       findings=findings))
    return build_event_programme_certification(areas)
