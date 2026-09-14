"""0.6 and 0.7 - what the driver hears is fewer things, each marked for what it is.

Deep Forest, 6 Sep 2026: nine position flaps, a championship line six times in
thirty seconds mid-battle, the same fuel figure spoken twice inside a minute,
a haptics fault announced on the out-lap, "Box now and the car behind comes
out in front" three laps before a stop was due, "Short-shift and lift" three
times while eight laps short with no stop planned - and a push-to-talk "gap"
that refused while the pit wall was reading 154 gap frames.
"""
from __future__ import annotations

from pitcrew.engineer.intents import GAP, answer
from pitcrew.race.calls import (BOX_NOW, FUEL_LONG, FUEL_SHORT, HIGH,
                                POSITION, POSITION_HOLD_FRAMES, TYRE_TEMP,
                                Call, RaceState, _fuel, position_change)
from pitcrew.race.rival_calls import rejoin_call
from pitcrew.rig.supervisor import RigSupervisor


# ------------------------------------------------------------- PTT "gap"

def test_gap_answers_from_the_walls_reading():
    reply = answer(GAP, {"wallRunning": True, "gapAheadS": 3.4,
                         "gapAheadName": "Boxhead",
                         "gapAheadClosingSPerLap": 0.8,
                         "gapAheadTrendLaps": 6,
                         "gapBehindS": 10.2, "gapBehindName": None,
                         "gapBehindClosingSPerLap": -0.3,
                         "gapBehindTrendLaps": 6})
    assert reply.answered is True
    # Row 1.10: "a lap" carried seconds in five places and litres in two.
    # **One car, the nearer, in the board's words** (11 Sep 2026): it was a
    # two-row table with "closing" meaning opposite driving on each side.
    assert reply.text == ("Boxhead is 3.4 seconds ahead - you're catching "
                          "him 0.8 seconds a lap.")
    assert "10.2" not in reply.text


def test_gap_with_no_reading_yet_says_so_and_invites_a_retry():
    reply = answer(GAP, {"wallRunning": True})
    assert reply.answered is False
    assert "No gap read yet" in reply.text


def test_gap_with_no_wall_names_the_missing_instrument():
    reply = answer(GAP, {"wallRunning": False})
    assert reply.answered is False
    assert "No pit wall" in reply.text
    assert "position" in reply.text


def test_a_tiny_rate_is_not_called_closing_or_opening():
    reply = answer(GAP, {"wallRunning": True, "gapAheadS": 3.4,
                         "gapAheadClosingSPerLap": 0.05,
                         "gapAheadTrendLaps": 6})
    # "steady" - the board's word for the same reading.
    assert reply.text == "The car ahead is 3.4 seconds away - steady."


# -------------------------------------------------------------- registers

def test_a_suggestion_is_marked_and_an_instruction_is_not():
    push = Call(FUEL_LONG, 8, "You can push.", "2.1 laps in hand to the flag.")
    box = Call(BOX_NOW, 11, "Box this lap. No tyres.", "Fuel to 63 litres.")
    ease = Call(TYRE_TEMP, 6, "Ease the traction out of the slow corners.",
                "Rears 8 over the fronts.")
    assert push.spoken().endswith("Suggestion.")
    assert ease.spoken().endswith("Suggestion.")
    assert not box.spoken().endswith("Suggestion.")
    assert box.spoken() == "Box this lap. No tyres. Fuel to 63 litres."


# --------------------------------------------------------------- position

def _racing(position=3):
    return RaceState(lap=5, laps_total=20, position=position,
                     position_said=position, field_size=8)


def test_a_place_has_to_hold_for_eight_seconds():
    assert POSITION_HOLD_FRAMES == 8 * 60
    state = _racing(3)
    state.position = 2
    for _ in range(POSITION_HOLD_FRAMES - 1):
        assert position_change(state) is None
    call = position_change(state)
    assert call is not None and call.kind == POSITION
    assert call.call == "P2 of 8."


def test_a_side_by_side_that_swaps_back_says_nothing():
    """P2 / P3 / P2 / P3 inside a straight was seven sentences."""
    state = _racing(3)
    for _ in range(4):
        state.position = 2
        for _ in range(120):
            assert position_change(state) is None
        state.position = 3
        for _ in range(120):
            assert position_change(state) is None


