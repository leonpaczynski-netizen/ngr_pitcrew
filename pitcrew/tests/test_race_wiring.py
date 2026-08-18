"""The race, driven through the controller with a fake voice."""
from __future__ import annotations

import dataclasses

import pytest

from pitcrew.controller import PitCrewController
from pitcrew.engineer.voice import NullEngine, Voice
from pitcrew.race.calls import BOX_NOW, BOX_SOON, GREEN
from pitcrew.store.db import Store
from pitcrew.telemetry.session_state import Lap
from pitcrew.ui.event_screen import EventScreen
from pitcrew.ui.practice_screen import PracticeScreen
from pitcrew.ui.race_screen import RaceScreen
from pitcrew.ui.strategy_screen import StrategyScreen

from .test_controller import an_event, qt_app, raw  # noqa: F401


@pytest.fixture()
def voice():
    """A voice that records instead of speaking, run on this thread."""
    return Voice(NullEngine(), enabled=False)


@pytest.fixture()
def raced(qt_app, store: Store, voice):  # noqa: F811
    race_screen = RaceScreen()
    strategy = StrategyScreen()
    controller = PitCrewController(
        store, EventScreen(), PracticeScreen(), strategy, race_screen,
        voice=voice)
    controller._on_event_saved(an_event(race_laps=20))
    event_id = store.active_event_id()

    # Practice, so there is a fuel rate and a plan to race to.
    session_id = controller.open_practice_session()
    store.note_stream_facts(session_id, packet_format="C",
                            fuel_capacity_l=100.0)
    for lap_num in range(1, 7):
        lap = Lap(lap_num=lap_num, lap_time_ms=94_000, best_lap_ms=94_000,
                  delta_ms=0, fuel_start=92.0 - (lap_num - 1) * 3.4,
                  fuel_end=92.0 - lap_num * 3.4, fuel_used=3.4, position=1,
                  is_pit_lap=False, is_out_lap=lap_num == 1)
        lap_id = store.add_lap(session_id, lap)
        store.set_lap_compound(lap_id, "RM")
    # A gauge reading, so the tyre limit forces a stop into the plan -
    # without it the fastest plan is no-stop and there is no box call.
    store.set_lap_wear(lap_id, 0.42, 0.42, 0.35, 0.35)
    controller.build_strategy()
    controller.approve_strategy(0)
    yield controller, race_screen, store, event_id
    controller.shutdown()


def green(controller) -> None:
    """Grid, then lights out."""
    controller.bridge.on_packet(raw(speed_ms=0.0, laps_in_race=20))
    controller.bridge.on_packet(raw(speed_ms=40.0, laps_in_race=20))


def a_lap(controller, lap_num: int, fuel: float) -> None:
    controller.bridge.on_packet(
        raw(speed_ms=50.0, fuel_level=fuel + 3.4, laps_in_race=20))
    controller.bridge.on_packet(
        raw(speed_ms=50.0, fuel_level=fuel, last_lap_ms=93_000 + lap_num,
            laps_in_race=20))


# ------------------------------------------------------------------ arming

def test_starting_arms_but_does_not_race(raced):
    """Nothing fires until the car actually crosses the line."""
    controller, screen, _, _ = raced
    assert controller.start_race() is True
    assert controller.race.armed is True
    assert controller.race.running is False
    assert "Waiting for you" in screen.subtitle.text()


def test_racing_needs_an_event(qt_app, store: Store, voice):  # noqa: F811
    screen = RaceScreen()
    controller = PitCrewController(store, EventScreen(), PracticeScreen(),
                                   StrategyScreen(), screen, voice=voice)
    assert controller.start_race() is False
    assert "Create an event" in screen.subtitle.text()
    controller.shutdown()


def test_a_plan_built_for_another_race_is_refused(raced):
    controller, screen, store, event_id = raced
    store.update_event(event_id, race_laps=32)   # the plan was for 20
    assert controller.start_race() is False
    assert "refused" in screen.subtitle.text().lower()
    assert controller.race is None


