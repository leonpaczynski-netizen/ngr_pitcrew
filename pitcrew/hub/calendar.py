"""The league calendar, translated into the app's own vocabulary.

`read.py` speaks the hub's language: `RACING_SOFT`, `GRID_FALSE_START`,
`"Daytona International Speedway - Road Course"` as one string with an em dash.
The event row speaks the app's: `RS`, `"Grid - no track limit"`, a track and a
layout in two columns. **This module is the only place the two meet**, so that
a change to either vocabulary has one place to be made.

### Why the hub is the better source

The event row is typed by hand once a round and has been wrong repeatedly - the
Daytona round is declared by the league as a mandatory one-stop and the stored
event says `mandatory_stops = 0`, which is an input to the strategy engine. The
hub is what the league actually publishes and what the lobby is built from.

So the direction is: **the hub proposes, the driver disposes.** The driver
overriding a field by hand is the normal case, not an error.

**Only `refuel_rate_lps` records that it came from the hub**, because it is the
only one of these columns that has a provenance column beside it. The rest are
written indistinguishably from a figure the driver read off the lobby screen
himself. That is a real gap - the audit asked for `source = hub` throughout -
and closing it needs a schema change this module cannot make on its own, so it
is named here rather than implied away.

### The two fuel fields are different quantities, and the hub says so

`tyresFuel.refuelRate` is **litres per second** and `tyresFuel.fuelMultiplier`
is a **rate multiplier**. They are not two spellings of one setting, and the
app has a separate column for each: `refuel_rate_lps` and `fuel_mult`. The hub
declaring `refuelRate: 1` for the GR3 league is corroborated by the app's own
measurement at Daytona - 1.003 L/s off the tank climbing.

Because `refuel_rate_lps` is `NOT NULL DEFAULT 2.5`, the number alone can never
say where it came from, which is what `refuel_rate_source` is for. A rate taken
from the hub is written as `hub`: not `measured`, because nobody measured it,
and not `declared`, because the driver did not type it. The league did.

### What this module refuses to translate

- **`drivingAssists.absLimit` / `tractionControlLimit` are limits, not
  settings.** `NO_LIMIT` says the league permits ABS; it does not say what the
  driver runs, and the app's column is what he runs. Only `PROHIBITED` is
  translatable, because then there is only one thing he can be running.
- **`carRegulations.powerLimitBhp` / `weightLimitKg` are event columns since
  7 Sep 2026** (`power_limit_bhp`, `weight_limit_kg`). Sardegna's 509 BHP /
  1,243 kg and Supercars' 1,335 kg bind the setup, and a sheet issued
  without them is a sheet the lobby refuses.
- **`carRegulations.bopEnabled` / `tuningAllowed` are event columns since
  11 Sep 2026** (`bop_enabled`, `tuning_allowed`, 1/0, NULL where the hub
  does not say). The Enduro runs BoP, which locks the gearbox and the power
  adjustments; before this the app had no field and `initial` had to ask.
- **`timeWeather.variableTimeSpeedRate` is not `events.time_multiplier`** -
  or rather, it is the same quantity and writing it still breaks something.
  `store.record_measured_clock` refuses to overwrite a multiplier that is
  already set unless `clock_source` says `measured`, and a hub write sets the
  value without setting the source. The event then refuses every game-clock
  measurement it is ever offered, for ever, and `start_hour` stays NULL - a
  latch of exactly the shape rule 10 describes. The app measures this off the
  game clock; the lobby setting is not worth blinding it.
"""
from __future__ import annotations

import datetime
from dataclasses import dataclass, field

from pitcrew.diagnostics import log
from pitcrew.hub.read import _when
from pitcrew.store import catalogs

_log = log(__name__)

# The hub writes its layouts after an em dash; the app's catalogue uses an en
# dash (`catalogs.LAYOUT_SEPARATOR`). Nothing is wrong with either - they are
# two systems that chose differently - but a split on the wrong one fails on
# every multi-layout circuit in the calendar, which is 17 of 33.
_HUB_SEPARATOR = "\u2014"

# GT7's compound names as the hub spells them, in the app's codes.
COMPOUNDS = {
    "RACING_SOFT": "RS", "RACING_MEDIUM": "RM", "RACING_HARD": "RH",
    "RACING_INTER": "IM", "RACING_WET": "HW",
    "SPORTS_SOFT": "SS", "SPORTS_MEDIUM": "SM", "SPORTS_HARD": "SH",
    "COMFORT_SOFT": "CS", "COMFORT_MEDIUM": "CM", "COMFORT_HARD": "CH",
}

