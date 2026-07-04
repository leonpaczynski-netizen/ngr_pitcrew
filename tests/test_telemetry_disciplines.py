"""OFR-2 — tests for strategy/telemetry_disciplines.py.

Covers:
- QUALIFYING block content (labels, derivation note, disclaimer, oversteer split)
- RACE block content (std-dev, "N/A (1 lap)", temps "— not recorded", partial temps)
- Zero clean laps honesty for both disciplines
- UNKNOWN purpose → None sentinel
- normalise_purpose routing ("Race Setup", "Qualifying Setup", None, enum)
- Empty-list behaviour (UNKNOWN → None, so prompt unchanged)
- No tyre_radius string anywhere
- AST purity scan (no PyQt6 / sqlite3 / open())
"""
from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
DISCIPLINES_PATH = ROOT / "strategy" / "telemetry_disciplines.py"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_quali_rows(n=3):
    rows = []
    for i in range(n):
        rows.append({
            "lap_num": i + 1,
            "lap_time_ms": 90_000 - i * 100,
            "fuel_used": 3.0,
            "is_pit_lap": 0,
            "is_out_lap": 0,
            "max_lat_g": 2.5 + i * 0.1,
            "lock_up_count": i + 1,
            "brake_consistency_m": 2.0 + i * 0.5,
            "oversteer_count": 2 + i,
            "oversteer_throttle_on": 1,
            "wheelspin_count": 0,
            "snap_throttle_count": 0,
            "tyre_temp_fl_avg": 0.0,
            "tyre_temp_fr_avg": 0.0,
            "tyre_temp_rl_avg": 0.0,
            "tyre_temp_rr_avg": 0.0,
        })
    return rows


def _make_race_rows(n=3, with_temps=False):
    rows = []
    for i in range(n):
        rows.append({
            "lap_num": i + 1,
            "lap_time_ms": 90_100 + i * 200,
            "fuel_used": 3.1 + i * 0.05,
            "is_pit_lap": 0,
            "is_out_lap": 0,
            "lock_up_count": 1,
            "wheelspin_count": 2,
            "snap_throttle_count": 3,
            "oversteer_count": 1,
            "oversteer_throttle_on": 0,
            "max_lat_g": 2.3,
            "brake_consistency_m": 1.5,
            "tyre_temp_fl_avg": 80.0 if with_temps else 0.0,
            "tyre_temp_fr_avg": 85.0 if with_temps else 0.0,
            "tyre_temp_rl_avg": 78.0 if with_temps else 0.0,
            "tyre_temp_rr_avg": 83.0 if with_temps else 0.0,
        })
    return rows


# ---------------------------------------------------------------------------
# AST purity scan
# ---------------------------------------------------------------------------

class TestPurityScan:
    def test_no_pyqt6_import(self):
        src = DISCIPLINES_PATH.read_text(encoding="utf-8")
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                names = [a.name for a in getattr(node, "names", [])]
                module = getattr(node, "module", "") or ""
                assert not any("PyQt6" in n for n in names), "PyQt6 import found"
                assert "PyQt6" not in module, "PyQt6 module import found"

    def test_no_sqlite3_import(self):
        src = DISCIPLINES_PATH.read_text(encoding="utf-8")
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                names = [a.name for a in getattr(node, "names", [])]
                module = getattr(node, "module", "") or ""
                assert "sqlite3" not in module
                assert not any("sqlite3" in n for n in names)

    def test_no_open_builtin_call(self):
        src = DISCIPLINES_PATH.read_text(encoding="utf-8")
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Name) and func.id == "open":
                    raise AssertionError("open() call found — violates purity contract")


# ---------------------------------------------------------------------------
# UNKNOWN purpose → None sentinel
# ---------------------------------------------------------------------------

class TestUnknownReturnsNone:
    def test_none_returns_sentinel(self):
        from strategy.telemetry_disciplines import build_discipline_telemetry_block as bdt
        assert bdt([], None) is None

    def test_empty_string_returns_sentinel(self):
        from strategy.telemetry_disciplines import build_discipline_telemetry_block as bdt
        assert bdt([], "") is None

    def test_unknown_string_returns_sentinel(self):
        from strategy.telemetry_disciplines import build_discipline_telemetry_block as bdt
        assert bdt([], "unknown") is None

    def test_junk_string_returns_sentinel(self):
        from strategy.telemetry_disciplines import build_discipline_telemetry_block as bdt
        assert bdt([], "foobar") is None

    def test_with_rows_and_unknown_returns_sentinel(self):
        from strategy.telemetry_disciplines import build_discipline_telemetry_block as bdt
        assert bdt(_make_race_rows(), "unknown") is None

    def test_empty_list_with_unknown_returns_sentinel(self):
        from strategy.telemetry_disciplines import build_discipline_telemetry_block as bdt
        # Empty list + UNKNOWN → None: means no-params call produces byte-identical prompt
        assert bdt([], None) is None


