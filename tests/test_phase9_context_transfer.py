"""Engineering Brain Phase 9 — cross-context transfer + matching tests."""
import inspect

import pytest

from strategy import context_transfer as CT
from strategy.development_history import MemoryContextKey, build_development_record
from strategy.context_transfer import (
    TransferKind, TransferStrength, build_context_transfers, classify_context_match,
    group_matched_records, transfer_fingerprint,
)

Q = MemoryContextKey(driver="leon", car="RSR", track="Fuji", layout_id="fc",
                     discipline="Race", gt7_version="1.49", compound="RH")
CLS = {"RSR": "Gr.3", "AMG": "Gr.3", "Supra": "Gr.4"}


def _res(key, typ, state, new=False, present=True):
    return {"issue_key": key, "family": "rotation", "issue_type": typ, "axle": "front",
            "phase": "apex", "segment_id": "T1", "corner_name": "T1",
            "residual_state": state, "is_new": new, "is_regression": False,
            "still_present": present, "protected_good": False, "confidence": "high"}


def _rec(ctx, oid, eid, status, sess, residuals, field="toe_front", windows=None,
         failed=(), at="2026-07-01T10:00"):
    outcome = {"id": oid, "experiment_id": eid, "status": status,
               "confidence_level": "high", "scope_fingerprint": "sf",
               "test_session_id": sess, "protected": [], "failed_directions": list(failed)}
    exp = {"id": eid, "scope_fingerprint": "sf",
           "changes": [{"field": field, "from_value": "1", "to_value": "2",
                        "delta_direction": "increase"}]}
    return build_development_record(outcome, exp, context=ctx, scope_fingerprint="sf",
                                   working_windows=windows or [], residuals=residuals,
                                   recorded_at=at, session_date=at[:10])


# --- matching hierarchy -----------------------------------------------------
def test_direct_match():
    c = MemoryContextKey(driver="leon", car="RSR", track="Fuji", layout_id="fc",
                         discipline="Race", gt7_version="1.49", compound="RM")
    assert classify_context_match(Q, c, car_class_of=CLS)[0] == TransferStrength.DIRECT_MATCH


def test_strong_match_different_track():
    c = MemoryContextKey(driver="leon", car="RSR", track="Spa", layout_id="gp",
                         discipline="Race", gt7_version="1.49")
    assert classify_context_match(Q, c, car_class_of=CLS)[0] == TransferStrength.STRONG_MATCH


def test_related_match_needs_same_class():
    same_cls = MemoryContextKey(driver="leon", car="AMG", track="Fuji", layout_id="fc",
                                discipline="Race")
    diff_cls = MemoryContextKey(driver="leon", car="Supra", track="Fuji", layout_id="fc",
                                discipline="Race")
    assert classify_context_match(Q, same_cls, car_class_of=CLS)[0] == TransferStrength.RELATED_MATCH
    # different class, different car, same driver+track → not RELATED (Gr.4 vs Gr.3)
    assert classify_context_match(Q, diff_cls, car_class_of=CLS)[0] != TransferStrength.RELATED_MATCH


def test_related_needs_class_data():
    c = MemoryContextKey(driver="leon", car="AMG", track="Fuji", layout_id="fc",
                         discipline="Race")
    assert classify_context_match(Q, c, car_class_of={})[0] is None   # no class → excluded


def test_weak_match_different_discipline():
    c = MemoryContextKey(driver="leon", car="RSR", track="Fuji", layout_id="fc",
                         discipline="Qualifying")
    assert classify_context_match(Q, c, car_class_of=CLS)[0] == TransferStrength.WEAK_MATCH


def test_incompatible_context_excluded():
    c = MemoryContextKey(driver="bob", car="Miata", track="Monza", layout_id="gp",
                         discipline="Race")
    assert classify_context_match(Q, c, car_class_of=CLS)[0] is None


def test_every_match_states_a_reason():
    c = MemoryContextKey(driver="leon", car="RSR", track="Fuji", layout_id="fc",
                         discipline="Race", gt7_version="1.49")
    strength, reason = classify_context_match(Q, c, car_class_of=CLS)
    assert strength is not None and reason and "match" in reason


# --- transfers --------------------------------------------------------------
def test_transfers_emitted_and_ranked():
    direct = MemoryContextKey(driver="leon", car="RSR", track="Fuji", layout_id="fc",
                              discipline="Race", gt7_version="1.49", compound="RH")
    strong = MemoryContextKey(driver="leon", car="RSR", track="Spa", layout_id="gp",
                              discipline="Race", gt7_version="1.49")
    recs = [
        _rec(direct, 1, 10, "confirmed_improvement", "300",
             [_res("k", "understeer", "resolved", present=False)]),
        _rec(strong, 2, 11, "regression", "301",
             [_res("k2", "oversteer", "new", new=True)], field="arb_rear"),
    ]
    transfers = build_context_transfers(Q, recs, car_class_of=CLS)
    kinds = {t.kind for t in transfers}
    assert TransferKind.SUCCESSFUL_EXPERIMENT in kinds
    assert TransferKind.FAILED_EXPERIMENT in kinds
    # DIRECT ranks before STRONG
    assert transfers[0].strength == TransferStrength.DIRECT_MATCH


def test_excluded_context_produces_no_transfer():
    none_ctx = MemoryContextKey(driver="bob", car="Miata", track="Monza",
                                layout_id="gp", discipline="Race")
    recs = [_rec(none_ctx, 1, 10, "confirmed_improvement", "999",
                 [_res("k", "understeer", "resolved", present=False)])]
    assert build_context_transfers(Q, recs, car_class_of=CLS) == ()


def test_transfer_deterministic_order_independent():
    direct = MemoryContextKey(driver="leon", car="RSR", track="Fuji", layout_id="fc",
                              discipline="Race", gt7_version="1.49", compound="RH")
    recs = [_rec(direct, i, 10 + i, "confirmed_improvement", str(300 + i),
                 [_res("k", "understeer", "resolved", present=False)],
                 at=f"2026-07-0{i}T10:00") for i in (1, 2, 3)]
    a = build_context_transfers(Q, recs, car_class_of=CLS)
    b = build_context_transfers(Q, list(reversed(recs)), car_class_of=CLS)
    assert transfer_fingerprint(a) == transfer_fingerprint(b)


def test_module_is_pure():
    src = inspect.getsource(CT)
    for banned in ("import random", "random.", "time.time", "datetime.now",
                   "import sqlite3", "PyQt", "requests", "urllib", "openai"):
        assert banned not in src, banned
