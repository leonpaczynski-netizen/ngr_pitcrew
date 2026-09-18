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
    rank 3                  lap-time panel | four corner temperatures |
                            WET · ABS/LOCK · TCS lights
    rank 2 (middle)         laps to the stop | in hand to the stop | in hand to
                            the flag | position
    rank 1 (bottom, 180px)  gap ahead | gap behind

**With the phone strip reading** (15 Sep 2026, `ui/strip.py`) rank 1 and
LAPS TO THE STOP leave this board for his phone on the game monitor, and come
back the moment the phone stops polling (`DriverState.strip_live`). Every
block's words live in the `*_block` functions below so the two surfaces
cannot word one number twice.

**In practice and qualifying** (the board opens for them from 14 Sep 2026)
ranks 1 and 2 are race-only and hidden, and the lap-time panel takes rank 1:

    rank 4                  the last call
    rank 3                  four corner temperatures | the three lights
    rank 1 (bottom)         laptime | time diff | pred. time

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

--- rank 2 · laps to the stop -------------------------------------------------

From `RaceState.laps_to_stop()` - laps still to drive to the box, the in-lap
included - which clamps at zero, so `laps_past_box` (`RaceState.laps_overdue`)
carries the sign the clamp throws away: "NOW / box this lap" on the in-lap and
"NOW / 2 past the box lap" are different news. Urgent inside two laps.

**The caption names the plan's in-lap in GT7's numbering** -
`RaceState.box_lap_on_screen()`, which is `lap_on_screen() + laps_to_stop() -
1`. It was the app's lap count, one behind the HUD at every crossing and
further behind after a crossing lost in the pit lane (Road Atlanta: +1 on lap
1, +2 by lap 20). **And then it was `lap_on_screen() + laps_to_stop()`**,
defended here as the convention `_box_now` executed by firing at zero - which
was one lap late. Bathurst, 14 Sep 2026, plan `pit_laps` [11]: this block said
lap 12, the voice said "Box this lap" with eleven laps done, and he boxed on
12. The lap in progress is the in-lap at ONE (see `laps_to_stop`).

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

--- rank 3 · the lap-time panel and the three lights ---------------------------

**The tyre splits were removed on 14 Sep 2026, at the driver's call.** They were
a whole-stint signal resting on one stint's association (four corners, r=+0.82,
n=4) that changed nothing he could do on a straight, and the game's own wear
gauge already tells him which tyre is going. `race/tyre_split.SplitHistory`
stays: it still drives the per-corner "+N vs RL WIDENING" line under each tyre.

**Laptime / Time Diff / Pred. Time**, laid out as his reference image. The diff
is live minus the reference lap at the same distance, so **negative is faster
and green, positive slower and amber**. Two references, both named under the
panel: this session's best lap (the diff) and the best lap on file for this
car, circuit and game version (a second figure, because it may be another
setup or another day).

**Three lights**, each lit only on a reading and each saying where it comes from:

* **WET** - `telemetry/hygrometer.py`, calibrated 14 Sep 2026: a fill bar of
  water under the car, so the light follows the last few HUD reads, and a
  tunnel on a wet track reads dry for a second. Unreadable HUD is "cannot see",
  never DRY.
* **ABS** - GT7 sends no ABS signal and "ABS active" cannot be derived: with ABS
  off, heavy braking sits in the same slip band ABS holds (13-24% of frames on
  the Shelby, against 13-44% with ABS Weak). What ABS removes is the lock tail,
  so the box names the event's setting and lights **LOCK** when a front wheel
  locks (slip below 0.80) - derived, and it says so.
* **TCS** - `flags_raw` bit 11, calibrated on his TCS-on lap of 14 Sep 2026:
  22% of frames with TCS on, 0.01% off, and set on 82% of the hard-throttle
  wheelspin frames.

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

from PyQt6.QtCore import QEasingCurve, QPropertyAnimation, QRectF, Qt, pyqtProperty
from PyQt6.QtGui import QColor, QPainter, QPainterPath, QPen
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
from pitcrew.race.calls import (MARK_UNCONFIRMED, NO_PLAN, NO_STOP_TO_COME,
                                RACE_OVER)
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

# What an empty neighbour block says. Not "no gap read": nothing failed, there
# is simply no car there (`RaceState.nobody_on`).
NOBODY_AHEAD = "nobody ahead · P1"
NOBODY_BEHIND = "nobody behind"


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
    # **The compound the plan says to FIT, which is not `compound`.** On track
    # `compound` is the set bolted to the car - the only honest answer for the
    # four corner temperatures - and the laps-to-box caption was rendering it
    # as the plan's decision. On any compound-changing stop, which is the only
    # kind where that caption earns its place, the board named the wrong tyre
    # while the voice said the right one, in the same ten seconds and with no
    # way for him to ask which (rules 12 and 13). `_tyre_word` reads
    # `next_compound` and so does this.
    next_compound: str | None = None
    laps_to_box: float | None = None
    box_on_lap: int | None = None
    laps_of_fuel: float | None = None
    fuel_l: float | None = None
    burn_l: float | None = None

    # ---- what kind of session this is. The board opens for races, practice
    # and qualifying (the driver, 14 Sep 2026); in practice and qualifying the
    # race-only numbers - gaps, stop, fuel to the flag, position - have nothing
    # to show and are hidden rather than dashed, and the lap-time panel takes
    # the bottom rank he glances at. In a race the gaps keep it.
    session_kind: str = "race"          # "race" | "practice" | "qualifying"

    # ---- the lap-time panel (row 5.21). All times are GT7's own current-lap
    # clock where the C packet carries it. **The delta is live minus the
    # reference at the same point on the lap**: negative is faster, drawn
    # green; positive is slower, drawn amber. None is a dash with a reason.
    lap_time_ms: int | None = None
    delta_s: float | None = None            # against this session's best lap
    session_best_ms: int | None = None
    predicted_ms: int | None = None         # session best plus the live delta
    delta_file_s: float | None = None       # against the best lap on file
    file_best_ms: int | None = None
    delta_why: str | None = None            # why there is no delta
    # The compound both references are locked to (the driver, 14 Sep 2026:
    # "all best times should be locked to compound"). Named on the board so
    # "vs session best" can never be read as a best on another tyre.
    reference_compound: str | None = None
    # **The last lap's three sectors against this session's bests** on the
    # same tyre and lines (the driver, 15 Sep 2026). `race.board_live.
    # SectorsView`; None where no live reader is armed.
    sectors: "SectorsView | None" = None

    # ---- the plan's per-lap targets, race only (the driver, 16 Sep 2026).
    # What the lap being driven is asked for - a lap time on this compound,
    # this set's age and this fuel, and a burn - and how the LAST completed
    # lap did against its own. Positive is slow / over. The same verdict the
    # heartbeat speaks (`race/targets.py`). None is a dash with a reason.
    target_lap_ms: int | None = None
    target_burn_l: float | None = None
    target_why: str | None = None           # why the lap has no target time
    target_saving: bool | None = None       # priced on the fuel-saving beep
    last_vs_target_s: float | None = None
    last_burn_vs_target_l: float | None = None
    # This stint's mean burn against target, over the laps on the column the
    # last one was driven on, and how many laps that is (`targets.stint_burn`).
    stint_burn_vs_target_l: float | None = None
    stint_burn_laps: int = 0
    stint_burn_saving: bool | None = None

    # ---- the lap-timer face on the phone (17 Sep 2026). GT7's own figures:
    # the last completed lap it reports, and the lap its HUD shows - in a race
    # the controller replaces that with `RaceState.lap_on_screen`, the one
    # expression the box lap is already counted in.
    last_lap_ms: int | None = None
    lap_number: int | None = None

    # ---- the monitor as history (17 Sep 2026). His three-screen split puts
    # his car on the phone and the field on the tablet, and leaves this screen
    # the one he looks at least: every lap of the race as it was judged.
    # `RaceState.lap_history`, newest last. Drawn only while BOTH the phone
    # and the tablet are reading - with either of them gone this board is his
    # live pit board again, which is what it has always been.
    history: tuple = ()
    show_history: bool = False

    # ---- the three lights (row 5.21).
    # WET: the hygrometer over the last few HUD reads - "wet", "mixed", "dry",
    # or None where the HUD could not be read (never "dry" for want of a read).
    wet: str | None = None
    # ABS: GT7 sends no ABS signal. The box shows the event's ABS setting and
    # lights LOCK when a front wheel locks under braking - DERIVED from wheel
    # speed (front slip below 0.80), because that tail is what ABS removes.
    abs_setting: str | None = None
    # None: no packet to read a lock off (rule 3) - not "no lock".
    front_lock: bool | None = None
    # TCS: flags_raw bit 11, calibrated on the driver's TCS-on lap of 14 Sep
    # (22% of frames on, 0.01% off). None where no packet carries the flags.
    tcs_active: bool | None = None

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
    # **A strip page is receiving this board right now** - his phone on the
    # game monitor (15 Sep 2026). While it is, the neighbour gaps and laps to
    # the stop are read off the phone and leave this board; the moment it
    # stops polling they come back here. Set by the controller from
    # `StripServer.live()`, never assumed: a phone that went flat mid-race
    # must not take two numbers off both screens at once.
    strip_live: bool = False


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


