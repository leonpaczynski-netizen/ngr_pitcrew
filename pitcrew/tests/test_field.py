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
    # **A subject is a roster CLUSTER ID, and nothing else.**
    # `pit_wall._neighbour` returns whatever `Roster.see_frame` resolved the
    # adjacent row to - an int or None, never a string. This fixture used to
    # seed a NAME here, a shape production cannot produce, which is why the
    # suite was green through a whole race in which the tablet drew no gap
    # at all: the row names were compared against `str(cluster_id)`. The
    # roster's translation of that same id travels beside the trend, as
    # `gap_{side}_name`, and that is what the rows are keyed by.
    ahead.note(18, 1.4, subject=277)
    behind.note(18, 0.8, subject=533)
    state.gap_ahead, state.gap_behind = ahead, behind
    state.gap_ahead_name, state.gap_behind_name = "PUNISHED", "K.Graebs"
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
    # Built by hand, so the plain attributes the tablet reads are set by
    # hand too: `session_kind` is what says which session is OPEN, and
    # `_open_session_kind` reads it directly on purpose - a default there
    # would hide one that went missing.
    ctl.session_kind = None
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
    # Built by hand, so the plain attributes the tablet reads are set by
    # hand too: `session_kind` is what says which session is OPEN, and
    # `_open_session_kind` reads it directly on purpose - a default there
    # would hide one that went missing.
    ctl.session_kind = None
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
    # Built by hand, so the plain attributes the tablet reads are set by
    # hand too: `session_kind` is what says which session is OPEN, and
    # `_open_session_kind` reads it directly on purpose - a default there
    # would hide one that went missing.
    ctl.session_kind = None
    ctl.race = Broken()
    server = Server()
    assert ctl._publish_tablet(server) is False
    assert server.published == []


def test_the_press_route_refuses_a_body_that_is_not_a_press():
    """**The content type is the guard, and it is the one that was working.**

    The six-digit code went on 21 Sep 2026 (his call: a page on his own
    Wi-Fi). This is what is left, and it is what actually stopped a stray
    page: a JSON body is not a CORS simple request, so a browser has to
    preflight it, and this route answers a preflight with 404. A form post -
    which needs no preflight at all - is refused outright.
    """
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

        assert post('{"action": "george", "value": false}',
                    kind="text/plain") == 415
        assert post("not json at all") == 400
        assert post("[1, 2, 3]") == 400
        assert presses == []
    finally:
        server.stop()


# ------------------------------------------------------------- the buttons

def _press_server():
    from pitcrew.ui.strip_server import StripServer

    presses = []
    server = StripServer(port=0, host="127.0.0.1")
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


def test_a_press_is_acted_on_only_for_a_known_action_and_value():
    server, port, presses = _press_server()
    try:
        assert _post(port, {"action": "launch", "value": True}) == 400
        assert _post(port, {"action": "fuel", "value": "max"}) == 400
        # The sessions are a closed list too: "qualifying" is the store's word
        # for the intent and "quali" is the tablet's, and only one of them is
        # a press.
        assert _post(port, {"action": "session", "value": "qualifying"}) == 400
        assert presses == []
        assert _post(port, {"action": "fuel", "value": "save"}) == 202
        assert _post(port, {"action": "session", "value": "practice"}) == 202
        assert _post(port, {"action": "session", "value": "stop"}) == 202
        assert presses == [("fuel", "save"), ("session", "practice"),
                           ("session", "stop")]
    finally:
        server.stop()


def test_a_press_the_app_is_not_listening_for_is_refused_not_swallowed():
    """503, never a silent 202: a page left open after the app closed must
    hear that the press went nowhere."""
    server, port, _ = _press_server()
    server.on_press = None
    try:
        assert _post(port, {"action": "george", "value": False}) == 503
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


# --------------------------------------- starting a session from the tablet


class _Practice:
    """The Practice screen, as much of it as a tablet press touches."""

    def __init__(self, intent="race", status=""):
        self.intent, self.status, self.recording = intent, status, None

    def practice_intent(self):
        return self.intent

    def set_practice_intent(self, intent):
        self.intent = intent

    def status_text(self):
        return self.status


