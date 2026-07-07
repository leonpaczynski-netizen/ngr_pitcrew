"""Race state machine — detects events and emits them to the event queue."""
from __future__ import annotations
import enum
import time
import queue
import datetime
from dataclasses import dataclass, field
from typing import Optional
from .packet import GT7Packet
from .pit_state import (
    PitStintState, PitEvent, PitDetectionConfidence,
    start_stint_tracking, apply_lap_completed, apply_pit_event,
    classify_pit_confidence,
)


class TyreState(enum.Enum):
    COLD        = "cold"
    WARMING     = "warming"
    OPTIMAL     = "optimal"
    HOT         = "hot"
    OVERHEATING = "overheating"


class RacePhase(enum.Enum):
    IDLE     = "idle"
    PRE_RACE = "pre_race"
    RACING   = "racing"
    IN_PIT   = "in_pit"
    FINISHED = "finished"


class RaceType(enum.Enum):
    UNKNOWN  = "unknown"
    LAP      = "lap"
    TIMED    = "timed"
    UNLIMITED = "unlimited"


class EventType(enum.Enum):
    LAP_COMPLETED    = "lap_completed"
    POSITION_CHANGED = "position_changed"
    TYRE_STATE       = "tyre_state"
    PIT_ENTRY        = "pit_entry"
    PIT_EXIT         = "pit_exit"
    RACE_STARTED     = "race_started"
    RACE_FINISHED    = "race_finished"
    FUEL_LOW         = "fuel_low"


class Priority(enum.IntEnum):
    CRITICAL = 1
    HIGH     = 2
    MEDIUM   = 3
    LOW      = 4
    INFO     = 5


@dataclass
class TelemetryEvent:
    type: EventType
    data: dict
    priority: Priority


class SessionType(enum.Enum):
    UNKNOWN    = "unknown"
    PRACTICE   = "practice"
    QUALIFYING = "qualifying"
    RACE       = "race"


@dataclass
class LapRecord:
    lap_num: int
    lap_time_ms: int
    best_lap_ms: int
    delta_ms: int
    fuel_start: float
    fuel_end: float
    fuel_used: float
    position: int
    is_pit_lap: bool
    timestamp: str
    session_type: SessionType = SessionType.PRACTICE
    is_out_lap: bool = False

    @property
    def avg_fuel_note(self) -> str:
        return ""


@dataclass
class TyreThresholds:
    cold_max:    float = 70.0
    warming_max: float = 85.0
    optimal_max: float = 100.0
    hot_max:     float = 115.0

    @classmethod
    def from_config(cls, d: dict) -> "TyreThresholds":
        return cls(
            cold_max=float(d.get("cold_max", 70.0)),
            warming_max=float(d.get("warming_max", 85.0)),
            optimal_max=float(d.get("optimal_max", 100.0)),
            hot_max=float(d.get("hot_max", 115.0)),
        )

    def classify(self, temp: float) -> TyreState:
        if temp < self.cold_max:
            return TyreState.COLD
        if temp < self.warming_max:
            return TyreState.WARMING
        if temp < self.optimal_max:
            return TyreState.OPTIMAL
        if temp < self.hot_max:
            return TyreState.HOT
        return TyreState.OVERHEATING


_TYRE_KEYS  = ("fl", "fr", "rl", "rr")
_TYRE_NAMES = {"fl": "front left", "fr": "front right",
               "rl": "rear left",  "rr": "rear right"}
_PACKET_RESET_GAP = 10_000   # treat as new race if packet_id jumps back this far

# Speed below which a fuel increase is treated as pit-lane refueling.
# GT7 pit lane speed limiters are typically 60-80 km/h; 120 gives generous margin.
_PIT_MAX_SPEED_KMH = 120.0


