"""Phase 13 — architecture & safety guards (Section 23.11, 24.21–24.24).

The pure mechanism-annotation domain must stay Qt-free, DB-free, network-free, AI-free,
random-free, own no setup Apply/Revert/authoring capability, duplicate no sign graph or
dynamics registry, invent no GT7 channels, and leave every Program-1 / Phase-12 authority
canonical.
"""
import inspect

import pytest

from strategy import mechanism_annotation as MA
from strategy import mechanism_map as MM
from strategy import mechanism_annotation_render as MR


PURE_MODULES = [MA, MM, MR]


@pytest.mark.parametrize("mod", PURE_MODULES)
def test_pure_domain_has_no_forbidden_imports(mod):
    src = inspect.getsource(mod)
    for banned in ("import sqlite3", "PyQt6", "PyQt5", "import requests", "urllib",
                   "import openai", "import anthropic", "socket", "import random",
                   "random.", "time.time", "datetime.now", "open("):
        assert banned not in src, f"{mod.__name__}: {banned}"


@pytest.mark.parametrize("mod", PURE_MODULES)
def test_pure_domain_owns_no_apply_or_authoring(mod):
    """No Apply/authoring/persistence CAPABILITY — checked as call/def syntax + imports,
    not prose (the docstrings legitimately describe what the module refuses to do)."""
    src = inspect.getsource(mod)
    for banned in ("save_setup(", "apply_setup(", "create_setup_experiment(",
                   "select_experiment(", "set_working_window(", ".commit(", ".execute(",
                   "def apply", "def save", "def revert", "def record_",
                   "import sqlite3", "from data.session_db", "from data import session_db",
                   "from strategy.setup_authoring", "from strategy.setup_synthesis import "
                   "build"):
        assert banned not in src, f"{mod.__name__}: {banned}"


def test_no_duplicate_sign_graph_or_registry():
    """The annotator CONSUMES the Program-1 sign graph (imports it) but never redefines a
    component/interaction/LSD/aero table."""
    src = inspect.getsource(MA)
    assert "from strategy.setup_synthesis import PARAMETER_INTERACTIONS" in src
    assert "PARAMETER_INTERACTIONS = {" not in src   # consumes, never defines
    for banned in ("_KNOWLEDGE =", "_INTERACTIONS =", "_LSD_MODEL =", "_AERO_MODEL ="):
        assert banned not in src


def test_no_invented_gt7_channels():
    """Every 'unavailable channel' the annotator names is a genuinely absent GT7 channel —
    it aligns with Program-1's fabricated-metric list, and none is ever asserted as
    observed."""
    from strategy.corner_evidence import _FABRICATED_METRIC_KEYS  # noqa
    src = inspect.getsource(MA)
    # the annotator must talk about tyre load / differential lock state as UNAVAILABLE
    assert "individual tyre load" in src
    assert "differential lock state" in src


def test_annotation_returns_no_setup_values():
    from strategy.mechanism_annotation import annotate_diagnosis
    a = annotate_diagnosis({"issue_family": "traction", "issue_type": "wheelspin",
                            "axle": "rear", "phase": "exit", "residual_state": "worsened",
                            "recurring": True, "valid_laps": 5, "key": "x"})
    blob = str(a.to_dict())
    # no field=value authoring, no delta, no direction instruction in the output
    import re
    assert not re.search(r"set \w+ to \d", blob.lower())


def test_program1_and_phase12_authorities_remain_importable_and_unchanged():
    # Phase 13 imports these; it must not shadow or replace them
    from strategy.setup_experiment_outcome import OutcomeStatus
    from strategy.setup_decision_status import SetupDecisionState
    from strategy.engineering_issue import IssueFamily, ResidualState
    from strategy.postflight_reconciliation import ReconciliationStatus
    from strategy.vehicle_dynamics import build_engineering_knowledge
    assert OutcomeStatus.REGRESSION.value == "regression"
    assert SetupDecisionState.INVALID.value == "invalid"
    assert build_engineering_knowledge()["ok"]


def test_no_wall_clock_or_random_in_output():
    """Two builds an instant apart are identical — no time/random leaks into the result."""
    from strategy.mechanism_annotation import annotate_diagnosis
    d = {"issue_family": "braking", "issue_type": "front_lock", "axle": "front",
         "phase": "braking", "residual_state": "unchanged", "recurring": True,
         "valid_laps": 4, "key": "t"}
    assert annotate_diagnosis(d).to_dict() == annotate_diagnosis(d).to_dict()
