"""State Consolidation 2 — StrategyContext tests.

Pure unit tests of data/strategy_context.py (no PyQt6, no DB) plus source-scans
of the dashboard helper + migrated consumer. Mirrors tests/test_event_context.py.
"""

from pathlib import Path

import pytest

from data.event_context import build_event_context
from data.strategy_context import (
    STRATEGY_CONTEXT_SCHEMA,
    STRATEGY_PROMPT_SNAPSHOT_SCHEMA,
    StintPlanEntry,
    StrategyContext,
    StrategyContextSource,
    StrategyContextValidationResult,
    StrategyPromptSnapshot,
    build_strategy_context,
    build_strategy_prompt_snapshot,
    empty_strategy_context,
    validate_strategy_context,
    compute_change_hash,
)

ROOT = Path(__file__).parent.parent


@pytest.fixture(scope="module")
def dash_src():
    return (ROOT / "ui" / "dashboard.py").read_text(encoding="utf-8")


# --------------------------------------------------------------------------- #
# Representative fixtures
# --------------------------------------------------------------------------- #
def db_event(**over):
    """A DB events-table record as returned by SessionDB.get_event()."""
    d = {
        "id": 7,
        "name": "NGR Porsche Cup Rd7",
        "track": "Fuji Speedway",
        "race_type": "timed",
        "laps": 25,
        "duration_mins": 50,
        "tyre_wear": 3.0,
        "fuel_mult": 3.0,
        "refuel_rate_lps": 12.0,
        "mandatory_stops": 1,
        "bop": 0,
        "tuning": 1,
        "avail_tyres": ["RH", "RM", "RS"],
        "req_tyres": ["RM"],
        "allowed_tuning_categories": ["suspension", "aero"],
    }
    d.update(over)
    return d


def strategy_dict(**over):
    """A config["strategy"] snapshot (event + strategy fields interleaved)."""
    d = {
        # --- event/race fields (owned by EventContext, ignored by StrategyContext) ---
        "track": "Fuji Speedway",
        "car": "Porsche 911 RSR (991) '17",
        "race_type": "timed",
        "laps": 25,
        "total_laps": 25,
        "race_duration_minutes": 50,
        "tyre_wear_multiplier": 3,
        "fuel_mult": 3,
        "refuel_speed_lps": 12,
        "mandatory_stops": 1,
        "bop": False,
        "tuning": True,
        "allowed_tuning_categories": ["suspension", "aero"],
        "avail_tyres": ["RH", "RM", "RS"],
        "event_id": 7,
        "track_location_id": "fuji_speedway",
        "layout_id": "fuji_speedway__full_course",
        # --- strategy-plan fields (owned by StrategyContext) ---
        "config_id": "a1b2c3d4e5",
        "fuel_burn_per_lap": 2.85,
        "pit_loss_secs": 23.0,
        "lap_time_tolerance_ms": 1500,
        "fuel_tolerance_liters": 0.5,
        "degradation_consecutive_laps": 3,
        "stops": [
            {"laps": 12, "compound": "RM", "ref_lap_ms": 98000, "pace_threshold_ms": 2000},
            {"laps": 13, "compound": "RH", "ref_lap_ms": 99000, "pace_threshold_ms": 2500},
        ],
    }
    d.update(over)
    return d


# --------------------------------------------------------------------------- #
# Build sources
# --------------------------------------------------------------------------- #
class TestBuildSources:
    def test_empty(self):
        ctx = build_strategy_context()
        assert ctx.source == StrategyContextSource.EMPTY
        assert ctx.has_active_strategy is False
        assert ctx.change_hash == ""
        assert empty_strategy_context().source == StrategyContextSource.EMPTY

    def test_legacy_strategy(self):
        ctx = build_strategy_context(strategy=strategy_dict())
        assert ctx.source == StrategyContextSource.LEGACY_STRATEGY
        assert ctx.has_active_strategy

    def test_explicit_source_override(self):
        ctx = build_strategy_context(
            strategy=strategy_dict(), source=StrategyContextSource.GENERATED)
        assert ctx.source == StrategyContextSource.GENERATED


