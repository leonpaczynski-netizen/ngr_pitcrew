# Engineering Brain — Program 2, Phase 34: Deterministic Assurance Snapshot Comparison

**Status:** DONE (committed locally, NOT pushed, no PR, not merged) ·
**Branch:** `eng-brain-phase33-35-assurance-review-pack` (from Phase-32 tip `0e88b8e`) ·
**DB:** v26 (no migration, no new persistence) · **RULE_ENGINE_VERSION:** 46.0. Part of the combined
Phase 33–35 slice.

## What it is

A pure, deterministic comparison of two already-built assurance-chain exports (or snapshots) in an
**explicit direction (baseline → candidate)**. It reports what changed across domains, findings,
assumptions, contradictions, readiness and evidence priorities, and whether assurance improved,
regressed or is unchanged — without ever equating "newer" with "better" or using a timestamp to decide
which snapshot is authoritative.

## Domain (`strategy/assurance_snapshot_comparison.py`)

Models: `AssuranceComparisonDirection` (baseline→candidate), `AssuranceCompatibility`
(`COMPATIBLE` / `PARTIALLY_COMPATIBLE` / `INCOMPATIBLE` / `UNVERIFIABLE`), `AssuranceChangeType`
(`added` / `removed` / `unchanged` / `modified` / `improved` / `regressed` / `reopened` / `resolved` /
`incomparable`), `DomainAssuranceDelta`, `FindingDelta`, `AssumptionDelta`, `ContradictionDelta`,
`ReadinessDelta`, `PriorityDelta`, `AssuranceSnapshotComparison`. Entry:
`compare_assurance_snapshots(baseline_export, candidate_export)`.

## Compatibility gate

Verifies programme identity (car / discipline / gt7_version / driver), export schema, GT7 version,
rule-engine version, layout/compound context and domain identity. Missing required identity →
`UNVERIFIABLE`; car/discipline/driver or schema mismatch → `INCOMPATIBLE`; GT7/rule/layout/compound
differences → `PARTIALLY_COMPATIBLE`. An `INCOMPATIBLE`/`UNVERIFIABLE` comparison sets
`assurance_direction = incomparable` and renders **no trend**.

## Delta doctrine (enforced + tested)

- A finding/contradiction/assumption that vanishes **because its domain disappeared** → `INCOMPARABLE`,
  not resolved / not an improvement.
- A contradiction that **closes without an increase in independent evidence** → `MODIFIED`
  (unverified), not `RESOLVED`.
- An assumption **dropped without establishing evidence** → `REMOVED`, not an improvement (an
  assumption is only `RESOLVED` when readiness improved AND independence increased).
- A readiness increase is only `IMPROVED` when **corroborated by more independent evidence**, else
  flagged unverified.
- More evidence rows without more independence is not progress.
- The overall `assurance_direction` is only `improved`/`regressed` when the grade movement is
  **corroborated** by a material positive/negative change; otherwise `moved_unverified` /
  `changed_neutral`.

## Fingerprint

The **comparison fingerprint** is over: baseline chain fingerprint + candidate chain fingerprint +
compatibility decision + every ordered delta + the direction. It is direction-material (forward ≠
reverse) and timestamp-free. Deterministic tie-break: `(change_type_priority, domain, key)`.

## Baseline import & validation (`strategy/assurance_manifest_loader.py`)

A strict **pure** read-only validator for a supplied baseline (a prior Phase-33 export or Phase-35
review-package manifest, as JSON text or a parsed object). `parse_canonical_json` rejects non-finite
constants (`Infinity`/`NaN`) and non-JSON. `validate_baseline` detects export vs review-package,
checks schema + required fields + **no silent enum fallback**, recomputes section content digests and
the chain fingerprint (via the export authority) and **rejects tampered/forged values**.
`verify_review_package_artifacts` recomputes each artifact's sha256 vs the manifest and rejects
**path-traversal / duplicate / missing** names. It never executes content, never imports Python
objects, never uses pickle, and never trusts a claimed fingerprint without recomputation.

## Read-only SessionDB entry

`SessionDB.build_assurance_snapshot_comparison_report(baseline, ...)` → `{ok, comparison,
baseline_valid, compatibility, assurance_direction, content_fingerprint}`. Validates the baseline
**purely (no DB reads)** — an invalid baseline short-circuits before any chain read — then builds the
current export via the shared chain **once** and compares. Never calls lower public SessionDB
builders; no DB write; `user_version` 26.

## Renderer

`strategy/assurance_snapshot_comparison_render.py` — an incompatible comparison shows no trend;
strings only, zero DB, timestamp-free, no setup values.

## Tests (this phase's dedicated suite)

`tests/test_phase34_comparison.py` (19): compatible / partially / incompatible / unverifiable;
same-snapshot no changes; improvement/regression with provenance; every delta category; deleted-
evidence-and-domain-gone incomparable; contradiction-closed-without-evidence unverified; assumption-
dropped-without-evidence not improvement; readiness requires independence; timestamp ignored; direction-
material fingerprint; incompatible render shows no trend. Baseline loader/forgery/malformed/non-finite
rejection is in `tests/test_phase35_package.py`.

## Boundaries

No experiment/campaign/schedule/resource; no setup values; no Apply; no AI/optimiser/scheduler; no DB
write; no migration; comparison is not a certification and resolves/establishes nothing.

**Phase 36 not started.**
