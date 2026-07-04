"""AI context snapshots — frozen, owner-documented inputs for AI prompt paths.

Added by the **AI Snapshot Migration — Frozen Context Inputs** sprint
(2026-07-03). It composes the four canonical read models built by State
Consolidations 1–4 (`data/event_context.py`, `data/strategy_context.py`,
`data/setup_context.py`, `data/track_context.py`).

Why this exists
---------------
Every AI-input path in the app assembled its inputs **live** from
``config["strategy"]`` at call time — the exact SSOT-7 risk in
`docs/PRODUCT_CONSOLIDATION_AUDIT.md`: a prompt could mix a stale strategy
snapshot with fresh UI state, or read event fields that no longer match the
edited DB event. This module freezes one consistent set of inputs per AI call:

* ``StrategyAISnapshot``   — race-strategy analysis + mid-race re-plan inputs
  (`_assemble_strategy_inputs` / `_run_ai_analysis`),
* ``PracticeAnalysisSnapshot`` — practice-analysis inputs
  (`_run_practice_analysis`),
* ``SetupAISnapshot``      — Build-Setup-with-AI + Analyse-Setup event inputs
  (`setup_builder_ui`),

each embedding a common ``AIContextSnapshot`` core carrying the component
change markers, a combined ``snapshot_id``, build warnings and staleness
detection.

**This sprint changes inputs plumbing, not intelligence.** The snapshot
builders reproduce the legacy field expressions **byte-identically** whenever
the legacy config and the contexts are in sync (which the "Set as Active"
fan-out guarantees). The single intentional difference: when the durable DB
event record was edited after the fan-out, EventContext returns the **fresh**
value where legacy returned the stale copy — that is the purpose of the
migration and is covered by focused tests.

Ownership (documented per field)
--------------------------------
* Event/race truth (track, laps, duration, race type, multipliers, refuel
  rate, BoP/tuning legality, tyre lists, mandatory compounds) —
  **EventContext**.
* Strategy-plan truth (fuel burn per lap, pit loss, config_id) —
  **StrategyContext** (legacy defaults 2.0 L / 23.0 s applied exactly as the
  legacy expressions did, documented below).
* Setup-recommendation truth — **SetupContext / SetupPromptSnapshot**.
* Track/layout identity — **TrackContext** (falls back internally to
  EventContext / legacy ids exactly as State Consolidation 4 defined).
* Telemetry-derived values (live fuel burn from the tracker / loaded session)
  remain caller-supplied (``fuel_burn_override``) until a TelemetryContext
  sprint — documented legacy dependency.

Legacy fallback policy
----------------------
When **no** event context is available (``EventContext.source == EMPTY``) the
builders evaluate the *exact legacy expressions* against the legacy
``config["strategy"]`` dict and record a warning — they never silently prefer
legacy when a clean context exists.

Purity
------
No PyQt6, no UI, no network/AI calls, no DB, no file I/O. Builders never raise
on missing/malformed optional fields — they return warnings instead.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, asdict
from enum import Enum
from typing import Any, Optional, Tuple, TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - typing only
    from data.event_context import EventContext
    from data.strategy_context import StrategyContext
    from data.setup_context import SetupPromptSnapshot
    from data.track_context import TrackContext


AI_CONTEXT_SNAPSHOT_SCHEMA = "ai_context_snapshot_v1"


class AIContextSnapshotSource(str, Enum):
    """How the snapshot's inputs were resolved."""
    CONTEXTS = "contexts"        # built from the canonical read models
    LEGACY_ONLY = "legacy_only"  # no active event context — exact legacy expressions
    EMPTY = "empty"              # nothing available at all


# --------------------------------------------------------------------------- #
# Safe helpers (never raise) — mirror the context modules
# --------------------------------------------------------------------------- #
def _as_str(v, default: str = "") -> str:
    if v is None:
        return default
    try:
        return str(v)
    except Exception:  # pragma: no cover - defensive
        return default


def _as_int(v, default: int = 0) -> int:
    try:
        if v is None or v == "":
            return default
        return int(round(float(v)))
    except (TypeError, ValueError):
        return default


