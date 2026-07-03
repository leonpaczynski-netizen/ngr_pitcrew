# SessionContext Migration — live telemetry / session state register

> Sprint: **SessionContext / TelemetryContext** · 2026-07-03
> Branch: `session-telemetry-context` (from `master` @ `c94e4ad`)
>
> Companion docs: `docs/EVENT_CONTEXT_MIGRATION.md`,
> `docs/STRATEGY_CONTEXT_MIGRATION.md`, `docs/SETUP_CONTEXT_MIGRATION.md`,
> `docs/TRACK_CONTEXT_MIGRATION.md`, `docs/LEGACY_FANOUT_PHASE_1.md`,
> `docs/HOME_DASHBOARD_BUILD.md`, `docs/PRODUCT_CONSOLIDATION_AUDIT.md` §7.

---

## 1. Why this exists

"Am I connected / recording / how many laps / what's the fuel burn / is a live
session active?" was answered by reaching into **volatile dashboard/tracker
attributes** scattered across the UI:

| Concept | Ad-hoc read (before) |
|---|---|
| connected | `self._tracker is not None and getattr(self._tracker, "_connected", False)` |
| packet count | `getattr(self._tracker, "_packet_count", 0)` |
| laps recorded | `self._tracker.laps_recorded` |
| active session | `getattr(self, "_active_session_id", None)` |
| live telemetry fuel | `getattr(self._tracker, "avg_fuel_per_lap", 0)` |
| resolved fuel burn | `_computed_fuel_burn_lpl()` — 3-tier fallback ending in `config["strategy"]["fuel_burn_per_lap"]` |
| Home `live_active` / `has_practice_laps` | documented approximations built the same way |

`SessionContext` is the telemetry-layer counterpart to the four existing context
read models: one immutable, validated snapshot of live-session status, so
consumers stop reaching into tracker internals and the legacy config fuel
fallback.

## 2. The read model (`data/session_context.py`, NEW — pure Python)

`SessionContext` (frozen dataclass) fields:

* **connection / packets** — `connected`, `packet_count`
* **live session** — `laps_recorded`, `active_session_id`, `is_recording`
  (`active_session_id is not None`), `live_active` (= `connected`), `live_mode`
* **fuel** — `telemetry_avg_fuel_per_lap` (raw live average), `fuel_burn_per_lap`
  (resolved), `fuel_burn_source` (`LOADED_SESSION` / `TELEMETRY` /
  `CONFIG_FALLBACK`)
* **practice laps** — `has_practice_laps`, `has_valid_laps` (caller-owned
  DB-derived flags)
* **provenance** — `source` (`EMPTY` / `LIVE`)

Helpers: `connection_text()` ("Connected"/"Disconnected"), `recording_text()`
("Yes"/"No"), `is_live`, `has_telemetry_fuel`, `to_dict()`, and a `flow_flags()`
bridge (`has_practice_laps` / `has_valid_laps` / `live_active`) for
`ui.product_flow` / the Home Dashboard.

`build_session_context(...)` takes plain values the caller already holds and
**never raises**. Ownership boundary: telemetry/session truth **only** — no
event/strategy/setup/track/AI fields (tested).

### Byte-identity guarantees (the point of the sprint)

* `connected` reproduces `tracker is not None and getattr(tracker, "_connected",
  False)` — including that the `RaceStateTracker` does **not** currently carry a
  `_connected` attribute, so it resolves `False` today (a real connection signal
  can later be wired in this one place; behaviour is unchanged for now).
* `fuel_burn_per_lap` reproduces `_computed_fuel_burn_lpl`'s 3-tier fallback
  exactly: loaded historical session average (> 0) → live telemetry average
  (> 0) → config fallback (default 2.0).

## 3. What was migrated (`ui/dashboard.py`)

New `_build_session_context(*, has_practice_laps=False, has_valid_laps=False)`
helper assembles the context from `self._tracker` (via safe getters),
`self._active_session_id`, `self._loaded_session_avg_fuel`, the
`config["strategy"]["fuel_burn_per_lap"]` fallback (the single legacy bridge
read), and `config["live"]["mode"]`.

| Consumer | Before | After |
|---|---|---|
| `_computed_fuel_burn_lpl` | inline 3-tier fallback + `config["strategy"]` read | `return self._build_session_context().fuel_burn_per_lap` |
| `_build_home_dashboard_state` | `live = tracker … _connected`; ad-hoc flags | `session_ctx.live_active` / `.has_practice_laps` / `.has_valid_laps` |
| `_refresh_telemetry_context` | `getattr(tracker,"_connected"…)`, `_packet_count`, `avg_fuel_per_lap`, session-id recording | `sctx.connection_text()` / `.packet_count` / `.recording_text()` / `.telemetry_avg_fuel_per_lap` |

`_computed_fuel_burn_lpl` is the flagship: it was the telemetry-owned fuel-burn
read that `docs/AI_SNAPSHOT_MIGRATION.md` and `docs/LEGACY_FANOUT_PHASE_1.md`
deferred; its `config["strategy"]` read now lives only in the context builder.

## 4. What was intentionally NOT changed

* No telemetry, PTT, voice, live-race, calibration, setup, strategy-calculation,
  track-mapping, AI-prompt, or tab-order behaviour. Every migrated read is
  byte-identical (tested); labels and computed values are unchanged.
* `_home_has_practice_laps` still owns the DB query (SessionContext just carries
  the resulting flags — no DB/I/O moved into the pure model).
* `config["strategy"]` and both fan-out writers remain; the fuel-fallback read
  is the context builder's legitimate legacy input (LEGACY_REQUIRED), not a
  consumer leak.
* The `RaceStateTracker` itself is untouched — SessionContext reads it from the
  outside via safe getters.

## 5. Deferred / future

* **Real connection state** — today `connected` mirrors the (always-False)
  `tracker._connected` read. Wiring the actual UDP-listener connection signal
  into SessionContext is a follow-up; because every consumer now reads the
  context, that becomes a one-place change.
* **`has_valid_laps`** is still approximated as "recorded laps are reviewable"
  (the Home Dashboard approximation) — a true lap-validity owner (a lap/session
  validity model) is future work.
* Remaining volatile tracker reads elsewhere (live tyre labels, fuel bar, race
  countdown, per-packet UI) are live-render paths, not status/summary reads, and
  were left alone.

## 6. Tests

`tests/test_session_context.py` (25) — fuel-burn 3-tier byte-identity vs the
verbatim legacy logic + source classification; connection/live/recording
semantics; count coercion; live-mode default; source EMPTY vs LIVE; garbage
safety; ownership boundary (no foreign fields); `flow_flags` bridge; `to_dict`;
module purity; and source-scans that `_computed_fuel_burn_lpl`,
`_build_home_dashboard_state`, and `_refresh_telemetry_context` read the context
(no tracker-internal / inline-fallback reads remain) and write no
`config["strategy"]`; plus Home-first + config-guardrail invariants.

## 7. Next sprint recommendation

**Legacy Fan-Out Removal Phase 2** — migrate the DB-first-precedence event-rule
display/validation consumers (`_sync_strategy_from_event`,
`_sync_setup_builder_from_event`, tuning/BoP validation) to EventContext,
explicitly accepting and testing the behaviour change, then begin retiring the
"Set as Active" fan-out once every reader is migrated. Alternatively, **wire real
connection state into SessionContext** (now a one-place change) to make the Home
Dashboard's `live_active` reflect the actual UDP listener.
