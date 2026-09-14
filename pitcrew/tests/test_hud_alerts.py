"""Contact and water said out loud - `race/hud_alerts.py` - replayed on real reads.

`fixtures/hud_alert_reads.npz` (built by `tools/build_hud_alert_fixture.py`)
holds what the real readers made of real frames, and the real grab cadence:

* session 166, the dry Suzuka race: every 0.25 s, both contact episodes at 60 fps
  (rear lit 288-381 s, front 1266-1401 s);
* session 176, the dry Bathurst race: every 0.25 s, the LIVE icon reads rebuilt
  from its log, and its 1166 intervals between readable grabs;
* the driver's wet video: every 0.1 s, a tunnel at 133-138 s.

Every replay samples those reads at the live intervals, from several starting
phases, so the 2 Hz pulse is seen the way a 2.2 s grab sees it.
"""
from __future__ import annotations

import threading
import time
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from pitcrew.race import hud_alerts as H
from pitcrew.race.calls import (CONTACT, CONTACT_CLEAR, EVENT, FACT, REGISTER,
                                URGENCY, WATER, WATER_DRY, Call)
from pitcrew.race.hud_alerts import HudAlerts
from pitcrew.telemetry.hud_damage import MIN_ARC_PX

from .test_controller import qt_app  # noqa: F401
from .test_race_wiring import green, raced, voice  # noqa: F401

FIXTURE = Path(__file__).parent / "fixtures" / "hud_alert_reads.npz"
PHASES = (0, 137, 411, 777, 1003)
# Session 176's pit stop, in seconds from its video zero, off the lap frames:
# the speed step into the lane at 1626.4 s, back up to lane speed at 1719.5 s.
S176_PIT = (1626.4, 1722.0)


@pytest.fixture(scope="module")
def reads():
    return np.load(FIXTURE)


class _Source:
    def __init__(self, data, name):
        self.t0, self.fps = (float(x) for x in data[f"{name}__t0"])
        self.level = data[f"{name}__level"]
        self.front = data[f"{name}__front_px"]
        self.rear = data[f"{name}__rear_px"]

    @property
    def end(self) -> float:
        return self.t0 + (len(self.level) - 1) / self.fps

    def at(self, t):
        i = int(round((t - self.t0) * self.fps))
        if not 0 <= i < len(self.level):
            return None
        level = None if np.isnan(self.level[i]) else float(self.level[i])
        front = None if self.front[i] < 0 else int(self.front[i])
        rear = None if self.rear[i] < 0 else int(self.rear[i])
        return level, front, rear


def replay(data, base, *, episodes=(), phase=0, start=0.0, end=None,
           pit=None, intervals=None, shift=0.0, then=None):
    """`(t, text, kind)` said, feeding grabs at the live intervals.

    `then` is `(source, offset)`: after `end`, keep reading `source` at
    `t - offset` - a splice of two real captures.
    """
    base = _Source(data, base)
    windows = [_Source(data, name) for name in episodes]
    gaps = list(data["s176_live__intervals"]) if intervals is None else intervals
    alerts = HudAlerts()
    stop = base.end if end is None else end
    last = stop if then is None else then[2]
    t, k, said = start, phase, []
    while t <= last:
        if t <= stop:
            source = next((w for w in windows if w.t0 <= t <= w.end), base)
            read = source.at(t - shift)
        else:
            read = then[0].at(t - then[1])
        on_track = pit is None or not pit[0] <= t <= pit[1]
        level, front, rear = read if read is not None else (None, None, None)
        alerts.feed_damage(t, front, rear,
                           None if front is None else front >= MIN_ARC_PX,
                           None if rear is None else rear >= MIN_ARC_PX,
                           on_track=on_track)
        alerts.feed_hygro(t, level, on_track=on_track)
        said += [(t, call.call, call.kind)
                 for call in alerts.poll(t, lap=0, on_track=on_track)]
        t += float(gaps[k % len(gaps)])
        k += 1
    return said


def _lit_span(data, name, arc):
    source = _Source(data, name)
    px = source.rear if arc == "rear" else source.front
    lit = np.flatnonzero(px >= MIN_ARC_PX)
    return source.t0 + lit[0] / source.fps, source.t0 + lit[-1] / source.fps


