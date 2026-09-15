"""The phone strip: what it says, and the server that hands it over.

Asked for on 15 Sep 2026 - his iPhone on the game monitor, showing the
quick-reference numbers from a page the app serves on the local network, with
a centre slot that "changes based on what's important right now". Most of
these tests are about that slot, because a number whose meaning changes is
the rule-13 hazard in its purest form: it must always carry its own caption,
follow one fixed order, and not flicker between meanings on a noisy gap.

The rest hold the two failures that matter for a screen he cannot inspect
mid-race: a feed that stops must read NO DATA rather than a frozen number,
and the ultrawide must take the moved numbers back the moment the phone goes.
"""
from __future__ import annotations

import json
import os
import socket
import urllib.request
from dataclasses import replace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication  # noqa: E402

from pitcrew.ui.driver_view import (  # noqa: E402
    DriverState, DriverView, GapView, box_block, fuel_stop_block, gap_block)
from pitcrew.ui.strip import (  # noqa: E402
    CENTRE_BOX, CENTRE_CAR_AHEAD, CENTRE_CAR_BEHIND, CENTRE_FUEL_SHORT,
    CENTRE_LAPS_TO_STOP, CENTRE_RELEASE, CENTRE_TIME_DIFF, NEAR_CAR_RELEASE_S,
    NEAR_CAR_S, StripComposer)
from pitcrew.ui.strip_server import (  # noqa: E402
    LIVE_WITHIN_S, STALE_AFTER_S, StripServer)


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def racing(**kw) -> DriverState:
    """A race four laps from a planned stop, fuel on plan, nobody close."""
    base = dict(has_plan=True, laps_to_box=4.0, box_on_lap=14,
                fuel_to_stop=0.3, laps_of_fuel=4.3,
                ahead=GapView(seconds=3.4, note="steady"),
                behind=GapView(seconds=2.6, note="steady"))
    base.update(kw)
    return DriverState(**base)


# ------------------------------------------------------------- the default

def test_no_session_says_so_rather_than_holding_the_last_race():
    assert StripComposer().compose(None) == {"v": 1, "idle": True}


def test_a_quiet_race_leads_with_laps_to_the_stop_in_the_boards_own_words():
    """The phone and the ultrawide word one number once - `box_block`."""
    state = racing()
    got = StripComposer().compose(state)
    assert got["centre"]["id"] == CENTRE_LAPS_TO_STOP
    assert got["centre"]["caption"] == "LAPS TO THE STOP"
    expected = box_block(state)
    assert (got["centre"]["value"], got["centre"]["sub"]) == \
        (expected.value, expected.sub)
    assert got["left"]["caption"] == "AHEAD"
    assert got["right"]["caption"] == "BEHIND"
    assert got["extra"]["caption"] == "IN HAND TO THE STOP"
    assert got["extra"]["value"] == fuel_stop_block(state).value


def test_an_unread_gap_is_a_dash_with_its_reason_never_a_zero():
    got = StripComposer().compose(racing(ahead=None))
    assert got["left"]["value"] == "--"
    assert got["left"]["sub"] == gap_block(None).sub == "no gap read"


# ------------------------------------------------------------- the ladder

def test_in_the_box_the_centre_is_the_release_countdown():
    got = StripComposer().compose(racing(
        in_box=True, release_in_s=7.2, fuel_target_l=41.0, fuel_l=12.0,
        tyres_at_stop=False))
    assert got["kind"] == "box"
    assert got["centre"]["id"] == CENTRE_RELEASE
    assert got["centre"]["value"] == "8"            # rounded up, as the board
    assert got["centre"]["tone"] == "urgent"        # inside ten seconds
    assert got["left"]["caption"] == "FUEL TO"
    assert got["right"]["value"] == "NO TYRES"


def test_the_box_lap_takes_the_centre_as_now():
    got = StripComposer().compose(racing(laps_to_box=0.0, laps_past_box=0,
                                         tyres_at_stop=True,
                                         next_compound="rm"))
    assert got["centre"]["id"] == CENTRE_BOX
    assert got["centre"]["value"] == "NOW"
    assert got["centre"]["sub"] == "box this lap · fit RM"
    assert got["centre"]["tone"] == "urgent"


def test_fuel_short_of_the_stop_takes_the_centre_and_leaves_the_extra_slot():
    got = StripComposer().compose(racing(fuel_to_stop=-0.4))
    assert got["centre"]["id"] == CENTRE_FUEL_SHORT
    assert got["centre"]["value"] == "-0.4"
    assert got["centre"]["tone"] == "urgent"
    assert got["extra"] is None                     # not drawn twice


