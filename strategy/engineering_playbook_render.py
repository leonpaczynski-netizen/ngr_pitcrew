"""Deterministic renderer for the Engineering Playbook (Program 2, Phase 24).

Renders the cross-programme engineering INVESTIGATION playbook as structured sections: programme-
wide themes, confirmed-good behaviours to protect, reusable knowledge + transfer level,
investigation priorities, knowledge to recollect, context-specific boundaries, historical failed
directions, per-target new-programme briefs, evidence/maturity sources, explicit limitations, and
a visible statement that no setup values were copied, generated or applied.

It renders STRINGS only, shows NO Apply / import / copy-setup / optimise / schedule wording, and
never presents prose resembling a complete setup recommendation. Pure; deterministic; never
raises.
"""
from __future__ import annotations

from typing import List, Tuple


def _t(v) -> str:
    return str(v if v is not None else "").replace("_", " ").strip()


def _prog(p) -> str:
    p = p if isinstance(p, dict) else {}
    return f"{p.get('car')} / {_t(p.get('discipline'))} / v{p.get('gt7_version')} / {p.get('driver')}"


def render_playbook_sections(playbook) -> List[Tuple[str, List[str]]]:
    pb = playbook if isinstance(playbook, dict) else {}
    out: List[Tuple[str, List[str]]] = []

    ident = pb.get("programme_identity") or {}
    summ = pb.get("global_stable_summary") or {}
    cov = pb.get("evidence_coverage") or {}
    out.append(("Programme engineering playbook", [
        f"Programme: {_prog(ident)}.",
        f"Stable themes: {summ.get('stable_themes')}   Reusable across programmes: "
        f"{summ.get('themes_reusable_across_programmes')}   Confirmed-good: "
        f"{summ.get('confirmed_good_themes')}   With negative history: "
        f"{summ.get('themes_with_negative_history')}.",
        f"Target programmes: {summ.get('target_programmes')}   Priority categories: "
        f"{summ.get('priority_category_counts') or {}}.",
        f"Evidence coverage: {cov.get('known_domains')} known / {cov.get('missing_domains')} "
        f"missing domains; {cov.get('total_confirmations')} confirmations, "
        f"{cov.get('total_regressions')} regressions, {cov.get('domains_with_conflict')} with "
        f"conflict.",
    ]))

    # Programme-wide engineering themes
    tlines: List[str] = []
    for t in pb.get("stable_themes") or []:
        elig = t.get("transfer_eligibility_summary") or {}
        tlines.append(f"  - {_t(t.get('engineering_domain'))} [{t.get('mechanism')}]: "
                      f"recurrence {t.get('recurrence_count')}, {t.get('evidence_count')} "
                      f"confirmation(s), {_t(t.get('maturity_summary'))} / "
                      f"{_t(t.get('confidence_summary'))}; transfer best "
                      f"{_t(elig.get('best_level'))} across {elig.get('reusable_targets')}/"
                      f"{elig.get('total_targets')} target(s). {t.get('rationale')}")
    out.append(("Programme-wide engineering themes", tlines or ["No established themes yet."]))

    # Confirmed-good behaviours to protect
    plines: List[str] = []
    for t in pb.get("stable_themes") or []:
        for cg in t.get("confirmed_good_protections") or []:
            plines.append(f"  - {cg.get('behaviour')} (confidence {_t(cg.get('confidence'))}) - "
                          f"{cg.get('note')} [{cg.get('source')}]")
    out.append(("Confirmed-good behaviours to protect", plines or ["None recorded."]))

    # Reusable knowledge and its transfer level
    rlines: List[str] = []
    for t in pb.get("stable_themes") or []:
        for tp in t.get("compatible_target_programmes") or []:
            elig = t.get("transfer_eligibility_summary") or {}
            rlines.append(f"  - {_t(t.get('engineering_domain'))} may be reused in {_prog(tp)} "
                          f"[{_t(elig.get('best_level'))}] - as a HYPOTHESIS only.")
    rlines.append("  " + _reuse_note(pb))
    out.append(("Reusable knowledge and its transfer level", rlines))

    # Investigation priorities
    ilines: List[str] = []
    for p in pb.get("investigation_priorities") or []:
        flag = "  [!] threatens a confirmed-good behaviour" if p.get("masking_conflict") else ""
        ilines.append(f"  - [{_t(p.get('category'))}] {_t(p.get('domain'))} "
                      f"(score {p.get('engineering_score')}): {p.get('rationale')}{flag}")
    out.append(("Investigation priorities", ilines or ["Nothing to prioritise."]))

    # Knowledge that must be recollected
    recollect = [p for p in (pb.get("investigation_priorities") or [])
                 if str(p.get("category")) == "recollect_evidence"]
    out.append(("Knowledge that must be recollected",
                [f"  - {_t(p.get('domain'))}: {p.get('rationale')}" for p in recollect]
                or ["None."]))

    # Context-specific boundaries
    blines: List[str] = []
    for b in pb.get("knowledge_boundaries") or []:
        tgt = f" -> {b.get('target_car')}" if b.get("target_car") else ""
        blines.append(f"  - {_t(b.get('boundary_type'))} ({_t(b.get('domain'))}{tgt}): "
                      f"{b.get('reason')} [{b.get('source_authority')}]")
    out.append(("Context-specific boundaries", blines or ["None."]))

    # Historical failed directions
    flines: List[str] = []
    for t in pb.get("stable_themes") or []:
        for neg in t.get("known_negative_outcomes") or []:
            flines.append(f"  - {_t(t.get('engineering_domain'))}: {neg}")
    out.append(("Historical failed directions", flines or ["None recorded."]))

    # Per-target new-programme briefs
    for br in pb.get("new_programme_briefs") or []:
        out.append((f"New-programme brief: {br.get('target_programme', {}).get('car')}",
                    _brief_lines(br)))

    # Limitations + no-setup statement
    out.append(("Limitations", [f"  - {lim}" for lim in pb.get("limitations") or []]))
    out.append(("No setup transferred",
                [_NO_SETUP, str(pb.get("safety_statement") or "")]))
    return out


