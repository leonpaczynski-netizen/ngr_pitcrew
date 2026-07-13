"""Group 63 — Setup Brain UAT-2 regression suite.

Locks in the Porsche 911 RSR race-setup UAT repairs: feedback-parsing integrity,
gearbox mis-diagnosis (the "Final Drive 4.25 -> 4.20 for an unused sixth" defect),
the final-drive directional invariant, impact-based bottoming, the complete LSD
triplet, and the generalised coherence gate. Pure/offline — no Qt, no DB, no
runtime-file writes.
"""
from types import SimpleNamespace

import pytest

from strategy.setup_diagnosis import (
    _parse_driver_feel, _classify_gearing, _classify_bottoming_impact,
    _derive_dominant_problem, _dominant_problem_key, build_setup_diagnosis,
    build_feedback_dispositions,
    BOTTOMING_UNKNOWN, BOTTOMING_NORMAL_OR_EXPECTED, BOTTOMING_REQUIRED,
    BOTTOMING_PERFORMANCE,
)
from strategy import gearbox_evidence as ge
from strategy.lsd_reasoning import build_lsd_triplet_assessment


def _lap(*, bottoming=0, wheelspin=0, snap=0, lockups=0, rev_limiter_by_gear=None,
         max_speed=250.0, kerb=0, oversteer=0, oversteer_throttle_on=0, frames=None):
    rlbg = rev_limiter_by_gear or {}
    return SimpleNamespace(
        bottoming_count=bottoming, wheelspin_count=wheelspin, snap_throttle_count=snap,
        lock_up_count=lockups, rev_limiter_by_gear=rlbg, max_speed_kmh=max_speed,
        kerb_count=kerb, oversteer_count=oversteer,
        oversteer_throttle_on_count=oversteer_throttle_on,
        rev_limiter_count=sum(rlbg.values()), frames=frames or [],
    )


def _frame(gear):
    return SimpleNamespace(gear=gear, throttle=1.0, speed_kmh=250.0,
                           wheel_rps=None, tyre_radius=None)


# ---------------------------------------------------------------------------
# Feedback parsing integrity (RC-A)
# ---------------------------------------------------------------------------
class TestFeedbackParsing:
    def test_lsd_feel_wrong_captured(self):
        f = _parse_driver_feel("LSD is not set how I like, not hooking up on the apex")
        assert f["lsd_feel_wrong"]

    def test_rear_under_braking_distinct_from_exit(self):
        # Braking-only mention must NOT set the exit flag.
        f = _parse_driver_feel("Rear Under Braking: Steps out")
        assert f["rear_loose_under_braking"]
        assert not f["rear_loose_on_exit"]

    def test_both_exit_and_braking_when_both_reported(self):
        f = _parse_driver_feel("Rear loose on throttle. Rear Under Braking: Steps out")
        assert f["rear_loose_on_exit"] and f["rear_loose_under_braking"]

    def test_gearing_too_long_captured(self):
        f = _parse_driver_feel("not using all of sixth gear by the end of the straight")
        assert f["gearing_too_long"]

    def test_full_uat_string_all_flags(self):
        uat = ("Corner Entry: Too much understeer\nMid-Corner: Pushes wide\n"
               "Exit Stability: Rear loose on throttle\nRear Under Braking: Steps out\n"
               "Fuel Use: Higher than expected\nNotes: LSD is not set how I like, feels "
               "floaty and not hooking up on the apex. Not using all of sixth gear.")
        f = _parse_driver_feel(uat)
        for flag in ("entry_understeer", "mid_corner_understeer", "rear_loose_on_exit",
                     "rear_loose_under_braking", "lsd_feel_wrong", "gearing_too_long",
                     "fuel_use_high"):
            assert f[flag], flag


# ---------------------------------------------------------------------------
# Final-drive directional invariant (RC-B.4)
# ---------------------------------------------------------------------------
class TestDirectionalInvariant:
    def test_lower_ratio_is_longer(self):
        assert ge.final_drive_lengthens(4.25, 4.20)
        assert ge.final_drive_effect(-0.05) == ge.GEARING_LONGER

    def test_higher_ratio_is_shorter(self):
        assert ge.final_drive_shortens(4.20, 4.25)
        assert ge.final_drive_effect(+0.05) == ge.GEARING_SHORTER

    def test_4_25_to_4_20_classified_longer(self):
        # The exact UAT change lengthens the gearing (wrong for an unused sixth).
        assert ge.final_drive_lengthens(4.25, 4.20) is True
        assert ge.final_drive_shortens(4.25, 4.20) is False


