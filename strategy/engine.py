"""Race strategy engine for GT7 VR Dashboard.

Manages a stint-centric race plan, monitors pace/fuel, and announces pit windows.
All announcements go through the VoiceAnnouncer; all UI updates go through SignalBridge.
Thread-safety: on_event() is called from EventDispatcher thread; set_plan() and the
PTT response methods are called from Qt main thread and QueryListener thread respectively.
Internal state mutation is protected by _lock.
"""
from __future__ import annotations

import math
import threading
import time
from dataclasses import dataclass, field
from statistics import mean
from typing import TYPE_CHECKING, Callable, Optional

if TYPE_CHECKING:
    from telemetry.state import RaceStateTracker, TelemetryEvent
    from voice.announcer import VoiceAnnouncer
    from ui.dashboard import SignalBridge
    from data.session_db import SessionDB

from data.session_db import ms_to_str
from telemetry.state import EventType, Priority, TyreState

_FUEL_MULTIPLIERS: dict[str, float] = {"safe": 1.08, "balanced": 1.05, "aggressive": 1.02}

_SLICK_COMPOUNDS = frozenset({
    "soft", "medium", "hard",
    "racing soft", "racing medium", "racing hard",
    "rs", "rm", "rh",
})


@dataclass
class Stint:
    """One tyre set run.  Pit between each consecutive stint."""

    stint_num: int
    laps: int
    compound: str
    ref_lap_ms: int          # 0 = use session best
    pace_threshold_ms: int   # ms above ref before tyre-deg alert

    # Runtime — reset by set_plan / RACE_STARTED
    start_lap: int = field(default=0, repr=False)
    end_lap: int = field(default=0, repr=False)
    completed: bool = field(default=False, repr=False)
    warn_issued: bool = field(default=False, repr=False)
    box_announced: bool = field(default=False, repr=False)
    overdue_warned: bool = field(default=False, repr=False)
    tyre_alert_issued: bool = field(default=False, repr=False)

    def to_dict(self) -> dict:
        return {
            "laps": self.laps,
            "compound": self.compound,
            "ref_lap_ms": self.ref_lap_ms,
            "pace_threshold_ms": self.pace_threshold_ms,
        }

    @classmethod
    def from_dict(cls, d: dict, stint_num: int) -> "Stint":
        return cls(
            stint_num=stint_num,
            laps=int(d.get("laps", 10)),
            compound=str(d.get("compound", "Unknown")),
            ref_lap_ms=int(d.get("ref_lap_ms", 0)),
            pace_threshold_ms=int(d.get("pace_threshold_ms", 2000)),
        )

    def _reset_runtime(self) -> None:
        self.start_lap = 0
        self.end_lap = 0
        self.completed = False
        self.warn_issued = False
        self.box_announced = False
        self.overdue_warned = False
        self.tyre_alert_issued = False


