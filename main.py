"""GT7 VR Dashboard — entry point.

Run:  python main.py
      python main.py --config path/to/config.json
"""
from __future__ import annotations
import json
import logging
import math
import queue
import sys
import threading
import time
from pathlib import Path

_log = logging.getLogger(__name__)

from PyQt6.QtCore import QTimer
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QApplication

from telemetry.packet import parse_packet, GT7Packet
from telemetry.listener import UDPListener
from telemetry.state import (
    RaceStateTracker, TyreThresholds, TelemetryEvent, EventType, Priority,
    SessionType,
)
from voice.announcer import VoiceAnnouncer, AnnouncerEventHandler
from voice.query_listener import QueryListener
from data.logger import LapDataLogger
from ui.dashboard import MainWindow, SignalBridge
from strategy.engine import RaceStrategyEngine, Stint
from telemetry.recorder import LapTelemetryRecorder
from strategy.driving_advisor import DrivingAdvisor
from data.session_db import SessionDB

# ---------------------------------------------------------------------------
# Named constants — replace all magic numbers in on_packet / EventDispatcher
# ---------------------------------------------------------------------------
OVERSTEER_YAW_THRESHOLD_RAD_S = 1.8
OVERSTEER_REAR_SLIP_RATIO     = 1.15
OVERSTEER_SUSTAINED_SEC       = 0.3
OVERSTEER_COOLDOWN_SEC        = 8.0
EVENT_QUEUE_TIMEOUT_SEC       = 0.5

# ---------------------------------------------------------------------------
# Module-level threading lock for cross-thread shared state
# ---------------------------------------------------------------------------
_state_lock = threading.Lock()


class _DebugWriter:
    """Tees print() output to both the real stdout and the Debug tab event log.

    Installed after SignalBridge is created so bridge.event_log_entry is available.
    Lines are only emitted to the bridge when they contain printable content so
    blank flush() calls don't flood the log.
    """

    def __init__(self, orig, bridge) -> None:
        self._orig   = orig
        self._bridge = bridge
        self._buf    = ""
        self._active = False  # recursion guard

    def write(self, text: str) -> None:
        self._orig.write(text)
        if self._active:
            return
        self._buf += text
        while "\n" in self._buf:
            line, self._buf = self._buf.split("\n", 1)
            if line.strip():
                self._active = True
                try:
                    self._bridge.event_log_entry.emit(line)
                finally:
                    self._active = False

    def flush(self) -> None:
        self._orig.flush()


# Config defaults + loading now live in ``config_paths`` (pure, testable, and
# the single owner of the read/write guardrail that stops tests clobbering the
# user's real config.json). Re-exported here so existing ``main.DEFAULT_CONFIG``
# / ``main.load_config`` references keep working.
from config_paths import (  # noqa: E402
    DEFAULT_CONFIG,
    load_config,
    resolve_config_path,
)


# ---------------------------------------------------------------------------
# Pure helpers — shift-beep logic (module-level so they are unit-testable)
# ---------------------------------------------------------------------------

def resolve_threshold(
    live_mode: str,
    is_racing: bool,
    practice_is_qual: bool,
    sb: dict,
) -> tuple[str, float]:
    """Return (thresh_key, thresh) for the shift-beep RPM gate.

    Selection rules:
      - Race mode (is_racing=True)  -> "race_rpm"
      - "Qualifying" (live_mode)    -> "qual_rpm"
      - "Practice"                  -> "qual_rpm" if practice_is_qual else "race_rpm"
      - Any other live_mode         -> "qual_rpm"

    Falls back to legacy "rpm" key and then 7000 so an empty dict never raises.
    """
    if is_racing:
        key = "race_rpm"
    elif live_mode == "Practice":
        key = "qual_rpm" if practice_is_qual else "race_rpm"
    else:
        key = "qual_rpm"
    thresh = float(sb.get(key) or sb.get("rpm", 7000))
    return key, thresh


