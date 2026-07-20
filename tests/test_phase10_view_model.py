"""Engineering Brain Phase 10 — Qt-free pre-flight review view-model tests."""
import pytest

from ui import preflight_review_vm as vm

RESULT = {
    "ok": True,
    "review": {
        "risk_level": "moderate", "summary": "Pre-flight for lsd_accel increase",
        "experiment": {"field": "lsd_accel", "direction": "increase",
                       "current_value": 22.0, "proposed_value": 25.0,
                       "target_issue": "exit_wheelspin", "evidence_grade": "medium",
                       "window_relationship": "inside_window",
                       "hypothesis": "reduce wheelspin",
                       "expected_positive_effect": "increases exit traction",
                       "selection_rationale": "single-field minimum-effective"},
        "consequences": [{"kind": "primary_effect", "text": "increases exit traction",
                          "evidence_source": "graph", "confidence": "medium"},
                         {"kind": "interaction", "text": "interacts with arb_rear",
                          "evidence_source": "graph", "confidence": ""}],
        "checklist": [{"status": "ok", "glyph": "✓", "label": "Inside learned window",
                       "why": "within window", "supporting_sessions": [], "confidence": "window"},
                      {"status": "caution", "glyph": "⚠", "label": "Coupled interaction exists",
                       "why": "interacts with arb_rear", "supporting_sessions": [], "confidence": ""}],
        "sections": [
            {"key": "regression_risk", "title": "Regression risk", "severity": "risk",
             "lines": [{"text": "risk x", "evidence": "high", "supporting_sessions": [],
                        "confidence": "high"}]},
            {"key": "historical_success", "title": "Historical success", "severity": "ok",
             "lines": [{"text": "resolved before", "evidence": "strong",
                        "supporting_sessions": ["300"], "confidence": "confirmed"}]},
            {"key": "known_constraints", "title": "Known constraints", "severity": "caution",
             "lines": [{"text": "keep within 18..28", "evidence": "ww",
                        "supporting_sessions": ["300", "301"], "confidence": "high"}]},
        ],
    },
}


def test_not_empty_and_risk():
    assert not vm.is_empty(RESULT)
    assert vm.risk_level(RESULT) == "MODERATE"
    assert "lsd_accel" in vm.summary_line(RESULT)


def test_experiment_rows():
    rows = dict(vm.experiment_rows(RESULT))
    assert rows["Field"] == "lsd_accel"
    assert "22.0" in rows["Change"] and "25.0" in rows["Change"]


def test_rationale_lines():
    lines = vm.rationale_lines(RESULT)
    assert any("reduce wheelspin" in l for l in lines)


def test_consequence_rows():
    rows = vm.consequence_rows(RESULT)
    assert rows and all(len(r) == len(vm.CONSEQUENCE_COLUMNS) for r in rows)
    assert any(r[0] == "Primary" for r in rows)


def test_checklist_rows_have_glyph():
    rows = vm.checklist_rows(RESULT)
    assert any(r[0] == "✓" for r in rows)
    assert any(r[0] == "⚠" for r in rows)


def test_section_rows():
    assert vm.section_rows(RESULT, "historical_success")
    assert vm.section_rows(RESULT, "known_constraints")
    assert vm.section_rows(RESULT, "regression_risk")


def test_compact_summary():
    lines = vm.compact_summary(RESULT)
    assert lines and lines[0].startswith("Pre-flight risk:")


def test_is_empty_on_bad_result():
    assert vm.is_empty(None)
    assert vm.is_empty({"ok": False})
    assert vm.is_empty({"ok": True, "review": {}})
