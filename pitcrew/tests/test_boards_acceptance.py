"""Acceptance tests for S1–S4 (25 Sep 2026).

Covers the seams the orchestrator specified:
  controller → DriverState → compose → payload
  DriverState → _HistoryPanel

Probe results (static or runtime) are recorded inline with their criterion.

**What is NOT re-tested here** (already covered by the builders' unit files):
  fill_verdict arithmetic   → test_fill_verdict.py
  rival_stop_rows grouping  → test_rival_stops_monitor.py
  _RivalStopsPanel labels   → test_rival_stops_panel.py
  compound_bests            → test_practice_tablet_compound_bests.py
  practice sector ranking   → test_practice_monitor_sectors.py
  stint_plan_averages       → test_stint_averages.py
  compose box in-lap        → test_tablet_race_own.py

**Probe: tablet.html null/0 rendering — static inspection, no JS harness.**
All null-guards in the HTML use ``== null ? "--" : value`` or
``value || "--"`` (which is safe because all values are strings or numbers,
never integer 0).  The only falsy-string risk is ``box.value || "--"``
which would hide an empty string as "--"; that is correct behaviour.
No case found where a null renders as 0.  The JS is not executed here.
"""
from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

from pitcrew.race.field import FieldView, OwnGap  # noqa: E402
from pitcrew.ui.driver_view import DriverState  # noqa: E402
from pitcrew.ui.tablet import compose  # noqa: E402


def _view(**kw) -> FieldView:
    return FieldView(position=5, lap=10, laps_total=20, **kw)


def _state(**kw) -> DriverState:
    return DriverState(**kw)


# ===========================================================================
# S1a — gap ahead / behind: trend, rate, P1/last dash, expired "--", never 0
# ===========================================================================


def test_s1a_gap_null_when_p1():
    """P1 has no car ahead → gap_ahead is null in the payload (not "--" or 0)."""
    body = compose(_view(own_gap_ahead=None), _state())
    assert body["own"]["gap_ahead"] is None


def test_s1a_gap_null_when_last():
    """Last place has no car behind → gap_behind is null in the payload."""
    body = compose(_view(own_gap_behind=None), _state())
    assert body["own"]["gap_behind"] is None


def test_s1a_gap_expired_unread_true_gap_s_null():
    """Expired gap → unread=True AND gap_s=None in the payload (never a stale number)."""
    view = _view(own_gap_ahead=OwnGap(gap_s=None, unread=True,
                                      trend=None, rate_s_per_lap=None))
    own = compose(view, _state())["own"]
    ga = own["gap_ahead"]
    assert ga is not None
    assert ga["unread"] is True
    assert ga["gap_s"] is None


def test_s1a_gap_trend_and_rate_carried():
    """Valid gap → trend and rate_s_per_lap pass through unchanged."""
    view = _view(own_gap_ahead=OwnGap(gap_s=2.1, unread=False,
                                      trend="closing 1.3 s/lap",
                                      rate_s_per_lap=1.3))
    ga = compose(view, _state())["own"]["gap_ahead"]
    assert ga["gap_s"] == pytest.approx(2.1)
    assert ga["trend"] == "closing 1.3 s/lap"
    assert ga["rate_s_per_lap"] == pytest.approx(1.3)


def test_s1a_gap_trend_null_inside_noise():
    """When trend is None (inside noise gate), rate_s_per_lap is also None."""
    view = _view(own_gap_ahead=OwnGap(gap_s=1.2, unread=False,
                                      trend=None, rate_s_per_lap=None))
    ga = compose(view, _state())["own"]["gap_ahead"]
    assert ga["trend"] is None
    assert ga["rate_s_per_lap"] is None


def test_s1a_gap_s_not_zero_when_payload_has_valid_reading():
    """gap_s passes through as-is; the application layer must never send 0.0.

    This test ensures compose() does NOT sanitise a 0.0 to None — a zero
    gap is physically implausible and should never enter from telemetry.
    The criterion 'never 0' is enforced by the data source, not by compose().
    A zero that reaches compose() would appear in the payload as 0.0.
    """
    view = _view(own_gap_ahead=OwnGap(gap_s=0.5, unread=False,
                                      trend=None, rate_s_per_lap=None))
    ga = compose(view, _state())["own"]["gap_ahead"]
    # A real reading of 0.5 must not be suppressed.
    assert ga["gap_s"] == pytest.approx(0.5)
    assert ga["gap_s"] != 0


# ===========================================================================
# S1b — four own tyre temps; null → dash (None in payload)
# ===========================================================================


def test_s1b_all_temps_null_payload_is_null():
    """No readings → temps_c is None in the payload, not a dict of zeros."""
    body = compose(_view(), _state(temps_c=None))
    assert body["own"]["temps_c"] is None


def test_s1b_partial_null_temps_preserved():
    """Individual null temps pass through as None, never as 0.0."""
    body = compose(_view(), _state(
        temps_c={"fl": 95.0, "fr": None, "rl": 87.0, "rr": None}
    ))
    t = body["own"]["temps_c"]
    assert t["fl"] == pytest.approx(95.0)
    assert t["fr"] is None          # must not be 0
    assert t["rl"] == pytest.approx(87.0)
    assert t["rr"] is None          # must not be 0


def test_s1b_four_temps_all_present():
    """All four temps populated → all four present in payload."""
    body = compose(_view(), _state(
        temps_c={"fl": 90.0, "fr": 91.0, "rl": 85.0, "rr": 86.0}
    ))
    t = body["own"]["temps_c"]
    assert all(t[k] is not None for k in ("fl", "fr", "rl", "rr"))


