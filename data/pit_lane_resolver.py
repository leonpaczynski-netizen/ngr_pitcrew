"""Group 55 — Track-Specific Pit-Lane Mapping: pure pit-lane segment resolver.

WHY IT EXISTS
  Group 54 can count pit stops and age the current stint, but pit *confidence*
  still rests on tracker heuristics only: a refuel-based stop is MEDIUM, a
  speed-only sustained stop is LOW (GT7 broadcasts no explicit pit flag). This
  module adds an INDEPENDENT, corroborating line of evidence: if the car's live
  lap-progress falls inside a track's *known* pit-lane corridor, the pit/stint
  evidence is stronger.

WHAT THIS MODULE IS
  A pure, deterministic resolver over explicit pit-lane metadata carried on a
  resolved track model / track-library layout. Given a normalised lap progress
  (0.0–1.0) and that metadata, it reports which pit-lane zone the car is in:
  pit entry / pit lane body / pit exit / not-pit-lane / unknown.

WHAT THIS MODULE IS NOT
  • It never CREATES a pit stop and never counts one — Group 54 owns pit events.
    Pit-lane position is corroborating evidence only.
  • It never INFERS a pit lane from ordinary racing segments — a zone is reported
    only where explicit pit-lane metadata exists.
  • It writes no files, calls no AI, needs no DB, imports no Qt, and never raises
    on partial / malformed / older track-model dictionaries — missing or unusable
    mapping degrades to UNKNOWN (never treated as "safe" or "in the pit lane").
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class PitLaneZone(str, Enum):
    """Where the car is relative to the known pit-lane corridor."""
    UNKNOWN = "UNKNOWN"            # no usable mapping, or live progress unknown
    NOT_PIT_LANE = "NOT_PIT_LANE"  # position known, on the racing track
    PIT_ENTRY = "PIT_ENTRY"
    PIT_LANE = "PIT_LANE"          # pit-lane body
    PIT_EXIT = "PIT_EXIT"

    @property
    def is_inside(self) -> bool:
        return self in (PitLaneZone.PIT_ENTRY, PitLaneZone.PIT_LANE, PitLaneZone.PIT_EXIT)


class PitLaneMappingConfidence(str, Enum):
    """How trustworthy the pit-lane mapping itself is."""
    NONE = "NONE"      # no mapping available
    LOW = "LOW"        # estimated / seed
    MEDIUM = "MEDIUM"  # track_library sourced
    HIGH = "HIGH"      # engineer-validated / verified


# Map the JSON zone strings → PitLaneZone. Anything else is ignored (no inference).
_ZONE_STRINGS = {
    "pit_entry": PitLaneZone.PIT_ENTRY,
    "entry": PitLaneZone.PIT_ENTRY,
    "pit_lane": PitLaneZone.PIT_LANE,
    "pit_lane_body": PitLaneZone.PIT_LANE,
    "lane": PitLaneZone.PIT_LANE,
    "pit_exit": PitLaneZone.PIT_EXIT,
    "exit": PitLaneZone.PIT_EXIT,
}

# Map a mapping "source"/"confidence" label → PitLaneMappingConfidence.
_SOURCE_CONFIDENCE = {
    "engineer_validated": PitLaneMappingConfidence.HIGH,
    "verified": PitLaneMappingConfidence.HIGH,
    "high": PitLaneMappingConfidence.HIGH,
    "track_library": PitLaneMappingConfidence.MEDIUM,
    "reviewed": PitLaneMappingConfidence.MEDIUM,
    "medium": PitLaneMappingConfidence.MEDIUM,
    "estimated": PitLaneMappingConfidence.LOW,
    "seed": PitLaneMappingConfidence.LOW,
    "low": PitLaneMappingConfidence.LOW,
}


@dataclass(frozen=True)
class PitLaneSegment:
    """One pit-lane corridor span, expressed in normalised lap progress (0–1)."""
    zone: PitLaneZone
    start_progress: float
    end_progress: float
    label: str = ""
    source: str = ""
    confidence: Optional[PitLaneMappingConfidence] = None

    @property
    def wrapped(self) -> bool:
        """True when the span wraps past the start/finish line (start > end)."""
        return self.start_progress > self.end_progress

    @property
    def span(self) -> float:
        """Wrapped length of the span in progress units (0–1)."""
        if self.wrapped:
            return (1.0 - self.start_progress) + self.end_progress
        return self.end_progress - self.start_progress


@dataclass(frozen=True)
class PitLaneResolution:
    """Result of resolving a live progress value against pit-lane mapping."""
    zone: PitLaneZone = PitLaneZone.UNKNOWN
    confidence: PitLaneMappingConfidence = PitLaneMappingConfidence.NONE
    source: str = "missing"
    message: str = ""
    matched_segment_label: str = ""
    track_id: str = ""
    layout_id: str = ""

    @property
    def is_inside_pit_lane(self) -> bool:
        return self.zone.is_inside

    @property
    def has_mapping(self) -> bool:
        return self.confidence is not PitLaneMappingConfidence.NONE


# ---------------------------------------------------------------------------
# Progress helpers
# ---------------------------------------------------------------------------

def normalise_progress(value) -> Optional[float]:
    """Coerce a lap-progress value into [0.0, 1.0), or None when unusable.

    Accepts a fraction (0–1). Values at/above 1.0 wrap (1.0 → 0.0, 1.25 → 0.25).
    Rejects None / non-numeric / NaN / infinite. Never raises.
    """
    try:
        if value is None:
            return None
        v = float(value)
    except (TypeError, ValueError):
        return None
    # Reject NaN / inf (NaN != NaN).
    if v != v or v in (float("inf"), float("-inf")):
        return None
    # Wrap into [0, 1).
    v = v % 1.0
    if v < 0.0:
        v += 1.0
    # Guard tiny float error landing exactly on 1.0.
    if v >= 1.0:
        v = 0.0
    return v


def progress_in_wrapped_range(progress, start, end) -> bool:
    """True when ``progress`` lies within [start, end], wrapping past the line.

    ``start`` may exceed ``end`` (a span that crosses the start/finish line, e.g.
    pit exit 0.985 → 0.025). Endpoints are inclusive. Invalid inputs → False.
    """
    p = normalise_progress(progress)
    s = normalise_progress(start)
    e = normalise_progress(end)
    if p is None or s is None or e is None:
        return False
    if s == e:
        # Zero-width (or ambiguous full-lap) span — never a match.
        return False
    if s < e:
        return s <= p <= e
    # Wrapped span: [s, 1) ∪ [0, e].
    return p >= s or p <= e


# ---------------------------------------------------------------------------
# Segment building (from explicit pit-lane metadata only)
# ---------------------------------------------------------------------------

def _pit_lane_block(track_context) -> Optional[dict]:
    """Extract the ``pit_lane`` mapping block from a dict- or object-like context."""
    if track_context is None:
        return None
    block = None
    if isinstance(track_context, dict):
        block = track_context.get("pit_lane")
    else:
        block = getattr(track_context, "pit_lane", None)
    if isinstance(block, dict):
        return block
    return None


def _mapping_confidence(block: dict) -> PitLaneMappingConfidence:
    """Derive the mapping's own confidence from its confidence/source label."""
    for key in ("confidence", "source"):
        raw = block.get(key)
        if raw:
            mapped = _SOURCE_CONFIDENCE.get(str(raw).strip().lower())
            if mapped is not None:
                return mapped
    return PitLaneMappingConfidence.MEDIUM  # available but unlabelled → MEDIUM


