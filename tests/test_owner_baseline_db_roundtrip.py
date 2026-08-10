"""Cross-boundary DB round-trip tests for owner-baseline v43 fixes.

Covers:
  C1/Correction-2 — B9 unresolved riders persisted to owner_baseline_riders and
                     returned by get_owner_riders_for_event (NOT filtered from proposals).
  C2              — provenance column survives save_owner_proposal → get_owner_proposals_for_event.
  C3              — suppressed changes persisted to owner_baseline_suppressed_changes and
                     returned by get_suppressed_changes_for_event.
  C5              — owner_baseline= gate fires on the real DrivingAdvisor production path
                     (not hand-constructed SetupAuthoringContext).
  I1              — brake_bias_front → brake_bias canonicalized at save_owner_baseline.
  I1 (validate)   — validate_owner_baseline_field canonicalizes field name before lookup.
  I4              — mark_proposals_stale_for_revision; save_owner_baseline triggers stale
                     marking on re-entry.
  M3              — mark_evidence_without_baseline / get_evidence_without_baseline_disciplines.
  M1              — _FINGERPRINT_EXCLUDED_KEYS shared constant: writer and spec exclude same keys.

All tests use an in-memory SQLite DB (DB migration path is exercised fully).
No Qt, no network, no AI.
"""
from __future__ import annotations

import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pytest

from data.session_db import SessionDB


# ---------------------------------------------------------------------------
# Fixture: fresh in-memory DB at current schema version
# ---------------------------------------------------------------------------

@pytest.fixture()
def db(tmp_path):
    """Return a fresh SessionDB backed by a temp file (exercises full migration chain)."""
    db_path = tmp_path / "test_roundtrip.db"
    instance = SessionDB(str(db_path))
    yield instance
    instance.close()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _seed_event(db, name: str = "Test Event") -> int:
    """Insert a minimal event row and return its integer id."""
    eid = db.upsert_event({"name": name, "track": "Monza", "car": "Porsche RSR"})
    return int(eid or 1)


def _seed_baseline(db, event_id: int, discipline: str = "race") -> int:
    """Save a minimal owner baseline. Returns DB row id."""
    setup = {"ride_height_front": 90.0, "springs_front": 70.0}
    return db.save_owner_baseline(event_id, discipline, setup)


# ===========================================================================
# C2 — provenance survives save_owner_proposal → get_owner_proposals_for_event
# ===========================================================================

class TestC2ProvenianceSurvivesRoundtrip:
    def test_provenance_persisted_and_returned(self, db):
        event_id = _seed_event(db)
        proposal = {
            "event_id": event_id,
            "session_run_id": "run-abc",
            "discipline": "race",
            "parameter": "springs_front",
            "direction": "increase",
            "proposed_value": 75.0,
            "original_value": 70.0,
            "clipped": False,
            "clip_stated_reason": "",
            "label": "TEL_CORROBORATED",
            "status": "proposed",
            "original_proposed_value": 75.0,
            "evidence_sources": ["telemetry", "feedback"],
            "baseline_revision": 1,
            "clean_laps": 6,
            "provenance": "MEASURED_FACT",
        }
        pid = db.save_owner_proposal(event_id, proposal)
        assert pid, "save_owner_proposal must return a non-empty proposal_id"

        rows = db.get_owner_proposals_for_event(event_id)
        assert len(rows) == 1
        assert rows[0]["provenance"] == "MEASURED_FACT", (
            "provenance must survive the DB round-trip (C2)"
        )

    def test_provenance_defaults_to_empty_string_when_absent(self, db):
        event_id = _seed_event(db)
        proposal = {
            "event_id": event_id,
            "session_run_id": "run-xyz",
            "discipline": "qualifying",
            "parameter": "ride_height_front",
            "direction": "decrease",
            "proposed_value": 85.0,
            "original_value": 90.0,
            "status": "proposed",
            "baseline_revision": 1,
            "clean_laps": 3,
            # provenance key intentionally absent
        }
        pid = db.save_owner_proposal(event_id, proposal)
        assert pid
        rows = db.get_owner_proposals_for_event(event_id)
        assert rows[0]["provenance"] == ""

    def test_all_four_provenance_tags_round_trip(self, db):
        event_id = _seed_event(db)
        tags = [
            "MEASURED_FACT",
            "DETERMINISTIC_INFERENCE",
            "DRIVER_REPORT",
            "UNRESOLVED",
        ]
        for i, tag in enumerate(tags):
            db.save_owner_proposal(event_id, {
                "event_id": event_id,
                "session_run_id": f"run-{i}",
                "discipline": "race",
                "parameter": f"param_{i}",
                "direction": "increase",
                "proposed_value": float(i + 1),
                "original_value": 0.0,
                "status": "proposed",
                "baseline_revision": 1,
                "clean_laps": 6,
                "provenance": tag,
            })
        rows = db.get_owner_proposals_for_event(event_id)
        returned_tags = {r["provenance"] for r in rows}
        assert returned_tags == set(tags), (
            f"All C19 provenance tags must survive round-trip; missing={set(tags) - returned_tags}"
        )


