"""Group 62 — ABS Regulation (no-ABS awareness): Acceptance Tests

Covers all acceptance criteria from the approved user story:
  AC1    — ABS allowed default True; True = zero behaviour change
  AC2/9  — EventContext.abs_allowed field, defaults, resolution, change_hash, summary displays
  AC3    — driving_advisor injects no_abs into diagnosis; composes with tyre_wear_high
  AC4/5  — NoABS1 rule fires/blocked; A5 safety invariant unaffected; no brake_bias in NoABS pack
  AC6    — _get_event_context_block emits no-ABS line only when ABS disabled
  AC7    — engine _check_no_abs_brake_cue: ease/clean/no-fire/zero-lap-guard/pit-reset
  AC8    — RaceStrategyEvidence.no_abs informational; ABS_DISABLED_LOCKUP_RISK in missing_evidence;
           evidence_confidence unaffected by no_abs
  AC9    — EventContext summary shows "ABS: OFF" when disabled
  AC10   — Pure modules; no regression (source scans)
  Edges  — old configs default True; cue graceful on zero laps; no_abs + tyre_wear_high compose;
           lsd_decel delta positive; lockups reset on pit exit; no brake_bias front rule

All tests are pure/offline — no PyQt6, no DB, no network.
"""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# ---------------------------------------------------------------------------
# Imports
# ---------------------------------------------------------------------------
from data.event_context import (
    EVENT_CONTEXT_SCHEMA,
    EventContext,
    EventContextSource,
    build_event_context,
    empty_event_context,
)
from strategy.race_strategy_evidence import (
    ABS_DISABLED_LOCKUP_RISK,
    MISSING_EVIDENCE_TEXT,
    RaceStrategyEvidence,
    StrategyConfidence,
    build_strategy_evidence,
)
from strategy.setup_knowledge_base import (
    _PACK_NOABS,
    get_all_rules,
    resolve_delta,
)
from strategy.setup_rule_engine import run_rule_engine, SetupPlan
from strategy.setup_driver_profile import build_driver_profile
from strategy.setup_ranges import resolve_ranges
from strategy.engine import RaceStrategyEngine, Stint
from telemetry.state import Priority


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _db_event(**override):
    """Minimal DB event record. No 'abs' key by default (simulates pre-Group-62 records)."""
    d = {
        "id": 1,
        "name": "Test Event",
        "track": "Fuji Speedway",
        "race_type": "lap",
        "laps": 20,
        "duration_mins": 0,
        "tyre_wear": 3.0,
        "fuel_mult": 3.0,
        "refuel_rate_lps": 10.0,
        "mandatory_stops": 0,
        "bop": 0,
        "tuning": 1,
        "weather": "Clear",
        "damage": "None",
        "avail_tyres": ["RM"],
        "req_tyres": [],
        "allowed_tuning_categories": [],
    }
    d.update(override)
    return d


def _strategy_dict(**override):
    """Minimal config['strategy'] snapshot."""
    d = {
        "car": "Porsche 911 RSR (991) '17",
        "track": "Fuji Speedway",
        "race_type": "lap",
        "laps": 20,
        "total_laps": 20,
        "race_duration_minutes": 0,
        "tyre_wear_multiplier": 3,
        "fuel_mult": 3,
        "refuel_speed_lps": 10,
        "mandatory_stops": 0,
        "bop": False,
        "tuning": True,
        "weather": "Clear",
        "damage": "None",
        "avail_tyres": ["RM"],
        "required_tyres": [],
        "allowed_tuning_categories": [],
        "track_location_id": "fuji_speedway",
        "layout_id": "fuji_speedway__full_course",
    }
    d.update(override)
    return d


def _run_engine(diag: dict, setup: dict) -> SetupPlan:
    """Run the rule engine with a neutral driver profile and no restrictions."""
    ranges = resolve_ranges("")
    profile = build_driver_profile()
    return run_rule_engine(diag, setup, ranges, profile)


def _make_engine():
    """Build a RaceStrategyEngine with a single stub stint, ready for cue tests."""
    tracker = MagicMock()
    tracker.laps_recorded = 1
    tracker.best_lap_ms = 90000
    tracker.avg_fuel_per_lap = 3.0
    tracker.last_fuel = 30.0
    tracker.tyre_states = {}
    announcer = MagicMock()
    config = {"fuel": {"strategy": "balanced"}, "strategy": {}}
    bridge = MagicMock()
    engine = RaceStrategyEngine(tracker, announcer, config, bridge, db=None)
    stint = Stint(stint_num=1, laps=20, compound="RM",
                  ref_lap_ms=90000, pace_threshold_ms=3000)
    engine.set_plan([stint])
    engine._active = True
    return engine, announcer


def _make_record(lock_up_count: int = 0) -> SimpleNamespace:
    """Minimal LapStats-like record stub."""
    return SimpleNamespace(lock_up_count=lock_up_count, wheelspin_count=0,
                           oversteer_count=0, lap_time_ms=90000)


# ============================================================================
# AC1 — ABS allowed default True; True = zero behaviour change
# ============================================================================

