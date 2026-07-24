# NGR Pit Crew — UI Rebuild Manual UAT

**Status:** Prepared during Stage 1. Test cases are authored ahead of implementation; each is marked **NOT RUN** until executed against the built UI. **No case may be marked PASS unless actually performed.**
**Date created:** 2026-07-22
**Companions:** [`NGR_PIT_CREW_UI_ARCHITECTURE.md`](NGR_PIT_CREW_UI_ARCHITECTURE.md) · [`NGR_PIT_CREW_UI_REBUILD_PLAN.md`](NGR_PIT_CREW_UI_REBUILD_PLAN.md)

## Honesty rule (certification integrity)
- **Desktop workflow** cases: runnable on PC once built.
- **Physical / live GT7 / microphone / PTT / PSVR2 / voice** cases: **cannot be certified in the dev environment.** They remain **NOT TESTED** until the user runs them on real hardware with a live GT7 session. Do not mark visual-live/physical certification PASS from software alone. This mirrors the existing manual-UAT evidence discipline (`manual_uat_evidence`, `release_candidate_manifest`).

Result legend: **NOT RUN** · **PASS** · **FAIL** · **N/A** · **NOT TESTABLE (physical)**

---

## A. General Navigation
| # | Case | Steps | Expected | Result |
|---|---|---|---|---|
| A1 | New user can begin an event without instruction | Launch app cold | Home shows one clear objective + one primary action leading to Active Event/Briefing | NOT RUN |
| A2 | Returning user resumes an event | Launch with an active cycle | Home resumes at the current stage; progress rail shows position | NOT RUN |
| A3 | Next required action is identifiable | On any page | Exactly one dominant primary action; guidance states why | NOT RUN |
| A4 | Cannot accidentally skip a blocked critical stage | Click a blocked rail/nav node | Navigation is prevented and the blocking reason is shown | NOT RUN |
| A5 | Can move backward to review prior info | Navigate to a completed stage | Prior information is viewable read-only; no data loss | NOT RUN |
| A6 | Event header always correct | Across all pages | Series/event/car/track/session/stage/active-setup/connection stay accurate | NOT RUN |

## B. Garage / Setup
| # | Case | Expected | Result |
|---|---|---|---|
| B1 | Identify the active setup | Active-setup badge visible & correct on Garage | NOT RUN |
| B2 | Compare setups | Comparison shows changed value/direction/magnitude/reason/expected/outcome | NOT RUN |
| B3 | See lineage | Visual lineage tree with parent/child/previous + outcomes (worse prominent) | NOT RUN |
| B4 | See applied changes | Changed-fields list matches what was applied | NOT RUN |
| B5 | Save & apply safely | Apply clamps to ranges; no silent GT7 change; confirm-applied 3-state works | NOT RUN |
| B6 | Visible values refresh immediately | After apply/save, form + badge + lineage update at once (shown == applied) | NOT RUN |
| B7 | Discipline selector (no maze) | Base/Qual/Race via selector in one workspace; no side-by-side scroll panels | NOT RUN |
| B8 | RPM/gearbox discipline-specific | Quali vs race objectives shown; identical only with explanation | NOT RUN |

## C. Practice
| # | Case | Expected | Result |
|---|---|---|---|
| C1 | Follow a run plan | Run card shows objective/changes/expected/monitor/fuel/tyre/laps/push/invalidation | NOT RUN |
| C2 | Submit structured feedback | Dropdowns/segmented/scales/corner selector; free-text optional | NOT RUN |
| C3 | Identify whether experiment worked | Verdict succeeded/failed/inconclusive shown with evidence & contradictions | NOT RUN |
| C4 | Revert a failed change | Revert executes; failed direction flagged as blocked | NOT RUN |
| C5 | Begin next recommended run | Adaptive primary action leads to next run/build | NOT RUN |

## D. Qualifying
| # | Case | Expected | Result |
|---|---|---|---|
| D1 | Soft tyre requirement visible | Soft-tyre item shown (unless event rules forbid) | NOT RUN |
| D2 | Quali setup is discipline-specific | Differs from practice/race where evidence supports | NOT RUN |
| D3 | Out-lap & push-lap plan understood | Engineer explains out-lap/tyre-prep/push/traffic | NOT RUN |
| D4 | Remaining blockers visible | Checklist lists blockers with status | NOT RUN |

## E. Race Strategy
| # | Case | Expected | Result |
|---|---|---|---|
| E1 | Recommended + alternatives understandable | Plans as readable cards, not raw tables | NOT RUN |
| E2 | Evidence provenance visible | Each input tagged measured/derived/assumed/missing | NOT RUN |
| E3 | Missing evidence visible | Gaps shown, not hidden | NOT RUN |
| E4 | Time-certain optimisation understandable | Total time / expected laps explained | NOT RUN |
| E5 | Approve without altering setup | No setup-Apply control anywhere on strategy surface | NOT RUN |

## F. Live Pit Wall
| # | Case | Expected | Result |
|---|---|---|---|
| F1 | Readable at a glance | Few large KPIs; no dense-table scanning | NOT TESTABLE (physical) |
| F2 | Engineer instruction prominent | Current instruction dominant | NOT TESTABLE (physical) |
| F3 | Data age & confidence visible | Freshness (LIVE/STALE/NO SIGNAL) + confidence always shown | NOT TESTABLE (physical) |
| F4 | Voice & PTT understandable | Voice off-by-default; PTT gated; flows clear | NOT TESTABLE (physical) |
| F5 | Replanning stays advisory | No silent pit/fuel/strategy command; driver acts | NOT TESTABLE (physical) |
| F6 | Track position trust tiers distinct | Approved vs fallback vs low vs none visibly different | NOT TESTABLE (physical) |
| F7 | Handles disconnect/stale/session change | Clean degraded states, no crash | Partly testable (simulated) — NOT RUN |

## G. Debrief
| # | Case | Expected | Result |
|---|---|---|---|
| G1 | Understand what improved | Improvements listed | NOT RUN |
| G2 | Understand what regressed | Regressions prominent | NOT RUN |
| G3 | Understand carry-forward | Knowledge carried into next event shown | NOT RUN |
| G4 | Failed experiments remain visible | Not hidden | NOT RUN |
| G5 | Proven working windows visible | Shown per discipline | NOT RUN |

## H. Cross-cutting quality
| # | Case | Expected | Result |
|---|---|---|---|
| H1 | Empty / no-event / no-session states | Helpful message + action, never blank/crash | NOT RUN |
| H2 | Low-confidence states | Shown honestly, no fabricated certainty | NOT RUN |
| H3 | Keyboard navigation | Full keyboard operation; visible focus; logical order | NOT RUN |
| H4 | Scaling 1080p/1440p/4K | Readable; no clipping/tiny text | NOT RUN |
| H5 | Reduced motion | Pulses/streaming animation freeze; data still readable | NOT RUN |
| H6 | Official NGR logo | Loads from approved asset, unchanged | NOT RUN |
| H7 | No nested-scroll chaos | Single coherent scroll per page | NOT RUN |

---

## Physical / hardware certification (remains NOT TESTED here)
PSVR2 companion readability · live GT7 UDP telemetry end-to-end · microphone capture · push-to-talk recognition · TTS voice delivery · real pit-wall use during a race. These require the user's rig and a live session and must be signed off by the user, not by software.