def test_a_race_without_a_plan_still_arms(raced):
    """No plan is a reason to say less, not to refuse to race."""
    controller, screen, store, event_id = raced
    for strategy in store.list_strategies(event_id):
        store._write().__enter__().execute(
            "UPDATE strategies SET status='candidate' WHERE id=?",
            (strategy["id"],))
    assert controller.start_race() is True
    assert "fuel calls only" in screen.subtitle.text()


# ------------------------------------------------------------------- calls

def test_green_is_called_when_the_race_starts(raced, voice):
    controller, screen, _, _ = raced
    controller.start_race()
    green(controller)

    assert controller.race.running is True
    assert any("Green" in line for line in voice.spoken)
    assert "Green" in screen.last_call.text()


def test_the_box_call_arrives_and_is_spoken(raced, voice):
    controller, _, _, _ = raced
    controller.start_race()
    green(controller)
    for lap_num in range(1, 12):
        a_lap(controller, lap_num, 92.0 - lap_num * 3.4)

    said = " ".join(voice.spoken)
    assert "Box" in said


def test_every_call_is_recorded_with_its_reason(raced):
    controller, _, store, event_id = raced
    controller.start_race()
    green(controller)
    for lap_num in range(1, 12):
        a_lap(controller, lap_num, 92.0 - lap_num * 3.4)

    runs = store.list_race_runs(event_id)
    assert len(runs) == 1
    revisions = store.list_revisions(runs[0]["id"])
    assert revisions
    for revision in revisions:
        plan = revision["plan"]
        # Two shapes reach the chain: an engineer call, which carries its own
        # exported form, and a spoken recomputation, which carries the verdict
        # and why the register decided it was worth opening his mouth.
        assert plan.get("call", {}).get("call") or plan.get("reason")
        assert plan["confidence"] in ("high", "medium", "low")


def test_declined_calls_are_kept(raced):
    """A call offered and ignored is evidence about the model."""
    controller, _, store, event_id = raced
    controller.start_race()
    green(controller)
    a_lap(controller, 1, 88.0)

    runs = store.list_race_runs(event_id)
    revisions = store.list_revisions(runs[0]["id"])
    assert all(r["accepted"] is False for r in revisions)


def _always(controller, monkeypatch, verdict):
    """Force one verdict, and tell the register the race has evidence.

    The evidence gate is what stops the engineer re-arguing the approved plan
    on lap one, and these tests are about what happens AFTER something has
    changed - so they hand it the burn it is waiting for.
    """
    monkeypatch.setattr("pitcrew.controller.assess", lambda **kwargs: verdict)
    monkeypatch.setattr(
        type(controller.race), "observed_fuel_per_lap", lambda self: 3.4)


def test_a_recomputation_is_recorded_on_the_lap_it_is_spoken(raced, monkeypatch):
    """**Offers are no longer recorded only when they resolve.** They used to
    be, and one unanswered offer therefore gagged the loop for 29 minutes and
    never reached `race_revisions` at all. There is nothing to resolve now:
    the register speaks, and what it says is filed there and then."""
    from pitcrew.race.replan import RECOMMENDED, Replan

    controller, _, store, event_id = raced
    controller.start_race()
    green(controller)
    offer = Replan(RECOMMENDED, "burning 20% more fuel than planned",
                   stops=2, stint_laps=(7, 6), gain_s=12.0, next_stop_lap=7)
    _always(controller, monkeypatch, offer)
    for lap_num in range(1, 5):
        a_lap(controller, lap_num, 92.0 - lap_num * 3.4)

    revisions = store.list_revisions(store.list_race_runs(event_id)[0]["id"])
    spoken = [r for r in revisions if r["plan"].get("why_spoken")]
    assert len(spoken) == 1
    assert spoken[0]["plan"]["why_spoken"] == "first assessment of the race"
    assert spoken[0]["accepted"] is False


