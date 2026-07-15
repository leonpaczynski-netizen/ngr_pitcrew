"""TrackContext — canonical read model for track/layout identity and model state.

Added by the **State Consolidation 4 — TrackContext** sprint (2026-07-03) as the
fourth concrete step of the target architecture proposed in
`docs/PRODUCT_CONSOLIDATION_AUDIT.md` (§7). It follows
`data/event_context.py`, `data/strategy_context.py` and `data/setup_context.py`.

Why this exists
---------------
Track identity and track-model state are the most scattered state in the app
(SSOT-2 in the audit — "track/layout split three ways"):

* the **display track name** lives in `config["strategy"]["track"]` (written by
  Event Planner's "Set as Active"),
* the **canonical ids** (`track_location_id` / `layout_id`) live in
  `config["strategy"]` but are written by the *Track Modelling tab's combos*
  (`_tm_on_layout_changed`), a completely different surface,
* the **model artefacts** live in per-layout files (seed YAML, track library,
  seed coordinate maps, reference paths, calibration laps, station maps,
  reviewed models, accepted alignment, lap-offset calibration) discovered by
  half a dozen loaders,
* the **live state** lives in dashboard attributes (`_tm_station_map`,
  `_tm_alignment_result`, `_tm_seed_result`).

Nothing ties these together, so nothing can answer "what track is selected, what
model data exists for it, and is any of it stale?" in one place. ``TrackContext``
is an immutable read model that owns exactly that: **identity + availability +
status**, with a change marker and staleness/mismatch helpers.

Ownership boundary
------------------
TrackContext owns: track/layout identity (ids + display names + combined id +
identity source), seed metadata / corner-window / geometry availability,
reference path / calibration laps / station map / reviewed model / accepted
model / lap-offset availability, modelling status, alignment status, track-truth
gate results (as reported by the existing validators — never invented), a
``change_hash`` over identity + availability + status, and the
``event_change_hash`` it was built against.

It must **not** own: event/race rules (race type, duration/laps, multipliers,
BoP/tuning legality — EventContext), strategy plan / stint plan / fuel burn
(StrategyContext), setup recommendation state (SetupContext), raw telemetry
packets or lap validity (Telemetry/Session context), AI logs, or driver
learning history.

**No geometry truth is invented here.** Availability flags report what the
existing audits/loaders/validators said; a flag being True means "the artefact
exists / the existing validator accepted it", never "the geometry is accurate".

Purity
------
No PyQt6, no UI, no network/AI, no DB, and **no file I/O** — builders take
duck-typed result objects the existing loaders already produce
(``SeedAuditResult``, ``TrackModelFileAudit``, ``TrackModelResolverResult``,
``TrackModelAlignmentResult``, ``LapStartOffsetCalibration``,
``TrackTruthValidationResult``…). This keeps the module unit-testable without a
QApplication and free of import cycles. The legacy files, loaders and dashboard
attributes are intentionally *not* touched this sprint; they remain the writers.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, asdict
from enum import Enum
from typing import Optional, Tuple, TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - typing only
    from data.event_context import EventContext


TRACK_CONTEXT_SCHEMA = "track_context_v1"


class TrackContextSource(str, Enum):
    """Where the track/layout identity was resolved from."""
    EMPTY = "empty"                          # no identity available at all
    TRACK_MODELLING_UI = "track_modelling_ui"  # explicit Track Modelling combo ids
    EVENT_CONTEXT = "event_context"          # ids/name from EventContext
    LEGACY_STRATEGY = "legacy_strategy"      # ids/name from config["strategy"]
    SEED_LIBRARY = "seed_library"            # only seed/library objects supplied


# --------------------------------------------------------------------------- #
# Safe coercion helpers (never raise) — mirror data/event_context.py
# --------------------------------------------------------------------------- #
def _as_str(v, default: str = "") -> str:
    if v is None:
        return default
    try:
        return str(v)
    except Exception:  # pragma: no cover - defensive
        return default


def _as_int(v, default: int = 0) -> int:
    try:
        if v is None or v == "":
            return default
        return int(round(float(v)))
    except (TypeError, ValueError):
        return default


def _as_float(v, default: float = 0.0) -> float:
    try:
        if v is None or v == "":
            return default
        return float(v)
    except (TypeError, ValueError):
        return default


def _as_bool(v, default: bool = False) -> bool:
    if v is None:
        return default
    try:
        return bool(v)
    except Exception:  # pragma: no cover - defensive
        return default


def _as_opt_bool(v) -> Optional[bool]:
    """Tri-state: keep an *unknown* optional as ``None``."""
    if v is None:
        return None
    try:
        return bool(v)
    except Exception:  # pragma: no cover - defensive
        return None


def _get(obj, name, default=None):
    """getattr that also works for dicts and never raises."""
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(name, default)
    try:
        return getattr(obj, name, default)
    except Exception:  # pragma: no cover - defensive
        return default


def _enum_value(v, default: str = "") -> str:
    """Extract a str value from an Enum member, plain string, or None."""
    if v is None:
        return default
    val = getattr(v, "value", v)
    return _as_str(val, default) or default


# --------------------------------------------------------------------------- #
# Typed sub-structures
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class TrackIdentity:
    """Who the track is: canonical ids + display names."""
    track_location_id: str = ""
    layout_id: str = ""
    track_display_name: str = ""
    layout_display_name: str = ""

    @property
    def combined_id(self) -> str:
        """Canonical `<location>__<layout>` identity used by all per-layout file
        conventions (reference paths, station maps, lap offsets…). Empty when
        either half is missing."""
        if self.track_location_id and self.layout_id:
            return f"{self.track_location_id}__{self.layout_id}"
        return ""

    @property
    def is_complete(self) -> bool:
        return bool(self.track_location_id and self.layout_id)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["combined_id"] = self.combined_id
        return d


@dataclass(frozen=True)
class TrackMapAvailability:
    """What track-model artefacts exist for this layout.

    Every flag reports what an existing audit/loader said — True means "the
    artefact exists / loaded", never "the geometry is accurate".
    """
    # Seed (Layer 1) — from the seed YAML / track library
    seed_metadata_available: bool = False
    seed_lap_length_available: bool = False
    seed_corner_windows_available: bool = False
    seed_sector_definitions_available: bool = False
    seed_corner_complexes_available: bool = False
    seed_geometry_available: bool = False          # coordinate centreline
    seed_source: str = "none"                      # "track_library"/"legacy_fallback"/"none"
    seed_corner_count: int = 0

    # Telemetry-derived artefacts (Layer 2) — per-layout files / live objects
    reference_path_available: bool = False
    reference_path_point_count: int = 0
    calibration_laps_available: bool = False
    station_map_available: bool = False
    station_map_station_count: int = 0
    reviewed_model_available: bool = False
    accepted_model_available: bool = False
    lap_offset_available: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class TrackGeometryStatus:
    """Modelling maturity + resolver outcome for this layout.

    ``modelling_status`` mirrors ``TrackModellingStatus`` values;
    ``resolution_status`` / ``model_source_type`` mirror the resolver enums.
    All default to honest "unknown"/"missing" values.
    """
    modelling_status: str = "not_modelled"
    ai_ready: bool = False
    resolution_status: str = "missing"       # TrackModelResolutionStatus value
    model_source_type: str = "missing"       # TrackModelSourceType value
    corners_expected: int = 0                # from seed (0 = unknown)
    lap_length_seed_m: float = 0.0
    lap_length_model_m: float = 0.0
    # Track Truth gates (Group 18A) — tri-state; None = no validation supplied.
    # These echo the existing TrackTruthValidationResult, never a new judgement.
    truth_accepted: Optional[bool] = None
    truth_usable_for_live_mapping: Optional[bool] = None
    truth_usable_for_ai_corner_context: Optional[bool] = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class TrackAlignmentStatus:
    """Seed-vs-model alignment outcome, as computed by the existing
    ``align_track_model()`` — represented, never recomputed."""
    available: bool = False
    match_status: str = "NOT_READY"          # TrackModelMatchStatus value
    accepted: bool = False
    accepted_at: str = ""
    lap_length_delta_pct: float = 0.0
    blocker_count: int = 0
    warning_count: int = 0
    corner_position_match: str = "NOT_AVAILABLE"  # PASS/PARTIAL/FAIL/NOT_AVAILABLE

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class TrackContextValidationResult:
    """Validation result keeping identity problems, missing-data notes, and
    staleness/mismatch problems separate so callers can tell which is which."""
    ok: bool
    identity_warnings: Tuple[str, ...] = ()
    identity_missing: Tuple[str, ...] = ()
    availability_warnings: Tuple[str, ...] = ()
    staleness_warnings: Tuple[str, ...] = ()

    @property
    def warnings(self) -> Tuple[str, ...]:
        return (
            tuple(self.identity_warnings)
            + tuple(self.availability_warnings)
            + tuple(self.staleness_warnings)
        )


# --------------------------------------------------------------------------- #
# The read model
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class TrackContext:
    """Immutable snapshot of track/layout identity + model availability/status."""

    identity: TrackIdentity
    source: TrackContextSource
    availability: TrackMapAvailability
    geometry: TrackGeometryStatus
    alignment: TrackAlignmentStatus

    # Lap-offset calibration status (from LapStartOffsetCalibration, if any)
    lap_offset_status: str = "not_loaded"    # not_loaded / provisional_zero / calibrated
    lap_offset_confidence: str = "unknown"   # LapDistanceMappingConfidence value

    # Keys / change markers
    change_hash: str = ""
    event_change_hash: str = ""

    # -- convenience ------------------------------------------------------- #
    @property
    def has_identity(self) -> bool:
        return self.source != TrackContextSource.EMPTY and self.identity.is_complete

    @property
    def is_missing_identity(self) -> bool:
        return not self.identity.is_complete

    @property
    def combined_id(self) -> str:
        return self.identity.combined_id

    # -- staleness / mismatch ------------------------------------------------ #
    def matches_event(self, event_context: "EventContext") -> Optional[bool]:
        """Tri-state comparison against EventContext's track identity.

        Returns True/False when both sides carry comparable identity, or None
        when the comparison is not possible (either side has no ids and no
        matching display name to compare).
        """
        ev_loc = _as_str(_get(event_context, "track_location_id"))
        ev_lay = _as_str(_get(event_context, "layout_id"))
        if ev_loc and self.identity.track_location_id:
            if ev_lay and self.identity.layout_id:
                return (ev_loc == self.identity.track_location_id
                        and ev_lay == self.identity.layout_id)
            return ev_loc == self.identity.track_location_id
        # Fall back to display-name comparison when ids are absent on either side.
        ev_track = _as_str(_get(event_context, "track"))
        if ev_track and self.identity.track_display_name:
            return ev_track.strip().lower() == self.identity.track_display_name.strip().lower()
        return None

    def mismatches_event(self, event_context: "EventContext") -> bool:
        """True only when a comparison is possible AND it disagrees."""
        return self.matches_event(event_context) is False

    def is_stale_for_event(self, event_context: "EventContext") -> bool:
        """True when this context was built against a different event state
        (by change_hash) — the cheap invalidation check."""
        if not self.event_change_hash:
            return False
        cur = _as_str(_get(event_context, "change_hash"))
        return bool(cur) and cur != self.event_change_hash

    @property
    def can_attempt_live_mapping(self) -> bool:
        """Conservative gate for the current station-map-based live matcher:
        complete identity + a station map. Says nothing about accuracy."""
        return self.identity.is_complete and self.availability.station_map_available

    def live_mapping_blockers(self) -> Tuple[str, ...]:
        """Why live map matching cannot run right now (empty = can attempt)."""
        blockers = []
        if not self.identity.track_location_id:
            blockers.append("No track selected.")
        if not self.identity.layout_id:
            blockers.append("No layout selected.")
        if self.identity.is_complete and not self.availability.station_map_available:
            blockers.append("No station map built for this layout.")
        return tuple(blockers)

    # -- display ----------------------------------------------------------- #
    def summary_line(self) -> str:
        if self.source == TrackContextSource.EMPTY:
            return "No track selected"
        name = self.identity.track_display_name or self.identity.track_location_id or "—"
        layout = self.identity.layout_display_name or self.identity.layout_id or "—"
        return (
            f"Track: {name}  |  Layout: {layout}  |  "
            f"Model: {self.geometry.modelling_status}  |  "
            f"Alignment: {self.alignment.match_status if self.alignment.available else 'not run'}"
        )

    def to_summary_lines(self) -> list:
        av = self.availability
        lines = [
            f"Track: {self.identity.track_display_name or self.identity.track_location_id or '—'}",
            f"Layout: {self.identity.layout_display_name or self.identity.layout_id or '—'}",
            f"Modelling status: {self.geometry.modelling_status}",
            "Seed: "
            + ("metadata ✓" if av.seed_metadata_available else "metadata ✗")
            + (", corner windows ✓" if av.seed_corner_windows_available else ", corner windows ✗")
            + (", geometry ✓" if av.seed_geometry_available else ", geometry ✗"),
            "Model data: "
            + ("ref path ✓" if av.reference_path_available else "ref path ✗")
            + (", station map ✓" if av.station_map_available else ", station map ✗")
            + (", accepted ✓" if av.accepted_model_available else ", accepted ✗"),
        ]
        if self.alignment.available:
            lines.append(f"Alignment: {self.alignment.match_status}"
                         + (" (accepted)" if self.alignment.accepted else ""))
        lines.append(f"Lap offset: {self.lap_offset_status}")
        return lines

    def to_dict(self) -> dict:
        return {
            "schema": TRACK_CONTEXT_SCHEMA,
            "identity": self.identity.to_dict(),
            "source": self.source.value,
            "availability": self.availability.to_dict(),
            "geometry": self.geometry.to_dict(),
            "alignment": self.alignment.to_dict(),
            "lap_offset_status": self.lap_offset_status,
            "lap_offset_confidence": self.lap_offset_confidence,
            "change_hash": self.change_hash,
            "event_change_hash": self.event_change_hash,
        }


# --------------------------------------------------------------------------- #
# Change marker
# --------------------------------------------------------------------------- #
def compute_change_hash(fields: dict) -> str:
    """Stable 12-char hash — a change marker so consumers can cheaply detect
    that the track identity or model availability/state changed and invalidate
    any derived snapshot. Deterministic (no time / randomness)."""
    blob = json.dumps(fields, sort_keys=True, default=str)
    return hashlib.sha1(blob.encode("utf-8")).hexdigest()[:12]


# --------------------------------------------------------------------------- #
# Builder / adapter
# --------------------------------------------------------------------------- #
def _resolve_identity(
    selected_location_id: str,
    selected_layout_id: str,
    event_context,
    strategy: Optional[dict],
    location_seed,
    layout_seed,
) -> Tuple[TrackIdentity, TrackContextSource]:
    """Resolve identity by priority: explicit UI selection → EventContext →
    legacy strategy dict → seed objects. Display names come from the seed
    objects when available (they are the only store that has layout display
    names), falling back to the event/strategy track name."""
    strategy = strategy if isinstance(strategy, dict) else {}

    sel_loc = _as_str(selected_location_id).strip()
    sel_lay = _as_str(selected_layout_id).strip()
    ev_loc = _as_str(_get(event_context, "track_location_id")).strip()
    ev_lay = _as_str(_get(event_context, "layout_id")).strip()
    st_loc = _as_str(strategy.get("track_location_id")).strip()
    st_lay = _as_str(strategy.get("layout_id")).strip()
    seed_loc = _as_str(_get(location_seed, "track_location_id")
                       or _get(layout_seed, "track_location_id")).strip()
    seed_lay = _as_str(_get(layout_seed, "layout_id")).strip()

    if sel_loc or sel_lay:
        loc, lay, source = sel_loc, sel_lay, TrackContextSource.TRACK_MODELLING_UI
    elif ev_loc or ev_lay:
        loc, lay, source = ev_loc, ev_lay, TrackContextSource.EVENT_CONTEXT
    elif st_loc or st_lay:
        loc, lay, source = st_loc, st_lay, TrackContextSource.LEGACY_STRATEGY
    elif seed_loc or seed_lay:
        loc, lay, source = seed_loc, seed_lay, TrackContextSource.SEED_LIBRARY
    else:
        loc, lay, source = "", "", TrackContextSource.EMPTY

    track_name = (
        _as_str(_get(location_seed, "display_name"))
        or _as_str(_get(event_context, "track"))
        or _as_str(strategy.get("track"))
    )
    layout_name = _as_str(_get(layout_seed, "display_name"))

    # A bare display name with no ids still counts as (weak) identity.
    if source == TrackContextSource.EMPTY and track_name:
        source = (
            TrackContextSource.EVENT_CONTEXT
            if _as_str(_get(event_context, "track"))
            else TrackContextSource.LEGACY_STRATEGY
        )

    return (
        TrackIdentity(
            track_location_id=loc,
            layout_id=lay,
            track_display_name=track_name,
            layout_display_name=layout_name,
        ),
        source,
    )


def _derive_lap_offset(offset_calibration) -> Tuple[bool, str, str]:
    """(available, status, confidence) from a LapStartOffsetCalibration."""
    if offset_calibration is None:
        return False, "not_loaded", "unknown"
    source = _as_str(_get(offset_calibration, "calibration_source"))
    confidence = _enum_value(_get(offset_calibration, "confidence"), "unknown")
    status = "provisional_zero" if source == "zero_offset" else "calibrated"
    return True, status, confidence


def build_track_context(
    *,
    selected_location_id: str = "",
    selected_layout_id: str = "",
    event_context=None,
    strategy: Optional[dict] = None,
    location_seed=None,
    layout_seed=None,
    seed_audit=None,
    file_audit=None,
    resolver_result=None,
    alignment=None,
    station_map=None,
    station_map_exists: Optional[bool] = None,
    offset_calibration=None,
    truth_validation=None,
) -> TrackContext:
    """Build the canonical TrackContext from the current app state.

    All model/state parameters are duck-typed result objects produced by the
    **existing** loaders — this builder performs no file I/O and invents no
    geometry truth:

    - ``selected_location_id`` / ``selected_layout_id`` — the Track Modelling
      combo selection (highest-priority identity input).
    - ``event_context`` / ``strategy`` — identity fallbacks only (EventContext
      race rules are never copied).
    - ``location_seed`` / ``layout_seed`` — ``TrackLocationSeed`` /
      ``TrackLayoutSeed`` (display names, corners_expected, modelling_status,
      corner/sector/complex definitions).
    - ``seed_audit`` — ``SeedAuditResult`` from ``audit_layout_seed()``.
    - ``file_audit`` — ``TrackModelFileAudit`` from ``audit_track_model_files()``.
    - ``resolver_result`` — ``TrackModelResolverResult`` from
      ``resolve_best_track_model()``.
    - ``alignment`` — ``TrackModelAlignmentResult`` from ``align_track_model()``
      or a loaded accepted model.
    - ``station_map`` / ``station_map_exists`` — the in-memory
      ``TrackStationMap`` (preferred) or a bare existence flag.
    - ``offset_calibration`` — ``LapStartOffsetCalibration`` or None.
    - ``truth_validation`` — ``TrackTruthValidationResult`` or None (gates are
      echoed tri-state; None = unknown).

    Never raises. Returns an EMPTY-source context when nothing is available.
    """
    identity, source = _resolve_identity(
        selected_location_id, selected_layout_id,
        event_context, strategy, location_seed, layout_seed,
    )

    # ---- availability ----------------------------------------------------- #
    has_seed_obj = layout_seed is not None
    corner_defs = _get(layout_seed, "corner_definitions") or []
    sector_defs = _get(layout_seed, "sector_definitions") or []
    complex_defs = _get(layout_seed, "corner_complexes") or []

    seed_metadata_available = _as_bool(_get(seed_audit, "has_metadata"), has_seed_obj)
    seed_lap_length_available = _as_bool(
        _get(seed_audit, "has_lap_length"),
        _as_float(_get(layout_seed, "length_m")) > 0,
    )
    seed_corner_windows_available = _as_bool(
        _get(seed_audit, "has_corner_windows"), bool(corner_defs))
    seed_sector_definitions_available = _as_bool(
        _get(seed_audit, "has_sector_definitions"), bool(sector_defs))
    seed_corner_complexes_available = _as_bool(
        _get(seed_audit, "has_corner_complexes"), bool(complex_defs))
    seed_geometry_available = _as_bool(_get(seed_audit, "has_seed_centreline"), False)
    seed_source = _as_str(_get(seed_audit, "seed_source"), "none") or "none"
    seed_corner_count = _as_int(_get(seed_audit, "corner_count"), len(corner_defs))

    reference_path_available = _as_bool(_get(file_audit, "ref_path_exists"), False)
    reference_path_point_count = _as_int(_get(file_audit, "ref_path_point_count"), 0)
    calibration_laps_available = _as_bool(_get(file_audit, "calibration_laps_exists"), False)
    reviewed_model_available = _as_bool(_get(file_audit, "reviewed_exists"), False)

    if station_map is not None:
        station_map_available = True
        try:
            station_map_station_count = _as_int(
                station_map.station_count() if callable(_get(station_map, "station_count"))
                else _get(station_map, "station_count")
            )
        except Exception:  # pragma: no cover - defensive
            station_map_station_count = 0
    else:
        # No in-memory station map — fall back to the explicit existence flag or
        # the disk audit (Sprint 3), so a fresh restart still sees an on-disk map.
        station_map_available = (
            _as_bool(station_map_exists, False)
            or _as_bool(_get(file_audit, "station_map_exists"), False)
        )
        station_map_station_count = 0

    # Accepted model: in-memory alignment OR the disk audit (Sprint 3).
    accepted_model_available = (
        _as_bool(_get(alignment, "accepted"), False)
        or _as_bool(_get(file_audit, "accepted_exists"), False)
    )

    lap_offset_available, lap_offset_status, lap_offset_confidence = (
        _derive_lap_offset(offset_calibration)
    )
    if not lap_offset_available:
        lap_offset_available = _as_bool(_get(file_audit, "offset_exists"), False)
        if lap_offset_available:
            lap_offset_status = "on_disk_not_loaded"

    availability = TrackMapAvailability(
        seed_metadata_available=seed_metadata_available,
        seed_lap_length_available=seed_lap_length_available,
        seed_corner_windows_available=seed_corner_windows_available,
        seed_sector_definitions_available=seed_sector_definitions_available,
        seed_corner_complexes_available=seed_corner_complexes_available,
        seed_geometry_available=seed_geometry_available,
        seed_source=seed_source,
        seed_corner_count=seed_corner_count,
        reference_path_available=reference_path_available,
        reference_path_point_count=reference_path_point_count,
        calibration_laps_available=calibration_laps_available,
        station_map_available=station_map_available,
        station_map_station_count=station_map_station_count,
        reviewed_model_available=reviewed_model_available,
        accepted_model_available=accepted_model_available,
        lap_offset_available=lap_offset_available,
    )

    # ---- geometry status --------------------------------------------------- #
    resolved = _get(resolver_result, "resolved_model")
    modelling_status = (
        _as_str(_get(resolved, "modelling_status"))
        or _enum_value(_get(layout_seed, "modelling_status"), "")
        or "not_modelled"
    )
    geometry = TrackGeometryStatus(
        modelling_status=modelling_status,
        ai_ready=_as_bool(_get(resolved, "ai_ready"), False),
        resolution_status=_enum_value(
            _get(resolver_result, "resolution_status"), "missing"),
        model_source_type=_enum_value(_get(resolved, "source_type"), "missing"),
        corners_expected=_as_int(_get(layout_seed, "corners_expected"), 0),
        lap_length_seed_m=_as_float(_get(layout_seed, "length_m"), 0.0),
        lap_length_model_m=_as_float(_get(alignment, "lap_length_m_model"), 0.0),
        truth_accepted=_as_opt_bool(_get(truth_validation, "is_accepted")),
        truth_usable_for_live_mapping=_as_opt_bool(
            _get(truth_validation, "is_usable_for_live_mapping")),
        truth_usable_for_ai_corner_context=_as_opt_bool(
            _get(truth_validation, "is_usable_for_ai_corner_context")),
    )

    # ---- alignment status --------------------------------------------------- #
    # "Available" requires a real alignment-shaped object (it always carries
    # match_status) — a stray value must not read as a computed alignment.
    alignment_available = _get(alignment, "match_status") is not None
    alignment_status = TrackAlignmentStatus(
        available=alignment_available,
        match_status=_enum_value(_get(alignment, "match_status"), "NOT_READY"),
        accepted=_as_bool(_get(alignment, "accepted"), False),
        accepted_at=_as_str(_get(alignment, "accepted_at")),
        lap_length_delta_pct=_as_float(_get(alignment, "lap_length_delta_pct"), 0.0),
        blocker_count=len(_get(alignment, "blockers") or []),
        warning_count=len(_get(alignment, "warnings") or []),
        corner_position_match=_as_str(
            _get(alignment, "corner_position_match"), "NOT_AVAILABLE") or "NOT_AVAILABLE",
    )

    event_change_hash = _as_str(_get(event_context, "change_hash"))

    canonical = {
        "identity": identity.to_dict(),
        "availability": availability.to_dict(),
        "geometry": geometry.to_dict(),
        "alignment": alignment_status.to_dict(),
        "lap_offset_status": lap_offset_status,
        "lap_offset_confidence": lap_offset_confidence,
    }
    change_hash = (
        "" if source == TrackContextSource.EMPTY else compute_change_hash(canonical)
    )

    return TrackContext(
        identity=identity,
        source=source,
        availability=availability,
        geometry=geometry,
        alignment=alignment_status,
        lap_offset_status=lap_offset_status,
        lap_offset_confidence=lap_offset_confidence,
        change_hash=change_hash,
        event_change_hash=event_change_hash,
    )


def empty_track_context() -> TrackContext:
    """A well-formed EMPTY context (no track selected)."""
    return build_track_context()


# --------------------------------------------------------------------------- #
# Validation
# --------------------------------------------------------------------------- #
def validate_track_context(
    ctx: TrackContext,
    event_context=None,
) -> TrackContextValidationResult:
    """Return non-crashing validation warnings, keeping identity problems,
    missing-data notes and staleness/mismatch problems separate.

    Missing artefacts produce warnings, never exceptions — callers decide
    whether anything blocks. Availability warnings describe what is absent;
    they never claim what exists is accurate.
    """
    identity_warnings = []
    identity_missing = []
    availability_warnings = []
    staleness_warnings = []

    if ctx.source == TrackContextSource.EMPTY:
        return TrackContextValidationResult(
            ok=False,
            identity_warnings=("No track selected — pick one in Event Planner or Track Modelling.",),
            identity_missing=("track",),
        )

    if not ctx.identity.track_location_id:
        identity_warnings.append("No track location id — select a track in Track Modelling.")
        identity_missing.append("track_location_id")
    if not ctx.identity.layout_id:
        identity_warnings.append("No layout id — select a layout in Track Modelling.")
        identity_missing.append("layout_id")

    av = ctx.availability
    if not av.seed_metadata_available:
        availability_warnings.append("No seed metadata for this layout.")
    if not av.seed_geometry_available:
        availability_warnings.append(
            "No seed coordinate geometry — high-confidence corner mapping is unavailable.")
    if not av.reference_path_available:
        availability_warnings.append("No reference path built for this layout.")
    if not av.station_map_available:
        availability_warnings.append("No station map built for this layout.")
    if not av.accepted_model_available:
        availability_warnings.append("No accepted track model for this layout.")
    if not ctx.alignment.available:
        availability_warnings.append("Alignment has not been computed for this layout.")

    if event_context is not None:
        if ctx.mismatches_event(event_context):
            staleness_warnings.append(
                "Track Modelling selection does not match the active event's track.")
        if ctx.is_stale_for_event(event_context):
            staleness_warnings.append(
                "Track context is stale — the event changed after it was built.")

    ok = not identity_warnings and not availability_warnings and not staleness_warnings
    return TrackContextValidationResult(
        ok=ok,
        identity_warnings=tuple(identity_warnings),
        identity_missing=tuple(identity_missing),
        availability_warnings=tuple(availability_warnings),
        staleness_warnings=tuple(staleness_warnings),
    )


# --------------------------------------------------------------------------- #
# Bridge to ui/product_flow.py (mirrors event_context.flow_flags)
# --------------------------------------------------------------------------- #
def flow_flags(ctx: TrackContext) -> dict:
    """Track-derived flags for ``ui.product_flow.build_flow_state_summary``.

    Returns only keys that function accepts (splat-safe), so callers can merge:
    ``build_flow_state_summary(**{**event_flags, **flow_flags(track_ctx)})``.
    TrackContext's ``has_track`` supersedes EventContext's on merge — it is the
    canonical identity owner. Richer availability detail stays on the ctx
    itself (``availability`` / ``can_attempt_live_mapping``)."""
    return {
        "has_track": bool(
            ctx.identity.track_display_name or ctx.identity.track_location_id
        ),
    }
