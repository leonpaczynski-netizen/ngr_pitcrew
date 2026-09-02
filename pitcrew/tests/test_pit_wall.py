"""The live pit wall: watching a stop happen, and refusing to invent one.

Every rule here comes from something measured on the Spa replay of 1 Sep 2026:
the columns exist only while a car is standing, a frame that cannot be read is
not an absence, and a watcher that joins mid-fill has a floor rather than a
figure.
"""
from __future__ import annotations

import numpy as np

from pitcrew.race.pit_wall import (
    CLOSE_AFTER_CLEAN_FRAMES,
    MIN_READS,
    MIN_WATCHED_S,
    PitWall,
    Visit,
)
from pitcrew.telemetry.roster import NAME_SHAPE, Roster

W, H = 1920, 1080
DARK = (22, 28, 34)
PLATE = (36, 46, 60)
WHITE = (232, 236, 238)
FLAG_BLUE = (30, 60, 190)
DISC = (205, 42, 44)
INK = (238, 242, 244)

FLAG_X, FLAG_W = 256, 26
DISC_X, DISC_SIZE = 300, 28
PITCH, TOP, ROWS, OWN = 40, 190, 6, 2


def _digits(number, scale=2):
    """The fuel figure, rendered from the REAL template bank.

    Not a block of ink standing in for a number: the whole path under test ends
    in `hud_digits.read_fuel`, and a fixture that cannot be read by it proves
    nothing about a fixture that can. The leading block is the pump icon, which
    `read_fuel` drops.
    """
    from PIL import Image

    from pitcrew.telemetry.hud_digits import _bank

    cell, templates = _bank()
    glyphs = [
        np.asarray(Image.fromarray(((templates[c] > 0.5) * 255).astype("uint8"))
                   .resize((cell[0] * scale, cell[1] * scale), Image.NEAREST))
        > 127
        for c in str(int(number))]
    tall, gap = glyphs[0].shape[0], 3
    wide = 8 + gap + sum(g.shape[1] + gap for g in glyphs)
    canvas = np.zeros((tall, wide), dtype=bool)
    canvas[2:tall - 2, 0:8] = True              # the pump icon
    x = 8 + gap
    for glyph in glyphs:
        canvas[:, x:x + glyph.shape[1]] = glyph
        x += glyph.shape[1] + gap
    return canvas


def a_frame(*, in_lane=(), fuel=None, names=True):
    """A board with flags, one white own-row, and pit columns where asked.

    `in_lane` is the row indices currently showing the pit columns, and `fuel`
    maps a row index to the number drawn beside its disc. A row in the lane
    with no entry in `fuel` gets a default, because a car standing in its box
    always has a figure on it.
    """
    frame = np.zeros((H, W, 3), dtype=int)
    frame[:] = DARK
    fuel = fuel or {}
    for index in range(ROWS):
        y = TOP + index * PITCH + (28 if index == OWN else
                                   (56 if index > OWN else 0))
        frame[y - 9:y + 9, FLAG_X:FLAG_X + FLAG_W] = FLAG_BLUE
        frame[y - 16:y + 16, 40:FLAG_X - 8] = (WHITE if index == OWN
                                               else PLATE)
        if names:
            # A different name width per row, which is what identity is: a
            # short name and a long one are not the same driver.
            wide = 30 + index * 14
            frame[y - 5:y + 5, 96:96 + wide] = (
                DARK if index == OWN else INK)
        if index in in_lane:
            frame[y - DISC_SIZE // 2:y + DISC_SIZE // 2,
                  DISC_X:DISC_X + DISC_SIZE] = DISC
            number = _digits(fuel.get(index, 40))
            left = DISC_X + DISC_SIZE + int(DISC_SIZE * 0.7)
            top = y - number.shape[0] // 2
            frame[top:top + number.shape[0],
                  left:left + number.shape[1]][number] = INK
    return frame


