"""The app's own longitudinal tyre model: observations, gates and refusals.

GT7 broadcasts no tyre wear channel, so the model measures the *effect* of tyre
life from a friction-envelope percentile of laps he has already driven. What
these tests guard is not the arithmetic — that is checked once against a known
trace — but the four things that would let a wrong number reach a live call:

* the migration stays additive, and `laps` is never rebuilt;
* the frames gate and the push-lap filter exclude what they should, and say why;
* `yaw_source` cannot be null and a fit **refuses** to pool across it;
* a gate opens at the sample count it claims to and not before, and a thin
  scope says "not yet" rather than producing a coefficient with a straight face.

Synthetic data throughout, except one clearly-marked integration check against
the real archive that skips cleanly when it is absent.
"""
from __future__ import annotations

import math
import sqlite3
from pathlib import Path

import pytest

from pitcrew.analysis.corner_model import Corner, CornerModel
from pitcrew.analysis.grip import (
    APEX_SD_LIMIT_FRACTION,
    DERIVATION_VERSION,
    YAW_FROM_PACKET,
    YAW_FROM_PATH,
    LapTrace,
    SessionContext,
    apex_anchors,
    frames_gate,
    lap_eligibility,
    observation_rows,
    trace_lap,
    yaw_source_for,
)
from pitcrew.analysis.tyre_model import (
    STAGE0_LINE,
    STAGE2_MIN_PUSH_LAPS_PER_STINT,
    STAGE2_MIN_STINTS,
    SETTLED_LAP_IN_STINT,
    STAGE2_MAX_P,
    STAGE2_MIN_TOTAL_PUSH_LAPS,
    PoolingRefused,
    Scope,
    ScopeEvidence,
    consecutive_lap_cv,
    fit_archive,
    fit_degradation,
    gate_stage1_warmup,
    gate_stage2_degradation,
    gate_stage3_conserve,
    group_by_scope,
    may_i_say,
    ols,
    prior_scope_key,
    student_t_p,
    priors_for_scope,
    refuse_to_pool,
)
from pitcrew.store.db import DEFAULT_DB_PATH, Store
from pitcrew.store.schema import SCHEMA_VERSION

HZ = 60.0


# --------------------------------------------------------------- the schema



def _snapshot_of_the_archive(copied) -> None:
    """A faithful copy of the live archive, read without writing to it.

    **Not `shutil.copy`**, which copied the `.db` alone. The archive runs in
    WAL mode, so the newest committed rows can still be in `pitcrew.db-wal`,
    and a copy without it quietly tests yesterday's data (critic, 19 Sep; the
    memory note on copying the DB says the same). SQLite's backup API reads
    through the WAL, and the source is opened `mode=ro`, so the live file is
    never opened for writing - which the suite's tripwire would refuse anyway.
    """
    import sqlite3

    source = sqlite3.connect(
        f"file:{Path(DEFAULT_DB_PATH).resolve().as_posix()}?mode=ro", uri=True)
    target = sqlite3.connect(str(copied))
    try:
        source.backup(target)
    finally:
        target.close()
        source.close()

def test_the_migration_is_additive_and_leaves_laps_and_their_frames_alone(
        tmp_path, event_id, store):
    """v6 adds two tables. It must not touch `laps`, which `lap_frames`
    cascades off — rebuilding it would take every recorded blob with it."""
    session = store.start_session(event_id, "practice")
    lap_id = _store_lap(store, session, lap_num=1)
    before = store._query("PRAGMA table_info(laps)")

    reopened = Store(store.path)
    try:
        assert reopened._query("PRAGMA user_version")[0][0] == SCHEMA_VERSION
        assert [dict(r) for r in reopened._query("PRAGMA table_info(laps)")] == \
               [dict(r) for r in before]
        assert reopened.get_lap_frames(lap_id) is not None
    finally:
        reopened.close()


def test_reopening_twice_writes_no_second_copy_of_an_observation(store, event_id):
    session = store.start_session(event_id, "practice")
    lap_id = _store_lap(store, session, lap_num=1)
    row = _observation(lap_id, session)

    assert store.write_grip_observations([row]) == 1
    assert store.write_grip_observations([row]) == 1
    assert len(store.list_grip_observations()) == 1

    bumped = {**row, "derivation_version": DERIVATION_VERSION + 1}
    store.write_grip_observations([bumped])
    # A new derivation version is a new row, not a replacement: a fitted model
    # has to keep resolving the observations it was actually fitted on.
    assert len(store.list_grip_observations()) == 2
    assert store.grip_derivation_versions() == [DERIVATION_VERSION,
                                                DERIVATION_VERSION + 1]


def test_an_observation_cannot_be_written_without_a_yaw_source(store, event_id):
    session = store.start_session(event_id, "practice")
    lap_id = _store_lap(store, session, lap_num=1)
    row = {**_observation(lap_id, session), "yaw_source": None}
    with pytest.raises(sqlite3.IntegrityError):
        store.write_grip_observations([row])


def test_a_misspelled_covariate_is_refused_rather_than_dropped(store, event_id):
    session = store.start_session(event_id, "practice")
    lap_id = _store_lap(store, session, lap_num=1)
    row = {**_observation(lap_id, session), "temp_rear_celsius": 82.0}
    with pytest.raises(ValueError, match="temp_rear_celsius"):
        store.write_grip_observations([row])


# ------------------------------------------------------------- yaw_source


