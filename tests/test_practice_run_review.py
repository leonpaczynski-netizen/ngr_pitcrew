"""Reviewing a recorded run: measured laps, and the outcome built from them.

UAT-4: "I ran base setup and recorded practice — there is nothing that shows me my lap
times or fuel per lap to review", and "when I submit my feedback it just takes me to a
blank outcome screen". Nothing ever turned the stored lap rows into either surface.
"""

import pytest

from strategy.practice_run_review import (
    CLEAN_LAP_TOLERANCE, MIN_LAPS_FOR_VERDICT, RunReview, build_run_outcome,
    build_run_review, format_delta, format_lap_time,
)


def _laps(*times, fuel=3.0, compound="RM"):
    return [{"lap_num": i, "lap_time_ms": t, "fuel_used": fuel, "compound": compound}
            for i, t in enumerate(times, 1)]


class TestFormatting:
    def test_lap_time(self):
        assert format_lap_time(92100) == "1:32.100"
        assert format_lap_time(0) == "—"
        assert format_lap_time(None) == "—"

    def test_delta(self):
        assert format_delta(-1400) == "-1.400"
        assert format_delta(700) == "+0.700"
        assert format_delta(0) == "—"


class TestRunReview:
    def test_no_laps_is_empty_not_a_crash(self):
        r = build_run_review([])
        assert r.has_laps is False
        assert r.summary_line == ""
        assert build_run_review(None).has_laps is False

    def test_measures_pace_fuel_and_consistency(self):
        r = build_run_review(_laps(92500, 92100, 92800))
        assert r.best_ms == 92100
        assert r.clean_laps == 3
        assert r.average_clean_ms == 92467
        assert r.consistency_ms > 0
        assert r.fuel_per_lap == 3.0
        assert r.laps_of_fuel == pytest.approx(33.3, abs=0.1)   # 100 L tank
        assert "3.00 L/lap" in r.summary_line

    def test_in_and_out_laps_are_excluded_but_still_shown(self):
        rows = _laps(92500, 92100)
        rows.insert(0, {"lap_num": 0, "lap_time_ms": 98000, "is_out_lap": 1, "fuel_used": 3.1})
        r = build_run_review(rows)
        assert r.clean_laps == 2
        out = [l for l in r.laps if not l.clean][0]
        assert out.excluded_reason == "in/out lap"
        assert len(r.laps) == 3          # nothing is hidden from the driver

    def test_an_out_lap_never_becomes_the_best_lap(self):
        """UAT-6: "in practice review it's counting out lap as the best lap".

        A flying out lap (GT7's rolling start gives one) set ``best``, so the run
        reported a time the driver never raced and every honest lap read seconds slow
        against it.
        """
        rows = _laps(118072, 118517, 117926, 117695)
        rows.insert(0, {"lap_num": 0, "lap_time_ms": 112791, "is_out_lap": 1,
                        "fuel_used": 3.63})
        r = build_run_review(rows)
        assert r.best_ms == 117695                     # the best CLEAN lap
        assert "1:57.695" in r.summary_line
        out = [l for l in r.laps if not l.clean][0]
        assert out.excluded_reason == "in/out lap"
        assert out.delta_to_best_ms < 0                # shown honestly, still excluded
        # The clean laps are measured against a lap that was actually raced.
        assert [l.delta_to_best_ms for l in r.laps if l.clean] == [377, 822, 231, 0]

    def test_the_out_lap_does_not_decide_which_laps_are_off_the_pace(self):
        """A slow in-lap must not raise the tolerance and let a bad lap count as clean."""
        rows = _laps(92100, 92300)
        rows.append({"lap_num": 3, "lap_time_ms": 130000, "is_pit_lap": 1, "fuel_used": 3.0})
        rows.append({"lap_num": 4, "lap_time_ms": int(92100 * CLEAN_LAP_TOLERANCE) + 3000,
                     "fuel_used": 3.0})
        r = build_run_review(rows)
        assert r.clean_laps == 2
        reasons = sorted(l.excluded_reason for l in r.laps if not l.clean)
        assert reasons == ["in/out lap", "off the pace"]

    def test_a_run_of_only_in_out_laps_still_reports_something(self):
        rows = [{"lap_num": 1, "lap_time_ms": 98000, "is_out_lap": 1, "fuel_used": 3.0}]
        r = build_run_review(rows)
        assert r.has_laps and r.best_ms == 98000 and r.clean_laps == 0

    def test_a_lap_far_off_the_pace_does_not_pollute_the_average(self):
        slow = int(92100 * CLEAN_LAP_TOLERANCE) + 5000
        r = build_run_review(_laps(92100, 92300, slow))
        assert r.clean_laps == 2
        assert r.average_clean_ms == 92200
        assert [l.excluded_reason for l in r.laps if not l.clean] == ["off the pace"]

    def test_zero_time_laps_are_ignored(self):
        r = build_run_review(_laps(92100, 0, 92300))
        assert len(r.laps) == 2

    def test_mistakes_are_counted(self):
        rows = _laps(92100, 92300)
        rows[0]["lock_up_count"] = 2
        rows[1]["wheelspin_count"] = 3
        r = build_run_review(rows)
        assert r.lock_ups == 2 and r.wheelspin == 3

    def test_unknown_fuel_never_invents_a_stint(self):
        r = build_run_review(_laps(92100, 92300, 92200, fuel=0))
        assert r.fuel_per_lap == 0.0
        assert r.laps_of_fuel == 0.0
        assert "per tank" not in r.summary_line


