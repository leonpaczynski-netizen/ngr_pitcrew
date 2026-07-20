"""Phase 15 — safety & frozen-contract tests (Section 27)."""
import inspect

import pytest

from strategy import experiment_synthesis as M
from strategy import experiment_synthesis_render as R

PURE = [M, R]


@pytest.mark.parametrize("mod", PURE)
def test_no_forbidden_imports(mod):
    src = inspect.getsource(mod)
    for banned in ("import sqlite3", "PyQt6", "PyQt5", "import requests", "urllib",
                   "import openai", "import anthropic", "socket", "import random",
                   "random.", "time.time", "datetime.now",
                   "from data.session_db"):
        assert banned not in src, f"{mod.__name__}: {banned}"


def test_no_apply_or_persist_capability():
    src = inspect.getsource(M)
    for banned in ("mark_applied(", "create_setup_experiment(", "save_setup(",
                   "compute_apply_status(", ".commit(", ".execute(", "def apply",
                   "def approve", "def save"):
        assert banned not in src


def test_consumes_canonical_authorities_no_shadow():
    src = inspect.getsource(M)
    # consumes the canonical step / quantiser / bounds / baseline / gearbox authorities
    assert "from strategy.experiment_selection import legal_step" in src
    assert "from strategy.setup_synthesis import _round" in src
    assert "from data.setup_state_authority import" in src
    assert "from strategy import gearbox_evidence" in src
    # no shadow parameter-range / step-size / synthesiser tables
    for banned in ("PARAMETER_INTERACTIONS = {", "_RANGES = {", "_STEP_SIZE = {",
                   "def resolve_ranges", "def generate_candidates"):
        assert banned not in src


def test_db_version_and_rule_engine_unchanged():
    from strategy._setup_constants import DB_VERSION, RULE_ENGINE_VERSION
    from data.session_db import SessionDB
    assert DB_VERSION == 27 and RULE_ENGINE_VERSION == "46.0"
    db = SessionDB(":memory:")
    db.build_bounded_setup_experiments(car="Porsche 911 RSR", track="Fuji")
    assert db._conn.execute("PRAGMA user_version").fetchone()[0] == 27
    db.close()


def test_frozen_authorities_canonical():
    from data.setup_state_authority import evaluate_analysis_gate, ActiveSetup
    from strategy.experiment_selection import legal_step
    from strategy.gearbox_evidence import final_drive_lengthens
    assert legal_step("arb_front") == 1.0 and legal_step("toe_front") == 0.01
    assert final_drive_lengthens(4.25, 4.20) is True


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


def test_synthesis_writes_nothing(tmp_path):
    from data.session_db import SessionDB
    db = SessionDB(str(tmp_path / "s.db"))
    v0 = db._conn.execute("PRAGMA user_version").fetchone()[0]
    db.build_bounded_setup_experiments(car="Porsche 911 RSR", track="Fuji", discipline="Race")
    assert db._conn.execute("PRAGMA user_version").fetchone()[0] == v0 == 27
    db.close()
