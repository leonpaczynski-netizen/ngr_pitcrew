"""What the driver can ask, and what the engineer is allowed to answer.

A bounded vocabulary, deliberately. Free-form speech recognition at racing
speed with a headset on is unreliable, and an engineer who confidently
mis-hears is worse than one who says "say again".

The rule that matters most: **an answer the app does not have is a refusal,
never a guess.** "I don't have fuel yet" is useful — the driver stops asking
and manages it himself. A fabricated number gets acted on.

**Not every intent is a question.** The REPORT family is the driver telling the
engineer something rather than asking, and it exists because CLAUDE.md §4.1 is
the standing rule of the whole programme — *the driver's report is primary
evidence, telemetry is corroboration* — and until these were added the app
could not receive any. A handling complaint went into the `radio` table as free
text tagged `unknown`, where nothing could find it again.

Reports are **acknowledged, never analysed out loud**. The engineer says copy
and writes it down beside what the feed was reading; see
`race/driver_report.py`. Telling him what a report means would be inventing the
meaning the record exists to collect evidence for.
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
# **The one calibration bridge that exists between his eyes and our feed.**
# GT7's HUD reddens the frame around each tyre as it heats - PD's own manual
# says so - and nobody has ever paired that colour with a telemetry value. He
# reports the event; the app writes down the degrees it was reading at that
# instant. See `race/hud_calibration.py`.
TYRES_RED = "tyres-red"
# **"Are we on the plan?"** - the lap-to-lap reference the driver asked for,
# answered from what the plan said it would execute against what it is
# executing. The fuel half is actionable; the pace half is confirmation only
# and is withheld entirely until it clears his own measured noise floor.
ON_PLAN = "on-plan"
# **The question this whole app is about, and it had no intent.** "How are my
# tyres" matched BOX_WHAT and was answered with the compound planned for the
# stop - a confident answer to a question he did not ask. It is answerable now
# because the live gauge reads wear off the HUD; when it is not reading, the
# honest answer is that it is not reading.
TYRES = "tyres"
# "What's my best lap" matched LAPS_LEFT, which answered "twelve to go".
PACE = "pace"

# --- the REPORT family: he tells the engineer, rather than asking it ---------
#
# **Two of these change what the app does and two only get written down**, and
# the split is deliberate. A handling complaint is evidence for a setup and
# nothing live may act on one: §4.1 makes it primary, and one observation is
# still one observation. An off or a spell in traffic is different - it makes
# the lap unrepresentative, and `laps.exclusion_reason` already exists for
# exactly that, with "traffic" named in the export contract's own example.
REPORT_UNDERSTEER = "report-understeer"
REPORT_OVERSTEER = "report-oversteer"
# **An incident excludes the lap.** Not because the app judges the driving, but
# because an aggregate that includes the lap he went off on describes a lap
# nobody drove on purpose - and CLAUDE.md is explicit that it is cheaper to
# explain an exclusion than to have a setup built on a misread aggregate.
REPORT_INCIDENT = "report-incident"
# **So is traffic**, for the same reason and with more force: he cannot drive
# his own line behind another car, so the lap measures the car in front.
REPORT_TRAFFIC = "report-traffic"
REPORTS = (REPORT_UNDERSTEER, REPORT_OVERSTEER, REPORT_INCIDENT,
           REPORT_TRAFFIC)

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
    # **Two jobs, and they used to be one.** These are the closed grammar SAPI
    # recognises *and* the reference points the semantic matcher measures
    # against, and they were written only for the first: terse keyword forms
    # like "fuel", "keep", "again" that a grammar matches exactly.
    #
    # Measured against the driver's own phrasing, that cost him the radio. Six
    # of twenty real questions landed beyond the act band and came back as
    # "did you mean...?", and the gap between real questions and unrelated
    # speech had gone **negative** - real questions reached 0.380 while "the
    # dog wants to go out" sat at 0.330. Nearest-neighbour matching is only as
    # good as what it is near, and nothing here was near how he talks.
    #
    # So every intent now carries the natural forms as well as the terse ones.
    # The terse forms stay: they are what the grammar needs, and they cost
    # nothing.
    FUEL: ("fuel", "how much fuel", "fuel left", "enough fuel",
           "how's my fuel", "hows my fuel", "how is my fuel",
           "how much fuel have i got", "give me a fuel update",
           "what's my fuel", "where's my fuel", "fuel update",
           "have i got enough fuel", "am i ok on fuel"),
    POSITION: ("position", "where am i", "what position",
               "what position am i in", "where am i running",
               # Measured: reached `laps-left` without this, and it predates
               # the report family - the two intents have always been close.
               "where am i in the race", "what place am i in"),
    LAPS_LEFT: ("laps left", "how long", "how many laps", "time left",
                "laps remaining", "to go", "how many laps left",
                "how many laps to go", "how much longer",
                "how many laps are left", "what lap am i on",
                "what lap is this", "how far into the race are we"),
    BOX_WHEN: ("when do i box", "when box", "box when", "pit when",
               "when do i pit", "when am i boxing", "when am i stopping",
               "how far to the stop", "how many laps to the stop",
               "when's my stop", "whens my stop", "do i box this lap",
               "box this lap", "am i boxing soon", "when's the pit stop",
               "when do i come in", "what lap do i come in",
               "do i come in soon", "am i coming in"),
    BOX_WHAT: ("what tyres", "which tyres", "what tires", "which compound",
               "what compound", "what tyres am i taking",
               "which tyres at the stop", "what am i fitting",
               "what compound at the stop", "what's going on the car"),
    BOX_FUEL: ("how much fuel do i take", "fuel to take", "how much to take",
               "fuel in the stop", "how much fuel at the stop",
               "how many litres do i take", "what's my fuel target",
               "how much am i putting in"),
    PLAN: ("what's the plan", "whats the plan", "the plan", "strategy",
           "remind me of the plan", "what's the strategy",
           "run me through the plan", "tell me the plan",
           "what are we doing", "what's my race plan"),
    ACCEPT: ("accept", "do it", "yes do it", "agreed", "copy that",
             "go ahead", "let's do it", "confirmed", "affirmative",
             "yeah do that"),
    KEEP: ("keep", "stay out", "negative", "keep the plan",
           "i'll stay out", "staying out", "leave it",
           "stick with the plan", "no change"),
    REPEAT: ("say again", "repeat", "again", "say that again",
             "i missed that", "come again", "one more time"),
    TYRES_RED: ("tyres are red", "tires are red", "tyres red", "tires red",
                "gone red", "went red", "frame is red",
                "the gauge has gone red", "tyres are in the red",
                "my tyres are red"),
    TYRES: ("how are my tyres", "how are my tires", "tyre wear",
            "how are the tyres", "what's my tyre wear",
            "how much wear have i got", "what's the tyre situation",
            "are the tyres going off", "talk to me about the tyres",
            "how are the tyres holding up", "how worn are my tyres",
            "tyre update", "give me a tyre update", "worst tyre",
            "how much life is in the tyres", "how much life is left",
            "have the tyres got life left",
            # **The axle forms, added because a report phrase outranked
            # them.** Measured: "how shot are the fronts" sat 0.290 from
            # "the front won't bite" and only 0.505 from "how are the tyres",
            # so a WEAR question was being recorded as a HANDLING report. The
            # fix is on the question side - "the front won't bite" is exactly
            # how he would report understeer and deleting it would cost more.
            # Note the shape that separates them: a question opens with "how
            # are"/"how shot", a report is a statement about the car.
            "how are the fronts", "how are the rears",
            "how shot are the fronts", "how shot are the tyres",
            "how much is left on the fronts",
            "how much is left on the rears"),
    PACE: ("what's my pace", "how's my pace", "hows my pace",
           "what's my best lap", "am i quick enough", "how's my lap time",
           "am i on pace", "what's my lap time", "how am i doing on pace",
           "am i losing time"),
    # **Measured 22 Aug 2026, after the REPORT family took the vocabulary from
    # 57 phrases to 230.** The bands in `gate.py` were calibrated against the
    # smaller list, and more reference phrases means smaller distances for
    # everything - so the question was never "are reports recognised" but "did
    # adding them break the questions that already worked".
    #
    # Twenty-six held-out probes, none of them in this file, thirteen of them
    # questions that already worked: **26/26 to the right intent, all inside
    # the act band.** Four collisions had to be fixed to get there, and each
    # one is commented where it was fixed. The most instructive:
    #
    # * **"how shot are the fronts" was being recorded as a handling report.**
    #   It sat 0.290 from "the front won't bite" and only 0.505 from "how are
    #   the tyres" - so a question about WEAR became a statement about
    #   BALANCE. Fixed on the question side, because "the front won't bite" is
    #   exactly how he would report understeer. The shape that separates them
    #   is worth knowing: a question opens "how are" / "how shot"; a report is
    #   a statement about the car.
    #
    # **Unrelated speech still lands in the act band and that is unchanged
    # doctrine** - see the note above the bands, which sets them on the cost of
    # being wrong because no separation exists. But the cost is no longer
    # symmetric: a stray sentence reaching `report-incident` strikes a lap,
    # where before the worst case was one answer he ignores. Two things carry
    # it: the engineer names the lap out loud so he hears which one went, and
    # the lap rack's Strike/Restore puts it back. It is the reason those two
    # reports name a lap at all.
    #
    # **The report vocabulary is how he actually complains, not how a
    # textbook does.** "Understeer" is in here because it is unambiguous, but
    # nobody says it at racing speed - "no front end", "it's pushing", "won't
    # turn in" is what comes over the radio, and the semantic matcher is only
    # as good as what it is near.
    #
    # Kept clear of `TYRES`, which is a question about wear: "the fronts are
    # gone" would be either, so it is in neither.
    # **"i've got no front" and "nothing from the front" were here and are
    # gone.** Measured: they pulled "how shot are the fronts" - a question
    # about WEAR that the gate's own band note names as a success case for
    # `tyres` - onto understeer at 0.290. A phrase that steals a question the
    # app already answered correctly costs more than it adds.
    REPORT_UNDERSTEER: ("understeer", "understeering", "no front end",
                        "it's pushing", "its pushing", "the front is pushing",
                        "pushing on entry", "won't turn in", "wont turn in",
                        "no turn in", "washing out", "washing wide",
                        "running wide", "the front won't bite",
                        "it won't rotate", "it wont rotate", "won't rotate",
                        "no rotation"),
    REPORT_OVERSTEER: ("oversteer", "oversteering", "the rear is loose",
                       "rear is loose", "loose on exit", "it's snapping",
                       "its snapping", "the back stepped out",
                       "stepped out", "no rear grip", "no grip at the rear",
                       "the rear is gone", "it's oversteering on exit",
                       "spinning up", "kicking out",
                       # Measured: "the back end is coming round on me"
                       # reached `report-traffic` without these.
                       "the back end is coming round", "coming round on me",
                       "the back is coming round", "snap oversteer"),
    REPORT_INCIDENT: ("i went off", "went off", "i had a moment",
                      "had a moment", "i spun", "spun it", "off track",
                      "i went wide", "had contact", "i got hit",
                      "hit the wall", "in the gravel", "that lap was ruined",
                      "scrap that lap",
                      # Measured: "i just put two wheels on the grass" reached
                      # `tyres-red` without these - grass and red frames sit
                      # closer together than they have any business doing.
                      "on the grass", "two wheels on the grass",
                      "in the grass", "off the track", "i ran wide and lost it"),
    REPORT_TRAFFIC: ("traffic", "i'm in traffic", "im in traffic",
                     "stuck behind", "stuck behind him", "held up",
                     "i got held up", "can't get past", "cant get past",
                     "backmarker", "lapping traffic", "boxed in"),
    ON_PLAN: ("are we on the plan", "on the plan", "how's the burn",
              "hows the burn", "fuel burn", "on target",
              "am i saving enough", "is the saving working",
              "am i on target", "how's the burn looking",
              "do i need to save fuel", "am i where i should be"),
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


# What the engineer says back to a report. Short, and it never says what the
# report MEANS - see the module docstring. The two that exclude a lap name the
# lap, because the driver is the only one who can tell the engineer it picked
# the wrong one, and he cannot do that if he was not told which.
_REPORT_REPLY = {
    REPORT_UNDERSTEER: "Copy, understeer noted.",
    REPORT_OVERSTEER: "Copy, oversteer noted.",
}


def _report_answer(intent: str, snapshot: dict) -> Answer:
    """Acknowledge a report. Never analyse one."""
    plain = _REPORT_REPLY.get(intent)
    if plain is not None:
        return Answer(plain, intent)

    what = "Traffic" if intent == REPORT_TRAFFIC else "Noted"
    # The lap being driven, never the last one completed - see `lapInProgress`
    # on the coordinator's snapshot for what the difference cost.
    lap = snapshot.get("lapInProgress")
    if not lap:
        # **No lap number is not a failure to record it.** The report is still
        # written; the engineer just cannot say which lap comes out, so it
        # does not claim one. A confident wrong lap number is worse than none,
        # because it is the number he would correct against.
        return Answer(f"Copy. {what} - this lap is out.", intent)
    return Answer(f"Copy. {what} - lap {lap} is out.", intent)


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

    if intent in REPORTS:
        return _report_answer(intent, snapshot)

    if intent == TYRES_RED:
        # Acknowledged, never analysed out loud. One observation is one
        # observation, and telling him what it means would be inventing the
        # meaning this file exists to collect evidence for.
        return Answer("Copy, noted with the temperatures.", intent)

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

    if intent == ON_PLAN:
        return Answer(_on_plan(snapshot), intent,
                      answered=snapshot.get("burnVsPlanPct") is not None)

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

    if intent == TYRES:
        worst = snapshot.get("wearWorst")
        if worst is None:
            # **Never modelled here.** `CLAUDE.md` §3.3: there is no tyre wear
            # channel, and a number invented in answer to a direct question is
            # the worst place in the app to invent one - he asked precisely
            # because he wanted to know.
            return Answer("No tyre gauge - read it to me.", intent,
                          answered=False)
        corner = (snapshot.get("wearCorner") or "").upper()
        where = f"{corner} " if corner else "Worst "
        said = f"{where}{worst * 100:.0f} percent."
        stint = snapshot.get("lapsToStop")
        if stint is not None and stint > 0:
            said += f" {_laps(stint)} to the box."
        return Answer(said, intent)

    if intent == PACE:
        # `paceIsReal` is the noise gate: his lap-to-lap spread puts the
        # detection floor above the whole degradation band, so a pace figure
        # that has not cleared it is not a finding and must not sound like one.
        delta = snapshot.get("paceVsPlanMs")
        if delta is None:
            return Answer("No pace reference yet.", intent, answered=False)
        if not snapshot.get("paceIsReal"):
            return Answer("Pace is inside the noise - nothing to call.",
                          intent)
        seconds = abs(delta) / 1000.0
        way = "up on" if delta < 0 else "down on"
        return Answer(f"{seconds:.1f} {way} the plan.", intent)

    return Answer("Say again.", UNKNOWN, answered=False)


def _on_plan(snapshot: dict) -> str:
    """The race against what the plan expected, in one sentence.

    **The two halves are not symmetric and the answer says so.** Burn is the
    low-noise channel and it is quoted as a percentage he can act on. Pace is
    quoted only when the deviation clears the noise floor measured on this
    car at this circuit - inside that floor the honest answer is that the app
    cannot tell, and a number would be read as a trend.
    """
    burn = snapshot.get("burnVsPlanPct")
    if burn is None:
        return "I don't have the burn against the plan yet."
    direction = "over" if burn > 0 else "under"
    said = f"Burn {abs(burn):.0f} percent {direction} plan."
    if snapshot.get("paceIsReal"):
        pace = snapshot.get("paceVsPlanMs") or 0
        said += (f" Pace {abs(pace) / 1000.0:.1f} a lap "
                 f"{'down' if pace > 0 else 'up'}.")
    else:
        floor = snapshot.get("paceDetectableMs")
        said += (f" Pace is inside the {floor / 1000.0:.1f} a lap I can see."
                 if floor else " Pace not measurable yet.")
    return said


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
