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
from voice.query_listener import _INTENT_KEYWORDS, _match_intent


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
