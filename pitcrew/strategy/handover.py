"""The plan Ludo writes and George runs, and the bounds George may move inside.

**Ludo plans; George executes.** Ludo is the engineer at the desk and works
before the green and after the flag; George is the app's voice in the car. The
driver races in VR, so Ludo cannot be the live voice and George cannot be the
one who decides the strategy - each is the only one who can do its half.

That split needs two artefacts and not one. **A plan alone is not enough**,
because a race stops matching its plan and something has to decide what happens
next. Left to re-run the optimiser mid-race, George is silently re-planning
against Ludo's intent - which is how a driver ends up hearing a call nobody
would have approved. So the plan comes with a **playbook**: the adaptations
George may make on his own, each with a trigger, an action and a limit.

Anything outside the playbook is George reporting rather than deciding, and
saying *"the plan no longer fits and I cannot fix it from here"* is a useful,
honest call - not a failure.

### What is deliberately NOT here

**The optimiser is not removed.** `recommend()` still exists and still ranks
plans, for two reasons that outlive the handover: `certify` needs something to
check a proposed plan against, and a plan arriving as prose cannot be trusted to
have done its own arithmetic - `CLAUDE.md` §5 is explicit that a plan from the
engineer the driver is talking to is exactly the case the gate exists for. What
changes is which one is authoritative: Ludo's plan is the plan, and the app's is
the fallback and the comparison.
"""
from __future__ import annotations

import pathlib
from dataclasses import dataclass, field

# The triggers George is allowed to act on alone. A playbook entry naming
# anything else is refused rather than ignored, because a rule the driver
# believes is armed and which silently is not is worse than no rule.
#
# **`safety_car` was retired on 7 Sep 2026.** GT7 broadcasts no flag state in
# any packet format and the league has no lobby setting for one, so it was a
# trigger that could never fire, listed under *unhandled* on every card as if
# a rule were missing. `tyre_short` joined the same day: the wear cliff's
# "Box this lap" adds a stop when none was planned, and an added stop is one
# of the structural four, so it needs a trigger the desk can grant it under.
TRIGGERS = (
    "fuel_short",        # the tank will not reach the flag or the next stop
    "fuel_long",         # more fuel aboard than the plan needs
    "stop_missed",       # the planned pit lap has gone by
    "incident",          # time lost to an off, a spin or contact
    "rain",              # the surface is wet and the plan assumed dry
    "tyre_short",        # the tyres will not reach the planned stop or the flag
)

# What George may do about one. Deliberately short: every entry here is
# something the app can already execute and the driver has already accepted.
ACTIONS = (
    "short_shift",       # his first fuel lever
    "lift_and_coast",    # his second
    "recost_to_flag",    # re-price the remaining stints, do not re-plan the race
    "offer_stay_out",
    "bring_stop_forward",
    "report_only",       # say it and decide nothing
    # --- the structural four. See STRUCTURAL_ACTIONS. ---
    "add_stop",
    "drop_stop",
    "change_compound",
    "abandon_plan",
)

# **The four things George may not do unless the desk wrote them down.**
#
# The rail used to gate whatever a playbook happened to name and to gate
# nothing at all when there was no playbook, which is the two failure modes of
# one mechanism: a plan the app wrote itself left George unbounded, and a
# handover that forgot an entry silenced a lever the driver was expecting.
# Neither is a decision anybody took.
#
# **So the bound is here, in code, and it does not depend on a document being
# present.** The line is whether the call changes the plan's SHAPE or only its
# TIMING. A stop is twenty seconds and cannot be taken back; a lap either side
# of the box window is worth a second or two and the next lap can revise it.
# Everything on the timing side is free - short-shift, lift-and-coast,
# re-costing, bringing a stop forward, reporting - because George being
# cautious with those makes him useless without making him safe.
#
# **`drop_stop` is George deciding a planned stop is unnecessary. It is NOT
# George acknowledging a stop the driver has already declined** by driving
# past the box. That fold is the driver's decision being recognised, and
# refusing to recognise it is how the box call fires every lap to the flag.
STRUCTURAL_ACTIONS = frozenset({
    "add_stop", "drop_stop", "change_compound", "abandon_plan",
})

# Named because they are the two the driver has refused outright, and a
# playbook that contained either would be executed. See `brain/driver.md`.
FORBIDDEN_ACTIONS = ("fuel_map", "brake_bias_forward")


def grants(entries, trigger: str, action: str) -> bool:
    """Whether a playbook lets George take this action on this trigger.

    **The gate the race actually runs on**, and the gate the standing orders
    are written from - one expression, because they were two and disagreed.
    `RaceCoordinator._may` delegates here; `standing_orders` asks it before it
    tells the driver what George will do without asking. A screen that decides
    that from "is there an entry" instead of from this says the opposite of
    the truth for exactly the pairs in `GATED`, which is what it did.

    Takes the playbook as a dict keyed by trigger (the coordinator's) or as a
    list of entries (a stored plan's).
    """
    if action not in STRUCTURAL_ACTIONS:
        return True
    if isinstance(entries, dict):
        entry = entries.get(trigger)
    else:
        # **Last wins, because the coordinator's dict comprehension does.**
        # Taking the first was the same inversion this function exists to
        # remove: on a playbook holding `fuel_long: drop_stop` then
        # `fuel_long: report_only`, the screen said George may drop the stop
        # and the race refused it. `Handover.validate` rejects a duplicated
        # trigger, but `mcp.propose_strategy` stores a payload without
        # validating and `certify` never reads the playbook, so a duplicate
        # reaches `plan_json` - which is the premise of this whole module.
        entry = None
        for candidate in entries:
            if candidate.trigger == trigger:
                entry = candidate
    return entry is not None and entry.action == action


