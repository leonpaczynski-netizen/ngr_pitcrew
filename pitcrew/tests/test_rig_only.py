"""Rig-only (Free Run) mode: the rig outputs run without a recording session.

These drive `start_rig_only` / `stop_rig_only` through the real controller and
assert on what reaches (and does not reach) the store. A `FakeUDPListener` stands
in for the real socket so no port is bound and no console is asked. Haptics and
wind are no-ops by default because `haptics_enabled` and `wind_enabled` both
default to False in the test-time settings.

Threading note: `on_packet_rig_only` is normally called on the UDP thread, but
these tests call it directly on the test thread - the same pattern every other
bridge test uses. Nothing in the path needs to be thread-safe for the assertion
to be valid.
"""
from __future__ import annotations

import pytest

import pitcrew.controller as controller_mod
from pitcrew.controller import PitCrewController, TelemetryBridge
from pitcrew.store.db import Store
from pitcrew.ui.event_screen import EventScreen
from pitcrew.ui.practice_screen import PracticeScreen

from .conftest import make_packet, raw_packet
from .test_controller import an_event, qt_app, raw  # noqa: F401


# ---------------------------------------------------------------- test doubles

class FakeUDPListener:
    """A stand-in for `UDPListener` that never opens a socket.

    **Holds the callback** so tests can drive the rig-only path directly,
    without a network. Exposes the properties that `bench._report_health`
    reads so the health routing tests can exercise the full branch without
    a live listener.
    """

    def __init__(self, host: str, port: int, callback, *,
                 source_ip=None, heartbeat_to=None) -> None:
        self._port = port
        self.callback = callback
        self.heartbeat_to = heartbeat_to
        self.source_ip = source_ip
        self.running = False
        # Bench health-line properties; set to the happy-path values so only
        # tests that specifically probe a failure branch have to override them.
        self.bind_error = None
        self.send_error = None
        self.foreign_dropped = 0
        self.total_received = 0
        self.connected = False     # not connected = "no telemetry yet" branch
        self.decoded = 0
        self.heartbeats_sent = 0
        self.packet_rate = 0.0

    @property
    def port(self) -> int:
        return self._port

    def start(self) -> None:
        self.running = True

    def stop(self) -> None:
        self.running = False


@pytest.fixture()
def wired(qt_app, store: Store):           # noqa: F811 - qt_app from import
    """Controller wired with real practice and event screens, no socket."""
    event_screen = EventScreen()
    practice = PracticeScreen()
    controller = PitCrewController(store, event_screen, practice)
    yield controller, event_screen, practice, store
    controller.shutdown()


@pytest.fixture()
def patched(wired, monkeypatch):
    """Wired controller with `UDPListener` replaced by the fake.

    Returns `(controller, event_screen, practice, store, listener_log)` where
    `listener_log` is a list that accumulates every `FakeUDPListener` created
    during the test. Its first entry is the one that `start_rig_only` built.
    """
    controller, event_screen, practice, store = wired
    created: list[FakeUDPListener] = []

    class _CapturingFake(FakeUDPListener):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            created.append(self)

    monkeypatch.setattr(controller_mod, "UDPListener", _CapturingFake)
    yield controller, event_screen, practice, store, created


# ------------------------------------------------------------------- start-up

def test_start_opens_no_session_and_writes_no_sessions_row(patched, store):
    """Free Run must never touch the `sessions` table."""
    controller, *_, _ = patched
    controller.start_rig_only()

    assert controller.session_id is None, "session_id must stay None"
    # Count directly - `list_sessions` needs an event id we may not have.
    row_count = store._conn.execute(
        "SELECT COUNT(*) FROM sessions").fetchone()[0]
    assert row_count == 0, "start_rig_only must not write a session row"


def test_start_rig_only_starts_haptics_and_wind(patched, monkeypatch):
    """The hardware-start methods must be called even when devices are absent.

    `haptics_enabled` and `wind_enabled` default to False so the real
    supervisor returns early without opening a device. What matters is that the
    CODE PATH was entered — a future settings change must not silently skip it.
    """
    controller, *_ = patched
    haptics_calls: list = []
    wind_calls: list = []
    monkeypatch.setattr(controller, "start_haptics",
                        lambda: haptics_calls.append(1) or False)
    monkeypatch.setattr(controller, "start_wind",
                        lambda: wind_calls.append(1) or False)

    controller.start_rig_only()

    assert haptics_calls, "start_haptics was not called"
    assert wind_calls, "start_wind was not called"


