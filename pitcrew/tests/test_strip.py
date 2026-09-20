"""The phone strip: what it says, and the server that hands it over.

Asked for on 15 Sep 2026 as quick reference on the game monitor; redrawn on
17 Sep 2026 as **his own car, laid out like a lap timer** - last lap and the
best across the top, the delta as a flood across the middle, the lap and the
burn against the plan along the bottom. The gaps went to the tablet.

Most of these tests are about the middle, because a band whose meaning can
change is the rule-13 hazard: it must always carry its own caption, name what
the delta is against, and give way to an instruction in one fixed order.

The rest hold the failure that matters for a screen he cannot inspect
mid-race: a feed that stops must read NO DATA rather than a frozen number.
"""
from __future__ import annotations

import json
import os
import urllib.request

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication  # noqa: E402

from pitcrew.ui.driver_view import (  # noqa: E402
    DriverState, DriverView, box_block, fuel_stop_block)
from pitcrew.ui.strip import (  # noqa: E402
    CENTRE_BOX, CENTRE_DELTA, CENTRE_FUEL_SHORT, CENTRE_RELEASE,
    PAYLOAD_VERSION, StripComposer)
from pitcrew.ui.strip_server import (  # noqa: E402
    LIVE_WITHIN_S, STALE_AFTER_S, StripServer)


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def racing(**kw) -> DriverState:
    """Lap 8 of a race on a plan with targets, fuel on plan, nothing to do."""
    base = dict(session_kind="race", has_plan=True, laps_to_box=6.0,
                box_on_lap=14, fuel_to_stop=0.4, laps_of_fuel=6.4,
                last_lap_ms=101_412, lap_number=8, target_lap_ms=101_100,
                predicted_ms=101_410, target_burn_l=5.37, target_saving=True,
                last_vs_target_s=0.312, last_burn_vs_target_l=0.12,
                stint_burn_vs_target_l=0.05, stint_burn_laps=6,
                stint_burn_saving=True)
    base.update(kw)
    return DriverState(**base)


def practising(**kw) -> DriverState:
    base = dict(session_kind="practice", reference_compound="RM",
                last_lap_ms=134_400, lap_number=7, file_best_ms=133_700,
                delta_file_s=0.31)
    base.update(kw)
    return DriverState(**base)


# ------------------------------------------------------------- the face

def test_no_session_says_so_rather_than_holding_the_last_race():
    assert StripComposer().compose(None) == {"v": PAYLOAD_VERSION, "idle": True}


def test_practice_is_the_lap_timer_against_the_best_ever_on_this_compound():
    """His words: "best lap time ever recorded on that compound"."""
    got = StripComposer().compose(practising())
    assert (got["last"]["caption"], got["last"]["value"]) == ("LAST LAP", "2:14.400")
    assert (got["best"]["caption"], got["best"]["value"]) == ("BEST · RM", "2:13.700")
    assert got["best"]["tone"] == "good"          # green, as the timer's
    assert got["centre"]["caption"] == "VS BEST"
    assert (got["centre"]["value"], got["centre"]["tone"]) == ("+0.310", "urgent")
    assert got["centre"]["act"] is False          # slow is red, not an order
    assert got["lap"]["value"] == "7"
    assert got["burn"] is None                    # no plan burn in practice


def test_with_no_best_on_file_the_delta_says_so_rather_than_a_zero():
    got = StripComposer().compose(practising(file_best_ms=None, delta_file_s=None))
    assert got["centre"]["value"] == "--.---"
    assert got["centre"]["sub"] == "no best on file"


def test_the_race_delta_is_the_projected_lap_against_the_plans_lap():
    got = StripComposer().compose(racing())
    assert (got["best"]["caption"], got["best"]["value"]) == (
        "TARGET LAP · SAVE", "1:41.100")
    assert got["centre"]["id"] == CENTRE_DELTA
    # **The caption says which lap** - the one being driven, projected, or the
    # one just finished. One band, two quantities, same ink (rule 13). And the
    # word is the voice's own: "Pace on target".
    assert got["centre"]["caption"] == "VS TARGET · PROJ"
    assert got["centre"]["value"] == "+0.310"
    # A projection, and it says so (rule 5).
    assert got["centre"]["sub"] == "projected 1:41.410"
    assert got["centre"]["tone"] == "urgent"
    assert got["lap"]["value"] == "8"


