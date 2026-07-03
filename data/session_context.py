"""SessionContext — canonical read model for live telemetry / session state.

Added by the **SessionContext / TelemetryContext** sprint (2026-07-03), the
telemetry-layer counterpart to EventContext / StrategyContext / SetupContext /
TrackContext (see `docs/PRODUCT_CONSOLIDATION_AUDIT.md` §7's target
architecture).

Why this exists
---------------
"Am I connected / recording / how many laps / what's the fuel burn / is a live
session active?" was answered by reaching into **volatile dashboard attributes**
scattered across the UI — ``self._tracker._connected`` /
``self._tracker._packet_count`` / ``self._tracker.avg_fuel_per_lap`` /
``self._active_session_id`` / ``self._loaded_session_avg_fuel`` — plus a
``config["strategy"]["fuel_burn_per_lap"]`` fallback. The Home Dashboard's
``live_active`` / ``has_practice_laps`` were documented approximations built the
same ad-hoc way. This read model normalises those into one immutable snapshot so
consumers stop reaching into tracker internals and the legacy config.

Ownership boundary
------------------
SessionContext owns *only* live telemetry / session-status truth. It must **not**
own event/race config (EventContext), strategy plan (StrategyContext), setup
(SetupContext), track identity (TrackContext), or AI inputs. It never mutates
anything and performs no I/O.

Purity
------
No PyQt6, no DB, no network, no file I/O — the builder takes plain values the
caller already has (duck-typed tracker read via safe getters, plus caller-owned
DB-derived flags). Unit-testable without a QApplication (the project convention);
never raises.

Byte-identity
-------------
Every field mirrors the exact expression it replaces, so migrated consumers are
behaviour-preserving (proven in tests/test_session_context.py). In particular
``fuel_burn_per_lap`` reproduces ``_computed_fuel_burn_lpl``'s 3-tier fallback
(loaded historical session → live telemetry average → config fallback default
2.0), and ``connected`` reproduces ``tracker is not None and
getattr(tracker, "_connected", False)`` — including that the tracker does not
currently carry ``_connected`` (so it resolves False today; the read model is
where a real connection signal would later be wired, in one place).
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from enum import Enum
from typing import Optional


SESSION_CONTEXT_SCHEMA = "session_context_v1"


class SessionContextSource(str, Enum):
    """Where a SessionContext was resolved from."""
    EMPTY = "empty"    # no tracker and nothing recording
    LIVE = "live"      # a tracker (and/or an active session) is present


class SessionFuelSource(str, Enum):
    """Which of ``_computed_fuel_burn_lpl``'s three tiers supplied the burn."""
    LOADED_SESSION = "loaded_session"   # a historical session was loaded
    TELEMETRY = "telemetry"             # live telemetry average
    CONFIG_FALLBACK = "config_fallback"  # config["strategy"] default (2.0)


# --------------------------------------------------------------------------- #
# Safe coercion helpers (never raise)
# --------------------------------------------------------------------------- #
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


def _as_str(v, default: str = "") -> str:
    if v is None:
        return default
    try:
        return str(v)
    except Exception:  # pragma: no cover - defensive
        return default


# --------------------------------------------------------------------------- #
# The read model
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class SessionContext:
    """Immutable, normalised snapshot of live telemetry / session status."""

    # Connection / packets
    connected: bool
    packet_count: int

    # Live session
    laps_recorded: int
    active_session_id: Optional[int]
    is_recording: bool
    live_active: bool
    live_mode: str

    # Fuel burn (per lap)
    telemetry_avg_fuel_per_lap: float     # raw live-telemetry average (0.0 if none)
    fuel_burn_per_lap: float              # resolved with the 3-tier fallback
    fuel_burn_source: SessionFuelSource

    # Practice-lap availability (caller-owned DB-derived flags)
    has_practice_laps: bool
    has_valid_laps: bool

    # Provenance
    source: SessionContextSource = SessionContextSource.EMPTY

    # -- convenience ------------------------------------------------------- #
    @property
    def is_live(self) -> bool:
        return self.source != SessionContextSource.EMPTY

    @property
    def has_telemetry_fuel(self) -> bool:
        return self.telemetry_avg_fuel_per_lap > 0

    def connection_text(self) -> str:
        return "Connected" if self.connected else "Disconnected"

    def recording_text(self) -> str:
        return "Yes" if self.is_recording else "No"

    def to_dict(self) -> dict:
        d = asdict(self)
        d["source"] = self.source.value
        d["fuel_burn_source"] = self.fuel_burn_source.value
        d["schema"] = SESSION_CONTEXT_SCHEMA
        return d


