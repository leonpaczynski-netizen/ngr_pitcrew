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

import math
from dataclasses import dataclass, field

from pitcrew.strategy.model import fuel_margin_l



# --- the measured wear call ------------------------------------------------
#
# **One pixel of the gauge is 3.3% of tyre life**, so every figure here is
# quantised to thirtieths and no arithmetic can make it finer. Everything below
# is sized against that quantum rather than against what would look tidy.

# Readings needed in this stint before a rate is fitted. Two points and a
# quantum of noise is a rate of anything you like; three is the fewest that can
# disagree with itself.
WEAR_MIN_READINGS = 3
# ...and the worst corner has to have actually moved this far across them.
# Two quanta: one is indistinguishable from a bar crossing a pixel boundary.
WEAR_MIN_SPAN = 0.067
# A reading older than this many laps is not describing the tyre he is on now.
# Three laps at a Monza-ish 5.6% a lap is most of a phase.
WEAR_MAX_STALENESS_LAPS = 3
# Where the stint ends. `analysis/wear.STINT_SAFETY_FACTOR`, restated rather
# than imported so the live path carries no offline dependency - and asserted
# equal to it in the tests, because two numbers that must agree and cannot see
# each other is how they come to disagree.
WEAR_STINT_LIMIT = 0.85
# Below this the projection is not worth saying: he is inside the margin the
# limit already builds in, and "about seven laps left" on a six-lap race is
# noise dressed as a finding.
WEAR_PROJECT_MAX_LAPS = 8
# A corner this far clear of the next-worst is a finding about that corner
# rather than about the set. Three quanta, so it cannot be quantisation.
WEAR_ASYMMETRY = 0.10

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
# **The gauge, not the model.** `TYRE` above is the retired
# modelled warning; this one rests on a transcription of GT7's own
# wear readout and is the only wear call that may speak plainly.
WEAR = "wear"
TYRE_TEMP = "tyre-temp"
STATUS = "status"
GREEN = "green"
STAY_OUT = "stay-out"
# **The answer to a saving the engineer asked for.** Not an
# instruction, so it is ranked below every call that is one - but it
# closes a loop the engineer opened, and an unclosed loop leaves the
# driver believing a shortfall was covered when it was not.
SAVING_RESPONSE = "saving-response"
CHEQUER = "chequer"
# **"Two to go" and "Last lap", which only an accurate clock makes sayable.**
# GT7's own race clock is not accurate - the driver measured it - so a timed
# race used to have no honest way to know whether there was time for another
# lap. With the app's own timer started at the green there is, and the call is
# made at the crossing that BEGINS the final lap, not after it.
LAPS_TO_GO = "laps-to-go"

# **The chequered flag outranks everything.** It used to sit second from
# last, below the box call - and on the night that mattered, "Box this lap.
# RS. Fuel to 27 litres." was voiced on the driver's chequered-flag crossing
# of a race he had just finished without stopping. The flag is the one call
# that is true exactly once and never again; nothing said instead of it can
# be more urgent.
# **`LAPS_TO_GO` sits below `FUEL_SHORT` deliberately.** Ranked above it, the
# two calls it makes - "two to go" and "last lap" - fall on exactly the two
# laps where a fuel shortfall is most actionable and least recoverable. In the
# measured race he saved 4.6 litres across laps 14 and 15 and finished with
# 1.79: under a ranking that puts the countdown first, "short-shift and lift"
# could not have been voiced on either of them. He can count laps himself; he
# cannot see the fuel arithmetic.
# **Every kind in `_candidates` must appear here.** `next_call` sorts on
# `URGENCY.index(kind)`, so a kind that is emitted but not ranked raises on the
# race path - which is exactly what `WEAR` did until a test asked for it.
URGENCY = (CHEQUER, BOX_NOW, FUEL_SHORT, LAPS_TO_GO, BOX_SOON,
           # **`WEAR` sits below the fuel calls and above temperature.** A car
           # out of fuel stops on the circuit; a car on worn tyres is still
           # moving, so fuel wins. But a measured wear figure beats an
           # inference drawn from how hot the rubber is, so it takes
           # precedence over `TYRE_TEMP`.
           FUEL_LONG, WEAR, TYRE_TEMP, GREEN, STATUS)

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
# The temperatures are per-lap frame means. The RANGE they are compared
# against is measured from this event's own practice laps (`race/temps.py`)
# and is a description of where he has been running the tyres - **not a
# window**. There is no published GT7 window and this app does not have one;
# the four-tier band that used to sit in `store/tyres` was real-world slick
# data and has been deleted. No measured range on file means the comparison is
# not made, never that a default is invented.

# More than this below the measured range's floor at the green is worth a
# warning; less is a normal out-of-the-garage state not worth a word.
TEMP_COLD_BELOW_C = 10.0
# Both axles still climbing by at least this much per lap reads as "cold at
# the green" even with no range on file - the relative form of the same call.
TEMP_RISING_C = 4.0
# An axle this far above its own steady mean, for this many consecutive laps,
# is a departure worth calling. The baseline is each axle against ITSELF:
# on some cars the rears run 8-11 degC hotter than the fronts all race, and
# that offset is the car's normal, never a finding.
TEMP_TREND_C = 5.0
TEMP_TREND_LAPS = 2

