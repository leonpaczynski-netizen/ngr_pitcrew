"""One identity, one car: Bathurst Rd 7 (session 176) replayed off its board.

On 14 Sep 2026 the gap handle "78" stood as "the car ahead" from lap 0 to lap
14 while we went P11 to P7. The recording shows nine drivers in the row above
ours at the moments it was filed under - Corn_flake, Greenmachine 070, X-Man
Oce, BustedGun, A.Maidment, Chook, PUNISHED, K.Graebs, ZenPhilosopher. The
roster's clusters were not the fault: each big cluster held one name. The
fault was `PitWall._neighbour` looking up the car beside us in a STICKY table
of the row every cluster was last seen on, so a cluster parked on the row
above ours answered for everybody who passed through it.

`fixtures/board_identity_s176.npz` is every row the live reader finds on that
race's recording at the live 2 s grab, as the 64x16 bitmap the roster
compares, with a true name per row read at native resolution
(`tools/extract_board_identity_fixture.py` says how, and how it was checked).
Every test here would fail on the code that raced that night, or on a roster
threshold or merge rule moved far enough to put two drivers under one id.
"""
from __future__ import annotations

import collections
import json
from pathlib import Path

import numpy as np
import pytest

from pitcrew.race import pit_wall as pit_wall_module
from pitcrew.race.pit_wall import PitWall
from pitcrew.telemetry.roster import (
    NAME_SHAPE,
    SAME_NAME_MAX_DIFF,
    BoardRow,
    Roster,
    _distance,
)

FIXTURES = Path(__file__).parent / "fixtures"
VIDEO_ZERO_CLOCK_S = 20 * 3600 + 19 * 60 + 14      # 2026-09-14 20-19-14.mp4


def _unpack(packed):
    width, height = NAME_SHAPE
    return np.unpackbits(packed)[:width * height].reshape(height, width) \
        .astype(bool)


@pytest.fixture(scope="module")
def race():
    data = np.load(FIXTURES / "board_identity_s176.npz")
    names = [str(n) for n in data["names"]]
    frames = collections.OrderedDict()
    for second, place, own, packed, label in zip(
            data["second"], data["place"], data["own"], data["bits"],
            data["label"]):
        rows = frames.setdefault(int(second), [])
        bits = None if label == -2 else _unpack(packed)
        truth = names[label] if label >= 0 else None
        rows.append((int(place), bool(own), bits, truth))
    seed = {str(n): _unpack(b)
            for n, b in zip(data["seed_names"], data["seed_bits"])}
    return frames, seed, names


def _place_on_laps():
    """Our lap and race position at each video second, off the race record."""
    comms = json.loads((FIXTURES / "race_comms_s176.json").read_text(
        encoding="utf-8"))
    green_video_s = comms["green_clock_s"] - VIDEO_ZERO_CLOCK_S
    ends = sorted((green_video_s + lap["race_elapsed_s"], lap["lap_num"],
                   lap["position"]) for lap in comms["laps"]
                  if lap["race_elapsed_s"] is not None)

    def at(video_s):
        for end, lap, position in ends:
            if video_s <= end:
                return lap, position
        return None, None
    return at


# --- the distance, on real names -------------------------------------------

def test_two_drivers_on_one_frame_never_measure_inside_the_threshold(race):
    """Measured over every pair of differently-named rows on one frame of
    the race (the only pairs a frame PROVES are two cars): nearest 0.641,
    0.1th percentile 0.687. A threshold above that merges drivers."""
    frames, _, _ = race
    nearest = 1.0
    pairs = 0
    for rows in frames.values():
        named = [(truth, bits) for _, _, bits, truth in rows
                 if truth and bits is not None]
        for i in range(len(named)):
            for j in range(i + 1, len(named)):
                if named[i][0] != named[j][0]:
                    nearest = min(nearest, _distance(named[i][1], named[j][1]))
                    pairs += 1
    assert pairs > 10_000
    assert nearest >= SAME_NAME_MAX_DIFF, (
        f"two different drivers measured {nearest:.3f} apart, inside the "
        f"same-driver threshold {SAME_NAME_MAX_DIFF}")


def test_most_sightings_of_one_driver_are_inside_the_threshold(race):
    """The other side of the same measurement. Same-driver pairs, across the
    race: median 0.233, 95th percentile 0.674 - the 64x16 bitmap moves when
    the reader's band clips a glyph - so about one pair in ten falls outside
    0.58 and a driver can come back as a second cluster. A threshold tightened
    far enough to split most drivers would make every identity a fragment."""
    frames, _, _ = race
    by_name = collections.defaultdict(list)
    for rows in frames.values():
        for _, _, bits, truth in rows:
            if truth and bits is not None:
                by_name[truth].append(bits)
    rng = np.random.default_rng(176)
    inside = total = 0
    for items in by_name.values():
        for _ in range(200):
            a, b = rng.choice(len(items), 2, replace=False)
            inside += _distance(items[a], items[b]) < SAME_NAME_MAX_DIFF
            total += 1
    assert inside / total > 0.85


# --- the roster -------------------------------------------------------------

def _roster_over(frames, seed):
    roster = Roster(seed=seed)
    members = collections.defaultdict(collections.Counter)
    for rows in frames.values():
        ids = roster.see_frame([bits for _, _, bits, _ in rows])
        for (_, _, _, truth), driver in zip(rows, ids):
            if driver is not None and truth:
                members[driver][truth] += 1
    return roster, members