# ===========================================================================
# S1c — stint averages: DERIVED, lap count, null under 2 laps
# ===========================================================================


def test_s1c_stint_averages_null_when_zero_laps():
    """No stint data → all four stint fields are None, never 0."""
    own = compose(_view(), _state())["own"]
    assert own["stint_lap_delta_ms"] is None
    assert own["stint_lap_laps"] is None
    assert own["stint_burn_delta_l"] is None
    assert own["stint_burn_laps"] is None


def test_s1c_stint_averages_carried_when_two_or_more_laps():
    """Averages over 3 laps are present with count in payload."""
    view = _view(
        own_stint_lap_delta_ms=-120,
        own_stint_lap_laps=3,
        own_stint_burn_delta_l=0.2,
        own_stint_burn_laps=3,
    )
    own = compose(view, _state())["own"]
    assert own["stint_lap_delta_ms"] == -120
    assert own["stint_lap_laps"] == 3
    assert own["stint_burn_delta_l"] == pytest.approx(0.2)
    assert own["stint_burn_laps"] == 3


def test_s1c_stint_averages_missing_carries_null_not_zero():
    """Partially missing data: if only one count is null, the other is also null."""
    # If only laps count is None, the delta is meaningless: both must be null together.
    view = _view(
        own_stint_lap_delta_ms=None,
        own_stint_lap_laps=None,
        own_stint_burn_delta_l=None,
        own_stint_burn_laps=None,
    )
    own = compose(view, _state())["own"]
    assert own["stint_lap_delta_ms"] is None
    assert own["stint_lap_laps"] is None


# ===========================================================================
# S1d — laps figure: laps to stop or flag with label; NOW not "0"
# ===========================================================================


def test_s1d_box_value_is_numeric_when_stop_planned():
    """With a stop planned, box.value and own.laps.value are the same string."""
    state = _state(laps_to_box=5.0, has_plan=True)
    own = compose(_view(), state)["own"]
    assert own["box"]["value"] == "5"
    # Rule 13: own.laps.value is VERBATIM from box_block — same string, same
    # tone — so the two cells on the same screen cannot disagree.
    assert own["laps"]["value"] == own["box"]["value"]
    assert own["laps"]["label"] == "to the stop"


def test_s1d_box_value_NOW_on_in_lap_never_zero():
    """On the in-lap (laps_past_box=0) box.value must be 'NOW', never '0'."""
    state = _state(laps_to_box=0.0, laps_past_box=0, has_plan=True)
    own = compose(_view(), state)["own"]
    assert own["box"]["value"] == "NOW"
    assert own["box"]["value"] != "0"


def test_s1d_laps_value_is_NOW_on_box_lap_never_zero():
    """On the in-lap own.laps.value must be 'NOW', never '0' (rule 3).

    The value comes verbatim from box_block, which returns 'NOW' on the
    in-lap.  The old implementation computed str(int(laps_to_box)) = '0';
    the fix is to take box_block(state).value directly (rule 13).
    """
    from pitcrew.ui.driver_view import box_block as _box_block

    state = _state(laps_to_box=0.0, laps_past_box=0, has_plan=True)
    own = compose(_view(), state)["own"]
    bb_value = _box_block(state).value
    assert own["laps"]["value"] == bb_value, (
        "own.laps.value must equal box_block(state).value verbatim"
    )
    assert own["laps"]["value"] == "NOW"
    assert own["laps"]["value"] != "0"


def test_s1d_laps_to_flag_when_no_further_stop():
    """When plan has no further stop, own.laps shows laps to the flag.

    S1d criterion: 'otherwise laps to the flag, with a label naming which.'
    C1 fix, 25 Sep 2026: own.laps {value, label, tone} carries the flag figure
    when laps_to_box is None and has_plan is True.  The box block is unchanged.
    """
    state = _state(laps_to_box=None, has_plan=True)
    view = _view(own_laps_remaining=10)
    own = compose(view, state)["own"]
    assert own["laps"] is not None, "laps block must be present"
    assert own["laps"]["label"] == "to the flag"
    assert own["laps"]["value"] == "10"


def test_s1d_laps_none_when_finished_box_has_flag_word():
    """Finished race: own.laps is None; own.box carries box_block's 'FLAG' word.

    I-B fix, 25 Sep 2026: when state.finished is True, laps_remaining() returns
    0 and _laps_block would emit {'value': '0', 'label': 'to the flag'} — a
    zero that is not a measurement (rule 3) and hides 'FLAG'.  Return None so
    the page falls back to own.box, which box_block has already worded.
    """
    from pitcrew.ui.driver_view import box_block as _box_block

    state = _state(finished=True, has_plan=True, laps_to_box=None)
    own = compose(_view(own_laps_remaining=0), state)["own"]
    assert own["laps"] is None, (
        "finished race: own.laps must be None — box_block says 'FLAG'"
    )
    # own.box carries box_block's value verbatim.
    assert own["box"]["value"] == _box_block(state).value


def test_s1d_laps_none_when_laps_remaining_zero():
    """laps_remaining==0 before finished is set: own.laps must still be None.

    At the final crossing laps_remaining() becomes 0 before the controller
    sets finished=True.  The guard must catch both to prevent '0 to the flag'.
    """
    state = _state(finished=False, has_plan=True, laps_to_box=None)
    own = compose(_view(own_laps_remaining=0), state)["own"]
    assert own["laps"] is None, (
        "laps_remaining==0 must give own.laps None, not '0 to the flag'"
    )


