"""Pure view-model for the Operational Certification developer/UAT surface (Qt-free, Program 2, Phase 56).

Turns an ``EventProgrammeCertification`` payload into an overall banner + one card per certification area
(evidence type, effective level, last scenario, findings). This is a DEVELOPER/UAT surface — it is kept
off the driver-facing Command Centre. Each item carries a text tag + tone (meaning never colour alone).
Display strings only; never raises.
"""
from __future__ import annotations

from typing import List


def build(result=None) -> dict:
    return result if isinstance(result, dict) else {}


def is_empty(result) -> bool:
    return not build(result).get("areas")


# certification level -> tone (higher levels greener; not-tested/automated neutral)
_LEVEL_TONE = {
    "not_tested": "neutral", "automated_only": "info", "offscreen_validated": "info",
    "replay_validated": "info", "visual_uat_partial": "warn", "visual_uat_validated": "success",
    "live_gt7_partial": "warn", "live_gt7_validated": "success",
    "operationally_ready_with_limitations": "success", "operationally_ready": "success",
}
_EVIDENCE_TONE = {"none": "neutral", "automated": "info", "offscreen": "info", "replay": "info",
                  "visual_partial": "warn", "visual": "success", "live_partial": "warn", "live": "success"}
_SEVERITY_TONE = {"info": "info", "limitation": "warn", "blocker": "warn"}


def header_text(result) -> str:
    r = build(result)
    if is_empty(result):
        return ("No certification recorded. This developer/UAT surface reports the evidence supporting each "
                "area of the NGR event journey. Automated evidence never awards visual/live/operational "
                "certification.")
    overall = str(r.get("overall_level") or "not_tested")
    parts = [f"[OVERALL: {overall.replace('_', ' ').upper()}]  bounded by '{r.get('weakest_area') or '-'}'"]
    if r.get("blockers"):
        parts.append(f"{len(r.get('blockers'))} blocker(s).")
    if r.get("limitations"):
        parts.append(f"{len(r.get('limitations'))} limitation(s).")
    return "  ".join(parts)


def banner_tone(result) -> str:
    if is_empty(result):
        return "advisory"
    if build(result).get("blockers"):
        return "warn"
    return _LEVEL_TONE.get(str(build(result).get("overall_level")), "neutral")


def area_cards(result) -> List[dict]:
    r = build(result)
    cards: List[dict] = []
    for a in (r.get("areas") or []):
        level = str(a.get("effective_level") or "not_tested")
        lines = [f"Evidence: {str(a.get('evidence_type') or 'none').upper()}   "
                 f"Level: {level.replace('_', ' ').upper()}.",
                 f"Last scenario: {a.get('last_scenario') or '-'}."]
        for f in (a.get("findings") or []):
            lines.append(f"[{str(f.get('severity') or 'info').upper()}] {f.get('message') or ''}")
        cards.append({"title": str(a.get("name") or "-").replace("_", " ").title(),
                      "status_tag": level.replace("_", " ").upper(),
                      "tone": _LEVEL_TONE.get(level, "neutral"), "lines": lines})
    return cards
