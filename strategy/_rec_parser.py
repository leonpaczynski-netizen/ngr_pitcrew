"""Parse AI response text into structured recommendation records."""
from __future__ import annotations

import datetime as _dt
import json as _json
import re as _re
from typing import Any

_MAX_RECS = 10
_MAX_REC_CHARS = 1000
_MAX_FALLBACK_CHARS = 2000

_STRUCTURED_PREFIXES = _re.compile(r"^(\d+\.|#{2,3}|\-\ |\*\ )")


def parse_recommendations_from_response(
    response_text: str,
    feature: str,
    car_id: int,
    track: str,
    layout_id: str,
    session_id: int,
    ai_interaction_id: int | None,
) -> list[dict[str, Any]]:
    """Split an AI response into discrete recommendation records.

    Returns a list of dicts ready for SessionDB.insert_setup_recommendations().
    Returns an empty list if response_text is empty.
    """
    if not response_text or not response_text.strip():
        return []

    # Extract recommendation_status from the JSON payload when present.
    # The setup-advice and combined-setup paths serialise the full validated _data dict
    # as _response_text; that dict carries recommendation_status after _finalise_recommendation.
    # Non-setup coaching paths produce plain prose with no JSON, so we default to 'proposed'.
    _lifecycle_status: str | None = None
    try:
        _parsed = _json.loads(response_text)
        if isinstance(_parsed, dict):
            _lifecycle_status = _parsed.get("recommendation_status") or None
    except (ValueError, TypeError):
        pass  # Plain-text response — status stays None → default 'proposed'

    created_at = _dt.datetime.utcnow().isoformat()
    base: dict[str, Any] = {
        "ai_interaction_id": ai_interaction_id,
        "session_id": session_id,
        "car_id": car_id,
        "track": track,
        "layout_id": layout_id,
        "feature": feature,
        "created_at": created_at,
    }
    # Attach final lifecycle status when available; fall back to 'proposed' for legacy paths.
    if _lifecycle_status is not None:
        base["status"] = _lifecycle_status

    blocks = [b.strip() for b in response_text.split("\n\n") if b.strip()]
    qualified = [b for b in blocks if _STRUCTURED_PREFIXES.match(b)]

    if not qualified:
        return [{**base, "recommendation_text": response_text[:_MAX_FALLBACK_CHARS]}]

    return [
        {**base, "recommendation_text": b[:_MAX_REC_CHARS]}
        for b in qualified[:_MAX_RECS]
    ]
