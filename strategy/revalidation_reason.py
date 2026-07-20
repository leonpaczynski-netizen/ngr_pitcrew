"""Re-validation Reason — why established knowledge may need re-validation (Program 2, Phase 26).

A visible enum of the deterministic reasons that can put a knowledge domain into a re-validation
state, plus a pure helper that derives the applicable reasons from already-computed signals. It
never schedules, never generates a test plan, and never invents a cause - a reason is emitted only
when its explicit signal is present.

Purity: Qt-free, DB-free, UI-free, network-free, AI-free; no random, no wall-clock; deterministic;
never raises.
"""
from __future__ import annotations

from enum import Enum
from typing import List, Mapping, Tuple

REVALIDATION_REASON_VERSION = "revalidation_reason_v1"


class RevalidationReason(str, Enum):
    GT7_VERSION_CHANGED = "gt7_version_changed"
    CAR_CHANGED = "car_changed"
    MANUFACTURER_CHANGED = "manufacturer_changed"
    TRACK_CHANGED = "track_changed"
    LAYOUT_CHANGED = "layout_changed"
    DRIVER_CHANGED = "driver_changed"
    TYRE_COMPOUND_CHANGED = "tyre_compound_changed"
    TYRE_MULTIPLIER_CHANGED = "tyre_multiplier_changed"
    FUEL_MULTIPLIER_CHANGED = "fuel_multiplier_changed"
    WEATHER_CONTEXT_CHANGED = "weather_context_changed"
    EVENT_FORMAT_CHANGED = "event_format_changed"
    SETUP_CONTEXT_CHANGED = "setup_context_changed"
    EVIDENCE_TOO_DEPENDENT = "evidence_too_dependent"
    CONFLICT_INTRODUCED = "conflict_introduced"
    REGRESSION_OBSERVED = "regression_observed"
    KNOWLEDGE_SUPERSEDED = "knowledge_superseded"
    DIRECTION_RETIRED = "direction_retired"
    DATE_UNKNOWN = "date_unknown"
    VERSION_UNKNOWN = "version_unknown"
    CONTEXT_UNKNOWN = "context_unknown"


# Deterministic map: changed-context field name -> reason.
_CONTEXT_FIELD_REASON = {
    "gt7_version": RevalidationReason.GT7_VERSION_CHANGED,
    "car": RevalidationReason.CAR_CHANGED,
    "manufacturer": RevalidationReason.MANUFACTURER_CHANGED,
    "track": RevalidationReason.TRACK_CHANGED,
    "layout": RevalidationReason.LAYOUT_CHANGED,
    "layout_id": RevalidationReason.LAYOUT_CHANGED,
    "driver": RevalidationReason.DRIVER_CHANGED,
    "compound": RevalidationReason.TYRE_COMPOUND_CHANGED,
    "tyre_compound": RevalidationReason.TYRE_COMPOUND_CHANGED,
    "tyre_multiplier": RevalidationReason.TYRE_MULTIPLIER_CHANGED,
    "fuel_multiplier": RevalidationReason.FUEL_MULTIPLIER_CHANGED,
    "weather": RevalidationReason.WEATHER_CONTEXT_CHANGED,
    "event_format": RevalidationReason.EVENT_FORMAT_CHANGED,
    "discipline": RevalidationReason.EVENT_FORMAT_CHANGED,
    "setup_context": RevalidationReason.SETUP_CONTEXT_CHANGED,
}

_REASON_TEXT = {
    RevalidationReason.GT7_VERSION_CHANGED: "the GT7 version differs from the evidence version",
    RevalidationReason.CAR_CHANGED: "the car differs from the evidence car",
    RevalidationReason.MANUFACTURER_CHANGED: "the manufacturer differs from the evidence",
    RevalidationReason.TRACK_CHANGED: "the track differs from the evidence track",
    RevalidationReason.LAYOUT_CHANGED: "the layout differs from the evidence layout",
    RevalidationReason.DRIVER_CHANGED: "the driver differs from the evidence driver",
    RevalidationReason.TYRE_COMPOUND_CHANGED: "the tyre compound differs from the evidence",
    RevalidationReason.TYRE_MULTIPLIER_CHANGED: "the tyre wear multiplier differs from the evidence",
    RevalidationReason.FUEL_MULTIPLIER_CHANGED: "the fuel multiplier differs from the evidence",
    RevalidationReason.WEATHER_CONTEXT_CHANGED: "the weather context differs from the evidence",
    RevalidationReason.EVENT_FORMAT_CHANGED: "the event format / discipline differs from the evidence",
    RevalidationReason.SETUP_CONTEXT_CHANGED: "the setup context differs from the evidence",
    RevalidationReason.EVIDENCE_TOO_DEPENDENT: "the supporting evidence is dependent, not independent",
    RevalidationReason.CONFLICT_INTRODUCED: "conflicting evidence has been recorded",
    RevalidationReason.REGRESSION_OBSERVED: "a regression has been recorded",
    RevalidationReason.KNOWLEDGE_SUPERSEDED: "the conclusion was superseded by stronger evidence",
    RevalidationReason.DIRECTION_RETIRED: "the tested direction was retired",
    RevalidationReason.DATE_UNKNOWN: "the evidence date is unknown",
    RevalidationReason.VERSION_UNKNOWN: "the GT7 version of the evidence is unknown",
    RevalidationReason.CONTEXT_UNKNOWN: "the evidence context is unknown",
}


def _lc(v) -> str:
    return str(v if v is not None else "").strip().lower()


def context_change_reason(field: str) -> str:
    r = _CONTEXT_FIELD_REASON.get(_lc(field))
    return r.value if r else ""


def reasons_from_signals(signals: Mapping) -> Tuple[dict, ...]:
    """Derive the applicable re-validation reasons (each with its visible text) from a domain's
    already-computed decay signals. Only emits a reason when its explicit signal is present.
    Never raises."""
    s = signals if isinstance(signals, Mapping) else {}
    out: List[dict] = []
    seen = set()

    def _add(reason: RevalidationReason, detail: str = ""):
        if reason.value in seen:
            return
        seen.add(reason.value)
        out.append({"reason": reason.value,
                    "text": _REASON_TEXT.get(reason, reason.value)
                    + (f" ({detail})" if detail else "")})

    if s.get("is_superseded"):
        _add(RevalidationReason.KNOWLEDGE_SUPERSEDED)
    if s.get("retired_directions"):
        _add(RevalidationReason.DIRECTION_RETIRED)
    if s.get("has_conflict"):
        _add(RevalidationReason.CONFLICT_INTRODUCED)
    if s.get("has_regression"):
        _add(RevalidationReason.REGRESSION_OBSERVED)
    if s.get("version_sensitive") and s.get("version_changed"):
        _add(RevalidationReason.GT7_VERSION_CHANGED)
    if s.get("dependent_heavy"):
        _add(RevalidationReason.EVIDENCE_TOO_DEPENDENT)
    for field in (s.get("context_changed_fields") or ()):
        code = context_change_reason(field)
        if code:
            _add(RevalidationReason(code))
    if s.get("all_dates_unknown"):
        _add(RevalidationReason.DATE_UNKNOWN)
    if s.get("version_unknown"):
        _add(RevalidationReason.VERSION_UNKNOWN)
    if s.get("context_unknown"):
        _add(RevalidationReason.CONTEXT_UNKNOWN)
    return tuple(out)


def reason_versions() -> dict:
    return {"revalidation_reason": REVALIDATION_REASON_VERSION}