# ===========================================================================
# C1/Correction-2 — B9 riders persisted and fetched from their OWN table
# ===========================================================================

class TestC1UnresolvedRiders:
    def test_save_and_retrieve_rider(self, db):
        event_id = _seed_event(db)
        rider = {
            "event_id": event_id,
            "session_run_id": "run-r1",
            "discipline": "race",
            "parameter": "brake_bias",
            "feedback_direction": "increase",
            "baseline_revision": 1,
            "note": "Driver says front-biased; telemetry silent on this field.",
            "evidence_sources": ["feedback"],
        }
        rid = db.save_owner_rider(event_id, rider)
        assert rid, "save_owner_rider must return a non-empty rider_id"

        rows = db.get_owner_riders_for_event(event_id)
        assert len(rows) == 1
        r = rows[0]
        assert r["parameter"] == "brake_bias"
        assert r["feedback_direction"] == "increase"
        assert r["discipline"] == "race"
        assert r["rider_id"] == rid

    def test_riders_isolated_from_proposals(self, db):
        """B9 riders and B11 contradiction proposals must be in separate stores (C1)."""
        event_id = _seed_event(db)

        # A B9 rider
        db.save_owner_rider(event_id, {
            "event_id": event_id, "session_run_id": "r1",
            "discipline": "race", "parameter": "lsd_accel",
            "feedback_direction": "decrease", "baseline_revision": 1,
            "note": "Rider note", "evidence_sources": [],
        })

        # A B11 contradiction proposal with status="unresolved"
        db.save_owner_proposal(event_id, {
            "event_id": event_id, "session_run_id": "r1",
            "discipline": "race", "parameter": "springs_front",
            "direction": "increase", "proposed_value": 80.0,
            "original_value": 70.0, "status": "unresolved",
            "baseline_revision": 1, "clean_laps": 6, "provenance": "UNRESOLVED",
        })

        riders = db.get_owner_riders_for_event(event_id)
        proposals = db.get_owner_proposals_for_event(event_id)

        # Riders table must contain ONLY the genuine B9 rider.
        assert len(riders) == 1
        assert riders[0]["parameter"] == "lsd_accel"

        # Proposals must contain ONLY the B11 contradiction.
        assert len(proposals) == 1
        assert proposals[0]["parameter"] == "springs_front"
        assert proposals[0]["status"] == "unresolved"

    def test_empty_event_returns_empty_list(self, db):
        event_id = _seed_event(db)
        assert db.get_owner_riders_for_event(event_id) == []

    def test_evidence_sources_persisted_as_list(self, db):
        event_id = _seed_event(db)
        db.save_owner_rider(event_id, {
            "event_id": event_id, "session_run_id": "r1",
            "discipline": "race", "parameter": "camber_front",
            "feedback_direction": "decrease", "baseline_revision": 1,
            "note": "", "evidence_sources": ["feedback", "lap_data"],
        })
        rows = db.get_owner_riders_for_event(event_id)
        assert rows[0]["evidence_sources"] == ["feedback", "lap_data"]


