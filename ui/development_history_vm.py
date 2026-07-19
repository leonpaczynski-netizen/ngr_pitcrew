"""Pure view-model for the Development History page (Qt-free, Phase 8).

Turns ``SessionDB.build_cross_session_memory`` (permanent memory + long-term metrics
+ scorecard + comparison + timeline) into the rows/lines the Qt page renders as
engineering visualisations — a scorecard banner, a metrics grid, a long-term timeline,
resolved / remaining issue tables, protected behaviours + protected knowledge, an
experiment history table and a working-window evolution table.

READ-ONLY presentation: derives display strings only. Authors nothing, recommends
nothing, exposes no Apply control. Deterministic; never raises.
"""
from __future__ import annotations

from typing import List, Sequence, Tuple

SCORECARD_COLUMNS: Tuple[str, ...] = (
    "Issues solved", "Issues remaining", "Protected kept", "Protected damaged",
    "Success rate", "Velocity", "Efficiency", "Confidence",
)
ISSUE_COLUMNS: Tuple[str, ...] = (
    "Issue", "Corner", "Phase", "State", "Seen", "Sessions",
    "Resolved×", "Regressed×", "Recurring",
)
TIMELINE_COLUMNS: Tuple[str, ...] = ("Date", "Event", "Experiment", "Status", "Detail")
EXPERIMENT_COLUMNS: Tuple[str, ...] = (
    "Date", "Experiment", "Changes", "Outcome", "Confidence", "Session",
)
WINDOW_COLUMNS: Tuple[str, ...] = (
    "Field", "Min", "Max", "Confidence", "Converged", "Snapshots",
)
KNOWLEDGE_COLUMNS: Tuple[str, ...] = (
    "Rule", "Field", "Direction", "Value", "Confidence", "Reinforced",
)

_TREND_LABEL = {
    "improving": "Improving ▲", "worsening": "Worsening ▼", "stable": "Stable →",
    "insufficient": "Too few sessions",
}
_BAND_LABEL = {
    "strong": "Strong — solving more than breaking", "progressing": "Progressing",
    "stalled": "Stalled — little net progress",
    "regressing": "Regressing — attention needed",
    "insufficient": "Building picture — too few conclusive reviews",
}
_STATE_LABEL = {
    "resolved": "Resolved", "unchanged": "Unchanged", "worsened": "Worsened",
    "improved_but_present": "Improved (present)", "new": "New",
    "good_behaviour_damaged": "Protected damaged", "not_observed": "Not observed",
    "confirmed_good": "Confirmed good",
}
_CONSTRAINT_LABEL = {
    "never_move_direction": "Never move", "never_below": "Never below",
    "never_above": "Never above", "preferred_range": "Preferred range",
    "known_unstable": "Known unstable", "protected_behaviour": "Protected behaviour",
}
_EVENT_LABEL = {
    "session": "Session", "experiment": "Experiment", "improvement": "Improvement",
    "regression": "Regression", "resolution": "Resolved",
    "protected_kept": "Protected kept", "protected_damaged": "Protected damaged",
    "inconclusive": "Inconclusive",
}


def _label(mapping, key) -> str:
    return mapping.get(str(key or ""), str(key or "").replace("_", " ").title())


def is_empty(result) -> bool:
    if not isinstance(result, dict) or not result.get("ok"):
        return True
    return int(result.get("record_count") or 0) <= 0


def context_label(result) -> str:
    hist = (result or {}).get("history") or {}
    ctx = hist.get("context") or {}
    return str(ctx.get("label") or "unknown context")


def _fmt(v) -> str:
    if v is None:
        return "—"
    if isinstance(v, float):
        return f"{v:g}"
    return str(v)


def scorecard_band_label(result) -> str:
    band = ((result or {}).get("scorecard") or {}).get("band", "insufficient")
    return _label(_BAND_LABEL, band)


def scorecard_row(result) -> List[Tuple[str, str]]:
    s = (result or {}).get("scorecard") or {}
    return [
        ("Issues solved", _fmt(s.get("issues_solved"))),
        ("Issues remaining", _fmt(s.get("issues_remaining"))),
        ("Protected kept", _fmt(s.get("protected_retained"))),
        ("Protected damaged", _fmt(s.get("protected_damaged"))),
        ("Experiment success rate", _pct(s.get("experiment_success_rate"))),
        ("Development velocity", _fmt(s.get("development_velocity"))),
        ("Experiment efficiency", _fmt(s.get("experiment_efficiency"))),
        ("Confidence trend", _label(_TREND_LABEL, s.get("engineering_confidence"))),
    ]


def _pct(v) -> str:
    try:
        return f"{float(v) * 100:.0f}%"
    except (TypeError, ValueError):
        return "—"