def test_a_car_within_a_second_takes_the_centre_and_its_flank_shows_the_stop():
    got = StripComposer().compose(racing(
        behind=GapView(seconds=0.7, note="he is catching 0.9 s a lap",
                       urgent=True)))
    assert got["centre"]["id"] == CENTRE_CAR_BEHIND
    assert got["centre"]["caption"] == "BEHIND"
    assert got["centre"]["value"] == "0.7"
    # The neighbour is not drawn twice; nothing left the strip.
    assert got["right"]["id"] == CENTRE_LAPS_TO_STOP
    assert got["left"]["caption"] == "AHEAD"


def test_the_order_is_box_then_fuel_then_a_car():
    close = GapView(seconds=0.4, note="")
    composer = StripComposer()
    state = racing(laps_to_box=0.0, laps_past_box=0, fuel_to_stop=-0.2,
                   ahead=close, behind=close)
    assert composer.compose(state)["centre"]["id"] == CENTRE_BOX
    state = replace(state, laps_past_box=None, laps_to_box=3.0)
    assert composer.compose(state)["centre"]["id"] == CENTRE_FUEL_SHORT
    state = replace(state, fuel_to_stop=0.1)
    assert composer.compose(state)["centre"]["id"] in (CENTRE_CAR_AHEAD,
                                                       CENTRE_CAR_BEHIND)


def test_the_nearer_car_wins_and_a_dead_heat_goes_to_the_car_behind():
    composer = StripComposer()
    got = composer.compose(racing(ahead=GapView(seconds=0.5),
                                  behind=GapView(seconds=0.8)))
    assert got["centre"]["id"] == CENTRE_CAR_AHEAD
    composer.new_session()
    got = composer.compose(racing(ahead=GapView(seconds=0.6),
                                  behind=GapView(seconds=0.6)))
    assert got["centre"]["id"] == CENTRE_CAR_BEHIND


def test_a_car_slot_holds_across_the_line_and_lets_go_past_the_hold():
    """0.98 then 1.02 must not flip what the big number means."""
    composer = StripComposer()
    at = lambda s: composer.compose(racing(behind=GapView(seconds=s)))  # noqa: E731
    assert at(0.9)["centre"]["id"] == CENTRE_CAR_BEHIND
    assert at(NEAR_CAR_S + 0.1)["centre"]["id"] == CENTRE_CAR_BEHIND
    assert at(NEAR_CAR_RELEASE_S + 0.1)["centre"]["id"] == CENTRE_LAPS_TO_STOP
    # And a car arriving at 1.1 from outside never took it at all.
    assert at(NEAR_CAR_S + 0.1)["centre"]["id"] == CENTRE_LAPS_TO_STOP


def test_the_hold_does_not_survive_into_the_next_session():
    composer = StripComposer()
    composer.compose(racing(behind=GapView(seconds=0.9)))
    composer.new_session()
    got = composer.compose(racing(behind=GapView(seconds=1.1)))
    assert got["centre"]["id"] == CENTRE_LAPS_TO_STOP


def test_at_the_flag_there_is_no_car_to_race():
    got = StripComposer().compose(racing(
        finished=True, laps_to_box=None, behind=GapView(seconds=0.3)))
    assert got["centre"]["value"] == "FLAG"


# ------------------------------------------------------------- practice

def test_practice_leads_with_the_time_difference_named_against_its_reference():
    got = StripComposer().compose(DriverState(
        session_kind="practice", lap_time_ms=61_250, delta_s=-0.214,
        predicted_ms=92_204, session_best_ms=92_418, reference_compound="RM"))
    assert got["centre"]["id"] == CENTRE_TIME_DIFF
    assert got["centre"]["value"] == "-0.214"
    assert got["centre"]["tone"] == "good"
    assert "vs RM session best 1:32.418" in got["centre"]["sub"]
    assert got["left"]["value"] == "1:01.250"
    assert got["right"]["value"] == "1:32.204"


def test_the_lights_carry_their_own_ink_and_never_claim_a_reading_they_lack():
    got = StripComposer().compose(DriverState(
        session_kind="practice", wet="wet", tcs_active=True, front_lock=None))
    wet, abs_, tcs = got["lights"]
    assert wet["ink"] is not None
    assert abs_["ink"] is None and abs_["sub"] == "no reading"
    assert tcs["ink"] is not None and tcs["word"] == "TCS"


