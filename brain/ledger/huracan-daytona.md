# Experiment ledger — Huracán GT3 '15 × Daytona Road Course

The car and its settings: [`brain/car-state/huracan-daytona.md`](../car-state/huracan-daytona.md) - the only place a value is written. This file holds keys, directions and deltas in percentage points of slider range, never a setting. Conventions: [README](README.md).

Seeded 11 Sep 2026 from the car-state file at `b6a0b54` 2026-09-08.

```csv
date,session_ids,key,direction,delta_pct_range,instrument,measured_floor,control,prediction,falsifier,outcome,source,car_state_rev
2026-09-01,s113/114 -> s115,rh_f;cam_f;toe_f;gear6,rh_f down; cam_f up; toe_f toe-out; 6th shorter (numerically higher ratio),rh_f -16.0; cam_f +6.7; toe_f -4.0; gear6 range unknown,none stated,not established,none (four keys moved in one step),none stated in this file,none stated,open,"Header table, Run 1a vs Run 2 columns",Run 1a -> Run 2
2026-09-03,s116 -> s117,toe_f,toe-in (reversing the Run 2 toe-out step),+4.0,front L/R slip split under braking (>60 % brake >80 km/h),0.003-0.006,4 Sep five-run sweep s120-124 plus race stint s118 (split -0.0035 to -0.0073),remove the front L/R braking asymmetry (0.0428),split stays outside the floor,confirmed,"Header table Run 4 toe cell; §4 Sep para 'bb = 0 for all five' ('the toe fix is holding'); AXIS-REGISTER toe_f row",Run 4
2026-09-03,s116 onward,bb,forward (the driver's own trim; two clicks),-20.0,n/a (a condition and not a test),n/a,n/a,none - recorded because every later RR wear baseline runs on it,n/a,open,"Header table Run 4 bb (the driver's move; the file dates it both 'run 4' and 'before 3 Sep')",Run 4
2026-09-03,s116 -> s117,dc_r,softer,-20.0,rear squat velocity on throttle-up at zone 4 (mm/s),not established,Run 1a / Run 2 / Run 3 squat velocities,none stated (the file notes the same outcome would confirm an exit-traction intent and refute a braking one),none stated,open,"Header table Note 1; §'Why this file exists' (setup_changes gains reason)",Run 4
2026-09-03,s117/s118 -> s119,cam_f,down,-6.7,driver report; front surface temps; rear-minus-front temp gap,not established,s118 race stint (camber state unknown),none stated (driver-initiated),none stated,unresolvable,"Header table Run 4 cam cell and s119 row ('resolves nothing'); §4 Sep F1 (candidate mechanism: front ~1.1 mm higher)",Run 4 / s119
2026-09-04,s119 -> s120,df_f,up (as a lever at this magnitude; the direction is not refuted),+40.0,"suspension compression at speed; RR wear; terminal speed; rear temp; lap time","terminal 0.56-2.77 km/h; lap time cannot rank (F5); others not established",s119 (3 Sep other day),'more aero to look after the rears' (3 Sep),load/wear unmoved,refuted,"§4 Sep five A/B runs, run 5; F4; F7; AXIS-REGISTER df row ('Invisible')",run 5
2026-09-04,s120 -> s121,df_r,up (as a lever at this magnitude; the direction is not refuted),+25.0,"rear compression at 270 km/h (+0.65 mm); wear; terminal; rear temp","terminal 0.56-2.77 km/h; others not established",s120,'more aero to look after the rears',load/wear unmoved,refuted,"§4 Sep run 6; F4; F7",run 6
2026-09-04,s122 -> s123,cam_f;cam_r,down;down,cam_f -16.7; cam_r -3.3,front surface temp; front L/R slip split and lock,front temp 0.9-1.4 °C; split 0.003-0.006,s122 baseline,none stated (sweep),none stated,unresolvable,"§4 Sep run 8; F3 ('nothing measurable on the front'; contact patch invisible)",run 8
2026-09-04,s122 -> s124,cam_f,up,+33.3,front surface temp; front slip split,front temp 0.9-1.4 °C; split 0.003-0.006,s122 baseline,none stated (sweep),none stated,unresolvable,"§4 Sep run 9; F3",run 9
2026-09-04,s122 -> s124,cam_r,up,+46.7,rear slip >1.05 on exit at T2-T5,whole-lap unchanged-rear band 18.7-34.4 % (3 Sep); per-zone floor not established,s122 baseline,none stated,none stated,unresolvable,"§4 Sep F2 ('[DERIVED], suggestive, not proven'); AXIS-REGISTER camber-rear row",run 9
2026-09-04,s122 -> s123/s124,cam_f;cam_r (mechanism),either,cam_f 50.0 sweep span,front/rear suspension height on the banking at full throttle,not established (s119 same-camber reading used as day control),s119 (other day same camber),none (unpredicted finding: camber is a ride-height lever ~2.8 mm/deg),n/a,confirmed,"§4 Sep F1 '[MEASURED], one instrument'",runs 7-9
2026-09-04,s125 -> s126,lsd_b,up,+12.0,sub-0.90 rear frames at first corner; rotation-under-brakes index at T1/z3/z4,T1 0.0033; z3 0.0014; z4 0.0011,s125 13-lap stint,rear brake lock at the first corner removed; cost = less rotation on release,cost on release is the trade and the falsifier,confirmed,"§4 Sep evening, the 'RUN, session 126' paragraph and the '(superseded) ... was issued as' paragraph",s126
2026-09-04,s126 -> s127,lsd_b,down,-5.0,none stated,not established,none,none stated (the driver's own ask; 'justified by §AB2'),none stated,open,"§4 Sep evening, the 'THEN:' line (driver's ask); §7 Sep SCREEN sheet confirms it was in the car",s127 sheet
2026-09-04,s127 (session not named in file),dc_f;dc_r,softer;softer,dc_f -40.0; dc_r -30.0,body swing at the Bus Stop kerb (mm),not established,pre-change Bus Stop swing,the car stops leaving the ground over the Bus Stop kerb,swing unchanged or worse,refuted,"§4 Sep evening 'NEXT CHANGE ISSUED dc'; §7 Sep line 267 (dc 'was falsified there on 4 Sep'); AXIS-REGISTER dc row (driver says fixed; disagreement unaveraged)",s127 sheet
2026-09-04,s127 (session not named in file),dc_f;dc_r,softer;softer,dc_f -40.0; dc_r -30.0,driver report,n/a,pre-change Bus Stop behaviour,the car stops leaving the ground over the Bus Stop kerb,he reports it unchanged,confirmed,"AXIS-REGISTER dc row (the driver says fixed); the instrument row above says refuted - both kept, not averaged (rule 1), see (b)-D9",s127 sheet
2026-09-08,s143 -> s144,rh_r,down,-20.0,"lap time fuel-corrected (0.003 s/L/lap [DERIVED]); driver report",lap-to-lap sd 0.918 s (stated at s147); not established for fuel-corrected best,"race laps s139-143 (config A)",less rake is better (rear brought toward the front's percent of range),none stated for pace,confirmed,"§8 Sep session 144; s146 'stands on pace and on his report'; AXIS-REGISTER rh row",config B
2026-09-08,s144 -> s146,rh_r,down,-20.0,T1 opposite-lock laps,none stated (binomial: 0/2 has p~0.55),8 of 31 laps at the previous rake,T1 opposite-lock laps fall to <=2 in 12,rate not reduced over ~10+ laps,refuted,"§8 Sep s144 prediction table (holding n=2); §s146 'FALSIFIER 2 FAILED' (5 of 15)",config B/C
2026-09-08,s144,rh_r,down,-20.0,T5-exit rear-slip peak,not established,race median 1.090 max 1.264,peak < 1.15,peak >= 1.15,open,"§8 Sep s144 prediction table ('holding n=2')",config B
2026-09-08,s144,rh_r,down,-20.0,RR wear per lap (HUD gauge),not established,race 0.054/lap,RR wear < 0.054/lap,>= 0.054/lap,open,"§8 Sep s144 prediction table ('not measurable in 3 laps')",config B
2026-09-08,s139-143 -> s144,rh_r,down,-20.0,on-power rotation index (T3/T5 exit),T3 0.00058; T5 0.00104,config A (n=15),stated cost: less rotation,n/a,unresolvable,"§s145 table: A->B T5 -0.00064 inside floor; T3 -0.00113 about at floor. Driver located the cost on acceleration (§s144 table)",config B
2026-09-08,s144 -> s145,lsd_a,down,-6.0,on-power rotation index T3/T5 exit; rear exit slip-split p95,T3 0.00058; T5 0.00104 (odd/even split of 15 race laps),config B (n=2),exit split p95 opens above 0.03 at T3 and T5; rotation back,unchanged split AND no driver report of change,refuted,"§8 Sep 'NEXT CHANGE, ISSUED, session 145'; §s145 'REFUTED. I had the direction backwards' (T5 -0.00170)",config C
2026-09-08,s144 -> s145/146,n/a (hypothesis: T3-exit kerb contact is downstream of on-power rotation),n/a,n/a,T3-exit kerb contact rate,not established,16 of 27 race laps,kerb contact falls if on-power rotation returns,rate does not fall -> kerb problem separate,unresolvable,"§8 Sep HYPOTHESIS; driver correction on s144 L2; §s146 'T3 exit bit for the SIXTH time' (rate not recomputed; reclassified as a placement problem)",config C/D
2026-09-01,not stated,lsd_a,up,step not stated in this file,rear wheel-speed slip split at exits,none (channel sat at 0.0000 through a 6-click change),not stated,diff is an exit lever,split median 0.0000,unresolvable,"§8 Sep lines 300-304 and §s145 'THE SPLIT WAS THE WRONG INSTRUMENT' (1 Sep refutation retired)",pre-Run 3
2026-09-08,s145 -> s146,lsd_a,up,+12.0 (+6.0 from the pre-s145 setting),on-power rotation index T5 exit,T5 0.00104,config C (n=3); race config A (n=15),T5 index rises above 0.0089; front scrub below +0.0082,index at or below 0.00788,confirmed,"§s145 'NEXT CHANGE, ISSUED, session 146'; §s146 'FALSIFIER 1 FAILED' (0.00748 n=10) - but against the race baseline at a different rake; the file's verdict is that the axis is confirmed (monotonic at ~2x floors across the two steps), and that verdict is kept",s146 (s147's table calls it config C)
2026-09-08,s144 -> s146,lsd_a,up (the +6.0 pp step from the pre-s145 setting only),+6.0,on-power rotation index T5,T5 0.00104,config B (n=2),n/a,n/a,unresolvable,"§s146: the +6.0 pp step moved T5 +0.00024, INSIDE the floor; the full +12.0 pp step is monotonic at ~2x floors. Driver prefers the higher setting: his call (rule 1). Cost: 2 T5-exit spins in 10 laps",s146
2026-09-08,s146 -> s147,lsd_a,down,-2.0,none (below the instrument's resolution),T5 0.00104,none,none (driver feel adjustment; the file says it is not a test),none,unresolvable,"§s147 as RUN ('BELOW THE INSTRUMENT'S RESOLUTION and is not a test')",config D
2026-09-08,s146 -> s147,lsd_b,up,+5.0,laps with sub-0.90 rear frames at T1 (240-425 m),none stated; the file says ~22 laps needed to prove absence,2 of 15 laps (s146),laps with rear brake lock at T1 fall to 0,rate unchanged over 12 laps,open,"§s147 as RUN; §s147 'it WORKED' (0 of 5) - scored open: the file's own arithmetic needs ~22 laps, 12 were asked for, 5 run. The file's own power arithmetic says n=5 is short; see (b)-D5",config D
2026-09-08,s146 -> s147,lsd_b,up,+5.0,T1 opposite-lock laps,binomial: N=12 gives p 0.008 (file's own arithmetic),5 of 15 laps (33 %),T1 opposite-lock laps fall below 2 in 12,rate unchanged over 12 laps,unresolvable,"§s147 as RUN (12 laps requested); result 2 of 5 laps, corrections smaller (-7.0 deg vs -27.9/-18.6); only 5 laps run",config D
2026-09-08,s146 -> s147,lsd_b,up,+5.0,entry rotation index T1 (brake >=20 %); mid-corner rotation index,entry 0.0033 (4 Sep); mid-corner T1 0.00086 hairpin 0.00027 T5 0.00026,config C,stated cost: the car will not rotate into the corner,n/a (named cost),confirmed,"§s147 'WHAT IT COST' (entry 0.01197 -> 0.00485; mid-corner lost at all three corners by 2-3.6x floor); driver 'lsd_b is too high'; AXIS-REGISTER lsd_b 'REFUSED'",config D
2026-09-08,s147 -> s148,arb_f,softer,-22.2,mid-corner rotation index (off both pedals); front mid-corner slip; roll (front/rear L/R suspension split),T1 0.00086; hairpin 0.00027; T5 0.00026; roll not established,config A (race sheet),mid-corner rotation above best on file at every corner; front slip mid-corner below +0.020,rotation unchanged or front scrub not falling,refuted,"§s147 'NEXT session 148' item 2; §s148 'REFUTED. His report holds' (both hairpins -2x floor; roll +1.5-3.6 mm both ends); AXIS-REGISTER arb_f 'CLOSED. Refuted twice'",config E
2026-09-08,s148 -> s149,arb_r,stiffer,+22.2,S2 sector median (s); driver report,not established (S1/S3 used as controls),S1 and S3 medians (unmoved); config A S2 median,mid-corner rotation clears best on file; total roll under config A,rotation unchanged OR rear mid-corner slip above the front's,confirmed,"§s148 'NEXT session 149'; §s149 'THE BEST THE CAR HAS BEEN' (S2 median -0.449 s; two fastest S2s in archive); AXIS-REGISTER arb_r",config F
2026-09-08,s148 -> s149,arb_r,stiffer,+22.2,mid-corner rotation index,T1 0.00086; hairpin 0.00027; T5 0.00026,config A,rotation clears best on file at every corner,rotation unchanged,unresolvable,"§s149 'my instrument missed it' (all three inside/at floor); the file treats this as instrument blindness, not refutation; see (b)-D6",config F
2026-09-08,s149,arb_r,stiffer,+22.2,Bus Stop grass rate,not established,9 of 17 laps at the previous rear bar,the stiffer rear bar does not make the Bus Stop launch worse (the named risk does not happen),grass rate rises,confirmed,"§s148 'THE RISK'; §s149 'The risk I named did NOT happen' (3 of 9)",config F
2026-09-08,s149 -> s150,de_r,up,+26.7,T1 rear-brake-lock laps; Bus Stop grass rate; S2 median; driver report,not established,s149 (0 of 9 rear-lock laps; 3 of 9 grass),T1 rear lock stays 0; opposite-lock < 2 in 12; Bus Stop grass < 3 in 9; S2 median <= 35.9,Bus Stop rate unchanged or S2 going backwards,refuted,"§s149 'NEXT ... de_r'; §s150 'REFUTED after 2 laps. Reverted' (1 of 2 laps rear lock; driver 'lost rotation on throttle'); n=2; AXIS-REGISTER de_r",s150
2026-09-08,s144-s146 (T3 exit),n/a (T3-exit off / kerb placement),n/a,n/a,distance of lift / kerb / grass per event,not established,n/a,T3-exit offs are a placement / extension problem not touched by any change so far,n/a,open,"§s144 '⛔ Lap 2 spun at 1,881 m'; §s146 'The T3 exit bit for the SIXTH time'",-
2026-09-04,s120-s150 (Bus Stop),n/a (Bus Stop kerb launch),n/a,n/a,Bus Stop grass rate; RR wheel extension,not established,n/a,an extension event; rear rebound is the lever (tested: refuted),n/a,open,"§7 Sep (de named there as the untried axis); §s150 (the de_r lever was refuted, launch remains)",-
```

