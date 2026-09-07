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

from pitcrew.diagnostics import log

from pitcrew.strategy.model import fuel_margin_l

# What George says at the green when nobody wrote a briefing. Imported rather
# than restated: `race/knowledge.py` owns the sentence, and two copies of one
# line is how the app comes to say it two ways.
from pitcrew.race.knowledge import NO_NOTES
from pitcrew.strategy.fuel_model import fill_for_l, stint_burn_l




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
# Below this an incident is not worth a number. The driver's own measured
# lap-to-lap noise is sd 0.918 s, so anything under about three of those is
# inside the spread of laps he drives without noticing - and
# `analysis/incidents.TIME_LOSS_S` uses the same 3 s as its own first test,
# which is the figure this deliberately matches.
INCIDENT_WORTH_SAYING_MS = 3000
# How many crossings an unspoken incident may wait for a quiet one. It can
# lose its own crossing to a box call, and one lap late is still true; two is
# news about a lap two minutes gone.
INCIDENT_STALE_LAPS = 1

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
# **After an off or a spin.** Not an instruction - he knows he went
# off - but the lap has left the count and he is the only one who can
# tell the engineer it picked the wrong lap.
INCIDENT = "incident"
TYRE_TEMP = "tyre-temp"
STATUS = "status"
GREEN = "green"
# **A place gained or lost, said as it happens.**
#
# It is a fact, not an instruction, so under the two registers it has no
# business being volunteered - and it is volunteered anyway, as the single
# documented exception (`docs/ENGINEER-TARGET-STATE_2026-08-29.md` D7). Two
# reasons, and the second is the one that decides it:
#
# 1. **He races with the GT7 race HUD off.** A fact he cannot look up is not
#    a fact on request; it is a fact he does not have.
# 2. **Position changes what a stop costs.** Dropping into traffic before a
#    stop, or sitting behind a car that is about to pit, moves the box
#    decision - so the fact is the leading edge of a decision, and saying it
#    late is saying it after the decision was needed.
#
# Said MID-LAP, off `note_packet`, not at the crossing. That is not a detail:
# it is what keeps §5.5's one-thing-at-a-time intact, because a call made
# between crossings never competes with the crossing's own.
POSITION = "position"
STAY_OUT = "stay-out"
# The tank now reaches the flag and the plan's remaining stops were only ever
# there to fill it. See `_stops_off`.
STOPS_OFF = "stops-off"
# **The answer to a saving the engineer asked for.** Not an
# instruction, so it is ranked below every call that is one - but it
# closes a loop the engineer opened, and an unclosed loop leaves the
# driver believing a shortfall was covered when it was not.
SAVING_RESPONSE = "saving-response"
# **The driver has stopped saving on his own** - the lift-and-coast or the
# hand short-shift has gone, measured off the frames, and the burn with it.
SAVING_CHANGE = "saving-change"
# **The chase.** A car ahead inside the window with few laps left: the gap,
# the laps, and what he has to find per lap - stated against his own
# lap-to-lap spread so a target inside the noise is not heard as one he can
# drive to. Deep Forest, 6 Sep 2026: seven laps chasing P2 with the wall
# reading the gap on 154 frames, and not one of them spoken.
CHASE = "chase"
# **Where round the lap the car ahead has us, and where we have him.** The
# gap binned by road position over laps, rolled up into the circuit's own
# sectors. A fact: "Faster than Boxhead through 1 and 2. He has you in 3."
SECTOR_SPLIT = "sector-split"
# **The undercut, as it exists in GT7.** Not the tyre undercut - CLAUDE.md
# 5.4 says that one is weak here and it is not imported. This is the
# TRAFFIC undercut: held up behind a car we are faster than, with the stop
# still to come, the fill costs the same standing time on any lap from the
# first one the tank can hold fuel to the flag on - so the stop is taken NOW
# and buys clear air, and he pays the same toll later.
UNDERCUT = "undercut"
# **Is the tow worth it.** The fuel saved in his wake priced at the pump,
# against the lap time given away there. A fact, with a verdict in it -
# "Not worth it" - because the arithmetic has one answer and the driver
# asked for it in real time. See `race/tow.py`.
TOW_TRADE = "tow-trade"
# **A penalty served, and what it cost.** Read off the frames at the
# crossing; the lap leaves the pace population and he hears the figure.
PENALTY = "penalty"
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
# **`STOPS_OFF` sits with the box calls, above them.** It is the call that
# cancels one, so it cannot rank below the thing it cancels.
# The rival kinds. Defined here rather than in `race/rival_calls.py` so that
# `URGENCY` and `REGISTER` can name them without importing the module that
# composes them - the ranking is a property of the vocabulary, not of the
# thing that speaks it.
REJOIN = "rejoin"
CLOSING = "closing"
RIVAL_BOXED = "rival-boxed"
RIVAL_COMMITTED = "rival-committed"
RIVAL_SHORT = "rival-short"
STAY_OUT_FUEL = "stay-out-fuel"

URGENCY = (CHEQUER, STOPS_OFF, BOX_NOW,
           # **`UNDERCUT` sits directly below `BOX_NOW`.** It is a box
           # instruction that brings the planned stop forward, so a stop
           # already due wins, and a fuel shortfall is an argument FOR it
           # rather than against - the fill it asks for is to the flag.
           UNDERCUT,
           FUEL_SHORT, LAPS_TO_GO, BOX_SOON,
           # **`STAY_OUT_FUEL` sits immediately below `BOX_SOON`, because it
           # is the argument against it.** The two answer the same question
           # and must be adjacent, or the driver hears them in an order that
           # implies they are about different things. Below rather than above:
           # a box call that fires has a reason the tank cannot argue with,
           # and the case for one more lap is worth seconds where being a lap
           # short of the flag is worth a stop.
           STAY_OUT_FUEL,
           # **`REJOIN` sits with the other three answers to "when do I
           # stop".** It is the one that decides a PLACE where the rest decide
           # seconds - every car within our own pit loss behind us comes out in
           # front - so it ranks above them, and below only the calls about
           # running out of fuel altogether.
           REJOIN,
           # **`WEAR` sits below the fuel calls and above temperature.** A car
           # out of fuel stops on the circuit; a car on worn tyres is still
           # moving, so fuel wins. But a measured wear figure beats an
           # inference drawn from how hot the rubber is, so it takes
           # precedence over `TYRE_TEMP`.
           # **`INCIDENT` outranks `WEAR`** and everything below it.
           # It is true exactly once, on the crossing after the lap it
           # describes, and a wear note said instead of it is a note
           # that could have been said on any of the next five laps.
           # **`POSITION` ranks second from last, above the heartbeat only.**
           # It is a fact and the register says facts do not outrank
           # instructions. It never actually contends here - it is emitted
           # mid-lap, off `note_packet`, where nothing else is speaking - but
           # `next_call` raises on any kind absent from this tuple, and a kind
           # that only ever arrives by another road is exactly the one that
           # goes unranked until a race finds it.
           FUEL_LONG, INCIDENT, WEAR, TYRE_TEMP,
           # A fact about his own driving, below every call about the car.
           SAVING_CHANGE,
           # And the chase, below it: news about the car ahead, not about ours.
           CHASE,
           # And where he has us: said once a stint, and it can wait a lap.
           SECTOR_SPLIT,
           # And what his wake is worth against what it costs.
           TOW_TRADE,
           # A penalty served: one crossing's news, below the plan's calls.
           PENALTY,
           # **A rival's stop ranks below every call about our own car**, and
           # below the incident and the wear note too. It is the only thing
           # here that is about somebody else: a car of ours about to run dry,
           # or on a tyre that is going, outranks news of what another driver
           # just did, however useful that news is. `RIVAL_BOXED` leads
           # `RIVAL_COMMITTED` because it is the one that can still be acted
           # on - the columns are drawn only while he is standing, so it is
           # true now and gone in a minute, where a forced second stop stays
           # true for the rest of the race.
           # **`RIVAL_SHORT` sits immediately below `RIVAL_COMMITTED`,
           # because the two are the two answers to one question.** A rival
           # short of fuel either stops again or drives it out.
           # **Named for what is observed, not for what is inferred.** It was
           # `RIVAL_SAVING`, which asserted an intent the app cannot see - and
           # collided with `SAVING_RESPONSE` and the short-shift instructions,
           # which are about the DRIVER saving. One voice, one word, two
           # subjects, at racing speed (rule 13).
           RIVAL_BOXED, RIVAL_COMMITTED, RIVAL_SHORT,
           # **`CLOSING` is a fact about pace and ranks with the other facts.**
           # It is worth hearing and it is never an instruction: what to do
           # about catching somebody is the driver's, and a closing rate that
           # outranked a fuel call would be a pace note said instead of a stop.
           CLOSING,
           GREEN, POSITION, STATUS)

# --- the two registers -----------------------------------------------------
#
# **What George volunteers, and what he only answers.** The driver's account
# of what was wrong, 29 Aug 2026: *the engineer reports where he should
# advise*. Reading the inventory he was right - most of the vocabulary above
# is status wearing an instruction's clothes.
#
# So every kind declares which register it is in, and the registers mean
# different things about when a thing may be said:
#
#   DECISION  an instruction. Volunteered, ranked, one per crossing.
#   EVENT     true exactly once and not askable afterwards - the green, the
#             flag, an incident, the run-in. Volunteered because a fact that
#             expires is not a fact on request.
#   FACT      volunteered only where he cannot obtain it himself. Today that
#             is POSITION and the heartbeat, and BOTH are there for the same
#             reason: he races with GT7's race HUD off.
#
# **This is a register, not a rank.** `URGENCY` still decides what wins a
# crossing. What this decides is whether a kind may open its mouth unasked,
# and it is asserted in the tests so a new kind cannot be added without
# someone saying which of the three it is.
DECISION = "decision"
EVENT = "event"
FACT = "fact"

# **Calls that are advice, not orders.** Spoken with a one-word suffix so
# the driver can tell them from an instruction without a second sentence.
SUGGESTIONS = frozenset({FUEL_LONG, TYRE_TEMP, STAY_OUT})

REGISTER = {
    BOX_NOW: DECISION,
    BOX_SOON: DECISION,
    STOPS_OFF: DECISION,
    FUEL_SHORT: DECISION,
    FUEL_LONG: DECISION,
    STAY_OUT: DECISION,
    SAVING_RESPONSE: DECISION,
    SAVING_CHANGE: FACT,
    CHASE: FACT,
    SECTOR_SPLIT: FACT,
    TOW_TRADE: FACT,
    PENALTY: FACT,
    UNDERCUT: DECISION,
    WEAR: DECISION,
    TYRE_TEMP: DECISION,
    TYRE: DECISION,
    GREEN: EVENT,
    CHEQUER: EVENT,
    INCIDENT: EVENT,
    LAPS_TO_GO: EVENT,
    POSITION: FACT,
    STATUS: FACT,
    # **The rival calls, and all three are DECISIONS.** None of them is a
    # separation in seconds - `_fuel_gap` already says "gap" meaning laps of
    # fuel in hand, and one word with two units on one voice is rule 13. They
    # say litres, seconds standing, and the lap a car must stop by, and each
    # names its own reference inside the call. See `race/rival_calls.py`.
    REJOIN: DECISION,
    CLOSING: FACT,
    RIVAL_BOXED: DECISION,
    RIVAL_COMMITTED: DECISION,
    RIVAL_SHORT: DECISION,
    STAY_OUT_FUEL: DECISION,
}


def register_of(kind: str) -> str:
    """Which register a kind speaks in. Raises on a kind nobody classified.

    Deliberately not `.get(kind, FACT)`. A default here would let a new
    instruction be added and silently treated as a fact - which is the exact
    direction of the defect this whole split exists to correct.
    """
    try:
        return REGISTER[kind]
    except KeyError:                                         # pragma: no cover
        raise KeyError(
            f"{kind!r} has no register. Every call kind must declare whether "
            f"it is a {DECISION}, an {EVENT} or a {FACT} - see REGISTER."
        ) from None

