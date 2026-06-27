"""Driving coach and setup advisor powered by telemetry data + Claude API.

build_last_lap_response()  — rule-based, instant, no API.
build_coaching_response()  — Claude API, uses last 3 laps + session history from DB.
build_setup_advice_response(setup) — Claude API, maps telemetry + DB history to setup changes.
"""
from __future__ import annotations

import json as _json
import re as _re
from statistics import mean
from typing import Optional, TYPE_CHECKING

from data.session_db import ms_to_str
from strategy._ai_client import call_api, format_setup_for_prompt, load_gt7_reference
from strategy._rec_parser import parse_recommendations_from_response
from strategy.setup_ranges import resolve_ranges
from ui.gt7_data import build_track_context

_ALL_TUNING_CATS = [
    "tyres", "brake_balance", "suspension", "differential",
    "aero", "transmission", "power", "ballast", "steering", "nitrous",
]


def _tuning_constraint_block(
    allowed_tuning: "list[str] | None",
    tuning_locked: bool,
) -> str:
    if tuning_locked:
        return (
            "\n## EVENT RULES — TUNING LOCKED\n"
            "Do NOT suggest any setup changes. Focus on driving technique and tyre choices only.\n\n"
        )
    if allowed_tuning:
        locked = [c for c in _ALL_TUNING_CATS if c not in allowed_tuning]
        return (
            f"\n## EVENT TUNING RESTRICTIONS\n"
            f"Allowed to modify: {', '.join(allowed_tuning)}\n"
            f"LOCKED (do not recommend changes): {', '.join(locked)}\n"
            f"Only recommend changes to ALLOWED areas.\n\n"
        )
    return ""

# ---------------------------------------------------------------------------
# Canonical param keys recognised by the combined-setup response normaliser.
# Must match the setup_fields key list given in _build_combined_prompt and the
# keys used by setup_ranges.GENERIC_DEFAULTS / _parse_setup_recommendation.
# ---------------------------------------------------------------------------
_CANONICAL_SETUP_PARAMS: frozenset[str] = frozenset({
    "ride_height_front", "ride_height_rear",
    "springs_front", "springs_rear",
    "dampers_front_comp", "dampers_front_ext",
    "dampers_rear_comp", "dampers_rear_ext",
    "arb_front", "arb_rear",
    "camber_front", "camber_rear",
    "toe_front", "toe_rear",
    "aero_front", "aero_rear",
    "lsd_initial", "lsd_accel", "lsd_decel",
    "lsd_front_initial", "lsd_front_accel", "lsd_front_decel",
    "brake_bias",
    "ballast_kg", "ballast_position",
    "power_restrictor",
    "transmission_max_speed_kmh",
})

# Aliases: legacy/alternate names the AI may produce → canonical key
_PARAM_ALIASES: dict[str, str] = {
    "brake_bias_front": "brake_bias",
}


def _slug(text: str) -> str:
    """Strip all non-alphanumeric characters and lowercase — for fuzzy matching."""
    return _re.sub(r"[^a-z0-9]", "", text.lower())


# Pre-built slug → canonical key map for fast matching
_SLUG_TO_CANONICAL: dict[str, str] = {
    _slug(k): k for k in _CANONICAL_SETUP_PARAMS
}


def _resolve_field_key(field: str, setting: str) -> str | None:
    """Return the canonical param key for a change item, or None if unresolvable.

    Resolution order:
    1. ``field`` is already a recognised canonical key — return as-is.
    2. ``field`` is a known alias — return the canonical key.
    3. Slug-match ``field`` against all canonical keys.
    4. Slug-match ``setting`` (the human label) against all canonical keys.
    """
    if field and field in _CANONICAL_SETUP_PARAMS:
        return field
    if field and field in _PARAM_ALIASES:
        return _PARAM_ALIASES[field]
    # Slug-match field value
    if field:
        s = _slug(field)
        if s in _SLUG_TO_CANONICAL:
            return _SLUG_TO_CANONICAL[s]
        for k_slug, k in _SLUG_TO_CANONICAL.items():
            if k_slug in s or s in k_slug:
                return k
    # Slug-match the human-readable setting label
    if setting:
        s = _slug(str(setting))
        if s in _SLUG_TO_CANONICAL:
            return _SLUG_TO_CANONICAL[s]
        for k_slug, k in _SLUG_TO_CANONICAL.items():
            if k_slug in s or s in k_slug:
                return k
    return None


def _normalise_changes(
    changes: list[dict],
    setup_fields: dict[str, object],
    car_name: str,
) -> list[dict]:
    """Enrich each change item with resolved ``field`` and ``to_clamped`` keys.

    Parameters
    ----------
    changes:
        Raw list of change dicts from the AI JSON (mutated in-place copies).
    setup_fields:
        The ``setup_fields`` dict from the same AI response (already clamped
        by the prompt's numeric-value constraint, used as preferred source).
    car_name:
        Used with resolve_ranges to obtain per-car bounds for ``to_clamped``.

    Returns
    -------
    A new list of dicts with ``field`` (str | None) and ``to_clamped`` added.
    Every other key is preserved unchanged.

    Contract for the frontend
    -------------------------
    - ``ch["field"]``      — canonical param key (str) or None if unresolvable.
    - ``ch["to"]``         — raw AI recommended value (string or number, unchanged).
    - ``ch["to_clamped"]`` — numeric value clamped to per-car range, or the raw
                             ``to`` value if the field is unresolvable or non-numeric.
    """
    ranges = resolve_ranges(car_name)
    result: list[dict] = []
    for ch in changes:
        ch = dict(ch)  # copy; never mutate caller's data
        raw_field   = str(ch.get("field", "")).strip()
        raw_setting = str(ch.get("setting", "")).strip()
        resolved    = _resolve_field_key(raw_field, raw_setting)
        ch["field"] = resolved

        # Derive to_clamped: prefer the value from setup_fields (already
        # instructed to be numeric and in-range); fall back to clamping
        # ch["to"] against the resolved range.
        raw_to = ch.get("to")
        to_clamped: object = raw_to
        if resolved is not None:
            # If setup_fields carries this param, use that numeric value
            # (it matches what the apply-button path will use).
            if resolved in setup_fields:
                to_clamped = setup_fields[resolved]
            elif raw_to is not None and resolved in ranges:
                try:
                    num = float(raw_to)
                    lo, hi = ranges[resolved]
                    to_clamped = max(lo, min(hi, num))
                    # Preserve int type for integer params
                    if isinstance(lo, int) and isinstance(hi, int):
                        to_clamped = int(to_clamped)
                except (TypeError, ValueError):
                    pass  # non-numeric "to" — leave as-is
        ch["to_clamped"] = to_clamped
        result.append(ch)
    return result


if TYPE_CHECKING:
    from telemetry.recorder import LapTelemetryRecorder, LapStats
    from data.session_db import SessionDB


