"""What the engineer says, and when.

CLAUDE.md §5.5 is the spec, and it is unusually strict about form because the
driver hears this under a helmet at racing speed:

    "Box this lap or next. Fuel is the constraint - you're 1.2 laps short."

One thing at a time. The instruction first, the reason second and short. Not a
table, not three options. If the app is not confident it says so **inside the
call**, because "unconfirmed" is a word the driver can act on.

So this module returns **at most one call per lap** — the most urgent thing
true right now. A second call would arrive while he is still processing the
first, and two instructions at once is the same as none.
"""
from __future__ import annotations

from dataclasses import dataclass, field



# Confidence travels with every call so a guess never sounds like a reading.
HIGH = "high"
MEDIUM = "medium"
LOW = "low"

# Kinds, ordered by urgency. The first match wins the lap.
BOX_NOW = "box-now"
BOX_SOON = "box-soon"
FUEL_SHORT = "fuel-short"
FUEL_LONG = "fuel-long"
TYRE = "tyre"
TYRE_TEMP = "tyre-temp"
STATUS = "status"
GREEN = "green"
STAY_OUT = "stay-out"
CHEQUER = "chequer"

# **The chequered flag outranks everything.** It used to sit second from
# last, below the box call - and on the night that mattered, "Box this lap.
# RS. Fuel to 27 litres." was voiced on the driver's chequered-flag crossing
# of a race he had just finished without stopping. The flag is the one call
# that is true exactly once and never again; nothing said instead of it can
# be more urgent.
URGENCY = (CHEQUER, BOX_NOW, FUEL_SHORT, BOX_SOON, TYRE, FUEL_LONG,
           TYRE_TEMP, GREEN, STATUS)

# A status call every few laps, so silence means "nothing to report" rather
# than "the app has died".
STATUS_EVERY_LAPS = 5

# Fuel margin below which the plan no longer reaches the stop.
FUEL_SHORT_LAPS = 0.5
# Fuel surplus above which he is carrying a lap he does not need.
FUEL_LONG_LAPS = 1.5

# How many laps a box call goes unanswered before the engineer stops
# repeating it and re-reads the race in the light of what the driver is
# actually doing. The driver's action is primary evidence: nine identical
# "Box this lap" calls were once voiced to a driver executing a perfectly
# feasible zero-stop, the last of them on his chequered-flag crossing.
BOX_IGNORED_LAPS = 2
# The fuel gap to the flag, in laps, inside which staying out is a plan
# rather than a gamble when the car has NO measured short-shift slope. With
# a measured slope there is no constant floor at all: the gate is
# `short_shift_for`'s own arithmetic - the fold happens only when the lever,
# within its rpm cap, actually closes the gap. A -1.5 floor used to stand in
# for that and it overcommitted: at 800 rpm of cap the lever could leave
# 0.7 laps uncovered and the fold still said "you can make it".
STAY_OUT_GAP_UNMEASURED = -0.5
# What `short_shift_for` may report still-short after the drop and the fold
# still claim the flag - the same epsilon below which the fuel call does not
# bother voicing a residue.
STAY_OUT_STILL_SHORT = 0.05

# --- tyre temperature, the one tyre channel GT7 actually broadcasts ---
#
# Everything here is measured: the temperatures are per-lap frame means and
# the window they are judged against is measured from this event's own laps
# (`race/temps.py`) - never the fabricated real-world band the strategy layer
# still carries with `windowMeasured: false`. No window on file means the
# comparison is not made, not that a default is invented.

# More than this below the measured window floor at the green is worth a
# warning; less is a normal out-of-the-garage state not worth a word.
TEMP_COLD_BELOW_C = 10.0
# Both axles still climbing by at least this much per lap reads as "cold at
# the green" even with no window on file - the relative form of the same call.
TEMP_RISING_C = 4.0
# An axle this far above its own steady mean, for this many consecutive laps,
# is a departure worth calling. The baseline is each axle against ITSELF:
# on some cars the rears run 8-11 degC hotter than the fronts all race, and
# that offset is the car's normal, never a finding.
TEMP_TREND_C = 5.0
TEMP_TREND_LAPS = 2
# A set's first laps are warm-up (about two on the measured cars), so its
# baseline starts after them. **Counted from the start of the history, not
# from the race lap number**: the history is cleared on a tyre change, and a
# filter on the absolute lap once let a fresh set fitted on lap 10 put its
# own cold laps into its baseline - after which its normal steady
# temperature read as "heating" in every race with a stop.
TEMP_WARMUP_LAPS = 2
TEMP_BASELINE_MIN_LAPS = 3

