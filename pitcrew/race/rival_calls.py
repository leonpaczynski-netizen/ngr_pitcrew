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

from dataclasses import dataclass, replace

from pitcrew.race.calls import (
    CLOSING,
    HIGH,
    LOW,
    MEDIUM,
    REJOIN,
    RIVAL_BOXED,
    RIVAL_COMMITTED,
    RIVAL_SHORT,
    SECTOR_SPLIT,
    STAY_OUT_FUEL,
    TOW_TRADE,
    UNDERCUT,
    WEAR_STINT_LIMIT,
    Call,
    _crossing_the_line,
    _laps_after_this_stop,
    _tyre_word,
    fuel_to_flag_l,
    stop_still_needed,
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

# Beyond this many laps, "on him in about N laps" is not news about this race.
MAX_LAPS_TO_SAY = 15

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
                ours: Stop | None,
                capacity_l: float = TANK_L,
                entry_is_a_bound: bool = False) -> Call | None:
    """A rival has entered the pits. What it costs him, against what it costs us.

    Said once, on the lap he enters, because that is when the driver can still
    do something about it. The figure is his STANDING time, not a gap: he is
    stationary for as long as his fill takes and every second of it is a second
    we are driving.
    """
    if not rival.pitted or rival.stop is None:
        return None
    if entry_is_a_bound:
        # He was already standing when the watching began, so the lowest
        # reading is an UPPER bound on what he arrived with, not a reading of
        # it. Pricing it overstates the fill and therefore his standing time -
        # the mirror of the exit bound `fuel_shortfall` refuses.
        return None
    entered_on = rival.stop.fuel_in_l
    if entered_on is None or not refuel_rate_lps or refuel_rate_lps <= 0:
        return None
    needs = _fill_to_the_flag(laps_left, rival.burn_per_lap_l or burn_per_lap_l)
    if needs is None:
        return None
    # **A fill cannot exceed the tank.** Without this, any stop taken while the
    # remaining laps cost more than a tank - the whole first half of a long
    # race - priced a rival's fill at more than the car can hold: measured, a
    # lap-2 stop on a 20-lap race quoted him 44 seconds longer than us when the
    # true swing was zero. `fuel_shortfall` learned this in the commit before
    # and this call re-introduced it.
    needs = min(needs, capacity_l)
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
                    f"That is about {theirs:.0f} seconds standing{_whose(rival)}.",
                    MEDIUM, tag=f"{RIVAL_BOXED}:{who}")
    swing = theirs - mine
    if abs(swing) < WORTH_SAYING_S:
        return None
    who = rival.name or "He"
    if swing > 0:
        return Call(RIVAL_BOXED, lap,
                    f"{who} has boxed on {entered_on:.0f} litres.",
                    f"He stands {swing:.0f} seconds longer than you did"
                    f"{_whose(rival)}.", HIGH, tag=f"{RIVAL_BOXED}:{who}")
    return Call(RIVAL_BOXED, lap,
                f"{who} has boxed on {entered_on:.0f} litres.",
                f"He stands {-swing:.0f} seconds less than you did"
                f"{_whose(rival)}.", HIGH, tag=f"{RIVAL_BOXED}:{who}")