def test_listener_callback_is_on_packet_rig_only(patched):
    """The listener must receive the rig-only callback, not the full one.

    Bound methods create a fresh wrapper object on every attribute access, so
    `is` comparison always fails. Compare the underlying function instead.
    """
    controller, *_, created = patched
    controller.start_rig_only()

    assert len(created) == 1
    cb = created[0].callback
    assert cb.__func__ is TelemetryBridge.on_packet_rig_only, (
        "listener callback should be on_packet_rig_only, not on_packet")
    assert cb.__self__ is controller.bridge, (
        "listener callback must be bound to the controller's bridge")


def test_listener_is_started(patched):
    """start() must be called on the listener so it actually runs."""
    controller, *_, created = patched
    controller.start_rig_only()

    assert created[0].running is True


def test_rig_only_flag_is_true_after_start(patched):
    controller, *_ = patched
    controller.start_rig_only()
    assert controller._rig_only_mode is True


def test_start_with_no_active_event_works(patched, store):
    """Free Run does not require an event — it is a hardware test."""
    controller, *_, _ = patched
    # No event created. Must not refuse.
    controller.start_rig_only()
    assert controller._rig_only_mode is True


def test_rig_only_changed_signal_emitted_on_start(patched, qt_app):  # noqa: F811
    """The Event screen needs to know the moment the mode changes."""
    controller, *_ = patched
    received: list[bool] = []
    controller.rig_only_changed.connect(received.append)

    controller.start_rig_only()

    assert received == [True]


# ------------------------------------------------- refusals (both directions)

def test_double_start_is_refused(patched):
    """Calling start twice must not create a second listener."""
    controller, *_, created = patched
    controller.start_rig_only()
    controller.start_rig_only()

    assert len(created) == 1, "second start_rig_only must be a no-op"


def test_start_refused_when_session_is_open(patched, store):
    """An open practice session must block Free Run."""
    controller, _, _, store, _ = patched
    controller._on_event_saved(an_event())
    controller.open_practice_session()          # opens a session without a socket
    assert controller.session_id is not None

    controller.start_rig_only()

    assert controller._rig_only_mode is False


def test_start_refused_when_race_is_armed(wired, monkeypatch):
    """An armed race must block Free Run (no fake listener needed — refused before)."""
    controller, *_ = wired
    # Fake an armed race without going through the full arm sequence.
    from unittest.mock import MagicMock
    fake_race = MagicMock()
    fake_race.armed = True
    fake_race.running = False
    controller.race = fake_race

    controller.start_rig_only()

    assert controller._rig_only_mode is False


def test_start_practice_refused_while_rig_only(patched, qt_app):  # noqa: F811
    """Practice must refuse while Free Run holds the listener."""
    controller, _, practice, _, _ = patched
    controller._on_event_saved(an_event())
    controller.start_rig_only()

    controller.start_practice()

    # Session must not have opened.
    assert controller.session_id is None
    assert "Free Run" in practice.subtitle.text()


def test_start_race_refused_while_rig_only(patched, store, qt_app):  # noqa: F811
    """Race arming must refuse while Free Run holds the listener."""
    from pitcrew.ui.race_screen import RaceScreen
    from pitcrew.ui.strategy_screen import StrategyScreen

    controller, _, _, store, _ = patched

    race_screen = RaceScreen()
    strategy = StrategyScreen()
    controller.race_screen = race_screen
    controller.strategy = strategy

    controller._on_event_saved(an_event())
    controller.start_rig_only()

    result = controller.start_race()

    assert result is False
    assert "Free Run" in race_screen.subtitle.text()


# --------------------------------------------------------------- stop / reset

def test_stop_clears_flag_and_emits_signal(patched, qt_app):  # noqa: F811
    controller, *_ = patched
    received: list[bool] = []
    controller.rig_only_changed.connect(received.append)

    controller.start_rig_only()
    controller.stop_rig_only()

    assert controller._rig_only_mode is False
    assert received == [True, False]


def test_stop_tears_down_listener(patched):
    controller, *_, created = patched
    controller.start_rig_only()
    controller.stop_rig_only()

    assert controller.listener is None
    assert created[0].running is False


