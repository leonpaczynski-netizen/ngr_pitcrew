"""UAT remediation — DEF-073-008: a from-scratch baseline populates the Car Setup form.

A baseline build authors a COMPLETE setup, but the form used to keep its defaults (fields were
only highlighted), so e.g. ride height showed the 80 mm default instead of the authored value and
"most fields didn't load". Two fixes:

  1. ``_display_setup_result`` fills the target form from the baseline ``setup_fields`` when the
     result is a baseline build (the Analyse path stays Apply-gated).
  2. ``SetupFormWidget.apply_ai_fields`` translates the recommendation's ``brake_bias`` key to the
     ``brake_bias_front`` key that ``fill_setup_fields`` reads, so brake bias is no longer dropped.
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


def _form(qapp):
    from ui.setup_form_widget import SetupFormWidget
    return SetupFormWidget("Race", None)


def test_apply_ai_fields_writes_values_into_the_form(qapp):
    f = _form(qapp)
    # sanity: defaults differ from what we apply, so a pass proves the fill happened
    assert f._setup_rh_f.value() == 80
    f.apply_ai_fields({
        "ride_height_front": 65.0,
        "ride_height_rear": 70.0,
        "springs_front": 4.20,
        "camber_front": 2.5,
        "arb_front": 6.0,
    })
    assert f._setup_rh_f.value() == 65
    assert f._setup_rh_r.value() == 70
    assert abs(f._setup_spr_f.value() - 4.20) < 1e-6
    assert abs(f._setup_cam_f.value() - 2.5) < 1e-6
    assert f._setup_arb_f.value() == 6


def test_brake_bias_key_is_translated(qapp):
    # recommendation uses "brake_bias"; fill_setup_fields reads "brake_bias_front".
    f = _form(qapp)
    assert f._setup_bb.value() == 0
    f.apply_ai_fields({"brake_bias": 3.0})
    assert f._setup_bb.value() == 3


def test_explicit_brake_bias_front_still_wins(qapp):
    f = _form(qapp)
    # if the caller already supplies the form key, do not clobber it with the translation
    f.apply_ai_fields({"brake_bias_front": -2.0})
    assert f._setup_bb.value() == -2


def test_baseline_result_fills_the_form_source_wiring():
    from ui.setup_builder_ui import SetupBuilderMixin
    src = inspect.getsource(SetupBuilderMixin._display_setup_result)
    assert 'entry_type == "baseline_setup"' in src   # baseline-only fill
    assert "apply_ai_fields" in src                  # fills via the shared apply path
