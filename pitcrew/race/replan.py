"""Re-planning the race, from scratch, at the end of every lap.

The driver redirected this design in as many words: *"Race engineer needs to
read data at end of every lap and recalculate entire strategy each lap based
on all the practice data and even more important the current race data,
especially as the race data builds... The offer shouldn't expire after two
laps as the engineer should be re assessing after each lap and looking at what
is now the optimal."*

So the model that used to live here - a drift threshold that decided whether
to think at all, and an offer desk that held one question open for two laps
and then let it lapse - is gone. What replaces it:

* **The whole problem is rebuilt and solved every lap.** `assess` assembles
  the rest of the race from practice evidence plus everything this race has
  shown, and puts it through `recommend`. The answer is always current.
* **Speaking is a separate decision from thinking.** `PlanRegister` compares
  the fresh optimum against what the driver was last told and speaks only when
  the answer has MATERIALLY changed. The failure this replaces is the race of
  16 Aug: nine identical box calls. Recalculating each lap must not become
  announcing each lap, and silence is what the status call already promises
  means "nothing to report".
* **Nothing expires.** There is no pending-offer state and no expiry timer,
  because the engineer reassesses next lap anyway and will say whatever is
  optimal then. "Offered, never imposed" survives: adopting a different stop
  SHAPE still needs the driver's word (PTT accept/keep), and until he gives it
  the plan of record stands. What he hears is simply always the latest.

### The lap-time guard, which is not negotiable

**Lap time confirms; it never triggers.** His measured lap-to-lap standard
deviation at this car and circuit is **2.04 s** - wider than the entire
0.5-1.5 s/lap degradation band a stint plan is trying to see, by a factor of
more than two. At that spread a 2 s/lap deviation takes four laps to become
distinguishable and a 1 s/lap deviation takes sixteen, so a fifteen-lap race
can never honestly show a one-second drift at all. A pace-driven verdict is
therefore a coin flip dressed as a finding, and the first verdict of one
measured race was exactly that: "lapping 2% slower than planned", voiced two
minutes after the green, built on the standing-start lap.

(The figure on record was 0.918 s. It is a Monza/Porsche number taken over a
population that still contained incident laps, and recomputed clean it is
0.68-0.76 s even there - a builder who had inherited it would have
over-claimed detectability by about a factor of two.

**Sigma is therefore never inherited: it is re-measured from the clean laps of
the race in progress**, which makes it per-car and per-circuit by
construction. It is not yet PERSISTED per car and circuit, so every race
starts without one and says "not yet measurable" until four clean laps exist -
honest, but it means the first laps of every race are mute on pace even at a
circuit measured a dozen times. Storing it is the outstanding half.)

There is a standing rule in this project's history: *never route a lap-time
TRIGGER through `recommend()`*. It is honoured here, and the word doing the
work is "trigger". Lap time may not raise a finding and may not be the reason
a stop count changes; those are routed off fuel burn - the low-noise channel -
and off the wear assumption, which is labelled an assumption because GT7
broadcasts no wear at all.

**Lap time as a unit is a different thing from lap time as a signal**, and the
rule was never about the unit. How many laps fit in the time left is a
question about lap times and always was; so is what a nineteen-second pit stop
costs in laps. `_remaining_race` therefore prices the remainder in the median
lap this race has actually run, and sets out there why the distance cannot
move on it: the laps left are counted upstream against that same median and
handed in, so converting them back into minutes round-trips exactly whatever
the figure is. A faster median cannot invent or remove a stop. It can only
stop a stop looking cheaper than it is.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, replace

from pitcrew.diagnostics import log
from pitcrew.race.calls import saving_covers
from pitcrew.strategy.model import (
    RaceInputs,
    StrategyImpossible,
    recommend,
)

# How far off the planned burn is worth putting into words. Below this the
# burn is "on plan" and the reason does not mention it.
FUEL_DRIFT = 0.05
# The band edges for the burn-versus-expectation line the driver asked for.
# Entering a band takes a 5% deviation; returning to "on plan" takes coming
# back inside 3%. The gap is hysteresis: a burn sitting exactly on 5% would
# otherwise announce itself every other lap.
BURN_BAND_ENTER = 0.05
BURN_BAND_LEAVE = 0.03
BAND_ON = "on plan"
BAND_OVER = "over plan"
BAND_UNDER = "under plan"

# A new plan must beat the current one by more than this to be worth the
# disruption of changing strategy mid-race.
WORTH_CHANGING_S = 8.0

# **The re-plan's time budget, and why it needs one.** Measured at this
# event's real shape a full `recommend()` costs 1.4 ms - eight percent of one
# telemetry frame, and 21 ms across a whole thirty-minute race. Free.
#
# But the cost is not bounded by the race, it is bounded by how many compounds
# have profiles, and it is superlinear: `_candidate_sequences` enumerates
# `compounds ** stints`, so two profiled compounds cost 32 ms, three cost
# 234 ms, and a fifty-lap TIMED race with three profiled compounds costs
# **6.35 seconds** - the fixed-point clock search making a timed race about
# thirty times a distance race of the same length. Today only RS has a
# profile, which is the only reason this is cheap. The moment a second and a
# third get one, an unbudgeted per-lap re-plan blocks the Qt thread mid-race.
#
# So the caller times it and degrades honestly: over budget once and the
# search narrows; over budget again and the engineer keeps the plan he has and
# says nothing, which is the correct failure for an adviser.
REPLAN_BUDGET_S = 0.05
REPLAN_MAX_STOPS = 3
REPLAN_NARROWED_MAX_STOPS = 2

# **The budget has to be checked BEFORE the solve, or it is not a budget.**
# Timing `assess` and reacting afterwards means the 6.35-second solve happens
# in full, on the Qt thread, mid-race - and then the narrowed retry happens
# too. So the size of the problem is estimated first, from the two numbers
# that drive it, and an oversized one is refused rather than attempted.
#
# `recommend` calls `build_plan` once per ordered compound assignment per stop
# count: `sum(n ** s for s in 1..stops+1)`. Each call costs roughly in
# proportion to the race distance, and a timed race costs about thirty times a
# distance race of the same length because `clock_bound_stints` runs a
# fixed-point search inside it. Calibrated against the measured table:
#
#     1 compound, 15 laps, timed        5 calls      1.4 ms
#     2 compounds, 15 laps, timed      62 calls     32   ms
#     3 compounds, 15 laps, timed     363 calls    234   ms
#     1 compound, 50 laps, timed        5 calls     38   ms
#     3 compounds, 50 laps, timed     363 calls   6351   ms
#
# `calls x laps` orders every row of that table correctly, which is all a
# refusal needs. The cap is set at the point the predicted cost passes the
# budget on the linear part of the curve; everything above it is refused
# without being attempted, and the post-hoc measurement stays as a backstop
# for a shape this estimate does not anticipate.
#
# **Recalibrated 23 Aug 2026, and it had to be.** The estimator counts search
# WORK; the cap converts that into a time budget, and the conversion rate
# changed when `recommend` started sharing its cost and dynamic-programming
# results across candidate sequences. The same table, re-measured:
#
#     1 compound, 15 laps, timed        5 calls    1.4 ->   0.7 ms
#     2 compounds, 15 laps, timed      62 calls   32   ->   8.1 ms
#     3 compounds, 15 laps, timed     363 calls  234   ->  45.3 ms
#     1 compound, 50 laps, timed        5 calls   38   ->   1.0 ms
#     3 compounds, 50 laps, timed     363 calls 6351   ->  63.8 ms
#
# A hundred times faster at the wide end. Left at 1200 the cap would have gone
# on refusing searches that now cost fifteen milliseconds, which is the whole
# point of the change thrown away - and the estimate would have been wrong by
# more than an order of magnitude in the direction that silently costs the
# driver the better plan.
#
# **The budget is unchanged at about 40 ms.** That is what 1200 meant on the
# old curve - 930 work measured 32 ms, so 1200 was ~41 ms - and it is
# deliberately kept, because this runs on the Qt thread at a lap crossing and
# the acceptable hitch has not changed just because the search got faster.
# Only the units have.
#
# 5000 is where ~40 ms now falls, measured on the shapes the re-plan actually
# runs (three profiled compounds, timed remainder):
#
#     laps left   max stops    work    was        now
#            27           2    1053    ok        4.0 ms
#            27           3    3240    REFUSED  15.0 ms   <- now allowed
#            27           4    9801    REFUSED  48.3 ms   <- still refused
#            20           3    2400    REFUSED  13.7 ms   <- now allowed
#            12           4    4356    REFUSED  38.2 ms   <- now allowed
#
# The row that matters is the second. `self._replan_max_stops` latches DOWN
# when a search is refused and is never restored, so the 3-stop shape was
# ruled out on lap one and not reconsidered for the rest of the race - at
# Monza on 18 Aug that is the plan that removes a stop and gains a whole lap.
# It cost 165 ms then and costs 15 ms now; refusing it was right at 165 and
# is indefensible at 15.
REPLAN_MAX_WORK = 5000


def replan_work(inputs: RaceInputs | None, laps_left: int,
                max_stops: int) -> int:
    """The size of the search `assess` is about to run. Zero when unknown."""
    if inputs is None or laps_left <= 0:
        return 0
    compounds = max(1, len(inputs.planning_compounds()))
    calls = sum(compounds ** stints for stints in range(1, max_stops + 2))
    return calls * laps_left

# **How far the next stop may move before it is worth another word.** The
# driver's instruction was "the stop lap moves by more than a lap or two". Two
# is the figure: one lap of movement is the model rounding a stint against a
# burn that moved a tenth of a litre, and telling him about it every lap is
# the nine-box-calls defect wearing a different hat.
STOP_LAP_MOVE_LAPS = 2

# **How short on fuel the plan he is already running may be and still count as
# runnable - and it applies to that plan only.**
#
# The same half-lap the urgent branch allows, for the same reason: a driver
# 0.4 laps short is a short-shift call, not a plan that cannot be executed. Set
# to zero, the measured race read "the 0-stop plan is no longer runnable" from
# lap 9 to the flag and would have reopened the box conversation the engineer
# had just closed by folding to the driver's stay-out - on a race he finished
# with 1.79 litres in the tank.
#
# It is the same figure `stay_out_call` already uses for a car with no
# measured short-shift slope, and for the same reason: inside half a lap he
# closes it with lift-and-coast, and the measured race is the proof - he
# finished 0.34 laps short on paper with 1.79 litres in the tank.
#
# **A plan that only fits inside the tolerance says so out loud.** Silently
# recommending a shape that depends on him saving fuel would be the app
# quietly betting his race on a lever it never mentioned; the shortfall and
# the lever go in the reason, and the confidence comes down with them.
FUEL_FITS_TOLERANCE_LAPS = 0.5

# **How much race a stop needs behind it to be worth taking.** Re-planning the
# REMAINDER hands the model shorter and shorter problems, and on a timed
# remainder it starts preferring shapes that would never be raced: with four
# laps left the search came back with three stops and quoted a gain of 476
# seconds, which is the timed model comparing plans that cover different
# distances. Two laps per stop throws those out before they can be offered,
# without touching the model that produces them.
#
# It is a rule about the STOP COUNT and not about the individual stints, on
# purpose. `allocate_laps` will happily hand a distance race a [14, 1] split -
# the tyre limit lets the first stint take everything - and rejecting that
# shape outright left nothing runnable at all on a race where the plan of
# record was a perfectly ordinary one-stop.
LAPS_PER_STOP = 2

# A residue below this is not worth voicing - the same epsilon the fuel call
# uses before it bothers reporting what a short-shift still leaves uncovered.
STILL_SHORT_EPSILON = 0.05

NONE = "none"
# Spoken, but not a question: a fact about how the race is running against
# what the plan expected. Nothing to accept or keep.
NOTED = "noted"
RECOMMENDED = "recommended"
URGENT = "urgent"

# How a recommendation left the register. Recorded with the revision so the
# post-race audit can tell an answer from a supersession.
RESOLVED_ACCEPTED = "accepted"
RESOLVED_KEPT = "explicitly kept"
RESOLVED_SUPERSEDED = "superseded by a later recomputation"

# What the stop count in a plan rests on, said out loud in the reason.
# Nothing derived is presented as measured (CLAUDE.md §4.5), and the wear rate
# behind every stint length is the plan's assumption for the whole race:
# there is no wear channel and no gauge reading is entered while racing.
WEAR_IS_ASSUMED = "wear is the plan's assumption, not a reading"

# **Said once, when per-lap re-planning gives up for the race.** Here rather
# than inline in the controller so `phrase_manifest` can reach it: a sentence
# the manifest cannot obtain is rendered nowhere and is synthesised live, and
# this one arrives mid-race to tell him the engineer has stopped adapting.
REPLANNING_OFF = ("Strategy re-planning is off. The approved plan stands - "
                  "I won't adapt the stops from here.")


@dataclass(frozen=True)
class Replan:
    """What the model now thinks, and how strongly."""
    verdict: str
    reason: str
    stops: int | None = None
    stint_laps: tuple[int, ...] = ()
    # The rubber the re-planner chose for each of those stints. `recommend`
    # has always returned it on `Stint.compound` and this dataclass dropped it
    # on the floor, so `adopt` had nothing to take and wrote `None` over the
    # plan's own answer. A compound is not a detail of a stop, it is the stop.
    stint_compounds: tuple[str | None, ...] = ()
    # **The tyres decision the re-planner priced, per stint** (the critic on
    # row 2.6, pass 2, MAJOR). `recommend` prices every stop as a fresh set,
    # so every stop in its answer is `True`; the first stint is the one being
    # driven, whose stop is behind him, and is `None` - nothing to decide.
    # Without it `adopt` carried the old plan's decisions by position, and a
    # re-plan that added a stop moved "No tyres." onto a stop it was never
    # made for.
    stint_tyres: tuple[bool | None, ...] = ()
    gain_s: float = 0.0
    confidence: str = "medium"
    # The lap the next stop would fall on under this answer, or None where the
    # answer has no stop in it. **Recorded, but never compared.**
    next_stop_lap: int | None = None
    # **How many laps from NOW that stop is, which is the comparable figure.**
    # `next_stop_lap` is absolute, and re-planning the remainder re-starts the
    # first stint at the current lap every time - so a tyre-limited stint of a
    # fixed length marches the absolute number forward one lap per lap while
    # the answer has not changed at all. Compared absolutely it tripped
    # `STOP_LAP_MOVE_LAPS` every third lap: nine announcements in 28 laps on a
    # probe, the same instruction three times running. Relative, it sits
    # still.
    laps_to_next_stop: int | None = None
    # Laps short of the flag that a fuel save covers, on a zero-stop race, or
    # None. Not a stop: the fuel call says the save (`calls.fuel_save_l`).
    fuel_short_laps: float | None = None

    @property
    def offered(self) -> bool:
        """Whether this is a change of stop shape, needing the driver's word."""
        return self.verdict in (RECOMMENDED, URGENT)

    @property
    def worth_speaking(self) -> bool:
        return self.verdict in (NOTED, RECOMMENDED, URGENT)

    def call(self) -> str:
        """One instruction, in the engineer's register.

        **Never "Recommend None stops."** A verdict can be offered with no
        stop count - the low-confidence branch where there is nothing to
        re-plan with says something has changed without knowing the shape -
        and it must not be read out as an arithmetic accident.
        """
        if self.verdict == NOTED:
            return self.reason
        if not self.offered:
            return ""
        if self.stops is None:
            return "The plan needs a look."
        if self.stops == 0:
            return "Recommend running to the flag."
        # **"N stops" means three things** (row 1.10): the brief's total
        # for the race, `BOX_SOON`'s ordinal ("Stop 2, on the plan"), and
        # this, which is stops REMAINING. "from here" is the reference.
        return (f"Recommend {self.stops} stop"
                f"{'' if self.stops == 1 else 's'} from here.")

    def spoken_reason(self) -> str:
        """The reason, cut to one clause. §5.5: instruction first, reason short.

        `reason` accumulates every fact the verdict rests on, because the
        revision record wants all of them. What he hears under a helmet at
        racing speed is the first one - the finding that actually raised the
        call - and the rest stays in the record. Measured on the certifying
        replay, the full string was 145 characters of three semicolon-joined
        clauses starting in lower case.
        """
        first = self.reason.split(";")[0].strip()
        if not first:
            return ""
        return first[0].upper() + first[1:] + "."

    def as_plan(self) -> dict:
        return {
            "verdict": self.verdict,
            "stops": self.stops,
            "stint_laps": list(self.stint_laps),
            "stint_compounds": list(self.stint_compounds),
            "stint_tyres": list(self.stint_tyres),
            "next_stop_lap": self.next_stop_lap,
            "laps_to_next_stop": self.laps_to_next_stop,
            "gain_s": round(self.gain_s, 1),
            "reason": self.reason,
            "confidence": self.confidence,
        }


