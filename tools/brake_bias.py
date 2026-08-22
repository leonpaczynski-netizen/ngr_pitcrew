"""What brake balance actually does, measured off the wheels rather than felt.

    python tools/brake_bias.py --event 1
    python tools/brake_bias.py --session 61 --bias -5
    python tools/brake_bias.py --event 1 --trail

**GT7 sends no brake-bias channel.** The value is a delta from each car's own
factory bias, set on the sheet and adjustable live on the MFD, and nothing in
any packet format reports it. So the bias itself has to be DECLARED - like the
compound - and what this tool measures is its *effect*.

### The instrument, and why it beats driving impressions

`telemetry/recorder` already stores, every frame, `slip_fl/fr/rl/rr`: wheel
surface speed divided by car speed. 1.0 is rolling true, below 1.0 is locking.
**Under braking, which axle goes lower - and by how much - is the bias
signature, directly.**

Three reasons that is the right instrument here:

* **It is immune to the hardware confound.** 1.71 changed force feedback,
  understeer vibration and the Fanatec auto-setup parameters at the same time
  as it changed ABS. On an 18 Nm direct drive that reads exactly like a braking
  change, and no amount of careful driving separates the two. A wheel-speed
  ratio does not care how the rim feels.
* **It has the sample count.** A braking event is a few hundred frames at
  60 Hz. Per-corner lap metrics - minimum speed, brake point - were measured on
  22 Aug over 307 laps and are far too noisy to resolve a click of bias:
  2 sd of 9-11 km/h on minimum speed and 14-37 m on brake point.
* **It answers the sign question objectively.** The knowledge base records
  negative = front as settled, and offers a 60-second in-game check. This is
  that check, without the observing.

### What it will not tell you

**Not the bias value.** It reads the effect, and the mapping from effect back
to value is what a declared-bias run establishes. Once several runs at known
biases exist, the front-minus-rear slip difference could be inverted to read
the value back - which is the thing that would let the app confirm a mid-race
MFD change actually landed. That is a hypothesis this tool exists to test, not
a claim it makes.

**Nothing about laps recorded before the slip repair.** `slip_*` was 2pi too
large in v1 blobs - `lockup` fired on 0.2% of braking frames when the real
figure was an 86.5% lock - and `Store.get_lap_frames` repairs those on read.
The repaired values are honest, but a v1 lap is flagged in the output anyway,
because a channel that had to be reconstructed is not the same evidence as one
that was recorded correctly.
"""
from __future__ import annotations

import argparse
import statistics as st
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pitcrew.store.db import Store                           # noqa: E402

# A braking event starts here. Well above the pedal noise of a trail-brake
# release and well below the pressure of a real stop.
BRAKE_ON_PCT = 40.0
# ...and ends when the pedal comes off this far.
BRAKE_OFF_PCT = 10.0
# Shorter than this is a dab, a correction or a downshift stab, not a stop.
MIN_EVENT_FRAMES = 20
# Below this the slip ratio is arithmetic on a divisor that means nothing -
# the same floor `recorder._slip_ratios` applies before it stores one at all.
MIN_SPEED_KPH = 30.0
# **The trail-brake window.** Brake still applied with real lock on, which is
# the phase 1.71's "cornering brake behaviour" note names directly and the
# phase this driver's whole technique lives in.
TRAIL_STEER_NORM = 0.15
TRAIL_MIN_BRAKE_PCT = 5.0
# Fewer braking events than this in one session and its mean split
# describes a handful of stops rather than the session.
MIN_SESSION_STOPS = 8


@dataclass(frozen=True)
class Stop:
    """One braking event, reduced to the numbers bias moves."""

    lap_id: int
    lap_num: int
    frames: int
    entry_kph: float
    exit_kph: float
    # The lowest the axle got. Below 1.0 is locking; the LOWER axle is the one
    # carrying more brake than its grip supports, which is the bias signature.
    front_min_slip: float | None
    rear_min_slip: float | None
    # Mean deceleration over the event, in g. Stopping performance.
    decel_g: float
    schema_version: int

    @property
    def split(self) -> float | None:
        """Front minus rear minimum slip.

        **Negative means the FRONT locked deeper**, which on the settled
        convention is what front bias does. Positive means the rear did.
        """
        if self.front_min_slip is None or self.rear_min_slip is None:
            return None
        return self.front_min_slip - self.rear_min_slip


