# Setup Brain — UAT-2 Root-Cause Report (Group 63)

**Scenario:** `R NGR Porsche Cup Rd7 15 [Race Setup]`, Porsche 911 RSR (991) '17.
Driver reported entry understeer, mid-corner push, rear loose on throttle, rear
steps out under braking, high fuel use, "LSD not set how I like … floaty and not
hooking up on the apex", sixth gear not fully used on the main straight. The app's
only recommendation was `Final Drive 4.25 -> 4.20` (which **lengthens** gearing —
the wrong direction for an unused sixth), while bottoming was marked dominant/
required with no impact evidence and no bottoming change, and the three LSD fields
and camber were never meaningfully evaluated.

This report is grounded in a four-thread code trace (gearbox, bottoming, LSD,
recommendation-assembly). File:line references are to the tip of `master`
(`b951e06`) at the start of Group 63. **No prompt claim was taken on faith** — each
was verified against the current code; verdicts (REAL / PARTIAL / NOT-PRESENT) are
recorded per defect.

---

## Cross-cutting theme

Every failure is the **same class of bug at a different stage**: *evidence is lost,
inverted, or treated as valid when it is unknown, and nothing enforces coherence
between the diagnosis and the change that is authored.* The prior 16-phase
remediation added rich **advisory** surfaces (history comparison, race-time note,
candidate table, dispositions) but they sit **beside** the deterministic
diagnosis→rule-engine core; they do not repair the evidence pipeline that authors
the change.

---

## RC-A — Driver feedback is lost or mis-routed at parse time
`strategy/setup_diagnosis.py:136-189` (`_FEEL_VOCABULARY`, `_parse_driver_feel`).

1. **"LSD not set how I like / not hooking up on the apex / floaty" has no LSD flag.**
   "floaty" → `floaty_front` (turn-in only, line 141-145), which routes exclusively
   to front-aero/ARB. "not hooking up at the apex" and "LSD … not how I like" match
   **no** vocabulary entry. The explicit differential complaint is silently dropped
   or misfiled as a front-aero problem. **VERDICT: REAL.**
2. **"Rear steps out under braking" is mis-classified as a throttle/exit symptom.**
   `rear_loose_on_exit` contains the substring `"rear steps"` (line 164), so the
   phrase sets `rear_loose_on_exit=True`; `braking_instability`'s vocabulary
   (`locks / lock-up / dances / nervous / tail wags`, line 176-179) does not match
   "steps out". The braking-oversteer complaint is absorbed into an exit flag whose
   addressing set is `{lsd_accel, aero_rear, arb_rear}` — never `lsd_decel`.
   **VERDICT: REAL.**
3. **"Sixth gear not fully used" has no flag and cannot veto lengthening.** No
   vocabulary phrase for unused-top-gear / gear-too-long; only `gearbox_good`
   forces preserve (line 1580). The driver's own contradicting report cannot block
   the lengthening recommendation. **VERDICT: REAL (missing guard).**

## RC-B — Gearbox mis-diagnosed as `gear_too_short`
`strategy/setup_diagnosis.py:675-753` (`_classify_gearing`); rule B5
`strategy/setup_knowledge_base.py:745-785`.

1. **`top_gear` is derived from limiter-hit keys** — `top_gear = max(int(g) for g in
   rlbg)` (line 704-707) where `rlbg = rev_limiter_by_gear` contains only gears that
   *hit* the limiter. A too-long, never-limited sixth is **absent**, so `top_gear`
   collapses to the highest *intermediate* gear that did hit; `top_gear_limiter_hits
   > 0` then fires `gear_too_short`. The classifier structurally cannot distinguish
   "limiter in intermediate gears / 6th too long" from "limiter in true top gear" —
   exactly the reported condition. **VERDICT: REAL (primary defect).**
2. **`transmission_max_speed_kmh` = 0 enables a `gear_too_short` default.** 0 →
   `top_speed_target_kmh = 0.0` (line 1525-1529) → `speed_ratio = None` (718-724) →
   the else branch returns `gear_too_short` on any top-gear limiter hit (745-751),
   with **zero top-speed corroboration**. **VERDICT: PARTIAL** (0 is not accepted as
   a *speed*, but it silently permits the wrong label instead of blocking).
