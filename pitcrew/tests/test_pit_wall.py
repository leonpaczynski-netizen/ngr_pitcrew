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


def a_frame(*, in_lane=(), fuel=None, names=True, smudged=()):
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
            if index in smudged:
                # **Something bright where the figure goes, and no figure.**
                # What a glimpse looks like: a disc-shaped blob and a patch of
                # ink the fuel box accepts, which `read_fuel` cannot read.
                number = np.ones_like(number)
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


def test_a_visit_too_brief_to_be_filed_is_never_announced():
    """**Bathurst, Car #30.** Announced on its second reading, discarded three
    minutes later as "4 reads over 13 s is too brief to be a stop". The entry
    now waits for the same bar the stop is filed on, so what is not filed was
    never said."""
    seen, clock = [], Clock(step=3.0)
    wall = a_watching_wall(seen)
    warm(wall, clock)
    for litres in (40, 41, 42, 43):                  # 4 reads over 9 s
        wall.see(a_frame(in_lane=(4,), fuel={4: litres}), lap=8,
                 now=clock.tick())
    closed = []
    for _ in range(CLOSE_AFTER_CLEAN_FRAMES):
        closed += wall.see(a_frame(), lap=8, now=clock.tick())
    assert closed == [] and seen == []


def test_the_entry_is_announced_once_the_visit_meets_the_filing_bar():
    seen, clock = [], Clock(step=5.0)
    wall = a_watching_wall(seen)
    warm(wall, clock)
    for n, litres in enumerate((12, 13, 14, 15)):
        wall.see(a_frame(in_lane=(4,), fuel={4: litres}), lap=8,
                 now=clock.tick())
        # 0, 5 and 10 s watched are under MIN_WATCHED_S; 15 s is not.
        assert len(seen) == (1 if n >= 3 else 0), n
    assert seen[0].fuel_in_l == 12


def test_the_entry_says_whether_he_was_ahead_of_us_when_he_went_in():
    """A car ahead that pits drops behind us on the position byte without
    being passed.

    Driven through `_announce_entry` with the board places set by hand: the
    six-row fixture's clusters do not hold still enough across frames to
    stand for a place, which is a fact about the fixture and not the board.
    """
    seen = []
    wall = a_watching_wall(seen)
    wall._roster.sightings = lambda driver: 99
    wall._roster.spaced_sightings = lambda driver: 99
    # driver -> (his place, our place) the last time he was seen out.
    wall._clean_place = {11: (2, 5), 12: (7, 5), 13: (3, None)}
    for driver, litres in ((11, 20), (12, 30), (13, 40)):
        visit = Visit(driver=driver, lap=8, started_s=0.0,
                      readings=[litres, litres], last_s=MIN_WATCHED_S)
        wall._announce_entry(driver, visit, 8, own=1)
    ahead = {e.fuel_in_l: e.ahead_at_entry for e in seen}
    assert ahead == {20: True, 30: False, 40: None}


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


class _Lines:
    """The wall's log, kept. `log()` names it under `pitcrew.`, which does not
    propagate to pytest's capture, so the test holds the lines itself."""

    def __init__(self):
        self.lines = []

    def _keep(self, msg, *args, **_):
        self.lines.append(msg % args if args else msg)

    info = debug = warning = exception = _keep


def _kept_log(monkeypatch) -> _Lines:
    import pitcrew.race.pit_wall as pit_wall

    kept = _Lines()
    monkeypatch.setattr(pit_wall, "_log", kept)
    return kept


def _own_stop_lines(kept):
    return [line for line in kept.lines if "own stop" in line]