def _as_float(v, default: float = 0.0) -> float:
    try:
        if v is None or v == "":
            return default
        return float(v)
    except (TypeError, ValueError):
        return default


def _get(obj, name, default=None):
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(name, default)
    try:
        return getattr(obj, name, default)
    except Exception:  # pragma: no cover - defensive
        return default


def _freeze_params(d: dict) -> Tuple[Tuple[str, Any], ...]:
    """Freeze a params dict into a sorted tuple (lists become tuples)."""
    out = []
    for k in sorted(d):
        v = d[k]
        if isinstance(v, list):
            v = tuple(v)
        out.append((str(k), v))
    return tuple(out)


def _thaw_params(frozen: Tuple[Tuple[str, Any], ...]) -> dict:
    """Reconstruct the plain params dict (tuples back to lists)."""
    out = {}
    for k, v in (frozen or ()):
        out[k] = list(v) if isinstance(v, tuple) else v
    return out


def compute_snapshot_id(fields: dict) -> str:
    """Stable 12-char id over the snapshot payload + component change markers.
    Deterministic (no time / randomness)."""
    blob = json.dumps(fields, sort_keys=True, default=str)
    return hashlib.sha1(blob.encode("utf-8")).hexdigest()[:12]


# --------------------------------------------------------------------------- #
# Core snapshot (shared by every use case)
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class AIContextSnapshot:
    """The common core: component change markers + combined id + warnings."""
    schema: str
    snapshot_id: str
    source: AIContextSnapshotSource

    # Component keys (empty string = that context was not supplied)
    event_change_hash: str = ""
    strategy_change_hash: str = ""
    setup_snapshot_id: str = ""
    track_change_hash: str = ""

    # Build-time notes: legacy fallbacks used, staleness/mismatch detected.
    warnings: Tuple[str, ...] = ()
    stale_warnings: Tuple[str, ...] = ()

    @property
    def has_stale_state(self) -> bool:
        return bool(self.stale_warnings)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["source"] = self.source.value
        d["warnings"] = list(self.warnings)
        d["stale_warnings"] = list(self.stale_warnings)
        return d


@dataclass(frozen=True)
class AIContextSnapshotValidationResult:
    ok: bool
    warnings: Tuple[str, ...] = ()
    stale_warnings: Tuple[str, ...] = ()

    @property
    def all_warnings(self) -> Tuple[str, ...]:
        return tuple(self.warnings) + tuple(self.stale_warnings)


def validate_ai_context_snapshot(core: AIContextSnapshot) -> AIContextSnapshotValidationResult:
    """Non-crashing validation of a snapshot core. ``ok`` means: built from
    contexts, no staleness detected."""
    warnings = list(core.warnings)
    if core.source == AIContextSnapshotSource.LEGACY_ONLY:
        warnings.append(
            "AI inputs built from legacy config only — no active event context.")
    elif core.source == AIContextSnapshotSource.EMPTY:
        warnings.append("AI inputs are empty — no event or legacy state available.")
    return AIContextSnapshotValidationResult(
        ok=(core.source == AIContextSnapshotSource.CONTEXTS and not core.stale_warnings),
        warnings=tuple(warnings),
        stale_warnings=core.stale_warnings,
    )


# --------------------------------------------------------------------------- #
# Shared staleness detection
# --------------------------------------------------------------------------- #
def _detect_stale(
    event_context,
    strategy_context=None,
    setup_snapshot=None,
    track_context=None,
) -> Tuple[str, ...]:
    """Cross-context staleness/mismatch checks. Never raises."""
    stale = []
    ev_hash = _as_str(_get(event_context, "change_hash"))

    sc_ev_hash = _as_str(_get(strategy_context, "event_change_hash"))
    if ev_hash and sc_ev_hash and sc_ev_hash != ev_hash:
        stale.append(
            "Strategy plan was built against an older event configuration.")

    setup_ev_hash = _as_str(_get(setup_snapshot, "event_change_hash"))
    if ev_hash and setup_ev_hash and setup_ev_hash != ev_hash:
        stale.append("Setup was generated for a previous event configuration.")

    if track_context is not None and event_context is not None:
        try:
            if track_context.mismatches_event(event_context):
                stale.append(
                    "Track Modelling selection does not match the active event's track.")
        except Exception:  # pragma: no cover - defensive
            pass

    return tuple(stale)


