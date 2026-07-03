"""SessionContext / TelemetryContext sprint — canonical live-session read model.

Pure-Python unit tests for data/session_context.py (byte-identity with the
expressions it replaces, ownership boundary, garbage safety) + source-scans that
ui/dashboard.py's telemetry/session consumers now read the context instead of
reaching into tracker internals / the legacy config fuel fallback.

Follows the project's no-Qt convention. Every migrated read is behaviour-
preserving; this file proves it.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from data import session_context as sc
from data.session_context import (
    build_session_context,
    empty_session_context,
    flow_flags,
    SessionContextSource,
    SessionFuelSource,
)

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def dash_src():
    return (ROOT / "ui" / "dashboard.py").read_text(encoding="utf-8")


def _method_body(src: str, name: str) -> str:
    m = re.search(rf"\n    def {name}\(.*?(?=\n    def |\n(?:class |# ---)|\Z)",
                  src, re.DOTALL)
    assert m, f"method {name} not found"
    return m.group(0)


# --------------------------------------------------------------------------- #
# 1. Fuel-burn 3-tier fallback — byte-identical to _computed_fuel_burn_lpl
# --------------------------------------------------------------------------- #
def _legacy_computed_fuel(loaded, tracker_avg, cfg_fallback):
    """Verbatim of the pre-migration _computed_fuel_burn_lpl logic."""
    if loaded > 0:
        return float(loaded)
    if tracker_avg and tracker_avg > 0:
        return float(tracker_avg)
    return float(cfg_fallback)


class TestFuelBurnByteIdentical:
    @pytest.mark.parametrize("loaded,avg,cfg", [
        (0.0, 0.0, 2.0),      # nothing → config fallback
        (0.0, 0.0, 1.75),     # config fallback custom
        (0.0, 2.7, 2.0),      # telemetry average
        (3.1, 2.2, 2.5),      # loaded session wins over telemetry
        (5.0, 0.0, 2.0),      # loaded only
        (0.0, 0.01, 2.0),     # tiny telemetry still > 0
    ])
    def test_matches_legacy(self, loaded, avg, cfg):
        ctx = build_session_context(
            loaded_session_avg_fuel=loaded,
            telemetry_avg_fuel_per_lap=avg,
            config_fuel_burn_per_lap=cfg,
        )
        assert ctx.fuel_burn_per_lap == _legacy_computed_fuel(loaded, avg, cfg)

    def test_source_classification(self):
        assert build_session_context(loaded_session_avg_fuel=4.0).fuel_burn_source \
            == SessionFuelSource.LOADED_SESSION
        assert build_session_context(telemetry_avg_fuel_per_lap=3.0).fuel_burn_source \
            == SessionFuelSource.TELEMETRY
        assert build_session_context().fuel_burn_source \
            == SessionFuelSource.CONFIG_FALLBACK

    def test_default_config_fallback_is_2(self):
        assert build_session_context().fuel_burn_per_lap == 2.0


# --------------------------------------------------------------------------- #
# 2. Connection / recording / live semantics
# --------------------------------------------------------------------------- #
class TestSessionSemantics:
    def test_connected_drives_live_active_and_text(self):
        c = build_session_context(connected=True)
        assert c.live_active is True
        assert c.connection_text() == "Connected"
        d = build_session_context(connected=False)
        assert d.live_active is False
        assert d.connection_text() == "Disconnected"

    def test_recording_from_active_session_id(self):
        assert build_session_context(active_session_id=7).is_recording is True
        assert build_session_context(active_session_id=0).is_recording is True  # 0 is a real id
        assert build_session_context(active_session_id=None).is_recording is False
        assert build_session_context(active_session_id=7).recording_text() == "Yes"
        assert build_session_context(active_session_id=None).recording_text() == "No"

    def test_packet_and_lap_counts_coerced(self):
        c = build_session_context(packet_count="12", laps_recorded=3.0)
        assert c.packet_count == 12
        assert c.laps_recorded == 3

    def test_live_mode_default(self):
        assert build_session_context().live_mode == "Race"
        assert build_session_context(live_mode="Qualifying").live_mode == "Qualifying"
        assert build_session_context(live_mode=None).live_mode == "Race"

    def test_source_empty_vs_live(self):
        assert empty_session_context().source == SessionContextSource.EMPTY
        assert empty_session_context().is_live is False
        for kw in ({"connected": True}, {"packet_count": 1},
                   {"laps_recorded": 1}, {"active_session_id": 3}):
            assert build_session_context(**kw).source == SessionContextSource.LIVE


# --------------------------------------------------------------------------- #
# 3. Robustness / ownership boundary
# --------------------------------------------------------------------------- #
class TestRobustnessAndBoundary:
    def test_never_raises_on_garbage(self):
        c = build_session_context(
            packet_count="x", laps_recorded=None,
            telemetry_avg_fuel_per_lap="nope", loaded_session_avg_fuel="",
            config_fuel_burn_per_lap="bad", active_session_id="7",
        )
        assert c.packet_count == 0
        assert c.laps_recorded == 0
        assert c.fuel_burn_per_lap == 2.0            # bad config → 2.0 default
        assert c.active_session_id == 7

    def test_ownership_boundary_no_foreign_fields(self):
        # SessionContext owns telemetry/session truth ONLY — no event/strategy/
        # setup/track fields leak in.
        fields = set(build_session_context().to_dict().keys())
        for foreign in ("car", "track", "config_id", "stint_plan",
                        "setup_label", "layout_id", "tyre_wear_multiplier"):
            assert foreign not in fields

    def test_flow_flags_bridge(self):
        c = build_session_context(connected=True, has_practice_laps=True,
                                  has_valid_laps=False)
        assert flow_flags(c) == {
            "has_practice_laps": True,
            "has_valid_laps": False,
            "live_active": True,
        }

    def test_to_dict_serialisable(self):
        d = build_session_context(connected=True, active_session_id=2).to_dict()
        assert d["schema"] == sc.SESSION_CONTEXT_SCHEMA
        assert d["source"] == "live"
        assert d["fuel_burn_source"] == "config_fallback"

    def test_module_is_pure(self):
        src = (ROOT / "data" / "session_context.py").read_text(encoding="utf-8")
        assert not re.search(r"^\s*(import PyQt6|from PyQt6)", src, re.M)
        assert "import sqlite3" not in src


# --------------------------------------------------------------------------- #
# 4. Dashboard consumers migrated to the context (source-scan)
# --------------------------------------------------------------------------- #
class TestMigratedConsumers:
    def test_builder_helper_exists_and_reads_tracker_safely(self, dash_src):
        body = _method_body(dash_src, "_build_session_context")
        assert "build_session_context(" in body
        assert 'getattr(tracker, "_connected", False)' in body
        assert 'getattr(tracker, "_packet_count", 0)' in body
        assert 'get("fuel_burn_per_lap", 2.0)' in body   # legacy bridge read
        assert 'get("mode", "Race")' in body

    def test_computed_fuel_burn_delegates_to_context(self, dash_src):
        body = _method_body(dash_src, "_computed_fuel_burn_lpl")
        assert "self._build_session_context().fuel_burn_per_lap" in body
        # The inline 3-tier logic and direct config read are gone.
        assert "avg_fuel_per_lap" not in body
        assert 'config.get("strategy"' not in body

    def test_home_state_uses_session_context_for_live(self, dash_src):
        body = _method_body(dash_src, "_build_home_dashboard_state")
        assert "self._build_session_context(" in body
        assert "session_ctx.live_active" in body
        assert 'getattr(self._tracker, "_connected"' not in body

    def test_telemetry_context_uses_session_context(self, dash_src):
        body = _method_body(dash_src, "_refresh_telemetry_context")
        assert "self._build_session_context()" in body
        assert "sctx.connection_text()" in body
        assert "sctx.recording_text()" in body
        assert "sctx.packet_count" in body
        assert 'getattr(self._tracker, "_connected"' not in body
        assert 'getattr(self._tracker, "_packet_count"' not in body

    def test_migrated_methods_write_no_config_strategy(self, dash_src):
        for name in ("_build_session_context", "_computed_fuel_burn_lpl",
                     "_refresh_telemetry_context"):
            body = _method_body(dash_src, name)
            assert 'setdefault("strategy"' not in body, f"{name} writes config['strategy']"


# --------------------------------------------------------------------------- #
# 5. Sprint invariants unchanged
# --------------------------------------------------------------------------- #
class TestInvariantsUnchanged:
    def test_tab_order_home_first(self):
        from ui import tab_registry as tr
        assert tr.DEFAULT_TAB_ORDER[0] == tr.TAB_HOME

    def test_config_safety_guardrail_still_active(self):
        import config_paths as cp
        assert cp.real_config_access_blocked(str(cp.REAL_CONFIG_PATH)) is True
