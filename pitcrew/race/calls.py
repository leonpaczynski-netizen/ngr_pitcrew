"""What the engineer says, and when.

CLAUDE.md §5.5 is the spec, and it is unusually strict about form because the
driver hears this under a helmet at racing speed:

    "Box this lap or next. Fuel is the constraint - you're 1.2 laps short."

One thing at a time. The instruction first, the reason second and short. Not a
table, not three options. If the app is not confident it says so **inside the
call**, because "unconfirmed" is a word the driver can act on.

So this module returns **at most one call per lap** — the most urgent thing
true right now. A second call would arrive while he is still processing the
first, and two instructions at once is the same as none.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# Confidence travels with every call so a guess never sounds like a reading.
HIGH = "high"
MEDIUM = "medium"
LOW = "low"

# Kinds, ordered by urgency. The first match wins the lap.
BOX_NOW = "box-now"
BOX_SOON = "box-soon"
FUEL_SHORT = "fuel-short"
FUEL_LONG = "fuel-long"
TYRE = "tyre"
STATUS = "status"
GREEN = "green"
CHEQUER = "chequer"

URGENCY = (BOX_NOW, FUEL_SHORT, BOX_SOON, TYRE, FUEL_LONG, GREEN, CHEQUER,
           STATUS)

# A status call every few laps, so silence means "nothing to report" rather
# than "the app has died".
STATUS_EVERY_LAPS = 5

# Fuel margin below which the plan no longer reaches the stop.
FUEL_SHORT_LAPS = 0.5
# Fuel surplus above which he is carrying a lap he does not need.
FUEL_LONG_LAPS = 1.5


@dataclass(frozen=True)
class Call:
    """One thing said, with why and how sure."""
    kind: str
    lap: int
    call: str
    reason: str
    confidence: str = HIGH

    def spoken(self) -> str:
        """Instruction, then reason. Confidence only when it is not high."""
        text = self.call
        if self.reason:
            text = f"{text} {self.reason}"
        if self.confidence == LOW:
            text = f"{text} Unconfirmed."
        return text

    def as_export(self) -> dict:
        return {
            "lap": self.lap,
            "call": self.call,
            "reason": self.reason,
            "confidence": self.confidence,
        }


@dataclass
class RaceState:
    """What is true right now, as far as the app can tell."""
    lap: int = 0                       # laps completed
    laps_total: int | None = None
    fuel_l: float | None = None
    fuel_per_lap_l: float | None = None
    # What the tank actually holds. Without it the engineer will ask for a
    # fuel figure the car cannot take - and it did: "Fuel to 510 litres."
    fuel_capacity_l: float | None = None
    position: int | None = None
    in_pit: bool = False
    finished: bool = False
    # Stint accounting against the approved plan.
    stint_index: int = 0
    stint_ends_on_lap: int | None = None
    next_compound: str | None = None
    wear_per_lap: float | None = None
    laps_since_stop: int = 0
    said: list[str] = field(default_factory=list)

    def laps_remaining(self) -> int | None:
        if self.laps_total is None:
            return None
        return max(0, self.laps_total - self.lap)

    def laps_of_fuel(self) -> float | None:
        """How many more laps the fuel on board covers."""
        if self.fuel_l is None or not self.fuel_per_lap_l:
            return None
        return self.fuel_l / self.fuel_per_lap_l

    def laps_to_stop(self) -> int | None:
        if self.stint_ends_on_lap is None:
            return None
        return self.stint_ends_on_lap - self.lap


def _fuel_gap(state: RaceState) -> float | None:
    """Laps of fuel minus laps still to run before the stop.

    Negative means short. This is the number the driver acts on, so it is
    computed once and reused rather than re-derived per call.
    """
    onboard = state.laps_of_fuel()
    if onboard is None:
        return None
    target = state.laps_to_stop()
    if target is None:
        target = state.laps_remaining()
    if target is None:
        return None
    return onboard - target


def next_call(state: RaceState) -> Call | None:
    """The single most urgent thing true this lap, or nothing.

    Silence is a valid answer and the common one. A call repeated every lap
    stops being information, so anything already said this stint is suppressed
    unless it has become more urgent.
    """
    candidates = [c for c in _candidates(state) if c is not None]
    if not candidates:
        return None
    candidates.sort(key=lambda c: URGENCY.index(c.kind))
    for call in candidates:
        if call.kind not in state.said:
            return call
    return None


def _candidates(state: RaceState) -> list[Call | None]:
    return [
        _chequer(state),
        _green(state),
        _box_now(state),
        _box_soon(state),
        _fuel(state),
        _tyre(state),
        _status(state),
    ]


def _green(state: RaceState) -> Call | None:
    if state.lap != 0 or state.finished:
        return None
    laps = f"{state.laps_total} laps." if state.laps_total else ""
    return Call(GREEN, 0, "Green, green, green.", laps)


def _chequer(state: RaceState) -> Call | None:
    if not state.finished:
        return None
    where = f"P{state.position}." if state.position else ""
    return Call(CHEQUER, state.lap, "Chequered flag.", where)


def _box_now(state: RaceState) -> Call | None:
    to_stop = state.laps_to_stop()
    if to_stop is None or state.in_pit or state.finished:
        return None
    if to_stop > 0:
        return None

    fuel = _fuel_instruction(state)
    compound = f" {state.next_compound}." if state.next_compound else ""
    return Call(
        BOX_NOW, state.lap,
        f"Box this lap.{compound}",
        fuel or "On the plan.",
    )


def _box_soon(state: RaceState) -> Call | None:
    to_stop = state.laps_to_stop()
    if to_stop is None or state.in_pit or state.finished:
        return None
    if not 1 <= to_stop <= 2:
        return None
    return Call(
        BOX_SOON, state.lap,
        f"Box in {to_stop}." if to_stop > 1 else "Box next lap.",
        f"Stop {state.stint_index + 1}, on the plan.",
    )


def _fuel_instruction(state: RaceState) -> str:
    """How much to take, in litres, to the diamond plus a lap.

    Clamped to the tank, because an instruction the car cannot execute is
    worse than no instruction: the driver acts on it, finds the fill stops
    short, and has to work out the shortfall himself at pit-exit speed. When
    the clamp binds, the shortfall is the call - "fill it and you are still
    two laps short" is something he can plan around; "fuel to 510 litres" is
    not.
    """
    if not state.fuel_per_lap_l or state.laps_remaining() is None:
        return ""
    after_stop = state.laps_remaining()
    if state.stint_ends_on_lap is not None:
        after_stop = (state.laps_total or 0) - state.stint_ends_on_lap
    litres = (after_stop + 1) * state.fuel_per_lap_l

    capacity = state.fuel_capacity_l
    if capacity and litres > capacity:
        short = (litres - capacity) / state.fuel_per_lap_l
        return f"Fuel to full. Still {short:.1f} laps short."
    return f"Fuel to {litres:.0f} litres."


def _fuel(state: RaceState) -> Call | None:
    gap = _fuel_gap(state)
    if gap is None or state.in_pit or state.finished:
        return None

    confidence = MEDIUM if state.lap < 3 else HIGH
    if gap < -FUEL_SHORT_LAPS:
        return Call(
            FUEL_SHORT, state.lap,
            "Map 3 down the straights.",
            f"You're {abs(gap):.1f} laps short on fuel.",
            confidence)
    if gap > FUEL_LONG_LAPS and _past_half_stint(state):
        # Only worth saying once the stint is half run. At the start of a
        # stint there is always surplus - the tank was just filled - and
        # "you can push" on lap one is noise the driver learns to ignore.
        return Call(
            FUEL_LONG, state.lap,
            "You can push.",
            f"{gap:.1f} laps of fuel in hand.",
            confidence)
    return None


def _past_half_stint(state: RaceState) -> bool:
    to_stop = state.laps_to_stop()
    if to_stop is None:
        remaining = state.laps_remaining()
        if remaining is None or state.laps_total is None:
            return True
        return state.lap >= state.laps_total / 2
    return state.laps_since_stop >= to_stop


def _tyre(state: RaceState) -> Call | None:
    """Only ever a warning, never a lap time.

    Wear is modelled, never measured, so this call carries low confidence by
    construction - and says so out loud.
    """
    if state.wear_per_lap is None or state.in_pit or state.finished:
        return None
    consumed = state.laps_since_stop * state.wear_per_lap
    if consumed < 0.85:
        return None
    return Call(
        TYRE, state.lap,
        "Tyres are at the end of their window.",
        f"Modelled at {consumed:.0%}.",
        LOW)


def _status(state: RaceState) -> Call | None:
    """Proactive reassurance, rarely. Silence should mean nothing to report."""
    if state.lap < 1 or state.finished or state.in_pit:
        return None
    if state.lap % STATUS_EVERY_LAPS != 0:
        return None
    remaining = state.laps_remaining()
    where = f"P{state.position}." if state.position else ""
    left = f"{remaining} to go." if remaining is not None else ""
    return Call(STATUS, state.lap, f"{where} {left}".strip(), "")


def clear_stint(state: RaceState) -> None:
    """A stop resets what has been said, so the next stint speaks freshly."""
    state.said = [kind for kind in state.said if kind in (GREEN,)]
    state.laps_since_stop = 0
