"""Program 3 Phase J — J8 debrief-to-learning + J9 determinism / replay.

Certifies through the real SessionDB debrief aggregation, learning workflow and
transfer evaluator.
"""

from data.session_db import SessionDB
from strategy.event_debrief import build_event_debrief, DebriefProvenance
from strategy.learning_transfer import evaluate_learning_transfer, rank_priors_for_target
from strategy.ptt_interaction import PttInteractionRecord


def _db(tmp_path):
    return SessionDB(str(tmp_path / "s.db"))


def _seed_event(db, eid, track="Fuji"):
    db.upsert_event({"name": f"Event {eid}", "track": track})
    real = int(db._conn.execute("SELECT id FROM events WHERE name=?", (f"Event {eid}",)).fetchone()[0])
    sid = db.open_session(1, track, "Race", event_id=real)
    run = db.get_run_for_session(sid)["run_id"]
    db.append_strategy_revision(session_run_id=run, event_id=real, trigger="ptt_accept", plan_json="{}")
    db.record_ptt_interaction(PttInteractionRecord(
        event_id=real, session_run_id=run, command_class="report",
        recognised_action="rain", lap_number=4).as_dict())
    return real, run


# --------------------------------------------------------------------------- #
# J8 — debrief to learning
# --------------------------------------------------------------------------- #

def test_j8_debrief_retains_provenance_classification(tmp_path):
    db = _db(tmp_path)
    eid, _ = _seed_event(db, 1)
    d = db.build_event_debrief_for_event(eid)
    provs = {f["provenance"] for f in d["findings"]}
    assert "measured_fact" in provs and "driver_report" in provs
    # a driver 'rain' report is a driver_report, never a measured fact
    rain = [f for f in d["findings"] if "rain" in f["text"].lower()]
    assert rain and all(f["provenance"] == "driver_report" for f in rain)


def test_j8_debrief_does_not_auto_promote_learning(tmp_path):
    db = _db(tmp_path)
    eid, _ = _seed_event(db, 1)
    db.build_event_debrief_for_event(eid)
    # aggregation NEVER silently becomes a learning proposal — promotion is driver-gated
    assert db.get_learning_proposals() == []
    assert db.get_active_learning_priors() == []


def test_j8_accepted_learning_retains_source_provenance(tmp_path):
    db = _db(tmp_path)
    pid = db.propose_learning(observation="softer rear ARB helped", source_event_id=7,
                              source_session_run_id="run-x", evidence_json='[{"lap": 4}]',
                              confidence=0.7)
    db.decide_learning(pid, "accept")
    prior = db.get_active_learning_priors()[0]
    assert prior["source_event_id"] == 7 and prior["source_session_run_id"] == "run-x"
    assert prior["evidence_json"] == '[{"lap": 4}]'            # source evidence retained


def test_j8_low_confidence_finding_does_not_silently_promote(tmp_path):
    db = _db(tmp_path)
    pid = db.propose_learning(observation="maybe understeer", confidence=0.2,
                              proposed_layer="global_driver")
    # even if accepted, a low-confidence prior is excluded by the transfer gate
    db.decide_learning(pid, "accept")
    prior = db.get_active_learning_priors()[0]
    t = evaluate_learning_transfer(prior, {}, confidence_threshold=0.5)
    assert not t.applies


def test_j8_driver_review_can_exclude_misleading_evidence(tmp_path):
    db = _db(tmp_path)
    pid = db.propose_learning(observation="telemetry showed early throttle")
    db.decide_learning(pid, "reject", note="traffic-affected lap, misleading")
    assert db.get_active_learning_priors() == []


def test_j8_one_events_debrief_does_not_alter_another_events_truth(tmp_path):
    db = _db(tmp_path)
    e1, _ = _seed_event(db, 1)
    e2, _ = _seed_event(db, 2)
    before = db.build_event_debrief_for_event(e2)
    db.build_event_debrief_for_event(e1)                       # aggregate event 1
    after = db.build_event_debrief_for_event(e2)
    assert before == after                                     # event 2's truth unchanged (read-only)


# --------------------------------------------------------------------------- #
# J9 — determinism / replay
# --------------------------------------------------------------------------- #

def test_j9_debrief_aggregation_is_deterministic(tmp_path):
    db = _db(tmp_path)
    eid, _ = _seed_event(db, 1)
    assert db.build_event_debrief_for_event(eid) == db.build_event_debrief_for_event(eid)


def test_j9_transfer_decisions_are_deterministic():
    prior = {"observation": "x", "proposed_layer": "car_specific", "confidence": 0.8}
    a = evaluate_learning_transfer(prior, {"car_id": 1})
    b = evaluate_learning_transfer(prior, {"car_id": 1})
    assert a == b
    priors = [prior, {"observation": "x", "proposed_layer": "global_driver", "confidence": 0.8}]
    assert rank_priors_for_target(priors, {"car_id": 1}) == rank_priors_for_target(priors, {"car_id": 1})


def test_j9_active_strategy_revision_selection_is_stable(tmp_path):
    db = _db(tmp_path)
    db.append_strategy_revision(session_run_id="run-1", trigger="pre_race", plan_json='{"stops":1}')
    db.append_strategy_revision(session_run_id="run-1", trigger="rain", plan_json='{"stops":2}')
    a = db.get_active_strategy_revision("run-1")
    b = db.get_active_strategy_revision("run-1")
    assert a == b and a["revision_index"] == 2                 # latest, stable


def test_j9_replay_does_not_mutate_history_or_duplicate(tmp_path):
    db = _db(tmp_path)
    eid, run = _seed_event(db, 1)
    revs_before = db.get_strategy_revisions_for_event(eid)
    props_before = db.get_learning_proposals()
    # replay the read-only aggregation repeatedly
    for _ in range(3):
        db.build_event_debrief_for_event(eid)
    assert db.get_strategy_revisions_for_event(eid) == revs_before   # no mutation
    assert db.get_learning_proposals() == props_before              # no duplicate promotion
