"""The qualifying coach, driven with synthetic frames - no sound card, no Qt
for the coach itself, and the controller wiring at the end through the same
real-widget fixtures the other wiring tests use.

Sign convention under test, from the module: "up" means faster than the
reference, "down" means slower. The delta is reference-elapsed-at-distance
minus live elapsed, so positive is up.
"""
from __future__ import annotations

import pytest

from pitcrew.race.qualifying import (
    QualifyingCoach,
    ReferenceLap,
    _Phase,
    reference_lap,
)
from pitcrew.race.temps import TempWindow
from pitcrew.store.db import Store
from pitcrew.telemetry.recorder import LapRecorder
from pitcrew.telemetry.session_state import EventKind, Lap, SessionEvent

from .conftest import make_packet

pytest.importorskip("PyQt6.QtWidgets")

from .test_controller import an_event, qt_app, raw  # noqa: F401,E402
from pitcrew.controller import PitCrewController      # noqa: E402
from pitcrew.engineer.voice import NullEngine, Voice  # noqa: E402
from pitcrew.ui.event_screen import EventScreen       # noqa: E402
from pitcrew.ui.practice_screen import PracticeScreen  # noqa: E402


# A window measured the way race/temps measures one: floors at 72 front,
# 78 rear.
WINDOW = TempWindow(front=(72.0, 77.0), rear=(78.0, 88.0),
                    laps_to_window=2, laps_sampled=8)


def ref_50ms() -> ReferenceLap:
    """A 5500 m lap driven at a constant 50 m/s: 110.000 s."""
    frames = [{"lap_distance_m": float(d), "t_ms": d / 50.0 * 1000.0}
              for d in range(0, 5501, 25)]
    reference = ReferenceLap.from_frames(frames, lap_id=7,
                                         lap_time_ms=110_000)
    assert reference is not None
    return reference


def pkt(pid: int, *, speed: float = 50.0, front: float = 55.0,
        rear: float = 58.0, on_track: bool = True):
    return make_packet(
        packet_id=pid, speed_ms=speed, on_track=on_track,
        tyre_temp_fl=front, tyre_temp_fr=front,
        tyre_temp_rl=rear, tyre_temp_rr=rear)


def a_lap(num: int, ms: int, *, pit: bool = False, out: bool = False) -> Lap:
    return Lap(lap_num=num, lap_time_ms=ms, best_lap_ms=ms, delta_ms=0,
               fuel_start=30.0, fuel_end=29.0, fuel_used=1.0, position=1,
               is_pit_lap=pit, is_out_lap=out)


def crossing(lap: Lap) -> list[SessionEvent]:
    return [SessionEvent(EventKind.LAP_COMPLETED,
                         {"lap": lap, "remaining_time_ms": -1})]


def pit_entry() -> list[SessionEvent]:
    return [SessionEvent(EventKind.PIT_ENTRY,
                         {"fuel": 30.0, "tyres_changed": False})]


class StubPacket:
    """Only what the coach touches. Exists because the fixture packets
    cannot set `current_lap_time_ms` (a C-tail property) or a paused flag
    without building raw bytes, and these two fields are exactly what the
    stale-clock and pause defects are about."""
    loading = False
    car_on_track = True

    def __init__(self, pid: int, *, speed: float = 50.0, front: float = 75.0,
                 rear: float = 80.0, paused: bool = False,
                 lap_ms: int | None = None) -> None:
        self.packet_id = pid
        self.speed_ms = speed
        self.tyre_temps = (front, front, rear, rear)
        self.paused = paused
        self.current_lap_time_ms = lap_ms

    @property
    def speed_kmh(self) -> float:
        return self.speed_ms * 3.6


def set_off(coach: QualifyingCoach, *, front: float = 55.0,
            rear: float = 58.0) -> tuple[int, float]:
    """Roll out of the box and set off. Returns (packet_id, now)."""
    coach.update(pkt(0, speed=1.0, front=front, rear=rear), [], 0.0)
    coach.update(pkt(60, speed=15.0, front=front, rear=rear), [], 1.0)
    return 60, 1.0


def start_flyer(coach: QualifyingCoach, pid: int, now: float, *,
                front: float = 75.0, rear: float = 80.0,
                out_time_ms: int = 130_000) -> tuple[int, float]:
    """Cross the line off the out lap. Returns (packet_id, now)."""
    pid, now = pid + 60, now + 1.0
    coach.update(pkt(pid, speed=50.0, front=front, rear=rear),
                 crossing(a_lap(1, out_time_ms, out=True)), now)
    return pid, now


