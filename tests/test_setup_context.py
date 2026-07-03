"""State Consolidation 3 — SetupContext tests.

Pure unit tests of data/setup_context.py (no PyQt6, no DB) plus source-scans of
the setup_builder helper + migrated consumer. Mirrors tests/test_event_context.py
and tests/test_strategy_context.py.
"""

from pathlib import Path

import pytest

from data.event_context import build_event_context
from data.strategy_context import build_strategy_context, build_strategy_prompt_snapshot
from data.setup_context import (
    SETUP_CONTEXT_SCHEMA,
    SETUP_PROMPT_SNAPSHOT_SCHEMA,
    SetupChangeEntry,
    SetupContext,
    SetupContextSource,
    SetupContextValidationResult,
    SetupPromptSnapshot,
    SetupPurpose,
    build_setup_context,
    build_setup_prompt_snapshot,
    empty_setup_context,
    normalise_purpose,
    validate_setup_context,
    compute_change_hash,
)

ROOT = Path(__file__).parent.parent


@pytest.fixture(scope="module")
def setup_builder_src():
    return (ROOT / "ui" / "setup_builder_ui.py").read_text(encoding="utf-8")


# --------------------------------------------------------------------------- #
# Representative fixtures
# --------------------------------------------------------------------------- #
def db_event(**over):
    d = {
        "id": 7, "name": "NGR Porsche Cup Rd7", "track": "Fuji Speedway",
        "race_type": "timed", "laps": 25, "duration_mins": 50,
        "tyre_wear": 3.0, "fuel_mult": 3.0, "refuel_rate_lps": 12.0,
        "bop": 0, "tuning": 1,
    }
    d.update(over)
    return d


def strategy_dict(**over):
    d = {
        "car": "Porsche 911 RSR (991) '17", "track": "Fuji Speedway",
        "track_location_id": "fuji_speedway", "layout_id": "fuji_speedway__full_course",
        "config_id": "a1b2c3d4e5", "fuel_burn_per_lap": 2.85,
        "stops": [{"laps": 12, "compound": "RM"}, {"laps": 13, "compound": "RH"}],
    }
    d.update(over)
    return d


def setup_dict(**over):
    """A setup dict as produced by _current_setup_dict()."""
    d = {
        "setup_id": 5,
        "name": "Porsche 911 RSR (991) '17",
        "car": "Porsche 911 RSR (991) '17",
        "setup_label": "Q Fuji 1",
        "track": "Fuji Speedway",
        "setup_type": "Qualifying Setup",
        "config_id": "a1b2c3d4e5",
        "ride_height_front": 80, "ride_height_rear": 82,
        "springs_front": 3.50, "springs_rear": 3.00,
        "arb_front": 5, "arb_rear": 4,
        "aero_front": 250, "aero_rear": 300,
        "gear_ratios": [3.1, 2.2, 1.7, 1.3, 1.0, 0.85],
        "captured_at": "2026-07-03 10:00",
    }
    d.update(over)
    return d


def ai_recommendation(**over):
    """An AI setup-advice response dict."""
    d = {
        "analysis": "Front is floaty on entry; add front bite.",
        "changes": [
            {"setting": "Front ARB", "field": "arb_front", "from": "5", "to": "7",
             "why": "more front bite"},
            {"setting": "Rear Wing", "field": "aero_rear", "from": "300", "to": "320",
             "why": "stabilise platform"},
        ],
        "setup_fields": {"arb_front": 7, "aero_rear": 320},
        "validation_errors": [],
        "primary_issue": "floaty_front",
        "confidence": "high",
    }
    d.update(over)
    return d


def make_event():
    return build_event_context(event=db_event(), strategy=strategy_dict())


def make_strategy_snapshot(event_context=None):
    ev = event_context or make_event()
    sc = build_strategy_context(strategy=strategy_dict(), event_context=ev)
    return build_strategy_prompt_snapshot(sc, ev)