# GT7's fixed-weather presets as the hub spells them, in the app's four words.
# The two cloud presets are dry track; the app's "Damp" is the closest thing it
# has to light rain, and heavy rain and a storm are both "Wet". A preset not in
# this table sets nothing, which leaves the field for the driver.
WEATHER_PRESETS = {
    "CLEAR": {"weather": "dry"},
    "LIGHT_CLOUD": {"weather": "dry"},
    "HEAVY_CLOUD": {"weather": "dry"},
    "LIGHT_RAIN": {"weather": "damp"},
    "HEAVY_RAIN": {"weather": "wet"},
    "STORM": {"weather": "wet"},
}

# The app's own drivetrain vocabulary, and the hub uses the same words. Listed
# rather than passed through so a value neither side has agreed on is refused.
DRIVETRAINS = ("FF", "FR", "MR", "RR", "4WD")

START_TYPES = {
    "ROLLING": "Rolling",
    "STANDING": "Standing",
    # GT7's "grid start with false-start check" is the app's third option.
    "GRID_FALSE_START": "Grid - no track limit",
}

# **Only names both vocabularies actually use.** Every value the hub holds
# today is one of these. `MORNING` was mapped in an earlier draft to the app's
# "Late Morning", which is a claim that two lists mean the same GT7 preset and
# nothing establishes it - and the app measures what a preset means off the
# game clock, so a wrong name here would be measured against.
TIMES_OF_DAY = {
    "DAWN": "Dawn", "NOON": "Noon", "AFTERNOON": "Afternoon",
    "EVENING": "Evening", "NIGHT": "Night",
    "SUNRISE": "Sunrise", "SUNSET": "Sunset",
}

# The hub's own name for the base layout of a circuit. `gt7-tracks.ts`:
# *"A circuit whose only layout is the base configuration uses the single
# variant `Default`, which renders as just the circuit name"*, and
# `parseTrackOption` is explicit that a string with no separator parses as
# variant `Default`. So a bare circuit name is a STATEMENT that the round runs
# the base layout - it is not the hub declining to say.
HUB_DEFAULT_VARIANT = "Default"

# The hub writes a reversed layout as `"<layout> Reverse"`; the app catalogue
# writes `"<layout> (Reverse)"`. Both list their layouts in the game's own
# order, which is what lets `Default` resolve positionally.
HUB_REVERSE_SUFFIX = " Reverse"


@dataclass(frozen=True)
class TrackMatch:
    """A hub track string, resolved against the app's catalogue.

    `layout` is `None` whenever the app cannot know it, and `why` says which
    kind of not-knowing it is. **It is never guessed**: a corner model is keyed
    on track and layout together, so a layout invented here would file Fuji's
    Short Course laps under the Full Course's corner numbers.
    """
    track: str | None
    layout: str | None
    why: str = ""

    @property
    def complete(self) -> bool:
        return bool(self.track and self.layout)


def resolve_track(hub_track: str | None) -> TrackMatch:
    """Turn one hub track string into the app's track and layout.

    **The hub's format is documented and exact**, in its own
    `src/lib/gt7-tracks.ts`: an option string is `"<circuit> — <variant>"`, and
    a string with no separator is the circuit at its `Default` variant. That
    file calls the format stable - *"changing it is a data migration, not a
    cosmetic edit"* - so this reads it as a specification rather than guessing
    at it.

    An earlier version of this function treated a bare circuit name as the hub
    declining to name a layout, and refused to resolve it wherever the app knew
    of more than one. That was wrong in the way that matters most here: it
    turned a definite statement into an absence, and it made 10 of the 33
    circuits on the calendar - Monza, Spa, Suzuka, Fuji, Deep Forest, Red Bull
    Ring and the rest - unresolvable when every one of them had been stated.

    Tried in this order, and the order matters:

    1. **The whole string as a track base.** `"Sardegna - Road Track"` is one
       circuit in both catalogues whose *name* contains a hyphen. Splitting on
       punctuation before this test invents a track called `Sardegna`.
    2. **Split on the hub's em dash** into circuit and variant.
    """
    raw = (hub_track or "").strip()
    if not raw:
        return TrackMatch(None, None, "the hub round names no circuit")

    # **A tuple, and the catalogue's own order preserved.** `Default` resolves
    # to the first layout, so a set here would have made the base layout of
    # every circuit whichever one happened to hash first.
    known = {name: tuple(catalogs.layouts_for(name))
             for name in catalogs.track_bases()}

    # 1. The bare string is a circuit in its own right, at its base layout.
    if raw in known:
        return _variant(raw, known[raw], HUB_DEFAULT_VARIANT)

    # 2. Circuit and variant, either side of the hub's separator. Split on the
    #    FIRST one, as `parseTrackOption` does.
    base, sep, variant = raw.partition(f" {_HUB_SEPARATOR} ")
    if not sep:
        base, sep, variant = raw.partition(f" {catalogs.LAYOUT_SEPARATOR} ")
    base, variant = base.strip(), variant.strip()
    if not sep or base not in known:
        return TrackMatch(
            None, None,
            f"{raw!r} is not a circuit this app has a catalogue entry for")
    return _variant(base, known[base], variant)


