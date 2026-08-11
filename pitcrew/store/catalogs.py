"""Reference data: GT7 track names, car names, and track station maps.

These are files, not database rows — they are shipped reference data that the
app reads and never writes, so they survive a database reset.  This is the only
thing carried across from the old data layer.
"""
from __future__ import annotations

import functools
import json
from pathlib import Path

DATA_DIR = Path("data")
TRACKS_FILE = DATA_DIR / "gt7_extra.json"
CARS_FILE = DATA_DIR / "car_id_map.json"
TRACK_MODELS_DIR = DATA_DIR / "track_models"

STATION_MAP_SUFFIX = ".station_map.json"


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
    path = DATA_DIR / "car_specs.json"
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


# Race classes first, in their own order; road cars last because there are ten
# times as many of them and they are not what a league event usually picks.
CATEGORY_ORDER = ("Gr.1", "Gr.2", "Gr.3", "Gr.4", "Gr.B", "Road Car")


@functools.lru_cache(maxsize=1)
def cars_by_category() -> dict[str, tuple[str, ...]]:
    """Car names grouped by GT7 class.

    Note the shipped spec file carries no Gr.B cars, so that group is simply
    absent rather than empty - a heading with nothing under it would suggest
    the data is there when it is not.
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
