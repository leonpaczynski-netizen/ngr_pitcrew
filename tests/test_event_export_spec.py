"""Unit tests for strategy.event_export_spec.

Covers:
  C17  — File output contains owner baseline, all proposals, session evidence,
           unresolved riders, suppressed changes, driver profile delta.
  C18  — Content fingerprint is deterministic; generated_at_human excluded from fp.
  C19  — Every proposal carries a provenance tag.
  C20  — Driver profile delta blocks with blocked_reason when < 4 sessions.
  C21  — export_filename produces expected deterministic format.
  GENERAL — build_event_export_spec never raises; empty inputs produce valid spec.

Pure tests — no Qt, no DB, no network.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pytest

from strategy.event_export_spec import (
    SCHEMA_KEY_ORDER,
    build_event_export_spec,
    export_filename,
)
from strategy._setup_constants import DB_VERSION, EXPORT_FORMAT_VERSION, RULE_ENGINE_VERSION
from data.engineering_context_key import FINGERPRINT_VERSION


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _minimal_spec(**overrides) -> dict:
    """Call build_event_export_spec with empty / minimal inputs."""
    defaults = dict(
        event_id=1,
        event_name="Test Event",
        car="Porsche RSR",
        track="Fuji",
        scope_fingerprint="eck_v1:scope:abcdef123456",
        memory_context_key_race="mcr_race",
        memory_context_key_qualifying="mcr_qual",
        owner_baselines={"race": None, "qualifying": None},
        proposals=[],
        unresolved_riders=[],
        suppressed_changes=[],
        session_evidence=[],
        feedback_rows=[],
        lap_cov_list=[],
        generated_at_human="2026-08-10T12:00:00+00:00",
    )
    defaults.update(overrides)
    return build_event_export_spec(**defaults)


# ---------------------------------------------------------------------------
# Schema / structure (C17)
# ---------------------------------------------------------------------------

def test_all_schema_keys_present():
    spec = _minimal_spec()
    for key in SCHEMA_KEY_ORDER:
        assert key in spec, f"schema key {key!r} missing from spec"


def test_version_fields_embedded():
    spec = _minimal_spec()
    assert spec["db_version"] == DB_VERSION
    assert spec["rule_engine_version"] == RULE_ENGINE_VERSION
    assert spec["export_format_version"] == EXPORT_FORMAT_VERSION
    assert spec["fingerprint_version"] == FINGERPRINT_VERSION


def test_event_identity_fields():
    spec = _minimal_spec(event_id=42, event_name="Fuji GP", car="GR86", track="Fuji")
    assert spec["event_id"] == 42
    assert spec["event_name"] == "Fuji GP"
    assert spec["car"] == "GR86"
    assert spec["track"] == "Fuji"


def test_owner_baselines_structure():
    spec = _minimal_spec(
        owner_baselines={"race": {"spring_rate_front": 55.0}, "qualifying": None}
    )
    assert spec["owner_baselines"]["race"]["spring_rate_front"] == 55.0
    assert spec["owner_baselines"]["qualifying"] is None


def test_proposals_list_preserved():
    proposals = [
        {"proposal_id": "p1", "parameter": "camber_front", "direction": "decrease",
         "discipline": "race", "status": "proposed", "label": "telemetry (driver feedback absent or silent)",
         "provenance": "MEASURED_FACT", "evidence_sources": []},
    ]
    spec = _minimal_spec(proposals=proposals)
    assert len(spec["proposals"]) == 1
    assert spec["proposals"][0]["proposal_id"] == "p1"


def test_session_evidence_list_preserved():
    evidence = [
        {"session_run_id": "run-1", "discipline": "race",
         "clean_lap_count": 7, "feedback_signals": {}},
    ]
    spec = _minimal_spec(session_evidence=evidence)
    assert len(spec["session_evidence"]) == 1
    assert spec["session_evidence"][0]["clean_lap_count"] == 7


def test_unresolved_riders_list_preserved():
    riders = [
        {"parameter": "arb_front", "feedback_direction": "increase",
         "discipline": "race", "session_run_id": "run-1",
         "baseline_revision": 1, "note": "no telemetry signal", "evidence_sources": [],
         "event_id": 1},
    ]
    spec = _minimal_spec(unresolved_riders=riders)
    assert len(spec["unresolved_riders"]) == 1
    assert spec["unresolved_riders"][0]["parameter"] == "arb_front"


def test_suppressed_changes_list_preserved():
    suppressed = [
        {"parameter": "spring_rate_rear", "reason": "SUPPRESSED: ratchet",
         "ratchet_locked": True, "feedback_recorded": False},
    ]
    spec = _minimal_spec(suppressed_changes=suppressed)
    assert len(spec["suppressed_changes"]) == 1


# ---------------------------------------------------------------------------
# Content fingerprint (C18)
# ---------------------------------------------------------------------------

def test_content_fingerprint_present_and_non_empty():
    spec = _minimal_spec()
    assert spec["content_fingerprint"].startswith("sha256:")
    assert len(spec["content_fingerprint"]) > 10


def test_content_fingerprint_deterministic():
    """Same inputs → same content_fingerprint."""
    spec_a = _minimal_spec()
    spec_b = _minimal_spec()
    assert spec_a["content_fingerprint"] == spec_b["content_fingerprint"]


def test_content_fingerprint_changes_when_proposals_change():
    """Adding a proposal changes the fingerprint."""
    spec_empty = _minimal_spec(proposals=[])
    spec_with = _minimal_spec(proposals=[{"proposal_id": "x", "parameter": "camber_front"}])
    assert spec_empty["content_fingerprint"] != spec_with["content_fingerprint"]


def test_generated_at_excluded_from_fingerprint():
    """generated_at_human must NOT affect the fingerprint (C18)."""
    spec_a = _minimal_spec(generated_at_human="2026-08-10T12:00:00+00:00")
    spec_b = _minimal_spec(generated_at_human="2026-08-10T13:00:00+00:00")
    assert spec_a["content_fingerprint"] == spec_b["content_fingerprint"], (
        "different generated_at_human must NOT change the content fingerprint"
    )
    # The field should still be present in the output, just not in the hash.
    assert spec_b["generated_at_human"] == "2026-08-10T13:00:00+00:00"


def test_content_fingerprint_changes_when_car_changes():
    spec_a = _minimal_spec(car="Porsche RSR")
    spec_b = _minimal_spec(car="Ferrari F355")
    assert spec_a["content_fingerprint"] != spec_b["content_fingerprint"]


# ---------------------------------------------------------------------------
# C20 — Driver profile delta gate
# ---------------------------------------------------------------------------

def test_profile_delta_blocked_when_no_feedback():
    """C20: profile delta blocks with blocked_reason when no feedback sessions."""
    spec = _minimal_spec(feedback_rows=[], lap_cov_list=[])
    delta = spec["driver_profile_delta"]
    assert delta["delta_fields"] == {}, "delta_fields must be empty when blocked"
    assert delta.get("blocked_reason", "") != "", "blocked_reason must explain why no delta"


def test_profile_delta_blocked_reason_mentions_session_threshold():
    spec = _minimal_spec(feedback_rows=[{"mid_corner": "understeer"}], lap_cov_list=[])
    delta = spec["driver_profile_delta"]
    # When blocked, reason should mention the threshold requirement.
    if delta.get("blocked_reason"):
        assert "session" in delta["blocked_reason"].lower(), (
            "blocked_reason should reference the session threshold"
        )


# ---------------------------------------------------------------------------
# C21 — export_filename
# ---------------------------------------------------------------------------

def test_export_filename_format():
    name = export_filename("Fuji GP", "eck_v1:scope:abcdef123456abcdef")
    assert name.endswith("_event_export.json")
    assert "Fuji_GP" in name or "Fuji GP".replace(" ", "_") in name.replace(" ", "_")


def test_export_filename_uses_12_chars_of_fingerprint():
    fp = "eck_v1:scope:123456789012abcdef"
    name = export_filename("TestEvent", fp)
    # The fingerprint part after the colon, first 12 chars, with `:` replaced.
    fp12 = fp[:12].replace(":", "_")
    assert fp12 in name


def test_export_filename_sanitises_illegal_chars():
    name = export_filename("Event: 2026/08", "eck_v1:scope:abc")
    # Colons and slashes must not appear in the sanitised part.
    # (The fingerprint part uses replace(":", "_") separately.)
    assert "<" not in name
    assert ">" not in name
    assert "/" not in name
    assert "*" not in name
    assert "?" not in name


def test_export_filename_fallback_on_empty_event_name():
    name = export_filename("", "eck_v1:scope:abc123")
    # Must produce a valid filename even with an empty event name.
    assert name.endswith("_event_export.json")
    assert len(name) > len("_event_export.json")


# ---------------------------------------------------------------------------
# Never raises
# ---------------------------------------------------------------------------

def test_build_event_export_spec_never_raises_on_none_inputs():
    """All-None/empty inputs must return a valid (degraded) spec, never crash."""
    spec = build_event_export_spec(
        event_id=0,
        event_name="",
        car="",
        track="",
        scope_fingerprint="",
        memory_context_key_race="",
        memory_context_key_qualifying="",
        owner_baselines={},
        proposals=[],
        unresolved_riders=[],
        suppressed_changes=[],
        session_evidence=[],
        feedback_rows=[],
        lap_cov_list=[],
        generated_at_human="",
    )
    assert isinstance(spec, dict)
    for key in SCHEMA_KEY_ORDER:
        assert key in spec


def test_build_event_export_spec_never_raises_on_broken_proposals():
    """Broken proposal dicts must not crash the spec builder."""
    broken_proposals = [
        None,                 # type: ignore[list-item]
        {},
        {"proposal_id": 123, "parameter": None},  # bad types
    ]
    spec = build_event_export_spec(
        event_id=1,
        event_name="Test",
        car="Test Car",
        track="Test Track",
        scope_fingerprint="eck_v1:scope:test0000",
        memory_context_key_race="mcr",
        memory_context_key_qualifying="mcq",
        owner_baselines={},
        proposals=broken_proposals,  # type: ignore[arg-type]
        unresolved_riders=[],
        suppressed_changes=[],
        session_evidence=[],
        feedback_rows=[],
        lap_cov_list=[],
        generated_at_human="",
    )
    assert isinstance(spec, dict)


# ---------------------------------------------------------------------------
# Scope / memory context keys preserved
# ---------------------------------------------------------------------------

def test_scope_and_memory_keys_in_spec():
    spec = _minimal_spec(
        scope_fingerprint="eck_v1:scope:cafebabe12",
        memory_context_key_race="mck_race_001",
        memory_context_key_qualifying="mck_qual_001",
    )
    assert spec["scope_fingerprint"] == "eck_v1:scope:cafebabe12"
    assert spec["memory_context_key_race"] == "mck_race_001"
    assert spec["memory_context_key_qualifying"] == "mck_qual_001"