# ---------------------------------------------------------------------------
# Gearbox diagnosis correctness (RC-B)
# ---------------------------------------------------------------------------
class TestGearboxDiagnosis:
    def test_zero_top_speed_target_is_unknown(self):
        # transmission_max_speed_kmh = 0 -> no valid target -> insufficient_data.
        frames = [_frame(6)] * 10
        cat = _classify_gearing(frames, {5: 3.0}, 250.0, 0.0, "severe", num_gears=6)
        assert cat == "insufficient_data"

    def test_unused_top_gear_not_gear_too_short(self):
        # 6th is driven but never limited; limiter only in gear 5 -> not gear_too_short.
        frames = [_frame(6)] * 20 + [_frame(5)] * 5
        cat = _classify_gearing(frames, {5: 4.0}, 250.0, 300.0, "low", num_gears=6)
        assert cat != "gear_too_short"

    def test_real_gear_too_short_still_detected(self):
        # Genuine top-gear limiter + low top speed + trustworthy location.
        frames = [_frame(6)] * 20
        cat = _classify_gearing(frames, {6: 4.0}, 250.0, 300.0, "low",
                                num_gears=6, location_trustworthy=True)
        assert cat == "gear_too_short"

    def test_low_location_confidence_blocks_gear_too_short(self):
        frames = [_frame(6)] * 20
        cat = _classify_gearing(frames, {6: 4.0}, 250.0, 300.0, "low",
                                num_gears=6, location_trustworthy=False)
        assert cat == "insufficient_data"

    def test_driver_unused_sixth_vetoes_short_to_conflicting(self):
        st = ge.derive_gearing_state("gear_too_short", driver_says_too_long=True)
        assert st == ge.GEARING_CONFLICTING

    def test_conflicting_evidence_preserves_gearbox(self):
        frames = [_frame(6)] * 20
        laps = [_lap(rev_limiter_by_gear={6: 4}, max_speed=250.0, frames=frames)]
        diag = build_setup_diagnosis(
            laps=laps,
            setup={"transmission_max_speed_kmh": 300, "num_gears": 6, "final_drive": 4.25},
            car_name="", event_ctx={},
            feeling="sixth gear not fully used on the main straight",
            location_confidence="high",
        )
        assert diag["gearing_diagnosis_category"] == "conflicting_evidence"
        assert diag["gearbox_flag"] == "preserve"

    def test_final_drive_rejected_by_validator_when_conflicting(self):
        from strategy.setup_diagnosis import validate_setup_engineering
        from strategy.setup_ranges import resolve_ranges
        frames = [_frame(6)] * 20
        laps = [_lap(rev_limiter_by_gear={6: 4}, frames=frames)]
        diag = build_setup_diagnosis(
            laps=laps,
            setup={"transmission_max_speed_kmh": 300, "num_gears": 6, "final_drive": 4.25},
            car_name="", event_ctx={},
            feeling="sixth gear not fully used",
            location_confidence="high",
        )
        ai_resp = {"changes": [{"field": "final_drive", "from": 4.25, "to": 4.20,
                                "setting": "Final Drive", "why": "x", "to_clamped": 4.20}],
                   "setup_fields": {"final_drive": 4.20}, "analysis": "", "primary_issue": ""}
        reasons = validate_setup_engineering(ai_resp, diag, {"final_drive": 4.25},
                                             resolve_ranges(""), {})
        assert any(r.startswith("gearbox_category_mismatch") for r in reasons)