def _tablet_ctl(**kw):
    """A controller with only what a session press reads.

    Built by hand for the reason `_publish_tablet`'s tests are: the real
    `__init__` wants a store, a bridge, Qt and a UDP socket, and none of that
    is what is under test here.
    """
    from pitcrew.controller import PitCrewController

    ctl = PitCrewController.__new__(PitCrewController)
    ctl.race = None
    ctl.session_kind = None
    ctl.session_id = None
    ctl.race_screen = None
    ctl.practice = _Practice()
    for name, value in kw.items():
        setattr(ctl, name, value)
    return ctl


def test_the_tablet_opens_each_of_the_three_sessions():
    """His ask, 21 Sep 2026: practice, qualifying and the race, from the seat.

    **The intent is set either way**, because a press is an instruction: the
    picker is on the PC and holds whatever the last session was, so pressing
    Practice with it left on Qualifying would arm the coach for a run he did
    not ask for.
    """
    from pitcrew.analysis.runs import FOR_QUALIFYING, FOR_RACE

    toggled = []
    ctl = _tablet_ctl(practice=_Practice(intent=FOR_QUALIFYING))
    ctl._on_recording_toggled = lambda wanted: (
        toggled.append(wanted), setattr(ctl, "session_id", 7))

    ctl._on_tablet_press("session", "practice")
    assert toggled == [True]
    assert ctl.practice.intent == FOR_RACE
    # Nothing to say: it started.
    assert ctl.__dict__.get("_tablet_note") is None

    ctl = _tablet_ctl()
    ctl._on_recording_toggled = lambda wanted: setattr(ctl, "session_id", 8)
    ctl._on_tablet_press("session", "quali")
    assert ctl.practice.intent == FOR_QUALIFYING

    armed = []
    ctl = _tablet_ctl()
    ctl.start_race = lambda: (armed.append(True), True)[1]
    ctl._on_tablet_press("session", "race")
    assert armed == [True]


def test_the_tablet_will_not_open_a_second_session_over_the_first():
    """And it names the one that is open. Starting one session over another
    is the failure `start_practice`'s own guard exists for - two UDP binds,
    the first socket keeping the datagrams on Windows, the second session
    deaf - and from the tablet it is a mis-press rather than a condition.
    """
    ctl = _tablet_ctl(session_kind="practice")
    started = []
    ctl._on_recording_toggled = lambda wanted: started.append(wanted)
    ctl._on_tablet_press("session", "race")
    assert started == []
    assert ctl._tablet_controls()["note"] == "Practice is already running."

    # **An armed race counts as open before the green.** `racing` is False on
    # the grid; a Start read off that would offer to arm it twice.
    ctl = _tablet_ctl(race=object())
    assert ctl._open_session_kind() == "race"


def test_a_refused_start_puts_the_screens_own_reason_on_the_tablet():
    """Rule 13: one refusal, one wording. `start_race` already writes every
    one of its half-dozen refusals into its status line, and the tablet reads
    that back rather than carrying a second copy that can drift from it.
    """
    class Screen:
        def status_text(self):
            return "Free Run is active. Stop it before arming the race."

    ctl = _tablet_ctl(race_screen=Screen())
    ctl.start_race = lambda: False
    ctl._on_tablet_press("session", "race")
    assert ctl._tablet_controls()["note"] == (
        "Free Run is active. Stop it before arming the race.")

    # A refusal with nothing to say still says something.
    ctl = _tablet_ctl()
    ctl.start_race = lambda: False
    ctl._on_tablet_press("session", "race")
    assert "the log has the reason" in ctl._tablet_controls()["note"]