def driving_gate(
    car_on_track: bool,
    paused: bool,
    loading: bool,
    in_gear: bool,
    speed_kmh: float,
) -> bool:
    """Return True only when the car is on track — the beep-worthy state.

    The user's requirement is explicit: the shift beep must fire ONLY when on
    track. So this gates strictly on ``car_on_track`` (and never while paused or
    loading), muting the beep everywhere else — garage, menus, replays, the PIT
    LANE, and formation / roll-out laps. An earlier version also allowed any
    moving, in-gear car through; that let the beep fire in the pit lane and
    replays, which is exactly the off-track beeping being reported. ``in_gear``
    and ``speed_kmh`` are kept in the signature (call site / future use) but no
    longer widen the gate.
    """
    if paused or loading:
        return False
    return bool(car_on_track)


def should_shift_beep(
    prev_gear: int,
    cur_gear: int,
    rpm: float,
    threshold: float,
    shift_above: bool,
    enabled: bool,
    muted_until: float,
    downshift_muted_until: float,
    now: float,
) -> tuple[bool, bool, float]:
    """Decide whether to fire a shift beep this packet.

    Returns (beep, new_shift_above, new_downshift_muted_until).

    Rules:
    - enabled=False  -> no beep; shift_above and downshift_muted_until unchanged.
    - Gear neutral (0) or reverse (not 1-8) -> no beep.
    - Downshift detected (1<=cur_gear<=8 and prev_gear>0 and cur_gear<prev_gear)
        -> no beep; set new_downshift_muted_until = now + 0.3; reset shift_above=True
           so a throttle blip after the downshift doesn't fire.
    - Upshift / steady (1<=cur_gear<=8):
        -> beep when rpm>=threshold AND NOT shift_above AND now>=muted_until
           AND now>=downshift_muted_until; then new_shift_above=True.
    - Re-arm: when rpm < 0.95*threshold -> new_shift_above=False.
    """
    if not enabled:
        return False, shift_above, downshift_muted_until

    valid_gear = 1 <= cur_gear <= 8
    if not valid_gear:
        return False, shift_above, downshift_muted_until

    # Downshift: cur_gear < prev_gear (and both are valid drive gears or prev was neutral)
    if prev_gear > 0 and cur_gear < prev_gear:
        # Mute beep for 0.3 s and keep shift_above=True (suppress blip spike)
        return False, True, now + 0.3

    # Re-arm hysteresis when RPM drops back below 95 % of threshold
    new_shift_above = shift_above
    if rpm < threshold * 0.95:
        new_shift_above = False

    # Fire beep
    if (rpm >= threshold
            and not new_shift_above
            and now >= muted_until
            and now >= downshift_muted_until):
        return True, True, downshift_muted_until

    return False, new_shift_above, downshift_muted_until


# ---------------------------------------------------------------------------
# Event dispatcher thread
# ---------------------------------------------------------------------------