# How much worse a thing has to get before it is worth saying twice, in the
# units of the call itself. The docstring on `next_call` has always promised
# re-issue "unless it has become more urgent" and nothing implemented it: a
# shortfall warned at 3.8 laps was met with silence at 4.9, 5.9 and 7.0. These
# are the stated thresholds that promise now rests on - large enough that a
# drifting number does not chatter, small enough that a lap of fuel going
# missing is always spoken.
WORSE_BY = {
    FUEL_SHORT: 0.5,     # half a lap further short
    FUEL_LONG: 1.0,      # another lap in hand
    TYRE: 0.10,          # ten more points of modelled life gone
    BOX_NOW: 1.0,        # another lap overdue at the stop
    BOX_SOON: 1.0,       # a lap closer to it
}


@dataclass(frozen=True)
class Call:
    """One thing said, with why and how sure."""
    kind: str
    lap: int
    call: str
    reason: str
    confidence: str = HIGH
    # What the call was made *at*, in its own units, with larger meaning
    # worse. Not exported and never spoken: it exists so the same call can be
    # made again when the thing it was about has deteriorated.
    severity: float | None = None
    # Which occasion of a many-occasion kind this is. The tyre-temperature
    # kind has three distinct things it can say - cold, in window, trending -
    # and each is said at most once per stint; suppressing by kind alone
    # would let the first swallow the other two. Recorded by
    # `RaceState.record`, never spoken or exported.
    tag: str | None = None

    def spoken(self) -> str:
        """Instruction, then reason. Confidence only when it is not high."""
        text = self.call
        if self.reason:
            text = f"{text} {self.reason}"
        if self.confidence == LOW:
            text = f"{text} Unconfirmed."
        return text

    def as_export(self) -> dict:
        return {
            "lap": self.lap,
            "call": self.call,
            "reason": self.reason,
            "confidence": self.confidence,
        }


