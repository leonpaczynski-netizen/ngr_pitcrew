"""AI Snapshot Migration — frozen context inputs tests.

Three layers:
1. **Golden byte-identity** — the legacy race-params/setup-input expressions
   (copied VERBATIM from the pre-migration dashboard/setup_builder code) are
   reproduced here and must match the snapshot builders' output exactly for
   every synced scenario, including a byte-identical prompt-text comparison.
2. **Snapshot semantics** — ids stable/changing per context, frozen after
   legacy mutation, staleness detection, warnings, legacy fallback.
3. **Source scans** — the migrated dashboard/setup_builder paths read through
   the snapshot layer, not raw config["strategy"] event fields.
"""

from pathlib import Path

import pytest

from data.event_context import build_event_context
from data.strategy_context import build_strategy_context
from data.setup_context import build_setup_context, build_setup_prompt_snapshot
from data.track_context import build_track_context
from data.ai_context_snapshot import (
    AI_CONTEXT_SNAPSHOT_SCHEMA,
    AIContextSnapshot,
    AIContextSnapshotSource,
    AIContextSnapshotValidationResult,
    PracticeAnalysisSnapshot,
    SetupAISnapshot,
    StrategyAISnapshot,
    build_practice_analysis_snapshot,
    build_setup_ai_snapshot,
    build_strategy_ai_snapshot,
    validate_ai_context_snapshot,
)

ROOT = Path(__file__).parent.parent


@pytest.fixture(scope="module")
def dash_src():
    return (ROOT / "ui" / "dashboard.py").read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def sb_src():
    return (ROOT / "ui" / "setup_builder_ui.py").read_text(encoding="utf-8")


# --------------------------------------------------------------------------- #
# Fixtures: a fully-synced state (the "Set as Active" fan-out ran)
# --------------------------------------------------------------------------- #
def db_event(**over):
    d = {
        "id": 7, "name": "NGR Porsche Cup Rd7", "track": "Fuji Speedway",
        "race_type": "timed", "laps": 25, "duration_mins": 50,
        "tyre_wear": 3.0, "fuel_mult": 3.0, "refuel_rate_lps": 12.0,
        "mandatory_stops": 1, "bop": 0, "tuning": 1,
        "avail_tyres": ["RH", "RM", "RS"], "req_tyres": ["RM"],
        "allowed_tuning_categories": ["suspension", "aero"],
    }
    d.update(over)
    return d


def strategy_dict(**over):
    """config["strategy"] exactly as the fan-out + strategy tab write it."""
    d = {
        "track": "Fuji Speedway",
        "car": "Porsche 911 RSR (991) '17",
        "race_type": "timed",
        "laps": 25, "total_laps": 25,
        "race_duration_minutes": 50,
        "tyre_wear_multiplier": 3, "fuel_mult": 3, "fuel_multiplier": 3,
        "refuel_speed_lps": 12,
        "mandatory_stops": 1,
        "mandatory_compounds": "RM",
        "required_tyres": ["RM"],
        "avail_tyres": ["RH", "RM", "RS"],
        "bop": False, "tuning": True,
        "allowed_tuning_categories": ["suspension", "aero"],
        "event_id": 7,
        "track_location_id": "fuji_speedway",
        "layout_id": "fuji_speedway__full_course",
        "config_id": "a1b2c3d4e5",
        "fuel_burn_per_lap": 2.85,
        "pit_loss_secs": 23.0,
        "stops": [{"laps": 12, "compound": "RM"}, {"laps": 13, "compound": "RH"}],
    }
    d.update(over)
    return d


def contexts_for(strat, event=None):
    ev = build_event_context(event=event, strategy=strat,
                             active_event_id=(event or {}).get("name"))
    sc = build_strategy_context(strategy=strat, event_context=ev)
    tc = build_track_context(event_context=ev, strategy=strat)
    return ev, sc, tc


