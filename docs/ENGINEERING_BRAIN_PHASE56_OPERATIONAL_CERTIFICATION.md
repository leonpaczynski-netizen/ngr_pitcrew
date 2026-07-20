# Engineering Brain — Phase 56: End-to-End Operational Certification

Program 2, Phase 56. Read-only, deterministic, offline, no AI. An explicit, honest certification of the
complete NGR event journey. It grants nothing on its own — it reports what the recorded evidence supports.

## Certification domain — `strategy/event_programme_certification.py`

- `EvidenceType` (8) and `CertificationLevel` (10) with strict caps: automated evidence cannot award
  visual/live/operational; offscreen cannot award visual; replay cannot award live-GT7.
- `CERTIFICATION_AREAS` = the 23 areas of the NGR event journey (active-event selection … NGR immersion).
- `build_event_programme_certification` bounds the overall level by the WEAKEST area's effective level; a
  BLOCKER finding withholds any award for that area and prevents operational readiness;
  `OPERATIONALLY_READY(_WITH_LIMITATIONS)` requires live-GT7 evidence AND an explicit human grant AND no
  blocker. `CertificationArea` records evidence type + findings + last scenario (UAT instrumentation).
- `current_slice_certification()` = the HONEST self-certification of Phase 54–56: domain logic =
  automated, UI panels = offscreen, live/visual areas = NONE (not run headlessly). Overall = `NOT_TESTED`,
  bounded by the untested live areas — no live or operational certification is claimed.

## Developer/UAT UI (post `/ui-ux-pro-max`)

`ui/certification_vm.py` + `ui/certification_panel.py`: an overall-level banner + one card per area
(evidence type + effective-level tag + tone, findings) with contained horizontal overflow — not a wide
table. Unknown/not-tested render neutral, never as "ready". Placed on the developer surface (Development
History) via `update_certification`, keeping the driver Command Centre uncluttered.

## Evidence hierarchy (this slice)

| Means | Awardable level | This slice |
| --- | --- | --- |
| unit / property / runtime-DB | AUTOMATED_ONLY | domain areas |
| offscreen Qt | OFFSCREEN_VALIDATED | UI construction |
| replay / shadow | REPLAY_VALIDATED | bridge tested via snapshots |
| manual visual UAT | VISUAL_UAT_* | not run |
| live GT7 UAT | LIVE_GT7_* / operational | not run |

## Tests

`test_phase56_certification.py` (11), `test_phase56_certification_ui.py` (5).