@dataclass
class RaceState:
    """What is true right now, as far as the app can tell."""
    lap: int = 0                       # laps completed
    laps_total: int | None = None
    # Set when the race runs to the clock rather than to a distance. The lap
    # count is then a **derived** figure - the distance the approved plan
    # expects to cover - and every remaining-laps number said out loud is an
    # estimate, so the calls say "about". `events.race_laps` holds the minutes
    # for a timed race, which is how a 45-minute Monza came to be raced as a
    # 45-lap one: "40 to go" with 19 left, and a fuel shortfall to match.
    race_minutes: float | None = None
    fuel_l: float | None = None
    fuel_per_lap_l: float | None = None
    # What the tank actually holds. Without it the engineer will ask for a
    # fuel figure the car cannot take - and it did: "Fuel to 510 litres."
    fuel_capacity_l: float | None = None
    position: int | None = None
    in_pit: bool = False
    finished: bool = False
    # Stint accounting against the approved plan.
    stint_index: int = 0
    stint_ends_on_lap: int | None = None
    next_compound: str | None = None
    # How long the stint *after* the next stop is. The fill at that stop is
    # for that stint and not for the rest of the race: fuelling to the flag at
    # stop 1 of a two-stop asks for a tankful nobody needs, and where the tank
    # cannot hold it the call became a shortfall that does not exist.
    next_stint_laps: int | None = None
    # Whether the plan holds a further stop *after* the next one. None is
    # "nobody said" - the state was built by hand, as the tests do - and then
    # the fill is taken at its word. False is a positive claim, and it matters
    # when the plan has gone stale: with no stop after the next stint, that
    # stint runs to the flag, so a fill sized to a stint shorter than the
    # laps actually remaining would send him back out to run dry.
    further_stop_planned: bool | None = None
    wear_per_lap: float | None = None
    # **What a short-shift is worth on this car, in litres per lap per 1000
    # rpm.** Measured by `tools/shortshift_trade.py` from laps where his own
    # upshift rpm varied: 1.762 on the Porsche at Monza, 95% CI [0.92, 2.60],
    # over 69 laps across 5 sessions. None for a car nobody has measured, and
    # then the fuel call names the lever without a number rather than
    # inventing a conversion.
    short_shift_l_per_1000rpm: float | None = None
    # How far the beep may be dropped before the answer stops being "save
    # fuel" and starts being "box". Beyond this the lap-time cost is well
    # outside anything the fit bounds, and short-shifting out of the
    # powerband is not fuel saving.
    short_shift_max_drop_rpm: float = 800.0
    laps_since_stop: int = 0
    # A stop was made and nothing said whether the tyres came off. The wear
    # model keeps counting through it - GT7 lets you take fuel without taking
    # tyres - and the call that rests on it says so out loud.
    tyre_change_unconfirmed: bool = False
    # --- tyre temperature, per-lap frame means fed by the coordinator ---
    # The measured working window per axle, (floor, ceiling) in degC, from
    # this event's own practice laps. None where nobody has measured one -
    # never a default band, and never the strategy layer's fabricated
    # real-world figures.
    temp_window_front: tuple[float, float] | None = None
    temp_window_rear: tuple[float, float] | None = None
    # Measured laps from stone cold to the window, or None where no practice
    # session started cold enough to show it. Spoken in the cold-tyre call
    # when present; the call carries no number otherwise.
    temp_laps_to_window: int | None = None
    # (lap, front mean, rear mean) per completed lap that carried temps.
    # Cleared on a tyre change - a new set's baseline is its own.
    temp_history: list[tuple[int, float, float]] = field(default_factory=list)
    # Which tyre-temp occasions were said this stint: "cold", "in-window",
    # "trend-front", "trend-rear". Each is said at most once per stint.
    temp_said: set[str] = field(default_factory=set)
    said: list[str] = field(default_factory=list)
    # What each kind was last said at, so a call can be made again when it has
    # got worse. Kept beside `said` rather than inside it because `said` is
    # read as a plain list of kinds in half a dozen places.
    said_at: dict[str, float] = field(default_factory=dict)

    def laps_remaining(self) -> int | None:
        if self.laps_total is None:
            return None
        return max(0, self.laps_total - self.lap)

    def laps_of_fuel(self) -> float | None:
        """How many more laps the fuel on board covers."""
        if self.fuel_l is None or not self.fuel_per_lap_l:
            return None
        return self.fuel_l / self.fuel_per_lap_l

    def laps_to_stop(self) -> int | None:
        """Laps still to run before the planned stop. **Never negative.**

        A stop cannot be fewer than no laps away, and the negative this used
        to return was read straight into the fuel gap as surplus: every lap
        run past the box lap *added* to the fuel reported in hand. "You can
        push. 2.9 laps of fuel in hand." was spoken at high confidence with
        0.88 laps aboard.
        """
        if self.stint_ends_on_lap is None:
            return None
        return max(0, self.stint_ends_on_lap - self.lap)

    @property
    def past_box_lap(self) -> bool:
        """The planned stop has come and it has not been taken."""
        return (self.stint_ends_on_lap is not None
                and self.lap >= self.stint_ends_on_lap)

    def note_temps(self, lap: int, front_c: float, rear_c: float) -> None:
        """One completed lap's measured axle means, in order driven."""
        self.temp_history.append((lap, front_c, rear_c))

    def record(self, call: Call) -> None:
        """Remember a call was made, and how bad it was when it was."""
        if call.kind not in self.said:
            self.said.append(call.kind)
        if call.severity is not None:
            self.said_at[call.kind] = call.severity
        if call.kind == TYRE_TEMP and call.tag:
            self.temp_said.add(call.tag)


def _fuel_target(state: RaceState) -> float | None:
    """Laps that have to be covered on the fuel now aboard.

    The stop when there is one still to come, the flag when there is not.
    **Flooring `laps_to_stop` at zero is not enough on its own**: at a target
    of zero the gap becomes the whole tank and the "you can push" call fires
    harder than ever. Once the box lap has gone by, the honest target is the
    rest of the race - he is running on this fuel until he actually stops.
    """
    if state.past_box_lap:
        return state.laps_remaining()
    to_stop = state.laps_to_stop()
    return state.laps_remaining() if to_stop is None else to_stop


def _fuel_gap(state: RaceState) -> float | None:
    """Laps of fuel minus laps still to run before the stop.

    Negative means short. This is the number the driver acts on, so it is
    computed once and reused rather than re-derived per call.
    """
    onboard = state.laps_of_fuel()
    if onboard is None:
        return None
    target = _fuel_target(state)
    if target is None:
        return None
    return onboard - target


def next_call(state: RaceState) -> Call | None:
    """The single most urgent thing true this lap, or nothing.

    Silence is a valid answer and the common one. A call repeated every lap
    stops being information, so anything already said this stint is suppressed
    unless it has become more urgent.
    """
    candidates = [c for c in _candidates(state) if c is not None]
    if not candidates:
        return None
    candidates.sort(key=lambda c: URGENCY.index(c.kind))
    for call in candidates:
        if _worth_saying_again(state, call):
            return call
    return None


