"""The race, driven through the controller with a fake voice."""
from __future__ import annotations

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
        assert revision["plan"]["call"]["call"]
        assert revision["plan"]["confidence"] in ("high", "medium", "low")


def test_declined_calls_are_kept(raced):
    """A call offered and ignored is evidence about the model."""
    controller, _, store, event_id = raced
    controller.start_race()
    green(controller)
    a_lap(controller, 1, 88.0)

    runs = store.list_race_runs(event_id)
    revisions = store.list_revisions(runs[0]["id"])
    assert all(r["accepted"] is False for r in revisions)


def test_an_expired_offer_is_recorded_not_vanished(raced, monkeypatch):
    """One unanswered offer once gagged the loop for 29 minutes AND never
    reached `race_revisions` - offers were only recorded on resolve, and it
    was never resolved. Expiry is a resolution now, and it is filed."""
    from pitcrew.race.replan import RECOMMENDED, Replan

    controller, _, store, event_id = raced
    controller.start_race()
    green(controller)
    offer = Replan(RECOMMENDED, "burning 20% more fuel than planned",
                   stops=2, stint_laps=(7, 6), gain_s=12.0)
    monkeypatch.setattr("pitcrew.controller.assess", lambda **kwargs: offer)
    for lap_num in range(1, 5):
        a_lap(controller, lap_num, 92.0 - lap_num * 3.4)

    revisions = store.list_revisions(store.list_race_runs(event_id)[0]["id"])
    expired = [r for r in revisions
               if r["plan"].get("resolution") == "expired unanswered"]
    assert len(expired) == 1
    assert expired[0]["accepted"] is False
    assert controller._replans.pending is None


def test_a_superseding_offer_is_spoken_and_the_old_one_recorded(
        raced, monkeypatch, voice):
    from pitcrew.race.replan import NONE, RECOMMENDED, URGENT, Replan

    controller, _, store, event_id = raced
    controller.start_race()
    green(controller)
    verdicts = iter([
        Replan(RECOMMENDED, "burning more fuel than planned",
               stops=2, stint_laps=(7, 6), gain_s=12.0),
        Replan(URGENT, "1.4 laps short of the flag on current burn",
               stops=1, stint_laps=(9,), confidence="high"),
    ])
    fallback = Replan(NONE, "on the plan")
    monkeypatch.setattr("pitcrew.controller.assess",
                        lambda **kwargs: next(verdicts, fallback))
    a_lap(controller, 1, 88.6)
    a_lap(controller, 2, 85.2)

    revisions = store.list_revisions(store.list_race_runs(event_id)[0]["id"])
    superseded = [r for r in revisions
                  if r["plan"].get("resolution") == "superseded by a new offer"]
    assert len(superseded) == 1
    assert controller._replans.pending is not None
    assert controller._replans.pending.verdict == URGENT
    assert any("1 stop" in line for line in voice.spoken)


def test_a_pending_offer_at_teardown_is_recorded_not_vanished(
        raced, monkeypatch):
    """An offer voiced in the final laps used to vanish from the record
    entirely when the race closed on it - the audit hole the forensics
    documented. Teardown drains it as "race ended unanswered"."""
    from pitcrew.race.replan import RECOMMENDED, Replan

    controller, _, store, event_id = raced
    controller.start_race()
    green(controller)
    offer = Replan(RECOMMENDED, "burning 20% more fuel than planned",
                   stops=2, stint_laps=(7, 6), gain_s=12.0)
    monkeypatch.setattr("pitcrew.controller.assess", lambda **kwargs: offer)
    a_lap(controller, 1, 88.6)
    controller.stop_race()

    revisions = store.list_revisions(store.list_race_runs(event_id)[0]["id"])
    ended = [r for r in revisions
             if r["plan"].get("resolution") == "race ended unanswered"]
    assert len(ended) == 1
    assert ended[0]["accepted"] is False


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
