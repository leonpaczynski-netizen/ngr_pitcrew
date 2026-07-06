"""Group 48 — Race Strategy Brain Phase 2: explanation surface + safety tests.

Two concerns in one file (both pure/offline):

EXPLANATION SURFACE (strategy/race_strategy_explain.py)
  • shows the recommended plan and confidence
  • separates KNOWN evidence, CALCULATED estimate, ASSUMPTION, MISSING evidence, RISK
  • lists risk flags and missing evidence
  • never uses "perfect strategy" / "guaranteed" language

SAFETY GUARANTEES (Group 43-47 must not weaken)
  • strategy intelligence authors NO setup fields and cannot apply/approve setups
  • the Setup Apply-gate predicate is unchanged
  • the old ungated AI Build path stays disabled
  • Group 47 driver memory cannot override strategy legality or maths
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from strategy.race_strategy_evidence import build_strategy_evidence, StrategyConfidence  # noqa: E402
from strategy.race_strategy_candidates import (  # noqa: E402
    generate_candidates, legal_candidates, Legality,
)
from strategy.race_strategy_scorer import (  # noqa: E402
    recommend_strategy, StrategyScore, StrategyRecommendation,
)
from strategy.race_strategy_explain import (  # noqa: E402
    build_explanation, StrategyExplanation, plan_name,
)


def _ev(**over):
    kw = dict(
        car_id=911, track="Fuji", race_laps=20,
        fuel_multiplier=3.0, tyre_multiplier=8.0,
        refuel_rate_lps=1.0, pit_loss_seconds=22.0,
        available_compounds=("RM", "RH"), weather_context="dry_stable",
        lap_time_samples=[100.0] * 8, fuel_use_samples=[4.0] * 4,
        tyre_wear_samples=[0.08] * 10, compound_samples={"RM": [100.0], "RH": [101.5]},
    )
    kw.update(over)
    return build_strategy_evidence(**kw)


# ===========================================================================
# Explanation surface
# ===========================================================================

class TestExplanation:
    def test_shows_recommended_plan(self):
        ev = _ev()
        exp = build_explanation(recommend_strategy(ev), ev)
        assert exp.has_recommendation
        assert exp.recommended_plan
        assert "plan" in exp.recommended_plan.lower()
        assert "Recommended Strategy" in exp.to_text()

    def test_confidence_displayed(self):
        ev = _ev()
        exp = build_explanation(recommend_strategy(ev), ev)
        assert exp.confidence in {c.value for c in StrategyConfidence}
        assert "Confidence" in exp.to_text()

    def test_separates_four_categories(self):
        ev = _ev()
        exp = build_explanation(recommend_strategy(ev), ev)
        text = exp.to_text()
        assert "Known evidence" in text
        assert "Calculated estimate" in text
        assert "Assumptions" in text
        # Known and calculated are distinct, non-empty buckets.
        assert exp.known_evidence
        assert exp.calculated
        assert exp.assumptions

    def test_missing_evidence_displayed(self):
        ev = _ev(tyre_wear_samples=[0.08, 0.09])  # short sample → missing long-run
        exp = build_explanation(recommend_strategy(ev), ev)
        assert exp.missing_evidence
        assert "Missing evidence" in exp.to_text()

    def test_risk_flags_displayed_when_present(self):
        # A no-stop with no degradation data raises risk flags; force that route
        # by making a no-stop the recommendation via cheap fuel + tiny race.
        ev = _ev(race_laps=8, fuel_use_samples=[1.0], tyre_wear_samples=[])
        rec = recommend_strategy(ev)
        exp = build_explanation(rec, ev)
        if exp.risk_flags:
            assert "Risk" in exp.to_text()

    def test_no_perfect_strategy_language(self):
        ev = _ev()
        text = build_explanation(recommend_strategy(ev), ev).to_text().lower()
        for banned in ("perfect strategy", "guaranteed", "guarantee the win",
                       "the winning strategy", "flawless"):
            assert banned not in text

    def test_no_recommendation_surface_is_honest(self):
        ev = _ev(lap_time_samples=[], fuel_use_samples=[])
        exp = build_explanation(recommend_strategy(ev), ev)
        assert not exp.has_recommendation
        assert exp.confidence == StrategyConfidence.INSUFFICIENT_EVIDENCE.value
        assert exp.missing_evidence
        assert "insufficient" in exp.recommended_plan.lower()

    def test_plan_name_maps_known_ids(self):
        assert plan_name("1stop") == "One-stop race plan"
        assert plan_name("2stop_push") == "Push two-stop race plan"


# ===========================================================================
# Safety guarantees (Group 43-47)
# ===========================================================================

_SETUP_FIELD_TOKENS = (
    "ride_height", "springs", "damper", "arb", "camber", "toe",
    "aero_front", "aero_rear", "lsd", "brake_bias", "ballast",
    "power_restrictor", "final_drive", "gear_ratio", "approved_fields",
    "setup_fields", "approved_changes",
)


class TestSafetyGuarantees:
    def test_strategy_outputs_author_no_setup_fields(self):
        ev = _ev()
        rec = recommend_strategy(ev)
        exp = build_explanation(rec, ev)
        # Inspect every dataclass field name across the Group 48 result surface.
        names = set()
        for obj in (rec, rec.recommended, exp, *rec.candidates, *rec.ranked):
            if obj is None:
                continue
            names |= set(vars(obj).keys())
        for token in _SETUP_FIELD_TOKENS:
            assert not any(token in n for n in names), f"setup token {token} leaked into strategy output"

    def test_recommendation_has_no_apply_capability(self):
        rec = recommend_strategy(_ev())
        for banned in ("apply", "approve", "approved_fields", "setup_fields", "write"):
            assert not hasattr(rec, banned)
            if rec.recommended is not None:
                assert not hasattr(rec.recommended, banned)

    def test_group48_modules_do_not_import_setup_authoring(self):
        import strategy.race_strategy_evidence as m1
        import strategy.race_strategy_candidates as m2
        import strategy.race_strategy_scorer as m3
        import strategy.race_strategy_explain as m4
        for src_path in (m1.__file__, m2.__file__, m3.__file__, m4.__file__):
            text = Path(src_path).read_text(encoding="utf-8")
            for banned in ("setup_plan", "setup_rule_engine", "setup_ai_audit",
                           "setup_knowledge_base", "setup_baseline"):
                assert banned not in text, f"{src_path} imports setup-authoring module {banned}"

    def test_apply_gate_predicate_unchanged(self):
        src = (ROOT / "ui" / "setup_builder_ui.py").read_text(encoding="utf-8")
        # The exact Group 41/42 Apply-gate predicate must still be present.
        assert "_status_approved and bool(_parsed_ai_fields) and not _is_legacy" in src

    def test_old_ai_build_path_still_disabled(self):
        src = (ROOT / "ui" / "setup_builder_ui.py").read_text(encoding="utf-8")
        assert "form._btn_build_setup.setEnabled(False)" in src

    def test_driver_memory_cannot_flip_legality(self):
        # A fuel-limited no-stop is ILLEGAL; the rear-fragility driver memory flag
        # must not promote it, and legality must be identical regardless of it.
        ev = _ev(fuel_use_samples=[6.0])  # 20 * 6 = 120 L > tank → no-stop illegal
        cands = generate_candidates(ev)
        nostop = next(c for c in cands if c.candidate_id == "nostop")
        assert nostop.legality_status == Legality.ILLEGAL

        rec_safe = recommend_strategy(ev, rear_traction_fragile=True)
        rec_plain = recommend_strategy(ev, rear_traction_fragile=False)
        assert rec_safe.recommended.candidate_id != "nostop"
        assert rec_plain.recommended.candidate_id != "nostop"
        # legality set is invariant to the driver-memory flag
        legal_safe = {c.candidate_id for c in legal_candidates(rec_safe.candidates)}
        legal_plain = {c.candidate_id for c in legal_candidates(rec_plain.candidates)}
        assert legal_safe == legal_plain

    def test_driver_memory_cannot_change_total_time_maths(self):
        # The deterministic total-time of a given candidate must not depend on the
        # driver-memory flag (memory may only touch confidence / risk / tie-breaks).
        ev = _ev()
        a = {s.candidate_id: s.estimated_total_time_seconds
             for s in recommend_strategy(ev, rear_traction_fragile=True).ranked}
        b = {s.candidate_id: s.estimated_total_time_seconds
             for s in recommend_strategy(ev, rear_traction_fragile=False).ranked}
        assert a == b


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
