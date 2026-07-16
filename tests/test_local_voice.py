"""Sprint 11 — speech recognition is LOCAL-only (no cloud transcription).

Pit Crew is fully local and private: the push-to-talk voice path must never
send audio to a cloud service. These tests lock that in at the source level
(no audio / pocketsphinx dependency required to run).
"""
from __future__ import annotations

import re
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
_QL_SRC = (_REPO / "voice" / "query_listener.py").read_text(encoding="utf-8")
_DASH_SRC = (_REPO / "ui" / "dashboard.py").read_text(encoding="utf-8")


def test_no_cloud_recognition_call_in_query_listener():
    # A real call is `.recognize_google(` — the docstring mention (no parens) is fine.
    assert ".recognize_google(" not in _QL_SRC


def test_local_sphinx_is_used():
    assert ".recognize_sphinx(" in _QL_SRC


def test_config_default_backend_is_local():
    import config_paths
    default = config_paths.DEFAULT_CONFIG
    assert default.get("query", {}).get("speech_backend") == "sphinx"


def test_settings_combo_has_no_cloud_option():
    # No "google" backend value should be offered in the settings combo.
    combo_region = _DASH_SRC[_DASH_SRC.find("_combo_speech_backend"):
                             _DASH_SRC.find("_combo_speech_backend") + 800]
    assert '"google"' not in combo_region and "'google'" not in combo_region


def test_recognise_signature_defaults_local():
    from voice import query_listener as ql
    import inspect
    sig = inspect.signature(ql._recognise)
    assert sig.parameters["backend"].default == "sphinx"
