"""The gate: a question with a working resolver may never be asked."""
from __future__ import annotations

import pytest

from pitcrew.analysis.session import LapInput
from pitcrew.prompts import questions as q
from pitcrew.prompts.context import PromptContext


def a_lap(lap_num=2, frames=None, **overrides) -> LapInput:
    fields = dict(lap_num=lap_num, lap_time_ms=109_000,
                  fuel_start=80.0, fuel_end=74.0, frames=frames or [])
    fields.update(overrides)
    return LapInput(**fields)


def exit_frame(*, steering=30.0, slip_rl=1.05, slip_rr=1.05,
               susp_rl=210.0, susp_rr=240.0, throttle=100.0, lat_g=1.2,
               brake=0.0) -> dict:
    return {"steering_deg": steering, "lat_g": lat_g, "throttle_pct": throttle,
            "brake_pct": brake, "slip_rl": slip_rl, "slip_rr": slip_rr,
            "susp_mm_rl": susp_rl, "susp_mm_rr": susp_rr}


def a_context(frames) -> PromptContext:
    return PromptContext(laps=[a_lap(frames=frames)])


# ------------------------------------------------------------------ registry


def test_every_question_either_resolves_or_says_why_not():
    """The rule that keeps the registry honest."""
    for question in q.REGISTRY:
        has_resolver = question.resolver is not None
        has_reason = bool(question.unmeasurable_because)
        assert has_resolver != has_reason, (
            f"{question.key} must have exactly one of a resolver or a reason")


def test_a_question_with_neither_is_rejected():
    with pytest.raises(q.RegistryError):
        q.Question(key="lazy", asks="?", feeds=(), impact=5)


def test_a_question_claiming_both_is_rejected():
    with pytest.raises(q.RegistryError):
        q.Question(key="confused", asks="?", feeds=(), impact=5,
                   resolver=lambda store, ctx: None,
                   unmeasurable_because="but also this")


def test_an_answer_without_evidence_is_rejected():
    with pytest.raises(q.RegistryError):
        q.Answer("both rears together", q.MEASURED, "")


# ------------------------------------------------- the acceptance test
#
# 23 Aug 2026: the driver was asked to watch the tyre indicators and report
# whether one rear span alone or both went together. It was in the frames.


def test_both_rears_together_is_measured_and_the_question_is_suppressed():
    frames = [exit_frame(slip_rl=1.052, slip_rr=1.046)] * 600
    result = q.resolve(None, a_context(frames), kind=q.REFINEMENT)

    assert "rear_wheelspin_pattern" in result.suppressed
    assert all(a.key != "rear_wheelspin_pattern" for a in result.asked), (
        "the tyre-indicator question must not be reachable when the frames "
        "already answer it")
    answer = result.answered["rear_wheelspin_pattern"]
    assert "both rears together" in answer.value
    assert answer.source == q.MEASURED
    assert "corner-exit frames" in answer.evidence


def test_the_inside_wheel_alone_resolves_the_other_way():
    # Inside is the LESS compressed wheel; susp_rl < susp_rr on positive
    # steering makes the left the inside one, and only it is spinning.
    frames = [exit_frame(slip_rl=1.09, slip_rr=1.001)] * 600
    answer = q.rear_wheelspin_pattern(None, a_context(frames))
    assert answer is not None and "inside rear alone" in answer.value


def test_the_sign_convention_is_derived_not_assumed():
    """Flip which wheel is loaded and the verdict must follow the suspension."""
    # susp_rr < susp_rl now, so on positive steering the RIGHT is the inside
    # wheel. The spinning wheel is still the inside one, so the verdict holds.
    frames = [exit_frame(slip_rl=1.001, slip_rr=1.09,
                         susp_rl=240.0, susp_rr=210.0)] * 600
    answer = q.rear_wheelspin_pattern(None, a_context(frames))
    assert answer is not None and "inside rear alone" in answer.value


# ------------------------------------------------------------------ the gate


def test_too_few_frames_asks_rather_than_guesses():
    result = q.resolve(None, a_context([exit_frame()] * 10), kind=q.REFINEMENT)
    assert "rear_wheelspin_pattern" not in result.suppressed
    assert any(a.key == "rear_wheelspin_pattern" for a in result.asked)


def test_no_roll_refuses_to_pick_an_inside_wheel():
    """Equal suspension loads carry no information about which side is inside."""
    frames = [exit_frame(susp_rl=225.0, susp_rr=225.0)] * 600
    assert q.rear_wheelspin_pattern(None, a_context(frames)) is None


def test_an_ambiguous_pattern_resolves_to_nothing():
    """Half and half is a coin toss, and a coin toss is not an answer."""
    frames = ([exit_frame(slip_rl=1.052, slip_rr=1.046)] * 300
              + [exit_frame(slip_rl=1.09, slip_rr=1.001)] * 300)
    assert q.rear_wheelspin_pattern(None, a_context(frames)) is None


def test_a_broken_resolver_asks_and_is_recorded():
    """Silence from a broken query is the failure this module exists to stop."""
    def explodes(store, context):
        raise RuntimeError("bad query")

    registry = (q.Question(key="boom", asks="?", feeds=(), impact=9,
                           resolver=explodes),)
    result = q.resolve(None, a_context([]), kind=q.REFINEMENT,
                       registry=registry)
    assert result.failed == ("boom",)
    assert [a.key for a in result.asked] == ["boom"]
    assert "boom" not in result.answered


