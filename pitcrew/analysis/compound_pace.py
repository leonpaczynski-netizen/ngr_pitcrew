"""Bests and pace gaps per compound, on the lap and on each sector - plan row 5.22.

The driver, 14 Sep 2026: *"a best time for each compound run and best sector
times for each compound, how does the total lap time compare per compound as
well as each sector"*. Two different claims, kept apart because they answer
different questions and obey different rules:

**A best is a mark.** The fastest lap and the fastest each sector has been on
one compound, with the number of laps it was the best OF. It is the fastest
thing he did, not what the tyre is worth: one lap in a tow on a fresh set is a
best. So bests are never subtracted from each other to make a gap.

**A gap is a comparison.** "RM +0.5 s on RH" is only a statement about tyres
when the laps are alike, so every gap - the lap and each sector - comes off
`strategy.evidence.comparable_groups`: within `PACE_MAX_TYRE_AGE` laps of a
set going on, inside one fuel band, at least `PACE_MIN_LAPS` a side, and all
in **one sitting**. Where that cannot be met the gap is refused with the
reason, never replaced by a difference of bests or of whole-session medians -
that is the figure that once made a Racing Medium quicker than a Racing Soft.

**A sitting is a chain of back-to-back sessions, not one session** - each
starting within `SITTING_GAP_H` of the one before - and this is wider than
strategy's rule, which stays the session. The driver sweeps compounds by
restarting from the garage on each set (Sardegna, 9 Sep: RH, RM, RS as sessions
153-155), so a session never holds two compounds and the session rule refuses
every comparison he has run. **So every gap says it spans separate sessions and
that the race plan does not use it** (critic pass 1, rule 13: the Practice
screen and `strategy_evidence` read the same laps and must not appear to
disagree silently). The price of the wider unit is that the gap carries
whatever changed between sessions - a setup click, his warm-up, the track - so
each sitting reports its **session-to-session floor** where one compound has
`PACE_MIN_LAPS` comparable laps in two of its sessions: how far the same tyre
moved between them. A gap inside that floor is not a tyre difference, and the
report says so. Where no compound qualifies there is no floor, and the words
say exactly that - not "no tyre ran twice", which was false at Sardegna on 10
Sep, where RM ran twice but its second run lost its young laps to incidents.

**The reference compound is fixed by hardness, not by count**: the hardest
compound in the group in GT7's catalogue order (`store.tyres.ALL_COMPOUNDS`),
unless the caller names one. Most-run, strategy's rule, can change hands as a
session adds laps, and every row's sign reverses when it does. A sitting whose
sessions hold two compounds but not the reference is named in `refusals`, never
silently dropped.

**Sector medians do not add up to the lap median** - each is the middle of its
own laps - so the sector gaps are not a split of the lap gap, and the report
says so.

What is grouped with what:

* **game version** - 1.71 reworked the tyres, so a best either side of it is
  two cars (`analysis/version`);
* **sector model** - the stamp carries the circuit and the lines, so a sector
  is only ever held against a sector cut at the same places;
* **compound** - untagged laps belong to no compound and are counted, not
  guessed.

**Which laps may set a best.** Counted laps (no out-lap, pit lap, strike or
incident) **with all three sectors**, which is `Store.personal_bests`' rule and
for its reason: the span gate refuses a lap whose frames do not run line to
line, so a lap with sectors is a lap that was driven from the line to the line.
That is the guard against the Daytona pit-exit fragment reading as a best.

**The theoretical best** is the three best sectors on one compound added up -
a lap nobody drove, labelled derived, all three or nothing
(`PracticeScreen.optimal_lap`'s rule).

**Spread** is the interquartile range of the laps behind a gap, in seconds, on
each side - so "RM +0.5 s" over laps that scatter by 1.2 s reads as the weak
claim it is. It is not a confidence interval and is not called one.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from statistics import median, quantiles

from pitcrew.analysis.session import LapInput
from pitcrew.store.tyres import ALL_COMPOUNDS
from pitcrew.strategy.evidence import (
    PACE_FUEL_BAND_L,
    PACE_MAX_TYRE_AGE,
    PACE_MIN_LAPS,
    comparable_groups,
    lap_time_of,
)

TIMINGS = ("lap", "S1", "S2", "S3")


def _timing(name: str, model: str | None):
    """The accessor for one timing, refusing a lap cut at other lines."""
    if name == "lap":
        return lambda lap: (lap.lap_time_ms if lap.sector_model == model
                            and all(s is not None for s in lap.sectors_ms)
                            else None)
    index = TIMINGS.index(name) - 1
    return lambda lap: (lap.sectors_ms[index] if lap.sector_model == model
                        else None)


def may_set_a_best(lap: LapInput) -> bool:
    """Counted, and driven line to line - see the module docstring."""
    return (lap.counted and lap.lap_time_ms > 0 and lap.sector_model is not None
            and all(value is not None for value in lap.sectors_ms))


@dataclass(frozen=True)
class CompoundBest:
    game_version: str | None
    sector_model: str
    compound: str
    lap_ms: int
    lap_session_id: int | None
    lap_num: int
    laps: int                                    # laps the best was the best of
    sectors_ms: tuple[int, int, int]

    @property
    def theoretical_ms(self) -> int:
        """Derived: three sectors from up to three laps, never driven."""
        return sum(self.sectors_ms)


@dataclass(frozen=True)
class CompoundGap:
    game_version: str | None
    sector_model: str
    timing: str                                  # "lap", "S1", "S2", "S3"
    compound: str
    reference: str
    delta_s: float                               # median against median
    n: int
    reference_n: int
    spread_s: float                              # IQR of this compound's laps
    reference_spread_s: float
    sitting: str
    sessions: tuple[int | None, ...]             # every session behind both sides
    # How far one compound's median moved between two sessions of this sitting,
    # on this timing; None where no compound has `PACE_MIN_LAPS` comparable
    # laps in two of them.
    floor_s: float | None

    @property
    def inside_floor(self) -> bool | None:
        if self.floor_s is None:
            return None
        return abs(self.delta_s) <= self.floor_s

    def describe(self) -> str:
        """The figure and its laps. **No floor clause**: the floor is the
        sitting's and is said once, in `sitting_line` - a second wording of it
        here printed a sentence the first had already been corrected out of
        (critic pass 2)."""
        sign = "+" if self.delta_s >= 0 else "-"
        return (f"{self.compound} {sign}{abs(self.delta_s):.2f} s on "
                f"{self.reference} over the {self.timing} "
                f"({self.n} laps, spread {self.spread_s:.2f} s, against "
                f"{self.reference_n}, spread {self.reference_spread_s:.2f} s)")


@dataclass(frozen=True)
class CompoundPace:
    bests: tuple[CompoundBest, ...]
    gaps: tuple[CompoundGap, ...]
    # Why a (version, model) group has no gaps, where it has none.
    refusals: tuple[str, ...]
    untagged: int                                # counted laps with no compound
    without_sectors: int                         # counted, tagged, no full sectors

    def across_sittings(self, timing: str = "lap") -> list[str]:
        """Where one comparison was run in more than one sitting, how far apart.

        **Never pooled into one figure.** Two sittings that disagree by more
        than either one's spread are saying the gap moves with something
        other than the tyre, and a mean of them would hide exactly that.
        """
        lines: list[str] = []
        pairs: dict[tuple, list[CompoundGap]] = {}
        for gap in self.gaps:
            if gap.timing == timing:
                key = (gap.game_version, gap.sector_model, gap.compound,
                       gap.reference)
                pairs.setdefault(key, []).append(gap)
        for (_, _, code, reference), found in pairs.items():
            if len(found) < 2:
                continue
            deltas = [gap.delta_s for gap in found]
            apart = max(deltas) - min(deltas)
            widest = max(max(gap.spread_s, gap.reference_spread_s)
                         for gap in found)
            verdict = ("wider than any sitting's own spread - the gap moved "
                       "with something other than the tyre"
                       if apart > widest else
                       "inside the sittings' own spread")
            lines.append(
                f"{code} on {reference} over the {timing}, {len(found)} "
                f"sittings: {', '.join(f'{d:+.2f} s' for d in deltas)} - "
                f"{apart:.2f} s apart, {verdict}")
        return lines


def _iqr_s(times_ms: list[int]) -> float:
    if len(times_ms) < 2:
        return 0.0
    low, _, high = quantiles(times_ms, n=4, method="inclusive")
    return (high - low) / 1000.0


def _groups(laps: list[LapInput]) -> dict[tuple, list[LapInput]]:
    """Laps by (game version, sector model), in the order they were driven.

    Every lap of a version goes into each of that version's model groups, so
    the tyre age `split_runs` counts is the age on the road, not the age among
    laps that happen to carry this stamp; the timing accessor is what refuses
    a lap cut at other lines.
    """
    by_version: dict[str | None, list[LapInput]] = {}
    for lap in laps:
        by_version.setdefault(lap.game_version, []).append(lap)
    out: dict[tuple, list[LapInput]] = {}
    for version, group in by_version.items():
        models = []
        for lap in group:
            if lap.sector_model and lap.sector_model not in models:
                models.append(lap.sector_model)
        for model in models:
            out[(version, model)] = group
    return out


def reference_by_hardness(codes) -> str | None:
    """The hardest compound present, in GT7's catalogue order."""
    present = set(codes)
    return next((c.code for c in ALL_COMPOUNDS if c.code in present), None)