@dataclass(frozen=True)
class Resolution:
    """How one recommendation ended: what it was, when, and on whose word."""
    offer: Replan
    lap: int
    accepted: bool
    reason: str


@dataclass(frozen=True)
class Recomputation:
    """One lap's re-plan: what the model said, and whether it was voiced.

    Every lap produces one of these. Only the ones with `spoken` set reach the
    driver, and only those become a row in `race_revisions` - **a
    recomputation that changes nothing is not a revision**, and a row per lap
    would bury the ones that matter under a race's worth of noise.
    """
    lap: int
    verdict: Replan
    spoken: bool
    why: str = ""


def materially_different(new: Replan, told: Replan | None, *,
                         stop_lap_move: int = STOP_LAP_MOVE_LAPS,
                         abandoned_stops: int | None = None
                         ) -> tuple[bool, str]:
    """Whether the fresh optimum says something the driver has not been told.

    Returns the answer and, when it is yes, the reason in the engineer's own
    words - which is what the revision record stores, so the audit can read
    why the engineer opened his mouth as well as what he said.

    Four things are material, and nothing else is:

    * the stop count changes - that is a different race;
    * the stop moves by more than `stop_lap_move` laps FROM NOW;
    * the answer escalates to urgent, which is the fuel picture crossing into
      "won't reach the flag";
    * or it de-escalates out of urgent, which is the same crossing the other
      way and is worth saying because the driver is currently saving fuel he
      may not need to save.

    **`abandoned_stops` is the swap-back guard, and it is not optional.** A
    race sitting on a stop-count boundary flips the model's answer lap to lap,
    and the measured race sat inside 1.80% of exactly that boundary. The first
    swap is information; swapping straight back is the model dithering out
    loud, and a probe of six consecutive laps produced six contradictory
    instructions - "Recommend 1 stop" / "running to the flag" / "1 stop" /
    "running to the flag". `OfferDesk` refused the swap-back and the class
    that replaced it did not; this is that guard, restored. Only an escalation
    to urgent goes through it, because that is arithmetic and not preference.
    """
    if told is None:
        return new.worth_speaking, "first assessment of the race"
    if not new.offered:
        if told.verdict == URGENT and new.fuel_short_laps is None:
            return True, "the fuel picture has cleared"
        return False, ""
    urgent_now = new.verdict == URGENT and told.verdict != URGENT
    if urgent_now and told.fuel_short_laps is not None:
        return True, "a fuel save no longer covers the shortfall"
    if new.stops != told.stops:
        if (abandoned_stops is not None and new.stops == abandoned_stops
                and not urgent_now):
            return False, ""
        return True, "the stop count has changed"
    if urgent_now:
        return True, "the fuel no longer reaches the flag"
    # **Laps from now, never the absolute lap alone** - see
    # `laps_to_next_stop`. **And never laps from now alone either.** A stop
    # that stays on lap 11 comes three laps nearer in three laps: Suzuka,
    # 13 Sep 2026, "the stop has moved 3 laps" four times while it sat on 11,
    # 11, 13, 13. A stop has moved when BOTH say so; the lap he boxes on is
    # the figure spoken.
    if (new.laps_to_next_stop is None or told.laps_to_next_stop is None):
        return False, ""
    relative = new.laps_to_next_stop - told.laps_to_next_stop
    absolute = (new.next_stop_lap - told.next_stop_lap
                if new.next_stop_lap is not None
                and told.next_stop_lap is not None else relative)
    if min(abs(relative), abs(absolute)) <= stop_lap_move:
        return False, ""
    way = "later" if absolute > 0 else "earlier"
    return True, f"the stop has moved {abs(absolute)} laps {way}"