def test_before_a_projection_exists_the_last_lap_stands_in_and_says_so():
    got = StripComposer().compose(racing(predicted_ms=None))
    assert (got["centre"]["value"], got["centre"]["sub"]) == ("+0.312", "last lap")
    assert got["centre"]["caption"] == "VS TARGET · LAST"


def test_the_burn_is_this_lap_against_the_plan_with_the_stint_on_its_column():
    """The stint figure names its column and its lap count: the two beeps
    burn ~30% apart, and pooling them looks right and is not."""
    burn = StripComposer().compose(racing())["burn"]
    assert burn["caption"] == "BURN VS TARGET"
    assert (burn["value"], burn["tone"]) == ("+0.12", "urgent")
    assert burn["sub"] == "stint +0.05 · 6 laps · save"


def test_the_burn_caption_names_which_burn_the_target_is():
    """Rule 13 on the screen right of his wheel. At Bathurst Rd 8 the figure
    under this caption stepped 10.625 -> 8.47 around lap 7 - the plan's burn
    replaced by this race's own - and the slot read "BURN VS TARGET" over
    both halves, so a change of reference was drawn as a change of driving.

    The caption rather than the sub, because the sub is already the stint's
    mean and ITS lap count, and two counts on one line is the same defect."""
    from pitcrew.strategy.targets import BURN_BASIS_PLAN, BURN_BASIS_RACE

    plan = StripComposer().compose(
        racing(target_burn_l=10.625, target_burn_source=BURN_BASIS_PLAN,
               last_burn_source=BURN_BASIS_PLAN))["burn"]
    assert plan["caption"] == "BURN VS PLAN"

    race = StripComposer().compose(
        racing(target_burn_l=8.47, target_burn_source=BURN_BASIS_RACE,
               target_burn_laps=7, last_burn_source=BURN_BASIS_RACE))["burn"]
    assert race["caption"] == "BURN VS RACE"
    # The sub is untouched: the stint's own mean, on its own column.
    assert race["sub"] == "stint +0.05 · 6 laps · save"
    # **And the page marks the change for nothing.** `strip.html`'s `fig`
    # keys a figure's identity on its subject or, failing that, its caption,
    # so a caption that changed makes the burn a new thing and it is drawn
    # rather than rolled - the page's own idiom, no animation written.
    assert plan["subject"] == race["subject"] == ""
    assert plan["caption"] != race["caption"]


def test_a_burn_target_that_named_no_reference_keeps_the_old_caption():
    """Rule 3: nothing said which burn it is, so nothing is claimed."""
    assert StripComposer().compose(racing())["burn"]["caption"] ==         "BURN VS TARGET"


def test_an_instruction_takes_the_band_in_a_fixed_order():
    composer = StripComposer()
    state = racing(laps_to_box=0.0, laps_past_box=0, fuel_to_stop=-0.2)
    now = composer.compose(state)["centre"]
    assert now["id"] == CENTRE_BOX and now["act"] is True
    assert (now["caption"], now["value"]) == ("LAPS TO THE STOP",
                                              box_block(state).value)
    short_state = racing(fuel_to_stop=-0.2)
    short = composer.compose(short_state)["centre"]
    assert short["id"] == CENTRE_FUEL_SHORT and short["act"] is True
    assert short["value"] == fuel_stop_block(short_state).value
    # Two laps to the stop is amber on the ultrawide, and not an order here.
    assert composer.compose(racing(laps_to_box=2.0))["centre"]["id"] == CENTRE_DELTA


def test_in_the_box_the_band_is_the_release_countdown():
    got = StripComposer().compose(racing(
        in_box=True, release_in_s=7.2, fuel_target_l=41.0, fuel_l=12.0,
        tyres_at_stop=False))
    assert got["kind"] == "box"
    assert got["centre"]["id"] == CENTRE_RELEASE
    assert got["centre"]["value"] == "8"            # rounded up, as the board
    assert got["centre"]["act"] is True             # inside ten seconds
    assert got["last"]["caption"] == "FUEL TO"
    assert got["best"]["value"] == "NO TYRES"


