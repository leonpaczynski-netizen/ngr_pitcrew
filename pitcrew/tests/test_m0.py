"""M0: the measurement run, and the refusals that keep it honest.

The tests that matter most here are the ones asserting the analysis says *no*.
A run that quietly returns a number it could not have measured is worse than
one that returns nothing, because the number goes into a constants file, and
the whole point of the constants file is that it holds measured things.
"""
from __future__ import annotations

import json

import pytest

from pitcrew.analysis.m0 import (
    INCONCLUSIVE,
    PARALLEL,
    SERIAL,
    analyse,
    write_constants,
)
from pitcrew.telemetry.capture import (
    CaptureError,
    CaptureWriter,
    read_datagrams,
    read_metadata,
)
from pitcrew.telemetry.pit_detect import Sample, find_stops, refuel_span
from pitcrew.tests.conftest import raw_packet
from pitcrew.tests.test_controller import qt_app  # noqa: F401

HZ = 60.0
STEP = 1.0 / HZ
GREEN_LAP_S = 100.0
HOT = (90.0, 90.0, 90.0, 90.0)
COLD = (40.0, 40.0, 40.0, 40.0)


def _run(stops, *, laps=26, capacity=100.0, lap_s=GREEN_LAP_S,
         start_fuel=90.0, burn_per_lap=3.0, gap_at=None, position=None,
         transit_s=0.0):
    """A synthetic race at 60 Hz, with the given stops.

    `stops` maps lap number to a dict describing what happened:
    `dead` seconds before anything, `tyres` seconds of tyre change, `fuel`
    litres added, `rate` L/s, and `serial` for whether the two overlap.
    """
    samples: list[Sample] = []
    t = 0.0
    fuel = start_fuel
    temps = HOT

    def emit(count, *, speed, lap, fuel_delta=0.0, temp=None):
        nonlocal t, fuel, temps
        for _ in range(count):
            if temp is not None:
                temps = temp
            fuel += fuel_delta
            samples.append(Sample(
                t_s=t, speed_kph=speed, fuel_l=fuel, on_track=True, lap=lap,
                temps=temps, road_distance_m=0.0,
                position=position if position is not None else 5))
            t += STEP

    for lap in range(1, laps + 1):
        stop = stops.get(lap)
        # A lap with a stop in it runs its full green length and then stands
        # still, plus whatever the pit transit costs on top.
        green_s = lap_s + (transit_s if stop else 0.0)

        # green running for this lap, minus the burn
        n = max(1, int(green_s / STEP))
        emit(n, speed=180.0, lap=lap, fuel_delta=-burn_per_lap / n,
             temp=HOT)

        if not stop:
            continue

        dead = stop.get("dead", 5.0)
        tyres = stop.get("tyres", 0.0)
        litres = stop.get("fuel", 0.0)
        rate = stop.get("rate", 2.5)
        serial = stop.get("serial", True)
        fuelling = litres / rate if litres else 0.0

        emit(int(dead / STEP), speed=0.0, lap=lap)
        if serial:
            if tyres:
                emit(int(tyres / STEP), speed=0.0, lap=lap, temp=COLD)
            if fuelling:
                n = int(fuelling / STEP)
                emit(n, speed=0.0, lap=lap, fuel_delta=litres / n)
        else:
            # Overlapped: fuel flows while the tyres are being changed.
            n = max(int(max(tyres, fuelling) / STEP), 1)
            fuel_n = int(fuelling / STEP)
            for i in range(n):
                if tyres and i == 0:
                    emit(1, speed=0.0, lap=lap, temp=COLD,
                         fuel_delta=litres / fuel_n if i < fuel_n else 0.0)
                else:
                    emit(1, speed=0.0, lap=lap,
                         fuel_delta=litres / fuel_n if i < fuel_n else 0.0)

        if gap_at == lap:
            t += 1.5                      # a hole in the stream, mid-stop
            emit(30, speed=0.0, lap=lap)

    return samples


