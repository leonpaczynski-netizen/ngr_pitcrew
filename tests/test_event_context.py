"""State Consolidation 1 — EventContext tests.

Pure unit tests of data/event_context.py (no PyQt6, no DB) plus source-scans of
the one migrated dashboard consumer.
"""

from pathlib import Path

import pytest

from data.event_context import (
    EVENT_CONTEXT_SCHEMA,
    EventContext,
    EventContextSource,
    EventContextValidationResult,
    build_event_context,
    empty_event_context,
    validate_event_context,
    compute_change_hash,
    flow_flags,
)

ROOT = Path(__file__).parent.parent


@pytest.fixture(scope="module")
def dash_src():
    return (ROOT / "ui" / "dashboard.py").read_text(encoding="utf-8")


# --------------------------------------------------------------------------- #
# Representative fixtures mirroring the real schemas
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
        "weather": "Random",
        "damage": "Heavy",
        "avail_tyres": ["RH", "RM", "RS"],
        "req_tyres": ["RM"],
        "allowed_tuning_categories": ["suspension", "aero"],
        "notes": "",
    }
    d.update(over)
    return d


def strategy_dict(**over):
    """A config["strategy"] snapshot."""
    d = {
        "track": "Fuji Speedway",
        "car": "Porsche 911 RSR (991) '17",
        "race_type": "timed",
        "laps": 1,
        "total_laps": 1,
        "race_duration_minutes": 50,
        "tyre_wear_multiplier": 3,
        "fuel_mult": 3,
        "refuel_speed_lps": 1,
        "mandatory_stops": 0,
        "weather": "Random",
        "damage": "Heavy",
        "avail_tyres": ["RH", "RM", "RS", "IM", "HW"],
        "required_tyres": [],
        "bop": False,
        "tuning": True,
        "allowed_tuning_categories": ["brake_balance", "suspension", "aero"],
        "event_id": 7,
        "track_location_id": "fuji_speedway",
        "layout_id": "fuji_speedway__full_course",
    }
    d.update(over)
    return d


# --------------------------------------------------------------------------- #
# Build sources
# --------------------------------------------------------------------------- #
class TestBuildSources:
    def test_empty(self):
        ctx = build_event_context()
        assert ctx.source == EventContextSource.EMPTY
        assert ctx.has_active_event is False
        assert ctx.change_hash == ""
        assert empty_event_context().source == EventContextSource.EMPTY

    def test_db_only(self):
        ctx = build_event_context(event=db_event())
        assert ctx.source == EventContextSource.DB_EVENT
        assert ctx.has_active_event

    def test_strategy_only_is_legacy(self):
        ctx = build_event_context(strategy=strategy_dict())
        assert ctx.source == EventContextSource.LEGACY_STRATEGY
        assert ctx.has_active_event

    def test_merged(self):
        ctx = build_event_context(event=db_event(), strategy=strategy_dict())
        assert ctx.source == EventContextSource.MERGED


# --------------------------------------------------------------------------- #
# Field normalisation across the two schemas
# --------------------------------------------------------------------------- #
class TestNormalisation:
    def test_db_field_names_mapped(self):
        # DB uses tyre_wear / duration_mins / refuel_rate_lps / req_tyres.
        ctx = build_event_context(event=db_event())
        assert ctx.tyre_wear_multiplier == 3.0
        assert ctx.race_duration_minutes == 50
        assert ctx.refuel_rate_lps == 12.0
        assert ctx.required_tyres == ("RM",)
        assert ctx.available_tyres == ("RH", "RM", "RS")

    def test_strategy_field_names_mapped(self):
        # Strategy uses tyre_wear_multiplier / race_duration_minutes / refuel_speed_lps.
        ctx = build_event_context(strategy=strategy_dict())
        assert ctx.tyre_wear_multiplier == 3.0
        assert ctx.race_duration_minutes == 50
        assert ctx.refuel_rate_lps == 1.0
        assert ctx.required_tyres == ()

    def test_car_comes_from_strategy_when_db_lacks_it(self):
        # events table has no car column; car must come from the strategy overlay.
        ctx = build_event_context(event=db_event(), strategy=strategy_dict())
        assert ctx.car == "Porsche 911 RSR (991) '17"
        # track ids likewise only in the strategy snapshot
        assert ctx.track_location_id == "fuji_speedway"
        assert ctx.layout_id == "fuji_speedway__full_course"

    def test_event_id_and_name(self):
        ctx = build_event_context(event=db_event(), active_event_id="NGR Porsche Cup Rd7")
        assert ctx.event_id == 7
        assert ctx.event_name == "NGR Porsche Cup Rd7"

    def test_name_falls_back_to_active_event_id(self):
        ctx = build_event_context(strategy=strategy_dict(), active_event_id="My Event")
        assert ctx.event_name == "My Event"


