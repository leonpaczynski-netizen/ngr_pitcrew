"""A circuit's straights, so George starts a line only where it fits.

Bathurst, 14 Sep 2026: George's lines ran into the Hell Corner braking. Without
a circuit model the voice waits for 4 s of held straight and caps a data line
at 2.8 s, and replayed over that race a 2.8 s clip started that way finished
inside the detector's window 63% of the time. The model says where each
straight ENDS - as lap-distance windows derived from his own clean laps - and
the gate starts a clip only if it and a 0.5 s margin fit in what is left.
"""
from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path

import pytest

from pitcrew.analysis import straights as derivation
from pitcrew.race import straight
from pitcrew.race.lap_ruler import LapRuler
from pitcrew.store.db import Store

from .test_controller import qt_app  # noqa: F401
from .test_race_wiring import raced, voice  # noqa: F401

FIXTURE = Path(__file__).parent / "fixtures" / "straights_mount_panorama.json"
BATHURST = "mount-panorama-circuit-full-course"

HZ = 60.0
LENGTH = 3000.0


# ------------------------------------------------------- a synthetic lap

def _segment(d: float) -> dict:
    """What the car is doing at `d` metres round a 3 km test circuit.

    0-150     the pit straight, carried across the line
    150-220   braking for T1
    220-400   T1 and its exit, flat but at 1 g
    400-1400  the back straight, accelerating 45 -> 70 m/s, one upshift
    1400-1500 braking
    1500-2600 the infield, part throttle at 1.2 g
    2600-3000 the pit straight
    """
    if d < 150 or d >= 2600:
        return {"throttle_pct": 100.0, "lat_g": 0.05, "brake_pct": 0.0,
                "v": 60.0}
    if d < 220:
        return {"throttle_pct": 0.0, "lat_g": 0.1, "brake_pct": 90.0, "v": 40.0}
    if d < 400:
        return {"throttle_pct": 100.0, "lat_g": 1.0, "brake_pct": 0.0,
                "v": 35.0}
    if d < 1400:
        v = 45.0 + 25.0 * (d - 400.0) / 1000.0
        # An upshift at 800 m: the throttle drops to zero for six frames.
        dip = 800.0 <= d < 800.0 + 6 * v / HZ
        return {"throttle_pct": 0.0 if dip else 100.0, "lat_g": 0.05,
                "brake_pct": 0.0, "v": v}
    if d < 1500:
        return {"throttle_pct": 0.0, "lat_g": 0.1, "brake_pct": 95.0, "v": 40.0}
    return {"throttle_pct": 60.0, "lat_g": 1.2, "brake_pct": 0.0, "v": 30.0}


def synthetic_lap(session_id: int = 1, lap_num: int = 1, *,
                  length: float = LENGTH, teleport_at: int | None = None,
                  ) -> derivation.LapInput:
    frames, d = [], 0.0
    while d < length:
        seg = _segment(d * LENGTH / length)
        v = seg["v"]
        x = d + (500.0 if teleport_at is not None
                 and len(frames) >= teleport_at else 0.0)
        frames.append({
            "throttle_pct": seg["throttle_pct"], "brake_pct": seg["brake_pct"],
            "lat_g": seg["lat_g"], "speed_kph": v * 3.6,
            "yaw_rate": seg["lat_g"] * 9.81 / v,
            "lap_distance_m": round(d, 2), "pos_x": x, "pos_y": 0.0,
            "pos_z": 0.0})
        d += v / HZ
    return derivation.LapInput(session_id, lap_num,
                               int(len(frames) * 1000 / HZ), frames, HZ, "Car")


@pytest.fixture(scope="module")
def synthetic():
    laps = [synthetic_lap(1 + i % 2, i + 1) for i in range(12)]
    return derivation.derive("test-circuit", laps, derived_on="2026-09-14")


def test_the_thresholds_are_the_live_detectors():
    assert derivation.THROTTLE_PCT == straight.THROTTLE_PCT
    assert derivation.MAX_LATERAL_G == straight.MAX_LATERAL_G
    assert derivation.MIN_HELD_S == straight.MIN_HELD_S


