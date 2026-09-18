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


def test_a_saveable_shortfall_counts_no_total_and_says_what_george_says():
    """**The screen may not assert what the voice refuses to.**

    `short_to_the_flag` says this same shortfall as "he lifts or he stops
    again" and says in its own docstring that asserting either half is the
    defect it exists to fix - and `SAVEABLE_FRACTION` is a QUARTER of the
    remaining fuel, not "a few per cent". The row used to read "1 STOP /
    short, saves it" off the same numbers: a total for the rest of his race,
    from an assumption about how he would drive it.
    """
    from pitcrew.race.rival_calls import short_to_the_flag

    rival = _rival("B", 10, 85.0)
    got = predict(rival, stops_seen=1, our_burn_l=5.0, laps_total=30)
    assert (got.words, got.total_stops, got.burn_of) == (SHORT_SAVES, None,
                                                         "ours")
    spoken = short_to_the_flag(rival, 5.0, lap=12, laps_total=30)
    assert spoken is not None, "the voice must have something to say here"
    assert "he lifts or he stops again" in spoken.spoken(), spoken.spoken()


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
    """**And it asks George**, which the test of this name never did.

    It asserted the row against constants, so the row and the voice could -
    and did - name two different laps for one car: the tablet added
    `laps_missed()` to a stop lap the pit wall had already drop-corrected,
    and `must_stop_by` spoke a completed-lap count where the HUD numbers the
    lap in progress. Three domains, one car. Rule 13 is about the words; this
    is the same failure in figures, and only a test that runs both catches it.
    """
    from pitcrew.race.rival_calls import must_stop_by

    board = BoardRead(packet=1, places={"PUNISHED": 3, "K.Graebs": 5},
                      visible=frozenset({3, 5}), windowed=False)
    state = _state()
    rows = {row.name: row for row in field_view(state, board, packet=1).rows}
    punished = rows["PUNISHED"]
    # Filed against our completed count; his HUD read one more than that.
    assert (punished.last_stop_lap, punished.fuel_in_l, punished.fuel_out_l) == (
        13, 8.0, 50.0)
    assert punished.prediction.words == STOPS_AGAIN
    assert punished.prediction.total_stops == 2

    spoken = must_stop_by(state.rivals["PUNISHED"], state.fuel_per_lap_l,
                          lap=state.lap, laps_total=state.laps_total)
    assert spoken is not None
    assert f"lap {punished.prediction.reaches_lap}," in spoken.spoken(), (
        spoken.spoken(), punished.prediction.reaches_lap)

    graebs = rows["K.Graebs"]
    assert graebs.out_is_bound and graebs.prediction.words == CANNOT_TELL


def test_a_missed_crossing_does_not_move_a_rivals_stop_lap():
    """Our own drift is ours. `lap_on_screen` corrects OUR number; a rival's
    stop lap is already in the drop-corrected domain, so applying our offset
    to it moved his stop a lap per lap we lost."""
    board = BoardRead(packet=1, places={"PUNISHED": 3}, visible=frozenset({3}),
                      windowed=False)
    clean = _state()
    drifted = _state()
    drifted.screen_lap = drifted.lap + 3        # GT7 two ahead of our count

    def punished(state):
        rows = {r.name: r for r in field_view(state, board, packet=1).rows}
        return rows["PUNISHED"]

    assert punished(clean).last_stop_lap == punished(drifted).last_stop_lap
    assert (punished(clean).prediction.reaches_lap
            == punished(drifted).prediction.reaches_lap)
    # ...while OUR header still follows the HUD.
    assert field_view(drifted, board, packet=1).lap == drifted.lap + 3


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


def test_between_sessions_both_pages_are_told_there_is_no_session():
    """The board timer stops between sessions, so this is the last thing
    either page hears. Told only the phone, the tablet's numbers simply
    stopped - and a page whose numbers stop says the PC has died."""
    from pitcrew.controller import PitCrewController
    from pitcrew.ui.strip import StripComposer

    class Server:
        def __init__(self):
            self.published = []

        def publish(self, body, page="strip"):
            self.published.append((page, body))

    ctl = PitCrewController.__new__(PitCrewController)
    ctl.race = None
    ctl.strip = Server()
    ctl._strip_composer = StripComposer()
    ctl._strip_idle()
    pages = {page: body for page, body in ctl.strip.published}
    assert pages["strip"]["idle"] is True
    assert pages["tablet"]["idle"] is True
    # The buttons still read the app back with no session running: George
    # on/off is meant to work there.
    assert pages["tablet"]["controls"]["racing"] is False


