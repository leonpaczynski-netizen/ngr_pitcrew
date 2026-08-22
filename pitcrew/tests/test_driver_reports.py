"""The REPORT family - the driver telling the engineer, rather than asking it.`CLAUDE.md` §4.1 is the standing rule the whole programme runs on: the driver's
report is primary evidence and telemetry is corroboration. Until these landed
the radio only went one way, and a handling complaint made at racing speed went
into the `radio` table as free text tagged `unknown`.

So the tests that matter are about what happens to the evidence: that his own
words survive verbatim, that the app never analyses a report out loud, and that
the two reports which throw a lap away throw away the right one.
"""
from __future__ import annotations

import json

import pytest

from pitcrew.engineer import intents as I
from pitcrew.race import driver_report


# --------------------------------------------------------------- the words

@pytest.mark.parametrize("heard,want", [
    ("no front end", I.REPORT_UNDERSTEER),
    ("the front is pushing", I.REPORT_UNDERSTEER),
    ("it won't rotate", I.REPORT_UNDERSTEER),
    ("the rear is loose", I.REPORT_OVERSTEER),
    ("i have no grip at the rear", I.REPORT_OVERSTEER),
    ("the back end is coming round", I.REPORT_OVERSTEER),
    ("i went off", I.REPORT_INCIDENT),
    ("i spun", I.REPORT_INCIDENT),
    ("two wheels on the grass", I.REPORT_INCIDENT),
    ("i'm in traffic", I.REPORT_TRAFFIC),
    ("stuck behind him", I.REPORT_TRAFFIC),
    ("i got held up", I.REPORT_TRAFFIC),
])
def test_the_reports_route_to_their_own_intent(heard, want):
    assert I.match_intent(heard) == want


def test_a_wear_question_is_not_a_handling_report():
    """**The collision the vocabulary had to be tuned to fix.** "How shot are
    the fronts" is a question about wear; "the front won't bite" is a statement
    about balance. Recording the first as the second loses a question the app
    already answered and files a complaint he never made."""
    assert I.match_intent("how shot are the fronts") == I.TYRES
    assert I.match_intent("how are the fronts") == I.TYRES
    assert I.match_intent("the front won't bite") == I.REPORT_UNDERSTEER


def test_a_report_is_still_distinct_from_saying_nothing():
    assert I.match_intent("blah blah nonsense") == I.UNKNOWN


# ------------------------------------------------------------ the responses

def test_a_handling_report_is_acknowledged_and_never_analysed():
    """One observation is one observation. Telling him what it means would be
    inventing the meaning the record exists to collect evidence for."""
    for intent in (I.REPORT_UNDERSTEER, I.REPORT_OVERSTEER):
        said = I.answer(intent, {"lapInProgress": 13}).text
        assert said.startswith("Copy")
        assert "noted" in said.lower()
        # No diagnosis, no instruction, no number.
        assert not any(ch.isdigit() for ch in said)


def test_the_lap_named_is_the_one_being_driven():
    """`lap` counts crossings, so during the thirteenth it reads 12. Told
    "lap 12 is out" while driving 13, he would correct a mistake the app had
    not made and the right lap would stay in."""
    said = I.answer(I.REPORT_INCIDENT, {"lap": 12, "lapInProgress": 13}).text
    assert "lap 13" in said
    assert "12" not in said


def test_with_no_lap_number_it_claims_none():
    """A confident wrong lap number is worse than no number - it is the one he
    would correct against."""
    said = I.answer(I.REPORT_TRAFFIC, {}).text
    assert "this lap is out" in said
    assert not any(ch.isdigit() for ch in said)


def test_traffic_says_which_of_the_two_it_heard():
    assert "Traffic" in I.answer(I.REPORT_TRAFFIC, {"lapInProgress": 4}).text