def _floor_s(pools: dict[str, list[LapInput]], timing) -> float | None:
    """The widest move of one compound between two sessions of the sitting,
    counting only a session with `PACE_MIN_LAPS` comparable laps on it."""
    moves = []
    for matched in pools.values():
        by_session: dict[int | None, list[int]] = {}
        for lap in matched:
            by_session.setdefault(lap.session_id, []).append(timing(lap))
        medians = [median(times) for times in by_session.values()
                   if len(times) >= PACE_MIN_LAPS]
        if len(medians) >= 2:
            moves.append((max(medians) - min(medians)) / 1000.0)
    return max(moves) if moves else None


def compound_pace(laps: list[LapInput], reference: str | None = None, *,
                  sitting_of: dict[int | None, str] | None = None) -> CompoundPace:
    """Every best and every like-for-like gap on file for these laps.

    `laps` are one car at one circuit, in the order they were driven - an
    event's practice as `export.build.event_lap_inputs` returns it, incidents
    already marked. `reference` is the compound the gaps are measured against;
    by default the hardest present (module docstring). `sitting_of` names each
    session's sitting (`sittings`); a session missing from it is a sitting of
    its own, which is strategy's rule.
    """
    names = sitting_of or {}

    def group_of(lap: LapInput) -> str:
        return names.get(lap.session_id) or f"session {lap.session_id}"

    bests: list[CompoundBest] = []
    gaps: list[CompoundGap] = []
    refusals: list[str] = []

    counted = [lap for lap in laps if lap.counted]
    untagged = sum(1 for lap in counted if not lap.compound)
    without = sum(1 for lap in counted
                  if lap.compound and not may_set_a_best(lap))

    for (version, model), group in _groups(laps).items():
        eligible = [lap for lap in group
                    if lap.compound and lap.sector_model == model
                    and may_set_a_best(lap)]
        by_code: dict[str, list[LapInput]] = {}
        for lap in eligible:
            by_code.setdefault(lap.compound, []).append(lap)
        for code, pool in by_code.items():
            fastest = min(pool, key=lambda lap: lap.lap_time_ms)
            bests.append(CompoundBest(
                game_version=version, sector_model=model, compound=code,
                lap_ms=fastest.lap_time_ms,
                lap_session_id=fastest.session_id, lap_num=fastest.lap_num,
                laps=len(pool),
                sectors_ms=tuple(min(lap.sectors_ms[i] for lap in pool)
                                 for i in range(3))))

        yardstick = reference or reference_by_hardness(by_code)
        where = f"{version or 'unknown version'}, {model}"
        if len(by_code) < 2:
            refusals.append(
                f"{where}: {len(by_code)} compound{'' if len(by_code) == 1 else 's'}"
                f" with full laps - nothing to compare")
            continue
        if reference is not None and reference not in by_code:
            refusals.append(
                f"{where}: no {reference} laps with all three sectors on file "
                f"to measure against")
            continue
        if yardstick is None:
            refusals.append(
                f"{where}: none of {', '.join(sorted(by_code))} is a compound in "
                f"GT7's catalogue, so there is nothing to measure against")
            continue
        codes_by_sitting: dict[str, set] = {}
        for lap in eligible:
            codes_by_sitting.setdefault(group_of(lap), set()).add(lap.compound)
        shared_none = not any(len(codes) >= 2 for codes in codes_by_sitting.values())
        if shared_none:
            refusals.append(
                f"{where}: no sitting holds two compounds - a gap across "
                f"sittings would compare the days, not the tyres")
        for name in TIMINGS:
            timing = _timing(name, model)
            groups = comparable_groups(group, yardstick, timing, group_of)
            if not groups:
                continue
            for sitting, pools in groups.items():
                reference_times = [timing(lap) for lap in pools[yardstick]]
                reference_ms = median(reference_times)
                floor = _floor_s(pools, timing)
                for code, matched in pools.items():
                    if code == yardstick:
                        continue
                    times = [timing(lap) for lap in matched]
                    behind = pools[yardstick] + matched
                    gaps.append(CompoundGap(
                        game_version=version, sector_model=model, timing=name,
                        compound=code, reference=yardstick,
                        delta_s=(median(times) - reference_ms) / 1000.0,
                        n=len(times), reference_n=len(reference_times),
                        spread_s=_iqr_s(times),
                        reference_spread_s=_iqr_s(reference_times),
                        sitting=sitting,
                        sessions=tuple(sorted({lap.session_id for lap in behind},
                                              key=lambda s: (s is None, s or 0))),
                        floor_s=floor))

        # **Every compound with full laps in a sitting that got no lap gap is
        # said, never dropped** (critic passes 1 and 2) - including one beside
        # a compound that did get one.
        gapped = {(gap.sitting, gap.compound) for gap in gaps
                  if gap.timing == "lap" and gap.game_version == version
                  and gap.sector_model == model}
        named: set[str] = set()
        for sitting, codes in codes_by_sitting.items():
            if len(codes) < 2:
                continue
            if yardstick not in codes:
                named |= codes
                refusals.append(
                    f"{where}, {sitting}: no {yardstick} run to measure "
                    f"{', '.join(sorted(codes))} against")
                continue
            for code in sorted(codes - {yardstick}):
                if (sitting, code) in gapped:
                    continue
                named.add(code)
                refusals.append(
                    f"{where}, {sitting}: no gap for {code} - it needs "
                    f"{PACE_MIN_LAPS}+ laps on it and on {yardstick} within the "
                    f"first {PACE_MAX_TYRE_AGE - 1} laps of a run, inside a "
                    f"{PACE_FUEL_BAND_L:.0f} L fuel band of the {yardstick} laps")
        # **And a compound with a best that only ever ran in sittings of its
        # own** (critic pass 3: Spa's RS, 2 h 07 after the RH and RM runs
        # ended) - a best with no word about its gap reads as an oversight.
        if not shared_none:
            with_gap = {code for _, code in gapped}
            for code in sorted(set(by_code) - {yardstick} - with_gap - named):
                refusals.append(
                    f"{where}: no gap for {code} - it never shared a sitting "
                    f"with {yardstick} (a sitting ends when the next practice "
                    f"session starts more than {SITTING_GAP_H:g} h after the "
                    f"last one ended)")

    return CompoundPace(bests=tuple(bests), gaps=tuple(gaps),
                        refusals=tuple(refusals), untagged=untagged,
                        without_sectors=without)


