"""Getting a corner model for a circuit, without renumbering it every session.

`detect_corners` runs on one reference lap. Running it afresh each session would
renumber the corners the first time the driver took a different line, and a
corner aggregate is worthless if `T3` means a different corner next week. So a
model is detected once, stored against the circuit, and reused.

It is rebuilt only when the stored model does not apply — a different layout,
which shows up as a lap length outside tolerance.
"""
from __future__ import annotations

from pitcrew.analysis.corner_model import (
    CornerModel,
    detect_corners,
    model_id_for,
)


def circuit_key(track: str, layout: str | None = None) -> str:
    return model_id_for(track, layout)


def resolve_corner_model(store, track: str, layout: str | None,
                         reference_frames: list[dict] | None) -> CornerModel | None:
    """The stored model for this circuit, detecting and saving one if needed.

    Returns None when there is no stored model and the reference lap cannot be
    segmented. None means the export omits `corners` — which is honest — rather
    than inventing corner identities.
    """
    key = circuit_key(track, layout)
    stored = store.get_corner_model(key)

    lap_length = _lap_length(reference_frames)
    if stored is not None:
        if lap_length is None or stored.applies_to(lap_length):
            return stored
        # A different lap length at the same circuit key means a different
        # layout. Supersede rather than silently aggregate against windows that
        # do not fit the track.
        version = stored.version + 1
    else:
        version = 1

    if not reference_frames:
        return stored

    detected = detect_corners(reference_frames, key, version=version)
    if detected is None:
        return stored
    store.save_corner_model(key, detected)
    return detected


def _lap_length(frames: list[dict] | None) -> float | None:
    if not frames:
        return None
    distances = [f["road_distance_m"] for f in frames
                 if f.get("road_distance_m") is not None]
    return max(distances) if distances else None
