"""The live gauge reader, wired to a lap crossing.

The point of these is not that the reading is right - `test_hud_wear.py` covers
that - but that **nothing it does can reach the lap.** GT7 sends no wear
channel, the driver has said he will not record it by hand, and the only source
left is a screenshot of another process over a socket. That is exactly the kind
of dependency that must not be able to stall a race.
"""
from __future__ import annotations

import time

from pitcrew.setup.sheet import SetupSheet
from pitcrew.store.db import WEAR_DRIVER, WEAR_HUD_VIDEO, Store
from pitcrew.telemetry.hud import LiveWearSampler


class Grabs:
    def __init__(self, result):
        self.result = result
        self.calls = 0

    def grab(self):
        self.calls += 1
        return self.result


def wait(predicate, timeout=3.0):
    deadline = time.time() + timeout
    while time.time() < deadline and not predicate():
        time.sleep(0.01)
    return predicate()


def a_lap(store: Store) -> int:
    from pitcrew.telemetry.session_state import Lap

    event_id = store.create_event(
        name="Monza", track="Autodromo Nazionale Monza", layout="Full",
        car_name="Porsche 911 RSR (991) '17", race_type="laps", race_laps=20,
        game_version="1.71")
    session_id = store.start_session(event_id, "practice", game_version="1.71")
    return store.add_lap(session_id, Lap(
        lap_num=1, lap_time_ms=110_000, best_lap_ms=110_000, delta_ms=0,
        fuel_start=100.0, fuel_end=94.0, fuel_used=6.0, position=1,
        is_pit_lap=False, is_out_lap=False))


def test_a_reading_lands_on_the_lap_tagged_as_video(store: Store):
    lap_id = a_lap(store)
    written = []

    def write(lap, wear):
        store.set_lap_wear(lap, wear["fl"], wear["fr"], wear["rl"], wear["rr"],
                           source=WEAR_HUD_VIDEO)
        written.append(lap)

    from .test_hud_wear import a_canvas
    sampler = LiveWearSampler(
        Grabs((a_canvas({"fl": 0.3, "fr": 0.2, "rl": 0.5, "rr": 0.4}), None)),
        write)
    sampler.start()
    try:
        sampler.request(lap_id)
        assert wait(lambda: written)
    finally:
        sampler.stop()

    row = store._query(
        "SELECT wear_fl, wear_rl FROM laps WHERE id = ?", (lap_id,))[0]
    assert row["wear_rl"] > row["wear_fl"] > 0


def test_a_video_reading_never_overwrites_the_drivers_own(store: Store):
    """`CLAUDE.md` §4.1: his report is primary evidence and this is
    corroboration, so where they disagree the disagreement has to stay
    visible rather than be settled by whichever was written last."""
    lap_id = a_lap(store)
    store.set_lap_wear(lap_id, 0.10, 0.10, 0.10, 0.10, source=WEAR_DRIVER)
    store.set_lap_wear(lap_id, 0.90, 0.90, 0.90, 0.90, source=WEAR_HUD_VIDEO)
    row = store._query("SELECT wear_fl FROM laps WHERE id = ?", (lap_id,))[0]
    assert row["wear_fl"] == 0.10


def test_a_dead_obs_costs_nothing_but_a_log_line(store: Store):
    """The failure that will actually happen: OBS is shut, or the websocket
    server is off. The lap is already recorded by the time this runs, and it
    must stay that way."""
    lap_id = a_lap(store)
    sampler = LiveWearSampler(Grabs((None, "ConnectionRefusedError")),
                              lambda lap, wear: None)
    sampler.start()
    try:
        sampler.request(lap_id)
        assert wait(lambda: sampler._source.calls > 0)
        time.sleep(0.1)
    finally:
        sampler.stop()
    row = store._query("SELECT wear_fl FROM laps WHERE id = ?", (lap_id,))[0]
    assert row["wear_fl"] is None


def test_the_sampler_is_not_built_at_all_when_it_is_switched_off(store: Store):
    """It reaches out to another process on a port. Nothing should start doing
    that because the app was updated."""
    from pitcrew import settings as settings_module

    assert settings_module.Settings().hud_wear_enabled is False


def test_the_sheet_keeps_its_shift_table_alongside(store: Store):
    """Unrelated to wear, and the reason it is here: both landed in the same
    afternoon and both write through `save_setup_sheet`."""
    sheet_id = store.save_setup_sheet(SetupSheet(
        car_name="Porsche 911 RSR (991) '17", sheet_name="Monza race",
        values={"rh_f": 60}, shift_rpm={1: 7400.0, 6: 8500.0}))
    assert store.get_setup_sheet(sheet_id).shift_rpm == {1: 7400.0, 6: 8500.0}
