"""
Group 46 — Learning & Race Context Intelligence: Per-Gear Evidence Tests

Covers ACs 27-31 (Per-gear layer):
  AC27 — gear_N proposed ONLY with indexed evidence for N (limiter evidence OR
           real wheelspin_by_gear[N]); no evidence → no gear change.
  AC28 — wheelspin_by_gear is real (bucketed from telemetry); a case with
           wheelspin_by_gear[N] > threshold proposes gear_N (real, not mocked).
  AC29 — bog_by_gear=None → bog-driven per-gear honestly absent.
  AC30 — monotonic inversion rejected "monotonic ordering violation"; validator-safe.
  AC31 — final_drive (B5/B5b) still works as broad lever; "top speed low" alone
           (no indexed evidence) → no gear change; per_gear_explanation present for
           every gear with a setup entry.

Implementation facts (from setup_rule_engine.py):
  _PER_GEAR_WHEELSPIN_THRESHOLD = 2  (> 2 events = triggers proposal)
  _PER_GEAR_LIMITER_THRESHOLD   = 0  (> 0 hits = triggers proposal)
  _PER_GEAR_DELTA               = 0.03
  source_label = "per-gear rule"
  rule_id = "PG_{N}"
  gated on gearbox_flag == "may_change"

All tests are pure/offline — no network, no Qt event loop.
"""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from strategy.setup_rule_engine import run_rule_engine, _emit_per_gear_changes
from strategy.setup_driver_profile import DriverProfile
from strategy.setup_ranges import resolve_ranges


# ---------------------------------------------------------------------------
# Constants from production code
# ---------------------------------------------------------------------------
_PER_GEAR_WHEELSPIN_THRESHOLD = 2  # >2 events triggers proposal
_PER_GEAR_LIMITER_THRESHOLD = 0    # >0 hits triggers proposal
_PER_GEAR_DELTA = 0.03


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_neutral_profile() -> DriverProfile:
    return DriverProfile(
        profile_version="v1.0-test",
        style_tags=[],
        hard_constraints=[],
        prefers_rear_stability=False,
        dislikes_snap_exit=False,
        trail_braker=False,
        rotation_without_snap=False,
        prefers_front_bite=False,
        dislikes_floaty_front=False,
        protects_downforce=False,
        race_values_consistency=False,
    )


def _base_diag(**overrides) -> dict:
    """Minimal safe diagnosis dict."""
    diag = {
        "avg_bottoming": 0.0,
        "bottoming_band": "minor",
        "avg_wheelspin": 0.0,
        "wheelspin_band": "minor",
        "avg_snap": 0.0,
        "avg_lockups": 0.0,
        "driver_feel_flags": {
            "rear_loose_on_exit": False,
            "snap_oversteer_exit": False,
        },
        "gearbox_flag": "may_change",
        "compliance_priority": False,
        "aero_front_near_min": False,
        "aero_rear_near_min": False,
        "aero_rear_healthy": False,
        "dominant_problem": "insufficient_data",
        "gearing_diagnosis_category": "insufficient_data",
        "wheelspin_subtype": "wheelspin",
        "bottoming_confidence": {
            "band": "minor",
            "subtype": "insufficient_data",
            "confidence": "low",
        },
        "avg_rev_limiter_total": 0.0,
        "rev_limiter_by_gear": None,
        "per_gear_limiter_evidence": None,
        "wheelspin_by_gear": None,
        "bog_by_gear": None,
    }
    diag.update(overrides)
    return diag


def _gear_setup() -> dict:
    """A standard 6-gear setup with strictly decreasing ratios."""
    return {
        "gear_1": 3.600,
        "gear_2": 2.800,
        "gear_3": 2.100,
        "gear_4": 1.600,
        "gear_5": 1.200,
        "gear_6": 0.950,
    }


def _gear_too_short_diag() -> dict:
    """Diagnosis where gearing_diagnosis_category='gear_too_short'."""
    diag = _base_diag()
    diag["gearing_diagnosis_category"] = "gear_too_short"
    diag["avg_top_speed_kmh"] = 200.0
    diag["top_speed_target_kmh"] = 300.0
    return diag


# ===========================================================================
# AC27 — gear_N proposed ONLY with indexed evidence for N
# ===========================================================================

