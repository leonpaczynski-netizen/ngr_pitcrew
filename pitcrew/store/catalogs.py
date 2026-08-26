"""Reference data: GT7 track names, car names, and track station maps.

These are files, not database rows — they are shipped reference data that the
app reads and never writes, so they survive a database reset.  This is the only
thing carried across from the old data layer.
"""
from __future__ import annotations

import functools
import json
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from pitcrew.paths import DATA_DIR
# The complete circuit and layout catalogue, off GT7's own track list. The
# string list in gt7_extra.json is the fallback for a checkout without it, and
# it is incomplete - see `track_layouts`.
TRACK_CATALOGUE_FILE = DATA_DIR / "gt7_tracks.json"
TRACKS_FILE = DATA_DIR / "gt7_extra.json"
CARS_FILE = DATA_DIR / "car_id_map.json"
TRACK_MODELS_DIR = DATA_DIR / "track_models"

# Lifted out of the retired HTML tool by tools/extract_reference.py.  See that
# file for what each one is and why the join keys are what they are.
CAR_REFERENCE_FILE = DATA_DIR / "gt7_cars.json"
CIRCUITS_FILE = DATA_DIR / "gt7_circuits.json"
SYMPTOMS_FILE = DATA_DIR / "gt7_symptoms.json"
RANGE_SEED_FILE = DATA_DIR / "gt7_range_seed.json"
RANGE_PRESETS_FILE = DATA_DIR / "gt7_range_presets.json"
QUICK_REFERENCE_FILE = DATA_DIR / "gt7_quick_reference.json"

STATION_MAP_SUFFIX = ".station_map.json"


def _read(path: Path) -> dict:
    """Reference files are optional: a missing one is an absent section, not a
    crash.  Every read specifies utf-8 — Windows defaults to cp1252, which
    turns the en dashes in the track names into mojibake."""
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


@functools.lru_cache(maxsize=1)
def layout_records() -> tuple[dict, ...]:
    """Every circuit/layout GT7 has, as rows: track, layout, rain, reversible.

    Structured rather than a list of "Base – Layout" strings, because the app
    keeps track and layout in separate fields and splitting a display name
    back apart is how "Sardegna - Road Track" became a track called
    "Sardegna".  Reverse configurations are not rows here: GT7 lists them as a
    property of a layout, and `track_layouts` expands them.

    Every file read here specifies utf-8 explicitly.  Windows defaults to
    cp1252, which silently turns the accented names into mojibake.
    """
    payload = _read(TRACK_CATALOGUE_FILE)
    rows = payload.get("layouts") or []
    return tuple(
        {"track": str(row.get("track", "")).strip(),
         "layout": str(row.get("layout", "")).strip(),
         "type": row.get("type"),
         "lengthM": row.get("lengthM"),
         "reversible": bool(row.get("reversible")),
         # Null, not False, when the catalogue does not say. A circuit added
         # since this was read is unknown, and unknown is not dry.
         "rain": None if row.get("rain") is None else bool(row.get("rain"))}
        for row in rows if str(row.get("track", "")).strip()
    )


@functools.lru_cache(maxsize=1)
def track_names() -> tuple[str, ...]:
    """Every GT7 track/layout name, as GT7 writes them: "Base – Layout".

    Derived from `track_layouts`, so it carries the reverse configurations
    too.  Kept because it is the shape the display name has always had; new
    code wants `layout_records` or `track_layouts` instead.
    """
    names = [f"{base}{LAYOUT_SEPARATOR_SPACED}{layout}"
             for base, layouts in track_layouts().items()
             for layout in layouts]
    return tuple(sorted(set(names)))


@functools.lru_cache(maxsize=1)
def _legacy_track_names() -> tuple[str, ...]:
    """The old string list. Only reached when the catalogue file is absent."""
    if not TRACKS_FILE.exists():
        return ()
    with TRACKS_FILE.open(encoding="utf-8") as handle:
        payload = json.load(handle)
    return tuple(sorted({str(name) for name in payload.get("tracks", [])}))


