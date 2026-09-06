"""Wear rates fitted from what the gauge actually read, per compound.

**The highest-value number in the app, and it has never survived a race.**
GT7 broadcasts no tyre wear channel, so wear is modelled - and the model was
measured at roughly 21% low against the replay reader, which is verified to
0.5% against the game's own gauge. A 21% error sits underneath every stint
length raced so far.

The reader already exists (`tools/read_hud_wear.py`, `telemetry/hud.py`) and
already writes `laps.wear_*`. What was missing is the step after: **turn a
race's readings into a rate, and carry the rate into the next race.** Without
it every race re-derives wear from nothing, and in VR it mostly cannot -
the HUD is drawn on the car's dashboard in 3D, so the gauge reads about 6
crossings in 22 and a live fit needs three inside one stint.

### The fit

Least squares of the worst corner against lap number, **within a stint**, per
compound. Stints, not races: a fresh set resets the gauge to zero, so a slope
across a stop is a line through two unrelated segments and comes out shallow.

Refused rather than reported where:

* fewer than `MIN_READINGS` readings stand behind it - two points and a
  quantum of noise is a rate of anything you like;
* the gauge has not moved by `MIN_SPAN` across them - one pixel of the bar is
  3.3% of tyre life, so a span under two quanta is indistinguishable from a
  bar crossing a pixel boundary;
* the slope comes out flat or negative. A tyre that is not wearing is a
  reading problem, not a finding, and `max(x, 0.0)` on it would be CLAUDE.md
  rule 9 exactly.

### It is declared, not measured, by the time it is used

The transcription is a measurement - it is the game's own readout. The *rate*
is a fit over it, and it reaches the next race through `race_knowledge`, which
reports everything it holds as declared. Both statements are true at once and
the export says which is which.
"""
from __future__ import annotations

from dataclasses import dataclass

# Restated from `race/calls.py` rather than imported, and asserted equal to it
# in the tests: the offline fit and the live one answer the same question about
# the same gauge, and two numbers that must agree and cannot see each other is
# how they come to disagree.
MIN_READINGS = 3
MIN_SPAN = 0.067

# A rate this large is not a tyre, it is a misread bar - a full set consumed in
# under four laps. Refused rather than clamped: the reading's reference is
# wrong and saying so is the honest answer (CLAUDE.md rule 9).
MAX_PLAUSIBLE_PER_LAP = 0.25


@dataclass(frozen=True)
class Fit:
    """One compound's wear rate, with everything needed to judge it."""
    compound: str
    per_lap: float
    stints: int
    readings: int
    span: float

    def as_record(self) -> dict:
        """The shape `race_knowledge.wear_rates_json` holds."""
        return {"perLap": round(self.per_lap, 5),
                "samples": self.stints,
                "readings": self.readings,
                "source": "hud-gauge, replay"}


def worst_corner(lap) -> float | None:
    """The most worn corner of this lap, or None where nothing was read.

    **All four or none.** A lap where only two bars read is not a lap where
    the other two were fine; it is a lap the reader could not see, and taking
    the max of what it did see would report the worst of a subset as the worst
    of the set.
    """
    corners = [getattr(lap, name, None) for name in
               ("wear_fl", "wear_fr", "wear_rl", "wear_rr")]
    if any(corner is None for corner in corners):
        return None
    return max(corners)


def fit_stint(laps) -> tuple[float | None, int, float]:
    """(rate per lap, readings used, span covered) for one stint's laps.

    `None` with its reasons intact rather than a number: the caller reports
    how many readings and how much span there were, so a refusal can be told
    from an absence.
    """
    points = []
    for lap in laps:
        worn = worst_corner(lap)
        if worn is not None:
            points.append((lap.lap_num, worn))
    if len(points) < MIN_READINGS:
        return None, len(points), 0.0
    span = points[-1][1] - points[0][1]
    if span < MIN_SPAN:
        return None, len(points), span

    n = len(points)
    mean_lap = sum(lap for lap, _ in points) / n
    mean_worn = sum(worn for _, worn in points) / n
    denominator = sum((lap - mean_lap) ** 2 for lap, _ in points)
    if denominator <= 0:                                     # pragma: no cover
        return None, n, span
    slope = sum((lap - mean_lap) * (worn - mean_worn)
                for lap, worn in points) / denominator
    if slope <= 0 or slope > MAX_PLAUSIBLE_PER_LAP:
        # Flat, backwards, or a full set in under four laps. Every one of
        # those is the reading's reference being wrong rather than the tyre
        # doing something, and clamping would turn "I cannot tell you" into a
        # confident, well-formed, wrong answer.
        return None, n, span
    return slope, n, span