def test_stop_is_idempotent(patched):
    """Calling stop twice must not raise."""
    controller, *_ = patched
    controller.start_rig_only()
    controller.stop_rig_only()
    controller.stop_rig_only()       # second call: must be silent
    assert controller._rig_only_mode is False


def test_stop_restores_status_target_to_practice_screen(patched):
    """After stop, bench health messages must go back to the practice screen.

    Bound methods create a new wrapper object on every attribute access, so
    `is` comparison fails. Verify the bound object and the function instead.
    """
    controller, _, practice, *_ = patched
    controller.start_rig_only()
    controller.stop_rig_only()

    target = controller.bench._status_target
    # The restored target must be bound to the practice screen.
    assert getattr(target, "__self__", None) is practice, (
        "bench._status_target was not restored to the practice screen")
    from pitcrew.ui.practice_screen import PracticeScreen
    assert getattr(target, "__func__", None) is PracticeScreen.set_status, (
        "bench._status_target function was not practice.set_status")


# ----------------------------------------- rig-only packet sink (on_packet_rig_only)

def test_full_lap_sequence_writes_zero_sessions_laps_lap_frames(patched, store):
    """Driving packets through the rig-only sink must not touch the DB."""
    controller, _, _, store, _ = patched
    controller.start_rig_only()

    bridge = controller.bridge
    # First packet — car on track.
    bridge.on_packet_rig_only(raw(speed_ms=50.0, fuel_level=92.0,
                                  time_of_day_ms=0))
    # Second packet — lap crossing (last_lap_ms set).
    bridge.on_packet_rig_only(raw(speed_ms=50.0, fuel_level=88.6,
                                  last_lap_ms=93_912, time_of_day_ms=16))
    # Third packet — after the crossing.
    bridge.on_packet_rig_only(raw(speed_ms=50.0, fuel_level=88.0,
                                  time_of_day_ms=32))

    sessions = store._conn.execute(
        "SELECT COUNT(*) FROM sessions").fetchone()[0]
    laps = store._conn.execute(
        "SELECT COUNT(*) FROM laps").fetchone()[0]
    frames = store._conn.execute(
        "SELECT COUNT(*) FROM lap_frames").fetchone()[0]
    assert sessions == 0, "no session row must exist"
    assert laps == 0, "no lap row must exist"
    assert frames == 0, "no frame row must exist"


def test_corrupt_datagram_returns_false_and_emits_parse_failed(patched):
    """A decode failure must report itself, not silently pass."""
    controller, *_ = patched
    controller.start_rig_only()

    failed: list[int] = []
    controller.bridge.parse_failed.connect(lambda: failed.append(1))

    result = controller.bridge.on_packet_rig_only(b"not a GT7 packet")

    assert result is False
    assert failed == [1], "parse_failed signal was not emitted"


def test_sink_returns_true_on_valid_packet(patched):
    """A good decode must return True so the listener can count it."""
    controller, *_ = patched
    controller.start_rig_only()

    result = controller.bridge.on_packet_rig_only(raw(speed_ms=50.0))
    assert result is True


def test_sink_updates_last_packet(patched):
    """last_packet must be updated so Qt-thread readers have a live value."""
    controller, *_ = patched
    controller.start_rig_only()

    controller.bridge.on_packet_rig_only(raw(speed_ms=40.0))
    assert controller.bridge.last_packet is not None
    assert abs(controller.bridge.last_packet.speed_kmh
               - 40.0 * 3.6) < 1.0     # m/s → km/h conversion


def test_sink_never_calls_state_update(patched, monkeypatch):
    """SessionState.update must not be called: it drives lap-crossing logic."""
    controller, *_ = patched
    controller.start_rig_only()

    called: list = []
    monkeypatch.setattr(controller.bridge.state, "update",
                        lambda pkt: called.append(1) or [])

    controller.bridge.on_packet_rig_only(raw(speed_ms=50.0))

    assert called == [], "state.update was called from on_packet_rig_only"


