"""Closed-loop setup learning — the WRITE side of the outcome loop (Phase 2).

The rule engine already CONSUMES learning outcomes (it seeds a RuleOutcomeStore from
``get_learning_outcomes`` and locks out rules that repeatedly worsened the car — see
strategy/driving_advisor.py). What was missing is the CAPTURE: nothing recorded an
outcome when the driver applied a change and then drove a run, so the store was
always empty and the brain re-recommended a change that had already made the car
worse.

This module supplies the two headless, UI-free pieces that close the loop:

* ``persist_applied_recommendation`` — when the driver confirms a recommendation is
  on the car, write it as an ``applied`` (unscored) row against the session it was
  based on (the "before" session).
* ``run_scoring_pass`` — when a new session opens, compare the just-finished session
  ("after") against each applied-but-unscored rec's "before" session, persist the
  telemetry verdict, and record a per-rule learning outcome. This is the exact
  orchestration the classic ``MainWindow._trigger_scoring_pass`` performed, extracted
  so BOTH the classic dashboard and the new shell (via the backend session-open) run
  the same code path.

Everything here is pure over the DB + the pure scoring/evidence helpers, never raises,
and never touches Qt — so it can run on the dispatcher thread.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Mapping, Optional, Sequence


def persist_applied_recommendation(
    db,
    *,
    car_id: int,
    track: str,
    layout_id: str,
    before_session_id: int,
    changes: Sequence[Mapping],
    diagnosis: Optional[Mapping] = None,
    driver_profile_version: str = "",
    rule_engine_version: str = "",
    recommendation_text: str = "",
    created_at: str = "",
) -> Optional[int]:
    """Persist a just-applied recommendation as an ``applied`` (unscored) row.

    ``before_session_id`` is the session the recommendation was based on — the laps
    that represent the car BEFORE the change. A later run becomes the "after" side
    and ``run_scoring_pass`` scores the two. ``changes`` must carry ``rule_id`` per
    item for the outcome to be attributable to a rule (items without it are simply
    not learned from). Returns the new rec id, or None on failure / nothing to store.
    """
    try:
        if db is None or car_id <= 0 or not track or not before_session_id:
            return None
        _changes = [dict(c) for c in (changes or []) if isinstance(c, Mapping)]
        if not _changes:
            return None
        rec = {
            "ai_interaction_id": None,
            "session_id": int(before_session_id),
            "car_id": int(car_id),
            "track": str(track),
            "layout_id": str(layout_id or ""),
            "feature": "setup_analyse",
            "recommendation_text": str(recommendation_text or ""),
            "status": "applied",
            "created_at": created_at or datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "approved_changes_json": json.dumps(_changes),
            "diagnosis_json": json.dumps(dict(diagnosis)) if diagnosis else None,
            "driver_profile_version": str(driver_profile_version or ""),
            "rule_engine_version": str(rule_engine_version or ""),
        }
        db.insert_setup_recommendations([rec])
        # Best-effort: return the id of the row we just wrote (most-recent applied for scope).
        try:
            recs = db.get_applied_unverified_recs(int(car_id), str(track), str(layout_id or ""))
            ids = [r.get("id") for r in recs if r.get("session_id") == int(before_session_id)]
            return max(i for i in ids if i is not None) if any(ids) else None
        except Exception:
            return None
    except Exception:
        return None


def run_scoring_pass(
    db, car_id: int, track: str, layout_id: str, new_session_id: int
) -> int:
    """Score applied-but-unscored recs for this car+track against the just-finished
    session, persisting a telemetry verdict + a per-rule learning outcome for each.

    Returns the number of non-trivial (not insufficient_data) outcomes written.
    Never raises. Headless — safe to call from the backend dispatcher thread. This is
    the extracted body of the classic MainWindow._trigger_scoring_pass (minus the Qt
    home-nudge), so both UIs run identical scoring.
    """
    written = 0
    try:
        if db is None or car_id <= 0 or not track:
            return 0
        # The just-finished session (before new_session_id) is the "after" side.
        after_sid = db.get_previous_session_id(car_id, track, new_session_id)
        if not after_sid:
            return 0
        recs = db.get_applied_unverified_recs(car_id, track, layout_id)
        # A rec can never be scored against its own creation session.
        scoreable = [r for r in recs if r.get("session_id") != after_sid]
        if not scoreable:
            return 0
        from data.recommendation_scoring import (
            aggregate_lap_window, compute_verdict_and_confidence,
        )
        from strategy.setup_feedback_evidence import (
            combine_driver_feedback_text, verify_change_outcome,
        )
        after_laps = db.get_laps_for_scoring(after_sid)
        after_window = aggregate_lap_window(after_laps)
        multi_count = len(scoreable)
        _feedback_rows = db.get_recent_feedback(car_id, track)
        has_driver_feedback = bool(_feedback_rows)
        _feedback_text = combine_driver_feedback_text(
            _feedback_rows[0] if _feedback_rows else {})
        for rec in scoreable:
            before_laps = db.get_laps_for_scoring(rec["session_id"])
            before_window = aggregate_lap_window(before_laps)
            result = compute_verdict_and_confidence(
                rec, before_window, after_window,
                multi_rec_count=multi_count,
                has_driver_feedback=has_driver_feedback,
            )
            db.persist_score(result.rec_id, result.verdict, result.confidence,
                             result.details)
            if result.verdict == "insufficient_data":
                continue
            try:
                db.record_lineage_outcome_by_rec(result.rec_id, result.verdict, after_sid)
            except Exception:
                pass
            written += 1
            try:
                _ac_json = rec.get("approved_changes_json") or ""
                if not _ac_json:
                    continue
                _ac_list = json.loads(_ac_json)
                if not isinstance(_ac_list, list):
                    continue
                _dpv = rec.get("driver_profile_version") or ""
                _rev = rec.get("rule_engine_version") or ""
                for _ch in _ac_list:
                    if not isinstance(_ch, dict):
                        continue
                    _rule_id = _ch.get("rule_id", "")
                    if not _rule_id:
                        continue
                    _g47 = verify_change_outcome(
                        _rule_id, _ch.get("field", ""), car_id, track, layout_id,
                        before_window, after_window, _feedback_text)
                    db.record_learning_outcome(
                        car_id=car_id, track=track, layout_id=layout_id,
                        session_id=after_sid, session_type="", rule_id=_rule_id,
                        source_path="Analyse", verdict=result.verdict,
                        confidence=result.confidence,
                        driver_profile_version=_dpv, rule_engine_version=_rev,
                        target_issue=_g47["target_issue"],
                        evidence_summary=_g47["evidence_summary"],
                        driver_feedback=_feedback_text,
                        safety_notes=_g47["safety_notes"],
                        outcome_kind=_g47["outcome_kind"])
            except Exception:
                pass  # learning persistence is best-effort — never disrupt scoring
    except Exception:
        pass
    return written
