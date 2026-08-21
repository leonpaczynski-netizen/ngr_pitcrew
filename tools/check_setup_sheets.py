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

from pitcrew.store.db import Store                           # noqa: E402

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

            if newest_doc and newest_sheet and \
                    newest_doc[0].isoformat() > newest_sheet[0]:
                problems += 1
                gap = (newest_doc[0] - dt.date.fromisoformat(newest_sheet[0])).days
                print(f"  ** NEVER FILED: {newest_doc[1]} is {gap} day"
                      f"{'' if gap == 1 else 's'} newer than anything the app "
                      f"holds.")
                # The sessions that were recorded against the stale sheet, and
                # are therefore exporting the wrong setup as run.
                affected = [
                    s for s in _sessions_for_car(store, car)
                    if s["started_at"][:10] >= newest_doc[0].isoformat()]
                if affected:
                    print(f"     {len(affected)} session"
                          f"{'' if len(affected) == 1 else 's'} recorded since "
                          f"it was issued, all reporting the older sheet:")
                    for s in affected[:6]:
                        print(f"       session {s['id']}  {s['kind']:<8} "
                              f"{s['started_at']}")

        print()
        if problems:
            print(f"{problems} car{'' if problems == 1 else 's'} carrying a "
                  f"revision the app never received.")
            print("File it on the Event screen before diagnosing anything from "
                  "these sessions - the export presents the stored sheet as "
                  "the setup as run.")
        else:
            print("Every issued revision is on file.")
        return 1 if problems else 0
    finally:
        store.close()


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
