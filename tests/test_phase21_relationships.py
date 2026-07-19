"""Phase 21 — cross-campaign relationship domain tests.

Every relationship type reachable, evidence-grounded (never inferred), explained + sourced;
isolated detection; deterministic; large-count + duplicate handling; never raises.
"""
import inspect

import pytest

from strategy.cross_campaign_map import (
    CampaignRelationship, build_cross_campaign_map, CROSS_CAMPAIGN_MAP_VERSION,
)


def rec(cid, family="rotation", region="front", fields=("arb_front",), mechanisms=("m1",),
        confidence="medium", opportunity="worth_another_confirmation", conflicting=False,
        unresolved=0, testable=True):
    return {"campaign_id": cid, "objective": f"{family}-{region}", "family": family,
            "region": region, "fields": list(fields), "mechanisms": list(mechanisms),
            "confidence_level": confidence, "opportunity": opportunity,
            "conflicting": conflicting, "unresolved_mechanisms": unresolved, "testable": testable}


def _rel(a, b):
    m = build_cross_campaign_map([a, b])
    return m.edges[0] if m.edges else None


def test_duplicates():
    a = rec("A", family="rotation", region="front", fields=("arb_front",))
    b = rec("B", family="rotation", region="front", fields=("arb_front",))
    e = _rel(a, b)
    assert e["relationship"] == CampaignRelationship.DUPLICATES.value
    assert not e["directional"]


def test_overlaps_same_objective_diff_field():
    a = rec("A", fields=("arb_front",))
    b = rec("B", fields=("springs_front",))
    e = _rel(a, b)
    assert e["relationship"] == CampaignRelationship.OVERLAPS.value


def test_related_same_family_diff_region():
    a = rec("A", family="rotation", region="front", mechanisms=("mx",))
    b = rec("B", family="rotation", region="mid", mechanisms=("my",))
    e = _rel(a, b)
    assert e["relationship"] == CampaignRelationship.RELATED.value


def test_overlaps_shared_field_diff_family():
    a = rec("A", family="rotation", region="front", fields=("arb_front",), mechanisms=("mx",))
    b = rec("B", family="braking", region="rear", fields=("arb_front",), mechanisms=("my",))
    e = _rel(a, b)
    assert e["relationship"] == CampaignRelationship.OVERLAPS.value
    assert "arb_front" in " ".join(e["supporting_evidence"])


def test_contradicts_same_family():
    a = rec("A", family="rotation", region="front", mechanisms=("mx",),
            confidence="very_high", opportunity="not_worth_further_work")
    b = rec("B", family="rotation", region="mid", mechanisms=("my",),
            confidence="low", conflicting=True, opportunity="worth_contradiction_testing")
    e = _rel(a, b)
    assert e["relationship"] == CampaignRelationship.CONTRADICTS.value


def test_depends_on_shared_mechanism():
    a = rec("A", family="traction", region="rear", mechanisms=("m1",), unresolved=1,
            confidence="low", opportunity="worth_mechanism_isolation")
    b = rec("B", family="rotation", region="front", mechanisms=("m1",),
            confidence="very_high", opportunity="not_worth_further_work")
    e = _rel(a, b)
    assert e["relationship"] == CampaignRelationship.DEPENDS_ON.value
    assert e["directional"] and e["from_campaign_id"] == "A" and e["to_campaign_id"] == "B"


def test_supports_shared_mechanism():
    a = rec("A", family="traction", region="rear", mechanisms=("m1",),
            confidence="very_high", opportunity="not_worth_further_work", unresolved=0)
    b = rec("B", family="rotation", region="front", mechanisms=("m1",),
            confidence="medium", opportunity="worth_another_confirmation")
    e = _rel(a, b)
    assert e["relationship"] == CampaignRelationship.SUPPORTS.value
    assert e["directional"] and e["from_campaign_id"] == "A"


def test_blocked_by_related_contradiction():
    a = rec("A", family="rotation", region="front", mechanisms=("mx",),
            confidence="low", opportunity="worth_another_confirmation", conflicting=False)
    b = rec("B", family="rotation", region="mid", mechanisms=("my",),
            confidence="low", conflicting=True, opportunity="worth_contradiction_testing")
    # a needs progress, b is contradictory, same family, different region, no shared mech
    e = _rel(a, b)
    assert e["relationship"] == CampaignRelationship.BLOCKED_BY.value
    assert e["directional"] and e["from_campaign_id"] == "A" and e["to_campaign_id"] == "B"


def test_isolated_when_no_relationship():
    a = rec("A", family="rotation", region="front", fields=("arb_front",), mechanisms=("m1",))
    b = rec("B", family="braking", region="rear", fields=("brake_bias",), mechanisms=("m9",))
    m = build_cross_campaign_map([a, b])
    assert m.edges == () or all(e["relationship"] == "none" for e in m.edges)
    assert set(m.isolated_campaign_ids) == {"A", "B"}


def test_every_edge_explained_and_sourced():
    a = rec("A"); b = rec("B")
    m = build_cross_campaign_map([a, b])
    for e in m.edges:
        assert e["reason"] and e["authority"] and e["supporting_evidence"]


def test_relationship_counts():
    a = rec("A", fields=("arb_front",)); b = rec("B", fields=("arb_front",))
    m = build_cross_campaign_map([a, b])
    assert m.relationship_counts.get("duplicates") == 1


def test_deterministic_and_order_stable():
    campaigns = [rec("A"), rec("B", family="braking", region="rear", mechanisms=("mz",),
                     fields=("brake_bias",)), rec("C", family="rotation", region="front")]
    a = build_cross_campaign_map(campaigns).to_dict()
    b = build_cross_campaign_map(campaigns).to_dict()
    assert a == b


def test_large_campaign_count():
    campaigns = [rec(f"c{i}", family=("rotation" if i % 2 else "braking"),
                     region=("front" if i % 3 else "rear"),
                     fields=(f"field{i % 4}",), mechanisms=(f"m{i % 5}",)) for i in range(40)]
    m = build_cross_campaign_map(campaigns)
    # completes deterministically; edge count is a plain function of the inputs
    assert isinstance(m.edges, tuple)
    assert build_cross_campaign_map(campaigns).to_dict() == m.to_dict()


def test_duplicate_campaign_ids_handled():
    a = rec("dup", fields=("arb_front",)); b = rec("dup", fields=("arb_front",))
    m = build_cross_campaign_map([a, b])
    # a duplicate-id pair still classifies deterministically without raising
    assert isinstance(m.edges, tuple)


def test_never_raises_on_garbage():
    for junk in (None, [], [None, 5], [{"campaign_id": "x"}, None]):
        m = build_cross_campaign_map(junk)
        assert isinstance(m.edges, tuple)


def test_no_forbidden_imports_or_graph_optimisation():
    src = inspect.getsource(__import__("strategy.cross_campaign_map", fromlist=["x"]))
    for banned in ("import sqlite3", "PyQt6", "import random", "random.", "datetime.now",
                   "date.today", "time.time", "from data.session_db", "networkx", "sklearn",
                   "numpy", "scipy", "def optimi", "heapq"):
        assert banned not in src
    assert CROSS_CAMPAIGN_MAP_VERSION == "cross_campaign_map_v1"
