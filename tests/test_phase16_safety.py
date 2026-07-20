"""Phase 16 — safety & frozen-contract tests.

No duplicate Apply / Experiment / Outcome / Reconciliation / Prediction-Calibration; no
automatic setup changes; no DB writes except through the existing lifecycle; read-only.
"""
import inspect

import pytest

from strategy import experiment_lifecycle as M
from strategy import experiment_lifecycle_render as R

PURE = [M, R]


@pytest.mark.parametrize("mod", PURE)
def test_no_forbidden_imports(mod):
    src = inspect.getsource(mod)
    for banned in ("import sqlite3", "PyQt6", "PyQt5", "import requests", "urllib",
                   "import openai", "import anthropic", "socket", "import random",
                   "random.", "time.time", "datetime.now", "from data.session_db"):
        assert banned not in src, f"{mod.__name__}: {banned}"


def test_no_duplicate_lifecycle_or_apply_or_recording_capability():
    src = inspect.getsource(M)
    # the orchestration must not define its own apply / persistence / outcome / reconciliation
    for banned in ("def create_setup_experiment", "def mark_applied", "def compute_apply_status",
                   "def record_experiment_reconciliation", "def evaluate_outcome",
                   "def build_reconciliation_record", "def apply", "def save", ".commit(",
                   ".execute(", "mark_applied(", "create_setup_experiment("):
        assert banned not in src, banned


def test_connects_existing_authorities_only():
    src = inspect.getsource(M)
    # it CONSUMES the canonical experiment builder; it does not reimplement one
    assert "from strategy.setup_experiment import build_experiment_from_recommendation" in src
    for banned in ("class SetupExperiment", "def build_experiment_from_recommendation(",
                   "APPROVED_STATUSES = "):
        assert banned not in src


def test_no_new_domain_experiment_model():
    # the orchestration objects are not a second experiment model — the canonical experiment
    # remains the real SetupExperiment (schema setup_experiment_v1)
    from strategy.experiment_lifecycle import build_execution_request
    from strategy.mechanism_annotation import annotate_diagnosis
    from strategy.intervention_hypothesis import build_intervention_hypotheses as BIH
    from strategy.experiment_synthesis import synthesize_bounded_experiments as SYN
    from strategy.setup_ranges import resolve_ranges
    from data.applied_checkpoint import compute_setup_hash
    F = {"arb_front": 4, "arb_rear": 4, "brake_bias": 0, "springs_front": 5.0}
    ap = {"car": "Porsche 911 RSR", "track": "Fuji", "layout_id": "fc", "setup_id": "S",
          "name": "B", "revision": 1, "state": "applied", "fields": F, "purpose": "Race"}
    ap["setup_hash"] = compute_setup_hash(F)
    a = annotate_diagnosis({"issue_family": "rotation", "issue_type": "entry_understeer",
                            "axle": "front", "phase": "entry", "residual_state": "unchanged",
                            "recurring": True, "valid_laps": 4, "key": "k"})
    res = SYN(BIH(a.to_dict()).to_dict(), applied_setup=ap,
              session_identity={"car": "Porsche 911 RSR", "track": "Fuji", "layout_id": "fc"},
              ranges=resolve_ranges("Porsche 911 RSR"))
    req = build_execution_request(res.selected_candidate, scope={"track": "Fuji"})
    assert req.setup_experiment["schema_version"] == "setup_experiment_v1"


def test_db_version_and_rule_engine_unchanged():
    from strategy._setup_constants import DB_VERSION, RULE_ENGINE_VERSION
    from data.session_db import SessionDB
    assert DB_VERSION == 27 and RULE_ENGINE_VERSION == "46.0"
    db = SessionDB(":memory:")
    db.build_engineering_lifecycle(car="Porsche 911 RSR", track="Fuji")
    db.build_experiment_execution({}, car="Porsche 911 RSR", track="Fuji")
    assert db._conn.execute("PRAGMA user_version").fetchone()[0] == 27
    db.close()


def test_runtime_path_writes_nothing(tmp_path):
    from data.session_db import SessionDB
    db = SessionDB(str(tmp_path / "s.db"))
    before_exp = db._conn.execute("SELECT COUNT(*) FROM setup_experiments").fetchone()[0]
    before_rec = db._conn.execute(
        "SELECT COUNT(*) FROM engineering_reconciliation_records").fetchone()[0]
    db.build_engineering_lifecycle(car="Porsche 911 RSR", track="Fuji", discipline="Race")
    db.build_experiment_execution({"status": "ready_for_preflight",
                                   "deltas": [{"field": "arb_front", "baseline_value": 4,
                                               "candidate_value": 3, "direction": "soften",
                                               "is_exactly_one_step": True}],
                                   "baseline": {"setup_id": "S"}, "canonical_issue": {},
                                   "test_protocol": {}}, car="Porsche 911 RSR", track="Fuji")
    assert db._conn.execute("SELECT COUNT(*) FROM setup_experiments").fetchone()[0] == before_exp
    assert db._conn.execute(
        "SELECT COUNT(*) FROM engineering_reconciliation_records").fetchone()[0] == before_rec
    db.close()


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
