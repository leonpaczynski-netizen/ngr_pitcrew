"""Drivetrain data file + resolver — car_specs.json has no drivetrain for any car,
so the curated data/car_drivetrains.json fills it (directive item 1: scope).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from data.car_drivetrain import resolve_drivetrain
from data.car_drivetrain_inference import infer_drivetrain


def test_data_file_exists_and_covers_most_cars():
    specs = json.loads((ROOT / "data" / "car_specs.json").read_text(encoding="utf-8"))
    dt = json.loads((ROOT / "data" / "car_drivetrains.json").read_text(encoding="utf-8"))
    # Every mapped car must exist in specs and carry a valid code.
    valid = {"FF", "FR", "MR", "RR", "4WD"}
    assert all(dt[k] in valid for k in dt)
    assert all(k in specs for k in dt)
    # Broad coverage of the 579-car roster (the rest resolve to "" safely).
    assert len(dt) >= 500


def test_garage_cars_resolve_correctly():
    # The cars Leon actually races must be right (they drive the setup reasoning).
    cases = {
        "Ford Mustang Gr.3": "FR",
        "Porsche 911 RSR (991) '17": "MR",     # mid-engine, not RR
        "Porsche 963 '24": "MR",               # LMDh prototype, not RR
        "Ford Shelby GT350R '16": "FR",
        "Nissan GT-R NISMO GT3 '13": "4WD",
    }
    for name, want in cases.items():
        assert resolve_drivetrain(name) == want, f"{name} → {resolve_drivetrain(name)}, want {want}"


def test_representative_drivetrains():
    assert resolve_drivetrain("Honda NSX '17") == "MR"
    assert resolve_drivetrain("Chevrolet Corvette C8 '20") == "MR"
    assert resolve_drivetrain("Toyota GR Supra RZ '20") == "FR"
    assert resolve_drivetrain("Subaru WRX Gr.3") == "4WD"
    assert resolve_drivetrain("Honda Civic Type R (EK) '97") == "FF"
    assert resolve_drivetrain("Toyota Corolla Levin 1600GT APEX (AE86) '83") == "FR"


def test_unknown_car_resolves_to_empty_not_a_guess():
    assert resolve_drivetrain("Totally Made Up Car 9000") == ""
    assert resolve_drivetrain("") == ""


def test_inference_rule_ordering():
    # AE86 (name contains 'corolla') must be FR, not FF.
    assert infer_drivetrain("Toyota Corolla Levin (AE86) '83") == "FR"
    # A plain Corolla is FF.
    assert infer_drivetrain("Toyota Corolla '19", "Road Car") == "FF"
    # Porsche prototype is MR, not the Porsche RR default.
    assert infer_drivetrain("Porsche 963 '24", "Gr.1") == "MR"
    # A plain 911 is RR.
    assert infer_drivetrain("Porsche 911 GT3 '22", "Road Car") == "RR"