def test_a_synthetic_lap_gives_its_two_straights(synthetic):
    model = synthetic.model
    assert model is not None and model["tag"] == "[DERIVED]"
    assert synthetic.laps_used == 12
    back, pit = model["windows"]
    # The back straight, bridged across its upshift and ended before braking.
    assert back["start_m"] == pytest.approx(400.0, abs=5.0)
    assert back["end_m"] == pytest.approx(1400.0, abs=5.0)
    assert back["brake_m"] == pytest.approx(1400.0, abs=5.0)
    assert back["laps"] == 12 and back["laps_pooled"] == 12
    # 1000 m at 45 -> 70 m/s is (1000/25) * ln(70/45) = 17.7 s.
    assert back["median_s"] == pytest.approx(17.7, abs=0.2)
    profile = back["t_left_s"]
    assert profile[0] == pytest.approx(back["median_s"], abs=0.2)
    assert profile[-1] == 0.0
    assert all(a >= b for a, b in zip(profile, profile[1:]))


def test_a_straight_across_the_line_is_one_window(synthetic):
    pit = synthetic.model["windows"][1]
    axis = synthetic.model["lap_length_m"]
    assert pit["start_m"] == pytest.approx(2600.0, abs=5.0)
    assert pit["end_m"] > axis, "it ends on the next lap"
    assert pit["end_m"] - axis == pytest.approx(150.0, abs=5.0)
    # Braking for T1, on the next lap's axis.
    assert pit["brake_m"] - axis == pytest.approx(150.0, abs=5.0)


def test_braking_zones_are_marked(synthetic):
    entries = [z["start_m"] for z in synthetic.model["braking"]]
    assert entries == [pytest.approx(150.0, abs=5.0),
                       pytest.approx(1400.0, abs=5.0)]
    assert all(z["laps"] == 12 for z in synthetic.model["braking"])


def test_every_window_carries_its_count_and_sources(synthetic):
    model = synthetic.model
    assert model["session_ids"] == [1, 2]
    assert model["laps"] == 12
    for window in model["windows"]:
        assert window["laps"] > 0


def test_a_lateral_spike_is_never_bridged():
    """An upshift is bridged; 0.2 s at 1 g in the middle of a straight is a
    kink, and it splits the straight however short it is."""
    flat = {"throttle_pct": 100.0, "lat_g": 0.05, "brake_pct": 0.0}
    corner = [{"throttle_pct": 50.0, "lat_g": 1.5, "brake_pct": 0.0}] * 60
    kinked = (corner + [flat] * 200
              + [{"throttle_pct": 100.0, "lat_g": 1.0, "brake_pct": 0.0}] * 12
              + [flat] * 200 + corner)
    assert derivation.straight_runs(kinked) == [(60, 260), (272, 472)]
    dipped = (corner + [flat] * 200
              + [{"throttle_pct": 0.0, "lat_g": 0.05, "brake_pct": 0.0}] * 6
              + [flat] * 200 + corner)
    assert derivation.straight_runs(dipped) == [(60, 466)]


def test_a_run_across_the_line_is_joined_and_judged_whole():
    """1.5 s before the line and 1.5 s after it: neither half is a straight
    alone, and together they are one of 3 s."""
    flat = {"throttle_pct": 100.0, "lat_g": 0.05, "brake_pct": 0.0}
    corner = {"throttle_pct": 50.0, "lat_g": 1.5, "brake_pct": 0.0}
    frames = [flat] * 90 + [corner] * 300 + [flat] * 90
    assert derivation.straight_runs(frames) == [(390, 480 + 90)]


def test_teleported_and_wrong_length_laps_are_refused():
    laps = [synthetic_lap(1, i) for i in range(1, 6)]
    laps.append(synthetic_lap(1, 6, teleport_at=2000))
    laps.append(synthetic_lap(1, 7, length=LENGTH * 1.5))
    result = derivation.derive("test-circuit", laps)
    assert result.laps_used == 5
    assert result.refused == {"teleport": 1,
                              "length off the median by more than 2%": 1}