def _variant(track: str, layouts: tuple, variant: str) -> TrackMatch:
    """One hub variant name as the app's layout name.

    Three rules, and none of them is a guess:

    - **`Default` is the circuit's base layout**, which both catalogues list
      first because both list layouts in the game's own order. It is `Full
      Course` almost everywhere and `Layout A` at Sardegna - Road Track, which
      is exactly why it is taken positionally rather than by that name.
    - **`"<layout> Reverse"` is the app's `"<layout> (Reverse)"`.** The two
      catalogues punctuate the same fact differently.
    - Anything else has to match a layout the app knows, or the circuit goes
      through without one for the driver to finish.
    """
    if not layouts:
        return TrackMatch(track, None,
                          f"{track} has no layouts in this app's catalogue")
    if variant == HUB_DEFAULT_VARIANT:
        return TrackMatch(track, layouts[0])
    if variant in layouts:
        return TrackMatch(track, variant)
    if variant == "Reverse":
        # The base layout, reversed - the hub's shorthand where a circuit has
        # only the one configuration to reverse.
        reversed_base = f"{layouts[0]}{catalogs.REVERSE_SUFFIX}"
        if reversed_base in layouts:
            return TrackMatch(track, reversed_base)
    if variant.endswith(HUB_REVERSE_SUFFIX):
        spelled = (f"{variant[:-len(HUB_REVERSE_SUFFIX)]}"
                   f"{catalogs.REVERSE_SUFFIX}")
        if spelled in layouts:
            return TrackMatch(track, spelled)
    # The circuit is known and the variant is not. **The track still goes
    # through**: half an answer the driver completes beats no answer at all,
    # and he is the one looking at the lobby.
    return TrackMatch(
        track, None,
        f"the hub calls this layout {variant!r}, which is not one of "
        f"{list(layouts)} - pick it by hand")


# --------------------------------------------------------------- regulations

def _merge(*layers) -> dict:
    """Series defaults with the round's overrides laid over them, one level in.

    **Four layers, laid down weakest first**: the series default, the
    division's override, the round's, and the division's own entry for that
    round. The hub applies them in that order and so must this, or a driver in
    a division that changes a setting is planned against a race nobody is
    running.

    The blob is two levels deep - `{"tyresFuel": {"fuelMultiplier": 3}}` - so a
    shallow `dict.update` would let a round that overrides one tyre field
    discard every other field in that section.

    **And it is load-bearing, not speculative.** An earlier draft of this
    docstring said all 57 rounds override nothing; four of them do, two are
    still to come, and one is the 20 September Supercars round this driver
    races - it overrides the series' 30 minutes to 60. A shallow merge there
    would have kept the duration and dropped every other race-format field.
    """
    out: dict = {}
    for layer in layers:
        for section, body in (layer or {}).items():
            if isinstance(body, dict) and isinstance(out.get(section), dict):
                out[section].update(body)
            else:
                out[section] = dict(body) if isinstance(body, dict) else body
    return out