# --------------------------------------------------------------------------- #
# Strategy-plan fields preserved
# --------------------------------------------------------------------------- #
class TestStrategyFieldsPreserved:
    def test_config_id_preserved(self):
        ctx = build_strategy_context(strategy=strategy_dict())
        assert ctx.config_id == "a1b2c3d4e5"

    def test_fuel_burn_preserved(self):
        ctx = build_strategy_context(strategy=strategy_dict())
        assert ctx.fuel_burn_per_lap == 2.85
        assert ctx.has_fuel_burn is True

    def test_stint_plan_parsed(self):
        ctx = build_strategy_context(strategy=strategy_dict())
        assert len(ctx.stint_plan) == 2
        assert all(isinstance(s, StintPlanEntry) for s in ctx.stint_plan)
        assert ctx.stint_plan[0].compound == "RM"
        assert ctx.stint_plan[0].laps == 12
        assert ctx.stint_plan[0].ref_lap_ms == 98000
        assert ctx.stint_plan[0].index == 1
        assert ctx.compound_sequence() == ("RM", "RH")

    def test_planned_stops_derived(self):
        # 2 stints => 1 pit stop between them.
        ctx = build_strategy_context(strategy=strategy_dict())
        assert ctx.planned_stops == 1
        assert ctx.has_plan is True

    def test_pit_laps_derived(self):
        # First stint 12 laps => pit on lap 12; no stop after the final stint.
        ctx = build_strategy_context(strategy=strategy_dict())
        assert ctx.pit_laps == (12,)

    def test_three_stint_plan_two_stops(self):
        s = strategy_dict(stops=[
            {"laps": 10, "compound": "RS"},
            {"laps": 10, "compound": "RM"},
            {"laps": 5, "compound": "RH"},
        ])
        ctx = build_strategy_context(strategy=s)
        assert ctx.planned_stops == 2
        assert ctx.pit_laps == (10, 20)
        assert ctx.total_planned_laps == 25

    def test_degradation_fields(self):
        ctx = build_strategy_context(strategy=strategy_dict(), tyre_degradation={"RM": {}})
        assert ctx.degradation_consecutive_laps == 3
        assert ctx.tyre_degradation_available is True

    def test_degradation_default_consecutive_laps(self):
        s = strategy_dict()
        del s["degradation_consecutive_laps"]
        ctx = build_strategy_context(strategy=s)
        assert ctx.degradation_consecutive_laps == 2  # sensible default

    def test_tolerances_preserved(self):
        ctx = build_strategy_context(strategy=strategy_dict())
        assert ctx.lap_time_tolerance_ms == 1500
        assert ctx.fuel_tolerance_liters == 0.5
        assert ctx.pit_loss_secs == 23.0

    def test_optional_fuel_fields(self):
        ctx = build_strategy_context(strategy=strategy_dict(
            starting_fuel=60.0, fuel_margin=1.5, refuel_required=True))
        assert ctx.starting_fuel == 60.0
        assert ctx.fuel_margin == 1.5
        assert ctx.refuel_required is True

    def test_optional_fuel_fields_absent_stay_none(self):
        ctx = build_strategy_context(strategy=strategy_dict())
        assert ctx.starting_fuel is None
        assert ctx.fuel_margin is None
        assert ctx.refuel_required is None


