"""OFR-2 Setup-Builder UI wiring tests.

Two categories, following the house pattern from test_ofr1_trigger_wiring.py:

1. Source-scan tests: assert the method bodies contain the expected fragments
   (or do NOT contain forbidden ones) without importing PyQt6 or constructing
   MainWindow.

2. Behavioural stub tests: bind the REAL _resolve_recent_laps to a minimal
   stub (types.MethodType + MagicMock, matching the _make_scoring_stub pattern
   from test_ofr1_trigger_wiring.py) and exercise the happy path, the no-db
   guard, the zero-car-id guard, the no-session guard, and the exception guard.
"""
from __future__ import annotations

import re
import types
from pathlib import Path
from unittest.mock import MagicMock

import pytest

ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# Source helpers (mirror test_legacy_fanout_phase_5._method_body)
# ---------------------------------------------------------------------------

def _method_body(src: str, name: str) -> str:
    m = re.search(
        rf"\n    def {name}\(.*?(?=\n    def |\n(?:class |# ---)|\Z)",
        src, re.DOTALL,
    )
    assert m, f"method {name!r} not found in source"
    return m.group(0)


@pytest.fixture(scope="module")
def sbu_src() -> str:
    return (ROOT / "ui" / "setup_builder_ui.py").read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# 1. Source-scan: _resolve_recent_laps helper wiring (still used by the
#    deterministic setup engine to feed per-lap telemetry)
# ---------------------------------------------------------------------------

class TestResolveRecentLapsHelperWiring:

    def test_calls_get_session_laps_in_helper(self, sbu_src):
        # get_session_laps must appear in the _resolve_recent_laps helper body.
        helper = _method_body(sbu_src, "_resolve_recent_laps")
        assert "get_session_laps" in helper

    def test_calls_get_previous_session_id_in_helper(self, sbu_src):
        helper = _method_body(sbu_src, "_resolve_recent_laps")
        assert "get_previous_session_id" in helper


# ---------------------------------------------------------------------------
# 2. Source-scan: _build_setup_ai_snapshot body contracts
# ---------------------------------------------------------------------------

class TestBuildSetupAiSnapshotBody:

    def test_passes_session_type_kwarg(self, sbu_src):
        body = _method_body(sbu_src, "_build_setup_ai_snapshot")
        assert "session_type=" in body, (
            "_build_setup_ai_snapshot must pass session_type= to "
            "build_setup_ai_snapshot so SetupAISnapshot.discipline is real")

    def test_reads_setup_type_defensively(self, sbu_src):
        body = _method_body(sbu_src, "_build_setup_ai_snapshot")
        assert 'hasattr(self, "_setup_type")' in body, (
            "session_type read must be guarded with hasattr so the helper "
            "is safe before the combo widget is created")


# ---------------------------------------------------------------------------
# 3. Source-scan: _resolve_recent_laps body contracts
# ---------------------------------------------------------------------------

class TestResolveRecentLapsBody:

    def test_method_exists(self, sbu_src):
        body = _method_body(sbu_src, "_resolve_recent_laps")
        assert body

    def test_has_guard_no_db(self, sbu_src):
        body = _method_body(sbu_src, "_resolve_recent_laps")
        assert "self._db" in body

    def test_has_guard_car_id(self, sbu_src):
        body = _method_body(sbu_src, "_resolve_recent_laps")
        assert "car_id > 0" in body

    def test_has_guard_track(self, sbu_src):
        body = _method_body(sbu_src, "_resolve_recent_laps")
        assert "track" in body

    def test_returns_list_on_no_session(self, sbu_src):
        body = _method_body(sbu_src, "_resolve_recent_laps")
        # Must guard on falsy sid and return []
        assert "return []" in body

    def test_fully_try_wrapped(self, sbu_src):
        body = _method_body(sbu_src, "_resolve_recent_laps")
        assert "except Exception" in body, (
            "_resolve_recent_laps must be wrapped in try/except so it "
            "can never raise")

    def test_passes_latest_true_to_get_session_laps(self, sbu_src):
        """I1: _resolve_recent_laps must pass latest=True to get_session_laps
        so it fetches the most recent laps rather than the earliest ones."""
        body = _method_body(sbu_src, "_resolve_recent_laps")
        assert "latest=True" in body, (
            "_resolve_recent_laps must pass latest=True to get_session_laps "
            "(I1: avoid returning early full-fuel laps instead of recent stint)"
        )