# A status call every few laps, so silence means "nothing to report" rather
# than "the app has died".
#
# **Settable, because the driver asked for one every lap** (28 Aug 2026:
# *"each lap making sure I'm on track"*). `RaceState.status_every_laps`
# overrides it, and `1` is the every-lap setting.
#
# A second call kind was the obvious way to do that and it is the wrong one.
# `record()` sets `last_said_lap` for every kind, so a per-lap call of any kind
# takes `laps_since_anything_said()` to 1 forever - which silently kills this
# heartbeat, `_saving_response` and the colour calls (both reached only through
# the `next_call() is None` branch), and clears the short-shift beep the lap
# after it was asked for. One heartbeat with one meaning and a rate on it does
# all of that damage to none of them.
STATUS_EVERY_LAPS = 5

# Fuel margin below which the plan no longer reaches the stop.
# Under this much short, "good" is the honest word: the shortfall is inside
# the scatter of the burn it was measured from. Past it the driver gets the
# figure rather than reassurance - the same threshold the fuel call itself
# acts on, deliberately, so the heartbeat and the instruction cannot disagree
# about whether he is short.
# What the fuel is measured against, in the words the driver hears. There are
# two of them and they are ten laps apart.
TO_THE_STOP = "to the stop"
TO_THE_FLAG = "to the flag"