class Clock:
    """A frame clock, because a stop is measured in seconds and the guard that
    discards fragments is a duration."""

    def __init__(self, step=10.0):
        self.now, self.step = 0.0, step

    def tick(self):
        self.now += self.step
        return self.now


def blank():
    """A frame with no board at all - a menu, a replay cut, a paused game."""
    return np.full((H, W, 3), 90, dtype=int)


# --- what it does with a frame ---------------------------------------------

def test_a_board_with_nobody_in_the_lane_closes_nothing():
    clock = Clock()
    wall = PitWall()
    assert wall.see(a_frame(), now=clock.tick()) == []
    assert wall.stops() == []


def test_a_car_in_the_lane_is_latched_as_having_pitted():
    clock = Clock()
    wall = PitWall()
    wall.see(a_frame(in_lane=(1,)), now=clock.tick())
    assert any(wall.has_pitted(d) for d, _ in wall.named(min_sightings=1))


def test_a_frame_that_cannot_be_read_is_silence_and_not_absence():
    """The rule that stops a stop being closed in the middle of its own fill.

    A menu, a replay cut or a paused game says nothing about whether a car is
    standing in its box. Counting it as absence gives that car an exit figure
    taken from halfway through its own refuel.
    """
    clock = Clock()
    wall = PitWall()
    wall.see(a_frame(in_lane=(1,)), now=clock.tick())
    for _ in range(CLOSE_AFTER_CLEAN_FRAMES + 3):
        assert wall.see(blank(), now=clock.tick()) == []
    assert wall.stops() == []


def test_a_stop_closes_once_the_columns_are_gone_from_clean_frames():
    clock = Clock()
    wall = PitWall()
    for litres in (19, 40, 83):
        wall.see(a_frame(in_lane=(1,), fuel={1: litres}), now=clock.tick())
    closed = []
    for _ in range(CLOSE_AFTER_CLEAN_FRAMES):
        closed += wall.see(a_frame(), now=clock.tick())
    assert len(closed) == 1
    assert closed[0].reads >= MIN_READS
    assert closed[0].stop.fuel_in_l == 19.0
    assert closed[0].stop.fuel_out_l == 83.0


def test_one_reading_is_not_a_stop():
    """One figure cannot tell an entry from an exit."""
    visit = Visit(driver=0, lap=11, started_s=0.0, readings=[19])
    assert len(visit.readings) < MIN_READS


def test_something_briefer_than_the_dead_time_was_not_a_stop():
    """A GT7 stop has 16.9 s of dead time before a hose is even connected, so
    nothing shorter can be a car standing in its box. Over the whole Spa race
    this discarded two twelve-second fragments, one of them reporting identical
    entry and exit fuel because it had caught the same number twice - against
    real stops watched for 87 to 117 s."""
    clock = Clock(step=3.0)
    wall = PitWall()
    for litres in (19, 40):
        wall.see(a_frame(in_lane=(1,), fuel={1: litres}), now=clock.tick())
    closed = []
    for _ in range(CLOSE_AFTER_CLEAN_FRAMES):
        closed += wall.see(a_frame(), now=clock.tick())
    assert closed == []
    assert MIN_WATCHED_S < 16.9


def test_the_lowest_reading_is_the_entry_and_the_highest_the_exit():
    visit = Visit(driver=0, lap=11, started_s=0.0, readings=[19, 25, 37, 83])
    stop = visit.as_stop()
    assert stop.fuel_in_l == 19.0 and stop.fuel_out_l == 83.0
    assert stop.litres == 64.0


def test_a_visit_with_no_readings_has_no_fuel_rather_than_zero():
    """CLAUDE.md rule 3: a tank that was never read is not an empty one."""
    stop = Visit(driver=0, lap=11, started_s=0.0).as_stop()
    assert stop.fuel_in_l is None and stop.fuel_out_l is None
    assert stop.litres is None


# --- the honesty flags ------------------------------------------------------

