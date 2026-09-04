"""A session's opening lap is an out-lap when it left the pit box - and the
stored flag has to say so, not just the rack.

The live flag came from a pit EXIT, which needs a pit ENTRY first; a lap that
begins already in the box never has one, so every lobby opener reached the
database as `is_out_lap = 0`. Sessions 122 and 123 at Daytona (4 Sep 2026)
stored a 91.6 s and a 91.8 s "lap 1" against a 104 s lap, and
`min(lap_time_ms)` over the event returned 93.100 s - a pit-exit-to-line
fragment.

The numbers below are the real ones: `standing_start_ms` as the recorder
measured it on the sessions named.
"""
from __future__ import annotations

from pitcrew.analysis.runs import (
    LOBBY,
    TIME_TRIAL,
    auto_out_laps,
    flag_opening_lap,
    opening_lap_verdict,
)
from pitcrew.analysis.session import LapInput
from pitcrew.telemetry.session_state import Lap


def a_live_lap(lap_num: int, lap_time_ms: int, **overrides) -> Lap:
    fields = dict(lap_num=lap_num, lap_time_ms=lap_time_ms, best_lap_ms=0,
                  delta_ms=0, fuel_start=100.0, fuel_end=92.6, fuel_used=7.4,
                  position=1, is_pit_lap=False, is_out_lap=False)
    fields.update(overrides)
    return Lap(**fields)


def a_stint(count: int, *, session_id: int = 1, **overrides) -> list[LapInput]:
    return [LapInput(lap_num=n + 1, lap_time_ms=105_000,
                     fuel_start=100.0 - 7.5 * n, fuel_end=100.0 - 7.5 * (n + 1),
                     session_id=session_id, **overrides)
            for n in range(count)]


# ------------------------------------------------------------ the verdict

def test_a_partial_first_lap_out_of_the_box_is_an_out_lap():
    """Session 122: declared lobby, 31.6 s at rest in the box, 91.587 s from
    the pit exit to the line."""
    verdict = opening_lap_verdict(session_kind="practice", practice_mode=LOBBY,
                                  standing_start_ms=31_600)
    assert verdict.is_out_lap is True
    assert "at rest" in verdict.reason


def test_a_race_standing_start_is_a_full_lap_and_not_an_out_lap():
    """Session 118: 83.9 s at rest - on the GRID, not in the pits. Its first
    lap is a full lap from a standing start and counts."""
    verdict = opening_lap_verdict(session_kind="race", practice_mode=None,
                                  standing_start_ms=83_883)
    assert verdict.is_out_lap is False
    assert "grid" in verdict.reason


def test_a_time_trial_starts_rolling_on_track_and_its_first_lap_counts():
    """Every time-trial opener on file begins rolling at 135-272 km/h."""
    verdict = opening_lap_verdict(session_kind="practice",
                                  practice_mode=TIME_TRIAL, standing_start_ms=0)
    assert verdict.is_out_lap is False


def test_the_declaration_wins_over_the_frames_and_the_disagreement_is_named():
    """Rule 1: the driver's report is primary. A time trial that the frames
    show at rest is a disagreement to surface, not to resolve silently."""
    verdict = opening_lap_verdict(session_kind="practice",
                                  practice_mode=TIME_TRIAL,
                                  standing_start_ms=12_000)
    assert verdict.is_out_lap is False
    assert "declaration stands" in verdict.reason


def test_an_undeclared_session_that_began_at_rest_began_in_the_box():
    """Only a lobby session's car is stationary at its first frame."""
    verdict = opening_lap_verdict(session_kind="practice", practice_mode=None,
                                  standing_start_ms=533)
    assert verdict.is_out_lap is True


def test_an_undeclared_session_picked_up_rolling_cannot_be_placed():
    """Rule 3: the recording caught the car late. Not a guess either way."""
    rolling = opening_lap_verdict(session_kind="practice", practice_mode=None,
                                  standing_start_ms=0)
    no_frames = opening_lap_verdict(session_kind="practice", practice_mode=None,
                                    standing_start_ms=None)
    assert rolling.is_out_lap is None
    assert no_frames.is_out_lap is None


def test_a_lobby_opener_the_recording_caught_rolling_is_still_an_out_lap():
    """The declaration is what decides; the frames only corroborate."""
    verdict = opening_lap_verdict(session_kind="practice", practice_mode=LOBBY,
                                  standing_start_ms=0)
    assert verdict.is_out_lap is True
    assert "neither confirm nor deny" in verdict.reason


# ----------------------------------------------------------- the live path

def test_the_live_path_sets_the_flag_on_a_lobby_opener_before_it_is_stored():
    lap = a_live_lap(1, 91_587)
    flagged, verdict = flag_opening_lap(lap, session_kind="practice",
                                        practice_mode=LOBBY,
                                        standing_start_ms=31_600)
    assert flagged.is_out_lap is True
    assert verdict is not None and verdict.is_out_lap is True
    # Everything else on the lap is exactly as the session state built it.
    assert flagged.lap_time_ms == 91_587 and flagged.fuel_end == 92.6


def test_the_live_path_leaves_a_race_opener_alone():
    lap = a_live_lap(1, 115_211)
    flagged, verdict = flag_opening_lap(lap, session_kind="race",
                                        practice_mode=None,
                                        standing_start_ms=83_883)
    assert flagged.is_out_lap is False
    assert verdict is not None and verdict.is_out_lap is False


def test_the_live_path_does_not_touch_lap_two():
    lap = a_live_lap(2, 104_504)
    same, verdict = flag_opening_lap(lap, session_kind="practice",
                                     practice_mode=LOBBY, standing_start_ms=0)
    assert same is lap and verdict is None
    assert same.is_out_lap is False


def test_the_live_path_never_guesses_and_never_clears():
    """`None` leaves the flag as recorded; a flag already set is not judged."""
    lap = a_live_lap(1, 105_000)
    same, verdict = flag_opening_lap(lap, session_kind="practice",
                                     practice_mode=None, standing_start_ms=0)
    assert same.is_out_lap is False and verdict.is_out_lap is None

    already = a_live_lap(1, 105_000, is_out_lap=True)
    same, verdict = flag_opening_lap(already, session_kind="practice",
                                     practice_mode=TIME_TRIAL,
                                     standing_start_ms=0)
    assert same.is_out_lap is True and verdict is None


# --------------------------------------------- the rack reaches the same answer

def test_the_rack_rule_agrees_with_the_verdict():
    """`auto_out_laps` is what `_rows_for_event` and the export apply; it
    must name the same opener the live path flagged (rule 13)."""
    lobby = a_stint(5, practice_mode=LOBBY, standing_start_ms=31_600)
    assert auto_out_laps(lobby) == {1}, "lap 1 struck, lap 2 onward counted"

    time_trial = a_stint(5, practice_mode=TIME_TRIAL, standing_start_ms=0)
    assert auto_out_laps(time_trial) == set()

    # The declaration wins on the rack exactly as it does live.
    declared_tt_at_rest = a_stint(5, practice_mode=TIME_TRIAL,
                                  standing_start_ms=12_000)
    assert auto_out_laps(declared_tt_at_rest) == set()
