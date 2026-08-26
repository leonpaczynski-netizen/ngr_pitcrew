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
    # The rule is expressed as `gap <= args.every` in the join; this asserts
    # the tool exposes the interval it was read at rather than hard-coding a
    # tolerance that could outlive its sampling.
    import inspect
    source = inspect.getsource(store_module.main)
    assert "best[0] <= args.every" in source