# ---------------------------------------------------------------------------
# normalise_purpose routing
# ---------------------------------------------------------------------------

class TestNormalisePurposeRouting:
    def test_race_setup_routes_to_race_block(self):
        from strategy.telemetry_disciplines import build_discipline_telemetry_block as bdt
        result = bdt(_make_race_rows(), "Race Setup")
        assert result is not None
        assert "RACE" in result

    def test_qualifying_setup_routes_to_qualifying_block(self):
        from strategy.telemetry_disciplines import build_discipline_telemetry_block as bdt
        result = bdt(_make_quali_rows(), "Qualifying Setup")
        assert result is not None
        assert "QUALIFYING" in result

    def test_qualifying_string_routes_to_qualifying_block(self):
        from strategy.telemetry_disciplines import build_discipline_telemetry_block as bdt
        result = bdt(_make_quali_rows(), "Qualifying")
        assert result is not None
        assert "QUALIFYING" in result

    def test_race_string_routes_to_race_block(self):
        from strategy.telemetry_disciplines import build_discipline_telemetry_block as bdt
        result = bdt(_make_race_rows(), "race")
        assert result is not None
        assert "RACE" in result

    def test_none_returns_sentinel(self):
        from strategy.telemetry_disciplines import build_discipline_telemetry_block as bdt
        assert bdt(_make_race_rows(), None) is None

    def test_setup_purpose_enum_qualifying(self):
        from data.setup_context import SetupPurpose
        from strategy.telemetry_disciplines import build_discipline_telemetry_block as bdt
        result = bdt(_make_quali_rows(), SetupPurpose.QUALIFYING)
        assert result is not None
        assert "QUALIFYING" in result

    def test_setup_purpose_enum_race(self):
        from data.setup_context import SetupPurpose
        from strategy.telemetry_disciplines import build_discipline_telemetry_block as bdt
        result = bdt(_make_race_rows(), SetupPurpose.RACE)
        assert result is not None
        assert "RACE" in result

    def test_setup_purpose_enum_unknown_returns_sentinel(self):
        from data.setup_context import SetupPurpose
        from strategy.telemetry_disciplines import build_discipline_telemetry_block as bdt
        assert bdt(_make_race_rows(), SetupPurpose.UNKNOWN) is None


# ---------------------------------------------------------------------------
# Zero clean laps
# ---------------------------------------------------------------------------

class TestZeroCleanLaps:
    def test_qualifying_no_laps_returns_honesty_line(self):
        from strategy.telemetry_disciplines import build_discipline_telemetry_block as bdt
        result = bdt([], "Qualifying")
        assert result is not None
        assert "No clean laps available" in result

    def test_race_no_laps_returns_honesty_line(self):
        from strategy.telemetry_disciplines import build_discipline_telemetry_block as bdt
        result = bdt([], "Race")
        assert result is not None
        assert "No clean laps available" in result

    def test_qualifying_pit_laps_only_returns_honesty_line(self):
        from strategy.telemetry_disciplines import build_discipline_telemetry_block as bdt
        rows = [{"lap_num": 1, "lap_time_ms": 90000, "is_pit_lap": 1, "is_out_lap": 0}]
        result = bdt(rows, "Qualifying")
        assert "No clean laps available" in result

    def test_race_out_laps_only_returns_honesty_line(self):
        from strategy.telemetry_disciplines import build_discipline_telemetry_block as bdt
        rows = [{"lap_num": 1, "lap_time_ms": 90000, "is_pit_lap": 0, "is_out_lap": 1}]
        result = bdt(rows, "Race")
        assert "No clean laps available" in result

    def test_no_division_by_zero_with_empty_race(self):
        from strategy.telemetry_disciplines import build_discipline_telemetry_block as bdt
        # Must not raise
        result = bdt([], "race")
        assert result is not None

    def test_no_division_by_zero_with_empty_qualifying(self):
        from strategy.telemetry_disciplines import build_discipline_telemetry_block as bdt
        result = bdt([], "qualifying")
        assert result is not None


# ---------------------------------------------------------------------------
# QUALIFYING block content
# ---------------------------------------------------------------------------