def build_pit_lane_segments_from_track_context(track_context) -> list[PitLaneSegment]:
    """Build validated pit-lane segments from a track context. Never raises.

    Returns [] when no explicit, usable pit-lane metadata exists. Only segments
    with a recognised zone and valid progress bounds are kept; malformed / partial
    entries are skipped silently (never inferred as pit lane).
    """
    try:
        block = _pit_lane_block(track_context)
        if block is None:
            return []
        if not block.get("available", True):
            return []
        raw_segments = block.get("segments")
        if not isinstance(raw_segments, (list, tuple)):
            return []
        default_conf = _mapping_confidence(block)
        default_source = str(block.get("source", "") or "")
        out: list[PitLaneSegment] = []
        for raw in raw_segments:
            if not isinstance(raw, dict):
                continue
            zone = _ZONE_STRINGS.get(str(raw.get("zone", "")).strip().lower())
            if zone is None:
                continue
            start = normalise_progress(raw.get("start_progress"))
            end = normalise_progress(raw.get("end_progress"))
            if start is None or end is None or start == end:
                continue
            seg_conf = _SOURCE_CONFIDENCE.get(str(raw.get("confidence", "")).strip().lower())
            out.append(PitLaneSegment(
                zone=zone,
                start_progress=start,
                end_progress=end,
                label=str(raw.get("label", "") or ""),
                source=str(raw.get("source", "") or default_source),
                confidence=seg_conf if seg_conf is not None else default_conf,
            ))
        return out
    except Exception:
        return []


