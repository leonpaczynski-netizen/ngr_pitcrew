"""Sprint 5 — cross-lap persistence engine + spec fixtures A, B, F.

The core guarantee: one or two poor laps, or scattered single-corner events,
CANNOT reach a setup-eligible classification. Only same-corner/same-phase
recurrence across a meaningful fraction of representative laps — or cross-session
confirmation — becomes eligible.
"""
from __future__ import annotations

from strategy.cross_lap_persistence import (
    IssueOccurrence, LapMeta, RecurrenceThresholds, DEFAULT_THRESHOLDS,
    PersistenceClass, analyse_cross_lap, SETUP_ELIGIBLE,
)


def _occ(session, lap, seg, *, phase="exit", itype="wheelspin", axle="rear",
         subtype="power_wheelspin", conf=0.7, sev=0.4, dur=0.42, checkpoint="cp1"):
    return IssueOccurrence(
        session_id=session, setup_checkpoint_id=checkpoint, lap_number=lap,
        track="fuji", layout_id="fuji__full", segment_id=seg, corner_phase=phase,
        issue_type=itype, issue_subtype=subtype, axle=axle,
        duration_s=dur, severity=sev, confidence=conf, throttle=0.9, gear=3,
    )


def _laps(session, n, classification="flying", checkpoint="cp1"):
    return [LapMeta(session_id=session, lap_number=i + 1, classification=classification,
                    valid=True, setup_checkpoint_id=checkpoint) for i in range(n)]


def _result_for(results, seg, phase="exit"):
    for r in results:
        if r.signature.segment_id == seg and r.signature.corner_phase == phase:
            return r
    return None


# --------------------------------------------------------------------------- #
# Fixture A — two bad laps at different corners → ISOLATED_ANOMALY
# --------------------------------------------------------------------------- #
def test_fixture_a_isolated_anomaly_different_corners():
    laps = _laps(1, 8)
    occs = [_occ(1, 2, "T3"), _occ(1, 5, "T6")]  # different corners, one lap each
    results = analyse_cross_lap(occs, laps)
    assert _result_for(results, "T3").classification is PersistenceClass.ISOLATED_ANOMALY
    assert _result_for(results, "T6").classification is PersistenceClass.ISOLATED_ANOMALY
    assert all(not r.eligible_for_setup for r in results)


# --------------------------------------------------------------------------- #
# Fixture B — same-corner wheelspin on 6/8 laps → PERSISTENT_PATTERN
# --------------------------------------------------------------------------- #
def test_fixture_b_persistent_pattern_same_corner():
    laps = _laps(1, 8)
    occs = [_occ(1, ln, "T3") for ln in (1, 2, 4, 5, 7, 8)]  # 6 of 8, same corner/phase/axle
    results = analyse_cross_lap(occs, laps)
    r = _result_for(results, "T3")
    assert r.classification is PersistenceClass.PERSISTENT_PATTERN
    assert r.affected_representative_laps == 6
    assert r.total_representative_laps == 8
    assert r.recurrence_pct == 0.75
    assert r.eligible_for_setup


# --------------------------------------------------------------------------- #
# Fixture F — same issue across two sessions → CROSS_SESSION_CONFIRMED
# --------------------------------------------------------------------------- #
def test_fixture_f_cross_session_confirmed():
    laps = _laps(1, 8) + _laps(2, 8)
    occs = ([_occ(1, ln, "T3") for ln in (1, 2, 4, 5, 7)] +
            [_occ(2, ln, "T3") for ln in (1, 3, 5, 6, 8)])
    results = analyse_cross_lap(occs, laps)
    r = _result_for(results, "T3")
    assert r.classification is PersistenceClass.CROSS_SESSION_CONFIRMED
    assert r.sessions == 2
    assert r.eligible_for_setup


# --------------------------------------------------------------------------- #
# Guards: poor laps / thin data / suppression never author a change
# --------------------------------------------------------------------------- #
def test_two_poor_laps_same_corner_is_not_setup_eligible():
    # Only 2 of 8 laps affected (25%) — below recurring. Emerging at most.
    laps = _laps(1, 8)
    occs = [_occ(1, 2, "T3"), _occ(1, 5, "T3")]
    r = _result_for(analyse_cross_lap(occs, laps), "T3")
    assert r.classification is PersistenceClass.EMERGING_PATTERN
    assert not r.eligible_for_setup


