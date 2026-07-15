"""OFR-2 Race vs Qualifying Telemetry Disciplines — acceptance tests.

Post determinism-rebuild: the generative-AI prompt builders (strategy.ai_planner)
and the practice/strategy orchestrators were removed. The deterministic core of
OFR-2 survives and is what this file now covers:

* strategy.telemetry_disciplines.build_discipline_telemetry_block (pure builder)
* data.ai_context_snapshot discipline field derivation
* data.recommendation_scoring (OFR-1 block, untouched)
* ui.setup_builder_ui._resolve_recent_laps (per-lap telemetry resolver)

The AI-prompt-injection tests (AC1/AC2/AC3/AC5-prompt/AC7/AC11 and the prompt
edge cases) were deleted with the AI planner they exercised.
"""
from __future__ import annotations

import ast
import types
from pathlib import Path
from unittest.mock import MagicMock

import pytest

REPO = Path(__file__).resolve().parents[1]


# ===========================================================================
# Shared helpers
# ===========================================================================

def _clean_lap_row(i=0, **overrides):
    """A fully-populated clean lap row."""
    row = {
        "lap_num": i + 1,
        "lap_time_ms": 90_000 + i * 200,
        "fuel_used": 3.1 + i * 0.05,
        "is_pit_lap": 0,
        "is_out_lap": 0,
        "lock_up_count": 1,
        "wheelspin_count": 2,
        "snap_throttle_count": 1,
        "oversteer_count": 2,
        "oversteer_throttle_on": 1,
        "max_lat_g": 2.5,
        "brake_consistency_m": 2.0,
        "tyre_temp_fl_avg": 0.0,
        "tyre_temp_fr_avg": 0.0,
        "tyre_temp_rl_avg": 0.0,
        "tyre_temp_rr_avg": 0.0,
    }
    row.update(overrides)
    return row


def _laps(n=3, **overrides):
    return [_clean_lap_row(i, **overrides) for i in range(n)]


def _laps_with_temps(n=3):
    rows = []
    for i in range(n):
        rows.append(_clean_lap_row(
            i,
            tyre_temp_fl_avg=80.0,
            tyre_temp_fr_avg=85.0,
            tyre_temp_rl_avg=78.0,
            tyre_temp_rr_avg=83.0,
        ))
    return rows


# ===========================================================================
# AC4 — [measured]/[calculated]/[estimated] labels via the pure builder
# ===========================================================================

class TestAC4Labels:
    """AC4: all three data-quality labels appear in the discipline block."""

    def test_ac4_build_discipline_block_direct_estimated_label(self):
        """Direct call to build_discipline_telemetry_block for QUALIFYING."""
        from strategy.telemetry_disciplines import build_discipline_telemetry_block as bdt
        block = bdt(_laps(3), "Qualifying")
        assert "[estimated]" in block
        assert "angvel_z" in block

    def test_ac4_build_discipline_block_direct_measured_label_race(self):
        from strategy.telemetry_disciplines import build_discipline_telemetry_block as bdt
        block = bdt(_laps_with_temps(2), "Race")
        assert "[measured]" in block

    def test_ac4_build_discipline_block_direct_calculated_label_race(self):
        from strategy.telemetry_disciplines import build_discipline_telemetry_block as bdt
        block = bdt(_laps(3), "Race")
        assert "[calculated]" in block


# ===========================================================================
# AC5 — UNKNOWN purpose → None sentinel from the pure builder
# ===========================================================================

class TestAC5UnknownSentinel:
    """AC5: UNKNOWN purpose → build_discipline_telemetry_block returns None."""

    def test_ac5_build_discipline_block_unknown_returns_none_sentinel(self):
        from strategy.telemetry_disciplines import build_discipline_telemetry_block as bdt
        assert bdt(_laps(3), "unknown") is None
        assert bdt(_laps(3), None) is None
        assert bdt(_laps(3), "") is None


# ===========================================================================
# AC6 — No tyre_radius in any discipline block path
# ===========================================================================

