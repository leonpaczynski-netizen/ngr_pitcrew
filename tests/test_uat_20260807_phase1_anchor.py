"""Phase 1 chunks 2-3: anchor-based synthesis + proven setups survive — A1, A3.

The UAT verification criteria, as executable assertions:

  * a Gr.3 baseline lands in physically sane windows;
  * a proven setup survives synthesis unchanged;
  * an unmapped car is marked archetype-sourced and never labelled "engineered for
    car + track".

The regression these guard against is specific and was reproduced before the fix:
with a MEASURED track model, synthesis-primary authored ride height 108/97mm, springs
13.4/14.9Hz, camber 1.4 front against 4.8 rear, toe front -0.47 and LSD initial 48 on
a Gr.3 — by walking away from the midpoint of a generic slider range. Phase 0 closed
that gate for a track SEED only, so completing a track model brought it straight back.
"""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from strategy.driving_advisor import DrivingAdvisor
from strategy.setup_anchor import (
    TIER_ARCHETYPE, TIER_GENERIC, TIER_PROVEN, resolve_anchor,
)
from strategy.setup_ranges import resolve_ranges

_DATA = Path(__file__).resolve().parent.parent / "data"

UNMAPPED_GR3 = "AMG Mercedes-AMG GT3 '20"     # no curated range, no proven setup
PROVEN_CAR = "Porsche 911 RSR '17"
PROVEN_TRACK = "Autodromo Nazionale Monza"


def _measured_track():
    """A track model that has actually been recorded and accepted — the state that
    re-opens the synthesis-primary gate Phase 0 closed for seeds."""
    return SimpleNamespace(trustworthy=True, measured=True, straight_fraction=0.30,
                           corner_density_per_km=4.0, track_location_id="",
                           layout_id="", summary=lambda: {})


def _baseline(car, *, session="Race", track=PROVEN_TRACK, car_class="Gr.3"):
    advisor = DrivingAdvisor.__new__(DrivingAdvisor)
    advisor._db = None
    return json.loads(advisor.build_baseline_setup_response(
        car, resolve_ranges(car), "", 0, None, False,
        session_type=session, car_class=car_class,
        track_profile=_measured_track(), track_name=track))


def _proven(discipline="race", track=PROVEN_TRACK):
    for s in json.loads((_DATA / "proven_setups.json").read_text(encoding="utf-8"))["setups"]:
        if s["discipline"] == discipline and track.split()[-1] in s["track"]:
            return s
    raise AssertionError(f"no vetted {discipline} setup for {track}")


# ---------------------------------------------------------------------------
# A1 — the Gr.3 golden file
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def gr3():
    return _baseline(UNMAPPED_GR3)["setup_fields"]


def test_gr3_ride_height_is_physically_sane(gr3):
    """UAT criterion: 50-80mm. The old path produced 80/80 from NEUTRAL_SEEDS and
    108/97 from the midpoint walk."""
    for field in ("ride_height_front", "ride_height_rear"):
        assert 50 <= gr3[field] <= 80, f"{field} = {gr3[field]}"


def test_gr3_front_camber_is_at_least_rear_camber(gr3):
    """UAT criterion. The old path produced 1.4 front / 4.8 rear — the car turning in
    on its rear axle. Every vetted setup in the proven library runs front above rear."""
    assert gr3["camber_front"] >= gr3["camber_rear"], (
        f"camber {gr3['camber_front']} front / {gr3['camber_rear']} rear")


def test_gr3_springs_are_inside_the_class_band(gr3):
    """UAT criterion. GT7's spring slider is not real-world natural frequency: a Gr.3
    sits near 3.0-5.0 here, and the vetted RSR setups run 3.4-3.6. The midpoint walk
    produced 13.4/14.9 because half of a generic 1-20Hz range is 9.5Hz."""
    for field in ("springs_front", "springs_rear"):
        assert 3.0 <= gr3[field] <= 5.0, f"{field} = {gr3[field]}"