def test_the_cover_hides_the_numbers_and_never_the_buttons():
    """Over the whole screen it swallowed every press - including George
    on/off, which is for exactly the moments the cover is up."""
    from pitcrew.ui.strip_server import PAGE

    page = PAGE.with_name("tablet.html").read_text(encoding="utf-8")
    assert "#cover { position: fixed; inset: 0 19vw 0 0;" in page
    assert "#buttons { position: relative; z-index: 6;" in page
    # And installed on the tablet it opens the tablet's page, not the phone's.
    assert 'href="/tablet.webmanifest"' in page
    assert 'rel="apple-touch-icon"' in page


def test_a_tablet_that_is_being_sent_nothing_does_not_take_the_gaps():
    """`live` means a page polled, not that it is showing anything. Returning
    it after a failed build surrendered the ultrawide's gaps to a page reading
    NO DATA - and turned that screen to history at the same time."""
    from pitcrew.controller import PitCrewController

    class Server:
        def __init__(self):
            self.published = []

        def live(self, page="strip"):
            return True

        def last_client_of(self, page="strip"):
            return "10.0.0.9"

        def publish(self, body, page="strip"):
            self.published.append((page, body))

    class Broken:
        running = True
        state = C.RaceState()

        def field_view(self):
            raise ValueError("a data race on the board read")

    ctl = PitCrewController.__new__(PitCrewController)
    ctl.race = Broken()
    server = Server()
    assert ctl._publish_tablet(server) is False
    assert server.published == []


def test_the_press_route_refuses_a_body_that_is_not_a_press_and_cools_off():
    from pitcrew.ui.strip_server import PRESS_WRONG_LIMIT

    server, port, presses = _press_server()
    try:
        import urllib.error
        import urllib.request

        def post(body, kind="application/json"):
            request = urllib.request.Request(
                f"http://127.0.0.1:{port}/tablet/press",
                data=body.encode("utf-8"), method="POST",
                headers={"Content-Type": kind})
            try:
                with urllib.request.urlopen(request, timeout=5) as reply:
                    return reply.status
            except urllib.error.HTTPError as refused:
                return refused.code

        # A form post is a CORS simple request: any page on his network could
        # send one without a preflight. A press says it is JSON.
        assert post('{"action": "george", "value": false, "key": "123456"}',
                    kind="text/plain") == 415
        for _ in range(PRESS_WRONG_LIMIT):
            assert post('{"action": "george", "value": false, "key": "000000"}') == 403
        # Hammering a six-digit code is answered with a cool-off, not a log flood.
        assert post('{"action": "george", "value": false, "key": "123456"}') == 429
        assert presses == []
    finally:
        server.stop()


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
    # The press moves the beep itself now, whatever the column was before.
    beeps = []
    ctl.bridge = type("Bridge", (), {"set_short_shift": lambda _self, drop:
                                     beeps.append(drop)})()
    ctl._on_tablet_press("george", False)
    assert ctl._engineer_speaks is False
    ctl._on_tablet_press("fuel", "save")
    assert ctl.race.state.fuel_column_held is True
    # **The beep is set on every press**, not only when the column moved: a
    # one-off "Short-shift 450." had left it where his press says it is not.
    assert beeps == [C.FUEL_MODE_DROP_RPM]
    ctl._on_tablet_press("pit", True)
    assert ctl.race.state.laps_to_stop() == 1
    assert ctl.voice.said and ctl.voice.said[-1].startswith("Boxing this lap.")
    ctl._on_tablet_press("pit", False)
    assert ctl.voice.said[-1] == "Stop cancelled. Back on the plan."
    controls = ctl._tablet_controls()
    assert controls == {"george": False, "fuel": "save", "fuel_held": True,
                        "pit": None, "pit_cancellable": False, "racing": True}
    # A hold past the lap it was declared for has nothing to take back, and
    # the button says so rather than answering with silence.
    ctl._on_tablet_press("pit", False)
    assert ctl.voice.said[-1].startswith("Too late")


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
        "2 STOPS", "in by L23 · our burn")
    assert rows["PUNISHED"]["tone"] == "stops" and rows["PUNISHED"]["gap"] == "1.4"
    assert rows["K.Graebs"]["fuel"] == "8 → ≥30"
    assert rows["K.Graebs"]["prediction"] == "CAN'T TELL"
    assert rows["Close"]["prediction"] == "1 STOP SO FAR"
    assert "lifts or stops again" in rows["Close"]["detail"]
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


