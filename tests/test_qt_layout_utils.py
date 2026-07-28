"""Safe layout teardown must empty a layout WITHOUT ever reparenting a visible
widget to None (which flashes a native top-level — the stray-window bug)."""
import pytest

pytest.importorskip("PyQt6")

from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QLabel, QPushButton,
)

from ui.qt_layout_utils import clear_layout, discard_widget, detach_widget


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def _toplevels():
    return {w for w in QApplication.topLevelWidgets()}


def test_clear_layout_empties_and_makes_no_new_toplevel(qapp):
    host = QWidget()
    lay = QVBoxLayout(host)
    for i in range(5):
        lay.addWidget(QLabel(f"row {i}"))
    host.show()
    before = _toplevels()

    clear_layout(lay)

    assert lay.count() == 0
    # No cleared child was promoted to a top-level window.
    assert _toplevels() - before == set()
    host.close()


def test_clear_layout_recurses_into_sublayouts(qapp):
    host = QWidget()
    outer = QVBoxLayout(host)
    inner = QVBoxLayout()
    inner.addWidget(QPushButton("deep"))
    outer.addLayout(inner)
    outer.addWidget(QLabel("shallow"))

    clear_layout(outer)
    assert outer.count() == 0


def test_discard_widget_hides_before_delete(qapp):
    w = QWidget()
    w.show()
    discard_widget(w)
    assert w.isVisible() is False


def test_detach_widget_hides_then_unparents_but_survives(qapp):
    parent = QWidget()
    lay = QVBoxLayout(parent)
    child = QLabel("keep me")
    lay.addWidget(child)
    parent.show()

    detach_widget(child)
    assert child.isVisible() is False   # hidden first, so no top-level flash
    assert child.parent() is None       # detached, but still alive (not deleted)
    assert child.text() == "keep me"
    parent.close()


def test_none_inputs_are_noops(qapp):
    clear_layout(None)
    discard_widget(None)
    detach_widget(None)