# ------------------------------------------------------------ Suzuka, s166

@pytest.mark.parametrize("phase", PHASES)
def test_each_suzuka_contact_episode_is_one_onset_and_one_clear(reads, phase):
    said = replay(reads, "s166_4fps",
                  episodes=("s166_rear60", "s166_front60"), phase=phase)
    contact = [(t, text) for t, text, kind in said
               if kind in (CONTACT, CONTACT_CLEAR)]
    assert [text for _, text in contact] == [
        "Contact, rear.", "Contact warning's cleared.",
        "Contact, front.", "Contact warning's cleared."], contact
    rear_on, rear_off = _lit_span(reads, "s166_rear60", "rear")
    front_on, front_off = _lit_span(reads, "s166_front60", "front")
    (t1, _), (t2, _), (t3, _), (t4, _) = contact
    # Onset within a few grabs of the first lit frame (51 phases: rear 2.3-13.6
    # s, front 2.9-22.9 s - the front hit's first seconds are the pale,
    # mostly-0 px onset the reader documents).
    assert rear_on <= t1 <= rear_on + 20
    assert front_on <= t3 <= front_on + 25
    # Clear: CLEAR_S after the first clean grab. That grab can fall in a dim
    # half of the last pulses, a few seconds before the last lit FRAME (51
    # phases: 26.4-36.1 s after it).
    assert rear_off + H.CLEAR_S - 5 <= t2 <= rear_off + H.CLEAR_S + 10
    assert front_off + H.CLEAR_S - 5 <= t4 <= front_off + H.CLEAR_S + 10


@pytest.mark.parametrize("phase", PHASES)
def test_the_dry_suzuka_race_says_nothing_about_water(reads, phase):
    """21 of its 6015 readable frames fill past the wet level - kerbs and sky
    flooding the see-through panel, never two within 10 s."""
    said = replay(reads, "s166_4fps",
                  episodes=("s166_rear60", "s166_front60"), phase=phase)
    assert not [s for s in said if s[2] in (WATER, WATER_DRY)]


def test_not_even_at_the_half_second_regrab(reads):
    """When the gauge refuses, the sampler grabs again every ~0.5 s."""
    said = replay(reads, "s166_4fps", intervals=[0.55])
    assert not [s for s in said if s[2] in (WATER, WATER_DRY)]


# ------------------------------------------------------------ Bathurst, s176

def test_the_live_bathurst_reads_give_this_transcript(reads):
    """Session 176's LIVE icon reads, rebuilt from its log. Each onset falls on
    a lap the laps table credits with off-track time (1, 8, 9, 11, 14, 16,
    19); the front-and-rear episodes name no end; the rear arc lighting 19 s
    into lap 19's front episode is said as a second hit."""
    alerts = HudAlerts()
    said = []
    for at, front, rear in reads["s176_live__grabs"]:
        at = float(at)
        on_track = not S176_PIT[0] <= at <= S176_PIT[1]
        alerts.feed_damage(at, int(front), int(rear), front >= MIN_ARC_PX,
                           rear >= MIN_ARC_PX, on_track=on_track)
        said += [(round(at), call.call)
                 for call in alerts.poll(at, lap=0, on_track=on_track)]
    assert [text for _, text in said] == [
        "Contact, front.", "Contact warning's cleared.",
        "Contact, front.", "Contact warning's cleared.",
        "Contact.", "Contact warning's cleared.",
        "Contact.", "Contact warning's cleared.",
        "Contact, front.", "Contact warning's cleared.",
        "Contact, front.", "Contact warning's cleared.",
        "Contact, front.", "Contact again, rear.",
        "Contact warning's cleared."]
    times = [t for t, _ in said]
    assert times == sorted(times)
    assert 185 <= times[0] <= 195            # first lit 20:22:21 = 187 s
    assert times[-2] - times[-3] < 30        # the second hit, inside the first


def test_the_dry_bathurst_race_says_nothing_about_water(reads):
    said = replay(reads, "s176_4fps", pit=S176_PIT)
    assert not [s for s in said if s[2] in (WATER, WATER_DRY)]


