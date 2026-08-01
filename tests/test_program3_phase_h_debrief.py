"""Program 3 Phase H — end-of-event debrief aggregation (§20).

The defining rule (gate #18): every finding is tagged with its provenance so the
debrief never conflates measured fact, deterministic inference, and driver report.
"""

from data.session_db import SessionDB
from strategy.event_debrief import (
    DebriefProvenance, build_event_debrief,
)
from strategy.ptt_interaction import PttInteractionRecord


# --------------------------------------------------------------------------- #
# pure aggregator
# --------------------------------------------------------------------------- #

def test_event_overview_is_a_measured_fact():
    d = build_event_debrief(
        event_id=5, track="Fuji",
        session_runs=[{"status": "complete"}, {"status": "complete"}, {"status": "failed"}])
    ov = d.by_section("event_overview")
    assert ov and ov[0].provenance == DebriefProvenance.MEASURED_FACT
    assert "2 completed" in ov[0].text and "1 abandoned/failed" in ov[0].text


def test_strategy_revisions_are_facts_with_triggers():
    d = build_event_debrief(strategy_revisions=[
        {"trigger": "pre_race", "is_active": 0, "revision_index": 1},
        {"trigger": "ptt_accept", "is_active": 1, "revision_index": 2}])
    sr = d.by_section("strategy_review")
    assert any(f.provenance == DebriefProvenance.MEASURED_FACT and "ptt_accept" in f.text for f in sr)


def test_ambiguous_ptt_is_an_inference_not_a_fact():
    d = build_event_debrief(ptt_interactions=[
        {"ambiguous": True, "command_class": "query"},
        {"ambiguous": False, "command_class": "strategy_ack"}])
    inf = d.inferences
    assert any("ambiguous" in f.text.lower() for f in inf)
    # the raw count is a fact; the interpretation is an inference — never merged
    assert any(f.provenance == DebriefProvenance.MEASURED_FACT for f in d.by_section("engineer_review"))


def test_driver_report_is_kept_separate():
    d = build_event_debrief(ptt_interactions=[
        {"command_class": "report", "recognised_action": "rain", "lap_number": 4}])
    dr = d.driver_reports
    assert len(dr) == 1
    assert dr[0].provenance == DebriefProvenance.DRIVER_REPORT
    assert "rain" in dr[0].text and "lap 4" in dr[0].text
    # a driver report must never be counted as a measured fact
    assert dr[0] not in d.facts


def test_quarantine_and_unresolved():
    d = build_event_debrief(
        quarantined=[{"record_type": "session"}],
        unresolved_questions=["Did the softer front ARB actually help mid-corner?"])
    assert any(f.provenance == DebriefProvenance.MEASURED_FACT and "quarantined" in f.text
               for f in d.by_section("data_quality"))
    assert any(f.provenance == DebriefProvenance.UNRESOLVED for f in d.unresolved)


def test_never_raises_on_garbage():
    d = build_event_debrief(session_runs=[None, {"status": None}])  # type: ignore
    assert d is not None


# --------------------------------------------------------------------------- #
# DB convenience over the spine
# --------------------------------------------------------------------------- #

def test_build_event_debrief_for_event_reads_the_spine(tmp_path):
    db = SessionDB(str(tmp_path / "s.db"))
    eid = int(db.upsert_event({"name": "Round 5", "track": "Fuji"}))
    sid = db.open_session(333, "Fuji", "Race", event_id=eid)     # C1 run
    run = db.get_run_for_session(sid)
    db.append_strategy_revision(session_run_id=run["run_id"], event_id=eid,
                                trigger="ptt_accept", plan_json="{}")
    db.record_ptt_interaction(PttInteractionRecord(
        event_id=eid, session_run_id=run["run_id"], command_class="report",
        recognised_action="rain", lap_number=4).as_dict())

    d = db.build_event_debrief_for_event(eid)
    assert d["event_id"] == eid and d["track"] == "Fuji"
    provs = {f["provenance"] for f in d["findings"]}
    assert "measured_fact" in provs and "driver_report" in provs
    texts = " ".join(f["text"] for f in d["findings"]).lower()
    assert "strategy revision" in texts and "rain" in texts
