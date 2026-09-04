"""Wiring: screens, the telemetry stream, and the store.

The screens know nothing about the database and the telemetry layer knows
nothing about Qt. This is the only place the three meet.

Threading. Packets arrive on the UDP thread at 60 Hz. Everything expensive —
compressing a lap's frames, writing to sqlite, touching a widget — happens on
the Qt thread, reached by emitting a signal from `TelemetryBridge`. The one
thing that must happen inline on the UDP thread is detaching the finished
lap's rows, because a frame recorded after the lap boundary but before the
swap would be filed against the wrong lap.
"""
from __future__ import annotations

import datetime
import sqlite3
import threading
from dataclasses import replace
from pathlib import Path
from time import monotonic as _monotonic

from PyQt6.QtCore import QObject, QTimer, pyqtSignal
from PyQt6.QtWidgets import QApplication, QWidget

from pitcrew import settings
from pitcrew.settings import FEED_PS5
from pitcrew.analysis.gameclock import clock, read_clock
from pitcrew.analysis.incidents import (
    find_incidents,
    read_rows,
    stored_or_read,
)
from pitcrew.analysis.resolve import circuit_key
from pitcrew.analysis.session import counted_laps
from pitcrew.analysis.runs import (
    FOR_QUALIFYING,
    REASON_FUEL_IMPLAUSIBLE,
    auto_out_laps,
    carry_compound,
    flag_opening_lap,
    fuel_implausible_laps,
)
from pitcrew.diagnostics import log
from pitcrew.engineer.ptt import (
    PushToTalk,
    best_listener,
    speech_from,
)
from pitcrew.engineer.shift_beep import ShiftBeep
from pitcrew.rig.effects import EffectDeriver
from pitcrew.rig.supervisor import RigSupervisor
from pitcrew.bench import Bench
from pitcrew.telemetry.hud_session import HudSession
from pitcrew.rig.wind_curve import WindCurve
from pitcrew.engineer import audio_devices, endpoint_meter
from pitcrew.engineer.voice import Voice
from pitcrew.export.build import (
    _rows_to_laps,
    build_event_export,
    event_lap_inputs,
)
from pitcrew.export.payload import APP_VERSION, ExportRefused, to_json
from pitcrew.prompts.build import KIND_LABELS, PromptRefused, build_prompt
from pitcrew.prompts.context import gather
from pitcrew.prompts.report import DriverReport
from pitcrew.prompts.templates import PROMPT_VERSION
from pitcrew.race import knowledge
from pitcrew.setup import doubt
from pitcrew.setup.parse import parse_reply
from pitcrew.setup.sheet import RangeRecord, SetupError, SetupSheet
from pitcrew.store import catalogs
from pitcrew.store.db import DEFAULT_SHEET_PURPOSE, Store
from pitcrew.store.identity import IDENTITY_OK
from pitcrew.race.calls import (STATUS, STATUS_EVERY_LAPS, STAY_OUT,
                               fuel_target_l, fuel_to_flag_l)
from pitcrew.race.coordinator import (PlanContext, RaceCoordinator,
                                      context_from_stored)
from pitcrew.race.expectations import PRACTICE
from pitcrew.race.hud_calibration import note_frame_red
from pitcrew.race.incident_watch import IncidentWatch
from pitcrew.race.straight import Straight
from pitcrew.race.colour import ColourCalls
from pitcrew.race.refuel import RefuelAdviser
from pitcrew.race.replan import (
    REPLAN_BUDGET_S,
    REPLAN_MAX_STOPS,
    REPLAN_MAX_WORK,
    REPLAN_NARROWED_MAX_STOPS,
    PlanRegister,
    assess,
    observed_fuel_per_lap,
    replan_work,
)
from pitcrew.race.qualifying import QualifyingCoach, reference_lap
from pitcrew.race.temps import measured_temp_window
from pitcrew.race.brief import Instruments, brief, lost_the_gauge
from pitcrew.race.quali_fuel import qualifying_fuel
from pitcrew.race.quali_fuel import refusal as quali_fuel_refusal
from pitcrew.strategy.certify import certify, certify_for_event
from pitcrew.strategy.evidence import build_inputs
from pitcrew.strategy.execution import stamp
from pitcrew.strategy.model import StrategyImpossible, recommend
from pitcrew.telemetry.selftest import LISTEN_S
from pitcrew.telemetry.listener import (
    GT7_STREAM_PORT,
    UDPListener,
    probe_port,
)
from pitcrew.telemetry.capture import CaptureWriter
from pitcrew.telemetry.recorder import FRAME_FIELDS, SAMPLE_HZ
from pitcrew.telemetry.packet import packet_format_for, parse_packet
from pitcrew.telemetry.recorder import LapRecorder
from pitcrew.telemetry.session_state import (
    EventKind,
    SessionKind,
    SessionState,
)
from pitcrew.ui.banner import Banner
from pitcrew.ui.practice_screen import LapRow

# SimHub's relay port. Kept as a module constant because `app.py` reads it,
# but it is only the fallback now - the live value comes from settings, so a
# SimHub reconfiguration is a thing the driver can follow without a rebuild.
DEFAULT_PORT = settings.DEFAULT_UDP_PORT
EXPORT_DIR = Path("exports")
# Raw session captures. A 30-minute run is ~40 MB, which is nothing set
# against re-driving it.
CAPTURE_DIR = Path("captures")
STALE_AFTER_S = 3.0
# How many lost packets a session may absorb before the rack says so. Two
# frames is a hiccup that costs a few centimetres of integrated lap distance;
# a whole second of stream is a corner window in the wrong place.
_LOST_PACKET_BUDGET = 30
# How much of its claimed duration a lap must actually carry in frames before
# it is believed. Generous, because a genuine lap can lose frames to a stream
# gap and still be worth keeping; a fragment inheriting the previous lap's
# time comes in at a few per cent.
_LAP_FRAGMENT_FRACTION = 0.5
# ...and how much recording there has to be before that ratio is allowed to
# disbelieve a lap at all.
#
# The two failures look nothing alike. A lap that recorded 21.8 seconds of a
# claimed 110 means the recorder was working and the lap was short - that is a
# phantom. A lap that recorded two frames means the RECORDER was not running,
# which says nothing whatever about whether he drove the lap, and calling that
# a phantom would throw away real laps whenever the stream started late.
#
# Ten seconds is comfortably above anything that counts as "no recording" and
# comfortably below both phantoms seen so far.
_LAP_MIN_EVIDENCE_S = 10.0
# One GT7 frame. The rig outputs are slew-limited in real time rather than in
# packets, so they need a duration; the stream's own 59.88 Hz is close enough
# to nominal that using the constant costs nothing a fan could express.
_FRAME_S = 1.0 / SAMPLE_HZ


def circuit_key_for(event) -> str | None:
    """Which circuit an event is at, in the store's own vocabulary.

    The same key `grip_observations` and `tyre_models` are already indexed on,
    so a sheet, a grip observation and a fitted tyre model all agree about
    where they were measured.

    None where the event has no track, which cannot happen through the Event
    screen but can through a hand-built row - and None must not then match a
    sheet, because "circuit unknown" is not "circuit is this one".
    """
    if not event:
        return None
    track = event["track"] if "track" in event.keys() else None
    if not track:
        return None
    layout = event["layout"] if "layout" in event.keys() else None
    return circuit_key(track, layout)


# How often a cluster must be seen on the board before it is a driver rather
# than a misread. See `telemetry.roster.Roster.drivers` for the two populations
# this separates: eight real drivers at 17-26 sightings in 30 frames, against a
# tail of forty-odd clusters seen once each.
PIT_WALL_MIN_SIGHTINGS = 20


class TelemetryBridge(QObject):
    """Turns the packet stream into Qt signals, on the right threads."""

    lap_completed = pyqtSignal(object, object)   # Lap, detached frame rows
    session_event = pyqtSignal(object)           # every event, for the race
    stream_seen = pyqtSignal(object)             # first packet's fixed facts
    parse_failed = pyqtSignal()
    ptt_answered = pyqtSignal(str, str)      # heard, said - off the hook thread
    # The practice debrief, built off the Qt thread because it decodes
    # every lap's telemetry - 2.5 s on the active event, 9.4 s on the
    # largest. Emitted queued so the speaking happens on the Qt thread.
    debriefed = pyqtSignal(object)           # analysis.debrief.Debrief
    # **A rival finished a pit stop**, composed on the HUD sampler's worker
    # thread and handled on the Qt one. It carries the `pit_wall.Seen` rather
    # than a formatted line, because what to say about it is a decision the
    # call layer makes with our own fuel in hand.
    rival_stopped = pyqtSignal(object)       # race.pit_wall.Seen
    rival_entered = pyqtSignal(object)       # race.pit_wall.Entered
    button_probed = pyqtSignal(str)          # probe note - off the hook thread
    # **The car stopped mid-lap.** Emitted on the telemetry thread and
    # handled on the Qt one, like every other cross-thread edge here:
    # what it costs is read off the coordinator, and the coordinator is
    # not thread-safe.
    incident_seen = pyqtSignal()
    # **The car is somewhere he can listen.** Emitted once per
    # straight, not once per frame: `Straight.update` stays true
    # for the whole straight so the caller does not have to catch
    # one particular frame, and the edge is what is worth a signal.
    straight_reached = pyqtSignal()
    # **A place gained or lost**, composed on the telemetry thread and spoken
    # on the Qt one. It carries the `Call` itself rather than a position,
    # because the coordinator holds the state that decides whether a moved
    # byte is news - and that state is not thread-safe, so the decision has
    # to be taken where the frames are and only the answer crosses over.
    position_changed = pyqtSignal(object)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.state = SessionState(SessionKind.PRACTICE)
        self.recorder = LapRecorder()
        self._announced = False
        # A raw capture sink, off unless the driver turned it on. It is a tee
        # on this callback rather than a second socket on purpose, and the
        # reason got stronger when the app started asking the console itself:
        # GT7 streams to whichever address last heartbeated it, so a capture
        # tool that opened its own socket would not merely latch a different
        # format, it would take the stream away from the app entirely.
        self.capture = None
        self.capture_formats: set[str] = set()
        self.capture_unparsed = 0
        # On the telemetry thread on purpose: a shift beep routed through
        # the Qt event loop arrives after the corner it was for.
        self.shift_beep = ShiftBeep(enabled=False)
        # The transducer. `effects` turns each packet into six intensities and
        # `haptics` renders them on PortAudio's own thread, so what happens
        # here is one array write - see `on_packet`. Both are None until the
        # driver switches it on, because this drives 150 W into his seat.
        self.effects = EffectDeriver()
        self.haptics = None
        # The wind simulator, the same shape: a curve that turns speed into
        # fan duty here, and a worker thread that does the talking. `set_output`
        # is one array write; the serial write happens elsewhere, because a
        # stalled USB port must not reach the packet handler.
        self.wind_curve = WindCurve()
        self.wind = None
        # **In the pit lane, tracked here rather than read off the race.**
        # The first version of the incident watch asked the coordinator, and
        # the coordinator lives on the controller - `self.race` does not exist
        # on this object, so every frame raised, the guard swallowed it and
        # the watch disabled itself silently on the first packet of every
        # race. The events that decide it arrive on this thread anyway.
        self._in_pit = False
        # **Whether the car is on a straight**, for anything that wants to
        # speak mid-lap. Lives here rather than in the race layer because it
        # is a fact about the frame, like the shift beep.
        self.straight = Straight()
        self._on_straight = False
        # The incident watch, armed with the race. None when no race is
        # armed - practice laps are judged afterwards, by the module
        # that can see a whole lap.
        self.incidents = None
        # The qualifying coach, armed by the controller when a practice
        # session opens with the qualifying intent. On the telemetry thread
        # like the shift beep, because the out-lap and delta calls are about
        # the frame they were computed from; its voice is a queue put.
        self.quali = None
        # The in-box refuel adviser, handed over when a race is armed. On the
        # telemetry thread for the same reason the beep is: the tank climbing
        # is a fact about the frame, and the release call is only worth
        # anything at the moment the tank actually reaches the target.
        self.refuel = None
        # The race coordinator, handed over when a race is armed, so GT7's own
        # lap counter can be read at 60 Hz. On the telemetry thread because a
        # crossing missed in the box has to be caught while the car is still
        # in the box - the fuel call is made there. See
        # `RaceCoordinator.note_packet`.
        self.lap_watch = None
        # The app's own race clock, handed over when a race is armed. It is
        # ticked here rather than from the race layer because a PAUSE is only
        # visible on the frames: `SessionState.update` returns early on one
        # and produces no events at all, so a clock fed by events would run
        # straight through a paused race and call the last lap early.
        self.race_clock = None
        # The last decoded packet, for the handful of Qt-thread answers that
        # need a live reading rather than a per-lap aggregate - the HUD
        # calibration report is the only one today. One attribute write per
        # frame; nothing reads it on this thread.
        self.last_packet = None
        self.racing = False
        self.beep_wanted = True
        # The settings the per-gear table lives in, and the car the stream is
        # currently showing. The table is per car and the car is not known
        # until a packet arrives, so the two are kept apart and joined in
        # `_apply_shift_points`.
        self._shift_points = None
        self._car_id = None
        # The car's canonical NAME, set from the active event. Kept for the
        # log lines that name which car is on the wire.
        self._car_name = None
        # The assist declared on the active event, held so the push happens
        # once per change rather than once per call. `_pushed_abs` separates
        # "no assist declared" from "never asked", which are different facts
        # and used to compare equal.
        self._abs_setting = None
        self._pushed_abs = False
        # Whether a REAL car id has been announced yet, as distinct from
        # `_announced`, which only says a packet arrived. The first packet
        # routinely carries id 0 - the car has not loaded - and that is not an
        # identity.
        self._car_announced = False
        # The largest short-shift drop in force at any point during the lap
        # being driven. None until a packet arrives - a lap nobody watched
        # makes no claim about how it was driven.
        self._lap_short_shift_rpm = None
        # **The fitted sheet's own table**, set when a session opens. A shift
        # point belongs to the gearbox, so it belongs to the sheet: change a
        # ratio or the final drive and the rpm worth shifting at moves with
        # it, which a table keyed by car alone cannot express.
        self._sheet_shift_rpm: dict[int, float] = {}

    def set_short_shift(self, drop_rpm: float | None) -> None:
        """Engage or release the beep's short-shift, at the rpm asked for.

        The drop is the engineer's, not the setting's: it comes from
        `short_shift_for`, which costs the saving against this car's measured
        litres-per-1000-rpm. Where no drop was named the beep returns to the
        sheet's own thresholds - the call that says "short-shift and lift into
        the slow corners" deliberately withheld a number, and inventing one to
        move the beep by would put back the fabrication it avoided.
        """
        if drop_rpm and drop_rpm > 0:
            self.shift_beep.short_shift_drop_rpm = float(drop_rpm)
            self.shift_beep.short_shifting = True
        else:
            self.shift_beep.short_shifting = False

    def set_abs(self, setting: str | None) -> None:
        """Which ABS the regulations put in the car, from the active event.

        The brake cue's scale is a property of the assist, not of the car: with
        ABS on it is measuring a regulator that holds the axle near its peak,
        and with ABS off there is no regulator and the same slip number means
        something else. The rig had no way to know which, and had been reading
        every car as though a regulator were fitted.
        """
        self.effects.set_abs(setting)

    def set_sheet_shift_rpm(self, table: dict | None) -> None:
        self._sheet_shift_rpm = {int(g): float(r)
                                 for g, r in (table or {}).items()}
        self._apply_shift_points()

    def _apply_shift_points(self) -> None:
        """Install the measured per-gear table for the car now on track.

        **The fitted sheet first**, then the legacy per-car setting for a car
        whose sheet has not been given one yet. A car with no measured table
        anywhere gets an EMPTY one, never a neighbour's and never a default:
        the whole value of a per-gear threshold is that it was measured on
        that gearbox, and a table that quietly fills itself would be
        indistinguishable at the wheel from one that was.
        """
        settings = self._shift_points
        if settings is None:
            return
        table = dict(self._sheet_shift_rpm)
        self.shift_beep.per_gear = table
        if self._car_id is None:
            return
        if table:
            log("beep").info(
                "car %s has shift points: %s", self._car_id,
                ", ".join(f"g{g} {rpm:.0f}" for g, rpm in sorted(table.items())))
        else:
            # **Silence, and it is said out loud.** There is no fallback any
            # more: a gearbox nobody has measured does not beep, because the
            # global rpm and GT7's own shift light both sounded exactly like a
            # measurement without being one. A silence nobody can account for
            # is its own defect, so the log says which car and what to do.
            log("beep").info(
                "car %s has no measured shift points on the fitted sheet, so "
                "the beep is silent. Run tools/shift_points.py against a "
                "session in this car and put the table on the setup sheet.",
                self._car_id)

    def apply_settings(self, settings) -> None:
        self.beep_wanted = settings.beep_enabled
        # Held rather than applied: which car this is arrives with the first
        # packet, so the table cannot be looked up until then - see
        # `_apply_shift_points`.
        self._shift_points = settings
        self.shift_beep.short_shift_drop_rpm = settings.beep_short_shift_drop
        self._apply_shift_points()
        # **On means "sound the measured thresholds", not "sound something".**
        # The beep no longer waits on a packet for a threshold, because the
        # threshold is on the sheet and the sheet is known before the car
        # turns a wheel.
        self.shift_beep.enabled = settings.beep_enabled

    def reset(self, *, race: bool = False) -> None:
        self.state = SessionState(
            SessionKind.RACE if race else SessionKind.PRACTICE)
        self.recorder.discard()
        self._announced = False
        # A new session asks the identity question again from scratch: the
        # car may well have changed between one run and the next.
        self._car_announced = False
        # A session boundary ends the lap in progress, so the shift mode
        # accumulated for it belongs to nothing.
        self._lap_short_shift_rpm = None
        # A coach armed for the previous session would speak about laps that
        # belong to nothing. Whoever opens the next session re-arms it.
        self.quali = None
        # A watch armed for the race just closed would judge the next race's
        # first stop against the last one's target.
        self.refuel = None
        # And a coordinator belonging to the race just closed would carry its
        # counter offset into the next one.
        self.lap_watch = None
        # And an incident watch would carry "the car has been under way" into
        # a session that opens with the car stationary in the box - which is
        # the exact shape it exists to refuse.
        self.incidents = None
        self._in_pit = False
        # And a clock belonging to the race just closed would keep accruing
        # paused time against a race that no longer exists.
        self.race_clock = None
        # Velocity and suspension carried across a session boundary are a
        # collision that never happened, at full scale, the instant he
        # rejoins somewhere else on the map.
        self.effects.reset()
        self.wind_curve.reset()
        # Which the wind curve needs, because his static-wind floor is set to
        # be suppressed in a race and not in practice.
        self.racing = race

    def on_packet(self, data: bytes) -> bool:
        """Called on the UDP thread for every datagram.

        Returns whether the datagram decoded. The listener counts that to
        decide whether asking for format `C` is getting anywhere, which it
        cannot tell from arrival alone - bytes landing on GT7's port are not
        the same claim as telemetry landing on GT7's port.
        """
        if self.capture is not None:
            # Before parsing, so a datagram this build cannot decode is still
            # on disk for one that can. A capture that only kept what today's
            # parser understood would be worth nothing the next time GT7
            # changes the packet.
            self.capture.write(data, _monotonic())
            fmt = packet_format_for(len(data))
            if fmt is None:
                self.capture_unparsed += 1
            else:
                self.capture_formats.add(fmt)

        packet = parse_packet(data)
        if packet is None:
            # Never degrade into a stream of zeros: a decode failure is
            # reported, because zeros survive all the way into a setup
            # recommendation.
            self.parse_failed.emit()
            return False

        if not self._announced:
            self._announced = True
            # GT7 sends the car's own shift-light thresholds, so the beep does
            # not need a configured rpm per car - the game already knows. The
            # driver can override it, and then the game must not win: a manual
            # threshold is usually a deliberate short-shift.
            # **GT7's own shift light is no longer consulted.** It is one
            # number for the whole gearbox and it is the game's opinion, not a
            # measurement of where this car actually stops pulling - and at
            # the wheel it was indistinguishable from a measured threshold.
            self.shift_beep.enabled = self.beep_wanted
            # Now the car is known, so the measured per-gear table can be
            # looked up. It overrides both the game's shift light and the
            # driver's single number, because it is the only one of the three
            # measured on this gearbox.
            self._car_id = packet.car_id
            self._car_announced = bool(packet.car_id)
            self._apply_shift_points()
            self.stream_seen.emit({
                "packet_format": packet.packet_format,
                "car_category": packet.car_category,
                "fuel_capacity_l": packet.fuel_capacity,
                "car_id": packet.car_id,
                # A per-car constant the extended packets carry and nothing
                # stored, so `understeer-mid` was dividing every car's
                # expected yaw by the RSR's 2.516 m.
                "wheelbase_m": packet.wheelbase_m,
            })
        elif not self._car_announced and packet.car_id:
            # **The first packet is often too early to know what the car is.**
            # `car_id` 0 is GT7's "not loaded yet" sentinel and it arrives with
            # `car_category` null and a 0 L tank - measured on 16 Aug 2026 at
            # 19:51:14, which is session 42's `started_at` to the second. That
            # session recorded no car class at all and none of its three laps
            # can be attributed. Announcing once and never again is what made
            # the miss permanent, so the facts are re-sent the moment the car
            # actually loads.
            self._car_announced = True
            self._car_id = packet.car_id
            self._apply_shift_points()
            self.stream_seen.emit({
                "packet_format": packet.packet_format,
                "car_category": packet.car_category,
                "fuel_capacity_l": packet.fuel_capacity,
                "car_id": packet.car_id,
                # A per-car constant the extended packets carry and nothing
                # stored, so `understeer-mid` was dividing every car's
                # expected yaw by the RSR's 2.516 m.
                "wheelbase_m": packet.wheelbase_m,
            })

        self.recorder.record_frame(packet)
        # Before anything that can raise: the race clock is arithmetic on
        # three floats and it must not be able to lose time because an
        # adviser downstream had a bad frame.
        self.last_packet = packet
        race_clock = self.race_clock
        if race_clock is not None:
            race_clock.note_frame(_monotonic(),
                                  paused=packet.paused or packet.loading)
        self.shift_beep.update(packet, _monotonic())
        # **How the lap being driven right now is being shifted.** Held per
        # frame rather than read at the line, because the switch can be thrown
        # mid-lap and what matters afterwards is that the lap was driven under
        # an instruction at all - a lap half short-shifted is not a clean
        # sample of the car either way.
        if self.shift_beep.short_shifting:
            self._lap_short_shift_rpm = max(
                self._lap_short_shift_rpm or 0.0,
                self.shift_beep.short_shift_drop_rpm)
        elif self._lap_short_shift_rpm is None:
            self._lap_short_shift_rpm = 0.0
        events = self.state.update(packet)
        for event in events:
            if event.kind is EventKind.LAP_COMPLETED:
                # Detach inline; compress and store on the Qt thread.
                rows = self.recorder.take_rows()
                event.data["lap"].short_shift_rpm = self._lap_short_shift_rpm
                self._lap_short_shift_rpm = None
                self.lap_completed.emit(event.data["lap"], rows)
            self.session_event.emit(event)

        # The qualifying coach, under the same doctrine as the outputs
        # below: an adviser must never cost the driver a recorded lap, so it
        # runs after everything that carries state, guarded, and is dropped
        # for the session on its first exception. Speaking is a queue put.
        # Read once into a local: the Qt thread clears `self.quali` on
        # disarm, and a second read between check and call would raise here
        # and be mis-logged as the coach's own fault.
        coach = self.quali
        if coach is not None:
            try:
                coach.update(packet, events, _monotonic())
            except Exception as exc:                       # noqa: BLE001
                log("quali").error(
                    "the qualifying coach raised on the telemetry thread and "
                    "has been stopped for this session: %s: %s",
                    type(exc).__name__, exc, exc_info=True)
                if self.quali is coach:
                    self.quali = None

        # **The incident watch**, under the same doctrine as the coach above.
        # One comparison a frame until the car slows, and it answers exactly
        # one question - has the car stopped mid-lap. What that is worth is
        # decided on the Qt thread, not here.
        watch = self.incidents
        if watch is not None:
            try:
                # **The crossing first, on this thread.** `new_lap` is what
                # holds it to one incident per lap, and doing it on the Qt
                # side would leave a window where the frames after a crossing
                # are still charged to the lap before it.
                for event in events:
                    if event.kind is EventKind.LAP_COMPLETED:
                        watch.new_lap()
                    elif event.kind is EventKind.PIT_ENTRY:
                        self._in_pit = True
                    elif event.kind is EventKind.PIT_EXIT:
                        self._in_pit = False
                if watch.update(packet, _monotonic(), in_pit=self._in_pit):
                    self.incident_seen.emit()
            except Exception as exc:                        # noqa: BLE001
                log("race").error(
                    "the incident watch raised on the telemetry thread and "
                    "has been stopped for this race: %s: %s",
                    type(exc).__name__, exc, exc_info=True)
                self.incidents = None

        # **The straight detector.** Two floats and a comparison; it answers
        # one question and emits only on the EDGE, so nothing downstream has
        # to de-duplicate six hundred frames of the same straight.
        try:
            was, self._on_straight = self._on_straight, self.straight.update(
                throttle_pct=packet.throttle * 100.0,
                speed_ms=packet.speed_ms,
                yaw_rate=packet.angvel_y,
                now=_monotonic())
            if self._on_straight and not was:
                self.straight_reached.emit()
        except Exception as exc:                            # noqa: BLE001
            log("race").error(
                "the straight detector raised on the telemetry thread: "
                "%s: %s", type(exc).__name__, exc, exc_info=True)
            self._on_straight = False

        # **The in-box refuel watch**, under the same doctrine as the coach
        # above: guarded, and dropped for the session on its first exception.
        # It does nothing at all until the tank starts climbing, which is once
        # or twice a race, and the target is only sized when the car is slow
        # enough to be in a pit box - so the 60 Hz cost is one comparison.
        # **Before the refuel watch, because the watch sizes the fill from the
        # race state and this is what corrects it.** GT7's own lap counter
        # sees a crossing missed in the box within a packet; the clock only
        # sees it when the lap finally completes, which at Road Atlanta on
        # 23 Aug 2026 was two minutes after the fill had been called and
        # thirteen litres too late. Same doctrine as its neighbours: guarded,
        # and dropped for the session on its first exception.
        # **Where on the road we are, integrated from speed.** GT7 has no
        # lap-distance channel, so a screen reading can only be tagged with a
        # road position if something is counting - and it cannot be recovered
        # afterwards, because the frame is gone and so is the packet. Guarded
        # and dropped for the session on its first exception, like everything
        # else on this thread.
        ruler = getattr(self, "_lap_ruler", None)
        if ruler is not None:
            try:
                ruler.note_packet(packet)
            except Exception as exc:                        # noqa: BLE001
                log("race").error(
                    "the lap ruler raised on the telemetry thread and has "
                    "been stopped for this race: %s: %s",
                    type(exc).__name__, exc, exc_info=True)
                self._lap_ruler = None

        lap_watch = self.lap_watch
        if lap_watch is not None:
            try:
                # **Returns a call now.** `note_packet` reads the position
                # byte as well as GT7's lap counter, and a place changed is
                # the one fact the engineer volunteers - see `calls.POSITION`.
                # Emitted rather than spoken: this is the telemetry thread.
                moved = lap_watch.note_packet(packet)
                if moved is not None:
                    self.position_changed.emit(moved)
            except Exception as exc:                        # noqa: BLE001
                log("race").error(
                    "the lap-counter watch raised on the telemetry thread and "
                    "has been stopped for this race: %s: %s",
                    type(exc).__name__, exc, exc_info=True)
                self.lap_watch = None

        refuel = self.refuel
        if refuel is not None:
            try:
                refuel.note_frame(packet.fuel_level, packet.speed_kmh)
            except Exception as exc:                        # noqa: BLE001
                log("race").error(
                    "the refuel watch raised on the telemetry thread and has "
                    "been stopped for this race: %s: %s",
                    type(exc).__name__, exc, exc_info=True)
                self.refuel = None

        # **Last, and unable to hurt anything above it.** This is an output,
        # and CLAUDE.md is clear that the app observes and advises - so a
        # transducer must never be able to cost the driver a recorded session.
        # It is appended after every stage that carries state because lap
        # distance is INTEGRATED: a consumer that raised here, or that ran
        # before the recorder, would move every corner window at this circuit.
        #
        # It also does no work worth speaking of. `update` is arithmetic on
        # six numbers and `set_intensities` is one array write; the rendering
        # happens on PortAudio's thread. Nothing here waits on a sound card,
        # which is what the shift beep used to do to this loop.
        if self.haptics is not None:
            try:
                self.haptics.set_intensities(self.effects.update(packet))
            except Exception as exc:                        # noqa: BLE001
                log("haptics").error(
                    "the transducer path raised on the telemetry thread and "
                    "has been stopped for this session: %s: %s",
                    type(exc).__name__, exc, exc_info=True)
                self.haptics = None
        if self.wind is not None:
            try:
                # The car's own state goes with the duty, so the frame log
                # aligns to a lap without the one-second anchor that made the
                # last attempt at this unresolvable.
                self.wind.set_output(
                    self.wind_curve.update(packet, _FRAME_S,
                                           racing=self.racing),
                    context={"speed_kmh": packet.speed_kmh,
                             "on_track": packet.car_on_track,
                             "paused": packet.paused})
            except Exception as exc:                        # noqa: BLE001
                log("wind").error(
                    "the wind path raised on the telemetry thread and has "
                    "been stopped for this session: %s: %s",
                    type(exc).__name__, exc, exc_info=True)
                self.wind = None
        return True


