"""Put real names to the drivers the pit wall has been watching.

The wall recognises a driver by the shape of his name on the leaderboard, not
by reading it: GT7's font is proportional and mixed-case, and a guess about
whose car this is corrupts every stop filed against him. So a cluster nobody
has named carries a provisional handle - `Car #1`, `Car #2` - and this is where
those become people.

**Renaming is retroactive.** `rival_stops.driver` is the name rather than an
id, so renaming a driver carries every stop already on file across with him in
the same transaction. Naming `Car #3` as `Rocky` tonight means the two stops he
made last month are Rocky's two stops, and the burn rate reads back over both.

Two provisional handles that turn out to be the same person merge cleanly: give
the second one the name the first already has.

    python -m tools.name_drivers                 # list what needs a name
    python -m tools.name_drivers "Car #3" Rocky  # name one
    python -m tools.name_drivers --teammate Rocky
"""
from __future__ import annotations

import argparse
import sys

from pitcrew.store.db import Store


def show(store) -> int:
    unnamed = store.unnamed_drivers()
    stops = store.rival_stops()
    counts: dict[str, int] = {}
    for row in stops:
        counts[row["driver"]] = counts.get(row["driver"], 0) + 1

    if not unnamed:
        print("Every driver on file has a name.")
    else:
        print("Waiting for a name:\n")
        for row in unnamed:
            print("  %-10s %d race%s on file, %d stop%s watched"
                  % (row["name"], row["races_seen"],
                     "" if row["races_seen"] == 1 else "s",
                     counts.get(row["name"], 0),
                     "" if counts.get(row["name"], 0) == 1 else "s"))
        print("\n  python -m tools.name_drivers \"Car #1\" <their name>")

    named = [n for n in sorted(counts) if not n.startswith("Car #")]
    if named:
        print("\nAlready named:\n")
        for name in named:
            mate = " (teammate)" if name == store.teammate_name() else ""
            print("  %-16s %d stop%s%s"
                  % (name, counts[name], "" if counts[name] == 1 else "s",
                     mate))
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("old", nargs="?", help="the handle to rename")
    parser.add_argument("new", nargs="?", help="the driver's real name")
    parser.add_argument("--teammate", metavar="NAME",
                        help="flag a driver as the teammate")
    parser.add_argument("--db", help="a different archive")
    args = parser.parse_args(argv)

    store = Store(args.db) if args.db else Store()

    if args.teammate:
        store.save_driver(args.teammate, is_teammate=True)
        print("Teammate: %s" % args.teammate)
        return 0

    if args.old and args.new:
        moved = store.rename_driver(args.old, args.new)
        print("%s is now %s. %d stop%s came with him."
              % (args.old, args.new, moved, "" if moved == 1 else "s"))
        return 0

    if args.old and not args.new:
        parser.error("give the new name too")
    return show(store)


if __name__ == "__main__":
    sys.exit(main())
