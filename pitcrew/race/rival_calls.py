"""What George says about a rival's stop, and the much longer list he does not.

The screen carries a pit flag, a compound and a live fuel figure for every car
that has entered the pit lane. This turns that into calls.

### The one thing that decides a GT7 stop

GT7 has no partial tyre change and no split compounds, so the only part of a
stop that VARIES between two cars is fuel. On this driver's own archive that is
48-63 s of standing at Monza against a pit transit of the order of ten. Litres
divided by a measured refuel rate is seconds, and the difference between his
and a rival's is the swing across the stop cycle.

### Why nothing here recommends an undercut

An adversarial review of the first design found it inverted, and the reason is
measured rather than stylistic. **He fuels to the flag and carries no spare, so
every lap he defers takes a lap's fuel out of his own stop** - 3.2 s at Road
Atlanta, 5.6 at Monza, 8.0 at Spa, against an out-lap penalty measured at about
1.2 s. Staying out is worth several times what fresh tyres are.

And the tyre half is not there to be won: at the 2x wear he races, his stints
end at 0.44-0.56 worst corner, which is CLAUDE.md 5.1 phase 1 - "losses in
tenths" - for the whole stint. There is no old-tyre pace loss to gain against,
so an undercut model would be multiplying by a number never observed at his
multiplier.

### What is knowable, and when

**A rival's fuel is invisible until he pits.** The columns are drawn only for
cars that have entered the lane, so nothing here can predict a stop before it
starts. What it can do is read the entry figure the moment it appears - and
that is enough, because the fill is then predictable: a car fills to what it
needs for the laps that remain, so his standing time follows from the lap he
stopped on rather than from watching him.

### Rule 13, and it bites hard here

`_fuel_gap` in `race/calls.py` already says "gap" meaning laps of fuel in hand.
Rival separations are seconds. **One word, two units, one voice.** So nothing
in this module says "gap" at all: it says litres, seconds standing, and the lap
a car must stop by, and every figure names its own reference inside the call.
"""
from __future__ import annotations

from dataclasses import dataclass

from pitcrew.race.calls import DECISION, HIGH, MEDIUM, Call
from pitcrew.race.rivals import Stop, deferring_saves_s, earliest_stop_lap

# Call kinds. Registered in `calls.REGISTER` so `register_of` can classify
# them - a kind with no register raises, deliberately.
#
# **Deliberately absent from `calls.URGENCY`.** Nothing offers these to
# `_candidates` yet, and `next_call` sorts on `URGENCY.index`, so the day one is
# wired it raises on the race path rather than taking a rank nobody chose. When
# that day comes the ordering is already decided: `RIVAL_BOXED` and
# `RIVAL_COMMITTED` rank BELOW every call about our own fuel, because a car
# about to run dry outranks news about somebody else's stop; `STAY_OUT_FUEL`
# belongs beside `BOX_SOON`, being the argument against it.
RIVAL_BOXED = "rival-boxed"
RIVAL_COMMITTED = "rival-committed"
STAY_OUT_FUEL = "stay-out-fuel"

# A rival's stop has to be worth this many seconds more than ours before it is
# worth saying. Below it he is being told about a difference he cannot drive to.
WORTH_SAYING_S = 8.0

# Seconds of our own standing time saved per lap deferred, below which staying
# out is not worth a call of its own.
DEFER_WORTH_SAYING_S = 3.0


@dataclass(frozen=True)
class Rival:
    """One car we are racing, as the screen has shown it.

    `None` throughout means not seen. A rival whose fuel was never read is not
    a rival with a full tank, and every field here can refuse.
    """
    name: str | None = None
    position: int | None = None
    stop: Stop | None = None
    # Whether the pit flag is showing. Absent is "has not pitted", which the
    # HUD asserts by drawing no columns - that is a fact, not a gap.
    pitted: bool = False


def _fill_to_the_flag(laps_left: int | None,
                      burn_per_lap_l: float | None) -> float | None:
    """The litres a car needs to reach the flag from here.

    No margin. He does not carry one and has said so: six litres left at the
    flag is six seconds standing still, and a battle instead of a gap.
    """
    if not laps_left or not burn_per_lap_l or burn_per_lap_l <= 0:
        return None
    return laps_left * burn_per_lap_l