def test_sink_never_calls_recorder_record_frame(patched, monkeypatch):
    """The recorder must not be fed in rig-only mode."""
    controller, *_ = patched
    controller.start_rig_only()

    called: list = []
    monkeypatch.setattr(controller.bridge.recorder, "record_frame",
                        lambda pkt: called.append(1))

    controller.bridge.on_packet_rig_only(raw(speed_ms=50.0))

    assert called == [], "recorder.record_frame was called from on_packet_rig_only"


def test_sink_never_calls_shift_beep_update(patched, monkeypatch):
    """The shift beep must stay silent: it belongs to a recording session."""
    controller, *_ = patched
    controller.start_rig_only()

    called: list = []
    from time import monotonic
    monkeypatch.setattr(controller.bridge.shift_beep, "update",
                        lambda pkt, t: called.append(1))

    controller.bridge.on_packet_rig_only(raw(speed_ms=50.0))

    assert called == [], "shift_beep.update was called from on_packet_rig_only"


# -------------------------------------------- _drive_rig called by both paths

def test_drive_rig_called_by_rig_only_sink(patched, monkeypatch):
    """on_packet_rig_only must route through _drive_rig."""
    controller, *_ = patched
    controller.start_rig_only()

    called: list = []
    original = controller.bridge._drive_rig
    monkeypatch.setattr(controller.bridge, "_drive_rig",
                        lambda pkt: called.append(pkt) or original(pkt))

    controller.bridge.on_packet_rig_only(raw(speed_ms=50.0))

    assert len(called) == 1, "_drive_rig was not called from on_packet_rig_only"


def test_drive_rig_called_by_normal_on_packet(patched, monkeypatch):
    """on_packet (the recording path) must also route through _drive_rig."""
    controller, _, _, store, _ = patched
    controller._on_event_saved(an_event())
    controller.open_practice_session()

    called: list = []
    original = controller.bridge._drive_rig
    monkeypatch.setattr(controller.bridge, "_drive_rig",
                        lambda pkt: called.append(pkt) or original(pkt))

    controller.bridge.on_packet(raw(speed_ms=50.0))

    assert len(called) == 1, "_drive_rig was not called from on_packet"


# ---------------------------------------- state reset on start (rule 11)

def test_start_calls_effects_reset(patched, monkeypatch):
    """Effects state from a prior session must be cleared before rig-only starts."""
    controller, *_ = patched
    calls: list = []
    original = controller.bridge.effects.reset
    monkeypatch.setattr(controller.bridge.effects, "reset",
                        lambda: calls.append(1) or original())

    controller.start_rig_only()

    assert calls, "bridge.effects.reset was not called by start_rig_only"


def test_start_calls_wind_curve_reset(patched, monkeypatch):
    """Wind-curve state from a prior session must be cleared."""
    controller, *_ = patched
    calls: list = []
    original = controller.bridge.wind_curve.reset
    monkeypatch.setattr(controller.bridge.wind_curve, "reset",
                        lambda: calls.append(1) or original())

    controller.start_rig_only()

    assert calls, "bridge.wind_curve.reset was not called by start_rig_only"


def test_bridge_racing_is_false_after_start(patched):
    """The wind curve's racing flag must be cleared to the correct floor."""
    controller, *_ = patched
    controller.bridge.racing = True          # simulate a prior race

    controller.start_rig_only()

    assert controller.bridge.racing is False


def test_start_does_not_call_recorder_discard(patched, monkeypatch):
    """bridge.reset() (which calls recorder.discard) must not be called.

    `bridge.reset()` rebuilds the SessionState and discards the recorder —
    that is the practice-session setup path and it does not belong here.
    """
    controller, *_ = patched
    discarded: list = []
    monkeypatch.setattr(controller.bridge.recorder, "discard",
                        lambda: discarded.append(1))

    controller.start_rig_only()

    assert discarded == [], "recorder.discard was called (bridge.reset was called)"


# ----------------------------------------------- bench health routing

