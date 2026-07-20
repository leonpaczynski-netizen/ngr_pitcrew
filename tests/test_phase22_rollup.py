"""Phase 22 — multi-event roll-up domain + programme-report assembly tests.

Compatible contexts merge; unlike contexts never merge and the reason is explicit; merge/exclude
reasons visible; deterministic; empty safe; never raises.
"""
import inspect

import pytest

from strategy.multi_event_rollup import (
    build_rollup, COMPATIBILITY_FIELDS, MULTI_EVENT_ROLLUP_VERSION,
)
from strategy.programme_knowledge_report import build_programme_knowledge


def ctx(car="RSR", track="Fuji", layout="fc", discipline="Race", gt7="1.49", driver="leon"):
    return {"car": car, "track": track, "layout": layout, "discipline": discipline,
            "gt7_version": gt7, "driver": driver}


def camp(cid, fields=("lsd_accel",), track="Fuji"):
    return {"campaign_id": cid, "objective": cid, "family": "traction", "fields": list(fields),
            "mechanisms": ["load_transfer"], "confidence_level": "high",
            "knowledge_state": "well_understood", "track": track, "confirmations": 2,
            "regressions": 0, "conflicting": False, "unresolved_mechanisms": 0, "executed": 2,
            "remaining_information_gain": "low", "testable": False}


def ev(context, campaigns):
    return {"context": context, "campaigns": campaigns}


def test_compatible_contexts_merge():
    events = [ev(ctx(track="Fuji"), [camp("a", track="Fuji")]),
              ev(ctx(track="Spa"), [camp("b", track="Spa")])]
    r = build_rollup(events, primary_context=ctx()).to_dict()
    prim = r["primary_group"]
    assert set(prim["tracks"]) == {"Fuji", "Spa"}
    assert {c["campaign_id"] for c in prim["campaigns"]} == {"a", "b"}
    assert r["other_groups"] == []


def test_incompatible_discipline_not_merged():
    events = [ev(ctx(discipline="Race"), [camp("a")]),
              ev(ctx(discipline="Qualifying", track="Fuji"), [camp("b")])]
    r = build_rollup(events, primary_context=ctx(discipline="Race")).to_dict()
    assert len(r["other_groups"]) == 1
    assert r["excluded_reasons"][0]["differing_fields"] == ["discipline"]
    assert "discipline" in r["excluded_reasons"][0]["reason"]


def test_incompatible_car_not_merged():
    events = [ev(ctx(car="RSR"), [camp("a")]), ev(ctx(car="GT3"), [camp("b")])]
    r = build_rollup(events, primary_context=ctx(car="RSR")).to_dict()
    assert r["primary_group"]["compatibility_key"]["car"] == "RSR"
    assert any(g["compatibility_key"]["car"] == "GT3" for g in r["other_groups"])


def test_merge_reason_visible():
    events = [ev(ctx(track="Fuji"), [camp("a", track="Fuji")]),
              ev(ctx(track="Spa"), [camp("b", track="Spa")])]
    r = build_rollup(events, primary_context=ctx()).to_dict()
    assert "merged" in r["primary_group"]["merge_reason"]


def test_duplicate_campaign_ids_deduped():
    events = [ev(ctx(track="Fuji"), [camp("dup", track="Fuji")]),
              ev(ctx(track="Spa"), [camp("dup", track="Spa")])]
    r = build_rollup(events, primary_context=ctx()).to_dict()
    assert len(r["primary_group"]["campaigns"]) == 1


def test_compatibility_fields_constant():
    assert COMPATIBILITY_FIELDS == ("car", "discipline", "gt7_version", "driver")


def test_rollup_deterministic():
    events = [ev(ctx(track="Fuji"), [camp("a")]), ev(ctx(track="Spa"), [camp("b")])]
    assert build_rollup(events, primary_context=ctx()).to_dict() == \
        build_rollup(events, primary_context=ctx()).to_dict()


def test_rollup_never_raises():
    for junk in (None, [], [None], [{"context": None, "campaigns": None}]):
        r = build_rollup(junk)
        assert r.to_dict()["eval_version"] == MULTI_EVENT_ROLLUP_VERSION


# --- programme report assembly ---------------------------------------------
def test_programme_report_builds_graph_for_primary():
    events = [ev(ctx(track="Fuji"), [camp("a", fields=["lsd_accel"], track="Fuji")]),
              ev(ctx(track="Spa"), [camp("b", fields=["arb_front"], track="Spa")]),
              ev(ctx(discipline="Qualifying"), [camp("c", fields=["brake_bias"])])]
    rep = build_programme_knowledge(events, primary_context=ctx(discipline="Race")).to_dict()
    assert rep["compatibility"]["events_merged"] == 2
    assert "differential" in rep["knowledge_graph"]["known_domains"]
    assert "anti_roll_bars" in rep["knowledge_graph"]["known_domains"]
    # the Qualifying event forms a separate group, not merged
    assert rep["totals"]["other_programme_groups"] == 1
    assert rep["safety_statement"]


def test_programme_report_deterministic_and_empty_safe():
    events = [ev(ctx(), [camp("a")])]
    assert build_programme_knowledge(events, primary_context=ctx()).to_dict() == \
        build_programme_knowledge(events, primary_context=ctx()).to_dict()
    empty = build_programme_knowledge([], primary_context=ctx()).to_dict()
    assert empty["knowledge_graph"].get("known_domains", []) == [] or \
        empty["knowledge_graph"] == {}
    assert empty["safety_statement"]


def test_programme_report_never_raises():
    for junk in (None, [None], [{"context": 5}]):
        rep = build_programme_knowledge(junk)
        assert rep.safety_statement


def test_no_forbidden_imports():
    for mod in ("strategy.multi_event_rollup", "strategy.programme_knowledge_report"):
        src = inspect.getsource(__import__(mod, fromlist=["x"]))
        for banned in ("import sqlite3", "PyQt6", "import random", "random.", "datetime.now",
                       "date.today", "time.time", "from data.session_db", "networkx", "sklearn",
                       "numpy", "def optimi", "argmax"):
            assert banned not in src, f"{mod}: {banned}"