def test_a_refused_board_read_takes_its_places_with_it():
    """The guard refused the AGE and kept the DATA.

    So the page said "board not read yet" in one corner and drew a full
    timing tower in the middle - of the previous race, whose order the wall
    had carried across the arm. The comment on the guard names that exact
    hazard; only half of it was implemented.
    """
    from pitcrew.ui.tablet import compose

    state = _state()
    board = BoardRead(packet=5_000, places={"PUNISHED": 3, "K.Graebs": 5},
                      visible=frozenset({3, 5}), windowed=False)
    # The packet counter reset at the arm: the read is stamped in the future.
    view = field_view(state, board, packet=10)
    assert view.board_age_s is None
    assert not [row for row in view.rows if not row.us and row.place is not None]
    got = compose(view)
    assert not [row for row in got["rows"] if not row["us"] and row["place"]]


def test_a_place_nobody_read_this_time_is_not_drawn_as_one():
    """`rival_positions` is `update()`d once a lap and never pruned, so a name
    read at P5 twenty laps ago kept that row for the rest of the race - beside
    a live one, under one caption saying how old the BOARD was. Two cars at
    P5, and a retired car still holding P7."""
    state = _state()
    state.rival_positions.update({"Ghost": 5, "Faded": 7})
    board = BoardRead(packet=1, places={"PUNISHED": 3, "Beeni": 4},
                      visible=frozenset({3, 4}), windowed=False)
    rows = {row.name: row for row in field_view(state, board, packet=1).rows}
    assert rows["PUNISHED"].place == 3
    # Ghost and Faded keep their rows - the stop and fuel on them are facts -
    # but neither claims a place the board did not just read.
    for name in ("Ghost", "Faded"):
        if name in rows:
            assert rows[name].place is None, name
    places = [row.place for row in rows.values() if row.place is not None]
    assert len(places) == len(set(places)), f"two rows at one place: {places}"


def test_the_entry_figure_is_marked_where_the_wall_joined_the_fill():
    """`boxed_call` refuses to SAY the litres in that case; the screen drew
    them as read. A car that dropped in on 4 L and took 76 read "42 -> 80"."""
    from pitcrew.race.rival_calls import Rival
    from pitcrew.race.rivals import Stop
    from pitcrew.ui.tablet import _fuel

    partial = Rival(name="P", stop=Stop(lap=9, fuel_in_l=42.0, fuel_out_l=80.0),
                    pitted=True, entry_is_a_bound=True)
    state = _state()
    state.rivals["P"] = partial
    board = BoardRead(packet=1, places={"P": 6, "Beeni": 4},
                      visible=frozenset({4, 6}), windowed=False)
    row = {r.name: r for r in field_view(state, board, packet=1).rows}["P"]
    assert row.in_is_bound is True
    assert _fuel(row) == "≤42 → 80"


def test_the_tablet_and_george_call_a_board_stale_at_the_same_second():
    """One name, one value. `field` declared its own `BOARD_FRESH_S` at 6.0
    against the 12.0 George refuses a board at, so between the two the screen
    said stale while the voice still built a picture from it."""
    from pitcrew.race import field as field_module
    from pitcrew.race import news as news_module

    assert field_module.BOARD_FRESH_S is news_module.BOARD_FRESH_S


def test_a_gap_goes_to_the_car_it_was_read_against_not_to_a_place():
    """`GapTrend` carries its `subject` because it is on file reporting
    confident numbers about a car that was no longer there. This reader threw
    it away and pinned the figure to whoever the board last put at `ours ± 1`,
    so a pass into the last corner gave the passed car's row the gap to the
    car now being chased."""
    state = _state()
    # The board still has the old order; the trends know who they watched.
    state.gap_ahead.subject = "K.Graebs"
    state.gap_behind.subject = "PUNISHED"
    board = BoardRead(packet=1, places={"PUNISHED": 3, "K.Graebs": 5},
                      visible=frozenset({3, 5}), windowed=False)
    rows = {row.name: row for row in field_view(state, board, packet=1).rows}
    assert rows["K.Graebs"].gap_s == 1.4      # the ahead trend's own subject
    assert rows["PUNISHED"].gap_s == 0.8      # the behind trend's
    assert rows["PUNISHED"].place == 3        # the board's place is untouched


