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

DATA_DIR = Path("data")
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
def track_names() -> tuple[str, ...]:
    """Every GT7 track/layout name we know about, sorted.

    Note this list is incomplete — it holds 86 layouts and uses en dashes in
    the layout separator ("Alsace – Test Course").  Treat it as autocomplete
    suggestions for a free-text field, not as a closed set: an event must be
    creatable for a track that is not in here.

    Every file read here specifies utf-8 explicitly.  Windows defaults to
    cp1252, which silently turns the en dashes into mojibake.
    """
    if not TRACKS_FILE.exists():
        return ()
    with TRACKS_FILE.open(encoding="utf-8") as handle:
        payload = json.load(handle)
    names = [str(name) for name in payload.get("tracks", [])]
    return tuple(sorted(set(names)))


@functools.lru_cache(maxsize=1)
def cars_by_id() -> dict[int, str]:
    """GT7 car id -> car name.  The id is what the telemetry packet carries."""
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
# track and layout in separate fields, so the catalogue is split on it rather
# than offering 86 entries that repeat the base name a dozen times.
LAYOUT_SEPARATOR = "–"


@functools.lru_cache(maxsize=1)
def track_layouts() -> dict[str, tuple[str, ...]]:
    """Base track name -> its layouts, empty when the track has only one."""
    grouped: dict[str, list[str]] = {}
    for name in track_names():
        base, _, layout = name.partition(LAYOUT_SEPARATOR)
        base = base.strip()
        layout = layout.strip()
        grouped.setdefault(base, [])
        if layout and layout not in grouped[base]:
            grouped[base].append(layout)
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
    if not candidates:
        return None

    with files[sorted(candidates)[0]].open(encoding="utf-8") as handle:
        return json.load(handle)


def modelled_tracks() -> tuple[str, ...]:
    """Slugs of tracks that have a station map available."""
    return tuple(sorted(station_map_files()))
