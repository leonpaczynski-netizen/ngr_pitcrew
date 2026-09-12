"""Who was around him: storage, and the one number that must not be invented.

The feed carries a car count and nothing else, so this is the first channel
the app has ever had about anybody but the driver. Two things are worth
protecting: a re-read must replace rather than accumulate, and the metre
figure must stop where the calibration does.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from pitcrew.store.db import Store

TOOL = Path(__file__).resolve().parents[2] / "tools" / "read_replay_traffic.py"


def _tool():
    spec = importlib.util.spec_from_file_location("read_replay_traffic", TOOL)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def contact(**kw) -> dict:
    base = dict(lap_id=None, lap_num=3, video_s=120.0, side="behind",
                ribbon_px=7.0, near_m=23.8, rival_position=6,
                source="replay-radar")
    base.update(kw)
    return base


# ------------------------------------------------------------------ storage

def test_contacts_round_trip(store: Store):
    session = store.start_session(store.create_event(name="e", track="Fuji Speedway",
                                       layout="Full Course"), "race")
    store.record_traffic(session, [contact(), contact(video_s=124.0)])
    rows = store.list_traffic(session)
    assert len(rows) == 2
    assert rows[0]["side"] == "behind"
    assert rows[0]["ribbon_px"] == 7.0
    assert rows[0]["source"] == "replay-radar"


def test_a_re_read_replaces_rather_than_accumulates(store: Store):
    """The same capture read at a finer interval is a better answer to the
    same question, not a second set of cars."""
    session = store.start_session(store.create_event(name="e", track="Fuji Speedway",
                                       layout="Full Course"), "race")
    store.record_traffic(session, [contact(), contact(video_s=124.0)])
    store.record_traffic(session, [contact(video_s=121.0)])
    rows = store.list_traffic(session)
    assert len(rows) == 1
    assert rows[0]["video_s"] == 121.0


def test_an_unplaced_contact_is_stored_as_a_car_with_no_distance(store: Store):
    """A car the flood fill could not reach is still a car.

    Dropping it would make "no traffic" mean "the mask failed", which is the
    reading that gets a driver told he was alone when he was not.
    """
    session = store.start_session(store.create_event(name="e", track="Fuji Speedway",
                                       layout="Full Course"), "race")
    store.record_traffic(session, [contact(side=None, ribbon_px=None,
                                           near_m=None, rival_position=None)])
    row = store.list_traffic(session)[0]
    assert row["side"] is None
    assert row["ribbon_px"] is None
    assert row["near_m"] is None


# ------------------------------------------- the metre figure, and its limit

def test_metres_stop_where_the_calibration_does():
    """**The radar is a perspective projection.** Fitted against his own path,
    the near field wants about 3.4 m/px and points 100-200 m out want 8 or
    more - so one scale applied at range would be a number this tool invented.
    """
    tool = _tool()
    assert tool.NEAR_FIELD_PX > 0
    inside = tool.NEAR_FIELD_PX - 1
    outside = tool.NEAR_FIELD_PX + 1
    assert round(inside * tool.NEAR_M_PER_PX, 1) > 0
    # The rule itself, as `contacts` applies it.
    assert (inside <= tool.NEAR_FIELD_PX) is True
    assert (outside <= tool.NEAR_FIELD_PX) is False


def test_the_near_scale_carries_its_spread():
    """Printed with the figure, so it is never read to a precision it has
    not got: the three near-field fits were 2.80, 3.35 and 3.95 m/px."""
    tool = _tool()
    assert tool.NEAR_M_PER_PX_SPREAD > 0
    low = tool.NEAR_M_PER_PX - tool.NEAR_M_PER_PX_SPREAD
    high = tool.NEAR_M_PER_PX + tool.NEAR_M_PER_PX_SPREAD
    assert low <= 2.8 + 0.01 and high >= 3.95 - 0.01


# --------------------------------------------------- the side, at the seed

def test_the_side_is_decided_at_the_crosshair_not_at_the_contact():
    """On a hairpin the road ahead is drawn BELOW the car, so any rule reading
    the sign off a contact's own coordinates gets it backwards exactly where
    traffic matters most."""
    numpy = pytest.importorskip("numpy")
    tool = _tool()
    # A ribbon that leaves the crosshair upward and immediately doubles back,
    # so a point on the "ahead" branch ends up below the seed.
    passable = numpy.zeros((21, 21), dtype=bool)
    passable[10, 10] = True
    for y in range(4, 11):
        passable[y, 10] = True          # ahead: straight up
    for x in range(10, 16):
        passable[4, x] = True           # ...then across
    for y in range(4, 17):
        passable[y, 15] = True          # ...and back down, below the seed
    for y in range(10, 17):
        passable[y, 10] = True          # behind: straight down
    distance, label = tool.branches(passable, (10, 10))
    assert label[16, 15] == 1, "doubled back but still the road ahead"
    assert label[16, 10] == -1, "straight down is the road behind"

# ------------------------------------------------- naming the car, not the box

def _board():
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "read_replay_board",
        Path(__file__).resolve().parents[2] / "tools" / "read_replay_board.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_same_name_clusters_and_a_different_one_does_not():
    """GT7 renders one font at one size, so the same name is the same bitmap.

    Exact where OCR would be probabilistic - and there is no OCR engine on
    this machine to be probabilistic with.
    """
    numpy = pytest.importorskip("numpy")
    board = _board()
    a = numpy.zeros((16, 64), dtype=bool)
    a[4:12, 8:40] = True
    b = a.copy()
    b[5, 9] = False                      # one pixel of rendering noise
    c = numpy.zeros((16, 64), dtype=bool)
    c[2:14, 20:60] = True                # a different name
    groups = board.cluster([(("t1", "ahead"), a), (("t2", "ahead"), b),
                            (("t3", "behind"), c)])
    assert len(groups) == 2
    assert len(groups[0]["seen"]) == 2


def test_an_unreadable_cluster_has_a_way_to_say_so():
    """The board reorders between frames and a sample caught mid-reorder has
    two names over each other. Guessing puts a driver on a car that was never
    there; leaving it blank blocks every other contact."""
    board = _board()
    assert board.UNREADABLE
    assert board.UNREADABLE != ""


def test_a_name_is_never_carried_further_than_the_board_was_read():
    """Beyond one sampling interval the order may have changed in between,
    and a name carried across a pass names the wrong driver."""
    store_module = _board()
    # **The bound is the sampling interval, whatever it was set to** — not a
    # tolerance of its own that could outlive the sampling. This used to grep
    # `main` for the literal `best[0] <= args.every`, which is a pin on the
    # prose: the guard was rewritten as `best[0] > args.every: continue`, the
    # property unchanged, and the test failed anyway.
    import inspect
    source = inspect.getsource(store_module.main)
    assert "args.every" in source, "the join no longer references the interval"
    joined = [line for line in source.splitlines()
              if "best[0]" in line and "args.every" in line]
    assert joined, "no comparison of the match distance against the interval"
    # And an unreadable reading must not be replaced by a readable neighbour.
    assert "best[1] is None" in source, (
        "a contact whose nearest reading was marked unreadable must stay "
        "unnamed rather than inherit the next name within the interval")


# ------------------------------------------- finding the radar, not assuming it

def _traffic():
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "read_replay_traffic",
        Path(__file__).resolve().parents[2] / "tools" / "read_replay_traffic.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _red_blob(numpy, pixels, cx, cy, w, h):
    """Draw a red rectangle centred on (cx, cy).

    Odd sizes only where the test asserts the centre back: an even-height
    block has no integer centre and the half-pixel comes back as an off-by-one
    that looks like a tool defect and is not one.
    """
    pixels[cy - h // 2:cy + h // 2 + 1, cx - w // 2:cx + w // 2 + 1] = (200, 30, 30)


def test_the_radar_box_keeps_the_offsets_the_old_geometry_had():
    """The widget did not change size when it moved — only where it sits. So
    the box around a found marker is the old box's own offsets."""
    tool = _traffic()
    assert tool.radar_box(tool.OWN_XY) == tool.RADAR


