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
TRIGGERS = (
    "fuel_short",        # the tank will not reach the flag or the next stop
    "fuel_long",         # more fuel aboard than the plan needs
    "stop_missed",       # the planned pit lap has gone by
    "incident",          # time lost to an off, a spin or contact
    "rain",              # the surface is wet and the plan assumed dry
    "safety_car",        # the field has been neutralised
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

# Names the stored payload owns. A plan carrying one of these is refused
# rather than merged - see `Handover.as_stored`.
RESERVED_KEYS = frozenset(("handover", "author", "playbook", "unhandled",
                           "certificate"))


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
            problems.append(
                f"the plan carries {key!r}, which is the handover's own - "
                f"rename it, because storing both would silently keep one")
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


def from_dict(payload: dict) -> Handover:
    """Rebuild a handover from the JSON an author writes.

    Accepts either shape: the plan at the top with the handover's fields
    beside it, or the plan nested under `"plan"`. Ludo writes the first;
    `as_stored` produces it too, so a stored row round-trips.
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
        plan = {k: v for k, v in payload.items()
                if k not in RESERVED_KEYS and k != "plan"}
    return Handover(plan=plan, playbook=entries,
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
    for trigger in handover.unhandled():
        print(f"  no playbook entry for {trigger} - George will report it "
              f"and decide nothing")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
