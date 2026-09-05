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
be ripped out (`store/tyres.py`). Measured here on 277 clean laps, minimum
corner speed against tyre temperature has slopes of the OPPOSITE SIGN at Monza
and Spa with R^2 under 0.2 - because temperature is endogenous. It is a
consequence of how hard the tyre is being worked, not an input to grip. More
laps cannot fix that; it needs temperature varied independently of driving.

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
    laps_to_box: float | None = None
    box_on_lap: int | None = None
    laps_of_fuel: float | None = None
    fuel_l: float | None = None
    burn_l: float | None = None

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
    # Where the fill rate came from - "measured here" or "declared rate".
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
    grip, with slopes of opposite sign at Monza and Spa.

    The gaps do not have that problem. Measured across the archive, the
    rear-front and RR-RL splits are monotone and match the measured wear map
    at r=+0.82 - so of everything on this screen, this is the reading with
    evidence behind it.

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

    VALUE_PX = 104
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
    GAP_PX = 210

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
        self.sub.setText(sub)
        ink = NEAR if urgent else GOOD if good else INK
        if ink != self._ink:
            self._ink = ink
            self._restyle()
        self.sub.setStyleSheet(
            f"font-family:{NUMBER_FACE};font-size:{self.SUB_PX}px;"
            f"color:{ink if (urgent or good) else INK_DIM};"
            f"background:transparent;")


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
        self.resize(1280, 480)
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
            reason = ("no fill rate measured here" if state.fuel_target_l
                      else "nothing sized this stop")
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
            self.fuel_stat.show_value("--", "nothing sized this stop")
        else:
            parts = []
            if state.fuel_l is not None:
                parts.append(f"{state.fuel_l:.0f} aboard")
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
        if state.compound:
            self.tyre_stat.show_value(state.compound, "plan")
        elif state.has_plan:
            self.tyre_stat.show_value("--", "the plan names no compound")
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
            self.next_stat.show_value("FLAG", "this stint runs to the end")
        elif state.next_stint_laps is not None:
            self.next_stat.show_value(f"{state.next_stint_laps}",
                                      "laps, then box again")
        elif state.past_the_plan:
            # Out past the end of the stint list - an unplanned stop. NOT the
            # same as having no plan, and emphatically not "runs to the flag":
            # nothing has checked the fuel aboard against what is left.
            self.next_stat.show_value("--", "past the end of the plan")
        elif state.has_plan:
            # Inside the plan, on a stint whose length it does not state.
            # Sharing the caption above would have said he was past the end of
            # a plan he is squarely in the middle of.
            self.next_stat.show_value("--", "the plan states no length")
        else:
            self.next_stat.show_value("--", "no plan")


class DriverView(QWidget):
    """The whole instrument. `update_state` is the only thing to call."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setStyleSheet(f"background:{GROUND};")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(40, 20, 40, 34)
        # **Bottom-anchored.** He glances UP from the game screen below, so the
        # bottom edge of this display is the shortest eye travel.
        outer.addStretch(1)

        row = QHBoxLayout()
        row.setSpacing(70)

        self.box_stat = _Stat("laps to box")
        self.fuel_stat = _Stat("laps of fuel")
        # **At the ends, and in the order the cars are in.** Ahead on the
        # left, behind on the right, so which block is which needs no reading -
        # it is where the car is. That is what keeps this from being the
        # fourth and fifth items the docstring above warns about: they are one
        # paired mnemonic rather than two more things in a list.
        self.ahead_stat = _Stat("ahead", value_px=_Stat.GAP_PX)
        self.behind_stat = _Stat("behind", value_px=_Stat.GAP_PX)

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
        for stat in (self.ahead_stat, self.box_stat,
                     self.fuel_stat, self.behind_stat):
            row.addStretch(1)
            row.addWidget(stat, 0, Qt.AlignmentFlag.AlignBottom)
        row.addStretch(1)

        stacked = QVBoxLayout()
        stacked.setContentsMargins(0, 0, 0, 0)
        stacked.setSpacing(30)

        centred = QHBoxLayout()
        centred.addStretch(1)
        centred.addWidget(tyres)
        centred.addStretch(1)
        stacked.addLayout(centred)

        leading = QWidget()
        leading.setLayout(row)
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
                f"plan: lap {state.box_on_lap}" if state.box_on_lap else "",
                # **Urgent inside two laps**, which is where the number stops
                # being background and starts being a thing to act on.
                urgent=state.laps_to_box <= 2)

        self._show_gap(self.ahead_stat, state.ahead)
        self._show_gap(self.behind_stat, state.behind)

        if state.laps_of_fuel is None:
            self.fuel_stat.show_value("--", "not measured")
        else:
            parts = []
            if state.fuel_l is not None:
                parts.append(f"{state.fuel_l:.1f} L")
            if state.burn_l is not None:
                parts.append(f"{state.burn_l:.2f} L/lap")
            self.fuel_stat.show_value(
                f"{state.laps_of_fuel:.1f}", " · ".join(parts),
                urgent=state.laps_of_fuel <= 2.0)
