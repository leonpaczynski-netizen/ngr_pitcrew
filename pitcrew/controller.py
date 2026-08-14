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
from dataclasses import replace
from pathlib import Path
from time import monotonic as _monotonic

from PyQt6.QtCore import QObject, QTimer, pyqtSignal
from PyQt6.QtWidgets import QApplication

from pitcrew import settings
from pitcrew.analysis.gameclock import clock, read_clock
from pitcrew.analysis.incidents import (
    find_incidents,
    read_rows,
    stored_or_read,
)
from pitcrew.analysis.runs import auto_out_laps, carry_compound
from pitcrew.diagnostics import log
from pitcrew.engineer.ptt import (
    PushToTalk,
    best_listener,
    best_recogniser_for,
    best_semantic_matcher,
)
from pitcrew.engineer.shift_beep import ShiftBeep
from pitcrew.engineer.voice import Voice
from pitcrew.export.build import _rows_to_laps, build_event_export
from pitcrew.export.payload import APP_VERSION, ExportRefused, to_json
from pitcrew.prompts.build import KIND_LABELS, PromptRefused, build_prompt
from pitcrew.prompts.context import gather
from pitcrew.prompts.report import DriverReport
from pitcrew.prompts.templates import PROMPT_VERSION
from pitcrew.setup.sheet import RangeRecord, SetupError, SetupSheet
from pitcrew.store import catalogs
from pitcrew.store.db import Store
from pitcrew.race.coordinator import PlanContext, RaceCoordinator
from pitcrew.race.replan import assess, observed_fuel_per_lap
from pitcrew.strategy.evidence import build_inputs
from pitcrew.strategy.model import StrategyImpossible, recommend
from pitcrew.telemetry.listener import UDPListener, probe_port
from pitcrew.telemetry.capture import CaptureWriter
from pitcrew.telemetry.recorder import FRAME_FIELDS
from pitcrew.telemetry.packet import packet_format_for, parse_packet
from pitcrew.telemetry.recorder import LapRecorder
from pitcrew.telemetry.session_state import (
    EventKind,
    SessionKind,
    SessionState,
)
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


