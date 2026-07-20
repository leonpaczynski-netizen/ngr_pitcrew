"""Phase 30 — safety & frozen-contract tests.

No AI/network/random/wall-clock in the pure layer; no setup generation/values/writes; no
experiment/campaign creation; no scheduler/optimiser; no Apply; no migration/DB mutation; no
duplicate authority; facts != assumptions; assumptions only cap readiness (never create it);
conservative bounds labelled; _setup_constants unchanged.
"""
import inspect
import json
import re

import pytest

from strategy import assumption_classification as AC
from strategy import assumption_impact as AI
from strategy import engineering_assumption as EA
from strategy import programme_assumption_register as REP
from strategy import programme_assumption_register_render as REN

PURE = [AC, AI, EA, REP, REN]


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
    for mod in (AC, AI, EA, REP):
        src = inspect.getsource(mod)
        for banned in ("def apply", "def optimi", "def schedule", "def create_experiment",
                       "def create_campaign", "def generate_setup", "def copy_setup",
                       "def recommend", "argmax", "heapq", "mark_applied(", "save_setup(",
                       ".commit(", ".execute(", "pit_command", "driver_command"):
            assert banned not in src, f"{mod.__name__}: {banned}"


def test_no_duplicate_authority_logic():
    for mod in (AC, AI, EA, REP):
        src = inspect.getsource(mod)
        assert "def build_knowledge_graph" not in src
        assert "def build_programme_timeline" not in src
        assert "def build_revalidation_report" not in src


def test_facts_are_not_assumptions():
    # a directly-evidenced domain yields no assumptions
    a = EA.derive_domain_assumptions(
        "differential", {"domain": "differential", "convergence_status": "strongly_converged",
                         "confirmed_good": True, "transfer_limitations": []},
        {"freshness_status": "current"}, {"gap_count": 0}, {"is_open": False})
    assert a == ()


def test_assumptions_only_cap_never_create_readiness():
    # every impact's readiness cap is one of the non-elevating levels; none says HIGH / MEDIUM
    caps = set(AI.IMPACT_READINESS_CAP.values())
    assert caps <= {"not_ready", "context_bound_only", "ready_with_limitations", "ready"}
    # the impact enum has no positive/creating member
    assert "creates" not in inspect.getsource(AI).lower()
    assert "raise_readiness" not in inspect.getsource(AI)


def test_conservative_bound_labelled():
    tl = {"source_programme": {"car": "GT-R", "discipline": "race", "gt7_version": "1",
                               "driver": "L"}, "convergence_summaries": [], "content_fingerprint": "p25"}
    pb = {"knowledge_boundaries": [{"boundary_type": "unverified_transfer_proxy",
                                    "domain": "differential", "target_car": "", "reason": "proxy"}]}
    r = REP.build_programme_assumption_register(tl, {"items": []}, {"domain_coverage": []},
                                                {"contradictions": []}, pb).to_dict()
    assert r["conservative_bounds"] and r["conservative_bounds"][0]["is_conservative_bound"]


def test_report_contains_no_setup_values():
    tl = {"source_programme": {"car": "GT-R", "discipline": "race", "gt7_version": "1",
                               "driver": "L"},
          "convergence_summaries": [{"domain": "differential",
                                     "convergence_status": "stable_but_context_bound",
                                     "confirmed_good": True, "transfer_limitations": []}],
          "content_fingerprint": "p25"}
    reval = {"items": [{"domain": "differential", "freshness_status": "revalidation_required"}]}
    cov = {"domain_coverage": [{"domain": "differential", "gap_count": 3,
                                "dimensions": [{"dimension": "track_variety",
                                                "status": "single_context_only"}]}]}
    r = REP.build_programme_assumption_register(tl, reval, cov, {"contradictions": []},
                                                {"knowledge_boundaries": []}).to_dict()
    blob = json.dumps(r)
    assert not re.search(r'"(arb_front|lsd_accel|springs_front)"\s*:\s*-?\d', blob)
    assert "to_value" not in blob
    txt = REN.render_assumption_text(r).lower()
    assert "no action is scheduled or applied" in txt
    assert "never create readiness" in txt or "cap" in txt


def test_db_version_unchanged_and_no_write(tmp_path):
    from strategy._setup_constants import DB_VERSION, RULE_ENGINE_VERSION
    from data.session_db import SessionDB
    assert DB_VERSION == 27 and RULE_ENGINE_VERSION == "46.0"
    db = SessionDB(str(tmp_path / "s.db"))
    v0 = db._conn.execute("PRAGMA user_version").fetchone()[0]
    dev0 = db._conn.execute(
        "SELECT COUNT(*) FROM engineering_development_records").fetchone()[0]
    db.build_programme_assumption_register(car="Porsche 911 RSR (991) '17", track="Fuji",
                                           discipline="Race")
    assert db._conn.execute(
        "SELECT COUNT(*) FROM engineering_development_records").fetchone()[0] == dev0 == 0
    assert db._conn.execute("PRAGMA user_version").fetchone()[0] == v0 == 27
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