def _protocol(over=None):
    """The run card's protocol: A tyres, B fuel, C both."""
    base = {
        5: {"dead": 5.0, "tyres": 9.0, "fuel": 0.0},
        12: {"dead": 5.0, "tyres": 0.0, "fuel": 45.0, "rate": 2.5},
        20: {"dead": 5.0, "tyres": 9.0, "fuel": 45.0, "rate": 2.5},
    }
    for lap, changes in (over or {}).items():
        base[lap] = {**base[lap], **changes}
    return base


# ------------------------------------------------------------ the capture file

def test_a_capture_round_trips(tmp_path):
    path = tmp_path / "run.pcap"
    with CaptureWriter(path, note="M0", track="Test") as writer:
        for i in range(5):
            writer.write(raw_packet(), 1000.0 + i * STEP)

    assert read_metadata(path) == {"note": "M0", "track": "Test"}
    read = list(read_datagrams(path))
    assert len(read) == 5
    assert read[0].data == raw_packet()
    # Timestamps are relative to the first datagram, so no wall clock is stored.
    assert read[0].t_s == 0.0
    assert read[-1].t_s == pytest.approx(4 * STEP)


def test_a_truncated_tail_is_dropped_not_raised(tmp_path):
    """A capture is often closed by the process dying, not by a clean stop."""
    path = tmp_path / "run.pcap"
    with CaptureWriter(path) as writer:
        for i in range(4):
            writer.write(raw_packet(), i * STEP)
    whole = path.read_bytes()
    path.write_bytes(whole[:-40])
    assert len(list(read_datagrams(path))) == 3


def test_a_file_that_is_not_a_capture_is_refused(tmp_path):
    path = tmp_path / "nope.pcap"
    path.write_bytes(b"this is not a capture\n")
    with pytest.raises(CaptureError, match="not a pitcrew capture"):
        list(read_datagrams(path))


# ------------------------------------------------------------ stop detection

def test_the_three_stops_are_found_and_told_apart():
    stops = find_stops(_run(_protocol()))
    assert [s.lap for s in stops] == [5, 12, 20]
    tyres, fuel, both = stops
    assert (tyres.changed_tyres, tyres.took_fuel) == (True, False)
    assert (fuel.changed_tyres, fuel.took_fuel) == (False, True)
    assert (both.changed_tyres, both.took_fuel) == (True, True)


def test_a_stop_seen_by_fuel_and_temperature_is_high_confidence():
    stops = find_stops(_run(_protocol()))
    assert stops[2].confidence == "high"
    assert stops[0].confidence == "medium"      # temps only
    assert stops[1].confidence == "medium"      # fuel only


def test_a_car_stopped_off_track_is_not_a_pit_stop():
    """A gravel trap is not a pit box, and must not become a constant."""
    samples = [Sample(t_s=i * STEP, speed_kph=0.0, fuel_l=50.0,
                      on_track=False, lap=3, temps=HOT)
               for i in range(600)]
    assert find_stops(samples) == []


def test_refuel_span_excludes_the_dead_time():
    """The rate is the slope of the flow, not litres over the whole stop."""
    samples = _run(_protocol())
    fuel_stop = find_stops(samples)[1]
    span = refuel_span(samples, fuel_stop)
    assert span[-1].t_s - span[0].t_s == pytest.approx(45.0 / 2.5, abs=0.1)
    assert fuel_stop.duration_s == pytest.approx(5.0 + 18.0, abs=0.1)


# ------------------------------------------------------ recovering the constants

@pytest.mark.parametrize("rate", [1.0, 2.5, 5.0, 7.0])
def test_the_refuel_rate_is_recovered(rate):
    """1 vs 7 L/s is the number the whole fuel-saving doctrine turns on."""
    result = analyse(_run(_protocol({12: {"rate": rate},
                                       20: {"rate": rate}})), capacity_l=100.0)
    measured = result.measurements["refuelRateLps"]
    assert measured.value == pytest.approx(rate, rel=0.02)
    assert measured.low <= rate <= measured.high
    assert measured.conclusive