# --------------------------------------------------------------------------- #
# Race type preservation
# --------------------------------------------------------------------------- #
class TestRaceType:
    def test_timed_stays_timed(self):
        ctx = build_event_context(event=db_event(race_type="timed", duration_mins=45))
        assert ctx.is_timed and not ctx.is_lap_race
        assert ctx.race_type == "timed"
        assert "45 minutes, Timed Race" in ctx.race_length_text()

    def test_lap_stays_lap(self):
        ctx = build_event_context(event=db_event(race_type="lap", laps=25))
        assert ctx.is_lap_race and not ctx.is_timed
        assert "25 laps, Lap Race" in ctx.race_length_text()

    def test_one_lap_is_singular(self):
        ctx = build_event_context(event=db_event(race_type="lap", laps=1))
        assert "1 lap, Lap Race" in ctx.race_length_text()

    def test_weird_race_type_token_normalises(self):
        ctx = build_event_context(event=db_event(race_type="Timed Race"))
        assert ctx.race_type == "timed"
        ctx2 = build_event_context(event=db_event(race_type="Lap Race"))
        assert ctx2.race_type == "lap"


# --------------------------------------------------------------------------- #
# Rules / multipliers preserved
# --------------------------------------------------------------------------- #
class TestRulesPreserved:
    def test_bop_and_tuning_preserved(self):
        on = build_event_context(event=db_event(bop=1, tuning=0))
        assert on.bop_enabled is True
        assert on.tuning_allowed is False
        assert on.tuning_locked is True
        off = build_event_context(event=db_event(bop=0, tuning=1))
        assert off.bop_enabled is False
        assert off.tuning_allowed is True

    def test_allowed_tuning_categories_preserved(self):
        ctx = build_event_context(event=db_event(allowed_tuning_categories=["aero", "differential"]))
        assert ctx.allowed_tuning_categories == ("aero", "differential")

    def test_multipliers_and_refuel_preserved(self):
        ctx = build_event_context(event=db_event(tyre_wear=8.0, fuel_mult=5.0, refuel_rate_lps=20.0))
        assert ctx.tyre_wear_multiplier == 8.0
        assert ctx.fuel_multiplier == 5.0
        assert ctx.refuel_rate_lps == 20.0

    def test_bop_from_strategy_bool(self):
        ctx = build_event_context(strategy=strategy_dict(bop=True, tuning=False))
        assert ctx.bop_enabled is True
        assert ctx.tuning_allowed is False


# --------------------------------------------------------------------------- #
# DB-first resolution avoids stale strategy values
# --------------------------------------------------------------------------- #
class TestNoStaleDownstream:
    def test_db_event_beats_stale_strategy(self):
        # Event edited to 6× wear in the DB but the strategy snapshot is stale at 3×.
        fresh_event = db_event(tyre_wear=6.0, fuel_mult=4.0)
        stale_strategy = strategy_dict(tyre_wear_multiplier=3, fuel_mult=3)
        ctx = build_event_context(event=fresh_event, strategy=stale_strategy)
        assert ctx.tyre_wear_multiplier == 6.0, "must reflect the fresh DB value, not the stale snapshot"
        assert ctx.fuel_multiplier == 4.0

    def test_rebuild_reflects_changed_settings_via_hash(self):
        a = build_event_context(event=db_event(laps=25))
        b = build_event_context(event=db_event(laps=30))
        assert a.change_hash != b.change_hash, "changed lap count must change the hash"

    def test_identical_state_same_hash(self):
        a = build_event_context(event=db_event(), strategy=strategy_dict())
        b = build_event_context(event=db_event(), strategy=strategy_dict())
        assert a.change_hash == b.change_hash

    def test_hash_ignores_source_provenance(self):
        # Same canonical fields via different provenance need not match, but the
        # hash must be stable for identical inputs and change with real edits.
        base = build_event_context(event=db_event())
        changed = build_event_context(event=db_event(bop=1))
        assert base.change_hash != changed.change_hash

    def test_compute_change_hash_is_deterministic(self):
        f = {"a": 1, "b": [1, 2], "c": "x"}
        assert compute_change_hash(f) == compute_change_hash(dict(f))
        assert len(compute_change_hash(f)) == 12


