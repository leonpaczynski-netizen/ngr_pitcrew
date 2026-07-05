"""Persistent per-race-config setup history.

Stores AI-generated setup builds, analysis results, and driver-feeling
fixes keyed by config_id.  Entries are fed back into AI prompts so every
call is aware of what has been tried for this specific car/track/race-length
combination — preventing the AI from recommending changes that were already
applied and helping it build on previous iterations.

Group 42 — legacy_unknown treatment
-------------------------------------
Entries with a validation_status that is absent, None, or unrecognised
(not in APPROVED_STATUSES and not a known non-approved status) are labelled
LEGACY_UNKNOWN.  These are display-only — they must never be applied as
actionable recommendations.

Backend hook: is_legacy_unknown(validation_status) -> bool
  Returns True when the status indicates an unknown/pre-validation-gate entry.
  Frontend-builder wires this to the UI; the backend only exposes the hook.

Known non-approved statuses (routed to _rejected_ bucket but recognised):
  "ai_audit_rejected_advisory", "validation_failed", "retry_failed",
  "blocked_no_safe_recommendation".
"""
from __future__ import annotations

import json
import threading
from datetime import datetime
from pathlib import Path

# Import APPROVED_STATUSES from _setup_constants to avoid duplicating the frozenset.
# setup_history is a data-layer module with no dependency on strategy/, so this
# import is clean (no circular risk).
from strategy._setup_constants import APPROVED_STATUSES  # noqa: F401 — re-exported

_HISTORY_PATH = Path(__file__).parent / "setup_history.json"
_lock = threading.Lock()
_MAX_ENTRIES_PER_CONFIG = 20

# Key prefix for the rejected/diagnostic bucket — entries with non-approved statuses
# are written here so they never appear as the current recommendation but are still
# visible for debugging.
_REJECTED_KEY_PREFIX = "_rejected_"

# ---------------------------------------------------------------------------
# Group 42 — legacy_unknown treatment
# ---------------------------------------------------------------------------

# Statuses that are explicitly non-approved but recognised (routed to _rejected_).
_KNOWN_NON_APPROVED_STATUSES: frozenset[str] = frozenset({
    "ai_audit_rejected_advisory",
    "validation_failed",
    "retry_failed",
    "blocked_no_safe_recommendation",
    "generated",
    "validation_failed",
    "retry_requested",
    # Group 41 status strings
    "proposed",
})

# Sentinel string for entries with absent/unrecognised validation_status.
LEGACY_UNKNOWN: str = "legacy_unknown"


def is_legacy_unknown(validation_status: "str | None") -> bool:
    """Return True when validation_status is absent, None, or unrecognised.

    An entry is legacy_unknown when it was saved before the engineering-
    validation-gate (Group 41) or before the rule-first pipeline (Group 42)
    and therefore has no reliable status to act on.

    legacy_unknown entries are DISPLAY-ONLY — they must never be applied as
    actionable recommendations.

    Frontend hook: call this function when rendering history entries to decide
    whether to surface an 'apply' button or a 'legacy — cannot apply' banner.
    """
    if not validation_status:
        return True
    if validation_status in APPROVED_STATUSES:
        return False
    if validation_status in _KNOWN_NON_APPROVED_STATUSES:
        return False
    # Unknown / unrecognised status → treat as legacy
    return True


def normalise_validation_status(entry: dict) -> str:
    """Return the effective validation_status for a history entry.

    Applies the legacy_unknown treatment: entries with absent or unrecognised
    status are returned as LEGACY_UNKNOWN.  All other statuses are returned
    as-is.

    Parameters
    ----------
    entry : A history entry dict (as stored by save_entry).

    Returns
    -------
    str — one of: LEGACY_UNKNOWN, an APPROVED_STATUSES value, or a known
          non-approved status string.
    """
    vs = entry.get("validation_status") or ""
    if is_legacy_unknown(vs):
        return LEGACY_UNKNOWN
    return vs


