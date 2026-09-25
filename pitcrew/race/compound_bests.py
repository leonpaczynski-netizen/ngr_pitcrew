"""Per-compound best laps for the practice tablet (Story 3, 25 Sep 2026).

His ask for the practice face on the tablet (20 Sep 2026): the best lap per
compound, so a tyre crossover shows up at a glance before the next session.

**What counts, and what does not.** Only laps the export also counts: out-laps,
in-laps, excluded laps and laps with a null time are all refused.  An out-lap
is short by definition (a pit-exit-to-line fragment at Daytona was once 93.100 s
and `LapRow.counted` is the one expression that strikes it correctly).  Using
any other filter would mean the tablet's best and the export's best disagree for
the same session (rules 3 and 13).

**Ordered best first** so the front-end can read entry 0 as "the fastest compound
seen today" without sorting.

**`best_ms` is integer milliseconds** throughout — the same unit the export and
`format_lap_ms` speak.
"""
from __future__ import annotations


def compound_bests_for_session(laps) -> list[dict]:
    """Best lap per compound, over counted laps only.

    `laps` is any iterable of `LapRow` objects (or duck-types with `.counted`,
    `.lap_time_ms` and `.compound`).

    Returns a list of ``{"compound": str, "best_ms": int, "lap_count": int}``
    ordered by `best_ms` ascending (fastest compound first).  Returns an empty
    list when there are no qualifying laps.

    **A `None` compound is grouped as its own key** — a session where the disc
    was never read still has a best, and silently dropping it would make the
    section disappear when the rack has laps but no compound reads (rule 3).
    However the front-end may choose to dim or label a `None` compound
    differently.
    """
    groups: dict = {}   # compound -> list[int]  (lap_time_ms values)
    for row in (laps or []):
        # `counted` is the one predicate shared with the export (practice_screen
        # line 200-213): out-laps, pit-laps, excluded laps and incidents are all
        # False here, and we do not re-derive the rule.
        if not getattr(row, "counted", False):
            continue
        ms = getattr(row, "lap_time_ms", None)
        if ms is None or ms <= 0:
            # A zero time is a lap whose telemetry was never filed (rule 3).
            continue
        compound = getattr(row, "compound", None)
        groups.setdefault(compound, []).append(ms)

    result = [
        {"compound": c, "best_ms": int(min(times)), "lap_count": len(times)}
        for c, times in groups.items()
    ]
    result.sort(key=lambda r: r["best_ms"])
    return result