def _resolve_track_ids(track_context, event_context, legacy: dict) -> Tuple[str, str]:
    """Track/layout ids — owner: TrackContext (its own resolution already
    falls back to EventContext then legacy ids, per State Consolidation 4)."""
    if track_context is not None:
        ident = _get(track_context, "identity")
        loc = _as_str(_get(ident, "track_location_id"))
        lay = _as_str(_get(ident, "layout_id"))
        if loc or lay:
            return loc, lay
    loc = _as_str(_get(event_context, "track_location_id")) or _as_str(legacy.get("track_location_id"))
    lay = _as_str(_get(event_context, "layout_id")) or _as_str(legacy.get("layout_id"))
    return loc, lay


def _mandatory_compounds_from_event(event_context) -> list:
    """Mandatory compounds — owner: EventContext.required_tyres. Reproduces the
    legacy ``_get_mandatory_compounds()`` normalisation (strip + upper)."""
    req = _get(event_context, "required_tyres") or ()
    return [str(c).strip().upper() for c in req if str(c).strip()]


def _legacy_mandatory_compounds(legacy: dict) -> list:
    """Exact legacy ``_get_mandatory_compounds()`` semantics on the legacy dict."""
    raw = legacy.get("mandatory_compounds", "")
    if isinstance(raw, list):
        return [c.strip().upper() for c in raw if c.strip()]
    if isinstance(raw, str) and raw.strip():
        return [c.strip().upper() for c in raw.split(",") if c.strip()]
    return []


def _event_has_real_tuning(event_context, legacy: dict) -> bool:
    """True when the tuning flag is genuinely known (present in the legacy dict,
    or the context was built from a durable DB event record — the events table
    always stores bop/tuning)."""
    if "tuning" in legacy:
        return True
    src = _as_str(_get(_get(event_context, "source"), "value")) or _as_str(_get(event_context, "source"))
    return src in ("db_event", "merged")


# --------------------------------------------------------------------------- #
# Race-params assembly (strategy + practice paths)
# --------------------------------------------------------------------------- #
def _race_params_from_contexts(
    event_context,
    strategy_context,
    track_context,
    legacy: dict,
    *,
    tuning_absent_locked: bool,
    fuel_burn_override: Optional[float],
) -> dict:
    """Build the RaceParams kwargs from the canonical contexts.

    Byte-identical to the legacy expressions whenever the contexts and the
    legacy dict are in sync; where the durable DB event was edited after the
    fan-out, the **fresh** context value is used (the intentional difference).
    Legacy defaults are preserved exactly:

    - ``total_laps`` → 25 when nothing is set,
    - ``refuel_speed_lps`` → 10.0 when nothing is set,
    - ``fuel_burn_per_lap`` → 2.0 (StrategyContext value when calibrated),
    - ``pit_loss_secs`` → 23.0 (StrategyContext value when set),
    - ``tuning_locked`` when the flag is genuinely unknown →
      ``tuning_absent_locked`` (True for practice analysis per DEF-P1-005's
      safe-locked default; False for strategy analysis).
    """
    ev = event_context
    loc_id, lay_id = _resolve_track_ids(track_context, ev, legacy)

    laps = _as_int(_get(ev, "laps"), 0)
    total_laps = laps if laps > 0 else _as_int(legacy.get("total_laps"), 25)

    refuel = _as_float(_get(ev, "refuel_rate_lps"), 0.0)
    if refuel <= 0.0:
        refuel = _as_float(legacy.get("refuel_speed_lps"), 10.0)

    if fuel_burn_override is not None:
        # Telemetry-derived (tracker / loaded session) — caller-owned until a
        # TelemetryContext sprint.
        fuel_burn = float(fuel_burn_override)
    else:
        fuel_burn = _as_float(_get(strategy_context, "fuel_burn_per_lap"), 0.0)
        if fuel_burn <= 0.0:
            fuel_burn = _as_float(legacy.get("fuel_burn_per_lap"), 2.0)

    pit_loss = _as_float(_get(strategy_context, "pit_loss_secs"), 0.0)
    if pit_loss <= 0.0:
        pit_loss = _as_float(legacy.get("pit_loss_secs"), 23.0)

    if _event_has_real_tuning(ev, legacy):
        tuning_locked = bool(_get(ev, "tuning_locked", False))
    else:
        tuning_locked = tuning_absent_locked

    return {
        "track":                _as_str(_get(ev, "track")),
        "track_location_id":    loc_id,
        "layout_id":            lay_id,
        "total_laps":           total_laps,
        "tyre_wear_multiplier": _as_float(_get(ev, "tyre_wear_multiplier"), 1.0),
        "fuel_burn_per_lap":    fuel_burn,
        "refuel_speed_lps":     refuel,
        "pit_loss_secs":        pit_loss,
        "min_mandatory_stops":  _as_int(_get(ev, "mandatory_stops"), 0),
        "mandatory_compounds":  _mandatory_compounds_from_event(ev),
        "race_type":            _as_str(_get(ev, "race_type")) or "lap",
        "duration_mins":        _as_int(_get(ev, "race_duration_minutes"), 0),
        "tuning_locked":        tuning_locked,
        "allowed_tuning":       list(_get(ev, "allowed_tuning_categories") or ()) or [],
        "bop":                  bool(_get(ev, "bop_enabled", False)),
        "avail_tyres":          list(_get(ev, "available_tyres") or ()) or [],
    }


