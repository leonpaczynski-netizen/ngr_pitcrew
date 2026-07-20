"""Phase 48-50 — future NGR League Hub manifest contract tests (task items 36, 37, and the invariants
that the Hub cannot become required for offline use and a revision cannot rewrite immutable history)."""
from __future__ import annotations

from strategy.ngr_event_manifest import (
    NgrEventManifest, NgrEventManifestVersion as Ver, NgrRegisteredDriverReference,
    validate_manifest, NgrEventManifestValidationCode as VC, diff_revision, OfflineNgrEventImportPort,
    manifest_to_cycle_identity,
)


def _m(**kw):
    base = dict(manifest_version=Ver.V1, event_ref="ngr-porsche-r3", series="NGR Porsche Cup",
                round_label="R3", track="Fuji", layout="Full", car="Porsche 911 RSR",
                official_quali_date="2026-06-21", official_race_date="2026-06-21")
    base.update(kw)
    return NgrEventManifest(**base)


def test_manifest_validates_ok():
    v = validate_manifest(_m())
    assert v.ok is True and not v.codes


def test_manifest_requires_event_ref():
    v = validate_manifest(_m(event_ref=""))
    assert v.ok is False and VC.MISSING_EVENT_REF in v.codes


def test_manifest_rejects_invalid_date():
    v = validate_manifest(_m(official_race_date="not-a-date"))
    assert v.ok is False and VC.INVALID_DATE in v.codes


def test_manifest_fingerprint_excludes_revision():
    a = _m(revision=1)
    b = _m(revision=7)
    assert a.fingerprint() == b.fingerprint()  # revision is metadata, not environment content


def test_offline_port_imports_nothing_hub_not_required():
    port = OfflineNgrEventImportPort()
    assert port.fetch_manifest("anything") is None  # offline creation is unaffected


def test_revision_environment_change_flags_incompatible_evidence():
    prev = _m(revision=1, bop="BoP A")
    new = _m(revision=2, bop="BoP B")  # BoP is evidence-sensitive
    rev = diff_revision(prev, new)
    assert rev.environment_changed is True
    assert rev.prior_evidence_compatible is False
    assert "bop" in rev.changed_fields


def test_revision_non_environment_change_keeps_evidence_compatible():
    prev = _m(revision=1, penalties="standard")
    new = _m(revision=2, penalties="strict")  # penalties are not evidence-sensitive
    rev = diff_revision(prev, new)
    assert rev.prior_evidence_compatible is True
    assert "penalties" in rev.changed_fields


def test_manifest_projects_to_cycle_identity():
    ident = manifest_to_cycle_identity(_m(driver=NgrRegisteredDriverReference("drv-1", "Leon", "42", "NGR")))
    assert ident["series"] == "NGR Porsche Cup" and ident["track"] == "Fuji"
    assert ident["driver_id"] == "drv-1"
    assert "R3" in ident["event_name"]