# --- up to temperature, and conserve: what the evidence will actually bear ---
#
# The driver asked for two things: *"I need to know when tyres are in optimal
# temps so I know I can start pushing in race, I need to know when they are
# approaching the top of optimal window so I can conserve."*
#
# **Neither can be built as a rule about temperature, and the reasons differ.**
#
# There is no push call, because there is no window to announce. Researched
# Aug 2026: no optimal tyre-temperature window has ever been published for GT7
# - not by Polyphony, not by the testing community, not by any telemetry
# project. The question was asked directly on GTPlanet in April 2025 and
# answered "I didn't test the lower range". PD's own manual documents the HUD
# tyre frame as monotonically redder with heat: no green, no in-window state,
# no thresholds. "You're in the window, push" would fabricate its lower edge,
# which is precisely how 85-110 degC - real-world slick data - came to be in
# this codebase. What replaces it is a call about the WARM-UP: the temperature
# stops rising, which is measured, in his own data, and needs no window at
# all. See `_up_to_temperature`.
#
# The conserve call ships, but **scoped to where its evidence exists rather
# than as a law**. The candidate law was the front-to-rear gap: on 17 of his
# own laps at Yas Marina in the Shelby, `rear mean - front mean` predicts lap
# time at +0.87 s per degree (t = 3.52), sign-stable, robust to leave-one-out
# and session-demeaning. Tested since across 95 clean laps at three cars and
# three circuits it does not generalise:
#
#     Yas / Shelby      +0.872 +/- 0.248   t = 3.52   CONSISTENT
#     Watkins / Huracan +0.778 +/- 0.398   t = 1.95   MARGINAL
#     Monza / Porsche   +0.011 +/- 0.077   t = 0.15   REFUTED (z = -11.4)
#
# Monza's gap range is WIDER than Yas Marina's on more than twice the sample,
# so the null is not a range artefact - and against a proper grip observable
# the two circuits invert, which per CLAUDE.md §4.1 is the finding and not
# something to average away.
#
# So the thresholds are **not constants here**. They come from a stored prior
# with a falsification status and an explicit list of scopes it may be spoken
# in (`store/tyres.GAP_PRIOR`), and `RaceState` carries them only when the car
# and circuit on track are one of those scopes. Everywhere else the call does
# not exist. The external 88/90/93 degC wear thresholds are kept as a labelled
# cross-check in the export and **nothing speaks on them**: they are untestable
# on his data, 0 of 318 Monza corner observations reaching 88 degC at all.

# **Smoothing: the lap mean, and nothing shorter.** Measured directly: a
# 10-second moving average removes only 21% of within-lap variation, because
# the signal is at lap scale. A fixed rear threshold toggles 3-4 times a lap
# on instantaneous values and 0.0-0.1 times over a 60-second window. The lap
# means this module is fed are already 60 s or more, so one of them is the
# right unit. The constant stays so the window can be widened without
# rewriting the call.
TEMP_SMOOTH_LAPS = 1

# **When the warm-up has finished**, which is a statement about a curve rather
# than about grip. Measured: the rear climbs +1.3 to +1.6 degC a minute while
# warming and +0.25 to +0.36 a minute once settled - roughly +2.7 degC and
# +0.5 degC respectively over a two-minute lap. One degree a lap splits the two
# populations with margin either side.
TEMP_PLATEAU_C_PER_LAP = 1.0
# How far a settled lap may drift DOWNWARD and still be settled. Anything
# below this is a cool-down - he is backing off, or the set is going away -
# and neither is a warm-up finishing. Half the upward threshold, and well
# inside the measured 4 degC a saving lap sheds.
TEMP_SETTLED_DRIFT_C = 0.5
# Two consecutive lap-to-lap rises under that, so one flat lap in the middle of
# a warm-up cannot call it settled. Needs three lap means to evaluate at all.
TEMP_PLATEAU_LAPS = 2

