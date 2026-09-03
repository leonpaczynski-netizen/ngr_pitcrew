"""Put your existing events into leagues.

Every event on file predates the `series` column, so they are all unlabelled -
which is not broken, but it does pool them into one unnamed league. Until they
are labelled, a rival profile scoped to a series will not find them and a team
mate cannot be named for a league that does not exist yet.

New events get a Series box on the event screen. This is for the backlog.

    python -m tools.series                          # what is unlabelled
    python -m tools.series --set 12 "GT3 League"    # label one event
    python -m tools.series --like Spa "Endurance"   # label everything matching
    python -m tools.series --car 992 "GT3 League"   # label by car

**`--like` and `--car` show what they would do and ask before writing.** They
match on a substring of the event name or the car, and a substring is a blunt
instrument: "Spa" catches a one-off as readily as a championship round.
"""
from __future__ import annotations

import argparse
import sys

from pitcrew.store.db import Store


def show(store) -> int:
    unlabelled = store.events_without_a_series()
    known = store.known_series()

    if known:
        print("Leagues on file:\n")
        for name in known:
            rows = store._query(
                "SELECT COUNT(*) AS n FROM events WHERE series = ?", (name,))
            print("  %-24s %d event%s" % (name, rows[0]["n"],
                                          "" if rows[0]["n"] == 1 else "s"))
        print()

    if not unlabelled:
        print("Every event has a league.")
        return 0

    print("No league yet (%d):\n" % len(unlabelled))
    for event in unlabelled:
        print("  %4s  %-30s %-18s %s"
              % (event["id"], (event["name"] or "")[:30],
                 (event["track"] or "")[:18], event["car_name"] or ""))
    print('\n  python -m tools.series --set <id> "<league>"')
    print('  python -m tools.series --like <text> "<league>"')
    return 0


def _matching(store, like: str | None, car: str | None) -> list[dict]:
    wanted = []
    for event in store.events_without_a_series():
        name = (event["name"] or "").lower()
        which = (event["car_name"] or "").lower()
        if like and like.lower() not in name:
            continue
        if car and car.lower() not in which:
            continue
        wanted.append(event)
    return wanted


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("series", nargs="?", help="the league to apply")
    parser.add_argument("--set", type=int, metavar="ID",
                        help="label one event by id")
    parser.add_argument("--like", metavar="TEXT",
                        help="label every unlabelled event whose name matches")
    parser.add_argument("--car", metavar="TEXT",
                        help="label every unlabelled event in a matching car")
    parser.add_argument("--yes", action="store_true",
                        help="do not ask before a bulk change")
    parser.add_argument("--db", help="a different archive")
    args = parser.parse_args(argv)

    store = Store(args.db) if args.db else Store()

    if args.set is not None:
        if not args.series:
            parser.error("give the league name too")
        store.set_event_series(args.set, args.series)
        print("event %d is now %s" % (args.set, args.series))
        return 0

    if args.like or args.car:
        if not args.series:
            parser.error("give the league name too")
        wanted = _matching(store, args.like, args.car)
        if not wanted:
            print("Nothing unlabelled matches.")
            return 0
        print("Would put %d event%s into %s:\n"
              % (len(wanted), "" if len(wanted) == 1 else "s", args.series))
        for event in wanted:
            print("  %4s  %-30s %s" % (event["id"], (event["name"] or "")[:30],
                                       event["car_name"] or ""))
        # **Shown before it is written.** A substring catches a one-off as
        # readily as a championship round, and an event labelled into the
        # wrong league takes its rival evidence with it.
        if not args.yes:
            answer = input("\nApply? [y/N] ").strip().lower()
            if answer not in ("y", "yes"):
                print("Nothing changed.")
                return 0
        for event in wanted:
            store.set_event_series(event["id"], args.series)
        print("Done: %d event%s in %s."
              % (len(wanted), "" if len(wanted) == 1 else "s", args.series))
        return 0

    return show(store)


if __name__ == "__main__":
    sys.exit(main())
