"""What would change the plan - flip points, plan row 5.1.

**A plan is a decision taken on numbers that each carry an error, and the
driver needs to know which error would change the decision.** Suzuka, 13 Sep
2026: strategy 32 planned one stop on a burn of 9.116 L/lap taken from four
practice laps at quali pace. The race burned about 7.4 L/lap for twelve laps
and then he saved to the flag on zero stops with 2.73 L left, against George's
"recommend 1 stop". Nothing on the plan said how close to a zero-stop it was.

This module answers that by **re-running the optimiser itself** across one
input at a time and reporting the value at which its first choice changes -
never by a second formula for the same decision (rule 12). It is a
**sensitivity, not a simulation**: one input moves while the rest hold, except
that in a timed race burn and lap time decide the distance together, so there
the burn flip is reported at each lap time across that input's own spread.

What a flip point is **not**: a forecast. It says where the decision turns; the
spread says how plausible it is that the race lands on the other side. The
spread quoted beside it is lap-to-lap scatter unless the caller supplies the
practice-to-race band, and the report says which it is.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Callable

from pitcrew.strategy.model import (
    Plan,
    RaceInputs,
    StrategyImpossible,
    recommend,
)

# How finely a flip is located. Finer than any of these inputs is measured.
TOLERANCE = {
    "fuel_per_lap_l": 0.01,       # litres per lap
    "wear_scale": 0.005,          # fraction of the stated wear rate
    "pit_loss_s": 0.25,           # seconds
    "refuel_rate_lps": 0.01,      # litres per second
    "lap_time_ms": 50.0,          # milliseconds
}

# How far either side of the plan's figure a flip is looked for, as a fraction
# of that figure. A decision that does not turn inside this band is reported as
# "does not flip within" the band - not as "cannot flip".
SEARCH_FRACTION = 0.40
SEARCH_STEPS = 24

INPUT_WORDS = {
    "fuel_per_lap_l": "fuel burn",
    "wear_scale": "tyre wear",
    "pit_loss_s": "pit loss",
    "refuel_rate_lps": "refuel rate",
    "lap_time_ms": "lap time",
}

# How a value of each input is printed, so a line never carries a bare number
# (rule 13).
def _value_words(name: str, value: float) -> str:
    if name == "fuel_per_lap_l":
        return f"{value:.2f} L/lap"
    if name == "wear_scale":
        return f"{value:.0%} of the stated wear rate"
    if name == "pit_loss_s":
        return f"{value:.1f} s"
    if name == "refuel_rate_lps":
        return f"{value:.2f} L/s"
    if name == "lap_time_ms":
        return f"{value / 1000:.2f} s a lap"
    return f"{value:.3g}"


@dataclass(frozen=True)
class Decision:
    """The part of a plan a driver acts on. Two plans with the same decision
    differ only in where the stops fall, which a flip point does not report."""
    stops: int | None
    compounds: tuple[str | None, ...] = ()
    # Not part of equality: two refusals worded differently are the same
    # decision, and must not read as a flip (critic pass 1).
    impossible: str | None = field(default=None, compare=False)

    @classmethod
    def of(cls, plans: list[Plan]) -> "Decision":
        best = plans[0]
        return cls(stops=best.stops, compounds=best.compounds)

    def words(self) -> str:
        if self.impossible is not None:
            return "no runnable plan"
        stops = ("no stop" if self.stops == 0
                 else f"{self.stops} stop" + ("" if self.stops == 1 else "s"))
        if not any(self.compounds):
            return stops
        return f"{stops} ({'-'.join(c or '?' for c in self.compounds)})"


def decide(inputs: RaceInputs) -> Decision:
    """The optimiser's first choice, or the refusal it gave."""
    try:
        return Decision.of(recommend(inputs))
    except StrategyImpossible as refusal:
        return Decision(stops=None, impossible=str(refusal))


