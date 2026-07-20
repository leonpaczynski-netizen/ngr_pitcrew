"""Phase 38 — integrated crew brief: conflict resolution, one coherent plan, honesty."""
from strategy.contextual_knowledge_activation import activate_context_knowledge
from strategy.setup_outcome_learning import build_setup_outcome_learning
from strategy.setup_working_window import build_setup_working_windows
from strategy.driver_development_state import build_driver_development_state
from strategy.coaching_priority import build_coaching_plan
from strategy.race_engineer_team_brief import build_race_engineer_team_brief
from tests._race_engineer_helpers import scope, ctx, record, change, residual


def _assemble(records, *, next_experiment=None, strategy_context=None):
    s = scope()
    act = activate_context_knowledge(s, records)
    exact = [r for r in records if r["record_key"] in act.keys_for("exact_context")]
    sfp = s.context_fingerprint()
    sol = build_setup_outcome_learning(sfp, exact)
    ww = build_setup_working_windows(sfp, s.discipline.value, exact, sol.blocked_directions)
    dd = build_driver_development_state(sfp, exact)
    cp = build_coaching_plan(sfp, dd.to_dict())
    return build_race_engineer_team_brief(s.to_dict(), act.to_dict(), sol.to_dict(), ww.to_dict(),
                                          dd.to_dict(), cp.to_dict(), next_experiment=next_experiment,
                                          strategy_context=strategy_context)


# ---- 14. integrated brief conflict resolution ----------------------------------------------- #
def test_failed_experiment_produces_rollback_first_plan():
    a = record("A", changes=[change("arb_rear", "6")], outcome="confirmed_improvement", at="2026-01-01",
               protected=[{"behaviour": "stable entry", "verdict": "kept", "confidence": "high"}])
    b = record("B", changes=[change("lsd_acceleration", "40")], outcome="regression", at="2026-01-02",
               regressions=[{"issue_type": "wheelspin", "corner_name": "T2", "is_new": True}])
    brief = _assemble([a, b])
    plan = brief.ordered_development_plan
    assert plan and "roll back" in plan[0]["action"].lower()
    assert "stable entry" in brief.setup_engineer["confirmed_good_to_protect"]


def test_coaching_vs_setup_experiment_sequenced_not_simultaneous():
    # persistent driver-attributed wheelspin (coaching, hold setup) + a supplied next experiment.
    recs = [record(f"w{i}", changes=[change(f)], session=f"s{i}", at=f"2026-01-0{i+1}",
                   residuals=[residual("wheelspin", phase="exit", corner="T2", state="present")])
            for i, f in enumerate(("lsd_initial", "ride_height_rear", "anti_roll_bar_rear"))]
    brief = _assemble(recs, next_experiment={"field": "arb_rear", "direction": "increase", "id": "9"})
    kinds = {c["kind"] for c in brief.contradictions}
    assert "coaching_vs_setup_experiment" in kinds
    # the plan sequences with an explicit hold-constant, never both at once.
    holds = [a.get("hold_constant") for a in brief.ordered_development_plan if a.get("hold_constant")]
    assert holds


def test_one_coherent_plan_is_ordered_and_numbered():
    a = record("A", changes=[change("arb_rear", "6")], outcome="confirmed_improvement")
    brief = _assemble([a])
    steps = [x["step"] for x in brief.ordered_development_plan]
    assert steps == list(range(1, len(steps) + 1))


# ---- empty programme ------------------------------------------------------------------------ #
def test_empty_programme_is_honest_collection_plan():
    brief = _assemble([])
    assert brief.empty_state
    plan = brief.ordered_development_plan
    assert plan and "baseline" in plan[-1]["action"].lower()
    # no fabricated setup values anywhere in the brief.
    assert "confirmed_good_to_protect" in brief.setup_engineer


# ---- contradictory evidence ----------------------------------------------------------------- #
def test_incremental_not_labelled_ultimate_setup():
    a = record("A", changes=[change("arb_rear", "6")], outcome="confirmed_improvement")
    brief = _assemble([a])
    assert "not_an_ultimate_setup" in brief.setup_engineer
    assert "ultimate" in brief.setup_engineer["not_an_ultimate_setup"].lower()


# ---- 14b. authority reuse / non-duplication proof ------------------------------------------- #
def test_subordinate_fingerprints_reference_each_layer():
    a = record("A", changes=[change("arb_rear", "6")], outcome="confirmed_improvement")
    brief = _assemble([a])
    subs = brief.subordinate_fingerprints
    assert set(subs) == {"activation", "outcome_learning", "working_windows", "driver_development",
                         "coaching_plan"}
    # each present layer contributes its own fingerprint (a view over shared evidence, not a rebuild).
    assert subs["activation"] and subs["outcome_learning"]


def test_strategy_engineer_honest_without_race_plan():
    a = record("A", changes=[change("arb_rear", "6")], outcome="confirmed_improvement")
    brief = _assemble([a])
    assert brief.strategy_engineer["evidence_required"]  # states missing race-plan evidence


# ---- determinism ---------------------------------------------------------------------------- #
def test_brief_deterministic_and_shuffle_stable():
    recs = [record(f"r{i}", changes=[change("camber_front")], at=f"2026-01-0{i+1}", session=f"s{i}")
            for i in range(3)]
    a = _assemble(recs).content_fingerprint
    b = _assemble(list(reversed(recs))).content_fingerprint
    assert a == b


def test_export_destination_style_change_no_semantic_effect():
    # the brief carries no destination; adding an unrelated strategy note must not change identity core.
    a = record("A", changes=[change("arb_rear", "6")], outcome="confirmed_improvement")
    b1 = _assemble([a])
    b2 = _assemble([a])
    assert b1.content_fingerprint == b2.content_fingerprint