def _multiplier(enabled, value) -> str | None:
    """GT7's wear and fuel multipliers, in the picker's own vocabulary.

    **`Off` is a real answer and is not the same as unknown.** A league that
    disables tyre wear has said something definite; a league whose blob does
    not mention it has not, and the strategy engine must be able to tell those
    apart - one means "no stop is ever forced", the other means "nobody knows".
    """
    if enabled is False:
        return "Off"
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    # **Refused rather than rounded.** `int(1.5)` is 1, and a 1.5x wear race
    # planned as 1x runs a stint half again as long as the tyres have. The
    # picker's vocabulary is whole multipliers, so a fractional one is a thing
    # this app cannot express - and saying nothing leaves the field for the
    # driver, where rounding would put a wrong answer in it silently.
    # **Refused outside the range the app can express, too.** The hub allows
    # 1-50 and the picker offers 1x-10x; a `12x` set on a non-editable combo is
    # a silent no-op that leaves the form on its own default of `4x`, which is
    # a 3x error in stint length with nothing said. §5.2: never silently
    # convert a multiplier.
    if number != int(number) or not 1 <= number <= 10:
        _log.info("hub calendar: %r is not a multiplier this app can hold "
                  "- left unset", value)
        return None
    return f"{int(number)}x"


def regulations(settings: dict | None) -> dict:
    """The lobby blob as event-row fields. Absent stays absent.

    Every key this returns is one the event row has a column for and the hub
    states unambiguously. A field the hub does not carry is **not in the
    returned dict at all** - not `None` in it - so that a caller can tell "the
    hub says nothing about this" from "the hub says this is nothing", and a
    prefill never overwrites a driver's answer with an emptiness.
    """
    settings = settings or {}
    fmt = settings.get("raceFormat") or {}
    weather = settings.get("timeWeather") or {}
    fuel = settings.get("tyresFuel") or {}
    grid = settings.get("gridStart") or {}
    cars = settings.get("carRegulations") or {}
    assists = settings.get("drivingAssists") or {}

    out: dict = {}

    # --- how long, and in what units ---
    race_type = fmt.get("raceType")
    if race_type == "LAPS":
        out["race_type"] = "laps"
        if fmt.get("lapCount") is not None:
            out["race_laps"] = int(fmt["lapCount"])
    elif race_type == "TIMED":
        # The app stores a timed race's length in `race_laps` too -
        # `race_minutes` is never written, and `controller` reads the one
        # figure against `race_type`. Following that rather than introducing a
        # second convention this module would be alone in using.
        out["race_type"] = "time"
        if fmt.get("durationMinutes") is not None:
            out["race_laps"] = int(fmt["durationMinutes"])

    # --- weather ---
    mode = weather.get("weatherMode")
    if mode in ("RANDOM", "FIXED"):
        out["weather_rule"] = mode.title()
    if mode == "RANDOM":
        # Random is the app's "changeable": the circuit decides.
        out["weather"] = "changeable"
    elif mode == "FIXED":
        # **All six presets, because the column defaults to `dry`.** Mapping
        # only CLEAR and STORM meant a fixed HEAVY_RAIN round was written as a
        # dry race with `weather_rule` asserting the setting was fixed - a
        # confident wrong answer on the one field that decides the compound.
        out.update(WEATHER_PRESETS.get(
            weather.get("weatherStartPreset"), {}))
    if weather.get("timeOfDay") in TIMES_OF_DAY:
        out["time_of_day"] = TIMES_OF_DAY[weather["timeOfDay"]]
    # `variableTimeSpeedRate` is deliberately NOT mapped - see below.

    # --- tyres and fuel ---
    wear = _multiplier(fuel.get("tyreWearEnabled"),
                       fuel.get("tyreWearMultiplier"))
    if wear is not None:
        out["tyre_wear_mult"] = wear
    burn = _multiplier(fuel.get("fuelEnabled"), fuel.get("fuelMultiplier"))
    if burn is not None:
        out["fuel_mult"] = burn
    # **Litres per second, and a different quantity from the multiplier above.**
    # Only where fuel is actually on: a league that has switched fuel off has
    # no refuelling to have a rate for, and a rate carried into such an event
    # would price a stop that cannot happen.
    rate = fuel.get("refuelRate")
    if rate is not None and fuel.get("fuelEnabled") is not False:
        try:
            out["refuel_rate_lps"] = float(rate)
            # Never `declared` - the driver did not type this - and never
            # `measured`, because nobody measured it. `events.refuel_rate_lps`
            # is NOT NULL with a default of 2.5, so without a source beside it
            # a league figure and the schema's own placeholder are the same
            # number to every reader downstream.
            out["refuel_rate_source"] = "hub"
        except (TypeError, ValueError):
            pass

    compounds = _compounds(cars.get("allowedTyreCompounds"))
    if compounds:
        out["available_compounds"] = compounds
    required = _compounds(cars.get("requiredTyreCompound"))
    if required:
        out["required_compounds"] = required

    # --- the start, and the stops ---
    if grid.get("startType") in START_TYPES:
        out["start_type"] = START_TYPES[grid["startType"]]
    stops = grid.get("mandatoryPitStops")
    if stops is True:
        # **The count, and 1 only as the floor of "yes".** `mandatoryPitStops`
        # true with no count still means at least one stop; reading the missing
        # count as zero is how the stored Daytona event came to say a mandatory
        # one-stop round needs no stops.
        out["mandatory_stops"] = int(grid.get("minPitStopCount") or 1)
    elif stops is False:
        out["mandatory_stops"] = 0

    # --- assists: only a prohibition is translatable ---
    # **A mandated drivetrain is the drivetrain.** GT7 broadcasts no
    # drivetrain channel in any packet format, so this column is declared or it
    # is unknown - and `wheelspin` watches all four wheels without it. Where
    # the league restricts entries to one layout, every car in the race is that
    # layout, so this is a reading rather than a guess. `drivetrainLimit`
    # absent means the league did not restrict it, which says nothing about
    # what he drives.
    if cars.get("drivetrainLimit") in DRIVETRAINS:
        out["drivetrain"] = cars["drivetrainLimit"]
    # **The car regulations that bind a setup.** A limit the hub states is
    # written as a number; one it does not state is left out, so a prefill
    # never writes 0 over "unlimited" (rule 3).
    for hub_key, column in (("powerLimitBhp", "power_limit_bhp"),
                            ("weightLimitKg", "weight_limit_kg")):
        value = cars.get(hub_key)
        if value is not None:
            try:
                out[column] = float(value)
            except (TypeError, ValueError):
                pass
    # **BoP, and whether tuning is open** (plan row 2.7). A BoP round locks
    # the gearbox and the power adjustments, and `initial` asked the driver
    # because the app had no field. Only a real boolean is written: a hub
    # that does not say leaves the column NULL, never "no" (rule 3).
    for hub_key, column in (("bopEnabled", "bop_enabled"),
                            ("tuningAllowed", "tuning_allowed")):
        value = cars.get(hub_key)
        if isinstance(value, bool):
            out[column] = int(value)

    if assists.get("absLimit") == "PROHIBITED":
        out["abs_setting"] = "Off"
    if assists.get("tractionControlLimit") == "PROHIBITED":
        out["tcs"] = 0
    if assists.get("countersteeringAssistLimit") == "PROHIBITED":
        out["countersteer"] = 0

    return out