def test_yaw_source_follows_the_blob_schema_and_never_guesses():
    assert yaw_source_for(1) == YAW_FROM_PATH
    assert yaw_source_for(2) == YAW_FROM_PACKET
    # No stamp at all is a v1 blob; that is what `decode_frames` assumes and
    # the two must not disagree.
    assert yaw_source_for(None) == YAW_FROM_PATH


def test_a_fit_refuses_to_pool_across_yaw_sources():
    rows = [_lap_row(1, grip=1.85, yaw_source=YAW_FROM_PATH),
            _lap_row(2, grip=1.91, yaw_source=YAW_FROM_PACKET)]
    with pytest.raises(PoolingRefused, match="3-4%"):
        refuse_to_pool(rows)


def test_scopes_split_on_yaw_source_so_a_mixed_archive_fits_separately():
    rows = [_lap_row(n, grip=1.85, yaw_source=YAW_FROM_PATH) for n in range(1, 5)]
    rows += [_lap_row(n, grip=1.91, yaw_source=YAW_FROM_PACKET, session=2)
             for n in range(1, 5)]
    scopes = group_by_scope(rows)
    assert {s.yaw_source for s in scopes} == {YAW_FROM_PATH, YAW_FROM_PACKET}
    for evidence in scopes.values():
        assert refuse_to_pool(evidence.rows)          # each side is single-source


# ---------------------------------------------------- the gate and the filter


@pytest.mark.parametrize("frames, passes", [
    (110 * 60, True),        # a real 110 s lap: frames account for the time
    (int(110 * 60 * 1.14), False),   # the lobby-join phantom, +14 %
    (int(110 * 60 * 0.90), False),
    (int(110 * 60 * 1.019), True),   # inside the 2 % tolerance
])
def test_the_frames_gate_separates_a_driven_lap_from_a_phantom(frames, passes):
    ok, error = frames_gate(110_000, frames, HZ)
    assert ok is passes
    assert error is not None


def test_the_frames_gate_says_unanswerable_rather_than_failed():
    ok, error = frames_gate(None, 6600, HZ)
    assert ok is False and error is None


@pytest.mark.parametrize("lap, reason", [
    ({"lap_time_ms": 110_000, "crawl_s": 0.0, "spin_s": 0.0,
      "off_track_s": 0.0}, None),
    ({"lap_time_ms": 110_000, "excluded": 1, "crawl_s": 0.0, "spin_s": 0.0,
      "off_track_s": 0.0}, "excluded"),
    ({"lap_time_ms": 110_000, "spin_s": 1.2, "crawl_s": 0.0,
      "off_track_s": 0.0}, "spin"),
    ({"lap_time_ms": 110_000, "crawl_s": 4.0, "spin_s": 0.0,
      "off_track_s": 0.0}, "crawl"),
    ({"lap_time_ms": 110_000, "crawl_s": 0.0, "spin_s": 0.0,
      "off_track_s": 6.0}, "off-track"),
    ({"lap_time_ms": 110_000, "standing_start_ms": 900, "crawl_s": 0.0,
      "spin_s": 0.0, "off_track_s": 0.0}, "standing-start"),
    # A lap driven under the app's own fuel-saving instruction measures the
    # radio call, not the car.
    ({"lap_time_ms": 110_000, "short_shift_rpm": 500.0, "crawl_s": 0.0,
      "spin_s": 0.0, "off_track_s": 0.0}, "save-lap-short-shift"),
    # ...but a lap recorded on the normal threshold is not a save lap, and a
    # lap recorded before the column existed is not cleared by it either.
    ({"lap_time_ms": 110_000, "short_shift_rpm": 0.0, "crawl_s": 0.0,
      "spin_s": 0.0, "off_track_s": 0.0}, None),
])
def test_the_push_lap_filter_excludes_what_it_should_and_says_why(lap, reason):
    verdict = lap_eligibility(lap, frame_count=int(110 * HZ), sample_hz=HZ,
                              is_pit_lap=False, is_out_lap=False)
    assert verdict.reason == reason
    assert verdict.counts is (reason is None)


def test_an_unmeasured_incident_is_not_a_clean_lap():
    """Null is not zero. A lap whose frames were never read for incidents has
    not been cleared of them, and a detector that reads the first as the second
    silently passes every lap it cannot see."""
    verdict = lap_eligibility({"lap_time_ms": 110_000, "crawl_s": None,
                               "spin_s": None, "off_track_s": None},
                              frame_count=int(110 * HZ), sample_hz=HZ,
                              is_pit_lap=False, is_out_lap=False)
    assert verdict.counts is False
    assert verdict.reason == "crawl-unmeasured"


def test_a_pit_lap_and_its_out_lap_are_both_kept_out_of_the_fit():
    lap = {"lap_time_ms": 110_000, "crawl_s": 0.0, "spin_s": 0.0,
           "off_track_s": 0.0}
    assert lap_eligibility(lap, frame_count=6600, sample_hz=HZ,
                           is_pit_lap=True, is_out_lap=False).reason == "pit-lap"
    assert lap_eligibility(lap, frame_count=6600, sample_hz=HZ,
                           is_pit_lap=False, is_out_lap=True).reason == "out-lap"


# ------------------------------------------------------------- the observable


def test_the_observable_is_a_percentile_of_the_combined_vector_not_its_peak():
    """One kerb strike must not own the lap. `comb_max` has a measured CV of
    26-28 % for exactly this reason."""
    frames = _synthetic_lap(lateral=1.5)
    frames[2000]["lat_g"] = 9.0            # one frame of nonsense
    trace = trace_lap(frames, HZ, lap_id=1, session_id=1, lap_num=1,
                      frame_schema_version=2)
    rows = observation_rows(trace, _lap(1), _context(), None, {})
    assert rows[0]["grip_stat"] == "comb_p95"
    assert rows[0]["grip_g"] == pytest.approx(1.5, abs=0.02)