class TestAC1AbsAllowedDefault:
    """AC1: abs_allowed defaults to True; True leaves all existing logic unchanged."""

    def test_abs_allowed_default_is_true_on_empty_context(self):
        ctx = empty_event_context()
        assert ctx.abs_allowed is True

    def test_abs_allowed_true_on_event_without_abs_key(self):
        """Pre-migration event record (no 'abs' key) must default abs_allowed=True."""
        ctx = build_event_context(event=_db_event())  # no abs key
        assert ctx.abs_allowed is True

    def test_no_abs_injection_false_when_event_has_no_abs_key(self):
        """When event has no abs key, the advisor injection logic must give no_abs=False."""
        event_ctx: dict = {}  # no "abs" key
        _abs_raw = event_ctx.get("abs")
        no_abs = not bool(_abs_raw if _abs_raw is not None else True)
        assert no_abs is False, "no abs key → default True → no_abs=False"

    def test_rule_engine_noabs1_does_not_fire_by_default(self):
        """When no_abs is absent, NoABS1 must not fire even with lockups."""
        diag = {"avg_lockups": 5.0, "driver_feel_flags": {}}
        plan = _run_engine(diag, {"lsd_decel": 20})
        noabs1 = [c for c in plan.proposed if c.rule_id == "NoABS1"]
        assert not noabs1, "NoABS1 must not fire when no_abs is absent"


# ============================================================================
# AC2/9 — EventContext.abs_allowed field
# ============================================================================

class TestAC2EventContextAbsAllowed:
    """AC2: EventContext has abs_allowed bool; DB-first; missing/None → True."""

    def test_abs_zero_in_event_gives_false(self):
        ctx = build_event_context(event=_db_event(abs=0))
        assert ctx.abs_allowed is False

    def test_abs_one_in_event_gives_true(self):
        ctx = build_event_context(event=_db_event(abs=1))
        assert ctx.abs_allowed is True

    def test_abs_none_in_event_gives_true(self):
        """abs=None treated as absent → default True."""
        ctx = build_event_context(event=_db_event(abs=None))
        assert ctx.abs_allowed is True

    def test_abs_missing_key_in_event_gives_true(self):
        ctx = build_event_context(event=_db_event())
        assert ctx.abs_allowed is True

    def test_abs_false_via_strategy_gives_false(self):
        ctx = build_event_context(strategy=_strategy_dict(abs=False))
        assert ctx.abs_allowed is False

    def test_abs_missing_in_strategy_gives_true(self):
        ctx = build_event_context(strategy=_strategy_dict())
        assert ctx.abs_allowed is True

    def test_db_event_abs_beats_stale_strategy_abs(self):
        """DB event with abs=1 takes precedence over strategy with abs=False."""
        ctx = build_event_context(event=_db_event(abs=1), strategy=_strategy_dict(abs=False))
        assert ctx.abs_allowed is True

    def test_change_hash_differs_when_abs_flips(self):
        ctx_on = build_event_context(event=_db_event(abs=1))
        ctx_off = build_event_context(event=_db_event(abs=0))
        assert ctx_on.change_hash != ctx_off.change_hash, (
            "change_hash must differ when abs_allowed changes"
        )

    def test_change_hash_stable_when_abs_unchanged(self):
        a = build_event_context(event=_db_event(abs=0))
        b = build_event_context(event=_db_event(abs=0))
        assert a.change_hash == b.change_hash

    def test_abs_allowed_included_in_change_hash(self):
        """Same event fields but different abs → different hash confirms abs is hashed."""
        hash_with_abs = build_event_context(event=_db_event(abs=1)).change_hash
        hash_without_abs = build_event_context(event=_db_event(abs=0)).change_hash
        assert hash_with_abs != hash_without_abs


class TestAC9Summary:
    """AC9: EventContext summary shows 'ABS: OFF' only when disabled."""

    def test_event_context_schema_is_v2(self):
        assert EVENT_CONTEXT_SCHEMA == "event_context_v2"

    def test_summary_line_shows_abs_off_when_disabled(self):
        ctx = build_event_context(event=_db_event(abs=0))
        assert "ABS: OFF" in ctx.summary_line()

    def test_summary_line_no_abs_text_when_allowed(self):
        ctx = build_event_context(event=_db_event(abs=1))
        assert "ABS: OFF" not in ctx.summary_line()

    def test_summary_line_no_abs_text_when_key_missing(self):
        ctx = build_event_context(event=_db_event())  # no abs key → default True
        assert "ABS: OFF" not in ctx.summary_line()

    def test_to_summary_lines_shows_abs_off_when_disabled(self):
        ctx = build_event_context(event=_db_event(abs=0))
        combined = "\n".join(ctx.to_summary_lines())
        assert "ABS: OFF" in combined

    def test_to_summary_lines_no_abs_text_when_allowed(self):
        ctx = build_event_context(event=_db_event(abs=1))
        combined = "\n".join(ctx.to_summary_lines())
        assert "ABS: OFF" not in combined


# ============================================================================
# AC3 — Driving advisor injects no_abs into diagnosis
# ============================================================================

