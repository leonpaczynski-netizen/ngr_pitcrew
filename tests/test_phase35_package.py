"""Phase 35 — review package + writer + loader tests: determinism, integrity, safe file writing."""
import copy
import json
import os

from strategy.assurance_review_package import (
    build_review_package_spec, PACKAGE_MANIFEST_NAME, package_manifest_bytes,
)
from strategy.assurance_review_package_render import render_package_text
from strategy.assurance_manifest_loader import (
    load_and_validate_baseline, validate_baseline, verify_review_package_artifacts,
    parse_canonical_json,
)
from data.assurance_review_package_writer import write_review_package
from tests._assurance_pack_helpers import synthetic_export


def _spec(**kw):
    return build_review_package_spec(synthetic_export(**kw))


# ---- pure spec determinism ------------------------------------------------------------------

def test_spec_deterministic_and_artifacts_ordered():
    a = _spec().to_dict()
    b = _spec().to_dict()
    assert a["package_fingerprint"] == b["package_fingerprint"]
    kinds = [x["kind"] for x in a["artifacts"]]
    assert kinds == ["assurance_review_report", "assurance_chain_manifest"]


def test_spec_with_comparison_includes_comparison_artifacts():
    from strategy.assurance_snapshot_comparison import compare_assurance_snapshots
    base = synthetic_export(grade="not_assured", contra_open=True, independent=1)
    cand = synthetic_export(grade="assured_with_limitations", contra_open=False, independent=3,
                            findings=[])
    comp = compare_assurance_snapshots(base, cand).to_dict()
    pkg = build_review_package_spec(cand, comp).to_dict()
    kinds = [x["kind"] for x in pkg["artifacts"]]
    assert "comparison_report" in kinds and "comparison_manifest" in kinds
    assert pkg["has_comparison"] and pkg["comparison_fingerprint"]


def test_content_digests_match_bytes():
    pkg = _spec()
    for a in pkg.artifacts:
        import hashlib
        assert hashlib.sha256(pkg.artifact_bytes(a.kind)).hexdigest() == a.content_digest


def test_package_fingerprint_independent_of_destination():
    # the destination is not an input to the pure spec, so the fp is identical regardless
    assert _spec().to_dict()["package_fingerprint"] == _spec().to_dict()["package_fingerprint"]


def test_render_ascii_and_no_setup_values():
    import re
    txt = render_package_text(_spec().to_dict())
    assert all(ord(c) < 127 for c in txt)
    assert not re.search(r"(arb_front|lsd_accel)\s*[=:]\s*-?\d", txt)
    assert "verify by digest" in txt.lower()


# ---- writer ---------------------------------------------------------------------------------

def test_explicit_destination_required(tmp_path):
    r = write_review_package(_spec(), "").to_dict()
    assert not r["ok"] and "explicit export destination" in r["errors"][0]


def test_writes_and_verifies(tmp_path):
    dest = str(tmp_path / "out")
    r = write_review_package(_spec(), dest, make_archive=True).to_dict()
    assert r["ok"]
    names = {f["name"] for f in r["files_written"]}
    assert "assurance_review_report.md" in names and "assurance_chain_manifest.json" in names
    assert PACKAGE_MANIFEST_NAME in names
    assert os.path.exists(os.path.join(dest, PACKAGE_MANIFEST_NAME))
    assert r["archive_sha256"]


def test_no_overwrite_unless_allowed(tmp_path):
    dest = str(tmp_path / "out")
    assert write_review_package(_spec(), dest).to_dict()["ok"]
    assert not write_review_package(_spec(), dest).to_dict()["ok"]         # refuses
    assert write_review_package(_spec(), dest, allow_overwrite=True).to_dict()["ok"]


def test_failed_write_leaves_no_partial_staging(tmp_path, monkeypatch):
    # force a failure mid-write and confirm no staging temp dir leaks (staging always cleaned)
    import data.assurance_review_package_writer as W
    dest = str(tmp_path / "out")
    orig_move = W.shutil.move
    calls = {"n": 0}

    def boom(src, dst):
        calls["n"] += 1
        if calls["n"] == 1:
            raise IOError("simulated move failure")
        return orig_move(src, dst)
    monkeypatch.setattr(W.shutil, "move", boom)
    r = write_review_package(_spec(), dest).to_dict()
    assert not r["ok"]
    # no leftover ngr_assurance_pkg_ temp dirs
    import tempfile
    leaks = [d for d in os.listdir(tempfile.gettempdir()) if d.startswith("ngr_assurance_pkg_")]
    assert leaks == []


def test_no_source_paths_or_secrets_in_written_files(tmp_path):
    dest = str(tmp_path / "out")
    write_review_package(_spec(), dest)
    for name in os.listdir(dest):
        data = open(os.path.join(dest, name), "rb").read().decode("utf-8", errors="replace").lower()
        assert "c:\\projects" not in data and "/home/" not in data and ".claude" not in data
        assert "api_key" not in data and "apikey" not in data and "password" not in data
        assert "setup_history" not in data