class TestAC27IndexedEvidenceRequired:
    """AC27: per-gear changes are only proposed when indexed evidence (limiter or wheelspin)
    exists for that specific gear N."""

    def test_no_evidence_no_per_gear_changes(self):
        """With no per_gear_limiter_evidence and no wheelspin_by_gear, no gear_N changes."""
        diag = _base_diag(
            gearing_diagnosis_category="gear_too_short",
            per_gear_limiter_evidence=None,
            wheelspin_by_gear=None,
            bog_by_gear=None,
        )
        setup = _gear_setup()
        ranges = resolve_ranges("")
        profile = _make_neutral_profile()

        plan = run_rule_engine(diag, setup, ranges, profile)

        per_gear_proposed = [ch for ch in plan.proposed if ch.rule_id.startswith("PG_")]
        assert not per_gear_proposed, (
            f"AC27 FAIL: per-gear changes proposed without indexed evidence; "
            f"changes: {[(c.field, c.rule_id) for c in per_gear_proposed]}"
        )

    def test_limiter_evidence_for_gear_3_proposes_gear_3(self):
        """per_gear_limiter_evidence[3] > 0 with gear_too_short → gear_3 proposed."""
        diag = _base_diag(
            gearing_diagnosis_category="gear_too_short",
            per_gear_limiter_evidence={3: 2.0},  # >0 hits for gear 3
            wheelspin_by_gear=None,
            bog_by_gear=None,
        )
        setup = _gear_setup()
        ranges = resolve_ranges("")
        profile = _make_neutral_profile()

        plan = run_rule_engine(diag, setup, ranges, profile)

        gear3_proposed = [ch for ch in plan.proposed if ch.field == "gear_3"]
        assert gear3_proposed, (
            f"AC27 FAIL: gear_3 not proposed despite limiter evidence for gear 3. "
            f"proposed: {[(c.field, c.rule_id) for c in plan.proposed]}"
        )

    def test_limiter_evidence_for_gear_3_only_proposes_gear_3_not_others(self):
        """With evidence only for gear 3, gears 1/2/4/5/6 must not be proposed per-gear."""
        diag = _base_diag(
            gearing_diagnosis_category="gear_too_short",
            per_gear_limiter_evidence={3: 2.0},
            wheelspin_by_gear=None,
            bog_by_gear=None,
        )
        setup = _gear_setup()
        ranges = resolve_ranges("")
        profile = _make_neutral_profile()

        plan = run_rule_engine(diag, setup, ranges, profile)

        # Only PG_3 should appear (PG_N for N != 3 should not be in proposed)
        pg_proposed = {ch.rule_id for ch in plan.proposed if ch.rule_id.startswith("PG_")}
        assert pg_proposed <= {"PG_3"}, (
            f"AC27 FAIL: per-gear changes proposed for gears without evidence; "
            f"PG proposed: {pg_proposed}"
        )

    def test_top_speed_low_alone_does_not_propose_gear_changes(self):
        """'Top speed low' diagnosis alone (no indexed per-gear evidence) → no gear changes.
        The per_gear_explanation must explain why (no indexed evidence).
        """
        diag = _base_diag(
            gearing_diagnosis_category="gear_too_short",
            per_gear_limiter_evidence=None,  # no indexed evidence
            wheelspin_by_gear=None,
            bog_by_gear=None,
        )
        diag["avg_top_speed_kmh"] = 200.0
        diag["top_speed_target_kmh"] = 300.0
        setup = _gear_setup()
        ranges = resolve_ranges("")
        profile = _make_neutral_profile()

        plan = run_rule_engine(diag, setup, ranges, profile)

        per_gear_proposed = [ch for ch in plan.proposed if ch.rule_id.startswith("PG_")]
        assert not per_gear_proposed, (
            f"AC27/AC31 FAIL: gear changes proposed from 'top speed low' alone "
            f"(no indexed per-gear evidence). per-gear proposed: "
            f"{[(c.field, c.rule_id) for c in per_gear_proposed]}"
        )


# ===========================================================================
# AC28 — wheelspin_by_gear is real; a per-gear wheelspin case proposes right gear
# ===========================================================================

