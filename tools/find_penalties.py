"""Which laps of a session served a track-limit penalty, off the frames.

    python tools/find_penalties.py --session 121

Read-only. Prints every brake at speed on a straight outside the circuit's
corner approaches, with the derived time lost. Written 7 Sep 2026 against the
Daytona A/B runs of 4 Sep, where six such laps went unflagged.

**It applies the same gates the live app applies** - a wet event stands the
detector down, a pit lap, an out lap and lap one are not read, and
`RoadNotPenalty` withdraws a place braked on four consecutive laps. Without
them the tool and the app report different things about the same session and
neither can be checked against the other. `--raw` is the detector alone.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pitcrew.analysis.penalties import (WET_WORDS, RoadNotPenalty, braked_at,
                                        read_rows)
from pitcrew.analysis.resolve import circuit_key
from pitcrew.store.db import Store


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--session", type=int, required=True)
    ap.add_argument("--raw", action="store_true",
                    help="what the detector alone reads, with none of the "
                         "gates the live app applies (wet event, pit/out/lap "
                         "one, the missing-corner ledger)")
    args = ap.parse_args()
    store = Store()
    try:
        session = store._query("SELECT * FROM sessions WHERE id = ?",
                               (args.session,))
        if not session:
            print(f"no session {args.session}")
            return 1
        event = store.get_event(session[0]["event_id"])
        key = circuit_key(event["track"], event["layout"])
        model = store._query(
            "SELECT corners_json FROM corner_models WHERE circuit_key = ?",
            (key,))
        corners = (json.loads(model[0]["corners_json"]).get("corners")
                   if model else [])
        if not corners:
            print(f"no corner model for {key} - every brake would look "
                  f"like a penalty; refusing")
            return 1
        print(f"session {args.session} at {key}: "
              f"{len(corners)} corners in the model")
        weather = (event["weather"] or "").strip().lower()
        if any(word in weather for word in WET_WORDS) and not args.raw:
            print(f"the event declares '{weather}' - the live app stands the "
                  f"detector down here (no wet calibration frame). --raw "
                  f"reads it anyway.")
            return 1
        by_lap = {}
        ledger = RoadNotPenalty()
        for lap in store._query(
                "SELECT id, lap_num, lap_time_ms, is_pit_lap, is_out_lap "
                "FROM laps WHERE session_id = ? ORDER BY lap_num",
                (args.session,)):
            # **The same three gates the live app applies**, or the tool and
            # the app disagree about the same session and neither is checkable
            # against the other. `--raw` shows what the detector alone reads.
            skip = (not args.raw
                    and (lap["is_pit_lap"] or lap["is_out_lap"]
                         or lap["lap_num"] <= 1))
            frames = (store.get_lap_frames(lap["id"]) or {}).get("frames") or []
            served = None if skip else read_rows(frames, corners)
            if served is None:
                print(f"  lap {lap['lap_num']:>2}: "
                      f"{'not read (pit, out or lap one)' if skip else 'no frames'}")
                continue
            verdict = (ledger.filter(lap["lap_num"], served,
                                     braked_at(frames))
                       if not args.raw else None)
            for note in (verdict.notes if verdict else ()):
                print(f"    {note}")
            for gone in (verdict.give_back if verdict else ()):
                by_lap[gone.lap] = gone.served
                print(f"    lap {gone.lap}: WITHDRAWN - {gone.served} "
                      f"still stand(s)")
            standing = verdict.kept if verdict else served
            by_lap[lap["lap_num"]] = len(standing)
            for p in standing:
                print(f"  lap {lap['lap_num']:>2}: penalty at {p.at_m:.0f} m - "
                      f"{p.speed_from_kph:.0f} -> {p.speed_to_kph:.0f} km/h over "
                      f"{p.brake_s:.1f} s, about {p.lost_s:.1f} s lost (derived)")
        found = sum(by_lap.values())
        print(f"{found} penalt{'y' if found == 1 else 'ies'} served")
        if not args.raw and ledger.retired():
            print("corners the model is missing (nothing here was counted): "
                  + ", ".join(f"{p:.0f} m" for p in ledger.retired()))
        return 0
    finally:
        store.close()


if __name__ == "__main__":
    sys.exit(main())