def drive(coach: QualifyingCoach, pid: int, now: float, updates: int, *,
          speed: float, front: float = 75.0, rear: float = 80.0
          ) -> tuple[int, float]:
    """One-second steps: 60 packets each, exactly `speed` metres apiece."""
    for _ in range(updates):
        pid, now = pid + 60, now + 1.0
        coach.update(pkt(pid, speed=speed, front=front, rear=rear), [], now)
    return pid, now


# ---------------------------------------------------------------- reference

def test_the_reference_curve_is_strictly_monotonic():
    frames = [
        {"lap_distance_m": 0.0, "t_ms": 0.0},
        {"lap_distance_m": 10.0, "t_ms": 200.0},
        {"lap_distance_m": 10.0, "t_ms": 220.0},   # duplicate distance
        {"lap_distance_m": 8.0, "t_ms": 240.0},    # regression
        {"lap_distance_m": 20.0, "t_ms": 400.0},
        {"lap_distance_m": None, "t_ms": 500.0},   # missing channel
        {"lap_distance_m": 30.0, "t_ms": 600.0},
    ]
    reference = ReferenceLap.from_frames(frames, lap_id=1, lap_time_ms=1_000)
    assert reference is not None
    assert list(reference.distances) == [0.0, 10.0, 20.0, 30.0]
    assert all(b > a for a, b in zip(reference.distances,
                                     reference.distances[1:]))
    # Interpolation, clamped at both ends.
    assert reference.elapsed_at(15.0) == pytest.approx(300.0)
    assert reference.elapsed_at(-5.0) == 0.0
    assert reference.elapsed_at(99.0) == 600.0


def test_too_few_usable_frames_is_no_reference():
    assert ReferenceLap.from_frames([{"lap_distance_m": 1.0, "t_ms": 0.0}],
                                    lap_id=1, lap_time_ms=1_000) is None
    frames = [{"lap_distance_m": float(d), "t_ms": d * 20.0}
              for d in range(10)]
    assert ReferenceLap.from_frames(frames, lap_id=1, lap_time_ms=0) is None


def test_reference_lap_reads_the_best_counted_lap(store: Store, event_id):
    session = store.start_session(event_id, "practice",
                                  practice_intent="qualifying")
    recorder = LapRecorder()
    for i in range(600):
        recorder.record_frame(make_packet(packet_id=i, speed_ms=50.0))
    frames = recorder.take_lap()

    # Faster than the best counted lap, and structurally uncounted.
    store.add_lap(session, a_lap(1, 9_000, out=True))
    best_id = store.add_lap(session, a_lap(2, 10_000), frames=frames)
    store.add_lap(session, a_lap(3, 11_000))

    reference = reference_lap(store, event_id)
    assert reference is not None
    assert reference.lap_id == best_id
    assert reference.lap_time_ms == 10_000
    # 600 frames at 50 m/s and 60 Hz integrate to 500 m.
    assert reference.total_m == pytest.approx(500.0, rel=0.02)
    assert reference.elapsed_at(250.0) == pytest.approx(5_000.0, rel=0.05)


def test_a_best_lap_without_frames_falls_back_to_one_with(store: Store,
                                                          event_id):
    session = store.start_session(event_id, "practice")
    recorder = LapRecorder()
    for i in range(600):
        recorder.record_frame(make_packet(packet_id=i, speed_ms=50.0))
    frames = recorder.take_lap()

    store.add_lap(session, a_lap(1, 9_500))                    # no frames
    with_frames = store.add_lap(session, a_lap(2, 10_000), frames=frames)

    reference = reference_lap(store, event_id)
    assert reference is not None
    assert reference.lap_id == with_frames


def test_no_practice_laps_is_no_reference(store: Store, event_id):
    assert reference_lap(store, event_id) is None


def test_a_phantom_fastest_lap_is_rejected_for_the_reference(store: Store,
                                                             event_id):
    """The lobby-join phantom: fastest on paper, wearing a time its own
    frames contradict (real case: lap 155 claims 104.4 s over 123.3 s of
    frames). Chasing it put every delta call 8-15 s out on the replay."""
    session = store.start_session(event_id, "practice")

    def recorded_frames():
        recorder = LapRecorder()
        for i in range(600):
            recorder.record_frame(make_packet(packet_id=i, speed_ms=50.0))
        return recorder.take_lap()

    # Ten seconds of frames claiming a five-second lap: 100% mismatch.
    store.add_lap(session, a_lap(1, 5_000), frames=recorded_frames())
    honest_id = store.add_lap(session, a_lap(2, 10_000),
                              frames=recorded_frames())

    reference = reference_lap(store, event_id)
    assert reference is not None
    assert reference.lap_id == honest_id
    assert reference.lap_time_ms == 10_000


# ------------------------------------------------------------------ out lap

