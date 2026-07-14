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


def test_handoff_only_renders_with_characteristics():
    # A base/quali response has no handoff → no Strategy-tab panel.
    assert "Strategy tab" not in _engineering_brain_html(
        {"discipline_objective": {"objective": "base", "rpm": {"note": "balanced"}}})