class _Face(QWidget):
    """A rounded plate whose fill changes by wiping down, never by cutting.

    **Motion as signal, and only where the meaning changed** (15 Sep 2026).
    A lamp lighting or a figure turning into an instruction is the moment he
    needs to catch out of the corner of his eye, and a colour that simply
    swaps between two frames is the easiest change there is to miss. So the
    new fill is painted down over the old in 180 ms - the stroke
    `widgets.CompoundBand` paints a compound with, which is DESIGN.md's one
    authored motion, and nothing else on this board moves.

    Painted rather than styled: a stylesheet background cannot be part-drawn.
    Instant where the widget is not on screen, so a hidden page and the tests
    see the end state, never a frame of the wipe.
    """

    WIPE_MS = 180
    RADIUS = 10

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._fill: str | None = None
        self._under: str | None = None
        self._border: str | None = None
        self._wipe = 1.0
        self._animation = QPropertyAnimation(self, b"wipe", self)
        self._animation.setDuration(self.WIPE_MS)
        self._animation.setEasingCurve(QEasingCurve.Type.OutCubic)

    def set_face(self, fill: str | None, border: str | None) -> None:
        """`fill` None is no plate at all; `border` None is no edge."""
        if fill == self._fill and border == self._border:
            return
        self._border = border
        if fill != self._fill:
            self._under, self._fill = self._fill, fill
            if self.isVisible():
                self._animation.stop()
                self._wipe = 0.0
                self._animation.setStartValue(0.0)
                self._animation.setEndValue(1.0)
                self._animation.start()
            else:
                self._wipe = 1.0
                self._wiped()
        self.update()

    def fill_showing(self) -> str | None:
        """The fill behind most of the face right now, for choosing ink.

        **The ink follows the wipe past halfway, not the request.** Switched
        when the flood was asked for, the figure went to ground ink over a
        fill still at the top of the plate - dark on dark, and the number
        blinked out for the length of the wipe (first render, 15 Sep 2026).
        """
        return self._fill if self._wipe >= 0.5 else self._under

    def _wiped(self) -> None:
        """The fill behind the face has changed over; re-ink to match."""

    # Declared in the class body: PyQt builds the meta-object when the class
    # is created, and an animation cannot find a property added afterwards.
    @pyqtProperty(float)
    def wipe(self) -> float:
        return self._wipe

    @wipe.setter
    def wipe(self, value: float) -> None:
        crossed = self._wipe < 0.5 <= value
        self._wipe = value
        if crossed:
            self._wiped()
        self.update()

    def paintEvent(self, event) -> None:            # noqa: N802 - Qt naming
        if self._fill is None and self._under is None and self._border is None:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        path = QPainterPath()
        path.addRoundedRect(rect, self.RADIUS, self.RADIUS)
        painter.setClipPath(path)
        wipe = max(0.0, min(1.0, self._wipe))
        edge = rect.top() + rect.height() * wipe
        if self._under is not None and wipe < 1.0:
            # What is left of the old fill, below the edge coming down.
            painter.fillRect(QRectF(rect.left(), edge, rect.width(),
                                    rect.bottom() - edge), QColor(self._under))
        if self._fill is not None:
            painter.fillRect(QRectF(rect.left(), rect.top(), rect.width(),
                                    edge - rect.top()), QColor(self._fill))
        painter.setClipping(False)
        if self._border is not None:
            painter.setPen(QPen(QColor(self._border), 2))
            painter.drawPath(path)


class _Stat(_Face):
    """One large number with a caption under it."""

    def __init__(self, label: str, parent: QWidget | None = None, *,
                 value_px: int | None = None) -> None:
        super().__init__(parent)
        self._floods = False
        self._flooded = False
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
        self._recaption(INK_DIM)
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
    # them taken off - see the note below, which is what that turned out to
    # be worth. `test_the_board_fits_his_monitor_on_the_faces_he_actually_has`
    # is what holds the board to the actual monitor.
    # **Two faces, and the numbers differ by 1.7.** On the rig, Cascadia Mono
    # at 27 px is 16 px a character, so the middle rank's 640 holds forty and
    # nothing on the board is elided at all. Under the offscreen platform the
    # tests run on, the same stylesheet falls back to a stub metric of 27 px
    # a character - twenty-three - and the longest strings DO elide there.
    #
    # **These are not "the panel's room divided by the blocks on it."** They
    # were described that way and the arithmetic does not hold: driven to
    # their caps the middle rank and the box page both measure past 2,560
    # offscreen. The board fits because the blocks do not all reach their cap
    # at once - POSITION's sub is `of 12`.
    #
    # **On the rig these caps never fire at all**, because his face is 16 px
    # a character and the longest string on the board is well inside them. So
    # what they are is insurance against a string nobody has written yet, and
    # what holds the panel is
    # `test_the_board_fits_his_monitor_on_the_faces_he_actually_has`. That
    # test's HEIGHT leg bites - `GAP_PX = 210` and `LINES = 3` both fail it -
    # and its width leg cannot, because the real-face board has some 600 px
    # of headroom. Stated rather than engineered around: the width is not
    # under threat and pretending a guard tests it would be worse than
    # saying it does not.
    MIDDLE_SUB_W = 640
    GAP_SUB_W = 1100
    BOX_SUB_W = 620

    # The side room a flooded plate needs so its figure does not touch the
    # edge. Horizontal only: the board is 25 px inside his panel's height and
    # has hundreds of pixels spare across it.
    FLOOD_SIDE_PX = 26

    def set_flood(self, floods: bool = True) -> None:
        """Let an urgent reading fill this block, not only colour its ink.

        **Only for a figure that asks for an action** - laps to the stop at
        NOW, fuel short, the release countdown. A neighbour catching is urgent
        too, but it is a trend to weigh, not a thing to do this lap, and two
        plates flooding at once would be two claims on one glance. The room
        is reserved whether or not it is flooded, so the board never reflows
        when a plate lights.
        """
        self._floods = floods
        side = self.FLOOD_SIDE_PX if floods else 0
        self.layout().setContentsMargins(side, 0, side, 0)

    def _recaption(self, ink: str) -> None:
        self.caption.setStyleSheet(
            f"font-family:{LABEL_FACE};font-size:{self.CAPTION_PX}px;"
            f"font-weight:600;letter-spacing:7px;color:{ink};"
            f"background:transparent;")

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
                   urgent: bool = False, good: bool = False,
                   act: bool | None = None) -> None:
        """`urgent` and `good` are the two ends of one reading, not two flags.

        Both false is the honest middle - steady, or too few laps to say -
        and it stays white. `urgent` wins if somehow both arrive, because the
        cost of missing bad news is higher than the cost of missing good.

        `act` is whether this urgent reading is an instruction for now, and
        only then does a flooding block flood. None takes it from `urgent`;
        laps to the stop passes it explicitly, because it is amber from two
        laps out and a plate that fills two laps early teaches him to ignore
        the plate.
        """
        self.value.setText(text)
        self._sub_text = sub
        self._resub()
        flooded = self._floods and urgent and (urgent if act is None else act)
        self._urgent, self._good = urgent, good
        if flooded != self._flooded:
            self._flooded = flooded
            self.set_face(NEAR if flooded else None, NEAR if flooded else None)
        self._reink()

    def _wiped(self) -> None:
        self._reink()

    def _reink(self) -> None:
        # On the plate every line is the ground ink, which is 12:1 against
        # the amber; the dim ink would be lost on it.
        plate = self.fill_showing() is not None
        urgent, good = getattr(self, "_urgent", False), getattr(self, "_good", False)
        ink = GROUND if plate else NEAR if urgent else GOOD if good else INK
        if ink != self._ink:
            self._ink = ink
            self._restyle()
            self._recaption(GROUND if plate else INK_DIM)
        self.sub.setStyleSheet(
            f"font-family:{NUMBER_FACE};font-size:{self.SUB_PX}px;"
            f"color:{ink if (plate or urgent or good) else INK_DIM};"
            f"background:transparent;")
        # The stylesheet is re-applied above, which can change the face the
        # metrics resolve to; the elide has to be redone against it.
        self._resub()

def format_lap_ms(ms: int | float | None) -> str:
    """`1:32.418`, or a dash. Minutes are shown only when there are some."""
    if ms is None or ms < 0:
        return "-:--.---"
    total_ms = int(round(ms))
    minutes, rest = divmod(total_ms, 60_000)
    seconds, millis = divmod(rest, 1000)
    return f"{minutes}:{seconds:02d}.{millis:03d}"


def format_delta(seconds: float | None) -> str:
    """`-0.214` faster, `+0.312` slower, or a dash. Three decimals, as every
    timing screen draws it, and the sign always printed."""
    if seconds is None:
        return "--.---"
    return f"{seconds:+.3f}"


# ============================================================================
# **What a block says, apart from how it is drawn.** Two surfaces draw these
# now - the Qt board on the ultrawide and the strip page on his phone
# (`ui/strip.py`) - and a number worded twice is a number that drifts: the
# fuel block already carried "-7.1 in hand" once for want of one expression.
# So the words, the value and whether it is bad news are decided here, once,
# and each surface only chooses a size and an ink.
# ============================================================================

TONE_PLAIN = "plain"
TONE_URGENT = "urgent"
TONE_GOOD = "good"


@dataclass(frozen=True)
class Block:
    """One number as a surface draws it: the value, the line under it, and
    which of the three readings it is. `urgent` wins over `good`, as
    `_Stat.show_value` has always had it."""
    value: str
    sub: str = ""
    tone: str = TONE_PLAIN

    @property
    def urgent(self) -> bool:
        return self.tone == TONE_URGENT

    @property
    def good(self) -> bool:
        return self.tone == TONE_GOOD