class EventDispatcher(threading.Thread):
    """Drains the priority event queue and fans out to handlers."""

    def __init__(
        self,
        event_queue: "queue.PriorityQueue",
        announcer_handler: AnnouncerEventHandler,
        logger: LapDataLogger,
        bridge: SignalBridge,
        shift_muted_until: "list[float] | None" = None,
        strategy_engine=None,
        recorder=None,
        db=None,
        config=None,
        car_id_ref=None,
        is_racing_ref: "list[bool] | None" = None,
        tracker=None,
    ) -> None:
        super().__init__(daemon=True, name="EventDispatcher")
        self._eq = event_queue
        self._ah = announcer_handler
        self._logger = logger
        self._bridge = bridge
        self._shift_muted_until = shift_muted_until
        self._is_racing = is_racing_ref
        self._strategy_engine = strategy_engine
        self._recorder = recorder
        self._db = db
        self._car_id_ref = car_id_ref or [0]
        self._tracker = tracker
        self._session_id: int = 0
        self._stop = threading.Event()
        # Legacy Fan-Out Removal Phase 6a: the dispatcher no longer reads
        # config["strategy"] in the telemetry event path. It holds a frozen
        # SessionTag (track/car/config_id/event_id), seeded here from the config
        # it was constructed with (one-time, before the thread starts) and
        # re-pushed by the UI (MainWindow._push_session_tag) whenever a
        # tag-relevant field changes. Immutable swap → no lock needed.
        from data.session_context import SessionTag
        self._session_tag = SessionTag.from_strategy(
            (config or {}).get("strategy", {}))

    def set_session_id(self, sid: int) -> None:
        self._session_id = sid

    def set_session_tag(self, tag) -> None:
        """Atomically swap the frozen session tag (called from the UI thread)."""
        if tag is not None:
            self._session_tag = tag

    def stop(self) -> None:
        self._stop.set()
        try:
            self._eq.put_nowait((0, -1, None))
        except Exception:
            pass

    def run(self) -> None:
        while not self._stop.is_set():
            try:
                _, _, event = self._eq.get(timeout=EVENT_QUEUE_TIMEOUT_SEC)
            except queue.Empty:
                continue

            if event is None:
                break

            try:
                self._dispatch(event)
            except Exception as e:
                _log.error("Dispatcher error handling %s: %s", event.type, e)

    def _dispatch(self, event: TelemetryEvent) -> None:
        t = event.type
        log_msg = f"{time.strftime('%H:%M:%S')} [{t.value}]"

        if t == EventType.LAP_COMPLETED:
            record = event.data["record"]
            self._logger.add_lap(record)
            self._bridge.lap_completed.emit(record)
            log_msg += (f" Lap {record.lap_num} — "
                        f"fuel used {record.fuel_used:.2f}L")
            if self._recorder is not None:
                try:
                    self._recorder.finalize_lap(record.lap_num, record.lap_time_ms)
                except Exception as e:
                    _log.error("Dispatcher recorder error: %s", e)
            if self._db is not None and self._session_id > 0 and self._recorder is not None:
                try:
                    lap_stats = self._recorder.last_lap()
                    tag       = self._session_tag  # frozen SessionTag (Phase 6a)
                    frames    = self._recorder.last_lap_frames()
                    _compound = (
                        getattr(self._tracker, "_current_compound", "")
                        if self._tracker is not None else ""
                    )
                    self._db.write_lap(
                        self._session_id, record.lap_num,
                        record.lap_time_ms, record.fuel_used,
                        lap_stats, compound=_compound,
                        event_id=int(tag.event_id),
                        frames=frames if frames else None,
                        fuel_start=getattr(record, "fuel_start", 0.0),
                        fuel_end=getattr(record, "fuel_end", 0.0),
                        is_pit_lap=bool(getattr(record, "is_pit_lap", False)),
                        is_out_lap=bool(getattr(record, "is_out_lap", False)),
                        delta_ms=int(getattr(record, "delta_ms", 0)),
                        session_type=(record.session_type.value
                                      if hasattr(record.session_type, "value")
                                      else str(getattr(record, "session_type", ""))),
                    )
                except Exception as e:
                    print(f"[Dispatcher] db write_lap error: {e}")

        elif t == EventType.RACE_STARTED:
            rt = event.data.get("race_type")
            log_msg += f" type={rt}"
            self._bridge.race_state_changed.emit("RACING")
            if self._shift_muted_until is not None:
                with _state_lock:
                    self._shift_muted_until[0] = 0.0  # re-enable shift beeps for new race
            if self._is_racing is not None:
                with _state_lock:
                    self._is_racing[0] = True          # switch to race shift RPM
            if self._db is not None and self._session_id == 0:
                try:
                    car_id    = int(self._car_id_ref[0])
                    # Phase 6a: fallback race-session open tags from the frozen
                    # SessionTag. (The old strat.get("track", "Unknown") default
                    # was dead code — DEFAULT_CONFIG materialises track = "".)
                    tag       = self._session_tag
                    self._session_id = self._db.open_session(
                        car_id, tag.track, "race", tag.car, tag.config_id,
                        event_id=int(tag.event_id))
                    print(f"[Dispatcher] fallback race session opened: id={self._session_id} "
                          f"car={car_id} ({tag.car}) track={tag.track}")
                except Exception as e:
                    print(f"[Dispatcher] db open_session error: {e}")

        elif t == EventType.RACE_FINISHED:
            self._bridge.race_state_changed.emit("FINISHED")
            if self._is_racing is not None:
                with _state_lock:
                    self._is_racing[0] = False         # back to qual/practice RPM
            if self._shift_muted_until is not None:
                # Suppress shift beeps for 15 s so the race-finish announcement
                # isn't interrupted by post-race RPM spikes.
                with _state_lock:
                    self._shift_muted_until[0] = time.time() + 15.0

        elif t == EventType.PIT_ENTRY:
            target = event.data.get("fuel_target", 0.0)
            log_msg += f" fuel_target={target:.1f}L"
            self._bridge.race_state_changed.emit("IN PIT")

        elif t == EventType.PIT_EXIT:
            added = event.data.get("fuel_added", 0.0)
            log_msg += f" fuel_added={added:.1f}L"
            self._bridge.race_state_changed.emit("RACING")

        self._ah.handle(event)
        if self._strategy_engine is not None:
            try:
                self._strategy_engine.on_event(event)
            except Exception as e:
                print(f"[Dispatcher] strategy error: {e}")
        self._bridge.event_log_entry.emit(log_msg)


