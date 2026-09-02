"""What a rival's stop costs him, and whether that is more than ours costs us.

*"If we know when a rival pits and the fuel they come in on, we know if we have
a fuel advantage or not, and what they leave with, and how long they spent in
the pits compared to what we will spend."* — the driver, 2 Sep 2026, and he is
right that this stands on its own.

**This is arithmetic on observed quantities, and that is the point.** It needs
no degradation model, no tyre-age lever and no theory about undercuts. Litres
taken divided by a measured refuel rate is seconds standing still; the
difference between his and ours is the swing across the stop cycle. Every term
is either read off the screen or measured from our own tank.

### Why that is the whole game in GT7

GT7 has no partial tyre change and no split compounds, so the only part of a
stop that VARIES between two cars is fuel. Measured on this driver's own
archive: at Monza he stood for 48-63 s taking 48-63 L at a measured 1.001 L/s,
against a pit transit of the order of ten seconds. A rival taking twenty litres
where he takes fifty is thirty seconds cheaper in the box, and no tyre
advantage on this driver's wear multipliers comes close to paying that back.

### What this deliberately does NOT do

**It does not recommend an undercut**, and the reason is measured rather than
stylistic. At the 2x wear he actually races, his stints end at 0.44-0.56 worst
corner — CLAUDE.md §5.1 phase 1, "losses in tenths" — so there is no old-tyre
pace loss to gain against. Any undercut model would be multiplying by a number
never observed at his multiplier, which is rule 5.

**It does not assume the pit delta cancels.** Two cars pitting on different
laps take different fuel loads, so their stops are different lengths, and that
difference is the whole of `fuel_swing`.

**But a lap deferred does NOT shorten your own stop, and this file used to say
it did.** It shrinks the fill by a lap's burn and it also means arriving with a
lap's burn less aboard; the two cancel exactly, leaving `laps_total x burn -
start` litres to be taken whatever lap the stop happens on. `deferring_costs_s`
carries the corrected arithmetic and the measured table.

**It does not speak.** It answers what a stop costs; the caller decides whether
that is worth saying.
"""
from __future__ import annotations

from dataclasses import dataclass

# **Measured, and it is not the figure the strategy model uses.** Time from pit
# entry to the first rise in the tank, measured off the frames at all three
# Monza stops as 16.93 s and identical between them to 0.01 s. CLAUDE.md §5.4
# says 5-10 s and understates it; `strategy/model.py` uses 7.5.
#
# It is carried here as an ADDITIVE term only where the caller supplies a
# transit that excludes it. Where a circuit's stored `pit_loss_secs` already
# describes the whole non-fuel cost - which is what the measured 17.6-19.0 s at
# Monza against a declared 19.0 says it does - adding this again double-counts
# by eight seconds, and that defect is live in the strategy model today.
DEAD_TIME_S = 16.9
DEAD_TIME_SOURCE = "measured: 3 Monza stops, 16.93 s, identical to 0.01 s"


@dataclass(frozen=True)
class Stop:
    """One stop, as observed. Every field may be `None` — it was not seen.

    Nullable throughout and deliberately so: these come from reading a screen,
    and a reader that returns 0.0 for "could not see it" writes a rival's fuel
    down as an empty tank. CLAUDE.md rule 3.
    """
    lap: int | None = None
    fuel_in_l: float | None = None
    fuel_out_l: float | None = None
    tyres_changed: bool | None = None
    compound: str | None = None

    @property
    def litres(self) -> float | None:
        """Fuel taken, or None. Never negative and never clamped to zero.

        A negative result means one of the two readings is wrong, not that no
        fuel was taken — clamping it would turn "I misread" into a confident
        "he took nothing", which is CLAUDE.md rule 9.
        """
        if self.fuel_in_l is None or self.fuel_out_l is None:
            return None
        taken = self.fuel_out_l - self.fuel_in_l
        return taken if taken >= 0 else None

    def standing_s(self, refuel_rate_lps: float | None) -> float | None:
        """Seconds stationary: the fill, plus the dead time before it starts."""
        litres = self.litres
        if litres is None or not refuel_rate_lps or refuel_rate_lps <= 0:
            return None
        return litres / refuel_rate_lps + DEAD_TIME_S


@dataclass(frozen=True)
class Swing:
    """What a stop cycle is worth against a rival's, and why.

    `seconds` is positive when WE come out ahead of where we would have been.
    `reason` names the term that produced it, because a figure whose reason
    comes from a different expression is CLAUDE.md rule 12 — and that rule
    exists because this app has already reported a plan capped by evidence as
    though it were capped by fuel.
    """
    seconds: float | None
    reason: str
    ours_standing_s: float | None = None
    theirs_standing_s: float | None = None

    @property
    def known(self) -> bool:
        return self.seconds is not None


