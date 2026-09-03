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
    RIVAL_SHORT,
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
           "RIVAL_SHORT", "STAY_OUT_FUEL", "Rival", "candidates",
           "closing_call", "fuel_shortfall", "must_stop_by", "rejoin_call",
           "rival_boxed", "short_to_the_flag", "stay_out"]

# A rival's stop has to be worth this many seconds more than ours before it is
# worth saying. Below it he is being told about a difference he cannot drive to.
WORTH_SAYING_S = 8.0

# Seconds of our own standing time saved per lap deferred, below which staying
# out is not worth a call of its own. It is rarely met: above the tank clamp the
# saving is exactly zero - see `rivals.deferring_costs_s` - so this fires only
# in the narrow band where the fill is still capped by the tank rather than by
# the flag, which is the one place a lap deferred genuinely shortens the stop.
DEFER_WORTH_SAYING_S = 3.0

# How many laps before the planned stop the case for one more lap is worth
# hearing. Before that the driver is not deciding whether to box.
STAY_OUT_WINDOW = 3

# **The tank, because a fill cannot exceed it.** A rival who leaves on a
# brim-full tank and is still short did not CHOOSE the shortfall - he took
# everything the game allows - so nothing about his fill says what he intends
# to do about it. Kept as a fact for the reason clause rather than as a gate.
TANK_L = 100.0
# Within this of the tank he is at the brim: the fuel figure is read to the
# litre and a fill stops a little short of the physical top.
FILL_SLACK_L = 2.0

# **What two screen readings contribute to the uncertainty**, against the burn
# term below which grows with the run. Both readings are integer litres.
READ_ERROR_L = 2.0
# **And what his burn contributes, per lap of the run.** `profile.py` states
# 0.4 L/lap as already outside reading error between two drivers - so over a
# fifteen-lap run to the flag that alone is six litres, and a flat four-litre
# floor was calling a six-litre error certain.
BURN_ERROR_L_PER_LAP = 0.4

# Fewer laps left than this and there is nothing to exploit: a shortfall he
# has to drive out over two laps costs him a fraction of a second in total.
MIN_LAPS_LEFT = 3

# **How far away he can be and still be worth the word "attack".** Beyond it
# the call is a fact about a car the driver cannot see, and §5.5 asks for an
# instruction he can act on.
NEARBY_PLACES = 3

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
    # **His exit fuel is a LOWER BOUND, not a reading.** True where the visit
    # was closed on the clock because he dropped off the visible top eight
    # while standing - which `profile.py` says is the normal case, since a car
    # drops places exactly while it is in the lane. The figure then comes from
    # the middle of the fill, so a full tank reads as a half one and a car with
    # no shortfall at all reads as short. Every call that prices a shortfall
    # refuses on it.
    exit_is_a_bound: bool = False
    # How many stops are behind his burn figure. CLAUDE.md rule 4: one stop is
    # one stint's worth of evidence about a driver who may have been saving.
    burn_stops: int = 0


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
    # **Whether it is bigger than we can read.** Two integer fuel figures plus
    # a burn rate that is one number for a whole stint - and the burn term
    # scales with the laps still to run, which a flat floor did not: at
    # fifteen laps the burn error alone is six litres and a four-litre floor
    # called that certain.
    certain: bool
    error_l: float
    # He left on everything the tank holds, so the shortfall was forced rather
    # than chosen and says nothing about his intent.
    at_the_brim: bool


def fuel_shortfall(rival: Rival, burn_per_lap_l: float | None, *,
                   laps_total: int | None,
                   capacity_l: float = TANK_L) -> Shortfall | None:
    """What he is short by, or `None` where it cannot be computed.

    **His own burn where the book has it, ours where it does not** - and never
    a default tank. An unread exit figure is not a full one.
    """
    if rival.stop is None or rival.stop.lap is None or laps_total is None:
        return None
    if rival.exit_is_a_bound:
        # A bound is not a reading. Pricing one understates his fuel, which
        # invents a shortfall - and an invented shortfall reads exactly like a
        # measured one downstream (rule 3).
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
    error = READ_ERROR_L + BURN_ERROR_L_PER_LAP * laps_to_flag
    return Shortfall(litres=short, fraction=short / needs,
                     laps_to_flag=laps_to_flag, needs=needs,
                     saveable=short <= needs * SAVEABLE_FRACTION,
                     certain=abs(short) > error, error_l=error,
                     at_the_brim=out >= capacity_l - FILL_SLACK_L)


