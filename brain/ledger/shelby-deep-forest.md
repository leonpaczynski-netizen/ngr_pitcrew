# Experiment ledger — Ford Shelby GT350R '16 × Deep Forest Raceway

The car and its settings: [`brain/car-state/shelby-deep-forest.md`](../car-state/shelby-deep-forest.md) - the only place a value is written. This file holds keys, directions and deltas in percentage points of slider range, never a setting. Conventions: [README](README.md).

Seeded 11 Sep 2026 from the car-state file at `712b4f7` 2026-09-06.

**Range situation.** The car-state header says *"Range record: measured 23 Aug 2026, GT7 v1.71,
`verified = 1`"*, and its percentages are computed against that record. The range register
(`11-car-slider-ranges.md`, updated 24 Aug) lists the Shelby as **v1.70, STALE, "do not issue"**.
The car-state's own percentages do not fit the register's v1.70 endpoints, so the two files
describe different records: (b)-S1. The file also states the **differential is issued in
absolutes only**, "register has not been re-read". So LSD is `range unknown` here. The one
experiment actually run is a gearbox change, and gear ratios have no range anyway.

```csv
date,session_ids,key,direction,delta_pct_range,instrument,measured_floor,control,prediction,falsifier,outcome,source,car_state_rev
2026-09-06,s133 -> s134,gear2;gear3;gear4;gear5;gear6,longer (numerically lower) in gears 2-6; final gear unchanged,range unknown,gear changes per lap (FEED),not established,s133 (4 clean laps; Rev A box),gear changes drop ~4.5 per lap,no drop,confirmed,"§Rev B 'Why — session 133'; §'Rev B verified — session 134' row 1 (31.2 -> 26.4 = -4.9/lap)",Rev B
2026-09-06,s133 -> s134,gear2;gear3;gear4;gear5;gear6,longer,range unknown,rev-limiter frames in 6th (FEED),not established,s133 (998 limiter frames in 6th),the limiter frames in 6th go to ~0,6th still limiting,confirmed,"§'Rev B verified' row 2 (6th now zero; 250 -> 59 per lap overall)",Rev B
2026-09-06,s133 -> s134,gear2;gear3;gear4;gear5;gear6,longer,range unknown,Vmax (FEED),not established,s133 Vmax 265.2 km/h,Vmax rises above s133's,Vmax not higher,confirmed,"§'Rev B verified' row 3 (+7.6 km/h)",Rev B
2026-09-06,s134,gear2;gear3 (shift 2->3 landing rpm),landing ~400 rpm lower,range unknown,driver report,not established,none,2->3 does not feel flat despite landing lower,driver reports it flat,confirmed,"§'Rev B verified' row 4 ('no complaint from the driver'); see (b)-S3",Rev B
2026-09-06,none yet,gear2,longer,range unknown,limiter frames in 2nd (FEED),not established,s134 (199 of 293 limiter frames in 2nd),lengthening 2nd clears its limiter frames,none stated,open,"§'Rev B verified' ('One item left open ... Not worth a fourth box iteration before this race')",Rev B
2026-09-06,none yet (run 2 on the sheet),df_r,down,step not stated in this file,none stated,not established,none,lowering df_r helps the front (df_f has no travel left upward; see the car-state file),none stated,open,"§'What GT7's own readout says' last para ('That is run 2 on the sheet')",Rev A
2026-08-26,never run,lsd_a,up,range unknown (diff issued in absolutes per the file),none stated,not established,none,none stated in this file (doctrine band cited at Rev A),none stated,open,"§'Open against this car' last row ('PROPOSED 26 Aug, NEVER RUN ... Demoted below the aero test'); Rev A DIFFERENTIAL block",Rev A
2026-09-06,none yet,top (readout) / six ratios,verification (no change),range unknown,Manual Adjustment screen,not established,n/a,one tap on Manual Adjustment settles the Top Speed readout,n/a,open,"§'Open against this car' rows 'Top Speed' and 'Six ratios'; see (b)-S2 (the file resolves both elsewhere)",Rev A
2026-09-06,s134,n/a (circuit-reference wear figure),n/a,n/a,HUD wear gauge regression laps 2-6 (5 readings),not established (gauge resolution not stated here),n/a,reference: 13-16 laps at 1x (6.5-8 at 2x),measured stint far longer,refuted,"§'Tyre wear — MEASURED here' item 1 (30.3 laps measured; ~4x; RECONCILIATION AS4)",Rev B
2026-09-06,s134,n/a (wearSeverity grading),n/a,n/a,worst-wheel wear per km,not established,RBR measured 0.90-1.35 %/km,reference grades Deep Forest harder (5) than RBR (3),Deep Forest gentler per km,refuted,"§'Tyre wear' item 2 ('anti-predictive': 0.66 %/km)",Rev B
```

