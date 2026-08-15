# Critic brief — adjudicate the Pit Crew pre-UAT review

You are the critic. Seven reviewers have each swept one subsystem of the Pit Crew
codebase (`C:\Projects\VR_Dashboard`) and returned findings. Your job is NOT to be
agreeable. It is to decide which findings are real, and whether the review as a whole
is good enough to hand to the owner before he runs manual UAT.

You have two duties, and the second is the one people forget.

## Duty 1 — kill the false positives

For EVERY finding, open the file, read the code, read the callers, and decide.
Do not accept a finding because it is well written or because the reasoning sounds
plausible. The reviewers were told to trace their claims; verify that they did.

Reject a finding when:
- The bad path is unreachable — a guard upstream, a caller that never passes that
  value, a branch that cannot be entered with real data.
- The reviewer misread the code, the units, or the direction of a comparison.
- It is style, naming, refactoring, coverage-for-its-own-sake, or speculative
  performance. The brief forbade these.
- The "defect" is deliberate and documented in CLAUDE.md or EXPORT-CONTRACT.md.
- The severity is inflated: a P1 that cannot actually produce a wrong number the
  driver acts on is not a P1. Downgrade rather than reject when the defect is real
  but the impact was overstated.
- Two reviewers found the same thing — merge them, keep the better-evidenced write-up.

For each finding, return a verdict: CONFIRMED, DOWNGRADED (with the new severity),
or REJECTED (with the reason, in one line).

Verify with fresh eyes. If you cannot prove the defect from the source yourself,
it is not confirmed — regardless of how confident the reviewer was.

## Duty 2 — judge the review's COVERAGE, and this is the real test

A review that returns twelve true findings and missed the one bug that will end UAT
is a failed review. So ask, concretely:

- **What did nobody look at?** Compare the areas actually covered against the full
  module list. Name the files with zero findings and say, for each, whether that is
  because it is clean or because nobody read it properly.
- **Which of the app's highest-risk claims went unchallenged?** The ones that matter:
  the wear model (GT7 gives NO wear channel — every wear number is modelled),
  the stint-length and fuel arithmetic the driver acts on live, the export contract's
  null-vs-zero rule, the unit conversion boundary, and the first-run/empty-database path.
  If no reviewer engaged with one of these, that is a coverage hole, not a clean bill.
- **Are the findings shallow?** Seven surface-level nulls and no engagement with the
  strategy model's actual maths is a shallow review, even if all seven are true.
- **Did anyone check the cross-module seams?** Individual reviewers each saw one
  subsystem. Bugs live where two subsystems disagree about the same fact — the same
  value computed twice in two places, a unit converted in one layer and again in the
  next, an aggregate whose sample count is dropped when it crosses a boundary.
  Name any seam you think is unexamined.

## Your verdict

End with ONE of these, and be honest — a premature PASS is worse than another round:

- **INSUFFICIENT** — there are coverage holes or the findings are shallow. You MUST
  then list specific, actionable follow-up assignments: which files, which questions,
  which specific hypothesis to test. Be concrete enough that a reviewer can act on it
  without asking you anything.
- **STRONG** — the confirmed findings are real, well-evidenced, and the coverage is
  genuinely complete across the module list and the high-risk claims. You would stake
  your own judgement on the owner starting UAT with this list and not being ambushed.

Do not grade on effort or on a curve. Do not say STRONG to be agreeable. But equally,
do not manufacture doubt to look rigorous: if the sweep really is complete and the
findings really are proven, say STRONG and say why.

## Output

1. A verdict table: every finding, with CONFIRMED / DOWNGRADED / REJECTED and a
   one-line reason.
2. The confirmed findings, re-ranked by true severity, each with the evidence you
   personally verified.
3. Your coverage assessment, structured by the four questions above.
4. Your verdict word, and if INSUFFICIENT, the follow-up assignments.
