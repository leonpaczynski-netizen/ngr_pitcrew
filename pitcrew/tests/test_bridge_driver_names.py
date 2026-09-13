"""Carrying replay-board names onto the live pit wall's `Car #N` drivers.

`tools/bridge_driver_names.py` pairs the two readers on the same frame and the
same row, and renames a live driver only when nearly every pairing agrees. The
failure that matters is a WRONG name on a car, so most of what is pinned here
is refusal: a split vote, too few votes, a row nobody labelled.
"""
from __future__ import annotations

import importlib.util
import json
import sqlite3
import sys
from pathlib import Path

import numpy as np
import pytest

from pitcrew.store.db import Store
from pitcrew.telemetry.roster import BoardRow, Roster

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def bridge():
    spec = importlib.util.spec_from_file_location(
        "bridge_driver_names", ROOT / "tools" / "bridge_driver_names.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["bridge_driver_names"] = module
    spec.loader.exec_module(module)
    return module


def bits(seed: int, noise: float = 0.0):
    """A name bitmap. Different seeds are far apart under both distances."""
    rng = np.random.default_rng(seed)
    out = rng.random((16, 64)) > 0.6
    if noise:
        out = out ^ (np.random.default_rng(seed + 1000).random((16, 64)) < noise)
    return out


def live_row(y, seed, own=False):
    return BoardRow(y=y, is_own=own, name=bits(seed))


def replay_row(y, seed, side="ahead"):
    return (side, y, bits(seed + 500), None)


# ------------------------------------------------------------------ pairing

def test_rows_pair_on_the_same_y_and_nothing_else(bridge):
    live = [live_row(200, 1), live_row(240, 2), live_row(280, 3, own=True)]
    rep = [replay_row(241, 2), replay_row(330, 9)]
    pairs = bridge.pair_rows(live, rep)
    assert len(pairs) == 1
    assert pairs[0][0].y == 240 and pairs[0][1][1] == 241


def test_the_own_row_is_never_paired(bridge):
    """The replay reader never reads his own row; a pairing there would be a
    neighbour's name on the driver himself."""
    assert bridge.pair_rows([live_row(280, 3, own=True)],
                            [replay_row(280, 3)]) == []


def test_a_replay_row_with_two_live_rows_in_reach_is_dropped(bridge):
    live = [live_row(240, 1), live_row(244, 2)]
    assert bridge.pair_rows(live, [replay_row(242, 1)], tol=6) == []


def test_votes_follow_the_row_on_its_own_frame_not_its_position(bridge):
    """Two cars swap places between frames. Each vote must go to the live
    driver on THAT frame's row, or a pass hands both names to both cars."""
    roster = Roster(seed={"Car #1": bits(1), "Car #2": bits(2)})
    labels = [(bits(501), "Rocky"), (bits(502), "PUNISHED")]
    frames = [
        ([live_row(240, 1), live_row(280, 2)],
         [replay_row(240, 1), replay_row(280, 2, "behind")]),
        ([live_row(240, 2), live_row(280, 1)],
         [replay_row(240, 2), replay_row(280, 1, "behind")]),
    ]
    votes = bridge.Votes()
    for live, rep in frames:
        votes.see(None, roster, labels,
                  live=lambda _f, rows=live: rows,
                  rep=lambda _f, rows=rep: rows)
    assert votes.by_driver["Car #1"] == {"Rocky": 2}
    assert votes.by_driver["Car #2"] == {"PUNISHED": 2}


def test_a_cluster_minted_during_the_walk_gets_no_vote(bridge):
    roster = Roster(seed={"Car #1": bits(1)})
    votes = bridge.Votes()
    votes.see(None, roster, [(bits(507), "Rocky")],
              live=lambda _f: [live_row(240, 7)],
              rep=lambda _f: [replay_row(240, 7)])
    assert votes.minted == 1 and not votes.by_driver


def test_a_replay_crop_near_two_different_names_is_not_a_vote(bridge):
    a = np.zeros((16, 64), dtype=bool)
    b = a.copy()
    b.reshape(-1)[:40] = True
    c = a.copy()
    c.reshape(-1)[40:80] = True
    assert bridge.name_of_replay(a, [(b, "Rocky"), (c, "J.Jonas")]) == \
        bridge.AMBIGUOUS
    assert bridge.name_of_replay(a, [(b, "Rocky")]) == "Rocky"
    assert bridge.name_of_replay(bits(3), [(bits(4), "Rocky")]) == \
        bridge.UNMATCHED


# ----------------------------------------------------------------- deciding

def votes_of(bridge, **per_driver):
    votes = bridge.Votes()
    for driver, names in per_driver.items():
        votes.by_driver[driver.replace("_", " #")].update(names)
    return votes


def test_a_split_cluster_is_never_named(bridge):
    """A live cluster whose rows read as two drivers is two drivers merged.
    Naming it after either puts a name on the other's car."""
    [v] = bridge.decide(votes_of(bridge, Car_3={"Rocky": 16, "K.Graebs": 4}))
    assert not v.rename and "split" in v.why
    assert bridge.renames([v]) == []


def test_a_unanimous_cluster_with_enough_pairs_is_named(bridge):
    [v] = bridge.decide(votes_of(bridge, Car_3={"Rocky": 19, "K.Graebs": 1}))
    assert v.rename and bridge.renames([v]) == [("Car #3", "Rocky")]


def test_too_few_pairings_refuse_even_when_unanimous(bridge):
    [v] = bridge.decide(votes_of(bridge, Car_3={"Rocky": bridge.MIN_PAIRS - 1}))
    assert not v.rename


def test_rows_nobody_labelled_count_against_the_share(bridge):
    """Half a cluster being somebody with no name on file is still a merge."""
    [v] = bridge.decide(votes_of(
        bridge, Car_3={"Rocky": 12, bridge.UNMATCHED: 8}))
    assert not v.rename


def test_an_already_named_driver_is_not_renamed(bridge):
    votes = bridge.Votes()
    votes.by_driver["Rocky"].update({"K.Graebs": 20})
    [v] = bridge.decide(votes)
    assert not v.rename and "already named" in v.why


def test_renames_run_most_paired_first(bridge):
    """`rename_driver` merges by deleting the later row, so the first rename
    decides whose exemplar seeds tomorrow."""
    verdicts = bridge.decide(votes_of(
        bridge, Car_9={"Rocky": 10}, Car_2={"Rocky": 40}))
    assert bridge.renames(verdicts) == [("Car #2", "Rocky"),
                                        ("Car #9", "Rocky")]


# ----------------------------------------------------------- labels on disk

def test_labels_decode_from_the_exemplar_png_and_check_the_fingerprint(
        bridge, tmp_path):
    from PIL import Image
    good, bad = bits(11), bits(12)
    for name, arr in (("good.png", good), ("bad.png", bad)):
        Image.fromarray((arr * 255).astype("uint8")).resize(
            (256, 64), Image.NEAREST).save(tmp_path / name)
    roster = {
        "0": {"name": "Rocky", "fingerprint": bridge.replay.fingerprint(good),
              "exemplar_do_not_read": "good.png"},
        "1": {"name": "J.Jonas", "fingerprint": "000000000000",
              "exemplar_do_not_read": "bad.png"},
        "2": {"name": "-", "exemplar_do_not_read": "good.png"},
    }
    path = tmp_path / "roster-session-1.json"
    path.write_text(json.dumps(roster), encoding="utf-8")
    labels = bridge.replay_labels(path)
    assert [name for _, name in labels] == ["Rocky"]
    assert (labels[0][0] == good).all()


# ------------------------------------------------------------ dry run, apply

@pytest.fixture
def walk(bridge, tmp_path, monkeypatch):
    """A tiny archive, a roster, and a 'video' of twelve identical frames in
    which Car #1's row reads as Rocky."""
    from PIL import Image
    db = tmp_path / "pitcrew.db"
    store = Store(db)
    store.save_driver("Car #1", bits(1))
    store.save_driver("Car #2", bits(2))
    store.record_rival_stop(None, "Car #1", lap=5, fuel_in_l=10.0)
    store.close()
    Image.fromarray((bits(501) * 255).astype("uint8")).resize(
        (256, 64), Image.NEAREST).save(tmp_path / "rocky.png")
    roster = tmp_path / "roster.json"
    roster.write_text(json.dumps({"0": {
        "name": "Rocky", "exemplar_do_not_read": "rocky.png"}}),
        encoding="utf-8")
    video = tmp_path / "race.mp4"
    video.write_bytes(b"")
    frames = iter(range(12))
    monkeypatch.setattr(bridge, "frame_at",
                        lambda _v, _s: next(frames, None))
    monkeypatch.setattr(bridge, "live_read", lambda _f: [live_row(240, 1)])
    monkeypatch.setattr(bridge, "replay_read",
                        lambda _f: [replay_row(240, 1)])
    return db, ["--session", "1", "--db", str(db), "--roster", str(roster),
                "--video", str(video)]


def drivers_in(db):
    conn = sqlite3.connect(db)
    try:
        return sorted(r[0] for r in conn.execute("SELECT name FROM drivers"))
    finally:
        conn.close()


def test_a_dry_run_writes_nothing(bridge, walk, capsys):
    db, argv = walk
    before = db.read_bytes()
    assert bridge.main(argv) == 0
    assert "rename_driver('Car #1', 'Rocky')" in capsys.readouterr().out
    assert db.read_bytes() == before
    assert drivers_in(db) == ["Car #1", "Car #2"]
    assert not list(db.parent.glob("*before-bridge-names*"))


def test_apply_backs_up_and_goes_through_rename_driver(
        bridge, walk, monkeypatch):
    db, argv = walk
    calls = []
    real = Store.rename_driver

    def spy(self, old, new):
        calls.append((old, new))
        return real(self, old, new)

    monkeypatch.setattr(Store, "rename_driver", spy)
    assert bridge.main(argv + ["--apply"]) == 0
    assert calls == [("Car #1", "Rocky")]
    assert drivers_in(db) == ["Car #2", "Rocky"]
    [backup] = list(db.parent.glob("*before-bridge-names*"))
    assert drivers_in(backup) == ["Car #1", "Car #2"]
    store = Store(db)
    assert [s["driver"] for s in store.rival_stops()] == ["Rocky"]