# **The structural decisions a trigger can reach, what George says instead
# when the desk did not grant one, and WHEN the gate actually bites.**
#
# The third of those was missing and it made the sentence false for most of
# every race on file. `add_stop` is set on the wear cliff only when
# `state.stint_ends_on_lap is None` - the LAST stint. With a stop still ahead
# the same reading brings it forward, which is timing, and timing is free, so
# the driver hears "Box this lap." exactly as he would with a rule. Stating
# the gate flat told him he would not get the instruction he will get.
#
# The words after the dash are the call's own `report_form`, quoted, so the
# contract and the call say the same thing (rule 13).
#
# The sentences are built by `_withheld_sentence`, which reads the plan: the
# `add_stop` gate bites only on the last stint, and saying that flat was
# wrong for every other stint of every plan on file.
GATED = (("tyre_short", "add_stop"), ("fuel_long", "drop_stop"))


# How each stop reading is said. One vocabulary, because a second one for
# the same three fields can only ever drift out of step with this.
_STOP_SAID = {"stints": "its stints imply {n}",
              "stops": "its stop count says {n}",
              "pit_laps": "its box laps name {n}"}


# No race has ever run more than a handful of stops, and a figure past this
# is a corrupt field rather than a plan. Bounded so a stray `1e300` is named
# as unreadable instead of rendered as a 301-digit number on the grid.
_STOP_CEILING = 1000

# Laps are not stops. A 24-hour race at 90-second laps is 960, so the stop
# ceiling is not a margin for a lap count - it is a category error.
LAP_CEILING = 100_000


def as_whole_number(value, ceiling: int, *,
                    minimum: int | None = None) -> int | None:
    """A stored field read as a whole number within the caller's bounds.

    **The bounds are the caller's**, because a stop count and a lap count are
    not the same quantity: one ceiling for both would refuse a real endurance
    distance to catch a corrupt stop field, and `minimum` is None for stops -
    where a negative is deliberately kept as an unusable reading and named as
    one - and 0 for laps, where it is simply not a lap count.
    """
    if isinstance(value, bool):
        return None
    # `inf` and `nan` fail `is_integer()`. Everything else that survives is
    # bounded HERE, on both paths: the ceiling used to sit on the float
    # branch alone, after `isinstance(value, int)` had already returned - so
    # `1001.0` was refused and `1001` was read as a count, two opposite
    # verdicts on the same JSON number. `json.loads` gives an `int` for a
    # digit string with no decimal point, which is the likelier shape, and a
    # 400-digit one rendered a 2,822 px line against a 733 px plate.
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    if not isinstance(value, int) or abs(value) > ceiling:
        return None
    return None if minimum is not None and value < minimum else value


def as_stop_count(value) -> int | None:
    """A stop count off a stored field, or None when it cannot be read as one.

    **Public, because six places read `plan["stops"]` and four of them used
    to do their own arithmetic on it.** A float certified clean by `certify`
    then printed "1.0 stop" on the Race page and slipped past the export's
    stints-vs-stops cross-check, which only looked at `int`. One expression,
    read by every consumer.

    **An integral float is a count.** JSON has no integer type and
    `mcp.propose_strategy` stores arbitrary JSON, so `5.0` is what a
    round-trip produces rather than a hostile input - and gating on
    `isinstance(value, int)` dropped it, which let `_stops_planned` answer a
    confident 0 off the stints alone while the plan's own field said 5.
    """
    return as_whole_number(value, _STOP_CEILING)


def _stop_readings(plan: dict) -> tuple[dict[str, int], list[str]]:
    """Every field of the plan that says how many stops it holds.

    Three of them, and no gate makes all three agree. `Handover.validate`
    requires only `stints`; `certify` refuses `stops != len(stints) - 1` but
    **never checks `pit_laps` against either**, so a plan listing one box lap
    and one stint validates, certifies and stores.

    Returns the readings it could take and the names of the fields that are
    THERE and unreadable - which is a finding, not an absence.
    """
    readings: dict[str, int] = {}
    unreadable: list[str] = []
    stints = plan.get("stints")
    if isinstance(stints, list) and stints:
        # `Plan.stops`' own definition, and the expression the coordinator
        # arms from: `_apply_stint` sets `stint_ends_on_lap = None` when
        # there is no stint after this one.
        readings["stints"] = len(stints) - 1
    elif stints is not None:
        unreadable.append("stints")
    # **A negative stop count is kept as an unusable reading, not dropped.**
    # Dropping it made `_stops_planned` answer a confident count again -
    # `{stints: 3, stops: -2}` reported 2 and the card said "he may bring a
    # planned stop forward" - with nothing anywhere saying the stored plan
    # carries an impossible figure. Rule 3 asks for `None` and for the
    # disagreement to be said, not for the corrupt reading to vanish. A field
    # of the wrong TYPE is the same thing one step earlier.
    # **`is not None`, like the two branches either side.** Keyed on the
    # KEY, a `"stops": null` - the ordinary JSON for "not stated" - counted
    # as a corrupt field, so `_stops_planned` returned None instead of 0,
    # `_cannot_fire` went False, and a granted `fuel_long: drop_stop`
    # rendered under *George may* on a plan where `_stops_off` can never
    # fire. That is the state pass 11 was written to close.
    if plan.get("stops") is not None:
        count = as_stop_count(plan.get("stops"))
        if count is None:
            unreadable.append("stops")
        else:
            readings["stops"] = count
    laps = plan.get("pit_laps")
    if isinstance(laps, list):
        readings["pit_laps"] = len(laps)
    elif laps is not None:
        unreadable.append("pit_laps")
    return readings, unreadable


def _stops_planned(plan: dict) -> int | None:
    """How many stops the plan holds, or None. **Never 0 for "don't know".**

    **Three fields say it and nothing makes them agree**, so this reports a
    number only when they do. Reading `stints` first and returning it was the
    pass-4 fix and it was rule 3 in the shape rule 9 warns about: a plan whose
    `pit_laps` said one stop and whose `stints` said none rendered a
    confident `0`, and the Race page printed *"box lap 10"* two inches above
    *"No stop is planned"*. Where two readings disagree, the disagreement is
    the finding (rule 1) - `_stop_disagreement` says it aloud.
    """
    readings, unreadable = _stop_readings(plan)
    if unreadable or any(number < 0 for number in readings.values()):
        return None            # a negative, or a field of the wrong type
    values = set(readings.values())
    return values.pop() if len(values) == 1 else None


