"""Group 64 — UAT integration proof through the REAL production path.

Exercises the exact failed-UAT scenario (Porsche 911 RSR race setup, multi-problem
driver feedback, weak/unlocated wheelspin, count-only bottoming) through
``build_combined_setup_response`` and the discipline-authoring path, and asserts the
Group 64 invariants:

  * bottoming renders ONE canonical state (never "required" + "normal" at once);
  * weak/unlocated wheelspin is NOT gear_too_short_spin;
  * a plan that leaves confirmed handling problems untreated is NOT "approved
    complete" — it is partial / targeted-test;
  * proven same-car history reaches deterministic authoring (incl. the LSD triplet);
  * Base / Qualifying / Race are separately engineered full-field setups;
  * a fresh profile invents no history.

Pure/offline — no Qt, no DB, no runtime-file writes (AI audit is monkeypatched).
"""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

# Reuse the Group 63 UAT harness (same car, feeling, history, advisor).
from tests.test_group63_setup_brain_uat2 import (
    _uat_advisor, _uat_history, _UAT_FEELING, _CAR,
)
from strategy._setup_constants import APPROVED_STATUSES
from strategy.setup_ranges import resolve_ranges


def _uat_setup():
    # The UAT current setup: ARB Front 6, LSD 10/15/10, low camber.
    return {
        "final_drive": 4.25, "transmission_max_speed_kmh": 0, "num_gears": 6,
        "aero_front": 450, "aero_rear": 590,
        "lsd_initial": 10, "lsd_accel": 15, "lsd_decel": 10,
        "camber_front": 1.0, "camber_rear": 1.5,
        "arb_front": 6, "arb_rear": 5,
    }


@pytest.fixture
def result():
    adv = _uat_advisor()
    raw = adv.build_combined_setup_response(
        setup_dict=_uat_setup(), car_name=_CAR, feeling=_UAT_FEELING,
        purpose="Race", drivetrain="RR", historical_setups=_uat_history(),
        track_name="NGR Porsche Cup Rd7", fuel_multiplier=3.0, refuel_rate_lps=1.0,
    )
    return json.loads(raw)


# ---------------------------------------------------------------- RC3 bottoming truth

def test_bottoming_single_canonical_state(result):
    diag = result.get("diagnosis") or {}
    bds = diag.get("bottoming_display_state") or {}
    assert bds, "canonical bottoming_display_state must be present"
    impact = (result.get("bottoming_impact") or {}).get("impact")
    # The canonical state must agree with the impact — never "required"/"address"
    # while the impact is a non-performance-relevant class.
    if impact in ("NORMAL_OR_EXPECTED", "ADVISORY", "UNKNOWN"):
        assert bds.get("state") not in ("address",)
        assert not bds.get("performance_relevant", False)


def test_bottoming_not_required_and_not_contradictory(result):
    bi = result.get("bottoming_impact") or {}
    assert bi.get("impact") in ("UNKNOWN", "ADVISORY", "NORMAL_OR_EXPECTED")
    bds = (result.get("diagnosis") or {}).get("bottoming_display_state") or {}
    # If the raw count band is "required" the canonical state must still not be.
    assert bds.get("state") != "required"


# ---------------------------------------------------------------- RC4 wheelspin gate

def test_wheelspin_not_gear_too_short_on_weak_evidence(result):
    subtype = (result.get("diagnosis") or {}).get("wheelspin_subtype")
    assert subtype != "gear_too_short_spin", (
        "weak/unlocated limiter evidence must not become a gearing certainty")


def test_final_drive_not_lengthened(result):
    for ch in result.get("changes", []):
        if ch.get("field") == "final_drive":
            to_v = ch.get("to_clamped", ch.get("to"))
            assert not (to_v is not None and float(to_v) < 4.25)


# ---------------------------------------------------------------- RC5 completeness

def test_not_approved_complete_with_untreated_problems(result):
    comp = result.get("recommendation_completeness") or {}
    assert comp, "recommendation_completeness verdict must be present"
    # Never a finished setup while confirmed handling problems remain untreated.
    assert comp.get("state") != "approved_complete"
    assert comp.get("complete") is False


def test_status_not_plain_approved(result):
    status = result.get("recommendation_status")
    # A lone/weak plan must never be plain "approved" or "approved_with_warnings"
    # while confirmed handling problems remain untreated (this scenario resolves to
    # the stronger evidence_required — nothing applyable).
    assert status not in ("approved", "approved_with_warnings", "approved_with_rejections")