@functools.lru_cache(maxsize=1)
def cars_by_id() -> dict[int, str]:
    """An ordinal -> car name, out of `car_id_map.json`.

    **These are NOT the ids the telemetry packet carries**, whatever this
    docstring used to say. Measured 17 Aug 2026: the Ford Shelby GT350R '16
    streams `car_id = 3391` - logged to the second at the start of sessions
    42, 43 and 44 - while this file maps `473` to that car and its whole id
    space stops at 712. It is almost certainly an ordinal from an older
    catalogue.

    So nothing may write these numbers into `cars.gt7_car_id`. The game's own
    id is **learned from the stream** the first time a car is driven, and the
    canonical `cars` table starts every row at NULL rather than importing a
    number that measured false. What survives here is the display-name
    fallback, which is all this file was ever reliable for.
    """
    if not CARS_FILE.exists():
        return {}
    with CARS_FILE.open(encoding="utf-8") as handle:
        payload = json.load(handle)
    out: dict[int, str] = {}
    for key, name in payload.items():
        try:
            out[int(key)] = str(name)
        except (TypeError, ValueError):
            continue
    return out


# GT7 writes track names as "Base – Layout" with an en dash. The app keeps
# track and layout in separate fields, so the catalogue is a mapping rather
# than 121 entries that repeat the base name a dozen times.
LAYOUT_SEPARATOR = "–"
LAYOUT_SEPARATOR_SPACED = f" {LAYOUT_SEPARATOR} "
# GT7 offers a reversed configuration of any layout its track list marks
# reversible. It is a different circuit to drive and a different corner
# sequence, so it is offered as its own layout rather than a flag.
REVERSE_SUFFIX = " (Reverse)"


def is_reverse(layout: str | None) -> bool:
    return bool(layout) and layout.strip().endswith(REVERSE_SUFFIX)


@functools.lru_cache(maxsize=1)
def track_layouts() -> dict[str, tuple[str, ...]]:
    """Base track name -> its layouts, in GT7's own order.

    Not sorted within a track: GT7 lists Full Course first and the cut-down
    variants after it, which is the order the driver reads on the console.
    The tracks themselves are sorted, because that list is 41 long and is
    scanned alphabetically.

    This used to be built by splitting the display strings in gt7_extra.json
    on the en dash, and that file held 27 of the 41 circuits. Yas Marina,
    Suzuka, Mount Panorama, Interlagos, Laguna Seca and Brands Hatch among
    others could not be picked at all.
    """
    grouped: dict[str, list[str]] = {}
    for row in layout_records():
        layouts = grouped.setdefault(row["track"], [])
        if row["layout"] and row["layout"] not in layouts:
            layouts.append(row["layout"])
            if row["reversible"]:
                layouts.append(row["layout"] + REVERSE_SUFFIX)

    if not grouped:
        # No catalogue file. Fall back to splitting the legacy strings so a
        # checkout without the data file still offers something.
        for name in _legacy_track_names():
            base, _, layout = name.partition(LAYOUT_SEPARATOR)
            layouts = grouped.setdefault(base.strip(), [])
            if layout.strip() and layout.strip() not in layouts:
                layouts.append(layout.strip())

    return {base: tuple(layouts) for base, layouts in sorted(grouped.items())}


def track_bases() -> tuple[str, ...]:
    return tuple(track_layouts())


def layouts_for(track: str) -> tuple[str, ...]:
    return track_layouts().get(track, ())


@functools.lru_cache(maxsize=1)
def car_specs() -> dict[str, dict]:
    """Every GT7 car the app knows, keyed by its full name.

    `gt7_cars.json` is the merge of the old scraped spec file with the car
    table out of the retired HTML tool, and it is the one the app reads. The
    scraped file is still the fallback so the app runs before the extraction
    tool has been run, but it carries no drivetrain and its classes are
    wrong for Gr.B, Gr.X and VGT.
    """
    reference = _read(CAR_REFERENCE_FILE).get("cars")
    if reference:
        return reference
    return _read(DATA_DIR / "car_specs.json")


def car_spec(car_name: str | None) -> dict | None:
    if not car_name:
        return None
    return car_specs().get(car_name)


# Race classes first, in their own order; road cars last because there are ten
# times as many of them and they are not what a league event usually picks.
CATEGORY_ORDER = ("Gr.1", "Gr.2", "Gr.3", "Gr.4", "Gr.B", "Gr.X", "VGT",
                  "Road Car")


@functools.lru_cache(maxsize=1)
def cars_by_category() -> dict[str, tuple[str, ...]]:
    """Car names grouped by GT7 class.

    A class with no cars in it is absent rather than empty - a heading with
    nothing under it would suggest the data is there when it is not.
    """
    grouped: dict[str, list[str]] = {}
    for name, spec in car_specs().items():
        grouped.setdefault(spec.get("category") or "Road Car", []).append(name)

    ordered: dict[str, tuple[str, ...]] = {}
    for category in CATEGORY_ORDER:
        if grouped.get(category):
            ordered[category] = tuple(sorted(grouped.pop(category)))
    for category in sorted(grouped):
        ordered[category] = tuple(sorted(grouped[category]))
    return ordered


