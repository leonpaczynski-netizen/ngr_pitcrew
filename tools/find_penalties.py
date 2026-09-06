"""Which laps of a session served a track-limit penalty, off the frames.

    python tools/find_penalties.py --session 121

Read-only. Prints every brake at speed on a straight outside the circuit's
corner approaches, with the derived time lost. Written 7 Sep 2026 against the
Daytona A/B runs of 4 Sep, where six such laps went unflagged.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pitcrew.analysis.penalties import read_rows
from pitcrew.analysis.resolve import circuit_key
from pitcrew.store.db import Store


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--session", type=int, required=True)
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
        found = 0
        for lap in store._query(
                "SELECT id, lap_num, lap_time_ms FROM laps WHERE session_id = ? "
                "ORDER BY lap_num", (args.session,)):
            frames = (store.get_lap_frames(lap["id"]) or {}).get("frames") or []
            served = read_rows(frames, corners)
            if served is None:
                print(f"  lap {lap['lap_num']:>2}: no frames")
                continue
            for p in served:
                found += 1
                print(f"  lap {lap['lap_num']:>2}: penalty at {p.at_m:.0f} m - "
                      f"{p.speed_from_kph:.0f} -> {p.speed_to_kph:.0f} km/h over "
                      f"{p.brake_s:.1f} s, about {p.lost_s:.1f} s lost (derived)")
        print(f"{found} penalt{'y' if found == 1 else 'ies'} served")
        return 0
    finally:
        store.close()


if __name__ == "__main__":
    sys.exit(main())