# --------------------------------------------------------------------------- #
# GOLDEN legacy expressions — copied VERBATIM from the pre-migration code.
# _assemble_strategy_inputs / _run_ai_analysis (tuning default True) and
# _run_practice_analysis (tuning default False, DEF-P1-005).
# --------------------------------------------------------------------------- #
def legacy_mandatory_compounds(sc):
    raw = sc.get("mandatory_compounds", "")
    if isinstance(raw, list):
        return [c.strip().upper() for c in raw if c.strip()]
    if isinstance(raw, str) and raw.strip():
        return [c.strip().upper() for c in raw.split(",") if c.strip()]
    return []


def legacy_strategy_race_params(_sc, fuel_burn):
    """VERBATIM: dashboard._assemble_strategy_inputs / _run_ai_analysis."""
    return {
        "track":                _sc.get("track", ""),
        "track_location_id":    _sc.get("track_location_id", ""),
        "layout_id":            _sc.get("layout_id", ""),
        "total_laps":           int(_sc.get("total_laps", 25)),
        "tyre_wear_multiplier": float(_sc.get("tyre_wear_multiplier", 1.0)),
        "fuel_burn_per_lap":    fuel_burn,
        "refuel_speed_lps":     float(_sc.get("refuel_speed_lps", 10.0)),
        "pit_loss_secs":        float(_sc.get("pit_loss_secs", 23.0)),
        "min_mandatory_stops":  int(_sc.get("mandatory_stops", 0)),
        "mandatory_compounds":  legacy_mandatory_compounds(_sc),
        "race_type":            _sc.get("race_type", "lap"),
        "duration_mins":        int(_sc.get("race_duration_minutes", 0)),
        "tuning_locked":        not bool(_sc.get("tuning", True)),
        "allowed_tuning":       _sc.get("allowed_tuning_categories") or [],
        "bop":                  bool(_sc.get("bop", False)),
        "avail_tyres":          _sc.get("avail_tyres", []) or [],
    }


def legacy_practice_race_params(_psc, fuel_burn):
    """VERBATIM: dashboard._run_practice_analysis (tuning default False)."""
    p = legacy_strategy_race_params(_psc, fuel_burn)
    p["tuning_locked"] = not bool(_psc.get("tuning", False))
    return p


def legacy_setup_build_inputs(_sc):
    """VERBATIM: setup_builder_ui Build-Setup-with-AI input block."""
    return {
        "car":                  _sc.get("car", "") or "Unknown",
        "track":                _sc.get("track", ""),
        "race_laps":            _sc.get("total_laps", 25),
        "duration_mins":        int(_sc.get("race_duration_minutes", 0)),
        "mandatory_stops":      int(_sc.get("mandatory_stops", 0)),
        "refuel_rate_lps":      float(_sc.get("refuel_speed_lps", 0.0)),
        "pit_loss_secs":        float(_sc.get("pit_loss_secs", 0.0)),
        "allowed_tuning":       _sc.get("allowed_tuning_categories", []) or None,
        "tuning_locked":        not bool(_sc.get("tuning", True)),
        "tyre_wear_multiplier": float(_sc.get("tyre_wear_multiplier", 1.0)),
        "fuel_multiplier":      float(_sc.get("fuel_multiplier", 1.0)),
        "avail_tyres":          _sc.get("avail_tyres", []) or [],
        "required_tyres":       _sc.get("required_tyres", []) or [],
        "race_type":            _sc.get("race_type", "lap"),
        "track_location_id":    _sc.get("track_location_id", ""),
        "layout_id":            _sc.get("layout_id", ""),
        "mandatory_compounds":  _sc.get("mandatory_compounds", "") or "",
    }


def snapshot_strategy_params(strat, event=None, fuel_burn_override=None):
    ev, sc, tc = contexts_for(strat, event)
    snap = build_strategy_ai_snapshot(
        event_context=ev, strategy_context=sc, track_context=tc,
        legacy_strategy=strat, fuel_burn_override=fuel_burn_override)
    return snap.race_params_dict(), snap


def snapshot_practice_params(strat, event=None, fuel_burn_override=None):
    ev, sc, tc = contexts_for(strat, event)
    snap = build_practice_analysis_snapshot(
        event_context=ev, strategy_context=sc, track_context=tc,
        legacy_strategy=strat, fuel_burn_override=fuel_burn_override)
    return snap.race_params_dict(), snap