def _load_all() -> dict:
    try:
        return json.loads(_HISTORY_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_all(data: dict) -> None:
    _HISTORY_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


# Fixed label vocabulary for setup history entries
VALID_LABELS = frozenset({
    "liked", "hated", "neutral",
    "applied", "not_applied",
    "improved", "made_worse",
})


def save_entry(
    config_id: str,
    car: str,
    track: str,
    entry: dict,
    labels: "list[str] | None" = None,
    driver_feedback: str = "",
    validation_status: str = "",
) -> None:
    """Append one history entry for this config_id.

    entry dict keys (all optional except 'type'):
      type         : "build_qual" | "build_race" | "analyse_setup" | "feeling_fix"
      setup_snapshot : dict of setup values (for build types)
      reasoning    : str (for build types)
      shift_rpm    : int (for build types) — legacy; max(shift_rpm_qual, shift_rpm_race)
      shift_rpm_qual : int (for build types) — upshift RPM for qualifying
      shift_rpm_race : int (for build types) — upshift RPM for race
      analysis     : str (summary text from advisor)
      changes      : list of {"setting", "from", "to", "why"} dicts
      feeling      : str (driver description, for feeling_fix type)

    New optional params (backward-compatible):
      labels            : list of label strings from VALID_LABELS (any invalid labels silently dropped)
      driver_feedback   : free-text driver outcome description (empty = not provided)
      validation_status : SetupRecommendationResult.status string.
                          When provided AND not in APPROVED_STATUSES, the entry is written
                          to a separate diagnostic bucket (key prefix "_rejected_") so it
                          never appears as the current recommendation.  Approved statuses
                          write to the primary bucket as before.
    """
    if not config_id:
        return
    entry = dict(entry)
    entry["ts"] = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    # Attach labels (filter to valid vocabulary)
    if labels:
        valid = [lbl for lbl in labels if lbl in VALID_LABELS]
        if valid:
            entry["labels"] = valid
    # Attach driver feedback
    if driver_feedback:
        entry["driver_feedback"] = driver_feedback.strip()
    # Attach validation status for audit trail
    if validation_status:
        entry["validation_status"] = validation_status

    # Route non-approved statuses to the rejected diagnostic bucket
    _use_config_id = config_id
    if validation_status and validation_status not in APPROVED_STATUSES:
        _use_config_id = f"{_REJECTED_KEY_PREFIX}{config_id}"

    with _lock:
        data = _load_all()
        cfg = data.setdefault(_use_config_id, {"car": car, "track": track, "entries": []})
        cfg["car"] = car
        cfg["track"] = track
        cfg.setdefault("entries", []).append(entry)
        if len(cfg["entries"]) > _MAX_ENTRIES_PER_CONFIG:
            cfg["entries"] = cfg["entries"][-_MAX_ENTRIES_PER_CONFIG:]
        _save_all(data)


def load_history(config_id: str, max_entries: int = 8) -> list[dict]:
    """Return the most recent entries for this config_id (oldest first)."""
    if not config_id:
        return []
    with _lock:
        data = _load_all()
    return data.get(config_id, {}).get("entries", [])[-max_entries:]


def format_for_prompt(config_id: str, max_entries: int = 5) -> str:
    """Return a formatted block describing past AI setup work for this race config.

    Injected into strategy and analysis prompts so the AI is aware of every
    setup change that has already been tried or recommended.

    Entries with 'labels' key:
      - "hated" label -> emits "DRIVER HATED: <settings/changes>" + directive not to repeat.
      - "liked" label -> emits "DRIVER LIKED: ..." + directive to prefer similar changes.
    A single "For this driver, subjective confidence is a performance variable." line is
    emitted once (at the top) whenever any labelled entry exists.
    """
    entries = load_history(config_id, max_entries)
    if not entries:
        return ""

    # Check whether any entry carries labels — if so, emit subjective-confidence note.
    _any_labelled = any(e.get("labels") for e in entries)

    lines: list[str] = [
        "## Setup history for this car/track/race-length (most recent last)",
        "The driver has already applied or considered these AI recommendations. "
        "Do not re-recommend changes already listed here unless reverting them "
        "is now the correct call, and explain why.",
    ]
    if _any_labelled:
        lines.append(
            "For this driver, subjective confidence is a performance variable."
        )

    for e in entries:
        ts = e.get("ts", "")[:16].replace("T", " ")
        t = e.get("type", "unknown")
        entry_labels = e.get("labels") or []
        driver_feedback = e.get("driver_feedback", "")

        if t in ("build_qual", "build_race"):
            session = "Qualifying" if t == "build_qual" else "Race"
            lines.append(f"\n[{ts}] AI Build Setup — {session}")
            s = e.get("setup_snapshot") or {}
            if s:
                lines.append(
                    f"  Springs F/R: {s.get('springs_front','?')}/{s.get('springs_rear','?')} Hz  "
                    f"  ARB F/R: {s.get('arb_front','?')}/{s.get('arb_rear','?')}  "
                    f"  Dampers comp/ext F: {s.get('dampers_front_comp','?')}/{s.get('dampers_front_ext','?')}  "
                    f"  R: {s.get('dampers_rear_comp','?')}/{s.get('dampers_rear_ext','?')}"
                )
                # Camber is always rendered as a positive value (abs) regardless of
                # how it was stored — old entries may carry negative values under the
                # previous convention.
                _cf_raw = s.get("camber_front")
                _cr_raw = s.get("camber_rear")
                _cf = abs(float(_cf_raw)) if _cf_raw is not None else "?"
                _cr = abs(float(_cr_raw)) if _cr_raw is not None else "?"
                lines.append(
                    f"  Camber F/R: {_cf}/{_cr}°  "
                    f"  Toe F/R: {s.get('toe_front','?')}/{s.get('toe_rear','?')}°"
                )
                # Display shift RPM: prefer new per-session fields; fall back to legacy.
                _srq = e.get("shift_rpm_qual")
                _srr = e.get("shift_rpm_race")
                if _srq is not None or _srr is not None:
                    _shift_str = f"Shift RPM qual/race: {_srq or 0}/{_srr or 0}"
                else:
                    _shift_str = f"Shift RPM: {e.get('shift_rpm', '?')}"
                lines.append(
                    f"  LSD init/accel/decel: {s.get('lsd_initial','?')}/{s.get('lsd_accel','?')}/{s.get('lsd_decel','?')}  "
                    f"  Brake bias: {s.get('brake_bias','?')}  "
                    f"  Restrictor: {s.get('power_restrictor','?')}%  "
                    f"  {_shift_str}"
                )
            if e.get("reasoning"):
                reasoning_preview = str(e["reasoning"])[:400]
                lines.append(f"  Reasoning: {reasoning_preview}")

        elif t == "analyse_setup":
            lines.append(f"\n[{ts}] Analyse Setup with AI")
            if e.get("analysis"):
                lines.append(f"  {str(e['analysis'])[:250]}")
            for ch in (e.get("changes") or [])[:6]:
                lines.append(
                    f"  → {ch.get('setting','?')}: {ch.get('from','?')} → {ch.get('to','?')}"
                    + (f"  ({ch.get('why','')})" if ch.get("why") else "")
                )

        elif t == "feeling_fix":
            lines.append(f"\n[{ts}] Ask AI for Fix")
            if e.get("feeling"):
                lines.append(f"  Driver: \"{str(e['feeling'])[:120]}\"")
            for ch in (e.get("changes") or [])[:6]:
                lines.append(
                    f"  → {ch.get('setting','?')}: {ch.get('from','?')} → {ch.get('to','?')}"
                    + (f"  ({ch.get('why','')})" if ch.get("why") else "")
                )

        # Label directives — appended after the entry body
        if "hated" in entry_labels:
            # Summarise what was hated: prefer changes, fall back to type
            _hated_desc = ""
            _ch_list = e.get("changes") or []
            if _ch_list:
                _hated_desc = "; ".join(
                    f"{c.get('setting','?')} → {c.get('to','?')}"
                    for c in _ch_list[:4]
                )
            if not _hated_desc and e.get("setup_snapshot"):
                _snap = e["setup_snapshot"]
                _hated_desc = f"build snapshot springs {_snap.get('springs_front','?')}/{_snap.get('springs_rear','?')} Hz"
            lines.append(
                f"  DRIVER HATED: {_hated_desc or 'this setup/change'}"
            )
            lines.append(
                "  Do not repeat changes previously marked as hated unless "
                "the situation is materially different."
            )
        elif "liked" in entry_labels:
            _liked_desc = ""
            _ch_list = e.get("changes") or []
            if _ch_list:
                _liked_desc = "; ".join(
                    f"{c.get('setting','?')} → {c.get('to','?')}"
                    for c in _ch_list[:4]
                )
            if not _liked_desc and e.get("setup_snapshot"):
                _snap = e["setup_snapshot"]
                _liked_desc = f"build snapshot springs {_snap.get('springs_front','?')}/{_snap.get('springs_rear','?')} Hz"
            lines.append(
                f"  DRIVER LIKED: {_liked_desc or 'this setup/change'}"
            )
            lines.append(
                "  Prefer changes that historically improved this driver's "
                "confidence and telemetry."
            )

        if driver_feedback:
            lines.append(f"  Driver feedback: \"{driver_feedback[:200]}\"")

    return "\n".join(lines)
