"""Building and validating the `gt7-pitcrew/1.7` payload.

This is the app's most important output. It is pasted into a prompt and read by
a language model, not parsed by a program — so a malformed payload does not
throw, it gets misread and a setup gets built on it. Hence `validate()`, and
hence `to_json()` refusing to emit rather than emitting something wrong.

Sections are omitted when the app does not have them. An omitted section reads
as "not built yet"; a section full of nulls reads as "built but nothing
measured". Both are honest. A section full of zeros is not.
"""
from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field

from pitcrew.telemetry.packet import STEER_SOURCE, STEERING_FULL_LOCK_RAD

FORMAT = "gt7-pitcrew/1.7"
APP_VERSION = "pitcrew 2.2.0"

SESSION_TYPES = ("practice", "quali", "tt", "race")
PACKET_FORMATS = ("A", "B", "~", "C")
ABS_SETTINGS = ("Off", "Weak", "Default")
CORNER_MODEL_SOURCES = ("track-map", "auto-segment")

# Contract §2. GT7's own tokens (`GR3`) are mapped to these at the export
# boundary in `build.py`; anything else reaching here is a class that does not
# exist and is refused rather than passed on.
CAR_CATEGORIES = ("Gr.1", "Gr.2", "Gr.3", "Gr.4", "Gr.B", "Gr.X", "Gr.N")
_N_CLASS = re.compile(r"^N(100|[1-9]\d{2}|1000)$")

# Contract §5 and §16.3 row 5.
EXCLUSION_REASONS = ("out-lap", "in-lap", "incident", "traffic",
                     "fuel-implausible", "manual")
EXCLUSION_SOURCES = ("auto", "driver")

# Contract §8. **Spelled out here rather than imported from `analysis/wear.py`**
# so that the validator states the contract instead of mirroring the producer -
# a drift in the producer's wording has to surface as a refusal, which it
# cannot do if both sides read the same constant.
WEAR_METHODS = (
    "two gauge readings inside one run",
    "one gauge reading, assumed fresh at the run's first lap",
    "one gauge reading, over a set the driver declared fresh",
    "one gauge reading, over a set whose opening temperatures are those of a "
    "set as fitted",
)
WEAR_CONFIDENCES = ("measured", "assumed", "converted")
# The one method that rests on an app-side temperature band rather than on two
# readings or on the driver's own word. §6.1 makes `measured` conditional on
# those two and on nothing else.
METHOD_FRESH_OBSERVED = WEAR_METHODS[3]
METHOD_FRESH_AT_RUN_START = WEAR_METHODS[1]

WEAR_PHASES = ("flat", "linear", "cliff")
COMPOUND_PROFILE_SOURCES = ("measured", "declared", "assumed")
BINDING_CONSTRAINTS = ("tyre", "fuel", "regulation", "evidence",
                       "unknown")
RACE_LENGTH_TYPES = ("time", "laps")

# Contract §16.4. The rate the plan's stops were costed at is only readable
# beside a statement of where it came from, and the one value that must never
# pass for a measurement in a race payload is the app's own default.
REFUEL_RATE_UNCONFIRMED = "still the app default - not confirmed"

MIN_DEGRADATION_SAMPLES = 5     # §8: a slope needs five counted laps in one run


class ExportRefused(ValueError):
    """The payload would be misread. Fix it rather than send it."""


@dataclass
class Meta:
    # All five are required and **none of them has a fallback**. A placeholder
    # here is worse than an absent field: it satisfies the validator's own
    # required-field check with something that was never measured. See
    # `build.py` for the two that had one.
    car: str | None
    circuit: str | None
    date: str | None                # YYYY-MM-DD
    session_type: str | None
    packet: str | None
    car_category: str | None = None
    game_version: str | None = None
    # What the running was for and where the car started, because the
    # same lap times mean different things under each. A qualifying
    # session judged on stint consistency is being judged on something it
    # was never run for.
    practice_intent: str | None = None
    practice_mode: str | None = None
    # A full race against the AI, run to prove the plan. Real stops under
    # race conditions and therefore the best evidence there is - and not
    # the league race, which a post-mortem must not mistake it for.
    rehearsal: bool = False
    compound_front: str | None = None
    compound_rear: str | None = None
    # Every compound the session ran, in order. Present whether one was run or
    # five; `compound.front/.rear` is emitted only when there was exactly one,
    # because a single compound is a fact about the session and a vote between
    # three is not.
    compounds_run: list[str] | None = None
    abs_setting: str | None = None
    tcs: int | None = None
    countersteer: bool | None = None
    tyre_wear_mult: str | None = None       # "Off" or "4x" - a string, so Off fits
    fuel_mult: str | None = None
    corner_model: dict | None = None
    app_version: str = APP_VERSION

    def as_export(self) -> dict:
        payload: dict = {
            "car": self.car,
            "carCategory": self.car_category,
            "circuit": self.circuit,
            "date": self.date,
            "sessionType": self.session_type,
            "packet": self.packet,
            "appVersion": self.app_version,
        }
        if self.game_version:
            payload["gameVersion"] = self.game_version
        if self.practice_intent:
            payload["practiceIntent"] = self.practice_intent
        if self.practice_mode:
            payload["practiceMode"] = self.practice_mode
        if self.rehearsal:
            payload["rehearsal"] = True
        if self.compound_front or self.compound_rear:
            payload["compound"] = {
                "front": self.compound_front,
                "rear": self.compound_rear,
            }
        if self.compounds_run:
            payload["compoundsRun"] = list(self.compounds_run)
        if any(v is not None for v in (self.abs_setting, self.tcs, self.countersteer)):
            payload["assists"] = {
                "abs": self.abs_setting,
                "tcs": self.tcs,
                "countersteer": self.countersteer,
            }
        if self.tyre_wear_mult is not None or self.fuel_mult is not None:
            payload["multipliers"] = {
                "tyreWear": self.tyre_wear_mult,
                "fuel": self.fuel_mult,
            }
        if self.corner_model is not None:
            payload["cornerModel"] = self.corner_model
        return payload