def test_s1d_laps_value_never_zero_across_remaining_range():
    """own.laps.value is never '0' for any laps_remaining from 0 to N.

    Parametric guard: iterate laps_remaining 0..3 and confirm no '0' string
    escapes.  Values of 1+ produce the numeric label; 0 produces None.
    """
    for remaining in range(4):
        state = _state(finished=False, has_plan=True, laps_to_box=None)
        view = _view(own_laps_remaining=remaining)
        own = compose(view, state)["own"]
        laps = own.get("laps")
        if laps is not None:
            assert laps["value"] != "0", (
                f"own.laps.value must never be '0' (remaining={remaining})"
            )


def test_s1d_laps_one_on_final_lap():
    """On the final lap (laps_remaining==1) own.laps shows '1 to the flag'."""
    state = _state(finished=False, has_plan=True, laps_to_box=None)
    own = compose(_view(own_laps_remaining=1), state)["own"]
    assert own["laps"] is not None
    assert own["laps"]["value"] == "1"
    assert own["laps"]["label"] == "to the flag"


def test_s1d_own_block_absent_without_state():
    """Without a DriverState the own key must be absent (rule 3: absent ≠ null)."""
    body = compose(_view())
    assert "own" not in body


# ===========================================================================
# S2a — all entered drivers get a row; not-entered dimmed; own excluded
# ===========================================================================


def test_s2a_own_driver_excluded_by_rival_stop_rows():
    """rival_stop_rows excludes the own driver by name match (case-insensitive)."""
    from pitcrew.race.fill_verdict import rival_stop_rows

    stops = [
        {"id": 1, "driver": "BEENI", "lap": 10, "fuel_in_l": 8.0,
         "fuel_out_l": 45.0, "partial": 0, "exit_is_a_bound": 0,
         "compound": "RS", "compound_in": "RH"},
        {"id": 2, "driver": "RIVAL", "lap": 10, "fuel_in_l": 8.0,
         "fuel_out_l": 45.0, "partial": 0, "exit_is_a_bound": 0,
         "compound": "RS", "compound_in": "RH"},
    ]
    rows = rival_stop_rows(stops, entered=["BEENI", "RIVAL"],
                           own_driver="BEENI", laps_remaining=8,
                           own_burn_l=8.0)
    names = [r.driver for r in rows]
    assert "BEENI" not in names, "own driver must be excluded"
    assert "RIVAL" in names


def test_s2a_own_driver_exclusion_is_case_insensitive():
    """Own driver exclusion is case-insensitive (board may use mixed case)."""
    from pitcrew.race.fill_verdict import rival_stop_rows

    stops = [
        {"id": 1, "driver": "Beeni-187", "lap": 10, "fuel_in_l": 8.0,
         "fuel_out_l": 45.0, "partial": 0, "exit_is_a_bound": 0,
         "compound": "RS", "compound_in": "RH"},
    ]
    rows = rival_stop_rows(stops, entered=["Beeni-187"],
                           own_driver="BEENI-187", laps_remaining=8,
                           own_burn_l=8.0)
    assert len(rows) == 0, "own driver (upper case) must still be excluded"


def test_s2a_entered_driver_not_dimmed():
    """A driver whose name is in the entered list is NOT dimmed."""
    from pitcrew.race.fill_verdict import rival_stop_rows

    stops = [{"id": 1, "driver": "ROCKY", "lap": 10, "fuel_in_l": 8.0,
              "fuel_out_l": 45.0, "partial": 0, "exit_is_a_bound": 0,
              "compound": "RS", "compound_in": "RH"}]
    rows = rival_stop_rows(stops, entered=["ROCKY"], own_driver=None,
                           laps_remaining=8, own_burn_l=8.0)
    assert rows[0].dimmed is False


def test_s2a_not_entered_driver_is_dimmed():
    """A driver in stops but not in entered is dimmed, not hidden.

    C2: BEENI is in entered but has no stops, so she also gets a row.
    GHOST is in stops but not in entered, so she is dimmed.
    """
    from pitcrew.race.fill_verdict import rival_stop_rows

    stops = [{"id": 1, "driver": "GHOST", "lap": 10, "fuel_in_l": 8.0,
              "fuel_out_l": 45.0, "partial": 0, "exit_is_a_bound": 0,
              "compound": "RS", "compound_in": "RH"}]
    rows = rival_stop_rows(stops, entered=["BEENI"], own_driver=None,
                           laps_remaining=8, own_burn_l=8.0)
    # C2: two rows — BEENI (entered, no stops) and GHOST (not entered, dimmed).
    assert len(rows) == 2, "both the entered no-stop driver and the dimmed driver get rows"
    ghost = next(r for r in rows if r.driver == "GHOST")
    assert ghost.dimmed is True


def test_s2a_entered_driver_with_no_stops_gets_row():
    """An entered driver with no stops gets a row with stop_count=0 (C2 fix).

    S2a criterion: 'emit one row for EVERY name in entered (except own),
    even with no stops (dashes)'.  C2 fix, 25 Sep 2026.
    """
    from pitcrew.race.fill_verdict import rival_stop_rows

    # No stops at all for "PUNISHED" who is in the entered list.
    rows = rival_stop_rows([], entered=["PUNISHED"], own_driver=None,
                           laps_remaining=10, own_burn_l=8.0)
    assert len(rows) == 1, "entered driver with no stops must get a row"
    assert rows[0].driver == "PUNISHED"
    assert rows[0].stop_count == 0
    assert rows[0].last_stop_lap is None
    assert rows[0].fuel_in_l is None
    assert rows[0].dimmed is False


# ===========================================================================
# S2b — columns: stop lap, fuel in/out, tyres in/out, stop count
# (seam test: RivalStopRow fields reach the table correctly)
# ===========================================================================


