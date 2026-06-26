"""Shared Claude API client and prompt utilities for strategy modules.

Single source of truth for:
  - API URL and model name
  - GT7 tuning reference loader (cached)
  - HTTP call to Claude API
  - Canonical setup formatting for AI prompts
  - AI call logging (AILogEntry + hook)
"""
from __future__ import annotations

import datetime as _dt
import json as _json
import os
import time as _time
from dataclasses import dataclass, field as _dc_field
from pathlib import Path
from typing import Optional

_API_URL       = "https://api.anthropic.com/v1/messages"
_DEFAULT_MODEL = "claude-opus-4-8"

# Opus 4.8 pricing (USD per token)
_COST_INPUT_PER_TOKEN  = 5.0  / 1_000_000
_COST_OUTPUT_PER_TOKEN = 25.0 / 1_000_000

# ---------------------------------------------------------------------------
# AI call log entry
# ---------------------------------------------------------------------------

@dataclass
class AILogEntry:
    timestamp: str          # ISO-8601 UTC
    feature: str            # "Strategy Analysis", "Driver Coaching", etc.
    model: str
    prompt: str
    structured_payload: str # JSON string of key input data
    response: str
    success: bool
    duration_ms: int
    prompt_tokens: int
    response_tokens: int
    estimated_cost: float   # USD
    error_msg: str
    validation_warnings: list = _dc_field(default_factory=list)
    car_id: int = 0    # DB id of the car at the time of the call; 0 if unknown
    track: str = ""    # track name at the time of the call; "" if unknown
    session_id: int = 0

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.response_tokens


# ---------------------------------------------------------------------------
# Log hook — registered by main.py at startup
# ---------------------------------------------------------------------------

_log_hook = None   # callable(AILogEntry) | None


def set_log_hook(callback) -> None:
    """Register a callback fired after every AI call (success or failure).

    The callback is invoked on the worker thread that made the call.
    Qt signal emissions from the callback are automatically queued to the UI
    thread via PyQt's cross-thread signal mechanism.
    """
    global _log_hook
    _log_hook = callback


def _fire_log_hook(entry: AILogEntry) -> None:
    if _log_hook is not None:
        try:
            _log_hook(entry)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Debug / dry-run mode
# ---------------------------------------------------------------------------
# When True every call_api() invocation prints the full prompt to stdout
# (visible in the app's Debug tab) and raises RuntimeError instead of hitting
# the API.  Flip this back to False — or unset the env var — to restore live
# calls.  Reverts in one edit.
#
# Enable via code:  set _AI_DEBUG = True below
# Enable via shell: set GT7_AI_DEBUG=1  (before launching main.py)
_AI_DEBUG: bool = os.getenv("GT7_AI_DEBUG", "") == "1"

_GT7_REF_CACHE: Optional[str] = None   # static knowledge base only
_STATS_PATH = Path(__file__).parent.parent / "knowledge" / "driver_stats.md"


def load_gt7_reference() -> str:
    """Load the static knowledge base and append the latest dynamic driver stats.

    The static file (gt7_tuning_reference.md) is cached after first read.
    The stats file (driver_stats.md) is read fresh every call so it always
    reflects the most recently recorded sessions.
    """
    global _GT7_REF_CACHE
    if _GT7_REF_CACHE is None:
        try:
            ref_path = Path(__file__).parent.parent / "knowledge" / "gt7_tuning_reference.md"
            _GT7_REF_CACHE = ref_path.read_text(encoding="utf-8")
        except Exception:
            _GT7_REF_CACHE = ""

    try:
        stats = _STATS_PATH.read_text(encoding="utf-8")
        if stats.strip():
            return _GT7_REF_CACHE + "\n\n---\n\n" + stats
    except FileNotFoundError:
        pass
    return _GT7_REF_CACHE


def clear_gt7_cache() -> None:
    """Force reload of the static knowledge base on the next call.

    Call this after the driver profile (Part 2) has been edited so the
    updated text is picked up immediately.
    """
    global _GT7_REF_CACHE
    _GT7_REF_CACHE = None