# --------------------------------------------------------------------------- #
# Ownership boundary — StrategyContext must NOT own event/race config
# --------------------------------------------------------------------------- #
class TestOwnershipBoundary:
    def test_strategy_context_has_no_event_race_fields(self):
        ctx = build_strategy_context(strategy=strategy_dict())
        forbidden = [
            "car", "track", "track_location_id", "layout_id", "race_type",
            "laps", "race_duration_minutes", "tyre_wear_multiplier",
            "fuel_multiplier", "refuel_rate_lps", "bop_enabled", "tuning_allowed",
            "allowed_tuning_categories", "available_tyres", "required_tyres",
        ]
        for name in forbidden:
            assert not hasattr(ctx, name), f"StrategyContext must not own event field {name!r}"

    def test_event_fields_in_strategy_dict_are_ignored(self):
        # Even though the legacy dict carries tyre_wear_multiplier etc., the
        # StrategyContext does not surface them.
        d = build_strategy_context(strategy=strategy_dict()).to_dict()
        assert "tyre_wear_multiplier" not in d
        assert "race_type" not in d
        assert "car" not in d

    def test_event_read_from_event_context_not_strategy(self):
        # The event/race truth is read from EventContext; StrategyContext only
        # records which event it was built against (event_change_hash).
        ev = build_event_context(event=db_event(), strategy=strategy_dict())
        ctx = build_strategy_context(strategy=strategy_dict(), event_context=ev)
        assert ctx.event_change_hash == ev.change_hash
        assert ctx.event_change_hash != ""


# --------------------------------------------------------------------------- #
# Change markers
# --------------------------------------------------------------------------- #
class TestChangeMarkers:
    def test_identical_state_same_hash(self):
        a = build_strategy_context(strategy=strategy_dict())
        b = build_strategy_context(strategy=strategy_dict())
        assert a.change_hash == b.change_hash

    def test_strategy_change_marker_changes_on_plan_edit(self):
        a = build_strategy_context(strategy=strategy_dict())
        b = build_strategy_context(strategy=strategy_dict(
            stops=[{"laps": 25, "compound": "RH"}]))
        assert a.change_hash != b.change_hash, "changed stint plan must change strategy hash"

    def test_strategy_change_marker_changes_on_fuel_burn(self):
        a = build_strategy_context(strategy=strategy_dict(fuel_burn_per_lap=2.85))
        b = build_strategy_context(strategy=strategy_dict(fuel_burn_per_lap=3.10))
        assert a.change_hash != b.change_hash

    def test_strategy_hash_ignores_event_fields(self):
        # Changing a pure event field (tyre_wear_multiplier) in the strategy dict
        # must NOT change the strategy change hash — it is not strategy state.
        a = build_strategy_context(strategy=strategy_dict(tyre_wear_multiplier=3))
        b = build_strategy_context(strategy=strategy_dict(tyre_wear_multiplier=8))
        assert a.change_hash == b.change_hash

    def test_event_change_marker_changes_when_event_context_changes(self):
        ev1 = build_event_context(event=db_event(laps=25), strategy=strategy_dict())
        ev2 = build_event_context(event=db_event(laps=30), strategy=strategy_dict())
        a = build_strategy_context(strategy=strategy_dict(), event_context=ev1)
        b = build_strategy_context(strategy=strategy_dict(), event_context=ev2)
        assert a.event_change_hash != b.event_change_hash
        # ...but the strategy state is identical, so the strategy hash matches.
        assert a.change_hash == b.change_hash

    def test_compute_change_hash_deterministic(self):
        f = {"a": 1, "b": [1, 2], "c": "x"}
        assert compute_change_hash(f) == compute_change_hash(dict(f))
        assert len(compute_change_hash(f)) == 12