# **The full lock of the channel that is exported**, in degrees, and not the
# driver's 1080-degree rim setting. `wheelRotation` is GT7's in-game wheel and
# saturates at +-pi whatever the rim is set to, so `steerPeakDeg` is on a
# 180-degree scale. Emitting the rim's figure put the two fields a factor of
# three apart: a reader given `steerPeakDeg: -67.47` against 1080 computes
# 12.5% of lock where `steerPeakNorm: -0.375` says 37.5%, and the contract
# pairs the two precisely so degrees can be scaled.
STEER_FULL_LOCK_DEG = round(math.degrees(STEERING_FULL_LOCK_RAD), 1)
STEER_ROTATION_SOURCE = (
    "full lock of the exported channel, from centre. `wheelRotation` is GT7's "
    "in-game wheel and saturates at +-pi whatever rotation the rim is set to, "
    "so steerPeakDeg divided by this is steerPeakNorm. It is not the driver's "
    "physical wheel rotation setting.")


@dataclass
class Derived:
    """The `derived` section: everything the app computed, with its thresholds."""
    thresholds: dict
    bottoming_ref_mm: dict | None = None
    bottoming_ref_source: str | None = None
    # The raw per-wheel minimum, which is a measurement, beside the reference,
    # which is an inference. CLAUDE.md 3.3 fact 3 asks for both and the app
    # published only the second.
    observed_min_height_mm: dict | None = None
    steer_source: str = STEER_SOURCE
    steer_rotation_deg: float = STEER_FULL_LOCK_DEG
    extra: dict = field(default_factory=dict)

    def as_export(self) -> dict:
        payload = {
            "thresholds": dict(self.thresholds),
            "steerSource": self.steer_source,
            "steerRotationDeg": self.steer_rotation_deg,
            "steerRotationSource": STEER_ROTATION_SOURCE,
        }
        if self.bottoming_ref_mm is not None:
            payload["bottomingRefMm"] = dict(self.bottoming_ref_mm)
            payload["bottomingRefSource"] = (
                self.bottoming_ref_source
                or "lowest suspension height observed across the counted laps")
        if self.observed_min_height_mm is not None:
            payload["observedMinHeightMm"] = dict(self.observed_min_height_mm)
        payload.update(self.extra)
        return payload


def build_payload(meta: Meta, *,
                  setup: dict | None = None,
                  driver_changes: list[dict] | None = None,
                  range_record: dict | None = None,
                  session: dict | None = None,
                  laps: list[dict] | None = None,
                  runs: list[dict] | None = None,
                  corners: list[dict] | None = None,
                  wear: dict | None = None,
                  gearing: dict | None = None,
                  strategy: dict | None = None,
                  derived: Derived | None = None,
                  notes: str = "") -> dict:
    """Assemble the payload. Empty sections are omitted, not emitted as nulls."""
    payload: dict = {"format": FORMAT, "meta": meta.as_export()}

    if setup:
        section = dict(setup)
        if driver_changes:
            section["driverChanges"] = list(driver_changes)
        payload["setup"] = section
    if range_record:
        payload["rangeRecord"] = range_record
    if session:
        payload["session"] = session
    if laps:
        payload["laps"] = list(laps)
    if runs:
        payload["runs"] = list(runs)
    if corners:
        payload["corners"] = list(corners)
    if wear:
        payload["wear"] = wear
    if gearing:
        payload["gearing"] = gearing
    if strategy:
        payload["strategy"] = strategy
    if derived is not None:
        payload["derived"] = derived.as_export()
    if notes:
        payload["notes"] = notes

    return payload


def validate(payload: dict) -> list[str]:
    """Everything wrong with this payload, as readable sentences."""
    problems: list[str] = []

    if payload.get("format") != FORMAT:
        problems.append(f"format must be {FORMAT!r}, got {payload.get('format')!r}")

    meta = payload.get("meta")
    if not isinstance(meta, dict):
        problems.append("meta is required")
        return problems

    for key in ("car", "circuit", "date", "sessionType", "packet"):
        if not meta.get(key):
            problems.append(f"meta.{key} is required")

    # Required since 1.4. GT7's physics, tyre model and geometry have been
    # rewritten twice in two updates, so a measurement without the version it
    # was taken under cannot be filed and cannot safely be compared with the
    # next one. Refusing costs one field on the event page; not refusing costs
    # a measurement that reads as current forever.
    if not meta.get("gameVersion"):
        problems.append(
            "meta.gameVersion is required - a measurement with no game version "
            "cannot be filed against the update it was taken under")

    if meta.get("sessionType") and meta["sessionType"] not in SESSION_TYPES:
        problems.append(
            f"meta.sessionType must be one of {SESSION_TYPES}, "
            f"got {meta['sessionType']!r}")
    if meta.get("packet") and meta["packet"] not in PACKET_FORMATS:
        problems.append(
            f"meta.packet must be one of {PACKET_FORMATS}, got {meta['packet']!r}")

    # GT7's stream writes `GR3`; the contract's vocabulary is `Gr.3`, and the
    # consuming tool's per-car library is keyed on the latter. The mapping is
    # done at the export boundary, so a raw token arriving here means it was
    # bypassed.
    category = meta.get("carCategory")
    if category is not None and category not in CAR_CATEGORIES \
            and not _N_CLASS.match(str(category)):
        problems.append(
            f"meta.carCategory must be one of {CAR_CATEGORIES} or N100-N1000, "
            f"got {category!r} - GT7's own token is not the contract's "
            f"vocabulary")

    date = meta.get("date") or ""
    if date and (len(date) != 10 or date[4] != "-" or date[7] != "-"):
        problems.append(f"meta.date must be YYYY-MM-DD, got {date!r}")

    assists = meta.get("assists")
    if isinstance(assists, dict):
        if assists.get("abs") is not None and assists["abs"] not in ABS_SETTINGS:
            problems.append(
                f"meta.assists.abs must be one of {ABS_SETTINGS}, "
                f"got {assists['abs']!r}")
        tcs = assists.get("tcs")
        if tcs is not None and not (isinstance(tcs, int) and 0 <= tcs <= 5):
            problems.append(f"meta.assists.tcs must be an integer 0-5, got {tcs!r}")

    multipliers = meta.get("multipliers")
    if isinstance(multipliers, dict):
        for key, value in multipliers.items():
            if value is not None and not isinstance(value, str):
                problems.append(
                    f"meta.multipliers.{key} must be a string so that 'Off' is "
                    f"representable, got {value!r}")

    problems.extend(_validate_compounds(payload, meta))
    problems.extend(_validate_runs(payload))
    problems.extend(_validate_corners(payload, meta))
    problems.extend(_validate_laps(payload))
    problems.extend(_validate_session(payload))
    problems.extend(_validate_gearing(payload))
    problems.extend(_validate_wear(payload))
    problems.extend(_validate_prohibited(payload))
    problems.extend(_validate_strategy(payload, meta))
    problems.extend(_validate_known_keys(payload))
    return problems