3. **No location/straight gating.** Limiter contacts are counted anywhere, any gear
   (`recorder.py:222-228`); `_classify_gearing` applies no positional filter, yet B5's
   symptom asserts "Rev limiter hit **on straights**" with no such evidence.
   **VERDICT: REAL (missing gate).**
4. The **direction helpers are correct**: `final_drive_down = -0.05` = longer gearing;
   `final_drive_up = +0.05` = shorter (`setup_knowledge_base.py:312-332`). B5b
   (gear_too_long → up) exists. So the −0.05 sign is only wrong *because the category
   is wrong*. `gear_too_short_spin` never authors `final_drive` (NOT-PRESENT). Rev-
   limiter is a genuine packet flag `0x0020`, not inferred (NOT-PRESENT).

## RC-C — Bottoming dominance is frequency-based, with no impact axis
`strategy/setup_diagnosis.py`.

1. **Severity is pure events/lap.** `avg_bottoming` (line 1393) → `_bottoming_band`
   (214-229): `>2.0 ⇒ "required"`. Nothing measures speed loss, lap-time delta or
   stability. `_classify_bottoming_confidence` signals are data-quantity/history, not
   impact (868-907). **VERDICT: REAL.**
2. **Dominance ordering privileges count-bottoming over handling complaints.**
   `_derive_dominant_problem` (281-379) appends bottoming at position 2 and returns
   `issues[0]`; `mid_corner_understeer` is **absent** from the function and can never
   be dominant; `entry_understeer`/`rear_loose_on_exit` qualify only with near-min
   aero. **VERDICT: REAL.**
3. **The Phase-3 demotion gate is disarmed.** `_bottoming_evidence_insufficient`
   requires `confidence == "low"` (1671-1673), but any session with ≥4 laps is graded
   ≥ "medium" (868-869 → 911-915), so the demotion never fires for a realistic multi-
   lap run; bottoming stays dominant and the gate only relabels to
   `partial_recommendation` (still an APPROVED status). **VERDICT: PARTIAL (real gap).**
4. **The contradiction is reachable**: bottoming dominant+required, no bottoming
   change, and an unrelated gearbox change still surfaced as applyable
   (`driving_advisor.py:642-674`). **VERDICT: REAL.**

## RC-D — LSD triplet is dead or blocked
`strategy/setup_knowledge_base.py`, `strategy/setup_rule_engine.py`,
`strategy/setup_diagnosis.py`.

1. **`lsd_initial` (Initial Torque) is entirely unauthored** — no `SetupRule`, no
   delta resolver (`_DELTA_RESOLVERS` has only accel/decel, kb:357-360), no diagnosis
   flag, no feel vocabulary. It appears only in passive fuel-upgrade / addressing /
   history-compare lists. **VERDICT: REAL (strongest).**
2. **All `lsd_accel` increase rules are contraindicated by `rear_loose_on_exit`**
   (B6 kb:831-838, C5 kb:984-990) → blocked in this scenario; the decrease rule needs
   `snap_oversteer_exit`. Net: no `lsd_accel` change, only a text disposition.
   **VERDICT: REAL (narrow).**
3. **`lsd_decel` has no path on an ABS car** for braking-oversteer: only
   `C1_entry_lsd_decel` (needs `entry_understeer`) and `NoABS1` (needs `no_abs`).
   Combined with RC-A.2, "rear steps out under braking" never reaches `lsd_decel`.
   **VERDICT: REAL.**
4. **Unknown wheelspin subtype prescribes nothing executable** — `inside_wheel_spin`
   is never emitted; the "run a test" line is prose; `build_test_sequence` only
   orders *already-proposed* changes. **VERDICT: NOT-PRESENT as an executable test.**

## RC-E — Historical evidence is advisory-only
`strategy/setup_history_intelligence.py`, `strategy/driving_advisor.py:2124-2141`.