class TestAC3DiagnosisInjection:
    """AC3: build_combined_setup_response injects no_abs via setdefault from event ctx.

    Verified by replicating the exact injection logic and by source scan.
    """

    @staticmethod
    def _inject(event_ctx: dict, pre_diagnosis: dict | None = None) -> dict:
        """Replicate the Group 62 injection from build_combined_setup_response."""
        diagnosis = dict(pre_diagnosis) if pre_diagnosis else {}
        _abs_raw = event_ctx.get("abs")
        diagnosis.setdefault("no_abs", not bool(_abs_raw if _abs_raw is not None else True))
        return diagnosis

    def test_abs_disabled_injects_no_abs_true(self):
        d = self._inject({"abs": 0})
        assert d["no_abs"] is True

    def test_abs_enabled_injects_no_abs_false(self):
        d = self._inject({"abs": 1})
        assert d["no_abs"] is False

    def test_absent_abs_key_injects_no_abs_false(self):
        """No abs key → default True → no_abs=False."""
        d = self._inject({})
        assert d["no_abs"] is False

    def test_abs_none_injects_no_abs_false(self):
        """abs=None treated as absent → no_abs=False."""
        d = self._inject({"abs": None})
        assert d["no_abs"] is False

    def test_no_abs_composes_with_tyre_wear_high(self):
        """no_abs and tyre_wear_high coexist correctly in the diagnosis."""
        d = self._inject({"abs": 0}, {"tyre_wear_high": True})
        assert d["no_abs"] is True
        assert d["tyre_wear_high"] is True

    def test_setdefault_does_not_override_pre_existing_no_abs(self):
        """setdefault semantics: pre-existing no_abs=False is not overwritten."""
        d = self._inject({"abs": 0}, {"no_abs": False})
        assert d["no_abs"] is False, "setdefault must not overwrite a pre-set no_abs"

    def test_source_scan_injection_code_in_driving_advisor(self):
        """Source scan: driving_advisor.py contains the Group 62 injection logic."""
        src = (ROOT / "strategy" / "driving_advisor.py").read_text(encoding="utf-8")
        assert "no_abs" in src
        assert "setdefault" in src
        assert "_abs_raw" in src, (
            "driving_advisor.py must contain the _abs_raw injection pattern"
        )


# ============================================================================
# AC4/5 — Rule engine: NoABS1 fires/blocked; A5 unaffected; no brake_bias front
# ============================================================================

class TestAC4NoABS1Rule:
    """AC4: NoABS1 fires on no_abs+lockups; blocked by entry_understeer;
    targets lsd_decel not brake_bias."""

    def _noabs1_proposed(self, plan: SetupPlan) -> list:
        return [c for c in plan.proposed if c.rule_id == "NoABS1"]

    def _noabs1_in_plan(self, plan: SetupPlan) -> list:
        return ([c for c in plan.proposed if c.rule_id == "NoABS1"] +
                [c for c in plan.rejected_candidates if c.rule_id == "NoABS1"])

    def test_noabs1_fires_on_no_abs_and_avg_lockups(self):
        """NoABS1 appears in proposed when no_abs=True and avg_lockups>0."""
        diag = {"no_abs": True, "avg_lockups": 3.0, "driver_feel_flags": {}}
        plan = _run_engine(diag, {"lsd_decel": 20})
        hits = self._noabs1_proposed(plan)
        assert hits, (
            "NoABS1 must be in proposed when no_abs=True + avg_lockups=3.0; "
            f"proposed: {[c.rule_id for c in plan.proposed]}"
        )

    def test_noabs1_proposes_lsd_decel(self):
        """NoABS1 must target lsd_decel (not brake_bias)."""
        diag = {"no_abs": True, "avg_lockups": 3.0, "driver_feel_flags": {}}
        plan = _run_engine(diag, {"lsd_decel": 20})
        hits = self._noabs1_proposed(plan)
        assert hits, "NoABS1 must fire"
        assert hits[0].field == "lsd_decel"

    def test_noabs1_proposes_positive_delta(self):
        """NoABS1 must raise lsd_decel (delta > 0)."""
        diag = {"no_abs": True, "avg_lockups": 3.0, "driver_feel_flags": {}}
        plan = _run_engine(diag, {"lsd_decel": 20})
        hits = self._noabs1_proposed(plan)
        assert hits and hits[0].delta > 0, (
            f"NoABS1 must raise lsd_decel (positive delta); got delta={hits[0].delta if hits else 'N/A'}"
        )

    def test_noabs1_fires_on_braking_instability(self):
        """NoABS1 fires via braking_instability flag (alternative __any__ path)."""
        diag = {
            "no_abs": True,
            "avg_lockups": 0,
            "driver_feel_flags": {"braking_instability": True},
        }
        plan = _run_engine(diag, {"lsd_decel": 20})
        hits = self._noabs1_proposed(plan)
        assert hits, (
            "NoABS1 must fire on braking_instability even with avg_lockups=0; "
            f"proposed: {[c.rule_id for c in plan.proposed]}"
        )

    def test_noabs1_blocked_by_entry_understeer(self):
        """NoABS1 must not fire when entry_understeer is present (contraindication)."""
        diag = {
            "no_abs": True,
            "avg_lockups": 3.0,
            "driver_feel_flags": {
                "braking_instability": True,
                "entry_understeer": True,
            },
        }
        plan = _run_engine(diag, {"lsd_decel": 20})
        hits = self._noabs1_proposed(plan)
        assert not hits, (
            "NoABS1 must be blocked when entry_understeer=True; "
            f"proposed: {[c.rule_id for c in plan.proposed]}"
        )

    def test_noabs1_does_not_fire_without_no_abs_key(self):
        """NoABS1 must not fire when no_abs is absent from the diagnosis."""
        diag = {"avg_lockups": 5.0, "driver_feel_flags": {"braking_instability": True}}
        plan = _run_engine(diag, {"lsd_decel": 20})
        assert not self._noabs1_in_plan(plan), (
            "NoABS1 must not fire when no_abs key is absent"
        )

    def test_noabs1_does_not_fire_when_no_abs_false(self):
        """NoABS1 must not fire when no_abs=False even with lockups."""
        diag = {
            "no_abs": False,
            "avg_lockups": 5.0,
            "driver_feel_flags": {"braking_instability": True},
        }
        plan = _run_engine(diag, {"lsd_decel": 20})
        assert not self._noabs1_in_plan(plan), (
            "NoABS1 must not fire when no_abs=False"
        )

    def test_pack_noabs_contains_noabs1(self):
        """_PACK_NOABS must contain exactly the NoABS1 rule."""
        ids = [r.rule_id for r in _PACK_NOABS]
        assert "NoABS1" in ids, f"_PACK_NOABS must contain NoABS1; got: {ids}"

    def test_pack_noabs_no_rule_targets_brake_bias(self):
        """AC4 contract: no rule in _PACK_NOABS targets brake_bias at all."""
        for rule in _PACK_NOABS:
            assert rule.field != "brake_bias", (
                f"NoABS pack rule {rule.rule_id} must not target brake_bias; "
                "AC4 requires LSD decel, not front bias adjustment"
            )

    def test_noabs1_delta_fn_is_increase_lsd_decel(self):
        """NoABS1 must use the increase_lsd_decel delta resolver (+2.0)."""
        noabs1 = next(r for r in _PACK_NOABS if r.rule_id == "NoABS1")
        assert noabs1.delta_fn == "increase_lsd_decel"
        delta = resolve_delta("increase_lsd_decel", {}, {}, {})
        assert delta == 2.0, f"increase_lsd_decel must return +2.0; got {delta}"

    def test_noabs1_registered_globally(self):
        """NoABS1 must be discoverable via get_all_rules()."""
        all_ids = [r.rule_id for r in get_all_rules()]
        assert "NoABS1" in all_ids, "NoABS1 must be registered in the global rule catalogue"


