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
    # **Through today's box ladder, not as heard.** That night lap 9 said
    # "Box in 2 laps." - the old ladder, a lap late (e9c7657). The same
    # crossing (plan in-lap 11, `laps_to_stop()` 2) now says "Box next lap.",
    # and lap 8's "Box in 3 laps." is the first "Box in N" the race can say.
    # "Box in 2 laps." is a sentence nothing can produce any more, so it is
    # not kept here to demand a clip for it.
    "Box in 3 laps. Stop 1. The regulations need a stop.",
    "Box next lap. Stop 1. The regulations need a stop.",
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


@pytest.mark.parametrize("line", (
    # Sardegna, 15 Sep 2026, race_run 24, 20:30:32 - as it should have been
    # said: the burn behind the 97 litres was practice's, not this race's.
    "Fuel to 97 litres. 17 laps after the box, at the practice burn.",
    "Fuel to 97 litres. 17 laps at the practice burn.",
))
def test_the_fill_that_names_the_practice_burn_plays_from_declared_clips(line):
    clips = set(manifest.clips())
    segments = manifest.segments_for(line)
    assert segments, line
    missing = [name for name in segments if name not in clips]
    assert not missing, (line, missing)


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


def test_the_place_calls_the_lane_explains_play_from_declared_clips():
    """The rival fix's sentences (14 Sep 2026): the stop's result, and the
    places cars in the lane made or took back - every wording
    `places_through_the_lane` has, behind a position, from the source."""
    from pitcrew.race.calls import (AFTER_YOUR_STOP, POSITION_MAX_STEP,
                                    places_through_the_lane)

    clips = set(manifest.clips())
    reasons = {AFTER_YOUR_STOP}
    for places in range(-POSITION_MAX_STEP, POSITION_MAX_STEP + 1):
        for lane in range(1, POSITION_MAX_STEP + 1):
            reasons.add(places_through_the_lane(places, lane))
    reasons.discard(None)
    assert "Not passes - 2 cars ahead boxed." in reasons
    for reason in sorted(reasons):
        line = f"P6 of 13. {reason}"
        segments = manifest.segments_for(line)
        assert segments[-1] == reason, (line, segments)   # whole, no join
        assert all(name in clips for name in segments), (line, segments)


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


def test_every_tablet_button_says_something_the_pack_can_play():
    """The three levers speak, and speech that misses the pack is a pause.

    **Measured 18 Sep 2026, the day after the buttons were built: not one of
    their sentences was in the manifest.** `_fuel_mode` only fires on a state
    carrying `fuel_mode_change` and no manifest state set one, so the whole
    beep-column family was live-synthesised; the pit button's three sentences
    were written inline in the controller, where the manifest - which builds
    its list by calling the code that speaks - could not reach them at all.

    The pit confirmation is the one that matters most: it is spoken even with
    George switched off (his call, 17 Sep), so it is the only sentence a
    silenced engineer still says, and it arrives while he is deciding whether
    he is in the lane this lap.
    """
    from pitcrew.race.calls import (
        BOX_CANCELLED,
        BOX_TOO_LATE,
        column_held_said,
        declared_box_said,
    )

    declared = set(manifest.clips())

    def playable(line):
        segments = manifest.segments_for(line)
        assert segments, f"{line!r} decomposes to nothing"
        return [clip for clip in segments if clip not in declared]

    for line in (BOX_CANCELLED, BOX_TOO_LATE):
        assert not playable(line), f"{line!r} is not in the pack"

    # The beep column, either way, and the reason naming a compound.
    for saving in (True, False):
        line = column_held_said(saving, "no RH target on the plan")
        assert line.startswith("Fuel-save beeps." if saving else "Full beeps.")
        assert not playable(line), f"{line!r} is not in the pack"

    # And the declared stop, whose fill is the box call's own sentence.
    for instruction in manifest._box_instructions():
        line = declared_box_said(instruction)
        assert not playable(line), f"{line!r} is not in the pack"


