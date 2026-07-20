# Engineering Brain — Phase 53: Resume, Recovery & Operational Certification

Program 2, Phase 53. Read-only, deterministic, offline, no AI. Makes the preparation cycle resilient for
real multi-week use and defines an honest certification of the primary experience.

## Restart, interruption, telemetry dropout — `strategy/programme_resume.py`

`build_resume_state` restores the selected event / phase / completed / next / interrupted / pending-binding
/ pending-debrief / locks / strategy-final state after restart; **an interrupted activity is never restored
COMPLETED** (a passed COMPLETED is downgraded to INTERRUPTED — a restart cannot fabricate a completion);
voice is restored disabled by default. `classify_interrupted_activity` → resumable / session_recoverable /
binding_required / insufficient_evidence / abandoned / invalid; **never auto-completes** (the user decides).
`resolve_telemetry_dropout`: a gap suppresses advisories, preserves evidence, creates no duplicate session,
does not complete the activity, and shows an honest recovery state.

## Setup-lock reopening — `strategy/setup_lock_reopen.py` (Audit C remediation)

`assess_lock_reopen` classifies the eight triggers. A single noisy lap (`NOISE_ONLY`) or an isolated
subjective complaint (`SUBJECTIVE_ONLY`) is **not** eligible; a corroborated critical regression, event-
context revision, fingerprint mismatch, rules change, GT7 physics-version change, independently corroborated
evidence, or an explicit driver override (with visible consequence) **is** eligible. Noise never blocks a
genuine trigger. It reopens nothing itself — reopening is an explicit user action.

## Event revision impact — `strategy/event_revision_impact.py`

`assess_event_revision(old, new)` compares two event contexts; an evidence-sensitive field change
(car/track/layout/bop/tuning/power/weight/tyres/tyre+fuel multiplier) makes prior exact evidence
incompatible and requires a lock reopen; strategy-sensitive changes require recalculation. It rewrites
nothing — completed session provenance is untouched (inputs are not mutated).

## Operational certification — `strategy/operational_certification.py`

`CertificationState` (8): NOT_TESTED → AUTOMATED_ONLY → OFFSCREEN_VALIDATED → VISUAL_UAT_PARTIAL →
LIVE_GT7_PARTIAL → LIVE_GT7_VALIDATED → OPERATIONALLY_READY_WITH_LIMITATIONS → OPERATIONALLY_READY. The
overall state is bounded by the WEAKEST area's proof level; **live/operational certification requires
live-GT7 evidence and cannot be granted from automated/offscreen tests alone** (an operationally-ready
grant with only automated evidence is ignored). See `UAT_ENGINEERING_BRAIN_PHASE51_53.md` for this slice's
certification result (AUTOMATED_ONLY — live GT7 not run headlessly).

## Tests

`test_phase53_resume.py` (11), `test_phase53_revision_reopen_cert.py` (17).