class TestAC4C2ContraindictedUnderNoAbs:
    """AC4 whole-system gap: C2_entry_brake_bias must not fire under no_abs=True;
    it must fire under no_abs=False (regression guard).

    C2 moves brake_bias forward (delta=-0.5 via brake_bias_front).
    NoABS1 raises lsd_decel (delta=+2.0).
    The production fix adds "no_abs": True to C2's contraindications.
    """

    # Diagnosis conditions that trigger both C2 and NoABS1 preconditions:
    #   C2  requires: driver_feel_flags.braking_instability=True AND avg_lockups > 0
    #   NoABS1 requires: no_abs=True AND (braking_instability OR avg_lockups)
    _BASE_SETUP = {"brake_bias": -2, "lsd_decel": 20}

    def _diag_no_abs_on(self) -> dict:
        return {
            "no_abs": True,
            "avg_lockups": 2.0,
            "driver_feel_flags": {"braking_instability": True},
        }

    def _diag_no_abs_off(self) -> dict:
        return {
            # no_abs key absent → default False in injection; C2 contraindication not triggered
            "avg_lockups": 2.0,
            "driver_feel_flags": {"braking_instability": True},
        }

    def test_c2_does_not_fire_under_no_abs(self):
        """C2 must NOT produce a front-direction brake_bias recommendation when no_abs=True."""
        plan = _run_engine(self._diag_no_abs_on(), self._BASE_SETUP)
        front_bias_hits = [
            c for c in plan.proposed
            if c.field == "brake_bias" and c.delta < 0
        ]
        assert not front_bias_hits, (
            "C2 must be contraindicated (not proposed) when no_abs=True; "
            f"proposed brake_bias changes: "
            f"{[(c.rule_id, c.field, c.delta) for c in plan.proposed if c.field == 'brake_bias']}"
        )

    def test_noabs1_fires_under_no_abs(self):
        """NoABS1 must propose lsd_decel increase when no_abs=True (same conditions as C2 test)."""
        plan = _run_engine(self._diag_no_abs_on(), self._BASE_SETUP)
        lsd_increase_hits = [
            c for c in plan.proposed
            if c.field == "lsd_decel" and c.delta > 0 and c.rule_id == "NoABS1"
        ]
        assert lsd_increase_hits, (
            "NoABS1 must be proposed (lsd_decel increase) when no_abs=True + braking_instability + lockups; "
            f"proposed: {[(c.rule_id, c.field, c.delta) for c in plan.proposed]}"
        )

    def test_c2_fires_under_abs_allowed(self):
        """C2 DOES propose brake_bias forward when no_abs is absent (ABS allowed) — regression guard."""
        plan = _run_engine(self._diag_no_abs_off(), self._BASE_SETUP)
        front_bias_hits = [
            c for c in plan.proposed
            if c.field == "brake_bias" and c.delta < 0
        ]
        assert front_bias_hits, (
            "C2 must fire (brake_bias forward) when no_abs is absent/False; "
            "this proves the contraindication is scoped to no-ABS only. "
            f"proposed: {[(c.rule_id, c.field, c.delta) for c in plan.proposed]}"
        )

    def test_c2_rule_id_in_front_bias_hit_under_abs_allowed(self):
        """Confirm the front-bias hit under ABS-allowed is specifically C2_entry_brake_bias."""
        plan = _run_engine(self._diag_no_abs_off(), self._BASE_SETUP)
        c2_hits = [
            c for c in plan.proposed
            if c.rule_id == "C2_entry_brake_bias"
        ]
        assert c2_hits, (
            "C2_entry_brake_bias must be in proposed when no_abs absent + braking_instability + lockups; "
            f"proposed: {[(c.rule_id, c.field, c.delta) for c in plan.proposed]}"
        )


