"""Dynamic driver profile — stats generation and AI-assisted updates.

Two capabilities:
  save_stats_doc(db)          — recompute driver_stats.md from the session DB
  propose_profile_update(key) — ask Claude to revise Part 2 of the knowledge base
  apply_profile_update(text)  — write approved text back to the knowledge base
"""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from data.session_db import ms_to_str
from strategy._ai_client import call_api, clear_gt7_cache

if TYPE_CHECKING:
    from data.session_db import SessionDB

_STATS_PATH   = Path(__file__).parent.parent / "knowledge" / "driver_stats.md"
_REF_PATH     = Path(__file__).parent.parent / "knowledge" / "gt7_tuning_reference.md"
_PART2_MARKER = "## PART 2 — DRIVER PERSONAL TUNING PROFILE"


# ---------------------------------------------------------------------------
# Stats document
# ---------------------------------------------------------------------------

def generate_stats_doc(summary: dict) -> str:
    """Build a markdown stats document from an all-laps summary dict."""
    if not summary or summary.get("total_laps", 0) == 0:
        return ""

    def _arrow(trend: str) -> str:
        return {"improving": "↑ improving", "worsening": "↓ worsening",
                "stable": "→ stable"}.get(trend, "→ stable")

    lines = [
        "## Driver Performance Statistics (auto-generated from session history)",
        "",
        f"**Sessions:** {summary['total_sessions']}  |  "
        f"**Total laps:** {summary['total_laps']}  |  "
        f"**Period:** {summary['first_session']} → {summary['last_session']}",
        "",
        "**All-time averages (recent 30-lap trend):**",
        f"- Lock-ups per lap: {summary['avg_lockups']:.1f} "
        f"(recent {summary['recent_lockups']:.1f}, {_arrow(summary['lockup_trend'])})",
        f"- Wheelspin events per lap: {summary['avg_wheelspin']:.1f} "
        f"(recent {summary['recent_wheelspin']:.1f}, {_arrow(summary['wheelspin_trend'])})",
    ]

    if summary["avg_consistency_m"] >= 0:
        lines.append(
            f"- Braking consistency std-dev: {summary['avg_consistency_m']:.1f}m "
            f"(recent {summary['recent_consistency_m']:.1f}m, "
            f"{_arrow(summary['consistency_trend'])})"
        )

    if summary.get("track_breakdown"):
        lines += ["", "**Track breakdown (most-practised):**"]
        for t in summary["track_breakdown"]:
            best = ms_to_str(t["best_ms"])
            lines.append(
                f"- {t['track']}: {t['laps']} laps, best {best}, "
                f"avg lock-ups {t['avg_lockups']:.1f}/lap, "
                f"wheelspin {t['avg_wheelspin']:.1f}/lap"
            )

    if summary.get("compound_bests"):
        lines += ["", "**Best lap times by compound (all tracks):**"]
        for compound, info in sorted(summary["compound_bests"].items()):
            lines.append(
                f"- {compound}: best {ms_to_str(info['best_ms'])} "
                f"({info['laps']} laps)"
            )

    return "\n".join(lines)


def save_stats_doc(db: "SessionDB") -> str:
    """Regenerate driver_stats.md from current DB state. Returns the text written."""
    summary = db.get_all_laps_summary()
    text = generate_stats_doc(summary)
    if text:
        _STATS_PATH.write_text(text, encoding="utf-8")
    elif _STATS_PATH.exists():
        _STATS_PATH.unlink()
    return text


def load_stats_doc() -> str:
    """Return the current stats doc, or empty string if not generated yet."""
    try:
        return _STATS_PATH.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""


# ---------------------------------------------------------------------------
# Profile Part 2 management
# ---------------------------------------------------------------------------

def _extract_part2() -> str:
    """Return only the Part 2 (driver profile) section from the knowledge base."""
    try:
        full = _REF_PATH.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""
    idx = full.find(_PART2_MARKER)
    return full[idx:] if idx != -1 else full


def _replace_part2(new_part2: str) -> None:
    """Swap Part 2 in the knowledge base file, preserving Part 1 exactly."""
    full = _REF_PATH.read_text(encoding="utf-8")
    idx = full.find(_PART2_MARKER)
    if idx == -1:
        raise ValueError(f"Marker '{_PART2_MARKER}' not found in knowledge base — file may be corrupted.")
    _REF_PATH.write_text(full[:idx] + new_part2, encoding="utf-8")


# ---------------------------------------------------------------------------
# AI-assisted update
# ---------------------------------------------------------------------------

def propose_profile_update(api_key: str, model: str | None = None) -> str:
    """Ask Claude to revise Part 2 based on the current telemetry stats.

    Returns the proposed new Part 2 text (starting with _PART2_MARKER).
    Caller should show this to the user for review before calling apply_profile_update().
    """
    current_profile = _extract_part2()
    if not current_profile:
        raise ValueError("Driver profile not found in knowledge base.")

    stats = load_stats_doc()
    if not stats:
        raise ValueError(
            "No stats available yet — click 'Refresh Stats' first to generate them from your session history."
        )

    prompt = f"""You are updating a Gran Turismo 7 driver's personal tuning profile.

This profile is embedded in a race engineer AI system. Every AI call for setup advice, driving coaching, and race strategy reads this profile to tailor recommendations to this specific driver. Keeping it accurate directly improves the quality of all AI advice.

## Current driver profile
{current_profile}

## Telemetry statistics from recorded sessions
{stats}

## Your task
Update the profile to reflect what the telemetry data clearly shows about this driver's current skill level and tendencies. Specific rules:

1. Only update sections where the data gives clear, consistent evidence (>10% trend over 30 laps = clear)
2. If a metric is "improving", update the relevant section to reflect the driver has developed strength there
3. If a metric is "worsening", note it as an active focus area (not a weakness — framed as something being worked on)
4. If "stable", leave that section's text unchanged
5. Add or update a brief "## Observed Trends" section at the very end with 2–4 bullet points summarising what the data shows
6. Preserve ALL existing sections — never delete anything, only update wording
7. Keep the driver's personal vocabulary exactly as-is ("skaty", "loose", "planted", etc.)
8. Do not invent detail the data doesn't support
9. Return ONLY the updated profile text — no explanation, no preamble, no markdown code fences
10. The response must begin exactly with: {_PART2_MARKER}"""

    return call_api(prompt, api_key, max_tokens=3000, feature="Profile Update", model=model)


def apply_profile_update(new_part2: str) -> None:
    """Write the approved profile text back to the knowledge base and clear the cache."""
    if not new_part2.strip().startswith(_PART2_MARKER):
        raise ValueError(
            "Proposed text does not begin with the expected Part 2 marker — "
            "it may have been corrupted. Discard and try again."
        )
    _replace_part2(new_part2)
    clear_gt7_cache()
