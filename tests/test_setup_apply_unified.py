"""F2.2 — prove the setup recommendation is applied from the SAME rows it shows.

The audit found a renderer-vs-plan divergence: the table rendered from
data["changes"] while Apply wrote from a separate data["setup_fields"]. The VM's
applied_field_values() closes that: the applied dict is derived from the displayed
FieldRows, so shown == applied by construction.
"""

from ui.setup_recommendation_vm import (
    build_recommendation_vm, _coerce_value, PROPOSED, APPLIED, REJECTED,
)


def _sample():
    return {
        "changes": [
            # clamped value differs from raw 'to' — the driver sees the CLAMPED value.
            {"field": "arb_rear", "setting": "Rear ARB", "from": 5, "to": 3,
             "to_clamped": 4, "confidence_level": "high"},
            {"field": "brake_bias_front", "setting": "Brake bias", "from": 52.0,
             "to": 54.0, "confidence_level": "medium"},
            {"field": "transmission_type", "setting": "Gearbox", "from": "Std",
             "to": "Fully Custom"},          # non-numeric enum value
            {"field": "", "setting": "Unresolved", "from": 1, "to": 2},  # no field key
        ],
        "rejected_changes": [
            {"field": "aero_rear", "setting": "Rear wing", "from": 300, "to": 400},
        ],
    }


class TestShownEqualsApplied:
    def test_applied_values_match_displayed_rows(self):
        vm = build_recommendation_vm(_sample())
        applied = vm.applied_field_values()
        # Every changed+proposed row with a field is in applied, and its applied
        # value stringifies to exactly the value shown in the row.
        from ui.setup_recommendation_vm import _to_str
        for r in vm.field_rows:
            if r.changed and r.field and r.status == PROPOSED:
                assert r.field in applied, f"{r.field} shown but not applied"
                assert _to_str(applied[r.field]) == r.recommended_value, (
                    f"shown {r.recommended_value!r} != applied {applied[r.field]!r}"
                )

    def test_clamped_value_is_the_one_applied(self):
        # Raw 'to' was 3, clamped to 4 — the APPLIED value must be the clamped 4.
        vm = build_recommendation_vm(_sample())
        assert vm.applied_field_values()["arb_rear"] == 4

    def test_non_numeric_value_preserved(self):
        vm = build_recommendation_vm(_sample())
        assert vm.applied_field_values()["transmission_type"] == "Fully Custom"

    def test_unresolved_and_rejected_excluded(self):
        vm = build_recommendation_vm(_sample())
        applied = vm.applied_field_values()
        assert "aero_rear" not in applied          # rejected
        assert "" not in applied                    # unresolved field key
        # exactly the three resolved, changed fields
        assert set(applied) == {"arb_rear", "brake_bias_front", "transmission_type"}

    def test_mark_applied_still_yields_same_values(self):
        vm = build_recommendation_vm(_sample())
        before = vm.applied_field_values()
        after = vm.mark_applied().applied_field_values()
        assert before == after   # status flip proposed->applied doesn't change values

    def test_empty_recommendation_is_empty(self):
        assert build_recommendation_vm({}).applied_field_values() == {}


class TestCoerce:
    def test_int_float_string(self):
        assert _coerce_value("4") == 4 and isinstance(_coerce_value("4"), int)
        assert _coerce_value("54.5") == 54.5
        assert _coerce_value("Fully Custom") == "Fully Custom"
        assert _coerce_value("") == ""
        assert _coerce_value(None) == ""
