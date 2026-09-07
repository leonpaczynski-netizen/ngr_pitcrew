"""The glance-up instrument for the screen above the game.

He came out of VR on 2 Sep 2026 and put a 2560x1080 ultrawide directly above
the PS5's monitor: *"I can glance up at it… tyre temps is probably my main
request in colour for ease of visibility, then laps to box and laps of fuel…
most of it will be verbal through George."*

**So this shows only what the game does not.** GT7 already gives him position,
gaps, lap, speed, gear, revs, a fuel bar, the wear gauge, the track map and
wind. Duplicating any of that spends the one thing a glance-up display has,
which is glance time. What it does not give him is a tyre temperature in
degrees - the game draws a coloured frame and nothing else - or fuel expressed
in laps, or where he is against the plan.

**The layout is anchored to the bottom.** He is looking down at the game and
glancing up, so the bottom edge of this screen is the shortest eye travel;
content sits there rather than centred - and once something is the priority,
that rule decides the order as well as the position.

**The gaps lead, on his own revision of the brief.** Tyre temperatures were
the original request and were first promoted to lead; seeing that, he settled
it differently: *"the temps can take a back seat and gaps can be the prominent
with trend and colour"*, because **he glances at this on the straights and
nowhere else.** On a straight the car ahead and the car behind are what he can
act on within seconds; the tyres are what he acts on over a stint. Both are on
the screen. Only one of them can be the first thing read.

So three ranks: the two neighbour gaps at the bottom edge, laps-to-box and
laps-of-fuel between them at the middle rank, and the four corners in the row
above. A display where everything is the same size has no priority at all,
which is where this one started.

### What the colours may and may not claim

**Nobody has ever published an optimal tyre-temperature window for GT7**, and
this app once carried a fabricated four-zone one with a cold side that had to
be ripped out (`store/tyres.py`). Temperature is endogenous: it is a
consequence of how hard the tyre is being worked, not an input to grip.

**That conclusion stands and the evidence under it has changed.** This file
used to say minimum corner speed against tyre temperature had "slopes of the
OPPOSITE SIGN at Monza and Spa with R^2 under 0.2". **It does not.** Those
were per-corner OLS fits on 8-11 laps; specified properly - corner x stint
fixed effects, `lap_in_stint` held, standard errors clustered by lap - both
slopes are negative and neither is significant (Monza -0.809, t -1.57; Spa
-0.227, t -0.29), and the two circuits differed by car, compound, wear
multiplier and race format as well, so the sign disagreement was the
instrument rather than the physics. What replaced it measures the mechanism
directly (4 Sep 2026, 48 Daytona laps): rear slip against rear temperature
inside a cell of the same 100 m, gear, speed band and throttle band gives
+0.002772 per degC, 18 of 22 cells positive against a permutation null of
47.0% - and **lagging the temperature by one second collapses the slope
146-fold and the positive share to exactly 50.0%.** Slip heats the tyre; the
tyre does not lose grip because it is hot. More laps still cannot fix it; it
needs temperature varied independently of driving.

So there are exactly two things a colour here is allowed to mean:

* **Past the wear-onset threshold** - RS 88, RM 90, RH 93 degC, sourced and
  measured by someone else, and explicitly a WEAR threshold rather than a grip
  window. There is no cold side because the author never tested one.
* **Well above its pair.** A corner ten degrees hotter than the tyre opposite
  is diagnostic whatever the optimum is, and it needs no window at all. This is
  the most useful mark on the display.

Anything cooler than onset is drawn in one neutral colour and claims nothing
beyond "not yet wearing faster for heat".

**And it is fed a 3-second mean, never a raw frame - which for a long time
was a claim this file made and the controller did not honour.** Per-lap peaks
reach 117.8 degC at Monza and 158.8 at Spa against an onset of 88-93, so a
display driven from instantaneous samples would sit red almost permanently and
mean nothing.

### The second state: the box

Asked for on 4 Sep 2026. *"When I'm in pits have it display the fuel and tyres
still and what position I should come out and a countdown timer to pit release
and details about the next stint or run this to the flag."*

**The screen switches wholly rather than adding to itself**, which is what he
chose when the alternative was offered. On track it is three things; stopped it
is five, and that is not a contradiction of the one-thing-at-a-time rule -
`race/refuel.py` already makes the argument and it applies harder to a screen
than to the voice: *"In the box the car is stationary, the driver is doing
nothing, and the thing he is otherwise doing is reading a number off a gauge
and waiting for it."*

The switch is `in_box`, set from the pit-entry discontinuity or from the tank
rising. Either is unambiguous - GT7 hands the car over at the pit entry line so
the speed trace steps rather than decelerates, and fuel never rises anywhere
else.

**What the box state may claim, and what it may not.** The fuel figure and the
countdown are honest to the litre: litres are measured off the feed and the
fill rate is measured per circuit (1.002 L/s at Monza, 1.001 at Watkins). The
compound is what the PLAN says to fit - a decision, not a measurement - and
nothing here claims to know how worn the set coming off is, because no packet
format carries wear at all. The rejoin position is the weakest of the five: it
is read off the game's own gap boxes, which have never once returned a number
in a real race (`race/gaps.py`), so it shows a dash far more readily than a
place.

================================================================================
THE BOARD SPEC - what is on it, in rank order, and what each item may claim
================================================================================

Written 8 Sep 2026 for Phase 1 row 1.8. **He races in a wheel and sometimes a
PSVR2 headset.** This is a second monitor he glances at down a straight, so
every item below is a number or a word - never a table, never a colour scale,
and never a figure whose units he has to work out. The screenshot the row asks
for comes from `python -m pitcrew.ui.preview --shot out/`, which renders the
board from a synthetic `DriverState` with no PS5 and no database attached.

**Rank, bottom-anchored, because he glances UP from the game below.** The
bottom edge is the shortest eye travel and the lead rank sits there.

    rank 4 (top, dimmest)   the last call and its mark
    rank 3                  four corner temperatures, then the two tyre splits
    rank 2 (middle)         laps to box | in hand to the stop | in hand to
                            the flag | position
    rank 1 (bottom, 210px)  gap ahead | gap behind

--- rank 1 · the two neighbour gaps -------------------------------------------

Unchanged and still the lead, on his own revision of the brief: on a straight
the car ahead and the car behind are what he can act on within seconds. Ahead
on the left, behind on the right, because that is where the cars are. Each
side gets a sentence only true of that side and **no signed rate reaches the
screen** - "the gap is closing" means we are catching him on one side and he
is catching us on the other, and those demand opposite driving (rule 13).
Three states: it favours you, it favours him, or nobody can tell yet.

⚠️ **`gap_reads` and `board_positions` are 0 rows on file as of 8 Sep 2026.**
Every gap item is a dash until a race runs with the repaired locator, so the
dash says "no gap read" rather than sitting blank.

--- rank 2 · laps to box ------------------------------------------------------

From `RaceState.laps_to_stop()`, which clamps at zero, so `laps_past_box`
carries the sign the clamp throws away: "NOW / box this lap" and "NOW / 2 past
the box lap" are different news. Urgent inside two laps.

**The caption names the lap in GT7's numbering and counts the same way the
figure above it does** - `lap_on_screen() + laps_to_stop()`. Both halves of
that were wrong. It was the app's lap count, which is one behind the HUD at
every crossing and further behind after a crossing lost in the pit lane (Road
Atlanta: +1 on lap 1, +2 by lap 20); and the offset has to be `to_stop`
exactly, because that is the convention the rest of the app executes -
`_box_now` fires at `to_stop == 0` saying *"Box this lap"*, so at zero the lap
in progress IS the box lap. Get either wrong and a big "2" sits over a caption
naming a lap his HUD reaches in one, and he has to work out which lied.

--- rank 2 · fuel in hand, TWO numbers, each naming its own distance ----------

**This is the item that has already gone wrong once and the shape of the
failure is why both numbers are labelled in words.** Session 127, Daytona,
4 Sep 2026, lap 2: *"-7.1 laps of fuel in hand to the flag"* spoken with
**84.0 L aboard and the planned stop nine laps away**, twenty-six seconds
after *"1.9 spare to the stop"*. Two numbers, both introduced as spare or in
hand, nine laps apart, inside half a minute. The model was never wrong: the
old expression divided the tank by the burn and subtracted the laps to the
FLAG, **with no term for the litres the stop would add.**

So the board carries both, and:

* **IN HAND TO THE STOP** is `calls.fuel_in_hand_to_stop` - literally the
  expression the voice speaks as *"N laps of fuel in hand to the stop"*, so
  the ear and the eye cannot be given different numbers. It is the live one:
  it moves with the tank and with the burn. A dash whenever there is no stop
  still to come, saying which of the reasons it is.
* **IN HAND TO THE FLAG** is `calls.fuel_in_hand_to_flag` - laps of fuel he
  will have left at the chequer, counting the fill still to come. With no
  stop left that is the tank against the flag, the same expression the voice
  speaks. With a stop still to come the supply is **the biggest of what he
  arrives with and what the plan fills to, capped by the tank**, and the
  sub-line names whichever of the three actually bound it: `on the plan's
  fill`, `on the fuel aboard`, `on a full tank`. **Its negative is the
  finding: one stop does not do this race.** Never clamped away. A dash, with
  its reason, where the capacity is unknown or zero - a missing tank size
  must not become an infinite one (rule 3).

  ⚠️ **This figure took three attempts and both wrong ones are worth
  keeping.** Sized as the plan's fill with a fixed caption, it read **1.0 at
  45, 60 and 84 litres aboard** - `fuel_margin_l` falls back to
  `FUEL_MARGIN_LAPS` where no burn scatter has been measured, so the block
  was the app's own margin policy read back as an instrument. Replaced with
  `capacity / burn - laps after the box` it moved, and **over-promised by the
  whole margin**: 14.9 where the plan will leave 1.0, beside a stop figure of
  6.1, and a 17.8-lap step across one crossing.

  What was actually wrong was the caption. Where the plan's fill binds, this
  IS the plan's margin in laps and it is *supposed* to sit still - a stop
  refills, so what he carries before it does not decide the run home - and it
  is not a constant: with a measured scatter the margin is sized on that
  scatter. It moves for real where the supply is really something else, and
  in those branches the caption now says so. It moved only where its caption
  lied, which is the version this replaced.

Both refuse rather than guess where a further stop follows this one: the laps
after the *next* stop ride on a fill nothing has sized.

**Neither is urgent above zero, and there is no invented margin threshold.**
The driver's own standing rule is that he will not carry a spare lap of fuel
in a lap race, so a figure of 0.2 is on plan and colouring it would be an
alarm that fires every race. Below zero it does not reach, and that is red.

The laps the tank alone covers - the old single "laps of fuel" figure - is now
the caption under the stop number, in the words `N laps aboard`. One big
number per question; the supply is its reason, not a third question. **The
live litres are on the box panel and nowhere else**: both figures here are
computed from the tank as it read at the last crossing, and printing
`packet.fuel_level` beside them put three readings of one tank on the screen
with none of them reconciling.

--- rank 2 · position ---------------------------------------------------------

`P6` with `of 12` under it, from `RaceState.position` / `field_size` (874 of
874 laps on file carry a position). **It is on the board against this file's
own founding rule** - "this shows only what the game does not", and GT7 does
show position - so it is deliberately at the middle rank and not the lead. It
earns its place because it is the frame every strategy call is about
("you inherit P2", the rejoin seat in the box panel), the field size is not
something GT7 puts in front of him, and the game's own leaderboard is
truncated to the top eight.

--- rank 3 · the four corner temperatures -------------------------------------

His first request, twice repeated, and the game gives him no number at all.
Fed a **3-second mean, never a raw frame**: RR raw frames span 64.4-186.1 degC
where RR per-lap medians span 69.4-79.6, so the noise is 11.9x the signal and
a faster refresh makes the display worse. Coloured only against wear onset
(RS 88 / RM 90 / RH 93 degC) and against a corner sitting 10 degC above its
pair.

⚠️ **This IS raw temperature drawn as colour, and row 1.8's spec line says
"never raw temps as colour". It is kept deliberately and here is the whole
case, so the next person does not have to re-derive it.**

Kept, because what it colours against is a WEAR-onset threshold and not a
grip window - the thing this file exists to refuse - it is imported from one
sourced constant rather than restated, it has nine tests, and removing it is
not on this row's list of what was missing. Row 1.8's phrase is about the
tyre-split item below: the split is the signal, and no colour SCALE is
invented over absolute temperature anywhere on this board.

Thin, and in five specific ways. The source is one measurement by someone
else - GT7 1.55, one car (Gr.3 911), one track (Northern Isle), 4x wear,
n=1. 1.71 rewrote the tyre slip model, so by the programme's own
re-measurement rule the figure is suspect until re-measured here. Its own
author concedes the endogeneity. It does not say which aggregate - hottest
wheel, axle mean, four-wheel mean - the 88 is about, and this driver's axles
live 8-11 degC apart, which is wider than the gap between the RS and RH
thresholds. And on his own archive only 29 of 3,129 rear-axle observations
reach 88 at all.

⚠️ **Whether it fires on what the board actually draws is NOT known.** His RR
per-lap MEDIAN peaked at 79.6 degC against a warn line at 83 - but this
display is fed a **3-second mean**, which is neither a lap median nor a raw
frame, and raw RR frames reach p99 102.6. Nobody has measured how often a
3-second window crosses 83. Do not repeat "it has never fired" as though it
had been checked on this aggregate; it has not.

--- rank 3 · the two tyre splits ----------------------------------------------

**The reading on this car with evidence behind it, and until now the board
could not show one of them at all.** `race/tyre_split.PAIRS` is left-right
only, so the axle gap - the stronger of the two - had no implementation, and
the RR-RL gap only appeared as a per-corner figure once it passed 10 degC,
which on the measured stint it never did (it reached +4.0).

Two items, per lap, never per frame:

* **rear minus front**, drawn as a positive figure with the direction in
  words - `REAR OVER FRONT` or `FRONT OVER REAR`. The sign is a finding both
  ways, which is why `tyre_split.axle_split_now` returns it signed: rears
  hotter is a rear-limited car and fronts hotter is a front-limited one, and
  CLAUDE.md 5.5's worked example - *"Brake balance one click rearward. Fronts
  are going first."* - is the second of those. A number whose sign he has to
  decode under a helmet is what rule 13 is about, so the board never shows
  the sign.
* **the rear pair**, `RR OVER RL` or `RL OVER RR`, from `split_now`.

Each carries its lap count (rule 4) and, where five laps and the instrument
allow, `WIDENING` or `SETTLING` - the same two words the per-corner figure
uses. Silence where the trend is inside the floor: **no rate is not a rate of
zero.**

⚠️ **What the r=+0.82 behind these is, exactly.** Daytona session 118, 3 Sep
2026, 71,449 frames: across the FOUR CORNERS OF THE CAR, per-lap mean
temperature against measured per-lap wear rate (FL 62.5 degC / 0.0275 per lap
… RR 75.7 / 0.0570). **n=4, and it is an association** - both quantities are
driven by load. It is not "temperature predicts wear" and it is not a grip
claim. What it buys is that the gap is a finer instrument than the wear gauge
for the same thing: the gauge quantises at 2.8-3.3% of tyre life per pixel and
the gap moves continuously. The trend floor `RATE_WORTH_SAYING_C` = 1.25
degC/lap is **derived, not measured**, and the board says `derived` beside it.

--- rank 4 · the last call and its mark ---------------------------------------

One dim line across the top: the lap, the sentence he heard, and the one word
that says how it was meant - `INSTRUCTION`, `SUGGESTION`, `UNCONFIRMED`, or
for the re-planner `OFFER` and `REPORT`. It answers "what did George just
say?" for a driver who missed it under a helmet, which is the one thing a
screen can do that a voice cannot.

**The word comes from `Call.mark()`, which is the same expression
`Call.spoken()` builds its suffix from** (rule 12). An instruction carries no
spoken suffix because §5.5 wants one thing at a time in the ear; on a screen
there is no cost to naming it, and a driver who cannot tell an order from an
offer will end up treating every line as one or the other.

⚠️ **Not `PitCrewController.last_call`**, which is assigned in three places,
read by nothing, never initialised, and not set on the ordinary call path.
The board is fed by `_board_call`, which is cleared at race start and at race
stop - CLAUDE.md rule 11: state that outlives a session gets read as if it
belongs to this one, and a reset with no caller is the shape of that defect
rather than the fix for it.

--- the box state · the tyres-at-stop decision --------------------------------

`state.next_tyres` was rendered only inside `_BoxPanel`, so he learned the
plan's tyre decision when he was already stationary. It now rides on the
laps-to-box caption as well - `plan: lap 14 · RS on` or `plan: lap 14 · no
tyres` - so the decision arrives while there is still something he can do
about it.
"""
from __future__ import annotations

