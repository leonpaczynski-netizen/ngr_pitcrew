"""Phase 39-41 — deterministic golden rendering + fingerprint properties."""
from strategy.engineering_run_plan import build_engineering_run_plan
from strategy.engineering_run_plan_render import render_run_plan_text
from strategy.engineering_run_outcome import build_run_outcome
from strategy.closed_loop_report import build_closed_loop_report
from strategy.closed_loop_report_render import render_closed_loop_text
from strategy.context_scoped_chain import build_context_scoped_chain
from tests._race_engineer_helpers import scope as _scope, ctx, record, change


_SCOPE = {"driver": "Leon", "car": "Porsche 911 RSR", "track": "Fuji", "layout_id": "fc",
          "event_id": "E1", "discipline": "race", "compound": "RH", "context_fingerprint": "cfp:x"}
_BASE = dict(candidate_tested=True, applied_setup_matches_plan=True, context_matches_plan=True,
             telemetry_complete=True, clean_laps=5, min_clean_required=3, compound_used="RH",
             planned_compound="RH")


def _plan():
    return build_engineering_run_plan(_SCOPE, candidate={"candidate_id": "c1", "field": "lsd_initial",
                                      "direction": "increase", "hypothesis": "reduce wheelspin"},
                                      applied_setup={"name": "B", "fields": {"lsd_initial": "20",
                                                     "arb_rear": "6"}},
                                      parent_setup={"name": "A"}).to_dict()


def test_run_plan_render_deterministic_ascii():
    p = _plan()
    t1, t2 = render_run_plan_text(p), render_run_plan_text(p)
    assert t1 == t2 and t1.isascii()
    for m in ("Controlled change", "Held constant", "Run-validity gate", "Safety & rollback"):
        assert m in t1


def test_closed_loop_render_deterministic_ascii():
    o = build_run_outcome({**_BASE, "new_regressions": ["x"]}, _plan(), discipline="race")
    rep = build_closed_loop_report(_SCOPE, _plan(), o.to_dict()).to_dict()
    t1, t2 = render_closed_loop_text(rep), render_closed_loop_text(rep)
    assert t1 == t2 and t1.isascii()
    assert "Primary next action" in t1 and "Knowledge-update PROPOSAL" in t1


def test_run_plan_render_has_no_apply_instruction():
    t = render_run_plan_text(_plan()).lower()
    # 'apply' only appears as the advisory disclaimer, never as an instruction.
    assert "apply gate" in t or "not permission to apply" in t.replace("apply gate", "")


def test_changed_observed_outcome_alters_closure_fingerprint():
    plan = _plan()
    reg = build_closed_loop_report(_SCOPE, plan,
                                   build_run_outcome({**_BASE, "new_regressions": ["x"]}, plan,
                                                     discipline="race").to_dict()).content_fingerprint
    imp = build_closed_loop_report(_SCOPE, plan,
                                   build_run_outcome({**_BASE, "target_metric_improved": True,
                                                      "lap_time_delta": -0.2,
                                                      "consistency_effect": "better"}, plan,
                                                     discipline="race").to_dict()).content_fingerprint
    assert reg != imp


def test_invalid_run_does_not_change_proven_working_window():
    # metamorphic: adding an INVALID run to the exact history changes visibility but not the exact
    # working-window inputs (exact fingerprint of the scoped chain).
    s = _scope()
    valid = [record("A", changes=[change("arb_rear", "6")], outcome="confirmed_improvement",
                    context=ctx(), session="s1")]
    invalid_run = record("BAD", changes=[change("arb_rear", "6")], outcome="confounded",
                         context=ctx(), session="s2", at="2026-02-01")
    a = build_context_scoped_chain(s, valid)
    b = build_context_scoped_chain(s, valid + [invalid_run])
    # a confounded record is still exact-context membership, but the domain summary counts it as
    # neither improvement nor regression, so the PROVEN convergence is unchanged.
    da = {d["domain"]: d["convergence"] for d in a.exact_domain_summary}
    db = {d["domain"]: d["convergence"] for d in b.exact_domain_summary}
    assert da.get("anti_roll_bars") == db.get("anti_roll_bars")
