"""The measurement and verdict store, and the four things it must not do.

The tables exist because on 8 Sep 2026 two calls went wrong for want of two
answers the app could not give — *"has this axis ever been tested on this
car?"* and *"what instrument produced that refutation, and can it resolve the
axis at all?"* Every test here is one of those two questions, or one of the
defects this codebase has already paid for:

* a column that reaches a fresh database and never a real one
  (`test_schema_drift.py` is the general case; the pre-migration test below is
  this change's);
* a zero standing in for a missing measurement (rule 3);
* a table with both ends built and no caller (five times in this codebase);
* a setup value stored anywhere but `brain/car-state/<car>-<circuit>.md`.
"""
from __future__ import annotations

import json
import sqlite3

import pytest

from pitcrew.engineer.measurements import (
    Measurement,
    MeasurementError,
    Verdict,
    untested,
)
from pitcrew.store.db import Store
from pitcrew.store.schema import DDL, SCHEMA_VERSION

CAR = "Lamborghini Huracan GT3 '15"
CIRCUIT = "daytona-international-speedway-road-course"


def a_measurement(**overrides) -> Measurement:
    fields = dict(
        car_name=CAR, circuit_key=CIRCUIT, metric="on_power_rotation_index",
        value=0.00788, unit="ratio", scope="corner", zone="T5 exit",
        source="DERIVED", config_ref="huracan-daytona#s143",
        config_label="A", n=15, n_basis="clean laps", noise_floor=0.00104,
        floor_method="odd/even split of one session's clean laps",
        tool="test", session_ids=(143,), game_version="1.71",
        measured_on="2026-09-07")
    fields.update(overrides)
    return Measurement(**fields)


def a_verdict(**overrides) -> Verdict:
    fields = dict(
        car_name=CAR, circuit_key=CIRCUIT, axis="lsd_a", direction="down",
        verdict="refuted", instrument="on_power_rotation_index",
        instrument_floor=0.00104, decided_on="2026-09-08",
        game_version="1.71", why="less lock gave less rotation on power")
    fields.update(overrides)
    return Verdict(**fields)


# ------------------------------------------------------------ the migration

def _v17_shaped(path) -> None:
    """A database at the shape this change found, with rows in it.

    The v18 tables are cut out of the current DDL rather than pasted in from
    an old copy, so this fixture cannot drift away from what the file it is
    imitating actually was. `user_version` is stamped at 17, which is the
    state `CREATE TABLE IF NOT EXISTS` cannot see and every live file was in.
    """
    before, _, _after = DDL.partition("-- ---------------------------------"
                                      "--------------------------------- v18")
    conn = sqlite3.connect(path)
    try:
        conn.executescript(before)
        conn.execute(
            "INSERT INTO events (id, name, track, layout, car_name, "
            "created_at, updated_at) VALUES (1, 'Round 6', 'Daytona "
            "International "
            "Speedway', 'Road Course', ?, '2026-09-07', '2026-09-07')",
            (CAR,))
        conn.execute(
            "INSERT INTO range_records (car_name, measured_date, "
            "ranges_json, verified, updated_at) VALUES (?,?,?,1,?)",
            (CAR, "2026-08-11",
             json.dumps({"rh_f": [55, 80], "rh_r": [60, 90],
                         "lsd_a": [5, 60], "lsd_b": [5, 60]}),
             "2026-08-11"))
        conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION - 1}")
        conn.commit()
    finally:
        conn.close()


def test_a_pre_migration_file_gains_both_tables_and_keeps_its_rows(tmp_path):
    """The whole risk of this change, on a file that predates it.

    `lap_frames` cascades off `laps` and the live file holds 96 sessions of
    them, so a migration that rebuilt anything would be expensive in a way
    nothing else here is. This one adds two tables and touches nothing.
    """
    from tools.schema_audit import declared_columns, drift

    path = tmp_path / "v17.db"
    _v17_shaped(path)

    before = sqlite3.connect(path)
    have = {r[0] for r in before.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table'")}
    events_before = before.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    before.close()
    assert "measurement" not in have and "verdict" not in have, (
        "the fixture must predate the tables")
    assert events_before == 1

    store = Store(path)
    try:
        tables = {r[0] for r in store._conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'")}
        assert {"measurement", "verdict"} <= tables

        # Every declared column on both tables, not just the tables.
        declared = declared_columns()
        for table in ("measurement", "verdict"):
            live = {r[1] for r in
                    store._conn.execute(f"PRAGMA table_info({table})")}
            want = set(declared[table])
            assert want <= live, (table, want - live)

        # And nothing else drifted, on a file that was not fresh.
        assert drift(store._conn) == {}

        # The rows that were there are still there.
        assert store.get_event(1)["car_name"] == CAR
        assert store.get_range_record(CAR).ranges["rh_r"] == [60, 90]

        # And the new tables take a write on this file, which is the check
        # `rival_stops.compound_reads` did not have for a whole race.
        assert store.record_measurement(a_measurement()) > 0
        assert store.record_verdict(a_verdict()) > 0
    finally:
        store.close()


def test_opening_twice_does_not_double_anything(tmp_path):
    path = tmp_path / "twice.db"
    _v17_shaped(path)
    for _ in range(2):
        Store(path).close()
    conn = sqlite3.connect(path)
    try:
        names = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' "
            "AND name = 'measurement'")]
        assert names == ["measurement"]
        assert conn.execute("PRAGMA user_version").fetchone()[0] \
            == SCHEMA_VERSION
    finally:
        conn.close()


