"""The box call a real race makes, played from the pack (critic 3, 11 Sep 2026).

`test_every_box_call_plays_from_the_pack` built its states with no fuel data,
so the box call carried no fuel figure - and no race with a measured burn
makes that call. With a burn it says "Box this lap. RS on. The regulations
need a stop. Fuel to 24 litres - 7 laps after the box.", and the peel stopped
at the stop's reason (a clip, but not peelable), the rest landed as one clause
holding two numbers, and `uncovered_reason` filed the whole call as a
declared gap. The engine plays from the pack only when every segment is
present, so the call he acts on at every stop was synthesised whole.

The critic's sweep: 588 box-now lines declared, 306 undeclared misses.
"""
from __future__ import annotations

import pytest

from pitcrew.engineer import phrase_manifest as manifest
from pitcrew.race.calls import BOX_NOW, BOX_SOON, RaceState, next_call

BOX_OPENERS = ("Box this lap.", "Box next lap.", "Box in ",
               "The stop is back on.")


def _plays(line: str) -> bool:
    clips = set(manifest.clips())
    segments = manifest.segments_for(line)
    return bool(segments) and all(name in clips for name in segments)


def _box_states():
    """Box calls as a race with a measured burn makes them: every tyre
    decision, every reason branch, the three fuel sentences."""
    reasons = (
        dict(mandatory_stops_left=1),                          # regulations
        dict(mandatory_stops_left=None),                       # on the plan
        dict(mandatory_stops_left=0, plan_binding_constraint="fuel"),
        dict(mandatory_stops_left=0, plan_binding_constraint="tyre"),
    )
    fuels = (
        dict(fuel_l=10.0, fuel_per_lap_l=3.0),                 # fuel to N
        dict(fuel_l=60.0, fuel_per_lap_l=3.0),                 # fuel is fine
        dict(fuel_l=2.0, fuel_per_lap_l=9.0),                  # fuel to full
    )
    for reason in reasons:
        for fuel in fuels:
            for tyres in (True, False, None):
                for code in ("RS", "RM", "IM", None):
                    for lap, end in ((12, 12), (11, 12), (10, 12), (14, 12)):
                        yield RaceState(
                            lap=lap, laps_total=20, stint_ends_on_lap=end,
                            fuel_capacity_l=100.0, next_compound=code,
                            next_tyres=tyres, next_stint_laps=8,
                            further_stop_planned=False, **reason, **fuel)


def test_every_box_call_with_a_fuel_figure_plays_from_the_pack():
    missed, declared = [], []
    for state in _box_states():
        call = next_call(state)
        if call is None or call.kind not in (BOX_NOW, BOX_SOON):
            continue
        spoken = call.spoken()
        if manifest.uncovered_reason(spoken):
            declared.append(spoken)
        elif not _plays(spoken):
            missed.append((spoken, manifest.segments_for(spoken)))
    assert not declared, f"{len(declared)} declared, e.g. {declared[:3]}"
    assert not missed, f"{len(missed)} missed, e.g. {missed[:3]}"


def test_a_box_call_is_never_a_declared_gap():
    """`test_every_declared_gap_is_one_of_the_two_named_ones` accepted any
    line whose reason said "numbers left", whatever kind of call it was. A
    box instruction is never allowed to be one. The undercut is the named
    exception: its reason carries the rival's name, which no clip can hold,
    and the engine plays a line from the pack only whole."""
    for line in manifest.race_call_examples():
        if not line.startswith(BOX_OPENERS):
            continue
        if "Undercut on" in line:
            continue
        assert manifest.uncovered_reason(line) is None, line


def test_the_pack_stays_within_budget_with_the_fuel_sentence_in_it():
    # 830 since 16 Sep 2026 - see `test_voice_pack.test_the_pack_stays_within_budget`.
    assert len(manifest.clips()) < 830