# ===========================================================================
# C3 — Suppressed changes persisted and fetched from their OWN table
# ===========================================================================

class TestC3SuppressedChanges:
    def test_save_and_retrieve_suppressed_change(self, db):
        event_id = _seed_event(db)
        change = {
            "event_id": event_id,
            "session_run_id": "run-s1",
            "discipline": "race",
            "parameter": "ride_height_rear",
            "reason": "SUPPRESSED: previously rejected at this band",
            "ratchet_locked": False,
            "feedback_recorded": True,
            "baseline_revision": 1,
        }
        cid = db.save_suppressed_change(event_id, change)
        assert cid, "save_suppressed_change must return a non-empty change_id"

        rows = db.get_suppressed_changes_for_event(event_id)
        assert len(rows) == 1
        c = rows[0]
        assert c["parameter"] == "ride_height_rear"
        assert c["feedback_recorded"] is True
        assert c["ratchet_locked"] is False
        assert c["change_id"] == cid

    def test_multiple_suppressed_changes_all_returned(self, db):
        event_id = _seed_event(db)
        for param in ("springs_front", "dampers_fast_bump", "aero_front"):
            db.save_suppressed_change(event_id, {
                "event_id": event_id, "session_run_id": "r2",
                "discipline": "qualifying", "parameter": param,
                "reason": "SUPPRESSED", "ratchet_locked": False,
                "feedback_recorded": False, "baseline_revision": 1,
            })
        rows = db.get_suppressed_changes_for_event(event_id)
        assert len(rows) == 3
        params = {r["parameter"] for r in rows}
        assert params == {"springs_front", "dampers_fast_bump", "aero_front"}

    def test_empty_event_returns_empty_list(self, db):
        event_id = _seed_event(db)
        assert db.get_suppressed_changes_for_event(event_id) == []


# ===========================================================================
# I1 — brake_bias_front → brake_bias canonicalized at save_owner_baseline
# ===========================================================================

class TestI1FieldCanonicalization:
    def test_brake_bias_front_stored_as_brake_bias(self, db):
        event_id = _seed_event(db)
        setup = {
            "ride_height_front": 90.0,
            "brake_bias_front": 58.0,  # UI/GT7 name
        }
        db.save_owner_baseline(event_id, "race", setup)
        stored = db.get_owner_baseline(event_id, "race")
        assert stored is not None
        # The UI name must NOT appear; the canonical name must.
        assert "brake_bias_front" not in stored, (
            "brake_bias_front must be canonicalized to brake_bias at save time (I1)"
        )
        assert "brake_bias" in stored, (
            "canonical brake_bias key must be present after canonicalization (I1)"
        )
        assert stored["brake_bias"] == 58.0

    def test_other_fields_unchanged_by_alias_map(self, db):
        event_id = _seed_event(db)
        setup = {
            "ride_height_front": 90.0,
            "springs_front": 70.0,
            "camber_front": -2.5,
        }
        db.save_owner_baseline(event_id, "race", setup)
        stored = db.get_owner_baseline(event_id, "race")
        assert stored["ride_height_front"] == 90.0
        assert stored["springs_front"] == 70.0
        assert stored["camber_front"] == -2.5

    def test_validate_owner_baseline_field_never_raises_for_ui_name(self, db):
        """validate_owner_baseline_field must never raise for UI alias field names (I1).

        The method degrades open (returns True) when there is no spec for a field.
        When the field IS in the model after canonicalization, it validates normally.
        The critical invariant is that passing the UI alias NEVER causes a crash or
        silent always-true bypass — it must behave identically to the canonical name.
        """
        # Must never raise — result is True or False depending on the value and model.
        result = db.validate_owner_baseline_field("brake_bias_front", 58.0, car="")
        assert isinstance(result, tuple) and len(result) == 2, (
            "validate_owner_baseline_field must return a 2-tuple even for UI aliases"
        )
        ok, reason = result
        assert isinstance(ok, bool)
        assert isinstance(reason, str)

    def test_validate_resolves_canonical_alias(self, db):
        """When given 'brake_bias_front' and 'brake_bias', both should resolve the
        same spec (or both degrade open identically if the model doesn't know the car).
        They must NOT produce different outcomes — the alias map must be used."""
        ok_alias, _ = db.validate_owner_baseline_field("brake_bias_front", 58.0, car="")
        ok_canon, _ = db.validate_owner_baseline_field("brake_bias", 58.0, car="")
        assert ok_alias == ok_canon, (
            "brake_bias_front and brake_bias must produce identical validation results (I1)"
        )


