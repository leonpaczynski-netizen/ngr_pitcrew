"""Phase 48 — Event Preparation Cycle identity, timeline and flexible-duration tests.

Covers task test items: preparation-cycle identity (4), duration (5), activity timeline (6),
activity ordering (7), one-evening (12) and monthly (11) profiles, and the deterministic-rendering /
countdown-exclusion invariants (14, 38).
"""
from __future__ import annotations

import pytest

from strategy.event_preparation_cycle import (
    EventPreparationCycleIdentity, PreparationActivity, PreparationActivityType,
    PreparationActivityState, OfficialSession, OfficialSessionType, PreparationCycleState,
    PreparationPhase, build_event_preparation_cycle, build_preparation_timeline,
    multiweek_profile, single_evening_profile, endurance_profile, multi_race_profile,
    resolve_profile, PHASE_ORDER,
)


def _identity(**kw):
    base = dict(cycle_id="cyc-1", event_name="Porsche Cup R3", series="NGR Porsche Cup",
                round_label="Round 3", driver_id="leon", car="Porsche 911 RSR (992)",
                track="Fuji International Speedway", layout="Full Course",
                prep_open_date="2026-06-01", official_quali_date="2026-06-21",
                official_race_date="2026-06-21", format_profile_id="multiweek",
                disciplines=("race", "qualifying"))
    base.update(kw)
    return EventPreparationCycleIdentity(**base)


def _act(aid, atype, order, **kw):
    return PreparationActivity(activity_id=aid, activity_type=atype, order_index=order, **kw)


def _porsche_cup_activities():
    """The monthly Porsche Cup profile from the task (week 1-3 + race period). Not hard-coded in the
    library — supplied here as test/UAT data."""
    T = PreparationActivityType
    P = PreparationPhase
    return [
        _act("w1-brief", T.EVENT_BRIEFING, 0, title="Sporting briefing", planned_date="2026-06-01",
             phase=P.INITIAL_BRIEFING),
        _act("w1-base1", T.BASELINE_PRACTICE, 1, title="Baseline Practice 1", planned_date="2026-06-02",
             phase=P.BASELINE_ESTABLISHMENT),
        _act("w1-exp1", T.SETUP_EXPERIMENT, 2, title="Setup experiment 1", planned_date="2026-06-04",
             phase=P.SETUP_DEVELOPMENT),
        _act("w1-base2", T.BASELINE_PRACTICE, 3, title="Baseline Practice 2", planned_date="2026-06-05",
             phase=P.BASELINE_ESTABLISHMENT),
        _act("w2-exp2", T.SETUP_EXPERIMENT, 4, title="Setup experiment 2", planned_date="2026-06-08",
             phase=P.SETUP_DEVELOPMENT),
        _act("w2-coach", T.COACHING_RUN, 5, title="Driver coaching run", planned_date="2026-06-10",
             phase=P.DRIVER_DEVELOPMENT, optional=True),
        _act("w2-tyre", T.TYRE_TEST, 6, title="Tyre and fuel evaluation", planned_date="2026-06-11",
             phase=P.TYRE_AND_FUEL_MODELLING),
        _act("w2-long", T.LONG_RACE_RUN, 7, title="Long race run", planned_date="2026-06-13",
             phase=P.RACE_SIMULATION),
        _act("w3-quali", T.QUALIFYING_SIMULATION, 8, title="Qualifying simulation",
             planned_date="2026-06-15", phase=P.QUALIFYING_DEVELOPMENT),
        _act("w3-race", T.STRATEGY_VALIDATION_RUN, 9, title="Race simulation", planned_date="2026-06-16",
             phase=P.RACE_SIMULATION),
        _act("w3-cmp", T.FINAL_SETUP_CONFIRMATION, 10, title="Final setup comparison",
             planned_date="2026-06-18", phase=P.ENGINEERING_CONVERGENCE),
        _act("race-q", T.QUALIFYING, 11, title="Qualifying", planned_date="2026-06-21",
             phase=P.OFFICIAL_EVENT_ACTIVE),
        _act("race-r", T.RACE, 12, title="Race", planned_date="2026-06-21",
             phase=P.OFFICIAL_EVENT_ACTIVE),
        _act("race-d", T.POST_RACE_DEBRIEF, 13, title="Post-race debrief", planned_date="2026-06-21",
             phase=P.POST_RACE_REVIEW),
    ]


