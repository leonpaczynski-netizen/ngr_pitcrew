"""Phase 39 — context-first evidence pipeline: scoping-before-aggregation, equivalence, overlay."""
from strategy.engineering_context_scope import build_engineering_context_scope
from strategy.context_scoped_chain import build_context_scoped_chain, exact_records
from strategy.context_equivalence import assess_context_equivalence, EquivalenceDecision
from tests._race_engineer_helpers import scope as _scope, ctx, record, change


def _fuji():
    return _scope(track="Fuji", layout="full_course")


# ---- 1/2. pre-aggregation scoping + contamination prevention -------------------------------- #
def test_daytona_records_never_enter_exact_conclusions():
    s = _fuji()
    fuji = [record(f"f{i}", changes=[change("camber_front")], context=ctx(), at=f"2026-01-0{i+1}",
                   session=f"s{i}") for i in range(5)]
    ch = build_context_scoped_chain(s, fuji)
    assert ch.counts["exact_context"] == 5
    assert len(exact_records(fuji, ch)) == 5


def test_exact_fingerprint_invariant_to_100_incompatible_records():
    s = _fuji()
    fuji = [record(f"f{i}", changes=[change("camber_front")], context=ctx(), session=f"s{i}",
                   at=f"2026-01-0{i+1}") for i in range(5)]
    daytona = [record(f"d{i}", changes=[change("final_drive")],
                      context=ctx(track="Daytona", layout="road"), session=f"d{i}",
                      at="2026-02-01") for i in range(100)]
    a = build_context_scoped_chain(s, fuji)
    b = build_context_scoped_chain(s, fuji + daytona)
    # exact conclusions unchanged; only history visibility (full fp / counts) changes.
    assert a.exact_content_fingerprint == b.exact_content_fingerprint
    assert a.content_fingerprint != b.content_fingerprint
    assert b.counts["excluded"] == 100


def test_exact_fingerprint_shuffle_stable():
    import random
    s = _fuji()
    recs = ([record(f"f{i}", changes=[change("camber_front")], context=ctx(), session=f"s{i}",
                    at=f"2026-01-0{i+1}") for i in range(5)]
            + [record(f"d{i}", changes=[change("final_drive")],
                      context=ctx(track="Daytona", layout="road"), session=f"d{i}") for i in range(20)])
    a = build_context_scoped_chain(s, recs)
    r2 = list(recs); random.shuffle(r2)
    assert a.exact_content_fingerprint == build_context_scoped_chain(s, r2).exact_content_fingerprint


# ---- 3. event-condition equivalence --------------------------------------------------------- #
def test_equivalent_event_conditions_only_event_id_differs():
    a = _scope(event="E1").to_dict()
    b = _scope(event="E2").to_dict()
    r = assess_context_equivalence(a, b)
    assert r.decision == EquivalenceDecision.EQUIVALENT_CONDITIONS.value
    assert r.event_id_differs and not r.identity_diffs


def test_materially_different_event_condition_not_exact():
    a = build_engineering_context_scope({"programme": {"car": "P", "discipline": "race",
                                                       "gt7_version": "1", "driver": "L"},
                                         "track": "Fuji", "layout_id": "fc", "tyre_multiplier": "1"})
    b = build_engineering_context_scope({"programme": {"car": "P", "discipline": "race",
                                                       "gt7_version": "1", "driver": "L"},
                                         "track": "Fuji", "layout_id": "fc", "tyre_multiplier": "5"})
    r = assess_context_equivalence(a.to_dict(), b.to_dict())
    assert r.decision == EquivalenceDecision.MATERIALLY_DIFFERENT.value


def test_incompatible_identity_and_transfer_track():
    a = _scope().to_dict()
    assert assess_context_equivalence(a, _scope(car="Mazda").to_dict()).decision == \
        EquivalenceDecision.INCOMPATIBLE.value
    assert assess_context_equivalence(a, _scope(track="Daytona").to_dict()).decision == \
        EquivalenceDecision.TRANSFER_ONLY.value


# ---- 4. transfer-overlay separation --------------------------------------------------------- #
def test_transferable_evidence_is_overlay_not_exact():
    s = _fuji()
    recs = [record("exact", changes=[change("camber_front")], context=ctx()),
            record("dyn", changes=[change("anti_roll_bar_rear")],
                   context=ctx(track="Daytona", layout="road"))]
    ch = build_context_scoped_chain(s, recs)
    assert ch.counts["exact_context"] == 1
    assert ch.counts["explicitly_transferable"] == 1
    # the transferable record is in the overlay and NOT in the exact independence count.
    assert "exact" in ch.exact_record_keys and "dyn" not in ch.exact_record_keys
    assert ch.independence["exact_records"] == 1


def test_adding_incompatible_evidence_cannot_improve_exact_confidence():
    s = _fuji()
    base = [record("e", changes=[change("camber_front")], context=ctx(), session="s1")]
    a = build_context_scoped_chain(s, base)
    b = build_context_scoped_chain(s, base + [record("x", changes=[change("final_drive")],
                                                     context=ctx(track="Daytona", layout="road"))])
    assert a.independence["exact_independent_sessions"] == b.independence["exact_independent_sessions"]