def test_the_bathurst_pit_stop_is_unreadable_and_says_nothing(reads):
    """The lane on the recording: no bars found on any frame of the stop."""
    source = _Source(reads, "s176_4fps")
    stop = [source.at(t) for t in np.arange(1630.0, 1715.0, 0.25)]
    assert all(read[1] is None for read in stop)


# ------------------------------------------------------------ the wet video

@pytest.mark.parametrize("phase", PHASES)
def test_the_wet_video_says_water_once_and_the_tunnel_does_not_flap(reads, phase):
    said = replay(reads, "wet10", phase=phase)
    assert [(text, kind) for _, text, kind in said] == [("Water on track.",
                                                          WATER)]
    assert said[0][0] <= 12.0            # first wet frame at 1.4 s
    source = _Source(reads, "wet10")
    tunnel = [source.at(t)[0] for t in np.arange(133.5, 137.9, 0.1)]
    assert max(tunnel) < 0.3             # the tunnel really read dry


def test_wet_then_a_dry_race_says_dry_once_after_most_of_a_lap(reads):
    """A splice of two real captures: the wet video, then Suzuka's dry frames."""
    dry = _Source(reads, "s166_4fps")
    said = replay(reads, "wet10", end=160.0, then=(dry, 160.0 - 500.0, 400.0))
    assert [text for _, text, _ in said] == ["Water on track.",
                                             "Track looks dry again."]
    assert 160.0 + H.WATER_DRY_SPAN_S <= said[1][0] <= 160.0 + 100.0


def test_a_tunnel_on_a_long_wet_run_never_says_dry():
    alerts = HudAlerts()
    said, t = [], 0.0
    while t < 600.0:
        in_tunnel = 200.0 <= t % 240.0 <= 206.0
        alerts.feed_hygro(t, 0.0 if in_tunnel else 0.7, on_track=True)
        said += [c.call for c in alerts.poll(t, lap=0, on_track=True)]
        t += 2.2
    assert said == ["Water on track."]


# ------------------------------------------------------------ the rules

def _feed(alerts, at, front, rear, *, on_track=True):
    alerts.feed_damage(at, front, rear,
                       None if front is None else front >= MIN_ARC_PX,
                       None if rear is None else rear >= MIN_ARC_PX,
                       on_track=on_track)
    return [c.call for c in alerts.poll(at, lap=0, on_track=on_track)]


def test_red_in_the_pit_lane_is_never_said_nor_counted():
    alerts = HudAlerts()
    said = []
    for i in range(40):                         # 88 s of red in the lane
        said += _feed(alerts, i * 2.2, 40, 40, on_track=False)
    assert said == []
    assert alerts.contact.episode is None
    # Out of the box: one lit read on track is not two.
    assert _feed(alerts, 90.0, 40, 0) == []


def test_an_onset_owed_at_the_pit_entry_waits_for_the_exit():
    alerts = HudAlerts()
    _feed(alerts, 0.0, 0, 30)
    alerts.feed_damage(2.2, 0, 30, False, True, on_track=True)
    assert alerts.poll(2.3, lap=0, on_track=False) == []
    assert [c.call for c in alerts.poll(40.0, lap=0, on_track=True)] == [
        "Contact, rear."]


def test_a_stop_breaks_a_clear_run():
    alerts = HudAlerts()
    for i in range(3):
        _feed(alerts, i * 2.2, 30, 0)
    t = 6.6
    for _ in range(6):                          # 13 s clean before the lane
        assert _feed(alerts, t, 0, 0) == []
        t += 2.2
    for _ in range(30):                         # the stop
        assert _feed(alerts, t, 0, 0, on_track=False) == []
        t += 2.2
    said = []
    exit_at = t
    while t < exit_at + 40:
        said += [(t, s) for s in _feed(alerts, t, 0, 0)]
        t += 2.2
    assert [s for _, s in said] == ["Contact warning's cleared."]
    assert said[0][0] >= exit_at + H.CLEAR_S


