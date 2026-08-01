"""End-of-event debrief aggregation (Program 3 Phase H / §20).

The debrief is the controlled bridge between what happened, what the app measured,
and what may be learned. Today it exists only as a launch/binding gate plus a
presentation screen; the aggregation is scattered in caller code. This is the single
PURE aggregating service: it reads the event's spine (session runs, strategy
revisions, PTT interactions, quarantined records, setups) and produces a structured
``EventDebrief``.

Its defining rule (gate #18): every finding is tagged with its PROVENANCE — a measured
fact, a deterministic inference, a driver report, or an unresolved question — so the
debrief never blurs what the app measured with what it inferred or what the driver
said. Pure, deterministic, offline, never raises. It states; it decides nothing and
promotes no learning (that is Phase I, driver-gated).
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Mapping, Sequence, Tuple


class DebriefProvenance(str, enum.Enum):
    MEASURED_FACT = "measured_fact"
    DETERMINISTIC_INFERENCE = "deterministic_inference"
    DRIVER_REPORT = "driver_report"
    UNRESOLVED = "unresolved"


# The canonical §20 sections.
SECTIONS: Tuple[str, ...] = (
    "event_overview", "driver_performance", "setup_review", "strategy_review",
    "engineer_review", "data_quality", "driver_reflection",
)


@dataclass(frozen=True)
class DebriefFinding:
    text: str
    provenance: DebriefProvenance
    section: str = ""


@dataclass(frozen=True)
class EventDebrief:
    event_id: int = 0
    car: str = ""
    track: str = ""
    findings: Tuple[DebriefFinding, ...] = field(default_factory=tuple)

    def by_section(self, section: str) -> Tuple[DebriefFinding, ...]:
        return tuple(f for f in self.findings if f.section == section)

    def by_provenance(self, provenance: DebriefProvenance) -> Tuple[DebriefFinding, ...]:
        return tuple(f for f in self.findings if f.provenance == provenance)

    @property
    def facts(self) -> Tuple[DebriefFinding, ...]:
        return self.by_provenance(DebriefProvenance.MEASURED_FACT)

    @property
    def inferences(self) -> Tuple[DebriefFinding, ...]:
        return self.by_provenance(DebriefProvenance.DETERMINISTIC_INFERENCE)

    @property
    def driver_reports(self) -> Tuple[DebriefFinding, ...]:
        return self.by_provenance(DebriefProvenance.DRIVER_REPORT)

    @property
    def unresolved(self) -> Tuple[DebriefFinding, ...]:
        return self.by_provenance(DebriefProvenance.UNRESOLVED)


def _s(v) -> str:
    return "" if v is None else str(v)


def build_event_debrief(
    *,
    event_id: int = 0,
    car: str = "",
    track: str = "",
    session_runs: Sequence[Mapping] = (),
    strategy_revisions: Sequence[Mapping] = (),
    ptt_interactions: Sequence[Mapping] = (),
    quarantined: Sequence[Mapping] = (),
    setups_used: Sequence[str] = (),
    unresolved_questions: Sequence[str] = (),
) -> EventDebrief:
    """Aggregate the event's spine into a provenance-typed debrief. Never raises."""
    out: list = []
    add = lambda text, prov, section: out.append(DebriefFinding(text, prov, section))
    F = DebriefProvenance.MEASURED_FACT
    I = DebriefProvenance.DETERMINISTIC_INFERENCE
    DR = DebriefProvenance.DRIVER_REPORT
    U = DebriefProvenance.UNRESOLVED
    try:
        runs = [dict(r) for r in (session_runs or [])]
        revs = [dict(r) for r in (strategy_revisions or [])]
        ptts = [dict(p) for p in (ptt_interactions or [])]
        quar = list(quarantined or [])

        # --- Event overview (measured facts) ---
        completed = [r for r in runs if _s(r.get("status")) == "complete"]
        abandoned = [r for r in runs if _s(r.get("status")) in ("abandoned", "failed")]
        add(f"{len(runs)} session run(s): {len(completed)} completed, {len(abandoned)} abandoned/failed.",
            F, "event_overview")
        if setups_used:
            add(f"Setups used: {', '.join(_s(s) for s in setups_used if _s(s))}.", F, "event_overview")

        # --- Strategy review ---
        if revs:
            triggers = sorted({_s(r.get("trigger")) for r in revs if _s(r.get("trigger"))})
            add(f"{len(revs)} strategy revision(s); trigger(s): {', '.join(triggers) or '—'}.",
                F, "strategy_review")
            active = [r for r in revs if r.get("is_active")]
            if active:
                add(f"Final active plan is revision {active[-1].get('revision_index', '?')} "
                    f"({_s(active[-1].get('trigger')) or 'pre-race'}).", F, "strategy_review")
        else:
            add("No strategy revisions recorded — the pre-race plan ran unchanged, or none was captured.",
                I, "strategy_review")

        # --- Engineer / PTT review ---
        add(f"{len(ptts)} PTT interaction(s) recorded.", F, "engineer_review")
        ambiguous = [p for p in ptts if p.get("ambiguous")]
        if ambiguous:
            add(f"{len(ambiguous)} PTT interaction(s) were ambiguous — possible speech-recognition "
                "or phrasing issues worth reviewing.", I, "engineer_review")

        # --- Driver reflection (driver-reported, never conflated with measurement) ---
        for p in ptts:
            if _s(p.get("command_class")) == "report" and _s(p.get("recognised_action")):
                lap = p.get("lap_number") or 0
                where = f" (lap {lap})" if lap else ""
                add(f"Driver reported: {_s(p.get('recognised_action'))}{where}.", DR, "driver_reflection")

        # --- Data-quality review ---
        if quar:
            add(f"{len(quar)} record(s) quarantined (ambiguous/orphaned) — excluded from learning.",
                F, "data_quality")
        no_lap_runs = [r for r in runs if r.get("session_id") in (0, None, "")]
        if no_lap_runs:
            add(f"{len(no_lap_runs)} run(s) have no bound recorded session — data may be incomplete.",
                I, "data_quality")

        # --- Unresolved questions (carried, never guessed into a conclusion) ---
        for q in (unresolved_questions or []):
            if _s(q):
                add(_s(q), U, "setup_review")

        return EventDebrief(event_id=int(event_id or 0), car=_s(car), track=_s(track),
                            findings=tuple(out))
    except Exception:
        return EventDebrief(event_id=int(event_id or 0), car=_s(car), track=_s(track),
                            findings=tuple(out))
