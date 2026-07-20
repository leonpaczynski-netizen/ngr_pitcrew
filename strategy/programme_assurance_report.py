"""Programme Knowledge Assurance & Audit Report — pure orchestration (Program 2, Phase 31).

The FINAL layer of Program 2. It audits the whole knowledge programme - re-validation (26), coverage
(27), readiness (28), contradiction (29) and assumptions (30) - for assurance defects, and grades
whether the engineering knowledge can be ASSURED. A single BLOCKING finding prevents ASSURED. The
grade is rule-based over visible severity counts, not an opaque score. It reports findings only; it
authors no setup, schedules no test, and changes nothing.

Purity: Qt-free, DB-free, UI-free, network-free, AI-free; no random, no wall-clock; deterministic;
never raises.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import List, Mapping, Optional, Tuple

from strategy.assurance_finding import (
    ASSURANCE_FINDING_VERSION, ASSURANCE_SEVERITY_PRIORITY,
)
from strategy.knowledge_assurance import (
    KNOWLEDGE_ASSURANCE_VERSION, audit,
)
from strategy.assurance_grade import (
    ASSURANCE_GRADE_VERSION, grade_assurance,
)

PROGRAMME_ASSURANCE_REPORT_VERSION = "programme_assurance_report_v1"
PROGRAMME_ASSURANCE_REPORT_SCHEMA = 1

_SAFETY = ("Read-only knowledge assurance & audit report. It audits the knowledge products for "
           "assurance defects and grades whether the knowledge can be assured - a single blocking "
           "finding prevents ASSURED, and the grade is rule-based over visible counts, never an "
           "opaque score. It carries no setup values and recommends / schedules / applies / mutates "
           "NOTHING. Completion stays governed by Phase 18 and the frozen Apply gate remains the "
           "sole route to the car.")


def _lc(v) -> str:
    return str(v if v is not None else "").strip().lower()


@dataclass(frozen=True)
class ProgrammeAssuranceReport:
    schema_version: int
    source_programme: dict
    generated_from: dict
    assurance_grade: str
    grade_detail: dict
    findings: Tuple[dict, ...]
    blocking: Tuple[dict, ...]
    major: Tuple[dict, ...]
    moderate_minor: Tuple[dict, ...]
    informational: Tuple[dict, ...]
    audit_summary: str
    totals: dict
    empty_state: str
    safety_statement: str
    content_fingerprint: str
    knowledge_versions: dict
    eval_version: str = PROGRAMME_ASSURANCE_REPORT_VERSION

    def to_dict(self) -> dict:
        return {"schema_version": self.schema_version,
                "source_programme": dict(self.source_programme),
                "generated_from": dict(self.generated_from),
                "assurance_grade": self.assurance_grade, "grade_detail": dict(self.grade_detail),
                "findings": [dict(f) for f in self.findings],
                "blocking": [dict(f) for f in self.blocking],
                "major": [dict(f) for f in self.major],
                "moderate_minor": [dict(f) for f in self.moderate_minor],
                "informational": [dict(f) for f in self.informational],
                "audit_summary": self.audit_summary, "totals": dict(self.totals),
                "empty_state": self.empty_state, "safety_statement": self.safety_statement,
                "content_fingerprint": self.content_fingerprint,
                "knowledge_versions": dict(self.knowledge_versions),
                "eval_version": self.eval_version}


def build_programme_assurance_report(
        readiness: Optional[Mapping], contradiction: Optional[Mapping],
        assumptions: Optional[Mapping], coverage: Optional[Mapping], revalidation: Optional[Mapping],
        source_programme: Optional[Mapping] = None) -> ProgrammeAssuranceReport:
    """Assemble the assurance & audit report. Deterministic; never raises."""
    try:
        return _build(readiness or {}, contradiction or {}, assumptions or {}, coverage or {},
                      revalidation or {}, source_programme or {})
    except Exception as exc:   # never raise into the caller
        kv = knowledge_versions()
        return ProgrammeAssuranceReport(
            schema_version=PROGRAMME_ASSURANCE_REPORT_SCHEMA, source_programme={}, generated_from={},
            assurance_grade="insufficient_evidence", grade_detail={}, findings=(), blocking=(),
            major=(), moderate_minor=(), informational=(), audit_summary="Assurance report "
            "unavailable.", totals={}, empty_state="Assurance report unavailable.",
            safety_statement=_SAFETY,
            content_fingerprint=_fp({"error": type(exc).__name__, "kv": kv}), knowledge_versions=kv)


def _build(readiness: Mapping, contradiction: Mapping, assumptions: Mapping, coverage: Mapping,
           revalidation: Mapping, source_hint: Mapping) -> ProgrammeAssuranceReport:
    source = dict((readiness.get("source_programme") or source_hint) or {})
    findings, has_known = audit(readiness, contradiction, assumptions, coverage, revalidation)
    grade_detail = grade_assurance(findings, has_known)

    def bucket(*sev):
        return tuple(f for f in findings if _lc(f.get("severity")) in sev)

    blocking = bucket("blocking")
    major = bucket("major")
    moderate_minor = bucket("moderate", "minor")
    info = bucket("informational")

    totals = {"findings": len(findings), "blocking": len(blocking), "major": len(major),
              "moderate_minor": len(moderate_minor), "informational": len(info),
              "grade": grade_detail.get("grade"),
              "domains_with_findings": len({_lc(f.get("domain")) for f in findings if f.get("domain")})}

    summary = _audit_summary(grade_detail, totals)

    kv = knowledge_versions()
    fp = _fp({"src": {k: _lc(source.get(k)) for k in ("car", "discipline", "gt7_version", "driver")},
              "grade": grade_detail.get("grade"), "rule": grade_detail.get("rule"),
              "f": [(f["finding_type"], f["severity"], f["domain"]) for f in findings], "kv": kv})
    empty = "" if findings else ("No assurance findings - the audit produced nothing to report.")
    return ProgrammeAssuranceReport(
        schema_version=PROGRAMME_ASSURANCE_REPORT_SCHEMA,
        source_programme={k: str(source.get(k, "") or "")
                          for k in ("car", "discipline", "gt7_version", "driver")},
        generated_from={"phase26_fingerprint": _lc(revalidation.get("content_fingerprint")),
                        "phase27_fingerprint": _lc(coverage.get("content_fingerprint")),
                        "phase28_fingerprint": _lc(readiness.get("content_fingerprint")),
                        "phase29_fingerprint": _lc(contradiction.get("content_fingerprint")),
                        "phase30_fingerprint": _lc(assumptions.get("content_fingerprint")),
                        "authorities": ["Phase 26 re-validation", "Phase 27 coverage",
                                        "Phase 28 readiness", "Phase 29 contradiction",
                                        "Phase 30 assumptions"]},
        assurance_grade=grade_detail.get("grade"), grade_detail=grade_detail, findings=tuple(findings),
        blocking=blocking, major=major, moderate_minor=moderate_minor, informational=info,
        audit_summary=summary, totals=totals, empty_state=empty, safety_statement=_SAFETY,
        content_fingerprint=fp, knowledge_versions=kv)


def _audit_summary(grade_detail: Mapping, totals: Mapping) -> str:
    grade = _lc(grade_detail.get("grade")).replace("_", " ")
    reasons = "; ".join(grade_detail.get("reasons") or []) or "no findings"
    return (f"Assurance: {grade.upper()}. {totals.get('findings')} finding(s) - "
            f"{totals.get('blocking')} blocking, {totals.get('major')} major, "
            f"{totals.get('moderate_minor')} moderate/minor. Grade basis: {reasons}. A single "
            "blocking finding prevents ASSURED; the grade is rule-based over visible counts.")


def knowledge_versions() -> dict:
    return {"programme_assurance_report": PROGRAMME_ASSURANCE_REPORT_VERSION,
            "knowledge_assurance": KNOWLEDGE_ASSURANCE_VERSION,
            "assurance_grade": ASSURANCE_GRADE_VERSION,
            "assurance_finding": ASSURANCE_FINDING_VERSION,
            "schema": PROGRAMME_ASSURANCE_REPORT_SCHEMA}


def _fp(payload: dict) -> str:
    return (f"{PROGRAMME_ASSURANCE_REPORT_VERSION}:"
            + hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"),
                                        default=str).encode()).hexdigest()[:24])
