"""Phase 1 chunk 9: the GT7 car-data capture screen — A7.

The engineering brain has no real data for any car in the game. Until the driver types
in what GT7 actually shows, every setup rests on a class archetype — a real engineering
position, but not one derived for the car in front of them.

The panel is built so a PARTIAL capture is useful: every field is independent, anything
left blank keeps the class default and says so. It never asks for completeness and
never blocks on it, because four real numbers for the car you race beat none for 579.
"""
from __future__ import annotations

import json
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from data.car_parameter_model import (
    invalidate_cache, resolve_parameter_model, save_car_capture,
)

GR3_CAR = "AMG Mercedes-AMG GT3 '20"


@pytest.fixture(scope="module")
def qapp():
    from PyQt6.QtWidgets import QApplication
    yield QApplication.instance() or QApplication([])


@pytest.fixture
def capture_store(tmp_path, monkeypatch):
    import data.car_parameter_model as cpm
    path = tmp_path / "car_gt7_ranges.json"
    path.write_text(json.dumps({"schema": 1, "cars": {}}), encoding="utf-8")
    monkeypatch.setattr(cpm, "_CAPTURE_PATH", path)
    invalidate_cache()
    yield path
    invalidate_cache()


@pytest.fixture
def panel(qapp, capture_store):
    from ui.components.car_data_capture import CarDataCapturePanel
    p = CarDataCapturePanel()
    p.set_car(GR3_CAR)
    return p


# ---------------------------------------------------------------------------
# It tells the driver what they are actually running on
# ---------------------------------------------------------------------------
def test_an_uncaptured_car_says_it_is_on_class_defaults(panel):
    status = panel._status.text().lower()
    assert "class default" in status
    assert "gr3" in status


def test_each_row_shows_the_effective_value_and_where_it_came_from(panel):
    text = panel._rows["springs_front"][4].text()
    assert "class default" in text
    assert "generic fallback" in text or "curated" in text


def test_a_capture_flips_the_status_message(panel, capture_store):
    save_car_capture(GR3_CAR, {"stock": {"springs_front": 4.2}})
    panel.set_car(GR3_CAR)
    assert "captured for this car" in panel._status.text()


# ---------------------------------------------------------------------------
# A partial capture is useful — the central design constraint
# ---------------------------------------------------------------------------
def test_a_blank_form_saves_nothing_rather_than_zeroes(panel):
    """Blank must mean "not captured", never 0 — a captured ride height of 0mm would
    be far worse than no capture at all."""
    assert panel.collect() == {}


def test_one_field_is_enough(panel):
    panel._rows["springs_front"][3].setValue(4.2)      # stock only
    entry = panel.collect()
    assert entry == {"stock": {"springs_front": 4.2}}


def test_a_half_range_is_not_recorded_as_a_range(panel):
    """A min with no max is not a range. Recording half of one would clamp against a
    bound nobody supplied."""
    panel._rows["ride_height_front"][0].setValue(50)   # min only
    assert "ranges" not in panel.collect()
    panel._rows["ride_height_front"][1].setValue(90)   # now both
    assert panel.collect()["ranges"]["ride_height_front"] == {"min": 50, "max": 90}


def test_an_inverted_range_is_rejected(panel):
    panel._rows["ride_height_front"][0].setValue(90)
    panel._rows["ride_height_front"][1].setValue(50)
    assert "ranges" not in panel.collect()


def test_a_step_alone_is_still_recorded(panel):
    """A step is independently useful even with no bounds — it stops the app authoring
    a value the slider cannot land on."""
    panel._rows["ride_height_front"][2].setValue(5)
    assert panel.collect()["ranges"]["ride_height_front"] == {"step": 5}


def test_a_zero_step_is_ignored(panel):
    panel._rows["ride_height_front"][2].setValue(0)
    assert "ranges" not in panel.collect()


def test_gear_count_and_redline_are_captured(panel):
    panel._num_gears.setValue(6)
    panel._redline.setValue(8500)
    entry = panel.collect()
    assert entry["num_gears"] == 6
    assert entry["redline_rpm"] == 8500


def test_a_zero_gear_count_is_not_a_capture(panel):
    panel._num_gears.setValue(0)
    assert "num_gears" not in panel.collect()


