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
    MIN_SIGHTINGS,
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
            # **A different PATTERN per row, not a different width.**
            # `Roster.name_bitmap` normalises to a fixed shape, so names that
            # differ only in width are the SAME picture afterwards and
            # `_merge_converged` folded them: six rows came back as one driver
            # with 144 sightings over 24 frames. That is invisible to a test
            # asking only whether a stop was filed, and fatal to any test about
            # WHOSE stop it was - the car in the lane resolved to the same
            # cluster as our own row, so nothing here could tell that the wall
            # was filing the driver's own stop as a rival's.
            for block in range(index + 1):
                left = 96 + block * 22
                frame[y - 5:y + 5, left:left + 12] = (
                    DARK if index == OWN else INK)
        if index in in_lane:
            # **A circle, not a square.** The reader tests roundness - a filled
            # circle fills pi/4 of its box, and the real discs measured 0.780
            # and 0.798 - so a square fixture tests a shape GT7 does not draw.
            ys, xs = np.mgrid[0:DISC_SIZE, 0:DISC_SIZE]
            centre = (DISC_SIZE - 1) / 2.0
            round_ = (ys - centre) ** 2 + (xs - centre) ** 2 <= (
                DISC_SIZE / 2.0) ** 2
            frame[y - DISC_SIZE // 2:y + DISC_SIZE // 2,
                  DISC_X:DISC_X + DISC_SIZE][round_] = DISC
            number = _digits(fuel.get(index, 40))
            left = DISC_X + DISC_SIZE + int(DISC_SIZE * 0.7)
            top = y - number.shape[0] // 2
            frame[top:top + number.shape[0],
                  left:left + number.shape[1]][number] = INK
    return frame


# What a test needs a cluster seen before it counts as a driver. Two rather
# than the production twenty: reaching twenty means twenty full board reads per
# case, which cost three minutes across this file, and nothing here is about
# where the threshold sits - `test_a_cluster_too_rarely_seen...` sets its own.
FEW = 2


def a_wall(**kw):
    """A wall that treats a couple of sightings as a driver."""
    kw.setdefault("min_sightings", FEW)
    return PitWall(**kw)


def warm(wall, clock, *, in_lane=(), frames=FEW + 1):
    """Show the board until its rows are established drivers.

    **`_close` refuses a cluster below its sighting floor as a misread**, and
    with the rows finally distinct each frame is one sighting per driver rather
    than six. In a real race the board is read for laps before anyone pits, so
    this is what these tests always meant; it only used to be free because
    every row counted as the same car.

    `in_lane` keeps a driver OUT of `_seen_clean`, which is what `partial`
    turns on - a car nobody ever saw on the board without its columns.
    """
    for _ in range(frames):
        wall.see(a_frame(in_lane=in_lane, fuel={row: 40 for row in in_lane}),
                 now=clock.tick())


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
    wall = a_wall()
    warm(wall, clock)
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
    wall = a_wall()
    warm(wall, clock)
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
    wall = a_wall()
    # Warmed with him ALREADY in the lane, so he is never seen clean - which
    # is exactly what makes the entry figure a floor.
    warm(wall, clock, in_lane=(1,))
    for litres in (60, 83):
        wall.see(a_frame(in_lane=(1,), fuel={1: litres}), now=clock.tick())
    closed = []
    for _ in range(CLOSE_AFTER_CLEAN_FRAMES):
        closed += wall.see(a_frame(), now=clock.tick())
    assert closed and closed[0].partial


def test_a_car_seen_out_of_the_lane_first_is_not_partial():
    clock = Clock()
    wall = a_wall()
    warm(wall, clock)                       # clean frames, nobody in the lane
    for litres in (19, 40, 83):
        wall.see(a_frame(in_lane=(1,), fuel={1: litres}), now=clock.tick())
    closed = []
    for _ in range(CLOSE_AFTER_CLEAN_FRAMES):
        closed += wall.see(a_frame(), now=clock.tick())
    assert closed and not closed[0].partial


