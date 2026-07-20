"""Operational certification (Program 2, Phase 53).

An explicit certification report over the primary experience. Certification CANNOT be granted at a live
or operational level through automated tests alone — the overall state is bounded by the weakest area's
proof level, and live/operational states require live-GT7 evidence. This module aggregates per-area proof
into an honest overall state; it never fabricates a higher level than the evidence supports.

Purity: Qt-free, DB-free, offline, deterministic, no wall-clock, never raises.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import Enum
from typing import Sequence, Tuple

OPERATIONAL_CERTIFICATION_VERSION = "operational_certification_v1"


def _norm(v) -> str:
    return str(v if v is not None else "").strip()


def _dumps(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str, ensure_ascii=True,
                      allow_nan=False)


def _fp(payload) -> str:
    return (f"{OPERATIONAL_CERTIFICATION_VERSION}:"
            + hashlib.sha256(_dumps(payload).encode("utf-8")).hexdigest()[:24])


class ProofLevel(str, Enum):
    NOT_TESTED = "not_tested"
    AUTOMATED = "automated"
    OFFSCREEN = "offscreen"
    VISUAL_PARTIAL = "visual_partial"
    LIVE_PARTIAL = "live_partial"
    LIVE_VALIDATED = "live_validated"


_PROOF_ORDER = (ProofLevel.NOT_TESTED, ProofLevel.AUTOMATED, ProofLevel.OFFSCREEN,
                ProofLevel.VISUAL_PARTIAL, ProofLevel.LIVE_PARTIAL, ProofLevel.LIVE_VALIDATED)


class CertificationState(str, Enum):
    NOT_TESTED = "not_tested"
    AUTOMATED_ONLY = "automated_only"
    OFFSCREEN_VALIDATED = "offscreen_validated"
    VISUAL_UAT_PARTIAL = "visual_uat_partial"
    LIVE_GT7_PARTIAL = "live_gt7_partial"
    LIVE_GT7_VALIDATED = "live_gt7_validated"
    OPERATIONALLY_READY_WITH_LIMITATIONS = "operationally_ready_with_limitations"
    OPERATIONALLY_READY = "operationally_ready"


_LEVEL_TO_STATE = {
    ProofLevel.NOT_TESTED: CertificationState.NOT_TESTED,
    ProofLevel.AUTOMATED: CertificationState.AUTOMATED_ONLY,
    ProofLevel.OFFSCREEN: CertificationState.OFFSCREEN_VALIDATED,
    ProofLevel.VISUAL_PARTIAL: CertificationState.VISUAL_UAT_PARTIAL,
    ProofLevel.LIVE_PARTIAL: CertificationState.LIVE_GT7_PARTIAL,
    ProofLevel.LIVE_VALIDATED: CertificationState.LIVE_GT7_VALIDATED,
}


@dataclass(frozen=True)
class CertificationArea:
    name: str
    proof_level: ProofLevel
    note: str = ""

    def as_payload(self) -> dict:
        return {"name": _norm(self.name), "proof_level": self.proof_level.value, "note": _norm(self.note)}


@dataclass(frozen=True)
class OperationalCertification:
    overall_state: CertificationState
    areas: Tuple[CertificationArea, ...]
    weakest_area: str
    note: str
    fingerprint: str = ""

    def as_payload(self) -> dict:
        return {"overall_state": self.overall_state.value,
                "areas": [a.as_payload() for a in sorted(self.areas, key=lambda a: _norm(a.name))],
                "weakest_area": _norm(self.weakest_area), "note": _norm(self.note)}


def build_certification(areas: Sequence[CertificationArea], *,
                        operationally_ready_granted: bool = False) -> OperationalCertification:
    """Aggregate per-area proof into the honest overall state. The overall state is the WEAKEST area's
    proof level. OPERATIONALLY_READY(_WITH_LIMITATIONS) is only reachable with live evidence AND an
    explicit human grant — never from automated/offscreen evidence alone."""
    areas = tuple(areas)
    if not areas:
        return OperationalCertification(CertificationState.NOT_TESTED, (), "",
                                        "no certification areas provided",
                                        _fp({"empty": True}))
    weakest = min(areas, key=lambda a: _PROOF_ORDER.index(a.proof_level))
    overall = _LEVEL_TO_STATE[weakest.proof_level]

    # OPERATIONALLY_READY only when a human explicitly grants it AND every area is live-validated;
    # WITH_LIMITATIONS when a human grants it AND every area has at least live-partial evidence.
    if operationally_ready_granted:
        min_idx = _PROOF_ORDER.index(weakest.proof_level)
        if min_idx >= _PROOF_ORDER.index(ProofLevel.LIVE_VALIDATED):
            overall = CertificationState.OPERATIONALLY_READY
        elif min_idx >= _PROOF_ORDER.index(ProofLevel.LIVE_PARTIAL):
            overall = CertificationState.OPERATIONALLY_READY_WITH_LIMITATIONS
        # else: a grant with only automated/offscreen evidence is ignored (cannot fabricate readiness)

    note = (f"overall bounded by weakest area '{weakest.name}' ({weakest.proof_level.value}); "
            "live/operational certification requires live-GT7 evidence and cannot come from automated "
            "tests alone.")
    cert = OperationalCertification(overall, areas, weakest.name, note, "")
    return OperationalCertification(cert.overall_state, cert.areas, cert.weakest_area, cert.note,
                                    _fp(cert.as_payload()))