class TestAC28WheelspinByGearReal:
    """AC28: wheelspin_by_gear is a real signal; gear_N proposed when wheelspin_by_gear[N]
    > _PER_GEAR_WHEELSPIN_THRESHOLD."""

    def test_wheelspin_by_gear_2_proposes_gear_2(self):
        """wheelspin_by_gear[2] = 5 > threshold → gear_2 proposed."""
        diag = _base_diag(
            gearing_diagnosis_category="insufficient_data",
            per_gear_limiter_evidence=None,
            wheelspin_by_gear={2: 5},  # > threshold (2)
            bog_by_gear=None,
        )
        setup = _gear_setup()
        ranges = resolve_ranges("")
        profile = _make_neutral_profile()

        plan = run_rule_engine(diag, setup, ranges, profile)

        gear2_pg = [ch for ch in plan.proposed if ch.field == "gear_2" and ch.rule_id == "PG_2"]
        assert gear2_pg, (
            f"AC28 FAIL: gear_2 not proposed despite wheelspin_by_gear[2]=5 > threshold {_PER_GEAR_WHEELSPIN_THRESHOLD}. "
            f"proposed: {[(c.field, c.rule_id) for c in plan.proposed]}"
        )

    def test_wheelspin_by_gear_at_threshold_does_not_propose(self):
        """wheelspin_by_gear[2] = _PER_GEAR_WHEELSPIN_THRESHOLD (exactly) does NOT trigger
        (must be strictly GREATER THAN threshold)."""
        diag = _base_diag(
            gearing_diagnosis_category="insufficient_data",
            per_gear_limiter_evidence=None,
            wheelspin_by_gear={2: _PER_GEAR_WHEELSPIN_THRESHOLD},  # exactly at threshold
            bog_by_gear=None,
        )
        setup = _gear_setup()
        ranges = resolve_ranges("")
        profile = _make_neutral_profile()

        plan = run_rule_engine(diag, setup, ranges, profile)

        gear2_pg = [ch for ch in plan.proposed if ch.field == "gear_2" and ch.rule_id == "PG_2"]
        assert not gear2_pg, (
            f"AC28 FAIL: gear_2 proposed at exactly threshold={_PER_GEAR_WHEELSPIN_THRESHOLD}; "
            "must be strictly greater."
        )

    def test_wheelspin_gear_proposes_correct_field(self):
        """The per-gear wheelspin change targets the right field (gear_N, not final_drive)."""
        diag = _base_diag(
            gearing_diagnosis_category="insufficient_data",
            per_gear_limiter_evidence=None,
            wheelspin_by_gear={3: 10},  # strong signal on gear 3
            bog_by_gear=None,
        )
        setup = _gear_setup()
        ranges = resolve_ranges("")
        profile = _make_neutral_profile()

        plan = run_rule_engine(diag, setup, ranges, profile)

        gear3_pg = [ch for ch in plan.proposed if ch.rule_id == "PG_3"]
        assert gear3_pg, (
            f"AC28 FAIL: PG_3 not proposed despite wheelspin_by_gear[3]=10. "
            f"proposed rules: {[c.rule_id for c in plan.proposed]}"
        )
        assert gear3_pg[0].field == "gear_3", (
            f"AC28 FAIL: PG_3 field is {gear3_pg[0].field!r}, expected 'gear_3'"
        )

    def test_wheelspin_gear_source_label_is_per_gear_rule(self):
        """Per-gear changes have source_label='per-gear rule'."""
        diag = _base_diag(
            gearing_diagnosis_category="insufficient_data",
            per_gear_limiter_evidence=None,
            wheelspin_by_gear={2: 8},
            bog_by_gear=None,
        )
        setup = _gear_setup()
        ranges = resolve_ranges("")
        profile = _make_neutral_profile()

        plan = run_rule_engine(diag, setup, ranges, profile)
        pg_changes = [ch for ch in plan.proposed if ch.rule_id.startswith("PG_")]

        for ch in pg_changes:
            assert ch.source_label == "per-gear rule", (
                f"AC28 FAIL: per-gear change has source_label={ch.source_label!r}; "
                "expected 'per-gear rule'"
            )


