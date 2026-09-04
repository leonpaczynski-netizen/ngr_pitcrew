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

**Three items, and the layout is anchored to the bottom.** He is looking down
at the game and glancing up, so the bottom edge of this screen is the shortest
eye travel; content sits there rather than centred. A fourth item was
considered and left out: the cost of one more is that the first three stop
being findable.

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

**And it is fed a smoothed temperature, never a raw frame.** Per-lap peaks
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
    QStackedLayout,
    QVBoxLayout,
    QWidget,
)

# The one measured figure, from `store.tyres.WEAR_ONSET_C`. Imported rather
# than restated: two copies of a threshold drift, and this one is sourced.
from pitcrew.store.tyres import WEAR_ONSET_C

# How far below onset still counts as approaching it.
NEAR_ONSET_C = 5.0
# How far above the opposite tyre before a corner is called lopsided. Wide
# enough that ordinary front-to-rear bias does not trip it every lap.
PAIR_GAP_C = 10.0

GROUND = "#07090A"
PANEL = "#11161A"
EDGE = "#1E262C"
INK = "#EEF3F5"
INK_DIM = "#6C7C85"
COOL = "#7FA8C9"          # below onset - and that is the whole claim
NEAR = "#E0A03A"
OVER = "#E0523F"
LOPSIDED = "#C77CE0"

PAIRS = {"fl": "fr", "fr": "fl", "rl": "rr", "rr": "rl"}
CORNERS = ("fl", "fr", "rl", "rr")


@dataclass(frozen=True)
class DriverState:
    """Everything the instrument shows. `None` is missing and shows as a dash.

    Deliberately not the race state: this takes the three numbers it draws and
    nothing else, so it can be built and tested without a race.
    """
    temps_c: dict[str, float | None] | None = None
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


