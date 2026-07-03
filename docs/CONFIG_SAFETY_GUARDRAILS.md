# Config Safety Guardrails

> Author: Config Safety Guardrails sprint · Date: 2026-07-03
> Branch: `config-safety-guardrails` (from `home-dashboard-promotion` @ `69289ba`)
>
> Companion docs: `docs/HOME_DASHBOARD_PROMOTION.md` (the sprint whose smoke run
> triggered this), `docs/PROJECT_STATE.md`, `MASTER_TESTING_REGISTER.md`.

---

## 1. Why this sprint exists

`config.json` is the app's live settings store. The app rewrites it during
normal use **and during `MainWindow` construction** (the API-key auto-load and
`config_id` derivation paths call `_persist_config`). During the Home Dashboard
Promotion sprint a headless smoke test constructed `MainWindow` pointed at the
**real** `config.json` and clobbered the user's personal settings. The file is
gitignored, so there was no git recovery copy — it had to be rebuilt by hand
from `DEFAULT_CONFIG` (the Anthropic API key survived only because it was
re-read from `api_key.txt`).

This sprint makes that class of accident impossible: tests, smoke runs, and
automated app construction can never read from or write to the user's real
`config.json` unless explicitly requested.

## 2. Config read/write audit

**Where config is loaded**

| Site | What |
|---|---|
| `main.main()` | resolves the path (`--config` → `NGR_CONFIG_PATH` → `config.json`) and calls `load_config()` once at startup |
| `config_paths.load_config(path)` | the single loader — deep-merges the file over `DEFAULT_CONFIG`; never raises |

**Where config is saved**

| Site | What |
|---|---|
| `ui/dashboard.py MainWindow._persist_config()` | the single write site — delegates to `config_paths.save_config()` |
| ~22 callers of `_persist_config()` | settings save, event activation, race-config update, shift-beep, strategy cache, setup save, etc. |
| `ui/setup_builder_ui.py` (3), `strategy/setup_ranges.py` | `_persist_config` callers / an unrelated ranges cache (not the user config) |

**Paths that save config during `MainWindow` construction**

* `_migrate_setup_ids()` (from `__init__`) — persists if any saved setup lacked a `setup_id`.
* `_build_strategy_builder_tab()` (from `_setup_ui`) — auto-loads the API key from `api_key.txt` into `self._config` and derives the `config_id`; a subsequent save writes it back. **This is the exact path that reintroduced the real API key into the clobbered file.**

**What constructs `MainWindow`**

* `main.main()` — the real app (uses the resolved real path — correct).
* Before this sprint: **no committed test** constructed `MainWindow`; the clobber came from an ad-hoc Bash smoke script. The group tests bind individual methods onto `MagicMock` stubs (`types.MethodType`) and never build a real window.
* After this sprint: `tests/test_config_safety_smoke.py` constructs it — always against a temp config.

**Whether any test uses the real config path**

* `tests/test_group38_relative_degradation_acceptance.py::test_ac3_default_is_2_from_config_json` **reads** the real `config.json` (via `open()`) to assert `strategy.degradation_consecutive_laps == 2`. Read-only assertion of a committed default — not a clobber risk; the session guard proves it's never written.
* No test writes the real config.

**Protections that existed before** — only `.gitignore` (`config.json`).
**Protections that were missing** — path injection for tests, a guard against real-config reads/writes under tests, atomic/backup-safe writes, and a proof that construction leaves the real file untouched. All added here.

## 3. The mechanism (`config_paths.py`, NEW — pure Python)

A single, PyQt-free module owns config path resolution, loading, saving, and the
guardrail, so it is unit-testable and cannot create import cycles (`main` and
`ui.dashboard` import *from* it).

* **`DEFAULT_CONFIG`** — moved here from `main.py` (re-exported there for
  backward compatibility). One schema change: `strategy.degradation_consecutive_laps`
  is now materialised as `2` (previously only a read-time `.get(..., 2)`
  default), so a freshly created config carries the value the acceptance test
  pins. Behaviour is identical wherever the key is read.
* **`resolve_config_path(explicit=None)`** — precedence: explicit (`--config`) →
  `NGR_CONFIG_PATH` env → `config.json`. The normal app passes nothing; tests /
  smoke runs inject a temp path.
* **`is_test_environment()`** — true under pytest (`pytest` in `sys.modules`,
  `PYTEST_CURRENT_TEST`, or `NGR_TEST_MODE=1`). `python main.py` never imports
  pytest, so the real app is never treated as a test.
* **`is_real_config_path(path)`** — true only when `path` resolves to the
  repo-root `config.json` (`REAL_CONFIG_PATH`).
