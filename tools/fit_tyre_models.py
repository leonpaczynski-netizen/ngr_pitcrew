"""Fit the tyre model from stored grip observations, and say what it cannot fit.

    python tools/fit_tyre_models.py                 # report, change nothing
    python tools/fit_tyre_models.py --apply         # write tyre_models
    python tools/fit_tyre_models.py --gates         # just the staged gates
    python tools/fit_tyre_models.py --db path

Run `tools/derive_grip_observations.py --apply` first; this reads the rows it
wrote and never touches a frame.

**The half of the output that matters most is the "not yet" list.** A fitting
report that only prints coefficients leaves every gap looking like a clean bill
of health, and this app's own degradation memo is the record of silence being
read as "all clear". Every scope prints what it may say, what it may not, and
which sample count is standing in the way.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pitcrew.analysis.grip import DERIVATION_VERSION            # noqa: E402
from pitcrew.analysis.tyre_model import (                       # noqa: E402
    STAGE0_LINE,
    fit_archive,
    priors_for_scope,
)
from pitcrew.store.db import DEFAULT_DB_PATH, Store             # noqa: E402


def _number(value, places: int = 4) -> str:
    """Format, or say `null`. **Never print a missing value as 0.**"""
    if value is None:
        return "null"
    return f"{value:.{places}f}"


def _print_ordering(orderings: list[dict]) -> None:
    if not orderings:
        return
    print("\n== compound ordering (the observable's own validation) ==")
    for row in orderings:
        levels = "  ".join(
            f"{lv['compound']} {_number(lv['mean_grip_g'])} (n={lv['n']})"
            for lv in row["levels"])
        print(f"  {row['circuit_key']} / {row['car_key']} "
              f"[{row['yaw_source']}]")
        print(f"    {levels}")
        print(f"    monotone in softness: {row['monotone_in_softness']}, "
              f"softest-hardest {_number(row['softest_minus_hardest_pct'], 2)} %, "
              f"Welch t {_number(row['welch_t'], 2)}")
        print(f"    caveat: {row['caveat']}")


def _print_scope(scope, evidence, models: list[dict]) -> None:
    print(f"\n== {scope.label()} ==")
    print(f"  {evidence.samples} push laps, {evidence.sessions} session(s), "
          f"{evidence.stint_count} stint(s), "
          f"{len(evidence.contributing_stints)} contributing "
          f"({evidence.contributing_laps} laps)")
    for model in models:
        body = model["model"]
        gate = model["gate"]
        mark = "SPEAKABLE" if model["speakable"] else "silent"
        print(f"  {model['model_kind']:<21} {mark:<10} "
              f"confidence {model['confidence']}")
        if model["model_kind"] == "baseline":
            print(f"    mean {_number(body['mean_grip_g'])} g, "
                  f"CV {_number(body['cv_pct'], 2)} %, n {body['n']}")
        elif model["model_kind"] == "degradation":
            between = body.get("between_stint") or {}
            print(f"    {_number(body['grip_g_per_lap'], 5)} g/lap, "
                  f"se {_number(body['se'], 5)}, t {_number(body['t'], 2)} on "
                  f"{body.get('dof')} df, p {_number(body.get('p'), 4)} "
                  f"[{body.get('estimator')}]")
            pooled = body.get("pooled_within_stint") or {}
            print(f"      per-stint signs {between.get('signs') or 'n/a'}; "
                  f"within-stint pooled t {_number(pooled.get('t'), 2)} "
                  f"(reported, never gated on)")
            for key, per in sorted(body["per_stint"].items()):
                print(f"      stint {key}: "
                      f"{_number(per['slope_g_per_lap'], 5)} g/lap, "
                      f"t {_number(per['t'], 2)}, {per['laps']} laps")
        elif model["model_kind"] == "temperature-response":
            print(f"    {_number(body['grip_g_per_c'], 5)} g/degC, "
                  f"t {_number(body['t'], 2)}, "
                  f"settled laps {body['settled_laps']}, "
                  f"span {_number(body['settled_temp_span_c'], 1)} degC")
        elif model["model_kind"] == "warmup":
            print(f"    {body['warmup_sequences']} warm-up sequence(s), "
                  f"laps each {body['laps_each']}")
        if not model["speakable"]:
            for why in gate.get("failures", ()):
                print(f"      not yet: {why}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DEFAULT_DB_PATH))
    parser.add_argument("--apply", action="store_true",
                        help="write the fitted models; without it, report only")
    parser.add_argument("--gates", action="store_true",
                        help="print only the staged gates and what blocks them")
    parser.add_argument("--derivation-version", type=int,
                        default=DERIVATION_VERSION)
    args = parser.parse_args()

    store = Store(args.db)
    rows = store.list_grip_observations(
        derivation_version=args.derivation_version, unit_kind="LAP")
    if not rows:
        print(f"No grip observations at derivation version "
              f"{args.derivation_version}. Run "
              f"tools/derive_grip_observations.py --apply first.")
        return 1

    multipliers = {}
    versions = set()
    for event in store.list_events():
        from pitcrew.analysis.grip import event_circuit_key
        multipliers[event_circuit_key(event)] = event.get("tyre_wear_mult")
        if event.get("game_version"):
            versions.add(event["game_version"])

    result = fit_archive(rows, derivation_version=args.derivation_version,
                         game_version=", ".join(sorted(versions)) or None,
                         wear_multipliers=multipliers)
    scopes = result["scopes"]

    if not args.gates:
        by_scope: dict = {}
        for model in result["models"]:
            key = (model["car_key"], model["circuit_key"], model["compound"],
                   model["yaw_source"])
            by_scope.setdefault(key, []).append(model)
        for scope, evidence in sorted(scopes.items(),
                                      key=lambda kv: kv[0].label()):
            key = (scope.car_key, scope.circuit_key, scope.compound,
                   scope.yaw_source)
            _print_scope(scope, evidence, by_scope.get(key, []))
        _print_ordering(result["compound_ordering"])
        print("\n== lap-to-lap noise, consecutive-lap differences ==")
        for circuit, noise in result["noise_by_circuit"].items():
            print(f"  {circuit}: CV {_number(noise['cv_pct'], 2)} %, "
                  f"sigma {_number(noise['sigma_g'], 4)} g, "
                  f"{noise['laps']} laps over {noise['stints']} stint(s)")

    print("\n== what the model may not yet say ==")
    print(f"  every scope below falls back to: {STAGE0_LINE}")
    for entry in result["not_yet_supported"]:
        print(f"\n  {entry['scope']}")
        print(f"    open stages: {entry['open_stages'] or 'none beyond 0'}")
        for blocked in entry["blocked"]:
            print(f"    stage {blocked['stage']} ({blocked['name']}) blocked:")
            for why in blocked["why"]:
                print(f"      - {why}")

    print("\n== the priors, as carried, not as believed ==")
    seen: set[str] = set()
    for scope in sorted(scopes, key=lambda s: s.label()):
        key = f"{scope.circuit_key}/{scope.car_key}"
        if key in seen:
            continue
        seen.add(key)
        print(f"  {key}")
        for prior in priors_for_scope(scope):
            print(f"    {prior['id']}: {prior['status']}, in scope: "
                  f"{prior['in_scope']}, speakable here: "
                  f"{prior['speakable_here']}")
            for blocker in prior["blockers"]:
                print(f"      blocked: {blocker}")

    if not args.apply:
        print("\nNothing written. Re-run with --apply.")
        return 0

    dropped = store.clear_tyre_models(args.derivation_version)
    for model in result["models"]:
        store.save_tyre_model(model)
    print(f"\n{len(result['models'])} model(s) written to {args.db}"
          + (f", replacing {dropped} from the previous run." if dropped
             else "."))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
