"""Program 3 Phase J — J3 learning specificity, J4 global-style protection,
J5 learning-decision enforcement.

Certifies the transfer doctrine + driver-curation through the real SessionDB learning
workflow and the real transfer evaluator (no mocks).
"""

import json

from data.session_db import SessionDB
from strategy.learning_transfer import (
    TransferVerdict, evaluate_learning_transfer, rank_priors_for_target,
)


def _db(tmp_path):
    return SessionDB(str(tmp_path / "s.db"))


def _prior(obs, layer, conf=0.8):
    return {"observation": obs, "proposed_layer": layer, "confidence": conf}


# --------------------------------------------------------------------------- #
# J3 — learning specificity priority
# --------------------------------------------------------------------------- #

def test_j3_full_specificity_ladder_ranks_correctly():
    from strategy.learning_transfer import layer_rank, LAYER_SPECIFICITY
    ranks = [layer_rank(l) for l in LAYER_SPECIFICITY]
    assert ranks == sorted(ranks)                              # most-specific first, monotonic
    assert layer_rank("event") < layer_rank("track_layout") < layer_rank("car_specific") \
        < layer_rank("track_archetype") < layer_rank("vehicle_archetype") < layer_rank("global_driver")


def test_j3_more_specific_valid_evidence_outranks_broad():
    priors = [_prior("prefers front bite", "global_driver"),
              _prior("prefers front bite", "car_specific")]
    res = {r.layer: r for r in rank_priors_for_target(priors, {"car_id": 333, "driver_id": "leon"})}
    assert res["car_specific"].verdict == TransferVerdict.APPLIES_EXACT
    assert res["global_driver"].verdict == TransferVerdict.SUPPRESSED_BY_MORE_SPECIFIC


def test_j3_broad_learning_is_a_prior_not_a_command():
    t = evaluate_learning_transfer(_prior("smooth throttle", "global_driver", 0.9), {})
    assert t.verdict == TransferVerdict.APPLIES_AS_PRIOR and t.strength < 0.9
    assert "not a command" in t.explanation


# --------------------------------------------------------------------------- #
# J4 — global driver-style protection
# --------------------------------------------------------------------------- #

def test_j4_one_event_cannot_redefine_global_profile(tmp_path):
    db = _db(tmp_path)
    # a single anomalous observation becomes a PROPOSAL, never an auto-promoted prior
    pid = db.propose_learning(observation="brakes very late", proposed_layer="global_driver",
                              confidence=0.9, source_event_id=5)
    assert pid
    assert db.get_active_learning_priors() == []              # not active until the driver accepts


def test_j4_car_specific_problem_does_not_become_universal():
    # a car-specific prior requires the car in the target; a different/absent car excludes it
    t = evaluate_learning_transfer(_prior("unstable under braking", "car_specific"),
                                   {"driver_id": "leon"})      # no car_id
    assert t.verdict == TransferVerdict.EXCLUDED_CONTEXT_MISSING


def test_j4_track_reference_does_not_transfer_to_another_track():
    # a track+layout reference requires the exact track+layout present in the target
    t = evaluate_learning_transfer(_prior("brake at the 100 board T1", "track_layout"),
                                   {"track": "Fuji"})          # layout missing
    assert t.verdict == TransferVerdict.EXCLUDED_CONTEXT_MISSING


def test_j4_repeated_compatible_evidence_may_strengthen_a_prior():
    # higher confidence yields a stronger (but still bounded) prior
    weak = evaluate_learning_transfer(_prior("front bias", "global_driver", 0.5), {})
    strong = evaluate_learning_transfer(_prior("front bias", "global_driver", 0.9), {})
    assert strong.strength > weak.strength
    assert strong.strength <= 0.9 * 0.5 + 1e-9                 # a broad prior stays halved


def test_j4_contradiction_suppresses_rather_than_averages():
    t = evaluate_learning_transfer(_prior("front bias", "global_driver"), {},
                                   more_specific_contradiction=True)
    assert t.verdict == TransferVerdict.SUPPRESSED_BY_MORE_SPECIFIC   # never averaged


def test_j4_historical_profile_versions_are_immutable(tmp_path):
    db = _db(tmp_path)
    v1 = db.append_driver_profile_version(version_label="v1", profile_json='{"bias": "neutral"}')
    v2 = db.append_driver_profile_version(version_label="v2", profile_json='{"bias": "front"}')
    hist = db.get_driver_profile_versions()
    assert json.loads(hist[0]["profile_json"])["bias"] == "neutral"   # v1 not rewritten
    assert hist[1]["prior_version_id"] == v1
    assert db.get_current_driver_profile_version()["version_id"] == v2  # future uses latest


# --------------------------------------------------------------------------- #
# J5 — learning-decision enforcement
# --------------------------------------------------------------------------- #

def test_j5_accepted_influences_rejected_never_deferred_inactive(tmp_path):
    db = _db(tmp_path)
    acc = db.propose_learning(observation="A")
    rej = db.propose_learning(observation="B")
    dfr = db.propose_learning(observation="C")
    db.decide_learning(acc, "accept")
    db.decide_learning(rej, "reject")
    db.decide_learning(dfr, "defer")
    active_obs = {p["observation"] for p in db.get_active_learning_priors()}
    assert active_obs == {"A"}                                 # only accepted


def test_j5_rejected_is_suppressed_unless_new_evidence(tmp_path):
    db = _db(tmp_path)
    pid = db.propose_learning(observation="late braking helps", applicability_scope="global")
    db.decide_learning(pid, "reject")
    assert db.propose_learning(observation="late braking helps", applicability_scope="global") == ""
    assert db.propose_learning(observation="late braking helps", applicability_scope="global",
                               allow_if_previously_rejected=True)   # materially new evidence


def test_j5_edit_uses_the_edited_scope_no_silent_broadening(tmp_path):
    db = _db(tmp_path)
    pid = db.propose_learning(observation="strong rotation", applicability_scope="global_driver")
    # driver narrows it to a specific archetype — the edited (narrower) scope is what is stored
    db.decide_learning(pid, "edit", edited_scope="mid_engine_rwd")
    p = db.get_learning_proposals()[0]
    assert p["applicability_scope"] == "mid_engine_rwd"        # honoured, not silently broadened
    assert p["status"] == "edited"


def test_j5_decisions_are_immutable_and_auditable(tmp_path):
    db = _db(tmp_path)
    pid = db.propose_learning(observation="x")
    db.decide_learning(pid, "defer")
    db.decide_learning(pid, "reject")
    rows = db._conn.execute(
        "SELECT decision FROM learning_decisions WHERE proposal_id=? ORDER BY decided_at, decision_id",
        (pid,)).fetchall()
    assert [r[0] for r in rows] == ["defer", "reject"]         # full history retained, append-only
