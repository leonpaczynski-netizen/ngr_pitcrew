"""Plan row 5.21 - what the driver board reads live: lap delta, LOCK, TCS, WET.

Each piece is pinned on the claim the board makes about it, and each test that
answers a critic-pass-1 finding says which:

* the delta is live minus the reference at the same distance, negative ahead,
  **every reference is locked to a compound**, and the board reads one
  publication so the named tyre is the one the delta was measured against;
* distance survives a pause the way the recorder's does;
* LOCK is a front wheel below 0.80 slip under braking; TCS is bit 11 (0x0800);
* nothing stays lit once packets stop;
* WET and the compound need recent, undisputed reads.
"""
from __future__ import annotations

import ast
import inspect
import textwrap
import threading
from types import SimpleNamespace

import numpy as np
import pytest

from pitcrew.race.board_live import (
    LOCK_HOLD_S,
    NO_BEST_YET,
    NO_COMPOUND,
    NO_TELEMETRY,
    NOT_ON_A_LAP,
    STALE_S,
    BoardLive,
    best_lap_on_file,
)
from pitcrew.race.qualifying import ReferenceLap
from pitcrew.telemetry.hygrometer import HygroReading
from pitcrew.telemetry.recorder import FRAME_FIELDS


def packet(pid, *, speed=50.0, lap_ms=None, brake=0.0, flags=0x0001,
           rps=None, radius=0.33, paused=False, on_track=True):
    wheel = speed / radius if rps is None else rps
    return SimpleNamespace(
        packet_id=pid, speed_ms=speed, current_lap_time_ms=lap_ms, brake=brake,
        flags_raw=flags, paused=paused, loading=False, car_on_track=on_track,
        wheel_rps_fl=wheel, wheel_rps_fr=wheel, tyre_radius_fl=radius,
        tyre_radius_fr=radius)


def reference(lap_ms=90_000, metres_per_ms=0.05, lap_id=1):
    ts = list(range(0, lap_ms + 1, 1000))
    return ReferenceLap.from_frames(
        [{"lap_distance_m": t * metres_per_ms, "t_ms": t} for t in ts],
        lap_id=lap_id, lap_time_ms=lap_ms)


def drive(live, seconds, *, speed=50.0, start_pid=1, t0=0.0, cross_first=True):
    frames = int(seconds * 60)
    for i in range(frames):
        live.note_packet(packet(start_pid + i, speed=speed,
                                lap_ms=int(i * 1000 / 60)),
                         t0 + i / 60.0, crossed=(i == 0 and cross_first))
    return start_pid + frames, t0 + frames / 60.0


def fields(live, now):
    return live.board_fields(now=now)


# ------------------------------------------------------------------ the delta

def test_no_compound_means_no_delta_and_the_board_says_so():
    live = BoardLive()
    _, t = drive(live, 2.0)
    assert fields(live, t)["delta_s"] is None
    assert fields(live, t)["delta_why"] == NO_COMPOUND


def test_before_the_first_crossing_there_is_nothing_to_time():
    live = BoardLive()
    live.set_compound("RS")
    live.note_packet(packet(10), 0.0)          # joined mid-lap, no crossing
    got = fields(live, 0.1)
    assert got["lap_time_ms"] is None and got["delta_why"] == NOT_ON_A_LAP


def test_a_compound_with_no_best_yet_says_so():
    live = BoardLive()
    live.set_compound("RS")
    _, t = drive(live, 1.0)
    assert fields(live, t)["delta_why"] == NO_BEST_YET


def test_ahead_of_the_reference_is_negative_and_the_prediction_follows():
    live = BoardLive()
    live.set_compound("RS")
    live._session_refs = {"RS": reference(90_000, metres_per_ms=0.05)}
    _, t = drive(live, 10.0, speed=55.0)
    got = fields(live, t)
    assert got["delta_s"] < 0
    assert got["predicted_ms"] == round(90_000 + got["delta_s"] * 1000)
    assert got["reference_compound"] == "RS" and got["session_best_ms"] == 90_000
    slower = BoardLive()
    slower.set_compound("RS")
    slower._session_refs = {"RS": reference(90_000, metres_per_ms=0.05)}
    _, t = drive(slower, 10.0, speed=45.0)
    assert fields(slower, t)["delta_s"] > 0