def test_the_out_lap_opens_with_measured_temps_and_measured_targets():
    coach = QualifyingCoach(window=WINDOW, reference=ref_50ms())
    set_off(coach, front=55.0, rear=58.0)
    assert coach.phase is _Phase.OUT_LAP
    assert coach.said == ["Out lap. Fronts 55, rears 58 - need 72 and 78."]


def test_warming_into_the_window_is_called_once():
    coach = QualifyingCoach(window=WINDOW, reference=ref_50ms())
    pid, now = set_off(coach, front=55.0, rear=58.0)
    # Warm through the lap; the floors are crossed on the way.
    for k in range(90):
        pid, now = pid + 60, now + 1.0
        coach.update(pkt(pid, speed=45.0,
                         front=55.0 + k * 0.3, rear=58.0 + k * 0.3), [], now)
    in_window = [s for s in coach.said
                 if s == "Tyres in window. Push when you cross the line."]
    assert len(in_window) == 1


def test_the_rate_limiter_holds_and_then_releases():
    coach = QualifyingCoach(window=WINDOW, reference=ref_50ms())
    pid, now = set_off(coach, front=55.0, rear=58.0)     # call at now=1.0
    # Straight to working temperature: the rolling mean crosses both floors
    # about seven seconds in, still inside the spacing - held.
    for k in range(2, 15):
        coach.update(pkt(pid + 60 * k, speed=45.0, front=78.0, rear=85.0),
                     [], float(k))
    assert not any("in window" in s for s in coach.said)
    # And released once the spacing has passed.
    coach.update(pkt(pid + 60 * 17, speed=45.0, front=78.0, rear=85.0),
                 [], 17.0)
    assert any("in window" in s for s in coach.said)


def test_progress_names_the_axle_further_from_its_floor():
    coach = QualifyingCoach(window=WINDOW, reference=ref_50ms())
    pid, now = set_off(coach, front=55.0, rear=77.0)
    # Fronts warming through the lap; rears already a degree off their
    # floor. The rolling mean rises past the progress threshold mid-lap.
    for k in range(1, 31):
        coach.update(pkt(pid + 60 * k, speed=45.0,
                         front=55.0 + 0.5 * k, rear=77.0),
                     [], now + float(k))
    assert any(s.startswith("Fronts coming - ") for s in coach.said)
    assert not any(s.startswith("Rears") for s in coach.said)


def test_cold_at_the_line_is_stated_and_left_with_him():
    coach = QualifyingCoach(window=WINDOW, reference=ref_50ms())
    pid, now = set_off(coach, front=55.0, rear=77.0)
    start_flyer(coach, pid, now, front=55.0, rear=77.0)
    assert "Fronts still 17 cold - your call." in coach.said
    assert coach.phase is _Phase.FLYING


def test_a_cool_line_reading_on_a_warm_set_is_not_called_cold():
    """The floors are percentiles of LAP MEANS and the start/finish straight
    reads coolest, so a set at working temperature judged frame-by-frame
    heard "still 7 cold" at the worst possible moment. The rolling mean is
    the like-for-like figure."""
    coach = QualifyingCoach(window=WINDOW, reference=ref_50ms())
    pid, now = set_off(coach, front=73.0, rear=79.0)
    # Half a minute at working temperature...
    for k in range(1, 31):
        coach.update(pkt(pid + 60 * k, speed=45.0, front=73.0, rear=79.0),
                     [], now + float(k))
    # ...then the crossing frame itself reads five degrees cooler.
    said_before = len(coach.said)
    coach.update(pkt(pid + 60 * 31, speed=50.0, front=68.0, rear=74.0),
                 crossing(a_lap(1, 120_000, out=True)), now + 31.0)
    assert not any("cold" in s for s in coach.said[said_before:])
    assert coach.phase is _Phase.FLYING


def test_no_window_means_no_target_numbers_ever():
    coach = QualifyingCoach(window=None, reference=ref_50ms())
    pid, now = set_off(coach, front=50.0, rear=55.0)
    assert coach.said[-1] == "Out lap. Fronts 50, rears 55."
    # Warming is reported as trend only, once the rolling mean has risen.
    for k in range(1, 36):
        coach.update(pkt(pid + 60 * k, speed=45.0,
                         front=50.0 + 0.5 * k, rear=55.0 + 0.5 * k),
                     [], now + float(k))
    assert "Tyres still coming up." in coach.said
    # Crossing cold: no window, so no claim about cold.
    said_before = list(coach.said)
    start_flyer(coach, pid + 60 * 36, now + 36.0, front=68.0, rear=73.0)
    assert coach.said == said_before
    assert not any("need" in s or "window" in s or "cold" in s
                   for s in coach.said)


# --------------------------------------------------------------- flying lap

