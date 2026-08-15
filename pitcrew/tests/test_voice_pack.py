"""The phrase pack: what it covers, and what happens when it does not.

The pack is an optimisation. The property that matters is not that it is fast
but that it is invisible: a line it does not carry, or cannot play, must reach
the driver anyway. An optimisation that can silence the engineer is a bug.
"""
from __future__ import annotations

import json
import wave
from pathlib import Path

import pytest

from pitcrew.engineer import phrase_manifest as manifest
from pitcrew.engineer import voice as voice_module
from pitcrew.engineer.intents import (
    ACCEPT,
    BOX_FUEL,
    BOX_WHAT,
    BOX_WHEN,
    FUEL,
    KEEP,
    LAPS_LEFT,
    PLAN,
    POSITION,
    REPEAT,
    UNKNOWN,
    answer,
)
from pitcrew.engineer.voice import (
    Voice,
    VoicePackEngine,
    clip_filename,
    load_voice_pack,
)
from pitcrew.store.tyres import ALL_COMPOUNDS


# ------------------------------------------------------------- the manifest

def sweep() -> list[str]:
    """Everything the engineer can say, over a representative set of states.

    Driven through the real functions rather than listed, so a new branch in
    `answer()` - or a new proactive call in `race/calls.py` - shows up here as
    an uncovered line instead of as a pause in the driver's ear.
    """
    lines: list[str] = []
    empty: dict = {}

    lines.append(answer(UNKNOWN, empty).text)
    lines.append(answer(REPEAT, empty).text)
    lines.append(answer(REPEAT, empty, last_call="Box this lap.").text)
    for intent in (ACCEPT, KEEP):
        lines.append(answer(intent, empty).text)
        lines.append(answer(intent, empty, pending_replan="x").text)

    lines.append(answer(POSITION, empty).text)
    lines += [answer(POSITION, {"position": n}).text
              for n in range(1, manifest.MAX_POSITION + 1)]

    lines.append(answer(LAPS_LEFT, empty).text)
    lines += [answer(LAPS_LEFT, {"lapsRemaining": n}).text
              for n in range(0, manifest.MAX_LAPS + 1)]

    lines.append(answer(FUEL, empty).text)
    lines += [answer(FUEL, {"lapsOfFuel": n / 10}).text
              for n in range(0, manifest.MAX_FUEL_LAPS * 10 + 1)]

    lines.append(answer(BOX_WHEN, empty).text)
    lines.append(answer(BOX_WHEN, {"hasPlan": True}).text)
    lines += [answer(BOX_WHEN, {"lapsToStop": n}).text
              for n in range(0, manifest.MAX_LAPS + 1)]

    lines.append(answer(BOX_WHAT, empty).text)
    lines.append(answer(BOX_WHAT, {"hasPlan": True}).text)
    # Both the code and the full name: the plan stores the code, so the code
    # is what the engineer says at almost every stop.
    lines += [answer(BOX_WHAT, {"nextCompound": c.name}).text
              for c in ALL_COMPOUNDS]
    lines += [answer(BOX_WHAT, {"nextCompound": c.code}).text
              for c in ALL_COMPOUNDS]

    lines.append(answer(BOX_FUEL, empty).text)
    lines += [answer(BOX_FUEL, {"stopFuelL": float(n)}).text
              for n in range(0, manifest.MAX_FUEL_LITRES + 1)]

    lines += list(manifest.plan_summary_examples())
    lines += list(manifest.race_call_examples())
    return lines


def test_the_manifest_covers_everything_the_engineer_can_say():
    """A line that can be generated but not rendered is a silent regression."""
    clips = set(manifest.clips())
    gaps = []
    for line in sweep():
        segments = manifest.segments_for(line)
        if segments and all(name in clips for name in segments):
            continue
        if manifest.uncovered_reason(line):
            continue                      # a declared gap, not an oversight
        gaps.append(line)
    assert not gaps, f"{len(gaps)} lines cannot be played from the pack: {gaps[:8]}"