# ------------------------------------------------------- rule 3: null vs 0

def test_a_null_noise_floor_reads_back_null(store):
    """**The acceptance test for rule 3 on this table.**

    A floor of 0.0 says every difference is resolvable; a floor of null says
    nobody established one. Those are opposite claims, and a store that turned
    the second into the first would make every unresolvable change look
    resolvable — which is the 1 Sep `lsd_a` refutation exactly.
    """
    row_id = store.record_measurement(
        a_measurement(metric="front_scrub_t5_exit", noise_floor=None,
                      floor_method=None))
    back = store.measurements(metric="front_scrub_t5_exit")[0]
    assert back.id == row_id
    assert back.noise_floor is None
    assert back.floor_method is None
    # And in the file itself, not just after the dataclass has been through it.
    raw = store._conn.execute(
        "SELECT noise_floor FROM measurement WHERE id = ?", (row_id,))
    assert raw.fetchone()[0] is None


def test_a_zero_noise_floor_is_refused_by_name():
    with pytest.raises(MeasurementError, match="noise floor of 0.0"):
        a_measurement(noise_floor=0.0).validate()


def test_a_missing_sample_count_is_null_and_not_zero(store):
    store.record_measurement(
        a_measurement(metric="short_shift_lap_trade", n=None, n_basis=None,
                      scope="session", zone=None))
    back = store.measurements(metric="short_shift_lap_trade")[0]
    assert back.n is None


def test_a_sample_count_of_zero_is_refused():
    """Rule 4's other edge: n=0 is not a smaller measurement."""
    with pytest.raises(MeasurementError, match="sample count of zero"):
        a_measurement(n=0, n_basis="clean laps").validate()


def test_a_count_with_no_basis_is_refused():
    with pytest.raises(MeasurementError, match="of what"):
        a_measurement(n=15, n_basis=None).validate()


def test_a_floor_with_no_method_is_refused():
    with pytest.raises(MeasurementError, match="cannot be audited"):
        a_measurement(noise_floor=0.001, floor_method=None).validate()


# --------------------------------------------- the constraints on a verdict

def test_untested_is_the_answer_for_an_axis_with_no_rows(store):
    """**The question that had no answer on 8 Sep.**

    Ride height had never been A/B'd on any car in the programme and nobody
    knew, because "no rows" and "not asked yet" looked identical from every
    angle. `verdict_for` never returns None.
    """
    answer = store.verdict_for(CAR, "rh_f", CIRCUIT)
    assert answer.verdict == "untested"
    assert answer.instrument is None
    assert answer.why


def test_a_refutation_has_to_name_its_direction():
    """`lsd_a` was refuted on a test that only ever RAISED it."""
    with pytest.raises(MeasurementError, match="direction tested"):
        a_verdict(direction=None).validate()


def test_a_refutation_has_to_name_its_instrument():
    """A channel that cannot see the change never refuted the lever."""
    with pytest.raises(MeasurementError, match="name the.*instrument"):
        a_verdict(instrument=None).validate()


def test_unresolvable_may_carry_no_floor_at_all():
    """**The motivating row itself, and it has to be writable.**

    An instrument fails two ways: the change was inside a measured floor, or
    it never moved while another instrument did and no floor was ever taken
    for it. The second is the rear wheel-speed split on 1 Sep. A rule that
    demanded a floor here would refuse the one row this table exists for, and
    the only way to satisfy it would be to invent one.
    """
    a_verdict(verdict="unresolvable", instrument="rear_wheel_speed_split",
              instrument_floor=None).validate()


def test_unresolvable_still_has_to_name_the_instrument_that_failed():
    with pytest.raises(MeasurementError, match="could not resolve"):
        a_verdict(verdict="unresolvable", instrument=None,
                  instrument_floor=None).validate()


def test_an_untested_verdict_may_not_rest_on_evidence():
    with pytest.raises(MeasurementError, match="is not untested"):
        a_verdict(verdict="untested", direction=None,
                  instrument="on_power_rotation_index").validate()


