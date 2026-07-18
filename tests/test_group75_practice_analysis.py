"""UAT Finding 2 — deterministic Practice Analysis engine.

Pure, Qt-free tests of the cross-lap pattern engine. Covers required tests:

  8.  Consecutive telemetry packets consolidate into one event (per lap).
  9.  Isolated events are not presented as recurring.
  10. Repeatable Turn 1 brake locking is identified across laps.
  11. Repeatable Turn 4 wheelspin is identified only when throttle+phase gates pass.
  12. A consistently clean Turn 6 is identified as a strength.
  13. Kerb-induced slip remains isolated/excluded.
  14. Practice Analysis uses clean laps only.
"""
from __future__ import annotations

from strategy.practice_pattern_analysis import (
    analyze_practice, EpisodeObservation, RecurrenceThresholds,
    RecurrenceClass, FeedbackAgreement,
)


def obs(lap, seg, name, phase, issue, *, clean=True, throttle=0.0, brake=0.0,
        excluded=False, reason="", duration=0.4, magnitude=0.2, steering=0.0):
    return EpisodeObservation(
        lap_number=lap, is_clean=clean, segment_id=seg, corner_name=name,
        phase=phase, issue_type=issue, throttle=throttle, brake=brake,
        excluded=excluded, exclusion_reason=reason, duration_s=duration,
        magnitude=magnitude, steering=steering)


# --------------------------------------------------------------------------- #
# Test 10 + 14 — repeatable Turn 1 brake locking across (clean) laps
# --------------------------------------------------------------------------- #

def test_turn1_brake_lock_recurring():
    # Locked front brakes in T1 on 4 of 5 clean laps.
    observations = [
        obs(l, "t1", "Turn 1", "braking", "front_lock", brake=0.95)
        for l in (1, 2, 3, 4)
    ]
    report = analyze_practice(
        observations,
        clean_lap_numbers=[1, 2, 3, 4, 5],
        total_lap_numbers=[1, 2, 3, 4, 5])
    t1 = next(f for f in report.findings if f.segment_id == "t1")
    assert t1.recurrence_class is RecurrenceClass.STRONGLY_RECURRING
    assert t1.laps_affected == 4 and t1.clean_laps_observed == 5
    assert t1.setup_authoring_eligible
    assert t1 in report.repeatable_issues
    assert "Turn 1" in t1.headline() and "four" not in t1.headline().lower()  # numeric


def test_clean_laps_only():
    # Same lock but 3 of the affected laps are NON-clean -> only 1 clean-lap hit.
    observations = [
        obs(1, "t1", "Turn 1", "braking", "front_lock", brake=0.95, clean=True),
        obs(2, "t1", "Turn 1", "braking", "front_lock", brake=0.95, clean=False),
        obs(3, "t1", "Turn 1", "braking", "front_lock", brake=0.95, clean=False),
        obs(4, "t1", "Turn 1", "braking", "front_lock", brake=0.95, clean=False),
    ]
    report = analyze_practice(
        observations,
        clean_lap_numbers=[1, 5, 6],   # laps 2-4 are not clean
        total_lap_numbers=[1, 2, 3, 4, 5, 6])
    t1 = next((f for f in report.findings if f.segment_id == "t1"), None)
    assert t1 is not None
    assert t1.laps_affected == 1  # only the one clean lap counts
    assert t1.recurrence_class is RecurrenceClass.ISOLATED


# --------------------------------------------------------------------------- #
# Test 8 — consecutive packets consolidate into one event per lap
# --------------------------------------------------------------------------- #

def test_multiple_episodes_same_lap_count_as_one_affected_lap():
    # Two consolidated episodes on lap 1 (e.g. two separate moments) + one each
    # on laps 2 and 3 -> 3 affected laps, 4 episodes.
    observations = [
        obs(1, "t1", "Turn 1", "braking", "front_lock"),
        obs(1, "t1", "Turn 1", "braking", "front_lock"),
        obs(2, "t1", "Turn 1", "braking", "front_lock"),
        obs(3, "t1", "Turn 1", "braking", "front_lock"),
    ]
    report = analyze_practice(
        observations, clean_lap_numbers=[1, 2, 3, 4, 5],
        total_lap_numbers=[1, 2, 3, 4, 5])
    t1 = next(f for f in report.findings if f.segment_id == "t1")
    assert t1.laps_affected == 3        # 3 distinct laps, not 4 packets
    assert t1.consolidated_episode_count == 4
    # 3 of 5 clean laps -> recurring (not strongly: fraction 0.6 < 0.75).
    assert t1.recurrence_class is RecurrenceClass.RECURRING


# --------------------------------------------------------------------------- #
# Test 9 — isolated events are not presented as recurring
# --------------------------------------------------------------------------- #

def test_isolated_event_not_recurring():
    observations = [obs(2, "t10", "Turn 10", "exit", "rear_wheelspin", throttle=0.9)]
    report = analyze_practice(
        observations, clean_lap_numbers=[1, 2, 3, 4, 5],
        total_lap_numbers=[1, 2, 3, 4, 5])
    t10 = next(f for f in report.findings if f.segment_id == "t10")
    assert t10.recurrence_class is RecurrenceClass.ISOLATED
    assert not t10.setup_authoring_eligible
    assert t10 not in report.repeatable_issues
    assert t10 in report.isolated_events