def _tone(urgent: bool, good: bool = False) -> str:
    return TONE_URGENT if urgent else TONE_GOOD if good else TONE_PLAIN


def tyre_clause(state: "DriverState", head: str) -> str:
    """`head` with the plan's tyre decision appended, or `head` alone.

    **One expression for both captions.** The countdown and the "NOW"
    that replaces it are the same block saying the same thing about the
    same stop, and the decision went missing from the second because they
    were written twice.

    `· fuel only` rather than `· no tyres`: it is the box panel's own
    word for this decision, and on the running board the pair has to be
    told apart in the dimmest ink on the screen at 200 km/h - where
    `no tyres` and `new set` differ only in a two-word tail.
    """
    if state.tyres_at_stop is False:
        return f"{head} · fuel only"
    if state.tyres_at_stop and state.next_compound:
        return f"{head} · fit {state.next_compound.upper()}"
    if state.tyres_at_stop:
        return f"{head} · fit a set"
    # None: the plan did not say. Silence, because "fuel only" and "the
    # plan is quiet about it" are different answers and only one of them
    # is a decision he can act on.
    return head


def box_caption(state: "DriverState") -> str:
    """What sits under the laps-to-box figure: the lap, and the decision.

    **The tyre decision moved here from the box panel**, where he could
    only read it once he was stationary and it was already being
    executed. "Fit RS" and "fuel only" ask for different in-laps and
    different brake balance, and the plan has said which since before the
    green.
    """
    if state.box_on_lap is None:
        return ""
    return tyre_clause(state, f"plan: lap {state.box_on_lap}")


def box_block(state: "DriverState") -> Block:
    """LAPS TO THE STOP: the countdown, NOW, FLAG, or a dash that says why."""
    if state.finished:
        return Block("FLAG", RACE_OVER)
    if state.laps_to_box is None and state.has_plan:
        # **A plan with no further stop is not "no plan".**
        # `laps_to_stop()` is None exactly when `stint_ends_on_lap` is,
        # and `_apply_stint` sets that to None on the LAST stint - so
        # this block told him the engineer had no plan for laps 12-20 of
        # every one-stop race, and for the whole of a zero-stop one,
        # while `IN HAND TO THE FLAG` two blocks along was live and
        # right. He has no reason to trust a number on a board that says
        # nobody is planning.
        #
        # This is the third page this same defect has been fixed on -
        # `_BoxPanel` carries "the board said 'no plan' while a plan was
        # being executed" and the `finished` branch carries "'no plan' is
        # the wrong thing to tell a man who has just finished". The words
        # are `race/calls.py`'s, so the board and the fuel block say the
        # same thing about the same fact (rule 13).
        return Block("--", NO_STOP_TO_COME)
    if state.laps_to_box is None:
        # The same constant the fuel block beside it uses for the same
        # fact - with no plan running both say "no plan".
        return Block("--", NO_PLAN)
    if state.laps_past_box is not None:
        # **`laps_to_stop()` clamps at zero**, so a driver three laps past
        # his box lap read "0 laps to box, box on lap 15" - the current
        # lap, every lap, with nothing saying he was late.
        # `RaceState.laps_overdue` carries the sign the clamp discards:
        # 0 on the in-lap, N once N in-laps have gone by.
        # **The tyre word survives the in-lap.** This branch is taken on
        # the in-lap, so `box_caption` is not called on the one lap the
        # decision is executed - and the whole case for putting it on
        # this block is that "fit a set" and "fuel only" ask for
        # different in-laps and different brake balance. The voice says
        # "Box this lap. RS on." here; the board said nothing.
        late = ("box this lap" if state.laps_past_box <= 0 else
                f"{state.laps_past_box} past the box lap")
        return Block("NOW", tyre_clause(state, late), TONE_URGENT)
    # **Urgent inside two laps**, which is where the number stops being
    # background and starts being a thing to act on.
    return Block(f"{state.laps_to_box:.0f}", box_caption(state),
                 _tone(state.laps_to_box <= 2))


def gap_block(gap: "GapView | None") -> Block:
    """One neighbour: the gap large, what it is doing underneath.

    **The seconds are the big number and the trend is the caption**, not
    the other way round. The gap is what he can act on immediately - a car
    1.2 s up is in DRS-ish range and one 12 s up is not - and the trend
    tells him whether acting is worth it. Both at a glance, in that order.
    """
    if gap is None or gap.seconds is None:
        # **A dash is the expected state, not a fault.** The gap boxes
        # these come from have never once returned a number in a real
        # race - see `race/gaps.py` - so this says why rather than
        # sitting blank and making him wonder what broke. A view with no
        # seconds and a note is an empty side (`NOBODY_AHEAD`), which is
        # its own reason.
        return Block("--", (gap.note if gap is not None and gap.note
                            else "no gap read"))
    return Block(f"{gap.seconds:.1f}", gap.note, _tone(gap.urgent, gap.good))


def fuel_stop_block(state: "DriverState") -> Block:
    """IN HAND TO THE STOP. **Not urgent above zero** - see `_show_fuel`."""
    aboard = (None if state.laps_of_fuel is None
              else f"{state.laps_of_fuel:.1f} laps aboard")
    if state.fuel_to_stop is None:
        return Block("--", state.fuel_to_stop_why or aboard or "not measured")
    return Block(f"{state.fuel_to_stop:.1f}", aboard or "",
                 _tone(state.fuel_to_stop < 0))


def release_block(state: "DriverState") -> Block:
    """RELEASE IN, the seconds he is holding the trigger on.

    **Urgent the whole way down from ten seconds**, not only at zero. He has
    to move his hand to the trigger, and a release that turns red at the
    moment it is due is a release he is late for.
    """
    seconds = state.release_in_s
    if seconds is None:
        # **The dash says why.** This is the one figure the driver is
        # holding the trigger on, and it was the only one on the panel
        # showing a bare dash with an empty caption under it.
        # **`is not None`, not truthiness.** `fuel_target_l` is
        # deliberately unclamped and returns a real `0.0` where the stop
        # covers no laps, so the truthy test made RELEASE IN say
        # "nothing sized it" while FUEL TO one block along drew `0` -
        # two adjacent blocks contradicting each other about whether the
        # stop had been sized. CLAUDE.md rule 3, and the same shape as
        # the capacity hole already fixed in `calls.py`.
        reason = ("no fill rate here" if state.fuel_target_l is not None
                  else "nothing sized it")
        return Block("--", reason)
    return Block(format_release(seconds),
                 "seconds" if seconds > 0 else "release now",
                 _tone(seconds <= 10))


def fuel_target_block(state: "DriverState") -> Block:
    """FUEL TO: what the tank should read at release, litres."""
    if state.fuel_target_l is None:
        # Nothing sized the stop. Silence rather than a number the app
        # invented - the same refusal `RefuelWatch.note` makes, and for
        # the same reason: he is holding the trigger on this figure.
        return Block("--", "nothing sized it")
    parts = []
    if state.fuel_l is not None:
        # **"aboard", not a bare unit.** This block draws a big
        # target with the tank under it, and `31 L` under `63` does
        # not say which is which - `aboard` is the word separating
        # what is in the tank now from what is going in, and the
        # running board uses `laps aboard` for the same idea. It was
        # shortened to fit a bound computed from the wrong font.
        parts.append(f"{state.fuel_l:.0f} aboard")
    # Which rate the seconds beside it were priced at. A rate measured
    # at this pump and one typed on the event page are not the same
    # claim, and the countdown is only as good as whichever it used.
    if state.fill_rate_note:
        parts.append(state.fill_rate_note)
    return Block(f"{state.fuel_target_l:.0f}", " · ".join(parts))


def tyres_block(state: "DriverState") -> Block:
    """TYRES in the box: the plan's decision, not a reading off the car.

    Nothing here knows how worn the set coming off is, because no packet
    format carries wear at all.

    **"No plan" used to cover two different facts.** `next_compound` is
    also None when a plan IS running and simply does not name a compound
    for the next stint - which is the honest state after a mid-race
    replan - so the board told him there was no plan while one was being
    executed.
    """
    if state.tyres_at_stop is False:
        # The plan's decision in the box is "fuel only". Said as the
        # decision, not as a compound - the compound on the car is what
        # stays on it.
        return Block("NO TYRES", "plan · fuel only")
    if state.next_compound:
        # **`next_compound`, not `compound`.** They are two claims - the
        # set going on and the set coming off - and this panel wants the
        # first. It read `compound` and was right only because the
        # controller overwrote that field with `next_compound` on the
        # in-box branch, so one field meant two things depending on a
        # boolean set in another module. That is the defect fixed one
        # page over in `box_caption`, not the fix for it.
        return Block(state.next_compound,
                     "plan · new set" if state.tyres_at_stop else "plan")
    if state.tyres_at_stop:
        # **A set IS going on and the plan did not name which.** This
        # rendered a bare dash - on the one panel he reads with his hands
        # on the MFD, while the same board had said "new set" on the
        # straight and the voice had said "Tyres on." `handover.validate`
        # permits `tyres` with no `compound`, so it is plan-reachable, and
        # a dash where the opposite decision gets the word NO TYRES is how
        # he takes a fuel-only stop the plan did not ask for.
        return Block("NEW SET", "plan · set not named")
    if state.past_the_plan:
        # **Past the end of the stint list is not "the plan did not name
        # a compound".** An unplanned splash sets `past_the_plan` and
        # leaves `next_tyres` and `next_compound` None, and this block
        # said the plan had asked for a stop and not named a tyre while
        # the block beside it said the plan does not reach this stop at
        # all. He fits tyres nobody asked for - three seconds and a cold
        # out-lap (CLAUDE.md 5.4).
        return Block("--", "past the plan")
    if state.has_plan:
        return Block("--", "plan: no compound")
    return Block("--", "no plan")


