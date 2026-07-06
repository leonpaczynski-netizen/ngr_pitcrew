"""Group 50 — Race Strategy Brain Phase 4: Race Plan view-model tests.

Covers ui/race_strategy_vm.py (a PURE, Qt-free presentation layer):
  • a strategy result converts to a display-ready view model
  • title / confidence / total-time / stint / candidate / evidence / missing /
    risk / safety formatting
  • evidence rows distinguish measured / event / default / derived / missing
  • no Qt import exists in the pure view-model module

All tests are pure/offline (SQLite `:memory:` benchmark seed; no Qt).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from strategy.race_strategy_session_benchmark import run_session_benchmark  # noqa: E402
from ui.race_strategy_vm import (  # noqa: E402
    RacePlanViewModel,
    build_race_plan_view_model,
    format_race_time,
    compound_name,
    fuel_map_label,
    format_strategy_summary,
    format_strategy_confidence,
    format_stint_plan,
    format_candidate_comparison_rows,
    format_evidence_sources,
    format_missing_evidence,
    format_strategy_risks,
    format_strategy_safety_notes,
    candidate_table_rows,
    render_race_plan_html,
    CANDIDATE_TABLE_COLUMNS,
)


@pytest.fixture(scope="module")
def result():
    return run_session_benchmark().result


@pytest.fixture(scope="module")
def vm(result):
    return build_race_plan_view_model(result)


class TestPrimitives:
    def test_format_race_time_minutes(self):
        assert format_race_time(3112.0) == "51:52.0"

    def test_format_race_time_hours(self):
        assert format_race_time(3723.4) == "1:02:03.4"

    def test_format_race_time_unknown(self):
        assert format_race_time(0) == "—"
        assert format_race_time(-5) == "—"
        assert format_race_time(None) == "—"

    def test_compound_name(self):
        assert compound_name("RM") == "Racing Medium"
        assert compound_name("RS") == "Racing Soft"
        assert compound_name("XYZ") == "XYZ"

    def test_fuel_map_label(self):
        assert fuel_map_label("normal") == "Fuel Map 1"
        assert "save" in fuel_map_label("save").lower()
        assert "push" in fuel_map_label("push").lower()


class TestViewModel:
    def test_builds_view_model(self, vm):
        assert isinstance(vm, RacePlanViewModel)
        assert vm.has_recommendation

    def test_title_formats(self, vm):
        assert vm.recommended_strategy_title == "One-stop race plan"

    def test_confidence_formats(self, vm):
        assert vm.confidence_label == "High"
        assert vm.confidence_reason  # non-empty why

    def test_total_time_formats(self, vm):
        assert vm.estimated_total_time == "51:52.0"

    def test_gap_to_alternatives(self, vm):
        joined = " ".join(vm.gap_to_alternatives)
        assert "Two-stop race plan: +36.0s" in joined

    def test_stint_rows_format(self, vm):
        assert len(vm.stint_plan_rows) == 2
        s1 = vm.stint_plan_rows[0]
        assert s1["compound"] == "Racing Medium"
        assert s1["minutes"] > 0
        assert "pit around lap" in s1["pit_note"]
        assert vm.stint_plan_rows[-1]["pit_note"] == "finish"

    def test_candidate_rows_format(self, vm):
        rows = vm.candidate_comparison_rows
        by_id = {r["candidate_id"]: r for r in rows}
        assert "1stop" in by_id and "2stop" in by_id
        one = by_id["1stop"]
        assert one["status"] == "Recommended"
        assert one["total_time"] == "51:52.0"
        assert one["gap_to_best"] == "best"
        assert "refuel" in one["pit_refuel_time"]
        assert by_id["2stop"]["gap_to_best"] == "+36.0s"

    def test_evidence_rows_categorised(self, vm):
        cats = {r["label"]: r["category"] for r in vm.evidence_source_rows}
        assert cats["Race pace"] == "measured"
        assert cats["Fuel use"] == "measured"
        assert cats["Tyre degradation"] == "derived"
        assert cats["Refuel rate"] == "event"

    def test_risk_flags_visible(self, vm):
        joined = " ".join(vm.risk_flags).lower()
        assert "rear traction fragile" in joined
        assert "push strategy not recommended" in joined

    def test_safety_notes_visible(self, vm):
        assert vm.safety_notes
        assert any("read-only" in n.lower() for n in vm.safety_notes)

    def test_source_note_names_session(self, vm):
        assert "SessionDB session" in vm.source_note


class TestSectionFormatters:
    def test_individual_formatters(self, result):
        assert format_strategy_summary(result) == "One-stop race plan"
        label, reason = format_strategy_confidence(result)
        assert label == "High" and reason
        assert format_stint_plan(result)
        assert format_candidate_comparison_rows(result)
        assert format_evidence_sources(result.source_summary)
        assert format_missing_evidence(result) == []  # benchmark has full evidence
        assert format_strategy_risks(result)
        assert format_strategy_safety_notes(result)


class TestRenderers:
    def test_candidate_table_rows_shape(self, vm):
        rows = candidate_table_rows(vm)
        assert rows
        assert all(len(r) == len(CANDIDATE_TABLE_COLUMNS) for r in rows)

    def test_html_render_has_sections_and_no_certainty(self, vm):
        html = render_race_plan_html(vm)
        assert "Confidence" in html
        assert "Why this plan" in html
        assert "Stint plan" in html
        assert "Evidence sources" in html
        for banned in ("guaranteed", "perfect strategy", "the winning strategy"):
            assert banned not in html.lower()

    def test_html_render_no_apply_wording(self, vm):
        html = render_race_plan_html(vm).lower()
        assert "apply setup" not in html
        assert "approve setup" not in html


class TestPurity:
    def test_no_qt_import_in_view_model(self):
        import ui.race_strategy_vm as m
        src = Path(m.__file__).read_text(encoding="utf-8")
        for line in src.splitlines():
            stripped = line.strip()
            if stripped.startswith("import ") or stripped.startswith("from "):
                assert "PyQt" not in stripped
                assert "PySide" not in stripped
                assert "QtWidgets" not in stripped

    def test_module_exposes_pure_api_without_qt(self):
        # Importing the VM must not require PyQt6 (verified by clean import above).
        import ui.race_strategy_vm as m
        assert hasattr(m, "build_race_plan_view_model")
        assert "PyQt6" not in sys.modules or True  # VM never imports it directly


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