def _whose(rival: Rival) -> str:
    """Says the burn is ours when it is.

    `short_to_the_flag` says this out loud and this call did not, though it
    leans on the assumption harder: `_burn_of` can only find a rival's own burn
    after he has ALREADY completed a stop this race, so on his first stop -
    the common case - ours is always what is used (rules 4 and 5).
    """
    return "" if rival.burn_per_lap_l else ", on our burn"


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
                who: str | None = None,
                due: bool = True) -> Call | None:
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
    # **"Box now" only when a stop is actually due.** Three laps before the
    # planned stop at Deep Forest the call opened "Box now and the car behind
    # comes out in front" - an instruction-shaped sentence about a stop
    # nobody was taking, heard under a helmet as the box call. When the stop
    # is not due the same arithmetic is said as the conditional it is.
    if rejoin.ahead is False:
        return Call(REJOIN, lap,
                    (f"Box now and {them} comes out in front." if due
                     else f"A stop now puts you behind {them}."),
                    f"He is {rejoin.their_gap_s:.0f} seconds back and the stop "
                    f"costs {rejoin.ours_lost_s:.0f}.", HIGH if due else MEDIUM)
    if rejoin.too_close:
        return Call(REJOIN, lap,
                    ("Box now and it is too close to call." if due
                     else f"A stop now is too close to call against {them}."),
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
    # **Tagged per driver AND per side.** Untagged, one CLOSING call was said
    # and the other permanently swallowed for the stint - so "he is taking 1.5
    # a lap out of you" silenced "you are taking 1.4 a lap out of Rocky", which
    # are opposite pieces of news about two different cars.
    tag = f"{CLOSING}:{'behind' if behind else 'ahead'}:{them}"
    if behind:
        if not closing:
            return None          # he is dropping away: nothing to do about it
        return Call(CLOSING, lap,
                    f"{them} is taking {rate:.1f} seconds a lap out of you.",
                    f"Over the last {count} laps.", MEDIUM, tag=tag)
    if not closing:
        return Call(CLOSING, lap,
                    f"You are losing {-rate:.1f} seconds a lap to {them}.",
                    f"Over the last {count} laps.", MEDIUM, tag=tag)
    laps = trend.laps_to_catch(laps_left=laps_left)
    if laps is not None and laps_left is None and laps > MAX_LAPS_TO_SAY:
        # `laps_to_catch` clamps only when it knows the race length, and
        # `laps_total` is None until the coordinator has a distance - so with
        # no distance it said "on him in about 43 laps", which its own
        # docstring says is a figure not worth speaking.
        laps = None
    if laps is None:
        reason = f"Over the last {count} laps."
    elif laps < 1.5:
        # "In about 1 laps" is what it said, and this is spoken aloud.
        reason = "On him next lap at that rate."
    else:
        reason = f"On him in about {laps:.0f} laps at that rate."
    return Call(CLOSING, lap,
                f"You are taking {rate:.1f} seconds a lap out of {them}.",
                reason, MEDIUM, tag=tag)


# --------------------------------------------------- where he has us

# Held up: the car ahead inside `HELD_UP_GAP_S` (from `race/tow.py`, so the
# trade and the undercut agree about what "held up" is) on this many
# consecutive laps. A second and a half is a car length or two at racing
# speed on a 90 s lap - inside it the gap reads as traffic, not as pace.
from pitcrew.race.tow import HELD_UP_GAP_S  # noqa: E402

HELD_UP_LAPS = 3


def _sector_names(numbers) -> str:
    words = [str(n + 1) for n in numbers]
    if len(words) <= 1:
        return "".join(words)
    return ", ".join(words[:-1]) + " and " + words[-1]


def _split(state):
    """`(gains, losses, laps)` from the sector map, or None without evidence.

    Gains are sectors where the gap to him SHRINKS outside its own noise;
    losses where it grows. Both are `Bin`s. `None` until the map has the
    laps and the cuts to say anything.
    """
    sector_map = getattr(state, "sector_map", None)
    cuts = getattr(state, "sector_cuts_m", None)
    if sector_map is None or not cuts:
        return None
    try:
        sectors = sector_map.sectors(cuts)
    except Exception:
        return None
    said = [s for s in sectors if s.worth_saying]
    if not said:
        return None
    gains = [s for s in said if s.gaining]
    losses = [s for s in said if not s.gaining]
    return gains, losses, max(s.laps for s in said)


def sector_split_call(state) -> Call | None:
    """Where round the lap we take time out of him, and where he takes it back.

    A FACT, once a stint per rival: the HUD shows one gap, and never which
    stretch of road it moved on. Deep Forest, 6 Sep 2026: seven laps behind
    P2, quicker through the first two sectors every lap and losing it all
    back in the third, and the wall read the gap on 154 frames and said
    nothing about where.
    """
    if state.in_pit or state.finished:
        return None
    trend = _snapshot(getattr(state, "gap_ahead", None))
    if trend is None or trend.latest() is None:
        return None
    split = _split(state)
    if split is None:
        return None
    gains, losses, laps = split
    them = state.gap_ahead_name or "the car ahead"
    tag = f"{SECTOR_SPLIT}:{them}"
    if tag in state.said_tags:
        return None
    if gains and losses:
        call = (f"Faster than {them} through {_sector_names(g.index for g in gains)}. "
                f"He has you in {_sector_names(l.index for l in losses)}.")
        reason = (f"Over {laps} laps: {sum(-g.mean_s for g in gains):.1f} a lap "
                  f"through {_sector_names(g.index for g in gains)}, "
                  f"{sum(l.mean_s for l in losses):.1f} back in "
                  f"{_sector_names(l.index for l in losses)}.")
    elif gains:
        call = f"Faster than {them} through {_sector_names(g.index for g in gains)}."
        reason = f"Over {laps} laps."
    else:
        call = f"{them} has you in {_sector_names(l.index for l in losses)}."
        reason = f"Over {laps} laps."
    return Call(SECTOR_SPLIT, state.lap, call, reason, MEDIUM, tag=tag)


def _a_fill_is_still_to_come(state) -> bool:
    """Whether a litre saved now still buys standing time at a pump.

    **The whole value of the tow's fuel saving is the fill it shortens**, and
    `race/tow.py` says so in its own second paragraph: *"After the stop a
    saved litre is worth nothing at all: the fill is already in."* So the
    trade is only sayable while a fill remains.

    Two things have to hold, and they are different claims. A stop has to be
    left in the plan - `stint_ends_on_lap` is `None` on the last stint,
    which is exactly "no stop at the end of this one". And the stop has to
    still be a stop: `stop_still_needed` is the one expression this codebase
    uses for that, grant and arithmetic together (rule 12).
    """
    if state.finished:
        return False
    if state.stint_ends_on_lap is None:
        return False
    return stop_still_needed(state)


def tow_trade_call(state) -> Call | None:
    """What sitting in his wake is worth, and what it costs.

    **Once a race per car ahead**, not once a stint: the tag carries his
    name and `clear_stint` does not empty `said_tags`. A verdict given in
    stint one about a car he is still behind in stint two is not revised,
    which is a limit and not a feature - carried in the plan.

    The driver's question, 7 Sep 2026: *"was the fuel saving worth the lost
    lap time or not - that's what George needs to calculate in real time."*
    A fact with a verdict in it, because the arithmetic has one answer: a
    litre saved before the stop is worth its standing time at the pump, and
    a second given away in his wake is gone. See `race/tow.py`.

    **The verdict is silent once the last fill is in** (critic pass 6).
    `clear_stint` empties `said` at PIT_EXIT and `_weigh_the_tow` remakes the
    trade at every crossing, so a new car ahead after the last stop was
    hearing *"Worth it - stay in it"* about a saving `tow.py` itself prices at
    nothing. A verdict struck from half an argument is worse under a helmet
    than no verdict at all.

    **But he is not left with nothing** (critic pass 7, and it checked).
    `CHASE` needs `laps_left <= CHASE_LAPS` and speaks a different quantity -
    the gap and the delta needed - and `closing_call` needs a rate outside
    `TREND_WORTH_SAYING_S`, which a driver sitting at a steady gap in a wake
    is by definition inside. So neither says anything about the second a lap
    he is giving away, and an earlier draft of this docstring claimed they
    did. What is said instead, once, is the thing that actually CHANGED at
    the stop: a driver who was told to stay in the tow is still in it for a
    reason that no longer exists.
    """
    if state.in_pit or state.finished:
        return None
    them = state.gap_ahead_name or "the car ahead"
    trade = getattr(state, "tow_trade", None)
    if not _a_fill_is_still_to_come(state):
        return _tow_is_spent(state, them, trade)
    if trade is None:
        return None
    tag = f"{TOW_TRADE}:{them}"
    if tag in state.said_tags:
        return None
    call, reason = trade.sentence(them)
    return Call(TOW_TRADE, state.lap, call, reason, MEDIUM, tag=tag)


def _tow_is_spent(state, them: str, trade) -> Call | None:
    """The one thing left to say about a tow once no fill is coming. Once.

    **"The fill's in" was true in only one of the three ways this is
    reached** (critic pass 7, fourth round). `_a_fill_is_still_to_come`
    refuses on the flag, on the last stint, and on `stop_still_needed` -
    and that last one goes false with NO stop taken whenever `_stops_off`
    fires. So a driver on a fuel-bound plan who has just heard *"You're
    fuelled to the flag"* was then told *"the fill's in"* about a stop he
    never made, which under a helmet reads as the app believing he has
    pitted. The conclusion was right and the stated fact was false: rule 12,
    the reason has to come from the branch that produced the decision. It
    does now - `last_stop_lap` is set by `clear_stint` and is the one record
    of a stop having actually happened.

    **Said only where he was told, in those words, to stay in it** - the
    verdict spoken has to have been `True`, not merely "not False" (critic
    pass 7). `worth_it` is also `None` when there is no refuel rate on file,
    and `record()` files that `None` here: gated on "not False" the app first
    said *"no refuel rate on file to price it"* and then, four laps later,
    *"The saving was worth its standing time at the pump"* - asserting the
    price it had just refused to name. A wash is the same shape and is
    likewise not an instruction to stay.

    **And it has to be about the car he was told about.** The verdict is
    filed with its subject, because a driver told to stay behind Boxhead who
    stops and comes out behind Rocket would otherwise hear the withdrawal of
    an instruction he was never given, about a car he has never been told
    anything about. `GapTrend` clears on a subject change so the FIGURE would
    have been right; the premise would not.

    The tag carries no driver name and the whole race is its scope. This is
    not a fact about a rival, it is a fact about our own fuel, and it is true
    exactly once - `clear_stint` must not let it round again.
    """
    if trade is None or state.tow_said_worth_it is not True:
        return None
    # **`is not None and != them` was the hole this guard was written to
    # close** (critic pass 7, third round). `gap_ahead_name` is None whenever
    # the board cannot name the car ahead - the top-8 truncation does that
    # routinely - so a None subject passed for every rival, which is the
    # docstring's own example still live. The verdict has to name a car, and
    # it has to be this one.
    if state.tow_said_about is None or state.tow_said_about != them:
        return None
    tag = "tow-spent"
    if tag in state.said_tags:
        return None
    lost = getattr(trade, "losing_s_per_lap", None)
    # **A tenth is the floor, not zero.** `worth_it is True` needs the loss
    # to sit `WASH_S` under the saving, so a loss of 0.04 s a lap is exactly
    # the reachable case - and `:.1f` prints it "0.0", which is a measurement
    # rendered as nothing (rule 9's shape). Below a tenth there is no lap
    # time being given away worth a sentence.
    if lost is None or lost < 0.1:
        return None
    if state.last_stop_lap is not None:
        why, reason = ("the fill's in",
                       "The saving was worth its standing time at the pump, "
                       "and there is no pump left.")
    else:
        why, reason = ("there's no stop to save it for",
                       "The saving was only ever worth its standing time at "
                       "the pump, and you are not stopping.")
    return Call(TOW_TRADE, state.lap,
                f"No fuel left to save in the tow - {why}. "
                f"Behind {them} you're {lost:.1f} seconds a lap slower.",
                reason, MEDIUM, tag=tag)


def _held_up(trend, lap: int) -> bool:
    """Inside `HELD_UP_GAP_S` on the last `HELD_UP_LAPS` consecutive laps."""
    seen = getattr(trend, "seen", None) or {}
    if not seen:
        return False
    newest = max(seen)
    if newest < lap - 1:
        return False                    # the wall has not read this lap
    laps = [newest - i for i in range(HELD_UP_LAPS)]
    if any(l not in seen for l in laps):
        return False
    return all(0 < seen[l] <= HELD_UP_GAP_S for l in laps)


def undercut_call(state) -> Call | None:
    """Box now for clear air, on the first lap the tank holds fuel to the flag.

    **The traffic undercut, and it is the driver's own acceptance test for
    this engineer** (7 Sep 2026): held up behind a car he is faster than
    through two sectors of three, with the stop still to come, George is to
    pit him as soon as enough fuel to finish fits in the tank. Every term of
    it is read, not assumed:

    * held up - the gap inside `HELD_UP_GAP_S` for `HELD_UP_LAPS` laps;
    * faster - a sector where the gap to him shrinks outside its own noise;
    * he has not stopped - a rival with a stop on file is a different race;
    * a stop is still owed and it is the LAST one, so the fill is to the flag
      and `_laps_the_fill_covers` already says so;
    * the tank holds it - `fuel_to_flag_l` is None while it does not;
    * the tyres reach the flag on the briefed rate, or the call says they
      are unchecked and goes out LOW;
    * **and the tow is not worth more than the traffic costs** - where the
      trade says stay in it, there is no undercut to call. Where it says get
      out, the call carries the two figures.

    **Why now costs nothing.** The fill is the flag's laps times the burn
    less what is aboard, and both fall by one lap's burn per lap - so the
    litres, and the seconds standing, are the same on every lap from this
    one to the planned box. Waiting buys nothing and keeps him in the
    traffic. The tyre undercut CLAUDE.md 5.4 calls weak is not part of the
    argument and is not claimed.
    """
    if state.in_pit or state.finished or _crossing_the_line(state):
        return None
    if UNDERCUT in state.said:
        return None
    trend = _snapshot(getattr(state, "gap_ahead", None))
    if trend is None or not _held_up(trend, state.lap):
        return None
    them = state.gap_ahead_name or "the car ahead"
    rival = (state.rivals or {}).get(them)
    if rival is not None and getattr(rival, "stop", None) is not None:
        return None
    split = _split(state)
    if split is None or not split[0]:
        return None                     # no measured sector where we gain
    gains = split[0]
    if state.stint_ends_on_lap is None or state.lap >= state.stint_ends_on_lap:
        return None                     # no stop ahead, or it is due: BOX_NOW
    if state.further_stop_planned is not False:
        return None                     # only the last stop fills to the flag
    if not stop_still_needed(state):
        return None
    # **Read only below the three guards above**, which between them are
    # `_a_fill_is_still_to_come` and then some: a stop ahead, it is the last
    # one, and it is still a stop. So `worth_it` is never consulted here
    # after the fill is in, which is the window in which it means anything.
    trade = getattr(state, "tow_trade", None)
    if trade is not None and trade.worth_it is True:
        return None                     # the tow pays: stay in it
    litres = fuel_to_flag_l(state)
    if litres is None:
        return None                     # the tank cannot hold the flag yet
    laps_after = _laps_after_this_stop(state)
    rate = state.wear_per_lap or state.briefed_wear_per_lap
    confidence = MEDIUM
    tyres = ""
    if rate and laps_after is not None and state.next_tyres is not None:
        # **The set that reaches the flag is the one he leaves the box on.**
        # A fuel-only stop (Ludo's Deep Forest instruction) keeps the laps
        # already on the rubber; critic pass 5 built the call that boxed him
        # for fuel only onto a set at 95% at the flag.
        on_the_set = laps_after + (0 if state.next_tyres
                                   else max(0, state.laps_since_stop or 0))
        if on_the_set * rate > WEAR_STINT_LIMIT:
            return None                 # the set will not reach the flag
    else:
        confidence = LOW
        tyres = " Tyre life to the flag unchecked."
    tow = ""
    if trade is not None and trade.worth_it is False:
        # **`max(0.0, ...)` here was CLAUDE.md rule 9** (critic pass 7): a
        # saving that came out negative is the tow COSTING fuel, and printing
        # it as "0.0 seconds at the stop" is a measurement clamped into a
        # confident wrong number. Say what it is instead.
        saved = trade.saving_s_per_lap
        tow = ((f" The tow's {saved:.1f} seconds at the stop against "
                f"{trade.losing_s_per_lap:.1f} seconds a lap lost.")
               if saved is not None and saved > 0 else
               (f" No fuel saving in the tow, and "
                f"{trade.losing_s_per_lap:.1f} seconds a lap lost."))
    reason = (f"Undercut on {them}: you're held up, and faster through "
              f"{_sector_names(g.index for g in gains)}. The fill costs the "
              f"same now as on lap {state.stint_ends_on_lap}.{tow}{tyres}")
    # The same tyre word every box instruction carries (rule 13): "No
    # tyres." / "RS on." - the driver decides in the box on it.
    return Call(UNDERCUT, state.lap,
                f"Box this lap.{_tyre_word(state)} Fuel to the flag.",
                reason, confidence, tag=f"{UNDERCUT}:{them}")


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
    # **The one expression** (rule 12): `laps_remaining` corrects for a
    # crossing that went missing in the pit lane; `laps_total - lap` did
    # not, and read a lap long on every pit lap at Monza.
    laps_left = state.laps_remaining()

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
    # reason it is fed by its own event rather than by the finished stop. The
    # queue is DRAINED here: an entry is news for one crossing, and left in
    # place it was re-spoken after our own stop reset `said`, five laps later,
    # with a swing computed against a tank that had changed underneath it.
    entering = list(getattr(state, "rivals_entering", None) or ())
    if entering:
        state.rivals_entering = []
    for entered in entering:
        out.append(rival_boxed(
            Rival(name=entered.driver, pitted=True,
                  stop=Stop(lap=entered.lap, fuel_in_l=entered.fuel_in_l),
                  burn_per_lap_l=_burn_of(state, entered.driver)),
            lap=lap, laps_left=laps_left,
            burn_per_lap_l=state.fuel_per_lap_l,
            refuel_rate_lps=state.refuel_rate_lps,
            ours=state.our_stop,
            capacity_l=state.fuel_capacity_l or TANK_L,
            entry_is_a_bound=bool(getattr(entered, "partial", False))))

    # **Only while a stop is actually the question.** `URGENCY` puts this
    # immediately below `BOX_SOON` because "the two answer the same question" -
    # so where nothing is asking it, answering is noise that outranks real
    # calls. Offered from lap 1 it said "Stay out. Too much fuel aboard to
    # fill." on the opening lap of every race, which is true, useless, and
    # displaced the cold-tyre warning that opens the race.
    out.append(sector_split_call(state))
    out.append(tow_trade_call(state))
    out.append(undercut_call(state))

    if _a_stop_is_in_question(state):
        out.append(stay_out(
            lap=lap, laps_left=laps_left,
            burn_per_lap_l=state.fuel_per_lap_l,
            refuel_rate_lps=state.refuel_rate_lps,
            capacity_l=state.fuel_capacity_l,
            laps_total=state.laps_total,
            planned_stop_lap=state.stint_ends_on_lap))

    behind = _snapshot(getattr(state, "gap_behind", None))
    if behind is not None:
        # **Gated like `stay_out`, and for the same reason.** It answers "if I
        # box now, does he come out ahead?", which is only asked when a stop is
        # in prospect - and it carries no tag, so said once on lap 1 against a
        # nine-second gap it was suppressed for the rest of the stint and
        # silent on the lap it exists for. Its own module calls it "the call,
        # and it dominates everything else here".
        if _a_stop_is_in_question(state):
            to_stop = state.laps_to_stop()
            out.append(rejoin_call(
                lap=lap, gap_behind_s=behind.latest(),
                litres_to_take=_fill_at_the_stop(state),
                refuel_rate_lps=state.refuel_rate_lps,
                pit_loss_s=state.pit_loss_s,
                pit_loss_source=state.pit_loss_source,
                who=state.gap_behind_name,
                due=(to_stop is not None and to_stop <= 1)))
        out.append(closing_call(behind, lap=lap,
                                who=state.gap_behind_name,
                                laps_left=laps_left))
    ahead = _snapshot(getattr(state, "gap_ahead", None))
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


def _snapshot(trend):
    """A private copy of a gap trend, taken before it is read.

    **The live object is written on the sampler thread.** `note()` clears
    `seen` outright when the subject changes - an overtake, or the car ahead
    pitting, which is precisely when these calls fire - and
    `closing_s_per_lap` takes the keys and then re-indexes them, so a clear in
    between raises `KeyError` inside a Qt slot with nothing catching it.
    Reproduced. `PitWall.positions()` has a docstring about this exact hazard
    and snapshots; handing the raw object across was the same defect one layer
    up.
    """
    if trend is None:
        return None
    try:
        return replace(trend, seen=dict(trend.seen))
    except Exception:                        # pragma: no cover - belt
        return None


def _fill_at_the_stop(state) -> float | None:
    """The litres that actually go through the hose, or `None`.

    **`next_stint_load_l` is what the car STARTS the next stint on**, not what
    it takes on: the fill is that minus whatever is aboard when we arrive.
    Priced as a fill it overstated the stop - measured, 88 L quoted a 108 s
    stop against a true 100 s - and `REJOIN_MARGIN_S` is three seconds, so an
    eight-second error flips the verdict for any car in that window. That is
    the very error `stop_costs_s`'s docstring was written about.

    `None` rather than a guess where either half is missing, and `None` rather
    than a clamp where the arithmetic comes out negative: a car that arrives
    with more than the next stint needs is not one that takes zero litres, it
    is one this arithmetic does not describe (rule 9).
    """
    load = getattr(state, "next_stint_load_l", None)
    aboard = getattr(state, "fuel_l", None)
    if load is None or aboard is None:
        return None
    fill = load - aboard
    return fill if fill >= 0 else None


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
