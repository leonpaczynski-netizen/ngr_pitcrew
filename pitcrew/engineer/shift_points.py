"""The upshift rpm table, and who is allowed to author one.

**The driver does not enter these any more, and neither does the app.** They
are issued by the tune builder alongside the setup they belong to, because a
shift point is a property of the gearbox: change a single ratio or the final
drive and the rpm worth shifting at moves with it. A table typed in by hand
against last week's box is a number that sounds exactly like a measurement
at the wheel while being a memory of a different car.

### Two tables, because there are two ways to drive the same gearbox

`performance` is the rpm to take each gear to when lap time is the whole
objective. `fuel_saving` is where to short-shift when the stint is fuel-bound
— worth about 20% fuel for about 0.5 s/lap, and it lowers rear tyre wear
as well, so it is the engineer's highest-value live call after the tow.

Both are **absolute rpm per gear**, not a table and an offset. An offset
hides the thing worth checking: a fuel-saving point above its own performance
point is a contradiction, and stated as a drop it reads as a negative number
nobody looks at. Stated absolutely it is refused here, by name.

### What missing means

**A gear absent from `performance` does not beep**, and that is the honest
answer rather than a fallback. `ShiftBeep.threshold_for` says why at length:
one car wants the limiter in every gear and another wants 8250 in all five,
which is the whole reason this is a table, and any fallback tells the driver
a number nobody took on that gearbox.

A gear present in `performance` and absent from `fuel_saving` falls back to
`ShiftBeep`'s scalar drop, which is a stated default rather than a
measurement, and it is the one place that is acceptable — the alternative is
the beep going silent the moment fuel saving is called for.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from pitcrew.setup.vocabulary import MAX_GEARS

# Nothing below this is an upshift; nothing above it is an engine.
MIN_RPM = 1_000.0
MAX_RPM = 30_000.0


class ShiftPointError(ValueError):
    """A table that must not reach the beep."""


@dataclass
class ShiftPoints:
    """One gearbox's upshift table, as issued.

    `circuit_key` is part of the identity, not decoration: the gearbox is cut
    for the circuit, so the same car at two tracks is two boxes and wants two
    tables. None means it was issued without one, and it will not be asserted
    to be for the circuit in front of us — the same rule the setup record was
    given after a Road Atlanta session bound itself to a Yas Marina sheet.
    """
    car_name: str
    circuit_key: str | None = None
    performance: dict[int, float] = field(default_factory=dict)
    fuel_saving: dict[int, float] = field(default_factory=dict)
    # Who issued it and when. Free text on purpose: the point is that a table
    # can be traced back to the document that carried it, not that the app
    # can parse the attribution.
    issued_by: str = ""
    issued_at: str = ""
    note: str = ""
    id: int | None = None

    def validate(self) -> None:
        if not self.car_name.strip():
            raise ShiftPointError("a shift table needs a car")
        for label, table in (("performance", self.performance),
                             ("fuel saving", self.fuel_saving)):
            for gear, rpm in (table or {}).items():
                if not isinstance(gear, int) or not 1 <= gear <= MAX_GEARS:
                    raise ShiftPointError(
                        f"{label} is keyed by gear number, got {gear!r}")
                if rpm is None or not MIN_RPM < float(rpm) < MAX_RPM:
                    raise ShiftPointError(
                        f"gear {gear} {label} is not an upshift rpm: {rpm!r}")

        # **A fuel-saving point is a SHORT shift.** Above its own performance
        # point it is not a saving, it is a transcription error with the two
        # columns swapped - which is silent at the wheel and costs fuel in the
        # direction the driver was told it saved.
        stray = sorted(set(self.fuel_saving) - set(self.performance))
        if stray:
            raise ShiftPointError(
                "fuel saving names gears performance does not: "
                + ", ".join(str(g) for g in stray))
        wrong = [g for g, rpm in self.fuel_saving.items()
                 if float(rpm) >= float(self.performance[g])]
        if wrong:
            raise ShiftPointError(
                "fuel saving is not below performance in gear "
                + ", ".join(str(g) for g in sorted(wrong))
                + " - check the two columns are not swapped")

    def drops(self) -> dict[int, float]:
        """Per-gear short-shift drop, for `ShiftBeep`.

        Arithmetic, not a model: the beep works in base-minus-drop and the
        table is authored in absolute rpm, so this is the one conversion
        between them and it lives here rather than in three callers.
        """
        return {gear: float(self.performance[gear]) - float(rpm)
                for gear, rpm in self.fuel_saving.items()}

    def as_export(self) -> dict:
        """What the driver was actually being told, for the audit trail."""
        self.validate()
        payload: dict = {
            "car": self.car_name,
            "performanceRpm": {str(g): float(r)
                               for g, r in sorted(self.performance.items())},
        }
        if self.circuit_key:
            payload["circuit"] = self.circuit_key
        if self.fuel_saving:
            payload["fuelSavingRpm"] = {str(g): float(r) for g, r
                                        in sorted(self.fuel_saving.items())}
        if self.issued_by:
            payload["issuedBy"] = self.issued_by
        if self.issued_at:
            payload["issuedAt"] = self.issued_at
        if self.note:
            payload["note"] = self.note
        return payload
