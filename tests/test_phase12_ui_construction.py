"""Engineering Brain Program 2 Phase 12 — Engineering Knowledge panel construction test.

Run individually: Windows/PyQt teardown can segfault AFTER a clean pass. Asserts the
panel builds, renders the knowledge base, and exposes NO Apply controls.
"""
import pytest

_qt = pytest.importorskip("PyQt6.QtWidgets")


@pytest.fixture(scope="module")
def app():
    from PyQt6.QtWidgets import QApplication
    a = QApplication.instance() or QApplication([])
    yield a


def test_panel_constructs_and_renders(app):
    from ui.engineering_knowledge_panel import EngineeringKnowledgePanel
    w = EngineeringKnowledgePanel()
    # 8 component groups + load + phases + interactions + lsd + aero = 13 section tables
    assert len(w._tables) >= 12
    w.deleteLater()


def test_panel_refresh_is_stable(app):
    from ui.engineering_knowledge_panel import EngineeringKnowledgePanel
    w = EngineeringKnowledgePanel()
    n = len(w._tables)
    w.refresh()
    assert len(w._tables) == n
    w.deleteLater()


def test_panel_has_no_apply_controls(app):
    from PyQt6.QtWidgets import QPushButton
    from ui.engineering_knowledge_panel import EngineeringKnowledgePanel
    w = EngineeringKnowledgePanel()
    for btn in w.findChildren(QPushButton):
        label = (btn.text() or "").lower()
        assert "apply" not in label and "approve" not in label and "save" not in label
    w.deleteLater()