def _mean(values):
    present = [v for v in values if v is not None]
    return st.mean(present) if present else None


def _min(values):
    present = [v for v in values if v is not None]
    return min(present) if present else None


def find_stops(frames: list[dict], *, lap_id: int, lap_num: int,
               schema_version: int, sample_hz: float) -> list[Stop]:
    """Every real braking event in one lap."""
    out: list[Stop] = []
    run: list[dict] = []
    for frame in frames:
        brake = frame.get("brake_pct")
        speed = frame.get("speed_kph")
        if brake is None or speed is None:
            continue
        if brake >= BRAKE_ON_PCT and speed >= MIN_SPEED_KPH:
            run.append(frame)
            continue
        if run and brake <= BRAKE_OFF_PCT:
            stop = _measure(run, lap_id, lap_num, schema_version, sample_hz)
            if stop is not None:
                out.append(stop)
            run = []
    stop = _measure(run, lap_id, lap_num, schema_version, sample_hz)
    if stop is not None:
        out.append(stop)
    return out


def _measure(run: list[dict], lap_id: int, lap_num: int,
             schema_version: int, sample_hz: float) -> Stop | None:
    if len(run) < MIN_EVENT_FRAMES:
        return None
    speeds = [f["speed_kph"] for f in run]
    seconds = len(run) / sample_hz
    # **Mean, not peak.** A peak is one frame and one frame of a 60 Hz stream
    # is where every decode artefact lives; the whole event is the measurement.
    decel_g = ((speeds[0] - speeds[-1]) / 3.6) / seconds / 9.81
    return Stop(
        lap_id=lap_id, lap_num=lap_num, frames=len(run),
        entry_kph=speeds[0], exit_kph=speeds[-1],
        front_min_slip=_min([_mean((f.get("slip_fl"), f.get("slip_fr")))
                             for f in run]),
        rear_min_slip=_min([_mean((f.get("slip_rl"), f.get("slip_rr")))
                            for f in run]),
        decel_g=decel_g, schema_version=schema_version)


def trail_slip(frames: list[dict]) -> tuple[float | None, float | None, int]:
    """Mean front and rear slip through the trail-braking phase, and its size.

    **Per frame, not per corner**, and that is the point. A three-lap A/B on
    corner minimum speed cannot resolve a click of bias - 2 sd is 9-11 km/h -
    where one lap of trail-braking frames gives hundreds of samples of the
    quantity bias actually moves.
    """
    fronts, rears = [], []
    for frame in frames:
        brake = frame.get("brake_pct")
        steer = frame.get("steering_norm")
        speed = frame.get("speed_kph")
        if brake is None or steer is None or speed is None:
            continue
        if (brake < TRAIL_MIN_BRAKE_PCT or abs(steer) < TRAIL_STEER_NORM
                or speed < MIN_SPEED_KPH):
            continue
        front = _mean((frame.get("slip_fl"), frame.get("slip_fr")))
        rear = _mean((frame.get("slip_rl"), frame.get("slip_rr")))
        if front is not None:
            fronts.append(front)
        if rear is not None:
            rears.append(rear)
    return _mean(fronts), _mean(rears), min(len(fronts), len(rears))


# ------------------------------------------------------------------ reading

def sheet_bias(store: Store, session: dict) -> float | None:
    """The `bb` on the sheet this session records - **not a declaration.**

    The driver, 22 Aug: *"Brake bias hasn't always been 0, I haven't updated it
    and it has moved."* Brake balance is the one setup value he changes on the
    MFD mid-session, and the sheet is only rewritten when a whole revision is
    filed - so of every field on the sheet this is the likeliest to be stale,
    and it is stale in the direction that matters, because a stale 0 reads as
    a deliberate 0.

    It is reported as what it is: the last value anybody wrote down. Grouping
    runs by it manufactures agreement between runs driven at different
    settings, which is the opposite of the finding - see `by_session`.
    """
    sheet_id = session.get("setup_sheet_id")
    if not sheet_id:
        return None
    try:
        sheet = store.get_setup_sheet(sheet_id)
    except Exception:                                        # noqa: BLE001
        return None
    if sheet is None:
        return None
    # `SetupSheet.values` is the 23-key dict, keyed by the export contract's
    # own vocabulary - `bb` is brake balance there and everywhere else.
    values = getattr(sheet, "values", None)
    if not isinstance(values, dict):
        return None
    raw = values.get("bb")
    try:
        return float(raw) if raw is not None else None
    except (TypeError, ValueError):
        return None