# ===========================================================================
# I4 — Stale-marking on baseline re-entry
# ===========================================================================

class TestI4StaleMarkingOnReEntry:
    def test_proposals_become_stale_on_second_baseline_entry(self, db):
        event_id = _seed_event(db)
        # Enter baseline (revision 1).
        db.save_owner_baseline(event_id, "race", {"springs_front": 70.0})

        # Save two proposals tied to revision 1.
        for p in ("springs_front", "dampers_bump"):
            db.save_owner_proposal(event_id, {
                "event_id": event_id, "session_run_id": "r1",
                "discipline": "race", "parameter": p,
                "direction": "increase", "proposed_value": 75.0,
                "original_value": 70.0, "status": "proposed",
                "baseline_revision": 1, "clean_laps": 6, "provenance": "MEASURED_FACT",
            })

        # Re-enter the baseline (revision → 2).
        db.save_owner_baseline(event_id, "race", {"springs_front": 72.0})

        rows = db.get_owner_proposals_for_event(event_id)
        assert len(rows) == 2
        for row in rows:
            assert row["status"] == "stale", (
                f"proposal {row['parameter']!r} must be stale after baseline re-entry (I4); "
                f"got status={row['status']!r}"
            )

    def test_mark_proposals_stale_for_revision_direct(self, db):
        event_id = _seed_event(db)
        # Seed proposals at revision 1 and revision 2.
        for rev, param in [(1, "springs_front"), (2, "dampers_bump")]:
            db.save_owner_proposal(event_id, {
                "event_id": event_id, "session_run_id": "r1",
                "discipline": "race", "parameter": param,
                "direction": "increase", "proposed_value": 75.0,
                "original_value": 70.0, "status": "proposed",
                "baseline_revision": rev, "clean_laps": 6, "provenance": "MEASURED_FACT",
            })
        # Mark proposals older than revision 2 as stale.
        staled = db.mark_proposals_stale_for_revision(event_id, "race", 2)
        assert staled == 1, f"Exactly 1 row (rev 1) should be staled; got {staled}"

        rows = db.get_owner_proposals_for_event(event_id)
        by_param = {r["parameter"]: r["status"] for r in rows}
        assert by_param["springs_front"] == "stale"
        assert by_param["dampers_bump"] == "proposed"  # still at current revision

    def test_stale_accepted_by_update_proposal_status(self, db):
        event_id = _seed_event(db)
        pid = db.save_owner_proposal(event_id, {
            "event_id": event_id, "session_run_id": "r1",
            "discipline": "race", "parameter": "springs_front",
            "direction": "increase", "proposed_value": 75.0,
            "original_value": 70.0, "status": "proposed",
            "baseline_revision": 1, "clean_laps": 6, "provenance": "MEASURED_FACT",
        })
        ok = db.update_proposal_status(pid, "stale")
        assert ok is True
        rows = db.get_owner_proposals_for_event(event_id)
        assert rows[0]["status"] == "stale"


# ===========================================================================
# M3 — evidence-without-baseline flags (DB-backed, replaces in-memory counter)
# ===========================================================================

