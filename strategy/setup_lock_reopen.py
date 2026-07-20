"""Setup-lock reopening authority (Program 2, Phase 53 — Audit C remediation).

A locked/mature setup must RESIST noise (one noisy lap, one isolated subjective complaint) while remaining
open to valid evidence. This module classifies the eight distinct reopening triggers into an explicit,
reasoned decision. It reopens NOTHING itself — it reports eligibility; an actual reopen is an explicit
user action through the canonical lock workflow.

Purity: Qt-free, DB-free, offline, deterministic, no wall-clock, never raises. No setup values.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import Enum

SETUP_LOCK_REOPEN_VERSION = "setup_lock_reopen_v1"


def _norm(v) -> str:
    return str(v if v is not None else "").strip()


def _dumps(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str, ensure_ascii=True,
                      allow_nan=False)


def _fp(payload) -> str:
    return (f"{SETUP_LOCK_REOPEN_VERSION}:"
            + hashlib.sha256(_dumps(payload).encode("utf-8")).hexdigest()[:24])


class SetupLockReopenReason(str, Enum):
    NONE = "none"
    NOISE_ONLY = "noise_only"                       # one noisy lap — NOT eligible
    SUBJECTIVE_ONLY = "subjective_only"             # one isolated complaint — NOT eligible
    CONFIRMED_CRITICAL_REGRESSION = "confirmed_critical_regression"
    EVENT_CONTEXT_REVISION = "event_context_revision"
    FINGERPRINT_MISMATCH = "fingerprint_mismatch"
    RULES_CHANGE = "rules_change"
    PHYSICS_VERSION_CHANGE = "physics_version_change"
    INDEPENDENT_CORROBORATED_EVIDENCE = "independent_corroborated_evidence"
    EXPLICIT_DRIVER_OVERRIDE = "explicit_driver_override"


@dataclass(frozen=True)
class SetupLockReopenDecision:
    eligible: bool
    reason: SetupLockReopenReason
    requires_visible_consequence: bool
    note: str
    fingerprint: str = ""

    def as_payload(self) -> dict:
        return {"eligible": bool(self.eligible), "reason": self.reason.value,
                "requires_visible_consequence": bool(self.requires_visible_consequence),
                "note": _norm(self.note)}


def assess_lock_reopen(*, noisy_lap: bool = False, subjective_complaint: bool = False,
                       corroborated_regression: bool = False, critical_instability: bool = False,
                       event_context_revision: bool = False, fingerprint_mismatch: bool = False,
                       rules_change: bool = False, physics_version_change: bool = False,
                       independent_corroborated_evidence: bool = False,
                       explicit_override: bool = False) -> SetupLockReopenDecision:
    """Deterministic reopening eligibility. Valid triggers (in priority order) make reopening ELIGIBLE;
    noise / an isolated subjective complaint alone never do. An explicit driver override is eligible but
    always carries a visible consequence."""
    R = SetupLockReopenReason

    def _d(reason, eligible, consequence, note):
        d = SetupLockReopenDecision(eligible, reason, consequence, note, "")
        return SetupLockReopenDecision(d.eligible, d.reason, d.requires_visible_consequence, d.note,
                                       _fp(d.as_payload()))

    if explicit_override:
        return _d(R.EXPLICIT_DRIVER_OVERRIDE, True, True,
                  "reopened by explicit driver override — the consequence must be shown")
    if corroborated_regression and critical_instability:
        return _d(R.CONFIRMED_CRITICAL_REGRESSION, True, True,
                  "repeated, corroborated critical instability — reopening is warranted")
    if critical_instability and corroborated_regression is False and independent_corroborated_evidence:
        return _d(R.CONFIRMED_CRITICAL_REGRESSION, True, True,
                  "corroborated critical instability — reopening is warranted")
    if event_context_revision:
        return _d(R.EVENT_CONTEXT_REVISION, True, False,
                  "the event context changed — prior evidence may no longer apply")
    if fingerprint_mismatch:
        return _d(R.FINGERPRINT_MISMATCH, True, False,
                  "the applied setup no longer matches the locked fingerprint")
    if rules_change:
        return _d(R.RULES_CHANGE, True, False, "a material rules change affects the locked setup")
    if physics_version_change:
        return _d(R.PHYSICS_VERSION_CHANGE, True, False,
                  "a GT7 physics-version change may invalidate the locked setup")
    if corroborated_regression or independent_corroborated_evidence:
        return _d(R.INDEPENDENT_CORROBORATED_EVIDENCE, True, False,
                  "independently corroborated new evidence supports reopening")
    # only noise / subjective — resist
    if noisy_lap and not subjective_complaint:
        return _d(R.NOISE_ONLY, False, False, "a single noisy lap does not reopen a mature setup")
    if subjective_complaint:
        return _d(R.SUBJECTIVE_ONLY, False, False,
                  "an isolated subjective complaint does not reopen a mature setup")
    return _d(R.NONE, False, False, "no reopening trigger present")
