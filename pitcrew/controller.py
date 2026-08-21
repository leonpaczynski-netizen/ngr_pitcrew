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
import time
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
from pitcrew.analysis.session import counted_laps
from pitcrew.analysis.runs import (
    FOR_QUALIFYING,
    auto_out_laps,
    carry_compound,
    fuel_implausible_laps,
)
from pitcrew.diagnostics import log
from pitcrew.engineer.ptt import (
    PushToTalk,
    best_listener,
    best_recogniser_for,
    best_semantic_matcher,
)
from pitcrew.engineer.shift_beep import ShiftBeep
from pitcrew.rig import transducer
from pitcrew.rig.effects import EffectDeriver
from pitcrew.rig.haptics import HapticsEngine, TransducerWatchdog
from pitcrew.rig.wind import WindSim
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
from pitcrew.setup.parse import parse_reply
from pitcrew.setup.sheet import RangeRecord, SetupError, SetupSheet
from pitcrew.store import catalogs
from pitcrew.store.db import (DEFAULT_SHEET_PURPOSE, WEAR_HUD_VIDEO,
                              Store)
from pitcrew.store.identity import IDENTITY_OK
from pitcrew.race.calls import STAY_OUT, fuel_target_l
from pitcrew.race.coordinator import PlanContext, RaceCoordinator
from pitcrew.race.expectations import PRACTICE, Expectation
from pitcrew.race.hud_calibration import note_frame_red
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
from pitcrew.strategy.evidence import build_inputs
from pitcrew.strategy.model import StrategyImpossible, recommend
from pitcrew.telemetry.selftest import LISTEN_S, check_feed
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