def short_value(value, limit: int = 40) -> str:
    """A stored value quoted back to the driver, cut to one line's worth.

    **Public, because `certify`'s refusal reaches a status label too** and
    quoted the same field with a bare `repr` - a 400-digit figure or a whole
    stint structure would go into it whole.
    """
    text = repr(value)
    return text if len(text) <= limit else text[:limit - 1].rstrip() + "\u2026"


def _stop_disagreement(plan: dict) -> str | None:
    """The plan's own fields, quoted, when they do not agree about stops."""
    readings, unreadable = _stop_readings(plan)
    if len(set(readings.values())) < 2 and not unreadable \
            and not any(number < 0 for number in readings.values()):
        return None
    # **Every figure in STOPS, which is the unit they are compared in.**
    # The `stints` reading is `len(stints) - 1` and the sentence printed it
    # as `+ 1`, the field's own unit - so a plan with one stint, `stops: 1`
    # and one box lap read *"lists 1 stint, says 1 stop, names 1 box lap -
    # they disagree"*: three equal figures and a claim that they conflict,
    # which reads as the app being broken rather than the plan. The numbers
    # on screen were not the numbers compared.
    # Each clause names the field it came from - the middle one said a bare
    # "it says", so the driver could not tell which of three was the odd one.
    said = _STOP_SAID
    # **Corrupt readings last, and the clause that describes them is not
    # left dangling into the next one.** "its stop count says -2, which is
    # not a count, its box laps name 1 stop" reads as one sentence about the
    # box laps.
    good = [(name, number) for name, number in readings.items() if number >= 0]
    bad = [(name, number) for name, number in readings.items() if number < 0]
    parts = [said[name].format(n=number)
             + (" stop" if number == 1 else " stops")
             for name, number in good]
    parts += [said[name].format(n=number) + " (not a count)"
              for name, number in bad]
    # A field that is there and cannot be read at all - a `stops` of "5", a
    # `pit_laps` that is not a list. Quoted as stored, because the driver is
    # the only one who can tell the desk what it meant.
    # Truncated: a `stints` given as a dict renders its whole structure into
    # a standing order otherwise, and `Handover.validate` passes that shape.
    parts += [said[name].format(n=short_value(plan.get(name)))
              + " (not a count)" for name in unreadable]
    # **Only a real disagreement is called one.** With a single corrupt
    # reading and nothing to compare it against, the plan is not arguing
    # with itself; it is holding a figure that cannot be read.
    # **One clause is not a disagreement.** With a single reading there is
    # nothing to compare it against; the plan is holding a figure that
    # cannot be read, which is a different thing to say. The lone clause is
    # promoted to a sentence off the SAME vocabulary - `"its stints imply"`
    # becomes `"The plan's stints imply"` - rather than sliced back out of
    # the joined string or written twice in a second dict.
    # **The head names what was actually found, in this order: one clause is
    # never a disagreement; a conflict between readings is; anything else is
    # a field that cannot be read.** Both halves of that were wrong once -
    # `len(parts) > 1` counted an unreadable clause as evidence of a
    # conflict, and checking the conflict first gave a lone negative reading
    # the "disagrees with itself" head (rule 12: the head has to name the
    # constraint the expression produced).
    if len(parts) > 1:
        # **Only the set size.** `any(number < 0)` was decisive only when
        # there was ONE reading beside an unreadable field - and a head
        # asserting the figures conflict, with one figure in the sentence,
        # is the thing this ordering exists to prevent. With two readings a
        # negative one already makes the set bigger.
        conflict = len(set(readings.values())) > 1
        head = ("The plan disagrees with itself about stops - " if conflict
                else "The plan's stop figures cannot all be read - ")
        return head + ", ".join(parts) + \
            ". How many stops it holds is not known."
    # Promoted off the template, not off the joined clause: `_STOP_SAID`'s
    # entries all begin "its ", and asserting that here means a reworded
    # template fails loudly rather than silently losing its capital.
    name = (list(readings) + unreadable)[0]
    template = said[name]
    assert template.startswith("its "), template
    number = (readings[name] if name in readings
              else short_value(plan.get(name)))
    return ("The plan's " + template[len("its "):].format(n=number)
            + ", which is not a count. How many stops it holds is not known.")


def _cannot_fire(trigger: str, action: str, plan: dict) -> bool:
    """Whether this plan makes a GRANTED structural action unreachable.

    The mirror of `_withheld_sentence`, and the same class as a rule for a
    trigger George is blind to: `_stops_off` returns None while
    `stint_ends_on_lap` is None, so `fuel_long: drop_stop` on a plan with no
    stop in it is a rule the driver believes is armed and which can never
    fire. The wear cliff has no such bound - it can reach the last stint of
    any plan, and on a no-stop plan every stint is the last.
    """
    # **One pair, and the sentence that reports it depends on that.** A
    # second would need its reason ("there is no stop to drop") and its
    # fall-back clause derived rather than written flat, because the clause
    # is unconditional there only while this condition and
    # `_withheld_sentence`'s `stops == 0` branch are the same condition.
    return (trigger, action) == ("fuel_long", "drop_stop") \
        and _stops_planned(plan) == 0