# **Hysteresis is the gap between the two thresholds**, 1.3 degC of it, plus a
# minimum lap count. Measured: backing off cools the rear at about 2 degC/min
# against 0.25 degC/min of heating at pace - eight times faster - so one saving
# lap can genuinely unwind several laps of build-up, and two laps is long
# enough to be a real change rather than a flap.
TEMP_REARM_MIN_LAPS = 2
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
    # **The rpm the beep should come down by, when the call asks for a
    # short-shift.** None on every other call, and None is the instruction to
    # stop short-shifting rather than the absence of one.
    #
    # It exists because the engineer has been asking for a short-shift that
    # nothing delivered: `ShiftBeep.short_shifting` is read in two places and
    # was set True nowhere outside the tests, so "Short-shift 450" moved no
    # beep, and `laps.short_shift_rpm` recorded 0.0 on all 179 laps that have
    # a value. He was asked to short-shift with no cue, and the app then had
    # no record of having asked.
    short_shift_drop_rpm: float | None = None

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
    # **Lap-to-lap scatter on the burn, which is what sizes the fill.** The
    # fill used to be the stint plus a flat lap; at Watkins on 17 Aug 2026
    # that was 6.3 L still aboard at the flag and, at the measured 1.001 L/s,
    # 6.3 seconds of standing still - the difference between coming out clear
    # and coming out into a fight. None until enough green laps exist to take
    # an sd from, and then `strategy.model.fuel_margin_l` falls back to the
    # flat lap and says so.
    fuel_sd_l: float | None = None
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
    # The compound on the car. Carried for the record and for the export's
    # cross-check; **no live call rests on a compound temperature threshold**,
    # because the only one that exists is untestable on this driver's data.
    tyre_compound: str | None = None
    # **The front-to-rear gap association, but only where it was measured.**
    # None everywhere else, and None means the conserve call does not exist -
    # see the note above the constants. Set at arming from
    # `store/tyres.gap_association_for`, which answers for this car at this
    # circuit and refuses everywhere the prior was refuted or never tested.
    temp_gap_conserve_c: float | None = None
    temp_gap_quiet_c: float | None = None
    temp_gap_front_floor_c: float | None = None
    temp_gap_s_per_c: float | None = None
    # The lap the conserve call was last made, for the re-arm hysteresis.
    temp_conserve_lap: int | None = None
    # --- tyre wear, MEASURED off the HUD gauge (telemetry/hud.py) ---
    # (lap, {corner: fraction worn}) per lap that carried a gauge reading.
    # **Measured, not modelled** - it is a transcription of the game's own
    # readout - which is why the calls resting on it may speak plainly where
    # the retired `_tyre` had to hedge three times in one sentence.
    #
    # **The reading lags its lap by one.** The sampler is asked at the crossing
    # and answers on a worker thread a moment later, so the figure filed
    # against lap N reaches the state during lap N+1. That is why staleness is
    # measured in laps and tolerated up to `WEAR_MAX_STALENESS_LAPS` rather
    # than required to be current.
    #
    # Cleared on a confirmed tyre change: a fresh set's wear starts at its own
    # zero, and a rate fitted across a stop describes neither set.
    wear_history: list[tuple[int, dict[str, float]]] = field(default_factory=list)
    # Which wear occasions were said this stint: "limited", "cliff",
    # "asymmetry". Each at most once, like the temperature occasions.
    wear_said: set[str] = field(default_factory=set)
    # Which tyre-temp occasions were said this stint: "cold", "up-to-temp",
    # "conserve", "trend-front", "trend-rear". Each is said at most once per
    # stint, and the conserve call can be re-armed within one - see
    # `_tyre_temp`.
    temp_said: set[str] = field(default_factory=set)
    # The estimated laps still to run, from the app race clock. **An
    # estimate**: it is the time left divided by the median lap, ceiling'd,
    # because GT7 drops the flag at the first crossing after the clock. None
    # for a race that is not run to a clock, or before the estimate exists.
    laps_to_go_estimate: int | None = None
    # Whether the app timer and the sum of GT7's own lap times still agree.
    # None before a second lap can corroborate the first; False means the
    # estimate rests on the lap-time sum and the call says so.
    clock_corroborated: bool | None = None
    # **Crossings the clock believes were missed.** Non-zero changes what the
    # lap-count calls should say about themselves: the clock folds a dropped
    # lap into its offset and keeps the APP TIMER as the reference, so a call
    # that blames the disagreement on the two measures drifting is describing
    # the wrong fault - and naming the pit lane is something he can weigh.
    laps_dropped: int = 0
    # Whether the lap-count estimate is resolvable at all. Measured: in the
    # first four crossings of a 30-minute race the median only had to be wrong
    # by 0.12-0.66 s to change the answer, against a lap-time spread of
    # 2.04 s. False means no lap count is spoken - not a count with a hedge on
    # it, no count.
    laps_estimate_firm: bool = False
    # **Laps still to run once the stops still to come are out of the clock.**
    # `laps_total` counts crossings and a crossing still happens on the lap a
    # stop is taken, so the flag and the run-in keep reading that. This is the
    # fuel path's own figure: a stop is a minute of clock that covers no
    # ground, and counting it as racing buys a lap of fuel that gets parked.
    # None where no stop is pending or nothing measured the loss, and then the
    # fill falls back to `laps_remaining` exactly as before.
    laps_after_stops: int | None = None
    said: list[str] = field(default_factory=list)
    # Tags of the tagged calls already made, for the kinds that have several
    # distinct occasions. `temp_said` is the per-stint version for tyre
    # temperature (cleared at a stop); this one is for the race.
    said_tags: set[str] = field(default_factory=set)
    # What each kind was last said at, so a call can be made again when it has
    # got worse. Kept beside `said` rather than inside it because `said` is
    # read as a plain list of kinds in half a dozen places.
    said_at: dict[str, float] = field(default_factory=dict)

    def laps_remaining(self) -> int | None:
        """Laps still to run, corrected for any crossing that went missing.

        **`self.lap` is the app's count, and it can be short.** GT7 takes the
        car over at the pit entry and places it in the box, and the crossing
        inside that sequence does not reach the app - so a pit lap arrives as
        one lap that covered two. Measured: every Monza race on file recorded
        26 rows for 27 laps driven, the pit row spanning 1.94 laps of distance
        with 5.50 L gone against a 5.55 L lap.

        The clock already detects this and folds the missing time into its
        offset, but `laps_dropped` reached exactly one place - the wording of
        the run-in call - and never the arithmetic. So the count stayed one
        light, and **one light here is one lap of fuel too many at the stop.**
        At 1 L/s that is about six litres and six seconds standing still, on a
        driver who will not carry a spare lap of fuel precisely because he
        counts the stop in seconds.

        Corrected here rather than at each caller, because this is the
        quantity that is wrong and every caller of it inherits the error.
        """
        if self.laps_total is None:
            return None
        # A dropped crossing means more laps are behind him than the app
        # counted, so fewer remain.
        counted = self.lap + max(0, self.laps_dropped)
        return max(0, self.laps_total - counted)

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

    # The last lap on which the engineer said anything at all. None until he
    # has: a race that has not started is not a race that has gone quiet.
    last_said_lap: int | None = None

    def note_wear(self, lap: int, wear: dict[str, float] | None) -> None:
        """File a gauge reading against a lap. Ignores a repeat of one lap.

        Repeats matter because with the sampler free-running the same held
        reading can be offered at two crossings, and a duplicated point would
        flatten the fitted rate towards zero - which reads as a tyre that has
        stopped wearing, the one direction this must never err in.
        """
        if not wear:
            return
        present = {corner: value for corner, value in wear.items()
                   if value is not None}
        if not present:
            return
        if self.wear_history and self.wear_history[-1][0] >= lap:
            return
        self.wear_history.append((lap, present))

    def note_temps(self, lap: int, front_c: float, rear_c: float) -> None:
        """One completed lap's measured axle means, in order driven."""
        self.temp_history.append((lap, front_c, rear_c))

    def laps_since_anything_said(self) -> int | None:
        """Laps since the engineer last spoke, or None if he never has.

        **The heartbeat's measure.** `_status` used to fire on `lap % 5`,
        which is a metronome: it spoke whether or not anything else had, and
        it collided with the run-in, which speaks every lap of the last five.
        What it is for is proving the engineer is still there - and that is a
        function of silence, not of the lap number.
        """
        if self.last_said_lap is None:
            return None
        return max(0, self.lap - self.last_said_lap)

    def record(self, call: Call) -> None:
        """Remember a call was made, and how bad it was when it was."""
        # **Every kind, including the ones that say nothing new.** The
        # heartbeat measures silence, so a lap on which anything at all was
        # said is not silent - otherwise the status call would answer a
        # quietness that never happened.
        self.last_said_lap = call.lap
        if call.kind not in self.said:
            self.said.append(call.kind)
        if call.severity is not None:
            self.said_at[call.kind] = call.severity
        if call.tag:
            self.said_tags.add(call.tag)
        if call.kind == TYRE_TEMP and call.tag:
            self.temp_said.add(call.tag)
            if call.tag == "conserve":
                self.temp_conserve_lap = call.lap


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
    if call.kind == LAPS_TO_GO:
        # Two occasions, "two to go" and "last lap", and the first must not
        # swallow the second. Each self-suppresses on its own tag.
        return call.tag not in state.said_tags
    margin = WORSE_BY.get(call.kind)
    was = state.said_at.get(call.kind)
    if margin is None or call.severity is None or was is None:
        return False
    return call.severity >= was + margin


