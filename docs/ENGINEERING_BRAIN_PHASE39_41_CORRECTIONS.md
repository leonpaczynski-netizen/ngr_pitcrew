# Engineering Brain — Phase 39–41 Completion Corrections

Focused corrections to the Phase 39–41 completion documentation, discovered while auditing at the start
of the Phase 42–44 slice. No Phase 39–41 commit is amended; this is an additive correction record.

## 1. Verified changed-file count

Git truth for the Phase 39–41 slice (`git diff --name-status 2cbe077..a57d25a`):

| Class | Count |
| --- | --- |
| Added (`A`) | 28 |
| Modified (`M`) | 28 |
| Deleted (`D`) | 0 |
| **Total changed** | **56** |

`git diff --stat` agrees: *56 files changed, 4296 insertions(+), 90 deletions(-)*. The completion
report's headline "56 files changed" is **correct**. Any narrative reference to "57 files" is an
overcount and should read **56 (28 added, 28 modified, 0 deleted)**.

## 2. Automated tests are not executed manual UAT

The Phase 39–41 slice provided a **written** manual UAT guide but did **not** execute it in the live
GUI. Automated unit/property/runtime tests prove the equivalent behaviours but are **not** a substitute
for executed manual UAT. The Phase 42–44 slice executes manual UAT where the environment permits and
reports exactly which steps ran/passed/failed/were-not-run.

## 3. The 5-vs-16 query-shape proof was limited

The Phase 39–41 query-shape test compared only small histories (5 vs 16 records). That proves the query
**count** is constant across those sizes but is a **limited** proof. The Phase 42–44 slice extends
query-shape testing to larger deterministic fixtures (5 / 50 / 500 records, many legacy partial-context
records, many incompatible records, several candidate sessions) and reports both query count and basic
runtime observations.

## 4. Unknown material context does not prove exact equivalence

The Phase 36–41 context model correctly held that "an unknown value never counts as a *difference*"
(`_both_known_differ`). The Phase 42 corollary, now made explicit: **an unknown value also never proves
exact *equivalence*.** Missing material fields (tyre multiplier, compound, BoP, tuning state, layout,
setup discipline, …) **cap or block** exact-context use for the conclusions that depend on them, rather
than being silently treated as a match. This is implemented in the Phase 42 material-context trust
domain.