def test_gr3_aero_is_not_pinned_to_a_range_extreme(gr3):
    """UAT criterion. The old path produced aero_rear 800 against a curated ceiling of
    800 — a clamp artefact presented as a decision."""
    ranges = resolve_anchor(UNMAPPED_GR3, PROVEN_TRACK, "race")
    for field in ("aero_front", "aero_rear"):
        a = ranges.get(field)
        assert a.legal_low < gr3[field] < a.legal_high, (
            f"{field} = {gr3[field]} pinned to {a.legal_low}..{a.legal_high}")


def test_gr3_rear_downforce_is_not_below_front(gr3):
    assert gr3["aero_rear"] >= gr3["aero_front"]


def test_gr3_rides_with_rake(gr3):
    assert gr3["ride_height_rear"] >= gr3["ride_height_front"]


def test_gr3_toe_is_not_a_range_walk(gr3):
    """The old path produced toe_front -0.47 by walking 30% of a (-2, +2) range. Real
    Gr.3 toe lives within a few hundredths of zero."""
    assert -0.15 <= gr3["toe_front"] <= 0.10
    assert -0.05 <= gr3["toe_rear"] <= 0.25


def test_gr3_lsd_initial_is_not_a_range_walk(gr3):
    """The old path produced 48 out of a (0, 60) range. A Gr.3 runs 8-25."""
    assert 5 <= gr3["lsd_initial"] <= 30


def test_a_measured_track_no_longer_reopens_the_defect():
    """Phase 0 closed the gate for a track SEED. This asserts the fix survives the
    state Phase 0 did not cover — a completed, measured, accepted track model."""
    fields = _baseline(UNMAPPED_GR3)["setup_fields"]
    assert fields["springs_front"] < 6.0        # was 13.4
    assert fields["ride_height_front"] < 90     # was 108
    assert fields["camber_rear"] < 3.0          # was 4.8


# ---------------------------------------------------------------------------
# A1 — the anchor itself
# ---------------------------------------------------------------------------
def test_anchor_prefers_proven_over_class():
    proven = _proven("race")["fields"]
    a = resolve_anchor(PROVEN_CAR, PROVEN_TRACK, "race", proven_fields=proven)
    assert a.tier("ride_height_front") == TIER_PROVEN
    assert a.value("ride_height_front") == proven["ride_height_front"]


def test_anchor_falls_back_to_class_without_proven_data():
    a = resolve_anchor(UNMAPPED_GR3, PROVEN_TRACK, "race")
    assert a.tier("springs_front") == TIER_ARCHETYPE
    assert a.archetype == "gr3"


def test_generic_anchor_is_labelled_as_the_absence_of_a_position():
    """A legal midpoint must never present as an engineering decision."""
    a = resolve_anchor("A Car That Does Not Exist", "Nowhere", "race",
                       ranges={"made_up_field": (0, 1000)})
    fa = a.get("made_up_field")
    assert fa.tier == TIER_GENERIC
    assert fa.is_engineering_position is False
    assert "no data" in fa.source


def test_anchor_window_is_narrower_than_the_legal_range():
    """The second half of the A1 fix: the distance a move may travel is half the
    PREFERENCE band, not half the legal span."""
    a = resolve_anchor(UNMAPPED_GR3, PROVEN_TRACK, "race")
    fa = a.get("springs_front")
    assert fa.window_span < (fa.legal_high - fa.legal_low) / 2


def test_anchor_resolution_never_raises_on_garbage():
    a = resolve_anchor("", "", "", ranges={"x": (1,)}, history_prior={"y": "junk"},
                       proven_fields={"z": None})
    assert a.anchors == {} or all(v.value is not None for v in a.anchors.values())