def _validate_compounds(payload: dict, meta: dict) -> list[str]:
    """`wear.byCompound` may only name compounds the session actually ran.

    This is the check that was missing when an export carried wear rates for
    Racing Soft and Racing Medium against a `meta.compound` of Racing Hard,
    each tagged `driver-gauge` - the highest-trust provenance in the schema -
    and a consumer picked the race tyre off them. A rate for a compound the
    session never ran is a fabrication however it got there, so it is refused
    rather than left to discipline.
    """
    wear = payload.get("wear")
    if not isinstance(wear, dict):
        return []
    by_compound = wear.get("byCompound")
    if not isinstance(by_compound, dict):
        return []

    recorded = set(meta.get("compoundsRun") or [])
    compound = meta.get("compound") or {}
    for end in ("front", "rear"):
        if compound.get(end):
            recorded.add(compound[end])
    if not recorded:
        return ["wear.byCompound is present but meta records no compound at "
                "all, so its keys cannot be checked against what was run"]

    problems = []
    for code, entry in by_compound.items():
        name = (entry or {}).get("compound")
        if not name:
            problems.append(
                f"wear.byCompound.{code} does not name its compound, so it "
                f"cannot be checked against meta")
            continue
        if name not in recorded:
            problems.append(
                f"wear.byCompound.{code} is {name!r}, which this session never "
                f"ran - it recorded {sorted(recorded)}")

    single = compound.get("front") or compound.get("rear")
    if single and len(by_compound) > 1:
        problems.append(
            f"meta.compound says one compound ({single!r}) but wear.byCompound "
            f"carries {len(by_compound)} - one of the two is inventing a stint")
    return problems


def _validate_runs(payload: dict) -> list[str]:
    """Runs must be ordered, contiguous, and honest about the tyres."""
    runs = payload.get("runs")
    if runs is None:
        return []
    problems = []
    previous = None
    for index, run in enumerate(runs):
        where = f"runs[{index}]"
        if not isinstance(run.get("id"), int):
            problems.append(f"{where}.id is required")
        first, last = run.get("firstLap"), run.get("lastLap")
        if not isinstance(first, int) or not isinstance(last, int):
            problems.append(f"{where} must carry firstLap and lastLap")
            continue
        if last < first:
            problems.append(f"{where} ends at lap {last}, before it starts")
        if previous is not None and first <= previous:
            problems.append(
                f"{where} starts at lap {first}, which run before it already "
                f"covered - a lap belongs to one run")
        elif previous is not None and first != previous + 1:
            # Only the overlap was refused, so a lap belonging to no run at all
            # passed. Every rate in `wear.byRun` is computed inside a run, so a
            # lap in no run is a lap nothing can be measured over and nothing
            # said so.
            problems.append(
                f"{where} starts at lap {first} where the run before it ended "
                f"at {previous} - laps {previous + 1} to {first - 1} belong to "
                f"no run, and nothing can be measured over them")
        previous = last
        if run.get("tyresFresh") is False and not run.get("tyresFreshSource"):
            problems.append(
                f"{where}.tyresFresh is false, which claims the set carried "
                f"over. That is a positive claim and needs its source; "
                f"'not declared' is null")
    return problems


# Contract §13 and CLAUDE.md §4.8, as key fragments. Each entry is
# (fragment, why it cannot be here). Only "tow" was ever walked, so a payload
# carrying an oil temperature, a boost trace or a high/low-speed damper split
# shipped unremarked - and the last four of these are the app's own proof that
# a piece of logic was pattern-matched from a sim that is not GT7.
PROHIBITED_KEY_FRAGMENTS: tuple[tuple[str, str], ...] = (
    ("tow", "GT7's feed carries no proximity, closing speed or opponent "
            "positions, so a tow cannot be detected"),
    ("oiltemp", "oil temperature is pinned at ~110 C and carries no "
                "information"),
    ("watertemp", "water temperature is pinned at ~85 C and carries no "
                  "information"),
    ("boost", "boost is on the do-not-export list - it changes no setup "
              "decision and displaces the driver's report"),
    ("tyrepressure", "GT7 has no tyre pressure; the logic was pattern-matched "
                     "from another sim"),
    ("tirepressure", "GT7 has no tyre pressure; the logic was pattern-matched "
                     "from another sim"),
    ("caster", "GT7 has no caster; the logic was pattern-matched from another "
               "sim"),
    ("brakepressure", "GT7 has no brake pressure; the logic was "
                      "pattern-matched from another sim"),
    ("highspeeddamper", "GT7 has no high/low-speed damper split"),
    ("lowspeeddamper", "GT7 has no high/low-speed damper split"),
    ("damperhighspeed", "GT7 has no high/low-speed damper split"),
    ("damperlowspeed", "GT7 has no high/low-speed damper split"),
    ("gps", "GPS position arrays are raw trace, not an aggregate"),
    ("latitude", "GPS position arrays are raw trace, not an aggregate"),
    ("longitude", "GPS position arrays are raw trace, not an aggregate"),
)

# A key that names one of these *and* carries a list is a series. The scalars
# are allowed and named in §13 - `limiterRpm`, `maxSpeedRpm`, `upshiftRpm` -
# so the prohibition is on the shape, not on the word.
SERIES_KEY_FRAGMENTS = ("rpm", "trace", "series", "samplesat", "framebyframe")


def _normalised_key(key: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(key).lower())