def test_health_routing_uses_rig_only_status_target(patched, qt_app):  # noqa: F811
    """While rig-only, bench health messages must reach the Event screen.

    When the listener has not connected yet, `_report_health` emits the
    "No telemetry" branch. In rig-only mode that must go to `rig_only_status`,
    not to the practice screen's `set_status`.
    """
    controller, *_, created = patched
    controller.start_rig_only()

    # Give the bench a listener it can ask about (the fake, connected=False).
    # `_report_health` is normally called by the health timer; drive it directly.
    received_practice: list = []
    received_rig: list = []
    controller.practice.subtitle  # access to verify practice screen exists

    # Intercept practice.set_status to detect if it is called instead.
    original_practice_status = controller.practice.set_status
    controller.practice.set_status = lambda *a, **kw: received_practice.append(a)
    controller.rig_only_status.connect(
        lambda msg, warn: received_rig.append((msg, warn)))

    # Make the fake listener "connected=False" so the no-telemetry branch runs.
    # The fake's `connected` attribute already defaults to False.
    controller.bench._report_health()

    # Restore.
    controller.practice.set_status = original_practice_status

    assert received_practice == [], (
        "bench wrote to practice.set_status during rig-only mode")
    assert len(received_rig) == 1, (
        "no rig_only_status signal was emitted by _report_health")
    msg, warn = received_rig[0]
    assert "telemetry" in msg.lower() or "console" in msg.lower(), (
        f"unexpected message: {msg!r}")
    assert warn is True


def test_health_does_not_warn_about_recorder_lost_packets_in_rig_only(patched):
    """Stale recorder counters from a prior session must not fire a warning."""
    controller, *_, created = patched
    # Simulate stale lost-packet count from a previous recording session.
    controller.bridge.recorder._lost_packets = 1000
    controller.start_rig_only()

    warnings: list = []
    controller.rig_only_status.connect(
        lambda msg, warn: warnings.append((msg, warn)) if warn else None)

    # Make the fake look healthy so only the lost-packets branch would fire.
    if created:
        created[-1].connected = True
        created[-1].total_received = 100
        created[-1].decoded = 100

    controller.bench._report_health()

    for msg, _ in warnings:
        assert "dropped" not in msg.lower(), (
            f"recorder lost-packet warning fired during rig-only: {msg!r}")


# ----------------------------------------- UI: Free Run button on EventScreen

def test_free_run_button_is_present_on_event_screen(wired, qt_app):  # noqa: F811
    """The event screen must expose a free_run_button widget after wiring."""
    _, event_screen, *_ = wired
    assert hasattr(event_screen, "free_run_button"), (
        "EventScreen has no free_run_button — was wire_rig_only called?")


def test_free_run_button_enabled_with_no_event_no_session(wired, qt_app):  # noqa: F811
    """With nothing open, Free Run must be startable regardless of event."""
    controller, event_screen, *_ = wired
    assert controller.can_start_rig_only is True, (
        "can_start_rig_only should be True with nothing open")
    assert event_screen.free_run_button.isEnabled() is True, (
        "free_run_button must be enabled when can_start_rig_only is True")


def test_free_run_button_click_starts_rig_only(patched, qt_app):  # noqa: F811
    """Clicking Free Run must start the rig-only mode through the controller."""
    controller, event_screen, *_ = patched
    event_screen.free_run_button.click()
    assert controller._rig_only_mode is True, (
        "clicking Free Run must call start_rig_only")


def test_rig_only_changed_true_flips_button_text(patched, qt_app):  # noqa: F811
    """When rig_only_changed fires True, button text must indicate Stop."""
    controller, event_screen, *_ = patched
    controller.start_rig_only()
    text = event_screen.free_run_button.text().lower()
    assert "stop" in text, (
        f"button text after start should contain 'stop', got {text!r}")


def test_rig_only_changed_true_shows_active_status(patched, qt_app):  # noqa: F811
    """When active, the status label must confirm the rig is running."""
    controller, event_screen, *_ = patched
    controller.start_rig_only()
    note = event_screen.rig_only_note.text().lower()
    assert "free run" in note or "rig" in note, (
        f"status label should mention free run or rig when active, got {note!r}")


def test_rig_only_status_warn_shows_message(patched, qt_app):  # noqa: F811
    """A rig_only_status(msg, True) must appear in the status label."""
    controller, event_screen, *_ = patched
    controller.start_rig_only()
    controller.rig_only_status.emit("Port blocked.", True)
    assert event_screen.rig_only_note.text() == "Port blocked.", (
        "rig_only_note must show the message from rig_only_status")


def test_stop_free_run_button_click_stops(patched, qt_app):  # noqa: F811
    """Clicking again while active must stop rig-only mode."""
    controller, event_screen, *_ = patched
    controller.start_rig_only()
    event_screen.free_run_button.click()
    assert controller._rig_only_mode is False, (
        "clicking Stop Free Run must call stop_rig_only")


