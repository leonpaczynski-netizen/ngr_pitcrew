"""Tests for the live-wiring adapters (canonical outputs -> shell VMs)."""

import types
import pytest

from ui.shell_feed_adapters import (
    live_pit_wall_vm_from_state, strategy_plan_vm_from_rpvm,
    qualifying_vm_from_cc_view, debrief_vm_from_memory,
)


def _ns(**kw):
    return types.SimpleNamespace(**kw)


class TestLive:
    def test_maps_state(self):
        st = _ns(current_lap=18, laps_remaining=16, fuel_remaining_l=34.0,
                 fuel_per_lap_actual=2.0, current_compound="Soft", tyre_age_laps=6,
                 pit_stops_completed=1, laps_since_pit=6, lap_time_actual_s=90.5,
                 lap_time_plan_s=90.0, required_stops=2, telemetry_fresh=True)
        vm = live_pit_wall_vm_from_state(st, connected=True)
        assert vm.lap == "18 / 34"
        assert vm.fuel.startswith("34.0 L") and "17 laps" in vm.fuel
        assert vm.tyre == "Soft · 6 laps"
        assert vm.gap_to_plan == "+0.5s"
        assert vm.freshness == "live"

    def test_none_state_disconnected(self):
        vm = live_pit_wall_vm_from_state(None, connected=False)
        assert vm.freshness == "none"

    def test_never_raises(self):
        assert live_pit_wall_vm_from_state(_ns(), connected=True) is not None


class TestStrategy:
    def test_maps_rpvm(self):
        rpvm = _ns(
            has_recommendation=True,
            recommended_strategy_title="2-stop", estimated_total_time="1:02:14",
            confidence_label="High", driver_explanation="Fastest on measured deg.",
            stint_plan_rows=[{"laps": 12, "compound": "Soft"}, {"laps": 10, "compound": "Medium"}],
            candidate_comparison_rows=[
                {"strategy": "2-stop", "status": "Recommended", "total_time": "1:02:14",
                 "compounds": "S/S/M", "pit_stops": 2, "confidence": "High", "risk": "—"},
                {"strategy": "1-stop", "status": "Alternative", "total_time": "1:02:49",
                 "confidence": "Medium", "risk": "deg"},
            ],
            evidence_source_rows=[{"label": "Tyre deg", "detail": "0.06 s/lap", "category": "measured"},
                                  {"label": "Fuel burn", "detail": "assumed", "category": "assumed"}],
            missing_evidence_rows=["Safety-car probability"],
            risk_flags=["Tyre deg medium"], warnings=["Replan if deg > 0.10"])
        vm = strategy_plan_vm_from_rpvm(rpvm)
        assert len(vm.options) == 2
        assert vm.options[0].recommended is True
        assert vm.options[0].confidence == "high"
        assert vm.options[0].stints == ("12 Soft", "10 Medium")
        srcs = {i.name: i.source for i in vm.inputs}
        assert srcs["Tyre deg"] == "measured"
        assert srcs["Safety-car probability"] == "missing"
        assert vm.replan_triggers == ("Replan if deg > 0.10",)

    def test_no_recommendation_empty(self):
        assert strategy_plan_vm_from_rpvm(_ns(has_recommendation=False)).has_plan is False
        assert strategy_plan_vm_from_rpvm(None).has_plan is False


class TestQualifying:
    def test_maps_view(self):
        view = {"ok": True,
                "readiness": [["Setup convergence", "Locked", "Quali v3"],
                              ["Track limits", "not reviewed", ""]],
                "attention": [{"kind": "risk", "message": "Turn 1 lock-up", "tone": "warn"}],
                "next_action": {"detail": "Softer rear ARB gives one-lap pace."}}
        vm = qualifying_vm_from_cc_view(view, active_setup_label="Quali v3", soft_confirmed=True)
        labels = {i.label: i.status for i in vm.items}
        assert labels["Qualifying setup selected"] == "ok"
        assert labels["Soft tyres confirmed"] == "ok"
        assert labels["Setup convergence"] == "ok"        # 'Locked' -> ok
        assert labels["Track limits"] == "blocked"        # 'not reviewed' -> blocked
        assert vm.blockers == ("Turn 1 lock-up",)
        assert "one-lap pace" in vm.explanation

    def test_soft_not_confirmed_blocks(self):
        vm = qualifying_vm_from_cc_view({"ok": True, "readiness": []},
                                        active_setup_label="Q", soft_confirmed=False)
        assert any(i.label == "Soft tyres confirmed" and i.status == "blocked" for i in vm.items)

    def test_bad_view_empty(self):
        assert qualifying_vm_from_cc_view(None).items == ()


class TestDebrief:
    def test_maps_memory(self):
        # The REAL build_cross_session_memory shape: nested memory/scorecard/comparison,
        # not the top-level band/issues this used to assert (which never existed, so the
        # Debrief was always empty — UAT-6 "debrief doesn't seem to be doing anything").
        mem = {
            "ok": True, "record_count": 2,
            "memory": {
                "issues": [
                    {"issue_type": "understeer", "corner": "the Esses",
                     "currently_resolved": True, "times_regressed": 0},
                    {"issue_type": "entry_instability", "corner": "Turn 1",
                     "currently_resolved": False, "times_regressed": 1},
                ],
                "protected_behaviours": [{"label": "Rear ARB 4-5 window"}],
            },
            "scorecard": {"band": "improving"},
            "comparison": {"earlier_label": "Session 1", "later_label": "Session 2",
                           "verdict": "improved", "regressions_delta": -1},
        }
        vm = debrief_vm_from_memory(mem)
        assert vm.has_debrief is True
        assert "improving" in vm.what_happened
        assert vm.improved == ("understeer at the Esses",)
        assert vm.regressed == ("entry instability at Turn 1",)
        assert vm.carry_forward == ("Rear ARB 4-5 window",)

    def test_insufficient_empty(self):
        assert debrief_vm_from_memory({"insufficient": True}).has_debrief is False
        assert debrief_vm_from_memory(None).has_debrief is False
        assert debrief_vm_from_memory({"ok": False}).has_debrief is False
        # No records = the honest placeholder, not a hollow "band: insufficient" debrief.
        assert debrief_vm_from_memory(
            {"ok": True, "record_count": 0, "scorecard": {"band": "insufficient"}}
        ).has_debrief is False