def _scale_wear(inputs: RaceInputs, factor: float) -> RaceInputs:
    """Every wear rate in the inputs times `factor` - the event's own rate and
    each compound's, so a compound cannot escape the change by carrying its
    own figure."""
    profiles = {
        code: (replace(profile, wear_per_lap=profile.wear_per_lap * factor)
               if profile.wear_per_lap is not None else profile)
        for code, profile in inputs.compound_profiles.items()}
    return replace(
        inputs,
        wear_per_lap=(None if inputs.wear_per_lap is None
                      else inputs.wear_per_lap * factor),
        compound_profiles=profiles)


def _setter(name: str) -> Callable[[RaceInputs, float], RaceInputs]:
    if name == "wear_scale":
        return _scale_wear
    if name == "lap_time_ms":
        return lambda inputs, value: replace(inputs, lap_time_ms=int(round(value)))
    return lambda inputs, value: replace(inputs, **{name: value})


def _base_value(inputs: RaceInputs, name: str) -> float | None:
    if name == "wear_scale":
        has_wear = inputs.wear_per_lap is not None or any(
            p.wear_per_lap is not None for p in inputs.compound_profiles.values())
        return 1.0 if has_wear else None
    value = getattr(inputs, name)
    return None if value is None else float(value)


@dataclass
class Flip:
    """Where one input turns the decision, in one direction."""
    name: str
    direction: str                 # "down" | "up"
    base: float
    at: float | None               # None: no flip inside the searched band
    searched_to: float
    becomes: Decision | None = None

    @property
    def distance(self) -> float | None:
        return None if self.at is None else self.at - self.base


