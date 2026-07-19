"""Phase 23 — safety & frozen-contract tests.

No mutation; no setup transfer/import/copy/apply; no AI/ML/optimisation/scheduling; no new write
(DB stays v26); transfer levels decided only by visible deterministic rules; unlike contexts
never transfer.
"""
import inspect

import pytest

from strategy import transfer_rules as RULES
from strategy import knowledge_transfer as XFER
from strategy import engineering_reuse as REUSE
from strategy import programme_transfer_report as REP
from strategy import programme_transfer_report_render as REN

PURE = [RULES, XFER, REUSE, REP, REN]


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


def test_no_setup_transfer_or_apply_capability():
    for mod in (RULES, XFER, REUSE, REP):
        src = inspect.getsource(mod)
        for banned in ("def apply", "def import_setup", "def copy_setup", "def transfer_setup",
                       "def execute", "def schedule", "def optimi", "argmax", "heapq",
                       "mark_applied(", "save_setup(", ".commit(", ".execute(",
                       "def recommend"):
            assert banned not in src, f"{mod.__name__}: {banned}"


def test_transfer_rules_are_visible_constants():
    src = inspect.getsource(RULES)
    assert "TRANSFER_RULES" in src and "DOMAIN_TRANSFER_CLASS" in src
    assert "CATEGORY_KEYWORDS" in src and "DRIVETRAIN_KEYWORDS" in src


def test_unlike_contexts_never_transfer_gearbox():
    """A gearbox observation must not transfer to a different manufacturer."""
    from strategy.knowledge_transfer import evaluate_transfer, TransferLevel
    src = {"domain": "gearbox", "maturity": {"value": "mature"},
           "confidence": {"value": "high"}, "supporting_mechanisms": ["final_drive"],
           "supporting_campaigns": ["c1"], "knowledge_state": {"value": "well_understood"}}
    c = evaluate_transfer(src, {"car": "Porsche 911 RSR (991) '17", "gt7_version": "1.49",
                                "driver": "l"},
                          {"car": "Toyota GR Supra Racing Concept Gr.3", "gt7_version": "1.49",
                           "driver": "l"})
    assert c.transfer_level == TransferLevel.NOT_TRANSFERABLE.value


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
    db.build_programme_transfer_report(car="Porsche 911 RSR (991) '17", track="Fuji",
                                       discipline="Race")
    assert db._conn.execute(
        "SELECT COUNT(*) FROM engineering_campaign_registry").fetchone()[0] == reg0 == 0
    assert db._conn.execute(
        "SELECT COUNT(*) FROM engineering_development_records").fetchone()[0] == dev0 == 0
    assert db._conn.execute("PRAGMA user_version").fetchone()[0] == v0 == 26
    db.close()


def test_reuse_never_recommends_applying():
    """The reuse statements report reusability; they must not say 'apply' / 'import' / 'copy'."""
    src = inspect.getsource(REUSE)
    for banned in ("apply this", "import this", "copy this setup", "you should apply"):
        assert banned not in src.lower()


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