FUEL_STANDING_TOLERANCE_LAPS = 0.5
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
    # **A change to the plan's SHAPE riding on this call**, named from
    # `handover.STRUCTURAL_ACTIONS`, or None where the call changes nothing
    # structural. Two calls carry one as of 7 Sep 2026: `STOPS_OFF` is a
    # `drop_stop`, and the wear cliff's "Box this lap" is an `add_stop` when
    # no stop was planned. The stay-out fold carries none on purpose - see
    # `handover.STRUCTURAL_ACTIONS`: it recognises a stop the driver has
    # already declined, it does not take one.
    #
    # It exists because the rail has to gate something nameable. George may
    # not add a stop, drop a reachable one, change compound or abandon the
    # plan unless the desk wrote it down, and a gate needs the instruction to
    # be a field it can strip rather than a side effect it cannot see. The
    # report is never stripped; the instruction is - see `report_form` and
    # `RaceCoordinator._within_the_playbook`.
    structural_action: str | None = None
    # The playbook trigger the structural action rides under, from
    # `handover.TRIGGERS`. The gate used to look the call's KIND up as a
    # trigger, and no kind is one, so every structural action would have
    # been refused whatever the desk granted.
    trigger: str | None = None
    # **What the call says when the desk withheld the action.** The report
    # without the instruction: "You're fuelled to the flag." without "No
    # more stops on fuel." A call that carries a structural action and no
    # report form keeps its words when stripped, which is the old behaviour
    # and means the rail changed nothing audible.
    report_form: str | None = None

    def spoken(self) -> str:
        """Instruction, then reason. Then the one word that marks a register.

        An instruction is the default and carries no suffix (§5.5: one thing
        at a time). A **suggestion** - "You can push", the tyre-temperature
        advice, the stay-out offer - ends "Suggestion." so it cannot be heard
        as an order; a LOW-confidence call ends "Unconfirmed.". That is what a
        real pit wall does with "diff mid plus one, suggestion". The box call's
        "copy?" waits on the push-to-talk round trip being proven live (A5):
        "copy that" already accepts a re-plan, and a confirmation word that
        can be misheard as one is worse than none.
        """
        text = self.call
        if self.reason:
            text = f"{text} {self.reason}"
        if self.confidence == LOW:
            text = f"{text} Unconfirmed."
        elif self.kind in SUGGESTIONS:
            text = f"{text} Suggestion."
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
    # **The number on the driver's screen, which is NOT `lap`.** GT7's own
    # counter names the lap in PROGRESS; `lap` counts the ones behind him, so
    # at every crossing they differ by one and in session 127 (Daytona, 4 Sep
    # 2026) they differed by one on all 20 rows. The engineer spoke `lap`, so
    # *"Lap 2. 18 laps to go."* was said while GT7's HUD displayed lap 3, all
    # race, and the driver reported it unprompted.
    #
    # **Two names because they are two quantities** - CLAUDE.md rule 13. Every
    # piece of arithmetic in this module counts laps BEHIND him and keeps
    # using `lap`; the only thing that may be spoken as "Lap N" is this one,
    # because it is the only one he can check against anything. `None` until a
    # crossing has carried GT7's count - see `lap_on_screen`.
    screen_lap: int | None = None
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
    # **The mean fuel aboard across the laps `fuel_per_lap_l` was taken from.**
    # Burn rises with what is in the tank, so a burn measured over a heavy
    # stretch over-states a stint that runs the tank down - at Spa on 31 Aug
    # the median was taken at 66 L aboard while a full stint averages 41 L,
    # and the difference was 1.5 L of fill, i.e. 1.5 s standing still. None
    # means unknown, and every fuel sum then falls back to `laps x burn`
    # exactly as it did before. See `strategy/fuel_model.py`.
    fuel_reference_load_l: float | None = None
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
    # **Nobody wrote a briefing for this circuit**, so George is on the generic
    # model. Said once, at the green - see `_green`. Set by the coordinator
    # from `race/knowledge.for_event`; False when a briefing exists, and the
    # default is False because a state built by hand in a test is not a claim
    # that the briefing is missing.
    no_notes: bool = False
    position: int | None = None
    # **How many cars are out there.** `packet.cars_in_race` decodes it and
    # nothing in this package has ever read it. "P8" and "P8 of 9" are
    # different pieces of news and the second one is the one he can act on.
    field_size: int | None = None
    # The position the last position call was made at, so a change is said
    # once and a jitter is not said at all. `None` until the first reading.
    # Written by `RaceCoordinator.note_packet`; read by `_position_change`.
    position_said: int | None = None
    # How many consecutive frames have agreed on a position that disagrees
    # with `position`. A place change is worth a word; a single frame of a
    # field that was being written as it was read is not.
    position_pending: int = 0
    position_pending_value: int | None = None
    in_pit: bool = False
    finished: bool = False
    # **What the pit wall has seen of the other cars, keyed by name.** Every
    # rival call in `race/rival_calls.py` was written, tested and reachable
    # from nothing: `must_stop_by` and `rival_boxed` were called only by their
    # own tests, and the controller emitted `rival_stopped` into a signal with
    # no connection. This field is the road in.
    rivals: dict = field(default_factory=dict)
    # Board positions per driver, refreshed each lap. Kept apart from `rivals`
    # because a stop's position is read while the car is STANDING - the one
    # moment it does not describe where he is racing.
    rival_positions: dict = field(default_factory=dict)
    # **The two gap trends the board reader keeps**, refreshed each lap. Held
    # as objects rather than numbers because `closing_call` needs the run
    # length behind the rate: a trend is only worth saying after
    # `MIN_LAPS_FOR_TREND` CONSECUTIVE laps.
    gap_ahead: object = None
    gap_behind: object = None
    # **Names, because `GapTrend.subject` is a cluster id.** The roster that
    # can turn one into a name lives on the pit wall, on the other side of the
    # thread boundary, so the translation happens where the roster is.
    gap_ahead_name: str | None = None
    gap_behind_name: str | None = None
    # **The gap to the car ahead binned by road position** - a
    # `sectors.SectorMap`, fed by the coordinator once a lap from the wall's
    # samples. None until the wall runs. `sector_cuts_m` are the circuit's
    # sector lines, so the map speaks in the sectors on his rack.
    sector_map: object = None
    sector_cuts_m: tuple | None = None
    # **What the tow is worth against what it costs** - a `tow.TowTrade`,
    # remade by the coordinator on every crossing from this race's own laps
    # and the wall's gaps. None until three laps have been held up.
    tow_trade: object = None
    # **The verdict he was last told the tow carried**, set in `record()` so
    # that only a call actually spoken sets it. It survives the stop on
    # purpose: once the last fill is in, a driver who was told "Worth it -
    # stay in it" is still sitting in a wake for a reason that has stopped
    # existing, and saying so once is the last thing worth saying about it.
    tow_said_worth_it: bool | None = None
    # Whether a `TOW_TRADE` verdict has ever been SPOKEN this race. Separate
    # from the verdict above because that is tri-state: a wash reads None,
    # which is not the same claim as "he has never been told about the tow".
    tow_said: bool = False
    # `(lap, seconds lost)` of a penalty served on the lap just completed,
    # from the controller's read of the frames; cleared once said.
    penalty_note: tuple | None = None
    # **Whether the desk granted George `drop_stop`** (`fuel_long` in the
    # playbook). False keeps every planned stop whatever the tank says -
    # the report "You're fuelled to the flag" is still made, the box call
    # still comes. None is a state built by hand, and the tank decides as
    # it always did. Critic pass 5: the rail had changed the sentence and
    # not the behaviour.
    drop_stop_granted: bool | None = None
    # **Rivals seen entering the lane, as a queue.** A single slot lost one of
    # two cars entering in the same frame, and was never cleared - so the same
    # lap-8 entry was re-spoken five laps later, after our own stop had reset
    # `said`, with a swing computed against a different tank. Drained by
    # `_rivals` on the crossing that offers it (rule 11).
    rivals_entering: list = field(default_factory=list)
    # Litres a second at the pump, from the event. `None` is not a rate.
    refuel_rate_lps: float | None = None
    # Seconds lost driving through the lane, a TRACK constant (CLAUDE.md 5.4).
    pit_loss_s: float | None = None
    pit_loss_source: str | None = None
    # Our own last stop, so a rival's standing time has something to be
    # compared against.
    our_stop: object = None
    # **The fuel the next stint STARTS on, not the fill.** The litres through
    # the hose are this minus what is aboard when we arrive, and `stop_costs_s`
    # prices what goes through the hose. Named for what it holds.
    next_stint_load_l: float | None = None
    # Stint accounting against the approved plan.
    stint_index: int = 0
    stint_ends_on_lap: int | None = None
    next_compound: str | None = None
    # **Whether the next stop takes tyres - the plan's decision, tri-state.**
    # True: a set goes on. False: fuel only. None: the plan did not say, and
    # the box call then names the compound as it always has. Deep Forest,
    # 6 Sep 2026: Ludo wrote "TYRES: DO NOT TAKE THEM" into a knowledge note
    # nothing reads, the box call said "Box this lap. RS." because that is the
    # plan's compound, and the driver took a set - ~4.4 s. A decision that
    # lives in prose is not a decision the car can say.
    next_tyres: bool | None = None
    # **Whether this stop's start/finish crossing has already happened.** At
    # Daytona and Spa the line is inside the pit lane before the box, so the
    # lap counter has already moved by the time the hose is in and the lap in
    # progress is the out-lap - which the fill has to cover in full. At Deep
    # Forest and Monza the crossing comes after the box, and the lap in
    # progress is mostly behind the car. Set on LAP_COMPLETED while `in_pit`,
    # cleared at PIT_ENTRY and PIT_EXIT. Without it the fill was a lap short
    # at the two circuits where the line comes first (critic, 7 Sep 2026).
    crossed_in_box: bool = False
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
    # **The wear rate measured off a replay of an earlier race here**, for the
    # compound actually on the car, with the number of stints behind it.
    #
    # This is what makes a wear call possible in VR at all. GT7 draws the HUD
    # on the car's dashboard in 3D, so the gauge moves with his head and reads
    # about 6 crossings in 22 - a live fit needs three in one stint and rarely
    # gets them. Read off the replay afterwards the same gauge is good to
    # 0.5%, against a model that was ~21% low, and `race/knowledge.py` carries
    # it forward. Set by the coordinator when the compound is known; None
    # where nobody has driven a measured stint on this compound here.
    briefed_wear_per_lap: float | None = None
    # How many stints stand behind that rate. Every aggregate carries its
    # sample count (CLAUDE.md 4.4) - a rate from one stint and one from six
    # are not the same claim.
    briefed_wear_samples: int = 0
    # The tyre-wear multiplier this race runs at ("2x"), from the event.
    tyre_wear_mult: str | None = None
    # Set by the coordinator when the frames say he stopped saving: the
    # sentence to say, once, and the lap it was first true on.
    saving_change_note: str | None = None
    saving_change_lap: int | None = None
    # This car's lap-to-lap spread at this circuit, seconds, from the race's
    # own clean laps (`expectations.sigma_ms`). None until enough laps exist.
    lap_sigma_s: float | None = None
    # What the tyre model held the moment a stop was taken as a tyre change:
    # (laps_since_stop, wear_history, temp_history). Kept so that a driver's
    # "no tyres" can put the OLD set back under the live projection, not only
    # onto the record. Critic pass 4, 7 Sep 2026: the ledger said his word
    # stood while the projection still counted the set as fresh.
    stint_before_stop: tuple | None = None
    # The lap the chase line was last said on, so it is said every other lap
    # and not every crossing.
    chase_said_lap: int | None = None
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
    # The lap the unconfirmed stop happened on, so a later resolution can
    # restart the stint count from the right place; and what resolved it,
    # for the log and the audit ("gauge: fresh set" / "gauge: same set").
    unconfirmed_stop_lap: int | None = None
    tyre_change_resolution: str | None = None
    # **The worst corner as the gauge last read it BEFORE the stop.** Every
    # reading while unconfirmed is judged against this and never against
    # the previous unresolved reading - a partial drop appended to the old
    # history moved the baseline to itself, and the next reading then read
    # "same set" against a set that had just fallen by thirty points (rule
    # 10: a baseline that cannot be retired is a latch).
    unconfirmed_before: float | None = None
    # Readings taken while unconfirmed, held back from the history until the
    # question is settled: `(lap, wear)` pairs.
    parked_wear: list = field(default_factory=list)
    # The stop lap a resolution belongs to, for the controller to write
    # `laps.tyres_changed` back; None until a resolution has been reached
    # and then cleared once written.
    tyre_change_write_back: tuple | None = None
    # The lap of the last stop, whatever was known about its tyres - so a
    # driver's word that arrives after a verdict still names the stop.
    last_stop_lap: int | None = None
    # (what was settled before, what the driver said) when the two disagree.
    tyre_change_disagreement: tuple | None = None
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
    # --- an off or a spin, seen live (race/incident_watch.py) ---
    # The lap the car stopped on, set at the crossing that ends it and cleared
    # once spoken. None means nothing has happened.
    incident_lap: int | None = None
    # What that lap cost against the race's own representative pace, in ms, or
    # None where no pace has been established yet. **A cost of None is not a
    # cost of zero** - it means the race has not run enough clean laps to say,
    # and the call then reports the incident without a figure.
    incident_cost_ms: int | None = None
    # Whether the driver told the engineer first. He has already been
    # acknowledged if so, and saying it again is the app talking to itself.
    incident_reported: bool = False

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
    # **Crossings GT7's own lap counter says were missed, seen live.**
    # `laps_dropped` above is the clock's, and the clock can only count one at
    # a crossing - which is one lap too late for the only call that needs it.
    # Measured, Road Atlanta 23 Aug 2026: the crossing went missing inside the
    # box, the in-box fuel call went out at 20:40:35 asking for twelve laps of
    # fuel against nine to run, and the clock only said so at 20:42:36 when
    # lap 12 finally completed. Thirteen litres crossed the line unburnt.
    #
    # GT7's `laps_completed` had it right the whole time: +2 across the pit
    # lap and +1 across all twenty others in that race. The field is marked
    # unreliable *for the race finish* and that caution stands - this uses it
    # only as a delta against the app's own count, which is the one thing it
    # was right about on every lap on file.
    #
    # **Combined with `max`, never `+`.** Two detectors incrementing one
    # counter is how a single missed crossing becomes two; taking the larger
    # of the two makes double-counting impossible by construction, and lets
    # the clock's authoritative count supersede this one at the crossing
    # without either having to know about the other.
    laps_dropped_seen: int = 0
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
        counted = self.lap + self.laps_missed()
        return max(0, self.laps_total - counted)

    def laps_missed(self) -> int:
        """Crossings that went missing, by whichever detector saw one.

        **`max`, not a sum.** See `laps_dropped_seen`: the clock counts at the
        crossing and GT7's counter within a packet of the event, so on an
        ordinary missed lap both eventually report the same one. Adding them
        would report two.
        """
        return max(0, self.laps_dropped, self.laps_dropped_seen)

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
    # How often the heartbeat speaks. `1` is the driver's every-lap setting.
    status_every_laps: int = STATUS_EVERY_LAPS
    # **What the plan's stops were FOR**, off `plan["binding_constraint"]`.
    # A stop exists because of fuel, or the tyre, or a rule, and only the
    # first kind can be cancelled by a tankful. `None` means the plan did not
    # say, and a stop nobody can account for is never cancelled.
    plan_binding_constraint: str | None = None
    # Stops the regulations require that have not been taken. `None` where the
    # app does not know - the event page has no field for it - and unknown is
    # not the same as none, so it never cancels a stop on its own.
    mandatory_stops_left: int | None = None
    # Said once. The driver does not need telling twice that the stops are off.
    stops_off_said: bool = False
    # Whether the spoken count needs a hedge - noise, plus the degradation
    # bias `laps_estimate_firm` cannot see. Deliberately NOT that flag: it
    # sizes fuel margins, and widening it put a spare lap in every tank.
    laps_count_hedged: bool = False
    # A stop is still on the plan. The count assumes he does NOT take it,
    # because he may not, so the stop is priced beside it.
    stop_pending: bool = False
    # What that stop actually costs in laps, from the clock and the measured
    # pit loss. Usually zero. `None` where no pit loss has been measured here,
    # and an unmeasured cost is not spoken.
    stop_costs_laps: int | None = None
    # The kind of the last thing said, beside the lap it was said on.
    last_said_kind: str | None = None
    # **Seconds left on the race clock**, for a timed race. The app timer from
    # the green, which is the only measurement of it there is - GT7 broadcasts
    # no race time. `None` in a lap race and before the green.
    race_remaining_s: float | None = None

    def lap_now(self) -> int:
        """The lap he is actually on, GT7's count and not the app's.

        **`state.lap` alone can run light for a whole race.** GT7 takes the
        car over at pit entry and the crossing inside that sequence does not
        reach the app; `laps_missed()` is what both detectors - the clock's
        and GT7's own `laps_completed` - report about it. Road Atlanta is on
        file: GT7's counter sat +1 above the app's on lap 1 and +2 by lap 20,
        so the app has 21 laps of a race he drove 22 of.

        `laps_remaining()` has always applied this correction. The lap NUMBER
        never did, because nothing spoke it - and with the race HUD off it is
        the one figure he cannot check against anything.
        """
        return self.lap + self.laps_missed()

    def lap_on_screen(self) -> int:
        """The lap number GT7 is showing him, which is the one to say out loud.

        **`lap_now()` counts what is behind him; this counts the one he is
        driving.** They are one apart at every crossing, and the engineer said
        the wrong one for a whole race: session 127 (Daytona, 4 Sep 2026),
        `laps.laps_completed` = `laps.lap_num` + 1 on **all 20 rows**, so
        *"Lap 2. 18 laps to go."* went out while the HUD read lap 3. The
        arithmetic was right - 18 really did remain - but **the number he
        hears has to match the number he can see, and under a helmet the
        screen wins.**

        `laps.laps_completed` recorded that offset from the start and was read
        by nothing; that sentence has now been written three times in this
        project (Fuji 26 Aug, and twice since). This is where it gets read.

        **GT7's own count first, arithmetic second.** `screen_lap` is set at
        each crossing from `Lap.laps_completed`, which is the authority - the
        offset is not always one, because a crossing GT7 counted and the app
        missed widens it (Road Atlanta: +1 on lap 1, +2 by lap 20). The
        fallback `lap_now() + 1` is not a measurement and does not pretend to
        be one: it is the definition of "the lap in progress" applied to the
        drop-corrected count, and it is only reached before GT7's counter has
        travelled on a crossing.
        """
        if self.screen_lap is not None and self.screen_lap > 0:
            return self.screen_lap
        return self.lap_now() + 1

    def only_the_heartbeat_this_lap(self) -> bool:
        """Whether this lap has had nothing but the heartbeat.

        The question every "was the lap already spoken for" guard actually
        wants. Asked as `last_said_lap == lap` it answers a different one, and
        at the driver's every-lap setting the two diverge on every crossing of
        the race.
        """
        return (self.last_said_lap == self.lap
                and self.last_said_kind == STATUS)

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
        if self.tyre_change_unconfirmed:
            # Judged, and either settled or parked - never appended to the
            # old set's history while the question is open.
            self._resolve_tyre_change(lap, present)
            return
        self.wear_history.append((lap, present))

    def _resolve_tyre_change(self, lap: int, present: dict) -> None:
        """A stop said nothing about the tyres; the gauge can.

        **The gauge saw the fresh set at Deep Forest and nobody asked it.**
        The swap detector missed the lap-13 change, PIT_EXIT said "not
        changed", and the live fit ran through 0.42 -> 0.00 -> 0.03 while the
        briefed projection counted thirteen laps on a set that was one lap
        old. The first reading after an unconfirmed stop settles it: every
        corner back near zero is a new set, a series that carries on from
        where it was is the old one. Either way the word "unconfirmed" comes
        off the wear call, and the resolution is logged so the audit can see
        which instrument answered.
        """
        # **A reading offered twice is one reading.** The sampler holds its
        # last good read until a new one lands, and the controller offers it
        # at every crossing - so one all-zero misread at lap 14 would arrive
        # again at crossing 15 and satisfy "two readings" on its own.
        if self.parked_wear and lap <= self.parked_wear[-1][0]:
            return
        before = self.unconfirmed_before
        if before is None:
            # No reading before the stop to judge against: the gauge cannot
            # settle this one. The stop's own detector already said nothing;
            # the driver's word can (`note_tyres_word`).
            self.parked_wear.append((lap, present))
            return
        now = max(present.values())
        stop_lap = self.unconfirmed_stop_lap
        # **A fresh set needs two readings, not one.** An all-four-corners
        # 0.000 misread is a documented failure of the gauge locator, and
        # `coherent()` upstream accepts it as a fresh set - so a single
        # reading near zero must not wipe the history. Two consecutive
        # readings under the gauge's own fresh-set ceiling, both well below
        # the pre-stop worst and the second no lower than the first, is a
        # set that has gone on. One definition of "fresh" - the gauge's
        # `FRESH_SET_MAX` - not a second threshold pair here.
        looks_fresh = (now <= GAUGE_FRESH_SET_MAX
                       and before - now >= GAUGE_FRESH_SET_DROP)
        previous = self.parked_wear[-1] if self.parked_wear else None
        if looks_fresh and previous is not None:
            earlier = max(previous[1].values())
            if (earlier <= GAUGE_FRESH_SET_MAX
                    and now >= earlier - GAUGE_SAME_SET_SLACK):
                self.laps_since_stop = (max(0, lap - stop_lap)
                                        if stop_lap is not None else 0)
                # The new set's history is the parked readings that were on
                # it - those under the ceiling - and this one.
                self.wear_history = [(l, w) for l, w in self.parked_wear
                                     if max(w.values()) <= GAUGE_FRESH_SET_MAX]
                self.wear_history.append((lap, present))
                self.temp_history = []
                self._settle_tyre_change("gauge: fresh set", before, now, True)
                return
        looks_same = now >= before - GAUGE_SAME_SET_SLACK and not looks_fresh
        if looks_same and previous is not None:
            # **Two readings for "same set" as well.** One stale grab of the
            # old set at 0.40 would otherwise latch the verdict, and the new
            # set's 0.02, 0.03 would then be appended to the old history
            # with no gauge-side way back. Symmetric on purpose.
            earlier = max(previous[1].values())
            if earlier >= before - GAUGE_SAME_SET_SLACK:
                self.wear_history.extend(self.parked_wear)
                self.wear_history.append((lap, present))
                self._settle_tyre_change("gauge: same set", before, now, False)
                return
        # Neither shape yet: a first near-zero reading, or a partial drop.
        # Parked, and the next reading is judged against the SAME pre-stop
        # baseline, never against this one.
        self.parked_wear.append((lap, present))

    def _settle_tyre_change(self, how: str, before: float, now: float,
                            changed: bool) -> None:
        stop_lap = self.unconfirmed_stop_lap
        self.tyre_change_resolution = how
        self.tyre_change_unconfirmed = False
        self.unconfirmed_stop_lap = None
        self.unconfirmed_before = None
        self.parked_wear = []
        self.tyre_change_write_back = (stop_lap, changed, how)
        log("race").info(
            "tyre change at the lap-%s stop resolved by the %s (worst corner "
            "%.0f%% -> %.0f%%)", stop_lap if stop_lap is not None else "last",
            how, before * 100, now * 100)

    def note_tyres_word(self, changed: bool, lap: int | None = None) -> None:
        """The driver said it: "new tyres" or "no tyres". Primary evidence.

        Settles an unconfirmed stop outright, and disagrees out loud with ANY
        verdict already reached the other way - the gauge's or the session's
        own swap detector - and his word stands: the disagreement is the
        finding (CLAUDE.md 4.1), never averaged and never silently kept.
        """
        how = "driver: " + ("new tyres" if changed else "no tyres")
        stop_lap = (self.unconfirmed_stop_lap
                    if self.unconfirmed_stop_lap is not None
                    else self.last_stop_lap)
        if not self.tyre_change_unconfirmed:
            prior = self.tyre_change_resolution
            prior_changed = (None if not prior else
                             ("fresh" in prior or "swap seen" in prior
                              or "new tyres" in prior))
            if prior_changed is None or prior_changed == changed:
                # Nothing to overrule: agreement, or no verdict at all.
                if changed:
                    # The old set's model, held against a "no tyres" that is
                    # not coming, is no longer wanted.
                    self.stint_before_stop = None
                if prior is None and stop_lap is not None:
                    pass
                else:
                    return
            else:
                log("race").warning(
                    "the driver says %s at the lap-%s stop; it had been "
                    "settled as %s - his word stands, the disagreement is "
                    "recorded", how, stop_lap, prior)
                self.tyre_change_disagreement = (prior, how)
        if changed:
            self.laps_since_stop = (max(0, (lap or self.lap) - stop_lap)
                                    if stop_lap is not None else 0)
            self.wear_history = [(l, w) for l, w in self.parked_wear]
            self.temp_history = []
        else:
            stashed = self.stint_before_stop
            if stashed is not None:
                # The stop had been taken as a tyre change and the old set's
                # model zeroed. His word says the rubber never left the car,
                # so the count and the history resume from where they were:
                # the pre-stop laps plus the laps run since, and the old
                # readings ahead of whatever the new stint has read.
                old_laps, old_wear, old_temps = stashed
                self.laps_since_stop = old_laps + max(0, self.laps_since_stop)
                self.wear_history = list(old_wear) + list(self.wear_history)
                self.temp_history = list(old_temps) + list(self.temp_history)
                log("race").info(
                    "the old set's model is back under the projection: %d "
                    "laps on it, %d readings", self.laps_since_stop,
                    len(self.wear_history))
            self.wear_history.extend(self.parked_wear)
        self.stint_before_stop = None
        self.tyre_change_resolution = how
        self.tyre_change_unconfirmed = False
        self.unconfirmed_stop_lap = None
        self.unconfirmed_before = None
        self.parked_wear = []
        self.tyre_change_write_back = (stop_lap, changed, how)
        log("race").info("tyre change at the lap-%s stop resolved by the %s",
                         stop_lap if stop_lap is not None else "last", how)

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
        # **And what it was.** The heartbeat reports; it does not occupy the
        # lap. Everything downstream that keys off "something was said this
        # lap" has to be able to tell a real call from a heartbeat, or the
        # every-lap setting silently takes the whole tier below it - and the
        # gauge prompt lives in that tier.
        self.last_said_kind = call.kind
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
        # **`WEAR` and `INCIDENT` book themselves off HERE, and this is not a
        # tidy-up.** Both used to do it inside the function that builds the
        # call, which runs for every candidate whether or not it wins - and
        # `next_call` builds them all and then ranks. So a wear finding that
        # lost one lap to a box call marked itself said and was never spoken
        # again, and an incident that lost one was cleared and lost outright.
        # Only the call that is actually made may record that it was made,
        # which is what this method has always been for.
        if call.kind == WEAR and call.tag:
            self.wear_said.add(call.tag)
        if call.kind == STATUS and "Tyre gauge" in call.call:
            # Once a stint, like every other occasion-based call. `clear_stint`
            # drops the tags, so a fresh set asks again.
            self.said_tags.add(GAUGE_ASK)
        if call.kind == STOPS_OFF:
            self.stops_off_said = True
        if call.kind == CHASE:
            self.chase_said_lap = call.lap
        if call.kind == TOW_TRADE:
            # What he was actually told, not what the trade currently says -
            # `tow_trade` is remade every crossing and the sentence he is
            # living by is the one that was spoken.
            if call.tag != "tow-spent":
                trade = getattr(self, "tow_trade", None)
                self.tow_said = True
                self.tow_said_worth_it = (getattr(trade, "worth_it", None)
                                          if trade is not None else None)
        if call.kind == INCIDENT:
            self.incident_lap = None
            self.incident_cost_ms = None
            self.incident_reported = False


