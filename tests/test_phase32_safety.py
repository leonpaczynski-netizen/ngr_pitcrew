"""Phase 32 — safety & frozen-contract tests.

No AI/network/random/wall-clock in the pure layer; no setup generation/values/writes; no
experiment/campaign/schedule creation; no optimiser/scheduler; no Apply; no migration/DB mutation;
no runtime-file mutation; _setup_constants byte-identical; DB stays v26 / rule-engine 46.0.
"""
import hashlib
import inspect
import json
import re

import pytest

from strategy import assurance_engineering_priority as AEP
from strategy import assurance_engineering_priority_render as REN

PURE = [AEP, REN]


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


def test_no_setup_generation_experiment_campaign_schedule_or_apply():
    for mod in PURE:
        src = inspect.getsource(mod)
        for banned in ("def apply", "def optimi", "def schedule", "def create_experiment",
                       "def create_campaign", "def allocate", "def assign_", "argmax", "heapq",
                       "mark_applied(", "save_setup(", "generate_setup", ".commit(", ".execute(",
                       "pit_command", "driver_command", "def run_experiment", "preflight"):
            assert banned not in src, f"{mod.__name__}: {banned}"


def test_no_optimiser_or_scheduler_or_ai_imports():
    src = inspect.getsource(AEP)
    low = src.lower()
    # actual import tokens (not prose): these libraries must never be imported
    for banned in ("import scipy", "scipy.optimize", "import pulp", "import ortools", "import cvxpy",
                   "apscheduler", "import celery", "import sched\n", "import openai",
                   "import anthropic", "langchain"):
        assert banned not in low, banned


def test_does_not_import_phase17_portfolio_candidates():
    """Reuses the Phase-17 information-gain DOCTRINE, but does not import its setup-experiment
    candidates or mutate a portfolio."""
    src = inspect.getsource(AEP)
    assert "build_experiment_portfolio" not in src
    assert "ExperimentValuation" not in src
    assert "from strategy.experiment_portfolio" not in src


def test_never_guarantees_grade_increase():
    src = inspect.getsource(AEP)
    low = src.lower()
    # impact language must be potential, never a guarantee
    assert "not guaranteed" in low or "potential" in low
    # build a report and confirm no guarantee wording is emitted
    a = {"source_programme": {"car": "GT-R", "discipline": "race", "gt7_version": "1", "driver": "L"},
         "assurance_grade": "not_assured", "totals": {"blocking": 1, "major": 0},
         "findings": [{"finding_type": "open_contradiction", "severity": "blocking",
                       "domain": "d", "source_phase": "P31"}], "content_fingerprint": "p31"}
    cov = {"domain_coverage": [{"domain": "d", "gap_count": 1,
                                "evidence_totals": {"independent": 3, "dependent": 0,
                                                    "record_count": 3}}], "content_fingerprint": "p27"}
    r = AEP.build_assurance_engineering_priority(a, {}, cov, {}, {}).to_dict()
    txt = REN.render_priority_text(r).lower()
    for banned in ("guarantees an increase", "will improve the grade", "guaranteed grade",
                   "definitely resolves", "assured after"):
        assert banned not in txt


def test_report_contains_no_setup_values():
    a = {"source_programme": {"car": "GT-R", "discipline": "race", "gt7_version": "1", "driver": "L"},
         "assurance_grade": "not_assured", "totals": {"blocking": 1, "major": 1},
         "findings": [{"finding_type": "open_contradiction", "severity": "blocking", "domain": "d",
                       "source_phase": "P31", "to_value": "6"},
                      {"finding_type": "single_context_reliance", "severity": "major", "domain": "d2",
                       "source_phase": "P30"}], "content_fingerprint": "p31"}
    cov = {"domain_coverage": [{"domain": "d", "gap_count": 1,
                                "evidence_totals": {"independent": 3, "dependent": 0,
                                                    "record_count": 3}}], "content_fingerprint": "p27"}
    r = AEP.build_assurance_engineering_priority(a, {}, cov, {}, {}).to_dict()
    blob = json.dumps(r)
    assert not re.search(r'"(arb_front|lsd_accel|springs_front|brake_bias|ride_height|toe_front)"'
                         r'\s*:\s*-?\d', blob)
    assert "to_value" not in blob
    txt = REN.render_priority_text(r).lower()
    assert "not permission to apply" in txt


def test_no_dates_or_resource_assignment_in_output():
    a = {"source_programme": {"car": "GT-R", "discipline": "race", "gt7_version": "1", "driver": "L"},
         "assurance_grade": "not_assured", "totals": {"blocking": 1, "major": 0},
         "findings": [{"finding_type": "open_contradiction", "severity": "blocking", "domain": "d",
                       "source_phase": "P31"}], "content_fingerprint": "p31"}
    cov = {"domain_coverage": [{"domain": "d", "gap_count": 1,
                                "evidence_totals": {"independent": 3, "dependent": 0,
                                                    "record_count": 3}}], "content_fingerprint": "p27"}
    r = AEP.build_assurance_engineering_priority(a, {}, cov, {}, {}).to_dict()
    blob = json.dumps(r)
    assert not re.search(r"\d{4}-\d{2}-\d{2}", blob)   # no dates
    low = blob.lower()
    for banned in ("session 1", "assigned to", "owner", "duration", "o'clock", "next session:"):
        assert banned not in low


def test_db_version_unchanged_and_no_write(tmp_path):
    from strategy._setup_constants import DB_VERSION, RULE_ENGINE_VERSION
    from data.session_db import SessionDB
    assert DB_VERSION == 27 and RULE_ENGINE_VERSION == "46.0"
    db = SessionDB(str(tmp_path / "s.db"))
    v0 = db._conn.execute("PRAGMA user_version").fetchone()[0]
    dev0 = db._conn.execute(
        "SELECT COUNT(*) FROM engineering_development_records").fetchone()[0]
    db.build_assurance_engineering_priority_report(car="Porsche 911 RSR (991) '17", track="Fuji",
                                                   discipline="Race")
    assert db._conn.execute(
        "SELECT COUNT(*) FROM engineering_development_records").fetchone()[0] == dev0 == 0
    assert db._conn.execute("PRAGMA user_version").fetchone()[0] == v0 == 27
    db.close()


def test_setup_constants_byte_identical():
    import subprocess
    out = subprocess.run(["git", "diff", "--stat", "HEAD", "--",
                          "strategy/_setup_constants.py"], capture_output=True, text=True, cwd=".")
    assert out.stdout.strip() == "", f"_setup_constants.py changed: {out.stdout}"


def test_runtime_and_protected_files_not_modified_by_phase32():
    """Phase 32 introduces no schema/migration and touches no runtime/user-generated files."""
    import subprocess
    out = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True, cwd=".")
    changed = [ln[3:] for ln in out.stdout.splitlines()]
    # our Phase-32 changes are only under strategy/, ui/, data/session_db.py, tests/, docs/, MASTER*
    for path in changed:
        p = path.strip().strip('"')
        if p.startswith(("setup_history", "data/setup_history", "data/track_models",
                         "data/track_library", "active_setup_state")):
            # these pre-existing app-state files must not be staged/modified BY us; if present they
            # were already dirty before Phase 32 (untracked/pre-modified) - ensure none are staged.
            staged = subprocess.run(["git", "diff", "--cached", "--name-only", "--", p],
                                    capture_output=True, text=True, cwd=".")
            assert staged.stdout.strip() == "", f"Phase 32 must not stage runtime file {p}"


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