def delta_block(state: "DriverState") -> Block:
    """TIME DIFF: live minus the reference at the same point on the lap.
    Negative is faster and good; positive is slower and drawn in the warning
    ink, as `_LapTimePanel` has it."""
    delta = state.delta_s
    tone = (TONE_PLAIN if delta is None or delta == 0
            else TONE_GOOD if delta < 0 else TONE_URGENT)
    return Block(format_delta(delta), lap_reference_note(state), tone)


def target_pace_block(state: "DriverState") -> Block:
    """VS TARGET: the last lap against the time the plan asked of it.

    Green on target or quicker, the warning ink when slow past the band - the
    band the voice uses, so "Pace on target." and a green box are one
    decision (rule 12). The sub names what THIS lap is asked for.
    """
    from pitcrew.race.targets import ON_TARGET_S

    delta = state.last_vs_target_s
    if delta is None:
        tone = TONE_PLAIN
    elif delta >= ON_TARGET_S:
        tone = TONE_URGENT
    else:
        tone = TONE_GOOD
    return Block(format_delta(delta) if delta is not None else "--",
                 target_note(state), tone)


def target_burn_block(state: "DriverState") -> Block:
    """BURN VS TARGET: the last lap's litres against the plan's per-lap burn."""
    from pitcrew.race.targets import ON_TARGET_L

    delta = state.last_burn_vs_target_l
    if delta is None:
        return Block("--", (f"target {state.target_burn_l:.2f} L"
                            if state.target_burn_l is not None else "no target"))
    tone = TONE_URGENT if delta >= ON_TARGET_L else TONE_GOOD
    return Block(f"{delta:+.2f}", (f"target {state.target_burn_l:.2f} L"
                                   if state.target_burn_l is not None else ""),
                 tone)


def target_strip_block(state: "DriverState") -> Block:
    """VS TARGET for the phone strip: the lap gap, the burn under it.

    One block for both surfaces (rules 12 and 13) - the phone's figure is the
    board's `target_pace_block` value with the board's burn line as its
    reason, so the two cannot word one lap two ways. None where the lap got
    no verdict at all: the strip hides a slot rather than showing a dash it
    has no room to explain.
    """
    pace = target_pace_block(state)
    if state.last_vs_target_s is None and state.last_burn_vs_target_l is None:
        return Block("--", state.target_why or "no target", TONE_PLAIN)
    burn = target_burn_block(state)
    against = ("" if state.target_burn_l is None
               else f" of {state.target_burn_l:.2f}")
    return Block(pace.value, f"burn {burn.value}{against}", pace.tone)


# ============================================================================
# **The phone's lap-timer face** (the driver, 17 Sep 2026, from a photo of a
# lap timer: last lap and today's best across the top, the delta as a flood
# across the middle, the lap bottom-left - "instead of time of day at bottom
# have our fuel target and burn to it"). Expressions here, beside the board's,
# so a figure on the phone and the same figure on the ultrawide are one
# decision (rules 12 and 13).

def face_last_block(state: "DriverState") -> Block:
    """LAST LAP: GT7's own last completed lap."""
    return Block(format_lap_ms(state.last_lap_ms))


def face_lap_block(state: "DriverState") -> Block:
    """LAP: the lap his HUD shows."""
    return Block(str(state.lap_number) if state.lap_number else "--")


def face_best_block(state: "DriverState") -> tuple[str, Block]:
    """`(caption, block)` for top right - what the delta is against.

    Practice and qualifying: **the best lap ever recorded on this compound**
    (his words), which is `best_lap_on_file` - this car, this circuit, this
    game version, this tyre. Race: the lap time the plan asks of this lap.
    """
    if state.session_kind == "race":
        saving = " · SAVE" if state.target_saving else ""
        return (f"PLAN LAP{saving}",
                Block(format_lap_ms(state.target_lap_ms), "", TONE_PLAIN))
    tyre = f" · {state.reference_compound}" if state.reference_compound else ""
    return (f"BEST{tyre}",
            Block(format_lap_ms(state.file_best_ms), "",
                  TONE_GOOD if state.file_best_ms is not None else TONE_PLAIN))


def face_delta_block(state: "DriverState") -> tuple[str, Block]:
    """`(caption, block)` for the flood: the live delta to top right's lap.

    **Race: the projected lap against the plan's lap**, live - the session
    best plus the live delta to it, which is `predicted_ms`, less the target.
    A projection, so the line under it says "projected" (rule 5). Until there
    is a session best to project from, the last lap's verdict stands in and
    says so. The band is the voice's `ON_TARGET_S`, as VS TARGET's is.

    Practice and qualifying: the live delta to the best on file, negative
    quick.
    """
    if state.session_kind == "race":
        from pitcrew.race.targets import ON_TARGET_S

        if state.predicted_ms is not None and state.target_lap_ms is not None:
            delta = (state.predicted_ms - state.target_lap_ms) / 1000.0
            sub = f"projected {format_lap_ms(state.predicted_ms)}"
        elif state.last_vs_target_s is not None:
            delta = state.last_vs_target_s
            sub = "last lap"
        else:
            return "VS PLAN LAP", Block("--", state.target_why or "no plan lap")
        tone = TONE_URGENT if delta >= ON_TARGET_S else TONE_GOOD
        return "VS PLAN LAP", Block(format_delta(delta), sub, tone)
    delta = state.delta_file_s
    if delta is None:
        why = ("no best on file" if state.file_best_ms is None
               else state.delta_why or "not on a lap")
        return "VS BEST", Block("--.---", why)
    tone = TONE_GOOD if delta < 0 else TONE_URGENT if delta > 0 else TONE_PLAIN
    return "VS BEST", Block(format_delta(delta), "", tone)


def face_burn_block(state: "DriverState") -> Block | None:
    """BURN VS PLAN: the last lap's litres over the plan's, and the stint's.

    **The stint figure is only the column he is on** (`targets.stint_burn`),
    and names it - "save" or "full" - with its lap count (rule 4). None
    outside a race: practice has no plan burn to be against.
    """
    if state.session_kind != "race":
        return None
    from pitcrew.race.targets import ON_TARGET_L

    stint = ""
    if state.stint_burn_vs_target_l is not None:
        column = ("save" if state.stint_burn_saving
                  else "full" if state.stint_burn_saving is False else "")
        laps = state.stint_burn_laps
        stint = (f"stint {state.stint_burn_vs_target_l:+.2f} · {laps} "
                 f"lap{'s' if laps != 1 else ''}"
                 + (f" · {column}" if column else ""))
    delta = state.last_burn_vs_target_l
    if delta is None:
        return Block("--", stint or (f"plan {state.target_burn_l:.2f} L/lap"
                                     if state.target_burn_l is not None
                                     else "no plan burn"))
    tone = TONE_URGENT if delta >= ON_TARGET_L else TONE_GOOD
    return Block(f"{delta:+.2f}", stint, tone)


# How many laps the rack draws. A race is thirty-odd laps and this is read
# between stints, not at speed; the rest of the race is the export's job.
HISTORY_ROWS = 12


@dataclass(frozen=True)
class HistoryRow:
    """One lap on the monitor's rack, already worded."""
    lap: str
    time: str
    delta: str
    burn: str
    note: str
    delta_tone: str = TONE_PLAIN
    burn_tone: str = TONE_PLAIN


def history_rows(history, rows: int = HISTORY_ROWS) -> tuple[HistoryRow, ...]:
    """The last laps, newest last, as the rack draws them.

    **A lap with no verdict keeps its row and says why** - a pit lap, an out
    lap, an incident lap. Dropping them would leave a rack whose lap numbers
    skip, and the gaps are where most of a race's time goes.
    """
    from pitcrew.race.targets import ON_TARGET_L, ON_TARGET_S

    drawn = []
    for lap in list(history or ())[-rows:]:
        delta, burn_delta = lap.get("lap_delta_s"), lap.get("burn_delta_l")
        saving = lap.get("saving")
        note = lap.get("why") or ("save" if saving else
                                  "full" if saving is False else "")
        if lap.get("pit"):
            note = "pit lap"
        elif lap.get("out"):
            note = "out lap"
        used = lap.get("burn_l")
        # **The litres AND what they were against.** Coloured alone, a 7.04
        # in green beside a 5.37 in amber reads as a judgement on the figure
        # rather than on its distance from the lap's own target.
        burn = ("" if used is None else f"{used:.2f}" +
                ("" if burn_delta is None else f"  {burn_delta:+.2f}"))
        drawn.append(HistoryRow(
            lap=str(lap.get("lap") or "--"),
            time=format_lap_ms(lap.get("lap_ms")),
            delta="" if delta is None else format_delta(delta),
            burn=burn,
            note=note,
            delta_tone=(TONE_PLAIN if delta is None else
                        TONE_URGENT if delta >= ON_TARGET_S else TONE_GOOD),
            burn_tone=(TONE_PLAIN if burn_delta is None else
                       TONE_URGENT if burn_delta >= ON_TARGET_L else TONE_GOOD),
        ))
    return tuple(drawn)


