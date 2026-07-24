"""Tests for the setup comparison view + pure diff (F2.5)."""

import pytest

from PyQt6.QtWidgets import QApplication

from ui.components.setup_comparison import SetupComparison, build_comparison_rows


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def _base():
    return {"ride_height_front": 60, "ride_height_rear": 70, "arb_front": 5,
            "arb_rear": 5, "aero_front": 430, "aero_rear": 590,
            "brake_bias_front": 54, "tyre_front": "Racing: Hard", "tyre_rear": "Racing: Hard"}


def _quali():
    return {"ride_height_front": 60, "ride_height_rear": 74, "arb_front": 5,
            "arb_rear": 4, "aero_front": 430, "aero_rear": 590,
            "brake_bias_front": 52, "tyre_front": "Racing: Soft", "tyre_rear": "Racing: Soft"}


class TestBuildComparisonRows:
    def test_flags_changed_fields(self):
        rows = build_comparison_rows(_base(), _quali())
        by_label = {r["label"]: r for r in rows}
        # Body height differs on the rear (70 vs 74) -> changed.
        assert by_label["Body Height (mm)"]["changed"] is True
        assert by_label["Anti-Roll Bar"]["changed"] is True     # 5/5 vs 5/4
        # Downforce identical -> not changed.
        assert by_label["Downforce"]["changed"] is False

    def test_paired_values_render_front_slash_rear(self):
        rows = build_comparison_rows(_base(), _quali())
        bh = next(r for r in rows if r["label"] == "Body Height (mm)")
        assert bh["a"] == "60 / 70"
        assert bh["b"] == "60 / 74"

    def test_identical_setups_have_no_changes(self):
        rows = build_comparison_rows(_base(), _base())
        assert all(r["changed"] is False for r in rows)

    def test_never_raises_on_garbage(self):
        # Two empty setups compare as all-unchanged placeholder rows (not a crash).
        rows = build_comparison_rows(None, None)
        assert isinstance(rows, list) and all(r["changed"] is False for r in rows)
        # A non-dict input is swallowed to an empty diff.
        assert isinstance(build_comparison_rows("x", {}), list)


class TestSetupComparisonWidget:
    def test_modes_populate_and_render_changed_only(self, qapp):
        w = SetupComparison()
        w.set_comparisons([
            ("Base ↔ Qualifying", "Base", _base(), "Qualifying", _quali()),
            ("Base ↔ Base", "Base", _base(), "Base2", _base()),
        ])
        assert w._combo.count() == 2
        # Default = changed only; Base↔Qualifying has differences.
        assert w.current_rows() > 0

    def test_identical_pair_shows_no_rows_when_changed_only(self, qapp):
        w = SetupComparison()
        w.set_comparisons([("Base ↔ Base", "Base", _base(), "Base2", _base())])
        assert w.current_rows() == 0

    def test_show_all_reveals_unchanged(self, qapp):
        w = SetupComparison()
        w.set_comparisons([("Base ↔ Base", "Base", _base(), "Base2", _base())])
        w._changed_only.setChecked(False)
        assert w.current_rows() > 0

    def test_empty_comparisons_safe(self, qapp):
        w = SetupComparison()
        w.set_comparisons([])
        assert w.current_rows() == 0

    def test_malformed_modes_filtered(self, qapp):
        w = SetupComparison()
        w.set_comparisons([("bad", "only", "three")])   # wrong arity -> filtered
        assert w._combo.count() == 0