def fit(laps) -> dict[str, Fit]:
    """Every compound's rate, fitted stint by stint over one race's laps.

    **Stints, not races.** A fresh set resets the gauge to zero, so a slope
    taken across a stop is a line through two unrelated segments and comes out
    shallow - which is the direction that overruns the cliff.

    Where a compound has more than one usable stint the rates are averaged and
    the stint count carried, because a rate from one stint and one from six
    are not the same claim.
    """
    found: dict[str, list[tuple[float, int, float]]] = {}
    for compound, stint in _stints(laps):
        rate, readings, span = fit_stint(stint)
        if rate is not None:
            found.setdefault(compound, []).append((rate, readings, span))

    out = {}
    for compound, fits in found.items():
        out[compound] = Fit(
            compound=compound,
            per_lap=sum(rate for rate, _, _ in fits) / len(fits),
            stints=len(fits),
            readings=sum(readings for _, readings, _ in fits),
            span=max(span for _, _, span in fits))
    return out


def carry_into_knowledge(store, event_id: int, *, kind: str = "race",
                         author: str = "replay wear pass") -> dict:
    """Fit this event's rates and write them into the circuit's briefing.

    **The step that makes the whole thing worth doing.** The reader has
    transcribed the gauge since 26 Aug and the numbers went into `laps.wear_*`
    and stopped there - so every race still started with a modelled rate that
    was measured at ~21% low, on a channel that reads 6 crossings in 22 in VR.

    Written against the circuit rather than the event (`event_id=None`), so the
    next round at the same track inherits it. Rates for compounds this race
    did not run are left alone: a race on RS says nothing about RH, and
    replacing the whole map would delete a rate nobody re-measured.

    Returns what was written, keyed by compound.
    """
    from pitcrew.analysis.resolve import circuit_key
    from pitcrew.export.build import event_lap_inputs
    from pitcrew.race.knowledge import Knowledge

    event = store.get_event(event_id)
    if event is None or not event.get("track"):
        return {}
    fits = fit(event_lap_inputs(store, event_id, kind, hydrate=set()))
    if not fits:
        return {}

    key = circuit_key(event["track"], event.get("layout"))
    existing = store.get_race_knowledge(key, None)
    rates = dict(existing.wear_rates) if existing else {}
    # **Stamped with the multiplier it was measured at.** A rate is a claim
    # about one multiplier; `Knowledge.wear_per_lap` refuses it for another.
    multiplier = event.get("tyre_wear_mult")
    rates.update({compound: {**got.as_record(), "multiplier": multiplier}
                  for compound, got in fits.items()})

    base = existing or Knowledge(circuit_key=key)
    store.save_race_knowledge(_with_rates(base, rates, author))
    return {compound: got.as_record() for compound, got in fits.items()}


def _with_rates(base, rates: dict, author: str):
    """`base` with new wear rates and its own provenance restamped.

    A `replace` rather than a fresh record, so the pit loss, the tow and
    everything else Ludo wrote by hand survive a wear pass. The author moves,
    because the last hand that touched the record is the one that should be on
    it.
    """
    from dataclasses import replace

    from pitcrew.store.db import _now

    return replace(base, wear_rates=rates, author=author, written_at=_now())


def _stints(laps):
    """(compound, laps) for each run on one set, in order.

    A stint ends at a pit lap or at a compound change. Out-laps start the next
    one; the pit lap itself belongs to neither, because the gauge on it is
    read partly on the old set and partly on the new.
    """
    current, compound = [], None
    for lap in laps:
        code = (getattr(lap, "compound", None) or "").upper() or None
        if getattr(lap, "is_pit_lap", False) or (
                compound is not None and code != compound):
            if compound and len(current) >= MIN_READINGS:
                yield compound, current
            current, compound = [], code
            if getattr(lap, "is_pit_lap", False):
                continue
        compound = compound or code
        if compound:
            current.append(lap)
    if compound and len(current) >= MIN_READINGS:
        yield compound, current
