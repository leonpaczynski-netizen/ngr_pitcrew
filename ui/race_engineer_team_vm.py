"""Pure view-model for the Race-Engineer Team Brief section (Qt-free, Program 2, Phase 38).

Turns the read-only ``SessionDB.build_race_engineer_team_brief`` result into a structured banner + a
set of role-scoped cards, each carrying a semantic *tone* AND an explicit text *status tag* so meaning
is never carried by colour alone (NGR accessibility rule). Display strings only; never raises; no setup
values.
"""
from __future__ import annotations

from typing import List, Tuple


def build(result=None) -> dict:
    return result if isinstance(result, dict) else {}


def _brief(result) -> dict:
    r = build(result)
    v = r.get("brief")
    return v if isinstance(v, dict) else {}


def is_empty(result) -> bool:
    r = build(result)
    b = _brief(result)
    if not r.get("ok") or not b:
        return True
    return not (b.get("ordered_development_plan") or b.get("chief_engineer"))


def completeness_label(result) -> str:
    return str(_brief(result).get("completeness") or "").replace("_", " ").upper() or "-"


def _rollback_needed(b) -> bool:
    return bool((b.get("setup_engineer") or {}).get("rollback_plan", {}).get("needed"))


def status_summary(result) -> Tuple[str, str]:
    """Return (status_tag_text, tone) for the OVERALL brief. Text carries the meaning; tone is a
    secondary cue (colour is never the only signal)."""
    b = _brief(result)
    if not b:
        return ("AWAITING EVIDENCE", "advisory")
    if _rollback_needed(b):
        return ("ROLLBACK NEEDED", "warn")
    comp = str(b.get("completeness") or "")
    if comp in ("insufficient", "partial"):
        return ("CONTEXT INCOMPLETE", "warn")
    if b.get("empty_state"):
        return ("COLLECT BASELINE", "advisory")
    if b.get("contradictions"):
        return ("CONFLICTS RESOLVED", "info")
    return ("ON PLAN", "info")


def next_action(result) -> str:
    plan = _brief(result).get("ordered_development_plan") or []
    if not plan:
        return ""
    a = plan[0]
    return f"{a.get('step')}. {a.get('action')}"


def header_text(result) -> str:
    b = _brief(result)
    if not b:
        return ("No race-engineer brief yet. Read-only, advisory-only - the Engineering Brain "
                "coordinates the current best-PROVEN setup, working windows, driver progression and "
                "the next controlled step. It is not a certification, not an experiment, not a setup "
                "and not permission to Apply. No setup values.")
    ce = b.get("chief_engineer") or {}
    tag, _tone = status_summary(result)
    parts = [f"[{tag}]  Context readiness {completeness_label(result)}.",
             f"{len(b.get('ordered_development_plan') or [])} planned step(s)."]
    if b.get("empty_state"):
        parts.append(b.get("empty_state"))
    else:
        parts.append("Highest priority: " + str(ce.get("highest_priority_problem") or "-"))
    return " ".join(parts)


def banner_tone(result) -> str:
    return status_summary(result)[1]


# per-section (title -> (status tag text, tone)) so each role card is scannable on its own and its
# severity is stated in words, not colour alone.
def _card_meta(result, section_title: str) -> Tuple[str, str]:
    b = _brief(result)
    t = section_title.lower()
    if t.startswith("integrated"):
        return status_summary(result)
    if "chief" in t:
        return status_summary(result)[0], status_summary(result)[1]
    if "setup engineer" in t:
        return ("ROLLBACK", "warn") if _rollback_needed(b) else ("PROVEN, NOT FINAL", "info")
    if "performance" in t:
        return ("DATA", "neutral")
    if "driver coach" in t:
        prios = (b.get("driver_coach") or {}).get("priorities") or []
        return ("COACH", "info") if prios else ("NO COACHING YET", "neutral")
    if "strategy" in t:
        return ("STRATEGY", "info")
    if "contradiction" in t:
        return ("RESOLVED", "warn") if b.get("contradictions") else ("NO CONFLICTS", "success")
    if "coherent development plan" in t:
        return ("PLAN", "info")
    if "advisory" in t:
        return ("READ-ONLY", "advisory")
    return ("", "neutral")


def brief_cards(result) -> List[dict]:
    """One card per rendered role/section. Each card carries a tone + an explicit text status tag."""
    from strategy.race_engineer_team_brief_render import render_brief_sections
    b = _brief(result)
    if not b:
        return []
    cards: List[dict] = []
    for title, lines in render_brief_sections(b):
        tag, tone = _card_meta(result, title)
        cards.append({"title": title, "status_tag": tag, "tone": tone,
                      "lines": [str(ln) for ln in lines if str(ln).strip()]})
    return cards