class TestAC6NoTyreRadius:
    """AC6: tyre_radius must never appear in any discipline-block path."""

    def test_ac6_no_tyre_radius_in_disciplines_module_source(self):
        """The telemetry_disciplines module itself must not mention tyre_radius."""
        src = (REPO / "strategy" / "telemetry_disciplines.py").read_text(encoding="utf-8")
        assert "tyre_radius" not in src
        assert "tyre radius" not in src.lower()

    def test_ac6_no_tyre_radius_in_build_discipline_block_qualifying_output(self):
        from strategy.telemetry_disciplines import build_discipline_telemetry_block as bdt
        block = bdt(_laps(3), "Qualifying")
        assert block is not None
        assert "tyre_radius" not in block
        assert "tyre radius" not in block.lower()

    def test_ac6_no_tyre_radius_in_build_discipline_block_race_output(self):
        from strategy.telemetry_disciplines import build_discipline_telemetry_block as bdt
        block = bdt(_laps(3), "Race")
        assert block is not None
        assert "tyre_radius" not in block
        assert "tyre radius" not in block.lower()


# ===========================================================================
# AC8 — SetupAISnapshot + PracticeAnalysisSnapshot gain discipline field;
#        StrategyAISnapshot does NOT
# ===========================================================================

class TestAC8SnapshotDisciplineField:
    """AC8: dataclass field checks + derivations; StrategyAISnapshot negative check."""

    def test_ac8_setup_snapshot_has_discipline_field(self):
        from data.ai_context_snapshot import build_setup_ai_snapshot
        snap = build_setup_ai_snapshot()
        assert hasattr(snap, "discipline"), "SetupAISnapshot must have discipline field"

    def test_ac8_setup_snapshot_default_unknown(self):
        from data.ai_context_snapshot import build_setup_ai_snapshot
        assert build_setup_ai_snapshot().discipline == "unknown"

    def test_ac8_setup_snapshot_race_setup_derives_race(self):
        from data.ai_context_snapshot import build_setup_ai_snapshot
        snap = build_setup_ai_snapshot(session_type="Race Setup")
        assert snap.discipline == "race"

    def test_ac8_setup_snapshot_qualifying_setup_derives_qualifying(self):
        from data.ai_context_snapshot import build_setup_ai_snapshot
        snap = build_setup_ai_snapshot(session_type="Qualifying Setup")
        assert snap.discipline == "qualifying"

    def test_ac8_setup_snapshot_none_derives_unknown(self):
        from data.ai_context_snapshot import build_setup_ai_snapshot
        snap = build_setup_ai_snapshot(session_type=None)
        assert snap.discipline == "unknown"

    def test_ac8_practice_snapshot_has_discipline_field(self):
        from data.ai_context_snapshot import build_practice_analysis_snapshot
        snap = build_practice_analysis_snapshot()
        assert hasattr(snap, "discipline")

    def test_ac8_practice_snapshot_default_unknown(self):
        from data.ai_context_snapshot import build_practice_analysis_snapshot
        assert build_practice_analysis_snapshot().discipline == "unknown"

    def test_ac8_practice_snapshot_qualifying_derives_qualifying(self):
        from data.ai_context_snapshot import build_practice_analysis_snapshot
        snap = build_practice_analysis_snapshot(session_purpose="Qualifying")
        assert snap.discipline == "qualifying"

    def test_ac8_practice_snapshot_race_setup_derives_race(self):
        from data.ai_context_snapshot import build_practice_analysis_snapshot
        snap = build_practice_analysis_snapshot(session_purpose="Race Setup")
        assert snap.discipline == "race"

    def test_ac8_strategy_snapshot_has_no_discipline_field(self):
        from data.ai_context_snapshot import build_strategy_ai_snapshot
        snap = build_strategy_ai_snapshot()
        assert not hasattr(snap, "discipline"), (
            "StrategyAISnapshot must NOT have a discipline field (AC8 negative check)"
        )

    def test_ac8_strategy_snapshot_to_dict_no_discipline_key(self):
        from data.ai_context_snapshot import build_strategy_ai_snapshot
        d = build_strategy_ai_snapshot().to_dict()
        assert "discipline" not in d, (
            "StrategyAISnapshot.to_dict() must not carry a discipline key"
        )

    def test_ac8_setup_snapshot_to_dict_has_discipline(self):
        from data.ai_context_snapshot import build_setup_ai_snapshot
        d = build_setup_ai_snapshot(session_type="Race Setup").to_dict()
        assert "discipline" in d
        assert d["discipline"] == "race"

    def test_ac8_practice_snapshot_to_dict_has_discipline(self):
        from data.ai_context_snapshot import build_practice_analysis_snapshot
        d = build_practice_analysis_snapshot(session_purpose="Qualifying").to_dict()
        assert "discipline" in d
        assert d["discipline"] == "qualifying"

    def test_ac8_normalise_purpose_handles_enum_qualifying(self):
        """normalise_purpose accepts SetupPurpose enum values."""
        from data.setup_context import SetupPurpose, normalise_purpose
        assert normalise_purpose(SetupPurpose.QUALIFYING) == SetupPurpose.QUALIFYING

    def test_ac8_normalise_purpose_handles_enum_unknown(self):
        from data.setup_context import SetupPurpose, normalise_purpose
        assert normalise_purpose(SetupPurpose.UNKNOWN) == SetupPurpose.UNKNOWN