def test_the_gaps_are_not_on_the_phone_any_more():
    """17 Sep 2026: his car on the phone, the field on the tablet."""
    got = StripComposer().compose(racing())
    assert not {"left", "right", "extra", "extra2"} & set(got)
    assert "AHEAD" not in json.dumps(got) and "BEHIND" not in json.dumps(got)


def test_the_lights_carry_their_own_ink_and_never_claim_a_reading_they_lack():
    got = StripComposer().compose(DriverState(
        session_kind="practice", wet="wet", tcs_active=True, front_lock=None))
    wet, abs_, tcs = got["lights"]
    assert wet["ink"] is not None
    assert abs_["ink"] is None and abs_["sub"] == "no reading"
    assert tcs["ink"] is not None and tcs["word"] == "TCS"


def test_an_unread_lamp_is_not_a_lamp_reading_no():
    """`abs_light(None)` is "no reading" and `abs_light(False)` is "no lock";
    both draw unlit, so the page is told which is which (rule 3)."""
    unread = StripComposer().compose(DriverState(
        session_kind="practice", wet=None, front_lock=None, tcs_active=None))
    assert [light["unread"] for light in unread["lights"]] == [True, True, True]
    measured = StripComposer().compose(DriverState(
        session_kind="practice", wet="dry", abs_setting="Weak",
        front_lock=False, tcs_active=False))
    assert [light["unread"] for light in measured["lights"]] == [False] * 3


def test_the_band_says_flag_rather_than_flooding_red_on_the_slow_down_lap():
    got = StripComposer().compose(racing(finished=True))
    assert got["centre"]["value"] == "FLAG"
    assert got["centre"]["tone"] == "plain"


def test_the_page_is_laid_out_like_the_lap_timer():
    from pitcrew.ui.strip_server import PAGE

    page = PAGE.read_text(encoding="utf-8")
    for part in ('id="last"', 'id="best"', 'id="band"', 'id="lap"',
                 'id="burn"', 'id="lights"'):
        assert part in page, part
    # The band's colour is its meaning: amber only for an instruction.
    assert "data.act === true" in page
    assert "#band.quick { --fill: var(--quick); }" in page
    # The watchdog is armed by a render that FINISHED: stamped first, a render
    # that threw left the last numbers up for ever (CLAUDE.md 7).
    assert "render(d); lastOk = performance.now(); last = d;" in page
    # An unread lamp is marked, and a turn of the phone re-fits the figures.
    assert 'data.unread ? " ?" : ""' in page
    assert 'window.addEventListener("resize"' in page


# ------------------------------------------------------------- the ultrawide

def test_the_ultrawide_still_draws_its_phone_page_when_asked(app):
    """The page stays for the tablet: when the tablet carries the gaps, the
    ultrawide gives them up. Nothing asks for it until then."""
    view = DriverView()
    view.update_state(racing(strip_live=True, position=6, field_size=12))
    assert view.lower.currentWidget() is view.race_phone
    view.update_state(racing(strip_live=False))
    assert view.lower.currentWidget() is view._race_lower


def test_practice_is_untouched_by_the_strip(app):
    view = DriverView()
    view.update_state(DriverState(session_kind="practice", strip_live=True))
    assert view.lower.currentWidget() is view.leading_lap


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
    assert got["centre"]["id"] == CENTRE_DELTA


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


def test_a_reading_phone_no_longer_takes_the_gaps_off_the_ultrawide():
    """The phone carries his car now, not the gaps - so a phone polling must
    not swap the ultrawide to the page that gives them up."""
    server = _FakeServer(live=True)
    ctl = _controller_harness(server)
    ctl._driver_board_state = lambda: racing()
    state = ctl._publish_strip()
    assert state.strip_live is False
    assert server.published[-1]["centre"]["id"] == CENTRE_DELTA


def test_a_strip_that_cannot_be_built_publishes_nothing_so_the_page_goes_stale():
    server = _FakeServer(live=False)
    ctl = _controller_harness(server)

    def broken():
        raise ValueError("a data race on the temperature window")

    ctl._driver_board_state = broken
    assert ctl._publish_strip() is None
    assert server.published == []