def test_the_own_marker_is_found_by_shape_and_place():
    """A small upright red blob near y 907. Measured 6-15 x 5-14 px."""
    numpy = pytest.importorskip("numpy")
    tool = _traffic()
    pixels = numpy.zeros((1080, 1920, 3), dtype=numpy.uint8) + 20
    _red_blob(numpy, pixels, 960, 907, 7, 13)
    assert tool.find_own_marker(pixels) == (960, 907)


def test_the_rev_counter_and_the_gear_are_not_the_marker():
    """Both are red and both live in the same band. The rev counter measured
    38x80 at y 951-959 and the gear number 40x150 at y 915 — it was the gear
    number's edge that once put the radar four hundred pixels away."""
    numpy = pytest.importorskip("numpy")
    tool = _traffic()
    pixels = numpy.zeros((1080, 1920, 3), dtype=numpy.uint8) + 20
    _red_blob(numpy, pixels, 1164, 915, 40, 150)      # the gear number
    _red_blob(numpy, pixels, 1377, 955, 38, 80)       # the rev counter
    assert tool.find_own_marker(pixels) is None


def test_a_flat_bar_beside_the_marker_is_not_the_marker():
    """Measured at y 902, 15 px wide and 6 tall — the one red thing close
    enough in y to matter, and twice as wide as tall where the marker at its
    flattest was 6x5."""
    numpy = pytest.importorskip("numpy")
    tool = _traffic()
    pixels = numpy.zeros((1080, 1920, 3), dtype=numpy.uint8) + 20
    _red_blob(numpy, pixels, 789, 902, 15, 6)
    assert tool.find_own_marker(pixels) is None


