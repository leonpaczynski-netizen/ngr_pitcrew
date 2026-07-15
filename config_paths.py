"""Config path resolution, safe loading/saving, and test guardrails.

Added by the **Config Safety Guardrails** sprint (2026-07-03). Pure Python — no
PyQt6, no app imports — so it is unit-testable without a QApplication and cannot
create import cycles (``main`` and ``ui.dashboard`` import *from* here).

Why this exists
---------------
The app treats ``config.json`` as its live settings store and rewrites it during
normal use (and during ``MainWindow`` construction, via the api-key auto-load +
``config_id`` derivation paths). During the Home Dashboard Promotion sprint a
headless smoke test constructed ``MainWindow`` pointed at the **real**
``config.json`` and clobbered the user's personal settings — and the file is
gitignored, so there was no recovery copy.

This module centralises three things so that can never happen again:

1. **Path resolution** (:func:`resolve_config_path`) — explicit arg →
   ``NGR_CONFIG_PATH`` env → the default ``config.json``. Tests and smoke runs
   inject a temp path; the normal app is unchanged.
2. **A test guardrail** — under pytest (or ``NGR_TEST_MODE=1``), reading or
   writing the *real* ``config.json`` is refused unless explicitly allowed with
   ``NGR_ALLOW_REAL_CONFIG=1``. Writes raise :class:`ConfigSafetyError`; reads
   fall back to :data:`DEFAULT_CONFIG` (so a test never exposes the user's API
   key or clobbers the file even if it forgets to pass a temp path).
3. **Safe writes** (:func:`save_config`) — serialise first (never truncate the
   target on an encoding error), optional ``.bak`` backup, then an **atomic**
   ``os.replace`` from a temp file.

Nothing here logs or returns secret values.
"""

from __future__ import annotations

import copy
import json
import logging
import os
import shutil
import sys
from pathlib import Path
from typing import Optional

_log = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# The canonical default config (single source of truth).
# --------------------------------------------------------------------------- #
# Moved here from ``main.py`` (re-exported there for backward compatibility).
# Schema unchanged from the previous ``main.DEFAULT_CONFIG`` except the
# explicit ``strategy.degradation_consecutive_laps: 2`` — previously only a
# read-time ``.get(..., 2)`` default, now materialised so a freshly created
# config carries it (matches the value pinned by
# ``tests/test_group38_relative_degradation_acceptance.py``). Behaviour is
# identical everywhere the key is read.
DEFAULT_CONFIG = {
    "connection": {"host": "127.0.0.1", "port": 33741},
    "tyre_thresholds": {
        "cold_max": 70.0, "warming_max": 85.0,
        "optimal_max": 100.0, "hot_max": 115.0,
    },
    "voice": {
        "enabled": True, "rate": 175, "volume": 1.0, "voice_id": "",
        "tyre_alerts": True, "lap_alerts": True,
        "position_alerts": False, "fuel_alerts": True, "countdown_alerts": False,
        "beep_device": None,
        "beep_use_tts": False,
    },
    "fuel": {"safety_margin_laps": 1.0, "pit_threshold_liters": 0.5},
    "ui": {"refresh_ms": 100},
    "query": {
        "speech_backend": "google",
        "mic_index": None,
        "record_secs": 3.0,
    },
    "query_button": {},
    "strategy": {
        "stops": [],
        "track": "",
        "total_laps": 25,
        "tyre_wear_multiplier": 1.0,
        "fuel_burn_per_lap": 2.0,
        "refuel_speed_lps": 10.0,
        "pit_loss_secs": 20.0,
        "lap_time_tolerance_ms": 1500,
        "fuel_tolerance_liters": 0.5,
        "degradation_consecutive_laps": 2,
    },
    "shift_beep": {
        "enabled": True,
        "qual_rpm": 7000,
        "race_rpm": 6500,
    },
    "car_setup": {
        "setups": []
    },
}


# --------------------------------------------------------------------------- #
# Names / constants
# --------------------------------------------------------------------------- #
DEFAULT_CONFIG_FILENAME = "config.json"

#: Env var a test / smoke run sets to point the app at an isolated config file.
ENV_CONFIG_PATH = "NGR_CONFIG_PATH"
#: Env var that (when truthy) opts *out* of the test guardrail — the explicit
#: "yes, I really do mean the real config" escape hatch.
ENV_ALLOW_REAL_CONFIG = "NGR_ALLOW_REAL_CONFIG"
#: Env var that (when "1") forces test mode even outside pytest.
ENV_TEST_MODE = "NGR_TEST_MODE"

#: Absolute path of the one file the guardrail protects — the repo-root
#: ``config.json`` next to this module.
REAL_CONFIG_PATH = (Path(__file__).resolve().parent / DEFAULT_CONFIG_FILENAME).resolve()


class ConfigSafetyError(RuntimeError):
    """Raised when a test would read/write the real user config without opting in."""