def test_a_gap_with_no_subject_is_not_drawn_against_anyone():
    state = _state()
    state.gap_ahead.subject = None
    state.gap_behind.subject = None
    state.gap_ahead_name = state.gap_behind_name = None
    board = BoardRead(packet=1, places={"PUNISHED": 3, "K.Graebs": 5},
                      visible=frozenset({3, 5}), windowed=False)
    rows = field_view(state, board, packet=1).rows
    assert all(row.gap_s is None for row in rows)


def test_a_gap_from_laps_ago_is_not_still_on_the_screen():
    """`latest()` is keyed by lap and never expires, so a reader that stopped
    left a bare "1.4" up for the rest of the race. `news` bounds a spoken gap
    at `GAP_FRESH_S`; the screen bounded nothing."""
    state = _state()
    state.gap_ahead.subject = "PUNISHED"
    board = BoardRead(packet=1, places={"PUNISHED": 3}, visible=frozenset({3}),
                      windowed=False)
    fresh = {r.name: r for r in field_view(state, board, packet=1).rows}
    assert fresh["PUNISHED"].gap_s == 1.4
    state.lap += 5                              # five laps with no new read
    stale = {r.name: r for r in field_view(state, board, packet=1).rows}
    assert stale["PUNISHED"].gap_s is None


def test_a_visit_the_wall_never_closed_stops_saying_he_is_standing_there():
    """"IN LANE" is the one thing on this screen happening right now, and it
    could not expire: only `note_rival_stop` clears a visit and it returns
    early when the race is not running, so a plate could stay up for the rest
    of the race. `untold()` has `STALE_AFTER_LAPS`; the plate had nothing."""
    from pitcrew.race.lane import STALE_AFTER_LAPS

    state = _state()
    board = BoardRead(packet=1, places={"PUNISHED": 3}, visible=frozenset({3}),
                      windowed=False)
    from types import SimpleNamespace

    state.lane.enter(SimpleNamespace(driver="PUNISHED", lap=state.lap),
                     lap=state.lap)
    assert state.lane.in_the_lane(), "the fixture must put him in the lane"

    def punished(at_lap):
        state.lap = at_lap
        rows = {r.name: r for r in field_view(state, board, packet=1).rows}
        return rows["PUNISHED"].in_lane

    began = state.lap
    assert punished(began) is True
    assert punished(began + STALE_AFTER_LAPS) is True
    assert punished(began + STALE_AFTER_LAPS + 1) is False


def test_a_timed_races_distance_is_hedged_where_it_is_an_estimate():
    """Every spoken call says "about" for a timed race's lap count. The header
    said "/ 30" flat - and it is the number every prediction on the screen is
    divided by (`fuel_shortfall`), so the screen was the confident one."""
    from pitcrew.ui.tablet import compose

    board = BoardRead(packet=1, places={"PUNISHED": 3}, visible=frozenset({3}),
                      windowed=False)
    firm = _state()
    assert "/ 30" in compose(field_view(firm, board, packet=1))["lap"]

    timed = _state()
    timed.laps_count_hedged = True
    assert "/ ~30" in compose(field_view(timed, board, packet=1))["lap"]


def test_his_burn_says_how_many_stops_it_rests_on():
    """Rule 4. Only OUR burn was marked, so "his burn" was the unmarked
    default - the reassuring case, on the weakest evidence, with nothing
    saying whether it stood on one stop or six."""
    from pitcrew.race.rival_calls import Rival
    from pitcrew.race.rivals import Stop
    from pitcrew.ui.tablet import prediction_words

    def words(stops):
        rival = Rival(name="R", stop=Stop(lap=10, fuel_in_l=8.0,
                                          fuel_out_l=95.0),
                      pitted=True, burn_per_lap_l=5.0, burn_stops=stops)
        return prediction_words(predict(rival, stops_seen=1, our_burn_l=5.0,
                                        laps_total=30))[1]

    assert "his burn, 1 stop" in words(1)
    assert "his burn, 4 stops" in words(4)
    # Ours carries no count: it is this race's, over every lap of it, and a
    # count there would invite comparing two different kinds of number.
    ours = Rival(name="R", stop=Stop(lap=10, fuel_in_l=8.0, fuel_out_l=95.0),
                 pitted=True)
    assert prediction_words(
        predict(ours, stops_seen=1, our_burn_l=5.0,
                laps_total=30))[1].endswith("our burn")