class TelemetryBridge(QObject):
    """Turns the packet stream into Qt signals, on the right threads."""

    lap_completed = pyqtSignal(object, object)   # Lap, detached frame rows
    session_event = pyqtSignal(object)           # every event, for the race
    stream_seen = pyqtSignal(object)             # first packet's fixed facts
    parse_failed = pyqtSignal()
    ptt_answered = pyqtSignal(str, str)      # heard, said - off the hook thread
    button_probed = pyqtSignal(str)          # probe note - off the hook thread

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

        # **The in-box refuel watch**, under the same doctrine as the coach
        # above: guarded, and dropped for the session on its first exception.
        # It does nothing at all until the tank starts climbing, which is once
        # or twice a race, and the target is only sized when the car is slow
        # enough to be in a pit box - so the 60 Hz cost is one comparison.
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
                self.wind.set_output(self.wind_curve.update(
                    packet, _FRAME_S, racing=self.racing))
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
                 port: int | None = None, voice=None,
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
        self._button_probe = None
        # Build the recogniser first, then ask *it* what it is. The gate used to
        # be chosen from the configured backend, but `best_recogniser_for` falls
        # back across that very boundary: with the shipped default of SAPI, and
        # SAPI failing to come up on this machine, the app ran Moonshine free
        # dictation with `matcher=None` - and `gate.judge` short-circuits when
        # there is no distance, so the whole five-stage gate was skipped on the
        # one path that needs it. Only free dictation needs it; SAPI's closed
        # grammar is exact by construction.
        recogniser = best_recogniser_for(self.settings.speech_backend)
        free_dictation = getattr(recogniser, "name", "") == "moonshine"
        self.ptt = PushToTalk(
            snapshot=self._ptt_snapshot,
            speak=self.voice.say,
            recogniser=recogniser,
            listener=best_listener(self.settings.ptt_key),
            on_answer=self._on_ptt_answer,
            matcher=best_semantic_matcher() if free_dictation else None,
            sensitivity=self.settings.speech_sensitivity)
        self._plans: list = []
        self._inputs = None
        self._plans_event_id: int | None = None
        # What the open session is, so handlers that write "to the open
        # session" can tell a practice run from a race.
        self.session_kind: str | None = None

        self.bridge = TelemetryBridge(self)
        self.listener: UDPListener | None = None
        self.session_id: int | None = None
        self._parse_errors = 0
        self._store_errors = 0

        self.bridge.lap_completed.connect(self._on_lap_completed)
        self.bridge.stream_seen.connect(self._on_stream_seen)
        self.bridge.parse_failed.connect(self._on_parse_failed)
        self.bridge.ptt_answered.connect(self._show_ptt_answer)
        self.bridge.button_probed.connect(self._note_button_probe)
        self.bridge.session_event.connect(self._on_race_event)

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
        if self.strategy is not None:
            self.strategy.build_requested.connect(self.build_strategy)
            self.strategy.approve_requested.connect(self.approve_strategy)
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
            self.engineer.generate_requested.connect(self.generate_prompt)
            self.engineer.copy_requested.connect(self.copy_prompt)
            self.engineer.reply_saved.connect(self.file_prompt_reply)
        if self.settings_screen is not None:
            self.settings_screen.saved.connect(self.save_settings)
            self.settings_screen.test_beep_requested.connect(self.test_beep)
            self.settings_screen.test_voice_requested.connect(self.test_voice)
            self.settings_screen.test_haptics_requested.connect(
                self.test_haptics)
            self.settings_screen.test_feed_requested.connect(self.test_feed)
            self.settings_screen.capture_toggled.connect(self.toggle_capture)
            self.settings_screen.listen_toggled.connect(self.probe_button)
            self.settings_screen.load(self.settings)
            self.settings_screen.show_capabilities(
                speech=self.voice.engine_name, hook=self.ptt.has_listener)

        # Ranges measured before the app had anywhere to keep them. Seeded
        # once, and never allowed to overwrite something read off a car.
        self.store.seed_range_records(catalogs.range_seed_records())
        self.bridge.apply_settings(self.settings)
        self.voice.tune(**self.settings.voice_tuning())

        self._health = QTimer(self)
        self._health.setInterval(1000)
        self._health.timeout.connect(self._report_health)

        self.refresh_catalogs()
        self.load_active_event()
        # Last, so its warning survives: loading the event writes the practice
        # status line, and running this first meant the one message saying the
        # app had died was overwritten before anyone saw it.
        self._close_orphaned_sessions()

    # --------------------------------------------------------------- catalog

    def refresh_catalogs(self) -> None:
        """Shipped names, plus anything added straight to the store.

        There is no UI for adding: a free-text field is where the typos came
        from. A missing track is fixed in the catalogue, not at the keyboard
        mid-session.
        """
        tracks = sorted(set(catalogs.track_bases())
                        | set(self.store.custom_catalog("track")))
        groups = list(catalogs.cars_by_category().items())
        extra = self.store.custom_catalog("car")
        if extra:
            groups.append(("Added", tuple(sorted(extra))))
        self.event_screen.set_catalogs(tracks, groups)
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
        sheet = self.store.sheet_for(car, "race")
        if sheet is None:
            sheets = self.store.list_setup_sheets(car)
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
        sheet = SetupSheet(
            car_name=data["car_name"],
            sheet_name=name,
            values=dict(data["setup_values"]),
            gears=gears,
            shift_rpm=shift_rpm,
            performance=dict(data.get("performance") or {}),
            build=dict(data.get("build") or {}),
            purpose=purpose,
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

    def test_feed(self, listen_s: float = LISTEN_S) -> bool:
        """Can the port actually be opened, and is anything on it?

        Tested against the value in the boxes rather than the saved one, so
        the answer is about the change he is considering. It reports the two
        failures separately: a port that will not bind is a different problem
        from a port that binds and stays silent, and only the first is
        something this screen can fix.
        """
        if self.settings_screen is None:
            return False
        wanted = self.settings_screen.values()
        direct = (wanted.feed_source == FEED_PS5
                  and bool(wanted.ps5_ip.strip()))

        # **Compare against the port that would actually be bound.** Direct
        # mode ignores the configured port and uses GT7's own, so comparing
        # `udp_port` to the live listener never matched: the test then tried
        # to bind 33740 out from under the app's own listener, could not,
        # and reported "another program is holding it" while the feed was
        # working perfectly. The self-test called the healthy case a fault.
        would_bind = GT7_STREAM_PORT if direct else wanted.udp_port
        if self.listener is not None and would_bind == self.listener.port:
            seen = self.listener.total_received
            decoded = self.listener.decoded
            rate = self.listener.packet_rate
            detail = (f"{decoded} of {seen} packets decoded"
                      + (f", {rate:.0f} Hz" if rate else ""))
            self.settings_screen.note_feed(
                f"Port {would_bind} is in use by this session's own "
                f"listener, which is the answer you want. {detail}.",
                warn=bool(seen and not decoded))
            return True

        # **Not a port probe.** A free port proves nothing: a wrong port
        # pair, a console nobody has asked, and a game sitting in the
        # menus all bind cleanly and deliver nothing. This opens the
        # socket, sends real heartbeats where they are required, and says
        # what decoded - CLAUDE.md 7, the connection fails loudly.
        if wanted.feed_source == FEED_PS5 and not wanted.ps5_ip.strip():
            self.settings_screen.note_feed(
                "Direct mode needs the console's address. Without it "
                "there is nothing to send a heartbeat to, and GT7 streams "
                "only to an address that has asked it.", warn=True)
            return False

        # **Say it is working before it blocks.** `check_feed` listens for
        # four seconds on this thread, deliberately - it is driven by a button
        # pressed while sitting still, and a background version would report
        # into a screen he has already left. But the button was not disabled
        # and nothing said "listening", so the app was an unresponsive
        # white-flagged window for four seconds after every click. The PTT
        # probe beside it already does this properly.
        self.settings_screen.set_feed_testing(True)
        QApplication.processEvents()
        try:
            report = check_feed(
                port=GT7_STREAM_PORT if direct else wanted.udp_port,
                heartbeat_to=wanted.ps5_ip.strip() if direct else None,
                source_ip=wanted.udp_source_ip,
                listen_s=listen_s)
        finally:
            self.settings_screen.set_feed_testing(False)
        self.settings_screen.note_feed(report.as_text(), warn=not report.ok)
        return report.ok

    def _chosen_output(self) -> str:
        return self.settings.audio_output_device or ""

    def _where_he_listens(self) -> str:
        return self._chosen_output() or "the system default output"

    def test_beep(self) -> bool:
        """Sound the beep now. The only way to know it carries over the engine.

        Played and then **verified against the sound card's own peak meter**.
        Returning from `play_now` only proves the app got as far as writing
        samples, and a card that has stopped rendering accepts those without
        complaining - see `endpoint_meter` for the measurement that proved it.
        """
        if self.settings_screen is None:
            return False
        beep = self.bridge.shift_beep
        outcome: dict[str, bool] = {}

        def play() -> None:
            outcome["played"] = beep.play_now()

        heard, detail = self._confirm_audio(
            play, device=self._chosen_output() or None)
        played = outcome.get("played", False)
        note, warn = self._audio_verdict(
            acted=played,
            failed=(f"No beep - {beep.last_error}" if beep.last_error else
                    "No beep - this machine has no tone device"),
            worked=("Beeped at "
                    + (", ".join(f"g{g} {rpm:.0f} rpm"
                                 for g, rpm in sorted(beep.per_gear.items()))
                       if beep.per_gear else
                       "no measured threshold - the fitted sheet has none")),
            heard=heard, detail=detail)
        self.settings_screen.note_beep(note, warn=warn)
        return played and heard is not False

    def test_voice(self) -> None:
        if self.settings_screen is None:
            return
        self.voice.warm()
        line = "Radio check. Box this lap or next."
        # Synchronously, and report what happened rather than that it was
        # queued: this button exists because he is in a headset and cannot see
        # whether a sound came out, which is exactly the case where a false
        # success is worst. Speaking is still not the same as being heard, so
        # the endpoint meter answers the second half of the question.
        outcome: dict[str, object] = {}

        def play() -> None:
            outcome["spoke"], outcome["why"] = self.voice.say_now(line)

        heard, detail = self._confirm_audio(
            play, device=self._chosen_output() or None)
        spoke = bool(outcome.get("spoke", False))
        note, warn = self._audio_verdict(
            acted=spoke,
            failed=f"Nothing came out - {outcome.get('why', '')}. "
                   f"Check the output device and the log",
            worked=f"Said it through {self.voice.engine_name}: “{line}”",
            heard=heard, detail=detail)
        self.settings_screen.note_beep(note, warn=warn)

    def _audio_verdict(self, *, acted: bool, failed: str, worked: str,
                       heard: bool | None, detail: str) -> tuple[str, bool]:
        """What to tell the driver, given what the app did and what the card
        actually rendered.

        Three outcomes, not two, and the third is the point of the whole
        exercise: **the app played it and the card did not**. That is what a
        dead endpoint looks like from in here, and it used to read as success
        in green. `heard is None` is a fourth state - unmeasurable - and is
        deliberately not reported as either, because claiming a measurement
        that was not taken is how this class of fault hides.
        """
        if not acted:
            return f"{failed}.", True
        if heard is False:
            return (f"{worked}, but no audio reached "
                    f"{self._where_he_listens()} - {detail}. The device is "
                    f"accepting sound and dropping it; choose another.", True)
        if heard is None:
            return f"{worked}. Could not verify it reached the sound card.", False
        return f"{worked} - {detail}.", False

    def probe_button(self, listening: bool) -> None:
        """Watch for the configured key and say when it is pressed.

        The button is on a wheel, mapped through Fanatec's software, and the
        app cannot see any of that. Pressing it here is the only proof.
        """
        if self.settings_screen is None:
            return
        if self._button_probe is not None:
            self._button_probe.stop()
            self._button_probe = None
        if not listening:
            self.settings_screen.set_listening(False)
            self.settings_screen.note_ptt("Stopped listening.")
            return

        key = self.settings_screen.values().ptt_key
        probe = best_listener(key)
        if probe is None:
            self.settings_screen.set_listening(False)
            self.settings_screen.note_ptt(
                "No keyboard hook on this machine, so the button cannot be "
                "read at all. Check the log.", warn=True)
            return

        # Through the bridge, not straight into the label: pynput dispatches
        # these on its own daemon thread, and `note_ptt` calls setText and
        # setStyleSheet. That is the cross-thread widget write this controller
        # already documents fixing one method along, left behind on this path.
        probe.start(
            lambda: self.bridge.button_probed.emit(f"{key} down - held."),
            lambda: self.bridge.button_probed.emit(
                f"{key} released. That is the button."))
        self._button_probe = probe
        self.settings_screen.set_listening(True)

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
        intent = self.practice.practice_intent()
        sheet = self.store.sheet_for(event["car_name"] or "", intent)
        if sheet is None:
            sheets = self.store.list_setup_sheets(event["car_name"] or "")
            sheet = sheets[0] if len(sheets) == 1 else None
            if sheet is None and sheets:
                self.practice.set_status(
                    f"No {intent} sheet on file for this car, and it has "
                    f"{len(sheets)} others - this run is recorded without one. "
                    f"Load the {intent} sheet on the Event screen.")
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
        self.bridge.quali = QualifyingCoach(
            window=window, reference=reference,
            speak=self.voice.say if speaks else None, mid_lap=mid_lap)
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

    def start_haptics(self) -> bool:
        """Open the transducer for this session, if the driver wants it.

        Returns whether anything is now running. A False is not a failure the
        session cares about: an output must never be able to stop the app
        recording, so this reports and the run goes on either way.
        """
        if not self.settings.haptics_enabled or self.bridge.haptics is not None:
            return self.bridge.haptics is not None
        engine = HapticsEngine(
            device=self.settings.haptics_device or transducer.DEVICE_NAME,
            master=self.settings.haptics_gain)
        if not engine.start():
            log("haptics").warning(
                "no haptics this session: %s", engine.error)
            return False
        self.bridge.effects.reset()
        self.bridge.haptics = engine
        # A fresh watchdog per engine: its cadence baseline and its recovery
        # ladder belong to this stream, not to whatever the last session did.
        self._rig_watchdog = TransducerWatchdog()
        return True

    def test_haptics(self) -> None:
        """Make the transducer do something, here, without going out.

        The whole point of a settings page for hardware: he is in a headset
        while driving and cannot see this screen, so the only way to know the
        strength is right is to feel it standing still. Runs the road-rumble
        effect at half, which is the one he will spend a lap inside.
        """
        if self.settings_screen is None:
            return
        wanted = self.settings_screen.values()
        engine = self.bridge.haptics
        borrowed = engine is None
        if borrowed:
            engine = HapticsEngine(
                device=wanted.haptics_device or transducer.DEVICE_NAME,
                master=wanted.haptics_gain)
            if not engine.start():
                self.settings_screen.note_rig(engine.error or
                                              "The transducer would not open.",
                                              warn=True)
                return
        else:
            # Live session: honour the number in the box rather than the one
            # the session started with, so turning it up can be judged now.
            engine.set_master(wanted.haptics_gain)

        names = list(self.bridge.effects.NAMES)
        levels = [0.0] * (len(names) + len(self.bridge.effects.MODIFIERS))
        levels[names.index("road")] = 0.5
        try:
            deadline = _monotonic() + 2.0
            while _monotonic() < deadline:
                engine.set_intensities(levels)
                QApplication.processEvents()
                time.sleep(0.02)
            engine.silence()
        finally:
            if borrowed:
                engine.stop()
        self.settings_screen.note_rig(
            f"Road rumble at half, {wanted.haptics_gain:.1f}x. Felt about "
            f"right? If it wants to be stronger, turn the amplifier up "
            f"first - this control drives the limiter and the duty cycle, "
            f"and its own knob does not.")

    def stop_haptics(self) -> None:
        engine, self.bridge.haptics = self.bridge.haptics, None
        self._rig_watchdog = None
        if engine is not None:
            engine.stop()

    def start_wind(self) -> bool:
        """Bring the fans up for this session, if the driver wants them.

        The worker thread finds the device itself and keeps trying, so a wind
        sim that is switched on halfway through a session joins in rather than
        staying dark until the next one.
        """
        if not self.settings.wind_enabled or self.bridge.wind is not None:
            return self.bridge.wind is not None
        sim = WindSim()
        sim.start()
        self.bridge.wind_curve.reset()
        # **Scale the fans to the circuit, not to the car.** An event is one
        # car at one circuit, so its recorded top speed is the pair's and it
        # is the speed the fans should reach full at. NULL on an event nobody
        # has driven yet, and the curve then falls back to the car's broadcast
        # maximum and says which it used - see `WindCurve.scale_kph`.
        event = self.active_event()
        self.bridge.wind_curve.observed_top_kph = (
            event["observed_top_kph"]
            if event is not None and "observed_top_kph" in event.keys()
            else None)
        self.bridge.wind = sim
        return True

    def stop_wind(self) -> None:
        sim, self.bridge.wind = self.bridge.wind, None
        if sim is not None:
            # Zero before letting go. The firmware's deadman would catch it a
            # second later, but a second of wind after the session ended is a
            # second of wondering whether it is stuck.
            sim.stop_fans()
            sim.shutdown()

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

    def _hud_sampler(self):
        """The live gauge reader, built on first use, or None if it is off.

        **Nothing about it may reach the race path.** It is constructed here
        rather than at start-up so that a driver who never turns it on never
        opens a socket, and every failure inside it is logged and swallowed -
        the lap is recorded whatever the gauge does.
        """
        if not self.settings.hud_wear_enabled:
            return None
        existing = getattr(self, "_hud", None)
        if existing is not None:
            return existing
        from pitcrew.telemetry.hud import LiveWearSampler, ObsSource

        sampler = LiveWearSampler(
            ObsSource(self.settings.obs_host, self.settings.obs_port,
                      self.settings.obs_password),
            self._write_hud_wear)
        sampler.start()
        self._hud = sampler
        return sampler

    def _write_hud_wear(self, lap_id: int, wear: dict) -> None:
        """Worker thread. Writes the reading and nothing else.

        `set_lap_wear` already refuses to let a video reading overwrite one the
        driver gave: CLAUDE.md makes his report primary evidence and this
        corroboration, so where the two disagree the disagreement stays visible
        instead of being settled by whichever arrived last.
        """
        try:
            self.store.set_lap_wear(
                lap_id, wear.get("fl"), wear.get("fr"),
                wear.get("rl"), wear.get("rr"), source=WEAR_HUD_VIDEO)
        except Exception as exc:                             # noqa: BLE001
            log("hud").warning("could not store lap %s wear: %s", lap_id, exc)

    def _stop_hud_sampler(self) -> None:
        sampler, self._hud = getattr(self, "_hud", None), None
        if sampler is not None:
            sampler.stop()

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
            self.store.end_session(self.session_id)
            log("session").info("practice session %s closed", self.session_id)
            self.session_id = None
            self.session_kind = None

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
        elif event:
            self.practice.set_status(self._idle_status(event))

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

    def _on_lap_completed(self, lap, rows) -> None:
        """Qt thread: compress, store, and put the lap on the rack."""
        if self.session_id is None:
            return
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

        # **One gauge reading per crossing, off this thread.** GT7 sends no
        # wear channel and he will not record it by hand, so the only source
        # is the capture that is running anyway. The request returns at once
        # and may be dropped; nothing here waits on it, and a fragment never
        # gets one because it is not a lap.
        sampler = self._hud_sampler()
        if sampler is not None:
            sampler.request(lap_id)
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
        ))

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
        )
        if call is None:
            return
        spoken = call.spoken()
        if self._engineer_speaks:
            self.voice.say(spoken)
        self.ptt.last_call = spoken
        if self.race_screen is not None:
            self.race_screen.set_status(spoken)

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
        for lap_num in fuel_implausible_laps(rows, capacity):
            for row in rows:
                if row.lap_num == lap_num and not row.excluded:
                    row.excluded = True
                    row.exclusion_reason = "fuel-implausible"

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
        """
        for session in self.store.list_sessions(event_id, "practice"):
            capacity = session["fuel_capacity_l"]
            if capacity:
                return float(capacity)
        return None

    # A rendered peak below this is a quiet moment, not a signal, and asking
    # the card whether it played it would prove nothing either way.
    _AUDIBLE_PEAK = 0.02
    # The last health check's outcome, written by the meter thread and read by
    # the next report. **The success path used to record nothing**, and that
    # cost a diagnosis: in session 39 the endpoint wedged below the audio
    # engine, the engine kept metering the app's own signal back, and every
    # check passed silently - a check that passes was indistinguishable in the
    # log from one that never ran. This line cannot see below the engine
    # either (nothing in software certifies the piston), but it separates
    # "checked, engine renders" / "not asked, too quiet" / "unreadable", and a
    # driver reporting dead haptics against a logged healthy endpoint now
    # isolates the fault to below the engine in one line instead of a night
    # of forensics.
    _endpoint_note = "endpoint not yet asked"
    # Judges the endpoint's numbers and holds the recovery ladder. Created
    # with the engine in `start_haptics`; lazily here only so a bridge wired
    # by hand in a test still gets one.
    _rig_watchdog: TransducerWatchdog | None = None

    def _check_transducer_is_heard(self, haptics) -> None:
        """Did the card play what we rendered, or only accept it?

        **This session is why.** The log read `blocks 10767 · fades 0 ·
        running True` for a whole lap while the transducer produced nothing at
        all - the app synthesised, the card took every sample, and the driver
        felt none of it. Windows reported the device present, allowed,
        unmuted, at volume 50, and its own test tone was silent on it too, so
        the fault was the hardware. But nothing in here said so: every
        indicator was green for a device rendering silence.

        That is precisely the failure `endpoint_meter` exists to catch, and it
        was only ever wired to the settings-screen test button - the one place
        the driver is not looking while racing.

        Two halves make the claim: `take_recent_peak` says whether WE produced
        a signal, and the endpoint's own meter says whether the card rendered
        one. Loud in and nothing out is a dead transducer, and nothing else
        looks like that.

        Runs on its own thread. The meter needs a few hundred milliseconds to
        say anything, and spending that on the Qt thread would be a visible
        stutter every ten seconds of a race.
        """
        # The degraded latch stays visible on every path, including the ones
        # that never reach the meter - it is the one state the driver acts on.
        watchdog = self._rig_watchdog
        exhausted = (" · recovery exhausted"
                     if watchdog is not None and watchdog.degraded else "")
        produced = haptics.take_recent_peak()
        refused = getattr(haptics, "refused", None)
        if refused is not None:
            # **The meter cannot testify about audio nobody sent.** Asking it
            # here would write down "it is accepting the audio and playing
            # none of it" - true, and entirely about a silence of our own
            # making - and the ladder would then be climbing after a fault
            # the app had caused. The frame clock is the instrument for this
            # one, so the ladder runs off that instead.
            self._endpoint_note = f"output REFUSED - {refused}{exhausted}"
            if watchdog is not None:
                self._climb_ladder_off_thread(haptics, watchdog)
            return
        if produced < self._AUDIBLE_PEAK:
            self._endpoint_note = (
                f"endpoint not asked (rendered {produced:.3f}, quiet)"
                f"{exhausted}")
            return
        device = self.settings.haptics_device or transducer.DEVICE_NAME

        def ask() -> None:
            from pitcrew.engineer import endpoint_meter

            try:
                reading = endpoint_meter.poll_briefly(device, seconds=0.4)
            except Exception as exc:                        # noqa: BLE001
                self._endpoint_note = f"endpoint unreadable{exhausted}"
                log("haptics").debug("could not read the endpoint: %s", exc)
                return
            self._act_on_endpoint_reading(haptics, device, produced, reading,
                                          _monotonic())

        threading.Thread(target=ask, name="PitCrewHapticsMeter",
                         daemon=True).start()

    def _act_on_endpoint_reading(self, haptics, device: str, produced: float,
                                 reading, now: float) -> None:
        """Judge one endpoint reading and run the recovery ladder it earns.

        Separated from the worker thread that takes the reading so the whole
        ladder can be driven in a test without a sound card or a thread. Two
        readings are wedge evidence of equal rank: the meter reading nothing
        while we render loud, and - the race of 16 Aug 2026 - the meter
        reading the SAME number every check while what we render varies. The
        old detector only knew the first, so a meter that froze at 0.054 was
        read as healthy for twenty minutes of dead haptics.

        `reading` is an `endpoint_meter.Reading`; a bare float is accepted as
        the plain "this is the peak, no doubt about it" case. The distinction
        that matters is `measured`: a meter that could not be opened used to
        arrive here as `0.0` and be convicted as silence, which is how the
        app came to tell the driver his haptics were dead on the strength of
        an instrument that was never there.
        """
        if self.bridge.haptics is not haptics:
            # A poll still in flight from a session that has since been
            # stopped. It must not deposit its reading into - or lazily
            # create - the next session's watchdog.
            return
        reading = endpoint_meter.Reading.of(reading)
        watchdog = self._rig_watchdog
        if watchdog is None:
            watchdog = self._rig_watchdog = TransducerWatchdog()
        exhausted = " · recovery exhausted" if watchdog.degraded else ""
        if not reading.measured:
            # **"Cannot measure" is not "failed", and no rung of the ladder
            # is earned by it.** Written down so a driver reporting dead
            # haptics against a silent log still lands on the right line.
            watchdog.unmeasurable(reading.detail)
            self._endpoint_note = (
                f"rendered {produced:.2f} · endpoint UNREADABLE "
                f"({reading.detail}){exhausted}")
            log("haptics").warning(
                "the transducer rendered a peak of %.3f and the endpoint "
                "meter for %s could not be read (%s). That is a fact about "
                "the meter and none at all about the device - nothing is "
                "being recovered off it.", produced, device, reading.detail)
            return
        watchdog.note_endpoint(reading.endpoint, reading.matches)
        watchdog.note_stream_changed(getattr(haptics, "last_open_changed", ()))
        heard = reading.peak
        if heard > endpoint_meter.SILENT_PEAK:
            verdict = watchdog.judge(produced, heard, now)
            if verdict == "live":
                # The engine renders what we produce. This says nothing about
                # the piston - session 39's wedge sat below the engine and
                # passed this check throughout - which is exactly why the
                # value is written down rather than silently returned past.
                watchdog.settled(now)
                self._endpoint_note = (
                    f"rendered {produced:.2f} · endpoint {heard:.3f}"
                    f"{exhausted}")
                self._deliver_rig_notice(watchdog)
                return
            if verdict == "unsettled":
                # A number, but not yet a verdict either way - typically the
                # first readings after a value change. Written down as
                # unconfirmed; no recovery is planned off it and no recovery
                # is declared to have worked off it.
                self._endpoint_note = (
                    f"rendered {produced:.2f} · endpoint {heard:.3f} "
                    f"(unconfirmed){exhausted}")
                return
            run = watchdog.stale_details()
            self._endpoint_note = (
                f"rendered {produced:.2f} · endpoint STALE "
                f"(frozen at {heard:.3f}){exhausted}")
            # One ERROR when the run first convicts; the polls after it say
            # nothing new, and the race night would have written this line
            # 119 times. The status line above carries STALE every cycle.
            # `first` is latched by the watchdog on the candidate itself -
            # keying on count == needed here missed the conviction when the
            # cadence corroboration lowered `needed` between polls.
            writer = (log("haptics").error
                      if run["first"]
                      else log("haptics").debug)
            writer(
                "the transducer rendered varying peaks (%.2f-%.2f) and %s "
                "has metered exactly %.3f for %d checks. A meter on a live "
                "signal jitters - this one is dead, and the endpoint behind "
                "it has stopped rendering, which is the same wedge as "
                "metering nothing.%s", run["rendered_low"],
                run["rendered_high"], device, heard, run["count"],
                (" The block cadence dropped at the same time, which "
                 "corroborates a device-side drop."
                 if watchdog.corroborated(now) else ""))
        else:
            watchdog.silent(now)
            self._endpoint_note = (
                f"rendered {produced:.2f} · endpoint SILENT{exhausted}")
            # Deliberately an error rather than a warning. The driver cannot
            # see this screen, and a transducer that is accepting audio and
            # playing none of it is indistinguishable from a working one by
            # every other measure the app has.
            #
            # **Hedged when it has to be.** A silent meter is only a claim
            # about the transducer when there was one endpoint it could have
            # meant and the stream is still on the terms it opened with.
            log("haptics").error(
                "the transducer rendered a peak of %.3f here and %s metered "
                "nothing - it is accepting the audio and playing none of "
                "it.%s", produced, device,
                (" This cannot be relied on: " + "; ".join(watchdog.doubts())
                 + ". If the seat is still working, the meter is not "
                   "watching what the stream is feeding."
                 if watchdog.uncertain else ""))
        # **And then do something about it.** This exact wedge has needed a
        # laptop restart from the seat more than once, and a log line is not
        # a recovery. Reopen in place first; if the evidence comes straight
        # back - the "came and went" flapping - tear down and rebuild from a
        # fresh device list, a capped number of times, and then say so once
        # and stand down rather than hammer a device that is gone.
        self._climb_ladder(haptics, watchdog, now)

    def _climb_ladder(self, haptics, watchdog, now: float) -> None:
        """One rung, whichever instrument earned it.

        Inline and synchronous, so the whole ladder can still be driven in a
        test without a sound card or a thread. Callers that are on the Qt
        thread go through `_climb_ladder_off_thread` instead, because
        `rebuild` stands back for a second before it reopens.
        """
        action = watchdog.plan_recovery(now)
        if action == "reopen":
            haptics.recover()
            watchdog.reopened(now)
        elif action == "rebuild":
            outcome = haptics.rebuild()
            if outcome is not None:
                # None is the driver's own stop cutting the rebuild short -
                # not an attempt, so not spent against the cap.
                watchdog.rebuilt(outcome, now)
        self._deliver_rig_notice(watchdog)

    # A rebuild outlives the ten-second cycle that started it, and two of
    # them racing would each tear down the other's stream.
    _ladder_busy = False

    def _climb_ladder_off_thread(self, haptics, watchdog) -> None:
        """The same rung, for callers that must not block."""
        if self._ladder_busy:
            return
        self._ladder_busy = True

        def climb() -> None:
            try:
                self._climb_ladder(haptics, watchdog, _monotonic())
            finally:
                self._ladder_busy = False

        threading.Thread(target=climb, name="PitCrewHapticsLadder",
                         daemon=True).start()

    def _apply_clock_verdict(self, haptics, watchdog) -> None:
        """Refuse the output when the card is not pulling it at 48 kHz.

        `HapticsEngine._open` already refuses a stream that NEGOTIATES a rate
        the mix is not generated for, because the amplifier passes one band
        and the driver's verdict on the alternative is that wrong output is
        worse than not being on. This is that same rule applied to the rate
        the card turns out to be pulling at - not the same number, and on
        17 Aug 2026 not the same answer: the stream opened at 48000, was
        pulled at 30611, and drove the piston with everything transposed
        0.64x for nineteen minutes while the app logged what was wrong.

        Spoken both ways, because a seat that has gone quiet on purpose is
        indistinguishable from one that has died, and he is in a headset with
        no way to check.
        """
        clock = watchdog.clock_hz
        if watchdog.clock_suspect and clock is not None:
            ratio = clock / float(transducer.SAMPLE_RATE)
            reason = (f"the card is pulling about {clock:.0f} frames a "
                      f"second against the {transducer.SAMPLE_RATE} the mix "
                      f"is generated at, so every effect would arrive "
                      f"transposed by {ratio:.2f}x")
            if haptics.refuse(reason):
                log("haptics").error(
                    "nothing further is being sent to the transducer: %s. "
                    "The road bed at %.0f Hz would arrive at %.0f Hz and the "
                    "amplifier passes %.0f-%.0f Hz, so the cues would be in "
                    "the wrong places rather than merely weak, which the "
                    "driver has said is worse than none. The stream is left "
                    "open so the frame clock can still be watched.",
                    reason, 38.0, 38.0 * ratio,
                    transducer.BAND_LOW_HZ, transducer.BAND_HIGH_HZ)
                self.voice.say(
                    "Haptics muted. The sound card is running them at the "
                    "wrong speed, so every cue would land in the wrong "
                    "place. I have stopped sending rather than give you a "
                    "wrong one.")
            return
        if haptics.allow():
            log("haptics").warning(
                "the transducer's frame clock is back at the rate the mix is "
                "generated for, so it is being sent to again.")
            self.voice.say("Haptics are back.")

    def _deliver_rig_notice(self, watchdog) -> None:
        """The one operational instruction, where the driver will get it.

        The log line carries the evidence; the spoken line is the seam that
        reaches a man in a headset. `take_notice` is one-shot, so neither can
        repeat.
        """
        notice = watchdog.take_notice()
        if notice is None:
            return
        written, spoken = notice
        log("haptics").error(written)
        self.voice.say(spoken)

    # Below this an effect was not doing anything worth writing down.
    _EXPLAIN_FLOOR = 0.01

    def _log_haptic_state(self, haptics) -> None:
        """One line naming every effect that was actually contributing.

        Deliberately only the ones above the floor: a report listing seven
        effects of which five are at zero is a report nobody reads, and the
        interesting case is almost always one or two of them.
        """
        try:
            rows = [r for r in haptics.explain() if r["final"] > self._EXPLAIN_FLOOR]
        except Exception as exc:                            # noqa: BLE001
            log("haptics").debug("could not read the mix: %s", exc)
            return
        # **Silence is logged, not skipped, and skipping it cost a diagnosis.**
        #
        # Reported from the seat: "haptics died on second lap". The log for
        # that minute held block counts and nothing else - no mix line, no
        # state line - because this returned early whenever every effect was
        # below the floor. The one event worth diagnosing produced the one
        # gap in the evidence.
        #
        # It was then diagnosed WRONGLY from a neighbouring subsystem. The
        # wind level read 0.00 over the same ten seconds, so the car looked
        # parked. The driver said otherwise and the stored frames agreed with
        # him: 1,320 of a possible 1,320 for that stretch, mean 173 km/h,
        # minimum 59, no gaps. Two outputs silent, one recorder perfectly
        # happy, and nothing written down that could separate them.
        parts = [f"{r['effect']} {r['final']:.3f}@{r['hz']:.0f}Hz"
                 + (f" -{r['ducked_by']*100:.0f}%" if r["ducked_by"] > 0.05 else "")
                 for r in rows]
        log("haptics").info("mix: %s", " · ".join(parts) if parts
                            else "SILENT - every effect under the floor")
        car = self.bridge.effects.explain()
        # **The inputs, not only the verdicts.** Silence has several causes and
        # they are indistinguishable without these: a car in the garage should
        # be silent and a car at 173 km/h should not. A stream that has gone to
        # zeros without dropping a packet then shows up here as a
        # contradiction rather than as an absence.
        inputs = car["inputs"]
        # `lock@` is the learned lock threshold. Session 39 was diagnosed
        # blind on exactly this number: the cue collapsed because the
        # threshold had climbed, and the climb was inferred from code because
        # nothing had written the value down.
        log("haptics").info(
            "car: %.0f km/h · thr %.2f brk %.2f · traction %s %.2f (%s, %s) · "
            "brake %s %.2f (%s, lock@%.2f) · rotation %s %.2f (%s) · "
            "unload %.2f",
            inputs["speed_ms"] * 3.6, inputs["throttle"], inputs["brake"],
            car["traction"]["state"], car["traction"]["level"],
            car["traction"]["witness"], car["traction"]["confidence"],
            car["brake"]["state"], car["brake"]["level"], car["brake"]["axle"],
            car["brake"]["lock_threshold"],
            car["rotation"]["state"], car["rotation"]["level"],
            car["rotation"]["confidence"], car["load"]["unload"])

    def _report_rig(self) -> None:
        """Write down what the outputs are actually doing, once every so often.

        Because two sessions were spent guessing. "The haptics dropped in the
        first corner" and "the wind stopped again" are both symptoms with
        several possible causes, and every number that would separate them -
        how many blocks the transducer rendered, how many it faded out, how
        many the limiter caught, how many frames the fans sent, how many the
        device rejected - was being counted and thrown away.

        A symptom the driver reports an hour later is worth much less than a
        line in the log, and this is cheap.
        """
        haptics = self.bridge.haptics
        if haptics is not None:
            if self._rig_watchdog is None:
                self._rig_watchdog = TransducerWatchdog()
            # The callback count once per cycle is the cadence watchdog's
            # whole diet: the rate falling and staying fallen is the
            # endpoint's audio pump being rebuilt under the stream. The frame
            # count beside it is what says whether the buffer got longer or
            # the clock got slower, which the block count alone cannot.
            self._rig_watchdog.note_cadence(
                haptics.callbacks, _monotonic(),
                frames=getattr(haptics, "frames", None))
            self._apply_clock_verdict(haptics, self._rig_watchdog)
            # The endpoint note is the PREVIOUS cycle's check - the check runs
            # after this line, on its own thread. Ten seconds stale is fine;
            # invisible was the problem.
            clock = self._rig_watchdog.clock_hz
            # **The underrun count sits next to the frame clock because it
            # is the control on it.** A frame clock below nominal says only
            # that fewer frames went out than the mix generated; it does not
            # say whose fault that was. PortAudio's own `output_underflow`
            # does: underruns rising alongside a low clock means the card
            # still wants 48 kHz and we are failing to fill it - the cues are
            # gapped, not transposed - while a low clock with NO underruns is
            # a card genuinely consuming slower, which is the transposition
            # the refusal was written for. On 17 Aug 2026 the app spent a
            # whole race asserting the second without being able to rule out
            # the first.
            underruns = haptics.take_underflows()
            log("haptics").info(
                "blocks %d · %s · fades %d · limited %d · running %s · %s · "
                "underruns %d this cycle (%d total, %d flagged blocks) · "
                "recoveries %d · rebuilds %d",
                haptics.callbacks,
                f"clock {clock:.0f}Hz" if clock is not None else "clock -",
                haptics.faded_out,
                haptics._mix.limited_blocks, haptics.running,
                self._endpoint_note, underruns, haptics.underflows,
                haptics.status_blocks,
                haptics.recoveries, haptics.rebuilds)
            # **What the mix was doing, not just that it was running.**
            #
            # "I felt something odd in turn four" is unanswerable an hour
            # later unless the numbers were written down at the time. One line
            # per report is cheap and it is the difference between diagnosing
            # a cue and re-driving the session to reproduce it.
            self._log_haptic_state(haptics)
            self._check_transducer_is_heard(haptics)
        wind = self.bridge.wind
        if wind is not None and getattr(wind, "state", None) is not None:
            state = wind.state
            log("wind").info(
                "frames %d · resyncs %d · stale %d · failures %d · "
                "level %.2f · connected %s",
                state.frames_sent, state.resyncs, state.stale_bytes,
                state.write_failures, self.bridge.wind_curve.level,
                state.connected)

    def _report_health(self) -> None:
        """Say which of the several silences this one is.

        A listener that never bound, a console that is not streaming, and a
        source filter eating every packet all look identical from the rack -
        no laps appear. Zeros are the one failure mode that survives all the
        way into a setup recommendation, so each gets its own sentence.
        """
        self._health_ticks = getattr(self, "_health_ticks", 0) + 1
        if self._health_ticks % 10 == 0:
            self._report_rig()
        if self.listener is None:
            return
        # The port the listener is actually on. `self.port` is the configured
        # relay port and is not what direct mode binds, so printing it sent
        # him to check a number nothing was listening on.
        port = self.listener.port
        direct = self.listener.heartbeat_to is not None
        upstream = ("the console" if direct else "SimHub")

        if self.listener.bind_error:
            self.practice.set_status(
                f"Port {port} could not be opened: "
                f"{self.listener.bind_error}. Nothing will arrive until that "
                f"is fixed - change the port on the Settings screen, or close "
                f"whatever else is holding it.", warn=True)
        elif self.listener.send_error:
            # Only reachable in direct mode, and it is a different failure
            # from silence: the console was never asked, so of course it is
            # not streaming. Without this the driver was told to check GT7.
            self.practice.set_status(
                f"Could not reach the console at {self.listener.heartbeat_to}: "
                f"{self.listener.send_error}. GT7 streams only to an address "
                f"that has asked it to, so nothing will arrive until this is "
                f"fixed - check the address on the Settings screen and that "
                f"the PS5 is awake.", warn=True)
        elif self.listener.foreign_dropped and not self.listener.total_received:
            self.practice.set_status(
                f"{self.listener.foreign_dropped} packets arrived on "
                f"{port} and every one was refused: they are not from "
                f"{self.listener.source_ip}. Clear the source address on the "
                f"Settings screen if the console moved.", warn=True)
        elif not self.listener.connected:
            if direct:
                why = (f"The console has been asked "
                       f"{self.listener.heartbeats_sent} times and has not "
                       f"answered. Is GT7 running and out of the menus?")
            else:
                why = "Is GT7 running and SimHub relaying?"
            self.practice.set_status(f"No telemetry on {port}. {why}",
                                     warn=True)
        elif self.listener.total_received and not self.listener.decoded:
            # Bytes are arriving and none of them are telemetry. Distinct
            # from silence, and it means something else is on this port.
            self.practice.set_status(
                f"{self.listener.total_received} packets arrived on {port} "
                f"and none decoded. Something other than GT7 is talking on "
                f"this port.", warn=True)
        elif self._parse_errors:
            self.practice.set_status(
                f"{self._parse_errors} packets failed to decode. Check "
                f"{upstream}.", warn=True)
        elif self.bridge.recorder.lost_packets > _LOST_PACKET_BUDGET:
            # Lap distance is INTEGRATED, so a gap is paid for by every metre
            # after it, and corner windows are keyed on lap distance. A lap
            # that lost packets still looks clean on the rack, which is the
            # reason to say so here rather than let it through quietly.
            lost = self.bridge.recorder.lost_packets
            gaps = self.bridge.recorder.stream_gaps
            self.practice.set_status(
                f"The feed has dropped {lost} packets in {gaps} "
                f"break{'' if gaps == 1 else 's'}. Lap distance is integrated "
                f"from the packet clock, so corner positions drift by roughly "
                f"{lost / SAMPLE_HZ:.1f} s of driving.", warn=True)
        elif self.listener.packet_rate and self.listener.packet_rate < 45.0:
            # CLAUDE.md 7: the connection must fail loudly. A feed limping at
            # 20 Hz used to report as healthy - and the recorder converts
            # packet-id deltas into METRES at an assumed flat 60 Hz, so a
            # degraded rate silently skews lap distance and every corner
            # window derived from it.
            self.practice.set_status(
                f"Telemetry is arriving at {self.listener.packet_rate:.0f} Hz, "
                f"not 60. Lap distance is derived from the packet clock, so "
                f"corner positions will be off until this is fixed.",
                warn=True)

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
        # **The plan carries the two numbers it expects to execute.** The
        # driver asked for exactly this: a median lap time and a fuel burn
        # stored with the plan, so the engineer has something to reference lap
        # to lap when deciding if and how the plan needs adjusting. Both
        # travel with their sample count and their source, because a burn from
        # three practice laps and one from fourteen are not the same claim.
        practice_laps = len(counted_laps(
            event_lap_inputs(self.store, event["id"], "practice")))
        payload["expects"] = Expectation(
            lap_time_ms=self._inputs.lap_time_ms or None,
            lap_time_samples=practice_laps,
            lap_time_source=PRACTICE,
            fuel_per_lap_l=self._inputs.fuel_per_lap_l,
            fuel_samples=practice_laps,
            fuel_source=PRACTICE,
            wear_per_lap=self._inputs.wear_per_lap,
        ).as_plan()
        # What the plan was built for. Without this the race-day guard
        # has nothing to check against and silently always passes.
        context = self._race_context(event)
        payload["context"] = {
            "car": context.car,
            "track": context.track,
            "layout": context.layout,
            "race_laps": context.race_laps,
            "race_minutes": context.race_minutes,
        }
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

        # How many practice laps stand behind the two figures the plan
        # expects to execute. Every aggregate carries its sample count
        # (CLAUDE.md §4.4): a burn from three laps and one from fourteen are
        # not the same claim, and the driver is about to be told one of them.
        practice_laps = len(counted_laps(
            event_lap_inputs(self.store, event["id"], "practice")))
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
            practice_lap_samples=practice_laps,
            practice_fuel_samples=practice_laps)

        actual = self._race_context(event)
        stored = (plan or {}).get("context")
        planned = PlanContext(**stored) if stored else None
        if not self.race.arm(planned, actual):
            self.race_screen.set_status(
                f"Plan refused: {self.race.refusal}", warn=True)
            self.race = None
            return False

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
        sheet = self.store.sheet_for(event["car_name"] or "", "race")
        if sheet is None:
            sheets = self.store.list_setup_sheets(event["car_name"] or "")
            sheet = sheets[0] if len(sheets) == 1 else None
            if sheet is None and sheets:
                self.race_screen.set_status(
                    f"No race sheet on file for this car, and it has "
                    f"{len(sheets)} others - this race is recorded without "
                    f"one, so its laps carry no compound and the export "
                    f"cannot say what was on the car. Load the race sheet on "
                    f"the Event screen.", warn=True)
        self.bridge.set_sheet_shift_rpm(sheet.shift_rpm if sheet else None)
        self.session_id = self.store.start_session(
            event["id"], "race", setup_sheet_id=sheet.id if sheet else None,
            rehearsal=rehearsal, game_version=self.settings.game_version)
        self.session_kind = "race"
        self.race_run_id = self.store.start_race_run(
            event["id"], approved["id"] if approved else None, self.session_id)

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

    def stop_race(self) -> None:
        self.stop_haptics()
        self.stop_wind()
        if self.listener is not None:
            self.listener.stop()
            self.listener = None
        self._health.stop()
        if self.session_id is not None:
            self.store.end_session(self.session_id)
            self.session_kind = None
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
        call = self.race.handle(event)
        replan = None
        if event.kind is EventKind.LAP_COMPLETED:
            replan = self._check_replan(event.data["lap"], against=call)
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
            if event.kind is EventKind.LAP_COMPLETED and replan is None:
                self._voice_colour(event.data["lap"])
            return

        # Spoken unless the re-planner won the lap. Everything below the voice
        # still happens: the screen shows it and the revision chain records
        # it, because an audit that could not see a call the engineer decided
        # against voicing would make the model look tidier than it was.
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
        """What the engineer is allowed to answer from."""
        if self.race is None:
            return {}
        snapshot = self._race_snapshot()
        # The fuel target for the stop, so "how much fuel do I take" has an
        # answer rather than a refusal.
        stints = (self.race.plan or {}).get("stints") or []
        index = self.race.state.stint_index + 1
        if index < len(stints):
            snapshot["stopFuelL"] = stints[index].get("fuel_l")
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

    def _show_ptt_answer(self, heard: str, said: str) -> None:
        if self.race_screen is not None:
            self.race_screen.show_exchange(heard, said)
        if not heard:
            return
        from pitcrew.engineer.intents import (
            ACCEPT,
            KEEP,
            TYRES_RED,
            match_intent,
        )
        intent = match_intent(heard)
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
            self.race.adopt(offer.stint_laps)
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
        return fuel_target_l(race.state), race.state.fuel_per_lap_l

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
        # Close the session before anything else. Shutting the window while
        # recording used to leave `ended_at` null, which is exactly what a
        # crash leaves - so a clean exit was indistinguishable from a lost one.
        if self.session_id is not None:
            self.store.end_session(self.session_id)
            log("session").info("session %s closed on shutdown",
                                self.session_id)
            self.session_id = None
        self.stop_haptics()
        self.stop_wind()
        self._stop_hud_sampler()
        if self.listener is not None:
            self.listener.stop()
        if self._button_probe is not None:
            self._button_probe.stop()
            self._button_probe = None
        self._health.stop()
        self.ptt.stop()
        self.voice.stop()