def test_the_tyre_change_time_is_recovered():
    result = analyse(_run(_protocol()), capacity_l=100.0)
    # Stop A is dead + tyres; the tyre change alone is A minus the dead time
    # recovered from stop B.
    assert result.measurements["tyresOnlyStopS"].value == pytest.approx(
        14.0, abs=0.1)
    assert result.measurements["pitDeadTimeS"].value == pytest.approx(
        5.0, abs=0.2)
    assert result.measurements["tyreChangeS"].value == pytest.approx(
        9.0, abs=0.3)


def test_the_pit_lane_delta_is_recovered():
    """A known transit loss injected into the pit lap comes back out."""
    result = analyse(_run(_protocol(), transit_s=21.0), capacity_l=100.0)
    delta = result.measurements["pitLaneDeltaS"]
    assert delta.value == pytest.approx(21.0, abs=0.5)
    assert "NOT entry-line to exit-line" in delta.note


def test_a_stop_with_no_transit_loss_measures_none():
    result = analyse(_run(_protocol()), capacity_l=100.0)
    assert result.measurements["pitLaneDeltaS"].value == pytest.approx(
        0.0, abs=0.5)


PHYSICAL = ("refuelRateLps", "tyresOnlyStopS", "fuelOnlyStopS", "bothStopS",
            "pitLaneDeltaS", "pitDeadTimeS", "tyreChangeS")


def test_every_constant_carries_an_interval_and_a_source():
    result = analyse(_run(_protocol()), capacity_l=100.0)
    for name in PHYSICAL:
        m = result.measurements[name]
        if m.value is None:
            assert m.note, f"{name} is absent with no reason"
            continue
        assert m.low is not None and m.high is not None, name
        assert m.high > m.low, f"{name} claims an interval of zero width"
        assert m.low <= m.value <= m.high, name
        assert m.source, name


def test_a_constant_with_no_supporting_stop_is_absent_never_defaulted():
    result = analyse(_run({5: {"dead": 5.0, "tyres": 9.0}}), capacity_l=100.0)
    rate = result.measurements["refuelRateLps"]
    assert rate.value is None
    assert rate.as_dict()["value"] is None
    assert "no fuel-only stop" in rate.note


# ------------------------------------------------------------- the verdict

def test_a_serial_run_reads_as_serial():
    result = analyse(_run(_protocol({20: {"serial": True}})),
                     capacity_l=100.0)
    assert result.verdict == SERIAL
    assert "Serial predicts" in result.verdict_note


def test_a_parallel_run_reads_as_parallel():
    result = analyse(_run(_protocol({20: {"serial": False}})),
                     capacity_l=100.0)
    assert result.verdict == PARALLEL


def test_a_fill_too_small_to_separate_the_models_is_inconclusive():
    """The most important test here.

    The two models differ by exactly min(tyre change, fuelling time). Fill only
    a few litres at stop C and they predict almost the same duration, so
    whichever "wins" won on noise. That is precisely how a guess gets laundered
    into a measured constant, and the run must say so instead.
    """
    result = analyse(_run(_protocol({20: {"fuel": 2.0, "serial": True}})),
                     capacity_l=100.0)
    assert result.verdict == INCONCLUSIVE
    assert "larger fill" in result.verdict_note
    assert "arrive emptier" in result.verdict_note


def test_an_inconclusive_verdict_still_reports_what_it_did_measure():
    """Refusing the verdict must not throw away the rate that was measured."""
    result = analyse(_run(_protocol({20: {"fuel": 2.0}})), capacity_l=100.0)
    assert result.verdict == INCONCLUSIVE
    assert result.measurements["refuelRateLps"].value == pytest.approx(
        2.5, rel=0.02)


def test_a_run_missing_a_stop_cannot_reach_a_verdict():
    result = analyse(_run({5: {"dead": 5.0, "tyres": 9.0},
                           12: {"dead": 5.0, "fuel": 45.0}}),
                     capacity_l=100.0)
    assert result.verdict == INCONCLUSIVE
    assert "tyres-and-fuel" in result.verdict_note
    assert result.void


# --------------------------------------------------------- refusing bad data