class TestAC5InvariantUnaffected:
    """AC5: A5 (brake_bias rearward blocked) fires unchanged regardless of no_abs."""

    def test_a5_fires_in_rejected_candidates_under_no_abs_and_lockups(self):
        """A5 must be in rejected_candidates even when no_abs=True is also present."""
        diag = {
            "no_abs": True,
            "avg_lockups": 3.0,
            "driver_feel_flags": {"braking_instability": True},
        }
        plan = _run_engine(diag, {"brake_bias": -2, "lsd_decel": 20})
        a5_hits = [c for c in plan.rejected_candidates if c.rule_id == "A5"]
        assert a5_hits, (
            "A5 must still be in rejected_candidates when no_abs=True + lockups; "
            f"rejected: {[c.rule_id for c in plan.rejected_candidates]}"
        )

    def test_a5_fires_without_no_abs_as_baseline(self):
        """A5 baseline: fires on avg_lockups alone (independent of no_abs)."""
        diag = {"avg_lockups": 3.0, "driver_feel_flags": {}}
        plan = _run_engine(diag, {"brake_bias": -2})
        a5_hits = [c for c in plan.rejected_candidates if c.rule_id == "A5"]
        assert a5_hits, (
            "A5 must fire on avg_lockups>0 regardless of no_abs; "
            f"rejected: {[c.rule_id for c in plan.rejected_candidates]}"
        )

    def test_a5_field_is_brake_bias(self):
        """A5 protects brake_bias (not lsd_decel)."""
        diag = {"avg_lockups": 3.0, "driver_feel_flags": {}}
        plan = _run_engine(diag, {"brake_bias": -2})
        a5_hits = [c for c in plan.rejected_candidates if c.rule_id == "A5"]
        assert a5_hits and a5_hits[0].field == "brake_bias"


# ============================================================================
# AC6 — _get_event_context_block emits no-ABS line only when ABS disabled
# ============================================================================

import strategy.driving_advisor as _da


def _make_advisor_stub(event_ctx: dict) -> _da.DrivingAdvisor:
    """Build a minimal DrivingAdvisor stub for _get_event_context_block tests."""
    adv = _da.DrivingAdvisor.__new__(_da.DrivingAdvisor)
    adv._event_ctx = event_ctx
    adv._config = {"strategy": {}}
    return adv


class TestAC6EventContextBlock:
    """AC6: _get_event_context_block emits the no-ABS line only when abs is falsy."""

    def test_no_abs_line_present_when_abs_disabled(self):
        adv = _make_advisor_stub({"abs": 0, "name": "Test Event", "track": "Fuji"})
        block = adv._get_event_context_block()
        assert "ABS: DISABLED" in block, (
            f"block must contain 'ABS: DISABLED' when abs=0; got:\n{block!r}"
        )

    def test_no_abs_block_references_lsd_decel(self):
        """The no-ABS line must name LSD decel as the control method."""
        adv = _make_advisor_stub({"abs": 0, "name": "Test"})
        block = adv._get_event_context_block()
        assert "LSD decel" in block, (
            "no-ABS coaching block must reference 'LSD decel' as the control method"
        )

    def test_no_abs_block_contains_ease_brake_pressure(self):
        """The no-ABS line must contain the 'ease brake pressure' coaching phrase."""
        adv = _make_advisor_stub({"abs": 0, "name": "Test"})
        block = adv._get_event_context_block()
        assert "ease brake pressure" in block, (
            f"no-ABS block must mention 'ease brake pressure'; got:\n{block!r}"
        )

    def test_no_abs_block_absent_when_abs_enabled(self):
        adv = _make_advisor_stub({"abs": 1, "name": "Test"})
        block = adv._get_event_context_block()
        assert "ABS: DISABLED" not in block

    def test_no_abs_block_absent_when_abs_key_missing(self):
        """No abs key → block must not contain the no-ABS line."""
        adv = _make_advisor_stub({"name": "Test", "track": "Fuji"})
        block = adv._get_event_context_block()
        assert "ABS: DISABLED" not in block

    def test_no_abs_block_absent_when_ctx_empty(self):
        adv = _make_advisor_stub({})
        block = adv._get_event_context_block()
        assert block == "", "empty event ctx must return empty string"

    def test_no_abs_block_absent_for_abs_none(self):
        """abs=None is treated as absent — no no-ABS line emitted."""
        adv = _make_advisor_stub({"abs": None, "name": "Test"})
        block = adv._get_event_context_block()
        assert "ABS: DISABLED" not in block, (
            "abs=None must not emit the no-ABS line (treated as absent/default True)"
        )

    def test_no_abs_block_contains_threshold_braking(self):
        """The no-ABS coaching line must include the 'threshold braking' phrase (exact wording)."""
        adv = _make_advisor_stub({"abs": 0, "name": "Test"})
        block = adv._get_event_context_block()
        # Exact text from driving_advisor.py line ~2405:
        # "ABS: DISABLED — threshold braking required."
        assert "threshold braking" in block, (
            f"no-ABS block must contain 'threshold braking'; got:\n{block!r}"
        )

    def test_no_abs_block_contains_avoid_front_lock_up(self):
        """The no-ABS coaching line must include the 'Avoid front lock-up' phrase (exact wording)."""
        adv = _make_advisor_stub({"abs": 0, "name": "Test"})
        block = adv._get_event_context_block()
        # Exact text from driving_advisor.py line ~2407:
        # "Avoid front lock-up."
        assert "Avoid front lock-up" in block, (
            f"no-ABS block must contain 'Avoid front lock-up'; got:\n{block!r}"
        )


