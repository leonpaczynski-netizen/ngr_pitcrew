"""Find setup revisions the knowledge base issued and the app never received.

    python tools/check_setup_sheets.py

**The highest-severity defect in the loop, and until now it was undetectable.**
`15-pitcrew-detector-audit.md` §4 logged the `setup` block as stale three
sessions out of three, and on the third it would have produced a fully coherent
diagnosis of a car that was not on the circuit — every delta, every "as run"
column and every ranked cost computed against the wrong setup.

The app's own sheet selection is not at fault: `Store.sheet_for` returns the
most recent sheet for the purpose, and it does. The fault is upstream of it. A
revision is written by the tune builder, typed into GT7 by the driver, and
**never filed into Pit Crew** — so the app is faithfully reporting the newest
sheet it has, which is not the newest sheet that exists. Nothing inside the app
can see that, because the missing sheet is missing.

Now that `brain/` is in the repository, it can. The setup documents carry their
date, car and revision in the filename, so the two records can be compared
directly: *what did the knowledge base issue, and did the app ever get it?*

**This reports; it never writes.** Filing a sheet means transcribing values a
human read off a screen, and inventing one from a filename would be exactly the
class of error the whole exercise exists to prevent.
"""
from __future__ import annotations

import datetime as dt
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from pitcrew.store.db import Store                           # noqa: E402
from read_setup_document import read_race_sheet              # noqa: E402

SETUPS = REPO / "brain" / "_inbox" / "setups"

# A filename is `YYYY-MM-DD-<car>-<track>[-revX].md`. The car token is matched
# against the cars that actually appear on events, so a fourth car needs no
# edit here - only that its documents are named after it. Matching against the
# whole catalogue does not work: "huracan" is three Lamborghinis.
NAME = re.compile(r"^(\d{4}-\d{2}-\d{2})[-_](.+?)\.md$", re.I)


def car_tokens(name: str) -> set[str]:
    """The words of a car's name that might appear in a filename."""
    cleaned = re.sub(r"[^a-z0-9 ]", " ", name.lower())
    skip = {"gt3", "gt350r", "the", "and", ""}
    return {word for word in cleaned.split()
            if len(word) > 2 and word not in skip and not word.isdigit()}


def issued(cars: list[str]) -> dict[str, list[tuple[dt.date, str]]]:
    """Every setup document, by the car it names."""
    out: dict[str, list[tuple[dt.date, str]]] = {car: [] for car in cars}
    unmatched = []
    for path in sorted(SETUPS.glob("*.md")):
        found = NAME.match(path.name)
        if not found:
            continue                       # 00-PRE-1.71-NOTICE.md and friends
        when = dt.date.fromisoformat(found.group(1))
        slug = found.group(2).lower()
        hit = [car for car in cars
               if any(token in slug for token in car_tokens(car))]
        if len(hit) == 1:
            out[hit[0]].append((when, path.name))
        else:
            unmatched.append((path.name, hit))
    for name, hit in unmatched:
        print(f"  ? {name} matched {len(hit)} cars - not attributed")
    return out