def test_a_dropped_packet_gap_gives_insufficient_data_not_a_number():
    """Arithmetic across a hole produces a confident wrong answer."""
    result = analyse(_run(_protocol(), gap_at=12), capacity_l=100.0)
    rate = result.measurements["refuelRateLps"]
    assert rate.value is None
    assert "insufficient data" in rate.note
    assert result.void
    assert any("lower bound" in r for r in result.void_reasons)


def test_a_capacity_that_is_not_100_is_flagged_not_absorbed():
    """5 L is a kart, 0 L an EV, anything else a bad parse. All worth hearing."""
    result = analyse(_run(_protocol()), capacity_l=64.0)
    assert any("64.0 L" in w and "bad parse" in w for w in result.warnings)


def test_the_expected_capacity_is_not_hardcoded_into_the_measurement():
    """100 is what we expect to read, never what we assume."""
    quiet = analyse(_run(_protocol()), capacity_l=100.0)
    assert not any("capacity" in w for w in quiet.warnings)
    missing = analyse(_run(_protocol()), capacity_l=None)
    assert any("no fuel capacity" in w for w in missing.warnings)


# ------------------------------------------------------------------- G17

def test_a_constant_position_field_reads_as_no_live_classification():
    result = analyse(_run(_protocol(), position=0), capacity_l=100.0)
    field = result.measurements["positionFieldLive"]
    assert field.value == 1.0
    assert "no live classification" in field.note


def test_a_changing_position_field_is_reported_rather_than_assumed_away():
    """If GT7 turns out to update it, that is a finding, not an inconvenience."""
    samples = _run(_protocol())
    moved = [Sample(**{**s.__dict__, "position": 3 if s.lap > 10 else 5})
             for s in samples]
    field = analyse(moved, capacity_l=100.0).measurements["positionFieldLive"]
    assert field.value == 2.0
    assert "may be a live classification" in field.note


# ---------------------------------------------------------------- the artefact

def test_the_constants_file_is_json_with_provenance(tmp_path):
    result = analyse(_run(_protocol()), capacity_l=100.0)
    path = write_constants(result, tmp_path / "m0.json")
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert payload["schema"] == "pitcrew.m0/1"
    assert payload["serialOrParallel"]["verdict"] == SERIAL
    rate = payload["constants"]["refuelRateLps"]
    assert rate["unit"] == "L/s"
    assert rate["interval"][0] <= rate["value"] <= rate["interval"][1]
    assert "lap 12" in rate["source"]
    assert rate["conclusive"] is True


def test_the_analysis_is_deterministic():
    """Same capture in, same bytes out - no clock, no RNG on this path."""
    first = analyse(_run(_protocol()), capacity_l=100.0).as_dict()
    second = analyse(_run(_protocol()), capacity_l=100.0).as_dict()
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)


def test_a_void_run_says_so_at_the_top_of_the_summary():
    result = analyse(_run(_protocol(), gap_at=12), capacity_l=100.0)
    assert result.summary().splitlines()[2].startswith("RUN VOID")


# ------------------------------------------------- end to end, through the CLI
#
# Everything above drives `Sample` objects. This drives real GT7 bytes through
# `parse_packet` and the capture file, so the format, the parser and the
# analysis are proved to agree rather than assumed to.

def _bytes_with(**values) -> bytes:
    """A structurally valid GT7 packet with named fields set.

    Built by unpacking the zero-filled packet, editing the tuple and repacking,
    so the field offsets come from `packet.py` itself and cannot drift out of
    step with it.
    """
    from pitcrew.telemetry import packet as pk

    raw = raw_packet(extended=True)
    fields = list(pk._FMT.unpack_from(raw, 0))
    index = {"fuel_level": 16, "fuel_capacity": 17, "speed_ms": 18,
             "laps_completed": 28, "flags_raw": 37, "road_distance": 44}
    for name, value in values.items():
        fields[index[name]] = value
    head = pk._FMT.pack(*fields)
    return head + raw[len(head):]