def test_low_sample_when_few_representative_laps():
    laps = _laps(1, 2)  # only 2 representative laps
    occs = [_occ(1, 1, "T3"), _occ(1, 2, "T3")]
    r = _result_for(analyse_cross_lap(occs, laps), "T3")
    assert r.classification is PersistenceClass.LOW_SAMPLE
    assert not r.eligible_for_setup


def test_occurrences_on_excluded_laps_do_not_count_and_are_visible():
    # 6 flying laps + 2 out/incident laps; slip only on the excluded laps.
    laps = _laps(1, 6) + [
        LapMeta(1, 7, classification="out", valid=True),
        LapMeta(1, 8, classification="incident", valid=True),
    ]
    occs = [_occ(1, 7, "T3"), _occ(1, 8, "T3")]  # both on non-representative laps
    results = analyse_cross_lap(occs, laps)
    # No signature reaches any pattern (no admissible representative occurrences).
    assert not any(r.eligible_for_setup for r in results)
    # Excluded laps are surfaced, not hidden.
    # (excluded list is attached to every result; when there are no results we still
    #  prove the classifier marks them non-representative.)
    from strategy.cross_lap_persistence import classify_laps
    lc = classify_laps(laps)
    assert lc[(1, 7)] == (False, "out lap")
    assert lc[(1, 8)] == (False, "incident on lap")


def test_suppressed_occurrences_are_inadmissible():
    laps = _laps(1, 8)
    occs = [IssueOccurrence(
        session_id=1, setup_checkpoint_id="cp1", lap_number=ln, track="fuji",
        layout_id="fuji__full", segment_id="T3", corner_phase="exit",
        issue_type="wheelspin", issue_subtype="power_wheelspin", axle="rear",
        confidence=0.7, severity=0.4, duration_s=0.3,
        exclusion_reason="kerb_unload",  # suppressed
    ) for ln in (1, 2, 4, 5, 7, 8)]
    results = analyse_cross_lap(occs, laps)
    assert results == [] or all(not r.eligible_for_setup for r in results)


def test_low_confidence_occurrences_excluded_by_threshold():
    laps = _laps(1, 8)
    occs = [_occ(1, ln, "T3", conf=0.2) for ln in (1, 2, 4, 5, 7, 8)]  # below min_confidence
    results = analyse_cross_lap(occs, laps)
    assert not any(r.eligible_for_setup for r in results)


def test_recurring_between_50_and_60_percent():
    # 4 of 8 laps = 50% → RECURRING (not yet persistent).
    laps = _laps(1, 8)
    occs = [_occ(1, ln, "T3") for ln in (1, 3, 5, 7)]
    r = _result_for(analyse_cross_lap(occs, laps), "T3")
    assert r.classification is PersistenceClass.RECURRING_PATTERN
    assert not r.eligible_for_setup  # recurring still needs correlation, not eligible alone


def test_setup_eligible_set_membership():
    assert PersistenceClass.PERSISTENT_PATTERN in SETUP_ELIGIBLE
    assert PersistenceClass.CROSS_SESSION_CONFIRMED in SETUP_ELIGIBLE
    assert PersistenceClass.RECURRING_PATTERN not in SETUP_ELIGIBLE
    assert PersistenceClass.ISOLATED_ANOMALY not in SETUP_ELIGIBLE


def test_deterministic_repeatable():
    laps = _laps(1, 8)
    occs = [_occ(1, ln, "T3") for ln in (1, 2, 4, 5, 7, 8)]
    assert analyse_cross_lap(occs, laps) == analyse_cross_lap(occs, laps)


def test_thresholds_are_configurable():
    laps = _laps(1, 8)
    occs = [_occ(1, ln, "T3") for ln in (1, 3, 5, 7)]  # 50%
    strict = RecurrenceThresholds(recurring_pct=0.7, persistent_pct=0.8)
    r = _result_for(analyse_cross_lap(occs, laps, strict), "T3")
    assert r.classification is PersistenceClass.EMERGING_PATTERN  # 50% < 70% strict recurring