def test_ahead_of_the_reference_reads_up():
    coach = QualifyingCoach(window=WINDOW, reference=ref_50ms())
    pid, now = set_off(coach)
    pid, now = start_flyer(coach, pid, now)
    # 55 m/s against a 50 m/s reference: a third of the lap in 34 s.
    pid, now = drive(coach, pid, now, 34, speed=55.0)
    # ref elapsed at 1870 m = 37.4 s, live 34.0 s: 3.4 s up, "about"
    # because no completed flyer has yet measured the integration drift.
    assert "On it. Up about 3.4 seconds." in coach.said


def test_behind_the_reference_reads_down():
    coach = QualifyingCoach(window=WINDOW, reference=ref_50ms())
    pid, now = set_off(coach)
    pid, now = start_flyer(coach, pid, now)
    pid, now = drive(coach, pid, now, 41, speed=45.0)
    # ref elapsed at 1845 m = 36.9 s, live 41.0 s: 4.1 s down.
    assert "Down about 4.1 seconds." in coach.said


def test_the_mid_lap_call_behind_asks_for_a_tidy_last_sector():
    coach = QualifyingCoach(window=WINDOW, reference=ref_50ms())
    pid, now = set_off(coach)
    pid, now = start_flyer(coach, pid, now)
    pid, now = drive(coach, pid, now, 82, speed=45.0)   # past two thirds
    assert any(s.startswith("Down about") and "tidy the last sector" in s
               for s in coach.said)


def test_a_purple_lap_is_called_purple_with_the_gap():
    coach = QualifyingCoach(window=WINDOW, reference=ref_50ms())
    pid, now = set_off(coach)
    pid, now = start_flyer(coach, pid, now)
    pid, now = drive(coach, pid, now, 100, speed=55.0)
    coach.update(pkt(pid + 60, speed=55.0, front=75.0, rear=80.0),
                 crossing(a_lap(2, 109_400)), now + 1.0)
    assert "Purple. one forty-nine point four - six tenths under your best." in coach.said


def test_a_slower_lap_on_ready_tyres_says_another_run_is_worth_taking():
    coach = QualifyingCoach(window=WINDOW, reference=ref_50ms())
    # Warm from the start, so the rolling mean is in window at the line.
    pid, now = set_off(coach, front=75.0, rear=80.0)
    pid, now = start_flyer(coach, pid, now, front=75.0, rear=80.0)
    pid, now = drive(coach, pid, now, 100, speed=55.0)
    coach.update(pkt(pid + 60, speed=55.0, front=75.0, rear=80.0),
                 crossing(a_lap(2, 110_400)), now + 1.0)
    assert ("one fifty point four - four tenths down. Tyres were ready - grip should hold "
            "for another run." in coach.said)


def test_a_slower_lap_on_cold_tyres_makes_no_grip_claim():
    coach = QualifyingCoach(window=WINDOW, reference=ref_50ms())
    pid, now = set_off(coach, front=55.0, rear=58.0)
    pid, now = start_flyer(coach, pid, now, front=60.0, rear=63.0)
    pid, now = drive(coach, pid, now, 100, speed=55.0,
                     front=60.0, rear=63.0)
    coach.update(pkt(pid + 60, speed=55.0, front=60.0, rear=63.0),
                 crossing(a_lap(2, 110_400)), now + 1.0)
    line = next(s for s in coach.said if s.startswith("one fifty point four"))
    assert "grip" not in line


def test_purple_is_judged_against_the_session_best_not_just_the_reference():
    coach = QualifyingCoach(window=WINDOW, reference=ref_50ms())
    pid, now = set_off(coach)
    pid, now = start_flyer(coach, pid, now)
    pid, now = drive(coach, pid, now, 100, speed=55.0)
    coach.update(pkt(pid + 60, speed=55.0, front=75.0, rear=80.0),
                 crossing(a_lap(2, 109_000)), now + 1.0)     # new best
    pid, now = pid + 60, now + 1.0
    pid, now = drive(coach, pid, now, 100, speed=55.0)
    coach.update(pkt(pid + 60, speed=55.0, front=75.0, rear=80.0),
                 crossing(a_lap(3, 109_500)), now + 1.0)
    # Faster than the practice reference, slower than tonight's best:
    # that is down, not purple.
    assert any(s.startswith("one forty-nine point five - five tenths down.")
               for s in coach.said)
    assert sum(s.startswith("Purple") for s in coach.said) == 1


def test_an_abandoned_flyer_resets_quietly():
    coach = QualifyingCoach(window=WINDOW, reference=ref_50ms())
    pid, now = set_off(coach)
    pid, now = start_flyer(coach, pid, now)
    pid, now = drive(coach, pid, now, 5, speed=50.0)     # 250 m, on it
    said_before = list(coach.said)
    # Into the barrier: distance stops, the clock does not, and 10 s behind
    # the run is dead.
    pid, now = drive(coach, pid, now, 25, speed=0.0)
    assert coach.phase is _Phase.OUT_LAP
    assert coach.said == said_before
    # The next crossing starts a fresh run - and the dead lap gets no line
    # call, because it was never a clean flyer.
    coach.update(pkt(pid + 60, speed=50.0, front=75.0, rear=80.0),
                 crossing(a_lap(2, 200_000)), now + 1.0)
    assert coach.said == said_before
    assert coach.phase is _Phase.FLYING


