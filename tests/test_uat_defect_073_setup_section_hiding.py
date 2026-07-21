"""UAT remediation — DEF-073 (setup proportions): progressive-disclosure section hiding.

The Setup Builder used to render every tuning section even when the active Event locked most
of them out, forcing the operator to scroll past disabled controls. ``apply_section_visibility``
now hides the sections whose tuning categories are ALL locked, on both the Race and Qualifying
forms, while unrestricted and fully-locked contexts keep every section visible.
"""
from __future__ import annotations

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


def _form(qapp):
    from ui.setup_form_widget import SetupFormWidget
    return SetupFormWidget("Race", None)


def test_section_boxes_exposed_with_categories(qapp):
    f = _form(qapp)
    assert hasattr(f, "section_boxes")
    # every section maps to a non-empty set of tuning categories
    for key, (box, cats) in f.section_boxes.items():
        assert box is not None, key
        assert isinstance(cats, set) and cats, key
    # the categories referenced must be a subset of the real permission categories
    known = {"tyres", "brake_balance", "suspension", "differential", "aero",
             "transmission", "power", "ballast", "steering", "nitrous"}
    for _key, (_box, cats) in f.section_boxes.items():
        assert cats <= known, (_key, cats)


def test_unrestricted_shows_every_section(qapp):
    f = _form(qapp)
    f.apply_section_visibility(allowed_cats=[], restricted=False)
    for _key, (box, _cats) in f.section_boxes.items():
        assert box.isVisibleTo(f) is True, _key


def test_restricted_hides_fully_locked_sections(qapp):
    f = _form(qapp)
    # Event allows only suspension + aero + differential (a typical BoP-style lock)
    allowed = ["suspension", "aero", "differential", "brake_balance", "tyres"]
    f.apply_section_visibility(allowed_cats=allowed, restricted=True)
    vis = {k: box.isVisibleTo(f) for k, (box, _c) in f.section_boxes.items()}
    # permitted sections stay visible
    assert vis["suspension"] is True
    assert vis["aero"] is True
    assert vis["differential"] is True
    assert vis["tyres"] is True
    # fully-locked sections are hidden
    assert vis["nitrous"] is False          # {nitrous} not allowed
    assert vis["ecu"] is False              # {power} not allowed
    assert vis["performance"] is False      # {ballast, power} not allowed
    assert vis["transmission_type"] is False
    assert vis["transmission_gears"] is False


def test_partial_category_overlap_keeps_section(qapp):
    f = _form(qapp)
    # performance = {ballast, power}: allowing just ballast must keep it visible
    f.apply_section_visibility(allowed_cats=["ballast"], restricted=True)
    assert f.section_boxes["performance"][0].isVisibleTo(f) is True
    # ecu = {power}: power still locked → hidden
    assert f.section_boxes["ecu"][0].isVisibleTo(f) is False