def test_the_tyre_pips_sit_below_the_band():
    """12-14 px wide and as tall, so shape alone will not separate them —
    their y is what does. Measured at 961-968 against the marker's 907-910."""
    numpy = pytest.importorskip("numpy")
    tool = _traffic()
    pixels = numpy.zeros((1080, 1920, 3), dtype=numpy.uint8) + 20
    _red_blob(numpy, pixels, 392, 965, 14, 12)
    _red_blob(numpy, pixels, 476, 967, 14, 15)
    assert tool.find_own_marker(pixels) is None


def test_a_capture_with_no_radar_is_refused_not_guessed():
    """The legacy box belongs to a HUD layout that is not recorded any more.
    Falling back to it puts the search on bare tarmac and reports an empty
    race — which is what happened, silently, for a whole league round."""
    from pathlib import Path as _P
    tool = _traffic()
    with pytest.raises(SystemExit) as raised:
        tool.locate_radar(_P("no-such-capture.mp4"), 0.0, 100.0,
                          _P("no-such-frame.png"), None)
    assert "radar" in str(raised.value).lower()


def test_an_explicit_radar_x_is_taken_as_given():
    tool = _traffic()
    from pathlib import Path as _P
    assert tool.locate_radar(_P("x.mp4"), 0.0, 1.0, _P("y.png"), 961) == (
        961, tool.OWN_XY[1])


# --------------------------------- the board's reading, kept in its own right

def _sighting(**kw) -> dict:
    base = dict(lap_id=None, lap_num=4, video_s=200.0, side="ahead",
                driver="K.Graebs", source="replay-board")
    base.update(kw)
    return base


_RACES = [0]


def _race(store: Store) -> int:
    """A race session under its own event — `events.name` is UNIQUE, so a
    test needing two races cannot reuse one name."""
    _RACES[0] += 1
    return store.start_session(
        store.create_event(name=f"e{_RACES[0]}", track="Fuji Speedway",
                           layout="Full Course"), "race")


def test_board_sightings_round_trip(store: Store):
    session = _race(store)
    store.record_board_sightings(session, [
        _sighting(), _sighting(video_s=204.0, side="behind", driver="Rocky")])
    rows = store.list_board_sightings(session)
    assert [(r["side"], r["driver"]) for r in rows] == [
        ("ahead", "K.Graebs"), ("behind", "Rocky")]
    assert rows[0]["source"] == "replay-board"


def test_a_re_read_of_the_board_replaces_rather_than_accumulates(store: Store):
    """The same capture read again is a better answer to the same question,
    not a second set of cars."""
    session = _race(store)
    store.record_board_sightings(session, [_sighting(), _sighting(video_s=8.0)])
    store.record_board_sightings(session, [_sighting(video_s=12.0)])
    rows = store.list_board_sightings(session)
    assert len(rows) == 1 and rows[0]["video_s"] == 12.0


