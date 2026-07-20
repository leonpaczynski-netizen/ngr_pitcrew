"""Deterministic renderer for the Assurance-Chain Export (Program 2, Phase 33).

Renders the export as concise structured sections. Strings only; zero DB access; timestamp-free;
never renders setup values, dates, resources, machine paths or Apply controls. Pure; deterministic;
never raises.
"""
from __future__ import annotations

from typing import List, Tuple


def _t(v) -> str:
    return str(v if v is not None else "").replace("_", " ").strip()


def _prog(p) -> str:
    p = p if isinstance(p, dict) else {}
    return f"{p.get('car')} / {_t(p.get('discipline'))} / v{p.get('gt7_version')} / {p.get('driver')}"


def render_export_sections(export) -> List[Tuple[str, List[str]]]:
    r = export if isinstance(export, dict) else {}
    m = r.get("manifest") or {}
    out: List[Tuple[str, List[str]]] = []

    ident = [f"Programme: {_prog(m.get('programme_identity'))}.",
             f"Context: layout {m.get('context_identity', {}).get('layout_id') or '-'}, compound "
             f"{m.get('context_identity', {}).get('compound') or '-'}; domains "
             f"{', '.join(m.get('context_identity', {}).get('domains') or []) or 'none'}.",
             f"DB schema v{m.get('db_schema_version')}, rule engine {m.get('rule_engine_version')}.",
             f"Assurance grade: {_t(m.get('assurance_grade')).upper()}.",
             f"Chain fingerprint: {m.get('assurance_chain_fingerprint')}.",
             f"Manifest fingerprint: {m.get('canonical_manifest_fingerprint')}."]
    if r.get("empty_state"):
        ident.append(r.get("empty_state"))
    out.append((f"Assurance-chain export - grade {_t(r.get('assurance_grade')).upper()}", ident))

    sec_lines: List[str] = []
    for s in (r.get("sections") or []):
        state = "present" if s.get("present") else "absent"
        sec_lines.append(f"  - [{s.get('order')}] {s.get('title')} ({_t(s.get('phase_key'))}) - "
                         f"{state}; fingerprint {s.get('subordinate_fingerprint') or '-'}; digest "
                         f"{(s.get('content_digest') or '')[:16]}...")
    out.append(("Included chain sections (derivation order)", sec_lines or ["None."]))

    prov = [f"  - [{p.get('derivation_order')}] {_t(p.get('phase_key'))}: schema "
            f"{p.get('schema_version') or '-'}, eval {p.get('eval_version') or '-'}, digest "
            f"{(p.get('recomputed_content_digest') or '')[:16]}..."
            for p in (r.get("provenance") or [])]
    out.append(("Provenance", prov or ["None."]))

    integ = [f"  - {_t(i.get('section_key'))}: self-fp {i.get('subordinate_fingerprint') or '-'} / "
             f"recomputed digest {(i.get('content_digest') or '')[:16]}..."
             for i in (r.get("integrity") or [])]
    out.append(("Integrity (recompute-to-verify)", integ or ["None."]))

    val = r.get("validation") or {}
    val_lines = [f"  Status: {_t(val.get('status'))}."]
    val_lines += [f"  Error: {e}" for e in (val.get("errors") or [])]
    val_lines += [f"  Warning: {w}" for w in (val.get("warnings") or [])]
    out.append(("Validation", val_lines))

    out.append(("Limitations & advisory",
                ["  - " + str(x) for x in (r.get("limitations") or [])]
                + [f"  {r.get('advisory_statement') or ''}"]))
    return out


def render_export_text(export) -> str:
    out: List[str] = []
    for title, lines in render_export_sections(export):
        out.append(title)
        out.extend(f"  {ln}" for ln in lines if str(ln).strip())
        out.append("")
    return "\n".join(out).rstrip() + "\n"