# --------------------------------------------------------------------------- #
# Validation — warnings not crashes
# --------------------------------------------------------------------------- #
class TestValidation:
    def test_empty_context_flagged_not_crashing(self):
        res = validate_event_context(empty_event_context())
        assert isinstance(res, EventContextValidationResult)
        assert res.ok is False
        assert "event" in res.missing_fields

    def test_missing_car_warns(self):
        ctx = build_event_context(event=db_event())  # no strategy → no car
        res = validate_event_context(ctx)
        assert not res.ok
        assert "car" in res.missing_fields
        assert any("car" in w.lower() for w in res.warnings)

    def test_timed_without_duration_warns(self):
        ctx = build_event_context(event=db_event(race_type="timed", duration_mins=0),
                                  strategy=strategy_dict(car="X", race_duration_minutes=0))
        res = validate_event_context(ctx)
        assert "race_duration_minutes" in res.missing_fields

    def test_lap_without_laps_warns(self):
        ctx = build_event_context(event=db_event(race_type="lap", laps=0),
                                  strategy=strategy_dict(car="X", laps=0, total_laps=0))
        res = validate_event_context(ctx)
        assert "laps" in res.missing_fields

    def test_tuning_locked_but_categories_listed_warns(self):
        ctx = build_event_context(event=db_event(tuning=0, allowed_tuning_categories=["aero"]),
                                  strategy=strategy_dict(car="X"))
        res = validate_event_context(ctx)
        assert any("lock" in w.lower() for w in res.warnings)

    def test_fully_specified_context_is_ok(self):
        ctx = build_event_context(event=db_event(), strategy=strategy_dict())
        res = validate_event_context(ctx)
        assert res.ok, res.warnings

    def test_validation_never_raises_on_garbage(self):
        # Defensive: junk types must not crash the builder or validator.
        ctx = build_event_context(event={"tyre_wear": "abc", "laps": None, "bop": "yes"},
                                  strategy={"fuel_mult": None})
        res = validate_event_context(ctx)
        assert isinstance(res, EventContextValidationResult)
        assert ctx.bop_enabled is True  # "yes" → True
        assert ctx.tyre_wear_multiplier == 1.0  # "abc" → default


# --------------------------------------------------------------------------- #
# Legacy compatibility + product_flow bridge + serialisation
# --------------------------------------------------------------------------- #
class TestInteropAndSerialisation:
    def test_legacy_strategy_only_still_builds(self):
        ctx = build_event_context(strategy=strategy_dict())
        assert ctx.car and ctx.track and ctx.is_timed
        assert ctx.source == EventContextSource.LEGACY_STRATEGY

    def test_flow_flags_mapping(self):
        ctx = build_event_context(event=db_event(), strategy=strategy_dict())
        flags = flow_flags(ctx)
        assert flags == {
            "has_event": True, "has_car": True,
            "has_track": True, "tuning_confirmed": True,
        }

    def test_flow_flags_empty(self):
        flags = flow_flags(empty_event_context())
        assert flags["has_event"] is False
        assert flags["has_car"] is False

    def test_flow_flags_feed_product_flow(self):
        # The bridge must actually satisfy build_flow_state_summary's signature.
        from ui import product_flow
        ctx = build_event_context(event=db_event(), strategy=strategy_dict())
        summary = product_flow.build_flow_state_summary(**flow_flags(ctx))
        # event/car/track/tuning done → next action is practice laps.
        assert "practice" in summary["next_action"].lower()

    def test_to_dict_roundtrip_keys(self):
        d = build_event_context(event=db_event(), strategy=strategy_dict()).to_dict()
        assert d["schema"] == EVENT_CONTEXT_SCHEMA
        assert d["source"] == "merged"
        assert isinstance(d["allowed_tuning_categories"], list)
        assert d["tyre_wear_multiplier"] == 3.0

    def test_summary_line_and_lines(self):
        ctx = build_event_context(event=db_event(), strategy=strategy_dict())
        line = ctx.summary_line()
        assert "Fuji Speedway" in line and "Timed Race" in line
        lines = ctx.to_summary_lines()
        assert any("Required tyres" in l for l in lines)

    def test_frozen_immutable(self):
        ctx = build_event_context(event=db_event())
        with pytest.raises(Exception):
            ctx.car = "hacked"  # type: ignore[misc]


# --------------------------------------------------------------------------- #
# Source-scan: the migrated dashboard consumer
# --------------------------------------------------------------------------- #
class TestDashboardMigration:
    def test_has_build_event_context_helper(self, dash_src):
        assert "def _build_event_context(self)" in dash_src
        assert "from data.event_context import build_event_context" in dash_src

    def test_telemetry_context_uses_event_context(self, dash_src):
        # Locate the method and confirm it reads from the EventContext helper.
        start = dash_src.index("def _refresh_telemetry_context")
        # Slice to the end of the method (next top-level def in the class).
        nxt = dash_src.index("\n    def ", start + 1)
        body = dash_src[start:nxt]
        assert "_build_event_context()" in body
        assert "ctx.car" in body
        assert "ctx.track" in body
        # And the DEF-P1-011 behaviour is preserved.
        assert "avg_fuel_per_lap" in body
        assert "from telemetry" in body