def _validate_prohibited(payload: dict) -> list[str]:
    """Contract §13: what may never appear, at any depth.

    These are refused by the validator rather than left to discipline, because
    every one of them is a field that reads as measured and is not - and the
    last four are the app's own signal that a heuristic came from a different
    simulator.
    """
    problems: list[str] = []

    def walk(node, path: str) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                where = f"{path}.{key}" if path else key
                flat = _normalised_key(key)
                for fragment, why in PROHIBITED_KEY_FRAGMENTS:
                    if fragment in flat:
                        problems.append(f"{where} is refused: {why}")
                if isinstance(value, list) and any(
                        fragment in flat for fragment in SERIES_KEY_FRAGMENTS):
                    problems.append(
                        f"{where} is a series, and the export is aggregates "
                        f"only - raw 60 Hz traces stay in the app")
                walk(value, where)
        elif isinstance(node, list):
            for index, value in enumerate(node):
                walk(value, f"{path}[{index}]")

    walk(payload, "")
    return problems


def _validate_strategy(payload: dict, meta: dict) -> list[str]:
    strategy = payload.get("strategy")
    if not isinstance(strategy, dict):
        return []
    problems = []
    assumptions = strategy.get("assumptions")
    if not isinstance(assumptions, dict):
        problems.append("strategy.assumptions is required alongside a plan")
        return problems

    # **The refusal that could never fire.** `events.refuel_rate_lps` is
    # `NOT NULL DEFAULT 2.5`, so the None test below was unreachable from any
    # app-built payload and the case it was written for - the app's own
    # default standing in for a measurement - shipped silently. The
    # provenance is what is actually checkable, so it is required, and a race
    # plan costed on an unconfirmed default is refused: on the measured Monza
    # figure of ~1 L/s against 2.5 that is a 2.5x error in the stop count.
    if assumptions.get("refuelRateLps") in (None, ""):
        problems.append(
            "strategy.assumptions.refuelRateLps is required - it is the number "
            "that decides the race, and a default in its place is unreadable")
    elif not assumptions.get("refuelRateSource"):
        problems.append(
            "strategy.assumptions.refuelRateSource is required beside "
            "refuelRateLps - the figure is only readable with a statement of "
            "whether it was measured, declared or left at the app default")
    elif (assumptions["refuelRateSource"] == REFUEL_RATE_UNCONFIRMED
          and meta.get("sessionType") == "race"):
        problems.append(
            f"strategy.assumptions.refuelRateLps is still the app default "
            f"({assumptions['refuelRateLps']} L/s) and nothing has confirmed "
            f"it. It sets the cost of every stop and therefore the stop "
            f"count - measure or declare it before exporting a race")

    constraint = strategy.get("bindingConstraint")
    if constraint not in BINDING_CONSTRAINTS + (None,):
        problems.append(
            f"strategy.bindingConstraint must be one of "
            f"{', '.join(BINDING_CONSTRAINTS)}, got {constraint!r}")

    problems.extend(_validate_race_length(strategy))
    problems.extend(_validate_plan(strategy))

    for index, profile in enumerate(strategy.get("compoundProfiles") or []):
        source = profile.get("source")
        if source is not None and source not in COMPOUND_PROFILE_SOURCES:
            problems.append(
                f"strategy.compoundProfiles[{index}].source must be one of "
                f"{COMPOUND_PROFILE_SOURCES}, got {source!r}")
    return problems


def _validate_race_length(strategy: dict) -> list[str]:
    """§10.0's one invariant: no plan may finish after the race can end.

    A plan past `maxDurationS` is not a slow plan, it is an impossible one -
    the flag falls at the first line crossing after the clock, so the race can
    last at most the limit plus one lap. This is the check the section exists
    to make possible and it was never made.
    """
    length = strategy.get("raceLength")
    if not isinstance(length, dict):
        return []
    problems = []
    kind = length.get("type")
    if kind not in RACE_LENGTH_TYPES:
        problems.append(
            f"strategy.raceLength.type must be 'time' or 'laps', got {kind!r}")
    finish, ceiling = length.get("finishAtS"), length.get("maxDurationS")
    if isinstance(finish, (int, float)) and isinstance(ceiling, (int, float)):
        if finish > ceiling:
            problems.append(
                f"strategy.raceLength.finishAtS is {finish} against a "
                f"maxDurationS of {ceiling} - this plan describes a race that "
                f"cannot happen, not a slow one")
    return problems


def _validate_plan(strategy: dict) -> list[str]:
    plan = strategy.get("plan")
    if not isinstance(plan, dict):
        return []
    problems = []
    stints, laps = plan.get("stintLaps"), plan.get("laps")
    if isinstance(stints, list) and all(isinstance(n, int) for n in stints):
        if isinstance(laps, int) and sum(stints) != laps:
            problems.append(
                f"strategy.plan.stintLaps sums to {sum(stints)} against a "
                f"plan of {laps} laps - the stints and the distance disagree")
        stops = plan.get("stops")
        if isinstance(stops, int) and len(stints) != stops + 1:
            problems.append(
                f"strategy.plan has {len(stints)} stints against {stops} "
                f"stop(s) - a stop separates two stints")
    compounds = plan.get("compounds")
    if isinstance(compounds, list) and isinstance(stints, list) \
            and len(compounds) != len(stints):
        problems.append(
            f"strategy.plan names {len(compounds)} compound(s) for "
            f"{len(stints)} stint(s) - every stint runs on something")
    return problems


def _validate_corners(payload: dict, meta: dict) -> list[str]:
    corners = payload.get("corners")
    if corners is None:
        return []
    problems = []

    model = meta.get("cornerModel")
    if not isinstance(model, dict):
        problems.append(
            "meta.cornerModel is required whenever corners are present - "
            "without it the corner ids cannot be compared across sessions")
    else:
        if model.get("source") not in CORNER_MODEL_SOURCES:
            problems.append(
                f"meta.cornerModel.source must be one of {CORNER_MODEL_SOURCES}, "
                f"got {model.get('source')!r}")
        if not model.get("id"):
            problems.append("meta.cornerModel.id is required")

    for index, corner in enumerate(corners):
        where = corner.get("id") or f"corners[{index}]"
        if not corner.get("id"):
            problems.append(f"{where} has no id")
        samples = corner.get("samples")
        if not isinstance(samples, int) or samples < 1:
            problems.append(
                f"{where} must carry its sample count - a metric from two laps "
                f"and one from eleven are not the same claim")
    return problems