def test_an_invented_axis_is_refused():
    """`pitcrew/setup/vocabulary.py` is the only place a slider key is spelled."""
    with pytest.raises(MeasurementError, match="not a slider key"):
        a_verdict(axis="wing_angle").validate()


def test_a_verdict_with_no_reason_is_refused():
    with pytest.raises(MeasurementError, match="no reason"):
        a_verdict(why="  ").validate()


def test_a_better_verdict_supersedes_without_deleting_the_old_one(store):
    """Append-only: why the old instrument was blind outlives the call."""
    store.record_verdict(a_verdict(
        verdict="unresolvable", direction="up",
        instrument="rear_wheel_speed_split", instrument_floor=None,
        why="the split never moved"))
    store.record_verdict(a_verdict())

    assert store.verdict_for(CAR, "lsd_a", CIRCUIT).verdict == "refuted"
    history = store.verdicts(car_name=CAR, axis="lsd_a")
    assert [v.verdict for v in history] == ["refuted", "unresolvable"]


def test_a_circuit_verdict_wins_over_a_car_wide_one(store):
    store.record_verdict(a_verdict(circuit_key=None, verdict="confirmed",
                                   direction="up", why="car-wide"))
    store.record_verdict(a_verdict())
    assert store.verdict_for(CAR, "lsd_a", CIRCUIT).verdict == "refuted"
    assert store.verdict_for(CAR, "lsd_a", None).verdict == "confirmed"
    # A circuit with nothing of its own falls back to the car-wide row rather
    # than reporting untested, which would hide a real finding.
    assert store.verdict_for(CAR, "lsd_a", "spa-francorchamps").verdict \
        == "confirmed"


# -------------------------------------------- the question, in one call

def test_untested_axes_answers_the_question_in_one_call(store):
    store.save_range_record(_a_range_record())
    store.record_verdict(a_verdict())
    store.record_verdict(a_verdict(axis="rh_r", verdict="unresolvable",
                                   why="inside the floor"))

    board = store.untested_axes(CAR, CIRCUIT)
    assert board["axesFrom"] == "range record"
    assert board["settled"] == {"lsd_a": "refuted"}
    # **Tried, and the instrument could not see it** is its own bucket: it
    # wants a different instrument, not another test.
    assert board["unresolvable"] == ["rh_r"]
    assert "rh_f" in board["untested"]
    assert "lsd_a" not in board["untested"]


def test_the_axis_list_says_where_it_came_from(store):
    """A car with no range record still answers, and says which list it used."""
    board = store.untested_axes("A Car Nobody Measured", CIRCUIT)
    assert board["axesFrom"].startswith("shipped vocabulary")
    assert "rh_r" in board["untested"]
    assert board["settled"] == {}


def _a_range_record():
    from pitcrew.setup.ranges import RangeRecord
    return RangeRecord(
        car_name=CAR, measured_date="2026-08-11", verified=True,
        game_version="1.71",
        ranges={"rh_f": [55, 80], "rh_r": [60, 90], "lsd_a": [5, 60],
                "lsd_b": [5, 60], "cam_f": [0, 6]})


# ------------------------------------------------- no setup values, anywhere

def test_a_config_reference_carrying_a_slider_value_is_refused():
    """⛔ `brain/car-state/<car>-<circuit>.md` is the only place one may live.

    A convenient label is how the second copy gets in, and two copies of a
    setup is two setups — the defect removed on 5 Sep after five sessions ran
    against the wrong sheet.
    """
    for smuggled in ("rh_r=64", "lsd_a 8", "rev B, bb:-1"):
        with pytest.raises(MeasurementError, match="slider value"):
            a_measurement(config_ref=smuggled).validate()


def test_a_pointer_that_is_only_a_pointer_is_accepted():
    for legitimate in ("huracan-daytona#s145", "rev-b", "a1b2c3d4",
                       "shelby-deep-forest#s133-138"):
        a_measurement(config_ref=legitimate).validate()


def test_neither_table_has_a_column_for_a_setup_value(store):
    """The structural half of the same rule.

    A per-slider column would be a place for one to land whether or not
    anything wrote there today.
    """
    from pitcrew.setup.vocabulary import SETUP_KEYS

    keys = {k.key for k in SETUP_KEYS}
    for table in ("measurement", "verdict"):
        columns = {r[1] for r in
                   store._conn.execute(f"PRAGMA table_info({table})")}
        # `verdict.axis` NAMES an axis; nothing anywhere holds its value.
        assert not (columns & keys), (table, columns & keys)


# --------------------------------------------------------- the floor, in use