def test_every_stop_carries_the_evidence_behind_it():
    """CLAUDE.md rule 4."""
    clock = Clock()
    wall = a_wall()
    warm(wall, clock)
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
    wall = a_wall()
    warm(wall, clock)
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
    wall = a_wall()
    warm(wall, clock)
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


def test_a_fill_that_never_moved_was_not_watched():
    """`partial` means the entry figure is an upper bound, and a visit whose
    lowest and highest readings are the same number is the strongest case of
    that. On the Spa race one driver came back 19 L in and 19 L out on two
    readings - a fragment of a stop that really ran to 83."""
    clock = Clock()
    wall = a_wall()
    warm(wall, clock)
    for _ in range(3):
        wall.see(a_frame(in_lane=(1,), fuel={1: 19}), now=clock.tick())
    closed = []
    for _ in range(CLOSE_AFTER_CLEAN_FRAMES):
        closed += wall.see(a_frame(), now=clock.tick())
    assert closed and closed[0].partial
    assert closed[0].stop.litres == 0.0


# --- the entry hook, which is the ONLY road RIVAL_BOXED has ---------------

def a_watching_wall(seen, **kw):
    handles = (f"Car #{n}" for n in range(1, 9))
    return a_wall(on_enter=seen.append,
                  name_for=lambda taken=(): next(handles), **kw)


def test_a_car_entering_is_announced_even_though_nobody_has_named_him_yet():
    """**The defect that made `rival_boxed` unreachable in production.** Names
    were minted only at `_close`, so a driver the archive has never seen was
    nameless while he stood in the box - and the coordinator refuses a nameless
    entry. `drivers` has zero rows, so that is every driver in every race, and
    the call ranked above every other rival call could not be spoken once.

    Worse, the driver was added to `_announced` BEFORE the name was resolved,
    so the refusal spent the one announcement and no later frame could recover
    it: a refusal that becomes its own baseline (rule 10).
    """
    seen, clock = [], Clock()
    wall = a_watching_wall(seen)
    for _ in range(FEW + 1):
        wall.see(a_frame(in_lane=(4,), fuel={4: 12}), lap=8,
                 now=clock.tick())
    assert [(e.driver, e.fuel_in_l) for e in seen] == [("Car #1", 12)]


def test_our_own_stop_is_not_announced_as_a_rival_boxing():
    """`read_rows` is the one path that returns the driver's own row, so
    without an exclusion the app announces our own stop and compares it against
    itself."""
    seen, clock = [], Clock()
    wall = a_watching_wall(seen)
    for _ in range(FEW + 1):
        wall.see(a_frame(in_lane=(OWN,), fuel={OWN: 12}), lap=8,
                 now=clock.tick())
    assert seen == []


def test_a_cluster_too_rarely_seen_to_be_a_driver_is_not_announced():
    """`_close` refuses one below `MIN_SIGHTINGS` as a misread. Announcing it
    aloud first and declining to file it afterwards is the weaker bar on the
    louder channel."""
    seen, clock = [], Clock()
    # The PRODUCTION floor here, because this test is about where it sits.
    wall = a_watching_wall(seen, min_sightings=MIN_SIGHTINGS)
    for _ in range(3):
        wall.see(a_frame(in_lane=(4,), fuel={4: 12}), lap=8,
                 now=clock.tick())
    assert seen == []


def test_a_second_stop_by_the_same_car_is_announced_too():
    """`_announced` was keyed per driver for the whole SESSION, so in a
    two-stop race every rival's second entry - the one that decides the end of
    the race - was silent."""
    seen, clock = [], Clock()
    wall = a_watching_wall(seen)
    for _ in range(FEW + 1):
        wall.see(a_frame(in_lane=(4,), fuel={4: 12}), lap=8,
                 now=clock.tick())
    for _ in range(CLOSE_AFTER_CLEAN_FRAMES):
        wall.see(a_frame(), lap=9, now=clock.tick())
    for _ in range(4):
        wall.see(a_frame(in_lane=(4,), fuel={4: 20}), lap=15,
                 now=clock.tick())
    assert [e.fuel_in_l for e in seen] == [12, 20]


