"""Per-domain practice run briefs (UAT-6 remediation).

Every objective the Event Command Centre raises names an evidence DOMAIN, and each
domain is only served by a genuinely different kind of run: a coaching run is driven
flat out on a light tank one clean lap at a time, a tyre test is driven at a fixed
race pace for as long as the tyre lasts, a qualifying simulation is out-flyer-in on a
single fresh set. Until now the run card described all of them identically — one
generic template whose "monitor" line was the placeholder string *"whatever the
coaching run is meant to show"* — so the driver had no way to tell what made the run
they were being sent on different from the last one.

This module holds the brief for each domain: how to drive it, what to watch while
driving, what fuel and tyre to run, what invalidates it, and what the review will be
able to tell them afterwards. It is the engineering content of the run, kept in one
pure, testable place.

Pure — no Qt, no DB, no I/O, never raises. It decides nothing about the programme;
``practice_run_recording`` still owns which activity a domain writes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Tuple


def _norm(v) -> str:
    return "" if v is None else str(v).strip()


@dataclass(frozen=True)
class RunBrief:
    """Everything that makes one kind of run different from another."""

    domain: str = ""
    #: "coaching run", "tyre test" — the run's name in the driver's language.
    run_name: str = "practice run"
    #: The one-line headline for the run card.
    objective: str = ""
    #: How this run must be DRIVEN. This is what makes it a coaching run and not a
    #: tyre test, and it is the part that was missing entirely.
    how_to_drive: Tuple[str, ...] = field(default_factory=tuple)
    #: What to pay attention to while driving it.
    monitor: Tuple[str, ...] = field(default_factory=tuple)
    fuel: str = ""
    tyre: str = ""
    target_laps: str = ""
    push_level: str = ""
    purpose: str = ""
    #: Conditions under which the run cannot be used as evidence.
    invalidation: Tuple[str, ...] = field(default_factory=tuple)
    #: What the Review will be able to report once the run is recorded. Setting the
    #: driver's expectation is what makes the run feel purposeful rather than repeated.
    reports: Tuple[str, ...] = field(default_factory=tuple)

    @property
    def is_known(self) -> bool:
        return bool(self.domain and self.how_to_drive)


#: The briefs, keyed by evidence domain as named in a command-centre objective.
_BRIEFS: Dict[str, RunBrief] = {
    "setup_base": RunBrief(
        domain="setup_base",
        run_name="baseline run",
        objective="Baseline run — establish the reference this event is measured against",
        how_to_drive=(
            "Drive the setup exactly as it is — change nothing during the run.",
            "Settle into a pace you can repeat rather than chasing one fast lap.",
            "Take the same line and the same braking points every lap.",
        ),
        monitor=(
            "Whether the car does the same thing every lap",
            "Balance at corner entry, mid-corner and on exit",
            "Anything that stops you committing to the throttle",
        ),
        fuel="Half tank, kept constant",
        tyre="Race compound",
        target_laps="5–8",
        push_level="Representative pace you can repeat",
        purpose="baseline",
        invalidation=(
            "Changing any setup value mid-run",
            "Traffic or an off that skews the lap",
        ),
        reports=(
            "Your reference best clean lap and consistency band",
            "Fuel per lap and how many laps a tank gives",
        ),
    ),
    "working_window": RunBrief(
        domain="working_window",
        run_name="setup experiment",
        objective="Setup experiment — test ONE change back-to-back against the baseline",
        how_to_drive=(
            "One change only. Two changes at once cannot be told apart afterwards.",
            "Drive it the same way you drove the baseline — same lines, same commitment.",
            "Give it a lap to settle before you judge it.",
        ),
        monitor=(
            "The specific behaviour the change was aimed at",
            "Whether it helped in the corner type it targeted",
            "Anything elsewhere on the lap that got worse",
        ),
        fuel="Same load as the baseline run",
        tyre="Same compound and similar tyre age as the baseline",
        target_laps="5–8",
        push_level="Identical to the baseline run",
        purpose="experiment",
        invalidation=(
            "More than one setup change in the same run",
            "A different fuel load or compound than the baseline",
            "Fresh tyres compared against worn ones",
        ),
        reports=(
            "Whether the change was faster, slower or inside the noise",
            "Whether your feel agrees with what the telemetry measured",
        ),
    ),
    "driver_coaching": RunBrief(
        domain="driver_coaching",
        run_name="coaching run",
        objective="Coaching run — the car is not under test, your driving is",
        how_to_drive=(
            "Light fuel and fresh tyres: this run is about your peak, not the car's.",
            "One committed lap at a time — reset and go again rather than pushing on "
            "through a scrappy lap.",
            "Change nothing on the car for the whole run.",
        ),
        monitor=(
            "Whether your braking point is the same lap after lap",
            "Minimum speed in mid-corner — where you are giving time away",
            "How early you can get to the throttle without wheelspin",
            "Lock-ups and wheelspin, and which corners they happen in",
        ),
        fuel="Light and constant",
        tyre="Fresh set, one warm-up lap",
        target_laps="5–8",
        push_level="Qualifying commitment on each clean lap",
        purpose="coaching",
        invalidation=(
            "Changing the setup during the run",
            "Running a long stint — worn tyres hide driving errors",
        ),
        reports=(
            "Which corners cost you the most against your own best",
            "Lock-ups and wheelspin per corner, and the technique behind them",
            "Whether your pace is limited by the car or by the lap you are driving",
        ),
    ),
    "tyre_model": RunBrief(
        domain="tyre_model",
        run_name="tyre test",
        objective="Tyre test — find out how the tyre falls away over a stint",
        how_to_drive=(
            "Start on a fresh set and stay out — degradation is the whole point.",
            "Hold ONE pace for the entire run. Varying push makes the drop unreadable.",
            "Do not pit and do not change compound mid-run.",
        ),
        monitor=(
            "When the lap time starts dropping away, and by how much per lap",
            "Which end of the car goes off first",
            "Whether the balance moves as the tyres wear",
        ),
        fuel="Race load",
        tyre="Fresh set at the start — run it down",
        target_laps="12–20, or until the tyre is done",
        push_level="Consistent race pace, held for the whole run",
        purpose="tyre wear",
        invalidation=(
            "Pitting or changing compound mid-run",
            "Varying your push level through the stint",
        ),
        reports=(
            "Lap-time drop per lap and where the cliff is",
            "How long a usable stint is on this compound",
        ),
    ),
    "fuel_model": RunBrief(
        domain="fuel_model",
        run_name="fuel test",
        objective="Fuel test — measure what a lap actually costs in fuel",
        how_to_drive=(
            "Start from a known fuel figure and note it.",
            "Drive normal race pace with your normal lifting — not an economy run "
            "unless economy is what you plan to race.",
            "Keep every lap the same; a spin or a slow lap wastes the sample.",
        ),
        monitor=(
            "Fuel used per lap and how steady it is",
            "Whether short-shifting or lifting changes it meaningfully",
        ),
        fuel="Known starting load",
        tyre="Race compound",
        target_laps="8–12",
        push_level="Race pace with normal lift and coast",
        purpose="fuel",
        invalidation=(
            "A spin, an off or an unrepresentative slow lap",
            "Changing push level part-way through",
        ),
        reports=(
            "Litres per lap and how many laps a tank gives",
            "Whether you can run the race distance on the planned stops",
        ),
    ),
    "setup_race": RunBrief(
        domain="setup_race",
        run_name="long race run",
        objective="Long race run — prove the setup over a full stint, not one lap",
        how_to_drive=(
            "Full race fuel from the start — the car will feel different to a low-fuel run.",
            "Run a complete stint. Stopping early tells you nothing about the end of one.",
            "Hold race pace rather than qualifying pace.",
        ),
        monitor=(
            "How the balance changes as the fuel burns off",
            "Whether the pace holds to the end of the stint",
            "Whether the car is still driveable when the tyres are worn",
        ),
        fuel="Full race load",
        tyre="Race compound, starting fresh",
        target_laps="A full stint",
        push_level="Race pace you can hold to the end",
        purpose="race pace",
        invalidation=(
            "Ending the stint early",
            "Changing any setup value mid-run",
        ),
        reports=(
            "Pace over the stint and how much it fell away",
            "Fuel per lap at race load and the stint length it supports",
        ),
    ),
    "race_pace": RunBrief(
        domain="race_pace",
        run_name="long race run",
        objective="Long race run — establish the pace you can actually hold",
        how_to_drive=(
            "Full race fuel and a complete stint.",
            "Drive the pace you could hold for the whole race, not your best lap.",
            "Deal with traffic as you would in the race rather than backing out.",
        ),
        monitor=(
            "Whether your lap times hold or drift",
            "Where mistakes creep in as concentration drops",
        ),
        fuel="Full race load",
        tyre="Race compound",
        target_laps="A full stint",
        push_level="Sustainable race pace",
        purpose="race pace",
        invalidation=("Ending the stint early", "Switching to qualifying pace part-way"),
        reports=(
            "Your true average race pace and its spread",
            "How that pace compares with your single-lap best",
        ),
    ),
    "setup_qualifying": RunBrief(
        domain="setup_qualifying",
        run_name="qualifying simulation",
        objective="Qualifying simulation — out lap, one flying lap, in lap",
        how_to_drive=(
            "Minimum fuel: enough for the out lap, the flyer and the lap back in.",
            "Use the out lap to get the tyre into its window — that is its whole job.",
            "One flying lap only. A second lap on the same set is a different test.",
        ),
        monitor=(
            "Whether the tyre is in its window on the flying lap",
            "Peak grip compared with the race setup",
            "Anything that only bites when you commit fully on a single lap",
        ),
        fuel="Minimum — out, flyer, in",
        tyre="Fresh set, one warm-up lap",
        target_laps="3 (out · flyer · in)",
        push_level="Maximum on the flying lap only",
        purpose="qualifying",
        invalidation=(
            "Two flying laps on the same set",
            "Traffic on the flying lap",
        ),
        reports=(
            "Your single-lap potential on this setup",
            "Whether the qualifying setup is genuinely faster than the race one",
        ),
    ),
    "consistency": RunBrief(
        domain="consistency",
        run_name="practice run",
        objective="Practice run — how repeatable is your lap?",
        how_to_drive=(
            "Drive the pace you can repeat, not the pace you can reach once.",
            "Keep fuel and tyre state as steady as you can across the run.",
            "Do not chase a lap time — the spread is the result here.",
        ),
        monitor=(
            "The spread between your laps",
            "Whether mistakes cluster in the same corner",
        ),
        fuel="Constant",
        tyre="Constant compound and age",
        target_laps="8–12",
        push_level="Repeatable, not peak",
        purpose="consistency",
        invalidation=("Pushing for a single fast lap",),
        reports=(
            "Your consistency band and how it compares with previous runs",
            "The corners where your laps diverge most",
        ),
    ),
    "strategy": RunBrief(
        domain="strategy",
        run_name="strategy validation run",
        objective="Strategy run — does the plan's stint actually hold?",
        how_to_drive=(
            "Run the fuel load and compound the plan calls for — not a convenient one.",
            "Drive the plan's target pace, including its fuel saving if it assumes any.",
            "Complete the planned stint length.",
        ),
        monitor=(
            "Whether the fuel lasts the stint the plan assumes",
            "Whether the tyre lasts it too",
            "Your pace at the END of the stint, not the start",
        ),
        fuel="As the plan calls for",
        tyre="As the plan calls for",
        target_laps="The planned stint length",
        push_level="The plan's target pace",
        purpose="strategy",
        invalidation=(
            "Deviating from the planned fuel load or compound",
            "Cutting the stint short",
        ),
        reports=(
            "Whether the planned stint is achievable as written",
            "What the plan has to change if it is not",
        ),
    ),
    "convergence": RunBrief(
        domain="convergence",
        run_name="final confirmation run",
        objective="Confirmation run — prove the best-known setup, do not explore",
        how_to_drive=(
            "Change nothing. This run confirms what you already believe.",
            "Race fuel, race compound, race pace.",
            "If something feels wrong, that is a finding — do not fix it mid-run.",
        ),
        monitor=(
            "Whether the car repeats what the earlier runs showed",
            "Anything that contradicts what you have already established",
        ),
        fuel="Race load",
        tyre="Race compound",
        target_laps="6–10",
        push_level="Race pace",
        purpose="confirmation",
        invalidation=("Any setup change during the run",),
        reports=(
            "Whether the setup is confirmed or contradicted",
            "What is still unresolved before the event",
        ),
    ),
}


def brief_for_domain(domain: str) -> RunBrief:
    """The brief for an evidence domain. Unknown domains get an honest generic brief.

    The fallback deliberately does NOT invent domain-specific instructions: an
    unrecognised objective is a free practice run, and saying so is more useful than
    pretending it is a controlled test.
    """
    d = _norm(domain).lower()
    brief = _BRIEFS.get(d)
    if brief is not None:
        return brief
    return RunBrief(
        domain=d,
        run_name="practice run",
        objective="Practice run — general running",
        how_to_drive=(
            "No specific test is set, so drive a clean representative stint.",
            "Keep fuel, compound and push level steady so the laps are comparable.",
        ),
        monitor=("Anything the car does that you cannot explain",),
        fuel="Constant",
        tyre="Constant",
        target_laps="5–8",
        push_level="Representative pace",
        purpose="practice",
        invalidation=("A lock-up or off-track that skews the lap",),
        reports=("Your clean-lap pace, consistency and fuel per lap",),
    )


#: Preparation activity type value -> the domain whose brief describes that run. Used
#: to describe a run that has already been RECORDED, where the activity type is what
#: survives rather than the objective headline that started it.
_RUN_TYPE_DOMAIN: Dict[str, str] = {
    "baseline_practice": "setup_base",
    "setup_experiment": "working_window",
    "coaching_run": "driver_coaching",
    "tyre_test": "tyre_model",
    "fuel_test": "fuel_model",
    "qualifying_simulation": "setup_qualifying",
    "long_race_run": "setup_race",
    "strategy_validation_run": "strategy",
    "final_setup_confirmation": "convergence",
    "free_practice": "consistency",
    "official_practice": "consistency",
    "installation_run": "consistency",
}


def brief_for_run_type(activity_type: str) -> RunBrief:
    """The brief describing a recorded run, keyed by its preparation activity type."""
    return brief_for_domain(_RUN_TYPE_DOMAIN.get(_norm(activity_type).lower(), ""))


def known_domains() -> Tuple[str, ...]:
    """Every domain that has a specific brief. Sorted for stable display/tests."""
    return tuple(sorted(_BRIEFS))