def collect(store: Store, *, event_id: int | None, session_id: int | None,
            override: float | None):
    """(bias -> [Stop]), and the trail-brake means per bias."""
    sessions = []
    if session_id is not None:
        row = store.get_session(session_id)
        if row:
            sessions.append(row)
    elif event_id is not None:
        for kind in ("practice", "race"):
            sessions.extend(store.list_sessions(event_id, kind))

    by_bias: dict[float | None, list[Stop]] = {}
    trail: dict[float | None, list[tuple[float, float, int]]] = {}
    for session in sessions:
        bias = override if override is not None else sheet_bias(store, session)
        for lap in store.list_laps(session["id"]):
            if lap.get("excluded") or lap.get("is_pit_lap"):
                continue
            stored = store.get_lap_frames(lap["id"])
            if not stored:
                continue
            frames = stored["frames"]
            version = stored.get("frame_schema_version") or 2
            hz = stored.get("sample_hz") or 60.0
            by_bias.setdefault(bias, []).extend(
                find_stops(frames, lap_id=lap["id"], lap_num=lap["lap_num"],
                           schema_version=version, sample_hz=hz))
            front, rear, samples = trail_slip(frames)
            if front is not None and rear is not None and samples:
                trail.setdefault(bias, []).append((front, rear, samples))
    return by_bias, trail


def report(by_bias, trail, *, show_trail: bool) -> None:
    if not any(by_bias.values()):
        print("No braking events found. A stop needs "
              f"{MIN_EVENT_FRAMES} frames above {BRAKE_ON_PCT:.0f}% brake "
              f"above {MIN_SPEED_KPH:.0f} km/h.")
        return

    print(f"\n{'bias':>6} {'stops':>6} {'front min':>10} {'rear min':>9} "
          f"{'split':>8} {'decel g':>8}  laps")
    print("-" * 62)
    for bias in sorted(by_bias, key=lambda b: (b is None, b)):
        stops = by_bias[bias]
        if not stops:
            continue
        splits = [s.split for s in stops if s.split is not None]
        label = "??" if bias is None else f"{bias:+.0f}"
        laps = len({s.lap_num for s in stops})
        print(f"{label:>6} {len(stops):>6} "
              f"{_mean([s.front_min_slip for s in stops]) or float('nan'):>10.3f} "
              f"{_mean([s.rear_min_slip for s in stops]) or float('nan'):>9.3f} "
              f"{(st.mean(splits) if splits else float('nan')):>8.3f} "
              f"{_mean([s.decel_g for s in stops]):>8.3f}  {laps}")

    print("\n  The bias column is THE SHEET'S last-known value, not a "
          "declaration - brake\n  balance is changed on the MFD and the sheet "
          "is only rewritten when a whole\n  revision is filed, so of every "
          "field on it this is the likeliest to be stale.\n  Use --bias for a "
          "run you actually know, and --by-session to see whether it moved.")

    v1 = {s.schema_version for stops in by_bias.values() for s in stops} & {1}
    if v1:
        print("\n  ! Some laps are v1 blobs: `slip_*` was 2pi too large at "
              "the source and has been\n  repaired on read. The values are "
              "honest, but a reconstructed channel is weaker\n  evidence than "
              "a recorded one - prefer runs driven since the repair.")

    print("\n  split = front minimum slip minus rear. NEGATIVE means the "
          "front locked deeper,\n  which on the settled convention "
          "(negative bias = more front) is what front bias does.\n  A "
          "monotone split across -5 / 0 / +5 confirms the sign on this game "
          "version.")

    if show_trail and trail:
        print(f"\n{'bias':>6} {'front':>8} {'rear':>8} {'frames':>8}   "
              f"trail-braking phase")
        print("-" * 52)
        for bias in sorted(trail, key=lambda b: (b is None, b)):
            rows = trail[bias]
            weight = sum(n for _, _, n in rows)
            front = sum(f * n for f, _, n in rows) / weight
            rear = sum(r * n for _, r, n in rows) / weight
            label = "??" if bias is None else f"{bias:+.0f}"
            print(f"{label:>6} {front:>8.3f} {rear:>8.3f} {weight:>8}")
        print("\n  Per frame, not per corner - which is why this can resolve "
              "a click where a\n  three-lap comparison of corner minimum "
              "speed cannot.")


