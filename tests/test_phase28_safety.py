"""Phase 28 — safety & frozen-contract tests.

No AI/network/random/wall-clock in the pure layer; no setup generation/values/writes; no
experiment/campaign creation; no scheduler/optimiser; no Apply; no migration/DB mutation; no
duplicate authority logic; canonical enums reused not redefined; grade is rule-based (no opaque
score); 'ready' never means 'apply this setup'; unvalidated never ready; _setup_constants unchanged.
"""
import inspect
import json
import re

import pytest

from strategy import knowledge_readiness as KR
from strategy import readiness_grade as RG
from strategy import programme_readiness_report as REP
from strategy import programme_readiness_report_render as REN

PURE = [KR, RG, REP, REN]


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
                   "monotonic", "now_date"):
        assert banned not in src, f"{mod.__name__}: {banned}"


def test_no_setup_generation_execution_or_scheduling():
    for mod in (KR, RG, REP):
        src = inspect.getsource(mod)
        for banned in ("def apply", "def optimi", "def schedule", "def create_experiment",
                       "def create_campaign", "def generate_setup", "def copy_setup",
                       "def recommend", "argmax", "heapq", "mark_applied(", "save_setup(",
                       ".commit(", ".execute(", "pit_command", "driver_command"):
            assert banned not in src, f"{mod.__name__}: {banned}"


def test_no_duplicate_authority_or_redefined_enums():
    for mod in (KR, RG, REP):
        src = inspect.getsource(mod)
        assert "def build_knowledge_graph" not in src
        assert "def build_programme_timeline" not in src
        assert "def build_revalidation_report" not in src
        assert "def build_programme_evidence_coverage_report" not in src
        assert "class ConvergenceStatus" not in src
        assert "class KnowledgeFreshnessStatus" not in src
        assert "class CoverageStatus" not in src


def test_grade_is_rule_based_not_opaque_score():
    """The grade must be produced by visible rules over counts, exposing the counts + the rule."""
    src = inspect.getsource(RG)
    assert "rule" in src and "counts" in src
    # no opaque numeric scoring / weighting of an aggregate 'score'
    assert "weight" not in src.lower()
    g = RG.grade_programme([{"readiness_status": "ready"}, {"readiness_status": "ready"},
                            {"readiness_status": "conflicted"}])
    assert set(g) >= {"grade", "counts", "rule", "reasons", "assessable", "relyable", "blocking"}


def test_unvalidated_is_never_ready():
    for conv_status in ("converging", "mixed", "insufficient_evidence", "unknown"):
        item = KR.classify_readiness(
            {"domain": "d", "convergence_status": conv_status, "confirmed_good": False},
            {"freshness_status": "current"}, {"gap_count": 1})
        assert item.readiness_status != KR.KnowledgeReadinessStatus.READY.value


def test_ready_never_means_apply_setup():
    for mod in (KR, REP, REN):
        src = inspect.getsource(mod)
        assert "apply this setup" in src   # only ever in the DENIAL text
    item = KR.classify_readiness({"domain": "d", "convergence_status": "strongly_converged",
                                  "confirmed_good": True, "current_maturity": "mature",
                                  "current_confidence": "high"},
                                 {"freshness_status": "current"}, {"gap_count": 0})
    assert "never 'apply this setup'" in item.no_action_statement


def test_report_contains_no_setup_values():
    tl = {"source_programme": {"car": "GT-R", "discipline": "race", "gt7_version": "1",
                               "driver": "L"},
          "convergence_summaries": [{"domain": "differential",
                                     "convergence_status": "strongly_converged",
                                     "independent_support_count": 3, "confirmed_good": True,
                                     "compatible_contexts": 3, "current_maturity": "mature",
                                     "current_confidence": "high"}],
          "timeline_points": [], "content_fingerprint": "p25"}
    r = REP.build_programme_knowledge_readiness_report(
        tl, {"content_fingerprint": "p22"},
        {"items": [{"domain": "differential", "freshness_status": "current"}]},
        {"domain_coverage": [{"domain": "differential", "gap_count": 0}]}).to_dict()
    blob = json.dumps(r)
    assert not re.search(r'"(arb_front|lsd_accel|springs_front|brake_bias)"\s*:\s*-?\d', blob)
    assert "to_value" not in blob
    txt = REN.render_readiness_text(r).lower()
    assert "no action is scheduled or applied" in txt


def test_db_version_unchanged_and_no_write(tmp_path):
    from strategy._setup_constants import DB_VERSION, RULE_ENGINE_VERSION
    from data.session_db import SessionDB
    assert DB_VERSION == 26 and RULE_ENGINE_VERSION == "46.0"
    db = SessionDB(str(tmp_path / "s.db"))
    v0 = db._conn.execute("PRAGMA user_version").fetchone()[0]
    dev0 = db._conn.execute(
        "SELECT COUNT(*) FROM engineering_development_records").fetchone()[0]
    db.build_programme_knowledge_readiness_report(car="Porsche 911 RSR (991) '17", track="Fuji",
                                                  discipline="Race")
    assert db._conn.execute(
        "SELECT COUNT(*) FROM engineering_development_records").fetchone()[0] == dev0 == 0
    assert db._conn.execute("PRAGMA user_version").fetchone()[0] == v0 == 26
    db.close()


def test_setup_constants_unchanged():
    import subprocess
    out = subprocess.run(["git", "diff", "--stat", "HEAD", "--",
                          "strategy/_setup_constants.py"], capture_output=True, text=True, cwd=".")
    assert out.stdout.strip() == "", f"_setup_constants.py changed: {out.stdout}"


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