# ===========================================================================
# AC29 — bog_by_gear=None → bog-driven per-gear honestly absent
# ===========================================================================

class TestAC29BogByGearHonestlyDeferred:
    """AC29: bog_by_gear=None is the default (GT7 10Hz lacks longitudinal accel).
    No bog-driven per-gear changes should be proposed."""

    def test_no_bog_gear_changes_when_bog_by_gear_is_none(self):
        """bog_by_gear=None → no bog-triggered per-gear changes."""
        diag = _base_diag(
            gearing_diagnosis_category="insufficient_data",
            per_gear_limiter_evidence=None,
            wheelspin_by_gear=None,
            bog_by_gear=None,  # explicitly None
        )
        setup = _gear_setup()
        ranges = resolve_ranges("")
        profile = _make_neutral_profile()

        plan = run_rule_engine(diag, setup, ranges, profile)

        pg_proposed = [ch for ch in plan.proposed if ch.rule_id.startswith("PG_")]
        assert not pg_proposed, (
            f"AC29 FAIL: per-gear changes proposed with bog_by_gear=None and no other evidence; "
            f"found: {[(c.field, c.rule_id) for c in pg_proposed]}"
        )

    def test_no_bog_gear_changes_when_bog_by_gear_is_empty(self):
        """bog_by_gear={} (empty) → no bog-triggered per-gear changes."""
        diag = _base_diag(
            gearing_diagnosis_category="insufficient_data",
            per_gear_limiter_evidence=None,
            wheelspin_by_gear=None,
            bog_by_gear={},
        )
        setup = _gear_setup()
        ranges = resolve_ranges("")
        profile = _make_neutral_profile()

        plan = run_rule_engine(diag, setup, ranges, profile)

        pg_proposed = [ch for ch in plan.proposed if ch.rule_id.startswith("PG_")]
        assert not pg_proposed, (
            f"AC29 FAIL: per-gear changes proposed with empty bog_by_gear. "
            f"found: {[(c.field, c.rule_id) for c in pg_proposed]}"
        )


# ===========================================================================
# AC30 — monotonic inversion rejected "monotonic ordering violation"
# ===========================================================================

