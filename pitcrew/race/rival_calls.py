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

**The tyre half of the argument is measured and it holds.** At the 2x wear he
races, his stints end at 0.44-0.56 worst corner, which is CLAUDE.md 5.1 phase 1
- "losses in tenths" - for the whole stint. There is no old-tyre pace loss to
gain against, so an undercut model would be multiplying by a number never
observed at his multiplier. Against a measured out-lap penalty of about 1.2 s,
an undercut is roughly a second down before anything else happens.

**The fuel half of the argument was wrong and has been withdrawn.** This module
was written claiming that every lap deferred takes a lap's fuel out of the stop
- 8 s a lap at Spa - and that staying out was therefore worth several times
what fresh tyres are. It is not. A lap deferred does shrink the fill by a lap's
worth, and it also means arriving with a lap's worth less aboard, and the two
cancel exactly: the litres that pass through the hose are `laps_total x burn -
start`, with no lap term in them at all. See `rivals.deferring_costs_s` for the
arithmetic and the measured table. Above the tank clamp the saving is zero;
below it the sign inverts.

So staying out is still right, for smaller and different reasons - fuel weight
and the tank clamp - and this module no longer prices it at eight seconds a
lap.

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

from pitcrew.race.calls import (
    CLOSING,
    HIGH,
    MEDIUM,
    REJOIN,
    RIVAL_BOXED,
    RIVAL_COMMITTED,
    RIVAL_SAVING,
    STAY_OUT_FUEL,
    Call,
)
from pitcrew.race.gaps import (
    MIN_LAPS_FOR_TREND,
    TREND_WORTH_SAYING_S,
    GapTrend,
    rejoin_against,
    stop_costs_s,
)
from pitcrew.race.rivals import (
    DEAD_TIME_S,
    Stop,
    deferring_costs_s,
    earliest_stop_lap,
)

# The three kinds are defined in `calls.py`, beside the ranking that orders
# them, and re-exported here because this is the module that composes them.
# `STAY_OUT_FUEL` sits immediately below `BOX_SOON` - it is the argument
# against it and the two must be adjacent; the other two rank below every call
# about our own car, because a car of ours about to run dry outranks news of
# what somebody else just did.
__all__ = ["CLOSING", "REJOIN", "RIVAL_BOXED", "RIVAL_COMMITTED",
           "RIVAL_SAVING", "STAY_OUT_FUEL", "Rival", "candidates",
           "closing_call", "fuel_shortfall", "must_stop_by", "rejoin_call",
           "rival_boxed", "saving_to_the_flag", "stay_out"]

# A rival's stop has to be worth this many seconds more than ours before it is
# worth saying. Below it he is being told about a difference he cannot drive to.
WORTH_SAYING_S = 8.0

# Seconds of our own standing time saved per lap deferred, below which staying
# out is not worth a call of its own. It is rarely met: above the tank clamp the
# saving is exactly zero - see `rivals.deferring_costs_s` - so this fires only
# in the narrow band where the fill is still capped by the tank rather than by
# the flag, which is the one place a lap deferred genuinely shortens the stop.
DEFER_WORTH_SAYING_S = 3.0

# **What a driver can take out of his own fuel consumption by driving for it.**
# Measured on this driver's own car at Monza: short-shifting alone gave -24.9%
# fuel for +0.5 s/lap. Lift-and-coast is additive but is not on file, so this
# is the conservative half of what is available. A shortfall inside this is one
# a rival drives out; beyond it he has to stop.
SAVEABLE_FRACTION = 0.249
# What that saving costs him, per lap, at the full 24.9%. Interpolated linearly
# below it - which is an ASSUMPTION about the shape and stated as one wherever
# the number is spoken.
SAVING_COSTS_S_PER_LAP = 0.5

# A shortfall has to cost him this many seconds across the remaining laps
# before it is worth a call. Below it he is being told about a car he cannot
# catch any faster than he already was.
SAVING_WORTH_SAYING_S = 1.5


