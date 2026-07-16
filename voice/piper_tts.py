"""Local neural TTS via Piper — natural, offline, private (no cloud, no API key).

Optional speech engine used by :mod:`voice.announcer` when the voice config sets
``tts_engine == "piper"``. Piper synthesises far more natural speech than the
legacy Windows SAPI5 "Desktop" voices while staying fully on-device, matching
the determinism rebuild's local-only guarantee.

This wrapper is deliberately thin and defensive: if ``piper-tts`` is not
installed or no voice model is present, :meth:`PiperEngine.load` fails cleanly and
the announcer falls back to SAPI5. Synthesis returns raw int16 mono samples so
the announcer plays them through its existing sounddevice output path (the same
one the beeps/PTT cues use) — no new audio plumbing.

Voice models (``*.onnx`` + ``*.onnx.json``) live in ``voice/piper_models/`` and
are downloaded once via ``python -m piper.download_voices <name> <dir>`` (they are
gitignored — ~60 MB each). The shipped default is ``en_GB-alan-medium`` (a calm
British male, the classic race-engineer radio voice).
"""
from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Optional, Tuple

_MODELS_DIR = Path(__file__).resolve().parent / "piper_models"


def find_default_model(models_dir=None) -> str:
    """Return the path to the first ``*.onnx`` voice model found, or ""."""
    d = Path(models_dir) if models_dir else _MODELS_DIR
    try:
        hits = sorted(p for p in d.glob("*.onnx") if p.is_file())
    except Exception:
        return ""
    return str(hits[0]) if hits else ""


def _resolve_model(model: str, models_dir=None) -> str:
    """Resolve a config value to a model path.

    Accepts an absolute/relative ``.onnx`` path, a bare voice name
    (``en_GB-alan-medium`` → ``<models_dir>/en_GB-alan-medium.onnx``), or "" to
    auto-pick the first model in ``models_dir``.
    """
    if not model:
        return find_default_model(models_dir)
    p = Path(model)
    if p.suffix == ".onnx" and p.is_file():
        return str(p)
    d = Path(models_dir) if models_dir else _MODELS_DIR
    cand = d / (model if model.endswith(".onnx") else f"{model}.onnx")
    if cand.is_file():
        return str(cand)
    return str(p) if p.is_file() else ""


class PiperEngine:
    """Loads a Piper voice model and synthesises int16 PCM. Thread-safe synth."""

    def __init__(self, model: str = "", *, models_dir=None) -> None:
        self._voice = None
        self._sr = 22050
        self._lock = threading.Lock()
        self._model_path = _resolve_model(model, models_dir)
        self.error = ""

    @property
    def available(self) -> bool:
        return self._voice is not None

    @property
    def model_path(self) -> str:
        return self._model_path

    @property
    def model_name(self) -> str:
        return Path(self._model_path).stem if self._model_path else ""

    def load(self) -> bool:
        """Load the ONNX voice model. Returns True on success (idempotent)."""
        if self._voice is not None:
            return True
        if not self._model_path or not os.path.exists(self._model_path):
            self.error = "no Piper voice model found in voice/piper_models"
            return False
        try:
            from piper import PiperVoice
        except Exception as e:  # piper-tts not installed
            self.error = f"piper-tts not installed ({e})"
            return False
        try:
            self._voice = PiperVoice.load(self._model_path)
            return True
        except Exception as e:
            self.error = f"model load failed: {e}"
            self._voice = None
            return False

    def warmup(self) -> None:
        """Prime onnxruntime so the first real utterance has no cold-start lag."""
        try:
            if self.load():
                with self._lock:
                    list(self._voice.synthesize("ready"))
        except Exception:
            pass

    def synth(self, text: str, *, rate_wpm: int = 175, volume: float = 1.0
              ) -> Tuple[Optional["object"], int]:
        """Synthesise ``text`` → (int16 mono ndarray, sample_rate).

        Returns (None, sr) on any failure so the caller can fall back to SAPI5.
        ``rate_wpm`` maps to Piper's length_scale (higher wpm → shorter/faster).
        """
        text = (text or "").strip()
        if not text or not self.load():
            return None, self._sr
        try:
            import numpy as np
            from piper.config import SynthesisConfig
            # Piper's default cadence (~length_scale 1.0) sits near ~175 wpm; scale
            # inversely so the user's rate setting still shifts pace sensibly.
            length_scale = max(0.5, min(2.0, 175.0 / max(int(rate_wpm), 60)))
            syn = SynthesisConfig(
                length_scale=length_scale,
                volume=max(0.0, min(1.0, float(volume))),
                normalize_audio=True)
            parts = []
            sr = self._sr
            with self._lock:
                for ch in self._voice.synthesize(text, syn):
                    parts.append(np.frombuffer(ch.audio_int16_bytes, dtype=np.int16))
                    sr = ch.sample_rate
            self._sr = sr
            if not parts:
                return None, sr
            return np.concatenate(parts), sr
        except Exception as e:
            self.error = f"synthesis failed: {e}"
            return None, self._sr