def test_rig_only_changed_false_clears_status_and_restores_label(patched, qt_app):  # noqa: F811
    """When rig_only_changed fires False, status clears and button text resets."""
    controller, event_screen, *_ = patched
    controller.start_rig_only()
    controller.stop_rig_only()
    assert event_screen.rig_only_note.text() == "", (
        "status note must be empty after Free Run stops")
    text = event_screen.free_run_button.text().lower()
    assert "stop" not in text, (
        f"button text must not say 'stop' after Free Run stops, got {text!r}")


def test_free_run_button_disabled_when_session_is_open(patched, qt_app):  # noqa: F811
    """While a practice session is open, Free Run must be disabled."""
    controller, event_screen, _, store, _ = patched
    controller._on_event_saved(an_event())
    controller.open_practice_session()
    assert controller.session_id is not None, "open_practice_session must set session_id"
    assert event_screen.free_run_button.isEnabled() is False, (
        "free_run_button must be disabled while a session is open")


# ===================================================== Fix 1 — Settings screen
# _tell_settings_about_the_session must treat _rig_only_mode like an open session
# so PortAudio is never re-enumerated while the ButtKicker is running.

def test_settings_screen_sees_session_open_while_rig_only(wired, monkeypatch):
    """When Free Run is active, _tell_settings_about_the_session must call
    set_session_open(True) so the Settings screen blocks device enumeration."""
    controller, *_ = wired

    calls: list = []

    class _FakeSettings:
        def set_session_open(self, value: bool) -> None:
            calls.append(value)

    controller.settings_screen = _FakeSettings()
    calls.clear()                           # discard any call from construction

    # Without a real listener we just set the flag and call the method directly.
    controller._rig_only_mode = True
    controller._tell_settings_about_the_session()

    assert calls == [True], (
        "_tell_settings_about_the_session must pass True while _rig_only_mode "
        f"is set; got {calls!r}")


def test_settings_screen_sees_session_closed_after_stop_rig_only(patched,
                                                                  monkeypatch):
    """After stop_rig_only, set_session_open(False) must be called."""
    controller, *_ = patched

    calls: list = []

    class _FakeSettings:
        def set_session_open(self, value: bool) -> None:
            calls.append(value)

    controller.settings_screen = _FakeSettings()
    controller.start_rig_only()
    calls.clear()                           # discard the True from start

    controller.stop_rig_only()

    assert False in calls, (
        "stop_rig_only must call _tell_settings_about_the_session with False; "
        f"got {calls!r}")


# ===================================================== Fix 2 — device-start warnings

def test_haptics_failure_emits_rig_only_status_warning(patched, monkeypatch):
    """When haptics_enabled=True but start_haptics returns False, a warning
    must be emitted on rig_only_status AFTER rig_only_changed(True)."""
    controller, *_ = patched
    monkeypatch.setattr(controller.settings, "haptics_enabled", True,
                        raising=False)
    monkeypatch.setattr(controller, "start_haptics", lambda: False)

    events: list = []
    controller.rig_only_changed.connect(
        lambda v: events.append(("changed", v)))
    controller.rig_only_status.connect(
        lambda msg, warn: events.append(("status", msg, warn)))

    controller.start_rig_only()

    # rig_only_changed(True) must come before the warning.
    changed_idx = next(
        (i for i, e in enumerate(events) if e == ("changed", True)), None)
    warn_idx = next(
        (i for i, e in enumerate(events)
         if e[0] == "status" and e[2] is True and "ButtKicker" in e[1]),
        None)
    assert changed_idx is not None, "rig_only_changed(True) was not emitted"
    assert warn_idx is not None, (
        "no ButtKicker warning was emitted when haptics_enabled=True but "
        "start_haptics returned False")
    assert changed_idx < warn_idx, (
        "rig_only_changed(True) must come before the haptics warning")