def _validate_laps(payload: dict) -> list[str]:
    laps = payload.get("laps")
    if laps is None:
        return []
    problems = []
    for index, lap in enumerate(laps):
        where = f"laps[{index}]"
        if not isinstance(lap.get("lap"), int):
            problems.append(f"{where}.lap must be an integer")
        time_ms = lap.get("timeMs")
        if not isinstance(time_ms, int):
            problems.append(
                f"{where}.timeMs must be integer milliseconds, never a "
                f"formatted string, got {time_ms!r}")
    return problems


def _validate_session(payload: dict) -> list[str]:
    """§5. Nothing here was checked at all before 1.5.

    Which is why a `fuelCapacityL` of 0 - a real value meaning electric, and
    also what the packet carries before the car has loaded - could sit above
    `laps[]` burning 7.28 L each, and why a `bestLapMs` that belongs to no
    counted lap could ship. The cross-checks against `laps[]` are the point:
    the two sections are built by different code and only agree by accident
    unless something says they must.
    """
    session = payload.get("session")
    if session is None:
        return []
    if not isinstance(session, dict):
        return ["session must be an object"]

    problems = []
    for key in ("lapsRun", "lapsCounted"):
        if not isinstance(session.get(key), int):
            problems.append(f"session.{key} is required and must be an integer")
    excluded = session.get("lapsExcluded")
    if not isinstance(excluded, list):
        problems.append("session.lapsExcluded is required, as a list")
        excluded = []

    capacity = session.get("fuelCapacityL")
    if capacity is not None and (not isinstance(capacity, (int, float))
                                 or capacity < 0):
        problems.append(
            f"session.fuelCapacityL must be litres or null, got {capacity!r}")

    laps = payload.get("laps")
    if isinstance(laps, list) and laps:
        counted = [lap for lap in laps if lap.get("valid")]
        if isinstance(session.get("lapsRun"), int) \
                and session["lapsRun"] != len(laps):
            problems.append(
                f"session.lapsRun is {session['lapsRun']} against "
                f"{len(laps)} laps[] entries")
        if isinstance(session.get("lapsCounted"), int) \
                and session["lapsCounted"] != len(counted):
            problems.append(
                f"session.lapsCounted is {session['lapsCounted']} against "
                f"{len(counted)} laps marked valid - the rack and the payload "
                f"must reach the same answer or a lap reads as counted on the "
                f"screen and excluded in the export")
        struck = sorted(lap["lap"] for lap in laps
                        if not lap.get("valid") and isinstance(lap.get("lap"), int))
        if sorted(n for n in excluded if isinstance(n, int)) != struck:
            problems.append(
                f"session.lapsExcluded is {sorted(excluded)} against "
                f"{struck} laps marked invalid")

        best = session.get("bestLapMs")
        times = {lap.get("timeMs") for lap in counted}
        if best is not None and times and best not in times:
            problems.append(
                f"session.bestLapMs is {best}, which is not the time of any "
                f"counted lap - a best taken from a struck lap is how a lap "
                f"boundary inside a pit transition became the session best")

    detail = session.get("lapsExcludedDetail")
    if detail is not None and not isinstance(detail, list):
        problems.append("session.lapsExcludedDetail must be a list")
        detail = []
    for index, entry in enumerate(detail or []):
        where = f"session.lapsExcludedDetail[{index}]"
        reason, source = entry.get("reason"), entry.get("source")
        if reason not in EXCLUSION_REASONS:
            problems.append(
                f"{where}.reason must be one of {EXCLUSION_REASONS}, "
                f"got {reason!r}")
        if source not in EXCLUSION_SOURCES:
            problems.append(
                f"{where}.source must be 'auto' or 'driver', got {source!r}")
        if isinstance(entry.get("lap"), int) and excluded \
                and entry["lap"] not in excluded:
            problems.append(
                f"{where} explains lap {entry['lap']}, which "
                f"session.lapsExcluded does not list as excluded")
    return problems


# The prefix, not the whole sentence: the app's own wording adds the
# unloaded-radius caveat, which is more useful than the contract's example and
# must not be refused for it. What is load-bearing is the word `derived`.
FINAL_GEAR_SOURCE_PREFIX = "derived:"
LIMITER_OBSERVED = "observed-at-rev-limiter"
LIMITER_NEVER_FIRED = "limiter never fired in this session"


