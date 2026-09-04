"""Cutting a lap into three, and the four ways it must refuse to.

GT7 sends no sector times and no sector lines, so every number here is the
app's own claim laid on a distance channel that is itself integrated from
speed. That makes the refusals the load-bearing half of the module: a sector
taken against boundaries that are somewhere else on the road is not an
imprecise number, it is a confident number about a different piece of track.

The one that cost a rebuild is the **out-lap**. Its frames begin while the car
is still sitting in the box and GT7's lap time begins at the line, so the two
clocks have different origins - while the distance channel still integrates to
within the circuit's tolerance and passes every length check. Measured across
the archive an out-lap's frames span a median 1.34x its stated lap time. The
first version of this module read S3 as 5.58 s on a 95 s lap.
"""
from __future__ import annotations

import pytest

from pitcrew.analysis.corner_model import Corner, CornerModel
from pitcrew.analysis.lap_sectors import (
    SECTOR_LINES,
    SOURCE_LANDMARK,
    SOURCE_THIRDS,
    model_for,
    read,
)

CIRCUIT = 6000.0
LAP_MS = 120_000


def _frames(length_m: float = CIRCUIT, lap_ms: int = LAP_MS,
            count: int = 600, jump_at: int | None = None):
    """One lap at a constant speed, so distance and time are proportional.

    Constant speed makes every expectation arithmetic: a line at 2,000 m of a
    6,000 m lap is crossed at exactly a third of a 120 s lap.
    """
    out, x = [], 0.0
    step = length_m / (count - 1)
    for index in range(count):
        if jump_at is not None and index == jump_at:
            x += 300.0
        out.append({"t_ms": round(index * lap_ms / (count - 1)),
                    "lap_distance_m": round(index * step, 2),
                    "pos_x": x, "pos_y": 0.0, "pos_z": 0.0})
        x += step
    return out


def _model(source=SOURCE_LANDMARK, lines=(2000.0, 4000.0)):
    from pitcrew.analysis.lap_sectors import SectorModel
    return SectorModel(circuit_key="test", source=source,
                       lap_length_m=CIRCUIT, lines_m=lines)


# --------------------------------------------------------------- the cutting

def test_three_sectors_sum_to_the_lap_time_exactly():
    """The one property the rack cannot do without.

    S3 is taken back from GT7's own lap time rather than from the frames' own
    span, so the three reconcile with the number sitting beside them on the
    same row. A rack whose sectors do not add up to its lap time is a rack
    nobody can read.
    """
    found = read(_frames(), LAP_MS, _model())
    assert found.measured
    assert sum(found.times_ms) == LAP_MS


def test_lines_at_a_third_and_two_thirds_cut_a_constant_lap_evenly():
    found = read(_frames(), LAP_MS, _model())
    assert found.times_ms == pytest.approx((40_000, 40_000, 40_000), abs=200)


def test_the_stamp_records_the_lines_the_lap_was_cut_against():
    """Without it a lap measured against boundaries that have since moved
    cannot be told from a fresh one, and the rack silently mixes two
    definitions of `S2` in one column."""
    found = read(_frames(), LAP_MS, _model())
    assert found.stamp == "test:landmark:2000/4000"


def test_a_lap_shorter_than_the_circuit_is_still_cut_at_the_same_fractions():
    """The integration runs 0.2-0.9% short, systematically. The lines are
    fractions of the lap's own length for that reason - the same correction
    `distance.anchor` makes, without carrying a scale factor around."""
    found = read(_frames(length_m=CIRCUIT * 0.994), LAP_MS, _model())
    assert found.measured
    assert found.times_ms == pytest.approx((40_000, 40_000, 40_000), abs=200)


# -------------------------------------------------------------- the refusals

def test_an_out_lap_is_refused_because_the_two_clocks_start_in_different_places():
    """The defect this module was rebuilt for.

    The frames run 160 s - the car sat in the box, then crawled down the pit
    lane - while GT7 calls the lap 120 s because it starts timing at the line.
    Distance still integrates to the full circuit, so no length check sees
    anything wrong. Taking S3 as `lap_time - t(S2)` across those two origins
    returned a five-second final sector on a ninety-five-second lap.
    """
    frames = _frames(lap_ms=160_000)
    found = read(frames, LAP_MS, _model())
    assert not found.measured
    assert found.times_ms == (None, None, None)
    assert "do not start in the same place" in found.refused