def onset_for(compound: str | None) -> float | None:
    """The wear-onset temperature for this compound, or None if unknown.

    None for an unknown compound rather than a default: a threshold guessed
    for a tyre nobody measured would colour the display against nothing.
    """
    if not compound:
        return None
    return WEAR_ONSET_C.get(compound.upper())


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
    """One corner: a big number and its label."""

    def __init__(self, corner: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._corner = corner
        box = QVBoxLayout(self)
        box.setContentsMargins(0, 14, 0, 10)
        box.setSpacing(4)
        self.value = QLabel("--")
        self.value.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.value.setStyleSheet(
            "font-family:Archivo,Arial;font-weight:800;font-size:104px;"
            f"letter-spacing:-3px;color:{COOL};background:transparent;")
        name = QLabel(corner.upper())
        name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        name.setStyleSheet(
            "font-family:'JetBrains Mono',monospace;font-size:15px;"
            f"letter-spacing:4px;color:{INK_DIM};background:transparent;")
        box.addWidget(self.value)
        box.addWidget(name)
        self.setMinimumWidth(210)
        self._paint("missing", False)

    def show_value(self, value: float | None, state: str,
                   lopsided: bool) -> None:
        self.value.setText("--" if value is None else f"{value:.0f}")
        self._paint(state, lopsided)

    def _paint(self, state: str, lopsided: bool) -> None:
        ink = {"over": OVER, "near": NEAR, "cool": COOL,
               "missing": INK_DIM}[state]
        border = LOPSIDED if lopsided else {
            "over": OVER, "near": NEAR}.get(state, EDGE)
        background = "#1D1211" if state == "over" else PANEL
        self.value.setStyleSheet(
            "font-family:Archivo,Arial;font-weight:800;font-size:104px;"
            f"letter-spacing:-3px;color:{ink};background:transparent;")
        self.setStyleSheet(
            f"background:{background};border:3px solid {border};"
            "border-radius:10px;")


class _Stat(QWidget):
    """One large number with a caption under it."""

    def __init__(self, label: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
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
            "font-family:'JetBrains Mono',monospace;font-size:15px;"
            f"letter-spacing:4px;color:{INK_DIM};background:transparent;")
        self.sub = QLabel("")
        self.sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.sub.setStyleSheet(
            "font-family:'JetBrains Mono',monospace;font-size:17px;"
            f"color:{INK_DIM};background:transparent;")
        box.addWidget(self.value)
        box.addWidget(self.caption)
        box.addWidget(self.sub)

    def _restyle(self) -> None:
        self.value.setStyleSheet(
            "font-family:Archivo,Arial;font-weight:800;font-size:180px;"
            f"letter-spacing:-7px;color:{self._ink};background:transparent;")

    def show_value(self, text: str, sub: str = "", *, urgent: bool = False) -> None:
        self.value.setText(text)
        self.sub.setText(sub)
        ink = NEAR if urgent else INK
        if ink != self._ink:
            self._ink = ink
            self._restyle()


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

    Five items, and the order is the order he needs them: the number he is
    watching the gauge for, the seconds until it arrives, what is going on the
    car, where it puts him, and what the stint after this one is.
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
        self.out_stat = _Stat("out in")
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
        self.release_stat.show_value(
            format_release(seconds),
            "seconds" if seconds and seconds > 0 else
            "" if seconds is None else "release",
            urgent=seconds is not None and seconds <= 10)

        if state.fuel_target_l is None:
            # Nothing sized the stop. Silence rather than a number the app
            # invented - the same refusal `RefuelWatch.note` makes, and for
            # the same reason: he is holding the trigger on this figure.
            self.fuel_stat.show_value("--", "nothing sized this stop")
        else:
            aboard = (f"{state.fuel_l:.0f} aboard" if state.fuel_l is not None
                      else "")
            self.fuel_stat.show_value(f"{state.fuel_target_l:.0f}", aboard)

        # The plan's decision, not a reading off the car. Nothing here knows
        # how worn the set coming off is, because no packet format carries
        # wear at all.
        self.tyre_stat.show_value(state.compound or "--",
                                  "plan" if state.compound else "no plan")

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

        tyres = QWidget()
        grid = QGridLayout(tyres)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(16)
        self.tyres = {c: _Tyre(c) for c in CORNERS}
        # Laid out as he sits in the car, not mirrored.
        grid.addWidget(self.tyres["fl"], 0, 0)
        grid.addWidget(self.tyres["fr"], 0, 1)
        grid.addWidget(self.tyres["rl"], 1, 0)
        grid.addWidget(self.tyres["rr"], 1, 1)
        self.tyre_caption = QLabel("TYRE SURFACE °C")
        self.tyre_caption.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.tyre_caption.setStyleSheet(
            "font-family:'JetBrains Mono',monospace;font-size:15px;"
            f"letter-spacing:4px;color:{INK_DIM};background:transparent;")
        grid.addWidget(self.tyre_caption, 2, 0, 1, 2)

        row.addStretch(1)
        row.addWidget(self.box_stat)
        row.addStretch(1)
        row.addWidget(tyres)
        row.addStretch(1)
        row.addWidget(self.fuel_stat)
        row.addStretch(1)

        # **The two states are two widgets, swapped, not one relabelled.**
        # Relabelling five captions on a screen he reads while stationary in
        # the box would leave the previous state's numbers on it for whatever
        # part of a frame the repaint takes, and the numbers mean different
        # things - a litre figure under a "laps" caption is the shape of
        # mistake this display exists to avoid.
        self.running = QWidget()
        self.running.setLayout(row)

        self.box = _BoxPanel()

        self.states = QStackedLayout()
        self.states.addWidget(self.running)
        self.states.addWidget(self.box)
        outer.addLayout(self.states)

        self.update_state(DriverState())

    def update_state(self, state: DriverState) -> None:
        self.states.setCurrentWidget(self.box if state.in_box else self.running)
        if state.in_box:
            self.box.show_state(state)
        temps = state.temps_c or {}
        for corner, widget in self.tyres.items():
            kind, lopsided = classify(corner, temps, state.compound)
            widget.show_value(temps.get(corner), kind, lopsided)
        self.tyre_caption.setText(
            "TYRE SURFACE °C" if not state.compound
            else f"TYRE SURFACE °C · {state.compound.upper()}")

        if state.laps_to_box is None:
            self.box_stat.show_value("--", "no plan")
        else:
            self.box_stat.show_value(
                f"{state.laps_to_box:.0f}",
                f"plan: lap {state.box_on_lap}" if state.box_on_lap else "",
                # **Urgent inside two laps**, which is where the number stops
                # being background and starts being a thing to act on.
                urgent=state.laps_to_box <= 2)

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
