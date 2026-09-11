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
# **An intent whose only job is to refuse by name, and it earns its place.**
# The feed carries this car and nothing else - no opponent position, no gap, no
# closing speed (§3.2/§3.3) - so "how far behind is he" has no answer and never
# will from telemetry. Without an intent it did not fall silent, which would at
# least be honest: it reached `position` and came back "you're fifth", which
# answers a question he did not ask, or it reached a report intent and was
# written into the ledger as a handling complaint.
#
# `intents.py`'s own rule is that an answer the app does not have is a refusal
# and never a guess, and that a refusal is useful - "I don't have fuel yet"
# lets him stop asking and manage it himself. A refusal that names its reason
# is the same thing done properly: he learns once that the app cannot see other
# cars, and never spends another press on it.
GAP = "gap"

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
# **What went on at the stop, from the only instrument that always knows.**
# The swap detector missed the Deep Forest change and the gauge needs two
# readings to settle it; he knows the moment he leaves the box.
REPORT_NEW_TYRES = "report-new-tyres"
REPORT_NO_TYRES = "report-no-tyres"
REPORTS = (REPORT_UNDERSTEER, REPORT_OVERSTEER, REPORT_INCIDENT,
           REPORT_TRAFFIC, REPORT_NEW_TYRES, REPORT_NO_TYRES)

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
           "have i got enough fuel", "am i ok on fuel",
           # **Measured: "am i going to run out" reached `pace` at 0.340.**
           # Every phrase above names fuel as a noun; the way he actually
           # worries about it is as an outcome - running out, making it,
           # being short - and none of those words were anywhere near this
           # intent.
           "will i make it on fuel", "can i make the end on fuel",
           "am i short on fuel", "will the fuel last",
           "do i have enough to finish", "is fuel going to be tight",
           "how many laps of fuel do i have"),
    POSITION: ("position", "where am i", "what position",
               "what position am i in", "where am i running",
               # Measured: reached `laps-left` without this, and it predates
               # the report family - the two intents have always been close.
               "where am i in the race", "what place am i in",
               # Measured: "am i still in the points" reached `on-plan` at
               # 0.352 - "am i still..." is the shape of a status question and
               # `on-plan` owned that shape alone.
               "am i still in the top ten", "am i still in the points",
               "have i gained any places", "did i lose a place",
               "how many cars are ahead of me", "what place am i running"),
    LAPS_LEFT: ("laps left", "how long", "how many laps", "time left",
                "laps remaining", "to go", "how many laps left",
                "how many laps to go", "how much longer",
                "how many laps are left", "what lap am i on",
                "what lap is this", "how far into the race are we",
                "how many more to go", "what's left to run",
                "how many laps in this race", "how many have i got left"),
    BOX_WHEN: ("when do i box", "when box", "box when", "pit when",
               "when do i pit", "when am i boxing", "when am i stopping",
               "how far to the stop", "how many laps to the stop",
               "when's my stop", "whens my stop", "do i box this lap",
               "box this lap", "am i boxing soon", "when's the pit stop",
               "when do i come in", "what lap do i come in",
               "do i come in soon", "am i coming in",
               "which lap is the stop", "how far away is the stop",
               "is the stop soon", "am i due in", "what lap is my stop"),
    BOX_WHAT: ("what tyres", "which tyres", "what tires", "which compound",
               "what compound", "what tyres am i taking",
               "which tyres at the stop", "what am i fitting",
               "what compound at the stop", "what's going on the car",
               # Measured: "what am i going onto" reached `plan` at 0.299.
               # "what am i..." belonged to no intent here, and `plan` is the
               # catch-all for a question about what happens next.
               "what am i going on", "what am i changing to",
               "what tyre goes on", "which compound am i getting",
               "what rubber goes on", "what am i fitting at the stop"),
    BOX_FUEL: ("how much fuel do i take", "fuel to take", "how much to take",
               "fuel in the stop", "how much fuel at the stop",
               "how many litres do i take", "what's my fuel target",
               "how much am i putting in", "how much goes in",
               "what's going in the tank", "how many litres at the stop"),
    PLAN: ("what's the plan", "whats the plan", "the plan", "strategy",
           "remind me of the plan", "what's the strategy",
           "run me through the plan", "tell me the plan",
           "what are we doing", "what's my race plan",
           # **Measured: "run me through it again" reached `repeat` at 0.258
           # and "what are we doing about the stop" reached `box-when` at
           # 0.269.** The word "again" belonged entirely to `repeat`, and any
           # mention of the stop pulled to `box-when`. Both are the plan.
           "go through the plan again", "run the plan by me again",
           "remind me what we're doing", "talk me through the strategy",
           "what are we doing about the stop", "what's the whole plan"),
    ACCEPT: ("accept", "do it", "yes do it", "agreed", "copy that",
             "go ahead", "let's do it", "confirmed", "affirmative",
             "yeah do that"),
    KEEP: ("keep", "stay out", "negative", "keep the plan",
           "i'll stay out", "staying out", "leave it",
           "stick with the plan", "no change"),
    REPEAT: ("say again", "repeat", "again", "say that again",
             "i missed that", "come again", "one more time",
             # Held apart from `plan` deliberately: `repeat` is about the last
             # thing the engineer said, not about the strategy. These name the
             # hearing rather than the content.
             "i didn't hear you", "what did you say", "what was that",
             "didn't catch that"),
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
            "how much is left on the rears",
            # **The worst collision measured: "have the rears gone" reached
            # `report-oversteer` at 0.124** - closer than any correct match in
            # the whole probe set. A question about tyre LIFE was being filed
            # as a driver report about the CAR, so the engineer would have said
            # "copy, noted" and written down a handling complaint he never
            # made. The axle words alone do not separate them; the verb does.
            # "Gone", "done", "finished", "left" are about wear.
            "have the tyres gone", "have the fronts gone",
            "are the rears gone", "are the tyres done",
            "are the fronts done", "are they finished",
            "is there life left in the tyres",
            "is there anything left in the rears",
            "are the tyres past it", "how much have they worn"),
    PACE: ("what's my pace", "how's my pace", "hows my pace",
           "what's my best lap", "am i quick enough", "how's my lap time",
           "am i on pace", "what's my lap time", "how am i doing on pace",
           "am i losing time",
           # **Measured: "was that a good lap" reached `laps-left` at 0.240.**
           # This is the collision already fixed once, for "what's my best
           # lap", come straight back in a different phrasing: the word "lap"
           # belongs to `laps-left` unless something here claims it. These
           # claim the lap he has just driven, which is a different thing from
           # the laps he has left.
           "how was that lap", "was that lap any good", "was that quick",
           "how quick was that lap", "am i improving",
           "am i faster or slower", "what did i just do"),
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
                        "no rotation",
                        # **Measured: "the front just washes out" reached
                        # `report-oversteer` at 0.219** - the word "washing"
                        # was here but every form of it was a bare participle,
                        # and a sentence with a subject and a verb matched the
                        # oversteer phrases, which are all full sentences. The
                        # two report intents are each other's nearest
                        # neighbours, so each needs the other's sentence shape.
                        "the front washes out", "it washes wide",
                        "the front is washing", "it's pushing wide",
                        "i can't get it turned", "it just runs wide",
                        "the front end is gone"),
    REPORT_OVERSTEER: ("oversteer", "oversteering", "the rear is loose",
                       "rear is loose", "loose on exit", "it's snapping",
                       "its snapping", "the back stepped out",
                       "stepped out", "no rear grip", "no grip at the rear",
                       "the rear is gone", "it's oversteering on exit",
                       "spinning up", "kicking out",
                       # Measured: "the back end is coming round on me"
                       # reached `report-traffic` without these.
                       "the back end is coming round", "coming round on me",
                       "the back is coming round", "snap oversteer",
                       # **Measured: "i nearly lost it" reached
                       # `report-incident` at 0.312.** A near-miss is a
                       # handling report; an incident is something that
                       # happened. "Nearly", "almost" and "caught it" are the
                       # words that separate a moment he saved from one he did
                       # not, and `report-incident` owned all of them.
                       "i nearly lost it", "i nearly lost the back",
                       "it nearly went round", "i caught a slide",
                       "i almost spun it", "it's snapping on me",
                       "the rear won't stay put"),
    REPORT_NEW_TYRES: ("new tyres", "took tyres", "fresh tyres",
                       "changed tyres", "i took tyres", "new set",
                       "fresh set on", "tyres changed"),
    REPORT_NO_TYRES: ("no tyres", "fuel only", "kept the tyres",
                      "same tyres", "didn't take tyres", "no new tyres",
                      "stayed on the same set"),
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
                     "backmarker", "lapping traffic", "boxed in",
                     # **Measured: "there's a train of cars in front" reached
                     # `report-understeer` at 0.369** - on the word "front",
                     # which this intent never used and understeer uses in
                     # every phrase. Traffic is about other cars, and nothing
                     # here said so in a full sentence.
                     "there's a train in front", "there's a queue of cars",
                     "i'm behind a train", "there are cars in front of me",
                     "i'm being held up", "stuck in a queue",
                     "i can't get through this traffic",
                     # Measured: "i'm stuck behind someone" reached `gap` at
                     # 0.260, because "someone" reads as a reference to
                     # another car and every `gap` phrase names one. The
                     # difference is that this is a report - he is telling the
                     # engineer he is being held up, which strategy can act on
                     # - where `gap` is a question about a number nobody has.
                     "i'm stuck behind a car", "i'm stuck behind this guy",
                     "i've got someone holding me up",
                     "there's someone in my way"),
    # **Narrow, and the first draft was not.** It was written wide on the
    # reasoning that a wrong match INTO an unanswerable intent costs one honest
    # sentence while a wrong match out of it costs a confident wrong answer.
    # Measured, that was backwards: the wide version pulled "am i going to run
    # out" - a FUEL question - to 0.301 and "i'm stuck behind someone" to
    # 0.260, because generic motion phrases like "am i pulling away" and "am i
    # losing ground" are about no particular subject and therefore near
    # everything. **An unanswerable intent that is wide is a magnet, and what
    # it catches is questions that had answers.**
    #
    # So every phrase here names another car explicitly - "he", "him", "the car
    # ahead", "the next car" - or the word gap itself. That is the only thing
    # that makes the question genuinely about something the feed cannot see.
    GAP: ("what's the gap", "whats the gap", "how far behind is he",
          "how far ahead is he", "how far behind am i", "how far ahead am i",
          "who am i behind", "who's behind me", "whos behind me",
          "who's in front of me", "am i catching him", "is he catching me",
          "how far back is the next car", "can i catch him",
          "how close is he", "gap to the car ahead", "gap to the car behind",
          "how far up the road is he", "is he pulling away from me",
          "what's the gap to the car in front"),
    ON_PLAN: ("are we on the plan", "on the plan", "how's the burn",
              "hows the burn", "fuel burn", "on target",
              "am i saving enough", "is the saving working",
              "am i on target", "how's the burn looking",
              "do i need to save fuel", "am i where i should be",
              "are we on track", "am i ahead or behind the plan",
              "am i using too much fuel", "is my burn ok",
              "should i be lifting", "do i need to lift and coast"),
}

