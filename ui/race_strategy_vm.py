"""Group 50 — Race Strategy Brain Phase 4: driver-facing Race Plan view model.

WHY IT EXISTS
  Groups 48/49 built a deterministic strategy engine that returns rich, honest
  result objects (`SessionStrategyResult`). This module turns those objects into
  DISPLAY-READY data for the Strategy Builder's Race Plan surface — recommended
  plan, confidence, total race time, stint plan, candidate comparison, evidence
  sources, missing evidence, risk flags, safety notes, and a driver explanation.

WHAT THIS MODULE IS NOT
  • It is NOT PyQt. There is **no Qt import here** — this is a pure, unit-testable
    presentation layer. The Qt tab is a thin renderer over these functions.
  • It authors no setup values, has no Apply/approve capability, reads no API key,
    and writes nothing. It only formats an already-computed strategy result.
  • It invents nothing: missing evidence stays visible; it never claims certainty.

PURITY
  Deterministic and offline. Never raises — every builder wraps its internals and
  degrades to a safe, honest "insufficient evidence" view model.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

# Pure strategy-layer imports only (no Qt).
from strategy.race_strategy_explain import plan_name
from strategy.race_strategy_evidence import StrategyConfidence


# ---------------------------------------------------------------------------
# Display constants
# ---------------------------------------------------------------------------

_COMPOUND_NAMES = {
    "RSS": "Racing Super Soft", "RS": "Racing Soft", "RM": "Racing Medium",
    "RH": "Racing Hard", "RI": "Intermediate", "IM": "Intermediate",
    "RW": "Wet", "W": "Wet",
    "SS": "Super Soft", "S": "Soft", "M": "Medium", "H": "Hard",
    "soft": "Soft", "medium": "Medium", "hard": "Hard",
}

_FUEL_MAP_LABELS = {
    "normal": "Fuel Map 1",
    "save": "Fuel Map 1 (lean / save)",
    "push": "Fuel Map 1 (rich / push)",
}

_CONFIDENCE_LABELS = {
    StrategyConfidence.HIGH: "High",
    StrategyConfidence.MEDIUM: "Medium",
    StrategyConfidence.LOW: "Low",
    StrategyConfidence.INSUFFICIENT_EVIDENCE: "Insufficient evidence",
}


def compound_name(code: str) -> str:
    c = str(code or "")
    return _COMPOUND_NAMES.get(c, _COMPOUND_NAMES.get(c.upper(), c or "Unknown"))


def fuel_map_label(fuel_map: str) -> str:
    return _FUEL_MAP_LABELS.get(str(fuel_map or "normal"), "Fuel Map 1")


def format_race_time(seconds: float) -> str:
    """Format seconds as M:SS.s (or H:MM:SS.s past an hour). '—' when unknown."""
    try:
        total = float(seconds or 0.0)
    except (TypeError, ValueError):
        return "—"
    if total <= 0:
        return "—"
    hours = int(total // 3600)
    rem = total - hours * 3600
    minutes = int(rem // 60)
    secs = rem - minutes * 60
    if hours:
        return f"{hours}:{minutes:02d}:{secs:04.1f}"
    return f"{minutes}:{secs:04.1f}"


# ---------------------------------------------------------------------------
# View model
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RacePlanViewModel:
    """Display-ready projection of a strategy result for the Race Plan surface."""

    has_recommendation: bool
    recommended_strategy_title: str
    confidence_label: str
    confidence_reason: str
    estimated_total_time: str
    gap_to_alternatives: list[str] = field(default_factory=list)
    stint_plan_rows: list[dict] = field(default_factory=list)
    candidate_comparison_rows: list[dict] = field(default_factory=list)
    evidence_source_rows: list[dict] = field(default_factory=list)
    missing_evidence_rows: list[str] = field(default_factory=list)
    risk_flags: list[str] = field(default_factory=list)
    safety_notes: list[str] = field(default_factory=list)
    driver_explanation: str = ""
    warnings: list[str] = field(default_factory=list)
    source_note: str = ""


# ---------------------------------------------------------------------------
# Section formatters (pure, individually testable)
# ---------------------------------------------------------------------------

def format_strategy_summary(result) -> str:
    """Recommended-strategy title, e.g. 'One-stop race plan'."""
    rec = getattr(getattr(result, "recommendation", None), "recommended", None)
    if rec is None:
        exp = getattr(result, "explanation", None)
        return getattr(exp, "recommended_plan", "No recommendation — insufficient evidence")
    return plan_name(rec.candidate_id)


def format_strategy_confidence(result) -> tuple[str, str]:
    """(label, reason) for the confidence display."""
    conf = getattr(result, "confidence", StrategyConfidence.INSUFFICIENT_EVIDENCE)
    label = _CONFIDENCE_LABELS.get(conf, str(getattr(conf, "value", conf)))
    exp = getattr(result, "explanation", None)
    rec_obj = getattr(result, "recommendation", None)
    reason = ""
    if exp is not None and getattr(exp, "why", ""):
        reason = exp.why
    elif rec_obj is not None and getattr(rec_obj, "reason", ""):
        reason = rec_obj.reason
    return label, reason


def format_stint_plan(result) -> list[dict]:
    """Rows describing each stint of the recommended plan."""
    rec = getattr(getattr(result, "recommendation", None), "recommended", None)
    if rec is None:
        return []
    cand = _find_candidate(result, rec.candidate_id)
    if cand is None:
        return []
    ev = getattr(result, "evidence", None)
    lap_s = ev.representative_lap_s() if ev is not None else 0.0

    rows: list[dict] = []
    laps_per = list(getattr(cand, "estimated_laps_per_stint", []) or [])
    compounds = list(getattr(cand, "compound_plan", []) or [])
    fuel_maps = list(getattr(cand, "fuel_map_plan", []) or [])
    n = len(laps_per)
    cumulative = 0
    for i in range(n):
        laps = int(laps_per[i])
        cumulative += laps
        minutes = round(laps * lap_s / 60.0) if lap_s > 0 else 0
        comp = compounds[i] if i < len(compounds) else ""
        fmap = fuel_maps[i] if i < len(fuel_maps) else "normal"
        if i < n - 1:
            pit_note = f"pit around lap {cumulative}"
        else:
            pit_note = "finish"
        rows.append({
            "stint": i + 1,
            "compound": compound_name(comp),
            "compound_code": comp,
            "laps": laps,
            "minutes": minutes,
            "fuel_map": fuel_map_label(fmap),
            "pit_note": pit_note,
        })
    return rows


def format_candidate_comparison_rows(result) -> list[dict]:
    """One row per scored (legal) candidate, ranked by total race time."""
    rec = getattr(getattr(result, "recommendation", None), "recommended", None)
    rec_id = rec.candidate_id if rec is not None else None
    rows: list[dict] = []
    for score in getattr(result, "scored_candidates", ()) or ():
        cand = _find_candidate(result, score.candidate_id)
        pit_stops = getattr(cand, "pit_count", 0) if cand else 0
        compounds = _compound_summary(cand)
        gap = score.estimated_gap_to_best_seconds
        rows.append({
            "strategy": plan_name(score.candidate_id),
            "candidate_id": score.candidate_id,
            "pit_stops": pit_stops,
            "compounds": compounds,
            "total_time": format_race_time(score.estimated_total_time_seconds),
            "gap_to_best": "best" if gap <= 0 else f"+{gap:.1f}s",
            "pit_refuel_time": (
                f"{score.pit_time_total_seconds:.0f}s "
                f"({score.refuel_time_total_seconds:.0f}s refuel)"
            ),
            "deg_cost": f"{score.degradation_cost_seconds:.1f}s",
            "fuel_save_cost": f"{score.fuel_saving_cost_seconds:.1f}s",
            "risk": "; ".join(score.risk_flags) if score.risk_flags else "—",
            "confidence": _CONFIDENCE_LABELS.get(score.confidence, str(getattr(score.confidence, "value", ""))),
            "status": "Recommended" if score.candidate_id == rec_id else "Alternative",
        })
    return rows


def format_evidence_sources(source_summary: dict) -> list[dict]:
    """Rows describing each strategy input's provenance + a category tag.

    category ∈ {measured, derived, event, manual, default, missing}.
    """
    rows: list[dict] = []
    try:
        fields = dict((source_summary or {}).get("fields", {}) or {})
    except Exception:
        fields = {}
    for key in _EVIDENCE_ORDER:
        if key not in fields:
            continue
        detail = str(fields.get(key, "") or "")
        rows.append({
            "label": _EVIDENCE_LABELS.get(key, key.replace("_", " ").title()),
            "detail": detail if detail != "missing" else "missing",
            "category": _classify_source(detail),
        })
    return rows


def format_missing_evidence(result) -> list[str]:
    """Human-readable missing-evidence lines (always visible)."""
    out: list[str] = []
    for m in getattr(result, "missing_evidence", ()) or ():
        out.append(str(m))
    return out


def format_strategy_risks(result) -> list[str]:
    """Risk flags to surface to the driver.

    Includes the recommended plan's OWN risk flags, plus a cross-plan note when an
    aggressive (push) alternative was flagged rear-fragile and NOT recommended —
    so the driver sees why the snappier plan was left on the table. Never presents
    another plan's flags as though they were the recommended plan's own risks.
    """
    rec = getattr(getattr(result, "recommendation", None), "recommended", None)
    out: list[str] = []
    rec_id = rec.candidate_id if rec is not None else None
    if rec is not None:
        out.extend(list(getattr(rec, "risk_flags", []) or []))

    for score in getattr(result, "scored_candidates", ()) or ():
        if score.candidate_id == rec_id:
            continue
        if "push" not in str(score.candidate_id).lower():
            continue
        if any("rear" in str(f).lower() for f in (score.risk_flags or [])):
            note = "Rear traction fragile: push strategy not recommended."
            if note not in out:
                out.append(note)
    return out


def format_strategy_safety_notes(result) -> list[str]:
    return list(getattr(result, "safety_notes", ()) or ())


# ---------------------------------------------------------------------------
# Top-level view-model builder
# ---------------------------------------------------------------------------

def build_race_plan_view_model(result) -> RacePlanViewModel:
    """Convert a `SessionStrategyResult` into a `RacePlanViewModel` (never raises)."""
    try:
        has_rec = bool(getattr(getattr(result, "recommendation", None), "has_recommendation", False))
        title = format_strategy_summary(result)
        conf_label, conf_reason = format_strategy_confidence(result)

        rec = getattr(getattr(result, "recommendation", None), "recommended", None)
        total = format_race_time(rec.estimated_total_time_seconds) if rec is not None else "—"

        exp = getattr(result, "explanation", None)
        explanation = getattr(exp, "why", "") if exp is not None else ""
        if not explanation and rec is None:
            explanation = getattr(getattr(result, "recommendation", None), "reason", "")

        return RacePlanViewModel(
            has_recommendation=has_rec,
            recommended_strategy_title=title,
            confidence_label=conf_label,
            confidence_reason=conf_reason,
            estimated_total_time=total,
            gap_to_alternatives=_gap_lines(result),
            stint_plan_rows=format_stint_plan(result),
            candidate_comparison_rows=format_candidate_comparison_rows(result),
            evidence_source_rows=format_evidence_sources(getattr(result, "source_summary", {})),
            missing_evidence_rows=format_missing_evidence(result),
            risk_flags=format_strategy_risks(result),
            safety_notes=format_strategy_safety_notes(result),
            driver_explanation=explanation,
            warnings=list(getattr(result, "warnings", ()) or ()),
            source_note=_source_note(result),
        )
    except Exception:
        return RacePlanViewModel(
            has_recommendation=False,
            recommended_strategy_title="No recommendation — insufficient evidence",
            confidence_label="Insufficient evidence",
            confidence_reason="Could not build a race plan from the available data.",
            estimated_total_time="—",
            safety_notes=list(getattr(result, "safety_notes", ()) or ()),
        )


# ---------------------------------------------------------------------------
# Runners (thin: pipeline + view model) — pure, testable with a mock/:memory: db
# ---------------------------------------------------------------------------

def run_race_plan_from_session(db, **kwargs) -> RacePlanViewModel:
    """Run the session-backed pipeline and project it to a view model."""
    from strategy.race_strategy_pipeline import recommend_strategy_from_session
    result = recommend_strategy_from_session(db, **kwargs)
    return build_race_plan_view_model(result)


def run_race_plan_from_event_context(db, **kwargs) -> RacePlanViewModel:
    """Run the event-context pipeline and project it to a view model."""
    from strategy.race_strategy_pipeline import recommend_strategy_from_event_context
    result = recommend_strategy_from_event_context(db, **kwargs)
    return build_race_plan_view_model(result)


# ---------------------------------------------------------------------------
# Renderers (pure) — the Qt tab is a thin wrapper over these
# ---------------------------------------------------------------------------

CANDIDATE_TABLE_COLUMNS = [
    "Strategy", "Pit Stops", "Compounds", "Total Time", "Gap to Best",
    "Pit + Refuel", "Deg Cost", "Fuel Save", "Risk", "Confidence", "Status",
]


def candidate_table_rows(vm: RacePlanViewModel) -> list[list[str]]:
    """Rows (list of string cells) for the candidate-comparison table widget."""
    rows: list[list[str]] = []
    for r in vm.candidate_comparison_rows:
        rows.append([
            str(r.get("strategy", "")),
            str(r.get("pit_stops", "")),
            str(r.get("compounds", "")),
            str(r.get("total_time", "")),
            str(r.get("gap_to_best", "")),
            str(r.get("pit_refuel_time", "")),
            str(r.get("deg_cost", "")),
            str(r.get("fuel_save_cost", "")),
            str(r.get("risk", "")),
            str(r.get("confidence", "")),
            str(r.get("status", "")),
        ])
    return rows


def render_race_plan_html(vm: RacePlanViewModel) -> str:
    """Render the Race Plan narrative as HTML for a read-only text widget.

    Deterministic, self-contained, no external assets. Never advertises an Apply
    action and never claims certainty.
    """
    def esc(s: str) -> str:
        return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))

    parts: list[str] = []
    parts.append(f"<h2 style='color:#64B5F6; margin:2px 0;'>{esc(vm.recommended_strategy_title)}</h2>")
    parts.append(
        f"<p style='margin:2px 0;'><b>Confidence:</b> {esc(vm.confidence_label)}"
        + (f" &nbsp;|&nbsp; <b>Estimated total race time:</b> {esc(vm.estimated_total_time)}"
           if vm.estimated_total_time != '—' else "")
        + "</p>"
    )
    if vm.source_note:
        parts.append(f"<p style='color:#AAA; font-size:11px; margin:2px 0;'>{esc(vm.source_note)}</p>")

    if vm.driver_explanation:
        parts.append("<h3 style='color:#8BC34A; margin:8px 0 2px;'>Why this plan</h3>")
        parts.append(f"<p style='margin:2px 0;'>{esc(vm.driver_explanation)}</p>")

    if vm.stint_plan_rows:
        parts.append("<h3 style='color:#8BC34A; margin:8px 0 2px;'>Stint plan</h3><ul style='margin:2px 0;'>")
        for s in vm.stint_plan_rows:
            mins = f"{s['minutes']} min" if s.get("minutes") else f"{s.get('laps', 0)} laps"
            parts.append(
                f"<li>Stint {s['stint']}: {esc(s['compound'])}, {esc(mins)}, "
                f"{esc(s['fuel_map'])}, {esc(s['pit_note'])}</li>"
            )
        parts.append("</ul>")

    if vm.evidence_source_rows:
        parts.append("<h3 style='color:#8BC34A; margin:8px 0 2px;'>Evidence sources</h3><ul style='margin:2px 0;'>")
        for e in vm.evidence_source_rows:
            parts.append(f"<li>{esc(e['label'])}: {esc(e['detail'])}</li>")
        parts.append("</ul>")

    if vm.missing_evidence_rows:
        parts.append("<h3 style='color:#F5C542; margin:8px 0 2px;'>Missing evidence</h3><ul style='margin:2px 0;'>")
        for m in vm.missing_evidence_rows:
            parts.append(f"<li>{esc(m)}</li>")
        parts.append("</ul>")

    if vm.risk_flags:
        parts.append("<h3 style='color:#E8A9A3; margin:8px 0 2px;'>Risk flags</h3><ul style='margin:2px 0;'>")
        for r in vm.risk_flags:
            parts.append(f"<li>{esc(r)}</li>")
        parts.append("</ul>")

    if vm.safety_notes:
        parts.append("<h3 style='color:#888; margin:8px 0 2px;'>Safety notes</h3><ul style='margin:2px 0; color:#888; font-size:11px;'>")
        for n in vm.safety_notes:
            parts.append(f"<li>{esc(n)}</li>")
        parts.append("</ul>")

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------

_EVIDENCE_LABELS = {
    "race_pace": "Race pace",
    "fuel_use": "Fuel use",
    "tyre_degradation": "Tyre degradation",
    "compound_pace": "Compound pace",
    "refuel_rate": "Refuel rate",
    "pit_loss": "Pit loss",
    "weather": "Weather",
}
_EVIDENCE_ORDER = (
    "race_pace", "fuel_use", "tyre_degradation",
    "compound_pace", "refuel_rate", "pit_loss", "weather",
)


def _classify_source(detail: str) -> str:
    d = str(detail or "").lower()
    if not d or "missing" in d:
        return "missing"
    if "derived" in d:
        return "derived"
    if "measured" in d:
        return "measured"
    if "manual" in d:
        return "manual"
    if "default" in d or "assumed" in d:
        return "default"
    if "event" in d:
        return "event"
    return "event"


def _find_candidate(result, candidate_id: str):
    for c in getattr(result, "candidates", ()) or ():
        if getattr(c, "candidate_id", None) == candidate_id:
            return c
    return None


def _compound_summary(cand) -> str:
    if cand is None:
        return "—"
    plan = list(getattr(cand, "compound_plan", []) or [])
    if not plan:
        return "—"
    # Preserve order, drop consecutive duplicates for a compact summary.
    seq: list[str] = []
    for c in plan:
        name = compound_name(c)
        if not seq or seq[-1] != name:
            seq.append(name)
    return " → ".join(seq)


def _gap_lines(result) -> list[str]:
    rec = getattr(getattr(result, "recommendation", None), "recommended", None)
    rec_id = rec.candidate_id if rec is not None else None
    lines: list[str] = []
    seen_names: set[str] = set()
    for score in getattr(result, "scored_candidates", ()) or ():
        if score.candidate_id == rec_id:
            continue
        gap = score.estimated_gap_to_best_seconds
        if gap <= 0:
            continue
        name = plan_name(score.candidate_id)
        if name in seen_names:
            continue
        seen_names.add(name)
        lines.append(f"{name}: +{gap:.1f}s")
        if len(lines) >= 4:
            break
    return lines


def _source_note(result) -> str:
    ss = getattr(result, "source_summary", {}) or {}
    samples = getattr(result, "samples", None)
    sid = getattr(samples, "session_id", 0) if samples is not None else ss.get("session_id", 0)
    clean = getattr(samples, "clean_lap_count", 0) if samples is not None else 0
    if sid and clean:
        return f"Based on SessionDB session {sid} ({clean} clean laps)."
    return "No session data selected — strategy uses event settings only, so confidence is lower."
