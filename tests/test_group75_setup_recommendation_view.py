"""UAT Finding 3 — structured Setup Builder recommendation (VM + view + wiring).

Covers required tests:
  6. Proposed fields highlight before "Applied in Game".
  7. Applied status changes without altering the recommendation visibility.
"""
from __future__ import annotations

import os
import queue
from unittest.mock import MagicMock

import pytest

from ui.setup_recommendation_vm import (
    build_recommendation_vm, HeaderInfo, PROPOSED, APPLIED, REJECTED,
)


_PAYLOAD = {
    "analysis": "Rear unstable on entry.",
    "recommendation_status": "approved",
    "diagnosis": {"primary_issue": "corner-entry oversteer"},
    "changes": [
        {"setting": "Rear ARB", "from": 5, "to": 4, "to_clamped": 4, "field": "rear_arb",
         "why": "reduce entry oversteer", "rule_id": "ARB_REAR_SOFT",
         "symptom": "entry oversteer", "rationale": "softer rear ARB adds rear grip",
         "evidence": ["rear slip on 4/5 laps"], "rejected_alternatives": ["raise rear wing"],
         "risk_level": "low", "confidence_level": "high",
         "driver_style_alignment": "matches smooth entry"},
        {"setting": "Front wing", "from": 3, "to": 5, "to_clamped": 5, "field": "front_wing",
         "why": "more front load", "rule_id": "WING_FRONT_UP", "confidence_level": "medium"},
    ],
    "rejected_changes": [
        {"setting": "Rear wing", "from": 6, "to": 8, "field": "rear_wing"},
    ],
}


# --------------------------------------------------------------------------- #
# VM
# --------------------------------------------------------------------------- #

def test_vm_builds_structured_rows_and_cards():
    vm = build_recommendation_vm(_PAYLOAD, header=HeaderInfo(car="RSR", track="Fuji"))
    assert vm.has_recommendation
    # Two proposed (changed) rows + one rejected row.
    changed = [r for r in vm.field_rows if r.changed]
    assert len(changed) == 2
    assert all(r.status == PROPOSED for r in changed)
    # Delta computed numerically.
    arb = next(r for r in vm.field_rows if r.setting == "Rear ARB")
    assert arb.delta == "-1"
    assert arb.current_value == "5" and arb.recommended_value == "4"
    # Rejected candidate present, not highlighted.
    rej = next(r for r in vm.field_rows if r.status == REJECTED)
    assert not rej.highlighted
    # Why cards carry the full rationale set.
    card = next(c for c in vm.why_cards if c.setting == "Rear ARB")
    assert card.symptom and card.rationale and card.evidence and card.alternatives
    assert card.rule_source == "ARB_REAR_SOFT"
    # Test plan is an ordered sequence.
    assert len(vm.test_plan) >= 1
    assert vm.header.primary_issue == "corner-entry oversteer"


def test_vm_highlights_before_apply_then_flips():
    vm = build_recommendation_vm(_PAYLOAD)
    # Highlighted immediately at generate — proposed + highlighted.
    assert len(vm.highlighted_rows()) == 2
    assert len(vm.proposed_rows()) == 2

    applied = vm.mark_applied()
    # Same rows, now applied — still highlighted/visible.
    assert len(applied.field_rows) == len(vm.field_rows)
    changed = [r for r in applied.field_rows if r.changed]
    assert all(r.status == APPLIED for r in changed)
    assert len(applied.highlighted_rows()) == 2  # visibility unchanged
    assert applied.proposed_rows() == ()


# --------------------------------------------------------------------------- #
# View + real Setup Builder wiring
# --------------------------------------------------------------------------- #

@pytest.fixture(scope="module")
def qapp():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    pytest.importorskip("PyQt6")
    from PyQt6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def test_view_highlights_changed_rows_at_generate(qapp):
    from ui.setup_recommendation_view import SetupRecommendationView, RECO_COLS
    view = SetupRecommendationView()
    vm = build_recommendation_vm(_PAYLOAD, header=HeaderInfo(car="RSR"))
    view.set_vm(vm)

    status_col = RECO_COLS.index("Status")
    # Changed rows show "Proposed" and carry a highlight background BEFORE apply.
    proposed_bg = []
    for r in range(view._table.rowCount()):
        status = view._table.item(r, status_col).text()
        bg = view._table.item(r, 0).background().color().name()
        if status == "Proposed":
            proposed_bg.append(bg)
    assert len(proposed_bg) == 2
    # The highlight colour is not the default black/transparent.
    assert all(c != "#000000" for c in proposed_bg)

    # Apply -> statuses flip to Applied; row count (visibility) unchanged.
    before = view._table.rowCount()
    view.mark_applied()
    assert view._table.rowCount() == before
    applied_statuses = [
        view._table.item(r, status_col).text()
        for r in range(view._table.rowCount())
        if view._table.item(r, status_col).text() != "Rejected"]
    assert applied_statuses and all(s == "Applied" for s in applied_statuses)


@pytest.fixture
def window(qapp, tmp_path):
    import config_paths as cp
    cfg = str(tmp_path / "config.json")
    cp.write_default_config(cfg)
    config = cp.load_config(cfg)
    config.setdefault("strategy", {}).update({"car": "RSR", "track": "Fuji",
                                              "layout_id": "full_course"})
    from ui.dashboard import MainWindow, SignalBridge
    win = MainWindow(config=config, logger=MagicMock(), announcer=MagicMock(),
                     bridge=SignalBridge(), ui_queue=queue.Queue(),
                     config_path=cfg, db=None)
    win._query_listener = None
    yield win
    win.close()


def test_real_builder_populate_and_apply(window):
    # Structured view exists (not a single text box).
    assert getattr(window, "_setup_rec_view", None) is not None

    # Generate: populate via the real integration method -> highlighted + visible.
    window._populate_setup_recommendation_view(_PAYLOAD, True)
    view = window._setup_rec_view
    assert not view.isHidden()  # shown once a recommendation exists
    vm = view.current_vm()
    assert len(vm.proposed_rows()) == 2          # test 6: highlighted at generate
    assert len(vm.highlighted_rows()) == 2

    # Applied in game via the real handler path -> status flips, still visible.
    row_count_before = view._table.rowCount()
    window._rec_view_apply_in_game()
    vm2 = view.current_vm()
    assert vm2.proposed_rows() == ()             # test 7: status changed
    assert len(vm2.highlighted_rows()) == 2      # visibility unchanged
    assert view._table.rowCount() == row_count_before
    assert not view.isHidden()