def test_every_declared_gap_is_one_of_the_two_named_ones():
    """If anything else starts falling through, it is a bug, not a decision.

    Two families are allowed to: the multi-clause plan summary, and a call
    left holding two numbers in one clause. Both are stated in
    `uncovered_reason`; anything else declaring itself a decision is one
    nobody made.
    """
    uncovered = [line for line in sweep()
                 if manifest.uncovered_reason(line)]
    assert uncovered, "the plan summary should still be a declared gap"
    for line in uncovered:
        reason = manifest.uncovered_reason(line)
        assert "combinatorial" in reason or "numbers left" in reason, line
        if "combinatorial" in reason:
            assert "," in line, f"{line!r} is not a plan summary"


def test_a_line_with_a_comma_in_it_is_not_a_plan_summary_by_itself():
    """The old test for this was `"," in text`, which called the green-flag
    call a plan summary and told the driver's log it was synthesised live for
    a reason that has nothing to do with it."""
    assert manifest.uncovered_reason("Green, green, green. 20 laps.") is None
    assert manifest.uncovered_reason("Stop 1, on the plan.") is None
    assert manifest.uncovered_reason("Running to the flag.") is None
    assert manifest.uncovered_reason(
        "Box in 4 laps, onto Racing Medium.") is not None


# ------------------------------------------------------ the proactive calls
#
# The half the pack never covered: measured before this, 0 of 7 real race
# calls could be played. A reply the driver asked for can be asked for again;
# a call that arrives mid-corner cannot.

def test_every_proactive_call_can_be_played_from_the_pack():
    clips = set(manifest.clips())
    gaps = []
    for line in manifest.race_call_examples():
        segments = manifest.segments_for(line)
        if segments and all(name in clips for name in segments):
            continue
        if manifest.uncovered_reason(line):
            continue
        gaps.append(line)
    assert not gaps, f"{len(gaps)} race calls cannot be played: {gaps[:8]}"


def test_the_calls_the_review_measured_as_missing_are_covered():
    """The seven from `findings-r3-audio.md`, by name, so this cannot quietly
    regress to the state that produced that measurement."""
    clips = set(manifest.clips())
    for line in ("10 to go.",
                 "Chequered flag.",
                 "Chequered flag. P2.",
                 "You can push. 2.1 laps of fuel in hand.",
                 "Box next lap. Stop 1, on the plan.",
                 "Green, green, green. 20 laps.",
                 "Box this lap. RS. On the plan."):
        segments = manifest.segments_for(line)
        assert segments, line
        missing = [name for name in segments if name not in clips]
        assert not missing, (line, missing)


def test_a_number_inside_a_word_is_not_split_out():
    """"P4." is a position and one clip; splitting it would say "P" and then
    "four" as two separate recordings."""
    assert manifest.segments_for("Chequered flag. P4.") == (
        "Chequered flag.", "P4.")


def test_a_clause_that_would_leave_a_fragment_starting_with_a_comma_is_whole():
    assert manifest.segments_for("Box next lap. Stop 3, on the plan.") == (
        "Box next lap.", "Stop 3, on the plan.")


def test_a_percentage_is_spelled_out_rather_than_rendered_as_a_symbol():
    segments = manifest.segments_for(
        "Tyres are at the end of their window. Modelled at 90%. Unconfirmed.")
    assert segments is not None
    assert "ninety" in segments
    assert any(name.startswith("percent") for name in segments)
    assert not any("%" in name for name in segments)


def test_a_whole_line_the_pack_already_carries_is_never_split():
    """"Box in 3 laps." is a rendered answer. Decomposing it into "Box in" and
    a number would miss the clip that exists and synthesise it live."""
    assert manifest.segments_for("Box in 3 laps.") == ("Box in 3 laps.",)
    assert manifest.segments_for("12 laps to go.") == ("12 laps to go.",)