class PitCrewController(QObject):
    """Owns the store and the live session, and drives the screens."""

    # What each screen has to show for itself, for the nav rail. Emitted
    # rather than polled so the rail cannot drift from the store.
    nav_state_changed = pyqtSignal(dict)

    def __init__(self, store: Store, event_screen, practice_screen,
                 strategy_screen=None, race_screen=None, *,
                 car_screen=None, engineer_screen=None, settings_screen=None,
                 port: int | None = None, voice=None, warm=None,
                 parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.store = store
        self.event_screen = event_screen
        self.practice = practice_screen
        self.strategy = strategy_screen
        self.race_screen = race_screen
        self.car_screen = car_screen
        self.engineer = engineer_screen
        self.settings_screen = settings_screen
        # An exclusion reason the driver gave mid-lap, waiting for
        # that lap to land. See `_note_driver_report`.
        self._exclude_next_lap: str | None = None
        self.prompt_issue_id: int | None = None
        self.settings = settings.load(store)
        # The streams are opened deep inside two engines that must not know
        # what a settings object is, so the choice is pushed down instead.
        self._apply_audio_devices(self.settings)
        # How the test buttons find out whether the sound card really played
        # what the app sent it. Injectable because the real one reads a
        # Windows peak meter and answers about the machine it is running on:
        # a test that stubs the tone is asking a different question, and a
        # test on a build agent with no audio hardware is asking none at all.
        self._confirm_audio = endpoint_meter.confirm_reached_endpoint
        # The screen-filling notice, anchored to whichever screen the practice
        # page is on. None where there is no Qt widget to anchor to, which is
        # every controller test and every capture replay - the recording path
        # has to stay drivable headless.
        self._banner = (Banner(practice_screen)
                        if isinstance(practice_screen, QWidget) else None)
        # An explicit port wins - the tests bind their own - but otherwise the
        # setting is the source of truth, not a constant in this file.
        self._port_override = port
        self.port = port if port is not None else self.settings.udp_port
        self.voice = voice if voice is not None else Voice()
        self.race: RaceCoordinator | None = None
        self.race_run_id: int | None = None
        self._race_inputs = None
        self._race_burns: list[float] = []
        # What the driver was last told, and the rule that decides whether
        # the latest optimum is worth another word. This was an `OfferDesk`
        # that held one question open for two laps and let it lapse; the
        # driver's instruction was that an offer should not expire, because
        # the engineer reassesses every lap anyway. What remains is the
        # opposite guard - recalculating every lap must not become announcing
        # every lap. See `race/replan.PlanRegister`.
        self._replans = PlanRegister()
        # How wide the per-lap re-plan is allowed to search, narrowed when it
        # overruns its budget. See `replan.REPLAN_BUDGET_S`: 1.4 ms today,
        # 6.35 s on a shape that is one compound profile away.
        self._replan_max_stops = REPLAN_MAX_STOPS
        self._replan_over_budget = 0
        # The quiet-lap radio, armed with the race. None outside one.
        self._colour: ColourCalls | None = None
        # Whether the engineer talks during the race in progress. True outside
        # a race so nothing that speaks for another reason is silenced by it.
        self._engineer_speaks = True
        # Build the recogniser first, then ask *it* what it is. The gate used to
        # be chosen from the configured backend, but `best_recogniser_for` falls
        # back across that very boundary: with the shipped default of SAPI, and
        # SAPI failing to come up on this machine, the app ran Moonshine free
        # dictation with `matcher=None` - and `gate.judge` short-circuits when
        # there is no distance, so the whole five-stage gate was skipped on the
        # one path that needs it. Only free dictation needs it; SAPI's closed
        # grammar is exact by construction.
        # `warm` is the launch's background load, joined here. It is None
        # everywhere else - tests, replay, the bench - and `speech_from` then
        # builds exactly what this line used to build inline, which is why
        # there is no second code path to keep in step.
        recogniser, matcher = speech_from(warm, self.settings.speech_backend)
        self.ptt = PushToTalk(
            snapshot=self._ptt_snapshot,
            speak=self.voice.say,
            recogniser=recogniser,
            listener=best_listener(self.settings.ptt_key),
            on_answer=self._on_ptt_answer,
            matcher=matcher,
            sensitivity=self.settings.speech_sensitivity,
            toggle=self.settings.ptt_toggle)
        self._plans: list = []
        self._inputs = None
        self._plans_event_id: int | None = None
        # What the open session is, so handlers that write "to the open
        # session" can tell a practice run from a race.
        self.session_kind: str | None = None

        self.bridge = TelemetryBridge(self)
        # **The rig's lifecycle and its health, out of this file.** 597 lines
        # of it lived here; what is left are six lines of delegation, and this
        # class can no longer reach the watchdog, the endpoint note or the
        # recovery ladder. `active_event` goes in as a callable rather than a
        # value because it changes underneath - see `RigSupervisor`.
        self.rig = RigSupervisor(
            bridge=self.bridge, settings=lambda: self.settings,
            voice=self.voice,
            settings_screen=lambda: self.settings_screen,
            event=self.active_event)
        # **The wear gauge and the recording**, likewise out of this file. It
        # hands back four values - the latest reading, its lap, a blind note,
        # and whether a request was taken - and those used to be four loose
        # attributes here, written on a worker thread and read from three
        # different places. See `telemetry/hud_session.py`.
        self.hud = HudSession(settings=lambda: self.settings, store=self.store)
        # **And the bench**: the Settings screen's hardware checks and the
        # ten-tick health line. `listener` and `settings` go in as readers
        # because the controller rebinds both - a bench holding the object it
        # was built with would report on the port the app opened with rather
        # than the one it is listening on.
        self.bench = Bench(
            settings=lambda: self.settings,
            settings_screen=lambda: self.settings_screen, bridge=self.bridge,
            voice=self.voice, rig=self.rig,
            listener=lambda: self.listener, practice=self.practice,
            confirm_audio=lambda: self._confirm_audio,
            parse_errors=lambda: self._parse_errors)
        self.listener: UDPListener | None = None
        self.session_id: int | None = None
        self._parse_errors = 0
        self._store_errors = 0

        # Set once, so an attach that runs twice does not connect twice.
        self._engineer_wired = False
        self._settings_wired = False

        self.bridge.lap_completed.connect(self._on_lap_completed)
        self.bridge.debriefed.connect(self._on_debriefed)
        self.bridge.stream_seen.connect(self._on_stream_seen)
        self.bridge.parse_failed.connect(self._on_parse_failed)
        self.bridge.ptt_answered.connect(self._show_ptt_answer)
        self.bridge.button_probed.connect(self._note_button_probe)
        self.bridge.session_event.connect(self._on_race_event)
        self.bridge.incident_seen.connect(self._on_incident_seen)
        self.bridge.straight_reached.connect(self._on_straight_reached)
        self.bridge.position_changed.connect(self._on_position_changed)
        # **The connection this signal never had.** `_on_rival_stop` emitted
        # into it from the worker thread and nothing was listening, so every
        # rival call in `race/rival_calls.py` was unreachable - written,
        # documented, tested, and silent for the whole of every race.
        self.bridge.rival_stopped.connect(self._rival_stop_filed)
        self.bridge.rival_entered.connect(self._rival_entry_seen)

        self.event_screen.saved.connect(self._on_event_saved)
        self.event_screen.discarded.connect(self.discard_event_edits)
        self.event_screen.switched.connect(self.switch_event)
        self.practice.recording_toggled.connect(self._on_recording_toggled)
        self.practice.lap_changed.connect(self._on_lap_changed)
        self.practice.export_requested.connect(self._on_export)
        self.practice.practice_mode_changed.connect(self._on_practice_mode)
        self.practice.practice_intent_changed.connect(
            self._on_practice_intent)
        self.practice.coach_speaks_changed.connect(self._on_coach_speaks)
        self.practice.debrief_requested.connect(self.read_the_stint)
        if self.strategy is not None:
            self.strategy.build_requested.connect(self.build_strategy)
            self.strategy.qualifying_requested.connect(
                self.plan_qualifying)
            self.strategy.approve_requested.connect(self.approve_strategy)
            self.strategy.approve_loaded_requested.connect(
                self.approve_stored_strategy)
        if self.race_screen is not None:
            self.race_screen.start_requested.connect(self.start_race)
            self.race_screen.replan_accepted.connect(
                lambda: self._resolve_replan(accepted=True))
            self.race_screen.replan_declined.connect(
                lambda: self._resolve_replan(accepted=False))
            self.race_screen.stop_requested.connect(self.stop_race)
        if self.car_screen is not None:
            self.car_screen.car_changed.connect(self.load_car)
            self.car_screen.saved.connect(self.save_ranges)
        if self.engineer is not None:
            self.attach_engineer_screen(self.engineer)
        if self.settings_screen is not None:
            self.attach_settings_screen(self.settings_screen)

        # Ranges measured before the app had anywhere to keep them. Seeded
        # once, and never allowed to overwrite something read off a car.
        self.store.seed_range_records(catalogs.range_seed_records())
        self.bridge.apply_settings(self.settings)
        self.voice.tune(**self.settings.voice_tuning())

        self._health = QTimer(self)
        self._health.setInterval(1000)
        self._health.timeout.connect(self._report_health)

        self.refresh_catalogs()
        # **Scheduled, not called.** See `_first_paint_work`: this is ~130 ms
        # of widget filling that the window does not need in order to appear.
        self._first_paint_done = False
        QTimer.singleShot(0, self._first_paint_work)

    def _first_paint_work(self) -> None:
        """Fill the screens, once, after the window has had a chance to paint.

        A named method rather than a lambda, and one callback rather than two,
        because **the order of these two calls is load-bearing and Qt will not
        tell anyone who breaks it.** Loading the event writes the practice
        status line; closing orphaned sessions writes the one message saying
        the app died last time. Run the other way round - or split across two
        `singleShot`s, which is the same thing with extra steps - and that
        message is overwritten before anyone sees it, silently.

        Idempotent, and `shutdown` calls it if the event loop never did. The
        orphan sweep used to be unconditional in `__init__`, so deferring it
        would otherwise turn the app's only unclean-shutdown detector into a
        best-effort one: `main()` can raise between here and `app.exec()`, and
        then this would never run at all.
        """
        if self._first_paint_done:
            return
        self._first_paint_done = True
        self.load_active_event()
        self._close_orphaned_sessions()

    # --------------------------------------------------------------- catalog

    # ------------------------------------------------------- late screens
    #
    # Two screens are built when the driver first navigates to them rather
    # than at launch - see `app.NavRail`'s builder. That saves ~300 ms off a
    # startup nobody was enjoying, and it costs this: the wiring that used to
    # be a block inside `__init__` has to be callable twice, from either
    # order, without doubling anything.
    #
    # **Both are idempotent**, because a doubled `connect` is permanent for
    # the life of the process, fires every handler twice, and is invisible -
    # no exception, no log, nothing to see until a Save writes two records.

    def _tell_settings_about_the_session(self) -> None:
        """Let the Settings screen know whether a session is running.

        It re-enumerates the sound devices when it is first opened, and that
        tears PortAudio down and rebuilds it. Doing so mid-race would stall
        the window and drop the transducer, so the screen skips the refresh
        and says it did. None outside a session, so nothing is blocked when
        it does not need to be.
        """
        screen = self.settings_screen
        if screen is not None and hasattr(screen, "set_session_open"):
            screen.set_session_open(self.session_kind is not None)

    def attach_engineer_screen(self, screen) -> None:
        """Wire the Engineer screen, whenever it turns up."""
        if self.engineer is screen and self._engineer_wired:
            return
        self.engineer = screen
        if screen is None:
            return
        if not self._engineer_wired:
            screen.generate_requested.connect(self.generate_prompt)
            screen.copy_requested.connect(self.copy_prompt)
            screen.reply_saved.connect(self.file_prompt_reply)
            self._engineer_wired = True
        # What `load_active_event` would have pushed into it had it existed.
        self.refresh_engineer()

    def attach_settings_screen(self, screen) -> None:
        """Wire the Settings screen, whenever it turns up.

        `rig` and `bench` reach this screen through a reader that resolves
        `self.settings_screen` on every read, so nothing has to be handed to
        them here. That is deliberate: assigning the screen into two other
        objects by hand is the shape of a reset with no caller, and the five
        buttons it would silently disable are the pre-race checks.
        """
        if self.settings_screen is screen and self._settings_wired:
            return
        self.settings_screen = screen
        if screen is None:
            return
        if not self._settings_wired:
            screen.saved.connect(self.save_settings)
            screen.test_beep_requested.connect(self.test_beep)
            screen.test_voice_requested.connect(self.test_voice)
            screen.test_haptics_requested.connect(self.test_haptics)
            screen.test_feed_requested.connect(self.test_feed)
            screen.test_gauge_requested.connect(self.test_gauge)
            screen.capture_toggled.connect(self.toggle_capture)
            screen.listen_toggled.connect(self.probe_button)
            self._settings_wired = True
        screen.load(self.settings)
        screen.show_capabilities(speech=self.voice.engine_name,
                                 hook=self.ptt.has_listener)
        # Built lazily, so it can arrive mid-session and would otherwise
        # think nothing was running.
        self._tell_settings_about_the_session()

    def refresh_catalogs(self) -> None:
        """Shipped names, plus anything added straight to the store.

        There is no UI for adding: a free-text field is where the typos came
        from. A missing track is fixed in the catalogue, not at the keyboard
        mid-session.
        """
        tracks = sorted(set(catalogs.track_bases())
                        | set(self.store.custom_catalog("track")))
        extra = self.store.custom_catalog("car")
        # Two shapes of the same catalogue. The event screen narrows by class
        # then maker and wants the nested form; the car screen's flat `Picker`
        # wants class alone. Building both here keeps the widgets ignorant of
        # each other rather than making one accept the other's shape.
        groups = list(catalogs.cars_by_category().items())
        nested = list(catalogs.cars_by_category_and_maker().items())
        if extra:
            groups.append(("Added", tuple(sorted(extra))))
            nested.append(("Added", {"Added": tuple(sorted(extra))}))
        self.event_screen.set_catalogs(tracks, nested)
        if self.car_screen is not None:
            self.car_screen.set_car_groups(groups)

    # ----------------------------------------------------------------- event

    def active_event(self) -> dict | None:
        event_id = self.store.active_event_id()
        event = self.store.get_event(event_id) if event_id else None
        # **The car's name, on the way past.** The bridge needs it to find a
        # per-gear shift table for a car whose packet id has never been seen -
        # which is every car until it has been driven with the app recording,
        # including the one being raced next. Setting it here rather than
        # hunting for an event-changed hook keeps the two in step: the bridge
        # can never be looking at a car the app is not.
        name = (event or {}).get("car_name") if event else None
        if getattr(self.bridge, "_car_name", None) != name:
            self.bridge._car_name = name
            self.bridge._apply_shift_points()
        # **And the assist, on the same hook and for the same reason.** ABS is
        # a regulation on the event - Supercars declares Off, every other
        # series he runs declares Weak - so it changes when the event does,
        # not when a session opens. Pushing it here keeps the brake cue's
        # scale and the rulebook in step.
        assist = (event or {}).get("abs_setting") if event else None
        # **`_pushed_abs` and not `_abs_setting is None`.** The bridge starts
        # with no assist, so comparing values meant that an event declaring
        # nothing compared equal to the initial state, the push never
        # happened, and the one log line that says "you are on a borrowed
        # scale" could only fire on a transition FROM a declared assist - the
        # rarest case, and never the one it was written for.
        if not self.bridge._pushed_abs or self.bridge._abs_setting != assist:
            self.bridge._pushed_abs = True
            self.bridge._abs_setting = assist
            self.bridge.set_abs(assist)
            if assist is None:
                log("rig").info(
                    "no ABS setting on the active event, so the brake cue is "
                    "borrowing the ABS-on scale - it will read LOW confidence "
                    "until the event declares one")
        return event

    def _refresh_race_options(self, event) -> None:
        """Say whether there is a plan for the Strategy choice to be about.

        Offering "Approved plan" with none approved is a control that cannot
        do what it says, on a screen whose subtitle would be saying the
        opposite two inches away.
        """
        if self.race_screen is None:
            return
        approved = (self.store.get_approved_strategy(event["id"])
                    if event else None)
        self.race_screen.set_plan_available(approved is not None)
        # **And what that plan actually is.** The picker only ever said
        # whether one existed; the stops, the box laps and the compounds were
        # nowhere on the screen the race is started from, so the only way to
        # check the engineer was holding tonight's race was to run it.
        self.race_screen.set_plan(approved)

    def load_active_event(self) -> None:
        event = self.active_event()
        # Plans describe one event's evidence. Re-saving the event they were
        # built for keeps them; moving to another event drops them.
        if self._plans and self._plans_event_id != (event["id"] if event else None):
            self._forget_plans()
        # The picker is refreshed either way: with no active event it is the
        # only route back to one that does exist.
        self.event_screen.set_events(self.store.list_events(),
                                     event["id"] if event else None)
        if event is None:
            self.practice.set_status(
                "No event yet. Create one on the Event screen first.",
                warn=True)
            # The Engineer's premise plate is the screen's whole argument -
            # the division between what the app knows and what only he does,
            # visible before anything is generated. It returned early here and
            # left the plate empty on exactly the run where the division has
            # never been explained.
            self.refresh_engineer()
            self._refresh_race_options(None)
            return

        # The race sheet, by purpose - not whichever row sorted first.
        # `list_setup_sheets` orders by `updated_at DESC, id DESC`, and a pasted
        # race+qualifying pair is written inside the same second, so the
        # qualifying sheet came back on top.  `EventScreen.load` then showed it
        # under the Race label and one Save rewrote it as the race sheet, which
        # left the car with two race sheets and no qualifying one.
        car = event["car_name"] or ""
        here = circuit_key_for(event)
        sheet = self.store.sheet_for(car, "race", here)
        if sheet is None:
            # Falling back across circuits is what put a Yas Marina sheet on
            # the Event screen for a Road Atlanta event.
            sheets = [x for x in self.store.list_setup_sheets(car)
                      if x.circuit_key == here]
            sheet = sheets[0] if sheets else None
        self.event_screen.load(event, sheet)
        self.practice.set_laps(self._rows_for_event(event["id"]))
        self.practice.set_status(self._idle_status(event))
        self._refresh_race_options(event)
        self.refresh_nav_state()
        if self.car_screen is not None and event["car_name"]:
            self.load_car(event["car_name"])
        self.refresh_engineer()

    def switch_event(self, event_id) -> None:
        """Make another saved event the one the whole app is working on.

        A read, not a write: nothing about the event being left is touched.
        Every screen behind this one keys off `active_event_id`, so moving it
        and reloading is the entire operation - the sessions, laps,
        strategies and race runs of both events stay exactly where they are,
        filed against their own event id.
        """
        if event_id is None:
            # Composing an event that does not exist yet. The previous one has
            # to stop being active: a practice session started from this state
            # would otherwise record laps against the event that is no longer
            # on the screen, which is the one mistake this feature exists to
            # prevent.
            self.store.set_state("active_event_id", None)
            self._forget_plans()
            self.event_screen.set_events(self.store.list_events(), None)
            self.event_screen.clear()
            self.practice.set_laps([])
            self.practice.set_status(
                "No event yet. Fill one in on the Event screen and save it.",
                warn=True)
            self.refresh_nav_state()
            self.refresh_engineer()
            self.event_screen.note(
                "New event. Nothing is stored until you save it.")
            return

        event = self.store.get_event(int(event_id))
        if event is None:
            self.event_screen.set_events(self.store.list_events(),
                                         self.store.active_event_id())
            self.event_screen.note(
                "That event is no longer in the store.", warn=True)
            return

        self.store.set_state("active_event_id", int(event_id))
        self.load_active_event()
        laps = len(self.store.list_event_laps(event["id"]))
        recorded = (f"{laps} practice lap{'' if laps == 1 else 's'} recorded."
                    if laps else "No practice laps recorded yet.")
        self.event_screen.note(f"Working on {event['name']}. {recorded}")

    def _idle_status(self, event: dict) -> str:
        circuit = event["track"] or "unknown"
        if event["layout"]:
            circuit += f" ({event['layout']})"
        return (f"{event['name']} — {circuit}. "
                "Start practice when you are ready to go out.")

    def _on_event_saved(self, data: dict) -> None:
        """Create or update the event, and the sheet fitted to it.

        Which event is being written is decided by the id the form was loaded
        with, never by the name on it. Matching on the name meant two things
        that both cost data: a rename created a second event and orphaned
        every session recorded under the old one, and typing an existing
        event's name onto a form filled in for a different round overwrote
        that event's regulations without saying so.
        """
        event_id = data.get("id")
        existing = self.store.get_event(int(event_id)) if event_id else None
        # The name still has to be unique - it is what the driver reads in the
        # picker, and the store enforces it anyway. Refusing here turns a
        # constraint violation into a sentence.
        clash = next((e for e in self.store.list_events()
                      if e["name"] == data["name"]
                      and (existing is None or e["id"] != existing["id"])), None)
        if clash:
            self.event_screen.note(
                f"Another event is already called {data['name']}. Give this "
                f"one a different name, or switch to that event to edit it.",
                warn=True)
            return
        fields = {
            "name": data["name"], "track": data["track"],
            "layout": data["layout"], "car_name": data["car_name"],
            "race_type": data["race_type"], "race_laps": data["race_laps"],
            "weather": data["weather"],
            "tyre_wear_mult": data["tyre_wear_mult"],
            "fuel_mult": data["fuel_mult"],
            "refuel_rate_lps": data["refuel_rate_lps"],
            "pit_loss_secs": data["pit_loss_secs"],
            "mandatory_stops": data["mandatory_stops"],
            "abs_setting": data["abs_setting"], "tcs": data["tcs"],
            "available_compounds": data["available_compounds"],
        }
        # Declared event facts the race-engineering prompts carry. Optional in
        # the payload so an older caller - or a test - still saves an event.
        for key in ("countersteer", "pp_cap", "start_type", "time_of_day",
                    "priority", "notes", "game_version", "extra_time_s",
                    "start_hour", "time_multiplier", "weather_rule",
                    "rain_possible"):
            if key in data:
                fields[key] = data[key]
        if existing:
            self.store.update_event(existing["id"], **fields)
            event_id = existing["id"]
            verb = "Updated"
        else:
            event_id = self.store.create_event(**fields)
            verb = "Created"
        event_id = int(event_id)

        message = f"{verb} {data['name']}."
        if (data["setup_values"] or data["sheet_name"]
                or data.get("build") or data.get("performance")):
            try:
                self._save_sheet(data)
                message += " Sheet saved."
            except SetupError as exc:
                self.event_screen.note(f"Event saved, but the sheet was "
                                       f"refused: {exc}", warn=True)
                self.store.set_state("active_event_id", event_id)
                self.load_active_event()
                return

        self.store.set_state("active_event_id", event_id)
        self.event_screen.note(message)
        self.load_active_event()

    def discard_event_edits(self) -> None:
        """Put the form back to what is actually stored.

        Unsaved edits are the only thing lost, and they are the only thing
        this can lose: the store is not touched. An event that was never
        saved has nothing to go back to, so the form is left alone and says
        so rather than silently blanking work in progress.
        """
        event = self.active_event()
        if event is None:
            self.event_screen.note(
                "Nothing saved yet, so there is nothing to go back to.",
                warn=True)
            return
        self.load_active_event()
        self.event_screen.note(f"Reloaded {event['name']} as stored. "
                               f"Unsaved edits are gone.")

    def _save_sheet(self, data: dict) -> int:
        """Save the sheet on the form, and the other half of a pasted pair.

        The prompts ask for a race sheet and a qualifying sheet in one reply,
        so one paste carries both and the form can only hold one at a time.
        Saving only what is on screen would mean asking for two and keeping
        one, which is worse than not asking.

        Returns the id of the sheet the form was showing - that is the one the
        event is fitted with, and the caller records it against the session.
        """
        gears = []
        for chunk in data.get("gear_text", "").replace(",", " ").split():
            try:
                gears.append(float(chunk))
            except ValueError:
                continue
        # **Positional, 1st gear first, same as the ratios beside it.** A
        # blank entry is a gear nobody measured and is skipped rather than
        # filled: the value of a per-gear threshold is that it was measured on
        # that gearbox, and a table that quietly completes itself is
        # indistinguishable at the wheel from one that did not.
        shift_rpm: dict[int, float] = {}
        for gear, chunk in enumerate(
                data.get("shift_rpm_text", "").replace(",", " ").split(), 1):
            try:
                rpm = float(chunk)
            except ValueError:
                continue
            if rpm > 0:
                shift_rpm[gear] = rpm

        purpose = data.get("sheet_purpose") or DEFAULT_SHEET_PURPOSE
        name = data["sheet_name"] or f"{data['name']} sheet"
        # **Stamped with the circuit it was built for.** A sheet is a property
        # of the car and the circuit, and until this was written the lookup
        # had no way to tell one from another - so a Road Atlanta session
        # bound itself to a Yas Marina sheet.
        here = circuit_key_for(data)
        sheet = SetupSheet(
            car_name=data["car_name"],
            sheet_name=name,
            values=dict(data["setup_values"]),
            gears=gears,
            shift_rpm=shift_rpm,
            performance=dict(data.get("performance") or {}),
            build=dict(data.get("build") or {}),
            purpose=purpose,
            circuit_key=here,
        )
        sheet_id = self.store.save_setup_sheet(sheet)

        for other_purpose, parsed in (data.get("other_sheets") or {}).items():
            # **The name is kept, and the purpose keeps them apart.**
            #
            # This used to rename the second sheet to "<name> (qualifying)"
            # because the store's key was `(car_name, sheet_name)` and two
            # sheets of one name could not coexist - the comment here called
            # the collision out and then worked around it. The workaround only
            # covered the half of the case where the reply gave no name of its
            # own; where it did, and the names matched, the second sheet still
            # overwrote the first and relabelled it. That is the defect the
            # driver reported. The key carries `purpose` now, so the two are
            # two rows and re-pasting the same reply updates both in place
            # instead of breeding a third.
            self.store.save_setup_sheet(SetupSheet(
                car_name=data["car_name"],
                sheet_name=parsed.sheet_name or name,
                values=dict(parsed.values),
                gears=list(parsed.gears),
                purpose=other_purpose,
                circuit_key=here,
            ))
        return sheet_id

    # ------------------------------------------------------------- nav state

    def nav_state(self) -> dict:
        """One line per screen for the rail: where the work actually stands.

        Every figure here is already in the store. The rail used to show eight
        equal peers with no completion state while the app knew perfectly well
        that there were eleven laps, no approved plan and an unverified range
        record - so the one place he looks first told him the least.
        """
        event = self.active_event()
        if event is None:
            return {"Event": "none yet"}

        state = {"Event": event["name"] or "unnamed"}

        car = event["car_name"]
        if car:
            record = self.store.get_range_record(car)
            state["Car"] = ("measured" if record and record.verified
                            else "unverified" if record else "no ranges")

        laps = len(self.store.list_event_laps(event["id"], "practice"))
        state["Practice"] = f"{laps} laps" if laps else "nothing recorded"

        approved = self.store.get_approved_strategy(event["id"])
        state["Strategy"] = (approved["label"] or "approved") if approved \
            else "no plan"

        race_laps = len(self.store.list_event_laps(event["id"], "race"))
        state["Race"] = f"{race_laps} laps" if race_laps else "not raced"

        issued = self.store.list_prompts(event["id"], limit=50)
        state["Engineer"] = (f"{len(issued)} prompts" if issued
                             else "not asked")
        return state

    def refresh_nav_state(self) -> None:
        self.nav_state_changed.emit(self.nav_state())

    # -------------------------------------------------------------- settings

    def _apply_audio_devices(self, values: settings.Settings) -> None:
        """Tell the audio layer which card he races on.

        Empty means the system default, which is what this always did - and
        what let the engineer speak into a headset that was not connected.
        """
        audio_devices.set_output_device(values.audio_output_device or None)
        audio_devices.set_input_device(values.audio_input_device or None)

    def save_settings(self, new: settings.Settings) -> None:
        """Apply the button and the beep, and remember them."""
        try:
            settings.save(self.store, new)
        except ValueError as exc:
            if self.settings_screen is not None:
                self.settings_screen.note(f"Refused: {exc}", warn=True)
            return

        # **The colour level is read when the race is built**, so a change
        # made during one would otherwise not arrive until the next race -
        # which is exactly when he is reaching for it.
        if self._colour is not None:
            self._colour.level = new.colour_calls
        rebind = new.ptt_key != self.settings.ptt_key
        # Everything that decides where the stream comes from. Port and
        # filter were the only two checked, so switching between SimHub and
        # the console mid-session - or correcting a mistyped console address,
        # which is exactly when someone is anxious about it - said "Saved."
        # and left the listener on the old feed for the rest of the session.
        feed_moved = (new.udp_port != self.settings.udp_port
                      or new.udp_source_ip != self.settings.udp_source_ip
                      or new.feed_source != self.settings.feed_source
                      or new.ps5_ip.strip() != self.settings.ps5_ip.strip())
        self.settings = new
        self._apply_audio_devices(new)
        if self._port_override is None:
            self.port = new.udp_port
        self.bridge.apply_settings(new)
        self.voice.tune(**new.voice_tuning())
        if rebind:
            # A key the hook is not watching is a button that does nothing, so
            # the listener is rebuilt rather than reconfigured.
            self.ptt.set_listener(best_listener(new.ptt_key))
        table = self.bridge.shift_beep.per_gear or {}
        log("settings").info(
            "ptt %s on %r (practice=%s) · beep %s, %s",
            "on" if new.ptt_enabled else "off", new.ptt_key,
            new.ptt_in_practice, "on" if new.beep_enabled else "off",
            (", ".join(f"g{g} {rpm:.0f}" for g, rpm in sorted(table.items()))
             if table else "no measured thresholds on the fitted sheet"))
        if self.settings_screen is not None:
            # A live listener is already bound to the old port. Rebinding it
            # under a running session would drop packets mid-lap, so it is
            # left alone and the change is announced instead.
            if feed_moved and self.listener is not None:
                now_on = (f"the console at {self.listener.heartbeat_to}"
                          if self.listener.heartbeat_to
                          else f"SimHub on {self.listener.port}")
                self.settings_screen.note(
                    f"Saved. The feed is still coming from {now_on} for this "
                    f"session - stop and restart it to move to "
                    f"{self._feed_description(new)}.", warn=True)
            else:
                self.settings_screen.note("Saved.")
            self.settings_screen.show_capabilities(
                speech=self.voice.engine_name, hook=self.ptt.has_listener)

    # ---------------------------------------------------------- raw capture

    # What M0 expects to be arriving. Not a filter — anything that turns up is
    # written — but a mismatch is said out loud, because a capture recorded in
    # the wrong format is only discovered when the analysis has nothing to
    # measure, which is after the race and after the driver has got out.
    CAPTURE_EXPECTED_FORMAT = "C"

    def start_capture(self, path=None, **note) -> Path | None:
        """Begin recording every datagram, raw, to disk.

        A pre-race action. There is nothing here to operate at speed, and
        nothing here that talks to the console: this is a tee on the callback
        the app already receives.
        """
        if self.bridge.capture is not None:
            return self.bridge.capture.path

        target = Path(path) if path else (
            CAPTURE_DIR / f"{datetime.datetime.now():%Y-%m-%d_%H%M%S}.pcap")
        writer = CaptureWriter(
            target, app_version=APP_VERSION,
            started=datetime.datetime.now().isoformat(timespec="seconds"),
            expected_format=self.CAPTURE_EXPECTED_FORMAT, **note)
        writer.__enter__()
        self.bridge.capture_formats = set()
        self.bridge.capture_unparsed = 0
        self.bridge.capture = writer
        log("capture").info("recording raw telemetry to %s", target)
        return target

    def stop_capture(self) -> dict | None:
        """Close the capture and say what actually landed in it."""
        writer = self.bridge.capture
        if writer is None:
            return None
        self.bridge.capture = None
        writer.__exit__(None, None, None)

        formats = sorted(self.bridge.capture_formats)
        unparsed = self.bridge.capture_unparsed
        # Fail loudly rather than silently mis-parsing later. A capture in the
        # wrong format still contains bytes, and an analysis over the wrong
        # bytes produces numbers rather than an error.
        wrong = [f for f in formats if f != self.CAPTURE_EXPECTED_FORMAT]
        problem = None
        if not writer.count:
            problem = ("Nothing was captured. The stream was not running - "
                       "this file is empty and the run needs repeating.")
        elif unparsed:
            problem = (f"{unparsed} datagrams were not a GT7 packet size at "
                       f"all. Something else is on the port.")
        elif wrong:
            problem = (f"Captured format {'/'.join(formats)}, expected "
                       f"{self.CAPTURE_EXPECTED_FORMAT}. Only 'C' carries "
                       f"current-lap time and surface type - reconfigure "
                       f"SimHub and run it again.")
        elif len(formats) > 1:
            problem = f"The format changed mid-capture: {'/'.join(formats)}."

        summary = {"path": writer.path, "packets": writer.count,
                   "formats": formats, "unparsed": unparsed,
                   "problem": problem}
        if problem:
            log("capture").warning("%s (%s)", problem, writer.path)
        else:
            log("capture").info("captured %d packets to %s",
                                writer.count, writer.path)
        return summary

    @property
    def capturing(self) -> bool:
        return self.bridge.capture is not None

    def toggle_capture(self, wanted: bool) -> None:
        """The Settings button. Says what happened, including when nothing did."""
        if self.settings_screen is None:
            return
        if wanted:
            path = self.start_capture()
            self.settings_screen.set_capturing(True)
            self.settings_screen.note_capture(
                f"Recording to {path}. Stop it when you come in - the file is "
                f"closed on stop, and analysed with tools/analyse_m0.py.")
            return

        summary = self.stop_capture()
        self.settings_screen.set_capturing(False)
        if summary is None:
            self.settings_screen.note_capture("Nothing was recording.")
            return
        if summary["problem"]:
            self.settings_screen.note_capture(summary["problem"], warn=True)
            return
        self.settings_screen.note_capture(
            f"{summary['packets']} packets, format "
            f"{'/'.join(summary['formats'])}, written to {summary['path']}.")

    # ------------------------------------------------------------- the bench
    #
    # 343 lines of "does the hardware work" moved to `bench.py`. None of it
    # runs during a session - it is what the Settings screen's buttons do,
    # plus the health line every tenth tick - and it was sitting in the middle
    # of the class that runs a race.
    #
    # Kept as methods because the tests call them on the controller and the
    # settings screen connects signals to them by name.

    def test_feed(self, listen_s: float = LISTEN_S) -> bool:
        return self.bench.test_feed(listen_s)

    def test_gauge(self) -> bool:
        return self.bench.test_gauge()

    def test_beep(self) -> bool:
        return self.bench.test_beep()

    def test_voice(self) -> None:
        self.bench.test_voice()

    def probe_button(self, listening: bool) -> None:
        self.bench.probe_button(listening)

    def _report_health(self) -> None:
        self.bench._report_health()


    # ------------------------------------------------------- session hygiene

    def _close_orphaned_sessions(self) -> None:
        """Close any session the last run left open, and say so.

        A session with no `ended_at` means the app went without stopping -
        killed, crashed, or the window shut mid-recording. Left alone it stays
        open forever and every later run looks like it is still going. Closed
        silently, nobody ever finds out the app died.
        """
        open_sessions = self.store.open_sessions()
        if not open_sessions:
            return
        for session in open_sessions:
            self.store.end_session(session["id"], at=session["last_seen"])
            log("session").warning(
                "session %s (%s, started %s) was never closed - the app did "
                "not shut down cleanly. Closed at %s.",
                session["id"], session["kind"], session["started_at"],
                session["last_seen"])
        newest = open_sessions[0]
        self.practice.set_status(
            f"The previous session ({newest['started_at'][:16].replace('T', ' ')}) "
            f"was never closed - the app did not shut down cleanly. Its laps "
            f"are kept. Anything it recorded after the last lap is lost; "
            f"logs/pitcrew.log has what happened.", warn=True)

    # ------------------------------------------------------------------- car

    def load_car(self, car: str) -> None:
        """Show a car's reference facts and whatever ranges are on file."""
        if self.car_screen is None or not car:
            return
        self.car_screen.show_car(car, catalogs.car_spec(car),
                                 self.store.get_range_record(car))

    def save_ranges(self, car: str, ranges: dict, verified: bool) -> None:
        """Measure a car once. Everything downstream picks it up from here."""
        if self.car_screen is None:
            return
        record = RangeRecord(
            car_name=car,
            measured_date=datetime.date.today().isoformat(),
            ranges=ranges,
            # **The installed game, not the event's.** A range record is a
            # reading off the car's own settings screen on whatever version is
            # running right now - it is not a property of the round being
            # prepared. Taking it from the event meant every record written
            # while the active event had a blank version was stored unversioned,
            # which is all three of them: the register now holds the RSR's
            # v1.71 endpoints beside the Shelby's and Huracan's v1.70 ones with
            # nothing marking the difference. 1.71 moved the three LSD axes from
            # a shared 5-60 to 0-30, 0-100 and 0-99, so a percentage read
            # against the wrong register is a different setting entirely.
            # The event still overrides, for a register re-entered from an
            # older version on purpose.
            game_version=((self.active_event() or {}).get("game_version")
                          or self.settings.game_version or None),
            verified=verified,
        )
        try:
            self.store.save_range_record(record)
        except SetupError as exc:
            self.car_screen.footer(f"Refused: {exc}", warn=True)
            return
        self.load_car(car)
        self.refresh_nav_state()
        self.car_screen.footer(
            f"Saved {len(ranges)} ranges for {car}"
            + (". Every prompt and every export now quotes them as measured."
               if verified else
               ". Not marked as read off the car, so they stay labelled "
               "estimates."))
        self.refresh_engineer()

    # -------------------------------------------------------- race engineer

    def prompt_context(self, kind: str):
        event = self.active_event()
        return gather(self.store, event_id=event["id"] if event else None,
                      kind=kind, game_version=self.settings.game_version)

    def refresh_engineer(self) -> None:
        """Say what the app is filling in, before anything is generated."""
        if self.engineer is None:
            return
        event = self.active_event()
        if event is None:
            self.engineer.set_context_note(
                "No event yet. Create one on the Event screen — a prompt has "
                "to be about something.")
            return
        context = self.prompt_context(self.engineer.kind())
        parts = [f"{context.car or 'no car'} at "
                 f"{context.circuit_name or 'no circuit'}"]
        if context.sheet is not None:
            parts.append(f"sheet {context.sheet.sheet_name}")
        if context.ranges.source == "record":
            parts.append("measured slider ranges"
                         if context.ranges.verified else
                         "slider ranges on file, unverified")
        else:
            parts.append("no measured ranges — estimated windows")
        if context.laps:
            parts.append(f"{len(context.laps)} recorded laps")
        gaps = context.missing()
        note = " · ".join(parts)
        if gaps:
            note += ". Not on file: " + ", ".join(gaps) + "."
        self.engineer.set_context_note(note)
        self._ask_only_what_is_left(context)

    def _ask_only_what_is_left(self, context) -> None:
        """Show the questions the data cannot answer, and answer the rest.

        **`prompts/questions.py` is the whole confirm-not-recall design and it
        had no caller anywhere in the app.** Five hundred lines, a registry, a
        gate and working resolvers, reachable only from its own test file -
        which is the fourth instance of that pattern found this week, and the
        one that cost the most, because what stood in its place was the
        thirteen-field form its own docstring is a rebuttal of.

        The rule it enforces is one line: **a question with a working resolver
        may never be asked.** It exists because on 23 Aug the driver was asked
        to watch the tyre indicators and report whether one rear wheel was
        spinning alone - a question `lap_frames` had answered seventeen
        thousand times over. He noticed before the app did.

        Silent on failure. A prompt screen that will not open because a
        resolver raised is worse than one asking a question it need not.
        """
        if self.engineer is None or not hasattr(self.engineer, "set_questions"):
            return
        try:
            from pitcrew.prompts.questions import resolve

            found = resolve(self.store, context, kind=self.engineer.kind())
        except Exception as exc:                            # noqa: BLE001
            log("prompts").warning(
                "could not work out what still needs asking: %s: %s",
                type(exc).__name__, exc)
            return
        if found.failed:
            # **A broken resolver ASKS rather than silently answering**, and
            # it says so here: the driver would otherwise never learn the app
            # had stopped looking at something it used to check.
            log("prompts").warning(
                "resolvers raised and their questions are being asked "
                "instead: %s", ", ".join(found.failed))
        self.engineer.set_questions(found)

    def generate_prompt(self, kind: str) -> str | None:
        """Compose a prompt and log it as issued."""
        if self.engineer is None:
            return None
        event = self.active_event()
        context = self.prompt_context(kind)
        try:
            prompt = build_prompt(context, self.engineer.report(), kind=kind)
        except PromptRefused as exc:
            self.engineer.show_prompt("")
            self.engineer.note(f"Refused: {exc}", warn=True)
            return None

        self.engineer.show_prompt(prompt.text, warnings=prompt.warnings)
        self.refresh_engineer()
        self.prompt_issue_id = self.store.log_prompt(
            kind=kind, body=prompt.text, prompt_version=PROMPT_VERSION,
            app_version=APP_VERSION,
            event_id=event["id"] if event else None,
            session_id=context.session_id,
            car_name=context.car, circuit=context.circuit_name)
        self.engineer.note(
            f"{KIND_LABELS.get(kind, kind)} logged as prompt "
            f"#{self.prompt_issue_id}, template {PROMPT_VERSION}.")
        self.refresh_nav_state()
        self.engineer.note_reply("")
        return prompt.text

    def copy_prompt(self) -> str:
        """Clipboard is the whole transport. The app makes no network calls."""
        if self.engineer is None:
            return ""
        text = self.engineer.prompt_text()
        clipboard = QApplication.clipboard()
        if clipboard is not None and text:
            clipboard.setText(text)
        self.engineer.note(
            "Copied. Paste it into the knowledge base session."
            if text else "Nothing to copy — generate first.", warn=not text)
        return text

    def file_prompt_reply(self, reply: str) -> None:
        """Keep what came back, against the prompt that asked for it."""
        if self.engineer is None:
            return
        if self.prompt_issue_id is None:
            self.engineer.note_reply(
                "Generate a prompt first — a reply is filed against the "
                "prompt that asked for it.", warn=True)
            return
        if not reply.strip():
            self.engineer.note_reply("Nothing pasted.", warn=True)
            return
        self.store.save_prompt_reply(self.prompt_issue_id, reply)

        # **Filed and fitted, from one paste.** The app had the reply in
        # memory, had a working parser, and asked him to paste the same block
        # a second time on a different screen - and the copy said so, which is
        # worse than the seam itself: it documented it rather than closing it.
        # Filing and fitting stay separate actions; the transcription between
        # them is what goes.
        parsed = parse_reply(reply)
        if parsed.sheets:
            self.event_screen.take_reply(reply)
            fitted = ", ".join(sorted(parsed.sheets))
            self.engineer.note_reply(
                f"Filed against prompt #{self.prompt_issue_id}, and the "
                f"{fitted} sheet{'' if len(parsed.sheets) == 1 else 's'} "
                f"loaded onto the Event screen. Check it there and save. "
                f"Your report has been cleared for the next session.")
            self.engineer.clear_report()
            return
        self.engineer.note_reply(
            f"Filed against prompt #{self.prompt_issue_id}. No setup block in "
            f"it, so nothing was fitted - paste the sheet into the Event "
            f"screen if there is one.", warn=True)

    # -------------------------------------------------------------- practice

    def _on_recording_toggled(self, wanted: bool) -> None:
        if not wanted:
            self.stop_practice()
            return
        try:
            self.start_practice()
        except Exception as exc:                            # noqa: BLE001
            # **Because the store is written before the screen is painted.**
            # `open_practice_session` opens the session in the database and
            # then paints the rack, so anything that throws in the painting
            # left a session running with a button still reading "Start
            # session" and no way to stop it - the driver's only recovery was
            # to restart the app, mid-lobby. It happened for real: a deleted
            # `EmptyState` widget in `_rebuild_rack`.
            #
            # Caught broadly on purpose. The specific fault is fixed, but the
            # shape of it - a UI failure orphaning a session in the store - is
            # worth closing off rather than waiting to meet again. Rolled back
            # so the screen and the database agree, and re-raised into the log
            # so it is still a bug and not a shrug.
            log("session").error(
                "starting practice failed and was rolled back: %s: %s",
                type(exc).__name__, exc, exc_info=True)
            try:
                self.stop_practice()
            finally:
                self.practice.set_recording(False)
                self.practice.set_status(
                    f"Could not start: {type(exc).__name__}. Nothing is "
                    f"recording - the log has the detail.", warn=True)

    def open_practice_session(self) -> int | None:
        """Start a practice session without touching the network.

        Separate from `start_practice` so the whole recording path can be
        driven without a socket - and so the sheet that was fitted is recorded
        the same way whoever opens the session.
        """
        event = self.active_event()
        if event is None:
            return None

        # **The sheet that matches what he is about to practise.** A
        # qualifying run on the race sheet is a measurement of the race
        # sheet, and filing it against the qualifying one would put a
        # symptom on the wrong car.
        #
        # Where the car has exactly ONE sheet on file, that is the sheet that
        # is on the car whatever it was labelled, and the session records it -
        # a car with one sheet is the normal case and refusing to open a
        # session over it would be bureaucracy. Where it has several and none
        # of them is for this purpose, the honest answer is that the app does
        # not know which one is fitted, so **the session records no sheet at
        # all rather than the wrong one**. Missing is null, never a
        # substitute: a `setup_sheet_id` that names a sheet he was not running
        # is worse than one that names none, because the export presents it as
        # the setup as run.
        # **Keyed on the circuit as well as the car.** Without it this picked
        # the car's most recent race sheet whatever circuit he was at - which
        # is how a Road Atlanta session came to be recorded against a Yas
        # Marina sheet on 23 Aug 2026, five sessions after the same class of
        # error was first written down.
        intent = self.practice.practice_intent()
        here = circuit_key_for(event)
        sheet = self.store.sheet_for(event["car_name"] or "", intent, here)
        if sheet is None:
            # **The one-sheet fallback may not cross a circuit.** "This car
            # has exactly one sheet, so that is what is on it" is sound
            # reasoning within a circuit and wrong across one: the single
            # sheet on file is then demonstrably for somewhere else.
            sheets = [s for s in self.store.list_setup_sheets(
                event["car_name"] or "") if s.circuit_key == here]
            sheet = sheets[0] if len(sheets) == 1 else None
            if sheet is None:
                others = len(self.store.list_setup_sheets(
                    event["car_name"] or ""))
                if others:
                    self.practice.set_status(
                        f"No {intent} sheet on file for this car at this "
                        f"circuit, and it has {others} for elsewhere - this "
                        f"run is recorded without one. Load the {intent} "
                        f"sheet on the Event screen.")
        sheet_id = sheet.id if sheet else None
        # The beep follows the gearbox that is actually fitted.
        self.bridge.set_sheet_shift_rpm(sheet.shift_rpm if sheet else None)

        self.bridge.reset()
        self.session_id = self.store.start_session(
            event["id"], "practice", setup_sheet_id=sheet_id,
            practice_mode=self.practice.practice_mode(),
            practice_intent=intent,
            game_version=self.settings.game_version)
        self.session_kind = "practice"
        self._tell_settings_about_the_session()
        # **Every change is an experiment, and this is where it is filed.**
        # The session that opens against a different sheet from the last one on
        # this car and circuit IS the run that tests the difference. Recorded
        # here rather than asked for later, because a ledger that depends on
        # somebody remembering is the ledger that held zero rows for 88
        # sessions. Silent and harmless when nothing changed.
        self._note_sheet_change()
        self._check_setup_record(event)

        # The rack is NOT cleared. Going out again adds to the session's
        # evidence; it does not replace it. Three runs at one circuit are one
        # body of evidence about one car.
        self.practice.set_laps(self._rows_for_event(event["id"]))
        if intent == FOR_QUALIFYING:
            self._arm_quali(event)
        return self.session_id

    def _arm_quali(self, event: dict, *, mid_lap: bool = False) -> None:
        """Arm the qualifying coach with what practice actually measured.

        Both halves arm independently and honestly: the temperature target
        is the window measured from this event's own laps (`race/temps.py`,
        never the fabricated band), and the delta reference is the best
        counted practice lap's frames. Either can be missing - the coach
        says what it is missing and coaches with the rest.

        Decodes up to sixteen lap blobs (~1 s) on the Qt thread - a
        pre-session action, the same cost the race arm already pays.
        `mid_lap` means the car is already circulating: the coach then holds
        its tongue until the next line crossing rather than calling "Out
        lap" into the middle of a flyer.
        """
        window = measured_temp_window(self.store, event["id"])
        reference = reference_lap(self.store, event["id"])
        speaks = self.practice.coach_speaks()
        brief = knowledge.for_event(self.store, event)
        self.bridge.quali = QualifyingCoach(
            window=window, reference=reference,
            speak=self.voice.say if speaks else None, mid_lap=mid_lap,
            # **The same briefing the race reads, and there is no quali
            # variant of it.** A circuit where the temperature call is noise
            # is a circuit where it is noise on a flying lap too, so a second
            # record shape would be a second thing to keep in step.
            knowledge=brief)
        if brief is None and speaks:
            # Said once, at the top of the session, for the same reason the
            # green says it in a race: silent fallback is how the gauge
            # ratchet stayed invisible for a whole race.
            self.voice.say(knowledge.NO_NOTES)
        # **The fuel call, before he goes out rather than after.**
        # Qualifying is the one run where carrying fuel is pure loss: there is
        # no stint to survive, so every litre is mass dragged round the only
        # lap that counts. The app has always known the burn and the weight
        # coefficient and never put them together into a sentence he could act
        # on.
        self._announce_quali_fuel(event)

        # One auditable line: what tonight's coaching rests on.
        log("quali").info(
            "armed: reference lap %s (%s), window front %s rear %s, "
            "laps to window %s, %s",
            reference.lap_id if reference else None,
            f"{reference.lap_time_ms / 1000:.3f}s" if reference else "none",
            window.front if window else None,
            window.rear if window else None,
            window.laps_to_window if window else None,
            "speaking" if speaks else "silent")

    def _say_brief(self, event: dict, plan: dict | None, *,
                   speaks: bool) -> None:
        """What the engineer can see this race. App state only, no telemetry."""
        stints = ((plan or {}).get("stints") or [])
        compounds = tuple(
            s.get("compound") for s in stints
            if isinstance(s, dict) and s.get("compound"))
        sampler = getattr(self, "_hud", None)
        # **`events.race_laps` holds MINUTES when `race_type` is `time`, and
        # `race_minutes` is NEVER written** - `race/coordinator.py` says so in
        # its own docstring. Gating on `race_minutes` therefore never fired,
        # so every timed race was briefed as a lap count: Spa's 120 minutes
        # was announced as "120 laps", and Monza's 50 and Yas's 30 the same
        # way. Read `race_type`, which is the field that actually says.
        timed = (event.get("race_type") or "laps") == "time"
        declared = event.get("race_laps")
        lines = brief(Instruments(
            has_plan=plan is not None,
            race_laps=None if timed else declared,
            race_minutes=(float(declared) if declared else None) if timed
            else event.get("race_minutes"),
            stops=(len(stints) - 1) if stints else None,
            compounds=compounds,
            # **Only if it is actually working now.** Switched on, built, and
            # not already stood down - promising an instrument that is not
            # there is worse than promising nothing.
            wear_gauge=bool(self.settings.hud_wear_enabled
                            and sampler is not None
                            and not sampler.stood_down),
            temp_window=measured_temp_window(self.store, event["id"]) is not None,
            # The `A` format carries no per-wheel surface, so nothing can
            # see a kerb or an off. Read off the last packet rather than a
            # setting, because the format is whatever the console actually
            # sent. Unknown is treated as present: the brief should not
            # announce a limitation it has not observed.
            surface_channel=(getattr(self.bridge.last_packet,
                                     "packet_format", None) or "C") != "A",
        ))
        # **The championship, on the grid, once.** It is the one thing said
        # here that is not about the car: what has to be finished today and who
        # in this race can still take it. Appended rather than folded in, so a
        # race with no league reads exactly as it always did.
        title = self._league_line()
        if title:
            lines = list(lines) + [title]
        for line in lines:
            log("race").info("brief: %s", line)
        if self.race_screen is not None:
            self.race_screen.set_status(" ".join(lines))
        # **`speaks` is passed rather than read.** `_engineer_speaks` is not
        # assigned until later in the arming sequence, so reading it here got
        # the *previous* race's answer - and a silent run spoke.
        if speaks:
            for line in lines:
                self.voice.say(line)

    def _announce_quali_fuel(self, event: dict) -> None:
        """Say the qualifying load, or say why there is not one.

        **Silence would read as "carry what you like".** Where nothing has
        measured this car's burn here the refusal is spoken instead, because
        an unconfident call that says so is still a call he can act on.
        """
        try:
            inputs, _evidence = build_inputs(self.store, event["id"])
        except Exception:                                    # noqa: BLE001
            inputs = None

        burn = getattr(inputs, "fuel_per_lap_l", None) if inputs else None
        load = qualifying_fuel(
            fuel_per_lap_l=burn,
            fuel_capacity_l=getattr(inputs, "fuel_capacity_l", None)
            if inputs else None,
            fuel_weight_s_per_l_per_lap=getattr(
                inputs, "fuel_weight_s_per_l_per_lap", None) if inputs else None,
            # The load the burn was measured at. Practice runs a race-ish tank
            # and a quali run is near-empty, so without this the flat product
            # over-fuels the one lap that must carry nothing.
            fuel_reference_load_l=getattr(
                inputs, "fuel_reference_load_l", None) if inputs else None)
        said = load.call() if load is not None else quali_fuel_refusal(burn)
        if not said:
            return
        log("quali").info("%s", said)
        if self.practice is not None:
            self.practice.set_status(said)
        if self.practice is not None and self.practice.coach_speaks():
            self.voice.say(said)

    # ------------------------------------------------------------- the rig
    #
    # **Six lines of delegation over 597 lines that used to live here.** The
    # supervisor holds the watchdog, the endpoint note and the recovery
    # ladder; this class can no longer reach any of them, which is the whole
    # point of the cut. See `rig/supervisor.py`.
    #
    # Kept as methods rather than replaced at every call site because the
    # settings screen connects a signal straight to `test_haptics`, and
    # because a session boundary saying `self.start_haptics()` reads as the
    # session doing something rather than as plumbing.

    def start_haptics(self) -> bool:
        return self.rig.start_haptics()

    def test_haptics(self) -> None:
        self.rig.test_haptics()

    def stop_haptics(self) -> None:
        self.rig.stop_haptics()

    def start_wind(self) -> bool:
        return self.rig.start_wind()

    def stop_wind(self) -> None:
        self.rig.stop_wind()

    def shutdown_wind(self) -> None:
        self.rig.shutdown_wind()




    @staticmethod
    def _feed_description(values) -> str:
        """Where a given settings object would take telemetry from."""
        if values.feed_source == FEED_PS5 and values.ps5_ip.strip():
            return (f"the console at {values.ps5_ip.strip()} "
                    f"on {GT7_STREAM_PORT}")
        if values.feed_source == FEED_PS5:
            return "the console - but no address has been entered"
        return f"SimHub on {values.udp_port}"

    @property
    def direct(self) -> bool:
        """Talking to the console itself rather than to SimHub."""
        return (self.settings.feed_source == FEED_PS5
                and bool(self.settings.ps5_ip.strip()))

    @property
    def feed_port(self) -> int:
        """The port to bind.

        Direct mode is not free to choose: GT7 streams on its own port and
        the configured one is SimHub's relay, so using it in direct mode
        would bind a port the console never sends to.
        """
        return GT7_STREAM_PORT if self.direct else self.port

    @property
    def heartbeat_target(self) -> str | None:
        return self.settings.ps5_ip.strip() if self.direct else None

    # ------------------------------------------------ tyre wear off the video

    # ------------------------------------------------------- the wear gauge
    #
    # 183 lines of sampler lifecycle, worker-thread callbacks and OBS
    # recording moved to `telemetry/hud_session.py`. What it hands back is
    # four values - the latest reading, its lap, a blind note and a request -
    # which used to be four loose attributes on this class read from three
    # different places. See that module for why `new_session` matters.

    def _new_hud_session(self) -> None:
        self.hud.new_session()

    def _stop_hud_sampler(self) -> None:
        self.hud.stop()

    def _start_video(self) -> None:
        self.hud.start_video(self.session_id)

    def _stop_video(self, session_id: int | None) -> None:
        self.hud.stop_video(session_id)


    def _note_sheet_change(self) -> None:
        """File this session's setup delta, and never let it cost a session.

        The ledger is worth having and it is worth nothing at all compared with
        the session opening. Every failure here is logged and swallowed - see
        `Store.note_sheet_change` for what it records and why the caller was
        missing for so long.
        """
        if self.session_id is None:
            return
        try:
            self.store.note_sheet_change(self.session_id)
        except Exception as exc:                            # noqa: BLE001
            log("store").warning(
                "could not file this session's setup delta: %s: %s",
                type(exc).__name__, exc)

    def _check_setup_record(self, event: dict) -> None:
        """Ask, at the top of a session, whether anybody has checked the car.

        **Rank zero, and the app has never once caught it itself.** The setup
        record was wrong in five consecutive sessions - a Yas Marina sheet at
        Road Atlanta, a v1 sheet against a Rev B car, `bb -1` in the car
        against `0` on every sheet on file - and every one was found by the
        driver mentioning it in passing.

        **It prompts and it never blocks.** A session not recorded cannot be
        re-driven, and a sheet can be corrected afterwards and the session
        re-bound. The place that refuses is the export, because that is where
        a wrong premise stops being a local error and becomes a knowledge
        base's permanent learning. See `setup/doubt.py` and `export/build.py`.

        The gearbox detector needs a fitted box and there is none before the
        first lap, so at this point only the unfiled-revision half can speak.
        That is the half that matters here anyway: it is answerable at the
        desk, with the headset off, before he goes out.
        """
        try:
            found = doubt.for_event(self.store, event)
        except Exception as exc:                            # noqa: BLE001
            log("setup").warning("could not check the setup record: %s: %s",
                                 type(exc).__name__, exc)
            return
        if not found:
            return
        note = (f"Setup record unverified. {found.describe()} "
                f"Photograph the setup and gear screens before you go out.")
        log("setup").warning("%s", note)
        if self.practice is not None:
            self.practice.note(note, warn=True)


    def start_practice(self) -> None:
        # Starting one session over another left the first with no `ended_at`
        # and its listener running: SO_REUSEADDR lets the second UDP bind
        # succeed, and on Windows the *first* socket keeps the datagrams, so
        # the new session went deaf while the orphan fed the bridge.
        if self.session_id is not None:
            self.practice.set_status(
                "A session is already open. Stop it before starting another.",
                warn=True)
            self.practice.set_recording(False)
            return
        if self.open_practice_session() is None:
            self.practice.set_status(
                "Create an event before recording - laps have to belong to "
                "something.", warn=True)
            self.practice.set_recording(False)
            return

        # **After the session exists, before the first lap can land.** The
        # zero has to be stamped against a session row, and it has to be
        # stamped before anything is recorded against it, or the first laps
        # sit outside the capture the index says contains them.
        self._start_video()
        self._new_hud_session()

        self.voice.warm()
        self.listener = UDPListener(
            "0.0.0.0", self.feed_port, self.bridge.on_packet,
            source_ip=self.settings.udp_source_ip,
            heartbeat_to=self.heartbeat_target)
        self.listener.start()
        self._parse_errors = 0
        self._store_errors = 0
        self._health.start()
        self.start_haptics()
        self.start_wind()
        # Off by default: the engineer only answers during a race. On, it is
        # how the button gets tested without committing to a race.
        if self.settings.ptt_enabled and self.settings.ptt_in_practice:
            self.ptt.start()
        log("session").info(
            "practice session %s open, listening on %s", self.session_id,
            self.port)

        self.practice.set_recording(True)
        where = (f"Asking the PS5 at {self.settings.ps5_ip} for format "
                 f"{self.listener.heartbeat_format}, listening on "
                 f"{self.feed_port}"
                 if self.direct else f"Listening on {self.feed_port}")
        status = f"{where}. Waiting for the car to go out."
        coach = self.bridge.quali
        if coach is not None:
            # The armed state and what it was armed with, where he can read
            # it before putting the headset on. The coaching itself is voice.
            status += (" Qualifying coach armed - reference "
                       f"{coach.reference.lap_time_ms / 1000:.1f}."
                       if coach.reference else
                       " Qualifying coach armed - no reference lap, "
                       "temperatures and lap times only.")
        self.practice.set_status(status)
        self.announce("Recording", "Go out when you are ready.")

    # ------------------------------------------- the capture's own zero point


    def stop_practice(self) -> None:
        # The coach before the listener, so no frame can arrive for a coach
        # whose session is being closed under it.
        self.bridge.quali = None
        self.stop_haptics()
        self.stop_wind()
        if self.listener is not None:
            self.listener.stop()
            self.listener = None
        self._health.stop()
        self.ptt.stop()
        if self.session_id is not None:
            closing = self.session_id
            self.store.end_session(closing)
            log("session").info("practice session %s closed", closing)
            self.session_id = None
            self.session_kind = None
            self._tell_settings_about_the_session()
            # After the session is closed, so a slow websocket cannot hold the
            # close open - the session row is what matters and it is written.
            self._stop_video(closing)

        self.practice.set_recording(False)
        event = self.active_event()
        rows = self.practice.rows()
        self.announce("Stopped", f"{len(rows)} laps recorded."
                      if rows else "No laps recorded.",
                      warn=not rows)
        if rows:
            learned = self._learn_clock(event)
            self.practice.set_status(
                f"Session closed. {len(rows)} laps recorded - mark them up, "
                f"then export.{learned}")
            self._start_debrief(event)
        elif event:
            self.practice.set_status(self._idle_status(event))

    def _start_debrief(self, event) -> None:
        """Build the practice debrief off the Qt thread, then speak it.

        **This is the half of the practice gap that can be answered honestly.**
        Every live call in the app comes from `RaceCoordinator`, built only in
        `start_race()` - so George owns the race and nothing owned practice, and
        three Daytona sessions were driven with the engineer silent throughout
        while every number he would have wanted was computed and stored.

        **Off the Qt thread, and not with `QTimer.singleShot`.** Building it
        decodes every practice lap's telemetry: 2.5 s on the active event and
        9.4 s on the largest, which is a frozen window at the moment the driver
        has just stopped. `Store` opens sqlite with `check_same_thread=False`
        and this path only reads. The hop back is a queued signal for the
        reason spelled out in `_on_ptt_answer`: a `singleShot` posted from a
        worker builds its dispatch object on the calling thread and never
        fires.
        """
        if event is None:
            return
        event_id = event["id"]

        def work() -> None:
            try:
                from pitcrew.analysis.debrief import from_store
                debrief = from_store(self.store, event_id)
            except Exception:
                # A debrief that cannot be built is not worth taking the app
                # down for, and it happens for an honest reason: no corner
                # model for this circuit yet.
                log("session").exception("debrief failed for event %s", event_id)
                return
            if debrief is not None:
                self.bridge.debriefed.emit(debrief)

        threading.Thread(target=work, name="debrief", daemon=True).start()

    def _on_debriefed(self, debrief) -> None:
        """Say it, and put the same words on the screen.

        **The screen gets the lines whether or not the voice is on.** The
        engineer being muted is a preference about audio, not an instruction to
        withhold the finding - and a debrief that exists only as speech cannot
        be re-read, which is most of what a debrief is for.
        """
        from pitcrew.analysis.debrief import spoken_lines

        lines = spoken_lines(debrief)
        if not lines:
            return
        for line in lines:
            if self._engineer_speaks:
                self.voice.say(line)
        self.practice.set_status(" ".join(lines))
        log("session").info("debrief: %s", " | ".join(lines))

    def announce(self, headline: str, subtitle: str = "", *,
                 warn: bool = False) -> None:
        """Put one line where it can be read through a headset.

        Silently does nothing without a Qt parent, so the whole recording
        path stays drivable headless - which is what the controller tests
        do, and what a capture replay does.
        """
        if not self.settings.banner_enabled or self._banner is None:
            return
        self._banner.announce(headline, subtitle, warn=warn)

    def _learn_clock(self, event) -> str:
        """Put what the game clock did into the event, once it is known.

        He asked why practice never filled the start hour or the time
        multiplier in. It was measured, cached against the circuit, and never
        written anywhere he could see it.

        It is read across every lap of the event rather than the session just
        closed: a session run entirely after the circuit's clock has stopped
        measures a multiplier of zero, which is true of that session and false
        of the lobby.
        """
        if event is None:
            return ""
        laps = _rows_to_laps(self.store,
                             self.store.list_event_laps(event["id"], "practice"),
                             hydrate=set())
        reading = read_clock(laps)
        if not reading.measured:
            return ""
        if not self.store.record_measured_clock(
                event["id"], reading.start_hour, reading.multiplier):
            return ""
        # The form is reloaded so the figure appears where he went looking
        # for it, rather than only inside the next export.
        self.event_screen.set_events(self.store.list_events(), event["id"])
        return (f" Game clock measured: x{reading.multiplier:g} from "
                f"{clock(reading.start_hour)}.")

    def _on_stream_seen(self, facts: dict) -> None:
        if self.session_id is None:
            return
        status = self.store.note_stream_facts(
            self.session_id,
            packet_format=facts["packet_format"],
            car_category=facts["car_category"],
            fuel_capacity_l=facts["fuel_capacity_l"],
            car_id=facts.get("car_id"),
            wheelbase_m=facts.get("wheelbase_m"),
            # Stamped on the id the moment it is learned, because packet-id
            # stability across a GT7 version bump is **unproven** - one car,
            # one version. A renumbering has to be visible as a flagged
            # session rather than as a silent reassignment.
            game_version=self.settings.game_version)
        if status and status != IDENTITY_OK:
            # **Said while the run is happening.** Session 11's mismatch was
            # discovered three days later, by which time its fuel figure was
            # in an approved race plan. A flag nobody sees until the
            # post-mortem is the same as no flag.
            self.practice.set_status(
                f"Connected, but this run is flagged: {status}. Its laps will "
                "not be used to cost a race plan until you resolve it.")
            return
        self.practice.set_status(
            f"Connected. Packet {facts['packet_format'] or '?'}"
            f"{', ' + facts['car_category'] if facts['car_category'] else ''}."
            " Laps land here as you complete them.")

    def _on_parse_failed(self) -> None:
        self._parse_errors += 1

    def _close_the_ruler_lap(self, lap_num: int | None) -> None:
        """A crossing: the ruler closes the lap and says whether it measured it.

        A lap that did not come out the length of the circuit was a teleport or
        a long dropout, and every sector boundary on it is in the wrong place.
        The caller throws those laps away rather than binning them wrongly -
        see `race/sectors.py`.
        """
        ruler = getattr(self, "_lap_ruler", None)
        if ruler is None:
            return
        try:
            ruler.crossed_line(lap_num)
        except Exception:
            log("race").exception("the lap ruler could not close a lap")

    def _on_lap_completed(self, lap, rows) -> None:
        """Qt thread: compress, store, and put the lap on the rack."""
        if self.session_id is None:
            return
        # **The ruler closes its lap on the crossing**, so the next one starts
        # from zero and the finished one can be judged against the circuit.
        self._close_the_ruler_lap(getattr(lap, "lap_num", None))
        # **The clock onto the lap BEFORE it is written.** The coordinator
        # owns the clock and stamped it there, in `_on_lap` - which is a
        # different queued slot, and Qt runs them FIFO, so the INSERT happened
        # first and the three columns were NULL on every row ever written. A
        # write-only column is worse than no column: the next audit trusts it.
        # Here the row has not been written yet and the clock is a lap old at
        # worst, which is the same instant the driver was told.
        if self.race is not None and self.race.clock is not None:
            self.race.stamp_clock(lap)
        # **Where the other cars are, refreshed on the crossing.** A rival's
        # position is filed at his STOP, which is the one moment it does not
        # describe where he is racing - so a call that asks "is he near enough
        # to attack" would be reading a place he held while standing still.
        wall = getattr(self, "_pit_wall", None)
        if self.race is not None and wall is not None:
            try:
                self.race.note_rival_positions(wall.positions())
                # **The trends hold a cluster id; the roster turns it into a
                # name, and the roster is here.** Without it every gap call
                # says "the car ahead" about a driver the app can name.
                self.race.note_gaps(
                    ahead=wall.ahead, behind=wall.behind,
                    ahead_name=wall.roster.name_of(wall.ahead.subject),
                    behind_name=wall.roster.name_of(wall.behind.subject))
            except Exception:
                log("race").exception("the gap trends could not be read")
        frames = self.bridge.recorder.encode(rows)

        # **A lap has to have been driven for as long as it says it was.**
        #
        # Observed twice. Two laps driven, three recorded; the third carried
        # 192 frames - 3.2 seconds - while claiming lap two's time. Then again
        # after the haptic rebuild: two and a third laps driven, three
        # recorded, the third carrying 1,306 frames against a claimed 110.9 s
        # and lap two's exact time.
        #
        # The cause is upstream and is not a bug in the lap detector. GT7's
        # `last_lap_ms` is a reliable crossing signal while the stream is
        # continuous, but leaving the session drops it and brings it back -
        # and a value that has changed away and back satisfies "this is a new
        # lap time" perfectly. The fragment then inherits a whole lap's time.
        #
        # A phantom lap is not cosmetic. It lands on the rack, in the best-lap
        # comparison, in the degradation fit and in the stint count, and it
        # looks exactly like a real lap that happened to match the one before.
        #
        # **The claimed time is what gets removed, not the evidence.** Marking
        # it excluded was not enough: the row still carried a lap time it
        # never set, and a lap time on the record is a number something will
        # eventually average. So the time is cleared, the lap is excluded, and
        # it never reaches the rack - he sees the two laps he drove. The
        # frames stay on disk with the reason attached, because CLAUDE.md's
        # rule throughout is that doubtful evidence is quarantined and
        # labelled rather than deleted.
        # **Judged only where there is something to judge against.** A lap
        # that recorded no frames at all is not evidence that it did not
        # happen - it is the absence of evidence either way, and the
        # conservative reading of that is to believe GT7. Every phantom seen
        # so far arrived with plenty of frames: 192 the first time and 1,306
        # the second.
        fragment = False
        if frames is not None and lap.lap_time_ms:
            recorded_s = frames.frame_count / max(1.0, frames.sample_hz)
            claimed_s = lap.lap_time_ms / 1000.0
            fragment = (recorded_s >= _LAP_MIN_EVIDENCE_S
                        and recorded_s < claimed_s * _LAP_FRAGMENT_FRACTION)
            if fragment:
                log("session").warning(
                    "lap %s carries %.1fs of frames against a claimed %.1fs - "
                    "it never crossed the line, so it is not being counted as "
                    "a lap", lap.lap_num, recorded_s, claimed_s)
                # A time it did not set is the part that does damage. Nothing
                # downstream can average, rank or fit against a zero, and
                # `delta_ms` goes with it for the same reason.
                lap = replace(lap, lap_time_ms=0, delta_ms=0)

        if frames is not None:
            # Taken while the rows are still uncompressed and in hand. The
            # alternative is decoding the blob back out every time the rack
            # redraws, which it does on every mark he makes.
            seen = read_rows(rows, FRAME_FIELDS, frames.sample_hz)
            frames = replace(frames, crawl_s=seen.crawl_s,
                             off_track_s=seen.off_track_s,
                             spin_s=seen.spin_s)
        # **The session's opening lap is judged here, before it is written,
        # by the rule the rack rebuilds with.** The session state flags an
        # out-lap on a PIT EXIT, and a pit exit needs a pit ENTRY first -
        # which a lap that begins already in the box never has. So the
        # opening lap of every lobby session reached the database as
        # `is_out_lap = 0`, the rack struck it on the screen from
        # `auto_out_laps` and wrote nothing back, and `min(lap_time_ms)` over
        # the Daytona event returned a 93.100 s pit-exit-to-line fragment as
        # the best lap. Only ever set, never cleared; `None` leaves the flag
        # as it was. The accept is logged as well as the refusal (rule 10).
        lap, verdict = flag_opening_lap(
            lap,
            session_kind=self.session_kind,
            practice_mode=(self.practice.practice_mode()
                           if self.session_kind == "practice" else None),
            standing_start_ms=(frames.standing_start_ms
                               if frames is not None else None))
        if verdict is not None:
            log("session").info(
                "opening lap %s: %s (%s)",
                "is an out-lap" if verdict.is_out_lap
                else "left as recorded" if verdict.is_out_lap is None
                else "is not an out-lap",
                verdict.reason,
                "flag set" if verdict.is_out_lap else "flag unchanged")
        try:
            lap_id = self.store.add_lap(self.session_id, lap, frames=frames)
        except sqlite3.Error:
            # A lap that cannot be stored is the one failure the driver must
            # not have to read a log to discover: he is in the car, watching
            # the rack, and an empty rack is indistinguishable from a lap that
            # simply has not landed yet. Say it on the page, keep the session
            # running so the rest of the run is not lost with it.
            self._store_errors += 1
            log("session").exception(
                "lap %s could not be stored", lap.lap_num)
            self.practice.set_status(
                f"Lap NOT saved - the database rejected it "
                f"({self._store_errors} so far this run). See logs/pitcrew.log.",
                warn=True)
            return
        if fragment:
            # Marked after the insert rather than carried on the `Lap` record,
            # which has no such field - `Lap` is what GT7 said, and this is
            # what we make of it.
            self.store.exclude_lap(lap_id, "fragment")
            self.refresh_nav_state()
            # **And it stops here.** The rack is his count of what he drove;
            # a lap that never crossed the line does not belong on it.
            return

        # **The lap he said to throw away.** Set by a driver report during the
        # lap; consumed here, on the first lap to land after it. It runs after
        # the fragment check above deliberately - a fragment never reaches
        # this line, so a report made during one is still waiting for the next
        # real lap, which is the one he meant.
        pending = getattr(self, "_exclude_next_lap", None)
        if pending:
            self._exclude_next_lap = None
            self.store.exclude_lap(lap_id, pending)
            log("pitcrew").info(
                "lap %s excluded on the driver's report: %s",
                lap.lap_num, pending)

        # **One gauge reading per crossing, off this thread.** GT7 sends no
        # wear channel and he will not record it by hand, so the only source
        # is the capture that is running anyway. The request returns at once
        # and may be dropped; nothing here waits on it, and a fragment never
        # gets one because it is not a lap.
        # **The lap NUMBER, kept against the id the sampler answers with.**
        # The reading comes back on a worker thread carrying only the lap id,
        # and the race state files wear by lap number - so the pairing has to
        # be made where both are in hand. `note_lap` bounds what it keeps: it
        # is a lookup for a reading already in flight, not a record of the
        # session.
        self.hud.note_lap(lap_id, lap.lap_num)
        self.hud.request(lap_id)
        self._tag_race_compound(lap_id)
        self.refresh_nav_state()
        # Race laps belong to the race session, not to the practice rack.
        # They were pushed on here numbered as a continuation of the practice
        # laps, then vanished on the next rebuild because `_rows_for_event`
        # filters on kind - and in between, `_on_lap_changed` ran
        # `carry_compound` across a rack holding both.
        if self.session_kind != "practice":
            return
        self.practice.add_lap(LapRow(
            lap_id=lap_id,
            lap_num=len(self.practice.rows()) + 1,
            lap_time_ms=lap.lap_time_ms,
            fuel_used=lap.fuel_used,
            # The rack reads the tank to find where one run ends and the next
            # begins, which is where a fresh set can be declared.
            fuel_start=lap.fuel_start,
            fuel_end=lap.fuel_end,
            compound=lap.compound,
            is_out_lap=lap.is_out_lap,
            is_pit_lap=lap.is_pit_lap,
            session_id=self.session_id,
            # **The rack names out-laps itself and cannot do it without this.**
            # `PracticeScreen.add_lap` applies `auto_out_laps`, whose one
            # exception is the opening lap of a TIME TRIAL - the car starts on
            # track there and that lap is the session best in six of the eight
            # time trials on file. Left off, every row reached the rule as
            # `practice_mode=None`, the exception could never fire, and the
            # live path would have struck the best lap of the day and then
            # handed it back on the next rebuild.
            practice_mode=self.practice.practice_mode(),
            lap_num_in_session=lap.lap_num,
            # What the opening-lap rule corroborates the declaration with;
            # without it the rack's rule and the flag just written could
            # read the same session two ways.
            standing_start_ms=(frames.standing_start_ms
                               if frames is not None else None),
        ))

    def plan_qualifying(self) -> bool:
        """How much fuel to put in, and how many runs fit.

        **The measured burn is the whole input, and without it there is no
        plan.** A qualifying run wants the laps it will actually drive and not
        one litre more - a full tank is about 73 kg - so every figure here
        comes off what this car has actually shown at this event, and where it
        has shown nothing the plan refuses rather than assuming a rate.
        """
        if self.strategy is None:
            return False
        from pitcrew.race.qualifying_plan import QualifyingInputs, build
        from pitcrew.race.temps import measured_temp_window

        event = self.active_event()
        if event is None:
            self.strategy.note("Create an event first.", warn=True)
            return False

        # The event's own practice laps, through the same reader every other
        # measurement uses - so the burn here and the burn the race plan is
        # costed on cannot disagree.
        inputs = self._race_inputs_for(event) if hasattr(
            self, "_race_inputs_for") else None
        burn = getattr(inputs, "fuel_per_lap_l", None) if inputs else None
        if burn is None:
            burn = self._measured_burn(event)

        # **A plan the app did not write wins.** Under the 29 Aug
        # architecture Ludo authors and the app costs, certifies and
        # executes; `build` below stays as the fallback for an event nobody
        # has written one for, and it says which it showed.
        written = self.store.qualifying_plan(event["id"])
        if written:
            from pitcrew.race.qualifying_plan import QualifyingPlan, Run

            plan = QualifyingPlan(
                runs=[Run(**run) for run in written.get("runs") or ()],
                fuel_l=written.get("fuel_l"),
                weight_saved_kg=written.get("weight_saved_kg"),
                estimated_gain_s=written.get("estimated_gain_s"),
                assumptions=list(written.get("assumptions") or ()),
                refusals=list(written.get("refusals") or ()))
            self.strategy.show_qualifying(plan)
            self.strategy.note("Qualifying plan written by the race engineer "
                               "- the app did not cost this one.")
            log("pitcrew").info("showed the written qualifying plan for "
                                "event %s", event["id"])
            return True

        window = measured_temp_window(self.store, event["id"])
        plan = build(QualifyingInputs(
            lap_time_ms=self._best_practice_lap_ms(event),
            fuel_per_lap_l=burn,
            fuel_capacity_l=self._event_fuel_capacity(event["id"]),
            laps_to_window=window.laps_to_window if window else None,
            session_minutes=self.strategy.qualifying_minutes()))
        self.strategy.show_qualifying(plan)
        log("pitcrew").info(
            "qualifying plan: %s",
            "; ".join(plan.as_text()) if plan.usable
            else "refused - " + "; ".join(plan.refusals))
        return plan.usable

    def _measured_burn(self, event: dict) -> float | None:
        """Median fuel used over this event's counted practice laps."""
        from statistics import median

        from pitcrew.analysis.session import counted_laps
        from pitcrew.export.build import event_lap_inputs

        # `hydrate=set()` - `fuel_used` is a column on the lap, and the
        # default hydrates EVERY lap's 60 Hz blob to reach it. Measured on
        # the active event, 3.4 s against 1.0 ms for the same answer.
        used = [lap.fuel_used for lap
                in counted_laps(event_lap_inputs(self.store, event["id"],
                                                 "practice", hydrate=set()))
                if lap.fuel_used and lap.fuel_used > 0]
        return median(used) if used else None

    def _best_practice_lap_ms(self, event: dict) -> int | None:
        times = [row["lap_time_ms"] for row
                 in self.store.list_event_laps(event["id"], "practice")
                 if not row.get("excluded") and not row.get("is_out_lap")
                 and not row.get("is_pit_lap") and (row.get("lap_time_ms") or 0) > 0]
        return min(times) if times else None

    def read_the_stint(self) -> bool:
        """What the run just recorded says about its corners.

        **On demand, and only on demand.** It decompresses every lap's frames
        and re-measures every corner window, which is not work to do on a
        repaint - and it is a thing he asks for with the headset off, between
        runs, rather than something that should happen while he is driving.

        The session is the unit, not the event. `analysis/corner_findings`
        estimates the noise floor from CONSECUTIVE laps, and two laps either
        side of a session boundary are not consecutive in any sense that
        estimate can use.
        """
        if self.practice is None:
            return False
        from pitcrew.analysis.corner_findings import analyse
        from pitcrew.analysis.corners import CountedLap
        from pitcrew.analysis.resolve import resolve_corner_model

        event = self.active_event()
        rows = self.practice.rows()
        if event is None or not rows:
            self.practice.set_status(
                "Nothing to read - record a run first.", warn=True)
            return False

        counted = []
        reference = None
        for row in rows:
            if not row.counted:
                continue
            stored = self.store.get_lap_frames(row.lap_id)
            if not stored:
                continue
            frames = stored["frames"]
            counted.append(CountedLap(row.lap_num, frames,
                                      sample_hz=stored.get("sample_hz")))
            if reference is None or (row.lap_time_ms or 0) < reference[0]:
                reference = (row.lap_time_ms or 0, frames)

        if not counted:
            self.practice.set_status(
                "No counted lap on the rack carries frames to read.",
                warn=True)
            return False

        model = resolve_corner_model(self.store, event.get("track") or "",
                                     event.get("layout"),
                                     reference[1] if reference else None)
        if model is None:
            # **Honest rather than empty.** No stored model and a reference lap
            # that would not segment means there are no corner identities to
            # report against - not that the corners were fine.
            self.practice.set_status(
                "No corner model for this circuit yet, and the fastest lap "
                "would not segment - so there are no corners to report "
                "against.", warn=True)
            return False

        report = analyse(model, counted)
        self.practice.show_debrief(report)
        log("pitcrew").info(
            "stint read: %d finding(s) over %d lap(s), %d held out",
            len(report.findings), report.laps_used, report.laps_held_out)
        return True

    def _on_practice_mode(self, mode: str) -> None:
        """He changed his mind about where the car starts.

        Written straight through to the open session rather than held until
        the next one: the question is asked once, immediately before going
        out, which is the worst moment to make anybody answer carefully. It is
        also the answer that decides whether the session's opening lap counts,
        so it has to be correctable after the fact.
        """
        if self.session_id is not None:
            self.store.set_practice_mode(self.session_id, mode)
        event = self.active_event()
        if event:
            # The rack redraws because the answer moves which laps are
            # out-laps, and that is visible on it.
            self.practice.set_laps(self._rows_for_event(event["id"]))

    def _on_practice_intent(self, intent: str) -> None:
        """He changed what this session is for.

        Correctable after the fact for the same reason the mode is: it is
        asked immediately before going out, and it changes what the
        numbers mean rather than which laps count, so getting it wrong
        costs a reading rather than a lap.
        """
        if self.session_id is not None:
            self.store.set_practice_intent(self.session_id, intent)
        # The coach follows the intent live: switching to qualifying
        # mid-session arms it, switching away stands it down. Only for an
        # open practice session - a race has its own engineer.
        if self.session_id is None or self.session_kind != "practice":
            return
        if intent == FOR_QUALIFYING:
            event = self.active_event()
            if event is not None and self.bridge.quali is None:
                # Mid-lap if the stream shows the car on track: the fresh
                # coach then waits for the next line crossing instead of
                # announcing an out lap that is not one.
                self._arm_quali(event, mid_lap=self.bridge.state.on_track)
        elif self.bridge.quali is not None:
            self.bridge.quali = None
            log("quali").info("disarmed - intent moved off qualifying")

    def _on_coach_speaks(self, speaks: bool) -> None:
        """The Speaks/Silent toggle follows him live, mid-session.

        Silent still records: the coach keeps computing and logging every
        call, exactly as the race engineer's silent mode does.
        """
        coach = self.bridge.quali
        if coach is not None:
            coach.set_speak(self.voice.say if speaks else None)

    @staticmethod
    def _laps_of_fuel_in_hand(state) -> float | None:
        """Laps the fuel aboard covers beyond what is left to run.

        None where either half is unknown - a surplus computed against a burn
        nobody measured is a number he would plan around.
        """
        aboard = state.laps_of_fuel()
        needed = state.laps_remaining()
        if aboard is None or needed is None:
            return None
        return round(aboard - needed, 1)

    @staticmethod
    def _worst_wear(lap) -> float | None:
        values = [getattr(lap, f"wear_{c}", None) for c in ("fl", "fr", "rl", "rr")]
        present = [v for v in values if v is not None]
        return max(present) if present else None

    @staticmethod
    def _worst_wear_corner(lap) -> str | None:
        """Which corner it is - the number is worth little without it."""
        pairs = [(getattr(lap, f"wear_{c}", None), c)
                 for c in ("fl", "fr", "rl", "rr")]
        present = [(v, c) for v, c in pairs if v is not None]
        return max(present)[1] if present else None

    def _file_informational(self, call) -> None:
        """Put a colour or data call on the race's ledger.

        **The ledger was half a ledger.** After the Road Atlanta race on
        23 Aug 2026 it held fourteen calls; the app had spoken roughly twice
        that. Every instruction was there and every *number* was missing - the
        fuel in hand, the countdown to the box, the wear readings off the gauge
        - because the colour paths spoke straight to the voice and never filed.

        Those are precisely the calls a post-race audit needs. CLAUDE.md §5.5
        requires the record to carry the calls the engineer made and the
        assumptions behind them; "Fuel: 3.1 laps in hand" is the fuel model
        saying out loud what it believed, three laps from the flag, and losing
        it means the model can never be marked right or wrong afterwards.

        **This takes a `ColourCall`, which is not a `Call`.** It carries
        `kind`, `call` and `reason` and nothing else - no `lap`, no
        `confidence`, no `as_export`. The first version of this method assumed
        otherwise, and every filing raised `AttributeError` into a guard that
        swallowed it, so it wrote nothing at all. The payload is therefore
        built here rather than asked for.

        Filed with `informational: True` and `accepted=False`, the same shape
        the in-box refuel call uses, so `export/build.py::_disposition` reads
        these as informational rather than as offers the driver declined.
        """
        if self.race_run_id is None or self.race is None:
            return
        state = self.race.state
        if state.finished:
            # The flag has fallen. Anything after it belongs to no lap.
            return
        try:
            self.store.append_revision(
                self.race_run_id, state.lap, call.call,
                {"call": {"lap": state.lap, "call": call.call,
                          "reason": getattr(call, "reason", "") or "",
                          "confidence": "high"},
                 "confidence": "high",
                 "kind": getattr(call, "kind", "colour"),
                 "informational": True},
                accepted=False)
        except Exception as exc:                            # noqa: BLE001
            # **Never into the caller** - he has already heard the call, and a
            # ledger write must not cost him the next one. But it disarms
            # after the first failure, like every other guard on this path: a
            # fault here is permanent far more often than it is transient, and
            # the first version logged the same error every lap of a race
            # while writing nothing. Once, loudly, with a traceback.
            log("race").error(
                "colour calls are not reaching the ledger and filing has been "
                "stopped for this race - it will be short: %s: %s",
                type(exc).__name__, exc, exc_info=True)
            self._file_informational = lambda _call: None

    def _voice_colour(self, lap) -> None:
        """The radio for a quiet lap, or nothing - usually nothing."""
        race = self.race
        if race is None or not race.running or self._colour is None:
            return
        state = race.state
        sigma_ms = race.expect.sigma_ms()
        call = self._colour.consider(
            lap=state.lap,
            lap_time_ms=lap.lap_time_ms,
            laps_remaining=state.laps_remaining(),
            laps_total=state.laps_total,
            stint_ends_on_lap=state.stint_ends_on_lap,
            # Measured from the race in progress, never inherited - so it is
            # None until enough clean laps exist, and the consistency call
            # stays silent rather than inventing a band.
            sigma_s=(sigma_ms / 1000.0) if sigma_ms else None,
            # Laps on the current set. **No wear reading is captured live at
            # all**, which is exactly why the prompt is worth making: GT7
            # broadcasts no wear channel and he read the gauge zero times in
            # the Monza race.
            wear_reading_age=state.laps_since_stop,
            # GT7's own, off the packet - the run-in is the one place a
            # position is worth repeating every lap.
            position=state.position,
            # **Whether the lap count can be resolved at all.** A timed race's
            # distance is an output of the plan, and the count can sit inside
            # this car's own lap-time noise; the run-in then says "about three
            # to go" rather than quoting a figure it cannot stand behind.
            laps_firm=state.laps_estimate_firm or not state.race_minutes,
            # **The instrument read out, for chatty mode.** He asked for it:
            # "chatty mode still didn't talk to me enough and isn't keeping me
            # engaged. I love data." Every one of these is measured - the fuel
            # off the tank against this race's own burn, the wear off the
            # gauge. Nothing modelled goes in here, because a number said in a
            # relaxed register every lap is exactly the kind that stops
            # sounding like an estimate.
            fuel_laps_in_hand=self._laps_of_fuel_in_hand(state),
            wear_worst=self._worst_wear(lap),
            wear_corner=self._worst_wear_corner(lap),
            # **The straight speaks it now.** Ranked here it displaced a
            # finding on every lap it fired, and findings are rare where a
            # number is always available - so the rare thing lost every
            # collision. See `ColourCalls.data_line`.
            include_data=False,
        )
        if call is None:
            return
        spoken = call.spoken()
        if self._engineer_speaks:
            self.voice.say(spoken)
        self.ptt.last_call = spoken
        if self.race_screen is not None:
            self.race_screen.set_status(spoken)
        self._file_informational(call)

    def _tag_race_compound(self, lap_id: int) -> None:
        """A race lap's compound comes from the approved plan.

        **The compound is app state, not telemetry** - GT7 broadcasts no tyre
        code in any packet format - and in a race the app already knows it
        exactly: the plan names a compound per stint, and `_apply_stint`
        advances it at every pit exit as the stops are taken. Nothing was
        writing it down.

        The cost of not writing it down is that the race contributes nothing
        to the tyre model. Every one of the 26 laps of Monza on 18 Aug 2026
        landed with `compound` NULL, and so did the Watkins race the day
        before - the two hardest, most representative stints on record, both
        invisible to the compound profiles that size every stint of the next
        plan. Practice laps get tagged because the practice rack has a column
        he fills in by hand; a race has no rack and nobody to fill it in.

        Only where the plan actually named one. A re-plan adopted mid-race
        carries no compound and `_apply_stint` deliberately leaves the rubber
        on the car alone, so None here means nobody said - and a guessed
        compound would be worse than a missing one, because a wear rate
        attributed to the wrong tyre is not a gap in the model, it is a
        corruption of it.
        """
        race = self.race
        if race is None or not race.running:
            return
        compound = race.state.tyre_compound
        if compound:
            self.store.set_lap_compound(lap_id, compound)

    def _on_lap_changed(self, lap_id: int) -> None:
        """Persist a mark the moment it is made."""
        rows = self.practice.rows()
        row = next((r for r in rows if r.lap_id == lap_id), None)
        if row is None:
            return
        carried = carry_compound(rows, lap_id)
        for tagged in carried:
            self.store.set_lap_compound(tagged.lap_id, tagged.compound)
        # The carry mutated rows these widgets are holding. Nothing else
        # tells them, so a tagged stint stayed grey on screen while the
        # database had it right.
        if len(carried) > 1:
            self.practice.repaint_rows()
        self.store.set_lap_tyres_fresh(lap_id, row.tyres_fresh)
        self.store.set_lap_wear(lap_id, row.wear_fl, row.wear_fr,
                                row.wear_rl, row.wear_rr)
        self.store.exclude_lap(
            lap_id, "struck by hand" if row.excluded else None)

    @staticmethod
    def _column(row, name: str):
        return row[name] if name in row.keys() else None

    def _rows_for_event(self, event_id: int) -> list[LapRow]:
        """Every practice lap at this event, numbered continuously.

        The stored numbers restart at 1 each run, so two laps would both read
        "1" on the rack. Display numbering runs through the whole event; the
        database id is what every edit is written against, so renumbering the
        display cannot mis-file a mark.
        """
        stored = self.store.list_event_laps(event_id, "practice")
        rows = [
            LapRow(
                lap_id=row["id"],
                lap_num=index,
                lap_time_ms=row["lap_time_ms"],
                fuel_used=row["fuel_used"],
                fuel_start=row["fuel_start"],
                fuel_end=row["fuel_end"],
                tyres_fresh=(None if row["tyres_fresh"] is None
                             else bool(row["tyres_fresh"])),
                tyres_changed=(None if self._column(row, "tyres_changed") is None
                                else bool(row["tyres_changed"])),
                compound=row["compound"],
                is_out_lap=bool(row["is_out_lap"]),
                is_pit_lap=bool(row["is_pit_lap"]),
                excluded=bool(row["excluded"]),
                exclusion_reason=row["exclusion_reason"],
                wear_fl=row["wear_fl"],
                wear_fr=row["wear_fr"],
                wear_rl=row["wear_rl"],
                wear_rr=row["wear_rr"],
                session_id=row["session_id"],
                session_started=row["session_started"],
                practice_mode=self._column(row, "practice_mode"),
                lap_num_in_session=row["lap_num"],
                standing_start_ms=self._column(row, "standing_start_ms"),
                crawl_s=self._column(row, "crawl_s"),
                off_track_s=self._column(row, "off_track_s"),
                spin_s=self._column(row, "spin_s"),
                tod_start_ms=self._column(row, "tod_start_ms"),
                tod_end_ms=self._column(row, "tod_end_ms"),
            )
            for index, row in enumerate(stored, 1)
        ]

        # **The rack names the out-laps itself.** It must reach the same
        # answer as the export or a lap would read as counted on the screen
        # and be excluded in the payload, so the rule is imported rather than
        # restated - and it is the rule, not the stored flag, because the flag
        # is zero on every lap recorded before the app could see a pit stop.
        # A lap the live path already flagged keeps its flag either way.
        for row in rows:
            if row.lap_num in auto_out_laps(rows):
                row.is_out_lap = True

        # **And the fuel-implausible laps, for the same reason.** A lap
        # boundary landing inside a garage transition burns a twentieth of a
        # lap's fuel and, being short, was promoted to the rack's best - so the
        # screen read 1.9 s quicker than the payload on the owner's own Monza
        # session. The export strikes those laps through `classify_exclusions`;
        # the rack did not, and the two disagreed about the number he judges
        # every session by.
        capacity = self._event_fuel_capacity(event_id)
        # Handed to the rack because it applies this rule on every append as
        # well as on a rebuild - the floor is half the median burn and moves
        # as laps arrive, so it cannot be decided once here and left.
        self.practice.set_fuel_capacity(capacity)
        for lap_num in fuel_implausible_laps(rows, capacity):
            for row in rows:
                if row.lap_num == lap_num and not row.excluded:
                    row.excluded = True
                    row.exclusion_reason = REASON_FUEL_IMPLAUSIBLE

        # Incidents after the out-laps, because an out-lap loses time it is
        # supposed to lose and must not be judged for it. Answered from the
        # three stored numbers, so no frame blob is decoded to draw the rack.
        for lap_num, incident in find_incidents(rows, stored_or_read).items():
            for row in rows:
                if row.lap_num == lap_num:
                    row.incident = True
                    row.incident_note = incident.describe()
        return rows

    def _event_fuel_capacity(self, event_id: int) -> float | None:
        """The tank this event ran, or None if no session saw a plausible one.

        First *plausible*, not first non-null: a session that opened before the
        car was loaded stores 0.0, and 0 is a real capacity meaning electric -
        which switches the fuel-plausibility test off for the whole event.

        **A second copy of this method was added on 22 Aug 2026 and shadowed
        this one**, taking the event dict rather than its id and returning the
        first NON-NULL capacity. Python keeps the later definition, so the new
        one was dead and the new caller - the qualifying plan - handed a dict
        to `list_sessions`, which is `ProgrammingError: Error binding
        parameter 1: type 'dict' is not supported`. The qualifying-plan button
        raised every time it was pressed.

        Its argument was CLAUDE.md rule 3, that a 0 which means "not measured"
        must not be confused with a real 0, and in principle that is right.
        It loses on this data: the live database holds three sessions at 0.0
        against sixty-three at 100.0, the car is a Porsche 911 RSR, and an RSR
        is not electric - so every 0.0 on file is the "opened before the car
        loaded" artefact this rule was written for. If an electric car is ever
        raced, the fix is to stop writing 0.0 for an unloaded car, not to
        start believing it here.
        """
        for session in self.store.list_sessions(event_id, "practice"):
            capacity = session["fuel_capacity_l"]
            if capacity:
                return float(capacity)
        return None







    # -------------------------------------------------------------- strategy

    def build_strategy(self) -> list:
        """Plan the race from what practice actually measured."""
        if self.strategy is None:
            return []
        event = self.active_event()
        if event is None:
            self.strategy.set_status(
                "Create an event first - a plan needs a race to plan for.",
                warn=True)
            return []

        inputs, evidence = build_inputs(self.store, event["id"])
        self._inputs = inputs
        # **Shown before the optimiser runs, and whatever it returns.** A plan
        # loaded from the desk does not depend on the app being able to build
        # one of its own - and `recommend` refusing is exactly when a loaded
        # plan matters most.
        self._show_loaded_plans(event["id"])
        try:
            plans = recommend(inputs)
        except StrategyImpossible as exc:
            # Refusing beats inventing a plan the driver would race to.
            self._plans = []
            self.strategy.show_plans([], evidence, timed=inputs.is_timed)
            self.strategy.set_status(str(exc), warn=True)
            return []

        self._plans = plans
        self._plans_event_id = event["id"]
        approved = self.store.get_approved_strategy(event["id"])
        approved_index = None
        if approved:
            # A plan is identified by its stops *and* its compounds. Several
            # plans now share a stop count on different rubber, and matching
            # on stops alone would re-select whichever came first - silently
            # putting the car on a compound he did not approve.
            stored = approved["plan"]
            want_stops = stored.get("stops")
            want_compounds = [s.get("compound")
                              for s in stored.get("stints") or []]
            approved_index = next(
                (i for i, plan in enumerate(plans)
                 if plan.stops == want_stops
                 and list(plan.compounds) == want_compounds), None)
            if approved_index is None:
                # The compounds no longer line up - the evidence moved under
                # the plan. Fall back to the stop count so something sensible
                # is selected, rather than nothing.
                approved_index = next(
                    (i for i, plan in enumerate(plans)
                     if plan.stops == want_stops), None)

        self.strategy.show_plans(plans, evidence, approved_index=approved_index,
                                 timed=inputs.is_timed)
        gaps = inputs.missing()
        if gaps:
            self.strategy.note(
                "Planned without " + ", ".join(gaps)
                + ". Fill those in and rebuild before racing to this.",
                warn=True)
        else:
            self.strategy.note("Every input measured.")
        return plans

    def _show_loaded_plans(self, event_id: int) -> None:
        """Put the plans somebody else wrote on the screen.

        A stored candidate carrying a `handover` was written outside the app -
        by the race engineer at the desk - and until now it was visible to
        nobody: the screen rendered `recommend()`'s output and nothing else,
        and approval took an index into that list. Fuji is the cost. Ludo's
        one-stop plan certified clean and could not be chosen, because the
        optimiser would not offer a fifteen-lap stint against an evidence cap
        of six and there was no other way in.
        """
        if self.strategy is None:
            return
        rows = [row for row in self.store.list_strategies(event_id)
                if (row.get("plan") or {}).get("handover")]
        self.strategy.show_loaded(rows)

    def _forget_plans(self) -> None:
        """Drop plans built for the event we are leaving.

        `self._plans` was only ever written by `build_strategy`, and nothing
        cleared it, so switching events left the previous event's cards on the
        Strategy screen with Approve still enabled.  Approve reads the plan out
        of `_plans` but takes the event and the guard context from
        `active_event()` - so it filed one event's stints, pit laps and payload
        against another, stamped with the new event's car and track, and the
        race-day guard then agreed with itself and passed.
        """
        self._plans = []
        self._inputs = None
        self._plans_event_id = None
        if self.strategy is not None:
            # **The loaded cards go with them.** They are another event's
            # plans the moment the event changes, and this method exists
            # because leaving the previous event's cards on screen with
            # Approve enabled was a defect - reintroduced for the new list.
            self.strategy.show_loaded([])
            self.strategy.show_plans([], [], timed=False)
            self.strategy.set_status("Build a plan for this event.")

    def _short_shift_slope(self) -> float | None:
        """Litres per lap per 1000 rpm for the car on the stream, or None.

        None is the honest answer for a car nobody has fitted, and the fuel
        call handles it by naming the lever without a number. Guessing here -
        borrowing another car's slope, or averaging - would put a fabricated
        conversion behind an instruction spoken as a measurement.
        """
        car_id = getattr(self.bridge, "_car_id", None)
        if car_id is None:
            return None
        table = getattr(self.settings, "short_shift_litres_per_1000rpm", None)
        if not table:
            return None
        value = table.get(str(car_id))
        return float(value) if value else None

    def _race_context(self, event) -> PlanContext:
        """What this race actually is, in the units the race layer expects.

        `events.race_laps` holds **minutes** when the format is timed - the
        spin box is relabelled and saved into the same column - so reading it
        as a distance raced a 45-minute Monza as a 45-lap one: "40 to go" with
        19 left, and a fuel call short by the difference. The strategy path
        already made this distinction; the live path did not.
        """
        timed = (event["race_type"] or "") == "time"
        figure = float(event["race_laps"] or 0)
        return PlanContext(
            car=event["car_name"] or "", track=event["track"] or "",
            layout=event["layout"],
            race_laps=0 if timed else int(figure),
            race_minutes=figure if timed else None)

    def approve_strategy(self, index: int) -> int | None:
        if self.strategy is None or not self._plans:
            return None
        event = self.active_event()
        if event is None or index >= len(self._plans):
            return None

        plan = self._plans[index]
        payload = plan.as_dict()
        payload["export"] = plan.as_export(self._inputs)
        # **The plan carries the two numbers it expects to execute, and what it
        # was built for.** Both blocks come from `strategy.execution.stamp`,
        # which is the one implementation of them - the app's optimiser is no
        # longer the only author, and a plan from the desk that arrived without
        # them armed and then ran blind, every per-lap comparison reporting
        # nothing rather than reporting a problem. `inputs` and `event` are
        # handed in because this caller already has them: without them `stamp`
        # rebuilds `build_inputs`, which walks every practice lap, on the Qt
        # thread at every plan approval.
        payload = stamp(self.store, event["id"], payload,
                        inputs=self._inputs, event=event)
        strategy_id = self.store.save_strategy(
            event["id"], payload, label=plan.label(),
            evidence={"missing": self._inputs.missing()})
        self.store.approve_strategy(strategy_id)
        self.strategy.note(
            f"{plan.label()} approved. It is the race plan until you approve "
            "another.")
        # The Race screen's Strategy choice is about this plan, so it has to
        # hear that one now exists - otherwise approving a plan and going
        # straight to Race offers a control still saying there is nothing to
        # run to.
        self._refresh_race_options(event)
        self.refresh_nav_state()
        return strategy_id

    def approve_stored_strategy(self, strategy_id: int) -> bool:
        """Approve a plan already in the store, whoever wrote it.

        **The other approval path can only approve the app's own work.**
        `approve_strategy` takes an INDEX into `self._plans`, which is
        `recommend()`'s output and nothing else, so a plan authored at the desk
        could be stored and certified and then had no route to the grid at all
        - it was visible to nobody and approvable by nothing.

        Certified here and not merely on the way in. A candidate can be days
        old: the tyre evidence behind it, the compounds declared for the event
        and the race distance itself can all have moved since, and the plan
        that was driveable when it was written may not be driveable now.
        `start_race` certifies once more against the evidence of the moment,
        which is the last gate; this is the one that stops an undriveable plan
        wearing the word "approved" on the Race screen in the meantime.
        """
        event = self.active_event()
        if event is None:
            return False
        row = next((s for s in self.store.list_strategies(event["id"])
                    if s["id"] == strategy_id), None)
        if row is None:
            if self.strategy is not None:
                self.strategy.set_status(
                    "That plan is not on file for this event.", warn=True)
            return False

        certificate = certify_for_event(self.store, event["id"], row["plan"])
        if not certificate.certified:
            if self.strategy is not None:
                self.strategy.set_status(
                    f"Not approved. {certificate.describe()}", warn=True)
            log("strategy").warning("refused %r: %s", row["label"],
                                    "; ".join(certificate.refusals))
            return False

        self.store.approve_strategy(strategy_id)
        # **The accepts are logged too, not only the refusals** - CLAUDE.md
        # rule 10. A log that only ever records refusals cannot answer "which
        # plan was armed", which is the first question a debrief asks.
        log("strategy").info("approved %r (id %d): %s", row["label"],
                             strategy_id, certificate.describe())
        if self.strategy is not None:
            self.strategy.note(
                f"{row['label'] or 'That plan'} approved. It is the race plan "
                f"until you approve another."
                + (" " + certificate.describe() if certificate.warnings
                   or certificate.unchecked else ""))
        self._refresh_race_options(event)
        self.refresh_nav_state()
        return True

    # ------------------------------------------------------------------ race

    def start_race(self) -> bool:
        """Arm the race. Nothing fires until the car actually goes green."""
        if self.race_screen is None:
            return False
        event = self.active_event()
        if event is None:
            self.race_screen.set_status(
                "Create an event before racing.", warn=True)
            return False

        # **Three choices, all his.** Whether this is the league race or a
        # rehearsal, whether the engineer speaks, and whether it runs to the
        # approved plan at all. Running without the plan is how you find out
        # what the plan is worth; running silent is how you find out whether
        # you reach the same decisions it does.
        rehearsal = self.race_screen.rehearsal()
        speaks = self.race_screen.engineer_speaks()
        approved = self.store.get_approved_strategy(event["id"])
        if not self.race_screen.use_plan():
            approved = None
        plan = approved["plan"] if approved else None
        try:
            inputs, _ = build_inputs(self.store, event["id"])
        except ValueError:
            inputs = None

        # **The last gate, and it is here because this is the last moment.**
        # A plan the app's own optimiser built is feasible by construction, but
        # a plan can also arrive from the race engineer the driver is talking
        # to, and prose cannot be trusted to have done arithmetic. The 12 Aug
        # audit is what that costs: the app ranked the most impossible plan
        # cheapest and asked for 510 litres of fuel into a 100 litre tank.
        #
        # Refused rather than warned about. A plan that cannot be executed is
        # not a plan with a caveat.
        if plan is not None and inputs is not None:
            certificate = certify(plan, inputs)
            if not certificate.certified:
                self.race_screen.set_status(
                    f"Plan refused: {certificate.describe()}", warn=True)
                return False
            for warning in certificate.warnings:
                log("race").warning("approved plan: %s", warning)
            for gap in certificate.unchecked:
                log("race").info("approved plan, not checked: %s", gap)

        # How many practice laps stand behind the two figures the plan
        # expects to execute. Every aggregate carries its sample count
        # (CLAUDE.md §4.4): a burn from three laps and one from fourteen are
        # not the same claim, and the driver is about to be told one of them.
        # `hydrate=set()`: this is a COUNT. The default decodes every
        # practice lap's telemetry to produce one integer - 2.5 s on the
        # active event and 9.4 s on the largest, against 1.0 ms, and on the
        # Qt thread at every race start and plan approval.
        practice_laps = len(counted_laps(
            event_lap_inputs(self.store, event["id"], "practice",
                             hydrate=set())))
        # What the plan expects to execute, as stored when it was approved.
        expects = (plan or {}).get("expects") or {}
        self.race = RaceCoordinator(
            plan,
            fuel_per_lap_l=inputs.fuel_per_lap_l if inputs else None,
            # The lap-to-lap spread behind that burn, which is what sizes the
            # fill at every stop. See `strategy.model.fuel_margin_l`.
            fuel_sd_l=inputs.fuel_sd_l if inputs else None,
            wear_per_lap=inputs.wear_per_lap if inputs else None,
            fuel_capacity_l=inputs.fuel_capacity_l if inputs else None,
            # Keyed by the car the stream is showing, which `on_packet` has
            # already learned. Missing is the normal state for a car whose
            # short-shift trade nobody has fitted yet.
            short_shift_l_per_1000rpm=self._short_shift_slope(),
            # What the plan was built to run: the practice median lap and the
            # practice burn. The race is compared against these every lap.
            lap_time_ms=inputs.lap_time_ms if inputs else None,
            # **The reference comes off the approved plan, not off today's
            # evidence.** `expects` was stamped when he approved it; anything
            # driven since then changes what the app would plan now, not what
            # this plan is. Reading the fresh figure instead is how "burning
            # 8% under plan" was said against a burn no plan ever held.
            planned_fuel_per_lap_l=expects.get("expected_fuel_per_lap_l"),
            planned_lap_time_ms=expects.get("expected_lap_time_ms"),
            # **A track constant, measured once** (CLAUDE.md 5.4). Read by the
            # fuel path only, to keep a stop's own minute of clock out of the
            # distance the next fill is sized against.
            pit_loss_s=event.get("pit_loss_secs"),
            # **The source, not just the value.** The column carries a
            # `NOT NULL DEFAULT 20.0`, so the figure alone cannot say
            # whether anyone ever measured a stop here.
            pit_loss_measured=(event.get("pit_loss_source")
                               == "measured"),
            # **Litres a second at the pump.** Every pit-lane call prices a
            # stop with it, and without it `rival_boxed` and `rejoin_call`
            # refuse rather than assume a rate.
            refuel_rate_lps=event.get("refuel_rate_lps"),
            # **The regulations, which never reached here.** `_note_mandatory_
            # stops`' own docstring says a rule that cannot fire is the thing
            # this codebase keeps building by accident - and the only caller
            # passing this was a hand-run tool, so `mandatory_stops_left` was
            # 0 in every race and `stop_still_needed` short-circuited past the
            # regulation test forever. George would cancel a stop the rules
            # require, and say so.
            mandatory_stops=int(event.get("mandatory_stops") or 0),
            practice_lap_samples=practice_laps,
            practice_fuel_samples=practice_laps,
            # **Ludo's briefing for this circuit**, or None where nobody wrote
            # one. It is the only route by which anything George cannot derive
            # enters a race - no model runs in the live loop, so everything
            # clever is precomputed. Absent is a state he announces at the
            # green, never one he papers over.
            knowledge=knowledge.for_event(self.store, event))
        # Set here rather than inside the coordinator so a state built by hand
        # in a test is not a claim that the briefing is missing.
        self.race.state.no_notes = self.race.knowledge is None
        # **The interval he asked for, reaching the race.** Built, tested, and
        # settable only from a test file until now - CLAUDE.md rule 11's named
        # failure, and the fourth instance of it found in this codebase this
        # week. He races with the GT7 race HUD off, so lap, position and time
        # remaining exist nowhere but here.
        self.race.state.status_every_laps = max(
            1, int(self.settings.status_every_laps or STATUS_EVERY_LAPS))

        actual = self._race_context(event)
        stored = (plan or {}).get("context")
        # **`context_from_stored`, not `PlanContext(**stored)`.** It was
        # written for this call site, its docstring says so, and it was reached
        # only from a test file - the same shape of defect as every other
        # "exists, documented, never called" in this codebase. Splatting a
        # stored dict raises `TypeError` on any key the dataclass does not
        # declare, on the grid, with nothing catching it; and a context saved
        # with the minutes in `race_laps` reads as a lap race and gets a valid
        # timed plan refused on race day.
        planned = context_from_stored(stored, event) if stored else None
        if not self.race.arm(planned, actual):
            self.race_screen.set_status(
                f"Plan refused: {self.race.refusal}", warn=True)
            self.race = None
            return False

        # **Declare the instrument, once, on the grid.** Silence is this
        # app's most-used output and it has never meant one thing - no plan,
        # no wear evidence, no resolvable lap count and nothing to report all
        # sound identical. Nothing competes for the channel here.
        # **The league is opened BEFORE the brief, because the brief reads
        # it.** Opened after, `_league_line()` found last race's league still
        # loaded - so the first race of a session got no championship line at
        # all, and every race after it was told where it stood in the league it
        # had raced PREVIOUSLY. Wrong is worse than absent here: he would act
        # on a title margin belonging to another championship.
        self._open_the_league(event)
        self._say_brief(event, plan, speaks=speaks)

        self.bridge.reset(race=True)
        # **The race records the sheet it was run on, exactly as practice
        # does.** It did not, and that is the most expensive omission in the
        # loop: with no `setup_sheet_id` the export reports the *event's* v1
        # sheet as the setup as run, so the Watkins race post-mortem described
        # the low car with the trimmed rear wing - precisely the setup Rev C
        # had been written to replace. Every delta and every ranked cost would
        # have been computed against a car that was not on the circuit, and
        # coherently enough that nothing would have looked wrong.
        #
        # It cascades further than the setup block. `laps.compound` comes off
        # the sheet, so all twenty race laps landed with a null compound and
        # sixteen fit-eligible laps sat outside the RS tyre model entirely;
        # `fuelMap` went null for the same reason; and `gearingConstantK`,
        # which prefers the sheet's final drive and only falls back to the
        # derived one, fell back - and the derived figure reads high through
        # the unloaded tyre radius, which the payload's own note says.
        #
        # Same rule as practice, and the same refusal: where the car has one
        # sheet that is the sheet, where a race sheet exists it is that, and
        # where neither holds the session records NO sheet rather than a
        # plausible wrong one. A named sheet he was not running is worse than
        # none, because the export presents it as the setup as run.
        here = circuit_key_for(event)
        sheet = self.store.sheet_for(event["car_name"] or "", "race", here)
        if sheet is None:
            # The one-sheet rule holds within a circuit and breaks across one.
            sheets = [x for x in self.store.list_setup_sheets(
                event["car_name"] or "") if x.circuit_key == here]
            sheet = sheets[0] if len(sheets) == 1 else None
            if sheet is None and self.store.list_setup_sheets(
                    event["car_name"] or ""):
                sheets = self.store.list_setup_sheets(event["car_name"] or "")
                self.race_screen.set_status(
                    f"No race sheet on file for this car at this circuit, and "
                    f"it has {len(sheets)} elsewhere - this race is recorded without "
                    f"one, so its laps carry no compound and the export "
                    f"cannot say what was on the car. Load the race sheet on "
                    f"the Event screen.", warn=True)
        self.bridge.set_sheet_shift_rpm(sheet.shift_rpm if sheet else None)
        self.session_id = self.store.start_session(
            event["id"], "race", setup_sheet_id=sheet.id if sheet else None,
            rehearsal=rehearsal, game_version=self.settings.game_version)
        self.session_kind = "race"
        self._tell_settings_about_the_session()
        # **Every change is an experiment, and this is where it is filed.**
        # The session that opens against a different sheet from the last one on
        # this car and circuit IS the run that tests the difference. Recorded
        # here rather than asked for later, because a ledger that depends on
        # somebody remembering is the ledger that held zero rows for 88
        # sessions. Silent and harmless when nothing changed.
        self._note_sheet_change()

        self.race_run_id = self.store.start_race_run(
            event["id"], approved["id"] if approved else None, self.session_id)

        # **The race is the session most worth having on video, and it was the
        # only kind that never was.** `_start_video` had one call site, in
        # `start_practice`, so every practice on 24 Aug 2026 was recorded and
        # the race was not - and no session with `kind='race'` has a
        # `video_path` anywhere in the database's history. It matters more than
        # a missing convenience: the HUD wear gauge is read off the OBS frame,
        # the live reader accepted nothing at all that race, and `hud-video` on
        # a recording is the only route that produced a usable wear reading all
        # weekend. Same placement as in `start_practice` - after the session
        # row exists, before any lap can land against it.
        self._start_video()
        self._new_hud_session()

        self.listener = UDPListener(
            "0.0.0.0", self.feed_port, self.bridge.on_packet,
            source_ip=self.settings.udp_source_ip,
            heartbeat_to=self.heartbeat_target)
        self.listener.start()
        self._health.start()
        self.start_haptics()
        self.start_wind()

        # Silent means silent, not idle: the calls are still computed, still
        # shown on the screen and still written into the outcome export. What
        # stops is the voice and the microphone - there is nothing to answer
        # if nothing was asked out loud.
        self._engineer_speaks = speaks
        if speaks:
            self.voice.warm()
            self.ptt.start()
        self._race_inputs = inputs
        self._race_burns = []
        # A fresh watch per race. Reset again on every pit exit, so a
        # two-stop race gets a clean one for its second stop.
        self.bridge.refuel = RefuelAdviser(
            context=self._refuel_context, speak=self._voice_refuel)
        # The same coordinator the event path drives, read at 60 Hz for one
        # question only: has GT7 counted a crossing the app did not.
        self.bridge.lap_watch = self.race
        # **Armed with the race, not with the session.** A practice lap with a
        # spin in it is judged afterwards by `analysis/incidents.py`, which can
        # see the whole lap and all three of its signals; this exists only for
        # the one case where the verdict has to be reached before the lap is
        # over, which is a race being planned around.
        self.bridge.incidents = IncidentWatch()
        self._colour = ColourCalls(level=self.settings.colour_calls)
        self._replan_max_stops = REPLAN_MAX_STOPS
        self._replan_over_budget = 0
        self._replans.reset()
        self.ptt.pending_replan = None
        # The measured tyre-temperature window for this event, decoded once
        # from its practice laps. None where nothing was measured - the
        # temperature voice then stays silent rather than judging against
        # the strategy layer's fabricated band.
        window = measured_temp_window(self.store, event["id"])
        if window is not None:
            self.race.state.temp_window_front = window.front
            self.race.state.temp_window_rear = window.rear
            self.race.state.temp_laps_to_window = window.laps_to_window
        # The app race clock needs to see the paused frames, and only the
        # telemetry thread does: `SessionState.update` returns early on a
        # pause and produces no events at all, so nothing else downstream can
        # tell that the race stopped. One arithmetic call per frame.
        self.bridge.race_clock = self.race.clock
        self.race_screen.clear_log()
        self.race_screen.set_armed(True)
        # **Started here, on the grid, not at the green.** The pit columns are
        # drawn only while a car is standing in its box, so a watcher that
        # starts late does not get a late reading - it gets none at all, and
        # there is no later question that recovers one. Armed is the last
        # moment that is certainly before anybody stops.
        self._start_pit_wall()

        how = "Rehearsal armed" if rehearsal else "Armed"
        parts = [
            "running to the approved plan" if plan else
            "no plan - fuel calls only",
            "engineer speaking" if speaks else
            "engineer silent, still logging every call",
        ]
        self.race_screen.set_status(
            f"{how}: {', '.join(parts)}. Waiting for you to cross the line.")
        self.announce("Rehearsal" if rehearsal else "Race",
                      " · ".join(parts), warn=not plan)
        return True

    # ---------------------------------------------------------- the pit wall

    def _start_pit_wall(self) -> None:
        """Watch the leaderboard for the rest of this race.

        **Seeded from the archive, and that is the whole point of the book.**
        `drivers.exemplar` carries a name bitmap from every race already
        watched, so tonight's rows attach to the same drivers as last month's
        rather than founding an anonymous roster that dies at the flag.

        Built fresh per race. CLAUDE.md rule 11: the visits, the positions and
        the latched pit flags all describe one race, and a race that opens
        holding the last one's is a race that reports it. The ROSTER is the
        exception and is deliberately carried, because driver identity is the
        one thing that should cross a session boundary.
        """
        if self.hud is None:
            return
        # **Last race's wall is stopped before this one's is built.** Armed
        # twice without a `stop_race` between - a rehearsal then the race - the
        # old wall stayed live, so `_on_the_grid()` answered with the PREVIOUS
        # race's field and every position in it. Rule 11, in the one place
        # this feature claimed to have closed it.
        if getattr(self, "_pit_wall", None) is not None:
            self._stop_pit_wall()
        # **Refused loudly rather than started blind.** The wall sees only the
        # frames the wear sampler grabs. With the gauge off none are grabbed at
        # all; with `hud_sample_interval_s` at 0 one is grabbed per crossing,
        # and a 90-second stop then yields a single reading against the two a
        # stop needs - so every stop is discarded and the driver is told
        # nothing, which is indistinguishable from a race in which nobody
        # pitted.
        if not self.settings.hud_wear_enabled:
            log("pitcrew").warning(
                "pit-wall: not watching - the tyre gauge is off, and the wall "
                "sees only the frames it grabs.")
            return
        interval = float(self.settings.hud_sample_interval_s or 0.0)
        if interval <= 0 or interval > 5.0:
            log("pitcrew").warning(
                "pit-wall: not watching - the gauge samples %s, which is too "
                "slow to catch a pit stop. Set a sampling interval of a "
                "second or two.",
                "only at each crossing" if interval <= 0
                else f"every {interval:g}s")
            return
        try:
            from pitcrew.race.pit_wall import PitWall
            from pitcrew.telemetry.roster import Roster

            from pitcrew.race.lap_ruler import LapRuler

            self._lap_ruler = LapRuler(
                circuit_length_m=self._circuit_length_m())
            seed = self.store.driver_exemplars()
            self._last_session_id = self.session_id
            self._pit_wall = PitWall(Roster(seed=seed),
                                     on_stop=self._on_rival_stop,
                                     on_enter=self._on_rival_enter,
                                     name_for=self.store.provisional_driver_name,
                                     where_on_lap=self._where_on_lap)
            self.hud.watch_board(self._pit_wall, lap_of=self._our_lap)
            log("pitcrew").info(
                "pit-wall: watching, seeded with %d known driver%s",
                len(seed), "" if len(seed) == 1 else "s")
        except Exception:
            # Never the race path. A pit wall that cannot start is a pit wall
            # the driver races without, exactly as he did before it existed.
            log("pitcrew").exception("pit-wall: could not start")
            self._pit_wall = None

    # ---------------------------------------------------------- the league

    def _open_the_league(self, event: dict) -> None:
        """Work out which championship this race is a round of.

        **Never a guess.** The league is matched from the event's own series
        name, or from the car when that is unambiguous, and otherwise there is
        no league - because a race matched to the wrong one would compute a
        title from somebody else's points, which is worse than computing none.

        Everything here is optional and guarded. The app raced for months with
        no hub at all and must go on doing so when it is not there.
        """
        self._league = None
        self._league_place: int | None = None
        try:
            from pitcrew.hub.link import league_for
            from pitcrew.hub.read import Hub

            me = self.store.driver_name()
            if not me:
                log("race").info(
                    "league: skipped - no driver name is set, so there is "
                    "nobody to look up on the hub. "
                    "python -m tools.name_drivers --me \"<your hub name>\"")
                return
            hub = Hub()
            try:
                league = league_for(hub, event, me)
            finally:
                hub.close()
            if not league.known:
                # **A refusal is a finding and gets said.** A league Pit Crew
                # declines to score - a multi-class round, an unreadable points
                # table - is indistinguishable in the log from no league at
                # all, and the two want opposite responses from whoever reads
                # it afterwards.
                if getattr(league, "refused", ""):
                    log("race").info("league: %s", league.refused)
                return
            self._league = league
            log("race").info(
                "league: %s, matched by %s, %d rounds left, %s",
                league.series_name, league.matched_by, league.rounds_left,
                league.taken_at)
        except Exception:
            log("race").exception("the league could not be read")
            self._league = None

    def _league_line(self) -> str | None:
        """One sentence for the grid, or `None` when there is no league.

        The hub's age is on it whenever the hub is stale. "P5 secures it" and
        "P5 secured it as of Tuesday" are different claims, and a championship
        moves every round - so a copy older than a round is quoted with its
        date rather than as fact.
        """
        league = getattr(self, "_league", None)
        if league is None or not league.known:
            return None
        try:
            from pitcrew.hub.link import before_the_start

            me = self.store.driver_name()
            if not me:
                return None
            math = before_the_start(league, me, on_the_grid=self._on_the_grid())
            if math is None:
                return None
            said = math.to_say()
            if not said:
                # **Said, because it is a finding and not an absence.** This is
                # the state that used to announce a false championship: the
                # league matched and the driver was not in its table. Silent,
                # it is indistinguishable from having no league at all, and the
                # two want opposite responses from whoever reads the log.
                log("race").info(
                    "league: %s matched, but %r is not in its standings - "
                    "no championship line. Check the name against the hub.",
                    league.series_name, me)
                return None
            # **Only name rivals we have some reason to think are here.**
            # Unnarrowed, this was the top three of a 26-name championship,
            # none of whom need be in tonight's race - and defending a title
            # against a driver who is not on the circuit costs the race that
            # is. `rivals_from` is empty when nothing narrowed the list, and
            # then the clause is simply not said.
            if math.live_rivals and math.rivals_from:
                said += " Watch " + ", ".join(math.live_rivals[:3])
                said += (" - entered, not yet seen."
                         if math.rivals_from == "the entry list" else ".")
            if league.stale:
                said += f" ({league.taken_at})"
            return said
        except Exception:
            log("race").exception("the league line could not be composed")
            return None

    def _on_the_grid(self) -> list:
        """Everyone the leaderboard reader has recognised so far."""
        wall = getattr(self, "_pit_wall", None)
        if wall is None:
            return []
        try:
            return [name for _, name in wall.named() if name]
        except Exception:
            return []

    def _league_moved(self) -> str | None:
        """The championship position if the race ended now, when it CHANGES.

        Said on a change and not otherwise. A projection recomputed every lap
        is a number that moves constantly and means little; the fact worth
        hearing is that it has moved - "P4 now, he is out" - and only then.
        """
        league = getattr(self, "_league", None)
        if league is None or not league.known:
            return None
        try:
            from pitcrew.hub.link import where_we_would_be

            me = self.store.driver_name()
            if not me:
                return None
            wall = getattr(self, "_pit_wall", None)
            rivals = wall.positions() if wall is not None else {}
            ours = rivals.pop(me, None) or self._our_race_position()
            where = where_we_would_be(league, me, ours, rivals)
            if where is None or where == getattr(self, "_league_place", None):
                return None
            was, self._league_place = getattr(self, "_league_place", None), where
            if was is None:
                return None            # the first reading is not a change
            return (f"Championship {where} if it ends here."
                    if where < was else
                    f"Down to championship {where} if it ends here.")
        except Exception:
            log("race").exception("the league projection failed")
            return None

    def _our_race_position(self) -> int | None:
        race = self.race
        try:
            return int(race.state.position) if race is not None else None
        except Exception:
            return None

    def _circuit_length_m(self) -> float | None:
        """The circuit's own length, for judging whether a lap measured it."""
        try:
            event = self.active_event()
            if not event:
                return None
            layout = self.store.track_layout_for(event) if hasattr(
                self.store, "track_layout_for") else None
            if layout:
                return float(layout.get("length_m") or 0.0) or None
        except Exception:
            return None
        return None

    def _where_on_lap(self) -> float | None:
        """Metres round the lap, or `None` where the ruler cannot say.

        Worker thread. `None` rather than a stale figure: a sector boundary
        placed with a distance that has already lost packets is somewhere else
        on the road, which is worse than no boundary.
        """
        ruler = getattr(self, "_lap_ruler", None)
        if ruler is None:
            return None
        try:
            return ruler.where()
        except Exception:
            return None

    def _our_lap(self) -> int | None:
        """Our current lap, for attributing a rival's stop. Worker thread.

        **Ours, not his**, and the column it is stored in says so. A rival's
        own lap count is not on screen; what is knowable is which of our laps
        we were on when he came in, and on the same lead lap those are within
        one of each other. `state.lap` is the app's count and can be short of
        GT7's - see `calls.RaceState.lap` - which is another reason this is a
        reference rather than a measurement of his race.
        """
        race = self.race
        try:
            # `lap_now()`, not `state.lap`. The raw counter is documented as
            # systematically short - GT7 sat +1 above it on lap 1 at Road
            # Atlanta and +2 by lap 20 - and this number divides a rival's fuel
            # to give his burn rate. A two-lap deficit at lap 20 inflates that
            # by 10%, five times the 0.4 L/lap at which the engineer starts
            # telling the driver a rival uses more fuel than he does.
            return int(race.state.lap_now()) if race is not None else None
        except Exception:
            return None

    def _on_rival_stop(self, seen) -> None:  # noqa: D401
        """Worker thread. A rival has finished a stop: file it and say it.

        Filing happens here rather than at the flag because the watcher can
        only see a stop while it is happening - there is no later question that
        recovers it - and a race that crashes at lap 18 should still have the
        stops it watched at lap 11.
        """
        # **The session id is read once, here, and a stop with none is still
        # filed.** The worker can arrive after `stop_race` has cleared it, and
        # `rival_book.profile_of` maps a null session to the literal race key
        # "unknown" - so two races' stops would collapse into one and
        # `races_seen` would under-report, which is rule 4's whole point.
        session = self.session_id or getattr(self, "_last_session_id", None)
        # Save the bitmap with the name at the same moment, so a handle issued
        # mid-race can find the same driver in the next one.
        wall = getattr(self, "_pit_wall", None)
        if wall is not None and seen.driver:
            try:
                self.store.save_driver(seen.driver,
                                       wall.roster.exemplar_of(seen.driver_id))
            except Exception:
                log("pitcrew").exception("pit-wall: could not save a driver")
        try:
            from pitcrew.race import rival_book

            rival_book.record(self.store, session, seen,
                              laps_total=self._planned_laps())
        except Exception:
            log("pitcrew").exception("pit-wall: stop not filed")
        try:
            self.bridge.rival_stopped.emit(seen)
        except Exception:
            pass

    def _on_rival_enter(self, entered) -> None:  # noqa: D401
        """Worker thread. A rival is standing in his box; say so while he is.

        Nothing is filed here - an entry is not a stop, and the book records
        stops. It exists only to be spoken, and it is only worth speaking
        while he is still in there.
        """
        try:
            self.bridge.rival_entered.emit(entered)
        except Exception:
            pass

    def _rival_entry_seen(self, entered) -> None:
        """Qt thread: hand the entry to the coordinator."""
        race = self.race
        if race is None or entered is None:
            return
        try:
            race.note_rival_entered(entered)
        except Exception:
            log("race").exception("a rival's entry could not be noted")

    def _rival_stop_filed(self, seen) -> None:
        """Qt thread. Hand a watched stop to the coordinator so it can speak.

        Queued from `_on_rival_stop`, which runs on the sampler's worker
        thread: `RaceState.rivals` is read on every crossing, and a dict
        written from two threads is the defect the roster had.

        **His own burn where the book has watched him**, ours only as a stated
        fallback inside the calls. `profile.py` puts 0.4 L/lap outside reading
        error, which over a dozen remaining laps is five litres - enough on its
        own to invent a shortfall that is not there.
        """
        race = self.race
        if race is None or seen is None:
            log("race").info(
                "rival stop not filed: %s",
                "no race is armed" if seen is not None else "nothing was sent")
            return
        burn, stops = None, 0
        try:
            from pitcrew.race import rival_book

            # **Scoped to the car, because litres a lap is a property of the
            # CAR.** He races several leagues at once and a Gr.3 burn averaged
            # with a Gr.4 one describes neither. `burn_per_lap_l` returns the
            # figure with the stops behind it - rule 4 - and `None, 0` where
            # there is nothing on file for this car.
            burn, stops = rival_book.profile_of(
                self.store, seen.driver).burn_per_lap_l(
                    getattr(self.bridge, "_car_name", None))
            if not stops:
                burn = None
        except Exception:
            # A rival with no burn on file is not a rival who burns nothing.
            # The calls fall back to ours and say that they have.
            burn = None
        try:
            race.note_rival_stop(seen, burn_per_lap_l=burn,
                                 burn_stops=stops or 0)
        except Exception:
            log("race").exception("a rival's stop could not be filed")

    def _planned_laps(self) -> int | None:
        race = self.race
        try:
            return int(race.state.laps_total) if race is not None else None
        except Exception:
            return None

    def _name_the_field(self, wall) -> None:
        """Give every driver seen enough of a name, and remember his bitmap.

        A cluster that already carries a name got it from the archive, and
        re-saving keeps its exemplar current - a running average gets more
        typical as evidence arrives, not less. A cluster with no name gets a
        provisional handle rather than being dropped, because the alternative
        is throwing away a stop that cannot be observed again.
        """
        for driver_id in wall.roster.drivers(min_sightings=PIT_WALL_MIN_SIGHTINGS):
            try:
                name = wall.roster.name_of(driver_id)
                if not name:
                    name = self.store.provisional_driver_name()
                    wall.roster.label(driver_id, name)
                self.store.save_driver(name, wall.roster.exemplar_of(driver_id))
            except Exception:
                log("pitcrew").exception("pit-wall: could not save a driver")

    def _stop_pit_wall(self) -> None:
        """Close the wall, filing any stop still in progress at the flag.

        Called from `stop_race` AND from `shutdown`: closing the app mid-race
        otherwise files nothing, and leaves the sampler - which may still be
        inside a two-second grab it cannot be joined out of - pointing at a
        wall whose session has gone.
        """
        wall = getattr(self, "_pit_wall", None)
        if wall is None:
            return
        try:
            if self.hud is not None:
                self.hud.stop_watching_board()
            # **Named BEFORE the stops are closed, not after.** `rival_book`
            # refuses a stop with no driver on it, and the pit columns are gone
            # the moment the car leaves - so a stop filed after the flag with
            # no name is a stop lost for good. Every cluster seen enough to be
            # a driver gets a handle here, and its exemplar is saved so the
            # same handle finds him next race.
            self._name_the_field(wall)
            for seen in wall.close_all():
                self._on_rival_stop(seen)
            named = [name for _, name in wall.named() if name]
            if named:
                self.store.note_races_seen(named)
        except Exception:
            log("pitcrew").exception("pit-wall: could not close cleanly")
        finally:
            self._pit_wall = None

    def stop_race(self) -> None:
        # Before the session id is cleared: the stops are filed against it.
        self._stop_pit_wall()
        self.stop_haptics()
        self.stop_wind()
        if self.listener is not None:
            self.listener.stop()
            self.listener = None
        self._health.stop()
        if self.session_id is not None:
            # Before the id is cleared: `_stop_video` files the path OBS wrote
            # against the session row, and it needs the row to file it against.
            # It stops only a recording this app started, so a race run without
            # one costs nothing here.
            self._stop_video(self.session_id)
            self.store.end_session(self.session_id)
            self.session_kind = None
            self._tell_settings_about_the_session()
            # `stop_practice` clears this and `stop_race` did not, so the
            # Practice screen's pickers went on writing `practice_mode` onto
            # the closed race session - which `list_evidence_laps` reads back
            # for a rehearsal, and `auto_out_laps` acts on.
            self.session_id = None
        if self.race_run_id is not None:
            # **Nothing is drained here any more.** The offer desk used to
            # hold one unanswered question that would otherwise vanish from
            # `race_revisions` at the flag. There is no pending question now:
            # every recommendation is recorded on the lap it is spoken, and
            # the driver's answer - when it comes - is recorded beside it.
            self.store.finish_race_run(self.race_run_id)
            self.race_run_id = None
        self.race = None
        self.bridge.race_clock = None
        # An offer outlives the race that raised it: the buttons stayed live
        # and connected, and Accept then dereferenced `self.race`, which this
        # method had just set to None - straight out of a Qt slot, which aborts
        # the process, immediately after a race and before the export.
        self._replans.reset()
        self.ptt.pending_replan = None
        if self.race_screen is not None:
            self.race_screen.hide_offer()
        self.ptt.stop()
        if self.race_screen is not None:
            self.race_screen.set_armed(False)
            self.race_screen.set_status("Race closed.")

    def _close_out_finished_race(self) -> None:
        """Close the race run at the flag, rather than at app shutdown.

        **The Fuji race never ended.** `race_runs.finished_at` stayed null, no
        chequered flag was called, and the session closed on shutdown 16
        minutes 48 seconds after the last crossing - so `finish_race_run` never
        ran, and `prompt_issues` holds nothing for that event at all. Job 3,
        the export that is this app's most important output, did not run for
        the race it exists to describe.

        The proximate cause was the lap counter (see `coordinator._on_lap`),
        but the run stayed open for a second reason: **nothing closed it except
        `stop_race`, and `stop_race` is a button.** A driver who watches the
        replay, or closes the app, or simply forgets, loses the export for a
        race that is already over.

        **Deliberately not `stop_race`.** The flag is not the end of the
        session: the slow-down lap is still being recorded, the transducer is
        still running, and tearing all that down on a detector - however well
        guarded - is a bigger claim than this needs to make. What is recorded
        here is the fact that the race finished and when, which is what the
        run row and the export are missing. Stopping remains his.

        Idempotent: `race_run_id` is cleared, so a second crossing after the
        flag does nothing.
        """
        if self.race is None or self.race_run_id is None:
            return
        if not self.race.state.finished:
            return
        run_id, self.race_run_id = self.race_run_id, None
        try:
            self.store.finish_race_run(run_id)
        except Exception as exc:                            # noqa: BLE001
            # Never into the caller. He has just taken the flag and the app
            # falling over on the ledger write would be the last thing he sees
            # of the race.
            log("race").error("could not close the race run at the flag: %s",
                              exc, exc_info=True)
            return
        log("race").info(
            "race finished on lap %s - run %s closed. The session is still "
            "recording; stop it when you are done to file the video and "
            "close the laps.", self.race.state.lap, run_id)

    def _on_race_event(self, event) -> None:
        """Feed one telemetry event to the race, and say ONE thing back.

        **One call per lap has to hold across both producers.** The
        coordinator makes calls and the re-planner makes recommendations, and
        they used to be voiced independently, in the order the code happened
        to run them: on lap 8 of the certifying replay the driver heard
        "Recommend running to the flag." and then, on the same crossing,
        "Box this lap. RS. 1 lap overdue." - two opposite instructions two
        hundred milliseconds apart, in the exact race this engineer was
        rebuilt for. CLAUDE.md §5.5 is unambiguous: one thing at a time.

        So the two are arbitrated here. The loser is HELD rather than
        discarded - the re-planner changes no state when it is held, so the
        next lap decides it again on its own merits - and the coordinator's
        call is still recorded and shown even when it is not spoken, because
        the record is not the voice.
        """
        if self.race is None:
            return
        # **Pit exit, before the coordinator clears the stint.** Leaving short
        # of the target is a lift-and-coast he can start on the next straight,
        # which is the whole reason to say it here rather than three laps
        # later when the running estimate finally crosses a threshold. Then a
        # clean watch, so a second stop is not judged against the first.
        if event.kind is EventKind.PIT_EXIT:
            if self.bridge.refuel is not None:
                self.bridge.refuel.note_pit_exit(
                    self.bridge.last_packet.fuel_level
                    if self.bridge.last_packet else None)
            if self._colour is not None:
                # A new set and a new stint: "5 to the stop" and the gauge
                # prompt are news again, and the consistency window must not
                # straddle a pit stop.
                self._colour.new_stint()
        # **Before `handle`, so the call sees this lap's gauge.** The reading
        # lags its own lap by one - the sampler is asked at the crossing and
        # answers a moment later on its worker - so what lands here is the
        # previous lap's, which is exactly what the wear call is built to
        # expect. Filed after the coordinator instead, it would be a lap
        # further behind again and every projection would be one lap stale.
        if event.kind is EventKind.LAP_COMPLETED:
            # Both or neither. A reading whose lap could not be identified is
            # dropped rather than filed against lap 0, which would anchor every
            # fitted rate to a point the tyre was never at.
            # **The gauge going blind is news, and it is said here.**
            # The sampler decided; this is the Qt thread, where speaking is
            # allowed. Cleared as it is taken so it is said once per
            # diagnosis - see `LiveWearSampler._note_blind`.
            blind = self.hud.take_blind_note()
            if blind:
                if self._engineer_speaks:
                    self.voice.say(blind)
                log("pitcrew").warning("hud-wear: told the driver: %s", blind)
            wear_now, wear_lap = self.hud.latest_wear()
            if wear_lap and wear_now:
                self.race.state.note_wear(wear_lap, wear_now)
        call = self.race.handle(event)
        replan = None
        if event.kind is EventKind.LAP_COMPLETED:
            replan = self._check_replan(event.data["lap"], against=call)
        self._close_out_finished_race()
        if self.race_screen is not None:
            self.race_screen.show_snapshot(self._race_snapshot())
        if replan is not None:
            self._voice_replan(replan)
        if call is None:
            # **Colour calls rank below everything.** They only ever reach the
            # voice on a crossing that had nothing real to say - an engineer
            # who says "nice lap" over the top of a box call has actively hurt
            # the race, and the register that stopped the nine-box-calls
            # defect must not be undone by adding a second mouth to it.
            #
            # **The heartbeat is not "something real to say" for this
            # purpose.** At the driver's every-lap setting it wins every
            # crossing, so gating on `call is None` alone retires the whole
            # colour tier for the race - and `ColourCalls._gauge` lives there.
            # That prompt is the ONLY wear input that exists in VR, where the
            # live reader made 553 attempts at Fuji and accepted none: its own
            # docstring calls it worth more to the model than anything else
            # said all race. Trading it for a lap count is not a trade.
            #
            # **So the heartbeat does not return here - it falls through and
            # is SPOKEN.** The
            # first attempt at this put the heartbeat in the branch above and
            # deleted the voicing of the very thing it was protecting: STATUS
            # took almost every crossing, hit this `return`, and never reached
            # `voice.say`, `show_call` or the revision record. He would have
            # turned the race HUD off and heard nothing about lap, position or
            # time all night.
            #
            # The colour tier does NOT also speak on that crossing: §5.5 is
            # one thing at a time and `test_only_one_thing_is_voiced_per_
            # crossing` enforces it. What that tier held which could not be
            # lost - the gauge prompt, the only wear input that exists in VR -
            # is carried by the heartbeat itself now. See `calls._status`.
            if event.kind is EventKind.LAP_COMPLETED and replan is None:
                self._voice_colour(event.data["lap"])
            return

        # Spoken unless the re-planner won the lap. Everything below the voice
        # still happens: the screen shows it and the revision chain records
        # it, because an audit that could not see a call the engineer decided
        # against voicing would make the model look tidier than it was.
        # **A call that asks for a short-shift now moves the beep.**
        #
        # It did not, and that is the defect this fixes: `short_shifting` was
        # read in two places and set True nowhere outside the tests, so
        # "Short-shift 450." reached his ears and nothing reached the beep. He
        # was asked to short-shift with no cue, and `laps.short_shift_rpm`
        # then recorded 0.0 on every lap that had a value - so the app could
        # not tell afterwards that it had ever asked.
        #
        # Applied even when the engineer is silent, because the beep IS the
        # instruction when it is not spoken. Cleared by any later call that
        # does not ask for one: a box call ends the saving, and None here is
        # "stop short-shifting" rather than "no opinion".
        # **The heartbeat is exempt.** It is a report, not an instruction, and
        # at the every-lap setting it lands on the crossing after almost every
        # real call - so clearing on it would withdraw a short-shift the lap
        # after it was asked for, silently, every single time. `None` from a
        # call that instructs still means "stop short-shifting"; `None` from
        # one that only describes the race means nothing at all.
        if call.kind != STATUS:
            self.bridge.set_short_shift(call.short_shift_drop_rpm)

        if self._engineer_speaks and replan is None:
            self.voice.say(call.spoken())
            self.ptt.last_call = call.spoken()
        if self.race_screen is not None:
            self.race_screen.show_call(call)
        if self.race_run_id is not None:
            # Every call is recorded, accepted or not: a plan offered and
            # ignored is evidence about the model, and dropping it would make
            # the model look better than it was.
            #
            # **The stay-out fold is the one call recorded as accepted.**
            # It is not the engineer imposing anything - the driver voted by
            # staying out, laps past his stop, and the call adopts what he
            # is already doing. Recording it declined would tell the audit
            # the driver ignored the engineer at the exact moment the two
            # finally agreed.
            payload = {"call": call.as_export(), "confidence": call.confidence,
                       "kind": call.kind}
            accepted = call.kind == STAY_OUT
            if accepted:
                payload["resolution"] = "driver stayed out"
                # **The driver has chosen a shape with his own hands.** The
                # coordinator has already folded the plan to the zero-stop he
                # is executing; telling the register means the next lap's
                # recomputation confirms or revises THAT race rather than
                # re-proposing the stop he has spent two laps declining.
                # Only the fuel failing to reach cuts through - see
                # `PlanRegister._blocked_by_the_driver`.
                self._replans.note_driver_shape(
                    self.race.stops_planned(), lap=call.lap)
            self.store.append_revision(
                self.race_run_id, call.lap, call.call, payload,
                accepted=accepted)

    # ------------------------------------------------------------------- ptt

    def _race_snapshot(self) -> dict:
        """The coordinator's snapshot plus what only the controller knows.

        `replanning` is False once the per-lap re-plan has stood down. It is
        on the snapshot rather than only in the log because silence from an
        adviser reads as "nothing to report" - the status call says so in as
        many words - and an engineer that has stopped adapting the strategy
        must not be able to hide inside that.
        """
        if self.race is None:
            return {}
        return {**self.race.snapshot(),
                "replanning": self._replan_max_stops > 0,
                "replanOverBudget": self._replan_over_budget}

    def _ptt_snapshot(self) -> dict:
        """What the engineer is allowed to answer from.

        Also where a press becomes a mark in the wind frame log. **Every
        press, before anything else here can return early**, because the
        thing worth marking - fans that stopped while the link stayed
        perfect - happens in practice as readily as in a race, and the driver
        cannot be asked to remember which button means which.
        """
        # **`wind` lives on the BRIDGE, not on the controller**, and reading it
        # off `self` raised `AttributeError` on every press that got this far -
        # PitCrewPTT logged it and died, so **no push-to-talk question was
        # answered on 3 Sep 2026 at all.** Line 247's `self.wind = None` is
        # `TelemetryBridge.__init__` (class at line 183); this method is on
        # `PitCrewController` (class at line 709), and the two were read as one
        # object. The same shape as the `_hud`/`_sampler` rename that caused the
        # 30 Aug practice crash: an attribute that moved, and one reader left
        # behind. `getattr` would have hidden it - the mark would simply never
        # have been made - so it is spelled out and reached through its owner.
        wind = getattr(self.bridge, "wind", None)
        if wind is not None:
            wind.mark("ptt")
        if self.race is None:
            return {}
        snapshot = self._race_snapshot()
        # The fuel target for the stop, so "how much fuel do I take" has an
        # answer rather than a refusal.
        stints = (self.race.plan or {}).get("stints") or []
        index = self.race.state.stint_index + 1
        if index < len(stints):
            snapshot["stopFuelL"] = stints[index].get("fuel_l")
        # **The gauge, so "how are my tyres" has a measured answer.** It is the
        # question this app is about and it had no intent at all - it matched
        # BOX_WHAT and came back with the compound planned for the stop. Absent
        # keys stay absent: `intents.TYRES` answers "no tyre gauge" rather than
        # a number, because §3.3 gives the feed no wear channel and a figure
        # invented in reply to a direct question is the worst kind there is.
        wear = self.hud.latest_wear()[0]
        if wear:
            corner, worst = max(wear.items(), key=lambda kv: kv[1])
            snapshot["wearWorst"] = worst
            snapshot["wearCorner"] = corner
        return snapshot

    def _on_ptt_answer(self, heard: str, said: str) -> None:
        """**Hop to the Qt thread before touching a widget.**

        pynput runs its keyboard hook on its own daemon thread, and the
        push-to-talk reply arrives on it. This method used to build QWidgets
        and call insertWidget from there, which is undefined behaviour in Qt -
        and the window in which it happens is a live race, the one surface
        CLAUDE.md gives the strictest correctness bar. Everything else in this
        app is routed through the bridge's signals; this was the one path that
        went straight across.

        `QTimer.singleShot` was not the hop it looked like.  The no-receiver
        overload builds its dispatch object on the *calling* thread and posts
        to that thread's event loop, and pynput's hook thread has none - so the
        callback never ran at all.  Measured: posted from a worker it never
        fires; the same call on the Qt thread does.  So the driver said
        "accept", heard "Copy, changing the plan", and the plan did not change:
        `_resolve_replan` never ran, `_pending_replan` stayed set, and
        `_check_replan` returns early while it is, so no further offer could
        ever be made either.  A queued signal is delivered to the receiver's
        thread whether or not the emitting thread has a loop.
        """
        self.bridge.ptt_answered.emit(heard, said)

    def _current_lap(self) -> int | None:
        """The lap he is on, or None if nothing on the wire says.

        `laps_completed` is the count behind him, so the lap in progress is one
        more. None rather than a guess when there is no packet: an exchange
        filed against a lap that was not being driven is worse than one filed
        against no lap at all.
        """
        packet = getattr(self.bridge, "last_packet", None)
        done = getattr(packet, "laps_completed", None) if packet else None
        return int(done) + 1 if isinstance(done, int) and done >= 0 else None

    def _show_ptt_answer(self, heard: str, said: str) -> None:
        if self.race_screen is not None:
            self.race_screen.show_exchange(heard, said)
        from pitcrew.engineer.intents import (
            ACCEPT,
            KEEP,
            REPORTS,
            TYRES_RED,
            match_intent,
        )
        # **The verdict that reached him, not a second opinion of it.** This
        # re-derived the intent with `match_intent` - the literal keyword
        # matcher - while the decision he actually heard came from the semantic
        # matcher and `gate.judge`. Those two disagree by design, so the ledger
        # could record `fuel` against a press the engineer had refused, and the
        # record of what he asked became a record of something else answering
        # it. `last_verdict` is set on every path through `ask()`, including
        # the refusals.
        verdict = getattr(self.ptt, "last_verdict", None)
        intent = getattr(verdict, "intent", None) or match_intent(heard)
        action = getattr(verdict, "action", None)
        distance = getattr(verdict, "distance", None)
        reason = getattr(self.ptt, "last_reason", None) if (
            action == "reject") else None

        # **Both sides of the exchange, on the record - including the ones with
        # no question in them.** The calls ledger has only ever held what the
        # engineer said and whether it was taken. A call that was right and
        # ignored, and a call that was noise and ignored, look identical there;
        # the difference is almost always in the reply.
        #
        # And this used to return before writing anything whenever `heard` was
        # empty, which is precisely what a refused press looks like from here.
        # **Every press the app could not understand was therefore discarded**,
        # and those are the rows worth the most: a question his engineer could
        # not take, in his own words, is exactly what the phrase list is
        # missing. `tools/radio_review.py` reads them back.
        self.store.log_radio(
            self.session_id, heard=heard, said=said,
            lap_num=self._current_lap(), intent=intent,
            action=action, distance=distance, reason=reason)

        if not heard:
            return

        if intent in REPORTS:
            self._note_driver_report(intent, heard)
            return
        if intent == TYRES_RED:
            self._note_tyre_frame_red()
            return
        # **Only an OPEN offer can be accepted or kept.** This used to gate on
        # "the register has said something", which every spoken verdict sets -
        # including the burn notes, which are facts and not questions - and
        # which then stays set for the rest of the race. ACCEPT's vocabulary
        # includes "copy that", the phrase he uses to acknowledge ANY call, so
        # one stray acknowledgement locked the register onto a shape and wrote
        # an empty resolution row. `pending_replan` is set only for an offer
        # and cleared the moment it is answered.
        if self.ptt.pending_replan and intent in (ACCEPT, KEEP):
            self._resolve_replan(accepted=intent == ACCEPT)

    def _note_driver_report(self, intent: str, heard: str) -> None:
        """He told the engineer something. Write it down; act only where the
        report is about the LAP rather than about the car.

        **CLAUDE.md §4.1 is the reason this exists**: the driver's report is
        primary evidence and telemetry is corroboration, and until this landed
        the app could only be asked questions. A handling complaint went into
        the `radio` table as free text tagged `unknown`.

        A handling report is recorded and nothing more - one observation is one
        observation, and `race/driver_report.py` says why analysing it out loud
        would be inventing the meaning the record exists to establish. An off
        or a spell in traffic also **excludes the lap**, because the lap is
        then not a measurement of this car.
        """
        from pitcrew.engineer.intents import (
            REPORT_INCIDENT,
            REPORT_OVERSTEER,
            REPORT_TRAFFIC,
            REPORT_UNDERSTEER,
        )
        from pitcrew.race import driver_report

        kinds = {REPORT_UNDERSTEER: driver_report.UNDERSTEER,
                 REPORT_OVERSTEER: driver_report.OVERSTEER,
                 REPORT_INCIDENT: driver_report.INCIDENT,
                 REPORT_TRAFFIC: driver_report.TRAFFIC}
        packet = self.bridge.last_packet
        event = self.active_event()
        driver_report.note_report(
            kinds[intent], heard,
            packet=packet,
            car_id=getattr(packet, "car_id", None) if packet else None,
            compound=(self.race.state.tyre_compound if self.race else None),
            lap=self._current_lap(),
            event_id=event["id"] if event else None,
            session_id=self.session_id)

        if intent == REPORT_INCIDENT and self.race is not None:
            # **Told, rather than detected.** The coordinator costs the lap
            # either way; `reported` is what stops the engineer announcing
            # something he has just been thanked for.
            self.race.note_incident(reported=True)

        if intent in (REPORT_INCIDENT, REPORT_TRAFFIC):
            # **Held for the NEXT crossing rather than applied now.** The lap
            # he is describing has not been stored yet - it is the one he is
            # driving - so there is no row to mark. A lap number is
            # deliberately not used as the key either: it would have to agree
            # with GT7's own count, and `laps_completed` is still unverified
            # against a real race. "The next lap to land" needs no such
            # agreement.
            self._exclude_next_lap = (
                "incident" if intent == REPORT_INCIDENT else "traffic")

    def _live_worst_wear(self) -> tuple[float | None, str | None]:
        """The worst corner the gauge has read, and which one. (None, None)
        where it is not reading - never a zero, which would say fresh."""
        wear = self.hud.latest_wear()[0]
        if not wear:
            return None, None
        corner, worst = max(wear.items(), key=lambda kv: kv[1])
        return worst, corner

    def _on_straight_reached(self) -> None:
        """Qt thread: the car is somewhere he can listen. Read him a number.

        **This is the only thing in the app that speaks mid-lap**, and it is
        the smallest thing that could: one measured figure, in chatty mode
        only, at most once a lap.

        *"Agree data should come on straights not corners."* - and the measured
        reason it needs `race/straight.py` rather than a throttle test is in
        that module: sustained full throttle alone finds nineteen windows on a
        Monza lap, several of them above 1.7 g, because the runs are broken by
        upshifts rather than by corners. Speaking at 2.78 g is worse than
        speaking in a braking zone. With the lateral gate it is five sensible
        windows.

        It is not extra radio. The data tier moved OFF the crossing to get
        here, so the budget is unchanged and the findings it used to displace
        now get through.
        """
        race = self.race
        if race is None or not race.running or self._colour is None:
            return
        state = race.state
        if state.in_pit or state.finished:
            return
        # **Never over the engineer.** A call was made on this lap's crossing,
        # so the lap has already had its word - and a number read out on top
        # of a box call is the nine-box-calls defect with a second mouth.
        # The heartbeat is the exception and has to be: it takes every
        # crossing at the every-lap setting, and this line would then never be
        # reached again for the rest of the race.
        if (state.last_said_lap == state.lap
                and not state.only_the_heartbeat_this_lap()):
            return
        call = self._colour.data_line(
            lap=state.lap,
            fuel_laps_in_hand=self._laps_of_fuel_in_hand(state),
            # **The live gauge, not a lap row.** There is no lap to read here
            # - this is mid-lap - and `_worst_wear(None)` would return None
            # for every corner, so the straight would never once carry a wear
            # figure. `hud.latest_wear` is what the sampler last transcribed,
            # is fresher than a stored lap in any case.
            wear_worst=self._live_worst_wear()[0],
            wear_corner=self._live_worst_wear()[1],
            stint_ends_on_lap=state.stint_ends_on_lap)
        if call is None:
            return
        spoken = call.spoken()
        if self._engineer_speaks:
            self.voice.say(spoken)
        self.ptt.last_call = spoken
        if self.race_screen is not None:
            self.race_screen.set_status(spoken)
        self._file_informational(call)

    def _on_position_changed(self, call) -> None:
        """Qt thread: he has gained or lost a place. Say so.

        **And where that leaves the championship, when it moves.** A place
        changed is also a championship position changed, sometimes - and that
        is the version worth hearing. Said only on a change: a projection
        recomputed every lap is a number that moves constantly and means
        little, while "down to championship P4" is a fact he can drive to.

        **The one fact the engineer volunteers**, and the reasons are on
        `calls.POSITION`: he races with GT7's race HUD off, so this is not a
        fact he could look up, and a place changed moves what a stop costs.

        **It does not go through `_on_race_event`'s arbitration and must
        not.** That arbitration exists to stop two *instructions* landing on
        one crossing. This is not an instruction and it does not arrive on a
        crossing - it is composed mid-lap, off a frame, in the gap where
        nothing else is speaking. Routing it through the crossing would make
        it compete with the box call and lose, which is the same as deleting
        it: places change between crossings, and by the next one the news is
        a lap old.

        Recorded like any other call. A place lost two laps before a stop is
        evidence about the plan, and the ledger is where the debrief reads it.
        """
        if self.race is None or call is None:
            return
        if self._engineer_speaks:
            self.voice.say(call.spoken())
            self.ptt.last_call = call.spoken()
        if self.race_screen is not None:
            self.race_screen.show_call(call)
        if self.race_run_id is not None:
            self.store.append_revision(
                self.race_run_id, call.lap, call.call,
                {"call": call.as_export(), "confidence": call.confidence,
                 "kind": call.kind},
                accepted=False)
        # **After the place, and only when the championship actually moved.**
        # Said second because the place is the thing he can see out of the
        # window and the championship is the thing he cannot.
        moved = self._league_moved()
        if moved:
            log("race").info("league: %s", moved)
            if self._engineer_speaks:
                self.voice.say(moved)
            if self.race_screen is not None:
                self.race_screen.set_status(moved)

    def _on_incident_seen(self) -> None:
        """Qt thread: the car stopped mid-lap. Decide what it is worth.

        **Both halves land here** - this one and the driver saying "I went
        off" - so the lap leaves the count by one route whichever way the
        engineer found out, and the two can never disagree about which lap.
        """
        if self.race is not None:
            self.race.note_incident(reported=False)
        # The same seam the driver's own report uses. Not overwritten if he
        # already named it: his word is the primary record and "incident" is
        # what both produce anyway.
        if not getattr(self, "_exclude_next_lap", None):
            self._exclude_next_lap = "incident"

    def _note_tyre_frame_red(self) -> None:
        """He saw a tyre frame go red. Write it down beside our own degrees.

        **The only bridge that exists between what he can see in VR and what
        this app measures.** PD documents the frame as reddening with heat and
        publishes no scale; nobody has ever paired the colour with a number.
        His report is the event - primary evidence, CLAUDE.md §4.1 - and the
        temperature beside it is ours. Nothing reads the file yet, and nothing
        should until there are enough rows to say something.
        """
        packet = self.bridge.last_packet
        if packet is None:
            return
        event = self.active_event()
        note_frame_red(
            car_id=getattr(packet, "car_id", None),
            compound=(self.race.state.tyre_compound if self.race else None),
            temps=packet.tyre_temps,
            lap=self.race.state.lap if self.race else None,
            speed_kmh=getattr(packet, "speed_kmh", None),
            event_id=event["id"] if event else None)

    def _note_button_probe(self, text: str) -> None:
        if self.settings_screen is not None:
            self.settings_screen.note_ptt(text)

    def _resolve_replan(self, *, accepted: bool) -> None:
        """Record what the driver did with the recommendation, and act on it.

        **"Offered, never imposed" survives continuous re-planning.** The
        engineer's current best plan refreshes silently every lap, but taking
        on a different stop SHAPE is still the driver's word - and either
        answer is him choosing, so the register notes the shape either way and
        stops re-opening a question he has just closed.
        """
        resolution = self._replans.answered(
            accepted=accepted, lap=self.race.state.lap if self.race else 0,
            # What "keep" means: the shape he is actually running. Without it
            # the register forgot his refusal and re-offered the plan of
            # record as news on the very next lap.
            current_stops=self.race.stops_planned() if self.race else None)
        self.ptt.pending_replan = None
        if resolution is None or self.race_run_id is None:
            return
        self._record_resolution(resolution)
        offer = resolution.offer
        if accepted and offer.stint_laps and self.race is not None:
            self.race.adopt(offer.stint_laps,
                            compounds=offer.stint_compounds or None)
        # The question is answered, so it stops being asked.
        if self.race_screen is not None:
            self.race_screen.hide_offer()

    def _record_resolution(self, resolution) -> None:
        """One answered recommendation into the revision chain.

        `resolution` distinguishes a driver who said "keep" from one who
        accepted - the audit needs to tell a refusal from an adoption. A
        recommendation he never answered at all is already in the chain, from
        the lap it was spoken on.
        """
        if self.race_run_id is None:
            return
        offer = resolution.offer
        payload = offer.as_plan()
        payload["resolution"] = resolution.reason
        self.store.append_revision(
            self.race_run_id, resolution.lap,
            offer.call() or offer.reason, payload,
            accepted=resolution.accepted)

    # ---------------------------------------------------------------- replan

    def _check_replan(self, lap, *, against=None):
        """Rebuild the whole strategy problem at the end of every lap.

        The driver's instruction: *"Race engineer needs to read data at end of
        every lap and recalculate entire strategy each lap based on all the
        practice data and even more important the current race data."* So the
        model is re-solved here unconditionally - no drift gate decides
        whether to think - over practice evidence plus everything this race
        has shown, with the race's own burn taking over from the practice
        figure as soon as it has converged.

        **Speaking is a separate decision, and it is the register's.** The
        answer being current is the point; announcing it is not. The failure
        this replaces is the race of 16 Aug, nine identical box calls, and
        recalculating every lap makes that failure easier to reach rather than
        harder. `PlanRegister.consider` speaks only on a material change - the
        stop count moves, the stop lap slides more than a lap or two, the fuel
        crosses into or out of "won't reach", or the burn crosses a band edge
        against what the plan expected.

        **Lap time is in none of that.** It refines the timed race's distance
        estimate and it feeds the expectation comparison the driver asked for,
        both of which are reported as estimates. It never moves a stop count:
        his lap-to-lap noise is wider than the whole degradation band, and
        there is a standing rule in this project's history against routing a
        lap-time trigger through `recommend()`.

        Returns the recomputation to voice, or None. `against` is the
        coordinator's call for this same crossing, and it wins the lap unless
        the fuel has stopped reaching the flag - see `_replan_outranks`.
        """
        if self.race is None or not self.race.running:
            return None
        if lap.fuel_used > 0:
            self._race_burns.append(lap.fuel_used)

        inputs = self._race_inputs
        if self._replan_max_stops <= 0:
            # Budget exhausted. The plan he is on stands and the engineer
            # says nothing about the stops - an adviser that blocks the Qt
            # thread mid-race is worse than one that stops advising, and the
            # driver is told once that it has happened.
            return None

        # **The budget is checked BEFORE the solve, because a budget measured
        # afterwards is not a budget.** Timing `assess` and reacting to the
        # result means the 6.35-second solve happens in full, on this thread,
        # mid-race - and then the narrowed retry happens too. `replan_work`
        # estimates the search from the two numbers that drive it and an
        # oversized problem is refused rather than attempted.
        laps_left = (self.race.state.laps_remaining() or 0)
        work = replan_work(inputs, laps_left, self._replan_max_stops)
        if work > REPLAN_MAX_WORK:
            # **Narrow first, stand down second - the same ladder the post-hoc
            # backstop already climbs.** This branch used to go straight to a
            # full stand-down, so an oversized FULL search took the narrowed
            # one down with it, and the two guards disagreed about how to fail.
            #
            # It cost the Monza race of 18 Aug 2026 its entire adaptation. A
            # third compound had acquired a profile since the cap was
            # calibrated, so `calls` went 2**s to 3**s: 3000 units against the
            # 1200 cap on lap 1, refused, re-planning off for the rest of the
            # race, and the last stop was still being fuelled by the plan
            # approved before the green. The narrowed search that was never
            # tried was 975 units, and measured on that race's own shape it
            # cost 19 ms against the 50 ms budget - the full one cost 161.
            if self._replan_max_stops > REPLAN_NARROWED_MAX_STOPS:
                narrowed = replan_work(inputs, laps_left,
                                       REPLAN_NARROWED_MAX_STOPS)
                if narrowed <= REPLAN_MAX_WORK:
                    self._replan_max_stops = REPLAN_NARROWED_MAX_STOPS
                    log("race").warning(
                        "the per-lap re-plan would be %d units against a %d "
                        "cap - narrowing the search to %d stops rather than "
                        "standing down (%d units). Cost is superlinear in "
                        "profiled compounds.",
                        work, REPLAN_MAX_WORK, REPLAN_NARROWED_MAX_STOPS,
                        narrowed)
                    work = narrowed
            if work > REPLAN_MAX_WORK:
                self._stand_down_replan(
                    f"the search would be {work} units against a "
                    f"{REPLAN_MAX_WORK} cap - refused without being attempted")
                return None

        started = _monotonic()
        verdict = assess(
            laps_done=self.race.state.lap,
            laps_total=self.race.state.laps_total,
            fuel_l=self.race.state.fuel_l,
            planned_fuel_per_lap=self.race.planned_fuel_per_lap_l,
            observed_fuel_per_lap_l=self.race.observed_fuel_per_lap(),
            # Accepted and then ignored by the verdict - see `assess`. Passed
            # so a reader finds the guard rather than the absence of one.
            lap_time_ms=self.race.representative_pace_ms(),
            planned_lap_time_ms=inputs.lap_time_ms if inputs else None,
            current_stops=self.race.stops_planned(),
            inputs=inputs,
            fuel_capacity_l=inputs.fuel_capacity_l if inputs else None,
            # **What this race has shown, refreshed every crossing.** The plan
            # approved before the green is the fallback for each of these and
            # not the source: he asked for the remainder to be re-solved on
            # what is actually happening, and a margin sized off practice
            # scatter is a margin sized off another car's day.
            observed_fuel_sd_l=self.race.expect.race_fuel_sd_l(),
            achieved_lap_ms=self.race.expect.achieved_lap_time_ms(),
            lap_sigma_s=((self.race.expect.sigma_ms() or 0) / 1000.0) or None,
            max_stops=self._replan_max_stops,
        )
        self._note_replan_cost(_monotonic() - started)
        outcome = self._replans.consider(
            verdict, lap=self.race.state.lap,
            burn_drift=self.race.expect.burn_vs_plan(),
            # The race has shown something the plan was not built on once its
            # own burn has converged - the low-noise channel, and the only one
            # allowed to move a stop count.
            race_evidence=self.race.observed_fuel_per_lap() is not None,
            # Asked about the candidate actually about to be said, not about
            # the raw verdict - a verdict of "on the plan" can still produce a
            # burn note, and ranking the verdict let one be voiced on the same
            # crossing as a tyre call.
            may_speak=lambda candidate: self._replan_outranks(
                candidate, against))
        if not outcome.spoken:
            # **A recomputation that changes nothing is not a revision.** A
            # row a lap would bury the ones that matter under a race's worth
            # of "still the same plan".
            return None
        return outcome

    @staticmethod
    def _replan_outranks(verdict, call) -> bool:
        """Whether the re-planner may have this lap, or the coordinator does.

        **One thing at a time has to hold across both producers**, so the two
        are ranked against each other on the same scale the coordinator
        already uses for its own calls (`calls.URGENCY`). Where the
        re-planner sits on that scale depends on what it is saying:

        * **The fuel no longer reaches the flag** is not a preference between
          plans, it is arithmetic about whether the car gets to the end.
          Nothing except the chequered flag outranks it.
        * **A change of stop shape** is about a stop some laps away, so it
          ranks with `BOX_SOON`: it beats a tyre warning or a status call and
          it waits behind an immediate instruction. On lap 8 of the measured
          race that is the whole point - "Box this lap, one lap overdue" and
          "Recommend running to the flag" contradict each other, and the
          driver heard both, two hundred milliseconds apart.
        * **A note about the burn** is a fact rather than an instruction and
          waits behind everything.

        The stay-out fold is not in `URGENCY` - the coordinator returns it
        directly rather than through `next_call` - and it is treated as top
        rank, because it is the engineer agreeing with something the driver
        has already spent two laps doing.
        """
        from pitcrew.race.calls import BOX_SOON, CHEQUER, STAY_OUT, URGENCY
        from pitcrew.race.replan import NOTED, URGENT

        if call is None:
            return True
        if verdict.verdict == URGENT:
            return call.kind != CHEQUER
        if verdict.verdict == NOTED or call.kind in (CHEQUER, STAY_OUT):
            return False
        if call.kind not in URGENCY:
            return False
        return URGENCY.index(call.kind) > URGENCY.index(BOX_SOON)

    def _voice_replan(self, outcome) -> None:
        """Say one recommendation, record it, and arm accept/keep if it is one."""
        spoken = outcome.verdict
        # **Instruction first, reason short** (§5.5). The full reason carries
        # every fact the verdict rests on and goes into the record; what he
        # hears is the one that raised it. The unabridged form was 145
        # characters of three semicolon-joined clauses beginning in lower
        # case.
        text = (f"{spoken.call()} {spoken.spoken_reason()}".strip()
                if spoken.offered else spoken.call())
        # Only a change of stop shape is a question. A note about the burn
        # against the plan's expectation is a fact, and arming accept/keep for
        # it would ask him to answer something nobody asked.
        self.ptt.pending_replan = spoken.call() if spoken.offered else None
        if self._engineer_speaks:
            self.voice.say(text)
        self.last_call = text
        self.ptt.last_call = text
        if self.race_screen is not None:
            if spoken.offered:
                self.race_screen.show_offer(spoken)
            else:
                self.race_screen.hide_offer()
        if self.race_run_id is not None:
            payload = spoken.as_plan()
            payload["why_spoken"] = outcome.why
            # **Said, not asked.** This path records what the engineer spoke;
            # nothing here was ever an offer, so the `accepted=False` the
            # column forces is the absence of a question. Marking it keeps
            # the export from reading it back as a refusal - which is how the
            # Watkins race came to report all fourteen calls declined,
            # including the chequered flag.
            payload["informational"] = True
            self.store.append_revision(
                self.race_run_id, outcome.lap,
                spoken.call() or spoken.reason, payload, accepted=False)

    def _refuel_context(self):
        """What the fill should be sized to, for the race right now.

        **Recomputed here rather than reused from the box call.** That call is
        made a lap and a half before the fuel moves and is sized by the plan's
        picture of the race; this is sized by the race, off the burn it has
        actually shown and the laps that are actually left. At Monza on
        18 Aug 2026 the gap between those two was about twelve litres, which
        at the measured 1.002 L/s is twelve seconds parked.
        """
        race = self.race
        if race is None or not race.running:
            return None
        # The third figure is the alternative he is actually weighing in the
        # box - see `calls.fuel_to_flag_l`. It is None whenever staying out is
        # not a live option, and the watch says nothing about it then.
        return (fuel_target_l(race.state), race.state.fuel_per_lap_l,
                fuel_to_flag_l(race.state))

    def _voice_refuel(self, call) -> None:
        """Say it, show it, and file it with the rest of the race's calls."""
        spoken = call.spoken()
        if self._engineer_speaks:
            self.voice.say(spoken)
        self.ptt.last_call = spoken
        self.last_call = spoken
        if self.race_screen is not None:
            self.race_screen.set_status(spoken)
        if self.race_run_id is not None and self.race is not None:
            # Recorded like every other call, because the post-race audit has
            # to be able to ask what the engineer said in the box and what it
            # was sized on - CLAUDE.md §5.5.
            self.store.append_revision(
                self.race_run_id, self.race.state.lap, spoken,
                {"call": {"kind": call.kind, "call": call.call,
                          "reason": call.reason},
                 "confidence": "high", "informational": True},
                accepted=False)

    def _note_replan_cost(self, seconds: float) -> None:
        """The backstop, for a shape `replan_work` did not anticipate.

        The real guard is the pre-check in `_check_replan`: an estimate made
        before the solve, so an oversized problem is refused rather than run.
        This one only fires when something got through it and cost more than
        expected anyway - narrow once, stand down the second time.
        """
        if seconds <= REPLAN_BUDGET_S:
            return
        self._replan_over_budget += 1
        if self._replan_max_stops > REPLAN_NARROWED_MAX_STOPS:
            self._replan_max_stops = REPLAN_NARROWED_MAX_STOPS
            log("race").warning(
                "the per-lap re-plan took %.0f ms against a %.0f ms budget - "
                "narrowing the search to %d stops. Cost is superlinear in "
                "profiled compounds.",
                seconds * 1000, REPLAN_BUDGET_S * 1000,
                REPLAN_NARROWED_MAX_STOPS)
            return
        self._stand_down_replan(
            f"it took {seconds * 1000:.0f} ms even narrowed")

    def _stand_down_replan(self, why: str) -> None:
        """Stop re-planning for this race, and **tell him it has stopped**.

        Silence from an adviser is indistinguishable from an adviser with
        nothing to say - that is the whole reason the status call exists - so
        an engineer that has quietly stopped adapting the strategy is worse
        than one that never offered to. Said once, out loud, and carried on
        the snapshot for the rest of the race.
        """
        if self._replan_max_stops <= 0:
            return
        self._replan_max_stops = 0
        self._replan_over_budget += 1
        log("race").error(
            "per-lap re-planning is off for this race and the approved plan "
            "stands - %s. The engineer will not adapt the stop count from "
            "here.", why)
        told = ("Strategy re-planning is off. The approved plan stands - "
                "I won't adapt the stops from here.")
        if self._engineer_speaks:
            self.voice.say(told)
        self.last_call = told
        self.ptt.last_call = told
        if self.race_screen is not None:
            self.race_screen.set_status(told, warn=True)

    # ---------------------------------------------------------------- export

    def _on_export(self) -> str | None:
        event = self.active_event()
        if event is None:
            self.practice.note("Create an event before exporting.", warn=True)
            return None
        try:
            payload = build_event_export(
                self.store, event["id"],
                game_version=self.settings.game_version)
            text = to_json(payload)
        except ExportRefused as exc:
            # Refusing is the designed behaviour: the consumer is a reader, so
            # a malformed payload would be misread rather than rejected. Show
            # every reason, not the first - a one-line note was easy to miss.
            self.practice.note(
                " · ".join(line.strip(" -") for line in
                           str(exc).splitlines()[1:]) or str(exc), warn=True)
            return None
        except ValueError as exc:
            self.practice.note(str(exc), warn=True)
            return None

        clipboard = QApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(text)

        path = self._write_export(text)
        laps = len(payload.get("laps") or ())
        self.practice.note(
            f"{laps} laps copied to the clipboard. The Race Engineer screen "
            f"embeds this payload in a prompt for you. Also saved to {path}.")
        return text

    def _write_export(self, text: str) -> Path:
        EXPORT_DIR.mkdir(parents=True, exist_ok=True)
        stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        path = EXPORT_DIR / f"pitcrew-{stamp}.json"
        path.write_text(text, encoding="utf-8")
        return path

    def shutdown(self) -> None:
        # **The orphan sweep, if the event loop never got to it.** It is
        # deferred to first paint now, and `main()` can return through its
        # `finally` without ever reaching `app.exec()` - so without this, the
        # one thing that notices the previous run died could itself be skipped
        # by a run that dies. Idempotent, so a normal exit does nothing here.
        self._first_paint_work()
        # Close the session before anything else. Shutting the window while
        # recording used to leave `ended_at` null, which is exactly what a
        # crash leaves - so a clean exit was indistinguishable from a lost one.
        if self.session_id is not None:
            self.store.end_session(self.session_id)
            log("session").info("session %s closed on shutdown",
                                self.session_id)
            self.session_id = None
        self.stop_haptics()
        # The one place the link is really let go: the app is closing. A
        # session boundary only parks the fans - see `start_wind`.
        self.shutdown_wind()
        self._stop_pit_wall()
        self._stop_hud_sampler()
        if self.listener is not None:
            self.listener.stop()
        self.bench.shutdown()
        self._health.stop()
        self.ptt.stop()
        self.voice.stop()
