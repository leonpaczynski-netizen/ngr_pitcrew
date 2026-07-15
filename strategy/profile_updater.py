"""Dynamic driver profile — deterministic stats generation and profile edits.

Capabilities:
  save_stats_doc(db)          — recompute driver_stats.md from the session DB
  apply_profile_update(text)  — write approved text back to the knowledge base
"""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from data.session_db import ms_to_str

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
# Profile edit (deterministic — user-authored text only)
# ---------------------------------------------------------------------------

def apply_profile_update(new_part2: str) -> None:
    """Write approved profile text back to the knowledge base.

    The text is user-authored/reviewed; this function only validates the
    Part 2 marker and persists it, preserving Part 1 exactly.
    """
    if not new_part2.strip().startswith(_PART2_MARKER):
        raise ValueError(
            "Proposed text does not begin with the expected Part 2 marker — "
            "it may have been corrupted. Discard and try again."
        )
    _replace_part2(new_part2)
