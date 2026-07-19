"""Deterministic renderer for the Assurance Review Package specification (Program 2, Phase 35).

Renders the package OVERVIEW (identity, grade, artifact membership + digests, fingerprints,
verification instructions, advisory). The individual artifacts (report + manifests) are rendered by
their own phase renderers and carried inside the package. Strings only; zero DB; timestamp-free; no
setup values; no machine paths. Pure; deterministic; never raises.
"""
from __future__ import annotations

from typing import List, Tuple


def _t(v) -> str:
    return str(v if v is not None else "").replace("_", " ").strip()


def _prog(p) -> str:
    p = p if isinstance(p, dict) else {}
    return f"{p.get('car')} / {_t(p.get('discipline'))} / v{p.get('gt7_version')} / {p.get('driver')}"


def render_package_sections(pkg) -> List[Tuple[str, List[str]]]:
    r = pkg if isinstance(pkg, dict) else {}
    ident = r.get("identity") or {}
    out: List[Tuple[str, List[str]]] = []

    header = [f"Programme: {_prog(ident.get('programme'))}.",
              f"DB schema v{ident.get('db_schema_version')}, rule engine "
              f"{ident.get('rule_engine_version')}.",
              f"Assurance grade: {_t(r.get('assurance_grade')).upper()}.",
              f"Assurance-chain fingerprint: {r.get('assurance_chain_fingerprint')}.",
              f"Package fingerprint: {r.get('package_fingerprint')}.",
              f"Baseline comparison included: {'yes' if r.get('has_comparison') else 'no'}"
              + (f" (comparison fingerprint {r.get('comparison_fingerprint')})"
                 if r.get('has_comparison') else "") + "."]
    out.append((f"Review package - grade {_t(r.get('assurance_grade')).upper()}", header))

    arts = [f"  - {_t(a.get('kind'))} [{a.get('media_type')}] digest "
            f"{(a.get('content_digest') or '')[:16]}..." for a in (r.get("artifacts") or [])]
    out.append(("Member artifacts (verify by digest, not filename)", arts or ["None."]))

    out.append(("How to verify (no trust in filenames or timestamps)",
                ["  " + str(x) for x in (r.get("verification_instructions") or [])]))

    out.append(("Limitations & advisory",
                ["  - " + str(x) for x in (r.get("limitations") or [])]
                + [f"  {r.get('advisory_statement') or ''}"]))
    return out


def render_package_text(pkg) -> str:
    out: List[str] = []
    for title, lines in render_package_sections(pkg):
        out.append(title)
        out.extend(f"  {ln}" for ln in lines if str(ln).strip())
        out.append("")
    return "\n".join(out).rstrip() + "\n"