# ============================================================================
# AC7 — Engine no-ABS brake cue
# ============================================================================

class TestAC7NoAbsBrakeCue:
    """AC7: _check_no_abs_brake_cue fires correctly gated on _no_abs and _recent_lockups."""

    def test_set_abs_allowed_false_sets_no_abs_true(self):
        engine, _ = _make_engine()
        engine.set_abs_allowed(False)
        assert engine._no_abs is True

    def test_set_abs_allowed_true_sets_no_abs_false(self):
        engine, _ = _make_engine()
        engine.set_abs_allowed(True)
        assert engine._no_abs is False

    def test_ease_cue_on_high_avg_lockups(self):
        """Rising lockups → HIGH priority ease-pressure cue announced."""
        engine, announcer = _make_engine()
        engine.set_abs_allowed(False)
        # avg_of[2,3] = 2.5 ≥ 1 → "ease" path
        engine._recent_lockups = [2, 3, 4]
        engine._check_no_abs_brake_cue(_make_record())
        assert announcer.announce.called
        args = announcer.announce.call_args[0]
        msg, priority = args[0], args[1]
        assert "ease" in msg.lower() or "earlier" in msg.lower(), (
            f"ease cue msg must mention 'ease' or 'earlier'; got: {msg!r}"
        )
        assert priority == Priority.HIGH

    def test_ease_cue_when_latest_greater_than_prev(self):
        """latest > prev triggers ease cue even when avg < 1."""
        engine, announcer = _make_engine()
        engine.set_abs_allowed(False)
        # avg_of[0] = 0.0 (only 1 element → _roll_avg returns 0), latest=3, prev=0 → latest > prev
        engine._recent_lockups = [0, 3]
        engine._check_no_abs_brake_cue(_make_record())
        assert announcer.announce.called
        args = announcer.announce.call_args[0]
        assert args[1] == Priority.HIGH

    def test_clean_cue_on_zero_lockups(self):
        """All-zero lockups → MEDIUM priority clean/margin cue."""
        engine, announcer = _make_engine()
        engine.set_abs_allowed(False)
        engine._recent_lockups = [0, 0, 0]
        engine._check_no_abs_brake_cue(_make_record())
        assert announcer.announce.called
        args = announcer.announce.call_args[0]
        msg, priority = args[0], args[1]
        assert "margin" in msg.lower() or "pressure" in msg.lower(), (
            f"clean cue must mention 'margin' or 'pressure'; got: {msg!r}"
        )
        assert priority == Priority.MEDIUM

    def test_no_cue_when_abs_allowed(self):
        """ABS allowed → _no_abs=False → no cue announced."""
        engine, announcer = _make_engine()
        engine.set_abs_allowed(True)
        engine._recent_lockups = [5, 5, 5]
        engine._check_no_abs_brake_cue(_make_record())
        assert not announcer.announce.called

    def test_no_cue_on_zero_lap_baseline(self):
        """Empty _recent_lockups (zero-lap baseline guard) → no cue."""
        engine, announcer = _make_engine()
        engine.set_abs_allowed(False)
        engine._recent_lockups = []
        engine._check_no_abs_brake_cue(_make_record())
        assert not announcer.announce.called, (
            "zero-lap baseline guard must prevent any cue announcement"
        )

    def test_pit_exit_clears_recent_lockups(self):
        """_on_pit_exit must reset _recent_lockups to [] for the new stint."""
        engine, _ = _make_engine()
        engine._recent_lockups = [3, 5, 2]
        engine._on_pit_exit({})
        assert engine._recent_lockups == [], (
            f"_recent_lockups must be cleared on pit exit; got {engine._recent_lockups!r}"
        )

    def test_after_pit_exit_no_cue_fires_on_empty_window(self):
        """After pit exit clears lockups, _check_no_abs_brake_cue must not announce."""
        engine, announcer = _make_engine()
        engine.set_abs_allowed(False)
        engine._recent_lockups = [5, 5, 5]
        engine._on_pit_exit({})
        announcer.announce.reset_mock()   # discard any pit-exit announcement
        engine._check_no_abs_brake_cue(_make_record())
        assert not announcer.announce.called, (
            "no cue must fire immediately after pit exit (empty lockup window)"
        )

    def test_cue_dedupe_key_is_no_abs_brake_cue(self):
        """The cue must use dedupe key 'no_abs_brake_cue' with 60s cooldown."""
        engine, announcer = _make_engine()
        engine.set_abs_allowed(False)
        engine._recent_lockups = [3, 4, 5]
        engine._check_no_abs_brake_cue(_make_record())
        assert announcer.announce.called
        args = announcer.announce.call_args[0]
        dedupe_key = args[2]
        cooldown = args[3]
        assert dedupe_key == "no_abs_brake_cue", f"dedupe key must be 'no_abs_brake_cue'; got {dedupe_key!r}"
        assert cooldown == 60.0, f"cooldown must be 60.0s; got {cooldown}"


# ============================================================================
# AC8 — RaceStrategyEvidence no_abs is informational only
# ============================================================================

