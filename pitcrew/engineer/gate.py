"""The confidence gate: deciding whether the engineer heard, or only thinks he did.

The closed SAPI grammar had one safety property, and it came for free: a
recogniser that can only return phrases from a list cannot return a phrase
that is not on it, so a misrecognition became "nothing heard" rather than a
confident wrong answer. Free dictation throws that away. This is what replaces
it.

`intents.py` states the rule this exists to honour: **an engineer who
confidently mis-hears is worse than one who says "say again".** But the
converse is not free either - a driver with his hands full can say "yes" in a
second, where repeating a question costs him a corner. So the middle band
**confirms rather than rejects**.

Six stages, cheapest first, each rejecting for a different reason - and each
reason is **spoken in its own words** (see `SPOKEN`), because the driver cannot
see a screen and "say again" is the same answer for all six.

0. **Audio present.** Did the capture device deliver anything at all? Not the
   same question as the next one: a device that is not there opens without
   error and delivers nothing, and telling him to speak up will not fix it.
1. **Speech present.** Was there any speech in the capture at all, or did the
   button get brushed? This is the stage that matters most: a recogniser given
   silence does not return silence, it hallucinates a plausible sentence, and
   a plausible sentence is exactly what the rest of the gate is bad at
   catching.
2. **Duration sane.** Too short to be a question, or longer than the capture
   limit.
3. **Something transcribed.** An empty transcript is a rejection, not an
   intent.
4. **Not a repeat loop.** An autoregressive decoder that loses its place emits
   the same token forever. Words per second of audio is the tell: nobody
   speaks at nine words a second.
5. **Meant something.** How close the transcript is, in meaning, to a phrase
   the engineer can actually answer. This is the stage doing the work the
   closed grammar used to do.

Stages 0-4 are pure functions of numbers and take no model, which is why they
are here and not inside the recogniser: they are exhaustively testable, and
they are the stages that keep a fabricated answer out of the driver's ear.
"""
from __future__ import annotations

from dataclasses import dataclass

from pitcrew.engineer.intents import UNKNOWN

# What the gate decided to do about an utterance.
ACT = "act"                 # confident enough to answer
CONFIRM = "confirm"         # plausible, but worth one word of checking
REJECT = "reject"           # say again

# Why it was rejected. Reported, never guessed at - a driver who is told
# "I didn't hear you" learns to press the button properly; one who is told
# nothing learns the app is unreliable. Every one of these now has a line in
# SPOKEN below, because for two years they were computed, stored and read by
# nobody: all five spoke "Say again.", which is the one thing that tells him
# nothing about which of them happened.
NO_INPUT = "the microphone delivered no audio"
NO_DEVICE = "the microphone did not open"
NO_SPEECH = "no speech in the capture"
TOO_SHORT = "too short to be a question"
TOO_LONG = "longer than the capture limit"
NOTHING_HEARD = "nothing transcribed"
REPEAT_LOOP = "the recogniser lost its place"
NOT_UNDERSTOOD = "no phrase close enough in meaning"
FAILED = "push to talk failed"
# The recogniser lost its start-up race and is still loading. Not a
# failure - a "not yet", and the only reason on this list that fixes
# itself if he asks again in a moment.
NOT_READY = "the recogniser is still loading"

# What the driver hears for each. §5.5 form: the instruction he can act on
# first, the reason second and short. The first two are the ones that were
# indistinguishable from "you did not speak" and are the reason this table
# exists - a dead microphone is not something he can fix by asking again, and
# telling him to ask again is worse than useless.
SPOKEN: dict[str, str] = {
    NO_INPUT: "No audio from your microphone. Check the device.",
    NO_DEVICE: "Your microphone didn't open. Check the device.",
    NO_SPEECH: "I didn't hear you. Hold the button and say again.",
    TOO_SHORT: "Too short. Say again.",
    TOO_LONG: "That ran long. Say again, shorter.",
    NOTHING_HEARD: "I didn't catch that. Say again.",
    REPEAT_LOOP: "I didn't catch that. Say again.",
    NOT_UNDERSTOOD: "Say again.",
    FAILED: "Push to talk failed. Check the log.",
    NOT_READY: "Still starting up. Ask me again in a moment.",
}

# Every reason, in the order the stages produce them. For the phrase pack,
# which renders `SPOKEN[reason]` for each one.
ALL_REASONS: tuple[str, ...] = (
    NO_INPUT, NO_DEVICE, NO_SPEECH, TOO_SHORT, TOO_LONG, NOTHING_HEARD,
    REPEAT_LOOP, NOT_UNDERSTOOD, FAILED, NOT_READY,
)

# Under this much detected speech, treat the capture as a brushed button.
MIN_SPEECH_S = 0.30
# Under this, it is not a question even if something was detected.
MIN_DURATION_S = 0.40
# Nobody speaks this fast. A decoder stuck in a loop does.
MAX_WORDS_PER_SECOND = 6.5

