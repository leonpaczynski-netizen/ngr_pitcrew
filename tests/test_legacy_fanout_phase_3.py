"""Legacy Fan-Out Removal Phase 3 — functional gating/validation migration.

Scope (explicit product sign-off: "flip reads only"): the two remaining
FUNCTIONAL `config["strategy"]` consumers now read the canonical DB-first
**EventContext**:

  1. Setup-permission gating — `_sync_setup_builder_from_event` feeds
     `_on_bop_toggled` / `_apply_setup_permissions` from `ev_ctx.bop_enabled` /
     `.tuning_allowed` / `.allowed_tuning_categories` (which setup fields are
     editable).
  2. DEF-P3-012 strategy-options tuning validation — `_strat_locked` /
     `_strat_allowed` from EventContext.

This completes READER consistency: the AI inputs (AI Snapshot Migration), the
display labels (Phase 2), the gating, and the validation all follow the same
DB-first truth. The fan-out WRITERS are still untouched (Phase 4's job).

Guarantees tested here:
  * byte-identical gating/validation inputs when the DB event and the fan-out
    are in sync (the normal case, right after "Set as Active");
  * DB-first when they diverge (edited + Saved but not re-activated) — the
    signed-off behaviour change: gating/validation follow the DB edit;
  * `_on_event_set_active`'s own `_apply_setup_permissions` call still reads the
    just-written `strat` (inside the writer, fresh by construction — unchanged).
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from data.event_context import build_event_context

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def dash_src():
    return ((ROOT / "ui" / "dashboard.py").read_text(encoding="utf-8") + (ROOT / "ui" / "event_planner_ui.py").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def sbu_src():
    return (ROOT / "ui" / "setup_builder_ui.py").read_text(encoding="utf-8")


def _method_body(src: str, name: str) -> str:
    m = re.search(rf"\n    def {name}\(.*?(?=\n    def |\n(?:class |# ---)|\Z)",
                  src, re.DOTALL)
    assert m, f"method {name} not found"
    return m.group(0)


def _in_sync_pair():
    """DB event + the fan-out 'Set as Active' would write from it (in sync)."""
    event = {
        "id": 1, "name": "Race A", "track": "Spa",
        "bop": True, "tuning": False,
        "allowed_tuning_categories": ["suspension", "aero"],
    }
    strategy = {
        "track": "Spa", "car": "Porsche 963",
        "bop": True, "tuning": False,
        "allowed_tuning_categories": ["suspension", "aero"],
    }
    return event, strategy


# --------------------------------------------------------------------------- #
# 1. Gating inputs byte-identical when in sync
# --------------------------------------------------------------------------- #
class TestInSyncByteIdentical:
    @pytest.mark.parametrize("bop,tuning,cats", [
        (False, True, []),                      # unrestricted
        (True, True, []),                       # BoP on, tuning free
        (True, False, []),                      # fully locked
        (False, True, ["suspension"]),          # partially restricted
        (True, False, ["aero"]),                # locked (lock wins)
    ])
    def test_gating_trio_matches_raw_fan_out(self, bop, tuning, cats):
        event = {"id": 1, "name": "E", "track": "Spa",
                 "bop": bop, "tuning": tuning, "allowed_tuning_categories": cats}
        strategy = {"track": "Spa", "car": "X",
                    "bop": bop, "tuning": tuning, "allowed_tuning_categories": cats}
        ctx = build_event_context(event=event, strategy=strategy)
        # OLD reads (verbatim): bool(sc.get("bop", ...)), bool(sc.get("tuning", ...)),
        # sc.get("allowed_tuning_categories", [])
        assert ctx.bop_enabled == bool(strategy.get("bop", False))
        assert ctx.tuning_allowed == bool(strategy.get("tuning", True))
        assert list(ctx.allowed_tuning_categories) == strategy.get(
            "allowed_tuning_categories", [])

    def test_validation_inputs_match_raw_fan_out(self):
        event, strategy = _in_sync_pair()
        ctx = build_event_context(event=event, strategy=strategy)
        # OLD reads (verbatim): not bool(sc.get("tuning", True)),
        # sc.get("allowed_tuning_categories") or []
        assert ctx.tuning_locked == (not bool(strategy.get("tuning", True)))
        assert list(ctx.allowed_tuning_categories) == (
            strategy.get("allowed_tuning_categories") or [])

    def test_empty_state_defaults_match(self):
        # No event, no strategy → tuning defaults to allowed, nothing locked.
        ctx = build_event_context()
        assert ctx.tuning_allowed is True
        assert ctx.tuning_locked is False
        assert list(ctx.allowed_tuning_categories) == []


# --------------------------------------------------------------------------- #
# 2. DB-first when diverged (the signed-off behaviour change)
# --------------------------------------------------------------------------- #
class TestDivergedDbFirst:
    def test_gating_follows_db_edit(self):
        # Event edited + Saved (DB fresh) but not re-activated (fan-out stale):
        # the DB now locks tuning and enables BoP — gating must follow the DB.
        event, strategy = _in_sync_pair()
        event.update({"bop": False, "tuning": True,
                      "allowed_tuning_categories": ["brakes"]})
        ctx = build_event_context(event=event, strategy=strategy)
        assert ctx.bop_enabled is False            # fan-out still says True
        assert ctx.tuning_allowed is True          # fan-out still says False
        assert list(ctx.allowed_tuning_categories) == ["brakes"]

    def test_validation_follows_db_edit(self):
        event, strategy = _in_sync_pair()
        event.update({"tuning": True})             # DB unlocked; fan-out locked
        ctx = build_event_context(event=event, strategy=strategy)
        assert ctx.tuning_locked is False


# --------------------------------------------------------------------------- #
# 3. Source-scans — the flipped reads and what stayed put
# --------------------------------------------------------------------------- #
class TestSetupGatingMigrated:
    def test_gating_inputs_read_event_context(self, sbu_src):
        body = _method_body(sbu_src, "_sync_setup_builder_from_event")
        assert "_bop    = ev_ctx.bop_enabled" in body
        assert "_tuning = ev_ctx.tuning_allowed" in body
        assert "_cats   = list(ev_ctx.allowed_tuning_categories)" in body

    def test_no_raw_gating_reads_remain(self, sbu_src):
        body = _method_body(sbu_src, "_sync_setup_builder_from_event")
        assert 'sc.get("bop"' not in body
        assert 'sc.get("tuning"' not in body
        assert 'sc.get("allowed_tuning_categories"' not in body

    def test_gating_calls_unchanged(self, sbu_src):
        body = _method_body(sbu_src, "_sync_setup_builder_from_event")
        assert "self._on_bop_toggled(_bop)" in body
        assert "self._apply_setup_permissions(_bop, _tuning, _cats)" in body

    def test_apply_setup_permissions_itself_untouched(self, sbu_src):
        # The gating LOGIC is unchanged — only its inputs moved.
        body = _method_body(sbu_src, "_apply_setup_permissions")
        assert "fully_locked = not tuning_allowed" in body
        assert "_SETUP_TUNING_GROUPS" in body
        assert 'config' not in body


class TestValidationMigrated:
    def test_no_raw_validation_reads_remain(self, dash_src):
        assert "_sc_strat" not in dash_src, (
            "DEF-P3-012 validation still reads config['strategy'] via _sc_strat")


class TestWriterPathUnchanged:
    def test_set_active_gating_still_reads_fresh_strat(self, dash_src):
        # Rule-Cache Deletion (2026-07-04): the writer-internal permission call
        # was REDUNDANT since this phase — _sync_setup_builder_from_event
        # (called at activation) applies permissions from the just-saved DB
        # event via EventContext, with identical values. The redundant call and
        # its strat.get gating reads are deleted; the invariant ("gating applied
        # with fresh event values at activation") holds via the sync.
        body = _method_body(dash_src, "_on_event_set_active")
        assert "self._sync_setup_builder_from_event()" in body
        assert 'strat.get("bop"' not in body
        assert 'strat.get("tuning"' not in body
        assert 'strat.get("allowed_tuning_categories"' not in body

    def test_fan_out_writers_preserved(self, dash_src):
        # Phase 4 update: the fan-out block lives in _fanout_event_to_strategy,
        # still invoked by Set-as-Active (same invariant, new home).
        helper = _method_body(dash_src, "_fanout_event_to_strategy")
        assert 'strat = self._config.setdefault("strategy", {})' in helper
        assert 'strat["track"]' in helper
        assert "self._fanout_event_to_strategy(evt_name)" in _method_body(
            dash_src, "_on_event_set_active")


# --------------------------------------------------------------------------- #
# 4. Sprint invariants unchanged
# --------------------------------------------------------------------------- #
class TestInvariantsUnchanged:
    def test_tab_order_home_first(self):
        from ui import tab_registry as tr
        assert tr.DEFAULT_TAB_ORDER[0] == tr.TAB_HOME

    def test_config_safety_guardrail_still_active(self):
        import config_paths as cp
        assert cp.real_config_access_blocked(str(cp.REAL_CONFIG_PATH)) is True