def _race_params_legacy(
    legacy: dict,
    *,
    tuning_absent_default: bool,
    fuel_burn_override: Optional[float],
) -> dict:
    """The EXACT legacy expressions, for the documented no-context fallback.
    ``tuning_absent_default`` is the legacy ``_sc.get("tuning", <default>)``
    default (True for strategy paths, False for practice — DEF-P1-005)."""
    fuel_burn = (
        float(fuel_burn_override) if fuel_burn_override is not None
        else float(_as_float(legacy.get("fuel_burn_per_lap"), 2.0))
    )
    return {
        "track":                legacy.get("track", ""),
        "track_location_id":    legacy.get("track_location_id", ""),
        "layout_id":            legacy.get("layout_id", ""),
        "total_laps":           _as_int(legacy.get("total_laps"), 25),
        "tyre_wear_multiplier": _as_float(legacy.get("tyre_wear_multiplier"), 1.0),
        "fuel_burn_per_lap":    fuel_burn,
        "refuel_speed_lps":     _as_float(legacy.get("refuel_speed_lps"), 10.0),
        "pit_loss_secs":        _as_float(legacy.get("pit_loss_secs"), 23.0),
        "min_mandatory_stops":  _as_int(legacy.get("mandatory_stops"), 0),
        "mandatory_compounds":  _legacy_mandatory_compounds(legacy),
        "race_type":            legacy.get("race_type", "lap"),
        "duration_mins":        _as_int(legacy.get("race_duration_minutes"), 0),
        "tuning_locked":        not bool(legacy.get("tuning", tuning_absent_default)),
        "allowed_tuning":       legacy.get("allowed_tuning_categories") or [],
        "bop":                  bool(legacy.get("bop", False)),
        "avail_tyres":          legacy.get("avail_tyres", []) or [],
    }