def test_a_refusal_reaches_the_tablet_with_its_reason():
    """**A refusal that never reads the body is a refusal he never sees.**

    The cool-off and the content-type check both answered before reading the
    request, so the connection was reset with the reply in flight and the
    page got a transport error where the server had sent "too many wrong
    codes". The tablet then says the PC is unreachable - which is the one
    thing that had NOT happened - and he presses the button again, which is
    what the cool-off exists to stop.
    """
    import json
    import urllib.error
    import urllib.request

    from pitcrew.ui.strip_server import PRESS_WRONG_LIMIT

    server, port, presses = _press_server()
    try:
        def post(body, kind="application/json"):
            request = urllib.request.Request(
                f"http://127.0.0.1:{port}/tablet/press",
                data=body.encode("utf-8"), method="POST",
                headers={"Content-Type": kind})
            try:
                with urllib.request.urlopen(request, timeout=5) as reply:
                    return reply.status, json.loads(reply.read() or b"{}")
            except urllib.error.HTTPError as refused:
                return refused.code, json.loads(refused.read() or b"{}")

        wrong = '{"action": "george", "value": false, "key": "000000"}'
        right = '{"action": "george", "value": false, "key": "123456"}'

        # The body is read even where the content type is refused outright.
        status, why = post(right, kind="text/plain")
        assert (status, why.get("why")) == (415, "not a press")

        for _ in range(PRESS_WRONG_LIMIT):
            assert post(wrong)[0] == 403
        # ...and the cool-off says so, in words, rather than dropping the
        # connection on a body it never drained.
        status, why = post(right)
        assert (status, why.get("why")) == (429, "too many wrong codes")
        assert presses == []
    finally:
        server.stop()


def test_the_field_is_readable_without_the_buttons_code():
    """**The code authorises a PRESS, never a READ.**

    The page demanded it on load, so a new tablet - or any browser whose site
    data had been cleared - put a keypad over the timing tower and every
    figure behind it. Nothing on this page needs a code to be looked at: it
    is the same read-only payload the phone gets. Measured 18 Sep 2026: all
    four tablet scenes rendered as the pairing prompt and nothing else.
    """
    from pathlib import Path

    source = (Path(__file__).resolve().parents[1] / "ui"
              / "tablet.html").read_text(encoding="utf-8")

    # Nothing opens the prompt on load; `poll()` starts regardless.
    assert "if (!key()) pair(true);" not in source, (
        "the page is gating the race behind the buttons code again")
    # It is opened from a press, which is the moment it is needed...
    assert 'if (!key()) { pair(true); return; }' in source
    # ...and from a refusal, which is the moment it is wrong.
    assert 'pair(true, "that code was refused")' in source
    # ...and it can be left, or it is a gate by another name.
    assert 'id="pair-shut"' in source
    assert '$("pair").addEventListener' in source


def test_an_unpaired_button_says_so_rather_than_looking_live():
    """A control that draws the app's state and answers a press with a keypad
    is one he presses twice at the worst moment."""
    from pathlib import Path

    source = (Path(__file__).resolve().parents[1] / "ui"
              / "tablet.html").read_text(encoding="utf-8")
    assert 'var locked = !key();' in source
    assert '"tap for the code"' in source
    assert "#buttons.locked" in source


