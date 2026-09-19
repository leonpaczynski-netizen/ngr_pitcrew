"""Acceptance tests for the Free Run (rig-only) feature.

One test per acceptance criterion, named after the criterion. Each criterion
is exercised end-to-end through the real controller and real EventScreen
widgets. A FakeUDPListener (borrowed from test_rig_only) stands in for the
real socket so no port is bound and no console is needed.

References to the brief:
  AC1  — UI label, telemetry start, rig start
  AC2  — zero rows in every DB table, no capture file
  AC3  — identical _drive_rig path as practice on_packet
  AC4  — prior-session state cleared before Free Run starts
  AC5  — stop tears down state; next practice starts clean; quit mid-run clean
  AC6  — league data untouched; active_event_id unchanged
  AC7  — null active event does not block Free Run
  AC8  — no telemetry → Event screen warned; corrupt datagram → parse_failed
  AC9  — no shift beep, no George speech
  EDGE — haptics_enabled / wind_enabled False → rig not started
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

import pitcrew.controller as controller_mod
from pitcrew.controller import PitCrewController, TelemetryBridge
from pitcrew.store.db import Store
from pitcrew.ui.event_screen import EventScreen
from pitcrew.ui.practice_screen import PracticeScreen

from .conftest import make_packet
from .test_controller import an_event, qt_app, raw  # noqa: F401
from .test_rig_only import FakeUDPListener              # noqa: F401


# ================================================================= fixtures

@pytest.fixture()
def wired(qt_app, store: Store):  # noqa: F811
    """Real controller + real screens, no socket bound."""
    event_screen = EventScreen()
    practice = PracticeScreen()
    controller = PitCrewController(store, event_screen, practice)
    yield controller, event_screen, practice, store
    controller.shutdown()


@pytest.fixture()
def patched(wired, monkeypatch):
    """Wired controller with UDPListener replaced by FakeUDPListener.

    Returns (controller, event_screen, practice, store, created) where
    `created` accumulates every fake listener built during the test.
    """
    controller, event_screen, practice, store = wired
    created: list[FakeUDPListener] = []

    class _CapturingFake(FakeUDPListener):
        def __init__(self, *a, **kw):
            super().__init__(*a, **kw)
            created.append(self)

    monkeypatch.setattr(controller_mod, "UDPListener", _CapturingFake)
    yield controller, event_screen, practice, store, created


# ================================================================ helpers

def _all_tables(store: Store) -> set[str]:
    """Every user table in the throwaway store."""
    return {
        r[0]
        for r in store._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
    }


def _row_counts(store: Store) -> dict[str, int]:
    """Row count for every table in the throwaway store."""
    return {
        name: store._conn.execute(
            f"SELECT COUNT(*) FROM [{name}]"
        ).fetchone()[0]
        for name in _all_tables(store)
    }


# ================================================================ AC1 ===
# Free Run starts from the Event screen with or without an active event:
# telemetry begins, wind fan and ButtKicker start, UI labels it "Free Run".

def test_ac1_starts_with_no_active_event(patched, qt_app):  # noqa: F811
    """No event needed — Free Run starts and the listener is running."""
    controller, event_screen, _, _, created = patched
    # Deliberately no event created.
    event_screen.free_run_button.click()

    assert controller._rig_only_mode is True, "rig-only flag not set"
    assert len(created) == 1, "no UDPListener was created"
    assert created[0].running is True, "listener was not started"


def test_ac1_starts_with_active_event(patched, qt_app):  # noqa: F811
    """Free Run also works when an event exists."""
    controller, event_screen, _, _, created = patched
    controller._on_event_saved(an_event())

    event_screen.free_run_button.click()

    assert controller._rig_only_mode is True


def test_ac1_ui_label_says_free_run_active(patched, qt_app):  # noqa: F811
    """The status label must confirm the rig is running, no data recorded."""
    controller, event_screen, *_ = patched
    controller.start_rig_only()

    note = event_screen.rig_only_note.text()
    assert "free run" in note.lower() or "rig running" in note.lower(), (
        f"status label does not mention Free Run: {note!r}")
    # The brief requires this exact phrase.
    assert "no data recorded" in note.lower(), (
        f"status label does not confirm no data is recorded: {note!r}")


def test_ac1_haptics_and_wind_start_called(patched, monkeypatch):
    """start_haptics and start_wind are called from start_rig_only."""
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


# ================================================================ AC2 ===
# Nothing recorded: zero rows in sessions, laps, lap_frames, any
# aggregate/measurement table; no raw capture file created.

def test_ac2_zero_rows_in_all_tables_after_multi_lap_sequence(patched, store):
    """Driving several lap-crossing packets through on_packet_rig_only
    must leave every table at zero rows."""
    controller, _, _, store, _ = patched
    controller.start_rig_only()

    # Snapshot before.
    before = _row_counts(store)

    bridge = controller.bridge
    # Three packets: normal, lap crossing, after crossing.
    bridge.on_packet_rig_only(raw(speed_ms=50.0, fuel_level=92.0,
                                  time_of_day_ms=0))
    bridge.on_packet_rig_only(raw(speed_ms=50.0, fuel_level=88.6,
                                  last_lap_ms=93_912, time_of_day_ms=16))
    bridge.on_packet_rig_only(raw(speed_ms=50.0, fuel_level=88.0,
                                  time_of_day_ms=32))

    after = _row_counts(store)

    for table_name, count in after.items():
        was = before.get(table_name, 0)
        assert count == was, (
            f"table '{table_name}' gained {count - was} row(s) during Free Run")


def test_ac2_no_capture_file_created(patched, tmp_path, monkeypatch):
    """on_packet_rig_only must not write to a capture file.

    The bridge's `capture` attribute stays None throughout; no CaptureWriter
    is built and therefore no file appears in the capture directory.
    """
    controller, *_ = patched
    # Point the capture dir at a fresh temp subdirectory so we can check it.
    capture_dir = tmp_path / "captures"
    capture_dir.mkdir()
    monkeypatch.setattr(controller_mod, "CAPTURE_DIR", capture_dir)

    controller.start_rig_only()
    # Feed ten packets including a lap crossing.
    for i in range(10):
        controller.bridge.on_packet_rig_only(
            raw(speed_ms=50.0, fuel_level=90.0 - i,
                last_lap_ms=(93_000 if i == 5 else -1),
                time_of_day_ms=i * 16))

    assert controller.bridge.capture is None, (
        "bridge.capture must stay None during Free Run")
    files = list(capture_dir.iterdir())
    assert files == [], (
        f"capture files appeared during Free Run: {files}")


# ================================================================ AC3 ===
# Rig effects behave identically to practice (same per-frame path),
# respecting haptics_enabled / wind_enabled.

def test_ac3_drive_rig_called_on_every_valid_packet(patched, monkeypatch):
    """_drive_rig must be called once per valid packet, same as in practice."""
    controller, *_ = patched
    controller.start_rig_only()

    called: list = []
    original = controller.bridge._drive_rig
    monkeypatch.setattr(controller.bridge, "_drive_rig",
                        lambda pkt: called.append(pkt) or original(pkt))

    # Feed three packets.
    for _ in range(3):
        controller.bridge.on_packet_rig_only(raw(speed_ms=50.0))

    assert len(called) == 3, (
        f"_drive_rig called {len(called)} times, expected 3")


def test_ac3_same_effects_path_with_fake_haptics(patched, monkeypatch):
    """on_packet_rig_only calls effects.update via _drive_rig when haptics
    are present — the same code path as practice on_packet.

    We inject a fake haptics engine (set_intensities is a no-op) so that
    effects.update is actually reached. Both paths call _drive_rig; this
    confirms the effects deriver is not bypassed in rig-only mode.
    """
    controller, *_ = patched
    controller.start_rig_only()

    # Inject a fake haptics engine so _drive_rig reaches effects.update.
    intensities_seen: list = []
    fake_haptics = MagicMock()
    fake_haptics.set_intensities.side_effect = intensities_seen.append
    controller.bridge.haptics = fake_haptics

    controller.bridge.effects.reset()
    controller.bridge.on_packet_rig_only(raw(speed_ms=40.0))

    assert intensities_seen, (
        "effects.update was not called via _drive_rig from on_packet_rig_only "
        "even with a haptics engine present")
    # One call per packet.
    assert len(intensities_seen) == 1


# ================================================================ AC4 ===
# Clean start: prior-session state (tyre splits, quali coach, shift state,
# wind/effects, racing flag) cannot influence Free Run.

def test_ac4_racing_flag_cleared_from_prior_race(patched):
    """If racing was True from a prior session it must be False in Free Run."""
    controller, *_ = patched
    controller.bridge.racing = True        # simulated post-race state

    controller.start_rig_only()

    assert controller.bridge.racing is False


def test_ac4_effects_reset_before_start(patched, monkeypatch):
    """effects.reset() must be called so prior state does not carry in."""
    controller, *_ = patched
    calls: list = []
    original = controller.bridge.effects.reset
    monkeypatch.setattr(controller.bridge.effects, "reset",
                        lambda: calls.append(1) or original())
    controller.start_rig_only()
    assert calls, "effects.reset was not called"


def test_ac4_wind_curve_reset_before_start(patched, monkeypatch):
    """wind_curve.reset() must be called so the racing floor does not leak."""
    controller, *_ = patched
    calls: list = []
    original = controller.bridge.wind_curve.reset
    monkeypatch.setattr(controller.bridge.wind_curve, "reset",
                        lambda: calls.append(1) or original())
    controller.start_rig_only()
    assert calls, "wind_curve.reset was not called"


def test_ac4_bridge_reset_not_called(patched, monkeypatch):
    """bridge.reset() (recorder.discard) must NOT be called — that is the
    practice-session path."""
    controller, *_ = patched
    discarded: list = []
    monkeypatch.setattr(controller.bridge.recorder, "discard",
                        lambda: discarded.append(1))
    controller.start_rig_only()
    assert discarded == [], "recorder.discard was called (bridge.reset was triggered)"


def test_ac4_quali_coach_not_started(patched):
    """The qualifying coach must be None throughout Free Run.

    The coach is armed in start_practice, never in start_rig_only.
    """
    controller, *_ = patched
    controller.start_rig_only()
    assert controller.bridge.quali is None, (
        "quali coach was armed during Free Run")


def test_ac4_splits_cleared_on_start(patched, monkeypatch):
    """The tyre split history must be reset (CLAUDE.md rule 11)."""
    controller, *_ = patched
    calls: list = []
    monkeypatch.setattr(controller._splits, "new_session",
                        lambda: calls.append(1))
    controller.start_rig_only()
    assert calls, "_splits.new_session was not called by start_rig_only"


# ================================================================ AC5 ===
# Clean exit: stopping stops fan and ButtKicker; next league practice starts
# clean; app quit mid-free-run shuts down cleanly.

def test_ac5_stop_stops_haptics_and_wind(patched, monkeypatch):
    """stop_rig_only must call stop_haptics and stop_wind."""
    controller, *_ = patched
    haptics_stops: list = []
    wind_stops: list = []
    monkeypatch.setattr(controller, "stop_haptics",
                        lambda: haptics_stops.append(1))
    monkeypatch.setattr(controller, "stop_wind",
                        lambda: wind_stops.append(1))

    controller.start_rig_only()
    controller.stop_rig_only()

    assert haptics_stops, "stop_haptics was not called"
    assert wind_stops, "stop_wind was not called"


def test_ac5_stop_tears_down_listener(patched):
    """The listener must be stopped and cleared after stop_rig_only."""
    controller, *_, created = patched
    controller.start_rig_only()
    controller.stop_rig_only()

    assert controller.listener is None
    assert created[0].running is False


def test_ac5_flag_cleared_after_stop(patched):
    """_rig_only_mode must be False after stop."""
    controller, *_ = patched
    controller.start_rig_only()
    controller.stop_rig_only()
    assert controller._rig_only_mode is False


def test_ac5_next_practice_starts_and_records(patched, store, qt_app):  # noqa: F811
    """After Free Run stops, a normal practice session must open and
    accept packet data without touching the rig-only path."""
    controller, _, _, store, _ = patched
    controller._on_event_saved(an_event())

    # Run Free Run.
    controller.start_rig_only()
    controller.bridge.on_packet_rig_only(raw(speed_ms=50.0))
    controller.stop_rig_only()

    # Open a practice session.
    controller.open_practice_session()
    assert controller.session_id is not None, (
        "practice session did not open after Free Run stopped")
    assert controller._rig_only_mode is False


def test_ac5_shutdown_mid_free_run_clears_flag(patched):
    """shutdown() while Free Run is active must leave _rig_only_mode False."""
    controller, *_ = patched
    controller.start_rig_only()
    # Call shutdown directly — the fixture teardown calls it too but the
    # flag must be False immediately after the call.
    controller.shutdown()
    assert controller._rig_only_mode is False


def test_ac5_shutdown_mid_free_run_stops_listener(patched):
    """shutdown() while Free Run is active must stop the listener."""
    controller, *_, created = patched
    controller.start_rig_only()
    controller.shutdown()
    assert created[0].running is False
    assert controller.listener is None


# ================================================================ AC6 ===
# League data untouched: nothing in aggregates/exports; active_event_id
# unchanged.

def test_ac6_active_event_id_not_changed(patched, store):
    """start_rig_only must not change the active event id."""
    controller, _, _, store, _ = patched
    controller._on_event_saved(an_event())
    event_id_before = store.active_event_id()

    controller.start_rig_only()
    controller.bridge.on_packet_rig_only(raw(speed_ms=50.0))

    assert store.active_event_id() == event_id_before


def test_ac6_sessions_table_zero_rows_during_run(patched, store):
    """No session row may appear while Free Run is running."""
    controller, _, _, store, _ = patched
    controller.start_rig_only()
    for _ in range(5):
        controller.bridge.on_packet_rig_only(raw(speed_ms=50.0))

    count = store._conn.execute(
        "SELECT COUNT(*) FROM sessions").fetchone()[0]
    assert count == 0, "a session row was written during Free Run"


def test_ac6_laps_table_zero_after_lap_crossing(patched, store):
    """A lap crossing in rig-only mode must not write a laps row."""
    controller, _, _, store, _ = patched
    controller.start_rig_only()
    # Lap crossing.
    controller.bridge.on_packet_rig_only(
        raw(speed_ms=50.0, last_lap_ms=93_000))
    controller.bridge.on_packet_rig_only(raw(speed_ms=50.0))

    count = store._conn.execute(
        "SELECT COUNT(*) FROM laps").fetchone()[0]
    assert count == 0, "a laps row was written during Free Run"


# ================================================================ AC7 ===
# Null active event does not block Free Run.

def test_ac7_no_event_does_not_block_start(patched):
    """start_rig_only must succeed with no active event."""
    controller, *_, _ = patched
    # No event created — active_event_id() returns None.
    controller.start_rig_only()
    assert controller._rig_only_mode is True, (
        "start_rig_only was blocked when no event exists")


def test_ac7_can_start_rig_only_true_with_no_event(wired, qt_app):  # noqa: F811
    """can_start_rig_only must be True when no event and no session exist."""
    controller, *_ = wired
    assert controller.can_start_rig_only is True


def test_ac7_button_enabled_with_no_event(wired, qt_app):  # noqa: F811
    """The Free Run button must be enabled with no event and no session."""
    _, event_screen, *_ = wired
    assert event_screen.free_run_button.isEnabled() is True


# ================================================================ AC8 ===
# Fails loudly: no telemetry → UI says so; corrupt datagram → parse_failed,
# rig not driven.

def test_ac8_corrupt_packet_emits_parse_failed_not_drive_rig(patched, monkeypatch):
    """A corrupt datagram must emit parse_failed and NOT call _drive_rig."""
    controller, *_ = patched
    controller.start_rig_only()

    failed: list = []
    controller.bridge.parse_failed.connect(lambda: failed.append(1))

    drive_calls: list = []
    monkeypatch.setattr(controller.bridge, "_drive_rig",
                        lambda pkt: drive_calls.append(pkt))

    result = controller.bridge.on_packet_rig_only(b"not a GT7 packet")

    assert result is False
    assert len(failed) == 1, "parse_failed was not emitted on bad data"
    assert drive_calls == [], "_drive_rig was called with corrupt data"


def test_ac8_no_telemetry_routes_warning_to_event_screen(patched, qt_app):  # noqa: F811
    """With no telemetry the bench health line must reach the Event screen,
    not the practice screen."""
    controller, event_screen, practice, _, created = patched
    controller.start_rig_only()

    # Intercept practice.set_status to ensure it is NOT called.
    practice_calls: list = []
    original = practice.set_status
    practice.set_status = lambda *a, **kw: practice_calls.append(a)

    # `created[0].connected` defaults False → the "no telemetry" branch.
    rig_messages: list = []
    controller.rig_only_status.connect(
        lambda msg, warn: rig_messages.append((msg, warn)))

    controller.bench._report_health()

    practice.set_status = original

    assert practice_calls == [], (
        "bench wrote to the practice screen during Free Run")
    assert rig_messages, "no rig_only_status signal from bench during no-telemetry"
    msg, warn = rig_messages[0]
    assert warn is True, "the no-telemetry message must be a warning"
    assert ("telemetry" in msg.lower() or "console" in msg.lower()), (
        f"no-telemetry message missing keyword: {msg!r}")


def test_ac8_warning_appears_in_event_screen_note(patched, qt_app):  # noqa: F811
    """A rig_only_status warning must appear on the rig_only_note label."""
    controller, event_screen, *_ = patched
    controller.start_rig_only()

    controller.rig_only_status.emit("No telemetry on port 33740. Is GT7 running?", True)

    note = event_screen.rig_only_note.text()
    assert "No telemetry" in note, (
        f"Event screen did not display the warning: {note!r}")


# ================================================================ AC9 ===
# No shift beep and no George speech during Free Run.

def test_ac9_shift_beep_update_not_called(patched, monkeypatch):
    """ShiftBeep.update must not be called from on_packet_rig_only."""
    controller, *_ = patched
    controller.start_rig_only()

    called: list = []
    monkeypatch.setattr(controller.bridge.shift_beep, "update",
                        lambda pkt, t: called.append(1))

    controller.bridge.on_packet_rig_only(raw(speed_ms=50.0))

    assert called == [], "shift_beep.update was called from on_packet_rig_only"


def test_ac9_shift_beep_silent_even_with_gear_table(patched, monkeypatch):
    """When the shift beep has a per-gear table that would fire in practice,
    it must stay silent in Free Run.

    The test arms the beep with a table that always fires (threshold = 1 rpm)
    and confirms play is never reached.
    """
    controller, *_ = patched
    controller.start_rig_only()

    # Give the beep a table that fires at any RPM.
    controller.bridge.shift_beep._enabled = True
    controller.bridge.shift_beep.per_gear = {1: 1.0, 2: 1.0, 3: 1.0}

    beeps_played: list = []
    monkeypatch.setattr(controller.bridge.shift_beep, "_play",
                        lambda blocking=False: beeps_played.append(1) or True)

    # Feed a packet that would trigger the beep in practice.
    controller.bridge.on_packet_rig_only(raw(speed_ms=50.0))

    assert beeps_played == [], (
        "shift beep was played from on_packet_rig_only with a live gear table")


def test_ac9_voice_say_not_called_during_free_run(patched):
    """voice.say must not be called during Free Run.

    voice.spoken tracks every say() call — it must remain empty throughout.
    """
    controller, *_ = patched
    # Clear any say() calls that happened at construction.
    controller.voice.spoken.clear()

    controller.start_rig_only()

    # Feed packets including a lap crossing (which would trigger debrief/George
    # in practice).
    for i in range(5):
        controller.bridge.on_packet_rig_only(
            raw(speed_ms=50.0, fuel_level=90.0 - i,
                last_lap_ms=(93_000 if i == 3 else -1),
                time_of_day_ms=i * 16))

    assert controller.voice.spoken == [], (
        f"voice.say was called during Free Run: {controller.voice.spoken}")


def test_ac9_no_george_coaching_during_free_run(patched):
    """The qualifying coach (George) must be None throughout Free Run.

    quali is only armed in start_practice / start_race, never here.
    """
    controller, *_ = patched
    controller.start_rig_only()
    controller.bridge.on_packet_rig_only(raw(speed_ms=50.0))
    assert controller.bridge.quali is None, (
        "qualifying coach was running during Free Run")


def test_ac9_straight_reached_not_triggering_george(patched, monkeypatch, qt_app):  # noqa: F811
    """Even if straight_reached fires, George stays silent in Free Run.

    The controller's _on_straight_reached calls voice.say; in Free Run mode
    it must be a no-op because no qualifying coach or race coordinator is armed.
    """
    controller, *_ = patched
    controller.start_rig_only()
    controller.voice.spoken.clear()

    # Emit the signal directly — as the telemetry thread would.
    controller.bridge.straight_reached.emit()

    assert controller.voice.spoken == [], (
        f"voice.say was called from straight_reached during Free Run: "
        f"{controller.voice.spoken}")


# ================================================================ EDGE ===
# haptics/wind disabled in Settings → Free Run leaves them off.

def test_edge_haptics_disabled_bridge_haptics_stays_none(patched, monkeypatch):
    """When haptics_enabled is False the bridge's haptics attribute stays None
    throughout Free Run — the disabled setting is respected."""
    controller, *_ = patched

    # Make the settings return haptics_enabled = False (the default in tests).
    # The real supervisor guard: `if not self.settings.haptics_enabled: return`
    # We verify that bridge.haptics is still None after start.
    monkeypatch.setattr(controller.settings, "haptics_enabled", False,
                        raising=False)

    controller.start_rig_only()

    assert controller.bridge.haptics is None, (
        "bridge.haptics was set even though haptics_enabled is False")


def test_edge_wind_disabled_bridge_wind_stays_none(patched, monkeypatch):
    """When wind_enabled is False the bridge's wind attribute stays None."""
    controller, *_ = patched
    monkeypatch.setattr(controller.settings, "wind_enabled", False,
                        raising=False)

    controller.start_rig_only()

    assert controller.bridge.wind is None, (
        "bridge.wind was set even though wind_enabled is False")