def test_the_tablets_answer_retires_and_a_repeat_reads_as_a_second_press():
    """Two guards, and both are needed.

    Nothing publishes between sessions - the board timer is stopped - so
    without an age the last refusal sits on the page until the next session
    opens (rule 11). And without a count the page cannot tell a second
    identical refusal from the sentence already on screen, so it would answer
    the second press with silence.
    """
    from pitcrew import controller as C

    ctl = _tablet_ctl()
    ctl.start_race = lambda: False
    ctl._on_tablet_press("session", "race")
    first = ctl._tablet_controls()
    ctl._on_tablet_press("session", "race")
    second = ctl._tablet_controls()
    assert first["note"] == second["note"]
    assert second["note_n"] == first["note_n"] + 1

    words, at, said = ctl._tablet_note
    ctl._tablet_note = (words, at - C.TABLET_NOTE_S - 1, said)
    assert ctl._tablet_controls()["note"] is None


def test_the_tablet_stops_whichever_session_is_open():
    stopped = []
    ctl = _tablet_ctl(session_kind="practice")
    ctl._on_recording_toggled = lambda wanted: stopped.append(wanted)
    ctl._on_tablet_press("session", "stop")
    assert stopped == [False]
    assert ctl._tablet_controls()["note"] == "Practice stopped."

    ctl = _tablet_ctl(session_kind="race", race=object())
    ctl.stop_race = lambda: stopped.append("race")
    ctl._on_tablet_press("session", "stop")
    assert stopped[-1] == "race"

    ctl = _tablet_ctl()
    ctl._on_tablet_press("session", "stop")
    assert ctl._tablet_controls()["note"] == "Nothing is running."


def test_the_gauge_dialog_never_opens_behind_a_tablet_press():
    """It is the app's one modal and it opens on the PC.

    From the seat he can neither see it nor answer it, and the app would sit
    on `exec()` with the page showing nothing at all - so the press takes the
    answer the dialog itself defaults to, which is not to go out. The refusal
    then reaches him on the tablet's own face.
    """
    from types import SimpleNamespace

    ctl = _tablet_ctl()
    ctl._pressing_from_tablet = True
    check = SimpleNamespace(source="OBS", reason="it did not answer",
                            headline="", recovery="", caveat="")
    assert ctl.confirm_without_gauge("this race", check) is False


def test_george_pressed_on_the_tablet_moves_the_picker_on_the_race_screen():
    """Found 21 Sep 2026, and it had never worked.

    The sync read `self.__dict__["race_screen"]`, and that name is never in
    the instance dict - `race_screen` is a lazy property backed by
    `_race_screen`. So it was None every time, and the Race screen went on
    showing "Engineer speaks" with George switched off from the seat: one
    setting, two readings, and the one on the screen was the wrong one.
    """
    class Picker:
        def __init__(self):
            self.data, self.index = {True: 0, False: 1}, None

        def findData(self, value):                       # noqa: N802 - Qt
            return self.data[value]

        def setCurrentIndex(self, index):                # noqa: N802 - Qt
            self.index = index

    class Screen:
        def __init__(self):
            self.engineer_picker = Picker()

    ctl = _tablet_ctl()
    ctl.race_screen = Screen()
    ctl._on_tablet_press("george", False)
    assert ctl._engineer_speaks is False
    assert ctl.__dict__["_race_screen"].engineer_picker.index == 1


def test_the_controller_routes_each_press_and_confirms_a_stop_out_loud():
    """The confirmation is said with George OFF - his call."""
    from pitcrew.controller import PitCrewController

    class Voice:
        def __init__(self):
            self.said = []

        def say(self, line):
            self.said.append(line)

    ctl = PitCrewController.__new__(PitCrewController)
    # Built by hand, so the plain attributes the tablet reads are set by
    # hand too: `session_kind` is what says which session is OPEN, and
    # `_open_session_kind` reads it directly on purpose - a default there
    # would hide one that went missing.
    ctl.session_kind = None
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
                        "pit": None, "pit_cancellable": False, "racing": True,
                        # A race under way is a race open: `racing` is the
                        # green flag, `session` is what is running at all.
                        "session": "race", "note": None, "note_n": 0}
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
    # **And the gap is withdrawn at twenty seconds, which is the point of
    # reading this row at a board age of twenty.** The stop, the fuel and the
    # prediction are facts about a stop that happened and do not go stale;
    # the gap is a reading off an instrument that has gone quiet. Fresh, the
    # same row draws the figure - below.
    assert rows["PUNISHED"]["tone"] == "stops"
    assert rows["PUNISHED"]["gap"] == "--"
    assert rows["PUNISHED"]["gap_unread"] is True
    fresh = {row["name"]: row
             for row in compose(field_view(state, board, packet=1))["rows"]}
    assert fresh["PUNISHED"]["gap"] == "1.4"
    assert fresh["PUNISHED"]["gap_unread"] is False
    assert rows["K.Graebs"]["fuel"] == "8 → ≥30"
    assert rows["K.Graebs"]["prediction"] == "CAN'T TELL"
    assert rows["Close"]["prediction"] == "1 STOP SO FAR"
    assert rows["Close"]["detail"].startswith("lifts or stops")
    assert rows["YOU"]["us"] is True and rows["YOU"]["place"] == "P4"
    assert got["board"] == "board read 20 s ago" and got["board_stale"] is True