def test_a_glimpse_on_our_own_row_is_not_an_own_stop(monkeypatch):
    """Suzuka, 13 Sep 2026, lap 7: *"pit-wall: own stop on lap 7 not filed as
    a rival's"* - and he did not stop. 126.66 s, 53.5 L to 46.4 L, no pit
    lap. By then the whole race had drawn pit columns on six frames with
    **no fuel figure read on any of them**; the same line is on file for
    laps where he did not stop on 7 and 11 Sep.

    `_close` checked for our own car BEFORE the evidence every rival's stop
    has to meet, so a visit with no reading at all was announced as a stop.
    Our own row is the white plate, which is exactly what the white-disc and
    bright-ink tests find easiest to see."""
    caplog = _kept_log(monkeypatch)
    clock = Clock()
    wall = a_wall()
    warm(wall, clock)
    wall.see(a_frame(in_lane=(OWN,), smudged=(OWN,)), lap=7, now=clock.tick())
    closed = []
    for _ in range(CLOSE_AFTER_CLEAN_FRAMES):
        closed += wall.see(a_frame(), lap=7, now=clock.tick())
    assert closed == [] and wall.stops() == []
    assert _own_stop_lines(caplog) == []
    # And the same where nothing closes it but the flag or the stale clock.
    wall.see(a_frame(in_lane=(OWN,), smudged=(OWN,)), lap=9, now=clock.tick())
    assert wall.close_all() == []
    assert _own_stop_lines(caplog) == []


def test_a_real_own_stop_is_still_recognised_as_ours(monkeypatch):
    """The gate is the rival's bar, not a silencer: a stop watched with its
    fuel readings is still ours, and still not filed as anyone else's."""
    caplog = _kept_log(monkeypatch)
    clock = Clock()
    wall = a_wall()
    warm(wall, clock)
    for litres in (19, 40, 83):
        wall.see(a_frame(in_lane=(OWN,), fuel={OWN: litres}), lap=11,
                 now=clock.tick())
    for _ in range(CLOSE_AFTER_CLEAN_FRAMES):
        assert wall.see(a_frame(), now=clock.tick()) == []
    assert len(_own_stop_lines(caplog)) == 1
    assert "lap 11" in _own_stop_lines(caplog)[0]


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


# --- his own fill, kept (Bathurst, 20 Sep 2026) ----------------------------

def _own_stop(wall, clock, litres=(19, 40, 83), lap=11):
    for reading in litres:
        wall.see(a_frame(in_lane=(OWN,), fuel={OWN: reading}), lap=lap,
                 now=clock.tick())


def test_his_own_fill_is_kept_although_it_is_not_filed_as_a_rivals():
    """**Refusing to file it as a rival's left nothing filing it as his.**

    Bathurst, 20 Sep 2026: the fill was on screen for both of his stops,
    read 477 times a race for everybody else and zero times for him, because
    both own-car branches of `_close` returned `None` and dropped
    `Visit.readings` on the floor. The refusal stays - his own stop in
    `rival_stops` is his habits fed back to him as an opponent's - and the
    readings now go down a path of their own.
    """
    clock = Clock()
    fills = []
    wall = a_wall(on_own_fill=fills.append)
    warm(wall, clock)
    _own_stop(wall, clock)
    for _ in range(CLOSE_AFTER_CLEAN_FRAMES):
        assert wall.see(a_frame(), now=clock.tick()) == []
    assert wall.stops() == [], "his own stop is still not a rival's"
    assert len(wall.own_fills()) == 1 and len(fills) == 1
    fill = wall.own_fills()[0]
    assert (fill.lap, fill.fuel_in_l, fill.fuel_out_l) == (11, 19.0, 83.0)
    assert fill.litres == 64.0 and fill.reads == 3 and not fill.standing
    assert fill.watched_s >= MIN_WATCHED_S


def test_the_fill_can_be_read_while_he_is_still_standing_in_the_box():
    """The litres going in are worth having during the stop, not after it -
    that is the one number he asked for. `standing` says which it is."""
    clock = Clock()
    wall = a_wall()
    warm(wall, clock)
    assert wall.own_fill() is None
    _own_stop(wall, clock, litres=(19, 40))
    assert wall.own_fill() is None, "two readings in 10 s is not yet a stop"
    _own_stop(wall, clock, litres=(60,))
    live = wall.own_fill()
    assert live is not None and live.standing
    assert (live.fuel_in_l, live.fuel_out_l, live.litres) == (19.0, 60.0, 41.0)
    assert live.reads == 3


def test_a_glimpse_on_our_own_row_is_not_kept_as_a_fill(monkeypatch):
    """The glimpse branch is the one that fired on his lap 11 - `0 fuel reads
    over 17 s`. Below the bar a rival's fragment is dropped, and ours is
    dropped the same way: a fill with nothing read on it is not a fill."""
    _kept_log(monkeypatch)
    clock = Clock()
    fills = []
    wall = a_wall(on_own_fill=fills.append)
    warm(wall, clock)
    wall.see(a_frame(in_lane=(OWN,), smudged=(OWN,)), lap=11, now=clock.tick())
    assert wall.own_fill() is None
    for _ in range(CLOSE_AFTER_CLEAN_FRAMES):
        wall.see(a_frame(), lap=11, now=clock.tick())
    assert wall.own_fills() == [] and fills == []


