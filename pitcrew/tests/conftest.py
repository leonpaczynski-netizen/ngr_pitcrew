"""Shared fixtures: synthetic GT7 packets and a throwaway store."""
from __future__ import annotations

import dataclasses

import pytest

from pitcrew.store.db import Store
from pitcrew.telemetry.packet import (
    PACKET_SIZE,
    PACKET_SIZE_NEW,
    GT7Packet,
    parse_packet,
)

MAGIC = b"0S7G"


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
    """Wheel rotation that corresponds to rolling without slip."""
    return speed_ms / (radius * 2.0 * 3.141592653589793)


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
