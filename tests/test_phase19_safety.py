"""Phase 19 — safety & frozen-contract tests.

No setup/experiment/outcome mutation; no Apply/approve/freeze/complete/execute authority; no
AI; no duplicate ranking (Phase 17) / lifecycle (Phase 16) / completion (Phase 18). The only
write is the additive, idempotent campaign-registry metadata capture. DB v26; RULE 46.0.
"""
import inspect

import pytest

from strategy import evidence_saturation as SAT
from strategy import engineering_cost_model as COST
from strategy import campaign_persistence as PER
from strategy import engineering_efficiency_render as REN

PURE = [SAT, COST, PER, REN]


@pytest.mark.parametrize("mod", PURE)
def test_no_forbidden_imports(mod):
    src = inspect.getsource(mod)
    for banned in ("import sqlite3", "PyQt6", "PyQt5", "import requests", "urllib",
                   "import openai", "import anthropic", "socket", "import random",
                   "random.", "time.time", "datetime.now", "from data.session_db"):
        assert banned not in src, f"{mod.__name__}: {banned}"


@pytest.mark.parametrize("mod", PURE)
def test_no_wall_clock(mod):
    """Dates are DATA (passed in); no module reads the clock."""
    src = inspect.getsource(mod)
    for banned in ("date.today", "datetime.today", "utcnow", "time.time", "perf_counter",
                   "monotonic"):
        assert banned not in src, f"{mod.__name__}: {banned}"


def test_no_completion_or_execution_capability():
    """Phase 19 measures; it never completes/freezes/applies/executes/ranks."""
    for mod in (SAT, COST, PER):
        src = inspect.getsource(mod)
        for banned in ("def complete", "def freeze", "def apply", "def approve",
                       "def execute", "mark_applied(", "save_setup(",
                       "create_setup_experiment(", "def build_portfolio",
                       "DIMENSION_WEIGHTS", "def build_campaign_programme"):
            assert banned not in src, f"{mod.__name__}: {banned}"


def test_value_not_recomputed_reuses_phase17():
    """The cost model divides the Phase-17 value; it never derives a value of its own."""
    src = inspect.getsource(COST)
    # value comes verbatim from the experiment's engineering_value
    assert 'experiment.get("engineering_value")' in src
    # no ranking weights / scoring tables live here
    for banned in ("DIMENSION_WEIGHTS", "def rank", "def score_"):
        assert banned not in src


def test_saturation_thresholds_are_named_constants():
    src = inspect.getsource(SAT)
    for name in ("CONFIRMATIONS_FOR_STRONG", "CONFIRMATIONS_FOR_SATURATED",
                 "OVERTESTED_REPEATS", "EXECUTED_FOR_BUILDING"):
        assert name in src


def test_db_version_and_rule_engine():
    from strategy._setup_constants import DB_VERSION, RULE_ENGINE_VERSION
    from data.session_db import SessionDB
    assert DB_VERSION == 27 and RULE_ENGINE_VERSION == "46.0"
    db = SessionDB(":memory:")
    db.build_engineering_efficiency(car="Porsche 911 RSR", track="Fuji")
    assert db._conn.execute("PRAGMA user_version").fetchone()[0] == 27
    db.close()


def test_read_only_build_writes_nothing(tmp_path):
    from data.session_db import SessionDB
    db = SessionDB(str(tmp_path / "s.db"))
    v0 = db._conn.execute("PRAGMA user_version").fetchone()[0]
    reg0 = db._conn.execute(
        "SELECT COUNT(*) FROM engineering_campaign_registry").fetchone()[0]
    dev0 = db._conn.execute(
        "SELECT COUNT(*) FROM engineering_development_records").fetchone()[0]
    # no register_session_id -> pure read
    db.build_engineering_efficiency(car="Porsche 911 RSR", track="Fuji", discipline="Race")
    assert db._conn.execute(
        "SELECT COUNT(*) FROM engineering_campaign_registry").fetchone()[0] == reg0 == 0
    assert db._conn.execute(
        "SELECT COUNT(*) FROM engineering_development_records").fetchone()[0] == dev0 == 0
    assert db._conn.execute("PRAGMA user_version").fetchone()[0] == v0 == 27
    db.close()


def test_registry_capture_touches_only_registry(tmp_path):
    """The opt-in write never touches engineering records / experiments / outcomes."""
    from data.session_db import SessionDB
    from strategy.development_history import MemoryContextKey, build_development_record
    db = SessionDB(str(tmp_path / "w.db"))
    ctx = MemoryContextKey(driver="leon", car="Porsche 911 RSR", track="Fuji", layout_id="fc",
                           discipline="Race", gt7_version="1.49", compound="RH")
    rec = build_development_record(
        {"id": "o", "experiment_id": 10, "status": "confirmed_improvement",
         "confidence_level": "high", "scope_fingerprint": "sf", "test_session_id": "s1",
         "protected": [], "failed_directions": []},
        {"id": 10, "scope_fingerprint": "sf", "changes": [{"field": "arb_front"}]},
        context=ctx, scope_fingerprint="sf", working_windows=[],
        residuals=[{"issue_key": "k", "family": "rotation", "issue_type": "entry_understeer",
                    "axle": "front", "phase": "entry", "segment_id": "T1", "corner_name": "T1",
                    "residual_state": "unchanged", "is_new": False, "is_regression": False,
                    "still_present": True, "protected_good": False, "confidence": "high"}],
        recorded_at="2026-07-01T10:00", session_date="2026-07-01")
    db._persist_development_record(rec, created_at=rec.recorded_at)
    dev = db._conn.execute(
        "SELECT COUNT(*) FROM engineering_development_records").fetchone()[0]
    exp = db._conn.execute("SELECT COUNT(*) FROM setup_experiments").fetchone()[0]
    db.build_engineering_efficiency(
        car="Porsche 911 RSR", track="Fuji", layout_id="fc", discipline="Race", driver="leon",
        gt7_version="1.49", compound="RH", register_session_id="s", recorded_at="2026-07-02",
        now_date="2026-07-02")
    assert db._conn.execute(
        "SELECT COUNT(*) FROM engineering_development_records").fetchone()[0] == dev
    assert db._conn.execute("SELECT COUNT(*) FROM setup_experiments").fetchone()[0] == exp
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