def test_a_new_session_forgets_the_last_races_fill():
    """CLAUDE.md rule 11. A fill kept across the boundary is read as this
    race's, and "you took 64 litres" is a sentence about the wrong race."""
    clock = Clock()
    wall = a_wall()
    warm(wall, clock)
    _own_stop(wall, clock)
    for _ in range(CLOSE_AFTER_CLEAN_FRAMES):
        wall.see(a_frame(), now=clock.tick())
    assert wall.own_fills()
    wall.new_session()
    assert wall.own_fills() == [] and wall.own_fill() is None


def test_the_own_rows_columns_and_figures_are_counted_separately():
    """A column found on our own row is not a figure read off it.

    His lap 11 took 0 fuel readings over 17 s while rivals in the same window
    took 20 to 60 each, and nothing in the log could say whether the own row
    is genuinely harder to read or a gate is wrong. Two counters, so the next
    race can answer it.
    """
    clock = Clock()
    wall = a_wall()
    warm(wall, clock)
    _own_stop(wall, clock)
    assert ("our own row: pit columns on 3 frames -> fuel read 3"
            in wall.health())
    # And a glimpse counts its columns and no figure.
    other_clock = Clock()
    other = a_wall()
    warm(other, other_clock)
    other.see(a_frame(in_lane=(OWN,), smudged=(OWN,)),
              now=other_clock.tick())
    assert ("our own row: pit columns on 1 frames -> fuel read 0"
            in other.health())


def test_the_seed_is_reported_against_the_size_of_the_field(monkeypatch):
    """**160 known drivers for a seven-car race**, and nothing put the two
    numbers together (`logs/pitcrew.log:3233`, Bathurst 20 Sep 2026). The
    field size was known all evening - George said "P3 of 7" off it.

    Counted and reported only: capping the roster is a behaviour change and
    is deliberately not this.
    """
    caplog = _kept_log(monkeypatch)
    seed = {"Rocky": np.zeros(NAME_SHAPE[::-1], dtype=bool),
            "PUNISHED": np.ones(NAME_SHAPE[::-1], dtype=bool)}
    wall = PitWall(Roster(seed=seed))
    assert "seeded 2 for a field of unknown" in wall.health()

    wall.note_field_size(0)              # 0 is "no reading", never a field
    assert "field of unknown" in wall.health()

    wall.note_field_size(7)
    assert "seeded 2 for a field of 7, holding 2" in wall.health()
    said = [line for line in caplog.lines if "for a field of" in line]
    assert len(said) == 1 and "seeded with 2 known drivers" in said[0]

    wall.note_field_size(7)              # ...and said once, not every lap
    assert len([line for line in caplog.lines if "for a field of" in line]) == 1


def test_the_health_line_reports_the_rosters_merges():
    """Rule 10, and B#7: a merge was neither counted nor logged, so the one
    path that can undo a split never appeared on the line that reports the
    roster's accepts and refusals."""
    roster = Roster()
    wall = PitWall(roster)
    assert "merged 0" in wall.health()
    roster.counts["merged"] += 2
    assert "merged 2" in wall.health()


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


# --- the race news hooks (D7, 14 Sep 2026) ---------------------------------

def test_each_frame_hands_the_race_its_rows_and_our_own_row():
    """Per FRAME, not the sticky `_position`: a car that has left the board
    must not be handed on at the row it last held."""
    boards = []
    wall = a_wall(on_board=lambda rows, own: boards.append((rows, own)))
    warm(wall, Clock())
    assert boards, "no board was handed on"
    # One hand-over per frame our own row was identified on, every row of
    # that frame numbered down the board, and our own row among them. (The
    # synthetic names do not survive clustering as six drivers, so WHICH row
    # is ours is not what this pins - that is `test_the_entry_says_...`.)
    assert len(boards) == FEW + 1
    rows, own = boards[-1]
    assert [row for row, _ in rows] == list(range(1, ROWS + 1))
    assert own in {row for row, _ in rows}