def test_too_few_laps_is_no_model_and_says_why():
    result = derivation.derive("test-circuit",
                               [synthetic_lap(1, i) for i in range(3)])
    assert result.model is None
    assert "fewer than" in result.reason


# ----------------------------------------------------- the Bathurst model

@pytest.fixture(scope="module")
def bathurst() -> straight.StraightsModel:
    return straight.StraightsModel.from_dict(
        json.loads(FIXTURE.read_text(encoding="utf-8")))


def _window_over(model, lo: float, hi: float):
    return [s for s in model.straights if s.start_m < hi and s.end_m > lo]


def test_bathurst_has_mountain_conrod_and_the_pit_straight(bathurst):
    """Measured on 43 clean laps of sessions 151-176.

    Mountain Straight runs from the Hell Corner exit to Griffins Bend,
    Conrod from the Dipper to the Chase kink, and the pit straight from
    Murray's exit across the line to the Hell Corner braking.
    """
    assert bathurst.circuit_key == BATHURST
    assert bathurst.laps >= 40 and 176 in bathurst.session_ids

    mountain, = _window_over(bathurst, 400.0, 1100.0)
    assert 250.0 < mountain.start_m < 400.0
    assert 1150.0 < mountain.end_m < 1230.0
    assert 13.0 < mountain.median_s < 16.0

    conrod, = _window_over(bathurst, 4200.0, 4800.0)
    assert 3950.0 < conrod.start_m < 4100.0
    assert 4900.0 < conrod.end_m < 5000.0
    assert 12.0 < conrod.median_s < 14.5

    pit = [s for s in bathurst.straights if s.end_m > bathurst.lap_length_m]
    assert len(pit) == 1, "the pit straight crosses the line"
    assert 5900.0 < pit[0].start_m < 6050.0
    # It has to be over before the Hell Corner braking on the next lap.
    assert pit[0].limit_m - bathurst.lap_length_m < 130.0
    assert 4.5 < pit[0].median_s < 7.0

    for window in bathurst.straights:
        assert window.laps >= derivation.MIN_LAPS


# ------------------------------------------------------------ the gate

def test_a_28s_clip_is_refused_with_15s_left_and_accepted_with_5():
    assert not straight.fits(straight.Window(held_s=2.5, remaining_s=1.5),
                             2.8, strict=True)
    assert straight.fits(straight.Window(held_s=2.5, remaining_s=5.0),
                         2.8, strict=True)


def test_on_conrod_the_model_refuses_and_accepts_by_what_is_left(bathurst):
    conrod, = _window_over(bathurst, 4200.0, 4800.0)
    axis = bathurst.lap_length_m
    speed = 77.0                                        # ~280 km/h
    near_end = conrod.limit_m - 1.5 * speed
    left = bathurst.remaining_s(near_end, last_lap_m=axis, speed_ms=speed)
    assert left is not None and left <= 1.5 + 1e-9
    assert not straight.fits(straight.Window(held_s=6.0, remaining_s=left),
                             2.8, strict=True)

    early = conrod.limit_m - 5.5 * speed
    left = bathurst.remaining_s(early, last_lap_m=axis, speed_ms=speed)
    assert left is not None and left >= 2.8 + straight.FIT_MARGIN_S
    assert straight.fits(straight.Window(held_s=6.0, remaining_s=left),
                         2.8, strict=True)


def test_the_lower_of_the_two_estimates_is_used(bathurst):
    """His usual pace down Conrod against tonight's speed: whichever says
    less time is left is the one the gate believes."""
    conrod, = _window_over(bathurst, 4200.0, 4800.0)
    at = conrod.start_m + 200.0
    axis = bathurst.lap_length_m
    by_model = conrod.time_to_end(at) - conrod.time_to_end(conrod.limit_m)
    slow = bathurst.remaining_s(at, last_lap_m=axis, speed_ms=10.0)
    fast = bathurst.remaining_s(at, last_lap_m=axis, speed_ms=150.0)
    assert slow == pytest.approx(by_model)
    assert fast == pytest.approx((conrod.limit_m - at) / 150.0)


