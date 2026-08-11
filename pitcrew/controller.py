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
from pathlib import Path

from PyQt6.QtCore import QObject, QTimer, pyqtSignal
from PyQt6.QtWidgets import QApplication

from pitcrew.export.build import build_event_export
from pitcrew.export.payload import ExportRefused, to_json
from pitcrew.setup.sheet import SetupError, SetupSheet
from pitcrew.store import catalogs
from pitcrew.store.db import Store
from pitcrew.strategy.evidence import build_inputs
from pitcrew.strategy.model import StrategyImpossible, recommend
from pitcrew.telemetry.listener import UDPListener
from pitcrew.telemetry.packet import parse_packet
from pitcrew.telemetry.recorder import LapRecorder
from pitcrew.telemetry.session_state import (
    EventKind,
    SessionKind,
    SessionState,
)
from pitcrew.ui.practice_screen import LapRow

DEFAULT_PORT = 33741        # SimHub's relay
EXPORT_DIR = Path("exports")
STALE_AFTER_S = 3.0


class TelemetryBridge(QObject):
    """Turns the packet stream into Qt signals, on the right threads."""

    lap_completed = pyqtSignal(object, object)   # Lap, detached frame rows
    stream_seen = pyqtSignal(object)             # first packet's fixed facts
    parse_failed = pyqtSignal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.state = SessionState(SessionKind.PRACTICE)
        self.recorder = LapRecorder()
        self._announced = False

    def reset(self) -> None:
        self.state = SessionState(SessionKind.PRACTICE)
        self.recorder.discard()
        self._announced = False

    def on_packet(self, data: bytes) -> None:
        """Called on the UDP thread for every datagram."""
        packet = parse_packet(data)
        if packet is None:
            # Never degrade into a stream of zeros: a decode failure is
            # reported, because zeros survive all the way into a setup
            # recommendation.
            self.parse_failed.emit()
            return

        if not self._announced:
            self._announced = True
            self.stream_seen.emit({
                "packet_format": packet.packet_format,
                "car_category": packet.car_category,
                "fuel_capacity_l": packet.fuel_capacity,
                "car_id": packet.car_id,
            })

        self.recorder.record_frame(packet)
        for event in self.state.update(packet):
            if event.kind is EventKind.LAP_COMPLETED:
                # Detach inline; compress and store on the Qt thread.
                rows = self.recorder.take_rows()
                self.lap_completed.emit(event.data["lap"], rows)


