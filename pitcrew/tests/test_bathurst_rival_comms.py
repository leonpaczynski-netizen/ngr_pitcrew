"""Bathurst, 14 Sep 2026 (session 176, race run 21), laps 9-14, replayed.

The driver, afterwards: *"want more comms from him about what is going on in
the race."* The pit wall filed ten rival stops and George said two of them -
"Car #76 has boxed on 5 litres", 59 s after he went in, and "TommyTbone has
boxed on 7 litres", 168 s after, with TommyTbone already back on the circuit.

This drives the coordinator through that part of the race at 60 Hz from the
log's own timestamps: the crossings, the two box calls that won laps 10 and 11,
our own stop, the off at 20:41:31, the position byte, and every rival visit -
entering when the pit wall's new filing bar would have confirmed it (13 s
after the logged second reading, the fifteen-second bar less the ~2 s between
the first two readings) and leaving when its stop was filed.

What it pins is the defect, not the wording: **every stop the wall confirmed
reaches the driver exactly once**, the box calls still own their crossings,
and the two places that were cars in the lane are not called passes.
"""
from __future__ import annotations

from dataclasses import dataclass

import pytest

from pitcrew.race import coordinator as coordinator_module
from pitcrew.race.calls import (BOX_NOW, BOX_SOON, POSITION, RIVAL_BOXED,
                                Call, next_call)
from pitcrew.race.coordinator import RaceCoordinator, RacePhase
from pitcrew.race.pit_wall import Entered


def t(clock: str) -> int:
    """`20:41:59` as seconds past 20:00:00."""
    h, m, s = (int(x) for x in clock.split(":"))
    return (h - 20) * 3600 + m * 60 + s


START, END = t("20:39:00"), t("20:52:30")

# Crossings: the pit wall's health line and the call ledger agree on these.
CROSSINGS = {t("20:39:32"): 9, t("20:41:59"): 10, t("20:44:21"): 11,
             t("20:46:40"): 12, t("20:49:51"): 13, t("20:51:57"): 14}
# What won the crossing that night where it was not a rival.
FORCED = {10: Call(BOX_SOON, 10, "Box next lap.", "Stop 1."),
          11: Call(BOX_NOW, 11, "Box this lap. RS on.", "Fuel to 67 litres.")}

# (driver, lap on file, second reading logged, stop filed, ahead of us at entry)
VISITS = [
    ("PUNISHED", 8, "20:39:52", "20:40:25", None),
    ("CruisingChaos", 9, "20:40:41", "20:43:30", None),
    ("K.Graebs", 9, "20:41:45", "20:45:34", None),
    ("Magical daddy", 10, "20:42:41", "20:43:39", None),
    ("Car #31", 10, "20:43:16", "20:44:38", True),
    ("Car #28", 10, "20:43:59", "20:46:53", True),
    ("Car #76", 11, "20:45:41", "20:50:04", None),
    ("Car #11", 11, "20:45:43", "20:47:10", None),
    ("TommyTbone", 12, "20:47:03", "20:48:16", None),
    ("Car #33", 12, "20:47:34", "20:50:52", None),
]
CONFIRM_AFTER_S = 13
# Entry fuel as filed in `rival_stops`; CruisingChaos was joined mid-fill.
FUEL_IN = {"PUNISHED": 47, "CruisingChaos": 41, "K.Graebs": 21,
           "Magical daddy": 32, "Car #31": 14, "Car #28": 17, "Car #76": 5,
           "Car #11": 6, "TommyTbone": 7, "Car #33": 15}
PARTIAL = {"CruisingChaos"}
# Car #30 entered at 20:39:32 and was discarded - 4 reads over 13 s - so under
# the filing bar it is never announced and is not in VISITS.

# The position byte, simplified to the changes the ledger shows.
POSITIONS = [(t("20:39:00"), 9), (t("20:41:59"), 8), (t("20:44:22"), 6),
             (t("20:46:20"), 8), (t("20:47:52"), 11)]
IN_PIT = (t("20:46:30"), t("20:47:50"))
OFF_TRACK = [(t("20:41:31"), t("20:41:36")), (t("20:50:49"), t("20:50:53"))]


@dataclass
class _Packet:
    current_position: int
    cars_in_race: int = 13
    surface_types: tuple = ("T", "T", "T", "T")
    laps_completed: int | None = None


