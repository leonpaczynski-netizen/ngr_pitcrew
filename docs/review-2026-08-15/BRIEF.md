# Pit Crew — pre-UAT code review brief

You are one of several reviewers doing a **full correctness review** of the Pit Crew
codebase (`C:\Projects\VR_Dashboard`, package `pitcrew/`) immediately before the owner
runs manual UAT. Your findings will be checked line-by-line by an adversarial critic
who will reject anything you cannot prove from the source. Precision matters more
than volume: **one proven defect beats ten plausible ones.**

## Read first (they are the contract, and they outrank your instincts)
- `CLAUDE.md` — the project brief. Sections 3 (what the telemetry feed does and does
  NOT give), 4 (standing rules), 5 (the strategy engine) are the substance.
- `EXPORT-CONTRACT.md` — the export schema. Treat it as an API.

## What counts as a finding
Ranked by what actually hurts this app:

1. **Silent wrongness in a number the driver acts on.** A wear rate, a stint length,
   a fuel figure, a lap time, a corner metric that is computed wrong and displayed
   with confidence. This is the worst class of bug here and the highest priority.
2. **Violations of the standing rules in CLAUDE.md §4**, especially:
   - missing must be `null`, never `0` (a defaulted zero is diagnosed as a real value)
   - every aggregate carries its sample count
   - nothing derived is presented as measured
   - driver report is primary evidence; telemetry corroborates
3. **Crashes and exceptions on real paths** — unguarded divides (fuel capacity can
   legitimately be 0 for EVs, 5 L for karts), index errors on short/empty sequences,
   `None` arithmetic, `KeyError` on optional data, unhandled empty-DB / first-run state.
4. **Contract violations** against EXPORT-CONTRACT.md — wrong key names, wrong units,
   wrong nesting, a field emitted as 0 where the contract says null.
5. **Unit errors.** CLAUDE.md §3.4 fixes the conversion table: speed m/s→km/h,
   pedals 0-255→0-100%, angles rad→deg, suspension m→mm, times integer ms.
   A conversion applied twice, or not at all, or at the wrong layer.
6. **State-machine and lifecycle bugs** — session/lap boundaries, pit detection,
   threading (Qt thread affinity, mutation from the capture thread), resource leaks.
7. **Bare `except`** and over-broad exception handling that swallows real failures.
   This is a known through-line of past defects in this codebase.
8. **Dead / unreachable / contradictory code** — a branch that can never fire, two
   code paths that disagree about the same fact, a constant that is fabricated.

## What is NOT a finding (the critic will cut these, so do not send them)
- Style, naming, formatting, type-hint coverage, docstring absence.
- "Could be refactored", "consider extracting", "this file is long".
- Speculative performance concerns with no measured impact. This app runs at 60 Hz
  on one PC; a list comprehension is not a defect.
- Anything you have not read the surrounding code for. Do not guess at a caller's
  behaviour — go read the caller.
- Missing test coverage *on its own*. Untested code is only a finding if you can
  also show the code is wrong.

## How to verify before you report
For every candidate finding you MUST:
- Read the function, its callers, and its callees. Trace where the value ends up.
- Confirm the bad path is actually reachable with real data. If a guard upstream
  makes it impossible, it is not a finding — say so and drop it.
- Check the tests: if a test asserts the behaviour you think is wrong, work out
  whether the test encodes the bug or you have misread the intent.
- State the concrete trigger: what input, what state, what the user sees.

## Output format — return exactly this, nothing else
A JSON array. No prose before or after. Each element:

{
  "severity": "P1" | "P2" | "P3",
  "file": "pitcrew/....py",
  "line": <int>,
  "title": "<one line, the defect itself>",
  "what_is_wrong": "<2-4 sentences, mechanical, no hedging>",
  "trigger": "<concrete inputs/state that reach it, and what the driver sees>",
  "evidence": "<the actual code lines, quoted, plus the caller you traced>",
  "rule": "<CLAUDE.md/EXPORT-CONTRACT.md clause it breaks, if any>",
  "fix": "<the specific change, not a direction>",
  "confidence": "certain" | "high" | "medium"
}

Severity: P1 = wrong number the driver acts on, crash on a normal path, or contract
violation that corrupts an export. P2 = wrong under a reachable but less common
state, or a standing-rule violation with limited blast radius. P3 = real but minor.

If your area is clean, return `[]`. An empty array is a respectable result and is
far better than padding. Do not invent findings to look thorough.