# --------------------------------------------------------------------------- #
# normalise_purpose
# --------------------------------------------------------------------------- #
class TestNormalisePurpose:
    def test_qualifying_variants(self):
        assert normalise_purpose("Qualifying Setup") == SetupPurpose.QUALIFYING
        assert normalise_purpose("qual") == SetupPurpose.QUALIFYING
        assert normalise_purpose("build_qual") == SetupPurpose.QUALIFYING

    def test_race_variants(self):
        assert normalise_purpose("Race Setup") == SetupPurpose.RACE
        assert normalise_purpose("build_race") == SetupPurpose.RACE

    def test_practice_and_test(self):
        assert normalise_purpose("practice") == SetupPurpose.PRACTICE
        assert normalise_purpose("test") == SetupPurpose.TEST

    def test_unknown_and_empty(self):
        assert normalise_purpose("") == SetupPurpose.UNKNOWN
        assert normalise_purpose(None) == SetupPurpose.UNKNOWN
        assert normalise_purpose("something") == SetupPurpose.UNKNOWN

    def test_passthrough_enum(self):
        assert normalise_purpose(SetupPurpose.RACE) == SetupPurpose.RACE

    def test_never_raises_on_garbage(self):
        assert normalise_purpose(12345) == SetupPurpose.UNKNOWN
        assert normalise_purpose([1, 2]) == SetupPurpose.UNKNOWN


# --------------------------------------------------------------------------- #
# Build sources
# --------------------------------------------------------------------------- #
class TestBuildSources:
    def test_empty(self):
        ctx = build_setup_context()
        assert ctx.source == SetupContextSource.EMPTY
        assert ctx.has_active_setup is False
        assert ctx.change_hash == ""
        assert empty_setup_context().source == SetupContextSource.EMPTY

    def test_saved_db_when_setup_id_present(self):
        ctx = build_setup_context(setup=setup_dict())
        assert ctx.source == SetupContextSource.SAVED_DB
        assert ctx.has_active_setup

    def test_manual_when_no_setup_id(self):
        s = setup_dict()
        del s["setup_id"]
        ctx = build_setup_context(setup=s)
        assert ctx.source == SetupContextSource.MANUAL

    def test_ai_when_recommendation_present(self):
        ctx = build_setup_context(setup=setup_dict(), recommendation=ai_recommendation())
        assert ctx.source == SetupContextSource.AI
        assert ctx.has_recommendation

    def test_explicit_source_override(self):
        ctx = build_setup_context(setup=setup_dict(),
                                  source=SetupContextSource.LEGACY_CONFIG)
        assert ctx.source == SetupContextSource.LEGACY_CONFIG

    def test_generated_source_override(self):
        ctx = build_setup_context(setup=setup_dict(), recommendation=ai_recommendation(),
                                  source=SetupContextSource.GENERATED)
        assert ctx.source == SetupContextSource.GENERATED


