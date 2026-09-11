"""Pit loss, measured from the race's own lap rows - never declared.

`CLAUDE.md` §5.4: pit time loss is a track constant, measured once per circuit
and stored. It never was. Every event on file carries the app's own 20 s
default under `pit_loss_source = 'declared'`, and `race/refuel.py` measured
the fill at every stop and wrote nothing down. The Deep Forest fill was
discounted by that 20 s; the stop took 52.

The recipe is the one every pit wall uses:

    pit loss = (in-lap + out-lap) - 2 x clean lap

and it is robust to where the start/finish line sits relative to the box -
whichever of the two laps holds the stop, their sum holds all of it. What
comes off it to give the EX-FUEL figure (the lane loss plus the dead time,
which is what a strategy needs) is the litres through the hose at the pump's
rate. The dead time is included in the ex-fuel figure on purpose: it is paid
at every stop whatever is taken.

Returned with every input beside the answer, because a pit loss is a claim
about a circuit that will be reused for a season.
"""
from __future__ import annotations

from dataclasses import dataclass
from statistics import median

# Fewer clean laps than this and the reference lap is a guess, not a median.
MIN_CLEAN_LAPS = 3
# A stop where the hose delivered less than this is treated as tyres-only or
# a drive-through: the fuel term is left out rather than divided by a rate
# that was not exercised.
MIN_FILL_L = 2.0


@dataclass(frozen=True)
class PitLoss:
    total_s: float              # (in-lap + out-lap) - 2 x clean, everything
    ex_fuel_s: float            # total less litres / rate: lane + dead time
    in_lap_ms: int
    out_lap_ms: int
    clean_lap_ms: float         # median of the green laps either side
    clean_laps: int
    fuel_added_l: float | None
    refuel_rate_lps: float | None
    stop_lap: int
    # What the two rows recorded going in, whether or not it could be taken
    # off - so "no fill on file" is never said of a stop that had one.
    fill_seen_l: float | None = None

    @property
    def method(self) -> str:
        if self.fuel_added_l and self.refuel_rate_lps:
            fuel = (f"{self.fuel_added_l:.1f} L at {self.refuel_rate_lps:.2f} "
                    f"L/s taken off")
        elif self.fill_seen_l is None:
            fuel = "no fill on file"
        elif self.fill_seen_l < MIN_FILL_L:
            fuel = (f"{self.fill_seen_l:.1f} L on file - under "
                    f"{MIN_FILL_L:.0f} L, so no fuel term")
        else:
            fuel = (f"{self.fill_seen_l:.1f} L on file but no refuel rate to "
                    f"take it off")
        return (f"(in {self.in_lap_ms / 1000:.1f} s + out "
                f"{self.out_lap_ms / 1000:.1f} s) - 2 x clean "
                f"{self.clean_lap_ms / 1000:.1f} s over {self.clean_laps} laps; "
                f"{fuel}")


def measure(laps: list, *, refuel_rate_lps: float | None) -> list[PitLoss]:
    """One `PitLoss` per stop the rows can resolve, in race order.

    `laps` are the session's rows as dicts (`lap_num`, `lap_time_ms`,
    `is_pit_lap`, `is_out_lap`, `fuel_added_l`, `off_track_s`, `spin_s`).
    A stop needs the pit lap, the out lap that follows it, and at least
    `MIN_CLEAN_LAPS` green laps in the same session that were not the first
    lap, a pit lap, an out lap or an incident.
    """
    rows = sorted((dict(r) for r in laps), key=lambda r: int(r.get("lap_num") or 0))
    by_num = {int(r["lap_num"]): r for r in rows if r.get("lap_num") is not None}
    clean = [int(r["lap_time_ms"]) for r in rows
             if int(r.get("lap_num") or 0) > 1
             and not r.get("is_pit_lap") and not r.get("is_out_lap")
             and not (r.get("off_track_s") or 0) > 1.0
             and not (r.get("spin_s") or 0) > 0
             and not r.get("excluded")
             and (r.get("lap_time_ms") or 0) > 0]
    if len(clean) < MIN_CLEAN_LAPS:
        return []
    reference = float(median(clean))
    out: list[PitLoss] = []
    for row in rows:
        if not row.get("is_pit_lap"):
            continue
        num = int(row["lap_num"])
        following = by_num.get(num + 1)
        if following is None or not following.get("is_out_lap"):
            # The stop straddled the line and the app filed both halves on
            # one row, or the out-lap never came - nothing to sum.
            continue
        in_ms = int(row["lap_time_ms"] or 0)
        out_ms = int(following["lap_time_ms"] or 0)
        if in_ms <= 0 or out_ms <= 0:
            continue
        total = (in_ms + out_ms) / 1000.0 - 2.0 * reference / 1000.0
        # **Both rows, summed** (critic 6 on row 2.5). The fill was taken
        # from the in-lap and only fell back to the out-lap on a None - and
        # Daytona's in-lap stores 0.0 while its out-lap stores the 49 L, so
        # the 0.0 was read as "no fill", the fuel term was dropped, and 72 s
        # with the refuelling inside it was stored as the circuit's measured
        # pit loss. A 0.0 on one row is "not on this row", not "none" (rule 3).
        seen = [float(value) for value in (row.get("fuel_added_l"),
                                           following.get("fuel_added_l"))
                if value is not None]
        added = sum(seen) if seen else None
        fuel_term = 0.0
        fuel_l = None
        if added is not None and added >= MIN_FILL_L and refuel_rate_lps:
            fuel_l = float(added)
            fuel_term = fuel_l / float(refuel_rate_lps)
        out.append(PitLoss(total_s=round(total, 2),
                           ex_fuel_s=round(total - fuel_term, 2),
                           in_lap_ms=in_ms, out_lap_ms=out_ms,
                           clean_lap_ms=reference, clean_laps=len(clean),
                           fuel_added_l=fuel_l,
                           refuel_rate_lps=(float(refuel_rate_lps)
                                            if fuel_l is not None else None),
                           stop_lap=num, fill_seen_l=added))
    return out


def best(stops: list[PitLoss]) -> PitLoss | None:
    """The stop to record: the one with a fuel term, else the first.

    A stop with no fuel term cannot separate lane loss from standing time,
    so it is a ceiling rather than a measurement of the ex-fuel figure.
    """
    with_fuel = [s for s in stops if s.fuel_added_l is not None]
    if with_fuel:
        return min(with_fuel, key=lambda s: s.ex_fuel_s)
    return stops[0] if stops else None