_NO_SETUP = ("No setup values were copied, generated, recommended or applied. This is an "
             "engineering investigation playbook, not a baseline setup - every item is knowledge "
             "to validate, not numbers to enter.")


def _reuse_note(pb) -> str:
    for t in pb.get("stable_themes") or []:
        meaning = (t.get("transfer_eligibility_summary") or {}).get("meaning")
        if meaning:
            return meaning
    return _NO_SETUP


def _brief_lines(br) -> List[str]:
    def _items(key, fmt):
        return [fmt(x) for x in (br.get(key) or [])]
    lines = [f"  Source: {_prog(br.get('source_programme'))}   ->   Target: "
             f"{_prog(br.get('target_programme'))}",
             "  Established knowledge: "
             + (", ".join(_t(x.get("domain")) for x in br.get("established_knowledge") or [])
                or "-")]
    lines += ["  Protect (confirmed-good): "
              + (", ".join(_t(x.get("domain")) for x in br.get("protect") or []) or "-")]
    lines += ["  Eligible for cautious reuse (hypothesis only): "
              + (", ".join(f"{_t(x.get('domain'))} [{_t(x.get('transfer_level'))}]"
                           for x in br.get("eligible_for_cautious_reuse") or []) or "-")]
    lines += ["  Needs early validation: "
              + (", ".join(_t(x.get("domain")) for x in br.get("needs_early_validation") or [])
                 or "-")]
    lines += ["  Recollect evidence: "
              + (", ".join(_t(x.get("domain")) for x in br.get("recollect_evidence") or []) or "-")]
    lines += ["  Must NOT reuse: "
              + (", ".join(_t(x.get("domain")) for x in br.get("must_not_reuse") or []) or "-")]
    for neg in br.get("negative_directions_to_avoid") or []:
        lines.append(f"  Avoid: {neg}")
    for unc in br.get("unresolved_uncertainties") or []:
        lines.append(f"  Uncertainty: {unc}")
    lines.append(f"  {br.get('no_setup_statement')}")
    return lines


def render_playbook_text(playbook) -> str:
    out: List[str] = []
    for title, lines in render_playbook_sections(playbook):
        out.append(title)
        out.extend(f"  {ln}" for ln in lines if str(ln).strip())
        out.append("")
    return "\n".join(out).rstrip() + "\n"
