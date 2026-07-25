"""The constrained PTT command vocabulary (UAT-4).

PocketSphinx was transcribing FREE-FORM speech against a general language model and
the result was then keyword-matched, so the keyword almost never landed and the driver
heard "Sorry, I did not catch that" every time. Recognition is now constrained to the
command phrases — which only works if every phrase is pronounceable and short words
are held to a strict threshold.
"""

from voice.command_vocabulary import (
    EXTRA_PHRASES, candidate_phrases, dictionary_words, keyword_entries,
    phrase_is_pronounceable, sensitivity_for,
)
from voice.query_listener import (
    _INTENT_KEYWORDS, _match_intent, match_intent_with_confidence,
)


class TestDictionary:
    def test_the_shipped_dictionary_is_readable(self):
        words = dictionary_words()
        assert len(words) > 50_000
        assert "fuel" in words and "pit" in words

    def test_british_spellings_the_app_uses_are_detected_as_oov(self):
        """These are in the app's own keyword lists and WOULD abort the keyword pass."""
        words = dictionary_words()
        assert phrase_is_pronounceable("tyres", words) is False
        assert phrase_is_pronounceable("litre", words) is False
        assert phrase_is_pronounceable("analyse", words) is False

    def test_nothing_is_claimed_pronounceable_without_a_dictionary(self):
        assert phrase_is_pronounceable("fuel", set()) is False


class TestSensitivity:
    def test_longer_phrases_are_matched_more_loosely(self):
        assert sensitivity_for("how much fuel left") < sensitivity_for("fuel check")
        assert sensitivity_for("fuel check") < sensitivity_for("fuel")

    def test_every_value_is_inside_the_accepted_range(self):
        """SpeechRecognition validates sensitivity into [0, 1]; outside it, the whole
        keyword pass raises and recognition silently falls back."""
        for phrase in candidate_phrases(_INTENT_KEYWORDS):
            assert 0.0 <= sensitivity_for(phrase) <= 1.0

    def test_a_lone_word_gets_the_strictest_threshold(self):
        # Measured: at a loose threshold one second of noise "spotted" 35 words.
        assert sensitivity_for("fuel") == 1.0


class TestPhraseList:
    def test_real_radio_questions_are_included(self):
        phrases = candidate_phrases(_INTENT_KEYWORDS)
        assert "how much fuel" in phrases
        assert "when should i pit" in phrases

    def test_longest_first_so_the_specific_intent_wins(self):
        phrases = candidate_phrases(_INTENT_KEYWORDS)
        assert phrases.index("fuel check") < phrases.index("fuel")

    def test_thin_phrases_are_dropped(self):
        assert "gas" not in candidate_phrases(_INTENT_KEYWORDS)

    def test_entries_are_pronounceable_pairs(self):
        entries = keyword_entries(_INTENT_KEYWORDS)
        assert len(entries) > 50
        words = dictionary_words()
        for phrase, sensitivity in entries:
            assert phrase_is_pronounceable(phrase, words)
            assert 0.0 <= sensitivity <= 1.0

    def test_oov_phrases_never_reach_the_recogniser(self):
        spoken = {p for p, _ in keyword_entries(_INTENT_KEYWORDS)}
        assert "tyres" not in spoken
        assert "litre" not in spoken

    def test_no_dictionary_means_no_keyword_pass(self, monkeypatch):
        monkeypatch.setattr("voice.command_vocabulary.dictionary_words", lambda: set())
        assert keyword_entries(_INTENT_KEYWORDS) == []

    def test_every_spoken_phrase_still_resolves_to_an_intent(self):
        """A phrase the recogniser can spot but the matcher cannot route is dead weight."""
        unroutable = [p for p, _ in keyword_entries(_INTENT_KEYWORDS) if not _match_intent(p)]
        assert unroutable == []

    def test_the_extra_phrases_cover_the_questions_a_driver_actually_asks(self):
        for phrase in ("how much fuel", "what position am i", "when should i pit",
                       "how many laps", "is it raining"):
            assert phrase in EXTRA_PHRASES
            assert _match_intent(phrase) != ""