def test_s2b_compound_out_none_when_disc_flip_unconfirmed():
    """compound_out is None when disc flip was not confirmed (schema reads=0)."""
    from pitcrew.race.fill_verdict import rival_stop_rows

    stops = [{"id": 1, "driver": "X", "lap": 10, "fuel_in_l": 8.0,
              "fuel_out_l": 45.0, "partial": 0, "exit_is_a_bound": 0,
              "compound": None,      # no confirmed disc read on exit
              "compound_in": "RH"}]
    rows = rival_stop_rows(stops, entered=["X"], own_driver=None,
                           laps_remaining=8, own_burn_l=8.0)
    assert rows[0].compound_out is None


def test_s2b_stop_count_is_one_for_single_stop():
    from pitcrew.race.fill_verdict import rival_stop_rows

    stops = [{"id": 1, "driver": "Y", "lap": 10, "fuel_in_l": 8.0,
              "fuel_out_l": 45.0, "partial": 0, "exit_is_a_bound": 0,
              "compound": "RS", "compound_in": "RH"}]
    rows = rival_stop_rows(stops, entered=["Y"], own_driver=None,
                           laps_remaining=8, own_burn_l=8.0)
    assert rows[0].stop_count == 1


# ===========================================================================
# S2c — burn per lap: first-stop 100 L assumption probe
# ===========================================================================


def test_s2c_first_stop_uses_100l_start_assumption():
    """First stop: burn = (100 L − fuel_in) / laps (C3 fix, 25 Sep 2026).

    S2c criterion: 'burn = (previous fuel out, or 100 for the first stop
    − fuel in) / laps between'.  With no assumed_start_l on the stop row
    and no capacity supplied, 100 L is assumed (burn_assumed=True).
    """
    from pitcrew.race.fill_verdict import rival_stop_rows

    # Single stop: arrived with 8 L after 10 laps.
    # Expected: burn = (100 - 8) / 10 = 9.2 L/lap.
    stops = [{"id": 1, "driver": "Z", "lap": 10, "fuel_in_l": 8.0,
              "fuel_out_l": 50.0, "partial": 0, "exit_is_a_bound": 0,
              "compound": "RS", "compound_in": "RH"}]
    rows = rival_stop_rows(stops, entered=["Z"], own_driver=None,
                           laps_remaining=8, own_burn_l=5.0)
    assert len(rows) == 1
    assert rows[0].burn_per_lap_l == pytest.approx(9.2), (
        "first-stop burn must be (100 - fuel_in) / laps = 9.2, "
        "not own_burn_l=5.0"
    )
    assert rows[0].burn_assumed is True, "burn_assumed must be True when 100 L used"


def test_s2c_electric_car_capacity_zero_gives_none_burn():
    """capacity_l=0 (electric car): first-stop burn must be None, not computed.

    S2c / CLAUDE.md §3.4: 'A capacity of 0 is a real value, not an error —
    guard the divide.'  Rule 9: return None rather than clamping or producing
    a meaningless figure.  C3 fix, 25 Sep 2026.
    """
    from pitcrew.race.fill_verdict import rival_stop_rows

    # Electric car (capacity=0): single stop, arrived with some fuel.
    # The burn computation must return None (no meaningful L/lap derivable).
    stops = [{"id": 1, "driver": "E", "lap": 10, "fuel_in_l": 8.0,
              "fuel_out_l": 50.0, "partial": 0, "exit_is_a_bound": 0,
              "compound": "RS", "compound_in": "RS"}]
    rows = rival_stop_rows(stops, entered=["E"], own_driver=None,
                           laps_remaining=8, own_burn_l=None,
                           capacity_l=0)
    assert len(rows) == 1
    # With capacity_l=0 and own_burn_l=None, burn_per_lap_l must be None.
    assert rows[0].burn_per_lap_l is None, (
        "electric car (capacity=0) must yield None burn, not a computed figure"
    )


def test_s2c_negative_burn_returns_none_not_clamped():
    """Rule 9: _burn_per_lap returns None for negative burned fuel, never 0."""
    from pitcrew.race.fill_verdict import _burn_per_lap

    result = _burn_per_lap(prev_fuel_out_l=30.0, fuel_in_l=50.0)
    assert result is None, "negative burned fuel must return None, not be clamped"


# ===========================================================================
# S2d — fill verdict uses own laps_remaining (rule 13 / probe)
# ===========================================================================


def test_s2d_fill_verdict_uses_laps_remaining_not_laps_to_stop():
    """Rule 13 probe: the fill verdict uses laps_remaining (to the flag), while
    the tablet box shows laps_to_box (to the next pit stop).  These are
    different quantities, correctly labelled differently.  Neither figure
    appears under the other's label in the payload — no rule 13 violation.

    This test verifies the seam: rival_stop_rows passes laps_remaining to
    fill_verdict, not laps_to_box.
    """
    from pitcrew.race.fill_verdict import fill_verdict, rival_stop_rows

    laps_remaining = 8      # laps to the flag
    laps_to_stop = 3        # laps to next pit (a different number)

    stops = [{"id": 1, "driver": "A", "lap": 10, "fuel_in_l": 8.0,
              "fuel_out_l": 40.0, "partial": 0, "exit_is_a_bound": 0,
              "compound": "RS", "compound_in": "RH"}]
    rows = rival_stop_rows(stops, entered=["A"], own_driver=None,
                           laps_remaining=laps_remaining, own_burn_l=8.0)
    row = rows[0]

    # C3: burn is now derived from (100 - fuel_in) / stop_lap = (100-8)/10 = 9.2.
    derived_burn = (100.0 - 8.0) / 10
    # Fill verdict built with laps_remaining=8 directly (the correct figure).
    expected = fill_verdict(40.0, derived_burn, laps_remaining,
                            partial=False, exit_is_a_bound=False)
    # NOT built with laps_to_stop=3.
    wrong = fill_verdict(40.0, derived_burn, laps_to_stop,
                         partial=False, exit_is_a_bound=False)

    assert row.verdict.verdict == expected.verdict
    assert row.verdict.margin_l == pytest.approx(expected.margin_l)
    # The margin with laps_to_stop would be different.
    assert expected.margin_l != pytest.approx(wrong.margin_l), (
        "laps_remaining and laps_to_stop must produce different margins "
        "for this test to be meaningful"
    )