class TestAC8RaceStrategyEvidence:
    """AC8: no_abs adds ABS_DISABLED_LOCKUP_RISK to missing_evidence; confidence unchanged."""

    def test_no_abs_default_false_on_dataclass(self):
        ev = RaceStrategyEvidence()
        assert ev.no_abs is False

    def test_abs_disabled_lockup_risk_constant_value(self):
        assert ABS_DISABLED_LOCKUP_RISK == "abs_disabled_lockup_risk"

    def test_abs_disabled_lockup_risk_in_missing_evidence_text(self):
        assert ABS_DISABLED_LOCKUP_RISK in MISSING_EVIDENCE_TEXT, (
            "ABS_DISABLED_LOCKUP_RISK must have a human-readable entry in MISSING_EVIDENCE_TEXT"
        )

    def test_no_abs_true_adds_abs_disabled_lockup_risk_to_missing(self):
        ev = build_strategy_evidence(no_abs=True)
        assert ABS_DISABLED_LOCKUP_RISK in ev.missing_evidence

    def test_no_abs_false_does_not_add_abs_disabled_lockup_risk(self):
        ev = build_strategy_evidence(no_abs=False)
        assert ABS_DISABLED_LOCKUP_RISK not in ev.missing_evidence

    def test_evidence_confidence_unaffected_by_no_abs(self):
        """Identical inputs → identical confidence regardless of no_abs flag."""
        common = dict(
            lap_time_samples=[90.0, 90.1, 90.2, 90.3, 90.0],
            fuel_use_samples=[3.0, 3.1, 3.0],
            tyre_wear_samples=[0.01] * 8,
            fuel_multiplier=3.0,
            tyre_multiplier=3.0,
            refuel_rate_lps=10.0,
            pit_loss_seconds=30.0,
        )
        ev_abs_allowed = build_strategy_evidence(**common, no_abs=False)
        ev_abs_off     = build_strategy_evidence(**common, no_abs=True)
        assert ev_abs_allowed.evidence_confidence == ev_abs_off.evidence_confidence, (
            "evidence_confidence must be identical with or without no_abs=True"
        )

    def test_no_abs_true_only_adds_one_extra_missing_entry(self):
        """no_abs=True adds exactly ABS_DISABLED_LOCKUP_RISK and nothing else."""
        args = dict(lap_time_samples=[90.0, 90.1, 90.2])
        ev_off = build_strategy_evidence(**args, no_abs=False)
        ev_on  = build_strategy_evidence(**args, no_abs=True)
        extra = set(ev_on.missing_evidence) - set(ev_off.missing_evidence)
        assert extra == {ABS_DISABLED_LOCKUP_RISK}, (
            f"Only ABS_DISABLED_LOCKUP_RISK should be added; diff={extra}"
        )

    def test_no_abs_true_preserves_all_other_evidence_fields(self):
        """no_abs=True must not change lap_time_samples or any other evidence field."""
        args = dict(lap_time_samples=[90.0, 90.1, 90.2])
        ev_off = build_strategy_evidence(**args, no_abs=False)
        ev_on  = build_strategy_evidence(**args, no_abs=True)
        assert ev_off.lap_time_samples == ev_on.lap_time_samples
        assert ev_on.no_abs is True
        assert ev_off.no_abs is False

    def test_build_strategy_evidence_from_event_context_inversion(self):
        """build_strategy_evidence_from_event_context passes no_abs=not abs_allowed."""
        from strategy.race_strategy_from_session import build_strategy_evidence_from_event_context

        class _FakeEC:
            abs_allowed = False   # ABS disabled → no_abs=True
            track = "Fuji Speedway"
            layout_id = "fuji_speedway__full_course"
            laps = 20
            race_duration_minutes = 0
            is_lap_race = True
            is_timed = False
            fuel_multiplier = 3.0
            tyre_wear_multiplier = 3.0
            refuel_rate_lps = 10.0
            mandatory_stops = 0
            available_tyres = ("RM",)
            required_tyres = ()
            weather = "Clear"

        result = build_strategy_evidence_from_event_context(
            None, session_id=0, event_context=_FakeEC()
        )
        assert result.evidence.no_abs is True, (
            "build_strategy_evidence_from_event_context must pass no_abs=True when abs_allowed=False"
        )

    def test_build_strategy_evidence_from_event_context_abs_allowed(self):
        """abs_allowed=True → no_abs=False in evidence."""
        from strategy.race_strategy_from_session import build_strategy_evidence_from_event_context

        class _FakeEC:
            abs_allowed = True
            track = ""
            layout_id = ""
            laps = 0
            race_duration_minutes = 0
            is_lap_race = False
            is_timed = False
            fuel_multiplier = 0.0
            tyre_wear_multiplier = 0.0
            refuel_rate_lps = 0.0
            mandatory_stops = 0
            available_tyres = ()
            required_tyres = ()
            weather = ""

        result = build_strategy_evidence_from_event_context(
            None, session_id=0, event_context=_FakeEC()
        )
        assert result.evidence.no_abs is False


# ============================================================================
# Edge cases
# ============================================================================

