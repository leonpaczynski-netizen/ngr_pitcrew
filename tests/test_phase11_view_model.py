"""Engineering Brain Phase 11 — Qt-free post-flight view-model tests."""
import pytest

from ui import postflight_review_vm as vm

RESULT = {"ok": True, "record": {
    "predicted_risk": "moderate", "outcome_status": "regression",
    "accuracy": {"overall_accuracy": 0.5, "primary_consequence_accuracy": 0.0,
                 "side_effect_accuracy": 1.0, "risk_accuracy": 1.0,
                 "constraint_accuracy": 0.0, "historical_transfer_usefulness": 0.0,
                 "checklist_usefulness": 0.75, "confirmed_count": 1,
                 "contradicted_count": 2},
    "consequence_reconciliations": [
        {"predicted": "increases exit traction", "status": "contradicted",
         "observed": "regressed", "reason": "worsened"},
        {"predicted": "may reduce oversteer resistance", "status": "confirmed",
         "observed": "oversteer appeared", "reason": "regression observed"}],
    "checklist_validations": [
        {"label": "Coupled interaction exists", "expectation": "coupled interaction may show",
         "outcome": "materialised", "useful": True, "reason": "coupled effect observed",
         "status": "caution"}],
}}
CALIBRATION = {"ok": True, "calibration": {
    "reconciliations": 3, "overall_accuracy": 0.7, "primary_consequence_accuracy": 0.6,
    "side_effect_accuracy": 0.9, "risk_accuracy": 0.8, "constraint_accuracy": 0.7,
    "historical_transfer_usefulness": 0.5, "checklist_usefulness": 0.8,
    "confirmed_total": 8, "contradicted_total": 3, "elevated_risk_regressions": 1}}


def test_not_empty_and_summary():
    assert not vm.is_empty(RESULT)
    assert "accuracy" in vm.summary_line(RESULT)


def test_prediction_vs_outcome():
    rows = dict(vm.prediction_vs_outcome_rows(RESULT))
    assert rows["Predicted risk"] == "moderate"
    assert rows["Actual outcome"] == "regression"


def test_confirmed_and_unexpected_split():
    conf = vm.confirmed_rows(RESULT)
    unexp = vm.unexpected_rows(RESULT)
    assert any("oversteer" in r[0] for r in conf)
    assert any("exit traction" in r[0] for r in unexp)


def test_checklist_rows():
    rows = vm.checklist_rows(RESULT)
    assert rows and all(len(r) == len(vm.CHECKLIST_COLUMNS) for r in rows)


def test_accuracy_rows():
    rows = dict(vm.accuracy_rows(RESULT))
    assert "Overall" in rows and rows["Overall"] == "50%"


def test_lessons_rows():
    lessons = vm.lessons_rows(RESULT)
    assert any("did not hold" in l for l in lessons)
    assert any("materialised" in l for l in lessons)


def test_calibration_rows():
    rows = dict(vm.calibration_rows(CALIBRATION))
    assert rows["Reconciliations"] == "3"
    assert rows["Overall accuracy"] == "70%"


def test_is_empty_on_bad_result():
    assert vm.is_empty(None)
    assert vm.is_empty({"ok": False})
    assert vm.calibration_is_empty({"ok": True, "calibration": {"reconciliations": 0}})