def fuel_swing(ours: Stop, theirs: Stop,
               refuel_rate_lps: float | None) -> Swing:
    """How much longer their stop is than ours, in seconds.

    **The one number the screen makes available that nothing else does.** Both
    cars pay the same pit transit at the same circuit, so it cancels here and
    only here — what does not cancel is what each of them stands still for, and
    on this driver's archive that is 48-63 s against a transit of ten.
    """
    mine = ours.standing_s(refuel_rate_lps)
    yours = theirs.standing_s(refuel_rate_lps)
    if mine is None or yours is None:
        missing = []
        if mine is None:
            missing.append("ours")
        if yours is None:
            missing.append("theirs")
        return Swing(None,
                     f"not known: {' and '.join(missing)} fuel was not read",
                     ours_standing_s=mine, theirs_standing_s=yours)
    swing = yours - mine
    litres = (theirs.litres or 0.0) - (ours.litres or 0.0)
    return Swing(
        swing,
        (f"he takes {litres:+.0f} L on you, which is {swing:+.0f} s "
         f"standing still"),
        ours_standing_s=mine, theirs_standing_s=yours)


def fill_at(stop_lap: int | None, laps_total: int | None,
            burn_per_lap_l: float | None, capacity_l: float | None,
            start_l: float | None = None) -> float | None:
    """Litres taken if the stop happens on this lap, or `None`.

    He fuels to the flag and carries nothing spare, so the fill is what the
    remaining laps cost, clamped by the tank, less what is still aboard.
    """
    if (stop_lap is None or laps_total is None or not burn_per_lap_l
            or burn_per_lap_l <= 0 or not capacity_l or capacity_l <= 0):
        return None
    if stop_lap < 0 or stop_lap > laps_total:
        return None
    aboard = (capacity_l if start_l is None else start_l) - stop_lap * burn_per_lap_l
    if aboard < 0:
        return None                 # he cannot reach that lap on this tank
    needed = (laps_total - stop_lap) * burn_per_lap_l
    return min(capacity_l, needed) - aboard


def deferring_costs_s(lap_now: int | None, laps_total: int | None,
                      burn_per_lap_l: float | None,
                      capacity_l: float | None,
                      refuel_rate_lps: float | None,
                      start_l: float | None = None) -> float | None:
    """Seconds a stop gets LONGER for each lap it is put off. `None` if unknown.

    Positive means deferring costs standing time; negative means it saves it.

    **This replaces a function that had the answer wrong in both directions,
    and it was the headline claim of the module that used it.**
    `deferring_saves_s` returned `burn / rate` - 8 s a lap at Spa - on the
    argument that every lap deferred takes a lap's fuel out of the stop. It
    does. It also means arriving with a lap's fuel less aboard, and the two
    cancel exactly:

        fill = (laps_total - lap) x burn - (start - lap x burn)
             = laps_total x burn - start

    There is no lap term. Over a 20-lap Spa on 8 L a lap from a full 100 L
    tank, 60 litres passes through the hose whatever lap the stop happens on:

        lap      5     6     7     8    10    12
        fill    40    48    56    60    60    60

    So above the tank clamp the saving is **zero**, not eight seconds; and
    below it - where the fill is capped by capacity rather than by the flag -
    the sign inverts and deferring makes the stop eight seconds LONGER per lap,
    which is the one regime where the old figure had the right magnitude and
    the wrong sign.

    What genuinely remains above the clamp is second order and this does not
    pretend otherwise: carrying less fuel for longer is worth about 0.003
    s/L/lap of lap time, and burn falls with load at about 0.0061 L per litre
    aboard. Those are lap time and fuel used, not standing time, so they belong
    to whatever weighs a stint - not here.
    """
    if not refuel_rate_lps or refuel_rate_lps <= 0 or lap_now is None:
        return None
    here = fill_at(lap_now, laps_total, burn_per_lap_l, capacity_l, start_l)
    later = fill_at(lap_now + 1, laps_total, burn_per_lap_l, capacity_l,
                    start_l)
    if here is None or later is None:
        return None
    return (later - here) / refuel_rate_lps


def earliest_stop_lap(laps_total: int | None, lap_now: int | None,
                      burn_per_lap_l: float | None,
                      capacity_l: float | None) -> int | None:
    """The first lap on which a stop can still reach the flag, or None.

    **A hard floor under every stop call, and the design had none.** Stopping
    earlier than this does not merely waste time — the tank cannot hold enough
    fuel to finish, so it forces a second stop worth the better part of a
    minute. This app has already put nine wrong box calls into one race; a box
    call that cannot reach the end is a worse failure than a late one.
    """
    if not laps_total or not lap_now or not burn_per_lap_l or not capacity_l:
        return None
    if burn_per_lap_l <= 0 or capacity_l <= 0:
        return None
    reach = capacity_l / burn_per_lap_l
    earliest = laps_total - reach
    return max(lap_now, int(earliest) + 1 if earliest > int(earliest)
               else int(earliest))


def forced_stop_lap(stop: Stop, burn_per_lap_l: float | None) -> int | None:
    """The last lap a rival can reach on the fuel he left the pits with.

    Their constraint, which changes what we do with ours: a car that must stop
    by lap 22 cannot overcut us to 25. `None` where their fuel was not read —
    an unread tank is not a full one.
    """
    if stop.lap is None or stop.fuel_out_l is None:
        return None
    if not burn_per_lap_l or burn_per_lap_l <= 0:
        return None
    return stop.lap + int(stop.fuel_out_l / burn_per_lap_l)
