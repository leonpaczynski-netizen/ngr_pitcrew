"""What the pack covers, measured against a real race and the pack on disk.

Bathurst, 14 Sep 2026: 32 of the 46 lines the engineer said missed the pack
and were synthesised live - a pause before each and a second voice. Three
causes, one test group each: a decomposition bug, families nobody declared,
and a rendered pack older than the manifest it was rendered from.
"""
from __future__ import annotations

import json

import pytest

from pitcrew.engineer import phrase_manifest as manifest
from pitcrew.engineer import voice as voice_module

# The lines said that night, from `race_revisions` (race_run_id 21), less the
# three that stay live on purpose - two rival stops, whose names no clip can
# hold, and the rejoin call's two-number clause - and "Two to go. On the
# clock.", whose second sentence is being removed from the call.
BATHURST = (
    "Green, green, green. 20 laps. No notes for this circuit. "
    "I'm running on the model.",
    "You're back on it. About 9 seconds off the road.",
    "Lap 1 is out. You stopped on it.",
    "P11 of 13. You've lost a place.",
    "P10 of 13. You've made a place.",
    "Lap 3. 18 laps to go. P10. Fuel good to the stop.",
    "RR 11 percent.",
    "8 laps to the stop.",
    "P9 of 13. You've made 2 places.",
    "6 laps to the stop.",
    "Box in 2 laps. Stop 1. The regulations need a stop.",
    "Box this lap. RS on. The regulations need a stop. "
    "Fuel to 67 litres - 8 laps after the box.",
    "Fuel to 67 litres. 8 laps to the flag, at this race's burn.",
    "Go. 66 litres aboard.",
    "P11 of 13.",
    "Lap 16 is out. That cost you 32 seconds against your pace.",
    "Lap 18. 3 laps to go. P12. Fuel good to the flag.",
    "Save 0.7 litres a lap to make the flag. "
    "You're 0.1 laps short on current burn.",
)


def test_a_position_call_with_its_reason_plays_from_its_pieces():
    """The shape was only tried on a whole line, so with a reason behind it
    "P11 of 13." went to the generic split - which refuses the 11 in "P11"
    and asked for a clip called "P11 of"."""
    assert manifest.segments_for("P11 of 13. You've lost a place.") == (
        "P11", "of 13.", "You've lost a place.")
    assert manifest._decompose("P9 of 13. You've made 2 places.") == (
        "P9", "of 13.", "You've made 2 places.")


def test_a_position_out_of_range_is_a_miss_not_a_wrong_cut():
    segments = manifest.segments_for("P40 of 13. You've lost a place.")
    clips = set(manifest.clips())
    assert not all(name in clips for name in segments)
    assert "P40 of" not in segments


def test_a_fuel_line_plays_the_reference_it_said():
    """The shape played the answer's sampled tail - "to the stop" - whatever
    the line said, so "to the flag" was heard as the other journey."""
    assert manifest.segments_for("4.5 laps of fuel in hand to the flag.")[-1] \
        == "laps of fuel in hand to the flag."
    assert manifest.segments_for("4.5 laps of fuel in the tank.")[-1] \
        == "laps of fuel in the tank."
    assert manifest.segments_for("4.5 laps of fuel in hand to the stop.")[-1] \
        == "laps of fuel in hand to the stop."


@pytest.mark.parametrize("line", BATHURST)
def test_every_line_bathurst_heard_plays_from_declared_clips(line):
    clips = set(manifest.clips())
    segments = manifest.segments_for(line)
    assert segments, line
    missing = [name for name in segments if name not in clips]
    assert not missing, (line, missing)


def test_the_new_families_come_from_their_sources():
    """Driven through the functions that say them, so a reworded line is a
    re-rendered clip, not a copy that drifts."""
    assert "percent." in manifest.colour_data_lines()
    assert "RR" in manifest.colour_data_lines()
    assert "laps to the stop." in manifest.colour_data_lines()
    assert "You're back on it." in manifest.off_road_lines()
    assert "is out." in manifest.off_road_lines()
    assert "Go." in manifest.refuel_lines()
    assert "litres aboard." in manifest.refuel_lines()


def _rendered_packs():
    root = voice_module.PACK_ROOT
    if not root.is_dir():
        return []
    return [p for p in sorted(root.iterdir())
            if (p / voice_module.PACK_MANIFEST).is_file()]


@pytest.mark.skipif(not _rendered_packs(),
                    reason="no rendered voice pack on this machine - it is "
                           "gitignored, and rendered by "
                           "tools/render_voice_pack.py")
@pytest.mark.parametrize("folder", _rendered_packs(),
                         ids=lambda p: p.name)
def test_the_rendered_pack_holds_every_declared_clip(folder):
    """**The coverage tests checked the declared list, never the pack.**

    c6dc506 (13 Sep 2026) declared eleven clips - "Save", "litres a lap to
    make the flag.", "laps short on current burn." - and the pack on disk was
    rendered two days before it, so every one of them missed at Bathurst with
    every test green. Declared and rendered are two lists; this holds them
    together wherever a pack exists.
    """
    with (folder / voice_module.PACK_MANIFEST).open(encoding="utf-8") as fh:
        rendered = json.load(fh).get("clips") or {}
    missing = [line for line in manifest.clips() if line not in rendered]
    assert not missing, (
        f"{len(missing)} declared clips are not in the rendered pack "
        f"{folder.name} - re-run tools/render_voice_pack.py. "
        f"e.g. {missing[:6]}")
    absent = [entry["file"] for line, entry in rendered.items()
              if line in set(manifest.clips())
              and not (folder / entry["file"]).is_file()]
    assert not absent, f"{len(absent)} clips named but not on disk: {absent[:3]}"