# --------------------------------------------------------------------------- #
# Setup fields preserved
# --------------------------------------------------------------------------- #
class TestSetupFieldsPreserved:
    def test_identity_fields(self):
        ctx = build_setup_context(setup=setup_dict())
        assert ctx.setup_id == 5
        assert ctx.config_id == "a1b2c3d4e5"
        assert ctx.setup_label == "Q Fuji 1"
        assert ctx.car == "Porsche 911 RSR (991) '17"
        assert ctx.track == "Fuji Speedway"

    def test_purpose_from_setup_type(self):
        assert build_setup_context(setup=setup_dict()).purpose == SetupPurpose.QUALIFYING
        assert build_setup_context(
            setup=setup_dict(setup_type="Race Setup")).purpose == SetupPurpose.RACE

    def test_adjustments_parsed(self):
        ctx = build_setup_context(setup=setup_dict(), recommendation=ai_recommendation())
        assert len(ctx.adjustments) == 2
        assert all(isinstance(a, SetupChangeEntry) for a in ctx.adjustments)
        assert ctx.adjustments[0].field == "arb_front"
        assert ctx.adjustments[0].from_value == "5"
        assert ctx.adjustments[0].to_value == "7"
        assert ctx.adjustments[0].why == "more front bite"

    def test_changed_fields_union_of_changes_and_target(self):
        ctx = build_setup_context(setup=setup_dict(), recommendation=ai_recommendation())
        assert set(ctx.changed_fields) == {"arb_front", "aero_rear"}

    def test_target_and_baseline_setup(self):
        ctx = build_setup_context(setup=setup_dict(), recommendation=ai_recommendation())
        assert ctx.target_setup_dict() == {"arb_front": 7, "aero_rear": 320}
        base = ctx.baseline_setup_dict()
        assert base["ride_height_front"] == 80
        assert base["gear_ratios"] == [3.1, 2.2, 1.7, 1.3, 1.0, 0.85]

    def test_reason_confidence_primary_issue(self):
        ctx = build_setup_context(setup=setup_dict(), recommendation=ai_recommendation())
        assert "floaty" in ctx.reason_summary.lower()
        assert ctx.primary_issue == "floaty_front"
        assert ctx.confidence == "high"

    def test_validation_warnings_from_response(self):
        rec = ai_recommendation(validation_errors=["arb_front out of range", "locked field"])
        ctx = build_setup_context(setup=setup_dict(), recommendation=rec)
        assert ctx.validation_warnings == ("arb_front out of range", "locked field")

    def test_applied_flag(self):
        ctx = build_setup_context(setup=setup_dict(), applied=True)
        assert ctx.applied is True

    def test_purpose_explicit_override(self):
        ctx = build_setup_context(setup=setup_dict(setup_type="Race Setup"),
                                  purpose="qualifying")
        assert ctx.purpose == SetupPurpose.QUALIFYING


# --------------------------------------------------------------------------- #
# Ownership boundary — SetupContext must NOT own event/strategy state
# --------------------------------------------------------------------------- #
class TestOwnershipBoundary:
    def test_no_event_race_fields(self):
        ctx = build_setup_context(setup=setup_dict(), event_context=make_event())
        forbidden = [
            "race_type", "laps", "race_duration_minutes", "tyre_wear_multiplier",
            "fuel_multiplier", "refuel_rate_lps", "bop_enabled", "tuning_allowed",
            "allowed_tuning_categories",
        ]
        for name in forbidden:
            assert not hasattr(ctx, name), f"SetupContext must not own event field {name!r}"

    def test_no_strategy_plan_fields(self):
        ctx = build_setup_context(setup=setup_dict(),
                                  strategy_snapshot=make_strategy_snapshot())
        forbidden = ["stint_plan", "planned_stops", "fuel_burn_per_lap", "pit_laps"]
        for name in forbidden:
            assert not hasattr(ctx, name), f"SetupContext must not own strategy field {name!r}"

    def test_event_read_via_change_hash_only(self):
        ev = make_event()
        ctx = build_setup_context(setup=setup_dict(), event_context=ev)
        assert ctx.event_change_hash == ev.change_hash
        assert ctx.event_change_hash != ""

    def test_strategy_read_via_snapshot_id_only(self):
        snap = make_strategy_snapshot()
        ctx = build_setup_context(setup=setup_dict(), strategy_snapshot=snap)
        assert ctx.strategy_snapshot_id == snap.snapshot_id
        assert ctx.strategy_snapshot_id != ""

    def test_to_dict_has_no_event_or_strategy_plan_fields(self):
        d = build_setup_context(setup=setup_dict(), event_context=make_event(),
                                strategy_snapshot=make_strategy_snapshot()).to_dict()
        for k in ("race_type", "tyre_wear_multiplier", "stint_plan", "fuel_burn_per_lap"):
            assert k not in d