_CONF_ORDER = {
    PitLaneMappingConfidence.NONE: 0,
    PitLaneMappingConfidence.LOW: 1,
    PitLaneMappingConfidence.MEDIUM: 2,
    PitLaneMappingConfidence.HIGH: 3,
}


def segments_mapping_confidence(pit_lane_segments) -> PitLaneMappingConfidence:
    """The strongest confidence across usable segments (NONE when none). Never raises."""
    try:
        confs = [
            (s.confidence or PitLaneMappingConfidence.MEDIUM)
            for s in (pit_lane_segments or []) if isinstance(s, PitLaneSegment)
        ]
        if not confs:
            return PitLaneMappingConfidence.NONE
        return max(confs, key=lambda c: _CONF_ORDER[c])
    except Exception:
        return PitLaneMappingConfidence.NONE


# ---------------------------------------------------------------------------
# Resolution
# ---------------------------------------------------------------------------

def resolve_pit_lane_zone(progress, pit_lane_segments) -> PitLaneResolution:
    """Resolve which pit-lane zone ``progress`` is in, given explicit segments.

    • No usable segments            → UNKNOWN (confidence NONE).
    • Progress unknown / invalid    → UNKNOWN (confidence NONE), but note that
                                      mapping exists so the caller can say so.
    • Progress inside a pit segment → that zone (narrowest matching span wins).
    • Progress valid, no match      → NOT_PIT_LANE (position known, on track).
    Never raises.
    """
    try:
        segments = [s for s in (pit_lane_segments or []) if isinstance(s, PitLaneSegment)]
        if not segments:
            return PitLaneResolution(
                zone=PitLaneZone.UNKNOWN,
                confidence=PitLaneMappingConfidence.NONE,
                source="missing",
                message="No pit-lane mapping available for this track/layout.",
            )

        # Overall mapping confidence = the strongest segment confidence present.
        map_conf = segments_mapping_confidence(segments)
        map_source = next((s.source for s in segments if s.source), "track_model")

        p = normalise_progress(progress)
        if p is None:
            return PitLaneResolution(
                zone=PitLaneZone.UNKNOWN,
                confidence=PitLaneMappingConfidence.NONE,
                source=map_source,
                message="Pit-lane mapping exists but live track progress is unavailable.",
            )

        # Narrowest matching span wins (entry/exit are narrower than the body).
        best: Optional[PitLaneSegment] = None
        for seg in segments:
            if progress_in_wrapped_range(p, seg.start_progress, seg.end_progress):
                if best is None or seg.span < best.span:
                    best = seg
        if best is not None:
            return PitLaneResolution(
                zone=best.zone,
                confidence=best.confidence or map_conf,
                source=best.source or map_source,
                message=f"Inside {best.zone.value} per track model"
                        + (f" ({best.label})" if best.label else "") + ".",
                matched_segment_label=best.label,
            )

        # Position known, but not in any pit-lane span → on the racing track.
        return PitLaneResolution(
            zone=PitLaneZone.NOT_PIT_LANE,
            confidence=map_conf,
            source=map_source,
            message="Live position is on the racing track (not in the pit-lane corridor).",
        )
    except Exception:
        return PitLaneResolution(
            zone=PitLaneZone.UNKNOWN,
            confidence=PitLaneMappingConfidence.NONE,
            source="missing",
            message="Pit-lane resolution unavailable.",
        )


def resolve_pit_lane_from_track_context(progress, track_context) -> PitLaneResolution:
    """Build segments from a track context and resolve ``progress`` against them.

    Attaches track_id / layout_id from the context where available. Never raises;
    returns an UNKNOWN/NONE resolution when no usable pit-lane metadata exists.
    """
    try:
        segments = build_pit_lane_segments_from_track_context(track_context)
        res = resolve_pit_lane_zone(progress, segments)
        track_id, layout_id = _context_ids(track_context)
        if track_id or layout_id:
            return PitLaneResolution(
                zone=res.zone, confidence=res.confidence, source=res.source,
                message=res.message, matched_segment_label=res.matched_segment_label,
                track_id=track_id, layout_id=layout_id,
            )
        return res
    except Exception:
        return PitLaneResolution(source="missing", message="Pit-lane resolution unavailable.")


def _context_ids(track_context) -> tuple[str, str]:
    """Best-effort (track_id, layout_id) from a dict- or object-like context."""
    def _get(key: str) -> str:
        if track_context is None:
            return ""
        if isinstance(track_context, dict):
            return str(track_context.get(key, "") or "")
        return str(getattr(track_context, key, "") or "")

    track_id = _get("track_id") or _get("track_location_id")
    layout_id = _get("layout_id")
    return track_id, layout_id
