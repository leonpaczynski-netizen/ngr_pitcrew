# Engineering Brain — Program 2, Phase 33: Deterministic Assurance-Chain Export

**Status:** DONE (committed locally, NOT pushed, no PR, not merged) ·
**Branch:** `eng-brain-phase33-35-assurance-review-pack` (from Phase-32 tip `0e88b8e`) ·
**DB:** v26 (no migration, no new persistence) · **RULE_ENGINE_VERSION:** 46.0 · `_setup_constants.py`
byte-identical. Part of the combined Phase 33–35 Assurance Review Pack slice.

## What it is

A deterministic, offline, **read-only** on-demand export of the complete assurance chain (Phases
26–32) required to explain the programme's current assurance state. It consumes **one shared in-memory
knowledge chain** and does not rebuild any lower phase through a separate SessionDB entry point. The
pure builder **writes no files**.

## Canonical serialization authority (`strategy/assurance_chain_serialization.py`)

The single serializer shared by Phases 33–35: deterministic canonical JSON (sorted keys, compact
separators, ASCII-only, `allow_nan=False`), explicit float normalisation to 6 decimals with rejection
of non-finite numbers, enum-value normalisation, `content_digest` (full sha256) and timestamp-free
`short_fingerprint`, a conservative `is_safe_relative_name` check, `recomputed_content_digest`
(digest over a report's actual content excluding its self-declared fingerprint), and the fixed
`CHAIN_PHASE_ORDER` (Phase 26→32). No object identity/addresses/timestamps/machine paths; byte-
identical across restart. It is the ONE serializer — export, comparison and packaging all use it.

## Export domain (`strategy/assurance_chain_export.py`)

Models: `AssuranceChainExport`, `AssuranceChainManifest`, `AssuranceChainSection`, `ProvenanceEntry`,
`IntegrityEntry`, `ExportValidationResult`. Builder: `build_assurance_chain_export(chain_products,
context)`.

Each section carries the **canonical product content** + its self-declared subordinate fingerprint +
a **recomputed content digest** (over the actual content). The manifest exposes: schema, programme
identity, context identity (layout/compound/domains), DB schema version, rule-engine version,
included phase versions, section order, subordinate fingerprints, assurance grade, the
**assurance-chain fingerprint** and the **canonical-manifest fingerprint**, plus deterministic
ordering metadata. Provenance identifies programme/context, domains, source-evidence identity
(source-chain fingerprints), version context, schema versions, subordinate fingerprints and
derivation order.

`recompute_chain_fingerprint(export)` and `verify_export_integrity(export)` recompute each section
digest from its content and the chain fingerprint from those digests — so tampered content is
detected independent of the claimed labels.

## Fingerprint hierarchy (this phase)

- **Subordinate fingerprints** — each Phase 26–32 product's own `content_fingerprint`, retained.
- **Assurance-chain fingerprint** — over the *recomputed* section content digests + identity + DB/rule
  versions + fixed section order. Changes on ANY material subordinate change even if a lower phase
  keeps the same summary label.
- **Canonical-manifest fingerprint** — over the canonical manifest.

### Fingerprint identity policy (clarified — audited in the Phase 36–38 slice)

Earlier wording ("No ... object identity or DB row order enters any fingerprint") was correct but
incomplete, because it did not distinguish *semantic* identity/order (which is material) from
*runtime/accidental* identity/order (which is not). The precise policy, shared by every Program 2
domain fingerprint, is:

1. **Semantic engineering-context identity IS included** where it is part of the meaning — programme
   identity (car / discipline / gt7_version / driver), layout/compound, knowledge domains, DB schema
   and rule-engine versions. Two different contexts must not collide on one fingerprint.
2. **Runtime / object / machine identity is excluded** — Python `id()`/memory addresses, `repr` of
   objects, hostnames, usernames, filesystem paths, export destinations, wall-clock timestamps and
   random identifiers never enter a fingerprint.
3. **Accidental source-row order is excluded** — the order rows happen to arrive from a `SELECT`
   (`id ASC`, insertion order) must not change any fingerprint; the pure layers re-order
   deterministically before hashing.
4. **Canonical semantic priority order MAY be fingerprint-material** — where an ordering *is* part of
   the product meaning (e.g. `CHAIN_PHASE_ORDER`; a ranked priority list), that canonical order is
   included, so deliberately changing the canonical order changes the fingerprint. This is intended.

## Read-only SessionDB entry

`SessionDB.build_assurance_chain_export_report(...)` → `{ok, export, grade, chain_fingerprint,
content_fingerprint}`. Uses the shared `_build_knowledge_chain` **once**, computes Phase-26..32 purely
in memory via the private `_assurance_chain_products` helper, never calls the lower public SessionDB
builders, performs no extra DB reads, writes nothing. `user_version` stays 26; empty programmes return
a truthful `None`; negative-only programmes remain exportable (the Phase-29 chain gate is unchanged).

## Deterministic ordering

Sections in the fixed `CHAIN_PHASE_ORDER`; within each product, lists keep their own deterministic
order; canonical JSON sorts object keys. Shuffled DB row order → identical export bytes and
fingerprint (runtime-verified).

## Tests (this phase's dedicated suite)

`tests/test_phase33_export.py` (14): complete Phase 26–32 inclusion in order; subordinate
fingerprints; provenance/integrity; byte-identical canonical manifest across restart; material
subordinate change alters the chain fingerprint; tampered section content detected by recompute;
recompute matches claimed; empty / negative-only / fully-assured exports; DB+rule versions; no setup
values; ASCII-clean render; real-DB determinism + no DB write. (Query-shape, safety, golden and
runtime are shared with Phases 34–35 — see those docs.)

## Boundaries

No experiment/campaign/schedule/resource; no setup values; no Apply; no AI/optimiser/scheduler; no DB
write; no migration; no new persistent tables/fields; the export is NOT an independent certification.

**Phase 36 not started.**