def test_the_screen_and_the_voice_answer_the_stop_question_the_same_way():
    """**Two mechanisms were answering "will he stop again".**

    The tablet worked it out per car from the fuel; `news.picture` assumed
    every rival stops exactly as many times as the regulations require. So
    the screen could read "PUNISHED 2 STOPS" while the voice, from the same
    `RaceState`, placed him on the assumption he stopped once - two answers
    to one question, one spoken and one a foot to the left (rule 13).
    `must_stop_again` is the one expression now, and both read it.
    """
    from pitcrew.race.field import CANNOT_TELL, REACHES_FLAG, STOPS_AGAIN
    from pitcrew.race.rival_calls import Rival, must_stop_again
    from pitcrew.race.rivals import Stop

    def car(out, bound=False, lap=10):
        return Rival(name="R", stop=Stop(lap=lap, fuel_in_l=8.0,
                                         fuel_out_l=out),
                     pitted=True, exit_is_a_bound=bound)

    cases = [
        (car(50.0), STOPS_AGAIN, True),      # well short: he must come in
        (car(60.0, lap=25), REACHES_FLAG, False),   # the tank covers it
        (car(30.0, bound=True), CANNOT_TELL, None),  # a bound is not a figure
    ]
    for rival, expected_words, expected_verdict in cases:
        got = predict(rival, stops_seen=1, our_burn_l=5.0, laps_total=30)
        assert got.words == expected_words, (got.words, expected_words)
        assert must_stop_again(rival, 5.0, laps_total=30) is expected_verdict


def test_a_forced_stop_raises_the_regulation_count_and_never_lowers_it():
    """A mandatory stop he has not taken is owed whatever his tank says, and
    a `None` - a bound exit figure, a shortfall he can lift for - is not a
    "no". The fuel can only ADD."""
    from pitcrew.race.rival_calls import Rival, must_stop_again
    from pitcrew.race.rivals import Stop

    covers = Rival(name="R", stop=Stop(lap=25, fuel_in_l=8.0, fuel_out_l=60.0),
                   pitted=True)
    assert must_stop_again(covers, 5.0, laps_total=30) is False

    def owed(by_rule, forced):
        return max(by_rule, 1) if forced else by_rule

    # He owes the regulations one; his tank covering the flag does not excuse
    # it, because a mandatory stop is not a fuel question.
    assert owed(1, must_stop_again(covers, 5.0, laps_total=30)) == 1
    # He owes none by the rules, but the fuel forces one.
    short = Rival(name="S", stop=Stop(lap=10, fuel_in_l=8.0, fuel_out_l=50.0),
                  pitted=True)
    assert owed(0, must_stop_again(short, 5.0, laps_total=30)) == 1
    # Cannot tell is not a yes.
    bound = Rival(name="B", stop=Stop(lap=10, fuel_in_l=8.0, fuel_out_l=30.0),
                  pitted=True, exit_is_a_bound=True)
    assert owed(0, must_stop_again(bound, 5.0, laps_total=30)) == 0


def test_a_place_only_moves_on_evidence_it_could_be_marked_with():
    """**The voice has nowhere to put a "?".**

    The tablet draws this verdict with "?" and "our burn" beside it, so an
    unconfirmed one is honestly shown. `news.picture` folds it into a spoken
    PLACE, where those words cannot go - so it asks for `firm`: outside the
    reading error, and on HIS burn rather than ours standing in for it.
    """
    from pitcrew.race.rival_calls import Rival, must_stop_again
    from pitcrew.race.rivals import Stop

    # A 2 L shortfall inside a +/-4 L reading error, on our burn.
    thin = Rival(name="R", stop=Stop(lap=10, fuel_in_l=8.0, fuel_out_l=3.0),
                 pitted=True)
    assert must_stop_again(thin, 1.0, laps_total=15) is True
    assert must_stop_again(thin, 1.0, laps_total=15, firm=True) is None

    # His own burn, well outside the error: firm enough to move a place.
    his = Rival(name="H", stop=Stop(lap=10, fuel_in_l=8.0, fuel_out_l=20.0),
                pitted=True, burn_per_lap_l=7.0)
    assert must_stop_again(his, 7.0, laps_total=30, firm=True) is True


def test_the_spoken_hedge_describes_the_sum_that_was_done():
    """Rule 12. "If they stop once." is the REGULATION assumption said out
    loud, and it stayed word for word after the count began taking a car's
    own fuel into account - so he heard "Effectively P1. If they stop once."
    about a place computed with a rival stopping twice. The error only runs
    one way: a car forced to stop again drops behind us, so the wrong hedge
    always flatters."""
    from pitcrew.race.news import picture_words

    _, on_rules = picture_words(6, ("effective", 2), 1, on_fuel=False)
    assert "If they stop once." in on_rules

    _, on_fuel = picture_words(6, ("effective", 1), 1, on_fuel=True)
    assert "If they stop once." not in on_fuel
    assert "their own fuel" in on_fuel