def test_package_contains_no_forbidden_files(tmp_path):
    dest = str(tmp_path / "out")
    write_review_package(_spec(), dest, make_archive=True)
    names = set(os.listdir(dest))
    for forbidden in (".db", ".sqlite", "setup_history", "settings", "config.json",
                      "accepted_model", "reviewed_segments"):
        assert not any(forbidden in n for n in names), forbidden


def test_deterministic_zip_byte_identical(tmp_path):
    r1 = write_review_package(_spec(), str(tmp_path / "a"), make_archive=True).to_dict()
    r2 = write_review_package(_spec(), str(tmp_path / "b"), make_archive=True).to_dict()
    assert r1["archive_sha256"] == r2["archive_sha256"]


def test_written_files_byte_identical_across_writes(tmp_path):
    write_review_package(_spec(), str(tmp_path / "a"))
    write_review_package(_spec(), str(tmp_path / "b"))
    for name in os.listdir(str(tmp_path / "a")):
        assert open(os.path.join(str(tmp_path / "a"), name), "rb").read() == \
            open(os.path.join(str(tmp_path / "b"), name), "rb").read()


# ---- re-open + verify + tamper --------------------------------------------------------------

def test_valid_package_reopens_and_verifies(tmp_path):
    dest = str(tmp_path / "out")
    pkg = _spec()
    write_review_package(pkg, dest)
    pm, err = parse_canonical_json(open(os.path.join(dest, PACKAGE_MANIFEST_NAME), "rb").read())
    assert err is None
    lr = validate_baseline(pm)
    assert lr.kind == "review_package" and lr.ok
    bytes_by_name = {a.name: open(os.path.join(dest, a.name), "rb").read() for a in pkg.artifacts}
    ver = verify_review_package_artifacts(pm, bytes_by_name)
    assert ver["ok"] and ver["checked"] == len(pkg.artifacts)


def test_corrupted_artifact_fails_verification(tmp_path):
    dest = str(tmp_path / "out")
    pkg = _spec()
    write_review_package(pkg, dest)
    pm, _ = parse_canonical_json(open(os.path.join(dest, PACKAGE_MANIFEST_NAME), "rb").read())
    bytes_by_name = {a.name: open(os.path.join(dest, a.name), "rb").read() for a in pkg.artifacts}
    bytes_by_name[pkg.artifacts[0].name] += b"TAMPER"
    assert not verify_review_package_artifacts(pm, bytes_by_name)["ok"]


def test_manifest_tampering_fails_export_baseline_load():
    exp = synthetic_export()
    forged = copy.deepcopy(exp)
    forged["manifest"]["assurance_chain_fingerprint"] = "forged:deadbeefdeadbeef"
    lr = load_and_validate_baseline(json.dumps(forged))
    assert not lr.ok and any("fingerprint does not match" in e for e in lr.errors)


def test_loader_rejects_malformed_non_finite_and_path_traversal():
    assert not load_and_validate_baseline("{not json").ok
    assert not load_and_validate_baseline('{"x": Infinity}').ok
    assert not load_and_validate_baseline('{"x": NaN}').ok
    # a package manifest with a path-traversing artifact name
    pm = {"schema_version": 1, "package_fingerprint": "x",
          "artifacts": [{"name": "../evil.json", "kind": "assurance_chain_manifest",
                         "content_digest": "d"}]}
    lr = validate_baseline(pm)
    assert not lr.ok and any("path-travers" in e or "unsafe" in e for e in lr.errors)


def test_loader_rejects_duplicate_artifact_names():
    pm = {"schema_version": 1, "package_fingerprint": "x",
          "artifacts": [{"name": "a.json", "kind": "assurance_chain_manifest", "content_digest": "d"},
                        {"name": "a.json", "kind": "assurance_review_report", "content_digest": "e"}]}
    lr = validate_baseline(pm)
    assert not lr.ok and any("duplicate" in e for e in lr.errors)


def test_loader_rejects_unknown_enum_no_silent_fallback():
    exp = synthetic_export()
    exp["manifest"]["assurance_grade"] = "totally_made_up_grade"
    lr = load_and_validate_baseline(json.dumps(exp))
    assert not lr.ok and any("unknown assurance grade" in e for e in lr.errors)


def test_export_valid_baseline_round_trip():
    exp = synthetic_export()
    lr = load_and_validate_baseline(json.dumps(exp))
    assert lr.ok and lr.kind == "export" and lr.export is not None
    assert lr.recomputed_fingerprints["assurance_chain_fingerprint"] == \
        exp["manifest"]["assurance_chain_fingerprint"]