# --------------------------------------------------------------------------- #
# Purpose distinction — qualifying vs race
# --------------------------------------------------------------------------- #
class TestPurposeDistinction:
    def test_qualifying_and_race_distinguishable(self):
        q = build_setup_context(setup=setup_dict(setup_type="Qualifying Setup"))
        r = build_setup_context(setup=setup_dict(setup_type="Race Setup"))
        assert q.purpose == SetupPurpose.QUALIFYING
        assert r.purpose == SetupPurpose.RACE
        assert q.purpose != r.purpose
        assert q.change_hash != r.change_hash

    def test_matches_purpose(self):
        q = build_setup_context(setup=setup_dict(setup_type="Qualifying Setup"))
        assert q.matches_purpose("Qualifying Setup") is True
        assert q.matches_purpose("qualifying") is True
        assert q.matches_purpose("Race Setup") is False


# --------------------------------------------------------------------------- #
# Keying / staleness
# --------------------------------------------------------------------------- #
class TestKeyingAndStaleness:
    def test_matches_event(self):
        ev = make_event()
        ctx = build_setup_context(setup=setup_dict(), event_context=ev)
        assert ctx.matches_event(ev) is True

    def test_stale_when_event_change_hash_changes(self):
        ev1 = build_event_context(event=db_event(laps=25), strategy=strategy_dict())
        ev2 = build_event_context(event=db_event(laps=30), strategy=strategy_dict())
        ctx = build_setup_context(setup=setup_dict(), event_context=ev1)
        assert ctx.is_stale_for_event(ev1) is False
        assert ctx.is_stale_for_event(ev2) is True
        assert ctx.matches_event(ev2) is False

    def test_stale_when_strategy_snapshot_id_changes(self):
        ev = make_event()
        snap1 = make_strategy_snapshot(ev)
        # A different strategy → different snapshot id
        sc2 = build_strategy_context(strategy=strategy_dict(fuel_burn_per_lap=9.9),
                                     event_context=ev)
        snap2 = build_strategy_prompt_snapshot(sc2, ev)
        ctx = build_setup_context(setup=setup_dict(), strategy_snapshot=snap1)
        assert ctx.is_stale_for_strategy(snap1) is False
        assert ctx.is_stale_for_strategy(snap2) is True

    def test_empty_context_never_stale(self):
        ctx = empty_setup_context()
        assert ctx.is_stale_for_event(make_event()) is False
        assert ctx.is_stale_for_strategy(make_strategy_snapshot()) is False

    def test_missing_identity(self):
        s = setup_dict()
        del s["car"]
        del s["name"]
        ctx = build_setup_context(setup=s)
        assert ctx.is_missing_identity() is True

    def test_setup_change_hash_changes_when_recommendation_changes(self):
        a = build_setup_context(setup=setup_dict(), recommendation=ai_recommendation())
        b = build_setup_context(setup=setup_dict(),
                                recommendation=ai_recommendation(
                                    setup_fields={"arb_front": 9}))
        assert a.change_hash != b.change_hash

    def test_setup_change_hash_ignores_event_and_strategy(self):
        # Same setup+recommendation, different event/strategy → same setup hash
        # (event/strategy tracked via their own hashes, not the setup hash).
        ev1 = build_event_context(event=db_event(laps=25), strategy=strategy_dict())
        ev2 = build_event_context(event=db_event(laps=30), strategy=strategy_dict())
        a = build_setup_context(setup=setup_dict(), recommendation=ai_recommendation(),
                                event_context=ev1)
        b = build_setup_context(setup=setup_dict(), recommendation=ai_recommendation(),
                                event_context=ev2)
        assert a.change_hash == b.change_hash
        assert a.event_change_hash != b.event_change_hash

    def test_telemetry_diagnosis_hash_changes_with_diagnosis(self):
        a = build_setup_context(setup=setup_dict(), diagnosis={"dominant_problem": "understeer"})
        b = build_setup_context(setup=setup_dict(), diagnosis={"dominant_problem": "oversteer"})
        assert a.telemetry_diagnosis_hash != b.telemetry_diagnosis_hash
        assert a.telemetry_diagnosis_hash != ""

    def test_compute_change_hash_deterministic(self):
        f = {"a": 1, "b": [1, 2], "c": "x"}
        assert compute_change_hash(f) == compute_change_hash(dict(f))
        assert len(compute_change_hash(f)) == 12

    def test_identical_state_same_hash(self):
        a = build_setup_context(setup=setup_dict(), recommendation=ai_recommendation())
        b = build_setup_context(setup=setup_dict(), recommendation=ai_recommendation())
        assert a.change_hash == b.change_hash


