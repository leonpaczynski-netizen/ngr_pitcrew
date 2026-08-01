"""Program 3 Phase I — learning proposal / decision workflow + rejected suppression.

Cross-event learning is never silently promoted: propose -> accept/reject/edit/defer.
Only accepted (or accepted-with-edit) learning is an active prior; a rejected learning
is never re-proposed without new evidence and never influences a future recommendation.
"""

from data.session_db import SessionDB
from strategy.learning_proposal import observation_key, LearningStatus


def _db(tmp_path):
    return SessionDB(str(tmp_path / "s.db"))


def test_observation_key_normalises():
    assert observation_key("  Trail  Braking  Preference ", "driver") == \
        observation_key("trail braking preference", "DRIVER")


def test_table_and_version(tmp_path):
    db = _db(tmp_path)
    assert db._conn.execute("PRAGMA user_version").fetchone()[0] >= 40
    tables = {r[0] for r in db._conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"learning_proposals", "learning_decisions"} <= tables


def test_propose_and_read(tmp_path):
    db = _db(tmp_path)
    pid = db.propose_learning(observation="prefers front-end bite", applicability_scope="global_driver",
                              proposed_layer="global_driver", confidence=0.7,
                              evidence_json='[{"event": 1}]', source_event_id=5)
    assert pid
    props = db.get_learning_proposals(status="proposed")
    assert len(props) == 1 and props[0]["observation"] == "prefers front-end bite"
    assert props[0]["confidence"] == 0.7 and props[0]["proposed_layer"] == "global_driver"


def test_accept_makes_it_an_active_prior(tmp_path):
    db = _db(tmp_path)
    pid = db.propose_learning(observation="trail braking preference")
    did = db.decide_learning(pid, "accept")
    assert did
    priors = db.get_active_learning_priors()
    assert len(priors) == 1 and priors[0]["status"] == LearningStatus.ACCEPTED.value


def test_reject_excludes_and_suppresses(tmp_path):
    db = _db(tmp_path)
    pid = db.propose_learning(observation="late braking helps everywhere", applicability_scope="global")
    db.decide_learning(pid, "reject", note="contradicted at Monza")
    # rejected learning is not an active prior
    assert db.get_active_learning_priors() == []
    # and cannot be re-proposed without new evidence (gate #23)
    assert db.is_learning_suppressed("late braking helps everywhere", "global") is True
    assert db.propose_learning(observation="late braking helps everywhere",
                               applicability_scope="global") == ""
    # ... unless materially new evidence is asserted
    pid2 = db.propose_learning(observation="late braking helps everywhere",
                               applicability_scope="global", allow_if_previously_rejected=True)
    assert pid2


def test_edit_updates_scope_and_is_a_prior(tmp_path):
    db = _db(tmp_path)
    pid = db.propose_learning(observation="strong front rotation", applicability_scope="global_driver")
    db.decide_learning(pid, "edit", edited_scope="mid_engine_rwd", note="only this archetype")
    p = db.get_learning_proposals()[0]
    assert p["status"] == LearningStatus.EDITED.value
    assert p["applicability_scope"] == "mid_engine_rwd"
    assert len(db.get_active_learning_priors()) == 1     # edited = accepted-with-edit


def test_defer_is_neither_prior_nor_rejected(tmp_path):
    db = _db(tmp_path)
    pid = db.propose_learning(observation="softer rear ARB at Fuji")
    db.decide_learning(pid, "defer")
    assert db.get_active_learning_priors() == []
    assert db.is_learning_suppressed("softer rear ARB at Fuji") is False   # can be raised again


def test_decisions_are_logged_immutably(tmp_path):
    db = _db(tmp_path)
    pid = db.propose_learning(observation="x")
    db.decide_learning(pid, "defer")
    db.decide_learning(pid, "accept")
    rows = db._conn.execute(
        "SELECT decision FROM learning_decisions WHERE proposal_id=? ORDER BY decided_at, decision_id",
        (pid,)).fetchall()
    assert [r[0] for r in rows] == ["defer", "accept"]   # full immutable decision history
    # latest decision wins the proposal status
    assert db.get_learning_proposals()[0]["status"] == LearningStatus.ACCEPTED.value


def test_bad_decision_is_ignored(tmp_path):
    db = _db(tmp_path)
    pid = db.propose_learning(observation="x")
    assert db.decide_learning(pid, "nonsense") == ""
    assert db.decide_learning("", "accept") == ""
