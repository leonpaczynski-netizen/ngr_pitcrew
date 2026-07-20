"""Phase 36-38 — safety boundaries: pure, offline, read-only, no AI, no setup values, no mutation."""
import ast
import os

import strategy.engineering_context_scope as m_ctx
import strategy.contextual_knowledge_activation as m_act
import strategy.setup_outcome_learning as m_sol
import strategy.setup_working_window as m_ww
import strategy.driver_development_state as m_dd
import strategy.coaching_priority as m_cp
import strategy.race_engineer_team_brief as m_brief

PURE_MODULES = [m_ctx, m_act, m_sol, m_ww, m_dd, m_cp, m_brief]

FORBIDDEN_IMPORTS = {"PyQt6", "PyQt5", "sqlite3", "requests", "urllib", "openai", "anthropic",
                     "httpx", "socket"}
FORBIDDEN_TOKENS = ("datetime.now", "time.time", "random.", "os.environ", "api_key", "API_KEY",
                    "apply_setup", "requests.", "openai", "anthropic")


def test_pure_modules_have_no_forbidden_imports():
    for mod in PURE_MODULES:
        src = open(mod.__file__, encoding="utf-8").read()
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for n in node.names:
                    assert n.name.split(".")[0] not in FORBIDDEN_IMPORTS, (mod.__file__, n.name)
            elif isinstance(node, ast.ImportFrom):
                assert (node.module or "").split(".")[0] not in FORBIDDEN_IMPORTS, (mod.__file__,
                                                                                     node.module)


def test_pure_modules_have_no_forbidden_tokens():
    for mod in PURE_MODULES:
        src = open(mod.__file__, encoding="utf-8").read()
        for tok in FORBIDDEN_TOKENS:
            assert tok not in src, (mod.__file__, tok)


def test_domain_builders_never_raise_on_garbage():
    from strategy.engineering_context_scope import build_engineering_context_scope
    from strategy.contextual_knowledge_activation import activate_context_knowledge
    from strategy.setup_outcome_learning import build_setup_outcome_learning
    from strategy.setup_working_window import build_setup_working_windows
    from strategy.driver_development_state import build_driver_development_state
    from strategy.coaching_priority import build_coaching_plan
    from strategy.race_engineer_team_brief import build_race_engineer_team_brief
    for bad in (None, {}, [], "x", 5, {"programme": None}):
        build_engineering_context_scope(bad)
        activate_context_knowledge(bad, bad)
        build_setup_outcome_learning("fp", bad)
        build_setup_working_windows("fp", "race", bad, bad)
        build_driver_development_state("fp", bad)
        build_coaching_plan("fp", bad)
        build_race_engineer_team_brief(bad, bad, bad, bad, bad, bad)


def test_brief_declares_not_a_setup_or_certification():
    from strategy.race_engineer_team_brief import build_race_engineer_team_brief
    b = build_race_engineer_team_brief({}, {}, {}, {}, {}, {}).to_dict()
    adv = b["advisory_statement"].lower()
    assert "not permission to apply" in adv.replace("apply.", "apply")  # advisory only
    assert "not a certification" in adv or "not a complete" in adv


def test_runtime_immutability_versions_unchanged():
    from strategy._setup_constants import DB_VERSION, RULE_ENGINE_VERSION
    assert DB_VERSION == 28 and RULE_ENGINE_VERSION == "46.0"
