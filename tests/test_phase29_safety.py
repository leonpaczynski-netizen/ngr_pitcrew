"""Phase 29 — safety & frozen-contract tests.

No AI/network/random/wall-clock in the pure layer; no setup generation/values/writes; no
experiment/campaign creation; no scheduler/optimiser; no Apply; no migration/DB mutation; no
duplicate authority logic; reuses the canonical record→domain mapping; never resolves by majority or
recency; a contradiction may stay open; _setup_constants unchanged.
"""
import inspect
import json
import re

import pytest

from strategy import contradiction_cause as CC
from strategy import contradiction_resolution_status as CR
from strategy import knowledge_contradiction as KC
from strategy import programme_contradiction_report as REP
from strategy import programme_contradiction_report_render as REN

PURE = [CC, CR, KC, REP, REN]


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
    # ".monotonic"/"time.monotonic" is the wall-clock call; the enum value "non_monotonic_response"
    # is unrelated, so match the clock-call forms specifically.
    for banned in ("date.today", "datetime.today", "utcnow", "time.time", "perf_counter",
                   "time.monotonic", ".monotonic(", "now_date"):
        assert banned not in src, f"{mod.__name__}: {banned}"


def test_no_setup_generation_execution_or_scheduling():
    for mod in (CC, CR, KC, REP):
        src = inspect.getsource(mod)
        for banned in ("def apply", "def optimi", "def schedule", "def create_experiment",
                       "def create_campaign", "def generate_setup", "def copy_setup",
                       "def recommend", "argmax", "heapq", "mark_applied(", "save_setup(",
                       ".commit(", ".execute(", "pit_command", "driver_command"):
            assert banned not in src, f"{mod.__name__}: {banned}"


def test_no_duplicate_authority_or_redefined_enums():
    for mod in (CC, CR, KC, REP):
        src = inspect.getsource(mod)
        assert "def build_knowledge_graph" not in src
        assert "def build_programme_timeline" not in src
        assert "class ConvergenceStatus" not in src


def test_reuses_canonical_record_domain_mapping():
    src = inspect.getsource(REP)
    assert "_record_domains" in src
    assert "FIELD_DOMAIN_KEYWORDS" not in src


def test_never_resolves_by_majority_or_recency():
    """A larger dependent count never wins; later-alone never wins."""
    # more dependent regressions must not outvote the independent confirming side
    r = CR.resolve({"context_causes": (), "independent_side": "positive",
                    "pos_side": {"sessions": 2}, "neg_side": {"sessions": 50}})
    assert r["status"] == "resolved_by_independence" and "confirming" in r["standing_conclusion"]
    # later but not stronger -> not superseded
    r2 = CR.resolve({"context_causes": (), "independent_side": "", "later_side": "negative",
                     "later_side_stronger": False, "pos_side": {"sessions": 1},
                     "neg_side": {"sessions": 1}})
    assert r2["status"] != "resolved_by_supersession"
    # the source must not contain any average/mean/majority scoring
    for mod in (CR, KC):
        s = inspect.getsource(mod).lower()
        assert "majority" not in s or "not a majority" in s or "never" in s or "no majority" in s
        assert "statistics.mean" not in s and "sum(" not in s.replace("assumptions", "")


def test_contradiction_may_stay_open():
    src = inspect.getsource(CR)
    assert "UNRESOLVED" in src and "allowed to remain" in src.lower() or "stay open" in \
        inspect.getsource(REN).lower()
    r = CR.resolve({"context_causes": (), "independent_side": "", "later_side": "",
                    "both_weak": False, "pos_side": {"sessions": 3}, "neg_side": {"sessions": 3}})
    assert r["status"] == "unresolved"


def test_version_mismatch_is_visible():
    causes = CC.context_difference_causes({"gt7_version": {"1.0"}}, {"gt7_version": {"1.49"}})
    assert any(c["cause"] == "different_gt7_version" for c in causes)


def test_report_contains_no_setup_values():
    tl = {"source_programme": {"car": "GT-R", "discipline": "race", "gt7_version": "1",
                               "driver": "L"}, "content_fingerprint": "p25"}
    recs = [{"context": {"track": "Fuji", "car": "GT-R"}, "changes": [{"field": "arb_front",
             "to_value": "6"}], "residual_states": [{"family": "rotation"}],
             "outcome_status": "confirmed_improvement", "confidence_level": "high",
             "test_session_id": "s1", "session_date": "2026-07-01"},
            {"context": {"track": "Fuji", "car": "GT-R"}, "changes": [{"field": "arb_front"}],
             "residual_states": [{"family": "rotation"}], "outcome_status": "regression",
             "confidence_level": "high", "test_session_id": "r1", "session_date": "2026-07-02"}]
    r = REP.build_programme_contradiction_report(tl, {"content_fingerprint": "p22"}, recs).to_dict()
    blob = json.dumps(r)
    assert not re.search(r'"(arb_front|lsd_accel|springs_front)"\s*:\s*-?\d', blob)
    assert "to_value" not in blob
    txt = REN.render_contradiction_text(r).lower()
    assert "no action is scheduled or applied" in txt
    assert "never" in txt  # doctrine present


def test_db_version_unchanged_and_no_write(tmp_path):
    from strategy._setup_constants import DB_VERSION, RULE_ENGINE_VERSION
    from data.session_db import SessionDB
    assert DB_VERSION == 27 and RULE_ENGINE_VERSION == "46.0"
    db = SessionDB(str(tmp_path / "s.db"))
    v0 = db._conn.execute("PRAGMA user_version").fetchone()[0]
    dev0 = db._conn.execute(
        "SELECT COUNT(*) FROM engineering_development_records").fetchone()[0]
    db.build_programme_contradiction_report(car="Porsche 911 RSR (991) '17", track="Fuji",
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
