"""Phase 17 — safety & frozen-contract tests.

No setup/experiment/outcome/calibration mutation; no Apply path; no hidden optimisation
(dimensions + weights are visible); no AI; no DB writes; no duplicate lifecycle/scoring.
"""
import inspect

import pytest

from strategy import experiment_portfolio as M
from strategy import experiment_portfolio_render as R

PURE = [M, R]


@pytest.mark.parametrize("mod", PURE)
def test_no_forbidden_imports(mod):
    src = inspect.getsource(mod)
    for banned in ("import sqlite3", "PyQt6", "PyQt5", "import requests", "urllib",
                   "import openai", "import anthropic", "socket", "import random",
                   "random.", "time.time", "datetime.now", "from data.session_db"):
        assert banned not in src, f"{mod.__name__}: {banned}"


def test_no_apply_or_mutation_capability():
    src = inspect.getsource(M)
    for banned in ("mark_applied(", "create_setup_experiment(", "save_setup(", ".commit(",
                   ".execute(", "def apply", "def approve", "def save", "def record_",
                   "build_experiment_from_recommendation("):
        assert banned not in src


def test_no_hidden_optimisation_weights_are_visible():
    # the value weights are a module constant and echoed into every portfolio result
    from strategy.experiment_portfolio import DIMENSION_WEIGHTS, build_portfolio
    assert isinstance(DIMENSION_WEIGHTS, dict) and DIMENSION_WEIGHTS
    p = build_portfolio({"ok": True, "synthesis_results": []}, session_context={})
    assert p.dimension_weights == DIMENSION_WEIGHTS


def test_no_duplicate_scoring_or_lifecycle_authority():
    src = inspect.getsource(M)
    # it does not reimplement synthesis / lifecycle / evidence grading
    for banned in ("def synthesize_bounded_experiments", "def build_execution_request",
                   "def evaluate_outcome", "class SetupExperiment", "def resolve_ranges",
                   "def legal_step"):
        assert banned not in src


def test_optimises_learning_not_lap_time():
    src = inspect.getsource(M)
    assert "information_gain" in src
    # lap time must not be a scoring dimension
    for banned in ("lap_time", "laptime", "fastest"):
        assert banned not in src.lower()


def test_db_version_and_rule_engine_unchanged():
    from strategy._setup_constants import DB_VERSION, RULE_ENGINE_VERSION
    from data.session_db import SessionDB
    assert DB_VERSION == 27 and RULE_ENGINE_VERSION == "46.0"
    db = SessionDB(":memory:")
    db.build_experiment_portfolio(car="Porsche 911 RSR", track="Fuji")
    assert db._conn.execute("PRAGMA user_version").fetchone()[0] == 27
    db.close()


def test_runtime_writes_nothing(tmp_path):
    from data.session_db import SessionDB
    db = SessionDB(str(tmp_path / "s.db"))
    v0 = db._conn.execute("PRAGMA user_version").fetchone()[0]
    before = db._conn.execute(
        "SELECT COUNT(*) FROM engineering_development_records").fetchone()[0]
    db.build_experiment_portfolio(car="Porsche 911 RSR", track="Fuji", discipline="Race")
    after = db._conn.execute(
        "SELECT COUNT(*) FROM engineering_development_records").fetchone()[0]
    assert before == after == 0 and db._conn.execute(
        "PRAGMA user_version").fetchone()[0] == v0 == 27
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
