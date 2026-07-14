"""One-setup-editor rollback controls (Engineering-Brain Phase 7).

Covers the pure rollback-apply helpers and the lineage→revert decision that drive
the editor's "Revert last change" button, plus an end-to-end proof through a real
SessionDB, and the form-widget button wiring. The rollback logic stays pure and
Qt-free in strategy.setup_lineage; the UI only reads its decision.
"""
from __future__ import annotations

import json

from strategy.setup_lineage import (
    apply_revert_to_setup, revert_button_state, _coerce_setup_value,
    rollback_from_lineage,
)


# ------------------------------------------------------------- value coercion

def test_coerce_setup_value():
    assert _coerce_setup_value("6") == 6 and isinstance(_coerce_setup_value("6"), int)
    assert _coerce_setup_value("1.5") == 1.5
    assert _coerce_setup_value("-0.07") == -0.07
    assert _coerce_setup_value(8) == 8
    assert _coerce_setup_value("soft") == "soft"   # non-numeric passes through
    assert _coerce_setup_value("") == ""


# ------------------------------------------------------------- apply_revert_to_setup

def test_apply_revert_restores_prior_values_on_a_copy():
    setup = {"arb_front": 6, "camber_front": 1.5, "aero_front": 480}
    # revert_changes come from rollback_from_lineage: 'to' is the value to restore.
    revert = [{"field": "arb_front", "from": 6, "to": "5"},
              {"field": "aero_front", "from": 480, "to": "450"}]
    out = apply_revert_to_setup(setup, revert)
    assert out["arb_front"] == 5
    assert out["aero_front"] == 450
    assert out["camber_front"] == 1.5      # untouched
    assert setup["arb_front"] == 6         # original not mutated (copy)


def test_apply_revert_skips_bad_entries():
    setup = {"arb_front": 6}
    out = apply_revert_to_setup(setup, [{"field": "", "to": 1}, "nonsense",
                                        {"no_field": 1}, {"field": "arb_front", "to": "5"}])
    assert out == {"arb_front": 5}


def test_apply_revert_empty_is_identity_copy():
    setup = {"arb_front": 6}
    out = apply_revert_to_setup(setup, [])
    assert out == setup and out is not setup


# ------------------------------------------------------------- revert_button_state

def _node(nid, parent, verdict, changes):
    return {"id": nid, "parent_id": parent, "outcome_verdict": verdict,
            "changes_json": json.dumps(changes), "label": f"n{nid}"}


def test_revert_state_hidden_when_no_lineage_or_not_worsened():
    assert revert_button_state([])["visible"] is False
    # Newest scored node improved → nothing to revert.
    rows = [_node(2, 1, "improved", [{"field": "arb_front", "from": 5, "to": 6}])]
    assert revert_button_state(rows)["visible"] is False
    # Newest node unscored, older worsened but not newest-scored → still hidden
    # (rollback only fires on the NEWEST scored node).
    rows = [_node(3, 2, "", [{"field": "aero_front", "from": 450, "to": 480}]),
            _node(2, 1, "improved", [{"field": "arb_front", "from": 5, "to": 6}])]
    assert revert_button_state(rows)["visible"] is False


def test_revert_state_visible_when_newest_scored_worsened():
    rows = [_node(2, 1, "worsened",
                  [{"field": "arb_front", "from": 5, "to": 6},
                   {"field": "aero_front", "from": 450, "to": 480}])]
    st = revert_button_state(rows)
    assert st["visible"] is True
    assert st["count"] == 2
    assert st["target_id"] == 1
    # revert_changes restore the parent (pre-change) values.
    by_field = {c["field"]: c["to"] for c in st["revert_changes"]}
    assert by_field == {"arb_front": 5, "aero_front": 450}
    assert "worse" in st["tooltip"].lower() or "previous" in st["tooltip"].lower()
    # Applying the revert to a live setup puts the old values back.
    reverted = apply_revert_to_setup({"arb_front": 6, "aero_front": 480}, st["revert_changes"])
    assert reverted == {"arb_front": 5, "aero_front": 450}


def test_worsened_node_without_parent_is_not_revertable():
    rows = [_node(1, None, "worsened", [{"field": "arb_front", "from": 5, "to": 6}])]
    assert revert_button_state(rows)["visible"] is False


# ------------------------------------------------------------- end-to-end via SessionDB

def test_end_to_end_apply_worse_then_revert_state():
    from data.session_db import SessionDB
    db = SessionDB(":memory:")
    # Parent applied setup.
    db._conn.execute(
        "INSERT INTO setup_recommendations (car_id, track, layout_id, status, "
        "approved_changes_json, created_at) VALUES (1,'Fuji','full','proposed',?,'t')",
        (json.dumps([{"field": "aero_rear", "from": "600", "to": "630"}]),))
    db._conn.commit()
    db.apply_recommendation_for_car_track(1, "Fuji", 10)      # parent node
    # Child applied setup that the driver will rate worse.
    db._conn.execute(
        "INSERT INTO setup_recommendations (car_id, track, layout_id, status, "
        "approved_changes_json, created_at) VALUES (1,'Fuji','full','proposed',?,'t')",
        (json.dumps([{"field": "arb_front", "from": "5", "to": "7"}]),))
    db._conn.commit()
    db.apply_recommendation_for_car_track(1, "Fuji", 12)      # child node, parent set
    # No verdict yet → nothing to revert.
    assert revert_button_state(db.get_lineage(1, "Fuji", "full"))["visible"] is False
    # Driver reports the child worse.
    db.record_latest_lineage_outcome(1, "Fuji", "full", "worsened", 13)
    st = revert_button_state(db.get_lineage(1, "Fuji", "full"))
    assert st["visible"] is True
    assert {c["field"]: c["to"] for c in st["revert_changes"]} == {"arb_front": "5"}
    reverted = apply_revert_to_setup({"arb_front": 7}, st["revert_changes"])
    assert reverted["arb_front"] == 5


# ------------------------------------------------------------- form-widget button

def test_form_widget_has_hidden_revert_button():
    import pytest
    pytest.importorskip("PyQt6")
    from PyQt6.QtWidgets import QApplication
    from ui.setup_form_widget import SetupFormWidget

    app = QApplication.instance() or QApplication([])

    class _Host:
        def __getattr__(self, _n):
            def _noop(*a, **k):
                return None
            return _noop

    for purpose in ("Race", "Qualifying"):
        form = SetupFormWidget(purpose, _Host())
        assert hasattr(form, "_btn_revert_setup")
        assert form._btn_revert_setup.isVisible() is False
        assert "Revert" in form._btn_revert_setup.text()
