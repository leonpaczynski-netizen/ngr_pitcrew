"""UAT remediation — DEF-073-001/-007: compact read-only "Transcribe to GT7" view.

The editable Setup Builder is tall (spinboxes, ranges, help text). This adds a dense, read-only
summary in GT7 tuning-menu order so the whole setup is visible at a glance for copying into the
game. ``build_transcribe_sections`` is pure and unit-tested for ordering + conditional rows.
"""
from __future__ import annotations

import os

import pytest

from ui.setup_transcribe_view import build_transcribe_sections


@pytest.fixture(scope="module")
def qapp():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    try:
        from PyQt6.QtWidgets import QApplication
    except Exception:
        pytest.skip("PyQt6 not available")
    return QApplication.instance() or QApplication([])


def _base_setup(**over):
    d = {
        "car": "Porsche Cayman GT4", "track": "Watkins Glen", "setup_label": "R Baseline 1",
        "tyre_front": "Racing Medium", "tyre_rear": "Racing Medium",
        "ride_height_front": 65, "ride_height_rear": 70,
        "arb_front": 5, "arb_rear": 6,
        "dampers_front_comp": 30, "dampers_rear_comp": 28,
        "dampers_front_ext": 40, "dampers_rear_ext": 38,
        "springs_front": 4.20, "springs_rear": 3.90,
        "camber_front": 2.5, "camber_rear": 1.8,
        "toe_front": 0.00, "toe_rear": 0.15,
        "lsd_initial": 10, "lsd_accel": 20, "lsd_decel": 8,
        "torque_distribution_rear": 60, "brake_bias_front": 3,
        "aero_front": 300, "aero_rear": 520,
        "final_drive": 3.700, "transmission_max_speed_kmh": 250,
        "gear_ratios": [3.2, 2.4, 1.9, 1.5, 1.2, 1.0],
        "ballast_kg": 0, "ballast_position": 0, "power_restrictor": 100,
        "ecu_ingame": "Stock", "ecu_ingame_output": 100,
        "transmission_type": "Fully Customisable",
        "nitrous_type": "None", "nitrous_output": 0,
        "drivetrain": "RWD",
    }
    d.update(over)
    return d


def test_sections_follow_gt7_menu_order():
    secs = build_transcribe_sections(_base_setup())
    titles = [s["title"] for s in secs]
    # tyres → suspension → differential → aero → transmission come in GT7 order
    assert titles.index("Tyres") < titles.index("Suspension")
    assert titles.index("Suspension") < titles.index("Differential & Brakes")
    assert titles.index("Differential & Brakes") < titles.index("Aerodynamics")
    assert titles.index("Aerodynamics") < titles.index("Transmission")


def test_front_rear_values_are_mapped():
    secs = {s["title"]: s for s in build_transcribe_sections(_base_setup())}
    susp = {r[0]: (r[1], r[2]) for r in secs["Suspension"]["rows"]}
    assert susp["Body Height (mm)"] == ("65", "70")
    assert susp["Natural Frequency (Hz)"] == ("4.20", "3.90")   # 2 dp, tabular
    aero = {r[0]: (r[1], r[2]) for r in secs["Aerodynamics"]["rows"]}
    assert aero["Downforce"] == ("300", "520")


def test_brake_bias_is_read_from_brake_bias_front_key():
    secs = {s["title"]: s for s in build_transcribe_sections(_base_setup())}
    diff = {r[0]: r[1] for r in secs["Differential & Brakes"]["rows"]}
    assert diff["Brake Balance"] == "3"


def test_gears_are_listed_in_order():
    secs = {s["title"]: s for s in build_transcribe_sections(_base_setup())}
    trans_labels = [r[0] for r in secs["Transmission"]["rows"]]
    assert trans_labels[:2] == ["Final Drive", "Top Speed (km/h)"]
    assert "Gear 1" in trans_labels and "Gear 6" in trans_labels


def test_awd_adds_front_lsd_rows_only_when_awd():
    rwd = {s["title"]: s for s in build_transcribe_sections(_base_setup(drivetrain="RWD"))}
    rwd_labels = [r[0] for r in rwd["Differential & Brakes"]["rows"]]
    assert "LSD Front Initial" not in rwd_labels
    awd = {s["title"]: s for s in build_transcribe_sections(_base_setup(drivetrain="AWD"))}
    awd_labels = [r[0] for r in awd["Differential & Brakes"]["rows"]]
    assert "LSD Front Initial" in awd_labels


def test_optional_sections_dropped_when_not_fitted():
    titles = [s["title"] for s in build_transcribe_sections(_base_setup())]
    # nitrous None, ECU Stock/100, ballast 0, power 100 → those sections are omitted
    assert "Nitrous" not in titles
    assert "Performance Adjustment" not in titles
    assert "Engine / ECU" not in titles
    # but present when actually set
    titles2 = [s["title"] for s in build_transcribe_sections(
        _base_setup(nitrous_type="NOS", nitrous_output=50, ballast_kg=20, power_restrictor=95))]
    assert "Nitrous" in titles2
    assert "Performance Adjustment" in titles2


def test_view_renders_without_error(qapp):
    from ui.setup_transcribe_view import SetupTranscribeView, SetupTranscribeDialog
    v = SetupTranscribeView()
    v.set_setup(_base_setup())            # must not raise
    v.set_setup(_base_setup(drivetrain="AWD", nitrous_type="NOS"))  # re-render clears old body
    dlg = SetupTranscribeDialog()
    dlg.set_setup(_base_setup())
