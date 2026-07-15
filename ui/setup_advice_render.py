"""Structured setup-advice rendering (pure, Qt-free).

Sprint 10 of the determinism rebuild. Advice was assembled into one monolithic
HTML blob dumped in a read-only text box. This module turns the deterministic
``SetupDecision`` (Sprint 6), cross-lap persistence patterns (Sprint 5), and
tyre crossovers (Sprint 7) into an ordered list of typed display cards the Qt
layer renders as discrete components (a decision banner, an approved-changes
table, a preserved-fields list, an evidence-conflict card, a controlled-test
card, a recurring-pattern table, ...). No free-form generated prose.

Pure: no Qt, no I/O. Returns plain structured data.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Tuple

from strategy.setup_decision import DecisionStatus


# Tone drives colour in the Qt layer without hard-coding styles here.
TONE_OK = "ok"
TONE_WARN = "warn"
TONE_DANGER = "danger"
TONE_INFO = "info"

_STATUS_TONE = {
    DecisionStatus.APPROVED_WITH_CHANGES: TONE_OK,
    DecisionStatus.APPROVED_NO_CHANGE: TONE_OK,
    DecisionStatus.CONTROLLED_TEST_REQUIRED: TONE_WARN,
    DecisionStatus.EVIDENCE_CONFLICT: TONE_WARN,
    DecisionStatus.INSUFFICIENT_EVIDENCE: TONE_INFO,
    DecisionStatus.REJECTED_UNSAFE: TONE_DANGER,
    DecisionStatus.ENGINEERING_FAILURE: TONE_DANGER,
}


@dataclass(frozen=True)
class AdviceCard:
    kind: str                 # banner | approved | preserved | rejected | conflict | test | recurring | crossover
    title: str
    tone: str
    lines: Tuple[str, ...] = ()
    rows: Tuple[tuple, ...] = ()   # tabular rows (header-less; the widget supplies headers)


def _fields(decision, outcome):
    return decision.fields_by_outcome(outcome)


def render_setup_decision(decision, persistence_results=(), crossovers=()) -> list:
    """Return an ordered list of typed :class:`AdviceCard` for one decision."""
    cards: list[AdviceCard] = []
    tone = _STATUS_TONE.get(decision.status, TONE_INFO)

    # 1) Decision banner — status is unambiguous; never "approved" + "failed".
    banner_lines = [decision.rationale] if decision.rationale else []
    if decision.validation_failed:
        banner_lines.append("Engineering validation failed — the recommendation is not approved.")
    cards.append(AdviceCard(
        kind="banner", title=decision.headline or decision.status.value,
        tone=tone, lines=tuple(banner_lines)))

    # 2) Approved changes table.
    approved = [fd for fd in decision.field_decisions if fd.outcome == "approved"]
    if approved:
        cards.append(AdviceCard(
            kind="approved", title="Approved changes", tone=TONE_OK,
            rows=tuple((fd.field, fd.reason) for fd in approved)))

    # 3) Preserved fields.
    preserved = [fd for fd in decision.field_decisions if fd.outcome == "preserved"]
    if preserved:
        cards.append(AdviceCard(
            kind="preserved", title="Preserved (no change)", tone=TONE_OK,
            rows=tuple((fd.field, fd.reason) for fd in preserved)))

    # 4) Evidence conflict card.
    if decision.status is DecisionStatus.EVIDENCE_CONFLICT:
        cards.append(AdviceCard(
            kind="conflict", title="Evidence conflict — setup preserved", tone=TONE_WARN,
            lines=("Telemetry suggests a possible issue, but it is not repeatable or "
                   "confident enough to override the driver's positive feedback.",)))

    # 5) Controlled test card.
    deferred = [fd for fd in decision.field_decisions if fd.outcome == "deferred_test"]
    if decision.controlled_test or deferred:
        lines = [decision.controlled_test] if decision.controlled_test else []
        cards.append(AdviceCard(
            kind="test", title="Controlled test", tone=TONE_WARN,
            lines=tuple(l for l in lines if l),
            rows=tuple((fd.field, fd.reason) for fd in deferred)))

    # 6) Rejected changes.
    rejected = [fd for fd in decision.field_decisions if fd.outcome == "rejected"]
    if rejected:
        cards.append(AdviceCard(
            kind="rejected", title="Rejected", tone=TONE_DANGER,
            rows=tuple((fd.field, fd.reason) for fd in rejected)))

    # 7) Cross-lap recurrence evidence table.
    recur_rows = []
    for r in (persistence_results or []):
        sig = getattr(r, "signature", None)
        recur_rows.append((
            getattr(r, "classification").value if getattr(r, "classification", None) else "",
            f"{getattr(sig, 'issue_type', '?')} @ {getattr(sig, 'segment_id', '?')}/"
            f"{getattr(sig, 'corner_phase', '?')} ({getattr(sig, 'axle', '?')})",
            f"{getattr(r, 'affected_representative_laps', 0)}/"
            f"{getattr(r, 'total_representative_laps', 0)} laps "
            f"({getattr(r, 'recurrence_pct', 0):.0%})",
            "eligible" if getattr(r, "eligible_for_setup", False) else "not eligible",
        ))
    if recur_rows:
        cards.append(AdviceCard(
            kind="recurring", title="Cross-lap evidence", tone=TONE_INFO,
            rows=tuple(recur_rows)))

    # 8) Tyre crossovers (when provided, e.g. on the strategy surface).
    cross_rows = []
    for c in (crossovers or []):
        cross_rows.append((
            f"{getattr(c, 'softer', '?')} → {getattr(c, 'harder', '?')}",
            f"after lap {getattr(c, 'crossover_after_lap', 0)}",
            getattr(c, "confidence", ""),
        ))
    if cross_rows:
        cards.append(AdviceCard(
            kind="crossover", title="Tyre crossovers", tone=TONE_INFO,
            rows=tuple(cross_rows)))

    return cards