class TestRunOutcome:
    def test_no_laps_says_so_instead_of_going_blank(self):
        o = build_run_outcome(RunReview())
        assert o.verdict == "inconclusive"
        assert "no laps" in o.summary.lower()
        assert o.primary_action_key == "gather"

    def test_first_run_is_inconclusive_not_an_improvement(self):
        o = build_run_outcome(build_run_review(_laps(92500, 92100, 92800)),
                              feedback={"overall": "better"})
        assert o.verdict == "inconclusive"
        assert "first recorded run" in o.summary
        assert o.primary_action_key == "gather"
        assert o.telemetry_findings          # it still shows what was measured

    def test_too_few_clean_laps_refuses_to_judge(self):
        o = build_run_outcome(build_run_review(_laps(92100, 92300)),
                              previous=build_run_review(_laps(93500, 93600, 93400)))
        assert o.verdict == "inconclusive"
        assert str(MIN_LAPS_FOR_VERDICT) in o.summary
        assert o.confidence == "low"

    def test_faster_run_agreeing_with_the_driver(self):
        prev = build_run_review(_laps(93500, 93600, 93400))
        o = build_run_outcome(build_run_review(_laps(92500, 92100, 92800)),
                              feedback={"overall": "better"}, previous=prev)
        assert o.verdict == "improved"
        assert o.agreements == ("telemetry says improved, you said improved",)
        assert o.contradictions == ()
        assert o.confidence == "medium"
        assert o.primary_action_key == "keep"
        assert any("Best lap -1.300s" in c for c in o.changed_vs_previous)

    def test_slower_run_offers_a_revert(self):
        prev = build_run_review(_laps(92100, 92300, 92200))
        o = build_run_outcome(build_run_review(_laps(93500, 93600, 93400)),
                              feedback={"overall": "worse"}, previous=prev)
        assert o.verdict == "worse"
        assert o.primary_action_key == "revert"

    def test_a_contradiction_lowers_confidence_and_never_outvotes_the_driver(self):
        prev = build_run_review(_laps(93500, 93600, 93400))
        o = build_run_outcome(build_run_review(_laps(92500, 92100, 92800)),
                              feedback={"overall": "worse"}, previous=prev)
        assert o.verdict == "improved"                 # what was measured, stated plainly
        assert o.contradictions == ("telemetry says improved, you said worse",)
        assert o.confidence == "low"
        assert o.primary_action_key == "gather"        # not "keep"

    def test_noise_sized_change_is_unchanged_not_a_result(self):
        prev = build_run_review(_laps(92150, 92300, 92200))
        o = build_run_outcome(build_run_review(_laps(92100, 92300, 92200)),
                              feedback={"overall": "unchanged"}, previous=prev)
        assert o.verdict == "unchanged"
        assert o.primary_action_key == "refine"

    def test_driver_feedback_is_summarised_without_the_neutral_noise(self):
        o = build_run_outcome(
            build_run_review(_laps(92500, 92100, 92800)),
            feedback={"overall": "better", "entry_balance": "Neutral",
                      "traction": "Excellent", "kerb_behaviour": "None",
                      "notes": "felt planted"})
        assert "traction: Excellent" in o.feedback_summary
        assert "Neutral" not in o.feedback_summary
        assert "felt planted" in o.feedback_summary
