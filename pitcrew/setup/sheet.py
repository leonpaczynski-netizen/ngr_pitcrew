"""Setup sheets and car range records — the `setup` and `rangeRecord` sections.

Pure app state. No capture code, no derivation, no opinion. The value is that
it removes all ambiguity about which version of a sheet produced the symptoms
the driver reported.

Two rules from the contract are enforced here rather than at export time,
because by export time the information needed to honour them is gone:

* **A value that was never entered is `None`, not `0`.** A zero rear-toe and an
  unentered rear-toe are different claims and get diagnosed differently.
* **A range record says whether it was `verified`** — read off the car's own
  settings screen — or estimated. That difference decides whether a returned
  sheet can be entered without clamping.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from pitcrew.setup.vocabulary import (
    MAX_GEARS,
    RANGE_KEY_NAMES,
    SETUP_KEY_NAMES,
    unknown_keys,
)


class SetupError(ValueError):
    """A sheet or range record that must not reach the export."""


@dataclass
class SetupSheet:
    car_name: str
    sheet_name: str
    values: dict[str, float | None] = field(default_factory=dict)
    gears: list[float] = field(default_factory=list)
    performance: dict[str, float] = field(default_factory=dict)
    build: dict[str, float] = field(default_factory=dict)
    notes: str = ""
    # **What this sheet is for**: `race`, `qualifying`, or None where it
    # has not been said. Two sheets for one car are two different objects
    # answering different questions, not two versions of one - the tune
    # builder is asked for both and issues them separately, and a
    # qualifying sheet judged on stint consistency is being judged on
    # something it was never built for.
    #
    # None rather than defaulting to `race`: a sheet stored before the
    # question existed has not answered it.
    purpose: str | None = None
    # Set when the sheet came out of the store, so a session can record which
    # sheet was fitted without a second lookup.
    id: int | None = None

    def validate(self) -> None:
        if not self.car_name.strip():
            raise SetupError("a setup sheet needs a car")
        if not self.sheet_name.strip():
            raise SetupError("a setup sheet needs a name")

        stray = unknown_keys(self.values)
        if stray:
            raise SetupError(
                "not in the shared setup vocabulary: " + ", ".join(stray))

        for key, value in self.values.items():
            if value is not None and not isinstance(value, (int, float)):
                raise SetupError(f"{key} must be a number or None, got {value!r}")

        if len(self.gears) > MAX_GEARS:
            raise SetupError(f"{len(self.gears)} gears is more than GT7 allows")
        for index, ratio in enumerate(self.gears, start=1):
            if ratio is None or ratio <= 0:
                raise SetupError(f"gear {index} ratio must be positive")
        # GT7 gear ratios always descend from 1st.  An ascending pair means the
        # sheet was transcribed out of order, which is silent and expensive.
        for index in range(1, len(self.gears)):
            if self.gears[index] >= self.gears[index - 1]:
                raise SetupError(
                    f"gear {index + 1} ({self.gears[index]}) is not shorter than "
                    f"gear {index} ({self.gears[index - 1]}) - check the order")

    def entered_values(self) -> dict[str, float]:
        """Only the keys actually filled in."""
        return {k: v for k, v in self.values.items() if v is not None}

    def missing_keys(self) -> tuple[str, ...]:
        return tuple(k for k in SETUP_KEY_NAMES
                     if self.values.get(k) is None)

    def as_export(self) -> dict:
        """The `setup` section, contract shape. Empty sub-objects are omitted."""
        self.validate()
        payload: dict = {
            "sheetName": self.sheet_name,
            "values": {k: self.values.get(k) for k in SETUP_KEY_NAMES
                       if k in self.values},
        }
        # Omitted rather than defaulted where it has not been said. A sheet
        # stored before the question existed has not answered it, and calling
        # it a race sheet would be the app answering for him.
        if self.purpose:
            payload["purpose"] = self.purpose
        if self.gears:
            payload["gears"] = list(self.gears)
        if self.performance:
            payload["performance"] = dict(self.performance)
        if self.build:
            payload["build"] = dict(self.build)
        return payload


@dataclass
class SetupChange:
    """One mid-session change, as `setup.driverChanges`."""
    from_lap: int
    key: str
    from_value: float | None
    to_value: float | None

    def validate(self) -> None:
        if self.key not in SETUP_KEY_NAMES:
            raise SetupError(f"{self.key} is not in the shared setup vocabulary")
        if self.from_lap < 1:
            raise SetupError("a change applies from lap 1 at the earliest")

    def as_export(self) -> dict:
        self.validate()
        return {
            "fromLap": self.from_lap,
            "key": self.key,
            "from": self.from_value,
            "to": self.to_value,
        }


@dataclass
class RangeRecord:
    car_name: str
    measured_date: str
    ranges: dict[str, list[float]] = field(default_factory=dict)
    game_version: str | None = None
    verified: bool = False

    def validate(self) -> None:
        if not self.car_name.strip():
            raise SetupError("a range record needs a car")
        stray = tuple(sorted(set(self.ranges) - set(RANGE_KEY_NAMES)))
        if stray:
            raise SetupError("not a range-bearing setup key: " + ", ".join(stray))
        for key, bounds in self.ranges.items():
            if not isinstance(bounds, (list, tuple)) or len(bounds) != 2:
                raise SetupError(f"{key} range must be [min, max], got {bounds!r}")
            low, high = bounds
            if low is None or high is None:
                raise SetupError(f"{key} range has an empty bound")
            if low > high:
                raise SetupError(f"{key} range is inverted: [{low}, {high}]")

    def covers(self, key: str) -> bool:
        return key in self.ranges

    def fraction_of_range(self, key: str, value: float) -> float | None:
        """Where a value sits in its slider, 0..1, or None if not covered.

        The programme reasons in percent of slider range rather than absolute
        values, because GT7's ranges are per-car and derived from chassis data
        — "3.5 Hz" means different things on different cars.
        """
        bounds = self.ranges.get(key)
        if not bounds:
            return None
        low, high = bounds
        if high == low:
            return None
        return (value - low) / (high - low)

    def as_export(self) -> dict:
        self.validate()
        payload: dict = {
            "car": self.car_name,
            "measuredDate": self.measured_date,
            "verified": self.verified,
            "r": {k: list(v) for k, v in self.ranges.items()},
        }
        if self.game_version:
            payload["gameVersion"] = self.game_version
        return payload