def test_frames_below_fifteen_metres_per_second_do_not_reach_the_observable():
    frames = _synthetic_lap(lateral=1.5)
    for frame in frames[:1000]:
        frame["speed_kph"] = 20.0          # pit lane, and a huge apparent lat_g
        frame["lat_g"] = 4.0
    trace = trace_lap(frames, HZ, lap_id=1, session_id=1, lap_num=1,
                      frame_schema_version=2)
    rows = observation_rows(trace, _lap(1), _context(), None, {})
    assert rows[0]["grip_g"] == pytest.approx(1.5, abs=0.02)


def test_an_unmeasured_channel_comes_back_null_and_never_zero():
    frames = _synthetic_lap(lateral=1.2)
    for frame in frames:
        frame["temp_fl"] = frame["temp_fr"] = None
        frame.pop("surf_fl", None)
        frame.pop("surf_fr", None)
        frame.pop("surf_rl", None)
        frame.pop("surf_rr", None)
    trace = trace_lap(frames, HZ, lap_id=1, session_id=1, lap_num=1,
                      frame_schema_version=2)
    row = observation_rows(trace, _lap(1), _context(), None, {})[0]
    assert row["temp_front_c"] is None
    assert row["kerb_frac"] is None            # 'A'/'B' offer no surface channel
    assert row["temp_rear_c"] is not None


def test_every_row_carries_its_sample_count_and_names_its_derivation():
    frames = _synthetic_lap(lateral=1.4)
    trace = trace_lap(frames, HZ, lap_id=1, session_id=1, lap_num=1,
                      frame_schema_version=1)
    model = CornerModel("m", 3, "auto-segment", 4000.0,
                        (Corner("T1", "Turn 1", 900.0, 1000.0, 1100.0),))
    rows = observation_rows(trace, _lap(1), _context(), model, {})
    assert {r["grip_stat"] for r in rows} == {"comb_p95", "comb_p90"}
    assert all(r["sample_frames"] > 0 for r in rows)
    assert all(r["yaw_source"] == YAW_FROM_PATH for r in rows)
    assert all(r["derivation_version"] == DERIVATION_VERSION for r in rows)
    corner = [r for r in rows if r["unit_kind"] == "CORNER"][0]
    assert corner["corner_model_version"] == 3


# ------------------------------------------------------------ apex anchoring


def test_the_corner_window_moves_to_the_apex_he_actually_drives():
    corner = Corner("T1", "Turn 1", 900.0, 1000.0, 1100.0)
    model = CornerModel("m", 1, "auto-segment", 4000.0, (corner,))
    traces = [_trace_with_apex_at(1040.0 + n * 0.5, index=n) for n in range(12)]
    anchor = apex_anchors(model, traces)["T1"]
    assert anchor.apex_m_observed == pytest.approx(1042.75, abs=1.0)
    assert anchor.offset_m == pytest.approx(42.75, abs=1.0)
    assert anchor.stable is True


def test_a_corner_whose_apex_will_not_hold_still_is_marked_not_dropped():
    corner = Corner("T1", "Turn 1", 900.0, 1000.0, 1100.0)   # half-width 100 m
    model = CornerModel("m", 1, "auto-segment", 4000.0, (corner,))
    # Scatter well past a quarter of the half-width.
    traces = [_trace_with_apex_at(940.0 + (n % 2) * 100.0, index=n)
              for n in range(12)]
    anchor = apex_anchors(model, traces)["T1"]
    assert anchor.sd_m > APEX_SD_LIMIT_FRACTION * anchor.half_width_m
    assert anchor.stable is False

    trace = _trace_with_apex_at(1000.0, index=99)
    lap = _lap(1, lap_time_ms=int(round(1000 * trace.frame_count / HZ)))
    rows = observation_rows(trace, lap, _context(), model, {"T1": anchor})
    corner_row = [r for r in rows if r["unit_kind"] == "CORNER"][0]
    assert corner_row["counts_toward_fit"] == 0
    assert corner_row["exclusion_reason"] == "corner-identity-unstable"
    # Written, not discarded: "we cannot tell which corner this was" is a fact.
    assert corner_row["grip_g"] is not None


def test_too_few_laps_leaves_the_window_where_the_model_put_it():
    corner = Corner("T1", "Turn 1", 900.0, 1000.0, 1100.0)
    model = CornerModel("m", 1, "auto-segment", 4000.0, (corner,))
    anchor = apex_anchors(model, [_trace_with_apex_at(1040.0, index=n)
                                  for n in range(3)])["T1"]
    assert anchor.apex_m_observed is None
    assert anchor.offset_m == 0.0
    assert anchor.laps == 3


# ------------------------------------------------------------- the fitting


def test_ols_charges_a_degree_of_freedom_for_every_group_mean():
    """A within-group fit that forgets the group means comes out looking about
    twice as significant as it is."""
    xs = [float(n) for n in range(10)]
    ys = [2.0 - 0.01 * x for x in xs]
    honest = ols(xs, ys, dof_penalty=6)
    naive = ols(xs, ys, dof_penalty=2)
    assert honest.slope == pytest.approx(-0.01)
    assert honest.se is not None and naive.se is not None
    assert honest.se >= naive.se


