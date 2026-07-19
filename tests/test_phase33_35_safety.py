"""Phases 33-35 — safety & frozen-contract tests."""
import inspect
import json
import os
import re

import pytest

from strategy import assurance_chain_serialization as SER
from strategy import assurance_chain_export as EXP
from strategy import assurance_chain_export_render as EXPR
from strategy import assurance_snapshot_comparison as CMP
from strategy import assurance_snapshot_comparison_render as CMPR
from strategy import assurance_review_package as PKG
from strategy import assurance_review_package_render as PKGR
from strategy import assurance_manifest_loader as LDR
import data.assurance_review_package_writer as WRT

PURE = [SER, EXP, EXPR, CMP, CMPR, PKG, PKGR, LDR]
ALL_MODULES = PURE + [WRT]


@pytest.mark.parametrize("mod", ALL_MODULES)
def test_no_ai_llm_optimiser_scheduler_or_key_imports(mod):
    src = inspect.getsource(mod).lower()
    # actual import/usage tokens (not prose): these must never appear
    for banned in ("import openai", "import anthropic", "langchain", "import requests", "urllib",
                   "import scipy", "scipy.optimize", "import pulp", "ortools", "apscheduler",
                   "import celery", "os.environ[", "os.getenv", "getpass", '["api_key"]',
                   "['api_key']"):
        assert banned not in src, f"{mod.__name__}: {banned}"


@pytest.mark.parametrize("mod", PURE)
def test_pure_modules_have_no_qt_db_wallclock_or_pickle(mod):
    src = inspect.getsource(mod)
    for banned in ("PyQt6", "PyQt5", "import sqlite3", "from data.session_db", "import pickle",
                   "pickle.load", "pickle.dump", "date.today", "datetime.now", "time.time", "random.", "import random"):
        assert banned not in src, f"{mod.__name__}: {banned}"


@pytest.mark.parametrize("mod", PURE)
def test_pure_modules_do_no_file_io(mod):
    src = inspect.getsource(mod)
    for banned in ("open(", "os.remove", "os.rename", "shutil.", "tempfile.", "os.makedirs",
                   ".write(", "zipfile."):
        assert banned not in src, f"{mod.__name__}: {banned} (pure module must not do file I/O)"


def test_no_setup_apply_experiment_campaign_schedule_in_any_module():
    for mod in ALL_MODULES:
        src = inspect.getsource(mod)
        for banned in ("def apply", "mark_applied(", "generate_setup", "def create_experiment",
                       "def create_campaign", "def schedule", "def optimi", "preflight",
                       "def run_experiment", "pit_command", "driver_command"):
            assert banned not in src, f"{mod.__name__}: {banned}"


def test_loader_uses_no_pickle_or_eval():
    src = inspect.getsource(LDR).lower()
    # actual dangerous-usage tokens, not the prose that DENIES them
    assert "import pickle" not in src and "pickle.load" not in src and "pickle.dump" not in src
    assert "eval(" not in src and "exec(" not in src and "__import__(" not in src


def test_export_and_package_contain_no_setup_values():
    from tests._assurance_pack_helpers import synthetic_export
    exp = synthetic_export()
    pkg = PKG.build_review_package_spec(exp).to_dict()
    for blob in (json.dumps(exp), json.dumps(pkg)):
        assert not re.search(r'"(arb_front|lsd_accel|springs_front|brake_bias|ride_height|toe_front)"'
                             r'\s*:\s*-?\d', blob)


def test_written_package_has_no_forbidden_files_or_secrets(tmp_path):
    from tests._assurance_pack_helpers import synthetic_export
    pkg = PKG.build_review_package_spec(synthetic_export())
    dest = str(tmp_path / "out")
    WRT.write_review_package(pkg, dest, make_archive=True)
    for name in os.listdir(dest):
        assert not any(f in name.lower() for f in (".db", ".sqlite", "setup_history", "settings",
                                                   "config.json", "accepted_model", "api"))
        text = open(os.path.join(dest, name), "rb").read().decode("utf-8", errors="replace").lower()
        for secret in ("api_key", "password", "c:\\users", "/home/", ".claude"):
            assert secret not in text


def test_writer_never_writes_without_explicit_destination(tmp_path):
    from tests._assurance_pack_helpers import synthetic_export
    pkg = PKG.build_review_package_spec(synthetic_export())
    assert not WRT.write_review_package(pkg, "").to_dict()["ok"]
    assert not WRT.write_review_package(pkg, None).to_dict()["ok"]


def test_db_version_and_rule_engine_unchanged_and_no_write(tmp_path):
    from strategy._setup_constants import DB_VERSION, RULE_ENGINE_VERSION
    from data.session_db import SessionDB
    assert DB_VERSION == 26 and RULE_ENGINE_VERSION == "46.0"
    db = SessionDB(str(tmp_path / "s.db"))
    v0 = db._conn.execute("PRAGMA user_version").fetchone()[0]
    dev0 = db._conn.execute("SELECT COUNT(*) FROM engineering_development_records").fetchone()[0]
    db.build_assurance_chain_export_report(car="Porsche 911 RSR (991) '17", track="Fuji",
                                           discipline="Race")
    assert db._conn.execute("SELECT COUNT(*) FROM engineering_development_records").fetchone()[0] \
        == dev0 == 0
    assert db._conn.execute("PRAGMA user_version").fetchone()[0] == v0 == 26
    db.close()


def test_setup_constants_byte_identical():
    import subprocess
    out = subprocess.run(["git", "diff", "--stat", "HEAD", "--", "strategy/_setup_constants.py"],
                         capture_output=True, text=True, cwd=".")
    assert out.stdout.strip() == ""


def test_no_schema_migration_added_by_slice():
    import subprocess
    # the slice must not add a migration; DB_VERSION line unchanged vs Phase-31 tip
    out = subprocess.run(["git", "diff", "4b485be", "HEAD", "--", "strategy/_setup_constants.py"],
                         capture_output=True, text=True, cwd=".")
    assert out.stdout.strip() == ""


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
