"""The numbers that were written into prose on 7-8 Sep 2026, as rows.

Every figure here already exists in `brain/car-state/huracan-daytona.md`,
`brain/RECONCILIATION.md` or the 8 Sep Shelby memory. It is copied in once so
the store starts useful, and so the next session compares against it instead of
deriving it again from the frames.

**Idempotent.** A row is skipped where the same car, circuit, metric, zone and
config reference are already on file, so this can be run twice without doubling
the archive. Nothing is ever updated in place: both tables are append-only.

    python tools/backfill_measurements.py --db path/to/copy.db --dry-run
    python tools/backfill_measurements.py --apply

⛔ **Not one of these rows carries a setup value.** Where the write-up said
"rh 70 / lsd_a 14" the row says `config_ref='huracan-daytona#s143'` and the
values stay in the car-state file, which is the only place they may be written
(`CLAUDE.md` §1a). That is why the configs are labelled A, B and C here: to
learn what A and B differ by, open the file.

**What is deliberately NOT back-filled.** Verdicts for the Shelby's axes. The
8 Sep braking table is three circuits with three different sheets, and its own
memory says so - *"suggestive, not measured; the clean test is within one
circuit"*. Writing `confirmed` off it would be the same defect as the `lsd_a`
refutation it is meant to prevent, so those axes stay `untested`, which they
are.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pitcrew.engineer.measurements import Measurement, Verdict  # noqa: E402
from pitcrew.store.db import DEFAULT_DB_PATH, Store              # noqa: E402

HURACAN = "Lamborghini Huracán GT3 '15"
SHELBY = "Ford Shelby GT350R '16"
DAYTONA = "daytona-international-speedway-road-course"
DEEP_FOREST = "deep-forest-raceway-full-course"
RBR = "red-bull-ring-short-track"
ROAD_ATLANTA = "michelin-raceway-road-atlanta-full-course"

# The instrument the 8 Sep session built and calibrated: median |yaw rate| per
# degree of lock, throttle >60%, >60 km/h, lock >10 deg, all four wheels on
# tarmac. The floor was taken by splitting one session's clean laps odd/even -
# same car, same day, same setup - which is the only split that holds
# everything but chance constant.
ROTATION = "on_power_rotation_index"
ROTATION_FLOOR_METHOD = ("odd/even split of the 15 clean race laps, same car "
                         "and same day, session 143")

# ---------------------------------------------------------------------------
# 1. On-power rotation index, Huracan at Daytona, three configurations.
#    car-state 8 Sep, the table under "session 145, lsd_a 14 -> 8".

_ROTATION_ROWS = [
    # (config_ref, label, sessions, date, n, T3 value, T5 value)
    ("huracan-daytona#s143", "A", (143,), "2026-09-07", 15, 0.00672, 0.00788),
    ("huracan-daytona#s144", "B", (144,), "2026-09-08", 2, 0.00559, 0.00724),
    ("huracan-daytona#s145", "C", (145,), "2026-09-08", 3, 0.00555, 0.00554),
]
# Per-zone floors, both from the same odd/even split.
_ROTATION_FLOORS = {"T3 exit": 0.00058, "T5 exit": 0.00104}


def rotation_rows() -> list[Measurement]:
    rows = []
    for ref, label, sessions, date, n, t3, t5 in _ROTATION_ROWS:
        for zone, value in (("T3 exit", t3), ("T5 exit", t5)):
            rows.append(Measurement(
                car_name=HURACAN, circuit_key=DAYTONA, metric=ROTATION,
                value=value, unit="ratio", scope="corner", zone=zone,
                source="DERIVED", config_ref=ref, config_label=label,
                n=n, n_basis="clean laps",
                noise_floor=_ROTATION_FLOORS[zone],
                floor_method=ROTATION_FLOOR_METHOD,
                tool="race engineer, 8 Sep session",
                session_ids=sessions, game_version="1.71", measured_on=date,
                note="median |yaw rate| per degree of lock, throttle >60%, "
                     ">60 km/h, lock >10 deg, all four on tarmac"))
    return rows


# ---------------------------------------------------------------------------
# 2. Front scrub and rear spin at the T5 exit, the two channels that moved
#    with the rotation index and say which end let go.

_SCRUB_ROWS = [
    ("huracan-daytona#s143", "A", (143,), "2026-09-07", 15, 0.0079, 0.0264),
    ("huracan-daytona#s144", "B", (144,), "2026-09-08", 2, 0.0082, 0.0340),
    ("huracan-daytona#s145", "C", (145,), "2026-09-08", 3, 0.0099, 0.0304),
]


def scrub_rows() -> list[Measurement]:
    rows = []
    for ref, label, sessions, date, n, scrub, spin in _SCRUB_ROWS:
        for metric, value in (("front_scrub_t5_exit", scrub),
                              ("rear_spin_t5_exit", spin)):
            rows.append(Measurement(
                car_name=HURACAN, circuit_key=DAYTONA, metric=metric,
                value=value, unit="ratio", scope="corner", zone="T5 exit",
                source="DERIVED", config_ref=ref, config_label=label,
                n=n, n_basis="clean laps",
                # ⛔ No floor was taken for these two. NULL, never 0.0: the
                # odd/even split was run on the rotation index and on nothing
                # else, so a difference in scrub cannot be called resolvable.
                noise_floor=None, floor_method=None,
                tool="race engineer, 8 Sep session",
                session_ids=sessions, game_version="1.71", measured_on=date,
                note="measured beside the rotation index on the same frames; "
                     "no noise floor was established for this channel"))
    return rows


# ---------------------------------------------------------------------------
# 3. T1 opposite-lock rate across the ride-height change.
#    car-state 7 Sep and the 8 Sep prediction table.

def opposite_lock_rows() -> list[Measurement]:
    return [
        Measurement(
            car_name=HURACAN, circuit_key=DAYTONA,
            metric="opposite_lock_lap_rate", value=8 / 31,
            unit="fraction-of-laps", scope="corner", zone="T1",
            source="DERIVED", config_ref="huracan-daytona#pre-s144",
            config_label="A", n=31, n_basis="clean laps",
            noise_floor=None, floor_method=None,
            tool="race engineer, 7 Sep session", game_version="1.71",
            measured_on="2026-09-07",
            note="8 laps of 31 carried opposite lock at T1. The session list "
                 "was not carried with the figure in the write-up, so no "
                 "session ids are claimed here"),
        Measurement(
            car_name=HURACAN, circuit_key=DAYTONA,
            metric="opposite_lock_lap_rate", value=0.0,
            unit="fraction-of-laps", scope="corner", zone="T1",
            source="DERIVED", config_ref="huracan-daytona#s144",
            config_label="B", n=2, n_basis="clean laps",
            noise_floor=None, floor_method=None,
            tool="race engineer, 8 Sep session", session_ids=(144,),
            game_version="1.71", measured_on="2026-09-08",
            note="0 frames on both laps. NOT EVIDENCE: 0 of 2 has p about "
                 "0.55 under the old 26% rate, and needs about 10 laps"),
    ]


# ---------------------------------------------------------------------------
# 4. Dynamic rake: its level either side of the change, and what fuel does to
#    it. The slope is what refuted `04-race-vs-qualifying.md` §2.3 on this car.

def rake_rows() -> list[Measurement]:
    return [
        Measurement(
            car_name=HURACAN, circuit_key=DAYTONA,
            metric="dynamic_rake_vs_fuel", value=0.0060, unit="mm/L",
            scope="session", source="DERIVED",
            config_ref="huracan-daytona#pre-s144", config_label="A",
            n=31, n_basis="clean laps", noise_floor=None, floor_method=None,
            tool="race engineer, 7 Sep session", game_version="1.71",
            measured_on="2026-09-07",
            note="+0.55 mm across a full-to-empty 92 L swing. The 'a full "
                 "tank squats the rear and kills your rake' mechanism is NOT "
                 "present on this car - measured, not argued"),
        Measurement(
            car_name=HURACAN, circuit_key=DAYTONA,
            metric="dynamic_rake", value=10.51, unit="mm", scope="session",
            source="DERIVED", config_ref="huracan-daytona#pre-s144",
            config_label="A", n=31, n_basis="clean laps",
            noise_floor=None, floor_method=None,
            tool="race engineer, 7 Sep session", game_version="1.71",
            measured_on="2026-09-07",
            note="rear minus front suspension height, full throttle before "
                 "the banking. Range 8.98-12.81 over the 31 laps"),
        Measurement(
            car_name=HURACAN, circuit_key=DAYTONA,
            metric="dynamic_rake", value=16.6, unit="mm", scope="session",
            source="DERIVED", config_ref="huracan-daytona#s144",
            config_label="B", n=2, n_basis="clean laps",
            noise_floor=None, floor_method=None,
            tool="race engineer, 8 Sep session", session_ids=(144,),
            game_version="1.71", measured_on="2026-09-08",
            note="the rear channel moved +6.1 mm and the front did not "
                 "(273.4 -> 272.6). The channel's sign is inverted relative "
                 "to the slider, so quote the magnitude and the asymmetry, "
                 "never the absolute"),
    ]


# ---------------------------------------------------------------------------
# 5. Shelby braking, three circuits, 150 post-1.71 laps, ABS off.
#    From the 8 Sep memory. Brake >40%, >60 km/h, all four on tarmac.

_SHELBY = [
    # (circuit, sessions, date, n, front slip min, rear slip min, front lock
    #  laps, rear lock laps)
    (ROAD_ATLANTA, (71, 72, 73, 74, 75, 76, 77), "2026-08-23", 41,
     0.781, 0.935, 37, 8),
    (RBR, (93, 94, 98, 99, 100, 101), "2026-08-30", 62, 0.869, 0.965, 44, 0),
    (DEEP_FOREST, (133, 134, 135, 136, 137, 138), "2026-09-06", 47,
     0.663, 0.947, 47, 2),
]

_SHELBY_NOTE = ("brake >40%, >60 km/h, all four on tarmac, ABS off. ⚠ Across "
                "circuits this is suggestive, not measured: different sheets "
                "and different tracks. The clean test is within one circuit")


def shelby_rows() -> list[Measurement]:
    rows = []
    for circuit, sessions, date, n, front, rear, f_lock, r_lock in _SHELBY:
        # ⛔ No `config_ref` for two of these three: there is no car-state
        # file for the Shelby at Road Atlanta or at Red Bull Ring, so what was
        # in the car is not on record anywhere. A pointer at a file that does
        # not exist would read as though it were.
        ref = ("shelby-deep-forest#s133-138"
               if circuit == DEEP_FOREST else None)
        missing = (None if ref else
                   " No car-state file exists for this car at this circuit, "
                   "so the configuration is not on record.")
        for metric, value, unit in (
                ("front_slip_min_braking", front, "ratio"),
                ("rear_slip_min_braking", rear, "ratio"),
                ("front_lock_lap_rate", f_lock / n, "fraction-of-laps"),
                ("rear_lock_lap_rate", r_lock / n, "fraction-of-laps")):
            rows.append(Measurement(
                car_name=SHELBY, circuit_key=circuit, metric=metric,
                value=value, unit=unit, scope="session", source="DERIVED",
                config_ref=ref, n=n, n_basis="clean laps",
                noise_floor=None, floor_method=None,
                tool="race engineer, 8 Sep session", session_ids=sessions,
                game_version="1.71", measured_on=date,
                note=_SHELBY_NOTE + (missing or "")))
    return rows


# ---------------------------------------------------------------------------
# 6. The short-shift trade at Daytona. Reproducible:
#    `python tools/shortshift_trade.py --event 10`.

_TRADE_NOTE = ("fixed-effects fit over 60 laps demeaned within 6 sessions; "
               "the pooled fit is a known artefact and is not this number. "
               "Sign convention is per +1000 rpm of upshift rpm, so a "
               "short-shift moves both figures the other way. Reproduce with "
               "tools/shortshift_trade.py --event 10")


def short_shift_rows() -> list[Measurement]:
    return [
        Measurement(
            car_name=HURACAN, circuit_key=DAYTONA,
            metric="short_shift_fuel_trade", value=3.458,
            unit="L per 1000 rpm", scope="session", source="DERIVED",
            n=60, n_basis="laps, demeaned within 6 sessions",
            # Half the 95% interval [+2.466, +4.449] - the fit's own statement
            # of what it can resolve, which is the honest floor for a slope.
            noise_floor=0.9915,
            floor_method="half-width of the fit's 95% CI [+2.466, +4.449]",
            tool="tools/shortshift_trade.py", game_version="1.71",
            measured_on="2026-09-08", note=_TRADE_NOTE),
        Measurement(
            car_name=HURACAN, circuit_key=DAYTONA,
            metric="short_shift_lap_trade", value=-6.767,
            unit="s per 1000 rpm", scope="session", source="DERIVED",
            n=60, n_basis="laps, demeaned within 6 sessions",
            noise_floor=5.55,
            floor_method="half-width of the fit's 95% CI [-12.317, -1.217]",
            tool="tools/shortshift_trade.py", game_version="1.71",
            measured_on="2026-09-08",
            note=_TRADE_NOTE + ". ⚠ The floor is 5.55 against a value of "
                               "6.767: this slope is barely outside its own "
                               "interval and 60 laps is close to all it can "
                               "say"),
    ]


ALL_MEASUREMENTS = (rotation_rows, scrub_rows, opposite_lock_rows, rake_rows,
                    shelby_rows, short_shift_rows)


# ---------------------------------------------------------------------------
# The verdicts. Three, and only where the source is unambiguous.

def verdicts(ids: dict) -> list[Verdict]:
    """The three axis verdicts the 7-8 Sep sessions actually settled.

    `ids` maps (metric, zone, config_label) to the measurement row id, so a
    verdict points at the rows it rests on rather than restating them.
    """
    def rows(*keys) -> tuple[int, ...]:
        return tuple(ids[k] for k in keys if k in ids)

    return [
        # The one that has to be on record, and the reason the table exists.
        Verdict(
            car_name=HURACAN, circuit_key=DAYTONA, axis="lsd_a",
            direction="up", verdict="unresolvable",
            instrument="rear_wheel_speed_split",
            # ⛔ NULL, not 0.0. No floor was ever established for this
            # channel, and that is precisely why it settled nothing.
            instrument_floor=None,
            decided_on="2026-09-08", game_version="1.71",
            why="RETIRES the 1 Sep refutation. It rested on rear wheel-speed "
                "split, which stayed at a median of 0.0000 across a six-click "
                "change of that very axis while the on-power rotation index "
                "moved to 1.6x "
                "its own floor. A channel that cannot see the change never "
                "refuted the lever - and it only ever tested RAISING it"),
        Verdict(
            car_name=HURACAN, circuit_key=DAYTONA, axis="lsd_a",
            direction="down", verdict="refuted",
            instrument=ROTATION, instrument_floor=0.00104,
            measurement_ids=rows((ROTATION, "T5 exit", "B"),
                                 (ROTATION, "T5 exit", "C"),
                                 ("front_scrub_t5_exit", "T5 exit", "B"),
                                 ("front_scrub_t5_exit", "T5 exit", "C")),
            decided_on="2026-09-08", game_version="1.71",
            why="a six-click step DOWN on lsd_a cost 0.00170 of rotation "
                "index at the T5 exit, "
                "1.6x the odd/even floor and 2.1x the lap-to-lap sd, and "
                "front scrub rose with it (+0.0082 -> +0.0099). On this car "
                "LESS acceleration lock gives LESS rotation on power - the "
                "opposite of the textbook. Driver, unprompted: 'it felt like "
                "it was worse at rotating.' Fuel-corrected lap +2.30 s. "
                "Lowering it is refuted; RAISING it is untested"),
        Verdict(
            car_name=HURACAN, circuit_key=DAYTONA, axis="rh_r",
            direction="down", verdict="unresolvable",
            instrument=ROTATION, instrument_floor=0.00104,
            measurement_ids=rows((ROTATION, "T5 exit", "A"),
                                 (ROTATION, "T5 exit", "B"),
                                 ("dynamic_rake", None, "A"),
                                 ("dynamic_rake", None, "B")),
            decided_on="2026-09-08", game_version="1.71",
            why="a six-click step DOWN on rh_r - the first ride-height A/B "
                "on any car in this programme. It cost 0.00064 of rotation "
                "index at "
                "T5 - INSIDE the 0.00104 floor - and 0.00113 at T3, about at "
                "its floor. The ride height itself is confirmed to have moved "
                "(rear suspension channel +6.1 mm, front unmoved), so this is "
                "the instrument failing to resolve the change and not the car "
                "failing to respond. n=2 laps"),
    ]


def _key(row: Measurement):
    return (row.car_name, row.circuit_key, row.metric, row.zone,
            row.config_ref, row.config_label)


def run(store: Store, *, apply: bool) -> dict:
    wanted = [row for build in ALL_MEASUREMENTS for row in build()]
    for row in wanted:
        row.validate()

    existing = {_key(row): row.id for row in store.measurements()}
    written, skipped, ids = 0, 0, {}
    for row in wanted:
        key = _key(row)
        if key in existing:
            skipped += 1
            ids[(row.metric, row.zone, row.config_label)] = existing[key]
            continue
        if apply:
            ids[(row.metric, row.zone, row.config_label)] = \
                store.record_measurement(row)
        written += 1

    on_file = {(v.car_name, v.circuit_key, v.axis, v.verdict, v.direction)
               for v in store.verdicts()}
    v_written, v_skipped = 0, 0
    for verdict in verdicts(ids):
        verdict.validate()
        if (verdict.car_name, verdict.circuit_key, verdict.axis,
                verdict.verdict, verdict.direction) in on_file:
            v_skipped += 1
            continue
        if apply:
            store.record_verdict(verdict)
        v_written += 1

    return {"measurements": written, "measurementsSkipped": skipped,
            "verdicts": v_written, "verdictsSkipped": v_skipped}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--db", default=str(DEFAULT_DB_PATH))
    parser.add_argument("--apply", action="store_true",
                        help="write. Without it nothing is stored")
    args = parser.parse_args(argv)

    store = Store(args.db)
    try:
        result = run(store, apply=args.apply)
    finally:
        store.close()

    verb = "wrote" if args.apply else "would write"
    print(f"{verb} {result['measurements']} measurements "
          f"({result['measurementsSkipped']} already on file) and "
          f"{result['verdicts']} verdicts "
          f"({result['verdictsSkipped']} already on file)")
    if not args.apply:
        print("dry run - nothing stored. Re-run with --apply")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
