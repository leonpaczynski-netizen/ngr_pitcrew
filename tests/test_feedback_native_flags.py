"""The setup brain reads the Practice-Review dropdowns NATIVELY.

`driver_feel_flags_from_feedback` maps the exact dropdown {field: value} dict
straight to driver-feel flags — no free-text synthesis, no substring matching.
Also covers the native traction verdict, the kerb-compliance signal, and the
honest-headline `feedback_has_handling_signal`.
"""

from strategy.setup_diagnosis import (
    driver_feel_flags_from_feedback,
    traction_status_from_feedback,
    _feedback_reports_kerb_compliance,
    feedback_has_handling_signal,
    _FEEL_VOCABULARY,
)


def _on(feedback):
    return {k for k, v in driver_feel_flags_from_feedback(feedback).items() if v}


class TestNativeFlags:
    def test_returns_fully_keyed_dict(self):
        flags = driver_feel_flags_from_feedback({})
        assert set(flags) == set(_FEEL_VOCABULARY)
        assert all(v is False for v in flags.values())

    def test_entry_balance(self):
        assert _on({"corner_entry": "Understeer"}) == {"entry_understeer"}
        assert _on({"corner_entry": "Strong understeer"}) == {"entry_understeer"}
        assert _on({"corner_entry": "Oversteer"}) == {"rear_loose_under_braking"}
        assert _on({"corner_entry": "Neutral"}) == {"entry_balance_good"}

    def test_mid_corner(self):
        assert _on({"mid_corner": "Understeer"}) == {"mid_corner_understeer"}
        # mid-corner oversteer has no dedicated flag -> nothing (never mis-fires)
        assert _on({"mid_corner": "Oversteer"}) == set()

    def test_exit_balance(self):
        assert _on({"exit_stability": "Oversteer"}) == {"rear_loose_on_exit"}
        assert _on({"exit_stability": "Strong oversteer"}) == {
            "rear_loose_on_exit", "snap_oversteer_exit"}
        # exit power-understeer has no flag -> nothing
        assert _on({"exit_stability": "Understeer"}) == set()

    def test_rotation_low_is_understeer(self):
        assert _on({"rotation": "Poor"}) == {"mid_corner_understeer"}
        assert _on({"rotation": "Below par"}) == {"mid_corner_understeer"}
        assert _on({"rotation": "Good"}) == set()

    def test_braking_confidence_low_is_instability(self):
        assert _on({"braking_confidence": "Poor"}) == {"braking_instability"}
        assert _on({"braking_confidence": "Good"}) == set()

    def test_bottoming_severity(self):
        assert _on({"bottoming": "Severe"}) == {"bottoming"}
        assert _on({"bottoming": "Noticeable"}) == {"bottoming"}
        assert _on({"bottoming": "Minor"}) == set()

    def test_gearing(self):
        assert _on({"gear_choice": "Too long"}) == {"gearing_too_long"}
        assert _on({"gear_choice": "About right"}) == {"gearbox_good"}
        assert _on({"gear_choice": "Too short"}) == set()

    def test_fuel(self):
        assert _on({"fuel_behaviour": "Worse than expected"}) == {"fuel_use_high"}
        assert _on({"fuel_behaviour": "As expected"}) == set()

    def test_multiple_reinforce(self):
        flags = _on({"corner_entry": "Understeer", "rotation": "Poor",
                     "exit_stability": "Oversteer"})
        assert flags == {"entry_understeer", "mid_corner_understeer", "rear_loose_on_exit"}

    def test_drivetrain_dependent_and_leverless_states_map_to_nothing(self):
        for field, val in (("traction", "Poor"), ("drive_out", "Poor"),
                           ("straight_line", "Poor"), ("confidence", "Poor"),
                           ("kerb_behaviour", "Severe"),
                           ("tyre_condition", "Worse than expected")):
            assert _on({field: val}) == set(), f"{field} must not set a balance flag"

    def test_never_raises_on_garbage(self):
        assert not any(driver_feel_flags_from_feedback(None).values())
        assert not any(driver_feel_flags_from_feedback("nope").values())
        assert not any(driver_feel_flags_from_feedback(123).values())


class TestTractionStatus:
    def test_low_traction_is_degraded(self):
        assert traction_status_from_feedback({"traction": "Poor"}) == "degraded"
        assert traction_status_from_feedback({"traction": "Below par"}) == "degraded"

    def test_high_traction_is_good(self):
        assert traction_status_from_feedback({"traction": "Excellent"}) == "good"
        assert traction_status_from_feedback({"traction": "Good"}) == "good"

    def test_traction_leads_drive_out(self):
        assert traction_status_from_feedback(
            {"traction": "Good", "drive_out": "Poor"}) == "good"

    def test_drive_out_used_when_traction_blank(self):
        assert traction_status_from_feedback({"drive_out": "Poor"}) == "degraded"

    def test_unknown_when_absent_or_mid(self):
        assert traction_status_from_feedback({}) == "unknown"
        assert traction_status_from_feedback({"traction": "OK"}) == "unknown"
        assert traction_status_from_feedback(None) == "unknown"


class TestKerbComplianceAndSignal:
    def test_kerb_compliance_signal(self):
        assert _feedback_reports_kerb_compliance({"kerb_behaviour": "Severe"}) is True
        assert _feedback_reports_kerb_compliance({"kerb_behaviour": "Noticeable"}) is True
        assert _feedback_reports_kerb_compliance({"kerb_behaviour": "Minor"}) is False
        assert _feedback_reports_kerb_compliance({}) is False

    def test_handling_signal_true_for_real_verdicts(self):
        assert feedback_has_handling_signal({"mid_corner": "Understeer"}) is True
        assert feedback_has_handling_signal({"traction": "Poor"}) is True
        assert feedback_has_handling_signal({"kerb_behaviour": "Severe"}) is True

    def test_handling_signal_false_for_overall_or_notes_only(self):
        assert feedback_has_handling_signal({"overall": "better"}) is False
        assert feedback_has_handling_signal({"notes": "felt nice"}) is False
        assert feedback_has_handling_signal({}) is False
        assert feedback_has_handling_signal(None) is False
