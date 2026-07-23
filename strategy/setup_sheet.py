"""SetupSheet — the car setup as DATA, not Qt widgets (single-system migration, stage 1).

Today the authoritative value of every setup field lives inside a ``QDoubleSpinBox`` on
the classic ``SetupFormWidget``. Everything that needs a setup — the new shell, the
advisor, the baseline builder, apply, revert, autosave — reaches into that widget tree
through ``MainWindow``. That single fact is what keeps the old UI load-bearing: the app
cannot run without it because the app's setup state IS the old UI.

This module makes the sheet a plain, typed, pure value object. It is the keystone of
removing the classic system: once the sheet is data, the operations over it can be
headless services, and the classic form becomes just another renderer that can be
deleted.

Pure: no Qt, no I/O, no DB, never raises. Field names and defaults mirror
``SetupBuilderMixin._current_setup_dict`` exactly, so a sheet round-trips through the
existing save/load/apply paths byte-identically.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Mapping, Optional, Tuple

#: Every numeric field, with its default and the number of decimals it is stored at.
#: Decimals matter: comparing 3.5 to 3.500000001 must not read as a change.
NUMERIC_FIELDS: Tuple[Tuple[str, float, int], ...] = (
    ("ride_height_front", 80.0, 0), ("ride_height_rear", 80.0, 0),
    ("springs_front", 3.50, 2), ("springs_rear", 3.00, 2),
    ("dampers_front_comp", 30.0, 0), ("dampers_front_ext", 40.0, 0),
    ("dampers_rear_comp", 25.0, 0), ("dampers_rear_ext", 35.0, 0),
    ("arb_front", 5.0, 0), ("arb_rear", 4.0, 0),
    ("camber_front", 1.0, 1), ("camber_rear", 1.5, 1),
    ("toe_front", 0.00, 2), ("toe_rear", 0.05, 2),
    ("aero_front", 0.0, 0), ("aero_rear", 0.0, 0),
    ("lsd_initial", 10.0, 0), ("lsd_accel", 15.0, 0), ("lsd_decel", 5.0, 0),
    ("lsd_front_initial", 0.0, 0), ("lsd_front_accel", 0.0, 0), ("lsd_front_decel", 0.0, 0),
    ("torque_distribution_rear", 50.0, 0),
    ("brake_bias_front", 0.0, 0),
    ("ballast_kg", 0.0, 0), ("ballast_position", 0.0, 0),
    ("power_restrictor", 100.0, 0),
    ("ecu_ingame_output", 100.0, 0),
    ("nitrous_output", 0.0, 0),
    ("final_drive", 0.0, 3),
    ("transmission_max_speed_kmh", 0.0, 0),
)

#: Free-text / choice fields, with their defaults.
TEXT_FIELDS: Tuple[Tuple[str, str], ...] = (
    ("name", ""), ("car", ""), ("track", ""), ("setup_label", "Setup 1"),
    ("condition", "Dry"), ("setup_type", ""),
    ("tyre_front", "Racing Medium"), ("tyre_rear", "Racing Medium"),
    ("tvcd", ""), ("ecu_ingame", "Stock"), ("transmission_type", "Stock"),
    ("nitrous_type", "None"), ("notes", ""), ("ecu_recommendation", ""),
    ("captured_at", ""),
)

_NUM_DEFAULTS = {name: default for name, default, _dp in NUMERIC_FIELDS}
_NUM_DECIMALS = {name: dp for name, _d, dp in NUMERIC_FIELDS}
_TEXT_DEFAULTS = dict(TEXT_FIELDS)

#: Fields that describe the CONTEXT a sheet was captured in rather than the setup
#: itself. They are carried along but never count as a setup difference — otherwise
#: simply re-reading a sheet a minute later would look like a change.
CONTEXT_FIELDS: frozenset = frozenset({
    "name", "car", "track", "condition", "setup_type", "captured_at",
    "bop_race", "ecu_recommendation",
})

#: Every field a complete sheet carries.
ALL_FIELDS: Tuple[str, ...] = tuple(_NUM_DEFAULTS) + tuple(_TEXT_DEFAULTS) + (
    "gear_ratios", "bop_race")


def _num(value, default: float, decimals: int) -> float:
    try:
        if value is None or value == "":
            return round(float(default), decimals)
        return round(float(value), decimals)
    except (TypeError, ValueError):
        return round(float(default), decimals)


def _text(value, default: str = "") -> str:
    if value is None:
        return default
    try:
        return str(value).strip()
    except Exception:  # pragma: no cover - defensive
        return default


def _gears(value) -> Tuple[float, ...]:
    """Gear ratios, in order, dropping unset entries. Never raises."""
    out = []
    for v in (value or ()):
        try:
            f = round(float(v), 3)
        except (TypeError, ValueError):
            continue
        if f > 0:
            out.append(f)
    return tuple(out)


@dataclass(frozen=True)
class SetupSheet:
    """One discipline's complete setup, as a value.

    Construct with :func:`sheet_from_dict`; read with :meth:`as_dict` (the exact shape
    the existing save/apply/advisor paths already consume).
    """

    values: Mapping[str, Any] = field(default_factory=dict)

    # ---- read ------------------------------------------------------------
    def get(self, field_name: str, default=None):
        return self.values.get(field_name, default)

    def as_dict(self) -> Dict[str, Any]:
        """A mutable copy in the canonical shape."""
        return dict(self.values)

    @property
    def is_authored(self) -> bool:
        """Whether this sheet holds a real setup rather than bare defaults.

        A sheet nobody has authored must never be presented as "your setup" — that is
        what made an empty Garage look like a configured one.
        """
        for name, default, dp in NUMERIC_FIELDS:
            if _num(self.values.get(name), default, dp) != round(float(default), dp):
                return True
        return bool(self.gear_ratios)

    @property
    def gear_ratios(self) -> Tuple[float, ...]:
        return _gears(self.values.get("gear_ratios"))

    # ---- write (always returns a NEW sheet) --------------------------------
    def merge(self, changes: Optional[Mapping]) -> "SetupSheet":
        """A new sheet with ``changes`` applied over this one, normalised."""
        if not changes:
            return self
        merged = dict(self.values)
        merged.update(dict(changes))
        return sheet_from_dict(merged)

    def diff(self, other: "SetupSheet") -> Dict[str, Tuple[Any, Any]]:
        """``{field: (mine, theirs)}`` for every SETUP field that differs.

        Context fields are excluded, so re-capturing the same setup a minute later is
        correctly reported as no change at all.
        """
        if not isinstance(other, SetupSheet):
            return {}
        out: Dict[str, Tuple[Any, Any]] = {}
        for name in ALL_FIELDS:
            if name in CONTEXT_FIELDS:
                continue
            mine, theirs = self.values.get(name), other.values.get(name)
            if name == "gear_ratios":
                mine, theirs = self.gear_ratios, other.gear_ratios
            if mine != theirs:
                out[name] = (mine, theirs)
        return out

    def matches(self, other: "SetupSheet") -> bool:
        return not self.diff(other)


def sheet_from_dict(d: Optional[Mapping]) -> SetupSheet:
    """Normalise any setup dict into a complete, typed sheet. Never raises.

    Unknown keys are preserved untouched — the advisor and the DB both round-trip
    fields this model does not know about, and silently dropping them would corrupt a
    saved setup.
    """
    src = dict(d or {})
    values: Dict[str, Any] = {}
    for name, default, dp in NUMERIC_FIELDS:
        values[name] = _num(src.pop(name, None), default, dp)
    for name, default in TEXT_FIELDS:
        values[name] = _text(src.pop(name, None), default)
    values["gear_ratios"] = list(_gears(src.pop("gear_ratios", ())))
    values["bop_race"] = bool(src.pop("bop_race", False))
    # Anything else the caller carried stays with the sheet.
    values.update(src)
    return SetupSheet(values=values)


def empty_sheet() -> SetupSheet:
    """A sheet of pure defaults — explicitly NOT an authored setup."""
    return sheet_from_dict({})


#: The two disciplines that have a sheet. There is no third.
DISCIPLINES: Tuple[str, ...] = ("race", "qualifying")

#: Discipline -> the purpose string the setup authority and the advisor use.
PURPOSE: Dict[str, str] = {"race": "Race", "qualifying": "Qualifying"}


def normalise_discipline(value) -> str:
    d = _text(value).lower()
    return d if d in DISCIPLINES else "race"