def history_summary(history) -> str:
    """One line under the rack: the laps that counted, the best, the burns.

    **Per beep column, and each with its lap count** (rule 4): the two columns
    are two burns 30% apart, and one average over both is the figure that put
    six litres in the car at Sardegna.
    """
    laps = [lap for lap in list(history or ()) if lap.get("lap_ms")]
    counted = [lap for lap in laps if lap.get("lap_delta_s") is not None]
    parts = [f"{len(laps)} laps"]
    if counted:
        best = min(lap["lap_ms"] for lap in counted)
        parts.append(f"best {format_lap_ms(best)}")
    for saving, word in ((True, "save"), (False, "full")):
        burns = [lap["burn_l"] for lap in laps
                 if lap.get("saving") is saving and lap.get("burn_l")]
        if burns:
            parts.append(f"{word} {sum(burns) / len(burns):.2f} L/lap "
                         f"over {len(burns)}")
    return "  ·  ".join(parts)


def target_note(state: "DriverState") -> str:
    """What the lap in progress is asked for, or why it is asked for nothing.

    **The burn target is not here, it is under the burn figure.** The note
    carries the lap references too and `_NoteLine` is bounded at 1,040 px: at
    the rig's faces a fourth clause elided the best on file off the end, and
    that reference is what stops "vs target" and "time diff" being read as
    the same claim (rule 13).
    """
    if state.target_lap_ms is not None:
        saving = " saving" if state.target_saving else ""
        return f"target{saving} {format_lap_ms(state.target_lap_ms)}"
    return state.target_why or ""


def lap_reference_note(state: "DriverState") -> str:
    """What the diff is against, named - rule 13: a delta that does not say
    what it is against is two numbers pretending to be one."""
    parts = []
    tyre = f"{state.reference_compound} " if state.reference_compound else ""
    if state.session_best_ms is not None:
        parts.append(f"vs {tyre}session best "
                     f"{format_lap_ms(state.session_best_ms)}")
    elif state.delta_why:
        parts.append(f"{tyre}{state.delta_why}" if tyre else state.delta_why)
    if state.file_best_ms is not None:
        on_file = f"{tyre}on file {format_lap_ms(state.file_best_ms)}"
        if state.delta_file_s is not None:
            on_file += f" ({format_delta(state.delta_file_s)})"
        parts.append(on_file)
    return "  ·  ".join(parts)


def fuel_flag_block(state: "DriverState") -> Block:
    """IN HAND TO THE FLAG, with the supply it rests on named.

    **The reference first, then the burn.** The reference is the half that
    has to survive a cut, because it is what says whether the figure is his
    to move; the burn is what lets him check it. The order is the whole
    design here - `set_sub_width` elides from the right, so on a face wide
    enough to need eliding it is the litres that go, not the words.

    The burn was taken off this line entirely for a while, on the arithmetic
    that `on the plan's fill · 4.19 L/lap` wanted thirty-one characters
    against a twenty-one character bound. That was measured on the OFFSCREEN
    test font at 27 px a character. On the rig the face is 16 px a character
    and the whole string is 496 px against a 640 px bound - it fits with room
    to spare, and it was removed for a reason that was not true.
    """
    if state.fuel_to_flag is None:
        # **A dash gets a REASON, never the reference or the burn.**
        # `on the plan's fill · 4.19 L/lap` under a dash says what the figure
        # would have rested on, which is not why there isn't one - and "every
        # dash on this board says why" is the rule the whole panel is built
        # on. `fuel_in_hand_to_flag` always returns a `why` beside a None, so
        # this fallback is the belt.
        return Block("--", state.fuel_to_flag_why or "not measured")
    rests_on = state.fuel_to_flag_on or ""
    if state.burn_l is not None:
        burn = f"{state.burn_l:.2f} L/lap"
        rests_on = f"{rests_on} · {burn}" if rests_on else burn
    return Block(f"{state.fuel_to_flag:.1f}", rests_on,
                 _tone(state.fuel_to_flag < 0))


def position_block(state: "DriverState") -> Block:
    """POSITION: `P6` over `of 12`, or a dash - P0 is not a place anyone
    finished in. `RaceState.position` is None until the first packet is
    decoded and after a read the locator refused."""
    if state.position is None:
        return Block("--", "not read yet")
    # `P6` and `of 12` rather than the spoken `position_line`'s "P6 of 12." -
    # the same two numbers, laid out for an eye instead of an ear.
    return Block(f"P{state.position}",
                 f"of {state.field_size}" if state.field_size else "")


def format_sector_ms(ms: int | None) -> str:
    """`38.412`, or `1:02.345` for a sector past a minute, or a dash."""
    if ms is None or ms <= 0:
        return "--.---"
    if ms >= 60_000:
        return format_lap_ms(ms)
    return f"{ms / 1000:.3f}"


def sector_blocks(state: "DriverState") -> tuple[tuple, str]:
    """The three sector boxes and the line under them.

    **Green "best" when this lap set that sector's session best; otherwise the
    difference to it, amber when slower** - the same colours TIME DIFF uses, so
    the lap panel speaks one language (his choice, 15 Sep 2026). A difference
    that is negative without being a best is a lap that does not count - an
    out-lap - running under a counted best, and it is shown as it is.

    **The reason for dashes goes on the line, not under S1**, where a box's
    reason would be elided and read as belonging to that sector alone.
    """
    view = state.sectors
    dashes = tuple(Block(format_sector_ms(None)) for _ in range(3))
    if view is None:
        return dashes, ""
    if view.times_ms is None:
        parts = [view.why or "no sector times"]
        if view.cut:
            parts.append(f"sectors {view.cut}")
        return dashes, "  ·  ".join(parts)
    blocks = []
    for ms, best, mine in zip(view.times_ms, view.best_ms, view.set_best):
        value = format_sector_ms(ms)
        if mine:
            blocks.append(Block(value, "best", TONE_GOOD))
        elif best is None:
            blocks.append(Block(value))
        else:
            diff = (ms - best) / 1000.0
            blocks.append(Block(value, f"{diff:+.3f}",
                                TONE_URGENT if diff > 0
                                else TONE_GOOD if diff < 0 else TONE_PLAIN))
    parts = ["last lap"]
    if view.compound and any(best is not None for best in view.best_ms):
        parts.append(f"vs {view.compound} session bests")
    if view.cut:
        parts.append(f"sectors {view.cut}")
    return tuple(blocks), "  ·  ".join(parts)


