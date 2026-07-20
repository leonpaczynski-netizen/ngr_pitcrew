"""Release-Candidate Manifest + Manual-UAT Readiness evaluator — pure (Program 2, Phase 71).

WHY IT EXISTS
  Manual UAT must run against ONE exact build. This module identifies that build (branch, commit, DB /
  rule-engine versions, test + bench totals, listener + runtime-file status) and issues an HONEST readiness
  decision for physical UAT. It cleanly separates the evidence tiers — automated regression, bench UAT,
  manual desktop UAT, physical voice/PTT UAT, PSVR2 UAT, live-GT7 UAT and operational certification — and
  never conflates them.

READINESS RULES (no hidden scoring, no AI, no optimistic default)
  • OPERATIONALLY_CERTIFIED is impossible while ANY required physical/live area is not PASS (and it also
    requires an explicit operational grant). Green unit tests alone, or green bench alone, can never reach it.
  • A failed safety / strategy-authority / telemetry-integrity / certification-integrity check → NOT_READY.
  • Missing optional hardware may yield only CONDITIONAL readiness where the area is not required for the
    intended stage.
  • Otherwise, with green automated regression + green bench + no manual FAIL → READY_FOR_MANUAL_UAT (the
    normal pre-physical maximum).
  Pure, deterministic, Qt-free, DB-free; never raises.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

from strategy.manual_uat_evidence import (
    ManualUatLedger, ManualUatStatus, required_physical_live_areas, MANUAL_UAT_AREAS,
)

RELEASE_CANDIDATE_MANIFEST_VERSION = "release_candidate_manifest_v1"


def _norm(v) -> str:
    return str(v if v is not None else "").strip()


def _fp(payload) -> str:
    return (f"{RELEASE_CANDIDATE_MANIFEST_VERSION}:"
            + hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"),
                                        ensure_ascii=True, default=str).encode()).hexdigest()[:24])


class ManualUatReadiness(str, Enum):
    NOT_READY_FOR_MANUAL_UAT = "not_ready_for_manual_uat"
    CONDITIONAL_FOR_MANUAL_UAT = "conditional_for_manual_uat"
    READY_FOR_MANUAL_UAT = "ready_for_manual_uat"
    OPERATIONALLY_CERTIFIED = "operationally_certified"


@dataclass(frozen=True)
class ManualUatReadinessResult:
    readiness: ManualUatReadiness
    blockers: Tuple[str, ...]
    caveats: Tuple[str, ...]
    rationale: str
    required_physical_live_areas: Tuple[str, ...]
    physical_live_passed: Tuple[str, ...]
    active_candidate_commit: str = ""
    historical_observation_count: int = 0
    fingerprint: str = ""

    def to_dict(self) -> dict:
        return {"readiness": self.readiness.value, "blockers": list(self.blockers),
                "caveats": list(self.caveats), "rationale": self.rationale,
                "required_physical_live_areas": list(self.required_physical_live_areas),
                "physical_live_passed": list(self.physical_live_passed),
                "active_candidate_commit": self.active_candidate_commit,
                "historical_observation_count": int(self.historical_observation_count),
                "fingerprint": self.fingerprint}


def evaluate_manual_uat_readiness(
    *,
    automated_tests_passed: bool,
    automated_tests_failed: int = 0,
    bench_ready: bool = False,
    bench_safety_failures: int = 0,
    bench_certification_integrity_failures: int = 0,
    safety_checks_ok: bool = True,
    telemetry_integrity_ok: bool = True,
    strategy_authority_ok: bool = True,
    ledger: Optional[ManualUatLedger] = None,
    operationally_granted: bool = False,
    active_candidate_commit: str = "",
) -> ManualUatReadinessResult:
    """The ONE pure readiness evaluator. Returns the honest decision + blockers + rationale. Manual evidence
    is CANDIDATE-SCOPED: only observations whose ``candidate_commit`` equals ``active_candidate_commit`` count
    (DEF-UAT-072-001 — evidence from a different commit can never certify the current candidate). Never raises.
    """
    try:
        led = ledger if isinstance(ledger, ManualUatLedger) else ManualUatLedger()
        cand = _norm(active_candidate_commit)
        req = required_physical_live_areas()
        passed = tuple(a for a in req if led.status_of(a, cand) == ManualUatStatus.PASS)
        physical_all_pass = len(passed) == len(req) and len(req) > 0
        historical = sum(1 for o in led.observations if _norm(o.candidate_commit) != cand)

        blockers: List[str] = []
        caveats: List[str] = []
        if not automated_tests_passed or int(automated_tests_failed or 0) > 0:
            blockers.append("automated regression is not green")
        if not safety_checks_ok:
            blockers.append("a safety check failed")
        if not telemetry_integrity_ok:
            blockers.append("telemetry-integrity check failed")
        if not strategy_authority_ok:
            blockers.append("strategy-authority check failed")
        if int(bench_safety_failures or 0) > 0:
            blockers.append(f"{int(bench_safety_failures)} bench safety failure(s)")
        if int(bench_certification_integrity_failures or 0) > 0:
            blockers.append(f"{int(bench_certification_integrity_failures)} certification-integrity failure(s)")
        # a proven manual FAIL on any area (for THIS candidate) is a defect that blocks the candidate
        failed_areas = [a for a in {o.area for o in led.observations}
                        if led.status_of(a, cand) == ManualUatStatus.FAIL]
        for a in sorted(set(failed_areas)):
            blockers.append(f"manual FAIL on '{a}'")
        if not bench_ready:
            # bench not green is a blocker for manual UAT readiness (it is a software gate)
            blockers.append("bench UAT is not green")

        # blocked (not failed) areas for THIS candidate → caveats, and cap to conditional
        blocked_areas = sorted({a for a in {o.area for o in led.observations}
                                if led.status_of(a, cand) == ManualUatStatus.BLOCKED})
        for a in blocked_areas:
            caveats.append(f"manual area '{a}' is BLOCKED (retest required)")

        if blockers:
            readiness = ManualUatReadiness.NOT_READY_FOR_MANUAL_UAT
            rationale = "Not ready — resolve the blockers before manual UAT."
        elif physical_all_pass and operationally_granted:
            readiness = ManualUatReadiness.OPERATIONALLY_CERTIFIED
            rationale = ("All required physical/live areas passed real UAT and an operational grant was "
                         "given — operationally certified.")
        elif physical_all_pass and not operationally_granted:
            readiness = ManualUatReadiness.CONDITIONAL_FOR_MANUAL_UAT
            caveats.append("all physical/live areas passed but no explicit operational grant is recorded")
            rationale = "All physical/live evidence passed; awaiting the explicit operational grant."
        elif blocked_areas:
            readiness = ManualUatReadiness.CONDITIONAL_FOR_MANUAL_UAT
            rationale = "Conditionally ready — some manual areas are blocked pending hardware/retest."
        else:
            readiness = ManualUatReadiness.READY_FOR_MANUAL_UAT
            caveats.append("physical microphone, wheel/PTT, TTS, PSVR2 and live GT7 remain untested until "
                           "real UAT evidence is recorded")
            rationale = ("Automated regression + bench UAT are green and no safety/integrity/manual failure "
                         "exists — ready for manual UAT. Physical/live areas are not yet certified.")

        if historical:
            caveats.append(f"{historical} historical observation(s) from a different candidate are viewable "
                           "but do NOT count toward this candidate")

        result = ManualUatReadinessResult(
            readiness=readiness, blockers=tuple(blockers), caveats=tuple(caveats), rationale=rationale,
            required_physical_live_areas=req, physical_live_passed=passed, active_candidate_commit=cand,
            historical_observation_count=historical)
        return _stamp_readiness(result)
    except Exception:  # pragma: no cover - defensive
        return _stamp_readiness(ManualUatReadinessResult(
            ManualUatReadiness.NOT_READY_FOR_MANUAL_UAT, ("evaluator error",), (),
            "evaluator error — treated as not ready", (), ()))


def _stamp_readiness(r: ManualUatReadinessResult) -> ManualUatReadinessResult:
    import dataclasses
    payload = {"readiness": r.readiness.value, "blockers": sorted(r.blockers),
               "cand": r.active_candidate_commit,
               "passed": sorted(r.physical_live_passed)}
    return dataclasses.replace(r, fingerprint=_fp(payload))


# --------------------------------------------------------------------------- #
# The release-candidate manifest
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class ReleaseCandidateManifest:
    branch: str
    commit: str
    parent_commit: str
    db_version: int
    rule_engine_version: str
    # evidence tiers (kept explicitly separate)
    automated_tests_passed: int
    automated_tests_skipped: int
    automated_tests_failed: int
    bench_total: int
    bench_passed: int
    bench_failed: int
    bench_ready: bool
    modified_file_summary: str
    schema_migration_status: str
    listener_status: str
    runtime_file_integrity: str
    required_manual_areas: Tuple[str, ...]
    manual_results: Tuple[dict, ...]
    known_blockers: Tuple[str, ...]
    known_caveats: Tuple[str, ...]
    readiness: ManualUatReadinessResult
    fingerprint: str = ""

    def as_payload(self) -> dict:
        return {"branch": _norm(self.branch), "commit": _norm(self.commit),
                "parent_commit": _norm(self.parent_commit), "db_version": int(self.db_version),
                "rule_engine_version": _norm(self.rule_engine_version),
                "automated_tests_passed": int(self.automated_tests_passed),
                "automated_tests_skipped": int(self.automated_tests_skipped),
                "automated_tests_failed": int(self.automated_tests_failed),
                "bench_total": int(self.bench_total), "bench_passed": int(self.bench_passed),
                "bench_failed": int(self.bench_failed), "bench_ready": bool(self.bench_ready),
                "modified_file_summary": _norm(self.modified_file_summary),
                "schema_migration_status": _norm(self.schema_migration_status),
                "listener_status": _norm(self.listener_status),
                "runtime_file_integrity": _norm(self.runtime_file_integrity),
                "required_manual_areas": list(self.required_manual_areas),
                "manual_results": list(self.manual_results),
                "known_blockers": list(self.known_blockers), "known_caveats": list(self.known_caveats),
                "readiness": self.readiness.to_dict()}

    def to_dict(self) -> dict:
        d = self.as_payload()
        d["fingerprint"] = self.fingerprint
        # explicit tier separation for the reader
        d["evidence_tiers"] = {
            "automated_regression": f"{self.automated_tests_passed} passed / "
                                    f"{self.automated_tests_skipped} skipped / {self.automated_tests_failed} failed",
            "bench_uat": f"{self.bench_passed}/{self.bench_total} passed (ready={self.bench_ready})",
            "manual_desktop_uat": "user evidence required",
            "physical_voice_ptt_uat": "user evidence required",
            "psvr2_uat": "user evidence required",
            "live_gt7_uat": "user evidence required",
            "operational_certification": self.readiness.readiness.value,
        }
        return d


def build_release_candidate_manifest(
    *,
    branch: str,
    commit: str,
    parent_commit: str = "",
    db_version: int = 0,
    rule_engine_version: str = "",
    automated_tests_passed: int = 0,
    automated_tests_skipped: int = 0,
    automated_tests_failed: int = 0,
    bench_total: int = 0,
    bench_passed: int = 0,
    bench_failed: int = 0,
    bench_ready: bool = False,
    bench_safety_failures: int = 0,
    bench_certification_integrity_failures: int = 0,
    modified_file_summary: str = "",
    schema_migration_status: str = "",
    listener_status: str = "",
    runtime_file_integrity: str = "",
    safety_checks_ok: bool = True,
    telemetry_integrity_ok: bool = True,
    strategy_authority_ok: bool = True,
    ledger: Optional[ManualUatLedger] = None,
    operationally_granted: bool = False,
) -> ReleaseCandidateManifest:
    """Assemble the manifest for ONE exact build and evaluate its manual-UAT readiness. Pure; never raises."""
    led = ledger if isinstance(ledger, ManualUatLedger) else ManualUatLedger()
    cand = _norm(commit)
    # The manifest is THE candidate: readiness + per-area results are scoped to THIS commit so evidence
    # from any other candidate is viewable history but never counts here (DEF-UAT-072-001).
    readiness = evaluate_manual_uat_readiness(
        automated_tests_passed=(automated_tests_failed == 0 and automated_tests_passed > 0),
        automated_tests_failed=automated_tests_failed, bench_ready=bench_ready,
        bench_safety_failures=bench_safety_failures,
        bench_certification_integrity_failures=bench_certification_integrity_failures,
        safety_checks_ok=safety_checks_ok, telemetry_integrity_ok=telemetry_integrity_ok,
        strategy_authority_ok=strategy_authority_ok, ledger=led,
        operationally_granted=operationally_granted, active_candidate_commit=cand)
    manual_results = tuple({"area": a.key, "category": a.category,
                            "status": led.status_of(a.key, cand).value,
                            "retest_required": (led.active(a.key, cand).retest_required
                                                if led.active(a.key, cand) is not None else False)}
                           for a in MANUAL_UAT_AREAS)
    m = ReleaseCandidateManifest(
        branch=_norm(branch), commit=_norm(commit), parent_commit=_norm(parent_commit),
        db_version=int(db_version), rule_engine_version=_norm(rule_engine_version),
        automated_tests_passed=int(automated_tests_passed),
        automated_tests_skipped=int(automated_tests_skipped),
        automated_tests_failed=int(automated_tests_failed), bench_total=int(bench_total),
        bench_passed=int(bench_passed), bench_failed=int(bench_failed), bench_ready=bool(bench_ready),
        modified_file_summary=_norm(modified_file_summary),
        schema_migration_status=_norm(schema_migration_status), listener_status=_norm(listener_status),
        runtime_file_integrity=_norm(runtime_file_integrity),
        required_manual_areas=required_physical_live_areas(), manual_results=manual_results,
        known_blockers=readiness.blockers, known_caveats=readiness.caveats, readiness=readiness)
    import dataclasses
    return dataclasses.replace(m, fingerprint=_fp(m.as_payload()))


def release_candidate_manifest_versions() -> dict:
    return {"release_candidate_manifest": RELEASE_CANDIDATE_MANIFEST_VERSION}