def test_the_board_names_the_tyre_the_delta_was_measured_on_under_a_switch():
    """Critic pass 1's blocker: a compound switched on the Qt thread mid-packet
    raised and killed the reader for the session. Hammer it from a thread."""
    live = BoardLive()
    live._session_refs = {"RS": reference(90_000)}
    live.set_compound("RS")
    stop = threading.Event()

    def switch():
        while not stop.is_set():
            live.set_compound("RM")
            live.set_compound("RS")

    import sys

    worker = threading.Thread(target=switch)
    interval = sys.getswitchinterval()
    sys.setswitchinterval(1e-6)          # pass 1 reproduced the crash at this rate
    worker.start()
    try:
        pid, t = drive(live, 20.0)
        for _ in range(2000):
            got = live.board_fields(now=t)
            if got["delta_s"] is not None:
                assert got["reference_compound"] == "RS"
                assert got["session_best_ms"] == 90_000
            if got["predicted_ms"] is not None:
                assert got["session_best_ms"] is not None
    finally:
        stop.set()
        worker.join()
        sys.setswitchinterval(interval)


def test_the_board_reads_what_was_published_not_what_changed_since():
    """A compound switched after the last packet must not re-pair the delta
    that packet produced with the new tyre's references."""
    live = BoardLive()
    live._session_refs = {"RS": reference(90_000)}
    live.set_compound("RS")
    _, t = drive(live, 5.0, speed=55.0)
    live.set_compound("RM")
    got = live.board_fields(now=t)
    assert got["reference_compound"] == "RS" and got["session_best_ms"] == 90_000
    assert got["delta_s"] is not None and got["predicted_ms"] is not None


def test_a_pause_does_not_add_distance_or_time():
    """Critic pass 1 reproduced 500 m becoming 2,000 m across a 30 s pause."""
    live = BoardLive()
    live.set_compound("RS")
    pid, t = drive(live, 10.0, speed=50.0)
    before = live._distance_m
    for i in range(1800):                                  # 30 s paused
        live.note_packet(packet(pid + i, speed=50.0, paused=True), t + i / 60.0)
    live.note_packet(packet(pid + 1800, speed=50.0, lap_ms=10_000), t + 30.0)
    assert live._distance_m == pytest.approx(before, abs=1.0)


def test_a_repeated_packet_id_adds_nothing():
    live = BoardLive()
    live.note_packet(packet(5), 0.0, crossed=True)
    live.note_packet(packet(6), 0.02)
    distance = live._distance_m
    live.note_packet(packet(6), 0.03)
    live.note_packet(packet(4), 0.04)
    assert live._distance_m == distance


def test_the_lap_clock_going_backwards_mid_lap_stops_the_timing():
    live = BoardLive()
    live.set_compound("RS")
    live._session_refs = {"RS": reference()}
    pid, t = drive(live, 5.0)                               # 5 s into the lap
    live.note_packet(packet(pid, lap_ms=5_000), t)
    live.note_packet(packet(pid + 1, lap_ms=500), t + 0.02)  # restart, no line
    assert fields(live, t + 0.02)["delta_s"] is None
    assert fields(live, t + 0.02)["delta_why"] == NOT_ON_A_LAP


def test_a_clock_reset_just_after_the_crossing_does_not_end_the_lap():
    """Critic pass 2: if GT7 resets its lap clock a packet AFTER the crossing is
    detected, an unguarded rule blanked the whole lap. No capture on file shows
    the order, so both orders must time the lap."""
    live = BoardLive()
    live.set_compound("RS")
    live._session_refs = {"RS": reference()}
    live.note_packet(packet(1, lap_ms=91_000), 0.0, crossed=True)   # old clock
    live.note_packet(packet(2, lap_ms=16), 1 / 60)                  # reset late
    for i in range(3, 120):
        live.note_packet(packet(i, lap_ms=int((i - 2) * 1000 / 60)), i / 60)
    assert fields(live, 2.0)["delta_s"] is not None


def test_a_small_clock_wobble_does_not_end_the_lap():
    live = BoardLive()
    live.set_compound("RS")
    live._session_refs = {"RS": reference()}
    pid, t = drive(live, 5.0)
    live.note_packet(packet(pid, lap_ms=5_000), t)
    live.note_packet(packet(pid + 1, lap_ms=4_500), t + 0.02)       # 0.5 s back
    assert fields(live, t + 0.02)["delta_s"] is not None