def short_to_the_flag(rival: Rival, burn_per_lap_l: float | None, *,
                      lap: int, laps_total: int | None = None,
                      our_position: int | None = None) -> Call | None:
    """A rival who cannot reach the flag on what he left the pits with, and
    who is close enough for that to be worth driving to.

    **It does not say why, because why is not observable.** The first version
    of this said "he is saving to the flag", which is an assertion of intent -
    and `profile.py`'s own header refuses exactly that: a car that stopped
    early because it was short of fuel looks identical to one that stopped
    early to jump somebody. A rival short of fuel lifts or he stops again, and
    the app cannot tell which. It does not need to: **both are good for us**,
    so the instruction is sound even where the reason is ambiguous, and the
    reason says both rather than picking one.

    The pace it costs him is deliberately NOT spoken. It was: "about 0.2
    seconds a lap", from a linear interpolation through a single measured point
    on OUR car applied to his. That is three assumptions presented as a
    measurement (rule 5). The model still decides whether the shortfall is
    worth a call at all - using a model to choose silence is not the same as
    speaking its output as fact - but the driver hears litres and laps, which
    are read and counted.
    """
    short = fuel_shortfall(rival, burn_per_lap_l, laps_total=laps_total)
    if short is None or short.litres <= 0:
        return None
    if not short.saveable:
        return None            # `must_stop_by` has this one
    if not short.certain:
        # Inside what two integer readings and a one-stint burn can resolve.
        return None
    laps_left = (laps_total - lap) if laps_total is not None else None
    if laps_left is not None and laps_left < MIN_LAPS_LEFT:
        # The window is spent. "15 litres light over 9 laps" said with two to
        # go describes a run that is eight-ninths over.
        return None
    if not _near_enough(rival.position, our_position):
        # A car six places away is not one he can attack, and "Attack" about a
        # car he cannot see is noise (§5.5).
        return None
    over_the_run = ((short.fraction / SAVEABLE_FRACTION)
                    * SAVING_COSTS_S_PER_LAP * short.laps_to_flag)
    if over_the_run < SAVING_WORTH_SAYING_S:
        return None
    who = rival.name or "He"
    brim = " He left on a full tank." if short.at_the_brim else ""
    whose = "" if rival.burn_per_lap_l else " on our burn"
    return Call(RIVAL_SHORT, lap,
                f"{who} is short to the flag. Attack.",
                f"{short.litres:.0f} litres light over {short.laps_to_flag} "
                f"laps{whose} - he lifts or he stops again.{brim}",
                MEDIUM, severity=over_the_run,
                tag=f"{RIVAL_SHORT}:{who}")


def _near_enough(theirs: int | None, ours: int | None) -> bool:
    """Whether a rival is close enough to be raced.

    Unknown on either side is `True`: the position is a convenience the board
    sometimes gives us, and refusing every call for want of it would silence
    the feature on the circuits where the leaderboard reads worst. Rule 3
    applies to the DATA - it is not stored as a place we do not have.
    """
    if theirs is None or ours is None:
        return True
    return abs(theirs - ours) <= NEARBY_PLACES


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
    # **Refused where it cannot be computed, rather than asserted.** With no
    # race length there is no shortfall and no way to tell a forced stop from a
    # lift - and this branch went on claiming the forced stop, which is
    # verbatim the defect the saving call was written to fix. `laps_total` is
    # `None` before the coordinator has a distance, and the pit wall starts at
    # arm, before the green.
    if short is None or short.saveable:
        return None
    who = rival.name or "He"
    return Call(RIVAL_COMMITTED, lap,
                f"{who} left on {out:.0f} litres.",
                f"That reaches lap {last}, so he has to stop again.", MEDIUM,
                # **Severity, so several forced stops rank by urgency.** With
                # none, they all tied at zero and the stable sort picked
                # whichever car's columns the sampler happened to catch first -
                # and a kind is said once, so the other was never said.
                severity=short.litres, tag=f"{RIVAL_COMMITTED}:{who}")

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
    if laps is None:
        reason = f"Over the last {count} laps."
    elif laps < 1.5:
        # "In about 1 laps" is what it said, and this is spoken aloud.
        reason = "On him next lap at that rate."
    else:
        reason = f"On him in about {laps:.0f} laps at that rate."
    return Call(CLOSING, lap,
                f"You are taking {rate:.1f} a lap out of {them}.",
                reason, MEDIUM)


