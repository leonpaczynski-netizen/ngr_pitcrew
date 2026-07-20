"""Phase 22 — engineering knowledge-graph domain tests.

Field/family/mechanism → domain mapping is visible + non-inferred; each domain aggregates its
contributing campaigns with maturity/confidence/evidence/limitations; missing domains surfaced;
deterministic; large graphs + empty safe; never raises.
"""
import inspect

import pytest

from strategy.engineering_knowledge_graph import (
    KnowledgeDomain, build_knowledge_graph, ENGINEERING_KNOWLEDGE_GRAPH_VERSION,
    _domains_for_campaign,
)


def camp(cid, family="", fields=(), mech=(), conf="medium", state="needs_confirmation",
         track="Fuji", executed=2, confirmations=1, reg=0, unresolved=0, info="low",
         testable=True):
    return {"campaign_id": cid, "objective": cid, "status": "active", "family": family,
            "region": "front", "car": "RSR", "track": track, "layout": "fc",
            "discipline": "Race", "fields": list(fields), "mechanisms": list(mech),
            "confidence_level": conf, "knowledge_state": state, "confirmations": confirmations,
            "regressions": reg, "conflicting": (confirmations > 0 and reg > 0),
            "unresolved_mechanisms": unresolved, "executed": executed,
            "remaining_information_gain": info, "testable": testable}


def _domain(graph, name):
    return next((d for d in graph.to_dict()["domains"] if d["domain"] == name), None)


def test_field_maps_to_domain():
    assert KnowledgeDomain.DIFFERENTIAL in _domains_for_campaign(camp("c", fields=["lsd_accel"]))
    assert KnowledgeDomain.ANTI_ROLL_BARS in _domains_for_campaign(camp("c", fields=["arb_front"]))
    assert KnowledgeDomain.SPRINGS in _domains_for_campaign(camp("c", fields=["springs_rear"]))
    assert KnowledgeDomain.BRAKE_BALANCE in _domains_for_campaign(camp("c", fields=["brake_bias"]))
    assert KnowledgeDomain.AERODYNAMICS in _domains_for_campaign(camp("c", fields=["aero_front"]))
    assert KnowledgeDomain.GEARBOX in _domains_for_campaign(camp("c", fields=["final_drive"]))
    assert KnowledgeDomain.DAMPERS in _domains_for_campaign(camp("c", fields=["dampers_rear_ext"]))
    assert KnowledgeDomain.ALIGNMENT in _domains_for_campaign(camp("c", fields=["toe_front"]))
    assert KnowledgeDomain.RIDE_HEIGHT in _domains_for_campaign(camp("c", fields=["ride_height_f"]))


def test_family_maps_to_handling_domain():
    assert KnowledgeDomain.VEHICLE_BALANCE in _domains_for_campaign(camp("c", family="rotation"))
    assert KnowledgeDomain.WEIGHT_TRANSFER in _domains_for_campaign(camp("c", family="traction"))
    assert KnowledgeDomain.BRAKE_BALANCE in _domains_for_campaign(camp("c", family="braking"))


def test_mechanism_maps_to_domain():
    assert KnowledgeDomain.WEIGHT_TRANSFER in _domains_for_campaign(
        camp("c", mech=["load_transfer"]))
    assert KnowledgeDomain.TRACK_SEGMENTS in _domains_for_campaign(
        camp("c", mech=["corner_specific_grip"]))
    assert KnowledgeDomain.DRIVER_TECHNIQUE in _domains_for_campaign(
        camp("c", mech=["throttle_application"]))


def test_unmapped_attribute_contributes_no_domain():
    # a nonsense field/family/mechanism maps to nothing (no inference)
    assert _domains_for_campaign(camp("c", fields=["zzz"], family="qqq", mech=["www"])) == set()


def test_domain_aggregates_evidence():
    g = build_knowledge_graph([camp("c1", fields=["lsd_accel"], conf="very_high",
                                    state="well_understood", confirmations=2, testable=False,
                                    info="none")])
    d = _domain(g, "differential")
    assert d["supporting_campaigns"] == ["c1"]
    assert d["confidence"]["value"] == "very_high"
    assert d["maturity"]["value"] == "complete"
    assert d["supporting_evidence"]["confirmations"] == 2


def test_multiple_campaigns_best_confidence_and_dominant_state():
    g = build_knowledge_graph([
        camp("c1", fields=["arb_front"], conf="medium", state="needs_confirmation"),
        camp("c2", fields=["arb_rear"], conf="very_high", state="well_understood",
             confirmations=2)])
    d = _domain(g, "anti_roll_bars")
    assert d["confidence"]["value"] == "very_high"          # best-known
    assert d["knowledge_state"]["value"] == "well_understood"   # most-understood dominant
    assert set(d["supporting_campaigns"]) == {"c1", "c2"}


def test_missing_domains_surfaced():
    g = build_knowledge_graph([camp("c1", fields=["lsd_accel"])]).to_dict()
    assert "differential" in g["known_domains"]
    assert "springs" in g["missing_domains"] and "gearbox" in g["missing_domains"]
    # all domains accounted for
    assert len(g["domains"]) == len(list(KnowledgeDomain))


def test_multi_track_limitation():
    g = build_knowledge_graph([
        camp("c1", fields=["lsd_accel"], track="Fuji"),
        camp("c2", fields=["lsd_accel"], track="Spa")])
    d = _domain(g, "differential")
    assert any("track" in lim for lim in d["known_limitations"])


def test_conflicting_limitation():
    g = build_knowledge_graph([camp("c1", fields=["lsd_accel"], confirmations=1, reg=1)])
    d = _domain(g, "differential")
    assert any("conflict" in lim for lim in d["known_limitations"])


def test_every_known_field_explained():
    g = build_knowledge_graph([camp("c1", fields=["lsd_accel"])])
    d = _domain(g, "differential")
    for key in ("knowledge_state", "confidence", "maturity", "remaining_uncertainty"):
        assert d[key]["reason"] and d[key]["source"]


def test_empty_graph_all_missing():
    g = build_knowledge_graph([]).to_dict()
    assert g["known_domains"] == []
    assert len(g["missing_domains"]) == len(list(KnowledgeDomain))


def test_large_graph_deterministic():
    fields = ["lsd_accel", "arb_front", "springs_front", "brake_bias", "aero_front", "toe_front"]
    campaigns = [camp(f"c{i}", fields=[fields[i % len(fields)]], track=f"T{i % 3}")
                 for i in range(60)]
    a = build_knowledge_graph(campaigns).to_dict()
    b = build_knowledge_graph(campaigns).to_dict()
    assert a == b
    assert len(a["domains"]) == len(list(KnowledgeDomain))


def test_never_raises_on_garbage():
    for junk in (None, [None, 5], [{"campaign_id": "x"}]):
        g = build_knowledge_graph(junk)
        assert len(g.to_dict()["domains"]) == len(list(KnowledgeDomain))


def test_no_forbidden_imports_or_graph_libs():
    src = inspect.getsource(__import__("strategy.engineering_knowledge_graph", fromlist=["x"]))
    for banned in ("import sqlite3", "PyQt6", "import random", "random.", "datetime.now",
                   "date.today", "time.time", "from data.session_db", "networkx", "sklearn",
                   "numpy", "scipy", "igraph", "def optimi", "argmax", "heapq"):
        assert banned not in src
    assert ENGINEERING_KNOWLEDGE_GRAPH_VERSION == "engineering_knowledge_graph_v1"