def _withheld_sentence(trigger: str, plan: dict) -> str | None:
    """What George will not do on this trigger, for THIS plan.

    **The condition has to be evaluated, not narrated.** The first version of
    this stated the `add_stop` gate flat and was false for every stint but the
    last; the second carried the condition as prose in a constant and was
    false again on a plan with no stop in it, where "he may bring a planned
    stop forward" names a stop that does not exist and "on the last stint"
    reads as a late-race restriction on a gate that bites from the green.
    """
    stops = _stops_planned(plan)
    if trigger == "tyre_short":
        if stops == 0:
            return ('No stop is planned, so he cannot bring one forward: on '
                    'tyre short he cannot add one without a rule from the '
                    'desk - he says "Tyres past the stint limit." and you '
                    'decide.')
        if stops is None:
            # **The half that is true either way.** Adding a stop is gated
            # whatever the plan holds; bringing one forward is free, and
            # naming a stop we cannot count would be the thing rule 3 is
            # about. `_stop_disagreement` says why the count is missing.
            return ('On tyre short he cannot add a stop without a rule from '
                    'the desk - he says "Tyres past the stint limit." and you '
                    'decide.')
        return ('On tyre short he may bring a planned stop forward, but '
                'cannot add one after the last without a rule from the desk - '
                'then he says "Tyres past the stint limit." and you decide.')
    if trigger == "fuel_long":
        if stops == 0:
            # `_stops_off` needs a planned stop, so the call cannot fire and
            # the line would be about a decision nobody faces. An UNKNOWN
            # count is not that: the stop may be there, and a false silence
            # is the worse of the two errors.
            return None
        return ('On fuel long he cannot drop a stop without a rule from the '
                'desk - he says "You\'re fuelled to the flag." and the stops '
                'stay in the plan.')
    return None

# Names the stored payload owns. A plan carrying one of these is refused
# rather than merged - see `Handover.as_stored`.
# **`export` is the app's**, and it was not on this list: `_strategy_section`
# prefers `plan["export"]` verbatim over the section it builds, so a
# desk-supplied one shipped `1.0` and `[11.0, 9.0]` into the contract on the
# branch where every reader this row added is bypassed. Two copies of one set
# of figures is §1a, and the app's is the one with the arithmetic behind it.
RESERVED_KEYS = frozenset(("handover", "author", "playbook", "unhandled",
                           "certificate", "export"))


@dataclass(frozen=True)
class PlaybookEntry:
    """One adaptation George may make without asking."""
    trigger: str
    action: str
    # The condition that has to hold before it fires, in the plan's own units -
    # "more than 1.5 laps short", "more than 8 seconds lost". Prose, because it
    # is read by a human as often as it is executed.
    when: str
    # What ends it. An adaptation with no limit is a new plan.
    until: str = ""
    note: str = ""

    def validate(self) -> list[str]:
        problems = []
        if self.trigger not in TRIGGERS:
            problems.append(
                f"{self.trigger!r} is not a trigger George can act on; "
                f"expected one of {', '.join(TRIGGERS)}")
        if self.action in FORBIDDEN_ACTIONS:
            problems.append(
                f"{self.action!r} is a standing refusal of the driver's and "
                f"may not appear in a playbook - a rule he believes is armed "
                f"and is not is worse than no rule")
        elif self.action not in ACTIONS:
            problems.append(
                f"{self.action!r} is not something George can execute; "
                f"expected one of {', '.join(ACTIONS)}")
        if not self.when.strip():
            problems.append(
                f"the {self.trigger!r} entry has no condition - an adaptation "
                f"that always fires is not an adaptation, it is the plan")
        return problems

    def as_dict(self) -> dict:
        return {"trigger": self.trigger, "action": self.action,
                "when": self.when, "until": self.until, "note": self.note}


@dataclass
class Handover:
    """Everything Ludo hands George for one race."""
    plan: dict
    playbook: list[PlaybookEntry] = field(default_factory=list)
    # Who wrote it and what it rests on. The audit after the race asks both.
    author: str = "ludo"
    assumptions: list[str] = field(default_factory=list)

    def validate(self) -> list[str]:
        """Every problem, not the first - the author fixes them in one pass."""
        problems: list[str] = []
        if not isinstance(self.plan, dict) or not self.plan.get("stints"):
            problems.append("the plan has no stints")
        for index, stint in enumerate((self.plan or {}).get("stints") or [],
                                      start=1):
            tyres = stint.get("tyres") if isinstance(stint, dict) else None
            if tyres is not None and not isinstance(tyres, bool) \
                    and tyres not in (0, 1):
                problems.append(
                    f"stint {index} carries tyres={tyres!r}; it must be true, "
                    f"false or absent - a word in quotes would be read as a "
                    f"set going on")
        # **Refused, never merged.** The stored payload is the plan's own keys
        # with the handover's alongside under one key, so a plan carrying one
        # of the reserved names would have it silently replaced. `assumptions`
        # is the live collision: `Plan.as_export` emits a dict of that name
        # and a handover's is a list of prose, and a reader taking the wrong
        # one gets no warning at all.
        for key in sorted(RESERVED_KEYS & set(self.plan or ())):
            # `export` is the APP's section, not the handover's, and the
            # answer for it is not "rename it" - the app builds one.
            owner = ("the app builds that section itself" if key == "export"
                     else "it is the handover's own - rename it")
            problems.append(
                f"the plan carries {key!r}: {owner}, because storing both "
                f"would silently keep one")
        seen = set()
        for entry in self.playbook:
            problems.extend(entry.validate())
            if entry.trigger in seen:
                problems.append(
                    f"two playbook entries answer {entry.trigger!r}; George "
                    f"would have to choose, and choosing is not his half")
            seen.add(entry.trigger)
        # **Not a refusal.** A race can legitimately be run to a plan with no
        # adaptations at all - a short sprint with one stop and no weather in
        # it. What must not happen is the driver assuming a playbook exists.
        return problems

    def unhandled(self) -> list[str]:
        """Triggers with no entry, so the driver knows what George will not do."""
        covered = {e.trigger for e in self.playbook}
        return [t for t in TRIGGERS if t not in covered]

    def as_dict(self) -> dict:
        """The handover's own half, for storing under one key."""
        return {
            "author": self.author,
            "playbook": [e.as_dict() for e in self.playbook],
            "assumptions": list(self.assumptions),
            # **A record of the moment, and nothing reads it back.** It
            # is `unhandled()` as it stood when the plan was written, so a
            # trigger retired or added since makes it disagree with today -
            # `[]` on strategies 15 and 16, `['safety_car']` on 29, while
            # `standing_orders` recomputes and says "tyre short". Every
            # surface the driver or the tune builder sees recomputes;
            # this is here for the audit, which asks what was known then.
            "unhandled": self.unhandled(),
        }

    def as_stored(self, plan: dict) -> dict:
        """The row as `strategies.plan_json`: the PLAN, with this alongside.

        **Flat for the plan, namespaced for the handover.** `RaceCoordinator`
        and `certify` read `stints`, `stops`, `expects` and `context` off the
        top level, so nesting the plan under a `"plan"` key - which is what
        this used to store - produced a row that saved cleanly and was then
        refused on the grid for naming no stints. And merging the handover's
        fields in flat collides: `assumptions` is a dict from
        `Plan.as_export` and a list of prose here.
        """
        return {**plan, "handover": self.as_dict()}