def test_the_pit_straight_is_found_after_the_crossing(bathurst):
    axis = bathurst.lap_length_m
    pit, = [s for s in bathurst.straights if s.end_m > axis]
    # 20 m past the line: the ruler has already reset to the new lap.
    left = bathurst.remaining_s(20.0, last_lap_m=axis, speed_ms=58.0)
    assert left == pytest.approx(min(
        (pit.limit_m - axis - 20.0) / 58.0,
        pit.time_to_end(axis + 20.0) - pit.time_to_end(pit.limit_m)))


def test_off_every_straight_is_no_room_not_unknown(bathurst):
    """The Chase: the distance is trusted and the model has no straight
    there, so the answer is a known 0.0 s - and nothing fits in it."""
    left = bathurst.remaining_s(5200.0, last_lap_m=bathurst.lap_length_m,
                                speed_ms=50.0)
    assert left == 0.0
    window = straight.Window(held_s=3.0, remaining_s=left)
    assert not straight.fits(window, 1.0, strict=True)
    assert not straight.fits(window, None, strict=False)


def test_the_live_scale_puts_tonights_integration_on_the_axis(bathurst):
    """A session integrating 0.5% long reads 0.5% further round; scaled by
    its own last lap it is the same place on the road."""
    axis = bathurst.lap_length_m
    at = 4600.0
    base = bathurst.remaining_s(at, last_lap_m=axis, speed_ms=70.0)
    scaled = bathurst.remaining_s(at * 1.005, last_lap_m=axis * 1.005,
                                  speed_ms=70.0)
    assert scaled == pytest.approx(base)


# --------------------------------------------------------- the fallback

class FakeRuler:
    def __init__(self, where=None, last=None):
        self._where, self.last_lap_length_m = where, last

    def where(self):
        return self._where


def _open_detector(model=None, ruler=None, *, held_s=6.0, speed=70.0):
    detector = straight.Straight()
    detector.use_model(model, ruler=ruler)
    for at in (100.0 - held_s, 100.0):
        detector.update(throttle_pct=100.0, speed_ms=speed, yaw_rate=0.0,
                        now=at)
    return detector


def test_no_model_is_the_held_4s_fallback_unchanged():
    window = _open_detector().window(100.0)
    assert window.remaining_s is None
    assert straight.fits(window, 2.8, strict=True)
    assert not straight.fits(window, 3.0, strict=True)
    early = _open_detector(held_s=2.5).window(100.0)
    assert not straight.fits(early, 2.0, strict=True)


def test_unknown_distance_falls_back_and_is_never_zero_metres(bathurst):
    axis = bathurst.lap_length_m
    cases = {
        "no ruler": lambda: None,
        "ruler lost packets": lambda: FakeRuler(None, axis),
        "first lap, nothing closed": lambda: FakeRuler(4500.0, None),
        "last lap was the out-lap": lambda: FakeRuler(4500.0, axis * 0.96),
    }
    for why, ruler in cases.items():
        window = _open_detector(bathurst, ruler).window(100.0)
        assert window.remaining_s is None, why
    # A LapRuler that has never been fed says None - not 0 m, which is the
    # start line and on Bathurst's pit straight.
    never_fed = LapRuler(circuit_length_m=6213.0)
    never_fed.last_lap_length_m = axis
    window = _open_detector(bathurst, lambda: never_fed).window(100.0)
    assert window.remaining_s is None


def test_a_ruler_that_raises_is_the_fallback_not_a_silenced_engineer(bathurst):
    def broken():
        raise RuntimeError("torn")
    window = _open_detector(bathurst, broken).window(100.0)
    assert window.open and window.remaining_s is None