class TestIntentSpecificityBeatsListOrder:
    """UAT-6: "PTT is still just saying not enough laps to determine pace instead of
    answering my tyre temp question or fuel". The matcher returned the FIRST intent in
    list order whose keyword appeared, and the pace intent (keywords "going",
    "performance") sits above tyre_state and fuel — so a topic word was shadowed by a
    filler word and the question was answered as a pace query."""

    def test_a_tyre_question_is_not_answered_as_pace(self):
        assert _match_intent("how are the tyre temps going") == "tyre_state"
        assert _match_intent("are my tyres overheating") == "tyre_state"

    def test_a_fuel_question_is_not_answered_as_pace(self):
        assert _match_intent("how much fuel have i got left") == "fuel"
        assert _match_intent("am i going to run out of fuel") == "fuel"

    def test_a_genuine_pace_question_still_routes_to_pace(self):
        assert _match_intent("how am i going") == "pace"
        assert _match_intent("hows my pace") == "pace"

    def test_a_multiword_command_beats_an_overlapping_single_word(self):
        # "fuel check" (a deliberate command) must not be swallowed by the "fuel" intent.
        assert _match_intent("give me a fuel check") == "fuel_check"
        # "should i pit" beats a stray "pit" mention elsewhere.
        assert _match_intent("should i pit") == "pit"

    def test_a_specific_topic_word_anywhere_wins_over_a_filler_word(self):
        # "how many" (generic) appears, but "position" is the real topic.
        assert _match_intent("how many places am i behind in position") == "position"

    def test_nothing_matched_returns_empty(self):
        assert _match_intent("hello there engineer") == ""

    def test_fuel_to_leave_routes_to_the_strategy_fuel_check(self):
        assert _match_intent("what fuel do i leave with") == "fuel_check"
        assert _match_intent("fuel to leave with") == "fuel_check"

    def test_fuel_delta_questions_route_to_the_fuel_delta_intent(self):
        assert _match_intent("what is my fuel delta") == "fuel_delta"
        assert _match_intent("am i saving fuel") == "fuel_delta"
        assert _match_intent("fuel per lap") == "fuel_delta"


class TestNoisyBagConfidence:
    """Real PTT logs return big noisy keyword-bags. The recogniser must reliably pull the
    intended race intent out of a bag, and must ASK AGAIN rather than confidently answer
    the wrong question when the bag only carries filler or lights up many unrelated topics."""

    def test_clean_single_topic_questions_are_high_confidence(self):
        for phrase, intent in [
            ("how much fuel", "fuel"),
            ("what position am i", "position"),
            ("when should i pit", "pit"),
            ("how are the tyre temps going", "tyre_state"),
            ("what is the weather", "rain"),
        ]:
            got, conf = match_intent_with_confidence(phrase)
            assert got == intent, phrase
            assert conf == "high", phrase

    def test_a_short_filler_only_pace_question_still_answers(self):
        # "how am i going" carries only generic words but is a genuine short question.
        got, conf = match_intent_with_confidence("how am i going")
        assert got == "pace"
        assert conf == "high"

    def test_a_noisy_bag_of_many_topics_asks_again(self):
        # From the user's race log — many unrelated race topics at once.
        bag = ("tune time how am i where weather when pit minor "
               "what is the weather spin pace pit stop how long tune")
        _got, conf = match_intent_with_confidence(bag)
        assert conf == "low"

    def test_a_bag_the_recogniser_still_resolves_stays_answerable(self):
        # This one resolved correctly in the field ("what position" -> P2); it must NOT
        # be thrown away — only two topics (position, setup) are present.
        got, conf = match_intent_with_confidence(
            "tune clock what position position what position am i")
        assert got == "position"
        assert conf == "high"

    def test_a_long_bag_of_only_filler_words_asks_again(self):
        _got, conf = match_intent_with_confidence(
            "how how long where when clock how many how am i remaining time")
        assert conf == "low"

    def test_nothing_recognised_asks_again(self):
        got, conf = match_intent_with_confidence("hello there engineer")
        assert got == ""
        assert conf == "low"
