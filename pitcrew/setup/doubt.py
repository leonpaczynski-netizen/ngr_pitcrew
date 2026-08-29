"""Whether the app's record of what is in the car can be trusted.

**Rank zero of the diagnosis hierarchy, and the app has never once caught it
itself.** The setup record was wrong in five consecutive sessions - a Yas
Marina sheet at Road Atlanta, a v1 sheet against a Rev B car, `bb -1` in the
car against `0` on every sheet on file - and every one of those was found by
the driver mentioning it in passing. `docs/RACE-ENGINEER-CHARTER_2026-08-23.md`
§4.1: *an experiment log whose "before" is wrong is worse than no log*, because
it converts a wrong premise into permanent learning.

The circuit key closed the largest mechanism (`Store.sheet_for` had no circuit,
so a session at Road Atlanta bound itself to the only race sheet on file for
the car). **What was still missing was anything that CHECKS.** This is that.

### Two detectors, and both are ground truth

1. **`gearing.matchesSheet is False`.** The only channel GT7 gives that
   contradicts a setup sheet directly: the gearbox is in the packet, the sheet
   states it, and they either agree or they do not. `None` is not doubt - it
   means the box was never fitted or the sheet has no gears - and reading it
   as doubt would raise an alarm on every session that never reached top gear.

2. **A revision issued and never filed.** `brain/_inbox/setups` holds the
   documents the tune builder wrote; `setup_sheets` holds what the app was
   told. A document newer than the newest sheet on file for that car and
   circuit is a revision that was written, typed into GT7, and never typed
   into here - which is charter B4, confirmed live, and the fault is upstream
   of every line of app code.

### What it deliberately is not

**It does not decide whether the sheet is right.** It decides whether anybody
has checked. Those are different questions and only the second one is
answerable from here.

**It never blocks the capture.** A session not recorded is a session lost and
cannot be re-driven; a sheet can be corrected afterwards and the session
re-bound. What must not leave the building is an *export* carrying a setup the
app has reason to doubt, because that is the one that becomes permanent
learning in a knowledge base. See `export/payload.py`.
"""
from __future__ import annotations

import datetime as dt
import re

from dataclasses import dataclass

from pitcrew.paths import PROJECT_ROOT

# Where the tune builder's documents land. Read-only, and read by filename
# only - the contents are `tools/read_setup_document.py`'s business and that
# reader is deliberately timid about them.
SETUPS = "brain/_inbox/setups"

# `YYYY-MM-DD-<car>-<track>[-revX].md`, the same shape
# `tools/check_setup_sheets.py` matches. Restated rather than imported: `tools`
# is not on the app's import path, and a copy of one regex is cheaper than a
# runtime dependency from the app into the toolbox.
_NAME = re.compile(r"^(\d{4}-\d{2}-\d{2})[-_](.+?)\.md$", re.I)

# The reasons, named so a caller can tell them apart without parsing prose.
GEARBOX = "gearbox-disagrees"
UNFILED = "revision-unfiled"


@dataclass(frozen=True)
class Doubt:
    """What is unverified about the setup record, and why.

    Empty means nothing raised a flag - **not** that the record was verified.
    The distinction is the whole point of `checked`: two of the five failures
    on record would not have been caught by either detector, and an empty
    result that read as a clean bill of health would be the same confident
    wrong answer in a new place.
    """
    reasons: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()

    def __bool__(self) -> bool:
        return bool(self.reasons)

    def describe(self) -> str:
        return " ".join(self.notes)


def gearbox_doubt(gearing: dict | None, disagreeing_sheets=None) -> Doubt:
    """The gearbox on track against the gearbox on the sheet it ran under.

    `matchesSheet` is a tri-state and only `False` is doubt. `None` means one
    side is unknown - no fitted ratios, or a sheet with no gears - and an
    unknown is not a disagreement.

    **`matchesSheet` alone is the wrong question on an event that spans
    revisions, and that mistake refused three real exports.** It takes the
    most recent lap's box and compares it against whichever single sheet the
    merged session carries, so a driver who revised his gearbox mid-event -
    the ordinary way of testing one - read as a wrong setup record. Measured
    on the archive: Yas Marina ran two boxes on two sheets and Watkins Glen
    ran two on two, and **all four matched their own sheets exactly.**

    So where the caller can say which sheets disagree with their OWN laps
    (`analysis.gearing.sheets_disagree`), that is the answer, and an empty
    list clears the doubt however `matchesSheet` came out. The flat boolean is
    the fallback for a caller that cannot group laps by sheet.
    """
    if not gearing or gearing.get("matchesSheet") is not False:
        return Doubt()
    covers = gearing.get("matchesSheetCovers") or "the ratios"

    if disagreeing_sheets is not None:
        if not disagreeing_sheets:
            # Every sheet matched the laps driven on it. The event ran more
            # than one gearbox, which the export already declares in
            # `gearboxChangedMidSession` - a change is a known state, not a
            # wrong record.
            return Doubt()
        named = ", ".join(str(one) for one in disagreeing_sheets)
        return Doubt(
            (GEARBOX,),
            (f"Sheet(s) {named} name a gearbox the laps driven on them did "
             f"not run ({covers}). That is the one setup value the feed can "
             f"check, and it disagrees.",))

    return Doubt(
        (GEARBOX,),
        (f"The gearbox on track does not match the sheet ({covers}). "
         f"That is the one setup value the feed can check, and it disagrees.",))


