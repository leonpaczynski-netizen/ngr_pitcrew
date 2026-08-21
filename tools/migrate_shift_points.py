"""Move the per-gear shift tables out of settings and onto the setup sheets.

    python tools/migrate_shift_points.py
    python tools/migrate_shift_points.py --apply

**Why they moved.** A shift point is a property of the gearbox, not of the car:
change the final drive or one ratio and the rpm worth shifting at moves with it,
so two sheets for the same car want two tables. Keyed by car in a settings file
they were also invisible to everything downstream - they did not travel with the
export, they were not versioned alongside the setup they were measured against,
and nothing could say which sheet a number had been measured on.

**What this will and will not decide.** A table keyed by a car id that resolves
to a car gets written onto that car's most recent race sheet. Anything else -
a table for a car the catalogue does not know, or two tables disagreeing about
one car - is **reported and left alone**. Guessing which gearbox a measurement
was taken on would put a number on a sheet it was never measured against, which
is the whole failure the move exists to fix.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pitcrew import settings as settings_module                # noqa: E402
from pitcrew.setup.sheet import SetupSheet                      # noqa: E402
from pitcrew.settings import shift_point_key                    # noqa: E402
from pitcrew.store.db import Store                              # noqa: E402


def _table(raw) -> dict[int, float]:
    return {int(gear): float(rpm) for gear, rpm in (raw or {}).items()}


def _spell(table: dict[int, float]) -> str:
    return ", ".join(f"g{g} {rpm:.0f}" for g, rpm in sorted(table.items()))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    store = Store()
    try:
        current = settings_module.load(store)
        points = dict(current.beep_shift_points or {})
        if not points:
            print("no shift tables in settings - nothing to move")
            return 0

        cars = [row["name"] for row in store.list_cars()]
        by_car: dict[str, list[tuple[str, dict]]] = {}
        orphans: list[tuple[str, dict]] = []

        for key, raw in points.items():
            table = _table(raw)
            if key.startswith("name:"):
                match = next((c for c in cars if shift_point_key(c) == key), None)
            else:
                car = store.car_by_gt7_id(int(key)) if key.isdigit() else None
                match = car["name"] if car else None
            if match:
                by_car.setdefault(match, []).append((key, table))
            else:
                orphans.append((key, table))

        moved = 0
        for car, entries in sorted(by_car.items()):
            sheet_id = _newest_race_sheet(store, car)
            print(f"\n{car}")
            if sheet_id is None:
                print("  no race sheet on file - left in settings")
                continue
            sheet = store.get_setup_sheet(sheet_id)
            print(f"  newest race sheet: {sheet_id} {sheet.sheet_name!r}")
            for key, table in entries:
                print(f"    [{key}] {_spell(table)}")

            if len(entries) > 1:
                # **Two tables, one car, and they disagree.** The app resolved
                # this by preferring the id-keyed one, which was fine while it
                # was a lookup and is not fine as a migration: writing one onto
                # the sheet would delete the argument.
                print("  ** two tables disagree about this car - LEFT ALONE. "
                      "Decide which gearbox each was measured on.")
                continue
            if sheet.shift_rpm:
                print(f"  sheet already carries {_spell(sheet.shift_rpm)} "
                      f"- left alone")
                continue

            table = entries[0][1]
            print(f"  -> sheet {sheet_id} gets {_spell(table)}")
            moved += 1
            if args.apply:
                store.save_setup_sheet(SetupSheet(
                    car_name=sheet.car_name, sheet_name=sheet.sheet_name,
                    purpose=sheet.purpose, values=sheet.values,
                    gears=sheet.gears, performance=sheet.performance,
                    build=sheet.build, notes=sheet.notes, shift_rpm=table))

        if orphans:
            print("\ntables whose car could not be resolved - LEFT IN SETTINGS:")
            for key, table in orphans:
                print(f"  [{key}] {_spell(table)}")
            print("  These cannot be placed without knowing which car they were "
                  "measured on, and a shift point on the wrong gearbox is worse "
                  "than one nobody moved.")

        print()
        if not args.apply:
            print(f"DRY RUN - {moved} table(s) would move. Re-run with --apply.")
        else:
            print(f"moved {moved} table(s) onto their sheets. The settings copy "
                  f"is left in place as the fallback for a sheet with none.")
        return 0
    finally:
        store.close()


def _newest_race_sheet(store, car: str) -> int | None:
    rows = store._query(
        "SELECT id FROM setup_sheets WHERE car_name = ? AND purpose = 'race' "
        "ORDER BY updated_at DESC, id DESC LIMIT 1", (car,))
    return rows[0]["id"] if rows else None


if __name__ == "__main__":
    raise SystemExit(main())