# ---------------------------------------------------------------------------
# A3 — a proven setup survives synthesis unchanged
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("discipline,track", [
    ("race", "Autodromo Nazionale Monza"),
    ("qualifying", "Autodromo Nazionale Monza"),
    ("race", "Circuit de Spa-Francorchamps"),
    ("qualifying", "Circuit de Spa-Francorchamps"),
    ("race", "Watkins Glen International - Grand Prix"),
    ("qualifying", "Watkins Glen International - Grand Prix"),
])
def test_every_proven_setup_survives_the_full_pipeline_unchanged(discipline, track):
    """The register's A3: proven values entered via proven_seed_overrides but never
    reached context.working_windows, so the `w.preferred is not None` guard that is
    supposed to protect them never fired. Verified before the fix: the vetted
    RSR-at-Monza race entry was matched, seeded, and then overwritten."""
    entry = _proven(discipline, track)
    fields = _baseline(PROVEN_CAR,
                       session=("Race" if discipline == "race" else "Qualifying"),
                       track=entry["track"])["setup_fields"]
    mismatches = [
        (k, v, fields.get(k)) for k, v in entry["fields"].items()
        if fields.get(k) is None or abs(float(fields[k]) - float(v)) > 1e-9
    ]
    assert not mismatches, f"proven values overwritten: {mismatches}"


def test_proven_gearbox_ratios_survive_with_no_gear_count():
    """A vetted gear set tells us how many gears the car has. The shell reads
    num_gears from car_specs.json, which carries it for no car, so this arrived as 0
    and shipped the proven final drive with none of its six ratios attached."""
    entry = _proven("race")
    fields = _baseline(PROVEN_CAR, track=entry["track"])["setup_fields"]
    for gear in range(1, 7):
        key = f"gear_{gear}"
        if key in entry["fields"]:
            assert fields.get(key) == entry["fields"][key], key


def test_proven_spring_precision_is_not_rounded_away():
    """_round_for_field snaps springs to one decimal, turning the vetted 3.35Hz into
    3.4. A curated setup is the strongest evidence in the system; rounding it is not
    the generator's call."""
    entry = _proven("race")
    fields = _baseline(PROVEN_CAR, track=entry["track"])["setup_fields"]
    assert fields["springs_rear"] == entry["fields"]["springs_rear"]


def test_proven_ride_height_is_not_moved_by_the_boundary_guard():
    """_place_seed_in_range re-places a seed that hugs a range boundary. A proven
    value is not a generic seed and must be clamped, never re-placed — the guard was
    moving the vetted 63mm rear ride height to 62.57."""
    entry = _proven("race")
    fields = _baseline(PROVEN_CAR, track=entry["track"])["setup_fields"]
    assert fields["ride_height_rear"] == entry["fields"]["ride_height_rear"]


def test_synthesis_reports_the_proven_fields_it_kept():
    entry = _proven("race")
    resp = _baseline(PROVEN_CAR, track=entry["track"])
    sp = resp.get("synthesis_primary") or {}
    assert sp.get("kept_proven"), "no proven field reported as protected"
    assert not sp.get("applied"), (
        f"synthesis overrode proven fields: {sp.get('applied')}")


# ---------------------------------------------------------------------------
# A9 (partial) — an unmapped car must not claim to be engineered for that car
# ---------------------------------------------------------------------------
def test_unmapped_car_is_marked_archetype_sourced():
    resp = _baseline(UNMAPPED_GR3)
    anchors = ((resp.get("engineering_context") or {}).get("anchors")) or {}
    assert anchors.get("is_archetype_only") is True
    assert "class defaults" in anchors.get("headline", "")


def test_unmapped_car_fields_are_never_labelled_engineered_for_this_car():
    """Only ENGINEERED and above may carry 'engineered for car + track + objective'.
    A class default is a real starting position but it is not derived for this car."""
    from strategy.setup_baseline import _LABEL_ANCHOR, _LABEL_ENGINEERING
    resp = _baseline(UNMAPPED_GR3)
    anchored = [c for c in resp["changes"]
                if str(c.get("source_label")) == _LABEL_ANCHOR]
    assert anchored, "no field reported as class-anchored on an unmapped car"
    for change in anchored:
        assert change["source_label"] != _LABEL_ENGINEERING