def unfiled_revisions(store, car_name: str,
                      circuit_key: str | None) -> Doubt:
    """Setup documents newer than the newest sheet the app was ever told.

    **The fault this catches is entirely outside the app**, which is why
    nothing inside it could see it before `brain/` was in the repository: a
    revision is written, typed into GT7, and never filed here, so the app
    faithfully reports the newest sheet it holds and that is not the newest
    sheet that exists.

    Filenames only. Reading the document to decide whether it actually differs
    is `tools/check_setup_sheets.py`'s job and it needs a human to act on the
    answer; here the question is narrower - *is there one the app has not
    seen* - and a date answers it.
    """
    folder = PROJECT_ROOT / SETUPS
    if not folder.is_dir():
        return Doubt()

    sheet = store.sheet_for(car_name, "race", circuit_key)
    if sheet is None:
        sheet = store.sheet_for(car_name, "race")
    filed = _sheet_date(store, sheet)
    if filed is None:
        # No sheet at all is a different fault and a louder one; the export
        # already refuses a payload with no setup block. Reporting "there is
        # a document you have not filed" on top of it would name the smaller
        # of the two problems.
        return Doubt()

    newer = []
    for path in sorted(folder.glob("*.md")):
        match = _NAME.match(path.name)
        if match is None:
            continue
        try:
            issued = dt.date.fromisoformat(match.group(1))
        except ValueError:                                   # pragma: no cover
            continue
        if issued <= filed:
            continue
        # **Both the car and the circuit have to appear**, or every document
        # in the folder is newer than some sheet somewhere and the detector
        # cries wolf on every session. A document that names neither is about
        # another car at another track.
        body = match.group(2).lower()
        if not any(token in body for token in _tokens(car_name)):
            continue
        if circuit_key and not any(token in body
                                   for token in _tokens(circuit_key)):
            continue
        newer.append((issued, path.name))

    if not newer:
        return Doubt()
    issued, name = newer[-1]
    return Doubt(
        (UNFILED,),
        (f"{len(newer)} setup revision(s) issued after the sheet on file "
         f"({filed}), the newest {name} on {issued}. If one of them is in the "
         f"car, every value the app is about to report is the wrong one.",))


def for_event(store, event: dict, gearing: dict | None = None,
              disagreeing_sheets=None) -> Doubt:
    """Everything doubtful about this event's setup record, in one answer.

    **The event, not the session.** `sessions` carries `setup_sheet_id` and
    nothing else about the car or the circuit - both live on the event row, and
    the circuit key is derived from `track` and `layout` rather than stored.
    """
    from pitcrew.analysis.resolve import circuit_key

    car = event.get("car_name") or ""
    track = event.get("track")
    circuit = circuit_key(track, event.get("layout")) if track else None
    found = [gearbox_doubt(gearing, disagreeing_sheets)]
    if car:
        found.append(unfiled_revisions(store, car, circuit))
    reasons, notes = [], []
    for one in found:
        reasons.extend(one.reasons)
        notes.extend(one.notes)
    return Doubt(tuple(reasons), tuple(notes))


def _sheet_date(store, sheet) -> dt.date | None:
    """When the app was told about this sheet.

    **Off the store, not off the dataclass.** `SetupSheet` carries the setup
    and no timestamp - which is right, a filing date is a fact about the
    record rather than about the car - and the first draft of this module read
    `sheet.updated_at` anyway. It does not exist, `getattr` returned None on
    every sheet, and the detector was silent on all eight events on file while
    looking entirely correct.
    """
    if sheet is None or getattr(sheet, "id", None) is None:
        return None
    filed = store.sheet_filed_on(sheet.id)
    if not filed:
        return None
    try:
        return dt.date.fromisoformat(filed)
    except ValueError:                                       # pragma: no cover
        return None


def _tokens(name: str) -> set[str]:
    """The words of a car or circuit that might appear in a filename.

    Short words are dropped: `gt3` and `911` are not, but a two-letter token
    matches inside half the folder. Matching the whole catalogue does not work
    either - "huracan" is three different Lamborghinis - which is why both the
    car AND the circuit have to hit.
    """
    words = re.split(r"[^a-z0-9]+", name.lower())
    return {word for word in words if len(word) > 2}