def test_pit_entry_stands_the_run_down_and_the_next_one_is_an_out_lap():
    coach = QualifyingCoach(window=WINDOW, reference=ref_50ms())
    pid, now = set_off(coach)
    pid, now = start_flyer(coach, pid, now)
    said_before = list(coach.said)
    coach.update(pkt(pid + 60, speed=5.0, front=75.0, rear=80.0),
                 pit_entry(), now + 1.0)
    assert coach.phase is _Phase.ARMED
    assert coach.said == said_before
    # Leaving the pits again is a new out lap, with its opening call.
    coach.update(pkt(pid + 120, speed=15.0, front=70.0, rear=76.0),
                 [], now + 30.0)
    assert coach.phase is _Phase.OUT_LAP
    assert coach.said[-1].startswith("Out lap.")


def test_no_reference_still_gives_temps_and_the_line_call():
    """The delta half stands down without a reference - but GT7's lap time
    is exact and it is the one number he wants at the line, so the line
    call stays, judged against tonight's own best as laps accrue."""
    coach = QualifyingCoach(window=WINDOW, reference=None)
    assert coach.said == ["No reference lap from practice - "
                          "temperatures and lap times only."]
    pid, now = set_off(coach, front=75.0, rear=80.0)
    pid, now = start_flyer(coach, pid, now)
    pid, now = drive(coach, pid, now, 120, speed=55.0)
    coach.update(pkt(pid + 60, speed=55.0, front=75.0, rear=80.0),
                 crossing(a_lap(2, 109_000)), now + 1.0)
    # First flyer: the exact time, no comparison claimed.
    assert "one forty-nine flat." in coach.said
    # And never a mid-lap delta: there is nothing measured to chase.
    assert not any(s.startswith(("On it.", "Up ", "Down ", "Level"))
                   for s in coach.said)
    # Second flyer beats it: purple against the session's own best.
    pid, now = pid + 60, now + 1.0
    pid, now = drive(coach, pid, now, 120, speed=55.0)
    coach.update(pkt(pid + 60, speed=55.0, front=75.0, rear=80.0),
                 crossing(a_lap(3, 108_500)), now + 1.0)
    assert "Purple. one forty-eight point five - five tenths under your best." in coach.said


def test_the_crossing_frame_cannot_abandon_the_new_flyer():
    """Whether GT7 has already reset the lap clock on the frame where
    `last_lap_ms` changes is unverified against a live stream. A clock
    still holding the outgoing lap's 116 s read as instantly-dead, and a
    naive abandon check silenced every flyer at birth."""
    coach = QualifyingCoach(window=None, reference=ref_50ms())
    coach.update(StubPacket(0, speed=15.0), [], 0.0)
    coach.update(StubPacket(60, speed=50.0, lap_ms=116_000),
                 crossing(a_lap(1, 116_000, out=True)), 1.0)
    pid, now = 60, 1.0
    # A few more frames of the stale clock after the crossing.
    for _ in range(5):
        pid, now = pid + 1, now + 1.0 / 60.0
        coach.update(StubPacket(pid, speed=50.0, lap_ms=116_000), [], now)
    assert coach.phase is _Phase.FLYING          # not silently abandoned
    # Once the clock has visibly reset, the lap proceeds to its calls.
    for k in range(2400):                        # 40 s at 50 m/s
        pid, now = pid + 1, now + 1.0 / 60.0
        coach.update(StubPacket(pid, speed=50.0,
                                lap_ms=int((5 + k) * 1000 / 60)), [], now)
    assert any(s.startswith(("On it.", "Up ", "Down ", "Level"))
               for s in coach.said)