# Longest phrases first: "how much fuel do i take" must win over "fuel".
_ORDERED = sorted(
    ((phrase, intent) for intent, phrases in PHRASES.items()
     for phrase in phrases),
    key=lambda pair: len(pair[0]), reverse=True)

# Whatever the driver said, as words. Apostrophes are kept ("what's the plan"
# is a phrase); everything else that is not a letter or a digit separates.
_WORDS = re.compile(r"[a-z0-9']+")

# **Which car each GAP question is about.** The answer is one car (§5.5), so
# the question has to be read for its side - and the inverted pairs are the
# trap: "how far ahead am I" is about the car BEHIND, "how far behind am I"
# about the car ahead. `None` is a question that names neither, answered with
# the nearer car. `test_every_gap_phrase_is_classified` holds this against
# `PHRASES[GAP]`, so a phrase added there without a side fails a test.
GAP_SIDES = {
    "what's the gap": None, "whats the gap": None, "how close is he": None,
    "how far ahead is he": "ahead", "how far behind am i": "ahead",
    "who am i behind": "ahead", "who's in front of me": "ahead",
    "am i catching him": "ahead", "can i catch him": "ahead",
    "gap to the car ahead": "ahead", "how far up the road is he": "ahead",
    "is he pulling away from me": "ahead",
    "what's the gap to the car in front": "ahead",
    "how far behind is he": "behind", "how far ahead am i": "behind",
    "who's behind me": "behind", "whos behind me": "behind",
    "is he catching me": "behind", "how far back is the next car": "behind",
    "gap to the car behind": "behind",
}


