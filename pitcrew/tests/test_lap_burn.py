"""A lap that ends with a fuller tank was filled, not un-burned.

Two Fuji rows carried `fuel_used = 0.0` on laps that plainly used fuel:

* **lap 1**, whose reference was the 49.92 L lobby tank, read 78 s before the
  game filled the car to 100 L on the grid - the lap "used" −44 L;
* **the pit lap**, where refuelling put 28.6 L in and the lap took ~6 L out.

Both went negative and both were clamped to zero, which is a positive claim of
nothing used rather than an admission. Neither is a lap the app cannot measure:
both were missing a term.

**And the null that looks like the obvious fix is a crash.** `laps.fuel_used`
is `NOT NULL DEFAULT 0.0`, and a None reaches `if lap.fuel_used > 0` in the
race coordinator and the practice screen. An unhandled TypeError inside a Qt
slot does not raise on Windows - it aborts the process. Reproduced: the whole
of `test_race_wiring.py` died with `0xC0000409` and no traceback.
"""
from __future__ import annotations

import pytest

from pitcrew.telemetry.session_state import (
    GRID_FILL_STEP_L,
    SessionState,
    _burn,
)

from .conftest import make_packet


# --------------------------------------------------------- the arithmetic

def test_an_ordinary_lap_is_the_difference():
    assert _burn(94.2, 88.1) == pytest.approx(6.1)


def test_a_pit_lap_counts_the_fuel_that_went_in():
    """Fuji's stop: 70.784 L on entry, 99.426 L at exit, 28.642 L added."""
    # Started the lap with 76.3, ended with 99.4, and 28.6 went in during it:
    # the real burn is 5.5, not the -23.1 the bare difference gives.
    assert _burn(76.3, 99.4, 28.642) == pytest.approx(5.542, abs=0.01)


def test_the_result_is_never_negative_and_never_none():
    """None is not available here - see the module docstring."""
    used = _burn(49.92, 94.2)

    assert used is not None
    assert isinstance(used, float)
    assert used >= 0.0


def test_a_missing_reading_is_zero_rather_than_a_crash():
    for pair in ((None, 90.0), (90.0, None), (None, None)):
        assert _burn(*pair) == 0.0


def test_a_fill_bigger_than_the_lap_still_reads_as_used_not_as_none():
    assert _burn(90.0, 99.0, 20.0) == pytest.approx(11.0)


# ------------------------------------------------- the grid re-baselining

def test_the_grid_fill_step_is_far_above_a_real_refuel():
    """GT7 fills at ~1 L/s against a 60 Hz stream: 0.0167 L per frame."""
    per_frame_l = 1.0 / 60.0

    assert GRID_FILL_STEP_L > per_frame_l * 50, (
        "a gate this low would re-baseline in the middle of a pit stop")


def test_lap_one_takes_its_reference_from_the_grid_not_the_lobby():
    """The whole of the lap-1 defect, end to end through the real detector."""
    state = SessionState()
    # Lobby: on track, stationary, part-filled. This is what used to be stamped
    # as lap one's reference.
    state.update(make_packet(speed_ms=0.0, fuel_level=49.88, laps_in_race=20))
    state.update(make_packet(speed_ms=0.0, fuel_level=49.88, laps_in_race=20))
    # The game fuels the car on the grid, in one frame, still stationary.
    state.update(make_packet(speed_ms=0.0, fuel_level=100.0, laps_in_race=20))

    assert state._fuel_lap_start == pytest.approx(100.0), (
        "lap one is still referenced to the lobby tank")


def test_a_moving_car_does_not_re_baseline():
    """Only before the green, and only stationary - a rising tank at speed is
    not a grid fill, and re-stamping there would erase a real stint."""
    state = SessionState()
    state.update(make_packet(speed_ms=0.0, fuel_level=50.0, laps_in_race=20))
    state.update(make_packet(speed_ms=50.0, fuel_level=50.0, laps_in_race=20))
    state.update(make_packet(speed_ms=50.0, fuel_level=100.0, laps_in_race=20))

    assert state._fuel_lap_start == pytest.approx(50.0)


def test_a_small_rise_does_not_re_baseline():
    """A real refuel moves 0.0167 L per frame. Only a step qualifies."""
    state = SessionState()
    state.update(make_packet(speed_ms=0.0, fuel_level=50.0, laps_in_race=20))
    state.update(make_packet(speed_ms=0.0, fuel_level=50.02, laps_in_race=20))

    assert state._fuel_lap_start == pytest.approx(50.0)


# ----------------------------------------- the decision, said out loud

class _Kept:
    """Stands in for `log("session")` and keeps what it was told."""

    def __init__(self):
        self.lines = []

    def info(self, msg, *args, **_):
        self.lines.append(msg % args if args else msg)

    debug = warning = error = exception = info