def _compounds(raw) -> list[str] | None:
    """Hub compound names as app codes, dropping none silently.

    An unrecognised compound is logged and left out rather than passed through:
    the strategy engine keys on these codes, and a `RACING_SOFT` reaching it
    unmapped is not a compound it can plan a stint on.
    """
    if not isinstance(raw, (list, tuple)) or not raw:
        return None
    out = []
    for name in raw:
        code = COMPOUNDS.get(str(name).strip().upper())
        if code is None:
            _log.info("hub calendar: no app code for compound %r", name)
            continue
        if code not in out:
            out.append(code)
    return out or None


# ------------------------------------------------------------- the calendar

@dataclass(frozen=True)
class Proposal:
    """One hub round, ready to become an event row.

    Nothing here is written anywhere until the driver selects it. A proposal is
    an offer with its provenance attached, which is why `unknowns` travels with
    it: the screen shows what the hub could not answer *before* he commits to
    the round, rather than leaving him to find the blank layout afterwards.
    """
    round_id: str
    series_id: str
    series_name: str
    round_name: str | None
    scheduled_at: datetime.datetime | None
    track: str | None
    layout: str | None
    car_name: str | None = None
    regs: dict = field(default_factory=dict)
    # Per-car BoP for this round, when the driver's car is known.
    bhp: int | None = None
    weight_kg: int | None = None
    # Where this round sits in the season, for naming an event whose round has
    # no name of its own.
    position: int | None = None
    # The class this round puts him in, where the series races more than one.
    # **It changes between rounds and it changes the car**, which is why it is
    # carried rather than derived once per series.
    race_class: str | None = None
    unknowns: tuple[str, ...] = ()
    # The stored event this round is already recorded as, if there is one.
    event_id: int | None = None
    # Whether `event_id` was matched by circuit and car rather than read off
    # the event's own `hub_round_id`. An adopted event has not been linked yet
    # and the caller is expected to write the id onto it, so that this is the
    # last time the match has to be inferred.
    adopted: bool = False

    @property
    def name(self) -> str:
        """The event's name, derived and stable.

        **Derived from the round, never from the date or the track.** Both of
        those move - a round gets rescheduled, a circuit gets corrected - and
        an event whose name moved with them would stop matching the sessions
        recorded under it.
        """
        round_name = (self.round_name or "").strip()
        if round_name:
            return f"{self.series_name} {round_name}"
        if self.position is not None:
            return f"{self.series_name} Rd{self.position}"
        return self.series_name

    # Regulations whose event column is NOT NULL with an app default, so an
    # unanswered one does not arrive as unanswered - it arrives as a confident,
    # wrong statement. `tyre_wear_mult` and `fuel_mult` default to `'Off'`,
    # which says wear and burn are disabled and no stop is ever forced;
    # `mandatory_stops` defaults to `0`, the exact figure this whole feature
    # exists to stop being wrong about.
    LOAD_BEARING = ("tyre_wear_mult", "fuel_mult", "mandatory_stops",
                    "available_compounds")

    @property
    def known(self) -> bool:
        """Whether this round can be written down without inventing anything.

        Track and layout, because `circuit_key` is built from the pair and a
        missing layout files laps under a corner model for a different lap
        length.

        **And the car**, because CLAUDE.md's rank zero is what is actually in
        the car and an event with a NULL one pushes that NULL into the bridge,
        the sheet lookup and the scope. The Enduro round is the live example:
        the hub carries no entry naming his car there, and it is otherwise
        complete enough to have been created unattended.

        **And the regulations that cannot be absent.** Their columns are NOT
        NULL with defaults, so leaving them out of the write does not leave
        them blank - it fills them with `'Off'`, `'Off'`, `0` and `[]`, which
        the strategy engine reads as a race with no wear, no fuel burn, no
        mandatory stop and no legal tyre. `_multiplier` goes to some trouble to
        keep "off" and "unknown" apart; creating a row unattended would
        collapse them again at the last step.
        """
        return bool(self.track and self.layout and self.car_name
                    and all(key in self.regs for key in self.LOAD_BEARING))

    @property
    def missing(self) -> tuple[str, ...]:
        """Everything that stops this round being written down, in words.

        Said to the driver rather than kept for a boolean: an incomplete round
        that does not name what it is missing leaves him to find the blank
        field after saving, which is the same information arriving too late to
        be free.
        """
        said = {"tyre_wear_mult": "tyre wear", "fuel_mult": "fuel use",
                "mandatory_stops": "mandatory stops",
                "available_compounds": "the legal compounds"}
        out = [] if self.car_name else ["your car in this league"]
        out += [said[key] for key in self.LOAD_BEARING if key not in self.regs]
        return tuple(out)

    def event_fields(self) -> dict:
        """Exactly what to write into the events table.

        The regulations first, then the identity - so that a hub field can
        never be shadowed by one of the app's own, and `hub_round_id` is
        written whatever else is missing. It is what makes this round findable
        again after the driver renames the event.
        """
        fields = dict(self.regs)
        fields.update({
            "name": self.name,
            "series": self.series_name,
            "hub_round_id": self.round_id,
            "track": self.track,
            "layout": self.layout,
        })
        if self.car_name:
            fields["car_name"] = self.car_name
        return {k: v for k, v in fields.items() if v is not None}