class _Box(QWidget):
    """A framed title-over-value box, as on the driver's reference image."""

    def __init__(self, title: str, value_px: int,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("box")
        # A plain QWidget paints no stylesheet background or border without
        # this, so the frame and the panel face were silently not drawn.
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(
            f"#box {{ border:2px solid {EDGE}; border-radius:10px;"
            f" background:{PANEL}; }}")
        column = QVBoxLayout(self)
        column.setContentsMargins(22, 6, 22, 10)
        column.setSpacing(0)
        self.title = QLabel(title.upper())
        self.title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title.setStyleSheet(
            f"font-family:{LABEL_FACE};font-size:21px;font-weight:600;"
            f"letter-spacing:5px;color:{INK_DIM};background:transparent;")
        self.value = QLabel("--")
        self.value.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._value_px = value_px
        self.set_value("--", INK)
        column.addWidget(self.title)
        column.addWidget(self.value)

    def set_value(self, text: str, ink: str) -> None:
        self.value.setText(text)
        self.value.setStyleSheet(
            f"font-family:{NUMBER_FACE};font-size:{self._value_px}px;"
            f"font-weight:600;color:{ink};background:transparent;")


class _NoteLine(QLabel):
    """The dim line under a panel, bounded in width and elided past it.

    **A panel's width must not be a property of its reason string.** Sardegna
    practice, 15 Sep 2026: a lap with no sector times put the analysis's own
    diagnostic under S1/S2/S3 - "the car jumped 167 m in one frame (2x) - a
    reset or a garage return, so every distance after it is against a
    different axis..." - and the board's minimum went to 2,702 px on his
    2,560 panel, twice in one evening. The same lesson `_Stat.set_sub_width`
    records for the sub-lines, one panel over. The whole sentence stays on
    the tooltip; the board carries what fits.
    """

    # The widest ordinary note - "last lap · vs RH session bests · sectors at
    # the circuit's timing lines" - needs about 1,000 px on the rig's faces.
    MAX_W = 1040

    def __init__(self) -> None:
        super().__init__("")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet(
            f"font-family:{NUMBER_FACE};font-size:24px;color:{INK_DIM};"
            f"background:transparent;")
        self.setMaximumWidth(self.MAX_W)
        self._full = ""

    def set_note(self, text: str) -> None:
        from PyQt6.QtGui import QFontMetrics

        if text == self._full and self.text():
            return
        self._full = text
        self.ensurePolished()
        self.setText(QFontMetrics(self.font()).elidedText(
            text, Qt.TextElideMode.ElideRight, self.MAX_W - 8))
        self.setToolTip(text if self.text() != text else "")

    def full_text(self) -> str:
        return self._full


class _LapTimePanel(QWidget):
    """Laptime | Time Diff | Pred. Time, and what the diff is against.

    The driver's own layout (reference image, 14 Sep 2026). **Two references,
    both named**: the big diff is against this session's best lap, and the
    line under the panel carries the best lap on file for this car, circuit
    and game version - a different setup or day, so it is the second line and
    not the lead (rule 13: a delta that does not say what it is against is two
    numbers pretending to be one).
    """

    def __init__(self, value_px: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        column = QVBoxLayout(self)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(6)
        row = QHBoxLayout()
        row.setSpacing(14)
        self.lap = _Box("laptime", value_px)
        self.diff = _Box("time diff", value_px)
        self.pred = _Box("pred. time", value_px)
        # **The plan's targets, race only** (the driver, 16 Sep 2026): the
        # last lap against the time the plan asked of it, with the burn
        # against its own under it. In this panel rather than the fuel blocks
        # because both are about ONE lap, and the fuel blocks' reason lines
        # are at their width already.
        #
        # **In the predicted time's place, not beside it.** Two more boxes
        # measured the race board at 4,014 px against the 3,400 ceiling
        # (`test_the_board_does_not_grow_in_the_widest_state_it_can_be_given`),
        # and the row "has no room for a third panel" already. In a race the
        # number he is driving to is the plan's, so the prediction against the
        # session best gives way; practice and qualifying keep it.
        self.vs_target = _Box("vs target", value_px)
        self.burn = QLabel("")
        self.burn.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.vs_target.layout().addWidget(self.burn)
        for box in (self.lap, self.diff, self.pred, self.vs_target):
            row.addWidget(box)
        column.addLayout(row)
        self.note = _NoteLine()
        column.addWidget(self.note, 0, Qt.AlignmentFlag.AlignHCenter)
        self._sub_px = max(20, value_px // 2)

    def show_state(self, state: "DriverState") -> None:
        self.lap.set_value(format_lap_ms(state.lap_time_ms), INK)
        delta = state.delta_s
        ink = INK if delta is None else GOOD if delta < 0 else NEAR if delta > 0 else INK
        self.diff.set_value(format_delta(delta), ink)
        self.pred.set_value(format_lap_ms(state.predicted_ms), INK)
        racing = state.session_kind == "race"
        self.vs_target.setVisible(racing)
        self.pred.setVisible(not racing)
        note = lap_reference_note(state)
        if racing:
            inks = {TONE_GOOD: GOOD, TONE_URGENT: NEAR, TONE_PLAIN: INK_DIM}
            pace, burn = target_pace_block(state), target_burn_block(state)
            self.vs_target.set_value(pace.value, inks[pace.tone])
            # The burn against its own target, with the target beside it -
            # the one place the figure he is being judged on is drawn.
            against = ("" if state.target_burn_l is None
                       else f" of {state.target_burn_l:.2f}")
            self.burn.setText(f"burn {burn.value}{against}")
            self.burn.setStyleSheet(
                f"font-family:{NUMBER_FACE};font-size:{self._sub_px}px;"
                f"color:{inks[burn.tone]};background:transparent;")
            # The target this lap is asked for leads the line: it is the
            # number he is driving to, and the references are the record.
            target = pace.sub
            note = "  ·  ".join(part for part in (target, note) if part)
        self.note.set_note(note)


class _SectorPanel(QWidget):
    """Last lap S1 | S2 | S3, each against this session's best of it.

    Framed boxes like the lap panel beside it, with the difference under each
    value and one line naming the lap, the tyre and where the lines came from -
    GT7 sends no sectors, so a split is the app's own claim and the board says
    whose (`analysis/lap_sectors.py`).
    """

    def __init__(self, value_px: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        column = QVBoxLayout(self)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(6)
        row = QHBoxLayout()
        row.setSpacing(14)
        self.boxes = []
        self.subs = []
        for name in ("s1", "s2", "s3"):
            box = _Box(name, value_px)
            sub = QLabel("")
            sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
            box.layout().addWidget(sub)
            self.boxes.append(box)
            self.subs.append(sub)
            row.addWidget(box)
        column.addLayout(row)
        self.note = _NoteLine()
        column.addWidget(self.note, 0, Qt.AlignmentFlag.AlignHCenter)

    def show_state(self, state: "DriverState") -> None:
        blocks, note = sector_blocks(state)
        for box, sub, block in zip(self.boxes, self.subs, blocks):
            ink = GOOD if block.good else NEAR if block.urgent else INK_DIM
            box.set_value(block.value, GOOD if block.sub == "best" else INK)
            sub.setText(block.sub)
            sub.setStyleSheet(
                f"font-family:{NUMBER_FACE};font-size:26px;color:{ink};"
                f"background:transparent;")
        self.note.set_note(note)


class _Light(_Face):
    """A box that lights: a word, its ink, and one line under it.

    The fill is painted by `_Face`, so a lamp lighting wipes down rather than
    blinking on - and a lit lamp still never draws its dark word on the dark
    ground, which was the first render's fault when the fill was a styled
    background that was not being painted at all.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("light")
        column = QVBoxLayout(self)
        column.setContentsMargins(18, 6, 18, 8)
        column.setSpacing(0)
        self.word = QLabel("--")
        self.word.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.sub = QLabel("")
        self.sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        column.addWidget(self.word)
        column.addWidget(self.sub)
        self.lit = False
        self.show_light("--", "", None)

    def show_light(self, word: str, sub: str, ink: str | None) -> None:
        """`ink` None is unlit: the word dim on the panel face. Lit fills the
        box with the ink and draws the word dark, so it reads as a lamp."""
        self.lit = ink is not None
        fill = ink if self.lit else PANEL
        border = ink if self.lit else EDGE
        self.set_face(fill, border)
        self.word.setText(word.upper())
        self.sub.setText(sub)
        self._reink()

    def _wiped(self) -> None:
        self._reink()

    def _reink(self) -> None:
        """Dark on a lit fill, dim on the panel - whichever is behind the
        word now, which during a wipe is not yet the one asked for."""
        word_ink = INK_DIM if self.fill_showing() in (None, PANEL) else GROUND
        if word_ink == getattr(self, "_word_ink", None):
            return
        self._word_ink = word_ink
        self.word.setStyleSheet(
            f"font-family:{LABEL_FACE};font-size:44px;font-weight:700;"
            f"letter-spacing:6px;color:{word_ink};background:transparent;")
        self.sub.setStyleSheet(
            f"font-family:{NUMBER_FACE};font-size:20px;"
            f"color:{word_ink};background:transparent;")


def wet_light(wet: str | None) -> tuple[str, str, str | None]:
    """(word, sub, ink) for the WET box. Never says dry without a reading."""
    if wet == "wet":
        return "wet", "water under the car", theme.WET_LIGHT
    if wet == "mixed":
        return "wet", "patchy", NEAR
    if wet == "dry":
        return "dry", "hygrometer", None
    return "wet", "cannot see", None


def abs_light(setting: str | None, front_lock: bool | None) -> tuple[str, str, str | None]:
    """(word, sub, ink) for the ABS box. GT7 sends no ABS signal: the box names
    the event's setting and lights LOCK on a front lock, which is derived.
    `front_lock` None is no telemetry to read one off - said, never "no lock"."""
    named = f"abs {setting.lower()}" if setting else "abs setting unknown"
    word = f"abs {setting}" if setting else "abs"
    if front_lock is None:
        return word, "no reading", None
    if front_lock:
        return "lock", f"{named} · derived", OVER
    return word, "no lock", None


def tcs_light(active: bool | None) -> tuple[str, str, str | None]:
    """(word, sub, ink) for the TCS box, off flags_raw bit 11."""
    if active is None:
        return "tcs", "no signal", None
    if active:
        return "tcs", "cutting in", NEAR
    return "tcs", "", None


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
        # **And a width bound on top of the height one.** Qt's word wrap does
        # not break a token longer than the line, so `heightForWidth` reports
        # a single line for a 200-character word and the bisection accepts the
        # lot - 6,060 px of it inside a 1,560 px label, clipped with no
        # ellipsis. Nothing the engineer says today looks like that; this is
        # the last hole in the fit and it costs one call to close.
        self.line.setText(metrics.elidedText(
            best, Qt.TextElideMode.ElideRight, self.MAX_WIDTH * self.LINES))

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
        # `test_the_board_fits_his_monitor_on_the_faces_he_actually_has`
        # measures the real faces in a subprocess and holds 2560 x 1080; its
        # offscreen sibling sweeps every refusal string, a sixteen-character
        # rival name, the box page and a call three times longer than any the
        # engineer makes, and holds a growth ceiling. This opens above the
        # real-face minimum, and Qt grows it where a state needs more. It is not a free choice
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
        # A belt for the next transient nobody has found: a layout that grows
        # the window for one call leaves it grown, so it is measured back
        # onto the monitor after every state. Returns at once when it fits.
        self.keep_on_screen()

    # -- dragging, because a frameless window has no title bar to grab -------

    def mousePressEvent(self, event) -> None:      # noqa: N802 - Qt naming
        self._drag_from = (event.globalPosition().toPoint()
                           - self.frameGeometry().topLeft())

    def mouseMoveEvent(self, event) -> None:       # noqa: N802 - Qt naming
        if self._drag_from is not None:
            self.move(event.globalPosition().toPoint() - self._drag_from)

    def mouseReleaseEvent(self, event) -> None:    # noqa: N802 - Qt naming
        self._drag_from = None

    # -- never bigger than the monitor it is on ------------------------------

    def showEvent(self, event) -> None:            # noqa: N802 - Qt naming
        super().showEvent(event)
        self.keep_on_screen()

    def resizeEvent(self, event) -> None:          # noqa: N802 - Qt naming
        super().resizeEvent(event)
        self.keep_on_screen()

    def keep_on_screen(self) -> None:
        """Shrink the window to the screen it is mostly on. Never move it.

        **Rd 9, 15 Sep 2026: the board was 2716 px wide on a 2560 panel.** Qt
        grows a frameless window to any layout minimum bigger than it, never
        shrinks it back, and `geometry_text` wrote the grown size away at every
        race's end, so one wide moment came back at every race after. So the
        SIZE is an answer to the monitor, not a memory.

        **The PLACE is his, and it was taken from him once.** The first version
        of this also pulled the window wholly onto the screen - after every
        drag and four times a second from `update_state`. The main app sits
        maximised on the same monitor behind this always-on-top board, and he
        reaches it by dragging the board partly off the edge (his saved spot
        was y=237, bottom 212 px off-screen). Clamped back every tick, the
        board could not be moved at all and he had to quit the app to get
        past it (15 Sep 2026, the same evening). A window that is lost off
        every screen is `restore_geometry`'s to refuse, not this method's.

        What Qt will not allow - content whose minimum exceeds the screen - is
        logged with its size, because that is a board with a number missing.
        """
        if getattr(self, "_placing", False):
            return
        screen = _screen_for(self.geometry())
        if screen is None:
            return
        bounds = screen.geometry()
        rect = self.geometry()
        x, y, width, height = fit_on_screen(
            (rect.x(), rect.y(), rect.width(), rect.height()),
            (bounds.x(), bounds.y(), bounds.width(), bounds.height()))
        need = self.minimumSizeHint()
        if need.width() > bounds.width() or need.height() > bounds.height():
            key = (need.width(), need.height())
            if key != getattr(self, "_overflow_logged", None):
                self._overflow_logged = key
                log("ui").warning(
                    "the driver board needs %dx%d and its screen is %dx%d - "
                    "part of it is off the monitor", need.width(),
                    need.height(), bounds.width(), bounds.height())
        if (width, height) == (rect.width(), rect.height()):
            return
        self._placing = True
        try:
            # `resize`, not `setGeometry`: the top-left stays where he put it.
            self.resize(width, height)
        finally:
            self._placing = False

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
        self.keep_on_screen()
        return True


def fit_on_screen(rect: tuple[int, int, int, int],
                  bounds: tuple[int, int, int, int]
                  ) -> tuple[int, int, int, int]:
    """`(x, y, w, h)` no bigger than `bounds`, **left where it was**.

    Only the size is fitted. Where the window sits is his - partly off the
    edge is how he gets to the app behind it (see `keep_on_screen`).

    Pure, so the rule is testable without a monitor: the offscreen platform
    the suite runs on has one 800x600 screen and a board far wider than it.
    """
    x, y, width, height = rect
    _, _, bw, bh = bounds
    return x, y, min(width, bw), min(height, bh)


def _screen_for(rect):
    """The screen holding most of `rect`, or the primary where none does."""
    app = QApplication.instance()
    if app is None:
        return None
    best, area = None, 0
    for screen in app.screens():
        overlap = screen.geometry().intersected(rect)
        size = overlap.width() * overlap.height() if not overlap.isEmpty() else 0
        if size > area:
            best, area = screen, size
    return best or app.primaryScreen()


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
        # The countdown he is holding the trigger on - urgent from ten
        # seconds, and the one figure on this page that is an instruction.
        self.release_stat.set_flood()
        outer.addLayout(row)

    def show_state(self, state: DriverState) -> None:
        # The countdown's words and urgency are `release_block`'s, shared
        # with the strip page so the two cannot count differently.
        release = release_block(state)
        self.release_stat.show_value(release.value, release.sub,
                                     urgent=release.urgent)

        fuel = fuel_target_block(state)
        self.fuel_stat.show_value(fuel.value, fuel.sub)
        tyres = tyres_block(state)
        self.tyre_stat.show_value(tyres.value, tyres.sub)

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


class _HistoryPanel(QWidget):
    """The race so far, a lap a row - the monitor's page.

    Built once and filled on each state: twelve rows of five labels is
    nothing to re-text at 4 Hz, and rebuilding widgets under a driver's eye
    is how a row comes to show one lap's time beside another's burn.
    """

    COLUMNS = ("LAP", "TIME", "VS PLAN", "BURN  VS PLAN", "")

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        column = QVBoxLayout(self)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(8)
        self.caption = QLabel("THE RACE SO FAR")
        self.caption.setStyleSheet(
            f"font-family:{LABEL_FACE};font-size:26px;font-weight:600;"
            f"letter-spacing:7px;color:{INK_DIM};background:transparent;")
        column.addWidget(self.caption)
        grid = QGridLayout()
        grid.setHorizontalSpacing(46)
        grid.setVerticalSpacing(4)
        for index, head in enumerate(self.COLUMNS):
            label = QLabel(head)
            label.setStyleSheet(
                f"font-family:{LABEL_FACE};font-size:22px;font-weight:600;"
                f"letter-spacing:5px;color:{INK_DIM};background:transparent;")
            grid.addWidget(label, 0, index)
        self.cells = []
        for row in range(HISTORY_ROWS):
            line = []
            for index in range(len(self.COLUMNS)):
                label = QLabel("")
                label.setStyleSheet(self._css(INK, 34))
                grid.addWidget(label, row + 1, index)
                line.append(label)
            self.cells.append(line)
        column.addLayout(grid)
        self.summary = QLabel("")
        self.summary.setStyleSheet(self._css(INK_DIM, 26))
        column.addWidget(self.summary)

    @staticmethod
    def _css(ink: str, size: int) -> str:
        return (f"font-family:{NUMBER_FACE};font-size:{size}px;"
                f"color:{ink};background:transparent;")

    def show_state(self, state: "DriverState") -> None:
        rows = history_rows(state.history)
        for index, line in enumerate(self.cells):
            row = rows[index] if index < len(rows) else None
            values = (("", "", "", "", "") if row is None else
                      (row.lap, row.time, row.delta, row.burn, row.note))
            inks = (INK, INK,
                    NEAR if (row and row.delta_tone == TONE_URGENT) else
                    GOOD if (row and row.delta_tone == TONE_GOOD) else INK,
                    NEAR if (row and row.burn_tone == TONE_URGENT) else
                    GOOD if (row and row.burn_tone == TONE_GOOD) else INK,
                    INK_DIM)
            for label, value, ink in zip(line, values, inks):
                label.setText(value)
                label.setStyleSheet(self._css(ink, 26 if value is values[-1]
                                              else 34))
        self.summary.setText(history_summary(state.history))


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

        # **"to the stop", as every other surface says it** (rule 13). The
        # voice says "N laps to the stop", the fuel block one along is "in
        # hand to the stop", and this one was the only place the same count
        # was captioned "laps to box". "Box this lap" stays the instruction
        # it turns into at zero; the caption names the distance.
        self.box_stat = _Stat("laps to the stop")
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

        # **Three lights where the tyre splits were** (the driver, 14 Sep 2026:
        # "drop it, would prefer wet, ABS and TCS indicator boxes that light
        # up"). Stacked beside the corner grid, which is the room the splits
        # occupied, so the board's height does not grow.
        self.wet_light = _Light()
        self.abs_light = _Light()
        self.tcs_light = _Light()
        light_block = QWidget()
        light_column = QVBoxLayout(light_block)
        light_column.setContentsMargins(0, 0, 0, 0)
        light_column.setSpacing(10)
        light_column.addStretch(1)
        for light in (self.wet_light, self.abs_light, self.tcs_light):
            light.setMinimumWidth(300)
            light_column.addWidget(light)
        light_column.addStretch(1)

        # **The lap-time panel, twice, and only one is ever shown.** In a race
        # it sits beside the corners and the gaps keep the bottom edge; in
        # practice and qualifying there are no gaps and it takes the bottom
        # rank itself (his choice, 14 Sep 2026). Two instances fed the same
        # state rather than one widget re-parented on every update.
        self.lap_panel_top = _LapTimePanel(value_px=58)
        self.lap_panel_lead = _LapTimePanel(value_px=120)
        # The race page for when the phone strip is reading: the lap panel at
        # the middle rank, above the fuel and position leading.
        self.lap_panel_mid = _LapTimePanel(value_px=96)
        # Last lap S1 / S2 / S3, beside the lights (15 Sep 2026).
        self.sector_panel = _SectorPanel(value_px=58)
        # **The phone page's lead rank.** Separate instances from the middle
        # rank's, fed the same blocks - a widget re-parented on every update
        # is the thing this file already refused once for the lap panel.
        self.stop_lead = _Stat("in hand to the stop", value_px=_Stat.GAP_PX)
        self.flag_lead = _Stat("in hand to the flag", value_px=_Stat.GAP_PX)
        self.position_lead = _Stat("position", value_px=_Stat.GAP_PX)

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
            stat.set_flood()
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
        light_block.setSizePolicy(QSizePolicy.Policy.Maximum,
                                  QSizePolicy.Policy.Preferred)
        self.lap_panel_top.setSizePolicy(QSizePolicy.Policy.Maximum,
                                         QSizePolicy.Policy.Preferred)
        centred = QHBoxLayout()
        centred.setSpacing(70)
        centred.addStretch(1)
        centred.addWidget(self.lap_panel_top, 0, Qt.AlignmentFlag.AlignVCenter)
        centred.addWidget(tyres)
        centred.addWidget(light_block)
        self.sector_panel.setSizePolicy(QSizePolicy.Policy.Maximum,
                                        QSizePolicy.Policy.Preferred)
        centred.addWidget(self.sector_panel, 0, Qt.AlignmentFlag.AlignVCenter)
        centred.addStretch(1)
        stacked.addLayout(centred)

        self.middle_row = QWidget()
        self.middle_row.setLayout(middle)
        self.leading = QWidget()
        self.leading.setLayout(lead)

        # **The ranks below the corners are swapped whole, never hidden row by
        # row.** Hiding rows inside a layout that has not been shown leaves Qt's
        # cached minimum counting them, and the first render came out 1295 px
        # tall on a 1080 panel. A stack is as tall as its tallest page - the
        # race page - so the board is one height whatever the session.
        race_lower = QWidget()
        race_column = QVBoxLayout(race_lower)
        race_column.setContentsMargins(0, 0, 0, 0)
        race_column.setSpacing(12)
        race_column.addWidget(self.middle_row)
        race_column.addWidget(self.leading)

        self.leading_lap = QWidget()
        practice_column = QVBoxLayout(self.leading_lap)
        practice_column.setContentsMargins(0, 0, 0, 0)
        # Bottom-anchored like everything else here: the panel sits on the
        # edge nearest his eye, with the page's spare height above it.
        practice_column.addStretch(1)
        lead_lap = QHBoxLayout()
        lead_lap.addStretch(1)
        lead_lap.addWidget(self.lap_panel_lead)
        lead_lap.addStretch(1)
        practice_column.addLayout(lead_lap)

        # **The phone page.** The gaps and laps to the stop are on his phone,
        # so the numbers he plans with take the edge nearest his eye at the
        # lead size, and the lap panel sits above them.
        self.race_phone = QWidget()
        phone_column = QVBoxLayout(self.race_phone)
        phone_column.setContentsMargins(0, 0, 0, 0)
        phone_column.setSpacing(12)
        phone_column.addStretch(1)
        mid_lap = QHBoxLayout()
        mid_lap.addStretch(1)
        mid_lap.addWidget(self.lap_panel_mid)
        mid_lap.addStretch(1)
        phone_column.addLayout(mid_lap)
        phone_lead = QHBoxLayout()
        phone_lead.setSpacing(70)
        for stat in (self.stop_lead, self.flag_lead, self.position_lead):
            stat.set_sub_width(_Stat.MIDDLE_SUB_W)
            stat.set_flood()
            phone_lead.addStretch(1)
            phone_lead.addWidget(stat, 0, Qt.AlignmentFlag.AlignBottom)
        phone_lead.addStretch(1)
        phone_column.addLayout(phone_lead)

        self.lower = QStackedLayout()
        self.lower.addWidget(race_lower)
        self.lower.addWidget(self.leading_lap)
        self.lower.addWidget(self.race_phone)
        self._race_lower = race_lower
        stacked.addLayout(self.lower)

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

        # **The history page, and why it is a page rather than a screen.**
        # With his car on the phone and the field on the tablet, this monitor
        # is the one he looks at least - so it carries the race behind him.
        # The moment either of those screens drops, this board is his live pit
        # board again: a page in the same stack cannot be out of date, and
        # cannot be missing when it is needed.
        self.history = _HistoryPanel()
        self.history.setSizePolicy(QSizePolicy.Policy.Preferred,
                                   QSizePolicy.Policy.Maximum)

        self.states = QStackedLayout()
        self.states.addWidget(self.running)
        self.states.addWidget(self.box)
        self.states.addWidget(self.history)
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
        block = gap_block(gap)
        stat.show_value(block.value, block.sub,
                        urgent=block.urgent, good=block.good)

    def update_state(self, state: DriverState) -> None:
        # The box always wins: a stop is happening, whatever is on the phone.
        page = (self.box if state.in_box else
                self.history if state.show_history else self.running)
        self.states.setCurrentWidget(page)
        if state.in_box:
            self.box.show_state(state)
        elif state.show_history:
            self.history.show_state(state)
        temps = state.temps_c or {}
        for corner, widget in self.tyres.items():
            kind, lopsided = classify(corner, temps, state.compound)
            widget.show_value(temps.get(corner), kind, lopsided,
                              pair_gap(corner, temps),
                              (state.split_rates or {}).get(corner))
        # **Say when there is no threshold at all.** With no compound
        # `onset_for` is None, `classify` returns "cool", and the four
        # numbers paint in the same white a measured-below-onset reading
        # gets - so 96 degC on an unknown set draws exactly like 60, and this
        # file's own docstring says that white claims "not yet wearing faster
        # for heat". It cannot claim that with nothing to compare against.
        # `_apply_stint(over_a_stop=True)` clears `tyre_compound` whenever
        # the stint the stop starts names none, so it is reachable, and a
        # plan naming no compounds leaves it None all race.
        self.tyre_caption.setText(
            f"TYRE SURFACE °C · {state.compound.upper()}" if state.compound
            else "TYRE SURFACE °C · COMPOUND UNKNOWN, NO WEAR LINE")
        self._show_session_kind(state)
        self.lap_panel_top.show_state(state)
        self.lap_panel_lead.show_state(state)
        self.lap_panel_mid.show_state(state)
        self.sector_panel.show_state(state)
        self.wet_light.show_light(*wet_light(state.wet))
        self.abs_light.show_light(*abs_light(state.abs_setting, state.front_lock))
        self.tcs_light.show_light(*tcs_light(state.tcs_active))
        self.last_call.show_call(state.last_call)

        # The words are `box_block`'s, shared with the strip page.
        box = box_block(state)
        self.box_stat.show_value(box.value, box.sub, urgent=box.urgent,
                                 act=state.laps_past_box is not None
                                 and not state.finished)

        self._show_gap(self.ahead_stat, state.ahead)
        self._show_gap(self.behind_stat, state.behind)
        self._show_fuel(state)
        self._relayout_if_the_page_changed()

    def _relayout_if_the_page_changed(self) -> None:
        """Re-measure everything once whenever a different page is showing.

        **A label whose text changes while its page is hidden keeps the size
        it had when it was last shown.** `QWidget.updateGeometry` does nothing
        for a hidden widget, so the layouts above it hold a stale size hint -
        and when the page comes back Qt lays it out from that. Measured on the
        rig's fonts, 15 Sep 2026: the lap panel beside the corners came back
        at 199 px against a 272 px `1:11.412` and drew `:11.41`. It happened
        going from practice to a race in one app run before the phone strip
        existed; the strip made it a mid-race event, because the phone
        dropping swaps the race pages. So on any page or panel change the
        whole view is invalidated once - not every tick, which would reflow
        the board four times a second.
        """
        shown = (self.states.currentWidget(), self.lower.currentWidget(),
                 self.lap_panel_top.isHidden(), self.sector_panel.isHidden())
        if shown == getattr(self, "_shown_pages", None):
            return
        self._shown_pages = shown
        for widget in (self, *self.findChildren(QWidget)):
            if widget.layout() is not None:
                widget.layout().invalidate()
            widget.updateGeometry()

    # Kept as names on the view for the tests that reach for them; the
    # expressions are the module's `tyre_clause` and `box_caption`.
    _tyre_clause = staticmethod(tyre_clause)
    _box_caption = staticmethod(box_caption)

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
        # Both race pages carry these three - the gap-led page at the middle
        # rank and the phone page at the lead - from one expression each.
        stop, flag, where = (fuel_stop_block(state), fuel_flag_block(state),
                             position_block(state))
        for stat, block in ((self.stop_stat, stop), (self.stop_lead, stop),
                            (self.flag_stat, flag), (self.flag_lead, flag),
                            (self.position_stat, where),
                            (self.position_lead, where)):
            stat.show_value(block.value, block.sub, urgent=block.urgent)

    def _show_session_kind(self, state: DriverState) -> None:
        """Race: the gaps lead and the lap panel sits by the corners. Practice
        and qualifying: the race-only rows are hidden and the lap panel leads.

        Hidden rather than dashed: a practice board of five dashes saying "no
        plan" and "no gap read" is five things to read that can never change.
        """
        racing = state.session_kind == "race"
        # **The phone page only while a phone is actually reading**
        # (`DriverState.strip_live`) - the gaps and laps to the stop are on
        # it, so this board promotes the fuel and position to the lead. The
        # moment it stops polling the whole gap-led page comes back: swapped
        # whole, never a row hidden, per the note where the pages are built.
        on_phone = racing and state.strip_live
        self.lower.setCurrentWidget(
            self.race_phone if on_phone
            else self._race_lower if racing else self.leading_lap)
        # Width only: both panels share the corners' row, whose height the
        # corner grid sets, so hiding one cannot move the board's height.
        # The gap-led page is today's board exactly, and its row has no room
        # for a third panel beside the lap panel - so the sectors are on the
        # phone page and in practice, not on the fallback.
        #
        # **Hide first, then show - the order is the fix, not a style.** Shown
        # first, both panels stood in the row together for one call: the
        # minimum went to 2,730 px, Qt grew the window to it on the spot, and
        # a window is never shrunk back. Every time the phone dropped the
        # board became wider than his monitor, and `geometry_text` saved the
        # width at the flag - Rd 9 closed at 2,716 (15 Sep 2026).
        top = racing and not on_phone
        hide, show = ((self.sector_panel, self.lap_panel_top) if top
                      else (self.lap_panel_top, self.sector_panel))
        hide.setVisible(False)
        show.setVisible(True)