def test_haptics_disabled_no_warning_emitted(patched, monkeypatch):
    """When haptics_enabled=False a False return from start_haptics is not a
    failure — no warning must be emitted."""
    controller, *_ = patched
    monkeypatch.setattr(controller.settings, "haptics_enabled", False,
                        raising=False)
    monkeypatch.setattr(controller, "start_haptics", lambda: False)

    warnings: list = []
    controller.rig_only_status.connect(
        lambda msg, warn: warnings.append((msg, warn)) if warn else None)

    controller.start_rig_only()

    haptics_warns = [(m, w) for m, w in warnings if "ButtKicker" in m]
    assert haptics_warns == [], (
        "haptics warning emitted even though haptics_enabled=False: "
        f"{haptics_warns!r}")


def test_wind_failure_emits_rig_only_status_warning(patched, monkeypatch):
    """When wind_enabled=True but start_wind returns False, a warning must be
    emitted."""
    controller, *_ = patched
    monkeypatch.setattr(controller.settings, "wind_enabled", True,
                        raising=False)
    monkeypatch.setattr(controller, "start_wind", lambda: False)

    warnings: list = []
    controller.rig_only_status.connect(
        lambda msg, warn: warnings.append((msg, warn)) if warn else None)

    controller.start_rig_only()

    wind_warns = [(m, w) for m, w in warnings if "Wind" in m or "wind" in m]
    assert wind_warns, (
        "no wind warning was emitted when wind_enabled=True but start_wind "
        "returned False")


# ===================================================== Fix 3 — board not closed on rig-only refusal

def test_start_race_does_not_close_board_when_refused_for_rig_only(
        patched, monkeypatch, qt_app):  # noqa: F811
    """When start_race is refused because Free Run is active, the finished-race
    board must NOT be closed — the refusal must happen before any preamble."""
    from pitcrew.ui.race_screen import RaceScreen
    from pitcrew.ui.strategy_screen import StrategyScreen
    from unittest.mock import MagicMock

    controller, *_ = patched
    race_screen = RaceScreen()
    strategy = StrategyScreen()
    controller.race_screen = race_screen
    controller.strategy = strategy
    controller._on_event_saved(an_event())

    # Simulate a finished race (board would close if preamble ran).
    fake_state = MagicMock()
    fake_state.finished = True
    fake_race = MagicMock()
    fake_race.state = fake_state
    fake_race.armed = False
    fake_race.running = False
    controller.race = fake_race

    closed: list = []
    monkeypatch.setattr(controller, "_close_driver_board",
                        lambda: closed.append(1))

    controller.start_rig_only()   # Free Run is now active.
    result = controller.start_race()

    assert result is False, "start_race must return False during Free Run"
    assert closed == [], (
        "_close_driver_board was called before the rig-only guard ran")


# ===================================================== Fix 4 — bench.restore_status_target None guard

def test_stop_rig_only_safe_when_bench_practice_is_none(patched, monkeypatch):
    """stop_rig_only must not raise when bench.practice is None.

    This happens if Bench was constructed without a practice screen (e.g.
    during unit tests that do not wire the full UI).
    """
    controller, *_ = patched
    controller.start_rig_only()

    # Tear away the practice reference so the None branch is exercised.
    controller.bench.practice = None

    # Must not raise.
    controller.stop_rig_only()

    assert controller._rig_only_mode is False


def test_restore_status_target_is_idempotent_with_practice(patched):
    """restore_status_target is safe to call multiple times with a real practice
    screen wired up."""
    controller, _, practice, *_ = patched
    from pitcrew.ui.practice_screen import PracticeScreen

    controller.bench.restore_status_target()
    controller.bench.restore_status_target()

    target = controller.bench._status_target
    assert getattr(target, "__self__", None) is practice
    assert getattr(target, "__func__", None) is PracticeScreen.set_status


# ===================================================== Fix 5 — _rig_only_refusal_reason consistency

def test_refusal_reason_none_when_nothing_open(wired):
    """When nothing is blocking Free Run, refusal reason must be None."""
    controller, *_ = wired
    assert controller._rig_only_refusal_reason() is None


def test_refusal_reason_already_active(wired):
    """When rig-only is already active the reason mentions it."""
    controller, *_ = wired
    controller._rig_only_mode = True
    reason = controller._rig_only_refusal_reason()
    assert reason is not None
    assert "already" in reason.lower() or "active" in reason.lower()


def test_refusal_reason_listener_running(wired):
    """When a listener is up the reason mentions stopping it."""
    from unittest.mock import MagicMock
    controller, *_ = wired
    controller.listener = MagicMock()
    reason = controller._rig_only_refusal_reason()
    assert reason is not None
    # listener check must come before session check (checked first in helper)
    controller.listener = None