# --------------------------------------------------------------------------- #
# Robustness — malformed / missing fields produce no crash
# --------------------------------------------------------------------------- #
class TestRobustness:
    def test_garbage_does_not_crash(self):
        ctx = build_strategy_context(strategy={
            "fuel_burn_per_lap": "abc",
            "config_id": None,
            "stops": "not a list",
            "degradation_consecutive_laps": None,
            "pit_loss_secs": {},
        })
        assert isinstance(ctx, StrategyContext)
        assert ctx.fuel_burn_per_lap == 0.0
        assert ctx.config_id == ""
        assert ctx.stint_plan == ()
        assert ctx.degradation_consecutive_laps == 2

    def test_malformed_stint_entries_skipped(self):
        ctx = build_strategy_context(strategy=strategy_dict(stops=[
            {"laps": 10, "compound": "RS"},
            "garbage",
            123,
            {"laps": "bad", "compound": None},
        ]))
        # Two dict entries survive; the string/int are skipped.
        assert len(ctx.stint_plan) == 2
        assert ctx.stint_plan[1].laps == 0
        assert ctx.stint_plan[1].compound == "Unknown"

    def test_none_strategy_builds_empty(self):
        ctx = build_strategy_context(strategy=None)
        assert ctx.source == StrategyContextSource.EMPTY

    def test_validate_never_raises_on_garbage(self):
        ctx = build_strategy_context(strategy={"stops": None, "fuel_burn_per_lap": "x"})
        res = validate_strategy_context(ctx)
        assert isinstance(res, StrategyContextValidationResult)


# --------------------------------------------------------------------------- #
# Validation — strategy vs event separation
# --------------------------------------------------------------------------- #
class TestValidation:
    def test_empty_context_flagged(self):
        res = validate_strategy_context(empty_strategy_context())
        assert res.ok is False
        assert "strategy" in res.strategy_missing

    def test_missing_plan_warns_as_strategy(self):
        ctx = build_strategy_context(strategy={"fuel_burn_per_lap": 2.8, "config_id": "x"})
        res = validate_strategy_context(ctx)
        assert not res.ok
        assert "stint_plan" in res.strategy_missing
        assert any("stint" in w.lower() for w in res.strategy_warnings)

    def test_missing_fuel_burn_warns_as_strategy(self):
        ctx = build_strategy_context(strategy=strategy_dict(fuel_burn_per_lap=0))
        res = validate_strategy_context(ctx)
        assert "fuel_burn_per_lap" in res.strategy_missing

    def test_fully_specified_strategy_ok_without_event(self):
        ctx = build_strategy_context(strategy=strategy_dict())
        res = validate_strategy_context(ctx)
        assert res.ok, res.strategy_warnings

    def test_event_problems_reported_separately(self):
        # Strategy fully specified, but the event has no car → event warning,
        # not a strategy warning. This is the key separation the sprint requires.
        ev = build_event_context(event=db_event())  # no strategy overlay → no car
        ctx = build_strategy_context(strategy=strategy_dict(), event_context=ev)
        res = validate_strategy_context(ctx, event_context=ev)
        assert "car" in res.event_missing
        assert "car" not in res.strategy_missing
        assert not res.ok  # event problem makes the whole thing not ok
        # strategy side is clean
        assert res.strategy_warnings == ()

    def test_missing_strategy_distinguished_from_missing_event(self):
        # No plan AND no car — each problem lands on its own side.
        ev = build_event_context(event=db_event())
        ctx = build_strategy_context(
            strategy={"config_id": "x"}, event_context=ev)
        res = validate_strategy_context(ctx, event_context=ev)
        assert "stint_plan" in res.strategy_missing
        assert "car" in res.event_missing

    def test_combined_warnings_property(self):
        ev = build_event_context(event=db_event())
        ctx = build_strategy_context(
            strategy={"config_id": "x"}, event_context=ev)
        res = validate_strategy_context(ctx, event_context=ev)
        # warnings property concatenates strategy then event warnings.
        assert set(res.warnings) >= set(res.strategy_warnings)
        assert set(res.warnings) >= set(res.event_warnings)


