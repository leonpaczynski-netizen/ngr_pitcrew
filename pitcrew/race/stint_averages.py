"""Stint-average deltas for the tablet's own-car block (Story 1, 25 Sep 2026).

The driver wants to see his own lap-time and burn trends alongside the field,
without leaving the tablet screen.  `stint_plan_averages` computes them from
the same `lap_history` the monitor's rack draws from - one source, so the two
surfaces cannot disagree about the same session (rule 13).

**What "current stint" means here, and why it matters.** A pit lap resets the
reference: laps driven before the stop are from a different tyre set, a
different fuel window, and a different plan target.  The stint whose averages
the driver acts on is the one he is in NOW, so only laps after the last pit
entry are collected.  A session with no pit lap at all is one stint from the
green, and all qualifying laps count.

**DERIVED, and both carry a count** (rule 5, rule 4).  The plan target changes
lap to lap with fuel weight; a mean is a rough guide, not a measurement, and
it is labelled as such in the payload.  Fewer than two qualifying laps means
nothing reliable can be said - the function returns `(None, None, 0)` and the
tablet draws a dash rather than a figure from one data point.
"""
from __future__ import annotations


def stint_plan_averages(
    lap_history,
) -> tuple[int | None, float | None, int]:
    """Mean lap-delta and burn-delta over the current stint's qualifying laps.

    `lap_history` is the sequence of dicts `RaceState.lap_history` carries,
    newest last, each with at minimum the keys `lap_delta_s`, `burn_delta_l`,
    `pit` and `out`.  Missing or None values on any required key exclude the
    lap silently.

    Returns `(avg_lap_delta_ms, avg_burn_delta_l, count)`.

    * `avg_lap_delta_ms` is rounded to the nearest integer millisecond;
      `burn_delta_l` carries the float precision the targets already use.
    * `count` is the number of qualifying laps the averages rest on.
    * All three are `None` / 0 when fewer than 2 qualifying laps exist - one
      point is not a trend (rule 4).

    **The stint resets at the LAST pit lap, not the first.**  A history that
    holds both the pit lap and the laps after it should give averages for the
    new stint only.  Laps are walked newest-last and collection stops the
    moment a `pit==True` row is seen - that row is itself excluded (a pit
    lap's split is partial, not representative of race pace) and everything
    before it is from the previous stint.
    """
    laps = list(lap_history or ())
    # Walk newest-first so the first pit lap encountered is the LAST one; stop
    # there and keep only the laps after it (which are earlier in the list,
    # i.e. later in the walk).
    current_stint: list[dict] = []
    for lap in reversed(laps):
        if lap.get("pit"):
            # This is the boundary.  The pit lap itself is excluded; everything
            # before it belongs to the previous stint.  Stop collecting.
            break
        if lap.get("out"):
            # The out-lap is structural: the car is on cold tyres and may carry
            # a partial lap.  It keeps its row on the rack but its split tells
            # us nothing about race pace, so excluded from the averages.
            continue
        current_stint.append(lap)

    # Collect only laps where both deltas are non-null - a lap with no plan
    # target has no delta and contributes nothing to a plan-deviation average.
    qualifying = [
        lap for lap in current_stint
        if lap.get("lap_delta_s") is not None
        and lap.get("burn_delta_l") is not None
    ]
    n = len(qualifying)
    if n < 2:
        # One data point is not a trend and must not be presented as one
        # (rule 4).  Returning None explicitly rather than clamping to 0 -
        # a 0 delta would look like a measurement of "exactly on target".
        return None, None, 0

    lap_delta_ms = round(
        sum(lap["lap_delta_s"] for lap in qualifying) / n * 1000
    )
    burn_delta_l = sum(lap["burn_delta_l"] for lap in qualifying) / n
    return lap_delta_ms, burn_delta_l, n