def test_a_pause_mid_flyer_does_not_fabricate_distance():
    """GT7's packet counter keeps running while paused. An integrator that
    left its last id behind charged the resume frame with the whole gap:
    30 s paused at 500 m read as 2,000 m and a spurious "Up about 30"."""
    coach = QualifyingCoach(window=None, reference=ref_50ms())
    coach.update(StubPacket(0, speed=15.0), [], 0.0)
    coach.update(StubPacket(60, speed=50.0, lap_ms=0),
                 crossing(a_lap(1, 130_000, out=True)), 1.0)
    pid, now = 60, 1.0
    for k in range(600):                         # 10 s at 50 m/s -> 500 m
        pid, now = pid + 1, now + 1.0 / 60.0
        coach.update(StubPacket(pid, speed=50.0,
                                lap_ms=int(k * 1000 / 60)), [], now)
    assert coach._distance_m == pytest.approx(500.0, abs=2.0)
    said_before = list(coach.said)
    for _ in range(1800):                        # 30 s paused, ids counting
        pid, now = pid + 1, now + 1.0 / 60.0
        coach.update(StubPacket(pid, speed=50.0, paused=True,
                                lap_ms=10_000), [], now)
    pid, now = pid + 1, now + 1.0 / 60.0
    coach.update(StubPacket(pid, speed=50.0, lap_ms=10_016), [], now)
    # One frame's worth of distance, not thirty seconds' worth.
    assert coach._distance_m == pytest.approx(500.8, abs=2.0)
    assert coach.said == said_before


def test_arming_mid_lap_waits_for_the_next_crossing():
    """An intent flip to qualifying mid-flyer must not announce "Out lap"
    into the middle of a push lap. The coach joins in at the line."""
    coach = QualifyingCoach(window=None, reference=ref_50ms(), mid_lap=True)
    assert coach.phase is _Phase.WAITING
    pid, now = 0, 0.0
    pid, now = drive(coach, pid, now, 30, speed=55.0)
    assert coach.phase is _Phase.WAITING
    assert coach.said == []                       # not a word mid-lap
    coach.update(pkt(pid + 60, speed=55.0, front=75.0, rear=80.0),
                 crossing(a_lap(1, 112_000)), now + 1.0)
    # No window and no measured claim of cold: the next lap is the run.
    assert coach.phase is _Phase.FLYING


def test_arming_mid_lap_with_a_cold_set_joins_as_an_out_lap():
    coach = QualifyingCoach(window=WINDOW, reference=ref_50ms(),
                            mid_lap=True)
    pid, now = 0, 0.0
    pid, now = drive(coach, pid, now, 30, speed=55.0,
                     front=55.0, rear=58.0)
    assert coach.said == []
    coach.update(pkt(pid + 60, speed=55.0, front=55.0, rear=58.0),
                 crossing(a_lap(1, 120_000)), now + 1.0)
    assert coach.phase is _Phase.OUT_LAP
    assert coach.said[-1].startswith("Out lap.")


def test_a_full_out_lap_and_flyer_replay():
    """The whole session shape: warm up, in window, push, purple - and the
    second flyer drops the "about" once the first has measured the drift."""
    coach = QualifyingCoach(window=WINDOW, reference=ref_50ms())
    pid, now = set_off(coach, front=50.0, rear=55.0)
    assert coach.said[0] == "Out lap. Fronts 50, rears 55 - need 72 and 78."
    for k in range(90):
        pid, now = pid + 60, now + 1.0
        coach.update(pkt(pid, speed=45.0,
                         front=50.0 + k * 0.35, rear=55.0 + k * 0.35),
                     [], now)
    assert "Tyres in window. Push when you cross the line." in coach.said
    # At most the three out-lap calls before the line.
    assert len(coach.said) <= 3

    pid, now = start_flyer(coach, pid, now, front=82.0, rear=87.0)
    # 100 one-second steps at 55 m/s land on exactly 5500 m - the reference
    # total - so the completed flyer measures the drift at zero. GT7's time
    # agrees with the trace (100 s), so the lap becomes the reference.
    pid, now = drive(coach, pid, now, 100, speed=55.0, front=82.0, rear=87.0)
    coach.update(pkt(pid + 60, speed=55.0, front=82.0, rear=87.0),
                 crossing(a_lap(2, 100_000)), now + 1.0)
    assert ("Purple. one forty flat - 10.0 seconds under your best."
            in coach.said)

    # Second flyer: the drift is measured and small, so no more "about" -
    # and it chases the 55 m/s lap just set, not the 50 m/s practice lap.
    # 31 s at 60 m/s is 1860 m, which that lap reached in 33.8 s.
    pid, now = pid + 60, now + 1.0
    pid, now = drive(coach, pid, now, 31, speed=60.0, front=82.0, rear=87.0)
    assert "On it. Up 2.8 seconds." in coach.said


# ------------------------------------------------- one reference for the lot

def _flyer(coach, pid, now, *, steps, speed, lap_num, lap_ms):
    """A whole flyer: `steps` one-second steps at `speed`, then the line."""
    start = len(coach.said)
    pid, now = drive(coach, pid, now, steps, speed=speed)
    pid, now = pid + 60, now + 1.0
    coach.update(pkt(pid, speed=speed, front=75.0, rear=80.0),
                 crossing(a_lap(lap_num, lap_ms)), now)
    return pid, now, coach.said[start:]


