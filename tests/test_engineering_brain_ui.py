"""Engineering-brain UI surfaces (Engineering-Brain Phase 7).

The Phase 2-6 reasoning is shown to the driver via self-guarding, module-level render
panels — the same Qt-free pattern as the balance/driver-fit/closed-loop panels.
"""
from __future__ import annotations

from ui.setup_builder_ui import _engineering_brain_html


def _full_data():
    return {
        "discipline_objective": {
            "objective": "qualifying",
            "tyre": {"compound": "RS", "name": "Racing Soft", "reason": "softest legal"},
            "rpm": {"note": "rev out over one lap"}},
        "setup_synthesis": {
            "objective": "race", "confidence": "medium", "best": {"lens": "driver_history"},
            "target_handling": {"drivers": ["rear-engined car needs front support"]},
            "candidates": [{"lens": "driver_history", "score": 2.3},
                           {"lens": "balance", "score": 2.1}]},
        "corner_diagnosis": {
            "corner": {"name": "T2 Apex"}, "phase": "apex", "confidence": "low",
            "causes": [{"cause": "LSD preload too low"}, {"cause": "front grip limit"}],
            "controlled_test": "capture front slip over 3 laps"},
        "setup_strategy_handoff": {
            "characteristics": {"tyre_preservation": 0.5},
            "strengths": ["protects the tyre", "stable traction"]},
    }


def test_all_engineering_brain_panels_render():
    h = _engineering_brain_html(_full_data())
    for token in ("Qualifying objective", "Racing Soft", "Complete-setup synthesis",
                  "driver_history", "T2 Apex", "Strategy tab", "protects the tyre"):
        assert token in h


def test_panels_self_guard():
    assert _engineering_brain_html({}) == ""
    assert _engineering_brain_html(None) == ""
    # A partial dict renders only the sections that are present.
    only_corner = _engineering_brain_html({"corner_diagnosis": {"corner": {"name": "T5"},
                                                                "phase": "exit",
                                                                "confidence": "medium",
                                                                "causes": []}})
    assert "T5" in only_corner and "Complete-setup synthesis" not in only_corner


def test_development_timeline_renders_chain_and_rollback():
    import json
    from ui.setup_builder_ui import _development_timeline_html
    data = {
        "setup_lineage": [
            {"id": 1, "parent_id": None, "label": "Race Setup 18",
             "changes_json": json.dumps([{"field": "aero_rear", "from": "600", "to": "630"}]),
             "outcome_verdict": "improved"},
            {"id": 2, "parent_id": 1, "label": "Race Setup 19",
             "changes_json": json.dumps([{"field": "lsd_accel", "from": "15", "to": "17"}]),
             "outcome_verdict": "worsened"},
        ],
        "rollback": {"recommend_rollback": True, "target_id": 1,
                     "revert_changes": [{"field": "lsd_accel", "to": "15"}]},
    }
    h = _development_timeline_html(data)
    assert "Race Setup 18" in h and "Race Setup 19" in h
    assert "better" in h and "worse" in h          # outcome badges
    assert "Roll back" in h                         # rollback recommendation
    # Self-guards.
    from ui.setup_builder_ui import _development_timeline_html as f
    assert f({}) == "" and f({"setup_lineage": []}) == ""


def test_handoff_only_renders_with_characteristics():
    # A base/quali response has no handoff → no Strategy-tab panel.
    assert "Strategy tab" not in _engineering_brain_html(
        {"discipline_objective": {"objective": "base", "rpm": {"note": "balanced"}}})
