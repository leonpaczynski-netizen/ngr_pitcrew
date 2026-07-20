"""Phase 42-44 — safety: pure modules, no AI/keys/writes/voice, frozen Apply gate, DB v26."""
import ast

import strategy.material_context as m_mc
import strategy.legacy_evidence_trust as m_le
import strategy.assisted_run_workflow as m_wf
import strategy.session_binding as m_sb
import strategy.assisted_outcome_capture as m_oc
import strategy.live_advisory as m_la
import strategy.live_advisory_engine as m_eng
import strategy.runtime_snapshot as m_rs

PURE = [m_mc, m_le, m_wf, m_sb, m_oc, m_la, m_eng, m_rs]

FORBIDDEN_IMPORTS = {"PyQt6", "PyQt5", "sqlite3", "requests", "urllib", "openai", "anthropic", "httpx",
                     "socket", "pyttsx3", "win32com"}
# pure engineering modules must not read wall-clock; runtime timing is injected. Tokens are
# call-specific (trailing "(") so docstring prose like "no random." never trips the scan.
FORBIDDEN_TOKENS = ("datetime.now(", "time.time(", "time.monotonic(", "random.random(",
                    "random.choice(", "random.shuffle(", "os.environ[", "os.getenv(", "apply_setup(",
                    "openai", "anthropic", "text_to_speech(", "pyttsx3", ".say(")


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
    from strategy.material_context import build_material_context_trust
    from strategy.legacy_evidence_trust import build_legacy_evidence_trust
    from strategy.assisted_run_workflow import evaluate_assisted_run_workflow
    from strategy.session_binding import rank_candidate_sessions
    from strategy.assisted_outcome_capture import build_assisted_outcome_review
    from strategy.live_advisory import build_candidate_prompts
    from strategy.live_advisory_engine import evaluate_live_advisories
    from strategy.runtime_snapshot import build_runtime_snapshot
    for bad in (None, {}, [], "x", 5):
        build_material_context_trust(bad, bad, "x")
        build_legacy_evidence_trust(bad, bad)
        evaluate_assisted_run_workflow(run_plan=bad)
        rank_candidate_sessions(bad, bad)
        build_assisted_outcome_review(bad, bad, bad)
        build_candidate_prompts(bad, bad)
        evaluate_live_advisories(bad, bad, now_monotonic=0.0)
        build_runtime_snapshot(run_plan=bad, telemetry=bad)


def test_no_ai_no_apply_no_voice_in_session_db_entries():
    import inspect
    from data.session_db import SessionDB
    for name in ("build_material_context_trust_report", "build_assisted_runtime_report"):
        src = inspect.getsource(getattr(SessionDB, name)).lower()
        for bad in ("openai", "anthropic", "api_key", "apply_setup(", "insert into", "update ",
                    "pyttsx3", "text_to_speech"):
            assert bad not in src, (name, bad)


def test_versions_unchanged():
    from strategy._setup_constants import DB_VERSION, RULE_ENGINE_VERSION
    assert DB_VERSION == 27 and RULE_ENGINE_VERSION == "46.0"


def test_advisory_advisories_are_read_only():
    from strategy.assisted_outcome_capture import build_assisted_outcome_review
    r = build_assisted_outcome_review({}, {}, {}, session_bound=False).to_dict()
    assert "nothing is recorded" in r["advisory_statement"].lower()
    assert r["explicit_confirmation_required"] is True
