"""Phase 34 — assurance snapshot comparison tests: compatibility, deltas, doctrine, determinism."""
import copy

from strategy.assurance_snapshot_comparison import compare_assurance_snapshots
from strategy.assurance_snapshot_comparison_render import render_comparison_text
from tests._assurance_pack_helpers import synthetic_export


def _cmp(base, cand):
    return compare_assurance_snapshots(base, cand).to_dict()


def test_compatible_identity():
    c = _cmp(synthetic_export(), synthetic_export())
    assert c["compatibility"] == "compatible"


def test_partially_compatible_on_version_change():
    c = _cmp(synthetic_export(rule="46.0"), synthetic_export(rule="47.0"))
    assert c["compatibility"] == "partially_compatible"


def test_incompatible_on_car_change_shows_no_trend():
    c = _cmp(synthetic_export(car="GT-R"), synthetic_export(car="Supra"))
    assert c["compatibility"] == "incompatible"
    assert c["assurance_direction"] == "incomparable"
    assert c["finding_deltas"] == [] and c["contradiction_deltas"] == []


def test_unverifiable_on_missing_identity():
    bad = synthetic_export()
    bad["manifest"]["programme_identity"]["car"] = ""
    c = _cmp(bad, synthetic_export())
    assert c["compatibility"] == "unverifiable"
    assert c["assurance_direction"] == "incomparable"


def test_same_snapshot_no_material_changes():
    base = synthetic_export()
    c = _cmp(base, copy.deepcopy(base))
    assert c["assurance_direction"] == "unchanged"
    assert not c["finding_deltas"] and not c["contradiction_deltas"] and not c["priority_deltas"]


def test_assurance_improvement_with_valid_provenance():
    base = synthetic_export(grade="not_assured", contra_open=True, independent=1)
    cand = synthetic_export(grade="assured_with_limitations", contra_open=False, independent=3,
                            findings=[])
    c = _cmp(base, cand)
    assert c["assurance_direction"] == "improved"
    assert any(d["change_type"] == "resolved" for d in c["contradiction_deltas"])
    assert any(d["change_type"] == "removed" and d["baseline"] == "blocking"
               for d in c["finding_deltas"])


def test_assurance_regression():
    base = synthetic_export(grade="assured_with_limitations", contra_open=False, independent=3,
                            findings=[])
    cand = synthetic_export(grade="not_assured", contra_open=True, independent=1)
    c = _cmp(base, cand)
    assert c["assurance_direction"] == "regressed"


def test_contradiction_closed_without_evidence_is_not_resolution():
    base = synthetic_export(grade="not_assured", contra_open=True, independent=1)
    # contradiction closes but independence unchanged (still 1) and grade unchanged
    cand = synthetic_export(grade="not_assured", contra_open=False, independent=1, findings=[])
    c = _cmp(base, cand)
    cds = c["contradiction_deltas"]
    assert cds and cds[0]["change_type"] == "modified"
    assert "unverified" in cds[0]["detail"]
    assert c["assurance_direction"] != "improved"


def test_contradiction_reopened():
    base = synthetic_export(grade="assured_with_limitations", contra_open=False, independent=3,
                            findings=[])
    cand = synthetic_export(grade="not_assured", contra_open=True, independent=3)
    c = _cmp(base, cand)
    assert any(d["change_type"] == "reopened" for d in c["contradiction_deltas"])


def test_finding_added_and_removed_and_modified():
    base = synthetic_export(findings=[{"finding_type": "single_context_reliance", "severity": "major",
                                       "domain": "differential", "source_phase": "P30"}])
    cand = synthetic_export(findings=[{"finding_type": "single_context_reliance", "severity": "moderate",
                                       "domain": "differential", "source_phase": "P30"},
                                      {"finding_type": "stale_knowledge", "severity": "major",
                                       "domain": "differential", "source_phase": "P26"}])
    c = _cmp(base, cand)
    types = {(d["key"], d["change_type"]) for d in c["finding_deltas"]}
    assert any(ct == "added" or ct == "regressed" for _k, ct in types)  # stale_knowledge added
    assert any("single_context" in k and ct == "modified" for k, ct in types)  # severity eased