def test_edge_drive_rig_does_not_explode_when_haptics_and_wind_none(patched):
    """_drive_rig must not raise when bridge.haptics and bridge.wind are both
    None, which is the state in every test (no real audio device)."""
    controller, *_ = patched
    controller.start_rig_only()

    assert controller.bridge.haptics is None
    assert controller.bridge.wind is None

    # Must not raise.
    result = controller.bridge.on_packet_rig_only(raw(speed_ms=50.0))
    assert result is True


# ================================================================ (a) ===
# AC5/AC3: Settings screen _fill_audio_devices does not re-enumerate while
# Free Run is active — the real SettingsScreen attached via attach_settings_screen.

def test_a_fill_audio_devices_does_not_run_during_free_run(
        patched, monkeypatch, qt_app):  # noqa: F811
    """With a real SettingsScreen attached and Free Run active, calling
    _fill_audio_devices must not invoke audio_devices.devices — PortAudio
    must not be torn down while the ButtKicker is running.

    Pattern follows test_audio_device_fill.py: monkeypatch the module-level
    `audio_devices` in `pitcrew.ui.settings_screen` so any call to
    `devices(kind)` fails the test.
    """
    from pitcrew.ui import settings_screen as ss_module
    from pitcrew.ui.settings_screen import SettingsScreen

    controller, *_ = patched

    # Monkeypatch BEFORE the screen is built so no enumeration happens at
    # construction either (matching the test_audio_device_fill pattern).
    called: list[str] = []
    monkeypatch.setattr(ss_module.audio_devices, "devices",
                        lambda kind: called.append(kind) or [])

    settings_screen = SettingsScreen()
    controller.attach_settings_screen(settings_screen)
    # start_rig_only calls _tell_settings_about_the_session which calls
    # set_session_open(True).
    controller.start_rig_only()

    # Reset the call log: we care only about what happens AFTER Free Run starts.
    called.clear()

    # Now call _fill_audio_devices directly (the same call showEvent defers).
    settings_screen._fill_audio_devices()

    assert called == [], (
        f"audio_devices.devices was called during Free Run: {called!r}. "
        "PortAudio must not be rebuilt while the ButtKicker is running.")