def test_unmeasurable_questions_are_never_suppressed():
    result = q.resolve(None, a_context([exit_frame()] * 600),
                       kind=q.REFINEMENT, limit=99)
    assert "brake_balance_as_run" in [a.key for a in result.asked]


# ---------------------------------------------------------------- the queue


def test_the_queue_is_capped_and_ranked_by_impact():
    result = q.resolve(None, a_context([]), kind=q.REFINEMENT)
    assert len(result.asked) <= q.MAX_QUESTIONS
    impacts = [a.question.impact for a in result.asked]
    assert impacts == sorted(impacts, reverse=True)
    # Rank zero: what is actually in the car outranks everything.
    assert result.asked[0].key == "brake_balance_as_run"


def test_kinds_filter_the_registry():
    result = q.resolve(None, a_context([]), kind=q.QUALI_PLAN, limit=99)
    assert "braking_feel" not in [a.key for a in result.asked]
    assert "assist_regulation" in [a.key for a in result.asked]


def test_a_question_states_what_is_known_before_it_asks():
    frames = [exit_frame(slip_rl=1.052, slip_rr=1.046)] * 600
    result = q.resolve(None, a_context(frames), kind=q.REFINEMENT, limit=99)
    push = next(a for a in result.asked if a.key == "push_location")
    assert push.context_line is not None
    assert "both rears together" in push.text
    assert push.question.asks in push.text


# ------------------------------------------------------------- other resolvers


def test_tyre_state_reads_the_gauge_instead_of_asking():
    laps = [a_lap(lap_num=8, wear_fl=0.32, wear_fr=0.21, wear_rl=0.22,
                  wear_rr=0.33),
            a_lap(lap_num=10, wear_fl=0.40, wear_fr=0.25, wear_rl=0.33,
                  wear_rr=0.20)]
    answer = q.tyre_state_at_end(None, PromptContext(laps=laps))
    assert answer is not None
    assert "FL" in answer.value and "40%" in answer.value
    assert "lap 10" in answer.evidence


def test_tyre_state_with_no_gauge_reading_asks():
    assert q.tyre_state_at_end(None, PromptContext(laps=[a_lap()])) is None


def test_throttle_state_answers_derived_never_measured():
    """It is a proxy, and a proxy may not claim to be a measurement."""
    mid = {"brake_pct": 0.0, "lat_g": 1.0, "steering_deg": 30.0,
           "speed_kph": 110.0}
    frames = ([dict(mid, throttle_pct=0.0)] * 200
              + [dict(mid, throttle_pct=100.0, steering_deg=45.0)] * 200)
    answer = q.push_throttle_state(None, a_context(frames))
    assert answer is not None
    assert answer.source == q.DERIVED
    assert "on throttle" in answer.value
    assert "speed buckets" in answer.evidence
    assert "weighted ratio" in answer.evidence


def test_throttle_state_recognises_a_both_phase_push():
    mid = {"brake_pct": 0.0, "lat_g": 1.0, "steering_deg": 30.0,
           "speed_kph": 110.0}
    frames = ([dict(mid, throttle_pct=0.0)] * 200
              + [dict(mid, throttle_pct=100.0)] * 200)
    answer = q.push_throttle_state(None, a_context(frames))
    assert answer is not None and "both phases" in answer.value


def test_throttle_state_needs_both_bands():
    mid = {"brake_pct": 0.0, "lat_g": 1.0, "steering_deg": 30.0,
           "speed_kph": 110.0}
    frames = [dict(mid, throttle_pct=100.0)] * 400
    assert q.push_throttle_state(None, a_context(frames)) is None


def test_throttle_state_compares_within_speed_buckets():
    """Otherwise it compares corner types and calls it a throttle effect.

    Off throttle only ever happens in the slow bucket here and on throttle
    only in the fast one, with the SAME steering-per-g in each. Pooled, the
    fast bucket's naturally lower angle would read as an on-throttle
    improvement; bucketed, there is no pair to compare and it says nothing.
    """
    slow = {"brake_pct": 0.0, "lat_g": 1.0, "steering_deg": 40.0,
            "speed_kph": 70.0, "throttle_pct": 0.0}
    fast = {"brake_pct": 0.0, "lat_g": 2.0, "steering_deg": 40.0,
            "speed_kph": 200.0, "throttle_pct": 100.0}
    assert q.push_throttle_state(
        None, a_context([slow] * 300 + [fast] * 300)) is None


def test_throttle_state_survives_null_channels():
    """22,365 frames in one event carry an explicit null in these channels."""
    mid = {"brake_pct": 0.0, "lat_g": 1.0, "steering_deg": 30.0,
           "speed_kph": 110.0}
    null_frame = {"brake_pct": 0.0, "lat_g": None, "steering_deg": None,
                  "speed_kph": None, "throttle_pct": None}
    frames = ([dict(mid, throttle_pct=0.0)] * 200
              + [dict(mid, throttle_pct=100.0)] * 200
              + [null_frame] * 500)
    answer = q.push_throttle_state(None, a_context(frames))
    assert answer is not None and "both phases" in answer.value


def test_wheelspin_survives_null_channels():
    frames = ([exit_frame(slip_rl=1.052, slip_rr=1.046)] * 600
              + [{"steering_deg": None, "lat_g": None, "throttle_pct": None,
                  "brake_pct": None, "slip_rl": None, "slip_rr": None,
                  "susp_mm_rl": 278.6, "susp_mm_rr": None}] * 500)
    answer = q.rear_wheelspin_pattern(None, a_context(frames))
    assert answer is not None and "both rears together" in answer.value