def test_with_a_model_and_a_trusted_ruler_the_window_carries_what_is_left(
        bathurst):
    axis = bathurst.lap_length_m
    ruler = FakeRuler(4600.0, axis)
    window = _open_detector(bathurst, lambda: ruler, held_s=2.2).window(100.0)
    assert window.remaining_s is not None and window.remaining_s > 3.3
    assert straight.fits(window, 2.8, strict=True), (
        "with a model the hold drops back to the 2 s edge")


def test_use_model_none_restores_the_fallback(bathurst):
    detector = _open_detector(bathurst, lambda: FakeRuler(4600.0, 6165.7))
    detector.use_model(None, ruler=lambda: FakeRuler(4600.0, 6165.7))
    assert detector.window(100.0).remaining_s is None


# ------------------------------------------------------------- storage

def test_the_store_round_trips_a_model(tmp_path):
    store = Store(tmp_path / "pitcrew.db")
    try:
        payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
        store.save_straight_model(BATHURST, payload)
        store.save_straight_model(BATHURST, payload)          # an upsert
        back = store.straight_model(BATHURST)
        assert back is not None and back.laps == payload["laps"]
        assert [s.id for s in back.straights] == [
            w["id"] for w in payload["windows"]]
        assert store.straight_model("somewhere-else") is None
        assert store.straight_model(None) is None
        rows = store._conn.execute(
            "SELECT COUNT(*), MAX(laps), MAX(session_ids) FROM straight_models"
        ).fetchone()
        assert rows[0] == 1 and rows[1] == payload["laps"]
        assert 176 in json.loads(rows[2])
    finally:
        store.close()


def test_the_store_refuses_a_window_without_its_lap_count(tmp_path):
    store = Store(tmp_path / "pitcrew.db")
    try:
        payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
        del payload["windows"][0]["laps"]
        with pytest.raises(ValueError):
            store.save_straight_model(BATHURST, payload)
        payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
        payload["session_ids"] = []
        with pytest.raises(ValueError):
            store.save_straight_model(BATHURST, payload)
    finally:
        store.close()


# ---------------------------------------------------------------- tool

def test_apply_refuses_a_database_that_does_not_exist(tmp_path, capsys):
    from tools.derive_straights import main

    missing = tmp_path / "typo.db"
    assert main(["--circuit", BATHURST, "--apply", "--db", str(missing)]) == 2
    assert not missing.exists(), "a mistyped path must not become a database"


def test_apply_needs_an_explicit_database():
    from tools.derive_straights import main

    with pytest.raises(SystemExit):
        main(["--circuit", BATHURST, "--apply"])


def test_apply_writes_a_copy_and_a_dry_run_writes_nothing(tmp_path):
    """End to end on a small database: dry run leaves it alone, --apply
    writes the model the live gate reads back."""
    from pitcrew.telemetry.recorder import FRAME_FIELDS, encode_frames
    from tools.derive_straights import main

    path = tmp_path / "copy.db"
    store = Store(path)
    try:
        event = store.create_event(
            name="Rd", track="Test Circuit", layout="Full Course",
            car_name="Car", race_type="laps", race_laps=10)
        session = store.start_session(event, "practice")
        index = {name: i for i, name in enumerate(FRAME_FIELDS)}
        for lap_num in range(1, 13):
            lap = synthetic_lap(session, lap_num)
            rows = []
            for f in lap.frames:
                row = [None] * len(FRAME_FIELDS)
                for key, value in f.items():
                    row[index[key]] = value
                rows.append(row)
            store._conn.execute(
                "INSERT INTO laps (session_id, lap_num, lap_time_ms, "
                "recorded_at) VALUES (?,?,?,?)",
                (session, lap_num, lap.lap_time_ms, "2026-09-14"))
            lap_id = store._conn.execute(
                "SELECT id FROM laps WHERE session_id=? AND lap_num=?",
                (session, lap_num)).fetchone()[0]
            store._conn.execute(
                "INSERT INTO lap_frames (lap_id, sample_hz, frame_count, blob)"
                " VALUES (?,?,?,?)", (lap_id, HZ, len(rows),
                                      encode_frames(rows)))
        store._conn.commit()
    finally:
        store.close()

    key = "test-circuit-full-course"
    assert main(["--db", str(path), "--circuit", key]) == 0
    conn = sqlite3.connect(path)
    try:
        assert conn.execute(
            "SELECT COUNT(*) FROM straight_models").fetchone()[0] == 0
    finally:
        conn.close()

    assert main(["--db", str(path), "--circuit", key, "--apply"]) == 0
    store = Store(path)
    try:
        model = store.straight_model(key)
        assert model is not None and len(model.straights) == 2
    finally:
        store.close()


