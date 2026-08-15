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
from pitcrew.analysis.runs import auto_out_laps, fuel_implausible_laps, carry_compound
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
from pitcrew.rig.haptics import HapticsEngine
from pitcrew.rig.wind import WindSim
from pitcrew.rig.wind_curve import WindCurve
from pitcrew.engineer import audio_devices, endpoint_meter
from pitcrew.engineer.voice import Voice
from pitcrew.export.build import _rows_to_laps, build_event_export
from pitcrew.export.payload import APP_VERSION, ExportRefused, to_json
from pitcrew.prompts.build import KIND_LABELS, PromptRefused, build_prompt
from pitcrew.prompts.context import gather
from pitcrew.prompts.report import DriverReport
from pitcrew.prompts.templates import PROMPT_VERSION
from pitcrew.setup.parse import parse_reply
from pitcrew.setup.sheet import RangeRecord, SetupError, SetupSheet
from pitcrew.store import catalogs
from pitcrew.store.db import Store
from pitcrew.race.coordinator import PlanContext, RaceCoordinator
from pitcrew.race.replan import assess, observed_fuel_per_lap
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
        self.racing = False
        # Whether the first packet is allowed to set the threshold. Off means
        # the driver picked a number, and the game must not overwrite it.
        self.beep_from_game = True
        self.beep_wanted = True

    def apply_settings(self, settings) -> None:
        self.beep_wanted = settings.beep_enabled
        self.beep_from_game = settings.uses_game_rpm
        if not settings.uses_game_rpm:
            self.shift_beep.rpm = settings.beep_rpm
        # Only the stream can turn the beep on when it follows the game: until
        # a packet arrives there is no threshold to beep at.
        self.shift_beep.enabled = settings.beep_enabled and (
            not settings.uses_game_rpm or self._announced)

    def reset(self, *, race: bool = False) -> None:
        self.state = SessionState(
            SessionKind.RACE if race else SessionKind.PRACTICE)
        self.recorder.discard()
        self._announced = False
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
            if self.beep_from_game:
                usable = 1000 < packet.rpm_alert_min < 20_000
                if usable:
                    self.shift_beep.rpm = float(packet.rpm_alert_min)
                # No threshold from the game and none chosen by the driver
                # means no beep. Falling back to a default would beep at an
                # rpm nobody picked, which is worse than silence.
                self.shift_beep.enabled = self.beep_wanted and usable
                if self.beep_wanted and not usable:
                    log("beep").warning(
                        "GT7 reported a shift-light rpm of %s, which is not a "
                        "threshold - beep stays off. Set one by hand on the "
                        "Settings screen.", packet.rpm_alert_min)
            else:
                self.shift_beep.enabled = self.beep_wanted
            self.stream_seen.emit({
                "packet_format": packet.packet_format,
                "car_category": packet.car_category,
                "fuel_capacity_l": packet.fuel_capacity,
                "car_id": packet.car_id,
            })

        self.recorder.record_frame(packet)
        self.shift_beep.update(packet, _monotonic())
        for event in self.state.update(packet):
            if event.kind is EventKind.LAP_COMPLETED:
                # Detach inline; compress and store on the Qt thread.
                rows = self.recorder.take_rows()
                self.lap_completed.emit(event.data["lap"], rows)
            self.session_event.emit(event)

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
        self._pending_replan = None
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
        return self.store.get_event(event_id) if event_id else None

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
        purpose = data.get("sheet_purpose") or "race"
        name = data["sheet_name"] or f"{data['name']} sheet"
        sheet = SetupSheet(
            car_name=data["car_name"],
            sheet_name=name,
            values=dict(data["setup_values"]),
            gears=gears,
            performance=dict(data.get("performance") or {}),
            build=dict(data.get("build") or {}),
            purpose=purpose,
        )
        sheet_id = self.store.save_setup_sheet(sheet)

        for other_purpose, parsed in (data.get("other_sheets") or {}).items():
            # Named after the sheet on the form where the reply did not name
            # it, so two sheets from one paste never collide on (car, name) -
            # which would silently make the second overwrite the first.
            self.store.save_setup_sheet(SetupSheet(
                car_name=data["car_name"],
                sheet_name=(parsed.sheet_name
                            or f"{name} ({other_purpose})"),
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
        log("settings").info(
            "ptt %s on %r (practice=%s) · beep %s at %s rpm from %s",
            "on" if new.ptt_enabled else "off", new.ptt_key,
            new.ptt_in_practice, "on" if new.beep_enabled else "off",
            round(self.bridge.shift_beep.rpm), new.beep_rpm_source)
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
            worked=f"Beeped at the current threshold, {round(beep.rpm)} rpm",
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
            game_version=(self.active_event() or {}).get("game_version"),
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
        # symptom on the wrong car. Falls back to the most recent sheet
        # of any purpose, because a car with one sheet on file is the
        # normal case and refusing to open a session over it would be
        # bureaucracy.
        intent = self.practice.practice_intent()
        sheet = self.store.sheet_for(event["car_name"] or "", intent)
        if sheet is None:
            sheets = self.store.list_setup_sheets(event["car_name"] or "")
            sheet = sheets[0] if sheets else None
        sheet_id = sheet.id if sheet else None

        self.bridge.reset()
        self.session_id = self.store.start_session(
            event["id"], "practice", setup_sheet_id=sheet_id,
            practice_mode=self.practice.practice_mode(),
            practice_intent=intent)
        self.session_kind = "practice"
        # The rack is NOT cleared. Going out again adds to the session's
        # evidence; it does not replace it. Three runs at one circuit are one
        # body of evidence about one car.
        self.practice.set_laps(self._rows_for_event(event["id"]))
        return self.session_id

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
        levels = [0.0] * len(names)
        levels[names.index("wheels_rumble")] = 0.5
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
        self.practice.set_status(f"{where}. Waiting for the car to go out.")
        self.announce("Recording", "Go out when you are ready.")

    def stop_practice(self) -> None:
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
        self.store.note_stream_facts(
            self.session_id,
            packet_format=facts["packet_format"],
            car_category=facts["car_category"],
            fuel_capacity_l=facts["fuel_capacity_l"])
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
        produced = haptics.take_recent_peak()
        if produced < self._AUDIBLE_PEAK:
            return
        device = self.settings.haptics_device or transducer.DEVICE_NAME

        def ask() -> None:
            from pitcrew.engineer import endpoint_meter

            try:
                heard = endpoint_meter.poll_briefly(device, seconds=0.4)
            except Exception as exc:                        # noqa: BLE001
                log("haptics").debug("could not read the endpoint: %s", exc)
                return
            if heard > endpoint_meter.SILENT_PEAK:
                return
            # Deliberately an error rather than a warning. The driver cannot
            # see this screen, and a transducer that is accepting audio and
            # playing none of it is indistinguishable from a working one by
            # every other measure the app has.
            log("haptics").error(
                "the transducer rendered a peak of %.3f here and %s metered "
                "nothing - it is accepting the audio and playing none of it. "
                "Check the amplifier is on and out of protection; Windows "
                "will still report the device as healthy.",
                produced, device)

        threading.Thread(target=ask, name="PitCrewHapticsMeter",
                         daemon=True).start()

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
            log("haptics").info(
                "blocks %d · fades %d · limited %d · running %s",
                haptics.callbacks, haptics.faded_out,
                haptics._mix.limited_blocks, haptics.running)
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

        self.race = RaceCoordinator(
            plan,
            fuel_per_lap_l=inputs.fuel_per_lap_l if inputs else None,
            wear_per_lap=inputs.wear_per_lap if inputs else None,
            fuel_capacity_l=inputs.fuel_capacity_l if inputs else None)

        actual = self._race_context(event)
        stored = (plan or {}).get("context")
        planned = PlanContext(**stored) if stored else None
        if not self.race.arm(planned, actual):
            self.race_screen.set_status(
                f"Plan refused: {self.race.refusal}", warn=True)
            self.race = None
            return False

        self.bridge.reset(race=True)
        self.session_id = self.store.start_session(
            event["id"], "race", rehearsal=rehearsal)
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
        self._pending_replan = None
        self.ptt.pending_replan = None
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
            self.store.finish_race_run(self.race_run_id)
            self.race_run_id = None
        self.race = None
        # An offer outlives the race that raised it: the buttons stayed live
        # and connected, and Accept then dereferenced `self.race`, which this
        # method had just set to None - straight out of a Qt slot, which aborts
        # the process, immediately after a race and before the export.
        self._pending_replan = None
        self.ptt.pending_replan = None
        if self.race_screen is not None:
            self.race_screen.hide_offer()
        self.ptt.stop()
        if self.race_screen is not None:
            self.race_screen.set_armed(False)
            self.race_screen.set_status("Race closed.")

    def _on_race_event(self, event) -> None:
        """Feed one telemetry event to the race, and say what comes back."""
        if self.race is None:
            return
        call = self.race.handle(event)
        if event.kind is EventKind.LAP_COMPLETED:
            self._check_replan(event.data["lap"])
        if self.race_screen is not None:
            self.race_screen.show_snapshot(self.race.snapshot())
        if call is None:
            return

        if self._engineer_speaks:
            self.voice.say(call.spoken())
        self.ptt.last_call = call.spoken()
        if self.race_screen is not None:
            self.race_screen.show_call(call)
        if self.race_run_id is not None:
            # Every call is recorded, accepted or not: a plan offered and
            # ignored is evidence about the model, and dropping it would make
            # the model look better than it was.
            self.store.append_revision(
                self.race_run_id, call.lap, call.call,
                {"call": call.as_export(), "confidence": call.confidence},
                accepted=False)

    # ------------------------------------------------------------------- ptt

    def _ptt_snapshot(self) -> dict:
        """What the engineer is allowed to answer from."""
        if self.race is None:
            return {}
        snapshot = self.race.snapshot()
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
        if self._pending_replan is not None and heard:
            from pitcrew.engineer.intents import ACCEPT, KEEP, match_intent
            intent = match_intent(heard)
            if intent in (ACCEPT, KEEP):
                self._resolve_replan(accepted=intent == ACCEPT)

    def _note_button_probe(self, text: str) -> None:
        if self.settings_screen is not None:
            self.settings_screen.note_ptt(text)

    def _resolve_replan(self, *, accepted: bool) -> None:
        """Record what the driver did with the offer, and act on it."""
        offer = self._pending_replan
        self._pending_replan = None
        self.ptt.pending_replan = None
        if offer is None or self.race_run_id is None:
            return
        self.store.append_revision(
            self.race_run_id, self.race.state.lap if self.race else 0,
            offer.call() or offer.reason, offer.as_plan(), accepted=accepted)
        if accepted and offer.stint_laps and self.race is not None:
            self.race.adopt(offer.stint_laps)
        # The question is answered, so it stops being asked.
        if self.race_screen is not None:
            self.race_screen.hide_offer()

    # ---------------------------------------------------------------- replan

    def _check_replan(self, lap) -> None:
        """After each lap, ask whether the plan still holds."""
        if self.race is None or not self.race.running:
            return
        if lap.fuel_used > 0:
            self._race_burns.append(lap.fuel_used)

        inputs = self._race_inputs
        verdict = assess(
            laps_done=self.race.state.lap,
            laps_total=self.race.state.laps_total,
            fuel_l=self.race.state.fuel_l,
            planned_fuel_per_lap=self.race.planned_fuel_per_lap_l,
            observed_fuel_per_lap_l=self.race.observed_fuel_per_lap(),
            lap_time_ms=lap.lap_time_ms,
            planned_lap_time_ms=inputs.lap_time_ms if inputs else None,
            current_stops=self.race.stops_planned(),
            inputs=inputs,
            fuel_capacity_l=inputs.fuel_capacity_l if inputs else None,
        )
        if not verdict.offered or self._pending_replan is not None:
            return

        # Offered, never imposed: it stands until he accepts or keeps.
        self._pending_replan = verdict
        self.ptt.pending_replan = verdict.call()
        text = f"{verdict.call()} {verdict.reason}."
        if self._engineer_speaks:
            self.voice.say(text)
        self.last_call = text
        self.ptt.last_call = text
        if self.race_screen is not None:
            self.race_screen.show_offer(verdict)

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
        if self.listener is not None:
            self.listener.stop()
        if self._button_probe is not None:
            self._button_probe.stop()
            self._button_probe = None
        self._health.stop()
        self.ptt.stop()
        self.voice.stop()
