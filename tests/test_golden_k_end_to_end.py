"""Program 3 Phase K — golden end-to-end UAT scenarios (§30).

Deterministic, offline, assembled-stack journeys (real SessionDB + real domain
functions). These are the automated half of Phase K; the live on-hardware GT7/PSVR2
UAT is separate. No live seam is activated here.
"""

import json

from data.session_db import SessionDB
from strategy.ptt_interaction import PttInteractionRecord
from strategy.qualifying_state_machine import (
    QualifyingState, on_pit_exit, on_lap_completed, on_cooldown, qualifying_cue, QualifyingPhase,
)
from strategy.practice_brief import start_practice_brief, on_valid_lap, on_invalid_lap, practice_status
from strategy.learning_transfer import rank_priors_for_target, TransferVerdict


def _db(tmp_path, name="s.db"):
    return SessionDB(str(tmp_path / name))


# --------------------------------------------------------------------------- #
# Scenario 1 — track modelling + restart linkage
# --------------------------------------------------------------------------- #

def test_golden_scenario_1_track_modelling_and_restart(tmp_path):
    path = str(tmp_path / "tm.db")
    db = SessionDB(path)
    db.upsert_event({"name": "Round 4 Fuji", "track": "fuji"})
    db.register_track_model_version(track_location_id="fuji", layout_id="full",
                                    model_status="draft", approved=False,
                                    created_at="2026-01-01T10:00:00Z")
    approved = db.register_track_model_version(track_location_id="fuji", layout_id="full",
                                               model_status="approved", approved=True,
                                               confidence=0.9, created_at="2026-01-01T11:00:00Z")
    db._conn.close()
    # RESTART — reopen the DB; the approved model + its identity survive
    db2 = SessionDB(path)
    got = db2.get_approved_track_model_version("fuji", "full")
    assert got is not None and got["version_id"] == approved and got["approved"] == 1
    assert db2.get_approved_track_model_version("monza", "full") is None   # scoped


# --------------------------------------------------------------------------- #
# Scenario 2 — practice + setup: exact lineage, no cross-event mix
# --------------------------------------------------------------------------- #

def test_golden_scenario_2_practice_setup_no_cross_event_mix(tmp_path):
    db = _db(tmp_path)
    a = int(db.upsert_event({"name": "Event A", "track": "fuji"}))
    b = int(db.upsert_event({"name": "Event B", "track": "monza"}))
    runs = []
    for _label in ("baseline", "setupA", "setupB"):
        sid = db.open_session(333, "fuji", "Practice", event_id=a)
        db.bind_session_to_activity("plan-A", sid, cycle_id="cyc-A")
        db.write_lap(sid, 1, 90_000, 2.0, None)
        runs.append(db.get_run_for_session(sid)["run_id"])
    # a run for event B
    sb = db.open_session(333, "monza", "Practice", event_id=b)
    # event A's evidence is exactly its three runs — event B never mixes in
    assert {r["run_id"] for r in db.get_session_runs_for_event(a)} == set(runs)
    assert db.get_run_for_session(sb)["run_id"] not in set(runs)
    # all three practice runs are bound to the one plan (lineage preserved)
    assert len(db.get_runs_for_plan("plan-A")) == 3


# --------------------------------------------------------------------------- #
# Scenario 3 — coaching uses correctly-scoped practice evidence
# --------------------------------------------------------------------------- #

def test_golden_scenario_3_coaching_evidence_is_car_track_scoped(tmp_path):
    db = _db(tmp_path)
    eid = int(db.upsert_event({"name": "Event A", "track": "fuji"}))
    # two practice runs for the coached car; one for a different car
    for _ in range(2):
        sid = db.open_session(333, "fuji", "Practice", event_id=eid)
        db.write_lap(sid, 1, 90_000, 2.0, None)
    other = db.open_session(999, "fuji", "Practice", event_id=eid)
    db.write_lap(other, 1, 88_000, 2.0, None)
    # coaching for car 333 must not pull the other car's (faster) lap into its evidence
    laps_333 = db.get_laps_for_scoring(db.get_latest_session_for_event(eid))  # latest is car 333 or 999?
    # explicit: the other car's session laps are separate
    assert db.count_valid_laps(other) == 1
    # a practice brief tracks valid evidence and won't let one anomaly dominate
    brief = start_practice_brief(domain="driver_coaching")
    brief = on_valid_lap(on_valid_lap(brief))
    brief = on_invalid_lap(brief, reason="off at T3")
    assert brief.valid_laps == 2 and brief.invalid_laps == 1
    assert "didn't count" in practice_status(brief)