def _validate_gearing(payload: dict) -> list[str]:
    """§9. Audited clean field by field, and checked by nothing.

    `matchesSheet: true` beside a contradictory `fittedFinalGear` was defect
    1.4/10 and the validator could not see it. The checks here are the ones
    that keep a derived number from reading as a measured one: every source
    string is required to agree with the field it describes.
    """
    gearing = payload.get("gearing")
    if gearing is None:
        return []
    if not isinstance(gearing, dict):
        return ["gearing must be an object"]

    problems = []
    ratios = gearing.get("fittedRatios")
    if ratios is not None:
        if not isinstance(ratios, list) or not ratios:
            problems.append(
                f"gearing.fittedRatios must be a non-empty list or null, "
                f"got {ratios!r}")
        elif any(not isinstance(r, (int, float)) or r <= 0 for r in ratios):
            problems.append(
                "gearing.fittedRatios must be positive dimensionless ratios")

    source = gearing.get("ratioSource")
    if source not in ("telemetry", None):
        problems.append(
            f"gearing.ratioSource is 'telemetry' or null and nothing else - "
            f"the app never reads ratios off the sheet into it, got {source!r}")
    if ratios is None and source is not None:
        problems.append(
            "gearing.ratioSource claims a source for ratios that are null")

    final = gearing.get("fittedFinalGear")
    final_source = gearing.get("finalGearSource")
    if final is not None and not str(final_source or "").startswith(
            FINAL_GEAR_SOURCE_PREFIX):
        problems.append(
            f"gearing.finalGearSource must begin "
            f"{FINAL_GEAR_SOURCE_PREFIX!r} whenever fittedFinalGear is "
            f"present - its whole job is to stop a derived number reading as "
            f"a measured one, got {final_source!r}")
    if final is None and final_source is not None:
        problems.append(
            "gearing.finalGearSource is set for a null fittedFinalGear")

    if gearing.get("matchesSheet") is not None \
            and not gearing.get("matchesSheetCovers"):
        problems.append(
            "gearing.matchesSheetCovers is required beside matchesSheet - the "
            "boolean does not cover the final drive and only this field says so")

    limiter = gearing.get("limiterRpm")
    limiter_source = gearing.get("limiterRpmSource")
    expected = LIMITER_OBSERVED if limiter is not None else LIMITER_NEVER_FIRED
    if limiter_source != expected:
        problems.append(
            f"gearing.limiterRpmSource must be {expected!r} for a "
            f"limiterRpm of {limiter!r}, got {limiter_source!r} - a null "
            f"limiter has to carry its own explanation")

    samples = gearing.get("samples")
    if not isinstance(samples, int) or samples < 0:
        problems.append(
            f"gearing.samples is required - a K from one lap is not a K from "
            f"nine, got {samples!r}")

    if "maxSpeedKph" not in gearing:
        for key in ("maxSpeedGear", "maxSpeedRpm", "topGearReachedLimiter"):
            if key in gearing:
                problems.append(
                    f"gearing.{key} is present with no maxSpeedKph - the three "
                    f"describe one frame and are omitted together")

    if "gearingConstantK" in gearing:
        constant_source = gearing.get("gearingConstantSource") or ""
        if not constant_source.startswith(("computed:", "extrapolated:")):
            problems.append(
                f"gearing.gearingConstantSource must begin 'computed:' or "
                f"'extrapolated:' - the two are never worded alike, got "
                f"{constant_source!r}")
        if not gearing.get("gearingConstantFinalGearSource"):
            problems.append(
                "gearing.gearingConstantFinalGearSource is required beside K - "
                "a K built on the derived final drive carries the "
                "unloaded-radius bias into every future gearbox")
    return problems


def _validate_wear(payload: dict) -> list[str]:
    wear = payload.get("wear")
    if not isinstance(wear, dict):
        return []
    problems = []
    if wear.get("channelAvailable") is not False:
        problems.append(
            "wear.channelAvailable must be false - GT7 exposes no tyre wear "
            "channel in any packet format")
    for index, reading in enumerate(wear.get("byDriverGauge") or []):
        for corner in ("fl", "fr", "rl", "rr", "worst"):
            value = reading.get(corner)
            if value is None:
                continue
            if not 0.0 <= value <= 1.0:
                problems.append(
                    f"wear.byDriverGauge[{index}].{corner} is a fraction "
                    f"consumed 0-1, got {value!r}")
        # A reading that names no corner is a row of nulls dressed as
        # evidence. Refusing is cheaper than having it read as a fresh tyre.
        if all(reading.get(corner) is None for corner in ("fl", "fr", "rl", "rr")):
            problems.append(
                f"wear.byDriverGauge[{index}] has no corner reading at all - "
                f"a gauge entry must name at least one of fl, fr, rl, rr")
    confidence = wear.get("modelConfidence")
    if confidence is not None and confidence not in WEAR_CONFIDENCES:
        problems.append(
            f"wear.modelConfidence must be measured, assumed or converted, "
            f"got {confidence!r}")

    problems.extend(_validate_wear_runs(payload, wear))
    problems.extend(_validate_wear_compounds(wear))
    problems.extend(_validate_wear_models(wear))
    return problems


def _run_ids(payload: dict) -> set[int]:
    return {run.get("id") for run in payload.get("runs") or []
            if isinstance(run.get("id"), int)}


def _validate_wear_runs(payload: dict, wear: dict) -> list[str]:
    """§6.1 and §8: every rate says what it had to assume to exist.

    The one that matters most is `measured`. It is conditional on two gauge
    readings inside one run or on the driver's own declaration, **and on
    nothing else** - a set called fresh because its opening temperatures fell
    in a band the app chose is an app-side heuristic, and four of six runs on
    the 11 Aug Monza data carried `measured` on exactly that, which promoted
    the whole payload to `modelConfidence: measured`.
    """
    problems = []
    known_runs = _run_ids(payload)

    for index, record in enumerate(wear.get("byRun") or []):
        where = f"wear.byRun[{index}]"
        run_id = record.get("runId")
        if known_runs and run_id not in known_runs:
            problems.append(
                f"{where}.runId is {run_id!r}, which is not a run in runs[]")
        method, confidence = record.get("method"), record.get("confidence")
        if method is not None and method not in WEAR_METHODS:
            problems.append(
                f"{where}.method must be one of the contract's stated "
                f"methods, got {method!r}")
        if confidence is not None and confidence not in WEAR_CONFIDENCES:
            problems.append(
                f"{where}.confidence must be measured, assumed or converted, "
                f"got {confidence!r}")
        if confidence == "measured" and method == METHOD_FRESH_OBSERVED:
            problems.append(
                f"{where} is 'measured' on a set called fresh by its opening "
                f"temperatures. That is an app-side band, not two readings and "
                f"not the driver's word, and §6.1 makes 'measured' conditional "
                f"on those two alone - it must be 'assumed' and carry "
                f"assumesFreshAtLap")
        if (method == METHOD_FRESH_AT_RUN_START
                and record.get("wearPerLap") is not None
                and record.get("assumesFreshAtLap") is None):
            problems.append(
                f"{where} assumes the set went on at the run's first lap and "
                f"does not say which lap that was")
        if record.get("wearPerLap") is None \
                and not record.get("wearPerLapUnavailable"):
            problems.append(
                f"{where}.wearPerLap is null with no reason - a missing rate "
                f"needs its sentence or it reads as an oversight")

    for index, reading in enumerate(wear.get("byDriverGauge") or []):
        run_id = reading.get("runId")
        if run_id is not None and known_runs and run_id not in known_runs:
            problems.append(
                f"wear.byDriverGauge[{index}].runId is {run_id!r}, which is "
                f"not a run in runs[]")
    return problems


