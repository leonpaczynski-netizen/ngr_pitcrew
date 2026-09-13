# Suzuka — Supercars Series 1 Round 7 — qualifying plan, 13 Sep 2026

**Written 7 Sep 2026 by Ludo, six days out. Everything below is either from the
hub, measured on this car at another circuit and labelled so, or `[DOCTRINE]`.
No Shelby lap has ever been recorded at Suzuka: there is nothing measured here
yet, and this file says so rather than pretending.** The event row does not
exist until the app next launches and adopts the hub round; the MCP
`write_qualifying_plan` call is made then, from §6.

```
  Supercars Series 1 Rd7 · Suzuka Circuit · 13 Sep 2026 10:30 UTC
  Quali: 10 minutes, fuel FIXED at 50 L, grid by FASTEST LAP     [hub, series defaults]
  Race : 30 min timed, 2x tyre / 2x fuel, refuel 2.0 L/s, 0 mandatory stops
  ABS / TCS / countersteer PROHIBITED · weather FIXED / CLEAR · weight limit 1,335 kg
```

---

## 1. The target — what pole has cost, and where we sit

From the hub (`RoundResult`), Supercars Series 1 so far:

| round | pole | our Q gap | fastest race lap | our race-lap gap |
|---|---|---:|---|---:|
| Sainte-Croix B | Magical daddy | — | Boxhead | — |
| Watkins Short | Boxhead | +0.472 (Q4) | Boxhead | +0.353 |
| Yas Marina | Magical daddy | +3.462 (Q5) | Magical daddy | +3.059 |
| Road Atlanta | Boxhead | +1.780 (Q4) | Magical daddy | +0.630 |
| RBR Short | Boxhead | +0.481 (Q3) | Magical daddy | +1.069 |
| Deep Forest | *(not yet on the hub)* | | | |

**Three drivers have taken every pole and every win.** Our qualifying gap runs
0.5–3.5 s and is the larger of the two gaps at three rounds of four. At Suzuka
overtaking is hard (T1 and the chicane, `05-track-reference.md` — pre-1.49,
mechanism only), so grid position is worth more here than anywhere on the
calendar. **Target: inside 0.5 s of pole**, which is the Watkins and RBR gap,
not the Yas one.

## 2. The session — 10 minutes, 50 L, fixed

- **Fuel is not a lever.** The lobby fixes 50 L; `race.quali_fuel` does not apply
  (`[MEASURED at Deep Forest quali, 6 Sep]` — same rule, same series).
> ⟂ **Correction, 13 Sep 2026 (Ludo, race day).** "Out-lap plus four flyers" was
> never checked against fuel. At this car's Deep Forest burn scaled to 5,807 m,
> out-lap + 3 flyers is ~43 L and a 4th flyer needs ~54 L of the fixed 50.
> **On map 1 the fourth flyer does not fit.** Out-lap on map 6 makes it fit
> `[DERIVED + DOCTRINE]`; practice run 1 rehearses it on 50 L. See
> `2026-09-13-shelby-suzuka-RUNPLAN.md`. Kept below as written.

- **The flying lap is the fourth.** At Deep Forest his best came on flying lap 4
  in both sessions, worth 1.2–1.6 s over lap 1 — ten times the fuel-weight
  effect `[MEASURED, n=2 sessions]`. Ten minutes at Suzuka (~2:00 laps in a
  Gr.3-class car) is an out-lap plus four flyers with nothing to spare.
- **Tyre temperature plateaus during the out-lap** `[MEASURED Deep Forest]`; a
  slow out-lap buys nothing. No optimal window has ever been published for
  GT7 — plan for the plateau, never for "the window".

## 3. The out-lap script `[DOCTRINE, from real-team practice — untested here]`

1. Leave the pits at the start of the session; the clock runs regardless.
2. Out-lap at 80–90%: full throttle on the exits of the Esses and 130R, brake
   firmly for the hairpin and the chicane to put heat in the discs. No lift
   through Dunlop.
3. Cross the line with a gap of ≥3 s to the car ahead — check the mirror down
   the back straight and, if needed, lift before the chicane rather than start
   the flyer in dirty air.
4. Flyers 1–3 are the build; **lap 4 is the lap**. If lap 3 is within 0.2 s of
   lap 2, the set has plateaued — commit on lap 4.
5. In-lap on the clock: say the balance in one sentence on the radio (front
   or rear, entry or exit) for the race sheet.

## 4. The car — nothing to move until a lap is on file

`brain/car-state/shelby-deep-forest.md` Rev B is the only SCREEN-confirmed
Shelby setup. Suzuka is a different gearbox problem (130R and the back straight
against the Esses), so the first practice run is **the gearbox run**: 4 clean
laps, then `tools/shift_points.py` and the K = 304 constant to cut the box; the
shift table is re-issued with it. No aero or mechanical change is proposed
before that run — proposing one would be doctrine wearing a setup's clothes.

## 5. Predictions (to be closed at the debrief)

1. Best lap on flying lap 4, not earlier `[falsified if lap 2 or 3 is best]`.
2. Gap to pole under 1.0 s `[falsified if ≥1.0 s]`; under 0.5 is the target.
3. The Deep Forest box tops out on the back straight — 6th at the limiter for
   >2 s `[falsified if 6th never reaches the limiter]`.
4. Front-right is the limiting tyre again (FR/FL ≥ 1.2 on the gauge after the
   session) `[falsified if FL ≥ FR]`.

## 6. The MCP write, at the next launch

```python
from pitcrew.mcp import server
server.write_qualifying_plan(event_id=<Suzuka event id>, plan=json.dumps({
    "minutes": 10, "fuel_l": 50.0, "flyers": 4, "the_lap": 4,
    "target_gap_to_pole_s": 0.5,
    "out_lap": "80-90%, heat the discs into the hairpin and chicane, 3 s gap at the line",
    "predictions": ["best on flyer 4", "gap to pole < 1.0 s", "6th hits the limiter on the back straight", "FR limits"],
}))
```
