"""StrategyContext — canonical read model for the active strategy plan.

Added by the **State Consolidation 2 — StrategyContext** sprint (2026-07-03) as
the second concrete step of the target architecture proposed in
`docs/PRODUCT_CONSOLIDATION_AUDIT.md` (§7). It follows
`data/event_context.py` (State Consolidation 1) and depends on it.

Why this exists
---------------
``config["strategy"]`` is a "god dict" that mixes two very different kinds of
truth:

* **event / race configuration** — track, car, race type, duration/laps, tyre
  wear + fuel multipliers, refuel rate, BoP / tuning legality. This is now owned
  by :class:`data.event_context.EventContext`.
* **strategy-plan state** — the selected/generated stint plan, number of stops,
  fuel burn per lap, degradation assumptions, the derived ``config_id`` match
  key, and the analysis tolerances.

``StrategyContext`` owns *only* the second kind. It reads event/race rules from
an :class:`EventContext` rather than duplicating them, so the two can never
drift. The AI race-plan prompt can freeze a
:class:`StrategyPromptSnapshot` combining a consistent EventContext + this
StrategyContext, preventing a prompt from mixing stale and fresh state.

Ownership boundary
------------------
StrategyContext owns: active ``config_id``, the stint plan, planned stops, pit
laps/windows, fuel burn per lap, optional starting fuel / fuel margin / refuel
requirement, tyre-degradation assumptions (incl. ``degradation_consecutive_laps``),
the analysis tolerances, the strategy source, a strategy change marker, and the
event change marker it was built against.

It must **not** own: selected event, car, track/layout, race type, race
duration/lap count, tyre wear multiplier, fuel multiplier, refuel rate,
BoP/tuning legality, allowed setup changes, telemetry packets, lap validity,
setup diagnosis, track-map geometry, AI logs, or driver learning history. Those
event/race fields are read from :class:`EventContext`.

Purity
------
No PyQt6, no DB, no I/O — builders take plain dicts (the legacy
``config["strategy"]`` snapshot) and an EventContext. This keeps the module
unit-testable without a QApplication (the project's test convention) and free of
import cycles. ``config["strategy"]`` is intentionally *not* deleted this sprint;
it remains as legacy compatibility.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, asdict
from enum import Enum
from typing import Optional, Tuple, TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - typing only
    from data.event_context import EventContext


STRATEGY_CONTEXT_SCHEMA = "strategy_context_v1"
STRATEGY_PROMPT_SNAPSHOT_SCHEMA = "strategy_prompt_snapshot_v1"


class StrategyContextSource(str, Enum):
    """Where a StrategyContext was resolved from."""
    EMPTY = "empty"                      # no strategy state at all
    LEGACY_STRATEGY = "legacy_strategy"  # built from config["strategy"]
    GENERATED = "generated"              # built from a generated StrategyOption plan


# --------------------------------------------------------------------------- #
# Safe coercion helpers (never raise) — mirror data/event_context.py
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


def _as_opt_float(v) -> Optional[float]:
    """Coerce to float, but keep ``None`` (an *absent* optional) as ``None``."""
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _as_opt_bool(v) -> Optional[bool]:
    """Coerce to bool, but keep an *absent* optional as ``None``."""
    if v is None or v == "":
        return None
    if isinstance(v, str):
        return v.strip().lower() in ("1", "true", "yes", "on")
    try:
        return bool(v)
    except Exception:  # pragma: no cover - defensive
        return None


# --------------------------------------------------------------------------- #
# Stint plan entry
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class StintPlanEntry:
    """One planned stint. Mirrors the legacy ``config["strategy"]["stops"]``
    dict shape (``{laps, compound, ref_lap_ms, pace_threshold_ms}``)."""
    index: int
    compound: str
    laps: int
    ref_lap_ms: int = 0
    pace_threshold_ms: int = 0

    def to_dict(self) -> dict:
        return {
            "laps": self.laps,
            "compound": self.compound,
            "ref_lap_ms": self.ref_lap_ms,
            "pace_threshold_ms": self.pace_threshold_ms,
        }


def _parse_stint_plan(raw) -> Tuple[StintPlanEntry, ...]:
    """Parse a legacy stops list into typed stint entries. Never raises."""
    if not isinstance(raw, (list, tuple)):
        return ()
    entries = []
    for i, d in enumerate(raw):
        if not isinstance(d, dict):
            continue
        entries.append(
            StintPlanEntry(
                index=i + 1,
                compound=_as_str(d.get("compound"), "Unknown"),
                laps=_as_int(d.get("laps"), 0),
                ref_lap_ms=_as_int(d.get("ref_lap_ms"), 0),
                pace_threshold_ms=_as_int(d.get("pace_threshold_ms"), 0),
            )
        )
    return tuple(entries)


def _derive_pit_laps(stints: Tuple[StintPlanEntry, ...]) -> Tuple[int, ...]:
    """Lap numbers on which each pit stop occurs — the cumulative stint lengths
    excluding the final stint (no stop after the last stint)."""
    if len(stints) < 2:
        return ()
    pit_laps = []
    running = 0
    for s in stints[:-1]:
        running += max(0, s.laps)
        pit_laps.append(running)
    return tuple(pit_laps)


# --------------------------------------------------------------------------- #
# The read model
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class StrategyContext:
    """Immutable, normalised snapshot of the active strategy plan."""

    # Identity / match key
    config_id: str

    # Plan
    stint_plan: Tuple[StintPlanEntry, ...]
    planned_stops: int
    pit_laps: Tuple[int, ...]
    has_plan: bool

    # Fuel
    fuel_burn_per_lap: float
    starting_fuel: Optional[float]
    fuel_margin: Optional[float]
    refuel_required: Optional[bool]
    pit_loss_secs: float

    # Tyre degradation assumptions
    degradation_consecutive_laps: int
    tyre_degradation_available: bool

    # Strategy analysis tolerances
    lap_time_tolerance_ms: int
    fuel_tolerance_liters: float

    # Provenance / change markers
    source: StrategyContextSource = StrategyContextSource.EMPTY
    change_hash: str = ""
    event_change_hash: str = ""

    # -- convenience ------------------------------------------------------- #
    @property
    def has_active_strategy(self) -> bool:
        return self.source != StrategyContextSource.EMPTY

    @property
    def total_planned_laps(self) -> int:
        return sum(max(0, s.laps) for s in self.stint_plan)

    @property
    def has_fuel_burn(self) -> bool:
        return self.fuel_burn_per_lap > 0

    def compound_sequence(self) -> Tuple[str, ...]:
        return tuple(s.compound for s in self.stint_plan)

    def summary_line(self) -> str:
        """One-line human summary for a status label."""
        if not self.has_plan:
            burn = f"{self.fuel_burn_per_lap:g}" if self.fuel_burn_per_lap > 0 else "—"
            return f"No strategy plan  |  Fuel burn: {burn} L/lap"
        seq = " → ".join(self.compound_sequence()) or "—"
        stops_word = "stop" if self.planned_stops == 1 else "stops"
        burn = f"{self.fuel_burn_per_lap:g}" if self.fuel_burn_per_lap > 0 else "—"
        return (
            f"Plan: {len(self.stint_plan)} stints ({self.planned_stops} {stops_word})  |  "
            f"{seq}  |  Fuel burn: {burn} L/lap"
        )

    def to_summary_lines(self) -> list:
        """Multi-line summary suitable for a small overview panel."""
        lines = []
        if self.has_plan:
            lines.append(
                f"Stint plan: {len(self.stint_plan)} stints, "
                f"{self.planned_stops} stop{'' if self.planned_stops == 1 else 's'}"
            )
            lines.append(f"Compounds: {' → '.join(self.compound_sequence()) or '—'}")
            if self.pit_laps:
                lines.append(f"Pit on lap: {', '.join(str(x) for x in self.pit_laps)}")
        else:
            lines.append("Stint plan: none")
        lines.append(
            f"Fuel burn: {self.fuel_burn_per_lap:g} L/lap"
            if self.fuel_burn_per_lap > 0 else "Fuel burn: not calibrated"
        )
        if self.starting_fuel is not None:
            lines.append(f"Starting fuel: {self.starting_fuel:g} L")
        if self.fuel_margin is not None:
            lines.append(f"Fuel margin: {self.fuel_margin:g} L")
        return lines

    def to_dict(self) -> dict:
        d = asdict(self)
        d["source"] = self.source.value
        d["stint_plan"] = [s.to_dict() for s in self.stint_plan]
        d["pit_laps"] = list(self.pit_laps)
        d["schema"] = STRATEGY_CONTEXT_SCHEMA
        return d


@dataclass(frozen=True)
class StrategyContextValidationResult:
    """Validation result that keeps strategy-input problems separate from
    event-input problems, so callers can tell the user which side is missing."""
    ok: bool
    strategy_warnings: Tuple[str, ...] = ()
    strategy_missing: Tuple[str, ...] = ()
    event_warnings: Tuple[str, ...] = ()
    event_missing: Tuple[str, ...] = ()

    @property
    def warnings(self) -> Tuple[str, ...]:
        """All warnings, strategy first then event — for a single banner."""
        return tuple(self.strategy_warnings) + tuple(self.event_warnings)


# --------------------------------------------------------------------------- #
# Builder / adapter
# --------------------------------------------------------------------------- #
def _canonical_change_fields(**kw) -> dict:
    """The subset of fields that define whether the *strategy* changed. Excludes
    provenance (source), the hash itself, and any event field (those are tracked
    separately via ``event_change_hash``)."""
    return {
        "config_id": kw["config_id"],
        "stint_plan": [s.to_dict() for s in kw["stint_plan"]],
        "fuel_burn_per_lap": kw["fuel_burn_per_lap"],
        "starting_fuel": kw["starting_fuel"],
        "fuel_margin": kw["fuel_margin"],
        "refuel_required": kw["refuel_required"],
        "pit_loss_secs": kw["pit_loss_secs"],
        "degradation_consecutive_laps": kw["degradation_consecutive_laps"],
        "tyre_degradation_available": kw["tyre_degradation_available"],
        "lap_time_tolerance_ms": kw["lap_time_tolerance_ms"],
        "fuel_tolerance_liters": kw["fuel_tolerance_liters"],
    }


def compute_change_hash(fields: dict) -> str:
    """Stable 12-char hash over the canonical strategy fields — a change marker
    so consumers can cheaply detect that the strategy plan changed and
    invalidate any derived snapshot. Deterministic (no time / randomness)."""
    blob = json.dumps(fields, sort_keys=True, default=str)
    return hashlib.sha1(blob.encode("utf-8")).hexdigest()[:12]


def build_strategy_context(
    *,
    strategy: Optional[dict] = None,
    event_context: Optional["EventContext"] = None,
    tyre_degradation=None,
    source: Optional[StrategyContextSource] = None,
) -> StrategyContext:
    """Build the canonical StrategyContext from the current app state.

    Parameters
    ----------
    strategy : dict | None
        The legacy ``config["strategy"]`` dict. Supplies strategy-plan fields:
        ``stops`` (stint plan), ``fuel_burn_per_lap``, ``config_id``,
        ``degradation_consecutive_laps``, ``pit_loss_secs`` and the analysis
        tolerances. Event/race rule fields present in this dict are *ignored* —
        they belong to EventContext.
    event_context : EventContext | None
        The canonical event/race read model. Only its ``change_hash`` is stored
        here (so a StrategyContext knows which event it was built against);
        event fields are never copied into StrategyContext.
    tyre_degradation : optional
        The current tyre-degradation cache/analysis (any truthy object marks it
        available). Kept opaque — StrategyContext records only that degradation
        data exists, not its internals.
    source : StrategyContextSource | None
        Override the provenance (e.g. ``GENERATED`` when built from an AI plan).
        Defaults to ``LEGACY_STRATEGY`` when any strategy data is present,
        ``EMPTY`` otherwise.

    Never raises. Returns an EMPTY-source context when nothing is available.
    """
    strategy = strategy or {}
    has_strategy = bool(strategy)

    stint_plan = _parse_stint_plan(strategy.get("stops"))
    has_plan = bool(stint_plan)
    planned_stops = max(0, len(stint_plan) - 1) if stint_plan else 0
    pit_laps = _derive_pit_laps(stint_plan)

    fuel_burn_per_lap = _as_float(strategy.get("fuel_burn_per_lap"), 0.0)
    starting_fuel = _as_opt_float(strategy.get("starting_fuel"))
    fuel_margin = _as_opt_float(strategy.get("fuel_margin"))
    refuel_required = _as_opt_bool(strategy.get("refuel_required"))
    pit_loss_secs = _as_float(strategy.get("pit_loss_secs"), 0.0)

    degradation_consecutive_laps = _as_int(strategy.get("degradation_consecutive_laps"), 2)
    tyre_degradation_available = bool(tyre_degradation)

    lap_time_tolerance_ms = _as_int(strategy.get("lap_time_tolerance_ms"), 0)
    fuel_tolerance_liters = _as_float(strategy.get("fuel_tolerance_liters"), 0.0)

    config_id = _as_str(strategy.get("config_id"))

    if source is None:
        resolved_source = (
            StrategyContextSource.LEGACY_STRATEGY if has_strategy
            else StrategyContextSource.EMPTY
        )
    else:
        resolved_source = source

    event_change_hash = _as_str(getattr(event_context, "change_hash", "")) if event_context else ""

    canonical = _canonical_change_fields(
        config_id=config_id, stint_plan=stint_plan,
        fuel_burn_per_lap=fuel_burn_per_lap, starting_fuel=starting_fuel,
        fuel_margin=fuel_margin, refuel_required=refuel_required,
        pit_loss_secs=pit_loss_secs,
        degradation_consecutive_laps=degradation_consecutive_laps,
        tyre_degradation_available=tyre_degradation_available,
        lap_time_tolerance_ms=lap_time_tolerance_ms,
        fuel_tolerance_liters=fuel_tolerance_liters,
    )
    change_hash = "" if resolved_source == StrategyContextSource.EMPTY else compute_change_hash(canonical)

    return StrategyContext(
        config_id=config_id,
        stint_plan=stint_plan,
        planned_stops=planned_stops,
        pit_laps=pit_laps,
        has_plan=has_plan,
        fuel_burn_per_lap=fuel_burn_per_lap,
        starting_fuel=starting_fuel,
        fuel_margin=fuel_margin,
        refuel_required=refuel_required,
        pit_loss_secs=pit_loss_secs,
        degradation_consecutive_laps=degradation_consecutive_laps,
        tyre_degradation_available=tyre_degradation_available,
        lap_time_tolerance_ms=lap_time_tolerance_ms,
        fuel_tolerance_liters=fuel_tolerance_liters,
        source=resolved_source,
        change_hash=change_hash,
        event_change_hash=event_change_hash,
    )


def empty_strategy_context() -> StrategyContext:
    """A well-formed EMPTY context (no active strategy)."""
    return build_strategy_context()


# --------------------------------------------------------------------------- #
# Validation
# --------------------------------------------------------------------------- #
def validate_strategy_context(
    ctx: StrategyContext,
    event_context: Optional["EventContext"] = None,
) -> StrategyContextValidationResult:
    """Return non-crashing validation warnings, keeping strategy-input problems
    separate from event-input problems.

    Missing optional fields produce warnings, never exceptions — callers decide
    whether to block. When ``event_context`` is provided, its own validation
    warnings are folded into the ``event_*`` fields so the user can tell whether
    it is the *strategy* or the *event* that is under-specified.
    """
    strat_warnings = []
    strat_missing = []

    if ctx.source == StrategyContextSource.EMPTY:
        strat_warnings.append("No strategy plan — build one in Strategy Builder.")
        strat_missing.append("strategy")
    else:
        if not ctx.has_plan:
            strat_warnings.append(
                "No stint plan set — add stints or run Race Strategy Analysis."
            )
            strat_missing.append("stint_plan")
        if ctx.fuel_burn_per_lap <= 0:
            strat_warnings.append(
                "Fuel burn per lap not calibrated — complete practice laps first."
            )
            strat_missing.append("fuel_burn_per_lap")

    event_warnings: Tuple[str, ...] = ()
    event_missing: Tuple[str, ...] = ()
    if event_context is not None:
        try:
            from data.event_context import validate_event_context
            evt_res = validate_event_context(event_context)
            event_warnings = tuple(evt_res.warnings)
            event_missing = tuple(evt_res.missing_fields)
        except Exception:  # pragma: no cover - defensive
            event_warnings = ()
            event_missing = ()

    ok = not strat_warnings and not event_warnings
    return StrategyContextValidationResult(
        ok=ok,
        strategy_warnings=tuple(strat_warnings),
        strategy_missing=tuple(strat_missing),
        event_warnings=event_warnings,
        event_missing=event_missing,
    )


# --------------------------------------------------------------------------- #
# Frozen prompt snapshot (EventContext race config + StrategyContext plan)
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class StrategyPromptSnapshot:
    """An immutable, value-copied snapshot combining the event race configuration
    (from EventContext) and the strategy assumptions (from StrategyContext) for
    AI race-plan prompt construction.

    Because every field is a copied primitive (or a tuple of frozen entries),
    the snapshot stays stable even if ``config["strategy"]`` or the source
    contexts are mutated after it is built — the whole point is to stop a prompt
    from mixing stale and fresh state.
    """
    schema: str

    # Identity — combined marker so equal event+strategy state yields equal id.
    snapshot_id: str
    event_change_hash: str
    strategy_change_hash: str

    # --- frozen event/race configuration (read from EventContext) --- #
    track: str
    car: str
    track_location_id: str
    layout_id: str
    race_type: str
    laps: int
    race_duration_minutes: int
    tyre_wear_multiplier: float
    fuel_multiplier: float
    refuel_rate_lps: float
    bop_enabled: bool
    tuning_allowed: bool

    # --- frozen strategy assumptions (read from StrategyContext) --- #
    config_id: str
    fuel_burn_per_lap: float
    planned_stops: int
    stint_plan: Tuple[StintPlanEntry, ...]
    pit_laps: Tuple[int, ...]
    starting_fuel: Optional[float]
    fuel_margin: Optional[float]
    refuel_required: Optional[bool]
    degradation_consecutive_laps: int
    pit_loss_secs: float

    def to_dict(self) -> dict:
        d = asdict(self)
        d["stint_plan"] = [s.to_dict() for s in self.stint_plan]
        d["pit_laps"] = list(self.pit_laps)
        return d


def build_strategy_prompt_snapshot(
    strategy_context: StrategyContext,
    event_context: Optional["EventContext"] = None,
) -> StrategyPromptSnapshot:
    """Freeze a consistent EventContext + StrategyContext into one snapshot.

    Event/race fields are read from ``event_context`` (never from the strategy
    dict); strategy fields from ``strategy_context``. Defensive — reads event
    fields via ``getattr`` so a missing/odd event_context yields sensible
    defaults rather than raising.
    """
    ev = event_context
    event_change_hash = _as_str(getattr(ev, "change_hash", "")) if ev else strategy_context.event_change_hash
    strategy_change_hash = strategy_context.change_hash

    snapshot_id = compute_change_hash(
        {"event": event_change_hash, "strategy": strategy_change_hash}
    )

    return StrategyPromptSnapshot(
        schema=STRATEGY_PROMPT_SNAPSHOT_SCHEMA,
        snapshot_id=snapshot_id,
        event_change_hash=event_change_hash,
        strategy_change_hash=strategy_change_hash,
        # event/race configuration
        track=_as_str(getattr(ev, "track", "")),
        car=_as_str(getattr(ev, "car", "")),
        track_location_id=_as_str(getattr(ev, "track_location_id", "")),
        layout_id=_as_str(getattr(ev, "layout_id", "")),
        race_type=_as_str(getattr(ev, "race_type", "lap")) or "lap",
        laps=_as_int(getattr(ev, "laps", 0)),
        race_duration_minutes=_as_int(getattr(ev, "race_duration_minutes", 0)),
        tyre_wear_multiplier=_as_float(getattr(ev, "tyre_wear_multiplier", 1.0), 1.0),
        fuel_multiplier=_as_float(getattr(ev, "fuel_multiplier", 1.0), 1.0),
        refuel_rate_lps=_as_float(getattr(ev, "refuel_rate_lps", 0.0), 0.0),
        bop_enabled=bool(getattr(ev, "bop_enabled", False)),
        tuning_allowed=bool(getattr(ev, "tuning_allowed", True)),
        # strategy assumptions
        config_id=strategy_context.config_id,
        fuel_burn_per_lap=strategy_context.fuel_burn_per_lap,
        planned_stops=strategy_context.planned_stops,
        stint_plan=strategy_context.stint_plan,
        pit_laps=strategy_context.pit_laps,
        starting_fuel=strategy_context.starting_fuel,
        fuel_margin=strategy_context.fuel_margin,
        refuel_required=strategy_context.refuel_required,
        degradation_consecutive_laps=strategy_context.degradation_consecutive_laps,
        pit_loss_secs=strategy_context.pit_loss_secs,
    )