class TestQualifyingBlockContent:
    def _block(self, rows=None):
        from strategy.telemetry_disciplines import build_discipline_telemetry_block as bdt
        return bdt(rows or _make_quali_rows(), "Qualifying")

    def test_header_mentions_qualifying_focus(self):
        block = self._block()
        assert "QUALIFYING" in block
        assert "peak metrics" in block.lower() or "peak" in block

    def test_best_lap_measured_label(self):
        block = self._block()
        assert "Best lap" in block
        assert "[measured]" in block

    def test_peak_lateral_g_estimated_label(self):
        block = self._block()
        assert "Peak lateral G" in block
        assert "[estimated]" in block

    def test_peak_lateral_g_derivation_note(self):
        block = self._block()
        assert "angvel_z" in block
        assert "speed / 9.81" in block

    def test_lockup_count_calculated_label(self):
        block = self._block()
        assert "lock-up" in block.lower() or "lock_up" in block.lower() or "lockup" in block.lower()
        assert "[calculated]" in block

    def test_brake_consistency_calculated_label(self):
        block = self._block()
        assert "brake consistency" in block.lower() or "Brake consistency" in block
        assert "[calculated]" in block

    def test_brake_consistency_in_metres(self):
        block = self._block()
        # "m [calculated]" in the brake consistency line
        assert "m [calculated]" in block or " m" in block

    def test_brake_consistency_unavailable_when_minus_one(self):
        from strategy.telemetry_disciplines import build_discipline_telemetry_block as bdt
        rows = _make_quali_rows()
        for r in rows:
            r["brake_consistency_m"] = -1.0
        block = bdt(rows, "Qualifying")
        assert "unavailable" in block.lower()

    def test_oversteer_total_and_split(self):
        block = self._block()
        assert "oversteer" in block.lower() or "Oversteer" in block
        assert "throttle-on" in block.lower()
        assert "entry" in block.lower()

    def test_oversteer_split_calculated_label(self):
        block = self._block()
        # Rotation line should have [calculated]
        lower = block.lower()
        idx = lower.find("oversteer")
        assert "[calculated]" in block[idx:]

    def test_disclaimer_line_present(self):
        block = self._block()
        assert "Steering corrections" in block
        assert "not measured" in block.lower()

    def test_no_tyre_radius(self):
        block = self._block()
        assert "tyre_radius" not in block
        assert "tyre radius" not in block.lower()

    def test_ends_with_newline(self):
        block = self._block()
        assert block.endswith("\n")

    def test_oversteer_split_values_correct(self):
        from strategy.telemetry_disciplines import build_discipline_telemetry_block as bdt
        rows = _make_quali_rows(1)
        rows[0]["oversteer_count"] = 5
        rows[0]["oversteer_throttle_on"] = 2
        block = bdt(rows, "Qualifying")
        # total=5, throttle-on=2, entry=3
        assert "5" in block
        assert "2" in block
        assert "3" in block


# ---------------------------------------------------------------------------
# RACE block content
# ---------------------------------------------------------------------------