def test_a_blind_reader_never_claims_cleared_and_retires_the_episode():
    alerts = HudAlerts()
    assert _feed(alerts, 0.0, 30, 0) == []
    assert _feed(alerts, 2.2, 30, 0) == ["Contact, front."]
    said, t = [], 4.4
    while t < 600.0:                            # ten minutes of nothing
        said += _feed(alerts, t, None, None)
        t += 2.2
    assert said == []
    assert alerts.contact.episode is None       # retired, silently
    # A hit after that is a new one, and said.
    assert _feed(alerts, t, 30, 0) == []
    assert _feed(alerts, t + 2.2, 30, 0) == ["Contact, front."]


def test_after_a_short_blind_spell_a_clean_run_is_still_the_evidence():
    alerts = HudAlerts()
    _feed(alerts, 0.0, 30, 0)
    _feed(alerts, 2.2, 30, 0)
    t = 4.4
    while t < 64.0:                             # a minute blind
        assert _feed(alerts, t, None, None) == []
        t += 2.2
    said = []
    while t < 110.0:
        said += [(t, s) for s in _feed(alerts, t, 0, 0)]
        t += 2.2
    assert [s for _, s in said] == ["Contact warning's cleared."]
    assert said[0][0] >= 64.0 + H.CLEAR_S


def test_both_arcs_at_onset_say_contact_and_never_again():
    alerts = HudAlerts()
    assert _feed(alerts, 0.0, 30, 40) == []
    assert _feed(alerts, 2.2, 30, 40) == ["Contact."]
    assert _feed(alerts, 4.4, 30, 40) == []


def test_red_below_the_bar_on_the_other_arc_names_no_end():
    alerts = HudAlerts()
    _feed(alerts, 0.0, 30, 3)
    assert _feed(alerts, 2.2, 30, 0) == ["Contact."]


def test_the_other_end_lighting_later_is_contact_again_said_once():
    alerts = HudAlerts()
    _feed(alerts, 0.0, 30, 0)
    assert _feed(alerts, 2.2, 30, 0) == ["Contact, front."]
    assert _feed(alerts, 10.0, 30, 40) == []
    assert _feed(alerts, 12.2, 0, 40) == ["Contact again, rear."]
    assert _feed(alerts, 14.4, 30, 40) == []
    assert _feed(alerts, 16.6, 30, 40) == []


def test_the_pulse_is_never_announced_twice():
    alerts = HudAlerts()
    said, t = [], 0.0
    pattern = [30, 0, 0, 30, 30, 0, 30, 0, 0, 0, 30]    # 3 dim grabs live max
    while t < 100.0:
        said += _feed(alerts, t, pattern[int(t / 2.2) % len(pattern)], 0)
        t += 2.2
    assert said == ["Contact, front."]


def test_contact_onset_rests_on_contact_recents_own_constants():
    from pitcrew.telemetry.hud_session import DAMAGE_MIN_LIT, DAMAGE_WINDOW_S

    assert H.CONTACT_WINDOW_S == DAMAGE_WINDOW_S
    assert H.CONTACT_MIN_LIT == DAMAGE_MIN_LIT
    assert H.CLEAR_S > 14.5 * 2 - 0.1           # twice the worst replayed run


def test_the_water_onset_is_at_most_as_eager_as_the_wet_light():
    from pitcrew.telemetry.hud_session import HYGRO_MIN_READS, HYGRO_WINDOW_S
    from pitcrew.telemetry.hygrometer import LAP_DRY_SHARE

    assert H.WATER_ON_WINDOW_S == HYGRO_WINDOW_S
    assert H.WATER_ON_MIN_WET >= HYGRO_MIN_READS
    assert H.WATER_DRY_SHARE == LAP_DRY_SHARE


# ------------------------------------------------------------ said means heard

def _onset(alerts, at=0.0):
    alerts.feed_damage(at, 30, 0, True, False, on_track=True)
    alerts.feed_damage(at + 2.2, 30, 0, True, False, on_track=True)


def test_an_alert_is_retired_only_when_heard():
    alerts = HudAlerts()
    alerts.acknowledged_delivery = True
    _onset(alerts)
    (call,) = alerts.poll(3.0, lap=4, on_track=True)
    assert alerts.awaits_delivery(call)
    assert alerts.poll(4.0, lap=4, on_track=True) == []       # in flight
    alerts.delivered(call, False)
    (again,) = alerts.poll(5.0, lap=4, on_track=True)
    assert again.call == "Contact, front." and again is not call
    alerts.delivered(again, True)
    assert alerts.poll(6.0, lap=4, on_track=True) == []


