# Engineering Brain — Program 2, Phase 35: External Assurance Review Package

**Status:** DONE (committed locally, NOT pushed, no PR, not merged) ·
**Branch:** `eng-brain-phase33-35-assurance-review-pack` (from Phase-32 tip `0e88b8e`) ·
**DB:** v26 (no migration, no new persistence) · **RULE_ENGINE_VERSION:** 46.0. Part of the combined
Phase 33–35 slice.

## What it is

An on-demand review package suitable for sharing with an external technical reviewer **without opening
the application**. It contains deterministic generated artifacts (not database persistence) that let a
reviewer answer: *"does this assurance verdict genuinely follow from the recorded evidence and
deterministic rules?"* — a human-readable report, a machine-readable manifest, content digests,
fingerprints, provenance, an optional baseline comparison, limitations/advisory, schema/version
identifiers, and verification instructions that **do not require trusting filenames or timestamps**.

## Pure package specification (`strategy/assurance_review_package.py`)

`build_review_package_spec(export, comparison=None)` computes (writing nothing): the member artifacts
— `assurance_review_report.md` (human-readable), `assurance_chain_manifest.json` (machine-readable),
and, when a baseline is supplied, `assurance_comparison_report.md` + `assurance_comparison_manifest.json`
— each with a sha256 content digest; the **package manifest** (membership, digests, identity, chain +
comparison fingerprints, artifact order, verification instructions, limitations, advisory); and the
**package fingerprint** over the SORTED `(kind, content_digest)` pairs + identity + grade + chain fp +
comparison fp. The destination path, filenames and timestamps are **not** in the fingerprint.

## The writer adapter (`data/assurance_review_package_writer.py`) — the ONLY file writer

`write_review_package(pkg, destination_dir, *, allow_overwrite=False, make_archive=False)`:
- requires an **explicit** destination (no implicit default); refuses to overwrite unless allowed;
- stages every file in a temp directory, verifies each written byte against its digest, then moves
  into place; cleans the staging directory on failure (no partial leak);
- writes only the package's own safe-named artifacts + `package_manifest.json`; touches **no
  database** and **no source/runtime file**; includes **no** db file / setup history / settings /
  API keys / track-model runtime files / absolute source paths;
- can emit a **byte-deterministic zip** (sorted members, fixed 1980-01-01 entry dates, `ZIP_STORED`,
  fixed attributes) — byte-identical across writes (verified);
- returns a deterministic result (files written + sha256, package fingerprint, archive sha, validation,
  warnings, destination). The destination is reported **outside** the deterministic report content.

## Fingerprint hierarchy (this phase)

- **Review-package fingerprint** — over the package manifest identity + the sorted `(kind,
  content_digest)` of every member artifact. Identical inputs → identical semantic manifest and
  fingerprint (a package generated twice from identical input is byte-identical, archive included).
- Container caveat: the directory-of-files package is guaranteed byte-identical; the optional zip is
  made byte-deterministic by fixing entry dates/attributes/order (documented honestly).

## Read-only SessionDB entry + UI

`SessionDB.build_assurance_review_package_report(baseline=None, ...)` builds the current export (+
optional validated baseline comparison) into a pure package SPEC — it **writes nothing**. Reuses the
shared chain **once**; never calls lower public SessionDB builders; baseline validation performs no DB
read.

UI: `ui/assurance_review_pack_vm.py` + `ui/assurance_review_pack_panel.py`
(`AssuranceReviewPackPanel`) in the Development History page. Read-only w.r.t. knowledge/DB: NO Apply,
NO experiment/campaign/schedule control, NO editable assurance grade/priority, NO setup values, NO
API-key access. Three explicit-action buttons — **Preview Assurance Review**, **Compare Baseline...**,
**Export Review Package...** — delegate to dashboard handlers that run the build/write **off the Qt
thread** with stale-worker guards; a successful export destination is shown **outside** the report
content. Nothing is exported automatically; writing happens only on an explicit user action with an
explicit destination.

## Deterministic ordering

Artifacts in fixed `ARTIFACT_ORDER`; canonical JSON sorts keys; zip members sorted; the package
fingerprint is over sorted `(kind, digest)` pairs. Shuffled inputs → identical package bytes and
fingerprint.

## Tests

`tests/test_phase35_package.py` (20): deterministic spec/artifacts/report/manifest/digests/fingerprint;
explicit destination required; no implicit writes; overwrite guard; failed-write staging cleanup; no
source paths/secrets/forbidden files; deterministic byte-identical zip; re-open + verify; corrupted
artifact fails; forged/malformed/non-finite/path-traversal/duplicate/unknown-enum baseline rejection;
valid export round-trip. Shared suites: `tests/test_phase33_35_{query_shape[7], safety[34], golden[8],
runtime[6], ui[14]}.py`.

## Runtime verification (shared Phase 33–35)

DB byte-identical before/after export + compare; `user_version` 26; repeated/restart/shuffled-row
export byte-identical; package manifest verifies independently and a corrupted artifact fails;
end-to-end dashboard export runs OFF the UI thread and mutates no DB; export refuses without a
destination; no setup values / secrets / absolute machine paths; negative-only visible; fully-assured
truthful; incompatible snapshots produce no false trend; explicit export is the only write path.

## Boundaries

No experiment/campaign/schedule/resource; no setup/race-strategy values; no Apply; no AI/optimiser/
scheduler; no knowledge mutation; no marking findings resolved / assumptions established; no DB write;
no migration; no new persistent tables. **A review package is NOT an independent certification.**

**Phase 36 not started.**