def test_an_unreadable_sighting_is_filed_with_no_driver(store: Store):
    """Two rows drawn over each other mid-reorder is a fact about the capture.

    Dropping those rows would make "nobody was there" and "the board could not
    be read" the same answer — the reading that gets a driver told he was
    alone when he was not.
    """
    session = _race(store)
    store.record_board_sightings(session, [_sighting(driver=None)])
    row = store.list_board_sightings(session)[0]
    assert row["driver"] is None
    assert row["side"] == "ahead", "the side is known even when the name is not"


def test_a_sighting_outside_the_counted_laps_keeps_a_null_lap(store: Store):
    """The formation lap, or a replay running past the flag. It happened; it
    did not happen on a lap, and saying it did puts a car beside him on a lap
    he was not on."""
    session = _race(store)
    store.record_board_sightings(session, [_sighting(lap_num=None)])
    assert store.list_board_sightings(session)[0]["lap_num"] is None


def test_tendencies_read_the_board_in_preference_to_the_radar(store: Store):
    """The radar sees about a second each way and only while that page is up:
    595 samples of the Daytona league race gave 2 contacts, neither placeable,
    against 1,096 board readings of the same capture."""
    from pitcrew.analysis.rivals import tendencies
    session = _race(store)
    store.record_traffic(session, [
        contact(lap_num=lap, rival="PUNISHED", side="behind")
        for lap in (1, 2, 3, 4)])
    store.record_board_sightings(session, [
        _sighting(lap_num=lap, driver="CruisingChaos", side="ahead")
        for lap in (1, 2, 3, 4, 5)])
    found = tendencies(store, session)
    assert [one.name for one in found] == ["CruisingChaos"], (
        "the radar's answer was preferred over the board's")
    assert found[0].laps_together == 5


def test_tendencies_still_read_the_radar_where_no_board_pass_was_run(store: Store):
    """The sessions already in the archive were named this way and must keep
    answering."""
    from pitcrew.analysis.rivals import tendencies
    session = _race(store)
    store.record_traffic(session, [
        contact(lap_num=lap, side="behind") for lap in (1, 2, 3, 4)])
    # `record_traffic` does not write the name — the board pass applies it
    # afterwards, one contact at a time, which is the whole point of it being
    # operator-assisted.
    for row in store.list_traffic(session):
        store.name_traffic(row["id"], "TommyTbone")
    found = tendencies(store, session)
    assert [one.name for one in found] == ["TommyTbone"]


def test_which_side_he_was_on_is_not_reversible(store: Store):
    """**"Mostly ahead" and "mostly behind" are opposite driving**, and the
    two counts can be swapped in one expression with nothing to say so."""
    from pitcrew.analysis.rivals import tendencies

    session = _race(store)
    store.record_board_sightings(session, [
        _sighting(lap_num=lap, side="ahead", driver="CruisingChaos")
        for lap in range(1, 9)])
    one = tendencies(store, session)[0]
    assert one.laps_ahead == 8 and one.laps_behind == 0
    assert one.mostly == "ahead"
    assert "mostly ahead" in one.describe()


def test_the_tendency_carries_the_instrument_that_read_it(store: Store):
    """Three laps off the board and three off the radar describe different
    races; rendered identically nobody can tell which they are looking at."""
    from pitcrew.analysis.rivals import tendencies

    session = _race(store)
    store.record_board_sightings(session, [
        _sighting(lap_num=lap, driver="Rocky") for lap in (1, 2, 3, 4)])
    assert tendencies(store, session)[0].source == "board"

    other = _race(store)
    store.record_traffic(other, [
        contact(lap_num=lap, side="behind") for lap in (1, 2, 3, 4)])
    for row in store.list_traffic(other):
        store.name_traffic(row["id"], "PUNISHED")
    assert tendencies(store, other)[0].source == "radar"


def test_a_side_the_board_never_writes_is_counted_as_unknown(store: Store):
    """It used to `setdefault` any string into the map, so a stray value made
    a rival vanish entirely rather than count as a lap together."""
    from pitcrew.analysis.rivals import tendencies

    session = _race(store)
    store.record_board_sightings(session, [
        _sighting(lap_num=lap, side="alongside", driver="Jubby")
        for lap in (1, 2, 3, 4)])
    found = tendencies(store, session)
    assert [one.name for one in found] == ["Jubby"]
    assert found[0].laps_together == 4
    assert found[0].mostly == "either side"
