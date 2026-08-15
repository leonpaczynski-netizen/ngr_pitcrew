"""What the driver can ask, and what the engineer is allowed to answer.

A bounded vocabulary, deliberately. Free-form speech recognition at racing
speed with a headset on is unreliable, and an engineer who confidently
mis-hears is worse than one who says "say again".

The rule that matters most: **an answer the app does not have is a refusal,
never a guess.** "I don't have fuel yet" is useful — the driver stops asking
and manages it himself. A fabricated number gets acted on.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

FUEL = "fuel"
POSITION = "position"
LAPS_LEFT = "laps-left"
BOX_WHEN = "box-when"
BOX_WHAT = "box-what"
BOX_FUEL = "box-fuel"
PLAN = "plan"
ACCEPT = "accept"
KEEP = "keep"
REPEAT = "repeat"
UNKNOWN = "unknown"

# Phrases the driver actually uses, mapped to intent. Matching is on whole
# words so "how much fuel" cannot be swallowed by a longer phrase containing it.
#
# **Nothing shorter than three letters belongs here.** `POSITION` carried `"p"`
# and `KEEP` carried `"no"`, which under the substring matching this file used
# to do meant "the front is pushing on entry" answered as a position and "I
# have no grip at the rear" as a refusal of a re-plan the driver never
# declined. They are gone, and matching is now what the line above always
# claimed it was.
PHRASES: dict[str, tuple[str, ...]] = {
    FUEL: ("fuel", "how much fuel", "fuel left", "enough fuel"),
    POSITION: ("position", "where am i", "what position"),
    LAPS_LEFT: ("laps left", "how long", "how many laps", "time left",
                "laps remaining", "to go"),
    BOX_WHEN: ("when do i box", "when box", "box when", "pit when",
               "when do i pit", "when am i boxing"),
    BOX_WHAT: ("what tyres", "which tyres", "what tires", "which compound",
               "what compound"),
    BOX_FUEL: ("how much fuel do i take", "fuel to take", "how much to take",
               "fuel in the stop"),
    PLAN: ("what's the plan", "whats the plan", "the plan", "strategy"),
    ACCEPT: ("accept", "do it", "yes do it", "agreed", "copy that"),
    KEEP: ("keep", "stay out", "negative", "keep the plan"),
    REPEAT: ("say again", "repeat", "again"),
}

# Longest phrases first: "how much fuel do i take" must win over "fuel".
_ORDERED = sorted(
    ((phrase, intent) for intent, phrases in PHRASES.items()
     for phrase in phrases),
    key=lambda pair: len(pair[0]), reverse=True)

# Whatever the driver said, as words. Apostrophes are kept ("what's the plan"
# is a phrase); everything else that is not a letter or a digit separates.
_WORDS = re.compile(r"[a-z0-9']+")


@dataclass(frozen=True)
class Answer:
    text: str
    intent: str
    answered: bool = True


def match_intent(heard: str) -> str:
    """Map recognised speech to one intent, or UNKNOWN.

    UNKNOWN is a real outcome and the engineer says "say again" rather than
    guessing at the closest match - which is only true if UNKNOWN is
    reachable. This used to be `if phrase in text`, a substring test, and with
    `"p"` and `"no"` in the phrase list almost nothing could fail to match:
    "the front is pushing on entry" came back as *position*, "blah blah
    nonsense" as *keep*. A phrase now has to appear as a run of whole words.
    """
    if not heard:
        return UNKNOWN
    words = _WORDS.findall(heard.lower())
    if not words:
        return UNKNOWN
    for phrase, intent in _ORDERED:
        wanted = _WORDS.findall(phrase)
        if not wanted:
            continue
        span = len(wanted)
        for start in range(len(words) - span + 1):
            if words[start:start + span] == wanted:
                return intent
    return UNKNOWN


def _laps(value) -> str:
    return "1 lap" if value == 1 else f"{value} laps"


# What the engineer says when the app has no plan at all, as distinct from a
# plan whose last stint runs to the flag. Both used to reach `lapsToStop is
# None` and both were answered "No stop planned. Running to the flag." - an
# assertion about a plan that does not exist. Arming with no plan is a
# supported state ("no plan - fuel calls only"), so this is a refusal in the
# §4.3 sense: missing is missing, never a confident zero.
NO_PLAN = "I don't have a plan."


def _has_plan(snapshot: dict) -> bool:
    """Whether the app has an approved plan to answer from.

    Absent means unknown, and unknown is a refusal rather than a claim in
    either direction: the snapshot has to say so, and until it does the honest
    answer is that the engineer does not have one.
    """
    return bool(snapshot.get("hasPlan"))


def answer(intent: str, snapshot: dict, *,
           last_call: str | None = None,
           pending_replan: str | None = None) -> Answer:
    """Answer from what the race actually knows. Never invents a number."""
    if intent == UNKNOWN:
        return Answer("Say again.", intent, answered=False)

    if intent == REPEAT:
        if not last_call:
            return Answer("Nothing to repeat.", intent, answered=False)
        return Answer(last_call, intent)

    if intent in (ACCEPT, KEEP):
        if not pending_replan:
            return Answer("Nothing to accept.", intent, answered=False)
        return Answer(
            "Copy, changing the plan." if intent == ACCEPT
            else "Copy, staying on the plan.", intent)

    if intent == POSITION:
        position = snapshot.get("position")
        if not position:
            return Answer("I don't have position.", intent, answered=False)
        return Answer(f"P{position}.", intent)

    if intent == LAPS_LEFT:
        remaining = snapshot.get("lapsRemaining")
        if remaining is None:
            return Answer("I don't know the race length.", intent,
                          answered=False)
        return Answer(f"{_laps(remaining)} to go.", intent)

    if intent == FUEL:
        laps_of_fuel = snapshot.get("lapsOfFuel")
        if laps_of_fuel is None:
            return Answer("I don't have a fuel rate yet.", intent,
                          answered=False)
        return Answer(f"{laps_of_fuel:.1f} laps of fuel.", intent)

    if intent == BOX_WHEN:
        to_stop = snapshot.get("lapsToStop")
        if to_stop is None:
            if not _has_plan(snapshot):
                return Answer(NO_PLAN, intent, answered=False)
            return Answer("No stop planned. Running to the flag.", intent)
        if to_stop <= 0:
            return Answer("Box this lap.", intent)
        return Answer(f"Box in {_laps(to_stop)}.", intent)

    if intent == BOX_WHAT:
        compound = snapshot.get("nextCompound")
        if not compound:
            if not _has_plan(snapshot):
                return Answer(NO_PLAN, intent, answered=False)
            return Answer("No tyre change planned.", intent)
        return Answer(f"{compound}.", intent)

    if intent == BOX_FUEL:
        litres = snapshot.get("stopFuelL")
        if litres is None:
            return Answer("I don't have a fuel target.", intent,
                          answered=False)
        return Answer(f"Fuel to {litres:.0f} litres.", intent)

    if intent == PLAN:
        if not _has_plan(snapshot):
            return Answer(NO_PLAN, intent, answered=False)
        return Answer(_plan_summary(snapshot), intent)

    return Answer("Say again.", UNKNOWN, answered=False)


def _plan_summary(snapshot: dict) -> str:
    """One sentence, because he is driving while he listens to it.

    Only called once there is a plan: "Running to the flag" is a statement
    about the last stint of one, not about their absence.
    """
    parts = []
    to_stop = snapshot.get("lapsToStop")
    if to_stop is None:
        parts.append("Running to the flag")
    elif to_stop <= 0:
        parts.append("Box this lap")
    else:
        parts.append(f"Box in {_laps(to_stop)}")
    if snapshot.get("nextCompound"):
        parts.append(f"onto {snapshot['nextCompound']}")
    remaining = snapshot.get("lapsRemaining")
    if remaining is not None:
        parts.append(f"{_laps(remaining)} to go")
    return ", ".join(parts) + "."


def known_phrases() -> list[str]:
    """Every phrase the recogniser should be primed with."""
    return [phrase for phrase, _ in _ORDERED]