def main() -> int:
    if not SETUPS.is_dir():
        raise SystemExit(f"no setup documents at {SETUPS}")

    store = Store()
    try:
        # **The cars actually raced, not the catalogue.** Matching filename
        # tokens against all 600 catalogued cars made "huracan" ambiguous
        # between three Lamborghini variants and attributed nothing.
        cars = sorted({(e.get("car_name") or "") for e in store.list_events()}
                      - {""})
        by_car = issued(cars)
        problems = 0

        for car in sorted(by_car):
            docs = sorted(by_car[car])
            sheets = store.list_setup_sheets(car)
            if not docs and not sheets:
                continue

            newest_doc = docs[-1] if docs else None
            newest_sheet = _newest_sheet(store, car)

            print(f"\n{car}")
            print(f"  knowledge base: "
                  + (f"{newest_doc[0]}  {newest_doc[1]}" if newest_doc
                     else "no setup documents"))
            print(f"  app holds:      "
                  + (f"{newest_sheet[0]}  {newest_sheet[1]!r} "
                     f"({len(sheets)} sheet{'' if len(sheets) == 1 else 's'})"
                     if newest_sheet else "no sheets"))

            if not (newest_doc and newest_sheet):
                continue

            # **Compare the VALUES, not the dates.** The first version of this
            # compared dates alone and cried wolf on the RSR: its Rev C says in
            # its own first line "UNCHANGED from Rev B", and every one of its
            # 22 values already matched what the app held under the older name.
            # A checker that raises a false alarm gets ignored, and then it
            # misses the real one.
            doc_values, doc_gears, _ = read_race_sheet(
                (SETUPS / newest_doc[1]).read_text(encoding="utf-8"))
            stored = store.get_setup_sheet(_sheet_id(store, car))
            if len(doc_values) < 18 or stored is None:
                print(f"  ?? could not read the sheet out of {newest_doc[1]} "
                      f"({len(doc_values)} of 22 values) - not compared")
                continue

            keys = sorted(set(doc_values) | set(stored.values))
            diffs = [(k, stored.values.get(k), doc_values.get(k)) for k in keys
                     if doc_values.get(k) is None or stored.values.get(k) is None
                     or abs(float(stored.values[k]) - doc_values[k]) > 1e-6]

            if not diffs:
                print(f"  values identical - the app holds this revision's "
                      f"numbers under the older name. Nothing to file.")
                continue

            problems += 1
            print(f"  ** {len(diffs)} value{'' if len(diffs) == 1 else 's'} differ "
                  f"from {newest_doc[1]}:")
            for key, app_value, doc_value in diffs:
                print(f"       {key:<8} app has {app_value!r:>8}   "
                      f"the revision says {doc_value!r:>8}")
            affected = [
                s for s in _sessions_for_car(store, car)
                if s["started_at"][:10] >= newest_doc[0].isoformat()]
            if affected:
                print(f"     {len(affected)} session"
                      f"{'' if len(affected) == 1 else 's'} recorded since, all "
                      f"exporting the older values:")
                for s in affected[:6]:
                    print(f"       session {s['id']}  {s['kind']:<8} "
                          f"{s['started_at']}")

        print()
        if problems:
            print(f"{problems} car{'' if problems == 1 else 's'} whose stored "
                  f"sheet does not match the revision that was issued.")
            print("Confirm which values were actually in the car, then file them "
                  "on the Event screen - the export presents the stored sheet as "
                  "the setup as run.")
        else:
            print("Every stored sheet matches the revision issued for it.")
        return 1 if problems else 0
    finally:
        store.close()


def _sheet_id(store, car: str) -> int | None:
    rows = store._query(
        "SELECT id FROM setup_sheets WHERE car_name = ? AND purpose = 'race' "
        "ORDER BY updated_at DESC, id DESC LIMIT 1", (car,))
    return rows[0]["id"] if rows else None


def _newest_sheet(store, car: str) -> tuple[str, str] | None:
    """(date, name) of the car's most recently touched sheet.

    Read from the table rather than the dataclass, which does not carry the
    timestamp - and the timestamp is the whole question here.
    """
    rows = store._query(
        "SELECT sheet_name, updated_at FROM setup_sheets WHERE car_name = ? "
        "ORDER BY updated_at DESC, id DESC LIMIT 1", (car,))
    if not rows:
        return None
    return (rows[0]["updated_at"] or "")[:10], rows[0]["sheet_name"]


def _sessions_for_car(store, car: str) -> list[dict]:
    out = []
    for event in store.list_events():
        if (event.get("car_name") or "") != car:
            continue
        out.extend(store.list_sessions(event["id"]))
    return sorted(out, key=lambda s: s["started_at"])


if __name__ == "__main__":
    raise SystemExit(main())
