"""The staged confidence gate, at every band.

The closed SAPI grammar could not return a phrase that was not in it. Free
dictation can return anything, so this is what stands between a hallucinated
sentence and an answer the driver acts on. `intents.py` states the rule these
enforce: an engineer who confidently mis-hears is worse than one who says "say
again" - and its converse, that a driver with his hands full can say "yes" in
a second where repeating a question costs him a corner.

Every stage is a pure function of numbers or strings, so all of it runs with
no microphone, no model and no audio device.
"""
from __future__ import annotations

import pytest

from pitcrew.engineer import gate
from pitcrew.engineer.intents import BOX_WHEN, FUEL, UNKNOWN
from pitcrew.engineer.ptt import PushToTalk

MAX_CAPTURE = 6.0


# --------------------------------------------------- stage 1: was there speech

def test_silence_is_rejected_before_anything_is_transcribed():
    """The dangerous one. A recogniser given silence does not return silence -
    it returns a plausible sentence."""
    assert gate.check_audio(duration_s=2.0, speech_s=0.0,
                            max_capture_s=MAX_CAPTURE) == gate.NO_SPEECH


def test_a_brushed_button_is_rejected():
    assert gate.check_audio(duration_s=1.5, speech_s=0.10,
                            max_capture_s=MAX_CAPTURE) == gate.NO_SPEECH


def test_speech_is_checked_before_length():
    """Two seconds of engine noise passes a duration test and is exactly the
    input that produces a confident hallucination."""
    assert gate.check_audio(duration_s=0.1, speech_s=0.0,
                            max_capture_s=MAX_CAPTURE) == gate.NO_SPEECH


# ------------------------------------------------------ stage 2: was it sane

def test_too_short_to_be_a_question_is_rejected():
    assert gate.check_audio(duration_s=0.35, speech_s=0.35,
                            max_capture_s=MAX_CAPTURE) == gate.TOO_SHORT


def test_longer_than_the_capture_limit_is_rejected():
    assert gate.check_audio(duration_s=7.0, speech_s=6.5,
                            max_capture_s=MAX_CAPTURE) == gate.TOO_LONG


def test_a_normal_question_passes():
    assert gate.check_audio(duration_s=1.5, speech_s=1.2,
                            max_capture_s=MAX_CAPTURE) is None


# ------------------------------------------- stages 3 and 4: what came back

def test_an_empty_transcript_is_a_rejection_not_an_intent():
    assert gate.check_transcript("", duration_s=1.5) == gate.NOTHING_HEARD
    assert gate.check_transcript("   ", duration_s=1.5) == gate.NOTHING_HEARD


def test_a_repeat_loop_is_caught_by_words_per_second():
    """A decoder that loses its place emits the same token forever. Nobody
    speaks at nine words a second."""
    runaway = " ".join(["box"] * 20)
    assert gate.check_transcript(runaway, duration_s=2.0) == gate.REPEAT_LOOP


def test_normal_speech_is_not_mistaken_for_a_repeat_loop():
    assert gate.check_transcript("how much fuel do i take",
                                 duration_s=2.0) is None


# ------------------------------------------------- stage 5: did it mean this

def test_a_close_match_is_acted_on():
    verdict = gate.judge("when do i box", intent=BOX_WHEN, distance=0.10)
    assert verdict.action == gate.ACT
    assert verdict.intent == BOX_WHEN


def test_an_ambiguous_match_is_confirmed_rather_than_rejected():
    """One syllable from him beats a whole repeated question."""
    verdict = gate.judge("when box thing", intent=BOX_WHEN, distance=0.36)
    assert verdict.action == gate.CONFIRM
    assert verdict.intent == BOX_WHEN


def test_nonsense_is_rejected():
    verdict = gate.judge("the fridge is making a noise", intent=BOX_WHEN,
                         distance=0.45)
    assert verdict.action == gate.REJECT
    assert verdict.intent == UNKNOWN
    assert verdict.reason == gate.NOT_UNDERSTOOD


def test_an_unmatched_intent_is_rejected_whatever_the_distance():
    verdict = gate.judge("blah", intent=UNKNOWN, distance=0.01)
    assert verdict.action == gate.REJECT


def test_no_semantic_model_falls_back_to_the_literal_match():
    """Which is exact by construction - the closed-grammar behaviour, and
    never the unsafe part."""
    verdict = gate.judge("when do i box", intent=BOX_WHEN, distance=None)
    assert verdict.action == gate.ACT


@pytest.mark.parametrize("sensitivity,distance,expected", [
    ("low", 0.20, gate.ACT),
    ("low", 0.30, gate.CONFIRM),
    ("low", 0.40, gate.REJECT),
    ("medium", 0.25, gate.ACT),
    ("medium", 0.36, gate.CONFIRM),
    ("medium", 0.50, gate.REJECT),
    ("high", 0.35, gate.ACT),
    ("high", 0.45, gate.CONFIRM),
    ("high", 0.60, gate.REJECT),
])
def test_sensitivity_moves_the_bands(sensitivity, distance, expected):
    verdict = gate.judge("x", intent=FUEL, distance=distance,
                         sensitivity=sensitivity)
    assert verdict.action == expected


def test_an_unknown_sensitivity_falls_back_to_the_default():
    assert gate.bands("nonsense") == gate.bands(gate.DEFAULT_SENSITIVITY)