# --------------------------------------------------------------------------- #
# Frozen prompt snapshot
# --------------------------------------------------------------------------- #
class TestPromptSnapshot:
    def test_snapshot_combines_event_and_strategy(self):
        ev = build_event_context(event=db_event(), strategy=strategy_dict())
        ctx = build_strategy_context(strategy=strategy_dict(), event_context=ev)
        snap = build_strategy_prompt_snapshot(ctx, ev)
        assert isinstance(snap, StrategyPromptSnapshot)
        # event/race config comes from EventContext
        assert snap.track == "Fuji Speedway"
        assert snap.car == "Porsche 911 RSR (991) '17"
        assert snap.race_type == "timed"
        assert snap.tyre_wear_multiplier == 3.0
        assert snap.refuel_rate_lps == 12.0
        # strategy assumptions come from StrategyContext
        assert snap.config_id == "a1b2c3d4e5"
        assert snap.fuel_burn_per_lap == 2.85
        assert snap.planned_stops == 1
        assert snap.stint_plan[0].compound == "RM"
        assert snap.pit_laps == (12,)

    def test_snapshot_id_stable_for_same_state(self):
        ev = build_event_context(event=db_event(), strategy=strategy_dict())
        ctx = build_strategy_context(strategy=strategy_dict(), event_context=ev)
        a = build_strategy_prompt_snapshot(ctx, ev)
        b = build_strategy_prompt_snapshot(ctx, ev)
        assert a.snapshot_id == b.snapshot_id
        assert a.schema == STRATEGY_PROMPT_SNAPSHOT_SCHEMA

    def test_snapshot_frozen_even_if_legacy_config_changes_later(self):
        # Build a snapshot, THEN mutate the source strategy dict. The snapshot
        # must not change — this is the whole point of freezing.
        strat = strategy_dict()
        ev = build_event_context(event=db_event(), strategy=strat)
        ctx = build_strategy_context(strategy=strat, event_context=ev)
        snap = build_strategy_prompt_snapshot(ctx, ev)
        before_burn = snap.fuel_burn_per_lap
        before_compounds = tuple(s.compound for s in snap.stint_plan)
        # Mutate the legacy dict in place afterwards.
        strat["fuel_burn_per_lap"] = 9.99
        strat["stops"].append({"laps": 5, "compound": "RS"})
        strat["stops"][0]["compound"] = "HACKED"
        assert snap.fuel_burn_per_lap == before_burn
        assert tuple(s.compound for s in snap.stint_plan) == before_compounds

    def test_snapshot_id_changes_when_event_changes(self):
        ev1 = build_event_context(event=db_event(laps=25), strategy=strategy_dict())
        ev2 = build_event_context(event=db_event(laps=30), strategy=strategy_dict())
        ctx = build_strategy_context(strategy=strategy_dict())
        a = build_strategy_prompt_snapshot(ctx, ev1)
        b = build_strategy_prompt_snapshot(ctx, ev2)
        assert a.snapshot_id != b.snapshot_id

    def test_snapshot_id_changes_when_strategy_changes(self):
        ev = build_event_context(event=db_event(), strategy=strategy_dict())
        c1 = build_strategy_context(strategy=strategy_dict(fuel_burn_per_lap=2.85), event_context=ev)
        c2 = build_strategy_context(strategy=strategy_dict(fuel_burn_per_lap=3.50), event_context=ev)
        a = build_strategy_prompt_snapshot(c1, ev)
        b = build_strategy_prompt_snapshot(c2, ev)
        assert a.snapshot_id != b.snapshot_id

    def test_snapshot_defensive_without_event_context(self):
        ctx = build_strategy_context(strategy=strategy_dict())
        snap = build_strategy_prompt_snapshot(ctx, None)
        assert snap.track == ""
        assert snap.race_type == "lap"
        assert snap.config_id == "a1b2c3d4e5"

    def test_snapshot_to_dict(self):
        ev = build_event_context(event=db_event(), strategy=strategy_dict())
        ctx = build_strategy_context(strategy=strategy_dict(), event_context=ev)
        d = build_strategy_prompt_snapshot(ctx, ev).to_dict()
        assert d["schema"] == STRATEGY_PROMPT_SNAPSHOT_SCHEMA
        assert isinstance(d["stint_plan"], list)
        assert d["stint_plan"][0]["compound"] == "RM"