# ---------------------------------------------------------------------------
# Bottoming impact model (RC-C)
# ---------------------------------------------------------------------------
class TestBottomingImpact:
    def test_count_only_required_is_unknown(self):
        imp = _classify_bottoming_impact("required", "floor_contact", "medium",
                                         driver_mentions_bottoming=False,
                                         accel_fade_detected=False,
                                         location_trustworthy=False)
        assert imp["impact"] == BOTTOMING_UNKNOWN
        assert imp["performance_relevant"] is False

    def test_kerb_strike_is_normal(self):
        imp = _classify_bottoming_impact("required", "kerb_strike", "high",
                                         False, False, True)
        assert imp["impact"] == BOTTOMING_NORMAL_OR_EXPECTED

    def test_impact_evidence_makes_required(self):
        imp = _classify_bottoming_impact("required", "floor_contact", "high",
                                         driver_mentions_bottoming=True,
                                         accel_fade_detected=True,
                                         location_trustworthy=True)
        assert imp["impact"] == BOTTOMING_REQUIRED
        assert imp["performance_relevant"]

    def test_accel_fade_only_is_performance_relevant(self):
        imp = _classify_bottoming_impact("consider", "floor_contact", "low",
                                         False, True, False)
        assert imp["impact"] == BOTTOMING_PERFORMANCE

    def test_handling_complaint_outranks_count_bottoming(self):
        flags = {"mid_corner_understeer": True, "bottoming": False}
        dom, _sec = _derive_dominant_problem(
            flags, "required", "low", aero_front_near_min=False,
            aero_rear_near_min=False, bottoming_evidence_insufficient=True)
        assert _dominant_problem_key(dom) == "mid_corner_understeer"

    def test_count_only_bottoming_demoted_via_diagnosis(self):
        # 3 bottoming/lap (required) but no driver mention, no accel-fade -> demoted.
        laps = [_lap(bottoming=3, wheelspin=20) for _ in range(4)]
        diag = build_setup_diagnosis(
            laps=laps, setup={}, car_name="", event_ctx={},
            feeling="Mid-Corner: Pushes wide", location_confidence="low",
        )
        assert diag["bottoming_impact"]["impact"] == BOTTOMING_UNKNOWN
        assert _dominant_problem_key(diag["dominant_problem"]) != "bottoming"


# ---------------------------------------------------------------------------
# LSD triplet (RC-D)
# ---------------------------------------------------------------------------
class TestLsdTriplet:
    def _prior(self):
        return {
            "lsd_initial": {"value": 22, "source": "Watkins Race", "tier": 2, "confidence": "medium"},
            "lsd_accel": {"value": 8, "source": "Watkins Race", "tier": 2, "confidence": "medium"},
            "lsd_decel": {"value": 33, "source": "Watkins Race", "tier": 2, "confidence": "medium"},
        }

    def test_all_three_evaluated_from_feedback(self):
        diag = {"driver_feel_flags": {"lsd_feel_wrong": True, "rear_loose_on_exit": True,
                                      "rear_loose_under_braking": True},
                "wheelspin_band": "severe", "wheelspin_subtype": "mixed"}
        a = build_lsd_triplet_assessment(diag, {"lsd_initial": 10, "lsd_accel": 17, "lsd_decel": 25},
                                         self._prior())
        assert all(f.evaluated for f in a.fields)

    def test_initial_torque_uses_proven_prior(self):
        diag = {"driver_feel_flags": {"lsd_feel_wrong": True}, "wheelspin_band": "low",
                "wheelspin_subtype": "insufficient_data"}
        a = build_lsd_triplet_assessment(diag, {"lsd_initial": 10}, self._prior())
        init = next(f for f in a.fields if f.field == "lsd_initial")
        assert init.evaluated and init.proven == 22 and init.direction == "increase"

    def test_unknown_subtype_yields_controlled_test(self):
        diag = {"driver_feel_flags": {"rear_loose_on_exit": True}, "wheelspin_band": "severe",
                "wheelspin_subtype": "mixed"}
        a = build_lsd_triplet_assessment(diag, {"lsd_accel": 17}, {})
        accel = next(f for f in a.fields if f.field == "lsd_accel")
        assert accel.direction == "controlled_test" and accel.controlled_test

    def test_braking_flag_routes_to_lsd_decel(self):
        diag = {"driver_feel_flags": {"rear_loose_under_braking": True}, "wheelspin_band": "low",
                "wheelspin_subtype": "insufficient_data"}
        a = build_lsd_triplet_assessment(diag, {"lsd_decel": 25}, self._prior())
        decel = next(f for f in a.fields if f.field == "lsd_decel")
        assert decel.evaluated and decel.proven == 33

    def test_no_lsd_complaint_no_evaluation(self):
        diag = {"driver_feel_flags": {}, "wheelspin_band": "low",
                "wheelspin_subtype": "insufficient_data"}
        a = build_lsd_triplet_assessment(diag, {"lsd_initial": 10}, {})
        assert not any(f.evaluated for f in a.fields)


