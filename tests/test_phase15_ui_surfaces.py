"""Phase 15 — additive UI surfaces for the Race-Engineer remediation.

_render_race_engineer_surfaces turns the response fields the backend now emits
(qualifying_brief / candidate_comparison / test_sequence / feedback_dispositions /
historical_comparison / arbitration) into read-only HTML panels. It touches no
self state, so it is tested directly. Legacy/empty responses render nothing.
"""
from __future__ import annotations

from ui.setup_builder_ui import SetupBuilderMixin

_render = SetupBuilderMixin._render_race_engineer_surfaces


def _r(data):
    return _render(None, data)   # method ignores self


# ------------------------------------------------- empty / legacy safety

def test_empty_dict_renders_nothing():
    assert _r({}) == ""


def test_non_dict_renders_nothing():
    assert _render(None, None) == ""
    assert _render(None, "legacy string") == ""


def test_legacy_response_without_new_fields_renders_nothing():
    assert _r({"analysis": "x", "changes": []}) == ""


# ------------------------------------------------- individual panels

def test_qualifying_brief_panel():
    html = _r({"qualifying_brief": {
        "is_qualifying": True, "objective": "one-lap pace",
        "strengths": ["sharper turn-in"], "compromises": ["tyre life"],
        "one_lap_warning": "do not race it"}})
    assert "Qualifying tune" in html
    assert "sharper turn-in" in html and "tyre life" in html
    assert "do not race it" in html


def test_qualifying_brief_absent_when_not_qualifying():
    assert _r({"qualifying_brief": {"is_qualifying": False}}) == ""


def test_candidate_comparison_table():
    html = _r({"candidate_comparison": {
        "columns": [{"name": "current", "label": "Current", "source": "on-car"},
                    {"name": "recommended", "label": "Rec", "source": "rules"}],
        "rows": [{"field": "arb_rear", "values": {"current": 5.0, "recommended": 7.0},
                  "differs": True}]}})
    assert "Candidate comparison" in html
    assert "arb_rear" in html and "Current" in html and "Rec" in html
    assert "5" in html and "7" in html


def test_candidate_comparison_absent_when_no_rows():
    assert _r({"candidate_comparison": {"columns": [{"name": "c", "label": "C"}],
                                        "rows": []}}) == ""


def test_test_sequence_panel():
    html = _r({"test_sequence": {"note": "one at a time", "stages": [
        {"order": 1, "field": "arb_front", "change": "lower arb_front (6 → 4)",
         "success_criterion": "pushes wide eases", "rollback": "revert to 6",
         "rationale": "high confidence", "isolate_note": "isolate this"}]}})
    assert "one at a time" in html
    assert "lower arb_front" in html and "pushes wide eases" in html
    assert "revert to 6" in html and "isolate this" in html


def test_feedback_dispositions_panel():
    html = _r({"feedback_dispositions": [
        {"feedback": "pushes wide", "state": "addressed", "detail": "softened front ARB"},
        {"feedback": "fuel high", "state": "strategy", "detail": ""}]})
    assert "pushes wide" in html and "addressed" in html
    assert "softened front ARB" in html and "strategy" in html


def test_historical_comparison_panel_flags_deviation():
    html = _r({"historical_comparison": [
        {"field": "lsd_accel", "current": 8, "historical": 8, "recommended": 17,
         "deviation_flagged": True, "note": "moves away from proven 8"}]})
    assert "lsd_accel" in html and "proven" in html
    assert "moves away from proven 8" in html


def test_arbitration_panel_when_notes_present():
    html = _r({"arbitration": {"compounding": True, "offsetting": False,
                               "net_direction": "looser",
                               "contributors": ["aero_front", "arb_rear"],
                               "notes": ["Balance note: overshoot risk"]}})
    assert "Balance interaction" in html and "overshoot risk" in html


def test_arbitration_absent_when_no_notes():
    assert _r({"arbitration": {"compounding": False, "notes": [],
                               "contributors": []}}) == ""


# ------------------------------------------------- combined + robustness

def test_all_panels_together():
    html = _r({
        "qualifying_brief": {"is_qualifying": True, "objective": "o",
                             "strengths": ["s"], "compromises": ["c"],
                             "one_lap_warning": "w"},
        "candidate_comparison": {"columns": [{"name": "current", "label": "Cur"}],
                                 "rows": [{"field": "f", "values": {"current": 1.0},
                                           "differs": False}]},
        "test_sequence": {"note": "n", "stages": [
            {"order": 1, "field": "f", "change": "ch", "success_criterion": "sc",
             "rollback": "rb", "rationale": "r", "isolate_note": ""}]},
        "feedback_dispositions": [{"feedback": "fb", "state": "deferred", "detail": ""}],
        "historical_comparison": [{"field": "f", "current": 1, "historical": 2,
                                   "recommended": 3, "deviation_flagged": False,
                                   "note": ""}],
    })
    assert "Qualifying tune" in html
    assert "Candidate comparison" in html
    assert "How to test these changes" in html
    assert "What happened to each thing you reported" in html
    assert "Compared to your proven setups" in html


def test_malformed_field_does_not_crash():
    # values not a dict, stages not a list -> guarded, no exception
    _r({"candidate_comparison": {"columns": [{"name": "c", "label": "C"}],
                                 "rows": [{"field": "f", "values": None,
                                           "differs": False}]}})


# ------------------------------------------------- end-to-end (backend -> UI)

def test_real_backend_response_renders_without_error(monkeypatch):
    """A real build_combined_setup_response output must feed the renderer cleanly —
    guards against backend/UI field-shape drift."""
    import json
    import tests.test_group41_validation_gate as G
    import strategy.driving_advisor as da
    adv = G._make_full_advisor({}, [G._make_lap()])
    monkeypatch.setattr(da, "call_api", lambda *a, **k: json.dumps({
        "status": "APPROVED", "warnings": [], "contradictions": [],
        "missing_evidence": [], "explanation_notes": "ok"}))
    res = json.loads(adv.build_combined_setup_response(
        setup_dict={"arb_front": 6, "arb_rear": 5, "aero_front": 400},
        car_name="Porsche 911 RSR (991) '17", purpose="Qualifying",
        feeling="The car pushes wide in the middle of the corner"))
    html = _r(res)
    # qualifying purpose -> the qualifying panel must appear from the real payload
    assert "Qualifying tune" in html
    assert isinstance(html, str)


def test_real_baseline_qualifying_renders_panel():
    import json
    import tests.test_group41_validation_gate as G
    from strategy.setup_ranges import resolve_ranges
    adv = G._make_full_advisor({}, [G._make_lap()])
    car = "Porsche 911 RSR (991) '17"
    res = json.loads(adv.build_baseline_setup_response(
        car, resolve_ranges(car), "RWD", 6, None, False,
        session_type="Qualifying", duration_mins=0.0))
    assert "Qualifying tune" in _r(res)