def sitting_line(gaps, code: str, sitting: str) -> str:
    """One tyre against the reference in one sitting: the lap, then each sector.

    The one wording of a gap row, for the Practice screen and the tool alike.
    """
    row = {g.timing: g for g in gaps if g.compound == code and g.sitting == sitting}
    sample = row.get("lap") or next(iter(row.values()))
    cells = [f"{name} " + ("refused" if row.get(name) is None
                           else f"{row[name].delta_s:+.2f} s")
             for name in TIMINGS]
    if sample.floor_s is None:
        floor = (f"no tyre has {PACE_MIN_LAPS}+ comparable laps in two of these "
                 f"sessions, so no session-to-session floor")
    else:
        floor = (f"the same tyre's lap moved {sample.floor_s:.2f} s between "
                 f"sessions" + (" - the lap gap is inside that"
                                if sample.inside_floor else ""))
    return (f"{code} on {sample.reference}, {sitting}: " + " · ".join(cells)
            + f"  ({sample.n} v {sample.reference_n} laps, the first "
              f"{PACE_MAX_TYRE_AGE - 1} laps of each run, one fuel band. "
              f"Separate sessions, so the race plan does not use it; {floor}. "
              f"Sector gaps do not add up to the lap gap.)")


# A practice session that starts more than this long after the one before it
# ENDED starts a new sitting. Sardegna's sweeps restart within minutes of the
# last run's end; an afternoon and an evening do not chain (critic pass 2:
# chained start to start, 15:00, 18:30 and 22:00 were one sitting).
SITTING_GAP_H = 2.0