def test_spring_fallback_no_longer_claims_to_be_engineered():
    """derive_spring_frequencies returns the flat NEUTRAL_SEEDS constants with an
    'insufficient data ... neutral fallback' reason when the car has no weight data,
    and those were written and then labelled as engineered for this car."""
    from strategy.setup_baseline import _LABEL_ENGINEERING
    resp = _baseline(UNMAPPED_GR3)
    springs = [c for c in resp["changes"]
               if c.get("field") in ("springs_front", "springs_rear")]
    assert springs
    for change in springs:
        if change["source_label"] == _LABEL_ENGINEERING:
            # Allowed only if the value genuinely differs from the neutral constant.
            from strategy.setup_baseline import NEUTRAL_SEEDS
            assert change["to"] != NEUTRAL_SEEDS[change["field"]], (
                f"{change['field']} is the neutral fallback but claims to be engineered")


# ---------------------------------------------------------------------------
# Physics invariants
# ---------------------------------------------------------------------------
def test_invariants_repair_inverted_camber():
    from strategy.setup_invariants import enforce_invariants
    result = enforce_invariants({"camber_front": 1.4, "camber_rear": 4.8})
    assert result.fields["camber_front"] >= result.fields["camber_rear"]
    assert result.corrections


def test_invariants_never_move_a_proven_value():
    """If the driver has validated a setup on track, the invariant is what is wrong."""
    from strategy.setup_invariants import enforce_invariants
    ctx = SimpleNamespace(anchor_set=SimpleNamespace(tier=lambda f: TIER_PROVEN),
                          working_windows={})
    result = enforce_invariants({"camber_front": 1.4, "camber_rear": 4.8}, ctx)
    assert result.fields["camber_front"] == 1.4
    assert result.fields["camber_rear"] == 4.8
    assert result.violations


def test_invariants_move_the_weaker_side():
    from strategy.setup_invariants import enforce_invariants
    tiers = {"camber_front": TIER_PROVEN, "camber_rear": TIER_ARCHETYPE}
    ctx = SimpleNamespace(anchor_set=SimpleNamespace(tier=tiers.get),
                          working_windows={})
    result = enforce_invariants({"camber_front": 2.4, "camber_rear": 4.8}, ctx)
    assert result.fields["camber_front"] == 2.4       # proven side untouched
    assert result.fields["camber_rear"] <= 2.4


def test_invariants_leave_a_valid_setup_alone():
    from strategy.setup_invariants import enforce_invariants
    entry = _proven("race")["fields"]
    result = enforce_invariants(dict(entry))
    assert not result.corrections
    assert not result.violations


def test_rake_invariant_does_not_fire_without_downforce():
    from strategy.setup_invariants import enforce_invariants
    result = enforce_invariants({"aero_rear": 0, "aero_front": 0,
                                 "ride_height_front": 120, "ride_height_rear": 110})
    assert result.fields["ride_height_rear"] == 110


def test_invariants_never_raise_on_junk():
    from strategy.setup_invariants import enforce_invariants
    for junk in ({}, {"camber_front": None}, {"camber_front": "x", "camber_rear": 2},
                 {"aero_rear": float("nan")}):
        enforce_invariants(junk)


# ---------------------------------------------------------------------------
# Status honesty (Phase 0's A8 fix must survive)
# ---------------------------------------------------------------------------
def test_low_confidence_baseline_still_reports_its_warning():
    resp = _baseline(UNMAPPED_GR3)
    assert resp["recommendation_status"] == "approved_with_warnings"
    assert any("Low-confidence" in w for w in resp["validation_warnings"])
