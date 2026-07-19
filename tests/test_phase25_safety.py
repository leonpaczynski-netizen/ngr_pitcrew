"""Phase 25 — safety & frozen-contract tests.

No AI/network/random/wall-clock; no setup generation/values/writes; no experiment/campaign
creation; no scheduler/optimiser; no Apply; no migration/DB mutation/persistence; no duplicate
knowledge graph / transfer logic; TransferLevel not reinterpreted; _setup_constants unchanged.
"""
import inspect
import json

import pytest

from strategy import evidence_independence as IND
from strategy import knowledge_transition as TRN
from strategy import knowledge_timeline as TL
from strategy import knowledge_convergence as CONV
from strategy import programme_timeline_report as REP
from strategy import programme_timeline_report_render as REN

PURE = [IND, TRN, TL, CONV, REP, REN]


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
    for mod in (IND, TRN, TL, CONV, REP):
        src = inspect.getsource(mod)
        for banned in ("def apply", "def optimi", "def schedule", "def create_experiment",
                       "def create_campaign", "def generate_setup", "def copy_setup",
                       "def recommend", "argmax", "heapq", "mark_applied(", "save_setup(",
                       ".commit(", ".execute(", "pit_command", "driver_command"):
            assert banned not in src, f"{mod.__name__}: {banned}"


def test_no_duplicate_graph_or_transfer_logic():
    for mod in (IND, TRN, TL, CONV, REP):
        src = inspect.getsource(mod)
        assert "def build_knowledge_graph" not in src
        assert "def evaluate_transfer" not in src
        assert "class TransferLevel" not in src   # reused, never redefined


def test_creation_time_not_used_as_event_time():
    """The event date must be session_date; recorded_at (creation) must not be read as event
    time."""
    src = inspect.getsource(REP)
    assert "session_date" in src
    assert 'r.get("recorded_at")' not in src and "recorded_at\"]" not in src


def test_timeline_contains_no_setup_field_values(tmp_path):
    prog = {"content_fingerprint": "p", "knowledge_graph": {
        "domains": [{"domain": "differential", "knowledge_state": {"value": "well_understood"},
                     "confidence": {"value": "very_high"}, "maturity": {"value": "complete"},
                     "remaining_uncertainty": {"value": "none"}, "supporting_campaigns": ["c1"],
                     "supporting_experiments": ["lsd_accel"], "supporting_mechanisms": ["load"],
                     "supporting_evidence": {"confirmations": 3, "regressions": 0, "executed": 3},
                     "known_limitations": []}],
        "known_domains": ["differential"], "missing_domains": []},
        "compatibility": {"primary_key": {"car": "Porsche 911 RSR (991) '17", "discipline": "Race",
                          "gt7_version": "1.49", "driver": "leon"}, "other_groups": []}}
    records = [{"record_key": f"r{i}", "test_session_id": f"s{i}", "scope_fingerprint": f"sc{i}",
                "session_date": f"2026-07-0{i}", "outcome_status": "confirmed_improvement",
                "confidence_level": "high", "changes": [{"field": "lsd_accel", "to_value": "25"}],
                "residual_states": [{"family": "traction"}],
                "context": {"car": "Porsche 911 RSR (991) '17", "track": "Fuji",
                            "discipline": "Race"}} for i in (1, 3, 5)]
    tl = REP.build_programme_timeline(prog, {}, records).to_dict()
    blob = json.dumps(tl)
    import re
    assert not re.search(r'"(arb_front|lsd_accel|springs_front|brake_bias|ride_height|toe_front)"'
                         r'\s*:\s*-?\d', blob)
    assert "to_value" not in blob


def test_db_version_unchanged_and_no_write(tmp_path):
    from strategy._setup_constants import DB_VERSION, RULE_ENGINE_VERSION
    from data.session_db import SessionDB
    assert DB_VERSION == 26 and RULE_ENGINE_VERSION == "46.0"
    db = SessionDB(str(tmp_path / "s.db"))
    v0 = db._conn.execute("PRAGMA user_version").fetchone()[0]
    dev0 = db._conn.execute(
        "SELECT COUNT(*) FROM engineering_development_records").fetchone()[0]
    db.build_programme_knowledge_timeline(car="Porsche 911 RSR (991) '17", track="Fuji",
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