def _worth_saying_again(state: RaceState, call: Call) -> bool:
    """Whether a call already made this stint should be made again.

    Only on a **stated deterioration**, in the units of the call itself: a
    repeated call stops being information, but silence while a shortfall
    doubles is worse - the driver reads silence as "nothing has changed",
    which is exactly what `_status` promises it means.
    """
    if call.kind not in state.said:
        return True
    if call.kind == STATUS:
        # `STATUS_EVERY_LAPS` is already this call's rate limiter. Suppressing
        # it as well meant the reassuring call could only ever be made once,
        # on lap 5, and never again for the rest of the race.
        return True
    if call.kind == TYRE_TEMP:
        # Rate-limited per occasion by `temp_said`, which `_tyre_temp` checks
        # itself: suppressing on the kind would let the cold warning at the
        # green swallow the in-window confirmation it promised.
        return True
    margin = WORSE_BY.get(call.kind)
    was = state.said_at.get(call.kind)
    if margin is None or call.severity is None or was is None:
        return False
    return call.severity >= was + margin


def _candidates(state: RaceState) -> list[Call | None]:
    return [
        _chequer(state),
        _green(state),
        _box_now(state),
        _box_soon(state),
        _fuel(state),
        _tyre(state),
        _tyre_temp(state),
        _status(state),
    ]


def _crossing_the_line(state: RaceState) -> bool:
    """The race's distance is covered but the finish event has not landed yet.

    LAP_COMPLETED for the final lap arrives before RACE_FINISHED - they are
    produced by the same packet, in that order - and in that gap the box call
    used to win the lap: "Box this lap. RS. Fuel to 27 litres." was voiced on
    the driver's chequered-flag crossing. Nothing about a stop, fuel or
    status is actionable on a lap that no longer exists, so every such call
    stands down here and the flag settles it. For a timed race the distance
    is the plan's own estimate, so the honest behaviour in the gap is
    silence, not a premature flag.
    """
    return state.laps_remaining() == 0 and not state.finished


def _green(state: RaceState) -> Call | None:
    if state.lap != 0 or state.finished:
        return None
    laps = f"{state.laps_total} laps." if state.laps_total else ""
    return Call(GREEN, 0, "Green, green, green.", laps)


def _chequer(state: RaceState) -> Call | None:
    """Position and one closing fact. The last words of the race should say
    what the race was, not what the plan wanted."""
    if not state.finished:
        return None
    parts = []
    if state.position:
        parts.append(f"P{state.position}.")
    if state.fuel_l is not None:
        fact = f"Fuel {state.fuel_l:.1f} litres"
        if state.stint_index == 0 and state.lap > 0:
            # No stop was ever taken - the stint pointer only moves on one.
            fact += " - zero-stop made it"
        parts.append(fact + ".")
    return Call(CHEQUER, state.lap, "Chequered flag.", " ".join(parts))


def _box_now(state: RaceState) -> Call | None:
    to_stop = state.laps_to_stop()
    if to_stop is None or state.in_pit or state.finished:
        return None
    if to_stop > 0 or _crossing_the_line(state):
        return None

    fuel = _fuel_instruction(state)
    compound = f" {state.next_compound}." if state.next_compound else ""
    # `to_stop` is not None here, so neither is the lap it came from.
    overdue = state.lap - (state.stint_ends_on_lap or 0)
    if overdue > 0:
        # **Never the same sentence twice.** The deterioration threshold
        # re-fires this call every lap once a planned stop is skipped -
        # severity is laps overdue and grows by exactly one - and it used to
        # re-fire *verbatim*, nine laps running. A repeat has to carry the
        # new fact: how overdue, and where the fuel stands against the flag.
        # (Past the box lap `_fuel_gap` is measured against the flag, which
        # is the frame he is actually racing in.)
        gap = _fuel_gap(state)
        laps_word = "lap" if overdue == 1 else "laps"
        reason = f"{overdue} {laps_word} overdue."
        confidence = HIGH
        if gap is not None and gap < 0:
            # This used to say "You will not make the flag." off a constant
            # floor - an unhedged claim about the future, and the measured
            # driver closed 0.7 laps with lift-and-coast alone on the very
            # night it was written for. The FUEL_SHORT register instead:
            # the measured gap, its frame, and his lever - hedged, because
            # "on current burn" is a projection, not a reading.
            reason += (f" You're {abs(gap):.1f} laps short of the flag on "
                       "current burn - short-shift and lift if you stay "
                       "out.")
            confidence = MEDIUM
        elif fuel:
            reason += f" {fuel}"
        return Call(BOX_NOW, state.lap, f"Box this lap.{compound}", reason,
                    confidence, severity=float(overdue))
    return Call(
        BOX_NOW, state.lap,
        f"Box this lap.{compound}",
        fuel or "On the plan.",
        severity=float(overdue),
    )