def test_a_slope_with_no_residual_degrees_of_freedom_reports_none_not_zero():
    fit = ols([0.0, 1.0], [1.9, 1.8])
    assert fit.slope == pytest.approx(-0.1)
    assert fit.t is None                # untestable is not "not significant"


def test_the_degradation_gate_needs_three_contributing_stints():
    """Three stints is the clause doing the real work. Within one stint fuel,
    elapsed time and wear are the same variable at r = -1.000, so no single
    stint separates a degradation trend from a fuel-load artefact at any
    length."""
    thin = _evidence(stints=2, laps_each=14, slope=-0.004)
    verdict = gate_stage2_degradation(thin, fit_degradation(thin))
    assert verdict.met is False
    assert any("2 contributing stint(s)" in why for why in verdict.failures)
    assert verdict.says.startswith("Not yet")


def test_a_stint_too_short_to_carry_a_trend_does_not_contribute():
    """A stint contributes on its SETTLED laps, so a short one drops out even
    though its raw lap count looks adequate."""
    short = _evidence(stints=6, laps_each=SETTLED_LAP_IN_STINT
                      + STAGE2_MIN_PUSH_LAPS_PER_STINT - 1, slope=-0.004,
                      fresh=True)
    assert short.contributing_stints == {}
    verdict = gate_stage2_degradation(short, fit_degradation(short))
    assert verdict.met is False
    assert any("0 contributing stint(s)" in why for why in verdict.failures)


def test_the_warm_up_laps_are_out_of_the_degradation_fit():
    """A warm-up is a rising process; pooled with a declining one it produces a
    slope that describes neither. The two fits used to disagree about this."""
    evidence = _evidence(stints=3, laps_each=10, slope=-0.004, fresh=True)
    for laps in evidence.contributing_stints.values():
        assert min(r["lap_in_stint"] for r in laps) >= SETTLED_LAP_IN_STINT
    assert all(r["lap_in_stint"] >= SETTLED_LAP_IN_STINT
               for r in evidence.settled())


def test_three_short_stints_still_need_the_total_lap_count():
    """The per-stint count is a floor, not the evidence condition. Three stints
    of five settled laps is fifteen observations, one short of what a 1 % effect
    needs at the measured CV, and the total clause says so out loud."""
    sparse = _evidence(stints=3,
                       laps_each=SETTLED_LAP_IN_STINT
                       + STAGE2_MIN_PUSH_LAPS_PER_STINT, slope=-0.004,
                       fresh=True)
    assert sparse.contributing_laps == 15
    verdict = gate_stage2_degradation(sparse, fit_degradation(sparse))
    assert verdict.met is False
    assert any(f"15 settled push lap(s)" in why for why in verdict.failures)


def test_the_degradation_gate_opens_on_enough_stints_and_enough_laps():
    enough = _evidence(stints=STAGE2_MIN_STINTS, laps_each=9, slope=-0.004)
    assert enough.contributing_laps >= STAGE2_MIN_TOTAL_PUSH_LAPS
    opened = gate_stage2_degradation(enough, fit_degradation(enough))
    assert opened.met is True
    # Direction only. A percentage here would be a magnitude the percentile
    # band cannot carry.
    assert "going away" in opened.says
    assert "per cent" not in opened.says
    assert "measured" not in opened.says
    assert opened.asks_for == "tyre-gauge-reading"


def test_laps_spread_unevenly_across_stints_no_longer_shut_the_gate():
    """**The regression this gate change exists for.** Monza / Porsche / RH
    fits -0.00415 g/lap at se 0.00065, t = -6.42, over 40 push laps and five
    stints - and the old "8 push laps in each" clause rejected it, purely
    because those 40 laps fell 10, 9, 7, 7, 7 instead of evenly. The evidence
    was never thin; the proxy was wrong."""
    rows = []
    for stint, laps in enumerate((13, 12, 10, 10, 10)):
        for lap in range(laps):
            rows.append(_lap_row(lap + 1, grip=1.871 - 0.004 * lap
                                 + (0.0009 if lap % 3 else -0.0007),
                                 session=stint + 1, stint=f"{stint + 1}:0"))
    evidence = ScopeEvidence.build(rows)
    assert len(evidence.contributing_stints) == 5
    verdict = gate_stage2_degradation(evidence, fit_degradation(evidence))
    assert verdict.met is True


def test_long_enough_stints_that_show_no_trend_keep_the_gate_shut():
    """Sample count is necessary and not sufficient. A flat scope has nothing
    to say and must say that, rather than reporting a slope of nearly zero."""
    flat = _evidence(stints=4, laps_each=10, slope=0.0)
    verdict = gate_stage2_degradation(flat, fit_degradation(flat))
    assert verdict.met is False
    assert any("p = " in why or "RISING" in why or "disagree in sign" in why
               for why in verdict.failures)


def test_a_rising_trend_is_never_announced_as_a_loss():
    """**C-1, and it was one Yas session away from shipping.**

    Nothing in the gate required the slope to be negative: it tested `abs(t)`
    and then formatted `abs(slope)` into "Grip's down". A scope whose own fit
    says grip is RISING would have announced a loss. Yas / Shelby / RS already
    fits +0.0109 g/lap at t = +2.68 and was held out only by its stint count.
    """
    rising = _evidence(stints=4, laps_each=10, slope=+0.006)
    fit = fit_degradation(rising)
    assert fit["grip_g_per_lap"] > 0
    assert abs(fit["t"]) > 3.0                 # it WOULD clear a |t| bar
    verdict = gate_stage2_degradation(rising, fit)
    assert verdict.met is False
    assert any("RISING" in why for why in verdict.failures)
    assert "down" not in verdict.says
    assert "going away" not in verdict.says