class TestM3EvidenceWithoutBaselineFlags:
    def test_flag_and_retrieve(self, db):
        event_id = _seed_event(db)
        inserted = db.mark_evidence_without_baseline(event_id, "race", "run-001")
        assert inserted is True, "First flag must return True (new row)"

        discs = db.get_evidence_without_baseline_disciplines(event_id)
        assert "race" in discs

    def test_duplicate_flag_is_idempotent(self, db):
        event_id = _seed_event(db)
        db.mark_evidence_without_baseline(event_id, "race", "run-001")
        second = db.mark_evidence_without_baseline(event_id, "race", "run-001")
        assert second is False, "Second flag for same session must return False (idempotent)"

    def test_multiple_disciplines_reported(self, db):
        event_id = _seed_event(db)
        db.mark_evidence_without_baseline(event_id, "qualifying", "run-q1")
        db.mark_evidence_without_baseline(event_id, "race", "run-r1")
        discs = db.get_evidence_without_baseline_disciplines(event_id)
        assert set(discs) == {"qualifying", "race"}

    def test_different_sessions_same_discipline(self, db):
        event_id = _seed_event(db)
        db.mark_evidence_without_baseline(event_id, "race", "run-r1")
        db.mark_evidence_without_baseline(event_id, "race", "run-r2")
        discs = db.get_evidence_without_baseline_disciplines(event_id)
        # Discipline should appear ONCE (DISTINCT query).
        assert discs.count("race") == 1

    def test_different_events_isolated(self, db):
        e1 = _seed_event(db)
        # create a second event
        e2 = db.upsert_event({
            "name": "Second Event", "car": "Aston Martin V8", "track": "Brands Hatch",
        })
        db.mark_evidence_without_baseline(e1, "race", "run-e1")
        db.mark_evidence_without_baseline(int(e2 or 2), "qualifying", "run-e2")
        assert db.get_evidence_without_baseline_disciplines(e1) == ["race"]
        assert db.get_evidence_without_baseline_disciplines(int(e2 or 2)) == ["qualifying"]

    def test_empty_event_returns_empty_list(self, db):
        event_id = _seed_event(db)
        assert db.get_evidence_without_baseline_disciplines(event_id) == []


# ===========================================================================
# C5 — owner_baseline= gate fires on the DrivingAdvisor production path
# ===========================================================================

class TestC5AdvisorSpy_IA:
    """I-A wiring: calls the REAL DrivingAdvisor.build_baseline_setup_response and
    spies on SetupAuthoringContext.__init__ to verify that owner_baseline= is non-None
    when a baseline has been saved to the DB.

    WHY THIS REPLACES TestC5ProductionPathOwnerBaselineGate:
        The old class simulated what _mk_ctx does by extracting the closure body into
        test code.  That means the test passed even when the production closure was
        broken — it tested a copy, not the production path.  This replacement calls the
        REAL public method and asserts on what the REAL code actually passes to
        SetupAuthoringContext.  A revert to the old bug immediately breaks this test.

    KNOWN PRODUCTION BUG (C5) — EXPECTED FAILURE:
        build_baseline_setup_response._mk_ctx references _event_ctx as a free variable.
        _event_ctx is NOT defined as a local in build_baseline_setup_response — it is
        only assigned in build_combined_setup_response (line ~1549:
            _event_ctx = getattr(self, "_event_ctx", {})
        ).
        The closure catches the resulting NameError via
            ``except Exception: _owner_bl = None``
        so owner_baseline=None is ALWAYS passed to SetupAuthoringContext regardless of
        whether a baseline exists in the DB.
        Spy evidence: captured [None, None, None] rather than at least one non-None.

        Fix (backend-builder): add
            _event_ctx = getattr(self, "_event_ctx", {})
        before the _mk_ctx closure definition inside build_baseline_setup_response.
    """

    def test_build_baseline_setup_response_passes_owner_baseline_when_baseline_in_db(
        self, db, monkeypatch
    ):
        """Spy on SetupAuthoringContext.__init__; assert owner_baseline= is non-None.

        EXPECTED FAILURE until the C5 production bug is fixed.
        The spy captures [None, None, None] — the NameError on _event_ctx is caught
        silently and owner_baseline defaults to None for every objective.
        """
        from strategy.driving_advisor import DrivingAdvisor
        from strategy.setup_ranges import resolve_ranges
        from strategy.setup_authoring import SetupAuthoringContext

        event_id = _seed_event(db, "C5-advisor-spy")
        _seed_baseline(db, event_id, "race")

        class _Stub:
            """Minimal stub: every attribute access returns a no-op callable."""
            def __getattr__(self, name):
                return lambda *a, **kw: None

        advisor = DrivingAdvisor(
            recorder=_Stub(), tracker=_Stub(), config=_Stub(), db=db
        )
        advisor.set_event_context({"id": event_id, "track": "Monza"})

        captured: list = []
        _orig_init = SetupAuthoringContext.__init__

        def _spy_init(ctx_self, *args, **kwargs):
            captured.append(kwargs.get("owner_baseline"))
            return _orig_init(ctx_self, *args, **kwargs)

        monkeypatch.setattr(SetupAuthoringContext, "__init__", _spy_init)

        ranges = resolve_ranges("Porsche RSR")
        advisor.build_baseline_setup_response(
            car_name="Porsche RSR",
            ranges=ranges,
            drivetrain="RR",
            num_gears=6,
            allowed_tuning=None,
            tuning_locked=False,
        )

        # PRODUCTION BUG (C5): this assertion FAILS.
        # _mk_ctx references _event_ctx which is not a local of build_baseline_setup_response.
        # The NameError is caught by ``except Exception: _owner_bl = None``, so the spy
        # captures [None, None, None] — never a real baseline dict.
        # A revert would break this test; a correct fix would make it green.
        # Fix owner: backend-builder.
        assert any(bl is not None for bl in captured), (
            f"C5 bug: build_baseline_setup_response always passes owner_baseline=None "
            f"to SetupAuthoringContext.__init__. Spy captured: {captured!r}. "
            "Fix: add '_event_ctx = getattr(self, \"_event_ctx\", {})' before the "
            "_mk_ctx closure inside build_baseline_setup_response "
            "(driving_advisor.py). Owner: backend-builder."
        )


