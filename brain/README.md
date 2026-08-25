# `brain/` — the race-engineering knowledge base, in version control

This is the "My Driving Style - Tuning" Claude Project, exported and put under
git on 21 Aug 2026. It is the reasoning half of the programme; `pitcrew/` is the
measuring half, and `CLAUDE.md` and `EXPORT-CONTRACT.md` are the contracts
between them.

**Why it moved.** A brain that lives only in a Project cannot be diffed, tested,
or read by anything but a person typing into a chat box — and it had drifted
from the code. The first reconciliation found six places where the knowledge
base carried a defect the app had already fixed, and one place where the app had
found a mechanism the knowledge base had wrong. Neither record knew.

## Layout

| | |
|---|---|
| `_inbox/` | **The raw export, unedited, under its original names.** Not authoritative — it is the record of what the Project actually said, so every later decision can be traced to a source rather than to a memory of one. The `NN-` numbering is the KB's own and is preserved. |
| `_inbox/setups/` | Event outputs — the dated, car-and-circuit documents. These carry the *reasoning* behind every value on a sheet, which `setup_sheets_v8` has nowhere to store. **All pre-1.71.** |
| `driver.md` | **The standing refusals and the measurement limits** — what he will not do, and what his own data cannot show. Started 21 Aug 2026 for facts that were true and written down nowhere. Every line sourced. |
| `RECONCILIATION.md` | Where the knowledge base and the code disagree, with verdicts and the open questions. **Read this before trusting either record on anything app-facing.** |

## The entry points, in the KB's own order

1. **`_inbox/16-update-1.71-physics-change.md`** — what update 1.71 changed and
   the re-measurement protocol. Until §12 is closed, read it alongside everything
   else: the method survived the patch, the numbers have not been re-verified.
2. **`_inbox/17-v1.71-measured-results.md`** — what has actually been measured
   since. Short, and the only document in the set whose numbers are post-patch.
3. **`fuji-race-2026-08-24.md`** — the first RACE measured on v1.71, and the
   only document here with post-patch race numbers rather than practice ones:
   lap-time sigma, fuel burn, the pit-stop decomposition, and why a null
   degradation result does not mean the tyres held. Its §6 reverses the Watkins
   setup-provenance conclusion; `RECONCILIATION.md` §F carries the rulings.
4. **`_inbox/08-playbook-leon.md`** — the synthesis, and where a setup decision
   starts.
5. **`_inbox/00-INDEX.md`** — the full map, the standing rules, and the open items.

## The rule this directory exists to enforce

**Superseded material is kept with its supersession recorded, never deleted.** A
rule that was believed and then disproved is evidence in its own right — about
the fault, and about how it survived scrutiny. Silently dropping it invites
re-adopting it a season later. `RECONCILIATION.md` §C1 is the worked example.