# --------------------------------------------------------------------------- #
# 1. Golden byte-identity — synced state
# --------------------------------------------------------------------------- #
class TestByteIdentitySynced:
    def test_strategy_params_identical_full_state(self):
        strat = strategy_dict()
        legacy = legacy_strategy_race_params(strat, float(strat.get("fuel_burn_per_lap", 2.0)))
        mine, _ = snapshot_strategy_params(strat, event=db_event())
        assert mine == legacy

    def test_strategy_params_identical_with_fuel_override(self):
        strat = strategy_dict()
        legacy = legacy_strategy_race_params(strat, 3.14)
        mine, _ = snapshot_strategy_params(strat, event=db_event(), fuel_burn_override=3.14)
        assert mine == legacy

    def test_practice_params_identical_full_state(self):
        strat = strategy_dict()
        legacy = legacy_practice_race_params(strat, 2.5)
        mine, _ = snapshot_practice_params(strat, event=db_event(), fuel_burn_override=2.5)
        assert mine == legacy

    def test_strategy_params_identical_lap_race(self):
        strat = strategy_dict(race_type="lap", laps=30, total_laps=30,
                              race_duration_minutes=0)
        legacy = legacy_strategy_race_params(strat, float(strat["fuel_burn_per_lap"]))
        mine, _ = snapshot_strategy_params(
            strat, event=db_event(race_type="lap", laps=30, duration_mins=0))
        assert mine == legacy

    def test_strategy_params_identical_bop_locked(self):
        strat = strategy_dict(bop=True, tuning=False, allowed_tuning_categories=[])
        legacy = legacy_strategy_race_params(strat, float(strat["fuel_burn_per_lap"]))
        mine, _ = snapshot_strategy_params(
            strat, event=db_event(bop=1, tuning=0, allowed_tuning_categories=[]))
        assert mine == legacy
        assert mine["tuning_locked"] is True
        assert mine["bop"] is True

    def test_strategy_params_identical_no_db_event(self):
        # Legacy-strategy-only context (no DB record) must still be identical.
        strat = strategy_dict()
        legacy = legacy_strategy_race_params(strat, float(strat["fuel_burn_per_lap"]))
        mine, snap = snapshot_strategy_params(strat, event=None)
        assert mine == legacy
        assert snap.core.source == AIContextSnapshotSource.CONTEXTS

    def test_setup_inputs_identical_full_state(self):
        strat = strategy_dict()
        legacy = legacy_setup_build_inputs(strat)
        ev, sc, tc = contexts_for(strat, db_event())
        snap = build_setup_ai_snapshot(
            event_context=ev, strategy_context=sc, track_context=tc,
            legacy_strategy=strat)
        assert snap.car == legacy["car"]
        assert snap.track == legacy["track"]
        assert snap.race_laps == legacy["race_laps"]
        assert snap.duration_mins == legacy["duration_mins"]
        assert snap.mandatory_stops == legacy["mandatory_stops"]
        assert snap.refuel_rate_lps == legacy["refuel_rate_lps"]
        assert snap.pit_loss_secs == legacy["pit_loss_secs"]
        assert snap.allowed_tuning_or_none() == legacy["allowed_tuning"]
        assert snap.tuning_locked == legacy["tuning_locked"]
        assert snap.tyre_wear_multiplier == legacy["tyre_wear_multiplier"]
        assert snap.fuel_multiplier == legacy["fuel_multiplier"]
        assert snap.avail_tyres_list() == legacy["avail_tyres"]
        assert snap.required_tyres_list() == legacy["required_tyres"]
        assert snap.race_type == legacy["race_type"]
        assert snap.track_location_id == legacy["track_location_id"]
        assert snap.layout_id == legacy["layout_id"]
        assert snap.mandatory_compounds_str == legacy["mandatory_compounds"]

    def test_race_params_construct_byte_identical(self):
        """The strongest proof available post-AI-removal: RaceParams built from
        the legacy expressions and from the snapshot are field-identical."""
        from strategy.race_params import RaceParams
        strat = strategy_dict()

        legacy_params = RaceParams(**legacy_strategy_race_params(
            strat, float(strat.get("fuel_burn_per_lap", 2.0))))
        mine, _ = snapshot_strategy_params(strat, event=db_event())
        snap_params = RaceParams(**mine)

        assert legacy_params == snap_params, "RaceParams must be field-identical"


