"""Group 57 — Approved Reference Path Assets & Live Progress Activation (pure loader).

WHY IT EXISTS
  Group 56 converts a live world position into normalised lap progress, but only if
  an approved reference path is available for the current track/layout. In real UAT
  it usually was not — the app guessed a filename and missed the real asset. This
  module is the read-only loader that DISCOVERS approved/reference path files on
  disk, validates track/layout identity, and converts them into Group 56
  ``TrackPathStation`` objects so live progress can actually activate.

WHAT THIS MODULE IS
  A pure, deterministic, read-only loader. It scans known search roots for
  ``*.reference_path.json`` files (and track-library ``reference_path.json``),
  parses BOTH the explicit ``reference_path_v1`` shape and the existing Group 17
  calibration shape (``track_location_id`` / ``points``), normalises stations, and
  validates identity. It never writes, never mutates a track model, never raises.

WHAT THIS MODULE IS NOT
  • It creates NO pit stop and authors NO strategy/setup values — it only supplies
    reference-path geometry. Progress → pit corroboration is gated downstream
    (Group 56 confidence rules + Group 55 pit-lane resolver).
  • It imports no Qt, no DB, no AI. Malformed / missing files degrade to an honest
    "unavailable" result; unknown/mismatched identity is never treated as safe.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple

from data.live_track_progress import TrackPathStation, build_track_path_stations

REFERENCE_PATH_SCHEMA_V1 = "reference_path_v1"
_REF_SUFFIX = ".reference_path.json"

# Generic track-name tokens ignored when fuzzily matching identity.
_GENERIC_TOKENS = {
    "international", "speedway", "circuit", "raceway", "full", "course",
    "gp", "grand", "prix", "national", "short", "long", "reverse", "layout",
    "track", "the", "de", "of", "road",
}


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ReferencePathAsset:
    """A loaded, validated approved/reference path for one track/layout."""
    track_id: str = ""
    layout_id: str = ""
    source: str = ""
    path: str = ""                       # file path it was loaded from (str)
    stations: tuple = ()                 # tuple of normalised station dicts
    lap_length_m: float = 0.0
    warnings: tuple = ()
    metadata: dict = field(default_factory=dict)

    @property
    def station_count(self) -> int:
        return len(self.stations)


@dataclass(frozen=True)
class ReferencePathLoadResult:
    """Outcome of a reference-path load attempt (never raises to the caller)."""
    asset: Optional[ReferencePathAsset] = None
    available: bool = False
    source: str = "missing"
    message: str = ""
    warnings: tuple = ()

    @property
    def has_stations(self) -> bool:
        return bool(self.asset is not None and self.asset.stations)


# ---------------------------------------------------------------------------
# Numeric helpers (reject NaN/inf; never raise)
# ---------------------------------------------------------------------------

def _finite(v) -> Optional[float]:
    try:
        if v is None:
            return None
        f = float(v)
    except (TypeError, ValueError):
        return None
    if f != f or f in (float("inf"), float("-inf")):
        return None
    return f


# ---------------------------------------------------------------------------
# Identity normalisation / matching
# ---------------------------------------------------------------------------

def _norm_id(s) -> str:
    """Lowercase, non-alphanumeric → underscore, collapse repeats, strip."""
    if not s:
        return ""
    out = []
    prev_us = False
    for ch in str(s).lower():
        if ch.isalnum():
            out.append(ch)
            prev_us = False
        else:
            if not prev_us:
                out.append("_")
            prev_us = True
    return "".join(out).strip("_")


def _sig_tokens(norm: str) -> set:
    return {t for t in norm.split("_") if t and t not in _GENERIC_TOKENS}


def _ids_match(requested: str, candidate: str) -> bool:
    """True when a requested id matches a candidate id (tolerant, never fuzzy-wrong).

    Match if: requested empty, exact equal, one contains the other, or their
    significant (non-generic) tokens overlap. Handles display-name vs canonical-id.
    """
    r = _norm_id(requested)
    c = _norm_id(candidate)
    if not r:
        return True
    if not c:
        return False
    if r == c or r in c or c in r:
        return True
    rt, ct = _sig_tokens(r), _sig_tokens(c)
    if not rt or not ct:
        return False
    return bool(rt & ct) and (rt <= ct or ct <= rt or len(rt & ct) >= 1 and len(rt) == 1)


# ---------------------------------------------------------------------------
# Station normalisation
# ---------------------------------------------------------------------------

def _lap_length(raw: dict, stations: List[dict]) -> Tuple[float, list]:
    warnings: list = []
    lap = _finite(raw.get("lap_length_m"))
    if lap is None:
        dists = [s["distance_along_lap_m"] for s in stations
                 if s.get("distance_along_lap_m") is not None]
        lap = max(dists) if dists else 0.0
    if lap is not None and lap <= 0:
        warnings.append("reference path has no usable lap length")
        lap = 0.0
    return float(lap or 0.0), warnings


def _normalise_stations(raw: dict) -> Tuple[List[dict], list]:
    """Return (normalised station dicts, warnings). Supports v1 + Group 17 shapes.

    Group 17 (calibration) uses ``points`` with ``lap_progress``; v1 uses
    ``stations`` with ``progress``. Bad / NaN / infinite stations are skipped.
    """
    warnings: list = []
    src_list = None
    for key in ("stations", "points"):
        if isinstance(raw.get(key), list):
            src_list = raw[key]
            break
    if src_list is None:
        return [], ["reference path has no usable stations"]

    out: List[dict] = []
    skipped = 0
    for item in src_list:
        if not isinstance(item, dict):
            skipped += 1
            continue
        x = _finite(item.get("x"))
        z = _finite(item.get("z"))
        if x is None or z is None:
            skipped += 1
            continue
        y = _finite(item.get("y"))
        dist = _finite(item.get("distance_along_lap_m"))
        prog = _finite(item.get("progress"))
        if prog is None:
            prog = _finite(item.get("lap_progress"))
        if prog is not None and prog > 1.0 + 1e-9:  # a percentage slipped in
            prog = prog / 100.0
        out.append({
            "index": len(out),
            "x": x, "y": y if y is not None else 0.0, "z": z,
            "distance_along_lap_m": dist if dist is not None else float(len(out)),
            "progress": prog,
        })
    if skipped:
        warnings.append(f"reference path had {skipped} malformed station(s), skipped")
    if not out:
        warnings.append("reference path has no usable stations")
    return out, warnings


# ---------------------------------------------------------------------------
# File loading
# ---------------------------------------------------------------------------

def load_reference_path_file(path) -> ReferencePathLoadResult:
    """Load and normalise a single reference-path JSON file. Never raises.

    Accepts the explicit ``reference_path_v1`` shape and the existing Group 17
    calibration shape (``track_location_id`` + ``points``).
    """
    try:
        p = Path(path)
        if not p.exists() or not p.is_file():
            return ReferencePathLoadResult(
                available=False, source="missing",
                message="Approved reference path unavailable.",
                warnings=("approved reference path unavailable",))
        try:
            raw = json.loads(p.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            return ReferencePathLoadResult(
                available=False, source="malformed",
                message="Reference path file is malformed and was ignored.",
                warnings=("reference path malformed, ignored",))
        if not isinstance(raw, dict):
            return ReferencePathLoadResult(
                available=False, source="malformed",
                message="Reference path file is malformed and was ignored.",
                warnings=("reference path malformed, ignored",))

        track_id = str(raw.get("track_id") or raw.get("track_location_id") or "")
        layout_id = str(raw.get("layout_id") or "")
        source = str(raw.get("source") or ("approved_track_model"
                     if raw.get("schema_version") == REFERENCE_PATH_SCHEMA_V1
                     else "calibration_reference_path"))

        stations, st_warn = _normalise_stations(raw)
        lap_len, lap_warn = _lap_length(raw, stations)
        # Only LOAD-TIME issues become live warnings; the file's own historical
        # calibration build notes are kept in metadata (not shown to the driver).
        warnings = tuple(st_warn + lap_warn)

        if not stations:
            return ReferencePathLoadResult(
                asset=None, available=False, source="malformed",
                message="Reference path has no usable stations.",
                warnings=warnings or ("reference path has no usable stations",))

        metadata = {
            "schema_version": raw.get("schema_version", ""),
            "calibration_car_id": raw.get("calibration_car_id", ""),
            "confidence": raw.get("confidence", None),
            "built_at": raw.get("built_at", ""),
            "source_lap_count": raw.get("source_lap_count", None),
            "build_warnings": tuple(raw.get("warnings", []) or []),
        }
        asset = ReferencePathAsset(
            track_id=track_id, layout_id=layout_id, source=source, path=str(p),
            stations=tuple(stations), lap_length_m=lap_len,
            warnings=warnings, metadata=metadata,
        )
        return ReferencePathLoadResult(
            asset=asset, available=True, source=source,
            message=f"Approved reference path loaded ({len(stations)} stations).",
            warnings=warnings)
    except Exception:
        return ReferencePathLoadResult(
            available=False, source="malformed",
            message="Reference path could not be read.",
            warnings=("reference path malformed, ignored",))


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------

def _default_search_roots() -> List[Path]:
    roots: List[Path] = []
    try:
        from data.track_calibration import TRACK_MODELS_DIR
        roots.append(Path(TRACK_MODELS_DIR))
    except Exception:
        pass
    try:
        from data.track_library import TRACK_LIBRARY_BASE
        roots.append(Path(TRACK_LIBRARY_BASE))
    except Exception:
        pass
    return roots


def _iter_reference_files(root: Path):
    try:
        if not root.exists() or not root.is_dir():
            return
        # Flat track_models/*.reference_path.json
        for p in root.glob(f"*{_REF_SUFFIX}"):
            if p.is_file():
                yield p
        # Track-library layouts/<id>/reference_path.json (+ *.reference_path.json)
        for p in root.rglob("reference_path.json"):
            if p.is_file():
                yield p
        for p in root.rglob(f"*{_REF_SUFFIX}"):
            if p.is_file():
                yield p
    except Exception:
        return


def find_reference_path_candidates(
    track_id: str,
    layout_id: str,
    search_roots=None,
) -> List[Path]:
    """Return reference-path files whose embedded identity matches track/layout.

    Read-only directory scan. Never raises. Results are ranked best-first: exact
    track+layout, then exact track, then tolerant token matches.
    """
    try:
        roots = [Path(r) for r in (search_roots or _default_search_roots())]
        seen: set = set()
        scored: List[Tuple[int, Path]] = []
        for root in roots:
            for p in _iter_reference_files(root):
                key = str(p.resolve()) if p.exists() else str(p)
                if key in seen:
                    continue
                seen.add(key)
                res = load_reference_path_file(p)
                if not res.has_stations:
                    continue
                a = res.asset
                t_ok = _ids_match(track_id, a.track_id)
                l_ok = _ids_match(layout_id, a.layout_id)
                if not t_ok:
                    continue
                # Score: prefer exact matches, then layout match, then track-only.
                exact_t = _norm_id(track_id) == _norm_id(a.track_id) and track_id
                exact_l = _norm_id(layout_id) == _norm_id(a.layout_id) and layout_id
                if exact_t and exact_l:
                    score = 0
                elif l_ok and exact_t:
                    score = 1
                elif l_ok:
                    score = 2
                elif not layout_id:
                    score = 3
                else:
                    continue  # track matched but layout explicitly mismatched
                scored.append((score, p))
        scored.sort(key=lambda sp: (sp[0], str(sp[1])))
        return [p for _s, p in scored]
    except Exception:
        return []


def load_reference_path_for_layout(
    track_id: str,
    layout_id: str,
    search_roots=None,
) -> ReferencePathLoadResult:
    """Discover + load the best approved reference path for a track/layout.

    Read-only. Returns an honest "unavailable" result when nothing usable is found;
    never raises.
    """
    try:
        candidates = find_reference_path_candidates(track_id, layout_id, search_roots)
        if not candidates:
            return ReferencePathLoadResult(
                available=False, source="missing",
                message="Approved reference path unavailable for this track/layout.",
                warnings=("approved reference path unavailable",))
        for cand in candidates:
            res = load_reference_path_file(cand)
            if res.has_stations:
                return res
        return ReferencePathLoadResult(
            available=False, source="missing",
            message="Approved reference path unavailable for this track/layout.",
            warnings=("approved reference path unavailable",))
    except Exception:
        return ReferencePathLoadResult(
            available=False, source="missing",
            message="Approved reference path unavailable for this track/layout.",
            warnings=("approved reference path unavailable",))


# ---------------------------------------------------------------------------
# Conversion + identity validation
# ---------------------------------------------------------------------------

def reference_path_to_track_stations(asset_or_dict) -> List[TrackPathStation]:
    """Convert a ReferencePathAsset (or raw dict) to Group 56 TrackPathStation list.

    Delegates to the Group 56 ``build_track_path_stations`` (never raises).
    """
    try:
        if isinstance(asset_or_dict, ReferencePathAsset):
            return build_track_path_stations({"points": list(asset_or_dict.stations)})
        if isinstance(asset_or_dict, dict):
            if "stations" in asset_or_dict or "points" in asset_or_dict:
                return build_track_path_stations(asset_or_dict)
            return build_track_path_stations({"points": [asset_or_dict]})
        return build_track_path_stations(asset_or_dict)
    except Exception:
        return []


def validate_reference_path_identity(
    asset,
    expected_track_id: str,
    expected_layout_id: str,
) -> Tuple[bool, str]:
    """Validate a loaded asset's identity against the expected track/layout.

    Returns (ok, message). ``ok`` is False on a genuine mismatch (which the caller
    must treat as "do not lift pit confidence"). Never raises.
    """
    try:
        if asset is None:
            return False, "reference path track/layout mismatch"
        t_ok = _ids_match(expected_track_id, getattr(asset, "track_id", ""))
        l_ok = _ids_match(expected_layout_id, getattr(asset, "layout_id", ""))
        if t_ok and l_ok:
            return True, "reference path identity verified"
        return False, "reference path track/layout mismatch"
    except Exception:
        return False, "reference path track/layout mismatch"


# ---------------------------------------------------------------------------
# Group 58 — reference-path asset registry foundation + trusted lap length
# ---------------------------------------------------------------------------

def list_available_reference_paths(search_roots=None) -> List[dict]:
    """List every discoverable approved reference-path asset (read-only registry).

    Returns one summary dict per usable asset:
      {track_id, layout_id, source, path, station_count, lap_length_m}
    Deterministic (sorted by track_id, layout_id, path). Never raises; never writes.
    Used to answer "which circuits currently ship an approved reference path?" and
    to drive docs / honest missing-asset messages. It invents nothing.
    """
    try:
        roots = [Path(r) for r in (search_roots or _default_search_roots())]
        seen: set = set()
        out: List[dict] = []
        for root in roots:
            for p in _iter_reference_files(root):
                key = str(p.resolve()) if p.exists() else str(p)
                if key in seen:
                    continue
                seen.add(key)
                res = load_reference_path_file(p)
                if not res.has_stations:
                    continue
                a = res.asset
                out.append({
                    "track_id": a.track_id, "layout_id": a.layout_id,
                    "source": a.source, "path": a.path,
                    "station_count": a.station_count, "lap_length_m": a.lap_length_m,
                })
        out.sort(key=lambda d: (d["track_id"], d["layout_id"], d["path"]))
        return out
    except Exception:
        return []


def reference_path_asset_summary(track_id: str, layout_id: str,
                                 search_roots=None) -> dict:
    """Return an honest availability summary for a track/layout (read-only).

    {available: bool, source: str, message: str, station_count: int, lap_length_m: float}.
    Never raises. A missing asset yields a clear, non-crashing "unavailable" summary.
    """
    try:
        res = load_reference_path_for_layout(track_id, layout_id, search_roots)
        if res.has_stations:
            a = res.asset
            return {
                "available": True, "source": a.source,
                "message": (f"Approved reference path available "
                            f"({a.station_count} stations)."),
                "station_count": a.station_count, "lap_length_m": a.lap_length_m,
            }
        return {
            "available": False, "source": "missing",
            "message": ("Approved reference path unavailable for this track/layout — "
                        "live progress will use the road-distance fallback if possible."),
            "station_count": 0, "lap_length_m": 0.0,
        }
    except Exception:
        return {"available": False, "source": "missing",
                "message": "Approved reference path unavailable.",
                "station_count": 0, "lap_length_m": 0.0}


def resolve_trusted_lap_length(track_id: str, layout_id: str,
                               search_roots=None) -> Optional[float]:
    """Return a TRUSTED lap length (metres) for a track/layout, or None. Read-only.

    Resolution order (first trustworthy, positive value wins):
      1. an approved reference-path asset's ``lap_length_m``
      2. the track-library manifest ``lap_length_m``
    Never invents a length; returns None when no trusted source exists. Never raises.
    """
    try:
        res = load_reference_path_for_layout(track_id, layout_id, search_roots)
        if res.has_stations and res.asset.lap_length_m and res.asset.lap_length_m > 0:
            return float(res.asset.lap_length_m)
    except Exception:
        pass
    try:
        from data.track_library import resolve_track_layout_manifest
        m = resolve_track_layout_manifest(track_id, layout_id)
        if m is not None and getattr(m, "lap_length_m", 0) and m.lap_length_m > 0:
            return float(m.lap_length_m)
    except Exception:
        pass
    return None