def test_low_sensitivity_acts_less_readily_than_high():
    """The named settings have to mean what they say."""
    low_act, low_confirm = gate.bands("low")
    high_act, high_confirm = gate.bands("high")
    assert low_act < high_act
    assert low_confirm < high_confirm


# ------------------------------------------------ the gate, through the seam

class Matcher:
    def __init__(self, intent, distance):
        self._result = (intent, distance)

    def match(self, _heard):
        return self._result


def talker(matcher=None, snapshot=None, **kwargs):
    said = []
    ptt = PushToTalk(snapshot=lambda: snapshot or {"lapsToStop": 3},
                     speak=said.append, matcher=matcher, **kwargs)
    return ptt, said


def test_a_confident_question_is_answered():
    ptt, said = talker(Matcher(BOX_WHEN, 0.10))
    assert ptt.ask("when do i box") == "Box in 3 laps."
    assert said == ["Box in 3 laps."]
    assert ptt.pending_confirmation is None


def test_an_ambiguous_question_asks_one_word_back():
    ptt, said = talker(Matcher(BOX_WHEN, 0.36))
    reply = ptt.ask("when box thing")
    assert reply == "Did you mean box when?"
    assert said == ["Did you mean box when?"]
    assert ptt.pending_confirmation == BOX_WHEN


def test_yes_to_a_confirmation_answers_the_question():
    ptt, said = talker(Matcher(BOX_WHEN, 0.36))
    ptt.ask("when box thing")
    assert ptt.ask("yes") == "Box in 3 laps."
    assert ptt.pending_confirmation is None


def test_no_to_a_confirmation_says_again():
    ptt, said = talker(Matcher(BOX_WHEN, 0.36))
    ptt.ask("when box thing")
    assert ptt.ask("no") == "Say again."
    assert ptt.pending_confirmation is None


def test_a_different_question_during_a_confirmation_is_answered_on_its_merits():
    """He ignored the question and asked something else. That is not a no."""
    ptt, said = talker(Matcher(BOX_WHEN, 0.36),
                       snapshot={"lapsToStop": 3, "position": 4})
    ptt.ask("when box thing")
    ptt._matcher = Matcher("position", 0.08)
    assert ptt.ask("what position am i") == "P4."
    assert ptt.pending_confirmation is None


def test_nonsense_says_again_rather_than_guessing():
    ptt, said = talker(Matcher(BOX_WHEN, 0.55))
    assert ptt.ask("the fridge is making a noise") == "Say again."


def test_a_rejected_capture_reaches_the_same_say_again():
    """The recogniser returns "" on a gate rejection, and that path already
    existed - it is the UNKNOWN branch."""
    ptt, said = talker(Matcher(UNKNOWN, None))
    assert ptt.ask("") == "Say again."


def test_a_matcher_that_throws_does_not_cost_the_answer():
    class Broken:
        def match(self, _heard):
            raise RuntimeError("model gone")

    ptt, said = talker(Broken())
    # Falls through to literal matching, which knows this phrase.
    assert ptt.ask("when do i box") == "Box in 3 laps."


def test_with_no_matcher_at_all_the_literal_path_still_works():
    ptt, said = talker(None)
    assert ptt.ask("how much fuel") == "I don't have a fuel rate yet."


def test_sensitivity_reaches_the_seam():
    ptt, _ = talker(Matcher(BOX_WHEN, 0.33), sensitivity="high")
    assert ptt.ask("when box") == "Box in 3 laps."       # acts at high
    ptt.pending_confirmation = None
    ptt._sensitivity = "low"
    assert ptt.ask("when box") == "Did you mean box when?"


def test_the_verdict_is_kept_for_the_log():
    ptt, _ = talker(Matcher(FUEL, 0.12))
    ptt.ask("how much fuel")
    assert ptt.last_verdict.intent == FUEL
    assert ptt.last_verdict.distance == 0.12


# ------------------------------------------------- a machine with no speech

def test_no_recogniser_still_constructs_and_runs():
    """A machine without a microphone must still run the app."""
    said = []
    ptt = PushToTalk(snapshot=dict, speak=said.append, recogniser=None,
                     listener=None)
    ptt.start()          # must not raise
    ptt.end()
    ptt.stop()
    assert said == ["Speech isn't available on this machine."]


def test_the_bands_sit_inside_the_measured_gap():
    """The calibration is the safety property, so it is asserted, not trusted.

    Measured against embeddinggemma-300m q4 and the real phrase list: genuine
    questions land at 0.028-0.244, unrelated speech at 0.416-0.473. Every
    band has to keep those two apart, or a sentence about the fridge gets
    answered as a fuel question.
    """
    real_worst, junk_best = 0.244, 0.416

    # low and medium refuse unrelated speech outright.
    for name in ("low", "medium"):
        assert gate.bands(name)[1] < junk_best, (
            f"{name} would confirm unrelated speech instead of refusing it")

    # `high` is allowed to ask about unrelated speech - that is what "acts
    # readily" costs, and one syllable is the price. It must never *act* on it.
    assert gate.bands("high")[0] < junk_best, (
        "high would answer a sentence about the fridge as a fuel question")

    # At medium, every real question measured acts outright rather than
    # asking - the whole point of putting the band inside the gap.
    assert gate.bands("medium")[0] > real_worst - 0.06
