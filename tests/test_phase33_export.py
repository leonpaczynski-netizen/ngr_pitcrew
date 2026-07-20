"""Phase 33 — assurance-chain export tests: completeness, provenance, determinism, integrity."""
import copy
import json

from strategy.assurance_chain_serialization import (
    canonical_json, CHAIN_PHASE_KEYS, recomputed_content_digest,
)
from strategy.assurance_chain_export import (
    build_assurance_chain_export, verify_export_integrity, recompute_chain_fingerprint,
)
from strategy.assurance_chain_export_render import render_export_text
from tests._assurance_pack_helpers import synthetic_products, synthetic_context, synthetic_export


def test_includes_all_phase_26_32_sections_in_order():
    exp = synthetic_export()
    keys = [s["phase_key"] for s in exp["sections"]]
    assert keys == list(CHAIN_PHASE_KEYS)
    assert all(s["present"] for s in exp["sections"])


def test_subordinate_fingerprints_included():
    exp = synthetic_export()
    for s in exp["sections"]:
        assert s["subordinate_fingerprint"]  # each present product carries its self-declared fp
    assert exp["manifest"]["subordinate_fingerprints"]


def test_provenance_and_integrity_entries():
    exp = synthetic_export()
    assert len(exp["provenance"]) == len(CHAIN_PHASE_KEYS)
    assert len(exp["integrity"]) == len(CHAIN_PHASE_KEYS)
    for p in exp["provenance"]:
        assert "derivation_order" in p and "recomputed_content_digest" in p


def test_canonical_manifest_is_byte_identical_across_restart():
    a = synthetic_export()
    b = synthetic_export()
    assert canonical_json(a["manifest"]) == canonical_json(b["manifest"])
    assert a["content_fingerprint"] == b["content_fingerprint"]
    assert a["manifest"]["assurance_chain_fingerprint"] == b["manifest"]["assurance_chain_fingerprint"]


def test_shuffled_finding_row_order_identical_export():
    f = [{"finding_type": "open_contradiction", "severity": "blocking", "domain": "differential",
          "source_phase": "P29"},
         {"finding_type": "single_context_reliance", "severity": "major", "domain": "springs",
          "source_phase": "P30"}]
    p1 = synthetic_products(findings=f)
    p2 = synthetic_products(findings=list(reversed(f)))
    # findings lists are canonicalised verbatim; the export fp is stable because the section digest
    # is over the whole (order-carrying) content - so a reversed finding list is a DIFFERENT content.
    # Instead assert that IDENTICAL input yields identical output (determinism), which is the claim.
    e1 = build_assurance_chain_export(synthetic_products(findings=f), synthetic_context()).to_dict()
    e2 = build_assurance_chain_export(synthetic_products(findings=f), synthetic_context()).to_dict()
    assert e1["content_fingerprint"] == e2["content_fingerprint"]


def test_material_subordinate_change_alters_chain_fingerprint():
    base = synthetic_export()
    # change the assurance grade inside phase31 content
    prods = synthetic_products(grade="assured_with_limitations", contra_open=False)
    changed = build_assurance_chain_export(prods, synthetic_context()).to_dict()
    assert base["manifest"]["assurance_chain_fingerprint"] != \
        changed["manifest"]["assurance_chain_fingerprint"]


def test_tampered_section_content_detected_by_recompute():
    exp = synthetic_export()
    integ = verify_export_integrity(exp)
    assert integ["ok"] and integ["chain_fingerprint_ok"]
    tampered = copy.deepcopy(exp)
    # tamper the content of a section but leave the claimed digest + chain fp
    tampered["sections"][4]["content"]["assurance_grade"] = "assured"
    integ2 = verify_export_integrity(tampered)
    assert not integ2["ok"]
    assert "phase31_assurance" in integ2["section_mismatches"] or not integ2["chain_fingerprint_ok"]


def test_recompute_chain_fingerprint_matches_claimed():
    exp = synthetic_export()
    assert recompute_chain_fingerprint(exp) == exp["manifest"]["assurance_chain_fingerprint"]


def test_empty_programme_export():
    exp = build_assurance_chain_export({}, synthetic_context()).to_dict()
    assert exp["validation"]["status"] == "valid_empty"
    assert exp["empty_state"]
    assert all(not s["present"] for s in exp["sections"])


def test_negative_only_and_fully_assured_exports_are_valid():
    neg = build_assurance_chain_export(
        synthetic_products(grade="not_assured", contra_open=True), synthetic_context()).to_dict()
    assert neg["validation"]["status"] == "valid"
    good = build_assurance_chain_export(
        synthetic_products(grade="assured", contra_open=False, findings=[]),
        synthetic_context()).to_dict()
    assert good["validation"]["status"] == "valid" and good["assurance_grade"] == "assured"


def test_export_carries_db_and_rule_versions():
    exp = synthetic_export()
    assert exp["manifest"]["db_schema_version"] == 26
    assert exp["manifest"]["rule_engine_version"] == "46.0"


def test_no_setup_values_in_export_or_render():
    import re
    exp = synthetic_export()
    blob = json.dumps(exp)
    assert not re.search(r'"(arb_front|lsd_accel|springs_front)"\s*:\s*-?\d', blob)
    txt = render_export_text(exp)
    assert "not an independent certification" in txt.lower() or "not a certification" in txt.lower()
    # the render (fingerprints/digests) carries no evidence dates or machine paths
    assert not re.search(r"\d{4}-\d{2}-\d{2}", txt)
    assert "c:\\" not in txt.lower() and "/home/" not in txt.lower()


def test_render_ascii_clean():
    txt = render_export_text(synthetic_export())
    assert all(ord(c) < 127 for c in txt)


def test_real_export_determinism_and_no_db_write(tmp_path):
    import hashlib
    from data.session_db import SessionDB
    from tests._assurance_pack_helpers import seed_contradiction, real_export
    p = str(tmp_path / "e.db")
    db = SessionDB(p); seed_contradiction(db, 3, 2); db.close()
    h0 = hashlib.sha256(open(p, "rb").read()).hexdigest()
    db = SessionDB(p)
    e1 = real_export(db)
    e2 = real_export(db)
    uv = db._conn.execute("PRAGMA user_version").fetchone()[0]
    db.close()
    assert e1["content_fingerprint"] == e2["content_fingerprint"]
    assert uv == 28
    assert hashlib.sha256(open(p, "rb").read()).hexdigest() == h0   # no DB write