**Notes, Daytona (arithmetic is step ÷ span, Huracán v1.71 ranges)**

- Run 1a -> Run 2: rh_f −4 mm ÷ 25 = −16.0 pp · cam_f +0.4° ÷ 6° = +6.7 pp · toe_f −0.08° ÷ 2.00° =
  −4.0 pp. The file records no reason or verdict for these three. The same step also changed the 6th
  ratio, which has no range.
- toe_f 3 Sep: +0.08° ÷ 2.00° = +4.0 pp. The register says toe should be *issued* in absolute
  degrees, because percent hides the useful step size. The ledger still holds only pp.
  ⚠️ Run 4 also carries the dc_r change (Note 1) and a driver bb move. The file dates the bb move
  both to "run 4" and to "before 3 Sep", so it is ambiguous. The toe verdict is not an isolated
  one-change result, and the file does not mention the confound.
- dc_r: −4 ÷ 20 = −20.0 pp.
- cam_f 3 Sep: −0.4° ÷ 6° = −6.7 pp. The driver said *"braking was better and the turn in
  improved"*, backwards from the textbook. The file scores nothing, because camber has no telemetry
  ground truth. It was adopted into the 4 Sep baseline.
- df_f: +40 ÷ 100 = +40.0 pp (s119 is a different-day reference). df_r: +50 ÷ 200 = +25.0 pp.
  Run 7 went back to the baseline: df_f −10 ÷ 100 = −10.0 pp, df_r −15 ÷ 200 = −7.5 pp. Outcome
  `refuted` follows F4's own words: *"cannot work at this magnitude … measured rather than argued"*.
  The register's word is "Invisible". **What is refuted is ±25–50 clicks as a usable lever. The
  direction is not refuted.** Lap time cannot rank the runs (F5: learning ~0.3 s per run).
