"""Deterministic renderer for the Programme Re-validation Report (Program 2, Phase 26).

Renders the knowledge decay / re-validation view as structured sections. It renders STRINGS only,
performs zero DB access, and never renders setup values, scheduling instructions, reminders, future
dates or automatic next actions. Pure; deterministic; never raises.
"""
from __future__ import annotations

from typing import List, Tuple


def _t(v) -> str:
    return str(v if v is not None else "").replace("_", " ").strip()


def _prog(p) -> str:
    p = p if isinstance(p, dict) else {}
    return f"{p.get('car')} / {_t(p.get('discipline'))} / v{p.get('gt7_version')} / {p.get('driver')}"


def _item_line(i) -> str:
    aid = "  (investigation aid only)" if i.get("investigation_aid_only") else ""
    cg = "  [confirmed-good protected]" if i.get("confirmed_good") else ""
    reasons = "; ".join(r.get("text", "") for r in (i.get("reasons") or [])) or "-"
    return (f"  - {_t(i.get('domain'))}: {_t(i.get('freshness_status'))}{cg}{aid} - "
            f"maturity {_t(i.get('current_maturity'))}, confidence {_t(i.get('current_confidence'))}; "
            f"last evidence {i.get('last_evidence_date') or 'unknown'}. Reasons: {reasons}. "
            f"Missing: {i.get('missing_evidence') or 'nothing'}.")


def render_revalidation_sections(report) -> List[Tuple[str, List[str]]]:
    r = report if isinstance(report, dict) else {}
    out: List[Tuple[str, List[str]]] = []

    src = r.get("source_programme") or {}
    tot = r.get("totals") or {}
    header = [f"Programme: {_prog(src)}.",
              f"Domains assessed: {tot.get('domains')}. Current/protected "
              f"{tot.get('current_protected')}, advised {tot.get('advised')}, required "
              f"{tot.get('required')}, version-invalidated {tot.get('version_invalidated')}, "
              f"conflict {tot.get('conflict_weakened')}, regression "
              f"{tot.get('regression_weakened')}, superseded/retired "
              f"{tot.get('superseded_retired')}, unknown {tot.get('unknown_insufficient')}.",
              f"Programme version changed: {tot.get('programme_version_changed')}; context changed "
              f"fields: {', '.join(tot.get('programme_context_changed_fields') or []) or 'none'}."]
    if r.get("empty_state"):
        header.append(r.get("empty_state"))
    out.append(("Re-validation summary", header))

    sections = [
        ("Current / protected knowledge", "current_protected"),
        ("Re-validation advised", "revalidation_advised"),
        ("Re-validation required", "revalidation_required"),
        ("Invalidated by version change", "version_invalidated"),
        ("Weakened by conflict", "conflict_weakened"),
        ("Weakened by regression", "regression_weakened"),
        ("Superseded / retired (inactive)", "superseded_retired"),
        ("Unknown / insufficient assessment", "unknown_insufficient"),
    ]
    for title, key in sections:
        items = r.get(key) or []
        out.append((title, [_item_line(i) for i in items] or ["None."]))

    out.append(("Notes", [_DATES_NOTE, str(r.get("safety_statement") or "")]))
    return out


_DATES_NOTE = ("Dates are evidence data, not an automatic expiry. Age alone never invalidates "
               "knowledge; a version change re-validates only version-sensitive knowledge; "
               "confirmed-good behaviour stays protected; retired directions stay retired. No "
               "action is scheduled or applied; no setup values are shown.")


def render_revalidation_text(report) -> str:
    out: List[str] = []
    for title, lines in render_revalidation_sections(report):
        out.append(title)
        out.extend(f"  {ln}" for ln in lines if str(ln).strip())
        out.append("")
    return "\n".join(out).rstrip() + "\n"