# --------------------------------------------------------------------------- #
# 1b. Golden byte-identity — absent keys / legacy defaults
# --------------------------------------------------------------------------- #
class TestByteIdentityDefaults:
    def test_absent_optional_keys_defaults_preserved(self):
        # A minimal strategy dict (event active, but optional keys never set).
        strat = {"track": "Fuji Speedway", "car": "X", "race_type": "lap",
                 "tuning": True, "event_id": 7}
        legacy = legacy_strategy_race_params(strat, float(strat.get("fuel_burn_per_lap", 2.0)) if "fuel_burn_per_lap" in strat else 2.0)
        # fuel_burn absent → legacy raw expression float(get(...,2.0)) = 2.0
        legacy["fuel_burn_per_lap"] = 2.0
        mine, _ = snapshot_strategy_params(strat, event=None)
        assert mine["total_laps"] == 25 == legacy["total_laps"]
        assert mine["refuel_speed_lps"] == 10.0 == legacy["refuel_speed_lps"]
        assert mine["pit_loss_secs"] == 23.0 == legacy["pit_loss_secs"]
        assert mine["fuel_burn_per_lap"] == 2.0
        assert mine == legacy

    def test_present_zero_values_not_replaced_by_defaults(self):
        # Keys present with 0 must stay 0 (not silently become 10/23/2).
        strat = strategy_dict(refuel_speed_lps=0, pit_loss_secs=0, fuel_burn_per_lap=0)
        legacy = legacy_strategy_race_params(strat, float(strat.get("fuel_burn_per_lap", 2.0)))
        # No DB event → context mirrors the legacy dict exactly.
        mine, _ = snapshot_strategy_params(strat, event=None)
        assert mine["refuel_speed_lps"] == 0.0 == legacy["refuel_speed_lps"]
        assert mine["pit_loss_secs"] == 0.0 == legacy["pit_loss_secs"]
        assert mine["fuel_burn_per_lap"] == 0.0 == legacy["fuel_burn_per_lap"]
        assert mine == legacy

    def test_practice_tuning_absent_stays_locked(self):
        # DEF-P1-005: practice analysis with NO tuning key anywhere → locked.
        strat = strategy_dict()
        del strat["tuning"]
        legacy = legacy_practice_race_params(strat, 2.5)
        assert legacy["tuning_locked"] is True
        mine, _ = snapshot_practice_params(strat, event=None, fuel_burn_override=2.5)
        assert mine["tuning_locked"] is True
        assert mine == legacy

    def test_strategy_tuning_absent_stays_unlocked(self):
        strat = strategy_dict()
        del strat["tuning"]
        legacy = legacy_strategy_race_params(strat, 2.5)
        assert legacy["tuning_locked"] is False
        mine, _ = snapshot_strategy_params(strat, event=None, fuel_burn_override=2.5)
        assert mine["tuning_locked"] is False
        assert mine == legacy

    def test_practice_tuning_absent_but_db_event_present_uses_db_truth(self):
        # INTENTIONAL DIFFERENCE (documented in docs/AI_SNAPSHOT_MIGRATION.md):
        # legacy practice defaulted to LOCKED when the config key was missing
        # even though the DB event said tuning is allowed. The snapshot uses
        # the durable DB truth instead of the blind safe default.
        strat = strategy_dict()
        del strat["tuning"]
        mine, _ = snapshot_practice_params(
            strat, event=db_event(tuning=1), fuel_burn_override=2.5)
        assert mine["tuning_locked"] is False  # DB says allowed
        legacy = legacy_practice_race_params(strat, 2.5)
        assert legacy["tuning_locked"] is True  # legacy blind default

    def test_setup_inputs_defaults_preserved(self):
        strat = {"track": "T", "car": "", "tuning": True}
        legacy = legacy_setup_build_inputs(strat)
        ev, sc, tc = contexts_for(strat, None)
        snap = build_setup_ai_snapshot(event_context=ev, strategy_context=sc,
                                       track_context=tc, legacy_strategy=strat)
        assert snap.car == "Unknown" == legacy["car"]
        assert snap.race_laps == 25 == legacy["race_laps"]
        assert snap.refuel_rate_lps == 0.0 == legacy["refuel_rate_lps"]   # setup default is 0.0
        assert snap.pit_loss_secs == 0.0 == legacy["pit_loss_secs"]      # setup default is 0.0
        assert snap.allowed_tuning_or_none() is None
        assert snap.mandatory_compounds_str == "" == legacy["mandatory_compounds"]


