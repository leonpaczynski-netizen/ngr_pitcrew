"""Shared pytest fixtures — config-safety isolation.

Added by the **Config Safety Guardrails** sprint (2026-07-03).

Two things live here:

1. ``temp_config_path`` — a per-test isolated ``config.json`` seeded from
   ``config_paths.DEFAULT_CONFIG``, in pytest's ``tmp_path``. Tests and smoke
   runs pass this to ``load_config`` / ``MainWindow(config_path=...)`` so they
   never touch the user's real config.

2. ``_guard_real_config`` — a **session-autouse** safety net that hashes the
   real ``config.json`` before and after the whole run and fails loudly if any
   test modified it. Compares SHA-256 digests, never raw bytes, so the API key
   is never held or printed.
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config_paths import REAL_CONFIG_PATH, write_default_config  # noqa: E402


def _config_digest() -> str | None:
    """SHA-256 of the real config file, or None if it doesn't exist.

    Hashing (not reading into a returned value) keeps the API key out of test
    state and out of any failure message.
    """
    p = Path(REAL_CONFIG_PATH)
    if not p.exists():
        return None
    return hashlib.sha256(p.read_bytes()).hexdigest()


@pytest.fixture(scope="session", autouse=True)
def _guard_real_config():
    """Fail the run if any test mutates the real config.json."""
    before = _config_digest()
    yield
    after = _config_digest()
    assert after == before, (
        "A test modified the real config.json during this run — tests must use "
        "an isolated temp config (see the temp_config_path fixture). The "
        "config-safety guardrail in config_paths.save_config should have "
        "prevented this."
    )


@pytest.fixture
def temp_config_path(tmp_path) -> str:
    """An isolated config.json seeded from DEFAULT_CONFIG, in a temp dir.

    Returns the path as a string. Because it lives outside the repo root it is
    never the guarded real config, so load/save operate on it freely.
    """
    path = tmp_path / "config.json"
    write_default_config(str(path))
    return str(path)