def _validate_wear_compounds(wear: dict) -> list[str]:
    problems = []
    for code, entry in (wear.get("byCompound") or {}).items():
        where = f"wear.byCompound.{code}"
        stints, measured = entry.get("stints"), entry.get("stintsMeasured")
        if isinstance(stints, int) and isinstance(measured, int) \
                and measured > stints:
            problems.append(
                f"{where} claims {measured} measured stints out of {stints}")
        confidence = entry.get("confidence")
        if confidence is not None and confidence not in WEAR_CONFIDENCES:
            problems.append(
                f"{where}.confidence must be measured, assumed or converted, "
                f"got {confidence!r}")
    return problems


def _validate_wear_models(wear: dict) -> list[str]:
    """The three modelled sections, and what each has to name.

    Each of these was a figure that read as one thing and was another:
    a stint length off whichever run happened to be last, a temperature trend
    with no sample count, and the driver's last gauge reading from anywhere in
    the session published under `source: lap-time-model`.
    """
    problems = []

    stint = wear.get("modelledStintLaps")
    compounds = wear.get("byCompound") or {}
    if stint is not None and len(compounds) > 1 \
            and not wear.get("modelledStintCompound"):
        problems.append(
            f"wear.modelledStintLaps is {stint} over a session that ran "
            f"{len(compounds)} compounds and does not name which one it is "
            f"for. A driver planning that many laps on the wrong rubber runs "
            f"past the cliff - name it in modelledStintCompound")

    by_temp = wear.get("byTemp")
    if isinstance(by_temp, dict) and not isinstance(by_temp.get("samples"), int):
        problems.append(
            "wear.byTemp must carry its sample count - a trend over two laps "
            "and one over seventy are not the same claim")

    by_lap_time = wear.get("byLapTime")
    if isinstance(by_lap_time, dict):
        phase = by_lap_time.get("phase")
        if phase is not None and phase not in WEAR_PHASES:
            problems.append(
                f"wear.byLapTime.phase must be flat, linear or cliff, "
                f"got {phase!r}")
        samples = by_lap_time.get("samples")
        if by_lap_time.get("degradationMsPerLap") is not None:
            if not isinstance(samples, int):
                problems.append(
                    "wear.byLapTime carries a slope with no sample count")
            elif samples < MIN_DEGRADATION_SAMPLES:
                problems.append(
                    f"wear.byLapTime is fitted over {samples} laps, under the "
                    f"{MIN_DEGRADATION_SAMPLES} a run needs before a slope "
                    f"describes the tyre rather than the noise")
            if by_lap_time.get("fittedRunId") is None:
                problems.append(
                    "wear.byLapTime carries a slope and does not name the run "
                    "it was fitted in - nothing may be fitted across a refuel")
        # `phase` and `estimatedFractionAtEnd` come off the driver's gauge, not
        # off the slope, and sit in a section stamped `lap-time-model`. Under
        # that heading they read as an output of the fit.
        if by_lap_time.get("estimatedFractionAtEnd") is not None \
                and not by_lap_time.get("estimatedFractionSource"):
            problems.append(
                "wear.byLapTime.estimatedFractionAtEnd is a gauge reading "
                "sitting under source: lap-time-model and must carry its own "
                "estimatedFractionSource, or be read as an output of the fit")
    return problems


