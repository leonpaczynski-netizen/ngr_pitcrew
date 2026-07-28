"""Safe layout-teardown helpers — the stray-window fix at the source.

Reparenting a *visible* widget to ``None`` (``w.setParent(None)``) promotes it to a
native top-level window. On Windows the native window is created and can briefly
FLASH as an empty, focus-stealing box before it is garbage-collected — the
intermittent "flashing box" bug the StrayWindowGuard was catching. It is most
visible when a widget list is rebuilt on a timer (e.g. the Home readiness box on
the 750 ms refresh), because the detached holders flash once per tick.

The safe idiom is to HIDE the widget first (so it can never be shown as a
top-level) and then either delete it (disposable content) or, for a widget that
must survive, reparent it while hidden. These helpers encapsulate that so call
sites never reintroduce the bug.
"""
from __future__ import annotations

from PyQt6.QtWidgets import QLayout, QWidget


def clear_layout(layout: QLayout) -> None:
    """Remove and delete every widget/sub-layout in ``layout`` — without flashing.

    Each widget is hidden before deletion, and never reparented to ``None``, so no
    detached top-level is ever created.
    """
    if layout is None:
        return
    while layout.count():
        item = layout.takeAt(0)
        w = item.widget()
        if w is not None:
            w.hide()
            w.deleteLater()
            continue
        sub = item.layout()
        if sub is not None:
            clear_layout(sub)


def discard_widget(w: QWidget | None) -> None:
    """Hide + schedule deletion of a disposable widget (never reparent-to-None)."""
    if w is not None:
        w.hide()
        w.deleteLater()


def detach_widget(w: QWidget | None) -> None:
    """Detach a widget that must SURVIVE (e.g. a borrowed panel handed back to its
    owner). Hidden first, so the reparent-to-None can never flash a top-level."""
    if w is not None:
        w.hide()
        w.setParent(None)