def _kept_session_log(monkeypatch) -> _Kept:
    import pitcrew.telemetry.session_state as session_state

    kept = _Kept()
    monkeypatch.setattr(session_state, "log", lambda *_a, **_k: kept)
    return kept


def test_the_grid_re_baseline_says_that_it_fired(monkeypatch):
    """**Rule 10: log the accepts, not only the refusals.**

    Bathurst, 20 Sep 2026: lap 1 filed `fuel_used 0.0` on a lap that burned
    about 8.67 L. The frames carry a single-frame 49.977 -> 100.0 L step at
    0 km/h, 23 s before the green - every stated precondition of this guard -
    and nobody could say why it had not fired, because it said nothing either
    way.
    """
    kept = _kept_session_log(monkeypatch)
    state = SessionState()
    state.update(make_packet(speed_ms=0.0, fuel_level=49.977, laps_in_race=20))
    state.update(make_packet(speed_ms=0.0, fuel_level=49.977, laps_in_race=20))
    state.update(make_packet(speed_ms=0.0, fuel_level=100.0, laps_in_race=20))

    said = [line for line in kept.lines if "grid fill" in line]
    assert len(said) == 1, said
    assert "re-baselined lap one" in said[0]
    for figure in ("49.98", "100.00", "50.02"):
        assert figure in said[0], said[0]


def test_the_grid_re_baseline_says_why_it_declined(monkeypatch):
    """The decline is the line that was missing on the night, and it has to
    carry the value that decided it - not merely the fact of a refusal."""
    kept = _kept_session_log(monkeypatch)
    state = SessionState()
    state.update(make_packet(speed_ms=0.0, fuel_level=50.0, laps_in_race=20))
    state.update(make_packet(speed_ms=50.0, fuel_level=50.0, laps_in_race=20))
    state.update(make_packet(speed_ms=50.0, fuel_level=100.0, laps_in_race=20))

    said = [line for line in kept.lines if "grid fill" in line]
    assert len(said) == 1, said
    assert "did NOT re-baseline" in said[0]
    assert "180.0 km/h" in said[0] and "50.00" in said[0]
    # ...and saying so changed nothing about what it does.
    assert state._fuel_lap_start == pytest.approx(50.0)


def test_a_fill_that_arrives_on_a_paused_frame_is_said_to_have_been_missed(
        monkeypatch):
    """**The guard can be refused, or it can never be asked, and those look
    identical on disk.**

    `update` returns on a paused or loading packet and advances `_prev` as it
    goes, so a fill landing on one of those frames is consumed before
    `_rebaseline_on_grid_fill` runs - and the recorder drops those frames too,
    so no stored lap can show it afterwards. On the Bathurst race of 20 Sep
    2026 the stored frames carry the 49.977 -> 100.0 L step at 0 km/h with
    every precondition met, and replaying them re-baselines correctly; the
    live run did not. This line is what separates the two explanations.
    """
    kept = _kept_session_log(monkeypatch)
    state = SessionState()
    state.update(make_packet(speed_ms=0.0, fuel_level=49.977, laps_in_race=20))
    state.update(make_packet(speed_ms=0.0, fuel_level=100.0, laps_in_race=20,
                             flags_raw=0x0001 | 0x0002))    # paused

    said = [line for line in kept.lines if "never saw it" in line]
    assert len(said) == 1, kept.lines
    assert "50.02 L fill" in said[0] and "paused" in said[0]
    assert state._fuel_lap_start == pytest.approx(49.977), (
        "saying so must not change what it does")


def test_an_ordinary_frame_says_nothing_about_the_grid_fill(monkeypatch):
    """This runs on every packet at 60 Hz. Only a step big enough to BE the
    grid fill is ever spoken about; a log that floods is a log nobody reads."""
    kept = _kept_session_log(monkeypatch)
    state = SessionState()
    for litres in (50.0, 49.98, 49.96, 49.94):
        state.update(make_packet(speed_ms=0.0, fuel_level=litres,
                                 laps_in_race=20))

    assert [line for line in kept.lines if "grid fill" in line] == []


# ------------------------------------------------------- the crash itself

def test_the_consumers_that_abort_a_qt_slot_are_never_handed_a_none():
    """`if lap.fuel_used > 0` appears in the coordinator and the practice
    screen. On Windows a TypeError there aborts the process rather than
    raising, so this is the guard that keeps the app alive mid-race."""
    for started, ended, added in ((49.92, 94.2, None), (None, 90.0, None),
                                  (76.3, 99.4, 28.6), (90.0, 90.0, None)):
        used = _burn(started, ended, added)
        assert used > 0 or used == 0.0     # the comparison itself must work
