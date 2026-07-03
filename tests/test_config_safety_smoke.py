"""Config Safety Guardrails — headless MainWindow construction is config-safe.

Constructs the real ``MainWindow`` (offscreen) against an **isolated temp
config** and proves:

  * the real ``config.json`` is byte-identical before and after (SHA-256),
  * no real API key leaks into the window's in-memory config (the temp dir has
    no ``api_key.txt`` to auto-load, and the temp config's key is empty),
  * even a construction that persists writes only the temp file.

This is the committed, safe replacement for the ad-hoc smoke run that clobbered
the user's config. It is skipped when PyQt6 isn't importable so pure-Python CI
still passes. The session-autouse ``_guard_real_config`` fixture (conftest.py)
independently fails the whole run if any test mutates the real config.
"""
from __future__ import annotations

import hashlib
import os
import queue
from pathlib import Path
from unittest.mock import MagicMock

import pytest

pytest.importorskip("PyQt6", reason="PyQt6 not available for headless smoke test")

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication  # noqa: E402

import config_paths as cp  # noqa: E402


def _digest(path: Path):
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def _build_window(config_path: str):
    """Construct MainWindow with mocked collaborators (no audio/threads/DB)."""
    from ui.dashboard import MainWindow, SignalBridge
    config = cp.load_config(config_path)
    return MainWindow(
        config=config,
        logger=MagicMock(),
        announcer=MagicMock(),
        bridge=SignalBridge(),
        ui_queue=queue.Queue(),
        config_path=config_path,
        db=None,
    )


class TestSmokeConfigSafety:
    def test_construction_uses_temp_config_and_leaves_real_untouched(
        self, qapp, temp_config_path
    ):
        real = Path(cp.REAL_CONFIG_PATH)
        before = _digest(real)

        win = _build_window(temp_config_path)

        # The window is wired to the temp path, not the real one.
        assert win._config_path == temp_config_path
        assert Path(win._config_path).resolve() != cp.REAL_CONFIG_PATH

        # No real API key leaked in (temp dir has no api_key.txt; temp cfg empty).
        assert win._config.get("anthropic", {}).get("api_key", "") == ""

        # The real config.json is byte-identical.
        assert _digest(real) == before, "MainWindow construction touched the real config.json"

    def test_persist_to_temp_writes_only_temp(self, qapp, temp_config_path):
        real = Path(cp.REAL_CONFIG_PATH)
        before = _digest(real)

        win = _build_window(temp_config_path)
        win._config["strategy"]["track"] = "SmokeTestTrack"
        win._persist_config()  # writes the TEMP path via the guarded saver

        # Temp file got the change; real file is untouched.
        assert cp.load_config(temp_config_path)["strategy"]["track"] == "SmokeTestTrack"
        assert _digest(real) == before

    def test_persist_to_real_path_is_blocked(self, qapp):
        """A window mistakenly wired to the real path cannot clobber it: the
        guardrail turns the write into a no-op (logged), not a crash."""
        real = Path(cp.REAL_CONFIG_PATH)
        before = _digest(real)

        from ui.dashboard import MainWindow, SignalBridge
        win = MainWindow(
            config=cp.load_config(str(real)),   # returns DEFAULT under tests
            logger=MagicMock(),
            announcer=MagicMock(),
            bridge=SignalBridge(),
            ui_queue=queue.Queue(),
            config_path=str(real),
            db=None,
        )
        win._config["strategy"]["track"] = "ShouldNeverBeWritten"
        win._persist_config()  # blocked + logged, must not raise or write

        assert _digest(real) == before, "guardrail failed: real config.json was written"
