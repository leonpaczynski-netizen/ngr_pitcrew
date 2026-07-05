"""Home Dashboard view model — the Race Engineer Command Centre read model.

Added by the **Home Dashboard Build** sprint (2026-07-03). This is the pure
display logic behind the home/overview surface that
`docs/PRODUCT_CONSOLIDATION_AUDIT.md` §1.1 identified as never built
(`REQUIREMENTS.md` §12.2 — "Suggested next action").

What it does
------------
Converts the four canonical read models (EventContext, StrategyContext,
SetupContext, TrackContext), the AI snapshot status, and
``ui.product_flow.build_flow_state_summary()`` into display-ready cards:

  A. Race Setup          — the active event and its race rules
  B. Track Intelligence  — track/layout identity + model data availability
  C. Setup Brain         — the latest setup recommendation and its freshness
  D. Strategy Brain      — the strategy plan and its freshness
  E. AI Input Safety     — whether AI paths use clean frozen snapshots
  F. Next Best Action    — the single suggested next step

Display-only. This module is NOT a new owner of state:
* it only **reads** the contexts the callers pass in,
* it writes nothing (no config, no DB, no files, no telemetry),
* it never invents readiness — every flag echoes what a context reported.

Purity
------
No PyQt6, no AI, no DB, no network, no file I/O — matching the project's
no-Qt test convention. Every input is duck-typed and read through a safe
getter, and every section builder is defensive, so malformed or missing
context data can never raise out of ``build_home_dashboard_state()``.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional, Tuple


HOME_DASHBOARD_SCHEMA = "home_dashboard_v1"


# --------------------------------------------------------------------------- #
# Statuses
# --------------------------------------------------------------------------- #
class HomeDashboardStatus(str, Enum):
    """Traffic-light status for one dashboard card."""
    READY = "ready"          # present and no known problems
    ATTENTION = "attention"  # present but stale / mismatched / has warnings
    MISSING = "missing"      # not available yet — a normal to-do, not an error
    BLOCKED = "blocked"      # something downstream cannot run because of this


_STATUS_LABELS = {
    HomeDashboardStatus.READY: "Ready",
    HomeDashboardStatus.ATTENTION: "Needs attention",
    HomeDashboardStatus.MISSING: "Not set up yet",
    HomeDashboardStatus.BLOCKED: "Blocked",
}


def status_label(status: HomeDashboardStatus) -> str:
    """Plain-English label for a card status."""
    return _STATUS_LABELS.get(status, "Unknown")


# --------------------------------------------------------------------------- #
# Display structures
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class HomeDashboardWarning:
    """One plain-English warning attached to a card."""
    section: str          # card key it belongs to
    message: str
    kind: str = "warning"  # "warning" | "stale" | "blocker"


@dataclass(frozen=True)
class HomeDashboardCard:
    """One display card. ``lines`` are ready-to-render "Label: value" rows."""
    key: str
    title: str
    status: HomeDashboardStatus
    headline: str
    lines: Tuple[str, ...] = ()
    warnings: Tuple[HomeDashboardWarning, ...] = ()

    @property
    def status_text(self) -> str:
        return status_label(self.status)


@dataclass(frozen=True)
class HomeDashboardAction:
    """A recommended user action (used for the next-best-action banner)."""
    action: str
    tab: str


@dataclass(frozen=True)
class HomeDashboardNextAction:
    """The single suggested next step plus overall journey progress."""
    action: str
    tab: str
    complete: bool
    ready_count: int
    pending_count: int
    pending: Tuple[str, ...] = ()

    @property
    def progress_text(self) -> str:
        total = self.ready_count + self.pending_count
        if total <= 0:
            return ""
        return f"{self.ready_count} of {total} steps done"


@dataclass(frozen=True)
class HomeDashboardState:
    """The full dashboard: cards in display order + the next-action banner."""
    schema: str
    cards: Tuple[HomeDashboardCard, ...]
    next_action: HomeDashboardNextAction
    warnings: Tuple[HomeDashboardWarning, ...] = ()

    def card(self, key: str) -> Optional[HomeDashboardCard]:
        for c in self.cards:
            if c.key == key:
                return c
        return None


# Card keys (stable identifiers for tests / renderers)
CARD_RACE_SETUP = "race_setup"
CARD_TRACK = "track_intelligence"
CARD_SETUP = "setup_brain"
CARD_STRATEGY = "strategy_brain"
CARD_AI_SAFETY = "ai_input_safety"

CARD_ORDER = (CARD_RACE_SETUP, CARD_TRACK, CARD_SETUP, CARD_STRATEGY, CARD_AI_SAFETY)


# --------------------------------------------------------------------------- #
# Card → tool-tab navigation (Home Dashboard Promotion, 2026-07-03)
# --------------------------------------------------------------------------- #
# Each card maps to the STABLE tab key of the tool the user would open to act on
# it (see ui/tab_registry.py). Keys — never visible labels — so the ⚙ tool-tab
# decoration can never affect navigation. The Qt layer resolves a key to an
# index through the registry and selects it with ``select_tab``; this table is
# pure data (tab_registry is pure Python too) so it stays unit-testable without
# a QApplication.
#
#   Race Setup         → Event Planner   (create/select the event, car, track)
#   Track Intelligence → Track Modelling (build/inspect the track model)
#   Setup Brain        → Setup Builder   (build/refine the car setup)
#   Strategy Brain     → Strategy Builder(build the race strategy)
#   AI Input Safety    → AI Log          (inspect the exact AI inputs/outputs)
from ui.tab_registry import (  # noqa: E402  (pure-Python import, no PyQt6)
    TAB_EVENT_PLANNER,
    TAB_TRACK_MODELLING,
    TAB_SETUP_BUILDER,
    TAB_STRATEGY_BUILDER,
    TAB_AI_LOG,
)

CARD_TAB_KEYS = {
    CARD_RACE_SETUP: TAB_EVENT_PLANNER,
    CARD_TRACK: TAB_TRACK_MODELLING,
    CARD_SETUP: TAB_SETUP_BUILDER,
    CARD_STRATEGY: TAB_STRATEGY_BUILDER,
    CARD_AI_SAFETY: TAB_AI_LOG,
}


def tab_key_for_card(card_key: str):
    """Stable tab key a Home card navigates to, or None when unmapped.

    Never raises — an unknown card key resolves to None so the Qt layer can
    fail safely and simply not offer navigation for that card.
    """
    return CARD_TAB_KEYS.get(card_key)


# --------------------------------------------------------------------------- #
# Safe getters (never raise) — mirror the data/*_context modules
# --------------------------------------------------------------------------- #
def _get(obj, name, default=None):
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(name, default)
    try:
        value = getattr(obj, name, default)
    except Exception:
        return default
    return default if value is None else value


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


def _enum_value(v, default: str = "") -> str:
    if v is None:
        return default
    val = getattr(v, "value", v)
    return _as_str(val, default) or default


def _tick(flag, present: str, absent: str) -> str:
    return present if bool(flag) else absent


# --------------------------------------------------------------------------- #
# Plain-English vocabularies (no internal enum values / ids leak to display)
# --------------------------------------------------------------------------- #
_SETUP_SOURCE_LABELS = {
    "ai": "AI recommendation (telemetry fix)",
    "generated": "AI recommendation (built from scratch)",
    "manual": "Entered manually",
    "saved_db": "Loaded from saved setups",
    "legacy_config": "Loaded from saved setups",
    "empty": "None",
}

_PURPOSE_LABELS = {
    "qualifying": "Qualifying",
    "race": "Race",
    "practice": "Practice",
    "test": "Test",
    "unknown": "Not set",
}

_MODELLING_STATUS_LABELS = {
    "not_modelled": "Not modelled yet",
    "seed_only": "Basic track info only",
    "calibrated": "Calibrated from your laps",
    "reviewed": "Reviewed",
    "accepted": "Accepted",
    "modelled": "Modelled",
    "": "Unknown",
}


def _modelling_status_text(raw: str) -> str:
    key = _as_str(raw).strip().lower()
    return _MODELLING_STATUS_LABELS.get(key, _as_str(raw).replace("_", " ").capitalize() or "Unknown")


# --------------------------------------------------------------------------- #
# Section A — Race Setup
# --------------------------------------------------------------------------- #
def _build_race_setup_card(event_context, track_context) -> HomeDashboardCard:
    has_event = bool(_get(event_context, "has_active_event", False))
    if not has_event:
        return HomeDashboardCard(
            key=CARD_RACE_SETUP,
            title="Race Setup",
            status=HomeDashboardStatus.MISSING,
            headline="No active event",
            lines=(
                "Create or select an event in Event Planner, then click "
                "'Set as Active'.",
            ),
        )

    ev = event_context
    name = _as_str(_get(ev, "event_name")) or "(unnamed event)"
    car = _as_str(_get(ev, "car")) or "Not selected"
    track = _as_str(_get(ev, "track")) or "Not selected"
    layout = _as_str(_get(_get(track_context, "identity"), "layout_display_name"))

    race_type = _as_str(_get(ev, "race_type")) or "lap"
    if race_type == "timed":
        mins = _as_int(_get(ev, "race_duration_minutes"))
        length = f"Timed race, {mins} minutes" if mins > 0 else "Timed race, duration not set"
    else:
        laps = _as_int(_get(ev, "laps"))
        length = f"Lap race, {laps} lap{'s' if laps != 1 else ''}" if laps > 0 \
            else "Lap race, lap count not set"

    tuning_allowed = bool(_get(ev, "tuning_allowed", True))
    bop = bool(_get(ev, "bop_enabled", False))
    wear = _as_float(_get(ev, "tyre_wear_multiplier"), 1.0)
    fuel = _as_float(_get(ev, "fuel_multiplier"), 1.0)
    refuel = _as_float(_get(ev, "refuel_rate_lps"), 0.0)
    stops = _as_int(_get(ev, "mandatory_stops"), 0)
    avail = tuple(_get(ev, "available_tyres") or ())
    required = tuple(_get(ev, "required_tyres") or ())
    damage = _as_str(_get(ev, "damage"))

    lines = [
        f"Event: {name}",
        f"Car: {car}",
        f"Track: {track}" + (f" — {layout}" if layout else ""),
        f"Race: {length}",
        f"Tyre wear: {wear:g}×   Fuel use: {fuel:g}×",
        f"BoP: {'On' if bop else 'Off'}   Tuning: {'Allowed' if tuning_allowed else 'Locked'}",
    ]
    if refuel > 0:
        lines.append(f"Refuelling speed: {refuel:g} L/s")
    if stops > 0:
        lines.append(f"Mandatory pit stops: {stops}")
    if avail:
        lines.append("Available tyres: " + ", ".join(_as_str(t) for t in avail))
    if required:
        lines.append("Required tyres: " + ", ".join(_as_str(t) for t in required))
    if damage:
        lines.append(f"Damage: {damage}")

    warnings = []
    try:
        from data.event_context import validate_event_context
        result = validate_event_context(ev)
        for w in _get(result, "warnings") or ():
            warnings.append(HomeDashboardWarning(CARD_RACE_SETUP, _as_str(w)))
    except Exception:
        pass

    status = HomeDashboardStatus.ATTENTION if warnings else HomeDashboardStatus.READY
    headline = f"{name} — {car if car != 'Not selected' else 'no car'} at " \
               f"{track if track != 'Not selected' else 'no track'}"
    return HomeDashboardCard(
        key=CARD_RACE_SETUP, title="Race Setup", status=status,
        headline=headline, lines=tuple(lines), warnings=tuple(warnings),
    )


# --------------------------------------------------------------------------- #
# Section B — Track Intelligence
# --------------------------------------------------------------------------- #
def _build_track_card(track_context, event_context) -> HomeDashboardCard:
    identity = _get(track_context, "identity")
    source_val = _enum_value(_get(track_context, "source"), "empty")
    track_name = (
        _as_str(_get(identity, "track_display_name"))
        or _as_str(_get(identity, "track_location_id"))
    )
    layout_name = (
        _as_str(_get(identity, "layout_display_name"))
        or _as_str(_get(identity, "layout_id"))
    )

    if track_context is None or source_val == "empty" or not (track_name or layout_name):
        return HomeDashboardCard(
            key=CARD_TRACK,
            title="Track Intelligence",
            status=HomeDashboardStatus.MISSING,
            headline="No track selected",
            lines=("Select a track in Event Planner or Track Modelling.",),
        )

    av = _get(track_context, "availability")
    geo = _get(track_context, "geometry")
    align = _get(track_context, "alignment")

    lines = [
        f"Track: {track_name or 'Not selected'}",
        f"Layout: {layout_name or 'Not selected'}",
        "Track model: " + _modelling_status_text(_get(geo, "modelling_status")),
        "Track info (seed): "
        + _tick(_get(av, "seed_metadata_available"), "available", "not available"),
        "Track shape (geometry): "
        + _tick(_get(av, "seed_geometry_available"), "available", "not available"),
        "Reference lap path: "
        + _tick(_get(av, "reference_path_available"), "built", "not built"),
        "Corner position map: "
        + _tick(_get(av, "station_map_available"), "built", "not built"),
        "Reviewed model: "
        + _tick(_get(av, "reviewed_model_available"), "saved", "none"),
        "Accepted model: "
        + _tick(_get(av, "accepted_model_available"), "accepted", "not accepted"),
    ]

    warnings = []
    identity_complete = bool(_get(identity, "is_complete", False))
    if not identity_complete:
        warnings.append(HomeDashboardWarning(
            CARD_TRACK, "Track or layout identity is missing — select both in "
                        "Track Modelling before building track data.",
            kind="blocker",
        ))

    # Live mapping readiness — echo the context's own gate, never invent it.
    can_map = bool(_get(track_context, "can_attempt_live_mapping", False))
    if can_map:
        lines.append("Live corner mapping: ready to attempt")
    else:
        lines.append("Live corner mapping: not available")
        blockers = ()
        try:
            fn = getattr(track_context, "live_mapping_blockers", None)
            if callable(fn):
                blockers = tuple(fn() or ())
        except Exception:
            blockers = ()
        for b in blockers:
            warnings.append(HomeDashboardWarning(
                CARD_TRACK, f"Live mapping is blocked: {_as_str(b)}", kind="blocker"))
        if not blockers:
            warnings.append(HomeDashboardWarning(
                CARD_TRACK, "Track model is unavailable for live mapping.",
                kind="blocker"))

    # Mismatch / staleness against the active event.
    try:
        fn = getattr(track_context, "mismatches_event", None)
        if callable(fn) and event_context is not None and fn(event_context):
            warnings.append(HomeDashboardWarning(
                CARD_TRACK,
                "The track selected in Track Modelling does not match the "
                "active event's track.",
                kind="stale",
            ))
    except Exception:
        pass

    if warnings:
        status = (
            HomeDashboardStatus.BLOCKED
            if any(w.kind == "blocker" for w in warnings) and not can_map
            else HomeDashboardStatus.ATTENTION
        )
    else:
        status = HomeDashboardStatus.READY
    headline = f"{track_name}" + (f" — {layout_name}" if layout_name else "")
    return HomeDashboardCard(
        key=CARD_TRACK, title="Track Intelligence", status=status,
        headline=headline, lines=tuple(lines), warnings=tuple(warnings),
    )


# --------------------------------------------------------------------------- #
# Section C — Setup Brain
# --------------------------------------------------------------------------- #
def _build_setup_card(setup_context, event_context, strategy_snapshot) -> HomeDashboardCard:
    has_setup = bool(_get(setup_context, "has_active_setup", False))
    if not has_setup:
        return HomeDashboardCard(
            key=CARD_SETUP,
            title="Setup Brain",
            status=HomeDashboardStatus.MISSING,
            headline="No setup recommendation yet",
            lines=("Build or analyse a car setup in Setup Builder.",),
        )

    sc = setup_context
    label = _as_str(_get(sc, "setup_label")) or "(unnamed setup)"
    purpose = _PURPOSE_LABELS.get(_enum_value(_get(sc, "purpose"), "unknown"), "Not set")
    source = _SETUP_SOURCE_LABELS.get(_enum_value(_get(sc, "source"), "empty"),
                                      "Unknown source")
    car = _as_str(_get(sc, "car"))
    track = _as_str(_get(sc, "track"))
    adjustments = tuple(_get(sc, "adjustments") or ())
    primary_issue = _as_str(_get(sc, "primary_issue"))
    confidence = _as_str(_get(sc, "confidence"))
    applied = _get(sc, "applied")

    lines = [
        f"Setup: {label}",
        f"For: {purpose}",
        f"Source: {source}",
        f"Car: {car or 'Not recorded'}   Track: {track or 'Not recorded'}",
    ]
    if adjustments:
        n = len(adjustments)
        lines.append(f"Recommended changes: {n}")
    if primary_issue:
        lines.append(f"Main issue addressed: {primary_issue}")
    if confidence:
        lines.append(f"Confidence: {confidence}")
    if applied is True:
        lines.append("Applied to the car: Yes")
    elif applied is False:
        lines.append("Applied to the car: Not yet")

    warnings = []

    # Identity
    try:
        if callable(getattr(sc, "is_missing_identity", None)) and sc.is_missing_identity():
            warnings.append(HomeDashboardWarning(
                CARD_SETUP,
                "This setup has no car or track identity recorded, so it "
                "cannot be matched to the event.",
            ))
    except Exception:
        pass

    # Freshness vs event
    try:
        if callable(getattr(sc, "is_stale_for_event", None)) and event_context is not None:
            if sc.is_stale_for_event(event_context):
                warnings.append(HomeDashboardWarning(
                    CARD_SETUP,
                    "Setup was generated for an older event version — the "
                    "event settings changed after it was built.",
                    kind="stale",
                ))
            elif callable(getattr(sc, "matches_event", None)) and sc.matches_event(event_context):
                lines.append("Built for the current event settings.")
    except Exception:
        pass

    # Freshness vs strategy
    try:
        if callable(getattr(sc, "is_stale_for_strategy", None)) and strategy_snapshot is not None:
            if sc.is_stale_for_strategy(strategy_snapshot):
                warnings.append(HomeDashboardWarning(
                    CARD_SETUP,
                    "Setup was generated before the strategy plan changed.",
                    kind="stale",
                ))
    except Exception:
        pass

    for w in tuple(_get(sc, "validation_warnings") or ()):
        warnings.append(HomeDashboardWarning(CARD_SETUP, _as_str(w)))

    status = HomeDashboardStatus.ATTENTION if warnings else HomeDashboardStatus.READY
    return HomeDashboardCard(
        key=CARD_SETUP, title="Setup Brain", status=status,
        headline=f"{label} ({purpose})",
        lines=tuple(lines), warnings=tuple(warnings),
    )


# --------------------------------------------------------------------------- #
# Section D — Strategy Brain
# --------------------------------------------------------------------------- #
def _build_strategy_card(strategy_context, event_context) -> HomeDashboardCard:
    has_strategy = bool(_get(strategy_context, "has_active_strategy", False))
    has_plan = bool(_get(strategy_context, "has_plan", False))
    if not has_strategy or (not has_plan and not _as_float(
            _get(strategy_context, "fuel_burn_per_lap"), 0.0) > 0):
        # No plan and no calibrated fuel burn — nothing useful to show yet.
        if not has_plan:
            return HomeDashboardCard(
                key=CARD_STRATEGY,
                title="Strategy Brain",
                status=HomeDashboardStatus.MISSING,
                headline="No strategy plan yet",
                lines=("Run Race Strategy Analysis in Strategy Builder, then "
                       "apply a plan.",),
            )

    sc = strategy_context
    stints = tuple(_get(sc, "stint_plan") or ())
    planned_stops = _as_int(_get(sc, "planned_stops"), 0)
    pit_laps = tuple(_get(sc, "pit_laps") or ())
    fuel_burn = _as_float(_get(sc, "fuel_burn_per_lap"), 0.0)
    pit_loss = _as_float(_get(sc, "pit_loss_secs"), 0.0)
    starting_fuel = _get(sc, "starting_fuel")
    plan_id = _as_str(_get(sc, "config_id"))

    lines = []
    if has_plan:
        lines.append(
            f"Plan: {len(stints)} stint{'s' if len(stints) != 1 else ''}, "
            f"{planned_stops} pit stop{'s' if planned_stops != 1 else ''}"
        )
        compounds = " → ".join(
            _as_str(_get(s, "compound"), "Unknown") for s in stints)
        if compounds:
            lines.append(f"Tyres: {compounds}")
        if pit_laps:
            lines.append("Pit on lap: " + ", ".join(str(_as_int(x)) for x in pit_laps))
    else:
        lines.append("Plan: none applied yet")
    lines.append(
        f"Fuel burn: {fuel_burn:g} L per lap" if fuel_burn > 0
        else "Fuel burn: not calibrated yet — complete practice laps"
    )
    if starting_fuel is not None:
        lines.append(f"Starting fuel: {_as_float(starting_fuel):g} L")
    if pit_loss > 0:
        lines.append(f"Pit time: {pit_loss:g} s")
    if plan_id:
        lines.append(f"Plan match key: {plan_id}")

    warnings = []

    # Freshness vs event — compare the change markers both sides carry.
    own_event_hash = _as_str(_get(sc, "event_change_hash"))
    current_event_hash = _as_str(_get(event_context, "change_hash"))
    if own_event_hash and current_event_hash and own_event_hash != current_event_hash:
        warnings.append(HomeDashboardWarning(
            CARD_STRATEGY,
            "Strategy plan was built before the current event settings "
            "changed — rebuild it in Strategy Builder.",
            kind="stale",
        ))

    if has_plan and fuel_burn <= 0:
        warnings.append(HomeDashboardWarning(
            CARD_STRATEGY,
            "Fuel burn per lap is not calibrated — the plan's fuel numbers "
            "are estimates.",
        ))

    status = HomeDashboardStatus.ATTENTION if warnings else HomeDashboardStatus.READY
    if has_plan:
        headline = (f"{len(stints)} stints, {planned_stops} "
                    f"stop{'s' if planned_stops != 1 else ''}")
    else:
        headline = "Fuel data only — no plan applied"
    return HomeDashboardCard(
        key=CARD_STRATEGY, title="Strategy Brain", status=status,
        headline=headline, lines=tuple(lines), warnings=tuple(warnings),
    )


# --------------------------------------------------------------------------- #
# Section E — AI Input Safety
# --------------------------------------------------------------------------- #
def _resolve_snapshot_core(ai_snapshot):
    """Accept a use-case snapshot (has ``.core``) or a bare core object."""
    if ai_snapshot is None:
        return None
    core = _get(ai_snapshot, "core")
    if core is not None and _get(core, "snapshot_id") is not None:
        return core
    if _get(ai_snapshot, "snapshot_id") is not None:
        return ai_snapshot
    return None


def _build_ai_safety_card(ai_snapshot) -> HomeDashboardCard:
    core = _resolve_snapshot_core(ai_snapshot)
    if core is None:
        return HomeDashboardCard(
            key=CARD_AI_SAFETY,
            title="AI Input Safety",
            status=HomeDashboardStatus.MISSING,
            headline="AI input status unknown",
            lines=("No AI input snapshot is available to check.",),
        )

    source = _enum_value(_get(core, "source"), "empty")
    stale = tuple(_as_str(w) for w in (_get(core, "stale_warnings") or ()))
    build_warnings = tuple(_as_str(w) for w in (_get(core, "warnings") or ()))

    lines = []
    warnings = []

    if source == "contexts":
        lines.append("AI prompts use a frozen snapshot of the current event, "
                     "strategy, setup and track state.")
        status = HomeDashboardStatus.READY
        headline = "AI inputs are clean"
    elif source == "legacy_only":
        lines.append("No active event — AI would fall back to older saved "
                     "settings for this path.")
        warnings.append(HomeDashboardWarning(
            CARD_AI_SAFETY,
            "AI used legacy fallback inputs for this path — set an active "
            "event so prompts use the current settings.",
        ))
        status = HomeDashboardStatus.ATTENTION
        headline = "AI inputs use legacy fallback"
    else:
        lines.append("No event or saved settings available for AI prompts.")
        status = HomeDashboardStatus.MISSING
        headline = "No AI inputs available"

    for w in stale:
        warnings.append(HomeDashboardWarning(CARD_AI_SAFETY, w, kind="stale"))
    for w in build_warnings:
        if source == "legacy_only":
            continue  # already summarised above in plain English
        warnings.append(HomeDashboardWarning(CARD_AI_SAFETY, w))

    if warnings and status == HomeDashboardStatus.READY:
        status = HomeDashboardStatus.ATTENTION
        headline = "AI inputs need attention"
    return HomeDashboardCard(
        key=CARD_AI_SAFETY, title="AI Input Safety", status=status,
        headline=headline, lines=tuple(lines), warnings=tuple(warnings),
    )


# --------------------------------------------------------------------------- #
# Section F — Next Best Action (product_flow bridge)
# --------------------------------------------------------------------------- #
def build_flow_flags(
    *,
    event_context=None,
    strategy_context=None,
    setup_context=None,
    track_context=None,
    has_practice_laps: bool = False,
    has_valid_laps: bool = False,
    live_active: bool = False,
    learning_saved: bool = False,
) -> dict:
    """Derive the ``build_flow_state_summary`` flags from the contexts.

    Context-derived flags come straight from the read models; the telemetry/
    session flags (practice laps, live) are caller-supplied because those are
    owned by the telemetry layer, not by any of the four contexts.
    """
    flags = {
        "has_event": bool(_get(event_context, "has_active_event", False)),
        "has_car": bool(_as_str(_get(event_context, "car"))),
        "has_track": bool(_as_str(_get(event_context, "track"))),
        # Tuning rules are recorded on the event itself, so an active event
        # means the legality step has been captured (mirrors event_context.flow_flags).
        "tuning_confirmed": bool(_get(event_context, "has_active_event", False)),
        "has_setup": bool(_get(setup_context, "has_active_setup", False)),
        "has_strategy": bool(_get(strategy_context, "has_plan", False)),
        "has_practice_laps": bool(has_practice_laps),
        "has_valid_laps": bool(has_valid_laps),
        "live_active": bool(live_active),
        "learning_saved": bool(learning_saved),
    }
    # TrackContext is the canonical identity owner — it supersedes the event's
    # display-name-only view when it carries identity (mirrors track_context.flow_flags).
    ident = _get(track_context, "identity")
    if ident is not None and (
        _as_str(_get(ident, "track_display_name"))
        or _as_str(_get(ident, "track_location_id"))
    ):
        flags["has_track"] = True
    return flags


def _build_next_action(flags: dict) -> HomeDashboardNextAction:
    try:
        from ui.product_flow import build_flow_state_summary
        summary = build_flow_state_summary(**flags)
    except Exception:
        summary = {}
    ready = list(summary.get("ready") or [])
    pending = list(summary.get("pending") or [])
    return HomeDashboardNextAction(
        action=_as_str(summary.get("next_action")) or "Create or select an event",
        tab=_as_str(summary.get("next_tab")) or "Event Planner",
        complete=bool(summary.get("complete", False)),
        ready_count=len(ready),
        pending_count=len(pending),
        pending=tuple(_as_str(p) for p in pending),
    )


# --------------------------------------------------------------------------- #
# The builder
# --------------------------------------------------------------------------- #
def _fallback_card(key: str, title: str) -> HomeDashboardCard:
    return HomeDashboardCard(
        key=key, title=title,
        status=HomeDashboardStatus.MISSING,
        headline="Status unavailable",
        lines=("This panel could not be read right now.",),
    )


def build_home_dashboard_state(
    *,
    event_context=None,
    strategy_context=None,
    setup_context=None,
    track_context=None,
    ai_snapshot=None,
    strategy_snapshot=None,
    has_practice_laps: bool = False,
    has_valid_laps: bool = False,
    live_active: bool = False,
    learning_saved: bool = False,
) -> HomeDashboardState:
    """Build the full Home Dashboard display state. **Never raises.**

    Parameters
    ----------
    event_context / strategy_context / setup_context / track_context
        The canonical read models (or None). Duck-typed — malformed objects
        degrade to "missing" cards rather than crashing.
    ai_snapshot
        A use-case AI snapshot (``StrategyAISnapshot`` etc., read via ``.core``)
        or a bare ``AIContextSnapshot``. Reflects whether AI paths would use
        clean frozen inputs right now.
    strategy_snapshot
        Optional ``StrategyPromptSnapshot`` used to check setup-vs-strategy
        staleness. When omitted it is derived from the strategy + event
        contexts (pure computation).
    has_practice_laps / has_valid_laps / live_active / learning_saved
        Telemetry/session flags supplied by the caller (those layers own them).
    """
    # Derive the strategy prompt snapshot when not supplied — needed only for
    # the setup-vs-strategy staleness check.
    if strategy_snapshot is None and strategy_context is not None:
        try:
            from data.strategy_context import build_strategy_prompt_snapshot
            strategy_snapshot = build_strategy_prompt_snapshot(
                strategy_context, event_context)
        except Exception:
            strategy_snapshot = None

    builders = (
        (CARD_RACE_SETUP, "Race Setup",
         lambda: _build_race_setup_card(event_context, track_context)),
        (CARD_TRACK, "Track Intelligence",
         lambda: _build_track_card(track_context, event_context)),
        (CARD_SETUP, "Setup Brain",
         lambda: _build_setup_card(setup_context, event_context, strategy_snapshot)),
        (CARD_STRATEGY, "Strategy Brain",
         lambda: _build_strategy_card(strategy_context, event_context)),
        (CARD_AI_SAFETY, "AI Input Safety",
         lambda: _build_ai_safety_card(ai_snapshot)),
    )

    cards = []
    for key, title, fn in builders:
        try:
            cards.append(fn())
        except Exception:
            cards.append(_fallback_card(key, title))

    try:
        flags = build_flow_flags(
            event_context=event_context,
            strategy_context=strategy_context,
            setup_context=setup_context,
            track_context=track_context,
            has_practice_laps=has_practice_laps,
            has_valid_laps=has_valid_laps,
            live_active=live_active,
            learning_saved=learning_saved,
        )
    except Exception:
        flags = {}
    next_action = _build_next_action(flags)

    all_warnings = tuple(w for c in cards for w in c.warnings)

    return HomeDashboardState(
        schema=HOME_DASHBOARD_SCHEMA,
        cards=tuple(cards),
        next_action=next_action,
        warnings=all_warnings,
    )


def empty_home_dashboard_state() -> HomeDashboardState:
    """A well-formed dashboard state with nothing configured."""
    return build_home_dashboard_state()


# --------------------------------------------------------------------------- #
# HTML rendering (pure strings — consumed by the Qt layer's rich-text labels)
# --------------------------------------------------------------------------- #
_STATUS_COLOURS = {
    HomeDashboardStatus.READY: "#2EA043",
    HomeDashboardStatus.ATTENTION: "#F5C542",
    HomeDashboardStatus.MISSING: "#9AA0A6",
    HomeDashboardStatus.BLOCKED: "#E5534B",
}

_WARNING_COLOURS = {
    "warning": "#F5C542",
    "stale": "#F5A742",
    "blocker": "#E5534B",
}


def _escape(text) -> str:
    import html
    return html.escape(_as_str(text))


def format_card_html(card: HomeDashboardCard, *, text_colour: str = "#E0E0E0") -> str:
    """One dashboard card as a self-contained rich-text block."""
    colour = _STATUS_COLOURS.get(card.status, "#9AA0A6")
    parts = [
        f"<div style='color:{text_colour};'>",
        f"<span style='font-size:13px; font-weight:bold;'>{_escape(card.title)}</span>"
        f"&nbsp;&nbsp;<span style='color:{colour}; font-size:11px; font-weight:bold;'>"
        f"● {_escape(card.status_text)}</span>",
        f"<div style='color:#AAAAAA; font-size:11px; margin-top:2px;'>"
        f"{_escape(card.headline)}</div>",
    ]
    if card.lines:
        rows = "".join(
            f"<div style='font-size:11px; padding:1px 0;'>{_escape(line)}</div>"
            for line in card.lines
        )
        parts.append(f"<div style='margin-top:6px;'>{rows}</div>")
    if card.warnings:
        rows = "".join(
            f"<div style='color:{_WARNING_COLOURS.get(w.kind, '#F5C542')};"
            f" font-size:11px; padding:1px 0;'>⚠ {_escape(w.message)}</div>"
            for w in card.warnings
        )
        parts.append(f"<div style='margin-top:6px;'>{rows}</div>")
    parts.append("</div>")
    return "".join(parts)


def format_next_action_html(next_action: HomeDashboardNextAction,
                            *, text_colour: str = "#E0E0E0") -> str:
    """The next-best-action banner as a rich-text block."""
    progress = next_action.progress_text
    progress_html = (
        f"<span style='color:#AAAAAA; font-size:11px;'>&nbsp;&nbsp;({_escape(progress)})</span>"
        if progress else ""
    )
    if next_action.complete:
        accent = "#2EA043"
        prefix = "All set"
    else:
        accent = "#F5C542"
        prefix = "Next step"
    tab_html = (
        f"<span style='color:#AAAAAA; font-size:12px;'>"
        f"&nbsp;→&nbsp;open <b>{_escape(next_action.tab)}</b></span>"
        if next_action.tab and not next_action.complete else ""
    )
    return (
        f"<div style='color:{text_colour};'>"
        f"<span style='color:{accent}; font-size:11px; font-weight:bold;"
        f" letter-spacing:1px;'>{prefix.upper()}</span><br/>"
        f"<span style='font-size:14px; font-weight:bold;'>"
        f"{_escape(next_action.action)}</span>{tab_html}{progress_html}"
        f"</div>"
    )
