"""One deterministic track-readiness resolver for every screen.

Sprint 3 of the determinism rebuild. Before this module, "is the track ready?"
was answered in at least three different places with three different rules —
most narrowly by ``TrackContext.can_attempt_live_mapping`` (station-map only),
which made Fuji read BLOCKED in the Command Centre even when a valid approved
reference path + accepted model were on disk.

This module computes ONE readiness verdict from a ``TrackContext`` (which
already aggregates every asset-availability signal). Every screen — Command
Centre, Track Modelling, Setup Builder, Practice, Strategy Builder, Live Race —
must consume the same ``resolve_track_readiness`` result.

Pure and deterministic: no Qt, no file I/O, no network. It reads the
availability booleans a caller already resolved (from disk audit + seeds); the
companion ``data.track_readiness_disk.resolve_track_readiness_from_disk`` builds
a disk-audited context so a screen can get a verdict on a fresh restart without
opening Track Modelling.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Tuple


class TrackReadiness(str, Enum):
    """The single readiness verdict for a track/layout."""
    READY_APPROVED = "ready_approved"          # approved reference path / accepted model present
    READY_SEED_GEOMETRY = "ready_seed_geometry"  # usable from seed geometry / station map / reviewed model
    PARTIAL = "partial"                        # identity ok, some assets, not enough to be usable
    MISSING_ASSET = "missing_asset"            # identity ok but no track model assets
    IDENTITY_MISMATCH = "identity_mismatch"    # selection does not resolve to a known layout identity
    INVALID_ASSET = "invalid_asset"            # an asset exists on disk but failed to load/validate


# States a screen may treat as "the track is usable now".
READY_STATES = frozenset({TrackReadiness.READY_APPROVED, TrackReadiness.READY_SEED_GEOMETRY})


@dataclass(frozen=True)
class TrackReadinessResult:
    """Immutable readiness verdict consumed identically by every screen."""
    state: TrackReadiness
    location_id: str = ""
    layout_id: str = ""
    confidence: str = "none"        # "high" | "medium" | "low" | "none"
    provenance: str = ""            # where the verdict came from (human-readable)
    assets: Tuple[str, ...] = ()    # human-readable available assets
    blockers: Tuple[str, ...] = ()  # why it is not (more) ready
    next_action: str = ""           # the single next step for the user

    @property
    def is_ready(self) -> bool:
        return self.state in READY_STATES

    @property
    def is_approved(self) -> bool:
        return self.state == TrackReadiness.READY_APPROVED


# --------------------------------------------------------------------------- #
# Safe getters (duck-typed; never raise) — mirror data/*_context conventions
# --------------------------------------------------------------------------- #
def _get(obj, name, default=None):
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(name, default)
    try:
        v = getattr(obj, name, default)
    except Exception:  # pragma: no cover - defensive
        return default
    return default if v is None else v


def _b(obj, name) -> bool:
    return bool(_get(obj, name, False))


def resolve_track_readiness(track_context) -> TrackReadinessResult:
    """Return the single readiness verdict for a ``TrackContext``.

    Precedence (first match wins):
      1. Identity incomplete / unresolved → MISSING_ASSET or IDENTITY_MISMATCH.
      2. An approved reference path or accepted model → READY_APPROVED.
      3. Seed geometry / station map / reviewed model → READY_SEED_GEOMETRY.
      4. An asset exists on disk but is broken → INVALID_ASSET.
      5. Some seed metadata but not enough geometry → PARTIAL.
      6. Identity ok, nothing on disk → MISSING_ASSET.

    Never raises; an unusable/None context resolves to MISSING_ASSET.
    """
    identity = _get(track_context, "identity")
    loc_id = str(_get(identity, "track_location_id", "") or "")
    lay_id = str(_get(identity, "layout_id", "") or "")
    id_complete = _b(identity, "is_complete")

    av = _get(track_context, "availability")

    # 1. Identity gate ---------------------------------------------------------
    if not id_complete:
        # A partial identity (one of loc/layout present) reads as a mismatch the
        # user must resolve; a wholly empty selection is simply "no track yet".
        if loc_id or lay_id:
            return TrackReadinessResult(
                state=TrackReadiness.IDENTITY_MISMATCH,
                location_id=loc_id, layout_id=lay_id,
                confidence="none",
                provenance="incomplete track identity",
                blockers=("Track/layout selection is incomplete.",),
                next_action="Select both a track and a layout.",
            )
        return TrackReadinessResult(
            state=TrackReadiness.MISSING_ASSET,
            confidence="none",
            provenance="no track selected",
            blockers=("No track selected.",),
            next_action="Select a track and layout to begin.",
        )

    # Availability signals -----------------------------------------------------
    accepted = _b(av, "accepted_model_available")
    ref_available = _b(av, "reference_path_available")
    ref_points = int(_get(av, "reference_path_point_count", 0) or 0)
    ref_valid = ref_available and ref_points > 0
    ref_broken = ref_available and ref_points <= 0  # file present but empty/failed to load

    station_map = _b(av, "station_map_available")
    reviewed = _b(av, "reviewed_model_available")
    seed_geometry = _b(av, "seed_geometry_available")
    seed_windows = _b(av, "seed_corner_windows_available")
    seed_length = _b(av, "seed_lap_length_available")
    seed_metadata = _b(av, "seed_metadata_available")

    assets: list[str] = []
    if ref_valid:
        assets.append(f"approved reference path ({ref_points} pts)")
    if accepted:
        assets.append("accepted model")
    if station_map:
        assets.append("station map")
    if reviewed:
        assets.append("reviewed segments")
    if seed_geometry:
        assets.append("seed geometry")
    elif seed_windows:
        assets.append("seed corner windows")
    assets_t = tuple(assets)

    # 2. Approved --------------------------------------------------------------
    if ref_valid or accepted:
        prov = "approved reference path" if ref_valid else "accepted track model"
        return TrackReadinessResult(
            state=TrackReadiness.READY_APPROVED,
            location_id=loc_id, layout_id=lay_id,
            confidence="high",
            provenance=prov,
            assets=assets_t,
            next_action="Load or build the race setup.",
        )

    # 3. Usable from seed geometry / station map / reviewed --------------------
    if station_map or reviewed or seed_geometry or (seed_windows and seed_length):
        blockers = ("No approved reference path yet — the model is usable but "
                    "not calibration-approved.",)
        return TrackReadinessResult(
            state=TrackReadiness.READY_SEED_GEOMETRY,
            location_id=loc_id, layout_id=lay_id,
            confidence="medium",
            provenance="seed geometry / station map",
            assets=assets_t,
            blockers=blockers,
            next_action="Optional: run a calibration session to build an "
                        "approved reference path.",
        )

    # 4. Broken asset ----------------------------------------------------------
    if ref_broken:
        return TrackReadinessResult(
            state=TrackReadiness.INVALID_ASSET,
            location_id=loc_id, layout_id=lay_id,
            confidence="none",
            provenance="reference path file present but unreadable/empty",
            blockers=("A saved reference path exists but could not be loaded.",),
            next_action="Rebuild the track model in Track Modelling.",
        )

    # 5. Partial (some seed metadata but not enough geometry) ------------------
    if seed_metadata or seed_windows or seed_length:
        return TrackReadinessResult(
            state=TrackReadiness.PARTIAL,
            location_id=loc_id, layout_id=lay_id,
            confidence="low",
            provenance="seed metadata only",
            assets=assets_t,
            blockers=("Seed metadata is present but there is no usable geometry, "
                      "station map, or reference path.",),
            next_action="Open Track Modelling to build the track geometry.",
        )

    # 6. Nothing on disk -------------------------------------------------------
    return TrackReadinessResult(
        state=TrackReadiness.MISSING_ASSET,
        location_id=loc_id, layout_id=lay_id,
        confidence="none",
        provenance="no track model assets found",
        blockers=("No track model assets found for this layout.",),
        next_action="Open Track Modelling to build the track model.",
    )