@dataclass(frozen=True)
class Rival:
    """One car we are racing, as the screen has shown it.

    `None` throughout means not seen. A rival whose fuel was never read is not
    a rival with a full tank, and every field here can refuse.
    """
    name: str | None = None
    position: int | None = None
    stop: Stop | None = None
    # **His burn, where the book has watched him.** Every figure here used to
    # apply OURS to him. `profile.py` computes his own and says plainly that
    # 0.4 L/lap is already outside reading error - so at half a litre out over
    # twelve remaining laps that is six litres, six seconds, on calls gated at
    # eight. A call could fire on nothing but the mismatch. `None` falls back
    # to ours, which is a stated assumption rather than a hidden one.
    burn_per_lap_l: float | None = None
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
    needs = _fill_to_the_flag(laps_left, rival.burn_per_lap_l or burn_per_lap_l)
    if needs is None:
        return None
    # **No clamp, and this module quotes the rule it was breaking.** A rival
    # who comes in with more fuel than the remaining laps cost is not a rival
    # who stands still for zero seconds - he is a rival who is not doing what
    # this arithmetic assumes: not filling to the flag, or taking tyres only,
    # or burning at a rate that is not ours. All three are "I cannot tell you",
    # and `max(x, 0.0)` renders them as a confident "about 0 seconds standing"
    # which the swing branch then subtracts from. CLAUDE.md rule 9.
    if needs < entered_on:
        return None
    theirs = (needs - entered_on) / refuel_rate_lps + DEAD_TIME_S
    # **The same words must mean the same thing.** `Stop.standing_s` includes
    # the 16.9 s dead time before a hose is connected, and this used to compute
    # the fill alone - so "seconds standing" meant two quantities 16.9 s apart
    # depending on which function said it, on one voice, with a threshold of
    # 8 s deciding whether to speak at all. CLAUDE.md rule 13.
    mine = ours.standing_s(refuel_rate_lps) if ours is not None else None
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
    floor = earliest_stop_lap(laps_total, lap, burn_per_lap_l, capacity_l)
    if floor is not None and lap < floor:
        # **Not "the tank cannot reach the flag".** Under a helmet those are
        # the words of an emergency, and this call means the opposite: there is
        # too much fuel aboard to fill usefully yet. `calls.py` learned exactly
        # this about leading with "No fuel" and the lesson did not travel.
        return Call(STAY_OUT_FUEL, lap,
                    "Stay out.",
                    f"Too much fuel aboard to fill. Lap {floor} at the "
                    f"earliest.", HIGH)
    if planned_stop_lap is not None and lap >= planned_stop_lap:
        return None
    # **Above the clamp there is no seconds argument, so there is no call.**
    # The fill is the same length whatever lap it happens on, and saying "every
    # lap you stay out is a shorter stop" was not a small overstatement - it
    # was a claim of eight seconds a lap where the true figure is zero. What
    # remains in favour of staying out is fuel weight and tyre life, neither of
    # which is a standing-time figure and neither of which this function has.
    cost = deferring_costs_s(lap, laps_total, burn_per_lap_l, capacity_l,
                             refuel_rate_lps)
    if cost is None or cost > -DEFER_WORTH_SAYING_S:
        return None
    return Call(STAY_OUT_FUEL, lap,
                "Every lap you stay out is a shorter stop.",
                f"About {-cost:.0f} seconds less standing, each lap.", MEDIUM)


@dataclass(frozen=True)
class Shortfall:
    """How far a rival is from reaching the flag on what he left the pits on.

    `litres` is what he is missing - positive means short. `fraction` is that
    against what the run needs, which is the figure that decides whether he
    drives it out or stops again, because saving is a percentage of
    consumption and not a number of litres.
    """
    litres: float
    fraction: float
    laps_to_flag: int
    needs: float
    saveable: bool
    # **Whether it is bigger than we can read.** A rival's burn comes from
    # entry-to-exit readings one stint apart, so it is one number for a whole
    # stint and the fill is known to about four litres. A two-litre shortfall
    # against that is not a finding.
    certain: bool


def fuel_shortfall(rival: Rival, burn_per_lap_l: float | None, *,
                   laps_total: int | None,
                   reading_error_l: float = 4.0) -> Shortfall | None:
    """What he is short by, or `None` where it cannot be computed.

    **His own burn where the book has it, ours where it does not** - and never
    a default tank. An unread exit figure is not a full one.
    """
    if rival.stop is None or rival.stop.lap is None or laps_total is None:
        return None
    out = rival.stop.fuel_out_l
    burn = rival.burn_per_lap_l or burn_per_lap_l
    if out is None or not burn or burn <= 0:
        return None
    laps_to_flag = laps_total - rival.stop.lap
    if laps_to_flag <= 0:
        return None
    needs = laps_to_flag * burn
    short = needs - out
    return Shortfall(litres=short, fraction=short / needs,
                     laps_to_flag=laps_to_flag, needs=needs,
                     saveable=short <= needs * SAVEABLE_FRACTION,
                     certain=abs(short) > reading_error_l)