def test_a_clear_waits_for_its_onset_to_be_heard():
    alerts = HudAlerts()
    alerts.acknowledged_delivery = True
    _onset(alerts)
    (onset,) = alerts.poll(3.0, lap=4, on_track=True)
    t = 5.0
    while t < 40.0:                  # cleared, inside the 45 s ack timeout
        alerts.feed_damage(t, 0, 0, False, False, on_track=True)
        t += 2.2
    assert alerts.contact.episode is None
    # Cleared while the onset is still queued: nothing yet.
    assert alerts.poll(t, lap=4, on_track=True) == []
    alerts.delivered(onset, True)
    (clear,) = alerts.poll(t + 1, lap=4, on_track=True)
    assert clear.kind == CONTACT_CLEAR


def test_an_onset_never_heard_takes_its_clear_with_it():
    alerts = HudAlerts()
    alerts.acknowledged_delivery = True
    _onset(alerts)
    (onset,) = alerts.poll(3.0, lap=4, on_track=True)
    t = 5.0
    while t < 60.0:
        alerts.feed_damage(t, 0, 0, False, False, on_track=True)
        t += 2.2
    alerts.delivered(onset, False)
    assert alerts.poll(t, lap=4, on_track=True) == []
    assert alerts.poll(t + 1, lap=4, on_track=True) == []


def test_a_hand_over_nobody_answers_is_released():
    alerts = HudAlerts()
    alerts.acknowledged_delivery = True
    _onset(alerts)
    (call,) = alerts.poll(3.0, lap=4, on_track=True)
    (again,) = alerts.poll(3.0 + H.ACK_TIMEOUT_S + 1, lap=4, on_track=True)
    assert again.call == call.call


def test_a_new_session_forgets_the_icon_and_the_water():
    alerts = HudAlerts()
    alerts.acknowledged_delivery = True
    _onset(alerts)
    (call,) = alerts.poll(3.0, lap=4, on_track=True)
    alerts.new_session()
    assert not alerts.awaits_delivery(call)
    alerts.delivered(call, False)                # a late answer changes nothing
    assert alerts.poll(4.0, lap=0, on_track=True) == []
    assert alerts.contact.episode is None and alerts.water.episode is None


def test_the_call_carries_its_why_and_lap():
    alerts = HudAlerts()
    _onset(alerts)
    (call,) = alerts.poll(3.0, lap=7, on_track=True)
    assert call.lap == 7 and call.spoken() == "Contact, front."
    assert "not the car's condition" in call.why_spoken


# ------------------------------------------------------------ vocabulary

def test_onsets_are_events_and_clears_are_news():
    from pitcrew.engineer.voice import EVENT as V_EVENT
    from pitcrew.engineer.voice import NEWS, class_of

    assert class_of(CONTACT) == V_EVENT and class_of(WATER) == V_EVENT
    assert class_of(CONTACT_CLEAR) == NEWS and class_of(WATER_DRY) == NEWS
    assert REGISTER[CONTACT] == EVENT and REGISTER[WATER] == EVENT
    assert REGISTER[CONTACT_CLEAR] == FACT and REGISTER[WATER_DRY] == FACT
    assert all(kind in URGENCY for kind in (CONTACT, WATER, CONTACT_CLEAR,
                                            WATER_DRY))


@pytest.mark.parametrize("kind", (CONTACT, CONTACT_CLEAR, WATER, WATER_DRY))
def test_every_alert_is_cannot_tell_with_its_own_reason(kind):
    from pitcrew.race.call_outcome import CANNOT_TELL, outcome_for

    outcome = outcome_for(Call(kind, 3, "x", ""), [])
    assert outcome.verdict == CANNOT_TELL and outcome.settled
    assert "nothing on file answers" not in outcome.detail


def test_the_words_never_claim_the_car_or_the_circuit():
    for line in H.fixed_lines():
        lowered = line.lower()
        assert "damage" not in lowered and "repair" not in lowered
        assert "rain" not in lowered and "wet" not in lowered


