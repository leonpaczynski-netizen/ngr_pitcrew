"""Headless build → validate → activate for the guided track-modelling flow.

The new shell's ``TrackModellingService`` owns the *sequence* of the guided
workflow but performs no algorithms itself: the coordinator-action steps that build
a model are supplied as injected ``builders`` (see ``services/track_modelling.py``).
This module is that injection — it reuses the **exact** domain calls the classic
Track Modelling tab makes (``ui/track_modelling_ui.py``), so the display shell drives
the same pipeline without the classic tab's fourteen simultaneous sections.

Pure sequencing over the domain. No Qt. Every runner takes a ``TrackModellingSession``
and returns either a new session (success) or an ``(ok, message, session)`` tuple —
the two shapes ``TrackModellingService._run`` accepts.

Threading of artefacts between steps:
  * ``build_model``  → reference path + station map + detected corners (has_*).
  * ``validate``     → alignment result; sets ``validation_passed`` when it matches.
  * ``activate``     → writes the accepted-model + reviewed-segments files to disk,
                       which is what makes the model "approved/active".
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable, Dict, List

from data.track_modelling_session import TrackModellingSession


# Segment types that are telemetry-behaviour overlays (braking/traction/gear/...),
# not geometry corners — the corner review list shows only real corners, exactly as
# the classic tab filters them (ui/track_modelling_ui.py:87-94).
def _geometry_segments(review) -> list:
    if review is None:
        return []
    try:
        from data.track_segment_detection import TrackSegmentType as T
        overlay = {
            T.BRAKING_ZONE, T.TRACTION_ZONE, T.GEAR_ZONE, T.LIMITER_ZONE,
            T.FUEL_SAVING_CANDIDATE, T.KERB_OR_BUMP_CANDIDATE,
        }
        return [s for s in (getattr(review, "segments", None) or [])
                if getattr(s, "segment_type", None) not in overlay]
    except Exception:
        return list(getattr(review, "segments", None) or [])


#: Review status → the plain phrase the corner list shows, so the driver can SEE that
#: "Looks right"/"Not a corner"/… actually took. Blank statuses (unreviewed) show nothing.
_STATUS_PHRASE = {
    "confirmed": "✓ confirmed",
    "engineer_validated": "✓ validated",
    "rejected": "rejected — won't be used",
    "renamed": "edited",
    "split_required": "flagged to split on rebuild",
    "merge_required": "flagged to merge",
    "needs_more_laps": "needs more laps",
}


def corners_for_review(session: TrackModellingSession) -> List[dict]:
    """The detected corners as the guided page's review table renders them.

    Keys match ``TrackModellingPage._render_corners``: number/name/type/confidence/
    status/note. Empty when nothing has been detected yet.
    """
    review = session.artefact("review") if session is not None else None
    out: List[dict] = []
    for i, seg in enumerate(_geometry_segments(review)):
        conf = getattr(getattr(seg, "confidence", None), "value", None) or \
            getattr(seg, "confidence", "")
        seg_type = getattr(getattr(seg, "segment_type", None), "value", "") or ""
        status_raw = getattr(getattr(seg, "review_status", None), "value", None) or \
            getattr(seg, "review_status", "") or ""
        out.append({
            "number": (seg.turn_number if getattr(seg, "turn_number", None) is not None
                       else i + 1),
            "name": getattr(seg, "display_name", "") or "",
            "type": str(seg_type).replace("_", " ").title(),
            "confidence": str(conf),
            "status": _STATUS_PHRASE.get(str(status_raw), ""),
            "note": "; ".join(getattr(seg, "warnings", None) or []),
        })
    return out


def geometry_segment_ids(session: TrackModellingSession) -> List[str]:
    """Segment ids in the same order and filtering as ``corners_for_review`` rows, so
    a display row index resolves to the exact segment that row shows (row → id)."""
    review = session.artefact("review") if session is not None else None
    return [str(getattr(s, "segment_id", "")) for s in _geometry_segments(review)]


def _resolve_seed(session: TrackModellingSession):
    """The official layout seed for this track, or None (unknown tracks degrade)."""
    try:
        from data.track_intelligence import resolve_track_layout
        return resolve_track_layout(session.location_id, session.layout_id)
    except Exception:
        return None


def _build_model(controller, session: TrackModellingSession):
    """Reference path → station map → corner detection, from the captured laps."""
    if controller is None:
        return (False, "No capture controller — cannot build a model.", session)

    # 1. Reference path from the usable captured laps.
    try:
        ref = controller.build_reference_path()
    except Exception as exc:
        return (False, f"Could not build a reference path: {exc}", session)
    if not getattr(ref, "success", False) or getattr(ref, "reference_path", None) is None:
        msg = "; ".join(getattr(ref, "warnings", None) or []) \
            or "Could not build a reference path from the captured laps."
        return (False, msg, session)
    ref_path = ref.reference_path

    # NB: the reference path is NOT persisted here. On-disk readiness treats any valid
    # reference path as "approved" (data/track_readiness.py: `ref_valid or accepted`),
    # so saving at build time would jump the guided flow straight to ACTIVE and make the
    # Review / Validate / Use-it steps dead. Persistence happens at ACTIVATE, once the
    # model has actually been validated against the track.
    seed = _resolve_seed(session)

    # 2. Station map (1 m stations) and persist it.
    from data.track_station_map import build_track_station_map, export_station_map_json
    station_map = build_track_station_map(ref_path, layout_seed=seed)
    try:
        export_station_map_json(station_map)
    except Exception:
        pass

    # 3. Detect corners/segments from the calibration session.
    from data.track_segment_detection import detect_track_segments
    from data.track_segment_review import create_review_from_detection
    detection = detect_track_segments(getattr(controller, "_session", None),
                                      layout_seed=seed)
    review = create_review_from_detection(detection)

    session = (session
               .cleared_error()
               .with_artefact("reference_path", ref_path)
               .with_artefact("station_map", station_map)
               .with_artefact("detection", detection)
               .with_artefact("review", review))
    return session


def _validate(session: TrackModellingSession):
    """Align the built model against the official seed. Passes on a good match."""
    station_map = session.artefact("station_map")
    if station_map is None:
        return (False, "Build the model before validating it.", session)

    from data.track_model_alignment import align_track_model
    seed = _resolve_seed(session)
    try:
        alignment = align_track_model(station_map, layout_seed=seed)
    except Exception as exc:
        return (False, f"Could not validate the model: {exc}", session)

    session = session.with_artefact("alignment", alignment)
    status = getattr(getattr(alignment, "match_status", None), "name", "") \
        or str(getattr(alignment, "match_status", ""))
    blockers = list(getattr(alignment, "blockers", None) or [])
    passed = status in ("GOOD_MATCH", "ACCEPTABLE_MATCH") and not blockers
    if not passed:
        reason = ("; ".join(blockers)
                  or f"The model does not line up with the track well enough yet "
                     f"({status.replace('_', ' ').lower() or 'no match'}). "
                     f"Record more clean laps and rebuild.")
        # ok=True (not an ERROR — the work is kept) but validation_passed stays False.
        return (True, reason, session.with_(validation_passed=False))
    return (True, "", session.with_(validation_passed=True))


def _activate(controller, session: TrackModellingSession):
    """Accept the validated model to disk, making it the approved/active model."""
    alignment = session.artefact("alignment")
    station_map = session.artefact("station_map")
    if alignment is None or station_map is None:
        return (False, "Validate the model before using it.", session)

    # Persist the reference path + calibration laps now (deferred from build) so the
    # approved model survives a restart. Best-effort — the accepted-model file below is
    # what actually flips the model to approved.
    if controller is not None and hasattr(controller, "save_reference_path"):
        try:
            controller.save_reference_path()
        except Exception:
            pass

    # Mark accepted, then write the accepted-model file (what flips is_approved on disk).
    try:
        alignment.accepted = True
        alignment.accepted_at = datetime.now(timezone.utc).isoformat()
    except Exception:
        pass
    from data.track_model_alignment import export_accepted_model_json
    try:
        export_accepted_model_json(
            alignment, station_map.track_location_id, station_map.layout_id)
    except Exception as exc:
        return (False, f"Could not save the accepted model: {exc}", session)

    # Reviewed-segments file makes the model AI-ready. Promote unreviewed → confirmed
    # and stamp the combo ids the resolver globs on, exactly as the classic accept does.
    review = session.artefact("review")
    if review is not None:
        try:
            from data.track_segment_review import SegmentReviewStatus, export_review_json
            for seg in getattr(review, "segments", None) or []:
                if getattr(seg, "review_status", None) == SegmentReviewStatus.UNREVIEWED:
                    seg.review_status = SegmentReviewStatus.CONFIRMED
            review.track_location_id = station_map.track_location_id
            review.layout_id = station_map.layout_id
            export_review_json(review)
        except Exception:
            pass

    return (True, "", session.with_(model_active=True, validation_passed=True))


def build_track_model_builders(controller) -> Dict[str, Callable]:
    """The injected ``builders`` for ``TrackModellingService`` — keyed by the
    coordinator action value the guided page emits."""
    return {
        "build_model": lambda session: _build_model(controller, session),
        "validate": _validate,
        "activate": lambda session: _activate(controller, session),
    }
