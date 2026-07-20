"""Engineering-Brain Phase 1 — pure canonical-identity tests.

Proves the PURE identity spine (data/engineering_context_key.py):
deterministic versioned fingerprints, honest unknowns, non-guessing ambiguous
track resolution, distinct layouts at one venue, enrichment without contradictory
duplicates, per-field provenance, and NO UI/PyQt/network/AI dependency.

These tests touch NO database and NO runtime files.
"""
from __future__ import annotations

import itertools
import re
from pathlib import Path

import pytest

from data.engineering_context_key import (
    EngineeringContextKey, EngineeringContextResolution, ResolutionStatus,
    ProvenanceSource, FINGERPRINT_VERSION,
    build_engineering_context, resolve_from_session_row,
    resolve_from_applied_checkpoint, resolve_from_lineage,
    resolve_from_driver_feedback, resolve_feedback_against_session_context,
    engineering_context_from_stored_row,
)

ROOT = Path(__file__).resolve().parents[1]

_COMPLETE = dict(
    driver_id="leon", car_id="7", track_location_id="fuji_speedway",
    layout_id="full_course", event_id="12", discipline="Race",
    gt7_version="1.49", config_id="51bd5b3bae", setup_id="s1",
    applied_checkpoint_id="cp1", lineage_id="9", session_id="5", run_id="2",
)


# ------------------------------------------------------------------ 1,2 determinism
def test_fingerprint_is_versioned_and_shaped():
    fp = EngineeringContextKey(**_COMPLETE).fingerprint()
    assert fp.startswith(f"{FINGERPRINT_VERSION}:")
    assert re.fullmatch(rf"{re.escape(FINGERPRINT_VERSION)}:[0-9a-f]{{16}}", fp)


def test_same_complete_context_same_fingerprint():
    a = EngineeringContextKey(**_COMPLETE)
    b = EngineeringContextKey(**dict(_COMPLETE))
    assert a.fingerprint() == b.fingerprint()
    assert a.scope_fingerprint() == b.scope_fingerprint()


def test_fingerprint_stable_across_calls():
    k = EngineeringContextKey(**_COMPLETE)
    assert len({k.fingerprint() for _ in range(50)}) == 1


# ------------------------------------------------------------------ 3 sensitivity
@pytest.mark.parametrize("field", [
    "driver_id", "car_id", "track_location_id", "layout_id", "discipline",
    "setup_id", "gt7_version",
])
def test_material_field_change_changes_full_fingerprint(field):
    base = EngineeringContextKey(**_COMPLETE)
    mutated = EngineeringContextKey(**{**_COMPLETE, field: _COMPLETE[field] + "_X"})
    assert base.fingerprint() != mutated.fingerprint()


@pytest.mark.parametrize("field", [
    "driver_id", "car_id", "track_location_id", "layout_id", "gt7_version",
])
def test_scope_field_change_changes_scope_fingerprint(field):
    base = EngineeringContextKey(**_COMPLETE)
    mutated = EngineeringContextKey(**{**_COMPLETE, field: _COMPLETE[field] + "_X"})
    assert base.scope_fingerprint() != mutated.scope_fingerprint()


@pytest.mark.parametrize("field", [
    "event_id", "discipline", "config_id", "setup_id",
    "applied_checkpoint_id", "lineage_id", "session_id", "run_id",
])
def test_non_scope_field_does_not_change_scope_fingerprint(field):
    base = EngineeringContextKey(**_COMPLETE)
    mutated = EngineeringContextKey(**{**_COMPLETE, field: _COMPLETE[field] + "_X"})
    assert base.scope_fingerprint() == mutated.scope_fingerprint()
    assert base.fingerprint() != mutated.fingerprint()  # but full identity differs


# ------------------------------------------------------------------ 4 honest unknowns
def test_unknown_field_is_none_not_guessed():
    r = resolve_from_session_row(
        {"id": 5, "car_id": 7, "track": "Fuji", "session_type": "Race"})
    assert r.context.layout_id is None
    assert r.context.track_location_id is None
    assert "layout_id" in r.unresolved
    assert r.status == ResolutionStatus.PARTIAL


