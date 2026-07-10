"""Unit tests for the NGR Enterprise design-system module (ui/ngr_theme).

Covers the pure layer (colour tokens, QSS builders, logo-slot resolution)
without needing a running QApplication, plus a light offscreen check of the
Qt widget helpers. These lock in the contract that the shared theme is
importable/testable and that the official logo asset resolves read-only.
"""
from __future__ import annotations

import os

import pytest

from ui import ngr_theme as t


def test_brand_tokens_are_hex():
    for name in ("INK_BLACK", "CARBON", "CARBON_RAISED", "NGR_GREEN",
                 "TEXT_HI", "WARN", "DANGER", "SUCCESS"):
        val = getattr(t, name)
        assert isinstance(val, str) and val.startswith("#") and len(val) == 7


def test_app_stylesheet_styles_key_chrome_only():
    qss = t.app_stylesheet()
    # The premium wins: styled top nav, buttons, tables, scrollbars, tooltips.
    for token in ("QTabBar::tab", "QPushButton", "QHeaderView::section",
                  "QScrollBar", "QToolTip", "QGroupBox"):
        assert token in qss, f"global stylesheet missing {token}"
    # SAFETY: must never set a blanket QWidget rule (would cascade everywhere).
    assert "QWidget {" not in qss
    assert "QWidget{" not in qss
    # The neon NGR accent must be present in the chrome.
    assert t.NGR_GREEN in qss


def test_badge_and_banner_builders_cover_all_tones():
    for tone in t.STATUS_TONES:
        assert t.badge_qss(tone).startswith("QLabel")
        assert t.banner_qss(tone).startswith("QLabel")
    # Unknown tone falls back gracefully (never raises).
    assert t.badge_qss("nonsense").startswith("QLabel")


def test_button_builders_have_states():
    prim = t.primary_button_qss()
    assert ":hover" in prim and ":pressed" in prim and ":disabled" in prim
    assert t.NGR_GREEN in prim  # primary CTA is neon green
    sec = t.secondary_button_qss()
    assert ":disabled" in sec


def test_heading_qss_uppercase_levels():
    for lvl in (1, 2, 3):
        assert "font-weight: 700" in t.heading_qss(lvl)


def test_official_logo_asset_resolves_readonly():
    # The supplied NGR logo ships at repo root; the theme must find it and never
    # imply a fabricated mark when present.
    p = t.logo_path()
    assert p.name == "logo.png"
    assert t.logo_exists() is p.is_file()
    assert t.logo_placeholder_text()  # non-empty fallback text always available


def test_qt_helpers_offscreen():
    pytest.importorskip("PyQt6")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt6.QtWidgets import QApplication, QLabel
    _ = QApplication.instance() or QApplication([])
    assert isinstance(t.heading_label("Strategy", level=2), QLabel)
    assert isinstance(t.status_badge("MEDIUM", "warn"), QLabel)
    assert isinstance(t.advisory_banner("Advisory only."), QLabel)
    assert isinstance(t.empty_state_label("No clean laps yet."), QLabel)
    # Logo pixmap loads the real asset non-null when present.
    pix = t.logo_pixmap(height=32)
    if t.logo_exists():
        assert pix is not None and not pix.isNull()
        assert pix.height() == 32