def _build_core(
    payload: dict,
    source: AIContextSnapshotSource,
    event_context,
    strategy_context,
    setup_snapshot,
    track_context,
    warnings: list,
) -> AIContextSnapshot:
    stale = _detect_stale(event_context, strategy_context, setup_snapshot, track_context)
    component_hashes = {
        "event": _as_str(_get(event_context, "change_hash")),
        "strategy": _as_str(_get(strategy_context, "change_hash")),
        "setup": _as_str(_get(setup_snapshot, "snapshot_id")),
        "track": _as_str(_get(track_context, "change_hash")),
    }
    snapshot_id = compute_snapshot_id({"payload": payload, **component_hashes})
    return AIContextSnapshot(
        schema=AI_CONTEXT_SNAPSHOT_SCHEMA,
        snapshot_id=snapshot_id,
        source=source,
        event_change_hash=component_hashes["event"],
        strategy_change_hash=component_hashes["strategy"],
        setup_snapshot_id=component_hashes["setup"],
        track_change_hash=component_hashes["track"],
        warnings=tuple(warnings),
        stale_warnings=stale,
    )


def _resolve_source(event_context, legacy: dict, warnings: list) -> AIContextSnapshotSource:
    has_event = bool(_get(event_context, "has_active_event", False))
    if has_event:
        return AIContextSnapshotSource.CONTEXTS
    if legacy:
        warnings.append(
            "No active event context — race parameters read from legacy "
            "config[\"strategy\"] expressions (documented fallback).")
        return AIContextSnapshotSource.LEGACY_ONLY
    warnings.append("No event context and no legacy strategy config available.")
    return AIContextSnapshotSource.EMPTY


# --------------------------------------------------------------------------- #
# Use-case snapshot: race strategy analysis / mid-race re-plan
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class StrategyAISnapshot:
    """Frozen inputs for race-strategy analysis (`_assemble_strategy_inputs`,
    `_run_ai_analysis`). ``race_params`` feeds ``RaceParams(**...)``."""
    core: AIContextSnapshot
    race_params: Tuple[Tuple[str, Any], ...]
    config_id: str  # owner: StrategyContext (setup-history match key)

    def race_params_dict(self) -> dict:
        return _thaw_params(self.race_params)

    def to_dict(self) -> dict:
        return {
            "core": self.core.to_dict(),
            "race_params": self.race_params_dict(),
            "config_id": self.config_id,
        }


def build_strategy_ai_snapshot(
    *,
    event_context=None,
    strategy_context=None,
    setup_snapshot=None,
    track_context=None,
    legacy_strategy: Optional[dict] = None,
    fuel_burn_override: Optional[float] = None,
) -> StrategyAISnapshot:
    """Freeze the strategy-analysis inputs. Never raises.

    ``fuel_burn_override`` — pass the telemetry-derived value
    (``_computed_fuel_burn_lpl()``) where the legacy path used it
    (`_run_ai_analysis`); omit to use StrategyContext with the legacy 2.0
    default (`_assemble_strategy_inputs`).
    """
    legacy = legacy_strategy if isinstance(legacy_strategy, dict) else {}
    warnings: list = []
    source = _resolve_source(event_context, legacy, warnings)

    if source == AIContextSnapshotSource.CONTEXTS:
        params = _race_params_from_contexts(
            event_context, strategy_context, track_context, legacy,
            tuning_absent_locked=False,  # legacy strategy paths: absent → unlocked
            fuel_burn_override=fuel_burn_override,
        )
    else:
        params = _race_params_legacy(
            legacy, tuning_absent_default=True,
            fuel_burn_override=fuel_burn_override,
        )

    config_id = _as_str(_get(strategy_context, "config_id")) or _as_str(legacy.get("config_id"))

    core = _build_core(params, source, event_context, strategy_context,
                       setup_snapshot, track_context, warnings)
    return StrategyAISnapshot(
        core=core, race_params=_freeze_params(params), config_id=config_id)


# --------------------------------------------------------------------------- #
# Use-case snapshot: practice analysis
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class PracticeAnalysisSnapshot:
    """Frozen inputs for practice analysis (`_run_practice_analysis`).

    Same shape as StrategyAISnapshot; kept distinct because the legacy practice
    path uses the DEF-P1-005 safe-locked tuning default (absent flag → locked)
    and always takes the telemetry-derived fuel burn.
    """
    core: AIContextSnapshot
    race_params: Tuple[Tuple[str, Any], ...]
    discipline: str = "unknown"   # OFR-2: resolved session discipline

    def race_params_dict(self) -> dict:
        return _thaw_params(self.race_params)

    def to_dict(self) -> dict:
        return {
            "core": self.core.to_dict(),
            "race_params": self.race_params_dict(),
            "discipline": self.discipline,
        }