**Notes, Shelby**

- **Rev B** changed gear ratios 2–6 only. The final gear is unchanged, and it is the only
  transmission value with a slider (fg [2,5]). The final gear did not move, so there is no pp
  delta anywhere in Rev B. It is listed in (a).
- The four Rev B predictions are one experiment, given one row each. The file headlines them as
  "All three predictions held" over a four-row table: see (b)-S3.
- Side effect, measured but not predicted: fuel went down 4.3 % with the new box. It gets no row.
- The `df_r` step size is not stated, so no delta can be computed. It is not in (a), because the
  file gives no absolutes for it either. The file's own arithmetic implies a df_r span
  of 150. Once a step is named, the delta will be step ÷ 150. That span is
  inferred from the file's arithmetic, not read from a range record.
- **Not rows:** `bb` −2 is the driver's own trim ("record it, never correct it"). The ballast
  mass is a regulation. The `arb_f` dispute is closed by SCREEN. FFB is confirmed. The Round 5
  wheelbase fault is explained. The RBR history row (a hand-cut box plus a `de_r` change in one
  run, 29 Aug) belongs to RBR's ledger, not this one.

## Items with no percent-of-range delta

Cited by location only; the absolutes are read at the cited section and restated nowhere.

| id | car × circuit | item | where the absolutes are | why no pp |
|---|---|---|---|---|
| a-S1 | Shelby × Deep Forest | **Rev B gearbox, ratios 2–6: the one experiment run on this file** | §Rev B TRANSMISSION block; Rev A TRANSMISSION block | gear ratios; the final gear (the only ranged transmission value) is unchanged |
| a-S2 | Shelby × Deep Forest | lengthen 2nd (open, deferred) | §"Rev B verified", last para | gear ratio |
| a-S3 | Shelby × Deep Forest | `lsd_a` proposal of 26 Aug, never run | §"Open against this car", last row; Rev A DIFFERENTIAL block | the file issues LSD in absolutes ("register has not been re-read"). The register's Shelby LSD range is v1.70 and STALE |
| a-S4 | Shelby × Deep Forest | `shift_points` id 2, issued then re-issued for Rev B | Rev A and Rev B TRANSMISSION blocks | not a slider |
| a-S5 | Shelby × Deep Forest | Top Speed readout discrepancy | Rev A TRANSMISSION block; §"And the readout moves the WRONG WAY" | readout, not a setting |

## Contradictions on file

Surfaced, not averaged (`CLAUDE.md` §4 rule 1). The latest is kept as the outcome; both are cited.

- **S1 (cross-file).** The car-state header says "Range record: measured 23 Aug 2026, GT7 v1.71,
  `verified = 1`". The range register (`11-car-slider-ranges.md`, updated 24 Aug) lists the Shelby
  as "v1.70, STALE, do not issue … the only card left to turn". The car-state's own nf and df_f
  percentages cannot be reproduced from the register's v1.70 endpoints: its nf percentages imply
  a different floor and span, and its df_f percentage implies a lower ceiling than the register's.
  Either a v1.71 record exists in `pitcrew.db` that the register never absorbed, or the car-state
  percentages rest on an unknown record. Not resolvable from files. This session read files only.
- **S2.** "Open against this car" lists the Top Speed readout discrepancy as "🔴 NEW, OPEN" and
  the six ratios as "not re-read since" s101. The same file's Rev A block records the ratios as
  read off Manual Adjustment on 6 Sep ("SCREEN … **and** FEED, in agreement"). §"And the readout
  moves the WRONG WAY" resolves the readout as a readout. Rev B then FEED-confirms the box in
  s134. Kept: resolved. The open table is stale.
- **S3.** The heading says "**All three** predictions held", but the table has four rows. The
  fourth ("no complaint from the driver") is the weakest class of evidence (see B3). Kept:
  `confirmed` ×4, the fourth flagged.
- **S4 (plan vs file).** Plan L7: `where_the_change_landed` counts **0 and 1** clean laps for
  s133 → s134. The car-state says **4 and 5**, and declares Rev B verified. The file does not
  resolve this. Its Rev B rows rest on the file's own clean-lap definition.

**Cross-file, doctrine**

- **X1.** Sardegna §13's driver note (10 Sep, *"me not complaining about the car doesn't mean it's
  got the best setup"*) retires "no symptom / no complaint" as evidence. Three earlier `confirmed`
  rows rest partly or wholly on silence: Shelby Rev B row 4 (S3), the Bathurst beep row (B3), and
  Sardegna Rev A's platform row ("Driver reported no harshness", though that row also has a
  body-height measurement). Kept as scored, flagged.