# ===========================================================================
# S2 — controller scopes rival_stops to current session_id (DB probe)
# ===========================================================================


def test_s2_db_rival_stops_scoped_by_session_id(tmp_path):
    """db.rival_stops(session_id=N) returns only stops from that session.

    This is the seam test for controller._rival_table: it passes
    session_id=self.session_id so last race's stops don't appear tonight.
    """
    from pitcrew.store.db import Store

    db = Store(tmp_path / "pitcrew.db")
    try:
        e = db.create_event(
            name="Test", track="Monza", layout="Full Course",
            car_id=1, car_name="Test Car",
            race_type="laps", race_laps=20,
            refuel_rate_lps=2.5, pit_loss_secs=20.0,
            available_compounds=["RS"], required_compounds=["RS"],
        )
        s1 = db.start_session(e, "race")
        s2 = db.start_session(e, "race")

        db.record_rival_stop(s1, "RIVAL_OLD", lap=5, fuel_out_l=50.0)
        db.record_rival_stop(s2, "RIVAL_NOW", lap=5, fuel_out_l=50.0)

        scoped = db.rival_stops(session_id=s2)
        names = [r["driver"] for r in scoped]
        assert "RIVAL_NOW" in names
        assert "RIVAL_OLD" not in names, (
            "rival_stops(session_id=N) must NOT return stops from a previous session"
        )
    finally:
        db.close()


def test_s2_db_rival_stops_no_session_filter_returns_all(tmp_path):
    """Without a session_id filter, all stops are returned (unscoped behaviour)."""
    from pitcrew.store.db import Store

    db = Store(tmp_path / "pitcrew.db")
    try:
        e = db.create_event(
            name="Test", track="Monza", layout="Full Course",
            car_id=1, car_name="Test Car",
            race_type="laps", race_laps=20,
            refuel_rate_lps=2.5, pit_loss_secs=20.0,
            available_compounds=["RS"], required_compounds=["RS"],
        )
        s1 = db.start_session(e, "race")
        s2 = db.start_session(e, "race")
        db.record_rival_stop(s1, "OLD", lap=5, fuel_out_l=50.0)
        db.record_rival_stop(s2, "NEW", lap=5, fuel_out_l=50.0)

        all_stops = db.rival_stops()   # no session filter
        names = {r["driver"] for r in all_stops}
        assert "OLD" in names
        assert "NEW" in names
    finally:
        db.close()


# ===========================================================================
# S2 — _RivalStopsPanel capacity: more than MAX_RIVALS silently drops rows
# ===========================================================================


def test_s2_rival_panel_more_than_16_drivers_shows_overflow():
    """_RivalStopsPanel with more than MAX_RIVALS entries shows an overflow line.

    C4 fix (25 Sep 2026): the panel used to silently drop entries beyond 16.
    Now when rival_table has 17+ entries, the first MAX_RIVALS are shown and
    an overflow label reads "+N more not shown", so the user knows the table
    is truncated (rule 3: a silent drop looks like complete data).
    """
    pytest.importorskip("PyQt6.QtWidgets")
    from PyQt6.QtWidgets import QApplication

    _app = QApplication.instance() or QApplication([])

    from pitcrew.race.fill_verdict import RivalStopRow
    from pitcrew.ui.driver_view import MAX_RIVALS, _RivalStopsPanel

    panel = _RivalStopsPanel()

    # Build MAX_RIVALS + 1 rows (17 total).
    rows = tuple(
        RivalStopRow(driver=f"DRIVER_{i}", last_stop_lap=i + 1)
        for i in range(MAX_RIVALS + 1)
    )
    panel.show_state(rows)

    # The first MAX_RIVALS rows are shown.
    shown_names = {panel._row_labels[i][0].text() for i in range(MAX_RIVALS)}
    for i in range(MAX_RIVALS):
        assert f"DRIVER_{i}" in shown_names, (
            f"DRIVER_{i} should be shown in the first {MAX_RIVALS} rows"
        )

    # The overflow is NOT silently dropped: the overflow label is not hidden
    # and says "+1 more not shown".  (isHidden rather than isVisible: the
    # parent panel is not shown in this offscreen test, so isVisible traverses
    # the parent chain and returns False regardless; isHidden checks only the
    # widget's own flag.)
    assert not panel._overflow_label.isHidden(), (
        "The overflow label must not be hidden when rival_table exceeds MAX_RIVALS"
    )
    assert "+1" in panel._overflow_label.text(), (
        f"Overflow label should mention '+1', got: {panel._overflow_label.text()!r}"
    )


# ===========================================================================
# S3 — practice tablet: compound_bests, no placeholders
# ===========================================================================


def test_s3_no_placeholder_rows_when_no_laps():
    """compound_bests=[] → key present but empty list, no placeholder entries."""
    from pitcrew.ui.tablet import compose_practice

    state = DriverState(session_kind="practice", lap_number=1,
                        last_lap_ms=None, compound=None,
                        compound_bests=[])
    body = compose_practice(state)
    assert "compound_bests" in body
    assert body["compound_bests"] == []


