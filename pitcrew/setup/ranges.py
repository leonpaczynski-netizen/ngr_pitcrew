"""Slider ranges per car — the `rangeRecord` section, and what survives.

**The setup sheet is gone from this app.** The car is held by the tune
builder; changes come back as a document the driver types into GT7 and
confirms with a screenshot. Nothing here records what is in the car, and
nothing here has an opinion about what should be.

What did not go is the range record, because it is not a setup. It is the
measured min and max of each slider on one car, which is what lets the whole
programme reason in **percent of slider range instead of absolute values** —
`3.5 Hz` means different things on different cars, so a bare number does not
travel. Those ranges are measured once per car off the car's own settings
screen and never re-entered, and they outlive every sheet ever run on it.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from pitcrew.setup.vocabulary import RANGE_KEY_NAMES


class SetupError(ValueError):
    """A range record that must not reach the export."""


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
