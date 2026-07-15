"""Deterministic setup tuning-compliance validator.

Given a setup-recommendation response (JSON or text) and the event's tuning
restrictions, returns the category codes that would be violated if the
recommendation were applied to a locked area. Pure string analysis; no AI,
network, or Qt dependencies.

Extracted from the former ``strategy.ai_planner.validate_ai_setup_response``
during the determinism rebuild (Sprint 1). Behaviour is unchanged; only the
name and home module changed (the check is generic — it applies to the
deterministic rule-engine output, not to any AI response).
"""
from __future__ import annotations

_LOCKED_CAT_KEYWORDS: dict[str, list[str]] = {
    "brake_balance": ["brake bias", "brake balance"],
    "suspension":    ["ride height", "spring rate", "spring stiffness", "springs", "damper",
                      "anti-roll", "camber", "toe-in", "toe-out", "toe setting", "arb"],
    "differential":  ["lsd", "differential", "limited slip"],
    "aero":          ["downforce", "front wing", "rear wing", "front aero", "rear aero",
                      "aero balance"],
    "transmission":  ["gear ratio", "final drive", "gearbox"],
    "power":         ["ecu output", "power restrictor", "power restriction"],
    "ballast":       ["ballast"],
    "nitrous":       ["nitrous"],
}

_SETUP_ACTION_VERBS: list[str] = [
    "increase", "decrease", "raise", "lower", "soften", "stiffen",
    "adjust", "try", "set to", "change", "modify", "reduce", "add",
    "recommend", "suggest", "consider",
]


def validate_setup_tuning_compliance(
    response: str,
    tuning_locked: bool,
    allowed_tuning: list[str] | None,
) -> list[str]:
    """Return violated category codes when a recommendation touches locked areas.

    Detects a violation when a locked-category keyword appears within 200
    characters of a setup-change action verb. Returns [] when no tuning
    restrictions are active or no violations are found.
    """
    if not tuning_locked and not allowed_tuning:
        return []

    text = response.lower()

    if tuning_locked:
        locked_cats = list(_LOCKED_CAT_KEYWORDS.keys())
    else:
        locked_cats = [c for c in _LOCKED_CAT_KEYWORDS if c not in (allowed_tuning or [])]

    violated: list[str] = []
    for cat in locked_cats:
        cat_violated = False
        for kw in _LOCKED_CAT_KEYWORDS.get(cat, []):
            pos = text.find(kw)
            while pos != -1 and not cat_violated:
                window = text[max(0, pos - 200): pos + len(kw) + 200]
                if any(v in window for v in _SETUP_ACTION_VERBS):
                    violated.append(cat)
                    cat_violated = True
                pos = text.find(kw, pos + 1)
    return violated