def call_api(
    prompt: str,
    api_key: str,
    max_tokens: int = 2048,
    system: str = "",
    feature: str = "Unknown",
    structured_payload: dict | None = None,
    model: str | None = None,
    car_id: int = 0,
    track: str = "",
    session_id: int = 0,
) -> str:
    """POST a prompt to the Claude API and return the response text.

    When _AI_DEBUG is True the prompt is printed to stdout (Debug tab) and
    a RuntimeError is raised instead of making a real API call.

    Every call (success or failure) fires the registered log hook with an
    AILogEntry so the UI can display it in the AI Log tab and persist it
    to the database.
    """
    effective_model = (model.strip() if model and model.strip() else None) or _DEFAULT_MODEL

    if _AI_DEBUG:
        _sep = "=" * 72
        print(f"\n{_sep}")
        print(f"[AI_DEBUG] API call intercepted  (max_tokens={max_tokens})")
        print(_sep)
        print(prompt)
        print(_sep + "\n")
        _fire_log_hook(AILogEntry(
            timestamp=_dt.datetime.now().isoformat(),
            feature=feature,
            model=effective_model,
            prompt=prompt,
            structured_payload=_json.dumps(structured_payload or {}, default=str),
            response="[AI_DEBUG dry-run — no API call made]",
            success=False,
            duration_ms=0,
            prompt_tokens=0,
            response_tokens=0,
            estimated_cost=0.0,
            error_msg="AI_DEBUG mode active — prompt intercepted, no API call made",
            car_id=car_id,
            track=track,
            session_id=session_id,
        ))
        raise RuntimeError(
            "AI_DEBUG mode — prompt printed to Debug tab. "
            "No API call was made.\n"
            "To restore live calls: set _AI_DEBUG=False in strategy/_ai_client.py "
            "or unset GT7_AI_DEBUG."
        )

    try:
        import requests as _req
    except ImportError:
        raise RuntimeError("The 'requests' library is required — pip install requests")
    if not api_key.strip():
        raise ValueError("No Anthropic API key configured in Settings or config.json")

    headers = {
        "x-api-key": api_key.strip(),
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    body: dict = {
        "model": effective_model,
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": prompt}],
    }
    if system:
        body["system"] = system

    t0 = _time.monotonic()
    payload_str = _json.dumps(structured_payload or {}, default=str)

    try:
        resp = _req.post(_API_URL, headers=headers, json=body, timeout=120)
        resp.raise_for_status()
        data = resp.json()
        text: str = data["content"][0]["text"]

        duration_ms = int((_time.monotonic() - t0) * 1000)
        usage = data.get("usage", {})
        prompt_tokens   = usage.get("input_tokens", 0)
        response_tokens = usage.get("output_tokens", 0)
        cost = prompt_tokens * _COST_INPUT_PER_TOKEN + response_tokens * _COST_OUTPUT_PER_TOKEN

        entry = AILogEntry(
            timestamp=_dt.datetime.now().isoformat(),
            feature=feature,
            model=effective_model,
            prompt=prompt,
            structured_payload=payload_str,
            response=text,
            success=True,
            duration_ms=duration_ms,
            prompt_tokens=prompt_tokens,
            response_tokens=response_tokens,
            estimated_cost=cost,
            error_msg="",
            car_id=car_id,
            track=track,
            session_id=session_id,
        )
        _fire_log_hook(entry)
        print(
            f"[AI] {feature} | ✓ | {duration_ms}ms | "
            f"{prompt_tokens + response_tokens} tokens | ${cost:.4f}"
        )
        return text

    except Exception as exc:
        duration_ms = int((_time.monotonic() - t0) * 1000)
        entry = AILogEntry(
            timestamp=_dt.datetime.now().isoformat(),
            feature=feature,
            model=effective_model,
            prompt=prompt,
            structured_payload=payload_str,
            response="",
            success=False,
            duration_ms=duration_ms,
            prompt_tokens=0,
            response_tokens=0,
            estimated_cost=0.0,
            error_msg=str(exc),
            car_id=car_id,
            track=track,
            session_id=session_id,
        )
        _fire_log_hook(entry)
        print(f"[AI] {feature} | ✗ | {duration_ms}ms | error: {exc}")
        raise


def format_gear_ratios(gear_ratios: list) -> str:
    """Format a gear ratio list for inclusion in an AI prompt."""
    if not gear_ratios:
        return "not captured"
    parts = [f"G{i+1}: {r:.3f}" for i, r in enumerate(gear_ratios) if r is not None and r > 0.0]
    return ", ".join(parts) if parts else "not captured"


def format_setup_for_prompt(setup: dict) -> str:
    """Return a canonical text block describing a car setup for AI prompts.

    This is the single authoritative representation of a GT7 car setup that
    is injected into every AI prompt (race strategy, practice analysis, setup
    advice, driver feeling response). Keeping it in one place ensures that
    adding a new setup field automatically propagates to all prompts.
    """
    gear_str = format_gear_ratios(setup.get("gear_ratios", []))
    lines = [
        f"  Car: {setup.get('name', 'Unknown')}",
        f"  Track: {setup.get('track', 'Unknown')}",
        f"  Condition: {setup.get('condition', 'Dry')}",
        f"  Setup Type: {setup.get('setup_type', setup.get('session', 'Race Setup'))}",
        f"  Ride Height F/R: {setup.get('ride_height_front', '?')}/{setup.get('ride_height_rear', '?')} mm",
        f"  Springs F/R: {setup.get('springs_front', '?')}/{setup.get('springs_rear', '?')} N/mm",
        f"  Dampers Comp F/R: {setup.get('dampers_front_comp', '?')}/{setup.get('dampers_rear_comp', '?')}",
        f"  Dampers Ext F/R: {setup.get('dampers_front_ext', '?')}/{setup.get('dampers_rear_ext', '?')}",
        f"  ARB F/R: {setup.get('arb_front', '?')}/{setup.get('arb_rear', '?')}",
        f"  Camber F/R: {setup.get('camber_front', '?')}/{setup.get('camber_rear', '?')}°",
        f"  Toe F/R: {setup.get('toe_front', '?')}/{setup.get('toe_rear', '?')}°",
        f"  Aero F/R: {setup.get('aero_front', '?')}/{setup.get('aero_rear', '?')} kg",
        f"  LSD Initial/Accel/Decel: {setup.get('lsd_initial', '?')}/{setup.get('lsd_accel', '?')}/{setup.get('lsd_decel', '?')}",
        f"  Brake bias: {setup.get('brake_bias', setup.get('brake_bias_front', '?'))} (GT7: −5 = more front, +5 = more rear)",
        f"  Ballast: {setup.get('ballast_kg', 0)} kg, position {setup.get('ballast_position', 0)} (−50 rear … +50 front)",
        f"  Power restrictor: {setup.get('power_restrictor', 100)}%",
        f"  Final drive: {setup.get('final_drive') or 'not set'}",
        f"  Gear ratios (G1→Gn): {gear_str}",
        f"  Top speed target: {setup.get('transmission_max_speed_kmh', '?')} km/h",
        f"  Notes: {setup.get('notes', 'none')}",
    ]
    return "\n".join(lines)