def _officials():
    return [OfficialSession(OfficialSessionType.QUALIFYING, "2026-06-21", "18:00", "Qualifying"),
            OfficialSession(OfficialSessionType.RACE, "2026-06-21", "18:30", "Race")]


# --- identity -------------------------------------------------------------

def test_identity_fingerprint_is_deterministic_and_field_sensitive():
    a = _identity()
    b = _identity()
    assert a.fingerprint() == b.fingerprint()
    # a material identity change (round) changes the fingerprint
    assert _identity(round_label="Round 4").fingerprint() != a.fingerprint()
    # discipline order does not matter (canonicalised)
    assert _identity(disciplines=("qualifying", "race")).fingerprint() == a.fingerprint()


def test_cycle_binds_every_activity_to_one_identity():
    idn = _identity()
    cyc = build_event_preparation_cycle(idn, _porsche_cup_activities(), official_sessions=_officials())
    assert cyc.identity.cycle_id == "cyc-1"
    assert len(cyc.activities) == 14
    # all activities are grouped under this one cycle (no fragmentation)
    assert cyc.identity.event_name == "Porsche Cup R3"


# --- flexible duration -----------------------------------------------------

def test_month_long_and_one_evening_spans_are_both_valid():
    month = build_event_preparation_cycle(_identity(), _porsche_cup_activities(),
                                          official_sessions=_officials())
    assert month.preparation_span_days == 20  # 2026-06-01 -> 2026-06-21

    evening_id = _identity(prep_open_date="2026-06-21", official_race_date="2026-06-21",
                           format_profile_id="single_evening")
    T = PreparationActivityType
    evening_acts = [
        _act("b", T.EVENT_BRIEFING, 0, planned_date="2026-06-21"),
        _act("p", T.FREE_PRACTICE, 1, planned_date="2026-06-21"),
        _act("q", T.QUALIFYING, 2, planned_date="2026-06-21"),
        _act("r", T.RACE, 3, planned_date="2026-06-21"),
        _act("d", T.POST_RACE_DEBRIEF, 4, planned_date="2026-06-21"),
    ]
    evening = build_event_preparation_cycle(evening_id, evening_acts,
                                            profile=single_evening_profile())
    assert evening.preparation_span_days == 0  # same-day is valid, not an error


def test_long_gap_does_not_auto_complete_or_abandon():
    # ten days pass between activities; no explicit terminal state -> cycle stays ACTIVE
    idn = _identity()
    T = PreparationActivityType
    acts = [
        _act("a1", T.BASELINE_PRACTICE, 0, planned_date="2026-06-02",
             state=PreparationActivityState.COMPLETED),
        _act("a2", T.SETUP_EXPERIMENT, 1, planned_date="2026-06-12"),  # 10-day gap
    ]
    cyc = build_event_preparation_cycle(idn, acts, now_date="2026-06-30")
    assert cyc.state == PreparationCycleState.ACTIVE
    assert cyc.next_activity_id == "a2"  # still shows the next objective


def test_missing_dates_do_not_raise():
    idn = _identity(prep_open_date="", official_race_date="")
    acts = [_act("x", PreparationActivityType.BASELINE_PRACTICE, 0)]  # no planned_date
    cyc = build_event_preparation_cycle(idn, acts)
    assert cyc.preparation_span_days is None
    assert cyc.days_until_race is None


# --- timeline & ordering ---------------------------------------------------

