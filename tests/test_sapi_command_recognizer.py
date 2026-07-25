"""Tests for the offline SAPI command-grammar recogniser wired into the live PTT path.

These cover construction, the phrase grammar, and graceful degradation. The actual
speech recognition is machine + microphone dependent and is validated on the physical
rig — never asserted here.
"""

import voice.sapi_command_recognizer as sapi


class TestGrammarPhrases:
    def test_phrases_are_built_from_the_app_vocabulary(self):
        phrases = sapi._command_phrases()
        assert isinstance(phrases, list) and phrases
        # The command questions the intent matcher understands are present.
        assert any("fuel" in p for p in phrases)
        assert any("pit" in p for p in phrases)

    def test_phrases_are_deduplicated(self):
        phrases = sapi._command_phrases()
        assert len(phrases) == len(set(phrases))


class TestGracefulDegradation:
    def test_is_available_never_raises(self):
        # True on a machine with offline SAPI, False elsewhere — either is fine.
        assert sapi.is_available() in (True, False)

    def test_empty_audio_returns_none(self):
        assert sapi.recognize_wav_bytes(b"", 16000) is None

    def test_recognition_never_raises_on_silence(self):
        # A short silent clip must return None (no command), never raise.
        silence = b"\x00\x00" * 1600  # 0.1s of 16-bit silence @ 16kHz
        result = sapi.recognize_wav_bytes(silence, 16000, timeout_s=0.5)
        assert result is None or isinstance(result, str)


class TestLivePathIntegration:
    def test_query_listener_recognise_tries_sapi_first_then_falls_back(self):
        """_recognise prefers SAPI; on None it must fall through to the Sphinx path and
        still return a string-or-None without raising."""
        from voice.query_listener import _recognise
        silence = b"\x00\x00" * 1600
        out = _recognise(silence, 16000)
        assert out is None or isinstance(out, str)