class TelemetryBridge(QObject):
    """Turns the packet stream into Qt signals, on the right threads."""

    lap_completed = pyqtSignal(object, object)   # Lap, detached frame rows
    session_event = pyqtSignal(object)           # every event, for the race
    stream_seen = pyqtSignal(object)             # first packet's fixed facts
    parse_failed = pyqtSignal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.state = SessionState(SessionKind.PRACTICE)
        self.recorder = LapRecorder()
        self._announced = False
        # A raw capture sink, off unless the driver turned it on. It is a tee
        # on this callback rather than a second socket on purpose: SimHub
        # relays and this app never heartbeats the console, so the packet
        # format is whatever SimHub asked for. A capture tool that opened its
        # own socket and heartbeated would latch a different format and take
        # the stream away from the app it is meant to be observing.
        self.capture = None
        self.capture_formats: set[str] = set()
        self.capture_unparsed = 0
        # On the telemetry thread on purpose: a shift beep routed through
        # the Qt event loop arrives after the corner it was for.
        self.shift_beep = ShiftBeep(enabled=False)
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

    def on_packet(self, data: bytes) -> None:
        """Called on the UDP thread for every datagram."""
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
            return

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
        self._button_probe = None
        self.ptt = PushToTalk(
            snapshot=self._ptt_snapshot,
            speak=self.voice.say,
            recogniser=best_recogniser_for(self.settings.speech_backend),
            listener=best_listener(self.settings.ptt_key),
            on_answer=self._on_ptt_answer,
            # Only Moonshine returns free dictation, so only Moonshine needs
            # the semantic gate. SAPI's closed grammar is exact already.
            matcher=(best_semantic_matcher()
                     if self.settings.speech_backend == settings.SPEECH_MOONSHINE
                     else None),
            sensitivity=self.settings.speech_sensitivity)
        self._plans: list = []
        self._inputs = None

        self.bridge = TelemetryBridge(self)
        self.listener: UDPListener | None = None
        self.session_id: int | None = None
        self._parse_errors = 0
        self._store_errors = 0

        self.bridge.lap_completed.connect(self._on_lap_completed)
        self.bridge.stream_seen.connect(self._on_stream_seen)
        self.bridge.parse_failed.connect(self._on_parse_failed)
        self.bridge.session_event.connect(self._on_race_event)

        self.event_screen.saved.connect(self._on_event_saved)
        self.event_screen.discarded.connect(self.discard_event_edits)
        self.event_screen.switched.connect(self.switch_event)
        self.event_screen.catalog_extended.connect(
            self._on_catalog_extended)
        self.practice.recording_toggled.connect(self._on_recording_toggled)
        self.practice.lap_changed.connect(self._on_lap_changed)
        self.practice.export_requested.connect(self._on_export)
        self.practice.practice_mode_changed.connect(self._on_practice_mode)
        if self.strategy is not None:
            self.strategy.build_requested.connect(self.build_strategy)
            self.strategy.approve_requested.connect(self.approve_strategy)
        if self.race_screen is not None:
            self.race_screen.start_requested.connect(self.start_race)
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

    def _on_catalog_extended(self, kind: str, name: str) -> None:
        self.store.add_to_catalog(kind, name)

    # ----------------------------------------------------------------- event

    def active_event(self) -> dict | None:
        event_id = self.store.active_event_id()
        return self.store.get_event(event_id) if event_id else None

    def load_active_event(self) -> None:
        event = self.active_event()
        # The picker is refreshed either way: with no active event it is the
        # only route back to one that does exist.
        self.event_screen.set_events(self.store.list_events(),
                                     event["id"] if event else None)
        if event is None:
            self.practice.set_status(
                "No event yet. Create one on the Event screen first.",
                warn=True)
            return

        sheet = None
        sheets = self.store.list_setup_sheets(event["car_name"] or "")
        if sheets:
            sheet = sheets[0]
        self.event_screen.load(event, sheet)
        self.practice.set_laps(self._rows_for_event(event["id"]))
        self.practice.set_status(self._idle_status(event))
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
        gears = []
        for chunk in data.get("gear_text", "").replace(",", " ").split():
            try:
                gears.append(float(chunk))
            except ValueError:
                continue
        sheet = SetupSheet(
            car_name=data["car_name"],
            sheet_name=data["sheet_name"] or f"{data['name']} sheet",
            values=dict(data["setup_values"]),
            gears=gears,
            performance=dict(data.get("performance") or {}),
            build=dict(data.get("build") or {}),
        )
        return self.store.save_setup_sheet(sheet)

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

    def save_settings(self, new: settings.Settings) -> None:
        """Apply the button and the beep, and remember them."""
        try:
            settings.save(self.store, new)
        except ValueError as exc:
            if self.settings_screen is not None:
                self.settings_screen.note(f"Refused: {exc}", warn=True)
            return

        rebind = new.ptt_key != self.settings.ptt_key
        feed_moved = (new.udp_port != self.settings.udp_port
                      or new.udp_source_ip != self.settings.udp_source_ip)
        self.settings = new
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
                self.settings_screen.note(
                    f"Saved. The feed is still on {self.listener._port} for "
                    f"this session - stop and restart it to move to "
                    f"{new.udp_port}.", warn=True)
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

    def test_feed(self) -> bool:
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
        if self.listener is not None and wanted.udp_port == self.listener._port:
            self.settings_screen.note_feed(
                f"Port {wanted.udp_port} is in use by this session's own "
                f"listener, which is the answer you want. "
                f"{self.listener.total_received} packets so far.")
            return True

        reason = probe_port(wanted.udp_port)
        if reason:
            self.settings_screen.note_feed(
                f"Port {wanted.udp_port} will not open: {reason}. Nothing "
                f"would arrive on it. Another copy of Pit Crew, or another "
                f"program, is holding it.", warn=True)
            return False
        self.settings_screen.note_feed(
            f"Port {wanted.udp_port} is free and this app can bind it. "
            f"Whether GT7 and SimHub are actually sending to it only shows "
            f"once you start practice."
            + (f" Packets from anything other than {wanted.udp_source_ip} "
               f"will be refused." if wanted.udp_source_ip else ""))
        return True

    def test_beep(self) -> bool:
        """Sound the beep now. The only way to know it carries over the engine."""
        if self.settings_screen is None:
            return False
        beep = self.bridge.shift_beep
        played = beep.play_now()
        self.settings_screen.note_beep(
            f"Beeped at the current threshold, {round(beep.rpm)} rpm."
            if played else
            "No beep - this machine has no tone device. Check the log.",
            warn=not played)
        return played

    def test_voice(self) -> None:
        if self.settings_screen is None:
            return
        self.voice.warm()
        line = "Radio check. Box this lap or next."
        self.voice.say(line)
        self.settings_screen.note_beep(
            f"Said it through {self.voice.engine_name}: “{line}”"
            if self.voice.enabled else
            "No speech engine loaded on this machine - check the log.",
            warn=not self.voice.enabled)

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

        probe.start(
            lambda: self.settings_screen.note_ptt(f"{key} down - held."),
            lambda: self.settings_screen.note_ptt(
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
                      kind=kind)

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
        self.engineer.note_reply(
            f"Filed against prompt #{self.prompt_issue_id}. Paste the setup "
            f"block into the Event screen to fit it.")

    # -------------------------------------------------------------- practice

    def _on_recording_toggled(self, wanted: bool) -> None:
        if wanted:
            self.start_practice()
        else:
            self.stop_practice()

    def open_practice_session(self) -> int | None:
        """Start a practice session without touching the network.

        Separate from `start_practice` so the whole recording path can be
        driven without a socket - and so the sheet that was fitted is recorded
        the same way whoever opens the session.
        """
        event = self.active_event()
        if event is None:
            return None

        sheets = self.store.list_setup_sheets(event["car_name"] or "")
        sheet_id = sheets[0].id if sheets else None

        self.bridge.reset()
        self.session_id = self.store.start_session(
            event["id"], "practice", setup_sheet_id=sheet_id,
            practice_mode=self.practice.practice_mode())
        # The rack is NOT cleared. Going out again adds to the session's
        # evidence; it does not replace it. Three runs at one circuit are one
        # body of evidence about one car.
        self.practice.set_laps(self._rows_for_event(event["id"]))
        return self.session_id

    def start_practice(self) -> None:
        if self.open_practice_session() is None:
            self.practice.set_status(
                "Create an event before recording - laps have to belong to "
                "something.", warn=True)
            self.practice.set_recording(False)
            return

        self.voice.warm()
        self.listener = UDPListener("0.0.0.0", self.port, self.bridge.on_packet,
                                    source_ip=self.settings.udp_source_ip)
        self.listener.start()
        self._parse_errors = 0
        self._store_errors = 0
        self._health.start()
        # Off by default: the engineer only answers during a race. On, it is
        # how the button gets tested without committing to a race.
        if self.settings.ptt_enabled and self.settings.ptt_in_practice:
            self.ptt.start()
        log("session").info(
            "practice session %s open, listening on %s", self.session_id,
            self.port)

        self.practice.set_recording(True)
        self.practice.set_status(
            f"Listening on {self.port}. Waiting for the car to go out.")

    def stop_practice(self) -> None:
        if self.listener is not None:
            self.listener.stop()
            self.listener = None
        self._health.stop()
        self.ptt.stop()
        if self.session_id is not None:
            self.store.end_session(self.session_id)
            log("session").info("practice session %s closed", self.session_id)
            self.session_id = None

        self.practice.set_recording(False)
        event = self.active_event()
        rows = self.practice.rows()
        if rows:
            learned = self._learn_clock(event)
            self.practice.set_status(
                f"Session closed. {len(rows)} laps recorded - mark them up, "
                f"then export.{learned}")
        elif event:
            self.practice.set_status(self._idle_status(event))

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

    def _on_lap_changed(self, lap_id: int) -> None:
        """Persist a mark the moment it is made."""
        rows = self.practice.rows()
        row = next((r for r in rows if r.lap_id == lap_id), None)
        if row is None:
            return
        for tagged in carry_compound(rows, lap_id):
            self.store.set_lap_compound(tagged.lap_id, tagged.compound)
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

        # Incidents after the out-laps, because an out-lap loses time it is
        # supposed to lose and must not be judged for it. Answered from the
        # three stored numbers, so no frame blob is decoded to draw the rack.
        for lap_num, incident in find_incidents(rows, stored_or_read).items():
            for row in rows:
                if row.lap_num == lap_num:
                    row.incident = True
                    row.incident_note = incident.describe()
        return rows

    def _report_health(self) -> None:
        """Say which of the several silences this one is.

        A listener that never bound, a console that is not streaming, and a
        source filter eating every packet all look identical from the rack -
        no laps appear. Zeros are the one failure mode that survives all the
        way into a setup recommendation, so each gets its own sentence.
        """
        if self.listener is None:
            return
        if self.listener.bind_error:
            self.practice.set_status(
                f"Port {self.port} could not be opened: "
                f"{self.listener.bind_error}. Nothing will arrive until that "
                f"is fixed - change the port on the Settings screen, or close "
                f"whatever else is holding it.", warn=True)
        elif self.listener.foreign_dropped and not self.listener.total_received:
            self.practice.set_status(
                f"{self.listener.foreign_dropped} packets arrived on "
                f"{self.port} and every one was refused: they are not from "
                f"{self.listener.source_ip}. Clear the source address on the "
                f"Settings screen if the console moved.", warn=True)
        elif not self.listener.connected:
            self.practice.set_status(
                f"No telemetry on {self.port}. Is GT7 running and SimHub "
                "relaying?", warn=True)
        elif self._parse_errors:
            self.practice.set_status(
                f"{self._parse_errors} packets failed to decode. Check the "
                "SimHub relay.", warn=True)

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
        payload["context"] = {
            "car": event["car_name"] or "",
            "track": event["track"] or "",
            "layout": event["layout"],
            "race_laps": int(event["race_laps"] or 0),
        }
        strategy_id = self.store.save_strategy(
            event["id"], payload, label=plan.label(),
            evidence={"missing": self._inputs.missing()})
        self.store.approve_strategy(strategy_id)
        self.strategy.note(
            f"{plan.label()} approved. It is the race plan until you approve "
            "another.")
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

        approved = self.store.get_approved_strategy(event["id"])
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

        actual = PlanContext(
            car=event["car_name"] or "", track=event["track"] or "",
            layout=event["layout"], race_laps=int(event["race_laps"] or 0))
        stored = (plan or {}).get("context")
        planned = PlanContext(**stored) if stored else None
        if not self.race.arm(planned, actual):
            self.race_screen.set_status(
                f"Plan refused: {self.race.refusal}", warn=True)
            self.race = None
            return False

        self.bridge.reset(race=True)
        self.session_id = self.store.start_session(event["id"], "race")
        self.race_run_id = self.store.start_race_run(
            event["id"], approved["id"] if approved else None, self.session_id)

        self.listener = UDPListener("0.0.0.0", self.port, self.bridge.on_packet,
                                    source_ip=self.settings.udp_source_ip)
        self.listener.start()
        self._health.start()

        self.voice.warm()
        self._race_inputs = inputs
        self._race_burns = []
        self._pending_replan = None
        self.ptt.pending_replan = None
        self.ptt.start()
        self.race_screen.clear_log()
        self.race_screen.set_armed(True)
        self.race_screen.set_status(
            "Armed. Waiting for you to cross the line." if plan else
            "Armed with no approved plan - the engineer will call fuel only.")
        return True

    def stop_race(self) -> None:
        if self.listener is not None:
            self.listener.stop()
            self.listener = None
        self._health.stop()
        if self.session_id is not None:
            self.store.end_session(self.session_id)
        if self.race_run_id is not None:
            self.store.finish_race_run(self.race_run_id)
        self.race = None
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
        if self.race_screen is not None:
            self.race_screen.show_exchange(heard, said)
        if self._pending_replan is not None and heard:
            from pitcrew.engineer.intents import ACCEPT, KEEP, match_intent
            intent = match_intent(heard)
            if intent in (ACCEPT, KEEP):
                self._resolve_replan(accepted=intent == ACCEPT)

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
        if accepted and offer.stint_laps:
            self.race.adopt(offer.stint_laps)

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
        if self.listener is not None:
            self.listener.stop()
        if self._button_probe is not None:
            self._button_probe.stop()
            self._button_probe = None
        self._health.stop()
        self.ptt.stop()
        self.voice.stop()
