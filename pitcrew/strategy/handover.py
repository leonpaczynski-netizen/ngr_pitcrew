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
)

# Named because they are the two the driver has refused outright, and a
# playbook that contained either would be executed. See `brain/driver.md`.
FORBIDDEN_ACTIONS = ("fuel_map", "brake_bias_forward")


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
        return {
            "author": self.author,
            "plan": self.plan,
            "playbook": [e.as_dict() for e in self.playbook],
            "assumptions": list(self.assumptions),
            "unhandled": self.unhandled(),
        }


def from_dict(payload: dict) -> Handover:
    """Rebuild a handover as stored. Unknown keys are ignored, not guessed at."""
    entries = [PlaybookEntry(trigger=e.get("trigger", ""),
                             action=e.get("action", ""),
                             when=e.get("when", ""),
                             until=e.get("until", ""),
                             note=e.get("note", ""))
               for e in (payload.get("playbook") or [])]
    return Handover(plan=payload.get("plan") or {}, playbook=entries,
                    author=payload.get("author") or "ludo",
                    assumptions=list(payload.get("assumptions") or []))


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

    problems = handover.validate()
    if problems:
        return None, problems

    certificate = certify_for_event(store, event_id, handover.plan)
    if not certificate.certified:
        return None, list(certificate.refusals)

    payload = handover.as_dict()
    payload["certificate"] = {
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