def test_each_gap_reading_is_handed_on_with_whose_it_is(monkeypatch):
    from pitcrew.race import pit_wall as pit_wall_module

    monkeypatch.setattr(pit_wall_module, "read_gaps",
                        lambda frame, board: (2.1, 0.6))
    gaps = []
    wall = a_wall(on_gap=lambda side, gap, who, name: gaps.append(
        (side, gap, who)))
    warm(wall, Clock())
    assert {side for side, _, _ in gaps} == {"ahead", "behind"}
    assert {gap for side, gap, _ in gaps if side == "ahead"} == {2.1}
    # A reading whose neighbour the board could not place says so with None,
    # never a guessed car - and the race keys it on nothing.
    assert len(gaps) == 2 * (FEW + 1)


def test_a_fast_grab_does_not_close_a_stop_in_a_second_and_a_half():
    """**A frame count is not a duration, and the grab rate is his to change.**

    Three clean frames was tuned at the 2 s grab - four to six seconds of a
    car visibly out of his box. At the 0.5 s grab he moved to on 19 Sep 2026
    the same three frames are 1.5 s, and a pit crew washing a disc out behind
    the translucent HUD for under two seconds would close a stop mid-fill.
    """
    from pitcrew.race.pit_wall import CLOSE_AFTER_CLEAN_S

    clock = Clock(step=0.5)                 # the new grab rate
    wall = a_wall()
    warm(wall, clock)
    # A real stop's length: `MIN_WATCHED_S` discards anything shorter as a
    # fragment, so a two-second fill would test that guard and not this one.
    for frame in range(60):                 # 30 s of filling, 19 -> 78 L
        wall.see(a_frame(in_lane=(1,), fuel={1: 19 + frame}),
                 now=clock.tick())
    closed = []
    for _ in range(CLOSE_AFTER_CLEAN_FRAMES):
        closed += wall.see(a_frame(), now=clock.tick())
    assert closed == [], "three frames at 0.5 s is 1.5 s - not a departure"
    # Once the duration is met as well, the stop closes as it always did.
    while clock.now < 60 and not closed:
        closed += wall.see(a_frame(), now=clock.tick())
    assert closed, "the stop must still close once he is genuinely gone"
    assert CLOSE_AFTER_CLEAN_S == 4.0       # three frames at the old 2 s


def test_at_the_old_grab_rate_the_close_is_exactly_what_it_was():
    """4.0 s is what three frames span at 2 s, so nothing changes there."""
    clock = Clock(step=2.0)
    wall = a_wall()
    warm(wall, clock)
    for frame in range(15):                 # 30 s of filling
        wall.see(a_frame(in_lane=(1,), fuel={1: 19 + 4 * frame}),
                 now=clock.tick())
    closed = []
    for _ in range(CLOSE_AFTER_CLEAN_FRAMES):
        closed += wall.see(a_frame(), now=clock.tick())
    assert closed, "three frames at 2 s is still a departure"


def test_a_place_not_read_again_goes_stale():
    """Critic, 19 Sep: `_position` never expired, so a car long gone from the
    rows around us kept the place that chose "Attack." or "Keep fighting."
    for him. The race asks for fresh places only."""
    from pitcrew.race.pit_wall import POSITION_FRESH_S

    first = PitWall()
    first.see(a_frame(), now=100.0)
    ids = first.roster.drivers(min_sightings=1)
    first.roster.label(ids[0], "Rocky")
    wall = PitWall(Roster(seed=first.roster.exemplars()))
    wall.see(a_frame(), now=100.0)
    assert "Rocky" in wall.positions(max_age_s=POSITION_FRESH_S, now=110.0)
    later = 100.0 + POSITION_FRESH_S + 1
    assert "Rocky" not in wall.positions(max_age_s=POSITION_FRESH_S, now=later)
    # The archive's unfiltered view keeps every place it ever read.
    assert "Rocky" in wall.positions()