- Camber sweep: cam_f −1.0° ÷ 6 = −16.7 pp; cam_r −0.2° ÷ 6 = −3.3 pp; cam_f +2.0° ÷ 6 = +33.3 pp;
  cam_r +2.8° ÷ 6 = +46.7 pp; the front sweep spans 3.0° ÷ 6 = 50.0 pp.
- lsd_b 4 Sep: +12 ÷ 100 = +12.0 pp (range 0–100 stated at line 222). −5 ÷ 100 = −5.0 pp.
- dc: −8 ÷ 20 = −40.0 pp front, −6 ÷ 20 = −30.0 pp rear. The
  verdict and the 32.3 mm vs 30.5 mm numbers are only in the AXIS-REGISTER and RECONCILIATION
  (§AB). This file carries only the word "falsified" (line 267). ⚠️ Line 217 records that an
  out-of-range value was once proposed for dc_r (outside the slider's range).
- rh_r: −6 mm ÷ 30 = −20.0 pp. The file also records the feed verifying rh: the rear channel moved
  6.1 mm, front unmoved. That is a verification, not an experiment.
- lsd_a: −6 ÷ 100 = −6.0 pp; the reverse step +12 ÷ 100 = +12.0 pp; the driver trim −2 ÷ 100 =
  −2.0 pp. lsd_b s147: +5 ÷ 100 = +5.0 pp.
- arb: ±2 clicks ÷ 9 = ±22.2 pp.
- de_r: +8 ÷ 30 = +26.7 pp. Refuted on two spoiled laps plus the driver's report. Only the upward
  step is refuted.
- **Reverts, not rows:** lsd_b back one step after s147, arb_f back after s148 and de_r back after
  s150. Each is "a REVERT … not an experiment". The 6th-gear shortening proposal was withdrawn
  4 Sep, because the limiter never fires in 6th across 79,090 frames. It is in list (a).
- **Refusals, not rows:** bb forward (AXIS-REGISTER; T1 front slip median 0.878 against RS ABS
  0.92–0.935). The register calls toe_f toe-out the "last unspent front-grip lever", but it was
  never issued, so it has no row.
- F6 (the 5,200 m track-limits penalty) and the out-lap misdetection on s149 L7 are app work, not
  ledger rows.

## Items with no percent-of-range delta

Cited by location only; the absolutes are read at the cited section and restated nowhere.

| id | car × circuit | item | where the absolutes are | why no pp |
|---|---|---|---|---|
| a-D1 | Huracán × Daytona | 6th gear ratio change, Run 1a → Run 2 (1 Sep) | header table, "6th gear" row | gear ratios have no slider range |
| a-D2 | Huracán × Daytona | 6th-gear shortening proposal, WITHDRAWN 4 Sep (limiter never fires in 6th across 79,090 frames) | header table, "6th gear" row, Run 4 cell; `RECONCILIATION.md` §Z1 | gear ratio |
| a-D3 | Huracán × Daytona | restrictor/ECU drift found with no change row (not an experiment; recorded for completeness) | §"Why this file exists", defect 3 | performance values have no range |

## Contradictions on file

Surfaced, not averaged (`CLAUDE.md` §4 rule 1). The latest is kept as the outcome; both are cited.

- **D1.** §7 Sep says `rh_f` "has never been moved since 1 Sep and **no ride-height A/B exists
  anywhere in this car's archive**". The header table shows a `rh_f` change between Run 1a and
  Run 2 on 1 Sep. The two reconcile if that step (four keys at once) is not counted as an A/B.
  Kept: no clean `rh_f` A/B exists.
- **D2.** The 1 Sep refutation of the diff as an exit lever came from raising `lsd_a` and reading
  the rear wheel-speed split. §s145 retires it: "A measure that cannot see the change cannot
  refute the lever", and `reference_daytona_corner_priority`'s ⛔ block is retired. Kept:
  `unresolvable`. s146 then shows the axis is real.
- **D3.** The s144 prediction table scores T1 opposite-lock "holding, NOT YET EVIDENCE". §s146
  reports "FALSIFIER 2 FAILED" (5 of 15). Kept: `refuted` for the entry-stability rationale. The
  rake change itself stays `confirmed` on pace and the driver.
- **D4.** §4 Sep evening says the driver's *"more rotation on other corners under brakes" is
  measured*, yet the figures beside it show rotation-under-brakes **down** at z3 and z4. §s146
  later says the stiffer `lsd_b` "measurably **reduced** rotation on release under brakes at z3
  and z4 on 4 Sep". The sentence and its numbers disagree. Check `RECONCILIATION.md` §AB (not
  read here). Row kept on the numbers.