class RaceStrategyEngine:
    """Stint-centric race strategy tracker and voice engineer."""

    def __init__(
        self,
        tracker,
        announcer,
        config,
        bridge,
        db: "Optional[SessionDB]" = None,
    ) -> None:
        self._tracker = tracker
        self._announcer = announcer
        self._config = config
        self._bridge = bridge
        self._db = db
        self._lock = threading.Lock()

        # Degradation cache: per-compound dict from compute_relative_degradation / merge.
        # Keys are compound codes; each value contains at minimum "harder_baseline_ms".
        self._degradation_cache: dict = {}

        self._stints: list[Stint] = []
        self._active = False
        self._ui_race_mode = True   # False when UI is in Practice/Qualifying — blocks RACE_STARTED
        self._qualifying_mode: bool = False  # True when UI is in Qualifying specifically
        self._recent_lap_times: list[int] = []
        self._rain_condition = False
        self._damage_level = ""
        self._recalc_cooldown_until = 0.0
        self._last_avg_fuel_ref = 0.0

        # Per-lap target monitoring state
        self._slow_lap_count = 0
        self._fast_fuel_count = 0

        # Post-damage monitoring state
        self._post_damage_laps = 0
        self._pre_damage_ref_ms = 0
        self._damage_pit_recommended = False

        # Grip-loss detection state
        self._recent_lockups:   list[float] = []
        self._recent_wheelspin: list[float] = []
        self._recent_oversteer: list[float] = []
        self._grip_alert_until: float = 0.0
        self._consecutive_grip_laps: int = 0
        self._grip_recalc_done: bool = False

        # No-ABS regulation state (Group 62)
        self._no_abs: bool = False

        # Mid-race re-plan state
        self._replan_in_flight: bool = False
        self._adapted_plan: bool = False
        self._replan_callback: Optional[Callable[[str], None]] = None

    # ------------------------------------------------------------------
    # Public API (Qt main thread)
    # ------------------------------------------------------------------

    def set_race_active(self, enabled: bool) -> None:
        """Suppress pit/strategy alerts when not in Race mode (Practice/Qualifying).
        Also gates RACE_STARTED so switching to Practice prevents the next race start
        from re-activating the engine even if game telemetry fires the event.
        """
        with self._lock:
            self._ui_race_mode = enabled
            if not enabled:
                self._active = False

    def set_qualifying_active(self, enabled: bool) -> None:
        """Track whether the UI is in Qualifying mode specifically.

        Called by the dashboard from _on_live_mode_changed.  Lets _on_race_start
        distinguish Qualifying from Practice so it can announce the one-time
        qualifying session acknowledgement.
        """
        with self._lock:
            self._qualifying_mode = enabled

    def set_abs_allowed(self, enabled: bool) -> None:
        """Record whether ABS is allowed in the current event.

        Called by the dashboard when the active event context changes.
        When enabled=False the engine will announce per-lap no-ABS braking cues.
        """
        with self._lock:
            self._no_abs = not bool(enabled)

    def set_degradation_cache(self, cache: dict) -> None:
        """Store the per-compound degradation dict on the engine.

        The cache is used by _check_tyre_degradation to decide whether to use
        the harder-compound baseline pace (when harder_baseline_ms is present)
        or fall back to the ref + pace_threshold_ms logic.

        Parameters
        ----------
        cache:
            Dict keyed by compound code.  Each value is a per-compound result
            dict as returned by compute_relative_degradation / analyse_tyre_degradation.
            May be {} or None to clear.  Stored thread-safely.
        """
        with self._lock:
            self._degradation_cache = dict(cache) if cache else {}

    def set_plan(self, stints: list[Stint]) -> None:
        with self._lock:
            self._stints = stints
            self._active = False
            self._recent_lap_times = []
            self._rain_condition = False
            self._damage_level = ""
            self._recalc_cooldown_until = 0.0
            self._last_avg_fuel_ref = 0.0
            self._slow_lap_count = 0
            self._fast_fuel_count = 0
            self._post_damage_laps = 0
            self._pre_damage_ref_ms = 0
            self._damage_pit_recommended = False
            self._recent_lockups = []
            self._recent_wheelspin = []
            self._recent_oversteer = []
            self._grip_alert_until = 0.0
            self._consecutive_grip_laps = 0
            self._grip_recalc_done = False
            self._replan_in_flight = False  # I3: loading a new plan cancels any stale in-flight replan
            self._adapted_plan = False      # I3: fresh plan is not yet adapted
            self._assign_lap_ranges()
        print(f"[Strategy] plan set: {len(stints)} stints")
        if self._bridge:
            self._bridge.strategy_status_changed.emit(self._build_status_str())

    # ------------------------------------------------------------------
    # Event dispatch (EventDispatcher thread)
    # ------------------------------------------------------------------

    def on_event(self, event) -> None:
        with self._lock:
            if not self._stints:
                return
            et = event.type
            if et == EventType.RACE_STARTED:
                self._on_race_start(event.data)
            elif et == EventType.LAP_COMPLETED and self._active:
                self._on_lap_completed(event.data)
            elif et == EventType.PIT_EXIT and self._active:
                self._on_pit_exit(event.data)
            elif et == EventType.RACE_FINISHED:
                self._active = False

    # ------------------------------------------------------------------
    # PTT response methods (QueryListener thread)
    # ------------------------------------------------------------------

    def build_pit_window_response(self, laps_recorded: int) -> str:
        with self._lock:
            if not self._stints:
                return "No strategy loaded. Pit when you judge."
            stint = self._active_stint()
            if stint is None:
                return "All planned stops done. Push to the flag."
            next_comp = self._next_compound(stint)
            if laps_recorded > stint.end_lap:
                return f"Stop {stint.stint_num} is overdue. Box now. Fit {next_comp}."
            laps_to_go = stint.end_lap - laps_recorded
            return (f"Stop {stint.stint_num} in {laps_to_go} lap(s). "
                    f"Box on lap {stint.end_lap}. Fit {next_comp}.")

    def build_strategy_response(self) -> str:
        with self._lock:
            if not self._stints:
                return "No strategy loaded. Set your stint plan in the Strategy tab."
            if not self._active:
                return "Race has not started yet. Strategy will activate at race start."
            stint = self._active_stint()
            if stint is None:
                return "All stints complete. Race strategy finished."
            laps_recorded = self._tracker.laps_recorded
            laps_until = stint.end_lap - laps_recorded
            fuel_str = self._fuel_target_str(stint)
            overdue = laps_recorded > stint.end_lap + 2
            if overdue:
                extra = laps_recorded - stint.end_lap
                return (f"Stop {stint.stint_num} is overdue by {extra} laps. "
                        f"Pit as soon as possible. {fuel_str}.")
            laps_word = "lap" if laps_until == 1 else "laps"
            total = len(self._stints)
            return (f"Next stop is stop {stint.stint_num} at lap {stint.end_lap}, "
                    f"{max(0, laps_until)} {laps_word} away. "
                    f"{fuel_str}. "
                    f"Fit {self._next_compound(stint)} tyres. "
                    f"Stop {stint.stint_num} of {total}.")

    def build_pace_response(self) -> str:
        with self._lock:
            if len(self._recent_lap_times) < 3:
                return "Not enough laps yet to assess pace."
            last3 = self._recent_lap_times[-3:]
            avg_recent = mean(last3)
            best = self._tracker.best_lap_ms
            if best <= 0:
                best = avg_recent
            delta_s = (avg_recent - best) / 1000.0
            if last3[-1] < last3[-2] < last3[-3]:
                trend = "improving"
            elif last3[-1] > last3[-2] > last3[-3]:
                trend = "falling away"
            else:
                trend = "consistent"
            msg = (f"Last 3 laps average {delta_s:+.1f} seconds from your best. "
                   f"Pace is {trend}.")
            stint = self._active_stint()
            if stint is not None:
                ref = stint.ref_lap_ms if stint.ref_lap_ms > 0 else best
                if ref > 0 and avg_recent > ref + stint.pace_threshold_ms:
                    msg += " Tyre performance is below reference — consider pitting."
            return msg

    def handle_rain_report(self) -> str:
        with self._lock:
            self._rain_condition = True
            self._rain_recalculate()
            stint = self._active_stint()
            if stint is None:
                msg = ("Rain noted. No active stint in plan. "
                       "Consider switching to wet tyres immediately.")
            else:
                fuel_str = self._fuel_target_str(stint)
                msg = (f"Rain noted. Strategy updated for wet conditions. "
                       f"Slick tyres will degrade quickly. "
                       f"Updated pit window is now lap {stint.end_lap}. "
                       f"{fuel_str}. "
                       f"Consider switching to intermediates or wets.")
            if self._bridge:
                self._bridge.strategy_status_changed.emit(self._build_status_str())
            return msg

    def handle_damage_report(self, text: str) -> str:
        with self._lock:
            major_words = {"major", "bad", "severe", "heavy", "serious", "significant"}
            is_major = any(w in text.lower() for w in major_words)

            # Capture pre-damage pace for subsequent monitoring
            if self._recent_lap_times:
                samples = self._recent_lap_times[-3:]
                self._pre_damage_ref_ms = int(mean(samples))
            elif self._tracker.best_lap_ms > 0:
                self._pre_damage_ref_ms = self._tracker.best_lap_ms
            self._post_damage_laps = 0
            self._damage_pit_recommended = False

            if is_major:
                self._damage_level = "major"
                stint = self._active_stint()
                if stint is None:
                    return "Major damage noted. Pit as soon as safely possible."
                fuel_str = self._fuel_target_str(stint)
                return (f"Major damage noted. Recommending pit as soon as possible. "
                        f"Your next window is at lap {stint.end_lap}. "
                        f"{fuel_str}, fit {self._next_compound(stint)}.")
            else:
                self._damage_level = "minor"
                return ("Minor damage noted. I will monitor your pace. "
                        "If lap times drop significantly I will alert you.")

    def build_fuel_check_response(self) -> str:
        with self._lock:
            avg = self._tracker.avg_fuel_per_lap
            if avg <= 0:
                return "Not enough data for fuel strategy check."
            strategy = self._config.get("fuel", {}).get("strategy", "balanced").lower()
            multiplier = _FUEL_MULTIPLIERS.get(strategy, 1.05)
            incomplete = [s for s in self._stints if not s.completed]
            laps_remaining = sum(s.laps for s in incomplete)
            fuel_needed = avg * laps_remaining * multiplier
            fuel_have = self._tracker.last_fuel
            surplus = fuel_have - fuel_needed
            if surplus > avg:
                return (f"Fuel check: you have {surplus:.1f} litres spare. "
                        f"You can push harder or save time in the next pit stop.")
            elif surplus < -avg:
                return (f"Fuel warning: you are {abs(surplus):.1f} litres short of strategy. "
                        f"Lift and coast, or plan an extra pit stop.")
            else:
                return (f"Fuel is on strategy. {fuel_have:.1f} litres remaining, "
                        f"need approximately {fuel_needed:.1f} to finish.")

    # ------------------------------------------------------------------
    # Accessors for UI
    # ------------------------------------------------------------------

    def stints(self) -> list[Stint]:
        with self._lock:
            return list(self._stints)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _assign_lap_ranges(self) -> None:
        cursor = 1
        for s in self._stints:
            s._reset_runtime()
            s.start_lap = cursor
            s.end_lap = cursor + s.laps - 1
            cursor = s.end_lap + 1

    def _active_stint(self):
        for s in self._stints:
            if not s.completed:
                return s
        return None

    def _next_compound(self, current_stint: Stint) -> str:
        idx = self._stints.index(current_stint)
        if idx + 1 < len(self._stints):
            return self._stints[idx + 1].compound
        return current_stint.compound

    def _fuel_target_for_next(self, current_stint: Stint) -> float:
        avg = self._tracker.avg_fuel_per_lap
        if avg <= 0:
            return 0.0
        strategy = self._config.get("fuel", {}).get("strategy", "balanced").lower()
        multiplier = _FUEL_MULTIPLIERS.get(strategy, 1.05)
        idx = self._stints.index(current_stint)
        if idx + 1 < len(self._stints):
            next_laps = self._stints[idx + 1].laps
        else:
            laps_rec = self._tracker.laps_recorded
            next_laps = max(1, current_stint.end_lap - laps_rec)
        return avg * next_laps * multiplier

    def _fuel_target_str(self, current_stint: Stint) -> str:
        target = self._fuel_target_for_next(current_stint)
        if target <= 0:
            return "fuel target unknown"
        return f"fuel to {math.ceil(target)} litres"

    def _on_race_start(self, data: dict) -> None:
        # Qualifying mode: fire the one-time session-start acknowledgement and return.
        # The engine does not activate strategy tracking in qualifying.
        if self._qualifying_mode:
            self._adapted_plan = False
            self._announcer.announce(
                "Qualifying session started. Push for your best lap.",
                Priority.HIGH, "strategy_race_start", 0.0,
            )
            return
        if not self._ui_race_mode:
            return  # UI is in Practice — ignore game's race start event
        self._active = True
        self._recent_lap_times = []
        self._rain_condition = False
        self._damage_level = ""
        self._last_avg_fuel_ref = 0.0
        self._slow_lap_count = 0
        self._fast_fuel_count = 0
        self._post_damage_laps = 0
        self._pre_damage_ref_ms = 0
        self._damage_pit_recommended = False
        self._recent_lockups = []
        self._recent_wheelspin = []
        self._recent_oversteer = []
        self._grip_alert_until = 0.0
        self._consecutive_grip_laps = 0
        self._grip_recalc_done = False
        self._adapted_plan = False
        self._replan_in_flight = False  # I2: clear in-flight flag on race start so restart unblocks replan
        self._assign_lap_ranges()
        if not self._stints:
            return
        compounds = ", ".join(s.compound for s in self._stints)
        first_stop = self._stints[0].end_lap
        msg = (f"Strategy loaded. {len(self._stints)} stints: {compounds}. "
               f"First stop at lap {first_stop}.")
        self._announcer.announce(msg, Priority.HIGH, "strategy_race_start", 0.0)
        if self._bridge:
            self._bridge.strategy_status_changed.emit(self._build_status_str())
            # Apply tyre thresholds for the starting compound
            self._bridge.tyre_preset_changed.emit(self._stints[0].compound)

    def _on_lap_completed(self, data: dict) -> None:
        record = data.get("record")
        if record is None:
            return
        laps_recorded = self._tracker.laps_recorded
        lt = record.lap_time_ms
        if lt > 0:
            self._recent_lap_times.append(lt)
            if len(self._recent_lap_times) > 5:
                self._recent_lap_times.pop(0)

        stint = self._active_stint()
        if stint is not None:
            self._check_pit_window(stint, laps_recorded)
            self._check_tyre_degradation(stint, record, laps_recorded)
            self._check_lap_targets(record, stint)

        self._check_damage_pace()
        self._check_fuel_drift()
        self._check_grip_loss(record)
        self._check_no_abs_brake_cue(record)

        if self._bridge:
            self._bridge.strategy_status_changed.emit(self._build_status_str())

    def _on_pit_exit(self, data: dict) -> None:
        next_stint = None
        for s in self._stints:
            if not s.completed:
                s.completed = True
                next_idx = self._stints.index(s) + 1
                if next_idx < len(self._stints):
                    next_stint = self._stints[next_idx]
                    msg = (f"Out of pits. Starting stint {next_stint.stint_num} "
                           f"on {next_stint.compound}. {next_stint.laps} laps planned.")
                    self._announcer.announce(
                        msg, Priority.HIGH,
                        f"strategy_exit_{next_stint.stint_num}", 0.0)
                break
        avg = self._tracker.avg_fuel_per_lap
        if avg > 0:
            self._last_avg_fuel_ref = avg
        # Reset per-lap counters on pit exit (fresh tyre run)
        self._slow_lap_count = 0
        self._fast_fuel_count = 0
        self._consecutive_grip_laps = 0
        self._grip_recalc_done = False
        self._grip_alert_until = 0.0
        self._recent_lockups = []  # Group 62: reset no-ABS lock-up context for new stint
        # Re-arm the mid-race re-plan trigger for the new stint
        self._adapted_plan = False
        if self._bridge:
            self._bridge.strategy_status_changed.emit(self._build_status_str())
            # Update tyre thresholds for the new compound
            if next_stint is not None:
                self._bridge.tyre_preset_changed.emit(next_stint.compound)

    def _check_pit_window(self, stint: Stint, laps_recorded: int) -> None:
        warn_lap = stint.end_lap - 2
        if laps_recorded >= warn_lap and not stint.warn_issued:
            fuel_str = self._fuel_target_str(stint)
            next_comp = self._next_compound(stint)
            msg = (f"Pit window opens in 2 laps. Box on lap {stint.end_lap}. "
                   f"{fuel_str.capitalize()}, fit {next_comp}.")
            self._announcer.announce(msg, Priority.HIGH,
                                     f"strategy_warn_{stint.stint_num}", 0.0)
            stint.warn_issued = True

        if laps_recorded >= stint.end_lap and not stint.box_announced:
            fuel_str = self._fuel_target_str(stint)
            next_comp = self._next_compound(stint)
            msg = (f"Stop {stint.stint_num}: box this lap. "
                   f"{fuel_str.capitalize()}. Fit {next_comp}.")
            self._announcer.announce(msg, Priority.CRITICAL,
                                     f"strategy_box_{stint.stint_num}", 0.0,
                                     interrupt=True)
            stint.box_announced = True

        if laps_recorded > stint.end_lap + 2 and not stint.overdue_warned:
            new_end = self._replan_after_overdue(stint, laps_recorded)
            fuel_str = self._fuel_target_str(stint)
            next_comp = self._next_compound(stint)
            msg = (
                f"Stop {stint.stint_num} window missed. "
                f"Extending stint, new pit window lap {new_end}. "
                f"{fuel_str.capitalize()}, fit {next_comp}."
            )
            self._announcer.announce(
                msg, Priority.CRITICAL,
                f"strategy_replan_{stint.stint_num}", 0.0,
                interrupt=True,
            )
            if self._bridge:
                self._bridge.strategy_status_changed.emit(self._build_status_str())

    def _replan_after_overdue(self, stint: Stint, laps_recorded: int) -> int:
        """Extend the current stint after a missed pit window and redistribute remaining laps.

        Pushes the pit lap 2 laps ahead of now, trims subsequent stints to compensate
        so the total planned race length stays consistent, and resets the window flags
        so the normal warn/box/overdue cycle fires again at the new target.

        Returns the new planned pit lap.
        """
        idx = self._stints.index(stint)
        original_end = stint.end_lap

        new_end = laps_recorded + 2
        laps_extension = new_end - original_end

        stint.laps += laps_extension
        stint.end_lap = new_end

        # Trim subsequent stints last-first to keep total race length consistent
        remaining = [s for s in self._stints[idx + 1:] if not s.completed]
        to_recover = laps_extension
        for rs in reversed(remaining):
            if to_recover <= 0:
                break
            trim = min(to_recover, rs.laps - 1)  # keep at least 1 lap per stint
            rs.laps -= trim
            to_recover -= trim

        # Reassign start/end laps for all subsequent stints
        cursor = new_end + 1
        for rs in self._stints[idx + 1:]:
            if not rs.completed:
                rs.start_lap = cursor
                rs.end_lap = cursor + rs.laps - 1
                cursor = rs.end_lap + 1

        # Reset flags: suppress the 2-lap pre-warn (we're announcing directly),
        # allow box and overdue to fire again at the new window
        stint.warn_issued = True
        stint.box_announced = False
        stint.overdue_warned = False

        return new_end

    def _check_tyre_degradation(self, stint: Stint, record, laps_recorded: int) -> None:
        if stint.tyre_alert_issued:
            return
        if len(self._recent_lap_times) < 3:
            return
        rolling_avg = mean(self._recent_lap_times[-3:])

        # Determine which alert logic to use.
        # If the engine holds a degradation cache and the current stint's compound
        # has a non-None harder_baseline_ms, trigger the alert when the rolling
        # 3-lap average >= harder_baseline_ms.
        # Otherwise fall back to the existing ref + pace_threshold_ms logic.
        compound_cache = self._degradation_cache.get(stint.compound, {})
        harder_baseline_ms = compound_cache.get("harder_baseline_ms") if compound_cache else None

        if harder_baseline_ms is not None:
            # Relative-baseline alert: fire when rolling average meets or exceeds the baseline.
            alert_triggered = rolling_avg >= harder_baseline_ms
            if alert_triggered:
                laps_into = laps_recorded - stint.start_lap + 1
                delta_s = (rolling_avg - harder_baseline_ms) / 1000.0
                msg = (f"Tyre note: {stint.compound} tyres have reached the harder-compound "
                       f"baseline pace ({harder_baseline_ms / 1000:.3f}s). "
                       f"You are {laps_into} laps into this stint. Consider pitting early.")
                self._announcer.announce(msg, Priority.HIGH,
                                         "strategy_tyre_deg", 60.0)
                stint.tyre_alert_issued = True
                self._request_replan(reason="tyre degradation breach")
        else:
            # Fallback: original ref + pace_threshold_ms logic (UNCHANGED)
            best = self._tracker.best_lap_ms
            ref = stint.ref_lap_ms if stint.ref_lap_ms > 0 else best
            if ref <= 0:
                return
            if rolling_avg > ref + stint.pace_threshold_ms:
                laps_into = laps_recorded - stint.start_lap + 1
                delta_s = (rolling_avg - ref) / 1000.0
                msg = (f"Tyre note: {stint.compound} tyres {delta_s:.1f} seconds per lap "
                       f"off reference. You planned {stint.laps} laps but are "
                       f"{laps_into} in. Consider pitting early.")
                self._announcer.announce(msg, Priority.HIGH,
                                         "strategy_tyre_deg", 60.0)
                stint.tyre_alert_issued = True
                self._request_replan(reason="tyre degradation breach")

    def _check_lap_targets(self, record, stint: Stint) -> None:
        """Compare actual lap time and fuel to stint targets; alert only when outside tolerance."""
        cfg = self._config.get("strategy", {})
        tolerance_ms = int(cfg.get("lap_time_tolerance_ms", 1500))
        fuel_tol = float(cfg.get("fuel_tolerance_liters", 0.5))

        ref_ms = stint.ref_lap_ms if stint.ref_lap_ms > 0 else self._tracker.best_lap_ms
        lap_ms = record.lap_time_ms

        # Lap time check — only alert when meaningfully slower than target
        if ref_ms > 0 and lap_ms > 0:
            if lap_ms > ref_ms + tolerance_ms:
                self._slow_lap_count += 1
                delta_s = (lap_ms - ref_ms) / 1000.0
                if self._slow_lap_count >= 2:
                    msg = (f"Pace {delta_s:.1f} seconds off target, "
                           f"{self._slow_lap_count} laps running. Strategy at risk.")
                    self._announcer.announce(
                        msg, Priority.HIGH, "strategy_pace_alert", 30.0)
                else:
                    msg = f"Lap time {delta_s:.1f} seconds below target."
                    self._announcer.announce(
                        msg, Priority.MEDIUM, "strategy_pace_lap", 10.0)
                # Trigger mid-race re-plan once 4 consecutive slow laps are recorded
                if self._slow_lap_count >= 4:
                    self._request_replan(
                        reason=f"{delta_s:.1f}s off target for {self._slow_lap_count} laps"
                    )
            else:
                self._slow_lap_count = 0

        # Fuel check — alert only when burning more than expected (positive drift)
        avg_fuel = self._tracker.avg_fuel_per_lap
        fuel_used = getattr(record, "fuel_used", 0.0)
        if avg_fuel > 0 and fuel_used > 0:
            if fuel_used > avg_fuel + fuel_tol:
                self._fast_fuel_count += 1
                delta = fuel_used - avg_fuel
                if self._fast_fuel_count >= 2:
                    msg = (f"Fuel {delta:.2f} litres over average for "
                           f"{self._fast_fuel_count} consecutive laps. "
                           f"Consider lifting.")
                    self._announcer.announce(
                        msg, Priority.HIGH, "strategy_fuel_alert", 45.0)
            else:
                self._fast_fuel_count = 0

    def _check_damage_pace(self) -> None:
        """Monitor pace after a damage report; recommend pit if pace has degraded."""
        if not self._damage_level:
            return
        if not self._recent_lap_times:
            return
        self._post_damage_laps += 1
        if self._post_damage_laps < 2:
            return
        if self._pre_damage_ref_ms <= 0:
            return
        if self._damage_pit_recommended:
            return

        samples = self._recent_lap_times[-3:] if len(self._recent_lap_times) >= 3 \
                  else self._recent_lap_times
        recent_avg = int(mean(samples))

        if recent_avg > self._pre_damage_ref_ms + 2000:
            delta_s = (recent_avg - self._pre_damage_ref_ms) / 1000.0
            msg = (f"Damage is costing {delta_s:.1f} seconds per lap. "
                   f"Pit recommended at next opportunity.")
            self._announcer.announce(msg, Priority.HIGH, "strategy_damage_pace", 60.0)
            self._damage_pit_recommended = True

        elif self._post_damage_laps >= 4 and recent_avg <= self._pre_damage_ref_ms + 1000:
            msg = "Pace has stabilised after damage. Continuing on strategy."
            self._announcer.announce(msg, Priority.MEDIUM, "strategy_damage_ok", 0.0)
            self._damage_level = ""

    def _rain_recalculate(self) -> None:
        """Adjust remaining stints for wet conditions. Called with _lock held."""
        WET_PACE_PENALTY = 1.12   # 12% slower on wets vs dry reference
        SLICK_RAIN_CAP = 5        # max laps remaining on slicks after rain starts

        laps_done = self._tracker.laps_recorded
        best_ref = self._tracker.best_lap_ms

        for s in self._stints:
            if s.completed:
                continue

            # Adjust ref pace to wet estimate
            dry_ref = s.ref_lap_ms if s.ref_lap_ms > 0 else best_ref
            if dry_ref > 0:
                s.ref_lap_ms = int(dry_ref * WET_PACE_PENALTY)

            # Shorten slick stints — tyres become undriveable in rain
            if s.compound.lower() in _SLICK_COMPOUNDS:
                if s.start_lap <= laps_done:
                    # Currently active stint: cap remaining laps at SLICK_RAIN_CAP
                    laps_remaining = s.end_lap - laps_done
                    if laps_remaining > SLICK_RAIN_CAP:
                        s.end_lap = laps_done + SLICK_RAIN_CAP
                        s.laps = s.end_lap - s.start_lap + 1
                else:
                    # Future stint on slicks: cap stint length
                    if s.laps > SLICK_RAIN_CAP:
                        s.laps = SLICK_RAIN_CAP
                        s.end_lap = s.start_lap + s.laps - 1

    def _check_fuel_drift(self) -> None:
        avg = self._tracker.avg_fuel_per_lap
        if avg <= 0:
            return
        if self._last_avg_fuel_ref <= 0:
            self._last_avg_fuel_ref = avg
            return
        drift = abs(avg - self._last_avg_fuel_ref) / self._last_avg_fuel_ref
        now = time.monotonic()
        if drift > 0.15 and now > self._recalc_cooldown_until:
            self._last_avg_fuel_ref = avg
            self._recalc_cooldown_until = now + 60.0
            msg = (f"Fuel consumption changed to {avg:.1f} litres per lap. "
                   f"Pit fuel targets updated.")
            self._announcer.announce(msg, Priority.HIGH, "strategy_recalc", 30.0)

    # ------------------------------------------------------------------
    # Mid-race re-plan (called from telemetry thread / Qt main thread)
    # ------------------------------------------------------------------

    def _request_replan(self, reason: str) -> None:
        """Safely request a mid-race strategy re-plan.

        Called from the telemetry thread (inside _on_lap_completed) or from
        _check_tyre_degradation.  Must not block.  Sets in-flight flag, announces
        a standby message, and invokes the callback (if set) with the reason string.
        """
        if self._replan_in_flight or self._adapted_plan:
            return
        self._replan_in_flight = True
        self._announcer.announce(
            "Adapting strategy, stand by.",
            Priority.HIGH, "strategy_replan_request", 0.0,
        )
        if self._replan_callback is not None:
            self._replan_callback(reason)

    def apply_replan(self, result) -> None:
        """Apply a new strategy returned by the AI re-plan worker.

        Called on the Qt main thread by the dashboard after the off-thread
        worker posts a successful result.  ``result`` is a StrategyResult
        (iterable of StrategyOption).

        If result has no strategies, delegates to replan_failed().
        """
        options = list(result)
        if not options:
            self.replan_failed()
            return

        with self._lock:
            first_option = options[0]
            new_stint_dicts = list(first_option.stints)
            if not new_stint_dicts:
                pass  # fall through — treat empty stints as failure
            else:
                # Keep completed stints; rebuild remaining ones from the AI result
                completed = [s for s in self._stints if s.completed]
                current_lap = self._tracker.laps_recorded

                new_stints: list[Stint] = []
                start_cursor = current_lap
                for i, d in enumerate(new_stint_dicts):
                    stint_num = len(completed) + i + 1
                    s = Stint.from_dict(d, stint_num=stint_num)
                    s.start_lap = start_cursor
                    s.end_lap = start_cursor + s.laps - 1
                    start_cursor = s.end_lap + 1
                    new_stints.append(s)

                self._stints = completed + new_stints
                self._adapted_plan = True
                self._slow_lap_count = 0
                self._replan_in_flight = False

                # Build announcement
                new_pit_lap = new_stints[0].end_lap if new_stints else 0
                new_ref_ms = new_stints[0].ref_lap_ms if new_stints else 0
                ref_str = ms_to_str(new_ref_ms) if new_ref_ms > 0 else "unchanged"
                msg = (
                    f"Strategy adapted. "
                    f"New pit window lap {new_pit_lap}. "
                    f"Target {ref_str} per lap."
                )
                self._announcer.announce(msg, Priority.HIGH, "strategy_adapted", 0.0)

                if self._bridge:
                    self._bridge.strategy_status_changed.emit(self._build_status_str())
                return

        # If we reach here, new_stint_dicts was empty
        self.replan_failed()

    def replan_failed(self) -> None:
        """Called when a mid-race re-plan attempt returns no usable result.

        Clears the in-flight flag so a future trigger can retry.  Stints are
        left intact.  Stays silent to avoid distracting the driver.
        """
        with self._lock:
            self._replan_in_flight = False

    def _build_status_str(self) -> str:
        if not self._stints:
            return "No plan loaded"
        if not self._active:
            return f"Plan ready: {len(self._stints)} stints"
        modifiers = []
        if self._rain_condition:
            modifiers.append("RAIN")
        if self._damage_level:
            modifiers.append(f"DAMAGE({self._damage_level})")
        prefix = f"[{', '.join(modifiers)}] " if modifiers else ""
        parts = []
        for s in self._stints:
            state = "done" if s.completed else "active"
            parts.append(f"S{s.stint_num}({s.compound},{s.start_lap}-{s.end_lap},{state})")
        return prefix + " | ".join(parts)

    # ------------------------------------------------------------------
    # Grip-loss detection
    # ------------------------------------------------------------------

    def _check_grip_loss(self, record) -> None:
        """Detect grip loss from per-lap metrics and announce when confidence is high enough."""
        if record is None:
            return

        # Update rolling event-count lists (cap at 10 laps)
        self._recent_lockups.append(getattr(record, "lock_up_count", 0))
        self._recent_wheelspin.append(getattr(record, "wheelspin_count", 0))
        self._recent_oversteer.append(getattr(record, "oversteer_count", 0))
        if len(self._recent_lockups)   > 10: self._recent_lockups.pop(0)
        if len(self._recent_wheelspin) > 10: self._recent_wheelspin.pop(0)
        if len(self._recent_oversteer) > 10: self._recent_oversteer.pop(0)

        # Need at least 3 reference laps before comparing
        if len(self._recent_lockups) < 3:
            return

        # Skip the first 3 laps of the current stint (tyres still settling)
        stint = self._active_stint()
        if stint is not None:
            laps_into_stint = self._tracker.laps_recorded - stint.start_lap
            if laps_into_stint < 3:
                return

        score, alert_type = self._compute_grip_score(record)

        # Determine level string
        if score >= 70:
            level = "significant"
        elif score >= 50:
            level = "warning"
        elif score >= 30:
            level = "watch"
        else:
            level = "normal"

        # Always emit bridge signal so UI stays current
        if self._bridge:
            self._bridge.grip_loss_detected.emit(score, level)

        if score < 30:
            self._consecutive_grip_laps = 0
            return

        if score >= 50:
            self._consecutive_grip_laps += 1
            now = time.monotonic()
            if self._consecutive_grip_laps >= 2 and now > self._grip_alert_until:
                self._announce_grip_loss(score, alert_type)
                self._grip_alert_until = now + 60.0
                if self._db is not None:
                    try:
                        lap_num = getattr(self._tracker, "laps_recorded", 0)
                        self._db.write_grip_alert(
                            session_id=0,
                            lap_num=lap_num,
                            score=score,
                            alert_type=alert_type,
                        )
                    except Exception:
                        pass
            if score >= 70 and not self._grip_recalc_done:
                self._grip_recalculate(record)
                self._grip_recalc_done = True
        else:
            self._consecutive_grip_laps = max(0, self._consecutive_grip_laps - 1)

    def _compute_grip_score(self, record) -> tuple[int, str]:
        """Return (confidence_score 0-100, alert_type 'front'/'rear'/'tyre'/'pace')."""
        score = 0
        front_pts = 0
        rear_pts = 0
        tyre_pts = 0

        # --- Pace component (0-38 pts) ---
        recent_times = self._recent_lap_times[-5:]
        if len(recent_times) >= 3 and getattr(record, "lap_time_ms", 0) > 0:
            avg_t = mean(recent_times)
            delta = record.lap_time_ms - avg_t
            if delta > 2000:
                score += 38
            elif delta > 1200:
                score += 25
            elif delta > 600:
                score += 10

        # --- Wheel-event components ---
        def _roll_avg(lst: list) -> float:
            sample = lst[-5:]
            return mean(sample) if len(sample) >= 2 else 0.0

        avg_lock = _roll_avg(self._recent_lockups[:-1])  # exclude current lap
        cur_lock = getattr(record, "lock_up_count", 0)
        if avg_lock > 0:
            if cur_lock > avg_lock * 2.0:
                front_pts += 20
            elif cur_lock > avg_lock * 1.5:
                front_pts += 10

        avg_spin = _roll_avg(self._recent_wheelspin[:-1])
        cur_spin = getattr(record, "wheelspin_count", 0)
        if avg_spin > 0:
            if cur_spin > avg_spin * 2.0:
                rear_pts += 20
            elif cur_spin > avg_spin * 1.5:
                rear_pts += 10

        avg_os = _roll_avg(self._recent_oversteer[:-1])
        cur_os = getattr(record, "oversteer_count", 0)
        if avg_os > 0:
            if cur_os > avg_os * 2.0:
                rear_pts += 12
            elif cur_os > avg_os * 1.5:
                rear_pts += 6

        # --- Tyre temperature component (0-20 pts) ---
        try:
            tyre_states = list(self._tracker.tyre_states.values())
            if any(s == TyreState.OVERHEATING for s in tyre_states):
                tyre_pts = 20
            elif any(s == TyreState.HOT for s in tyre_states):
                tyre_pts = 10
            elif all(s in (TyreState.COLD, TyreState.WARMING) for s in tyre_states):
                tyre_pts = 10
        except Exception:
            pass

        score += front_pts + rear_pts + tyre_pts

        # Determine alert type from largest contributor
        if tyre_pts >= max(front_pts, rear_pts) and tyre_pts >= 10:
            alert_type = "tyre"
        elif front_pts > rear_pts:
            alert_type = "front"
        elif rear_pts > 0:
            alert_type = "rear"
        else:
            alert_type = "pace"

        return min(100, score), alert_type

    def _announce_grip_loss(self, score: int, alert_type: str) -> None:
        _msgs = {
            "front": "Front grip is dropping. Ease the entry speed and release brake smoother.",
            "rear":  "Rear is unstable on exit. Short shift and feed throttle in.",
            "tyre":  "Tyres are outside the working window. Bring the car in gently.",
            "pace":  "Grip looks reduced. Brake a touch earlier next lap.",
        }
        text = _msgs.get(alert_type, _msgs["pace"])
        if score >= 70:
            text = "Significant grip loss. " + text
        self._announcer.announce(text, Priority.HIGH, "rt_grip_loss", 0.0)

    def _grip_recalculate(self, record) -> None:
        """Raise current stint's pace reference to reflect grip-induced lap time loss."""
        recent = self._recent_lap_times[-3:]
        if len(recent) < 2:
            return
        avg = mean(recent)
        stint = self._active_stint()
        if stint is None or stint.ref_lap_ms <= 0 or avg <= 0:
            return
        delta_ms = avg - stint.ref_lap_ms
        if delta_ms < 300:
            return
        stint.ref_lap_ms = int(avg)
        delta_s = delta_ms / 1000
        msg = (f"Pace loss suggests grip is down. "
               f"Target lap time adjusted by {delta_s:.1f} seconds.")
        self._announcer.announce(msg, Priority.HIGH, "strategy_recalc", 30.0)
        if self._bridge:
            self._bridge.strategy_status_changed.emit(self._build_status_str())

    # ------------------------------------------------------------------
    # No-ABS regulation coaching (Group 62)
    # ------------------------------------------------------------------

    def _check_no_abs_brake_cue(self, record) -> None:
        """Announce per-lap no-ABS braking coaching based on the lock-up trend.

        Only active when set_abs_allowed(False) has been called.  Uses the
        _recent_lockups window already maintained by _check_grip_loss (which
        runs immediately before this method in _on_lap_completed).

        Fires at most once per 60 seconds via the announcer's built-in cooldown.
        """
        if not self._no_abs:
            return
        if not self._recent_lockups:
            return  # zero-lap baseline guard — no cue on a fresh/empty window

        def _roll_avg(lst: list) -> float:
            sample = lst[-5:]
            return mean(sample) if len(sample) >= 2 else 0.0

        # Exclude the most recent lap from the rolling average (as _compute_grip_score does)
        avg = _roll_avg(self._recent_lockups[:-1])
        latest = self._recent_lockups[-1]
        prev = self._recent_lockups[-2] if len(self._recent_lockups) >= 2 else 0

        if avg >= 1 or latest > prev:
            msg = (
                "Ease brake pressure or brake a touch earlier — fronts locking without ABS."
            )
            self._announcer.announce(msg, Priority.HIGH, "no_abs_brake_cue", 60.0)
        else:
            msg = (
                "Brakes clean — you have margin to add brake pressure or brake later."
            )
            self._announcer.announce(msg, Priority.MEDIUM, "no_abs_brake_cue", 60.0)