def test_stints_that_disagree_in_sign_do_not_speak():
    """A trend that reverses between stints is not this car's tyre. Monza is
    5 of 5 negative, so this clause costs nothing today and closes the case
    where one long stint drags a mixed population negative."""
    rows = []
    for stint, slope in enumerate((-0.010, -0.009, +0.008, -0.008)):
        for lap in range(10):
            rows.append(_lap_row(lap + 1, grip=1.87 + slope * lap
                                 + (0.0006 if lap % 3 else -0.0004),
                                 session=stint + 1, stint=f"{stint + 1}:0"))
    evidence = ScopeEvidence.build(rows)
    fit = fit_degradation(evidence)
    assert fit["grip_g_per_lap"] < 0           # the mean still points down
    verdict = gate_stage2_degradation(evidence, fit)
    assert verdict.met is False
    assert any("disagree in sign" in why for why in verdict.failures)


def test_the_gate_is_judged_on_the_between_stint_estimator():
    """**M-3.** Laps inside a stint are not independent draws — fuel, heat and
    track state all drift smoothly through one — so a pooled within-stint t
    is miscalibrated in the dangerous direction. The gate reads the mean of the
    per-stint slopes at df = stints - 1."""
    evidence = _evidence(stints=4, laps_each=10, slope=-0.004)
    fit = fit_degradation(evidence)
    assert fit["estimator"].startswith("between-stint")
    assert fit["dof"] == 3
    assert fit["p"] == pytest.approx(
        student_t_p(fit["t"], fit["dof"]), rel=1e-9)
    # The pooled figure is still reported — it is just not what decides.
    # (Which of the two is larger depends on how alike the stints are, so no
    # assertion is made about that; what matters is that they are separate and
    # the gate reads the between-stint one.)
    assert fit["pooled_within_stint"]["t"] is not None
    assert fit["pooled_within_stint"]["t"] != fit["t"]
    verdict = gate_stage2_degradation(evidence, fit)
    assert verdict.requirements["p_two_sided"]["required"] == STAGE2_MAX_P


def test_the_conserve_gate_is_shut_and_names_the_gauge_as_the_blocker():
    evidence = _evidence(stints=4, laps_each=10, slope=-0.004)
    verdict = gate_stage3_conserve(evidence)
    assert verdict.met is False
    assert any("gauge readings" in why for why in verdict.failures)
    # It must not be gated on the external 88/90/93 figure.
    assert any("88/90/93" in why for why in verdict.failures)


def test_a_thin_scope_reports_not_yet_rather_than_a_coefficient():
    rows = [_lap_row(n, grip=1.85 - 0.004 * n) for n in range(1, 4)]
    result = fit_archive(rows)
    degradation = [m for m in result["models"]
                   if m["model_kind"] == "degradation"][0]
    assert degradation["speakable"] == 0
    assert degradation["confidence"] in {"none", "low"}
    assert degradation["gate"]["failures"]
    blocked = result["not_yet_supported"][0]["blocked"]
    assert {b["stage"] for b in blocked} >= {1, 2, 3, 4, 5}


def test_every_fitted_model_states_what_it_cannot_say():
    rows = [_lap_row(n, grip=1.85 - 0.004 * n) for n in range(1, 12)]
    for model in fit_archive(rows)["models"]:
        joined = " ".join(model["unknowns"])
        assert "no tyre wear channel" in joined
        # M-9: this used to assert "LOWER BOUND", which was a claim to know the
        # fuel direction. The data says otherwise, so the unknown now states
        # that the direction is unknown.
        assert "direction is NOT known" in joined
        assert model["samples"] and model["sessions"] and model["stints"]


def test_the_consecutive_lap_noise_figure_ignores_a_stints_own_decline():
    """Differencing is the point: a clean stint that declines steadily is
    signal, and a raw standard deviation would count all of it as noise."""
    rows = [_lap_row(n, grip=2.0 - 0.01 * n) for n in range(1, 13)]
    noise = consecutive_lap_cv(rows)
    assert noise["cv_pct"] == pytest.approx(0.0, abs=1e-6)
    assert noise["laps"] == 12


def test_the_warm_up_call_will_not_speak_when_the_plateau_moves():
    """**The clause that had been specified and left out.** Counting sequences
    is not the test — where the plateau lands is. On the real archive Monza's
    three fresh sets plateau on laps 5, 9 and 5, so this gate stays shut, and
    without the clause it would have announced a warm-up it could not locate.
    """
    scattered = _warmup_evidence(plateaus=(2, 6, 2))
    verdict = gate_stage1_warmup(scattered)
    assert verdict.met is False
    assert any("plateau lands on lap" in why for why in verdict.failures)

    agreed = _warmup_evidence(plateaus=(2, 2, 3))
    opened = gate_stage1_warmup(agreed)
    assert opened.met is True
    assert "up to temperature" in opened.says


def test_a_warm_up_is_found_even_though_its_first_lap_never_counts():
    """**M-4, and it was a structural dead end.** Every one of the 16 rows in
    the archive marked as a fresh set fails the frames gate — the first lap on
    a new set leaves the pits and recording starts mid-lap. Keying the warm-up
    off the first *counted* row therefore found nothing, ever, in any scope."""
    evidence = _warmup_evidence(plateaus=(2, 2, 2), first_lap_counts=False)
    assert len(evidence.fresh_started_stints) == 3
    assert len(evidence.warmups) == 3
    assert gate_stage1_warmup(evidence).met is True