def test_a_real_capture_parses_into_samples(tmp_path):
    """Bytes on disk -> parse_packet -> Sample, with the fields intact."""
    from tools.analyse_m0 import samples_from_capture

    path = tmp_path / "run.pcap"
    with CaptureWriter(path, note="smoke") as writer:
        for i in range(10):
            writer.write(_bytes_with(fuel_level=50.0 + i, fuel_capacity=100.0,
                                     speed_ms=0.0, laps_completed=4,
                                     flags_raw=0x0001), i * STEP)

    samples, capacity, formats, failed = samples_from_capture(path)
    assert failed == 0
    assert formats == {"C"}
    assert capacity == pytest.approx(100.0)
    assert len(samples) == 10
    assert samples[0].fuel_l == pytest.approx(50.0)
    assert samples[-1].fuel_l == pytest.approx(59.0)
    assert samples[0].on_track is True
    assert samples[0].lap == 4


def test_the_cli_refuses_a_capture_it_cannot_measure(tmp_path, capsys):
    """A capture with no stops must not quietly emit an empty constants file."""
    from tools.analyse_m0 import main

    path = tmp_path / "run.pcap"
    with CaptureWriter(path) as writer:
        for i in range(120):
            writer.write(_bytes_with(fuel_level=50.0, fuel_capacity=100.0,
                                     speed_ms=50.0, laps_completed=1 + i // 60,
                                     flags_raw=0x0001), i * STEP)

    out = tmp_path / "m0.json"
    assert main([str(path), "--out", str(out)]) == 1        # non-zero = void
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["void"] is True
    assert "three stops" in payload["voidReasons"][0]
    assert payload["constants"]["refuelRateLps"]["value"] is None
    assert "NOT wired into the strategy model" in capsys.readouterr().out


# --------------------------------------------------------- the capture harness
#
# These construct a real Controller, which was impossible until the recogniser
# deadline landed (register E6/E7). The harness is a tee on the callback the
# app already receives: no second socket, no heartbeat, nothing that changes
# who talks to the console.

@pytest.fixture
def rig(qt_app, store, tmp_path):                                  # noqa: F811
    from pitcrew.controller import PitCrewController
    from pitcrew.ui.event_screen import EventScreen
    from pitcrew.ui.practice_screen import PracticeScreen
    from pitcrew.ui.settings_screen import SettingsScreen

    screen = SettingsScreen()
    controller = PitCrewController(store, EventScreen(), PracticeScreen(),
                                   settings_screen=screen)
    yield controller, screen, tmp_path
    controller.stop_capture()
    controller.shutdown()


def _feed(controller, count, **fields):
    for i in range(count):
        controller.bridge.on_packet(_bytes_with(fuel_capacity=100.0, **fields))


def test_the_harness_opens_no_socket_of_its_own(rig):
    """The whole point: it observes the stream, it does not go and get one."""
    controller, _, tmp_path = rig
    before = controller.listener
    controller.start_capture(tmp_path / "run.pcap")
    assert controller.listener is before
    assert controller.capturing


def test_capture_records_the_datagrams_the_app_receives(rig):
    controller, _, tmp_path = rig
    path = controller.start_capture(tmp_path / "run.pcap")
    _feed(controller, 20, fuel_level=50.0, speed_ms=40.0, flags_raw=0x0001)
    summary = controller.stop_capture()

    assert summary["packets"] == 20
    assert summary["problem"] is None
    assert len(list(read_datagrams(path))) == 20
    assert read_metadata(path)["expected_format"] == "C"


def test_capture_is_off_unless_it_is_turned_on(rig):
    controller, _, _ = rig
    assert controller.capturing is False
    _feed(controller, 5, fuel_level=50.0, speed_ms=40.0, flags_raw=0x0001)
    assert controller.stop_capture() is None


def test_an_empty_capture_says_the_run_needs_repeating(rig):
    """Silence is the failure that looks most like success."""
    controller, _, tmp_path = rig
    controller.start_capture(tmp_path / "run.pcap")
    summary = controller.stop_capture()
    assert summary["packets"] == 0
    assert "Nothing was captured" in summary["problem"]
    assert "repeating" in summary["problem"]