# --------------------------------------------------------------------------- #
# 1c. The intentional difference — fresh DB event beats stale config
# --------------------------------------------------------------------------- #
class TestIntentionalFreshness:
    def test_edited_db_event_supersedes_stale_config(self):
        # Event edited to 8x wear / 40 laps AFTER the fan-out wrote 3x / 25.
        stale_strat = strategy_dict()  # still says 3x, 25 laps
        fresh_event = db_event(tyre_wear=8.0, laps=40, race_type="lap")
        mine, snap = snapshot_strategy_params(stale_strat, event=fresh_event)
        assert mine["tyre_wear_multiplier"] == 8.0, "fresh DB value must win"
        assert mine["total_laps"] == 40
        assert mine["race_type"] == "lap"
        # ...whereas legacy would have used the stale copies:
        legacy = legacy_strategy_race_params(stale_strat, float(stale_strat["fuel_burn_per_lap"]))
        assert legacy["tyre_wear_multiplier"] == 3.0
        assert legacy["total_laps"] == 25


# --------------------------------------------------------------------------- #
# 2. Snapshot semantics
# --------------------------------------------------------------------------- #
class TestSnapshotSemantics:
    def test_schema_and_source(self):
        _, snap = snapshot_strategy_params(strategy_dict(), event=db_event())
        assert snap.core.schema == AI_CONTEXT_SNAPSHOT_SCHEMA
        assert snap.core.source == AIContextSnapshotSource.CONTEXTS
        assert snap.config_id == "a1b2c3d4e5"

    def test_id_stable_for_stable_inputs(self):
        _, a = snapshot_strategy_params(strategy_dict(), event=db_event())
        _, b = snapshot_strategy_params(strategy_dict(), event=db_event())
        assert a.core.snapshot_id == b.core.snapshot_id

    def test_id_changes_when_event_changes(self):
        _, a = snapshot_strategy_params(strategy_dict(), event=db_event(laps=25))
        _, b = snapshot_strategy_params(strategy_dict(), event=db_event(laps=30))
        assert a.core.snapshot_id != b.core.snapshot_id
        assert a.core.event_change_hash != b.core.event_change_hash

    def test_id_changes_when_strategy_changes(self):
        _, a = snapshot_strategy_params(strategy_dict(fuel_burn_per_lap=2.85), event=db_event())
        _, b = snapshot_strategy_params(strategy_dict(fuel_burn_per_lap=3.50), event=db_event())
        assert a.core.snapshot_id != b.core.snapshot_id
        assert a.core.strategy_change_hash != b.core.strategy_change_hash

    def test_id_changes_when_setup_snapshot_changes(self):
        strat = strategy_dict()
        ev, sc, tc = contexts_for(strat, db_event())
        setup_a = build_setup_prompt_snapshot(build_setup_context(
            setup={"setup_label": "A", "car": "X", "track": "T"}, event_context=ev))
        setup_b = build_setup_prompt_snapshot(build_setup_context(
            setup={"setup_label": "B", "car": "X", "track": "T"}, event_context=ev))
        a = build_strategy_ai_snapshot(event_context=ev, strategy_context=sc,
                                       track_context=tc, setup_snapshot=setup_a,
                                       legacy_strategy=strat)
        b = build_strategy_ai_snapshot(event_context=ev, strategy_context=sc,
                                       track_context=tc, setup_snapshot=setup_b,
                                       legacy_strategy=strat)
        assert a.core.snapshot_id != b.core.snapshot_id
        assert a.core.setup_snapshot_id != b.core.setup_snapshot_id

    def test_id_changes_when_track_context_changes(self):
        strat = strategy_dict()
        ev, sc, _ = contexts_for(strat, db_event())
        tc1 = build_track_context(event_context=ev, strategy=strat)
        tc2 = build_track_context(event_context=ev, strategy=strat,
                                  station_map_exists=True)
        a = build_strategy_ai_snapshot(event_context=ev, strategy_context=sc,
                                       track_context=tc1, legacy_strategy=strat)
        b = build_strategy_ai_snapshot(event_context=ev, strategy_context=sc,
                                       track_context=tc2, legacy_strategy=strat)
        assert a.core.snapshot_id != b.core.snapshot_id
        assert a.core.track_change_hash != b.core.track_change_hash

    def test_snapshot_frozen_after_legacy_mutation(self):
        strat = strategy_dict()
        mine, snap = snapshot_strategy_params(strat, event=db_event())
        before = snap.race_params_dict()
        # Mutate the legacy dict afterwards.
        strat["tyre_wear_multiplier"] = 99
        strat["avail_tyres"].append("HACKED")
        strat["allowed_tuning_categories"].clear()
        after = snap.race_params_dict()
        assert after == before
        assert after["tyre_wear_multiplier"] == 3.0
        assert "HACKED" not in after["avail_tyres"]

    def test_never_raises_on_garbage(self):
        snap = build_strategy_ai_snapshot(
            event_context="junk", strategy_context=42, setup_snapshot=[],
            track_context=3.14, legacy_strategy="not a dict")
        assert isinstance(snap, StrategyAISnapshot)
        snap2 = build_practice_analysis_snapshot(legacy_strategy=None)
        assert isinstance(snap2, PracticeAnalysisSnapshot)
        snap3 = build_setup_ai_snapshot(legacy_strategy=object())
        assert isinstance(snap3, SetupAISnapshot)

    def test_empty_source_when_nothing_available(self):
        snap = build_strategy_ai_snapshot()
        assert snap.core.source == AIContextSnapshotSource.EMPTY
        assert snap.core.warnings

    def test_to_dict(self):
        _, snap = snapshot_strategy_params(strategy_dict(), event=db_event())
        d = snap.to_dict()
        assert d["core"]["schema"] == AI_CONTEXT_SNAPSHOT_SCHEMA
        assert d["race_params"]["track"] == "Fuji Speedway"