def test_the_splits_chase_the_lap_the_line_call_compares_with():
    """Sardegna quali, 15 Sep 2026: "Up five tenths" at two thirds, then
    "four tenths down" at the line for a 1:40.088 - up on the practice lap
    the splits chased, down on the 1:39.640 he had set two laps before.

    Here: a 110 s practice reference, a 100 s flyer, then a 106 s flyer -
    four seconds up on practice, six down on tonight's best. Every call on
    that lap has to say down."""
    coach = QualifyingCoach(window=WINDOW, reference=ref_50ms())
    pid, now = set_off(coach, front=75.0, rear=80.0)
    pid, now = start_flyer(coach, pid, now)
    pid, now, said = _flyer(coach, pid, now, steps=100, speed=55.0,
                            lap_num=2, lap_ms=100_000)
    assert said[-1].startswith("Purple.")
    assert coach.reference.lap_time_ms == 100_000
    assert coach.reference.lap_id is None           # tonight's, not a row

    pid, now, said = _flyer(coach, pid, now, steps=106, speed=52.0,
                            lap_num=3, lap_ms=106_000)
    # 36 s at 52 m/s is 1872 m, which the 100 s lap reached in 34.0 s.
    assert said[0] == "Down 2.0 seconds."
    assert said[1].startswith("Down ")
    assert said[2].startswith("one forty-six flat - 6.0 seconds down.")
    assert not any(s.startswith(("On it.", "Up ")) for s in said)


def test_a_new_best_whose_trace_contradicts_its_time_stands_the_splits_down():
    """Rule 12's shape: the line call has moved to this lap, so the splits
    either chase it or stop - never carry on against the lap before."""
    coach = QualifyingCoach(window=WINDOW, reference=ref_50ms())
    pid, now = set_off(coach, front=75.0, rear=80.0)
    pid, now = start_flyer(coach, pid, now)
    # GT7 says 109 s; the trace the coach integrated lasted 100.
    pid, now, said = _flyer(coach, pid, now, steps=100, speed=55.0,
                            lap_num=2, lap_ms=109_000)
    assert said[-1] == ("Splits off until your next best - "
                        "that lap's trace had a gap.")
    assert coach.reference is None

    # No splits on the next run - and a sound new best brings them back.
    pid, now, said = _flyer(coach, pid, now, steps=100, speed=55.0,
                            lap_num=3, lap_ms=100_000)
    assert not any(s.startswith(("On it.", "Up ", "Down ", "Level"))
                   for s in said)
    assert said[-1].startswith("Purple.")
    assert coach.reference is not None and coach.reference.lap_time_ms == 100_000
    pid, now = drive(coach, pid, now, 31, speed=60.0)
    assert coach.said[-1] == "On it. Up 2.8 seconds."
    # Said once, not once per refusal.
    assert sum(s.startswith("Splits off") for s in coach.said) == 1


def test_a_short_trace_is_not_the_lap_to_chase():
    """An off or a cut: the distance falls 3.6% short of the lap. Faster on
    the clock, not a lap anyone should chase."""
    coach = QualifyingCoach(window=WINDOW, reference=ref_50ms())
    pid, now = set_off(coach, front=75.0, rear=80.0)
    pid, now = start_flyer(coach, pid, now)
    pid, now, said = _flyer(coach, pid, now, steps=106, speed=50.0,
                            lap_num=2, lap_ms=106_000)
    assert said[-1].startswith("Splits off")
    assert coach.reference is None


def test_a_stale_lap_clock_at_the_line_does_not_poison_the_adopted_curve():
    """The first frames of a lap may still carry the outgoing lap's time.
    Kept, they would be the whole curve after monotonic filtering."""
    coach = QualifyingCoach(window=None, reference=ref_50ms())
    coach.update(StubPacket(0, speed=15.0), [], 0.0)
    coach.update(StubPacket(60, speed=55.0, lap_ms=116_000),
                 crossing(a_lap(1, 116_000, out=True)), 1.0)
    pid, now = 60, 1.0
    for _ in range(5):
        pid, now = pid + 1, now + 1.0 / 60.0
        coach.update(StubPacket(pid, speed=55.0, lap_ms=116_000), [], now)
    for k in range(6000):                        # 100 s at 55 m/s
        pid, now = pid + 1, now + 1.0 / 60.0
        coach.update(StubPacket(pid, speed=55.0,
                                lap_ms=int((5 + k) * 1000 / 60)), [], now)
    pid, now = pid + 1, now + 1.0 / 60.0
    coach.update(StubPacket(pid, speed=55.0, lap_ms=116_000),
                 crossing(a_lap(2, 100_100)), now)
    reference = coach.reference
    assert reference is not None and reference.lap_time_ms == 100_100
    assert reference.elapsed_ms[0] < 1_000
    assert reference.total_m == pytest.approx(5500.0, rel=0.01)
    assert len(reference.distances) > 5_000