def test_our_own_stop_is_never_filed_as_a_rivals():
    """**The book is permanent and keyed by name.** `read_rows` returns the
    driver's own row like any other, so the wall handed his own stop to
    `rival_book`, which recorded it against his own name as an opponent -
    and every figure drawn from it afterwards, his burn, his fill discipline,
    when he stops, would be his own habits fed back to him as a rival's.

    It went unseen because the fixture could not tell two drivers apart: the
    rows differed only in name WIDTH and all six folded into one cluster, so
    the car "in the lane" WAS the own row in every test in this file.
    """
    clock = Clock()
    wall = a_wall()
    warm(wall, clock)
    for litres in (19, 40, 83):
        wall.see(a_frame(in_lane=(OWN,), fuel={OWN: litres}),
                 now=clock.tick())
    closed = []
    for _ in range(CLOSE_AFTER_CLEAN_FRAMES):
        closed += wall.see(a_frame(), now=clock.tick())
    assert closed == [] and wall.stops() == []


def test_a_rival_in_the_same_race_is_still_filed():
    """The exclusion has to be about identity and not about pit stops."""
    clock = Clock()
    wall = a_wall()
    warm(wall, clock)
    for litres in (19, 40, 83):
        wall.see(a_frame(in_lane=(1,), fuel={1: litres}), now=clock.tick())
    closed = []
    for _ in range(CLOSE_AFTER_CLEAN_FRAMES):
        closed += wall.see(a_frame(), now=clock.tick())
    assert len(closed) == 1 and closed[0].stop.fuel_out_l == 83.0


def test_our_own_stop_open_at_the_flag_is_not_filed_either():
    """`close_all` runs where no board is readable, so the own row cannot be
    identified from the frame - which is why it is remembered."""
    clock = Clock()
    wall = a_wall()
    warm(wall, clock)
    for litres in (19, 40, 83):
        wall.see(a_frame(in_lane=(OWN,), fuel={OWN: litres}),
                 now=clock.tick())
    assert wall.close_all() == []


def test_health_has_a_caller_in_the_app():
    """`health()` is reported by the controller, not only by tests.

    **This codebase has built both ends and skipped the caller six times** -
    `LiveWearSampler.new_session`, `DriverView`, `handover.py`,
    `context_from_stored`, `laps.laps_completed`, and `health()` itself, which
    was written to end the pit wall's silence and then left with no call site
    at all while its own docstring claimed it was being logged.

    A source-level check is a weak test and is deliberate: the defect it
    guards is a MISSING CALL, which no behavioural test of `PitWall` can
    catch, because `PitWall` is perfectly correct when nobody asks it
    anything. It fails the moment the call is deleted again.
    """
    from pathlib import Path

    import pitcrew.controller as controller_module

    source = Path(controller_module.__file__).read_text(encoding="utf-8")
    assert source.count("wall.health()") >= 2, (
        "the pit wall's health line has lost its caller again - it belongs on "
        "the lap-completed path and in _stop_pit_wall")


def test_health_counts_frames_at_every_stage():
    """Each counter is frames, so the line reads as one funnel.

    A first version counted `named` once per driver per frame and `pit_cols`
    once per pit row per frame, so a healthy race printed a middle stage an
    order of magnitude larger than the frames it came from.
    """
    wall = PitWall(Roster())
    line = wall.health()
    assert "0 frames" in line
    for stage in ("ladder", "own row", "any named", "our row", "gaps",
                  "pit columns", "fuel read"):
        assert stage in line