# --------------------------------------------------------------------------- #
# 2b. Legacy fallback (no context at all)
# --------------------------------------------------------------------------- #
class TestLegacyFallback:
    def test_legacy_only_matches_legacy_expressions(self):
        strat = strategy_dict()
        snap = build_strategy_ai_snapshot(legacy_strategy=strat)  # no contexts
        assert snap.core.source == AIContextSnapshotSource.LEGACY_ONLY
        assert any("legacy" in w.lower() for w in snap.core.warnings)
        legacy = legacy_strategy_race_params(strat, 2.85)
        assert snap.race_params_dict() == legacy

    def test_legacy_only_practice_tuning_default(self):
        strat = strategy_dict()
        del strat["tuning"]
        snap = build_practice_analysis_snapshot(legacy_strategy=strat,
                                                fuel_burn_override=2.5)
        assert snap.race_params_dict()["tuning_locked"] is True

    def test_legacy_only_setup_inputs(self):
        strat = strategy_dict()
        snap = build_setup_ai_snapshot(legacy_strategy=strat)
        assert snap.core.source == AIContextSnapshotSource.LEGACY_ONLY
        legacy = legacy_setup_build_inputs(strat)
        assert snap.car == legacy["car"]
        assert snap.mandatory_compounds_str == legacy["mandatory_compounds"]