from dataclasses import dataclass

from PyQt6.QtCore import Qt
from pitcrew.diagnostics import log
from PyQt6.QtWidgets import (
    QApplication,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QStackedLayout,
    QVBoxLayout,
    QWidget,
)

# The one measured figure, from `store.tyres.WEAR_ONSET_C`. Imported rather
# than restated: two copies of a threshold drift, and this one is sourced.
from pitcrew.store.tyres import WEAR_ONSET_C
# The one vocabulary for how a call was meant, shared with `Call.spoken()` so
# the word on the screen and the word in his ear are one decision (rule 12).
from pitcrew.race.calls import MARK_UNCONFIRMED
# The trend floor, imported rather than restated: it is derived, its
# arithmetic is documented where it is defined, and two copies would drift.
from pitcrew.race.tyre_split import RATE_WORTH_SAYING_C
from pitcrew.ui import theme

# How far below onset still counts as approaching it.
NEAR_ONSET_C = 5.0
# How far above the opposite tyre before a corner is called lopsided. Wide
# enough that ordinary front-to-rear bias does not trip it every lap.
PAIR_GAP_C = 10.0

# **The app's own tokens, and its own faces.** This window had a private
# palette and asked for Archivo and JetBrains Mono, neither of which is
# installed on the rig - so every number on it was silently drawn in Arial.
# A system face standing in for the display voice is a failure rather than a
# fallback, and two visual worlds in one product is a third thing to learn.
GROUND = theme.RUBBER_DEEP
PANEL = theme.SHOULDER
EDGE = theme.TREAD
INK = theme.STENCIL
INK_DIM = theme.STENCIL_DIM
# **The state ladder, and what each colour is allowed to claim.**
#
# `cool` is white because a temperature below onset is a measured number
# making no further claim - there is no published grip window for GT7 and
# this app once carried a fabricated one. Amber and red are the wear-onset
# threshold, which is sourced. Nothing here is a grip reading.
COOL = theme.STENCIL
NEAR = theme.WARNING
OVER = theme.DANGER_INK
# The trend on a neighbour: it favours you, it favours him, or nobody knows.
# Green is not a register here - nothing on this instrument is declared - it
# is the third state of a three-state reading.
GOOD = theme.WEAR_FLAT

