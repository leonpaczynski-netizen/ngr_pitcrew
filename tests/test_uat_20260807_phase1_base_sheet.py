"""Phase 1 chunk 8: a Base sheet, with Race and Qualifying as deltas from it.

The Garage offered only Race and Qualifying, so there was nowhere for a base setup to
live and no anchor from which the two disciplines are deltas. The driver had to build
a base setup on a tab labelled with a discipline they were not running, and three
sheets that looked identical could not be told apart from three sheets that WERE
identical.

Base is deliberately INERT for the live runtime. Selecting a discipline tab already
mutates the live session type (defect C5, a Phase 3 fix); adding a third tab without
this would have meant that opening the Garage to build a base setup asserted a
discipline the driver is not running.
"""
from __future__ import annotations

import pytest

from services.setup_service import BaselineResult, _deltas_from_base
from strategy.setup_sheet import DISCIPLINES, PURPOSE, normalise_discipline


# ---------------------------------------------------------------------------
# The sheet exists
# ---------------------------------------------------------------------------
def test_base_is_a_discipline_with_a_sheet():
    assert "base" in DISCIPLINES
    assert normalise_discipline("base") == "base"


def test_base_carries_no_discipline_bias():
    """The anchor must not lean toward either discipline — that is what makes the
    other two readable as deltas from it."""
    assert PURPOSE["base"] == "Practice"


def test_the_workspace_offers_all_three_tabs():
    from ui.components.setup_workspace import DISCIPLINE_NOTE, DISCIPLINES as UI_D
    keys = [k for k, _ in UI_D]
    assert keys == ["base", "qualifying", "race"]
    for key in keys:
        assert DISCIPLINE_NOTE.get(key), f"{key} tab has no explanation"


def test_the_base_note_explains_it_is_the_anchor():
    from ui.components.setup_workspace import DISCIPLINE_NOTE
    note = DISCIPLINE_NOTE["base"].lower()
    assert "delta" in note or "deltas" in note
    assert "platform" in note or "anchor" in note


# ---------------------------------------------------------------------------
# Deltas from base
# ---------------------------------------------------------------------------
def test_deltas_report_only_what_moved():
    deltas = _deltas_from_base({
        "base": {"arb_front": 5, "camber_front": 2.5, "aero_rear": 600},
        "race": {"arb_front": 5, "camber_front": 2.5, "aero_rear": 640},
        "qualifying": {"arb_front": 6, "camber_front": 2.9, "aero_rear": 600},
    })
    assert deltas["race"] == {"aero_rear": (600, 640)}
    assert set(deltas["qualifying"]) == {"arb_front", "camber_front"}


def test_a_field_missing_from_base_is_not_a_delta():
    """An absence is not a change."""
    deltas = _deltas_from_base({"base": {"arb_front": 5},
                                "race": {"arb_front": 5, "gear_1": 2.9}})
    assert deltas["race"] == {}


def test_no_base_means_no_deltas_rather_than_wrong_ones():
    assert _deltas_from_base({"race": {"arb_front": 5}}) == {}
    assert _deltas_from_base({}) == {}


def test_non_numeric_values_still_compare():
    deltas = _deltas_from_base({"base": {"tyre": "RM"}, "race": {"tyre": "RH"}})
    assert deltas["race"] == {"tyre": ("RM", "RH")}


def test_deltas_never_raise_on_junk():
    _deltas_from_base({"base": {"a": None}, "race": {"a": object()}})
    _deltas_from_base({"base": {"a": 1}, "race": "not a dict"})


def test_the_summary_names_what_changed():
    result = BaselineResult(ok=True, built=("base", "race"), deltas_from_base={
        "race": {"aero_rear": (600, 640), "lsd_accel": (30, 34)}})
    summary = result.delta_summary("race")
    assert "2 fields" in summary
    assert "aero_rear" in summary and "lsd_accel" in summary


def test_the_summary_says_so_when_nothing_changed():
    """Three sheets that look identical and three sheets that ARE identical must not
    be indistinguishable — that was the UAT complaint."""
    result = BaselineResult(ok=True, deltas_from_base={"race": {}})
    assert "identical to Base" in result.delta_summary("race")


def test_the_summary_truncates_a_long_list_honestly():
    fields = {f"field_{i}": (i, i + 1) for i in range(10)}
    result = BaselineResult(ok=True, deltas_from_base={"race": fields})
    summary = result.delta_summary("race")
    assert "10 fields" in summary
    assert "and 4 more" in summary


# ---------------------------------------------------------------------------
# Base is inert for the live runtime
# ---------------------------------------------------------------------------
def test_selecting_base_does_not_push_a_session_mode():
    """Defect C5 is a Phase 3 fix, but adding a third tab must not make it worse:
    opening the Garage to build a base setup must not assert a discipline."""
    from ui.live_shell_bridge import LiveShellBridge

    pushed: list = []

    class _Stub:
        _discipline = "race"
        _push_practice_mode = lambda self, d: pushed.append(d)
        _apply_qualifying_compound = lambda self: None
        _feed_garage = lambda self: None
        _shell = None

    stub = _Stub()
    LiveShellBridge._on_discipline(stub, "base")
    assert stub._discipline == "base"
    assert pushed == [], f"selecting Base pushed a live mode: {pushed}"


@pytest.mark.parametrize("discipline", ["race", "qualifying"])
def test_selecting_a_real_discipline_still_pushes_its_mode(discipline):
    from ui.live_shell_bridge import LiveShellBridge

    pushed: list = []

    class _Stub:
        _discipline = "base"
        _push_practice_mode = lambda self, d: pushed.append(d)
        _apply_qualifying_compound = lambda self: None
        _feed_garage = lambda self: None
        _shell = None

    stub = _Stub()
    LiveShellBridge._on_discipline(stub, discipline)
    assert pushed == [discipline]


def test_an_unknown_discipline_still_falls_back_to_race():
    from ui.live_shell_bridge import LiveShellBridge

    class _Stub:
        _discipline = "base"
        _push_practice_mode = lambda self, d: None
        _apply_qualifying_compound = lambda self: None
        _feed_garage = lambda self: None
        _shell = None

    stub = _Stub()
    LiveShellBridge._on_discipline(stub, "nonsense")
    assert stub._discipline == "race"