def saving_to_the_flag(rival: Rival, burn_per_lap_l: float | None, *,
                       lap: int, laps_total: int | None = None,
                       reading_error_l: float = 4.0) -> Call | None:
    """A rival who reaches the flag only by saving, and what it costs him.

    **The third case, and the one that was silent.** `must_stop_by` split the
    race into "he has to stop again" and nothing at all - so a car that makes
    the flag comfortably and a car that makes it only by short-shifting from
    here sounded identical, and they are opposite races. This is the second of
    those: he is committed to the pace he can afford, and that is the moment to
    attack.

    Everything about it is honest about being derived. The shortfall is read
    off two screen figures and a burn rate estimated from one stint; the
    conversion into seconds uses OUR car's measured exchange rate, because his
    is not knowable, and the call says so.
    """
    short = fuel_shortfall(rival, burn_per_lap_l, laps_total=laps_total,
                           reading_error_l=reading_error_l)
    if short is None or short.litres <= 0:
        return None            # he has enough; nothing to say
    if not short.saveable:
        return None            # `must_stop_by` has this one
    if not short.certain:
        # Inside what two fuel readings and a one-stint burn can resolve.
        # Saying it anyway would be reporting the noise as a finding.
        return None
    costs = (short.fraction / SAVEABLE_FRACTION) * SAVING_COSTS_S_PER_LAP
    over_the_run = costs * short.laps_to_flag
    if over_the_run < SAVING_WORTH_SAYING_S:
        return None
    who = rival.name or "He"
    return Call(RIVAL_SAVING, lap,
                f"{who} is saving to the flag. Attack.",
                f"{short.litres:.0f} litres light over {short.laps_to_flag} "
                f"laps - about {costs:.1f} seconds a lap if he short-shifts "
                f"for it.",
                MEDIUM, severity=over_the_run)


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
    burn = rival.burn_per_lap_l or burn_per_lap_l
    if out is None or not burn or burn <= 0:
        return None
    last = rival.stop.lap + int(out / burn)
    # **Only when it actually binds.** A car that left the pits with enough
    # fuel to finish has no forced stop, and "he must stop by lap 22" in a
    # twenty-lap race is not a constraint - it is a true sentence about a race
    # that is already over. Rule 12 is about reporting the limit that bound the
    # answer; a limit beyond the flag bound nothing. Measured on the Spa
    # replay, this suppressed two of three calls and left the one that mattered
    # - Boxhead, out on 41 litres, reaching lap 16 of 20.
    if laps_total is not None and last >= laps_total:
        return None
    # **Short of the flag is not the same as forced to stop.** A stop costs him
    # a pit loss; a lift costs him tenths, so a driver who is a few per cent
    # light drives it out and does not come in. Told "he has to stop again",
    # the driver waits for a stop that never comes and does not attack the car
    # that is right there being slow. Measured: our own short-shift exchange is
    # -24.9% fuel for +0.5 s/lap, so anything inside a quarter of the run is
    # drivable. `saving_to_the_flag` says that case, and this one now refuses
    # it rather than asserting the wrong half.
    short = fuel_shortfall(rival, burn_per_lap_l, laps_total=laps_total)
    if short is not None and short.saveable:
        return None
    who = rival.name or "He"
    return Call(RIVAL_COMMITTED, lap,
                f"{who} left on {out:.0f} litres.",
                f"That reaches lap {last}, so he has to stop again.", MEDIUM)