def test_joining_after_the_fill_has_begun_is_marked_partial():
    """A late first reading is a floor, and nothing in the number says so."""
    clock = Clock()
    wall = PitWall()
    wall.see(a_frame(in_lane=(1,), fuel={1: 40}), now=clock.tick())   # first clean frame, in
    for litres in (60, 83):
        wall.see(a_frame(in_lane=(1,), fuel={1: litres}), now=clock.tick())
    closed = []
    for _ in range(CLOSE_AFTER_CLEAN_FRAMES):
        closed += wall.see(a_frame(), now=clock.tick())
    assert closed and closed[0].partial


def test_a_car_seen_out_of_the_lane_first_is_not_partial():
    clock = Clock()
    wall = PitWall()
    wall.see(a_frame(), now=clock.tick())                      # clean frame, nobody in the lane
    for litres in (19, 40, 83):
        wall.see(a_frame(in_lane=(1,), fuel={1: litres}), now=clock.tick())
    closed = []
    for _ in range(CLOSE_AFTER_CLEAN_FRAMES):
        closed += wall.see(a_frame(), now=clock.tick())
    assert closed and not closed[0].partial


def test_every_stop_carries_the_evidence_behind_it():
    """CLAUDE.md rule 4."""
    clock = Clock()
    wall = PitWall()
    wall.see(a_frame(), now=clock.tick())
    for litres in (19, 30, 55, 83):
        wall.see(a_frame(in_lane=(1,), fuel={1: litres}), now=clock.tick())
    closed = []
    for _ in range(CLOSE_AFTER_CLEAN_FRAMES):
        closed += wall.see(a_frame(), now=clock.tick())
    assert closed
    seen = closed[0]
    assert seen.reads >= 2
    assert seen.watched_s >= 0.0
    assert seen.driver_id is not None


# --- lifecycle --------------------------------------------------------------

def test_a_new_session_forgets_the_last_race_but_keeps_the_drivers():
    """CLAUDE.md rule 11 - and its one deliberate exception.

    Identity is the thing that SHOULD cross a session boundary; a race that
    opens holding the last one's pit flags is a race that reports them.
    """
    clock = Clock()
    wall = PitWall()
    for litres in (19, 40, 83):
        wall.see(a_frame(in_lane=(1,), fuel={1: litres}), now=clock.tick())
    for _ in range(CLOSE_AFTER_CLEAN_FRAMES):
        wall.see(a_frame(), now=clock.tick())
    before = len(wall.roster)
    assert wall.stops()

    wall.new_session()
    assert wall.stops() == []
    assert wall.positions() == {}
    assert not any(wall.has_pitted(d) for d in range(before))
    assert len(wall.roster) == before


def test_closing_the_session_files_a_stop_still_in_progress():
    """At the flag a car may still be standing. That is still a stop."""
    clock = Clock()
    wall = PitWall()
    wall.see(a_frame(), now=clock.tick())
    for litres in (19, 40, 83):
        wall.see(a_frame(in_lane=(1,), fuel={1: litres}), now=clock.tick())
    assert wall.stops() == []
    assert len(wall.close_all()) == 1


def test_a_seeded_roster_recognises_a_driver_from_a_previous_race():
    """The whole reason the book joins up across races."""
    clock = Clock()
    first = PitWall()
    first.see(a_frame(), now=clock.tick())
    ids = first.roster.drivers(min_sightings=1)
    assert ids
    first.roster.label(ids[0], "Rocky")

    second = PitWall(Roster(seed=first.roster.exemplars()))
    second.see(a_frame(), now=clock.tick())
    assert "Rocky" in second.positions()


def test_it_never_raises_on_rubbish():
    clock = Clock()
    wall = PitWall()
    assert wall.see(None) == []
    assert wall.see(np.zeros((4, 4, 3), dtype=int)) == []
    assert wall.see(np.zeros((NAME_SHAPE[1], NAME_SHAPE[0]), dtype=int)) == []