def metrics_rows(result) -> List[Tuple[str, str]]:
    m = (result or {}).get("metrics") or {}
    return [
        ("Reviews", _fmt(m.get("review_count"))),
        ("Sessions", _fmt(m.get("session_count"))),
        ("Conclusive reviews", _fmt(m.get("conclusive_reviews"))),
        ("Experiment success rate", _pct(m.get("experiment_success_rate"))),
        ("Issue resolution rate", _pct(m.get("issue_resolution_rate"))),
        ("Recurring issues reduced", _fmt(m.get("recurring_issues_reduced"))),
        ("Working-window convergence", _pct(m.get("working_window_convergence"))),
        ("Brake consistency", _label(_TREND_LABEL, m.get("brake_consistency_trend"))),
        ("Corner-entry stability", _label(_TREND_LABEL, m.get("entry_stability_trend"))),
        ("Exit traction", _label(_TREND_LABEL, m.get("exit_traction_trend"))),
        ("Driver consistency", _label(_TREND_LABEL, m.get("driver_consistency_trend"))),
        ("Engineering confidence", _label(_TREND_LABEL, m.get("engineering_confidence_trend"))),
    ]


def _issue_row(i: dict) -> Tuple[str, ...]:
    return (
        str(i.get("issue_type") or "—"), str(i.get("corner") or "—"),
        str(i.get("phase") or "—"), _label(_STATE_LABEL, i.get("latest_state")),
        _fmt(i.get("times_observed")), _fmt(i.get("sessions_seen")),
        _fmt(i.get("times_resolved")), _fmt(i.get("times_regressed")),
        ("yes" if i.get("recurring") else "no"),
    )


def resolved_issue_rows(result) -> List[Tuple[str, ...]]:
    issues = ((result or {}).get("memory") or {}).get("issues") or []
    res = [i for i in issues if i.get("currently_resolved")]
    return [_issue_row(i) for i in sorted(res, key=lambda i: i.get("issue_key", ""))]


def remaining_issue_rows(result) -> List[Tuple[str, ...]]:
    issues = ((result or {}).get("memory") or {}).get("issues") or []
    rem = [i for i in issues if not i.get("currently_resolved")]
    return [_issue_row(i) for i in sorted(rem, key=lambda i: i.get("issue_key", ""))]


def protected_behaviour_rows(result) -> List[Tuple[str, str]]:
    prot = ((result or {}).get("memory") or {}).get("protected_behaviours") or []
    return [(str(p.get("behaviour") or "—"), str(p.get("verdict") or "—"))
            for p in prot]


def protected_knowledge_rows(result) -> List[Tuple[str, ...]]:
    know = ((result or {}).get("memory") or {}).get("protected_knowledge") or []
    return [(_label(_CONSTRAINT_LABEL, k.get("kind")), str(k.get("field") or "—"),
             str(k.get("direction") or "—"), str(k.get("value") or "—"),
             str(k.get("confidence") or "—"), _fmt(k.get("times_reinforced")))
            for k in know]


def timeline_rows(result) -> List[Tuple[str, ...]]:
    out = []
    for e in (result or {}).get("timeline") or []:
        out.append((
            str(e.get("session_date") or e.get("recorded_at") or "—"),
            _label(_EVENT_LABEL, e.get("kind")),
            str(e.get("experiment_id") or "—"),
            str(e.get("outcome_status") or "—"),
            str(e.get("detail") or "—"),
        ))
    return out


def experiment_history_rows(result) -> List[Tuple[str, ...]]:
    hist = (result or {}).get("history") or {}
    out = []
    for rec in hist.get("records") or []:
        changes = ", ".join(c.get("field", "") for c in rec.get("changes") or []) or "—"
        out.append((
            str(rec.get("session_date") or rec.get("recorded_at") or "—"),
            str(rec.get("experiment_id") or "—"), changes,
            str(rec.get("outcome_status") or "—"),
            str(rec.get("confidence_level") or "—"),
            str(rec.get("test_session_id") or "—"),
        ))
    return out


def window_evolution_rows(result) -> List[Tuple[str, ...]]:
    windows = ((result or {}).get("memory") or {}).get("window_evolution") or []
    out = []
    for w in windows:
        out.append((
            str(w.get("field") or "—"), _fmt(w.get("latest_min")),
            _fmt(w.get("latest_max")), str(w.get("latest_confidence") or "—"),
            ("yes" if w.get("converged") else "no"),
            _fmt(len(w.get("snapshots") or [])),
        ))
    return out


def comparison_rows(result) -> List[Tuple[str, str]]:
    c = (result or {}).get("comparison")
    if not c:
        return []
    return [
        ("Verdict", str(c.get("verdict") or "—")),
        ("Compared", f"{c.get('earlier_session_id') or '—'} → {c.get('later_session_id') or '—'}"),
        ("Issues resolved Δ", _signed(c.get("issues_resolved_delta"))),
        ("Regressions Δ", _signed(c.get("regressions_delta"))),
        ("Improvements Δ", _signed(c.get("improvements_delta"))),
        ("Confidence Δ", _signed(c.get("confidence_delta"))),
        ("Protected damaged Δ", _signed(c.get("protected_damaged_delta"))),
    ]


def _signed(v) -> str:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return "—"
    if f == int(f):
        f = int(f)
    return f"+{f}" if (isinstance(f, int) and f > 0) or (isinstance(f, float) and f > 0) else str(f)