# --------------------------------------------------------------------------- #
# Robustness — malformed / missing fields never crash
# --------------------------------------------------------------------------- #
class TestRobustness:
    def test_garbage_setup_does_not_crash(self):
        ctx = build_setup_context(setup="not a dict", recommendation=123)
        assert isinstance(ctx, SetupContext)
        assert ctx.source == SetupContextSource.EMPTY

    def test_malformed_changes_skipped(self):
        rec = ai_recommendation(changes=[
            {"field": "arb_front", "from": "5", "to": "7"},
            "garbage", 42,
            {"from": "x", "to": "y"},  # no field/setting → skipped
        ])
        ctx = build_setup_context(setup=setup_dict(), recommendation=rec)
        assert len(ctx.adjustments) == 1
        assert ctx.adjustments[0].field == "arb_front"

    def test_none_everything_builds_empty(self):
        ctx = build_setup_context(setup=None, recommendation=None,
                                  event_context=None, strategy_snapshot=None,
                                  diagnosis=None)
        assert ctx.source == SetupContextSource.EMPTY

    def test_bad_setup_id_becomes_none(self):
        ctx = build_setup_context(setup=setup_dict(setup_id="notanumber"))
        assert ctx.setup_id is None

    def test_validate_never_raises_on_garbage(self):
        ctx = build_setup_context(setup={"setup_type": None, "car": None})
        res = validate_setup_context(ctx)
        assert isinstance(res, SetupContextValidationResult)


# --------------------------------------------------------------------------- #
# Validation — setup vs staleness separation
# --------------------------------------------------------------------------- #
class TestValidation:
    def test_empty_flagged(self):
        res = validate_setup_context(empty_setup_context())
        assert res.ok is False
        assert "setup" in res.setup_missing

    def test_missing_identity_warns_as_setup(self):
        s = setup_dict()
        del s["car"]; del s["name"]
        ctx = build_setup_context(setup=s)
        res = validate_setup_context(ctx)
        assert "car" in res.setup_missing
        assert any("car" in w.lower() for w in res.setup_warnings)

    def test_unknown_purpose_warns(self):
        ctx = build_setup_context(setup=setup_dict(setup_type="???"))
        res = validate_setup_context(ctx)
        assert "purpose" in res.setup_missing

    def test_fully_specified_ok(self):
        ctx = build_setup_context(setup=setup_dict(), event_context=make_event())
        res = validate_setup_context(ctx)
        assert res.ok, res.warnings

    def test_stale_event_reported_as_staleness_not_setup(self):
        ev1 = build_event_context(event=db_event(laps=25), strategy=strategy_dict())
        ev2 = build_event_context(event=db_event(laps=30), strategy=strategy_dict())
        ctx = build_setup_context(setup=setup_dict(), event_context=ev1)
        res = validate_setup_context(ctx, event_context=ev2)
        assert any("stale" in w.lower() for w in res.staleness_warnings)
        assert res.setup_warnings == ()  # the setup itself is fine
        assert not res.ok

    def test_stale_strategy_reported_as_staleness(self):
        ev = make_event()
        snap1 = make_strategy_snapshot(ev)
        sc2 = build_strategy_context(strategy=strategy_dict(fuel_burn_per_lap=9.9),
                                     event_context=ev)
        snap2 = build_strategy_prompt_snapshot(sc2, ev)
        ctx = build_setup_context(setup=setup_dict(), strategy_snapshot=snap1)
        res = validate_setup_context(ctx, strategy_snapshot=snap2)
        assert any("strategy" in w.lower() for w in res.staleness_warnings)

    def test_purpose_mismatch_reported(self):
        ctx = build_setup_context(setup=setup_dict(setup_type="Qualifying Setup"))
        res = validate_setup_context(ctx, requested_purpose="Race Setup")
        assert any("race" in w.lower() for w in res.staleness_warnings)

    def test_warnings_property_concatenates(self):
        s = setup_dict()
        del s["car"]; del s["name"]
        ev2 = build_event_context(event=db_event(laps=99), strategy=strategy_dict())
        ctx = build_setup_context(setup=s, event_context=make_event())
        res = validate_setup_context(ctx, event_context=ev2)
        assert set(res.warnings) >= set(res.setup_warnings)
        assert set(res.warnings) >= set(res.staleness_warnings)


