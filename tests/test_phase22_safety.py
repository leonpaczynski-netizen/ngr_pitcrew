"""Phase 22 — safety & frozen-contract tests.

No mutation; no Apply/approve/freeze/complete/execute/schedule authority; no AI/ML/graph
libraries/optimisation; no new write (DB stays v26); completion stays Phase-18-governed; unlike
contexts never merged; every field explained (source).
"""
import inspect

import pytest

from strategy import knowledge_maturity as MAT
from strategy import engineering_knowledge_graph as GRAPH
from strategy import multi_event_rollup as ROLL
from strategy import programme_knowledge_report as REP
from strategy import programme_knowledge_report_render as REN

PURE = [MAT, GRAPH, ROLL, REP, REN]


@pytest.mark.parametrize("mod", PURE)
def test_no_forbidden_imports(mod):
    src = inspect.getsource(mod)
    for banned in ("import sqlite3", "PyQt6", "PyQt5", "import requests", "urllib",
                   "import openai", "import anthropic", "socket", "import random",
                   "random.", "time.time", "datetime.now", "from data.session_db",
                   "sklearn", "numpy", "scipy", "networkx", "igraph", "torch", "tensorflow"):
        assert banned not in src, f"{mod.__name__}: {banned}"


@pytest.mark.parametrize("mod", PURE)
def test_no_wall_clock(mod):
    src = inspect.getsource(mod)
    for banned in ("date.today", "datetime.today", "utcnow", "time.time", "perf_counter",
                   "monotonic"):
        assert banned not in src, f"{mod.__name__}: {banned}"


def test_no_scheduling_execution_or_optimisation():
    for mod in (MAT, GRAPH, ROLL, REP):
        src = inspect.getsource(mod)
        for banned in ("def schedule", "def complete", "def freeze", "def apply",
                       "def approve", "def execute", "def prioriti", "def optimi", "argmax",
                       "heapq", "dijkstra", "def cluster", "kmeans", "mark_applied(",
                       "save_setup(", ".commit(", ".execute("):
            assert banned not in src, f"{mod.__name__}: {banned}"


def test_domain_maps_are_visible_constants():
    src = inspect.getsource(GRAPH)
    for name in ("FIELD_DOMAIN_KEYWORDS", "FAMILY_DOMAIN_KEYWORDS", "MECHANISM_DOMAIN_KEYWORDS"):
        assert name in src


def test_unlike_contexts_never_merged():
    from strategy.multi_event_rollup import build_rollup
    events = [{"context": {"car": "RSR", "discipline": "Race", "gt7_version": "1", "driver": "l"},
               "campaigns": [{"campaign_id": "a"}]},
              {"context": {"car": "GT3", "discipline": "Race", "gt7_version": "1", "driver": "l"},
               "campaigns": [{"campaign_id": "b"}]}]
    r = build_rollup(events, primary_context=events[0]["context"]).to_dict()
    # the GT3 event is a SEPARATE group, never merged into the RSR primary
    assert all(c["campaign_id"] != "b" for c in r["primary_group"]["campaigns"])
    assert len(r["other_groups"]) == 1


def test_db_version_unchanged_and_no_write(tmp_path):
    from strategy._setup_constants import DB_VERSION, RULE_ENGINE_VERSION
    from data.session_db import SessionDB
    assert DB_VERSION == 28 and RULE_ENGINE_VERSION == "46.0"
    db = SessionDB(str(tmp_path / "s.db"))
    v0 = db._conn.execute("PRAGMA user_version").fetchone()[0]
    reg0 = db._conn.execute(
        "SELECT COUNT(*) FROM engineering_campaign_registry").fetchone()[0]
    dev0 = db._conn.execute(
        "SELECT COUNT(*) FROM engineering_development_records").fetchone()[0]
    db.build_programme_knowledge_report(car="Porsche 911 RSR", track="Fuji", discipline="Race")
    assert db._conn.execute(
        "SELECT COUNT(*) FROM engineering_campaign_registry").fetchone()[0] == reg0 == 0
    assert db._conn.execute(
        "SELECT COUNT(*) FROM engineering_development_records").fetchone()[0] == dev0 == 0
    assert db._conn.execute("PRAGMA user_version").fetchone()[0] == v0 == 28
    db.close()


def test_completion_stays_phase18_governed():
    """The graph reads the Phase-21 knowledge state; a completed campaign yields COMPLETE
    maturity but the graph never sets/overrides completion itself."""
    from strategy.engineering_knowledge_graph import build_knowledge_graph
    g = build_knowledge_graph([{"campaign_id": "c", "fields": ["lsd_accel"], "mechanisms": [],
                                "family": "traction", "track": "Fuji",
                                "confidence_level": "very_high",
                                "knowledge_state": "engineering_complete", "confirmations": 2,
                                "regressions": 0, "conflicting": False,
                                "unresolved_mechanisms": 0, "executed": 2,
                                "remaining_information_gain": "none", "testable": False}])
    diff = next(d for d in g.to_dict()["domains"] if d["domain"] == "differential")
    assert diff["maturity"]["value"] == "complete"


def test_no_ai_architecture_scans_new_modules():
    import tests.test_no_ai_architecture as gmod
    hits = []
    for path in gmod._production_py_files():
        try:
            text = path.read_text(encoding="utf-8")
        except Exception:
            continue
        for rx, label in gmod._COMPILED:
            if rx.search(text):
                hits.append(f"{path}:{label}")
    assert not hits, hits
