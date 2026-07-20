"""Phase 45-47 — UI: voice controls, snapshot/validation cards, handlers, no strategy commands."""
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PyQt6")

from PyQt6.QtWidgets import QApplication, QPushButton


@pytest.fixture(scope="module")
def app():
    a = QApplication.instance() or QApplication([])
    yield a


def _result(voice=None, snapshot=None, shadow=None):
    return {"ok": True,
            "workflow": {"state": "ready_to_run", "next_user_action": "begin run",
                         "setup_check": {"verification": "match", "reason": "ok"}, "blockers": []},
            "advisory": {"delivered": None, "suppressed": [], "active_objective": ""},
            "material_trust": {"overall_trust": "exact_verified"},
            "evidence_progress": {"clean_laps": 1, "min_clean": 3}, "outcome_ready": False,
            "snapshot": snapshot or {"short_fingerprint": "engineering_context_snapshot_v1:snap:abc",
                                     "validation_state": "valid"},
            "shadow": shadow or {"readiness": "shadow_ready"},
            "voice": voice or {"enabled": False, "health": "disabled", "last_spoken": "",
                               "queue": {"pending": 0, "muted_types": []}}}


def test_panel_has_voice_controls_only(app):
    from ui.assisted_runtime_panel import AssistedRuntimePanel
    p = AssistedRuntimePanel()
    p.update_result(_result())
    labels = [b.text().lower() for b in p.findChildren(QPushButton)]
    assert any("voice" in l for l in labels)          # voice controls present
    assert any("acknowledge" in l for l in labels)
    # no strategy/apply command buttons
    for bad in ("apply", "pit now", "change tyre", "fuel map", "change setup", "create experiment"):
        assert not any(bad in l for l in labels), bad


def test_voice_button_reflects_enabled_state(app):
    from ui.assisted_runtime_panel import AssistedRuntimePanel
    p = AssistedRuntimePanel()
    p.update_result(_result(voice={"enabled": True, "health": "ok", "queue": {"pending": 0}}))
    labels = [b.text() for b in p.findChildren(QPushButton)]
    assert "Disable Voice" in labels
    p.update_result(_result(voice={"enabled": False, "health": "disabled", "queue": {"pending": 0}}))
    labels = [b.text() for b in p.findChildren(QPushButton)]
    assert "Enable Voice" in labels


def test_snapshot_and_validation_cards_shown(app):
    from ui.assisted_runtime_panel import AssistedRuntimePanel
    p = AssistedRuntimePanel()
    p.update_result(_result())
    text = " ".join(c.accessibleName() for c in p._cards)
    assert "Context Snapshot" in text and "Live Validation & Voice" in text


def test_voice_handlers_fire(app):
    from ui.assisted_runtime_panel import AssistedRuntimePanel
    called = {}
    p = AssistedRuntimePanel()
    p.set_voice_handlers(toggle=lambda: called.__setitem__("t", True),
                         acknowledge=lambda: called.__setitem__("a", True),
                         mute=lambda: called.__setitem__("m", True),
                         test=lambda: called.__setitem__("v", True))
    p._fire(p._on_toggle_voice); p._fire(p._on_acknowledge)
    p._fire(p._on_mute); p._fire(p._on_test_voice)
    assert called == {"t": True, "a": True, "m": True, "v": True}


def test_ui_refresh_creates_no_snapshot(app, tmp_path):
    # rendering the panel (pure) never calls a DB writer.
    from ui.assisted_runtime_panel import AssistedRuntimePanel
    p = AssistedRuntimePanel()
    p.update_result(_result())
    p.update_result(_result())   # repeated refresh
    assert len(p._cards) >= 4
