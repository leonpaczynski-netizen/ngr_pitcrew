"""What the engineer can see this race, said once before the green.

**Silence is the app's most-used output and it has never meant one thing.** It
can mean nothing is wrong; or that there is no plan; or that no wear evidence
exists; or that the lap count cannot be resolved; or that the packet format in
use carries no surface channel at all. The driver cannot tell those apart, and
`_status` promises him that silence means nothing to report - so he either
over-trusts it or stops listening.

A real race engineer opens by declaring the instrument. This does the same: the
shape of the race, what the engineer can see, and what he cannot. Once, at
arming, on the grid, where nothing competes for the channel.

### Two corrections that came out of review

**The lap count of a timed race is not knowable at arming.** `laps_estimate_firm`
is computed from a clock margin against a lap-time spread that does not exist
until several clean laps have been run. Promising a lap count on the grid and
withdrawing it later is worse than never promising it, so a timed race is
declared as a clock and the count is promised only when it can be stood behind.

**The tyre instrument can be lost mid-race.** The live sampler stands down for
good after repeated failures. A brief that says "I have the tyre gauge" and then
goes quiet has told him something that stopped being true, so the stand-down
gets its own single line - `lost_the_gauge()` - and the brief promises only
what is true when it is spoken.

Nothing here is derived from telemetry. It is all app state, known before a
wheel turns.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Instruments:
    """What is switched on and working, as the race is armed."""

    #: A certified, approved plan is loaded.
    has_plan: bool = False
    #: Lap count for a lap race; None for a timed race.
    race_laps: int | None = None
    race_minutes: float | None = None
    # The plan's estimate of a timed race's distance, said as one. None
    # where no plan carries one.
    laps_estimate: int | None = None
    #: Stops the plan makes, and the compounds in order, where it has them.
    stops: int | None = None
    compounds: tuple[str, ...] = ()
    #: How many of those stops are fuel only (`tyres: false`).
    fuel_only_stops: int = 0
    #: The live wear reader is on, connected, and has not stood down.
    wear_gauge: bool = False
    #: A measured temperature window exists for this event.
    temp_window: bool = False
    #: The packet format in use carries the per-wheel surface channel.
    surface_channel: bool = True
    #: Whether the pit wall will watch the leaderboard this race. `None` where
    #: the app cannot say, which is treated as "it will not" - promising less
    #: than is there is the safe direction for a brief.
    sees_rivals: bool | None = None


# **One sentence, said from two places.** The brief says it on the grid
# where the wall will not watch; `controller.start_race` says it late where
# the wall was going to watch and then failed to start, after this line has
# already been dropped. Two wordings would be two clips and two claims.
NO_RIVALS = "I can't see other cars - position only."
# Said by `controller.start_race` where the wall was going to watch and then
# failed to start. Here rather than in the controller because this is where
# the sentence's family lives - and because the opener test that keeps the
# voice pack honest scans this file and not the controller.
WALL_DID_NOT_START = "The pit wall did not start."


def _compound_phrase(compounds: tuple[str, ...]) -> str:
    """", RH onto RS" - or ", on RH" when every stint is the same set.

    A four-stop plan on one compound produced "RM onto RM onto RM onto RM",
    which is four facts where there is one. Consecutive repeats collapse:
    what the driver needs is the sequence of *changes*, and a stop that puts
    the same compound back is not one.
    """
    if not compounds:
        return ""
    ordered: list[str] = []
    for compound in compounds:
        if not ordered or ordered[-1] != compound:
            ordered.append(compound)
    if len(ordered) == 1:
        return f", on {ordered[0]}"
    return ", " + " onto ".join(ordered)


def _tyres_line(instruments: Instruments) -> str | None:
    """Whether the stops take tyres, where any of them does not.

    **The brief never said "fuel only"** (the critic on row 2.6, pass 2):
    "20 laps, 1 stop, on RS." on the grid, then "Box this lap. No tyres." at
    the stop. Fixed sentences, so every one is a clip; which stop is said at
    the box, where the box call already names it.
    """
    stops, fuel_only = instruments.stops or 0, instruments.fuel_only_stops
    if not stops or not fuel_only:
        return None
    if fuel_only < stops:
        return "Not every stop takes tyres - I'll say which at the box."
    if stops == 1:
        return "No tyres at the stop - fuel only."
    return "No tyres at any stop - fuel only."


def brief(instruments: Instruments) -> list[str]:
    """The lines to speak, in order. Never empty.

    Short sentences, one fact each, in the register of `CLAUDE.md` §5.5 - and
    the last one is always about what cannot be seen, because that is the half
    the driver has no other way to learn.
    """
    lines: list[str] = []

    # --- the shape of the race
    if instruments.race_laps:
        shape = f"{instruments.race_laps} laps"
        if instruments.stops is not None:
            shape += (", no stop" if instruments.stops == 0
                      else f", {instruments.stops} stop"
                           f"{'' if instruments.stops == 1 else 's'}")
        shape += _compound_phrase(instruments.compounds)
        lines.append(shape + ".")
        tyres = _tyres_line(instruments)
        if tyres:
            lines.append(tyres)
    elif instruments.race_minutes:
        # **A clock, not a distance.** The lap count of a timed race follows
        # from the pace and cannot be stood behind on the grid.
        shape = f"{instruments.race_minutes:g} minutes"
        if instruments.stops is not None:
            shape += (", no stop" if instruments.stops == 0
                      else f", {instruments.stops} stop"
                           f"{'' if instruments.stops == 1 else 's'}")
        lines.append(shape + " - this one runs to the clock.")
        tyres = _tyres_line(instruments)
        if tyres:
            lines.append(tyres)
        if instruments.laps_estimate:
            # The same estimate the green will say, said the same way; the
            # brief used to promise no count and the green then gave one.
            lines.append(f"About {instruments.laps_estimate} laps on the "
                         f"clock - I'll firm it up as we go.")
        else:
            lines.append("I won't give you a lap count until I can stand "
                         "behind one.")
    elif not instruments.has_plan:
        lines.append("No plan loaded - I'll call fuel and nothing else.")

    # --- what the engineer can see
    if instruments.wear_gauge:
        lines.append("I have the tyre gauge this race.")
    else:
        lines.append("No tyre gauge this race - read it to me when you can.")
        lines.append("If I'm quiet about tyres it means I can't see them, "
                     "not that they're fine.")

    if not instruments.temp_window:
        lines.append("No measured temperature window on this car, so I'll "
                     "call the trend and not a number.")

    if not instruments.surface_channel:
        # The `A` format carries no per-wheel surface, so nothing can see an
        # off or a kerb. Worth one line because it silences a whole family.
        lines.append("I can't see kerbs or offs on this stream.")

    # --- and what he cannot, always last
    #
    # **Unconditional, while the wall was watching** (row 1.10). With the
    # gauge on and a sampling interval inside five seconds the wall reads the
    # leaderboard all race, and the engineer then volunteers "Boxhead has
    # boxed on 40 litres", "He is 8 seconds back", "Faster than Boxhead
    # through 1 and 2" - having opened the race by promising none of it. This
    # file's own rule, one line up, is that promising an instrument that is
    # not there is worse than promising nothing; this was the same failure
    # running backwards.
    if not instruments.sees_rivals:
        lines.append(NO_RIVALS)
    return lines


def lost_the_gauge() -> str:
    """One line, when the wear reader stands down mid-race.

    The brief promised an instrument. Losing it silently would leave him
    reading the same silence as "tyres are fine", which is the exact confusion
    the brief exists to remove.
    """
    return ("I've lost the tyre gauge. Read it to me when you get a straight.")