def test_a_stint_of_unknown_age_keeps_its_opening_laps():
    """Warm-up laps are dropped where a warm-up is known to be, and only there.
    A blanket exclusion cut the opening laps off stints nothing says were
    fresh, which did not move the estimate and halved its precision."""
    rows = []
    for lap in range(8):
        rows.append(_lap_row(lap + 1, grip=1.87 - 0.004 * lap, session=1,
                             stint="1:0"))
    unknown = ScopeEvidence.build(rows)
    assert unknown.fresh_started_stints == set()
    assert len(unknown.contributing_stints["1:0"]) == 8

    fresh = ScopeEvidence.build(
        [{**r, "laps_on_set": 0 if r["lap_in_stint"] == 0 else None}
         for r in rows])
    assert fresh.fresh_started_stints == {"1:0"}
    assert len(fresh.contributing_stints["1:0"]) == 8 - SETTLED_LAP_IN_STINT


def test_may_i_say_answers_stage_zero_when_nothing_has_been_fitted(store):
    verdict = may_i_say(store, stage=2, car_key="porsche-911-rsr-991-17",
                        circuit_key="autodromo-nazionale-monza",
                        compound="RH", yaw_source=YAW_FROM_PATH)
    assert verdict["may_speak"] is False
    assert verdict["say"] == STAGE0_LINE


def test_may_i_say_reads_the_stored_boolean_rather_than_re_weighing(store):
    evidence = _evidence(stints=3, laps_each=10, slope=-0.004)
    fitted = fit_archive(evidence.rows)
    for model in fitted["models"]:
        store.save_tyre_model(model)
    scope = evidence.scope
    verdict = may_i_say(store, stage=2, car_key=scope.car_key,
                        circuit_key=scope.circuit_key, compound=scope.compound,
                        yaw_source=scope.yaw_source)
    assert verdict["may_speak"] is True
    assert verdict["samples"] == 30
    assert verdict["unknowns"]

    # Stages with no fitted model kind fall back to the honest null rather
    # than to silence.
    assert may_i_say(store, stage=3, car_key=scope.car_key,
                     circuit_key=scope.circuit_key, compound=scope.compound,
                     yaw_source=scope.yaw_source)["say"] == STAGE0_LINE


def test_saving_a_compound_agnostic_model_twice_leaves_one_row(store):
    rows = [_lap_row(n, grip=1.85, compound=None) for n in range(1, 12)]
    models = fit_archive(rows)["models"]
    for model in models:
        store.save_tyre_model(model)
    for model in models:
        store.save_tyre_model(model)
    kinds = [m["model_kind"] for m in store.list_tyre_models()]
    assert len(kinds) == len(set(kinds))


def test_an_accented_car_name_keys_the_same_way_on_both_sides():
    """**The identity defect this delegation exists to close.**

    `str.isalnum()` is True for an accented letter, so a rule written as "keep
    alphanumerics" kept it and wrote `lamborghini-huracan-gt3-15` with the
    acute intact, while the scope composition folded it away. The Huracan's 300
    grip observations and 8 fitted models were unreachable by any scope lookup,
    and both sides were internally consistent, which is why nothing complained.
    """
    from pitcrew.analysis.corner_model import model_id_for
    from pitcrew.analysis.grip import event_car_key
    from pitcrew.store.tyres import scope_key, slugify

    event = {"car_name": "Lamborghini Huracán GT3 '15",
             "track": "Watkins Glen International", "layout": "Long Course"}
    car = event_car_key(event)
    circuit = model_id_for(event["track"], event["layout"])
    assert car == "lamborghini-huracan-gt3-15"
    assert "á" not in car

    scope = Scope(car, circuit, "RS", YAW_FROM_PATH)
    # Composed from the stored keys, and composed from the raw names, must be
    # the same string — that is the whole property.
    assert prior_scope_key(scope) == scope_key(
        event["car_name"], event["track"], event["layout"])
    # And the rule is idempotent, which is what makes re-composing safe.
    assert slugify(car) == car and slugify(circuit) == circuit


def test_circuit_identity_and_scope_identity_use_the_one_rule():
    """A corner model is looked up by circuit key and a prior by scope key. If
    those two are composed by different rules they agree until the first name
    with punctuation in it, and then a circuit silently has no corners."""
    from pitcrew.analysis.corner_model import model_id_for
    from pitcrew.store.tyres import slugify

    for track, layout in (("Autodromo Nazionale Monza", None),
                          ("Yas Marina Circuit", "Full Course"),
                          ("Circuit de Spa-Francorchamps", None),
                          ("Autódromo José Carlos Pace", "Grand Prix")):
        joined = f"{track} {layout}" if layout else track
        assert model_id_for(track, layout) == slugify(joined)


def test_the_priors_are_consumed_from_the_store_not_restated_here():
    """Both priors live in `store/tyres.py` as rows with a falsification
    status. A duplicate here could be refuted in one place and survive in the
    other, so this asserts the model reads them rather than owning a copy."""
    scope = Scope("ford-shelby-gt350r-16", "yas-marina-circuit-full-course",
                  "RS", YAW_FROM_PATH)
    priors = {p["id"]: p for p in priors_for_scope(scope)}
    assert set(priors) == {"gap-laptime-0.89", "digitalrelay-wear-onset"}
    assert priors["gap-laptime-0.89"]["status"].startswith("REFUTED")
    # **M-6: a refuted prior is never speakable, scope list or not.** This was
    # a second door into the same room with no lock on it - `speakable_here`
    # came back True on n=17 with no gate in front of it, while every fitted
    # model went through a counted sample. One vocabulary now.
    assert priors["gap-laptime-0.89"]["in_scope"] is True
    assert priors["gap-laptime-0.89"]["speakable_here"] is False
    assert any("refuted prior is never speakable" in b
               for b in priors["gap-laptime-0.89"]["blockers"])
    assert any("below the" in b
               for b in priors["digitalrelay-wear-onset"]["blockers"])
    # The wear-onset threshold has no speakable scope anywhere, and a prior
    # with no scope cannot reach a voice line no matter what imports it.
    assert priors["digitalrelay-wear-onset"]["speakable_scopes"] == []
    assert priors["digitalrelay-wear-onset"]["speakable_here"] is False


