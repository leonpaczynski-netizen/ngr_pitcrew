"""SessionContext real connection signal — the promised one-place fix.

The SessionContext sprint documented that ``connected`` reproduced a tracker
attribute that never existed (always False) and that "a real connection signal
can later be wired into SessionContext in one place". This sprint delivers it:

  * ``MainWindow`` gains ``udp_listener`` (duck-typed: ``.connected`` /
    ``.total_received`` / ``.parse_errors`` / ``.packet_rate``), passed by
    ``main()`` — the ``UDPListener`` owns the true packet-timeout-based state;
  * ``_build_session_context`` sources ``connected`` + ``packet_count`` from
    the listener when wired → Home's ``live_active``, the telemetry-context
    labels, and the flow gates become REAL. Without a listener the legacy
    tracker fallbacks apply (byte-identical: those attrs never existed →
    False/0, the old behaviour — pinned);
  * ``_update_telemetry_labels`` (diagnostics panel) reads the listener's four
    stats — that panel was frozen at "Disconnected / 0 / — Hz" because it read
    four phantom tracker attributes.

Behavioural tests bind the REAL methods to widget-free stubs (types.MethodType,
the house pattern); the listener is a plain namespace — no sockets, no Qt.
"""
from __future__ import annotations

import re
import types
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def dash_src():
    return (ROOT / "ui" / "dashboard.py").read_text(encoding="utf-8")


def _method_body(src: str, name: str) -> str:
    m = re.search(rf"\n    def {name}\(.*?(?=\n    def |\n(?:class |# ---)|\Z)",
                  src, re.DOTALL)
    assert m, f"method {name} not found"
    return m.group(0)


def _make_stub(listener=None, tracker=None):
    """Widget-free stub carrying the real _build_session_context."""
    from ui import dashboard as _dash_mod
    stub = MagicMock()
    stub._udp_listener = listener
    stub._tracker = tracker
    stub._config = {"strategy": {"fuel_burn_per_lap": 2.0}, "live": {"mode": "Race"}}
    stub._active_session_id = None
    stub._loaded_session_avg_fuel = 0.0
    stub._build_session_context = types.MethodType(
        _dash_mod.MainWindow._build_session_context, stub)
    return stub


def _fake_listener(connected=True, total=123, errors=2, rate=59.9):
    return SimpleNamespace(connected=connected, total_received=total,
                           parse_errors=errors, packet_rate=rate)


# --------------------------------------------------------------------------- #
# 1. Real listener → real SessionContext
# --------------------------------------------------------------------------- #
class TestListenerWired:
    def test_connected_listener_makes_session_live(self):
        ctx = _make_stub(listener=_fake_listener(connected=True))._build_session_context()
        assert ctx.connected is True
        assert ctx.live_active is True
        assert ctx.connection_text() == "Connected"

    def test_packet_count_from_listener_total(self):
        ctx = _make_stub(listener=_fake_listener(total=123))._build_session_context()
        assert ctx.packet_count == 123

    def test_disconnected_listener(self):
        ctx = _make_stub(listener=_fake_listener(connected=False, total=0))._build_session_context()
        assert ctx.connected is False
        assert ctx.live_active is False

    def test_listener_beats_tracker(self):
        # With a listener wired, tracker attrs are irrelevant.
        tracker = SimpleNamespace(_connected=False, _packet_count=0,
                                  laps_recorded=0, avg_fuel_per_lap=0.0)
        ctx = _make_stub(listener=_fake_listener(connected=True, total=7),
                         tracker=tracker)._build_session_context()
        assert ctx.connected is True
        assert ctx.packet_count == 7

    def test_flow_flags_carry_real_live_state(self):
        from data.session_context import flow_flags
        ctx = _make_stub(listener=_fake_listener(connected=True))._build_session_context()
        assert flow_flags(ctx)["live_active"] is True