def test_the_wrong_packet_format_fails_loudly(rig):
    """A 296-byte 'A' capture cannot answer M0 and must not be discovered late."""
    from pitcrew.tests.conftest import raw_packet as short_packet

    controller, _, tmp_path = rig
    controller.start_capture(tmp_path / "run.pcap")
    for _ in range(5):
        controller.bridge.on_packet(short_packet(extended=False))
    summary = controller.stop_capture()

    assert summary["formats"] == ["A"]
    assert "expected C" in summary["problem"]
    assert "run it again" in summary["problem"]


def test_a_datagram_that_is_not_gt7_at_all_is_reported(rig):
    controller, _, tmp_path = rig
    controller.start_capture(tmp_path / "run.pcap")
    controller.bridge.on_packet(b"\x00" * 40)
    summary = controller.stop_capture()
    assert summary["unparsed"] == 1
    assert "not a GT7 packet size" in summary["problem"]


def test_an_undecodable_datagram_is_still_written_to_disk(rig):
    """The capture keeps what this build cannot read, for a build that can."""
    controller, _, tmp_path = rig
    path = controller.start_capture(tmp_path / "run.pcap")
    controller.bridge.on_packet(b"\x00" * 40)
    controller.stop_capture()
    assert [d.data for d in read_datagrams(path)] == [b"\x00" * 40]


def test_the_button_reports_what_happened(rig):
    controller, screen, tmp_path = rig
    controller.toggle_capture(True)
    assert controller.capturing
    assert screen.capture_button.isChecked()
    assert "Recording to" in screen.capture_note.text()

    _feed(controller, 10, fuel_level=50.0, speed_ms=40.0, flags_raw=0x0001)
    controller.toggle_capture(False)
    assert controller.capturing is False
    assert screen.capture_button.isChecked() is False
    assert "10 packets" in screen.capture_note.text()


def test_a_captured_run_analyses_end_to_end(rig):
    """Harness to file to analysis, with no synthetic Sample in the middle."""
    from tools.analyse_m0 import samples_from_capture

    controller, _, tmp_path = rig
    path = controller.start_capture(tmp_path / "run.pcap")
    # 3 laps of green running, then stationary with fuel going in.
    for lap in (1, 2, 3):
        _feed(controller, 5, fuel_level=60.0 - lap, speed_ms=50.0,
              laps_completed=lap, flags_raw=0x0001)
    for i in range(200):
        controller.bridge.on_packet(_bytes_with(
            fuel_capacity=100.0, fuel_level=57.0 + i * 0.1, speed_ms=0.0,
            laps_completed=4, flags_raw=0x0001))
    controller.stop_capture()

    samples, capacity, formats, failed = samples_from_capture(path)
    assert failed == 0 and formats == {"C"}
    assert capacity == pytest.approx(100.0)
    # Field values survived the whole chain: bytes -> file -> parse -> Sample.
    assert samples[0].lap == 1
    assert samples[-1].fuel_l == pytest.approx(57.0 + 199 * 0.1)

    # Timestamps come from the arrival clock, and feeding 215 packets in a
    # Python loop stamps them microseconds apart - so the "stop" lasts no time
    # and the detector rightly ignores it. Re-space them onto the 60 Hz grid
    # they would really arrive on; that is the loop being unrealistic, not the
    # capture.
    spaced = [Sample(**{**s.__dict__, "t_s": i * STEP})
              for i, s in enumerate(samples)]
    result = analyse(spaced, capacity_l=capacity)
    assert len(result.stops) == 1
    assert result.stops[0].took_fuel


def test_the_file_records_what_each_stop_arrived_on():
    """The run card's precondition is an arrival level, so expose it.

    The tank is 100 L, so this number is litres and percent at once - which is
    the whole reason the card can state a threshold the driver reads off the
    MFD.
    """
    payload = analyse(_run(_protocol()), capacity_l=100.0).as_dict()
    arrivals = {s["lap"]: s["arrivedOnL"] for s in payload["stops"]}
    assert arrivals[12] < arrivals[5], "the car should arrive at B emptier"
    assert all(v >= 0 for v in arrivals.values())
