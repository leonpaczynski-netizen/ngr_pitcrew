"""Independence tests for SetupFormWidget (post-UAT side-by-side refactor).

The Setup Builder now shows a Race panel and a Qualifying panel side by side,
each a SetupFormWidget instance. They must be fully independent: separate
serialized state, and applying an AI result (or a fill) to one must never
mutate the other. These tests build real (offscreen) widgets — the widget's
host calls are all hasattr-guarded, so an empty stub host exercises the
widget's own logic without constructing the whole MainWindow.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

# Must be set before any QApplication is created so the tests run headless.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

pytest.importorskip("PyQt6.QtWidgets")
from PyQt6.QtWidgets import QApplication  # noqa: E402
from ui.setup_form_widget import SetupFormWidget  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


class _StubHost:
    """Minimal host — every SetupFormWidget host call is hasattr-guarded."""


@pytest.fixture
def forms(qapp):
    host = _StubHost()
    return SetupFormWidget("Race", host), SetupFormWidget("Qualifying", host)


def test_purpose_sets_setup_type(forms):
    race, qual = forms
    assert race.current_setup_dict()["setup_type"] == "Race Setup"
    assert qual.current_setup_dict()["setup_type"] == "Qualifying Setup"


def test_purpose_prefix(forms):
    race, qual = forms
    assert race.purpose_prefix() == "R"
    assert qual.purpose_prefix() == "Q"


def test_independent_serialization(forms):
    race, qual = forms
    race._setup_spr_f.setValue(6.5)
    qual._setup_spr_f.setValue(3.2)
    assert race.current_setup_dict()["springs_front"] == 6.5
    assert qual.current_setup_dict()["springs_front"] == 3.2


def test_fill_one_does_not_touch_the_other(forms):
    race, qual = forms
    qual._setup_spr_f.setValue(3.5)
    race.fill_setup_fields({"name": "", "springs_front": 5.0})
    assert race.current_setup_dict()["springs_front"] == 5.0
    # Filling the Race panel must not disturb the Qualifying panel.
    assert qual.current_setup_dict()["springs_front"] == 3.5


def test_apply_ai_fields_is_isolated(forms):
    race, qual = forms
    qual_before = qual.current_setup_dict()["lsd_accel"]
    race.apply_ai_fields({"lsd_accel": 22})
    assert race.current_setup_dict()["lsd_accel"] == 22
    # The other panel must be untouched by an AI apply on this one.
    assert qual.current_setup_dict()["lsd_accel"] == qual_before


def test_label_is_per_form(forms):
    race, qual = forms
    race._setup_label.setText("R Fuji 1")
    qual._setup_label.setText("Q Fuji 1")
    assert race.current_setup_dict()["setup_label"] == "R Fuji 1"
    assert qual.current_setup_dict()["setup_label"] == "Q Fuji 1"


def test_widgets_are_distinct_objects(forms):
    race, qual = forms
    # Same field name, different underlying widget instances per panel.
    assert race._setup_spr_f is not qual._setup_spr_f
    assert race._setup_label is not qual._setup_label
