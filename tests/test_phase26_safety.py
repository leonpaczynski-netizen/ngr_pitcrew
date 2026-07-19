"""Phase 26 — safety & frozen-contract tests.

No AI/network/random/wall-clock in the pure layer; no setup generation/values/writes; no
experiment/campaign creation; no scheduler/optimiser/reminder/future-date; no Apply; no
migration/DB mutation/persistence; no duplicate graph/transfer/timeline logic; canonical enums
reused not redefined; _setup_constants unchanged.
"""
import inspect
import json
import re

import pytest

from strategy import revalidation_reason as RSN
from strategy import knowledge_decay as DEC
from strategy import revalidation_status as RST
from strategy import programme_revalidation_report as REP
from strategy import programme_revalidation_report_render as REN

PURE = [RSN, DEC, RST, REP, REN]


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
    for mod in (RSN, DEC, RST, REP):
        src = inspect.getsource(mod)
        for banned in ("def apply", "def optimi", "def schedule", "def create_experiment",
                       "def create_campaign", "def generate_setup", "def copy_setup",
                       "def recommend", "argmax", "heapq", "mark_applied(", "save_setup(",
                       ".commit(", ".execute(", "pit_command", "driver_command"):
            assert banned not in src, f"{mod.__name__}: {banned}"


def test_no_duplicate_authority_logic():
    for mod in (RSN, DEC, RST, REP):
        src = inspect.getsource(mod)
        assert "def build_knowledge_graph" not in src
        assert "def evaluate_transfer" not in src
        assert "def build_programme_timeline" not in src
        assert "class TransferLevel" not in src       # reused, never redefined
        assert "class ConvergenceStatus" not in src   # reused, never redefined


def test_age_alone_never_decays_is_documented_and_enforced():
    """No fixed-expiry / 'older than N days' rule anywhere in the pure layer: there is no date
    arithmetic at all, so age cannot mechanically decay knowledge."""
    for mod in (DEC, RST, REP):
        src = inspect.getsource(mod)
        for banned in ("timedelta", "days_since", "age_days", "fromisoformat", "strptime",
                       "> 30", ">= 30", "expiry_days", "max_age"):
            assert banned not in src, f"{mod.__name__}: {banned}"


def test_report_contains_no_setup_field_values():
    timeline = {"source_programme": {"car": "GT-R", "discipline": "race", "gt7_version": "1.0",
                                     "driver": "L"},
                "convergence_summaries": [{"domain": "differential",
                                           "convergence_status": "strongly_converged",
                                           "independent_support_count": 3,
                                           "dependent_support_count": 0, "regression_count": 0,
                                           "conflict_count": 0, "transfer_limitations": [],
                                           "retired_directions": [], "confirmed_good": True,
                                           "current_maturity": "complete",
                                           "current_confidence": "very_high",
                                           "compatible_contexts": 2}],
                "timeline_points": [{"knowledge_domain": "differential",
                                     "evidence_date": "2026-01-01"}],
                "content_fingerprint": "p25:x"}
    prog = {"compatibility": {}, "content_fingerprint": "p22:y"}
    r = REP.build_revalidation_report(timeline, prog).to_dict()
    blob = json.dumps(r)
    assert not re.search(r'"(arb_front|lsd_accel|springs_front|brake_bias|ride_height|toe_front)"'
                         r'\s*:\s*-?\d', blob)
    assert "to_value" not in blob
    # The safety statement explicitly DENIES scheduling/reminders; assert those denials are present
    # (the report states no action is scheduled), and no positive future-date field is emitted.
    txt = REN.render_revalidation_text(r).lower()
    assert "no action is scheduled or applied" in txt
    assert "schedules nothing" in txt
    for positive in ("due date", "expires on", "next test on", "re-test by", "revalidate by"):
        assert positive not in txt


def test_db_version_unchanged_and_no_write(tmp_path):
    from strategy._setup_constants import DB_VERSION, RULE_ENGINE_VERSION
    from data.session_db import SessionDB
    assert DB_VERSION == 26 and RULE_ENGINE_VERSION == "46.0"
    db = SessionDB(str(tmp_path / "s.db"))
    v0 = db._conn.execute("PRAGMA user_version").fetchone()[0]
    dev0 = db._conn.execute(
        "SELECT COUNT(*) FROM engineering_development_records").fetchone()[0]
    db.build_programme_revalidation_report(car="Porsche 911 RSR (991) '17", track="Fuji",
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
