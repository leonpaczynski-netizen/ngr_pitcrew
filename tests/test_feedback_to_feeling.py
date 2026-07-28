"""The Garage Analyse must weigh the driver's handling verdict, not just telemetry.

`feedback_to_feeling` turns the structured practice-feedback dict into a feeling
string, and each phrase must fire the intended flag in the setup diagnosis so the
balance rules actually run. Also covers the honest "no change" headline.
"""

from strategy.setup_feedback_evidence import feedback_to_feeling
from strategy.setup_diagnosis import _parse_driver_feel
from services.setup_service import AnalysisResult


def _flags(feedback):
    return {k for k, v in _parse_driver_feel(feedback_to_feeling(feedback)).items() if v}


class TestFeedbackToFeeling:
    def test_entry_understeer_fires_entry_flag(self):
        assert "entry_understeer" in _flags({"corner_entry": "Understeer"})

    def test_entry_oversteer_fires_braking_flag(self):
        assert "rear_loose_under_braking" in _flags({"corner_entry": "Oversteer"})

    def test_mid_understeer_fires_mid_flag(self):
        assert "mid_corner_understeer" in _flags({"mid_corner": "Strong understeer"})

    def test_exit_oversteer_fires_exit_flag(self):
        assert "rear_loose_on_exit" in _flags({"exit_stability": "Oversteer"})

    def test_exit_strong_oversteer_fires_snap_flag(self):
        assert "snap_oversteer_exit" in _flags({"exit_stability": "Strong oversteer"})

    def test_neutral_and_blank_yield_nothing(self):
        assert feedback_to_feeling({"mid_corner": "Neutral", "corner_entry": ""}) == ""
        assert _flags({"mid_corner": "Neutral"}) == set()

    def test_notes_are_appended(self):
        s = feedback_to_feeling({"mid_corner": "Understeer", "notes": "vague T3"})
        assert "pushes wide" in s and "vague T3" in s

    def test_never_raises_on_garbage(self):
        assert feedback_to_feeling(None) == ""
        assert feedback_to_feeling("not a dict") == ""
        assert feedback_to_feeling(123) == ""

    def test_ambiguous_combos_are_omitted_not_misattributed(self):
        # Exit understeer + mid oversteer have no clean flag; must NOT wrongly fire
        # exit/other flags (bad advice is worse than none).
        assert _flags({"mid_corner": "Oversteer"}) == set()


class TestHonestNoChangeHeadline:
    def test_no_feeling_headline_points_to_review(self):
        r = AnalysisResult(ok=True, weighed_feeling=False)
        assert "balance wasn't judged" in r.headline
        assert "Review" in r.headline

    def test_with_feeling_headline_reassures(self):
        r = AnalysisResult(ok=True, weighed_feeling=True)
        assert "inside its window" in r.headline

    def test_recommendation_headline_unchanged(self):
        r = AnalysisResult(ok=True, changes=({"field": "arb_rear"},),
                           setup_fields={"arb_rear": 6})
        assert "1 change recommended" in r.headline
