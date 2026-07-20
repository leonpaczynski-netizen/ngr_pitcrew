"""Deterministic renderer for the Live Advisory decision (Program 2, Phase 44).

Strings only; zero DB access; timestamp-free; never renders setup values. Pure; deterministic; never
raises.
"""
from __future__ import annotations

from typing import List, Tuple


def _t(v) -> str:
    return str(v if v is not None else "").replace("_", " ").strip()


def render_advisory_sections(decision) -> List[Tuple[str, List[str]]]:
    d = decision if isinstance(decision, dict) else {}
    out: List[Tuple[str, List[str]]] = []
    dv = d.get("delivered")
    if dv:
        out.append(("Current advisory",
                    [f"  [{_t(dv.get('prompt_class')).upper()} / P{dv.get('priority')}] "
                     f"{dv.get('message')}",
                     f"  Why: {dv.get('rationale')}",
                     f"  Source: {_t(dv.get('source_authority'))}; window {_t(dv.get('delivery_window'))}; "
                     f"confidence {dv.get('confidence') or '-'}."]))
    else:
        out.append(("Current advisory", ["  No advisory to deliver right now."]))

    if d.get("active_objective"):
        out.append(("Active coaching objective", [f"  {d.get('active_objective')}"]))

    supp = d.get("suppressed") or []
    lines = [f"  - [P{s.get('priority')}] {_t(s.get('suppression_key'))}: {s.get('reason')}"
             for s in supp]
    out.append((f"Suppressed ({len(supp)})", lines or ["  None."]))
    return out


def render_advisory_text(decision) -> str:
    out: List[str] = []
    for title, lines in render_advisory_sections(decision):
        out.append(title)
        out.extend(f"  {ln}" for ln in lines if str(ln).strip())
        out.append("")
    return "\n".join(out).rstrip() + "\n"
