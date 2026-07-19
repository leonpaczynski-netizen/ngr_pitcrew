"""Phase 21 — safety & frozen-contract tests.

No mutation; no Apply/approve/freeze/complete/execute/schedule authority; no AI/ML/stats/graph
optimisation; no new write (DB stays v26); completion stays Phase-18-governed; every measure
reused (nothing recomputed).
"""
import inspect

import pytest

from strategy import season_development as DEV
from strategy import cross_campaign_map as MAP
from strategy import season_knowledge_map as KMAP
from strategy import season_engineering_report as REP
from strategy import season_engineering_report_render as REN

PURE = [DEV, MAP, KMAP, REP, REN]


@pytest.mark.parametrize("mod", PURE)
def test_no_forbidden_imports(mod):
    src = inspect.getsource(mod)
    for banned in ("import sqlite3", "PyQt6", "PyQt5", "import requests", "urllib",
                   "import openai", "import anthropic", "socket", "import random",
                   "random.", "time.time", "datetime.now", "from data.session_db",
                   "sklearn", "numpy", "scipy", "networkx", "torch", "tensorflow"):
        assert banned not in src, f"{mod.__name__}: {banned}"


@pytest.mark.parametrize("mod", PURE)
def test_no_wall_clock(mod):
    src = inspect.getsource(mod)
    for banned in ("date.today", "datetime.today", "utcnow", "time.time", "perf_counter",
                   "monotonic"):
        assert banned not in src, f"{mod.__name__}: {banned}"


def test_no_scheduling_or_execution_capability():
    for mod in (DEV, MAP, KMAP, REP):
        src = inspect.getsource(mod)
        for banned in ("def schedule", "def complete", "def freeze", "def apply",
                       "def approve", "def execute", "def prioriti", "mark_applied(",
                       "save_setup(", "create_setup_experiment(", ".commit(", ".execute("):
            assert banned not in src, f"{mod.__name__}: {banned}"


def test_no_optimiser_or_graph_search():
    for mod in (DEV, MAP, KMAP, REP):
        src = inspect.getsource(mod)
        for banned in ("def optimi", "argmax", "heapq", "def rank", "dijkstra", "bfs(",
                       "dfs(", "def cluster", "kmeans"):
            assert banned not in src, f"{mod.__name__}: {banned}"


def test_relationships_are_evidence_grounded():
    """Every relationship edge must carry supporting evidence + an authority (no inference)."""
    from strategy.cross_campaign_map import build_cross_campaign_map
    a = {"campaign_id": "A", "family": "rotation", "region": "front", "fields": ["arb_front"],
         "mechanisms": ["m1"], "confidence_level": "medium", "opportunity": "x", "testable": True}
    b = {"campaign_id": "B", "family": "rotation", "region": "front", "fields": ["arb_front"],
         "mechanisms": ["m1"], "confidence_level": "medium", "opportunity": "x", "testable": True}
    m = build_cross_campaign_map([a, b])
    for e in m.to_dict()["edges"]:
        assert e["supporting_evidence"] and e["authority"]


def test_db_version_unchanged_and_no_write(tmp_path):
    from strategy._setup_constants import DB_VERSION, RULE_ENGINE_VERSION
    from data.session_db import SessionDB
    assert DB_VERSION == 26 and RULE_ENGINE_VERSION == "46.0"
    db = SessionDB(str(tmp_path / "s.db"))
    v0 = db._conn.execute("PRAGMA user_version").fetchone()[0]
    reg0 = db._conn.execute(
        "SELECT COUNT(*) FROM engineering_campaign_registry").fetchone()[0]
    dev0 = db._conn.execute(
        "SELECT COUNT(*) FROM engineering_development_records").fetchone()[0]
    db.build_season_engineering_report(car="Porsche 911 RSR", track="Fuji", discipline="Race")
    assert db._conn.execute(
        "SELECT COUNT(*) FROM engineering_campaign_registry").fetchone()[0] == reg0 == 0
    assert db._conn.execute(
        "SELECT COUNT(*) FROM engineering_development_records").fetchone()[0] == dev0 == 0
    assert db._conn.execute("PRAGMA user_version").fetchone()[0] == v0 == 26
    db.close()


def test_completion_stays_phase18_governed():
    """The season view reports Phase-18 status; it never sets/overrides completion."""
    from strategy.season_knowledge_map import classify_campaign_knowledge, SeasonKnowledgeState
    r = classify_campaign_knowledge({"campaign_id": "c", "status": "completed",
                                     "opportunity": "complete", "confidence_level": "very_high",
                                     "executed": 3, "confirmations": 3, "testable": False})
    assert r.state == SeasonKnowledgeState.ENGINEERING_COMPLETE.value


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
