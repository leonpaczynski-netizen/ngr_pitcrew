"""Every circuit's straights, kept current without the driver running a tool.

*"Map all known and future circuits."* - the driver, 15 Sep 2026. The gates
decide what may be stored (`analysis/straights.gate`); the refresh decides when
a circuit is derived again and refuses a worse model
(`analysis/straight_refresh`); the controller runs it when a session closes.
"""
from __future__ import annotations

import json
import logging
import threading

import pytest

from pitcrew.analysis import straight_refresh as refresh
from pitcrew.analysis import straights as derivation
from pitcrew.store.db import Store
from pitcrew.telemetry.recorder import FRAME_FIELDS, encode_frames

from .test_controller import an_event, qt_app, wired  # noqa: F401
from .test_race_wiring import raced, voice  # noqa: F401
from .test_straight_model import HZ, LENGTH, synthetic_lap

KEY = "test-circuit-full-course"


# ------------------------------------------------------------------ helpers

class Records(logging.Handler):
    """The straights log, whatever `diagnostics.install` did to propagation."""

    def __init__(self) -> None:
        super().__init__(logging.DEBUG)
        self.lines: list[tuple[int, str]] = []

    def emit(self, record) -> None:
        self.lines.append((record.levelno, record.getMessage()))

    def text(self, level: int = logging.DEBUG) -> str:
        return "\n".join(m for lvl, m in self.lines if lvl >= level)


@pytest.fixture()
def records():
    logger = logging.getLogger("pitcrew.straights")
    handler = Records()
    old = logger.level
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)
    yield handler
    logger.removeHandler(handler)
    logger.setLevel(old)


def with_kink(lap, at_m: float = 1100.0):
    """0.45 g for 10 m in the middle of the back straight: a lap whose straight
    ends there, as Yas Marina's does at the first reading over 0.3 g."""
    for frame in lap.frames:
        if at_m <= frame["lap_distance_m"] < at_m + 10.0:
            frame["lat_g"] = 0.45
    return lap


def without_pit_straight(lap):
    for frame in lap.frames:
        d = frame["lap_distance_m"]
        if d < 150.0 or d >= 2600.0:
            frame["lat_g"] = 1.0
    return lap


def event_at(store: Store, track: str = "Test Circuit") -> int:
    return store.create_event(name=f"Rd {track}", track=track,
                              layout="Full Course", car_name="Car",
                              race_type="laps", race_laps=10)


def add_laps(store: Store, session: int, count: int, *, first: int = 1,
             length: float = LENGTH, excluded: bool = False) -> None:
    index = {name: i for i, name in enumerate(FRAME_FIELDS)}
    for lap_num in range(first, first + count):
        lap = synthetic_lap(session, lap_num, length=length)
        rows = []
        for frame in lap.frames:
            row = [None] * len(FRAME_FIELDS)
            for key, value in frame.items():
                row[index[key]] = value
            rows.append(row)
        store._conn.execute(
            "INSERT INTO laps (session_id, lap_num, lap_time_ms, recorded_at, "
            "excluded) VALUES (?,?,?,?,?)",
            (session, lap_num, lap.lap_time_ms, "2026-09-15", int(excluded)))
        lap_id = store._conn.execute(
            "SELECT id FROM laps WHERE session_id=? AND lap_num=?",
            (session, lap_num)).fetchone()[0]
        store._conn.execute(
            "INSERT INTO lap_frames (lap_id, sample_hz, frame_count, blob) "
            "VALUES (?,?,?,?)", (lap_id, HZ, len(rows), encode_frames(rows)))
    store._conn.commit()


def stored_json(store: Store, key: str = KEY) -> dict | None:
    row = store._conn.execute(
        "SELECT model_json FROM straight_models WHERE circuit_key = ?",
        (key,)).fetchone()
    return json.loads(row[0]) if row else None


# ------------------------------------------------------------------- gates

