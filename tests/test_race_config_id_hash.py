"""Legacy Fan-Out Removal Phase 6b — race config_id hash byte-stability proof.

Retirement-map item 2 (docs/LEGACY_FANOUT_PHASE_5.md §4). `_compute_race_config_id`
derives the 10-char session-match-key every lap-bank entry, setup-history entry,
and DB session row is keyed by. Silently changing its algorithm or inputs would
re-key ALL of that history. This suite freezes it:

  1. **Golden vectors** — literal (inputs → id) pairs computed from the shipped
     algorithm. Any change to the raw-string format, the hash, the truncation,
     or the defaults fails these.
  2. **Source-level pin** — the function body's algorithm-critical fragments.
  3. **EventContext equivalence + the restore-divergence proof** — why the hash
     inputs CANNOT migrate to DB-first EventContext yet: `_load_session_config`
     deliberately restores a HISTORICAL session's track/params into the working
     config (without changing the active event) so the id follows the restored
     session. EventContext.track is DB-first and would pin the id to the active
     event, breaking the lap-bank restore. (`car` alone is always-safe —
     strategy-first — but hash inputs move together, with retirement-map items
     3/4.)

The REAL method is exercised via types.MethodType on a widget-free stub.
"""
from __future__ import annotations

import hashlib
import re
import types
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from data.event_context import build_event_context

ROOT = Path(__file__).resolve().parents[1]


def _bind(strategy: dict):
    from ui import dashboard as _dash_mod
    stub = MagicMock()
    stub._config = {"strategy": strategy}
    stub._compute_race_config_id = types.MethodType(
        _dash_mod.MainWindow._compute_race_config_id, stub)
    return stub


# --------------------------------------------------------------------------- #
# 1. Golden vectors — frozen 2026-07-04 from the shipped algorithm
# --------------------------------------------------------------------------- #
# (strategy-dict fields → expected id). DO NOT regenerate these on failure —
# a mismatch means history re-keying; the CODE must be fixed, not the vectors.
GOLDEN_VECTORS = [
    # raw '||l25' — the empty/default working config (a real id seen in the
    # field: it appeared in the restored user config on 2026-07-03).
    ({}, "05e6d2f288"),
    ({"track": "Spa", "car": "Porsche 963", "race_type": "lap",
      "total_laps": 12}, "51bd5b3bae"),                       # 'Spa|Porsche 963|l12'
    ({"track": "Spa", "car": "Porsche 963", "race_type": "timed",
      "race_duration_minutes": 30}, "ab4f42df9a"),            # 'Spa|Porsche 963|t30'
    ({"track": "Deep Forest Raceway", "car": "Mazda 787B",
      "race_type": "lap", "total_laps": 25}, "5642180116"),   # '...|l25'
    ({"track": "Suzuka Circuit", "car": "Toyota GR010 HYBRID",
      "race_type": "timed", "race_duration_minutes": 60}, "cb8879ec47"),
]


class TestGoldenVectors:
    @pytest.mark.parametrize("strategy,expected", GOLDEN_VECTORS)
    def test_real_method_matches_golden(self, strategy, expected):
        assert _bind(strategy)._compute_race_config_id() == expected

    def test_default_config_values_hash_to_empty_vector(self):
        # A freshly-loaded config (DEFAULT_CONFIG merged) has track="", no car,
        # total_laps=25 → the '||l25' id.
        from config_paths import DEFAULT_CONFIG
        assert _bind(dict(DEFAULT_CONFIG["strategy"]))._compute_race_config_id() \
            == "05e6d2f288"

    def test_shape_and_stability(self):
        a = _bind({"track": "Spa", "car": "X"})._compute_race_config_id()
        b = _bind({"track": "Spa", "car": "X"})._compute_race_config_id()
        assert a == b
        assert len(a) == 10 and re.fullmatch(r"[0-9a-f]{10}", a)

    def test_sensitivity_each_input_changes_the_id(self):
        base = {"track": "Spa", "car": "X", "race_type": "lap", "total_laps": 10}
        base_id = _bind(base)._compute_race_config_id()
        for mut in ({"track": "Monza"}, {"car": "Y"},
                    {"race_type": "timed", "race_duration_minutes": 10},
                    {"total_laps": 11}):
            assert _bind({**base, **mut})._compute_race_config_id() != base_id

    def test_defaults_25_laps_and_60_minutes(self):
        # Absent length keys fall back to l25 / t60 (the algorithm's own
        # defaults, distinct from EventContext's 0 defaults).
        lap = _bind({"track": "T", "car": "C"})._compute_race_config_id()
        lap_explicit = _bind({"track": "T", "car": "C",
                              "total_laps": 25})._compute_race_config_id()
        assert lap == lap_explicit
        timed = _bind({"track": "T", "car": "C",
                       "race_type": "timed"})._compute_race_config_id()
        timed_explicit = _bind({"track": "T", "car": "C", "race_type": "timed",
                                "race_duration_minutes": 60})._compute_race_config_id()
        assert timed == timed_explicit
        assert lap != timed

    def test_unknown_race_type_treated_as_lap(self):
        weird = _bind({"track": "T", "car": "C",
                       "race_type": "endurance"})._compute_race_config_id()
        lap = _bind({"track": "T", "car": "C",
                     "race_type": "lap"})._compute_race_config_id()
        assert weird == lap