# The number faces, restated here because this window sets its own style
# sheets rather than going through `widgets`. `QWidget { font-size }` beats
# `setFont`, so a size only counts if it is in the rule that wins.
NUMBER_FACE = f"'{theme.DATA_FAMILY}','{theme.DATA_FALLBACK}',monospace"
LABEL_FACE = f"'{theme.STENCIL_CONDENSED}','{theme.STENCIL_FAMILY}',sans-serif"

PAIRS = {"fl": "fr", "fr": "fl", "rl": "rr", "rr": "rl"}
CORNERS = ("fl", "fr", "rl", "rr")


@dataclass(frozen=True)
class GapView:
    """One neighbour, and what the gap to him is doing.

    **`note` is written per side and never shared.** `GapTrend` reports "the
    gap is closing" and that is deliberately one number meaning two things -
    on the car ahead it means we are catching him, on the car behind it means
    he is catching us, and those demand opposite driving. `race/gaps.py` calls
    that out as rule 13 in as many words. So nothing here shows a signed rate:
    each side gets a sentence that is only true of that side.
    """
    seconds: float | None = None
    note: str = ""
    # Bad news for us: he is catching, or we are being dropped. Drawn in the
    # warning ink so a glance separates "push" from "hold".
    urgent: bool = False
    # **Good news, and it is not merely "not urgent".** Catching the car
    # ahead and being unable to read a trend at all both used to render white,
    # so the display could say "this is going badly" and never "this is going
    # well" - and on a screen glanced at once down a straight, the difference
    # between those two is whether the effort is paying. Three states, because
    # there are three: it favours you, it favours him, or nobody can tell yet.
    good: bool = False


@dataclass(frozen=True)
class BoardCall:
    """The last thing the engineer said, as the board prints it.

    `mark` is one of `calls.MARK_*` and comes from `Call.mark()`, the same
    expression `Call.spoken()` builds its spoken suffix from - so the word on
    the screen and the word in his ear are one decision (CLAUDE.md rule 12).

    `lap` may be None: the re-planner speaks off a lap the state has, but a
    call built by hand need not carry one, and lap 0 is not a substitute for
    "no lap" (rule 3).
    """
    text: str
    mark: str
    lap: int | None = None


@dataclass(frozen=True)
class DriverState:
    """Everything the instrument shows. `None` is missing and shows as a dash.

    Deliberately not the race state: this takes the three numbers it draws and
    nothing else, so it can be built and tested without a race.
    """
    temps_c: dict[str, float | None] | None = None
    # **Which way each corner's split against its opposite is going**, in °C
    # per lap, for the corners where five laps say so and the movement is
    # outside the instrument. Absent means no answer, which is not a rate of
    # zero - see `race/tyre_split.py`, which owns the arithmetic and the
    # threshold. Positive is widening.
    split_rates: dict[str, float] | None = None
    compound: str | None = None
    # The plan's tyre decision for the coming stop: True a set goes on, False
    # fuel only, None the plan did not say. Shown in the box panel beside the
    # compound so "RS" cannot be read as "fit RS" when the plan says not to.
    tyres_at_stop: bool | None = None
    laps_to_box: float | None = None
    box_on_lap: int | None = None
    laps_of_fuel: float | None = None
    fuel_l: float | None = None
    burn_l: float | None = None

    # ---- the two tyre splits, per lap, both from `race/tyre_split.py`.
    # **Signed**, rear minus front: rears hotter and fronts hotter are
    # different diagnoses and the board words the direction rather than
    # showing him a sign to decode. None before any whole lap is sampled.
    axle_split_c: float | None = None
    # degC per lap, only where five laps say so and the movement clears the
    # derived floor. Absent is absent - it is NOT a rate of zero.
    axle_split_rate: float | None = None
    # Which of the two rear tyres is the hotter, and by how much. Positive
    # only, with the corner named, because a left and a right tyre are
    # interchangeable and "4 degrees cooler" is the same finding said about
    # the wrong one.
    rear_pair_hotter: str | None = None
    rear_pair_split_c: float | None = None
    rear_pair_rate: float | None = None
    # Laps behind both splits. Rule 4: an aggregate carries its sample count,
    # and a split from two laps and one from eight are not the same claim.
    split_laps: int = 0

    # ---- where he is. On the board because every strategy call is framed in
    # it, and at the middle rank rather than the lead because GT7 does show
    # him a position - see the spec above.
    position: int | None = None
    field_size: int | None = None

    # ---- fuel in hand, as two numbers that each name their own distance.
    # `*_why` is the reason the figure is missing, shown under the dash;
    # None when there IS a figure. See the spec above for the -7.1 this
    # shape exists to prevent.
    fuel_to_stop: float | None = None
    fuel_to_stop_why: str | None = None
    fuel_to_flag: float | None = None
    fuel_to_flag_why: str | None = None
    # **Which supply the flag figure was actually measured on, in words,
    # from the same expression that produced it** (rule 12). It is one of
    # three - the plan's fill, the fuel he arrives with, or a full tank - and
    # without it the two fuel blocks sit side by side under near-identical
    # captions with nothing saying they are answering off different supplies.
    # It has been wrong once: a figure that came from the tank he arrived
    # with, captioned as the plan's fill.
    fuel_to_flag_on: str | None = None

    # ---- the last thing said, and how it was meant.
    last_call: "BoardCall | None" = None

    # ---- the box. All None on track, and `in_box` is what switches the
    # screen rather than any of them being set: a stop with no plan behind it
    # still has to show something, and five dashes is the honest something.
    in_box: bool = False
    # What the tank should read at release, litres. Sized by the race's own
    # burn, not the plan's picture of it - see `controller._refuel_context`.
    fuel_target_l: float | None = None
    # Seconds until the tank reaches that, at this circuit's measured fill
    # rate. None where no rate has been measured here, which is a dash and
    # never a guess: he is holding the trigger on this number.
    release_in_s: float | None = None
    # Where the plan says he rejoins, and how it was reached. None where the
    # gap could not be read - which is most of the time, so far.
    out_position: int | None = None
    out_behind: str | None = None
    # The stint after this stop: how many laps it is, or that it runs to the
    # flag. **Both name their reference in words** - CLAUDE.md rule 13 exists
    # because "laps in hand" was said twice in two minutes meaning
    # laps-to-the-stop and laps-to-the-flag, ten laps apart.
    next_stint_laps: int | None = None
    runs_to_flag: bool = False
    # Where the fill rate came from - "briefing" or "declared".
    # On the screen because the countdown is only as good as its rate, and a
    # figure typed on the event page and one measured at this pump are not
    # the same claim.
    fill_rate_note: str | None = None
    # **Whether a plan exists at all.** `compound` and `next_stint_laps` are
    # both None after a mid-race replan that names neither, and also when
    # nothing was ever approved - and those are different answers, which is
    # rule 13. Without this the board said "no plan" while a plan was running.
    has_plan: bool = False
    # Past the last stint the plan names - an unplanned stop. Distinct from
    # `has_plan` being False, and from a planned stint whose length is not
    # stated; all three used to share one caption.
    past_the_plan: bool = False
    # The stop is due or overdue. `laps_to_box` clamps at zero, so without
    # this a driver three laps past his box lap reads "0 laps to box" every
    # lap with nothing saying he is late.
    # How many laps past the planned stop he is. 0 is "the box lap is this
    # one", which is due rather than late - the two read differently and the
    # first version captioned both "you are past the box lap". None where the
    # stop is still ahead.
    laps_past_box: int | None = None
    # The two neighbours. `None` where nothing has been read - which, until
    # the HUD gap reader is proven on a live race, is most of the time.
    ahead: "GapView | None" = None
    behind: "GapView | None" = None
    # The flag is out. The running panel needs it because `laps_to_box` is
    # None once the race is over, which it also is when no plan exists - and
    # "no plan" is the wrong thing to tell a man who has just finished.
    finished: bool = False


def onset_for(compound: str | None) -> float | None:
    """The wear-onset temperature for this compound, or None if unknown.

    None for an unknown compound rather than a default: a threshold guessed
    for a tyre nobody measured would colour the display against nothing.
    """
    if not compound:
        return None
    return WEAR_ONSET_C.get(compound.upper())


def pair_gap(corner: str, temps: dict[str, float | None]) -> float | None:
    """How far this corner is above the tyre opposite, or None.

    **Promoted from a border colour to a number**, because it is the most
    useful mark on the display and it was the only one with no figure. The
    module docstring has said so from the day it was written: a corner ten
    degrees hotter than its pair is diagnostic whatever the optimum is, and it
    needs no window at all - which matters here more than anywhere, because
    the absolute temperatures have no window. Nobody has ever published one
    for GT7, and the archive says why: temperature is endogenous, a
    consequence of how hard the tyre is being worked rather than an input to
    grip - measured directly by a one-second lag test on 48 Daytona laps, not
    by the sign disagreement this docstring used to cite, which did not
    survive a proper specification. See the spec at the top of this file.

    The gaps do not have that problem. Measured on Daytona session 118, the
    rear-front and RR-RL splits are monotone across the stint, and across the
    four corners of the car per-lap mean temperature tracks measured per-lap
    wear at r=+0.82 - n=4, an association, both driven by load. Of everything
    on this screen this is the reading with evidence behind it, and the spec
    above says exactly what that evidence is and is not.

    Only ever positive: the cooler side of a pair returns None rather than a
    negative, because "13 degrees hotter than the other one" is a finding and
    "13 degrees cooler" is the same finding said about the wrong corner.
    """
    value = temps.get(corner)
    pair = temps.get(PAIRS[corner])
    if value is None or pair is None or value <= pair:
        return None
    return value - pair