def test_an_out_of_order_packet_does_not_move_the_clock_it_is_judged_by():
    live = BoardLive()
    live.set_compound("RS")
    live._session_refs = {"RS": reference()}
    pid, t = drive(live, 5.0)
    live.note_packet(packet(pid, lap_ms=5_000), t)
    live.note_packet(packet(pid - 100, lap_ms=100), t + 0.01)        # stale, low
    assert live._last_lap_ms == 5_000                               # not moved by it
    live.note_packet(packet(pid + 1, lap_ms=5_016), t + 0.02)
    assert live._last_lap_ms == 5_016
    assert fields(live, t + 0.02)["delta_s"] is not None


def test_an_out_of_order_packet_does_not_end_the_lap():
    live = BoardLive()
    live.set_compound("RS")
    live._session_refs = {"RS": reference()}
    pid, t = drive(live, 5.0)
    live.note_packet(packet(pid - 200, lap_ms=1_000), t)             # stale datagram
    live.note_packet(packet(pid, lap_ms=5_000), t + 0.02)
    assert fields(live, t + 0.02)["delta_s"] is not None


def test_the_crossing_packet_is_not_the_new_laps_distance():
    live = BoardLive()
    live.note_packet(packet(1, speed=60.0), 0.0)
    live.note_packet(packet(2, speed=60.0), 0.02, crossed=True)
    assert live._distance_m == 0.0
    live.note_packet(packet(3, speed=60.0), 0.04)
    assert live._distance_m == pytest.approx(1.0)


def test_off_track_adds_no_distance():
    live = BoardLive()
    live.note_packet(packet(1), 0.0, crossed=True)
    live.note_packet(packet(2, on_track=False), 0.02)
    live.note_packet(packet(3, on_track=False), 0.04)
    assert live._distance_m == 0.0


def test_nothing_stays_lit_once_packets_stop():
    live = BoardLive()
    live.set_compound("RS")
    live.note_packet(packet(1, flags=0x0801, brake=0.9, rps=0.5 * 50 / 0.33), 0.0,
                     crossed=True)
    assert fields(live, 0.25)["tcs_active"] is True          # a quarter-second on
    assert fields(live, 1.0)["lap_time_ms"] is not None      # a second is not stale
    later = fields(live, 2.0)                                 # two seconds is
    assert later["tcs_active"] is None and later["front_lock"] is None
    assert later["lap_time_ms"] is None and later["delta_why"] == NO_TELEMETRY


def test_references_are_kept_per_compound():
    live = BoardLive()
    live._session_refs = {"RS": reference(90_000)}
    live.set_compound("RM")
    assert fields(live, 0.0)["session_best_ms"] is None
    live.set_compound("rs")
    assert fields(live, 0.0)["session_best_ms"] == 90_000


def _rows(lap_ms, metres=4500.0):
    n = int(lap_ms / 1000 * 60)
    index = {name: i for i, name in enumerate(FRAME_FIELDS)}
    rows = []
    for i in range(n):
        row = [None] * len(FRAME_FIELDS)
        row[index["t_ms"]] = i * 1000 / 60
        row[index["lap_distance_m"]] = metres * i / n
        rows.append(row)
    return rows


def lap(ms, **flags):
    values = dict(lap_time_ms=ms, lap_num=3, is_out_lap=False, is_pit_lap=False)
    values.update(flags)
    return SimpleNamespace(**values)


def test_only_a_counted_lap_on_a_known_tyre_becomes_the_best():
    live = BoardLive()
    assert not live.note_lap(lap(90_000), _rows(90_000), FRAME_FIELDS, None)
    assert not live.note_lap(lap(90_000, is_out_lap=True), _rows(90_000),
                             FRAME_FIELDS, "RS")
    assert not live.note_lap(lap(90_000, is_pit_lap=True), _rows(90_000),
                             FRAME_FIELDS, "RS")
    assert not live.note_lap(lap(90_000), _rows(60_000), FRAME_FIELDS, "RS")
    assert live.note_lap(lap(90_000), _rows(90_000), FRAME_FIELDS, "RS", lap_id=11)
    assert not live.note_lap(lap(91_000), _rows(91_000), FRAME_FIELDS, "RS", lap_id=12)
    assert live.note_lap(lap(89_000), _rows(89_000), FRAME_FIELDS, "RS", lap_id=13)
    assert live._session_refs["RS"].lap_id == 13
    assert live.note_lap(lap(95_000), _rows(95_000), FRAME_FIELDS, "RM", lap_id=14)