def rejoin_call(*, lap: int, gap_behind_s: float | None,
                litres_to_take: float | None,
                refuel_rate_lps: float | None,
                pit_loss_s: float | None,
                pit_loss_source: str | None = None,
                who: str | None = None) -> Call | None:
    """Where a stop taken now would put us against the car behind.

    **The call that decides a PLACE where the rest of this module decides
    seconds.** A stop costs the fill plus the lane and he gains every second of
    it, so every car closer than that comes out in front of us. It is one
    subtraction, and neither operand was available to the engineer before.

    Silent when we come out comfortably ahead: that is the expected case and
    saying it every lap is noise. Spoken when we come out behind, and spoken
    when it is too close to call - "it is marginal" is something the driver can
    act on, and a silence is not.
    """
    cost = stop_costs_s(litres_to_take, refuel_rate_lps, pit_loss_s,
                        pit_loss_source)
    rejoin = rejoin_against(gap_behind_s, cost)
    if rejoin is None:
        return None
    them = who or "the car behind"
    if rejoin.ahead is False:
        return Call(REJOIN, lap,
                    f"Box now and {them} comes out in front.",
                    f"He is {rejoin.their_gap_s:.0f} seconds back and the stop "
                    f"costs {rejoin.ours_lost_s:.0f}.", HIGH)
    if rejoin.too_close:
        return Call(REJOIN, lap,
                    "Box now and it is too close to call.",
                    f"He is {rejoin.their_gap_s:.0f} seconds back against a "
                    f"{rejoin.ours_lost_s:.0f} second stop.", MEDIUM)
    return None


def closing_call(trend: GapTrend, *, lap: int, who: str | None = None,
                 laps_left: int | None = None) -> Call | None:
    """How fast a gap is closing, and when it reaches zero.

    A FACT, not an instruction: what to do about catching somebody is the
    driver's own call. Said only on a real trend - `MIN_LAPS_FOR_TREND`
    CONSECUTIVE laps - and only when the rate is outside what a random walk
    produces on its own, which is a much larger number than it looks. See
    `gaps.TREND_WORTH_SAYING_S`.

    **The sentence depends on which side the trend is.** The rate means the
    same thing on both - the gap is shrinking - but a shrinking gap ahead is us
    catching him and a shrinking gap behind is him catching us, and those two
    demand opposite driving. Rule 13.
    """
    rate, count = trend.closing_s_per_lap()
    if rate is None or count < MIN_LAPS_FOR_TREND:
        return None
    if abs(rate) < TREND_WORTH_SAYING_S:
        return None
    behind = getattr(trend, "side", "ahead") == "behind"
    them = who or ("the car behind" if behind else "the car ahead")
    closing = rate > 0
    if behind:
        if not closing:
            return None          # he is dropping away: nothing to do about it
        return Call(CLOSING, lap,
                    f"{them} is taking {rate:.1f} a lap out of you.",
                    f"Over the last {count} laps.", MEDIUM)
    if not closing:
        return Call(CLOSING, lap,
                    f"You are losing {-rate:.1f} a lap to {them}.",
                    f"Over the last {count} laps.", MEDIUM)
    laps = trend.laps_to_catch(laps_left=laps_left)
    reason = (f"Over the last {count} laps." if laps is None
              else f"On him in about {laps:.0f} laps at that rate.")
    return Call(CLOSING, lap,
                f"You are taking {rate:.1f} a lap out of {them}.",
                reason, MEDIUM)


def candidates(state) -> list:
    """Every rival call true this lap, for `calls.next_call` to rank.

    **The road in, which did not exist.** `rival_boxed` and `must_stop_by` were
    written, documented and tested, and reachable from nothing: the controller
    emitted `rival_stopped` into a signal with no connection, and no candidate
    in `calls._candidates` had ever heard of a rival. Everything below the
    reader was correct and silent - the same "exists, documented, never called"
    shape as `LiveWearSampler.new_session()` and the handover context.

    Each rival is asked separately and the ranking picks between them, because
    a race has several and only one thing gets said a lap.
    """
    out = []
    for rival in (state.rivals or {}).values():
        if not isinstance(rival, Rival):
            continue
        out.append(saving_to_the_flag(
            rival, state.fuel_per_lap_l,
            lap=state.lap, laps_total=state.laps_total))
        out.append(must_stop_by(
            rival, state.fuel_per_lap_l,
            lap=state.lap, laps_total=state.laps_total))
    out = [call for call in out if call is not None]
    # **The biggest opportunity first, because only one of them gets said.**
    # `next_call` sorts by kind and Python's sort is stable, so two rivals
    # saving would have been separated by the order they happened to stop in -
    # and a call kind is said once a stint, so the second is not said at all.
    # Ordering by severity here makes the one that survives the one worth
    # driving to.
    out.sort(key=lambda c: -(c.severity or 0.0))
    return out