def test_the_same_verdict_four_laps_running_is_recorded_once(raced, monkeypatch):
    """A recomputation that changes nothing is not a revision. A row a lap
    would bury the ones that matter under a race's worth of "no change"."""
    from pitcrew.race.replan import RECOMMENDED, Replan

    controller, _, store, event_id = raced
    controller.start_race()
    green(controller)
    _always(controller, monkeypatch,
            Replan(RECOMMENDED, "burning 20% more", stops=2,
                   stint_laps=(7, 6), gain_s=12.0, next_stop_lap=7))
    for lap_num in range(1, 6):
        a_lap(controller, lap_num, 92.0 - lap_num * 3.4)

    revisions = store.list_revisions(store.list_race_runs(event_id)[0]["id"])
    assert len([r for r in revisions if r["plan"].get("why_spoken")]) == 1


def test_a_materially_different_verdict_is_spoken_and_filed(
        raced, monkeypatch, voice):
    from pitcrew.race.replan import NONE, RECOMMENDED, URGENT, Replan

    controller, _, store, event_id = raced
    controller.start_race()
    green(controller)
    verdicts = iter([
        Replan(RECOMMENDED, "burning more fuel than planned",
               stops=2, stint_laps=(7, 6), gain_s=12.0, next_stop_lap=7),
        Replan(URGENT, "1.4 laps short of the flag on current burn",
               stops=1, stint_laps=(9,), confidence="high", next_stop_lap=9),
    ])
    fallback = Replan(NONE, "on the plan")
    monkeypatch.setattr("pitcrew.controller.assess",
                        lambda **kwargs: next(verdicts, fallback))
    monkeypatch.setattr(
        type(controller.race), "observed_fuel_per_lap", lambda self: 3.4)
    a_lap(controller, 1, 88.6)
    a_lap(controller, 2, 85.2)

    revisions = store.list_revisions(store.list_race_runs(event_id)[0]["id"])
    spoken = [r for r in revisions if r["plan"].get("why_spoken")]
    assert len(spoken) == 2
    # Two stops to one is a different race, and that is what the record
    # says. The escalation to urgent would have carried it on its own.
    assert spoken[1]["plan"]["why_spoken"] == "the stop count has changed"
    assert controller._replans.told.verdict == URGENT
    assert any("1 stop" in line for line in voice.spoken)


def test_nothing_is_left_open_at_teardown_to_be_lost(raced, monkeypatch):
    """An offer voiced in the final laps used to vanish from the record when
    the race closed on it, because it was only filed on resolution. **There is
    no pending state left to drain**: it was filed when it was spoken."""
    from pitcrew.race.replan import RECOMMENDED, Replan

    controller, _, store, event_id = raced
    controller.start_race()
    green(controller)
    _always(controller, monkeypatch,
            Replan(RECOMMENDED, "burning 20% more fuel than planned",
                   stops=2, stint_laps=(7, 6), gain_s=12.0, next_stop_lap=7))
    a_lap(controller, 1, 88.6)
    before = store.list_revisions(store.list_race_runs(event_id)[0]["id"])
    controller.stop_race()
    after = store.list_revisions(store.list_race_runs(event_id)[0]["id"])

    assert len(before) == len(after)
    assert any(r["plan"].get("why_spoken") for r in after)
    assert controller._replans.told is None


def test_an_ignored_box_call_folds_and_is_recorded_as_the_drivers_call(raced):
    """Nine verbatim "Box this lap" calls were once voiced to a driver
    running a feasible zero-stop - the ninth on his chequered-flag crossing.
    Two laps past an ignored stop the engineer now folds to the stay-out,
    and the revision chain records the fold as accepted with its reason:
    the driver voted by staying out, and the audit must read it that way
    round rather than as one more call he ignored."""
    controller, _, store, event_id = raced
    controller.start_race()
    green(controller)
    for lap_num in range(1, 20):
        a_lap(controller, lap_num, 92.0 - lap_num * 3.4)

    runs = store.list_race_runs(event_id)
    revisions = store.list_revisions(runs[0]["id"])
    folds = [r for r in revisions if r["plan"].get("kind") == "stay-out"]
    assert len(folds) == 1
    assert folds[0]["accepted"] is True
    assert folds[0]["plan"]["resolution"] == "driver stayed out"
    assert "Staying out" in folds[0]["reason"]
    # And the fold is the only revision that claims the driver's assent.
    assert all(r["accepted"] is False for r in revisions
               if r["plan"].get("kind") != "stay-out")


