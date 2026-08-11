"""Building and validating the `gt7-pitcrew/1.2` payload.

This is the app's most important output. It is pasted into a prompt and read by
a language model, not parsed by a program — so a malformed payload does not
throw, it gets misread and a setup gets built on it. Hence `validate()`, and
hence `to_json()` refusing to emit rather than emitting something wrong.

Sections are omitted when the app does not have them. An omitted section reads
as "not built yet"; a section full of nulls reads as "built but nothing
measured". Both are honest. A section full of zeros is not.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field

from pitcrew.telemetry.packet import STEER_SOURCE
from pitcrew.telemetry.recorder import DEFAULT_STEER_ROTATION_DEG

FORMAT = "gt7-pitcrew/1.2"
APP_VERSION = "pitcrew 2.1.0"

SESSION_TYPES = ("practice", "quali", "tt", "race")
PACKET_FORMATS = ("A", "B", "~", "C")
ABS_SETTINGS = ("Off", "Weak", "Default")
CORNER_MODEL_SOURCES = ("track-map", "auto-segment")


class ExportRefused(ValueError):
    """The payload would be misread. Fix it rather than send it."""


@dataclass
class Meta:
    car: str
    circuit: str
    date: str                       # YYYY-MM-DD
    session_type: str
    packet: str
    car_category: str | None = None
    game_version: str | None = None
    compound_front: str | None = None
    compound_rear: str | None = None
    abs_setting: str | None = None
    tcs: int | None = None
    countersteer: bool | None = None
    tyre_wear_mult: str | None = None       # "Off" or "4x" - a string, so Off fits
    fuel_mult: str | None = None
    corner_model: dict | None = None
    app_version: str = APP_VERSION

    def as_export(self) -> dict:
        payload: dict = {
            "car": self.car,
            "carCategory": self.car_category,
            "circuit": self.circuit,
            "date": self.date,
            "sessionType": self.session_type,
            "packet": self.packet,
            "appVersion": self.app_version,
        }
        if self.game_version:
            payload["gameVersion"] = self.game_version
        if self.compound_front or self.compound_rear:
            payload["compound"] = {
                "front": self.compound_front,
                "rear": self.compound_rear,
            }
        if any(v is not None for v in (self.abs_setting, self.tcs, self.countersteer)):
            payload["assists"] = {
                "abs": self.abs_setting,
                "tcs": self.tcs,
                "countersteer": self.countersteer,
            }
        if self.tyre_wear_mult is not None or self.fuel_mult is not None:
            payload["multipliers"] = {
                "tyreWear": self.tyre_wear_mult,
                "fuel": self.fuel_mult,
            }
        if self.corner_model is not None:
            payload["cornerModel"] = self.corner_model
        return payload


@dataclass
class Derived:
    """The `derived` section: everything the app computed, with its thresholds."""
    thresholds: dict
    bottoming_ref_mm: dict | None = None
    bottoming_ref_source: str | None = None
    steer_source: str = STEER_SOURCE
    steer_rotation_deg: float = DEFAULT_STEER_ROTATION_DEG
    extra: dict = field(default_factory=dict)

    def as_export(self) -> dict:
        payload = {
            "thresholds": dict(self.thresholds),
            "steerSource": self.steer_source,
            "steerRotationDeg": self.steer_rotation_deg,
        }
        if self.bottoming_ref_mm is not None:
            payload["bottomingRefMm"] = dict(self.bottoming_ref_mm)
            payload["bottomingRefSource"] = (
                self.bottoming_ref_source
                or "lowest suspension height observed across the counted laps")
        payload.update(self.extra)
        return payload


def build_payload(meta: Meta, *,
                  setup: dict | None = None,
                  driver_changes: list[dict] | None = None,
                  range_record: dict | None = None,
                  session: dict | None = None,
                  laps: list[dict] | None = None,
                  corners: list[dict] | None = None,
                  wear: dict | None = None,
                  gearing: dict | None = None,
                  strategy: dict | None = None,
                  derived: Derived | None = None,
                  notes: str = "") -> dict:
    """Assemble the payload. Empty sections are omitted, not emitted as nulls."""
    payload: dict = {"format": FORMAT, "meta": meta.as_export()}

    if setup:
        section = dict(setup)
        if driver_changes:
            section["driverChanges"] = list(driver_changes)
        payload["setup"] = section
    if range_record:
        payload["rangeRecord"] = range_record
    if session:
        payload["session"] = session
    if laps:
        payload["laps"] = list(laps)
    if corners:
        payload["corners"] = list(corners)
    if wear:
        payload["wear"] = wear
    if gearing:
        payload["gearing"] = gearing
    if strategy:
        payload["strategy"] = strategy
    if derived is not None:
        payload["derived"] = derived.as_export()
    if notes:
        payload["notes"] = notes

    return payload


def validate(payload: dict) -> list[str]:
    """Everything wrong with this payload, as readable sentences."""
    problems: list[str] = []

    if payload.get("format") != FORMAT:
        problems.append(f"format must be {FORMAT!r}, got {payload.get('format')!r}")

    meta = payload.get("meta")
    if not isinstance(meta, dict):
        problems.append("meta is required")
        return problems

    for key in ("car", "circuit", "date", "sessionType", "packet"):
        if not meta.get(key):
            problems.append(f"meta.{key} is required")

    if meta.get("sessionType") and meta["sessionType"] not in SESSION_TYPES:
        problems.append(
            f"meta.sessionType must be one of {SESSION_TYPES}, "
            f"got {meta['sessionType']!r}")
    if meta.get("packet") and meta["packet"] not in PACKET_FORMATS:
        problems.append(
            f"meta.packet must be one of {PACKET_FORMATS}, got {meta['packet']!r}")

    date = meta.get("date") or ""
    if date and (len(date) != 10 or date[4] != "-" or date[7] != "-"):
        problems.append(f"meta.date must be YYYY-MM-DD, got {date!r}")

    assists = meta.get("assists")
    if isinstance(assists, dict):
        if assists.get("abs") is not None and assists["abs"] not in ABS_SETTINGS:
            problems.append(
                f"meta.assists.abs must be one of {ABS_SETTINGS}, "
                f"got {assists['abs']!r}")
        tcs = assists.get("tcs")
        if tcs is not None and not (isinstance(tcs, int) and 0 <= tcs <= 5):
            problems.append(f"meta.assists.tcs must be an integer 0-5, got {tcs!r}")

    multipliers = meta.get("multipliers")
    if isinstance(multipliers, dict):
        for key, value in multipliers.items():
            if value is not None and not isinstance(value, str):
                problems.append(
                    f"meta.multipliers.{key} must be a string so that 'Off' is "
                    f"representable, got {value!r}")

    problems.extend(_validate_corners(payload, meta))
    problems.extend(_validate_laps(payload))
    problems.extend(_validate_wear(payload))
    problems.extend(_validate_no_tow(payload))
    problems.extend(_validate_strategy(payload))
    return problems


def _validate_no_tow(payload: dict) -> list[str]:
    """GT7 carries no proximity, closing speed or opponent positions, so a tow
    cannot be detected. Any key named after one is a fabrication by definition,
    and this refuses it wherever it appears."""
    offenders: list[str] = []

    def walk(node, path: str) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if "tow" in key.lower():
                    offenders.append(f"{path}.{key}" if path else key)
                walk(value, f"{path}.{key}" if path else key)
        elif isinstance(node, list):
            for index, value in enumerate(node):
                walk(value, f"{path}[{index}]")

    walk(payload, "")
    return [f"{name} claims a tow, which GT7's feed cannot detect"
            for name in offenders]


def _validate_strategy(payload: dict) -> list[str]:
    strategy = payload.get("strategy")
    if not isinstance(strategy, dict):
        return []
    problems = []
    assumptions = strategy.get("assumptions")
    if not isinstance(assumptions, dict):
        problems.append("strategy.assumptions is required alongside a plan")
        return problems
    if assumptions.get("refuelRateLps") in (None, ""):
        problems.append(
            "strategy.assumptions.refuelRateLps is required - it is the number "
            "that decides the race, and a default in its place is unreadable")
    constraint = strategy.get("bindingConstraint")
    if constraint not in ("tyre", "fuel", "regulation", "unknown", None):
        problems.append(
            f"strategy.bindingConstraint must be tyre, fuel, regulation or "
            f"unknown, got {constraint!r}")
    return problems


def _validate_corners(payload: dict, meta: dict) -> list[str]:
    corners = payload.get("corners")
    if corners is None:
        return []
    problems = []

    model = meta.get("cornerModel")
    if not isinstance(model, dict):
        problems.append(
            "meta.cornerModel is required whenever corners are present - "
            "without it the corner ids cannot be compared across sessions")
    else:
        if model.get("source") not in CORNER_MODEL_SOURCES:
            problems.append(
                f"meta.cornerModel.source must be one of {CORNER_MODEL_SOURCES}, "
                f"got {model.get('source')!r}")
        if not model.get("id"):
            problems.append("meta.cornerModel.id is required")

    for index, corner in enumerate(corners):
        where = corner.get("id") or f"corners[{index}]"
        if not corner.get("id"):
            problems.append(f"{where} has no id")
        samples = corner.get("samples")
        if not isinstance(samples, int) or samples < 1:
            problems.append(
                f"{where} must carry its sample count - a metric from two laps "
                f"and one from eleven are not the same claim")
    return problems


def _validate_laps(payload: dict) -> list[str]:
    laps = payload.get("laps")
    if laps is None:
        return []
    problems = []
    for index, lap in enumerate(laps):
        where = f"laps[{index}]"
        if not isinstance(lap.get("lap"), int):
            problems.append(f"{where}.lap must be an integer")
        time_ms = lap.get("timeMs")
        if not isinstance(time_ms, int):
            problems.append(
                f"{where}.timeMs must be integer milliseconds, never a "
                f"formatted string, got {time_ms!r}")
    return problems


def _validate_wear(payload: dict) -> list[str]:
    wear = payload.get("wear")
    if not isinstance(wear, dict):
        return []
    problems = []
    if wear.get("channelAvailable") is not False:
        problems.append(
            "wear.channelAvailable must be false - GT7 exposes no tyre wear "
            "channel in any packet format")
    for index, reading in enumerate(wear.get("byDriverGauge") or []):
        for axle in ("front", "rear"):
            value = reading.get(axle)
            if value is None:
                continue
            if not 0.0 <= value <= 1.0:
                problems.append(
                    f"wear.byDriverGauge[{index}].{axle} is a fraction consumed "
                    f"0-1, got {value!r}")
    confidence = wear.get("modelConfidence")
    if confidence is not None and confidence not in ("measured", "assumed", "converted"):
        problems.append(
            f"wear.modelConfidence must be measured, assumed or converted, "
            f"got {confidence!r}")
    return problems


def to_json(payload: dict, *, indent: int = 2) -> str:
    """Serialise, refusing rather than emitting something that would be misread."""
    problems = validate(payload)
    if problems:
        raise ExportRefused(
            "refusing to export - the payload would be misread:\n  - "
            + "\n  - ".join(problems))
    return json.dumps(payload, indent=indent, ensure_ascii=False)