def test_every_report_is_answered():
    """`answered=False` is the shape of a refusal, and a report is never
    refused - the app always has somewhere to put it."""
    for intent in I.REPORTS:
        assert I.answer(intent, {"lapInProgress": 2}).answered


# ----------------------------------------------------------- the record

class FakePacket:
    speed_kmh = 214.6
    pos_x, pos_y, pos_z = 101.25, 3.5, -488.75
    throttle = 0.5          # 0-1 off the packet...
    brake = 0.25
    steering = 0.5          # ...and radians
    current_gear = 4
    engine_rpm = 7250.0
    tyre_temps = (81.0, 83.5, 90.25, 88.0)
    car_id = 3391


def test_his_own_words_survive_verbatim(tmp_path):
    """The classified kind is ours and is a lossy reading of what he said. The
    sentence is his, and §4.1 calls it primary."""
    path = tmp_path / "reports.jsonl"
    row = driver_report.note_report(
        driver_report.UNDERSTEER, "the front just will not bite in six",
        packet=FakePacket(), lap=11, path=path)
    assert row["heard"] == "the front just will not bite in six"
    assert row["kind"] == driver_report.UNDERSTEER
    assert row["lap"] == 11


def test_the_units_are_converted_where_they_are_written(tmp_path):
    """CLAUDE.md §3.4: convert once, at the boundary. The packet holds 0-1
    pedals and radians; nothing reading this file should have to know that."""
    row = driver_report.note_report(
        driver_report.OVERSTEER, "rear stepped out", packet=FakePacket(),
        path=tmp_path / "r.jsonl")
    assert row["telemetry"]["throttlePct"] == pytest.approx(50.0)
    assert row["telemetry"]["brakePct"] == pytest.approx(25.0)
    assert row["telemetry"]["steeringDeg"] == pytest.approx(28.6, abs=0.1)


def test_no_steering_channel_is_null_and_never_zero(tmp_path):
    """The 'A' packet format carries no steering. Zero would read as a straight
    wheel, which is exactly the wrong thing to record beside "it would not turn
    in"."""
    class NoSteering(FakePacket):
        steering = None

    row = driver_report.note_report(driver_report.UNDERSTEER, "no front",
                                    packet=NoSteering(),
                                    path=tmp_path / "r.jsonl")
    assert row["telemetry"]["steeringDeg"] is None


def test_a_report_with_no_telemetry_is_still_recorded(tmp_path):
    """**Unlike a HUD calibration row**, where the pairing IS the observation.
    Here his words are the observation and the telemetry corroborates, so
    losing the report because the stream had a gap would be discarding the
    primary evidence to keep the secondary."""
    row = driver_report.note_report(
        driver_report.INCIDENT, "i went off at the exit", packet=None,
        lap=7, path=tmp_path / "r.jsonl")
    assert row is not None
    assert row["heard"] == "i went off at the exit"
    assert row["telemetry"] is None


def test_a_kind_nobody_defined_is_refused(tmp_path):
    assert driver_report.note_report("vibes", "hmm",
                                     path=tmp_path / "r.jsonl") is None


def test_rows_round_trip_through_the_file(tmp_path):
    path = tmp_path / "r.jsonl"
    driver_report.note_report(driver_report.TRAFFIC, "stuck behind",
                              lap=3, path=path)
    driver_report.note_report(driver_report.INCIDENT, "went off", lap=4,
                              path=path)
    got = driver_report.read_reports(path)
    assert [row["lap"] for row in got] == [3, 4]


def test_a_half_written_row_does_not_cost_the_rest(tmp_path):
    """The rows before the damage are evidence, and refusing all of them to
    protest one is the wrong trade."""
    path = tmp_path / "r.jsonl"
    driver_report.note_report(driver_report.TRAFFIC, "held up", lap=2,
                              path=path)
    with path.open("a", encoding="utf-8") as handle:
        handle.write('{"kind": "incident", "heard": "went o\n')
    driver_report.note_report(driver_report.OVERSTEER, "loose", lap=5,
                              path=path)
    got = driver_report.read_reports(path)
    assert [row["lap"] for row in got] == [2, 5]


