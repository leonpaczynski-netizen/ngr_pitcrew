"""Tests for the "Build Race Plan from This Practice" hand-off (Sprint 10 UI,
determinism rebuild — piece 4).

The MainWindow is far too heavy to construct headless, so the new methods
are exercised as unbound functions against a light stub `self` that carries only
what they read (`_db`). This validates the Practice → Strategy wiring:
  * setup linkage reads the applied-in-GT7 Race checkpoint (piece 2 store);
  * the bundle banner reflects confidence / setup-confirmed / staleness;
  * a bundle is built from a session (empty DB → honest not-ready bundle).

Runs headless (QT_QPA_PLATFORM=offscreen); the banner is grabbed to a PNG.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

pytest.importorskip("PyQt6.QtWidgets")
from PyQt6.QtWidgets import QApplication, QTextEdit  # noqa: E402

from ui.dashboard import MainWindow  # noqa: E402
from data.session_db import SessionDB  # noqa: E402
from data.applied_checkpoint import make_checkpoint  # noqa: E402
from strategy.practice_evidence_bundle import build_practice_evidence_bundle  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


class _Stub:
    """Carries only what the practice-bundle methods read.

    ``_build_practice_evidence_bundle`` calls ``self._practice_bundle_setup_linkage``,
    so borrow that real method onto the stub."""
    _practice_bundle_setup_linkage = MainWindow._practice_bundle_setup_linkage

    def __init__(self, db=None):
        self._db = db


class _Conf:
    def __init__(self, v):
        self.value = v


class _FakeEvidence:
    track = "Fuji"
    layout_id = "full_course"
    race_laps = 12
    race_duration_minutes = 0.0
    fuel_multiplier = 1.0
    tyre_multiplier = 1.0
    refuel_rate_lps = 0.0
    mandatory_pit_stops = 0
    required_compounds = ()
    car_id = 3
    compound_samples = {"RM": [1, 2, 3]}
    evidence_confidence = _Conf("medium")


class _FakeResult:
    evidence = _FakeEvidence()
    missing_evidence = ()
    confidence = _Conf("medium")


_INP = {
    "track": "Fuji", "layout_id": "full_course", "race_laps": 12,
    "race_duration_minutes": 0.0, "fuel_multiplier": 1.0, "tyre_multiplier": 1.0,
    "refuel_rate_lps": 0.0, "car_id": 3, "car_name": "Test Car",
}


def _bundle(confirmed: bool):
    return build_practice_evidence_bundle(
        session_result=_FakeResult(), car_id=3, car_name="Test Car",
        approved_setup_id="7", applied_checkpoint_id="cp_7_abc",
        setup_confirmed_in_gt7=confirmed, session_ids=(5,))


# ── setup linkage reads the piece-2 checkpoint ──────────────────────────────

def test_setup_linkage_no_checkpoint():
    stub = _Stub(SessionDB(":memory:"))
    sid, cid, confirmed = MainWindow._practice_bundle_setup_linkage(stub, _INP)
    assert (sid, cid, confirmed) == ("", "", False)


def test_setup_linkage_with_checkpoint():
    db = SessionDB(":memory:")
    cp = make_checkpoint(setup_id="7", fields={"arb_rear": 4}, confirmed_at="now")
    db.save_applied_checkpoint(3, "Fuji", "full_course", "Race", cp)
    stub = _Stub(db)
    sid, cid, confirmed = MainWindow._practice_bundle_setup_linkage(stub, _INP)
    assert sid == "7" and cid == cp.checkpoint_id and confirmed is True


# ── bundle banner reflects state ────────────────────────────────────────────

def test_banner_confirmed_ready_is_green(qapp):
    stub = _Stub()
    html = MainWindow._practice_bundle_banner_html_for(stub, _bundle(True), _INP)
    assert "#3FA07A" in html  # ok/green border
    assert "confidence" in html.lower()
    assert "Setup confirmed applied in GT7" in html


def test_banner_not_confirmed_warns(qapp):
    stub = _Stub()
    html = MainWindow._practice_bundle_banner_html_for(stub, _bundle(False), _INP)
    assert "NOT confirmed applied in GT7" in html
    # not_confirmed is a staleness reason → rendered as a Stale note.
    assert "Stale:" in html


def test_banner_not_ready_is_danger(qapp):
    # A bundle with no evidence object is not ready for strategy.
    empty = build_practice_evidence_bundle(
        session_result=type("R", (), {"evidence": None, "missing_evidence": ("laps",),
                                       "confidence": _Conf("none")})(),
        car_id=3, car_name="Test Car", setup_confirmed_in_gt7=False)
    stub = _Stub()
    html = MainWindow._practice_bundle_banner_html_for(stub, empty, _INP)
    assert "#E05050" in html  # danger border
    assert "Not enough measured evidence" in html


# ── bundle is built from a session (empty DB → honest not-ready) ────────────

def test_build_bundle_from_empty_session():
    db = SessionDB(":memory:")
    stub = _Stub(db)
    inp = dict(_INP, session_id=0, starting_fuel_pct=100.0,
               pit_loss_seconds=20.0, available_compounds=(), required_compounds=(),
               mandatory_pit_stops=0)
    bundle = MainWindow._build_practice_evidence_bundle(stub, inp)
    assert bundle is not None
    # No laps → not ready, but the object is well-formed and honest.
    assert bundle.is_ready_for_strategy is False
    assert bundle.setup_confirmed_in_gt7 is False


def test_banner_renders_to_png(qapp, tmp_path):
    stub = _Stub()
    html = MainWindow._practice_bundle_banner_html_for(stub, _bundle(False), _INP)
    te = QTextEdit()
    te.setHtml(html)
    te.resize(560, 160)
    png = tmp_path / "bundle_banner.png"
    assert te.grab().save(str(png))
    assert png.exists() and png.stat().st_size > 0