def test_gear_ratios_are_captured_as_stock_values(panel):
    panel._gears["gear_1"].setValue(2.98)
    assert panel.collect()["stock"]["gear_1"] == 2.98


# ---------------------------------------------------------------------------
# Saving, and what it unlocks
# ---------------------------------------------------------------------------
def test_saving_writes_through_to_the_parameter_model(panel, capture_store):
    panel._rows["ride_height_front"][0].setValue(48)
    panel._rows["ride_height_front"][1].setValue(88)
    panel._rows["ride_height_front"][2].setValue(2)
    panel._on_save()
    spec = resolve_parameter_model(GR3_CAR).spec("ride_height_front")
    assert (spec.legal_low, spec.legal_high, spec.step) == (48, 88, 2)
    assert spec.legal_tier == "captured"


def test_saving_emits_so_the_shell_can_react(panel, capture_store):
    seen: list = []
    panel.capture_saved.connect(seen.append)
    panel._rows["springs_front"][3].setValue(4.2)
    panel._on_save()
    assert seen == [GR3_CAR]


def test_saving_nothing_is_not_an_error(panel):
    seen: list = []
    panel.capture_saved.connect(seen.append)
    panel._on_save()
    assert seen == []
    assert "class defaults" in panel._result.text()


def test_a_second_save_merges_rather_than_replacing(panel, capture_store):
    panel._rows["springs_front"][3].setValue(4.2)
    panel._on_save()
    panel.set_car(GR3_CAR)
    panel._rows["camber_front"][3].setValue(3.0)
    panel._on_save()
    model = resolve_parameter_model(GR3_CAR)
    assert model.spec("springs_front").anchor == 4.2
    assert model.spec("camber_front").anchor == 3.0


def test_a_capture_unlocks_the_gearbox(panel, capture_store):
    """The concrete payoff: capture the gearbox facts and the app stops saying
    'keep the stock gearing'."""
    from types import SimpleNamespace

    from strategy.setup_gearbox import derive_gearbox
    track = SimpleNamespace(measured=True, longest_straight_m=1100.0)
    assert derive_gearbox(car_model=resolve_parameter_model(GR3_CAR),
                          track_profile=track).authored is False

    panel._num_gears.setValue(6)
    panel._redline.setValue(8500)
    for i, ratio in enumerate([2.90, 2.10, 1.64, 1.31, 1.07, 0.89], start=1):
        panel._gears[f"gear_{i}"].setValue(ratio)
    panel._on_save()

    plan = derive_gearbox(car_model=resolve_parameter_model(GR3_CAR),
                          track_profile=track)
    assert plan.authored is True
    assert plan.gear_count == 6


def test_no_car_disables_saving(qapp, capture_store):
    from ui.components.car_data_capture import CarDataCapturePanel
    p = CarDataCapturePanel()
    p.set_car("")
    assert p._save.isEnabled() is False
    assert "No car selected" in p._status.text()


# ---------------------------------------------------------------------------
# It replaces the wrong-semantics editor rather than sitting beside it
# ---------------------------------------------------------------------------
def test_the_garage_button_opens_the_capture_page_not_the_classic_dialog(qapp):
    """The classic CarRangesDialog writes tuning PREFERENCE windows into a file the
    rest of the app reads as GT7 slider limits — right idea, wrong semantics."""
    from ui.components.setup_workspace import SetupWorkspace
    w = SetupWorkspace()
    assert "GT7 data" in w._ranges_btn.text()
    w.show_car_data_capture(GR3_CAR)
    assert w._stack.currentWidget() is w.car_data_capture


def test_closing_the_capture_page_returns_to_the_previous_view(qapp):
    from ui.components.setup_workspace import SetupWorkspace
    w = SetupWorkspace()
    before = w._stack.currentIndex()
    w.show_car_data_capture(GR3_CAR)
    w._ranges_btn.setChecked(False)
    assert w._stack.currentIndex() == before


def test_the_workspace_re_emits_a_capture(qapp, capture_store):
    from ui.components.setup_workspace import SetupWorkspace
    w = SetupWorkspace()
    seen: list = []
    w.car_data_captured.connect(seen.append)
    w.car_data_capture.set_car(GR3_CAR)
    w.car_data_capture._rows["springs_front"][3].setValue(4.2)
    w.car_data_capture._on_save()
    assert seen == [GR3_CAR]