# ---------------------------------------------------------------------------
# 4. Behavioural stub tests for _resolve_recent_laps
# ---------------------------------------------------------------------------

def _make_sbu_stub():
    """Build a minimal stub with the REAL _resolve_recent_laps bound to it.

    Follows the _make_scoring_stub pattern from test_ofr1_trigger_wiring.py:
    MagicMock shell, real DB mock, then bind the method with types.MethodType.
    No QApplication or MainWindow construction required.
    """
    from ui import setup_builder_ui as _sbu_mod

    stub = MagicMock()
    stub._db = MagicMock()
    stub._resolve_recent_laps = types.MethodType(
        _sbu_mod.SetupBuilderMixin._resolve_recent_laps, stub
    )
    return stub


class TestResolveRecentLapsBehaviour:

    def test_happy_path_returns_laps(self):
        """Happy path: db present, valid car_id and track → both DB calls made,
        lap rows returned."""
        stub = _make_sbu_stub()
        _fake_laps = [{"lap_num": 1, "lap_time_ms": 90_000}]
        stub._db.get_previous_session_id.return_value = 42
        stub._db.get_session_laps.return_value = _fake_laps

        result = stub._resolve_recent_laps(7, "Suzuka")

        stub._db.get_previous_session_id.assert_called_once_with(7, "Suzuka", 99_999_999)
        stub._db.get_session_laps.assert_called_once_with(
            42, exclude_pit=True, exclude_out=True, limit=5, latest=True
        )
        assert result == _fake_laps

    def test_db_none_returns_empty_list(self):
        """When _db is None the guard must return [] without raising."""
        stub = _make_sbu_stub()
        stub._db = None

        result = stub._resolve_recent_laps(7, "Suzuka")

        assert result == []

    def test_zero_car_id_returns_empty_list(self):
        """car_id <= 0 → guard must return [] without any DB call."""
        stub = _make_sbu_stub()

        result = stub._resolve_recent_laps(0, "Suzuka")

        stub._db.get_previous_session_id.assert_not_called()
        assert result == []

    def test_empty_track_returns_empty_list(self):
        """Empty track string → guard must return [] without any DB call."""
        stub = _make_sbu_stub()

        result = stub._resolve_recent_laps(7, "")

        stub._db.get_previous_session_id.assert_not_called()
        assert result == []

    def test_no_previous_session_returns_empty_list(self):
        """get_previous_session_id returns 0 → no get_session_laps call, [] returned."""
        stub = _make_sbu_stub()
        stub._db.get_previous_session_id.return_value = 0

        result = stub._resolve_recent_laps(7, "Suzuka")

        stub._db.get_session_laps.assert_not_called()
        assert result == []

    def test_exception_in_get_previous_session_id_returns_empty_list(self):
        """If get_previous_session_id raises, the guard must swallow it and return []."""
        stub = _make_sbu_stub()
        stub._db.get_previous_session_id.side_effect = RuntimeError("DB exploded")

        result = stub._resolve_recent_laps(7, "Suzuka")

        assert result == []

    def test_exception_in_get_session_laps_returns_empty_list(self):
        """If get_session_laps raises, the guard must swallow it and return []."""
        stub = _make_sbu_stub()
        stub._db.get_previous_session_id.return_value = 42
        stub._db.get_session_laps.side_effect = RuntimeError("rows gone")

        result = stub._resolve_recent_laps(7, "Suzuka")

        assert result == []