def test_a_struck_or_retagged_lap_stops_being_the_reference():
    live = BoardLive()
    live.note_lap(lap(89_000), _rows(89_000), FRAME_FIELDS, "RS", lap_id=13)
    live.drop_lap(99)
    assert "RS" in live._session_refs
    live.drop_lap(13)
    assert "RS" not in live._session_refs


def test_a_new_session_forgets_its_bests_but_not_the_archive():
    """Rule 11."""
    loads = []
    live = BoardLive(file_reference_for=lambda c: loads.append(c) or reference())
    live.set_compound("RS")
    live._session_refs = {"RS": reference(88_000)}
    live.new_session()
    assert live.compound is None and live._session_refs == {}
    live.set_compound("RS")
    assert loads == ["RS"]
    assert fields(live, 0.0)["file_best_ms"] == 90_000


# ------------------------------------------------------------------ the lights

def test_tcs_is_bit_eleven_and_is_held_briefly():
    live = BoardLive()
    live.note_packet(packet(1, flags=0x0001 | 0x0800), 0.0)
    assert fields(live, 0.0)["tcs_active"] is True
    live.note_packet(packet(2, flags=0x0001 | 0x0400), 0.1)   # bit 10 is not TCS
    assert fields(live, 0.1)["tcs_active"] is True            # still held from bit 11
    live.note_packet(packet(3, flags=0x0001 | 0x0400), 1.0)
    assert fields(live, 1.0)["tcs_active"] is False


def test_lock_is_below_eighty_percent_front_slip_under_braking():
    near = BoardLive()
    near.note_packet(packet(1, brake=0.8, rps=0.85 * 50.0 / 0.33), 0.0)
    assert fields(near, 0.0)["front_lock"] is False           # 0.85 is not a lock
    live = BoardLive()
    live.note_packet(packet(1, brake=0.8, rps=0.79 * 50.0 / 0.33), 0.0)
    assert fields(live, 0.0)["front_lock"] is True
    other = BoardLive()
    other.note_packet(packet(1, brake=0.0, rps=0.5 * 50.0 / 0.33), 0.0)
    assert fields(other, 0.0)["front_lock"] is False          # no brake, no lock
    live.note_packet(packet(2), LOCK_HOLD_S + 0.01)
    assert fields(live, LOCK_HOLD_S + 0.01)["front_lock"] is False


# ------------------------------------------------------------------ best on file, real schema

def test_best_on_file_filters_on_the_real_schema(tmp_path):
    """Critic pass 1: the SQL was only string-matched. Run it against the store's
    own tables: wrong compound, wrong version, excluded, out-lap and pit-lap
    laps must all be passed over for the right one."""
    from pitcrew.store.db import Store

    store = Store(tmp_path / "t.db")
    conn = store._conn
    cols = lambda table: {r[1] for r in conn.execute(f"pragma table_info({table})")}

    def insert(table, **values):
        values = {k: v for k, v in values.items() if k in cols(table)}
        # Any other NOT NULL column without a default gets a placeholder of its
        # type - the query under test reads none of them.
        for _, name, kind, notnull, default, pk in conn.execute(
                f"pragma table_info({table})"):
            if notnull and default is None and not pk and name not in values:
                values[name] = 0 if "INT" in (kind or "").upper() or                     "REAL" in (kind or "").upper() else "x"
        keys = ", ".join(values)
        marks = ", ".join("?" for _ in values)
        return conn.execute(f"INSERT INTO {table} ({keys}) VALUES ({marks})",
                            tuple(values.values())).lastrowid

    event = insert("events", name="E", track="Track", layout="L", car_name="Car",
                   created_at="x", updated_at="x")
    s171 = insert("sessions", event_id=event, kind="practice", started_at="x",
                  game_version="1.71")
    s170 = insert("sessions", event_id=event, kind="practice", started_at="x",
                  game_version="1.70")
    base = dict(fuel_start=50.0, fuel_end=48.0, fuel_used=2.0)
    wanted = insert("laps", session_id=s171, lap_num=1, lap_time_ms=90_000,
                    compound="RS", **base)
    for number, bad in enumerate((
            dict(session_id=s171, lap_time_ms=80_000, compound="RM"),
            dict(session_id=s170, lap_time_ms=80_000, compound="RS"),
            dict(session_id=s171, lap_time_ms=80_000, compound="RS", excluded=1),
            dict(session_id=s171, lap_time_ms=80_000, compound="RS", is_out_lap=1),
            dict(session_id=s171, lap_time_ms=80_000, compound="RS", is_pit_lap=1)),
            start=2):
        insert("laps", lap_num=number, **bad, **base)
    conn.commit()
    times = {row[0]: row[1] for row in conn.execute("SELECT id, lap_time_ms FROM laps")}

    def frames_for(lap_id):
        # Frames that span each lap's OWN time, so the span gate passes every
        # lap and only the SQL can refuse the wrong ones (critic pass 2).
        n = int(times[lap_id] / 1000 * 60)
        return {"frame_count": n, "sample_hz": 60.0,
                "frames": [{"lap_distance_m": 4.0 * i, "t_ms": i * 1000 / 60}
                           for i in range(n)]}

    store.get_lap_frames = frames_for
    ref = best_lap_on_file(store, "Car", "Track", "L", "1.71", "rs")
    assert ref is not None and ref.lap_id == wanted