def test_a_file_that_cannot_be_written_does_not_reach_the_driver(tmp_path):
    """Note-taking must never raise into a race. The exchange is already in
    the `radio` table, which is where it can be recovered from."""
    blocked = tmp_path / "nope"
    blocked.write_text("not a directory", encoding="utf-8")
    row = driver_report.note_report(driver_report.INCIDENT, "spun",
                                    path=blocked / "deeper" / "r.jsonl")
    assert row is not None      # returned, so the caller still has it


def test_the_written_line_is_one_json_object(tmp_path):
    path = tmp_path / "r.jsonl"
    driver_report.note_report(driver_report.UNDERSTEER, "pushing", lap=1,
                              packet=FakePacket(), path=path)
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["kind"] == "understeer"

# ------------------------------------------------- what it does to the lap
#
# Two of the four reports throw a lap away. These are about throwing away the
# right one - the lap he is describing is the one he is DRIVING, which has not
# been stored yet, so the exclusion has to wait for it to land.

from pitcrew.engineer.gate import confirmation_question       # noqa: E402


def test_a_handling_report_never_touches_a_lap(monkeypatch, tmp_path):
    """Understeer is a fact about the car, not about whether the lap counts."""
    from pitcrew.controller import PitCrewController

    controller = PitCrewController.__new__(PitCrewController)
    controller._exclude_next_lap = None
    _run_report(controller, monkeypatch, tmp_path, "the front is pushing")
    assert controller._exclude_next_lap is None


def test_an_off_marks_the_next_lap_to_land(monkeypatch, tmp_path):
    from pitcrew.controller import PitCrewController

    controller = PitCrewController.__new__(PitCrewController)
    controller._exclude_next_lap = None
    _run_report(controller, monkeypatch, tmp_path, "i went off")
    assert controller._exclude_next_lap == "incident"


def test_traffic_marks_it_as_traffic(monkeypatch, tmp_path):
    """The export contract's own example names traffic as an exclusion
    reason, so the reason has to survive as that word."""
    from pitcrew.controller import PitCrewController

    controller = PitCrewController.__new__(PitCrewController)
    controller._exclude_next_lap = None
    _run_report(controller, monkeypatch, tmp_path, "stuck behind him")
    assert controller._exclude_next_lap == "traffic"


def _run_report(controller, monkeypatch, tmp_path, heard):
    """Drive `_note_driver_report` with everything around it stubbed out."""
    from pitcrew.race import driver_report as dr

    monkeypatch.setattr(dr, "REPORT_FILE", tmp_path / "r.jsonl")
    controller.bridge = type("B", (), {"last_packet": FakePacket()})()
    controller.race = None
    controller.session_id = None
    controller.active_event = lambda: None
    controller._current_lap = lambda: 9
    controller._note_driver_report(I.match_intent(heard), heard)
    written = dr.read_reports(tmp_path / "r.jsonl")
    assert written and written[-1]["heard"] == heard
    assert written[-1]["lap"] == 9


def test_the_confirmation_reads_as_a_sentence():
    """The generic form turns an id into words, which is serviceable for
    `box-when` and unusable here - "Did you mean report understeer?" is not a
    question anybody answers at racing speed."""
    assert confirmation_question(I.REPORT_UNDERSTEER) == "Did you mean understeer?"
    assert "throw the lap out" in confirmation_question(I.REPORT_INCIDENT)


def test_the_new_phrases_reach_the_recogniser():
    """`known_phrases` primes the closed grammar. A phrase the vocabulary has
    and the recogniser does not is a phrase he can never be heard saying."""
    known = set(I.known_phrases())
    for phrase in I.PHRASES[I.REPORT_INCIDENT]:
        assert phrase in known