# ------------------------------------------------- the real archive, if present


@pytest.mark.skipif(not Path(DEFAULT_DB_PATH).exists(),
                    reason="no recorded archive on this machine")
def test_integration_the_backfilled_archive_reproduces_the_compound_ordering(
        tmp_path):
    """**Integration check against a COPY of `data/pitcrew.db`.**

    Two things here were wrong and both are the kind that make a suite lie.

    **It opened his live race data read-write.** `Store(DEFAULT_DB_PATH)` runs
    schema init, which creates tables and can run a migration, against the
    file holding every lap he has ever recorded - inside a test run. This
    project already has a guardrail against a smoke test writing to the real
    config for the same reason. The archive is copied to `tmp_path` first now,
    and nothing in this test can reach the original.

    **It hard-coded a circuit key that had since changed**, so it hit
    `pytest.skip` and the suite went green with the headline claim unverified -
    `CLAUDE.md` §7's exact failure mode. The scope is discovered from the data
    now, and a missing scope **fails** rather than skips: the only honest
    reasons to skip are "no archive on this machine" and "the archive has not
    been derived yet", and neither of those is "I could not find what I was
    looking for".
    """
    copied = tmp_path / "archive.db"
    _snapshot_of_the_archive(copied)
    store = Store(copied)
    try:
        rows = store.list_grip_observations(unit_kind="LAP")
        if not rows:
            pytest.skip("archive holds no derived observations yet")
        result = fit_archive(rows)

        # Discovered, not hard-coded: the multi-compound path-reconstructed
        # scope with the most laps behind it.
        candidates = [o for o in result["compound_ordering"]
                      if o["yaw_source"] == YAW_FROM_PATH
                      and len(o["levels"]) >= 3]
        assert candidates, (
            "no three-compound scope in the archive — the compound ordering "
            "is this observable's only validation against a known-sign grip "
            "step, so its absence is a failure, not a reason to skip. "
            f"Scopes present: "
            f"{[(o['circuit_key'], [lv['compound'] for lv in o['levels']]) for o in result['compound_ordering']]}")
        best = max(candidates, key=lambda o: sum(lv["n"] for lv in o["levels"]))
        levels = {lv["compound"]: lv["mean_grip_g"] for lv in best["levels"]}
        assert levels["RH"] < levels["RM"] < levels["RS"]
        assert best["monotone_in_softness"] is True
        assert best["welch_t"] > 3.0
        # The caveat travels into the export, so it has to keep naming every
        # confound rather than only the first one anybody thought of.
        for confound in ("SESSION", "LAP-IN-STINT", "CHRONOLOGY", "SETUP SHEET"):
            assert confound in best["caveat"]
    finally:
        store.close()


@pytest.mark.skipif(not Path(DEFAULT_DB_PATH).exists(),
                    reason="no recorded archive on this machine")
def test_integration_no_scope_speaks_a_rising_trend(tmp_path):
    """Nothing in the real archive may announce a loss while its own fit rises.

    The guard that makes this more than a restatement of the unit test: it runs
    against whatever is actually on disk, including scopes nobody thought to
    construct by hand.
    """
    copied = tmp_path / "archive.db"
    _snapshot_of_the_archive(copied)
    store = Store(copied)
    try:
        rows = store.list_grip_observations(unit_kind="LAP")
        if not rows:
            pytest.skip("archive holds no derived observations yet")
        for model in fit_archive(rows)["models"]:
            if model["model_kind"] != "degradation" or not model["speakable"]:
                continue
            slope = model["model"]["grip_g_per_lap"]
            assert slope is not None and slope < 0, (
                f"{model['circuit_key']}/{model['compound']} is speakable with "
                f"a rising slope of {slope}")
            assert model["model"]["between_stint"]["all_negative"]
            assert "per cent" not in model["gate"]["says"]
    finally:
        store.close()


# ----------------------------------------------------------------- fixtures


def _store_lap(store: Store, session_id: int, *, lap_num: int) -> int:
    from pitcrew.telemetry.recorder import encode_frames

    blob = encode_frames([[0, None, 200.0]])
    with store._write() as conn:
        cur = conn.execute(
            "INSERT INTO laps (session_id, lap_num, lap_time_ms, recorded_at) "
            "VALUES (?,?,?,datetime('now'))", (session_id, lap_num, 110_000))
        lap_id = int(cur.lastrowid)
        conn.execute("INSERT INTO lap_frames (lap_id, sample_hz, frame_count, "
                     "blob) VALUES (?,?,?,?)", (lap_id, HZ, 1, blob))
    return lap_id


