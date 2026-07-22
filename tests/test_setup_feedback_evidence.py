"""Unit tests for strategy/setup_feedback_evidence.py (UI-rebuild F0.1 extraction).

Verifies the pure feedback-evidence helpers behave identically to the versions
that used to live in ui/dashboard.py: deterministic, best-effort, never raise.
"""

import strategy.setup_feedback_evidence as sfe


class TestCombineDriverFeedbackText:
    def test_joins_structured_and_freetext_fields_in_order(self):
        row = {
            "corner_entry": "understeer on entry",
            "mid_corner": "",
            "exit_stability": "snappy exit",
            "rear_braking": None,
            "tyre_condition": "graining rears",
            "notes": "overall better",
            "ignored_field": "should not appear",
        }
        out = sfe.combine_driver_feedback_text(row)
        assert out == "understeer on entry; snappy exit; graining rears; overall better"

    def test_empty_row_returns_empty_string(self):
        assert sfe.combine_driver_feedback_text({}) == ""

    def test_strips_whitespace_and_skips_blanks(self):
        row = {"corner_entry": "  loose  ", "notes": "   "}
        assert sfe.combine_driver_feedback_text(row) == "loose"

    def test_never_raises_on_bad_input(self):
        # Non-dict / odd values must not raise (best-effort contract).
        assert sfe.combine_driver_feedback_text(None) == ""  # type: ignore[arg-type]
        assert sfe.combine_driver_feedback_text({"notes": 123}) == ""  # .strip() on int -> caught

    def test_field_list_is_the_documented_set(self):
        assert sfe.FEEDBACK_TEXT_FIELDS == (
            "corner_entry", "mid_corner", "exit_stability", "rear_braking",
            "tyre_condition", "notes",
        )


class TestVerifyChangeOutcome:
    def test_returns_empty_dict_shape_on_failure(self):
        # Passing windows the verification model cannot consume must yield the
        # neutral shape rather than raising.
        out = sfe.verify_change_outcome(
            rule_id="R1", field="rear_arb", car_id=1, track="fuji",
            layout_id="full", before_window=object(), after_window=object(),
            feedback_text="",
        )
        assert set(out.keys()) == {
            "target_issue", "evidence_summary", "safety_notes", "outcome_kind",
        }
        assert all(isinstance(v, str) for v in out.values())

    def test_dashboard_imports_resolve_to_this_module(self):
        # The historical private names in ui/dashboard.py must resolve here.
        import ui.dashboard as dash
        assert dash._combine_driver_feedback_text is sfe.combine_driver_feedback_text
        assert dash._verify_change_outcome is sfe.verify_change_outcome
        assert dash._FEEDBACK_TEXT_FIELDS is sfe.FEEDBACK_TEXT_FIELDS