def test_a_minted_handle_is_not_drawn_as_a_drivers_name():
    """**He asked where "Car #164" came from, and it is nowhere on his
    screen.**

    `Store.provisional_driver_name` mints it off a global counter - not the
    car's race number, not anything GT7 shows - and the tablet printed it in
    the same ink, case and column as `PUNISHED`. 25 of 27 rows on the 20 Sep
    race. `news.a_person` is the gate every other channel already uses, and
    `news` states the doctrine: a handle "is said as *the car ahead* ... it
    is not a person."

    A bare cluster id is the same claim by a different spelling, so it is
    worded the same way (rule 13) - and the ROW survives both, because his
    place and his stop are facts about him whatever the app can call him.
    """
    from pitcrew.ui.tablet import UNNAMED, compose

    state = _state()
    state.rivals["Car #164"] = _rival("Car #164", 10, 90.0)
    state.rivals["277"] = _rival("277", 12, 40.0)
    board = BoardRead(packet=1,
                      places={"PUNISHED": 3, "Car #164": 5, "277": 6},
                      visible=frozenset({3, 5, 6}), windowed=False)
    got = compose(field_view(state, board, packet=1))
    by_place = {row["place"]: row for row in got["rows"]}

    assert (by_place["P3"]["name"], by_place["P3"]["named"]) == ("PUNISHED",
                                                                 True)
    assert (by_place["P5"]["name"], by_place["P5"]["named"]) == (UNNAMED,
                                                                 False)
    assert (by_place["P6"]["name"], by_place["P6"]["named"]) == (UNNAMED,
                                                                 False)
    assert by_place["P4"]["name"] == "YOU" and by_place["P4"]["named"] is True
    # **Nothing was dropped and nothing else moved.** The unnamed rows keep
    # their place, their stop and their fuel - the naming failure costs the
    # name and only the name.
    assert len(got["rows"]) == 6, [row["name"] for row in got["rows"]]
    assert by_place["P5"]["stop"] == "L11" and by_place["P5"]["fuel"]
    assert UNNAMED not in {"", "-"}, "the word must not read as a value"


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
    # The board still has the old order; the trends know who they watched -
    # by cluster id, and the roster's name for that id comes with them.
    state.gap_ahead.subject, state.gap_ahead_name = 533, "K.Graebs"
    state.gap_behind.subject, state.gap_behind_name = 277, "PUNISHED"
    board = BoardRead(packet=1, places={"PUNISHED": 3, "K.Graebs": 5},
                      visible=frozenset({3, 5}), windowed=False)
    rows = {row.name: row for row in field_view(state, board, packet=1).rows}
    assert rows["K.Graebs"].gap_s == 1.4      # the ahead trend's own subject
    assert rows["PUNISHED"].gap_s == 0.8      # the behind trend's
    assert rows["PUNISHED"].place == 3        # the board's place is untouched