def _box_soon(state: RaceState) -> Call | None:
    to_stop = state.laps_to_stop()
    if to_stop is None or state.in_pit or state.finished:
        return None
    if not 1 <= to_stop <= 2 or _crossing_the_line(state):
        return None
    return Call(
        BOX_SOON, state.lap,
        f"Box in {to_stop}." if to_stop > 1 else "Box next lap.",
        f"Stop {state.stint_index + 1}, on the plan.",
        severity=float(-to_stop),
    )


def _fuel_instruction(state: RaceState) -> str:
    """How much to take, in litres, to the diamond plus a lap.

    **For the next stint, not for the rest of the race.** In a multi-stop race
    the fill at stop 1 has another stop after it, so fuelling to the flag asks
    for a tankful nobody needs - and where the tank cannot hold it, the call
    turned into a shortfall that does not exist. The stint's own lap count is
    the target and the burn is the one this race is showing, not the planned
    litres: the coordinator installs the race's measured rate for a reason,
    and reading the plan's `fuel_l` back would throw it away.

    Clamped to the tank, because an instruction the car cannot execute is
    worse than no instruction: the driver acts on it, finds the fill stops
    short, and has to work out the shortfall himself at pit-exit speed. When
    the clamp binds, the shortfall is the call - "fill it and you are still
    two laps short" is something he can plan around; "fuel to 510 litres" is
    not.
    """
    if not state.fuel_per_lap_l or state.laps_remaining() is None:
        return ""
    if state.next_stint_laps is not None:
        after_stop = state.next_stint_laps
        # **A stale plan must not size the fill.** When no further stop is
        # planned after the next stint, that stint runs to the flag - so if
        # the plan has drifted and the stint is now shorter than the laps
        # actually remaining, sizing the fill to it sends him back out to
        # run dry. `further_stop_planned` is None where nobody said (state
        # built by hand), and then the stint's own figure is taken at its
        # word.
        remaining = state.laps_remaining()
        if (state.further_stop_planned is False and remaining is not None
                and remaining > after_stop):
            after_stop = remaining
    elif state.stint_ends_on_lap is not None:
        # A stop is planned but how long the stint after it runs is unknown.
        # Fuelling to the flag is the safe direction to be wrong in, and the
        # clamp still reports what the tank cannot cover.
        after_stop = (state.laps_total or 0) - state.stint_ends_on_lap
    else:
        after_stop = state.laps_remaining()
    litres = (after_stop + 1) * state.fuel_per_lap_l

    # **A fill below what is already aboard is not an instruction.** "Fuel to
    # 27 litres" was voiced with 51.9 L in the tank - obeying was impossible
    # without draining it. GT7 cannot fill downwards, so when the tank
    # already covers the stint the honest line is that the fuel is fine,
    # which also tells him what the stop is actually for. Not "No fuel -":
    # under a helmet a sentence that leads with those words is an emergency
    # until its second half arrives.
    if state.fuel_l is not None and litres <= state.fuel_l:
        return "Fuel is fine - the tank covers the next stint."

    capacity = state.fuel_capacity_l
    if capacity and litres > capacity:
        short = (litres - capacity) / state.fuel_per_lap_l
        return f"Fuel to full. Still {short:.1f} laps short."
    return f"Fuel to {litres:.0f} litres."


# **`fuel_map_for` was here and has been deleted, deliberately.**
#
# It picked the richest fuel map that still reached the fuel target, and it
# was careful work: the map followed from the size of the shortfall rather
# than being a fixed "Map 3", and it reported what even map 6 could not cover.
#
# It is gone because the driver tested the premise and it does not hold for
# him: "I have only ever run FM1 and generally will never run anything else -
# you lose more lap time running a different fuel map than the fuel you save,
# versus short shifting and lift and coast or sitting in slipstream." His own
# test is primary evidence (CLAUDE.md §4.1), and a helper that exists to make
# a recommendation he will never take is not neutral - it is an invitation to
# wire the call back. `FUEL_MAP_CONSUMPTION` stays in `strategy.model`, where
# the offline plan still reasons about maps it may be asked to compare.


