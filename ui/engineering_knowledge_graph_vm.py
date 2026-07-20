"""Pure view-model for the Engineering Knowledge Graph section (Qt-free, Phase 22).

Turns the read-only ``SessionDB.build_programme_knowledge_report`` result into structured cards +
banner. Display strings only - it aggregates/decides nothing itself, edits nothing, and reads the
deterministic report exactly as built. Never raises.
"""
from __future__ import annotations

from typing import List


def build(result=None) -> dict:
    return result if isinstance(result, dict) else {}


def _report(result) -> dict:
    r = build(result)
    p = r.get("programme_knowledge")
    return p if isinstance(p, dict) else {}


def is_empty(result) -> bool:
    rep = _report(result)
    graph = rep.get("knowledge_graph") or {}
    return not build(result).get("ok") or not (graph.get("known_domains") or [])


def header_text(result) -> str:
    rep = _report(result)
    graph = rep.get("knowledge_graph") or {}
    known = graph.get("known_domains") or []
    if not known:
        return ("No engineering knowledge to graph yet for this car / discipline. The knowledge "
                "graph appears once campaigns exist. Read-only - it describes what is known and "
                "what remains unknown; it schedules, completes and applies nothing.")
    comp = rep.get("compatibility") or {}
    tot = rep.get("totals") or {}
    return (f"{len(known)} domain(s) known, {tot.get('missing_domains')} still missing across "
            f"{comp.get('events_merged')} merged event(s) "
            f"(tracks: {', '.join(comp.get('primary_tracks') or []) or '-'}). "
            f"Maturity: {tot.get('domain_maturity_counts') or {}}. Advisory only - it explains "
            "engineering knowledge; it completes and applies nothing.")


def banner_tone(result) -> str:
    rep = _report(result)
    graph = rep.get("knowledge_graph") or {}
    if not (graph.get("known_domains") or []):
        return "info"
    counts = (rep.get("totals") or {}).get("domain_maturity_counts") or {}
    if int(counts.get("complete", 0)) + int(counts.get("mature", 0)) > 0:
        return "success"
    if int(counts.get("plateaued", 0)) > 0:
        return "warn"
    return "info"


def graph_cards(result) -> List[dict]:
    from strategy.programme_knowledge_report_render import render_report_sections
    rep = _report(result)
    graph = rep.get("knowledge_graph") or {}
    if not (graph.get("known_domains") or []):
        return []
    return [{
        "title": "Engineering Knowledge Graph",
        "status": f"{len(graph.get('known_domains') or [])} domain(s) known",
        "sections": [(t, list(lines)) for t, lines in render_report_sections(rep)],
        "fingerprint": str(rep.get("content_fingerprint") or ""),
    }]