def test_the_calls_reach_the_export(raced):
    from pitcrew.export.build import build_event_export

    controller, _, store, event_id = raced
    controller.start_race()
    green(controller)
    for lap_num in range(1, 12):
        a_lap(controller, lap_num, 92.0 - lap_num * 3.4)
    controller.stop_race()

    payload = build_event_export(store, event_id)
    calls = payload["strategy"]["callsMade"]
    assert calls
    assert all("call" in call and "confidence" in call for call in calls)


def test_the_plan_stores_the_two_numbers_it_expects_to_execute(raced):
    """The lap-to-lap reference the driver asked for, written down with the
    plan at approval so the race has something to compare itself against -
    and so the post-race audit can see what the plan was built on."""
    controller, _, store, event_id = raced
    approved = store.get_approved_strategy(event_id)
    expects = approved["plan"]["expects"]
    assert expects["expected_fuel_per_lap_l"] == pytest.approx(3.4)
    assert expects["expected_lap_time_ms"] == 94_000
    # Every aggregate carries its sample count, and its source.
    assert expects["expected_fuel_samples"] > 0
    assert expects["expected_fuel_source"] == "practice"
    assert "assumption" in expects["expected_wear_source"]


def test_the_export_carries_the_expectation_and_the_outcome_against_it(raced):
    """**Both halves, because that is the whole audit value.** The contract's
    `outcome` is prose and this is where a comparison with its own sample
    counts and noise floor belongs - no key the consuming tool would have to
    read conservatively."""
    from pitcrew.export.build import build_event_export

    controller, _, store, event_id = raced
    controller.start_race()
    green(controller)
    for lap_num in range(1, 12):
        a_lap(controller, lap_num, 92.0 - lap_num * 3.4)
    controller.stop_race()

    outcome = build_event_export(store, event_id)["strategy"]["outcome"]
    assert "Planned on 3.40 L/lap" in outcome
    assert "green laps" in outcome
    assert "Planned on a 94.0 s lap" in outcome
    assert "ran 93.0 s" in outcome
    # Wear never stops being the plan's assumption, and the contradiction
    # between the gauge readings and the temperature gap travels with it.
    assert "no gauge reading was entered during the race" in outcome
    assert "unreconciled, not averaged" in outcome


# ---------------------------------------------------------------- lifecycle

def test_ending_the_race_closes_the_run(raced):
    controller, screen, store, event_id = raced
    controller.start_race()
    green(controller)
    controller.stop_race()

    assert controller.race is None
    assert screen.start_button.text().lower().startswith("start")
    run = store.list_race_runs(event_id)[0]
    assert run["finished_at"] is not None


def test_the_pit_wall_tracks_the_race(raced):
    controller, screen, _, _ = raced
    controller.start_race()
    green(controller)
    a_lap(controller, 1, 88.6)

    snapshot = controller.race.snapshot()
    assert snapshot["lap"] == 1
    assert snapshot["lapsRemaining"] == 19
    assert snapshot["lapsToStop"] is not None


# -------------------------------------------------------------------- voice

def test_the_voice_never_takes_the_app_down(qt_app):  # noqa: F811
    class Exploding:
        name = "exploding"

        def speak(self, text):
            raise RuntimeError("no audio device")

    speaker = Voice(Exploding(), enabled=True)
    speaker.say("Box this lap.")
    speaker.stop()
    assert "Box this lap." in speaker.spoken


def test_a_machine_with_no_speech_still_records_what_was_said():
    speaker = Voice(None, enabled=True)
    speaker.say("Green, green, green.")
    assert speaker.spoken == ["Green, green, green."]
    assert speaker.engine_name == "none"