# ===========================================================================
# AC9 — New builder (telemetry_disciplines.py) is pure — AST scan
# ===========================================================================

class TestAC9BuilderPurity:
    """AC9: telemetry_disciplines.py must be pure (no PyQt6, no sqlite3, no IO,
    no config["strategy"] reads); frozen allowlist unchanged."""

    DISCIPLINES_PATH = REPO / "strategy" / "telemetry_disciplines.py"

    def _tree(self):
        src = self.DISCIPLINES_PATH.read_text(encoding="utf-8")
        return ast.parse(src)

    def test_ac9_no_pyqt6_import(self):
        for node in ast.walk(self._tree()):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                names = [a.name for a in getattr(node, "names", [])]
                mod = getattr(node, "module", "") or ""
                assert "PyQt6" not in mod, "PyQt6 module import found"
                assert not any("PyQt6" in n for n in names), "PyQt6 import found"

    def test_ac9_no_sqlite3_import(self):
        for node in ast.walk(self._tree()):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                names = [a.name for a in getattr(node, "names", [])]
                mod = getattr(node, "module", "") or ""
                assert "sqlite3" not in mod
                assert not any("sqlite3" in n for n in names)

    def test_ac9_no_open_builtin_call(self):
        for node in ast.walk(self._tree()):
            if isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Name) and func.id == "open":
                    raise AssertionError("open() call found — violates purity contract")

    def test_ac9_no_config_strategy_access(self):
        """telemetry_disciplines must never read config["strategy"]."""
        src = self.DISCIPLINES_PATH.read_text(encoding="utf-8")
        assert 'config["strategy"]' not in src
        assert "config.get(\"strategy\"" not in src

    def test_ac9_telemetry_disciplines_adds_no_new_consumer(self):
        """AC9 real intent: telemetry_disciplines must not have added a NEW
        config['strategy'] consumer.

        The original test also asserted the frozen allowlist was byte-for-byte
        unchanged. After the determinism rebuild removed the generative-AI
        methods (_run_ai_analysis, _build_combined_prompt, _build_setup_prompt,
        _get_track_intelligence_context, ...), several allowlisted sites no
        longer exist. That bookkeeping belongs to test_legacy_fanout_phase_5's
        own frozen-list test, not to this OFR-2 purity check — so here we only
        assert the OFR-2 guarantee: no NEW consumer was introduced."""
        from tests.test_legacy_fanout_phase_5 import _scan_inventory, FROZEN_ALLOWLIST
        found = _scan_inventory()
        new = {k: v for k, v in found.items()
               if k not in FROZEN_ALLOWLIST or v > FROZEN_ALLOWLIST[k]}
        assert not new, (
            f"NEW config['strategy'] consumers introduced: {new}"
        )
        # telemetry_disciplines itself must never appear as a consumer.
        assert not any("telemetry_disciplines" in path for (path, _fn) in found), (
            "telemetry_disciplines must not read config['strategy']"
        )


# ===========================================================================
# AC10 — OFR-1 blocks untouched (recommendation_scoring + driving_advisor)
# ===========================================================================

