"""Shared marks: the primitives every Pit Crew screen is built from.

Nothing here is a generic component wearing a colour. A panel is a bolted
plate with its label struck through the top edge; a band is the coloured ring
a crew paints on a set; a value knows whether it was measured or declared and
renders in the matching register.
"""
from __future__ import annotations

from PyQt6.QtCore import (
    QEasingCurve,
    QPropertyAnimation,
    QRectF,
    Qt,
    pyqtProperty,
    pyqtSignal,
)
from PyQt6.QtGui import QColor, QFont, QPainter, QPen
from PyQt6.QtWidgets import (
    QAbstractSpinBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from pitcrew.ui import theme


class StencilLabel(QLabel):
    """Tracked condensed caps, cut the way a technical plate is stencilled."""

    def __init__(self, text: str = "", *, size: int = theme.LABEL_PX,
                 colour: str = theme.STENCIL_DIM, tracking: float = 10.0,
                 weight: QFont.Weight = QFont.Weight.DemiBold,
                 parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.setFont(theme.stencil_font(size, weight=weight, tracking=tracking))
        self.setStyleSheet(f"color: {colour}; background: transparent;")


class BodyLabel(QLabel):
    def __init__(self, text: str = "", *, size: int = theme.BODY_PX,
                 colour: str = theme.STENCIL_DIM, wrap: bool = True,
                 parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.setFont(theme.text_font(size))
        self.setStyleSheet(f"color: {colour}; background: transparent;")
        self.setWordWrap(wrap)


class Measured(QLabel):
    """A value that came off the telemetry stream. Stencil white, mono."""

    def __init__(self, text: str = "", *, size: int = theme.DATA_PX,
                 colour: str = theme.STENCIL, bold: bool = False,
                 parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        weight = QFont.Weight.DemiBold if bold else QFont.Weight.Normal
        self.setFont(theme.data_font(size, weight=weight))
        self.setStyleSheet(f"color: {colour}; background: transparent;")


class Declared(Measured):
    """A value the driver entered. Crayon, so it can never pass as measured."""

    def __init__(self, text: str = "", **kwargs) -> None:
        kwargs.setdefault("colour", theme.CRAYON)
        super().__init__(text, **kwargs)


class Plate(QFrame):
    """A bolted panel whose stencilled label is struck through its top edge.

    The plate's drawn border starts below the widget's own top, so the label
    can sit centred on that rule with its full cap height inside the widget.
    Straddling y=0 instead would clip the tops of the letters, which is what
    the first render did.
    """

    LABEL_INSET = 16
    LABEL_PAD = 8
    TOP_RESERVE = 9    # space above the drawn border for the label to sit in

    def __init__(self, title: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._title = title.upper()
        self._label_font = theme.stencil_font(theme.LABEL_PX, tracking=14.0)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)

        top = self.TOP_RESERVE + 18 if title else 18
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(18, top, 18, 18)
        self.body.setSpacing(theme.GAP)

    def setTitle(self, title: str) -> None:  # noqa: N802 - Qt naming
        self._title = title.upper()
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt naming
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)

        top = self.TOP_RESERVE if self._title else 0
        rect = QRectF(self.rect()).adjusted(0.5, top + 0.5, -0.5, -0.5)
        painter.fillRect(0, top, self.width(), self.height() - top,
                         QColor(theme.SHOULDER))
        painter.setPen(QPen(QColor(theme.TREAD), 1))
        painter.drawRect(rect)

        if not self._title:
            painter.end()
            return

        painter.setFont(self._label_font)
        metrics = painter.fontMetrics()
        width = metrics.horizontalAdvance(self._title)
        left = self.LABEL_INSET
        baseline = top + metrics.capHeight() // 2

        # Break the rule where the label crosses it.
        painter.fillRect(
            int(left - self.LABEL_PAD), top - 1,
            int(width + self.LABEL_PAD * 2), 3,
            QColor(theme.RUBBER))
        painter.setPen(QPen(QColor(theme.STENCIL_DIM)))
        painter.drawText(int(left), int(baseline), self._title)
        painter.end()


class CompoundBand(QWidget):
    """The coloured ring a crew paints on a set, carrying its own code.

    Colour is never the only channel: the two-letter code is stencilled on the
    band, so the classification survives for a viewer who cannot separate the
    hues, and in a screenshot, and in print.
    """

    WIDTH = 38

    def __init__(self, code: str | None = None, *, parent: QWidget | None = None,
                 animate: bool = True) -> None:
        super().__init__(parent)
        self._code = code
        self._previous = None
        self._wipe = 1.0
        self._struck = False
        self._animate = animate
        self.setFixedWidth(self.WIDTH)
        self._font = theme.stencil_font(12, tracking=6.0)

        self._animation = QPropertyAnimation(self, b"wipe", self)
        self._animation.setDuration(180)
        self._animation.setEasingCurve(QEasingCurve.Type.OutCubic)

    def code(self) -> str | None:
        return self._code

    def setCode(self, code: str | None) -> None:  # noqa: N802 - Qt naming
        if code == self._code:
            return
        self._previous = self._code
        self._code = code
        if self._animate and self.isVisible():
            self._animation.stop()
            self._animation.setStartValue(0.0)
            self._animation.setEndValue(1.0)
            self._animation.start()
        else:
            self._wipe = 1.0
            self.update()

    def setStruck(self, struck: bool) -> None:  # noqa: N802 - Qt naming
        if struck != self._struck:
            self._struck = struck
            self.update()

    @pyqtProperty(float)
    def wipe(self) -> float:
        return self._wipe

    @wipe.setter
    def wipe(self, value: float) -> None:
        self._wipe = value
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt naming
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        under = theme.band_colour(self._previous)
        over = theme.band_colour(self._code)
        if self._struck:
            under = _desaturate(under)
            over = _desaturate(over)

        painter.fillRect(self.rect(), under)
        height = int(self.height() * max(0.0, min(1.0, self._wipe)))
        painter.fillRect(0, 0, self.width(), height, over)

        if self._code:
            painter.setFont(self._font)
            ink = theme.band_ink(self._code)
            if self._struck:
                ink.setAlpha(150)
            painter.setPen(QPen(ink))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter,
                             self._code.upper())
        painter.end()


def _desaturate(colour: QColor) -> QColor:
    """A set taken out of the count keeps its identity but loses its voice."""
    grey = int(0.299 * colour.red() + 0.587 * colour.green()
               + 0.114 * colour.blue())
    return QColor(
        int(colour.red() * 0.32 + grey * 0.30),
        int(colour.green() * 0.32 + grey * 0.30),
        int(colour.blue() * 0.32 + grey * 0.30),
    )


class MarkButton(QPushButton):
    """An action, lettered on a plate. `primary` is the one the run ends with."""

    def __init__(self, text: str, *, primary: bool = False,
                 danger: bool = False, parent: QWidget | None = None) -> None:
        super().__init__(text.upper(), parent)
        self.setFont(theme.stencil_font(13, tracking=12.0))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(40)

        if primary:
            base, ink, edge = theme.CRAYON, theme.RUBBER, theme.CRAYON
            hover = "#FF823D"
        elif danger:
            base, ink, edge = "transparent", theme.DANGER, theme.DANGER
            hover = theme.SHOULDER_HI
        else:
            base, ink, edge = "transparent", theme.STENCIL, theme.TREAD_LIGHT
            hover = theme.SHOULDER_HI

        self.setStyleSheet(f"""
            QPushButton {{
                background: {base};
                color: {ink};
                border: 1px solid {edge};
                padding: 9px 20px;
            }}
            QPushButton:hover {{ background: {hover}; }}
            QPushButton:pressed {{ background: {theme.SHOULDER}; }}
            QPushButton:focus {{ border: 1px solid {theme.CHALK}; }}
            QPushButton:disabled {{
                color: {theme.STRUCK};
                border-color: {theme.SHOULDER_HI};
                background: transparent;
            }}
        """)


class Rule(QFrame):
    """A moulded groove."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(1)
        self.setStyleSheet(f"background: {theme.TREAD}; border: none;")


class SpecLine(QWidget):
    """Session totals as one stencilled spec run, the way a sidewall carries
    its rating: labels small and inline, values in mono, all on one line.

    Deliberately not a row of stat cards - a big-number-and-label grid is the
    template every dashboard ships, and it would break this world on the first
    screen the driver looks at.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._row = QHBoxLayout(self)
        self._row.setContentsMargins(0, 0, 0, 0)
        self._row.setSpacing(0)
        self._entries: list[tuple[StencilLabel, Measured]] = []

    def clear(self) -> None:
        while self._row.count():
            item = self._row.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._entries.clear()

    def add(self, label: str, value: str, *, declared: bool = False,
            emphasis: bool = False) -> None:
        if self._entries:
            separator = StencilLabel("·", size=theme.BODY_PX,
                                     colour=theme.TREAD_LIGHT, tracking=0.0)
            separator.setContentsMargins(14, 0, 14, 0)
            self._row.addWidget(separator)

        name = StencilLabel(label, size=11, colour=theme.STENCIL_DIM,
                            tracking=14.0)
        name.setContentsMargins(0, 0, 8, 0)
        cls = Declared if declared else Measured
        reading = cls(value, size=theme.DATA_LARGE_PX if emphasis else theme.DATA_PX,
                      bold=emphasis)
        self._row.addWidget(name)
        self._row.addWidget(reading)
        self._entries.append((name, reading))

    def finish(self) -> None:
        self._row.addStretch(1)


class Field(QWidget):
    """A labelled input. The label is stencilled; what you type is crayon."""

    def __init__(self, label: str, editor: QWidget, *, suffix: str = "",
                 hint: str = "", suffix_widget: QWidget | None = None,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        column = QVBoxLayout(self)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(theme.GAP_TIGHT)

        column.addWidget(StencilLabel(label, size=11, tracking=12.0))

        # A field sharing a grid row with a taller neighbour can be squeezed
        # until its editor is a sliver. Pin the height, and drop the spinner
        # arrows: they crowd the box at this size, and every value here is
        # typed from a screen the driver is reading anyway.
        editor.setMinimumHeight(34)
        if isinstance(editor, QAbstractSpinBox):
            editor.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        row.addWidget(editor, 1)
        if suffix_widget is not None:
            row.addWidget(suffix_widget)
        elif suffix:
            unit = StencilLabel(suffix, size=11, colour=theme.STRUCK,
                                tracking=8.0)
            row.addWidget(unit)
        column.addLayout(row)

        if hint:
            # Not wrapped: a hint that wraps reports a one-line height at its
            # size hint and then overruns the field below it once the grid
            # gives it a narrower column. Keep hints to one short line.
            note = BodyLabel(hint, size=12, colour=theme.STRUCK, wrap=False)
            # Bahnschrift's descenders run past the height Qt reports for the
            # label, so a hint sitting directly under an editor grazes it.
            # Reserve the real line height rather than the reported one.
            note.setMinimumHeight(note.fontMetrics().height() + 4)
            column.addSpacing(2)
            column.addWidget(note)

        self.editor = editor


class StrikeRow(QFrame):
    """A rack row that can be struck out.

    An excluded lap is drawn through, not merely greyed: the crew's chalk gets
    a line across it, and the row stays legible so you can see what you removed
    and why.
    """

    clicked = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._struck = False
        self._hovered = False
        self._strike_right = 16
        self.setMouseTracking(True)

    def setStrikeRight(self, inset: int) -> None:  # noqa: N802 - Qt naming
        """Stop the strike short of the controls.

        A line drawn through a combo box and a button reads as "disabled",
        which they are not - an excluded lap can still be re-counted, and its
        compound still needs tagging.
        """
        self._strike_right = inset
        self.update()

    def setStruck(self, struck: bool) -> None:  # noqa: N802 - Qt naming
        self._struck = struck
        self.update()

    def isStruck(self) -> bool:  # noqa: N802 - Qt naming
        return self._struck

    def enterEvent(self, event) -> None:  # noqa: N802 - Qt naming
        self._hovered = True
        self.update()

    def leaveEvent(self, event) -> None:  # noqa: N802 - Qt naming
        self._hovered = False
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt naming
        painter = QPainter(self)
        ground = QColor(theme.SHOULDER_HI if self._hovered else theme.RUBBER_DEEP)
        painter.fillRect(self.rect(), ground)

        painter.setPen(QPen(QColor(theme.TREAD), 1))
        painter.drawLine(0, self.height() - 1, self.width(), self.height() - 1)

        if self._struck:
            pen = QPen(QColor(theme.STRUCK), 2)
            painter.setPen(pen)
            middle = self.height() // 2
            painter.drawLine(CompoundBand.WIDTH + 12, middle,
                             self.width() - self._strike_right, middle)
        painter.end()
