"""The tablet's field: every car the app knows, and what his fuel says.

17 Sep 2026, the driver: *"I want to see what everyone is doing here: on lap
they pitted, how much fuel in and out, and prediction on one or two stop."*
These hold the three ways it could lie: a guessed row for a car never read, a
fuel bound shown as a fill, and a prediction that disagrees with George's.
"""
from __future__ import annotations

from pitcrew.race import calls as C
from pitcrew.race.field import (
    CANNOT_TELL, NO_STOP_SEEN, REACHES_FLAG, SHORT_SAVES, STOPS_AGAIN,
    field_view, predict)
from pitcrew.race.gaps import GapTrend
from pitcrew.race.news import SAMPLE_HZ, BoardRead
from pitcrew.race.rival_calls import Rival
from pitcrew.race.rivals import Stop


def _rival(name, lap, out, *, burn=None, bound=False, fuel_in=8.0):
    return Rival(name=name, stop=Stop(lap=lap, fuel_in_l=fuel_in, fuel_out_l=out),
                 pitted=True, burn_per_lap_l=burn, exit_is_a_bound=bound)


# ------------------------------------------------------------- the prediction

def test_a_car_that_left_with_enough_reaches_the_flag_on_one_stop():
    got = predict(_rival("A", 10, 100.0, burn=4.0), stops_seen=1,
                  our_burn_l=5.0, laps_total=30)
    assert (got.words, got.total_stops, got.burn_of) == (REACHES_FLAG, 1, "his")
    assert got.unconfirmed is False


def test_a_few_per_cent_light_is_short_and_saves_not_a_second_stop():
    """He lifts rather than stopping: `SAVEABLE_FRACTION`."""
    got = predict(_rival("B", 10, 85.0), stops_seen=1, our_burn_l=5.0,
                  laps_total=30)
    assert (got.words, got.total_stops, got.burn_of) == (SHORT_SAVES, 1, "ours")


def test_a_car_well_short_stops_again_and_says_by_when():
    got = predict(_rival("C", 10, 50.0), stops_seen=1, our_burn_l=5.0,
                  laps_total=30)
    assert (got.words, got.total_stops, got.reaches_lap) == (STOPS_AGAIN, 2, 20)


def test_an_exit_bound_is_not_priced_as_a_fill():
    got = predict(_rival("D", 10, 30.0, bound=True), stops_seen=1,
                  our_burn_l=5.0, laps_total=30)
    assert got.words == CANNOT_TELL and "lower bound" in got.why


def test_no_stop_is_said_as_none_seen_and_a_timed_race_cannot_tell():
    assert predict(None, stops_seen=0, our_burn_l=5.0,
                   laps_total=30).words == NO_STOP_SEEN
    got = predict(_rival("E", 10, 60.0), stops_seen=1, our_burn_l=5.0,
                  laps_total=None)
    assert got.words == CANNOT_TELL and got.why == "no race length"


def test_a_shortfall_inside_the_reading_error_is_unconfirmed():
    """Needs 100, left on 98: two litres against ten of reading error."""
    got = predict(_rival("F", 10, 98.0), stops_seen=1, our_burn_l=5.0,
                  laps_total=30)
    assert got.words == SHORT_SAVES and got.unconfirmed is True


# ------------------------------------------------------------- the table

def _state():
    state = C.RaceState(position=4, field_size=20, lap=18, laps_total=30,
                        fuel_per_lap_l=5.0)
    state.rivals = {"PUNISHED": _rival("PUNISHED", 12, 50.0),
                    "K.Graebs": _rival("K.Graebs", 11, 30.0, bound=True),
                    "Ghost": _rival("Ghost", 9, 90.0)}
    ahead, behind = GapTrend(side="ahead"), GapTrend(side="behind")
    ahead.note(18, 1.4, subject="PUNISHED")
    behind.note(18, 0.8, subject="K.Graebs")
    state.gap_ahead, state.gap_behind = ahead, behind
    return state


def test_every_known_car_has_a_row_by_place_and_ours_is_marked():
    board = BoardRead(packet=1000, places={"PUNISHED": 3, "K.Graebs": 5,
                                           "Beeni": 4, "X-Man Oce": 6},
                      visible=frozenset({3, 4, 5, 6}), windowed=False)
    view = field_view(_state(), board, packet=1000 + 3 * SAMPLE_HZ)
    names = [(row.place, row.name, row.us) for row in view.rows]
    # Ours from the packet, not the board's own name for our row; a car
    # whose stop was read but whose row never was goes to the bottom.
    assert names == [(3, "PUNISHED", False), (4, None, True),
                     (5, "K.Graebs", False), (6, "X-Man Oce", False),
                     (None, "Ghost", False)]
    assert view.board_age_s == 3.0


def test_only_the_two_neighbours_carry_a_gap():
    board = BoardRead(packet=1, places={"PUNISHED": 3, "K.Graebs": 5,
                                        "X-Man Oce": 6},
                      visible=frozenset({3, 5, 6}), windowed=False)
    rows = {row.name: row for row in field_view(_state(), board, packet=1).rows}
    assert rows["PUNISHED"].gap_s == 1.4 and rows["K.Graebs"].gap_s == 0.8
    assert rows["X-Man Oce"].gap_s is None


