"""The phrase pack: what it covers, and what happens when it does not.

The pack is an optimisation. The property that matters is not that it is fast
but that it is invisible: a line it does not carry, or cannot play, must reach
the driver anyway. An optimisation that can silence the engineer is a bug.
"""
from __future__ import annotations

import json
import wave

import pytest

from pitcrew.engineer import phrase_manifest as manifest
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
    VoicePackEngine,
    clip_filename,
    load_voice_pack,
)
from pitcrew.store.tyres import ALL_COMPOUNDS


# ------------------------------------------------------------- the manifest

def sweep() -> list[str]:
    """Everything `answer()` can say, over a representative set of states.

    Driven through the real function rather than listed, so a new branch in
    `answer()` shows up here as an uncovered line instead of as a pause in the
    driver's ear.
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
    lines += [answer(BOX_WHEN, {"lapsToStop": n}).text
              for n in range(0, manifest.MAX_LAPS + 1)]

    lines.append(answer(BOX_WHAT, empty).text)
    lines += [answer(BOX_WHAT, {"nextCompound": c.name}).text
              for c in ALL_COMPOUNDS]

    lines.append(answer(BOX_FUEL, empty).text)
    lines += [answer(BOX_FUEL, {"stopFuelL": float(n)}).text
              for n in range(0, manifest.MAX_FUEL_LITRES + 1)]

    lines += list(manifest.plan_summary_examples())
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


def test_the_only_declared_gap_is_the_plan_summary():
    """If anything else starts falling through, it is a bug, not a decision."""
    uncovered = [line for line in sweep()
                 if manifest.uncovered_reason(line)]
    assert uncovered, "the plan summary should still be a declared gap"
    for line in uncovered:
        assert "," in line, f"{line!r} is not a plan summary"
        assert "combinatorial" in manifest.uncovered_reason(line)


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


def test_the_pack_stays_under_five_hundred_clips():
    """The budget is real: every clip is a file to render and to ship."""
    assert len(manifest.clips()) < 500


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


def test_a_pack_with_no_live_engine_still_plays_what_it_has(pack, monkeypatch):
    """And says nothing, without raising, for what it has not."""
    folder, clips = pack
    engine = VoicePackEngine(folder, clips, None)
    played = []
    monkeypatch.setattr(engine, "_play", lambda segments: played.append(segments))

    engine.speak("P4.")
    engine.speak("Nothing rendered.")
    assert played == [("P4.",)]
    assert engine.hits == 1 and engine.misses == 1


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
