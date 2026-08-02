"""Live Activation 3 — controlled race-day certification workflow (Program 3, Workstream D).

A lightweight, guided "follow the bouncing ball" certification of ONE controlled GT7 + PSVR2 race
event. It is a domain model, not an administration app: it defines the ordered stages, the explicit
per-stage state machine, the honest verdict rules and the auditable report (JSON + Markdown).

The cardinal safety rule is enforced here: **automated or simulated evidence can never promote a
physical hardware checkpoint to PASS** — only a MANUAL result the user records can. A Certified
verdict is therefore impossible while any mandatory physical gate is still NOT_TESTED, and any
FAIL/BLOCKED on identity, telemetry, live-state, persistence, voice or PTT forces a FAILED verdict.

Purity: Qt-free, DB-free, offline, deterministic, no wall-clock (any timestamp is injected), never
raises. It grants nothing on its own — it reports what the recorded evidence supports.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Mapping, Optional, Sequence, Tuple

RACE_CERTIFICATION_VERSION = "race_certification_v1"


def _norm(v) -> str:
    return str(v if v is not None else "").strip()


class StageState(str, Enum):
    NOT_TESTED = "not_tested"
    IN_PROGRESS = "in_progress"
    PASS = "pass"
    CONDITIONAL = "conditional"
    FAIL = "fail"
    BLOCKED = "blocked"


class EvidenceKind(str, Enum):
    NONE = "none"
    AUTOMATED = "automated"     # a passing automated test
    SIMULATED = "simulated"     # fake/replayed telemetry drove it
    MANUAL = "manual"           # the user physically observed the result on hardware


class CertVerdict(str, Enum):
    NOT_TESTED = "not_tested"
    IN_PROGRESS = "in_progress"
    CERTIFIED = "certified"
    CONDITIONALLY_CERTIFIED = "conditionally_certified"
    FAILED = "failed"


@dataclass(frozen=True)
class StageSpec:
    key: str
    title: str
    physical: bool          # requires live GT7 / PSVR2 / physical hardware
    mandatory: bool         # must PASS for a Certified verdict
    core_safety: bool = False   # identity / telemetry / live-state — may not be merely CONDITIONAL


#: The ordered certification stages (§7.1). "Final certification outcome" is the computed verdict,
#: not a user-recorded checkpoint, so it is not a StageSpec.
STAGE_SPECS: Tuple[StageSpec, ...] = (
    StageSpec("environment_build", "Environment and build verification", physical=False, mandatory=True),
    StageSpec("identity", "Event/car/track/layout identity verification", physical=False,
              mandatory=True, core_safety=True),
    StageSpec("telemetry", "Telemetry connection", physical=True, mandatory=True, core_safety=True),
    StageSpec("live_practice", "Live Practice verification", physical=True, mandatory=True),
    StageSpec("live_qualifying", "Live Qualifying verification", physical=True, mandatory=True),
    StageSpec("live_race", "Live Race verification", physical=True, mandatory=True, core_safety=True),
    StageSpec("voice", "Voice verification", physical=True, mandatory=True),
    StageSpec("ptt", "PTT verification", physical=True, mandatory=True),
    StageSpec("restart_persistence", "Restart and persistence verification", physical=True,
              mandatory=True),
    StageSpec("integrity_audit", "Post-session integrity audit", physical=False, mandatory=True),
)

_SPEC_BY_KEY = {s.key: s for s in STAGE_SPECS}
STAGE_KEYS: Tuple[str, ...] = tuple(s.key for s in STAGE_SPECS)


@dataclass(frozen=True)
class StageResult:
    spec: StageSpec
    state: StageState = StageState.NOT_TESTED
    evidence: EvidenceKind = EvidenceKind.NONE
    detail: str = ""
    notes: str = ""
    limitations: Tuple[str, ...] = ()

    @property
    def effective_state(self) -> StageState:
        """The state the verdict trusts. A physical stage may only be credited PASS/CONDITIONAL on
        MANUAL evidence — automated or simulated evidence can never promote a hardware checkpoint,
        so such a claim is downgraded to NOT_TESTED. FAIL/BLOCKED are always honoured (a simulated
        test that finds a defect is real evidence of the defect)."""
        if self.state in (StageState.PASS, StageState.CONDITIONAL) and self.spec.physical \
                and self.evidence != EvidenceKind.MANUAL:
            return StageState.NOT_TESTED
        return self.state

    @property
    def credited_downgraded(self) -> bool:
        return self.effective_state != self.state

    def as_payload(self) -> dict:
        return {
            "key": self.spec.key, "title": self.spec.title, "physical": self.spec.physical,
            "mandatory": self.spec.mandatory, "core_safety": self.spec.core_safety,
            "recorded_state": self.state.value, "effective_state": self.effective_state.value,
            "evidence": self.evidence.value, "credited_downgraded": self.credited_downgraded,
            "detail": _norm(self.detail), "notes": _norm(self.notes),
            "limitations": [l for l in self.limitations if _norm(l)],
        }


def initial_stages() -> Tuple[StageResult, ...]:
    return tuple(StageResult(spec=s) for s in STAGE_SPECS)


def record_stage(
    stages: Sequence[StageResult], key: str, *, state, evidence,
    detail: str = "", notes: str = "", limitations: Optional[Sequence[str]] = None,
) -> Tuple[StageResult, ...]:
    """Return a new stage tuple with ``key`` updated. Deterministic; unknown keys are ignored. The
    recorded state is stored verbatim (auditable), and ``effective_state`` applies the physical-gate
    rule — this function never silently mutates a claim, it just records it honestly."""
    try:
        st = state if isinstance(state, StageState) else StageState(_norm(state).lower())
    except ValueError:
        st = StageState.NOT_TESTED
    try:
        ev = evidence if isinstance(evidence, EvidenceKind) else EvidenceKind(_norm(evidence).lower())
    except ValueError:
        ev = EvidenceKind.NONE
    lims = tuple(_norm(l) for l in (limitations or ()) if _norm(l))
    out = []
    for r in stages:
        if r.spec.key == key:
            out.append(replace(r, state=st, evidence=ev, detail=_norm(detail),
                               notes=_norm(notes), limitations=lims))
        else:
            out.append(r)
    return tuple(out)


def compute_verdict(stages: Sequence[StageResult]) -> Tuple[CertVerdict, str]:
    """The honest overall verdict from the stages' EFFECTIVE states (§7.4). Deterministic.

    FAILED  — any stage FAIL or BLOCKED (identity/telemetry/live-state/persistence/voice/PTT etc.).
    CERTIFIED — every mandatory stage effectively PASS (physical ones via MANUAL evidence).
    CONDITIONALLY_CERTIFIED — every mandatory stage effectively PASS or CONDITIONAL, at least one
       CONDITIONAL, AND no core-safety stage merely CONDITIONAL (limitations must not touch identity,
       telemetry or live-state).
    IN_PROGRESS — some evidence recorded but mandatory gates not all complete.
    NOT_TESTED — nothing meaningful recorded yet.
    """
    eff = {r.spec.key: r.effective_state for r in stages}
    mandatory = [r for r in stages if r.spec.mandatory]

    fails = [r.spec.title for r in stages if r.effective_state in (StageState.FAIL, StageState.BLOCKED)]
    if fails:
        return (CertVerdict.FAILED,
                "Failed — unreliable/unsafe for race day: " + "; ".join(sorted(fails)))

    if mandatory and all(eff[r.spec.key] == StageState.PASS for r in mandatory):
        return (CertVerdict.CERTIFIED,
                "Certified — every mandatory identity, telemetry, live-state, persistence, voice and "
                "PTT gate passed on hardware.")

    conditional = [r for r in mandatory if eff[r.spec.key] == StageState.CONDITIONAL]
    not_tested = [r for r in mandatory if eff[r.spec.key] == StageState.NOT_TESTED]
    core_conditional = [r for r in conditional if r.spec.core_safety]
    if conditional and not not_tested and not core_conditional:
        lims = sorted(l for r in stages for l in r.limitations if _norm(l))
        return (CertVerdict.CONDITIONALLY_CERTIFIED,
                "Conditionally certified — safe with documented limitations that do not invalidate "
                "core identity, telemetry or advisory safety"
                + (": " + "; ".join(lims) if lims else "."))

    # Nothing failed, but mandatory (esp. physical) gates remain untested → not certifiable yet.
    any_progress = any(r.effective_state != StageState.NOT_TESTED for r in stages)
    if any_progress:
        pending = sorted(r.spec.title for r in not_tested)
        return (CertVerdict.IN_PROGRESS,
                "In progress — mandatory gates still NOT_TESTED: " + "; ".join(pending)
                if pending else "In progress.")
    return (CertVerdict.NOT_TESTED, "Not tested — no certification evidence recorded yet.")


#: The evidence header fields captured for auditability (§7.3). All optional; recorded verbatim.
EVIDENCE_FIELDS: Tuple[str, ...] = (
    "app_version", "git_commit", "db_version", "rule_engine_version", "captured_at",
    "event_id", "car_id", "car_name", "track_id", "track_name", "layout_id", "layout_name",
    "session_ids", "run_ids", "telemetry_outcome", "lap_counts", "pit_event_counts",
    "voice_result", "ptt_result", "reconnect_result", "restart_result", "integrity_result",
    "user_notes", "known_limitations",
)


@dataclass(frozen=True)
class RaceCertificationReport:
    scenario: str
    stages: Tuple[StageResult, ...]
    evidence: Mapping = field(default_factory=dict)

    @property
    def verdict(self) -> CertVerdict:
        return compute_verdict(self.stages)[0]

    @property
    def verdict_reason(self) -> str:
        return compute_verdict(self.stages)[1]

    @property
    def is_certified(self) -> bool:
        return self.verdict == CertVerdict.CERTIFIED

    def as_json_payload(self) -> dict:
        v, reason = compute_verdict(self.stages)
        ev = {k: (self.evidence.get(k) if isinstance(self.evidence, Mapping) else None)
              for k in EVIDENCE_FIELDS}
        return {
            "version": RACE_CERTIFICATION_VERSION, "scenario": _norm(self.scenario),
            "verdict": v.value, "verdict_reason": reason, "certified": v == CertVerdict.CERTIFIED,
            "evidence": ev,
            "evidence_legend": {"automated": "a passing automated test",
                                "simulated": "fake/replayed telemetry drove it",
                                "manual": "physically observed on hardware"},
            "stages": [s.as_payload() for s in self.stages],
        }

    def as_json(self) -> str:
        return json.dumps(self.as_json_payload(), indent=2, sort_keys=False, ensure_ascii=True)

    def as_markdown(self) -> str:
        v, reason = compute_verdict(self.stages)
        ev = self.evidence if isinstance(self.evidence, Mapping) else {}
        lines = [
            f"# Race-Day Certification — {_norm(self.scenario) or 'controlled event'}",
            "",
            f"**Verdict: {v.value.replace('_', ' ').upper()}**",
            "",
            f"> {reason}",
            "",
            "## Evidence",
            "",
            "| Field | Value |",
            "| --- | --- |",
        ]
        for k in EVIDENCE_FIELDS:
            val = ev.get(k)
            if val is None or val == "" or val == []:
                continue
            lines.append(f"| {k} | {_norm(val)} |")
        lines += [
            "",
            "## Stages",
            "",
            "Evidence: **automated** = passing test · **simulated** = fake/replayed telemetry · "
            "**manual** = physically observed on hardware. A physical stage is only credited on "
            "*manual* evidence.",
            "",
            "| # | Stage | Recorded | Effective | Evidence | Notes |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
        for i, s in enumerate(self.stages, 1):
            note = _norm(s.detail) or _norm(s.notes)
            if s.credited_downgraded:
                note = (note + "  ⚠ not credited — physical gate needs manual evidence").strip()
            lines.append(
                f"| {i} | {s.spec.title}{' 🖐' if s.spec.physical else ''} | "
                f"{s.state.value} | {s.effective_state.value} | {s.evidence.value} | {note} |")
        lims = sorted({l for s in self.stages for l in s.limitations if _norm(l)})
        if lims:
            lines += ["", "## Known limitations", ""] + [f"- {l}" for l in lims]
        lines += ["", f"_{RACE_CERTIFICATION_VERSION}_", ""]
        return "\n".join(lines)


def new_report(scenario: str, *, evidence: Optional[Mapping] = None) -> RaceCertificationReport:
    return RaceCertificationReport(scenario=_norm(scenario), stages=initial_stages(),
                                   evidence=dict(evidence or {}))


def report_from_payload(payload: Optional[Mapping]) -> RaceCertificationReport:
    """Reconstruct a report from a saved JSON payload (for reload/re-export). Unknown stage keys are
    dropped; missing stages fall back to NOT_TESTED, so a report always covers the canonical stages
    in canonical order. Never raises."""
    p = payload if isinstance(payload, Mapping) else {}
    by_key = {}
    for s in (p.get("stages") or []):
        if isinstance(s, Mapping) and _norm(s.get("key")):
            by_key[_norm(s.get("key"))] = s
    stages = []
    for spec in STAGE_SPECS:
        s = by_key.get(spec.key, {})
        try:
            st = StageState(_norm(s.get("recorded_state") or s.get("state")).lower())
        except ValueError:
            st = StageState.NOT_TESTED
        try:
            ev = EvidenceKind(_norm(s.get("evidence")).lower())
        except ValueError:
            ev = EvidenceKind.NONE
        lims = tuple(_norm(l) for l in (s.get("limitations") or ()) if _norm(l))
        stages.append(StageResult(spec=spec, state=st, evidence=ev,
                                  detail=_norm(s.get("detail")), notes=_norm(s.get("notes")),
                                  limitations=lims))
    return RaceCertificationReport(scenario=_norm(p.get("scenario")), stages=tuple(stages),
                                   evidence=dict(p.get("evidence") or {}))