class TestAC10OFR1Untouched:
    """AC10: OFR-1 scored-recommendations block and recommendation_scoring.py untouched."""

    def test_ac10_telemetry_disciplines_not_imported_in_recommendation_scoring(self):
        src = (REPO / "data" / "recommendation_scoring.py").read_text(encoding="utf-8")
        assert "telemetry_disciplines" not in src, (
            "data/recommendation_scoring.py must not import telemetry_disciplines"
        )

    def test_ac10_telemetry_disciplines_not_imported_in_driving_advisor(self):
        src = (REPO / "strategy" / "driving_advisor.py").read_text(encoding="utf-8")
        assert "telemetry_disciplines" not in src, (
            "strategy/driving_advisor.py must not import telemetry_disciplines"
        )

    def test_ac10_format_performance_block_still_present_in_driving_advisor(self):
        """_get_previous_ai_context must still reference format_performance_block
        (OFR-1's §6.4 scored-recommendations block unchanged)."""
        src = (REPO / "strategy" / "driving_advisor.py").read_text(encoding="utf-8")
        assert "format_performance_block" in src, (
            "_get_previous_ai_context must still use format_performance_block (OFR-1 path)"
        )

    def test_ac10_get_previous_ai_context_body_has_scored_recs_call(self):
        """_get_previous_ai_context still calls get_scored_recs_for_prompt."""
        src = (REPO / "strategy" / "driving_advisor.py").read_text(encoding="utf-8")
        assert "get_scored_recs_for_prompt" in src, (
            "_get_previous_ai_context must still call get_scored_recs_for_prompt (OFR-1 AC)"
        )

    def test_ac10_recommendation_scoring_module_importable(self):
        """recommendation_scoring.py must remain importable without error and
        still export its core public functions."""
        import importlib
        mod = importlib.import_module("data.recommendation_scoring")
        assert hasattr(mod, "format_performance_block"), (
            "format_performance_block must still exist in recommendation_scoring"
        )
        assert hasattr(mod, "compute_verdict_and_confidence"), (
            "compute_verdict_and_confidence must still exist in recommendation_scoring"
        )

    def test_ac10_recommendation_scoring_hash_unchanged(self):
        """Byte-hash guard for recommendation_scoring.py (OFR-1 non-collision)."""
        import hashlib
        path = REPO / "data" / "recommendation_scoring.py"
        data = path.read_bytes()
        actual = hashlib.sha256(data).hexdigest()[:16]
        EXPECTED = "0fbd7d07c0dfc23c"
        assert actual == EXPECTED, (
            f"data/recommendation_scoring.py byte-hash changed (OFR-1 non-collision). "
            f"Expected {EXPECTED!r}, got {actual!r}"
        )


# ===========================================================================
# Edge cases — pure builder behaviour
# ===========================================================================

class TestEdgeCaseZeroCleanLaps:
    """Edge: zero clean laps → honest line in both disciplines."""

    def test_edge_zero_clean_laps_qualifying_honesty_line(self):
        from strategy.telemetry_disciplines import build_discipline_telemetry_block as bdt
        block = bdt([], "Qualifying")
        assert block is not None
        assert "No clean laps available" in block

    def test_edge_zero_clean_laps_race_honesty_line(self):
        from strategy.telemetry_disciplines import build_discipline_telemetry_block as bdt
        block = bdt([], "Race")
        assert block is not None
        assert "No clean laps available" in block


class TestEdgeCasePartialTyreTemps:
    """Edge: partial tyre temps (some non-zero, some zero) → renders what exists."""

    def test_edge_fl_only_renders_fl_not_not_recorded(self):
        from strategy.telemetry_disciplines import build_discipline_telemetry_block as bdt
        rows = _laps(2)
        for r in rows:
            r["tyre_temp_fl_avg"] = 75.0
            r["tyre_temp_fr_avg"] = 0.0
            r["tyre_temp_rl_avg"] = 0.0
            r["tyre_temp_rr_avg"] = 0.0
        block = bdt(rows, "Race")
        assert "— not recorded" not in block
        assert "75" in block

    def test_edge_rr_only_renders_rr_not_not_recorded(self):
        from strategy.telemetry_disciplines import build_discipline_telemetry_block as bdt
        rows = _laps(2)
        for r in rows:
            r["tyre_temp_fl_avg"] = 0.0
            r["tyre_temp_fr_avg"] = 0.0
            r["tyre_temp_rl_avg"] = 0.0
            r["tyre_temp_rr_avg"] = 88.0
        block = bdt(rows, "Race")
        assert "— not recorded" not in block
        assert "88" in block


