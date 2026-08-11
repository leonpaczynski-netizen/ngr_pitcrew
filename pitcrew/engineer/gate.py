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

Five stages, cheapest first, each rejecting for a different reason:

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

Stages 1-4 are pure functions of numbers and take no model, which is why they
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
# nothing learns the app is unreliable.
NO_SPEECH = "no speech in the capture"
TOO_SHORT = "too short to be a question"
TOO_LONG = "longer than the capture limit"
NOTHING_HEARD = "nothing transcribed"
REPEAT_LOOP = "the recogniser lost its place"
NOT_UNDERSTOOD = "no phrase close enough in meaning"

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
# **Measured, not guessed.** Against embeddinggemma-300m q4 and the forty-six
# phrases in `intents.PHRASES`, over the transcripts Moonshine actually
# produced for this vocabulary plus paraphrases of them:
#
#   real questions    0.028 - 0.244   ("what's the plan?" 0.028, "say out." 0.244)
#   unrelated speech  0.416 - 0.473   ("turn the heating up please" 0.447)
#
# A gap of 0.172 with nothing in it. The bands sit inside that gap, so at
# `medium` every real question acts and every unrelated sentence is refused.
# Re-measure if the phrase list or the embedding model changes: these numbers
# describe those two things and nothing else.
SENSITIVITIES: dict[str, tuple[float, float]] = {
    # (act at or below this, confirm at or below this)
    "high":   (0.38, 0.50),   # acts readily - unrelated speech asks rather
                              # than refuses, costing him one syllable
    "medium": (0.30, 0.40),   # inside the measured gap, clear both sides
    "low":    (0.22, 0.35),   # acts only when sure - a mis-heard word like
                              # "say out" for "stay out" asks first
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


def check_audio(*, duration_s: float, speech_s: float,
                max_capture_s: float) -> str | None:
    """Stages 1 and 2. The reason to reject, or None to carry on.

    Speech is checked before duration on purpose: a two-second capture of
    engine noise is long enough to pass a duration test and is exactly the
    input that produces a confident hallucination.
    """
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


def confirmation_question(intent: str) -> str:
    """One short question, answerable with one word at racing speed."""
    return f"Did you mean {intent.replace('-', ' ')}?"