# --------------------------------------------------------------------------- #
# Environment / path predicates
# --------------------------------------------------------------------------- #
def is_test_environment() -> bool:
    """True when running under pytest (or forced via ``NGR_TEST_MODE=1``).

    ``python main.py`` never imports pytest, so the real app is never treated as
    a test environment.
    """
    if os.environ.get(ENV_TEST_MODE) == "1":
        return True
    if "PYTEST_CURRENT_TEST" in os.environ:
        return True
    return "pytest" in sys.modules


def _truthy(value: Optional[str]) -> bool:
    return bool(value) and value.strip().lower() not in ("", "0", "false", "no")


def real_config_writes_allowed() -> bool:
    """True when the explicit ``NGR_ALLOW_REAL_CONFIG`` opt-out is set."""
    return _truthy(os.environ.get(ENV_ALLOW_REAL_CONFIG))


def is_real_config_path(path) -> bool:
    """True when ``path`` resolves to the protected repo-root ``config.json``."""
    if not path:
        return False
    try:
        return Path(path).resolve() == REAL_CONFIG_PATH
    except Exception:  # pragma: no cover - defensive (bad path types)
        return False


def real_config_access_blocked(path) -> bool:
    """True when touching ``path`` should be refused: test env + real config +
    no explicit opt-in."""
    return (
        is_test_environment()
        and is_real_config_path(path)
        and not real_config_writes_allowed()
    )


def resolve_config_path(explicit: Optional[str] = None) -> str:
    """Resolve which config file to use.

    Precedence: ``explicit`` (e.g. ``--config``) → ``NGR_CONFIG_PATH`` env →
    the default ``config.json``. The normal app passes nothing and gets the
    default; tests/smoke runs inject a temp path here.
    """
    if explicit:
        return explicit
    env = os.environ.get(ENV_CONFIG_PATH)
    if env:
        return env
    return DEFAULT_CONFIG_FILENAME


# --------------------------------------------------------------------------- #
# Load / save
# --------------------------------------------------------------------------- #
def load_config(path: str) -> dict:
    """Load a config file deep-merged over :data:`DEFAULT_CONFIG`.

    Never raises: a missing/corrupt file yields a fresh copy of the defaults.
    Under the test guardrail, reading the *real* config is refused (returns the
    defaults instead) so a test never pulls the user's secrets into memory.
    """
    if real_config_access_blocked(path):
        _log.warning(
            "Config safety: refusing to READ the real config under tests "
            "(%s); using DEFAULT_CONFIG. Pass a temp path or set %s=1.",
            path, ENV_ALLOW_REAL_CONFIG,
        )
        return copy.deepcopy(DEFAULT_CONFIG)

    try:
        with open(path, encoding="utf-8") as f:
            loaded = json.load(f)
    except FileNotFoundError:
        return copy.deepcopy(DEFAULT_CONFIG)
    except json.JSONDecodeError as e:
        _log.warning("JSON error in %s: %s — using defaults", path, e)
        return copy.deepcopy(DEFAULT_CONFIG)
    except OSError as e:  # pragma: no cover - defensive
        _log.warning("Could not read %s: %s — using defaults", path, e)
        return copy.deepcopy(DEFAULT_CONFIG)

    cfg = copy.deepcopy(DEFAULT_CONFIG)
    if isinstance(loaded, dict):
        for k, v in loaded.items():
            if isinstance(v, dict) and isinstance(cfg.get(k), dict):
                cfg[k] = {**cfg[k], **v}
            else:
                cfg[k] = v
    return cfg


def save_config(path: str, config: dict, *, backup: bool = True) -> None:
    """Atomically write ``config`` to ``path``.

    * Refuses to write the real user config under the test guardrail
      (raises :class:`ConfigSafetyError`).
    * Serialises **before** touching the target, so an encoding error never
      truncates an existing file (no partial writes).
    * Optionally copies the existing file to ``<name>.bak`` first.
    * Writes to ``<name>.tmp`` then ``os.replace`` — an atomic swap on all
      platforms — so a crash mid-write cannot corrupt the config.
    """
    if real_config_access_blocked(path):
        raise ConfigSafetyError(
            f"Refusing to write the real config under tests ({path}). "
            f"Pass a temp path, or set {ENV_ALLOW_REAL_CONFIG}=1 to override."
        )
    if not isinstance(config, dict):
        raise TypeError("config must be a dict")

    # Serialise first — a non-serialisable value raises here, before any file
    # is opened, so the existing config is left intact.
    data = json.dumps(config, indent=4)

    p = Path(path)
    if p.parent and not p.parent.exists():
        p.parent.mkdir(parents=True, exist_ok=True)

    if backup and p.exists():
        try:
            shutil.copy2(p, p.with_name(p.name + ".bak"))
        except Exception as e:  # pragma: no cover - backup best-effort
            _log.warning("Config backup failed for %s: %s", p, e)

    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(data, encoding="utf-8")
    os.replace(tmp, p)


def write_default_config(path: str) -> dict:
    """Create ``path`` from :data:`DEFAULT_CONFIG` and return the written dict.

    Convenience for tests/smoke runs that need an isolated starting config.
    """
    cfg = copy.deepcopy(DEFAULT_CONFIG)
    save_config(path, cfg)
    return cfg