def short_shift_for(state: RaceState) -> tuple[float | None, float]:
    """The rpm drop that closes the fuel gap, and what it still leaves short.

    **The lever is short-shifting, never a fuel map.** He runs map 1 only and
    has tested why: a map step costs more lap time than the fuel it saves,
    against short-shifting, lift-and-coast or a tow. His own test is primary
    evidence, so the map recommendation this replaced was wrong for the only
    driver this app has.

    The conversion is measured per car by `tools/shortshift_trade.py` - on the
    Porsche at Monza, 1.762 L per 1000 rpm over 69 laps - and where no
    measurement exists for the car the answer is None, which the caller speaks
    as the lever without a number rather than inventing one.
    """
    slope = state.short_shift_l_per_1000rpm
    burn = state.fuel_per_lap_l
    target = _fuel_target(state)
    if not slope or slope <= 0 or not burn or not target or target <= 0:
        return None, 0.0
    if state.fuel_l is None:
        return None, 0.0
    # The burn that would make the fuel reach, and what has to come off.
    needed_burn = state.fuel_l / target
    saving = burn - needed_burn
    if saving <= 0:
        return 0.0, 0.0
    drop = saving / slope * 1000.0
    if drop <= state.short_shift_max_drop_rpm:
        return drop, 0.0
    # Capped: short-shifting alone will not do it, and the laps it still
    # cannot cover are the useful half of the call - that is a box decision,
    # not a saving one.
    capped = state.short_shift_max_drop_rpm
    reachable = burn - capped / 1000.0 * slope
    still = target - (state.fuel_l / reachable if reachable > 0 else target)
    return capped, max(0.0, still)


def stay_out_call(state: RaceState) -> Call | None:
    """The fold: the driver has voted with the car, and the fuel agrees.

    Made by the coordinator when a box call has gone `BOX_IGNORED_LAPS`
    unanswered, in place of the tenth repetition. The driver's action is
    primary evidence (CLAUDE.md §4.1): a driver running past his stop lap by
    lap is executing a stay-out, and the engineer's job becomes checking
    whether it works, not restating the plan he has already left.

    Returns None when the fuel genuinely cannot reach the flag within the
    short-shift lever's range - then the box call stands, escalated. Past the
    box lap `_fuel_gap` is already measured against the flag, which is the
    only target a stay-out has.

    **The measured-slope gate is `short_shift_for`'s own arithmetic, not a
    constant.** A -1.5-lap floor used to stand in for the lever's reach and
    it overcommitted: the drop is capped at `short_shift_max_drop_rpm`, and
    the first component of `short_shift_for`'s answer used to be taken while
    the second - the laps the capped drop still cannot cover - was thrown
    away, so a fold could say "you can make it" over a 0.7-lap hole and
    retire a stop the driver needed. The fold now requires the lever to
    actually close the gap.

    And it says "should", not "can", whenever it rests on him executing a
    saving lap after lap: `spoken()` only voices LOW out loud, so the hedge
    has to live in the words themselves.
    """
    gap = _fuel_gap(state)
    if gap is None:
        return None
    if gap >= 0:
        # The one unhedged form: the fuel aboard reaches on the burn already
        # measured, with no saving asked of him.
        return Call(STAY_OUT, state.lap, "Staying out? You can make it.",
                    "Fuel is good to the flag.")
    if state.short_shift_l_per_1000rpm:
        drop, still = short_shift_for(state)
        if not drop or still > STAY_OUT_STILL_SHORT:
            # The capped lever leaves laps uncovered: that is a box
            # decision, not a saving one, and the box call stands.
            return None
        # Rounded to fifty for the same reason the fuel call rounds: he is
        # reading a beep, and the fit's interval does not support more.
        return Call(
            STAY_OUT, state.lap,
            "Staying out? You should make it.",
            f"Short-shift {int(round(drop / 50.0) * 50)}, "
            f"you're {abs(gap):.1f} short.")
    if gap < STAY_OUT_GAP_UNMEASURED:
        return None
    # No measured slope for this car: the lever is named without a number
    # rather than inventing one, and the confidence drops with it.
    return Call(
        STAY_OUT, state.lap,
        "Staying out? You should make it.",
        f"Short-shift and lift - you're {abs(gap):.1f} laps short to the "
        "flag.",
        MEDIUM)