def test_without_a_practice_reference_no_flyer_becomes_one():
    """The coach announced "lap times only"; a split appearing later would
    contradict the one thing it said."""
    coach = QualifyingCoach(window=WINDOW, reference=None)
    pid, now = set_off(coach, front=75.0, rear=80.0)
    pid, now = start_flyer(coach, pid, now)
    pid, now, _ = _flyer(coach, pid, now, steps=100, speed=55.0,
                         lap_num=2, lap_ms=100_000)
    pid, now, _ = _flyer(coach, pid, now, steps=100, speed=56.0,
                         lap_num=3, lap_ms=98_300)
    assert coach.reference is None
    assert not any(s.startswith(("On it.", "Up ", "Down ", "Level", "Splits"))
                   for s in coach.said)


# ------------------------------------------------------------------- wiring

@pytest.fixture()
def quali_wired(qt_app, store: Store):  # noqa: F811
    practice = PracticeScreen()
    # A voice that records instead of speaking: `spoken` still fills, so
    # the speaks/silent assertions hold without a sound card in the loop.
    controller = PitCrewController(store, EventScreen(), practice,
                                   voice=Voice(NullEngine(), enabled=False))
    controller._on_event_saved(an_event())
    yield controller, practice, store
    controller.shutdown()


def test_qualifying_intent_arms_the_coach_at_session_start(quali_wired):
    controller, practice, _ = quali_wired
    practice.set_practice_intent("qualifying")
    controller.open_practice_session()

    coach = controller.bridge.quali
    assert coach is not None
    # An empty store measured nothing: no window, no reference - and the
    # coach said which half it is missing, through the real voice path.
    assert coach.window is None and coach.reference is None
    assert any("lap times only" in line for line in coach.said)
    assert any("lap times only" in line for line in controller.voice.spoken)
    controller.stop_practice()
    assert controller.bridge.quali is None


def test_race_intent_does_not_arm_the_coach(quali_wired):
    controller, practice, _ = quali_wired
    practice.set_practice_intent("race")
    controller.open_practice_session()
    assert controller.bridge.quali is None
    controller.stop_practice()


def test_the_coach_follows_the_intent_mid_session(quali_wired):
    controller, practice, _ = quali_wired
    practice.set_practice_intent("race")
    controller.open_practice_session()
    assert controller.bridge.quali is None

    controller._on_practice_intent("qualifying")
    assert controller.bridge.quali is not None
    controller._on_practice_intent("race")
    assert controller.bridge.quali is None
    controller.stop_practice()


def test_silent_coach_still_records_every_call(quali_wired):
    controller, practice, _ = quali_wired
    practice.set_practice_intent("qualifying")
    index = practice.coach_picker.findData(False)
    practice.coach_picker.setCurrentIndex(index)
    controller.open_practice_session()

    coach = controller.bridge.quali
    assert coach is not None
    assert any("lap times only" in line for line in coach.said)
    assert not any("lap times only" in line
                   for line in controller.voice.spoken)
    controller.stop_practice()


def test_the_speak_toggle_follows_the_coach_live(quali_wired):
    """Silencing a coach mid-out-lap must not wait for the next session."""
    controller, practice, _ = quali_wired
    practice.set_practice_intent("qualifying")
    controller.open_practice_session()

    coach = controller.bridge.quali
    assert coach._speak is not None
    practice.coach_picker.setCurrentIndex(
        practice.coach_picker.findData(False))
    assert coach._speak is None
    practice.coach_picker.setCurrentIndex(
        practice.coach_picker.findData(True))
    assert coach._speak is not None
    controller.stop_practice()


def test_the_coach_is_fed_from_the_packet_path(quali_wired):
    """The per-frame hook beside the shift beep, driven with real bytes."""
    controller, practice, _ = quali_wired
    practice.set_practice_intent("qualifying")
    controller.open_practice_session()

    coach = controller.bridge.quali
    controller.bridge.on_packet(raw(speed_ms=20.0))
    assert coach.phase is _Phase.OUT_LAP
    assert any(line.startswith("Out lap.") for line in coach.said)
    controller.stop_practice()


def test_a_raising_coach_is_dropped_not_fatal(quali_wired):
    """The adviser must never cost a recorded lap - same doctrine as the
    haptics and wind outputs on the same thread."""
    controller, practice, _ = quali_wired
    practice.set_practice_intent("qualifying")
    controller.open_practice_session()

    class Exploding:
        def update(self, packet, events, now):
            raise RuntimeError("boom")

    controller.bridge.quali = Exploding()
    assert controller.bridge.on_packet(raw(speed_ms=20.0)) is True
    assert controller.bridge.quali is None
    controller.stop_practice()
