"""A notice big enough to read through a headset's passthrough.

The driver is in PSVR2. To look at this screen he flips passthrough on and
reads a monitor a metre away through two cameras, in a headset, while sitting
in a rig — which is roughly the worst display conditions there are. The
practice screen is unreadable like that, and it is exactly when he most needs
to know one thing: whether the app is recording.

So this is not a notification, it is a sign. One line, as large as the screen
will carry it, maximum contrast, gone on a timer. The same discipline
CLAUDE.md 5.5 puts on a live radio call — *one thing at a time, stated as an
instruction, reason second and short* — applied to the screen instead of the
voice.

Three rules it must not break:

* **It never takes focus.** He may be driving. A window that activates itself
  can steal a keypress from the game, and a stolen keypress in a race is worse
  than any notice is good.
* **It never waits for a click.** There is no mouse in a rig. It goes away by
  itself, and clicking is only a shortcut.
* **It opens on the screen the app is on**, not the primary one. This rig has
  three monitors and the one he can see is not necessarily the one Windows
  thinks is first.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import QLabel, QVBoxLayout, QWidget

from pitcrew.diagnostics import log
from pitcrew.ui import theme

# Long enough to notice, flip passthrough on and read; short enough that it is
# never in the way of going out.
DEFAULT_SECONDS = 4.0

# Fractions of the screen height. Passthrough costs an enormous amount of
# legibility, so the headline is sized the way a pit board is - by how far away
# it has to be read from, not by what looks proportionate on a desk.
HEADLINE_FRACTION = 0.22
SUBTITLE_FRACTION = 0.055


class Banner(QWidget):
    """One line, screen-filling, gone on a timer."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(None)
        self._anchor = parent
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool)
        # Shown without activating, so a keypress meant for the game stays
        # with the game.
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)

        page = QVBoxLayout(self)
        page.setContentsMargins(0, 0, 0, 0)
        page.setSpacing(0)
        page.addStretch(1)

        self.headline = QLabel("", self)
        self.headline.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.headline.setWordWrap(True)
        page.addWidget(self.headline)

        self.subtitle = QLabel("", self)
        self.subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.subtitle.setWordWrap(True)
        page.addWidget(self.subtitle)
        page.addStretch(1)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.hide)

    # ------------------------------------------------------------------ show

    def announce(self, headline: str, subtitle: str = "", *,
                 seconds: float = DEFAULT_SECONDS,
                 warn: bool = False) -> None:
        """Put one line on the screen the app is on, and take it away again."""
        screen = self._screen()
        if screen is None:
            # `_screen` already falls back to the primary, so reaching here
            # means Qt reports no screens at all. The component whose whole
            # job is saying the app is recording had one path where it said
            # nothing and reported nothing.
            log("ui").warning(
                "no screen to put the %r notice on, so it was not shown",
                headline)
            return
        geometry = screen.geometry()

        ink = theme.WARNING if warn else theme.STENCIL
        self.setStyleSheet(f"background: {theme.RUBBER_DEEP};")
        # **Sized through the stylesheet, not `setFont`.** The app-wide sheet
        # sets a font on QLabel, and a Qt style sheet beats anything
        # `setFont` puts on the widget - which is how the first version of
        # this ended up rendering a screen-filling sign at fifteen pixels.
        self.headline.setText(headline.upper())
        self.headline.setStyleSheet(self._sheet(
            ink, geometry.height(), HEADLINE_FRACTION, weight=700))
        self.subtitle.setText(subtitle)
        self.subtitle.setStyleSheet(self._sheet(
            theme.STENCIL_DIM, geometry.height(), SUBTITLE_FRACTION,
            weight=400))
        self.subtitle.setVisible(bool(subtitle))

        self.setGeometry(geometry)
        self.show()
        self.raise_()
        # Restarted rather than stacked: a second notice replaces the first
        # and gets its own full time, instead of inheriting whatever was left.
        self._timer.start(int(seconds * 1000))

    def mousePressEvent(self, event) -> None:      # noqa: N802 - Qt naming
        """A click dismisses it. Only ever a shortcut - there is no mouse in
        the rig, which is why it also goes on its own."""
        self._timer.stop()
        self.hide()

    # ------------------------------------------------------------- internals

    def _screen(self):
        """The screen the app is on, not the one Windows calls first.

        This rig has three monitors and the one he can see through passthrough
        is not necessarily the primary.
        """
        if self._anchor is not None and self._anchor.screen() is not None:
            return self._anchor.screen()
        from PyQt6.QtWidgets import QApplication
        return QApplication.primaryScreen()

    @staticmethod
    def _sheet(ink: str, screen_height: int, fraction: float, *,
               weight: int) -> str:
        size = max(12, int(screen_height * fraction))
        return (f"color: {ink};"
                f"background: transparent;"
                f"font-family: '{theme.STENCIL_CONDENSED}';"
                f"font-size: {size}px;"
                f"font-weight: {weight};")
