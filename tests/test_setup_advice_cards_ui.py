"""Tests for the structured setup-advice cards rendered into the Setup Builder
result panel (Sprint 10 UI, determinism rebuild — piece 3).

Three layers:
  * ``_advice_cards_to_html`` — pure card-list → themed HTML (no Qt).
  * ``_build_setup_advice_cards`` — payload → SetupDecision → AdviceCard list.
  * ``_display_setup_result`` — the structured block renders above the legacy
    analysis without disturbing the existing (tightly-tested) sections.

Runs headless (QT_QPA_PLATFORM=offscreen); a PNG of an approved result is grabbed.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

pytest.importorskip("PyQt6.QtWidgets")
from PyQt6.QtWidgets import QApplication, QTextEdit  # noqa: E402

from ui.setup_builder_ui import SetupBuilderMixin, _advice_cards_to_html  # noqa: E402
from ui.setup_form_widget import SetupFormWidget  # noqa: E402
from ui.setup_advice_render import AdviceCard  # noqa: E402
from strategy.setup_decision import DecisionStatus  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


class _StubHost(SetupBuilderMixin):
    def __init__(self):
        self._setup_result_text = QTextEdit()
        self._config = {}
        self._last_setup_context = None
        self._last_setup_ai_fields = {}

    def _build_setup_context(self, **kwargs):
        return None

    def _active_config_id(self):
        return None


def _payload(status="approved", changes=None, rejected=None, fields=None,
             protected=None, eng_failed=False):
    p = {
        "analysis": "Rear axle loses traction on power out of slow corners.",
        "primary_issue": "traction",
        "changes": changes or [],
        "setup_fields": fields or {},
        "rejected_changes": rejected or [],
        "validation_errors": [],
        "validation_warnings": [],
        "engineering_validation_errors": [],
        "engineering_validation_failed": eng_failed,
        "protected_fields": protected or [],
    }
    if status is not None:
        p["recommendation_status"] = status
    return json.dumps(p)


# ── Pure card → HTML ────────────────────────────────────────────────────────

def test_cards_to_html_empty():
    assert _advice_cards_to_html([]) == ""


def test_cards_to_html_renders_banner_and_table():
    cards = [
        AdviceCard(kind="banner", title="Approved — apply the changes below",
                   tone="ok", lines=("do it",)),
        AdviceCard(kind="approved", title="Approved changes", tone="ok",
                   rows=(("Rear ARB", "reduce mid-corner push"),)),
    ]
    html = _advice_cards_to_html(cards)
    assert "Approved — apply the changes below" in html
    assert "Approved changes" in html
    assert "Rear ARB" in html
    assert "reduce mid-corner push" in html
    # ok tone colour is used.
    assert "#3FA07A" in html


def test_cards_to_html_danger_tone_colour():
    cards = [AdviceCard(kind="rejected", title="Rejected", tone="danger",
                        rows=(("lsd_accel", "unsafe"),))]
    html = _advice_cards_to_html(cards)
    assert "#E05050" in html and "Rejected" in html


# ── payload → cards ─────────────────────────────────────────────────────────

def test_build_cards_approved(qapp):
    host = _StubHost()
    data = json.loads(_payload(
        changes=[{"setting": "Rear ARB", "field": "arb_rear", "why": "plant the rear"}],
        fields={"arb_rear": 4}))
    cards = host._build_setup_advice_cards(
        data, approved_changes=data["changes"], rejected_changes=[],
        protected_fields=[], validation_failed=False, status_approved=True)
    kinds = [c.kind for c in cards]
    assert kinds[0] == "banner"
    assert "approved" in kinds
    approved = next(c for c in cards if c.kind == "approved")
    assert approved.rows[0][0] == "Rear ARB"


def test_build_cards_engineering_failure(qapp):
    host = _StubHost()
    data = json.loads(_payload(status="validation_failed", eng_failed=True))
    cards = host._build_setup_advice_cards(
        data, approved_changes=[], rejected_changes=[],
        protected_fields=[], validation_failed=True, status_approved=False)
    banner = cards[0]
    assert banner.tone == "danger"
    assert "validation failed" in banner.title.lower()


def test_build_cards_rejected_and_preserved(qapp):
    host = _StubHost()
    data = json.loads(_payload(
        status="blocked_no_safe_recommendation",
        rejected=[{"field": "lsd_accel", "reason": "outside working window"}],
        protected=["brake_bias"]))
    cards = host._build_setup_advice_cards(
        data, approved_changes=[], rejected_changes=data["rejected_changes"],
        protected_fields=["brake_bias"], validation_failed=False,
        status_approved=False)
    kinds = {c.kind for c in cards}
    assert "rejected" in kinds and "preserved" in kinds


# ── Integration through _display_setup_result ───────────────────────────────

def test_display_renders_structured_cards_for_approved(qapp):
    host = _StubHost()
    form = SetupFormWidget("Race", host)
    payload = _payload(
        status="approved",
        changes=[{"setting": "Rear ARB", "field": "arb_rear", "from": 3, "to": 4,
                  "to_clamped": 4, "why": "plant the rear"}],
        fields={"arb_rear": 4})
    host._display_setup_result(("success", payload, "analyse_setup", None, form))
    html = form._setup_result_text.toHtml()
    # Structured decision card is present …
    assert "Approved changes" in html
    assert "Rear ARB" in html
    # … alongside the preserved legacy analysis text.
    assert "loses traction" in html


def test_display_no_double_banner_when_status_banner_present(qapp):
    host = _StubHost()
    form = SetupFormWidget("Race", host)
    # 'partial_recommendation' yields a legacy status banner → cards drop theirs.
    payload = _payload(
        status="partial_recommendation",
        changes=[{"setting": "Front ARB", "field": "arb_front", "why": "turn-in"}],
        fields={"arb_front": 5})
    host._display_setup_result(("success", payload, "analyse_setup", None, form))
    html = form._setup_result_text.toHtml()
    # The card table still renders; the legacy banner supplies the status line.
    assert "Approved changes" in html
    assert "Partial recommendation" in html


def test_display_result_renders_to_png(qapp, tmp_path):
    host = _StubHost()
    form = SetupFormWidget("Race", host)
    payload = _payload(
        status="approved",
        changes=[{"setting": "Rear ARB", "field": "arb_rear", "from": 3, "to": 4,
                  "to_clamped": 4, "why": "plant the rear"}],
        fields={"arb_rear": 4})
    host._display_setup_result(("success", payload, "analyse_setup", None, form))
    form._setup_result_text.resize(560, 320)
    png = tmp_path / "advice_cards.png"
    assert form._setup_result_text.grab().save(str(png))
    assert png.exists() and png.stat().st_size > 0