def test_partial_downgrade_when_dominant_treated_but_secondaries_are_not():
    """The NEW completeness downgrade: when a change DOES address the dominant but
    confirmed secondary problems remain untreated, the plan is partial — not
    'approved'. Exercised directly on the pure completeness assessor."""
    from strategy.setup_diagnosis import (
        assess_recommendation_completeness, RECO_PARTIAL, RECO_APPROVED_COMPLETE,
    )
    diag = {"driver_feel_flags": {
        "mid_corner_understeer": True, "rear_loose_on_exit": True,
        "rear_loose_under_braking": True}, "wheelspin_band": "low"}
    # arb_front treats mid-corner understeer, but the rear-exit / rear-braking
    # problems are untreated and no test covers them.
    comp = assess_recommendation_completeness(
        diag, approved_fields={"arb_front"}, tested_fields=set(),
        base_status="approved")
    assert comp["state"] == RECO_PARTIAL
    assert "mid_corner_understeer" in comp["treated"]
    assert set(comp["untreated"]) >= {"rear_loose_on_exit", "rear_loose_under_braking"}
    # And when everything is treated (change + tests), it can be complete.
    comp2 = assess_recommendation_completeness(
        diag, approved_fields={"arb_front"},
        tested_fields={"lsd_accel", "lsd_decel", "brake_bias"}, base_status="approved")
    assert comp2["state"] == RECO_APPROVED_COMPLETE
    assert comp2["complete"] is True


# ---------------------------------------------------------------- history authoring

def test_proven_lsd_reaches_assessment(result):
    lsd = result.get("lsd_assessment") or {}
    provens = {f["field"]: f.get("proven") for f in lsd.get("fields", [])}
    assert provens.get("lsd_initial") == 22
    assert provens.get("lsd_decel") == 33


def test_every_feedback_item_dispositioned(result):
    disp = result.get("feedback_dispositions") or []
    labels = {d.get("feedback", "") for d in disp}
    assert any("LSD" in l for l in labels)
    assert any("under braking" in l for l in labels)


def test_ai_remains_audit_only(result):
    assert result.get("rule_engine_version")


# ---------------------------------------------------------------- discipline authoring

def _baseline_advisor():
    from strategy.driving_advisor import DrivingAdvisor
    rec = SimpleNamespace(recent_laps=lambda n: [], last_lap=lambda: None, best_lap=lambda: None)
    return DrivingAdvisor(rec, SimpleNamespace(), {})


def test_disciplines_are_separately_engineered_with_history():
    adv = _baseline_advisor()
    raw = adv.build_baseline_setup_response(
        _CAR, resolve_ranges(_CAR), "RR", 6, None, False,
        session_type="Race", duration_mins=45.0,
        track_name="NGR Porsche Cup Rd7", layout_id="full",
        historical_setups=_uat_history(),
    )
    dfp = json.loads(raw).get("discipline_field_plan") or {}
    # Base / Qualifying / Race differ across several fields — not just a label.
    assert len(dfp.get("differing_fields") or []) >= 5
    # Proven same-car LSD reached deterministic authoring.
    assert set(dfp.get("seeded_from_history") or []) >= {"lsd_initial", "lsd_decel"}
    rows = {r["field"]: r for r in dfp.get("rows") or []}
    assert rows["lsd_initial"]["race"] == 22
    # Every row carries a disposition.
    assert all(r.get("disposition") is not None for r in dfp.get("rows") or [])


def test_fresh_profile_invents_no_history():
    adv = _baseline_advisor()
    raw = adv.build_baseline_setup_response(
        _CAR, resolve_ranges(_CAR), "RR", 6, None, False,
        session_type="Race", duration_mins=45.0,
        track_name="NGR Porsche Cup Rd7", layout_id="full",
        historical_setups=[],
    )
    dfp = json.loads(raw).get("discipline_field_plan") or {}
    assert (dfp.get("seeded_from_history") or []) == []
    for r in dfp.get("rows") or []:
        assert r.get("proven") is None


# ---------------------------------------------------------------- discipline UI table

def test_discipline_table_renders_side_by_side():
    """The Base/Quali/Race side-by-side table renders from the plan (Qt-free — the
    render method only uses class constants + staticmethods, so it can be called
    unbound without constructing the widget)."""
    from ui.setup_builder_ui import SetupBuilderMixin
    adv = _baseline_advisor()
    raw = adv.build_baseline_setup_response(
        _CAR, resolve_ranges(_CAR), "RR", 6, None, False,
        session_type="Race", duration_mins=45.0,
        track_name="NGR Porsche Cup Rd7", layout_id="full",
        historical_setups=_uat_history(),
    )
    dfp = json.loads(raw).get("discipline_field_plan")
    html = SetupBuilderMixin._render_discipline_field_plan(SetupBuilderMixin, dfp)
    assert "<table" in html
    for col in ("Base", "Qualifying", "Race", "Proven"):
        assert col in html
    assert "Seeded from your proven" in html  # proven LSD reached the table
    # Self-guards: empty / None / no-rows render nothing.
    assert SetupBuilderMixin._render_discipline_field_plan(SetupBuilderMixin, {}) == ""
    assert SetupBuilderMixin._render_discipline_field_plan(SetupBuilderMixin, None) == ""
    assert SetupBuilderMixin._render_discipline_field_plan(
        SetupBuilderMixin, {"rows": []}) == ""
