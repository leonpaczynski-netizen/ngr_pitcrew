"""How a rival races, learned across races from what the screen showed.

`roster.py` says which row is which driver. `rivals.py` says what one stop was
worth. This is what accumulates: a driver seen over several races has a fuel
consumption, a habit about when he stops, and a habit about how much he takes,
and all three change what we should do about him.

### What is actually measurable, and what only looks like it is

**Burn per lap is measurable.** A car that has run `n` laps and comes into the
pits showing `f` litres has used `start - f` litres to get there, and the entry
figure is on screen the moment he crosses the line into the lane. That is a
real per-rival number, comparable directly against ours, which we know exactly
from telemetry.

It rests on one assumption and it is stated in the record rather than hidden:
**what he started with.** GT7 lets a car start on less than a full tank, and
nothing on screen says whether it did. `assumed_start_l` carries that, so a
profile built on a wrong assumption can be found later rather than believed.

**Burn is not a virtue, and this module never calls it one.** It is fuel map,
driving style, car and tune together. A rival burning less than us may be
lifting, may be short-shifting, may be in a more efficient car, or may be a
map leaner than ours costing him lap time. The number is worth knowing because
it says what his stop will cost him; it says nothing about whether he is good.

**When he stops is measurable. Why he stopped is not.** A lap number against
the field's is a fact. Calling it an undercut is a reading of intent, and a car
that stopped early because he was short of fuel looks identical to one that
stopped early to jump somebody. So `stops_earlier_than` reports the fact and the
sample it came from and stops there.

**How much he takes is measurable, and it is the most useful of the three.**
A car that leaves with more than the remaining laps cost is carrying weight it
does not need and standing still to load it. Measured against this driver's own
policy - fill to the flag and carry nothing - it says whether a rival is giving
away seconds in the lane or on the road.

### The field is truncated, and it hides stops non-randomly

**GT7 draws only the top of the order** - eight rows on every clean frame of
the measured race - so a driver outside it is not on screen and cannot be read.
That is the game's limit and there is nothing to do about it.

What matters is that it does not hide stops at random. **A car drops places
while it stands in the pit lane, and standing in the pit lane is the only time
its columns are drawn.** So a driver running near the cut goes below it exactly
when he becomes worth reading. Measured across the Spa race, K.Graebs was on
the board for the first twenty minutes and the last ten, and absent through the
window in which every other car stopped - which is why he is the one driver of
eight with no stop on file.

The bias runs one way: stops by cars near the front are captured, stops by cars
near the cut are missed. A profile assembled from screen reads is therefore
better evidence about the leaders than about the midfield, and `stops_seen` is
the honest guard - a driver with none may simply never have been visible while
it counted. Do not read an empty profile as a driver who does not stop.

### One data point per stop

There is no continuous rival telemetry here. A twenty-lap race with one stop
each yields exactly one observation per driver, so every figure carries its
sample count and a profile from one race says so. CLAUDE.md rule 4.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from pitcrew.race.rivals import Stop

# A full GT7 tank, and the default assumption about what a car started on.
# Every tank in the game is 100 L, so litres and percent are the same number.
FULL_TANK_L = 100.0

# Below this many observed stops, a habit is not a habit. One stop is a fact
# about one race; it is reported as such and never as a tendency.
MIN_STOPS_FOR_HABIT = 3

# Litres of slack either side of "filled to exactly what he needs" before the
# fill is called long or short. A driver aiming at the in-game diamond lands
# within about this much of it.
FILL_SLACK_L = 4.0

# How much lower a rival's burn has to be than ours before it is worth saying.
# Below this the difference is inside what one stop's reading error can produce:
# the fuel figure is an integer and the lap count is exact, so a 20-lap read is
# good to about 0.05 L/lap, but which lap he actually entered on is not always
# certain to better than one.
BURN_DIFFERENCE_L = 0.4


@dataclass(frozen=True)
class Observation:
    """One stop by one driver in one race, as it was seen.

    `assumed_start_l` is the load he is taken to have begun the race on. It is
    an assumption, it is stored with the observation rather than applied and
    forgotten, and it is the one thing here that could make every burn figure
    wrong at once.
    """
    driver: str
    race: str
    lap: int
    laps_total: int | None = None
    fuel_in_l: float | None = None
    fuel_out_l: float | None = None
    compound: str | None = None
    assumed_start_l: float = FULL_TANK_L
    # Which league, and which car he was in. Both nullable: every observation
    # already on file predates them.
    series: str | None = None
    car: str | None = None

    @property
    def stop(self) -> Stop:
        return Stop(lap=self.lap, fuel_in_l=self.fuel_in_l,
                    fuel_out_l=self.fuel_out_l, compound=self.compound)

    @property
    def burn_per_lap_l(self) -> float | None:
        """Litres a lap over the stint just ended, or `None`.

        `None` rather than a number wherever the arithmetic cannot mean what it
        says: no entry reading, no laps run, or a tank that came in fuller than
        it started, which is a misread and not a car that made fuel.
        """
        if self.fuel_in_l is None or self.lap is None or self.lap <= 0:
            return None
        used = self.assumed_start_l - self.fuel_in_l
        if used <= 0:
            return None
        return used / self.lap

    def fill_surplus_l(self, burn_per_lap_l: float | None) -> float | None:
        """Litres he left with beyond what the remaining laps cost.

        Positive is fuel he is carrying and did not need; negative means he
        must stop again. `None` where either end of it was not seen - and an
        unread exit figure is not an empty tank.
        """
        if (self.fuel_out_l is None or self.laps_total is None
                or self.lap is None or not burn_per_lap_l
                or burn_per_lap_l <= 0):
            return None
        remaining = self.laps_total - self.lap
        if remaining < 0:
            return None
        return self.fuel_out_l - remaining * burn_per_lap_l


@dataclass
class Profile:
    """What is known about one driver, across every race he has been seen in.

    Everything is `None` until it has been seen. A driver with no observations
    is a driver nobody has watched, not a driver with no habits.
    """
    driver: str
    observations: list[Observation] = field(default_factory=list)

    def add(self, observation: Observation) -> None:
        self.observations.append(observation)

    # --- derived. CLAUDE.md rule 5: none of this is measured. --------------

    @property
    def stops_seen(self) -> int:
        return len(self.observations)

    @property
    def races_seen(self) -> int:
        return len({o.race for o in self.observations})

    def burn_per_lap_l(self, car: str | None = None
                       ) -> tuple[float | None, int]:
        """Mean litres a lap, and the number of stops behind it.

        **Scoped to one car when one is given, and it usually should be.**
        Litres a lap is a property of the CAR, not of the driver: a Gr.3 burn
        and a Gr.4 burn are different quantities, and their mean describes
        neither race. He races several leagues at once, so pooling here would
        quietly average across them.

        The count is half the answer and travels with it - one stop is one
        stint's worth of evidence about a driver who may have been saving.
        """
        wanted = [o for o in self.observations
                  if car is None or o.car == car]
        seen = [o.burn_per_lap_l for o in wanted]
        seen = [b for b in seen if b is not None]
        if not seen:
            return None, 0
        return sum(seen) / len(seen), len(seen)

    def fill_surplus_l(self, car: str | None = None
                       ) -> tuple[float | None, int]:
        """Mean litres carried beyond the flag, and the stops behind it.

        **Pooled across series**, because whether a driver fuels to the flag or
        carries a spare lap is a habit of his rather than a property of the
        car. The burn it is measured against is still the car's, so that is
        scoped even when this is not.
        """
        burn, _ = self.burn_per_lap_l(car)
        seen = [o.fill_surplus_l(burn) for o in self.observations]
        seen = [s for s in seen if s is not None]
        if not seen:
            return None, 0
        return sum(seen) / len(seen), len(seen)

    def stop_fraction(self) -> tuple[float | None, int]:
        """How far into the race he stops, as a fraction of its length.

        A fraction rather than a lap so that races of different lengths can be
        pooled at all - a stop on lap 11 means something quite different in a
        20-lap race and a 40-lap one.

        **Pooled across every series he has been watched in.** When a driver
        stops is a habit of the driver; it is also the figure that most needs
        the samples, because a stop is one observation a race and three is the
        floor for calling anything a habit.
        """
        seen = [o.lap / o.laps_total for o in self.observations
                if o.lap is not None and o.laps_total]
        if not seen:
            return None, 0
        return sum(seen) / len(seen), len(seen)

    def compounds(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for observation in self.observations:
            if observation.compound:
                out[observation.compound] = out.get(observation.compound, 0) + 1
        return out


def stops_earlier_than(profile: Profile, field_fraction: float | None
                       ) -> tuple[float | None, int]:
    """How much earlier into a race he stops than the field, as a fraction.

    Positive is earlier. **This is the fact and not the intent.** A car that
    stopped early to jump somebody and a car that stopped early because it was
    short of fuel look exactly the same from outside, so nothing here calls it
    an undercut - that word claims to know why, and the screen cannot say.
    """
    mine, count = profile.stop_fraction()
    if mine is None or field_fraction is None:
        return None, count
    return field_fraction - mine, count


def field_stop_fraction(profiles: list[Profile]) -> float | None:
    """Where the field as a whole stops, for one driver to be read against."""
    seen = []
    for profile in profiles:
        fraction, count = profile.stop_fraction()
        if fraction is not None and count:
            seen.append(fraction)
    return sum(seen) / len(seen) if seen else None


def field_without(profiles: list[Profile], driver: str) -> float | None:
    """Where the field stops, EXCLUDING the driver being judged against it.

    Including him shrinks his own deviation by 1/n, so in a field of eight a
    genuine 8% early stopper reads as 7%. The comparison is meant to be against
    the others.
    """
    return field_stop_fraction([p for p in profiles if p.driver != driver])


def burn_against(profile: Profile, ours_l: float | None,
                 car: str | None = None) -> tuple[float | None, int]:
    """Litres a lap he uses more than us. Negative means he uses less.

    Scoped to the car, because ours is the car's number too and comparing two
    different cars' burn says nothing about either driver.
    """
    theirs, count = profile.burn_per_lap_l(car)
    if theirs is None or ours_l is None:
        return None, count
    return theirs - ours_l, count


def describe(profile: Profile, *, ours_burn_l: float | None = None,
             field_fraction: float | None = None,
             refuel_rate_lps: float | None = None,
             car: str | None = None) -> list[str]:
    """What is known about this driver, in plain sentences, or nothing.

    Sentences only where the evidence carries them. A profile from a single
    stop says "one stop" out loud rather than presenting itself as a habit,
    because the difference between one observation and five is the whole
    difference between a fact and a tendency.
    """
    lines: list[str] = []
    if not profile.observations:
        return lines
    races = profile.races_seen
    span = ("%d stop%s over %d race%s"
            % (profile.stops_seen, "" if profile.stops_seen == 1 else "s",
               races, "" if races == 1 else "s"))

    burn, burn_n = profile.burn_per_lap_l(car)
    if burn is not None:
        line = "%s burns about %.1f L a lap (%s)." % (profile.driver, burn, span)
        difference, _ = burn_against(profile, ours_burn_l, car)
        if difference is not None and abs(difference) >= BURN_DIFFERENCE_L:
            line += (" That is %.1f L a lap %s than you."
                     % (abs(difference), "more" if difference > 0 else "less"))
        lines.append(line)

    surplus, surplus_n = profile.fill_surplus_l(car)
    if surplus is not None and surplus_n:
        if surplus > FILL_SLACK_L:
            # **Litres are not seconds until a measured rate says so.** This
            # printed the same number twice, which silently asserts 1.0 L/s -
            # true on this driver's archive and nowhere stated in the sentence.
            # Without a rate it says litres and stops. CLAUDE.md rule 5.
            if refuel_rate_lps and refuel_rate_lps > 0:
                lines.append(
                    "He leaves with about %.0f L more than he needs, so he "
                    "stands %.0f seconds longer than he has to."
                    % (surplus, surplus / refuel_rate_lps))
            else:
                lines.append("He leaves with about %.0f L more than he needs "
                             "and stands there loading it." % surplus)
        elif surplus < -FILL_SLACK_L:
            lines.append("He leaves short of the flag by about %.0f L, so he "
                         "is planning another stop." % (-surplus))
        else:
            lines.append("He fuels to the flag and carries nothing spare, "
                         "same as you.")

    earlier, count = stops_earlier_than(profile, field_fraction)
    if earlier is not None and count >= MIN_STOPS_FOR_HABIT:
        if abs(earlier) >= 0.05:
            lines.append("He stops about %.0f%% of the race %s than the field."
                         % (abs(earlier) * 100,
                            "earlier" if earlier > 0 else "later"))
    elif earlier is not None:
        lines.append("Too few stops to call his timing a habit (%s)." % span)

    compounds = profile.compounds()
    if len(compounds) == 1:
        only = next(iter(compounds))
        lines.append("Every stop seen was on %s." % only)
    return lines