def test_a_gap_is_drawn_although_its_subject_is_an_int_the_rows_never_hold():
    """**The defect that cost a whole race, stated as a type.**

    20 Sep, Bathurst Rd8: the tablet was the only surface carrying gaps and
    it drew none, for 62 minutes, silently - because it keyed the gap by
    `GapTrend.subject`, an int roster cluster id, against rows keyed by
    name. Nothing could match and nothing said so, because `subject` is
    never `None`, so the "no subject" log line never fired either.

    Seeded exactly as production does: an int on the trend, the roster's
    name beside it.
    """
    state = _state()
    assert isinstance(state.gap_ahead.subject, int), "production seeds an int"
    board = BoardRead(packet=1, places={"PUNISHED": 3, "K.Graebs": 5},
                      visible=frozenset({3, 5}), windowed=False)
    rows = {row.name: row for row in field_view(state, board, packet=1).rows}
    assert rows["PUNISHED"].gap_s == 1.4
    assert rows["K.Graebs"].gap_s == 0.8


def test_a_gap_whose_cluster_the_roster_never_named_is_not_drawn():
    """**A third of the readings, and that is correct** (rule 3). An
    unlabelled cluster has no name, the rows are names, so the figure is
    real but unattributable - and an unattributed number on a row is the
    shape of the mistake, not its size. It is not drawn, and the reason is
    logged."""
    state = _state()
    state.gap_ahead_name = state.gap_behind_name = None
    assert state.gap_ahead.subject is not None, "the trend still has a subject"
    board = BoardRead(packet=1, places={"PUNISHED": 3, "K.Graebs": 5},
                      visible=frozenset({3, 5}), windowed=False)
    rows = field_view(state, board, packet=1).rows
    assert all(row.gap_s is None for row in rows)


def test_a_gap_with_no_subject_is_not_drawn_against_anyone():
    state = _state()
    state.gap_ahead.subject = None
    state.gap_behind.subject = None
    state.gap_ahead_name = state.gap_behind_name = None   # the roster's answer
    board = BoardRead(packet=1, places={"PUNISHED": 3, "K.Graebs": 5},
                      visible=frozenset({3, 5}), windowed=False)
    rows = field_view(state, board, packet=1).rows
    assert all(row.gap_s is None for row in rows)


def test_a_gap_from_laps_ago_is_not_still_on_the_screen():
    """`latest()` is keyed by lap and never expires, so a reader that stopped
    left a bare "1.4" up for the rest of the race. `news` bounds a spoken gap
    at `GAP_FRESH_S`; the screen bounded nothing."""
    state = _state()                    # ahead is PUNISHED, cluster 277
    board = BoardRead(packet=1, places={"PUNISHED": 3}, visible=frozenset({3}),
                      windowed=False)
    fresh = {r.name: r for r in field_view(state, board, packet=1).rows}
    assert fresh["PUNISHED"].gap_s == 1.4
    state.lap += 5                              # five laps with no new read
    stale = {r.name: r for r in field_view(state, board, packet=1).rows}
    assert stale["PUNISHED"].gap_s is None


def test_a_gap_the_reader_has_lost_is_drawn_as_missing_not_as_nothing():
    """**An empty gap cell said two opposite things and he could tell them
    apart on neither.**

    A car that is not one of the two either side of us has no interval box
    on his screen and never will: its cell is empty because there is nothing
    to read. A gap that has expired is a number the app HAS and will not
    stand behind. Drawn the same, the second reads as the first, and the
    driver learns nothing from the column going quiet - which is exactly
    when he needs to know (rule 3).
    """
    state = _state()                    # ahead is PUNISHED, cluster 277
    board = BoardRead(packet=1, places={"PUNISHED": 3, "X-Man Oce": 6},
                      visible=frozenset({3, 6}), windowed=False)
    live = {r.name: r for r in field_view(state, board, packet=1).rows}
    assert (live["PUNISHED"].gap_s, live["PUNISHED"].gap_unread) == (1.4, False)
    # Never a neighbour: no box, nothing to lose.
    assert (live["X-Man Oce"].gap_s, live["X-Man Oce"].gap_unread) == (None,
                                                                      False)
    state.lap += 3                              # the reading is laps behind
    lost = {r.name: r for r in field_view(state, board, packet=1).rows}
    assert lost["PUNISHED"].gap_s is None and lost["PUNISHED"].gap_unread
    assert not lost["X-Man Oce"].gap_unread