# ------------------------------------------------------------------ WET and the compound

def test_wet_needs_recent_readable_reads_and_never_says_dry_without_them():
    from pitcrew.telemetry.hud_session import HudSession

    hud = HudSession(settings=SimpleNamespace(hud_wear_enabled=False), store=None)
    assert hud.wet_now(100.0) is None
    for at, level in ((95.0, 0.7), (97.0, None), (99.0, 0.7)):
        hud._hygro.append((at, level))
    assert hud.wet_now(100.0) is None
    hud._hygro.append((99.5, 0.65))
    assert hud.wet_now(100.0) == "wet"
    assert hud.wet_now(200.0) is None
    hud._hygro.extend([(199.0, 0.0), (199.5, 0.0), (199.8, 0.7)])
    assert hud.wet_now(200.0) == "dry"
    hud._hygro.extend([(199.9, 0.7)])
    assert hud.wet_now(200.0) == "mixed"
    hud.new_session()
    assert hud.wet_now(200.0) is None


def test_old_agreeing_compound_reads_do_not_settle_it():
    """Critic pass 1: the window was untested - the stale case was already
    disputed. Three agreeing reads, all older than the window, are no answer."""
    from pitcrew.telemetry.hud_session import COMPOUND_WINDOW_S, HudSession

    hud = HudSession(settings=SimpleNamespace(hud_wear_enabled=False), store=None)
    hud._compound.extend([(0.0, "RS"), (1.0, "RS"), (2.0, "RS")])
    assert hud.compound_now(3.0) == "RS"
    assert hud.compound_now(2.0 + COMPOUND_WINDOW_S + 1.0) is None


def test_the_sampler_hands_the_hygrometer_a_reading_every_grab():
    from pathlib import Path

    from pitcrew.telemetry.hud import CropFrame, LiveWearSampler, Reading

    got = []
    sampler = LiveWearSampler(source=None, write=lambda *a: None,
                              on_hygro=got.append)
    sampler._pass_hygro(b"not used", Reading(None, "no gauge"))
    assert got[-1].level is None
    data = np.load(Path(__file__).parent / "fixtures" / "hygrometer_panels.npz")
    frame = np.zeros((1080, 1920, 3), np.uint8)
    frame[930:1070, 280:500] = data["wet_steady"]
    bars = {k: (int(v[0]) + 280, int(v[1]) + 280, int(v[2]) + 930, int(v[3]) + 930)
            for k, v in zip(("fl", "rl", "fr", "rr"), data["wet_steady__bars"])}
    whole = CropFrame(pixels=frame, origin=(0, 0), canvas=(1920, 1080))
    sampler._pass_hygro(whole, Reading({"fl": 0.1}, bars=bars))
    assert isinstance(got[-1], HygroReading) and got[-1].wet is True
    crop = CropFrame(pixels=frame[900:1080, 250:520], origin=(250, 900),
                     canvas=(1920, 1080))
    sampler._pass_hygro(crop, Reading({"fl": 0.1}, bars=bars))
    assert got[-1].level is None and "crop" in got[-1].why


def test_a_read_gauge_carries_the_bars_it_read():
    from pitcrew.telemetry.hud import _read_bars

    frame = np.full((200, 200, 3), 255, int)
    layout = {"fl": (10, 20, 10, 45), "rl": (10, 20, 60, 95),
              "fr": (60, 70, 10, 45), "rr": (60, 70, 60, 95)}
    assert _read_bars(frame, layout).bars == layout


