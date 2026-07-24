"""Standalone INTERACTIVE preview of the new NGR Pit Crew shell.

Opens ONLY the new shell, populated with representative sample data. It starts no
telemetry backend, binds no UDP port, and never writes to your config or database —
so it is completely safe to run at any time, including during a race weekend, and
will not affect the classic dashboard you normally use.

Run it with:

    python preview_new_shell.py

(or double-click run_new_shell_preview.bat). Click the left nav, the progress-rail
stages, and the Pit Crew Engineer card's actions to move around. Close the window
to exit. This is a visual/interaction preview with SAMPLE data — the real event,
setup and live data are wired in through the app itself (flag NGR_NEW_SHELL=1).
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PyQt6.QtWidgets import QApplication

from ui.pit_crew_shell import PitCrewShell
from ui.pit_crew_controller import PitCrewController
from ui import ngr_theme as theme
from data.event_context import build_event_context
from ui.setup_recommendation_vm import build_recommendation_vm
from ui.components.setup_lineage import LineageNode


def main() -> int:
    app = QApplication.instance() or QApplication([])

    controller = PitCrewController()
    shell = PitCrewShell(controller)
    shell.setWindowTitle("NGR Pit Crew — NEW SHELL PREVIEW (sample data)")
    shell.resize(1380, 860)

    event = build_event_context(
        event={"id": 5, "name": "NGR GT Cup - Round 5"},
        strategy={"car": "Porsche 911 RSR",
                  "track_location_id": "Watkins Glen", "layout_id": "Long"},
    )
    controller.patch(
        event=event,
        programme_stage="garage",
        active_setup_label="Quali v3",
        active_setup_applied=True,
        connected=True,
        stage_states={
            "briefing": theme.STAGE_COMPLETE,
            "garage": theme.STAGE_CURRENT,
            "practice": theme.STAGE_AVAILABLE,
            "review": theme.STAGE_AVAILABLE,
            "qualifying": theme.STAGE_BLOCKED,
            "strategy": theme.STAGE_BLOCKED,
            "race": theme.STAGE_BLOCKED,
            "debrief": theme.STAGE_NOT_REQUIRED,
        },
    )
    shell.set_guidance_view({
        "ok": True,
        "next_action": {
            "headline": "Lock the qualifying setup",
            "detail": "Convergence is stable across the last 3 practice runs; "
                      "locking frees you to prepare qualifying.",
            "target_surface": "setup", "tone": "info",
        },
        "progress": {"practice_sessions": 3, "valid_laps": 42,
                     "setup_experiments": 2, "setup_confidence": "high"},
        "attention": [{"kind": "risk",
                       "message": "Rear tyres graining after lap 6", "tone": "warn"}],
        "quick_actions": [{"label": "Open Practice", "target_surface": "practice"}],
    })

    # Populate the Garage workspace so clicking "Garage" shows a live example.
    shell.garage_page.set_recommendation(
        build_recommendation_vm({
            "changes": [
                {"field": "arb_rear", "setting": "Rear anti-roll bar", "from": 5, "to": 3,
                 "to_clamped": 4, "confidence_level": "High",
                 "rationale": "reduce mid-corner understeer", "symptom": "mid-corner understeer"},
                {"field": "brake_bias_front", "setting": "Brake bias (front %)", "from": 54.0,
                 "to": 52.5, "confidence_level": "Medium",
                 "rationale": "improve entry stability", "symptom": "entry instability"},
                {"field": "ride_height_rear", "setting": "Ride height rear", "from": 70, "to": 74,
                 "confidence_level": "Medium", "rationale": "raise rear for rotation", "symptom": "understeer"},
                {"field": "aero_rear", "setting": "Rear downforce", "from": 350, "to": 320,
                 "confidence_level": "Low", "rationale": "reduce drag for the straights", "symptom": "low top speed"},
            ],
            "diagnosis": {"primary_issue": "Mid-corner understeer through the Esses limiting rotation"},
        }),
        discipline="qualifying", active_setup="Quali v3", saved=True, applied=False,
        setup_values={
            "tyre_front": "Racing: Hard", "tyre_rear": "Racing: Hard",
            "ride_height_front": 60, "ride_height_rear": 74,
            "arb_front": 5, "arb_rear": 4,
            "dampers_front_comp": 30, "dampers_rear_comp": 30,
            "dampers_front_ext": 40, "dampers_rear_ext": 40,
            "springs_front": 3.50, "springs_rear": 3.50,
            "camber_front": 3.0, "camber_rear": 3.0,
            "toe_front": 0.10, "toe_rear": 0.20,
            "aero_front": 430, "aero_rear": 590,
            "lsd_initial": 15, "lsd_accel": 40, "lsd_decel": 50,
            "torque_distribution_rear": 100, "brake_bias_front": 0,
            "final_drive": 3.90, "transmission_max_speed_kmh": 300,
            "ballast_kg": 0, "power_restrictor": 100,
            "ecu_ingame": "Fully Customisable", "ecu_ingame_output": 100,
        },
        lineage_nodes=[
            LineageNode("n3", "Quali v3", outcome="improved", is_current=True,
                        summary="Rear ARB 5->4 + rear ride height 70->74 - rotation improved",
                        discipline="qualifying"),
            LineageNode("n2", "Quali v2", outcome="worse",
                        summary="Softer front springs - lost front end on entry (reverted)",
                        discipline="qualifying"),
            LineageNode("n1", "Quali v1", outcome="unchanged",
                        summary="Brake bias 54->53 - no measurable change", discipline="qualifying"),
            LineageNode("n0", "Base", outcome="", summary="Baseline build from car + track profile",
                        discipline="base"),
        ],
        comparisons=[
            ("Base ↔ Qualifying", "Base",
             {"ride_height_front": 60, "ride_height_rear": 70, "arb_front": 5, "arb_rear": 5,
              "aero_front": 430, "aero_rear": 560, "brake_bias_front": 54,
              "tyre_front": "Racing: Medium", "tyre_rear": "Racing: Medium"},
             "Qualifying",
             {"ride_height_front": 60, "ride_height_rear": 74, "arb_front": 5, "arb_rear": 4,
              "aero_front": 430, "aero_rear": 590, "brake_bias_front": 52,
              "tyre_front": "Racing: Soft", "tyre_rear": "Racing: Soft"}),
        ],
    )
    # Shift beep — part of the car setup, per discipline.
    shell.garage_page.set_shift_rpm(
        7600, "The beep fires at 7600 RPM in a qualifying session (from this setup).")
    # A converged setup that can be locked for the event.
    shell.garage_page.set_lock_state(
        lockable=True, locked=False,
        hint="The setup has converged — lock it to mark it final for the event.")

    # Programme map — where the driver is across the whole event programme.
    from strategy.programme_map import build_programme_map
    shell.programme_page.set_map(build_programme_map([
        ["base_setup", "developing", "2 exact / 0 labelled sample(s)"],
        ["race_setup", "developing", "2 exact / 0 labelled sample(s)"],
        ["driver_coaching", "adequate", "3 exact / 0 labelled sample(s)"],
        ["consistency", "strong", "5 exact / 0 labelled sample(s)"],
        ["tyre_evidence", "missing", "0 exact / 0 labelled sample(s)"],
        ["fuel_evidence", "developing", "1 exact / 0 labelled sample(s)"],
        ["race_pace", "adequate", "3 exact / 0 labelled sample(s)"],
        ["qualifying_setup", "developing", "2 exact / 0 labelled sample(s)"],
        ["strategy_evidence", "missing", "0 exact / 0 labelled sample(s)"],
    ], next_domain="setup_base"))

    # Populate the Practice run card + corner options so 'Practice' shows a live example.
    from ui.components.run_card import RunCardVM
    from strategy.run_brief import brief_for_domain
    # Validating a recommendation is a setup experiment, so it carries that brief's
    # driving instructions — the same mapping the real bridge applies.
    _brief = brief_for_domain("working_window")
    shell.run_card.set_run(RunCardVM.from_run_plan({
        "objective": "Confirm the rear ARB change improves mid-corner rotation without hurting entry",
        "setup": "Quali v3",
        "changes": ["Rear ARB 5 -> 4", "Rear ride height 70 -> 74"],
        "expected_effect": "Less understeer through the Esses; entry stability unchanged",
        "how_to_drive": list(_brief.how_to_drive),
        "monitor": ["Turn 6 (Esses)", "Turn 10 entry", "Turn 1 braking"],
        "reports": list(_brief.reports),
        "fuel": "12 L", "tyre": "Racing: Soft", "target_laps": "5",
        "push_level": "Qualifying push", "purpose": "diagnosis",
        "invalidation": ["Lock-up into Turn 1", "Any off-track excursion"],
    }))
    shell.feedback_form.set_corner_options(
        ["Turn 1", "Turn 5", "Turn 6 (Esses)", "Turn 10", "Turn 11 (Bus Stop)"])

    # Practice outcome
    from ui.components.practice_outcome import PracticeOutcomeVM
    shell.practice_outcome.set_outcome(PracticeOutcomeVM(
        verdict="improved", verdict_summary="The rear ARB change worked — rotation up, no new instability.",
        telemetry_findings=("Mid-corner min speed +1.8 km/h at Turn 6",),
        feedback_summary="Better than previous; less understeer mid-corner",
        agreements=("Both show improved mid-corner rotation",),
        changed_vs_previous=("Rear ARB 5->4", "Rear ride height 70->74"),
        confidence="high", primary_action_label="Keep change & build next", primary_action_key="keep",
        secondary_action_label="Prepare qualifying", secondary_action_key="to_qualifying"))

    # Qualifying readiness
    from ui.components.qualifying_readiness import QualifyingReadinessVM, ReadinessItem
    shell.qualifying_page.set_readiness(QualifyingReadinessVM(
        items=(ReadinessItem("Qualifying setup selected", "ok", "Quali v3"),
               ReadinessItem("Soft tyres confirmed", "ok", "Racing: Soft"),
               ReadinessItem("Fuel target", "ok", "2 laps + margin"),
               ReadinessItem("Out-lap plan", "ok", "1 build lap, then push"),
               ReadinessItem("Traffic plan", "warn", "Leave a gap on the out-lap"),
               ReadinessItem("Risk corners", "warn", "Turn 1 lock-up risk on cold fronts")),
        explanation="Softer rear ARB gives more rotation for one-lap pace. Protect the fronts on the out-lap; "
                    "if the first push lap is compromised, back out and reset for a second run."))

    # Race strategy
    from ui.components.strategy_plan import StrategyPlanVM, StrategyOption, StrategyInput
    shell.strategy_page.set_plan(StrategyPlanVM(
        options=(StrategyOption("2-stop (Soft-Soft-Medium)", key="c2", total_time="1:02:14",
                                expected_laps="34 laps", gap="best",
                                stints=("12 laps Soft", "12 laps Soft", "10 laps Medium"),
                                tyre_sequence="S→S→M",
                                fuel_target="Full each stint", pit_windows="2 stop(s)", confidence="high",
                                summary=("vs 1-stop: 1 more stop, 22s more in the pits, "
                                         "57s less tyre degradation — 35s faster overall."),
                                recommended=True),
                 StrategyOption("1-stop (Medium-Hard)", key="c1", total_time="1:02:49",
                                expected_laps="34 laps", gap="+35.0s", pit_windows="1 stop(s)",
                                stints=("18 laps Medium", "16 laps Hard"),
                                confidence="medium",
                                summary=("vs 2-stop: 1 fewer stop, 22s less in the pits, "
                                         "57s more tyre degradation — 35s slower overall."),
                                pit_stops=("Stop 1 (lap 12): leave with 28 L · ~30s · fit Racing Soft",
                                           "Stop 2 (lap 24): leave with 24 L · ~28s · fit Racing Medium"))),
        risks=(("Tyre deg", "medium"), ("Traffic", "low")),
        inputs=(StrategyInput("Tyre deg", "0.06 s/lap", "measured"),
                StrategyInput("Pit loss", "22 s", "manual"),
                StrategyInput("Fuel burn", "2.1 L/lap", "measured"),
                StrategyInput("Safety car", "unknown", "missing")),
        replan_triggers=("Degradation exceeds 0.10 s/lap", "A safety car inside the first 10 laps")))

    # Live pit wall — live race engineer end-to-end demo.
    # State mirrors a mid-race moment: fuel is 0.3 L/lap over plan AND a wet-weather
    # replan candidate is available.  The engineer instruction, gap-to-plan with both
    # pace and fuel deltas, and the red replan warning (with PTT call-to-action) are
    # all populated, and the recommended candidate plan card is shown so the reviewer
    # can see what the driver would accept by saying "accept plan".
    from ui.components.live_pit_wall import LivePitWallVM
    from ui.shell_feed_adapters import live_plan_dict_from_candidate
    shell.live_page.set_state(LivePitWallVM(
        lap="18 / 34", position="P4", stint="Stint 2 · L6", fuel="34 L (11 laps)",
        tyre="Soft · 62%", pit_window="L22–L25",
        gap_to_plan="+1.2s / +0.3 L per lap",
        engineer_instruction=(
            "Fuel is 0.3 L/lap over plan — lift and coast into the hairpin."),
        next_decision="Pit call on lap 22 — weather closing in",
        warning=(
            "Weather closing in — an extra stop for wets may be faster. "
            "Say 'accept plan' to switch, or 'keep plan' to stay out."),
        freshness="live", confidence="medium", map_trust="approved",
        ptt_status="RADIO READY"))
    # Recommended replan candidate — the plan the driver would accept by voice.
    # Built via live_plan_dict_from_candidate so the reviewer can trace the full path
    # from candidate dict -> show_plan shape -> rendered card.
    shell.live_page.show_plan(live_plan_dict_from_candidate({
        "label": "3-stop (Soft-Soft-Wet-Wet)",
        "stop_count_delta": 1,
        "expected_completed_laps": 34,
        "fuel_target_note": "Reduce to 28 L per stop — wets burn less",
        "tyre_note": "Switch to Wets from stop 2 once rain is confirmed",
        "expected_gain_detail": "Est. +18 s advantage on a wet track vs staying on Softs",
    }))

    # Debrief
    from ui.components.debrief_view import DebriefVM
    shell.debrief_page.set_debrief(DebriefVM(
        what_happened="5-lap diagnosis run on Softs at Watkins Glen.",
        improved=("Mid-corner rotation at the Esses (+1.8 km/h)",),
        regressed=("Slight entry instability into Turn 1",),
        learned=("Rear ARB is the dominant lever for this car/track",),
        predictions_correct=("ARB softening improves rotation",),
        predictions_wrong=("Expected no entry change — there was one",),
        setup_outcome="Quali v3 kept — improved", strategy_outcome="No change",
        carry_forward=("Rear ARB working window 4–5 for this layout",),
        primary_action_label="Prepare qualifying", primary_action_key="to_qualifying"))

    # Native Settings (sample config)
    shell.settings_page.set_config({
        "connection": {"host": "127.0.0.1", "port": 33741},
        "voice": {"enabled": True, "rate": 175, "volume": 0.8,
                  "tyre_alerts": True, "lap_alerts": True, "fuel_alerts": True},
        "shift_beep": {"qual_rpm": 8200, "race_rpm": 7800},
    })

    shell.showMaximized()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
