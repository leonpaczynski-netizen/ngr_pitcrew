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
"""
from __future__ import annotations

from dataclasses import dataclass

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
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
        outer.addLayout(row)

        self.update_state(DriverState())

    def update_state(self, state: DriverState) -> None:
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