def _delta_str(ms: int, best_ms: int) -> str:
    if best_ms <= 0:
        return ""
    d = (ms - best_ms) / 1000.0
    return f" ({d:+.3f}s from best)" if d != 0 else " (best lap)"


class DrivingAdvisor:
    """Builds PTT driving coach responses from lap telemetry recordings."""

    def __init__(self, recorder, tracker, config, db=None, car_id_ref=None, session_id_getter=None) -> None:
        self._recorder    = recorder
        self._tracker     = tracker
        self._config      = config
        self._db: Optional["SessionDB"] = db
        self._car_id_ref  = car_id_ref or [0]
        self._event_ctx: dict = {}
        self._session_id_getter = session_id_getter if callable(session_id_getter) else (lambda: 0)

    # ------------------------------------------------------------------
    # Rule-based (instant)
    # ------------------------------------------------------------------

    def build_last_lap_response(self) -> str:
        lap = self._recorder.last_lap()
        if lap is None:
            return ("No lap data recorded yet. "
                    "Complete a lap with the car on track first.")

        best = self._recorder.best_lap()
        best_ms = best.lap_time_ms if best and best.lap_num != lap.lap_num else 0

        time_str  = ms_to_str(lap.lap_time_ms)
        delta_str = _delta_str(lap.lap_time_ms, best_ms)

        if lap.lock_up_count == 0:
            lock_str = "No lock-ups"
        elif lap.lock_up_count == 1:
            lock_str = "1 lock-up detected"
        else:
            lock_str = f"{lap.lock_up_count} lock-ups detected"

        if lap.wheelspin_count == 0:
            spin_str = "no wheelspin"
        elif lap.wheelspin_count == 1:
            spin_str = "1 wheelspin event"
        else:
            spin_str = f"{lap.wheelspin_count} wheelspin events"

        if lap.brake_consistency_m < 0:
            consist_str = "braking consistency could not be measured"
        elif lap.brake_consistency_m < 10:
            consist_str = f"braking very consistent ({lap.brake_consistency_m:.0f}m variation)"
        elif lap.brake_consistency_m < 25:
            consist_str = f"braking reasonably consistent ({lap.brake_consistency_m:.0f}m variation)"
        else:
            consist_str = f"braking inconsistent ({lap.brake_consistency_m:.0f}m variation — focus on reference points)"

        # Oversteer summary
        os_total = lap.oversteer_count
        os_ton   = lap.oversteer_throttle_on_count
        if os_total == 0:
            os_str = "no snap oversteer events"
        else:
            os_entry = os_total - os_ton
            os_str = (f"{os_total} oversteer event{'s' if os_total != 1 else ''} "
                      f"({os_ton} throttle-on, {os_entry} entry)")

        extras = []
        if lap.kerb_count:
            extras.append(f"{lap.kerb_count} hard kerb hit{'s' if lap.kerb_count != 1 else ''}")
        if lap.bottoming_count:
            extras.append(f"{lap.bottoming_count} bottoming event{'s' if lap.bottoming_count != 1 else ''}")
        if lap.snap_throttle_count:
            extras.append(f"{lap.snap_throttle_count} snap throttle application{'s' if lap.snap_throttle_count != 1 else ''}")
        extra_str = (". " + ", ".join(extras)) if extras else ""

        return (
            f"Lap {lap.lap_num}: {time_str}{delta_str}. "
            f"{lock_str}, {spin_str}, {os_str}. "
            f"{consist_str.capitalize()}. "
            f"Top speed {lap.max_speed_kmh:.0f} km/h, peak lateral G {lap.max_lat_g:.2f}. "
            f"Average throttle {lap.avg_throttle_pct:.0f}%, brake {lap.avg_brake_pct:.0f}%"
            f"{extra_str}."
        )

    # ------------------------------------------------------------------
    # Claude API responses
    # ------------------------------------------------------------------

    def build_coaching_response(
        self, car_name: str = "", car_specs: dict | None = None,
        allowed_tuning: "list[str] | None" = None, tuning_locked: bool = False,
        compound: str = "", corner_issues_summary: str = "",
        live_position=None,
    ) -> str:
        api_key = self._config.get("anthropic", {}).get("api_key", "")
        if not api_key.strip():
            return ("No Anthropic API key set. "
                    "Add your key in the Strategy tab to enable AI coaching.")

        recent = self._recorder.recent_laps(3)
        if not recent:
            return "Not enough laps recorded yet to give coaching advice."

        history_str = self._get_history_context()
        prompt = self._build_coaching_prompt(recent, history_str,
                                             car_name=car_name, car_specs=car_specs or {},
                                             allowed_tuning=allowed_tuning,
                                             tuning_locked=tuning_locked,
                                             compound=compound,
                                             corner_issues_summary=corner_issues_summary,
                                             live_position=live_position)
        _track_da = self._config.get("strategy", {}).get("track", "")
        try:
            _response_text = call_api(prompt, api_key, max_tokens=600,
                                      feature="Driver Coaching",
                                      structured_payload={"lap_count": len(recent),
                                                          "car": car_name,
                                                          "has_setup": False},
                                      model=self._config.get("anthropic", {}).get("model") or None,
                                      car_id=self._car_id_ref[0], track=_track_da)
            if self._db is not None:
                _session_id = self._session_id_getter()
                try:
                    _ai_id = self._db._conn.execute(
                        "SELECT MAX(id) FROM ai_interactions"
                    ).fetchone()[0]
                except Exception:
                    _ai_id = None
                _recs = parse_recommendations_from_response(
                    _response_text, "Driver Coaching",
                    self._car_id_ref[0], _track_da, "",
                    session_id=_session_id, ai_interaction_id=_ai_id,
                )
                if _recs:
                    self._db.insert_setup_recommendations(_recs)
            return _response_text
        except Exception as e:
            return f"Coaching analysis failed: {e}"

    def build_setup_advice_response(
        self, setup_dict: dict, car_name: str = "", car_specs: dict | None = None,
        allowed_tuning: "list[str] | None" = None, tuning_locked: bool = False,
        compound: str = "", corner_issues_summary: str = "",
    ) -> str:
        """Return a JSON string: {"analysis": str, "changes": [{setting,from,to,why}]}."""
        api_key = self._config.get("anthropic", {}).get("api_key", "")
        if not api_key.strip():
            return ("No Anthropic API key set. "
                    "Add your key in the Strategy tab to enable setup advice.")

        recent = self._recorder.recent_laps(5)
        if not recent:
            return "Not enough laps recorded yet. Drive a few laps first."

        history_str = self._get_history_context()
        prompt = self._build_setup_prompt(recent, setup_dict, history_str,
                                          car_name=car_name, car_specs=car_specs or {},
                                          allowed_tuning=allowed_tuning,
                                          tuning_locked=tuning_locked,
                                          compound=compound,
                                          corner_issues_summary=corner_issues_summary)
        _track_da = self._config.get("strategy", {}).get("track", "")
        try:
            _response_text = call_api(prompt, api_key, max_tokens=1000,
                                      feature="Setup Advice",
                                      structured_payload={"lap_count": len(recent),
                                                          "car": car_name,
                                                          "has_setup": bool(setup_dict)},
                                      model=self._config.get("anthropic", {}).get("model") or None,
                                      car_id=self._car_id_ref[0], track=_track_da)
            if self._db is not None:
                _session_id = self._session_id_getter()
                try:
                    _ai_id = self._db._conn.execute(
                        "SELECT MAX(id) FROM ai_interactions"
                    ).fetchone()[0]
                except Exception:
                    _ai_id = None
                _recs = parse_recommendations_from_response(
                    _response_text, "Setup Advice",
                    self._car_id_ref[0], _track_da, "",
                    session_id=_session_id, ai_interaction_id=_ai_id,
                )
                if _recs:
                    self._db.insert_setup_recommendations(_recs)
            return _response_text
        except Exception as e:
            return f"Setup analysis failed: {e}"

    def build_combined_setup_response(
        self, setup_dict: dict, n_laps: int = 5,
        car_name: str = "", car_specs: dict | None = None,
        feeling: str | None = None,
        allowed_tuning: "list[str] | None" = None, tuning_locked: bool = False,
        compound: str = "",
    ) -> str:
        """Return a JSON string: {"analysis": str, "changes": [...], "setup_fields": {...}}.

        Always uses full telemetry. If *feeling* is provided it is included alongside
        telemetry — never sent alone. Uses up to *n_laps* most recent laps from the recorder.
        """
        api_key = self._config.get("anthropic", {}).get("api_key", "")
        if not api_key.strip():
            return ("No Anthropic API key set. "
                    "Add your key in the Strategy tab to enable setup advice.")

        recent = self._recorder.recent_laps(n_laps)
        if not recent:
            return "Not enough laps recorded yet. Drive a few laps first."

        history_str = self._get_history_context()
        prompt = self._build_combined_prompt(
            recent, setup_dict, history_str,
            car_name=car_name, car_specs=car_specs or {},
            feeling=feeling,
            allowed_tuning=allowed_tuning, tuning_locked=tuning_locked,
            compound=compound,
        )
        _track_da = self._config.get("strategy", {}).get("track", "")
        try:
            _response_text = call_api(prompt, api_key, max_tokens=1200,
                                      feature="Combined Setup",
                                      structured_payload={"lap_count": len(recent),
                                                          "car": car_name,
                                                          "has_setup": bool(setup_dict),
                                                          "has_feeling": bool(feeling)},
                                      model=self._config.get("anthropic", {}).get("model") or None,
                                      car_id=self._car_id_ref[0], track=_track_da)
            if self._db is not None:
                _session_id = self._session_id_getter()
                try:
                    _ai_id = self._db._conn.execute(
                        "SELECT MAX(id) FROM ai_interactions"
                    ).fetchone()[0]
                except Exception:
                    _ai_id = None
                _recs = parse_recommendations_from_response(
                    _response_text, "Combined Setup",
                    self._car_id_ref[0], _track_da, "",
                    session_id=_session_id, ai_interaction_id=_ai_id,
                )
                if _recs:
                    self._db.insert_setup_recommendations(_recs)
            # Normalise changes server-side: resolve 'field' key and add
            # 'to_clamped' so the frontend never needs to slug-guess or
            # re-clamp raw AI values.
            try:
                _data = _json.loads(_response_text)
                _raw_changes = _data.get("changes") or []
                _setup_fields = _data.get("setup_fields") or {}
                if isinstance(_raw_changes, list) and _raw_changes:
                    _data["changes"] = _normalise_changes(
                        _raw_changes, _setup_fields, car_name
                    )
                    _response_text = _json.dumps(_data, ensure_ascii=False)
            except Exception:
                pass  # If normalisation fails, return the original text unchanged
            return _response_text
        except Exception as e:
            return f"Setup analysis failed: {e}"

    def build_driver_feeling_response(
        self, feeling_text: str, setup_dict: dict,
        car_name: str = "", car_specs: dict | None = None
    ) -> str:
        """Return a JSON string: {"analysis": str, "changes": [{setting,from,to,why}]}."""
        api_key = self._config.get("anthropic", {}).get("api_key", "")
        if not api_key.strip():
            return ("No Anthropic API key set. "
                    "Add your key in the Strategy tab to enable setup advice.")
        if not feeling_text.strip():
            return "Please describe how the car feels first."

        history_str = self._get_history_context()
        prompt = self._build_feeling_prompt(feeling_text.strip(), setup_dict, history_str,
                                            car_name=car_name, car_specs=car_specs or {})
        _track_da = self._config.get("strategy", {}).get("track", "")
        try:
            _response_text = call_api(prompt, api_key, max_tokens=1000,
                                      feature="Handling Analysis",
                                      structured_payload={"car": car_name,
                                                          "has_setup": bool(setup_dict),
                                                          "feeling_length": len(feeling_text)},
                                      model=self._config.get("anthropic", {}).get("model") or None,
                                      car_id=self._car_id_ref[0], track=_track_da)
            if self._db is not None:
                _session_id = self._session_id_getter()
                try:
                    _ai_id = self._db._conn.execute(
                        "SELECT MAX(id) FROM ai_interactions"
                    ).fetchone()[0]
                except Exception:
                    _ai_id = None
                _recs = parse_recommendations_from_response(
                    _response_text, "Handling Analysis",
                    self._car_id_ref[0], _track_da, "",
                    session_id=_session_id, ai_interaction_id=_ai_id,
                )
                if _recs:
                    self._db.insert_setup_recommendations(_recs)
            # Normalise changes server-side: resolve 'field' key and add
            # 'to_clamped'. The feeling path has no setup_fields dict, so
            # _normalise_changes falls back to range-clamping ch["to"] directly.
            try:
                _data = _json.loads(_response_text)
                _raw_changes = _data.get("changes") or []
                if isinstance(_raw_changes, list) and _raw_changes:
                    _data["changes"] = _normalise_changes(
                        _raw_changes, {}, car_name
                    )
                    _response_text = _json.dumps(_data, ensure_ascii=False)
            except Exception:
                pass  # If normalisation fails, return the original text unchanged
            return _response_text
        except Exception as e:
            return f"Setup advice failed: {e}"

    # ------------------------------------------------------------------
    # History context
    # ------------------------------------------------------------------

    def _get_history_context(self) -> str:
        """Return a formatted history string from the session DB, or empty note."""
        if self._db is None:
            return "(Session database not available — no historical context.)"
        try:
            car_id = int(self._car_id_ref[0]) or 0
            track  = self._config.get("strategy", {}).get("track", "") or ""
            return self._db.format_history_for_prompt(car_id, track)
        except Exception as e:
            return f"(History unavailable: {e})"

    def set_event_context(self, event_dict: dict) -> None:
        self._event_ctx = event_dict or {}

    def _get_event_context_block(self) -> str:
        evt = self._event_ctx
        if not evt:
            return ""
        lines = ["## Event Rules"]
        if evt.get("name"):
            lines.append(f"Event: {evt['name']}")
        track = evt.get("track") or self._config.get("strategy", {}).get("track", "")
        if track:
            lines.append(f"Track: {track}")
        race_type = evt.get("race_type", "")
        laps = evt.get("laps", 0)
        duration = evt.get("duration_mins", 0)
        if race_type == "timed":
            lines.append(f"Race: {duration} minutes, Timed Race")
        elif laps:
            lines.append(f"Race: {laps} laps, Lap Race")
        tyre_wear = float(evt.get("tyre_wear", 1.0))
        fuel_mult = float(evt.get("fuel_mult", 1.0))
        if tyre_wear != 1.0 or fuel_mult != 1.0:
            lines.append(f"Tyre wear: {tyre_wear}x | Fuel: {fuel_mult}x")
        bop    = evt.get("bop", False)
        tuning = evt.get("tuning", True)
        lines.append(f"BoP: {'ON' if bop else 'OFF'} | Tuning: {'Allowed' if tuning else 'Locked'}")
        weather = evt.get("weather", "")
        damage  = evt.get("damage", "")
        if weather or damage:
            lines.append(f"Weather: {weather or 'N/A'} | Damage: {damage or 'None'}")
        req_tyres = evt.get("req_tyres", [])
        if isinstance(req_tyres, list) and req_tyres:
            lines.append(f"Required compounds: {', '.join(req_tyres)}")
        elif isinstance(req_tyres, str) and req_tyres:
            lines.append(f"Required compound: {req_tyres}")
        notes = evt.get("notes", "")
        if notes:
            lines.append(f"Notes: {notes}")
        return "\n".join(lines)

    def _get_driver_feedback_context(self) -> str:
        if self._db is None:
            return ""
        try:
            car_id = int(self._car_id_ref[0]) or 0
            track  = self._config.get("strategy", {}).get("track", "") or ""
            rows   = self._db.get_recent_feedback(car_id, track, limit=5)
            if not rows:
                return ""
            lines = ["## Recent Driver Feedback"]
            for row in rows:
                parts: list[str] = []
                for field in ("corner_entry", "mid_corner", "exit_stability",
                              "rear_braking", "tyre_condition", "fuel_use"):
                    val = row.get(field, "")
                    if val and val != "neutral":
                        parts.append(f"{field.replace('_', ' ')}: {val}")
                free = (row.get("free_text") or "").strip()
                if free:
                    parts.append(f'"{free}"')
                if parts:
                    lines.append("- " + ", ".join(parts))
            return "\n".join(lines) if len(lines) > 1 else ""
        except Exception:
            return ""

    def _get_track_intelligence_context(self) -> str:
        """Return Track Intelligence prompt context for this session's selected track/layout."""
        from strategy.track_context_prompt import get_track_context_for_ai
        sc = self._config.get("strategy", {})
        return get_track_context_for_ai(
            sc.get("track_location_id") or "",
            sc.get("layout_id") or "",
            car_name="",  # no car name available in this scope; callers pass it via build_*_response
        )

    def _get_enriched_issue_context(self, laps: list) -> str:
        """Convert recent LapStats to enriched segment-located issue summary.

        Returns "" if no track/layout IDs are set, no issues detected, or
        enrichment produces no resolved matches (warnings still included).
        Never raises.
        """
        try:
            sc = self._config.get("strategy", {})
            loc_id = sc.get("track_location_id") or ""
            lay_id = sc.get("layout_id") or ""
            if not loc_id or not lay_id:
                return ""
            from data.track_issue_enrichment import (
                issues_from_lap_stats,
                enrich_telemetry_issues,
                summarise_enriched_issues_for_prompt,
            )
            raw_issues = issues_from_lap_stats(laps)
            if not raw_issues:
                return ""
            result = enrich_telemetry_issues(raw_issues, loc_id, lay_id)
            return summarise_enriched_issues_for_prompt(result.enriched_issues)
        except Exception:
            return ""

    def _get_live_segment_context(self, live_position=None) -> str:
        """Return a compact live segment prompt block for the current track position.

        live_position: a LivePosition object (from data.live_segment_resolver),
        or None.  When None, returns "" — live segment context is deferred and
        callers must supply the position explicitly.

        Why deferred at analysis time: coaching/setup prompts are triggered by
        user action (pressing "Analyse"), not by a continuous telemetry frame.
        The caller is responsible for supplying the most recent LivePosition if
        live context is desired.  Absence of a position is not an error.
        """
        try:
            sc = self._config.get("strategy", {})
            loc_id = sc.get("track_location_id") or ""
            lay_id = sc.get("layout_id") or ""
            if not loc_id or not lay_id or live_position is None:
                return ""
            from data.live_segment_resolver import get_live_segment_context_for_prompt
            return get_live_segment_context_for_prompt(loc_id, lay_id, live_position)
        except Exception:
            return ""

    def _get_live_coaching_context(self, live_position=None, laps=None) -> str:
        """Return a compact live coaching cue prompt block.

        live_position: LivePosition — required for segment resolution.
        laps: recent LapStats list — used to build enriched issue history.
        Returns "" when no cue fires or position unavailable.
        Never raises.

        Deferred: voice announcement integration.
        """
        try:
            sc = self._config.get("strategy", {})
            loc_id = sc.get("track_location_id") or ""
            lay_id = sc.get("layout_id") or ""
            if not loc_id or not lay_id or live_position is None:
                return ""
            from data.live_segment_resolver import resolve_live_segment
            from data.live_segment_coaching import (
                build_live_coaching_decision,
                format_live_coaching_for_prompt,
            )
            live_result = resolve_live_segment(loc_id, lay_id, live_position)
            enriched_issues = []
            if laps:
                try:
                    from data.track_issue_enrichment import (
                        issues_from_lap_stats,
                        enrich_telemetry_issues,
                    )
                    raw = issues_from_lap_stats(laps)
                    if raw:
                        er = enrich_telemetry_issues(raw, loc_id, lay_id)
                        enriched_issues = er.enriched_issues
                except Exception:
                    pass
            decision = build_live_coaching_decision(live_result, enriched_issues=enriched_issues)
            return format_live_coaching_for_prompt(decision)
        except Exception:
            return ""

    def _get_previous_ai_context(self, feature: str) -> str:
        if self._db is None:
            return ""
        try:
            car_id = int(self._car_id_ref[0]) or 0
            track  = self._config.get("strategy", {}).get("track", "") or ""
            joined = self._db.get_recommendations_for_context(car_id, track, limit=2)
            if not joined:
                return ""
            return "## Previous AI Recommendations\n" + joined
        except Exception:
            return ""

    # ------------------------------------------------------------------
    # Prompt construction
    # ------------------------------------------------------------------

    def _car_track_header(self, car_name: str, car_specs: dict) -> str:
        """Return a compact car + track line for injection into prompts."""
        track = self._config.get("strategy", {}).get("track", "")
        parts = [car_name] if car_name else []
        if car_specs.get("category"):   parts.append(car_specs["category"])
        if car_specs.get("pp_rating"):  parts.append(f"PP {car_specs['pp_rating']:.0f}")
        if car_specs.get("drivetrain"): parts.append(car_specs["drivetrain"])
        if car_specs.get("aspiration"): parts.append(car_specs["aspiration"])
        if car_specs.get("power_hp"):   parts.append(f"{car_specs['power_hp']} hp")
        if car_specs.get("weight_kg"):  parts.append(f"{car_specs['weight_kg']} kg")
        car_line = "Car: " + " | ".join(parts) if parts else ""
        track_line = build_track_context(track)
        return "\n".join(x for x in [car_line, track_line] if x)

    @staticmethod
    def _cluster_positions(positions: list, threshold_m: float = 15.0) -> list:
        """Group XYZ positions within threshold_m of each other; return [(x,y,z,count)]."""
        clusters: list = []
        for pos in positions:
            for i, (cx, cy, cz, cnt) in enumerate(clusters):
                dist = ((pos[0]-cx)**2 + (pos[1]-cy)**2 + (pos[2]-cz)**2) ** 0.5
                if dist <= threshold_m:
                    # merge into cluster (running centroid)
                    clusters[i] = (
                        (cx*cnt + pos[0]) / (cnt+1),
                        (cy*cnt + pos[1]) / (cnt+1),
                        (cz*cnt + pos[2]) / (cnt+1),
                        cnt + 1,
                    )
                    break
            else:
                clusters.append((pos[0], pos[1], pos[2], 1))
        return clusters

    def _summarize_location_patterns(self, laps: "list[LapStats]") -> str:
        """Return a human-readable string of repeated-location event clusters."""
        if len(laps) < 3:
            return ""
        agg: dict = {
            "lock-up":     [],
            "wheelspin":   [],
            "oversteer":   [],
            "snap-throttle": [],
            "over-braking": [],
        }
        for lap in laps:
            agg["lock-up"].extend(getattr(lap, "lock_up_positions", []))
            agg["wheelspin"].extend(getattr(lap, "wheelspin_positions", []))
            agg["oversteer"].extend(getattr(lap, "oversteer_positions", []))
            agg["snap-throttle"].extend(getattr(lap, "snap_throttle_positions", []))
            agg["over-braking"].extend(getattr(lap, "over_braking_positions", []))

        lines: list[str] = []
        for event_name, positions in agg.items():
            if not positions:
                continue
            clusters = self._cluster_positions(positions)
            total = len(positions)
            n_clusters = len(clusters)
            max_count = max(c[3] for c in clusters)
            lines.append(
                f"  {event_name}: {total} total events concentrated at "
                f"{n_clusters} location{'s' if n_clusters > 1 else ''} "
                f"(hotspot: {max_count} hits)"
            )
        if not lines:
            return ""
        return "Location-based patterns across {} laps:\n{}".format(
            len(laps), "\n".join(lines)
        )

    def _summarize_new_telemetry(self, laps: "list[LapStats]") -> str:
        """Build a compact summary of B1-B6 metrics for prompt injection."""
        if not laps:
            return ""
        lines: list[str] = []

        # B1 — rev limiter
        total_rl = sum(getattr(l, "rev_limiter_count", 0) for l in laps)
        if total_rl > 0:
            # aggregate by gear across all laps
            gear_totals: dict = {}
            for l in laps:
                for g, cnt in getattr(l, "rev_limiter_by_gear", {}).items():
                    gear_totals[g] = gear_totals.get(g, 0) + cnt
            gear_str = ", ".join(
                f"G{g}: {c}" for g, c in sorted(gear_totals.items()) if g > 0
            )
            lines.append(
                f"Rev limiter hits: {total_rl} total across {len(laps)} laps"
                + (f" ({gear_str})" if gear_str else "")
            )

        # B2 — location clustering
        loc_summary = self._summarize_location_patterns(laps)
        if loc_summary:
            lines.append(loc_summary)

        # B3 — over-braking
        total_ob = sum(getattr(l, "over_braking_count", 0) for l in laps)
        total_ar = sum(getattr(l, "abrupt_release_count", 0) for l in laps)
        if total_ob > 0 or total_ar > 0:
            lines.append(
                f"Over-braking events: {total_ob} (100% brake into slow corner); "
                f"abrupt brake releases: {total_ar}"
            )

        # B4 — theoretical max speed
        theoretical_speeds = [
            getattr(l, "car_max_speed_theoretical_kmh", 0.0) for l in laps
            if getattr(l, "car_max_speed_theoretical_kmh", 0.0) > 50
        ]
        if theoretical_speeds:
            theoretical = max(theoretical_speeds)
            actual_max = max((l.max_speed_kmh for l in laps), default=0.0)
            pct = (actual_max / theoretical * 100) if theoretical > 0 else 0
            lines.append(
                f"Theoretical max speed (inferred): {theoretical:.0f} km/h | "
                f"Actual top speed: {actual_max:.0f} km/h ({pct:.0f}% of theoretical)"
            )

        # B5 — tyre radius trend
        radius_laps = [l for l in laps if getattr(l, "avg_tyre_radius", {})]
        if len(radius_laps) >= 2:
            first = radius_laps[0].avg_tyre_radius
            last  = radius_laps[-1].avg_tyre_radius
            trend_parts: list[str] = []
            for corner in ("fl", "fr", "rl", "rr"):
                r0 = first.get(corner, 0.0)
                r1 = last.get(corner, 0.0)
                if r0 > 0.1 and r1 > 0.1:
                    delta_pct = (r1 - r0) / r0 * 100
                    trend_parts.append(f"{corner.upper()}: {r0:.4f}→{r1:.4f} ({delta_pct:+.1f}%)")
            if trend_parts:
                lines.append(
                    "Tyre radius trend (inferred wear proxy — do not over-rely): "
                    + ", ".join(trend_parts)
                )

        # B6 — off-track
        total_ot = sum(getattr(l, "off_track_count", 0) for l in laps)
        if total_ot > 0:
            lines.append(
                f"Road surface deviation events: {total_ot} "
                f"(possible kerb / grass contact — inferred from road normal)"
            )

        return "\n".join(lines) if lines else ""

    _DATA_QUALITY_NOTE = (
        "## Data Quality Note\n"
        "Measured = direct GT7 packet values (fuel, speed, position).\n"
        "Calculated = derived via physics formulas (lock-up/wheelspin = wheel slip threshold; "
        "braking consistency = std-dev of brake points).\n"
        "Estimated = inferred proxies with uncertainty (lateral G = angvel_z × speed / 9.81; "
        "off-track = road normal Y < threshold; tyre wear = radius trend).\n"
        "Do not state estimated values as fact. Qualify with 'may indicate' or 'suggests'."
    )

    def _build_coaching_prompt(
        self, laps: "list[LapStats]", history_str: str,
        car_name: str = "", car_specs: dict | None = None,
        allowed_tuning: "list[str] | None" = None, tuning_locked: bool = False,
        compound: str = "", corner_issues_summary: str = "",
        live_position=None,
    ) -> str:
        car_specs = car_specs or {}
        best = self._recorder.best_lap()
        best_ms = best.lap_time_ms if best else 0

        lap_lines: list[str] = []
        for lap in laps:
            delta = (lap.lap_time_ms - best_ms) / 1000.0 if best_ms else 0
            os_entry = lap.oversteer_count - lap.oversteer_throttle_on_count
            consist_note = (
                "(good)" if 0 <= lap.brake_consistency_m < 15
                else "(needs work)" if lap.brake_consistency_m >= 15
                else "(unmeasured)"
            )
            lap_lines.append(
                f"  Lap {lap.lap_num}: {ms_to_str(lap.lap_time_ms)} ({delta:+.3f}s from best)\n"
                f"    lock-ups [calculated]: {lap.lock_up_count}, "
                f"wheelspin [calculated]: {lap.wheelspin_count}\n"
                f"    snap oversteer [calculated]: {lap.oversteer_count} "
                f"({lap.oversteer_throttle_on_count} throttle-on, {os_entry} entry)\n"
                f"    kerb events [measured]: {lap.kerb_count}, "
                f"bottoming [measured]: {lap.bottoming_count}, "
                f"snap throttle [calculated]: {lap.snap_throttle_count}\n"
                f"    braking consistency [calculated]: "
                f"{'n/a' if lap.brake_consistency_m < 0 else f'{lap.brake_consistency_m:.1f}m'} "
                f"{consist_note}\n"
                f"    top speed [measured]: {lap.max_speed_kmh:.0f} km/h, "
                f"peak lateral G [estimated]: {lap.max_lat_g:.2f}\n"
                f"    avg throttle [measured]: {lap.avg_throttle_pct:.0f}%, "
                f"avg brake [measured]: {lap.avg_brake_pct:.0f}%"
            )

        gt7_ref = load_gt7_reference()
        header = self._car_track_header(car_name, car_specs)
        tuning_block = _tuning_constraint_block(allowed_tuning, tuning_locked)
        event_block  = self._get_event_context_block()
        feedback_block   = self._get_driver_feedback_context()
        prev_ai_block    = self._get_previous_ai_context("Driver Coaching")
        track_intel_block = self._get_track_intelligence_context()
        enriched_issues_block = self._get_enriched_issue_context(laps)
        live_segment_block = self._get_live_segment_context(live_position)
        live_coaching_block = self._get_live_coaching_context(live_position, laps)
        compound_line    = f"Current tyre compound: {compound}" if compound else ""

        extra_sections = "\n\n".join(
            s for s in [track_intel_block, live_segment_block, live_coaching_block,
                        event_block, feedback_block, prev_ai_block,
                        enriched_issues_block or corner_issues_summary] if s
        )

        return f"""You are an elite motorsport driving coach for Gran Turismo 7.

## GT7 Knowledge Base (includes driver's personal style and preferences)
{gt7_ref}

---
{chr(10) + header + chr(10) if header else ""}{chr(10) + compound_line + chr(10) if compound_line else ""}{tuning_block}Analyse the following lap data and give the driver 2–3 specific, actionable coaching points.
Tailor your advice to the driver's known style from the knowledge base above.
Be direct, concise, and practical. Respond in plain spoken English (no markdown, no bullet points).
Keep your response under 5 sentences.

Metric definitions:
- snap oversteer throttle-on = rear broke loose during acceleration (exit technique / LSD / rear ARB)
- snap oversteer entry = rear broke loose on corner entry (too fast in / trail braking issue)
- kerb events = hard suspension hits from aggressive kerb riding (may help or hurt lap time)
- bottoming = chassis hit the ground (ride height / spring rate issue)
- snap throttle = abrupt 100% throttle stab < 100 ms (triggers wheelspin; smoothness needed)
- peak lateral G [estimated] = angvel_z × speed / 9.81 — proxy, may not reflect true G loading

## Recent laps
{chr(10).join(lap_lines)}

## Best lap on record
{ms_to_str(best_ms)}

## Advanced telemetry intelligence
{self._summarize_new_telemetry(laps) or "(insufficient data)"}

## Historical context for this car and track
{history_str}
{chr(10) + extra_sections if extra_sections else ""}
{self._DATA_QUALITY_NOTE}

Focus on the most significant pattern. Reference specific numbers.
Use the driver's vocabulary where appropriate (e.g. "tail is skaty" if rear lock-ups are detected).
If history shows a recurring pattern (e.g. consistently high lock-ups), mention it.
If location-based patterns show clustering, name the type of corner (braking/fast/slow)."""

    def _build_setup_prompt(
        self,
        laps: "list[LapStats]",
        setup: dict,
        history_str: str,
        car_name: str = "",
        car_specs: dict | None = None,
        allowed_tuning: "list[str] | None" = None,
        tuning_locked: bool = False,
        compound: str = "",
        corner_issues_summary: str = "",
        live_position=None,
    ) -> str:
        car_specs = car_specs or {}
        avg_lockups  = mean(l.lock_up_count   for l in laps)
        avg_spins    = mean(l.wheelspin_count  for l in laps)
        avg_consist  = mean(l.brake_consistency_m for l in laps if l.brake_consistency_m >= 0) or -1
        avg_os_total = mean(l.oversteer_count               for l in laps)
        avg_os_ton   = mean(l.oversteer_throttle_on_count   for l in laps)
        avg_os_entry = avg_os_total - avg_os_ton
        avg_kerb     = mean(l.kerb_count        for l in laps)
        avg_bottom   = mean(l.bottoming_count   for l in laps)
        avg_snap     = mean(l.snap_throttle_count for l in laps)
        avg_lat_g    = mean(l.max_lat_g         for l in laps)
        avg_top_spd  = mean(l.max_speed_kmh     for l in laps)

        consist_note = (
            "(good)" if 0 <= avg_consist < 15
            else "(needs work)" if avg_consist >= 15
            else "(unmeasured)"
        )

        setup_block    = format_setup_for_prompt(setup)
        gt7_ref        = load_gt7_reference()
        header         = self._car_track_header(car_name, car_specs)
        tuning_block   = _tuning_constraint_block(allowed_tuning, tuning_locked)
        event_block    = self._get_event_context_block()
        feedback_block = self._get_driver_feedback_context()
        prev_ai_block  = self._get_previous_ai_context("Setup Advice")
        track_intel_block = self._get_track_intelligence_context()
        enriched_issues_block = self._get_enriched_issue_context(laps)
        live_segment_block = self._get_live_segment_context(live_position)
        compound_line  = f"Current tyre compound: {compound}" if compound else ""
        extra_sections = "\n\n".join(
            s for s in [track_intel_block, live_segment_block, event_block,
                        feedback_block, prev_ai_block,
                        enriched_issues_block or corner_issues_summary] if s
        )

        return f"""You are an expert Gran Turismo 7 car setup engineer.

## GT7 Knowledge Base (includes driver's personal tuning philosophy)
{gt7_ref}

---
{chr(10) + header + chr(10) if header else ""}{chr(10) + compound_line + chr(10) if compound_line else ""}{tuning_block}Analyse the driver's telemetry and current car setup. Give 2–4 specific setup changes
tailored to the driver's known style from the knowledge base above.
Use the driver's personal setup order (stabilise braking first, then front response, etc.)
Give EXACT values for every change (e.g. "ARB Front: 5 → 4", not "soften front ARB").
If gearing is relevant (over-revving, under-revving, wrong gear at key corners), include it.

Metric definitions:
- snap oversteer throttle-on [calculated]: rear breaks loose during acceleration (exit phase)
- snap oversteer entry [calculated]: rear breaks loose on entry / trail braking phase
- kerb events [measured]: hard suspension compression from kerb riding
- bottoming events [measured]: chassis ground contact — indicates ride height or spring rate issue
- snap throttle [calculated]: abrupt 0→100% throttle in < 100 ms — triggers wheelspin and yaw
- peak lateral G [estimated]: speed × yaw_rate / 9.81 — proxy for cornering intensity

## Telemetry summary ({len(laps)} laps)
Average lock-ups per lap [calculated]:           {avg_lockups:.1f}
Average wheelspin events per lap [calculated]:   {avg_spins:.1f}
Average oversteer events per lap [calculated]:   {avg_os_total:.1f}  ({avg_os_ton:.1f} throttle-on, {avg_os_entry:.1f} entry)
Kerb events per lap [measured]:                  {avg_kerb:.1f}
Bottoming events per lap [measured]:             {avg_bottom:.1f}
Snap throttle applications per lap [calculated]: {avg_snap:.1f}
Peak lateral G (avg best per lap) [estimated]:   {avg_lat_g:.2f} G
Average top speed per lap [measured]:            {avg_top_spd:.0f} km/h
Braking consistency (std-dev) [calculated]:      {'n/a' if avg_consist < 0 else f'{avg_consist:.1f}m'} {consist_note}

## Advanced telemetry intelligence
{self._summarize_new_telemetry(laps) or "(insufficient data)"}

## Current car setup
{setup_block}

## Historical context for this car and track
{history_str}
{chr(10) + extra_sections if extra_sections else ""}
{self._DATA_QUALITY_NOTE}

Reply ONLY with valid JSON — no markdown fences, no extra text:
{{
  "analysis": "2–3 sentence plain-English summary of what the telemetry shows and the primary issue.",
  "changes": [
    {{"setting": "Setting Name", "from": "current value", "to": "recommended value", "why": "one-sentence reason"}},
    {{"setting": "Setting Name", "from": "current value", "to": "recommended value", "why": "one-sentence reason"}}
  ]
}}"""

    def _build_feeling_prompt(
        self,
        feeling_text: str,
        setup: dict,
        history_str: str,
        car_name: str = "",
        car_specs: dict | None = None,
    ) -> str:
        car_specs = car_specs or {}
        setup_block = format_setup_for_prompt(setup)
        gt7_ref = load_gt7_reference()
        header = self._car_track_header(car_name, car_specs)

        # Attach recent telemetry snapshot to cross-check driver description
        recent = self._recorder.recent_laps(3)
        if recent:
            avg_os_total = mean(l.oversteer_count             for l in recent)
            avg_os_ton   = mean(l.oversteer_throttle_on_count for l in recent)
            avg_lockups  = mean(l.lock_up_count               for l in recent)
            avg_spins    = mean(l.wheelspin_count              for l in recent)
            avg_kerb     = mean(l.kerb_count                  for l in recent)
            avg_bottom   = mean(l.bottoming_count             for l in recent)
            avg_snap     = mean(l.snap_throttle_count         for l in recent)
            avg_lat_g    = mean(l.max_lat_g                   for l in recent)
            new_telem = self._summarize_new_telemetry(recent)
            telemetry_block = (
                f"Lock-ups per lap: {avg_lockups:.1f}\n"
                f"Wheelspin per lap: {avg_spins:.1f}\n"
                f"Snap oversteer per lap: {avg_os_total:.1f} "
                f"({avg_os_ton:.1f} throttle-on, {avg_os_total - avg_os_ton:.1f} entry)\n"
                f"Kerb events per lap: {avg_kerb:.1f}\n"
                f"Bottoming events per lap: {avg_bottom:.1f}\n"
                f"Snap throttle applications per lap: {avg_snap:.1f}\n"
                f"Peak lateral G (avg): {avg_lat_g:.2f} G"
                + (f"\n{new_telem}" if new_telem else "")
            )
        else:
            telemetry_block = "(No recent lap telemetry available.)"

        prev_ai_block = self._get_previous_ai_context("Handling Analysis")

        return f"""You are an expert Gran Turismo 7 car setup engineer.

## GT7 Knowledge Base (includes driver's personal tuning philosophy and preferences)
{gt7_ref}

---
{chr(10) + header + chr(10) if header else ""}
The driver has described a specific handling problem. Give 2–4 concrete setup changes to fix it.

Rules:
- Address the EXACT complaint — don't give generic advice
- Give EXACT values for every change (e.g. "Rear ARB: 4 → 3", not just "soften rear ARB")
- Use the driver's setup priority order from the knowledge base
- Cross-reference the telemetry — if the data contradicts the feeling (e.g. driver says oversteer
  but lock-ups dominate), call it out and target the telemetry-confirmed issue
- If a corner number is mentioned (T3, T6, etc.) target that type of corner (slow/fast/braking)
- If gearing is relevant to the complaint, include a specific gear ratio or top speed target

## Driver's description of how the car feels
"{feeling_text}"

## Recent telemetry (last 3 laps)
{telemetry_block}

## Current car setup
{setup_block}

## Historical context for this car and track
{history_str}
{chr(10) + prev_ai_block if prev_ai_block else ""}
Reply ONLY with valid JSON — no markdown fences, no extra text:
{{
  "analysis": "2–3 sentence plain-English explanation of what is causing the handling problem.",
  "changes": [
    {{"setting": "Setting Name", "field": "arb_rear", "from": "current value", "to": "recommended value", "why": "one-sentence reason"}},
    {{"setting": "Setting Name", "field": "camber_front", "from": "current value", "to": "recommended value", "why": "one-sentence reason"}}
  ]
}}
In changes, "field" MUST be the exact canonical param key (e.g. arb_front, camber_rear, springs_front, lsd_accel, brake_bias, ride_height_front, toe_rear, etc.)."""

    def _build_combined_prompt(
        self,
        laps: "list[LapStats]",
        setup: dict,
        history_str: str,
        car_name: str = "",
        car_specs: dict | None = None,
        feeling: str | None = None,
        allowed_tuning: "list[str] | None" = None,
        tuning_locked: bool = False,
        compound: str = "",
        corner_issues_summary: str = "",
        live_position=None,
    ) -> str:
        """Unified setup-analysis prompt: always includes telemetry; optionally adds feeling."""
        car_specs = car_specs or {}
        avg_lockups  = mean(l.lock_up_count   for l in laps)
        avg_spins    = mean(l.wheelspin_count  for l in laps)
        avg_consist  = mean(l.brake_consistency_m for l in laps if l.brake_consistency_m >= 0) or -1
        avg_os_total = mean(l.oversteer_count               for l in laps)
        avg_os_ton   = mean(l.oversteer_throttle_on_count   for l in laps)
        avg_os_entry = avg_os_total - avg_os_ton
        avg_kerb     = mean(l.kerb_count        for l in laps)
        avg_bottom   = mean(l.bottoming_count   for l in laps)
        avg_snap     = mean(l.snap_throttle_count for l in laps)
        avg_lat_g    = mean(l.max_lat_g         for l in laps)
        avg_top_spd  = mean(l.max_speed_kmh     for l in laps)

        consist_note = (
            "(good)" if 0 <= avg_consist < 15
            else "(needs work)" if avg_consist >= 15
            else "(unmeasured)"
        )

        # Gear / rev-limiter context
        top_speed_target = float(setup.get("transmission_max_speed_kmh") or 0)
        gear_note = ""
        if top_speed_target > 0 and avg_top_spd > 0:
            ratio = avg_top_spd / top_speed_target
            if ratio < 0.93:
                gear_note = (
                    f"\n⚠ Observed top speed {avg_top_spd:.0f} km/h is "
                    f"{100*(1-ratio):.0f}% below the transmission target "
                    f"({top_speed_target:.0f} km/h) — car is NOT hitting the rev "
                    f"limiter in top gear. Do NOT recommend lengthening gears."
                )
            elif ratio > 0.98:
                gear_note = (
                    f"\n✓ Car is at/near the rev limiter "
                    f"(observed {avg_top_spd:.0f} km/h vs target {top_speed_target:.0f} km/h)."
                )

        feeling_section = ""
        if feeling:
            feeling_section = f"""

## Driver's description of how the car feels
"{feeling}"

Cross-reference the telemetry — if data contradicts the feeling (e.g. driver says oversteer
but lock-ups dominate), call it out and target the telemetry-confirmed issue.
If a corner number is mentioned, target that type of corner (slow/fast/braking zone)."""

        setup_block    = format_setup_for_prompt(setup)
        gt7_ref        = load_gt7_reference()
        header         = self._car_track_header(car_name, car_specs)
        tuning_block   = _tuning_constraint_block(allowed_tuning, tuning_locked)
        event_block    = self._get_event_context_block()
        feedback_block = self._get_driver_feedback_context()
        prev_ai_block  = self._get_previous_ai_context("Setup Advice")
        track_intel_block = self._get_track_intelligence_context()
        enriched_issues_block = self._get_enriched_issue_context(laps)
        live_segment_block = self._get_live_segment_context(live_position)
        compound_line  = f"Current tyre compound: {compound}" if compound else ""
        extra_sections = "\n\n".join(
            s for s in [track_intel_block, live_segment_block, event_block,
                        feedback_block, prev_ai_block,
                        enriched_issues_block or corner_issues_summary] if s
        )

        return f"""You are an expert Gran Turismo 7 car setup engineer.

## GT7 Knowledge Base (includes driver's personal tuning philosophy)
{gt7_ref}

---
{chr(10) + header + chr(10) if header else ""}{chr(10) + compound_line + chr(10) if compound_line else ""}{tuning_block}Analyse the driver's telemetry and current car setup. Give 2–4 specific setup changes
tailored to the driver's known style from the knowledge base above.
Use the driver's personal setup priority order (stabilise braking first, then front response, etc.)
Give EXACT values for every change (e.g. "ARB Front: 5 → 4", not "soften front ARB").{feeling_section}

Metric definitions:
- snap oversteer throttle-on [calculated]: rear breaks loose during acceleration (exit phase)
- snap oversteer entry [calculated]: rear breaks loose on entry / trail braking phase
- kerb events [measured]: hard suspension compression from kerb riding
- bottoming events [measured]: chassis ground contact — indicates ride height or spring rate issue
- snap throttle [calculated]: abrupt 0→100% throttle in < 100 ms — triggers wheelspin and yaw
- peak lateral G [estimated]: speed × yaw_rate / 9.81 — proxy for cornering intensity

## Telemetry summary ({len(laps)} laps)
Average lock-ups per lap [calculated]:           {avg_lockups:.1f}
Average wheelspin events per lap [calculated]:   {avg_spins:.1f}
Average oversteer events per lap [calculated]:   {avg_os_total:.1f}  ({avg_os_ton:.1f} throttle-on, {avg_os_entry:.1f} entry)
Kerb events per lap [measured]:                  {avg_kerb:.1f}
Bottoming events per lap [measured]:             {avg_bottom:.1f}
Snap throttle applications per lap [calculated]: {avg_snap:.1f}
Peak lateral G (avg best per lap) [estimated]:   {avg_lat_g:.2f} G
Average top speed per lap [measured]:            {avg_top_spd:.0f} km/h{gear_note}
Braking consistency (std-dev) [calculated]:      {'n/a' if avg_consist < 0 else f'{avg_consist:.1f}m'} {consist_note}

## Advanced telemetry intelligence
{self._summarize_new_telemetry(laps) or "(insufficient data)"}

## Current car setup
{setup_block}

## Historical context for this car and track
{history_str}
{chr(10) + extra_sections if extra_sections else ""}
{self._DATA_QUALITY_NOTE}

## Valid setup_fields keys (numeric values only — use ONLY keys for fields you are changing)
arb_front, arb_rear, ride_height_front, ride_height_rear,
springs_front, springs_rear, dampers_front_comp, dampers_front_ext,
dampers_rear_comp, dampers_rear_ext, camber_front, camber_rear,
toe_front, toe_rear, aero_front, aero_rear,
lsd_initial, lsd_accel, lsd_decel, brake_bias,
transmission_max_speed_kmh, power_restrictor, ballast_kg, ballast_position

Reply ONLY with valid JSON — no markdown fences, no extra text:
{{
  "analysis": "2–3 sentence plain-English summary of what the telemetry shows and the primary issue.",
  "changes": [
    {{"setting": "Setting Name", "field": "arb_front", "from": "current value", "to": "recommended value", "why": "one-sentence reason"}}
  ],
  "setup_fields": {{
    "arb_front": 4
  }}
}}
In setup_fields include ONLY the fields being changed, with numeric values (not strings).
In changes, "field" MUST be the exact canonical key from the setup_fields list above."""