def test_the_gate_numbers_sit_where_they_were_measured():
    assert derivation.MIN_LAPS == 10
    assert derivation.MAX_END_SPREAD_M == 40.0
    ok = {"laps": 10, "end_spread_m": 40.0}
    assert derivation.gate(ok) is None
    assert "fewer than 10" in derivation.gate(ok | {"laps": 9})
    assert "wanders 40 m" in derivation.gate(ok | {"end_spread_m": 40.4})


def test_a_straight_that_ends_in_two_places_is_reported_not_stored():
    """Eight laps run to the braking at 1400 m; four end at a 0.45 g reading
    at 1100 m. The lower-quartile end is not a place on the road."""
    laps = [synthetic_lap(1, i + 1) for i in range(12)]
    for lap in laps[:4]:
        with_kink(lap)
    result = derivation.derive(KEY, laps)
    assert result.model is not None
    (dropped,) = result.dropped
    assert dropped["start_m"] == pytest.approx(400.0, abs=5.0)
    assert dropped["laps"] == 12 and dropped["laps_pooled"] == 12
    assert dropped["end_spread_m"] > derivation.MAX_END_SPREAD_M
    assert "wanders" in dropped["reason"]
    stored_starts = [w["start_m"] for w in result.model["windows"]]
    assert all(abs(s - 400.0) > 50 for s in stored_starts), \
        "the dropped window was stored anyway"
    assert result.model["rule"]["max_end_spread_m"] == 40.0
    assert result.model["rule"]["min_laps"] == 10


def test_a_window_on_fewer_than_the_minimum_laps_is_reported_not_stored():
    """16 laps, the pit straight on 9: present on most laps, too few to
    place its end."""
    laps = [synthetic_lap(1, i + 1) for i in range(16)]
    for lap in laps[:7]:
        without_pit_straight(lap)
    result = derivation.derive(KEY, laps)
    reasons = [d["reason"] for d in result.dropped]
    assert reasons == ["on 9 laps, fewer than 10"]
    assert all(w["laps"] >= 10 for w in result.model["windows"])


def test_a_model_needs_the_minimum_clean_laps():
    result = derivation.derive(KEY, [synthetic_lap(1, i) for i in range(9)])
    assert result.model is None and result.reason == "9 clean laps, fewer than 10"
    assert derivation.derive(
        KEY, [synthetic_lap(1, i) for i in range(10)]).model is not None