def test_a_fill_audio_devices_allowed_after_stop_rig_only(
        patched, monkeypatch, qt_app):  # noqa: F811
    """After Free Run stops, _fill_audio_devices must be able to enumerate
    (set_session_open(False) was called in stop_rig_only)."""
    from pitcrew.ui import settings_screen as ss_module
    from pitcrew.ui.settings_screen import SettingsScreen

    controller, *_ = patched

    called: list[str] = []
    monkeypatch.setattr(ss_module.audio_devices, "devices",
                        lambda kind: called.append(kind) or [])

    settings_screen = SettingsScreen()
    controller.attach_settings_screen(settings_screen)
    controller.start_rig_only()
    controller.stop_rig_only()

    # _audio_filled gate: reset it so a second fill is possible.
    settings_screen._audio_filled = False
    called.clear()

    settings_screen._fill_audio_devices()

    assert called != [], (
        "audio_devices.devices was NOT called after Free Run stopped — "
        "set_session_open(False) may not have been called by stop_rig_only")


# ================================================================ (b) ===
# AC8: haptics enabled but device start fails → Event screen shows the
# failure warning, not "rig running".

def test_b_haptics_enabled_failure_shows_warning_on_event_screen(
        patched, monkeypatch, qt_app):  # noqa: F811
    """When haptics_enabled=True but start_haptics returns False the
    rig_only_note on the Event screen must display the ButtKicker failure
    warning — not the normal 'Free Run active — rig running' confirmation.

    The warning is emitted on rig_only_status AFTER rig_only_changed(True),
    so it overwrites the initial 'rig running' text.
    """
    controller, event_screen, *_ = patched
    monkeypatch.setattr(controller.settings, "haptics_enabled", True,
                        raising=False)
    monkeypatch.setattr(controller, "start_haptics", lambda: False)

    controller.start_rig_only()

    note = event_screen.rig_only_note.text()
    assert "ButtKicker" in note or "buttKicker" in note.lower(), (
        f"Event screen does not show the ButtKicker warning: {note!r}")
    # The 'rig running, no data recorded' line must have been overwritten.
    assert "rig running" not in note.lower(), (
        f"Event screen still says 'rig running' after a ButtKicker failure: "
        f"{note!r}")