`compare_to_history` flags a field only when a **recommended** value already exists
and deviates (kb:239-243); the rec is built from `_plan.proposed`, which for LSD/
camber is empty here, so nothing is flagged and unflagged proven values (Race
22/8/33, Quali 20/9/31, camber 2.5/2.1) are **discarded**. History never generates
or ranks a candidate; the only value-writing path is baseline camber/toe seeding
(`build_baseline_seed_overrides`, camber/toe only, baseline path only).
**VERDICT: REAL — history is reactive to a recommendation that never comes.**

## RC-F — No cross-candidate ranking; coherence gate scoped to bottoming; render gaps
`strategy/setup_rule_engine.py`, `strategy/driving_advisor.py`, `ui/setup_builder_ui.py`.

1. **No global ranking / relevance / cap.** `proposed = list(proposed_by_field.
   values())` (rule_engine:583); confidence tweaks affect only *same-field* conflicts.
   A low-risk generic `final_drive` survives as the sole recommendation because no
   term rewards relevance-to-dominant-issue or penalises weak evidence.
   **VERDICT: REAL.**
2. **The coherence gate arms only for bottoming.** `dominant_required =
   (dominant_problem_key == "bottoming" and b_band == "required")`
   (setup_diagnosis:1683). For any other dominant problem the gate never runs and a
   lone final_drive returns plain `"approved"` with Apply shown. A bare `final_drive`
   is also inside `DOMINANT_ADDRESSING_FIELDS["wheelspin"]`, so even if armed it would
   falsely "address" wheelspin. **VERDICT: REAL.**
3. **Render gaps.** Rule-engine rejected candidates (those with a `rule_id` — deferred
   LSD/camber) are filtered out of the rejected section (ui:2069); there are no
   dedicated proven-Race / proven-Quali columns; a bare `"approved"` shows no banner
   at all. Base/Race/Quali "look identical" because the comparison is projected onto
   the single approved field (`final_drive`), which no session bias touches.
   **VERDICT: PARTIAL.**

---

## Repair map (smallest coherent slice)

| RC | Repair | Primary files |
|----|--------|---------------|
| A | New feel flags: `lsd_feel_wrong`, `rear_loose_under_braking`, `gearing_too_long`; fix "rear steps"/"under braking" routing | `setup_diagnosis.py` |
| B | Authoritative `gearing_state` (TOO_SHORT/APPROPRIATE/TOO_LONG/UNKNOWN/CONFLICTING); fix `top_gear` (use gear count); None speed_ratio→UNKNOWN; driver-unused-sixth veto→CONFLICTING+block B5; location gate; `final_drive` directional-invariant helper | `setup_diagnosis.py`, new `strategy/gearbox_evidence.py`, `setup_knowledge_base.py` (B5 contraindication) |
| C | Impact-aware bottoming severity + dominance so count-only/no-impact bottoming cannot outrank confirmed handling feedback; let handling complaints participate | `setup_diagnosis.py` |
| D | `lsd_initial` resolver+rule driven by `lsd_feel_wrong`/floaty-apex + history prior (bounded, or targeted test); route `rear_loose_under_braking`→`lsd_decel`; executable controlled-test stage on unknown subtype | `setup_knowledge_base.py`, `setup_rule_engine.py`, `setup_test_plan.py` |
| E | Historical prior surfaces proven Race/Quali unconditionally and drives a bounded candidate / targeted test toward proven LSD+camber (not just a note) | `setup_history_intelligence.py`, `driving_advisor.py` |
| F | Generalise `dominant_required` beyond bottoming; bare `final_drive` must not "address" a handling dominant; targeted-test status not applyable; render proven columns + reject reasons | `setup_diagnosis.py`, `driving_advisor.py`, `ui/setup_builder_ui.py` |

**Invariants preserved throughout:** deterministic rule-first authoring; AI audit-only
(never authors values, never validates invalid evidence, never bypasses the Apply
gate); no auto-Apply; no fabricated telemetry/fuel/history; honest UNKNOWN; disabled
AI-build stays disabled; runtime data files untouched (tests use fixtures).
