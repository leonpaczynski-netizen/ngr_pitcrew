"""Phase 39-41 — safety: pure modules, no AI/keys/writes, frozen Apply gate, DB v26."""
import ast

import strategy.context_equivalence as m_eq
import strategy.context_scoped_chain as m_chain
import strategy.regression_attribution as m_ra
import strategy.setup_independence as m_si
import strategy.production_history_validation as m_pv
import strategy.engineering_run_plan as m_rp
import strategy.run_candidate_selection as m_sel
import strategy.engineering_run_outcome as m_ro
import strategy.closed_loop_report as m_cl

PURE = [m_eq, m_chain, m_ra, m_si, m_pv, m_rp, m_sel, m_ro, m_cl]

FORBIDDEN_IMPORTS = {"PyQt6", "PyQt5", "sqlite3", "requests", "urllib", "openai", "anthropic", "httpx",
                     "socket"}
FORBIDDEN_TOKENS = ("datetime.now", "time.time", "random.", "os.environ", "api_key", "API_KEY",
                    "apply_setup", "openai", "anthropic")


def test_pure_modules_no_forbidden_imports():
    for mod in PURE:
        tree = ast.parse(open(mod.__file__, encoding="utf-8").read())
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for n in node.names:
                    assert n.name.split(".")[0] not in FORBIDDEN_IMPORTS, (mod.__file__, n.name)
            elif isinstance(node, ast.ImportFrom):
                assert (node.module or "").split(".")[0] not in FORBIDDEN_IMPORTS, mod.__file__


def test_pure_modules_no_forbidden_tokens():
    for mod in PURE:
        src = open(mod.__file__, encoding="utf-8").read()
        for tok in FORBIDDEN_TOKENS:
            assert tok not in src, (mod.__file__, tok)


def test_builders_never_raise_on_garbage():
    from strategy.context_scoped_chain import build_context_scoped_chain
    from strategy.regression_attribution import build_regression_attribution
    from strategy.setup_independence import assess_setup_independence, attribute_issue
    from strategy.production_history_validation import validate_production_history
    from strategy.engineering_run_plan import build_engineering_run_plan
    from strategy.run_candidate_selection import select_run_candidate
    from strategy.engineering_run_outcome import build_run_outcome
    from strategy.closed_loop_report import build_closed_loop_report
    from strategy.context_equivalence import assess_context_equivalence
    for bad in (None, {}, [], "x", 5):
        build_context_scoped_chain(bad, bad)
        build_regression_attribution(bad)
        assess_setup_independence(bad, bad, "x")
        attribute_issue("x", bad)
        validate_production_history(bad, bad)
        build_engineering_run_plan(bad)
        select_run_candidate(bad)
        build_run_outcome(bad)
        build_closed_loop_report(bad, bad, bad)
        assess_context_equivalence(bad, bad)


def test_run_plan_and_report_declare_read_only():
    from strategy.engineering_run_plan import build_engineering_run_plan
    from strategy.closed_loop_report import build_closed_loop_report
    plan = build_engineering_run_plan({"discipline": "race"},
                                      candidate={"candidate_id": "c", "field": "x"}).to_dict()
    assert "apply" in plan["advisory_statement"].lower() and "no setup values" in \
        plan["advisory_statement"].lower()
    rep = build_closed_loop_report({}, plan, {}).to_dict()
    assert "nothing is written" in rep["advisory_statement"].lower() or "applied" in \
        rep["advisory_statement"].lower()


def test_versions_unchanged():
    from strategy._setup_constants import DB_VERSION, RULE_ENGINE_VERSION
    assert DB_VERSION == 27 and RULE_ENGINE_VERSION == "46.0"


def test_no_ai_no_apply_in_new_session_db_entries():
    import inspect
    from data.session_db import SessionDB
    for name in ("build_context_scoped_evidence_report", "build_production_history_validation_report",
                 "build_engineering_run_plan_report", "build_closed_loop_workflow_report"):
        src = inspect.getsource(getattr(SessionDB, name)).lower()
        for bad in ("openai", "anthropic", "api_key", "apply_setup(", "insert into", "update "):
            assert bad not in src, (name, bad)
