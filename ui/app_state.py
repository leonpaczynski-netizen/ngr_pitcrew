"""Canonical application-state model for the NGR Pit Crew UI rebuild (F0.3).

``AppState`` is the single, immutable, Qt-free snapshot that the new shell, nav
rail, event header, progress rail and Pit Crew Engineer guidance card all read
from — so there is exactly one truth for "active event + programme stage + active
setup + session + connection" in the presentation layer.

It *aggregates* the existing canonical read models (``EventContext``,
``SessionContext``, ``StrategyContext``) rather than re-deriving anything; it adds
no engineering logic. The controller (a thin QObject, added separately) will hold
the current ``AppState`` and emit a change signal; this module stays Qt-free so it
is unit-testable without a QApplication.

Design rules honoured:
  * no Qt import;
  * frozen/immutable;
  * never raises — malformed inputs fall back to a safe empty state;
  * stage-state values are validated against the design-system tokens
    (``ngr_theme.STAGE_STATES``) so the rail can render them directly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Optional, Tuple

from data.event_context import EventContext, build_event_context
from data.session_context import SessionContext, build_session_context
from data.strategy_context import StrategyContext, build_strategy_context
from ui import ngr_theme as _theme


# Canonical ordered programme stages (the progress rail) — single source of truth.
# Mirrors docs/NGR_PIT_CREW_UI_ARCHITECTURE.md §3.
PROGRAMME_STAGES: Tuple[str, ...] = (
    "briefing", "garage", "practice", "review",
    "qualifying", "strategy", "race", "debrief",
)

# Canonical left-nav destinations (a superset of the rail: adds standing areas).
# Home IS the event command centre — a separate "Active Event" destination showed the
# same event identity + progress and muddied the single-home model, so it was folded in.
NAV_DESTINATIONS: Tuple[str, ...] = (
    "home", "programme", "garage", "practice", "qualifying",
    "race_strategy", "live_pit_wall", "debrief", "track_model",
    "engineering_library", "settings",
)

# Valid stage-state keys come straight from the design-system tokens.
_VALID_STAGE_STATES = frozenset(_theme.STAGE_STATES.keys())
_DEFAULT_STAGE_STATE = _theme.STAGE_AVAILABLE


@dataclass(frozen=True)
class AppState:
    """Immutable snapshot of everything the shell chrome needs to render."""

    event: EventContext
    session: SessionContext
    strategy: StrategyContext

    active_setup_label: str = ""
    active_setup_applied: bool = False

    programme_stage: str = ""                       # current stage key (or "")
    # stage_key -> one of ngr_theme.STAGE_STATES keys. Stored as a sorted tuple of
    # pairs so AppState stays hashable/frozen; use stage_state() to read.
    stage_states: Tuple[Tuple[str, str], ...] = ()

    connected: bool = False

    # ---- derived, read-only convenience -----------------------------------
    @property
    def car(self) -> str:
        return self.event.car

    @property
    def track(self) -> str:
        return self.event.track

    @property
    def layout_id(self) -> str:
        return self.event.layout_id

    @property
    def event_name(self) -> str:
        return self.event.event_name

    @property
    def has_active_event(self) -> bool:
        return self.event.event_id is not None

    def stage_state(self, stage_key: str) -> str:
        """State of one stage; 'available' if unknown. Never raises."""
        return dict(self.stage_states).get(stage_key, _DEFAULT_STAGE_STATE)

    def is_current_stage(self, stage_key: str) -> bool:
        return self.programme_stage == stage_key

    def can_navigate(self, stage_key: str) -> bool:
        """A stage is reachable unless it is explicitly blocked or not-required."""
        st = self.stage_state(stage_key)
        return st not in (_theme.STAGE_BLOCKED, _theme.STAGE_NOT_REQUIRED)

    # ---- factories --------------------------------------------------------
    @classmethod
    def empty(cls) -> "AppState":
        """A fully-valid, EMPTY-source state — used before any event is active
        and as the safe fallback. Never raises."""
        return cls(
            event=build_event_context(),
            session=build_session_context(),
            strategy=build_strategy_context(),
        )


def _normalise_stage_states(
    stage_states: Optional[Mapping[str, str]],
) -> Tuple[Tuple[str, str], ...]:
    """Coerce a stage_key->state mapping into a validated, sorted tuple.

    Unknown state values fall back to the default ('available'); unknown stage
    keys are kept (a caller may track extra stages) but their state is validated.
    Never raises.
    """
    if not stage_states:
        return ()
    out = []
    try:
        for key, state in stage_states.items():
            k = str(key)
            s = state if state in _VALID_STAGE_STATES else _DEFAULT_STAGE_STATE
            out.append((k, s))
    except Exception:
        return ()
    return tuple(sorted(out))


def build_app_state(
    *,
    event: Optional[EventContext] = None,
    session: Optional[SessionContext] = None,
    strategy: Optional[StrategyContext] = None,
    active_setup_label: str = "",
    active_setup_applied: bool = False,
    programme_stage: str = "",
    stage_states: Optional[Mapping[str, str]] = None,
    connected: bool = False,
) -> AppState:
    """Assemble an ``AppState`` from already-built canonical contexts.

    The caller (controller) passes the contexts it has built via the existing
    ``build_*_context`` adapters; this function only aggregates + validates. Any
    missing context is replaced by its EMPTY form so the result is always valid.
    Never raises.
    """
    return AppState(
        event=event if event is not None else build_event_context(),
        session=session if session is not None else build_session_context(),
        strategy=strategy if strategy is not None else build_strategy_context(),
        active_setup_label=str(active_setup_label or ""),
        active_setup_applied=bool(active_setup_applied),
        programme_stage=str(programme_stage or ""),
        stage_states=_normalise_stage_states(stage_states),
        connected=bool(connected),
    )
