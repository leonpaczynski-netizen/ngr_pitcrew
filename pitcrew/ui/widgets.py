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


def struck_when_empty(box: QAbstractSpinBox) -> QAbstractSpinBox:
    """Paint a spin box's "nothing entered" dash struck, not crayon.

    `setSpecialValueText("—")` renders in the ordinary text colour, and now
    that editors honour the palette that colour is crayon - so a setting
    nobody entered would read as one the driver declared. That is the same
    failure as the one this app was built to prevent, wearing a dash.

    Placeholders solve it through `QPalette.PlaceholderText`; a special value
    is not a placeholder, so it is switched by hand here.
    """
    def sync() -> None:
        empty = box.value() <= box.minimum()
        colour = QColor(theme.STRUCK if empty else theme.CRAYON)
        # On the line edit, not the spin box. A spin box's editor keeps its
        # own resolved palette once the parent's has been set, so a later
        # change to the parent never reaches it - which left every entered
        # value painted in the struck grey of the empty one it started as.
        target = box.lineEdit() if hasattr(box, "lineEdit") else None
        for widget in (box, target):
            if widget is None:
                continue
            palette = widget.palette()
            palette.setColor(palette.ColorRole.Text, colour)
            widget.setPalette(palette)

    box.valueChanged.connect(lambda _value: sync())
    sync()
    return box


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


class Derived(Measured):
    """A value the app worked out. Neither measured nor declared.

    The register that was missing. Without it every computed figure had to
    borrow an ink that meant something else, and the two that borrowed were
    the two that carry the most consequence - a modelled stint length wearing
    the disabled grey, and "Box in 3" wearing the ink for what the driver
    typed himself.
    """

    def __init__(self, text: str = "", **kwargs) -> None:
        kwargs.setdefault("colour", theme.DERIVED)
        super().__init__(text, **kwargs)


