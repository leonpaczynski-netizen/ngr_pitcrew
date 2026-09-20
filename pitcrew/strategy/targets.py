"""The lap time and the burn a plan asks for, lap by lap.

The driver, 16 Sep 2026: *"In a race with a plan we should have a lap time for
each compound and a fuel delta per lap we are trying to hit each lap based on
the optimal plan we have made. These figures should be displayed on the
dashboard and spoken by George if we are on target or not"* - and *"make sure
Ludo passes the lap time for each compound and fuel through to George."*

### What the plan carries

One block, `targets`, beside the stints:

    "targets": {
      "reference_load_l": 45.0,              # optional, applies to every entry
      "compounds": {
        "RM": {"lap_time_ms": 101200,        # a clean full-revs lap, fresh set
               "save_lap_time_ms": 101700,   # the same on the fuel-saving beep
               "wear_per_lap": 0.052,        # the set's wear rate
               "reference_load_l": 45.0}     # fuel aboard that lap time carried
      }
    }

Every field is optional at the door. **Whatever the author leaves out is filled
from practice at `stamp`, and says so**: each filled field carries a
`*_source` of `practice` beside it, and an author's own figure `author`. A
field that practice could not answer either is stored as None with its source
- missing, never zero (rule 3) - and George gives no target that rests on it.

**The plan's burn is not copied here.** It is already on the plan:
`fuel_burns` (save and full) where the author measured them, else
`expects.expected_fuel_per_lap_l`. A second copy of the PLAN's figure would be
a second value.

**But this race's own burn is a different quantity, and it is installed beside
it** (20 Sep 2026). This module used to hold the plan's burn as the sole
reference and cite CLAUDE.md §1a for it. That citation was misapplied: §1a is
about the *setup record* - a declared input that must have exactly one copy -
and a measured burn is not that. Rule 1 makes a measurement primary evidence
and rule 4 gives it a sample count.

What it cost, measured: at Bathurst on 20 Sep 2026 the race ran map 3 by the
driver's own last-minute choice and burned 8.2-8.5 L/lap against a plan costed
at 10.625. The race's own burn was installed for every fuel call on lap 7 and
the per-lap target was still judging him against 10.625 on lap 28 - all 28
`target:` lines of the race read `against 10.625 L`. "Burn 2.2 litres under"
on lap 25 said nothing about lap 25; it restated the plan's error. That is
rule 10's latch: a reference that disagrees with everything is the thing that
is wrong.

So there are two figures and they never merge (rule 13):

* `burn_full_l` / `burn_save_l` - **what the plan asked for**, set once from
  the plan and never written again.
* `measured_burn_l` - **what this race is burning**, handed over by the
  coordinator from the same expression that sizes every other fuel call
  (`RaceState.fuel_per_lap_l`, with `fuel_burn_basis` and `fuel_burn_laps`
  beside it), so the target and the fill cannot disagree about one number
  (rule 12).

`for_lap` reports against the measured burn once it is installed and **names
which one it used** (`LapTarget.burn_source`) with the laps behind it
(`LapTarget.burn_laps`), and carries the plan's figure alongside as
`planned_burn_l` so the two are always both readable. Nothing overwrites
anything: clearing the measured burn - which is what happens if the race's own
burn is ever retired - puts the target straight back on the plan's figure.

### What a lap's target is

`planned_lap_s`, the optimiser's own expression for one lap - pace, the set's
wear at this lap on it, the fuel aboard - evaluated for the lap being driven:
the compound on the car, whether the beep is on its saving points, how many
laps the set has done, and the fuel measured at the start of the lap. The fuel
term is taken against the load the lap time was set at, so a lap time from a
half tank is not charged for fuel it already carried.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from pitcrew.strategy.model import FUEL_WEIGHT_S_PER_L_PER_LAP, planned_lap_s

TARGETS_KEY = "targets"

# **What a lap's burn target was measured against, said out loud.** Two
# references for one word is rule 13, and "Burn 2.2 litres under" meant the
# plan's 10.625 all through a race run at 8.4.
#
# `BURN_BASIS_RACE` is word for word `refuel._burn_words`': the same figure
# said in two places has to be said the same way. The other one deliberately
# is NOT - the box says "the practice burn" because before a race burn is
# installed `RaceState.fuel_per_lap_l` holds `build_inputs`' practice figure,
# while the target's fallback is the plan's own `fuel_burns.full`. Those are
# two numbers reached by two routes and they can differ, so they get two
# names; that is rule 13 kept, not broken.
BURN_BASIS_PLAN = "the plan"
BURN_BASIS_RACE = "this race's burn"

SOURCE_AUTHOR = "author"
SOURCE_PRACTICE = "practice"
# A wear rate the model inherited from the reference compound because this one
# was never gauge-read (`RaceInputs.profile_for`). Rule 5: not "practice".
SOURCE_ASSUMED = "assumed"
SOURCES = (SOURCE_AUTHOR, SOURCE_PRACTICE, SOURCE_ASSUMED)

# The fields an author may write on a compound, and the plausible range of
# each. Bounds are wide on purpose: they exist to refuse a unit mistake (a lap
# time in seconds, a wear rate in percent), not to judge a figure.
LAP_TIME_MS = (10_000, 1_800_000)
COMPOUND_FIELDS = {
    "lap_time_ms": LAP_TIME_MS,
    "save_lap_time_ms": LAP_TIME_MS,
    "wear_per_lap": (0.0, 1.0),
    "reference_load_l": (0.0, 200.0),
}
TOP_FIELDS = {"reference_load_l": (0.0, 200.0),
              "fuel_weight_s_per_l_per_lap": (0.0, 0.1)}


def _number(value) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    value = float(value)
    return value if math.isfinite(value) else None


def target_problems(plan) -> list[str]:
    """Every problem with a plan's `targets` block, in words.

    **Read by the door and the gate** (`Handover.validate` and `certify`), the
    same arrangement as `fuel_plan_problems`, so a plan cannot pass one and
    fail the other. An unknown key is refused rather than ignored: a
    `lap_time` typed for `lap_time_ms` would store clean and give no target,
    which from the driver's seat is a plan that never asked for a lap time.
    """
    if not isinstance(plan, dict) or TARGETS_KEY not in plan:
        return []
    block = plan[TARGETS_KEY]
    if not isinstance(block, dict):
        return ["targets is not a set of fields"]
    problems: list[str] = []
    for key in sorted(set(block) - set(TOP_FIELDS) - {"compounds"}):
        problems.append(f"targets.{key} is not a field targets carries "
                        f"({', '.join(['compounds', *TOP_FIELDS])})")
    for key, (low, high) in TOP_FIELDS.items():
        if block.get(key) is not None:
            got = _number(block[key])
            if got is None or not low <= got <= high:
                problems.append(f"targets.{key} is {block[key]!r}, not a "
                                f"figure between {low:g} and {high:g}")
    compounds = block.get("compounds")
    if compounds is None:
        return problems
    if not isinstance(compounds, dict):
        return problems + ["targets.compounds is not a set of compounds"]
    allowed = set(COMPOUND_FIELDS) | {f"{k}_source" for k in COMPOUND_FIELDS}
    for code, entry in compounds.items():
        where = f"targets.compounds.{code}"
        if not isinstance(entry, dict):
            problems.append(f"{where} is not a set of fields")
            continue
        for key in sorted(set(entry) - allowed):
            problems.append(f"{where}.{key} is not a field a compound target "
                            f"carries ({', '.join(COMPOUND_FIELDS)})")
        for key, (low, high) in COMPOUND_FIELDS.items():
            if entry.get(key) is None:
                continue
            got = _number(entry[key])
            if got is None or not low <= got <= high:
                problems.append(f"{where}.{key} is {entry[key]!r}, not a "
                                f"figure between {low:g} and {high:g}")
            source = entry.get(f"{key}_source")
            if source is not None and source not in SOURCES:
                problems.append(f"{where}.{key}_source is {source!r}, not one "
                                f"of {', '.join(SOURCES)}")
        full, save = (_number(entry.get("lap_time_ms")),
                      _number(entry.get("save_lap_time_ms")))
        if full is not None and save is not None and save < full:
            # The shape `fuel_burns` refuses: a saving lap faster than a full
            # one is two columns transposed, and silent at the wheel.
            problems.append(f"{where}.save_lap_time_ms ({save:.0f}) is quicker "
                            f"than lap_time_ms ({full:.0f}) - a fuel-saving "
                            f"lap cannot be the faster one")
    return problems


def desk_target_problems(plan) -> list[str]:
    """What a plan from the desk must pass so George can judge every lap.

    **Refused at the desk's doors, not warned about** (the driver, 16 Sep
    2026: *"so it's never missed and fuel burn per lap for fuel saving strat
    must be passed"*). A warning was tried first and it is the shape that
    fails: a target filled from practice looks exactly like Ludo's on the
    board and in George's voice, so a missed figure is invisible at the only
    moment it could be fixed. Read by `Handover.validate` (so
    `write_strategy` and the CLI) and by `propose_strategy`; never by
    `certify`, because the app's own optimiser writes no desk figures and
    its plans are priced from practice by design.

    Required:

    * `targets.compounds.<code>.lap_time_ms` for every compound a stint runs;
    * `fuel_burns.full`, the burn per lap at full revs;
    * on a strategy with any fuel-save stint, `fuel_burns.save` (already
      refused by name in `handover.fuel_plan_problems`) and
      `targets.compounds.<code>.save_lap_time_ms` for every compound a
      saving stint runs.
    """
    if not isinstance(plan, dict):
        return []
    stints = [s for s in (plan.get("stints") or []) if isinstance(s, dict)]
    block = plan.get(TARGETS_KEY)
    compounds = (block.get("compounds") if isinstance(block, dict) else None)
    compounds = compounds if isinstance(compounds, dict) else {}
    problems: list[str] = []
    asked_full: list[str] = []
    asked_save: list[str] = []
    for index, stint in enumerate(stints, 1):
        code = stint.get("compound")
        if not isinstance(code, str) or not code:
            problems.append(f"stint {index} names no compound, so no target "
                            f"lap time can be keyed to it")
            continue
        entry = compounds.get(code)
        entry = entry if isinstance(entry, dict) else {}
        if entry.get("lap_time_ms") is None and code not in asked_full:
            asked_full.append(code)
            problems.append(
                f"no target lap time for {code}: pass targets.compounds."
                f"{code}.lap_time_ms - George judges every {code} lap "
                f"against it")
        if (stint.get("fuel_save") is True
                and entry.get("save_lap_time_ms") is None
                and code not in asked_save):
            asked_save.append(code)
            problems.append(
                f"stint {index} is a fuel-save stint on {code} with no "
                f"fuel-saving target lap time: pass targets.compounds.{code}"
                f".save_lap_time_ms - George judges its laps against it")
    # Missing only: a malformed `fuel_burns` is named by `fuel_plan_problems`.
    burns = plan.get("fuel_burns")
    if burns is None or (isinstance(burns, dict) and "full" not in burns):
        problems.append(
            "no burn per lap: pass fuel_burns.full (and fuel_burns.save for "
            "a fuel-saving strategy) - George judges every lap's burn "
            "against it")
    return problems


def _practice_lap_ms(inputs, code: str) -> int | None:
    """The practice lap on this compound, the way the optimiser prices it:
    the reference median plus the compound's measured pace delta. None where
    the delta was never comparable - `CompoundProfile.pace_known`."""
    base = getattr(inputs, "lap_time_ms", None)
    if not base:
        return None
    if code == getattr(inputs, "evidence_compound", None):
        return int(base)
    profile = (getattr(inputs, "compound_profiles", None) or {}).get(code)
    if profile is None or not profile.pace_known:
        return None
    return int(round(base + profile.pace_delta_s * 1000.0))


def fill_targets(plan: dict, inputs) -> dict:
    """The plan's `targets`, with every gap filled from practice and sourced.

    **An author's figure is never replaced**, and neither is a field that was
    filled before: the presence of its `*_source` says it has been answered,
    even where the answer was None. That is `stamp`'s rule for `expects` -
    re-stamping on approval must not swap what the plan was written against
    for today's figures.
    """
    supplied = plan.get(TARGETS_KEY) if isinstance(plan, dict) else None
    block = dict(supplied) if isinstance(supplied, dict) else {}
    top_load = _number(block.pop("reference_load_l", None))
    compounds = {code: dict(entry) for code, entry in
                 (block.get("compounds") or {}).items()
                 if isinstance(entry, dict)}
    for stint in plan.get("stints") or []:
        code = stint.get("compound") if isinstance(stint, dict) else None
        if isinstance(code, str) and code:
            compounds.setdefault(code, {})

    for code, entry in compounds.items():
        authored_lap = False
        for key in ("lap_time_ms", "save_lap_time_ms"):
            if f"{key}_source" in entry:
                authored_lap |= entry[f"{key}_source"] == SOURCE_AUTHOR
                continue
            if entry.get(key) is not None:
                entry[f"{key}_source"] = SOURCE_AUTHOR
                authored_lap = True
            elif inputs is None:
                # Nothing to fill from: left unanswered, so the next stamp
                # with evidence in hand can answer it.
                continue
            elif key == "lap_time_ms":
                entry[key] = _practice_lap_ms(inputs, code)
                entry[f"{key}_source"] = SOURCE_PRACTICE
            else:
                # **No practice figure for a saving lap exists.** The practice
                # median is a full-revs lap; handing it to a fuel-save stint
                # would judge every short-shifted lap half a second slow.
                entry[key] = None
                entry[f"{key}_source"] = SOURCE_PRACTICE
        if "wear_per_lap_source" not in entry:
            if entry.get("wear_per_lap") is not None:
                entry["wear_per_lap_source"] = SOURCE_AUTHOR
            elif inputs is not None:
                profile = inputs.profile_for(code)
                entry["wear_per_lap"] = profile.wear_per_lap
                entry["wear_per_lap_source"] = (
                    SOURCE_PRACTICE if profile.is_measured else SOURCE_ASSUMED)
        if "reference_load_l_source" not in entry:
            if entry.get("reference_load_l") is not None:
                entry["reference_load_l_source"] = SOURCE_AUTHOR
            elif top_load is not None:
                entry["reference_load_l"] = top_load
                entry["reference_load_l_source"] = SOURCE_AUTHOR
            elif authored_lap:
                # **Practice's load only under practice's lap time.** The load
                # is a property of the laps a time was taken from, and an
                # author's lap time was not taken from these. None, and the
                # target then carries no fuel term (see `for_lap`).
                entry["reference_load_l"] = None
                entry["reference_load_l_source"] = SOURCE_AUTHOR
            elif inputs is not None:
                entry["reference_load_l"] = getattr(
                    inputs, "fuel_reference_load_l", None)
                entry["reference_load_l_source"] = SOURCE_PRACTICE
    out = {"compounds": compounds}
    weight = _number(block.get("fuel_weight_s_per_l_per_lap"))
    if weight is None:
        weight = (getattr(inputs, "fuel_weight_s_per_l_per_lap", None)
                  if inputs is not None else None)
    out["fuel_weight_s_per_l_per_lap"] = (
        weight if weight is not None else FUEL_WEIGHT_S_PER_L_PER_LAP)
    return out


def targets_answered(plan) -> bool:
    """Whether every planned compound's target fields have been answered, so
    `stamp` knows if it needs the evidence to fill them."""
    if not isinstance(plan, dict):
        return True
    block = plan.get(TARGETS_KEY)
    compounds = (block.get("compounds") if isinstance(block, dict) else None) or {}
    if not isinstance(block, dict) or "fuel_weight_s_per_l_per_lap" not in block:
        return False
    for stint in plan.get("stints") or []:
        code = stint.get("compound") if isinstance(stint, dict) else None
        if not isinstance(code, str) or not code:
            continue
        entry = compounds.get(code)
        if not isinstance(entry, dict) or any(
                f"{key}_source" not in entry for key in COMPOUND_FIELDS):
            return False
    return True


@dataclass(frozen=True)
class LapTarget:
    """What one lap is asked to be. None in either half is no target."""
    lap_ms: int | None
    burn_l: float | None
    compound: str | None
    saving: bool
    # How many laps the set had done at the end of this lap, 1 on its first.
    lap_on_set: int
    # Whose figure the lap time rests on - `author` or `practice` - or None.
    lap_source: str | None = None
    # Why there is no lap time, in words, where there is none.
    why_no_lap: str | None = None
    # **Which burn `burn_l` is** - `BURN_BASIS_PLAN` or `BURN_BASIS_RACE` -
    # or None where there is no burn target at all. Never absent while
    # `burn_l` is set: a delta with no stated reference is rule 13.
    burn_source: str | None = None
    # Green laps behind `burn_l` where it is this race's own (rule 4). None
    # on the plan's figure, whose sample count is the plan's own `expects`
    # and is not a count of laps run today.
    burn_laps: int | None = None
    # **What the plan asked for, always** - kept beside the figure actually
    # used so the two can be shown together and never merge into one word.
    planned_burn_l: float | None = None


@dataclass(frozen=True)
class CompoundTarget:
    lap_time_ms: float | None
    save_lap_time_ms: float | None
    wear_per_lap: float | None
    reference_load_l: float | None
    lap_source: str | None
    save_source: str | None


class PlanTargets:
    """The read half, for the race. Built once at arming from the stored plan."""

    def __init__(self, compounds: dict[str, CompoundTarget], *,
                 fuel_weight: float, burn_full_l: float | None,
                 burn_save_l: float | None) -> None:
        self.compounds = compounds
        self.fuel_weight = fuel_weight
        # The plan's, set once here and never written again.
        self.burn_full_l = burn_full_l
        self.burn_save_l = burn_save_l
        # This race's own, installed by `install_measured_burn` and cleared
        # by it. None until the race has shown one.
        self.measured_burn_l: float | None = None
        self.measured_burn_laps: int | None = None
        self.measured_burn_basis: str | None = None

    def install_measured_burn(self, burn_l: float | None, *,
                              laps: int | None = None,
                              basis: str | None = None) -> bool:
        """This race's own burn, beside the plan's. True when it moved.

        **Handed over, never derived here.** The caller passes the figure
        that is already sizing every other fuel call - the coordinator's
        `RaceState.fuel_per_lap_l` with its `fuel_burn_basis` and
        `fuel_burn_laps` - so the per-lap target and the fill are two readings
        of one number rather than two numbers (rule 12).

        **And it can be retired** (rule 10). `None` puts the target back on
        the plan's figure, which is what must happen if the race's own burn is
        ever withdrawn: this is a reference that judges every lap, and a
        reference nothing can clear is the ratchet.

        A non-positive burn or a burn with no laps behind it is not a burn and
        is refused rather than clamped (rules 3 and 9).

        **The return value is the change of REFERENCE, not of figure.** The
        race's own burn moves a hundredth of a litre most crossings and the
        coordinator already logs every one of those (`burn installed on lap
        N`); what is news is the target moving between the plan's figure and
        the race's, because that is the moment "Burn 2.2 litres under" starts
        meaning something else. Returning True on every wobble would log
        twenty-two lines a race and retire the stint average on each of them.
        """
        got = _number(burn_l)
        if got is None or got <= 0.0 or not laps or laps <= 0:
            got, laps, basis = None, None, None
        rebased = (got is None) != (self.measured_burn_l is None)
        self.measured_burn_l = got
        self.measured_burn_laps = int(laps) if laps else None
        self.measured_burn_basis = basis
        return rebased

    @classmethod
    def from_plan(cls, plan) -> "PlanTargets | None":
        """None where the plan carries nothing a lap could be judged against.

        **A malformed block is no targets, not a crash on the grid.** The
        doors refuse one; a row stored before they did is read as absent.
        """
        if not isinstance(plan, dict):
            return None
        block = plan.get(TARGETS_KEY)
        compounds: dict[str, CompoundTarget] = {}
        weight = FUEL_WEIGHT_S_PER_L_PER_LAP
        if isinstance(block, dict) and not target_problems(plan):
            got = _number(block.get("fuel_weight_s_per_l_per_lap"))
            if got is not None:
                weight = got
            for code, entry in (block.get("compounds") or {}).items():
                compounds[code] = CompoundTarget(
                    lap_time_ms=_number(entry.get("lap_time_ms")),
                    save_lap_time_ms=_number(entry.get("save_lap_time_ms")),
                    wear_per_lap=_number(entry.get("wear_per_lap")),
                    reference_load_l=_number(entry.get("reference_load_l")),
                    lap_source=entry.get("lap_time_ms_source"),
                    save_source=entry.get("save_lap_time_ms_source"))
        burns = plan.get("fuel_burns")
        full = save = None
        if isinstance(burns, dict):
            full, save = _number(burns.get("full")), _number(burns.get("save"))
        if full is None:
            full = _number((plan.get("expects") or {}).get(
                "expected_fuel_per_lap_l"))
        if not compounds and full is None and save is None:
            return None
        return cls(compounds, fuel_weight=weight, burn_full_l=full,
                   burn_save_l=save)

    def for_lap(self, *, compound: str | None, saving: bool, lap_on_set: int,
                fuel_at_start_l: float | None) -> LapTarget:
        """What this lap is asked to be, and against whose burn.

        **The burn half reports against this race's own figure the moment one
        is installed**, and names it. The measured burn is already filed under
        the beep column being driven (`expectations.current_fuel_basis` reads
        the column), so it stands in for whichever of the plan's two columns
        this lap is on - which is the same figure the fill and the box call
        are using at that instant.
        """
        planned = self.burn_save_l if saving else self.burn_full_l
        burn, burn_laps = planned, None
        source = BURN_BASIS_PLAN if planned is not None else None
        if self.measured_burn_l is not None:
            burn = self.measured_burn_l
            burn_laps = self.measured_burn_laps
            source = BURN_BASIS_RACE
        entry = self.compounds.get(compound) if compound else None
        why = None
        lap_ms = lap_source = None
        if compound is None:
            why = "compound not known"
        elif entry is None:
            why = f"no {compound} target on the plan"
        else:
            base = entry.save_lap_time_ms if saving else entry.lap_time_ms
            lap_source = entry.save_source if saving else entry.lap_source
            if base is None:
                why = (f"no fuel-save {compound} target" if saving
                       else f"no {compound} target on the plan")
            else:
                onboard = None
                if (fuel_at_start_l is not None
                        and entry.reference_load_l is not None):
                    onboard = fuel_at_start_l - entry.reference_load_l
                seconds = planned_lap_s(max(0, lap_on_set - 1), base / 1000.0,
                                        entry.wear_per_lap, onboard,
                                        self.fuel_weight)
                lap_ms = int(round(seconds * 1000.0))
        return LapTarget(lap_ms=lap_ms, burn_l=burn, compound=compound,
                         saving=saving, lap_on_set=lap_on_set,
                         lap_source=lap_source if lap_ms is not None else None,
                         why_no_lap=why,
                         burn_source=source if burn is not None else None,
                         burn_laps=burn_laps if burn is not None else None,
                         planned_burn_l=planned)