def test_the_pool_keeps_the_most_recent_laps():
    laps = [synthetic_lap(1 + i // 6, i + 1) for i in range(18)]
    result = derivation.derive(KEY, laps, max_laps=12)
    assert result.laps_used == 12
    assert result.model["session_ids"] == [2, 3]
    assert result.refused == {"older than the most recent 12": 6}


def test_a_compact_frame_reads_like_the_dict_it_replaces():
    frame = refresh.Frame((100.0, 0.0, 0.05, 216.0, 12.5))
    assert frame.get("speed_kph") == 216.0 and frame["lap_distance_m"] == 12.5
    assert frame.get("pos_x") is None and frame[0] == 100.0


# --------------------------------------------------------------------- plan

def test_no_model_and_too_few_laps_is_no_model_and_says_so():
    plan = refresh.plan(None, 0, None)
    assert not plan.derive and "0 clean laps on file, 10 needed" in plan.reason
    assert refresh.plan(None, 10, None).derive


def test_growth_is_counted_in_new_laps_against_the_pool():
    """A full 80-lap pool of Monza's 218: re-derive after 20 more, not after
    25% of 218 and not at every close."""
    model = {"laps": 80, "laps_available": 218, "lap_length_m": 5748.0}
    assert not refresh.plan(model, 237, 5750.0).derive
    assert refresh.plan(model, 238, 5750.0).derive
    small = {"laps": 10, "laps_available": 12, "lap_length_m": 3000.0}
    assert not refresh.plan(small, 14, None).derive
    assert refresh.plan(small, 15, None).derive


def test_a_model_from_before_laps_available_counts_from_its_pool():
    model = {"laps": 43, "lap_length_m": 6165.7}       # the Bathurst fixture
    assert not refresh.plan(model, 53, None).derive
    assert refresh.plan(model, 54, None).derive


def test_an_axis_off_by_more_than_two_percent_is_a_rederive_on_the_new_axis():
    model = {"laps": 40, "laps_available": 40, "lap_length_m": 3000.0}
    assert not refresh.plan(model, 40, 3059.0).derive
    moved = refresh.plan(model, 40, 3300.0)
    assert moved.derive and moved.axis_changed
    assert moved.reference_length_m == 3300.0
    assert "axis moved" in moved.reason


# ------------------------------------------------------------------ compare

def _derived(laps: int, sessions, windows, dropped=()):
    model = {"laps": laps, "session_ids": list(sessions), "lap_length_m": 3000.0,
             "windows": [dict(w) for w in windows]}
    return derivation.Derived(KEY, model, laps, dropped=list(dropped))


BACK = {"id": "S1", "start_m": 400.0, "end_m": 1400.0, "laps": 12,
        "end_spread_m": 3.0}
PIT = {"id": "S2", "start_m": 2600.0, "end_m": 3150.0, "laps": 12,
       "end_spread_m": 3.0}


def test_fewer_laps_is_refused_unless_the_evidence_is_all_new():
    stored = _derived(20, [1, 2], [BACK, PIT]).model
    assert "pools 12 laps against the stored model's 20" in refresh.compare(
        stored, _derived(12, [2, 3], [BACK, PIT]))
    assert refresh.compare(stored, _derived(12, [3, 4], [BACK, PIT])) is None


def test_losing_a_stored_window_is_refused_and_names_why():
    stored = _derived(12, [1], [BACK, PIT]).model
    gone = dict(BACK, laps=14, end_spread_m=300.0, reason="its end wanders")
    refusal = refresh.compare(stored, _derived(14, [1, 2], [PIT], [gone]))
    assert refusal == "it would lose S1 400-1400 m (its end wanders)"
    # Twice the evidence outvotes it (rule 10).
    assert refresh.compare(stored, _derived(24, [1, 2], [PIT])) is None


def test_a_stored_model_that_fails_todays_gates_is_no_baseline():
    stale = _derived(12, [1], [BACK, dict(PIT, end_spread_m=51.4)]).model
    assert refresh.gate_failures(stale)
    assert refresh.compare(stale, _derived(8, [1], [BACK])) is None


def test_nothing_derived_is_refused():
    empty = derivation.Derived(KEY, None, 4, reason="4 clean laps, fewer than 10")
    assert refresh.compare(None, empty) == \
        "nothing derived - 4 clean laps, fewer than 10"


# ------------------------------------------------- after a session closes

def test_a_circuit_selected_for_the_first_time_with_no_laps_is_no_model_logged(
        store, records):
    session = store.start_session(event_at(store), "practice")
    outcome = refresh.refresh_after_session(store, session)
    assert outcome.action == "unchanged"
    assert stored_json(store) is None
    assert "no model; 0 clean laps on file, 10 needed" in records.text()


def test_a_new_circuit_is_mapped_once_it_has_the_laps(store, records):
    event = event_at(store)
    first = store.start_session(event, "practice")
    add_laps(store, first, 9)
    assert refresh.refresh_after_session(store, first).action == "unchanged"
    assert stored_json(store) is None

    second = store.start_session(event, "practice")
    add_laps(store, second, 3)
    outcome = refresh.refresh_after_session(store, second)
    assert outcome.action == "stored"
    model = stored_json(store)
    assert model["laps"] == 12 and model["laps_available"] == 12
    assert model["session_ids"] == [first, second]
    assert model["tag"] == "[DERIVED]"
    assert store.straight_model(KEY) is not None
    assert "stored (no model; 12 clean laps on file)" in records.text()


def test_growth_rederives_with_the_new_count_and_not_before(store, records):
    event = event_at(store)
    first = store.start_session(event, "practice")
    add_laps(store, first, 12)
    refresh.refresh_after_session(store, first)

    second = store.start_session(event, "practice")
    add_laps(store, second, 2)
    assert refresh.refresh_after_session(store, second).action == "unchanged"
    assert "2 clean laps since the model was derived from 12; 3 needed" \
        in records.text()
    assert stored_json(store)["laps"] == 12

    # A struck lap is not a clean lap.
    add_laps(store, second, 1, first=3, excluded=True)
    assert refresh.refresh_after_session(store, second).action == "unchanged"

    add_laps(store, second, 1, first=4)
    assert refresh.refresh_after_session(store, second).action == "stored"
    model = stored_json(store)
    assert model["laps"] == 15 and model["laps_available"] == 15


def test_a_worse_model_never_replaces_the_stored_one(store, records):
    event = event_at(store)
    session = store.start_session(event, "practice")
    add_laps(store, session, 12)
    refresh.refresh_after_session(store, session)
    better = stored_json(store)
    better["laps"] = 30                  # claims more laps than are on file now
    better["laps_available"] = 0         # so the growth rule fires
    store.save_straight_model(KEY, better)

    outcome = refresh.refresh_after_session(store, session)
    assert outcome.action == "refused"
    assert "pools 12 laps against the stored model's 30" in outcome.reason
    assert stored_json(store) == better
    assert "refused" in records.text() and "the stored model stays" \
        in records.text()


def test_a_window_the_new_laps_fail_is_not_taken_away(store):
    event = event_at(store)
    session = store.start_session(event, "practice")
    add_laps(store, session, 12)
    refresh.refresh_after_session(store, session)
    stored = stored_json(store)
    extra = {"id": "S9", "start_m": 1600.0, "end_m": 2500.0, "laps": 12,
             "laps_pooled": 12, "end_spread_m": 4.0, "t_left_s": [],
             "median_s": 30.0, "brake_m": None}
    stored["windows"].append(extra)
    stored["laps_available"] = 0
    store.save_straight_model(KEY, stored)

    outcome = refresh.refresh_after_session(store, session)
    assert outcome.action == "refused"
    assert outcome.reason.startswith("it would lose S9 1600-2500 m")
    assert len(stored_json(store)["windows"]) == len(stored["windows"])


def test_one_circuit_close_carries_nothing_into_another(store):
    """Rule 11: a model at one circuit says nothing at the next."""
    monza = store.start_session(event_at(store, "Test Circuit"), "practice")
    add_laps(store, monza, 12)
    assert refresh.refresh_after_session(store, monza).action == "stored"

    elsewhere = store.start_session(event_at(store, "Other Circuit"), "race")
    outcome = refresh.refresh_after_session(store, elsewhere)
    assert outcome.circuit_key == "other-circuit-full-course"
    assert outcome.action == "unchanged"
    assert stored_json(store, "other-circuit-full-course") is None
    assert stored_json(store)["laps"] == 12


def test_an_axis_change_rederives_from_the_new_axis_only(store, records):
    event = event_at(store)
    old = store.start_session(event, "practice")
    add_laps(store, old, 12)
    refresh.refresh_after_session(store, old)
    assert stored_json(store)["lap_length_m"] == pytest.approx(LENGTH, rel=0.01)

    new = store.start_session(event, "practice")
    add_laps(store, new, 6, length=LENGTH * 1.1)
    outcome = refresh.refresh_after_session(store, new)
    assert outcome.action == "refused"
    assert "6 clean laps, fewer than 10" in outcome.reason
    assert stored_json(store)["lap_length_m"] == pytest.approx(LENGTH, rel=0.01)
    assert "axis moved" in records.text()

    add_laps(store, new, 4, first=7, length=LENGTH * 1.1)
    outcome = refresh.refresh_after_session(store, new)
    assert outcome.action == "stored", outcome.reason
    model = stored_json(store)
    assert model["lap_length_m"] == pytest.approx(LENGTH * 1.1, rel=0.01)
    assert model["laps"] == 10 and model["session_ids"] == [new]


# --------------------------------------------------------- failure tolerance

def test_a_refresh_that_raises_is_a_logged_warning_and_nothing_changes(
        store, records, monkeypatch):
    event = event_at(store)
    session = store.start_session(event, "practice")
    add_laps(store, session, 12)

    def broken(*_args, **_kwargs):
        raise RuntimeError("blob unreadable")

    monkeypatch.setattr(refresh, "load_laps", broken)
    thread = refresh.refresh_in_background(store, session)
    thread.join(timeout=30)
    assert not thread.is_alive()
    assert stored_json(store) is None
    assert "could not refresh the model after session" in records.text(
        logging.WARNING)


def test_no_session_is_no_thread():
    assert refresh.refresh_in_background(object(), None) is None


def test_closing_practice_refreshes_the_closed_session_off_the_ui_thread(
        wired, monkeypatch):
    controller, _, _, store = wired
    controller._on_event_saved(an_event())
    session = controller.open_practice_session()
    seen = []

    def spy(store_, session_id):
        ended = store_._conn.execute(
            "SELECT ended_at FROM sessions WHERE id = ?",
            (session_id,)).fetchone()[0]
        seen.append((store_, session_id, ended, threading.current_thread()))

    monkeypatch.setattr(refresh, "refresh_in_background", spy)
    controller.stop_practice()
    assert len(seen) == 1
    got_store, got_session, ended, _thread = seen[0]
    assert got_store is store and got_session == session
    assert ended is not None, "refreshed before the session was closed"


def test_closing_a_race_refreshes_its_session(raced, monkeypatch):
    controller, _, store, _ = raced
    controller.start_race()
    session = controller.session_id
    seen = []
    monkeypatch.setattr(refresh, "refresh_in_background",
                        lambda s, sid: seen.append(sid))
    controller.stop_race()
    assert seen == [session]


def test_a_refresh_that_cannot_start_never_breaks_the_close(
        wired, monkeypatch, records):
    controller, _, _, store = wired
    controller._on_event_saved(an_event())
    session = controller.open_practice_session()

    def broken(*_args):
        raise RuntimeError("no threads left")

    monkeypatch.setattr(refresh, "refresh_in_background", broken)
    controller.stop_practice()
    assert controller.session_id is None
    assert store._conn.execute("SELECT ended_at FROM sessions WHERE id = ?",
                               (session,)).fetchone()[0] is not None
    assert "could not start the straights refresh" in records.text(
        logging.WARNING)


# --------------------------------------------------------------------- tool

def test_apply_all_maps_every_circuit_and_refuses_a_worse_model(tmp_path):
    from tools.derive_straights import main

    path = tmp_path / "copy.db"
    store = Store(path)
    try:
        for track in ("Test Circuit", "Other Circuit"):
            session = store.start_session(event_at(store, track), "practice")
            add_laps(store, session, 12)
        store.start_session(event_at(store, "Empty Circuit"), "practice")
    finally:
        store.close()

    assert main(["--all", "--apply", "--db", str(path)]) == 0
    store = Store(path)
    try:
        assert store.straight_model(KEY) is not None
        assert store.straight_model("other-circuit-full-course") is not None
        assert store.straight_model("empty-circuit-full-course") is None
        better = stored_json(store)
        better["laps"] = 30
        store.save_straight_model(KEY, better)
    finally:
        store.close()

    assert main(["--circuit", KEY, "--apply", "--db", str(path)]) == 1
    store = Store(path)
    try:
        assert stored_json(store)["laps"] == 30
    finally:
        store.close()
    assert main(["--circuit", KEY, "--apply", "--replace",
                 "--db", str(path)]) == 0
    store = Store(path)
    try:
        assert stored_json(store)["laps"] == 12
    finally:
        store.close()
