"""Which monitor a window opens on.

**21 Sep 2026: "I want the app to open on the wide screen not the main screen
and same with the board so it doesn't cover OBS."** The rig is a 1920x1080
primary with OBS on it and a 2560x1080 ultrawide beside it. Qt opens a window
wherever Windows puts it, which is the primary, and the driver board's
remembered spot was `0,0,2480,1050` - starting on the primary and running 560
px onto the ultrawide, so it sat on top of the stream.

The choice is a setting (`Settings.preferred_display`) rather than a rule
about primaries, because the rig's monitors have changed twice in a month -
three of them in August, two since he came out of VR. Empty means **the widest
screen**, which is the ultrawide here and needs nothing typed in.

**The pick is pure and the Qt part is a wrapper**, so the rule is testable on
the offscreen platform the suite runs on, which has exactly one 800x600 screen
and can never reproduce the defect.
"""
from __future__ import annotations

from dataclasses import dataclass

from pitcrew.diagnostics import log

# Room for the frame, which `availableGeometry` does not know about: a window
# sized to the exact work area opens with its title bar off the top on
# Windows. The same pair of margins `app.fit_to_screen` uses.
FRAME_W = 20
FRAME_H = 60


@dataclass(frozen=True)
class Display:
    """One monitor, in the logical pixels everything Qt sizes is measured in."""

    name: str
    x: int
    y: int
    width: int
    height: int
    primary: bool = False


def choose(displays, wanted: str = "") -> Display | None:
    """The display he asked for, or the widest one where he asked for none.

    A name that is not attached tonight falls back to the widest rather than
    to the primary - a monitor unplugged since the setting was written must
    not quietly put the board back over the stream, which is the whole defect
    this module exists for. It says so in the log, because a fallback nobody
    can see is a setting that appears not to work.

    Where two are equally wide the one that is **not** the primary wins: the
    primary is where OBS lives.
    """
    displays = list(displays)
    if not displays:
        return None
    if wanted:
        for display in displays:
            if display.name == wanted:
                return display
        log("ui").warning(
            "the display %r is not attached - opening on the widest instead",
            wanted)
    return max(displays, key=lambda d: (d.width, d.height, not d.primary))


def holds(display: Display, rect: tuple[int, int, int, int]) -> bool:
    """Is `(x, y, w, h)` mostly on this display?

    Mostly, not wholly: his board is deliberately dragged part-way off an
    edge so he can reach the app behind it (`DriverWindow.keep_on_screen`),
    and a rule that demanded the whole rectangle would throw that spot away
    every race.
    """
    x, y, width, height = rect
    if width <= 0 or height <= 0:
        return False
    across = min(x + width, display.x + display.width) - max(x, display.x)
    down = min(y + height, display.y + display.height) - max(y, display.y)
    if across <= 0 or down <= 0:
        return False
    return (across * down) * 2 >= width * height


# --------------------------------------------------------------- Qt wrappers


def attached(app=None) -> list[Display]:
    """Every screen Qt can see, as `Display`s. Empty when there is no app."""
    if app is None:
        from PyQt6.QtWidgets import QApplication
        app = QApplication.instance()
    if app is None:
        return []
    primary = app.primaryScreen()
    found = []
    for screen in app.screens():
        geometry = screen.geometry()
        found.append(Display(screen.name(), geometry.x(), geometry.y(),
                             geometry.width(), geometry.height(),
                             primary=screen is primary))
    return found


def screen_for(wanted: str = "", app=None):
    """The `QScreen` `choose` picks, or None where there is no app."""
    if app is None:
        from PyQt6.QtWidgets import QApplication
        app = QApplication.instance()
    if app is None:
        return None
    picked = choose(attached(app), wanted)
    if picked is None:
        return None
    for screen in app.screens():
        if screen.name() == picked.name:
            return screen
    return app.primaryScreen()


def fit(screen, width: int, height: int) -> tuple[int, int]:
    """`(w, h)` no bigger than that screen's work area."""
    if screen is None:
        return width, height
    available = screen.availableGeometry()
    return (min(width, max(320, available.width() - FRAME_W)),
            min(height, max(320, available.height() - FRAME_H)))


def centre_on(widget, screen) -> None:
    """Put the window in the middle of that screen, at the size it has.

    Clamped to the work area's own top-left, never past it: the board is
    taller than the work area on a 1080 panel, and a naive centring of
    something taller than its container puts the top edge - where the
    countdown is - above the screen.
    """
    if screen is None:
        return
    available = screen.availableGeometry()
    size = widget.frameGeometry()
    x = available.x() + max(0, (available.width() - size.width()) // 2)
    y = available.y() + max(0, (available.height() - size.height()) // 2)
    widget.move(x, y)