def test_refusal_reason_session_open(wired, store):
    """When a session is open the reason says so."""
    controller, *_ = wired
    controller._on_event_saved(an_event())
    controller.open_practice_session()
    reason = controller._rig_only_refusal_reason()
    assert reason is not None
    assert "session" in reason.lower()


def test_refusal_reason_race_armed(wired):
    """When a race is armed the reason says so."""
    from unittest.mock import MagicMock
    controller, *_ = wired
    fake_race = MagicMock()
    fake_race.armed = True
    fake_race.running = False
    controller.race = fake_race
    reason = controller._rig_only_refusal_reason()
    assert reason is not None
    assert "race" in reason.lower() or "armed" in reason.lower()


def test_already_active_refusal_emits_signal(patched):
    """The 'already active' refusal (Fix 5) must emit rig_only_status, not be
    silent. Previously it was logged but not signalled."""
    controller, *_ = patched
    controller.start_rig_only()      # first start succeeds

    warnings: list = []
    controller.rig_only_status.connect(
        lambda msg, warn: warnings.append((msg, warn)))

    controller.start_rig_only()      # second call — must emit

    assert len(warnings) == 1, (
        "double-start must emit rig_only_status; got "
        f"{len(warnings)} signal(s)")
    _, warn_flag = warnings[0]
    assert warn_flag is True


def test_can_start_rig_only_false_when_listener_running(wired):
    """can_start_rig_only must include the listener check (Fix 5)."""
    from unittest.mock import MagicMock
    controller, *_ = wired
    controller.listener = MagicMock()
    assert controller.can_start_rig_only is False
    controller.listener = None


# ===================================================== Fix 6 — AC3 identical output frame-for-frame

def test_drive_rig_produces_identical_intensities_via_both_paths(patched,
                                                                  monkeypatch):
    """on_packet_rig_only and on_packet must call set_intensities with the
    SAME values for the same packet sequence, frame-for-frame.

    Uses real EffectDeriver state (not mocked) and a recording fake haptics
    engine, fed identically through both code paths, then compared.
    """
    controller, _, _, store, _ = patched

    # ---------- rig-only path ----------------------------------------
    # Reset state exactly as start_rig_only does.
    controller.bridge.effects.reset()
    controller.bridge.wind_curve.reset()
    controller.bridge.racing = False

    intensities_rig: list = []

    class _RecordingHaptics:
        def set_intensities(self, values) -> None:
            # Copy the list — the caller may mutate it.
            intensities_rig.append(list(values))

        def silence(self) -> None:
            pass

        def stop(self) -> None:
            pass

    controller.bridge.haptics = _RecordingHaptics()

    packets = [
        raw(speed_ms=10.0, fuel_level=95.0),
        raw(speed_ms=30.0, fuel_level=90.0),
        raw(speed_ms=60.0, fuel_level=85.0),
    ]
    for pkt in packets:
        controller.bridge.on_packet_rig_only(pkt)

    # ---------- practice path ----------------------------------------
    # Reset to the same initial state.
    controller.bridge.effects.reset()
    controller.bridge.wind_curve.reset()
    controller.bridge.racing = False

    intensities_practice: list = []

    class _RecordingHapticsP:
        def set_intensities(self, values) -> None:
            intensities_practice.append(list(values))

        def silence(self) -> None:
            pass

        def stop(self) -> None:
            pass

    controller.bridge.haptics = _RecordingHapticsP()

    # open_practice_session sets up the bridge; drive via on_packet directly.
    controller._on_event_saved(an_event())
    controller.open_practice_session()

    for pkt in packets:
        controller.bridge.on_packet(pkt)

    # ---------- compare ----------------------------------------------
    assert len(intensities_rig) == 3, (
        f"rig path produced {len(intensities_rig)} frames, expected 3")
    assert len(intensities_practice) == 3, (
        f"practice path produced {len(intensities_practice)} frames, expected 3")
    for frame_i, (rig_vals, prac_vals) in enumerate(
            zip(intensities_rig, intensities_practice)):
        assert rig_vals == prac_vals, (
            f"frame {frame_i}: rig={rig_vals!r} != practice={prac_vals!r}")
