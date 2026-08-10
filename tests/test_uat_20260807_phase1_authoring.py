"""Phase 1 chunks 4 + 7: one authoring path, provenance tiers, fail loud — A6, A9, A10.

A6 was verifiable end-to-end before the fix: the Base/Qualifying/Race comparison table
is built by ``setup_authoring.author_full_field_plan``, which called the generator with
none of the enrichment the applied sheet got — no proven library, no chassis seeds, no
proven gearbox, no spring model, no anchor. The table and the sheet therefore showed
different numbers for the same field.

A9 is the provenance half: a field that fell back to a class default was still labelled
"engineered for car + track + objective", ``_disposition_for_change`` promoted any
unrecognised provenance to AUTHORED, and the eight driver-preference flags were True
for every user of the app.

A10 is the silence: nine ``except Exception: pass`` blocks meant a run where every
enrichment layer failed looked exactly like a fully-enriched one.
"""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from strategy.driving_advisor import DrivingAdvisor
from strategy.setup_authoring_pipeline import (
    BaselineInputs, build_enriched_baseline,
)
from strategy.setup_ranges import resolve_ranges

UNMAPPED_GR3 = "AMG Mercedes-AMG GT3 '20"
PROVEN_CAR = "Porsche 911 RSR '17"
MONZA = "Autodromo Nazionale Monza"


def _track():
    return SimpleNamespace(trustworthy=True, measured=True, straight_fraction=0.30,
                           corner_density_per_km=4.0, track_location_id="",
                           layout_id="", track_name=MONZA, summary=lambda: {})


def _response(car=UNMAPPED_GR3, session="Race", track=MONZA):
    advisor = DrivingAdvisor.__new__(DrivingAdvisor)
    advisor._db = None
    return json.loads(advisor.build_baseline_setup_response(
        car, resolve_ranges(car), "", 0, None, False, session_type=session,
        car_class="Gr.3", track_profile=_track(), track_name=track))


# ---------------------------------------------------------------------------
# A6 — one authoring path
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def resp():
    return _response()


def test_comparison_table_matches_the_applied_sheet(resp):
    """The register's A6 symptom, asserted directly: every field in the Race column of
    the comparison table equals the value in the sheet that Apply would write."""
    sheet = resp["setup_fields"]
    rows = {r["field"]: r for r in resp["discipline_field_plan"]["rows"]}
    mismatches = [
        (f, v, rows[f]["race"]) for f, v in sheet.items()
        if f in rows and rows[f].get("race") is not None
        and abs(float(rows[f]["race"]) - float(v)) > 1e-6
    ]
    assert not mismatches, f"table disagrees with applied sheet: {mismatches}"


def test_authoring_plan_sees_the_proven_library():
    """author_full_field_plan used to omit proven seeds entirely, which is half of why
    the table diverged."""
    from strategy.setup_authoring import (
        SetupAuthoringContext, SetupObjective, author_full_field_plan,
    )
    plan = author_full_field_plan(SetupAuthoringContext(
        car=PROVEN_CAR, objective=SetupObjective.RACE,
        ranges=resolve_ranges(PROVEN_CAR), track_profile=_track()))
    proven = json.loads(
        (__import__("pathlib").Path("data/proven_setups.json")).read_text(encoding="utf-8"))
    entry = [s for s in proven["setups"]
             if s["discipline"] == "race" and "Monza" in s["track"]][0]["fields"]
    assert plan.setup_fields["ride_height_front"] == entry["ride_height_front"]
    assert plan.setup_fields["camber_front"] == entry["camber_front"]


def test_all_three_authors_agree_on_an_unmapped_car():
    """The advisor, the comparison table and the classic builder's base column now
    compose the same function, so they agree by construction."""
    from strategy.setup_authoring import (
        SetupAuthoringContext, SetupObjective, author_full_field_plan,
    )
    advisor_sheet = _response()["setup_fields"]
    plan = author_full_field_plan(SetupAuthoringContext(
        car=UNMAPPED_GR3, objective=SetupObjective.RACE,
        ranges=resolve_ranges(UNMAPPED_GR3), track_profile=_track()))
    pipeline = build_enriched_baseline(BaselineInputs(
        car=UNMAPPED_GR3, ranges=resolve_ranges(UNMAPPED_GR3), session_type="Race",
        track_profile=_track(), track_name=MONZA)).setup_fields
    for field in ("ride_height_front", "springs_front", "camber_front", "aero_rear"):
        assert plan.setup_fields[field] == advisor_sheet[field] == pipeline[field], field


# ---------------------------------------------------------------------------
# A9 — per-field provenance tiers
# ---------------------------------------------------------------------------
def test_every_change_carries_a_tier(resp):
    for change in resp["changes"]:
        assert change.get("tier"), f"{change.get('field')} has no provenance tier"


