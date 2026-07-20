"""Phase 27 — safety & frozen-contract tests.

No AI/network/random/wall-clock in the pure layer; no setup generation/values/writes; no
experiment/campaign creation; no scheduler/optimiser; no Apply; no migration/DB mutation; no
duplicate authority logic; canonical enums reused not redefined; missing != negative; blind spot !=
fault; _setup_constants unchanged.
"""
import inspect
import json
import re

import pytest

from strategy import coverage_dimension as CD
from strategy import evidence_coverage as EC
from strategy import knowledge_blind_spot as BS
from strategy import programme_coverage_report as REP
from strategy import programme_coverage_report_render as REN

PURE = [CD, EC, BS, REP, REN]


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
    for mod in (CD, EC, BS, REP):
        src = inspect.getsource(mod)
        for banned in ("def apply", "def optimi", "def schedule", "def create_experiment",
                       "def create_campaign", "def generate_setup", "def copy_setup",
                       "def recommend", "argmax", "heapq", "mark_applied(", "save_setup(",
                       ".commit(", ".execute(", "pit_command", "driver_command"):
            assert banned not in src, f"{mod.__name__}: {banned}"


def test_no_duplicate_authority_or_redefined_enums():
    for mod in (CD, EC, BS, REP):
        src = inspect.getsource(mod)
        assert "def build_knowledge_graph" not in src
        assert "def evaluate_transfer" not in src
        assert "def build_programme_timeline" not in src
        assert "def build_revalidation_report" not in src
        assert "class TransferLevel" not in src
        assert "class ConvergenceStatus" not in src
        assert "class KnowledgeFreshnessStatus" not in src


def test_reuses_canonical_record_domain_mapping():
    """The report reuses the Phase-25 record->domain mapping rather than re-implementing it."""
    src = inspect.getsource(REP)
    assert "_record_domains" in src
    assert "FIELD_DOMAIN_KEYWORDS" not in src   # not re-implemented here


def test_missing_is_distinct_from_regression_everywhere():
    # the two statuses must both exist and never be aliased
    assert CD.CoverageStatus.MISSING.value != CD.CoverageStatus.REGRESSION_ONLY.value
    # a fully-empty domain yields MISSING dims, not REGRESSION_ONLY
    cov = EC.assess_domain_coverage("differential", [],
                                    {"domain": "differential", "convergence_status": "unknown",
                                     "compatible_contexts": 0}, {}).to_dict()
    statuses = {d["status"] for d in cov["dimensions"]}
    assert CD.CoverageStatus.MISSING.value in statuses
    assert CD.CoverageStatus.REGRESSION_ONLY.value not in statuses


def test_report_contains_no_setup_values_and_frames_blind_spots_safely():
    tl = {"source_programme": {"car": "GT-R", "discipline": "race", "gt7_version": "1",
                               "driver": "L"},
          "convergence_summaries": [{"domain": "differential", "convergence_status": "converging",
                                     "independent_support_count": 1, "dependent_support_count": 9,
                                     "regression_count": 0, "conflict_count": 0,
                                     "confirmed_good": True, "compatible_contexts": 1,
                                     "current_maturity": "mature", "current_confidence": "very_high"}],
          "timeline_points": [], "content_fingerprint": "p25"}
    prog = {"compatibility": {}, "content_fingerprint": "p22"}
    reval = {"items": [{"domain": "differential", "freshness_status": "current"}],
             "content_fingerprint": "p26"}
    recs = [{"context": {"track": "Fuji", "car": "GT-R"}, "changes": [{"field": "lsd_accel",
             "to_value": "25"}], "residual_states": [{"family": "traction"}],
             "outcome_status": "confirmed_improvement", "confidence_level": "high"}]
    r = REP.build_programme_evidence_coverage_report(tl, prog, reval, recs).to_dict()
    blob = json.dumps(r)
    assert not re.search(r'"(arb_front|lsd_accel|springs_front|brake_bias)"\s*:\s*-?\d', blob)
    assert "to_value" not in blob
    txt = REN.render_coverage_text(r).lower()
    assert "not a fault" in txt and "untested, never wrong" in txt
    # the safety statement DENIES scheduling; assert no positive scheduling/setup directive appears
    assert "no action is scheduled or applied" in txt
    for positive in ("due date", "expires on", "next test on", "apply the setup", "set the value",
                     "recommended setup", "change the "):
        assert positive not in txt


def test_db_version_unchanged_and_no_write(tmp_path):
    from strategy._setup_constants import DB_VERSION, RULE_ENGINE_VERSION
    from data.session_db import SessionDB
    assert DB_VERSION == 27 and RULE_ENGINE_VERSION == "46.0"
    db = SessionDB(str(tmp_path / "s.db"))
    v0 = db._conn.execute("PRAGMA user_version").fetchone()[0]
    dev0 = db._conn.execute(
        "SELECT COUNT(*) FROM engineering_development_records").fetchone()[0]
    db.build_programme_evidence_coverage_report(car="Porsche 911 RSR (991) '17", track="Fuji",
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
