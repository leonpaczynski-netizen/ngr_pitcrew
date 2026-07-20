"""Deterministic renderer for Material Context Trust (Program 2, Phase 42).

Strings only; zero DB access; timestamp-free; never renders setup values. Pure; deterministic; never
raises.
"""
from __future__ import annotations

from typing import List, Tuple


def _t(v) -> str:
    return str(v if v is not None else "").replace("_", " ").strip()


def render_material_context_sections(trust) -> List[Tuple[str, List[str]]]:
    r = trust if isinstance(trust, dict) else {}
    out: List[Tuple[str, List[str]]] = []
    head = [f"Domain: {_t(r.get('domain'))}.",
            f"Context trust: {_t(r.get('overall_trust')).upper()}.",
            f"Exact-eligible: {r.get('exact_eligible')}.",
            f"Trust fingerprint: {r.get('content_fingerprint') or '-'}."]
    out.append(("Material context trust", head))

    req = [f for f in (r.get("field_trust") or []) if f.get("required")]
    lines = [f"  - {f.get('field')} [{_t(f.get('field_class'))}]: {_t(f.get('trust')).upper()}"
             for f in req]
    out.append(("Required fields (this domain)", lines or ["  None."]))

    lim = r.get("limiting_fields") or []
    out.append(("Limiting fields", [f"  - {f.get('field')}: {_t(f.get('trust'))}" for f in lim]
                or ["  None - all required fields are a known match."]))

    out.append(("Explanation", [f"  {r.get('limitation_explanation') or ''}"]))
    return out


def render_material_context_text(trust) -> str:
    out: List[str] = []
    for title, lines in render_material_context_sections(trust):
        out.append(title)
        out.extend(f"  {ln}" for ln in lines if str(ln).strip())
        out.append("")
    return "\n".join(out).rstrip() + "\n"