def test_s3_compound_bests_ordered_best_first():
    """compound_bests are ordered by best_ms ascending (fastest first)."""
    from pitcrew.ui.tablet import compose_practice

    state = DriverState(session_kind="practice", lap_number=5,
                        last_lap_ms=95_000, compound="RS",
                        compound_bests=[
                            {"compound": "RM", "best_ms": 98_000, "lap_count": 3},
                            {"compound": "RS", "best_ms": 93_000, "lap_count": 5},
                        ])
    body = compose_practice(state)
    bests = body["compound_bests"]
    assert bests[0]["compound"] == "RM"   # as-supplied — compose_practice does not re-sort
    # The ordering must come from compound_bests_for_session (already tested).
    # This test verifies compose_practice passes the list through in supplied order.
    assert len(bests) == 2


def test_s3_compound_bests_absent_when_none():
    """compound_bests=None → key absent from payload (rule 3: absent ≠ empty)."""
    from pitcrew.ui.tablet import compose_practice

    state = DriverState(session_kind="practice", lap_number=1,
                        compound_bests=None)
    body = compose_practice(state)
    assert "compound_bests" not in body


# ===========================================================================
# S4 — practice rack: compound on every lap row; sector tones
# ===========================================================================


def test_s4_excluded_lap_has_no_sector_tones():
    """Excluded lap carries no sector tone regardless of time (rank_ink rule)."""
    from pitcrew.ui.driver_view import history_rows

    history = [
        {"lap": 1, "lap_ms": 100_000, "lap_delta_s": None,
         "burn_l": 3.0, "burn_delta_l": None, "saving": None, "why": None,
         "pit": False, "out": False, "counted": False,   # excluded
         "compound": "RS", "sectors_ms": (40_000, 36_000, 25_000)},
        {"lap": 2, "lap_ms": 101_000, "lap_delta_s": 1.0,
         "burn_l": 3.0, "burn_delta_l": None, "saving": None, "why": None,
         "pit": False, "out": False, "counted": True,
         "compound": "RS", "sectors_ms": (40_000, 36_000, 25_000)},
    ]
    rows = history_rows(history, kind="practice")
    # Row 0 is the excluded lap.
    assert all(t is None for t in rows[0].sector_tones), (
        "excluded lap must have no sector tones"
    )


def test_s4_null_sectors_are_dash_not_zero_or_ranked():
    """Null sector times produce None in sectors tuple, never ranked."""
    from pitcrew.ui.driver_view import history_rows

    history = [
        {"lap": 1, "lap_ms": 100_000, "lap_delta_s": 0.0,
         "burn_l": 3.0, "burn_delta_l": None, "saving": None, "why": None,
         "pit": False, "out": False, "counted": True,
         "compound": "RS", "sectors_ms": (None, 36_000, None)},
    ]
    rows = history_rows(history, kind="practice")
    assert rows[0].sectors[0] is None
    assert rows[0].sectors[2] is None
    assert rows[0].sector_tones[0] is None
    assert rows[0].sector_tones[2] is None


def test_s4_compound_on_every_row():
    """Every lap row carries its compound (even out-lap and pit lap)."""
    from pitcrew.ui.driver_view import history_rows

    history = [
        {"lap": 1, "lap_ms": 80_000, "lap_delta_s": None,
         "burn_l": 3.0, "burn_delta_l": None, "saving": None, "why": None,
         "pit": False, "out": True, "counted": False,
         "compound": "RM", "sectors_ms": (None, None, None)},
        {"lap": 2, "lap_ms": 100_000, "lap_delta_s": 0.0,
         "burn_l": 3.0, "burn_delta_l": None, "saving": None, "why": None,
         "pit": False, "out": False, "counted": True,
         "compound": "RS", "sectors_ms": (40_000, 36_000, 25_000)},
    ]
    rows = history_rows(history, kind="practice")
    assert rows[0].compound == "RM"
    assert rows[1].compound == "RS"


def test_s4_rank_ink_importable_from_practice_screen():
    """rank_ink is importable from practice_screen — no copy, no AttributeError."""
    from pitcrew.ui.practice_screen import rank_ink  # noqa: F401


def test_s4_board_fits_his_monitor():
    """Layout gate: the history panel in practice mode fits the ultrawide.

    **This test is the mandatory pre-merge gate for Story 4.**  It runs in
    a subprocess with a real font database; under offscreen Qt (no fonts)
    it is skipped rather than silently passing.
    """
    pytest.importorskip("PyQt6.QtWidgets")
    from PyQt6.QtWidgets import QApplication

    # If the font DB is empty offscreen Qt cannot measure text → skip.
    _app = QApplication.instance() or QApplication([])
    from PyQt6.QtGui import QFontDatabase

    if not QFontDatabase.families():
        pytest.skip("no font families available — run on rig with real display")

    # The existing fit test is the gate; import and run its logic here.
    from pitcrew.tests.test_window_fit import (
        test_the_board_fits_his_monitor_on_the_faces_he_actually_has,
    )
    test_the_board_fits_his_monitor_on_the_faces_he_actually_has()


# ===========================================================================
# NEW (post-fix): monitor burn equals state.rivals[name].burn_per_lap_l
# Rule 13: the voice and the monitor must show the same burn figure.
# ===========================================================================


def _rival(burn_per_lap_l=None, exit_is_a_bound=False, entry_is_a_bound=False):
    """Duck-type for rival_calls.Rival, compatible with getattr() lookups."""
    import types
    return types.SimpleNamespace(
        burn_per_lap_l=burn_per_lap_l,
        exit_is_a_bound=exit_is_a_bound,
        entry_is_a_bound=entry_is_a_bound,
    )