def test_resolves_says_i_cannot_tell_rather_than_no_change():
    """**Never False for want of a floor.**

    "I cannot tell" and "the change did nothing" are the two answers this
    whole record exists to keep apart, and collapsing them is how the split
    closed an axis that was open.
    """
    a = a_measurement(value=0.00788)
    b = a_measurement(value=0.00724)
    # 0.00064 apart, against a floor of 0.00104.
    assert a.resolves(b) is False
    c = a_measurement(value=0.00554)
    assert b.resolves(c) is True                      # 0.00170, 1.6x the floor
    # The floor belongs to the instrument, so one row carrying it answers
    # for the pair. With it on neither row there is no answer to give.
    blind = a_measurement(value=0.5, noise_floor=None, floor_method=None)
    assert blind.resolves(a) is True
    also_blind = a_measurement(value=0.6, noise_floor=None, floor_method=None)
    assert blind.resolves(also_blind) is None


def test_untested_is_synthesised_and_never_stored(store):
    """It costs nothing to be complete and it can never go stale."""
    answer = untested(CAR, "de_r", CIRCUIT)
    assert answer.id is None
    assert store._conn.execute(
        "SELECT COUNT(*) FROM verdict").fetchone()[0] == 0


# ------------------------------------------------------------- the back-fill

def test_the_backfill_lands_the_rows_that_were_written_into_prose(tmp_path):
    """The archive starts non-empty, and running it twice does not double it.

    Every figure here already existed in `brain/car-state/huracan-daytona.md`
    or the 8 Sep Shelby memory. The point of the test is not the numbers - it
    is that the numbers can be got back out, joined to the verdict that rests
    on them, without deriving anything from the frames again.
    """
    from tools.backfill_measurements import DAYTONA, HURACAN, run

    store = Store(tmp_path / "backfill.db")
    try:
        first = run(store, apply=True)
        assert first["measurements"] > 0 and first["verdicts"] == 3

        again = run(store, apply=True)
        assert again["measurements"] == 0, "the back-fill is not idempotent"
        assert again["verdicts"] == 0
        assert again["measurementsSkipped"] == first["measurements"]

        # The three rotation-index rows at the T5 exit, and the floor they
        # are all judged against.
        rows = store.measurements(car_name=HURACAN, circuit_key=DAYTONA,
                                  metric="on_power_rotation_index",
                                  zone="T5 exit")
        assert sorted(round(r.value, 5) for r in rows) == [0.00554, 0.00724,
                                                           0.00788]
        assert {r.noise_floor for r in rows} == {0.00104}
        assert {r.n for r in rows} == {15, 2, 3}

        # A→B is inside the floor and B→C is not. That difference is the
        # whole 8 Sep finding and it now comes out of the store rather than
        # out of a paragraph.
        by_label = {r.config_label: r for r in rows}
        assert by_label["A"].resolves(by_label["B"]) is False
        assert by_label["B"].resolves(by_label["C"]) is True

        # The channels measured beside it carry NO floor, and null is what
        # that has to read as.
        scrub = store.measurements(car_name=HURACAN,
                                   metric="front_scrub_t5_exit")
        assert scrub and all(r.noise_floor is None for r in scrub)

        # The verdict that had to be retired is still on file under the axis
        # it was wrong about, with the instrument that could not see it.
        history = store.verdicts(car_name=HURACAN, circuit_key=DAYTONA,
                                 axis="lsd_a")
        assert [v.verdict for v in history] == ["refuted", "unresolvable"]
        retired = history[-1]
        assert retired.instrument == "rear_wheel_speed_split"
        assert retired.instrument_floor is None
        assert history[0].measurement_ids, (
            "a verdict that rests on nothing is the defect, not the fix")
    finally:
        store.close()


def test_the_backfill_writes_no_setup_value_anywhere(tmp_path):
    """⛔ Every row went through `validate`, and this is the belt to its braces.

    The write-up these rows came from says "rh 70 / lsd_a 14" in its own
    table. What reaches the database is `huracan-daytona#s143`.
    """
    from pitcrew.engineer.measurements import _LOOKS_LIKE_A_SETTING
    from tools.backfill_measurements import run

    store = Store(tmp_path / "backfill.db")
    try:
        run(store, apply=True)
        for row in store.measurements():
            for text in (row.config_ref, row.config_label, row.note):
                assert not (text and _LOOKS_LIKE_A_SETTING.search(text)), text
    finally:
        store.close()


def test_the_backfilled_verdicts_quote_no_absolute_slider_value_either(tmp_path):
    """The prose half of the same rule.

    `why` is written for a human and describes what was tested, so it says
    "a six-click step DOWN on lsd_a" rather than the two numbers - which are
    in `brain/car-state/huracan-daytona.md` and are there once.
    """
    from pitcrew.engineer.measurements import _LOOKS_LIKE_A_SETTING
    from tools.backfill_measurements import verdicts

    for verdict in verdicts({}):
        assert not _LOOKS_LIKE_A_SETTING.search(verdict.why), verdict.why
