"""Group 49 — Race Strategy Brain Phase 3: session-aware explanation builder.

Extends the Group 48 explanation with an "Evidence source" section that tells the
driver, per input, whether the number is **SessionDB measured**, an **event
setting**, a **default assumption**, or **missing**. So a strategy built from real
practice laps reads differently from one running on defaults — and the driver can
see exactly which.

Pure: no PyQt / DB / AI / I/O; never raises. Renders text only; authors no setup
values and cannot reach the Apply gate.
"""
from __future__ import annotations

from strategy.race_strategy_evidence import RaceStrategyEvidence
from strategy.race_strategy_explain import StrategyExplanation, build_explanation
from strategy.race_strategy_scorer import StrategyRecommendation


# Human labels for the provenance keys produced by
# race_strategy_from_session._build_source_summary().
_FIELD_LABELS: dict[str, str] = {
    "race_pace": "Race pace",
    "fuel_use": "Fuel use",
    "tyre_degradation": "Tyre degradation",
    "compound_pace": "Compound pace",
    "refuel_rate": "Refuel rate",
    "pit_loss": "Pit loss",
    "weather": "Weather",
}

# Stable display order.
_FIELD_ORDER = (
    "race_pace", "fuel_use", "tyre_degradation",
    "compound_pace", "refuel_rate", "pit_loss", "weather",
)


def evidence_source_lines(source_summary: dict) -> list[str]:
    """Turn a from-session ``source_summary`` into driver-readable source lines.

    Returns e.g. ["Race pace: SessionDB measured (7 clean laps)",
    "Tyre degradation: missing, confidence reduced", ...]. Safe on any dict shape.
    """
    lines: list[str] = []
    fields = {}
    try:
        fields = dict(source_summary.get("fields", {}) or {})
    except Exception:
        fields = {}

    for key in _FIELD_ORDER:
        if key not in fields:
            continue
        label = _FIELD_LABELS.get(key, key.replace("_", " ").title())
        provenance = str(fields.get(key, "") or "")
        if provenance == "missing":
            lines.append(f"{label}: missing, confidence reduced")
        else:
            lines.append(f"{label}: {provenance}")
    return lines


def build_session_explanation(
    recommendation: StrategyRecommendation,
    evidence: RaceStrategyEvidence,
    source_summary: dict,
) -> StrategyExplanation:
    """Build a Group 48 explanation and attach SessionDB provenance lines.

    Reuses :func:`strategy.race_strategy_explain.build_explanation` unchanged, then
    populates the additive ``evidence_sources`` field so the rendered text opens
    with an honest "Evidence source" section.
    """
    exp = build_explanation(recommendation, evidence)
    exp.evidence_sources = evidence_source_lines(source_summary or {})
    return exp
