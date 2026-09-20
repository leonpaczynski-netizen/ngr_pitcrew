"""The strip: his own car, at a glance, on the phone right of the wheel.

Asked for on 15 Sep 2026 as quick reference on the game monitor. **Redrawn on
17 Sep 2026** when he settled three screens - *"Phone - my car immediate
regular data. Tablet - what's going on around me. Monitor - history"* - and
showed the face he wanted: a lap timer's. Last lap and the best across the
top, the delta as a flood across the middle, the lap bottom-left, and where
the timer has the time of day, *"our fuel target and burn to it"*.

**So the gaps and laps to the stop are not here any more.** They go to the
tablet with the rest of the field. What stays is what is about this car.

**This module decides what the strip says; `strip.html` only draws it.** Every
figure comes from `driver_view`'s block functions - the ones the ultrawide
draws - so the phone and the board cannot word one number two ways (CLAUDE.md
rules 12 and 13). Choosing in JavaScript would be a second copy, untested, on
a device he cannot inspect mid-race.

### What the delta is against, by session

* **Practice and qualifying:** the best lap ever recorded on this compound -
  `best_lap_on_file`, this car, circuit, game version and tyre.
* **Race:** the plan's lap time for this lap, the projected lap against it.

### An instruction still takes the middle

The flood is the delta, **except when there is something to do now**: in the
box the release countdown, then BOX THIS LAP (or late), then fuel short of the
stop. Those take the band in amber (`ACT_NOW`), in that fixed order, and each
carries its own caption - a band whose meaning changes is exactly rule 13's
hazard, so it is never uncaptioned.
"""
from __future__ import annotations

from dataclasses import dataclass

from pitcrew.ui.driver_view import (
    DECLARED, DERIVED, Block, DriverState, abs_light, box_block,
    face_best_block, face_burn_block, face_burn_caption, face_delta_block,
    face_lap_block, face_last_block, fuel_stop_block, fuel_target_block,
    release_block, stamped, tcs_light, tyres_block, wet_light)

CENTRE_RELEASE = "release"
CENTRE_BOX = "box"
CENTRE_FUEL_SHORT = "fuel_short"
CENTRE_DELTA = "delta"

# **The centre states that are an instruction, not a reading.** Only these
# flood amber. The delta floods too, but in its own red and green, which say
# quick or slow and never "do something".
ACT_NOW = (CENTRE_RELEASE, CENTRE_BOX, CENTRE_FUEL_SHORT)

# What a block is about, so the page can tell a changed number from a changed
# meaning: a value that moves within one subject rolls; a new subject in the
# band is a new thing, and wipes in.
SUBJECT_DELTA = "delta"
SUBJECT_LAPS_TO_STOP = "laps_to_stop"
SUBJECT_FUEL_TO_STOP = "fuel_to_stop"

PAYLOAD_VERSION = 2

# What a lamp says when it has no reading at all, from the lamp helpers in
# `driver_view` - never "the answer is no".
UNREAD_LIGHT = ("no reading", "no signal", "cannot see")


@dataclass(frozen=True)
class Item:
    """One captioned figure on the strip."""
    caption: str
    block: Block
    id: str = ""
    subject: str = ""

    def to_json(self) -> dict:
        return {"id": self.id, "subject": self.subject,
                "caption": self.caption,
                "value": self.block.value, "sub": self.block.sub,
                "tone": self.block.tone,
                # **Where the figure came from**, so the page can mark it.
                # Three white numbers in a row - the lap he drove, the lap the
                # plan asks for, the lap the app projects - are three
                # different claims and were drawn identically (rules 3, 5).
                "register": self.block.register,
                "act": self.id in ACT_NOW and self.block.urgent}