def _fuel(state: RaceState) -> Call | None:
    gap = _fuel_gap(state)
    if gap is None or state.in_pit or state.finished:
        return None
    if _crossing_the_line(state):
        return None

    confidence = MEDIUM if state.lap < 3 else HIGH
    if gap < -FUEL_SHORT_LAPS:
        drop, still = short_shift_for(state)
        reason = f"You're {abs(gap):.1f} laps short on fuel."
        if still > 0.05:
            # Said second because the instruction still stands - saving what
            # can be saved shortens the fill even when it cannot delete it.
            reason += f" Still {still:.1f} short after it."
        if drop:
            # Rounded to fifty because he is reading a beep, not a dial, and
            # a drop stated to the rpm implies a precision the fit does not
            # have - its interval is [0.92, 2.60] L per 1000 rpm.
            call = f"Short-shift {int(round(drop / 50.0) * 50)}."
        else:
            # No measured conversion for this car. The lever is still right -
            # it is his lever - but the number would be fabricated, so it is
            # replaced by the other two things he actually does.
            call = "Short-shift and lift into the slow corners."
        return Call(FUEL_SHORT, state.lap, call, reason, confidence,
                    severity=-gap)
    if gap > FUEL_LONG_LAPS and _past_half_stint(state):
        # Only worth saying once the stint is half run. At the start of a
        # stint there is always surplus - the tank was just filled - and
        # "you can push" on lap one is noise the driver learns to ignore.
        return Call(
            FUEL_LONG, state.lap,
            "You can push.",
            f"{gap:.1f} laps of fuel in hand.",
            confidence,
            severity=gap)
    return None


def _past_half_stint(state: RaceState) -> bool:
    to_stop = state.laps_to_stop()
    if to_stop is None:
        remaining = state.laps_remaining()
        if remaining is None or state.laps_total is None:
            return True
        return state.lap >= state.laps_total / 2
    return state.laps_since_stop >= to_stop


def _tyre(state: RaceState) -> Call | None:
    """Only ever a warning, never a lap time.

    Wear is modelled, never measured, so this call carries low confidence by
    construction - and says so out loud.
    """
    if state.wear_per_lap is None or state.in_pit or state.finished:
        return None
    if _crossing_the_line(state):
        return None
    consumed = state.laps_since_stop * state.wear_per_lap
    if consumed < 0.85:
        return None
    reason = f"Modelled at {consumed:.0%}."
    if state.tyre_change_unconfirmed:
        # The count ran through a stop that said nothing about the tyres, so
        # the set may be fresher than this. Said out loud rather than folded
        # into the number: "unconfirmed" is a word the driver can act on.
        reason += " Counting through a stop that may have changed them."
    return Call(
        TYRE, state.lap,
        "Tyres are at the end of their window.",
        reason,
        LOW,
        severity=consumed)