def _observation(lap_id: int, session_id: int) -> dict:
    return {
        "lap_id": lap_id, "unit_kind": "LAP", "unit_id": "LAP",
        "derivation_version": DERIVATION_VERSION, "frame_schema_version": 2,
        "yaw_source": YAW_FROM_PACKET, "sample_frames": 6600,
        "car_key": "porsche-911-rsr", "circuit_key": "monza",
        "compound": "RH", "session_id": session_id, "lap_num": 1,
        "grip_g": 1.85, "grip_stat": "comb_p95",
        "counts_toward_fit": 1,
    }


def _lap(lap_num: int, **overrides) -> dict:
    lap = {"id": lap_num, "lap_num": lap_num, "lap_time_ms": 110_000,
           "compound": "RH", "fuel_start": 60.0, "crawl_s": 0.0,
           "spin_s": 0.0, "off_track_s": 0.0}
    lap.update(overrides)
    return lap


def _context(**overrides) -> SessionContext:
    context = SessionContext(session_id=1, car_key="porsche-911-rsr",
                             circuit_key="monza", corner_model_version=3)
    for key, value in overrides.items():
        setattr(context, key, value)
    return context


def _synthetic_lap(*, lateral: float, frames: int = 6600) -> list[dict]:
    """A lap at constant speed and constant lateral load.

    Constant speed means the longitudinal term is zero and the combined
    magnitude is exactly the lateral one, so the expected percentile is known
    in closed form.
    """
    return [{"speed_kph": 200.0, "lat_g": lateral, "brake_pct": 0.0,
             "throttle_pct": 100.0, "temp_fl": 70.0, "temp_fr": 71.0,
             "temp_rl": 80.0, "temp_rr": 81.0,
             "surf_fl": "T", "surf_fr": "T", "surf_rl": "T", "surf_rr": "T",
             "lap_distance_m": index * 200.0 / 3.6 / HZ}
            for index in range(frames)]


def _trace_with_apex_at(distance_m: float, *, index: int) -> LapTrace:
    """A lap whose only speed minimum sits at a chosen lap distance."""
    frames = []
    for step in range(400):
        metres = 900.0 + step * 0.5
        frames.append({
            "speed_kph": 200.0 - 60.0 * math.exp(
                -((metres - distance_m) / 30.0) ** 2),
            "lat_g": 1.2, "brake_pct": 50.0, "throttle_pct": 40.0,
            "temp_fl": 70.0, "temp_fr": 70.0, "temp_rl": 80.0, "temp_rr": 80.0,
            "lap_distance_m": metres})
    return trace_lap(frames, HZ, lap_id=index, session_id=1, lap_num=index + 1,
                     frame_schema_version=2)


def _lap_row(lap_num: int, *, grip: float, yaw_source: str = YAW_FROM_PATH,
             session: int = 1, stint: str | None = None,
             compound: str | None = "RH", **overrides) -> dict:
    row = {
        "lap_id": session * 1000 + lap_num, "unit_kind": "LAP", "unit_id": "LAP",
        "derivation_version": DERIVATION_VERSION, "frame_schema_version": 2,
        "yaw_source": yaw_source, "sample_frames": 6000,
        "car_key": "porsche-911-rsr", "circuit_key": "monza",
        "compound": compound, "session_id": session, "lap_num": lap_num,
        "stint_key": stint or f"{session}:0", "lap_in_stint": lap_num - 1,
        "grip_g": grip, "grip_stat": "comb_p95",
        "temp_rear_c": 80.0 + 0.2 * lap_num, "temp_front_c": 70.0,
        "gauge_worst_frac": None, "laps_on_set": None,
        "counts_toward_fit": 1, "exclusion_reason": None,
    }
    row.update(overrides)
    return row


def _warmup_evidence(*, plateaus: tuple[int, ...],
                     first_lap_counts: bool = True) -> ScopeEvidence:
    """Fresh-set stints whose rear axle stops climbing at a chosen lap each.

    `first_lap_counts=False` reproduces the archive: the lap that carries the
    fresh-set mark is itself unmeasurable, because recording starts mid-lap on
    the way out of the pits.
    """
    rows = []
    for stint, plateau in enumerate(plateaus):
        for lap in range(6):
            temp = 70.0 + 4.0 * min(lap, plateau)
            rows.append(_lap_row(
                lap + 1, grip=1.87, session=stint + 1, stint=f"{stint + 1}:0",
                temp_rear_c=temp,
                laps_on_set=0 if lap == 0 else None,
                counts_toward_fit=0 if (lap == 0 and not first_lap_counts) else 1,
                exclusion_reason=("frames-gate" if (lap == 0
                                                    and not first_lap_counts)
                                  else None)))
    return ScopeEvidence.build(rows)


def _evidence(*, stints: int, laps_each: int, slope: float,
              fresh: bool = False) -> ScopeEvidence:
    """Stints with a chosen trend and a deterministic sprinkle of scatter.

    The scatter is not decoration. A noiseless line has zero residual, which
    leaves the slope's standard error at zero and its t undefined — an honest
    answer to a fabricated question, and one that would let these tests pass on
    a fit that could never happen. Real laps at this circuit scatter by about
    0.7 %; this is a tenth of that, deterministic so the gates are reproducible.
    """
    wobble = (0.0007, -0.0011, 0.0004, 0.0009, -0.0006,
              -0.0003, 0.0012, -0.0008, 0.0002, 0.0005)
    rows = []
    for stint in range(stints):
        for lap in range(laps_each):
            rows.append(_lap_row(
                lap + 1,
                grip=1.87 + slope * lap + wobble[(stint * 3 + lap) % len(wobble)],
                session=stint + 1, stint=f"{stint + 1}:0",
                laps_on_set=0 if (fresh and lap == 0) else None))
    return ScopeEvidence.build(rows)