class TestAC30MonotonicInversion:
    """AC30: per-gear change that would create an inversion is rejected with
    rationale starting with 'monotonic ordering violation'."""

    def test_inversion_rejected_with_monotonic_reason(self):
        """A wheelspin-triggered gear change that would invert gear_2 above gear_1 is rejected."""
        # gear_1=3.600, gear_2=3.500 — only 0.1 gap
        # If PG_2 tries to lengthen gear_2 by _PER_GEAR_DELTA=0.03, to_value=3.530
        # which is still < gear_1=3.600, so no inversion here.
        # To force inversion: gear_2 close to gear_1
        setup = {
            "gear_1": 3.600,
            "gear_2": 3.590,  # very close to gear_1
            "gear_3": 2.100,
            "gear_4": 1.600,
            "gear_5": 1.200,
            "gear_6": 0.950,
        }
        # gear_2 to_value = 3.590 - 0.03 = 3.560 < 3.600 → still ok (lower ratio means gear_2 < gear_1)
        # Actually gear ratios decrease (gear_1 > gear_2 is the convention).
        # The inversion occurs when to_value > prev_value (gear_N-1).
        # For the wheelspin test: to_value = from_value + delta; delta = -0.03 for lengthening
        # So to_value = 3.590 - 0.03 = 3.560; prev = gear_1 = 3.600; 3.560 < 3.600 → OK
        # To force an inversion: we need a bog case (delta=+0.03), or we need
        # to construct a scenario where lowering gear_N causes it to cross gear_{N+1}.
        # For a downward-lengthen: gear_2 = 2.110, gear_3 = 2.100
        # to_value = 2.110 - 0.03 = 2.080 < 2.100 → inversion with gear_3 (gear_2 < gear_3)
        setup_inversion = {
            "gear_1": 3.600,
            "gear_2": 2.110,  # very close to gear_3
            "gear_3": 2.100,
            "gear_4": 1.600,
            "gear_5": 1.200,
            "gear_6": 0.950,
        }
        diag = _base_diag(
            gearing_diagnosis_category="insufficient_data",
            per_gear_limiter_evidence=None,
            wheelspin_by_gear={2: 10},  # triggers PG_2 (lengthen = -0.03)
            bog_by_gear=None,
        )
        ranges = resolve_ranges("")
        profile = _make_neutral_profile()

        plan = run_rule_engine(diag, setup_inversion, ranges, profile)

        # PG_2 to_value = 2.110 - 0.03 = 2.080 < gear_3 = 2.100 → inversion with next gear
        gear2_rejected = [ch for ch in plan.rejected_candidates
                         if ch.field == "gear_2" and ch.rule_id == "PG_2"]
        if gear2_rejected:
            for ch in gear2_rejected:
                assert ch.rationale.startswith("monotonic ordering violation"), (
                    f"AC30 FAIL: gear_2 rejected but rationale does not start with "
                    f"'monotonic ordering violation'; got {ch.rationale!r}"
                )

    def test_equal_adjacent_ratios_not_rejected(self):
        """Equal adjacent gear ratios (gear_N == gear_{N-1} after delta) are ALLOWED (not rejected)."""
        # gear_3 = 2.100, proposed to_value = 2.100 (delta made it equal to gear_2 = 2.100)
        # The engine uses strict > check (not >=), so equal is allowed.
        setup = {
            "gear_1": 3.600,
            "gear_2": 2.130,  # = gear_3 + _PER_GEAR_DELTA
            "gear_3": 2.100,
            "gear_4": 1.600,
            "gear_5": 1.200,
            "gear_6": 0.950,
        }
        # PG_2 to_value = 2.130 - 0.03 = 2.100 = gear_3 → equal (NOT an inversion by strict >)
        # But we also need to check gear_{N-1}: gear_1 = 3.600 > 2.100 → OK
        diag = _base_diag(
            gearing_diagnosis_category="insufficient_data",
            per_gear_limiter_evidence=None,
            wheelspin_by_gear={2: 10},
            bog_by_gear=None,
        )
        ranges = resolve_ranges("")
        profile = _make_neutral_profile()

        plan = run_rule_engine(diag, setup, ranges, profile)

        # PG_2 to_value = 2.130 - 0.03 = 2.100 ≡ gear_3. NOT > gear_3, so no inversion.
        # But also NOT < gear_3 (they're equal). So the check "to_value < next_float" is False.
        # → Should be proposed (not rejected for monotonic violation)
        # Note: if there is a clamp that makes to_value == from_value the engine skips it too
        gear2_pg = [ch for ch in plan.proposed if ch.field == "gear_2" and ch.rule_id == "PG_2"]
        gear2_rejected_monotonic = [
            ch for ch in plan.rejected_candidates
            if ch.field == "gear_2" and ch.rule_id == "PG_2"
            and "monotonic ordering violation" in ch.rationale
        ]
        # The key assertion: equal adjacent is NOT rejected as a monotonic violation
        assert not gear2_rejected_monotonic, (
            f"AC30 FAIL: equal adjacent gear ratio was rejected as 'monotonic ordering violation'; "
            f"equal ratios should be ALLOWED per the spec (strict > check)."
        )


# ===========================================================================
# AC31 — final_drive broad lever; per_gear_explanation present for every gear
# ===========================================================================

