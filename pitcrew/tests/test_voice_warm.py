"""Warming the live engine has to run it, not just load it.

Bathurst, 14 Sep 2026: the first pack miss of the race took 550 ms to start
against 137 ms once the model had run once. `warm()` loaded the model and
stopped, so the session's first real synthesis still paid for the ONNX
session's first run - on a call, at racing speed.
"""
from __future__ import annotations

import numpy as np
import pytest

from pitcrew.engineer import voice


class _Chunk:
    sample_rate = 22_050
    audio_int16_bytes = np.zeros(220, dtype=np.int16).tobytes()


class _FakeModel:
    def __init__(self) -> None:
        self.said: list[str] = []

    def synthesize(self, text, _config):
        self.said.append(text)
        yield _Chunk()


def _engine(monkeypatch) -> tuple[voice.PiperEngine, _FakeModel]:
    engine = object.__new__(voice.PiperEngine)
    engine.tuning = dict(voice.DEFAULT_TUNING)
    model = _FakeModel()
    engine._voice = None
    monkeypatch.setattr(engine, "_load", lambda: model)
    monkeypatch.setattr(engine, "_config", lambda: None)
    return engine, model


def test_warm_runs_one_synthesis(monkeypatch):
    engine, model = _engine(monkeypatch)
    engine.warm()
    assert model.said == [voice.WARM_LINE]


def test_warm_makes_no_sound(monkeypatch):
    """A throwaway line into a buffer: no stream, no card, nothing heard."""
    engine, _model = _engine(monkeypatch)

    def refuse(*_a, **_k):
        raise AssertionError("warm-up opened an audio stream")

    monkeypatch.setattr(voice, "open_output", refuse)
    monkeypatch.setattr(voice.audio_devices, "open_and_declare", refuse)
    engine.warm()


def test_the_pack_warms_the_engine_under_it(monkeypatch):
    engine, model = _engine(monkeypatch)
    pack = voice.VoicePackEngine(None, {}, engine)
    pack.warm()
    assert model.said == [voice.WARM_LINE]


if __name__ == "__main__":                                   # pragma: no cover
    raise SystemExit(pytest.main([__file__]))
