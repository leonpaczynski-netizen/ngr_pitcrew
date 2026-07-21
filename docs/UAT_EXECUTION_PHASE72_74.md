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
| application_startup | 73-A | NOT_RUN | | |
| desktop_visual_layout | 73-A | NOT_RUN | | |
| windows_scaling | 73-A | NOT_RUN | | |
| live_dashboard_readability | 73-A/B | NOT_RUN | | |
| telemetry_connection | 73-B | NOT_RUN | | |
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

_(DEF-UAT-073-NNN / DEF-UAT-074-NNN added as physical stages run.)_

## 8. Remaining blockers / certification result
- No open blockers on the software candidate.
- **Overall: `NOT_TESTED` → readiness `READY_FOR_MANUAL_UAT`.** Physical microphone, keyboard/controller/
  wheel PTT, physical TTS, PSVR2 (audibility/timing/workload) and live GT7 (session binding / debrief /
  cumulative learning) remain untested. `OPERATIONALLY_CERTIFIED` is unreachable until every required area
  PASSes by user evidence on this exact commit **and** the user gives an explicit operational grant.