# ------------------------------------------------------------------ the controller's wiring

def _body(name):
    from pitcrew.controller import PitCrewController

    return ast.parse(textwrap.dedent(inspect.getsource(getattr(PitCrewController, name))))


def _assigns_board_live_none(tree) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant) \
                and node.value.value is None:
            for target in node.targets:
                if isinstance(target, ast.Attribute) and target.attr == "board_live":
                    return True
    return False


@pytest.mark.parametrize("method", ["stop_race", "stop_practice", "shutdown"])
def test_every_teardown_clears_the_boards_reader(method):
    """Rule 11: a reader left attached reads the next session's packets
    against this session's bests."""
    assert _assigns_board_live_none(_body(method)), method


def test_both_lap_paths_refuse_an_excluded_lap_and_file_its_id():
    calls = [node for node in ast.walk(_body("_on_lap_completed"))
             if isinstance(node, ast.Call) and getattr(node.func, "attr", "") == "_board_note_lap"]
    assert len(calls) == 2
    for call in calls:
        keywords = {k.arg: k.value for k in call.keywords}
        assert {"excluded", "lap_id"} <= set(keywords)
        excluded = ast.dump(keywords["excluded"])
        assert "pending" in excluded, excluded
    # And the practice call also refuses an out-lap the rack has struck.
    assert any("is_out_lap" in ast.dump({k.arg: k.value for k in call.keywords}["excluded"])
               for call in calls)


def test_board_note_lap_does_not_file_an_excluded_lap():
    from pitcrew.controller import PitCrewController

    live = BoardLive()
    stub = SimpleNamespace(bridge=SimpleNamespace(board_live=live))
    PitCrewController._board_note_lap(stub, lap(90_000), _rows(90_000), "RS",
                                      lap_id=1, excluded=True)
    assert live._session_refs == {}
    PitCrewController._board_note_lap(stub, lap(90_000), _rows(90_000), "RS",
                                      lap_id=1, excluded=False)
    assert live._session_refs["RS"].lap_id == 1


def test_opening_practice_records_the_start_tyre():
    tree = _body("open_practice_session")
    assigned = [node for node in ast.walk(tree) if isinstance(node, ast.Assign)
                and any(isinstance(t, ast.Attribute) and t.attr == "_started_compound"
                        for t in node.targets)]
    assert assigned


# ------------------------------------------------------------------ one tyre answer

from pitcrew.controller import PitCrewController as _Controller  # noqa: E402


class _Fitted:
    _fitted_compound = _Controller._fitted_compound
    _tag_race_compound = _Controller._tag_race_compound
    _on_lap_changed = _Controller._on_lap_changed

    def __init__(self, *, seen=None, race=None, rows=(), started=None):
        self.session_id = 42
        self.hud = SimpleNamespace(compound_now=lambda: seen)
        self.race = race
        self.practice = SimpleNamespace(rows=lambda: list(rows),
                                        repaint_rows=lambda: None)
        self._started_compound = started
        self._race_declared_compound = None
        self.written = []
        self.store = SimpleNamespace(
            set_lap_compound=lambda lap_id, c: self.written.append((lap_id, c)),
            set_lap_tyres_fresh=lambda *a: None, set_lap_wear=lambda *a: None,
            exclude_lap=lambda *a: None)

    def _event_record(self):
        return None


def _row(compound=None, pit=False, lap_id=0, session_id=42):
    return SimpleNamespace(compound=compound, is_pit_lap=pit, lap_id=lap_id,
                           session_id=session_id,
                           tyres_fresh=None, wear_fl=None, wear_fr=None,
                           wear_rl=None, wear_rr=None, excluded=False)


def test_the_label_beats_the_plan_and_the_plan_beats_the_event():
    race = SimpleNamespace(state=SimpleNamespace(tyre_compound="RS"), running=True)
    assert _Fitted(seen="RM", race=race)._fitted_compound() == "RM"
    assert _Fitted(seen=None, race=race)._fitted_compound() == "RS"
    bare = SimpleNamespace(state=SimpleNamespace(tyre_compound=None), running=True)
    stub = _Fitted(seen=None, race=bare)
    stub._race_declared_compound = "RH"
    assert stub._fitted_compound() == "RH"


