"""What has been measured on this car, and which axes nobody has ever tried.

The read side of `measurement` and `verdict`. Written because on 8 Sep 2026
two calls went wrong for want of exactly these two answers:

* **"Has this axis ever been tested on this car?"** Ride height had never been
  A/B'd on any car in the programme and there was no way to find that out.
  `--board` is that question, and `untested` is a real answer rather than an
  empty result set.
* **"What instrument produced that refutation, and can it resolve the axis at
  all?"** `lsd_a` was recorded as refuted on the strength of a rear wheel-speed
  split that then sat at a median of 0.0000 through a six-click change of that
  very axis. `--axis` prints the verdict *with* its instrument and that
  instrument's floor, because a verdict without them cannot be checked.

⛔ **Nothing here prints a setup value**, because nothing stores one.
`config` is a pointer into `brain/car-state/<car>-<circuit>.md`, which is the
only place the sliders are written down (`CLAUDE.md` §1a). To find out what
differs between config A and config B, open that file.

    python tools/axis_board.py --board --car "Lamborghini Huracan GT3 '15" \
        --circuit daytona-international-speedway-road-course
    python tools/axis_board.py --axis lsd_a --car "..." --circuit "..."
    python tools/axis_board.py --metric on_power_rotation_index
    python tools/axis_board.py --cars
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pitcrew.store.db import DEFAULT_DB_PATH, Store          # noqa: E402


def _floor(row) -> str:
    """A floor, or the fact that there is not one.

    **Never printed as 0.** A floor of zero says every difference is
    resolvable; a floor of none says nobody established one. Those are
    opposite claims and the whole record exists to keep them apart.
    """
    if row.noise_floor is None:
        return "floor: NOT ESTABLISHED"
    return f"floor {row.noise_floor:g} ({row.floor_method or 'method not stated'})"


def _n(row) -> str:
    if row.n is None:
        return "n not recorded"
    return f"n={row.n} {row.n_basis or '(basis not stated)'}"


def show_measurements(store: Store, args) -> int:
    rows = store.measurements(car_name=args.car, circuit_key=args.circuit,
                              metric=args.metric, zone=args.zone,
                              limit=args.limit)
    if not rows:
        print("no measurements match")
        return 0
    for row in rows:
        where = " · ".join(x for x in (row.circuit_key, row.zone) if x)
        config = row.config_label or row.config_ref or "config not stated"
        print(f"[{row.id}] {row.metric} = {row.value:g} {row.unit}"
              f"   [{row.source}]")
        print(f"      {row.car_name}{'  ·  ' + where if where else ''}")
        print(f"      config {config}"
              f"{'  (' + row.config_ref + ')' if row.config_label and row.config_ref else ''}")
        print(f"      {_n(row)} · {_floor(row)}")
        detail = [x for x in (row.measured_on,
                              f"sessions {list(row.session_ids)}"
                              if row.session_ids else None,
                              row.tool, row.game_version) if x]
        if detail:
            print("      " + " · ".join(str(d) for d in detail))
        if row.note:
            print(f"      {row.note}")
        print()
    return 0


def show_axis(store: Store, args) -> int:
    current = store.verdict_for(args.car, args.axis, args.circuit)
    history = store.verdicts(car_name=args.car, axis=args.axis)
    print(f"{args.axis} on {args.car}"
          f"{' at ' + args.circuit if args.circuit else ''}")
    print(f"  ⇒ {current.verdict.upper()}"
          f"{' (' + current.direction + ')' if current.direction else ''}")
    print(f"     instrument: {current.instrument or 'none named'}"
          + (f", floor {current.instrument_floor:g}"
             if current.instrument_floor is not None else
             ", floor NOT ESTABLISHED"))
    print(f"     {current.why}")
    if current.measurement_ids:
        print(f"     rests on measurements {list(current.measurement_ids)}")
    if len(history) > 1:
        print("\n  history, newest first:")
        for row in history:
            print(f"    [{row.id}] {row.decided_on or '?'} "
                  f"{row.verdict}"
                  f"{'/' + row.direction if row.direction else ''} "
                  f"on {row.instrument or 'no instrument'} — {row.why[:90]}")
    return 0


def show_board(store: Store, args) -> int:
    board = store.untested_axes(args.car, args.circuit)
    print(f"{board['car']}"
          f"{' at ' + board['circuit'] if board['circuit'] else ''}"
          f"   (axes from the {board['axesFrom']})")
    print(f"\n  NEVER TESTED ({len(board['untested'])}):")
    print("    " + (", ".join(board["untested"]) or "none - every axis has "
                                                    "been tried"))
    if board["unresolvable"]:
        print(f"\n  TRIED, INSTRUMENT COULD NOT SEE IT "
              f"({len(board['unresolvable'])}):")
        print("    " + ", ".join(board["unresolvable"]))
        print("    ⇒ these want a different instrument, not another test")
    if board["settled"]:
        print(f"\n  SETTLED ({len(board['settled'])}):")
        for axis, verdict in sorted(board["settled"].items()):
            print(f"    {axis:8s} {verdict}")
    return 0


def show_cars(store: Store, _args) -> int:
    rows = store._query(
        "SELECT car_name, circuit_key, COUNT(*) AS n FROM measurement "
        "GROUP BY car_name, circuit_key ORDER BY n DESC")
    if not rows:
        print("no measurements on file")
    for row in rows:
        print(f"{row['n']:5d}  {row['car_name']}  "
              f"{row['circuit_key'] or '(no circuit)'}")
    rows = store._query(
        "SELECT car_name, circuit_key, COUNT(*) AS n FROM verdict "
        "GROUP BY car_name, circuit_key ORDER BY n DESC")
    print()
    for row in rows:
        print(f"{row['n']:5d} verdicts  {row['car_name']}  "
              f"{row['circuit_key'] or '(no circuit)'}")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--db", default=str(DEFAULT_DB_PATH))
    parser.add_argument("--car")
    parser.add_argument("--circuit")
    parser.add_argument("--axis")
    parser.add_argument("--metric")
    parser.add_argument("--zone")
    parser.add_argument("--limit", type=int, default=40)
    parser.add_argument("--board", action="store_true",
                        help="which axes on this car have never been tested")
    parser.add_argument("--cars", action="store_true",
                        help="what the two tables hold, by car and circuit")
    args = parser.parse_args(argv)

    store = Store(args.db)
    try:
        if args.cars:
            return show_cars(store, args)
        if args.board or (args.car and not args.axis and not args.metric
                          and not args.zone):
            if not args.car:
                parser.error("--board needs a --car")
            return show_board(store, args)
        if args.axis:
            if not args.car:
                parser.error("--axis needs a --car")
            return show_axis(store, args)
        return show_measurements(store, args)
    finally:
        store.close()


if __name__ == "__main__":
    raise SystemExit(main())
