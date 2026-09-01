"""The teleport, which neither length check could ever see.

`analysis/distance` already anchors each lap onto the circuit's true length and
nulls the ones that cannot be anchored — a fragment, or a lap that swallowed a
crossing. Both of those are visible as a wrong LENGTH.

A teleport is not. The speed channel reads zero through a track reset, so the
integrated length comes out perfectly plausible and the lap passes both the
circuit tolerance and `length_gate`, carrying corner windows for a lap that was
driven partly somewhere else. Measured 1 Sep 2026: 7% of stored laps.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from pitcrew.analysis.distance import (
    CIRCUIT_TOLERANCE,
    TELEPORT_STEP_M,
    anchor,
    teleports,
)

TRUE = 5793.0


def _frames(count: int, step: float = 1.4, jump_at: int | None = None,
            jump: float = 400.0):
    out, x = [], 0.0
    for i in range(count):
        if jump_at is not None and i == jump_at:
            x += jump
        else:
            x += step
        out.append({"pos_x": x, "pos_y": 0.0, "pos_z": 0.0,
                    "speed_kph": 200.0,
                    "lap_distance_m": round(i * step, 2)})
    return out


# `anchor` rebuilds laps with `dataclasses.replace`, so the stub has to be one.
@dataclass
class _Lap:
    lap_num: int = 1
    frames: list = field(default_factory=list)


def test_an_ordinary_lap_has_not_teleported():
    assert not teleports(_frames(500)).happened


def test_a_reset_is_found_and_measured():
    found = teleports(_frames(500, jump_at=250, jump=402.0))
    assert found.happened
    assert found.count == 1
    assert found.longest_m == pytest.approx(402.0)
    assert "402 m" in found.describe()


def test_a_run_of_dropped_packets_is_not_a_teleport():
    """Real motion across a gap in the stream. At 200 km/h it would take
    thirty consecutive dropped packets to reach the threshold."""
    assert not teleports(_frames(200, jump_at=100, jump=8.0)).happened


def test_the_threshold_sits_clear_of_both_faults_rather_than_between_them():
    """300 km/h at 60 Hz is 1.4 m per frame. The smallest teleport in the
    archive is 302 m. The count is the same at 10 m as at 25."""
    fastest_real_step = 300.0 / 3.6 / 60.0
    assert fastest_real_step < 1.5
    assert TELEPORT_STEP_M > fastest_real_step * 10
    assert TELEPORT_STEP_M < 300.0


def test_missing_position_is_neither_a_jump_nor_a_stop():
    frames = _frames(100)
    frames[50] = {**frames[50], "pos_x": None, "pos_y": None, "pos_z": None}
    assert not teleports(frames).happened


def test_a_lap_with_no_position_channel_reports_nothing():
    assert not teleports([{"speed_kph": 100.0} for _ in range(50)]).happened
    assert not teleports([]).happened
    assert not teleports(None).happened


# ------------------------------------------------------------------ anchor

def _length(lap):
    return max(f["lap_distance_m"] for f in lap.frames
               if f.get("lap_distance_m") is not None)


def _at_true_length(jump_at=None):
    """A lap whose INTEGRATED length is exactly right — which is the whole
    point: a teleport does not show up as a wrong length."""
    frames = _frames(500, jump_at=jump_at)
    scale = TRUE / max(f["lap_distance_m"] for f in frames)
    return _Lap(1, [{**f, "lap_distance_m": round(f["lap_distance_m"] * scale, 2)}
                    for f in frames])


def test_a_teleported_lap_passes_every_length_check_and_is_still_refused():
    lap = _at_true_length(jump_at=250)
    assert abs(_length(lap) - TRUE) < TRUE * CIRCUIT_TOLERANCE, (
        "the premise: its length is perfectly plausible")

    result = anchor([lap], TRUE)
    assert len(result.teleported) == 1
    assert not result.refused, "it is not a wrong-length lap and must not say so"
    assert all(f["lap_distance_m"] is None for f in result.laps[0].frames)


def test_a_clean_lap_is_not_touched_by_the_teleport_check():
    result = anchor([_at_true_length()], TRUE)
    assert not result.teleported
    assert result.laps[0].frames[10]["lap_distance_m"] is not None


def test_the_export_names_the_teleported_laps_separately():
    """A caller reporting "could not be anchored" would otherwise tell the
    driver his lap was the wrong length when it was the right length driven in
    two places."""
    lap = _at_true_length(jump_at=250)
    lap.lap_num = 7
    said = anchor([lap], TRUE).as_export()
    assert said["lapsTeleported"] == 1
    assert said["teleportedLaps"][0]["lap"] == 7
    assert said["teleportedLaps"][0]["jumpM"] > 300
    assert said["lapsRefused"] == 0
