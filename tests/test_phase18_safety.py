"""Phase 18 — safety & frozen-contract tests.

No setup/experiment/outcome/record mutation; no Apply/approve/freeze/execution authority;
no AI; no DB writes; no duplicate ranking/lifecycle; frozen contracts + DB v25 unchanged.
"""
import inspect

import pytest

from strategy import engineering_campaign as M
from strategy import engineering_campaign_render as R

PURE = [M, R]


@pytest.mark.parametrize("mod", PURE)
def test_no_forbidden_imports(mod):
    src = inspect.getsource(mod)
    for banned in ("import sqlite3", "PyQt6", "PyQt5", "import requests", "urllib",
                   "import openai", "import anthropic", "socket", "import random",
                   "random.", "time.time", "datetime.now", "from data.session_db"):
        assert banned not in src, f"{mod.__name__}: {banned}"


def test_no_mutation_or_execution_capability():
    src = inspect.getsource(M)
    for banned in ("mark_applied(", "create_setup_experiment(", "save_setup(", ".commit(",
                   ".execute(", "def apply", "def approve", "def freeze", "def execute",
                   "def record_", "build_experiment_from_recommendation("):
        assert banned not in src


def test_no_duplicate_ranking_or_lifecycle():
    src = inspect.getsource(M)
    # Phase 18 owns neither ranking (Phase 17) nor synthesis/lifecycle
    for banned in ("def build_portfolio", "DIMENSION_WEIGHTS", "def synthesize_bounded",
                   "def build_execution_request", "def evaluate_outcome", "def legal_step"):
        assert banned not in src


def test_never_completes_unvalidated():
    """A successful-but-unvalidated objective must not be COMPLETED (source-level guard: the
    freeze_eligible criterion and COMPLETED both require the validated criterion)."""
    src = inspect.getsource(M)
    assert "_VALIDATION_MIN_CONFIRMATIONS" in src
    # behavioural check
    from strategy.engineering_campaign import build_campaign_programme, CampaignStatus
    portfolio = {"content_fingerprint": "fp", "valuations": [
        {"candidate_id": "c1", "diagnosis_key": "d", "issue_type": "entry_understeer",
         "field": "arb_front", "direction": "soften", "mechanism_id": "m", "rank": 0,
         "engineering_value": 0.8, "role": "highest_value", "attribution_scope": "single_field",
         "synthesis_status": "ready_for_preflight", "retirement_reason": "", "depends_on": [],
         "protected_good_at_risk": [], "dimensions": [], "expected_learning": "x"}],
        "dependencies": []}
    scope = {"car": "c", "track": "t", "layout_id": "l", "discipline": "Race", "driver": "d",
             "gt7_version": "1"}
    p = build_campaign_programme(portfolio, scope=scope, active_context=scope,
                                 outcome_history=[{"fields": ["arb_front"], "direction": "decrease",
                                                   "outcome_status": "confirmed_improvement",
                                                   "session_id": "s1"}])
    assert p.campaigns[0]["status"] == CampaignStatus.VALIDATION_REQUIRED.value


def test_db_version_and_rule_engine_unchanged():
    from strategy._setup_constants import DB_VERSION, RULE_ENGINE_VERSION
    from data.session_db import SessionDB
    assert DB_VERSION == 26 and RULE_ENGINE_VERSION == "46.0"
    db = SessionDB(":memory:")
    db.build_engineering_campaign_programme(car="Porsche 911 RSR", track="Fuji")
    assert db._conn.execute("PRAGMA user_version").fetchone()[0] == 26
    db.close()


def test_runtime_writes_nothing(tmp_path):
    from data.session_db import SessionDB
    db = SessionDB(str(tmp_path / "s.db"))
    v0 = db._conn.execute("PRAGMA user_version").fetchone()[0]
    before_dev = db._conn.execute(
        "SELECT COUNT(*) FROM engineering_development_records").fetchone()[0]
    before_exp = db._conn.execute("SELECT COUNT(*) FROM setup_experiments").fetchone()[0]
    db.build_engineering_campaign_programme(car="Porsche 911 RSR", track="Fuji", discipline="Race")
    assert db._conn.execute(
        "SELECT COUNT(*) FROM engineering_development_records").fetchone()[0] == before_dev == 0
    assert db._conn.execute("SELECT COUNT(*) FROM setup_experiments").fetchone()[0] == before_exp == 0
    assert db._conn.execute("PRAGMA user_version").fetchone()[0] == v0 == 26
    db.close()


def test_no_ai_architecture_scans_new_modules():
    import tests.test_no_ai_architecture as g
    hits = []
    for path in g._production_py_files():
        try:
            text = path.read_text(encoding="utf-8")
        except Exception:
            continue
        for rx, label in g._COMPILED:
            if rx.search(text):
                hits.append(f"{path}:{label}")
    assert not hits, hits