def test_every_alert_line_plays_whole_from_the_pack():
    from pitcrew.engineer import phrase_manifest as manifest

    clips = set(manifest.clips())
    for line in H.fixed_lines():
        assert line in clips
        assert manifest.segments_for(line) == (line,)


# ------------------------------------------------------------ the controller

class Recorder:
    enabled = True
    busy = False

    def __init__(self) -> None:
        self.said: list = []

    def say(self, text, kind=None, on_done=None):
        self.said.append((text, kind, on_done))

    def stop(self):
        pass


def _until(predicate, timeout: float = 3.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return predicate()


def _lit_history(controller, now):
    controller.hud._damage.extend([(now - 4.0, 30, 0, True, False),
                                   (now - 2.0, 32, 0, True, False)])


@pytest.fixture()
def race_controller(raced):  # noqa: F811
    controller, _, store, _ = raced
    controller.start_race()
    green(controller)
    return controller, store


def test_a_race_contact_is_an_event_filed_when_heard(race_controller, qt_app,
                                                     monkeypatch):
    from pitcrew.engineer.voice import EVENT as V_EVENT
    from pitcrew.engineer.voice import class_of
    from pitcrew.race.call_outcome import CANNOT_TELL

    controller, store = race_controller
    monkeypatch.setattr(controller.bridge, "state",
                        SimpleNamespace(on_track=True, phase=None,
                                        lap_count=2))
    recorder = controller.voice = Recorder()
    now = 10_000.0
    _lit_history(controller, now)
    controller._poll_hud_alerts(now=now)
    (text, kind, on_done), = recorder.said
    assert text == "Contact, front." and class_of(kind) == V_EVENT
    assert on_done is not None
    assert store.list_revisions(controller.race_run_id)[-1]["reason"] != text
    worker = threading.Thread(target=on_done, args=(True,))
    worker.start()
    worker.join()
    assert _until(lambda: (qt_app.processEvents() or True) and any(
        row["reason"] == text
        for row in store.list_revisions(controller.race_run_id)))
    row = [r for r in store.list_revisions(controller.race_run_id)
           if r["reason"] == text][-1]
    assert row["plan"]["kind"] == CONTACT
    assert "not the car's condition" in row["plan"]["why_spoken"]
    controller._judge_filed_calls(final=True)
    row = [r for r in store.list_revisions(controller.race_run_id)
           if r["reason"] == text][-1]
    assert row["verdict"] == CANNOT_TELL
    # Heard once: the next poll says nothing.
    controller._poll_hud_alerts(now=now + 1)
    assert len(recorder.said) == 1


def test_nothing_is_said_in_the_pit(race_controller, monkeypatch):
    controller, _ = race_controller
    monkeypatch.setattr(controller.bridge, "state",
                        SimpleNamespace(on_track=True, phase=None,
                                        lap_count=2))
    controller.race.state.in_pit = True
    recorder = controller.voice = Recorder()
    now = 10_000.0
    _lit_history(controller, now)
    controller._poll_hud_alerts(now=now)
    assert recorder.said == []


def test_the_race_arm_resets_the_alerts(race_controller, monkeypatch):
    controller, _ = race_controller
    alerts = controller._hud_alerts
    _onset(alerts, 1.0)
    assert alerts.contact.episode is not None
    controller._new_hud_session()
    assert alerts.contact.episode is None


def test_practice_speaks_the_alerts_too(raced, monkeypatch):
    controller, _, _, _ = raced
    assert controller.session_id is not None and controller.race is None
    monkeypatch.setattr(controller.bridge, "state",
                        SimpleNamespace(on_track=True, phase=None,
                                        lap_count=5))
    recorder = controller.voice = Recorder()
    shown = []
    monkeypatch.setattr(controller.practice, "set_status",
                        lambda text, **_: shown.append(text))
    now = 20_000.0
    controller.hud._hygro.extend([(now - 6.0, 0.7), (now - 4.0, 0.7),
                                  (now - 1.0, 0.71)])
    controller._poll_hud_alerts(now=now)
    assert [(text, kind) for text, kind, _ in recorder.said] == [
        ("Water on track.", WATER)]
    assert shown == ["Water on track."]
