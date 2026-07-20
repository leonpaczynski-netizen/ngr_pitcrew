"""Phases 33-35 — runtime verification: real temp DB + temp export dir, end-to-end determinism."""
import hashlib
import json
import os
import threading

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PyQt6")

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTimer

from data.session_db import SessionDB
from tests._assurance_pack_helpers import seed_contradiction, applied, KW, real_export


@pytest.fixture(scope="module")
def app():
    a = QApplication.instance() or QApplication([])
    yield a


def _seeded_db(path):
    db = SessionDB(path)
    seed_contradiction(db, 3, 2)
    return db


def test_db_byte_identical_before_and_after_export_and_compare(tmp_path):
    p = str(tmp_path / "r.db")
    db = _seeded_db(p); db.close()
    h0 = hashlib.sha256(open(p, "rb").read()).hexdigest()
    db = SessionDB(p)
    exp = real_export(db)
    db.build_assurance_snapshot_comparison_report(json.dumps(exp), applied_setup=applied(),
                                                  now_date="2026-07-10", **KW)
    db.build_assurance_review_package_report(baseline=None, applied_setup=applied(),
                                             now_date="2026-07-10", **KW)
    uv = db._conn.execute("PRAGMA user_version").fetchone()[0]
    db.close()
    assert uv == 27
    assert hashlib.sha256(open(p, "rb").read()).hexdigest() == h0


def test_repeated_and_restart_export_byte_identical(tmp_path):
    p = str(tmp_path / "r.db")
    db = _seeded_db(p)
    e1 = real_export(db); db.close()
    db = SessionDB(p)  # restart
    e2 = real_export(db); db.close()
    assert e1["content_fingerprint"] == e2["content_fingerprint"]
    from strategy.assurance_chain_serialization import canonical_json
    assert canonical_json(e1) == canonical_json(e2)


def test_shuffled_row_order_identical_export(tmp_path):
    # two DBs with the same records inserted in a different order -> identical export
    from tests._assurance_pack_helpers import _mk
    pa, pb = str(tmp_path / "a.db"), str(tmp_path / "b.db")
    da = SessionDB(pa)
    order_a = [("c", 0, "rotation"), ("c", 1, "traction"), ("c", 2, "braking"), ("r", 0, "rotation"),
               ("r", 1, "rotation")]
    for kind, i, fam in order_a:
        _mk(da, f"{kind}{i}", "confirmed_improvement" if kind == "c" else "regression",
            i if kind == "c" else i + 3, fam=fam)
    ea = real_export(da); da.close()
    db = SessionDB(pb)
    for kind, i, fam in reversed(order_a):
        _mk(db, f"{kind}{i}", "confirmed_improvement" if kind == "c" else "regression",
            i if kind == "c" else i + 3, fam=fam)
    eb = real_export(db); db.close()
    assert ea["content_fingerprint"] == eb["content_fingerprint"]


def test_package_manifest_verifies_independently(tmp_path):
    from strategy.assurance_review_package import build_review_package_spec
    from data.assurance_review_package_writer import write_review_package
    from strategy.assurance_manifest_loader import (parse_canonical_json,
                                                    verify_review_package_artifacts)
    db = _seeded_db(str(tmp_path / "r.db"))
    exp = real_export(db); db.close()
    pkg = build_review_package_spec(exp)
    dest = str(tmp_path / "out")
    res = write_review_package(pkg, dest, make_archive=True).to_dict()
    assert res["ok"]
    pm, err = parse_canonical_json(open(os.path.join(dest, "package_manifest.json"), "rb").read())
    assert err is None
    by_name = {a.name: open(os.path.join(dest, a.name), "rb").read() for a in pkg.artifacts}
    assert verify_review_package_artifacts(pm, by_name)["ok"]
    # corrupt a file on disk -> independent verification fails
    with open(os.path.join(dest, pkg.artifacts[0].name), "ab") as fh:
        fh.write(b"\ncorruption")
    by_name2 = {a.name: open(os.path.join(dest, a.name), "rb").read() for a in pkg.artifacts}
    assert not verify_review_package_artifacts(pm, by_name2)["ok"]


def test_dashboard_export_end_to_end_off_thread_no_db_mutation(app, tmp_path):
    """Drive MainWindow._start_assurance_review_export on a stub: it builds + writes OFF the Qt
    thread, reports the destination, and mutates no DB."""
    import ui.dashboard as dash

    p = str(tmp_path / "r.db")
    db = _seeded_db(p); db.close()
    h0 = hashlib.sha256(open(p, "rb").read()).hexdigest()
    db = SessionDB(p)

    class _Panel:
        def __init__(self): self.status = None
        def update_export_status(self, r): self.status = r

    class _Page:
        def __init__(self): self._review_pack_panel = _Panel()

    stub = dash.MainWindow.__new__(dash.MainWindow)
    stub._db = db
    stub._development_history_page = _Page()
    stub._assurance_review_ctx = (KW["car"], KW["track"], KW["layout_id"], KW["discipline"])
    stub._assurance_baseline_text = None
    stub._active_setup_for_current = lambda purpose: None  # no applied setup -> still exports

    dest = str(tmp_path / "export_out")
    main_thread = threading.get_ident()

    # wrap the ready handler to capture + quit the loop
    captured = {}
    orig_ready = dash.MainWindow._on_assurance_review_export_ready

    def ready(self, result, worker=None):
        captured["result"] = result
        captured["thread"] = threading.get_ident()
        orig_ready(self, result, worker)
        app.quit()
    dash.MainWindow._on_assurance_review_export_ready = ready
    try:
        QTimer.singleShot(0, lambda: stub._start_assurance_review_export(dest, make_archive=False))
        QTimer.singleShot(8000, app.quit)
        app.exec()
    finally:
        dash.MainWindow._on_assurance_review_export_ready = orig_ready
    worker = getattr(stub, "_review_export_worker", None)
    if worker is not None:
        worker.wait(2000)

    assert captured.get("result", {}).get("ok"), captured.get("result")
    assert captured["thread"] == main_thread   # the RESULT is delivered on the UI thread
    assert stub._development_history_page._review_pack_panel.status.get("destination") == dest
    assert os.path.exists(os.path.join(dest, "package_manifest.json"))
    uv = db._conn.execute("PRAGMA user_version").fetchone()[0]
    db.close()
    assert uv == 27
    assert hashlib.sha256(open(p, "rb").read()).hexdigest() == h0   # export did not mutate the DB


def test_dashboard_export_refuses_without_destination(app, tmp_path):
    import ui.dashboard as dash

    class _Panel:
        def __init__(self): self.status = None
        def update_export_status(self, r): self.status = r

    class _Page:
        def __init__(self): self._review_pack_panel = _Panel()

    stub = dash.MainWindow.__new__(dash.MainWindow)
    stub._db = SessionDB(str(tmp_path / "r.db"))
    stub._development_history_page = _Page()
    stub._assurance_review_ctx = (KW["car"], KW["track"], KW["layout_id"], KW["discipline"])
    stub._start_assurance_review_export("")   # no destination
    assert stub._development_history_page._review_pack_panel.status == {
        "ok": False, "errors": ["no destination selected"]}
    stub._db.close()