# --------------------------------------------------------------------------- #
# Builder / adapter
# --------------------------------------------------------------------------- #
def build_session_context(
    *,
    connected: bool = False,
    packet_count=0,
    laps_recorded=0,
    active_session_id=None,
    live_mode: str = "Race",
    telemetry_avg_fuel_per_lap=0.0,
    loaded_session_avg_fuel=0.0,
    config_fuel_burn_per_lap=2.0,
    has_practice_laps: bool = False,
    has_valid_laps: bool = False,
) -> SessionContext:
    """Build the canonical SessionContext from the current app state.

    All inputs are plain values the caller already holds (read from the tracker
    via safe getters, the active session id, the loaded-session average, and the
    ``config["strategy"]`` fuel fallback). Never raises.

    ``fuel_burn_per_lap`` reproduces ``_computed_fuel_burn_lpl`` exactly:
      1. a loaded historical session average (> 0), else
      2. the live telemetry average (> 0), else
      3. the config fallback (default 2.0).
    """
    connected = bool(connected)
    packet_count = _as_int(packet_count, 0)
    laps_recorded = _as_int(laps_recorded, 0)

    sid = None if active_session_id is None else _as_int(active_session_id, 0)
    is_recording = active_session_id is not None
    live_active = connected

    telemetry_avg = _as_float(telemetry_avg_fuel_per_lap, 0.0)
    loaded = _as_float(loaded_session_avg_fuel, 0.0)

    # 3-tier fallback — byte-identical to _computed_fuel_burn_lpl.
    if loaded > 0:
        fuel_burn = float(loaded)
        fuel_source = SessionFuelSource.LOADED_SESSION
    elif telemetry_avg > 0:
        fuel_burn = float(telemetry_avg)
        fuel_source = SessionFuelSource.TELEMETRY
    else:
        fuel_burn = _as_float(config_fuel_burn_per_lap, 2.0)
        fuel_source = SessionFuelSource.CONFIG_FALLBACK

    source = (
        SessionContextSource.LIVE
        if (connected or packet_count > 0 or laps_recorded > 0
            or active_session_id is not None)
        else SessionContextSource.EMPTY
    )

    return SessionContext(
        connected=connected,
        packet_count=packet_count,
        laps_recorded=laps_recorded,
        active_session_id=sid,
        is_recording=is_recording,
        live_active=live_active,
        live_mode=_as_str(live_mode, "Race") or "Race",
        telemetry_avg_fuel_per_lap=telemetry_avg,
        fuel_burn_per_lap=fuel_burn,
        fuel_burn_source=fuel_source,
        has_practice_laps=bool(has_practice_laps),
        has_valid_laps=bool(has_valid_laps),
        source=source,
    )


def empty_session_context() -> SessionContext:
    """A well-formed EMPTY context (no tracker, nothing recording)."""
    return build_session_context()


# --------------------------------------------------------------------------- #
# Bridge to ui/product_flow.py (home / next-action surface)
# --------------------------------------------------------------------------- #
def flow_flags(ctx: SessionContext) -> dict:
    """The telemetry/session flags ``ui.product_flow.build_flow_state_summary``
    (and the Home Dashboard) expect. Lets the home overview drive its
    live/practice gates from a canonical model instead of ad-hoc reads.
    """
    return {
        "has_practice_laps": ctx.has_practice_laps,
        "has_valid_laps": ctx.has_valid_laps,
        "live_active": ctx.live_active,
    }
