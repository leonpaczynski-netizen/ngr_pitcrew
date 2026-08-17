"""Shared fixtures: synthetic GT7 packets, a throwaway store, and silence."""
from __future__ import annotations

import dataclasses
import sys

import pytest

from pitcrew.store.db import Store
from pitcrew.telemetry.packet import (
    PACKET_SIZE,
    PACKET_SIZE_NEW,
    GT7Packet,
    parse_packet,
)

MAGIC = b"0S7G"


# --------------------------------------------------------------- no sound
#
# **On 17 Aug 2026 the driver heard the engineer talking while the app was
# not running.** It was the test suite, out of his headphones, mid-session.
# `PitCrewController.__init__` builds `Voice()` with no engine, and the bare
# form means "find the best one available" - so every test that constructs a
# real controller got a real Piper engine bound to his real output device.
# `test_settings_and_diagnostics` substitutes `say_now` *after* construction,
# which is too late, and one line was cut off mid-sentence when a test tore
# its stream down.
#
# The same shape of guardrail already exists for the config file, after a
# smoke test overwrote his settings by constructing the real `MainWindow`.
# This is that rule applied to the three things in this app that make a
# noise: the voice, the transducer and the shift beep.


class RealAudioForbidden(BaseException):
    """A test reached a real audio device.

    **Deliberately a `BaseException`.** Every audio path in this app wraps
    its opens in `except Exception` and falls through to the next route, so
    a plain exception here is swallowed and the test passes in silence -
    which is precisely how this went unnoticed until it was audible in
    another room. This one escapes the fall-through and names the caller.
    """


class _ForbiddenAudioModule:
    """Stands in for `sounddevice` and refuses every use of it.

    Importing it is allowed and doing anything with it is not. `shift_beep`
    imports the module while building a tone it may never play, and the
    import machinery itself probes `__spec__` and friends, so a guard that
    fired on the import would only prove that Python imports things.
    """

    __name__ = "sounddevice"

    # Enumerating and re-enumerating are reads, not sounds, and the settings
    # screen does both just by being built. Under test the machine simply has
    # no devices: that is honest, and it keeps the guard aimed at the thing it
    # is for. Anything below that opens a stream raises.
    _INERT = {
        "query_devices": lambda *a, **k: [],
        "query_hostapis": lambda *a, **k: [],
        "_terminate": lambda *a, **k: None,
        "_initialize": lambda *a, **k: None,
        "default": type("_Default", (), {"device": (-1, -1),
                                         "samplerate": None})(),
    }

    def __getattr__(self, name: str):
        if name.startswith("__") and name.endswith("__"):
            # Import machinery, `inspect`, and `repr`. Not a device.
            raise AttributeError(name)
        if name in self._INERT:
            return self._INERT[name]
        raise RealAudioForbidden(
            f"a test reached the real audio device via sounddevice.{name}. "
            "Nothing under pytest may open one: inject a double, or mark "
            "the test @pytest.mark.real_audio if it genuinely needs "
            "hardware.")


@pytest.fixture(autouse=True)
def _no_real_audio(request, monkeypatch):
    """No test makes a sound unless it says out loud that it means to."""
    if request.node.get_closest_marker("real_audio"):
        return
    monkeypatch.setitem(sys.modules, "sounddevice", _ForbiddenAudioModule())
    if request.node.get_closest_marker("engine_resolution"):
        # A test *of* the chooser. It substitutes the engine classes itself
        # and needs the real resolution logic to have anything to assert.
        return
    # The voice resolves its engine before any stream is opened, so it is
    # silenced at that seam rather than by the raise above: a controller
    # under test should build a mute engineer, not explode.
    from pitcrew.engineer import voice as voice_module
    monkeypatch.setattr(voice_module, "_best_engine", lambda *a, **k: None)


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "real_audio: this test opens a real audio device and will be heard")
    config.addinivalue_line(
        "markers",
        "engine_resolution: this test exercises `voice._best_engine` itself, "
        "so it keeps the real chooser while staying barred from a device")


def raw_packet(extended: bool = False) -> bytes:
    """A zero-filled but structurally valid decrypted packet."""
    size = PACKET_SIZE_NEW if extended else PACKET_SIZE
    return MAGIC + bytes(size - 4)


def base_packet(extended: bool = False) -> GT7Packet:
    packet = parse_packet(raw_packet(extended))
    assert packet is not None
    return packet


def make_packet(*, extended: bool = False, on_track: bool = True, **overrides) -> GT7Packet:
    """Build a packet with sensible racing defaults, overriding named fields.

    `on_track` is spelled out rather than left to the caller because
    `flags_raw` bit 0 gates almost every code path and a zero-filled packet
    means "in the menus".
    """
    packet = base_packet(extended)
    defaults = {
        "flags_raw": 0x0001 if on_track else 0x0000,
        "speed_ms": 50.0,
        "fuel_level": 60.0,
        "fuel_capacity": 100.0,
        "last_lap_ms": -1,
        "best_lap_ms": -1,
        "laps_completed": 0,
        "laps_in_race": 0,
        "tyre_radius_fl": 0.35, "tyre_radius_fr": 0.35,
        "tyre_radius_rl": 0.35, "tyre_radius_rr": 0.35,
    }
    defaults.update(overrides)
    return dataclasses.replace(packet, **defaults)


def rolling_wheel_rps(speed_ms: float, radius: float = 0.35) -> float:
    """Wheel rotation that corresponds to rolling without slip.

    **GT7's per-wheel channel is rad/s**, so this is `v / r` and nothing else.
    It used to synthesise rev/s, which is the same mistake the recorder made
    reading it -- so the fixture cancelled the defect out and
    `test_rolling_wheels_give_unit_slip` asserted 1.0 against an input built to
    produce it. On the real stream the median was 6.2832.
    """
    return speed_ms / radius


@pytest.fixture()
def store(tmp_path) -> Store:
    db = Store(tmp_path / "pitcrew.db")
    yield db
    db.close()


@pytest.fixture()
def event_id(store: Store) -> int:
    return store.create_event(
        name="Test Event",
        track="Autodromo Nazionale Monza",
        layout="Full Course",
        car_id=123,
        car_name="Porsche 911 RSR",
        race_type="laps",
        race_laps=20,
        refuel_rate_lps=2.5,
        pit_loss_secs=20.0,
        available_compounds=["RH", "RM", "RS"],
        required_compounds=["RM"],
    )