# Every key the contract defines, by path. List indices collapse to `[]`, and
# a path that is absent from this map is not descended into - `setup.values`,
# `rangeRecord.r`, `wear.byCompound` and `corners[].surfaceMix` are keyed by
# vocabulary or by compound code rather than by field name.
#
# **The point is that an undeclared key is refused rather than shipped.**
# Fifteen were shipping: several were useful, and the fix for those was to
# specify them (§16.4), not to drop them. What this stops is the next one
# arriving unannounced, where a reader has to guess conservatively at a field
# nothing documents.
KNOWN_KEYS: dict[str, frozenset[str]] = {
    "": frozenset({
        "format", "meta", "setup", "rangeRecord", "session", "laps", "runs",
        "corners", "wear", "gearing", "strategy", "derived", "notes"}),
    "meta": frozenset({
        "car", "carCategory", "circuit", "date", "sessionType", "packet",
        "appVersion", "gameVersion", "compound", "compoundsRun", "assists",
        "multipliers", "cornerModel", "practiceIntent", "practiceMode",
        "rehearsal"}),
    "meta.compound": frozenset({"front", "rear"}),
    "meta.assists": frozenset({"abs", "tcs", "countersteer"}),
    "meta.multipliers": frozenset({"tyreWear", "fuel"}),
    "meta.cornerModel": frozenset({"source", "id", "version"}),
    "setup": frozenset({
        "sheetName", "purpose", "values", "gears", "performance", "build",
        "driverChanges"}),
    "setup.performance": frozenset({
        "powerRestrictor", "ecuOutput", "ballastKg", "ballastPosition"}),
    # `drivetrain`, `weightBalance`, `torqueKgfm` and `displacementCc` joined in
    # 1.7. They are read off the car's own screen with the rest of the sheet and
    # were being emitted and then refused - so the first setup record this
    # project ever verified against the game could not be exported.
    "setup.build": frozenset({"bhp", "weightKg", "pp", "drivetrain",
                              "weightBalance", "torqueKgfm",
                              "displacementCc"}),
    "setup.driverChanges[]": frozenset({"fromLap", "key", "from", "to"}),
    "rangeRecord": frozenset({
        "car", "measuredDate", "gameVersion", "verified", "r"}),
    "session": frozenset({
        "lapsRun", "lapsCounted", "lapsExcluded", "lapsExcludedDetail",
        "fuelUsedPerLapL", "fuelCapacityL", "bestLapMs", "medianLapMs",
        "lapTimeStdDevMs", "greenLapRefMs"}),
    "session.lapsExcludedDetail[]": frozenset({
        "lap", "reason", "source", "note"}),
    "laps[]": frozenset({
        "lap", "timeMs", "valid", "fuelStartL", "fuelEndL", "fuelMap",
        "tyreTempMeanC", "tyreTempMaxC", "offTrackCount"}),
    "runs[]": frozenset({
        "id", "firstLap", "lastLap", "laps", "lapsCounted", "fuelStartL",
        "fuelEndL", "fuelDeltaL", "refuelledBefore", "compound", "tyresFresh",
        "tyresFreshSource", "tyresFreshDeclared", "tyresFreshObserved",
        "tyresFreshDisagreement", "tyresChangedAtStop"}),
    "corners[]": frozenset({
        "id", "name", "samples", "entrySpeedKph", "minSpeedKph",
        "exitSpeedKph", "brakePeakPct", "brakePointM", "brakePointSamples",
        "trailBrakeMs", "trailBrakeSamples", "steerPeakDeg", "steerPeakNorm",
        "steerPeakSamples", "throttleOnPct", "throttleOnSamples",
        "yawDeficitPct", "yawDeficitSamples", "yawDeficitFrames",
        "meanHeaveMm", "meanHeaveSamples",
        "timeLossVsBestMs", "consistencyMs", "gearMin", "gearAtApex",
        "gearAtExit", "shiftsInCorner", "upshiftRpm", "upshiftRpmSamples",
        "suspHeightMinMm", "surfaceMix",
        "flags", "flagLaps", "flagThresholdLaps"}),
    "wear": frozenset({
        "channelAvailable", "byDriverGauge", "byCorner", "byRun", "byCompound",
        "byLapTime", "byTemp", "gaugePinned", "modelledStintLaps",
        "modelledStintCompound", "wearMeasuredAtRaceMultiplier",
        "wearMultiplier", "modelBasis", "modelConfidence",
        "modelConfidenceBasis"}),
    "wear.byDriverGauge[]": frozenset({
        "lap", "runId", "fl", "fr", "rl", "rr", "worst", "worstCorner",
        "source"}),
    "wear.byCorner": frozenset({
        "atLap", "worstCorner", "worst", "frontMinusRear", "leftMinusRight",
        "source"}),
    "wear.byRun[]": frozenset({
        "runId", "compound", "firstLap", "lastLap", "readingLap", "reading",
        "readingCorner", "wearPerLap", "wearPerLapUnavailable", "method",
        "confidence", "source", "assumesFreshAtLap", "degradationMsPerLap",
        "degradationSamples"}),
    "wear.byLapTime": frozenset({
        "refLapMs", "degradationMsPerLap", "degradationUnavailable",
        "fittedRunId", "fittedOverLaps", "samples", "fuelDeltaL", "fuelNetted",
        "fuelNettedNote", "runsDisagree", "phase", "estimatedFractionAtEnd",
        "estimatedFractionSource", "source", "confidence"}),
    "wear.byTemp": frozenset({
        "frontRearAsymmetryC", "trendCPerLap", "samples", "source",
        "confidence"}),
    "gearing": frozenset({
        "fittedRatios", "fittedFinalGear", "ratioSource", "finalGearSource",
        "finalGearSheet", "finalGearVsSheetPct", "rollingRadiusImpliedM",
        "matchesSheet", "matchesSheetCovers", "gearboxChangedMidSession",
        "limiterRpm", "limiterGear", "limiterRpmSource", "samples",
        "maxSpeedKph", "maxSpeedGear", "maxSpeedRpm", "topGearReachedLimiter",
        "gearingConstantK", "gearingConstantSource", "gearingConstantFinalGear",
        "gearingConstantFinalGearSource", "gearingConstantSamples",
        "topGearSpeedAtLimiterKph"}),
    "strategy": frozenset({
        "plan", "raceLength", "bindingConstraint", "compoundProfiles",
        "compoundCrossover", "assumptions", "callsMade", "outcome"}),
    "strategy.plan": frozenset({
        "stops", "laps", "stintLaps", "compounds", "pitLap"}),
    "strategy.raceLength": frozenset({
        "type", "minutes", "extraTimeS", "lapsAtThisPace", "maxDurationS",
        "finishAtS", "startHour", "timeMultiplier", "note"}),
    "strategy.assumptions": frozenset({
        "pitLossS", "pitLossSource", "fuelPerLapL", "fuelWeightSPerLPerLap",
        "fuelWeightSource", "compoundDeltaSPerLap", "refuelRateLps",
        "refuelRateSource", "mandatoryStops"}),
    "strategy.compoundProfiles[]": frozenset({
        "compound", "paceDeltaSPerLap", "paceBasis", "wearPerLap", "source",
        "lapsMeasured", "stintsMeasured", "longestStintLaps", "tyreWindow",
        "windowQualification"}),
    "strategy.compoundProfiles[].tyreWindow": frozenset({
        "meanC", "perCornerC", "band", "lapsSampled", "lapsInWindow",
        "inWindow", "windowC", "windowMeasured", "windowSource",
        "hottestCorner", "source"}),
    "strategy.compoundCrossover": frozenset({
        "winner", "alternative", "stopsSaved", "alternativePaceDeltaSPerLap",
        "breakEvenSPerLap", "restsOnAssumption", "outsideTyreWindow",
        "verdict", "source"}),
    "strategy.callsMade[]": frozenset({
        "lap", "call", "reason", "accepted", "disposition", "confidence"}),
    "derived": frozenset({
        "thresholds", "steerSource", "steerRotationDeg", "steerRotationSource",
        "bottomingRefMm", "bottomingRefSource", "observedMinHeightMm",
        "understeerIndexByCorner", "balanceDriftPerLap", "incidents"}),
}


def _validate_known_keys(payload: dict) -> list[str]:
    """Anything the contract does not define, wherever it appears."""
    problems: list[str] = []

    def walk(node, path: str) -> None:
        if isinstance(node, dict):
            allowed = KNOWN_KEYS.get(path)
            for key, value in node.items():
                if allowed is not None and key not in allowed:
                    problems.append(
                        f"{path + '.' if path else ''}{key} is not defined by "
                        f"{FORMAT} - specify it in the contract or drop it, "
                        f"because a reader has to read an undocumented field "
                        f"conservatively")
                    continue
                walk(value, f"{path}.{key}" if path else key)
        elif isinstance(node, list):
            for value in node:
                walk(value, f"{path}[]")

    walk(payload, "")
    return problems


def to_json(payload: dict, *, indent: int = 2) -> str:
    """Serialise, refusing rather than emitting something that would be misread."""
    problems = validate(payload)
    if problems:
        raise ExportRefused(
            "refusing to export - the payload would be misread:\n  - "
            + "\n  - ".join(problems))
    return json.dumps(payload, indent=indent, ensure_ascii=False)