def upcoming(hub, *, me: str | None = None,
             now: datetime.datetime | None = None,
             stored_events=None) -> list[Proposal]:
    """The rounds still to come, soonest first, ready to be raced.

    `me` is the driver's name as the hub spells it. When it is set the calendar
    is **narrowed to the leagues he is actually registered in**, and his car
    comes off his own entry. When it is not, every active league is offered
    instead and `unknowns` says so - because a calendar showing four leagues he
    can pick from is a smaller failure than an empty screen, and the reason it
    is showing four is a thing he can fix.

    `stored_events` is the app's own event list. It is used only to attach
    `event_id` to a round already recorded, so that selecting tonight's race
    twice loads the event the second time instead of forking it.
    """
    if not getattr(hub, "available", False):
        return []

    entries: dict[str, str] = {}
    series_ids = None
    unknown_identity = ()
    driver = hub.driver_by_name(me) if me else None
    if driver is not None:
        mine = [s for s in hub.my_series(driver.id) if s.status == "ACTIVE"]
        series_ids = {s.id for s in mine}
        for series in mine:
            for entry in hub.entries(series.id):
                if entry.driver_id == driver.id and entry.car_name:
                    entries[series.id] = entry.car_name
    else:
        # **Two different failures, and they want different actions.** An
        # unset name and a name the hub does not recognise both land here;
        # saying "no name is set" to a driver who has set one sends him to
        # check a setting that is already right.
        unknown_identity = ((
            f"the hub has no driver called {me!r}, so this is every "
            f"active league rather than the ones you are entered in - "
            f"check the spelling against the hub"
        ) if me else (
            "no hub driver name is set, so this is every active league "
            "rather than the ones you are entered in - "
            "python -m tools.name_drivers --me <your hub name>"
        ),)
        series_ids = {s.id for s in hub.series(active_only=True)}

    by_id = {s.id: s for s in hub.series(active_only=False)}
    known_rounds = {
        str(event.get("hub_round_id")): event["id"]
        for event in (stored_events or [])
        if event.get("hub_round_id")}
    # **Events from before this feature existed, which is all nine of them.**
    # They carry no round id, so nothing links them to the calendar - and
    # without this every one of them would be offered as a round with no event,
    # then created a second time the moment it was picked, leaving the practice
    # laps on one copy and the race on the other.
    orphans = [event for event in (stored_events or [])
               if not event.get("hub_round_id")]
    claimed: set = set()
    spacing: dict = {}

    out: list[Proposal] = []
    for rnd in hub.upcoming_rounds(series_ids=series_ids, now=now):
        series = by_id.get(rnd.series_id)
        divisions, division_said = hub.division_layers(
            rnd.id, driver.id if driver is not None else None)
        settings = _merge(getattr(series, "lobby_settings", None),
                          *divisions[:1], rnd.overrides, *divisions[1:])
        match = resolve_track(rnd.track)
        car = entries.get(rnd.series_id)
        race_class, car_said = None, ""
        if car is None and driver is not None and getattr(
                series, "multi_class", False):
            # **A manufacturer series names a marque, not a car.** Read from
            # the series registration alone this looks like a driver with no
            # entry; the car is a consequence of the class he is assigned for
            # this particular round.
            car, race_class, car_said = hub.multi_class_car(
                rnd.series_id, driver.id, rnd.id)
        bhp = weight = None
        if car:
            override = hub.car_overrides(rnd.id).get(car)
            if override:
                bhp, weight = override.get("bhp"), override.get("weight_kg")
        unknowns = list(unknown_identity)
        if match.why:
            unknowns.append(match.why)
        if division_said.startswith("which of"):
            unknowns.append(division_said)
        if not car:
            unknowns.append(
                f"no car - {car_said}" if car_said
                else "no car - the hub has no entry naming yours here")

        event_id, adopted = known_rounds.get(rnd.id), False
        if event_id is None:
            event_id = _adopt(
                orphans, claimed, match, car, when=rnd.scheduled_at,
                spacing=spacing.setdefault(
                    rnd.series_id, _spacing_days(hub, rnd.series_id)))
            adopted = event_id is not None
            if adopted:
                claimed.add(event_id)

        out.append(Proposal(
            round_id=rnd.id, series_id=rnd.series_id,
            series_name=rnd.series_name, round_name=rnd.name,
            scheduled_at=rnd.scheduled_at,
            track=match.track, layout=match.layout, car_name=car,
            regs=regulations(settings), bhp=bhp, weight_kg=weight,
            position=rnd.position, race_class=race_class,
            unknowns=tuple(unknowns),
            event_id=event_id, adopted=adopted))
    return out


