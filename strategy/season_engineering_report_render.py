"""Deterministic renderer for the Season Engineering Report (Program 2, Phase 21).

Renders the Engineering Director's read-only season view as structured sections: the season
overview (with each metric's reason/source/calculation), the cross-campaign relationship map
(every edge explained + its authority), and the per-campaign knowledge map. It renders STRINGS
only, shows NO Apply / freeze / complete / execute / schedule wording, and never implies work
was scheduled or a campaign completed. Pure; deterministic; never raises.
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
        return str(v)


def render_report_sections(report) -> List[Tuple[str, List[str]]]:
    r = report if isinstance(report, dict) else {}
    out: List[Tuple[str, List[str]]] = []

    ctx = r.get("context_summary") or {}
    dev = r.get("development") or {}
    metrics = dev.get("metrics") or {}
    lines = [f"Context: {ctx.get('car')} / {ctx.get('track')} / {ctx.get('layout')} / "
             f"{_t(ctx.get('discipline'))}.",
             dev.get("engineering_summary") or "No engineering campaigns this season yet."]
    for name, m in metrics.items():
        if not isinstance(m, dict):
            continue
        val = m.get("value")
        val_s = _render_metric_value(val)
        lines.append(f"  - {_t(name)}: {val_s}  [{m.get('source')}; {m.get('calculation')}]")
    out.append(("Season overview", lines))

    rel = r.get("relationships") or {}
    edges = rel.get("edges") or []
    rlines: List[str] = [f"Relationships found: {len(edges)}. "
                         f"Counts: {rel.get('relationship_counts') or {}}."]
    for e in edges:
        arrow = "->" if e.get("directional") else "<->"
        rlines.append(f"  - {e.get('from_campaign_id')} {arrow} {e.get('to_campaign_id')}: "
                      f"{_t(e.get('relationship'))} - {e.get('reason')} "
                      f"[{'; '.join(e.get('supporting_evidence') or [])}; "
                      f"{e.get('authority')}]")
    iso = rel.get("isolated_campaign_ids") or []
    if iso:
        rlines.append(f"  - isolated (no engineering relationship to any other): "
                      f"{', '.join(iso)}")
    out.append(("Cross-campaign relationships", rlines))

    klines: List[str] = []
    for k in r.get("knowledge_map") or []:
        klines.append(f"  - {k.get('objective') or k.get('campaign_id')}: "
                      f"{_t(k.get('state'))} - {k.get('reason')} [{k.get('source')}]")
    out.append(("Engineering knowledge map", klines or ["No campaigns to map."]))

    out.append(("Safety", [str(r.get("safety_statement") or "")]))
    return out


def _render_metric_value(val) -> str:
    if isinstance(val, dict):
        return ", ".join(f"{_t(k)} {_n(v)}" for k, v in val.items())
    return _n(val)


def render_report_text(report) -> str:
    out: List[str] = []
    for title, lines in render_report_sections(report):
        out.append(title)
        out.extend(f"  {ln}" for ln in lines if str(ln).strip())
        out.append("")
    return "\n".join(out).rstrip() + "\n"
