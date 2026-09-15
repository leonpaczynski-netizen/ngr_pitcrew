"""The figures every plan from the desk must carry, for tests of other things.

Since 16 Sep 2026 the desk's doors refuse a plan without a target lap time
per compound and a burn per lap (`strategy.targets.desk_target_problems`). A
test about the playbook, the context or the stored row is not a test of that,
so its plan is given the figures here rather than each file restating them.
"""
from __future__ import annotations

LAP_TIME_MS = 90_000
SAVE_LAP_TIME_MS = 90_600
BURN_FULL_L = 4.8
BURN_SAVE_L = 4.0


def with_desk_figures(plan: dict) -> dict:
    """`plan` with a lap target for every compound its stints name, and the
    burn per lap. An author's own figures are left as they are."""
    out = dict(plan)
    stints = [s for s in (out.get("stints") or []) if isinstance(s, dict)]
    saving = any(s.get("fuel_save") is True for s in stints)
    burns = dict(out.get("fuel_burns") or {})
    burns.setdefault("full", BURN_FULL_L)
    if saving:
        burns.setdefault("save", BURN_SAVE_L)
    out["fuel_burns"] = burns
    targets = dict(out.get("targets") or {})
    compounds = {code: dict(entry) for code, entry in
                 (targets.get("compounds") or {}).items()}
    for stint in stints:
        code = stint.get("compound")
        if not isinstance(code, str) or not code:
            continue
        entry = compounds.setdefault(code, {})
        entry.setdefault("lap_time_ms", LAP_TIME_MS)
        if stint.get("fuel_save") is True:
            entry.setdefault("save_lap_time_ms", SAVE_LAP_TIME_MS)
    targets["compounds"] = compounds
    out["targets"] = targets
    return out