def playbook_of(stored: dict) -> list[PlaybookEntry]:
    """The playbook off a stored plan, or empty. The read half of `as_stored`."""
    section = (stored or {}).get("handover") or {}
    return [PlaybookEntry(trigger=e.get("trigger", ""),
                          action=e.get("action", ""),
                          when=e.get("when", ""),
                          until=e.get("until", ""),
                          note=e.get("note", ""))
            for e in (section.get("playbook") or [])]


def author_of(stored: dict) -> str | None:
    """Who wrote a stored plan, or None for the app's own optimiser."""
    return ((stored or {}).get("handover") or {}).get("author") or None


# **What George cannot see at all, whatever a playbook says.** GT7
# broadcasts no weather in any packet format, so a rule for it is a rule that
# can never fire - which is worse than no rule, because the driver believes it
# is armed. (The safety car left `TRIGGERS` on 7 Sep 2026 for the same
# reason, so it no longer needs saying here.)
CANNOT_SEE = ("rain",)

# The register each line is set in, which is the whole of what the ink means:
# a human declared it, the app derived it, or it is prose about a gap.
DECLARED, DERIVED, GAP = "declared", "derived", "gap"


@dataclass(frozen=True)
class Order:
    """One line of the standing orders, and the register it is said in."""
    text: str
    register: str
    heading: bool = False


