"""Pure view-model for the Live Engineering State Monitor (Qt-free, Phase 7).

Turns the ``SessionDB.build_live_engineering_state`` result (a plain dict of a
``LiveEngineeringState`` + ``SessionDevelopmentLedger``) into the rows/lines/series
the Qt panel renders as engineering VISUALISATIONS — a health banner, an active/
resolved/protected issue table, a per-issue live trend sparkline, and a development
timeline — instead of one large plain-text box.

READ-ONLY presentation: it derives display strings only. It authors no setup value,
recommends no experiment and exposes no Apply control. Deterministic; never raises.
"""
from __future__ import annotations

from typing import List, Sequence, Tuple

ISSUE_TABLE_COLUMNS: Tuple[str, ...] = (
    "Issue", "Corner", "Phase", "Status", "Trend", "Recurrence",
    "Laps", "Last Lap", "Confidence",
)

TIMELINE_COLUMNS: Tuple[str, ...] = ("Lap", "Event", "Issue", "From", "To")

# Human labels (fallback = title-cased raw value).
_STATUS_LABEL = {
    "active": "Active", "recovering": "Recovering", "stable": "Stable",
    "resolved": "Resolved", "new": "New", "protected": "Protected",
    "damaged": "Protected — Damaged", "unknown": "Unknown",
}
_TREND_LABEL = {
    "improving": "Improving", "worsening": "Worsening", "unchanged": "Unchanged",
    "fluctuating": "Fluctuating", "insufficient_evidence": "Too few laps",
}
_BAND_LABEL = {
    "nominal": "Nominal — nothing active", "settling": "Settling — issues recovering",
    "developing": "Developing — active issues", "degrading": "Degrading — attention needed",
    "unknown": "Building picture — too few comparable laps",
}
_EVENT_LABEL = {
    "issue_detected": "Detected", "status_changed": "Status changed",
    "trend_changed": "Trend changed", "issue_resolved": "Resolved",
    "issue_regressed": "Regressed", "protected_damaged": "Protected damaged",
    "protected_restored": "Protected restored", "health_band_changed": "Health band",
}


def _label(mapping, key: str) -> str:
    return mapping.get(str(key or ""), str(key or "").replace("_", " ").title())


def health_band_label(state: dict) -> str:
    band = (state.get("health") or {}).get("band", "unknown")
    return _label(_BAND_LABEL, band)


def health_summary_rows(state: dict) -> List[Tuple[str, str]]:
    """Label/value pairs for the health banner (whole-car snapshot)."""
    h = state.get("health") or {}
    total = int(h.get("total_valid_laps") or 0)
    clean = int(h.get("clean_valid_laps") or 0)
    return [
        ("Health", health_band_label(state)),
        ("Comparable laps", str(total)),
        ("Clean laps", f"{clean}/{total}" if total else "0"),
        ("Active issues", str(h.get("active_issue_count") or 0)),
        ("New this session", str(h.get("new_issue_count") or 0)),
        ("Worsening", str(h.get("worsening_issue_count") or 0)),
        ("Recovering", str(h.get("recovering_issue_count") or 0)),
        ("Resolved", str(h.get("resolved_issue_count") or 0)),
        ("Protected intact", str(h.get("protected_intact_count") or 0)),
        ("Protected damaged", str(h.get("protected_damaged_count") or 0)),
    ]


def _issue_row(issue: dict) -> Tuple[str, ...]:
    ident = issue.get("identity") or {}
    cons = issue.get("consistency") or {}
    corner = ident.get("corner_name") or ident.get("segment_id") or "—"
    laps = f"{cons.get('affected_valid_laps', 0)}/{cons.get('total_valid_laps', 0)}"
    last = issue.get("last_observed_lap")
    return (
        str(ident.get("issue_type") or "—"),
        str(corner),
        str(ident.get("phase") or "—"),
        _label(_STATUS_LABEL, issue.get("status")),
        _label(_TREND_LABEL, issue.get("trend")),
        str(issue.get("recurrence_class") or "—"),
        laps,
        ("—" if last is None else str(last)),
        str(issue.get("confidence") or "—"),
    )


# Ordering: most-attention-worthy first, then stable by issue key.
_STATUS_ORDER = {"damaged": 0, "new": 1, "active": 2, "recovering": 3,
                 "stable": 4, "protected": 5, "resolved": 6, "unknown": 7}


def _sort_key(issue: dict):
    return (_STATUS_ORDER.get(str(issue.get("status") or ""), 9),
            (issue.get("identity") or {}).get("key", ""))


def issue_rows(state: dict) -> List[Tuple[str, ...]]:
    issues = sorted(state.get("issues") or [], key=_sort_key)
    return [_issue_row(i) for i in issues]


def active_issue_rows(state: dict) -> List[Tuple[str, ...]]:
    active = [i for i in (state.get("issues") or [])
              if str(i.get("status")) in ("active", "recovering", "new", "damaged")]
    return [_issue_row(i) for i in sorted(active, key=_sort_key)]


def resolved_issue_rows(state: dict) -> List[Tuple[str, ...]]:
    res = [i for i in (state.get("issues") or [])
           if str(i.get("status")) == "resolved"]
    return [_issue_row(i) for i in sorted(res, key=_sort_key)]


def protected_rows(state: dict) -> List[Tuple[str, ...]]:
    prot = [i for i in (state.get("issues") or []) if i.get("is_protected")]
    return [_issue_row(i) for i in sorted(prot, key=_sort_key)]


def trend_series(issue: dict, valid_lap_numbers: Sequence[int]) -> List[bool]:
    """Per-comparable-lap affected series for a sparkline (True = issue present)."""
    affected = set(issue.get("affected_lap_numbers") or ())
    return [int(l) in affected for l in valid_lap_numbers]


def trend_sparkline(issue: dict, valid_lap_numbers: Sequence[int]) -> str:
    """A tiny text sparkline (▇ present / · clear) — a compact per-lap trend glyph."""
    return "".join("▇" if present else "·"
                   for present in trend_series(issue, valid_lap_numbers))


def timeline_rows(result: dict) -> List[Tuple[str, ...]]:
    """Development-ledger rows (append-only engineering timeline)."""
    ledger = result.get("ledger") or {}
    out: List[Tuple[str, ...]] = []
    for e in ledger.get("events") or []:
        lap = e.get("lap_number")
        out.append((
            ("—" if lap is None else str(lap)),
            _label(_EVENT_LABEL, e.get("event_type")),
            str(e.get("issue_type") or "—"),
            str(e.get("from_value") or "—"),
            str(e.get("to_value") or "—"),
        ))
    return out


def is_empty(result: dict) -> bool:
    """True when there is nothing meaningful to show yet."""
    if not result or not result.get("ok"):
        return True
    state = result.get("live_state") or {}
    return not (state.get("issues") or []) and not (
        (result.get("ledger") or {}).get("events"))