def fuel_frame(state: RaceState) -> tuple[float | None, str]:
    """`(laps the fuel aboard has to cover, what that distance is called)`.

    **One expression produces both, and that is the whole point.** The number
    and the words for it were computed in two places and drifted apart the
    moment a stop was cancelled: the target became the flag while the sentence
    went on saying "to the stop", so the driver heard a figure measured
    against a distance nobody was driving to. Rule 12 is about exactly this -
    the reported reason has to come from the same expression as the decision -
    and rule 13 is what it costs when it does not.

    Three ways the flag becomes the frame: no stop planned, the box lap has
    gone by, or the stop is no longer a stop (`stop_still_needed`).

    **Flooring `laps_to_stop` at zero is not enough on its own**: at a target
    of zero the gap becomes the whole tank and the "you can push" call fires
    harder than ever. Once the box lap has gone by, the honest target is the
    rest of the race - he is running on this fuel until he actually stops.
    """
    if state.stint_ends_on_lap is None or state.past_box_lap:
        return state.laps_remaining(), TO_THE_FLAG
    if not stop_still_needed(state):
        return state.laps_remaining(), TO_THE_FLAG
    to_stop = state.laps_to_stop()
    if to_stop is None:
        return state.laps_remaining(), TO_THE_FLAG
    return to_stop, TO_THE_STOP


def _fuel_target(state: RaceState) -> float | None:
    """Laps that have to be covered on the fuel now aboard."""
    return fuel_frame(state)[0]


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
    # **Checked before `said`, because these outlive a stint.** `clear_stint`
    # drops `said` and deliberately keeps `said_tags`, so a shortfall frozen at
    # a rival's stop lap was re-announced after our own stop - "14 litres light
    # over 9 laps" said again on lap 18 of 20, describing a window that is
    # mostly spent. Tagged per driver, so two rivals do not swallow each other
    # either. Below the `said` check it never ran at all.
    if call.kind in (RIVAL_SHORT, RIVAL_COMMITTED, RIVAL_BOXED, CLOSING,
                     CHASE):
        # `CHASE` too: tagged per lap, so `said` never silences it for the
        # stint - critic pass 5 found it spoken once and then never.
        # `RIVAL_BOXED` and `CLOSING` joined them: untagged, one CLOSING call
        # swallowed the other for the whole stint - "he is taking 1.5 a lap out
        # of you" silencing "you are taking 1.4 a lap out of Rocky", which are
        # opposite news about two different cars.
        return call.tag not in state.said_tags
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


# The chase is spoken while the car ahead is inside this many seconds and
# the flag is inside this many laps - beyond either there is nothing to drive
# to yet - and every other lap, so it never fills the radio.
CHASE_WINDOW_S = 20.0
CHASE_LAPS = 10
CHASE_EVERY_LAPS = 2


def _chase(state: RaceState) -> Call | None:
    """The car ahead, the laps left, and the pace it takes - with its noise.

    A FACT: catching him is the driver's decision. What the HUD cannot show
    him is the division - the gap over the laps left - and whether that
    number is inside his own lap-to-lap spread, which is the difference
    between a target and a coin toss. Every other lap, inside the window,
    and never in the box or on the flag.
    """
    if state.in_pit or state.finished or _crossing_the_line(state):
        return None
    # A copy: the sampler thread clears the live trend on a subject change.
    seen = dict(getattr(state.gap_ahead, "seen", None) or {})
    latest = seen[max(seen)] if seen else None
    if latest is None or latest <= 0 or latest > CHASE_WINDOW_S:
        return None
    laps_left = state.laps_remaining()
    if laps_left is None or laps_left < 1 or laps_left > CHASE_LAPS:
        return None
    if (state.chase_said_lap is not None
            and state.lap - state.chase_said_lap < CHASE_EVERY_LAPS):
        return None
    need = latest / laps_left
    them = state.gap_ahead_name or "the car ahead"
    laps_word = "lap" if laps_left == 1 else "laps"
    call = f"{them} {latest:.1f} ahead, {laps_left} {laps_word} to go."
    reason = f"You need {need:.1f} a lap."
    sigma = state.lap_sigma_s
    if sigma:
        reason += (" That's more than your lap-to-lap spread."
                   if need > sigma else
                   " That's inside your lap-to-lap spread.")
    # `chase_said_lap` is set by `record()`, when the call is actually
    # made - a builder that marks its own call as said marks calls that
    # were outranked and never spoken.
    return Call(CHASE, state.lap, call, reason, MEDIUM,
                tag=f"chase-{state.lap}")


def _penalty(state: RaceState) -> Call | None:
    """A penalty served on the lap just run, with its derived cost.

    **"Possible", and LOW, and it will never be anything else** (critic
    passes 6 and 7). Nothing here reads a penalty. `analysis/penalties.py`
    reads a hard brake at speed, going straight, outside every corner in the
    model - and an avoidance stab behind a spinning car is that shape, and so
    is a wet brake taken early for a corner the model does say is there. The
    HUD's own penalty indicator is not read and has no calibration frame.

    So two things carry the doubt, and they are in the order he hears them.
    The first word does: **"Penalty served." puts the flat assertion in the
    two words that land at speed**, and a hedge twelve words later is not
    where a driver takes it from. Then LOW, so `spoken()` ends it
    "Unconfirmed." - CLAUDE.md §5.5's own word, "a word the driver can act
    on". Said as a bare fact it is rule 5 exactly: something derived,
    presented as measured.

    **The reason stays short.** §5.5 wants the instruction, then the reason,
    and one thing at a time; how the reading was taken is a note for the log
    and the export, not a clause under a helmet.

    **The lap leaving the pace population is NOT hedged, and does not need
    to be.** Whatever caused a full-brake-to-a-crawl on a straight, the lap
    is not evidence of this car's pace or burn. Only the NAME is uncertain.
    """
    note = state.penalty_note
    if note is None or state.in_pit or state.finished:
        return None
    lap, lost = note
    tag = f"{PENALTY}:{lap}"
    if tag in state.said_tags:
        return None
    cost = (f" About {lost:.1f} seconds." if lost is not None and lost > 0
            else "")
    return Call(PENALTY, state.lap, f"Possible penalty served.{cost}",
                f"Lap {lap} is out of the pace.", LOW, tag=tag)


