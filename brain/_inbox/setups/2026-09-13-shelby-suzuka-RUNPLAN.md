# Run plan — Ford Shelby GT350R '16 at Suzuka Full Course, 13 Sep 2026

Filled by Ludo 13 Sep ~08:45 UTC, before the car turns a wheel. Quali 10:30 UTC.

```
  Session      : practice (own lobby)             Event : 13 / cmrbgn23c000t01n04esfvuzt
  Car state    : brain/car-state/shelby-suzuka.md Rev A, ISSUED 13 Sep (screenshot asked)
  League limits: - BHP / 1,335 kg / FR                                         [events row + hub]
  Multipliers  : tyre x2 · fuel x2 · refuel 2.0 L/s  -- PRACTICE LOBBY MUST MATCH
  Time on track: ~75 min before the quali debrief    Laps available: ~30 at ~2:00
```

## The derivations the predictions rest on — all `[DERIVED]`, cross-circuit

Deep Forest (4,253 m) → Suzuka (5,807 m), ×1.365 per lap. Read off `laps` 13 Sep:

| figure | Deep Forest source | at Suzuka |
|---|---|---:|
| race burn | s138 median 7.546 L/lap, n=17 | **10.30 L/lap** |
| practice flying burn | s134 median 7.817, n=5 | **10.67** |
| practice out-lap burn | s134 lap 1, 8.000 | **10.92** |
| front-right wear, race stint 1 | s138 laps 2→12, 5.6 → 41.7 % = 3.61 %/lap | **4.93 %/lap** |

Doctrine (`05-track-reference.md` §1.6, pre-1.49, mechanism only) says Suzuka is
the hardest circuit on fronts. Its Deep Forest wear figure was wrong by ~4×
(RECONCILIATION AS4), so the transfer is used and the doctrine is not.

**Quali fuel, 50 L fixed:** out-lap 10.92 + 3 flyers × 10.67 = **42.9 L** ·
a 4th flyer needs **53.6 L**. On race burn: 41.2 → 51.7. **Four flyers do not fit
on map 1 either way.** With the out-lap on **map 6** (~50 % consumption,
`CLAUDE.md` §5.3 `[DOCTRINE]`): ~5.5 + 4 × 10.67 = **48.2 L** — fits, ~2 L spare.

## Runs

| run | purpose | fuel | tyre | the ONE delta | lap type | laps | instrument + floor | prediction | falsifier | outcome |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | **quali rehearsal + baseline + gearbox** | **50 L** | RS new | none (Rev A) | out-lap on MAP 6, then map 1, push until dry | 1 + 4 | `laps.fuel_used`; gear-at-130R off frames; front/rear lock counts at the hairpin, Degner 2, chicane | P1 out-lap on map 6 ≤ 8.5 L · P2 flyers 10.0-11.0 L/lap · P3 4th flyer completes · P4 no upshift inside 130R | P1 out-lap > 8.5 L · P2 flyer ≤ 9.9 (4 flyers fit on map 1 — map 6 not needed) · P4 an upshift at 130R | |
| 2 | ONE change chosen by run 1 — only if run 1 names one | 50 L | same set | set by the run-1 debrief (candidates: `df_r` direction from his 130R/Esses report; box re-cut if P4 fails) | push, 3 clean | 4 | named at the debrief | named at the debrief | named at the debrief | |
| 3 | **race load: burn + wear** | 100 L | RS new | none | long, 8 clean | 9 | burn; HUD gauge wear (OBS ON) | P5 race burn 9.8-10.8 L/lap · P6 worst front 4-6 %/lap, fronts even side to side (Esses alternate) | P5 outside · P6 worst front < 3 or > 7 %/lap, or FR/FL ≥ 1.3 | |

**Priority if time runs short: 1, then 3, then 2.** Run 1 decides quali; run 3
decides whether the stop takes tyres (Deep Forest: 4.4 s of tyres nobody needed).

**Open from the 7 Sep quali plan, closed at the debrief:** best lap on flyer 4 ·
gap to pole < 1.0 s · 6th reaches the limiter on the back straight · FR limits.