def burn_band(drift: float | None, current: str = BAND_ON) -> str:
    """Which side of its expected burn the race is running, with hysteresis.

    Entering a band takes `BURN_BAND_ENTER`; coming back to "on plan" takes
    returning inside `BURN_BAND_LEAVE`. Without the gap a burn hovering on the
    threshold announces itself every other lap, which is the failure this
    whole module exists to avoid.
    """
    if drift is None:
        return current
    if current == BAND_ON:
        if drift >= BURN_BAND_ENTER:
            return BAND_OVER
        if drift <= -BURN_BAND_ENTER:
            return BAND_UNDER
        return BAND_ON
    if abs(drift) <= BURN_BAND_LEAVE:
        return BAND_ON
    if drift >= BURN_BAND_ENTER:
        return BAND_OVER
    if drift <= -BURN_BAND_ENTER:
        return BAND_UNDER
    return current


class PlanRegister:
    """What the driver was last told, and whether the latest optimum differs.

    This is what the `OfferDesk` became. The desk existed to stop one
    unanswered offer gagging the engineer for a race - it expired offers after
    two laps, superseded them, and drained them at the flag. None of that is
    needed once the engineer re-solves every lap: there is no question left
    open, because next lap he will say whatever is optimal then.

    What IS needed is the opposite guard. Recalculating every lap makes it
    trivially easy to announce every lap, which is the exact defect the race
    of 16 Aug was: nine identical box calls to a driver who was right. So the
    register holds the last thing said and speaks only on a material change.

    **The driver's own choice of shape outranks the model.** When he votes
    with the car - running past a box call until the engineer folds to his
    stay-out - the register is told, and it will not re-propose the shape he
    abandoned. Only the fuel failing to reach the flag cuts through that,
    because that is not a preference, it is arithmetic.
    """

    def __init__(self, *, stop_lap_move: int = STOP_LAP_MOVE_LAPS) -> None:
        self.stop_lap_move = stop_lap_move
        self.told: Replan | None = None
        self.told_lap: int | None = None
        self.band: str = BAND_ON
        # The stop count the driver has chosen with his own hands, or None
        # while the plan of record is the engineer's.
        self.driver_shape_stops: int | None = None
        # What the last swap moved AWAY from, so the model cannot swap back
        # to it the next lap. See `materially_different`.
        self.abandoned_stops: int | None = None

    def reset(self) -> None:
        self.told = None
        self.told_lap = None
        self.band = BAND_ON
        self.driver_shape_stops = None
        self.abandoned_stops = None

    def note_driver_shape(self, stops: int, *, lap: int | None = None) -> None:
        """The driver has chosen a shape - by staying out, or by keeping.

        His action is primary evidence (CLAUDE.md §4.1). From here the
        engineer's job is to keep checking THAT shape, not to keep offering
        the one he left.
        """
        self.driver_shape_stops = stops
        if lap is not None:
            self.told_lap = lap

    def consider(self, verdict: Replan, *, lap: int,
                 burn_drift: float | None = None,
                 race_evidence: bool = True,
                 may_speak=None) -> Recomputation:
        """One lap's fresh optimum in; what to say, if anything, out.

        The burn band is folded in here rather than spoken separately, because
        **one call per lap** is a hard rule: when the stop shape has something
        to say, that wins and the band is updated silently. When it has not,
        a band crossing is the lap-to-lap reference the driver asked for -
        "burning 8% under plan, no change to the stops" - and it is said once
        per crossing, never once per lap.

        `may_speak` is a predicate the caller supplies, asked about **the
        thing actually about to be said** rather than about the raw verdict.
        The distinction is not academic: a verdict of "on the plan" can still
        produce a burn note, and ranking the verdict instead of the note let a
        note be voiced on the same crossing as a tyre call. One call per lap
        is a hard rule and it has to hold ACROSS the two producers, not just
        within each. A held candidate changes no state at all, so the next lap
        reconsiders it from scratch and says it then if it still holds.

        `race_evidence` is False until this race has shown something the plan
        was not built on - in practice, until its own fuel burn has converged.
        **Before that the engineer has nothing new to say.** The model will
        still often prefer a different shape on lap one, because the approved
        plan is the driver's choice among ranked options and not always the
        model's favourite; re-offering the model's favourite two minutes after
        the green is not re-planning, it is arguing about a decision he already
        made. The fuel failing to reach the flag is the exception, because that
        is arithmetic rather than preference.
        """
        band = burn_band(burn_drift, self.band)
        band_changed = band != self.band

        blocked = (self._blocked_by_the_driver(verdict)
                   or (not race_evidence and verdict.offered
                       and verdict.verdict != URGENT))
        say, why = materially_different(
            verdict, self.told, stop_lap_move=self.stop_lap_move,
            abandoned_stops=self.abandoned_stops)
        if blocked:
            say, why = False, ""
        if (self.told is not None and self.told.verdict == URGENT
                and verdict.fuel_short_laps is not None):
            # **The stop is withdrawn in favour of a save, silently here.**
            # "Fuel reaches the flag now" would be false, and the fuel call
            # says the save with its figure. Committed, so the day the tank
            # does reach is not announced twice.
            self.told = verdict
            self.told_lap = lap

        def allowed(candidate: Replan) -> bool:
            return may_speak is None or may_speak(candidate)

        held = Recomputation(lap, verdict, spoken=False,
                             why="held - a more urgent call owns this lap")

        if say and not verdict.worth_speaking:
            # **A de-escalation is still news.** The one that matters is the
            # fuel picture clearing: he has been saving fuel he may no longer
            # need to save, and nobody has told him to stop. The verdict
            # itself has nothing to offer - it is "on the plan" - so it is
            # voiced as a note rather than as a question.
            cleared = Replan(NOTED, "Fuel reaches the flag now. Plan stands.",
                             confidence="high")
            if not allowed(cleared):
                return held
            self.band = band
            self.told = verdict
            self.told_lap = lap
            return Recomputation(lap, cleared, spoken=True, why=why)
        if say and verdict.worth_speaking:
            if not allowed(verdict):
                return held
            self.band = band
            if (self.told is not None and self.told.offered
                    and verdict.stops != self.told.stops):
                self.abandoned_stops = self.told.stops
            self.told = verdict
            self.told_lap = lap
            return Recomputation(lap, verdict, spoken=True, why=why)

        if band_changed and burn_drift is not None:
            note = _band_note(band, burn_drift)
            if note is not None and not allowed(note):
                # **The band is NOT committed here.** Committing it while the
                # note is held loses the crossing entirely: `band_changed` is
                # false on every later lap and the note is never said. Leaving
                # the band where it was means the same crossing is detected
                # again next lap, and said then.
                return held
            self.band = band
            if note is not None:
                # Not a change of plan and not a question - a fact, recorded
                # so the audit can see what the engineer was reading when he
                # did or did not change anything.
                return Recomputation(lap, note, spoken=True,
                                     why="the burn has moved against the plan")
        else:
            self.band = band
        return Recomputation(lap, verdict, spoken=False, why="")

    def _blocked_by_the_driver(self, verdict: Replan) -> bool:
        """Whether this answer re-proposes a shape the driver has abandoned."""
        if self.driver_shape_stops is None or not verdict.offered:
            return False
        if verdict.verdict == URGENT:
            # Not a preference: the fuel does not reach. It cuts through.
            return False
        return verdict.stops != self.driver_shape_stops

    def answered(self, *, accepted: bool, lap: int,
                 current_stops: int | None = None) -> Resolution | None:
        """The driver said accept or keep. Returns the resolution to record.

        Either answer settles the shape: accepting adopts the recommendation,
        keeping is him choosing the plan of record, and **both are him
        voting**. The register notes the shape either way so the next lap's
        recomputation confirms or revises HIS race rather than reopening the
        question he has just closed.

        The "keep" half used to clear `driver_shape_stops` instead of setting
        it, against this docstring's own promise, and the consequence was
        immediate: he said keep on lap 6 and on lap 7 heard "the stop count
        has changed - Recommend 2 stops", which is the plan of record offered
        back to him as news, one lap after he refused to change it.
        `current_stops` is the shape he is actually running and is what "keep"
        means.
        """
        offer = self.told
        if offer is None:
            return None
        if accepted and offer.stops is not None:
            self.note_driver_shape(offer.stops, lap=lap)
        elif not accepted:
            shape = current_stops
            if shape is None and offer.stops is not None:
                # Nobody said what he is running. The one thing known is that
                # it is not what he just refused, so the refusal is at least
                # remembered as a shape not to re-propose.
                self.abandoned_stops = offer.stops
            elif shape is not None:
                self.note_driver_shape(shape, lap=lap)
        return Resolution(offer, lap, accepted=accepted,
                          reason=RESOLVED_ACCEPTED if accepted
                          else RESOLVED_KEPT)