# ------------------------------------------------------------- the ultrawide

def test_the_ultrawide_gives_up_the_gaps_and_the_stop_only_while_a_phone_reads(app):
    view = DriverView()
    view.update_state(racing(strip_live=True))
    assert view.leading.isHidden() and view.box_stat.isHidden()
    # The phone went flat: both come straight back.
    view.update_state(racing(strip_live=False))
    assert not view.leading.isHidden() and not view.box_stat.isHidden()


def test_practice_is_untouched_by_the_strip(app):
    view = DriverView()
    view.update_state(DriverState(session_kind="practice", strip_live=True))
    assert not view.box_stat.isHidden()


# ------------------------------------------------------------- the server

class _Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def _get(server, path):
    with urllib.request.urlopen(
            f"http://127.0.0.1:{server.port}{path}", timeout=5) as reply:
        return reply.status, reply.headers, reply.read()


@pytest.fixture
def served():
    clock = _Clock()
    server = StripServer(port=0, host="127.0.0.1", clock=clock)
    # Port 0 is resolved on bind; read the real one back.
    assert server.start()
    server.port = server._httpd.server_address[1]
    yield server, clock
    server.stop()


def test_it_serves_the_page_and_nothing_it_was_not_asked_to(served):
    server, _ = served
    status, headers, body = _get(server, "/")
    assert status == 200 and b"NO DATA" in body
    assert headers["Cache-Control"] == "no-store"
    with pytest.raises(urllib.error.HTTPError) as refused:
        _get(server, "/../settings.py")
    assert refused.value.code == 404


def test_before_anything_is_published_the_page_is_told_it_is_waiting(served):
    server, _ = served
    _, _, body = _get(server, "/strip/state")
    got = json.loads(body)
    assert got["empty"] is True and got["age_s"] is None
    assert got["stale_after_s"] == STALE_AFTER_S


def test_every_answer_says_how_old_the_numbers_are(served):
    """The phone cannot compare clocks with the PC, so the age is decided
    here and the page blanks on it."""
    server, clock = served
    server.publish(StripComposer().compose(racing()))
    clock.now += 2.0
    got = json.loads(_get(server, "/strip/state")[2])
    assert got["age_s"] == 2.0 and got["age_s"] > got["stale_after_s"]
    assert got["centre"]["id"] == CENTRE_LAPS_TO_STOP


def test_a_non_finite_number_is_null_not_a_document_the_browser_refuses(served):
    server, _ = served
    server.publish({"v": 1, "idle": False, "x": float("nan")})
    assert json.loads(_get(server, "/strip/state")[2])["x"] is None


def test_live_means_a_page_is_actually_polling(served):
    server, clock = served
    assert not server.live()
    _get(server, "/strip/state")
    assert server.live() and server.last_client == "127.0.0.1"
    clock.now += LIVE_WITHIN_S + 0.1
    assert not server.live()


def test_a_taken_port_fails_to_start_and_says_so_rather_than_sharing_it(served):
    """With address reuse on, Windows let the second server bind the same
    port and the phone was answered by whichever socket it picked."""
    first, _ = served
    second = StripServer(port=first.port, host="127.0.0.1")
    try:
        assert second.start() is False
        assert not second.running
    finally:
        second.stop()


# ------------------------------------------------------------- the controller

def _controller_harness(server):
    from pitcrew.controller import PitCrewController

    ctl = PitCrewController.__new__(PitCrewController)
    ctl.strip = server
    ctl._strip_composer = StripComposer()
    ctl._strip_was_live = False
    ctl._strip_failures = 0
    return ctl


class _FakeServer:
    def __init__(self, live):
        self._live = live
        self.published = []
        self.last_client = "192.168.1.20"

    def live(self):
        return self._live

    def publish(self, body):
        self.published.append(body)


def test_the_controller_builds_the_state_once_and_marks_it_live():
    server = _FakeServer(live=True)
    ctl = _controller_harness(server)
    ctl._driver_board_state = lambda: racing()
    state = ctl._publish_strip()
    assert state.strip_live is True
    assert server.published[-1]["centre"]["id"] == CENTRE_LAPS_TO_STOP


def test_a_strip_that_cannot_be_built_publishes_nothing_so_the_page_goes_stale():
    server = _FakeServer(live=False)
    ctl = _controller_harness(server)

    def broken():
        raise ValueError("a data race on the temperature window")

    ctl._driver_board_state = broken
    assert ctl._publish_strip() is None
    assert server.published == []
