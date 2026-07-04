# OFR-2 — Separate Race vs Qualifying Telemetry Disciplines (Core Split)

> Author: OFR-2 feature-factory run · Date: 2026-07-04
> Branch: `ofr2-quali-race-disciplines` (from `master` @ `82ca7c3`)
>
> Companion docs: `docs/SMART_RACE_ENGINEER_ROADMAP.md` (OFR-2 spec §44–59,
> §2/§3 telemetry, Phase 2), `docs/OFR1_BETWEEN_RACE_LEARNING.md`.

---

## 1. What it does

Qualifying and race are different engineering problems. Since Group 26 the
setup prompts have branched their **objective text** on session type — but fed
identical telemetry regardless. OFR-2 makes the telemetry context
**discipline-aware**:

* **Qualifying** prompts get a peak-metrics block: best lap `[measured]`, peak
  lateral G `[estimated]` (with its derivation note), lock-up count, brake
  consistency (m), rotation breakdown (oversteer total + throttle-on vs entry)
  — plus a plain-English line that **steering corrections and rival
  traffic/dirty-air are not measured signals** (so the AI never assumes them).
* **Race** prompts get a consistency/efficiency block: fuel per lap
  `[measured]`, lock-up / wheelspin / snap-throttle rates per lap, lap-time
  consistency (std-dev across clean laps, "N/A (1 lap)"), per-corner tyre
  temperatures `[measured]` ("— not recorded" when absent).
* **Everything else keeps today's generic block byte-for-byte** — unknown,
  practice, and test purposes deliberately do not branch (a free-practice
  session is prep for either discipline).

Scope (explicit product decision — "Core split"): the setup-BUILD prompt and
the practice-analysis prompt. Strategy-prompt telemetry (roadmap Phase 2-B/2-C
fuel/degradation sequences) is deferred. Impossible metrics were scoped out
honestly: steering input (no signal in the GT7 packet), traffic/dirty-air (no
rival data), per-corner exit speeds (needs spatial clustering, Phase 7-A), and
the unvalidated tyre-radius wear proxy (standing rule).

## 2. How it was built (feature-factory)

Researcher → story (approved) → brief (approved with **two corrections I
flagged**: RF1 — practice discipline resolved SOLELY by the orchestrator from
the analysed session's stored `session_type`, never the live-mode combo, which
would be wrong for historical sessions; RF2 — the setup-build path wires REAL
recent laps rather than the brief's inert empty list, which would have left the
story's headline surface dead) → backend-builder → UI pass → 112-test
acceptance verification (all 11 ACs + 6 edge classes PASS) → validator → fix
round → re-verified. Checkpoints committed before each verifier stage.

## 3. The pieces

* **`strategy/telemetry_disciplines.py` (NEW, pure)** —
  `build_discipline_telemetry_block(laps, purpose, *, ms_to_str=None)`:
  resolves the discipline via the canonical `normalise_purpose()` (strings like
  "Race Setup", enums, None); returns the **`None` sentinel** for anything that
  isn't exactly QUALIFYING or RACE — callers keep the generic block untouched;
  zero clean laps → an honest "No clean laps available." line; labels follow
  the `[measured]/[calculated]/[estimated]` convention; no tyre-radius anywhere.
* **`strategy/ai_planner.py`** — `_build_practice_prompt(session_purpose=None)`
  uses the discipline block when non-None, ELSE the exact pre-existing generic
  call; `_build_setup_from_scratch_prompt(per_lap_telemetry=None)` injects a
  `{_telem_section}` that renders `""` for unknown/no-laps (prompt
  byte-identical to pre-OFR-2); `build_car_setup` / `analyse_practice_session`
  thread the new optional params. `_build_race_prompt` /
  `_build_degradation_prompt` untouched.
* **`strategy/practice_orchestrator.py`** — resolves `session_purpose` itself
  via the new `db.get_session_type(session_id)` (single source; the UI passes
  nothing — RF1).
* **`data/session_db.py`** — `get_session_laps` gains the two missing columns
  (`snap_throttle_count`, `brake_consistency_m`) and `latest: bool = False`
  (True = the LAST `limit` laps in ascending order — the representative recent
  stint); new `get_session_type()`.
* **`data/ai_context_snapshot.py`** — `SetupAISnapshot` +
  `PracticeAnalysisSnapshot` gain `discipline: str = "unknown"` (defensive;
  excluded from snapshot-id hashes; `StrategyAISnapshot` untouched).
* **`ui/setup_builder_ui.py`** — `_resolve_recent_laps(car_id, track)` fetches
  the most recent car+track session's latest 5 laps on the UI thread
  (defensive → `[]` keeps the prompt unchanged); wired into `build_car_setup`;
  the setup combo's session type threads into the setup snapshot.

## 4. Validator findings → fixes (all resolved, re-verified)

| Finding | Resolution |
|---|---|
| C1: PRACTICE/TEST purposes fell through to the RACE block (free-practice sessions are stored as "practice" — AC5 violation) | Only QUALIFYING/RACE branch; every other purpose returns the sentinel; real-DB practice-session byte-identity test added |
| I1: `limit=5` returned the EARLIEST 5 laps (full-fuel opening laps) | `latest=True` semantics added (default byte-identical); RF2 wiring uses it — the AI sees the recent stint |
| I2/M3: two coverage gaps | UNKNOWN+real-laps identity test; capitalised-"Practice" flow test |
| M1/M2: comment + logging polish | Comment corrected; `[Tag]` print kept (the file's own convention) |

## 5. Honesty properties (tested)

Unknown/practice/test → generic block **byte-for-byte**; the declared setup
purpose wins over whatever session the laps came from; zero clean laps and
single-lap std-dev degrade honestly; absent tyre temps say "— not recorded";
the quali block explicitly names what is NOT measured; estimated signals carry
their derivation.

## 6. Tests

269 new tests across six files: `test_telemetry_disciplines.py` (48),
`test_ofr2_prompts.py` (28), `test_ofr2_snapshot.py` (26),
`test_ofr2_session_db.py` (30), `test_ofr2_setup_wiring.py` (23),
`test_ofr2_acceptance.py` (114 — one end-to-end test per AC + edge classes).
Existing prompt byte-identity suite and the frozen allowlist pass unchanged.
**Full suite: 5217 pass / 6 skip / 0 fail** (pre-feature baseline 4948).

## 7. Deferred / future

Strategy-prompt telemetry (Phase 2-B/2-C); per-corner exit speeds (Phase 7-A);
steering-input and rival-data metrics (no signals exist); tyre-radius
validation (Phase 4); wiring richer lap windows into the setup path (currently
latest 5 clean-ish laps of the most recent session).

## 8. Next recommendation

Drive quali and race sessions and compare the setup advice — the disciplines
should now read like different engineers. Build candidates: a History-tab
surface for OFR-1's scored recommendations, Phase 2-B/2-C strategy telemetry,
or the plan-state schema migration.