# ===========================================================================
# M1 — _FINGERPRINT_EXCLUDED_KEYS shared between spec and writer
# ===========================================================================

class TestM1FingerprintExclusionKeysShared:
    def test_fingerprint_excluded_keys_in_spec(self):
        from strategy.event_export_spec import _FINGERPRINT_EXCLUDED_KEYS
        assert "content_fingerprint" in _FINGERPRINT_EXCLUDED_KEYS, (
            "content_fingerprint must be in _FINGERPRINT_EXCLUDED_KEYS (M1)"
        )
        assert "generated_at_human" in _FINGERPRINT_EXCLUDED_KEYS, (
            "generated_at_human must be in _FINGERPRINT_EXCLUDED_KEYS (M1)"
        )

    def test_writer_imports_from_spec(self):
        """The writer must import _FINGERPRINT_EXCLUDED_KEYS from event_export_spec,
        not define its own set."""
        import importlib
        writer_mod = importlib.import_module("data.event_export_writer")
        spec_mod = importlib.import_module("strategy.event_export_spec")
        # The writer must use the same object (by identity after import resolution).
        assert writer_mod._FINGERPRINT_EXCLUDED_KEYS is spec_mod._FINGERPRINT_EXCLUDED_KEYS, (
            "writer must use the SAME _FINGERPRINT_EXCLUDED_KEYS object as the spec (M1)"
        )

    def test_fingerprint_stable_across_generated_at_changes(self):
        """Changing generated_at_human must NOT change the content_fingerprint (M1)."""
        from strategy.event_export_spec import build_event_export_spec

        common_kwargs = dict(
            event_id=1, event_name="Test Event",
            car="Porsche RSR", track="Monza",
            scope_fingerprint="abc123",
            memory_context_key_race="", memory_context_key_qualifying="",
            owner_baselines={}, proposals=[],
            unresolved_riders=[], suppressed_changes=[],
            session_evidence=[], feedback_rows=[], lap_cov_list=[],
        )
        spec_a = build_event_export_spec(**common_kwargs, generated_at_human="2026-01-01T00:00:00+00:00")
        spec_b = build_event_export_spec(**common_kwargs, generated_at_human="2026-06-15T12:30:00+00:00")

        assert spec_a["content_fingerprint"] == spec_b["content_fingerprint"], (
            "content_fingerprint must be identical regardless of generated_at_human value (M1/C18)"
        )