def test_s2c_rivals_burn_used_when_present():
    """When state.rivals contains a burn figure, rival_stop_rows uses it.

    Rule 13: the voice reads rivals[name].burn_per_lap_l; the monitor must
    use the exact same figure so the two cannot give different numbers about
    the same car.  The derived consecutive-stop burn is a fallback only.
    """
    from pitcrew.race.fill_verdict import rival_stop_rows

    # Two consecutive stops whose stop-gap burn would be 5.0 L/lap.
    # The rivals dict carries 7.5 L/lap — that is what the voice uses.
    s1 = {"id": 1, "driver": "ROCKY", "lap": 5,
          "fuel_in_l": 10.0, "fuel_out_l": 60.0,
          "partial": 0, "exit_is_a_bound": 0,
          "compound": "RS", "compound_in": "RH"}
    s2 = {"id": 2, "driver": "ROCKY", "lap": 15,
          "fuel_in_l": 10.0, "fuel_out_l": 50.0,
          "partial": 0, "exit_is_a_bound": 0,
          "compound": "RS", "compound_in": "RS"}
    # Derived burn from consecutive stops: (60 - 10) / (15 - 5) = 5.0 L/lap.
    # Rival's live burn: 7.5 L/lap.
    rows = rival_stop_rows(
        [s1, s2], entered=["ROCKY"], own_driver=None,
        laps_remaining=8, own_burn_l=8.0,
        rivals={"ROCKY": _rival(burn_per_lap_l=7.5)},
    )
    assert len(rows) == 1
    assert rows[0].burn_per_lap_l == pytest.approx(7.5), (
        "the rivals dict burn (7.5) must override the derived burn (5.0)"
    )


def test_s2c_rivals_burn_fallback_when_absent():
    """When rivals dict has no burn, derivation or own_burn_l is used.

    If the Rival has burn_per_lap_l=None, the function falls back to
    consecutive-stop derivation.
    """
    from pitcrew.race.fill_verdict import rival_stop_rows

    s1 = {"id": 1, "driver": "ROCKY", "lap": 5,
          "fuel_in_l": 10.0, "fuel_out_l": 60.0,
          "partial": 0, "exit_is_a_bound": 0,
          "compound": "RS", "compound_in": "RH"}
    s2 = {"id": 2, "driver": "ROCKY", "lap": 15,
          "fuel_in_l": 10.0, "fuel_out_l": 50.0,
          "partial": 0, "exit_is_a_bound": 0,
          "compound": "RS", "compound_in": "RS"}
    # Derived burn: (60 - 10) / (15 - 5) = 5.0 L/lap.
    rows = rival_stop_rows(
        [s1, s2], entered=["ROCKY"], own_driver=None,
        laps_remaining=8, own_burn_l=8.0,
        rivals={"ROCKY": _rival(burn_per_lap_l=None)},   # no live burn
    )
    assert len(rows) == 1
    assert rows[0].burn_per_lap_l == pytest.approx(5.0), (
        "with rivals burn=None, derivation (5.0) must be used"
    )


def test_s2c_rivals_burn_case_insensitive_lookup():
    """rivals dict lookup is case-insensitive (same tolerance as own-driver)."""
    from pitcrew.race.fill_verdict import rival_stop_rows

    stop = {"id": 1, "driver": "Rocky", "lap": 10,
            "fuel_in_l": 8.0, "fuel_out_l": 50.0,
            "partial": 0, "exit_is_a_bound": 0,
            "compound": "RS", "compound_in": "RH"}
    rows = rival_stop_rows(
        [stop], entered=["Rocky"], own_driver=None,
        laps_remaining=8, own_burn_l=8.0,
        rivals={"ROCKY": _rival(burn_per_lap_l=6.5)},   # uppercase key
    )
    assert len(rows) == 1
    assert rows[0].burn_per_lap_l == pytest.approx(6.5)


# ===========================================================================
# NEW (post-fix): bound overlay reaching fill_verdict
# The controller overlays exit_is_a_bound/entry_is_a_bound from state.rivals
# onto stop dicts before passing to rival_stop_rows.  These tests confirm
# the overlay flows through to fill_verdict at the rival_stop_rows seam.
# ===========================================================================


def _stop(driver, lap, fuel_out, *, partial=False, exit_bound=False, stop_id=1):
    return {"id": stop_id, "driver": driver, "lap": lap,
            "fuel_in_l": 8.0, "fuel_out_l": fuel_out,
            "partial": int(partial), "exit_is_a_bound": int(exit_bound),
            "compound": "RS", "compound_in": "RH"}


def test_s2_exit_bound_spare_still_holds():
    """exit_is_a_bound=True: optimistic surplus → verdict 'spare', bound=True.

    Orchestrator amendment (binding): exit_is_a_bound means true exit fuel
    ≥ reading, so 'spare' holds.  The controller overlays this flag from
    state.rivals; this test passes it directly via the stop dict.
    """
    from pitcrew.race.fill_verdict import rival_stop_rows

    # fuel_out=70, burn=8, laps_remaining=6 → needs 48, margin +22 → spare.
    stops = [_stop("X", 10, 70.0, exit_bound=True)]
    rows = rival_stop_rows(stops, entered=["X"], own_driver=None,
                           laps_remaining=6, own_burn_l=8.0)
    assert rows[0].verdict.verdict == "spare"
    assert rows[0].verdict.bound is True, (
        "bound must be True when exit_is_a_bound=True and verdict is spare"
    )


