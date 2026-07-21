"""UAT remediation — DEF-073-017: Live Race Engineer tab layout + mode differentiation.

Two problems: (1) the Live tab stacked many cards in a plain vertical layout with no scroll area,
so the mode-specific panel and bottom content were clipped/"squished" on limited-height / VR
windows; (2) Race / Practice / Qualifying shared the same chrome, so the tab felt identical in
every mode. Fixes: wrap the tab content in a QScrollArea, and add a prominent colour-coded mode
banner that names the active mode and what it is for.
"""
from __future__ import annotations

import inspect
import os

import pytest


@pytest.fixture(scope="module")
def qapp():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    try:
        from PyQt6.QtWidgets import QApplication
    except Exception:
        pytest.skip("PyQt6 not available")
    return QApplication.instance() or QApplication([])


def test_mode_info_is_distinct_per_mode(qapp):
    from ui.live_ui import _LIVE_MODE_INFO
    titles = {_LIVE_MODE_INFO[m][0] for m in ("Race", "Practice", "Qualifying")}
    colours = {_LIVE_MODE_INFO[m][2] for m in ("Race", "Practice", "Qualifying")}
    assert len(titles) == 3       # each mode has a distinct heading
    assert len(colours) == 3      # and a distinct accent colour


def test_mode_banner_updates_distinctly(qapp):
    from PyQt6.QtWidgets import QLabel
    from ui.live_ui import LiveMixin

    class _Stub:
        pass

    s = _Stub()
    s._live_mode_banner = QLabel()
    LiveMixin._update_live_mode_banner(s, "Race")
    race_txt = s._live_mode_banner.text()
    LiveMixin._update_live_mode_banner(s, "Qualifying")
    qual_txt = s._live_mode_banner.text()
    assert "RACE MODE" in race_txt
    assert "QUALIFYING MODE" in qual_txt
    assert race_txt != qual_txt     # the tab no longer looks the same in every mode


def test_mode_banner_never_raises_without_widget(qapp):
    from ui.live_ui import LiveMixin

    class _Stub:
        pass

    LiveMixin._update_live_mode_banner(_Stub(), "Race")   # no banner attr → no-op, no raise


def test_live_tab_is_wrapped_in_a_scroll_area():
    src = inspect.getsource(__import__("ui.live_ui", fromlist=["LiveMixin"]).LiveMixin._build_live_tab)
    assert "QScrollArea" in src
    assert "setWidgetResizable(True)" in src
    assert "return scroll" in src           # the scroll area is what the tab returns
    # the mode-specific panel gets a stretch factor so it isn't squished
    assert "_live_mode_stack, 1" in src
