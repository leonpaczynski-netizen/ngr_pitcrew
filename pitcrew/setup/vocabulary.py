"""The shared setup vocabulary from EXPORT-CONTRACT.md §3.

These exact keys are what the consuming tune builder uses for its per-car range
library. Matching them removes a translation step and a class of silent
mismatches, so this module is the single place they are spelled out — nothing
else in the app may invent a key.

This is data entry, not engineering. Nothing here advises, derives, validates
against physics, or has an opinion about what a good setup is. The app records
what was in the car; the tune builder decides what should be.

Deliberately absent, because GT7 has none of them: tyre pressure, caster, brake
pressure, high/low-speed damper splits. If any of those ever appear here, the
logic was pattern-matched from another sim.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SetupKey:
    key: str
    label: str
    unit: str
    group: str
    decimals: int = 2
    note: str = ""


# Order is display order.
SETUP_KEYS: tuple[SetupKey, ...] = (
    SetupKey("rh_f", "Ride height front", "mm", "Body", 0),
    SetupKey("rh_r", "Ride height rear", "mm", "Body", 0),
    SetupKey("nf_f", "Natural frequency front", "Hz", "Springs", 2),
    SetupKey("nf_r", "Natural frequency rear", "Hz", "Springs", 2),
    SetupKey("arb_f", "Anti-roll bar front", "", "Springs", 0),
    SetupKey("arb_r", "Anti-roll bar rear", "", "Springs", 0),
    SetupKey("dc_f", "Damper compression front", "", "Dampers", 0),
    SetupKey("dc_r", "Damper compression rear", "", "Dampers", 0),
    SetupKey("de_f", "Damper extension front", "", "Dampers", 0),
    SetupKey("de_r", "Damper extension rear", "", "Dampers", 0),
    SetupKey("cam_f", "Camber front", "deg", "Geometry", 1),
    SetupKey("cam_r", "Camber rear", "deg", "Geometry", 1),
    SetupKey("toe_f", "Toe front", "deg", "Geometry", 2,
             "+ is toe-in, - is toe-out"),
    SetupKey("toe_r", "Toe rear", "deg", "Geometry", 2,
             "+ is toe-in, - is toe-out"),
    SetupKey("lsd_i", "LSD initial torque", "", "Differential", 0),
    SetupKey("lsd_a", "LSD acceleration sensitivity", "", "Differential", 0),
    SetupKey("lsd_b", "LSD braking sensitivity", "", "Differential", 0),
    SetupKey("awd", "AWD front torque split", "%", "Differential", 0,
             "null on two-wheel-drive cars"),
    SetupKey("df_f", "Downforce front", "", "Aero", 0),
    SetupKey("df_r", "Downforce rear", "", "Aero", 0),
    SetupKey("bb", "Brake balance", "", "Brakes", 0,
             "delta from the car's factory bias; - front, + rear"),
    SetupKey("top", "Top speed", "km/h", "Gearing", 0),
    SetupKey("fg", "Final gear", "", "Gearing", 3),
)

SETUP_KEY_NAMES: tuple[str, ...] = tuple(k.key for k in SETUP_KEYS)
_BY_KEY = {k.key: k for k in SETUP_KEYS}

# Keys the range record covers.  `awd` is absent because GT7 does not expose a
# slider range for it.
RANGE_KEY_NAMES: tuple[str, ...] = tuple(
    k for k in SETUP_KEY_NAMES if k != "awd")

GROUPS: tuple[str, ...] = tuple(dict.fromkeys(k.group for k in SETUP_KEYS))

MAX_GEARS = 9


def describe(key: str) -> SetupKey | None:
    return _BY_KEY.get(key)


def keys_in_group(group: str) -> tuple[SetupKey, ...]:
    return tuple(k for k in SETUP_KEYS if k.group == group)


def unknown_keys(values: dict) -> tuple[str, ...]:
    """Keys that are not in the shared vocabulary, sorted.

    Used to refuse an export rather than send the tune builder a key it will
    silently ignore.
    """
    return tuple(sorted(set(values) - set(SETUP_KEY_NAMES)))