def rival_boxed(rival: Rival, *, lap: int, laps_left: int | None,
                burn_per_lap_l: float | None,
                refuel_rate_lps: float | None,
                ours: Stop | None) -> Call | None:
    """A rival has entered the pits. What it costs him, against what it costs us.

    Said once, on the lap he enters, because that is when the driver can still
    do something about it. The figure is his STANDING time, not a gap: he is
    stationary for as long as his fill takes and every second of it is a second
    we are driving.
    """
    if not rival.pitted or rival.stop is None:
        return None
    entered_on = rival.stop.fuel_in_l
    if entered_on is None or not refuel_rate_lps or refuel_rate_lps <= 0:
        return None
    needs = _fill_to_the_flag(laps_left, burn_per_lap_l)
    if needs is None:
        return None
    # He fills to what the remaining laps cost, from what he came in on.
    theirs = max(0.0, needs - entered_on) / refuel_rate_lps
    mine = None
    if ours is not None:
        mine_litres = ours.litres
        if mine_litres is not None:
            mine = mine_litres / refuel_rate_lps
    if mine is None:
        if theirs < WORTH_SAYING_S:
            return None
        who = rival.name or "He"
        return Call(RIVAL_BOXED, lap,
                    f"{who} has boxed on {entered_on:.0f} litres.",
                    f"That is about {theirs:.0f} seconds standing.", MEDIUM)
    swing = theirs - mine
    if abs(swing) < WORTH_SAYING_S:
        return None
    who = rival.name or "He"
    if swing > 0:
        return Call(RIVAL_BOXED, lap,
                    f"{who} has boxed on {entered_on:.0f} litres.",
                    f"He stands {swing:.0f} seconds longer than you did.", HIGH)
    return Call(RIVAL_BOXED, lap,
                f"{who} has boxed on {entered_on:.0f} litres.",
                f"He stands {-swing:.0f} seconds less than you did.", HIGH)


def stay_out(*, lap: int, laps_left: int | None,
             burn_per_lap_l: float | None, refuel_rate_lps: float | None,
             capacity_l: float | None, laps_total: int | None,
             planned_stop_lap: int | None) -> Call | None:
    """Every lap deferred takes a lap's fuel out of our own stop.

    **The call the first design had inverted.** It is about our own tank and
    needs no rival at all, which is why it survives when everything about
    reading a rival fails.

    It refuses to fire before the tank can still reach the flag: a stop called
    earlier than that does not waste seconds, it forces a second stop worth
    most of a minute. Rule 12 - where that is what binds, that is what is said.
    """
    saved = deferring_saves_s(burn_per_lap_l, refuel_rate_lps)
    if saved is None or saved < DEFER_WORTH_SAYING_S:
        return None
    floor = earliest_stop_lap(laps_total, lap, burn_per_lap_l, capacity_l)
    if floor is not None and lap < floor:
        return Call(STAY_OUT_FUEL, lap,
                    "Stay out.",
                    f"The tank cannot reach the flag before lap {floor}.",
                    HIGH)
    if planned_stop_lap is not None and lap >= planned_stop_lap:
        return None
    return Call(STAY_OUT_FUEL, lap,
                "Every lap you stay out is a shorter stop.",
                f"About {saved:.0f} seconds less standing, each lap.", MEDIUM)


def must_stop_by(rival: Rival, burn_per_lap_l: float | None,
                 *, lap: int, laps_total: int | None = None) -> Call | None:
    """The last lap a rival can reach on the fuel he left the pits with.

    Their constraint, which changes what we do with ours: a car that must stop
    again cannot overcut us to the flag. `None` where the exit figure was never
    read - an unread tank is not a full one.
    """
    if rival.stop is None or rival.stop.lap is None:
        return None
    out = rival.stop.fuel_out_l
    if out is None or not burn_per_lap_l or burn_per_lap_l <= 0:
        return None
    last = rival.stop.lap + int(out / burn_per_lap_l)
    # **Only when it actually binds.** A car that left the pits with enough
    # fuel to finish has no forced stop, and "he must stop by lap 22" in a
    # twenty-lap race is not a constraint - it is a true sentence about a race
    # that is already over. Rule 12 is about reporting the limit that bound the
    # answer; a limit beyond the flag bound nothing. Measured on the Spa
    # replay, this suppressed two of three calls and left the one that mattered
    # - Boxhead, out on 41 litres, reaching lap 16 of 20.
    if laps_total is not None and last >= laps_total:
        return None
    who = rival.name or "He"
    return Call(RIVAL_COMMITTED, lap,
                f"{who} left on {out:.0f} litres.",
                f"That reaches lap {last}, so he has to stop again.", MEDIUM)
