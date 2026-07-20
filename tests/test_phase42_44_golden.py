"""Phase 42-44 — deterministic golden rendering."""
from strategy.material_context import build_material_context_trust
from strategy.material_context_render import render_material_context_text
from strategy.live_advisory import build_candidate_prompts
from strategy.live_advisory_engine import evaluate_live_advisories
from strategy.live_advisory_render import render_advisory_text


_CUR = {"driver": "Leon", "car": "Porsche", "track": "Fuji", "layout_id": "fc", "discipline": "race",
        "gt7_version": "1.49", "tyre_multiplier": "1"}
_LEGACY = {"driver": "Leon", "car": "Porsche", "track": "Fuji", "layout_id": "fc",
           "discipline": "race", "gt7_version": "1.49"}
_PLAN = {"content_fingerprint": "pfp", "run_structure": {"minimum_clean_laps": 3, "warm_up_laps": 2}}


def test_material_context_render_deterministic_ascii():
    t = build_material_context_trust(_CUR, _LEGACY, "tyre_degradation").to_dict()
    a, b = render_material_context_text(t), render_material_context_text(t)
    assert a == b and a.isascii()
    assert "Material context trust" in a and "Limiting fields" in a


def test_advisory_render_deterministic_ascii():
    snap = {"context_fingerprint": "cfp", "run_plan_fingerprint": "pfp", "run_active": True, "lap": 3,
            "clean_laps": 1, "telemetry_fresh": True, "plan_current": True, "session_active": True,
            "segment_type": "straight", "workload": "low", "approaching_corner": "T2"}
    dec = evaluate_live_advisories(build_candidate_prompts(snap, _PLAN, {"state": "run_active"},
                                   {"priorities": [{"corner": "T2", "technique_focus": "x",
                                                    "confidence": "high"}]}),
                                   snap, now_monotonic=100.0, state={}).to_dict()
    a, b = render_advisory_text(dec), render_advisory_text(dec)
    assert a == b and a.isascii()
    assert "Current advisory" in a and "Suppressed" in a


def test_advisory_render_no_setup_values():
    dec = {"delivered": None, "suppressed": [], "active_objective": ""}
    t = render_advisory_text(dec).lower()
    assert "apply" not in t