def _spacing_days(hub, series_id: str) -> float:
    """How far apart this league runs its rounds, from its own calendar.

    A season's own rhythm rather than a constant: these leagues run weekly, the
    Porsche Cup monthly and the Enduro less often than that, and one number for
    all of them would be wrong for most.

    Falls back to 14 days where a series has fewer than two dated rounds -
    stated rather than derived, and deliberately generous, because the bound it
    feeds exists to catch a match that is months out, not to be precise.
    """
    try:
        dates = sorted(d for d in (_when(r.get("scheduledAt"))
                                   for r in hub.rounds(series_id)) if d)
    except Exception:                                        # noqa: BLE001
        return 14.0
    gaps = sorted((b - a).total_seconds() / 86400.0
                  for a, b in zip(dates, dates[1:]) if b > a)
    return gaps[len(gaps) // 2] if gaps else 14.0


def _recent_enough(event, when, spacing: float) -> bool:
    """Whether this event was last worked on close enough to be this round's.

    Undated either way is a match: an event with no timestamp cannot be shown
    to belong to a different round, and refusing on a missing field would be
    rule 3 - treating absent as a value.
    """
    if when is None:
        return True
    # **`created_at`, not `updated_at`.** An event is created for a round;
    # `updated_at` moves every time it is saved, so merely opening last
    # season's Mount Panorama event and re-saving it made it recent enough to
    # adopt this season's Mount Panorama round.
    touched = _when(event.get("created_at") or event.get("updated_at"))
    if touched is None:
        return True
    return (when - touched).total_seconds() / 86400.0 <= spacing


def _adopt(orphans, claimed, match: TrackMatch, car: str | None,
           when: datetime.datetime | None = None, spacing: float = 14.0):
    """The one stored event that is already this round, or `None`.

    Matched on **circuit, layout and car together, and only when exactly one
    event fits** - the same bar `league_for` sets for matching a league by its
    car, and for the same reason: two candidates is not a match, it is a coin
    toss, and a round bound to the wrong event puts this week's laps in last
    month's aggregate where nothing downstream can separate them again.

    An unresolved layout adopts nothing. Without it the pair does not identify
    a circuit, and Spa's Full Course and its 24h Layout are different tracks
    with different lap lengths and different corner models.

    `claimed` stops one event answering for two rounds: the calendar is walked
    soonest-first, so the earlier round takes it and the later one is offered
    as new - which is the right way round, because the earlier one is the one
    whose laps already exist.

    **And it must be recent enough to be about this round.** Leagues revisit
    circuits: unbounded, July's Road Atlanta event - same circuit, same car,
    already raced - adopts September's Road Atlanta round, and every lap of the
    new round lands in the old event's aggregate mixed with laps from a
    different tune. The bound is one round-interval taken from the league's own
    calendar, and the reasoning is that an event is prepared for a round: if it
    was last touched longer ago than the gap between rounds, there was another
    round in between and it belongs to that one. Measured against this archive,
    every event was created 0-6 days before its round on a 7-day season.
    """
    from pitcrew.hub.link import _same_car

    if not match.complete or not car:
        return None
    fits = [event["id"] for event in orphans
            if event["id"] not in claimed
            and (event.get("track") or "") == match.track
            and (event.get("layout") or "") == match.layout
            and _same_car(event.get("car_name"), car)
            and _recent_enough(event, when, spacing)]
    return fits[0] if len(fits) == 1 else None


# What to call each field when the difference is read out loud. Only the
# fields worth interrupting for: a regulation that changes how the race is
# driven, not every cosmetic difference between two spellings.
SPOKEN = {
    "mandatory_stops": "mandatory stops",
    "race_laps": "race length",
    "race_type": "race type",
    "tyre_wear_mult": "tyre wear",
    "fuel_mult": "fuel use",
    "available_compounds": "compounds",
    "start_type": "start",
    "refuel_rate_lps": "refuel rate",
    # A hub that turns BoP on or off after he has an answer on file is news
    # (the critic on row 2.7, M1). 1 is on, 0 off.
    "bop_enabled": "BoP",
    "tuning_allowed": "open tuning",
}


def disagreements(proposal: Proposal, event: dict) -> list[str]:
    """Where the stored event and the league's own regulations differ.

    **Reported, never silently corrected.** The stored row is the driver's, and
    he may have fixed something the hub has wrong - the hub is the better
    source, not an infallible one, and overwriting his correction on every
    launch would be the same defect as the one this feature removes, pointed
    the other way.

    Only fields the hub actually states are compared. A field the hub is silent
    about cannot disagree with anything, and reading its absence as a
    difference would report every event as wrong about everything.
    """
    out = []
    for key, said in SPOKEN.items():
        if key not in proposal.regs:
            continue
        theirs, ours = proposal.regs[key], event.get(key)
        if isinstance(theirs, list) or isinstance(ours, list):
            if sorted(theirs or []) == sorted(ours or []):
                continue
        elif theirs == ours:
            continue
        out.append(f"{said} {ours!r} here, {theirs!r} on the hub")
    return out


def next_round(proposals) -> Proposal | None:
    """The one to open on. Soonest first, and nothing clever.

    **Not "the most complete" or "the one he has practised for".** The next
    race is the next race; ranking it by how much the app knows about it would
    open on a well-documented round three weeks away while tonight's sat
    further down the list.
    """
    return proposals[0] if proposals else None