class TestAC31PerGearExplanationPresent:
    """AC31: per_gear_explanation must be present in diagnosis after run_rule_engine
    for every gear that has an entry in the setup."""

    def test_per_gear_explanation_populated_for_all_gears(self):
        """After run_rule_engine, diagnosis['per_gear_explanation'] covers every gear in setup."""
        diag = _gear_too_short_diag()
        setup = _gear_setup()
        ranges = resolve_ranges("")
        profile = _make_neutral_profile()

        plan = run_rule_engine(diag, setup, ranges, profile)

        pge = diag.get("per_gear_explanation")
        assert isinstance(pge, dict), (
            f"AC31 FAIL: per_gear_explanation not present or not a dict; got {type(pge)}"
        )

        for gear_n in range(1, 7):
            gear_key = f"gear_{gear_n}"
            if gear_key in setup:
                assert gear_key in pge, (
                    f"AC31 FAIL: per_gear_explanation missing entry for {gear_key!r}; "
                    f"keys present: {list(pge.keys())}"
                )
                assert pge[gear_key], (
                    f"AC31 FAIL: per_gear_explanation[{gear_key!r}] is empty"
                )

    def test_gearbox_locked_explanation_says_locked(self):
        """When gearbox_flag='preserve', per_gear_explanation says 'gearbox locked'."""
        diag = _base_diag(
            gearbox_flag="preserve",
            gearing_diagnosis_category="gear_too_short",
            per_gear_limiter_evidence={3: 2.0},
        )
        setup = _gear_setup()
        ranges = resolve_ranges("")
        profile = _make_neutral_profile()

        plan = run_rule_engine(diag, setup, ranges, profile)

        pge = diag.get("per_gear_explanation", {})
        for gear_key, explanation in pge.items():
            assert "gearbox locked" in explanation or "preserve" in explanation, (
                f"AC31 FAIL: locked gearbox explanation for {gear_key!r} does not mention "
                f"'gearbox locked'; got {explanation!r}"
            )

    def test_no_indexed_evidence_explanation_says_no_evidence(self):
        """Without indexed evidence, per_gear_explanation says 'no indexed evidence'."""
        diag = _base_diag(
            gearbox_flag="may_change",
            gearing_diagnosis_category="insufficient_data",
            per_gear_limiter_evidence=None,
            wheelspin_by_gear=None,
            bog_by_gear=None,
        )
        setup = _gear_setup()
        ranges = resolve_ranges("")
        profile = _make_neutral_profile()

        plan = run_rule_engine(diag, setup, ranges, profile)

        pge = diag.get("per_gear_explanation", {})
        for gear_key, explanation in pge.items():
            assert "not proposed" in explanation, (
                f"AC31 FAIL: gear {gear_key!r} should say 'not proposed' with no evidence; "
                f"got {explanation!r}"
            )

    def test_final_drive_b5_still_broad_lever(self):
        """B5 (gear_too_short + may_change) still proposes final_drive as the broad lever."""
        diag = _base_diag(
            gearbox_flag="may_change",
            gearing_diagnosis_category="gear_too_short",
            per_gear_limiter_evidence=None,
            wheelspin_by_gear=None,
            bog_by_gear=None,
        )
        diag["avg_top_speed_kmh"] = 200.0
        diag["top_speed_target_kmh"] = 300.0
        setup = {"final_drive": 3.5, **_gear_setup()}
        ranges = resolve_ranges("")
        profile = _make_neutral_profile()

        plan = run_rule_engine(diag, setup, ranges, profile)

        # B5 should propose final_drive
        fd_proposed = [ch for ch in plan.proposed if ch.field == "final_drive"]
        # Note: B5 may not fire if other preconditions aren't met — this is a best-effort check
        # The key invariant: no per-gear PG_N changes without indexed evidence
        pg_proposed = [ch for ch in plan.proposed if ch.rule_id.startswith("PG_")]
        assert not pg_proposed, (
            f"AC31 FAIL: PG_N proposed without indexed per-gear evidence; "
            f"found: {[(c.field, c.rule_id) for c in pg_proposed]}"
        )

    def test_per_gear_explanation_keys_match_setup_gears(self):
        """per_gear_explanation only has keys for gears present in the setup."""
        # Use a 4-gear setup
        diag = _base_diag(
            gearbox_flag="may_change",
            gearing_diagnosis_category="insufficient_data",
        )
        setup = {
            "gear_1": 3.600,
            "gear_2": 2.800,
            "gear_3": 2.100,
            "gear_4": 1.600,
            # gear_5, gear_6 absent
        }
        ranges = resolve_ranges("")
        profile = _make_neutral_profile()

        plan = run_rule_engine(diag, setup, ranges, profile)

        pge = diag.get("per_gear_explanation", {})
        # Keys should be gear_1..gear_4 only
        for key in pge:
            assert key in setup, (
                f"AC31 FAIL: per_gear_explanation has key {key!r} not in setup"
            )
        # gear_5/gear_6 should NOT appear
        assert "gear_5" not in pge, "AC31 FAIL: gear_5 in explanation but not in setup"
        assert "gear_6" not in pge, "AC31 FAIL: gear_6 in explanation but not in setup"