def test_the_held_column_reason_keeps_the_compound_in_capitals():
    """`capitalize()` lowercases the rest of the string, and the reason
    carries a compound code - "No rh target on the plan" is read as a word."""
    from pitcrew.race.calls import column_held_said

    said = column_held_said(True, "no RH target on the plan")
    assert "No RH target on the plan" in said


def test_the_beep_column_call_is_declared_for_every_shape():
    """Each branch of `_fuel_mode` reaches the pack, both frames.

    Rule 13 lives in the reason: "short to the flag" and "short to the stop"
    are figures ten laps apart, so they are two clips, not one with a suffix.
    """
    from pitcrew.race.calls import next_call

    declared = set(manifest.clips())
    spoken, missing = 0, []
    for state in manifest._fuel_mode_states():
        call = next_call(state)
        if call is None or call.kind != "fuel-mode":
            continue
        spoken += 1
        for clip in manifest.segments_for(call.spoken()) or ():
            if clip not in declared:
                missing.append((call.spoken(), clip))
    # **Every state, not a floor.** `race_call_lines` silently skips a state
    # whose call is outranked, so a floor lets two shapes stop producing
    # clips with this test and the missing list both still green.
    assert spoken == len(manifest._fuel_mode_states()), (
        f"only {spoken} of {len(manifest._fuel_mode_states())} fuel-mode "
        f"states still reach the call - one is being outranked")
    assert not missing, missing[:4]
    frames = {call.spoken() for call in
              (next_call(s) for s in manifest._fuel_mode_states())
              if call is not None and call.kind == "fuel-mode"}
    assert any("to the flag." in line for line in frames)
    assert any("to the stop." in line for line in frames)


def test_the_replanner_speaks_from_the_pack():
    """The strategy engine changing its mind is job 4's own output.

    Found by a critic on 18 Sep 2026: none of `Replan.call()` was declared, so
    "Recommend 2 stops from here." - the sentence with the largest consequence
    in the app - arrived after a pause, in a different voice.
    """
    from pitcrew.race.replan import RECOMMENDED, REPLANNING_OFF, Replan

    declared = set(manifest.clips())
    for stops in (None, 0, 1, 2, 3):
        said = Replan(verdict=RECOMMENDED, reason="fuel", stops=stops).call()
        assert said, f"{stops} stops says nothing"
        missing = [clip for clip in manifest.segments_for(said) or ()
                   if clip not in declared]
        assert not missing, f"{said!r} misses {missing}"
    assert not [clip for clip in manifest.segments_for(REPLANNING_OFF) or ()
                if clip not in declared]


def test_the_gauge_says_it_cannot_see_from_the_pack():
    """Its sibling `lost_the_gauge()` has been declared for weeks; this one
    never was, and it is the message that stops silence reading as fine."""
    from pitcrew.race.brief import (
        GAUGE_NOT_IN_FRAME,
        GAUGE_UNREADABLE,
        blind_note,
    )

    declared = set(manifest.clips())
    for note in (GAUGE_NOT_IN_FRAME, GAUGE_UNREADABLE):
        said = blind_note(note)
        assert not [clip for clip in manifest.segments_for(said) or ()
                    if clip not in declared], said


def test_the_qualifying_split_calls_never_pause_the_flyer():
    """They fire at a fraction of a flying lap - the one lap of the weekend
    that cannot be taken again - and the coach had no line in the pack."""
    from pitcrew.race.qualifying import QualifyingCoach

    declared = set(manifest.clips())
    coach = object.__new__(QualifyingCoach)
    checked = 0
    for noise in (None, 0.0):
        coach._noise_s = noise
        for tenths in range(1, 31):
            for delta in (tenths / 10.0, -tenths / 10.0):
                for early in (True, False):
                    said = coach._delta_call(delta, early=early)
                    missing = [clip for clip
                               in manifest.segments_for(said) or ()
                               if clip not in declared]
                    assert not missing, f"{said!r} misses {missing}"
                    checked += 1
    assert checked == 240, checked
    # And level, which is the most likely thing it says.
    coach._noise_s = None
    assert coach._delta_call(0.0, early=True) == "Level."
    assert "Level." in declared
