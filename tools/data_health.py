"""What may honestly be claimed about one car at one circuit, before claiming it.

**A prose checklist would produce four slightly different ad-hoc queries every
time it was followed** — which is the failure it was meant to prevent, generated
fresh. This is the check as one command with one output.

It answers the questions that decide whether an analysis is possible at all:

* **Corner identity.** A per-corner claim needs corners that mean the same thing
  across sessions. Monza has none - `identity_stable` is 0 on every one of its
  observations - so no per-corner claim is available there at any sample size.
* **Is the grip archive keyed to the corner model that is actually stored?** A
  re-anchored model leaves every earlier observation pointing at corners that
  have since moved, and the symptom is quiet: an export and a grip row disagree
  by about one corner id.
* **Does the sheet the app holds match the gearbox the car actually ran?**
  `laps.gear_ratios` is decoded from the packet and copied from no sheet, which
  makes it the only independent witness to what was in the car - and it caught a
  session tagged one circuit's sheet while running another's gearbox.
* **What the fitted tyre model may say, and why it may not say more.**

**The `speakable` distinction this tool exists to draw.** A stage that cannot
speak may be blocked by evidence - not enough stints, not enough settled laps -
or by a gate that was never implemented. Two of them return "not met"
unconditionally with their parameters unused. Reporting an unimplemented gate as
an evidence conclusion is CLAUDE.md rule 3 violated at the doctrine layer: a
missing thing presented as a measured one. They are labelled separately here.

    python tools/data_health.py --car "Lamborghini Huracan GT3 '15" \\
                                --circuit fuji-international-speedway-full-course
    python tools/data_health.py --event 6      # resolve both from the event

Read-only. Nothing here writes.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pitcrew.store.db import Store  # noqa: E402

# Stages whose gate is a literal `met=False` with its parameters unused, rather
# than a verdict on evidence. Keep this list beside the code it describes: when
# one is implemented, a silent "not met" here becomes a real finding and the
# tool must stop calling it a stub.
UNIMPLEMENTED_STAGES = {3, 5}


def _rows(store, sql, params=()):
    return store._query(sql, params)


def corner_identity(store, circuit_key: str) -> str:
    rows = _rows(store,
                 "SELECT identity_stable, COUNT(*) n FROM grip_observations "
                 "WHERE circuit_key = ? AND unit_kind != 'LAP' "
                 "GROUP BY identity_stable", (circuit_key,))
    total = sum(r["n"] for r in rows)
    stable = sum(r["n"] for r in rows if r["identity_stable"])
    if not total:
        return "  corners        no corner observations - nothing to claim"
    if not stable:
        return (f"  corners        ** NONE STABLE ** 0 of {total} - no "
                f"per-corner claim is available at this circuit")
    return (f"  corners        {stable} of {total} stable "
            f"({stable / total:.0%})")


def model_version(store, circuit_key: str) -> str:
    stored = _rows(store, "SELECT version FROM corner_models "
                          "WHERE circuit_key = ?", (circuit_key,))
    if not stored:
        return "  corner model   none stored - corners cannot be named"
    want = stored[0]["version"]
    used = _rows(store,
                 "SELECT DISTINCT corner_model_version v FROM grip_observations "
                 "WHERE circuit_key = ? AND corner_model_version IS NOT NULL",
                 (circuit_key,))
    seen = sorted(r["v"] for r in used)
    if not seen:
        return f"  corner model   stored v{want}; no observations derived yet"
    if seen == [want]:
        return f"  corner model   v{want}, and the archive agrees"
    return (f"  corner model   ** STALE ** stored v{want}, archive holds "
            f"v{', v'.join(str(s) for s in seen)} - re-derive before trusting "
            f"any corner claim here")


def sheet_vs_gearbox(store, car_name: str, circuit_key: str) -> list[str]:
    """Did each session actually run the gearbox its sheet describes?

    The one setup value with an independent witness. Everything else on a sheet
    is taken on trust, which is why this one is worth checking every time.
    """
    from pitcrew.analysis.gearing import matches_sheet

    out: list[str] = []
    sessions = _rows(
        store,
        "SELECT s.id, s.kind, s.setup_sheet_id, sh.sheet_name "
        "FROM sessions s JOIN events e ON e.id = s.event_id "
        "LEFT JOIN setup_sheets sh ON sh.id = s.setup_sheet_id "
        "WHERE e.car_name = ? AND sh.circuit_key = ? ORDER BY s.id",
        (car_name, circuit_key))
    for row in sessions:
        sheet = (store.get_setup_sheet(row["setup_sheet_id"])
                 if row["setup_sheet_id"] else None)
        if sheet is None or not sheet.gears:
            continue
        laps = store.list_laps(row["id"])
        verdict = matches_sheet(laps, sheet.gears)
        if verdict is False:
            out.append(f"  ** session {row['id']} ({row['kind']}) is tagged "
                       f"{row['sheet_name']!r} but ran a different gearbox")
    return out or ["  gearbox        every session ran the sheet it is tagged "
                   "with"]


def tyre_verdicts(store, car_key: str, circuit_key: str) -> list[str]:
    """What the fitted model may say here, and what is blocking the rest."""
    rows = _rows(store,
                 "SELECT compound, model_kind, confidence, speakable, "
                 "samples, game_version FROM tyre_models "
                 "WHERE car_key = ? AND circuit_key = ? "
                 "ORDER BY compound, model_kind", (car_key, circuit_key))
    if not rows:
        return ["  tyres          no fitted model - run "
                "tools/fit_tyre_models.py --gates to see why"]
    out = []
    for r in rows:
        mark = "SPEAKABLE" if r["speakable"] else "silent   "
        out.append(f"  tyres          {mark} {r['compound'] or '--':<3} "
                   f"{r['model_kind']:<21} n={r['samples']:<4} "
                   f"{r['confidence']:<7} v{r['game_version']}")
    return out


def stage_blockers(car_key: str, circuit_key: str, compound: str) -> list[str]:
    """Why each stage is silent - and whether the reason is evidence or a stub.

    **This is the distinction the whole tool exists for.** A stage blocked by
    sample size is a finding: run more laps and it speaks. A stage blocked by an
    unimplemented gate is a TODO wearing a finding's clothes, and reporting it
    as evidence is a missing thing presented as a measured one.
    """
    from pitcrew.analysis import tyre_model
    from pitcrew.store.db import Store as _Store

    out = []
    store = _Store()
    try:
        for stage in (1, 2, 3, 4, 5):
            try:
                verdict = tyre_model.may_i_say(
                    store, stage=stage, car_key=car_key,
                    circuit_key=circuit_key, compound=compound,
                    yaw_source="packet-angvel-y")
            except Exception as exc:                     # noqa: BLE001
                out.append(f"  stage {stage}        could not be read: {exc}")
                continue
            if verdict.get("may_say"):
                out.append(f"  stage {stage}        may speak")
            elif stage in UNIMPLEMENTED_STAGES:
                out.append(f"  stage {stage}        ** NOT IMPLEMENTED ** - "
                           f"this is a stub, not a verdict on evidence")
            else:
                why = verdict.get("blocked") or verdict.get("why") or "silent"
                if isinstance(why, (list, tuple)):
                    why = "; ".join(str(w) for w in why)
                out.append(f"  stage {stage}        blocked by evidence: {why}")
    finally:
        store.close()
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--car")
    ap.add_argument("--circuit")
    ap.add_argument("--event", type=int)
    ap.add_argument("--compound", default="RS")
    args = ap.parse_args()

    store = Store()
    try:
        car, circuit = args.car, args.circuit
        if args.event:
            rows = _rows(store, "SELECT car_name FROM events WHERE id = ?",
                         (args.event,))
            if rows:
                car = car or rows[0]["car_name"]
            sheets = _rows(
                store,
                "SELECT DISTINCT sh.circuit_key FROM sessions s "
                "JOIN setup_sheets sh ON sh.id = s.setup_sheet_id "
                "WHERE s.event_id = ? AND sh.circuit_key IS NOT NULL",
                (args.event,))
            if sheets:
                circuit = circuit or sheets[0]["circuit_key"]
        if not (car and circuit):
            print("need --car and --circuit, or an --event that resolves both")
            return 2

        car_key = _rows(store, "SELECT DISTINCT car_key FROM grip_observations "
                               "WHERE circuit_key = ? LIMIT 1", (circuit,))
        car_key = car_key[0]["car_key"] if car_key else None

        print(f"\n{car}")
        print(f"{circuit}\n")
        print(corner_identity(store, circuit))
        print(model_version(store, circuit))
        for line in sheet_vs_gearbox(store, car, circuit):
            print(line)
        if car_key:
            for line in tyre_verdicts(store, car_key, circuit):
                print(line)
            print()
            for line in stage_blockers(car_key, circuit, args.compound):
                print(line)
        print()
        return 0
    finally:
        store.close()


if __name__ == "__main__":
    raise SystemExit(main())
