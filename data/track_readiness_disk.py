"""Disk-first track-readiness — audit assets directly, independent of UI state.

The Qt Track-Modelling tab only populates in-memory track state (station map,
accepted-model alignment, seed audit) *after* the user opens it and selects a
layout. On a fresh restart with the Command Centre showing, none of that is
loaded, so the legacy availability flags were all False and Fuji read BLOCKED
even though every asset was on disk.

This module audits the ``data/track_models`` flat store (and seed geometry)
straight from disk for a given (location_id, layout_id) and feeds the pure
:func:`data.track_readiness.resolve_track_readiness` decision. Every screen can
call :func:`resolve_track_readiness_from_disk` and get the same verdict without
opening Track Modelling.

Never raises: every disk probe is defensive; a failure degrades that asset to
"absent", never an exception out of a readiness call.
"""
from __future__ import annotations

from types import SimpleNamespace
from typing import Optional

from data.track_readiness import TrackReadinessResult, resolve_track_readiness


def _ref_path_summary(loc: str, lay: str) -> tuple[bool, int]:
    """(available, point_count) for the reference path, from the flat store + library."""
    try:
        from data.reference_path_loader import reference_path_asset_summary
        s = reference_path_asset_summary(loc, lay)
        return bool(s.get("available")), int(s.get("station_count", 0) or 0)
    except Exception:
        return False, 0


def _accepted_model_present(loc: str, lay: str) -> bool:
    try:
        from data.track_model_alignment import find_accepted_model_path
        return find_accepted_model_path(loc, lay) is not None
    except Exception:
        return False


def _station_map_present(loc: str, lay: str) -> bool:
    try:
        from data.track_station_map import find_station_map_path
        return find_station_map_path(loc, lay) is not None
    except Exception:
        return False


def _reviewed_present(loc: str, lay: str) -> bool:
    try:
        from data.track_model_resolver import find_reviewed_models_for_layout
        return bool(find_reviewed_models_for_layout(loc, lay))
    except Exception:
        return False


def _seed_geometry(loc: str, lay: str) -> tuple[bool, bool, bool, bool]:
    """(centreline, corner_windows, lap_length, metadata) seed availability."""
    try:
        from data.track_intelligence import resolve_track_layout, audit_layout_seed
        seed = resolve_track_layout(loc, lay)
        if seed is None:
            return False, False, False, False
        audit = audit_layout_seed(seed, loc, lay)

        def g(name):
            v = getattr(audit, name, False)
            return bool(v)
        return (g("has_seed_centreline"), g("has_corner_windows"),
                g("has_lap_length"), g("has_metadata"))
    except Exception:
        return False, False, False, False


def audit_track_assets_on_disk(location_id: str, layout_id: str) -> SimpleNamespace:
    """Return a TrackContext-shaped object (identity + availability) from disk.

    The returned object is duck-typed to what
    :func:`data.track_readiness.resolve_track_readiness` reads, so the same pure
    decision runs on disk-audited or in-memory availability.
    """
    loc = (location_id or "").strip()
    lay = (layout_id or "").strip()

    ref_available, ref_points = (_ref_path_summary(loc, lay) if (loc and lay) else (False, 0))
    accepted = _accepted_model_present(loc, lay) if (loc and lay) else False
    station = _station_map_present(loc, lay) if (loc and lay) else False
    reviewed = _reviewed_present(loc, lay) if (loc and lay) else False
    seed_cl, seed_win, seed_len, seed_meta = (
        _seed_geometry(loc, lay) if (loc and lay) else (False, False, False, False)
    )

    identity = SimpleNamespace(
        track_location_id=loc, layout_id=lay, is_complete=bool(loc and lay),
    )
    availability = SimpleNamespace(
        accepted_model_available=accepted,
        reference_path_available=ref_available,
        reference_path_point_count=ref_points,
        station_map_available=station,
        reviewed_model_available=reviewed,
        seed_geometry_available=seed_cl,
        seed_corner_windows_available=seed_win,
        seed_lap_length_available=seed_len,
        seed_metadata_available=seed_meta,
    )
    return SimpleNamespace(identity=identity, availability=availability)


def resolve_track_readiness_from_disk(
    location_id: str, layout_id: str,
) -> TrackReadinessResult:
    """Resolve track readiness for (location_id, layout_id) straight from disk.

    This is the entry point every screen should call to answer "is the track
    ready?" without depending on whether Track Modelling has been opened.
    """
    ctx = audit_track_assets_on_disk(location_id, layout_id)
    return resolve_track_readiness(ctx)
