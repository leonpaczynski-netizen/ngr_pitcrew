"""Extract one whole recorded race from the store as a test fixture.

    python tools/build_race_fixture.py --session 49

**CLAUDE.md §7 asks for a recorded session as *the* fixture, and there was one
lap.** `watkins_glen_lap.bin` is 6,211 frames of a single Huracan lap and it
has already earned its place - it is what caught a channel holding the roll
rate under the name `yaw_rate`, and a slip ratio 2*pi too large. But one lap
cannot exercise anything that spans a race: a stint, a pit stop, a tyre change,
a wear rate, the distance anchor's refusal of a lap that swallowed a crossing.

Those are exactly the things `docs/ENGINEER-TARGET-STATE_2026-08-29.md` is
about to change. E measures wear off a replay and carries the rate forward;
H1 anchors lap distance to the circuit. **Neither can be shown to be an
improvement against synthetic laps**, because the fault each one repairs only
appears in real driving.

### What it writes

A zip, one entry per lap plus a `manifest.json`, at
`pitcrew/tests/fixtures/<name>.zip`. Zip rather than a bare concatenation so
the thing can be opened and looked at, and because a lap has to be findable by
number without decoding the ones before it.

The blobs are copied byte for byte out of `lap_frames`, exactly as the recorder
wrote them. **Not re-encoded**: a fixture that has been through this app's own
encoder tests the encoder against itself, and the point of a real capture is
that nothing in the suite chose what is in it.

### What it deliberately does not carry

**The replay video.** It is gigabytes, it is not the app's to redistribute, and
runtime data files are never committed. The manifest records its path and its
offset so the wear and traffic passes can be pointed at it on this machine;
without it those tests skip rather than fail, and say which.
"""
from __future__ import annotations

import argparse
import json
import sys
import zipfile

from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from pitcrew.store.db import Store                           # noqa: E402
from pitcrew.analysis.resolve import circuit_key             # noqa: E402

FIXTURES = REPO / "pitcrew" / "tests" / "fixtures"


def build(session_id: int, name: str | None = None) -> Path:
    store = Store()
    try:
        session = store.get_session(session_id)
        if session is None:
            raise SystemExit(f"no session {session_id}")
        event = store.get_event(session["event_id"])
        laps = store.list_laps(session_id)
        if not laps:
            raise SystemExit(f"session {session_id} has no laps")

        key = circuit_key(event["track"], event.get("layout"))
        target = FIXTURES / f"{name or f'{key}-race'}.zip"
        FIXTURES.mkdir(parents=True, exist_ok=True)

        manifest = {
            "sessionId": session_id,
            "kind": session["kind"],
            "car": event["car_name"],
            "track": event["track"],
            "layout": event.get("layout"),
            "circuitKey": key,
            "raceType": event.get("race_type"),
            "raceLaps": event.get("race_laps"),
            "tyreWearMult": event.get("tyre_wear_mult"),
            "fuelMult": event.get("fuel_mult"),
            "gameVersion": session.get("game_version"),
            "packetFormat": session.get("packet_format"),
            "wheelbaseM": session.get("wheelbase_m"),
            # Recorded, never shipped. See the module docstring.
            "videoPath": session.get("video_path"),
            "videoStartedAt": session.get("video_started_at"),
            "laps": [],
        }

        with zipfile.ZipFile(target, "w", zipfile.ZIP_STORED) as bundle:
            for row in laps:
                stored = store.get_lap_frames(row["id"])
                entry = {
                    "lapNum": row["lap_num"],
                    "lapTimeMs": row["lap_time_ms"],
                    "fuelStart": row["fuel_start"],
                    "fuelEnd": row["fuel_end"],
                    "compound": row["compound"],
                    "position": row["position"],
                    "isPitLap": bool(row["is_pit_lap"]),
                    "isOutLap": bool(row["is_out_lap"]),
                    "excluded": bool(row["excluded"]),
                    "blob": None,
                }
                blob = _raw_blob(store, row["id"])
                if blob is not None:
                    entry["blob"] = f"laps/{row['lap_num']:03d}.bin"
                    entry["sampleHz"] = stored["sample_hz"] if stored else None
                    entry["frameCount"] = (stored["frame_count"]
                                           if stored else None)
                    bundle.writestr(entry["blob"], blob)
                manifest["laps"].append(entry)
            bundle.writestr("manifest.json",
                            json.dumps(manifest, indent=2, sort_keys=True))
        return target
    finally:
        store.close()


def _raw_blob(store, lap_id: int):
    """The blob exactly as the recorder wrote it, never re-encoded."""
    rows = store._query("SELECT blob FROM lap_frames WHERE lap_id = ?",
                        (lap_id,))
    return rows[0]["blob"] if rows else None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session", type=int, required=True)
    parser.add_argument("--name", default=None)
    args = parser.parse_args()
    target = build(args.session, args.name)
    size = target.stat().st_size / 1e6
    print(f"wrote {target.relative_to(REPO)} ({size:.1f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