def _candidates(state: RaceState) -> list[Call | None]:
    return [
        _chequer(state),
        _laps_to_go(state),
        _green(state),
        _box_now(state),
        _box_soon(state),
        _fuel(state),
        # **`_tyre` is not here, deliberately.** It said "Tyres are at the end
        # of their window. Modelled at 92%." - a sentence whose first clause is
        # a flat assertion about the tyres, built on wear-per-lap times laps.
        # CLAUDE.md §3.3 says there is no wear channel and §4.5 says nothing
        # derived may be presented as measured; the word "Modelled" was doing
        # all the work in between. It was also the only call that stacked three
        # hedges at once.
        #
        # Retiring it costs nothing measurable: across the five races on file
        # it fired **zero times in 74 recorded calls**. And it is no longer the
        # best available - `telemetry/hud.py` reads the gauge itself.
        #
        # **`_wear` is what replaced it**, and it sits here rather than beside
        # the box calls on purpose. Those reason about fuel and are right to
        # outrank it: a car out of fuel stops on the circuit, a car on worn
        # tyres is still moving. But it ranks above temperature, because a
        # measured wear figure beats an inference from how hot the rubber is.
        _wear(state),
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


def _laps_to_go(state: RaceState) -> Call | None:
    """"Two to go" and "Last lap" - sayable at last, and correct.

    A timed race used to have no honest way to know whether there was time for
    another lap: GT7's own clock is the only source and the driver measured it
    as inaccurate, so the app counted down a lap estimate derived from the
    approved plan and stretched it when the packet disagreed. With the app's
    own timer started at the green the question has an answer, and the answer
    is worth saying at the crossing that BEGINS the final lap - after it, the
    information is worth nothing.

    It is still an estimate: the time left divided by a median lap. So when
    the app timer and the sum of GT7's exact lap times have stopped agreeing,
    the call says which of the two it now rests on rather than sounding like a
    regulation.
    """
    if state.finished or state.in_pit:
        return None
    to_go = state.laps_to_go_estimate
    if to_go is None or not 1 <= to_go <= 2:
        return None
    call = "Last lap." if to_go == 1 else "Two to go."
    if state.laps_dropped:
        # **A missed crossing, not a drift.** The clock folds the missing lap
        # into its offset and stays on the app timer, so "on lap times" would
        # name the measure it is NOT using. Both races so far missed the
        # crossing in the pit lane, so this is the likely branch, and on the
        # last lap he needs to know the count is sound rather than wonder.
        # MEDIUM, not HIGH: the count is sound but the lap NUMBER is one
        # light, and a call that sounded like a regulation would be claiming
        # more than the clock knows.
        reason = "A crossing was missed in the box - counted on the timer."
        confidence = MEDIUM
    elif state.clock_corroborated is False:
        # The two measures have diverged and the estimate now rests on the
        # lap-time sum. Said out loud: "unconfirmed" is a word he can act on.
        reason = "On lap times - the race clock and the laps disagree."
        confidence = MEDIUM
    else:
        reason = "On the clock."
        confidence = HIGH
    return Call(LAPS_TO_GO, state.lap, call, reason, confidence,
                tag=f"to-go-{to_go}")


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


def _laps_after_this_stop(state: RaceState) -> int | None:
    """Laps still to run **once the car leaves the box**, or None.

    `laps_remaining` counts every lap the flag is still waiting on, and while
    the car is stationary in a pit box the lap in progress is one of them - it
    is the lap the stop is happening on. The fill does not have to cover it:
    most of it is already behind the car, and what is left of it is the exit.

    Counting it is a whole lap of fuel the driver parks for. At Monza on
    19 Aug 2026 the in-box call asked for 94 L where the stint needed 78, and
    this was the second of the two reasons - the clock's late green was the
    first. One litre is one second stationary at the measured 1.002 L/s.
    """
    remaining = (state.laps_after_stops if state.laps_after_stops is not None
                 else state.laps_remaining())
    if remaining is None:
        return None
    return max(0, remaining - 1) if state.in_pit else remaining


def fuel_target_l(state: RaceState) -> float | None:
    """What the tank should read at pit exit, or None if nothing can size it.

    Split out of `_fuel_instruction` so the number and the sentence cannot
    drift apart. The in-box refuel watch needs the figure itself - it says it
    again with the hose in, and then calls the release when the tank reaches
    it - and a second copy of this arithmetic is how the engineer ends up
    telling him two different numbers about the same stop.

    Unclamped: the caller decides what to do about a target the tank cannot
    hold or one already covered, because those two produce different sentences
    and the watch and the box call answer them differently.
    """
    if not state.fuel_per_lap_l or state.laps_remaining() is None:
        return None
    if state.next_stint_laps is not None:
        after_stop = state.next_stint_laps
        remaining = _laps_after_this_stop(state)
        if (state.further_stop_planned is False and remaining is not None
                and remaining > after_stop):
            after_stop = remaining
    elif state.stint_ends_on_lap is not None:
        after_stop = (state.laps_total or 0) - state.stint_ends_on_lap
    else:
        after_stop = state.laps_remaining()
    margin_l, _ = fuel_margin_l(after_stop, state.fuel_per_lap_l,
                                sd_l=state.fuel_sd_l,
                                timed=state.race_minutes is not None,
                                lap_count_firm=state.laps_estimate_firm)
    return after_stop * state.fuel_per_lap_l + (margin_l or 0.0)


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
    # **The sizing lives in `fuel_target_l`**, because the in-box refuel watch
    # says the same figure again with the hose in and two copies of this
    # arithmetic is how the engineer tells him two different numbers about one
    # stop. What stays here is everything about the SENTENCE: the clamps, and
    # what each of them means when it binds.
    #
    # The pieces it folds in, kept here because this is where a reader looks
    # for them: a stale plan must not size the fill - when no further stop is
    # planned the next stint runs to the flag, so a stint shorter than the
    # laps actually remaining would send him back out to run dry - and the
    # margin is sized rather than assumed, a flat lap only where the burn's
    # scatter is unmeasured or the race runs to the clock.
    litres = fuel_target_l(state)
    if litres is None:
        return ""

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
    # **Round up, never to nearest.** The spoken figure is what he dials in,
    # so rounding 50.4 down to 50 quietly spends 0.4 L of a margin that is now
    # measured in tenths rather than in whole laps. Up costs at most a litre -
    # one second at Watkins' rate - and down can cost the race.
    return f"Fuel to {math.ceil(litres):.0f} litres."


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
            f"you're {abs(gap):.1f} short.",
            short_shift_drop_rpm=drop)
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
                    severity=-gap,
                    # Only where a drop was named. "Short-shift and lift into
                    # the slow corners" is the lever without a number, and
                    # moving the beep by a figure nobody measured would be
                    # inventing the number the call deliberately withheld.
                    short_shift_drop_rpm=drop or None)
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