class PitCrewController(QObject):
    """Owns the store and the live session, and drives the screens."""

    def __init__(self, store: Store, event_screen, practice_screen,
                 strategy_screen=None, *, port: int = DEFAULT_PORT,
                 parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.store = store
        self.event_screen = event_screen
        self.practice = practice_screen
        self.strategy = strategy_screen
        self.port = port
        self._plans: list = []
        self._inputs = None

        self.bridge = TelemetryBridge(self)
        self.listener: UDPListener | None = None
        self.session_id: int | None = None
        self._parse_errors = 0

        self.bridge.lap_completed.connect(self._on_lap_completed)
        self.bridge.stream_seen.connect(self._on_stream_seen)
        self.bridge.parse_failed.connect(self._on_parse_failed)

        self.event_screen.saved.connect(self._on_event_saved)
        self.event_screen.catalog_extended.connect(
            self._on_catalog_extended)
        self.practice.recording_toggled.connect(self._on_recording_toggled)
        self.practice.lap_changed.connect(self._on_lap_changed)
        self.practice.export_requested.connect(self._on_export)
        if self.strategy is not None:
            self.strategy.build_requested.connect(self.build_strategy)
            self.strategy.approve_requested.connect(self.approve_strategy)

        self._health = QTimer(self)
        self._health.setInterval(1000)
        self._health.timeout.connect(self._report_health)

        self.refresh_catalogs()
        self.load_active_event()

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

    def _on_catalog_extended(self, kind: str, name: str) -> None:
        self.store.add_to_catalog(kind, name)

    # ----------------------------------------------------------------- event

    def active_event(self) -> dict | None:
        event_id = self.store.active_event_id()
        return self.store.get_event(event_id) if event_id else None

    def load_active_event(self) -> None:
        event = self.active_event()
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

    def _idle_status(self, event: dict) -> str:
        circuit = event["track"] or "unknown"
        if event["layout"]:
            circuit += f" ({event['layout']})"
        return (f"{event['name']} — {circuit}. "
                "Start practice when you are ready to go out.")

    def _on_event_saved(self, data: dict) -> None:
        """Create or update the event, and the sheet fitted to it."""
        existing = next((e for e in self.store.list_events()
                         if e["name"] == data["name"]), None)
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
        if existing:
            self.store.update_event(existing["id"], **fields)
            event_id = existing["id"]
            verb = "Updated"
        else:
            event_id = self.store.create_event(**fields)
            verb = "Created"

        message = f"{verb} {data['name']}."
        if data["setup_values"] or data["sheet_name"]:
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
        )
        return self.store.save_setup_sheet(sheet)

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
            event["id"], "practice", setup_sheet_id=sheet_id)
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

        self.listener = UDPListener("0.0.0.0", self.port, self.bridge.on_packet)
        self.listener.start()
        self._parse_errors = 0
        self._health.start()

        self.practice.set_recording(True)
        self.practice.set_status(
            f"Listening on {self.port}. Waiting for the car to go out.")

    def stop_practice(self) -> None:
        if self.listener is not None:
            self.listener.stop()
            self.listener = None
        self._health.stop()
        if self.session_id is not None:
            self.store.end_session(self.session_id)

        self.practice.set_recording(False)
        event = self.active_event()
        rows = self.practice.rows()
        if rows:
            self.practice.set_status(
                f"Session closed. {len(rows)} laps recorded - mark them up, "
                "then export.")
        elif event:
            self.practice.set_status(self._idle_status(event))

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
        lap_id = self.store.add_lap(self.session_id, lap, frames=frames)
        self.practice.add_lap(LapRow(
            lap_id=lap_id,
            lap_num=len(self.practice.rows()) + 1,
            lap_time_ms=lap.lap_time_ms,
            fuel_used=lap.fuel_used,
            compound=lap.compound,
            is_out_lap=lap.is_out_lap,
            is_pit_lap=lap.is_pit_lap,
        ))

    def _on_lap_changed(self, lap_id: int) -> None:
        """Persist a mark the moment it is made."""
        row = next((r for r in self.practice.rows() if r.lap_id == lap_id), None)
        if row is None:
            return
        self.store.set_lap_compound(lap_id, row.compound)
        self.store.set_lap_wear(lap_id, row.wear_front, row.wear_rear)
        self.store.exclude_lap(
            lap_id, "struck by hand" if row.excluded else None)

    def _rows_for_event(self, event_id: int) -> list[LapRow]:
        """Every practice lap at this event, numbered continuously.

        The stored numbers restart at 1 each run, so two laps would both read
        "1" on the rack. Display numbering runs through the whole event; the
        database id is what every edit is written against, so renumbering the
        display cannot mis-file a mark.
        """
        return [
            LapRow(
                lap_id=row["id"],
                lap_num=index,
                lap_time_ms=row["lap_time_ms"],
                fuel_used=row["fuel_used"],
                compound=row["compound"],
                is_out_lap=bool(row["is_out_lap"]),
                is_pit_lap=bool(row["is_pit_lap"]),
                excluded=bool(row["excluded"]),
                exclusion_reason=row["exclusion_reason"],
                wear_front=row["wear_front"],
                wear_rear=row["wear_rear"],
            )
            for index, row in enumerate(
                self.store.list_event_laps(event_id, "practice"), 1)
        ]

    def _report_health(self) -> None:
        if self.listener is None:
            return
        if not self.listener.connected:
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
            self.strategy.show_plans([], evidence)
            self.strategy.set_status(str(exc), warn=True)
            return []

        self._plans = plans
        approved = self.store.get_approved_strategy(event["id"])
        approved_index = None
        if approved:
            approved_index = next(
                (i for i, plan in enumerate(plans)
                 if plan.stops == approved["plan"].get("stops")), None)

        self.strategy.show_plans(plans, evidence, approved_index=approved_index)
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
        strategy_id = self.store.save_strategy(
            event["id"], payload, label=plan.label(),
            evidence={"missing": self._inputs.missing()})
        self.store.approve_strategy(strategy_id)
        self.strategy.note(
            f"{plan.label()} approved. It is the race plan until you approve "
            "another.")
        return strategy_id

    # ---------------------------------------------------------------- export

    def _on_export(self) -> str | None:
        event = self.active_event()
        if event is None:
            self.practice.note("Create an event before exporting.", warn=True)
            return None
        try:
            payload = build_event_export(self.store, event["id"])
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
            f"{laps} laps copied to the clipboard. Paste into the Pit Crew "
            f"data box on the Driver Feedback tab. Also saved to {path}.")
        return text

    def _write_export(self, text: str) -> Path:
        EXPORT_DIR.mkdir(parents=True, exist_ok=True)
        stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        path = EXPORT_DIR / f"pitcrew-{stamp}.json"
        path.write_text(text, encoding="utf-8")
        return path

    def shutdown(self) -> None:
        if self.listener is not None:
            self.listener.stop()
        self._health.stop()