# --------------------------------------------------------------------------- #
# 2. Source-level algorithm pin
# --------------------------------------------------------------------------- #
class TestAlgorithmPinnedInSource:
    def test_algorithm_fragments_unchanged(self):
        src = (ROOT / "ui" / "dashboard.py").read_text(encoding="utf-8")
        m = re.search(r"\n    def _compute_race_config_id\(.*?(?=\n    def )",
                      src, re.DOTALL)
        assert m, "_compute_race_config_id not found"
        body = m.group(0)
        # The raw-string format, hash, truncation, and defaults are the key —
        # any of these changing re-keys all history.
        assert 'raw = f"{track}|{car}|{length_key}"' in body
        assert "hashlib.sha256(raw.encode()).hexdigest()[:10]" in body
        assert "f\"t{int(sc.get('race_duration_minutes', 60))}\"" in body
        assert "f\"l{int(sc.get('total_laps', 25))}\"" in body
        # Inputs remain the WORKING config (see the divergence proof below).
        assert 'sc        = self._config.get("strategy", {})' in body


# --------------------------------------------------------------------------- #
# 3. EventContext equivalence — and why migration is deferred
# --------------------------------------------------------------------------- #
def _raw_from_context(ev_ctx, *, laps_default=25, dur_default=60):
    """The raw hash string a hypothetical EventContext-sourced hash would use
    (preserving the algorithm's own 25/60 defaults for unset lengths)."""
    if ev_ctx.race_type == "timed":
        length_key = f"t{int(ev_ctx.race_duration_minutes or dur_default)}"
    else:
        length_key = f"l{int(ev_ctx.laps or laps_default)}"
    return f"{ev_ctx.track}|{ev_ctx.car}|{length_key}"


class TestEventContextEquivalence:
    def test_in_sync_active_event_would_hash_identically(self):
        # Right after "Set as Active" (and always, since Phase 4's re-sync) the
        # working config mirrors the DB event → identical raw string.
        event = {"id": 1, "name": "E", "track": "Spa",
                 "race_type": "Lap Race", "laps": 12}
        strategy = {"track": "Spa", "car": "Porsche 963",
                    "race_type": "lap", "total_laps": 12}
        ev_ctx = build_event_context(event=event, strategy=strategy)
        legacy_raw = "Spa|Porsche 963|l12"
        assert _raw_from_context(ev_ctx) == legacy_raw
        assert hashlib.sha256(legacy_raw.encode()).hexdigest()[:10] == "51bd5b3bae"

    def test_restore_divergence_blocks_migration(self):
        # THE reason the hash inputs stay on the working config:
        # _load_session_config restores a historical session's track/params
        # into config["strategy"] WITHOUT changing the active event, then
        # recomputes the id — the id must follow the RESTORED session.
        event = {"id": 1, "name": "Active", "track": "Spa",
                 "race_type": "Lap Race", "laps": 12}          # active event
        strategy = {"track": "Deep Forest Raceway", "car": "Mazda 787B",
                    "race_type": "lap", "total_laps": 25}      # restored session
        # The shipped hash follows the restored working config:
        assert _bind(strategy)._compute_race_config_id() == "5642180116"
        # An EventContext-sourced hash would pin to the ACTIVE event instead —
        # a different id → the lap-bank restore feature would break:
        ev_ctx = build_event_context(event=event, strategy=strategy)
        assert ev_ctx.track == "Spa"                           # DB-first
        assert _raw_from_context(ev_ctx) != "Deep Forest Raceway|Mazda 787B|l25"

    def test_car_alone_is_always_safe(self):
        # car resolves strategy-first in EventContext (events never store one),
        # so it matches the working config even in the restore case — but hash
        # inputs move together (retirement-map items 3/4), not piecemeal.
        event = {"id": 1, "name": "Active", "track": "Spa"}
        strategy = {"track": "Deep Forest Raceway", "car": "Mazda 787B"}
        ev_ctx = build_event_context(event=event, strategy=strategy)
        assert ev_ctx.car == strategy["car"]


# --------------------------------------------------------------------------- #
# 4. Sprint invariants unchanged
# --------------------------------------------------------------------------- #
class TestInvariantsUnchanged:
    def test_frozen_allowlist_still_exact(self):
        # No reads were migrated this sprint — the allowlist must be untouched.
        from tests.test_legacy_fanout_phase_5 import _scan_inventory, FROZEN_ALLOWLIST
        assert _scan_inventory() == FROZEN_ALLOWLIST

    def test_tab_order_home_first(self):
        from ui import tab_registry as tr
        assert tr.DEFAULT_TAB_ORDER[0] == tr.TAB_HOME

    def test_config_safety_guardrail_still_active(self):
        import config_paths as cp
        assert cp.real_config_access_blocked(str(cp.REAL_CONFIG_PATH)) is True