@dataclass
class FlipReport:
    base: Decision
    flips: list[Flip] = field(default_factory=list)
    # In a timed race: the fuel-burn flips found at each lap time tried.
    joint: list[tuple[float, list[Flip]]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def for_input(self, name: str) -> list[Flip]:
        return [flip for flip in self.flips if flip.name == name]


def _locate(inputs: RaceInputs, name: str, base: float, limit: float,
            base_decision: Decision, steps: int = SEARCH_STEPS) -> Flip:
    """Walk from the plan's figure toward `limit`; bisect the first change."""
    setter = _setter(name)
    tolerance = TOLERANCE[name]
    direction = "down" if limit < base else "up"
    previous = base
    for i in range(1, steps + 1):
        value = base + (limit - base) * i / steps
        if name != "wear_scale" and value <= 0:
            break
        got = decide(setter(inputs, value))
        if got != base_decision:
            lo, hi = previous, value        # lo keeps the base decision
            becomes = got
            while abs(hi - lo) > tolerance:
                mid = (lo + hi) / 2.0
                mid_decision = decide(setter(inputs, mid))
                if mid_decision == base_decision:
                    lo = mid
                else:
                    hi, becomes = mid, mid_decision
            return Flip(name, direction, base, at=hi, searched_to=limit,
                        becomes=becomes)
        previous = value
    return Flip(name, direction, base, at=None, searched_to=limit)


def flip_points(inputs: RaceInputs, *,
                names: tuple[str, ...] = ("fuel_per_lap_l", "wear_scale",
                                          "pit_loss_s", "refuel_rate_lps"),
                fraction: float = SEARCH_FRACTION,
                lap_time_sd_ms: float | None = None) -> FlipReport:
    """Every flip of the optimiser's first choice, one input at a time.

    An input with no figure is reported in `notes` and not searched: a flip
    around an unknown is a number with nothing under it (rule 3).
    """
    base_decision = decide(inputs)
    report = FlipReport(base=base_decision)
    for name in names:
        base = _base_value(inputs, name)
        if base is None or base == 0:
            report.notes.append(f"{INPUT_WORDS[name]}: no figure, not searched")
            continue
        for limit in (base * (1 - fraction), base * (1 + fraction)):
            report.flips.append(
                _locate(inputs, name, base, limit, base_decision))

    if inputs.is_timed and "fuel_per_lap_l" in names:
        sd = lap_time_sd_ms
        if sd is None and inputs.lap_time_sd_s:
            sd = inputs.lap_time_sd_s * 1000.0
        if sd and inputs.fuel_per_lap_l:
            for lap_ms in (inputs.lap_time_ms - 2 * sd, inputs.lap_time_ms + 2 * sd):
                at_pace = replace(inputs, lap_time_ms=int(round(lap_ms)))
                decision = decide(at_pace)
                base = inputs.fuel_per_lap_l
                report.joint.append((lap_ms, [
                    _locate(at_pace, "fuel_per_lap_l", base, limit, decision)
                    for limit in (base * (1 - fraction), base * (1 + fraction))]))
        else:
            report.notes.append(
                "timed race: lap-time spread unknown, so burn and lap time "
                "were not flipped together - the burn flip is at the plan's "
                "lap time only")
    return report


def with_saving(inputs: RaceInputs, save_l: float, laps: int,
                cost_s_per_l: float | None) -> RaceInputs | None:
    """The inputs with `save_l` litres saved over `laps` laps, spread evenly.

    **A lever the driver pulls, not a change in the car**: burn falls by the
    saving per lap and the lap slows by what that saving costs. The cost is
    the caller's to supply from a measured lever (`tools/shortshift_trade.py`,
    row 1.1's detectors); None leaves the lap time alone and every sentence
    built on it says the cost was not priced."""
    if not inputs.fuel_per_lap_l or laps <= 0:
        return inputs
    per_lap = save_l / laps
    if per_lap >= inputs.fuel_per_lap_l:
        # A saving as big as the burn is not a lever - rule 9: no clamp.
        return None
    changed = replace(inputs, fuel_per_lap_l=inputs.fuel_per_lap_l - per_lap)
    if cost_s_per_l:
        changed = replace(changed, lap_time_ms=int(round(
            inputs.lap_time_ms + per_lap * cost_s_per_l * 1000.0)))
    return changed


@dataclass
class SavingFlip:
    """How much saving removes a stop, and what it was priced at."""
    litres: float | None           # None: no stop removed inside the search
    per_lap_l: float | None
    over_laps: int
    becomes: Decision | None
    cost_s_per_l: float | None
    searched_to_l: float

    def words(self) -> str:
        if self.litres is None:
            return (f"saving up to {self.searched_to_l:.0f} L over the race "
                    f"does not remove a stop")
        cost = ("cost not priced" if not self.cost_s_per_l
                else f"at {self.cost_s_per_l:.2f} s a litre")
        return (f"saving {self.litres:.1f} L over {self.over_laps} laps "
                f"(about {self.per_lap_l:.2f} L a lap) makes it "
                f"{self.becomes.words()} - [DERIVED], {cost}")


def flip_on_saving(inputs: RaceInputs, *, max_save_l: float | None = None,
                   cost_s_per_l: float | None = None,
                   tolerance_l: float = 0.1) -> SavingFlip | None:
    """The smallest saving, spread over the plan's own distance, at which the
    optimiser takes one fewer stop. None where the plan has no stop to lose or
    no burn to save from."""
    base = decide(inputs)
    if base.stops in (None, 0) or not inputs.fuel_per_lap_l:
        return None
    try:
        laps = recommend(inputs)[0].laps_completed
    except StrategyImpossible:
        return None
    if max_save_l is None:
        max_save_l = 0.15 * (inputs.fuel_capacity_l or laps * inputs.fuel_per_lap_l)

    def fewer(save: float) -> Decision | None:
        saved = with_saving(inputs, save, laps, cost_s_per_l)
        if saved is None:
            return None
        got = decide(saved)
        if got.stops is not None and got.stops < base.stops:
            return got
        return None

    steps = max(1, int(max_save_l / 0.5))
    lo, hi, becomes = 0.0, None, None
    for i in range(1, steps + 1):
        value = max_save_l * i / steps
        got = fewer(value)
        if got is not None:
            hi, becomes = value, got
            break
        lo = value
    if hi is None:
        return SavingFlip(None, None, laps, None, cost_s_per_l, max_save_l)
    while hi - lo > tolerance_l:
        mid = (lo + hi) / 2.0
        got = fewer(mid)
        if got is not None:
            hi, becomes = mid, got
        else:
            lo = mid
    return SavingFlip(hi, hi / laps, laps, becomes, cost_s_per_l, max_save_l)


def saving_to_flip(inputs: RaceInputs, flip: Flip) -> float | None:
    """Litres a lap the driver would have to save, at the plan's own lap count,
    to cross a burn flip that lies below the plan's burn. None for any other
    flip. Derived from the flip itself, never from a second fuel sum."""
    if flip.name != "fuel_per_lap_l" or flip.at is None or flip.at >= flip.base:
        return None
    return flip.base - flip.at


def playbook_hint(inputs: RaceInputs, report: FlipReport) -> dict | None:
    """A `fuel_long -> drop_stop` entry when a lower burn removes a stop.

    Prose `when`, as every playbook entry carries: George's own fuel arithmetic
    decides whether the stop has gone; this entry is the desk's grant that he
    may say so, with the number the grant was sized on."""
    if report.base.stops in (None, 0):
        return None
    if inputs.is_timed and any(flip.at is not None
                               for _, flips in report.joint for flip in flips):
        # In a timed race the burn flip moves with the lap time; one number
        # sized at the plan's pace would be a grant on the wrong side of it at
        # another. Say nothing rather than hand George half the answer.
        return None
    for flip in report.for_input("fuel_per_lap_l"):
        if (flip.direction == "down" and flip.at is not None
                and flip.becomes is not None and flip.becomes.stops is not None
                and flip.becomes.stops < report.base.stops):
            return {
                "trigger": "fuel_long",
                "action": "drop_stop",
                "when": (f"burn holding at or under {flip.at:.2f} L/lap - the "
                         f"flip point below the plan's {flip.base:.2f} - so "
                         f"the fuel aboard reaches the flag"),
                "until": "the planned stop lap",
                "note": "[DERIVED] from strategy.flip; one input moved, the rest held",
            }
    return None


def describe(report: FlipReport, *, spread: dict[str, tuple[float, str]] | None = None
             ) -> list[str]:
    """Plain lines for Ludo's brief. `spread` maps an input to (one sigma, what
    kind of spread it is), so the reader sees how far the flip is in the units
    of that input's own uncertainty."""
    spread = spread or {}
    moves = {"down": "falls", "up": "rises"}
    lines = [f"Plan's choice: {report.base.words()}."]
    for flip in report.flips:
        word = INPUT_WORDS[flip.name]
        if flip.at is None:
            lines.append(f"  If {word} {moves[flip.direction]} as far as "
                         f"{_value_words(flip.name, flip.searched_to)}, the "
                         f"choice does not change.")
            continue
        text = (f"  If {word} {moves[flip.direction]} to "
                f"{_value_words(flip.name, flip.at)} (plan "
                f"{_value_words(flip.name, flip.base)}), the choice becomes "
                f"{flip.becomes.words()}")
        if flip.name in spread:
            sigma, kind = spread[flip.name]
            if sigma:
                text += f" - {abs(flip.distance) / sigma:.1f} sigma away on {kind}"
        lines.append(text + ".")
    for lap_ms, flips in report.joint:
        for flip in flips:
            if flip.at is not None:
                lines.append(f"  At {lap_ms / 1000:.2f} s a lap, if fuel burn "
                             f"{moves[flip.direction]} to "
                             f"{_value_words(flip.name, flip.at)}, the choice "
                             f"becomes {flip.becomes.words()}.")
    lines.append(f"  (Searched in {SEARCH_STEPS} steps across "
                 f"{SEARCH_FRACTION:.0%} either side, then bisected: a choice "
                 f"that changes and changes back inside one step is not seen.)")
    lines.extend(f"  ({note})" for note in report.notes)
    return lines