class RaceStateTracker:
    """
    Processes every GT7Packet in the UDP thread.
    Emits TelemetryEvent objects into the shared PriorityQueue.
    """

    def __init__(
        self,
        event_queue: "queue.PriorityQueue[tuple[int,int,TelemetryEvent]]",
        thresholds: TyreThresholds,
        pit_threshold_liters: float = 0.5,
        safety_margin_laps: float = 1.0,
    ) -> None:
        self._eq = event_queue
        self._thresholds = thresholds
        self._pit_threshold = pit_threshold_liters
        self._safety_margin = safety_margin_laps
        self._seq = 0
        self._reset()

    # ------------------------------------------------------------------ public

    def update_thresholds(self, t: TyreThresholds) -> None:
        self._thresholds = t

    def update_fuel_config(self, pit_threshold: float, safety_margin: float) -> None:
        self._pit_threshold = pit_threshold
        self._safety_margin = safety_margin

    def set_race_config(self, race_type: RaceType,
                        duration_minutes: float = 0.0) -> None:
        """Override auto-detected race type and (for timed races) set duration."""
        self._manual_race_type = race_type
        self._timed_race_duration_ms = int(duration_minutes * 60 * 1000)
        if race_type != RaceType.UNKNOWN:
            self._race_type = race_type
        print(f"[StateTracker] race config: {race_type.value}, "
              f"duration={duration_minutes:.1f} min")

    def set_session_type_override(self, session_type: "SessionType | None") -> None:
        """Force all recorded laps to use this session type regardless of race state.
        Pass None to restore auto-detection from _race_is_active."""
        self._session_type_override = session_type

    def set_compound(self, compound: str) -> None:
        """Record the currently active tyre compound (e.g. 'RH', 'RM').
        Written to lap_records.compound on each lap save."""
        self._current_compound = compound or ""

    def computed_remaining_ms(self) -> int:
        """Remaining race time in ms for timed races, or -1 if not applicable."""
        if (self._manual_race_type != RaceType.TIMED
                or self._timed_race_duration_ms <= 0):
            return -1
        # IN_PIT counts as active race time — the clock keeps running in GT7 during
        # a pit stop, so we must include it here or remaining_ms returns -1 and the
        # fuel target calculation falls back to safety-margin-only.
        if self._phase in (RacePhase.RACING, RacePhase.IN_PIT) and self._race_start_time > 0:
            elapsed_ms = int((time.monotonic() - self._race_start_time) * 1000)
            return max(0, self._timed_race_duration_ms - elapsed_ms)
        if self._phase in (RacePhase.PRE_RACE, RacePhase.IDLE):
            return self._timed_race_duration_ms
        return -1

    @property
    def phase(self) -> RacePhase:
        return self._phase

    @property
    def race_type(self) -> RaceType:
        return self._race_type

    @property
    def manual_race_type(self) -> RaceType:
        return self._manual_race_type

    @property
    def timed_duration_minutes(self) -> float:
        return self._timed_race_duration_ms / 60_000.0

    @property
    def laps_recorded(self) -> int:
        """Number of laps recorded since last reset — use instead of p.laps_completed."""
        return len(self._lap_time_hist)

    @property
    def laps_in_race(self) -> int:
        """Race length captured at race start (0 = unknown / timed race)."""
        return self._laps_in_race

    @property
    def best_lap_ms(self) -> int:
        """Best lap time in ms cached from last packet; -1 if none set."""
        return self._best_lap_ms

    @property
    def laps_remaining(self) -> int:
        """Laps remaining in a lap race (0 for timed/unlimited/unknown)."""
        if self._race_type != RaceType.LAP or self._laps_in_race <= 0:
            return 0
        return max(0, self._laps_in_race - len(self._lap_time_hist))

    @property
    def last_fuel(self) -> float:
        """Fuel level (litres) from last received packet."""
        return self._last_fuel

    @property
    def last_position(self) -> int:
        """Race position from last received packet (0 if unknown)."""
        return self._last_position

    @property
    def last_total_cars(self) -> int:
        """Total cars in race from last received packet."""
        return self._last_total_cars

    @property
    def avg_fuel_per_lap(self) -> float:
        """Average fuel consumption per lap (litres); 0.0 if not enough data."""
        return self._avg_fuel()

    @property
    def session_type(self) -> "SessionType":
        return self._session_type_override if self._session_type_override is not None else self._session_type

    @property
    def tyre_states(self) -> dict[str, TyreState]:
        return dict(self._tyre_states)

    # --- Group 54: read-only pit / stint state ---------------------------
    @property
    def pit_stint_state(self) -> PitStintState:
        """The current runtime pit/stint state (pure model; read-only)."""
        return self._pit_stint

    @property
    def pit_stops_completed(self) -> int:
        """Detected pit stops so far (0 = none detected)."""
        return self._pit_stint.pit_stops_completed

    @property
    def laps_since_pit(self) -> int:
        """Laps completed on the current stint since the last pit / race start."""
        return self._pit_stint.laps_since_pit

    @property
    def tyre_age_laps(self) -> "int | None":
        """Laps on the current tyre set, or None when pit/stint tracking is inactive."""
        return self._pit_stint.tyre_age_laps

    @property
    def pit_state_confidence(self) -> str:
        """Confidence of the pit/stint state: HIGH / MEDIUM / LOW / UNKNOWN."""
        return self._pit_stint.pit_detection_confidence.value

    def update(self, packet: GT7Packet) -> None:
        now = time.monotonic()

        # Detect race reset (packet_id wraps back to ~0)
        if (self._prev_packet_id >= 0 and
                packet.packet_id + _PACKET_RESET_GAP < self._prev_packet_id):
            self._reset()
        self._prev_packet_id = packet.packet_id

        # Flush urgent (HOT/OVERHEATING) and stable (OPTIMAL) tyre batches
        self._flush_tyre_batch(now, force=False)
        self._flush_stable_tyres(now)

        # GT7 sets loading=True briefly during lights-out, pit service animations,
        # and session transitions.  Only reset on loading when waiting for race
        # (PRE_RACE — user navigated away from lobby).  During RACING and IN_PIT
        # the loading flag is transient and must NOT clear race state.
        if packet.loading:
            if self._phase == RacePhase.PRE_RACE:
                print("[StateTracker] loading=True during PRE_RACE — returning to IDLE")
                self._reset()
            elif self._phase in (RacePhase.RACING, RacePhase.IN_PIT):
                # GT7 also sets loading=True on the packet where last_lap_ms changes
                # for the final lap (results screen) and occasionally for the out-lap
                # after a pit stop.  Run _check_lap here so those laps are not lost.
                self._check_lap(packet, now)
                # Timed race: loading=True during RACING after laps are recorded AND
                # the configured timer has expired = results screen = race over.
                # GT7 ALSO sends loading=True during pit service animations (fuel
                # dispensing) while phase is still RACING (before the fuel threshold
                # is crossed).  Guarding on computed_remaining_ms()==0 ensures we
                # only fire when the wall-clock timer has actually run out, not
                # mid-race pit stops.
                if (self._race_type == RaceType.TIMED and
                        self._phase == RacePhase.RACING and
                        len(self._lap_time_hist) > 0 and
                        self.computed_remaining_ms() == 0 and
                        self._session_type_override not in (SessionType.PRACTICE, SessionType.QUALIFYING)):
                    print("[StateTracker] RACING->FINISHED (timed race, results screen detected)")
                    self._phase = RacePhase.FINISHED
                    self._emit(TelemetryEvent(
                        type=EventType.RACE_FINISHED,
                        data={
                            "position": self._last_position,
                            "total_cars": self._last_total_cars,
                        },
                        priority=Priority.HIGH,
                    ))
                # Session-transition guard: loading=True during RACING with no
                # recorded laps = practice/qualifying session just ended, not a
                # mid-race animation.  Reset so the actual race timer starts fresh.
                # IN_PIT is excluded — an early pit stop is still a valid race.
                elif (self._phase == RacePhase.RACING and
                        len(self._lap_time_hist) == 0):
                    print("[StateTracker] loading=True during RACING, 0 laps — session transition, resetting")
                    self._reset()
            elif self._phase == RacePhase.FINISHED:
                # Results screen / returning to lobby after race ends.
                # Reset so the tracker is ready to detect the next race cleanly.
                print("[StateTracker] loading=True during FINISHED — resetting for next session")
                self._reset()
            self._prev = packet
            return

        # Skip off-track packets when idle (no meaningful telemetry)
        if not packet.car_on_track and self._phase == RacePhase.IDLE:
            self._prev = packet
            return

        # Detect mid-race exit: car off-track for >15 s while racing.
        # Covers manual quit, DNF, or returning to lobby before race ends.
        # 15 s debounce avoids triggering on crash respawns (typically < 5 s).
        if self._phase in (RacePhase.RACING, RacePhase.IN_PIT):
            if not packet.car_on_track:
                if self._off_track_since == 0.0:
                    self._off_track_since = now
                    print(f"[StateTracker] car off-track during {self._phase.value} — monitoring")
                elif now - self._off_track_since > 15.0:
                    print("[StateTracker] off-track >15 s — treating as race exit, resetting")
                    self._reset()
                    self._prev = packet
                    return
            else:
                self._off_track_since = 0.0

        self._detect_race_type(packet)
        self._phase_transitions(packet, now)
        self._check_lap(packet, now)
        self._check_position(packet)
        self._check_tyres(packet, now)
        self._check_fuel_warning(packet)

        # Cache values for on-demand voice queries (QueryListener reads these)
        self._last_fuel = packet.fuel_level
        self._last_position = packet.current_position
        self._last_total_cars = packet.total_cars
        if packet.best_lap_ms > 0:
            self._best_lap_ms = packet.best_lap_ms

        self._prev = packet

    def reset(self) -> None:
        """Public manual reset — clears race tracking state without touching the
        LapDataLogger.  Called from the UI reset button."""
        self._reset()

    # ----------------------------------------------------------------- private

    def _reset(self) -> None:
        self._phase: RacePhase = RacePhase.IDLE
        self._race_type: RaceType = RaceType.UNKNOWN
        self._prev: Optional[GT7Packet] = None
        self._prev_packet_id: int = -1
        self._tyre_states: dict[str, TyreState] = {k: TyreState.COLD for k in _TYRE_KEYS}
        self._pending_tyre: list[tuple[str, TyreState, TyreState]] = []
        self._tyre_deadline: float = 0.0
        # Non-urgent state changes deferred 2 s; key → (target_state, announce_deadline)
        self._tyre_stable_pending: dict[str, tuple[TyreState, float]] = {}
        self._fuel_gained: float = 0.0   # cumulative pit-lane fuel added
        self._low_speed_start: float = 0.0  # monotonic time when continuous low-speed started (0 = not timing)
        self._fuel_at_pit_entry: float = 0.0
        self._pit_entry_time: float = 0.0
        self._fuel_lap_start: float = 0.0
        self._lap_start_time: float = time.monotonic()
        self._race_start_time: float = 0.0
        self._laps_in_race: int = 0          # captured at race start; GT7 can send -1 mid-race
        self._laps_in_race_prerace_max: int = 0  # max laps_in_race seen during PRE_RACE (before any decrement)
        self._pre_race_low_speed_seen: bool = False  # True once speed < 30 km/h during PRE_RACE
        self._off_track_since: float = 0.0   # monotonic time when car first went off-track during racing
        self._prev_laps_completed: int = -1
        self._prev_position: int = 0
        self._lap_fuel_hist: list[float] = []
        self._lap_time_hist: list[int]   = []
        self._pit_lap: bool = False
        # Group 54: runtime-only pit/stint state (pure model; no persistence).
        self._pit_stint: PitStintState = PitStintState()
        self._outlap_pending: bool = False  # True after pit exit in practice; next lap recorded as out-lap
        self._race_is_active: bool = False  # True after RACE_STARTED; drives session_type on LapRecord
        self._fuel_warned: bool = False    # True once FUEL_LOW emitted; reset on pit exit
        # Session type is re-derived from the first meaningful packet after each reset.
        self._session_type: SessionType = SessionType.UNKNOWN
        # UI-driven override: set from Live tab mode selector so laps record the correct type
        # regardless of internal _race_is_active state. None = use auto-detection.
        if not hasattr(self, "_session_type_override"):
            self._session_type_override: "SessionType | None" = None
        # Current tyre compound — set from UI compound selector; written to lap_records
        if not hasattr(self, "_current_compound"):
            self._current_compound: str = ""
        # Cached last-packet values for on-demand voice queries (read by QueryListener thread)
        self._last_fuel: float = 0.0
        self._last_position: int = 0
        self._last_total_cars: int = 0
        self._best_lap_ms: int = -1
        # Manual race config is NOT reset between races — user keeps their setting
        # until they explicitly change it.  Initialised once here; preserved on reset.
        if not hasattr(self, "_manual_race_type"):
            self._manual_race_type: RaceType = RaceType.UNKNOWN
            self._timed_race_duration_ms: int = 0

    def _detect_race_type(self, p: GT7Packet) -> None:
        # Derive session type from packet signals.
        # cars_in_race == 0 is typical in practice/time trial; > 1 means race or qualifying.
        # remaining_time_ms > 0 during any timed qualifying session.
        # For LAP races: remaining_time_ms == -1 during the race, > 0 during qualifying.
        # For server-controlled TIMED online races: remaining_time_ms == 0 during the race
        # (server doesn't send the value), > 0 during qualifying.  Both cases are caught by
        # the same remaining_time_ms > 0 check when a manual race type is configured.
        cars = p.cars_in_race
        if cars <= 1:
            # Solo session, time trial, or empty lobby — no meaningful race.
            # laps_in_race==0 is NOT used here: GT7 sends 0 for unlimited-lap
            # online races (timed by the server), which have cars > 1.
            new_session = SessionType.PRACTICE
        elif (p.remaining_time_ms > 0 and
              self._phase in (RacePhase.IDLE, RacePhase.PRE_RACE)):
            # remaining_time_ms > 0 before the race starts → qualifying session.
            # Gated on phase (not _manual_race_type) so race-type config in Settings
            # cannot flip the session label while the driver is on track.
            new_session = SessionType.QUALIFYING
        else:
            # laps_in_race > 0 (lap race) or -1 (timed race / qualifying)
            new_session = SessionType.RACE
        if new_session != self._session_type:
            print(f"[StateTracker] session_type → {new_session.value}  "
                  f"laps_in_race={p.laps_in_race}  cars={cars}  "
                  f"remaining_ms={p.remaining_time_ms}")
            self._session_type = new_session

        # Manual override wins; auto-detect only when not overridden.
        if self._manual_race_type != RaceType.UNKNOWN:
            self._race_type = self._manual_race_type
            return
        if self._race_type != RaceType.UNKNOWN:
            return
        if p.laps_in_race > 0:
            self._race_type = RaceType.LAP
        elif p.laps_in_race == -1:
            self._race_type = RaceType.TIMED
        elif p.laps_in_race == 0:
            self._race_type = RaceType.UNLIMITED

    def _phase_transitions(self, p: GT7Packet, now: float) -> None:
        if self._phase == RacePhase.IDLE:
            if p.car_on_track:
                self._phase = RacePhase.PRE_RACE
                self._fuel_lap_start = p.fuel_level
                self._lap_start_time = now
                # Clamp to 0: GT7 sends 0xFFFF (→ -1 signed) when no laps
                # completed yet; _check_lap's `< 0` guard would skip every lap.
                self._prev_laps_completed = max(0, p.laps_completed)
                # If the car is already stationary when we first see it (grid),
                # count that as satisfying the low-speed gate immediately.
                self._pre_race_low_speed_seen = p.speed_kmh < 30
                print(f"[StateTracker] IDLE->PRE_RACE  laps_completed={p.laps_completed} "
                      f"laps_in_race={p.laps_in_race} speed={p.speed_kmh:.1f}")

        elif self._phase == RacePhase.PRE_RACE:
            # Qualifying suppression: _detect_race_type() (called just before this)
            # sets session_type=QUALIFYING when remaining_time_ms > 0 for LAP/TIMED
            # race configs.  Returning here skips all RACING-transition logic so
            # qualifying laps don't fire RACE_STARTED and don't corrupt laps_in_race.
            if self._session_type == SessionType.QUALIFYING:
                race_start_detected = (
                    (self._pre_race_low_speed_seen and p.speed_kmh > 80) or
                    (self._prev_laps_completed >= 0 and
                     p.laps_completed > self._prev_laps_completed)
                )
                if not race_start_detected:
                    return
                # Fall through — timed race has actually launched

            # Track the maximum laps_in_race seen on-grid, before the race starts.
            # On some circuits the start grid sits just before the S/F line; the car
            # can cross it at low speed before reaching 80 km/h.  GT7 appears to
            # decrement laps_in_race at each crossing, so by the time we transition
            # to RACING the packet value is already N-1.  Taking the pre-race max
            # ensures we capture the full race length (N) from when the car was
            # stationary on the grid.
            if p.laps_in_race > 0:
                self._laps_in_race_prerace_max = max(self._laps_in_race_prerace_max, p.laps_in_race)

            # Gate: require the car to have been below 30 km/h at some point during
            # PRE_RACE before the speed-based RACING trigger is allowed.  This prevents
            # false race-starts when:
            #   • The app starts while a formation lap is already in progress (>80 km/h)
            #   • The user is in a practice/qualifying session at racing speed
            # For standing-start races the car is always stationary on the grid, so this
            # flag is set well before lights-out.  The laps_completed trigger below is
            # left ungated so that rolling-start races (which never go below 30 km/h)
            # still detect the race start when the first S/F line crossing occurs.
            if p.speed_kmh < 30:
                self._pre_race_low_speed_seen = True

            # 80 km/h threshold + low-speed gate distinguishes race start from formation
            # lap (50-70 km/h) or lobby cruising.
            if (self._pre_race_low_speed_seen and p.speed_kmh > 80) or (
                self._prev_laps_completed >= 0 and
                p.laps_completed > self._prev_laps_completed
            ):
                self._phase = RacePhase.RACING
                self._race_start_time = now
                # Group 54: begin read-only pit/stint tracking at race start.
                # 0 pits so far is certain; the stint ages from here (tyres started on).
                self._pit_stint = start_stint_tracking(
                    self._pit_stint, start_lap=len(self._lap_time_hist))
                # Prefer the pre-race max over the current packet value; the current
                # packet may already show a decremented count if the S/F line was
                # crossed before we hit the 80 km/h speed threshold.
                if self._laps_in_race_prerace_max > 0:
                    self._laps_in_race = self._laps_in_race_prerace_max
                elif p.laps_in_race > 0:
                    self._laps_in_race = p.laps_in_race
                print(f"[StateTracker] PRE_RACE->RACING  race_type={self._race_type.value}"
                      f"  laps_in_race={self._laps_in_race}  speed={p.speed_kmh:.1f}")
                self._race_is_active = True
                if self._session_type == SessionType.PRACTICE:
                    # Practice: allow RACING phase so laps are recorded, but don't
                    # fire RACE_STARTED and mark the first lap as an outlap.
                    self._outlap_pending = True
                    print("[StateTracker] Practice session active — RACE_STARTED suppressed")
                else:
                    self._emit(TelemetryEvent(
                        type=EventType.RACE_STARTED,
                        data={
                            "race_type": self._race_type,
                            "laps_in_race": p.laps_in_race,
                            "remaining_time_ms": self.computed_remaining_ms(),
                        },
                        priority=Priority.HIGH,
                    ))

        # ── Pit detection ───────────────────────────────────────────────────────
        if self._phase in (RacePhase.RACING, RacePhase.PRE_RACE) and self._prev:
            delta = p.fuel_level - self._prev.fuel_level

            if delta > 0.001:
                if p.speed_kmh < _PIT_MAX_SPEED_KMH:
                    self._fuel_gained += delta
                else:
                    # Fuel increased at racing speed = GT7 online auto-refuel / BOP top-up.
                    # Update the lap baseline so fuel_used for this lap stays accurate.
                    if p.fuel_level > self._fuel_lap_start:
                        self._fuel_lap_start = p.fuel_level
            else:
                self._fuel_gained = 0.0

            # Fuel-based pit entry
            if self._fuel_gained >= self._pit_threshold:
                self._enter_pit(p, now)
                return

            # Speed-based fallback: detect no-refuel pit stops where the car
            # comes to a full stop in the pit box but takes no fuel.
            # Only applies in RACING phase (not PRE_RACE where car is on grid).
            if self._phase == RacePhase.RACING:
                if p.speed_kmh < 10:
                    if self._low_speed_start == 0.0:
                        self._low_speed_start = now
                    elif (now - self._low_speed_start) >= 3.0:
                        self._low_speed_start = 0.0
                        self._enter_pit(p, now)
                        return
                else:
                    self._low_speed_start = 0.0

        elif self._phase == RacePhase.IN_PIT and self._prev:
            # Require fuel to be stable AND speed > 80 km/h (clear of pit lane)
            # AND at least 15 s have elapsed since entry (prevents false exit
            # from brief speed spikes during GT7 pit-service animation).
            stable = abs(p.fuel_level - self._prev.fuel_level) < 0.05
            min_duration = (now - self._pit_entry_time) >= 15.0
            if stable and p.speed_kmh > 80 and min_duration:
                self._exit_pit(p, now)

        # Race-finish detection is handled inside _check_lap (runs on the same
        # packet as the last lap), so it fires before loading=True can skip the
        # next packet and prevent detection here.

    def _enter_pit(self, p: GT7Packet, now: float) -> None:
        # Do NOT start the race timer here: pit entry can fire during the
        # between-races garage stop (previous race just finished, car drives in)
        # as well as during a genuine mid-race pit stop.  The _exit_pit() safety
        # net sets the timer when the car returns to track, which is always at
        # or after the actual race start rather than 10-20 s before it.
        self._phase = RacePhase.IN_PIT
        self._fuel_at_pit_entry = self._prev.fuel_level if self._prev else p.fuel_level
        self._fuel_gained = 0.0
        self._low_speed_start = 0.0
        self._pit_entry_time = now
        self._pit_lap = True

        avg_fuel = self._avg_fuel()
        avg_lap_ms = self._avg_lap_ms()
        fuel_target = 0.0

        if avg_fuel > 0:
            integer_rem  = 0
            lap_fraction = 0.0

            if self._race_type == RaceType.LAP and self._laps_in_race > 0:
                integer_rem = max(self._laps_in_race - len(self._lap_time_hist), 0)

                # Subtract the fraction of the current (unrecorded) lap already driven.
                # Without this, a driver pitting late in a lap (e.g. 90% through) gets a
                # fuel target nearly one full lap too high.  Use avg lap time as the
                # reference; fall back to GT7's best_lap_ms if avg not yet available.
                ref_ms = avg_lap_ms or (p.best_lap_ms if p.best_lap_ms > 0 else 0)
                if ref_ms > 0 and integer_rem > 0:
                    elapsed_ms = (now - self._lap_start_time) * 1000.0
                    lap_fraction = min(elapsed_ms / ref_ms, 1.0)

                remaining = max(float(integer_rem) - lap_fraction, 0.0)
            elif self._race_type == RaceType.TIMED:
                # Prefer the packet's own remaining time (authoritative GT7 value).
                # Fall back to wall-clock only if the packet field isn't populated.
                pkt_rem = p.remaining_time_ms
                rem_ms = pkt_rem if pkt_rem > 0 else self.computed_remaining_ms()
                # Prefer average lap time; fall back to GT7's best_lap_ms so we
                # can calculate a fuel target even when only one lap is complete.
                ref_ms = avg_lap_ms or (p.best_lap_ms if p.best_lap_ms > 0 else 0)
                remaining = rem_ms / ref_ms if (rem_ms > 0 and ref_ms > 0) else 0.0
            else:
                remaining = 0.0

            # Always compute a target even when remaining==0 so the safety
            # margin gives the driver enough fuel to complete the current lap.
            fuel_target = avg_fuel * (remaining + self._safety_margin)

        self._emit(TelemetryEvent(
            type=EventType.PIT_ENTRY,
            data={
                "fuel_target": fuel_target,              # total liters needed to finish
                "fuel_capacity": p.fuel_capacity,        # tank size in liters
                "fuel_level": p.fuel_level,              # current level (refueling already started)
                "fuel_at_entry": self._fuel_at_pit_entry,# level before refueling began
            },
            priority=Priority.CRITICAL,
        ))

    def _exit_pit(self, p: GT7Packet, now: float) -> None:
        fuel_added = p.fuel_level - self._fuel_at_pit_entry
        # Group 54: count the completed pit stop and reset the stint age. Confidence
        # is MEDIUM when a real refuel was seen, LOW for a speed-only (no-refuel) stop.
        _pit_conf = classify_pit_confidence(fuel_added, self._pit_threshold)
        self._pit_stint = apply_pit_event(
            self._pit_stint,
            pit_lap=len(self._lap_time_hist),
            confidence=_pit_conf,
            source=("refuel-detected pit" if _pit_conf == PitDetectionConfidence.MEDIUM
                    else "speed-stop pit (no refuel)"),
            event=PitEvent.EXIT,
        ).state
        self._phase = RacePhase.RACING
        self._fuel_lap_start = p.fuel_level
        self._lap_start_time = now
        self._fuel_warned = False   # re-arm warning for the next stint
        if self._session_type == SessionType.PRACTICE:
            self._outlap_pending = True
            print("[StateTracker] Practice pit exit — outlap will be recorded as out-lap")
        # Safety net: if the session was PRACTICE-typed at pit entry (flickered before
        # switching to RACE) the pit-entry fast-path didn't start the timer.  Start it
        # now from pit exit so computed_remaining_ms() works for this stint.
        if self._race_start_time == 0 and self._session_type == SessionType.RACE:
            self._race_start_time = now
            self._race_is_active = True
            print("[StateTracker] implicit race start at pit exit (session-type fallback)")
        # Use the user-selected override if set (e.g. Qualifying chosen in Live tab),
        # otherwise fall back to the packet-detected session type.
        _pit_exit_session_type = (
            self._session_type_override
            if self._session_type_override is not None
            else self._session_type
        )
        self._emit(TelemetryEvent(
            type=EventType.PIT_EXIT,
            data={"fuel_added": fuel_added, "session_type": _pit_exit_session_type.value},
            priority=Priority.INFO,
        ))

    def _check_lap(self, p: GT7Packet, now: float) -> None:
        # Allow during IN_PIT so laps completed while in the pit lane are not lost.
        # (The start/finish line can be crossed while stationary in pit if it is
        # near the pit entry — without this guard those laps are silently dropped.)
        if self._phase not in (RacePhase.RACING, RacePhase.IN_PIT):
            return

        prev_last_lap_ms = self._prev.last_lap_ms if self._prev else -1

        # Primary trigger: last_lap_ms changes to a new positive value.
        # This is the most reliable signal that GT7 recorded a completed lap,
        # regardless of how laps_completed is indexed or whether it's -1 for
        # timed races.
        if not (p.last_lap_ms > 0 and p.last_lap_ms != prev_last_lap_ms):
            return

        if not p.car_on_track and not p.loading:
            return

        lap_ms  = p.last_lap_ms
        best_ms = p.best_lap_ms
        # Use total laps recorded so far as the 1-based lap number — avoids
        # dependence on GT7's indexing convention for laps_completed.
        lap_num = len(self._lap_time_hist) + 1
        delta_ms = (lap_ms - best_ms) if best_ms > 0 else 0
        fuel_used = max(self._fuel_lap_start - p.fuel_level, 0.0)

        # Outlap after a practice pit exit — record it but flag it so the UI can label it.
        is_out_lap = False
        if self._outlap_pending:
            self._outlap_pending = False
            is_out_lap = True
            print(f"[StateTracker] Outlap ({lap_ms/1000:.1f}s) recorded as out-lap (lap {lap_num})")

        self._lap_fuel_hist.append(fuel_used)
        self._lap_time_hist.append(lap_ms)
        # Group 54: age the current stint by one lap (read-only pit/stint state).
        self._pit_stint = apply_lap_completed(self._pit_stint, len(self._lap_time_hist))

        _st = (
            self._session_type_override
            if self._session_type_override is not None
            else (SessionType.RACE if self._race_is_active else SessionType.PRACTICE)
        )
        record = LapRecord(
            lap_num=lap_num,
            lap_time_ms=lap_ms,
            best_lap_ms=best_ms,
            delta_ms=delta_ms,
            fuel_start=self._fuel_lap_start,
            fuel_end=p.fuel_level,
            fuel_used=fuel_used,
            position=p.current_position,
            is_pit_lap=self._pit_lap,
            timestamp=datetime.datetime.now().strftime("%H:%M:%S"),
            session_type=_st,
            is_out_lap=is_out_lap,
        )
        self._pit_lap = False

        self._emit(TelemetryEvent(
            type=EventType.LAP_COMPLETED,
            data={
                "record": record,
                "has_best": best_ms > 0 and best_ms != lap_ms,
                "race_type": self._race_type,
                "laps_in_race": self._laps_in_race,
                # len(_lap_time_hist) already incremented (append above), so this
                # gives remaining laps after the lap just completed.
                "laps_remaining": max(0, self._laps_in_race - len(self._lap_time_hist)) if self._laps_in_race > 0 else 0,
                "remaining_time_ms": (p.remaining_time_ms if p.remaining_time_ms > 0
                                      else self.computed_remaining_ms()),
                "best_lap_ms": best_ms if best_ms > 0 else lap_ms,
            },
            priority=Priority.HIGH,
        ))

        self._fuel_lap_start = p.fuel_level
        self._lap_start_time = now
        self._prev_laps_completed = p.laps_completed

        # Detect race finish on the same packet as the last lap, before the
        # next packet can be skipped by loading=True (results screen).
        if self._phase in (RacePhase.RACING, RacePhase.IN_PIT):
            if (self._race_type == RaceType.LAP and
                    self._laps_in_race > 0 and
                    len(self._lap_time_hist) >= self._laps_in_race):
                self._phase = RacePhase.FINISHED
                print(f"[StateTracker] RACING->FINISHED (lap race)  laps={len(self._lap_time_hist)}/{self._laps_in_race}")
                self._emit(TelemetryEvent(
                    type=EventType.RACE_FINISHED,
                    data={
                        "position": p.current_position,
                        "total_cars": p.total_cars,
                    },
                    priority=Priority.HIGH,
                ))
            elif (self._race_type == RaceType.TIMED and
                    self.computed_remaining_ms() == 0):
                # Wall-clock race timer expired and driver just crossed the S/F line.
                # Using only computed_remaining_ms() (wall-clock from _race_start_time)
                # prevents false positives from p.remaining_time_ms == 0 which also
                # fires when the qualifying timer expires before the actual race.
                # After FINISHED the phase blocks further pit detection and the
                # results-screen loading=True will reset for the next session.
                self._phase = RacePhase.FINISHED
                print(f"[StateTracker] RACING->FINISHED (timed race)  laps={len(self._lap_time_hist)}")
                self._emit(TelemetryEvent(
                    type=EventType.RACE_FINISHED,
                    data={
                        "position": p.current_position,
                        "total_cars": p.total_cars,
                    },
                    priority=Priority.HIGH,
                ))

    def _check_position(self, p: GT7Packet) -> None:
        cur_pos = p.current_position   # 0 if not in 1-100 range
        if cur_pos <= 0:
            self._prev_position = 0
            return

        if cur_pos == self._prev_position:
            return

        prev = self._prev_position
        self._prev_position = cur_pos

        if prev <= 0:
            # First valid reading — record but don't announce (no reference to compare)
            return

        gained = cur_pos < prev
        self._emit(TelemetryEvent(
            type=EventType.POSITION_CHANGED,
            data={
                "position": cur_pos,
                "prev_position": prev,
                "gained": gained,
                "total_cars": p.total_cars,
            },
            priority=Priority.HIGH,
        ))

    def _check_tyres(self, p: GT7Packet, now: float) -> None:
        # Only monitor tyres during active racing phases.
        # Without this guard, tyre events fire during the results screen
        # (FINISHED) and in the lobby (IDLE / PRE_RACE), flooding the log.
        if self._phase not in (RacePhase.RACING, RacePhase.IN_PIT):
            return
        if p.speed_kmh < 10:
            return
        temps = {
            "fl": p.tyre_temp_fl,
            "fr": p.tyre_temp_fr,
            "rl": p.tyre_temp_rl,
            "rr": p.tyre_temp_rr,
        }
        for key, temp in temps.items():
            new = self._thresholds.classify(temp)
            old = self._tyre_states[key]
            if new == old:
                continue
            self._tyre_states[key] = new

            if new in (TyreState.HOT, TyreState.OVERHEATING):
                # Grip-critical: batch within a 1-second window so all four tyres
                # heating up across a braking zone land in a single grouped event.
                self._pending_tyre.append((key, old, new))
                if self._tyre_deadline == 0.0:
                    self._tyre_deadline = now + 1.0
                # Cancel any pending OPTIMAL for this tyre — superseded by urgent.
                self._tyre_stable_pending.pop(key, None)

            elif new == TyreState.OPTIMAL:
                # Announce once stable for 5 seconds.
                # Covers: cold/warming→optimal (tyre ready) and hot→optimal (cooling OK).
                self._tyre_stable_pending[key] = (new, now + 5.0)

            else:
                # COLD or WARMING: update state only, no announcement.
                # Cancel any pending OPTIMAL so oscillation around OPTIMAL/WARMING
                # boundary doesn't trigger a spurious "tyres optimal" call.
                self._tyre_stable_pending.pop(key, None)

    def _flush_tyre_batch(self, now: float, force: bool) -> None:
        if not self._pending_tyre:
            return
        if not force and now < self._tyre_deadline:
            return
        changes, self._pending_tyre = self._pending_tyre[:], []
        self._tyre_deadline = 0.0

        # Group by new state so we can say "front tyres optimal" instead of two lines
        by_new: dict[TyreState, list[str]] = {}
        for key, _old, new in changes:
            by_new.setdefault(new, []).append(key)

        for new_state, keys in by_new.items():
            self._emit(TelemetryEvent(
                type=EventType.TYRE_STATE,
                data={
                    "keys": keys,
                    "new_state": new_state,
                    "label": self._tyre_group_label(keys),
                },
                priority=Priority.MEDIUM,
            ))

    def _flush_stable_tyres(self, now: float) -> None:
        """Emit queued OPTIMAL tyre announcements whose 5-second stability window has elapsed."""
        if not self._tyre_stable_pending:
            return
        to_emit: dict[TyreState, list[str]] = {}
        done = [k for k, (_, deadline) in self._tyre_stable_pending.items() if now >= deadline]
        for key in done:
            state, _ = self._tyre_stable_pending.pop(key)
            if self._tyre_states[key] == state:   # still in that state after 2 s
                to_emit.setdefault(state, []).append(key)
        for new_state, keys in to_emit.items():
            self._emit(TelemetryEvent(
                type=EventType.TYRE_STATE,
                data={"keys": keys, "new_state": new_state,
                      "label": self._tyre_group_label(keys)},
                priority=Priority.MEDIUM,
            ))

    @staticmethod
    def _tyre_group_label(keys: list[str]) -> str:
        s = set(keys)
        if s == {"fl", "fr", "rl", "rr"}: return "all tyres"
        if s == {"fl", "fr"}:             return "front tyres"
        if s == {"rl", "rr"}:             return "rear tyres"
        if s == {"fl", "rl"}:             return "left tyres"
        if s == {"fr", "rr"}:             return "right tyres"
        if len(keys) == 1:                return _TYRE_NAMES[keys[0]]
        return "tyres"

    def _check_fuel_warning(self, p: GT7Packet) -> None:
        """Emit FUEL_LOW when remaining fuel drops below 2 laps of estimated consumption."""
        if self._phase != RacePhase.RACING or self._fuel_warned:
            return
        avg = self._avg_fuel()
        if avg <= 0 or p.fuel_level <= 0:
            return
        fuel_laps = p.fuel_level / avg
        if fuel_laps < 2.0:
            self._fuel_warned = True
            self._emit(TelemetryEvent(
                type=EventType.FUEL_LOW,
                data={
                    "fuel_laps": fuel_laps,
                    "fuel_level": p.fuel_level,
                    "laps_remaining": self.laps_remaining,
                },
                priority=Priority.HIGH,
            ))

    def _avg_fuel(self) -> float:
        vals = [f for f in self._lap_fuel_hist if f > 0]
        return sum(vals) / len(vals) if vals else 0.0

    def _avg_lap_ms(self) -> float:
        vals = [t for t in self._lap_time_hist if t > 0]
        return sum(vals) / len(vals) if vals else 0.0

    def _emit(self, event: TelemetryEvent) -> None:
        self._seq += 1
        try:
            self._eq.put_nowait((event.priority.value, self._seq, event))
        except Exception:
            pass
