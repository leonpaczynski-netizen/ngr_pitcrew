"""The tablet in practice - the other half of his ask of 20 Sep 2026.

*"in practice board on monitor should move to tablet as it has nothing on it
and the lap rack on the practice page can be visible on the monitor."*

It had nothing on it because `race/field.py` needs a race to build a field, so
`_publish_tablet` composed `None` and the page drew a cover reading "no race
running" beside three inert buttons - while the app's only practice instrument
sat on the monitor, which now carries the rack (`test_monitor_history.py`).

**Nothing is re-parented and nothing is re-derived.** The tablet is a served
HTML page polling for JSON; no Qt widget can move to it. So the practice board
is WORDED here, in Python, from the same expressions the monitor draws -
`classify`, `pair_gap`, `sector_blocks`, the three lamp helpers - and the page
only chooses a size and an ink. These hold that division, and hold the page to
rule 3 on a face where almost everything can be unmeasured.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pitcrew.ui.driver_view import DriverState  # noqa: E402
from pitcrew.ui.tablet import compose_practice  # noqa: E402

PAGE = Path(__file__).resolve().parents[1] / "ui" / "tablet.html"


def _practising(**over) -> DriverState:
    base = dict(session_kind="practice", lap_number=7, last_lap_ms=104_900,
                file_best_ms=104_100, delta_file_s=0.412,
                reference_compound="RM", compound="RM",
                temps_c={"fl": 101.0, "fr": 88.0, "rl": 92.0, "rr": 91.0},
                split_rates={"fl": 0.4})
    base.update(over)
    return DriverState(**base)


def _sectors(**over):
    from pitcrew.race.board_live import SectorsView

    base = dict(times_ms=(38_412, 41_100, 25_388),
                best_ms=(38_200, 41_100, 25_100),
                set_best=(False, True, False),
                cut="thirds of the lap - not GT7's", compound="RM")
    base.update(over)
    return SectorsView(**base)


def test_the_tablet_has_a_face_in_practice_instead_of_a_cover():
    """The whole of his complaint: it had nothing on it."""
    body = compose_practice(_practising())
    assert body["idle"] is False and body["kind"] == "practice"
    assert body["session"] == "PRACTICE" and body["lap"] == "LAP 7"
    assert len(body["tyres"]) == 4 and len(body["faces"]) == 3
    assert len(body["lights"]) == 3


def test_a_qualifying_run_says_so_rather_than_calling_itself_practice():
    """One lap and a session of them are not the same session, and the board
    already keeps them apart (`practice_intent`)."""
    assert compose_practice(_practising(
        session_kind="qualifying"))["session"] == "QUALIFYING"


def test_the_tablet_is_still_told_when_there_is_no_session_to_draw():
    """Rule 11: outside a session the page says so rather than holding the
    last one's numbers. `compose_practice` is the single place that decides,
    so "no session" cannot be one condition in the controller and a different
    one here."""
    assert compose_practice(None) == {"v": 1, "idle": True}
    # A race is not this face's business: it has a field, and `compose` owns
    # it. A bare `DriverState` is `session_kind="race"`.
    assert compose_practice(DriverState())["idle"] is True


def test_the_practice_face_invents_no_field_and_no_plan():
    """There is no field, no plan, no target lap and no target burn in
    practice. A payload carrying any of them would be rule 3 at the top of
    the screen, and the page would draw it as a reading."""
    body = compose_practice(_practising())
    for absent in ("rows", "position", "board", "board_age_s", "left_off"):
        assert absent not in body, absent


def test_the_corners_are_the_boards_own_reading_and_not_a_second_one():
    """`classify` and `pair_gap` stay in Python and the page gets the answer.
    Re-deriving a wear-onset threshold in CSS is how one screen comes to
    colour a tyre the other does not (rules 12 and 13)."""
    from pitcrew.ui.driver_view import classify, pair_gap

    state = _practising()
    drawn = {tyre["corner"]: tyre for tyre in compose_practice(state)["tyres"]}
    for corner in ("fl", "fr", "rl", "rr"):
        reading, lopsided = classify(corner, state.temps_c, state.compound)
        assert drawn[corner.upper()]["state"] == reading
        gap = pair_gap(corner, state.temps_c)
        if lopsided and gap is not None:
            assert f"+{gap:.0f} vs" in drawn[corner.upper()]["gap"]
        else:
            # **Only where it is a finding**, as `_Tyre` has it: a gap under
            # the threshold is a small figure to decide about at 200 km/h.
            assert drawn[corner.upper()]["gap"] == ""


def test_a_split_says_which_way_it_is_going_or_says_nothing():
    """A split that is opening and one that has settled are the same figure
    and opposite news - and no rate is not a rate of zero, so five laps that
    do not say yet get no word at all."""
    hot = {"fl": 101.0, "fr": 88.0, "rl": 92.0, "rr": 91.0}
    widening = {tyre["corner"]: tyre for tyre in compose_practice(
        _practising(temps_c=hot, split_rates={"fl": 0.4}))["tyres"]}
    assert widening["FL"]["gap"].endswith("WIDENING")
    assert widening["FL"]["gap_tone"] == "near"
    settling = {tyre["corner"]: tyre for tyre in compose_practice(
        _practising(temps_c=hot, split_rates={"fl": -0.4}))["tyres"]}
    assert settling["FL"]["gap"].endswith("SETTLING")
    assert settling["FL"]["gap_tone"] == "good"
    silent = {tyre["corner"]: tyre for tyre in compose_practice(
        _practising(temps_c=hot, split_rates={}))["tyres"]}
    assert silent["FL"]["gap"] == "+13 vs FR"


def test_a_corner_with_no_reading_is_a_dash_and_not_a_zero():
    """Rule 3. A corner the instrument cannot see is not a corner at 0 °C,
    and on this screen the number is the whole reading."""
    body = compose_practice(_practising(temps_c={"fl": 101.0}))
    drawn = {tyre["corner"]: tyre for tyre in body["tyres"]}
    assert drawn["FR"]["value"] == "--" and drawn["FR"]["state"] == "missing"
    assert drawn["FL"]["value"] == "101"


def test_the_practice_face_refuses_a_wear_line_it_has_no_compound_for():
    """With no compound `classify` returns "cool" for everything, so 96 °C on
    an unknown set draws exactly like 60 - and white on this instrument claims
    "not yet wearing faster for heat". It cannot claim that against nothing."""
    body = compose_practice(_practising(compound=None))
    assert "NO WEAR LINE" in body["tyre_caption"]
    assert "RM" in compose_practice(_practising())["tyre_caption"]


def test_the_sectors_come_with_the_provenance_of_their_own_lines():
    """GT7 sends no sectors, so a split is the app's own claim and every
    surface that draws one says whose."""
    body = compose_practice(_practising(sectors=_sectors()))
    assert [s["value"] for s in body["sectors"]] \
        == ["38.412", "41.100", "25.388"]
    assert body["sectors"][1]["sub"] == "best"
    assert body["sectors"][0]["sub"] == "+0.212"
    assert "thirds of the lap - not GT7's" in body["sector_note"]


def test_a_lap_with_no_sectors_says_why_rather_than_drawing_three_dashes():
    body = compose_practice(_practising(
        sectors=_sectors(times_ms=None, why="no lap completed yet")))
    assert [s["value"] for s in body["sectors"]] == ["--.---"] * 3
    assert "no lap completed yet" in body["sector_note"]


def test_a_lamp_the_app_could_not_read_is_not_a_lamp_reading_no():
    """`abs_light(None)` is "no reading" and `abs_light(False)` is "no lock",
    and both draw unlit - so without the flag the page shows a missing reading
    as a measured negative (rule 3). The phone carries the same flag from the
    same list, which is why it is imported rather than copied."""
    unread = compose_practice(_practising(
        abs_setting=None, front_lock=None, tcs_active=None, wet=None))
    assert all(lamp["unread"] for lamp in unread["lights"]), unread["lights"]
    read = compose_practice(_practising(
        abs_setting="Default", front_lock=False, tcs_active=False, wet="dry"))
    assert not any(lamp["unread"] for lamp in read["lights"]), read["lights"]


def test_the_face_carries_where_each_figure_came_from():
    """Rule 5, and the reason `Block` carries a register at all: a lap the car
    drove and a lap nobody drove were three identical white numbers in a row
    until the surfaces started marking them."""
    body = compose_practice(_practising())
    assert [face["register"] for face in body["faces"]] == ["measured"] * 3
    blank = compose_practice(_practising(last_lap_ms=None, file_best_ms=None,
                                         delta_file_s=None))
    assert [face["register"] for face in blank["faces"]] == ["absent"] * 3
    # A refusal says why, as every dash on this programme's screens does.
    assert blank["faces"][2]["sub"]


# --------------------------------------------------------------- the wiring


class _Server:
    def __init__(self, tablet=True):
        self._tablet, self.published = tablet, []

    def live(self, page="strip"):
        return self._tablet if page == "tablet" else True

    def last_client_of(self, page="strip"):
        return "10.0.0.9"

    def publish(self, body, page="strip"):
        self.published.append((page, body))


def _controller(race=None):
    from pitcrew.controller import PitCrewController

    ctl = PitCrewController.__new__(PitCrewController)
    ctl.race = race
    return ctl


def test_the_controller_hands_the_tablet_the_practice_board():
    """It short-circuited to `compose(None)` on anything that was not a race,
    which is what put a cover on the screen for the whole of practice."""
    ctl, server = _controller(), _Server()
    assert ctl._publish_tablet(server, _practising()) is True
    (page, body), = server.published
    assert page == "tablet" and body["kind"] == "practice"
    # The buttons still read the app's state back, as they did under the
    # cover: George off is meant to work with no race running at all.
    assert body["controls"]["racing"] is False


def test_a_race_still_gets_the_field_and_never_the_practice_face():
    from pitcrew.race import calls as C

    class Race:
        running = True
        state = C.RaceState()

        def field_view(self):
            from pitcrew.race.field import FieldView

            return FieldView(why="under test")

    ctl, server = _controller(Race()), _Server()
    assert ctl._publish_tablet(server, _practising()) is True
    (_page, body), = server.published
    assert body["kind"] == "race"


def test_a_board_the_tablet_was_not_given_is_still_no_session():
    """The signature grew a default so the race path and every existing
    caller are unchanged; without a board there is nothing to draw and the
    page is told so rather than shown the last session's numbers (rule 11)."""
    ctl, server = _controller(), _Server()
    assert ctl._publish_tablet(server) is True
    (_page, body), = server.published
    assert body["idle"] is True


def test_the_practice_payload_is_drawn_and_not_merely_published():
    """**A figure the page never reads is a figure rendered nowhere** - this
    codebase's own recorded defect family, found five times on 18 Sep in the
    speech path. The page is a dumb renderer, so every key the composer emits
    has to appear in it; a key renamed on one side only would otherwise ship
    green and draw nothing.
    """
    page = PAGE.read_text(encoding="utf-8")
    body = compose_practice(_practising(sectors=_sectors()))
    for key in body:
        if key in ("v", "idle"):
            continue
        assert f'"{key}"' in page or f".{key}" in page, key
    # And the containers the practice face fills are all in the markup.
    for node in ("p-faces", "p-tyres", "p-tyrecap", "p-sectors", "p-secnote",
                 "p-lights"):
        assert f'id="{node}"' in page, node


@pytest.mark.parametrize("field", ["state", "gap_tone"])
def test_every_corner_carries_the_two_marks_the_page_inks_from(field):
    for tyre in compose_practice(_practising())["tyres"]:
        assert tyre[field], tyre
