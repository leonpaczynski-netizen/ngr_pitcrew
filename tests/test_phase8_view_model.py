"""Engineering Brain Phase 8 — Qt-free Development History view-model tests."""
import pytest

from data.session_db import SessionDB
from strategy.development_history import MemoryContextKey, build_development_record
from ui import development_history_vm as vm


def _res(key, typ, state, present=True):
    return {"issue_key": key, "family": "rotation", "issue_type": typ, "axle": "front",
            "phase": "apex", "segment_id": "T1", "corner_name": "Turn 1",
            "residual_state": state, "is_new": False, "is_regression": False,
            "still_present": present, "protected_good": False, "confidence": "high"}


@pytest.fixture
def result():
    db = SessionDB(":memory:")
    ctx = MemoryContextKey(car="RSR", track="Fuji", layout_id="fc", discipline="Race",
                           compound="RH")
    for i, (status, state, present) in enumerate([
            ("no_meaningful_change", "unchanged", True),
            ("partial_improvement", "improved_but_present", True),
            ("confirmed_improvement", "resolved", False)], start=1):
        outcome = {"id": i, "experiment_id": 10 + i, "status": status,
                   "confidence_level": "high", "scope_fingerprint": "sf",
                   "test_session_id": str(300 + i),
                   "protected": [{"behaviour": "rear traction", "field": "lsd_decel",
                                  "verdict": "preserved", "confidence": "high"}],
                   "failed_directions": []}
        exp = {"id": 10 + i, "scope_fingerprint": "sf",
               "changes": [{"field": "toe_front", "from_value": "0.1", "to_value": "0.2"}]}
        rec = build_development_record(
            outcome, exp, context=ctx, scope_fingerprint="sf",
            working_windows=[{"field": "toe_front", "min": 0.1, "max": 0.3,
                              "confidence": "high"}],
            residuals=[_res("k", "understeer", state, present)],
            recorded_at=f"2026-07-0{i}T10:00", session_date=f"2026-07-0{i}")
        db._persist_development_record(rec, created_at=rec.recorded_at)
    return db.build_cross_session_memory(
        car="RSR", track="Fuji", layout_id="fc", discipline="Race", compound="RH")


def test_not_empty(result):
    assert not vm.is_empty(result)
    assert "RSR" in vm.context_label(result)


def test_scorecard_and_metrics_rows(result):
    assert vm.scorecard_row(result)
    m = dict(vm.metrics_rows(result))
    assert "Issue resolution rate" in m


def test_resolved_and_remaining_rows(result):
    resolved = vm.resolved_issue_rows(result)
    assert any("understeer" in r[0] for r in resolved)
    assert all(len(r) == len(vm.ISSUE_COLUMNS) for r in resolved)


def test_timeline_rows(result):
    rows = vm.timeline_rows(result)
    assert rows
    assert all(len(r) == len(vm.TIMELINE_COLUMNS) for r in rows)


def test_protected_and_knowledge_rows(result):
    assert vm.protected_behaviour_rows(result)
    assert any("Never" in r[0] or "Preferred" in r[0] or "Protected" in r[0]
               for r in vm.protected_knowledge_rows(result))


def test_experiment_and_window_rows(result):
    assert len(vm.experiment_history_rows(result)) == 3
    assert vm.window_evolution_rows(result)


def test_comparison_rows(result):
    rows = dict(vm.comparison_rows(result))
    assert "Verdict" in rows


def test_is_empty_on_bad_result():
    assert vm.is_empty(None)
    assert vm.is_empty({"ok": False})
    assert vm.is_empty({"ok": True, "record_count": 0})
