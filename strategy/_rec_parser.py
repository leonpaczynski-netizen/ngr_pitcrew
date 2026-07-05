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


def _safe_json(value: Any) -> "str | None":
    """JSON-encode a dict or list value; return None on failure or when value is None."""
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        try:
            return _json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        except Exception:
            return None
    return None


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

    Group 42: when response_text is a JSON payload from the rule-first pipeline,
    extracts and attaches the 8 v11 structured columns (best-effort; all default
    to None when absent so old callers and plain-text paths are unaffected).
    """
    if not response_text or not response_text.strip():
        return []

    # Extract recommendation_status from the JSON payload when present.
    # The setup-advice and combined-setup paths serialise the full validated _data dict
    # as _response_text; that dict carries recommendation_status after _finalise_recommendation.
    # Non-setup coaching paths produce plain prose with no JSON, so we default to 'proposed'.
    _lifecycle_status: str | None = None

    # v11 Group 42 structured columns — populated when response is a JSON dict.
    _deterministic_plan_json: "str | None" = None
    _ai_audit_json: "str | None" = None
    _approved_changes_json: "str | None" = None
    _rejected_changes_json: "str | None" = None
    _diagnosis_json: "str | None" = None
    _driver_profile_version: "str | None" = None
    _rule_engine_version: "str | None" = None

    try:
        _parsed = _json.loads(response_text)
        if isinstance(_parsed, dict):
            _lifecycle_status = _parsed.get("recommendation_status") or None

            # Group 42 structured fields — best-effort extraction
            _deterministic_plan_json = _safe_json(_parsed.get("deterministic_plan"))
            _ai_audit_json = _safe_json(_parsed.get("ai_audit"))
            _approved_changes_json = _safe_json(_parsed.get("changes"))
            _rejected_changes_json = _safe_json(_parsed.get("rejected_changes"))
            _diagnosis_json = _safe_json(_parsed.get("diagnosis"))

            # rule_engine_version: prefer value from response (future-proof),
            # fall back to the module constant.
            _rev_from_resp = _parsed.get("rule_engine_version") or None
            if _rev_from_resp and isinstance(_rev_from_resp, str):
                _rule_engine_version = _rev_from_resp
            else:
                try:
                    from strategy._setup_constants import RULE_ENGINE_VERSION
                    _rule_engine_version = RULE_ENGINE_VERSION
                except Exception:
                    _rule_engine_version = None

            # driver_profile_version: prefer from deterministic_plan dict if present.
            _dp_raw = _parsed.get("deterministic_plan")
            if isinstance(_dp_raw, dict):
                _driver_profile_version = _dp_raw.get("driver_profile_version") or None
            if not _driver_profile_version:
                _dpv_from_resp = _parsed.get("driver_profile_version") or None
                if _dpv_from_resp and isinstance(_dpv_from_resp, str):
                    _driver_profile_version = _dpv_from_resp
                else:
                    try:
                        from strategy.setup_driver_profile import build_driver_profile
                        _driver_profile_version = build_driver_profile().profile_version
                    except Exception:
                        _driver_profile_version = "v1.0-hardcoded"

    except (ValueError, TypeError):
        pass  # Plain-text response — all v11 fields stay None → default 'proposed'

    created_at = _dt.datetime.utcnow().isoformat()
    base: dict[str, Any] = {
        "ai_interaction_id": ai_interaction_id,
        "session_id": session_id,
        "car_id": car_id,
        "track": track,
        "layout_id": layout_id,
        "feature": feature,
        "created_at": created_at,
        # v11 Group 42 columns — None for legacy/plain-text paths
        "deterministic_plan_json": _deterministic_plan_json,
        "ai_audit_json": _ai_audit_json,
        "approved_changes_json": _approved_changes_json,
        "rejected_changes_json": _rejected_changes_json,
        "diagnosis_json": _diagnosis_json,
        "driver_profile_version": _driver_profile_version,
        "rule_engine_version": _rule_engine_version,
    }
    # Attach final lifecycle status when available; fall back to 'proposed' for legacy paths.
    if _lifecycle_status is not None:
        base["status"] = _lifecycle_status
        # validation_status mirrors the lifecycle status for the v11 column.
        base["validation_status"] = _lifecycle_status

    blocks = [b.strip() for b in response_text.split("\n\n") if b.strip()]
    qualified = [b for b in blocks if _STRUCTURED_PREFIXES.match(b)]

    if not qualified:
        return [{**base, "recommendation_text": response_text[:_MAX_FALLBACK_CHARS]}]

    return [
        {**base, "recommendation_text": b[:_MAX_REC_CHARS]}
        for b in qualified[:_MAX_RECS]
    ]