def _band_note(band: str, drift: float) -> Replan | None:
    """The burn-against-expectation line, in the engineer's register."""
    if band == BAND_ON:
        return Replan(NOTED, "Burn is back on plan. Stops unchanged.",
                      confidence="high")
    direction = "over" if drift > 0 else "under"
    lever = ("Watch the fuel." if drift > 0
             else "The stops are unchanged for now.")
    return Replan(
        NOTED,
        f"Burning {abs(drift):.0%} {direction} plan. {lever}",
        confidence="high")


def observed_fuel_per_lap(fuel_used: list[float]) -> float | None:
    """Burn measured this race, not in practice.

    Uses the median so one lap behind a safety car cannot move it.
    """
    burns = sorted(value for value in fuel_used if value > 0)
    if not burns:
        return None
    return burns[len(burns) // 2]


def drift(observed: float | None, planned: float | None) -> float | None:
    """Fractional difference, or None when either side is unknown."""
    if observed is None or not planned:
        return None
    return (observed - planned) / planned


def assess(**kwargs) -> Replan:
    """`_assess`, and a line in the log saying what it answered.

    Keyword-only, like the function it wraps: every caller already names its
    arguments, and a positional one here would be a silent mis-binding of a
    signature with thirteen terms in it.

    **This module logged nothing at all** - `grep -c replan logs/pitcrew.log`
    returned 0 for the whole of Bathurst Rd 8, a race whose strategy shape was
    decided here on every one of 28 laps and spoken twice. The burn's install
    and its refusal are logged beautifully one layer down; the thing that
    decides the shape of the race was completely dark, and the only way to
    tell what it had done was to infer it from a frozen stop count.

    CLAUDE.md rule 10's second half asks for the accepts and not only the
    refusals, and this is a solve rather than a filter - so every call gets a
    line, whether or not anything is said. Speaking is `PlanRegister`'s
    decision and it logs its own; this is the thinking.

    One line per crossing, which is dozens a race rather than thousands.
    """
    verdict = _assess(**kwargs)
    log("race").info(
        "re-plan on lap %s: %s%s%s, confidence %s - %s",
        kwargs.get("laps_done", "?"), verdict.verdict,
        "" if verdict.stops is None else f", {verdict.stops} stops from here",
        "" if verdict.laps_to_next_stop is None
        else f", next stop in {verdict.laps_to_next_stop} laps",
        verdict.confidence, verdict.reason or "nothing to report")
    return verdict


def _assess(*, laps_done: int, laps_total: int | None,
            fuel_l: float | None,
            planned_fuel_per_lap: float | None,
            observed_fuel_per_lap_l: float | None,
            lap_time_ms: int | None,
            planned_lap_time_ms: int | None,
            current_stops: int,
            inputs: RaceInputs | None = None,
            fuel_capacity_l: float | None = None,
            observed_fuel_sd_l: float | None = None,
            achieved_lap_ms: int | None = None,
            lap_sigma_s: float | None = None,
            max_stops: int = REPLAN_MAX_STOPS) -> Replan:
    """Rebuild the rest of the race and solve it. Called every lap.

    This used to decide whether to think: a drift threshold gated the call to
    `recommend`, so a plan that had quietly become wrong for reasons other
    than drift was never re-examined. It now **always** solves when it has
    inputs to solve with, and the decision about whether to open the
    engineer's mouth is `PlanRegister`'s, one layer up.

    `lap_time_ms` is the race's representative CLEAN pace and it is accepted
    here for one purpose only: to be ignored by the verdict. **It never raises
    a finding** - see the module docstring and the standing rule it cites. It
    stays in the signature because the caller has it and because a future
    reader should find the guard rather than the absence of one.

    `achieved_lap_ms` is a different figure and is used: the median lap as
    actually run, incidents included, which is what the coordinator already
    predicts the distance from. It enters `recommend` as the unit a timed
    race's laps are priced in, never as a signal - `_remaining_race` sets out
    why that distinction holds and why the distance cannot move on it.
    `observed_fuel_sd_l` and `lap_sigma_s` are this race's own scatter, which
    is what sizes every fill from here.
    """
    if laps_total is None or laps_done >= laps_total:
        return Replan(NONE, "race is over or its length is unknown")
    if laps_total - laps_done <= 1:
        # **Nobody turns into the pit lane on the last lap.** The export
        # contract says the same thing about planning (§10.0: no plan stops
        # after the flag), and the measured race is why it matters here - its
        # ninth and last box call was voiced on the chequered-flag crossing.
        # There is nothing left to re-plan, so there is nothing to say.
        return Replan(NONE, "one lap left - nothing to re-plan")

    fuel_drift = drift(observed_fuel_per_lap_l, planned_fuel_per_lap)
    reasons = []
    if fuel_drift is not None and abs(fuel_drift) > FUEL_DRIFT:
        reasons.append(
            f"burning {abs(fuel_drift):.0%} "
            f"{'more' if fuel_drift > 0 else 'less'} fuel than planned")

    # **Running out before the flag is urgent whatever the model prefers, and
    # it must not wait for the burn to converge.**
    #
    # This branch used to require `observed_fuel_per_lap_l`, which is None
    # until five GREEN race laps exist - and `race_evidence`, the gate that
    # holds every non-urgent verdict back, is the same predicate. So the gate
    # and its own exemption were one thing: a genuinely short tank on laps 2,
    # 3 and 4 produced a verdict that was computed and then silenced. On the
    # replayed race, where laps 4 and 5 were incidents and did not count as
    # green, the strategy layer was mute for the first seven of fifteen laps.
    # In a ten-lap sprint with two incidents it would be eight of ten.
    #
    # The arithmetic here needs a burn, not a CONVERGED burn. The race's own
    # figure is used the moment it exists and the plan's practice figure
    # stands in before that, with the confidence saying which - because
    # "you will not reach the flag" off a practice burn is a projection, and
    # off five green laps it is close to a reading.
    laps_left = laps_total - laps_done
    burn_now = observed_fuel_per_lap_l or planned_fuel_per_lap
    covered_short = None
    if fuel_l is not None and burn_now and current_stops == 0:
        laps_of_fuel = fuel_l / burn_now
        short = laps_left - laps_of_fuel
        measured = observed_fuel_per_lap_l is not None
        basis = "current burn" if measured else "the planned burn"
        if short > 0 and saving_covers(short, laps_left):
            # **A save, not a stop** - `calls.saving_covers`, the one
            # expression the fuel call reads too. Suzuka, 13 Sep 2026:
            # "Recommend 1 stop" at 1.4 laps short on a count a lap long, and
            # he made the flag on 2.73 L without one.
            covered_short = short
            if inputs is None:
                return Replan(NONE, f"{short:.1f} laps short of the flag on "
                              f"{basis} - a fuel save covers it", stops=0,
                              fuel_short_laps=short)
        elif laps_of_fuel < laps_left - 0.5:
            return Replan(
                URGENT,
                f"{short:.1f} laps short of the flag on {basis}",
                stops=1, gain_s=0.0,
                confidence="high" if measured else "medium",
                next_stop_lap=laps_done + max(1, int(laps_of_fuel)),
                laps_to_next_stop=max(1, int(laps_of_fuel)))

    if inputs is None:
        # Nothing to re-plan with. Say what has changed rather than inventing
        # a stint length, and only when something has: with no model behind
        # it, "the plan still holds" is not a claim this branch can make.
        if not reasons:
            return Replan(NONE, "on the plan")
        return Replan(RECOMMENDED, "; ".join(reasons), confidence="low")

    rest = _remaining_race(inputs, laps_left, observed_fuel_per_lap_l,
                           fuel_capacity_l,
                           observed_fuel_sd=observed_fuel_sd_l,
                           achieved_lap_ms=achieved_lap_ms,
                           lap_sigma_s=lap_sigma_s)
    try:
        plans = recommend(rest, max_stops=max_stops)
    except StrategyImpossible as exc:
        return Replan(RECOMMENDED,
                      "; ".join(reasons + [str(exc)]) if reasons else str(exc),
                      confidence="low")

    burn = observed_fuel_per_lap_l or inputs.fuel_per_lap_l
    # **The fuel filter removes plans; it must never promote one.**
    #
    # It applies to every shape that is not strictly more stops than he is
    # running - including his own count, because re-optimising the remainder
    # can move the stop later and ask the tank for more than is in it. Adding
    # a stop can only make the fuel picture safer, so the filter has nothing
    # to say there.
    #
    # The promotion guard below is the other half, and it is needed because
    # `allocate_laps` front-loads a distance race: a one-stop from lap five
    # reads as [14, 1], which fails the fuel test on a half tank, and the
    # engineer came back recommending TWO stops off a split policy rather than
    # off anything the race had shown.
    runnable = [
        plan for plan in plans
        if _worth_stopping(plan, laps_left)
        and (plan.stops > current_stops
             or _first_stint_fits(plan, fuel_l, burn)
             # The run he is on, short by what a save covers.
             or (plan.stops == 0 and covered_short is not None))]
    if not runnable:
        # Every shape the model can build needs more fuel in the car than
        # there is. That is the urgent branch above arriving by another road.
        #
        # **The stop count it reports comes from the fuel, not from the plan
        # it has just rejected** (rule 12). This line read
        # `stops=max(1, current_stops)` until 20 Sep 2026, and `current_stops`
        # is `RaceCoordinator.stops_planned()` - the stops still in the FROZEN
        # plan. So the branch that had just found no plan fits answered "does
        # any plan fit?" by echoing that plan's own residue. At Bathurst Rd 8
        # it produced both of the race's two strategy sentences: "Recommend 3
        # stops from here" on lap 3, which was the approved plan read back
        # dressed as a recommendation, and "Recommend 2 stops from here" on
        # lap 22 with six laps left, when two stops was flatly impossible.
        #
        # And because it returned `laps_to_next_stop=None` with a sticky
        # URGENT, all three exits from `materially_different` were held shut
        # for eighteen laps: the stop count could not move, the stop-lap test
        # cannot fire on a None, and neither escalation nor de-escalation can
        # fire from URGENT to URGENT. The stop count and the laps to it are
        # both taken from the same arithmetic below, so the doors work again.
        stops, to_next, why = _stops_on_the_fuel(
            laps_left=laps_left, fuel_l=fuel_l, burn=burn,
            capacity_l=fuel_capacity_l)
        if stops == 0:
            # **The fuel is not what bound this**, so it may not be given as
            # the reason (rule 12). The tank covers the rest of the race and
            # every shape still failed - `_worth_stopping` on a short
            # remainder, or the promotion guard. Say that it needs a look
            # rather than naming a constraint that is not binding.
            #
            # **And no stop lap either, because no stop is being proposed.**
            # The two fields have to agree: `materially_different` compares
            # the absolute lap and the laps-from-now against each other, and
            # a pair that describes different stops is worse than a pair that
            # describes none.
            return Replan(URGENT,
                          f"no stop shape fits the race that is left, and "
                          f"{why} - the plan needs a look",
                          stops=None, confidence="low")
        return Replan(
            URGENT,
            f"no plan reaches the next stop on the fuel aboard; {why}",
            stops=stops, confidence="medium" if stops is not None else "low",
            next_stop_lap=(laps_done + to_next if to_next is not None
                           else laps_done + 1),
            laps_to_next_stop=to_next)

    best = runnable[0]
    current = next((p for p in runnable if p.stops == current_stops), None)
    if current is None and best.stops > current_stops:
        # His own shape did not survive the fuel filter and the only thing
        # left is a shape with MORE stops. That is the split policy talking,
        # not the race: `allocate_laps` puts almost everything in the first
        # stint, so a one-stop needs a fuller tank than a two-stop. The fuel
        # picture is genuinely tight and the urgent branch above and the fuel
        # call both own that conversation - this one stays out of it.
        return Replan(NONE, "the fuel is tight for the plan as split",
                      stops=current_stops, fuel_short_laps=covered_short)
    gain = (current.total_time_s - best.total_time_s) if current else 0.0
    to_next_stop = best.stints[0].laps if best.stops and best.stints else None
    next_stop = laps_done + to_next_stop if to_next_stop is not None else None

    if current is not None and gain <= WORTH_CHANGING_S:
        detail = "; ".join(reasons + ["the plan still wins"]) if reasons \
            else "on the plan"
        holding = (current.stints[0].laps
                   if current.stops and current.stints else None)
        return Replan(NONE, detail, stops=current_stops,
                      laps_to_next_stop=holding,
                      next_stop_lap=(laps_done + holding
                                     if holding is not None else None),
                      fuel_short_laps=covered_short)

    if current is None:
        # Nothing runnable at the stop count he is on, so there is no gain to
        # quote. Saying "0 seconds in it" put a measured-sounding nothing
        # against a plan that cannot be finished.
        detail = "; ".join(reasons + [
            f"the {current_stops}-stop plan is no longer runnable"])
    else:
        detail = "; ".join(reasons + [f"{gain:.0f} seconds in it"])

    if best.stops:
        detail = f"{detail} ({WEAR_IS_ASSUMED})"
    confidence = "medium"
    short = _laps_short(best, fuel_l, burn)
    if short > STILL_SHORT_EPSILON:
        # **Never a plan that quietly needs him to save.** The gap and the
        # lever are his to weigh, and the fold already speaks this way: "you
        # should make it - short-shift and lift, you're 0.4 short."
        detail += (f"; you'd be {short:.1f} laps short at this burn - "
                   f"short-shift and lift")
        # **And the size of the lever goes first**, because `spoken_reason`
        # keeps only the first clause and this one was being cut off.
        stint = best.stints[0].laps if best.stints else 0
        if stint and burn:
            where = "the flag" if not best.stops else "the stop"
            litres = math.ceil(short * burn / stint * 10.0 - 1e-9) / 10.0
            detail = (f"save {litres:.1f} litres a lap to make {where}; "
                      f"{detail}")
        confidence = "low"

    return Replan(
        RECOMMENDED,
        detail,
        stops=best.stops,
        stint_laps=tuple(stint.laps for stint in best.stints),
        stint_compounds=tuple(stint.compound for stint in best.stints),
        stint_tyres=tuple(None if index == 0 else True
                          for index in range(len(best.stints))),
        gain_s=gain,
        confidence=confidence,
        next_stop_lap=next_stop,
        laps_to_next_stop=to_next_stop,
    )


def _stops_on_the_fuel(*, laps_left: int, fuel_l: float | None,
                       burn: float | None, capacity_l: float | None
                       ) -> tuple[int | None, int | None, str]:
    """`(stops from here, laps to the first one, the arithmetic in words)`.

    **The expression that refuses every plan, made to answer for itself.**
    When nothing in `recommend`'s answer fits the tank, what bound the race is
    the fuel: the laps aboard, the laps a full tank buys, and the laps left.
    Those three produce the stop count, so the count George speaks is the one
    the decision was made on rather than a figure from the same family
    (CLAUDE.md rule 12).

    `None` for the count where a term is missing - a burn nobody has measured
    or a capacity nobody reported cannot be turned into a stop count, and
    `Replan.call` already has words for that ("The plan needs a look."). Never
    a guessed number and never a clamped one (rules 3 and 9).

    The laps to the first stop are the laps the fuel aboard actually covers,
    rounded down and never below one - he cannot box in the past. That is a
    bound on WHEN, not a measurement, so flooring it is not rule 9's clamp.
    """
    if not burn or burn <= 0 or fuel_l is None:
        return None, None, "no measured burn to size the fuel aboard against"
    aboard = fuel_l / burn
    to_next = max(1, int(aboard))
    said = f"{fuel_l:.0f} L aboard is {aboard:.1f} laps of {laps_left}"
    if not capacity_l or capacity_l <= 0:
        return None, to_next, f"{said}, and no tank size to plan a fill with"
    tank = capacity_l / burn
    short = laps_left - aboard
    if short <= 0:
        return 0, to_next, f"{said}, which reaches the flag"
    stops = int(math.ceil(short / tank - 1e-9))
    return stops, to_next, (f"{said}, and a full tank is {tank:.1f} - "
                            f"{stops} stop{'' if stops == 1 else 's'} from "
                            f"here at this burn")


def _first_stint_fits(plan, fuel_l: float | None,
                      burn: float | None) -> bool:
    """Whether the fuel already in the car covers this plan's first stint.

    **`recommend` bounds every stint by a full tank**, which is right for a
    race that starts on the grid and wrong for one re-planned on lap five with
    half a tank. Solved without this, a fifteen-lap run to the flag needing 51
    litres was ranked first with 50 aboard, and the engineer would have
    cancelled a stop the driver could not do without.

    Unknowns pass: a missing fuel level or burn rate is not evidence that a
    plan does not fit, and refusing every plan on a missing reading would take
    the engineer off the air exactly when he cannot see.
    """
    if fuel_l is None or not burn or burn <= 0 or not plan.stints:
        return True
    return (plan.stints[0].laps
            <= fuel_l / burn + FUEL_FITS_TOLERANCE_LAPS)


def _laps_short(plan, fuel_l: float | None, burn: float | None) -> float:
    """How far the fuel aboard falls short of this plan's first stint.

    Zero when it reaches. Anything above zero is a plan that only works if he
    saves, and the caller says so rather than letting the recommendation stand
    as though the tank covered it.
    """
    if fuel_l is None or not burn or burn <= 0 or not plan.stints:
        return 0.0
    return max(0.0, plan.stints[0].laps - fuel_l / burn)


def _worth_stopping(plan, laps_left: int) -> bool:
    """Whether there is enough race left for this many stops to mean anything.

    A zero-stop plan always passes - it is one stint and it is the race. What
    this rejects is the shape the search reaches for when the remainder gets
    short: three stops across four laps, which is an arithmetic answer to a
    question nobody asked.
    """
    if not plan.stops:
        return True
    return plan.stops * LAPS_PER_STOP < laps_left


def _remaining_race(inputs: RaceInputs, laps_left: int,
                    observed_fuel: float | None,
                    fuel_capacity_l: float | None,
                    observed_fuel_sd: float | None = None,
                    achieved_lap_ms: int | None = None,
                    lap_sigma_s: float | None = None) -> RaceInputs:
    """The rest of the race as its own planning problem.

    Re-planning the whole race would recommend a stop already taken. What is
    left is a shorter race starting now, **on what this race has shown rather
    than on what practice suggested** - the driver's instruction: *"at the end
    of every lap in a race the planner should be recalculating the plan for
    optimal based on what has and is happening in the race, current fuel
    usage, lap times."*

    Four figures are taken from the race in progress and each falls back to
    the plan's only where the race has not yet produced one:

    * **The burn.** Green laps only, and none of it until enough of them
      exist - `observed_fuel_per_lap` owns that gate.
    * **The burn's scatter**, which is what sizes every fill from here. It was
      practice's, and a margin is only cheap when the number under it belongs
      to the car actually running: at Watkins a lap of inherited margin was
      6.3 L still aboard at the flag and 6.3 seconds parked.
    * **The lap**, achieved and incidents-in - the same figure the coordinator
      already predicts the distance from, so the two can no longer disagree
      about how long a lap takes inside one crossing.
    * **The lap's sigma**, so `lap_count_firm` inside `recommend` is answered
      by this race rather than by practice. `state.laps_estimate_firm` was
      already live and the two were split-brained: the spoken fill and the
      modelled fill could size their margins off different noise floors.

    **A timed race has to have its clock shortened too.** `race_minutes` was
    left at the full limit while the lap count came down, so the model planned
    another whole race inside the remainder of this one: ten laps left came
    back as stints of 14 and 11. Adopted, that put the next stop on lap 29 of
    a 24-lap race and no box call was ever made again.

    ### Why the achieved lap may be used here, when lap time may not trigger

    The standing rule is that lap time never moves a stop count, because his
    lap-to-lap sigma is wider than the whole degradation band - a pace-derived
    verdict is a coin flip dressed as a finding. **That rule is about pace as
    a signal, and this is pace as a unit.**

    The laps left are counted upstream, by the app clock against this same
    achieved median, and handed in as `laps_left`. Converting them back into
    minutes with the same figure round-trips exactly: `minutes / lap` returns
    the laps that were put in, whatever the figure is. So the distance cannot
    move on pace here, and a faster median cannot invent or remove a stop.

    What it does correct is the price of a stop **in laps**, which is the
    currency a timed race is actually decided in. `clock_bound_stints` takes
    the pit loss out of the clock before dividing, so a 19-second stop costs
    more laps when the laps are quicker. Costing that against a practice lap
    the race has already beaten is a real distortion, and it always ran in the
    direction of making stops look cheaper than they were.
    """
    lap_ms = achieved_lap_ms or inputs.lap_time_ms
    minutes = None
    if inputs.is_timed and lap_ms > 0:
        minutes = laps_left * (lap_ms / 1000.0) / 60.0

    return replace(
        inputs,
        race_laps=laps_left,
        race_minutes=minutes,
        lap_time_ms=lap_ms,
        lap_time_sd_s=lap_sigma_s or inputs.lap_time_sd_s,
        fuel_per_lap_l=observed_fuel or inputs.fuel_per_lap_l,
        fuel_sd_l=observed_fuel_sd or inputs.fuel_sd_l,
        fuel_capacity_l=fuel_capacity_l or inputs.fuel_capacity_l,
        mandatory_stops=0,      # already satisfied, or not reachable now
    )
