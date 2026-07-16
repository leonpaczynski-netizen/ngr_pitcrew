"""Cross-lap issue persistence engine (pure, Qt-free, deterministic).

⚠ EXPERIMENTAL — NOT WIRED INTO THE LIVE PATH (see tests/test_engine_wiring_status.py).
This recurrence engine is consumed only by the dormant ``setup_decision``
arbiter, and its SQLite store (``corner_issue_occurrences`` /
``save_issue_occurrences``, DB v18) is defined but the live recorder does not yet
populate it. Validated by the golden UAT + its own tests; kept as the intended
future evidence layer for setup arbitration. The live setup-advice path uses
``setup_diagnosis`` instead.

Sprint 5 of the determinism rebuild. A telemetry-derived issue (wheelspin,
lockup, bottoming, oversteer, ...) must NOT become setup-authoring evidence
from one lap, one packet cluster, or a raw per-lap average. This module answers
the questions the spec requires: did it recur on multiple REPRESENTATIVE laps,
at the same corner and phase, with compatible inputs and the same axle/direction
— and is it eligible to influence a setup change, or only a controlled test?

Inputs are :class:`IssueOccurrence` records (one per admissible slip/bottoming
episode; build them from ``telemetry.slip_events`` episodes) plus per-lap
metadata used to decide which laps are representative. Excluded laps are never
hidden — they are returned with their exclusion reason.

Authors no setup values, calls no AI, touches no Qt/DB/files. Never raises.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from statistics import median
from typing import Optional, Tuple


class PersistenceClass(str, Enum):
    ISOLATED_ANOMALY = "isolated_anomaly"
    LOW_SAMPLE = "low_sample"
    EMERGING_PATTERN = "emerging_pattern"
    RECURRING_PATTERN = "recurring_pattern"
    PERSISTENT_PATTERN = "persistent_pattern"
    CROSS_SESSION_CONFIRMED = "cross_session_confirmed"
    INCONSISTENT = "inconsistent"


# States eligible to *support* a setup recommendation (still requires engineering
# correlation + arbitration downstream — Sprint 6).
SETUP_ELIGIBLE = frozenset({
    PersistenceClass.PERSISTENT_PATTERN,
    PersistenceClass.CROSS_SESSION_CONFIRMED,
})


@dataclass(frozen=True)
class RecurrenceThresholds:
    """One tested configuration object — not universal motorsport truth, an
    engineering confidence gate. Visible in debug output."""
    min_representative_laps: int = 3       # below this → LOW_SAMPLE
    recurring_pct: float = 0.50            # ≥ this fraction of rep laps → RECURRING
    persistent_pct: float = 0.60           # ≥ this + survives → PERSISTENT
    high_conf_min_laps: int = 5            # persistent needs this many rep laps...
    cross_session_min_sessions: int = 2    # ...or confirmation across this many sessions
    min_confidence: float = 0.40           # per-occurrence admissibility floor
    emerging_min_laps: int = 2             # repeats on ≥ this many rep laps → at least EMERGING


DEFAULT_THRESHOLDS = RecurrenceThresholds()


# Lap classifications that are NOT representative for setup diagnosis. The value
# is the exclusion reason surfaced to the user.
_NON_REPRESENTATIVE = {
    "out": "out lap",
    "in": "in lap",
    "formation": "formation lap",
    "pit_entry": "pit entry",
    "pit_exit": "pit exit",
    "incident": "incident on lap",
    "spin": "spin on lap",
    "off_track": "off-track excursion",
    "yellow": "yellow flag / traffic compromised",
    "cold_tyre": "cold out-lap tyres",
    "wet_mixed": "wet lap in a dry analysis",
    "invalid": "driver marked the run invalid",
    "corrupt": "missing/corrupt telemetry",
}


@dataclass(frozen=True)
class IssueOccurrence:
    """One admissible issue instance (usually one slip/bottoming episode)."""
    session_id: int
    setup_checkpoint_id: str
    lap_number: int
    track: str = ""
    layout_id: str = ""
    segment_id: str = ""
    corner_id: str = ""
    corner_phase: str = ""            # entry | mid | exit | braking | ...
    issue_type: str = ""             # wheelspin | lockup | bottoming | oversteer | ...
    issue_subtype: str = ""
    axle: str = ""                   # front | rear | all
    duration_s: float = 0.0
    severity: float = 0.0            # normalised 0..1 (e.g. max_slip margin)
    confidence: float = 0.0
    throttle: float = 0.0
    brake: float = 0.0
    speed_kmh: float = 0.0
    gear: int = 0
    compound: str = ""
    tyre_age: int = 0
    exclusion_reason: str = ""       # non-empty if this occurrence itself is suppressed
    provenance: str = ""

    @property
    def is_admissible(self) -> bool:
        return not self.exclusion_reason and self.confidence > 0.0


@dataclass(frozen=True)
class LapMeta:
    """Per-lap metadata used to decide representativeness."""
    session_id: int
    lap_number: int
    classification: str = "flying"   # flying | out | in | formation | incident | spin | ...
    valid: bool = True
    setup_checkpoint_id: str = ""
    compound: str = ""

    def representative(self) -> Tuple[bool, str]:
        if not self.valid:
            return False, _NON_REPRESENTATIVE.get("invalid", "invalid lap")
        reason = _NON_REPRESENTATIVE.get((self.classification or "").lower())
        if reason:
            return False, reason
        return True, ""


@dataclass(frozen=True)
class LapIssueSummary:
    session_id: int
    lap_number: int
    representative: bool
    exclusion_reason: str
    occurrence_count: int


@dataclass(frozen=True)
class CornerIssueSignature:
    track: str
    layout_id: str
    setup_checkpoint_id: str
    segment_id: str
    corner_phase: str
    issue_type: str
    axle: str
    subtype_family: str

    def key(self) -> tuple:
        return (self.track, self.layout_id, self.setup_checkpoint_id,
                self.segment_id, self.corner_phase, self.issue_type,
                self.axle, self.subtype_family)


@dataclass(frozen=True)
class IssuePersistenceResult:
    classification: PersistenceClass
    signature: CornerIssueSignature
    affected_representative_laps: int
    total_representative_laps: int
    recurrence_pct: float
    sessions: int
    median_severity: float
    median_duration_s: float
    confidence: float
    eligible_for_setup: bool
    excluded_laps: Tuple[LapIssueSummary, ...]
    reason: str
    next_action: str
    thresholds: RecurrenceThresholds = DEFAULT_THRESHOLDS


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _subtype_family(subtype: str) -> str:
    """Collapse compatible subtypes so like groups with like."""
    s = (subtype or "").lower()
    if "wheelspin" in s or "spin" in s or "oversteer" in s:
        return "power_traction"
    if "lockup" in s or "lock" in s:
        return "brake_lock"
    if "floor" in s or "bottom" in s or "compression" in s:
        return "floor_contact"
    return s or "generic"


def signature_of(occ: IssueOccurrence) -> CornerIssueSignature:
    return CornerIssueSignature(
        track=occ.track, layout_id=occ.layout_id,
        setup_checkpoint_id=occ.setup_checkpoint_id,
        segment_id=occ.segment_id or occ.corner_id,
        corner_phase=occ.corner_phase, issue_type=occ.issue_type,
        axle=occ.axle, subtype_family=_subtype_family(occ.issue_subtype),
    )


def classify_laps(laps) -> dict:
    """Return {(session_id, lap_number): (representative: bool, reason: str)}."""
    out = {}
    for lm in laps:
        rep, reason = lm.representative()
        out[(lm.session_id, lm.lap_number)] = (rep, reason)
    return out


def _classify(pattern_laps: set, total_rep: int, sessions: int,
              rep_conf: list, thresholds: RecurrenceThresholds) -> PersistenceClass:
    affected = len(pattern_laps)
    pct = (affected / total_rep) if total_rep else 0.0

    # Cross-session confirmation is the strongest signal.
    if sessions >= thresholds.cross_session_min_sessions and affected >= thresholds.emerging_min_laps:
        return PersistenceClass.CROSS_SESSION_CONFIRMED

    if total_rep < thresholds.min_representative_laps:
        # Not enough representative laps to judge recurrence at all.
        return PersistenceClass.LOW_SAMPLE if affected >= 1 else PersistenceClass.ISOLATED_ANOMALY

    if affected <= 1:
        return PersistenceClass.ISOLATED_ANOMALY

    if pct >= thresholds.persistent_pct and (
            affected >= thresholds.high_conf_min_laps or total_rep >= thresholds.high_conf_min_laps):
        return PersistenceClass.PERSISTENT_PATTERN

    if pct >= thresholds.recurring_pct:
        return PersistenceClass.RECURRING_PATTERN

    if affected >= thresholds.emerging_min_laps:
        return PersistenceClass.EMERGING_PATTERN

    return PersistenceClass.ISOLATED_ANOMALY


def _next_action(cls: PersistenceClass) -> str:
    return {
        PersistenceClass.ISOLATED_ANOMALY:
            "No setup change. Record the observation; review technique on the affected lap.",
        PersistenceClass.LOW_SAMPLE:
            "No setup change. Run more representative laps to judge recurrence.",
        PersistenceClass.EMERGING_PATTERN:
            "Preserve setup. Run a controlled test to confirm the pattern before authoring.",
        PersistenceClass.RECURRING_PATTERN:
            "May contribute to diagnosis, but requires engineering correlation before a change.",
        PersistenceClass.PERSISTENT_PATTERN:
            "Eligible to support a setup recommendation (still gated by arbitration).",
        PersistenceClass.CROSS_SESSION_CONFIRMED:
            "Strong evidence — eligible for a higher-confidence setup recommendation.",
        PersistenceClass.INCONSISTENT:
            "Signal is inconsistent across laps — no setup change; run a controlled test.",
    }.get(cls, "No setup change.")


def analyse_cross_lap(
    occurrences,
    laps,
    thresholds: RecurrenceThresholds = DEFAULT_THRESHOLDS,
) -> list[IssuePersistenceResult]:
    """Group admissible occurrences by corner-issue signature and classify each
    pattern's persistence. Returns one result per signature, most-persistent first.
    """
    th = thresholds or DEFAULT_THRESHOLDS
    lap_class = classify_laps(laps)

    # Representative-lap denominator (all representative laps in the sample).
    rep_lap_keys = {k for k, (rep, _r) in lap_class.items() if rep}
    total_rep = len(rep_lap_keys)

    # Visible exclusions.
    excluded = tuple(
        LapIssueSummary(session_id=sid, lap_number=ln, representative=False,
                        exclusion_reason=reason, occurrence_count=0)
        for (sid, ln), (rep, reason) in sorted(lap_class.items())
        if not rep
    )

    # Group admissible occurrences by signature.
    groups: dict[tuple, list] = {}
    for occ in occurrences:
        if not occ.is_admissible or occ.confidence < th.min_confidence:
            continue
        # Only occurrences on representative laps contribute to recurrence.
        if (occ.session_id, occ.lap_number) not in rep_lap_keys:
            continue
        sig = signature_of(occ)
        groups.setdefault(sig.key(), []).append((sig, occ))

    results: list[IssuePersistenceResult] = []
    for _key, items in groups.items():
        sig = items[0][0]
        occs = [o for _s, o in items]
        pattern_laps = {(o.session_id, o.lap_number) for o in occs}
        sessions = len({o.session_id for o in occs})
        rep_conf = [o.confidence for o in occs]

        cls = _classify(pattern_laps, total_rep, sessions, rep_conf, th)

        sev = [o.severity for o in occs] or [0.0]
        dur = [o.duration_s for o in occs] or [0.0]
        pct = (len(pattern_laps) / total_rep) if total_rep else 0.0
        confidence = round(min(1.0, (sum(rep_conf) / len(rep_conf)) if rep_conf else 0.0), 2)

        results.append(IssuePersistenceResult(
            classification=cls, signature=sig,
            affected_representative_laps=len(pattern_laps),
            total_representative_laps=total_rep,
            recurrence_pct=round(pct, 3), sessions=sessions,
            median_severity=round(median(sev), 3),
            median_duration_s=round(median(dur), 3),
            confidence=confidence,
            eligible_for_setup=cls in SETUP_ELIGIBLE,
            excluded_laps=excluded,
            reason=(f"{len(pattern_laps)} of {total_rep} representative laps affected "
                    f"at {sig.segment_id or 'unknown'}/{sig.corner_phase or 'unknown'} "
                    f"({sig.issue_type}, {sig.axle} axle); {sessions} session(s)."),
            next_action=_next_action(cls),
            thresholds=th,
        ))

    # Most persistent / most-affected first.
    order = {c: i for i, c in enumerate([
        PersistenceClass.CROSS_SESSION_CONFIRMED, PersistenceClass.PERSISTENT_PATTERN,
        PersistenceClass.RECURRING_PATTERN, PersistenceClass.EMERGING_PATTERN,
        PersistenceClass.LOW_SAMPLE, PersistenceClass.INCONSISTENT,
        PersistenceClass.ISOLATED_ANOMALY])}
    results.sort(key=lambda r: (order.get(r.classification, 99),
                                -r.affected_representative_laps))
    return results


def render_persistence_debug(results) -> str:
    """Deterministic plain-text debug/summary of persistence results.

    Makes recurrence, thresholds, and EXCLUDED laps visible (never hidden) —
    the spec requires excluded laps be shown with their reason.
    """
    if not results:
        return "No cross-lap issue patterns found."
    lines: list[str] = []
    excluded = results[0].excluded_laps if results else ()
    for r in results:
        s = r.signature
        lines.append(
            f"[{r.classification.value.upper()}] {s.issue_type} @ "
            f"{s.segment_id or '?'}/{s.corner_phase or '?'} ({s.axle} axle): "
            f"{r.affected_representative_laps}/{r.total_representative_laps} rep laps "
            f"({r.recurrence_pct:.0%}), {r.sessions} session(s), "
            f"median sev {r.median_severity:.2f}, median dur {r.median_duration_s:.2f}s, "
            f"conf {r.confidence:.2f} → "
            f"{'SETUP-ELIGIBLE' if r.eligible_for_setup else 'not eligible'}. "
            f"{r.next_action}"
        )
    if excluded:
        lines.append("Excluded laps (not counted): " + ", ".join(
            f"S{e.session_id}L{e.lap_number} [{e.exclusion_reason}]" for e in excluded))
    return "\n".join(lines)


def occurrence_from_episode(
    episode, *, session_id: int, setup_checkpoint_id: str, lap_number: int,
    track: str = "", layout_id: str = "", compound: str = "", tyre_age: int = 0,
) -> IssueOccurrence:
    """Bridge a ``telemetry.slip_events.SlipEpisode`` to an IssueOccurrence.

    Suppressed episodes carry their exclusion reason through (so they remain
    visible but inadmissible). Severity is the peak slip margin past threshold.
    """
    kind = getattr(episode, "kind", "")
    max_slip = float(getattr(episode, "max_slip", 0.0) or 0.0)
    thresh = 1.3 if kind == "wheelspin" else 1.0
    severity = max(0.0, min(1.0, abs(max_slip - thresh)))
    return IssueOccurrence(
        session_id=session_id, setup_checkpoint_id=setup_checkpoint_id,
        lap_number=lap_number, track=track, layout_id=layout_id,
        segment_id=getattr(episode, "segment_id", "") or "",
        corner_phase=getattr(episode, "corner_phase", "") or "",
        issue_type=kind, issue_subtype=getattr(episode, "subtype", "") or "",
        axle=getattr(episode, "axle", "") or "",
        duration_s=float(getattr(episode, "duration_s", 0.0) or 0.0),
        severity=round(severity, 3),
        confidence=float(getattr(episode, "confidence", 0.0) or 0.0),
        throttle=float(getattr(episode, "throttle", 0.0) or 0.0),
        brake=float(getattr(episode, "brake", 0.0) or 0.0),
        speed_kmh=float(getattr(episode, "speed_kmh", 0.0) or 0.0),
        gear=int(getattr(episode, "gear", 0) or 0),
        compound=compound, tyre_age=tyre_age,
        exclusion_reason=getattr(episode, "exclusion_reason", "") or "",
        provenance=getattr(episode, "provenance", "") or "",
    )
