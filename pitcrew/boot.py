"""The first 50 ms of a real launch, run before the app's own imports.

`python -m pitcrew.app` - what the desktop shortcut runs - calls `early()`
from the top of `pitcrew/app.py`, before that module imports the controller,
the screens and numpy: about 270 ms of Python that touches no font. That
time is used to have a Qt worker load the font fallback (`font_warm`), which
otherwise cost 170-400 ms on the Qt thread the first time any screen showed
a glyph Bahnschrift lacks - measured 19 Sep 2026, it was the freeze straight
after the window appeared. Loaded here, it is done, or nearly, before the
first screen is built, and nothing is on the screen to wait for it.

`main()` then finds the QApplication already made. Anything here that fails
is logged and left to `main()` to do the old way: this module may make the
launch faster, never make it fail. Nothing but the real launch calls it -
tests and tools build their own QApplication, exactly as before.
"""
from __future__ import annotations

import sys

# Windows groups taskbar buttons by this id - see `app.APP_ID`, which is
# this. Here so that it can be claimed before `app` has finished importing.
APP_ID = "NextGearRacing.PitCrew"

# Set by `early()`: the QApplication it made AND themed, or None.
APP = None


def early() -> None:
    global APP
    from pitcrew import diagnostics

    # First, as in `main`: under pythonw a failure with no log leaves
    # nothing behind at all. `install` is safe to call again from `main`.
    diagnostics.install()
    diagnostics.install_qt_handler()
    import os

    # `main` writes the full banner once the app has imported; this is the
    # line that ties the early marks to this process.
    diagnostics.log().info("Pit Crew launching - pid: %d", os.getpid())
    try:
        from PyQt6.QtWidgets import QApplication

        from pitcrew.ui import font_warm, theme

        claim_taskbar_identity()
        app = QApplication(sys.argv)
        diagnostics.mark("QApplication (early)")
        theme.apply(app)
        # Only now: `main` skips the theme for the app this module made, so
        # an app it made but could not theme is left for `main` to finish.
        APP = app
        font_warm.start(fallback_text(), theme.text_font(theme.BODY_PX),
                        "warm-font-fallback")
        diagnostics.mark("font warm-up started")
    except Exception:                                # noqa: BLE001
        diagnostics.log().error("early launch step failed - continuing "
                                "without it", exc_info=True)


def claim_taskbar_identity() -> None:
    """Before any window exists - see `app.APP_ID`."""
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)
    except Exception:                                # noqa: BLE001
        pass                                         # not Windows, or too old


def fallback_text() -> str:
    """Every glyph the app is known to show that Bahnschrift lacks, or may:
    the minus sign of a practice delta and of the Reference tables, and
    whatever the car and circuit catalogues carry outside ASCII - the
    katakana dot in "Nissan R34 GT-R V･spec II" among them.

    Only the first such glyph is expensive (it makes Qt work out the
    machine's fallback faces); each after it costs about a millisecond.
    """
    from pitcrew.store import catalogs

    rare = {"−"}
    for names in catalogs.cars_by_category().values():
        for name in names:
            rare.update(ch for ch in name if ord(ch) > 0x7F)
    for name in catalogs.track_bases():
        rare.update(ch for ch in name if ord(ch) > 0x7F)
    return "Pit Crew " + "".join(sorted(rare))
