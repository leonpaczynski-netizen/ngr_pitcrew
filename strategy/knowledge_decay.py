"""Knowledge Decay — deterministic decay signals for a knowledge domain (Program 2, Phase 26).

Extracts the visible signals that decide re-validation status, from a Phase-25 convergence entry +
its timeline points + the programme-level context/version changes. Age ALONE never decays
knowledge: there is no fixed expiry period and no "older than N days" rule. Re-validation is
caused only by explicit context change, version change, unresolved conflict, regression,
dependent-only evidence, insufficient date/context evidence or known supersession. Stable,
independent, compatible evidence stays current despite being old.

Purity: Qt-free, DB-free, UI-free, network-free, AI-free; no random, no wall-clock (no current-date
lookup); deterministic; never raises.
"""
from __future__ import annotations

from typing import List, Mapping, Sequence, Tuple

KNOWLEDGE_DECAY_VERSION = "knowledge_decay_v1"

# Domain transfer classes (Phase 23) considered context-bound.
_CONTEXT_BOUND = ("context_bound", "car_track_specific", "driver_specific")
# Minimum genuinely-independent lines below which evidence is "dependent-heavy".
MIN_INDEPENDENT_FOR_ROBUST = 2
_UNKNOWN_DATE = "unknown"


def _lc(v) -> str:
    return str(v if v is not None else "").strip().lower()


def _int(v) -> int:
    try:
        return int(v or 0)
    except (TypeError, ValueError):
        return 0


def programme_context_changes(compatibility: Mapping) -> dict:
    """From the Phase-22 compatibility block, determine what programme context has changed relative
    to the source group: a version change exists when an other group shares the source car+driver
    but differs in gt7_version; the changed fields are read from the excluded_reasons'
    differing_fields verbatim (never inferred). Never raises."""
    comp = compatibility if isinstance(compatibility, Mapping) else {}
    src = comp.get("primary_key") or {}
    src_car, src_driver = _lc(src.get("car")), _lc(src.get("driver"))
    changed_fields = set()
    version_changed = False
    for e in (comp.get("excluded_reasons") or []):
        if not isinstance(e, Mapping):
            continue
        diffs = [_lc(f) for f in (e.get("differing_fields") or [])]
        key = e.get("compatibility_key") or {}
        for f in diffs:
            changed_fields.add(f)
        # a same-car, same-driver group that differs only in version = a version change.
        if "gt7_version" in diffs and _lc(key.get("car")) == src_car \
                and _lc(key.get("driver")) == src_driver:
            version_changed = True
    return {"version_changed": version_changed,
            "changed_fields": tuple(sorted(changed_fields))}


def decay_signals(convergence: Mapping, timeline_points: Sequence[Mapping],
                  programme_changes: Mapping) -> dict:
    """Compute the visible decay signals for ONE domain. Never raises."""
    c = convergence if isinstance(convergence, Mapping) else {}
    pts = [p for p in (timeline_points or []) if isinstance(p, Mapping)]
    pc = programme_changes if isinstance(programme_changes, Mapping) else {}

    status = _lc(c.get("convergence_status"))
    independent = _int(c.get("independent_support_count"))
    dependent = _int(c.get("dependent_support_count"))
    regressions = _int(c.get("regression_count"))
    conflicts = _int(c.get("conflict_count"))
    transfer_limits = list(c.get("transfer_limitations") or [])
    retired = list(c.get("retired_directions") or [])

    dates = [_lc(p.get("evidence_date")) for p in pts]
    known_dates = [d for d in dates if d and d != _UNKNOWN_DATE]
    all_dates_unknown = bool(pts) and not known_dates
    some_dates_unknown = any(d == _UNKNOWN_DATE or not d for d in dates)
    last_known_date = max(known_dates) if known_dates else ""

    version_sensitive = any("gt7_version" in _lc(t) or "version" in _lc(t)
                            for t in transfer_limits)
    context_bound = (status == "stable_but_context_bound"
                     or any(cls in _lc(t) for t in transfer_limits for cls in _CONTEXT_BOUND)
                     or bool(transfer_limits))
    context_unknown = _int(c.get("compatible_contexts")) == 0 and not known_dates \
        and status in ("insufficient_evidence", "unknown")

    return {
        "convergence_status": status,
        "is_superseded": status == "superseded",
        "has_conflict": status == "conflicting" or conflicts > 0,
        "has_regression": status == "regressed" or regressions > 0 or bool(retired),
        "retired_directions": tuple(retired),
        "is_confirmed_good": bool(c.get("confirmed_good")),
        "is_context_bound": context_bound,
        "independent_count": independent, "dependent_count": dependent,
        "dependent_heavy": independent < MIN_INDEPENDENT_FOR_ROBUST and dependent > independent,
        "all_dates_unknown": all_dates_unknown, "some_dates_unknown": some_dates_unknown,
        "last_known_date": last_known_date,
        "version_sensitive": version_sensitive,
        "version_changed": bool(pc.get("version_changed")),
        "version_unknown": not last_known_date and version_sensitive and not pts,
        "context_changed_fields": tuple(pc.get("changed_fields") or ()),
        "context_unknown": context_unknown,
        "transfer_limited": bool(transfer_limits),
        "maturity": _lc(c.get("current_maturity")), "confidence": _lc(c.get("current_confidence")),
    }


def decay_versions() -> dict:
    return {"knowledge_decay": KNOWLEDGE_DECAY_VERSION}