def candidates(state) -> list:
    """Every rival call true this lap, for `calls.next_call` to rank.

    **All six, where four were reachable from nothing.** `rival_boxed`,
    `rejoin_call`, `closing_call` and `stay_out` were written, documented,
    ranked, registered and tested, and no production caller existed for any of
    them - `RIVAL_BOXED` in particular ranks ABOVE the two that were wired, on
    the stated argument that it is "the one that can still be acted on".

    Each asks for its own inputs and refuses without them, so a race with no
    board reader still gets `stay_out`, which needs no rival at all.
    """
    out = []
    lap = state.lap
    laps_left = (state.laps_total - lap) if state.laps_total else None

    for rival in (state.rivals or {}).values():
        if not isinstance(rival, Rival):
            continue
        out.append(short_to_the_flag(
            rival, state.fuel_per_lap_l,
            lap=lap, laps_total=state.laps_total,
            our_position=state.position))
        out.append(must_stop_by(
            rival, state.fuel_per_lap_l,
            lap=lap, laps_total=state.laps_total))

    # **He is in the box NOW**, which is the whole value of the call and the
    # reason it is fed by its own event rather than by the finished stop.
    entered = getattr(state, "rival_entered", None)
    if entered is not None:
        out.append(rival_boxed(
            Rival(name=entered.driver, pitted=True,
                  stop=Stop(lap=entered.lap, fuel_in_l=entered.fuel_in_l),
                  burn_per_lap_l=_burn_of(state, entered.driver)),
            lap=lap, laps_left=laps_left,
            burn_per_lap_l=state.fuel_per_lap_l,
            refuel_rate_lps=state.refuel_rate_lps,
            ours=state.our_stop))

    # **Only while a stop is actually the question.** `URGENCY` puts this
    # immediately below `BOX_SOON` because "the two answer the same question" -
    # so where nothing is asking it, answering is noise that outranks real
    # calls. Offered from lap 1 it said "Stay out. Too much fuel aboard to
    # fill." on the opening lap of every race, which is true, useless, and
    # displaced the cold-tyre warning that opens the race.
    if _a_stop_is_in_question(state):
        out.append(stay_out(
            lap=lap, laps_left=laps_left,
            burn_per_lap_l=state.fuel_per_lap_l,
            refuel_rate_lps=state.refuel_rate_lps,
            capacity_l=state.fuel_capacity_l,
            laps_total=state.laps_total,
            planned_stop_lap=state.stint_ends_on_lap))

    behind = getattr(state, "gap_behind", None)
    if behind is not None:
        out.append(rejoin_call(
            lap=lap, gap_behind_s=behind.latest(),
            litres_to_take=state.litres_to_take,
            refuel_rate_lps=state.refuel_rate_lps,
            pit_loss_s=state.pit_loss_s,
            pit_loss_source=state.pit_loss_source,
            who=state.gap_behind_name))
        out.append(closing_call(behind, lap=lap,
                                who=state.gap_behind_name,
                                laps_left=laps_left))
    ahead = getattr(state, "gap_ahead", None)
    if ahead is not None:
        out.append(closing_call(ahead, lap=lap,
                                who=state.gap_ahead_name,
                                laps_left=laps_left))

    out = [call for call in out if call is not None]
    # **The biggest opportunity first, because only one of them gets said.**
    # `next_call` sorts by kind and Python's sort is stable, so two rivals
    # would otherwise have been separated by the order they happened to stop
    # in - and a kind is said once, so the second is not said at all.
    out.sort(key=lambda c: -(c.severity or 0.0))
    return out


def _a_stop_is_in_question(state) -> bool:
    """Whether boxing is close enough to be worth arguing about.

    **Not `stop_pending`, which is true for the whole race.** It means "stops
    remain", not "a stop is imminent" - `_pending_stops() > 0` holds from the
    green - so gating on it gated on nothing, and "Stay out. Too much fuel
    aboard to fill." was said on lap 1 in place of the cold-tyre call that
    opens the race.

    The planned stop within a few laps, and nothing else. With no plan there
    is no stop in prospect for this to argue against.
    """
    planned = getattr(state, "stint_ends_on_lap", None)
    return planned is not None and state.lap >= planned - STAY_OUT_WINDOW


def _burn_of(state, driver: str | None) -> float | None:
    """His own burn where the book has it, from the rival already on file."""
    if not driver:
        return None
    known = (state.rivals or {}).get(driver)
    return getattr(known, "burn_per_lap_l", None)