def test_every_fuel_line_decomposes_into_clips_that_exist():
    clips = set(manifest.clips())
    for tenths in range(0, manifest.MAX_FUEL_LAPS * 10 + 1):
        line = answer(FUEL, {"lapsOfFuel": tenths / 10}).text
        segments = manifest.segments_for(line)
        assert segments is not None, line
        assert len(segments) == 4, (line, segments)
        assert set(segments) <= clips, (line, segments)


def test_a_fuel_reading_beyond_the_rendered_range_is_a_miss_not_a_wrong_word():
    """Better a live line than the wrong number read out confidently."""
    beyond = manifest.MAX_FUEL_LAPS + 5
    assert manifest.segments_for(f"{beyond}.0 laps of fuel.") is None


def test_the_manifest_is_built_from_intents_not_copied_from_it():
    """No format string is duplicated: change the answer, change the pack."""
    source = (manifest.__file__)
    with open(source, encoding="utf-8") as handle:
        text = handle.read()
    for literal in ("laps to go", "Box in", "Fuel to", "Say again",
                    "I don't have"):
        assert f'"{literal}' not in text, (
            f"{literal!r} is spelled out in the manifest - it must come from "
            f"answer() or the two will drift")


def test_the_pack_stays_within_budget():
    """The budget is real: every clip is a file to render and to keep.

    It was 500 while the pack covered only the driver's questions. Covering
    the proactive calls as well - the half he cannot ask for a second time -
    costs about ninety clips, of which forty are number words now shared by
    four different sentences. Measured on the rendered en_GB-alan-medium pack:
    33 MB for 417 clips, so ~81 KB each and ~48 MB at this ceiling. Raise it
    again only for something that buys as much.
    """
    assert len(manifest.clips()) < 600


def test_the_same_line_always_names_the_same_file():
    assert clip_filename("Box this lap.") == clip_filename("Box this lap.")
    assert clip_filename("Box this lap.") != clip_filename("Box in 1 lap.")
    assert clip_filename("Box this lap.").endswith(".wav")


# ------------------------------------------------------------- the engine

class Spy:
    """A live engine that records instead of making a sound."""

    name = "spy"

    def __init__(self):
        self.spoken = []
        self.warmed = False
        self.tuned = {}

    def speak(self, text):
        self.spoken.append(text)

    def warm(self):
        self.warmed = True

    def tune(self, **params):
        self.tuned.update(params)


@pytest.fixture()
def pack(tmp_path):
    """A two-clip pack on disk, with real wav files."""
    folder = tmp_path / "test-voice"
    folder.mkdir()
    clips = {}
    for text in ("Box this lap.", "P4."):
        name = clip_filename(text)
        with wave.open(str(folder / name), "wb") as handle:
            handle.setnchannels(1)
            handle.setsampwidth(2)
            handle.setframerate(22_050)
            handle.writeframes(b"\x00\x00" * 2205)      # 100 ms of silence
        clips[text] = {"file": name}
    (folder / "manifest.json").write_text(
        json.dumps({"voice": "test-voice", "clips": clips}), encoding="utf-8")
    return folder, clips


def test_a_miss_falls_through_to_the_live_engine(pack):
    folder, clips = pack
    spy = Spy()
    engine = VoicePackEngine(folder, clips, spy)

    engine.speak("Something nobody rendered.")
    assert spy.spoken == ["Something nobody rendered."]
    assert engine.misses == 1
    assert engine.hits == 0


def test_a_miss_is_logged_with_the_exact_string(pack, caplog):
    """The miss log is how the manifest gets finished."""
    folder, clips = pack
    engine = VoicePackEngine(folder, clips, Spy())
    with caplog.at_level("INFO", logger="pitcrew.voice"):
        engine.speak("Box in 7 laps.")
    assert "Box in 7 laps." in caplog.text


def test_a_hit_does_not_reach_the_live_engine(pack, monkeypatch):
    folder, clips = pack
    spy = Spy()
    engine = VoicePackEngine(folder, clips, spy)
    played = []
    monkeypatch.setattr(engine, "_play", lambda segments: played.append(segments))

    engine.speak("Box this lap.")
    assert played == [("Box this lap.",)]
    assert spy.spoken == []
    assert engine.hits == 1


