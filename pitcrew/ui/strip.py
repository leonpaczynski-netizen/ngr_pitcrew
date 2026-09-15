"""The strip: the board's quick-reference numbers, for a phone on the game monitor.

Asked for on 15 Sep 2026. He wanted a small screen for "quick data reference"
and the ultrawide above for the rest, then settled the hardware himself: his
own iPhone, landscape, on a magic arm at the bottom-right corner of the game
monitor, showing a page the app serves over the local network - *"it could be
a locally rendered HTML so it doesn't have to be directly connected"*.

**This module decides what the strip says; `strip.html` only draws it.** The
page is a dumb renderer on purpose. Every word and number on it comes out of
the same functions the Qt board uses (`driver_view.box_block`, `gap_block`,
`fuel_stop_block`, ...), so the phone and the ultrawide cannot word one number
two ways - the fuel block has been "-7.1 in hand" once already for want of one
expression (CLAUDE.md rules 12 and 13). Choosing in JavaScript would be a
second copy of the priority, untested, on a device he cannot inspect mid-race.

### The centre slot changes with what matters right now

His call: *"changes based on what's important right now, use it as a
changeable dash for critical information."* A slot whose meaning changes is
exactly the hazard rule 13 names - one big number that means different things
at different moments - so it obeys three rules:

* **It always carries its caption**, and the caption is the item's own
  (LAPS TO THE STOP, BEHIND, ...), never a generic "critical".
* **The order is fixed and lives here, once**, agreed with him on 15 Sep:
  in the box the release countdown; then BOX THIS LAP (or late); then fuel
  short of the stop; then a car within `NEAR_CAR_S`; otherwise laps to the
  stop (race) or the time difference (practice and qualifying).
* **A car slot holds** until the gap opens past `NEAR_CAR_RELEASE_S`, so a
  gap reading 0.98 then 1.02 does not flip the slot's meaning on every read.
  That hold is state, so `new_session()` drops it (rule 11) and the controller
  calls it whenever the board opens.

When the centre takes a neighbour, **that side's flank shows laps to the stop
instead**, so the neighbour is not drawn twice and nothing leaves the strip.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from pitcrew.ui.driver_view import (
    Block, DriverState, abs_light, box_block, delta_block,
    format_lap_ms, fuel_stop_block, fuel_target_block, gap_block,
    release_block, tcs_light, tyres_block, wet_light)

# **A car "within a second" is his threshold, not a measurement** (15 Sep
# 2026). What makes it usable is the reader, which is measured: two reads of
# one car under 4 s apart differ by a median 0.03-0.11 s (`race/gaps.py`), so
# at one second the slot is deciding on the gap, not on the digit reader.
NEAR_CAR_S = 1.0
# The hold. A car that took the slot keeps it until the gap is this wide -
# 0.2 s is about twice the reader's own median scatter, so a read wobbling
# across the line cannot toggle the slot on its own.
NEAR_CAR_RELEASE_S = 1.2

CENTRE_RELEASE = "release"
CENTRE_BOX = "box"
CENTRE_FUEL_SHORT = "fuel_short"
CENTRE_CAR_AHEAD = "car_ahead"
CENTRE_CAR_BEHIND = "car_behind"
CENTRE_LAPS_TO_STOP = "laps_to_stop"
CENTRE_TIME_DIFF = "time_diff"

# **The centre states that are an instruction, not a reading.** Only these
# flood the slot on the page. Laps to the stop is amber from two laps out,
# which is right for a number to watch and wrong for a slot turning solid
# amber two laps before there is anything to do - a flood that fires early
# teaches him to ignore the flood.
ACT_NOW = (CENTRE_RELEASE, CENTRE_BOX, CENTRE_FUEL_SHORT)

PAYLOAD_VERSION = 1


# **What a block is ABOUT, whichever slot it is in.** `id` names why the
# centre holds what it holds; `subject` names the number itself, and the same
# number keeps the same subject as it moves - laps to the stop in the centre,
# then in the flank a car pushed it to. The page morphs a subject from its old
# slot to its new one, so a change of meaning is something he SEES happen
# rather than a different number that is simply there on the next glance
# (his pick, 15 Sep 2026: "motion as signal"). No two blocks on one payload
# share a subject.
SUBJECT_LAPS_TO_STOP = "laps_to_stop"
SUBJECT_AHEAD = "ahead"
SUBJECT_BEHIND = "behind"
SUBJECT_FUEL_TO_STOP = "fuel_to_stop"


@dataclass(frozen=True)
class Item:
    """One captioned block on the strip."""
    caption: str
    block: Block
    id: str = ""
    subject: str = ""

    def to_json(self) -> dict:
        return {"id": self.id, "subject": self.subject,
                "caption": self.caption,
                "value": self.block.value, "sub": self.block.sub,
                "tone": self.block.tone,
                "act": self.id in ACT_NOW and self.block.urgent}


def _laps_to_stop(state: DriverState) -> Item:
    return Item("LAPS TO THE STOP", box_block(state), CENTRE_LAPS_TO_STOP,
                SUBJECT_LAPS_TO_STOP)


def _gap(state: DriverState, side: str) -> Item:
    gap = state.ahead if side == "ahead" else state.behind
    ahead = side == "ahead"
    return Item(side.upper(), gap_block(gap),
                CENTRE_CAR_AHEAD if ahead else CENTRE_CAR_BEHIND,
                SUBJECT_AHEAD if ahead else SUBJECT_BEHIND)


def _seconds(state: DriverState, side: str) -> float | None:
    gap = state.ahead if side == "ahead" else state.behind
    if gap is None or gap.seconds is None or not math.isfinite(gap.seconds):
        return None
    return gap.seconds


class StripComposer:
    """Builds the strip's payload from the board's state, one tick at a time.

    Holds exactly one thing across ticks: which neighbour, if any, has the
    centre slot. `new_session()` drops it.
    """

    def __init__(self) -> None:
        self._held_side: str | None = None

    def new_session(self) -> None:
        """Forget the held neighbour. A car that was close at the end of the
        last race is not close at the start of this one (rule 11)."""
        self._held_side = None

    # ------------------------------------------------------------------ race

    def _near_side(self, state: DriverState) -> str | None:
        """Which neighbour is inside the threshold, honouring the hold.

        Both inside: the nearer one; a dead heat goes to the car behind,
        because being passed costs a place now and passing can wait a lap.
        """
        held = self._held_side
        if held is not None:
            seconds = _seconds(state, held)
            if seconds is not None and seconds <= NEAR_CAR_RELEASE_S:
                return held
        near = [(s, side) for side in ("behind", "ahead")
                if (s := _seconds(state, side)) is not None and s < NEAR_CAR_S]
        if not near:
            return None
        best = min(s for s, _ in near)
        # "behind" is listed first, so it is the one a dead heat returns.
        return next(side for s, side in near if s == best)

    def _race(self, state: DriverState) -> dict:
        if state.in_box:
            self._held_side = None
            return {
                "kind": "box",
                "centre": Item("RELEASE IN", release_block(state),
                               CENTRE_RELEASE, "release").to_json(),
                "left": Item("FUEL TO", fuel_target_block(state),
                             subject="fuel_target").to_json(),
                "right": Item("TYRES", tyres_block(state),
                              subject="tyres").to_json(),
                "extra": None,
            }

        left, right = _gap(state, "ahead"), _gap(state, "behind")
        stop = fuel_stop_block(state)
        side = None
        if not state.finished and state.laps_past_box is not None \
                and state.laps_to_box is not None:
            # The same block and caption as the default - `box_block` has
            # already turned it into NOW - with its own id for the page.
            centre = Item("LAPS TO THE STOP", box_block(state), CENTRE_BOX,
                          SUBJECT_LAPS_TO_STOP)
        elif state.fuel_to_stop is not None and state.fuel_to_stop < 0:
            centre = Item("IN HAND TO THE STOP", stop, CENTRE_FUEL_SHORT,
                          SUBJECT_FUEL_TO_STOP)
        elif not state.finished and (side := self._near_side(state)):
            centre = _gap(state, side)
            # The flank it came from shows the default instead, so the
            # neighbour is not drawn twice.
            if side == "ahead":
                left = _laps_to_stop(state)
            else:
                right = _laps_to_stop(state)
        else:
            centre = _laps_to_stop(state)
        self._held_side = side
        # Fuel sits in the extra slot unless it has taken the centre.
        extra = (None if centre.id == CENTRE_FUEL_SHORT
                 else Item("IN HAND TO THE STOP", stop,
                           subject=SUBJECT_FUEL_TO_STOP).to_json())
        return {"kind": "race", "centre": centre.to_json(),
                "left": left.to_json(), "right": right.to_json(),
                "extra": extra}

    # -------------------------------------------------------------- practice

    @staticmethod
    def _practice(state: DriverState) -> dict:
        return {
            "kind": state.session_kind,
            "centre": Item("TIME DIFF", delta_block(state),
                           CENTRE_TIME_DIFF, "time_diff").to_json(),
            "left": Item("LAPTIME",
                         Block(format_lap_ms(state.lap_time_ms)),
                         subject="laptime").to_json(),
            "right": Item("PRED. TIME",
                          Block(format_lap_ms(state.predicted_ms)),
                          subject="pred_time").to_json(),
            "extra": None,
        }

    # ------------------------------------------------------------------ all

    def compose(self, state: DriverState | None) -> dict:
        """The whole payload. `None` is no session - the page says so, rather
        than holding the last race's numbers (rule 11)."""
        if state is None:
            self._held_side = None
            return {"v": PAYLOAD_VERSION, "idle": True}
        body = (self._race(state) if state.session_kind == "race"
                else self._practice(state))
        lights = [wet_light(state.wet),
                  abs_light(state.abs_setting, state.front_lock),
                  tcs_light(state.tcs_active)]
        body["lights"] = [{"word": word.upper(), "sub": sub, "ink": ink}
                          for word, sub, ink in lights]
        return {"v": PAYLOAD_VERSION, "idle": False, **body}