@functools.lru_cache(maxsize=1)
def cars_by_category_and_maker() -> dict[str, dict[str, tuple[str, ...]]]:
    """Car names grouped by GT7 class, then by manufacturer.

    The flat list is 608 cars long. Grouping it by class alone still leaves
    369 road cars under one heading, which is a scroll, not a choice - so the
    maker is the second axis. `Road Car` last for the same reason
    `CATEGORY_ORDER` puts it there.

    A car whose spec carries no maker is filed under `Unknown` rather than
    dropped: a name the driver can no longer reach is worse than a heading
    that admits the gap.
    """
    grouped: dict[str, dict[str, list[str]]] = {}
    for name, spec in car_specs().items():
        category = spec.get("category") or "Road Car"
        maker = spec.get("maker") or "Unknown"
        grouped.setdefault(category, {}).setdefault(maker, []).append(name)

    def _makers(makers: dict[str, list[str]]) -> dict[str, tuple[str, ...]]:
        return {maker: tuple(sorted(makers[maker])) for maker in sorted(makers)}

    ordered: dict[str, dict[str, tuple[str, ...]]] = {}
    for category in CATEGORY_ORDER:
        if grouped.get(category):
            ordered[category] = _makers(grouped.pop(category))
    for category in sorted(grouped):
        ordered[category] = _makers(grouped[category])
    return ordered


def car_name(car_id: int | None) -> str | None:
    if car_id is None:
        return None
    return cars_by_id().get(int(car_id))


def car_names() -> tuple[str, ...]:
    return tuple(sorted(set(cars_by_id().values())))


# ---------------------------------------------------------------- circuits
#
# GT7 sends no track id, so a circuit's reference data cannot be looked up
# from the stream. It is matched to the event's declared track and layout by
# name, through the alias list the extraction tool wrote. A circuit that does
# not match is simply unknown: the prompt says so and omits the section rather
# than attaching another circuit's wear axle to it.


@dataclass(frozen=True)
class Circuit:
    """One row of the circuit reference. Static GT7 data, never measured here."""
    name: str
    length_km: float
    corners: int
    gr3_reference_lap: str
    downforce: str
    mechanical_grip: str
    wear_severity: int
    wear_axle: str
    braking_severity: int
    pit_loss_pct_of_lap: int
    kind: str | None = None

    @classmethod
    def from_dict(cls, payload: dict) -> "Circuit":
        return cls(
            name=payload["name"],
            length_km=payload["lengthKm"],
            corners=payload["corners"],
            gr3_reference_lap=payload["gr3ReferenceLap"],
            downforce=payload["downforce"],
            mechanical_grip=payload["mechanicalGrip"],
            wear_severity=payload["wearSeverity"],
            wear_axle=payload["wearAxle"],
            braking_severity=payload["brakingSeverity"],
            pit_loss_pct_of_lap=payload["pitLossPctOfLap"],
            kind=payload.get("kind"),
        )


def _match_key(text: str) -> str:
    """Names compared without punctuation, accents or dash flavour."""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


@functools.lru_cache(maxsize=1)
def circuits() -> tuple[Circuit, ...]:
    payload = _read(CIRCUITS_FILE).get("circuits") or []
    return tuple(Circuit.from_dict(item) for item in payload)


@functools.lru_cache(maxsize=1)
def _circuits_by_alias() -> dict[str, Circuit]:
    index: dict[str, Circuit] = {}
    for item in _read(CIRCUITS_FILE).get("circuits") or []:
        circuit = Circuit.from_dict(item)
        for alias in item.get("aliases") or [item["name"]]:
            index.setdefault(_match_key(alias), circuit)
    return index


def circuit_for(track: str | None, layout: str | None = None) -> Circuit | None:
    """The reference row for an event's circuit, or None if it is not on file.

    Tried most specific first: "track - layout", then the track on its own.
    A track whose layouts genuinely differ (Big Willow against Streets of
    Willow) therefore never inherits its sibling's data, because the bare
    track name is not an alias of either.
    """
    if not track:
        return None
    index = _circuits_by_alias()
    candidates = [f"{track} {layout}" if layout else None, track]
    for candidate in candidates:
        if not candidate:
            continue
        found = index.get(_match_key(candidate))
        if found is not None:
            return found
    return None