def test_playback_failure_still_reaches_the_driver(pack, monkeypatch):
    """A pack that cannot play must not cost the call."""
    folder, clips = pack
    spy = Spy()
    engine = VoicePackEngine(folder, clips, spy)

    def broken(_segments):
        raise OSError("device gone")

    monkeypatch.setattr(engine, "_play", broken)
    engine.speak("Box this lap.")
    assert spy.spoken == ["Box this lap."]


def test_warm_and_tune_reach_the_engine_underneath(pack):
    folder, clips = pack
    spy = Spy()
    engine = VoicePackEngine(folder, clips, spy)
    engine.warm()
    engine.tune(length_scale=1.3)
    assert spy.warmed is True
    assert spy.tuned == {"length_scale": 1.3}


def test_a_pack_with_no_live_engine_raises_on_a_line_it_cannot_play(
        pack, monkeypatch):
    """It used to return, having played nothing and said nothing about it.

    That is the state `_best_engine` built when both live engines failed and a
    rendered pack was on disk - reachable, because the models and the pack are
    gitignored independently. `Voice.enabled` was True, `engine_name` was
    "voice-pack", and about one line in ten produced no sound with nothing
    above INFO in the log. An engine that made no sound has to say so.
    """
    folder, clips = pack
    engine = VoicePackEngine(folder, clips, None)
    played = []
    monkeypatch.setattr(engine, "_play", lambda segments: played.append(segments))

    engine.speak("P4.")
    assert played == [("P4.",)] and engine.hits == 1

    with pytest.raises(voice_module.NotSpoken):
        engine.speak("Nothing rendered.")
    assert engine.misses == 1


def test_a_pack_with_no_live_engine_raises_when_playback_fails(pack,
                                                               monkeypatch):
    """The other half: the clip exists and the device is gone."""
    folder, clips = pack
    engine = VoicePackEngine(folder, clips, None)

    def broken(_segments):
        raise OSError("device gone")

    monkeypatch.setattr(engine, "_play", broken)
    with pytest.raises(voice_module.NotSpoken):
        engine.speak("P4.")


def test_a_playback_failure_is_not_counted_as_a_miss(pack, monkeypatch):
    """The miss log is the list of lines still to render. A dead output device
    was putting lines that ARE rendered on it, and hits/misses stopped
    measuring coverage at all."""
    folder, clips = pack
    spy = Spy()
    engine = VoicePackEngine(folder, clips, spy)

    def broken(_segments):
        raise OSError("device gone")

    monkeypatch.setattr(engine, "_play", broken)
    engine.speak("Box this lap.")
    assert spy.spoken == ["Box this lap."]
    assert engine.misses == 0
    assert engine.hits == 0


def test_a_playback_failure_does_not_write_the_miss_log(pack, monkeypatch,
                                                        caplog):
    folder, clips = pack
    engine = VoicePackEngine(folder, clips, Spy())
    monkeypatch.setattr(engine, "_play",
                        lambda _s: (_ for _ in ()).throw(OSError("gone")))
    with caplog.at_level("INFO", logger="pitcrew.voice"):
        engine.speak("Box this lap.")
    assert "not in the manifest" not in caplog.text


# ------------------------------------------------ an engine that cannot speak

def test_a_pack_with_nothing_under_it_is_not_offered_as_an_engine(tmp_path,
                                                                  monkeypatch):
    """The state the review constructed: both live engines fail and a rendered
    pack is on disk. `enabled: True, engine_name: voice-pack, zero audio`."""
    monkeypatch.setattr(voice_module, "PiperEngine",
                        lambda: (_ for _ in ()).throw(RuntimeError("no model")))
    monkeypatch.setattr(voice_module, "Sapi5Engine",
                        lambda: (_ for _ in ()).throw(RuntimeError("no sapi")))
    root = tmp_path / "voice_pack"
    folder = root / "test-voice"
    folder.mkdir(parents=True)
    (folder / "manifest.json").write_text(
        json.dumps({"clips": {"P4.": {"file": "x.wav"}}}), encoding="utf-8")
    monkeypatch.setattr(voice_module, "PACK_ROOT", root)

    assert voice_module._best_engine() is None


