"""Who he races here, read off the replay after the race - never during one.

Live rival vision in VR is refused on evidence. GT7 draws its HUD on the car's
dashboard in 3D, so it moves with head position; the *wear gauge*, which is
larger and higher contrast than the radar, reads 6 crossings in 22. And the two
are not the same problem: wear changes slowly so occasional samples suffice,
while **rival proximity changes in a second**, so occasional samples of it are
no signal at all.

So rivals moved from perception to memory. These are the tests for the reading
after the race and for the thing that made it routine - the offset nobody has
to type any more.
"""
from __future__ import annotations

import pytest

from pitcrew.analysis import rivals
from pitcrew.analysis.rivals import MIN_LAPS_TOGETHER, Rival, tendencies


class FakeStore:
    def __init__(self, rows):
        self._rows = rows

    def list_traffic(self, session_id):
        return self._rows


def a_row(rival, side, lap):
    return {"rival": rival, "side": side, "lap_num": lap}


def rows_for(rival, side, laps):
    return [a_row(rival, side, lap) for lap in laps]


# --- what a tendency is -----------------------------------------------------

def test_a_rival_he_spent_a_race_beside_is_named():
    store = FakeStore(rows_for("TommyTbone", "behind", range(1, 10)))
    found = tendencies(store, 1)

    assert [one.name for one in found] == ["TommyTbone"]
    assert found[0].laps_together == 9
    assert "mostly behind" in found[0].describe()


def test_one_overtake_is_not_a_tendency():
    """Every race has one. None of them is a fact about the next race."""
    store = FakeStore(rows_for("Chook", "ahead",
                               range(1, MIN_LAPS_TOGETHER)))
    assert tendencies(store, 1) == []


def test_both_sides_is_said_when_it_was_both_sides():
    store = FakeStore(rows_for("Corn_flake", "ahead", [1, 2, 3])
                      + rows_for("Corn_flake", "behind", [4, 5, 6]))
    assert "both sides" in tendencies(store, 1)[0].describe()


def test_the_same_lap_seen_twice_counts_once():
    """The radar is sampled every few seconds; a rival sitting beside him for
    a whole lap is one lap of racing, not fifteen."""
    store = FakeStore(rows_for("TommyTbone", "behind", [1, 1, 1, 2, 2, 3]))
    assert tendencies(store, 1)[0].laps_together == 3


def test_unnamed_rows_are_skipped_and_never_lumped_together():
    """**The board pass supplies names and it is a separate step.** A traffic
    pass run on its own leaves most rows unnamed, and treating them as one
    driver would report a phantom who was everywhere."""
    store = FakeStore(rows_for(None, "ahead", range(1, 20))
                      + rows_for("PUNISHED", "behind", [1, 2, 3, 4]))
    assert [one.name for one in tendencies(store, 1)] == ["PUNISHED"]


def test_they_come_back_in_order_of_time_spent_together():
    store = FakeStore(rows_for("A", "behind", [1, 2, 3])
                      + rows_for("B", "behind", range(1, 12)))
    assert [one.name for one in tendencies(store, 1)] == ["B", "A"]


def test_no_distance_is_ever_reported():
    """`read_replay_traffic` is deliberate that the radar's distance is in
    ribbon pixels and not metres, because the ribbon narrows toward its ends.
    A tendency that quoted a gap would be one this layer invented."""
    record = Rival("TommyTbone", 1, 8, 9).as_record()
    assert set(record) == {"rival", "tendency"}
    assert "m" not in record["tendency"].split()


# --- the offset nobody has to type any more ---------------------------------

def test_the_offset_is_derived_where_the_app_started_the_recording():
    """**The thing standing between "run it after every race" and "run it when
    somebody has ten minutes."** `video_index.build` existed from the day it
    was written and was called from one test file and nothing else."""
    from pitcrew.race.video_index import offset_for
    from pitcrew.store.db import Store

    store = Store()
    try:
        # Session 84 is a practice run the app recorded itself.
        assert offset_for(store, 84) == pytest.approx(153.0, abs=1.0)
    finally:
        store.close()


def test_a_capture_the_app_did_not_start_has_no_derivable_offset():
    """Guessing one would seek to the wrong lap in silence. `--offset` stays
    the way in for a recording made by hand."""
    from pitcrew.race.video_index import offset_for
    from pitcrew.store.db import Store

    store = Store()
    try:
        assert offset_for(store, 49) is None
    finally:
        store.close()


# --- the briefing, and the shadowing bug ------------------------------------

def test_a_race_s_rivals_do_not_shadow_the_circuit_s_wear_rates(tmp_path):
    """**A defect this shipped with for about an hour.**

    "The event's record wins" has to mean field by field. Row by row, the
    first traffic pass to write rivals wiped every wear rate on that circuit
    out of George's view, and he went back to modelling wear with nothing
    saying so.
    """
    from pitcrew.race.knowledge import Knowledge
    from pitcrew.store.db import Store

    store = Store(tmp_path / "t.db")
    try:
        key = "fuji-international-speedway-full-course"
        # The event has to exist: `race_knowledge.event_id` is a foreign key,
        # which is what stops a briefing outliving the race it describes.
        event_id = store.create_event(name="r", track="Fuji International "
                                      "Speedway", layout="Full Course",
                                      car_name="x")
        store.save_race_knowledge(Knowledge(
            circuit_key=key, pit_loss_s=18.0,
            wear_rates={"RS": {"perLap": 0.037, "samples": 2}}))
        store.save_race_knowledge(Knowledge(
            circuit_key=key, event_id=event_id,
            rivals=({"rival": "TommyTbone", "tendency": "mostly behind"},)))

        merged = store.get_race_knowledge(key, event_id)

        assert merged.rivals[0]["rival"] == "TommyTbone"
        assert merged.wear_rates["RS"]["perLap"] == 0.037, \
            "the circuit's measured wear survived the race's own record"
        assert merged.pit_loss_s == 18.0
        assert merged.event_id == event_id
    finally:
        store.close()


def test_the_event_still_overrides_a_field_it_actually_sets(tmp_path):
    from pitcrew.race.knowledge import Knowledge
    from pitcrew.store.db import Store

    store = Store(tmp_path / "t.db")
    try:
        event_id = store.create_event(name="r", track="t", car_name="x")
        store.save_race_knowledge(Knowledge(circuit_key="x", pit_loss_s=20.0))
        store.save_race_knowledge(Knowledge(circuit_key="x", event_id=event_id,
                                            pit_loss_s=15.7))
        assert store.get_race_knowledge("x", event_id).pit_loss_s == 15.7
    finally:
        store.close()


def test_the_archive_s_own_rivals_come_back(tmp_path):
    """Fuji, session 88 - the only race with a traffic pass on file."""
    from pitcrew.store.db import Store

    store = Store()
    try:
        found = rivals.tendencies(store, 88)
    finally:
        store.close()
    assert [one.name for one in found[:2]] == ["TommyTbone", "Corn_flake"]
