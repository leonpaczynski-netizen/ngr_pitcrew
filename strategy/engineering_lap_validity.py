"""Canonical engineering lap-validity authority (Engineering Brain Phase 4).

ONE deterministic domain service answering "is this lap valid for setup
engineering / outcome comparison?" — with purpose-specific policy and every
rejection reason preserved. It unifies the previously-scattered clean-lap rules:

  * `data/recommendation_scoring.aggregate_lap_window` — flags only (is_pit_lap,
    is_out_lap); the OFR-1 / Phase-3 authority.
  * `strategy/practice_capture.resolve_clean_lap` — adds a pace-outlier gate
    (lap_time ≤ best × ratio); the live practice / perfect-lap authority.
  * `strategy/cross_lap_persistence.LapMeta.representative` — the richest
    rejection-reason vocabulary (dormant).

Doctrine: prefer correctly-scoped, repeatable, lower-volume evidence over larger
but noisy/mis-associated counts. A fastest lap is not proof; an out/in/pit/heavily
interrupted lap must never influence setup conclusions; evidence from the wrong
applied setup must not enter the comparison; unknown stays unknown.

Purity: Qt-free, DB-free, UI-free, network-free, AI-free; never raises for
ordinary missing data (a lap it cannot judge is UNRESOLVED, not an exception).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Mapping, Optional, Tuple


ENG_LAP_VALIDITY_VERSION = "eng_lap_v1"


class LapValidityStatus(str, Enum):
    VALID = "valid"
    VALID_WITH_LIMITATIONS = "valid_with_limitations"
    INVALID = "invalid"
    UNRESOLVED = "unresolved"          # not enough information to judge


class LapPurpose(str, Enum):
    """Different consumers need different policies over the SAME evidence."""

    SETUP_ENGINEERING = "setup_engineering"
    OUTCOME_COMPARISON = "outcome_comparison"
    PRACTICE_PATTERN = "practice_pattern"
    PERFECT_LAP_REFERENCE = "perfect_lap_reference"
    RACE_STRATEGY = "race_strategy"


# Rejection reason codes (stable strings; provenance-preserving).
R_PIT_LAP = "pit_lap"
R_OUT_LAP = "out_lap"
R_IN_LAP = "in_lap"
R_OFF_TRACK = "off_track"
R_INCIDENT = "incident"
R_INCOMPLETE = "incomplete_lap"
R_IMPLAUSIBLE_TIME = "implausible_lap_time"
R_PACE_OUTLIER = "pace_outlier"
R_MISSING_TELEMETRY = "missing_telemetry"
R_MIN_SAMPLES = "insufficient_samples"
R_SETUP_MISMATCH = "setup_mismatch"
R_LAYOUT_MISMATCH = "track_layout_mismatch"
R_DAMAGE = "damage_or_interruption"


@dataclass(frozen=True)
class LapValidityPolicy:
    """Purpose-specific policy. One authority, purpose-specific knobs."""

    reject_pit: bool = True
    reject_out: bool = True
    reject_in: bool = True
    reject_off_track: bool = True          # any off-track → reject (else limitation)
    off_track_limitation_max: int = 0      # ≤ this many off-tracks → limitation, not reject
    reject_pace_outlier: bool = True
    pace_outlier_ratio: float = 1.07       # lap_time > best×ratio → outlier
    reject_incident: bool = True
    require_min_samples: int = 0           # 0 = don't gate on samples
    limitation_on_missing_telemetry: bool = True


# Purpose → policy. Setup engineering + outcome comparison + perfect-lap are the
# strictest; race strategy tolerates pace outliers (fuel is what matters).
_POLICIES = {
    LapPurpose.SETUP_ENGINEERING: LapValidityPolicy(),
    LapPurpose.OUTCOME_COMPARISON: LapValidityPolicy(),
    LapPurpose.PRACTICE_PATTERN: LapValidityPolicy(
        reject_pace_outlier=False, off_track_limitation_max=1),
    LapPurpose.PERFECT_LAP_REFERENCE: LapValidityPolicy(
        pace_outlier_ratio=1.05, off_track_limitation_max=0),
    LapPurpose.RACE_STRATEGY: LapValidityPolicy(
        reject_pace_outlier=False, reject_off_track=False,
        off_track_limitation_max=99, reject_incident=False),
}


def policy_for(purpose: LapPurpose) -> LapValidityPolicy:
    return _POLICIES.get(purpose, LapValidityPolicy())


@dataclass(frozen=True)
class EngineeringLapValidity:
    """The authoritative per-lap validity verdict for one purpose."""

    lap_id: Optional[str]
    lap_num: Optional[int]
    session_id: Optional[str]
    run_id: Optional[str]
    scope_fingerprint: str
    setup_id: str
    applied_checkpoint_id: str
    experiment_id: Optional[str]
    purpose: LapPurpose
    status: LapValidityStatus
    accepted: bool
    rejection_reasons: Tuple[str, ...]
    primary_rejection_reason: str
    limitations: Tuple[str, ...]
    provenance: str
    telemetry_completeness: str            # full / partial / missing / unknown
    setup_identity_confidence: str         # high / medium / low / unknown
    track_layout_confidence: str
    corner_resolution_ready: bool
    is_warmup: bool
    is_out_lap: bool
    is_in_lap: bool
    is_pit_lap: bool
    off_track: bool
    incident: bool
    damage_or_interruption: str            # yes / no / unknown
    lap_time_plausible: str                # yes / no / unknown
    min_samples_ok: str                    # yes / no / unknown
    lap_time_ms: int
    eval_version: str = ENG_LAP_VALIDITY_VERSION

    def to_dict(self) -> dict:
        return {
            "lap_id": self.lap_id, "lap_num": self.lap_num,
            "session_id": self.session_id, "run_id": self.run_id,
            "scope_fingerprint": self.scope_fingerprint, "setup_id": self.setup_id,
            "applied_checkpoint_id": self.applied_checkpoint_id,
            "experiment_id": self.experiment_id, "purpose": self.purpose.value,
            "status": self.status.value, "accepted": self.accepted,
            "rejection_reasons": list(self.rejection_reasons),
            "primary_rejection_reason": self.primary_rejection_reason,
            "limitations": list(self.limitations), "provenance": self.provenance,
            "telemetry_completeness": self.telemetry_completeness,
            "setup_identity_confidence": self.setup_identity_confidence,
            "track_layout_confidence": self.track_layout_confidence,
            "corner_resolution_ready": self.corner_resolution_ready,
            "is_warmup": self.is_warmup, "is_out_lap": self.is_out_lap,
            "is_in_lap": self.is_in_lap, "is_pit_lap": self.is_pit_lap,
            "off_track": self.off_track, "incident": self.incident,
            "damage_or_interruption": self.damage_or_interruption,
            "lap_time_plausible": self.lap_time_plausible,
            "min_samples_ok": self.min_samples_ok, "lap_time_ms": self.lap_time_ms,
            "eval_version": self.eval_version,
        }


def _as_int(v, default=0) -> int:
    try:
        return int(v) if v is not None else default
    except (TypeError, ValueError):
        return default


# Ordering used to pick the single primary rejection reason (most decisive first).
_REASON_PRIORITY = (
    R_SETUP_MISMATCH, R_LAYOUT_MISMATCH, R_PIT_LAP, R_OUT_LAP, R_IN_LAP,
    R_INCOMPLETE, R_IMPLAUSIBLE_TIME, R_INCIDENT, R_OFF_TRACK, R_DAMAGE,
    R_PACE_OUTLIER, R_MISSING_TELEMETRY, R_MIN_SAMPLES,
)


def _primary(reasons) -> str:
    for r in _REASON_PRIORITY:
        if r in reasons:
            return r
    return next(iter(reasons), "")


def evaluate_engineering_lap(
    lap_row: Mapping,
    *,
    purpose: LapPurpose = LapPurpose.SETUP_ENGINEERING,
    scope_fingerprint: str = "",
    setup_id: str = "",
    applied_checkpoint_id: str = "",
    experiment_id: Optional[str] = None,
    run_id: Optional[str] = None,
    best_lap_ms: Optional[int] = None,
    expected_setup_id: Optional[str] = None,
    expected_checkpoint_id: Optional[str] = None,
    expected_track: Optional[str] = None,
    telemetry_sample_count: Optional[int] = None,
    corner_resolution_ready: Optional[bool] = None,
    provenance: str = "lap_records",
    policy: Optional[LapValidityPolicy] = None,
) -> EngineeringLapValidity:
    """Judge one ``lap_records`` row (dict-like) for a purpose. Deterministic;
    never raises. Missing signals stay 'unknown' and never fabricate a rejection.

    ``best_lap_ms`` enables the pace-outlier gate; ``expected_*`` enable
    setup/layout-mismatch rejection; ``telemetry_sample_count`` gates min-samples.
    """
    pol = policy or policy_for(purpose)
    if not isinstance(lap_row, Mapping):
        return EngineeringLapValidity(
            lap_id=None, lap_num=None, session_id=None, run_id=run_id,
            scope_fingerprint=scope_fingerprint, setup_id=setup_id,
            applied_checkpoint_id=applied_checkpoint_id, experiment_id=experiment_id,
            purpose=purpose, status=LapValidityStatus.UNRESOLVED, accepted=False,
            rejection_reasons=(), primary_rejection_reason="", limitations=(),
            provenance=provenance, telemetry_completeness="unknown",
            setup_identity_confidence="unknown", track_layout_confidence="unknown",
            corner_resolution_ready=bool(corner_resolution_ready),
            is_warmup=False, is_out_lap=False, is_in_lap=False, is_pit_lap=False,
            off_track=False, incident=False, damage_or_interruption="unknown",
            lap_time_plausible="unknown", min_samples_ok="unknown", lap_time_ms=0)

    lap_num = lap_row.get("lap_num")
    session_id = lap_row.get("session_id")
    lap_time_ms = _as_int(lap_row.get("lap_time_ms"), 0)
    is_pit = bool(_as_int(lap_row.get("is_pit_lap")))
    is_out = bool(_as_int(lap_row.get("is_out_lap")))
    # lap_records has no explicit in-lap flag; an is_pit_lap covers pit/in. Treat
    # an explicit 'is_in_lap' if a producer ever supplies it.
    is_in = bool(_as_int(lap_row.get("is_in_lap")))
    off_count = _as_int(lap_row.get("off_track_count"))
    off_track = off_count > 0

    reasons: list = []
    limitations: list = []

    # --- identity gates (strongest) -----------------------------------------
    setup_conf = "unknown"
    if expected_setup_id is not None and setup_id:
        if str(setup_id) == str(expected_setup_id):
            setup_conf = "high"
        else:
            setup_conf = "low"
            reasons.append(R_SETUP_MISMATCH)
    elif setup_id or applied_checkpoint_id:
        setup_conf = "medium"

    track_conf = "unknown"
    row_track = lap_row.get("track")
    if expected_track is not None and row_track:
        if str(row_track) == str(expected_track):
            track_conf = "high"
        else:
            track_conf = "low"
            reasons.append(R_LAYOUT_MISMATCH)
    elif row_track:
        track_conf = "medium"

    # --- lap-type gates ------------------------------------------------------
    if is_pit and pol.reject_pit:
        reasons.append(R_PIT_LAP)
    if is_out and pol.reject_out:
        reasons.append(R_OUT_LAP)
    if is_in and pol.reject_in:
        reasons.append(R_IN_LAP)

    # --- lap-time plausibility ----------------------------------------------
    if lap_time_ms <= 0:
        plausible = "no"
        reasons.append(R_INCOMPLETE if lap_time_ms == 0 else R_IMPLAUSIBLE_TIME)
    elif lap_time_ms < 10_000 or lap_time_ms > 1_200_000:
        plausible = "no"
        reasons.append(R_IMPLAUSIBLE_TIME)
    else:
        plausible = "yes"

    # --- off-track ----------------------------------------------------------
    if off_track:
        if off_count > pol.off_track_limitation_max:
            if pol.reject_off_track:
                reasons.append(R_OFF_TRACK)
            else:
                limitations.append(R_OFF_TRACK)
        else:
            limitations.append(R_OFF_TRACK)

    # --- incident (major spin / crash) — only when a producer flags it -------
    incident = bool(_as_int(lap_row.get("incident"))) or \
        bool(_as_int(lap_row.get("major_incident")))
    if incident and pol.reject_incident:
        reasons.append(R_INCIDENT)

    # --- damage / interruption (unknown unless flagged) ---------------------
    if lap_row.get("damage") is None:
        damage = "unknown"
    else:
        damage = "yes" if _as_int(lap_row.get("damage")) else "no"
        if damage == "yes":
            reasons.append(R_DAMAGE)

    # --- pace outlier -------------------------------------------------------
    if (pol.reject_pace_outlier and best_lap_ms and best_lap_ms > 0
            and plausible == "yes"):
        if lap_time_ms > best_lap_ms * pol.pace_outlier_ratio:
            reasons.append(R_PACE_OUTLIER)

    # --- min telemetry samples ----------------------------------------------
    if pol.require_min_samples > 0 and telemetry_sample_count is not None:
        min_ok = "yes" if telemetry_sample_count >= pol.require_min_samples else "no"
        if min_ok == "no":
            reasons.append(R_MIN_SAMPLES)
    elif telemetry_sample_count is None:
        min_ok = "unknown"
    else:
        min_ok = "yes"

    # --- telemetry completeness --------------------------------------------
    if telemetry_sample_count is None:
        completeness = "unknown"
    elif telemetry_sample_count <= 0:
        completeness = "missing"
        if pol.limitation_on_missing_telemetry:
            limitations.append(R_MISSING_TELEMETRY)
    elif telemetry_sample_count < 30:
        completeness = "partial"
        limitations.append(R_MISSING_TELEMETRY)
    else:
        completeness = "full"

    # warm-up: lap 1 of a session with no prior best is a warm-up limitation.
    is_warmup = (lap_num == 1 and (best_lap_ms is None or best_lap_ms <= 0))

    reasons_t = tuple(dict.fromkeys(reasons))       # de-dupe, keep order
    limitations_t = tuple(dict.fromkeys(limitations))
    if reasons_t:
        status = LapValidityStatus.INVALID
        accepted = False
    elif limitations_t:
        status = LapValidityStatus.VALID_WITH_LIMITATIONS
        accepted = True
    else:
        status = LapValidityStatus.VALID
        accepted = True

    cr_ready = (corner_resolution_ready if corner_resolution_ready is not None
                else completeness in ("full", "partial"))

    return EngineeringLapValidity(
        lap_id=(str(lap_row.get("id")) if lap_row.get("id") is not None else None),
        lap_num=(_as_int(lap_num) if lap_num is not None else None),
        session_id=(str(session_id) if session_id is not None else None),
        run_id=(str(run_id) if run_id is not None else None),
        scope_fingerprint=scope_fingerprint, setup_id=str(setup_id or ""),
        applied_checkpoint_id=str(applied_checkpoint_id or ""),
        experiment_id=(str(experiment_id) if experiment_id is not None else None),
        purpose=purpose, status=status, accepted=accepted,
        rejection_reasons=reasons_t, primary_rejection_reason=_primary(reasons_t),
        limitations=limitations_t, provenance=provenance,
        telemetry_completeness=completeness, setup_identity_confidence=setup_conf,
        track_layout_confidence=track_conf, corner_resolution_ready=bool(cr_ready),
        is_warmup=bool(is_warmup), is_out_lap=is_out, is_in_lap=is_in,
        is_pit_lap=is_pit, off_track=off_track, incident=incident,
        damage_or_interruption=damage, lap_time_plausible=plausible,
        min_samples_ok=min_ok, lap_time_ms=lap_time_ms)


@dataclass(frozen=True)
class LapValiditySummary:
    """Aggregate of per-lap verdicts for one session/purpose."""

    total_laps: int
    valid_laps: int
    limited_laps: int
    rejected_laps: int
    valid_lap_numbers: Tuple[int, ...]
    rejection_distribution: Mapping[str, int]
    purpose: LapPurpose
    eval_version: str = ENG_LAP_VALIDITY_VERSION

    @property
    def usable_laps(self) -> int:
        """Valid + valid-with-limitations (accepted) laps."""
        return self.valid_laps + self.limited_laps

    def to_dict(self) -> dict:
        return {
            "total_laps": self.total_laps, "valid_laps": self.valid_laps,
            "limited_laps": self.limited_laps, "rejected_laps": self.rejected_laps,
            "usable_laps": self.usable_laps,
            "valid_lap_numbers": list(self.valid_lap_numbers),
            "rejection_distribution": dict(self.rejection_distribution),
            "purpose": self.purpose.value, "eval_version": self.eval_version,
        }


def evaluate_session_laps(
    lap_rows,
    *,
    purpose: LapPurpose = LapPurpose.SETUP_ENGINEERING,
    scope_fingerprint: str = "",
    expected_setup_id: Optional[str] = None,
    expected_checkpoint_id: Optional[str] = None,
    expected_track: Optional[str] = None,
    **lap_kwargs,
) -> Tuple[Tuple[EngineeringLapValidity, ...], LapValiditySummary]:
    """Evaluate a session's laps → (per-lap verdicts, summary). The best clean lap
    (for the pace-outlier gate) is derived in a first pass over plausible,
    non-pit/out laps so the gate is order-independent and self-consistent."""
    rows = list(lap_rows or [])
    # First pass: best plausible non-pit/out lap time for the pace gate.
    times = []
    for r in rows:
        if not isinstance(r, Mapping):
            continue
        if _as_int(r.get("is_pit_lap")) or _as_int(r.get("is_out_lap")):
            continue
        t = _as_int(r.get("lap_time_ms"))
        if t > 0:
            times.append(t)
    best = min(times) if times else None

    verdicts = []
    dist: dict = {}
    valid_nums = []
    valid = limited = rejected = 0
    for r in rows:
        v = evaluate_engineering_lap(
            r, purpose=purpose, scope_fingerprint=scope_fingerprint,
            best_lap_ms=best, expected_setup_id=expected_setup_id,
            expected_checkpoint_id=expected_checkpoint_id,
            expected_track=expected_track, **lap_kwargs)
        verdicts.append(v)
        if v.status == LapValidityStatus.VALID:
            valid += 1
            if v.lap_num is not None:
                valid_nums.append(v.lap_num)
        elif v.status == LapValidityStatus.VALID_WITH_LIMITATIONS:
            limited += 1
            if v.lap_num is not None:
                valid_nums.append(v.lap_num)
        elif v.status == LapValidityStatus.INVALID:
            rejected += 1
            for reason in v.rejection_reasons:
                dist[reason] = dist.get(reason, 0) + 1
    summary = LapValiditySummary(
        total_laps=len(rows), valid_laps=valid, limited_laps=limited,
        rejected_laps=rejected, valid_lap_numbers=tuple(sorted(valid_nums)),
        rejection_distribution=dist, purpose=purpose)
    return tuple(verdicts), summary