def test_a_teleport_refuses_the_whole_lap_not_just_the_sector_it_landed_in():
    """Speed reads zero through a reset, so the integrated length stays
    plausible and every boundary after the jump is on a different axis."""
    found = read(_frames(jump_at=200), LAP_MS, _model())
    assert not found.measured
    assert "jumped" in found.refused


def test_a_lap_that_did_not_measure_the_circuit_is_refused():
    found = read(_frames(length_m=CIRCUIT * 0.5), LAP_MS, _model())
    assert not found.measured
    assert "the lines are elsewhere" in found.refused


def test_a_lap_with_no_distance_channel_is_refused_rather_than_zeroed():
    frames = [{**frame, "lap_distance_m": None} for frame in _frames()]
    found = read(frames, LAP_MS, _model())
    assert not found.measured
    assert found.refused


def test_no_model_means_no_sectors_and_says_so():
    """A circuit with no length in the catalogue has no axis to put a
    boundary on, and a boundary in the wrong place is worse than none."""
    found = read(_frames(), LAP_MS, None)
    assert not found.measured
    assert found.refused


def test_a_lap_carrying_no_time_is_refused():
    """A phantom fragment has its time cleared by the controller, and a
    sector taken back from a zero lap time is a negative number."""
    found = read(_frames(), 0, _model())
    assert not found.measured


def test_a_refusal_is_never_a_zero():
    """CLAUDE.md rule 3. A zero sector would be averaged, ranked and fitted
    against by everything downstream."""
    for found in (read(None, LAP_MS, _model()),
                  read(_frames(), 0, _model()),
                  read(_frames(jump_at=100), LAP_MS, _model())):
        assert found.times_ms == (None, None, None)
        assert found.refused


# ------------------------------------------------------------------ the model

def test_a_circuit_in_the_catalogue_gets_its_own_lines():
    key = "circuit-de-spa-francorchamps-full-course"
    model = model_for(key, 7044.0)
    assert model.source == SOURCE_LANDMARK
    assert model.lines_m == tuple(SECTOR_LINES[key]["lines_m"])


def test_a_circuit_with_no_entry_falls_to_thirds_and_declares_it():
    model = model_for("somewhere-nobody-has-measured", 6000.0)
    assert model.source == SOURCE_THIRDS
    assert model.lines_m == (2000.0, 4000.0)
    assert "thirds" in model.note.lower()


def test_thirds_snap_out_of_a_corner_they_would_have_split():
    """A cut landing mid-corner puts the entry in one sector and the exit in
    the next, so the two move in opposite directions every time he changes his
    line through it. The cut goes to the nearer edge, whichever that is.
    """
    corners = CornerModel(
        model_id="test", version=1, source="auto-segment", lap_length_m=6000.0,
        corners=(Corner(id="T1", name="Turn 1",          # cut at 2,000 is
                        start_m=1990.0, apex_m=2020.0,   # 10 m past the entry
                        end_m=2100.0),                   # and 100 m from exit
                 Corner(id="T2", name="Turn 2",          # cut at 4,000 is
                        start_m=3880.0, apex_m=3930.0,   # 20 m short of exit
                        end_m=3980.0)))
    model = model_for("unknown", 6000.0, corners)
    assert model.lines_m == (1990.0, 3980.0)


def test_a_corner_too_far_from_the_cut_does_not_pull_it():
    """Snapping is a nudge, not a search. Beyond the reach the honest
    boundary is the arithmetic one where it fell."""
    corners = CornerModel(
        model_id="test", version=1, source="auto-segment", lap_length_m=6000.0,
        corners=(Corner(id="T1", name="Turn 1",
                        start_m=100.0, apex_m=140.0, end_m=190.0),))
    model = model_for("unknown", 6000.0, corners)
    assert model.lines_m == (2000.0, 4000.0)


