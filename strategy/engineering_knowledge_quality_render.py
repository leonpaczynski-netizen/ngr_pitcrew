"""Deterministic renderer for the Engineering Knowledge Quality advisory (Program 2, Phase 20).

Renders the read-only confidence / ROI / opportunity view as structured sections: a summary,
then one card per campaign (overall confidence + component breakdown with reasons, development
ROI, and campaign opportunity). It renders STRINGS only, shows NO Apply / freeze / complete /
execute wording, and never implies a campaign was completed or a setup applied. It reflects the
Phase-20 measures verbatim - it ranks, sorts and decides nothing. Pure; deterministic; never
raises.
"""
from __future__ import annotations

from typing import List, Tuple


def _t(v) -> str:
    return str(v if v is not None else "").replace("_", " ").strip()


def _n(v, nd=3) -> str:
    if v is None:
        return "n/a"
    try:
        f = float(v)
        return str(int(f)) if f == int(f) else f"{round(f, nd)}"
    except (TypeError, ValueError):
        return "n/a"


def render_quality_sections(quality) -> List[Tuple[str, List[str]]]:
    q = quality if isinstance(quality, dict) else {}
    out: List[Tuple[str, List[str]]] = []

    ctx = q.get("context_summary") or {}
    tot = q.get("totals") or {}
    lc = tot.get("confidence_level_counts") or {}
    out.append(("Knowledge quality summary", [
        f"Context: {ctx.get('car')} / {ctx.get('track')} / {ctx.get('layout')} / "
        f"{_t(ctx.get('discipline'))}.",
        f"Campaigns: {tot.get('campaigns')}   Worthwhile of further work: "
        f"{tot.get('worthwhile_campaigns')}.",
        "Confidence: " + (", ".join(f"{_t(k)} {v}" for k, v in sorted(lc.items())) or "-") + ".",
        (f"Context prediction accuracy: {_n(tot.get('context_prediction_accuracy'))}"
         if tot.get("context_prediction_accuracy") is not None
         else "Context prediction accuracy: not yet calibrated."),
    ]))

    for c in q.get("campaigns") or []:
        conf = c.get("confidence") or {}
        roi = c.get("roi") or {}
        opp = c.get("opportunity") or {}
        lines = [
            f"Objective: {c.get('objective') or c.get('campaign_id')}   "
            f"(status: {_t(c.get('status'))})",
            f"Overall confidence: {_t(conf.get('overall_level'))} "
            f"(score {_n(conf.get('overall_score'))}).",
        ]
        for r in conf.get("reasons") or []:
            lines.append(f"  - {r}")
        for cap in conf.get("caps_applied") or []:
            lines.append(f"  - cap: {cap}")
        lines.append("  Confidence breakdown:")
        for comp in conf.get("components") or []:
            inc = "" if comp.get("included_in_overall") else " [informational]"
            lines.append(f"    - {_t(comp.get('name'))}: {_t(comp.get('label'))} "
                         f"(score {_n(comp.get('score'))}){inc} - {comp.get('reason')} "
                         f"[{comp.get('source')}; {comp.get('calculation')}]")
        lines.extend(_roi_lines(roi))
        lines.append(f"Opportunity: {_t(opp.get('opportunity'))} "
                     f"({'worth further work' if opp.get('worthwhile') else 'no further work'}).")
        lines.append(f"  - {opp.get('reason')}")
        if opp.get("recommended_focus") and opp.get("recommended_focus") != "none":
            lines.append(f"  - suggested test focus: {_t(opp.get('recommended_focus'))}")
        out.append((f"Campaign: {c.get('objective') or c.get('campaign_id')}", lines))

    out.append(("Safety", [str(q.get("safety_statement") or "")]))
    return out


def _roi_lines(roi) -> List[str]:
    if not roi:
        return []
    cost = roi.get("cost_to_close_gap") or {}
    lines = [
        f"Development ROI: expected information gain {_n(roi.get('expected_information_gain'))}, "
        f"expected confidence gain {_n(roi.get('expected_confidence_gain'))}, "
        f"knowledge gap {_n(roi.get('knowledge_gap'))}.",
        f"  Estimated session value {_n(roi.get('estimated_session_value'))}; "
        f"remaining risk {_t(roi.get('remaining_risk'))}.",
        f"  Cost to close the gap: {_n(cost.get('laps'))} laps, "
        f"{_n(cost.get('tyre_sets'))} tyre set(s), {_n(cost.get('time_minutes'))} min "
        f"[{cost.get('source')}].",
        f"  {roi.get('engineering_priority_reason')}",
    ]
    return lines


def render_quality_text(quality) -> str:
    out: List[str] = []
    for title, lines in render_quality_sections(quality):
        out.append(title)
        out.extend(f"  {ln}" for ln in lines if str(ln).strip())
        out.append("")
    return "\n".join(out).rstrip() + "\n"