# --- the measured wear call -------------------------------------------------
#
# **This is the call the app exists to be able to make.** CLAUDE.md 3.3 calls
# the absent wear channel the single most consequential fact in the document,
# and 5 builds the whole strategy engine around planning for a quantity the
# game will not report. The HUD gauge is the game's own readout of it, and
# `telemetry/hud.py` transcribes it, so for the first time a wear call can name
# a number without a model underneath it.
#
# It says at most one of three things, each once a stint:
#
# * **limited** - the tyres run out before the fuel does. Only a measurement
#   can establish this, and it is the one that changes the plan: every box call
#   above it reasons about fuel, so without this a tyre-limited stint is run to
#   a fuel-limited schedule.
# * **cliff** - the worst corner is past the stint limit. An instruction.
# * **asymmetry** - one corner is going first, named. Not an instruction to
#   pit; an instruction about brake balance, which is adjustable mid-race.


def _wear_worst(wear: dict[str, float]) -> tuple[str, float]:
    """The corner that ends the stint, and how worn it is.

    **The worst single corner, never an axle mean.** A car eating one corner is
    exactly what open tuning without BoP produces - his own eight gauge
    readings put RL worst every time - and averaging it with its healthy pair
    halves the number that decides when to stop.
    """
    return max(wear.items(), key=lambda kv: kv[1])


def _wear_rate(state: RaceState) -> float | None:
    """Fraction of the worst corner consumed per lap, or None.

    A least-squares slope over this stint's readings. None where there are too
    few, where the gauge has not moved far enough to be distinguishable from
    its own quantisation, or where the fit comes out flat or negative - a tyre
    that is not wearing is a reading problem, not a finding.
    """
    points = [(lap, _wear_worst(wear)[1]) for lap, wear in state.wear_history]
    if len(points) < WEAR_MIN_READINGS:
        return None
    if points[-1][1] - points[0][1] < WEAR_MIN_SPAN:
        return None
    n = len(points)
    mean_lap = sum(lap for lap, _ in points) / n
    mean_worn = sum(worn for _, worn in points) / n
    denominator = sum((lap - mean_lap) ** 2 for lap, _ in points)
    if denominator <= 0:
        return None
    slope = sum((lap - mean_lap) * (worn - mean_worn)
                for lap, worn in points) / denominator
    return slope if slope > 0 else None