def test_a_row_carries_the_stop_the_fuel_and_the_same_prediction_george_uses():
    board = BoardRead(packet=1, places={"PUNISHED": 3, "K.Graebs": 5},
                      visible=frozenset({3, 5}), windowed=False)
    rows = {row.name: row for row in field_view(_state(), board, packet=1).rows}
    punished = rows["PUNISHED"]
    assert (punished.last_stop_lap, punished.fuel_in_l, punished.fuel_out_l) == (
        12, 8.0, 50.0)
    assert punished.prediction.words == STOPS_AGAIN
    assert punished.prediction.total_stops == 2
    graebs = rows["K.Graebs"]
    assert graebs.out_is_bound and graebs.prediction.words == CANNOT_TELL


def test_no_race_says_so():
    assert field_view(None, None, packet=None).why == "no race running"


# ------------------------------------------------------------- the server

def test_the_tablet_is_served_and_tracked_apart_from_the_phone():
    """A tablet reading must not look like a phone reading, or the ultrawide
    gives its gaps to the wrong screen."""
    import json
    import urllib.request

    from pitcrew.ui.strip_server import TABLET, StripServer
    from pitcrew.ui.tablet import compose

    server = StripServer(port=0, host="127.0.0.1")
    assert server.start()
    port = server._httpd.server_address[1]
    try:
        def get(path):
            with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}",
                                        timeout=5) as reply:
                return reply.read()

        assert b"Pit Crew field" in get("/tablet")
        server.publish(compose(None), TABLET)
        assert json.loads(get("/tablet/state"))["idle"] is True
        assert server.live(TABLET) and not server.live()
    finally:
        server.stop()


def test_the_board_hands_its_gaps_over_only_while_the_tablet_reads():
    from pitcrew.controller import PitCrewController

    class Server:
        def __init__(self, tablet):
            self.tablet, self.published = tablet, []

        def live(self, page="strip"):
            return self.tablet if page == "tablet" else True

        def last_client_of(self, page="strip"):
            return "10.0.0.9"

        def publish(self, body, page="strip"):
            self.published.append((page, body))

    ctl = PitCrewController.__new__(PitCrewController)
    ctl.race = None
    assert ctl._publish_tablet(Server(tablet=True)) is True
    server = Server(tablet=False)
    assert ctl._publish_tablet(server) is False
    (page, body), = server.published
    assert page == "tablet" and body["idle"] is True
    # The buttons read the app's state back even with no race to show.
    assert body["controls"]["racing"] is False


# ------------------------------------------------------------- the buttons

def _press_server():
    from pitcrew.ui.strip_server import StripServer

    presses = []
    server = StripServer(port=0, host="127.0.0.1")
    server.press_key = "123456"
    server.on_press = lambda action, value: presses.append((action, value))
    assert server.start()
    return server, server._httpd.server_address[1], presses


def _post(port, body):
    import json
    import urllib.error
    import urllib.request

    data = json.dumps(body).encode("utf-8")
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}/tablet/press", data=data, method="POST",
        headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=5) as reply:
            return reply.status
    except urllib.error.HTTPError as refused:
        return refused.code


def test_a_press_is_acted_on_only_with_the_code_and_a_known_action():
    server, port, presses = _press_server()
    try:
        assert _post(port, {"action": "pit", "value": True, "key": "999999"}) == 403
        assert _post(port, {"action": "launch", "value": True, "key": "123456"}) == 400
        assert _post(port, {"action": "fuel", "value": "max", "key": "123456"}) == 400
        assert presses == []
        assert _post(port, {"action": "fuel", "value": "save", "key": "123456"}) == 202
        assert presses == [("fuel", "save")]
    finally:
        server.stop()


def test_a_server_with_no_code_refuses_every_press():
    server, port, presses = _press_server()
    server.press_key = None
    try:
        assert _post(port, {"action": "george", "value": False, "key": ""}) == 403
        assert presses == []
    finally:
        server.stop()


def _coordinator():
    """A 20-lap race armed on a one-stop plan and past the green - the way
    `test_plan_targets` builds one."""
    from pitcrew.race.coordinator import PlanContext, RaceCoordinator
    from pitcrew.telemetry.session_state import EventKind, SessionEvent

    plan = {"stops": 1, "stints": [
        {"laps": 10, "compound": "RM", "start_lap": 1, "fuel_l": 50.0},
        {"laps": 10, "compound": "RH", "start_lap": 11, "fuel_l": 50.0,
         "tyres": True}]}
    race = RaceCoordinator(plan, fuel_per_lap_l=5.0, fuel_capacity_l=100.0,
                           mandatory_stops=0)
    context = PlanContext(car="Huracan", track="Daytona", layout="Road",
                          race_laps=20)
    assert race.arm(context, context)
    race.handle(SessionEvent(EventKind.RACE_STARTED, {"laps_in_race": 20}))
    assert race.running
    return race