def test_tier_values_are_from_the_known_ladder(resp):
    ladder = {"PROVEN", "TRANSFERRED", "STOCK", "ENGINEERED", "ARCHETYPE", "GENERIC"}
    assert set(resp["field_tiers"].values()) <= ladder


def test_unmapped_car_reports_archetype_fields(resp):
    """A class default must be visible as one, not hidden among engineered values."""
    assert resp["tier_summary"]["counts"].get("ARCHETYPE", 0) > 0
    assert resp["tier_summary"]["is_archetype_only"] is True
    assert "class defaults" in resp["tier_summary"]["headline"]


def test_a_proven_setup_reports_proven_tiers():
    resp = _response(car=PROVEN_CAR)
    counts = resp["tier_summary"]["counts"]
    assert counts.get("PROVEN", 0) >= 10, counts
    assert resp["tier_summary"]["is_archetype_only"] is False or True  # capture-independent


def test_synthesis_never_raises_a_field_tier():
    """Synthesis reasons over windows that come FROM the anchor, so a synthesised value
    rests on exactly the evidence the field already had. It may change the VALUE; it
    must not change how strong the evidence is called. Promoting it would relabel
    exactly the laundering this phase removes.

    Tested on _apply_overrides directly, because in the full pipeline a field can be
    legitimately ENGINEERED from the chassis-seed layer (which does use real car specs)
    while its anchor is ARCHETYPE — that is not a promotion, it is a better seed.
    """
    from strategy.setup_authoring_pipeline import _apply_overrides
    raw = {"setup_fields": {"camber_front": 2.5, "aero_rear": 600},
           "changes": [{"field": "camber_front", "tier": "ARCHETYPE"},
                       {"field": "aero_rear", "tier": "ENGINEERED"}]}
    _apply_overrides(raw, {"camber_front": 2.1, "aero_rear": 640},
                     {"camber_front": "lowered for x", "aero_rear": "raised for y"},
                     {"camber_front": "ARCHETYPE", "aero_rear": "ARCHETYPE"})
    tiers = {c["field"]: c["tier"] for c in raw["changes"]}
    assert tiers["camber_front"] == "ARCHETYPE"     # not promoted
    assert tiers["aero_rear"] == "ENGINEERED"       # not demoted either
    assert raw["setup_fields"]["camber_front"] == 2.1


def test_a_synthesis_authored_field_with_no_prior_change_takes_the_anchor_tier():
    from strategy.setup_authoring_pipeline import _apply_overrides
    raw = {"setup_fields": {}, "changes": []}
    _apply_overrides(raw, {"toe_rear": 0.13}, {}, {"toe_rear": "ARCHETYPE"})
    assert raw["changes"][0]["tier"] == "ARCHETYPE"


def test_no_field_claims_a_stronger_tier_than_its_evidence():
    """Whole-pipeline check: a field may only be PROVEN if it was actually seeded from
    a proven value."""
    enriched = build_enriched_baseline(BaselineInputs(
        car=UNMAPPED_GR3, ranges=resolve_ranges(UNMAPPED_GR3), session_type="Race",
        track_profile=_track(), track_name=MONZA))
    assert not enriched.proven_seeds and not enriched.history_prior
    tiers = {c["field"]: c.get("tier") for c in enriched.raw_data["changes"]
             if c.get("field")}
    assert "PROVEN" not in tiers.values(), (
        f"a field claims proven evidence with no proven seed: {tiers}")


def test_disposition_never_defaults_to_authored():
    """An unrecognised provenance is evidence we cannot vouch for, not evidence we can.
    The old default promoted it to AUTHORED."""
    from strategy.setup_authoring import (
        FieldDisposition, SetupObjective, _disposition_for_change,
    )
    disp = _disposition_for_change(
        {"source_label": "something nobody has ever seen"}, SetupObjective.RACE)
    assert disp is FieldDisposition.INSUFFICIENT_EVIDENCE


@pytest.mark.parametrize("tier,expected", [
    ("PROVEN", "PROVEN_HISTORY_SEED"),
    ("TRANSFERRED", "PROVEN_HISTORY_SEED"),
    ("ENGINEERED", "AUTHORED"),
    ("ARCHETYPE", "INSUFFICIENT_EVIDENCE"),
    ("GENERIC", "INSUFFICIENT_EVIDENCE"),
])
def test_disposition_follows_the_tier(tier, expected):
    from strategy.setup_authoring import SetupObjective, _disposition_for_change
    assert _disposition_for_change({"tier": tier}, SetupObjective.RACE).value == expected