def _saving_change(state: RaceState) -> Call | None:
    """He stopped lift-and-coasting, or stopped short-shifting - said once.

    The Deep Forest fill was sized on a stint driven saving and the stint
    after it was not; the engineer had no way to see either. Now the frames
    say so at the crossing after the change, and the burn the fill is sized
    on (this stint's, `expectations.stint_fuel_per_lap_l`) already reflects
    it. A FACT, once per change, tagged by the lap it started.
    """
    note = state.saving_change_note
    if not note or state.in_pit or state.finished:
        return None
    if _crossing_the_line(state):
        return None
    tag = f"saving-change-{state.saving_change_lap}"
    if tag in state.said_tags:
        return None
    return Call(SAVING_CHANGE, state.lap, note, "", tag=tag)


def _candidates(state: RaceState) -> list[Call | None]:
    return [
        _chequer(state),
        _laps_to_go(state),
        _green(state),
        # Above the box calls because it is the call that cancels one.
        _stops_off(state),
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
        _incident(state),
        _wear(state),
        _tyre_temp(state),
        _saving_change(state),
        _chase(state),
        _penalty(state),
        *_rivals(state),
        _status(state),
    ]


def _rivals(state: RaceState) -> list:
    """What the pit wall has to say about the other cars.

    Imported here rather than at the top because `race/rival_calls.py` imports
    this module for the vocabulary - the ranking is a property of the
    vocabulary and lives here, the composition lives there.
    """
    # **No short-circuit on `state.rivals`.** There was one, from when a
    # watched stop was the only input this had - and it silenced `stay_out`,
    # which is about OUR tank and needs no rival at all, along with both gap
    # calls. The guard survived the wiring of the other four and made three of
    # them unreachable a second time. `candidates` refuses cheaply and the
    # import is cached after the first crossing.
    from pitcrew.race import rival_calls

    return rival_calls.candidates(state)


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
    # **A timed race's count is an estimate and is said as one.** "21 laps"
    # at Deep Forest was the plan's distance; the flag fell on 20. The
    # number is still worth saying - it is what every "to the flag" figure
    # rests on - but the driver has to hear that it can move by one.
    if state.laps_total and state.race_minutes is not None:
        laps = f"About {state.laps_total} laps on the clock."
    else:
        laps = f"{state.laps_total} laps." if state.laps_total else ""
    # **"No notes for this circuit" is said HERE or it is never said.**
    #
    # The briefing is what makes George anything other than generic - the
    # measured pit loss, the tow, what a stop is worth against the cars around
    # him - and a race can arrive without one. Falling back to the model is
    # right; falling back silently is the defect pattern that made the gauge
    # ratchet invisible for a whole race, where the number setting the bar
    # never appeared anywhere he could see it.
    #
    # The green is the only crossing where it is both true and free: nothing
    # else is competing, and by lap two it is news about a decision already
    # taken.
    if state.no_notes:
        laps = f"{laps} {NO_NOTES}".strip()
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
    if state.laps_missed():
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


def fuel_reaches_flag(state: RaceState) -> bool | None:
    """Whether the fuel aboard covers the rest of the race, margin included.

    `None` where it cannot be known - no burn, no lap count - and `None` is
    never read as yes. This is a projection off a measured burn, not a
    reading, so it carries the same margin `fuel_to_flag_l` sizes a fill with.
    """
    if not state.fuel_per_lap_l or state.fuel_l is None:
        return None
    remaining = state.laps_remaining()
    if remaining is None:
        return None
    margin_l, _ = fuel_margin_l(remaining, state.fuel_per_lap_l,
                                sd_l=state.fuel_sd_l,
                                timed=state.race_minutes is not None,
                                lap_count_firm=state.laps_estimate_firm)
    needed = stint_burn_l(state.fuel_per_lap_l, remaining, state.fuel_l,
                          reference_load_l=state.fuel_reference_load_l)
    return state.fuel_l >= needed + (margin_l or 0.0)


def stop_still_needed(state: RaceState) -> bool:
    """Whether the next planned stop is still a stop.

    **A fuel-bound stop that the fuel no longer needs is not a stop.** Fuji,
    Round 4: the plan was fuel-bound, three stops, and the tyre was good for
    20.7 laps of a 20-lap race - so every stop in it existed to put fuel in.
    He took 94.0 L on lap 6 with fourteen laps to run and a burn of 6.0 L, and
    was then told to box twice more for fuel he was already carrying. He
    ignored both, finished P5, and crossed the line with 8.3 L aboard.

    Three things keep a stop, and each is a different kind of claim:

    * **The plan was not fuel-bound.** A stop for the tyre is not answered by
      a tankful, and `binding_constraint` is the plan's own word for which it
      was. Where the plan does not say, the stop stands - CLAUDE.md §4.3, an
      unknown is not a no.
    * **The regulations require one.** `events.mandatory_stops` is a real
      column, so this is a count: Fuji required one, he took it on lap 6, and
      it was satisfied from that moment. `None` would keep the stop, and the
      first draft of this made it `None` always - which kept every stop and
      made the whole rule dead code.
    * **The fuel does not actually reach**, which is the arithmetic this is
      about, and `None` from it keeps the stop for the same reason.
    """
    if state.drop_stop_granted is False:
        # The tank may say otherwise; dropping a stop is the desk's to
        # grant, and it was not.
        return True
    return _stop_needed_on_fuel(state)


def _stop_needed_on_fuel(state: RaceState) -> bool:
    """`stop_still_needed` on the arithmetic alone, grant or no grant."""
    if state.mandatory_stops_left is None or state.mandatory_stops_left > 0:
        return True
    if (state.plan_binding_constraint or "").lower() != "fuel":
        return True
    return fuel_reaches_flag(state) is not True


def _stops_off(state: RaceState) -> Call | None:
    """Said once, when the tank stops being the reason to come in.

    It has to be a call and not a silence. Suppressing the box call alone
    would leave a driver who was told "Box in 2" hearing nothing on the lap
    the stop was due - and silence there reads as the app having died, not as
    the plan having changed.
    """
    if state.stops_off_said or state.in_pit or state.finished:
        return None
    if state.stint_ends_on_lap is None or state.lap < 1:
        return None
    if _stop_needed_on_fuel(state):
        return None
    remaining = state.laps_remaining()
    spare = None
    if state.fuel_l is not None and state.fuel_per_lap_l and remaining:
        spare = state.fuel_l - remaining * state.fuel_per_lap_l
    reason = (f"{spare:.0f} litres more than the flag needs."
              if spare is not None and spare >= 1 else "")
    # **A `drop_stop`, under `fuel_long`.** The desk that wrote
    # `fuel_long: report_only` hears "You're fuelled to the flag." and the
    # litres, and the stops stay in the plan for the driver to decide.
    return Call(STOPS_OFF, state.lap,
                "You're fuelled to the flag. No more stops on fuel.",
                reason, structural_action="drop_stop", trigger="fuel_long",
                report_form="You're fuelled to the flag.")


def _tyre_word(state: RaceState) -> str:
    """The tyre half of the box call, from the plan's decision.

    "No tyres." when the plan says fuel only - the two words the driver was
    never given at Deep Forest. "RS on." when it says a set goes on, so the
    word is a decision rather than a label. A bare "RS." when the plan names
    a compound and says nothing about changing - the old sentence, kept for
    plans written before the field existed rather than guessed either way.
    """
    if state.next_tyres is False:
        return " No tyres."
    if state.next_compound:
        return (f" {state.next_compound} on." if state.next_tyres
                else f" {state.next_compound}.")
    return " Tyres on." if state.next_tyres else ""


