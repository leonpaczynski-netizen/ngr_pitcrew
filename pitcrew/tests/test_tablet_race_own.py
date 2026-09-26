"""The tablet's own-car block — Story 1, 25 Sep 2026.

`compose()` now accepts an optional DriverState and adds an "own" key.  These
tests hold the three properties the brief lists as mandatory: the box value is
"NOW" on the in-lap (never "0"), the gap is drawn "--" when expired, and the
stint averages are null when fewer than two qualifying laps exist.
"""
from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pitcrew.race.field import FieldView, OwnGap  # noqa: E402
from pitcrew.ui.driver_view import DriverState  # noqa: E402
from pitcrew.ui.tablet import compose  # noqa: E402


# ----------------------------------------- helpers


def _view(**kw) -> FieldView:
    return FieldView(position=5, lap=10, laps_total=20, **kw)


def _state(**kw) -> DriverState:
    return DriverState(**kw)


# ----------------------------------------- box label on the in-lap


def test_compose_box_label_on_in_lap_is_NOW_not_zero():
    """box_block returns "NOW" on the in-lap - own.box and own.laps must agree."""
    # laps_to_box=0 clamps but laps_past_box=0 triggers the in-lap branch.
    state = _state(laps_to_box=0.0, laps_past_box=0, has_plan=True)
    body = compose(_view(), state)
    assert "own" in body
    assert body["own"]["box"]["value"] == "NOW"
    # Rule 13: own.laps.value is verbatim from box_block — same "NOW", never "0".
    assert body["own"]["laps"]["value"] == "NOW"
    assert body["own"]["laps"]["value"] != "0"


def test_compose_own_block_absent_without_state():
    """Without a DriverState the "own" key must be absent, not null."""
    body = compose(_view())
    assert "own" not in body


def test_compose_own_block_present_with_state():
    """Any DriverState causes the own key to appear."""
    body = compose(_view(), _state())
    assert "own" in body


def test_compose_own_none_when_view_is_none():
    """compose(None) is idle, no own key."""
    body = compose(None, _state())
    assert body["idle"] is True
    assert "own" not in body


# ----------------------------------------- gap unread flag


def test_own_gap_unread_when_expired():
    """When the gap cannot stand (`unread=True`), gap_s is null."""
    view = _view(
        own_gap_ahead=OwnGap(gap_s=None, unread=True, trend=None,
                             rate_s_per_lap=None),
    )
    body = compose(view, _state())
    ga = body["own"]["gap_ahead"]
    assert ga is not None
    assert ga["unread"] is True
    assert ga["gap_s"] is None


def test_own_gap_null_when_no_car_ahead():
    """P1 has no car ahead - gap_ahead should be null in the payload."""
    body = compose(_view(own_gap_ahead=None), _state())
    assert body["own"]["gap_ahead"] is None


# ----------------------------------------- stint averages


def test_stint_averages_null_when_fewer_than_two_laps():
    """FieldView with no stint data produces null stint fields."""
    body = compose(_view(), _state())
    own = body["own"]
    assert own["stint_lap_delta_ms"] is None
    assert own["stint_lap_laps"] is None
    assert own["stint_burn_delta_l"] is None
    assert own["stint_burn_laps"] is None


def test_stint_averages_carried_when_populated():
    """FieldView with two-lap averages passes them through unchanged."""
    view = _view(
        own_stint_lap_delta_ms=250,
        own_stint_lap_laps=3,
        own_stint_burn_delta_l=0.15,
        own_stint_burn_laps=3,
    )
    body = compose(view, _state())
    own = body["own"]
    assert own["stint_lap_delta_ms"] == 250
    assert own["stint_lap_laps"] == 3
    assert own["stint_burn_delta_l"] == pytest.approx(0.15)
    assert own["stint_burn_laps"] == 3


# ----------------------------------------- round-trip integration


def test_compose_race_own_block_round_trip():
    """Build a FieldView with gap data, call compose, assert key shapes."""
    view = _view(
        own_gap_ahead=OwnGap(gap_s=1.4, unread=False,
                             trend="catching 1.2 s/lap",
                             rate_s_per_lap=1.2),
        own_gap_behind=OwnGap(gap_s=None, unread=True,
                              trend=None, rate_s_per_lap=None),
        own_stint_lap_delta_ms=300,
        own_stint_lap_laps=4,
        own_stint_burn_delta_l=-0.12,
        own_stint_burn_laps=4,
    )
    state = _state(laps_to_box=3.0, has_plan=True)
    body = compose(view, state)
    own = body["own"]
    assert own["gap_ahead"]["gap_s"] == pytest.approx(1.4)
    assert own["gap_ahead"]["trend"] == "catching 1.2 s/lap"
    assert own["gap_behind"]["unread"] is True
    assert own["stint_lap_delta_ms"] == 300
    assert body["own"]["box"]["value"] == "3"


# ----------------------------------------- temps_c


def test_own_temps_c_from_driver_state():
    """temps_c comes from the DriverState, not from the FieldView."""
    state = _state(temps_c={"fl": 95.0, "fr": 98.0, "rl": 87.0, "rr": 89.0})
    body = compose(_view(), state)
    t = body["own"]["temps_c"]
    assert t["fl"] == pytest.approx(95.0)
    assert t["rr"] == pytest.approx(89.0)


def test_own_temps_c_null_when_absent():
    """No packet readings → null, not a dict of zeros."""
    body = compose(_view(), _state(temps_c=None))
    assert body["own"]["temps_c"] is None


# ----------------------------------------- gap neighbour names (26 Sep 2026)


def test_own_gap_ahead_carries_name():
    """OwnGap.name is forwarded into the payload for the tablet to display."""
    view = _view(
        own_gap_ahead=OwnGap(gap_s=0.8, unread=False, trend="holding",
                             rate_s_per_lap=0.0, name="PUNISHED"),
    )
    body = compose(view, _state())
    assert body["own"]["gap_ahead"]["name"] == "PUNISHED"


def test_own_gap_behind_carries_name():
    """OwnGap.name from gap_behind is forwarded."""
    view = _view(
        own_gap_behind=OwnGap(gap_s=2.1, unread=False, trend="pulling away",
                              rate_s_per_lap=-0.4, name="ROCKY"),
    )
    body = compose(view, _state())
    assert body["own"]["gap_behind"]["name"] == "ROCKY"


def test_own_gap_name_null_when_absent():
    """name is null (not absent) when OwnGap has no name — rule 3."""
    view = _view(
        own_gap_ahead=OwnGap(gap_s=1.0, unread=False, trend=None,
                             rate_s_per_lap=None),
    )
    body = compose(view, _state())
    # name key must be present; its value must be None, not a missing key.
    assert "name" in body["own"]["gap_ahead"]
    assert body["own"]["gap_ahead"]["name"] is None


# ----------------------------------------- history and fuel_in_hand (26 Sep 2026)


def test_own_history_key_present():
    """history key appears in own; it is a list (may be empty, never absent)."""
    body = compose(_view(), _state())
    own = body["own"]
    assert "history" in own
    assert isinstance(own["history"], list)


def test_own_fuel_in_hand_key_present():
    """fuel_in_hand key appears in own; it is a list."""
    body = compose(_view(), _state())
    own = body["own"]
    assert "fuel_in_hand" in own
    assert isinstance(own["fuel_in_hand"], list)


def test_own_last_call_text_present():
    """last_call_text key appears in own; None when no call, str otherwise."""
    body_no_call = compose(_view(), _state())
    assert "last_call_text" in body_no_call["own"]