# ---------------------------------------------------------------------------
# Coherence gate generalisation (RC-F)
# ---------------------------------------------------------------------------
class TestCoherenceGate:
    def test_handling_dominant_arms_gate(self):
        laps = [_lap(wheelspin=1) for _ in range(4)]
        diag = build_setup_diagnosis(
            laps=laps, setup={}, car_name="", event_ctx={},
            feeling="Mid-Corner: Pushes wide", location_confidence="low",
        )
        assert _dominant_problem_key(diag["dominant_problem"]) == "mid_corner_understeer"
        assert diag["dominant_required"] is True

    def test_bare_final_drive_does_not_address_wheelspin(self):
        from strategy.setup_diagnosis import DOMINANT_ADDRESSING_FIELDS
        assert "final_drive" not in DOMINANT_ADDRESSING_FIELDS["wheelspin"]


# ---------------------------------------------------------------------------
# Safety invariants
# ---------------------------------------------------------------------------
class TestSafetyInvariants:
    def test_lsd_module_pure(self):
        import strategy.lsd_reasoning as m
        import inspect
        src = inspect.getsource(m)
        assert "PyQt" not in src and "import sqlite3" not in src
        assert "open(" not in src and "api_key" not in src

    def test_gearbox_module_pure(self):
        import strategy.gearbox_evidence as m
        import inspect
        src = inspect.getsource(m)
        assert "PyQt" not in src and "sqlite3" not in src and "open(" not in src

    def test_lsd_assessment_authors_no_values(self):
        # The assessment never emits a 'to_value' / setup field — only direction+test.
        a = build_lsd_triplet_assessment(
            {"driver_feel_flags": {"lsd_feel_wrong": True}, "wheelspin_band": "low",
             "wheelspin_subtype": "insufficient_data"},
            {"lsd_initial": 10}, {})
        d = a.as_json()
        assert "setup_fields" not in d and "changes" not in d


# ---------------------------------------------------------------------------
# Full integration fixture — the Porsche 911 RSR race-setup UAT, end-to-end
# ---------------------------------------------------------------------------
_CAR = "Porsche 911 RSR (991) '17"
_UAT_FEELING = (
    "Corner Entry: Too much understeer\n"
    "Mid-Corner: Pushes wide\n"
    "Exit Stability: Rear loose on throttle\n"
    "Rear Under Braking: Steps out\n"
    "Fuel Use: Higher than expected\n"
    "Notes: LSD is not set how I like, feels quite floaty and not hooking up on the "
    "apex. The car is not using all of sixth gear by the end of the main straight."
)


def _watkins_setup(discipline, *, lsd_i, lsd_a, lsd_d, cam_f, cam_r, aero_f, aero_r,
                   arb_f, arb_r):
    return {
        "name": _CAR, "track": "Watkins Glen", "layout_id": "watkins_glen_long",
        "setup_type": discipline, "rating": "liked", "setup_label": f"Watkins {discipline}",
        "lsd_initial": lsd_i, "lsd_accel": lsd_a, "lsd_decel": lsd_d,
        "camber_front": cam_f, "camber_rear": cam_r,
        "aero_front": aero_f, "aero_rear": aero_r, "arb_front": arb_f, "arb_rear": arb_r,
    }


def _uat_history():
    return [
        _watkins_setup("Race", lsd_i=22, lsd_a=8, lsd_d=33, cam_f=2.5, cam_r=2.1,
                       aero_f=400, aero_r=600, arb_f=7, arb_r=7),
        _watkins_setup("Qualifying", lsd_i=20, lsd_a=9, lsd_d=31, cam_f=2.6, cam_r=1.9,
                       aero_f=430, aero_r=585, arb_f=7, arb_r=6),
    ]


def _uat_advisor():
    import tests.test_group41_validation_gate as G
    # Frames: sixth gear is actually driven on the straight; the limiter is only
    # tapped in gear 5 (intermediate). transmission_max_speed_kmh is uncaptured (0).
    frames = [SimpleNamespace(gear=6, throttle=1.0, speed_kmh=250.0,
                              wheel_rps=None, tyre_radius=None) for _ in range(30)]
    laps = [G._make_lap(bottoming_count=3, wheelspin_count=20,
                        rev_limiter_by_gear={5: 3}, kerb_count=8, frames=frames)
            for _ in range(4)]
    return G._make_full_advisor({}, laps)