# --------------------------------------------------------------------------- #
# Frozen prompt snapshot
# --------------------------------------------------------------------------- #
class TestPromptSnapshot:
    def test_snapshot_combines_setup_event_strategy_keys(self):
        ev = make_event()
        snap = make_strategy_snapshot(ev)
        ctx = build_setup_context(setup=setup_dict(), recommendation=ai_recommendation(),
                                  event_context=ev, strategy_snapshot=snap)
        ps = build_setup_prompt_snapshot(ctx)
        assert isinstance(ps, SetupPromptSnapshot)
        assert ps.schema == SETUP_PROMPT_SNAPSHOT_SCHEMA
        assert ps.event_change_hash == ev.change_hash
        assert ps.strategy_snapshot_id == snap.snapshot_id
        assert ps.setup_change_hash == ctx.change_hash
        assert ps.purpose == "qualifying"
        assert ps.target_setup_dict() == {"arb_front": 7, "aero_rear": 320}

    def test_snapshot_id_stable_for_same_state(self):
        ctx = build_setup_context(setup=setup_dict(), recommendation=ai_recommendation(),
                                  event_context=make_event())
        a = build_setup_prompt_snapshot(ctx)
        b = build_setup_prompt_snapshot(ctx)
        assert a.snapshot_id == b.snapshot_id

    def test_snapshot_frozen_after_legacy_mutation(self):
        s = setup_dict()
        rec = ai_recommendation()
        ctx = build_setup_context(setup=s, recommendation=rec)
        ps = build_setup_prompt_snapshot(ctx)
        before_target = ps.target_setup_dict()
        before_base = ps.baseline_setup_dict()
        before_adj = tuple(a.to_dict() for a in ps.adjustments)
        # Mutate the source dicts in place afterwards.
        s["ride_height_front"] = 999
        s["gear_ratios"].append(9.9)
        rec["setup_fields"]["arb_front"] = 111
        rec["changes"][0]["to"] = "HACKED"
        assert ps.target_setup_dict() == before_target
        assert ps.baseline_setup_dict() == before_base
        assert tuple(a.to_dict() for a in ps.adjustments) == before_adj

    def test_snapshot_id_changes_when_event_changes(self):
        ev1 = build_event_context(event=db_event(laps=25), strategy=strategy_dict())
        ev2 = build_event_context(event=db_event(laps=30), strategy=strategy_dict())
        a = build_setup_prompt_snapshot(build_setup_context(setup=setup_dict(), event_context=ev1))
        b = build_setup_prompt_snapshot(build_setup_context(setup=setup_dict(), event_context=ev2))
        assert a.snapshot_id != b.snapshot_id

    def test_snapshot_id_changes_when_setup_changes(self):
        a = build_setup_prompt_snapshot(build_setup_context(setup=setup_dict()))
        b = build_setup_prompt_snapshot(
            build_setup_context(setup=setup_dict(setup_label="Different")))
        assert a.snapshot_id != b.snapshot_id

    def test_snapshot_to_dict(self):
        ctx = build_setup_context(setup=setup_dict(), recommendation=ai_recommendation())
        d = build_setup_prompt_snapshot(ctx).to_dict()
        assert d["schema"] == SETUP_PROMPT_SNAPSHOT_SCHEMA
        assert isinstance(d["adjustments"], list)
        assert d["adjustments"][0]["field"] == "arb_front"