def test_a_backlog_is_dropped_rather_than_read_out_late():
    """Three corners later, the call is worse than silence."""
    from pitcrew.engineer.voice import MAX_QUEUED

    speaker = Voice(NullEngine(), enabled=True)
    speaker._stop.set()                      # hold the worker
    for index in range(MAX_QUEUED + 5):
        speaker.say(f"call {index}")
    assert speaker._queue.qsize() <= MAX_QUEUED + 1
    speaker.stop()


# ------------------------------------------------------------------- piper

@pytest.mark.engine_resolution
def test_piper_is_preferred_over_sapi():
    """Piper sounds like a race engineer; SAPI sounds like a screen reader."""
    import inspect

    from pitcrew.engineer import voice as voice_module

    source = inspect.getsource(voice_module._best_engine)
    assert source.index("PiperEngine") < source.index("Sapi5Engine")


def test_a_voice_model_is_shipped():
    from pitcrew.engineer.voice import _default_model
    assert _default_model().endswith(".onnx")


def test_the_engine_warms_up_off_the_callers_thread():
    """Cold-loading Piper takes ~1.7s; arriving mid-call it would be useless."""
    warmed = []

    class Slow:
        name = "slow"

        def warm(self):
            warmed.append(True)

        def speak(self, text):
            pass

    speaker = Voice(Slow(), enabled=True)
    assert warmed == []          # not on construction
    speaker.warm()
    for _ in range(50):
        if warmed:
            break
        import time
        time.sleep(0.02)
    speaker.stop()
    assert warmed == [True]


def test_an_engine_without_warmup_is_fine():
    speaker = Voice(NullEngine(), enabled=True)
    speaker.warm()
    speaker.say("Green, green, green.")
    speaker.stop()
    assert speaker.spoken == ["Green, green, green."]


# ------------------------------------------------- the re-plan's time budget

def test_the_replan_narrows_and_then_stands_down_rather_than_blocking(raced):
    """Measured, a per-lap re-plan costs 1.4 ms at this event's shape - and
    the cost is superlinear in profiled compounds, so a fifty-lap timed race
    with three of them is 6.35 seconds on the Qt thread. Today only one
    compound has a profile, which is the only reason it is cheap. When it
    stops being cheap the engineer keeps the plan he has and says nothing,
    which is the correct failure for an adviser."""
    from pitcrew.race.replan import (
        REPLAN_MAX_STOPS,
        REPLAN_NARROWED_MAX_STOPS,
    )

    controller, _, _, _ = raced
    controller.start_race()
    assert controller._replan_max_stops == REPLAN_MAX_STOPS
    controller._note_replan_cost(0.001)
    assert controller._replan_max_stops == REPLAN_MAX_STOPS
    controller._note_replan_cost(0.4)
    assert controller._replan_max_stops == REPLAN_NARROWED_MAX_STOPS
    controller._note_replan_cost(0.4)
    assert controller._replan_max_stops == 0


def test_an_oversized_search_narrows_before_it_stands_down(raced):
    """**The pre-solve guard used to skip the narrowing rung entirely.**

    It cost the Monza race of 18 Aug 2026 its whole adaptation. A third
    compound had acquired a profile since the cap was calibrated, so `calls`
    went from 2**s to 3**s: 3000 units against the 1200 cap on lap 1, refused,
    re-planning off for the rest of the race, and the last stop still being
    fuelled by the plan approved before the green. The narrowed search that
    was never tried was 975 units and cost 19 ms against a 50 ms budget - the
    full one cost 161.
    """
    from pitcrew.race.replan import (
        REPLAN_MAX_STOPS,
        REPLAN_MAX_WORK,
        REPLAN_NARROWED_MAX_STOPS,
        replan_work,
    )

    controller, _, _, _ = raced
    controller.start_race()
    green(controller)
    inputs = controller._race_inputs
    assert inputs is not None

    # The shape that refused: three profiled compounds and a race long enough
    # that the full search is over the cap while the narrowed one is not.
    laps_left = 25
    profiles = dict(inputs.compound_profiles)
    reference = next(iter(profiles.values()))
    for code in ("RH", "RM", "RS"):
        profiles.setdefault(code, dataclasses.replace(reference, code=code))
    controller._race_inputs = dataclasses.replace(
        inputs, compound_profiles=profiles)
    inputs = controller._race_inputs
    assert len(inputs.planning_compounds()) == 3
    assert replan_work(inputs, laps_left, REPLAN_MAX_STOPS) > REPLAN_MAX_WORK
    assert (replan_work(inputs, laps_left, REPLAN_NARROWED_MAX_STOPS)
            <= REPLAN_MAX_WORK)

    controller.race.state.laps_total = controller.race.state.lap + laps_left
    a_lap(controller, controller.race.state.lap + 1, 88.6)

    # Narrowed, not stood down: the engineer is still re-planning.
    assert controller._replan_max_stops == REPLAN_NARROWED_MAX_STOPS