def classify(corner: str, temps: dict[str, float | None],
             compound: str | None) -> tuple[str, bool]:
    """`(state, lopsided)` for one corner. State is cool / near / over.

    Lopsidedness is judged even where the compound is unknown, because it
    needs no threshold - which is exactly why it is the useful one.
    """
    value = temps.get(corner)
    if value is None:
        return "missing", False
    pair = temps.get(PAIRS[corner])
    lopsided = pair is not None and (value - pair) >= PAIR_GAP_C
    onset = onset_for(compound)
    if onset is None:
        return "cool", lopsided
    if value >= onset:
        return "over", lopsided
    if value >= onset - NEAR_ONSET_C:
        return "near", lopsided
    return "cool", lopsided


class _Tyre(QWidget):
    """One corner: the temperature, its name, and how far it is above its pair.

    **The corners are the subject of this screen.** The driver's own brief was
    *"tyre temps is probably my main request, in colour for ease of
    visibility"* - and they were rendering at 104px while laps-to-box and
    laps-of-fuel had 180, so the thing he asked for was the smallest of the
    big numbers on it. They lead now.

    The pair gap sits under the number as a figure rather than as a border
    hue. It was a purple outline that said "this corner is more than ten
    degrees above the other one" without saying how far above, on the one
    reading this display has evidence for - see `pair_gap`.
    """

    VALUE_PX = 96
    GAP_PX = 26

    def __init__(self, corner: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._corner = corner
        box = QVBoxLayout(self)
        box.setContentsMargins(0, 10, 0, 8)
        box.setSpacing(2)

        self.value = QLabel("--")
        self.value.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.gap = QLabel("")
        self.gap.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.gap.setStyleSheet(self._gap_css(NEAR))
        self.gap.setFixedHeight(self.GAP_PX + 8)

        name = QLabel(corner.upper())
        name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        name.setStyleSheet(
            f"font-family:{LABEL_FACE};font-size:19px;font-weight:600;"
            f"letter-spacing:7px;color:{INK_DIM};background:transparent;"
            f"border:none;")

        # **Name tight under its number, gap below that.** With the gap
        # between them, the corner label floated 50px clear of the figure it
        # names - on a screen read in one glance, a label that far from its
        # value belongs to nothing. The gap keeps a reserved height either
        # way, so a split appearing mid-race does not shift the grid under
        # him while he is looking at it.
        box.addWidget(self.value)
        box.addWidget(name)
        box.addWidget(self.gap)
        self.setMinimumWidth(210)
        self._paint("missing")

    def show_value(self, value: float | None, state: str,
                   lopsided: bool, gap: float | None = None,
                   rate: float | None = None) -> None:
        self.value.setText("--" if value is None else f"{value:.0f}")
        # **`_paint` runs on every path.** An early return here left every
        # corner that was NOT lopsided holding the grey it was constructed
        # with, so three of the four went dead the moment the fourth had a
        # split to report - on the reading this screen exists for.
        self._paint(state)

        # **Only where it is a finding.** `lopsided` is the threshold the
        # display has always used; the number is what it was missing. A gap
        # under the threshold shows nothing rather than a small figure the
        # driver would have to decide about at 200 km/h.
        if not lopsided or gap is None:
            self.gap.setText("")
            self.gap.setStyleSheet(self._gap_css(NEAR))
            return

        text = f"+{gap:.0f} vs {PAIRS[self._corner].upper()}"
        # **The direction, in the word and in the ink.** A split that is
        # opening and one that has settled are the same figure and opposite
        # news - the first says the tyre is going, the second says it has
        # found its level. Silent where five laps do not say so yet: no rate
        # is not a rate of zero, and "steady" would be a claim.
        ink = NEAR
        if rate is not None:
            text += "  WIDENING" if rate > 0 else "  SETTLING"
            ink = NEAR if rate > 0 else GOOD
        self.gap.setText(text)
        self.gap.setStyleSheet(self._gap_css(ink))

    def _gap_css(self, ink: str) -> str:
        return (f"font-family:{NUMBER_FACE};font-size:{self.GAP_PX}px;"
                f"color:{ink};background:transparent;border:none;")

    def _paint(self, state: str) -> None:
        """**The number carries the state. There is no box round it.**

        Each corner used to sit in a rounded 3px-outlined panel that changed
        colour with the reading - so a hot corner said the same thing twice,
        in an outline and in an ink, and the outline was the louder of the
        two. On a glance-up instrument the furniture is what you read first
        and it is never the thing you needed.

        It is also what the app's own world asks for: depth comes from value
        steps and a 1px groove, never from rounded outlines, and there is
        nothing here to separate - four numbers laid out as the car are
        already four numbers laid out as the car.
        """
        # `INK_DIM`, not `STRUCK`. A corner with no reading is a dash, and
        # the dash is the sentinel - but `STRUCK` means "removed from the
        # count" and `test_struck_is_only_used_where_low_contrast_is_the_point`
        # holds no screen may paint with it. It is also the wrong call for a
        # glance instrument on its own terms: 6.5:1 against 4.5:1.
        ink = {"over": OVER, "near": NEAR, "cool": COOL,
               "missing": INK_DIM}[state]
        self.value.setStyleSheet(
            f"font-family:{NUMBER_FACE};font-size:{self.VALUE_PX}px;"
            f"font-weight:600;color:{ink};background:transparent;border:none;")


class _Stat(QWidget):
    """One large number with a caption under it."""

    def __init__(self, label: str, parent: QWidget | None = None, *,
                 value_px: int | None = None) -> None:
        super().__init__(parent)
        self.VALUE_PX = value_px or self.VALUE_PX
        box = QVBoxLayout(self)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(6)
        self.value = QLabel("--")
        self.value.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._ink = INK
        self._restyle()
        self.caption = QLabel(label.upper())
        self.caption.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.caption.setStyleSheet(
            f"font-family:{LABEL_FACE};font-size:{self.CAPTION_PX}px;"
            f"font-weight:600;letter-spacing:7px;color:{INK_DIM};"
            f"background:transparent;")
        self.sub = QLabel("")
        self.sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.sub.setStyleSheet(
            f"font-family:{NUMBER_FACE};font-size:{self.SUB_PX}px;"
            f"color:{INK_DIM};background:transparent;")
        # The unelided reason, and the width it may occupy. `0` is unbounded,
        # which is the state no block on the running board is left in - see
        # `set_sub_width`.
        self._sub_text = ""
        self._sub_width = 0
        box.addWidget(self.value)
        box.addWidget(self.caption)
        box.addWidget(self.sub)

    # **Sized for the glance he actually takes.** He looks at this on the
    # straights and nowhere else, so the bar is a couple of seconds from a
    # metre away with a wheel in his hands - not a desk. The captions and the
    # trend lines under them were 15-17px on a 2560-wide display, which is
    # desk type on an instrument.
    #
    # The default is the middle rank; `value_px` raises a block to the lead.
    VALUE_PX = 120
    CAPTION_PX = 21
    SUB_PX = 27
    # **The tyre splits, one rank under the corner temperatures.** They are
    # the reading with evidence behind them and the corners are the reading
    # he asked for, and that tension is resolved by size rather than by
    # dropping either: the corners stay the subject of that block and the
    # splits sit under them, clearly a figure rather than a caption.
    SPLIT_PX = 58
    # **The gap to a neighbour leads this display**, on the driver's own
    # revision of the brief after seeing the corners lead: on a straight, the
    # car ahead and the car behind are what he can act on right now, and the
    # tyres are what he acts on over a stint. Both are on the screen; only
    # one of them can be the first thing read.
    # **180, not 210, and the cut is the monitor.** With the last-call line
    # and the split block added, the board's enforced minimum came out at
    # 1128 px against his 1080 panel - measured with the REAL faces, where it
    # is 93 px taller than the same board measured offscreen, so the guard
    # test cannot see it. The rank survives the trim: 180 is still half again
    # the middle rank and nearly twice the corners.
    GAP_PX = 180
    # **How wide a reason line may be, per rank.** The middle rank carries
    # four blocks across the panel and the lead rank two, so they can afford
    # different amounts; the box panel carries five. Each is the panel's own
    # room divided by the blocks on it, with the margins and the gaps between
    # them taken off. `test_the_board_fits_his_monitor_in_the_widest_state_it
    # _can_be_given` is what holds the arithmetic to the actual monitor.
    # Measured at the face the stylesheet resolves to - Cascadia Mono at
    # 27 px, 27 px a character - so the middle rank's 640 is twenty-three
    # characters, which is what every reason string there is written to and
    # what the longest box caption (`plan: lap 12 - no tyres`) needs.
    MIDDLE_SUB_W = 640
    GAP_SUB_W = 1100
    SPLIT_SUB_W = 700
    BOX_SUB_W = 480

    def set_sub_width(self, pixels: int) -> None:
        """Cap the reason line, and elide anything past it.

        **The board's width has to be a property of the board, not of every
        string anyone ever writes into it.** Twice now it has grown past his
        2560 px panel on the length of a sub-line - a 46-character refusal
        reason under a fuel figure once, and a rival's name inside a gap
        sentence the other time (PSN ids run to sixteen characters; at
        fourteen the board was already at 2490). The window is frameless with
        no resize handle, and Qt answers a layout minimum bigger than the
        screen by growing the window off it rather than by dropping anything,
        so he loses the right-hand end - POSITION and the edge of the BEHIND
        gap - with nothing saying he has.

        Short strings are still better than elided ones and the reasons are
        written short. This is what makes the bound true rather than
        conventional.
        """
        self._sub_width = pixels
        self.sub.setMaximumWidth(pixels)
        self._resub()

    def _resub(self) -> None:
        from PyQt6.QtGui import QFontMetrics

        text = self._sub_text
        if self._sub_width:
            text = QFontMetrics(self.sub.font()).elidedText(
                text, Qt.TextElideMode.ElideRight, self._sub_width)
        self.sub.setText(text)

    def _restyle(self) -> None:
        self.value.setStyleSheet(
            f"font-family:{NUMBER_FACE};font-size:{self.VALUE_PX}px;"
            f"font-weight:600;color:{self._ink};background:transparent;")

    def show_value(self, text: str, sub: str = "", *,
                   urgent: bool = False, good: bool = False) -> None:
        """`urgent` and `good` are the two ends of one reading, not two flags.

        Both false is the honest middle - steady, or too few laps to say -
        and it stays white. `urgent` wins if somehow both arrive, because the
        cost of missing bad news is higher than the cost of missing good.
        """
        self.value.setText(text)
        self._sub_text = sub
        self._resub()
        ink = NEAR if urgent else GOOD if good else INK
        if ink != self._ink:
            self._ink = ink
            self._restyle()
        self.sub.setStyleSheet(
            f"font-family:{NUMBER_FACE};font-size:{self.SUB_PX}px;"
            f"color:{ink if (urgent or good) else INK_DIM};"
            f"background:transparent;")
        # The stylesheet is re-applied above, which can change the face the
        # metrics resolve to; the elide has to be redone against it.
        self._resub()

    def set_label(self, label: str) -> None:
        """Rename the block.

        **Only the splits use this, and only to name a direction.** A caption
        that changes is a caption he has to read, so the rest of the board's
        are fixed at construction; the axle split has no fixed name because
        "rear over front" and "front over rear" are opposite diagnoses of one
        measurement and the board says which rather than showing a sign.
        """
        self.caption.setText(label.upper())


# **The words for a split's direction, and why they are words.** The figure is
# always drawn positive: a driver reading a minus sign at 200 km/h has to
# decide what it was a minus of, and rule 13 exists because he could not ask.
REAR_OVER_FRONT = "rear over front"
FRONT_OVER_REAR = "front over rear"
AXLES_LEVEL = "axles level"

# The two trend words, shared verbatim with the per-corner figure above. One
# vocabulary for one thing (rule 13): a split that is opening and one that has
# settled are the same number and opposite news.
WIDENING = "widening"
SETTLING = "settling"


def axle_words(split_c: float | None) -> tuple[float | None, str]:
    """`(the figure to draw, the direction in words)` for the axle split.

    The figure comes back as a magnitude and the direction as a phrase, so
    nothing downstream has to interpret a sign. `None` in, `(None, "")` out -
    a missing split is a dash, never a zero.
    """
    if split_c is None:
        return None, ""
    if split_c > 0:
        return split_c, REAR_OVER_FRONT
    if split_c < 0:
        return -split_c, FRONT_OVER_REAR
    return 0.0, AXLES_LEVEL


def trend_word(split_c: float | None, rate: float | None) -> str:
    """`widening`, `settling`, or "" where nothing may be claimed.

    **Judged against the gap the board is naming, not against the raw sign.**
    The axle rate is the slope of rear-minus-front, so a front-limited car
    with the fronts pulling further ahead has a NEGATIVE rate and a widening
    gap. Reading the raw sign would have told him the front-over-rear split
    was settling at the exact moment it was running away.

    Empty where there is no rate at all: five laps have not been sampled, or
    the movement is inside the derived floor. **No rate is not a rate of
    zero**, and "settling" would be a claim.
    """
    if rate is None or split_c is None or split_c == 0:
        return ""
    return WIDENING if (rate > 0) == (split_c > 0) else SETTLING


class _LastCall(QWidget):
    """One dim line: the lap, what was said, and how it was meant.

    **The one thing a screen does that a voice cannot** - it is still there
    thirty seconds later. He is in a helmet with a wheel in his hands; a call
    he half-heard is a call he cannot ask about, and the alternative to
    reading it here is acting on a guess.

    Deliberately the quietest thing on the board. It is a record, not an
    instruction: the instruction was the voice, and a sentence competing with
    the numbers for the same glance would cost him the numbers.
    """

    TEXT_PX = 26
    # **The sentence is bounded to this and never wider.** Without a bound
    # the label asks for its whole natural width and Qt hands that straight
    # to the window's layout minimum: the real overdue-box call - *"Box this
    # lap. RM on. 3 laps overdue. You're 1.4 laps short of the flag on
    # current burn - short-shift and lift if you stay out."* - wants 3,744 px
    # and took the board's minimum to 4,117, which is not a monitor he owns.
    # It was also clipped flat with no ellipsis, so the half he lost was the
    # reason - the half rule 13 is about - with nothing saying anything had
    # been cut.
    MAX_WIDTH = 1560
    # **Two lines, not one, and that is the difference between a cut and a
    # misreading.** At one line this bound holds about 59 characters, so that
    # same call rendered *"…You’re 1.4 laps …"* - and "1.4 laps" with
    # the direction cut off reads naturally as 1.4 laps IN HAND when what it
    # said was 1.4 short. Two lines hold about 118, which is the whole of
    # every call the engineer makes today. The height is reserved either way,
    # so nothing shifts under him when a long one arrives, and anything that
    # still will not fit ends in an ellipsis rather than stopping dead.
    LINES = 2

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(18)
        self.line = QLabel("")
        self.line.setStyleSheet(
            f"font-family:{NUMBER_FACE};font-size:{self.TEXT_PX}px;"
            f"color:{INK_DIM};background:transparent;")
        self.line.setWordWrap(True)
        self.line.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.mark = QLabel("")
        self.mark.setStyleSheet(self._mark_css(INK_DIM))
        row.addStretch(1)
        row.addWidget(self.line)
        row.addWidget(self.mark)
        row.addStretch(1)
        # Reserved, so a call arriving mid-race does not shift the whole
        # board under him while he is looking at it.
        self.setFixedHeight(self.TEXT_PX * self.LINES + 22)
        # The unelided sentence, kept so a resize can re-fit from the
        # original rather than from an already-shortened copy.
        self._text = ""
        self._fit("")

    def _line_box(self) -> int:
        """The height two lines of this face are allowed to occupy."""
        from PyQt6.QtGui import QFontMetrics

        return QFontMetrics(self.line.font()).lineSpacing() * self.LINES

    def _fit(self, text: str) -> None:
        """Set the sentence so it occupies at most `LINES` lines, and no more.

        **Measured, not estimated, and the estimate was the defect.** The
        first version elided against `MAX_WIDTH * LINES` as a single run and
        handed the result to a word-wrapping label whose laid-out width the
        layout decides - which came out at 780 px, so the real 126-character
        call wrapped to five lines inside a two-line box. Centred vertically,
        the visible slice was the MIDDLE: no *"Box this lap."* at the top and
        no ellipsis at the bottom, and what he read was a status note about
        being 1.4 laps short. He would have stayed out.

        So the label is given a definite width and the fit is asked of Qt
        itself - `heightForWidth` on the text actually set - and the longest
        prefix that fits is found by bisection. That is exact, it does not
        care what face the stylesheet resolved to, and it costs eleven layout
        queries on the laps where something is said.

        **Cut from the right**, so the instruction survives: §5.5 puts the
        instruction first and the reason second. The ellipsis is not
        decoration - it is the difference between a driver who knows there
        was more and one who acts on half a sentence believing it was whole.
        """
        from PyQt6.QtGui import QFontMetrics

        if not text:
            self.line.setFixedWidth(1)
            self.line.setText("")
            return
        metrics = QFontMetrics(self.line.font())
        natural = metrics.horizontalAdvance(text)
        if natural <= self.MAX_WIDTH:
            # One line, no wrapping and nothing to cut.
            self.line.setFixedWidth(natural + 8)
            self.line.setText(text)
            return
        self.line.setFixedWidth(self.MAX_WIDTH)
        box = self._line_box()
        lo, hi, best = 1, len(text), "…"
        while lo <= hi:
            mid = (lo + hi) // 2
            trial = text[:mid] + ("…" if mid < len(text) else "")
            self.line.setText(trial)
            if self.line.heightForWidth(self.MAX_WIDTH) <= box:
                best, lo = trial, mid + 1
            else:
                hi = mid - 1
        self.line.setText(best)

    def _mark_css(self, ink: str) -> str:
        return (f"font-family:{LABEL_FACE};font-size:{self.TEXT_PX - 6}px;"
                f"font-weight:600;letter-spacing:5px;color:{ink};"
                f"background:transparent;")

    def show_call(self, call: "BoardCall | None") -> None:
        if call is None:
            # **Blank, not a dash.** Every other empty box on this board says
            # why it is empty, because he is holding a trigger on it or
            # planning around it. Nothing has been said yet is the ordinary
            # state of the first two laps of every race and it needs no
            # explaining.
            self._text = ""
            self._fit("")
            self.mark.setText("")
            return
        where = f"L{call.lap}  " if call.lap is not None else ""
        self._text = f"{where}{call.text}"
        self.mark.setText(call.mark.upper())
        # After the mark, because the mark's width is part of the row and a
        # fit measured before it lands is measured against the wrong row.
        self._fit(self._text)
        # **Only "unconfirmed" gets an ink of its own.** It is the one mark
        # that says the engineer may be wrong, and it is the one he needs to
        # see without reading the word. Marking a suggestion in warning ink
        # would put a colour on advice that is perfectly sound.
        self.mark.setStyleSheet(
            self._mark_css(NEAR if call.mark == MARK_UNCONFIRMED else INK_DIM))


class DriverWindow(QWidget):
    """The instrument, in a window he drags onto the screen above the game.

    **Its own top-level, not a tab in the app.** The main window carries
    controls he must not be able to hit from the rig, and a race board wants
    the whole of a 2560x1080 panel with no furniture on it.

    Three properties it does not get to lose, all inherited from `ui/banner.py`
    which solved the same problem for the same rig:

    * **It never takes focus.** He is driving. `WA_ShowWithoutActivating` plus
      the `Tool` flag mean a keypress meant for the PS5 stays with the PS5.
    * **It stays on top**, because whatever else is on that monitor is not
      what he glanced up for.
    * **It opens where he last put it.** This rig has three monitors and the
      one he can see is not the one Windows thinks is first, so a board that
      reopens on the primary display every race is a board he re-drags every
      race. The geometry is remembered by the caller and handed back in.

    Frameless, so `move_to` is the only way it travels - which is why the
    window is draggable by its own surface. Without that there is no title bar
    to grab and it could never be positioned at all.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(None)
        self.setWindowTitle("Pit Crew - driver board")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setStyleSheet(f"background:{GROUND};")
        page = QVBoxLayout(self)
        page.setContentsMargins(0, 0, 0, 0)
        page.setSpacing(0)
        self.view = DriverView()
        page.addWidget(self.view)
        # **Sized to what the instrument actually needs.** This asked for
        # 1280x480 and never got it: the laid-out minimum is far larger than
        # that at these type sizes, so Qt grew the window on show and the
        # number here described nothing.
        #
        # **No point figure is quoted here on purpose.** Two have been, and
        # both were wrong within a commit: 1920x1010 (measured on a blank
        # board), then 2457x1031 (not reproducible - the same state measures
        # differently depending on what was drawn before it and on the face
        # the stylesheet resolves to). What IS checked is the bound:
        # `test_the_board_fits_his_monitor_in_the_widest_state_it_can_be_given`
        # drives every refusal string, a sixteen-character rival name, the
        # box panel and a call three times longer than any the engineer makes,
        # and holds the result under 2560 x 1080. This opens just inside that. It is not a free choice
        # - the ranks are set by how far away he is and how long a glance is,
        # and the panel is 2560x1080 - so the honest thing is to open at a
        # size the content fits in.
        #
        # Overridden by `restore_geometry` wherever he has dragged it before,
        # and Qt will still grow a saved geometry smaller than the minimum. A
        # frameless window has no resize handle, so being grown is the better
        # of the two failures: clipped, he would be reading a board with a
        # number missing and no way to know which.
        self.resize(2480, 1050)
        self._drag_from = None
        # Called when the window goes away by any route, so whoever is
        # pushing state into it can stop. Without it the controller went on
        # ticking four times a second into a hidden widget for the rest of
        # the race. A plain callable rather than a signal: this widget is
        # built by the controller and handed nothing else.
        self.on_closed = None

    def update_state(self, state: "DriverState") -> None:
        self.view.update_state(state)

    # -- dragging, because a frameless window has no title bar to grab -------

    def mousePressEvent(self, event) -> None:      # noqa: N802 - Qt naming
        self._drag_from = (event.globalPosition().toPoint()
                           - self.frameGeometry().topLeft())

    def mouseMoveEvent(self, event) -> None:       # noqa: N802 - Qt naming
        if self._drag_from is not None:
            self.move(event.globalPosition().toPoint() - self._drag_from)

    def mouseReleaseEvent(self, event) -> None:    # noqa: N802 - Qt naming
        self._drag_from = None

    def closeEvent(self, event) -> None:            # noqa: N802 - Qt naming
        """Tell the feeder, however it was closed."""
        if callable(self.on_closed):
            try:
                self.on_closed()
            except Exception:                       # noqa: BLE001
                log("ui").warning("the driver board's close handler raised")
        super().closeEvent(event)

    def keyPressEvent(self, event) -> None:        # noqa: N802 - Qt naming
        """Escape closes it.

        A frameless always-on-top window with no title bar has no close
        button, and the only other way off the screen was to stop the race -
        which is not something to do because a display is in the way. It does
        not take focus, so this only fires when he has deliberately clicked
        on it.
        """
        if event.key() == Qt.Key.Key_Escape:
            self.close()
            return
        super().keyPressEvent(event)

    # -- geometry, remembered across races -----------------------------------

    def geometry_text(self) -> str:
        """`x,y,w,h` for the settings file."""
        rect = self.geometry()
        return f"{rect.x()},{rect.y()},{rect.width()},{rect.height()}"

    def restore_geometry(self, text: str | None) -> bool:
        """Put it back where he left it. False if the text was unusable.

        **Checked against the screens that exist now**, because a monitor that
        was there last race may not be tonight - and a window restored onto a
        display that has gone is a board he cannot see and cannot find to drag
        back. Qt will happily place a window entirely off every screen.
        """
        if not text:
            return False
        try:
            x, y, width, height = (int(part) for part in text.split(","))
        except (ValueError, AttributeError):
            log("ui").warning("driver board geometry %r is unreadable", text)
            return False
        if width < 200 or height < 120:
            return False
        from PyQt6.QtCore import QRect
        wanted = QRect(x, y, width, height)
        app = QApplication.instance()
        screens = app.screens() if app is not None else []
        if not any(screen.geometry().intersects(wanted) for screen in screens):
            log("ui").warning(
                "the driver board was last on a screen that is not here now, "
                "so it opens on this one instead")
            return False
        self.setGeometry(wanted)
        return True


def format_release(seconds: float | None) -> str:
    """The countdown, as the driver reads it off a stopwatch.

    Seconds only, never a clock face: the whole figure lives between about
    five and seventy, and a `0:47` is a lap time everywhere else on this rig.
    Rounded UP, for the same reason `refuel._ceil_l` rounds the litres up -
    being late costs about a litre, being early costs fuel he cannot get back.
    """
    if seconds is None:
        return "--"
    if seconds <= 0:
        return "GO"
    return str(int(seconds) if seconds == int(seconds) else int(seconds) + 1)


class _BoxPanel(QWidget):
    """What the screen says while the car is stopped.

    Five items, in the order he needs them: the seconds he is counting down,
    the number those seconds are counting towards, what is going on the car,
    where it puts him, and what the stint after this one is.

    **The countdown leads.** The earlier docstring described the litres first
    and the code laid out the seconds first, which is the sort of disagreement
    that gets resolved by whoever reads it last. The seconds are what he acts
    on - the litres are the reason, and CLAUDE.md 5.5 puts the instruction
    first and the reason second.

    Every dash on this panel carries the reason it is a dash. An empty box he
    cannot explain is one he would stop trusting the rest of the screen over,
    and on this panel four of the five can legitimately be empty.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addStretch(1)

        row = QHBoxLayout()
        row.setSpacing(56)
        self.release_stat = _Stat("release in")
        self.fuel_stat = _Stat("fuel to")
        self.tyre_stat = _Stat("tyres")
        # **"Rejoin", not "out in".** The value is `P7`, and "out in" reads as
        # a duration everywhere else on this rig - directly above it, "release
        # in" IS one. A caption that names a unit the value does not have is
        # the collision rule 13 is about.
        self.out_stat = _Stat("rejoin")
        self.next_stat = _Stat("then")
        row.addStretch(1)
        for stat in (self.release_stat, self.fuel_stat, self.tyre_stat,
                     self.out_stat, self.next_stat):
            # **The box panel is bounded too, and it was the one that got
            # away.** `QStackedLayout`'s minimum is the maximum over BOTH
            # pages, so a stop whose next stint has no stated length set the
            # whole window's minimum to 3,220 px - and it kept it for the
            # rest of the race, because the page keeps its text after he
            # leaves the box. He came back out onto a running board 660 px
            # wider than his monitor.
            stat.set_sub_width(_Stat.BOX_SUB_W)
            row.addWidget(stat)
            row.addStretch(1)
        outer.addLayout(row)

    def show_state(self, state: DriverState) -> None:
        # **The countdown is urgent the whole way down from ten seconds**, not
        # only at zero. He has to move his hand to the trigger, and a release
        # that turns red at the moment it is due is a release he is late for.
        seconds = state.release_in_s
        if seconds is None:
            # **The dash says why.** This is the one figure the driver is
            # holding the trigger on, and it was the only one on the panel
            # showing a bare dash with an empty caption under it.
            reason = ("no fill rate here" if state.fuel_target_l
                      else "nothing sized it")
            self.release_stat.show_value("--", reason)
        else:
            self.release_stat.show_value(
                format_release(seconds),
                "seconds" if seconds > 0 else "release now",
                urgent=seconds <= 10)

        if state.fuel_target_l is None:
            # Nothing sized the stop. Silence rather than a number the app
            # invented - the same refusal `RefuelWatch.note` makes, and for
            # the same reason: he is holding the trigger on this figure.
            self.fuel_stat.show_value("--", "nothing sized it")
        else:
            parts = []
            if state.fuel_l is not None:
                parts.append(f"{state.fuel_l:.0f} L")
            # Which rate the seconds beside it were priced at. A rate measured
            # at this pump and one typed on the event page are not the same
            # claim, and the countdown is only as good as whichever it used.
            if state.fill_rate_note:
                parts.append(state.fill_rate_note)
            self.fuel_stat.show_value(f"{state.fuel_target_l:.0f}",
                                      " \u00b7 ".join(parts))

        # The plan's decision, not a reading off the car. Nothing here knows
        # how worn the set coming off is, because no packet format carries
        # wear at all.
        #
        # **"No plan" used to cover two different facts.** `next_compound` is
        # also None when a plan IS running and simply does not name a compound
        # for the next stint - which is the honest state after a mid-race
        # replan - so the board told him there was no plan while one was being
        # executed.
        if state.tyres_at_stop is False:
            # The plan's decision in the box is "fuel only". Said as the
            # decision, not as a compound - the compound on the car is what
            # stays on it.
            self.tyre_stat.show_value("NO TYRES", "plan · fuel only")
        elif state.compound:
            self.tyre_stat.show_value(
                state.compound,
                "plan · new set" if state.tyres_at_stop else "plan")
        elif state.has_plan:
            self.tyre_stat.show_value("--", "plan: no compound")
        else:
            self.tyre_stat.show_value("--", "no plan")

        if state.out_position is None:
            # **A dash, and it says why.** The gap boxes this rests on have
            # never returned a number in a real race, so this is the expected
            # state rather than a fault - and an empty box he cannot explain
            # is one he would stop trusting the rest of the screen over.
            self.out_stat.show_value("--", "no gap read")
        else:
            self.out_stat.show_value(
                f"P{state.out_position}",
                f"behind {state.out_behind}" if state.out_behind else "")

        # **Named in full both ways.** CLAUDE.md rule 13: "laps in hand" was
        # spoken twice in two minutes meaning laps-to-the-stop and
        # laps-to-the-flag, figures ten laps apart, neither naming its
        # reference. Under a helmet he could not ask which one he had heard;
        # on a screen he can read it, so it is written out.
        if state.runs_to_flag:
            self.next_stat.show_value("FLAG", "runs to the end")
        elif state.next_stint_laps is not None:
            self.next_stat.show_value(f"{state.next_stint_laps}",
                                      "then box again")
        elif state.past_the_plan:
            # Out past the end of the stint list - an unplanned stop. NOT the
            # same as having no plan, and emphatically not "runs to the flag":
            # nothing has checked the fuel aboard against what is left.
            self.next_stat.show_value("--", "past the plan")
        elif state.has_plan:
            # Inside the plan, on a stint whose length it does not state.
            # Sharing the caption above would have said he was past the end of
            # a plan he is squarely in the middle of.
            self.next_stat.show_value("--", "plan: no length")
        else:
            self.next_stat.show_value("--", "no plan")


class DriverView(QWidget):
    """The whole instrument. `update_state` is the only thing to call."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setStyleSheet(f"background:{GROUND};")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(40, 8, 40, 18)
        # **Bottom-anchored.** He glances UP from the game screen below, so the
        # bottom edge of this display is the shortest eye travel.
        outer.addStretch(1)

        middle = QHBoxLayout()
        middle.setSpacing(70)
        lead = QHBoxLayout()
        lead.setSpacing(70)

        self.box_stat = _Stat("laps to box")
        # **Two fuel numbers, each naming its own distance in its caption.**
        # One expression each, both from `race/calls.py`, so neither can drift
        # from what the voice says about the same stop. See the spec at the
        # top of this file for the -7.1 that makes this two blocks and not
        # one.
        self.stop_stat = _Stat("in hand to the stop")
        self.flag_stat = _Stat("in hand to the flag")
        # Middle rank, not the lead: GT7 does show him a position, and this
        # file's founding rule is that the board shows what the game does not.
        self.position_stat = _Stat("position")
        # **At the ends, and in the order the cars are in.** Ahead on the
        # left, behind on the right, so which block is which needs no reading -
        # it is where the car is. That is what keeps this from being the
        # fourth and fifth items the docstring above warns about: they are one
        # paired mnemonic rather than two more things in a list.
        self.ahead_stat = _Stat("ahead", value_px=_Stat.GAP_PX)
        self.behind_stat = _Stat("behind", value_px=_Stat.GAP_PX)
        self.last_call = _LastCall()

        tyres = QWidget()
        grid = QGridLayout(tyres)
        grid.setContentsMargins(0, 0, 0, 0)
        # **Spread across the ultrawide.** The corners are the subject and the
        # screen is 2560 wide; at 16px apart they were a small square in the
        # middle of it with the room going to ground nobody reads.
        grid.setHorizontalSpacing(40)
        grid.setVerticalSpacing(6)
        self.tyres = {c: _Tyre(c) for c in CORNERS}
        # Laid out as he sits in the car, not mirrored.
        grid.addWidget(self.tyres["fl"], 0, 0)
        grid.addWidget(self.tyres["fr"], 0, 1)
        grid.addWidget(self.tyres["rl"], 1, 0)
        grid.addWidget(self.tyres["rr"], 1, 1)
        self.tyre_caption = QLabel("TYRE SURFACE °C")
        self.tyre_caption.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.tyre_caption.setStyleSheet(
            f"font-family:{LABEL_FACE};font-size:21px;font-weight:600;"
            f"letter-spacing:7px;color:{INK_DIM};background:transparent;")
        grid.addWidget(self.tyre_caption, 2, 0, 1, 2)

        # **The two splits, under the corners they are made of.** These are
        # the readings with evidence behind them - see the spec at the top of
        # this file for what that evidence is and what it is not - and until
        # now the board could show neither: the axle gap had no
        # implementation at all, and the rear pair only surfaced as a
        # per-corner figure once it passed 10 degC, which on the measured
        # stint it never did.
        self.axle_stat = _Stat("", value_px=_Stat.SPLIT_PX)
        self.rear_pair_stat = _Stat("", value_px=_Stat.SPLIT_PX)
        for stat in (self.axle_stat, self.rear_pair_stat):
            stat.set_sub_width(_Stat.SPLIT_SUB_W)
        # **The floor is named on the board, not only in the file.** It is
        # derived rather than measured (CLAUDE.md rule 5) and the trend words
        # above it fall silent below it, so a driver who sees no trend can
        # tell "nothing to say" from "broken".
        self.split_caption = QLabel(
            "TYRE SPLIT °C  ·  TREND DERIVED, "
            f"{RATE_WORTH_SAYING_C:.2f} °C/LAP FLOOR")
        self.split_caption.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.split_caption.setStyleSheet(
            f"font-family:{LABEL_FACE};font-size:17px;font-weight:600;"
            f"letter-spacing:4px;color:{INK_DIM};background:transparent;")
        # **Beside the corner grid, not under it, and the reason is the
        # monitor.** He is on a 2560x1080 panel and this instrument already
        # came close to filling its height; a fourth full-width rank pushed
        # the layout's own minimum past 1080, and Qt answers that by growing
        # the window off the screen rather than by dropping anything. The
        # room on an ultrawide is horizontal, and a corner's gaps beside the
        # corners is where a reader looks for them anyway.
        split_block = QWidget()
        split_column = QVBoxLayout(split_block)
        split_column.setContentsMargins(0, 0, 0, 0)
        split_column.setSpacing(10)
        split_column.addStretch(1)
        split_column.addWidget(self.axle_stat)
        split_column.addWidget(self.rear_pair_stat)
        split_column.addWidget(self.split_caption)
        split_column.addStretch(1)

        # **The gaps lead and they sit at the bottom.** This file's layout
        # rule is that he glances UP from the game screen below, so the bottom
        # edge is the shortest eye travel and content is anchored there - and
        # once something is the priority, that rule decides the order. The
        # tyres take the row above; the neighbours take the edge nearest his
        # eye.
        #
        # **Ahead on the left, behind on the right**, which is where the cars
        # are. That is what keeps two blocks from being two more things in a
        # list: it is one paired mnemonic and it needs no reading. Box and
        # fuel sit between them, at the middle rank - still the highest
        # consequence numbers in the race, and not what a straight is for.
        # **Bottom-aligned, because the blocks are no longer the same size.**
        # A 210px gap beside a 120px fuel figure top-aligned puts their
        # captions 60px apart, so the row reads as ragged rather than as a
        # rank - and the caption is the part that says which number this is.
        # Sitting them on one baseline lets the value heights differ, which
        # is the whole point of ranking them.
        #
        # **Two rows now, not one.** Six blocks on one line makes six items of
        # equal weight, which is the failure this file's rank exists to
        # prevent. The neighbours keep the bottom edge on their own; the four
        # numbers he plans with take the rank above them.
        for stat in (self.box_stat, self.stop_stat,
                     self.flag_stat, self.position_stat):
            stat.set_sub_width(_Stat.MIDDLE_SUB_W)
            middle.addStretch(1)
            middle.addWidget(stat, 0, Qt.AlignmentFlag.AlignBottom)
        middle.addStretch(1)
        for stat in (self.ahead_stat, self.behind_stat):
            # **The gap sentence carries a rival's NAME**, which comes off
            # the game and is not ours to keep short: PSN ids run to sixteen
            # characters and at fourteen the board already measured 2,490 px.
            stat.set_sub_width(_Stat.GAP_SUB_W)
            lead.addStretch(1)
            lead.addWidget(stat, 0, Qt.AlignmentFlag.AlignBottom)
        lead.addStretch(1)

        stacked = QVBoxLayout()
        stacked.setContentsMargins(0, 0, 0, 0)
        stacked.setSpacing(12)

        # Top of the panel and the quietest thing on it: a record of what was
        # said, not a thing to act on.
        stacked.addWidget(self.last_call)

        # **Neither block may expand into the other's room.** Both default to
        # growing, so the corner grid drifted a couple of hundred pixels away
        # from the splits it is made of and the pair stopped reading as one
        # block. Held to their own widths, with the stretches outside them.
        tyres.setSizePolicy(QSizePolicy.Policy.Maximum,
                            QSizePolicy.Policy.Preferred)
        split_block.setSizePolicy(QSizePolicy.Policy.Maximum,
                                  QSizePolicy.Policy.Preferred)
        centred = QHBoxLayout()
        centred.setSpacing(70)
        centred.addStretch(1)
        centred.addWidget(tyres)
        centred.addWidget(split_block)
        centred.addStretch(1)
        stacked.addLayout(centred)

        middle_row = QWidget()
        middle_row.setLayout(middle)
        stacked.addWidget(middle_row)

        leading = QWidget()
        leading.setLayout(lead)
        stacked.addWidget(leading)

        # **The two states are two widgets, swapped, not one relabelled.**
        # Relabelling five captions on a screen he reads while stationary in
        # the box would leave the previous state's numbers on it for whatever
        # part of a frame the repaint takes, and the numbers mean different
        # things - a litre figure under a "laps" caption is the shape of
        # mistake this display exists to avoid.
        self.running = QWidget()
        self.running.setLayout(stacked)
        # **So the stretch above can actually push it down.** Both panels
        # expand to fill by default, which quietly cancelled the
        # bottom-anchoring this file's layout rule is built on - the content
        # sat mid-screen with a band of ground under it, which is the eye
        # travel the rule exists to save.
        self.running.setSizePolicy(QSizePolicy.Policy.Preferred,
                                   QSizePolicy.Policy.Maximum)

        self.box = _BoxPanel()
        self.box.setSizePolicy(QSizePolicy.Policy.Preferred,
                               QSizePolicy.Policy.Maximum)

        self.states = QStackedLayout()
        self.states.addWidget(self.running)
        self.states.addWidget(self.box)
        outer.addLayout(self.states)

        self.update_state(DriverState())

    @staticmethod
    def _show_gap(stat: "_Stat", gap: "GapView | None") -> None:
        """One neighbour block: the gap large, what it is doing underneath.

        **The seconds are the big number and the trend is the caption**, not
        the other way round. The gap is what he can act on immediately - a car
        1.2 s up is in DRS-ish range and one 12 s up is not - and the trend
        tells him whether acting is worth it. Both at a glance, in that order.
        """
        if gap is None or gap.seconds is None:
            # **A dash is the expected state, not a fault.** The gap boxes
            # these come from have never once returned a number in a real
            # race - see `race/gaps.py` - so this says why rather than
            # sitting blank and making him wonder what broke.
            stat.show_value("--", "no gap read")
            return
        stat.show_value(f"{gap.seconds:.1f}", gap.note,
                        urgent=gap.urgent, good=gap.good)

    def update_state(self, state: DriverState) -> None:
        self.states.setCurrentWidget(self.box if state.in_box else self.running)
        if state.in_box:
            self.box.show_state(state)
        temps = state.temps_c or {}
        for corner, widget in self.tyres.items():
            kind, lopsided = classify(corner, temps, state.compound)
            widget.show_value(temps.get(corner), kind, lopsided,
                              pair_gap(corner, temps),
                              (state.split_rates or {}).get(corner))
        self.tyre_caption.setText(
            "TYRE SURFACE °C" if not state.compound
            else f"TYRE SURFACE °C · {state.compound.upper()}")
        self._show_splits(state)
        self.last_call.show_call(state.last_call)

        if state.finished:
            self.box_stat.show_value("FLAG", "race over")
        elif state.laps_to_box is None:
            self.box_stat.show_value("--", "no plan")
        elif state.laps_past_box is not None:
            # **`laps_to_stop()` clamps at zero**, so a driver three laps past
            # his box lap read "0 laps to box, box on lap 15" - the current
            # lap, every lap, with nothing saying he was late. `past_box_lap`
            # carries the sign the clamp discards.
            self.box_stat.show_value(
                "NOW",
                "box this lap" if state.laps_past_box <= 0 else
                f"{state.laps_past_box} past the box lap",
                urgent=True)
        else:
            self.box_stat.show_value(
                f"{state.laps_to_box:.0f}",
                self._box_caption(state),
                # **Urgent inside two laps**, which is where the number stops
                # being background and starts being a thing to act on.
                urgent=state.laps_to_box <= 2)

        self._show_gap(self.ahead_stat, state.ahead)
        self._show_gap(self.behind_stat, state.behind)
        self._show_fuel(state)

        if state.position is None:
            # **A dash, not a zero.** `RaceState.position` is None until the
            # first packet is decoded and after a read the locator refused;
            # P0 is not a place anyone finished in.
            self.position_stat.show_value("--", "not read yet")
        else:
            # `P6` and `of 12` rather than the spoken `position_line`'s
            # "P6 of 12." - the same two numbers, laid out for an eye instead
            # of an ear.
            self.position_stat.show_value(
                f"P{state.position}",
                f"of {state.field_size}" if state.field_size else "")

    @staticmethod
    def _box_caption(state: DriverState) -> str:
        """What sits under the laps-to-box figure: the lap, and the decision.

        **The tyre decision moved here from the box panel**, where he could
        only read it once he was stationary and it was already being executed.
        "RS on" and "no tyres" ask for different in-laps and different brake
        balance, and the plan has said which since before the green.
        """
        if not state.box_on_lap:
            return ""
        plan = f"plan: lap {state.box_on_lap}"
        if state.tyres_at_stop is False:
            return f"{plan} · no tyres"
        if state.tyres_at_stop and state.compound:
            return f"{plan} · {state.compound.upper()} on"
        if state.tyres_at_stop:
            return f"{plan} · new set"
        # None: the plan did not say. Silence, because "fuel only" and "the
        # plan is quiet about it" are different answers and only one of them
        # is a decision he can act on.
        return plan

    def _show_fuel(self, state: DriverState) -> None:
        """The two in-hand figures, each against the distance it names.

        **Neither is urgent above zero.** There is no invented margin
        threshold on this board: the driver's own standing rule is that he
        will not carry a spare lap of fuel in a lap race, so 0.2 laps in hand
        is on plan and an alarm at 1.0 would fire in every race he drives.
        Below zero it does not reach, and that is worth an ink.

        **Each sub-line names the supply its own figure was measured on**, and
        neither borrows the other's. The stop figure is always the tank he is
        carrying, in laps. The flag figure names whichever of three bound it
        - the plan's fill, the fuel he arrives with, or a full tank - because
        that is the one thing that tells him whether the number is his to
        move. Where it is the plan's fill it will not move with what he is
        carrying, and it should not: a stop refills.

        **The live litres are not here.** `state.fuel_l` is the packet in
        hand and both figures are computed from the tank as it read at the
        last crossing, so printing the live number beside them put three
        readings of one tank on the screen, none reconciling with the others.
        The litres live on the box panel, where the stop is priced off them.
        """
        aboard = (None if state.laps_of_fuel is None
                  else f"{state.laps_of_fuel:.1f} laps aboard")
        if state.fuel_to_stop is None:
            self.stop_stat.show_value("--", state.fuel_to_stop_why or aboard
                                      or "not measured")
        else:
            self.stop_stat.show_value(
                f"{state.fuel_to_stop:.1f}", aboard or "",
                urgent=state.fuel_to_stop < 0)

        # **The burn is not on the running board, and the reason is width.**
        # Four blocks across a 2,560 px panel leave about 580 px each, which
        # is twenty-one characters; `on the plan's fill · 4.19 L/lap` wants
        # thirty-one and would have been elided into something he could not
        # read. The reference is the half that has to survive - it is what
        # says whether the figure is his to move - and the litres per lap are
        # in the voice and on the box panel. `9.1 laps aboard` beside the
        # stop figure already carries the supply in the unit he plans in.
        rests_on = state.fuel_to_flag_on or ""
        if state.fuel_to_flag is None:
            self.flag_stat.show_value(
                "--", state.fuel_to_flag_why or rests_on or "not measured")
        else:
            self.flag_stat.show_value(
                f"{state.fuel_to_flag:.1f}", rests_on,
                urgent=state.fuel_to_flag < 0)

    def _show_splits(self, state: DriverState) -> None:
        """The axle gap and the rear pair, per lap, with their lap count.

        **The figure is drawn positive and the direction is a caption.** A
        minus sign on a glance instrument is a thing to decode; `REAR OVER
        FRONT` and `FRONT OVER REAR` are two different diagnoses said in
        words, which is what rule 13 asks for.
        """
        laps = ("no laps yet" if not state.split_laps else
                "1 lap" if state.split_laps == 1 else
                f"{state.split_laps} laps")
        figure, direction = axle_words(state.axle_split_c)
        if figure is None:
            self.axle_stat.set_label("rear v front")
            self.axle_stat.show_value("--", laps)
        else:
            self.axle_stat.set_label(direction)
            self.axle_stat.show_value(
                f"{figure:.1f}",
                self._split_sub(laps, trend_word(state.axle_split_c,
                                                 state.axle_split_rate),
                                state.axle_split_rate))

        hotter = state.rear_pair_hotter
        if hotter is None or state.rear_pair_split_c is None:
            self.rear_pair_stat.set_label("rr v rl")
            self.rear_pair_stat.show_value("--", laps)
            return
        cooler = PAIRS[hotter]
        self.rear_pair_stat.set_label(f"{hotter} over {cooler}")
        self.rear_pair_stat.show_value(
            f"{state.rear_pair_split_c:.1f}",
            # The pair figure is positive by construction, so its trend word
            # is read straight off the sign of the rate.
            self._split_sub(laps, trend_word(state.rear_pair_split_c,
                                             state.rear_pair_rate),
                            state.rear_pair_rate))

    @staticmethod
    def _split_sub(laps: str, word: str, rate: float | None) -> str:
        """`6 laps · widening 1.4/lap`, or just the lap count.

        Silent about the direction where there is no rate: five laps have not
        been sampled, or the movement is inside the derived floor. **No rate
        is not a rate of zero** and "settling" would be a claim - see
        `race/tyre_split.py`, which owns the arithmetic and the threshold.
        """
        if not word or rate is None:
            return laps
        return f"{laps} · {word} {abs(rate):.1f}/lap"