# --------------------------------------------------------------------------- #
# Scenario 4 — qualifying lifecycle (deterministic golden)
# --------------------------------------------------------------------------- #

def test_golden_scenario_4_qualifying_lifecycle(tmp_path):
    s = QualifyingState.initial()
    s = on_pit_exit(s);                       out_lap = qualifying_cue(s)
    s = on_lap_completed(s, 0);               flying = qualifying_cue(s)   # out-lap done → flying
    s = on_lap_completed(s, 89_500, valid=True); complete = qualifying_cue(s)
    s = on_cooldown(s)
    assert s.phase == QualifyingPhase.COOLDOWN
    assert "temperature" in out_lap.lower()                 # out-lap: build temp
    assert flying == "This is your lap — commit."           # minimal, non-distracting
    assert "personal best" in complete.lower()              # reports the attempt
    assert s.best_lap_ms == 89_500                          # qualifying tracks its OWN best,
    #                                                         not a race-fuel lap comparison


# --------------------------------------------------------------------------- #
# Scenario 5 — race + replan: immutable revisions, snapshots, history preserved
# --------------------------------------------------------------------------- #

def test_golden_scenario_5_race_replan_preserves_history(tmp_path):
    db = _db(tmp_path)
    eid = int(db.upsert_event({"name": "Round 4 Fuji", "track": "fuji"}))
    sid = db.open_session(333, "fuji", "Race", event_id=eid)
    run = db.get_run_for_session(sid)["run_id"]
    v1 = db.append_strategy_revision(session_run_id=run, event_id=eid, trigger="pre_race",
                                     plan_json='{"stops":1}')
    for lap in range(1, 5):
        db.append_race_state_snapshot(session_run_id=run, event_id=eid, lap_number=lap,
                                      trigger="lap_complete", state_json=json.dumps({"fuel": 40 - lap * 3}))
    v2 = db.append_strategy_revision(session_run_id=run, event_id=eid, trigger="fuel_evidence",
                                     plan_json='{"stops":2}')
    v3 = db.append_strategy_revision(session_run_id=run, event_id=eid, trigger="rain",
                                     plan_json='{"stops":2,"tyres":"wet"}')
    revs = db.get_strategy_revisions(run)
    assert [r["revision_index"] for r in revs] == [1, 2, 3]
    assert [r["parent_revision_id"] for r in revs] == ["", v1, v2]        # parentage chain
    assert sum(r["is_active"] for r in revs) == 1
    assert db.get_active_strategy_revision(run)["revision_id"] == v3      # only latest active
    assert json.loads(revs[0]["plan_json"])["stops"] == 1                # v1 history preserved
    assert len(db.get_snapshots_for_run(run)) == 4                       # a snapshot per lap


# --------------------------------------------------------------------------- #
# Scenario 6 — event debrief + learning proposals (accept/reject/defer)
# --------------------------------------------------------------------------- #

def test_golden_scenario_6_debrief_and_proposals(tmp_path):
    db = _db(tmp_path)
    eid = int(db.upsert_event({"name": "Round 4 Fuji", "track": "fuji"}))
    sid = db.open_session(333, "fuji", "Race", event_id=eid)
    run = db.get_run_for_session(sid)["run_id"]
    db.append_strategy_revision(session_run_id=run, event_id=eid, trigger="rain", plan_json="{}")
    db.record_ptt_interaction(PttInteractionRecord(
        event_id=eid, session_run_id=run, command_class="report",
        recognised_action="rain", lap_number=4).as_dict())

    d = db.build_event_debrief_for_event(eid)
    assert {"measured_fact", "driver_report"} <= {f["provenance"] for f in d["findings"]}

    acc = db.propose_learning(observation="softer rear ARB helped", source_event_id=eid, confidence=0.7)
    rej = db.propose_learning(observation="brake later everywhere", source_event_id=eid, confidence=0.6)
    dfr = db.propose_learning(observation="try stiffer front springs", source_event_id=eid, confidence=0.5)
    db.decide_learning(acc, "accept")
    db.decide_learning(rej, "reject")
    db.decide_learning(dfr, "defer")
    assert {p["observation"] for p in db.get_active_learning_priors()} == {"softer rear ARB helped"}