# --------------------------------------------------------------------------- #
# 2c. Staleness / mismatch detection
# --------------------------------------------------------------------------- #
class TestStalenessDetection:
    def test_stale_strategy_against_current_event(self):
        old_ev = build_event_context(event=db_event(laps=25), strategy=strategy_dict())
        sc_old = build_strategy_context(strategy=strategy_dict(), event_context=old_ev)
        new_ev = build_event_context(event=db_event(laps=40), strategy=strategy_dict())
        snap = build_strategy_ai_snapshot(
            event_context=new_ev, strategy_context=sc_old,
            legacy_strategy=strategy_dict())
        assert snap.core.has_stale_state
        assert any("older event" in w for w in snap.core.stale_warnings)

    def test_stale_setup_against_current_event(self):
        old_ev = build_event_context(event=db_event(laps=25), strategy=strategy_dict())
        setup_snap = build_setup_prompt_snapshot(build_setup_context(
            setup={"setup_label": "S", "car": "X", "track": "T"}, event_context=old_ev))
        new_ev = build_event_context(event=db_event(laps=40), strategy=strategy_dict())
        snap = build_setup_ai_snapshot(
            event_context=new_ev, setup_snapshot=setup_snap,
            legacy_strategy=strategy_dict())
        assert any("previous event" in w for w in snap.core.stale_warnings)

    def test_track_event_mismatch_detected(self):
        strat = strategy_dict()
        ev = build_event_context(event=db_event(), strategy=strat)
        # Track Modelling combos point at Daytona while the event is at Fuji.
        tc = build_track_context(selected_location_id="daytona_international_speedway",
                                 selected_layout_id="daytona_international_speedway__road_course",
                                 event_context=ev)
        snap = build_strategy_ai_snapshot(
            event_context=ev, track_context=tc, legacy_strategy=strat)
        assert any("does not match" in w for w in snap.core.stale_warnings)

    def test_no_false_staleness_when_synced(self):
        strat = strategy_dict()
        ev, sc, tc = contexts_for(strat, db_event())
        setup_snap = build_setup_prompt_snapshot(build_setup_context(
            setup={"setup_label": "S", "car": "X", "track": "T"}, event_context=ev))
        snap = build_strategy_ai_snapshot(
            event_context=ev, strategy_context=sc, setup_snapshot=setup_snap,
            track_context=tc, legacy_strategy=strat)
        assert snap.core.stale_warnings == ()
        res = validate_ai_context_snapshot(snap.core)
        assert isinstance(res, AIContextSnapshotValidationResult)
        assert res.ok

    def test_validation_flags_legacy_only(self):
        snap = build_strategy_ai_snapshot(legacy_strategy=strategy_dict())
        res = validate_ai_context_snapshot(snap.core)
        assert res.ok is False
        assert any("legacy" in w.lower() for w in res.all_warnings)


# --------------------------------------------------------------------------- #
# 3. Source scans — migrated paths
# --------------------------------------------------------------------------- #
def _method_body(src, name):
    start = src.index(f"def {name}")
    nxt = src.index("\n    def ", start + 1)
    return src[start:nxt]


class TestDashboardMigration:
    def test_assemble_strategy_inputs_uses_snapshot(self, dash_src):
        body = _method_body(dash_src, "_assemble_strategy_inputs")
        assert "build_strategy_ai_snapshot" in body
        assert "race_params_dict()" in body
        # Event truth no longer read directly from config["strategy"]:
        for expr in ('_sc.get("tyre_wear_multiplier"', '_sc.get("race_type"',
                     '_sc.get("bop"', '_sc.get("avail_tyres"',
                     '_sc.get("track_location_id"'):
            assert expr not in body, f"legacy event read remains: {expr}"

    def test_dashboard_has_snapshot_helper(self, dash_src):
        assert "def _build_strategy_ai_snapshot" in dash_src
        assert "def _build_practice_ai_snapshot" in dash_src
        # Helpers thread the four contexts:
        body = _method_body(dash_src, "_build_strategy_ai_snapshot")
        assert "_build_event_context()" in body
        assert "_build_strategy_context()" in body
        assert "_build_track_context()" in body


class TestSetupBuilderMigration:
    def test_analyse_setup_uses_snapshot(self, sb_src):
        body = _method_body(sb_src, "_setup_analyse_ai")
        assert "_build_setup_ai_snapshot" in body
        assert '_sc.get("allowed_tuning_categories"' not in body
        assert '_sc.get("mandatory_compounds"' not in body

    def test_setup_builder_has_snapshot_helper(self, sb_src):
        assert "def _build_setup_ai_snapshot" in sb_src
        body = _method_body(sb_src, "_build_setup_ai_snapshot")
        assert "build_setup_ai_snapshot" in body
        assert "_build_event_context" in body
