"""Programme map — where the driver is in the WHOLE event programme (UAT-6).

Round 6: "I feel like we are going in circles now and the process is somewhat flawed."
The engineer nominates one weakest domain at a time and, after each recorded run,
nominates the next — which is correct — but nothing on screen ever showed how many runs
a domain NEEDS or how many remain, so every screen looked identical after every run and
it read as a loop.

This turns the readiness the Command Centre already produces into a MAP: each evidence
domain, how many qualifying runs it has, how many it needs, the kind of run that fills
it, ordered as a programme, plus an overall completion figure and the next few runs
planned ahead. It reads the numbers the domain layer already computed; it decides
nothing and adds no new authority.

Pure — no Qt, no DB, no I/O, never raises. The confidence ladder it mirrors lives in
``strategy.preparation_evidence._confidence_from``: 3 exact samples reach "adequate",
4 reach "strong"; a capped (partial/unknown) domain can never pass "developing".
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Mapping, Optional, Sequence, Tuple

from strategy.run_brief import brief_for_domain

#: Exact qualifying samples to reach each band (mirrors ``_confidence_from``).
TARGET_ADEQUATE = 3
TARGET_STRONG = 4

#: Bands that count as "this domain is covered" for the overall figure.
_READY_LEVELS = frozenset({"adequate", "strong"})

_LEVEL_RANK = {"missing": 0, "developing": 1, "adequate": 2, "strong": 3}

#: Readiness dimension name (as produced by ``to_readiness``) -> the run-brief domain
#: key. The two vocabularies differ ("base_setup" vs "setup_base"), so this is the one
#: place they are reconciled.
_READINESS_TO_DOMAIN = {
    "base_setup": "setup_base",
    "qualifying_setup": "setup_qualifying",
    "race_setup": "setup_race",
    "tyre_evidence": "tyre_model",
    "fuel_evidence": "fuel_model",
    "driver_coaching": "driver_coaching",
    "race_pace": "race_pace",
    "strategy_evidence": "strategy",
    "consistency": "consistency",
}

#: Human titles for the readiness dimensions.
_TITLES = {
    "base_setup": "Base setup",
    "qualifying_setup": "Qualifying setup",
    "race_setup": "Race setup",
    "tyre_evidence": "Tyre wear",
    "fuel_evidence": "Fuel use",
    "driver_coaching": "Driver coaching",
    "race_pace": "Race pace",
    "strategy_evidence": "Strategy",
    "consistency": "Consistency",
}

#: The order a programme naturally runs in: establish the base, develop the setup and
#: driver, model tyres/fuel, then qualifying, race and strategy. Anything unlisted sorts
#: last, alphabetically.
_PROGRAMME_ORDER = (
    "base_setup", "race_setup", "driver_coaching", "consistency",
    "tyre_evidence", "fuel_evidence", "race_pace", "qualifying_setup",
    "strategy_evidence",
)

_EXACT_RE = re.compile(r"(\d+)\s*exact")


def _norm(v) -> str:
    return "" if v is None else str(v).strip()


def _exact_from_note(note: str) -> int:
    """The exact-sample count carried in a readiness note ("2 exact / 0 labelled…")."""
    m = _EXACT_RE.search(_norm(note))
    if not m:
        return 0
    try:
        return max(0, int(m.group(1)))
    except (TypeError, ValueError):
        return 0


@dataclass(frozen=True)
class DomainProgress:
    """One evidence domain's place in the programme."""

    key: str                 # readiness dimension name, e.g. "driver_coaching"
    title: str               # "Driver coaching"
    level: str               # missing | developing | adequate | strong
    done: int                # exact qualifying samples recorded
    target: int = TARGET_ADEQUATE
    stretch: int = TARGET_STRONG
    capped: bool = False     # partial/unknown evidence can't pass "developing"
    run_name: str = "practice run"
    run_type: str = ""       # evidence-domain key the run card/objective uses
    is_next: bool = False    # the engineer's current objective

    @property
    def is_ready(self) -> bool:
        return self.level in _READY_LEVELS

    @property
    def runs_remaining(self) -> int:
        """Qualifying runs still needed to reach 'adequate'. 0 once there."""
        return max(0, self.target - self.done)

    @property
    def progress_text(self) -> str:
        if self.is_ready:
            extra = "" if self.done < self.stretch else " (strong)"
            return f"{self.done} of {self.target} runs — covered{extra}"
        if self.capped and self.done == 0:
            return "needs a clean run in this exact car and track"
        n = self.runs_remaining
        return (f"{self.done} of {self.target} runs — "
                f"{n} more {'run' if n == 1 else 'runs'} to cover")