def test_a_run_of_absent_frames_is_broken_by_a_frame_his_name_did_not_read():
    """Critic, 19 Sep (`interleave.py`): frames where his name did not read
    were skipped with the absent count KEPT, so absences either side of a
    spell of hidden names added up and closed a fill mid-stand. A frame that
    cannot see him now restarts the run."""
    from pitcrew.race.pit_wall import PitWall

    wall = PitWall()
    wall._visits[7] = Visit(driver=7, lap=3, started_s=0.0,
                            readings=[19, 58], last_s=20.0)
    wall._absent[7] = CLOSE_AFTER_CLEAN_FRAMES - 1
    wall._absent_since[7] = 0.0
    wall._row_y[7] = 5000                  # last read far off this board
    # Unread rows elsewhere say nothing about him either.
    wall.see(a_frame(names=False), now=29.0)
    assert wall._absent[7] == CLOSE_AFTER_CLEAN_FRAMES - 1
    # Every row read and he is not among them: off the visible board, which
    # is the normal case just after an exit. The run stands.
    wall.see(a_frame(), now=30.0)
    assert wall._absent[7] == CLOSE_AFTER_CLEAN_FRAMES - 1
    # A frame whose names did not read, one on the row he was last read on:
    # that may be him, still in his box.
    wall._row_y[7] = TOP                   # the first row's centre
    wall.see(a_frame(names=False), now=31.0)
    assert wall._absent.get(7, 0) == 0


# --- compound detection: exit disc vs arrival vote --------------------------
#
# Ground truth from s188 (Sardegna Rd 9, Magical daddy lap 26):
#   - Disc shows H from first frame (t=2758.8) to t=2781.6 (last standing frame)
#   - Disc flips to S at t=2782.0 (the lane exit frame)
#   - At every=3 replay cadence (0.6 s interval starting from t=0), the S frame
#     falls between processed frames: k=13910, 13910 % 3 = 2 → NOT processed.
#   - At every=2 (0.4 s interval), k=13910, 13910 % 2 = 0 → processed.
#   - The current code (left_on logic) correctly returns S when the exit frame
#     IS captured.  The cause of the filed H/H is sampling rate, not logic.


def _visit_with_exit_compound(
        arrivals=("H",), exit_compound="S", *,
        closed_on_absence=True, last_s=20.0, fuel=20,
        left_view=False):
    """Build a Visit whose compounds list ends with exit_compound.

    `arrivals` are the readings during the standing period. `exit_compound`
    is what was read on the last columns frame (the lane exit). `last_s` is
    that frame's timestamp. `fuel` is the reading on the exit frame (sets
    `last_compound_l`) and is also `max(readings)`.
    """
    compounds = list(arrivals) + [exit_compound]
    v = Visit(driver=1, lap=26, started_s=0.0,
              readings=[fuel] * (len(arrivals) + 1),
              compounds=compounds,
              last_s=last_s,
              last_compound_l=fuel,
              last_compound_s=last_s,
              closed_on_absence=closed_on_absence,
              left_view=left_view)
    return v


def test_exit_s_on_h_arrival_is_filed_as_compound_s():
    """H arrivals + S on the last columns frame → compound = S.

    This is the Magical daddy L26 case (s188): arrived on H, the disc flipped
    to S at the lane exit. When the exit frame is processed, the existing
    left_on logic returns S and compound = S.
    """
    v = _visit_with_exit_compound(arrivals=("H",) * 36, exit_compound="S")
    assert v.arrived_on == "H"
    assert v.left_on == "S"
    assert v.compound == "S"
    assert v.compound_changed is True


def test_same_compound_at_exit_is_filed_unchanged():
    """H arrivals + H on the last frame → compound = H (same-compound stop).

    This covers the no-change case: all s188 stops except Magical daddy L26
    were M→M or H→H.  The vote and exit agree → compound = arrived_on.
    """
    v = _visit_with_exit_compound(arrivals=("H",) * 36, exit_compound="H")
    assert v.arrived_on == "H"
    assert v.left_on == "H"
    assert v.compound == "H"
    assert v.compound_changed is None         # same compound: no change seen


def test_m_arrival_m_exit_no_change():
    """Medium compound: M arrivals + M on the last frame → compound = M."""
    v = _visit_with_exit_compound(arrivals=("M",) * 20, exit_compound="M")
    assert v.arrived_on == "M"
    assert v.compound == "M"
    assert v.compound_changed is None