def _at(series, second):
    value = series[0][1]
    for start, v in series:
        if second >= start:
            value = v
    return value


def replay(monkeypatch):
    real_next_call = next_call

    def crossing_call(state):
        forced = FORCED.get(state.lap)
        return forced if forced is not None else real_next_call(state)

    monkeypatch.setattr(coordinator_module, "next_call", crossing_call)
    co = RaceCoordinator()
    co.phase = RacePhase.RUNNING
    co.state.laps_total = 20
    co.state.lap = 8
    co.state.position = 9
    co.state.position_said = 9
    co._note_crossing_for_mid_lap()
    co._crossed_at_packet = -10 * 60        # the lap-8 crossing is well past

    enter_at = {t(second) + CONFIRM_AFTER_S: (d, lap, ahead)
                for d, lap, second, _, ahead in VISITS}
    leave_at = {t(filed): d for d, _, _, filed, _ in VISITS}
    said: list[tuple[str, str, str]] = []

    for second in range(START, END):
        if second in CROSSINGS:
            co.state.lap = CROSSINGS[second]
            co._note_crossing_for_mid_lap()
            call = co._emit()
            if call is not None:
                said.append((_clock(second), "line", call.spoken()))
        if second in enter_at:
            driver, lap, ahead = enter_at[second]
            co.note_rival_entered(Entered(driver=driver, driver_id=0, lap=lap,
                                          fuel_in_l=FUEL_IN[driver],
                                          partial=driver in PARTIAL,
                                          ahead_at_entry=ahead))
        if second in leave_at:
            co.state.lane.left(leave_at[second], lap=co.state.lap)
        co.state.in_pit = IN_PIT[0] <= second < IN_PIT[1]
        off = any(a <= second < b for a, b in OFF_TRACK)
        packet = _Packet(current_position=_at(POSITIONS, second),
                         surface_types=("G",) * 4 if off else ("T",) * 4)
        for _ in range(60):
            call = co.note_packet(packet)
            if call is not None:
                said.append((_clock(second), "mid-lap", call.spoken()))
    return co, said


def _clock(second: int) -> str:
    return f"20:{second // 60:02d}:{second % 60:02d}"


def test_every_confirmed_stop_reaches_him_exactly_once(monkeypatch):
    co, said = replay(monkeypatch)
    rival_lines = [text for _, _, text in said if "boxed" in text]
    for driver, *_ in VISITS:
        heard = [text for text in rival_lines if driver in text]
        assert len(heard) == 1, (driver, said)
    assert co.state.lane.untold(co.state.lap) == []


def test_the_box_calls_still_own_their_crossings(monkeypatch):
    _, said = replay(monkeypatch)
    lines = {when: text for when, how, text in said if how == "line"}
    assert lines["20:41:59"].startswith("Box next lap.")
    assert lines["20:44:21"].startswith("Box this lap.")


def test_the_two_cars_in_the_lane_are_not_called_passes(monkeypatch):
    _, said = replay(monkeypatch)
    p6 = [text for _, _, text in said if text.startswith("P6 of 13.")]
    assert p6 == ["P6 of 13. Not passes - 2 cars ahead boxed."]


def test_nothing_mid_lap_is_said_closer_than_the_spacing(monkeypatch):
    _, said = replay(monkeypatch)
    mid = [when for when, how, text in said
           if how == "mid-lap" and not text.startswith("You're back on it")]
    seconds = [t(when) for when in mid]
    gaps = [b - a for a, b in zip(seconds, seconds[1:])]
    assert all(gap >= RaceCoordinator.MID_LAP_SPACING_S for gap in gaps), said


def test_the_stop_is_one_line_after_he_rejoins(monkeypatch):
    _, said = replay(monkeypatch)
    after = [text for when, _, text in said
             if IN_PIT[0] <= t(when) and text.startswith("P")]
    assert after[:1] == ["P11 of 13. After your stop."]


def transcript(monkeypatch) -> list[str]:            # pragma: no cover
    """For a person: `pytest -k transcript -s` prints what he would hear."""
    _, said = replay(monkeypatch)
    return [f"{when}  {how:8}  {text}" for when, how, text in said]


def test_print_the_transcript(monkeypatch, capsys):
    lines = transcript(monkeypatch)
    print("\n".join(lines))
    assert lines
