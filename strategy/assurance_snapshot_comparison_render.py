"""Deterministic renderer for the Assurance Snapshot Comparison (Program 2, Phase 34).

Renders baseline -> candidate comparison as concise structured sections. Strings only; zero DB;
timestamp-free; no setup values. An incompatible/unverifiable comparison shows NO assurance trend.
Pure; deterministic; never raises.
"""
from __future__ import annotations

from typing import List, Tuple


def _t(v) -> str:
    return str(v if v is not None else "").replace("_", " ").strip()


def _ident(i) -> str:
    i = i if isinstance(i, dict) else {}
    return f"{i.get('car')} / {_t(i.get('discipline'))} / v{i.get('gt7_version')} / {i.get('driver')}"


def _delta_lines(deltas) -> List[str]:
    out = []
    for d in (deltas or []):
        bl = d.get("baseline") or "-"
        cd = d.get("candidate") or "-"
        out.append(f"  - [{_t(d.get('change_type'))}] {d.get('key')} ({_t(d.get('domain')) or 'programme'}"
                   f"): {bl} -> {cd}. {d.get('detail') or ''}")
    return out


def render_comparison_sections(comp) -> List[Tuple[str, List[str]]]:
    r = comp if isinstance(comp, dict) else {}
    out: List[Tuple[str, List[str]]] = []

    compat = _t(r.get("compatibility"))
    header = [f"Direction: baseline -> candidate.",
              f"Baseline: {_ident(r.get('baseline_identity'))}  (grade "
              f"{_t(r.get('baseline_grade')).upper()}, chain {r.get('baseline_chain_fingerprint')}).",
              f"Candidate: {_ident(r.get('candidate_identity'))}  (grade "
              f"{_t(r.get('candidate_grade')).upper()}, chain {r.get('candidate_chain_fingerprint')}).",
              f"Compatibility: {compat.upper()}."]
    for reason in (r.get("compatibility_reasons") or []):
        header.append(f"  - {reason}")
    out.append((f"Comparison - {compat.upper()}", header))

    trend = r.get("assurance_direction")
    if trend in ("incomparable",):
        out.append(("Assurance trend",
                    [f"  No assurance trend shown: {r.get('assurance_direction_reason')}."]))
    else:
        out.append(("Assurance trend",
                    [f"  {_t(trend).upper()}: {r.get('assurance_direction_reason')}."]))

    if trend != "incomparable":
        out.append(("Finding changes", _delta_lines(r.get("finding_deltas")) or ["None."]))
        out.append(("Contradiction changes", _delta_lines(r.get("contradiction_deltas")) or ["None."]))
        out.append(("Assumption changes", _delta_lines(r.get("assumption_deltas")) or ["None."]))
        out.append(("Readiness changes", _delta_lines(r.get("readiness_deltas")) or ["None."]))
        out.append(("Evidence-priority changes", _delta_lines(r.get("priority_deltas")) or ["None."]))
        out.append(("Domain rollup",
                    [f"  - {_t(d.get('domain'))}: {_t(d.get('change_type'))} "
                     f"(f{d.get('finding_changes')} a{d.get('assumption_changes')} "
                     f"c{d.get('contradiction_changes')} r:{_t(d.get('readiness_change'))} "
                     f"p{d.get('priority_changes')})"
                     for d in (r.get("domain_deltas") or [])] or ["None."]))

    out.append(("Changed chain sections (by content digest)",
                [f"  - {_t(f.get('section'))}: {f.get('baseline_digest')}... -> "
                 f"{f.get('candidate_digest')}..." for f in (r.get("fingerprint_changes") or [])]
                or ["None."]))

    out.append(("Notes", [f"  Comparison fingerprint: {r.get('content_fingerprint')}.",
                          f"  {r.get('advisory_statement') or ''}"]))
    return out


def render_comparison_text(comp) -> str:
    out: List[str] = []
    for title, lines in render_comparison_sections(comp):
        out.append(title)
        out.extend(f"  {ln}" for ln in lines if str(ln).strip())
        out.append("")
    return "\n".join(out).rstrip() + "\n"