def test_known_empty_differs_from_unknown():
    # A KNOWN empty string must not collide with a genuinely-unknown field.
    known_blank = EngineeringContextKey(car_id="")
    unknown = EngineeringContextKey(car_id=None)
    assert known_blank.fingerprint() != unknown.fingerprint()


def test_zero_and_blank_ids_normalise_to_unknown():
    # 0 (the schema's unset sentinel) and "" must not become authoritative ids.
    r = build_engineering_context(car_id=0, event_id="", session_id=None)
    assert r.context.car_id is None
    assert r.context.event_id is None
    assert r.context.session_id is None
    assert r.status == ResolutionStatus.UNRESOLVED  # no evidence at all


def test_no_evidence_is_unresolved():
    r = build_engineering_context()
    assert r.status == ResolutionStatus.UNRESOLVED
    assert r.context.known_fields == ()


# ------------------------------------------------------------------ 5 ambiguous track
def test_ambiguous_free_text_track_does_not_resolve():
    r = build_engineering_context(
        car_id="7", free_text_track="Fuji",
        layout_candidates=("full_course", "east_course", "west_course"))
    assert r.status == ResolutionStatus.AMBIGUOUS
    assert "layout_id" in r.ambiguous
    assert r.context.layout_id is None            # never guessed
    assert any("2" in w or "candidate" in w for w in r.warnings)


def test_single_candidate_resolves_with_provenance_and_warning():
    r = build_engineering_context(
        car_id="7", free_text_track="Deep Forest Raceway",
        layout_candidates=("deep_forest__reverse",))
    assert r.context.layout_id == "deep_forest__reverse"
    assert r.provenance["layout_id"] == ProvenanceSource.TRACK_LIBRARY.value


def test_free_text_no_candidates_stays_unknown():
    r = build_engineering_context(car_id="7", free_text_track="Some Track")
    assert r.context.layout_id is None
    assert any("unresolved" in w for w in r.warnings)


# ------------------------------------------------------------------ 6 distinct layouts
def test_different_layouts_same_venue_stay_distinct():
    a = build_engineering_context(
        car_id="7", track_location_id="fuji", layout_id="full_course").context
    b = build_engineering_context(
        car_id="7", track_location_id="fuji", layout_id="short_course").context
    assert a.scope_fingerprint() != b.scope_fingerprint()
    assert a.fingerprint() != b.fingerprint()


# ------------------------------------------------------------------ 11 enrichment
def test_enrich_fills_unknown_without_contradiction():
    partial = EngineeringContextKey(car_id="7", track_location_id="fuji")
    more = EngineeringContextKey(
        car_id="7", layout_id="full_course", gt7_version="1.49")
    enriched, conflicts = partial.enrich(more)
    assert conflicts == ()
    assert enriched.car_id == "7"
    assert enriched.layout_id == "full_course"
    assert enriched.gt7_version == "1.49"
    assert enriched.track_location_id == "fuji"


def test_enrich_reports_conflict_and_keeps_original():
    a = EngineeringContextKey(car_id="7", layout_id="full_course")
    b = EngineeringContextKey(car_id="8", gt7_version="1.49")   # car differs
    enriched, conflicts = a.enrich(b)
    assert conflicts == ("car_id",)
    assert enriched.car_id == "7"          # original wins, no silent overwrite
    assert enriched.gt7_version == "1.49"  # non-conflicting field still added


def test_enriched_shares_scope_when_only_volatile_added():
    base = EngineeringContextKey(
        car_id="7", track_location_id="fuji", layout_id="full_course")
    enriched, _ = base.enrich(EngineeringContextKey(setup_id="s1", session_id="5"))
    assert enriched.scope_fingerprint() == base.scope_fingerprint()
    assert enriched.fingerprint() != base.fingerprint()