def test_b_haptics_disabled_no_warning_on_event_screen(
        patched, monkeypatch, qt_app):  # noqa: F811
    """When haptics_enabled=False a failed start is not an error — the
    Event screen note must stay at the normal 'rig running' text."""
    controller, event_screen, *_ = patched
    monkeypatch.setattr(controller.settings, "haptics_enabled", False,
                        raising=False)
    monkeypatch.setattr(controller, "start_haptics", lambda: False)

    controller.start_rig_only()

    note = event_screen.rig_only_note.text()
    assert "ButtKicker" not in note, (
        f"Event screen shows a ButtKicker warning even though haptics_enabled "
        f"is False: {note!r}")


# ================================================================ (c) ===
# AC3 — wind side: set_output values from on_packet_rig_only and on_packet
# match frame-for-frame for the same packet sequence.

def test_c_wind_set_output_identical_via_both_paths(patched, monkeypatch):
    """on_packet_rig_only and on_packet must call wind.set_output with the
    SAME duty-cycle values for the same packet sequence, frame-for-frame.

    Uses a fake Wind object that records every set_output call, driven
    through both code paths on a fresh wind_curve reset.
    """
    controller, _, _, store, _ = patched

    class _RecordingWind:
        def __init__(self):
            self.outputs: list = []

        def set_output(self, values, *, context=None) -> None:
            # Copy, in case the caller mutates in place.
            self.outputs.append(
                list(values) if hasattr(values, "__iter__") else values)

        def stop(self) -> None:
            pass

        def park(self) -> None:
            pass

        def stop_fans(self) -> None:
            pass

        def shutdown(self) -> None:
            pass

    packets = [
        raw(speed_ms=10.0, fuel_level=95.0),
        raw(speed_ms=40.0, fuel_level=90.0),
        raw(speed_ms=80.0, fuel_level=85.0),
    ]

    # ---- rig-only path -------------------------------------------------
    controller.bridge.wind_curve.reset()
    controller.bridge.racing = False
    wind_rig = _RecordingWind()
    controller.bridge.wind = wind_rig

    for pkt in packets:
        controller.bridge.on_packet_rig_only(pkt)

    # ---- practice path -------------------------------------------------
    controller.bridge.wind_curve.reset()
    controller.bridge.racing = False
    wind_practice = _RecordingWind()
    controller.bridge.wind = wind_practice

    controller._on_event_saved(an_event())
    controller.open_practice_session()
    for pkt in packets:
        controller.bridge.on_packet(pkt)

    # ---- compare -------------------------------------------------------
    assert len(wind_rig.outputs) == 3, (
        f"rig-only path produced {len(wind_rig.outputs)} wind frames, expected 3")
    assert len(wind_practice.outputs) == 3, (
        f"practice path produced {len(wind_practice.outputs)} wind frames, "
        f"expected 3")
    for frame_i, (rig_vals, prac_vals) in enumerate(
            zip(wind_rig.outputs, wind_practice.outputs)):
        assert rig_vals == prac_vals, (
            f"wind frame {frame_i}: rig={rig_vals!r} != practice={prac_vals!r}")