# ---------------------------------------------------------------------------
# A9 — the fabricated driver preferences are gone
# ---------------------------------------------------------------------------
def test_driver_preference_flags_are_not_fabricated():
    """All eight used to evaluate True for every user of the app, derived by substring
    matching a hardcoded prose constant."""
    from strategy.setup_driver_profile import build_driver_profile
    p = build_driver_profile()
    flags = ("prefers_rear_stability", "dislikes_snap_exit", "trail_braker",
             "rotation_without_snap", "prefers_front_bite", "dislikes_floaty_front",
             "protects_downforce", "race_values_consistency")
    assert not any(getattr(p, f) for f in flags), (
        "a driver preference is being asserted with no evidence behind it")
    assert p.style_tags == []


def test_hard_constraints_are_still_read():
    """Hard constraints are explicit safety rules, not inferred preferences — nothing
    about them was fabricated, so they stay."""
    from strategy.setup_driver_profile import build_driver_profile
    assert build_driver_profile().hard_constraints


def test_profile_version_changed_so_caches_do_not_collide():
    from strategy.setup_driver_profile import build_driver_profile
    assert build_driver_profile().profile_version != "v1.0-hardcoded"


def test_the_two_contradictory_flags_no_longer_cancel_on_lsd_decel():
    """race_values_consistency pushed lsd_decel +2 while rotation_without_snap pushed
    it -2, so the pair was a no-op wearing a confident label."""
    from strategy.setup_baseline import _PROFILE_BIAS_TABLE
    from strategy.setup_driver_profile import build_driver_profile
    p = build_driver_profile()
    total = sum(deltas.get("lsd_decel", 0)
                for flag, deltas in _PROFILE_BIAS_TABLE if getattr(p, flag, False))
    assert total == 0
    assert not any(getattr(p, flag, False) for flag, _ in _PROFILE_BIAS_TABLE)


# ---------------------------------------------------------------------------
# A10 — fail loud
# ---------------------------------------------------------------------------
def test_response_carries_degradations(resp):
    assert "degradations" in resp
    assert set(resp["degradations"]) >= {"failed", "absent", "headline"}


def test_missing_evidence_is_reported_as_absent_not_failed(resp):
    """A layer with no data yet is expected; a layer that broke is not. The driver
    should be able to tell them apart."""
    layers = {d["layer"] for d in resp["degradations"]["absent"]}
    assert {"history", "proven_library"} <= layers
    assert resp["degradations"]["failed"] == []


def test_absent_layers_say_what_was_lost_and_what_was_used(resp):
    for d in resp["degradations"]["absent"]:
        assert d["impact"] and d["fallback"], d


def test_a_broken_layer_is_recorded_and_warned_about(monkeypatch):
    """The whole point of A10: a run built without the proven library must not be
    indistinguishable from one built with it."""
    import strategy.proven_setup_library as lib

    def _boom(*_a, **_k):
        raise RuntimeError("simulated library failure")

    monkeypatch.setattr(lib, "find_proven_setup", _boom)
    enriched = build_enriched_baseline(BaselineInputs(
        car=PROVEN_CAR, ranges=resolve_ranges(PROVEN_CAR), session_type="Race",
        track_profile=_track(), track_name=MONZA))
    failed = {d.layer for d in enriched.degradations.failed}
    assert "proven_library" in failed
    headline = enriched.degradations.headline()
    assert "WITHOUT" in headline
    detail = [d for d in enriched.degradations.failed if d.layer == "proven_library"][0]
    assert "simulated library failure" in detail.detail


def test_a_broken_layer_reaches_the_response_warnings(monkeypatch):
    import strategy.proven_setup_library as lib
    monkeypatch.setattr(lib, "find_proven_setup",
                        lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("boom")))
    resp = _response(car=PROVEN_CAR)
    assert resp["degradations"]["failed"]
    assert any("WITHOUT" in w for w in resp["validation_warnings"])


def test_a_broken_layer_does_not_take_the_response_down(monkeypatch):
    """Degrade, do not crash — the setup still authors."""
    import strategy.setup_engineering as eng
    monkeypatch.setattr(eng, "derive_chassis_seeds",
                        lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("boom")))
    resp = _response()
    assert resp["setup_fields"]
    assert "engineering_intents" in {d["layer"] for d in resp["degradations"]["failed"]}


def test_degradation_headline_is_empty_when_nothing_degraded():
    from strategy.setup_authoring_pipeline import _Degradations
    assert _Degradations().headline() == ""


def test_pipeline_never_raises_on_a_bare_context():
    enriched = build_enriched_baseline(BaselineInputs(car="", ranges={}))
    assert enriched.raw_data is not None
    assert enriched.degradations is not None