def standing_orders(stored: dict) -> list[Order]:
    """What George may do on his own, and what he is blind to. One source.

    **Rendered on two screens now** (row 1.7): the Strategy page's
    `LoadedCard`, where the plan is approved, and the Race page, where the
    driver is sitting on the grid. The words live here rather than in either
    of them - two copies of a contract are two contracts, and this one says
    what the engineer is allowed to do without asking.

    `None` register means prose about an absence; `DECLARED` is a human's
    word; `DERIVED` is the app's own certification.
    """
    # **No plan is not "no rules"** - it is nothing to say. A plan with no
    # HANDOVER is different and does have orders: it says George has no rule
    # from the desk on anything and falls back to his own, which is the most
    # consequential thing the driver can learn on the grid.
    if not stored:
        return []
    plan = stored
    handover = plan.get("handover") or {}
    out: list[Order] = []

    certificate = handover.get("certificate") or {}
    for warning in certificate.get("warnings") or ():
        out.append(Order(warning, DERIVED))
    for gap in certificate.get("unchecked") or ():
        # Named, not dropped. A check that could not run is not a check that
        # passed, and the driver is the only one who can decide whether to
        # race on it.
        out.append(Order(f"Not checked: {gap}", GAP))

    # **A rule is only a rule if it can fire.** Two ways it cannot, and a
    # stored plan on file has one of each: the trigger names a channel the
    # feed does not carry (`CANNOT_SEE`), or it was retired from `TRIGGERS`
    # after the plan was written. `PlaybookEntry.validate` catches both when a
    # handover is AUTHORED and nothing revalidates a stored one, so the check
    # has to be here, at the point the driver reads it.
    entries = playbook_of(plan)
    # **An entry with no trigger is unreadable, not a rule about nothing.**
    # `playbook_of` defaults every field to `""`, and this function exists
    # because stored rows escape validation - so the blank case has to be
    # named rather than rendered as "The desk left a rule for , which ...".
    blank = [e for e in entries if not e.trigger.strip()]
    named = [e for e in entries if e.trigger.strip()]
    # **Three states, and an entry is in exactly one.** Readable and able to
    # fire; readable and unable; not readable at all. Saying two of them
    # about one rule is what the whole `live`/`dead` split exists to stop,
    # and dropping the unfireable ones into `dead` said three - a retirement
    # notice, an unfireable notice and a no-rule notice, all disagreeing.
    # **Last wins, because `grants` and the coordinator both take the last.**
    # Built per-entry, a playbook holding `fuel_long: drop_stop` then
    # `fuel_long: report_only` printed BOTH under *George may* while the race
    # honoured only the second - the driver believing a lever is armed when
    # it is not, which is the screen-vs-race split this module exists to
    # close.
    by_trigger: dict[str, PlaybookEntry] = {}
    superseded: list[str] = []
    for entry in named:
        if entry.trigger in by_trigger:
            superseded.append(entry.trigger)
        by_trigger[entry.trigger] = entry
    latest = list(by_trigger.values())
    # **The ACTION is checked too, not only the trigger.** This function
    # exists because stored rows escape validation, and it re-checked the
    # trigger against `TRIGGERS` while printing `fuel long - fuel map` - a
    # standing refusal of the driver's - as something George may do alone,
    # and letting `incident - teleport to pits` fill the coverage gap for
    # incidents so he was never told he was on his own for one.
    unrunnable = [e for e in latest
                  if e.trigger in TRIGGERS and e.trigger not in CANNOT_SEE
                  and e.action not in ACTIONS]
    readable = [e for e in latest
                if e.trigger in TRIGGERS and e.trigger not in CANNOT_SEE
                and e.action in ACTIONS]
    stillborn = [e for e in readable
                 if _cannot_fire(e.trigger, e.action, plan)]
    live = [e for e in readable
            if not any(e is dud for dud in stillborn)]
    # By identity, because a row is a row. **This fixes nothing that was
    # broken** - liveness is a function of `trigger` alone, so two equal
    # entries are both live or both dead and `e not in live` could not
    # misclassify either. Critic pass 1 claimed otherwise and was wrong; the
    # real duplicate-entry defect was in `grants`, above. Kept because
    # identity is what the question means.
    dead = [e for e in latest
            if not any(e is kept for kept in readable)
            and not any(e is dud for dud in unrunnable)]
    if live:
        out.append(Order("George may, on his own", GAP, heading=True))
        for entry in live:
            out.append(Order(
                f"{entry.trigger.replace('_', ' ')} - "
                f"{entry.action.replace('_', ' ')} when {entry.when}"
                + (f", until {entry.until}" if entry.until else ""),
                DECLARED))

    # **Recomputed against today's triggers**, not read off the stored row: a
    # handover stored before a trigger was retired or added would otherwise
    # show a gap that no longer exists, or hide one that does.
    #
    # A rule that cannot fire on THIS plan still counts as cover, because the
    # desk did write one - the gap line would say "no rule from the desk"
    # about a rule it can see three lines below. What that rule cannot do is
    # said once, in its own sentence.
    # **A rule that cannot run counts as cover, and its own sentence carries
    # the fall-back.** Both halves are needed and each was tried alone: left
    # OUT of `covered`, the block said "The desk's rule for incident ... will
    # never fire" and, four lines below, "No rule from the desk on ...
    # incident" - one trigger, two opposite claims. Put IN without the
    # fall-back clause, the driver read that the rule will never fire and
    # found incident missing from the list of things George decides himself,
    # so he would conclude George does nothing on an off - and George says
    # "Lap 7 is out. That cost you 12 seconds against your pace." with no
    # playbook at all, because `_incident` carries no `structural_action`.
    covered = ({entry.trigger for entry in readable}
               | {entry.trigger for entry in unrunnable})
    unhandled = [t for t in TRIGGERS if t not in covered]
    no_rule = [t for t in unhandled if t not in CANNOT_SEE]

    # **Three sentences, because a driver would act differently on each.**
    # Nothing there; something there that cannot fire; something there whose
    # cause is a retirement rather than a missing channel. The first two were
    # one sentence and it asserted a cause the code had not determined:
    # `dead` is anything not in `TRIGGERS`, which is a retirement for ANY
    # reason, and "he cannot see it at all" is only true of `CANNOT_SEE`
    # (rules 5 and 12).
    blind_ruled = sorted({e.trigger for e in dead if e.trigger in CANNOT_SEE})
    gone_ruled = sorted({e.trigger for e in dead
                         if e.trigger not in CANNOT_SEE})
    unruled = [t for t in CANNOT_SEE if t not in blind_ruled]
    if unruled:
        out.append(Order(
            "He cannot see " + ", ".join(t.replace("_", " ") for t in unruled)
            + " at all - tell him.", GAP))
    if blind_ruled:
        out.append(Order(
            "The desk left a rule for "
            + ", ".join(t.replace("_", " ") for t in blind_ruled)
            + ", which he cannot see at all - it will never fire. Tell him.",
            GAP))
    if gone_ruled:
        out.append(Order(
            "The desk left a rule for "
            + ", ".join(t.replace("_", " ") for t in gone_ruled)
            + ", which George no longer acts on - it will never fire.", GAP))
    if superseded:
        # Named rather than dropped, the way a blank entry is: `validate`
        # rejects a duplicated trigger, so one here means the row reached
        # storage unvalidated, and the driver is reading a contract with a
        # rule in it that nothing will use.
        # **"read", not "used".** The surviving entry may itself be one
        # George cannot execute, cannot see, or the plan cannot fire, and
        # "only the last is used" then sits directly above the line saying it
        # will never fire. "Read" is true in every one of those states.
        out.append(Order(
            "The desk wrote more than one rule for "
            + ", ".join(t.replace("_", " ") for t in sorted(set(superseded)))
            + " - only the last is read.", GAP))
    if blank:
        out.append(Order(
            f"{len(blank)} playbook "
            + ("entry names" if len(blank) == 1 else "entries name")
            + " no trigger and cannot be read - treat the desk's rules as "
              "incomplete.", GAP))

    # **What he does NOT fall back to his own on.** `grants` is the gate the
    # race runs on: a structural action with no entry is refused, and the
    # driver has to know which decisions that removes from George rather than
    # being told he will use his judgement on all of them.
    # **`named`, not `live`** - the coordinator builds its book from every
    # stored entry, and asking the gate a different set here is the same
    # screen-vs-race split this function exists to close. Equal today only
    # because both gated triggers happen to be live; retiring one - which is
    # what happened to `safety_car` on 7 Sep - would have reopened it.
    # **Granted is not the same as reachable.** A rule the plan makes
    # unfireable is the same failure as a rule for a trigger he cannot see:
    # the driver believes it is armed. Said once, and not under *George may*.
    for entry in stillborn:
        # This loop had no fall-back clause at all, so a granted
        # `fuel_long: drop_stop` on a plan with no stop said only that it
        # cannot fire - while a garbage rule and no rule both said George
        # falls back to his own. Three states of one trigger, two saying he
        # decides and the third silent, and the silent one is what a real
        # desk writes.
        #
        # **The clause is unconditional here, and that is a fact about
        # `_cannot_fire`, not a shortcut.** The only pair it answers True for
        # is `fuel_long: drop_stop` with no stop planned - which is exactly
        # when `_withheld_sentence` returns None, so asking the predicate
        # would be asking a question with one answer.
        out.append(Order(
            f"The desk's rule for {entry.trigger.replace('_', ' ')} cannot "
            f"fire on this plan - there is no stop to drop, and George falls "
            f"back to his own.", GAP))
    # **Suppressed where a WITHHELD SENTENCE will follow, not merely where
    # the trigger is gated.** Saying "George falls back to his own" a few
    # lines above "he cannot drop a stop without a rule from the desk" is
    # pass 1's second blocker said again - but on a plan with no stop there
    # is nothing to withhold, `_withheld_sentence` returns None, and the
    # clause is true: the FUEL_LONG call carries no `structural_action`, so
    # George says "You can push." with no playbook at all. Keyed on the
    # trigger, a garbage rule REMOVED that true statement while having no
    # rule kept it.
    for entry in unrunnable:
        trigger = entry.trigger.replace("_", " ")
        falls_back = ("" if _withheld_sentence(entry.trigger, plan) is not None
                      else ", and George falls back to his own")
        if not entry.action.strip():
            # **Not "asks for nothing, which George cannot execute"** - doing
            # nothing is the one thing that is always executable, and it is
            # also how a driver reads `report_only`. Unreadable - and NOT
            # "treat it as absent", which told him to do what this function
            # does not: the trigger still counts as covered, so it is struck
            # from the fall-back line and the sentence has to say so itself.
            out.append(Order(
                f"The desk's rule for {trigger} names no action and cannot "
                f"be read{falls_back}.", GAP))
            continue
        # Third person throughout, like every other line here: the block is
        # read on the grid and "you have refused" put the driver in two roles
        # in one paragraph.
        refused = entry.action in FORBIDDEN_ACTIONS
        out.append(Order(
            f"The desk's rule for {trigger} asks for "
            f"{entry.action.replace('_', ' ')}, which "
            + ("the driver has refused outright" if refused
               else "George cannot execute")
            + f" - it will never fire{falls_back}.", GAP))

    withheld = []
    for trigger, action in GATED:
        if grants(named, trigger, action):
            continue
        sentence = _withheld_sentence(trigger, plan)
        if sentence is not None:
            withheld.append((trigger, sentence))
    for _trigger, sentence in withheld:
        out.append(Order(sentence, GAP))

    # **"No rule from the desk", not "he will do nothing".** The card said the
    # second and it was false in the direction that matters: `stop_still_
    # needed` and `stay_out_call` decide fuel and a missed stop with or
    # without a playbook. The gated pairs are named above and drop out here,
    # because saying both about one trigger is saying two things.
    gated_triggers = {trigger for trigger, _sentence in withheld}
    falls_back = [t for t in no_rule if t not in gated_triggers]
    if falls_back:
        out.append(Order(
            "No rule from the desk on "
            + ", ".join(t.replace("_", " ") for t in falls_back)
            + " - George falls back to his own.", GAP))

    disagreement = _stop_disagreement(plan)
    if disagreement is not None:
        out.append(Order(disagreement, GAP))

    # **The assumptions the plan rests on, which nothing rendered.** Six of
    # them are stored against the Daytona plan and no screen has ever shown
    # one - so a plan whose stint length rests on a wear rate nobody measured
    # looked exactly like one that did not (row 1.7).
    assumptions = handover.get("assumptions") or []
    if assumptions:
        out.append(Order("Resting on", GAP, heading=True))
        for line in assumptions:
            out.append(Order(str(line), DECLARED))
    return out