def test_a_stood_down_replan_leaves_the_plan_alone(raced, monkeypatch):
    controller, _, store, event_id = raced
    controller.start_race()
    green(controller)
    controller._replan_max_stops = 0
    monkeypatch.setattr("pitcrew.controller.assess",
                        lambda **kwargs: pytest.fail("must not be called"))
    a_lap(controller, 1, 88.6)
    assert controller._replans.told is None


# ------------------------------------------------ the in-box refuel readout

def test_the_engineer_calls_the_target_and_the_release_in_the_box(raced, voice):
    """The driver asked for this: *"pick up when fuel is going up and read out
    again what fuel volume (calculated from current race) what litres I need
    to leave the pits with."*

    The box call is made a lap and a half before the fuel moves and is sized
    by the plan's picture of the race. This one is said with the hose in, off
    the burn the race has actually shown.
    """
    controller, _, _, _ = raced
    controller.start_race()
    green(controller)
    for lap_num in range(1, 6):
        a_lap(controller, lap_num, 92.0 - lap_num * 3.4)
    voice.spoken.clear()

    # Down to the fumes he would actually arrive on, then into the box.
    for fuel in (30.0, 20.0, 12.0, 8.0):
        controller.bridge.on_packet(
            raw(speed_ms=50.0, fuel_level=fuel, laps_in_race=20))
    fuel = 8.0
    # Stopped, hose not in: the measured dead time is 5.3 s and nothing is
    # said across it.
    for _ in range(int(5.3 * 60)):
        controller.bridge.on_packet(
            raw(speed_ms=0.0, fuel_level=fuel, laps_in_race=20))
    assert controller.bridge.refuel.filling is False, "not filling yet"
    assert voice.spoken == []

    while fuel < 99.0:
        fuel += 1.0
        controller.bridge.on_packet(
            raw(speed_ms=0.0, fuel_level=fuel, laps_in_race=20))

    said = " ".join(voice.spoken)
    assert "Fuel to" in said, said
    assert "Go." in said, said
    assert said.index("Fuel to") < said.index("Go."), said
    assert controller.bridge.refuel.filling is True


def test_the_watch_says_nothing_while_the_car_is_driving(raced, voice):
    """Fuel only ever falls under green. A rise while moving is not a fill,
    and the engineer must not talk about the tank on a flying lap."""
    controller, _, _, _ = raced
    controller.start_race()
    green(controller)
    voice.spoken.clear()
    fuel = 40.0
    for _ in range(200):
        fuel += 0.5
        controller.bridge.on_packet(
            raw(speed_ms=50.0, fuel_level=fuel, laps_in_race=20))
    assert controller.bridge.refuel.filling is False
    assert not any("Fuel to" in line or line == "Go." for line in voice.spoken)


# ----------------------------------------- the HUD colour calibration bridge

def test_a_red_tyre_frame_is_paired_with_the_apps_own_degrees(
        raced, tmp_path, monkeypatch):
    """**The only bridge that exists between what he can see in VR and what
    this app measures.** PD documents the frame reddening with heat and
    publishes no scale; nobody has ever paired the colour with a number. His
    report is the event; the temperature beside it is ours."""
    import json

    from pitcrew.race import hud_calibration

    written = tmp_path / "tyre_hud_calibration.jsonl"
    monkeypatch.setattr(hud_calibration, "CALIBRATION_FILE", written)
    monkeypatch.setattr("pitcrew.controller.note_frame_red",
                        hud_calibration.note_frame_red)

    controller, _, _, _ = raced
    controller.start_race()
    green(controller)
    a_lap(controller, 1, 88.6)
    controller._show_ptt_answer("tyres are red", "Copy, noted.")

    row = json.loads(written.read_text(encoding="utf-8").strip())
    assert row["driverReport"] == "tyre frame went red"
    assert row["tempC"]["fl"] is not None
    assert row["frontMeanC"] is not None and row["rearMeanC"] is not None
    assert row["lap"] == 1