def gap_side(heard: str | None) -> str | None:
    """"ahead", "behind", or None where the question names neither.

    Whole-word runs, longest phrase first, exactly as `match_intent` reads -
    so "what's the gap to the car in front" is not taken for "what's the
    gap". A question the matcher reached semantically, in words none of these
    contain, names no side and gets the nearer car.
    """
    if not heard:
        return None
    words = _WORDS.findall(heard.lower())
    for phrase in sorted(GAP_SIDES, key=len, reverse=True):
        wanted = _WORDS.findall(phrase)
        for start in range(len(words) - len(wanted) + 1):
            if words[start:start + len(wanted)] == wanted \
                    and GAP_SIDES[phrase] is not None:
                return GAP_SIDES[phrase]
    # **A side named in other words** (critic 3): "what's the gap behind"
    # reached GAP through the literal matcher, named no phrase above with a
    # side, and was answered with the car ahead. The inverted pairs ("how
    # far ahead am I") are phrases and have already won; "am I" anywhere
    # else is a question about us and names no side.
    if "am" in words and "i" in words:
        return None
    if "behind" in words or "back" in words:
        return "behind"
    if "ahead" in words or "front" in words:
        return "ahead"
    return None


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
    REPORT_NEW_TYRES: "Copy, new tyres.",
    REPORT_NO_TYRES: "Copy, no tyres.",
}