def test_left_view_stop_compound_is_none():
    """CLAUDE.md rule 3: a left_view stop never saw the exit disc flip.

    The disc only changes at the lane exit.  A car that dropped off the visible
    board before the exit was seen has an unknown departure compound.  Returning
    arrived_on here would dress a guess as a measurement.
    """
    v = Visit(driver=1, lap=14, started_s=0.0,
              readings=[22, 30, 45],
              compounds=["M", "M", "M"],
              last_s=30.0,
              last_compound_l=45, last_compound_s=30.0,
              closed_on_absence=False,   # left_view = closed by stale timer
              left_view=True)
    assert v.arrived_on == "M"
    assert v.left_on is None              # not closed on absence
    assert v.compound is None             # rule 3: exit unseen → NULL


def test_left_view_compound_null_even_with_consistent_arrivals():
    """A car on M throughout that left view: compound = None.

    It is tempting to say 'clearly M → M, so compound = M'.  But the disc
    only changes at the exit, and the exit was never seen: he may have come
    back out on any compound.  Rule 3 applies regardless of how many arrival
    reads agreed.
    """
    v = Visit(driver=2, lap=20, started_s=0.0,
              readings=[20, 25, 30],
              compounds=["H"] * 50,      # 50 consistent H reads
              last_s=60.0,
              last_compound_l=30, last_compound_s=60.0,
              closed_on_absence=False,
              left_view=True)
    assert v.arrived_on == "H"
    assert v.compound is None             # rule 3: left view → unknown


def test_as_stop_h_to_s_sets_tyres_changed():
    """Visit.as_stop() sets tyres_changed=True when compound_in != compound.

    This is the Magical daddy L26 ground truth: arrived on H, departed on S.
    The as_stop() method must propagate both values and mark the change.
    """
    v = _visit_with_exit_compound(arrivals=("H",) * 36, exit_compound="S")
    s = v.as_stop()
    assert s.compound_in == "H"
    assert s.compound == "S"
    assert s.tyres_changed is True


def test_as_stop_same_compound_tyres_changed_is_none():
    """Visit.as_stop() leaves tyres_changed as None when no change was seen.

    Same compound at exit: the disc did not flip. Refitted or unchanged
    set — we cannot know. Rule 3: None, not False.
    """
    v = _visit_with_exit_compound(arrivals=("H",) * 36, exit_compound="H")
    s = v.as_stop()
    assert s.compound_in == "H"
    assert s.compound == "H"
    assert s.tyres_changed is None


# --- PitWall.any_visit_open --------------------------------------------------

def test_any_visit_open_false_when_no_visits():
    """No pit columns on any row → any_visit_open is False."""
    wall = a_wall()
    clock = Clock()              # default step=10 s
    warm(wall, clock)
    assert wall.any_visit_open is False


def test_any_visit_open_true_while_car_is_in_lane():
    """any_visit_open flips to True the first time pit columns appear."""
    wall = a_wall()
    clock = Clock()
    warm(wall, clock)

    # Show a car in the lane — this opens a Visit.
    for _ in range(MIN_READS + 1):
        wall.see(a_frame(in_lane=(1,), fuel={1: 40}), now=clock.tick())

    assert wall.any_visit_open is True


def test_any_visit_open_false_after_visit_closes():
    """any_visit_open drops back to False after the visit closes.

    The absence close requires both CLOSE_AFTER_CLEAN_FRAMES AND
    CLOSE_AFTER_CLEAN_S (4 s).  The default Clock step is 10 s so each
    frame advances the clock enough; CLOSE_AFTER_CLEAN_FRAMES+1 clean
    frames exceed both conditions.
    """
    stops = []
    wall = a_wall(on_stop=stops.append)
    clock = Clock()              # step=10 s, satisfies CLOSE_AFTER_CLEAN_S
    warm(wall, clock)

    for _ in range(MIN_READS + 1):
        wall.see(a_frame(in_lane=(1,), fuel={1: 40}), now=clock.tick())
    assert wall.any_visit_open is True

    # Clean board frames → absence close (needs ≥ CLOSE_AFTER_CLEAN_FRAMES
    # clean frames AND ≥ CLOSE_AFTER_CLEAN_S elapsed since first absence).
    for _ in range(CLOSE_AFTER_CLEAN_FRAMES + 1):
        wall.see(a_frame(), now=clock.tick())

    assert wall.any_visit_open is False
    # The stop should be filed (MIN_READS met, MIN_WATCHED_S met at 10s/frame).
    assert len(stops) == 1