class TestEdgeCases:
    """Edge cases from the acceptance criteria."""

    def test_old_event_dict_no_abs_key_defaults_true(self):
        """Pre-migration events without 'abs' key default to abs_allowed=True (AC1)."""
        old_event = {
            "id": 99, "name": "Legacy Event", "track": "Nürburgring",
            "race_type": "lap", "laps": 30,
            "tyre_wear": 2.0, "fuel_mult": 2.0,
            # deliberately no "abs" key
        }
        ctx = build_event_context(event=old_event)
        assert ctx.abs_allowed is True

    def test_cue_graceful_on_single_lap_with_lockups(self):
        """Single entry in _recent_lockups with lockups → ease cue still fires."""
        engine, announcer = _make_engine()
        engine.set_abs_allowed(False)
        engine._recent_lockups = [3]   # only one entry
        # avg_of([]) = 0.0, latest=3, prev=0 → latest > prev → ease
        engine._check_no_abs_brake_cue(_make_record())
        assert announcer.announce.called
        args = announcer.announce.call_args[0]
        assert args[1] == Priority.HIGH

    def test_cue_no_fire_on_zero_lap_baseline(self):
        """Zero-lap baseline must never fire a cue regardless of no_abs."""
        engine, announcer = _make_engine()
        engine.set_abs_allowed(False)
        engine._recent_lockups = []
        engine._check_no_abs_brake_cue(_make_record())
        assert not announcer.announce.called

    def test_no_abs_and_tyre_wear_high_compose_noabs1_fires(self):
        """NoABS1 fires even when tyre_wear_high=True (lsd_decel is not wear-tagged)."""
        diag = {
            "no_abs": True,
            "avg_lockups": 3.0,
            "tyre_wear_high": True,
            "driver_feel_flags": {},
        }
        plan = _run_engine(diag, {"lsd_decel": 20})
        hits = [c for c in plan.proposed if c.rule_id == "NoABS1"]
        assert hits, (
            "NoABS1 must still fire when tyre_wear_high=True (lsd_decel not wear-tagged)"
        )

    def test_lsd_decel_delta_positive(self):
        """increase_lsd_decel returns +2.0 (raises lsd_decel toward max, not lower)."""
        delta = resolve_delta("increase_lsd_decel", {}, {}, {})
        assert delta == 2.0

    def test_lsd_decel_from_noabs1_pack_is_increase(self):
        """The NoABS1 rule's delta is positive (+2.0), not negative."""
        noabs1 = next(r for r in _PACK_NOABS if r.rule_id == "NoABS1")
        delta = resolve_delta(noabs1.delta_fn, {}, {}, {})
        assert delta > 0, (
            f"NoABS1 delta must be positive (raises lsd_decel); got {delta}"
        )

    def test_no_rule_in_pack_noabs_moves_brake_bias_front(self):
        """Stored-profile front-bias override: no rule in _PACK_NOABS reinstates front bias."""
        for rule in _PACK_NOABS:
            if rule.field == "brake_bias":
                d = resolve_delta(rule.delta_fn, {}, {}, {})
                assert d >= 0, (
                    f"Rule {rule.rule_id} must not move brake_bias toward front (negative delta); "
                    f"got {d}"
                )

    def test_recent_lockups_reset_on_pit_exit(self):
        """_on_pit_exit always resets _recent_lockups regardless of stint state."""
        engine, _ = _make_engine()
        engine._recent_lockups = [1, 2, 3, 4, 5]
        engine._on_pit_exit({})
        assert engine._recent_lockups == []

    def test_abs_allowed_true_from_event_context_gives_no_abs_false(self):
        """abs_allowed=True → no_abs=False (correct inversion)."""
        ev = build_strategy_evidence(no_abs=not True)  # inversion of abs_allowed=True
        assert ev.no_abs is False
        assert ABS_DISABLED_LOCKUP_RISK not in ev.missing_evidence

    def test_abs_allowed_false_from_event_context_gives_no_abs_true(self):
        """abs_allowed=False → no_abs=True (correct inversion)."""
        ev = build_strategy_evidence(no_abs=not False)  # inversion of abs_allowed=False
        assert ev.no_abs is True
        assert ABS_DISABLED_LOCKUP_RISK in ev.missing_evidence


# ============================================================================
# AC10 — Pure modules; no regression (source scans)
# ============================================================================

class TestAC10Purity:
    """AC10: The new modules are pure (no PyQt6 imports in strategy/data files)."""

    def test_event_context_no_pyqt6(self):
        src = (ROOT / "data" / "event_context.py").read_text(encoding="utf-8")
        # Check for actual import lines, not docstring mentions
        import_lines = [l for l in src.splitlines() if l.strip().startswith("import") or l.strip().startswith("from")]
        assert not any("PyQt6" in line for line in import_lines), (
            "data/event_context.py must not import PyQt6"
        )

    def test_setup_knowledge_base_no_pyqt6(self):
        src = (ROOT / "strategy" / "setup_knowledge_base.py").read_text(encoding="utf-8")
        import_lines = [l for l in src.splitlines() if l.strip().startswith("import") or l.strip().startswith("from")]
        assert not any("PyQt6" in line for line in import_lines), (
            "strategy/setup_knowledge_base.py must not import PyQt6"
        )

    def test_race_strategy_evidence_no_pyqt6(self):
        src = (ROOT / "strategy" / "race_strategy_evidence.py").read_text(encoding="utf-8")
        import_lines = [l for l in src.splitlines() if l.strip().startswith("import") or l.strip().startswith("from")]
        assert not any("PyQt6" in line for line in import_lines), (
            "strategy/race_strategy_evidence.py must not import PyQt6"
        )

    def test_engine_abs_api_exported(self):
        """set_abs_allowed is a public method on RaceStrategyEngine."""
        engine, _ = _make_engine()
        assert hasattr(engine, "set_abs_allowed")
        assert callable(engine.set_abs_allowed)

    def test_event_context_schema_bumped_to_v2(self):
        """EVENT_CONTEXT_SCHEMA must be 'event_context_v2' (Group 62 bump)."""
        assert EVENT_CONTEXT_SCHEMA == "event_context_v2"