def test_a_reading_from_the_lap_before_the_crossing_is_not_this_laps_gap():
    """**The bound is the lap he is DRIVING, and the two laps were counted in
    different domains.**

    `GapTrend` is keyed by `lap_now()` - laps behind him - and this file
    counts in `lap_on_screen()`, the lap in progress. The old subtraction
    crossed the two and its constant read `1`, so the comment beside it
    promised "a reading from the lap before is still drawn" while the
    arithmetic refused it. One lap of a GT3 at Monza is about 105 s; the
    figure it would have carried is a car he has had a whole lap to pass.

    This pins the behaviour the constant change preserves. Measured against
    `bf84519`: `gap_s` was already `None` a lap on - which is why `E-boards`'
    *"up to two laps stale, ~250 s"* overstated it; the real bound was one
    lap, reached by an off-by-one rather than by the rule. The new half is
    that the row now SAYS so instead of going blank.
    """
    state = _state()                              # trend key 18, HUD lap 19
    board = BoardRead(packet=1, places={"PUNISHED": 3}, visible=frozenset({3}),
                      windowed=False)
    assert field_view(state, board, packet=1).rows[0].gap_s == 1.4
    state.lap += 1                                # one crossing, no new read
    only = field_view(state, board, packet=1).rows[0]
    assert only.gap_s is None and only.gap_unread


def test_a_gap_is_withdrawn_when_the_board_reader_has_gone_quiet():
    """**The board and the gaps are one instrument reading one frame.**

    `pit_wall._see` takes the ladder and the interval boxes off the same
    grab in the same pass, and the archive says how tightly they travel: of
    the gap readings this page can draw - a subject the roster named - 2054
    of 2057 at session 204, and every one of 1507 at 188 and 771 at 176,
    came off a frame that also produced a board read. So a board that has
    not been read inside `BOARD_FRESH_S` is a reader that has stopped, and
    the gap it left is not a current reading whatever lap it was taken on.

    Replayed over session 204, the lap bound alone let a figure stand for up
    to 83 s; with this it is 31 s ahead and 46 s behind. The bound is the
    value George already refuses a board at, not a second number beside it
    (rule 13).
    """
    from pitcrew.race.field import BOARD_FRESH_S

    state = _state()
    board = BoardRead(packet=0, places={"PUNISHED": 3}, visible=frozenset({3}),
                      windowed=False)
    inside = field_view(state, board,
                        packet=int((BOARD_FRESH_S - 1) * SAMPLE_HZ)).rows[0]
    assert inside.gap_s == 1.4 and not inside.gap_unread
    past = field_view(state, board,
                      packet=int((BOARD_FRESH_S + 1) * SAMPLE_HZ)).rows[0]
    assert past.gap_s is None and past.gap_unread


