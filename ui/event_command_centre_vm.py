"""Pure view-model for the Event Command Centre Home (Qt-free, Program 2, Phase 51).

Turns the read-only Command Centre view dict (from ``command_centre_to_dict``) into a prominent single
next-action banner, attention items, per-dimension readiness, cumulative-progress card, preparation
timeline nodes, quick-action navigation targets and (when several cycles exist) a candidate selector.
Each item carries a text tag AND a tone (meaning never colour alone). Display strings only; never raises.

Design (from the /ui-ux-pro-max gate): Real-Time / Operations IA — status hero + ONE primary action +
key metrics + timeline + navigation; a loading state is shown while the off-thread build runs (never a
frozen/blank panel). No setup values.
"""
from __future__ import annotations

from typing import List


def build(result=None) -> dict:
    return result if isinstance(result, dict) else {}


def is_loading(result) -> bool:
    return bool(build(result).get("loading"))


def is_empty(result) -> bool:
    r = build(result)
    return not r.get("ok")


_READINESS_TONE = {"missing": "warn", "developing": "info", "adequate": "success", "strong": "success",
                   "unknown": "neutral", "not_applicable": "neutral"}
_TIMELINE_TONE = {"done": "success", "current": "info", "upcoming": "neutral", "skipped": "neutral"}
_ACTION_TONE_DEFAULT = "info"


def header_text(result) -> str:
    r = build(result)
    if is_loading(result):
        return "Loading command centre…"
    if is_empty(result):
        return ("No active NGR event. Create or import an event to begin a preparation cycle. Read-only "
                "and offline; nothing is applied, bound, locked or finalised automatically. No setup values.")
    ev = r.get("event") or {}
    na = r.get("next_action") or {}
    parts = []
    name = ev.get("event_name") or "NGR Event"
    parts.append(name if not ev.get("series") else f"{name} — {ev.get('series')} {ev.get('round') or ''}".strip())
    d = r.get("days_until_race")
    if d is not None:
        parts.append(f"{d} day(s) to race.")
    if na.get("headline"):
        parts.append(f"NEXT: {na.get('headline')}.")
    return "  ".join(parts)


def banner_tone(result) -> str:
    if is_loading(result) or is_empty(result):
        return "advisory"
    return (build(result).get("next_action") or {}).get("tone") or _ACTION_TONE_DEFAULT


def next_action_card(result) -> dict:
    r = build(result)
    na = r.get("next_action") or {}
    if not na:
        return {}
    return {"title": "Primary Action", "status_tag": str(na.get("category") or "").replace("_", " ").upper(),
            "tone": na.get("tone") or _ACTION_TONE_DEFAULT,
            "lines": [na.get("headline") or "-", na.get("detail") or "",
                      f"Go to: {na.get('target_surface') or '-'}"]}


def attention_cards(result) -> List[dict]:
    r = build(result)
    cards: List[dict] = []
    for a in (r.get("attention") or []):
        cards.append({"title": str(a.get("kind") or "attention").replace("_", " ").title(),
                      "status_tag": "ATTENTION", "tone": a.get("tone") or "warn",
                      "lines": [a.get("message") or "-"]})
    return cards


def readiness_rows(result) -> List[dict]:
    r = build(result)
    rows: List[dict] = []
    for row in (r.get("readiness") or []):
        try:
            name, level, note = row[0], row[1], row[2]
        except (IndexError, TypeError, KeyError):
            continue
        rows.append({"name": str(name).replace("_", " ").title(), "level": str(level).upper(),
                     "note": note, "tone": _READINESS_TONE.get(str(level), "neutral")})
    return rows


def progress_card(result) -> dict:
    r = build(result)
    p = r.get("progress") or {}
    return {"title": "Cumulative Learning", "status_tag": "PROGRESS", "tone": "info", "lines": [
        f"Valid laps: {p.get('valid_laps', 0)}   Practice sessions: {p.get('practice_sessions', 0)}.",
        f"Experiments: {p.get('setup_experiments', 0)}   Coaching runs: {p.get('coaching_runs', 0)}.",
        f"Tyre samples: {p.get('tyre_samples', 0)}   Fuel samples: {p.get('fuel_samples', 0)}   "
        f"Race sims: {p.get('race_simulations', 0)}.",
        f"Race setup: {str(p.get('setup_confidence') or '-').replace('_', ' ').upper()}   "
        f"Strategy: {str(p.get('strategy_maturity') or '-').replace('_', ' ').upper()}.",
    ] + [f"Recent: {x}" for x in (r.get("recent_learning") or [])]}


def timeline_nodes(result) -> List[dict]:
    r = build(result)
    nodes: List[dict] = []
    for m in (r.get("timeline") or []):
        state = str(m.get("state") or "upcoming")
        nodes.append({"label": str(m.get("name") or "-"), "date": str(m.get("date") or ""),
                      "tag": state.upper(), "tone": _TIMELINE_TONE.get(state, "neutral")})
    return nodes


def quick_actions(result) -> List[dict]:
    return [{"label": q.get("label"), "target": q.get("target_surface")}
            for q in (build(result).get("quick_actions") or [])]


def candidate_rows(result) -> List[dict]:
    """Populated only when explicit selection is required (multiple active cycles)."""
    r = build(result)
    if str(r.get("resolution_state") or "") not in ("event_requires_selection", "multiple_active_events"):
        return []
    rows: List[dict] = []
    for c in (r.get("candidates") or []):
        if str(c.get("explicit_state") or "").lower() in ("complete", "abandoned"):
            continue
        rows.append({"cycle_id": c.get("cycle_id"),
                     "label": f"{c.get('series') or ''} {c.get('round') or ''} — {c.get('event_name') or ''}".strip(" —"),
                     "state": str(c.get("explicit_state") or "active").upper(),
                     "race_date": c.get("official_race_date") or ""})
    return rows
