"""Phase 31 — safety & frozen-contract tests.

No AI/network/random/wall-clock in the pure layer; no setup generation/values/writes; no
experiment/campaign creation; no scheduler/optimiser; no Apply; no migration/DB mutation; no
duplicate authority; a single blocking finding prevents ASSURED; grade rule-based (no opaque score);
_setup_constants unchanged.
"""
import inspect
import json
import re

import pytest

from strategy import assurance_finding as AF
from strategy import assurance_grade as AG
from strategy import knowledge_assurance as KA
from strategy import programme_assurance_report as REP
from strategy import programme_assurance_report_render as REN

PURE = [AF, AG, KA, REP, REN]


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
                   "time.monotonic", ".monotonic(", "now_date"):
        assert banned not in src, f"{mod.__name__}: {banned}"


def test_no_setup_generation_execution_or_scheduling():
    for mod in (AF, AG, KA, REP):
        src = inspect.getsource(mod)
        for banned in ("def apply", "def optimi", "def schedule", "def create_experiment",
                       "def create_campaign", "def generate_setup", "def copy_setup",
                       "def recommend", "argmax", "heapq", "mark_applied(", "save_setup(",
                       ".commit(", ".execute(", "pit_command", "driver_command"):
            assert banned not in src, f"{mod.__name__}: {banned}"


def test_no_duplicate_authority_logic():
    for mod in (AF, AG, KA, REP):
        src = inspect.getsource(mod)
        assert "def build_knowledge_graph" not in src
        assert "def build_programme_timeline" not in src
        assert "def build_programme_knowledge_readiness_report" not in src


def test_blocking_prevents_assured_and_grade_is_rule_based():
    g = AG.grade_assurance([{"severity": "blocking"}], True)
    assert g["grade"] == "not_assured"
    assert set(g) >= {"grade", "counts", "rule", "reasons"}
    # no opaque numeric weighting of an aggregate score
    s = inspect.getsource(AG).lower()
    assert "weight" not in s


def test_defects_are_recognised_finding_types():
    for name in ("hidden_assumption", "open_contradiction", "unresolved_regression",
                 "missing_transfer_boundary", "non_deterministic_output", "data_mutation_detected"):
        assert any(f.value == name for f in AF.AssuranceFindingType)


def test_report_contains_no_setup_values():
    readiness = {"source_programme": {"car": "GT-R", "discipline": "race", "gt7_version": "1",
                                      "driver": "L"},
                 "items": [{"domain": "differential", "readiness_status": "conflicted"}],
                 "content_fingerprint": "p28"}
    contra = {"open_contradictions": [{"domain": "differential", "rationale": "open"}],
              "content_fingerprint": "p29"}
    r = REP.build_programme_assurance_report(readiness, contra,
                                             {"assumptions": [{"domain": "differential",
                                              "assumption_type": "x", "impact": "informational",
                                              "to_value": "6"}], "content_fingerprint": "p30"},
                                             {"content_fingerprint": "p27"},
                                             {"content_fingerprint": "p26"}).to_dict()
    blob = json.dumps(r)
    assert not re.search(r'"(arb_front|lsd_accel|springs_front)"\s*:\s*-?\d', blob)
    txt = REN.render_assurance_text(r).lower()
    assert "no action is scheduled or applied" in txt
    assert "prevents assured" in txt


def test_db_version_unchanged_and_no_write(tmp_path):
    from strategy._setup_constants import DB_VERSION, RULE_ENGINE_VERSION
    from data.session_db import SessionDB
    assert DB_VERSION == 28 and RULE_ENGINE_VERSION == "46.0"
    db = SessionDB(str(tmp_path / "s.db"))
    v0 = db._conn.execute("PRAGMA user_version").fetchone()[0]
    dev0 = db._conn.execute(
        "SELECT COUNT(*) FROM engineering_development_records").fetchone()[0]
    db.build_programme_assurance_report(car="Porsche 911 RSR (991) '17", track="Fuji",
                                        discipline="Race")
    assert db._conn.execute(
        "SELECT COUNT(*) FROM engineering_development_records").fetchone()[0] == dev0 == 0
    assert db._conn.execute("PRAGMA user_version").fetchone()[0] == v0 == 28
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