# --------------------------------------------------------------------------- #
# 2. No listener → legacy fallback preserved (byte-identical old behaviour)
# --------------------------------------------------------------------------- #
class TestLegacyFallback:
    def test_no_listener_no_tracker_is_offline(self):
        ctx = _make_stub(listener=None, tracker=None)._build_session_context()
        assert ctx.connected is False
        assert ctx.packet_count == 0

    def test_no_listener_with_tracker_still_false(self):
        # The tracker never carried _connected/_packet_count — the fallback
        # reproduces the old always-False/0 result exactly.
        tracker = SimpleNamespace(laps_recorded=3, avg_fuel_per_lap=2.4)
        ctx = _make_stub(listener=None, tracker=tracker)._build_session_context()
        assert ctx.connected is False
        assert ctx.packet_count == 0
        assert ctx.laps_recorded == 3          # real tracker fields still flow

    def test_missing_attr_listener_is_safe(self):
        # Duck-typing guard: a listener without the expected attrs degrades
        # to disconnected/0 rather than raising.
        ctx = _make_stub(listener=SimpleNamespace())._build_session_context()
        assert ctx.connected is False
        assert ctx.packet_count == 0


# --------------------------------------------------------------------------- #
# 3. Diagnostics panel reads the listener's four stats
# --------------------------------------------------------------------------- #
class TestTelemetryLabels:
    def _run_labels(self, listener):
        from ui import dashboard as _dash_mod
        stub = MagicMock()
        stub._udp_listener = listener
        stub._tracker = None
        stub._last_packet = None
        stub._update_telemetry_labels = types.MethodType(
            _dash_mod.MainWindow._update_telemetry_labels, stub)
        stub._update_telemetry_labels()
        return stub

    def test_connected_listener_lights_the_panel(self):
        stub = self._run_labels(_fake_listener(connected=True, total=500,
                                               errors=3, rate=59.9))
        stub._telem_lbl_connection.setText.assert_any_call("Connected")
        stub._telem_lbl_pkt_total_t.setText.assert_any_call("500")
        stub._telem_lbl_pkt_errors_t.setText.assert_any_call("3")
        stub._telem_lbl_pkt_rate_t.setText.assert_any_call("59.9 Hz")

    def test_no_listener_panel_matches_old_frozen_state(self):
        stub = self._run_labels(None)
        stub._telem_lbl_connection.setText.assert_any_call("Disconnected")
        stub._telem_lbl_pkt_total_t.setText.assert_any_call("0")
        stub._telem_lbl_pkt_rate_t.setText.assert_any_call("— Hz")


# --------------------------------------------------------------------------- #
# 4. Wiring source-scans
# --------------------------------------------------------------------------- #
class TestWiring:
    def test_ctor_accepts_and_stores_listener(self, dash_src):
        assert "udp_listener=None," in dash_src
        assert "self._udp_listener    = udp_listener" in dash_src

    def test_main_passes_listener(self):
        main_src = (ROOT / "main.py").read_text(encoding="utf-8")
        assert "udp_listener=listener," in main_src

    def test_session_context_builder_prefers_listener_with_fallback(self, dash_src):
        body = _method_body(dash_src, "_build_session_context")
        assert 'getattr(listener, "connected", False)' in body
        assert 'getattr(listener, "total_received", 0)' in body
        # Legacy fallbacks retained (byte-identical when no listener).
        assert 'getattr(tracker, "_connected", False)' in body
        assert 'getattr(tracker, "_packet_count", 0)' in body

    def test_telemetry_labels_read_listener_stats(self, dash_src):
        body = _method_body(dash_src, "_update_telemetry_labels")
        for frag in ('"connected"', '"total_received"', '"parse_errors"',
                     '"packet_rate"'):
            assert frag in body, f"diagnostics panel missing listener stat {frag}"

    def test_listener_property_contract_holds(self):
        # The duck-typed contract the dashboard relies on, pinned against the
        # real class (no socket started).
        from telemetry.listener import UDPListener
        for attr in ("connected", "total_received", "parse_errors", "packet_rate"):
            assert isinstance(getattr(UDPListener, attr), property)


# --------------------------------------------------------------------------- #
# 5. Sprint invariants unchanged
# --------------------------------------------------------------------------- #
class TestInvariantsUnchanged:
    def test_no_new_config_strategy_consumers(self):
        # The frozen allowlist (Phase 5) still matches exactly.
        from tests.test_legacy_fanout_phase_5 import _scan_inventory, FROZEN_ALLOWLIST
        assert _scan_inventory() == FROZEN_ALLOWLIST

    def test_tab_order_home_first(self):
        from ui import tab_registry as tr
        assert tr.DEFAULT_TAB_ORDER[0] == tr.TAB_HOME

    def test_config_safety_guardrail_still_active(self):
        import config_paths as cp
        assert cp.real_config_access_blocked(str(cp.REAL_CONFIG_PATH)) is True
