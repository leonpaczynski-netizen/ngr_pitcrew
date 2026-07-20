"""Phase 56 — certification VM + offscreen panel construction (task items 31, 35, 38)."""
from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from strategy.event_programme_certification import current_slice_certification
from ui import certification_vm as vm


def _payload():
    return current_slice_certification().as_payload()


# --- view-model ------------------------------------------------------------

def test_vm_empty_state():
    assert vm.is_empty(None)
    assert "No certification" in vm.header_text(None)


def test_vm_this_slice_is_not_tested_overall():
    p = _payload()
    assert not vm.is_empty(p)
    assert "NOT TESTED" in vm.header_text(p)  # bounded by untested live areas
    cards = vm.area_cards(p)
    assert len(cards) == 23
    # a live area card shows NOT TESTED + a limitation finding
    live = [c for c in cards if c["title"].lower().startswith("live practice")][0]
    assert live["status_tag"] == "NOT TESTED"


def test_vm_never_shows_operational_ready_for_automated():
    p = _payload()
    assert "OPERATIONALLY READY" not in vm.header_text(p)


# --- offscreen panel construction ------------------------------------------

@pytest.fixture(scope="module")
def app():
    pytest.importorskip("PyQt6")
    from PyQt6.QtWidgets import QApplication
    a = QApplication.instance() or QApplication([])
    yield a


def test_certification_panel_constructs_and_renders(app):
    from ui.certification_panel import CertificationPanel
    panel = CertificationPanel()
    panel.update_result(None)          # empty
    panel.update_result(_payload())    # populated
    panel.update_result(None)          # back to empty; must not raise


def test_development_history_page_hosts_certification(app):
    from ui.development_history_page import DevelopmentHistoryPage
    page = DevelopmentHistoryPage()
    assert hasattr(page, "_certification_panel")
    page.update_certification(_payload())
    page.update_certification(None)  # must not raise