def test_deleted_evidence_domain_gone_is_incomparable_not_resolution():
    base = synthetic_export(grade="not_assured", contra_open=True, independent=1)
    # candidate has NO domains at all (domain disappeared)
    cand = synthetic_export(grade="insufficient_evidence", contra_open=False, findings=[])
    cand["sections"] = [s for s in cand["sections"]]
    # remove differential from every product so the domain is gone
    for s in cand["sections"]:
        cont = s["content"]
        for k in ("domain_coverage", "items", "assumptions", "contradictions"):
            if k in cont:
                cont[k] = []
    c = _cmp(base, cand)
    cds = c["contradiction_deltas"]
    assert cds and cds[0]["change_type"] == "incomparable"
    assert "domain disappeared" in cds[0]["detail"]


def test_assumption_dropped_without_evidence_not_improvement():
    base = synthetic_export()  # has an independence_assumed assumption
    cand = synthetic_export()
    # remove the assumption but do NOT increase independence or readiness
    for s in cand["sections"]:
        if s["phase_key"] == "phase30_assumptions":
            s["content"]["assumptions"] = []
    c = _cmp(base, cand)
    ads = c["assumption_deltas"]
    assert ads and ads[0]["change_type"] == "removed"
    assert "without establishing evidence" in ads[0]["detail"]


def test_readiness_increase_requires_independence_to_be_improved():
    base = synthetic_export(grade="not_assured", contra_open=True, independent=1)
    # readiness up (conflicted -> ready) but independence unchanged -> unverified
    cand = synthetic_export(grade="not_assured", contra_open=False, independent=1, findings=[])
    c = _cmp(base, cand)
    rds = c["readiness_deltas"]
    assert rds and rds[0]["change_type"] == "modified"
    assert "unverified" in rds[0]["detail"]


def test_readiness_improved_when_independence_up():
    base = synthetic_export(grade="not_assured", contra_open=True, independent=1)
    cand = synthetic_export(grade="assured_with_limitations", contra_open=False, independent=4,
                            findings=[])
    c = _cmp(base, cand)
    assert any(d["change_type"] == "improved" for d in c["readiness_deltas"])


def test_priority_moved_added_removed():
    base = synthetic_export(contra_open=True)   # has a contradiction_discrimination priority
    cand = synthetic_export(contra_open=False, findings=[])  # priority gone
    c = _cmp(base, cand)
    assert any(d["change_type"] == "removed" for d in c["priority_deltas"])


def test_timestamp_difference_ignored_in_fingerprint():
    # our synthetic exports have no build timestamp; identical content -> identical comparison fp
    a = _cmp(synthetic_export(), synthetic_export())
    b = _cmp(synthetic_export(), synthetic_export())
    assert a["content_fingerprint"] == b["content_fingerprint"]


def test_comparison_fingerprint_reacts_to_direction():
    base = synthetic_export(grade="not_assured", contra_open=True, independent=1)
    cand = synthetic_export(grade="assured_with_limitations", contra_open=False, independent=3,
                            findings=[])
    fwd = _cmp(base, cand)["content_fingerprint"]
    rev = _cmp(cand, base)["content_fingerprint"]
    assert fwd != rev   # direction is explicit and material


def test_render_incompatible_shows_no_trend():
    c = _cmp(synthetic_export(car="GT-R"), synthetic_export(car="Supra"))
    txt = render_comparison_text(c).lower()
    assert "no assurance trend" in txt
    assert "improved" not in txt.split("no assurance trend")[0]


def test_render_ascii_clean():
    c = _cmp(synthetic_export(grade="not_assured", contra_open=True, independent=1),
             synthetic_export(grade="assured_with_limitations", contra_open=False, independent=3,
                              findings=[]))
    assert all(ord(ch) < 127 for ch in render_comparison_text(c))