def test_in_practice_the_racks_tag_beats_the_start_tyre_until_a_stop():
    assert _Fitted(rows=[_row("RM")], started="RS")._fitted_compound() == "RM"
    assert _Fitted(rows=[_row(None)], started="RS")._fitted_compound() == "RS"
    # After a pit lap nothing before it says what is fitted now.
    after_stop = [_row("RS"), _row("RS", pit=True), _row(None)]
    assert _Fitted(rows=after_stop, started="RS")._fitted_compound() is None
    # A previous session's tag on the event's rack is not this session's tyre
    # (critic pass 3, rule 11).
    earlier = [_row("RH", session_id=41)]
    assert _Fitted(rows=earlier, started="RS")._fitted_compound() == "RS"


def test_a_disagreement_is_logged_once_per_change(monkeypatch):
    import pitcrew.controller as controller

    said = []
    monkeypatch.setattr(controller, "log",
                        lambda name: SimpleNamespace(warning=lambda *a: said.append(a)))
    stub = _Fitted(seen="RM", rows=[], started="RS")
    for _ in range(5):
        stub._fitted_compound()
    assert len(said) == 1


def test_a_race_lap_is_filed_under_the_label_and_the_answer_is_returned():
    race = SimpleNamespace(state=SimpleNamespace(tyre_compound="RS"), running=True)
    stub = _Fitted(seen="RM", race=race)
    assert stub._tag_race_compound(7) == "RM" and stub.written == [(7, "RM")]
    # A pit lap is never tagged off the label.
    pit = _Fitted(seen="RM", race=race)
    assert pit._tag_race_compound(8, is_pit_lap=True) == "RS"


def test_the_race_reference_is_filed_under_the_compound_the_lap_was_stored_with():
    """Critic pass 3: the board's filing compound was untested - a mutant
    passing the plan's tyre instead of what `_tag_race_compound` wrote lived."""
    calls = [node for node in ast.walk(_body("_on_lap_completed"))
             if isinstance(node, ast.Call)
             and getattr(node.func, "attr", "") == "_board_note_lap"]
    third = [call.args[2] for call in calls if len(call.args) >= 3]
    # One call files the practice row's tag, the other the race's stored tag.
    assert any(isinstance(arg, ast.Name) and arg.id == "filed" for arg in third)
    assert any(isinstance(arg, ast.Attribute) and arg.attr == "compound" for arg in third)
    assigned = [node for node in ast.walk(_body("_on_lap_completed"))
                if isinstance(node, ast.Assign)
                and any(isinstance(target, ast.Name) and target.id == "filed"
                        for target in node.targets)]
    assert assigned and "_tag_race_compound" in ast.dump(assigned[0].value)


def test_arming_a_race_resets_what_the_fitted_answer_reads():
    """Rule 11 for the two things `_fitted_compound` keeps between calls."""
    tree = _body("start_race")
    targets = {target.attr for node in ast.walk(tree) if isinstance(node, ast.Assign)
               for target in node.targets if isinstance(target, ast.Attribute)}
    assert {"_race_declared_compound", "_fitted_disagreement"} <= targets
    # Set on the SUCCESS path, not only by the except that falls back to None.
    in_try = {target.attr for node in ast.walk(tree) if isinstance(node, ast.Try)
              for statement in node.body for sub in ast.walk(statement)
              if isinstance(sub, ast.Assign)
              for target in sub.targets if isinstance(target, ast.Attribute)}
    assert "_race_declared_compound" in in_try


def test_the_race_lap_tells_the_tagger_whether_it_was_a_pit_lap():
    calls = [node for node in ast.walk(_body("_on_lap_completed"))
             if isinstance(node, ast.Call)
             and getattr(node.func, "attr", "") == "_tag_race_compound"]
    assert calls and all(any(k.arg == "is_pit_lap" for k in call.keywords)
                         for call in calls)


def test_marking_a_lap_retires_it_and_every_lap_the_carry_moved(monkeypatch):
    import pitcrew.controller as controller

    live = BoardLive()
    live._session_refs = {"RS": reference(lap_id=5), "RM": reference(lap_id=6),
                          "RH": reference(lap_id=9)}
    monkeypatch.setattr(controller, "carry_compound",
                        lambda rows, lap_id: [SimpleNamespace(lap_id=6, compound="RM")])
    stub = _Fitted(rows=[_row("RS", lap_id=5)])
    stub.bridge = SimpleNamespace(board_live=live)
    stub._on_lap_changed(5)
    assert set(live._session_refs) == {"RH"}
