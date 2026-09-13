# Ford Shelby GT350R '16 — Suzuka Circuit, Full Course

**The ONLY place a setup value for this car+circuit may be written.** Every
other file links here and restates nothing. Sources: **SCREEN** (settings
screenshot — ground truth) · **FEED** (the gearbox only) · **ISSUED** (a
request, not a reading).

**Event: NGR Supercars Series 1 Rd7 · `events.id` 13 · hub round
`cmrbgn23c000t01n04esfvuzt` · 13 Sep 2026 10:30 UTC.** `lobbySettingsOverrides =
null` (read 13 Sep), so the series defaults hold:

```
  Race : 30 MIN timed + 180 s · 2x tyre / 2x fuel · initial fuel 100 L · refuel 2.0 L/s
         0 mandatory stops · STANDING start · grid by FASTEST LAP · damage HEAVY
  Quali: 10 min + 180 s continuation · fuel FIXED 50 L · wear/fuel SAME AS RACE · NO slipstream
  ABS / TCS / ASM / countersteer PROHIBITED · weather FIXED / CLEAR · RS / RM / RH
  BoP OFF · tuning ALLOWED · weight limit 1,335 kg · ROAD_CAR
  Full Course 5,807 m (data/gt7_tracks.json)
```

**Range record: 23 Aug 2026, GT7 v1.71, `verified = 1`** (read via MCP 13 Sep).

---

# Rev A — **ISSUED 13 Sep 2026. Not yet SCREEN-confirmed.**

**Deep Forest Rev B carried unchanged, every value.** No Shelby lap has ever
been recorded at Suzuka, so there is no symptom to engineer from; the only
honest first sheet is the one SCREEN- and FEED-confirmed a week ago
([`shelby-deep-forest.md`](shelby-deep-forest.md), Rev A mechanicals + Rev B box).
Every value below is `[ASSUMED]` *for Suzuka* until practice run 1.

```
                                RACE (Rev A)                  % of range
TYRES           Racing Soft
SUSPENSION
  Body height            F 89 mm    R 107 mm                  16.5% / 14.1%
  Natural frequency      F 3.05 Hz  R 3.20 Hz                 52.5% / 60.0%
  Anti-roll bar          F 5        R 4                       44.4% / 33.3%
  Damping compression    F 24       R 28                      20.0% / 40.0%
  Damping expansion      F 40       R 38                      33.3% / 26.7%
  Negative camber        F 1.4      R 1.0                     23.3% / 16.7%
  Toe                    F -0.05    R +0.10                   47.5% / 55.0%
DIFFERENTIAL    Initial 5 · Accel 17 · Braking 34              16.7% / 17.0% / 34.0%
AERO            Downforce F 150  R 260                        100.0% / 73.3%
ECU / RESTRICTOR  100% / 100%
BALLAST         109 kg @ 0     (mass = regulation; total 1,335 kg)
TRANSMISSION    3.400 / 2.330 / 1.600 / 1.360 / 1.205 / 1.085 · final 3.600
                limiter speeds at K = 304 km/h: 89 / 130 / 190 / 224 / 252 / 280 km/h
BRAKE BALANCE   -2 (his in-car trim, last read 6 Sep — recorded, never corrected)
SHIFT BEEP      shift_points id 9 (13 Sep): perf 8500/8500/8250 · fuel 8000/8000/7750 · 4-6 SILENT
```

## Open against this sheet at Suzuka

| | status |
|---|---|
| **Is Rev B what is in the car?** | 🔴 ASKED 13 Sep — screenshot of settings + Manual Adjustment requested |
| **Gearbox at 130R** — doctrine: no upshift in 130R; 5th tops 252, 6th 280 | `[ASSUMED]` — run 1 |
| **Quali fuel: 4 flyers do not fit 50 L on map 1** | `[DERIVED]` — see `brain/_inbox/setups/2026-09-13-shelby-suzuka-RUNPLAN.md` |
| **Front lock at -2** — 47/47 laps at Deep Forest vs rear 2/47 (measurements 26-29) | his trim; measurement given to him, Degner 2 + chicane read in run 1 |
| **Aero balance** — circuit doctrine says run high/rear-biased; GT7 readout says high-speed UNDER -0.50 | direction decided by his run-1 report in 130R / Esses, not by doctrine |
