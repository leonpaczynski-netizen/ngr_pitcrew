"""Pure view-model for the Manual UAT evidence + readiness surface (Qt-free, Program 2, Phase 71).

Turns the manual areas, the active-observation ledger and the release-candidate readiness into glanceable
display rows: the area options, the status options, the active observation for a selected area, the honest
readiness banner (with blockers + caveats), and the release-candidate manifest tier summary. It states
plainly that physical / PSVR2 / live-GT7 areas are certified ONLY by real user evidence. Display strings
only; never raises; it records nothing (writes are the panel's explicit user action).
"""
from __future__ import annotations

from typing import List

from strategy.manual_uat_evidence import MANUAL_UAT_AREAS, ManualUatStatus


_STATUS_TONE = {"not_run": "neutral", "pass": "success", "fail": "warn", "blocked": "warn",
                "not_applicable": "info"}
_READINESS_TONE = {"not_ready_for_manual_uat": "warn", "conditional_for_manual_uat": "info",
                   "ready_for_manual_uat": "success", "operationally_certified": "success"}


def area_options() -> List[dict]:
    return [{"key": a.key, "label": a.label, "category": a.category} for a in MANUAL_UAT_AREAS]


def status_options() -> List[dict]:
    return [{"key": s.value, "label": s.value.replace("_", " ").upper()} for s in ManualUatStatus]


def status_tone(status: str) -> str:
    return _STATUS_TONE.get(str(status or "not_run"), "neutral")


def active_observation_lines(observation) -> List[str]:
    o = observation if isinstance(observation, dict) else {}
    if not o:
        return ["No observation recorded yet for this area."]
    lines = [f"Status: {str(o.get('status') or 'not_run').replace('_', ' ').upper()}"
             f"{'  (RETEST REQUIRED)' if o.get('retest_required') else ''}.",
             f"Tested: {o.get('tested_at') or '—'}  ·  commit {o.get('candidate_commit') or '—'}."]
    if o.get("expected_behaviour"):
        lines.append(f"Expected: {o.get('expected_behaviour')}")
    if o.get("observed_behaviour"):
        lines.append(f"Observed: {o.get('observed_behaviour')}")
    if o.get("notes"):
        lines.append(f"Notes: {o.get('notes')}")
    if o.get("defect_reference"):
        lines.append(f"Defect: {o.get('defect_reference')}")
    if o.get("evidence_reference"):
        lines.append(f"Evidence: {o.get('evidence_reference')}")
    if o.get("hardware_context"):
        lines.append(f"Hardware: {o.get('hardware_context')}")
    if o.get("supersedes"):
        lines.append("(supersedes a prior observation — the earlier one is preserved for audit)")
    return lines


def readiness_header(manifest) -> str:
    m = manifest if isinstance(manifest, dict) else {}
    rd = (m.get("readiness") or {})
    level = str(rd.get("readiness") or "not_ready_for_manual_uat")
    return f"[{level.replace('_', ' ').upper()}]  {rd.get('rationale') or ''}".strip()


def readiness_tone(manifest) -> str:
    rd = (manifest or {}).get("readiness", {}) if isinstance(manifest, dict) else {}
    return _READINESS_TONE.get(str(rd.get("readiness") or "not_ready_for_manual_uat"), "neutral")


def blocker_lines(manifest) -> List[str]:
    m = manifest if isinstance(manifest, dict) else {}
    rd = m.get("readiness") or {}
    lines = [f"[BLOCKER] {b}" for b in (rd.get("blockers") or [])]
    lines += [f"[CAVEAT] {c}" for c in (rd.get("caveats") or [])]
    if not lines:
        return ["No blockers or caveats."]
    return lines


def manifest_tier_lines(manifest) -> List[str]:
    m = manifest if isinstance(manifest, dict) else {}
    tiers = m.get("evidence_tiers") or {}
    order = ["automated_regression", "bench_uat", "manual_desktop_uat", "physical_voice_ptt_uat",
             "psvr2_uat", "live_gt7_uat", "operational_certification"]
    lines = []
    for k in order:
        if k in tiers:
            lines.append(f"{k.replace('_', ' ').title()}: {tiers[k]}")
    if m.get("commit"):
        lines.insert(0, f"Candidate: {m.get('branch') or '—'} @ {m.get('commit') or '—'} "
                        f"(DB v{m.get('db_version', '?')}, rule engine {m.get('rule_engine_version') or '?'}).")
    return lines or ["No manifest available."]


def manual_progress_lines(manifest) -> List[str]:
    """Per-category manual progress (how many areas passed vs total)."""
    m = manifest if isinstance(manifest, dict) else {}
    results = m.get("manual_results") or []
    by_cat: dict = {}
    for r in results:
        cat = str(r.get("category") or "?")
        c = by_cat.setdefault(cat, {"pass": 0, "total": 0})
        c["total"] += 1
        if str(r.get("status")) == "pass":
            c["pass"] += 1
    lines = []
    for cat in sorted(by_cat):
        c = by_cat[cat]
        lines.append(f"{cat}: {c['pass']}/{c['total']} passed")
    return lines or ["No manual areas."]
