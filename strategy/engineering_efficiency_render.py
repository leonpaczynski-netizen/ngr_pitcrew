"""Deterministic renderer for the Engineering Efficiency advisory (Program 2, Phase 19).

Renders the read-only "Engineering Efficiency" view as structured sections: the context /
totals summary, one card per campaign (age, evidence saturation with its visible reasons,
cost of knowledge, remaining information gain) and the session-budget fit. It renders STRINGS
only, shows NO Apply / freeze / complete / execute control wording, and never implies a
campaign was completed, frozen or a setup applied. Pure; deterministic; never raises.

Value is reused verbatim from Phase 17; saturation from Phase 19's evidence model; cost from
Phase 19's cost model. This module ranks, decides and mutates nothing.
"""
from __future__ import annotations

from typing import List, Tuple


def _t(v) -> str:
    return str(v if v is not None else "").replace("_", " ").strip()


def _n(v, nd=2) -> str:
    try:
        f = float(v)
        return str(int(f)) if f == int(f) else f"{round(f, nd)}"
    except (TypeError, ValueError):
        return "?"


def render_efficiency_sections(efficiency) -> List[Tuple[str, List[str]]]:
    e = efficiency if isinstance(efficiency, dict) else {}
    out: List[Tuple[str, List[str]]] = []

    ctx = e.get("context_summary") or {}
    tot = e.get("totals") or {}
    out.append(("Engineering efficiency summary", [
        f"Context: {ctx.get('car')} / {ctx.get('track')} / {ctx.get('layout')} / "
        f"{_t(ctx.get('discipline'))}.",
        f"Campaigns: {tot.get('campaigns')}   Saturated / over-tested: "
        f"{tot.get('saturated_campaigns')}   Archived: {tot.get('archived_campaigns')}.",
        f"Estimated remaining effort across campaigns: "
        f"{_n(tot.get('estimated_remaining_laps'))} laps, "
        f"{_n(tot.get('estimated_remaining_tyre_sets'), 3)} tyre set(s), "
        f"{_n(tot.get('estimated_remaining_time_minutes'))} min.",
    ]))

    for c in e.get("campaigns") or []:
        sat = c.get("saturation") or {}
        sig = sat.get("signals") or {}
        lines = [
            f"Objective: {c.get('objective') or '-'}",
            f"Status: {_t(c.get('status'))}   Age: {c.get('age_label')}"
            + (f" (first seen {c.get('first_seen')})" if c.get("first_seen") else "")
            + ("   [archived]" if c.get("archived") else ""),
            f"Evidence saturation: {_t(sat.get('status'))}   "
            f"Remaining information gain: {_t(c.get('remaining_information_gain'))}.",
        ]
        for r in sat.get("reasons") or []:
            lines.append(f"  - {r}")
        lines.append(
            f"Signals: {sig.get('confirmations')} confirmed, {sig.get('regressions')} "
            f"regressed, {sig.get('no_change')} no-change; "
            f"{sig.get('remaining_untested_experiments')} untested, "
            f"{sig.get('remaining_discriminating_experiments')} discriminating remain.")
        lines.append(
            f"Cost of knowledge (estimated): {_n(c.get('estimated_remaining_laps'))} laps, "
            f"{_n(c.get('estimated_remaining_tyre_sets'), 3)} tyre set(s), "
            f"{_n(c.get('estimated_remaining_time_minutes'))} min of remaining testing.")
        lines.extend(_experiment_cost_lines(c.get("experiment_costs") or []))
        if c.get("notes"):
            lines.append(f"Notebook: {c.get('notes')}")
        out.append((f"Campaign: {c.get('objective') or c.get('campaign_id')}", lines))

    out.append(("Session budget fit (advisory)", _budget_lines(e.get("budget") or {})))
    out.append(("Safety", [str(e.get("safety_statement") or "")]))
    return out


def _experiment_cost_lines(costs) -> List[str]:
    testable = [c for c in costs if c.get("testable")]
    if not testable:
        return ["  No still-testable experiment remains for this campaign."]
    lines = ["  Per-experiment cost (value reused from Phase-17 rank; not recomputed):"]
    for c in testable:
        lines.append(
            f"    - {_t(c.get('field'))}: {_n(c.get('laps'))} laps "
            f"({c.get('ab_structure')}), {_n(c.get('time_minutes'))} min, "
            f"{_n(c.get('tyre_sets'), 3)} tyre set(s); value {_n(c.get('engineering_value'), 3)}, "
            f"value/lap {_n(c.get('value_per_lap'), 3)}, "
            f"info-gain/tyre-set {_n(c.get('info_gain_per_tyre_set'), 3)}.")
    return lines


def _budget_lines(budget) -> List[str]:
    if not budget:
        return ["No budget context supplied."]
    if not budget.get("budget_known"):
        return ["Session budget unknown - no budget fit; supply session time / tyres / fuel "
                "to see which experiments fit. Nothing is scheduled or executed."]
    rec = budget.get("recommended") or []
    dfr = budget.get("deferred") or []
    lines = [
        f"Session budget: {_n(budget.get('session_time_minutes'))} min, "
        f"{_n(budget.get('tyre_sets_available'), 3)} tyre set(s), "
        f"{_n(budget.get('fuel_laps_available'))} fuel lap(s).",
        f"Fits this session (Phase-17 rank order, greedy fit - no optimisation): "
        f"{len(rec)} experiment(s), using {_n(budget.get('used_minutes'))} min / "
        f"{_n(budget.get('used_tyre_sets'), 3)} tyre set(s).",
    ]
    for r in rec:
        lines.append(f"  - fits: {_t(r.get('field'))} ({_n(r.get('laps'))} laps)")
    for d in dfr:
        lines.append(f"  - deferred (does not fit): {_t(d.get('field'))} "
                     f"({_n(d.get('laps'))} laps)")
    lines.append("Advisory only - which experiments FIT, not what to do. Nothing scheduled.")
    return lines


def render_efficiency_text(efficiency) -> str:
    out: List[str] = []
    for title, lines in render_efficiency_sections(efficiency):
        out.append(title)
        out.extend(f"  {ln}" for ln in lines if str(ln).strip())
        out.append("")
    return "\n".join(out).rstrip() + "\n"