def _gap_answer(intent: str, snapshot: dict,
                heard: str | None = None) -> Answer:
    """One car, from the pit wall's last reading, in the board's words.

    **One car, not a table** (§5.5, carried from row 1.10). It answered
    "Ahead: Boxhead, 3.4 seconds, closing 0.8 seconds a lap. Behind: the car
    behind, 10.2 seconds, opening 0.3 seconds a lap." - two cars, two rates,
    and "closing" meaning opposite driving on the two sides. The question is
    read for its side (`gap_side`); one that names neither gets the nearer.

    **And the board's floor, through the board's rule** (rules 12 and 13).
    This said "closing" above 0.1 s a lap with no lap count while the board
    said "steady" below `TREND_WORTH_SAYING_S` (0.8) or under five laps -
    the ear and the eye disagreeing about one car. `gaps.trend_words` is the
    one expression both read.
    """
    from pitcrew.race.gaps import trend_words

    read = {}
    for side in ("ahead", "behind"):
        key = f"gap{side.capitalize()}"
        gap = snapshot.get(f"{key}S")
        # **Zero or less is not a reading**, as `_chase` has it: "0.0
        # seconds ahead" was spoken and chosen as the nearer car (critic 3).
        if gap is not None and gap > 0:
            read[side] = (gap, snapshot.get(f"{key}Name"),
                          snapshot.get(f"{key}ClosingSPerLap"),
                          snapshot.get(f"{key}TrendLaps"))
    asked = gap_side(heard)
    if read:
        if asked is not None and asked not in read:
            # **Never the other car for the one he asked about.** Answering
            # "who's behind me" with the car ahead is a figure about the
            # wrong man, said as though it were the right one.
            return Answer(f"Nothing read {asked} yet. Ask again on the next "
                          "straight.", intent, answered=False)
        side = asked or min(read, key=lambda s: abs(read[s][0]))
        gap, name, rate, laps = read[side]
        # A gap under a twentieth reads "0.0" at one decimal - a measurement
        # spoken as nothing (rule 9's shape), so it is said as what it is.
        amount = (f"{gap:.1f} seconds" if gap >= 0.05
                  else "within a tenth of a second")
        who = (f"{name} is {amount} {side}" if name
               else f"The car {side} is {amount} away")
        # **No rate at all is not "steady"** (critic 3, rule 3): a single
        # reading, or a rate with no lap count, is no slope - so no clause.
        # A slope through too few laps IS "steady", the board's pinned word.
        if rate is None or laps is None:
            return Answer(f"{who}.", intent, answered=True)
        words = trend_words(side, rate, laps)
        clause = words.spoken if words is not None else "steady"
        return Answer(f"{who} - {clause}.", intent, answered=True)
    if not snapshot.get("wallRunning"):
        # One sentence for one fact, the same one the brief says and the
        # arming path says late (row 1.10): two wordings are two clips and
        # two claims.
        from pitcrew.race.brief import NO_RIVALS

        return Answer(f"No pit wall this session. {NO_RIVALS} "
                      f"Ask me for position.", intent, answered=False)
    return Answer("No gap read yet - the wall has nothing this lap. "
                  "Ask again on the next straight.", intent, answered=False)


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
           pending_replan: str | None = None,
           heard: str | None = None) -> Answer:
    """Answer from what the race actually knows. Never invents a number."""
    if intent == UNKNOWN:
        return Answer("Say again.", intent, answered=False)

    if intent in REPORTS:
        return _report_answer(intent, snapshot)

    if intent == GAP:
        # **The one refusal that is permanent, so it says so.** Every other
        # "I don't have that" here is about this moment - no plan yet, no fuel
        # rate yet, the gauge is not reading - and inviting him to ask again in
        # a few laps is right for those. This one will not change: the feed
        # carries one car. Telling him the reason once is worth more than
        # telling him "say again" every time, and it is the difference between
        # an engineer who cannot see the timing screen and one who is broken.
        # **Reworded 29 Aug 2026: the refusal is narrower than it was.** The
        # feed carries no gap, no closing speed and no rival, and that part is
        # permanent. What it does carry, and what this used to under-claim, is
        # where he is IN THE FIELD - position and car count, both live since
        # the position wiring landed. So the line names what he can have
        # instead, which is the whole point of refusing by name.
        #
        # **Fixed text, deliberately.** It is pre-rendered in the phrase
        # manifest because it is spoken often and a pause at the moment he has
        # just failed to get an answer lands on the one exchange that has
        # already gone wrong. Interpolating the position here would make every
        # utterance unique and send all of them to live synthesis.
        # **Reworded again, 7 Sep 2026: the refusal was false.** The feed
        # carries one car, and that is still true - but the pit wall reads
        # GT7's own leaderboard off the screen, and at Deep Forest it read
        # 154 gap frames through the 7-lap chase for P2 while this line told
        # the driver there were none. So the answer comes from the wall's
        # reading when there is one, names both cars, and gives the closing
        # rate where five laps have said so. The refusal survives only for
        # the session with no wall at all, and it says which.
        # What he actually said, because "who's behind me" and "am I
        # catching him" are the same intent and different cars.
        return _gap_answer(intent, snapshot, heard)

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
        # **Out of how many.** The field size has been in the packet all
        # along; without it "P8" is a number he cannot place, and P8 of 9 is
        # a different race from P8 of 20.
        #
        # Rendered by `calls.position_line`, which the engineer's own
        # unprompted position call uses too. One renderer, so the answer he
        # asks for and the one he is given cannot say it two ways - and so
        # the voice pack has one family to enumerate rather than two.
        from pitcrew.race.calls import position_line

        return Answer(position_line(position, snapshot.get("fieldSize")),
                      intent)

    if intent == LAPS_LEFT:
        return _how_much_longer(snapshot, intent)

    if intent == FUEL:
        # **The same words the engineer volunteers, off the same expression**
        # (row 1.10). This answered "8.2 laps of fuel" - an absolute - in the
        # noun phrase the volunteered call uses for a MARGIN, with no
        # reference on it. Heard as a margin with ten laps to run, 8.2 means
        # believing in slack that is really minus one point eight.
        in_hand = snapshot.get("fuelInHand")
        reference = snapshot.get("fuelReference")
        if in_hand is not None and reference:
            return Answer(f"{in_hand:.1f} laps of fuel in hand {reference}.",
                          intent)
        laps_of_fuel = snapshot.get("lapsOfFuel")
        if laps_of_fuel is None:
            return Answer("I don't have a fuel rate yet.", intent,
                          answered=False)
        # No reference to be a margin to - so the absolute, said as one.
        return Answer(f"{laps_of_fuel:.1f} laps of fuel in the tank.", intent)

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
            # One noun for one quantity (row 1.10): the colour tier and
            # `_box_soon` both say "to the stop".
            said += f" {_laps(stint)} to the stop."
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
        # Seconds a lap, said as such: `_on_plan` renders the same figure
        # as "Pace 0.8 a lap down." and this said "0.8 down on the plan",
        # which does not say it is per lap at all (row 1.10).
        return Answer(f"{seconds:.1f} seconds a lap {way} the plan.", intent)

    return Answer("Say again.", UNKNOWN, answered=False)


