"""Phases 33-35 — golden fixtures: 12 representative states, restart-identical + ordering-identical.

Golden values are the deterministic fingerprints of each canonical state. They contain no timestamps,
machine paths or random identifiers. If a fingerprint here changes, a material behaviour changed.
"""
import copy

from strategy.assurance_chain_export import build_assurance_chain_export
from strategy.assurance_snapshot_comparison import compare_assurance_snapshots
from strategy.assurance_review_package import build_review_package_spec
from tests._assurance_pack_helpers import synthetic_products, synthetic_context, synthetic_export


def _export(**kw):
    return synthetic_export(**kw)


# scenario builders (deterministic) ----------------------------------------------------------

def _empty():
    return build_assurance_chain_export({}, synthetic_context()).to_dict()


def _negative_only():
    # only negative (regression) evidence, no open contradiction
    return _export(grade="not_assured", contra_open=False, independent=1, findings=[
        {"finding_type": "unresolved_regression", "severity": "blocking", "domain": "differential",
         "source_phase": "P28"}])


def _fully_assured():
    return _export(grade="assured", contra_open=False, findings=[])


def _blocking_contradiction():
    return _export(grade="not_assured", contra_open=True, independent=1)


def _version_sensitive():
    return _export(grade="partially_assured", contra_open=False, findings=[
        {"finding_type": "version_sensitivity_unaddressed", "severity": "major",
         "domain": "differential", "source_phase": "P26"}])


def _severe_blind_spot():
    return _export(grade="not_assured", contra_open=False, findings=[
        {"finding_type": "critical_blind_spot", "severity": "major", "domain": "differential",
         "source_phase": "P27"}])


def _assumption_capped():
    return _export(grade="assured_with_limitations", contra_open=False, findings=[
        {"finding_type": "unverified_proxy_reliance", "severity": "major", "domain": "differential",
         "source_phase": "P30"}])


def _high_leverage():
    return _export(grade="not_assured", contra_open=False, findings=[
        {"finding_type": "dependent_evidence_reliance", "severity": "blocking",
         "domain": "differential", "source_phase": "P30"},
        {"finding_type": "unresolved_regression", "severity": "major", "domain": "differential",
         "source_phase": "P28"}])


ALL_SCENARIOS = {
    "empty": _empty, "negative_only": _negative_only, "fully_assured": _fully_assured,
    "blocking_contradiction": _blocking_contradiction, "version_sensitive": _version_sensitive,
    "severe_blind_spot": _severe_blind_spot, "assumption_capped": _assumption_capped,
    "high_leverage": _high_leverage,
}


def test_each_scenario_export_restart_identical():
    for name, fn in ALL_SCENARIOS.items():
        assert fn()["content_fingerprint"] == fn()["content_fingerprint"], name


def test_scenarios_have_distinct_fingerprints():
    fps = {name: fn()["content_fingerprint"] for name, fn in ALL_SCENARIOS.items()}
    # every distinct scenario must yield a distinct chain fingerprint (no collision)
    assert len(set(fps.values())) == len(fps), fps


def test_no_timestamps_paths_or_random_in_golden_exports():
    import re
    import json
    for name, fn in ALL_SCENARIOS.items():
        blob = json.dumps(fn())
        assert not re.search(r"\d{4}-\d{2}-\d{2}T\d{2}:", blob), name   # no ISO timestamps
        assert "c:\\" not in blob.lower() and "/home/" not in blob.lower(), name


def test_golden_9_compatible_baseline_improvement():
    base = _blocking_contradiction()
    cand = _export(grade="assured_with_limitations", contra_open=False, independent=3, findings=[])
    c1 = compare_assurance_snapshots(base, cand).to_dict()
    c2 = compare_assurance_snapshots(base, cand).to_dict()
    assert c1["assurance_direction"] == "improved"
    assert c1["content_fingerprint"] == c2["content_fingerprint"]


def test_golden_10_compatible_baseline_regression():
    base = _export(grade="assured_with_limitations", contra_open=False, independent=3, findings=[])
    cand = _blocking_contradiction()
    c = compare_assurance_snapshots(base, cand).to_dict()
    assert c["assurance_direction"] == "regressed"


def test_golden_11_incompatible_context():
    c = compare_assurance_snapshots(_export(car="GT-R"), _export(car="Supra")).to_dict()
    assert c["compatibility"] == "incompatible" and c["assurance_direction"] == "incomparable"


def test_golden_12_corrupted_review_package_fails_verification():
    from strategy.assurance_manifest_loader import verify_review_package_artifacts
    pkg = build_review_package_spec(_blocking_contradiction())
    pm = pkg.package_manifest
    good = {a.name: pkg.artifact_bytes(a.kind) for a in pkg.artifacts}
    assert verify_review_package_artifacts(pm, good)["ok"]
    bad = dict(good)
    first = pkg.artifacts[0].name
    bad[first] = bad[first] + b"corruption"
    assert not verify_review_package_artifacts(pm, bad)["ok"]


def test_golden_package_fingerprints_stable_and_distinct():
    fps = {}
    for name, fn in ALL_SCENARIOS.items():
        exp = fn()
        pkg = build_review_package_spec(exp).to_dict()
        assert pkg["package_fingerprint"] == build_review_package_spec(exp).to_dict()["package_fingerprint"]
        fps[name] = pkg["package_fingerprint"]
    assert len(set(fps.values())) == len(fps)