def sittings(sessions) -> dict[int, str]:
    """Each session's sitting, from its `started_at` - see the module docstring.

    **`ended_at` is when the session was stopped, not its last lap**, so a
    session left open over a break stretches its sitting into the next block.
    A known looseness, and the refusal lines name the rule so it can be seen.

    `sessions` are dicts with `id`, `started_at` and, where known, `ended_at`
    and `kind` (`Store.list_sessions`). **Practice only**: a race between two
    practice blocks must not bridge them. A sitting is named by its first
    session's start. A session with no readable start time is left out, and so
    becomes a sitting of its own rather than being joined to runs it may not
    belong to.
    """
    def when(text):
        try:
            return datetime.fromisoformat(str(text)) if text else None
        except ValueError:
            return None

    timed = []
    for session in sessions:
        if session.get("kind") not in (None, "practice"):
            continue
        started = when(session.get("started_at"))
        if started is None:
            continue
        ended = when(session.get("ended_at"))
        timed.append((started, ended if ended and ended >= started else started,
                      session["id"]))
    timed.sort()
    out: dict[int, str] = {}
    name, last_end = None, None
    for started, ended, session_id in timed:
        if last_end is None or started - last_end > timedelta(hours=SITTING_GAP_H):
            name = f"runs from {started:%Y-%m-%d %H:%M}"
        out[session_id] = name
        last_end = ended if last_end is None else max(last_end, ended)
    return out


__all__ = ["reference_by_hardness", "sitting_line", "sittings", "CompoundBest", "CompoundGap", "CompoundPace", "TIMINGS",
           "compound_pace", "lap_time_of", "may_set_a_best"]