# Past this fraction of a timed race he wants the laps as well as the clock.
# **Restated from `calls.LAPS_FROM_FRACTION` rather than imported**, and
# asserted equal to it in the tests: the same rule, on the same driver's
# request of 28 Aug 2026, reached over two different roads - what the engineer
# volunteers, and what he answers when asked.
LAPS_FROM_FRACTION = 0.5


def _clock(seconds: float) -> str:
    """The clock, in the unit he thinks in, rounded the safe way.

    **Rounded DOWN, never to nearest**, exactly as `calls.minutes_left` does
    and for the same reason: at 91 s, to-nearest says "2 minutes" and
    overstates by a third of a lap at the moment of the race where a third of
    a lap decides whether he takes another one.
    """
    if seconds < 100:
        return f"{max(0, int(seconds))} seconds"
    minutes = int(seconds // 60)
    return "1 minute" if minutes == 1 else f"{minutes} minutes"


def _how_much_longer(snapshot: dict, intent: str) -> Answer:
    """"How long left" - answered from the clock where there IS one.

    **This used to answer a timed race in laps, and the laps are the derived
    figure.** `remainingS` is the app's own timer, started at the green and
    reconciled against GT7's exact lap figures; the lap count divides it by a
    noisy median and is wrong whenever the median is. Quoting the inference
    and withholding the measurement, to a driver who asked "how long", is
    rule 5 in the one place he cannot check it.

    A lap race has no clock and its lap count is a regulation rather than an
    estimate, so there the laps ARE the measurement and are quoted alone.
    """
    remaining = snapshot.get("lapsRemaining")
    seconds = snapshot.get("remainingS")
    timed = bool(snapshot.get("raceMinutes"))

    if not timed:
        if remaining is None:
            return Answer("I don't know the race length.", intent,
                          answered=False)
        return Answer(f"{_laps(remaining)} to go.", intent)

    if seconds is None:
        # `calls.NO_CLOCK`'s case, and said rather than skipped: with GT7's
        # race HUD off, a race with no clause about its own length is
        # indistinguishable from one with no end.
        if remaining is None:
            return Answer("I don't have the clock.", intent, answered=False)
        return Answer(f"No clock. About {_laps(remaining)} to go.", intent,
                      answered=False)

    said = f"{_clock(seconds)} left."
    # The lap count joins the clock only once it has firmed up. Early in a
    # timed race the estimate flips on a median error far smaller than the
    # spread, so it would change every crossing while the clock did not.
    if remaining is not None and snapshot.get("lapsEstimateFirm"):
        said = f"{said} {_laps(remaining)} to go."
    return Answer(said, intent)


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
        said += (f" Pace {abs(pace) / 1000.0:.1f} seconds a lap "
                 f"{'down' if pace > 0 else 'up'}.")
    else:
        floor = snapshot.get("paceDetectableMs")
        said += (f" Pace is inside the {floor / 1000.0:.1f} seconds a lap "
                 f"I can see." if floor else " Pace not measurable yet.")
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