def _tyre_temp(state: RaceState) -> Call | None:
    """The one tyre channel GT7 broadcasts, spoken sparingly.

    Three occasions, each at most once per stint, all from measured data:

    * **Cold at the green** - the first lap's means sit well below the
      measured window floor. With no window on file the relative form is
      allowed instead: both axles still climbing hard after lap one.
    * **In window** - confirmation, and only of a warning already given.
      A confirmation of nothing is chatter.
    * **A departure from the axle's own baseline** - not from the other
      axle's. Rears 8-11 degC hotter than fronts is this car's normal and ran
      that way for a whole measured race; only an axle leaving its OWN steady
      mean, or exiting the measured window hot, is a change worth a word.
      Fronts going first may suggest brake balance rearward - never, under
      any circumstances, forward: that is a standing driver instruction.
    """
    if state.in_pit or state.finished or _crossing_the_line(state):
        return None
    history = state.temp_history
    if not history:
        return None
    lap, front, rear = history[-1]
    if lap != state.lap:
        # The latest reading is from an earlier lap - this lap carried no
        # temps, and a call about a stale reading would be presented as
        # current. Missing is silence, never a carry-forward.
        return None
    wf, wr = state.temp_window_front, state.temp_window_rear

    # (a) Cold at the green.
    if "cold" not in state.temp_said:
        if wf and wr and len(history) == 1:
            if (front < wf[0] - TEMP_COLD_BELOW_C
                    or rear < wr[0] - TEMP_COLD_BELOW_C):
                if state.temp_laps_to_window:
                    n = state.temp_laps_to_window
                    reason = f"{n} lap{'' if n == 1 else 's'} to window."
                else:
                    reason = "Below window."
                return Call(TYRE_TEMP, state.lap, "Tyres cold.", reason,
                            tag="cold")
        elif wf is None and len(history) == 2:
            # No measured window yet: the only allowed form is relative -
            # both axles still climbing hard says lap one started cold.
            _, f0, r0 = history[0]
            if front - f0 >= TEMP_RISING_C and rear - r0 >= TEMP_RISING_C:
                return Call(TYRE_TEMP, state.lap, "Tyres cold.",
                            "Still coming up to temperature.", MEDIUM,
                            tag="cold")

    # (b) In window - confirmation of the warning, not chatter.
    if ("cold" in state.temp_said and "in-window" not in state.temp_said
            and wf and wr
            and wf[0] <= front <= wf[1] and wr[0] <= rear <= wr[1]):
        return Call(TYRE_TEMP, state.lap, "Tyres in window.", "",
                    tag="in-window")

    # (c) A departure from the axle's own established baseline. The
    # baseline is positional within THIS set's history - its first
    # `TEMP_WARMUP_LAPS` entries are its warm-up and stay out - never the
    # absolute race lap: the history is cleared on a tyre change, and a
    # lap-number filter once let a set fitted mid-race baseline itself on
    # its own cold laps, reading its normal steady temperature as heating.
    recent = history[-TEMP_TREND_LAPS:]
    steady = history[TEMP_WARMUP_LAPS:-TEMP_TREND_LAPS]
    if len(recent) < TEMP_TREND_LAPS or len(steady) < TEMP_BASELINE_MIN_LAPS:
        return None
    base_front = sum(e[1] for e in steady) / len(steady)
    base_rear = sum(e[2] for e in steady) / len(steady)
    # Rears first: on the measured cars they are the loaded axle, and the
    # traction warning is the more expensive one to miss.
    if "trend-rear" not in state.temp_said:
        trending = all(e[2] - base_rear >= TEMP_TREND_C for e in recent)
        hot = wr is not None and all(e[2] > wr[1] for e in recent)
        if trending or hot:
            up = rear - base_rear
            return Call(TYRE_TEMP, state.lap, "Rears heating.",
                        f"Up {up:.0f} on their normal. Mind traction.",
                        tag="trend-rear")
    if "trend-front" not in state.temp_said:
        trending = all(e[1] - base_front >= TEMP_TREND_C for e in recent)
        hot = wf is not None and all(e[1] > wf[1] for e in recent)
        if trending or hot:
            up = front - base_front
            return Call(TYRE_TEMP, state.lap, "Fronts heating.",
                        f"Up {up:.0f} on their normal. "
                        "Brake balance one click rearward.",
                        tag="trend-front")
    return None


def _status(state: RaceState) -> Call | None:
    """Proactive reassurance, rarely. Silence should mean nothing to report."""
    if state.lap < 1 or state.finished or state.in_pit:
        return None
    if state.lap % STATUS_EVERY_LAPS != 0 or _crossing_the_line(state):
        return None
    remaining = state.laps_remaining()
    where = f"P{state.position}." if state.position else ""
    # A timed race has no lap count to count down: the distance follows from
    # the plan and the flag falls on the clock, so the figure is an estimate
    # and is spoken as one.
    about = "about " if state.race_minutes else ""
    left = f"{about}{remaining} to go." if remaining is not None else ""
    return Call(STATUS, state.lap, f"{where} {left}".strip(), "")


def clear_stint(state: RaceState, *, tyres_changed: bool | None = None) -> None:
    """A stop resets what has been said, so the next stint speaks freshly.

    **The tyre model is only reset when the tyres actually changed.** GT7 lets
    you take fuel without taking tyres, and `analysis/runs.py` forbids the
    same inference offline for the same reason: treating every stop as a fresh
    set halves every wear rate that spans one, and here it silenced the
    end-of-window call for a whole further stint - the driver reading silence
    as nothing to report.

    `None` is "the stop said nothing either way", which is not "no". The count
    carries on and the call that rests on it is marked unconfirmed.
    """
    state.said = [kind for kind in state.said if kind in (GREEN,)]
    state.said_at = {kind: value for kind, value in state.said_at.items()
                     if kind in (GREEN,)}
    # The temp occasions speak freshly each stint either way; the history
    # only survives when the rubber does - a new set's baseline is its own,
    # and it starts cold, which is exactly what the cold check should see.
    state.temp_said = set()
    if tyres_changed:
        state.laps_since_stop = 0
        state.tyre_change_unconfirmed = False
        state.temp_history = []
    elif tyres_changed is None:
        state.tyre_change_unconfirmed = True
