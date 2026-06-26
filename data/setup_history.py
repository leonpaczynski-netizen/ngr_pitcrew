"""Persistent per-race-config setup history.

Stores AI-generated setup builds, analysis results, and driver-feeling
fixes keyed by config_id.  Entries are fed back into AI prompts so every
call is aware of what has been tried for this specific car/track/race-length
combination — preventing the AI from recommending changes that were already
applied and helping it build on previous iterations.
"""
from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path

_HISTORY_PATH = Path(__file__).parent / "setup_history.json"
_lock = threading.Lock()
_MAX_ENTRIES_PER_CONFIG = 20


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


def save_entry(
    config_id: str,
    car: str,
    track: str,
    entry: dict,
) -> None:
    """Append one history entry for this config_id.

    entry dict keys (all optional except 'type'):
      type         : "build_qual" | "build_race" | "analyse_setup" | "feeling_fix"
      setup_snapshot : dict of setup values (for build types)
      reasoning    : str (for build types)
      shift_rpm    : int (for build types)
      analysis     : str (summary text from advisor)
      changes      : list of {"setting", "from", "to", "why"} dicts
      feeling      : str (driver description, for feeling_fix type)
    """
    if not config_id:
        return
    entry = dict(entry)
    entry["ts"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    with _lock:
        data = _load_all()
        cfg = data.setdefault(config_id, {"car": car, "track": track, "entries": []})
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
    """
    entries = load_history(config_id, max_entries)
    if not entries:
        return ""

    lines: list[str] = [
        "## Setup history for this car/track/race-length (most recent last)",
        "The driver has already applied or considered these AI recommendations. "
        "Do not re-recommend changes already listed here unless reverting them "
        "is now the correct call, and explain why.",
    ]
    for e in entries:
        ts = e.get("ts", "")[:16].replace("T", " ")
        t = e.get("type", "unknown")

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
                lines.append(
                    f"  LSD init/accel/decel: {s.get('lsd_initial','?')}/{s.get('lsd_accel','?')}/{s.get('lsd_decel','?')}  "
                    f"  Brake bias: {s.get('brake_bias','?')}  "
                    f"  Restrictor: {s.get('power_restrictor','?')}%  "
                    f"  Shift RPM: {e.get('shift_rpm', '?')}"
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

    return "\n".join(lines)