def test_every_established_driver_is_one_car(race):
    """Over the whole race, no cluster seen as often as a driver is - twenty
    times, `pit_wall.MIN_SIGHTINGS` - carries two true names. This is what
    a looser threshold, a merge across clusters seen side by side, or an
    exemplar walked from one name to another would break."""
    frames, seed, _ = race
    roster, members = _roster_over(frames, seed)
    mixed = {}
    for driver, names in members.items():
        resolved = roster._resolve(driver)
        if roster.sightings(resolved) < 20:
            continue
        if len(names) > 1:
            mixed[roster.name_of(resolved) or resolved] = dict(names)
    assert not mixed, f"clusters holding more than one driver: {mixed}"


def test_two_rows_of_one_frame_are_never_one_driver(race):
    """The same real name drawn on two rows of one frame - which no race
    board does - gets two ids, the contest is counted, and the two are never
    merged afterwards however alike they are."""
    frames, _, _ = race
    corn = next(bits for rows in frames.values()
                for _, _, bits, truth in rows if truth == "Corn_flake")
    roster = Roster()
    known = roster.see(corn)
    first, second = roster.see_frame([corn, corn])
    assert known in (first, second)
    assert first is not None and second is not None and first != second
    assert roster.counts["contested"] == 1
    # The contested row founded its own id and did not move the exemplar.
    assert roster.sightings(known) == 2
    for _ in range(5):
        roster.see(corn)
    assert roster._resolve(first) != roster._resolve(second)
    assert roster._merge_converged(second) == roster._resolve(second)


# --- the pit wall: whose gap it is ------------------------------------------

def _replay_wall(frames, seed, monkeypatch):
    """Drive `PitWall.see` over the fixture's rows, with the gap readout
    stubbed to a figure on both sides so every frame asks whose it is."""
    board = (40, 400, 280, 440)
    monkeypatch.setattr(pit_wall_module, "flag_ladder",
                        lambda frame: (250, 275, [0]))
    monkeypatch.setattr(pit_wall_module, "own_row",
                        lambda frame, ladder=None: board)
    monkeypatch.setattr(pit_wall_module, "read_rows",
                        lambda frame, board, ladder: [])
    monkeypatch.setattr(pit_wall_module, "read_gaps",
                        lambda frame, board: (1.0, 1.0))
    monkeypatch.setattr(
        pit_wall_module, "read_rows_of_board",
        lambda frame, board, ladder: [
            BoardRow(y=place * 40, is_own=own, name=bits)
            for place, own, bits, _ in frame])
    heard = []
    wall = PitWall(Roster(seed=seed), on_gap=lambda side, gap, who, name:
                   heard.append((side, who)))
    said = collections.defaultdict(list)
    for second, rows in frames.items():
        before = len(heard)
        wall.see(rows, now=float(second))
        own = next((place for place, is_own, _, _ in rows if is_own), None)
        for side, who in heard[before:]:
            if who is None or own is None:
                continue
            want = own + (-1 if side == "ahead" else 1)
            truth = next((t for place, _, _, t in rows if place == want), None)
            said[(side, who)].append((second, truth))
    return wall, said


def test_the_car_ahead_is_the_car_on_the_row_above(race, monkeypatch):
    """**Session 176 replayed: no identity handed out as the car beside us
    stands for two drivers.** The code that raced gave one id - "78" - the
    row above ours for fifteen laps and nine drivers. Here every id the gap
    hook is handed names one true driver across the whole race, and the car
    ahead while we went from P11 to P7 is the cars that were really there."""
    frames, seed, _ = race
    wall, said = _replay_wall(frames, seed, monkeypatch)
    mixed = {key: dict(collections.Counter(t for _, t in items if t))
             for key, items in said.items()
             if len({t for _, t in items if t}) > 1}
    assert not mixed, f"one identity said as several cars: {mixed}"

    at = _place_on_laps()
    ahead_names = collections.defaultdict(set)
    for (side, who), items in said.items():
        if side != "ahead":
            continue
        for second, truth in items:
            lap, position = at(second)
            if truth and position is not None and 7 <= position <= 11:
                ahead_names[truth].add(position)
    # The field really did pass through that row: the replay has to see it,
    # or the test above proves nothing.
    assert len(ahead_names) >= 6, dict(ahead_names)
    for expected in ("Greenmachine 070", "X-Man Oce", "BustedGun",
                     "Corn_flake", "A.Maidment"):
        assert expected in ahead_names


def test_a_car_long_gone_from_the_board_is_not_the_car_beside_us(monkeypatch):
    """The sticky-table failure in miniature. A driver seen once on the row
    above ours and never again must not be handed the gap when that row
    later holds somebody the roster cannot read."""
    a = np.zeros((16, 64), bool)
    a[2:14, 0:30] = True
    b = np.zeros((16, 64), bool)
    b[2:14, 34:64] = True
    own = np.zeros((16, 64), bool)
    own[0:4, :] = True
    frames = collections.OrderedDict()
    frames[0] = [(1, False, a, "A"), (2, True, own, "us")]
    frames[2] = [(1, False, None, None), (2, True, own, "us")]
    frames[4] = [(1, False, b, "B"), (2, True, own, "us")]
    _, said = _replay_wall(frames, {}, monkeypatch)
    ahead = {second: truth for (side, _), items in said.items()
             if side == "ahead" for second, truth in items}
    assert ahead == {0: "A", 4: "B"}, ahead
