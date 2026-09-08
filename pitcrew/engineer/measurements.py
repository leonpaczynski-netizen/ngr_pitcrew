"""What has been measured, and what an axis is believed to do about it.

Two records, and the second one exists mostly so that *"nobody has ever tried
this"* has somewhere to be true.

### Why they exist

The race engineer derives numbers off `lap_frames` every session — an on-power
rotation index at a corner exit, an opposite-lock rate, a rake-against-fuel
slope — writes them into prose, and derives them again from scratch next time.
Two wrong calls in one day on 8 Sep 2026 came out of that:

1. **Ride height had never been A/B'd on any car in the programme**, and nobody
   knew, because there was nowhere that fact could live. `untested` is not a
   gap in this record; it is the answer it is built to give, and
   `Store.untested_axes` is the question it answers.
2. **`lsd_a` was recorded as "refuted as an exit lever"** on the strength of
   rear wheel-speed split. The split then sat at a median of 0.0000 through a
   six-click `lsd_a` change while the rotation index moved to twice its own
   noise floor. **A channel that cannot see the change never refuted the
   lever** — and the record could not say which channel had been used. So a
   `Verdict` names the instrument it rests on or it is refused, and
   `unresolvable` exists as a distinct answer from `refuted`: the first is a
   statement about the instrument and the second is a statement about the car,
   and closing an axis on the first while writing down the second is exactly
   how an open lever gets closed.

### What they may not hold

⛔ **No setup values.** `brain/car-state/<car>-<circuit>.md` is the only place
one may be written (`CLAUDE.md` §1a), and a copy here would be the second copy
that was removed on 5 Sep after five sessions ran against the wrong sheet. A
`Measurement` points at the configuration it was taken under by *reference* —
`config_ref`, a pointer into that file — and says nothing about what was in the
car. Two rows with the same `config_ref` were taken on the same car; two with
different ones were not. What differs is in the file, not here.

`Measurement.validate` enforces that as far as text can be enforced: a
`config_ref` that reads like a slider assignment (`rh_r=64`, `lsd_a 8`) is
refused by name, because that is exactly how the second copy gets in.

### The three rules that shaped the fields

* **Rule 3, missing is null.** `noise_floor` is nullable and NULL means *not
  established*. A literal `0.0` is refused: a floor of zero says every
  difference is resolvable, which is `max(x, 0.0)` (rule 9) wearing a
  different hat.
* **Rule 4, every aggregate carries its sample count.** `n` and `n_basis`
  together — "n=15" of laps and of braking events are not the same claim.
* **Rule 5, nothing derived is presented as measured.** `source` is one of
  five words and it is not optional.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

from pitcrew.setup.vocabulary import SETUP_KEYS

# The five classes of evidence this programme recognises, from `CLAUDE.md`
# §4.5 and the tags the knowledge base already writes in prose. `DRIVER
# REPORT` is first among equals rather than the weakest: rule 1 makes the
# driver's report primary evidence and telemetry the corroboration.
SOURCES: frozenset[str] = frozenset({
    "MEASURED", "DERIVED", "DOCTRINE", "ASSUMED", "DRIVER REPORT",
})

# What a scope says the number is *about*. A rotation index at a corner exit
# and a fuel-per-lap figure are not comparable claims and the readers need to
# be able to tell them apart without parsing the metric name.
SCOPES: frozenset[str] = frozenset({
    "corner", "lap", "stint", "session", "car",
})

VERDICTS: frozenset[str] = frozenset({
    # The axis does what was claimed, on a named instrument that can see it.
    "confirmed",
    # The axis does not — and the instrument was capable of showing that it
    # did. This is a statement about the car.
    "refuted",
    # Nobody has tried it. The default for an axis with no rows; written down
    # only as "we went looking and there is nothing".
    "untested",
    # The axis moved and the instrument did not, or the difference was inside
    # the instrument's floor. **A statement about the instrument, not the
    # car**, and the distinction is the whole 8 Sep `lsd_a` lesson.
    "unresolvable",
})

# A refutation carries a direction. "lsd_a refuted" only ever tested RAISING
# it; lowering it turned out to be resolvable and to point the other way.
DIRECTIONS: frozenset[str] = frozenset({"up", "down", "both"})

# The slider keys, from the one module allowed to spell them
# (`EXPORT-CONTRACT.md` §6 vocabulary). An axis outside this set is a key
# somebody invented, which is the mismatch that vocabulary exists to prevent.
AXES: frozenset[str] = frozenset(k.key for k in SETUP_KEYS)

# A `config_ref` is a pointer. Anything of the shape `key=64`, `key 64` or
# `key:64` for a real slider key is a setup VALUE, and the value belongs in
# the car-state file and nowhere else.
_LOOKS_LIKE_A_SETTING = re.compile(
    r"\b(" + "|".join(sorted(AXES, key=len, reverse=True)) +
    r")\s*[=:]?\s*-?\d", re.IGNORECASE)


class MeasurementError(ValueError):
    """A row that must not reach the store."""


def _finite(value, label: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise MeasurementError(f"{label} is {value!r}, which is not a number")
    return number


@dataclass
class Measurement:
    """One derived number, with everything needed to trust or refuse it.

    A row **is** a number: `value` is not nullable. A quantity that could not
    be computed is not a measurement with a null in it — it is a `Verdict` of
    `unresolvable`, which says which instrument failed and why. Rule 9 in the
    other direction: nothing here is clamped to make it representable.
    """
    car_name: str
    metric: str
    value: float
    unit: str
    scope: str
    source: str
    # NULL means **not specific to a circuit** — a property of the car itself
    # — not "circuit unknown". Anything derived off frames has a circuit.
    circuit_key: str | None = None
    # The pointer into `brain/car-state/<car>-<circuit>.md`, never a value.
    config_ref: str | None = None
    # The short tag the write-up used for it — "A", "B", "C" — so a table in
    # prose can be joined back to these rows.
    config_label: str | None = None
    zone: str | None = None
    n: int | None = None
    n_basis: str | None = None
    # NULL is "not established". Never 0.0; see the module docstring.
    noise_floor: float | None = None
    floor_method: str | None = None
    tool: str | None = None
    session_ids: tuple[int, ...] = ()
    game_version: str | None = None
    measured_on: str | None = None
    note: str | None = None
    id: int | None = None

    def validate(self) -> None:
        if not (self.car_name or "").strip():
            raise MeasurementError("a measurement needs a car")
        if not (self.metric or "").strip():
            raise MeasurementError("a measurement needs a metric name")
        if not (self.unit or "").strip():
            raise MeasurementError(
                f"{self.metric}: a number with no unit is not a measurement "
                f"— `EXPORT-CONTRACT.md` §12 fixes the units")
        if self.scope not in SCOPES:
            raise MeasurementError(
                f"scope {self.scope!r} is not one of {sorted(SCOPES)}")
        if self.source not in SOURCES:
            raise MeasurementError(
                f"source {self.source!r} is not one of {sorted(SOURCES)} — "
                f"rule 5: nothing derived is presented as measured")
        _finite(self.value, f"{self.metric}: value")

        if self.scope == "corner" and not (self.zone or "").strip():
            raise MeasurementError(
                f"{self.metric}: a corner-scoped measurement has to say which "
                f"corner — corner aggregates are worthless if the identity "
                f"moves (CLAUDE.md §3.3)")
        if self.zone is not None and not self.zone.strip():
            raise MeasurementError(
                "zone is the empty string, which reads as a zone; use None")

        if self.n is not None:
            if int(self.n) <= 0:
                raise MeasurementError(
                    f"{self.metric}: n is {self.n} — a sample count of zero or "
                    f"less is not a smaller measurement, it is no measurement")
            if not (self.n_basis or "").strip():
                raise MeasurementError(
                    f"{self.metric}: n={self.n} of what? Rule 4 — set "
                    f"n_basis ('clean laps', 'braking events', 'frames')")

        if self.noise_floor is not None:
            floor = _finite(self.noise_floor, f"{self.metric}: noise_floor")
            if floor == 0.0:
                raise MeasurementError(
                    f"{self.metric}: a noise floor of 0.0 says every "
                    f"difference is resolvable. If it was not established, "
                    f"leave it NULL — rule 3, and rule 9's clamp in disguise")
            if floor < 0.0:
                raise MeasurementError(
                    f"{self.metric}: noise floor {floor} is negative")
            if not (self.floor_method or "").strip():
                raise MeasurementError(
                    f"{self.metric}: a floor with no method behind it cannot "
                    f"be audited — say how it was obtained")

        self._refuse_setup_values()

    def _refuse_setup_values(self) -> None:
        """⛔ The config is referenced, never restated.

        `brain/car-state/<car>-<circuit>.md` is the only place a setup value
        may be written. This catches the obvious smuggling — a `config_ref` of
        `"rh_r=64 lsd_a 8"` — which is how the second copy gets in, one
        convenient label at a time.
        """
        for label in ("config_ref", "config_label"):
            text = getattr(self, label)
            if text and _LOOKS_LIKE_A_SETTING.search(str(text)):
                raise MeasurementError(
                    f"{label}={text!r} carries a slider value. A config is "
                    f"referenced here and written down in "
                    f"brain/car-state/<car>-<circuit>.md — one copy, or it is "
                    f"two values (CLAUDE.md §1a)")

    def as_export(self) -> dict:
        return {
            "id": self.id,
            "car": self.car_name,
            "circuit": self.circuit_key,
            "configRef": self.config_ref,
            "configLabel": self.config_label,
            "scope": self.scope,
            "zone": self.zone,
            "metric": self.metric,
            "value": self.value,
            "unit": self.unit,
            "n": self.n,
            "nBasis": self.n_basis,
            "noiseFloor": self.noise_floor,
            "floorMethod": self.floor_method,
            "source": self.source,
            "tool": self.tool,
            "sessionIds": list(self.session_ids),
            "gameVersion": self.game_version,
            "measuredOn": self.measured_on,
            "note": self.note,
        }

    def resolves(self, other: "Measurement") -> bool | None:
        """Is the gap between these two rows bigger than the floor?

        None where no floor is established on either row — which is the
        honest answer and the one the 1 Sep refutation needed and did not
        have. **Never `False` for want of a floor**: "I cannot tell" and "the
        change did nothing" are the two answers this whole record exists to
        keep apart.
        """
        floors = [f for f in (self.noise_floor, other.noise_floor)
                  if f is not None]
        if not floors:
            return None
        return abs(self.value - other.value) > max(floors)


@dataclass
class Verdict:
    """What an axis is believed to do here, and what said so.

    Append-only: a verdict is retired by writing a better one, never by
    editing. The 1 Sep `lsd_a` refutation had to be retired on 8 Sep, and the
    reason it was wrong — the instrument could not see the change — is itself
    a row worth keeping.
    """
    car_name: str
    axis: str
    verdict: str
    why: str
    circuit_key: str | None = None
    direction: str | None = None
    instrument: str | None = None
    instrument_floor: float | None = None
    measurement_ids: tuple[int, ...] = field(default_factory=tuple)
    decided_on: str | None = None
    game_version: str | None = None
    id: int | None = None
    recorded_at: str | None = None

    def validate(self) -> None:
        if not (self.car_name or "").strip():
            raise MeasurementError("a verdict needs a car")
        if self.axis not in AXES:
            raise MeasurementError(
                f"axis {self.axis!r} is not a slider key — "
                f"pitcrew/setup/vocabulary.py is the only place these are "
                f"spelled, and nothing else may invent one")
        if self.verdict not in VERDICTS:
            raise MeasurementError(
                f"verdict {self.verdict!r} is not one of {sorted(VERDICTS)}")
        if not (self.why or "").strip():
            raise MeasurementError(
                f"{self.axis}: a verdict with no reason cannot be argued "
                f"with, and it is the argument that turned out to matter")

        if self.direction is not None and self.direction not in DIRECTIONS:
            raise MeasurementError(
                f"direction {self.direction!r} is not one of "
                f"{sorted(DIRECTIONS)}")

        if self.verdict in ("confirmed", "refuted"):
            if self.direction is None:
                raise MeasurementError(
                    f"{self.axis}: a {self.verdict} verdict has to name the "
                    f"direction tested. '`lsd_a` refuted' only ever tested "
                    f"RAISING it, and lowering it pointed the other way")
            if not (self.instrument or "").strip():
                raise MeasurementError(
                    f"{self.axis}: a {self.verdict} verdict has to name the "
                    f"instrument. A channel that cannot see the change never "
                    f"refuted the lever, and the 1 Sep record could not say "
                    f"which channel had been used")
        if self.verdict == "unresolvable":
            if not (self.instrument or "").strip():
                raise MeasurementError(
                    f"{self.axis}: 'unresolvable' is a statement about an "
                    f"instrument, so it has to name the one that could not "
                    f"resolve it")
            # **The floor is NOT required here, and that is deliberate.**
            # An instrument fails in two ways: the change was inside a floor
            # somebody measured, or the instrument never moved at all and no
            # floor was ever established for it. The second is the 1 Sep
            # `lsd_a` case - the rear wheel-speed split sat at a median of
            # 0.0000 through a six-click change - and it is the row this whole
            # record exists to be able to write. Demanding a floor here would
            # refuse the motivating example, and the only floor available to
            # satisfy the demand would be a fabricated one.
        if self.verdict == "untested":
            if self.instrument or self.measurement_ids:
                raise MeasurementError(
                    f"{self.axis}: an 'untested' verdict that names an "
                    f"instrument or rests on measurements is not untested")

        if self.instrument_floor is not None:
            floor = _finite(self.instrument_floor,
                            f"{self.axis}: instrument_floor")
            if floor == 0.0:
                raise MeasurementError(
                    f"{self.axis}: an instrument floor of 0.0 says the "
                    f"instrument is perfect. Leave it NULL where it was never "
                    f"established")
            if floor < 0.0:
                raise MeasurementError(
                    f"{self.axis}: instrument floor {floor} is negative")

    def as_export(self) -> dict:
        return {
            "id": self.id,
            "car": self.car_name,
            "circuit": self.circuit_key,
            "axis": self.axis,
            "direction": self.direction,
            "verdict": self.verdict,
            "instrument": self.instrument,
            "instrumentFloor": self.instrument_floor,
            "measurementIds": list(self.measurement_ids),
            "decidedOn": self.decided_on,
            "gameVersion": self.game_version,
            "why": self.why,
            "recordedAt": self.recorded_at,
        }


# The answer for an axis nobody has touched. **Synthesised, not stored**: the
# absence of rows is what makes it true, so it costs nothing to be complete
# and it can never go stale.
NEVER_TESTED = ("nothing on file. No measurement and no verdict names this "
                "axis on this car at this circuit")


def untested(car_name: str, axis: str,
             circuit_key: str | None = None) -> Verdict:
    return Verdict(car_name=car_name, axis=axis, circuit_key=circuit_key,
                   verdict="untested", why=NEVER_TESTED)