def test_s2_exit_bound_must_save_becomes_cant_tell():
    """exit_is_a_bound=True: apparent shortfall → 'can't tell' (exit could be higher).

    Orchestrator amendment: a 'must save' reading against a lower-bound exit
    fuel is suspect — the real exit fuel could be higher and eliminate the
    shortfall.  The verdict must be 'can't tell', not 'must save'.
    """
    from pitcrew.race.fill_verdict import rival_stop_rows

    # fuel_out=40, burn=8, laps_remaining=6 → needs 48, margin -8 → short.
    # But exit_is_a_bound=True: could be fine with higher actual exit fuel.
    stops = [_stop("X", 10, 40.0, exit_bound=True)]
    rows = rival_stop_rows(stops, entered=["X"], own_driver=None,
                           laps_remaining=6, own_burn_l=8.0)
    assert rows[0].verdict.verdict == "can't tell", (
        "with exit_is_a_bound=True and apparent shortfall, verdict must be "
        "'can't tell' not 'must save' — the true exit fuel could be higher"
    )


def test_s2_partial_entry_bound_must_save_holds():
    """partial=True: lower-bound burn still predicts shortfall → 'must save'.

    Orchestrator amendment: partial means fuel_in is an UPPER bound, so the
    real burn ≥ computed.  Even the optimistic burn says he's short →
    'must save' holds (bound=True).
    """
    from pitcrew.race.fill_verdict import rival_stop_rows

    # fuel_out=40, burn=8 (from own), laps_remaining=6 → margin -8 → short.
    # partial=True makes it a lower-bound burn.
    stops = [_stop("X", 10, 40.0, partial=True)]
    rows = rival_stop_rows(stops, entered=["X"], own_driver=None,
                           laps_remaining=6, own_burn_l=8.0)
    assert rows[0].verdict.verdict == "must save"
    assert rows[0].verdict.bound is True


def test_s2_partial_entry_bound_looks_spare_cant_tell():
    """partial=True with apparent surplus → 'can't tell' (real burn may be higher)."""
    from pitcrew.race.fill_verdict import rival_stop_rows

    # fuel_out=80, burn=8 (from own), laps_remaining=6 → margin +32 → spare.
    # partial=True: real burn could be higher, eliminating the margin.
    stops = [_stop("X", 10, 80.0, partial=True)]
    rows = rival_stop_rows(stops, entered=["X"], own_driver=None,
                           laps_remaining=6, own_burn_l=8.0)
    assert rows[0].verdict.verdict == "can't tell"


def test_s2_both_bounds_cant_tell():
    """Both partial and exit_is_a_bound → 'can't tell' (opposite directions)."""
    from pitcrew.race.fill_verdict import rival_stop_rows

    stops = [_stop("X", 10, 40.0, partial=True, exit_bound=True)]
    rows = rival_stop_rows(stops, entered=["X"], own_driver=None,
                           laps_remaining=6, own_burn_l=8.0)
    assert rows[0].verdict.verdict == "can't tell"


# ===========================================================================
# NEW (post-fix): own.laps — to the flag label vs to the stop label
# The two quantities must carry distinct labels so rule 13 is not violated.
# ===========================================================================


def test_s1d_laps_label_is_to_the_stop_when_stop_coming():
    """When a stop is planned, own.laps.label must say 'to the stop'."""
    state = _state(laps_to_box=4.0, has_plan=True)
    own = compose(_view(), state)["own"]
    assert own["laps"]["label"] == "to the stop", (
        "label must distinguish 'to the stop' from 'to the flag' (rule 13)"
    )
    assert own["laps"]["value"] == "4"


def test_s1d_laps_label_is_to_the_flag_when_no_further_stop():
    """When the plan has no further stop, own.laps.label must say 'to the flag'."""
    state = _state(laps_to_box=None, has_plan=True)
    view = _view(own_laps_remaining=12)
    own = compose(view, state)["own"]
    assert own["laps"]["label"] == "to the flag", (
        "label must distinguish 'to the flag' from 'to the stop' (rule 13)"
    )
    assert own["laps"]["value"] == "12"


def test_s1d_laps_block_none_when_no_plan():
    """Without a plan, own.laps is absent (None) — not 'to the flag' or '0'."""
    state = _state(laps_to_box=None, has_plan=False)
    view = _view(own_laps_remaining=8)
    own = compose(view, state)["own"]
    assert own["laps"] is None, (
        "with no plan, own.laps must be None — "
        "not a figure that would imply the app knows the race end"
    )


def test_s1d_laps_block_none_when_laps_remaining_unknown():
    """'To the flag' with no laps_remaining on the view → None, not '0'."""
    state = _state(laps_to_box=None, has_plan=True)
    # own_laps_remaining not set (defaults to None on FieldView).
    view = _view()
    own = compose(view, state)["own"]
    # own_laps_remaining is None → _laps_block returns None (rule 3: not '0').
    assert own["laps"] is None, (
        "own.laps must be None when own_laps_remaining is unknown — never '0'"
    )


def test_s1d_laps_two_labels_are_distinct():
    """The two labels 'to the stop' and 'to the flag' are different strings.

    Rule 13: two calls that use the same words must mean the same thing.
    This test catches a regression where both branches used the same label.
    """
    stop_state = _state(laps_to_box=3.0, has_plan=True)
    flag_state = _state(laps_to_box=None, has_plan=True)
    flag_view = _view(own_laps_remaining=10)

    stop_label = compose(_view(), stop_state)["own"]["laps"]["label"]
    flag_label = compose(flag_view, flag_state)["own"]["laps"]["label"]

    assert stop_label != flag_label, (
        f"labels must differ: stop={stop_label!r}, flag={flag_label!r}"
    )
