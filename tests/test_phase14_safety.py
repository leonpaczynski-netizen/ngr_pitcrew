"""Phase 14 — safety & frozen-contract tests (Section 27)."""
import inspect

import pytest

from strategy import intervention_hypothesis as IH
from strategy import intervention_hypothesis_render as IR

PURE = [IH, IR]


@pytest.mark.parametrize("mod", PURE)
def test_pure_no_forbidden_imports(mod):
    src = inspect.getsource(mod)
    for banned in ("import sqlite3", "PyQt6", "PyQt5", "import requests", "urllib",
                   "import openai", "import anthropic", "socket", "import random",
                   "random.", "time.time", "datetime.now", "open("):
        assert banned not in src, f"{mod.__name__}: {banned}"


@pytest.mark.parametrize("mod", PURE)
def test_pure_no_apply_or_authoring_capability(mod):
    src = inspect.getsource(mod)
    for banned in ("save_setup(", "apply_setup(", "create_setup_experiment(",
                   "select_experiment(", "set_working_window(", ".commit(", ".execute(",
                   "def apply", "def approve", "def save", "def revert",
                   "import sqlite3", "from data.session_db"):
        assert banned not in src, f"{mod.__name__}: {banned}"


def test_consumes_not_duplicates_authorities():
    src = inspect.getsource(IH)
    # consumes Phase-12, Phase-13, gearbox authority
    assert "from strategy.vehicle_dynamics import" in src
    assert "from strategy.mechanism_annotation import" in src
    assert "from strategy import gearbox_evidence" in src
    # no shadow sign graph / dynamics / interaction / LSD / aero table
    for banned in ("PARAMETER_INTERACTIONS = {", "_KNOWLEDGE =", "_INTERACTIONS =",
                   "_LSD_MODEL =", "_AERO_MODEL ="):
        assert banned not in src


def test_no_numeric_setup_values_authored():
    from strategy.intervention_hypothesis import build_intervention_hypotheses
    from strategy.mechanism_annotation import annotate_diagnosis
    import re
    a = annotate_diagnosis({"issue_family": "rotation", "issue_type": "entry_understeer",
                            "axle": "front", "phase": "entry", "residual_state": "unchanged",
                            "recurring": True, "valid_laps": 4, "key": "k"})
    blob = str(build_intervention_hypotheses(a.to_dict()).to_dict()).lower()
    assert not re.search(r"set \w+ to \d", blob)


def test_db_version_and_rule_engine_unchanged():
    from strategy._setup_constants import DB_VERSION, RULE_ENGINE_VERSION
    from data.session_db import SessionDB
    assert DB_VERSION == 27 and RULE_ENGINE_VERSION == "46.0"
    db = SessionDB(":memory:")
    db.build_intervention_hypotheses(car="RSR", track="Fuji")
    assert db._conn.execute("PRAGMA user_version").fetchone()[0] == 27
    db.close()


def test_frozen_authorities_still_canonical():
    # Phase 14 must not shadow these
    from strategy.setup_experiment_outcome import OutcomeStatus
    from strategy.working_window import LearnedWorkingWindow
    from strategy.gearbox_evidence import final_drive_lengthens
    from strategy.mechanism_annotation import MechanismStatus
    assert OutcomeStatus.REGRESSION.value == "regression"
    assert final_drive_lengthens(4.25, 4.20) is True
    assert MechanismStatus.SUPPORTED.value == "supported"


def test_no_ai_architecture_still_clean():
    # the repo-wide no-AI guard now also scans the new Phase-14 production modules
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


def test_build_is_read_only_writes_nothing(tmp_path):
    """Building hypotheses must not write to the DB (no new rows, version unchanged)."""
    from data.session_db import SessionDB
    p = str(tmp_path / "s.db")
    db = SessionDB(p)
    before = db._conn.execute(
        "SELECT COUNT(*) FROM engineering_development_records").fetchone()[0]
    db.build_intervention_hypotheses(car="RSR", track="Fuji", discipline="race")
    after = db._conn.execute(
        "SELECT COUNT(*) FROM engineering_development_records").fetchone()[0]
    assert before == after == 0
    assert db._conn.execute("PRAGMA user_version").fetchone()[0] == 27
    db.close()