- **D5.** s147 scores the stiffer `lsd_b` as "it WORKED" on T1 rear lock at **0 of 5 laps**. The
  same file had just calculated that the rear-lock half needs **~22 laps** to prove absent, and it
  requested 12. The AXIS-REGISTER repeats "does kill the rear brake lock". Kept: `open` - the
  file's 'it worked' is recorded, and the row waits for the laps the file itself asked for.
- **D6.** The s149 `arb_r` falsifier was "rotation unchanged". It fired literally: all three
  corners were inside or at their floor. The change is still `confirmed`, on S2 median −0.449 s
  plus the driver. The file resolves this explicitly as instrument blindness ("Do not let a null
  on a derived index outvote a driver report plus an outcome measure"). Kept: two rows,
  `confirmed` for the axis and `unresolvable` for the index.
- **D7.** Config letters are reused. In the s145 table, "C" is the reduced-`lsd_a` run. In the
  s147, s148 and s149 tables, "C" is the s146 setup. A ledger keyed on config letters would merge
  two different cars. The rows here key on session ids.
- **D8.** The AXIS-REGISTER and the Daytona close-out ("What transfers") say the stiffer `lsd_b`
  "**halved**" T1 entry rotation. §s147 says "**a 60 % cut**" (0.01197 → 0.00485 = −59.5 %).
  Kept: s147's figure.
- **D9.** `dc` softer is "FALSIFIED at the Bus Stop" (AXIS-REGISTER; Daytona line 267). The
  driver says it is fixed, and the file leaves that disagreement unaveraged (rule 1). The plan
  (L5) lists Daytona's `dc` setting among open items that were never surfaced. Kept: `refuted` on
  the instrument AND `confirmed` on his report - two rows, as with D6 (rule 1).
- **D10.** After s144 the driver placed the rake change's cost "on ACCELERATION". The s145
  on-power index puts the rake step inside its floor at T5 ("not resolvable … not what he felt
  most"). This is not averaged. Kept: `unresolvable` on the index. The report stands as the
  driver's.
- **D11 / B1 (cross-file).** Three places call rake against Bathurst clearance a tension to settle
  first: the AXIS-REGISTER ("Settle that tension first"), the Daytona close-out ("in tension with
  the rake finding"), and the Daytona "What does NOT transfer" list. The Bathurst file says "it
  dissolves … Settled. Not a tension": rake is the difference between the ends, clearance is the
  level of both. Kept: the Bathurst file, the latest.