# --------------------------------------------------------------------------- #
# Test 11 — Turn 4 wheelspin recurring only when throttle+phase gates pass
# --------------------------------------------------------------------------- #

def test_turn4_wheelspin_recurring_when_gated_episodes_present():
    # The caller only emits an episode when the upstream throttle+phase gate
    # passed (throttle high, exit phase). Four such clean laps -> recurring.
    observations = [
        obs(l, "t4", "Turn 4", "exit", "rear_wheelspin", throttle=0.9)
        for l in (1, 2, 3, 4)
    ]
    report = analyze_practice(
        observations, clean_lap_numbers=[1, 2, 3, 4, 5],
        total_lap_numbers=[1, 2, 3, 4, 5])
    t4 = next(f for f in report.findings if f.segment_id == "t4")
    assert t4.recurrence_class is RecurrenceClass.STRONGLY_RECURRING
    assert t4.setup_authoring_eligible
    assert t4.phase == "exit"
    assert t4.throttle_range[0] >= 0.7  # gate evidence carried through


def test_no_gated_episodes_means_no_finding():
    # If the gate never passed, the caller emits no episodes -> no T4 finding.
    report = analyze_practice(
        [], clean_lap_numbers=[1, 2, 3, 4, 5], total_lap_numbers=[1, 2, 3, 4, 5])
    assert not any(f.segment_id == "t4" for f in report.findings)


# --------------------------------------------------------------------------- #
# Test 12 — consistently clean Turn 6 is a strength
# --------------------------------------------------------------------------- #

def test_turn6_strength():
    # Issues only in T1; T6 exists on the track and has no issues.
    observations = [
        obs(l, "t1", "Turn 1", "braking", "front_lock") for l in (1, 2, 3)
    ]
    report = analyze_practice(
        observations, clean_lap_numbers=[1, 2, 3, 4, 5],
        total_lap_numbers=[1, 2, 3, 4, 5],
        track_corners=[("t1", "Turn 1"), ("t6", "Turn 6")])
    strong_ids = {s.segment_id for s in report.strong_corners}
    assert "t6" in strong_ids
    assert "t1" not in strong_ids
    t6 = next(s for s in report.strong_corners if s.segment_id == "t6")
    assert "consistent" in t6.note.lower()


# --------------------------------------------------------------------------- #
# Test 13 — kerb-induced slip stays isolated/excluded
# --------------------------------------------------------------------------- #

def test_kerb_slip_excluded():
    # A rear-wheel-speed anomaly that the extractor flagged as a kerb strike,
    # on several laps — must NOT become a recurring authorable issue.
    observations = [
        obs(l, "t10", "Turn 10", "exit", "rear_wheelspin", throttle=0.9,
            excluded=True, reason="kerb strike")
        for l in (1, 2, 3, 4)
    ]
    report = analyze_practice(
        observations, clean_lap_numbers=[1, 2, 3, 4, 5],
        total_lap_numbers=[1, 2, 3, 4, 5])
    t10 = next(f for f in report.findings if f.segment_id == "t10")
    assert t10.recurrence_class is RecurrenceClass.EXCLUDED
    assert not t10.setup_authoring_eligible
    assert t10 not in report.repeatable_issues
    assert "kerb" in t10.finding.lower()


# --------------------------------------------------------------------------- #
# Thresholds + feedback agreement
# --------------------------------------------------------------------------- #

def test_threshold_boundaries():
    th = RecurrenceThresholds()
    assert th.classify(1, 5) is RecurrenceClass.ISOLATED
    assert th.classify(2, 5) is RecurrenceClass.EMERGING
    assert th.classify(3, 12) is RecurrenceClass.RECURRING
    assert th.classify(4, 12) is RecurrenceClass.STRONGLY_RECURRING
    # 3/3 laps is strong by fraction even though count < 4.
    assert th.classify(3, 3) is RecurrenceClass.STRONGLY_RECURRING
    assert th.classify(0, 5) is RecurrenceClass.STRENGTH


def test_feedback_agreement():
    observations = [
        obs(l, "t1", "Turn 1", "braking", "front_lock") for l in (1, 2, 3)
    ]
    report = analyze_practice(
        observations, clean_lap_numbers=[1, 2, 3, 4],
        total_lap_numbers=[1, 2, 3, 4],
        driver_feedback={"rear_braking": "front locks under braking into T1"})
    t1 = next(f for f in report.findings if f.segment_id == "t1")
    assert t1.driver_feedback_agreement is FeedbackAgreement.AGREES


def test_configurable_thresholds():
    # A stricter shop that needs 5 laps to call something recurring.
    strict = RecurrenceThresholds(recurring_min=5, strongly_recurring_min=6,
                                  strong_fraction=0.95)
    observations = [
        obs(l, "t1", "Turn 1", "braking", "front_lock") for l in (1, 2, 3)
    ]
    report = analyze_practice(
        observations, clean_lap_numbers=[1, 2, 3, 4, 5, 6, 7, 8],
        total_lap_numbers=list(range(1, 9)), thresholds=strict)
    t1 = next(f for f in report.findings if f.segment_id == "t1")
    assert t1.recurrence_class is RecurrenceClass.EMERGING  # 3 < recurring_min=5
    assert not t1.setup_authoring_eligible