* **`real_config_access_blocked(path)`** — `is_test_environment()` **and**
  `is_real_config_path(path)` **and not** the explicit opt-out
  (`NGR_ALLOW_REAL_CONFIG=1`).
* **`load_config(path)`** — deep-merges over `DEFAULT_CONFIG`; never raises. Under
  the guardrail, reading the real config is refused (returns the defaults) so a
  test never pulls the user's secrets into memory.
* **`save_config(path, config, *, backup=True)`** — under the guardrail, writing
  the real config **raises `ConfigSafetyError`**. Otherwise it writes safely:
  serialise **first** (an encoding error never truncates the target — no partial
  writes), optional `.bak` backup of the previous file, then write `<name>.tmp`
  and `os.replace` (an **atomic** swap).
* **`write_default_config(path)`** — seed a fresh config from `DEFAULT_CONFIG`
  (used by the temp-config fixture).

## 4. Wiring changes

* **`main.py`** — `DEFAULT_CONFIG` / `load_config` now imported from
  `config_paths` (re-exported); `main()` resolves the path via
  `resolve_config_path(explicit)`.
* **`ui/dashboard.py _persist_config()`** — delegates to `config_paths.save_config(..., backup=True)`;
  catches `ConfigSafetyError` (logs "BLOCKED real-config write under tests" and
  returns without writing) so construction/saves never crash under tests. Normal
  runs write the real config exactly as before, now atomically with a `.bak`.
* **`.gitignore`** — also ignores `config.json.bak` and `config.json.tmp`.

## 5. Test isolation (`tests/conftest.py`, NEW)

* **`temp_config_path`** fixture — a per-test isolated `config.json` seeded from
  `DEFAULT_CONFIG` in pytest's `tmp_path`. Being outside the repo root it is
  never the guarded real path, so load/save operate on it freely. Its directory
  has no `api_key.txt`, so the API-key auto-load finds nothing — no secret is
  ever pulled into a test.
* **`_guard_real_config`** — session-autouse safety net. Hashes the real
  `config.json` (SHA-256, never raw bytes) before and after the whole run and
  **fails the suite** if any test changed it. Independent proof of the top
  acceptance criterion.

## 6. Safe headless smoke testing

`MainWindow` smoke construction must:

* use a temp config path (`temp_config_path` fixture),
* prove the real `config.json` is byte-identical before/after,
* use no real API key (a temp-dir config + no `api_key.txt` there),
* avoid real DB writes (`db=None`) and audio/threads (mock the logger/announcer).

`tests/test_config_safety_smoke.py` is the committed, safe pattern
(`pytest.importorskip("PyQt6")`, offscreen Qt). It also proves that a window
*mistakenly* wired to the real path cannot clobber it — the guardrail turns the
write into a logged no-op, not a crash.

**Never** construct `MainWindow`, run the app, or call `save_config` against the
real `config.json` in an ad-hoc script. If you must, set `NGR_CONFIG_PATH` to a
temp file first, or pass `--config <temp>`.

## 7. What was intentionally NOT changed

* No config **schema** change beyond materialising the already-effective
  `degradation_consecutive_laps: 2` default (required by the sprint and tested).
* No setup/strategy/track-mapping/AI-prompt/AI-input/telemetry/PTT/voice/
  calibration/workflow logic. `_persist_config`'s call sites and the config
  contents the app writes are unchanged — only *how* the bytes reach disk
  (atomic + guarded) changed.
* `config["strategy"]` and both legacy fan-outs are untouched (Legacy Fan-Out
  Removal remains a separate sprint).

## 8. Risks / notes

* The guardrail keys on `is_test_environment()`; it fires whenever pytest is
  imported into the process. A non-pytest tool that imports `pytest` and then
  writes the real config would be blocked — acceptable and safe.
* `is_real_config_path` compares resolved paths against the repo-root
  `config.json`. A user who runs the app from a different working directory with
  a *different* `config.json` is still writing their own file normally (not a
  test), so the guard (test-mode only) never interferes.
* `test_ac3_default_is_2_from_config_json` still reads the real file directly for
  its assertion; that is a read-only check of a committed default, and the
  session guard proves the file is never written.

## 9. Next sprint recommendation

**Legacy Fan-Out Removal Phase 1** — with the four canonical contexts, the AI
snapshot layer, the Home Dashboard (now the landing tab), named navigation, and
config-write safety all in place, the `config["strategy"]` event fan-out
(`_on_event_set_active`) is the remaining worst SSOT violation. Phase 1 should
migrate the low-risk read-only consumers off `config["strategy"]` onto
`EventContext`/`StrategyContext`, keeping the fan-out writer as compatibility
until every reader is migrated.