def test_the_report_is_acknowledged_and_never_interpreted():
    """One observation is one observation. Telling him what it means would be
    inventing the meaning the file exists to collect evidence for."""
    from pitcrew.engineer.intents import TYRES_RED, answer, match_intent

    assert match_intent("the tyres are red") == TYRES_RED
    assert match_intent("front left went red") == TYRES_RED
    said = answer(TYRES_RED, {})
    assert said.answered is True
    assert "noted" in said.text.lower()
    assert "hot" not in said.text.lower()


def test_the_driver_can_ask_whether_he_is_on_the_plan():
    """The lap-to-lap reference, answered out loud. **The two halves are not
    symmetric**: burn is quoted as a figure he can act on, pace only when it
    clears the noise floor measured on this car at this circuit."""
    from pitcrew.engineer.intents import ON_PLAN, answer, match_intent

    assert match_intent("are we on the plan") == ON_PLAN
    assert match_intent("how's the burn") == ON_PLAN

    nothing_yet = answer(ON_PLAN, {})
    assert nothing_yet.answered is False
    assert "don't have" in nothing_yet.text

    quiet = answer(ON_PLAN, {"burnVsPlanPct": -10.6, "paceIsReal": False,
                             "paceDetectableMs": 1990})
    assert "Burn 11 percent under plan" in quiet.text
    assert "inside the 2.0 a lap I can see" in quiet.text

    real = answer(ON_PLAN, {"burnVsPlanPct": 6.0, "paceIsReal": True,
                            "paceVsPlanMs": 2400, "paceDetectableMs": 1990})
    assert "Pace 2.4 a lap down" in real.text


# --------------------------------------------- one thing at a time, end to end

def test_only_one_thing_is_voiced_per_crossing(raced, monkeypatch, voice):
    """The coordinator and the re-planner both had a voice and neither knew
    about the other. On lap 8 of the measured race that produced "Recommend
    running to the flag." and "Box this lap. RS. 1 lap overdue." on the same
    crossing - two opposite instructions, §5.5 allows one."""
    from pitcrew.race.replan import RECOMMENDED, Replan

    controller, _, _, _ = raced
    controller.start_race()
    green(controller)
    _always(controller, monkeypatch,
            Replan(RECOMMENDED, "burning 20% less fuel than planned",
                   stops=0, stint_laps=(12,), gain_s=40.0))
    before = len(voice.spoken)
    for lap_num in range(1, 12):
        said = len(voice.spoken)
        a_lap(controller, lap_num, 92.0 - lap_num * 3.4)
        assert len(voice.spoken) - said <= 1, (lap_num, voice.spoken[said:])
    assert len(voice.spoken) > before


def test_a_box_call_outranks_a_strategy_recommendation(raced):
    """It is an immediate instruction and the recommendation is about a stop
    some laps away. The recommendation is HELD, not discarded - it changes no
    state, so the next lap decides it again."""
    from pitcrew.race.calls import BOX_NOW, Call
    from pitcrew.race.replan import NOTED, RECOMMENDED, URGENT, Replan

    box = Call(BOX_NOW, 8, "Box this lap.", "")
    outranks = PitCrewController._replan_outranks
    assert outranks(Replan(RECOMMENDED, "", stops=0), box) is False
    # Not reaching the flag is arithmetic, and it cuts through.
    assert outranks(Replan(URGENT, "", stops=1), box) is True
    # A note about the burn waits behind everything.
    assert outranks(Replan(NOTED, "burning 8% under"), box) is False
    assert outranks(Replan(RECOMMENDED, "", stops=0), None) is True


