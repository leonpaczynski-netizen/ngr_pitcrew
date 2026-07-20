# Engineering Brain — Phase 62: Visual, Live GT7 and Voice Certification

Program 2, Phase 62. Read-only, deterministic, offline, no AI. Certifies the complete production workflow
and records the real-tracker limitations honestly. Grants nothing on its own; never alters engineering
state.

## Production per-area certification — `strategy/event_programme_certification.py` (extended)

`PRODUCTION_CERTIFICATION_AREAS` = the 28 areas of the production event experience.
`production_event_certification()` = the honest self-certification: automated domain areas (event loop,
binding, debrief, cumulative update, restart, event switching, DB/config/thread safety); offscreen
(Command Centre, briefing, Live-tab navigation); **live-GT7 / visual / voice areas = NONE** (not run
headlessly, each with a `required_next_evidence` limitation). Overall = `NOT_TESTED` (bounded by the live
areas) BUT per-area detail is preserved (differentiated, not one undifferentiated NOT_TESTED).

## Certification levels & caps (retained)

The 10-level hierarchy with strict caps: automated ↛ visual/live/operational; offscreen ↛ visual; replay
↛ live-GT7; voice needs physical audio; operational readiness requires all live areas + a human grant + no
blocker. **`OPERATIONALLY_READY` is not awarded** — the live areas are untested headlessly.

## Real-tracker field limitations (Audit B) — `runtime_field_limitations()`

Per-field status, honestly recorded:

| Field | Status | Blocks |
| --- | --- | --- |
| car, track, fuel, telemetry-freshness, map-match | **EXACT** | — |
| event-context, setup-discipline, expected-setup, run-plan, selected-activity, session-purpose | **INFERRED** (composed from canonical local state) | — |
| layout | **LIMITED** (confirmed only with sufficient map-match confidence) | exact layout confidence |
| tyre compound | **LIMITED** (may be unknown before the first flying lap) | tyre-modelling confidence |
| **applied setup fingerprint** | **LIMITED — a LOCAL PROXY** (GT7 does not broadcast the setup; an unrecorded in-game change is undetectable) | exact setup identity, setup attribution |

These block **exact setup identity / setup attribution / tyre-model confidence** that depend on them; they
do **NOT** block Practice pace/consistency evidence. Nothing is disguised.

## Defect remediation (this slice)

The production golden/metamorphic net (`test_phase60_62_golden.py`) found ONE controller defect —
`UNVERIFIABLE` (a required field unknown, e.g. unverifiable layout) mapped to the generic `LIVE` state;
remediated to `LIMITED_MATCH` (cannot verify an exact match → limited). The golden scenario is the
regression test. No other domain defect surfaced. Live visual / GT7 / voice defect remediation is deferred
to live UAT.

## Voice certification

Voice remains optional, offline, disabled by default; the TTS advisory text is unchanged. Physical voice
UAT (enable / approved-message / mute / acknowledge / repeat / cooldown / priority / interruption / stale
+ dropout suppression / adapter-failure fallback / no autonomous commands) requires a physical audio
device and is marked `NOT RUN` here. The visual pit wall is fully functional without voice.

## Tests

`test_phase62_certification.py` (8), plus the shared golden/safety suites.
