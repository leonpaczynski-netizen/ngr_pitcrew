"""Program 3 Phase J — J6 Setup Brain + J7 Race Strategy certification.

Certifies that the repaired spine feeds the brains correctly-scoped evidence and that
the brains' advisory / immutability / Apply safety invariants remain intact. Does NOT
modify brain doctrine; the brains' internal clamp/movement-reserve/Apply behaviour is
certified by their existing golden + safety suites (run in the Phase-J regression).
"""

from pathlib import Path

from data.engineering_context_key import EngineeringContextKey
from data.session_db import SessionDB
from strategy.adaptive_live_strategy import acknowledge_strategy


def _db(tmp_path):
    return SessionDB(str(tmp_path / "s.db"))


# --------------------------------------------------------------------------- #
# J6 — Setup Brain
# --------------------------------------------------------------------------- #

def test_j6_setup_evidence_scope_isolates_by_physical_context():
    # setup evidence is scoped by the physical scope_fingerprint (driver+car+track+layout+gt7);
    # a DIFFERENT car isolates evidence, so one car's outcome can't reinforce another's.
    base = EngineeringContextKey(driver_id="leon", car_id="333", track_location_id="fuji",
                                 layout_id="full", gt7_version="1.49", event_id="5")
    other_car = EngineeringContextKey(driver_id="leon", car_id="999", track_location_id="fuji",
                                      layout_id="full", gt7_version="1.49", event_id="5")
    assert base.scope_fingerprint() != other_car.scope_fingerprint()


def test_j6_setup_evidence_is_event_independent_by_design():
    # the SAME physical context at a different EVENT legitimately shares setup evidence
    # (a setup behaves the same regardless of event rules) — event is NOT in the scope key.
    e5 = EngineeringContextKey(driver_id="leon", car_id="333", track_location_id="fuji",
                               layout_id="full", gt7_version="1.49", event_id="5")
    e9 = EngineeringContextKey(driver_id="leon", car_id="333", track_location_id="fuji",
                               layout_id="full", gt7_version="1.49", event_id="9")
    assert e5.scope_fingerprint() == e9.scope_fingerprint()      # physical scope, event-independent
    assert e5.fingerprint() != e9.fingerprint()                 # but full identity still differs


def test_j6_qualifying_and_race_objectives_are_distinct():
    from strategy.discipline_objectives import objective_priorities
    assert objective_priorities("qualifying") != objective_priorities("race")


def test_j6_rule_engine_version_unchanged_by_program3():
    from strategy._setup_constants import RULE_ENGINE_VERSION
    assert RULE_ENGINE_VERSION == "46.0"          # Program 3 changed no setup-rule doctrine


def test_j6_car_specific_outranks_global_in_setup_direction():
    from strategy.learning_transfer import rank_priors_for_target, TransferVerdict
    priors = [{"observation": "wants front bite", "proposed_layer": "global_driver", "confidence": 0.8},
              {"observation": "wants front bite", "proposed_layer": "car_specific", "confidence": 0.8}]
    res = {r.layer: r for r in rank_priors_for_target(priors, {"car_id": 333})}
    assert res["car_specific"].verdict == TransferVerdict.APPLIES_EXACT
    assert not res["global_driver"].applies


# --------------------------------------------------------------------------- #
# J7 — Race Strategy
# --------------------------------------------------------------------------- #

def test_j7_immutable_revisions_preserve_parentage(tmp_path):
    db = _db(tmp_path)
    v1 = db.append_strategy_revision(session_run_id="run-1", event_id=5, trigger="pre_race",
                                     plan_json='{"stops":1}')
    v2 = db.append_strategy_revision(session_run_id="run-1", event_id=5, trigger="rain",
                                     plan_json='{"stops":2}')
    revs = db.get_strategy_revisions("run-1")
    assert [r["revision_index"] for r in revs] == [1, 2]
    assert revs[1]["parent_revision_id"] == v1                  # parentage preserved
    import json
    assert json.loads(revs[0]["plan_json"])["stops"] == 1       # v1 never mutated by v2


def test_j7_only_latest_revision_is_active(tmp_path):
    db = _db(tmp_path)
    db.append_strategy_revision(session_run_id="run-1", trigger="pre_race", plan_json="{}")
    db.append_strategy_revision(session_run_id="run-1", trigger="rain", plan_json="{}")
    revs = db.get_strategy_revisions("run-1")
    assert sum(r["is_active"] for r in revs) == 1               # a superseded revision can't be active
    assert db.get_active_strategy_revision("run-1")["revision_index"] == 2


def test_j7_material_trigger_does_not_rewrite_history(tmp_path):
    db = _db(tmp_path)
    db.append_strategy_revision(session_run_id="run-1", trigger="pre_race", plan_json='{"stops":1}')
    before = db.get_strategy_revisions("run-1")[0]
    db.append_strategy_revision(session_run_id="run-1", trigger="damage", plan_json='{"stops":3}')
    after = db.get_strategy_revisions("run-1")[0]
    # the earlier revision's CONTENT is immutable — only the is_active *pointer* flips to the
    # new revision (only-latest-active). A material trigger appends; it never rewrites history.
    immutable = ("revision_id", "parent_revision_id", "revision_index", "trigger", "plan_json",
                 "reason", "created_at")
    assert {k: before[k] for k in immutable} == {k: after[k] for k in immutable}
    assert before["is_active"] == 1 and after["is_active"] == 0   # pointer moved, content intact


def test_j7_snapshots_link_to_event_run_and_lap(tmp_path):
    db = _db(tmp_path)
    sid = db.append_race_state_snapshot(session_run_id="run-1", event_id=5, lap_number=6,
                                        trigger="rain", state_json='{"fuel":25}')
    snaps = db.get_snapshots_for_run("run-1")
    assert len(snaps) == 1
    assert snaps[0]["snapshot_id"] == sid and snaps[0]["event_id"] == 5 and snaps[0]["lap_number"] == 6


def test_j7_acknowledgement_executes_nothing(tmp_path):
    ack = acknowledge_strategy(record_preference=True)
    assert ack.executes_anything is False                      # advisory only — no pit command


def test_j7_live_pit_wall_has_no_command_tokens():
    # the advisory-only guarantee (TestLiveSafety) still holds post-Program-3
    for rel in ("ui/components/live_pit_wall.py", "strategy/ngr_live_pit_wall.py"):
        src = Path(rel).read_text(encoding="utf-8")
        for token in ("set_plan(", "make_pit", "execute_pit", "strategy_engine"):
            assert token not in src, f"{rel} must not contain {token}"