# ------------------------------------------------------- the driver's answers

def test_keeping_the_plan_is_remembered_as_his_choice(raced, monkeypatch):
    """`answered(accepted=False)` used to clear the driver's shape instead of
    setting it, against its own docstring. He said keep on one lap and the
    next lap heard "the stop count has changed - Recommend 2 stops": the plan
    of record, offered back as news, one lap after he refused to change it."""
    from pitcrew.race.replan import RECOMMENDED, Replan

    controller, _, _, _ = raced
    controller.start_race()
    green(controller)
    offer = Replan(RECOMMENDED, "burning 20% more fuel than planned",
                   stops=2, stint_laps=(7, 6), gain_s=12.0,
                   laps_to_next_stop=7)
    _always(controller, monkeypatch, offer)
    a_lap(controller, 1, 88.6)
    assert controller.ptt.pending_replan

    controller._resolve_replan(accepted=False)
    assert controller._replans.driver_shape_stops is not None

    spoke = len(controller.voice.spoken) if hasattr(
        controller.voice, "spoken") else None
    a_lap(controller, 2, 85.2)
    # The shape he kept is not re-offered to him as a change.
    assert controller.ptt.pending_replan is None
    if spoke is not None:
        assert all("Recommend" not in line
                   for line in controller.voice.spoken[spoke:])


def test_an_acknowledgement_is_not_an_acceptance(raced, monkeypatch):
    """ACCEPT's vocabulary includes "copy that", which he says to acknowledge
    ANY call. The gate used to be "the register has said something", which
    every spoken verdict sets - including the burn notes, which are facts and
    not questions - and which then stayed set for the rest of the race. One
    stray acknowledgement locked the register onto a shape and wrote an empty
    resolution row."""
    from pitcrew.race.replan import NONE, Replan

    controller, _, store, event_id = raced
    controller.start_race()
    green(controller)
    _always(controller, monkeypatch, Replan(NONE, "on the plan"))
    a_lap(controller, 1, 88.6)
    assert controller.ptt.pending_replan is None

    before = len(store.list_revisions(store.list_race_runs(event_id)[0]["id"]))
    controller._show_ptt_answer("copy that", "")
    after = store.list_revisions(store.list_race_runs(event_id)[0]["id"])
    assert len(after) == before
    assert controller._replans.driver_shape_stops is None


# ------------------------------------------------------- the re-plan's budget

def test_an_oversized_search_is_refused_before_it_is_attempted(
        raced, monkeypatch):
    """**A budget measured after the solve is not a budget.** Timing `assess`
    and reacting afterwards means the 6.35-second solve happens in full, on
    this thread, mid-race - and then the narrowed retry happens too."""
    controller, _, _, _ = raced
    controller.start_race()
    green(controller)
    monkeypatch.setattr("pitcrew.controller.replan_work",
                        lambda *args, **kwargs: 99_999)
    monkeypatch.setattr("pitcrew.controller.assess",
                        lambda **kwargs: pytest.fail("must not be attempted"))
    a_lap(controller, 1, 88.6)
    assert controller._replan_max_stops == 0


def test_the_driver_is_told_when_the_engineer_stops_adapting(
        raced, monkeypatch, voice):
    """Silence from an adviser is indistinguishable from an adviser with
    nothing to say - the status call promises exactly that reading. An
    engineer that has quietly stopped adapting the strategy is worse than one
    that never offered to."""
    controller, _, _, _ = raced
    controller.start_race()
    green(controller)
    monkeypatch.setattr("pitcrew.controller.replan_work",
                        lambda *args, **kwargs: 99_999)
    a_lap(controller, 1, 88.6)

    assert any("re-planning is off" in line for line in voice.spoken)
    assert controller._race_snapshot()["replanning"] is False
    # Said once, not once a lap.
    said = sum(1 for line in voice.spoken if "re-planning is off" in line)
    a_lap(controller, 2, 85.2)
    assert sum(1 for line in voice.spoken
               if "re-planning is off" in line) == said