class TestEdgeCaseNormalisePurposeRouting:
    """Edge: purpose only via normalise_purpose — handles all input types."""

    def test_edge_race_setup_string_routes_to_race(self):
        from strategy.telemetry_disciplines import build_discipline_telemetry_block as bdt
        block = bdt(_laps(2), "Race Setup")
        assert block is not None
        assert "RACE" in block

    def test_edge_qualifying_setup_string_routes_to_qualifying(self):
        from strategy.telemetry_disciplines import build_discipline_telemetry_block as bdt
        block = bdt(_laps(2), "Qualifying Setup")
        assert block is not None
        assert "QUALIFYING" in block

    def test_edge_enum_qualifying_routes_to_qualifying_block(self):
        from data.setup_context import SetupPurpose
        from strategy.telemetry_disciplines import build_discipline_telemetry_block as bdt
        block = bdt(_laps(2), SetupPurpose.QUALIFYING)
        assert block is not None
        assert "QUALIFYING" in block

    def test_edge_enum_unknown_returns_none(self):
        from data.setup_context import SetupPurpose
        from strategy.telemetry_disciplines import build_discipline_telemetry_block as bdt
        assert bdt(_laps(2), SetupPurpose.UNKNOWN) is None

    def test_edge_none_returns_none(self):
        from strategy.telemetry_disciplines import build_discipline_telemetry_block as bdt
        assert bdt(_laps(2), None) is None


class TestEdgeCaseOneLapStdDev:
    """Edge: 1-lap std-dev → 'N/A (1 lap)'."""

    def test_edge_one_clean_lap_race_block_gives_n_a(self):
        from strategy.telemetry_disciplines import build_discipline_telemetry_block as bdt
        block = bdt(_laps(1), "Race")
        assert "N/A (1 lap)" in block


class TestEdgeCaseRF2Wiring:
    """Edge: RF2 wiring — _resolve_recent_laps is on the UI thread; defensive empty."""

    def test_edge_resolve_recent_laps_method_exists_in_source(self):
        src = (REPO / "ui" / "setup_builder_ui.py").read_text(encoding="utf-8")
        assert "_resolve_recent_laps" in src, (
            "_resolve_recent_laps helper must exist in setup_builder_ui.py"
        )

    def test_edge_resolve_recent_laps_returns_empty_list_on_no_db(self):
        """When _db is None the helper must return [] defensively."""
        from ui import setup_builder_ui as _sbu_mod

        stub = MagicMock()
        stub._db = None
        stub._resolve_recent_laps = types.MethodType(
            _sbu_mod.SetupBuilderMixin._resolve_recent_laps, stub
        )
        result = stub._resolve_recent_laps(7, "Suzuka")
        assert result == []

    def test_edge_resolve_recent_laps_returns_empty_list_on_zero_car_id(self):
        from ui import setup_builder_ui as _sbu_mod

        stub = MagicMock()
        stub._db = MagicMock()
        stub._resolve_recent_laps = types.MethodType(
            _sbu_mod.SetupBuilderMixin._resolve_recent_laps, stub
        )
        result = stub._resolve_recent_laps(0, "Suzuka")
        assert result == []
        stub._db.get_previous_session_id.assert_not_called()

    def test_edge_resolve_recent_laps_happy_path_returns_laps(self):
        from ui import setup_builder_ui as _sbu_mod

        fake_laps = [{"lap_num": 1, "lap_time_ms": 90_000}]
        stub = MagicMock()
        stub._db = MagicMock()
        stub._db.get_previous_session_id.return_value = 42
        stub._db.get_session_laps.return_value = fake_laps
        stub._resolve_recent_laps = types.MethodType(
            _sbu_mod.SetupBuilderMixin._resolve_recent_laps, stub
        )
        result = stub._resolve_recent_laps(7, "Suzuka")
        assert result == fake_laps
