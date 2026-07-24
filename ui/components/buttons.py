"""Action buttons (F0.5).

PrimaryActionButton is the single dominant CTA per screen (neon-green); the
Secondary variant is visually subordinate. Both carry a visible keyboard-focus
ring (never removed without replacement).
"""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QPushButton

from ui import ngr_theme as _t


class PrimaryActionButton(QPushButton):
    """The one dominant primary action on a page."""

    def __init__(self, text: str = "", parent=None):
        super().__init__(text, parent)
        self.setObjectName("ngrPrimaryAction")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(
            _t.primary_button_qss()
            + f" QPushButton:focus {{ {_t.focus_ring_qss()} }}"
        )

    def set_action(self, label: str, enabled: bool = True) -> None:
        """Set the CTA label + enabled state. A blank label disables the button."""
        label = label or ""
        self.setText(label)
        # A narrow column can still clip a long CTA — keep the full wording reachable.
        self.setToolTip(label)
        self.setEnabled(bool(enabled) and bool(label))
        self.setVisible(bool(label))


class SecondaryActionButton(QPushButton):
    """A subordinate action, visually quieter than the primary CTA."""

    def __init__(self, text: str = "", parent=None):
        super().__init__(text, parent)
        self.setObjectName("ngrSecondaryAction")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(
            _t.secondary_button_qss()
            + f" QPushButton:focus {{ {_t.focus_ring_qss()} }}"
        )

    def set_action(self, label: str, enabled: bool = True) -> None:
        label = label or ""
        self.setText(label)
        # A narrow column can still clip a long CTA — keep the full wording reachable.
        self.setToolTip(label)
        self.setEnabled(bool(enabled) and bool(label))
        self.setVisible(bool(label))
