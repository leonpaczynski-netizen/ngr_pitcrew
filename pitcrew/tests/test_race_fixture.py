"""One whole recorded race, as the fixture everything race-shaped is run against.

CLAUDE.md §7 asks for a recorded session checked in as *the* fixture, and there
was one lap. `watkins_glen_lap.bin` earned its place - it is what caught a
channel holding the roll rate under the name `yaw_rate`, and a slip ratio 2*pi
too large - but one lap cannot exercise anything that spans a race: a stint, a
pit stop, a tyre change, a wear rate, a lap that swallowed a crossing.

`watkins-glen-international-long-course-race.zip` is session 49 exactly as the
recorder wrote it - **the race he won from P3**, 20 laps of a Huracan GT3 on
Racing Softs round the Long Course, GT7 v1.70, 2x wear and 3x fuel. Rebuilt by
`tools/build_race_fixture.py`; the blobs are copied byte for byte and never
re-encoded, because a fixture that has been through this app's own encoder
tests the encoder against itself.

**The assertions are facts about the race, not golden values.** He started
third and finished first; a race has one green lap and one chequer; a closed
circuit's laps are all the same length once anchored; a 20-lap race at Watkins
runs about 35 minutes. Each survives a detector being retuned, and each is
something a synthetic lap could not have told anybody.
"""
from __future__ import annotations

import json
import pathlib
import zipfile

from dataclasses import dataclass

import pytest

from pitcrew.analysis.distance import anchor, integrated_length
from pitcrew.telemetry.recorder import decode_frames, repair_frames

FIXTURE = (pathlib.Path(__file__).parent / "fixtures"
           / "watkins-glen-international-long-course-race.zip")

# Watkins Glen Long Course, from GT7's own catalogue.
LENGTH_M = 5423.0


@pytest.fixture(scope="module")
def bundle():
    if not FIXTURE.exists():                                 # pragma: no cover
        pytest.skip(f"{FIXTURE.name} is not checked out")
    with zipfile.ZipFile(FIXTURE) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        frames = {}
        for lap in manifest["laps"]:
            if lap["blob"]:
                frames[lap["lapNum"]] = repair_frames(
                    decode_frames(archive.read(lap["blob"])))
        yield manifest, frames


# --- what the fixture is ----------------------------------------------------

def test_it_is_the_race_it_says_it_is(bundle):
    manifest, _ = bundle
    assert manifest["kind"] == "race"
    assert manifest["circuitKey"] == "watkins-glen-international-long-course"
    assert manifest["raceType"] == "laps"
    assert manifest["raceLaps"] == 20
    assert len(manifest["laps"]) == 20
    assert manifest["packetFormat"] == "C", \
        "the C packet is the only one carrying current lap time in ms"


def test_the_video_is_referenced_and_never_shipped(bundle):
    """Gigabytes, not the app's to redistribute, and runtime data files are
    never committed. The manifest records the path so the wear and traffic
    passes can be pointed at it; without it those skip rather than fail."""
    manifest, _ = bundle
    assert "videoPath" in manifest
    assert FIXTURE.stat().st_size < 16_000_000, \
        "the fixture is telemetry only - a video has got in"


# --- the race, which is what one lap could never show -----------------------

def test_he_started_third_and_finished_first(bundle):
    """**Independent proof that the position byte decodes correctly.**

    `packet.current_position` was decoded from the first version of the parser
    and read by nothing in `pitcrew/race/`, and `packet.py` carried two
    contradictory accounts of which byte it was. This is the archive settling
    it: he won this race from P3, and the channel says so.
    """
    manifest, _ = bundle
    positions = [lap["position"] for lap in manifest["laps"]
                 if lap["position"]]
    assert positions[0] == 3
    assert positions[-1] == 1
    assert min(positions) == 1


def test_the_race_carries_one_compound_and_a_full_stint(bundle):
    manifest, _ = bundle
    compounds = {lap["compound"] for lap in manifest["laps"] if lap["compound"]}
    assert compounds == {"RS"}


def test_the_lap_times_are_a_race_and_not_a_test_author_s_numbers(bundle):
    """A 20-lap race at Watkins in a GT3 car is around 35 minutes, the opening
    lap is the slowest of the clean ones because it starts from the grid, and
    nothing is under a minute and a half."""
    manifest, _ = bundle
    times = [lap["lapTimeMs"] for lap in manifest["laps"] if lap["lapTimeMs"]]
    assert len(times) >= 19
    assert sum(times) / 60_000 == pytest.approx(35, abs=6)
    assert min(times) > 90_000
    assert times[0] > min(times), "the opening lap starts from the grid"


# --- the distance anchor, on real laps --------------------------------------

def test_every_anchored_lap_measures_the_circuit(bundle):
    """`lap_distance_m` is integrated from speed and runs short. Anchored,
    every lap that survives measures exactly one lap of the circuit; the ones
    that cannot get there carry a null rather than a number nobody measured."""
    _, frames = bundle
    laps = [_FixtureLap(num, rows) for num, rows in sorted(frames.items())]

    result = anchor(laps, LENGTH_M)

    assert result.ran
    measured = [integrated_length(lap) for lap in result.laps]
    assert any(m is not None for m in measured)
    for got in measured:
        assert got is None or got == pytest.approx(LENGTH_M, abs=0.5)


def test_this_race_is_the_case_the_median_gate_cannot_catch(bundle):
    """**The reason the anchor exists on top of `length_gate`.**

    This race's raw distance channel is internally CONSISTENT - median 5,409 m,
    sd 42 m, every lap inside 4% of its neighbours - so `length_gate`, which
    compares each lap against the session's own median, finds nothing wrong
    with any of it. And every lap is still 0.25% short of the circuit, because
    the median moves with the bias.

    A session that is uniformly wrong is invisible to a test for disagreement.
    It is not invisible to the circuit's own length.
    """
    _, frames = bundle
    laps = [_FixtureLap(num, rows) for num, rows in sorted(frames.items())]

    before = [integrated_length(lap) for lap in laps]
    middle = sorted(before)[len(before) // 2]

    assert max(before) - min(before) < LENGTH_M * 0.05, \
        "this race is the consistent case - if that changes, so does the point"
    assert middle < LENGTH_M, "and consistently short of the circuit"

    result = anchor(laps, LENGTH_M)
    assert not result.refused, "nothing here is broken, only biased"
    assert all(integrated_length(lap) == pytest.approx(LENGTH_M, abs=0.5)
               for lap in result.laps)


# --- the frames themselves --------------------------------------------------

def test_the_frames_are_real_driving(bundle):
    """The same physics `test_real_capture_fixture` asserts on one lap, held
    across a whole race: a GT3 car pulls 2-3 g and a lap of a closed circuit
    turns through one revolution."""
    _, frames = bundle
    rows = frames[max(frames)]
    speeds = [row["speed_kph"] for row in rows if row.get("speed_kph")]

    assert max(speeds) > 200, "a Huracan at Watkins passes 200 km/h"
    assert min(speeds) < 120, "and it slows for the Inner Loop"


@dataclass
class _FixtureLap:
    """The minimum `analysis.distance` reads: a number and some frames.

    A dataclass because `distance.anchor` rebuilds a lap with
    `dataclasses.replace`, which is how it leaves the caller's laps untouched -
    the real `LapInput` is one too.
    """
    lap_num: int
    frames: list