def build_practice_analysis_snapshot(
    *,
    event_context=None,
    strategy_context=None,
    setup_snapshot=None,
    track_context=None,
    legacy_strategy: Optional[dict] = None,
    fuel_burn_override: Optional[float] = None,
    session_purpose: Optional[str] = None,
) -> PracticeAnalysisSnapshot:
    """Freeze the practice-analysis inputs. Never raises. ``fuel_burn_override``
    should carry ``_computed_fuel_burn_lpl()`` (telemetry-owned).
    ``session_purpose`` is optional — when supplied it is normalised to a
    discipline string; absent/unknown → "unknown" (OFR-2 AC8)."""
    legacy = legacy_strategy if isinstance(legacy_strategy, dict) else {}
    warnings: list = []
    source = _resolve_source(event_context, legacy, warnings)

    if source == AIContextSnapshotSource.CONTEXTS:
        params = _race_params_from_contexts(
            event_context, strategy_context, track_context, legacy,
            tuning_absent_locked=True,  # DEF-P1-005: unknown tuning → locked
            fuel_burn_override=fuel_burn_override,
        )
    else:
        params = _race_params_legacy(
            legacy, tuning_absent_default=False,  # not bool(get("tuning", False))
            fuel_burn_override=fuel_burn_override,
        )

    # Resolve discipline from session_purpose (OFR-2 AC8).
    try:
        from data.setup_context import normalise_purpose as _np
        _disc = _np(session_purpose).value
    except Exception:  # pragma: no cover - defensive
        _disc = "unknown"

    core = _build_core(params, source, event_context, strategy_context,
                       setup_snapshot, track_context, warnings)
    return PracticeAnalysisSnapshot(
        core=core, race_params=_freeze_params(params), discipline=_disc)


# --------------------------------------------------------------------------- #
# Use-case snapshot: setup AI (Build Setup with AI / Analyse Setup)
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class SetupAISnapshot:
    """Frozen event/track inputs for the setup AI paths (`setup_builder_ui`).

    Field owners: everything except ``pit_loss_secs`` (StrategyContext),
    ``track_location_id``/``layout_id`` (TrackContext) and
    ``setup_snapshot_id`` (SetupContext) is **EventContext** truth. Note the
    build-setup legacy defaults differ from the strategy paths: refuel and pit
    loss default to 0.0 here (preserved exactly).
    """
    core: AIContextSnapshot

    car: str
    track: str
    race_laps: int
    duration_mins: int
    mandatory_stops: int
    refuel_rate_lps: float
    pit_loss_secs: float
    tuning_locked: bool
    allowed_tuning: Tuple[str, ...]
    tyre_wear_multiplier: float
    fuel_multiplier: float
    avail_tyres: Tuple[str, ...]
    required_tyres: Tuple[str, ...]
    race_type: str
    track_location_id: str
    layout_id: str
    mandatory_compounds_str: str
    discipline: str = "unknown"   # OFR-2: resolved setup discipline

    def allowed_tuning_or_none(self):
        """Legacy call shape: ``allowed_tuning_categories or None``."""
        return list(self.allowed_tuning) or None

    def avail_tyres_list(self) -> list:
        return list(self.avail_tyres)

    def required_tyres_list(self) -> list:
        return list(self.required_tyres)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["core"] = self.core.to_dict()
        d["allowed_tuning"] = list(self.allowed_tuning)
        d["avail_tyres"] = list(self.avail_tyres)
        d["required_tyres"] = list(self.required_tyres)
        return d