# **The count-shaped keys, declared rather than enumerated at the call
# site.** `start_lap` was left out of the first version of `whole_numbers` and
# `stint_ends_on_lap` is `start_lap + laps - 1`, so the very symptom that
# motivated the door - George saying "the next 9.0-lap stint" - survived it.
# Adding one more field by hand would be the same shape a fourth time;
# `test_the_door_reads_every_count_a_plan_carries` holds these against what
# `Plan.as_dict` emits.
PLAN_COUNTS = {"stops": (_STOP_CEILING, None), "laps": (LAP_CEILING, 0)}
# `end_lap` is a `Stint` PROPERTY, never stored and never read off a stored
# stint, so declaring it here was a key that could not be exercised.
STINT_COUNTS = {"laps": (LAP_CEILING, 0), "start_lap": (LAP_CEILING, 1)}


def whole_numbers(plan: dict) -> dict:
    """The plan with its counts read as whole numbers. **Once, at the door.**

    JSON has no integer type, so a desk writing `11` may send `11.0` - and
    six readers were taught that separately, one per critic pass, while the
    plan itself kept the float. `certify` then accepted `{"laps": 11.0}`,
    `stint_ends_on_lap` became `11.0`, and George said *"the next 9.0-lap
    stint"* with the hose in.

    A value that cannot be read as a count is left exactly as it is: this
    function normalises, it does not judge. `certify` and `_validate_plan`
    are the two that refuse, and they need to see what the desk actually
    wrote.

    **Called by the two desk doors, not by every writer.** `from_dict` (so
    `write_strategy` and the CLI) and `mcp.propose_strategy`. The app's own
    optimiser writes `Plan.as_dict`, whose counts are `int` by construction,
    and `save_qualifying_plan` is a different surface.

    **So the guarantee is "read where it can be read", not "no consumer sees
    a float".** A value this cannot read is passed through untouched by
    design, and `certify` is what refuses it - including `start_lap`, which
    was checked by neither for a while and reached a spoken call as `1.5`.
    """
    def read(value, ceiling, minimum):
        got = as_whole_number(value, ceiling, minimum=minimum)
        return value if got is None else got

    out = dict(plan)
    for key, (ceiling, minimum) in PLAN_COUNTS.items():
        if key in out:
            out[key] = read(out[key], ceiling, minimum)
    if isinstance(out.get("pit_laps"), list):
        out["pit_laps"] = [read(lap, LAP_CEILING, 1)
                           for lap in out["pit_laps"]]
    if isinstance(out.get("stints"), list):
        out["stints"] = [
            {**stint,
             **{key: read(stint[key], ceiling, minimum)
                for key, (ceiling, minimum) in STINT_COUNTS.items()
                if key in stint}}
            if isinstance(stint, dict) else stint
            for stint in out["stints"]]
    return out