def _wear_laps_left(state: RaceState) -> tuple[float, str, float, float] | None:
    """(laps to the stint limit, worst corner, what it READ, where it IS now).

    **The last two are different numbers and the difference is the point.**
    The reading is a transcription of the game's own gauge and may be spoken
    plainly. The carry-forward is the reading plus the fitted rate across the
    laps since - a projection, and CLAUDE.md 4.5 forbids presenting one as a
    measurement. So the decisions below are taken on the projection, because
    that is where the tyre actually is, and every number said out loud is the
    reading, because that is what was measured. Conflating them had the
    engineer saying "RL measured at 99 percent" off a gauge that read 88.
    """
    if not state.wear_history:
        return None
    lap, wear = state.wear_history[-1]
    if state.lap - lap > WEAR_MAX_STALENESS_LAPS:
        # The gauge stopped reading. Silence is the honest answer: a
        # projection from a reading four laps old is about a tyre he was on,
        # not the one he is on.
        return None
    rate = _wear_rate(state)
    if rate is None:
        return None
    corner, worn = _wear_worst(wear)
    consumed = worn + rate * max(0, state.lap - lap)
    return (WEAR_STINT_LIMIT - consumed) / rate, corner, worn, consumed


def _wear(state: RaceState) -> Call | None:
    """What the gauge says, when it says something he can act on."""
    if state.in_pit or state.finished or _crossing_the_line(state):
        return None
    projection = _wear_laps_left(state)
    if projection is None:
        return None
    laps_left, corner, reading, consumed = projection
    name = corner.upper()

    # --- past the limit. An instruction, and the reading is enough on its own.
    if consumed >= WEAR_STINT_LIMIT and "cliff" not in state.wear_said:
        state.wear_said.add("cliff")
        return Call(
            WEAR, state.lap,
            "Box this lap.",
            f"{name} measured at {reading * 100:.0f} percent.",
            HIGH,
            severity=consumed)

    # --- the tyres run out before the fuel does.
    fuel_laps = state.laps_of_fuel()
    if (fuel_laps is not None and "limited" not in state.wear_said
            and 0 < laps_left <= WEAR_PROJECT_MAX_LAPS
            and laps_left + 1 < fuel_laps):
        # **+1 before it is a finding.** The two figures are a fitted gauge
        # slope and a fuel burn, and inside a lap of each other the ordering is
        # noise - which would have him stopping early on the strength of it.
        state.wear_said.add("limited")
        # **Rounded DOWN, and never below one.** The projection is a fitted
        # slope on a gauge quantised to thirtieths, and CLAUDE.md 5.1 is
        # explicit that overshooting the cliff costs far more than
        # undershooting it. Rounding to nearest would spend that asymmetry on
        # tidiness.
        whole = max(1, int(laps_left))
        return Call(
            WEAR, state.lap,
            f"Tyres are the constraint, not fuel. About {whole} "
            f"lap{'' if whole == 1 else 's'} left on them.",
            f"{name} at {reading * 100:.0f} percent, measured.",
            MEDIUM,
            severity=consumed)

    # --- one corner going first. A balance call, not a pit call.
    ordered = sorted(state.wear_history[-1][1].values(), reverse=True)
    if (len(ordered) >= 2 and "asymmetry" not in state.wear_said
            and ordered[0] - ordered[1] >= WEAR_ASYMMETRY):
        state.wear_said.add("asymmetry")
        # **Rearward only.** Moving the balance forward is a standing refusal
        # of his, and the axle this fires on is his measured pattern anyway:
        # every gauge reading on file has put a rear corner worst.
        toward = "rearward" if name.startswith("R") else "forward"
        if toward == "forward":
            # Named without a direction rather than told to do the one thing
            # he does not do. The finding is still worth having.
            return Call(
                WEAR, state.lap,
                f"{name} is going first.",
                f"{ordered[0] * 100:.0f} percent against "
                f"{ordered[1] * 100:.0f}, measured.",
                HIGH,
                severity=ordered[0])
        return Call(
            WEAR, state.lap,
            "Brake balance one click rearward.",
            f"{name} is going first - {ordered[0] * 100:.0f} percent "
            f"against {ordered[1] * 100:.0f}, measured.",
            HIGH,
            severity=ordered[0])
    return None


def _smoothed_axles(history: list[tuple[int, float, float]]
                    ) -> tuple[float, float]:
    """The last few laps' axle means, averaged.

    One lap is not a working temperature. The quali coach hit the same thing
    from the other side - the racing line reads systematically cool, so a
    single reading understates - and settled on a rolling mean. Here the
    inputs are already lap means, so the smoothing is over laps rather than
    frames: it exists so that one hot lap in an otherwise happy set cannot ask
    the driver to back off, and one cool one cannot tell him to push.
    """
    window = history[-TEMP_SMOOTH_LAPS:]
    return (sum(entry[1] for entry in window) / len(window),
            sum(entry[2] for entry in window) / len(window))


