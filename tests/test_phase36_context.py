"""Phase 36 — canonical context identity, completeness, context-safe knowledge activation."""
from strategy.engineering_context_scope import (
    build_engineering_context_scope, relate_context, ContextRelation, SetupDiscipline,
    ContextCompleteness,
)
from strategy.contextual_knowledge_activation import activate_context_knowledge, EvidenceClass
from tests._race_engineer_helpers import scope, ctx, record, change


# ---- 1. context identity and completeness --------------------------------------------------- #
def test_context_fingerprint_stable_across_rebuild():
    s1 = scope(); s2 = scope()
    assert s1.context_fingerprint() == s2.context_fingerprint()


def test_missing_context_is_explicit_not_empty_collision():
    s = build_engineering_context_scope({"programme": {"car": "A"}})
    assert s.completeness() is ContextCompleteness.INSUFFICIENT  # no track
    assert "track" in s.missing_core()


def test_completeness_grades():
    assert scope().completeness() is ContextCompleteness.COMPLETE
    partial = build_engineering_context_scope({"programme": {"car": "A"}, "track": "Fuji"})
    assert partial.completeness() is ContextCompleteness.PARTIAL


def test_discipline_normalisation():
    assert build_engineering_context_scope({"programme": {"discipline": "quali"}}).discipline \
        is SetupDiscipline.QUALIFYING


# ---- fingerprint identity invariants (property) --------------------------------------------- #
def test_different_identity_never_collides():
    base = scope()
    for kw in ({"driver": "Other"}, {"car": "Mazda"}, {"track": "Daytona"},
               {"layout": "road"}, {"discipline": "qualifying"}):
        assert scope(**kw).context_fingerprint() != base.context_fingerprint(), kw


def test_object_identity_and_order_excluded():
    # two scopes built from dict keys in different insertion order -> identical fingerprint.
    a = build_engineering_context_scope({"track": "Fuji", "programme": {"car": "A", "driver": "d"},
                                         "layout_id": "fc", "discipline": "race", "gt7_version": "1"})
    b = build_engineering_context_scope({"programme": {"driver": "d", "car": "A"},
                                         "discipline": "race", "layout_id": "fc", "track": "Fuji",
                                         "gt7_version": "1"})
    assert a.context_fingerprint() == b.context_fingerprint()


# ---- 2. compatibility and transfer classification ------------------------------------------- #
def test_relate_exact_requires_full_identity():
    s = scope()
    assert relate_context(s, ctx()) is ContextRelation.EXACT
    # same driver+car alone (different track) is NOT exact
    assert relate_context(s, ctx(track="Daytona", layout="road")) is ContextRelation.SAME_CAR_OTHER_TRACK


def test_relate_unverifiable_without_identity():
    assert relate_context(scope(), {"driver": "Leon"}) is ContextRelation.UNVERIFIABLE


# ---- 3. context contamination prevention ---------------------------------------------------- #
def test_daytona_gearbox_excluded_dynamics_transferable():
    s = scope()
    recs = [
        record("r_exact", changes=[change("natural_frequency_front")], context=ctx()),
        record("r_dyn", changes=[change("anti_roll_bar_rear")], context=ctx(track="Daytona", layout="road")),
        record("r_gear", changes=[change("final_drive")], context=ctx(track="Daytona", layout="road")),
        record("r_other_car", changes=[change("camber_front")], context=ctx(car="Mazda")),
    ]
    act = activate_context_knowledge(s, recs)
    by = {i["record_key"]: i["classification"] for i in act.items}
    assert by["r_exact"] == EvidenceClass.EXACT_CONTEXT.value
    assert by["r_dyn"] == EvidenceClass.EXPLICITLY_TRANSFERABLE.value
    assert by["r_gear"] == EvidenceClass.EXCLUDED.value       # gearbox never transfers across tracks
    assert by["r_other_car"] == EvidenceClass.EXCLUDED.value
    assert act.contamination_guard  # excluded items are surfaced with a reason


def test_activation_shuffle_stable():
    s = scope()
    recs = [record(f"r{i}", changes=[change("camber_front")], context=ctx(), at=f"2026-01-0{i+1}")
            for i in range(4)]
    a = activate_context_knowledge(s, recs)
    b = activate_context_knowledge(s, list(reversed(recs)))
    assert a.content_fingerprint == b.content_fingerprint


def test_adding_incompatible_evidence_cannot_raise_exact_count():
    s = scope()
    exact = [record("e", changes=[change("camber_front")], context=ctx())]
    a = activate_context_knowledge(s, exact)
    b = activate_context_knowledge(s, exact + [
        record("x", changes=[change("final_drive")], context=ctx(track="Daytona", layout="road"))])
    assert b.counts["exact_context"] == a.counts["exact_context"]