class EmptyState(QWidget):
    """What a plate says when it has nothing in it yet.

    Strategy and Race rested as large empty rectangles - about a million
    pixels of bordered nothing between them - with the only explanation a
    subtitle outside the plate. On Race that is the screen looked at straight
    after the headset comes off, where "no calls" and "it died before it
    recorded any" are the same picture.

    So the absence names itself, and names what would fill it. Set in prose,
    not in a register: nothing here is a value.
    """

    def __init__(self, headline: str, needs=(), *,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        column = QVBoxLayout(self)
        column.setContentsMargins(0, theme.GAP, 0, theme.GAP)
        column.setSpacing(theme.GAP_TIGHT)
        # Held to a readable measure. A plate here can be 1360px wide, and
        # prose set across all of it is one line the eye cannot track back.
        lead = BodyLabel(headline, colour=theme.STENCIL_DIM)
        lead.setMaximumWidth(620)
        column.addWidget(lead)
        for item in needs:
            row = BodyLabel(f"—  {item}", size=14, colour=theme.STENCIL_DIM)
            row.setContentsMargins(theme.GAP, 0, 0, 0)
            column.addWidget(row)
        column.addStretch(1)


class Plate(QFrame):
    """A bolted panel whose stencilled label is struck through its top edge.

    The plate's drawn border starts below the widget's own top, so the label
    can sit centred on that rule with its full cap height inside the widget.
    Straddling y=0 instead would clip the tops of the letters, which is what
    the first render did.
    """

    LABEL_INSET = 16
    LABEL_PAD = 8
    TOP_RESERVE = 11   # space above the drawn border for the label to sit in

    def __init__(self, title: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._title = title.upper()
        self._label_font = theme.stencil_font(theme.PLATE_TITLE_PX,
                                              tracking=14.0)
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
        painter.setPen(QPen(QColor(theme.STENCIL)))
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
        # Large text, deliberately. The two-letter code is the band's
        # redundant channel, and four of the eleven racing colours cannot
        # reach 4.5:1 against either ink without repainting colours that are
        # the sport's, not ours. At 19px DemiBold it is large text, where the
        # floor is 3:1 and every band clears it - and it reads better from the
        # driving position, which is where it is actually read.
        self._font = theme.stencil_font(19, tracking=4.0,
                                        weight=QFont.Weight.Bold)

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
        self._danger = danger
        self._compact = compact
        self.set_primary(primary)

    def set_primary(self, primary: bool) -> None:
        """Fill the plate, or empty it.

        Re-appliable, so a row of buttons standing for a choice can show which
        one is selected. Qt's `setDown` does not survive the next repaint, and
        a selection nobody can see is the same as no selection.
        """
        danger, compact = self._danger, self._compact
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
            derived: bool = False, emphasis: bool = False) -> None:
        if self._entries:
            separator = StencilLabel("·", size=theme.BODY_PX,
                                     colour=theme.TREAD_LIGHT, tracking=0.0)
            separator.setContentsMargins(14, 0, 14, 0)
            self._row.addWidget(separator)

        name = StencilLabel(label, size=11, colour=theme.STENCIL_DIM,
                            tracking=14.0)
        name.setContentsMargins(0, 0, 8, 0)
        cls = Derived if derived else Declared if declared else Measured
        reading = cls(value, size=theme.DATA_LARGE_PX if emphasis else theme.DATA_PX,
                      bold=emphasis)
        self._row.addWidget(name)
        self._row.addWidget(reading)
        self._entries.append((name, reading))

    def finish(self) -> None:
        self._row.addStretch(1)


class HintLabel(BodyLabel):
    """One line of guidance that shrinks instead of pushing the pane wider.

    Hints must not wrap: a wrapped hint reports a one-line height at its size
    hint and then overruns the field below it once the grid hands it a
    narrower column. But a non-wrapping label demands its full text width
    forever, and with the scroll areas set to never show a horizontal bar,
    that demand turned into content nobody could reach - Event lost 96px and
    the Race Engineer 107px at 1280x800, with no bar to scroll to them.

    So it keeps one line and gives up characters instead of space. The whole
    hint stays available as a tooltip, because an elided hint that cannot be
    read in full is only half a fix.
    """

    def __init__(self, text: str, **kwargs) -> None:
        kwargs.setdefault("size", 12)
        kwargs.setdefault("colour", theme.STENCIL_DIM)
        super().__init__(text, wrap=False, **kwargs)
        self._full = text
        self.setToolTip(text)
        self.setMinimumHeight(self.fontMetrics().height() + 4)
        self.setSizePolicy(QSizePolicy.Policy.Ignored,
                           QSizePolicy.Policy.Fixed)

    def resizeEvent(self, event) -> None:          # noqa: N802 - Qt naming
        super().resizeEvent(event)
        metrics = self.fontMetrics()
        self.setText(metrics.elidedText(self._full, Qt.TextElideMode.ElideRight,
                                        max(0, self.width())))


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
            unit = StencilLabel(suffix, size=11,
                                colour=theme.STENCIL_DIM,
                                tracking=8.0)
            row.addWidget(unit)
        column.addLayout(row)

        if hint:
            column.addSpacing(2)
            column.addWidget(HintLabel(hint))

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

    changed = pyqtSignal(str)

    def __init__(self, items=None, *, placeholder: str = "",
                 groups=None, parent: QWidget | None = None) -> None:
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
        # The popup is sized independently of the collapsed control, otherwise
        # a long name is elided to "24 Heures du...cing Circuit" and two
        # circuits become indistinguishable in the one place it matters.
        self.combo.view().setTextElideMode(Qt.TextElideMode.ElideNone)
        block_wheel(self.combo)
        self.combo.currentIndexChanged.connect(self._on_index_changed)
        if groups is not None:
            self.set_groups(groups)
        else:
            self.set_items(items or [])
        row.addWidget(self.combo, 1)

    # ------------------------------------------------------------------ value

    def set_items(self, items) -> None:  # noqa: N802 - Qt naming
        self.set_groups([(None, list(items))])

    def set_groups(self, groups) -> None:  # noqa: N802 - Qt naming
        """Populate from [(heading or None, [names]), ...].

        Headings are inserted as unselectable rows so a long list can be
        skimmed by class instead of scrolled by alphabet.
        """
        current = self.currentText()
        self.combo.blockSignals(True)
        self.combo.clear()
        self.combo.addItem(self._placeholder or "—", None)

        widest = self._placeholder or ""
        for heading, names in groups:
            if heading:
                self.combo.addItem(f"— {heading} —", None)
                self._disable_last_item()
            for name in names:
                self.combo.addItem(name, name)
                if len(name) > len(widest):
                    widest = name
        self.combo.blockSignals(False)

        metrics = self.combo.view().fontMetrics()
        self.combo.view().setMinimumWidth(
            metrics.horizontalAdvance(widest) + 44)

        if current:
            self.setCurrentText(current)
        self._sync_ink()

    def _disable_last_item(self) -> None:
        model = self.combo.model()
        item = model.item(self.combo.count() - 1)
        if item is not None:
            item.setEnabled(False)

    def _on_index_changed(self) -> None:
        self._sync_ink()
        self.changed.emit(self.currentText())

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
        """Selectable names, headings excluded."""
        return [self.combo.itemData(i) for i in range(1, self.combo.count())
                if self.combo.itemData(i) is not None]

    def setEnabledState(self, enabled: bool) -> None:  # noqa: N802 - Qt naming
        self.combo.setEnabled(enabled)


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


# ------------------------------------------------------------- the tyre gauge
#
# GT7 draws four tyres and fills each one as it wears. Reading a figure off
# that picture and typing `0.55` into a spin box is a transcription step, and
# transcription is where numbers get transposed - which is why this is a
# picture he drags to match rather than a number he retypes.
#
# The fill is graded rather than flat red because GT7's own indicator is
# graded, and because the grades are already in the app's model: the flat
# phase to 50%, the progressive phase to 90%, then the cliff (CLAUDE.md §5.1).
# So dragging past the amber band tells him he is into the phase where balance
# shifts before the stopwatch does, without the widget having to say so.
#
# Colour is never the only channel here either. Every gauge carries its corner
# and its percentage as text, so nothing depends on separating the hues.

PHASE_FLAT_UNTIL = 0.50
PHASE_CLIFF_FROM = 0.90


def wear_colour(fraction: float) -> QColor:
    """Fill colour for a fraction consumed, on the model's own phase bands."""
    if fraction < PHASE_FLAT_UNTIL:
        return QColor("#3FA34D")        # flat phase - losses in tenths
    if fraction <= PHASE_CLIFF_FROM:
        return QColor(theme.WARNING)    # progressive - balance shifts first
    return QColor(theme.DANGER)         # cliff - undriveable, not merely slow


def wear_phase(fraction: float) -> str:
    if fraction < PHASE_FLAT_UNTIL:
        return "flat"
    if fraction <= PHASE_CLIFF_FROM:
        return "linear"
    return "cliff"


class TyreGauge(QWidget):
    """One corner of the in-game tyre gauge, dragged to match what GT7 shows.

    Empty is *unread*, not zero - a zero would mean a fresh tyre and would be
    believed. Clearing is therefore a first-class action (Delete), not
    something achieved by dragging to the bottom.
    """

    changed = pyqtSignal()

    WIDTH = 46
    HEIGHT = 62
    STEP = 0.05
    PAGE_STEP = 0.25

    def __init__(self, corner: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._corner = corner.lower()
        self._fraction: float | None = None
        self._dragging = False
        self._limiting = False
        self.setFixedSize(self.WIDTH, self.HEIGHT)
        self.setCursor(Qt.CursorShape.SizeVerCursor)
        # Reachable by keyboard, not only by drag: a load-cell brake does not
        # help you here, and a mouse-only control fails anyone who cannot make
        # a precise drag.
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._label_font = theme.stencil_font(10, tracking=8.0)
        self._value_font = theme.data_font(14, weight=QFont.Weight.Bold)
        self._sync_tooltip()

    # ------------------------------------------------------------------ value

    def fraction(self) -> float | None:
        return self._fraction

    def setFraction(self, value: float | None) -> None:  # noqa: N802 - Qt naming
        if value is not None:
            value = round(max(0.0, min(1.0, value)), 2)
        if value == self._fraction:
            return
        self._fraction = value
        self._sync_tooltip()
        self.update()
        self.changed.emit()

    def setLimiting(self, limiting: bool) -> None:  # noqa: N802 - Qt naming
        """Mark this as the corner that ends the stint."""
        if limiting != self._limiting:
            self._limiting = limiting
            self.update()

    def _sync_tooltip(self) -> None:
        name = self._corner.upper()
        if self._fraction is None:
            text = (f"{name}: not read. Drag down to match the in-game gauge, "
                    f"or use the arrow keys.")
        else:
            text = (f"{name}: {self._fraction:.0%} consumed "
                    f"({wear_phase(self._fraction)} phase). "
                    f"Delete clears it back to unread.")
        self.setToolTip(text)
        self.setAccessibleName(f"{name} tyre wear")
        self.setAccessibleDescription(text)

    # ----------------------------------------------------------------- events

    def _fraction_at(self, y: float) -> float:
        return max(0.0, min(1.0, y / max(1, self.height())))

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt naming
        if event.button() != Qt.MouseButton.LeftButton:
            return
        self._dragging = True
        self.setFraction(self._fraction_at(event.position().y()))

    def mouseMoveEvent(self, event) -> None:  # noqa: N802 - Qt naming
        if self._dragging:
            self.setFraction(self._fraction_at(event.position().y()))

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 - Qt naming
        self._dragging = False

    def keyPressEvent(self, event) -> None:  # noqa: N802 - Qt naming
        key = event.key()
        current = self._fraction if self._fraction is not None else 0.0
        if key in (Qt.Key.Key_Up, Qt.Key.Key_Right):
            self.setFraction(current + self.STEP)
        elif key in (Qt.Key.Key_Down, Qt.Key.Key_Left):
            self.setFraction(current - self.STEP)
        elif key == Qt.Key.Key_PageUp:
            self.setFraction(current + self.PAGE_STEP)
        elif key == Qt.Key.Key_PageDown:
            self.setFraction(current - self.PAGE_STEP)
        elif key == Qt.Key.Key_Home:
            self.setFraction(0.0)
        elif key == Qt.Key.Key_End:
            self.setFraction(1.0)
        elif key in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            self.setFraction(None)
        else:
            super().keyPressEvent(event)

    # ------------------------------------------------------------------ paint

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt naming
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        body = QRectF(1.5, 1.5, self.width() - 3, self.height() - 3)

        # The unworn tyre. Pale, so the fill reads as rubber going away.
        painter.setBrush(QColor(theme.STENCIL if self._fraction is not None
                                else theme.SHOULDER_HI))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(body, 4, 4)

        if self._fraction:
            # Fills downward from the top, the direction of the drag, so the
            # gesture and the result point the same way.
            worn = QRectF(body.x(), body.y(),
                          body.width(), body.height() * self._fraction)
            painter.setBrush(wear_colour(self._fraction))
            painter.drawRoundedRect(worn, 4, 4)

        border = (QColor(theme.CRAYON) if self._limiting else
                  QColor(theme.TREAD_LIGHT if self.hasFocus() else theme.TREAD))
        painter.setPen(QPen(border, 2.0 if self._limiting or self.hasFocus() else 1.0))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(body, 4, 4)

        # Corner name, always on the dark ground at the foot of the gauge so
        # it never lands on the fill boundary.
        painter.setFont(self._label_font)
        painter.setPen(QPen(QColor(theme.RUBBER if self._fraction is not None
                                   else theme.STENCIL_DIM)))
        painter.drawText(self.rect().adjusted(0, 0, 0, -4),
                         Qt.AlignmentFlag.AlignBottom
                         | Qt.AlignmentFlag.AlignHCenter,
                         self._corner.upper())

        painter.setFont(self._value_font)
        if self._fraction is None:
            painter.setPen(QPen(QColor(theme.STENCIL_DIM)))
            text = "—"
        else:
            # Ink chosen against whichever band the number is sitting on, not
            # against the widget as a whole.
            painter.setPen(QPen(QColor(theme.RUBBER)))
            text = f"{self._fraction:.0%}"
        painter.drawText(self.rect().adjusted(0, 4, 0, 0),
                         Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter,
                         text)
        painter.end()


class TyreGaugeSet(QWidget):
    """Four corners, laid out as the car — front axle on top.

    Only shown where it is worth reading: the last lap of a stint. A gauge on
    every lap would be four more controls per row asking to be filled in, and
    a wear reading taken mid-stint tells the model nothing the end-of-stint
    one does not.
    """

    changed = pyqtSignal()

    CORNERS = ("fl", "fr", "rl", "rr")

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._gauges: dict[str, TyreGauge] = {}

        grid = QVBoxLayout(self)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(4)
        for axle in (("fl", "fr"), ("rl", "rr")):
            row = QHBoxLayout()
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(4)
            for corner in axle:
                gauge = TyreGauge(corner)
                gauge.changed.connect(self._on_changed)
                self._gauges[corner] = gauge
                row.addWidget(gauge)
            grid.addLayout(row)

    def _on_changed(self) -> None:
        self._mark_limiting()
        self.changed.emit()

    def _mark_limiting(self) -> None:
        """Outline the corner that ends the stint, which is the worst one."""
        read = {corner: gauge.fraction()
                for corner, gauge in self._gauges.items()
                if gauge.fraction() is not None}
        worst = max(read, key=read.__getitem__) if read else None
        # Only worth pointing at when there is something to choose between.
        if worst is not None and len(set(read.values())) == 1:
            worst = None
        for corner, gauge in self._gauges.items():
            gauge.setLimiting(corner == worst)

    def values(self) -> dict[str, float | None]:
        return {corner: gauge.fraction()
                for corner, gauge in self._gauges.items()}

    def setValues(self, values: dict[str, float | None]) -> None:  # noqa: N802
        for corner, gauge in self._gauges.items():
            gauge.blockSignals(True)
            gauge.setFraction(values.get(corner))
            gauge.blockSignals(False)
        self._mark_limiting()
        self.update()