def build_setup_ai_snapshot(
    *,
    event_context=None,
    strategy_context=None,
    setup_snapshot=None,
    track_context=None,
    legacy_strategy: Optional[dict] = None,
    session_type: Optional[str] = None,
) -> SetupAISnapshot:
    """Freeze the setup-AI event/track inputs. Never raises.
    ``session_type`` is optional — when supplied (the setup's declared purpose)
    it is normalised to a discipline string; absent/unknown → "unknown" (OFR-2)."""
    legacy = legacy_strategy if isinstance(legacy_strategy, dict) else {}
    warnings: list = []
    source = _resolve_source(event_context, legacy, warnings)

    if source == AIContextSnapshotSource.CONTEXTS:
        ev = event_context
        loc_id, lay_id = _resolve_track_ids(track_context, ev, legacy)
        laps = _as_int(_get(ev, "laps"), 0)
        payload = {
            "car":                  _as_str(_get(ev, "car")) or "Unknown",
            "track":                _as_str(_get(ev, "track")),
            "race_laps":            laps if laps > 0 else _as_int(legacy.get("total_laps"), 25),
            "duration_mins":        _as_int(_get(ev, "race_duration_minutes"), 0),
            "mandatory_stops":      _as_int(_get(ev, "mandatory_stops"), 0),
            # Build-setup legacy defaults are 0.0 (NOT the strategy paths' 10/23).
            "refuel_rate_lps":      _as_float(_get(ev, "refuel_rate_lps"), 0.0),
            "pit_loss_secs":        _as_float(_get(strategy_context, "pit_loss_secs"), 0.0),
            "tuning_locked":        bool(_get(ev, "tuning_locked", False)),
            "allowed_tuning":       tuple(_get(ev, "allowed_tuning_categories") or ()),
            "tyre_wear_multiplier": _as_float(_get(ev, "tyre_wear_multiplier"), 1.0),
            "fuel_multiplier":      _as_float(_get(ev, "fuel_multiplier"), 1.0),
            "avail_tyres":          tuple(_get(ev, "available_tyres") or ()),
            "required_tyres":       tuple(_get(ev, "required_tyres") or ()),
            "race_type":            _as_str(_get(ev, "race_type")) or "lap",
            "track_location_id":    loc_id,
            "layout_id":            lay_id,
            # Legacy stores the joined string; the fan-out writes ", ".join(req).
            "mandatory_compounds_str": ", ".join(
                str(c) for c in (_get(ev, "required_tyres") or ())),
        }
    else:
        payload = {
            "car":                  legacy.get("car", "") or "Unknown",
            "track":                legacy.get("track", ""),
            "race_laps":            _as_int(legacy.get("total_laps"), 25),
            "duration_mins":        _as_int(legacy.get("race_duration_minutes"), 0),
            "mandatory_stops":      _as_int(legacy.get("mandatory_stops"), 0),
            "refuel_rate_lps":      _as_float(legacy.get("refuel_speed_lps"), 0.0),
            "pit_loss_secs":        _as_float(legacy.get("pit_loss_secs"), 0.0),
            "tuning_locked":        not bool(legacy.get("tuning", True)),
            "allowed_tuning":       tuple(legacy.get("allowed_tuning_categories") or ()),
            "tyre_wear_multiplier": _as_float(legacy.get("tyre_wear_multiplier"), 1.0),
            "fuel_multiplier":      _as_float(legacy.get("fuel_multiplier"), 1.0),
            "avail_tyres":          tuple(legacy.get("avail_tyres") or ()),
            "required_tyres":       tuple(legacy.get("required_tyres") or ()),
            "race_type":            legacy.get("race_type", "lap"),
            "track_location_id":    _as_str(legacy.get("track_location_id")),
            "layout_id":            _as_str(legacy.get("layout_id")),
            "mandatory_compounds_str": _as_str(legacy.get("mandatory_compounds")) or "",
        }

    # Resolve discipline from session_type (OFR-2 AC8).
    # session_type is the setup's declared purpose — it wins over anything else.
    try:
        from data.setup_context import normalise_purpose as _np
        _disc = _np(session_type).value
    except Exception:  # pragma: no cover - defensive
        _disc = "unknown"

    core = _build_core(payload, source, event_context, strategy_context,
                       setup_snapshot, track_context, warnings)
    return SetupAISnapshot(core=core, discipline=_disc, **payload)
