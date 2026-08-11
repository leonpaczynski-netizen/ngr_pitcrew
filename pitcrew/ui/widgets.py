"""Shared marks: the primitives every Pit Crew screen is built from.

Nothing here is a generic component wearing a colour. A panel is a bolted
plate with its label struck through the top edge; a band is the coloured ring
a crew paints on a set; a value knows whether it was measured or declared and
renders in the matching register.
"""
from __future__ import annotations

from PyQt6.QtCore import (
    QEasingCurve,
    QEvent,
    QObject,
    QPropertyAnimation,
    QRectF,
    Qt,
    pyqtProperty,
    pyqtSignal,
)
from PyQt6.QtGui import QColor, QFont, QPainter, QPen
from PyQt6.QtWidgets import (
    QAbstractScrollArea,
    QAbstractSpinBox,
    QApplication,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from pitcrew.ui import theme


class _WheelGuard(QObject):
    """Stops the mouse wheel silently changing a setting you scrolled past.

    Qt's default is that a wheel over an unfocused combo or spin box edits it.
    On a page of setup values that means scrolling the form quietly rewrites
    the car — the driver would take a sheet to the track with a value nobody
    typed. The event is forwarded to the enclosing scroll area instead, so the
    page still scrolls.
    """

    def eventFilter(self, obj, event) -> bool:  # noqa: N802 - Qt naming
        if event.type() != QEvent.Type.Wheel or obj.hasFocus():
            return False
        scroller = obj.parentWidget()
        while scroller is not None and not isinstance(scroller, QAbstractScrollArea):
            scroller = scroller.parentWidget()
        if scroller is not None:
            QApplication.sendEvent(scroller.viewport(), event)
        return True


_WHEEL_GUARD = _WheelGuard()


def block_wheel(widget: QWidget) -> QWidget:
    """Make a value widget ignore the wheel until it is deliberately focused."""
    if isinstance(widget, (QComboBox, QAbstractSpinBox)):
        widget.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        widget.installEventFilter(_WHEEL_GUARD)
        if isinstance(widget, QComboBox):
            # A combo's own view scrolls on wheel too; the guard above only
            # covers the collapsed control.
            widget.view().setFocusPolicy(Qt.FocusPolicy.StrongFocus)
    return widget


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
                 danger: bool = False, compact: bool = False,
                 parent: QWidget | None = None) -> None:
        super().__init__(text.upper(), parent)
        self.setFont(theme.stencil_font(11 if compact else 13,
                                        tracking=6.0 if compact else 12.0))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(34 if compact else 40)
        padding = "4px 8px" if compact else "9px 20px"

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
                padding: {padding};
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

        # Every text row reserves its real line height rather than the height
        # Qt reports. Bahnschrift's ascenders and descenders run past that, and
        # at 125% display scaling the difference is enough for a label to sit
        # on the box below it.
        caption = StencilLabel(label, size=11, tracking=12.0)
        caption.setMinimumHeight(caption.fontMetrics().height() + 2)
        caption.setSizePolicy(caption.sizePolicy().horizontalPolicy(),
                              QSizePolicy.Policy.Fixed)
        column.addWidget(caption)

        # A field sharing a grid row with a taller neighbour can be squeezed
        # until its editor is a sliver. Pin the height, and drop the spinner
        # arrows: they crowd the box at this size, and every value here is
        # typed from a screen the driver is reading anyway.
        editor.setMinimumHeight(34)
        editor.setSizePolicy(QSizePolicy.Policy.Expanding,
                             QSizePolicy.Policy.Fixed)
        block_wheel(editor)
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
            note.setMinimumHeight(note.fontMetrics().height() + 4)
            note.setSizePolicy(note.sizePolicy().horizontalPolicy(),
                               QSizePolicy.Policy.Fixed)
            column.addSpacing(2)
            column.addWidget(note)

        # Nothing in a field stretches vertically: a grid row taller than this
        # one leaves space below rather than smearing it between the rows.
        column.addStretch(0)
        self.setSizePolicy(QSizePolicy.Policy.Preferred,
                           QSizePolicy.Policy.Minimum)

        self.editor = editor


class Picker(QWidget):
    """A dropdown you cannot mistype into, plus a way to add what is missing.

    Free text was letting a typo through: "Fuji Speedwya" would save happily
    and then match nothing next session. But the shipped track catalogue is
    incomplete, so a closed list alone would block real events. Both are solved
    by making the list authoritative and letting the driver extend it once —
    after which the name is in the dropdown forever.
    """

    added = pyqtSignal(str)

    def __init__(self, items, *, placeholder: str = "", allow_add: bool = True,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._placeholder = placeholder

        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)

        self.combo = QComboBox()
        self.combo.setMinimumHeight(34)
        self.combo.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.combo.setMinimumContentsLength(12)
        block_wheel(self.combo)
        self.combo.currentIndexChanged.connect(self._sync_ink)
        self.set_items(items)
        row.addWidget(self.combo, 1)

        self._add_button = None
        self._entry = None
        if allow_add:
            self._add_button = MarkButton("Add", compact=True)
            self._add_button.setFixedWidth(56)
            self._add_button.setToolTip("Add one the list is missing")
            self._add_button.clicked.connect(self._begin_add)
            row.addWidget(self._add_button)

            self._entry = QLineEdit()
            self._entry.setPlaceholderText("Name it exactly as GT7 spells it")
            self._entry.setMinimumHeight(34)
            self._entry.hide()
            self._entry.returnPressed.connect(self._commit_add)
            row.addWidget(self._entry, 1)

    # ------------------------------------------------------------------ value

    def set_items(self, items) -> None:  # noqa: N802 - Qt naming
        current = self.currentText()
        self.combo.clear()
        self.combo.addItem(self._placeholder or "—", None)
        for item in items:
            self.combo.addItem(item, item)
        if current:
            self.setCurrentText(current)
        self._sync_ink()

    def _sync_ink(self) -> None:
        """Nothing chosen reads struck, not crayon.

        The same discipline as a placeholder: an unset field must never look
        like a value the driver declared.
        """
        palette = self.combo.palette()
        chosen = self.combo.currentData() is not None
        palette.setColor(palette.ColorRole.ButtonText,
                         QColor(theme.CRAYON if chosen else theme.STRUCK))
        palette.setColor(palette.ColorRole.Text,
                         QColor(theme.CRAYON if chosen else theme.STRUCK))
        self.combo.setPalette(palette)

    def currentText(self) -> str:  # noqa: N802 - Qt naming
        return self.combo.currentData() or ""

    def setCurrentText(self, text: str) -> None:  # noqa: N802 - Qt naming
        if not text:
            self.combo.setCurrentIndex(0)
            return
        index = self.combo.findData(text)
        if index < 0:
            self.combo.addItem(text, text)
            index = self.combo.count() - 1
        self.combo.setCurrentIndex(index)

    def items(self) -> list[str]:
        return [self.combo.itemData(i) for i in range(1, self.combo.count())]

    # -------------------------------------------------------------- adding

    def _begin_add(self) -> None:
        # Inline, never a modal: a dialog waiting on a human is a hang
        # anywhere there is no human, and this app is driven by tests too.
        self.combo.hide()
        self._add_button.hide()
        self._entry.show()
        self._entry.setFocus()

    def _commit_add(self) -> None:
        name = self._entry.text().strip()
        self._entry.clear()
        self._entry.hide()
        self.combo.show()
        self._add_button.show()
        if not name:
            return
        if self.combo.findData(name) < 0:
            self.combo.addItem(name, name)
        self.setCurrentText(name)
        self.added.emit(name)


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