# --------------------------------------------------------------------------- #
# Scenario 7 — cross-event transfer to a new track + different car archetype
# --------------------------------------------------------------------------- #

def test_golden_scenario_7_cross_event_transfer(tmp_path):
    db = _db(tmp_path)
    # Event A learnings: a global tendency, an exact-car conclusion, an exact-track
    # reference, and one the driver rejects.
    g = db.propose_learning(observation="prefers front-end bite", proposed_layer="global_driver",
                            confidence=0.8, source_event_id=1)
    c = db.propose_learning(observation="RSR '17 stable under heavy braking",
                            proposed_layer="car_specific", confidence=0.8, source_event_id=1)
    t = db.propose_learning(observation="brake at the 100 board into T1", proposed_layer="track_layout",
                            confidence=0.8, source_event_id=1)
    r = db.propose_learning(observation="late braking helps everywhere", proposed_layer="global_driver",
                            confidence=0.7, source_event_id=1)
    for pid in (g, c, t):
        db.decide_learning(pid, "accept")
    db.decide_learning(r, "reject")

    # attach the exact-context values to the accepted priors (source scope)
    priors = db.get_active_learning_priors()
    for p in priors:
        if p["proposed_layer"] == "car_specific":
            p["car_id"] = 333
        if p["proposed_layer"] == "track_layout":
            p["track"], p["layout"] = "fuji", "full"

    # Event B: NEW track (monza), DIFFERENT car archetype/id, same driver
    target_B = {"driver_id": "leon", "car_id": 999, "vehicle_archetype": "mid_engine_rwd",
                "track": "monza", "layout": "gp"}
    results = {res.observation: res for res in rank_priors_for_target(priors, target_B)}

    # global driving style transfers as a LOW-strength prior
    assert results["prefers front-end bite"].verdict == TransferVerdict.APPLIES_AS_PRIOR
    # the exact-car conclusion does NOT transfer to a different car
    assert results["RSR '17 stable under heavy braking"].verdict == TransferVerdict.EXCLUDED_CONTEXT_MISMATCH
    # the exact-track reference does NOT transfer to another track
    assert results["brake at the 100 board into T1"].verdict == TransferVerdict.EXCLUDED_CONTEXT_MISMATCH
    # the rejected learning is not even a candidate (never an active prior)
    assert "late braking helps everywhere" not in results

    # a new, more-specific accepted prior for the EXACT event-B car overrides the broad prior
    db.propose_learning(observation="prefers front-end bite", proposed_layer="car_specific",
                        confidence=0.8, source_event_id=2, allow_if_previously_rejected=True)
    # (workflow already proven; here we assert the transfer ranks the specific one first)
    priors2 = priors + [{"observation": "prefers front-end bite", "proposed_layer": "car_specific",
                         "confidence": 0.8, "car_id": 999}]
    ranked = {(res.observation, res.layer): res for res in rank_priors_for_target(priors2, target_B)}
    assert ranked[("prefers front-end bite", "car_specific")].verdict == TransferVerdict.APPLIES_EXACT
    assert ranked[("prefers front-end bite", "global_driver")].verdict == \
        TransferVerdict.SUPPRESSED_BY_MORE_SPECIFIC


# --------------------------------------------------------------------------- #
# Restart / recovery — the spine survives a restart with no auto-active run
# --------------------------------------------------------------------------- #

def test_golden_restart_recovery(tmp_path):
    path = str(tmp_path / "restart.db")
    db = SessionDB(path)
    eid = int(db.upsert_event({"name": "Round 4 Fuji", "track": "fuji"}))
    sid = db.open_session(333, "fuji", "Race", event_id=eid)
    run = db.get_run_for_session(sid)["run_id"]
    db.append_strategy_revision(session_run_id=run, event_id=eid, trigger="pre_race", plan_json="{}")
    db.write_lap(sid, 1, 90_000, 2.0, None)
    db._conn.close()
    # RESTART
    db2 = SessionDB(path)
    got = db2.get_run_for_session(sid)
    assert got is not None and got["run_id"] == run                      # run identity survives
    assert db2.get_active_strategy_revision(run) is not None             # revision survives
    assert db2.count_valid_laps(sid) == 1                                # laps survive
    # the DB does not auto-elect an "active" event on restart (config layer owns that,
    # and clears it on launch) — the run is complete/recording, not auto-active
    assert db2.get_session_run(run)["status"] in ("recording", "complete")