def test_timeline_is_date_ordered_and_shuffle_stable():
    idn = _identity()
    acts = _porsche_cup_activities()
    tl_a = build_preparation_timeline(idn, multiweek_profile(), _officials(), acts)
    tl_b = build_preparation_timeline(idn, multiweek_profile(), _officials(), list(reversed(acts)))
    assert tl_a.fingerprint() == tl_b.fingerprint()
    dates = [m.milestone_date for m in tl_a.milestones if m.milestone_date]
    assert dates == sorted(dates)  # chronological


def test_activity_order_is_by_order_index_then_id():
    idn = _identity()
    T = PreparationActivityType
    acts = [_act("z", T.SETUP_EXPERIMENT, 2), _act("a", T.BASELINE_PRACTICE, 1),
            _act("m", T.COACHING_RUN, 1)]
    cyc = build_event_preparation_cycle(idn, acts)
    assert [a.activity_id for a in cyc.activities] == ["a", "m", "z"]


def test_undated_activities_keep_order_after_dated():
    idn = _identity()
    T = PreparationActivityType
    acts = [_act("dated", T.BASELINE_PRACTICE, 0, title="dated", planned_date="2026-06-05"),
            _act("undated", T.SETUP_EXPERIMENT, 1, title="undated")]
    tl = build_preparation_timeline(idn, multiweek_profile(), (), acts)
    names = [m.name for m in tl.milestones]
    assert names.index("dated") < names.index("undated")


# --- profiles: skipped phases explicit ------------------------------------

def test_single_evening_profile_skips_development_phases_explicitly():
    prof = single_evening_profile()
    assert PreparationPhase.SETUP_DEVELOPMENT in prof.skipped_phases
    assert PreparationPhase.STRATEGY_FINALISATION in prof.skipped_phases
    # nothing silently absent: included + skipped covers every prep phase
    covered = set(prof.included_phases) | set(prof.skipped_phases)
    assert set(p for p in PHASE_ORDER if p != PreparationPhase.COMPLETE) <= covered


def test_multiweek_profile_uses_all_phases():
    prof = multiweek_profile()
    assert not prof.skipped_phases
    assert PreparationPhase.SETUP_DEVELOPMENT in prof.included_phases


def test_multi_race_profile_expects_two_races():
    prof = multi_race_profile()
    races = [s for s in prof.official_sessions_expected if s == OfficialSessionType.RACE]
    assert len(races) == 2


def test_endurance_profile_has_setup_restriction_after_lock():
    prof = endurance_profile(setup_lock_date="2026-06-19")
    assert prof.setup_restriction_after_lock is True
    assert any(d.kind == "setup_lock" and d.mandatory for d in prof.deadlines)


def test_resolve_profile_defaults_to_multiweek_for_unknown():
    assert resolve_profile("nonsense").profile_id == "multiweek"


# --- determinism: countdown excluded from fingerprint ---------------------

def test_days_until_race_is_display_only_and_excluded_from_fingerprint():
    idn = _identity()
    acts = _porsche_cup_activities()
    early = build_event_preparation_cycle(idn, acts, official_sessions=_officials(),
                                          now_date="2026-06-01")
    late = build_event_preparation_cycle(idn, acts, official_sessions=_officials(),
                                         now_date="2026-06-20")
    assert early.days_until_race == 20 and late.days_until_race == 1
    # different countdown, identical semantic content -> identical fingerprint
    assert early.fingerprint == late.fingerprint


def test_cycle_fingerprint_changes_when_activity_status_changes():
    idn = _identity()
    acts = _porsche_cup_activities()
    base = build_event_preparation_cycle(idn, acts, official_sessions=_officials())
    changed = list(acts)
    changed[1] = PreparationActivity(activity_id="w1-base1",
                                     activity_type=PreparationActivityType.BASELINE_PRACTICE,
                                     order_index=1, state=PreparationActivityState.COMPLETED)
    after = build_event_preparation_cycle(idn, changed, official_sessions=_officials())
    assert base.fingerprint != after.fingerprint  # status is semantic
