# NGR Pit Crew — Operational UAT Execution Report (Phases 72–74)

Single authoritative record of the operational UAT of the Phase 69–71 build. **This is not a certification
claim.** Physical / PSVR2 / live-GT7 areas are certified ONLY by the user's real-world evidence recorded in
the Manual UAT panel. Claude records the software gates and guides the manual stages one step at a time; it
never infers a PASS.

## 1. Candidate identity (frozen)

| Field | Value |
|-------|-------|
| Branch | `eng-brain-phase72-74-operational-uat` |
| **Candidate commit** | `45928b4d7201087a4dd3b8d016f8f019869c98ae` |
| Parent / UAT base | `ecf922c` (PR #77 merge — Phases 69–71 into `master`) |
| DB version | 28 |
| Rule-engine version | 46.0 |
| Certification taxonomy | `event_programme_certification_v1` (31 live-VR areas) |
| Evidence-store version | `manual_uat_evidence_v1` |
| Listener status | single UDPListener (`telemetry/listener.py`) |
| Runtime-file integrity | unchanged (`.claude/settings.local.json` 40b47f9e · `data/setup_history.json` 004177da · `active_setup_state.json` cfc5a4c3) |
| Full regression | **10,359 passed / 27 skipped / 0 failed** (see §5) |
| Bench UAT | **67 / 67 passed, 0 failed, 0 blocked, 0 safety failures** |
| Readiness | `READY_FOR_MANUAL_UAT` |
| Overall certification | `NOT_TESTED` |

> Candidate identity is the **commit**, never the branch name alone. Any code change after this point creates
> a NEW candidate identity and voids inherited operational certification (DEF-UAT-072-001).

## 2. Evidence-integrity result (Phase 72)

**DEF-UAT-072-001 — Manual UAT evidence was not candidate-scoped (release-blocking) — FIXED.** Prior to the
fix, readiness counted manual observations from *any* commit, so an old-candidate PASS could certify a
different candidate. Now:

- Every observation records its `candidate_commit`; the UI stamps the exact running commit (`data/repo_identity.py`).
- Readiness and the manifest are scoped to the active candidate commit — evidence from another commit is
  viewable history but **does not count**.
- A newer observation supersedes only within the same area *and* candidate scope.
- A code change (new commit) cannot inherit operational certification.
- A failed area stays failed until an explicit same-candidate passing retest.
- No optimistic fallback (a blank/unknown candidate counts no commit-stamped evidence).

Covered by `tests/test_phase72_candidate_integrity.py` (12 tests, all pass).

## 3. Certification taxonomy — all 31 areas (exact canonical names, no wildcards)

| # | Area | Class | Current evidence |
|---|------|-------|------------------|
| 1 | `real_tracker_mapping` | Automated software | automated |
| 2 | `race_clock` | Automated software | automated |
| 3 | `fuel_burn` | Automated software | automated |
| 4 | `pace_divergence` | Automated software | automated |
| 5 | `tyre_proxy` | Automated software | automated |
| 6 | `pit_detection` | Automated software | automated |
| 7 | `lap_count_strategy` | Automated software | automated |
| 8 | `time_certain_strategy` | Automated software | automated |
| 9 | `revised_candidate_ranking` | Automated software | automated |
| 10 | `live_tab_strategy_card` | Manual desktop (offscreen-built) | offscreen |
| 11 | `physical_tts` | Physical audio | none |
| 12 | `keyboard_ptt` | Physical input | none |
| 13 | `controller_ptt` | Physical input | none |
| 14 | `wheel_ptt` | Physical input | none |
| 15 | `microphone_recognition` | Physical input (microphone) | none |
| 16 | `command_grammar` | Automated software | automated |
| 17 | `read_back` | Automated software | automated |
| 18 | `driver_report_confirmation` | Automated software | automated |
| 19 | `workload_aware_delivery` | Automated software | automated |
| 20 | `tts_ptt_coordination` | Automated software | automated |
| 21 | `telemetry_loss` | Automated software | automated |
| 22 | `device_failure` | Physical input | none |
| 23 | `psvr2_practice` | PSVR2 | none |
| 24 | `psvr2_qualifying` | PSVR2 | none |
| 25 | `psvr2_race` | PSVR2 | none |
| 26 | `revised_plan_acknowledgement` | Automated software | automated |
| 27 | `repeated_replanning` | Automated software | automated |
| 28 | `visual_fallback` | Manual desktop (offscreen-built) | offscreen |
| 29 | `session_binding` | Live GT7 | none |
| 30 | `debrief` | End-to-end operational | none |
| 31 | `cumulative_learning` | End-to-end operational | none |

**Exact areas that must PASS by real evidence for `OPERATIONALLY_CERTIFIED`** (8 manual areas, mapped to the
cert taxonomy): `physical_tts`, `physical_microphone`→`microphone_recognition`, `keyboard_ptt`,
`wheel_joystick_ptt`→`wheel_ptt`, `psvr2_audibility`/`psvr2_timing`/`psvr2_driver_workload`→`psvr2_race`,
`live_gt7_operational_suitability`→`cumulative_learning` — plus the explicit user operational grant. Live
`session_binding` and `debrief` are additionally validated in Stage 7 rehearsal.

## 4. Test environment / hardware / GT7 settings (to be recorded during Stages)
_To be filled at test time:_ OS + scaling, PC audio device, microphone, wheel/controller model, PSVR2, GT7
version, event (car / track / layout), fuel & tyre multipliers, lap count.

## 5. Software gates (this candidate)
- **Full regression:** 10,359 passed / 27 skipped / 0 failed (authoritative run for `45928b4`).
- **Bench UAT:** 67 / 67 passed, 0 failed, 0 blocked, 0 safety failures, 0 certification-integrity failures.
- **Runtime files:** unchanged before/after.

## 6. Manual UAT results by area (PASS / FAIL / BLOCKED / NOT_RUN)
Recorded by the user in the Manual UAT panel against candidate `45928b4`. **All physical / live areas are
currently `NOT_RUN`.** This table is updated as evidence is entered; Claude never marks a physical area PASS.

| Area | Stage | Status | Defect | Notes |
|------|-------|--------|--------|-------|
| application_startup | 73-A | **PASS** | | Window opened; welcome greeting spoken (intended — OBS-073-A); no console exceptions. |
| desktop_visual_layout | 73-A | **FAIL** | DEF-UAT-073-001, -002, -003 | Tabs open, but layout compressed/squashed across tabs; Track Modelling slow to open; Development History overloaded/unclear. |
| windows_scaling | 73-A | NOT_RUN | | (deferred — pending layout defects) |
| live_dashboard_readability | 73-A/B | RETEST_REQUIRED | DEF-UAT-073-001 | Affected by the compressed-layout defect. |
| home_command_centre_state | 73-A | **FAIL** | DEF-UAT-073-004 | "No active event / Create event" primary action while a prior event's race setup + 5/12 journey + track intelligence remain displayed. |
| telemetry_connection | 73-B | PRELIM PASS | | Bottom-left + Telemetry tab showed "not connected" until GT7 was up; once GT7 connected, telemetry connects and updates. Full Stage-B checks (packet freshness / session+event+car+track identity / fuel / race-clock) not yet formally verified. |
| telemetry_reconnect | 73-B | NOT_RUN | | |
| session_transition | 73-B | NOT_RUN | | |
| fuel_mapping | 73-B/C | NOT_RUN | | |
| pace_mapping | 73-C | NOT_RUN | | |
| race_clock | 73-B/E | NOT_RUN | | |
| lap_rollover | 73-C | NOT_RUN | | |
| pit_entry | 73-C | NOT_RUN | | |
| pit_stop | 73-C | NOT_RUN | | |
| pit_exit | 73-C | NOT_RUN | | |
| tyre_age_proxy | 73-C | NOT_RUN | | |
| lap_count_adaptive_strategy | 73-D | NOT_RUN | | |
| time_certain_adaptive_strategy | 73-E | NOT_RUN | | |
| strategy_explanation_quality | 73-D/E | NOT_RUN | | |
| audio_priority | 73-C / 74 | NOT_RUN | | |
| audio_cooldown | 73-C / 74 | NOT_RUN | | |
| physical_tts | 74.1 | NOT_RUN | | |
| keyboard_ptt | 74.2 | NOT_RUN | | |
| wheel_joystick_ptt | 74.3 | NOT_RUN | | |
| physical_microphone | 74.4 | NOT_RUN | | |
| recognition_confidence | 74.4 | NOT_RUN | | |
| ambiguous_speech | 74.4 | NOT_RUN | | |
| confirmation_flow | 74.4 | NOT_RUN | | |
| psvr2_audibility | 74.5 | NOT_RUN | | |
| psvr2_timing | 74.5 | NOT_RUN | | |
| psvr2_driver_workload | 74.5 | NOT_RUN | | |
| live_gt7_operational_suitability | 74.6 | NOT_RUN | | |

## 7. Defects
| ID | Severity | Area(s) | Status |
|----|----------|---------|--------|
| DEF-UAT-072-001 | Blocker (certification integrity) | manual-evidence readiness | **FIXED** in `45928b4` |
| DEF-UAT-073-001 | Medium (usability) | desktop_visual_layout, live_dashboard_readability | OPEN — compressed/squashed layout across tabs; poor use of screen real-estate; legacy UI not removed after enhancements |
| DEF-UAT-073-002 | Low–Medium (performance) | desktop_visual_layout (Track Modelling) | **FIXED** in `ae795fc` — the synchronous track-seed parse on first open now runs off the Qt thread (worker + stale guard); the tab opens instantly. **User retest.** |
| DEF-UAT-073-003 | Medium (usability / IA) | desktop_visual_layout (Development History) | **FIXED** in `6b84e9b` — split into 6 purpose-specific sub-tabs (Readiness & Assurance · Race Engineer & Runtime · Certification & UAT · Experiments & Development · Season & Knowledge · Overview & Records); Command Centre departments route to distinct sub-tabs. **User retest.** |
| DEF-UAT-073-004 | High (state consistency) | home_command_centre, next_action_accuracy, active-cycle resolution | **FIXED** in `e24c7c6` (Slice 1) — removed the legacy Home dashboard (stepper + duplicate cards + banner) that read the last-loaded config; the Event Command Centre is now the single Home surface. **User visual retest required.** |
| DEF-UAT-073-005 | High (broken primary workflow) | home_command_centre, activity_start | **FIXED** in `e24c7c6` (Slice 1) — the primary action is now a real button → Event Planner (was an inert status-badge QLabel; target `no_event`→`event_planner`). **User retest required.** |
| DEF-UAT-073-006 | Medium (dead control) | home_command_centre, cumulative_learning | **FIXED** in `e24c7c6` (Slice 1) — Cumulative Learning now has a real "View Progress" button → Development History (was an inert badge). **User retest required.** |

| DEF-UAT-073-007 | Medium (usability) | desktop_visual_layout (Setup Builder) | OPEN — recommendation display tall + small text + lots of scrolling; the side-by-side "Both" editor (Race + Qualifying columns) is space-inefficient so you **cannot see a whole car setup at a glance to transcribe into GT7**. Consider single-setup focus / wider fields / a compact "transcribe" view. |
| DEF-UAT-073-008 | High (functional) | Setup Builder recommendation→car-settings mapping | **NEEDS USER REPRO** — root-cause investigated: the top-level `self._setup_*` widgets correctly alias the Race form and `_HIGHLIGHT_PARAM_MAP` is correct, so the visible symptom depends on the exact recommendation payload. Two candidate causes: (a) `_apply_build_setup_result` highlights a FIXED 25-key list regardless of which fields the rec actually changed (over-highlights on a targeted fix); (b) a from-scratch baseline may leave some widgets unset if the rec omits them. To fix safely I need: which fields didn't load, whether it was a from-scratch baseline or a targeted fix, and whether the Race or Qualifying column was affected. |
| DEF-UAT-073-009 | High (functional / dead controls) | Setup Builder Apply-in-Game / value entry / Start Validation | OPEN — "Apply in Game" appears to do nothing; entering values does nothing; "Start Validation" does nothing. **Remediation must preserve the FROZEN setup Apply authority** — repair only the control wiring/state, never the Apply-gate predicate |
| DEF-UAT-073-010 | Medium (functional + usability) | Practice Review setup selector | **FIXED** in `28101f3` — the running-setup combos now filter to the ACTIVE car's setups (graceful fallback to all when the car is unknown / setups untagged). **User retest.** |
| DEF-UAT-073-011 | **High (broken event workflow)** | home_command_centre, active-cycle resolution, event_planner | **FIXED** in `<new>` — root cause confirmed (Event Planner set only `active_event_id`; nothing set the Command Centre's `active_cycle_id` / preparation cycle). `_ensure_active_preparation_cycle` now creates a deterministic idempotent cycle per event (populated from the event) and sets it as the active cycle on "Set as Active"; the Phase-51 resolver honours the explicit selection → Command Centre resolves ONE_ACTIVE_EVENT. 4 tests; a completed/abandoned cycle is never silently reopened. **User retest required.** |
| DEF-UAT-073-012 | Medium (UX clarity) | home_command_centre (Event Briefing dept) | PARTIAL — clarified by the DEF-014/015 IA pass; full clarity comes with the DEF-003 Development-History split |
| DEF-UAT-073-014 | Medium (workflow order) | home_command_centre departments | **FIXED** in `910be25` — Setup Development ordered before Practice Programme |
| DEF-UAT-073-015 | Medium (navigation / IA) | home_command_centre departments | PARTIAL (`910be25`) — Driver Coaching now routes to Practice Review (distinct); Event Briefing + Debrief still land on Development History pending the DEF-003 split |
| DEF-UAT-073-016 | Low–Medium (IA) | home_command_centre (Telemetry dept) | **FIXED** in `910be25` — Telemetry removed as an event department |
| ENH-UAT-073-001 | Enhancement | Setup Builder shift RPM | **DONE** in `5bbb708` — principled shift-RPM recommendation from GT7's rpm-alert band / peak-power / rev-limit; never fabricated (unknown → "drive it first"). |
| DEF-UAT-073-013 | High (functional persistence) | garage_readiness | OPEN — Garage does not persist the car selected for the event |
| DEF-UAT-073-014 | Medium (workflow order) | home_command_centre journey / departments | OPEN — "Practice" is ordered before "Setup"; setup should come first (build a setup, then practice it) |
| DEF-UAT-073-015 | Medium (navigation / IA) | home_command_centre departments | OPEN — multiple departments (Event Briefing, Driver Coaching, Debrief) all navigate to the SAME Development History catch-all page — no differentiation of purpose (ties to DEF-003) |
| DEF-UAT-073-016 | Low–Medium (IA) | home_command_centre (Telemetry dept) | OPEN — Telemetry does not belong as a Command Centre "department"; it just shows what is being captured |
| DEF-UAT-073-017 | Medium (layout + redundancy) | live_dashboard_readability (Live Race Engineer tab) | OPEN — Live tab is squished / mis-sized (some small things rendered big, wide elements cramped, bottom content clipped); mode differentiation unclear (Live vs Qualifying feel the same). Live-tab instance of DEF-001. |

### Remediation log
- **Slice 1 (branch `uat-defect-073-navigation-and-home-state`, candidate `e24c7c6` from base `ecf922c`):**
  fixed DEF-073-004/005/006 + delivered the "back to Command Centre" navigation (persistent tab-bar corner
  button, returns Home from any tab). Bench 67/67; full regression per MASTER_TESTING_REGISTER. **This mints a
  NEW candidate — per DEF-072-001 candidate-scoping, the manual UAT areas reset to NOT_RUN/RETEST_REQUIRED for
  `e24c7c6`; the user must re-verify the Home/nav behaviour in-app.** Remaining Slice-2+ backlog:
  DEF-073-001 (layout), -003 (Dev-History sub-tabs), -007 (Setup Builder readability), -008/-009 (Setup Builder
  functional), -010 (Practice Review selector), -002 (Track Modelling perf).

### Observations (not defects)
- **OBS-073-A — startup voice greeting: intended.** User confirms the spoken welcome at launch is wanted. No action.

### Enhancement requests (NOT defects; out of the UAT/remediation scope — logged for a future dev programme)
- **ENH-073-001 — torque-curve shift-beep recommendation.** Setup Builder should recommend the shift-beep RPM
  for Race and Qualifying from the specific car's torque curve + race requirements. This is NEW setup/engineering
  logic, which the current operational-UAT programme explicitly excludes — do not implement during UI
  remediation; requires a separate, scoped development effort.

_(DEF-UAT-074-NNN added as physical stages run.)_

## 8. Remaining blockers / certification result
- No open blockers on the software candidate.
- **Overall: `NOT_TESTED` → readiness `READY_FOR_MANUAL_UAT`.** Physical microphone, keyboard/controller/
  wheel PTT, physical TTS, PSVR2 (audibility/timing/workload) and live GT7 (session binding / debrief /
  cumulative learning) remain untested. `OPERATIONALLY_CERTIFIED` is unreachable until every required area
  PASSes by user evidence on this exact commit **and** the user gives an explicit operational grant.
