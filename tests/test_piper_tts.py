"""Tests for local Piper neural TTS (voice/piper_tts.py) and its wiring into the
VoiceAnnouncer speak path.

Two layers:
  * PiperEngine — model resolution, load/synth, and clean fallback when a model
    or the piper-tts package is absent (skipped when the model isn't downloaded).
  * VoiceAnnouncer._speak_piper — routes spoken text through Piper and plays it
    via sounddevice, honours interrupts, and returns None (→ SAPI fallback) when
    synthesis yields nothing. Sounddevice is mocked, so this runs with no audio
    hardware and no model.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from voice import piper_tts
from voice.piper_tts import (
    PiperEngine, find_default_model, _resolve_model, list_local_voices,
    friendly_label,
)
import voice.announcer as announcer
from voice.announcer import VoiceAnnouncer


_HAS_MODEL = bool(find_default_model())


# ── PiperEngine: resolution + fallback (always run) ─────────────────────────

def test_resolve_model_missing_returns_empty(tmp_path):
    assert _resolve_model("nope", models_dir=tmp_path) == ""


def test_resolve_model_by_name(tmp_path):
    f = tmp_path / "en_GB-alan-medium.onnx"
    f.write_bytes(b"\x00")
    assert _resolve_model("en_GB-alan-medium", models_dir=tmp_path) == str(f)


def test_engine_fallback_when_no_model(tmp_path):
    e = PiperEngine("does-not-exist", models_dir=tmp_path)
    assert e.load() is False
    assert e.available is False
    assert "no Piper voice model" in e.error
    samples, sr = e.synth("hello")
    assert samples is None


# ── PiperEngine: real synthesis (skipped without a downloaded model) ────────

@pytest.mark.skipif(not _HAS_MODEL, reason="no Piper voice model downloaded")
def test_engine_synthesises_nonsilent_pcm():
    e = PiperEngine()
    assert e.load() is True
    samples, sr = e.synth("Box, box. Pit this lap.", rate_wpm=175, volume=1.0)
    assert samples is not None and len(samples) > 0
    assert samples.dtype == np.int16
    assert sr == 22050
    rms = float(np.sqrt(np.mean(samples.astype(np.float32) ** 2)))
    assert rms > 100  # non-silent


# ── Announcer routing with mocked sounddevice ───────────────────────────────

class _FakeSD:
    def __init__(self):
        self.play_calls = []
        self.stopped = 0

    def play(self, samples, sr, device=None, blocking=False):
        self.play_calls.append((len(samples), sr, device, blocking))

    def stop(self):
        self.stopped += 1


class _FakeSp:
    def __init__(self):
        self.speaks = []

    def Speak(self, text, flags=0):
        self.speaks.append((text, flags))


class _StubEngine:
    """Piper stand-in returning fixed samples — no model needed."""
    def __init__(self, samples):
        self._samples = samples

    def synth(self, text, *, rate_wpm=175, volume=1.0):
        return self._samples, 22050


class _Ann:
    def __init__(self, text, interrupt=False):
        self.text = text
        self.interrupt = interrupt
        self.cooldown_key = "k"


@pytest.fixture
def mocked_sd(monkeypatch):
    fake = _FakeSD()
    monkeypatch.setattr(announcer, "_SD_OK", True)
    monkeypatch.setattr(announcer, "_sd", fake)
    return fake


def _announcer_with_engine(samples):
    a = VoiceAnnouncer({"enabled": True, "rate": 175, "volume": 1.0})
    a._piper = _StubEngine(samples)
    a._beep_dev_eff = None
    return a


def test_speak_piper_plays_and_returns_duration(mocked_sd):
    samples = np.zeros(22050, dtype=np.int16)  # 1.0s of audio
    a = _announcer_with_engine(samples)
    dur = a._speak_piper(_Ann("box box"), _FakeSp(), 2, 1)
    assert dur is not None
    assert abs(dur - (1.0 + 0.15)) < 0.02  # duration + tail
    assert mocked_sd.play_calls and mocked_sd.play_calls[0][0] == 22050


def test_speak_piper_interrupt_stops_and_purges(mocked_sd):
    a = _announcer_with_engine(np.zeros(4410, dtype=np.int16))
    sp = _FakeSp()
    a._speak_piper(_Ann("box box", interrupt=True), sp, 2, 1)
    assert mocked_sd.stopped == 1          # current playback cut
    assert sp.speaks and sp.speaks[0][0] == ""  # SAPI leftover purged


def test_speak_piper_empty_synth_falls_back(mocked_sd):
    a = _announcer_with_engine(None)       # engine yields nothing
    assert a._speak_piper(_Ann("box box"), _FakeSp(), 2, 1) is None
    assert not mocked_sd.play_calls


def test_speak_piper_none_engine_returns_none(mocked_sd):
    a = VoiceAnnouncer({"enabled": True})
    a._piper = None
    assert a._speak_piper(_Ann("x"), _FakeSp(), 2, 1) is None


# ── In-app voice listing + friendly labels ──────────────────────────────────

def test_friendly_label_from_filename():
    assert friendly_label("en_US-ryan-high").startswith("Ryan")
    assert "high" in friendly_label("en_US-ryan-high")


def test_list_local_voices_reads_pairs(tmp_path):
    (tmp_path / "en_GB-alan-medium.onnx").write_bytes(b"\x00")
    (tmp_path / "en_GB-alan-medium.onnx.json").write_text(
        '{"audio":{"quality":"medium"},"dataset":"alan",'
        '"language":{"country_english":"Great Britain","code":"en_GB"}}',
        encoding="utf-8")
    # a stray .onnx with no json config is ignored
    (tmp_path / "orphan.onnx").write_bytes(b"\x00")
    voices = list_local_voices(models_dir=tmp_path)
    assert [v["name"] for v in voices] == ["en_GB-alan-medium"]
    assert voices[0]["label"].startswith("Alan")
    assert voices[0]["quality"] == "medium"


# ── Runtime engine/voice hot-swap (update_config) ───────────────────────────

def test_update_config_switch_to_sapi5_drops_piper():
    a = VoiceAnnouncer({"enabled": True})
    a._piper = _StubEngine(np.zeros(10, dtype=np.int16))
    a.update_config({"tts_engine": "sapi5"})
    assert a._piper is None


def test_sync_piper_engine_loads_in_background(monkeypatch):
    import threading as _t

    class _FakeEng:
        def __init__(self, model="", **k):
            self._model = model
            self.model_name = model or "auto"
            self.model_path = f"/models/{model or 'auto'}.onnx"
            self.error = ""

        def load(self):
            return True

        def warmup(self):
            pass

    monkeypatch.setattr(piper_tts, "PiperEngine", _FakeEng)
    monkeypatch.setattr(piper_tts, "_resolve_model",
                        lambda m, models_dir=None: f"/models/{m or 'auto'}.onnx")

    a = VoiceAnnouncer({"enabled": True})
    a._piper = None
    a.update_config({"tts_engine": "piper", "piper_model": "en_US-ryan-high"})
    # The (re)load runs on a daemon thread; wait for it to swap in.
    for t in _t.enumerate():
        if t.name == "PiperSwitch":
            t.join(timeout=3)
    assert a._piper is not None
    assert a._piper.model_name == "en_US-ryan-high"