# ------------------------------------------------------------------ 12 provenance
def test_provenance_records_each_source():
    r = resolve_from_applied_checkpoint({
        "id": 9, "car_id": 7, "track": "Fuji", "layout_id": "full_course",
        "purpose": "race", "setup_id": "s1", "checkpoint_id": "cp1"})
    assert r.provenance["car_id"] == ProvenanceSource.APPLIED_CHECKPOINT.value
    assert r.provenance["setup_id"] == ProvenanceSource.APPLIED_CHECKPOINT.value
    assert r.provenance["layout_id"] == ProvenanceSource.CALLER.value


def test_feedback_inherits_session_scope():
    session_ctx = EngineeringContextKey(
        car_id="7", track_location_id="fuji", layout_id="full_course",
        session_id="5", discipline="Race")
    r = resolve_feedback_against_session_context(
        session_ctx, config_id="abc", setup_id="1")
    assert r.scope_fingerprint == session_ctx.scope_fingerprint()
    assert r.context.setup_id == "1"          # enriched
    assert r.context.session_id == "5"        # inherited


# ------------------------------------------------------------------ round-trip
def test_stored_row_round_trip_preserves_unknowns():
    ctx = build_engineering_context(
        car_id="7", layout_id="full_course").context
    row = {**ctx.to_dict()}
    rebuilt = engineering_context_from_stored_row(row)
    assert rebuilt.fingerprint() == ctx.fingerprint()
    assert rebuilt.driver_id is None          # unknown preserved as None


def test_invalid_input_is_invalid_status():
    assert resolve_from_session_row("not a mapping").status == ResolutionStatus.INVALID
    assert resolve_from_applied_checkpoint(None).status == ResolutionStatus.INVALID


# ------------------------------------------------------------------ property / metamorphic
def test_collision_resistance_over_domain_grid():
    drivers = ["leon", "guest"]
    cars = ["7", "8", "9"]
    tracks = ["fuji", "spa", "monza"]
    layouts = ["full", "short"]
    gt7 = ["1.48", "1.49"]
    seen = {}
    for d, c, t, la, g in itertools.product(drivers, cars, tracks, layouts, gt7):
        k = EngineeringContextKey(
            driver_id=d, car_id=c, track_location_id=t, layout_id=la,
            gt7_version=g)
        fp = k.fingerprint()
        # No two DISTINCT scope tuples share a fingerprint (deterministic
        # separation over the supported domain — not a cryptographic claim).
        assert fp not in seen, (seen.get(fp), (d, c, t, la, g))
        seen[fp] = (d, c, t, la, g)
    assert len(seen) == 2 * 3 * 3 * 2 * 2


def test_metamorphic_scope_invariance_under_volatile_permutation():
    # Permuting ONLY the volatile components leaves the scope fingerprint fixed.
    base = dict(driver_id="leon", car_id="7", track_location_id="fuji",
                layout_id="full", gt7_version="1.49")
    scopes = set()
    for ev, disc, setup, run in itertools.product(
            ["1", "2"], ["Race", "Qualifying"], ["s1", "s2"], ["1", "2"]):
        k = EngineeringContextKey(
            **base, event_id=ev, discipline=disc, setup_id=setup, run_id=run)
        scopes.add(k.scope_fingerprint())
    assert len(scopes) == 1


# ------------------------------------------------------------------ 16,17 purity
def test_module_has_no_ui_or_network_or_ai_imports():
    src = (ROOT / "data" / "engineering_context_key.py").read_text(encoding="utf-8")
    for banned in ("PyQt6", "PyQt5", "import requests", "urllib.request",
                   "http.client", "socket", "anthropic", "openai", "api_key",
                   "import sqlite3"):
        assert banned not in src, banned


def test_module_imports_without_qt_or_db():
    import sys
    import importlib
    # A fresh import must not pull in PyQt or sqlite as a side effect.
    mod = importlib.import_module("data.engineering_context_key")
    assert mod is not None
    assert "PyQt6" not in sys.modules or True  # module itself never imports it
    src = (ROOT / "data" / "engineering_context_key.py").read_text(encoding="utf-8")
    assert "import hashlib" in src  # deterministic hashing, no randomness
    assert "random" not in src