class TestRaceBlockContent:
    def _block(self, rows=None, **kw):
        from strategy.telemetry_disciplines import build_discipline_telemetry_block as bdt
        return bdt(rows or _make_race_rows(), "Race", **kw)

    def test_header_mentions_race_focus(self):
        block = self._block()
        assert "RACE" in block
        assert "consistency" in block.lower() or "efficiency" in block.lower()

    def test_fuel_per_lap_measured_label(self):
        block = self._block()
        assert "[measured]" in block
        assert "Fuel" in block or "fuel" in block

    def test_per_lap_fuel_values_present(self):
        block = self._block()
        # The 3 laps should have fuel values; first lap = 3.10
        assert "3.10" in block or "3.1" in block

    def test_lockup_rate_calculated_label(self):
        block = self._block()
        assert "Lock-up rate" in block or "lock-up rate" in block.lower()
        assert "[calculated]" in block

    def test_wheelspin_rate_calculated_label(self):
        block = self._block()
        assert "Wheelspin" in block or "wheelspin" in block
        assert "[calculated]" in block

    def test_snap_throttle_rate_calculated_label(self):
        block = self._block()
        assert "Snap-throttle" in block or "snap-throttle" in block.lower()
        assert "[calculated]" in block

    def test_stddev_calculated_label(self):
        block = self._block()
        assert "std-dev" in block.lower() or "std dev" in block.lower() or "stdev" in block.lower()
        assert "[calculated]" in block

    def test_one_lap_n_a_message(self):
        from strategy.telemetry_disciplines import build_discipline_telemetry_block as bdt
        rows = _make_race_rows(1)
        block = bdt(rows, "Race")
        assert "N/A (1 lap)" in block

    def test_multiple_laps_has_numeric_stddev(self):
        from strategy.telemetry_disciplines import build_discipline_telemetry_block as bdt
        rows = _make_race_rows(4)
        block = bdt(rows, "Race")
        assert "N/A (1 lap)" not in block
        # Some decimal number should appear for std-dev
        import re
        assert re.search(r"\d+\.\d{3} s", block) is not None

    def test_tyre_temps_not_recorded_when_all_zero(self):
        from strategy.telemetry_disciplines import build_discipline_telemetry_block as bdt
        rows = _make_race_rows(3, with_temps=False)
        block = bdt(rows, "Race")
        assert "— not recorded" in block

    def test_tyre_temps_rendered_when_present(self):
        from strategy.telemetry_disciplines import build_discipline_telemetry_block as bdt
        rows = _make_race_rows(3, with_temps=True)
        block = bdt(rows, "Race")
        assert "— not recorded" not in block
        # Should see the FL average (80°)
        assert "80" in block

    def test_partial_temps_render_what_exists(self):
        from strategy.telemetry_disciplines import build_discipline_telemetry_block as bdt
        rows = _make_race_rows(2)
        for r in rows:
            r["tyre_temp_fl_avg"] = 75.0
            r["tyre_temp_fr_avg"] = 0.0
            r["tyre_temp_rl_avg"] = 0.0
            r["tyre_temp_rr_avg"] = 0.0
        block = bdt(rows, "Race")
        # FL is non-zero → not "— not recorded"; partial rendering
        assert "— not recorded" not in block
        assert "75" in block

    def test_tyre_temps_measured_label(self):
        from strategy.telemetry_disciplines import build_discipline_telemetry_block as bdt
        rows = _make_race_rows(2, with_temps=True)
        block = bdt(rows, "Race")
        assert "tyre temp" in block.lower() or "Tyre temp" in block
        assert "[measured]" in block

    def test_no_tyre_radius(self):
        block = self._block()
        assert "tyre_radius" not in block
        assert "tyre radius" not in block.lower()

    def test_ends_with_newline(self):
        block = self._block()
        assert block.endswith("\n")


# ---------------------------------------------------------------------------
# ms_to_str injection
# ---------------------------------------------------------------------------

class TestMsToStrInjection:
    def test_custom_ms_to_str_used(self):
        from strategy.telemetry_disciplines import build_discipline_telemetry_block as bdt
        calls = []

        def mock_fmt(ms):
            calls.append(ms)
            return f"MOCK_{ms}"

        rows = _make_quali_rows(1)
        block = bdt(rows, "Qualifying", ms_to_str=mock_fmt)
        assert len(calls) > 0
        assert "MOCK_" in block

    def test_none_ms_to_str_uses_fallback(self):
        from strategy.telemetry_disciplines import build_discipline_telemetry_block as bdt
        rows = _make_quali_rows(1)
        # Should not raise
        block = bdt(rows, "Qualifying", ms_to_str=None)
        assert block is not None
        # Default formatter produces "m:ss.mmm" style
        assert ":" in block


# ---------------------------------------------------------------------------
# Clean-laps filter (pit/out lap exclusion)
# ---------------------------------------------------------------------------

class TestCleanLapsFilter:
    def test_pit_laps_excluded_from_qualifying(self):
        from strategy.telemetry_disciplines import build_discipline_telemetry_block as bdt
        rows = _make_quali_rows(2)
        # Add a pit lap — should not affect the "total lock-ups" count
        rows.append({
            "lap_num": 99, "lap_time_ms": 120_000, "is_pit_lap": 1, "is_out_lap": 0,
            "max_lat_g": 0.0, "lock_up_count": 100, "brake_consistency_m": -1.0,
            "oversteer_count": 0, "oversteer_throttle_on": 0, "fuel_used": 0.0,
        })
        block = bdt(rows, "Qualifying")
        # 100 lock-ups from the pit lap should NOT appear
        assert "100" not in block

    def test_out_laps_excluded_from_race(self):
        from strategy.telemetry_disciplines import build_discipline_telemetry_block as bdt
        rows = _make_race_rows(2)
        rows.append({
            "lap_num": 99, "lap_time_ms": 120_000, "is_pit_lap": 0, "is_out_lap": 1,
            "lock_up_count": 0, "wheelspin_count": 0, "snap_throttle_count": 0,
            "fuel_used": 99.0, "oversteer_count": 0, "oversteer_throttle_on": 0,
            "tyre_temp_fl_avg": 0.0, "tyre_temp_fr_avg": 0.0,
            "tyre_temp_rl_avg": 0.0, "tyre_temp_rr_avg": 0.0,
        })
        block = bdt(rows, "Race")
        # 99.0 L fuel from the out-lap should NOT appear
        assert "99.00" not in block
