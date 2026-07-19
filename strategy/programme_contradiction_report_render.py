"""Deterministic renderer for the Programme Contradiction Report (Program 2, Phase 29).

Renders the contradiction view as structured sections. Strings only; zero DB access; never renders
setup values, scheduling instructions, reminders, future dates or automatic next actions. Pure;
deterministic; never raises.
"""
from __future__ import annotations

from typing import List, Tuple


def _t(v) -> str:
    return str(v if v is not None else "").replace("_", " ").strip()


def _prog(p) -> str:
    p = p if isinstance(p, dict) else {}
    return f"{p.get('car')} / {_t(p.get('discipline'))} / v{p.get('gt7_version')} / {p.get('driver')}"


def _side(s) -> str:
    s = s if isinstance(s, dict) else {}
    return (f"{s.get('record_count')} record(s), {s.get('distinct_sessions')} session(s), "
            f"high-confidence {s.get('has_high_confidence')}, latest "
            f"{s.get('latest_date') or 'unknown'}")


def _c_line(c) -> str:
    causes = "; ".join(x.get("text", "") for x in (c.get("causes") or [])) or "-"
    standing = c.get("standing_conclusion") or "no single conclusion stands"
    return (f"  - {_t(c.get('domain'))}: {_t(c.get('status'))} "
            f"({'OPEN' if c.get('is_open') else 'resolved'}) - standing: {standing}. "
            f"Confirming side: {_side(c.get('positive_summary'))}. Regressing side: "
            f"{_side(c.get('negative_summary'))}. Causes: {causes}. {c.get('rationale') or ''}")


def render_contradiction_sections(report) -> List[Tuple[str, List[str]]]:
    r = report if isinstance(report, dict) else {}
    out: List[Tuple[str, List[str]]] = []

    src = r.get("source_programme") or {}
    tot = r.get("totals") or {}
    header = [f"Programme: {_prog(src)}.",
              f"Contradictions: {tot.get('contradictions')} ({tot.get('open')} open, "
              f"{tot.get('resolved')} resolved); genuinely unresolved "
              f"{tot.get('unresolved_genuine')}; context-explained "
              f"{tot.get('resolved_by_context')}."]
    if r.get("empty_state"):
        header.append(r.get("empty_state"))
    out.append(("Contradiction summary", header))

    out.append(("Open contradictions (evidence does not tell us which is right)",
                [_c_line(c) for c in (r.get("open_contradictions") or [])] or ["None."]))
    out.append(("Resolved / explained contradictions",
                [_c_line(c) for c in (r.get("resolved_contradictions") or [])] or ["None."]))

    out.append(("Notes", [_DOCTRINE, str(r.get("safety_statement") or "")]))
    return out


_DOCTRINE = ("A contradiction is never resolved by majority vote or by recency; dependent evidence "
             "never defeats independent evidence; a later observation only supersedes an earlier one "
             "when it is ALSO stronger; a version / context mismatch is surfaced, not hidden; and a "
             "contradiction is allowed to remain open. No action is scheduled or applied; no setup "
             "values are shown.")


def render_contradiction_text(report) -> str:
    out: List[str] = []
    for title, lines in render_contradiction_sections(report):
        out.append(title)
        out.extend(f"  {ln}" for ln in lines if str(ln).strip())
        out.append("")
    return "\n".join(out).rstrip() + "\n"
