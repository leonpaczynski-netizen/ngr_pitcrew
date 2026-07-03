# Legacy Fan-Out Removal Phase 6a — Dispatcher SessionTag Snapshot

> Author: Legacy Fan-Out Removal Phase 6a sprint · Date: 2026-07-04
> Branch: `legacy-fanout-phase-6a-dispatcher-tag` (from `master` @ `b010882`)
>
> Companion docs: `docs/LEGACY_FANOUT_PHASE_5.md` (§4 retirement map — this is
> item 1), `docs/SESSION_CONTEXT_MIGRATION.md`.

---

## 1. Goal

Retirement-map item 1: remove the **telemetry-path** `config["strategy"]` reads
— the last *runtime* consumers of the fan-out outside bridges/writers. The
`EventDispatcher` read the dict at two `_dispatch` sites:

* **per-lap DB tagging** — `event_id=int(strat.get("event_id", 0))` on every
  `write_lap`;
* **fallback race-session open** — track / car / config_id / event_id when a
  race starts with no session yet.

Building an `EventContext` there would mean a DB query per lap event in the
telemetry pipeline, so the fix is a **push model**.

## 2. The mechanism

* **`data/session_context.SessionTag` (NEW, pure)** — frozen dataclass
  (`track`, `car`, `config_id`, `event_id`) with `from_strategy()` (reproduces
  the dispatcher's original reads verbatim) and a coercing
  `build_session_tag()`. Immutable → a plain attribute swap is **atomic under
  the GIL**, so no lock is needed between the UI (writer) thread and the
  dispatcher (reader) thread.
* **`EventDispatcher`** — seeds `self._session_tag =
  SessionTag.from_strategy(config["strategy"])` at construction (one-time,
  before the thread starts — the single remaining `main.py` bridge read,
  allowlisted); gains `set_session_tag(tag)` (None-safe swap); `_dispatch`
  reads only the tag at both sites. The dispatcher **no longer holds the config
  dict at all** (`self._config` removed).
* **`MainWindow._push_session_tag()` (NEW)** — builds the tag from the
  canonical contexts (`EventContext.track/.car/.event_id` +
  `StrategyContext.config_id` via `_active_config_id()` — the same byte-identity
  proofs as Phase 5's session-open migration) and pushes it. Never raises.

## 3. Push coverage (why the tag can't go stale)

The tag-relevant fields change only via these flows, each of which now pushes:

| Write flow | Push site |
|---|---|
| "Set as Active" (fan-out + config_id) | funnels through `_sync_strategy_from_event` → **`_update_race_config()` end** |
| Garage "Select for Event" (car) | calls `_sync_strategy_from_event` → same |
| Session-config restore (track/car + config_id recompute) | calls `_update_race_config()` directly → same |
| Save of the ACTIVE event (Phase 4 re-sync: track/event_id/rules) | **`_on_event_save`'s re-sync branch**, right after `_fanout_event_to_strategy` |
| App startup | dispatcher's construction seed + a belt-and-braces push at the end of `MainWindow.__init__` (before `dispatcher.start()` in `main()`) |

Between pushes the tag is exactly what the dict held at push time — which is
also exactly what the old live reads would have returned, because since Phase 4
the dict only changes through those same flows.

## 4. Behaviour notes (byte-identity)

* In-sync (always, post-Phase-4): tag fields equal the old raw reads — proven
  by test both for `from_strategy` (verbatim) and for the context-built tag.
* **Dead-default note:** the old fallback-open used
  `strat.get("track", "Unknown")`, but `DEFAULT_CONFIG` has always materialised
  `strategy.track = ""` (and `load_config` deep-merges over it), so the
  `"Unknown"` default was dead code — the real behaviour (empty string) is
  preserved and now explicit (tested).
* The fallback-open log line now prints the tag's car/track (same values).

## 5. Allowlist movement

`FROZEN_ALLOWLIST` (Phase 5 guard): `("main.py", "_dispatch"): 2` **removed**;
`("main.py", "__init__"): 1` **added** (the construction-time seed — a bridge
read, out of the hot path). Net: the telemetry pipeline no longer touches
`config["strategy"]` at runtime.

## 6. What was intentionally NOT changed

* The fan-out writer + Phase 4 save re-sync, the Track Modelling combo writer,
  the `_compute_race_config_id` hash, restore writers, plan-state persistence,
  and the context-builder bridges (retirement-map items 2–5).
* No telemetry event semantics, announcer, strategy-engine wiring, PTT, voice,
  setup/strategy logic, track mapping, AI prompts, or tab order.

## 7. Tests

`tests/test_legacy_fanout_phase_6a.py` (21) — SessionTag pure model
(`from_strategy` verbatim vs the legacy expressions, defaults incl. None, the
dead-"Unknown" note pinned against `DEFAULT_CONFIG`, coercion, immutability);
context-built tag == strategy-built tag (in-sync + empty); the **real
`EventDispatcher`** (no Qt, thread not started): construction seed, None-safe
swap, `RACE_STARTED` opens the session with exactly the tag fields,
`LAP_COMPLETED` writes `event_id` from the tag, an updated tag is used by the
next event; source-scans (`_dispatch` reads no config; the config attr is gone;
the push helper builds from the contexts; all push sites wired incl. ordering
after the fan-out write); writer/re-sync/Home-first/config-guardrail
invariants. Plus the Phase 5 allowlist updated (the guard held — it failed
until the allowlist was consciously shrunk).

## 8. Next sprint recommendation

> **Executed (2026-07-04):** the Connection-Signal sprint ran next — the real
> UDP-listener state was wired into SessionContext (Home's `live_active` and
> the telemetry labels are now real). See
> `docs/SESSION_CONTEXT_MIGRATION.md` §5a.
>
> **Executed (2026-07-04):** Phase 6b then delivered retirement-map item 2 as
> proof + golden vectors; the migration half is blocked by the
> restore-divergence and folds into items 3/4. See
> `docs/LEGACY_FANOUT_PHASE_6B.md`.

Retirement-map item 2: **`_compute_race_config_id` hash byte-stability proof**
(pin hash vectors, prove EventContext-sourced inputs identical in-sync, then
migrate the hash inputs) — or the standing smaller job: **wire the real
UDP-listener connection signal into `SessionContext`** (Home's `live_active`
becomes real), or return to product work (OFR-1).