def _box_now(state: RaceState) -> Call | None:
    to_stop = state.laps_to_stop()
    if to_stop is None or state.in_pit or state.finished:
        return None
    if not stop_still_needed(state):
        return None
    if to_stop > 0 or _crossing_the_line(state):
        return None

    fuel = _fuel_instruction(state)
    compound = _tyre_word(state)
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
    if state.drop_stop_granted is False and not _stop_needed_on_fuel(state):
        # He has heard "You're fuelled to the flag." and now hears the box
        # call anyway: say why, or the two contradict each other.
        return Call(
            BOX_NOW, state.lap,
            f"Box this lap.{compound}",
            "On the plan. Fuel would reach the flag - dropping the stop was "
            "not granted.",
            severity=float(overdue),
        )
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
    if not stop_still_needed(state):
        return None
    if not 1 <= to_stop <= 2 or _crossing_the_line(state):
        return None
    # **The same clause `_box_now` carries, and for the same reason** (critic
    # pass 6). He has heard "You're fuelled to the flag." from `_stops_off`
    # and is now being told to box anyway; without the clause the two
    # contradict each other, and this is the call that arrives FIRST.
    reason = f"Stop {state.stint_index + 1}, on the plan."
    if state.drop_stop_granted is False and not _stop_needed_on_fuel(state):
        reason = ("Stop {}, on the plan. Fuel would reach the flag - dropping "
                  "the stop was not granted.".format(state.stint_index + 1))
    return Call(
        BOX_SOON, state.lap,
        f"Box in {to_stop}." if to_stop > 1 else "Box next lap.",
        reason,
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
    # **Only while the crossing is still ahead.** Once the line has been
    # crossed in the lane, `laps_remaining` already excludes the lap just
    # completed and the lap in progress is the out-lap, run in full. Before
    # it - at the box call on the crossing that starts the in-lap, or in the
    # box at a circuit whose line comes after the box - the lap in progress
    # is the in-lap, mostly driven before the fill, and comes off. The same
    # rule at both moments, so the box call and the hose-in figure name the
    # same laps (rule 13): the replay of Daytona s127 said "9 laps to the
    # flag" at the crossing and "8 laps to the flag" with the hose in.
    if state.crossed_in_box:
        return remaining
    return max(0, remaining - 1)


def _laps_the_fill_covers(state: RaceState) -> tuple[int | None, str | None]:
    """How many laps the fill has to cover, and which bound said so.

    **The last stop is sized by the flag. An intermediate stop is sized by the
    plan's next stint.** Those are the only two answers, and the plan's stint
    length never wins at a last stop in either direction:

    * A stop taken LATE - Deep Forest, 6 Sep 2026, lap 13 against a plan that
      said 11 - has fewer laps left than the stint says. The old rule took the
      larger of the two, so the 10-lap stint sized a 7-lap run home: 76 L
      called, 55-63 needed, 19.7 L over the line, 9.9 s parked at 2 L/s, and
      P2 lost by 8 s. The plan's stint was already stale the moment the stop
      moved.
    * A stop taken EARLY has MORE laps left than the stint says, and a fill
      to the stint would send him out to run dry. The old rule did get this
      direction right, which is why its comment defended only that case.

    Both are one rule: with no further stop planned, the laps still to run
    once the car leaves the box are the whole answer. `further_stop_planned`
    is None where nobody said (a state built by hand) and the plan's stint is
    then taken at its word, as before.

    The second value names the bound so the spoken figure can carry it - "7
    laps to the flag" and "the next 9-lap stint" are different claims and the
    driver has to be able to tell which one he is hearing (CLAUDE.md rule 12).
    """
    remaining = _laps_after_this_stop(state)
    # **The frame travels with the count (rule 13).** "N laps to go" in the
    # heartbeat counts the lap in progress; the fill before the crossing does
    # not, so it is said as "after the box" and never as "to the flag" until
    # the two counts are the same number.
    frame = "laps to the flag" if state.crossed_in_box else "laps after the box"
    if state.next_stint_laps is not None:
        if state.further_stop_planned is False and remaining is not None:
            return remaining, f"{remaining} {frame}"
        stint = state.next_stint_laps
        return stint, f"the next {stint}-lap stint"
    if (state.stint_ends_on_lap is not None and state.laps_total
            and not state.in_pit and state.lap < state.stint_ends_on_lap):
        # The box is still laps away: the fill it will need starts at the
        # planned box lap, not at the current lap. Labelled as the plan's.
        laps = state.laps_total - state.stint_ends_on_lap
        if laps > 0:
            return laps, f"{laps} laps after the planned box"
    if remaining is not None:
        return remaining, f"{remaining} {frame}"
    return None, None


def fuel_target_basis(state: RaceState) -> str | None:
    """The bound behind `fuel_target_l`, in words, or None where there is no
    figure. Said with the litres, in the box call and again with the hose in,
    so the two sentences cannot name the same number for different reasons."""
    if not state.fuel_per_lap_l or state.laps_remaining() is None:
        return None
    _laps, basis = _laps_the_fill_covers(state)
    return basis


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
    after_stop, _basis = _laps_the_fill_covers(state)
    if after_stop is None:
        return None
    margin_l, _ = fuel_margin_l(after_stop, state.fuel_per_lap_l,
                                sd_l=state.fuel_sd_l,
                                timed=state.race_minutes is not None,
                                lap_count_firm=state.laps_estimate_firm)
    # Solved, not multiplied: the fuel is its own weight, so a smaller fill
    # burns less and permits a smaller fill again. Identical to the old
    # product when `fuel_reference_load_l` is None.
    return fill_for_l(state.fuel_per_lap_l, after_stop,
                      reference_load_l=state.fuel_reference_load_l,
                      buffer_l=(margin_l or 0.0),
                      capacity_l=state.fuel_capacity_l)


def fuel_to_flag_l(state: RaceState) -> float | None:
    """What the tank needs at pit exit to reach the flag without stopping again.

    **The number the driver was not given, at the moment he needed it.** Fuji,
    20:27:19, with the hose already in: *"Go. 71 litres aboard - that already
    covers it."* True for the approved plan, whose next stint was four laps.
    He was not driving that race - he had ignored the box call twice by then
    and ran to the flag - and fifteen laps at the measured burn wanted about
    92 L. He filled the tank instead, crossed the line with 8.276 L aboard,
    and that is 8.3 s stationary at the measured 1.001 L/s.

    Nothing in the app produced this figure at the box. `fuel_target_l` sizes
    the NEXT STINT whenever a further stop is planned, which is right for the
    plan and silent about the alternative the driver is actually weighing. So
    it is computed alongside and spoken beside it, and he picks - which is the
    charter's division of labour: the engineer supplies the number, the driver
    makes the call.

    None where it cannot be sized, or where the tank cannot hold it anyway -
    a figure he cannot act on is not worth the words.
    """
    if not state.fuel_per_lap_l:
        return None
    remaining = _laps_after_this_stop(state)
    if remaining is None:
        return None
    margin_l, _ = fuel_margin_l(remaining, state.fuel_per_lap_l,
                                sd_l=state.fuel_sd_l,
                                timed=state.race_minutes is not None,
                                lap_count_firm=state.laps_estimate_firm)
    needed = fill_for_l(state.fuel_per_lap_l, remaining,
                        reference_load_l=state.fuel_reference_load_l,
                        buffer_l=(margin_l or 0.0),
                        capacity_l=state.fuel_capacity_l)
    capacity = state.fuel_capacity_l
    if capacity and needed > capacity:
        return None
    return needed


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
    #
    # **And the bound travels with the number.** "Fuel to 76" sized by a
    # 10-lap stint and "Fuel to 63" sized by 7 laps to the flag are different
    # instructions; without the clause the driver cannot tell a stale plan
    # from the race (rule 12).
    basis = fuel_target_basis(state)
    clause = f" - {basis}." if basis else "."
    return f"Fuel to {math.ceil(litres):.0f} litres{clause}"


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
        # **A shortfall no lever can cover is a stop, and is said as one.**
        # The Deep Forest race sim heard "Short-shift and lift into the slow
        # corners" three times while 6-8 laps short of the flag with no stop
        # planned: a saving of a fifth of the burn cannot close a gap of
        # that size, so the honest instruction is the stop. Priced against
        # what the laps still to run could save at the most a short-shift is
        # worth, plus the half-lap the call's own threshold allows.
        remaining = state.laps_remaining()
        if (remaining is not None and state.stint_ends_on_lap is None
                and not state.stop_pending
                and abs(gap) > SHORT_SHIFT_RECOVERY * remaining
                + FUEL_SHORT_LAPS):
            return Call(FUEL_SHORT, state.lap,
                        "Fuel needs a stop.",
                        f"{abs(gap):.1f} laps short of the flag - short-shifting "
                        f"cannot cover it.", confidence, severity=-gap)
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
            # **The reference is load-bearing and it was missing.** The colour
            # line says "Fuel: N laps in hand" against the FLAG, this one said
            # it against the STOP, and at Fuji they were spoken two minutes
            # apart - "9.4 laps of fuel in hand" at 20:29:34 and "Fuel: 0.6
            # laps in hand" at 20:31:33. Same words, quantities ten laps
            # apart, no reference stated in either. Under a helmet that is
            # CLAUDE.md 5.5's failure mode exactly.
            #
            # It said "to the box" as a constant, which was right until a stop
            # could be cancelled: `stop_still_needed` retires one mid-race, and
            # a fixed word then names a box the driver is no longer driving to.
            # `fuel_reference` comes off the same expression as the figure.
            f"{gap:.1f} laps of fuel in hand {fuel_reference(state)}.",
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


def _incident(state: RaceState) -> Call | None:
    """The lap the car stopped on has left the count. Said once.

    **What this is for is the assumption, not the news.** He knows he went off.
    What he cannot know is that the app noticed - and the app noticing is what
    keeps the lap out of the pace median, out of the fuel rate and out of every
    aggregate that would otherwise read the off as the car being slow. Told
    nothing, a driver who has just lost fifteen seconds has to assume his
    engineer is now planning around them.

    It is also the only chance to be corrected. The detector is one signal, and
    if it has struck the wrong lap the driver is the only one who can say so -
    which he cannot do if he was never told which.
    """
    if state.incident_lap is None or state.in_pit or state.finished:
        return None
    lap = state.incident_lap
    cost_ms = state.incident_cost_ms
    reported = state.incident_reported
    if state.lap - lap > INCIDENT_STALE_LAPS:
        # **Held for a lap or two, then dropped.** It can lose a crossing to a
        # box call, and being told on the next one is a lap late but still
        # true. Two laps on it is not news, and `record` never got the chance
        # to clear it, so it is cleared here.
        state.incident_lap = None
        state.incident_cost_ms = None
        state.incident_reported = False
        return None
    if reported:
        # Nothing will be spoken, so nothing will be recorded, so this is the
        # only place it can be cleared.
        state.incident_lap = None
        state.incident_cost_ms = None
        state.incident_reported = False
        # He said it first and was answered then. The app has nothing to add
        # and repeating it would be the engineer talking to himself.
        return None
    if cost_ms is None or cost_ms < INCIDENT_WORTH_SAYING_MS:
        # **No pace reference, or it cost nothing worth a number.** The lap is
        # still out - the exclusion is not in the driver's gift - but a figure
        # the race has not earned must not be spoken beside it.
        return Call(INCIDENT, state.lap, f"Lap {lap} is out.",
                    "You stopped on it.", HIGH)
    return Call(
        INCIDENT, state.lap,
        f"Lap {lap} is out.",
        f"That cost you {cost_ms / 1000:.0f} seconds.",
        HIGH,
        severity=cost_ms / 1000.0)


def _wear_worst(wear: dict[str, float]) -> tuple[str, float]:
    """The corner that ends the stint, and how worn it is.

    **The worst single corner, never an axle mean.** A car eating one corner is
    exactly what open tuning without BoP produces - his own eight gauge
    readings put RL worst every time - and averaging it with its healthy pair
    halves the number that decides when to stop.
    """
    return max(wear.items(), key=lambda kv: kv[1])


# Where a wear rate came from. It decides what may be said out loud about it.
GAUGE = "gauge"          # fitted from this stint's own readings
BRIEFED = "briefed"      # measured off a replay of an earlier race, carried in


def _wear_rate(state: RaceState) -> tuple[float | None, str | None]:
    """Fraction of the worst corner consumed per lap, and where it came from.

    **The live fit first, the briefed rate second, and never the other way
    round.** A slope fitted from this stint's own gauge readings is about
    these tyres on this fuel load at this pace; a briefed rate is about a race
    already driven. Where both exist the live one is better evidence.

    **The briefed rate is why this exists at all.** In VR the gauge reads
    about 6 crossings in 22 - GT7 draws the HUD on the car's dashboard in 3D
    and it moves with his head - so `_live_rate` returns None for most of most
    races, and wear is the quantity the whole strategy rests on. Measured off
    the replay afterwards it is good to 0.5%, against a model that was ~21%
    low, and `race/knowledge.py` is what carries it into the next race.
    """
    live = _live_rate(state)
    if live is not None:
        return live, GAUGE
    if state.briefed_wear_per_lap:
        return state.briefed_wear_per_lap, BRIEFED
    return None, None


def _live_rate(state: RaceState) -> float | None:
    """Fraction of the worst corner consumed per lap, from this stint's gauge.

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


@dataclass(frozen=True)
class WearView:
    """Where the tyre is, how it was worked out, and what was actually read.

    **`reading` and `consumed` are different numbers and the difference is the
    point.** The reading is a transcription of the game's own gauge and may be
    spoken plainly. `consumed` is that reading carried forward at the fitted
    rate - a projection, and CLAUDE.md 4.5 forbids presenting one as a
    measurement. Decisions are taken on the projection, because that is where
    the tyre actually is; every number said out loud is the reading, because
    that is what was measured. Conflating them had the engineer saying
    "RL measured at 99 percent" off a gauge that read 88.

    `reading` is `None` on the briefed path, where the gauge never read at all
    and there is nothing measured to quote.
    """
    laps_left: float
    corner: str
    reading: float | None
    consumed: float
    source: str


def _wear_laps_left(state: RaceState) -> WearView | None:
    """How much stint is left, from the gauge if it read and the briefing if not."""
    # **Nothing through an unconfirmed stop.** The history is the OLD set's
    # until the gauge or the driver says which set is on, and a projection
    # from it - "Box this lap. FR at 42 percent, measured." on the out-lap of
    # a fresh set - is the Deep Forest failure with the word "measured"
    # attached. Silence here is the honest answer for a lap or two; the
    # heartbeat still asks for the gauge.
    if state.tyre_change_unconfirmed:
        return None
    rate, source = _wear_rate(state)
    if rate is None:
        return None

    fresh = state.wear_history and (
        state.lap - state.wear_history[-1][0] <= WEAR_MAX_STALENESS_LAPS)
    if fresh:
        lap, wear = state.wear_history[-1]
        corner, worn = _wear_worst(wear)
        consumed = worn + rate * max(0, state.lap - lap)
        return WearView((WEAR_STINT_LIMIT - consumed) / rate, corner, worn,
                        consumed, source)

    # --- nothing readable, and a rate measured off an earlier race ----------
    #
    # **This is the VR case, and it is the normal one.** GT7 draws the HUD on
    # the car's dashboard in 3D, so the gauge moves with his head and reads
    # about 6 crossings in 22; a wear model that needs three readings in a
    # stint therefore says nothing for most of most races. Anchored at a fresh
    # set instead - which is a fact, not a reading: the bar is full white the
    # moment new rubber goes on - and carried forward at the measured rate.
    #
    # **Only on a briefed rate.** A live fit needs readings by definition, so
    # reaching here with `GAUGE` is impossible; and projecting from a stale
    # reading was already refused above, because a projection from a reading
    # four laps old is about a tyre he was on rather than the one he is on.
    if source != BRIEFED or state.laps_since_stop is None:
        return None
    consumed = rate * max(0, state.laps_since_stop)
    return WearView((WEAR_STINT_LIMIT - consumed) / rate, "worst", None,
                    consumed, source)


def _wear(state: RaceState) -> Call | None:
    """What the gauge says, when it says something he can act on."""
    if state.in_pit or state.finished or _crossing_the_line(state):
        return None
    projection = _wear_laps_left(state)
    if projection is None:
        return None
    laps_left = projection.laps_left
    consumed = projection.consumed
    reading = projection.reading
    name = projection.corner.upper()
    # **"measured" is only sayable about a gauge that actually read.** On the
    # briefed path there is no reading at all - the rate was measured off the
    # replay of an earlier race and the anchor is a fresh set - so the word
    # would be a projection wearing a measurement's clothes, which is the
    # single most repeated defect in this codebase.
    briefed = projection.source is BRIEFED or projection.source == BRIEFED
    # And the confidence follows the evidence: a rate from THESE tyres on THIS
    # fuel load beats one carried in from a race already driven.
    sure = MEDIUM if briefed else HIGH

    # --- past the limit. An instruction, and the reading is enough on its own.
    if consumed >= WEAR_STINT_LIMIT and "cliff" not in state.wear_said:
        # **An `add_stop` when no stop was planned** - the plan's shape
        # changes, and the desk has to have granted it under `tyre_short`.
        # With a stop still ahead this brings it forward, which is timing,
        # and timing is free. Withheld, the reading still reaches him.
        unplanned = state.stint_ends_on_lap is None
        rail = dict(structural_action="add_stop" if unplanned else None,
                    trigger="tyre_short",
                    report_form="Tyres past the stint limit.")
        if briefed:
            return Call(
                WEAR, state.lap,
                "Box this lap.",
                f"Tyres are past the stint limit on the measured rate for "
                f"this compound. No gauge reading this stint.",
                MEDIUM,
                severity=consumed,
                tag="cliff", **rail)
        return Call(
            WEAR, state.lap,
            "Box this lap.",
            f"{name} measured at {reading * 100:.0f} percent.",
            HIGH,
            severity=consumed,
            tag="cliff", **rail)

    # --- the tyres run out before the fuel does.
    fuel_laps = state.laps_of_fuel()
    if (fuel_laps is not None and "limited" not in state.wear_said
            and 0 < laps_left <= WEAR_PROJECT_MAX_LAPS
            and laps_left + 1 < fuel_laps):
        # **+1 before it is a finding.** The two figures are a fitted gauge
        # slope and a fuel burn, and inside a lap of each other the ordering is
        # noise - which would have him stopping early on the strength of it.
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
            ("On the measured rate for this compound. No gauge reading "
             "this stint." if briefed
             else f"{name} at {reading * 100:.0f} percent, measured."),
            MEDIUM,
            severity=consumed,
            tag="limited")

    # --- one corner going first. A balance call, not a pit call.
    #
    # **Never on the briefed path.** A rate is one number for the worst
    # corner; which corner is going first is a fact about four bars, and there
    # are no bars to read here. Inventing an axle would send him to the brake
    # balance on the strength of nothing.
    if briefed:
        return None
    ordered = sorted(state.wear_history[-1][1].values(), reverse=True)
    if (len(ordered) >= 2 and "asymmetry" not in state.wear_said
            and ordered[0] - ordered[1] >= WEAR_ASYMMETRY):
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
                severity=ordered[0],
                tag="asymmetry")
        return Call(
            WEAR, state.lap,
            "Brake balance one click rearward.",
            f"{name} is going first - {ordered[0] * 100:.0f} percent "
            f"against {ordered[1] * 100:.0f}, measured.",
            HIGH,
            severity=ordered[0],
            tag="asymmetry")
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
    if since is None or since < max(1, state.status_every_laps):
        return None
    where = f"P{state.position}." if state.position else ""
    said = " ".join(part for part in (orientation(state), where,
                                      _fuel_standing(state),
                                      _gauge_ask(state)) if part).strip()
    if not said:
        return None
    return Call(STATUS, state.lap, said, "")


# **What a short-shift can recover, as a fraction of the remaining burn.**
# Measured in-house on v1.71 at about a fifth (-21.6% fuel, brain/_inbox/17
# s4). A shortfall larger than this over the laps still to run is a stop.
SHORT_SHIFT_RECOVERY = 0.20


# How many agreeing frames a new position needs before it is believed.
#
# **Not a de-bounce for a noisy field - a guard against a true one.** The
# position byte is exact; what is not exact is the moment it turns over. A
# side-by-side into a braking zone swaps the two cars for a handful of frames
# and swaps them back, and "down to P8, up to P7, down to P8" inside two
# seconds is three sentences about nothing. A third of a second was not
# enough: Deep Forest lap 5 (6 Sep 2026) produced P2 / P3 / P2 / P3 seven
# times in nineteen seconds through one side-by-side, each with a
# championship line behind it. A place is a place once it has been held for
# eight seconds - the length of a straight - and a battle that has not
# settled in that time is one the driver is in, not one he needs told about.
POSITION_HOLD_FRAMES = 8 * 60

# Places gained or lost in one step past which this is not a place change.
# A restart, a re-grid, or the field being renumbered around a pit sequence
# moves the byte by more than anyone overtook. Said as a plain position
# rather than as a gain or a loss, because the count would be a fiction.
POSITION_MAX_STEP = 3


def position_change(state: RaceState) -> "Call | None":
    """A place gained or lost, ready to say. `None` when there is no news.

    Called from `RaceCoordinator.note_packet` on the telemetry thread and
    therefore **on a frame, not on a crossing** - which is the point: he
    should hear about a place while it is still the thing that just happened.

    Silent in the pit lane and on either side of it. Positions during a stop
    are arithmetic about cars that are still circulating, every one of them
    reverses on exit, and none of it is a place he won or lost on the road.
    """
    if state.finished or state.in_pit or state.lap < 1:
        return None
    now = state.position
    if not now:
        return None
    was = state.position_said
    if was is None:
        # The first reading is the baseline, not news. He knows where he
        # started; what he cannot see is the next change.
        state.position_said = now
        return None
    if now == was:
        state.position_pending = 0
        state.position_pending_value = None
        return None
    if now != state.position_pending_value:
        state.position_pending_value = now
        state.position_pending = 1
        return None
    state.position_pending += 1
    if state.position_pending < POSITION_HOLD_FRAMES:
        return None

    state.position_said = now
    state.position_pending = 0
    state.position_pending_value = None
    places = was - now                      # positive is a gain
    # **The position IS the call and the direction is the reason**, which is
    # §5.5's shape - the figure first, the why second and short - and it is
    # also what keeps the voice pack affordable. A position carries two
    # numbers ("P6 of 12") and `phrase_manifest` cannot peel two, so this
    # family has to be enumerated; written as "Up to P6 of 12." it would be a
    # second and third enumeration of the same 300 lines with a word bolted
    # on the front. Written this way it reuses the line the PTT answer to
    # "where am i" already renders, and the direction is six fixed clips.
    return Call(POSITION, state.lap, position_line(now, state.field_size),
                _places_moved(places))


def position_line(position: int, field_size: int | None) -> str:
    """`P6 of 12.` - the one rendering of a position in the whole app.

    Shared by the engineer's own call and by the PTT answer to "where am i",
    so the two can never drift into saying it differently, and so the voice
    pack renders one family rather than two.
    """
    if field_size:
        return f"P{position} of {field_size}."
    return f"P{position}."


def _places_moved(places: int) -> str:
    """Why the position changed, in the six ways it can be said.

    Empty above `POSITION_MAX_STEP`: a restart or a re-grid moves the byte by
    more than anyone overtook, so the position is still real and the count
    would be a fiction. Rule 3 - the honest answer is to say nothing about it
    rather than to say a number nobody measured.
    """
    if not places or abs(places) > POSITION_MAX_STEP:
        return ""
    if places > 0:
        got = "a place" if places == 1 else f"{places} places"
        return f"You've made {got}."
    lost = "a place" if places == -1 else f"{-places} places"
    return f"You've lost {lost}."


def fuel_reference(state: RaceState) -> str:
    """Which distance `_fuel_gap` is a gap TO, named.

    **Rule 13, and this is the call that would break it.** `_fuel_target`
    returns laps-to-the-stop while a stop is still to come and laps-to-the-flag
    once the box lap has gone by, so the same two words - "fuel good" - mean
    figures ten laps apart on either side of one crossing. The rule is on file
    from a race where "laps in hand" was spoken twice in two minutes meaning
    both: *"under a helmet the driver cannot ask which one he just heard."*

    Said every lap, an unnamed reference is that mistake made twenty times. So
    the reference is not optional and not a suffix - the sentence is not built
    without it.
    """
    return fuel_frame(state)[1]


def fuel_in_hand(state: RaceState) -> tuple[float | None, str]:
    """The fuel margin AND the distance it is a margin to, from one expression.

    **The colour line computed its own and got a different answer.** Session
    127 (Daytona, 4 Sep 2026), lap 2, 22:16:52: *"-7.1 laps of fuel in hand to
    the flag."* - a negative, spoken aloud, with **84.0 L aboard on a plan
    whose stop was nine laps away.** Twenty-six seconds earlier on the same
    lap, `_fuel_standing` had said *"1.9 spare to the stop."* Two numbers,
    both introduced as spare/in hand, 9.0 laps apart, inside half a minute -
    CLAUDE.md rule 13 verbatim, and rule 13 exists because this exact
    confusion happened before.

    The model was never wrong. Reproduced against the stored laps of that
    race, the old expression - tank divided by burn, minus laps to the FLAG,
    with no term for the litres the planned stop would add - returns the
    spoken figure to the tenth on all five laps it was said on: **-7.2, -7.2,
    -7.1 before the stop (spoken -7.1, -7.2, -7.1) and +0.2, +0.2 after it
    (spoken 0.2, 0.2)**. It is right after the stop precisely because there is
    no stop left to account for; he took the flag with 1.444 L = 0.185 laps,
    against a call of 0.2.

    So the fix is not arithmetic on the fill. It is that **the supply and the
    distance have to be the same journey** - CLAUDE.md rule 12, the reported
    reason must come from the same expression that produced the decision.
    `fuel_frame` already picks that journey for `_fuel_standing`: the stop
    while a stop is still to come, the flag once it is not. This returns its
    gap and its name together so no caller can take one without the other,
    and the tank-only supply is then correct by construction - it is only ever
    asked to reach the next place fuel is added.

    Returns `(None, reference)` where the burn or the distance is unknown. A
    surplus computed against a burn nobody measured is a number he would plan
    around, and the reference is still named so a caller can say what it could
    not tell him about.
    """
    gap = _fuel_gap(state)
    reference = fuel_reference(state)
    return (None if gap is None else round(gap, 1)), reference


# Past this fraction of a timed race, he wants the laps as well as the clock.
# **His call, and it matches the measurement.** The estimate is
# `ceil(time left / lap)`, which is unresolvable early - on a real 30-minute
# race the first four crossings would have flipped on a median error of
# 0.12-0.66 s against a 2.04 s spread - and firms up as the remaining time
# shrinks. "From the half way point I want time and laps remaining", 28 Aug
# 2026.
LAPS_FROM_FRACTION = 0.5

# What he hears when the race clock is not available. **Said, not skipped**:
# with GT7's race HUD off, a race with no clause about its own length is
# indistinguishable from one with no end, and from an app that has died.
NO_CLOCK = "I don't have the clock."


def minutes_left(state: RaceState) -> str:
    """The clock, in the only unit that is a measurement rather than a guess.

    **Minutes are measured; the lap count is inferred over a noisy median.**
    The app timer runs from the green and is reconciled against GT7's own
    exact lap figures, so the seconds are as good as the green detection. The
    lap estimate divides them by a median lap and is therefore wrong whenever
    the median is - which is the whole argument of `laps_estimate_firm`.

    With GT7's race HUD off, this is his only clock.
    """
    left = state.race_remaining_s
    if left is None:
        return ""
    # **Under one hundred, not under two minutes.** The pack renders number
    # words to `MAX_LAPS`, which is 99, so "119 seconds left." cannot be split
    # into a number and a tail and falls whole to live synthesis - a pause in
    # the last two minutes of the race. Ninety-nine seconds is also the point
    # past which minutes are the unit he thinks in.
    if left < 100:
        return f"{max(0, int(left))} seconds left."
    # **Rounded DOWN, never to nearest.** At 91 s to-nearest says "2 minutes
    # left", overstating by 29 s at the moment of the race where 29 s is a
    # third of a lap - and the green-detection lag already runs the clock
    # long by an unmeasured amount in the same direction. Two overstatements
    # compounding is how he plans a lap he does not have.
    minutes = int(left // 60)
    return f"{minutes} minute left." if minutes == 1 else         f"{minutes} minutes left."


def laps_to_go(laps: int, *, uncertain: bool = False) -> str:
    """`N laps to go.`, with its unit, because it is never said alone.

    It arrives beside a clock in the same breath, and "11 minutes left, 9 to
    go" names the unit of one figure and not the other - where the unnamed one
    is the figure he plans around. Rule 13 is on file for exactly that.

    **The uncertain pair runs DOWNWARD, and that is not cosmetic.** Every
    known error in this count is in the same direction - it reads long. The
    stop discount uses `pit_loss_s`, which is measured ex-fuel and is
    therefore too small, so the ceiling comes out high; with no pit loss
    measured at all there is no discount and it is a whole stop high; and the
    achieved median is dragged down by fresh-tyre laps, so a stint in phase 2
    is slower than the divisor. `N or N+1` asserts the truth may be higher
    than the estimate, which is the one thing it cannot be - and it was the
    same defect as "Lap 20 or 22", a pair that excludes the truth, in the
    other clause of the same sentence.
    """
    if uncertain and laps > 1:
        return f"{laps - 1} or {laps} laps to go."
    return f"{laps} lap to go." if laps == 1 else f"{laps} laps to go."


def orientation(state: RaceState) -> str:
    """Where he is: the lap, and how much race is left.

    **He turned GT7's race-information HUD off on 28 Aug 2026** - lap number,
    position and time remaining all came off the screen, leaving car
    information only. So none of this is a duplicate of something he can see;
    it is the only place it exists. That is also why an unknown is said rather
    than dropped: a clause that silently vanishes leaves him with no way to
    tell "nothing to report" from "the app has lost the clock".

    Ordering is orientation, then field, then consumable. **Not BLUF** - that
    governs calls which instruct, and this one instructs nothing. The fuel
    clause goes last because it is the one that escalates into next lap's
    instruction, and the last clause is the one retained under a helmet.
    """
    # **The count decides whether there is anything to say; the SCREEN number
    # is what gets said.** They are one apart - see `RaceState.lap_on_screen`
    # - and saying the count made every heartbeat of session 127 name a lap
    # the driver had already finished.
    done = state.lap_now()
    if done < 1:
        return ""
    lap = state.lap_on_screen()
    # **The corrected number, flat.** This said "Lap 20 or 22" at Road
    # Atlanta's measured drop of two - a pair that excludes the truth - and
    # the same breath then said "9 laps to go", which comes from
    # `laps_remaining()` and treats the correction as certain. One quantity
    # cannot be uncertain in one clause and certain in the next.
    #
    # It is certain enough to say flat: the correction comes from GT7's own
    # `laps_completed`, which is the authority here and the whole reason the
    # count is taken from it rather than from the app's own crossings.
    where = f"Lap {lap}"

    # **One number per sentence, deliberately.** The voice pack plays a call
    # by peeling known sentences off the front and splitting what is left on
    # its single number; a sentence carrying two splits into nothing and the
    # whole line falls through to live synthesis - a pause, on every crossing
    # of the race, at the cadence he asked for. It is also better radio: three
    # short units survive a helmet better than one long one.
    if not state.race_minutes:
        left = state.laps_remaining()
        return f"{where}. {laps_to_go(left)}" if left else f"{where}."

    clock = minutes_left(state)
    if not clock:
        # **Said, not skipped.** With the HUD off, a race with no clause about
        # its own length is indistinguishable from one with no end.
        return f"{where}. {NO_CLOCK}"

    duration = state.race_minutes * 60.0
    left = state.race_remaining_s or 0.0
    if left > duration * (1.0 - LAPS_FROM_FRACTION):
        return f"{where}. {clock}"

    # **`laps_remaining()`, not `laps_to_go_estimate`.** The two agree once
    # the coordinator has recomputed the distance, but only the accessor
    # applies the missed-crossing correction - and a lap the app never saw is
    # exactly the error this call exists to stop him inheriting.
    # **One count, and it is the one everything else uses.** A second,
    # stop-discounted figure lived here and was wrong twice over: inside
    # `laps_total` it moved the race distance under the whole fuel path, and
    # once isolated it disagreed with the answer push-to-talk and the colour
    # line give to the same question in the same words - two numbers, one
    # phrase, and he cannot ask which one he just heard.
    laps = state.laps_remaining()
    if laps is None or laps < 1:
        # Under one lap the count has run out before the flag has fallen, and
        # "0 or 1 laps to go." is not a thing to say - nor is it in the pack.
        # The run-in owns this ground: `_laps_to_go` says "Last lap."
        return f"{where}. {clock}"
    cost = state.stop_costs_laps
    if state.stop_pending and cost and laps > cost:
        # **The count is what he gets if he stays out, and the stop is priced
        # from the model.** Discounting it instead assumed he takes it, and he
        # may not - he skipped one in two recorded races and was right both
        # times. Asserting a flat "one less" was worse still: on the two timed
        # races on file the stop costs no lap at all on 15 of the 18 crossings
        # this is spoken, so a constant told him there was less race than
        # there is on five sixths of them.
        #
        # Silent when the stop costs nothing, which is the common case, and
        # silent when nothing has measured a stop here - `stop_costs_laps` is
        # `None` there and an unmeasured cost may not be spoken as one.
        fewer = "one" if cost == 1 else str(cost)
        return (f"{where}. {clock} {laps_to_go(laps)[:-1]}, "
                f"{fewer} less if you stop.")
    # **Both candidates when it genuinely is both.** `ceil` flips when the
    # time left is near a whole number of laps, and there the answer is not
    # unknown - it is one of two. Naming them beats picking one, and beats the
    # silence this used to fall to.
    return (f"{where}. {clock} "
            f"{laps_to_go(laps, uncertain=state.laps_count_hedged)}")


# Laps a gauge reading may be old before the engineer asks for another, and
# the tag under which the ask is remembered for the stint.
GAUGE_STALE_LAPS = 5

# **How the gauge settles an unconfirmed tyre change.** A fresh set reads at
# or under GAUGE_FRESH_SET_MAX on its worst corner AND has fallen by at least
# GAUGE_FRESH_SET_DROP from the last reading before the stop - the two halves
# together, because a set at 8% that reads 8% again is the same set, and a
# set at 60% that reads 40% is a gauge artefact, not new rubber. Deep Forest,
# 6 Sep 2026: 0.42 before the stop, 0.00 after. The same-set test is the
# series carrying on within a little slack for the gauge's own resolution.
# `telemetry/hud.FRESH_SET_MAX` is 0.15 - one definition of "fresh", not
# two (rule 13); it is restated here rather than imported because `hud`
# pulls in the screen-capture stack and this module runs at every crossing.
GAUGE_FRESH_SET_MAX = 0.15
GAUGE_FRESH_SET_DROP = 0.10
GAUGE_SAME_SET_SLACK = 0.03
GAUGE_ASK = "gauge-ask"


def _gauge_ask(state: RaceState) -> str:
    """Ask him to read the in-game wear gauge, inside the heartbeat.

    **It used to be a colour call and it cannot stay there.** The colour tier
    only speaks on a crossing that had nothing else to say, and at the
    every-lap setting the heartbeat has every crossing - so the tier retires
    for the race and this goes with it. Speaking both breaks §5.5's one thing
    at a time, which is on file from a race that produced two opposite
    instructions on one crossing.

    So it rides along. **It is the only wear evidence that exists in VR**,
    where the live reader made 553 attempts at Fuji and accepted none, and
    `colour._gauge`'s own docstring calls it worth more to the model than
    anything else said all race. A fourth clause once a stint is a cheap price
    for the thing the whole wear model rests on.
    """
    if GAUGE_ASK in state.said_tags or state.in_pit:
        return ""
    if state.wear_history:
        last_lap, _ = state.wear_history[-1]
        if state.lap - last_lap < GAUGE_STALE_LAPS:
            return ""
    elif state.lap < GAUGE_STALE_LAPS:
        # Early in a fresh set there is nothing to read yet worth reading.
        return ""
    return "Tyre gauge when you get a straight."


def _fuel_standing(state: RaceState) -> str:
    """Where the fuel stands, against a named distance, or an honest silence.

    Three outcomes and no fourth:

    * a gap, with what it is a gap to;
    * **no burn figure yet**, which is what `None` means and is said out loud.
      `laps_of_fuel` is `None` until a burn exists, and the race's own burn
      needs green laps to measure. Rendering that as "fuel good" would be
      §4.3 wearing a sentence - a confident, well-formed answer that no
      listener can tell from a real one.
    * nothing at all, before there is a lap to talk about.

    **What it may never say is anything about pace.** "On plan" is heard as a
    lap-time claim, and lap time is not detectable here: measured lap-to-lap
    sigma is 0.68-2.04 s against a 0.5-1.5 s/lap degradation band, so a pace
    verdict is a coin flip dressed as a finding. Said once a race that is a
    bad call; said every lap it is twenty of them.
    """
    if state.fuel_l is None:
        return ""
    if not state.fuel_per_lap_l:
        return "No burn figure yet."
    gap = _fuel_gap(state)
    if gap is None:
        return "No burn figure yet."
    reference = fuel_reference(state)
    if gap < -FUEL_STANDING_TOLERANCE_LAPS:
        return f"{abs(gap):.1f} short {reference} on current burn."
    if gap > FUEL_LONG_LAPS:
        return f"{gap:.1f} spare {reference}."
    return f"Fuel good {reference}."


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
    # An incident that had not been spoken by the time he pitted is stale: the
    # lap is still excluded, but "lap 12 is out" said on the way out of the
    # pits is news about a lap two minutes gone.
    state.incident_lap = None
    state.incident_cost_ms = None
    state.incident_reported = False
    state.last_stop_lap = state.lap
    state.tyre_change_disagreement = None
    state.stint_before_stop = None
    if tyres_changed:
        # Held, not dropped: a "no tyres" from the driver can still overrule
        # this session's swap detector, and it has to be able to restore
        # what it overrules (`note_tyres_word`).
        state.stint_before_stop = (state.laps_since_stop,
                                   list(state.wear_history),
                                   list(state.temp_history))
        state.laps_since_stop = 0
        state.tyre_change_unconfirmed = False
        state.unconfirmed_stop_lap = None
        state.unconfirmed_before = None
        state.parked_wear = []
        state.tyre_change_resolution = "session: swap seen"
        state.temp_history = []
        # **A rate fitted across a stop describes neither set.** The gauge
        # snaps back to white on a fresh set, so keeping the old points would
        # fit a line through a discontinuity and report a tyre that repairs
        # itself.
        state.wear_history = []
    elif tyres_changed is None:
        state.tyre_change_unconfirmed = True
        state.unconfirmed_stop_lap = state.lap
        state.tyre_change_resolution = None
        state.unconfirmed_before = (max(state.wear_history[-1][1].values())
                                    if state.wear_history else None)
        state.parked_wear = []