# --------------------------------------------------------------------------- #
# Serialisation + immutability + legacy compatibility
# --------------------------------------------------------------------------- #
class TestSerialisationAndImmutability:
    def test_to_dict_shape(self):
        d = build_setup_context(setup=setup_dict(), recommendation=ai_recommendation()).to_dict()
        assert d["schema"] == SETUP_CONTEXT_SCHEMA
        assert d["source"] == "ai"
        assert d["purpose"] == "qualifying"
        assert isinstance(d["adjustments"], list)
        assert isinstance(d["changed_fields"], list)
        assert d["target_setup"] == {"arb_front": 7, "aero_rear": 320}

    def test_summary_line(self):
        line = build_setup_context(setup=setup_dict(),
                                   recommendation=ai_recommendation()).summary_line()
        assert "Q Fuji 1" in line
        assert "qualifying" in line

    def test_summary_line_empty(self):
        assert "No setup" in empty_setup_context().summary_line()

    def test_summary_lines(self):
        lines = build_setup_context(setup=setup_dict(),
                                    recommendation=ai_recommendation()).to_summary_lines()
        assert any("Adjustments" in l for l in lines)
        assert any("Primary issue" in l for l in lines)

    def test_frozen_immutable(self):
        ctx = build_setup_context(setup=setup_dict())
        with pytest.raises(Exception):
            ctx.setup_id = 999  # type: ignore[misc]

    def test_change_entry_frozen(self):
        ctx = build_setup_context(setup=setup_dict(), recommendation=ai_recommendation())
        with pytest.raises(Exception):
            ctx.adjustments[0].field = "hacked"  # type: ignore[misc]

    def test_legacy_setup_dict_still_builds(self):
        # A legacy config setup (no setup_id, "session" key instead of setup_type).
        legacy = {"name": "Car X", "session": "Qualifying", "ride_height_front": 70}
        ctx = build_setup_context(setup=legacy)
        assert ctx.has_active_setup
        assert ctx.purpose == SetupPurpose.QUALIFYING
        assert ctx.baseline_setup_dict()["ride_height_front"] == 70


# --------------------------------------------------------------------------- #
# Source-scan: the setup_builder helper + migrated consumer
# --------------------------------------------------------------------------- #
class TestSetupBuilderMigration:
    def test_has_build_setup_context_helper(self, setup_builder_src):
        assert "def _build_setup_context(self" in setup_builder_src
        assert "from data.setup_context import build_setup_context" in setup_builder_src

    def test_setup_type_prefix_uses_normalise_purpose(self, setup_builder_src):
        start = setup_builder_src.index("def _setup_type_prefix")
        nxt = setup_builder_src.index("\n    def ", start + 1)
        body = setup_builder_src[start:nxt]
        assert "normalise_purpose" in body
        assert "SetupPurpose.QUALIFYING" in body

    def test_display_result_captures_setup_context(self, setup_builder_src):
        start = setup_builder_src.index("def _display_setup_result")
        nxt = setup_builder_src.index("\n    def ", start + 1)
        body = setup_builder_src[start:nxt]
        assert "_build_setup_context(" in body
        assert "_last_setup_context" in body
