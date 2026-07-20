"""Deterministic renderer for the Context-Safe Knowledge Activation (Program 2, Phase 36).

Renders the canonical context scope + the classified evidence as concise structured sections. Strings
only; zero DB access; timestamp-free (no wall-clock; recorded evidence dates are data, shown as-is);
never renders setup values or Apply controls. Pure; deterministic; never raises.
"""
from __future__ import annotations

from typing import List, Tuple


def _t(v) -> str:
    return str(v if v is not None else "").replace("_", " ").strip()


def render_scope_sections(scope) -> List[Tuple[str, List[str]]]:
    s = scope if isinstance(scope, dict) else {}
    out: List[Tuple[str, List[str]]] = []
    ident = [
        f"Driver: {s.get('driver') or '-'}; car: {s.get('car') or '-'}"
        + (f" ({s.get('car_variant')})" if s.get('car_variant') else "") + ".",
        f"Track: {s.get('track') or '-'} / {s.get('layout_id') or '-'}; event: {s.get('event_id') or '-'}.",
        f"Discipline: {_t(s.get('discipline')).upper() or '-'}; compound: {s.get('compound') or '-'}"
        + (f" (policy {s.get('compound_policy')})" if s.get('compound_policy') else "") + ".",
        f"Regulation: BoP {s.get('bop_state') or '-'}; tuning {_t(s.get('tuning_permitted')) or '-'}; "
        f"power {s.get('power_restriction') or '-'}; weight {s.get('weight_restriction') or '-'}.",
        f"Versions: GT7 {s.get('gt7_version') or '-'}, rule {s.get('rule_engine_version') or '-'}, "
        f"data {s.get('data_schema_version') or '-'}.",
        f"Objective: {s.get('race_objective') or '-'}; tyre x{s.get('tyre_multiplier') or '-'}, "
        f"fuel x{s.get('fuel_multiplier') or '-'}.",
        f"Completeness: {_t(s.get('completeness')).upper()}.",
    ]
    missing = s.get("missing_fields") or []
    if missing:
        ident.append("Missing (explicit, not assumed): " + ", ".join(_t(m) for m in missing) + ".")
    ident.append(f"Context fingerprint: {s.get('context_fingerprint') or '-'}.")
    out.append((f"Current engineering context - {s.get('label') or 'unknown'}", ident))
    return out


def render_activation_sections(activation) -> List[Tuple[str, List[str]]]:
    a = activation if isinstance(activation, dict) else {}
    out = render_scope_sections(a.get("scope") or {})

    counts = a.get("counts") or {}
    summary = [f"  - {_t(k)}: {v}" for k, v in sorted(counts.items())]
    out.append(("Evidence classification (context-safe retrieval)", summary or ["None."]))

    items = a.get("items") or []
    # show a compact line per item, already in canonical class order.
    lines: List[str] = []
    for i in items:
        lines.append(
            f"  - [{_t(i.get('classification'))}] {_t(i.get('relation'))}; "
            f"{i.get('context', {}).get('track') or '-'}/{i.get('context', {}).get('layout_id') or '-'}; "
            f"fields {', '.join(i.get('fields') or []) or '-'}; "
            f"outcome {_t(i.get('outcome_status')) or '-'}; "
            f"transfer {i.get('transfer_level') or '-'}. {i.get('reason')}")
    out.append(("Classified evidence (priority: exact first)", lines or ["No recorded evidence yet."]))

    guard = a.get("contamination_guard") or []
    out.append(("Contamination guard (excluded / reference-only)",
                ["  - " + str(g) for g in guard] or ["  None - no incompatible evidence present."]))

    out.append(("Invariant", [f"  {a.get('invariant_statement') or ''}"]))
    return out


def render_activation_text(activation) -> str:
    out: List[str] = []
    for title, lines in render_activation_sections(activation):
        out.append(title)
        out.extend(f"  {ln}" for ln in lines if str(ln).strip())
        out.append("")
    return "\n".join(out).rstrip() + "\n"
