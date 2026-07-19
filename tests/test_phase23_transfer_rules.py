"""Phase 23 — transfer-rules domain tests.

Car attributes derived deterministically from the GT7 name (unknown stays unknown); every rule
is a visible constant with why + authority; rule evaluation is deterministic; never raises.
"""
import inspect

import pytest

from strategy.transfer_rules import (
    car_attributes, evaluate_rules, rule_catalogue, domain_transfer_class,
    TRANSFER_RULES, DOMAIN_TRANSFER_CLASS, TRANSFER_RULES_VERSION,
)


def test_car_attributes_known_porsche():
    a = car_attributes("Porsche 911 RSR (991) '17")
    assert a["manufacturer"] == "porsche"
    assert a["drivetrain"] == "rr"
    assert a["layout"] == "rear_engine"
    assert a["category"] == "gr3"


def test_car_attributes_unknown_stays_unknown():
    a = car_attributes("Some Unlisted Prototype")
    assert a["manufacturer"] == "some"          # first token (deterministic)
    assert a["drivetrain"] == "unknown"
    assert a["layout"] == "unknown"
    assert a["category"] == "unknown"


def test_car_attributes_empty():
    a = car_attributes("")
    assert a == {"manufacturer": "unknown", "drivetrain": "unknown", "layout": "unknown",
                 "category": "unknown"}


def test_category_from_keyword():
    assert car_attributes("Toyota GR Supra Racing Concept Gr.3")["category"] == "gr3"
    assert car_attributes("Toyota GR Supra RC Gr.4")["category"] == "gr4"


def test_evaluate_rules_same_car():
    src = car_attributes("Porsche 911 RSR (991) '17")
    ctx = {"gt7_version": "1.49", "driver": "leon"}
    res = evaluate_rules(src, src, ctx, ctx)
    assert res["same_manufacturer"] and res["same_drivetrain"] and res["same_layout"]
    assert res["same_race_category"] and res["compatible_gt7_version"] and res["same_driver"]


def test_evaluate_rules_different_manufacturer():
    src = car_attributes("Porsche 911 RSR (991) '17")
    tgt = car_attributes("Toyota GR Supra Racing Concept Gr.3")
    ctx = {"gt7_version": "1.49", "driver": "leon"}
    res = evaluate_rules(src, tgt, ctx, ctx)
    assert not res["same_manufacturer"]
    assert res["same_race_category"]           # both gr3
    assert res["compatible_gt7_version"]


def test_incompatible_version():
    a = car_attributes("Porsche 911 RSR (991) '17")
    res = evaluate_rules(a, a, {"gt7_version": "1.49"}, {"gt7_version": "2.0"})
    assert not res["compatible_gt7_version"]


def test_rule_catalogue_visible():
    cat = rule_catalogue()
    assert len(cat) == len(TRANSFER_RULES)
    for r in cat:
        assert r["id"] and r["why"] and r["authority"]


def test_domain_transfer_classes():
    assert domain_transfer_class("gearbox") == "car_track_specific"
    assert domain_transfer_class("track_segments") == "context_bound"
    assert domain_transfer_class("driver_technique") == "driver_specific"
    assert domain_transfer_class("springs") == "architecture_dependent"
    assert domain_transfer_class("vehicle_balance") == "handling_drivetrain"
    # unknown domain defaults conservatively to architecture_dependent
    assert domain_transfer_class("zzz") == "architecture_dependent"


def test_evaluate_rules_never_raises():
    for junk in (None, {}, {"manufacturer": None}):
        res = evaluate_rules(junk, junk, junk, junk)
        assert isinstance(res, dict) and len(res) == len(TRANSFER_RULES)


def test_deterministic():
    a = car_attributes("Porsche 911 RSR (991) '17")
    assert car_attributes("Porsche 911 RSR (991) '17") == a
    ctx = {"gt7_version": "1.49", "driver": "leon"}
    assert evaluate_rules(a, a, ctx, ctx) == evaluate_rules(a, a, ctx, ctx)


def test_no_forbidden_imports():
    src = inspect.getsource(__import__("strategy.transfer_rules", fromlist=["x"]))
    for banned in ("import sqlite3", "PyQt6", "import random", "random.", "datetime.now",
                   "date.today", "time.time", "from data.session_db", "sklearn", "numpy",
                   "networkx", "def optimi", "argmax"):
        assert banned not in src
    assert TRANSFER_RULES_VERSION == "transfer_rules_v1"
