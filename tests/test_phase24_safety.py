"""Phase 24 — safety & frozen-contract tests.

No setup writes / experiment / campaign creation; no Apply / optimiser / scheduler; no AI /
network / random / wall-clock; no migration / DB mutation / persistence; no setup values in the
playbook; _setup_constants unchanged; runtime state unchanged.
"""
import inspect
import json

import pytest

from strategy import knowledge_boundary as BND
from strategy import stable_themes as THM
from strategy import investigation_priority as PRI
from strategy import new_programme_brief as BRF
from strategy import engineering_playbook as PB
from strategy import engineering_playbook_render as REN

PURE = [BND, THM, PRI, BRF, PB, REN]


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
                   "monotonic", "recorded_at", "created_at"):
        assert banned not in src, f"{mod.__name__}: {banned}"


def test_no_setup_generation_or_execution():
    for mod in (BND, THM, PRI, BRF, PB):
        src = inspect.getsource(mod)
        for banned in ("def apply", "def optimi", "def schedule", "def create_experiment",
                       "def create_campaign", "def generate_setup", "def copy_setup",
                       "def transfer_setup", "def recommend_setup", "argmax", "heapq",
                       "mark_applied(", "save_setup(", ".commit(", ".execute("):
            assert banned not in src, f"{mod.__name__}: {banned}"


def test_no_second_knowledge_graph_or_transfer_logic():
    """Phase 24 must not rebuild a knowledge graph or re-implement Phase-23 transfer decisions."""
    for mod in (BND, THM, PRI, BRF, PB):
        src = inspect.getsource(mod)
        assert "def build_knowledge_graph" not in src
        assert "def evaluate_transfer" not in src
        assert "DOMAIN_DOMAIN_KEYWORDS" not in src


def test_transfer_levels_named_constants_reused():
    """Stable themes must reuse the Phase-23 TransferLevel enum, not invent new levels."""
    src = inspect.getsource(THM)
    assert "from strategy.knowledge_transfer import TransferLevel" in src


def test_playbook_contains_no_setup_field_values():
    prog = {"content_fingerprint": "p", "knowledge_graph": {
        "domains": [{"domain": "differential", "knowledge_state": {"value": "well_understood"},
                     "confidence": {"value": "very_high"}, "maturity": {"value": "complete"},
                     "remaining_uncertainty": {"value": "none"}, "supporting_campaigns": ["c1"],
                     "supporting_experiments": ["lsd_accel"], "supporting_mechanisms": ["load"],
                     "supporting_evidence": {"confirmations": 2, "regressions": 0, "executed": 2},
                     "known_limitations": []}],
        "known_domains": ["differential"], "missing_domains": []},
        "compatibility": {"primary_key": {"car": "Porsche 911 RSR (991) '17", "discipline": "Race",
                          "gt7_version": "1.49", "driver": "leon"}, "other_groups": []}}
    pb = PB.build_engineering_playbook(prog, {"candidates": []}).to_dict()
    blob = json.dumps(pb)
    import re
    # no "setup_field": number assignments and no numeric starting-setup recommendation
    assert not re.search(r'"(arb_front|arb_rear|lsd_accel|lsd_decel|springs_front|brake_bias|'
                         r'ride_height|toe_front|camber_front|dampers)"\s*:\s*-?\d', blob)
    assert "starting setup" not in blob.lower() or "not a baseline setup" in blob.lower()


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
    db.build_programme_engineering_playbook(car="Porsche 911 RSR (991) '17", track="Fuji",
                                            discipline="Race")
    assert db._conn.execute(
        "SELECT COUNT(*) FROM engineering_campaign_registry").fetchone()[0] == reg0 == 0
    assert db._conn.execute(
        "SELECT COUNT(*) FROM engineering_development_records").fetchone()[0] == dev0 == 0
    assert db._conn.execute("PRAGMA user_version").fetchone()[0] == v0 == 26
    db.close()


def test_setup_constants_unchanged():
    """The Apply-gate constants file must be byte-identical to the Phase-23 tip."""
    import subprocess
    out = subprocess.run(["git", "diff", "--stat", "HEAD", "--",
                          "strategy/_setup_constants.py"], capture_output=True, text=True,
                         cwd=".")
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