def _tyre_temp(state: RaceState) -> Call | None:
    """The one tyre channel GT7 broadcasts, spoken sparingly.

    Four occasions, each at most once per stint, and each one built on
    something that was actually measured:

    * **Cold at the green** - the first lap's means sit well below the range
      this event's own practice ran in. A statement about where he has been,
      not about where he should be. With no measured range on file the
      relative form is allowed instead: both axles still climbing hard after
      lap one.
    * **Up to temperature** - the warm-up curve has flattened. See
      `_up_to_temperature` for why this is deliberately NOT a push call.
    * **Conserve** - the front-to-rear gap has opened, at a car and circuit
      where that association has actually been measured. See `_conserve`;
      everywhere else this occasion does not exist.
    * **A departure from the axle's own baseline**, kept only for the case
      where this event has no measured range at all. The rears running
      8-11 degC hotter than the fronts is this car's normal thermal balance
      and must never fire anything. Fronts going first may suggest brake
      balance rearward - never, under any circumstances, forward: a standing
      driver instruction.
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
    smooth_front, smooth_rear = _smoothed_axles(history)

    # (a) Cold at the green.
    if "cold" not in state.temp_said:
        if wf and wr and len(history) == 1:
            if (front < wf[0] - TEMP_COLD_BELOW_C
                    or rear < wr[0] - TEMP_COLD_BELOW_C):
                if state.temp_laps_to_window:
                    n = state.temp_laps_to_window
                    reason = (f"About {n} lap{'' if n == 1 else 's'} to come "
                              f"up.")
                else:
                    reason = "Below where you've been running them."
                return Call(TYRE_TEMP, state.lap, "Tyres cold.", reason,
                            tag="cold")
        elif wf is None and len(history) == 2:
            # No measured range yet: the only allowed form is relative -
            # both axles still climbing hard says lap one started cold.
            _, f0, r0 = history[0]
            if front - f0 >= TEMP_RISING_C and rear - r0 >= TEMP_RISING_C:
                return Call(TYRE_TEMP, state.lap, "Tyres cold.",
                            "Still coming up to temperature.", MEDIUM,
                            tag="cold")

    _rearm_conserve(state, smooth_front, smooth_rear)
    conserve = _conserve(state, smooth_front, smooth_rear)
    if conserve is not None:
        return conserve
    settled = _up_to_temperature(state, history)
    if settled is not None:
        return settled

    # (d) Each axle against its OWN established baseline.
    #
    # **The rear half of this is the fallback wherever the gap association is
    # not speakable**, which is everywhere except one car at one circuit. It
    # was briefly deleted in favour of the gap call, and that left the rear
    # axle with no thermal voice at all on two of the three cars on file -
    # for a driver whose rears are the loaded axle. It is a different
    # measurement, not a weaker one: it compares the rear against ITS OWN
    # steady mean, so the 8-11 degC front-to-rear offset that is this car's
    # normal was never a problem for it, and it needs no external prior.
    # Where the gap IS speakable the conserve call has already said it better
    # and this stands down.
    #
    # The front half runs either way: a front climbing towards the rear
    # SHRINKS the gap, so the conserve call can never see it, and the lever it
    # names is a different one.
    #
    # The baseline is positional within THIS set's history - its first
    # `TEMP_WARMUP_LAPS` entries are its warm-up and stay out - never the
    # absolute race lap: the history is cleared on a tyre change, and a
    # lap-number filter once let a set fitted mid-race baseline itself on its
    # own cold laps, reading its normal steady temperature as heating.
    recent = history[-TEMP_TREND_LAPS:]
    steady = history[TEMP_WARMUP_LAPS:-TEMP_TREND_LAPS]
    if len(recent) < TEMP_TREND_LAPS or len(steady) < TEMP_BASELINE_MIN_LAPS:
        return None
    base_front = sum(e[1] for e in steady) / len(steady)
    base_rear = sum(e[2] for e in steady) / len(steady)
    # Rears first: they are the loaded axle and the traction warning is the
    # more expensive one to miss.
    if ("trend-rear" not in state.temp_said
            and state.temp_gap_conserve_c is None
            and all(e[2] - base_rear >= TEMP_TREND_C for e in recent)):
        up = rear - base_rear
        return Call(TYRE_TEMP, state.lap, "Rears heating.",
                    f"Up {up:.0f} on their normal. Mind traction.",
                    tag="trend-rear")
    if "trend-front" not in state.temp_said:
        if all(e[1] - base_front >= TEMP_TREND_C for e in recent):
            up = front - base_front
            return Call(TYRE_TEMP, state.lap, "Fronts heating.",
                        f"Up {up:.0f} on their normal. "
                        "Brake balance one click rearward.",
                        tag="trend-front")
    return None


def _up_to_temperature(state: RaceState,
                       history: list[tuple[int, float, float]]) -> Call | None:
    """The warm-up has finished. **Deliberately not a push call.**

    The driver asked to be told when the tyres are in their optimal window so
    he can start pushing. **That call cannot be built honestly, and the reason
    is that the window does not exist to be announced.** Nobody has published
    an optimal tyre-temperature window for GT7 - the question was put to
    GTPlanet in April 2025 and answered "I didn't test the lower range", and
    it has not been answered since. PD's own manual describes the HUD tyre
    frame as simply redder with heat: no green, no in-window state, no
    thresholds. Saying "you're in the window, push" would invent its lower
    edge, and inventing a lower edge is exactly how 85-110 degC - real-world
    slick data - ended up in this codebase pretending to be a GT7 finding.

    What CAN be measured, from his own laps and nothing else, is the moment
    the temperature stops rising: the warm-up curve flattening. That is a
    statement about a curve, and it is what this says. It carries the numbers
    so he can decide what to do with them; it does not tell him to push.

    Once per stint, and never re-armed inside one. A set only warms up once.
    """
    if "up-to-temp" in state.temp_said:
        return None
    if len(history) < TEMP_PLATEAU_LAPS + 1:
        return None
    recent = history[-(TEMP_PLATEAU_LAPS + 1):]
    rises = [(later[1] - earlier[1], later[2] - earlier[2])
             for earlier, later in zip(recent, recent[1:])]
    # **One-sided.** A warm-up finishing is a rise that has stopped rising,
    # not a set that is cooling: tested on an absolute value, a lap he spent
    # backing off - measured at about 2 degC a minute, four degrees over a
    # lap - satisfied "up to temperature" while the tyres were on their way
    # down. A few tenths either way is a settled lap and is allowed.
    if not all(-TEMP_SETTLED_DRIFT_C <= d < TEMP_PLATEAU_C_PER_LAP
               for rise in rises for d in rise):
        return None
    _, front, rear = history[-1]
    return Call(TYRE_TEMP, state.lap, "Tyres are up to temperature.",
                f"Fronts {front:.0f}, rears {rear:.0f}, settled.",
                tag="up-to-temp")


def _conserve(state: RaceState, front: float, rear: float) -> Call | None:
    """Ease the rears, on an association measured at THIS car and circuit.

    **The gate is the scope, not the number.** `temp_gap_conserve_c` is set
    only where the front-to-rear gap has actually been fitted to his own laps
    and come out significant - one car at one circuit today. It is None
    elsewhere, including at a circuit where the same fit came back flat, and
    None means this call does not exist. Shipping it as a general threshold
    would be shipping a law the data refutes.

    **The front floor is not decoration.** The gap conflates two mechanisms -
    a cold front and a hot rear produce the same number, and one practice lap
    reads 8.3 degC because the front was at 67. Without it the call fires on
    an out lap and asks him to back off a set that is still warming up.

    The words are an association from his own laps at this circuit, never a
    law and never a physical optimum: causality is not established, a sliding
    lap heats tyres, and incident seconds correlate with peak rear temperature
    at r = 0.84. Confidence is MEDIUM at best, and it is worth saying at all
    because it is actionable inside a lap - measured, backing off cools the
    rear about eight times faster than pushing heats it.
    """
    if "conserve" in state.temp_said:
        return None
    threshold = state.temp_gap_conserve_c
    floor = state.temp_gap_front_floor_c
    if threshold is None or floor is None:
        return None
    gap = rear - front
    if gap < threshold or front < floor:
        return None
    slope = state.temp_gap_s_per_c
    worth = (f" - about {slope:.1f} a lap per degree on your own laps here"
             if slope else "")
    return Call(
        TYRE_TEMP, state.lap, "Ease the traction out of the slow corners.",
        f"Rears {gap:.0f} over the fronts{worth}.",
        MEDIUM, tag="conserve")


def _rearm_conserve(state: RaceState, front: float, rear: float) -> None:
    """Let the conserve call be said again, once the set has actually settled.

    **Both conditions, not either.** A margin alone would re-arm on the noise
    of one cooler lap; a lap count alone would re-arm a set still sitting on
    the ceiling. So the gap has to come back under the prior's quiet
    threshold - 1.3 degC of hysteresis below the trigger - AND
    `TEMP_REARM_MIN_LAPS` have to have passed. Two laps rather than more because the measured cool-down is
    fast: about 2 degC a minute when he backs off, eight times the rate it
    heats at pace, so one saving lap is a real change and not a flap.

    Mutates `temp_said`, which is what `record` writes. The re-arm is
    idempotent, so calling `next_call` twice for the same lap - as the tests
    do - cannot double-arm anything.
    """
    if "conserve" not in state.temp_said or state.temp_conserve_lap is None:
        return
    if state.lap - state.temp_conserve_lap < TEMP_REARM_MIN_LAPS:
        return
    quiet = state.temp_gap_quiet_c
    if quiet is None or rear - front > quiet:
        return
    state.temp_said.discard("conserve")
    state.temp_conserve_lap = None


def _status(state: RaceState) -> Call | None:
    """Proactive reassurance, rarely. Silence should mean nothing to report.

    **On silence, not on a clock.** This fired every fifth lap regardless, which
    made it a metronome rather than a heartbeat: it collided with the run-in,
    which speaks every lap of the last five, and it spent a call saying two
    numbers he can already read on a lap where something else may well have
    been said. Now it speaks only when nothing has been said for a while, which
    is the thing it was always for - proving the engineer is still there.
    """
    if state.lap < 1 or state.finished or state.in_pit:
        return None
    if _crossing_the_line(state):
        return None
    since = state.laps_since_anything_said()
    if since is None or since < STATUS_EVERY_LAPS:
        return None
    remaining = state.laps_remaining()
    where = f"P{state.position}." if state.position else ""
    # A timed race has no lap count to count down: the distance follows from
    # the clock and the pace, so the figure is an estimate and is spoken as
    # one - **and only once it can be resolved at all.** Measured on a real
    # 30-minute race, the estimate at the first four crossings would have
    # flipped on a median error of 0.12-0.66 s against a 2.04 s spread. In
    # that window the honest output is the position and nothing else: a lap
    # count no better than a coin toss, spoken with "about" in front of it, is
    # still a lap count he will plan around.
    about = "about " if state.race_minutes else ""
    unresolved = state.race_minutes and not state.laps_estimate_firm
    left = (f"{about}{remaining} to go."
            if remaining is not None and not unresolved else "")
    said = f"{where} {left}".strip()
    if not said:
        return None
    return Call(STATUS, state.lap, said, "")


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
    state.temp_conserve_lap = None
    # The wear occasions speak freshly each stint for the same reason the
    # temperature ones do; the readings only survive when the rubber does.
    state.wear_said = set()
    if tyres_changed:
        state.laps_since_stop = 0
        state.tyre_change_unconfirmed = False
        state.temp_history = []
        # **A rate fitted across a stop describes neither set.** The gauge
        # snaps back to white on a fresh set, so keeping the old points would
        # fit a line through a discontinuity and report a tyre that repairs
        # itself.
        state.wear_history = []
    elif tyres_changed is None:
        state.tyre_change_unconfirmed = True