def test_enabled_means_a_sound_can_be_made_not_that_an_object_exists():
    hollow = VoicePackEngine(Path("."), {}, None)
    assert voice_module.can_speak(hollow) is False
    assert voice_module.can_speak(VoicePackEngine(Path("."), {}, Spy())) is True
    assert voice_module.can_speak(None) is False
    assert voice_module.can_speak(Spy()) is True

    assert Voice(hollow).enabled is False
    assert Voice(Spy()).enabled is True


def test_silence_is_counted_so_it_can_be_reported():
    """He is in a headset with no screen. "Nothing for three calls" is the
    only form this can take that reaches him at all."""
    class Dead:
        name = "dead"

        def speak(self, _text):
            raise OSError("device gone")

    voice = Voice(Dead())
    voice.say("Box this lap.")
    voice.say("Box this lap.")
    _drain(voice)
    assert voice.silent_calls == 2
    assert "said nothing for 2 calls" in voice.health()
    assert "OSError" in voice.health()


def test_a_call_that_plays_clears_the_count():
    class Flaky:
        name = "flaky"

        def __init__(self):
            self.fail = True

        def speak(self, _text):
            if self.fail:
                raise OSError("device gone")

    engine = Flaky()
    voice = Voice(engine)
    voice.say("one")
    _drain(voice)
    assert voice.health() is not None
    engine.fail = False
    voice.say("two")
    _drain(voice)
    assert voice.health() is None
    assert voice.silent_calls == 0


def _drain(voice, timeout: float = 2.0) -> None:
    """Wait for the voice thread to work through the queue."""
    import time
    deadline = time.monotonic() + timeout
    while voice._queue.qsize() and time.monotonic() < deadline:
        time.sleep(0.01)
    time.sleep(0.05)


def test_the_clips_on_disk_are_readable_audio(pack):
    folder, clips = pack
    engine = VoicePackEngine(folder, clips, None)
    samples, rate = engine._read(clips["P4."]["file"])
    assert rate == 22_050
    assert len(samples) == 2205


def test_no_pack_on_disk_costs_nothing(tmp_path, monkeypatch):
    """The normal state before the render tool has ever run."""
    from pitcrew.engineer import voice as voice_module

    monkeypatch.setattr(voice_module, "PACK_ROOT", tmp_path / "absent")
    assert load_voice_pack(Spy()) is None


def test_an_unreadable_pack_is_skipped_rather_than_fatal(tmp_path,
                                                         monkeypatch):
    from pitcrew.engineer import voice as voice_module

    root = tmp_path / "voice_pack"
    (root / "broken").mkdir(parents=True)
    (root / "broken" / "manifest.json").write_text("{not json",
                                                   encoding="utf-8")
    monkeypatch.setattr(voice_module, "PACK_ROOT", root)
    assert load_voice_pack(Spy()) is None


def test_the_pack_sits_in_front_of_the_live_engine(tmp_path, monkeypatch):
    """pack -> Piper -> SAPI -> silent, with the pack wrapping, not replacing."""
    from pitcrew.engineer import voice as voice_module

    spy = Spy()
    monkeypatch.setattr(voice_module, "PiperEngine", lambda: spy)
    root = tmp_path / "voice_pack"
    folder = root / "test-voice"
    folder.mkdir(parents=True)
    (folder / "manifest.json").write_text(
        json.dumps({"clips": {"P4.": {"file": "x.wav"}}}), encoding="utf-8")
    monkeypatch.setattr(voice_module, "PACK_ROOT", root)

    engine = voice_module._best_engine()
    assert isinstance(engine, VoicePackEngine)
    assert engine._fallback is spy
