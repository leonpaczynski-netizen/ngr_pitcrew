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


# **Built on demand, not at import, and rebuilt if Qt takes it away.**
#
# This was `_WHEEL_GUARD = _WheelGuard()` at module scope, which constructs a
# QObject before any QApplication exists and keeps one Python reference to it
# for the life of the process. When a test file tears its QApplication down,
# Qt deletes the C++ object underneath, and the next file to call
# `block_wheel` dies with `RuntimeError: wrapped C/C++ object of type
# _WheelGuard has been deleted` - in setup, so every test in that file errors
# rather than fails.
#
# That is why the suite could not be run as one command: it was not a product
# defect and not the test that tripped over it, it was a module-level QObject
# outliving the application it belonged to. The full run cost a quarter of the
# suite to it.
_WHEEL_GUARD: "_WheelGuard | None" = None


def _wheel_guard() -> "_WheelGuard":
    """The shared guard, alive. Recreated if its C++ side has been deleted.

    Liveness is tested by calling into the object rather than by asking sip,
    because the question is exactly "will the next call raise" and that is
    the call that answers it.
    """
    global _WHEEL_GUARD
    guard = _WHEEL_GUARD
    if guard is not None:
        try:
            guard.parent()
        except RuntimeError:
            guard = None
    if guard is None:
        guard = _WheelGuard()
        _WHEEL_GUARD = guard
    return guard


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
        widget.installEventFilter(_wheel_guard())
        if isinstance(widget, QComboBox):
            # A combo's own view scrolls on wheel too; the guard above only
            # covers the collapsed control.
            widget.view().setFocusPolicy(Qt.FocusPolicy.StrongFocus)
    return widget