# ------------------------------------------------------------------- fuel

def _fuelled(**over):
    fields = dict(lap=8, laps_total=20, fuel_l=60.0, fuel_per_lap_l=5.0,
                  stint_ends_on_lap=10, laps_since_stop=8,
                  laps_estimate_firm=True)
    fields.update(over)
    return RaceState(**fields)


def test_a_shortfall_no_lever_can_cover_is_a_stop_when_none_is_planned():
    """The sim: 6-8 laps short of the flag, no plan, 'short-shift and lift'."""
    state = _fuelled(fuel_l=30.0, fuel_per_lap_l=7.8, stint_ends_on_lap=None,
                     next_stint_laps=None, lap=2, laps_since_stop=2)
    call = _fuel(state)
    assert call is not None and call.kind == FUEL_SHORT
    assert call.call == "Fuel needs a stop."
    assert "cannot cover" in call.reason


def test_a_shortfall_with_a_stop_planned_still_asks_for_the_saving():
    state = _fuelled(fuel_l=10.0, stint_ends_on_lap=12, lap=5,
                     laps_since_stop=5)
    call = _fuel(state)
    assert call is not None and call.kind == FUEL_SHORT
    assert "Short-shift" in call.call


def test_a_small_shortfall_with_no_plan_is_still_a_saving_call():
    """Half a lap short over 12 to run is inside what a short-shift recovers.

    To the flag it is said as the save in litres (Suzuka, 13 Sep 2026):
    0.6 laps x 7.8 L over 12 laps is 0.39, asked as 0.4."""
    state = _fuelled(fuel_l=7.8 * 11.4, fuel_per_lap_l=7.8,
                     stint_ends_on_lap=None, laps_total=20, lap=8)
    call = _fuel(state)
    assert call is not None and call.kind == FUEL_SHORT
    assert call.call == "Save 0.4 litres a lap to make the flag."
    assert "stop" not in call.spoken().lower()


# ------------------------------------------------------------------ rejoin

def _rejoin(due):
    return rejoin_call(lap=8, gap_behind_s=30.0, litres_to_take=35.0,
                       refuel_rate_lps=2.0, pit_loss_s=20.0,
                       pit_loss_source="measured", who="Boxhead", due=due)


def test_a_rejoin_call_is_an_instruction_only_when_the_stop_is_due():
    due = _rejoin(True)
    not_due = _rejoin(False)
    # Row 1.10, §5.5: the first two words were the box instruction and the
    # call means the opposite - he acts on "Box now" before the qualifier
    # arrives. The `due=False` variant already led with the consequence.
    assert due.call == "Boxhead comes out in front if you box now."
    assert due.confidence == HIGH
    assert not_due.call == "A stop now puts you behind Boxhead."
    assert not_due.confidence != HIGH
    assert due.reason == not_due.reason


# --------------------------------------------------------------------- rig

class _Voice:
    def __init__(self):
        self.said = []

    def say(self, text):
        self.said.append(text)


class _Watchdog:
    def __init__(self, notice):
        self._notice = notice

    def take_notice(self):
        notice, self._notice = self._notice, None
        return notice


def _supervisor(voice):
    return RigSupervisor(bridge=object(), settings=object(), voice=voice)


def test_a_rig_notice_is_held_while_a_race_runs_and_said_at_the_flag():
    voice = _Voice()
    rig = _supervisor(voice)
    racing = {"on": True}
    rig.hold_spoken_while = lambda: racing["on"]
    rig._deliver_rig_notice(_Watchdog(("written", "Check the amp after the race.")))
    assert voice.said == []
    racing["on"] = False
    rig.release_notices()
    assert voice.said == ["Check the amp after the race."]
    rig.release_notices()
    assert voice.said == ["Check the amp after the race."], "released once"


def test_a_rig_notice_outside_a_race_is_said_at_once():
    voice = _Voice()
    rig = _supervisor(voice)
    rig.hold_spoken_while = lambda: False
    rig._deliver_rig_notice(_Watchdog(("written", "Haptics are back.")))
    assert voice.said == ["Haptics are back."]


def test_no_hold_predicate_means_the_old_behaviour():
    voice = _Voice()
    rig = _supervisor(voice)
    rig._deliver_rig_notice(_Watchdog(("written", "spoken")))
    assert voice.said == ["spoken"]