# ---------------------------------------------------------------- symptoms


@functools.lru_cache(maxsize=1)
def symptom_groups() -> tuple[tuple[str, tuple[str, ...]], ...]:
    """The driver's symptom vocabulary, grouped by corner phase.

    Data rather than a hard-coded list because it is a controlled vocabulary
    shared with the knowledge base, and it is expected to grow.
    """
    payload = _read(SYMPTOMS_FILE).get("groups") or []
    return tuple((item["group"], tuple(item["symptoms"])) for item in payload)


def symptoms() -> tuple[str, ...]:
    return tuple(s for _group, items in symptom_groups() for s in items)


# ------------------------------------------------------------ slider ranges


@functools.lru_cache(maxsize=1)
def range_seed_records() -> tuple[dict, ...]:
    """Ranges recorded before the app had anywhere to keep them.

    Seeded into the store once, then never read again — the store is the
    single source of truth for what a car will accept.
    """
    return tuple(_read(RANGE_SEED_FILE).get("records") or [])


@functools.lru_cache(maxsize=1)
def _range_presets() -> dict:
    return _read(RANGE_PRESETS_FILE)


def range_preset(kind: str = "race") -> dict[str, list]:
    """GT7 typical windows for a class of car. NOT this car's limits.

    Anything built on these is estimated, and every prompt that uses them has
    to say so — the difference decides whether a returned sheet can be entered
    without clamping.
    """
    return dict((_range_presets().get("presets") or {}).get(kind) or {})


def range_step(key: str) -> float | None:
    """GT7's slider granularity for a setting — what makes a value "N clicks
    from minimum". None when it is not a slider we have a step for."""
    return (_range_presets().get("steps") or {}).get(key)


def range_label(key: str) -> str | None:
    """The label the retired tool used, which is the one the knowledge base's
    range register is written in. Kept so a range table round-trips."""
    return (_range_presets().get("labels") or {}).get(key)


def range_unit(key: str) -> str:
    return (_range_presets().get("units") or {}).get(key) or ""


def per_car_range_keys() -> tuple[str, ...]:
    """The settings whose limits actually vary between cars.

    ARB, LSD, brake balance and the damper windows are near-universal; ride
    height, natural frequency, downforce and gearing are not.
    """
    return tuple(_range_presets().get("perCar") or ())


# ----------------------------------------------------------- quick reference


@functools.lru_cache(maxsize=1)
def quick_reference() -> dict:
    """The knowledge base's own reference tables, for display only.

    Nothing in the app reads this to decide anything. The app composes
    prompts; it does not give setup advice.
    """
    return _read(QUICK_REFERENCE_FILE)


def _slug(text: str) -> str:
    return "".join(ch.lower() if ch.isalnum() else "_" for ch in text).strip("_")


def station_map_files() -> dict[str, Path]:
    """Track slug -> station map path, for every modelled track on disk."""
    if not TRACK_MODELS_DIR.is_dir():
        return {}
    out: dict[str, Path] = {}
    for path in TRACK_MODELS_DIR.glob(f"*{STATION_MAP_SUFFIX}"):
        out[path.name[:-len(STATION_MAP_SUFFIX)]] = path
    return out


def load_station_map(track: str, layout: str | None = None) -> dict | None:
    """Load the 1 m station model for a track, or None if it is not modelled.

    Station maps are the reference points the export hangs corner-by-corner
    telemetry off.  Without one, telemetry can still be exported against raw
    lap distance — it just cannot be labelled by corner.
    """
    files = station_map_files()
    if not files:
        return None

    wanted = _slug(track)
    layout_slug = _slug(layout) if layout else None

    candidates = [key for key in files if key.startswith(wanted)]
    if layout_slug:
        preferred = [key for key in candidates if layout_slug in key]
        if preferred:
            candidates = preferred
        elif is_reverse(layout):
            # A reversed lap meets the corners in the opposite order, so the
            # forward map would label every one of them wrongly. Better no
            # corner names than confident wrong ones.
            return None
    if not candidates:
        return None

    with files[sorted(candidates)[0]].open(encoding="utf-8") as handle:
        return json.load(handle)


def modelled_tracks() -> tuple[str, ...]:
    """Slugs of tracks that have a station map available."""
    return tuple(sorted(station_map_files()))