class StencilLabel(QLabel):
    """Tracked condensed caps, cut the way a technical plate is stencilled.

    **The size travels in the style sheet, and for a long time it did not.**
    `theme.apply` sets `QWidget { font-size: 15px }`, a style-sheet rule beats
    `setFont`, and nothing here restated it - so every stencilled label in the
    app rendered at 15px whatever size it asked for. `StencilLabel(size=10)`,
    `size=15` and `size=20` all painted 111px wide and 15px tall, measured.

    It flattened the whole type hierarchy: the 10px column heads, the 11px
    plate captions, the 12px hints and the 13px stint lines were one size, and
    DESIGN.md described a scale the app was not drawing. It surfaced as a
    clipped column head - "WEAR AT END" needs 48px at the 10px it asks for and
    111px at the 15px it was given, in a 92px column - which is how a defect
    that had been in every screen for the life of the app came to be reported
    as one word losing a letter.

    Third instance of this cascade, and they are all the same shape: a
    style-sheet rule silently beating a per-widget setting. `QWidget { color }`
    beat `QPalette.Text` and made every declared value render as a measured
    one; `QWidget { font-size }` beat `setFont` here and in `Measured`.
    """

    def __init__(self, text: str = "", *, size: int = theme.LABEL_PX,
                 colour: str = theme.STENCIL_DIM, tracking: float = 10.0,
                 weight: QFont.Weight = QFont.Weight.DemiBold,
                 parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.setFont(theme.stencil_font(size, weight=weight, tracking=tracking))
        self._size_css = f"font-size: {size}px;"
        self.set_ink(colour)

    def set_ink(self, colour: str) -> None:
        self.setStyleSheet(
            f"color: {colour}; background: transparent;" + self._size_css)


class BodyLabel(QLabel):
    def __init__(self, text: str = "", *, size: int = theme.BODY_PX,
                 colour: str = theme.STENCIL_DIM, wrap: bool = True,
                 bold: bool = False,
                 parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.setFont(theme.text_font(
            size, weight=QFont.Weight.DemiBold if bold else QFont.Weight.Normal))
        # Same cascade as `StencilLabel`: `QWidget { font-size: 15px }` beats
        # `setFont`, so a size asked for here has to be restated in the rule
        # that is winning or it is not applied at all.
        self._size_css = f"font-size: {size}px;"
        self.set_ink(colour)
        self.setWordWrap(wrap)

    def set_ink(self, colour: str) -> None:
        """Recolour without dropping the transparent background or the size.

        Five call sites across three screens replaced the whole style sheet
        with `color:` alone, so the label fell back to the app-wide
        `QWidget { background: RUBBER }` and painted a dark rectangle over the
        `SHOULDER` plate it was sitting on. Nine other sites got it right,
        which made it inconsistency rather than a decision.
        """
        self.setStyleSheet(
            f"color: {colour}; background: transparent;" + self._size_css)


class Measured(QLabel):
    """A value that came off the telemetry stream. Stencil white, mono."""

    def __init__(self, text: str = "", *, size: int = theme.DATA_PX,
                 colour: str = theme.STENCIL, bold: bool = False,
                 parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        weight = QFont.Weight.DemiBold if bold else QFont.Weight.Normal
        self.setFont(theme.data_font(size, weight=weight))
        # Kept so `set_rank` can put the ordinary ink back when the mark goes
        # away - a row stops being the best the moment a quicker lap lands.
        self._ink = colour
        self._rank: str | None = None
        # **The size goes in the stylesheet, not only in the font.**
        # `theme.apply` sets `QWidget { font-size: 15px }`, and a stylesheet
        # rule beats `setFont` - so every label in this app was 15px whatever
        # size it asked for, and nothing showed it until something asked for
        # 78. It is the same cascade the registers were caught by, where
        # `QWidget { color }` beat `QPalette.Text` and every declared value
        # rendered as a measured one.
        self._size_css = f"font-size: {size}px;"
        self._paint()

    def _paint(self) -> None:
        self.setStyleSheet(
            f"color: {self._rank or self._ink}; background: transparent;"
            + self._size_css)

    def set_ink(self, colour: str) -> None:
        """Change the ordinary ink without losing the timing mark.

        The rack re-inks a whole row every time a mark changes - struck laps
        and out-laps go dim - and it did that with a raw `setStyleSheet`,
        which silently wiped the mark. So a lap held its purple until the
        first time anything on its row was touched, and then lost it.
        """
        self._ink = colour
        self._paint()

    def set_rank(self, rank: str | None) -> None:
        """Mark this figure as the fastest ever, the fastest this stint, or
        neither — **in the ink, which is where the driver reads it.**

        This was a fill behind the number, on the argument that purple text
        was spoken for by the DERIVED register. The driver's report settles
        it the other way: on a column of times, purple already means fastest
        to him, so a rack whose every sector was purple read as a rack where
        every sector was the best one. See `theme.BEST_EVER`.

        `None` restores the ordinary ink rather than clearing to a default -
        an ordinary sector is dimmer than a measured lap time, and losing
        that would make the app's own cut of the lap look like a figure off
        the stream.
        """
        self._rank = rank
        self._paint()


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
            # **Measured against the colour actually painted.** The ink
            # was chosen against the undesaturated band and then the band was
            # desaturated and the ink dropped to alpha 150, which put the
            # code at 1.51-2.92:1 on eight of eleven compounds - below the
            # 3:1 the design states all eleven clear, in the one state where
            # colour becomes the only channel. Eight of the eleven chips on
            # the Event screen are in that state by default.
            ink = theme.band_ink_for(over)
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
            hover = theme.CRAYON_HOT
        elif danger:
            # DANGER on the hover ground is 3.65:1 at 13px DemiBold, which is
            # not large text. DANGER_INK is the same red lifted to clear the
            # body floor on every ground this button sits on; the border keeps
            # the racing red so the control still reads as the dangerous one.
            base, ink, edge = "transparent", theme.DANGER_INK, theme.DANGER
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
            derived: bool = False, warn: bool = False,
            emphasis: bool = False, tooltip: str = "") -> None:
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
        if warn:
            # A gap, not a register. Nothing was measured, declared or worked
            # out - the answer is missing, and the evidence column already
            # paints that state in warning.
            reading.setStyleSheet(
                f"color: {theme.WARNING}; background: transparent;")
        if tooltip:
            # On both halves: the label is the smaller target and it is the
            # one a reader points at when the word is what they did not
            # understand.
            name.setToolTip(tooltip)
            reading.setToolTip(tooltip)
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
                 data: bool | None = None,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        # **Which face this editor takes.** Mono is measurement; everything
        # else is Bahnschrift. A field holding a figure says so and gets the
        # mono face back; a field holding a name, a note or a sentence does
        # not. Inferred from the editor's type where it is obvious - a spin
        # box is always a number - so only the ambiguous line edits have to
        # say. See the `[data="true"]` rule in `theme`.
        if data is None:
            data = isinstance(editor, QAbstractSpinBox)
        editor.setProperty("data", "true" if data else "false")
        column = QVBoxLayout(self)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(theme.GAP_TIGHT)

        # Every text row reserves its real line height rather than the height
        # Qt reports. Bahnschrift's ascenders and descenders run past that, and
        # at 125% display scaling the difference is enough for a label to sit
        # on the box below it.
        caption = StencilLabel(label, size=11, tracking=12.0)
        # **The caption belongs to the editor.** A grep of the whole package
        # found no `setBuddy` and two `setAccessibleName`, so every one of the
        # app's ~80 form controls was anonymous to assistive tech and carried
        # no Alt-mnemonic. One line here covers all of them, because every
        # labelled control on every screen is built through this class.
        caption.setBuddy(editor)
        if not editor.accessibleName():
            editor.setAccessibleName(label)
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
            # The hint elides, so it is also the only place the whole
            # sentence lives - it belongs to the control it explains rather
            # than to the pixels beside it.
            editor.setAccessibleDescription(hint)

        # Nothing in a field stretches vertically: a grid row taller than this
        # one leaves space below rather than smearing it between the rows.
        column.addStretch(0)
        self.setSizePolicy(QSizePolicy.Policy.Preferred,
                           QSizePolicy.Policy.Minimum)

        self.editor = editor


def mark_unset(combo, *, unset=None, unset_index: int | None = None):
    """Paint a combo struck while it holds nothing, crayon once it does.

    `Picker` has done this since it was written; every *bare* `QComboBox` in
    the app did not, and there are a dozen. Their "—" and "Not answered" rows
    took `QPalette.ButtonText`, which is crayon - so an untagged lap's dash
    read as the same declaration as a tagged lap's "RM", and "Not answered"
    for *can this circuit rain* - a deliberate tri-state where unanswered is
    explicitly not "cannot rain" - read as an answer.

    Call once after building the combo; it wires itself to the signal.

    `unset_index` is for combos built with `addItems`, which carry no item
    data at all - there the sentinel is the row's position, not its value.

    Returns the sync, for the one caller that rebuilds its combo's rows inside
    `blockSignals(True)`: the signal cannot fire there, so the ink would be
    left describing the list the combo used to hold.
    """
    def sync() -> None:
        chosen = (combo.currentIndex() != unset_index
                  if unset_index is not None
                  else combo.currentData() is not unset)
        palette = combo.palette()
        ink = QColor(theme.CRAYON if chosen else theme.STRUCK)
        palette.setColor(palette.ColorRole.ButtonText, ink)
        palette.setColor(palette.ColorRole.Text, ink)
        combo.setPalette(palette)

    combo.currentIndexChanged.connect(sync)
    sync()
    return sync


class Picker(QWidget):
    """A dropdown you cannot mistype into.

    Free text was letting a typo through: "Fuji Speedwya" would save happily
    and then match nothing next session, so the list is authoritative.

    **There is no way to add to it from here**, and this docstring used to say
    there was — "letting the driver extend it once, after which the name is in
    the dropdown forever". No such control was ever built, and the signal that
    would have carried it has been removed rather than left connected to a
    live store write with no emitter, which is how the next reader comes to
    assume it works. A circuit the catalogue is missing is fixed in
    `data/gt7_tracks.json`, which one page owns and a test enforces agreement
    on.
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
        # A `Picker` is a plain QWidget wrapping the combo, so its focus policy
        # is NoFocus and `setFocus()` on it did nothing at all - which made the
        # save message's "and go there" a no-op for Track and Car, the two it
        # names most often. Tab reaches the combo either way; this makes the
        # programmatic half work too.
        self.setFocusProxy(self.combo)
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

        # **Restoring may not add.** This used to go through `setCurrentText`,
        # which appends the name when `findData` misses - so changing the track
        # kept the old track's layout AND injected it into the new track's
        # list: Le Mans / Full Course, switch to Alsace, and Alsace offers
        # Full Course. 31 circuits have more than one layout, and layout is
        # what the track model, the station map and the rain list key on.
        # A selection the new list does not contain has stopped existing;
        # the placeholder is the honest answer, and the caller decides what
        # to put there.
        if current:
            index = self.combo.findData(current)
            self.combo.setCurrentIndex(index if index >= 0 else 0)
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
        """Select a name, adding it if the catalogue does not carry it.

        The add is for *stored* values only - an event saved against a circuit
        the catalogue has since renamed must still show what it was raced on,
        and blanking it would throw the fact away on the next save. Nothing
        the driver can reach calls this with a name he typed, and `set_groups`
        deliberately does not use it: an add there is a leak from one track's
        list into another's.
        """
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


class CascadingPicker(QWidget):
    """Three dependent dropdowns for one value: class, then maker, then car.

    A `Picker` over the whole car catalogue is 608 rows behind eight headings,
    and 369 of them sit under `Road Car`. Headings make that skimmable; they
    do not make it choosable. Narrowing by class and then by manufacturer
    turns one long scroll into three short ones, and the two narrowing steps
    are throwaway - only the last combo carries a value.

    **Only the final selection is the value.** `currentText` is the car and
    nothing else, `changed` fires for the car and nothing else, so this is a
    drop-in for `Picker` everywhere the event screen uses one. Class and maker
    are navigation; they are never saved and never read back.
    """

    changed = pyqtSignal(str)

    def __init__(self, groups=None, *, placeholder: str = "",
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._placeholder = placeholder
        # {category: {maker: (name, ...)}}, the whole catalogue.
        self._catalog: dict[str, dict[str, tuple[str, ...]]] = {}
        # A stored car the catalogue no longer carries. Held apart from
        # `_catalog` so it shows without being offered to anyone else - the
        # same rule `Picker.setCurrentText` follows and for the same reason.
        self._unlisted: str | None = None
        self._loading = False

        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)

        self.category_combo = self._combo("Class")
        self.maker_combo = self._combo("Make")
        self.car_combo = self._combo(placeholder or "Car")
        # The car name is the long one and the only one worth reading in full,
        # so it takes the width and the two narrowing steps stay compact.
        row.addWidget(self.category_combo, 2)
        row.addWidget(self.maker_combo, 3)
        row.addWidget(self.car_combo, 5)

        # Tab and `setFocus()` land on the first step, which is where a driver
        # who has just been told the field is empty needs to start.
        self.setFocusProxy(self.category_combo)

        self.category_combo.currentIndexChanged.connect(self._on_category)
        self.maker_combo.currentIndexChanged.connect(self._on_maker)
        self.car_combo.currentIndexChanged.connect(self._on_car)

        self.set_groups(groups or [])

    def _combo(self, placeholder: str) -> QComboBox:
        combo = QComboBox()
        combo.setMinimumHeight(34)
        combo.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        combo.setMinimumContentsLength(8)
        combo.view().setTextElideMode(Qt.TextElideMode.ElideNone)
        block_wheel(combo)
        combo.setProperty("placeholder", placeholder)
        return combo

    # ------------------------------------------------------------- catalogue

    def set_groups(self, groups) -> None:  # noqa: N802 - Qt naming
        """Populate from `[(category, [(maker, [names]), ...]), ...]`.

        A two-level list - `[(category, [names])]`, what `Picker` takes - is
        accepted too and filed under one `All` maker, so a caller that has not
        been given maker data still gets a working control rather than an
        empty one.
        """
        current = self.currentText()
        self._catalog = {}
        for category, entries in groups:
            heading = category or "Other"
            makers: dict[str, list[str]] = {}
            for entry in (entries.items() if isinstance(entries, dict)
                          else entries):
                if isinstance(entry, str):
                    makers.setdefault("All", []).append(entry)
                else:
                    maker, names = entry
                    makers.setdefault(maker or "Unknown", []).extend(names)
            # Sorted here, not left to the caller. The whole point of the
            # narrowing is that a name can be found by eye, and a list in
            # whatever order a dict happened to be built in cannot be.
            self._catalog[heading] = {maker: tuple(sorted(makers[maker]))
                                      for maker in sorted(makers)}

        self._loading = True
        self._fill(self.category_combo, list(self._catalog))
        self._fill(self.maker_combo, [])
        self._fill(self.car_combo, [])
        self._loading = False

        # A selection the new catalogue does not carry has stopped existing,
        # and `Picker` documents why re-adding it here would be wrong: it
        # leaks one list's value into another's. The caller decides what to
        # put in the gap.
        if current and self._locate(current):
            self.setCurrentText(current)
        elif current:
            self._emit()

    def _fill(self, combo: QComboBox, names) -> None:
        placeholder = combo.property("placeholder") or ""
        combo.blockSignals(True)
        combo.clear()
        combo.addItem(placeholder or "-", None)
        widest = placeholder
        for name in names:
            combo.addItem(name, name)
            if len(name) > len(widest):
                widest = name
        combo.blockSignals(False)
        metrics = combo.view().fontMetrics()
        combo.view().setMinimumWidth(metrics.horizontalAdvance(widest) + 44)
        self._sync_ink(combo)

    # -------------------------------------------------------------- cascade

    def _on_category(self, _index: int = 0) -> None:
        if self._loading:
            return
        category = self.category_combo.currentData()
        makers = list(self._catalog.get(category, {})) if category else []
        self._loading = True
        self._fill(self.maker_combo, makers)
        self._fill(self.car_combo, [])
        self._loading = False
        self._sync_ink(self.category_combo)
        # Narrowing the class discards the car, so the value changed even
        # though nobody touched the car combo. Saying so is the whole reason
        # anything downstream can trust `currentText`.
        self._emit()

    def _on_maker(self, _index: int = 0) -> None:
        if self._loading:
            return
        category = self.category_combo.currentData()
        maker = self.maker_combo.currentData()
        names = (list(self._catalog.get(category, {}).get(maker, ()))
                 if category and maker else [])
        self._loading = True
        self._fill(self.car_combo, names)
        self._loading = False
        self._sync_ink(self.maker_combo)
        self._emit()

    def _on_car(self, _index: int = 0) -> None:
        self._sync_ink(self.car_combo)
        if not self._loading:
            self._emit()

    def _emit(self) -> None:
        self.changed.emit(self.currentText())

    def _sync_ink(self, combo: QComboBox) -> None:
        """Nothing chosen reads struck, not crayon - as `Picker` does."""
        palette = combo.palette()
        chosen = combo.currentData() is not None
        palette.setColor(palette.ColorRole.ButtonText,
                         QColor(theme.CRAYON if chosen else theme.STRUCK))
        palette.setColor(palette.ColorRole.Text,
                         QColor(theme.CRAYON if chosen else theme.STRUCK))
        combo.setPalette(palette)

    # ----------------------------------------------------------------- value

    def currentText(self) -> str:  # noqa: N802 - Qt naming
        return self.car_combo.currentData() or ""

    def setCurrentText(self, text: str) -> None:  # noqa: N802 - Qt naming
        """Select a car by name, driving the two steps above it to match.

        A stored name the catalogue no longer carries is still shown, for the
        reason `Picker.setCurrentText` gives: blanking it would throw away
        what the event was actually raced on at the next save. It is filed
        under the `Unknown` headings rather than smuggled into a real maker's
        list, so it is visible without being offered to anyone else.
        """
        self._unlisted = None
        if not text:
            self._loading = True
            self.category_combo.setCurrentIndex(0)
            self._fill(self.maker_combo, [])
            self._fill(self.car_combo, [])
            self._loading = False
            self._sync_ink(self.category_combo)
            self._emit()
            return

        found = self._locate(text)
        self._loading = True
        if found:
            category, maker = found
            self.category_combo.setCurrentIndex(
                self.category_combo.findData(category))
            self._fill(self.maker_combo, list(self._catalog[category]))
            self.maker_combo.setCurrentIndex(self.maker_combo.findData(maker))
            self._fill(self.car_combo, list(self._catalog[category][maker]))
        else:
            self._unlisted = text
            self._fill(self.category_combo,
                       list(self._catalog) + ["Unknown"])
            self.category_combo.setCurrentIndex(
                self.category_combo.findData("Unknown"))
            self._fill(self.maker_combo, ["Unknown"])
            self.maker_combo.setCurrentIndex(0 if self.maker_combo.count() < 2
                                             else 1)
            self._fill(self.car_combo, [text])
        self.car_combo.setCurrentIndex(self.car_combo.findData(text))
        self._loading = False
        for combo in (self.category_combo, self.maker_combo, self.car_combo):
            self._sync_ink(combo)
        self._emit()

    def _locate(self, text: str) -> tuple[str, str] | None:
        for category, makers in self._catalog.items():
            for maker, names in makers.items():
                if text in names:
                    return category, maker
        return None

    def items(self) -> list[str]:
        """Every selectable car in the catalogue, not just the visible page."""
        return sorted({name for makers in self._catalog.values()
                       for names in makers.values() for name in names})

    def setEnabledState(self, enabled: bool) -> None:  # noqa: N802 - Qt naming
        for combo in (self.category_combo, self.maker_combo, self.car_combo):
            combo.setEnabled(enabled)


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
        return QColor(theme.WEAR_FLAT)        # flat phase - losses in tenths
    if fraction <= PHASE_CLIFF_FROM:
        return QColor(theme.WEAR_LINEAR)  # progressive - balance shifts first
    return QColor(theme.WEAR_CLIFF)       # cliff - undriveable, not just slow


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

    def clear(self) -> None:
        """Back to unread. Not zero - zero is a reading, and a fresh tyre."""
        if self._fraction is not None:
            self._fraction = None
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
            text = (f"{name}: not read. Drag down to match the in-game "
                    f"gauge, or use the arrow keys. Right-click clears it "
                    f"back to unread.")
        else:
            text = (f"{name}: {self._fraction:.0%} consumed "
                    f"({wear_phase(self._fraction)} phase). "
                    f"Right-click or Delete clears it back to unread.")
        self.setToolTip(text)
        self.setAccessibleName(f"{name} tyre wear")
        self.setAccessibleDescription(text)

    # ----------------------------------------------------------------- events

    def _fraction_at(self, y: float) -> float:
        return max(0.0, min(1.0, y / max(1, self.height())))

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt naming
        # **Right-click puts it back to unread.** This gauge is 46x62 px,
        # sitting on a rack row beside two combo boxes and a button, and a
        # press used to commit a reading on the down-click with no threshold
        # and no way back: `Delete` clears it, but only once it is focused,
        # so a stray click wrote ~10% wear as a declared reading with no
        # mouse gesture that could retract it. It is the input to the wear
        # model, which is the input to stint length, which is the highest
        # consequence number this app emits. There is no undo anywhere.
        if event.button() == Qt.MouseButton.RightButton:
            self.clear()
            return
        if event.button() != Qt.MouseButton.LeftButton:
            return
        self.setFocus(Qt.FocusReason.MouseFocusReason)
        self._dragging = True
        self.setFraction(self._fraction_at(event.position().y()))

    def mouseMoveEvent(self, event) -> None:  # noqa: N802 - Qt naming
        if self._dragging:
            self.setFraction(self._fraction_at(event.position().y()))

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 - Qt naming
        # A drag down the 62 px of this widget emits `changed` on every 0.01,
        # and each one rebuilt the spec line and made four database writes -
        # 40-60 round trips for one gesture. The intermediate values are not
        # readings; only the one he let go on is.
        was_dragging = self._dragging
        self._dragging = False
        if was_dragging:
            self.changed.emit()

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
        painter.drawRect(body)

        if self._fraction:
            # Fills downward from the top, the direction of the drag, so the
            # gesture and the result point the same way.
            worn = QRectF(body.x(), body.y(),
                          body.width(), body.height() * self._fraction)
            painter.setBrush(wear_colour(self._fraction))
            painter.drawRoundedRect(worn, 4, 4)

        # CHALK when focused, matching every other control in the app.
        # It was TREAD_LIGHT at 2.04:1 against TREAD at 1.57 - a keyboard
        # state with less emphasis than the passive one, on the widget that
        # carries the wear model's only input.
        border = (QColor(theme.CRAYON) if self._limiting else
                  QColor(theme.CHALK if self.hasFocus() else theme.TREAD))
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


class WearCell(QPushButton):
    """One line that stands for the four gauges, and opens them to be set.

    **The rack is a timing tower and a timing tower has one line per lap.**
    `TyreGaugeSet` is 46x62 four times over, laid out as the car, which sets a
    140px row wherever a reading is worth taking — three laps in a 950px
    window on a screen whose whole job is comparing laps against each other.
    The gauges did not get smaller and they did not become a number: they
    moved behind this, at full size, still dragged rather than typed.

    What the line shows is **the corner that ends the stint**, which is the one
    figure the wear model actually consumes — `stint_limit` is driven by the
    worst corner, not by an average of four. So the cell is not a summary that
    loses information; it is the reading, with the other three a click away.

    Colour is the wear model's own phase band and it is **never the only
    channel**: the corner is named and the figure is written, so nothing here
    depends on telling the hues apart. Struck where nothing has been read —
    absent is not a wear of zero, which is the whole of rule 3.
    """

    changed = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._values: dict[str, float | None] = {}
        self._popup: QWidget | None = None
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFont(theme.data_font(13))
        self.setFlat(True)
        self.clicked.connect(self._open)
        self._render()

    # ------------------------------------------------------------- the value

    def values(self) -> dict[str, float | None]:
        return dict(self._values)

    def setValues(self, values: dict) -> None:   # noqa: N802 - Qt naming
        self._values = {k: v for k, v in (values or {}).items()
                        if v is not None}
        self._render()
        if self._popup is not None:
            self._popup.gauges.setValues(self._values)

    def worst(self) -> tuple[str, float] | None:
        """The corner that ends the stint, and how far gone it is."""
        if not self._values:
            return None
        corner = max(self._values, key=self._values.__getitem__)
        return corner, float(self._values[corner])

    # ------------------------------------------------------------ appearance

    def _render(self) -> None:
        worst = self.worst()
        if worst is None:
            self.setText("—")
            self.setStyleSheet(
                f"QPushButton {{ color: {theme.STRUCK}; background: transparent;"
                f" border: 1px solid {theme.TREAD}; text-align: center; }}"
                f"QPushButton:hover {{ border-color: {theme.TREAD_LIGHT}; }}")
            self.setToolTip(
                "No wear read off this stint. Click to set the four corners "
                "from GT7's own tyre indicator.\n\nGT7 broadcasts no wear "
                "channel, so this reading is the wear model's only measured "
                "input. Left unread, the stint is modelled from lap-time "
                "degradation alone.")
            self.setAccessibleName("tyre wear, nothing read")
            return

        corner, fraction = worst
        ink = wear_colour(fraction).name()
        self.setText(f"{corner.upper()} {fraction * 100:.0f}%")
        self.setStyleSheet(
            f"QPushButton {{ color: {ink}; background: transparent;"
            f" border: 1px solid {theme.TREAD}; text-align: center; }}"
            f"QPushButton:hover {{ border-color: {ink}; }}")
        others = "  ".join(
            f"{c.upper()} {v * 100:.0f}%"
            for c, v in sorted(self._values.items(),
                               key=lambda kv: -kv[1]))
        self.setToolTip(
            f"Worst corner {corner.upper()} at {fraction * 100:.0f}% "
            f"({wear_phase(fraction)} phase) — the corner that ends the "
            f"stint, and what the wear model runs on.\n\nAll four: {others}"
            f"\n\nClick to adjust.")
        self.setAccessibleName(
            f"tyre wear, worst corner {corner.upper()} "
            f"{fraction * 100:.0f} percent")

    # ---------------------------------------------------------------- popup

    def _open(self) -> None:
        """The four gauges, at full size, where the row cannot hold them.

        A popup rather than a dialog: this is an adjustment on one row of a
        rack he is working down, and a modal would put a lid on the screen
        between every lap. It closes on click-away and on Escape, and it
        writes through on every drag rather than on an OK button — there is
        nothing to confirm, and a confirmation step is where a reading gets
        lost.
        """
        if self._popup is not None:
            self._popup.close()
            return

        popup = QFrame(self.window(), Qt.WindowType.Popup)
        popup.setStyleSheet(
            f"QFrame {{ background: {theme.SHOULDER};"
            f" border: 1px solid {theme.TREAD_LIGHT}; }}")
        box = QVBoxLayout(popup)
        box.setContentsMargins(12, 10, 12, 12)
        box.setSpacing(8)
        box.addWidget(StencilLabel("WEAR AT END OF STINT", size=11,
                                   colour=theme.STENCIL_DIM, tracking=10.0))
        popup.gauges = TyreGaugeSet()
        popup.gauges.setValues(self._values)
        popup.gauges.changed.connect(self._take_from_popup)
        box.addWidget(popup.gauges)

        self._popup = popup
        popup.destroyed.connect(self._forget_popup)
        # Below the cell and right-aligned to it, so it never covers the row
        # being read, and never runs off the right edge of a rack that is
        # already the widest thing in the app.
        corner = self.mapToGlobal(self.rect().bottomRight())
        popup.adjustSize()
        popup.move(corner.x() - popup.width(), corner.y() + 4)
        popup.show()

    def _forget_popup(self) -> None:
        self._popup = None

    def _take_from_popup(self) -> None:
        popup = self._popup
        if popup is None:
            return
        self._values = {k: v for k, v in popup.gauges.values().items()
                        if v is not None}
        self._render()
        self.changed.emit()


class BigReading(QWidget):
    """One figure, allowed to be enormous, with its name under it.

    **The scale IS the design.** The race screen carried lap, position, fuel
    in hand and the box-in lap as a 15px spec run of dots — the same size as
    every other word on the screen — and "Box in 3" is the highest-consequence
    number this product emits. A driver glancing up from the wheel at three
    metres has time to read one thing, so one thing has to be readable.

    Deliberately not a stat card: no box, no border, no ground, no icon. The
    figure sits on the page in its register's ink with a small stencilled name
    beneath it, which is what a pit board is. The `refuses` list in DESIGN.md
    names the big-number-and-label card as a template to avoid; the difference
    is that a card makes a grid of equal boxes, and this makes a hierarchy —
    these figures are not peers and are not sized as peers.
    """

    def __init__(self, name: str, *, size: int = 56, ink: str = theme.STENCIL,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        column = QVBoxLayout(self)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)
        self._ink = ink
        self.value = Measured("—", size=size, bold=True, colour=theme.STRUCK)
        column.addWidget(self.value)
        self.name = StencilLabel(name, size=11, colour=theme.STENCIL_DIM,
                                 tracking=14.0)
        column.addWidget(self.name)

    def setValue(self, text: str | None, *,      # noqa: N802 - Qt naming
                 ink: str | None = None) -> None:
        """`None` renders struck, never a zero.

        A race with no plan armed has no box-in lap, and "0" would read as
        *box now* — the single most expensive misreading available on this
        screen. Absent is absent.
        """
        if text is None:
            self.value.setText("—")
            self.value.set_ink(theme.STRUCK)
            return
        self.value.setText(text)
        self.value.set_ink(ink or self._ink)


class PlanSpine(QWidget):
    """The whole race as one horizontal run: stints, stops, and where you are.

    **Not a progress bar, and the distinction is the point.** A bar says how
    far through something you are as a fraction. This says what the plan IS —
    how many stints, how long each one, on what rubber, and which one you are
    driving now — so the strategy is a single object you can check at a glance
    instead of four numbers you have to reassemble in your head.

    Drawn rather than composed from widgets because the segments have to be
    proportional to their stint lengths, and a layout with stretch factors
    rounds them into lying about the plan. Each segment carries its lap count
    stencilled inside it and its compound in the compound band's own colour,
    so colour is never the only channel here either.

    `None` for the current lap is honest: before the green nobody is on the
    spine, and the plan is still worth reading.
    """

    HEIGHT = 44

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._stints: list[tuple[int, str | None]] = []
        self._lap: int | None = None
        self.setFixedHeight(self.HEIGHT)
        self.setSizePolicy(QSizePolicy.Policy.Expanding,
                           QSizePolicy.Policy.Fixed)

    def setPlan(self, stints, compounds=None) -> None:   # noqa: N802
        codes = list(compounds or [])
        self._stints = [
            (int(laps), codes[i] if i < len(codes) else None)
            for i, laps in enumerate(stints or []) if laps]
        self.update()

    def setLap(self, lap: int | None) -> None:           # noqa: N802
        self._lap = lap
        self.update()

    def total(self) -> int:
        return sum(laps for laps, _ in self._stints)

    def paintEvent(self, event) -> None:                 # noqa: N802 - Qt naming
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        total = self.total()
        if not total:
            painter.setPen(QPen(QColor(theme.TREAD), 1))
            painter.drawLine(0, self.HEIGHT // 2, self.width(), self.HEIGHT // 2)
            return

        # The stop is a real gap in the run, not a tick on top of it: the car
        # is not on track for it, and a plan is easier to read as separated
        # stints than as one bar with marks in it.
        gap = 6
        usable = self.width() - gap * (len(self._stints) - 1)
        top, height = 4, 26
        x = 0
        driven = 0
        for laps, code in self._stints:
            width = max(2, round(usable * laps / total))
            colour = theme.band_colour(code) if code else QColor(theme.TREAD)
            here = (self._lap is not None
                    and driven < self._lap <= driven + laps)

            painter.fillRect(x, top, width, height, colour)
            # The stint being driven is the one with a lid on it. An outline
            # rather than a brighter fill, because the fill is the compound
            # and the compound must not change to say where the car is.
            if here:
                painter.setPen(QPen(QColor(theme.STENCIL), 2))
                painter.drawRect(x, top, width - 1, height - 1)

            painter.setPen(QPen(theme.band_ink_for(colour)))
            painter.setFont(theme.stencil_font(12, tracking=4.0))
            label = f"{laps}" if width < 58 else f"{laps} LAPS"
            painter.drawText(x, top, width, height,
                             Qt.AlignmentFlag.AlignCenter, label)

            if code and width >= 34:
                painter.setPen(QPen(QColor(theme.STENCIL_DIM)))
                painter.setFont(theme.stencil_font(10, tracking=10.0))
                painter.drawText(x, top + height + 2, width, 14,
                                 Qt.AlignmentFlag.AlignHCenter, code)

            driven += laps
            x += width + gap


# **The longest a desk assumption is shown on the page, in characters.**
# Strategy 15 carried eight of them at 206-432 characters - 2,262 of the
# block's 3,432 - on the page he reads on the grid. Cut at a word, whole on
# the tooltip, and never applied to a rule (see `Order.resting`).
RESTING_CAP = 160


def _cut_at_word(text: str, cap: int) -> str:
    """`text` whole if it fits, else cut at the last space inside `cap`."""
    if len(text) <= cap:
        return text
    head = text[:cap - 1]
    if " " in head:
        head = head[:head.rfind(" ")]
    return head.rstrip() + "…"


def render_standing_orders(layout, plan: dict | None,
                           author: str | None = None,
                           heading: bool = False) -> int:
    """Add the plan's standing orders to `layout`. Returns widgets added.

    **Two screens say this now** (row 1.7): the Strategy page's `LoadedCard`,
    where the plan is approved, and the Race page, where the driver is sitting
    on the grid waiting for the green. The words come from
    `strategy.handover.standing_orders` and the ink comes from here, so
    neither screen holds a copy of either - `CLAUDE.md` §1a's rule, applied to
    the one contract that says what the engineer may do without asking.

    The ink is the register and nothing else: **crayon** where a human
    declared it (the playbook, the assumptions), **`DERIVED`** where the app
    certified it, and dim for prose about a gap. `STENCIL_DIM` and not
    `STRUCK` for that last one, deliberately - struck means removed from the
    count, and "No rule from the desk on stop missed" is the most
    consequential thing on the card, not a placeholder.
    """
    from pitcrew.strategy.handover import DECLARED, DERIVED, standing_orders

    orders = standing_orders(plan or {})
    if not orders:
        return 0
    added = 0
    if heading:
        # **Named only when somebody is named.** `author_of` is None for a
        # plan with no handover, and "Standing orders - THE DESK" over a
        # block whose whole content is that no desk wrote anything asserts
        # the opposite of what it says.
        layout.addWidget(StencilLabel(
            f"Standing orders - {author.upper()}" if author
            else "Standing orders",
            size=11, colour=theme.STENCIL_DIM, tracking=14.0))
        added += 1
    ink = {DECLARED: theme.CRAYON, DERIVED: theme.DERIVED}
    for order in orders:
        if order.heading:
            layout.addWidget(StencilLabel(order.text, size=11,
                                          colour=theme.STENCIL_DIM,
                                          tracking=14.0))
            added += 1
            continue
        # **Cut here, in the one renderer both screens use**, so the card
        # and the Race page still say the same words - and the whole line is
        # on the tooltip on both, because the cut is for the glance and the
        # assumption is still the desk's word.
        shown = (_cut_at_word(order.text, RESTING_CAP) if order.resting
                 else order.text)
        label = BodyLabel(
            shown, size=13,
            colour=ink.get(order.register, theme.STENCIL_DIM), wrap=True)
        if shown != order.text:
            label.setToolTip(order.text)
        layout.addWidget(label)
        added += 1
    return added