# --------------------------------------------------------------------------- #
# Serialisation + immutability
# --------------------------------------------------------------------------- #
class TestSerialisationAndImmutability:
    def test_to_dict_shape(self):
        d = build_strategy_context(strategy=strategy_dict()).to_dict()
        assert d["schema"] == STRATEGY_CONTEXT_SCHEMA
        assert d["source"] == "legacy_strategy"
        assert isinstance(d["stint_plan"], list)
        assert d["config_id"] == "a1b2c3d4e5"
        assert d["pit_laps"] == [12]

    def test_summary_line_with_plan(self):
        line = build_strategy_context(strategy=strategy_dict()).summary_line()
        assert "RM" in line and "RH" in line
        assert "1 stop" in line

    def test_summary_line_no_plan(self):
        ctx = build_strategy_context(strategy={"fuel_burn_per_lap": 2.8})
        assert "No strategy plan" in ctx.summary_line()

    def test_summary_lines_list(self):
        lines = build_strategy_context(strategy=strategy_dict(
            starting_fuel=60.0, fuel_margin=1.5)).to_summary_lines()
        assert any("Stint plan" in l for l in lines)
        assert any("Starting fuel" in l for l in lines)

    def test_frozen_immutable(self):
        ctx = build_strategy_context(strategy=strategy_dict())
        with pytest.raises(Exception):
            ctx.config_id = "hacked"  # type: ignore[misc]

    def test_stint_entry_frozen(self):
        ctx = build_strategy_context(strategy=strategy_dict())
        with pytest.raises(Exception):
            ctx.stint_plan[0].laps = 999  # type: ignore[misc]


# --------------------------------------------------------------------------- #
# Existing behaviour preserved for current consumers
# --------------------------------------------------------------------------- #
class TestExistingBehaviourPreserved:
    def test_config_id_matches_legacy_read(self):
        # A consumer previously read config["strategy"]["config_id"] directly;
        # StrategyContext.config_id must return the identical value.
        strat = strategy_dict(config_id="deadbeef00")
        assert build_strategy_context(strategy=strat).config_id == \
            strat.get("config_id", "")

    def test_fuel_burn_matches_legacy_read(self):
        strat = strategy_dict(fuel_burn_per_lap=3.33)
        assert build_strategy_context(strategy=strat).fuel_burn_per_lap == \
            float(strat.get("fuel_burn_per_lap", 2.0))

    def test_stops_roundtrip_to_stint_dicts(self):
        # The stint plan must round-trip back to the legacy stops dict shape so
        # existing engine code (Stint.from_dict) still works.
        strat = strategy_dict()
        ctx = build_strategy_context(strategy=strat)
        roundtrip = [s.to_dict() for s in ctx.stint_plan]
        for orig, rt in zip(strat["stops"], roundtrip):
            assert rt["laps"] == orig["laps"]
            assert rt["compound"] == orig["compound"]
            assert rt["ref_lap_ms"] == orig["ref_lap_ms"]
            assert rt["pace_threshold_ms"] == orig["pace_threshold_ms"]


# --------------------------------------------------------------------------- #
# Source-scan: the dashboard helper + migrated consumer
# --------------------------------------------------------------------------- #
class TestDashboardMigration:
    def test_has_build_strategy_context_helper(self, dash_src):
        assert "def _build_strategy_context(self)" in dash_src
        assert "from data.strategy_context import build_strategy_context" in dash_src

    def test_helper_reads_event_context(self, dash_src):
        start = dash_src.index("def _build_strategy_context")
        nxt = dash_src.index("\n    def ", start + 1)
        body = dash_src[start:nxt]
        assert "_build_event_context()" in body
        assert "config[\"strategy\"]" in body or "config.get(\"strategy\"" in body

    def test_lap_bank_uses_strategy_context(self, dash_src):
        start = dash_src.index("def _refresh_lap_bank")
        nxt = dash_src.index("\n    def ", start + 1)
        body = dash_src[start:nxt]
        assert "_build_strategy_context()" in body
        assert "current_config_id" in body
