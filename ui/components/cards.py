"""Container primitives: Card and SectionHeading (F0.5)."""

from __future__ import annotations

from PyQt6.QtWidgets import QFrame, QLabel, QVBoxLayout

from ui import ngr_theme as _t


class Card(QFrame):
    """A raised carbon card with a standard inner padding + vertical layout.

    Add children with ``card.body.addWidget(...)`` (the inner layout) or use
    ``card.add(widget)``.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ngrCard")
        self.setStyleSheet(f"#ngrCard {{ {_t.card_qss()} }}")
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(_t.SPACE_LG, _t.SPACE_MD, _t.SPACE_LG, _t.SPACE_MD)
        self.body.setSpacing(_t.SPACE_SM)

    def add(self, widget) -> None:
        self.body.addWidget(widget)


class SectionHeading(QLabel):
    """An uppercase NGR section heading. level 1 = page title, 2 = section."""

    def __init__(self, text: str = "", level: int = 2, parent=None):
        super().__init__(text, parent)
        self.setObjectName("ngrSectionHeading")
        self._level = level
        self.setStyleSheet(_t.heading_qss(level))

    def set_text(self, text: str) -> None:
        self.setText(text or "")
