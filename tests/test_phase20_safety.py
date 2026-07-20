"""Phase 20 — safety & frozen-contract tests.

No setup/experiment/outcome/record mutation; no Apply/approve/freeze/complete/execute
authority; no AI; no optimiser / ranking / auto-prioritisation; no new write (DB stays v26);
value reused from Phase 17/19 (never recomputed); completion stays Phase-18-governed.
"""
import inspect

import pytest

from strategy import knowledge_confidence as KC
from strategy import development_roi as ROI
from strategy import campaign_opportunity as OPP
from strategy import knowledge_quality as KQ
from strategy import engineering_knowledge_quality_render as REN

PURE = [KC, ROI, OPP, KQ, REN]


@pytest.mark.parametrize("mod", PURE)
def test_no_forbidden_imports(mod):
    src = inspect.getsource(mod)
    for banned in ("import sqlite3", "PyQt6", "PyQt5", "import requests", "urllib",
                   "import openai", "import anthropic", "socket", "import random",
                   "random.", "time.time", "datetime.now", "from data.session_db"):
        assert banned not in src, f"{mod.__name__}: {banned}"


@pytest.mark.parametrize("mod", PURE)
def test_no_wall_clock(mod):
    src = inspect.getsource(mod)
    for banned in ("date.today", "datetime.today", "utcnow", "time.time", "perf_counter",
                   "monotonic"):
        assert banned not in src, f"{mod.__name__}: {banned}"


def test_no_completion_or_execution_capability():
    for mod in (KC, ROI, OPP, KQ):
        src = inspect.getsource(mod)
        for banned in ("def complete", "def freeze", "def apply", "def approve",
                       "def execute", "mark_applied(", "save_setup(",
                       "create_setup_experiment(", ".commit(", ".execute("):
            assert banned not in src, f"{mod.__name__}: {banned}"


def test_not_an_optimiser_no_ranking():
    """Phase 20 measures; it must not sort / rank / prioritise campaigns automatically."""
    for mod in (ROI, OPP, KQ):
        src = inspect.getsource(mod)
        for banned in ("sorted(", ".sort(", "def rank", "def prioriti", "heapq",
                       "DIMENSION_WEIGHTS", "argmax", "def optimi"):
            assert banned not in src, f"{mod.__name__}: {banned}"


def test_value_and_cost_reused_not_recomputed():
    """ROI reuses Phase-19 info gain + cost; it must not re-derive them."""
    src = inspect.getsource(ROI)
    assert 'campaign_efficiency.get("estimated_remaining_laps")' in src
    assert "INFO_GAIN_SCALE" in src
    for banned in ("def estimate_experiment_cost", "warmup", "TYRE_LAPS_PER_SET"):
        assert banned not in src


def test_thresholds_are_named_constants():
    src = inspect.getsource(KC)
    for name in ("MIN_CONFIRMATIONS_HIGH", "MIN_REPEATABILITY", "MAX_ALLOWED_CONTRADICTIONS",
                 "CONTRADICTION_FULL_PENALTY", "MECHANISM_FULL_PENALTY",
                 "MIN_PREDICTION_ACCURACY_HIGH"):
        assert name in src


def test_db_version_unchanged_and_no_write(tmp_path):
    from strategy._setup_constants import DB_VERSION, RULE_ENGINE_VERSION
    from data.session_db import SessionDB
    assert DB_VERSION == 27 and RULE_ENGINE_VERSION == "46.0"
    db = SessionDB(str(tmp_path / "s.db"))
    v0 = db._conn.execute("PRAGMA user_version").fetchone()[0]
    reg0 = db._conn.execute(
        "SELECT COUNT(*) FROM engineering_campaign_registry").fetchone()[0]
    dev0 = db._conn.execute(
        "SELECT COUNT(*) FROM engineering_development_records").fetchone()[0]
    db.build_engineering_knowledge_quality(car="Porsche 911 RSR", track="Fuji",
                                           discipline="Race")
    assert db._conn.execute(
        "SELECT COUNT(*) FROM engineering_campaign_registry").fetchone()[0] == reg0 == 0
    assert db._conn.execute(
        "SELECT COUNT(*) FROM engineering_development_records").fetchone()[0] == dev0 == 0
    assert db._conn.execute("PRAGMA user_version").fetchone()[0] == v0 == 27
    db.close()


def test_completion_stays_phase18_governed():
    """The opportunity layer reads Phase-18 status; it never sets/overrides completion."""
    from strategy.campaign_opportunity import classify_campaign_opportunity, CampaignOpportunity
    # a COMPLETED campaign is reported COMPLETE regardless of remaining signals
    ce = {"campaign_id": "c", "status": "completed",
          "saturation": {"status": "building", "signals": {"executed": 3, "confirmations": 3,
                         "remaining_untested_experiments": 4,
                         "remaining_discriminating_experiments": 2,
                         "unresolved_mechanisms": 2, "regressions": 0}}}
    r = classify_campaign_opportunity(ce, {"overall_level": "medium"}, {})
    assert r.opportunity == CampaignOpportunity.COMPLETE.value


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
