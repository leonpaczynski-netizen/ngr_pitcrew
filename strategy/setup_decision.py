"""Setup decision arbitration — one accountable engineering verdict (pure).

Sprint 6 of the determinism rebuild. Setup Builder must behave as one race
engineer: it weighs telemetry against driver feedback using a fixed evidence
precedence and returns EXACTLY ONE decision status. A single noisy lap must not
outrank repeated driver feedback or proven history; low-confidence telemetry
must not silently override explicit positive driver feedback. Every proposed
change ends in exactly one state: approved, preserved, rejected, deferred for a
controlled test, or insufficient evidence. The app must NEVER show "approved"
and "engineering validation failed" together.

Consumes the Sprint 5 cross-lap persistence verdicts (only PERSISTENT /
CROSS_SESSION are eligible to author a change) and structured driver feedback.
Authors no setup values itself, calls no AI, touches no Qt/DB/files.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, IntEnum
from typing import Optional, Tuple

from strategy.cross_lap_persistence import PersistenceClass, SETUP_ELIGIBLE


class DecisionStatus(str, Enum):
    APPROVED_WITH_CHANGES = "APPROVED_WITH_CHANGES"
    APPROVED_NO_CHANGE = "APPROVED_NO_CHANGE"
    CONTROLLED_TEST_REQUIRED = "CONTROLLED_TEST_REQUIRED"
    EVIDENCE_CONFLICT = "EVIDENCE_CONFLICT"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    REJECTED_UNSAFE = "REJECTED_UNSAFE"
    ENGINEERING_FAILURE = "ENGINEERING_FAILURE"


class EvidenceTier(IntEnum):
    """Evidence precedence — lower value = higher precedence (Requirement 2)."""
    VALIDATED_RECURRING_TELEMETRY = 1
    LATEST_DRIVER_FEEDBACK = 2
    CROSS_SESSION_EVIDENCE = 3
    PROVEN_HISTORY = 4
    TRACK_VEHICLE_MODEL = 5
    GENERIC_RULE = 6


# Which setup field maps to which feedback area + issue type, so telemetry and
# driver feedback are arbitrated on the SAME axis. Extend as needed.
_FIELD_AREA = {
    "lsd_accel": ("traction", "wheelspin"),
    "lsd_initial": ("traction", "wheelspin"),
    "lsd_decel": ("braking", "lockup"),
    "aero_rear": ("traction", "wheelspin"),
    "aero_front": ("rotation", "understeer"),
    "arb_rear": ("rotation", "oversteer"),
    "arb_front": ("rotation", "understeer"),
    "ride_height_front": ("stability", "bottoming"),
    "ride_height_rear": ("stability", "bottoming"),
    "brake_bias": ("braking", "lockup"),
    "camber_rear": ("traction", "wheelspin"),
    "toe_rear": ("traction", "wheelspin"),
}


@dataclass(frozen=True)
class DriverFeedback:
    """Structured per-area driver sentiment: 'good' | 'bad' | 'neutral'."""
    entry: str = "neutral"
    rotation: str = "neutral"
    traction: str = "neutral"
    braking: str = "neutral"
    stability: str = "neutral"
    fuel: str = "neutral"
    better_than_previous: Optional[bool] = None
    notes: str = ""

    def area(self, area: str) -> str:
        return getattr(self, area, "neutral") or "neutral"

    @property
    def any_positive(self) -> bool:
        vals = (self.entry, self.rotation, self.traction, self.braking, self.stability)
        return any(v == "good" for v in vals) or self.better_than_previous is True

    @property
    def any_complaint(self) -> bool:
        vals = (self.entry, self.rotation, self.traction, self.braking, self.stability)
        return any(v == "bad" for v in vals)


@dataclass(frozen=True)
class FieldDecision:
    field: str
    outcome: str           # approved | preserved | rejected | deferred_test | insufficient
    reason: str
    evidence_tier: Optional[EvidenceTier] = None


@dataclass(frozen=True)
class SetupDecision:
    status: DecisionStatus
    field_decisions: Tuple[FieldDecision, ...]
    validation_failed: bool
    headline: str
    rationale: str
    controlled_test: str = ""
    evidence_summary: str = ""

    @property
    def is_approved(self) -> bool:
        return self.status in (DecisionStatus.APPROVED_WITH_CHANGES,
                               DecisionStatus.APPROVED_NO_CHANGE)

    def fields_by_outcome(self, outcome: str) -> Tuple[str, ...]:
        return tuple(fd.field for fd in self.field_decisions if fd.outcome == outcome)


def _eligible_persistence_for_area(persistence_results, issue_type: str):
    """Return the strongest setup-eligible persistence result matching an issue
    type, and the strongest non-eligible one (for conflict detection)."""
    eligible = None
    non_eligible = None
    for r in (persistence_results or []):
        it = getattr(getattr(r, "signature", None), "issue_type", "") or ""
        if issue_type and it != issue_type:
            continue
        if getattr(r, "eligible_for_setup", False) and r.classification in SETUP_ELIGIBLE:
            if eligible is None or r.recurrence_pct > eligible.recurrence_pct:
                eligible = r
        else:
            if non_eligible is None or r.recurrence_pct > non_eligible.recurrence_pct:
                non_eligible = r
    return eligible, non_eligible


def _controlled_test_text(issue_type: str, area: str) -> str:
    return (
        "Run five representative laps on the current setup, focusing on the "
        f"corners where {issue_type or 'the issue'} appears. Keep tyre compound, "
        "fuel load, and driver-aids constant; make no setup changes. Setup review "
        "only if the same signature recurs on at least three of five laps."
    )


def arbitrate_setup_decision(
    proposed_changes,
    persistence_results,
    driver_feedback: DriverFeedback,
    *,
    validation_failed: bool = False,
    validation_errors: Optional[list] = None,
    unsafe_fields: Optional[set] = None,
    has_any_evidence: bool = True,
) -> SetupDecision:
    """Arbitrate proposed setup changes into ONE decision.

    ⚠ EXPERIMENTAL / DEPRECATED — NOT WIRED INTO THE LIVE PATH
    (see tests/test_engine_wiring_status.py). The live Setup "Analyse" flow uses
    ``setup_diagnosis`` + ``setup_rule_engine``; the UI imports only this module's
    render dataclasses (``DecisionStatus``/``FieldDecision``, via
    ``render_setup_decision``), NOT this arbiter. Validated by its own tests + the
    golden UAT; kept as the intended future evidence-precedence layer.

    Engineering-Brain Phase 4 formally deprecated this per-field arbiter as the
    driver-facing decision authority. The canonical authorities are now:
      * the Phase-2 experiment lifecycle (transitions) — data/session_db.py;
      * the Phase-3 outcome status (evidence judgement) — strategy/setup_experiment_outcome.py;
      * the Phase-4 driver-facing decision state — strategy/setup_decision_status.resolve_setup_decision.
    This arbiter is not promoted; its evidence-precedence field logic is superseded
    by the Phase 1–4 spine and remains dormant (no live caller — enforced by
    tests/test_engine_wiring_status.py and tests/test_phase4_setup_decision.py).

    ``proposed_changes`` — iterable of dicts/objects with a ``field`` (and
    optional ``delta``). ``persistence_results`` — Sprint 5 IssuePersistenceResult
    list. ``driver_feedback`` — structured sentiment.
    """
    fb = driver_feedback or DriverFeedback()
    unsafe = set(unsafe_fields or ())

    # 1) Engineering failure dominates — a failed recommendation is NOT approved,
    #    and must never be shown alongside "approved".
    if validation_failed:
        return SetupDecision(
            status=DecisionStatus.ENGINEERING_FAILURE,
            field_decisions=tuple(
                FieldDecision(_field_name(c), "rejected",
                              "engineering validation failed — recommendation not applied")
                for c in (proposed_changes or [])),
            validation_failed=True,
            headline="Engineering validation failed — no changes applied",
            rationale="The recommendation did not pass engineering validation, so it "
                      "is not approved. The current setup is preserved.",
            evidence_summary="; ".join(str(e) for e in (validation_errors or [])) or
                             "validation failed",
        )

    field_decisions: list[FieldDecision] = []
    conflict = False
    approved_any = False
    deferred_any = False

    for change in (proposed_changes or []):
        fname = _field_name(change)
        area, issue_type = _FIELD_AREA.get(fname, ("", ""))

        # Unsafe proposal — reject outright.
        if fname in unsafe:
            field_decisions.append(FieldDecision(
                fname, "rejected", "change is unsafe / outside working window"))
            continue

        eligible, non_eligible = _eligible_persistence_for_area(persistence_results, issue_type)
        driver_area = fb.area(area) if area else "neutral"

        # Driver reports the area is GOOD.
        if driver_area == "good":
            if eligible is not None:
                # Strong recurring telemetry vs a positive report — telemetry wins
                # per precedence, but flag the tension for the engineer.
                field_decisions.append(FieldDecision(
                    fname, "approved",
                    f"persistent {issue_type} recurrence outweighs the positive report",
                    EvidenceTier.VALIDATED_RECURRING_TELEMETRY))
                approved_any = True
            elif non_eligible is not None:
                # Low-confidence / non-recurring telemetry vs explicit positive
                # feedback → conflict; preserve. (Fixture E.)
                conflict = True
                field_decisions.append(FieldDecision(
                    fname, "preserved",
                    f"driver reports good {area}; telemetry {issue_type} is not "
                    f"recurring/confident enough to override it",
                    EvidenceTier.LATEST_DRIVER_FEEDBACK))
            else:
                field_decisions.append(FieldDecision(
                    fname, "preserved",
                    f"driver reports good {area} and there is no eligible telemetry evidence",
                    EvidenceTier.LATEST_DRIVER_FEEDBACK))
            continue

        # Driver neutral / complains.
        if eligible is not None:
            field_decisions.append(FieldDecision(
                fname, "approved",
                f"{eligible.classification.value} {issue_type} evidence supports the change",
                EvidenceTier.VALIDATED_RECURRING_TELEMETRY))
            approved_any = True
        elif non_eligible is not None and non_eligible.classification in (
                PersistenceClass.EMERGING_PATTERN, PersistenceClass.RECURRING_PATTERN):
            field_decisions.append(FieldDecision(
                fname, "deferred_test",
                f"{non_eligible.classification.value} {issue_type} — run a controlled "
                f"test before authoring", EvidenceTier.GENERIC_RULE))
            deferred_any = True
        elif driver_area == "bad":
            # Complaint but no telemetry pattern → controlled test, preserve.
            field_decisions.append(FieldDecision(
                fname, "deferred_test",
                f"driver reports poor {area} but no recurring telemetry pattern yet",
                EvidenceTier.LATEST_DRIVER_FEEDBACK))
            deferred_any = True
        else:
            field_decisions.append(FieldDecision(
                fname, "insufficient",
                f"no eligible evidence for {fname}"))

    # 2) Aggregate to one status.
    status = _aggregate_status(
        field_decisions, conflict, approved_any, deferred_any, fb, has_any_evidence)

    headline, rationale, test = _summarise(status, field_decisions, fb)
    return SetupDecision(
        status=status, field_decisions=tuple(field_decisions),
        validation_failed=False, headline=headline, rationale=rationale,
        controlled_test=test,
        evidence_summary=_evidence_summary(persistence_results),
    )


def _aggregate_status(field_decisions, conflict, approved_any, deferred_any,
                      fb, has_any_evidence) -> DecisionStatus:
    if any(fd.outcome == "rejected" for fd in field_decisions) and not approved_any \
            and not deferred_any and not conflict:
        # All proposals rejected as unsafe.
        return DecisionStatus.REJECTED_UNSAFE
    if approved_any:
        return DecisionStatus.APPROVED_WITH_CHANGES
    if conflict:
        return DecisionStatus.EVIDENCE_CONFLICT
    if deferred_any:
        return DecisionStatus.CONTROLLED_TEST_REQUIRED
    if not has_any_evidence:
        return DecisionStatus.INSUFFICIENT_EVIDENCE
    # Nothing to change and no conflict — the setup is preserved as good.
    if fb.any_positive or not field_decisions:
        return DecisionStatus.APPROVED_NO_CHANGE
    return DecisionStatus.CONTROLLED_TEST_REQUIRED


def _summarise(status, field_decisions, fb) -> tuple:
    test = ""
    if status == DecisionStatus.APPROVED_WITH_CHANGES:
        n = sum(1 for fd in field_decisions if fd.outcome == "approved")
        return (f"Approved — {n} change(s)",
                "Recurring, engineering-validated evidence supports the change(s).", "")
    if status == DecisionStatus.APPROVED_NO_CHANGE:
        return ("Approved — no change",
                "The current setup is preserved; no eligible evidence justifies a change.", "")
    if status == DecisionStatus.EVIDENCE_CONFLICT:
        test = _controlled_test_text("the reported issue", "")
        return ("Evidence conflict — setup preserved",
                "Telemetry suggests a possible issue, but it is not repeatable or "
                "confident enough to override the driver's positive feedback. The "
                "current setup is preserved.", test)
    if status == DecisionStatus.CONTROLLED_TEST_REQUIRED:
        test = _controlled_test_text("the reported issue", "")
        return ("Controlled test required — setup preserved",
                "Evidence is emerging but not yet sufficient to author a change.", test)
    if status == DecisionStatus.REJECTED_UNSAFE:
        return ("Rejected — unsafe", "The proposed change(s) are unsafe and were not applied.", "")
    if status == DecisionStatus.INSUFFICIENT_EVIDENCE:
        return ("Insufficient evidence",
                "Not enough representative data to make a setup decision.", "")
    return ("Engineering failure", "The recommendation is not approved.", "")


def _evidence_summary(persistence_results) -> str:
    parts = []
    for r in (persistence_results or []):
        sig = getattr(r, "signature", None)
        parts.append(f"{getattr(sig, 'issue_type', '?')}@"
                     f"{getattr(sig, 'segment_id', '?')}:{r.classification.value}"
                     f"({r.affected_representative_laps}/{r.total_representative_laps})")
    return "; ".join(parts)


def _field_name(change) -> str:
    if isinstance(change, dict):
        return str(change.get("field", "") or "")
    return str(getattr(change, "field", "") or "")
