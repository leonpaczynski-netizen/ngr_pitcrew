"""Pure view-model for the Event Preparation Cycle spine (Qt-free, Program 2, Phase 48-50 UI).

Turns the read-only ``SessionDB.build_event_preparation_report`` dict into a next-action banner, a
horizontal preparation TIMELINE (actual activities/dates, never forced 'Week 1/2/3'), and a small set
of status cards (cumulative progress, per-discipline setup convergence, strategy maturity, readiness).
Each card/timeline node carries a text status tag AND a tone (meaning is never colour alone). Display
strings only; never raises; no setup values.

Design (from the /ui-ux-pro-max gate): Real-Time / Operations IA — status/metrics first, data-dense but
scannable; dark, high-contrast status tones (green/amber/red) reused from the NGR theme; tabular
numerals for counts and the countdown; read-only advisory surfaces use the advisory tone so they never
read as an actionable Apply.
"""
from __future__ import annotations

from typing import List


def build(result=None) -> dict:
    return result if isinstance(result, dict) else {}


def is_empty(result) -> bool:
    r = build(result)
    return not r.get("ok") or not r.get("cycle")


_READINESS_TONE = {
    "missing": "warn", "developing": "info", "adequate": "success", "strong": "success",
    "unknown": "neutral", "not_applicable": "neutral",
}

_TIMELINE_TONE = {
    "done": "success", "current": "info", "upcoming": "neutral", "skipped": "neutral",
}


def status_summary(result):
    r = build(result)
    cyc = r.get("cycle") or {}
    state = str(cyc.get("state") or "")
    if state == "complete":
        return ("COMPLETE", "success")
    if state in ("paused", "abandoned"):
        return (state.upper(), "warn")
    if state == "not_started":
        return ("NOT STARTED", "neutral")
    return ("ACTIVE", "info")


def header_text(result) -> str:
    r = build(result)
    if is_empty(result):
        return ("No active event preparation cycle. Read-only and advisory: it groups every Practice "
                "session for one upcoming NGR round into one cumulative engineering programme. It applies "
                "no setup, binds no session, locks nothing and finalises nothing automatically. "
                "No setup values.")
    cyc = r.get("cycle") or {}
    tag, _tone = status_summary(result)
    parts = [f"[{tag}]  {cyc.get('event_name') or 'Event'}"]
    if cyc.get("series"):
        parts.append(f"{cyc.get('series')} {cyc.get('round') or ''}".strip())
    dur = cyc.get("days_until_race")
    if dur is not None:
        parts.append(f"{dur} day(s) to race.")
    na = r.get("next_action") or {}
    if na.get("headline"):
        parts.append(f"Next: {na.get('headline')}.")
    return "  ".join(parts)


def banner_tone(result) -> str:
    if is_empty(result):
        return "advisory"
    na = build(result).get("next_action") or {}
    return na.get("tone") or status_summary(result)[1]


def timeline_nodes(result) -> List[dict]:
    """A horizontal strip of preparation milestones. Each node: {label, date, state, tag, tone}."""
    r = build(result)
    nodes: List[dict] = []
    for m in (r.get("timeline") or []):
        state = str(m.get("state") or "upcoming")
        nodes.append({
            "label": str(m.get("name") or "-"),
            "date": str(m.get("date") or ""),
            "state": state,
            "tag": state.upper(),
            "tone": _TIMELINE_TONE.get(state, "neutral"),
        })
    return nodes


def progress_cards(result) -> List[dict]:
    r = build(result)
    if is_empty(result):
        return []
    cards: List[dict] = []

    # 1 — cumulative programme progress (data-dense, tabular)
    p = r.get("progress") or {}
    prog_lines = [
        f"Valid laps: {p.get('valid_laps', 0)}.",
        f"Practice sessions: {p.get('practice_sessions', 0)}.",
        f"Setup experiments: {p.get('setup_experiments', 0)}.",
        f"Coaching runs: {p.get('coaching_runs', 0)}.",
        f"Tyre samples: {p.get('tyre_samples', 0)}   Fuel samples: {p.get('fuel_samples', 0)}.",
        f"Race simulations: {p.get('race_simulations', 0)}.",
    ]
    cards.append({"title": "Cumulative Programme", "status_tag": "PROGRESS", "tone": "info",
                  "lines": prog_lines})

    # 2 — per-discipline setup convergence (Base / Qualifying / Race stay separate)
    setup = r.get("setup") or {}
    setup_lines = []
    for disc in ("base", "qualifying", "race"):
        st = setup.get(disc)
        if st:
            setup_lines.append(f"{disc.title()}: {str(st).replace('_', ' ').upper()}.")
    if not setup_lines:
        setup_lines = ["No setup convergence evidence yet."]
    cards.append({"title": "Setup Convergence", "status_tag": "SEPARATE", "tone": "neutral",
                  "lines": setup_lines})

    # 3 — strategy maturity
    strat = r.get("strategy") or {}
    strat_lines = [f"Maturity: {str(strat.get('maturity') or '-').replace('_', ' ').upper()}."]
    for miss in (strat.get("missing") or [])[:6]:
        strat_lines.append(f"Missing: {miss}.")
    smat = str(strat.get("maturity") or "")
    stone = ("success" if smat in ("finalisation_ready", "finalised") else
             "warn" if smat in ("no_evidence", "replan_required") else "info")
    cards.append({"title": "Strategy Maturity", "status_tag": smat.replace("_", " ").upper() or "NONE",
                  "tone": stone, "lines": strat_lines})

    # 4 — readiness dimensions (tag + tone, never colour alone)
    rdy = r.get("readiness") or []
    rdy_lines = []
    worst = "success"
    for row in rdy:
        try:
            name, level, note = row[0], row[1], row[2]
        except (IndexError, TypeError, KeyError):
            continue
        rdy_lines.append(f"{str(name).replace('_', ' ').title()}: {str(level).upper()} - {note}")
        if level == "missing":
            worst = "warn"
    if not rdy_lines:
        rdy_lines = ["No readiness evidence yet."]
    cards.append({"title": "Readiness", "status_tag": "REVIEW", "tone": worst, "lines": rdy_lines})
    return cards