def test_a_gap_whose_age_cannot_be_established_is_not_a_fresh_gap():
    """Rule 3, on the age itself. A board read refused as stamped in the
    future takes its places with it - and it has to take the gap too, or the
    page refuses to say where anybody is while asserting how far away one of
    them is. No age is not an age of zero."""
    state = _state()
    board = BoardRead(packet=5_000, places={"PUNISHED": 3},
                      visible=frozenset({3}), windowed=False)
    view = field_view(state, board, packet=10)       # stamped in the future
    assert view.board_age_s is None
    assert all(row.gap_s is None for row in view.rows)


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

    The content-type check answered before reading the request, so Windows
    reset the connection with the reply in flight and the page got a
    transport error where the server had sent a perfectly good "not a press".
    The tablet then says the PC is unreachable - which is the one thing that
    had NOT happened - and he presses the button again.
    """
    import json
    import urllib.error
    import urllib.request

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

        # The body is read even where the content type is refused outright.
        status, why = post('{"action": "george", "value": false}',
                           kind="text/plain")
        assert (status, why.get("why")) == (415, "not a press")
        assert presses == []
    finally:
        server.stop()


def _tablet_page():
    from pathlib import Path

    return (Path(__file__).resolve().parents[1] / "ui"
            / "tablet.html").read_text(encoding="utf-8")


def test_the_page_asks_for_no_code_at_all():
    """21 Sep 2026, his call: *"I don't need codes on the buttons on the
    tablet, it's a local only web page, no one in my home will muck around
    with it."*

    The whole pairing machinery is gone - the panel, the keypad, the stored
    key and the `locked` face - rather than being left switched off, because
    a code nothing checks is a second answer to the question of who may
    press. What is NOT gone is the content type: that is what stops a page
    open elsewhere on the Wi-Fi posting one, and it never asked him for
    anything.
    """
    source = _tablet_page()
    for gone in ("pair", "localStorage", "heldKey", "buttons.locked",
                 "tablet-key"):
        assert gone not in source, f"the buttons code is back: {gone}"
    assert '"Content-Type": "application/json"' in source
    assert '{ action: action, value: value }' in source


def test_the_three_sessions_are_started_from_the_cover():
    """His ask: start a practice, a qualifying run or the race from the seat.

    **They are on the cover and nowhere else.** The cover is exactly the "no
    session running" state, so a Start cannot be brushed against with a race
    under way - and the button that ENDS one is a hold, like the pit button,
    for the same reason.
    """
    source = _tablet_page()
    for ask in ("s-practice", "s-quali", "s-race"):
        assert f'id="{ask}"' in source
    assert 'press("session", "practice")' in source
    assert 'press("session", "quali")' in source
    assert 'press("session", "race")' in source
    # Started with a tap, stopped with a hold.
    assert 'hold("b-session"' in source
    assert 'press("session", "stop")' in source
    # The start face is shown from `idle`, which is the state itself - never
    # from the payload's age, because nothing publishes between sessions and
    # the buttons would go a second and a half after the last one closed.
    assert 'if (d.idle) {' in source
    assert "#cover.start #start" in source


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


def test_the_tablet_says_whether_a_car_can_push_not_only_whether_it_reaches():
    """**"Reaches the flag" was one verdict for two opposite cars.**

    Rocky at Sardegna Rd 9 (session 188): in on 19 L, out on 89, 15 laps to
    run at 5.79 L/lap - 86.8 L needed, 2.2 L spare. He told the driver he was
    managing fuel all stint, and he was: that fill allowed his rate and not a
    litre more. A car with 24 L spare reaches the flag too, and can come after
    you. "Can he push?" is the question the driver asked, so it is what the
    row answers - and "fuel to push" is said only where the spare is bigger
    than the reading error, so no new threshold is tuned for it.
    """
    from pitcrew.race.rival_calls import Rival
    from pitcrew.race.rivals import Stop
    from pitcrew.ui.tablet import prediction_words

    rocky = Rival(name="Rocky", pitted=True, burn_per_lap_l=5.79, burn_stops=1,
                  stop=Stop(lap=14, fuel_in_l=19.0, fuel_out_l=89.0))
    got = predict(rocky, stops_seen=1, our_burn_l=5.2, laps_total=29)
    assert got.words == REACHES_FLAG
    assert abs(got.spare_l - 2.2) < 0.1
    assert got.spare_readable is False          # 2.2 L inside an ~8 L error
    # "On the limit", not "no fuel to push": a spare inside the reading
    # error is one the instrument cannot resolve, so it may not be called
    # zero (rule 3) - and "on the limit" is what the point estimate says.
    assert prediction_words(got)[1].startswith("on the limit")

    flush = Rival(name="Flush", pitted=True, burn_per_lap_l=5.0, burn_stops=2,
                  stop=Stop(lap=14, fuel_in_l=19.0, fuel_out_l=99.0))
    plenty = predict(flush, stops_seen=1, our_burn_l=5.2, laps_total=29)
    assert plenty.spare_readable is True
    assert prediction_words(plenty)[1].startswith("24 L to push")

    # Sized to the column: nothing here may run past what it holds unclipped.
    for car in (rocky, flush):
        words = prediction_words(predict(car, stops_seen=1, our_burn_l=5.2,
                                         laps_total=29))[1]
        assert len(words) <= 38, (len(words), words)
