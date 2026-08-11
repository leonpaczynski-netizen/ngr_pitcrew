"""Read a setup sheet the tune builder returned, in whatever shape it came in.

The sheet arrives as pasted text. It might be the export contract's own JSON,
it might be `rh_f: 62` lines, it might be a markdown table with human labels.
All three are read here.

The rule that matters: **never silently drop a line.** Anything not understood
comes back in `unmatched` so the screen can show it, because a value quietly
missed is a setup change the driver thinks he made and did not.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from pitcrew.setup.vocabulary import SETUP_KEYS, SETUP_KEY_NAMES

# Human spellings the tune builder or GT7's own screens might use. Keys are
# matched case-insensitively with punctuation stripped, so "Ride Height (Front)"
# and "ride height front" both land.
_ALIASES: dict[str, str] = {
    "ride height front": "rh_f", "ride height rear": "rh_r",
    "front ride height": "rh_f", "rear ride height": "rh_r",
    "natural frequency front": "nf_f", "natural frequency rear": "nf_r",
    "spring rate front": "nf_f", "spring rate rear": "nf_r",
    "anti roll bar front": "arb_f", "anti roll bar rear": "arb_r",
    "antiroll bar front": "arb_f", "antiroll bar rear": "arb_r",
    "arb front": "arb_f", "arb rear": "arb_r",
    "damper compression front": "dc_f", "damper compression rear": "dc_r",
    "compression front": "dc_f", "compression rear": "dc_r",
    "damper extension front": "de_f", "damper extension rear": "de_r",
    "extension front": "de_f", "extension rear": "de_r",
    "rebound front": "de_f", "rebound rear": "de_r",
    "camber front": "cam_f", "camber rear": "cam_r",
    "toe front": "toe_f", "toe rear": "toe_r",
    "toe angle front": "toe_f", "toe angle rear": "toe_r",
    "initial torque": "lsd_i", "lsd initial torque": "lsd_i",
    "acceleration sensitivity": "lsd_a", "lsd acceleration": "lsd_a",
    "braking sensitivity": "lsd_b", "lsd braking": "lsd_b",
    "front torque distribution": "awd", "torque split": "awd",
    "downforce front": "df_f", "downforce rear": "df_r",
    "front downforce": "df_f", "rear downforce": "df_r",
    "brake balance": "bb", "brake bias": "bb",
    "top speed": "top", "final gear": "fg", "final drive": "fg",
}
_ALIASES.update({key.label.lower(): key.key for key in SETUP_KEYS})

_PUNCT = re.compile(r"[^a-z0-9 ]+")
_NUMBER = re.compile(r"-?\d+(?:\.\d+)?")
_GEAR_LINE = re.compile(r"^\s*(?:gear\s*)?(\d)(?:st|nd|rd|th)?\s*[:=]\s*(-?\d+(?:\.\d+)?)",
                        re.IGNORECASE)


@dataclass
class ParsedSheet:
    values: dict[str, float] = field(default_factory=dict)
    gears: list[float] = field(default_factory=list)
    sheet_name: str | None = None
    unmatched: list[str] = field(default_factory=list)
    source: str = "text"

    @property
    def matched_count(self) -> int:
        return len(self.values)

    def summary(self) -> str:
        parts = [f"{len(self.values)} of {len(SETUP_KEY_NAMES)} settings"]
        if self.gears:
            parts.append(f"{len(self.gears)} gears")
        if self.unmatched:
            parts.append(f"{len(self.unmatched)} lines not recognised")
        return ", ".join(parts)


def _normalise(text: str) -> str:
    return _PUNCT.sub(" ", text.strip().lower()).strip()


def _resolve_key(label: str) -> str | None:
    cleaned = _normalise(label)
    if not cleaned:
        return None
    compact = cleaned.replace(" ", "_")
    if compact in SETUP_KEY_NAMES:
        return compact
    collapsed = " ".join(cleaned.split())
    return _ALIASES.get(collapsed)


def parse_sheet(text: str) -> ParsedSheet:
    """Read a pasted sheet. Always returns a result; never raises on junk."""
    if not text or not text.strip():
        return ParsedSheet()

    stripped = text.strip()
    if stripped.startswith("{"):
        parsed = _parse_json(stripped)
        if parsed is not None:
            return parsed
    return _parse_lines(stripped)


def _parse_json(text: str) -> ParsedSheet | None:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None

    # Accept either a bare setup object or a whole gt7-pitcrew payload.
    setup = payload.get("setup") if isinstance(payload.get("setup"), dict) else payload
    raw_values = setup.get("values")
    if not isinstance(raw_values, dict):
        return None

    result = ParsedSheet(source="json", sheet_name=setup.get("sheetName"))
    for key, value in raw_values.items():
        if key in SETUP_KEY_NAMES and isinstance(value, (int, float)):
            result.values[key] = float(value)
        elif key not in SETUP_KEY_NAMES:
            result.unmatched.append(f"{key}: {value}")

    gears = setup.get("gears")
    if isinstance(gears, list):
        result.gears = [float(g) for g in gears
                        if isinstance(g, (int, float)) and g > 0]
    return result


def _parse_lines(text: str) -> ParsedSheet:
    result = ParsedSheet(source="text")
    inline_gears: dict[int, float] = {}

    for raw in text.splitlines():
        line = raw.strip().strip("|").strip()
        if not line or set(line) <= set("-=|_ "):
            continue

        gear_match = _GEAR_LINE.match(line)
        if gear_match and "gear" in line.lower():
            inline_gears[int(gear_match.group(1))] = float(gear_match.group(2))
            continue

        if _looks_like_gear_list(line):
            numbers = [float(n) for n in _NUMBER.findall(line)]
            ratios = [n for n in numbers if n > 0]
            if len(ratios) >= 2:
                result.gears = ratios
                continue

        label, value = _split_label_value(line)
        if label is None:
            result.unmatched.append(line)
            continue

        key = _resolve_key(label)
        if key is None:
            result.unmatched.append(line)
            continue
        result.values[key] = value

    if inline_gears and not result.gears:
        result.gears = [inline_gears[n] for n in sorted(inline_gears)]
    return result


def _looks_like_gear_list(line: str) -> bool:
    head = _normalise(line.split(":")[0] if ":" in line else line)
    return head.startswith("gears") or head.startswith("gear ratios")


def _split_label_value(line: str) -> tuple[str | None, float]:
    """Split "Camber Front: 1.2 deg" into ("Camber Front", 1.2)."""
    for separator in (":", "=", "\t", "|"):
        if separator in line:
            label, _, tail = line.partition(separator)
            numbers = _NUMBER.findall(tail)
            if numbers:
                return label, float(numbers[0])
            return None, 0.0

    # "Camber Front 1.2" - the value is the trailing number.
    numbers = _NUMBER.findall(line)
    if not numbers:
        return None, 0.0
    trailing = numbers[-1]
    index = line.rfind(trailing)
    label = line[:index]
    return (label, float(trailing)) if label.strip() else (None, 0.0)