def test_a_held_column_moves_the_beep_and_nothing_moves_it_back():
    """"Holds until I switch it back" - not the fuel, not the plan."""
    race = _coordinator()
    race.state.lap = 4
    race.hold_fuel_column(True)
    assert race.state.fuel_save_engaged is True
    assert race.state.fuel_column_held is True
    assert race.beep_drop_rpm(None) == C.FUEL_MODE_DROP_RPM
    change = race.state.fuel_mode_change
    assert change[1] is True and change[2] == C.FUEL_MODE_DRIVER
    call = C._fuel_mode(race.state)
    assert call.call == "Fuel-save beeps." and "Your call" in call.reason
    # The crossing's fuel decision leaves his column alone.
    race._decide_fuel_mode()
    assert race.state.fuel_save_engaged is True
    race.hold_fuel_column(False)
    assert race.state.fuel_save_engaged is False and race.beep_drop_rpm(None) is None


def test_declaring_the_stop_makes_this_lap_the_in_lap_and_can_be_taken_back():
    race = _coordinator()
    race.state.lap = 5                       # driving lap 6
    assert race.state.laps_to_stop() == 5
    assert race.declare_box_this_lap() is True
    assert race.state.laps_to_stop() == 1    # this lap is the in-lap
    assert race.state.box_declared_lap == 6
    # The stint after it carries the compound the plan had for the next one.
    assert race.state.next_compound == "RH"
    assert race.cancel_declared_box() is True
    assert race.state.laps_to_stop() == 5 and race.state.box_declared_lap is None


def test_a_stop_cannot_be_declared_from_the_box():
    race = _coordinator()
    race.state.in_pit = True
    assert race.declare_box_this_lap() is False


def test_the_controller_routes_each_press_and_confirms_a_stop_out_loud():
    """The confirmation is said with George OFF - his call."""
    from pitcrew.controller import PitCrewController

    class Voice:
        def __init__(self):
            self.said = []

        def say(self, line):
            self.said.append(line)

    ctl = PitCrewController.__new__(PitCrewController)
    ctl.race = _coordinator()
    ctl.race.state.lap = 5
    ctl.race.state.fuel_per_lap_l = 5.0
    ctl.race.state.fuel_capacity_l = 100.0
    ctl.voice = Voice()
    ctl._engineer_speaks = True
    ctl._fuel_mode_on_beep = None
    ctl._follow_fuel_mode = lambda: None
    ctl._on_tablet_press("george", False)
    assert ctl._engineer_speaks is False
    ctl._on_tablet_press("fuel", "save")
    assert ctl.race.state.fuel_column_held is True
    ctl._on_tablet_press("pit", True)
    assert ctl.race.state.laps_to_stop() == 1
    assert ctl.voice.said and ctl.voice.said[-1].startswith("Boxing this lap.")
    ctl._on_tablet_press("pit", False)
    assert ctl.voice.said[-1] == "Stop cancelled. Back on the plan."
    controls = ctl._tablet_controls()
    assert controls == {"george": False, "fuel": "save", "fuel_held": True,
                        "pit": None, "racing": True}


# ------------------------------------------------------------- the words

def test_the_tablet_words_what_each_figure_is_worth():
    """A bound is "≥", an unresolved shortfall ends "?", our burn says so."""
    from pitcrew.ui.tablet import compose

    board = BoardRead(packet=1, places={"PUNISHED": 3, "K.Graebs": 5},
                      visible=frozenset({3, 5}), windowed=False)
    state = _state()
    state.rivals["Close"] = _rival("Close", 10, 98.0)
    got = compose(field_view(state, board, packet=1 + 20 * SAMPLE_HZ))
    rows = {row["name"]: row for row in got["rows"]}
    assert rows["PUNISHED"]["fuel"] == "8 → 50"
    assert (rows["PUNISHED"]["prediction"], rows["PUNISHED"]["detail"]) == (
        "2 STOPS", "in by L22 · our burn")
    assert rows["PUNISHED"]["tone"] == "stops" and rows["PUNISHED"]["gap"] == "1.4"
    assert rows["K.Graebs"]["fuel"] == "8 → ≥30"
    assert rows["K.Graebs"]["prediction"] == "CAN'T TELL"
    assert rows["Close"]["prediction"] == "1 STOP?"
    assert rows["YOU"]["us"] is True and rows["YOU"]["place"] == "P4"
    assert got["board"] == "board read 20 s ago" and got["board_stale"] is True


def test_a_long_field_keeps_the_rows_nearest_him_and_says_how_many_it_left():
    from pitcrew.ui.tablet import MAX_ROWS, compose

    places = {f"Car {n}": n for n in range(1, 21) if n != 10}
    board = BoardRead(packet=1, places=places, visible=frozenset(places.values()),
                      windowed=False)
    state = C.RaceState(position=10, field_size=20, lap=5, laps_total=30)
    got = compose(field_view(state, board, packet=1))
    shown = [row["place"] for row in got["rows"]]
    assert len(shown) == MAX_ROWS and "P10" in shown
    assert shown == sorted(shown, key=lambda p: int(p[1:]))
    assert got["left_off"] == 20 - MAX_ROWS