# ---------------------------------------------------- the controller hook

def test_arming_a_race_hands_the_detector_its_circuits_model(raced):
    from pitcrew.controller import circuit_key_for

    controller, _, store, _ = raced
    key = circuit_key_for(controller.active_event())
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    payload["circuit_key"] = key
    store.save_straight_model(key, payload)
    controller.start_race()
    assert controller.bridge.straight.model is not None

    # The ruler the pit wall builds is what it reads - absent, the gate is
    # the fallback.
    controller._lap_ruler = None
    assert controller.bridge.straight.modelled_remaining_s() is None
    ruler = LapRuler(circuit_length_m=6213.0)
    ruler.note_packet(type("P", (), {"packet_id": 1, "speed_ms": 70.0})())
    ruler.distance_m = 4600.0
    ruler.last_lap_length_m = payload["lap_length_m"]
    controller._lap_ruler = ruler
    assert controller.bridge.straight.modelled_remaining_s() > 3.3


def test_arming_where_there_is_no_model_clears_the_last_one(raced):
    controller, _, _, _ = raced
    controller.bridge.straight.use_model(
        straight.StraightsModel.from_dict(
            json.loads(FIXTURE.read_text(encoding="utf-8"))),
        ruler=lambda: None)
    controller.start_race()
    assert controller.bridge.straight.model is None, (
        "last circuit's straights survived into this race - rule 11")


# ------------------------------------------------ the Bathurst race replay

LIVE = Path(os.environ.get("PITCREW_LIVE_DB")
            or Path(__file__).resolve().parents[2] / "data" / "pitcrew.db")


@pytest.mark.skipif(not LIVE.exists(), reason="no live database here")
def test_the_bathurst_race_replayed_through_the_gate():
    """Session 176, frame by frame through the live detector and `fits`, with
    the model derived WITHOUT that race (out of sample) and without a model.

    "Inside the straight" is the detector's own rule with upshift dips
    closed; "inside the detector window" is the like-for-like with the 63%
    the fallback was measured at, and it counts every upshift as the end of
    a straight - so it understates the model, which starts clips earlier on
    straights the detector splits at every gear.
    """
    from tools import derive_straights as tool

    conn = tool._read_only(LIVE)
    try:
        events = tool.circuits(conn).get(BATHURST)
        race = tool.session_laps(conn, 176) if events else []
        if not race:
            pytest.skip(f"{LIVE} holds no Bathurst race 176")
        laps = tool.clean_laps(conn, events, exclude_sessions={176})
    finally:
        conn.close()
    derived = derivation.derive(BATHURST, laps)
    model = straight.StraightsModel.from_dict(derived.model)

    fallback = tool.replay(race, None, 2.8)
    assert fallback.fraction(fallback.inside) == pytest.approx(0.63, abs=0.02)
    for clip in (2.0, 2.8):
        with_model = tool.replay(race, model, clip)
        without = tool.replay(race, None, clip)
        assert with_model.started > without.started, "fewer chances, not more"
        assert with_model.fraction(with_model.before_brake) >= 0.97
        assert with_model.fraction(with_model.on_straight) >= 0.90
        assert with_model.fraction(with_model.on_straight) > \
            without.fraction(without.on_straight)
