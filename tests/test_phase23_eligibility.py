"""Phase 23 — transfer-eligibility + reuse-summary domain tests.

Transfer level decided only by deterministic rules + domain class; established-source gating;
gearbox/context-bound/driver-specific handling; reuse summary + isolation; determinism; never
raises.
"""
import inspect

import pytest

from strategy.knowledge_transfer import (
    TransferLevel, evaluate_transfer, KNOWLEDGE_TRANSFER_VERSION,
)
from strategy.engineering_reuse import summarise_reuse, ENGINEERING_REUSE_VERSION

PORSCHE = "Porsche 911 RSR (991) '17"
PORSCHE_CUP = "Porsche 911 GT3 Cup"
TOYOTA = "Toyota GR Supra Racing Concept Gr.3"


def dom(name, maturity="mature", mechs=("load_transfer",), conf="high", state="well_understood",
        cids=("c1",)):
    return {"domain": name, "maturity": {"value": maturity}, "confidence": {"value": conf},
            "knowledge_state": {"value": state}, "supporting_mechanisms": list(mechs),
            "supporting_campaigns": list(cids)}


def ctx(car, gt7="1.49", driver="leon", discipline="Race"):
    return {"car": car, "discipline": discipline, "gt7_version": gt7, "driver": driver}


def test_unestablished_source_not_transferable():
    c = evaluate_transfer(dom("springs", maturity="emerging"), ctx(PORSCHE), ctx(PORSCHE_CUP))
    assert c.transfer_level == TransferLevel.NOT_TRANSFERABLE.value
    assert "established" in c.reason.lower()


def test_architecture_same_family_supported():
    # same manufacturer + category + drivetrain + mechanism + mature -> SUPPORTED
    c = evaluate_transfer(dom("springs"), ctx(PORSCHE), ctx(PORSCHE_CUP))
    assert c.transfer_level == TransferLevel.SUPPORTED.value


def test_architecture_different_manufacturer_low():
    # only category shared -> LOW
    c = evaluate_transfer(dom("springs"), ctx(PORSCHE), ctx(TOYOTA))
    assert c.transfer_level in (TransferLevel.LOW.value, TransferLevel.MEDIUM.value)
    assert any("manufacturer" in lim for lim in c.limitations)


def test_context_bound_never_transfers():
    c = evaluate_transfer(dom("track_segments"), ctx(PORSCHE), ctx(PORSCHE_CUP))
    assert c.transfer_level == TransferLevel.NOT_TRANSFERABLE.value
    assert "track" in c.reason.lower()


def test_gearbox_not_transferable_by_default():
    # same car family but gearbox is car/track specific -> at most LOW (explicitly supported)
    c = evaluate_transfer(dom("gearbox"), ctx(PORSCHE), ctx(PORSCHE_CUP))
    assert c.transfer_level in (TransferLevel.LOW.value, TransferLevel.NOT_TRANSFERABLE.value)


def test_gearbox_different_manufacturer_not_transferable():
    c = evaluate_transfer(dom("gearbox"), ctx(PORSCHE), ctx(TOYOTA))
    assert c.transfer_level == TransferLevel.NOT_TRANSFERABLE.value


def test_driver_specific_same_driver_transfers():
    same = evaluate_transfer(dom("driver_technique"), ctx(PORSCHE, driver="leon"),
                             ctx(PORSCHE_CUP, driver="leon"))
    diff = evaluate_transfer(dom("driver_technique"), ctx(PORSCHE, driver="leon"),
                             ctx(PORSCHE_CUP, driver="sam"))
    assert same.transfer_level != TransferLevel.NOT_TRANSFERABLE.value
    assert diff.transfer_level == TransferLevel.NOT_TRANSFERABLE.value


def test_version_incompatible_caps_low():
    c = evaluate_transfer(dom("springs"), ctx(PORSCHE, gt7="1.49"), ctx(PORSCHE, gt7="2.0"))
    assert c.transfer_level in (TransferLevel.VERY_LOW.value, TransferLevel.NOT_TRANSFERABLE.value)


def test_handling_transfers_on_drivetrain():
    # vehicle_balance: same drivetrain + layout -> HIGH/SUPPORTED
    c = evaluate_transfer(dom("vehicle_balance"), ctx(PORSCHE), ctx(PORSCHE_CUP))
    assert c.transfer_level in (TransferLevel.HIGH.value, TransferLevel.SUPPORTED.value)


def test_confidence_reused_from_source():
    c = evaluate_transfer(dom("springs", conf="very_high"), ctx(PORSCHE), ctx(PORSCHE_CUP))
    assert c.confidence["value"] == "very_high"


def test_candidate_fields_explained():
    c = evaluate_transfer(dom("springs"), ctx(PORSCHE), ctx(PORSCHE_CUP)).to_dict()
    assert c["reason"] and c["supporting_evidence"]["source"] and c["confidence"]["reason"]


def test_deterministic():
    args = (dom("springs"), ctx(PORSCHE), ctx(PORSCHE_CUP))
    assert evaluate_transfer(*args).to_dict() == evaluate_transfer(*args).to_dict()


def test_never_raises_on_garbage():
    for junk in (None, {}, {"domain": None}):
        c = evaluate_transfer(junk, junk, junk)
        assert c.transfer_level in {lv.value for lv in TransferLevel}


# --- reuse summary ----------------------------------------------------------
def test_reuse_summary_groups_and_isolates():
    cands = [
        evaluate_transfer(dom("springs"), ctx(PORSCHE), ctx(PORSCHE_CUP)).to_dict(),      # supported
        evaluate_transfer(dom("gearbox"), ctx(PORSCHE), ctx(TOYOTA)).to_dict(),           # not_transferable
        evaluate_transfer(dom("springs"), ctx(PORSCHE), ctx(TOYOTA)).to_dict(),           # low/medium
    ]
    s = summarise_reuse(cands).to_dict()
    assert s["counts"]["reusable"] >= 1
    assert s["counts"]["not_reusable"] >= 1
    # Toyota target has no reusable candidate -> isolated
    assert any(t["car"] == TOYOTA for t in s["isolated_targets"])


def test_reuse_statements_present():
    cands = [evaluate_transfer(dom("springs"), ctx(PORSCHE), ctx(PORSCHE_CUP)).to_dict()]
    s = summarise_reuse(cands).to_dict()
    assert s["reusable"][0]["statement"].startswith("This 'springs' knowledge is reusable")


def test_reuse_never_raises():
    for junk in (None, [None], [{"transfer_level": None}]):
        s = summarise_reuse(junk)
        assert s.eval_version == ENGINEERING_REUSE_VERSION


def test_no_forbidden_imports():
    for mod in ("strategy.knowledge_transfer", "strategy.engineering_reuse"):
        src = inspect.getsource(__import__(mod, fromlist=["x"]))
        for banned in ("import sqlite3", "PyQt6", "import random", "random.", "datetime.now",
                       "date.today", "time.time", "from data.session_db", "sklearn", "numpy",
                       "networkx", "def optimi", "argmax", "def apply", "copy_setup",
                       "import_setup"):
            assert banned not in src, f"{mod}: {banned}"
    assert KNOWLEDGE_TRANSFER_VERSION == "knowledge_transfer_v1"