@dataclass(frozen=True)
class ProgrammeMap:
    domains: Tuple[DomainProgress, ...] = field(default_factory=tuple)
    domains_ready: int = 0
    domains_total: int = 0
    overall_pct: int = 0
    #: (title, run_name) for the next few runs, weakest domain first.
    next_runs: Tuple[Tuple[str, str], ...] = field(default_factory=tuple)
    headline: str = ""

    @property
    def has_programme(self) -> bool:
        return bool(self.domains)


def _order_index(key: str) -> int:
    try:
        return _PROGRAMME_ORDER.index(key)
    except ValueError:
        return len(_PROGRAMME_ORDER)


def build_programme_map(
    readiness: Sequence,
    *,
    next_domain: str = "",
    next_count: int = 3,
) -> ProgrammeMap:
    """Build the map from readiness dimensions. Never raises.

    ``readiness`` is the ``[(name, level, note), ...]`` list the preparation report and
    the Command Centre view both expose (a tuple or a 3-item sequence per row). The exact
    count is read from the note. ``next_domain`` is the run-brief domain the engineer is
    currently pointing at (from the next-action), so the map can flag which row is live;
    ``next_count`` caps how many upcoming runs are listed.
    """
    try:
        return _build(readiness, next_domain=next_domain, next_count=next_count)
    except Exception:  # pragma: no cover - defensive
        return ProgrammeMap()


def _build(readiness, *, next_domain: str, next_count: int) -> ProgrammeMap:
    rows = []
    for entry in (readiness or ()):
        name, level, note = _row(entry)
        if not name:
            continue
        domain_key = _READINESS_TO_DOMAIN.get(name, "")
        brief = brief_for_domain(domain_key) if domain_key else None
        done = _exact_from_note(note)
        # A domain is capped when partial/unknown ("labelled") samples hold its band at
        # developing even though its exact count has reached the adequate target. Read it
        # straight from the note's labelled count rather than inferring.
        capped = (_labelled_from_note(note) > 0
                  and done >= TARGET_ADEQUATE
                  and _LEVEL_RANK.get(_norm(level).lower(), 0) < _LEVEL_RANK["adequate"])
        rows.append(DomainProgress(
            key=name,
            title=_TITLES.get(name, name.replace("_", " ").title()),
            level=_norm(level).lower() or "missing",
            done=done,
            capped=capped,
            run_name=(brief.run_name if brief else "practice run"),
            run_type=domain_key,
            is_next=bool(next_domain) and domain_key == next_domain,
        ))

    rows.sort(key=lambda d: (_order_index(d.key), d.key))
    total = len(rows)
    ready = sum(1 for d in rows if d.is_ready)
    pct = int(round(100 * ready / total)) if total else 0

    # The next runs to do: domains not yet covered, weakest first, then programme order.
    pending = [d for d in rows if not d.is_ready]
    pending.sort(key=lambda d: (_LEVEL_RANK.get(d.level, 0), _order_index(d.key)))
    next_runs = tuple((d.title, d.run_name) for d in pending[:max(0, int(next_count or 0))])

    headline = _headline(ready, total, pending)
    return ProgrammeMap(domains=tuple(rows), domains_ready=ready, domains_total=total,
                        overall_pct=pct, next_runs=next_runs, headline=headline)


def _headline(ready: int, total: int, pending) -> str:
    if not total:
        return "No programme yet — record a run to start building evidence."
    if ready >= total:
        return "Every area is covered — confirm and protect the setup before the event."
    remaining = sum(d.runs_remaining for d in pending) if pending else 0
    return (f"{ready} of {total} areas covered. "
            f"About {remaining} more recorded {'run' if remaining == 1 else 'runs'} "
            f"to cover the rest.")


def _row(entry) -> Tuple[str, str, str]:
    """Normalise a readiness row to (name, level, note). Accepts a tuple/list or a Mapping."""
    if isinstance(entry, Mapping):
        return (_norm(entry.get("name") or entry.get("dimension")),
                _norm(entry.get("level")).lower(), _norm(entry.get("note")))
    try:
        name = _norm(entry[0])
        level = _norm(entry[1]).lower() if len(entry) > 1 else ""
        note = _norm(entry[2]) if len(entry) > 2 else ""
        return name, level, note
    except (TypeError, IndexError, KeyError):
        return "", "", ""


_LABELLED_RE = re.compile(r"(\d+)\s*labelled")


def _labelled_from_note(note: str) -> int:
    m = _LABELLED_RE.search(_norm(note))
    if not m:
        return 0
    try:
        return max(0, int(m.group(1)))
    except (TypeError, ValueError):
        return 0