# Cosine distance bands, by how much the driver wants to be asked. Distance,
# not similarity: smaller is closer. These are the calibrated triples the
# named sensitivity maps to, and they are the only place raw numbers appear -
# nothing in the UI ever shows a cosine value, because it would mean nothing
# to the person reading it.
#
# **Re-measured 22 Aug, and the old numbers no longer described anything.**
# They were calibrated against forty-six phrases; the list had grown to
# fifty-seven and had never been re-measured, and it has since been rewritten
# for natural speech and grown two intents. Measured against the rewritten
# vocabulary, over phrasing deliberately held out of it:
#
#   real questions    0.066 - 0.505
#   unrelated speech  0.170 - 0.573
#
# There is no gap. There is no threshold that separates them, either, because
# the overlap is not noise: "remind me to buy milk" sits at 0.170 for the same
# reason "remind me of the plan" does, and no distance rule tells those apart.
# A best-versus-second-best margin was measured too and separates them no
# better - the collision has a *larger* margin than most real questions.
#
# **So the band is set on the cost of being wrong, not on a separation that
# does not exist.** Two measurements decide it:
#
# * On sixteen fresh held-out questions the intent was right thirteen times,
#   and being close was almost no guide to being right: **9 of 11 correct at or
#   below 0.34, and 4 of 5 correct above it.** 82% against 80%. A tight band
#   buys essentially no accuracy - it just refuses questions it would have
#   answered correctly. "How shot are the fronts" is 0.505 and matches `tyres`.
# * At the old medium band only **four of those sixteen would have acted.** The
#   other twelve came back as "did you mean...?", which is the driver's actual
#   complaint in his own words: it doesn't understand what he is saying.
#
# And the premise underneath both: **he pressed a button to talk to his race
# engineer.** He is not asking about milk. Answering a stray sentence costs him
# one line he ignores; refusing a real question costs him asking twice, at
# racing speed, with both hands on the wheel. Those are not the same price.
#
# Re-measure if the phrase list or the embedding model changes: these numbers
# describe those two things and nothing else.
SENSITIVITIES: dict[str, tuple[float, float]] = {
    # (act at or below this, confirm at or below this)
    "high":   (0.52, 0.70),   # acts on almost anything said into the button
    "medium": (0.42, 0.58),   # acts on 14 of 16 held-out questions, confirms
                              # the rest - nothing measured was refused outright
    "low":    (0.32, 0.48),   # acts only when close, and asks about the rest
}
DEFAULT_SENSITIVITY = "medium"


@dataclass(frozen=True)
class Verdict:
    """What to do with one press of the button."""
    action: str                     # ACT | CONFIRM | REJECT
    intent: str = UNKNOWN
    heard: str = ""
    reason: str = ""
    # For the log and the transcript. Never shown to the driver as a number.
    distance: float | None = None

    @property
    def acted(self) -> bool:
        return self.action == ACT


def bands(sensitivity: str) -> tuple[float, float]:
    return SENSITIVITIES.get(sensitivity, SENSITIVITIES[DEFAULT_SENSITIVITY])


def spoken_reason(reason: str | None) -> str:
    """What to say about a rejection. Unknown reasons fall back to "say again",
    which is the honest answer when we cannot name what went wrong."""
    return SPOKEN.get(reason or "", SPOKEN[NOT_UNDERSTOOD])


def check_audio(*, duration_s: float, speech_s: float,
                max_capture_s: float) -> str | None:
    """Stages 0, 1 and 2. The reason to reject, or None to carry on.

    Speech is checked before duration on purpose: a two-second capture of
    engine noise is long enough to pass a duration test and is exactly the
    input that produces a confident hallucination.

    Stage 0 is newer and is about the device rather than the driver. A capture
    of exactly nothing is not a quiet capture, it is a microphone that
    delivered no audio at all: measured on this machine, the disconnected
    Bluetooth earbud that is the default input opens without error and
    delivers **zero** callbacks over a three-second hold, where the built-in
    array delivers nineteen to seventy-five. Reporting that as "no speech in
    the capture" tells him to speak up at a device that is not there.
    """
    if duration_s <= 0.0:
        return NO_INPUT
    if speech_s < MIN_SPEECH_S:
        return NO_SPEECH
    if duration_s < MIN_DURATION_S:
        return TOO_SHORT
    if duration_s > max_capture_s:
        return TOO_LONG
    return None


def check_transcript(text: str, *, duration_s: float) -> str | None:
    """Stages 3 and 4. The reason to reject, or None to carry on."""
    words = text.split()
    if not words:
        return NOTHING_HEARD
    if duration_s > 0 and len(words) / duration_s > MAX_WORDS_PER_SECOND:
        return REPEAT_LOOP
    return None


def judge(text: str, *, intent: str, distance: float | None,
          sensitivity: str = DEFAULT_SENSITIVITY) -> Verdict:
    """Stage 5. How close in meaning, and therefore what to do about it.

    A `distance` of None means no semantic model was available and the caller
    fell back to literal phrase matching. That match is exact by construction,
    so it acts - it is the old closed-grammar behaviour, which was never the
    unsafe part.
    """
    if intent == UNKNOWN:
        return Verdict(REJECT, UNKNOWN, text, NOT_UNDERSTOOD, distance)
    if distance is None:
        return Verdict(ACT, intent, text)

    act_below, confirm_below = bands(sensitivity)
    if distance <= act_below:
        return Verdict(ACT, intent, text, distance=distance)
    if distance <= confirm_below:
        return Verdict(CONFIRM, intent, text, distance=distance)
    return Verdict(REJECT, UNKNOWN, text, NOT_UNDERSTOOD, distance)


# Where the intent name does not survive being read out. The generic form
# below turns a hyphenated id into words, which is serviceable for `box-when`
# and unusable for the report family - "Did you mean report understeer?" is
# not a sentence anybody answers.
_SPOKEN_AS = {
    "report-understeer": "understeer",
    "report-oversteer": "oversteer",
    "report-incident": "an incident - shall I throw the lap out",
    "report-traffic": "traffic - shall I throw the lap out",
}


def confirmation_question(intent: str) -> str:
    """One short question, answerable with one word at racing speed."""
    return f"Did you mean {_SPOKEN_AS.get(intent, intent.replace('-', ' '))}?"