class StripComposer:
    """Builds the strip's payload from the board's state, one tick at a time.

    Holds nothing across ticks now that the neighbour slot has gone to the
    tablet; `new_session()` stays so the controller's reset has a caller
    (rule 11) the day it holds something again.
    """

    def new_session(self) -> None:
        """Nothing is held between sessions."""

    # ------------------------------------------------------------------ race

    @staticmethod
    def _centre(state: DriverState) -> Item:
        """The band: an instruction if there is one, the delta otherwise."""
        # **The plan's own figures are derived** - a model with stated
        # assumptions produced them (CLAUDE.md §5) - and they sit in the
        # same slot as a measured delta, at the same size, in one ink.
        if not state.finished and state.laps_past_box is not None \
                and state.laps_to_box is not None:
            return Item("LAPS TO THE STOP",
                        stamped(box_block(state), DERIVED), CENTRE_BOX,
                        SUBJECT_LAPS_TO_STOP)
        if state.fuel_to_stop is not None and state.fuel_to_stop < 0:
            return Item("IN HAND TO THE STOP",
                        stamped(fuel_stop_block(state), DERIVED),
                        CENTRE_FUEL_SHORT, SUBJECT_FUEL_TO_STOP)
        caption, block = face_delta_block(state)
        return Item(caption, block, CENTRE_DELTA, SUBJECT_DELTA)

    @staticmethod
    def _box(state: DriverState) -> dict:
        return {
            "kind": "box",
            # In the box every figure is the plan's: what to fill to, what
            # goes on, how long he holds the trigger. None is a reading.
            "last": Item("FUEL TO", stamped(fuel_target_block(state), DERIVED),
                         subject="fuel_target").to_json(),
            "best": Item("TYRES", stamped(tyres_block(state), DECLARED),
                         subject="tyres").to_json(),
            "centre": Item("RELEASE IN",
                           stamped(release_block(state), DERIVED),
                           CENTRE_RELEASE, "release").to_json(),
            "lap": Item("LAP", face_lap_block(state)).to_json(),
            "burn": None,
        }

    # ------------------------------------------------------------------ all

    def compose(self, state: DriverState | None) -> dict:
        """The whole payload. `None` is no session - the page says so, rather
        than holding the last race's numbers (rule 11)."""
        if state is None:
            return {"v": PAYLOAD_VERSION, "idle": True}
        racing = state.session_kind == "race"
        if racing and state.in_box:
            body = self._box(state)
        else:
            best_caption, best = face_best_block(state)
            burn = face_burn_block(state)
            centre = (self._centre(state) if racing else
                      Item(*face_delta_block(state), CENTRE_DELTA,
                           SUBJECT_DELTA))
            body = {
                "kind": state.session_kind,
                "last": Item("LAST LAP", face_last_block(state)).to_json(),
                "best": Item(best_caption, best).to_json(),
                "centre": centre.to_json(),
                "lap": Item("LAP", face_lap_block(state)).to_json(),
                # **Absent, not dashed, outside a race**: practice has no plan
                # burn, and a dash there would be a reason nobody needs.
                #
                # **And the caption names which burn the target is** - the
                # plan's or this race's own (`face_burn_caption`). The figure
                # under it steps 2.2 L when the race's burn is installed and
                # the slot said "BURN VS TARGET" over both halves, which is
                # rule 13 on the screen right of his wheel. The caption
                # carries it rather than the sub, because the sub is the
                # stint's mean and ITS lap count, and two counts on one line
                # is the same defect one line down.
                "burn": (None if burn is None
                         else Item(face_burn_caption(state), burn).to_json()),
            }
        lights = [wet_light(state.wet),
                  abs_light(state.abs_setting, state.front_lock),
                  tcs_light(state.tcs_active)]
        # `unread` is the distinction the lamp helpers were written to keep:
        # "no reading" and "no signal" are the instrument saying it cannot
        # see, where "no lock" and "" are measured negatives (rule 3). The
        # page has no way to tell them apart from the word alone.
        body["lights"] = [{"word": word.upper(), "sub": sub, "ink": ink,
                           "unread": sub in UNREAD_LIGHT}
                          for word, sub, ink in lights]
        return {"v": PAYLOAD_VERSION, "idle": False, **body}