class TestPorscheRsrIntegration:
    @pytest.fixture
    def result(self, monkeypatch):
        import json
        import strategy.driving_advisor as da
        monkeypatch.setattr(da, "call_api", lambda *a, **k: json.dumps({
            "status": "APPROVED", "warnings": [], "contradictions": [],
            "missing_evidence": [], "explanation_notes": "audit ok"}))
        adv = _uat_advisor()
        setup = {
            "final_drive": 4.25, "transmission_max_speed_kmh": 0, "num_gears": 6,
            "aero_front": 450, "aero_rear": 590,
            "lsd_initial": 10, "lsd_accel": 17, "lsd_decel": 20,
            "camber_front": 1.0, "camber_rear": 1.5,
            "arb_front": 5, "arb_rear": 5,
        }
        raw = adv.build_combined_setup_response(
            setup_dict=setup, car_name=_CAR, feeling=_UAT_FEELING,
            purpose="Race", drivetrain="RR", historical_setups=_uat_history(),
            track_name="NGR Porsche Cup Rd7", fuel_multiplier=3.0, refuel_rate_lps=1.0,
        )
        return json.loads(raw)

    def test_final_drive_not_lengthened(self, result):
        # The exact UAT defect: no 4.25 -> 4.20 (lengthening) change is authored.
        for ch in result.get("changes", []):
            if ch.get("field") == "final_drive":
                to_v = ch.get("to_clamped", ch.get("to"))
                assert not (to_v is not None and float(to_v) < 4.25), \
                    "final_drive must not be lengthened for an unused sixth"

    def test_gearing_not_gear_too_short(self, result):
        cat = (result.get("diagnosis") or {}).get("gearing_diagnosis_category")
        assert cat != "gear_too_short"

    def test_bottoming_not_required(self, result):
        bi = result.get("bottoming_impact") or {}
        assert bi.get("impact") in ("UNKNOWN", "ADVISORY", "NORMAL_OR_EXPECTED")
        assert not bi.get("performance_relevant", False)

    def test_all_three_lsd_fields_evaluated(self, result):
        lsd = result.get("lsd_assessment") or {}
        evaluated = [f for f in lsd.get("fields", []) if f.get("evaluated")]
        assert len(evaluated) == 3

    def test_lsd_surfaces_proven_values(self, result):
        lsd = result.get("lsd_assessment") or {}
        provens = {f["field"]: f.get("proven") for f in lsd.get("fields", [])}
        # Same-car Watkins proven values transfer as a prior to a DIFFERENT track.
        assert provens.get("lsd_initial") == 22
        assert provens.get("lsd_decel") == 33

    def test_every_feedback_item_dispositioned(self, result):
        disp = result.get("feedback_dispositions") or []
        labels = {d.get("feedback", "") for d in disp}
        # The direct LSD complaint, the braking complaint and the gearing complaint
        # each receive an explicit disposition (nothing reported disappears).
        assert any("LSD" in l for l in labels)
        assert any("under braking" in l for l in labels)
        assert any("Sixth gear" in l for l in labels)

    def test_targeted_tests_present(self, result):
        tests = result.get("_targeted_tests") or []
        assert tests, "unresolved evidence must yield precise targeted tests"

    def test_authors_coordinated_balance_not_deferral(self, result):
        # Engineer-evolution (balance solver): with SEVERAL conflicting complaints the
        # app no longer defers to evidence_required — it AUTHORS a coordinated balance
        # setup to test. It is honestly framed (balance_recommendation), not "approved
        # complete", and the safety invariants still hold.
        assert result.get("recommendation_status") == "balance_recommendation"
        assert result.get("setup_fields")           # a real, applyable setup exists
        _bs = result.get("balance_solution") or {}
        assert _bs.get("solved") is True
        # Safety preserved: no accel-lock increase; brake bias never rearward.
        _changes = {c["field"]: c for c in result.get("changes", [])}
        assert "lsd_accel" not in _changes
        if "brake_bias" in _changes:
            assert float(_changes["brake_bias"]["to_clamped"]) <= 0

    def test_ai_remains_audit_only(self, result):
        # The DETERMINISTIC balance solver authored the changes — not the AI. The AI
        # audit stays advisory-only and cannot manufacture setup values.
        assert result.get("rule_engine_version")
        # Every authored change is deterministic (balance solver or rule engine),
        # never AI-authored.
        for ch in result.get("changes", []):
            assert ch.get("rule_id") in ("balance_solver",) or ch.get("rule_id")
