"""Closed-loop setup learning (Phase 2) — the WRITE side that was missing.

Proves the loop that lets the brain STOP re-recommending a change that made the car
worse: apply a recommendation -> drive a slower run -> the scoring pass records a
'worsened' outcome for that rule -> after enough worsened runs the rule is hard-blocked
(the consume side the rule engine already uses).

Deterministic / offline — no Qt, no telemetry rig.
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from data.session_db import SessionDB
from services.setup_learning import persist_applied_recommendation, run_scoring_pass
from strategy.setup_lineage import blocked_rules_from_outcomes, LOCKOUT_MIN_WORSENED

TRACK = "TestTrack"
LAYOUT = "layout_a"
RULE = "B7_reduce_rear_arb"


def _session(db, car_id, lap_ms, n=6):
    sid = db.open_session(car_id, TRACK, "Practice", "Test Car")
    for lap in range(1, n + 1):
        db.write_lap(sid, lap, lap_ms, 3.0, None)
    return sid


def _apply_then_worse_run(db, car_id):
    """One full cycle: baseline (fast) -> apply a rule -> a SLOWER run -> score."""
    before = _session(db, car_id, 90_000)            # fast baseline
    persist_applied_recommendation(
        db, car_id=car_id, track=TRACK, layout_id=LAYOUT,
        before_session_id=before,
        changes=[{"field": "arb_rear", "from": 5, "to": 4,
                  "reason": "loosen rear", "rule_id": RULE}],
        driver_profile_version="v1.0-hardcoded", rule_engine_version="v1")
    _session(db, car_id, 96_000)                     # SLOWER run with the change = worse
    trigger = db.open_session(car_id, TRACK, "Practice", "Test Car")  # next session opens
    return run_scoring_pass(db, car_id, TRACK, LAYOUT, trigger)


def test_worse_run_records_a_worsened_outcome_for_the_rule():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        db = SessionDB(os.path.join(tmp, "s.db"))
        try:
            car_id = db.upsert_car({"name": "Test Car"})
            written = _apply_then_worse_run(db, car_id)
            assert written >= 1, "the scoring pass should record a non-trivial outcome"
            outs = db.get_learning_outcomes(car_id, TRACK, LAYOUT)
            worsened = [o for o in outs
                        if o.get("rule_id") == RULE and o.get("verdict") == "worsened"]
            assert worsened, f"expected a 'worsened' outcome for {RULE}, got {outs}"
        finally:
            db.close()


def test_repeated_worse_runs_hard_block_the_rule():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        db = SessionDB(os.path.join(tmp, "s.db"))
        try:
            car_id = db.upsert_car({"name": "Test Car"})
            for _ in range(LOCKOUT_MIN_WORSENED):
                _apply_then_worse_run(db, car_id)
            outs = db.get_learning_outcomes(car_id, TRACK, LAYOUT)
            blocked = blocked_rules_from_outcomes(outs)
            # The consume side the rule engine reads: this rule is now locked out, so
            # analyse will stop re-recommending it (the exact UAT complaint).
            assert RULE in blocked, f"{RULE} should be hard-blocked after repeated worse runs"
        finally:
            db.close()


def test_a_rec_is_scored_only_once():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        db = SessionDB(os.path.join(tmp, "s.db"))
        try:
            car_id = db.upsert_car({"name": "Test Car"})
            _apply_then_worse_run(db, car_id)
            # A second pass with a fresh trigger must NOT re-score the same (now scored) rec.
            trigger2 = db.open_session(car_id, TRACK, "Practice", "Test Car")
            again = run_scoring_pass(db, car_id, TRACK, LAYOUT, trigger2)
            assert again == 0, "an already-scored rec must not be scored again"
        finally:
            db.close()


def test_change_without_rule_id_is_not_learned_from():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        db = SessionDB(os.path.join(tmp, "s.db"))
        try:
            car_id = db.upsert_car({"name": "Test Car"})
            before = _session(db, car_id, 90_000)
            persist_applied_recommendation(
                db, car_id=car_id, track=TRACK, layout_id=LAYOUT,
                before_session_id=before,
                changes=[{"field": "arb_rear", "from": 5, "to": 4, "reason": "x"}])  # no rule_id
            _session(db, car_id, 96_000)
            trigger = db.open_session(car_id, TRACK, "Practice", "Test Car")
            run_scoring_pass(db, car_id, TRACK, LAYOUT, trigger)
            outs = db.get_learning_outcomes(car_id, TRACK, LAYOUT)
            assert outs == [] or all(o.get("rule_id") != RULE for o in outs)
        finally:
            db.close()