@pytest.mark.parametrize("edges", [
    (0.0, 10.0), (1990.0, 2100.0), (2000.0, 2000.0), (3950.0, 4050.0),
    (1900.0, 4100.0), (2100.0, 2110.0), (5990.0, 6000.0),
])
def test_the_cuts_always_come_back_in_order(edges):
    """The invariant, rather than the branch that guards it.

    That fallback cannot fire at three sectors and a 4% reach - the cuts start
    a third of a lap apart and can close by at most 8% of one - so a test that
    claimed to exercise it would be asserting against a branch nothing can
    reach. What is worth pinning is the property the guard is there to keep,
    across corner layouts that put an edge everywhere awkward.
    """
    corners = CornerModel(
        model_id="test", version=1, source="auto-segment", lap_length_m=6000.0,
        corners=(Corner(id="T1", name="Turn 1", start_m=edges[0],
                        apex_m=(edges[0] + edges[1]) / 2, end_m=edges[1]),))
    lines = model_for("unknown", 6000.0, corners).lines_m
    assert 0 < lines[0] < lines[1] < 6000.0


def test_no_circuit_length_means_no_model_at_all():
    assert model_for("anywhere", None) is None
    assert model_for(None, 6000.0) is None


def test_the_meta_declares_the_source_the_way_the_corner_model_does():
    model = model_for("autodromo-nazionale-monza-full-course", 5746.9)
    meta = model.as_meta()
    assert meta["source"] == SOURCE_LANDMARK
    assert meta["sectors"] == 3
    assert len(meta["linesM"]) == 2
    assert meta["note"]


def test_every_catalogue_entry_is_ordered_and_inside_a_plausible_lap():
    """A hand-edited catalogue is the one place a typo lands silently: two
    numbers the wrong way round still produce three sectors, two of them
    negative, on every lap at that circuit."""
    for key, entry in SECTOR_LINES.items():
        lines = entry["lines_m"]
        assert len(lines) == 2, key
        assert 0 < lines[0] < lines[1], key
        assert entry["source"] in {"timing-line", "landmark", "thirds"}, key
        assert entry.get("note"), key


def test_an_accepted_lap_carries_the_ratio_that_admitted_it():
    """CLAUDE.md rule 10, the right way round: **log the accepts**, not only
    the refusals. The span ratio is the bar, and a lap admitted at 0.966 while
    the population sits at 0.9987 has its whole frame deficit inside S1 -
    invisible from the logs unless the accept carries the number."""
    found = read(_frames(), LAP_MS, _model())
    assert found.measured
    assert found.span_ratio == pytest.approx(1.0, abs=0.001)


def test_a_refused_lap_carries_no_ratio_to_be_mistaken_for_a_reading():
    assert read(_frames(jump_at=100), LAP_MS, _model()).span_ratio is None


# --------------------------------------------------- the gate's own edges

@pytest.mark.parametrize("ratio,admitted", [
    (1.000, True),
    (0.995, True),
    (0.991, True),
    (0.985, False),      # the band the old 0.95 bound let through
    (0.966, False),      # the worst of the seven laps it admitted
    (1.005, True),
    (1.020, False),
])
def test_the_span_gate_is_pinned_at_its_own_edges(ratio, admitted):
    """**The bound itself, not just laps far outside it.**

    Every refusal test above sits at 1.33 or 0.5 - refused by the old 0.95
    bound and the new 0.99 alike - so tightening the constant, the change with
    the largest data footprint in this work, was pinned by nothing. Reverting
    it left the whole suite green.
    """
    # A lap whose frames span `ratio` of the time GT7 claims for it.
    found = read(_frames(lap_ms=int(LAP_MS * ratio)), LAP_MS, _model())
    assert found.measured is admitted


def test_a_short_span_is_refused_because_the_deficit_lands_inside_S1():
    """`marks` starts at 0, so it assumes the first captured frame IS the
    crossing. Frames missing from the START of a lap make every crossing read
    early and put the whole offset inside S1 - while S3 absorbs it back, so
    the three still sum to the lap time and nothing looks wrong."""
    found = read(_frames(lap_ms=int(LAP_MS * 0.97)), LAP_MS, _model())
    assert not found.measured
    assert "do not start in the same place" in found.refused