def by_session(store: Store, event_id: int) -> None:
    """Every session's split, oldest first. **This is the useful view.**

    Grouped by the sheet's bias the archive looked uniform: three cars, three
    circuits, split -0.039 / -0.040 / -0.039. Per session it is not uniform at
    all - the Shelby at Yas runs +0.022 to -0.068 across six sessions on one
    car at one circuit, and +0.022 means the REAR locked deeper. A stale sheet
    had averaged a real change into a false agreement.

    **A moved split is not proof of a moved bias.** ABS setting, compound, fuel
    load and how hard the stop was taken all move it too, and none of them is
    recorded against a braking event. What the spread establishes is that the
    channel is sensitive enough to see a change of this size - which is the
    precondition for a declared-bias run being able to calibrate it.
    """
    rows = []
    for kind in ("practice", "race"):
        for session in store.list_sessions(event_id, kind):
            stops = []
            for lap in store.list_laps(session["id"]):
                if lap.get("excluded") or lap.get("is_pit_lap"):
                    continue
                stored = store.get_lap_frames(lap["id"])
                if not stored:
                    continue
                stops.extend(find_stops(
                    stored["frames"], lap_id=lap["id"], lap_num=lap["lap_num"],
                    schema_version=stored.get("frame_schema_version") or 2,
                    sample_hz=stored.get("sample_hz") or 60.0))
            splits = [s.split for s in stops if s.split is not None]
            if len(splits) >= MIN_SESSION_STOPS:
                rows.append((session, kind, stops, splits))
    if not rows:
        print(f"No session at event {event_id} has {MIN_SESSION_STOPS} "
              f"braking events.")
        return

    print(f"\n{'sess':>5} {'kind':<9} {'stops':>6} {'front':>7} {'rear':>7} "
          f"{'split':>7} {'decel':>6} {'sheet':>6}  started")
    print("-" * 76)
    for session, kind, stops, splits in sorted(
            rows, key=lambda r: (r[0].get("started_at") or "")):
        sheet = sheet_bias(store, session)
        print(f"{session['id']:>5} {kind:<9} {len(splits):>6} "
              f"{_mean([s.front_min_slip for s in stops]):>7.3f} "
              f"{_mean([s.rear_min_slip for s in stops]):>7.3f} "
              f"{st.mean(splits):>7.3f} "
              f"{_mean([s.decel_g for s in stops]):>6.2f} "
              f"{('--' if sheet is None else f'{sheet:+.0f}'):>6}  "
              f"{(session.get('started_at') or '')[:16]}")

    spread = [st.mean(r[3]) for r in rows]
    print(f"\n  split ranges {min(spread):+.3f} to {max(spread):+.3f} across "
          f"{len(rows)} sessions.")
    print("  A spread this wide on one car at one circuit is a setting that "
          "moved - but ABS,\n  compound, fuel and how hard the stop was taken "
          "move it too, and none of those\n  is recorded against a braking "
          "event either. It says the channel is SENSITIVE\n  enough, not what "
          "it was sensitive to.")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db")
    ap.add_argument("--event", type=int)
    ap.add_argument("--session", type=int)
    ap.add_argument("--bias", type=float,
                    help="the brake balance these runs were driven at, where "
                         "the sheet does not carry it")
    ap.add_argument("--by-session", action="store_true",
                    help="every session's split, oldest first - the view that "
                         "shows whether the setting moved")
    ap.add_argument("--trail", action="store_true",
                    help="also report the trail-braking phase")
    args = ap.parse_args()
    if args.event is None and args.session is None:
        raise SystemExit("give --event or --session")

    store = Store(args.db) if args.db else Store()
    if args.by_session:
        if args.event is None:
            raise SystemExit("--by-session needs --event")
        by_session(store, args.event)
        return 0
    by_bias, trail = collect(store, event_id=args.event,
                             session_id=args.session, override=args.bias)
    report(by_bias, trail, show_trail=args.trail)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