# ---------------------------------------------------------------------------
# Connection status monitor (runs in Qt main thread via timer callbacks)
# ---------------------------------------------------------------------------

class ConnectionMonitor:
    def __init__(self, listener: UDPListener, bridge: SignalBridge) -> None:
        self._listener = listener
        self._bridge = bridge
        self._was_connected = False

    def tick(self) -> None:
        connected = self._listener.connected
        hz = self._listener.packet_rate
        if connected != self._was_connected:
            self._was_connected = connected
        self._bridge.connection_changed.emit(connected, hz)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    dump_packets = "--dump-packets" in sys.argv
    explicit_config = None
    if "--config" in sys.argv:
        idx = sys.argv.index("--config")
        if idx + 1 < len(sys.argv):
            explicit_config = sys.argv[idx + 1]
    # Precedence: --config → NGR_CONFIG_PATH env → default config.json.
    config_path = resolve_config_path(explicit_config)

    config = load_config(config_path)

    event_queue: queue.PriorityQueue = queue.PriorityQueue()
    ui_queue:    queue.Queue         = queue.Queue(maxsize=5)

    thresholds = TyreThresholds.from_config(config["tyre_thresholds"])
    fc = config.get("fuel", {})
    tracker = RaceStateTracker(
        event_queue,
        thresholds,
        pit_threshold_liters=fc.get("pit_threshold_liters", 0.5),
        safety_margin_laps=fc.get("safety_margin_laps", 1.0),
    )

    logger    = LapDataLogger()
    announcer = VoiceAnnouncer(config.get("voice", {}))

    app    = QApplication(sys.argv)
    app.setFont(QFont("Segoe UI", 11))
    bridge = SignalBridge()

    recorder = LapTelemetryRecorder()
    db = SessionDB("data/gt7_sessions.db")

    strategy_engine = RaceStrategyEngine(tracker, announcer, config, bridge, db=db)
    # Saved stops are restored into the Strategy Builder UI only (dashboard __init__).
    # Do NOT call set_plan() here — the Live Race Engineer must remain inactive until
    # the user explicitly activates a plan during a session.
    _car_id_ref_early: list[int] = [0]  # shared ref updated in on_packet; used by advisor+dispatcher
    driving_advisor = DrivingAdvisor(recorder, tracker, config, db, _car_id_ref_early,
                                     session_id_getter=lambda: dispatcher._session_id if dispatcher is not None else 0)

    # Load car ID → name map for auto-detect (built by gt7_updater.py)
    _car_id_map: dict[str, str] = {}
    try:
        _car_id_map = json.loads(Path("data/car_id_map.json").read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    _last_car_id: list[int] = [-1]  # tracks last seen car_id to detect changes

    query_listener = QueryListener(
        tracker, announcer, config, strategy_engine, driving_advisor, bridge=bridge
    )

    # Route all print() output to the Debug tab as well as the console.
    sys.stdout = _DebugWriter(sys.stdout, bridge)

    ah         = AnnouncerEventHandler(announcer)

    # Packet processing callback (called from UDP thread)
    listener_ref: list[UDPListener] = []  # filled after listener created
    _dump_count = [0]   # how many raw packets have been logged
    _shift_above = [False]          # shift-beep hysteresis: re-arms when RPM drops below threshold
    _shift_muted_until = [0.0]      # suppress shift beeps after race finish (set by dispatcher)
    _shift_last_gear = [0]          # last observed gear; used to detect downshifts
    _is_racing = [False]            # True between RACE_STARTED and RACE_FINISHED (selects race vs qual RPM)
    # Snapshot refs written by the UI under _state_lock (see REF INJECTION CONTRACT below).
    # Frontend-builder writes [0] via window._live_mode_ref and window._practice_is_qual_ref.
    _live_mode_snap = ["Qualifying"]    # current session mode string; default Qualifying until race starts
    _practice_is_qual = [False]         # True when Practice tab is set to "qual simulation"
    _shift_downshift_muted_until = [0.0]  # monotonic: suppress beep after a downshift for 0.3 s
    _car_id_ref = _car_id_ref_early  # same list shared with driving_advisor

    # Real-time driving alert state — each is a single-element list for closure mutation
    _in_oversteer      = [False]    # hysteresis: currently inside a snap oversteer event
    _oversteer_started = [0.0]      # monotonic time when sustained oversteer began
    _oversteer_alert_until = [0.0]  # monotonic: don't alert before this time (cooldown)

    dispatcher = EventDispatcher(
        event_queue, ah, logger, bridge,
        _shift_muted_until, strategy_engine, recorder,
        db=db, config=config, car_id_ref=_car_id_ref,
        is_racing_ref=_is_racing, tracker=tracker,
    )

    _cal_pkt_counter = [0]

    def on_packet(data: bytes) -> None:
        if dump_packets and _dump_count[0] < 10:
            _dump_count[0] += 1
            try:
                with open("packet_dump.txt", "a") as f:
                    hex_str = " ".join(f"{b:02X}" for b in data[:64])
                    f.write(f"pkt#{_dump_count[0]} len={len(data)} first64: {hex_str}\n")
            except Exception:
                pass

        packet = parse_packet(data)
        if packet is None:
            if listener_ref:
                listener_ref[0].increment_errors()
            return
        tracker.update(packet)
        recorder.record_frame(packet, tracker.laps_recorded)
        if _cal_pkt_counter[0] % 6 == 0:
            bridge.calibration_packet.emit(packet)
        _cal_pkt_counter[0] = (_cal_pkt_counter[0] + 1) % 1000000
        if packet.car_id != 0:
            _car_id_ref[0] = packet.car_id
            if packet.car_id != _last_car_id[0]:
                _last_car_id[0] = packet.car_id
                car_name = _car_id_map.get(str(packet.car_id), "")
                bridge.car_detected.emit(packet.car_id, car_name)
                if car_name:
                    print(f"[CarDetect] car_id={packet.car_id} → {car_name}")
                else:
                    print(f"[CarDetect] unknown car_id={packet.car_id} — not in car_id_map.json")

        # Shift-beep: check RPM crossing on every packet (60 Hz), independent of
        # the event system.  Re-arms when RPM drops below 95 % of threshold so a
        # single gear-change produces exactly one beep.
        sb = config.get("shift_beep", {})
        with _state_lock:
            _shift_muted_snap            = _shift_muted_until[0]
            _is_racing_snap              = _is_racing[0]
            _live_mode_snap_val          = _live_mode_snap[0]
            _practice_is_qual_snap       = _practice_is_qual[0]
            _downshift_muted_snap        = _shift_downshift_muted_until[0]
        _now_wall = time.time()
        thresh_key, thresh = resolve_threshold(
            _live_mode_snap_val, _is_racing_snap, _practice_is_qual_snap, sb
        )
        cur_gear = packet.current_gear
        beep, new_shift_above, new_downshift_muted = should_shift_beep(
            prev_gear=_shift_last_gear[0],
            cur_gear=cur_gear,
            rpm=float(packet.engine_rpm),
            threshold=thresh,
            shift_above=_shift_above[0],
            enabled=bool(sb.get("enabled")),
            muted_until=_shift_muted_snap,
            downshift_muted_until=_downshift_muted_snap,
            now=_now_wall,
        )
        # Only sound the beep when the car is actually being driven — not in the
        # garage, menus, replays, or while paused/loading (see driving_gate).
        driving_now = driving_gate(
            car_on_track=packet.car_on_track,
            paused=packet.paused,
            loading=packet.loading,
            in_gear=packet.in_gear,
            speed_kmh=packet.speed_kmh,
        )
        if beep and driving_now:
            print(f"[ShiftBeep] fired — engine {packet.engine_rpm:.0f} >= thresh {thresh:.0f} "
                  f"({thresh_key}) gear {cur_gear}")
            # Play directly via winsound (WASAPI shared mode — always warm, no queue delay).
            if not announcer.play_beep_direct():
                print("[ShiftBeep] play_beep_direct failed — check rpm.wav exists and winsound is available")
        _shift_above[0] = new_shift_above
        with _state_lock:
            _shift_downshift_muted_until[0] = new_downshift_muted
        _shift_last_gear[0] = cur_gear

        # ── Real-time oversteer alert ────────────────────────────────────────
        # Wheelspin and lock-up detection data is used for per-lap coaching on
        # the Live tab but no longer fires real-time voice alerts — the events
        # are logged by the recorder for post-lap driving advice instead.
        if packet.car_on_track and packet.speed_kmh > 20:
            _now = time.monotonic()
            _spd = packet.speed_ms          # car speed in m/s

            _rear_avg_ms = (
                abs(packet.wheel_rps_rl) * packet.tyre_radius_rl
                + abs(packet.wheel_rps_rr) * packet.tyre_radius_rr
            ) * math.pi   # × 2π shared, then ÷ 2 wheels = × π

            # Oversteer: yaw rate > 1.8 rad/s (~103 °/s) AND rear slip > 1.15× car
            # speed simultaneously — filters out normal high-G cornering yaw which
            # routinely exceeds 0.8 rad/s in GT7 race cars.
            _yaw = abs(packet.angvel_z)
            _rear_slip = _rear_avg_ms > _spd * OVERSTEER_REAR_SLIP_RATIO and _spd > 5.0
            if _yaw > OVERSTEER_YAW_THRESHOLD_RAD_S and _rear_slip:
                if not _in_oversteer[0]:
                    _oversteer_started[0] = _now
                    _in_oversteer[0] = True
                sustained = _now - _oversteer_started[0]
                if sustained >= OVERSTEER_SUSTAINED_SEC and _now > _oversteer_alert_until[0]:
                    if packet.throttle > 0.5:
                        _os_msg = "Throttle oversteer — smooth the exit."
                    else:
                        _os_msg = "Snap oversteer — ease the entry speed."
                    announcer.announce(
                        _os_msg, Priority.HIGH, "rt_oversteer", 0.0, interrupt=False,
                    )
                    _oversteer_alert_until[0] = _now + OVERSTEER_COOLDOWN_SEC
            else:
                _in_oversteer[0] = False

        try:
            ui_queue.put_nowait(packet)
        except queue.Full:
            pass

    conn = config.get("connection", {})
    listener = UDPListener(
        host=conn.get("host", "127.0.0.1"),
        port=conn.get("port", 33741),
        callback=on_packet,
    )
    listener_ref.append(listener)

    # StateTracker race config is NOT restored at startup.
    # It is applied only when the user explicitly activates an event via Event Planner.
    # This prevents residual timed-race / lap-race config from a previous session
    # leaking into a fresh app startup.

    window = MainWindow(
        config=config,
        logger=logger,
        announcer=announcer,
        bridge=bridge,
        ui_queue=ui_queue,
        config_path=config_path,
        tracker=tracker,
        query_listener=query_listener,
        strategy_engine=strategy_engine,
        driving_advisor=driving_advisor,
        recorder=recorder,
        db=db,
        dispatcher=dispatcher,
        udp_listener=listener,
    )

    # REF INJECTION CONTRACT — post-construction attribute injection for shift-beep mode refs.
    # The frontend (MainWindow / dashboard slots) MUST write [0] under _state_lock:
    #   window._live_mode_ref[0]       = "Race" | "Qualifying" | "Practice"  (str)
    #   window._practice_is_qual_ref[0] = True | False                       (bool)
    # These are shared single-element lists (closures captured in on_packet).
    # Import _state_lock from main (or use getattr(window, '_state_lock_ref')) to guard writes.
    window._live_mode_ref       = _live_mode_snap        # list[str]  — on_packet reads [0]
    window._practice_is_qual_ref = _practice_is_qual     # list[bool] — on_packet reads [0]

    # Sync the refs with persisted/restored state NOW (before the listener starts).
    # Without this, the snapshots keep their module defaults until the user first
    # touches the Live-mode combo / Setup-type selector, so early packets would use
    # the wrong shift-RPM threshold (e.g. qual_rpm while the saved mode is Race).
    with _state_lock:
        _live_mode_snap[0] = config.get("live", {}).get("mode", "Race")
        _stype = ""
        if hasattr(window, "_setup_type") and window._setup_type is not None:
            try:
                _stype = window._setup_type.currentText()
            except Exception:
                _stype = ""
        _practice_is_qual[0] = "qual" in _stype.lower()

    conn_monitor = ConnectionMonitor(listener, bridge)

    def _periodic_tick() -> None:
        conn_monitor.tick()
        window.update_debug_stats(
            rate=listener.packet_rate,
            total=listener.total_received,
            errors=listener.parse_errors,
            hex_dump="",
        )
        # Keep tracker config in sync with any settings-tab changes
        tt = config.get("tyre_thresholds", {})
        tracker.update_thresholds(TyreThresholds.from_config(tt))
        fc2 = config.get("fuel", {})
        tracker.update_fuel_config(
            fc2.get("pit_threshold_liters", 0.5),
            fc2.get("safety_margin_laps", 1.0),
        )

    _tick_timer = QTimer()
    _tick_timer.timeout.connect(_periodic_tick)
    _tick_timer.start(200)  # every 200 ms — fast enough for status bar

    # Start background threads
    announcer.start()
    dispatcher.start()
    listener.start()
    query_listener.start()

    # UI rebuild (F1): optionally open the new NGR Pit Crew shell behind a flag
    # (env NGR_NEW_SHELL=1 or config.ui.new_shell). Defensive — any failure falls
    # back to the existing dashboard so startup is never blocked. The old window is
    # still constructed (the backend graph/timers reference it); it just stays hidden.
    _new_shell = None
    try:
        from ui.new_shell_launch import should_use_new_shell, launch_new_shell
        if should_use_new_shell(config):
            _new_shell = launch_new_shell(window=window, config=config, db=db)
    except Exception as _exc:
        print(f"[NewShell] launch failed, using classic dashboard: {_exc}")
        _new_shell = None

    if _new_shell is not None:
        _new_shell.show()
    else:
        window.show()
    exit_code = app.exec()

    # Graceful shutdown (query_listener first — may be mid-recording)
    query_listener.stop()
    listener.stop()
    dispatcher.stop()
    announcer.stop()
    query_listener.join(timeout=5)
    listener.join(timeout=3)
    dispatcher.join(timeout=3)
    announcer.join(timeout=3)
    db.close()

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