def from_dict(payload: dict) -> Handover:
    """Rebuild a handover from the JSON an author writes.

    Accepts either shape: the plan at the top with the handover's fields
    beside it, or the plan nested under `"plan"`. Ludo writes the first;
    `as_stored` produces it too, so a stored row round-trips.

    **The counts are read here and nowhere else.** See `whole_numbers`.
    """
    section = payload.get("handover") if isinstance(
        payload.get("handover"), dict) else payload
    entries = [PlaybookEntry(trigger=e.get("trigger", ""),
                             action=e.get("action", ""),
                             when=e.get("when", ""),
                             until=e.get("until", ""),
                             note=e.get("note", ""))
               for e in (section.get("playbook") or [])]
    plan = payload.get("plan")
    if not isinstance(plan, dict):
        # **The flat shape is what the desk actually writes**, and the
        # reserved names are stripped from it rather than refused - which is
        # right for the five the handover consumes, because they belong
        # beside the plan. `export` is the exception: nothing reads it back,
        # so the desk's own arithmetic disappeared with no message on the
        # common path. Kept on the plan so `validate` refuses it by name.
        plan = {k: v for k, v in payload.items()
                if (k not in RESERVED_KEYS or k == "export") and k != "plan"}
    return Handover(plan=whole_numbers(plan), playbook=entries,
                    author=section.get("author") or "ludo",
                    assumptions=list(section.get("assumptions") or []))


def accept(store, event_id: int, handover: Handover, *,
           label: str | None = None) -> tuple[int | None, list[str]]:
    """Certify a handover and store it as a candidate. `(id, problems)`.

    **Certified before it is stored, and stored as a candidate rather than
    approved.** Both halves matter. A plan that cannot be run must never reach
    the race screen looking like one - the app once ranked the most impossible
    plan cheapest and asked for 510 litres into a 100 litre tank. And approval
    stays the driver's: an engineer who could approve his own plan is not a
    second opinion.

    Returns `(None, problems)` when it is refused, and the problems are every
    one found rather than the first.
    """
    from pitcrew.strategy.certify import certify_for_event

    from pitcrew.strategy.execution import stamp

    problems = handover.validate()
    if problems:
        return None, problems

    # **Stamped before it is certified.** `expects` and `context` are what the
    # race reads once it is running, and a plan without them arms and then
    # runs blind - every per-lap comparison reporting nothing rather than
    # reporting a problem. `stamp` leaves an author's own figures alone.
    try:
        plan = stamp(store, event_id, handover.plan)
    except ValueError as exc:
        return None, [str(exc)]

    certificate = certify_for_event(store, event_id, plan)
    if not certificate.certified:
        return None, list(certificate.refusals)

    payload = handover.as_stored(plan)
    payload["handover"]["certificate"] = {
        "warnings": list(certificate.warnings),
        # **Recorded, because silence is never a pass.** A check that could not
        # run is not a check that passed, and the race audit has to be able to
        # tell the two apart.
        "unchecked": list(certificate.unchecked),
    }
    strategy_id = store.save_strategy(
        event_id, payload, label=label or f"{handover.author} plan",
        status="candidate")
    return strategy_id, list(certificate.warnings)


def main(argv: list[str] | None = None) -> int:
    """Load a handover from a JSON file. **The door Ludo comes through.**

        python -m pitcrew.strategy.handover --event 6 --file plan.json

    Ludo already runs Python in this repo - the skill's own instructions say
    to call `build_inputs` then `recommend` rather than hand-rolling stint
    arithmetic - so the load route is a command, not a service. There is no
    `.mcp.json` in this repo and registering a server is the driver's call.

    **This is the gap that cost the Fuji race.** Ludo wrote a one-stop plan
    with a fifteen-lap opening stint; the app's optimiser would not offer one
    because the evidence cap stood at six laps - two six-lap practice runs,
    deepest 24% worn, nothing had gone further. The certifier would have
    ACCEPTED the plan (its only tyre refusal is `0.85 / w`, which was 22 laps),
    but approval took an INDEX into `recommend()`'s output, so a plan the app
    had not thought of could not be chosen. He raced three stops. Read back
    afterwards the same set was watched to 56% and the cap lifted, and the
    optimiser now proposes 15 and 5 on one stop - Ludo's plan, arrived at
    independently.

    Exit 1 on refusal, so a refusal cannot be mistaken for a load.
    """
    import argparse
    import json
    import sys

    from pitcrew.store.db import Store

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--event", type=int, required=True)
    parser.add_argument("--file", required=True,
                        help="the handover as JSON: the plan, plus playbook "
                             "and assumptions")
    parser.add_argument("--label", default=None)
    args = parser.parse_args(argv)

    payload = json.loads(pathlib.Path(args.file).read_text(encoding="utf-8"))
    handover = from_dict(payload)

    store = Store()
    try:
        strategy_id, problems = accept(store, args.event, handover,
                                       label=args.label)
        # **Read back what was STORED, not re-render what was sent.**
        # `accept` attaches the certificate after `as_stored`, and returns
        # only the warnings - so rendering the handover again dropped every
        # "Not checked:" line, at the one moment the author could still act
        # on it. Silence is never a pass.
        stored = next((row.get("plan") or {}
                       for row in store.list_strategies(args.event)
                       if row.get("id") == strategy_id), {})
    finally:
        store.close()

    if strategy_id is None:
        print("REFUSED - not loaded:")
        for problem in problems:
            print(f"  - {problem}")
        return 1

    print(f"loaded as candidate {strategy_id} for event {args.event}.")
    print("It is NOT armed: approve it on the Strategy screen, which "
          "certifies it again against the evidence of the day.")
    for warning in problems:
        print(f"  warning: {warning}")
    # **The same sentences the two screens show.** These were a third
    # wording of one fact - "George will report it and decide nothing" - and
    # it was the wording the screens were changed away from for being false
    # on the free triggers (rule 13).
    for order in standing_orders(stored):
        if order.register == GAP and not order.heading:
            print(f"  {order.text}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
