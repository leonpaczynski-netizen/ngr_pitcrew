"""Pure view-model for the Bench UAT runner surface (Qt-free, Program 2, Phase 70).

Turns a ``BenchUatReport`` payload dict into a glanceable developer/UAT display: an overall readiness
banner, a totals summary, per-category counts, and the explicit failure details. A bench FAILURE is never
hidden behind a warning. It states plainly that bench success is SOFTWARE behaviour only — never physical,
PSVR2 or live-GT7 certification. Display strings only; never raises.
"""
from __future__ import annotations

from typing import List


def build(result=None) -> dict:
    return result if isinstance(result, dict) else {}


def is_empty(result) -> bool:
    return not build(result).get("results") and not build(result).get("total")


def header_text(result) -> str:
    r = build(result)
    if is_empty(result):
        return ("No bench run yet. Bench UAT exercises the REAL production live path with deterministic "
                "OFFLINE scenarios. It sends no network, keyboard, joystick or microphone input and "
                "certifies no physical hardware. Click Run to execute.")
    ready = bool(r.get("overall_bench_ready"))
    return (f"[{'BENCH READY' if ready else 'BENCH NOT READY'}]  "
            f"{r.get('passed', 0)}/{r.get('total', 0)} passed  ·  {r.get('failed', 0)} failed  ·  "
            f"{r.get('blocked', 0)} blocked  ·  {r.get('safety_failures', 0)} safety")


def banner_tone(result) -> str:
    if is_empty(result):
        return "advisory"
    r = build(result)
    if r.get("failed") or r.get("blocked") or r.get("safety_failures"):
        return "warn"
    return "success" if r.get("overall_bench_ready") else "neutral"


def summary_rows(result) -> List[dict]:
    r = build(result)
    if is_empty(result):
        return []
    return [
        {"label": "Total scenarios", "value": str(r.get("total", 0))},
        {"label": "Passed", "value": str(r.get("passed", 0))},
        {"label": "Failed", "value": str(r.get("failed", 0))},
        {"label": "Blocked", "value": str(r.get("blocked", 0))},
        {"label": "Safety failures", "value": str(r.get("safety_failures", 0))},
        {"label": "Strategy failures", "value": str(r.get("strategy_failures", 0))},
        {"label": "Audio/PTT failures", "value": str(r.get("audio_ptt_failures", 0))},
        {"label": "Certification-integrity failures",
         "value": str(r.get("certification_integrity_failures", 0))},
    ]


def category_counts(result) -> List[dict]:
    r = build(result)
    counts: dict = {}
    for res in (r.get("results") or []):
        cat = str(res.get("category") or "?")
        c = counts.setdefault(cat, {"pass": 0, "fail": 0})
        if res.get("passed"):
            c["pass"] += 1
        else:
            c["fail"] += 1
    rows = []
    for cat in sorted(counts):
        c = counts[cat]
        rows.append({"category": cat.replace("_", " "), "pass": c["pass"], "fail": c["fail"],
                     "tone": "success" if c["fail"] == 0 else "warn"})
    return rows


def failure_lines(result) -> List[str]:
    r = build(result)
    details = r.get("failure_details") or []
    if not details:
        return ["No bench failures."]
    return [f"[FAIL] {d}" for d in details]


def note_text(result) -> str:
    r = build(result)
    return str(r.get("note") or
               "Bench success is software behaviour only — not physical/PSVR2/live-GT7 certification.")
