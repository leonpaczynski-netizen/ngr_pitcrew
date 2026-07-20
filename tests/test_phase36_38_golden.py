"""Phase 36-38 — deterministic golden rendering of the activation and the crew brief."""
from strategy.contextual_knowledge_activation import activate_context_knowledge
from strategy.contextual_knowledge_activation_render import render_activation_text
from strategy.setup_outcome_learning import build_setup_outcome_learning
from strategy.setup_working_window import build_setup_working_windows
from strategy.driver_development_state import build_driver_development_state
from strategy.coaching_priority import build_coaching_plan
from strategy.race_engineer_team_brief import build_race_engineer_team_brief
from strategy.race_engineer_team_brief_render import render_brief_text
from tests._race_engineer_helpers import scope, ctx, record, change, residual


def _fixture():
    s = scope()
    recs = [
        record("A", changes=[change("arb_rear", "6")], outcome="confirmed_improvement", at="2026-01-01",
               protected=[{"behaviour": "stable entry", "verdict": "kept", "confidence": "high"}]),
        record("B", changes=[change("lsd_acceleration", "40")], outcome="regression", at="2026-01-02",
               regressions=[{"issue_type": "wheelspin", "corner_name": "T2", "is_new": True}],
               residuals=[residual("wheelspin", phase="exit", corner="T2", state="present", is_new=True)]),
        record("D", changes=[change("final_drive")], outcome="confirmed_improvement",
               context=ctx(track="Daytona", layout="road"), at="2026-01-03"),
    ]
    act = activate_context_knowledge(s, recs)
    exact = [r for r in recs if r["record_key"] in act.keys_for("exact_context")]
    sfp = s.context_fingerprint()
    sol = build_setup_outcome_learning(sfp, exact)
    ww = build_setup_working_windows(sfp, s.discipline.value, exact, sol.blocked_directions)
    dd = build_driver_development_state(sfp, exact)
    cp = build_coaching_plan(sfp, dd.to_dict())
    brief = build_race_engineer_team_brief(s.to_dict(), act.to_dict(), sol.to_dict(), ww.to_dict(),
                                           dd.to_dict(), cp.to_dict())
    return act, brief


def test_activation_render_deterministic_and_ascii():
    act, _ = _fixture()
    t1 = render_activation_text(act.to_dict())
    t2 = render_activation_text(act.to_dict())
    assert t1 == t2
    assert t1.isascii()
    assert "Contamination guard" in t1


def test_brief_render_deterministic_and_ascii():
    _, brief = _fixture()
    t1 = render_brief_text(brief.to_dict())
    t2 = render_brief_text(brief.to_dict())
    assert t1 == t2
    assert t1.isascii()


def test_brief_render_has_all_role_sections():
    _, brief = _fixture()
    t = render_brief_text(brief.to_dict())
    for marker in ("Chief Engineer", "Setup Engineer", "Performance / Data Engineer",
                   "Driver Coach", "Strategy Engineer", "One coherent development plan"):
        assert marker in t, marker


def test_render_contains_no_setup_values_leak():
    # the renderer must not print raw applied numeric setup values as a recommendation; it prints
    # window bounds/proven values as EVIDENCE only, never an "apply X" instruction.
    _, brief = _fixture()
    t = render_brief_text(brief.to_dict()).lower()
    assert "apply" not in t.replace("permission to apply", "").replace("not permission", "")


def test_brief_render_shows_rollback_first():
    _, brief = _fixture()
    t = render_brief_text(brief.to_dict())
    plan_idx = t.index("One coherent development plan")
    assert "roll back" in t[plan_idx:plan_idx + 400].lower()
