# Experiment ledger — Porsche 911 RSR '17 × Sardegna Road Track A

The car and its settings: [`brain/car-state/rsr-sardegna-road-track-a.md`](../car-state/rsr-sardegna-road-track-a.md) - the only place a value is written. This file holds keys, directions and deltas in percentage points of slider range, never a setting. Conventions: [README](README.md).

Seeded 11 Sep 2026 from the car-state file at `2945402` 2026-09-11.

Ranges: RSR v1.71, 21 Aug 2026, verified (see the header). The file's own percentages reconcile
with them (for example, Rev A's natural frequencies). The file says LSD is "ABSOLUTES … register has
not been re-read since". The register shows the RSR's LSD *was* re-read on v1.71, which is (b)-R17.
It matters only for the open lsd_a sweep row.

### 3a. Rev A to Rev E, and the gearbox (5 Sep, sessions 128–132)

```csv
date,session_ids,key,direction,delta_pct_range,instrument,measured_floor,control,prediction,falsifier,outcome,source,car_state_rev
2026-09-05,s128,nf_f;nf_r;de_r,stiffer;stiffer;stiffer,nf_f +17.5; nf_r +20.0; de_r +13.3,body-height channel (share of clean frames below 25 mm); driver report of harshness,not established,none (carried from the Monza Rev C sheet; no Sardegna control),springs let the platform settle over the crests without sinking,harsh over moderate kerbs or rear grip lost on sweeper exits (then de_r backs out first),confirmed,"§7 Predictions row 1; §s128 'The three Rev A predictions' row 1 (0.27 % of frames < 25 mm; no harshness); §9 Sep ¶3 corrects the zone description (see (b)-R5)",Rev A
2026-09-05,desk (s128 section),df_f;df_r,up;up,df_f +30.0; df_r +30.0,front aero share arithmetic,n/a (arithmetic),Monza sheet front share,equal percent of range front and rear leaves aero balance where he is used to it,front share moves,refuted,"§1 (aero moved by the same share of range at each end); §s128 'And an error of mine in Rev A itself' (the front share moved); §s130 'And it corrects an error of mine'",Rev A
2026-09-05,s128; s130-132; s153,n/a (RH worst-wheel wear at 8x),n/a,n/a,HUD wear gauge (hud-video),gauge ticks in 36ths = +/-0.0056/lap over 5 laps (§11),n/a,worst-wheel wear w <= 0.055/lap,w >= 0.068/lap,confirmed,"§7 row 2 (UNTESTED at s128: gauge null); §11 (s130-132 RR 0.0528); §14 (s153 RH 0.0498). Scored from the file's figures",Rev A -> Rev E
2026-09-05,s153-155,n/a (stop count follows from w),n/a,n/a,fuel per lap at 3x; stint-cap arithmetic,not established,n/a,w <= 0.055 kills the two-stop worry -> one stop,w >= 0.068 -> two stops,refuted,"§7 row 2; §13 'FUEL BINDS HERE' (no one-stop at full send on any compound: fuel is the binding limit, not wear); see (b)-R10",Rev F
2026-09-05,s128,n/a (fuel model: Monza burn scaled by distance and throttle share),n/a,n/a,fuel L/lap (15 laps),not established,Monza v1.71 L/s,fuel 4.4-5.4 L/lap,outside the band,refuted,"§7 row 3; §s128 row 3 'FALSIFIED as a model' (6.29-6.61 L/lap at full RPM; fuel tracks time under load not distance)",Rev A
2026-09-05,s128 -> s156/s157,n/a (short-shifting fuel as stated in §7),n/a,n/a,fuel L/lap while short-shifting,not established,n/a,short-shifting burns 4.4-5.4 L/lap,outside the band,open,"§7 row 3 ('untested as stated' at s128: no beep existed). §21 later reports short-shift burns inside the band; never re-scored. See (b)-R9",Rev A
2026-09-05,s128 -> s129,bb,rearward,+10.0,front-minus-rear mean slip gap in braking frames,0.003-0.006 (nearest class: front L/R split),s128 (-0.0200),gap narrows to -0.010 or shallower,rear frames < 0.90 exceed 2 % or rear steps out on entry,unresolvable,"§s128 'Rev B — ONE change'; §s129 'THE PREDICTION IS FALSIFIED' (+0.0007/+0.0014), reclassified in §'Rev B CONFIRMED' as a BLIND instrument (ABS pins front slip at the RH working point 0.888); see (b)-R3",Rev B
2026-09-05,s129,bb,rearward,+10.0,driver report (the only working instrument while ABS pins the front),n/a,s128,more entry rotation,he reports it worse or looser (then revert),confirmed,"§'Rev B CONFIRMED' ('more rotation on entry and I could move my brake markers forward')",Rev B
2026-09-05,s129 -> s130,bb,rearward,+20.0,rear p5 slip under heavy braking; rear share inside the ABS band; driver report,0.003-0.006,s129 (p5 0.9310),rear p5 -> ~0.9242 and more entry rotation with braking stable,rear steps out on brake RELEASE (then one click less),confirmed,"§'Rev C'; §s130 'Rev C CONFIRMED — and I under-predicted it by 3x' (0.9118; 6.4 % in ABS band; 'end of this axis')",Rev C
2026-09-05,s130 -> s131,df_f,up,+20.0,driver report (telemetry cannot arbitrate),corner steering-per-g index: 2 sd = 62.2 % of mean (17 passes; aero unchanged),none usable,more front bite mid-corner; most at the fast left (3641-3788 m),rear loose on fast-corner exit (then half the step),confirmed,"§'Rev D'; §s131 'Rev D CONFIRMED' ('much better')",Rev D
2026-09-05,s130 -> s131,df_f,up,+20.0,peak lat_g in the named corner,within-session 0.532 g (s128 sd 0.152),s128 -> s129 no-aero drift +0.411 g,n/a (read afterwards as a confirmation),no-change drift of the same size,unresolvable,"§s131 'RETRACTED IN THE SAME PASS: the lateral-g confirmation'",Rev D
2026-09-05,s128-130 -> s131,df_f,up,+20.0,mean terminal speed,0.56-2.77 km/h (project terminal floor),s128/s129/s130,none (measured side-effect: no drag cost),n/a,confirmed,"§s131 '[MEASURED] Twenty units of front wing cost NO measurable top speed'",Rev D
2026-09-05,s131 -> s132,df_f,up,+20.0,driver report,n/a,s131,more front bite again; mostly fast corners,rear loose on fast-corner exit (then half the step),confirmed,"§'Rev E'; §s132 'Rev E CONFIRMED' ('much more pointed all round'); aero axis CLOSED",Rev E
2026-09-05,s130 -> s132,df_f,up,+40.0 across both steps,median sector times (thirds),within-session sd 0.03-0.90 s (n=2-11),no-change steps s128->129->130 (S1 moved -0.489),'aero helped all round the track' (driver's timing claim),no-change drift of the same size,unresolvable,"§s132 'But proves the aero helped all round track does NOT survive the control'",Rev E
2026-09-05,s130 -> s132,df_f,up,+40.0,S3 sector median,not established (n=2 clean laps),S1/S2,S3 (all three fast corners) should gain most (v-squared),S3 gains least,open,"§s132 'OPEN QUESTION — S3 is the fast sector and it moved least'",Rev E
2026-09-05,never issued,df_r,down,-15.0,driver report (where the residual understeer is),n/a,n/a,next move if residual understeer stays in fast corners,n/a,open,"§'Rev E' ('The next moves if needed'); superseded by §17's choice, see (b)-R14",Rev E
2026-09-05,never issued,arb_f,softer,-11.1,driver report,n/a,n/a,next move if residual understeer is in slow corners,n/a,open,"§'Rev E' next moves; §17 declines it on the Spa/Daytona transfer ('Why not arb_f down'); see (b)-R14",Rev E
2026-09-05,desk (s128 data),fg,shorter,+10.0,gear-ratio arithmetic; rpm at the 265.1 km/h terminal,n/a (arithmetic),current box,shortening the final drive puts 6th to use (6th never engaged in 48640 frames),final drive only renames 5th as 6th,refuted,"§s128 'The gearbox is the bigger prize'; §'RETRACTED: 6th is never engaged is not a loss' (0.02 % apart; 5th already at peak power at terminal)",Rev B
2026-09-05,desk (s128 frames),top;gear1,longer 1st,range unknown,simulation over 32483 full-throttle tarmac frames with upshift at the beep,n/a (simulation),n/a,limiter bouncing in 1st (666 frames) is gearing: 1st too short,0.00 % rev-limited when upshifting at the beep,refuted,"§'The real loss' (1st too short); §'RETRACTION: the limiter bouncing is SHIFT TIMING'",Rev B
2026-09-05,probe (screenshot only; not driven),top,down,-10.0,Manual Adjustment ratios at two top settings,n/a (screen reading),current top setting,Shelby precedent: the top slider moves 1st far more than 6th (narrows the spread),higher top = longer gears AND a wider spread on this car,refuted,"§'The probe'; §'top mapped on this car — the opposite of the Shelby precedent'",Rev B/C
2026-09-09,s153-155,top;fg,down;down,top -10.0; fg -16.7,6th-gear full-throttle frames; max speed in 6th (FEED),not established,s128 (0 frames in 6th),6th comes into use with ~11 km/h of tow headroom and never meets the limiter,6th on the limiter or unused,confirmed,"§s130 'Gearbox — issued'; §'Gearbox CONFIRMED — the 6th-gear display anomaly'; §18 'Box prediction HELD' (11223 frames; max 262.8 vs 276.5 at the limiter)",Rev F sheet
2026-09-09,s153-155,top;fg,down;down,top -10.0; fg -16.7,mean rpm at full throttle; share above 7500 rpm; 1st top speed,not established,s128 (68.0 % above 7500),powerband share 68.0 -> 76.9 %; 1st gets longer,none stated,open,"§'The recommendation, scored against his own speeds' ('verifiable without lap time'); never reported after fitting",Rev F sheet
2026-09-09,s153-154,shift_points id 1 (5th upshift),pre-issued 5th point below gears 1-4,range unknown,tools/shift_points.py comparable-bin wins,not established,old box's ratio step,5th upshift earlier than gears 1-4 [ASSUMED from the old box],every gear 1-5 reports LIMITER,refuted,"§'Shift table on the new box'; §18 'the number I pre-issued was wrong'",Rev F
2026-09-05,none yet,lsd_a,full-span sweep,range known (0-100); step not specified,not stated,not established,none,open question: 1.71 changed the torque map; nudging toward the doctrine band answers it with a guess,none stated,open,"§4 'Why LSD acceleration stayed' (a full-span sweep is its own run)",Rev A
2026-09-05,none,n/a (pit loss at Sardegna),n/a,n/a,measured pit loss,not established,n/a,declared 20.0 s; reference 20-22 s low confidence,n/a,open,"§8 'Still open' ('a track constant — measure once')",Rev A
2026-09-05,s128-,n/a (FFB after 1.71),n/a,n/a,driver confirmation,n/a,n/a,FFB unchanged since 1.71,n/a,confirmed,"§8 'Wheel / FFB settings'; §'Gearbox RETRACTED' ('FFB unchanged since 1.71 (rank zero 1b CLOSED)')",Rev B
```

**Notes, 3a (RSR v1.71 ranges, step ÷ span)**

- Rev A against the Monza sheet: nf_f +0.35 Hz ÷ 2.00 = +17.5 pp; nf_r +0.40 ÷ 2.00 = +20.0 pp;
  de_r +4 ÷ 30 = +13.3 pp; df_f +30 ÷ 100 = +30.0 pp; df_r +60 ÷ 200 = +30.0 pp. These match the
  file's own percentages, which stay in the car-state file. Three keys moved at once, and the
  file says so. It names de_r "the least-evidenced … first to back out".
- bb: the file states "`bb` is 10 % of range per click". So one click = +10.0 pp (1 ÷ 10 span)
  and two clicks = +20.0 pp. `+` is rearward on this car, confirmed by the driver 5 Sep.
- df_f: +20 ÷ 100 = +20.0 pp per step, consistent with the file's own percentages. The held-back
  "restore the Monza ratio" correction (+11 ÷ 100 = +11.0 pp) was superseded by Rev D. No row.
- df_r candidate: −30 ÷ 200 = −15.0 pp. arb_f candidate: −1 ÷ 9 = −11.1 pp.
- Gearbox: fg proposal +0.300 ÷ 3.000 = +10.0 pp (desk-refuted, never driven); top probe
  −60 ÷ 600 = −10.0 pp; fitted fg −0.500 ÷ 3.000 = −16.7 pp. The alternative final drive
  (−0.320 ÷ 3.000 = −10.7 pp) was rejected when the 6th-row display factor (×1.060) was shown to
  be systematic. At that setting 6th would have topped out below the measured terminal. No row.
- The Rev A drag claim and every sector claim are "consistent with" at best, because learning ran
  at −5.9 s across session 128 alone. The file downgrades every such timing claim from
  [MEASURED] to [DRIVER REPORT]. The outcomes above follow the file.

### 3b. 9–11 Sep: platform, compounds, fuel-save, arb_r, race sim (sessions 153–159)

```csv
date,session_ids,key,direction,delta_pct_range,instrument,measured_floor,control,prediction,falsifier,outcome,source,car_state_rev
2026-09-09,s128-132 (re-derived),n/a (cause of the front ride-height change over a run),n/a,n/a,front/rear suspension channel vs fuel on the clean straight (mm/L),s128 slope se 0.0061 mm/L,between-session estimate +0.0115 +/- 0.0443 (n=6),cause is fuel (tank in the nose) not tyre wear,a channel that could carry wear (tyre_radius_m is constant),confirmed,"§4 ('CONFOUNDED'); §10 '§4 RESOLVED. It is fuel' (driver report plus mechanism and sign check); see (b)-R11",Rev E sheet
2026-09-09,s128-132 (re-derived),df_f,up,+40.0 (both steps),front suspension residual on the straight; front in the long right onto the straight,null spread 0.66 mm (three unchanged sessions); long-right zone floor 0.633 mm,the three sessions before the aero steps,none (unpredicted: the wing put ~1.4 mm into the front spring),n/a,open,"§5 '[MEASURED, weak]' ('held to suggestive, not settled'; all of it in the second step)",Rev E sheet
2026-09-09,not issued,nf_f,stiffer,+10.0,driver report,not established,n/a,pre-loaded: the answer if the nose goes light or fast-corner understeer arrives as fuel burns,n/a,open,"§8 'Pre-loaded, not issued' ([ASSUMED] until he reports)",Rev E sheet
2026-09-09,none,rh_f;rh_r;nf_f;dc_f,none specified,n/a,none yet,not established,n/a,recorded as untested in the measurement store (ids 79-87),n/a,open,"§9 'The store had nothing on this car'",Rev E sheet
2026-09-09,next 12-lap stint,n/a (front ride height over a stint),n/a,n/a,front suspension channel across a full stint with a refuel,not established,n/a,the nose rises ~3 mm as the tank empties and resets on the out-lap after a refuel,front flat across the stint or no reset after the stop,open,"§9 'Open predictions' row 1-2; amended in §12 'Open predictions — amended' row 1",Rev E sheet
2026-09-09,next stint,n/a (driver feel late in a stint),n/a,n/a,driver report,n/a,n/a,the car feels different late in a stint at the front not the rear,he reports the rear or nothing,open,"§9 'Open predictions' row 3",Rev E sheet
2026-09-09,s153-155,n/a (worst wheel over a full-length stint),n/a,n/a,HUD wear gauge per wheel,gauge tick 0.0278,Monza worst wheel was rear-left,rear-right stays the worst wheel over a full-length stint,any other wheel leads at 12 laps,confirmed,"§12 amended row 2; §14 ('worst wheel REAR-RIGHT throughout'; s154 ran 14 laps). Scored from the file's figures",Rev F
2026-09-09,s153 (length not stated),n/a (full-stint RR wear rate vs early-life),n/a,n/a,HUD wear gauge,gauge tick 0.0278,s130-132 rate 0.0528,full-stint rate is at or above 0.0528/lap (short runs are a lower bound),12-lap rate below 0.0528,open,"§12 amended row 3. §14/§21 report RH s153 at 0.0498 +/- 0.0006, below 0.0528 but inside the gauge's +/-0.0056/lap resolution (s153 is 14 laps in the store); never scored. See (b)-R12",Rev F
2026-09-09,s153-155,n/a (§3: 'fuel does not bind here; the tyre does'),n/a,n/a,fuel L/lap at 3x (67 counted laps); stint-cap arithmetic,not established,n/a,tyre is the binding stint limit at Sardegna,fuel binds before the tyre,refuted,"§3; §13 'FUEL BINDS HERE. Section 3's headline is overturned' (7.046 L/lap). §23 inverts again when saving; see (b)-R10",Rev F
2026-09-09,not run,n/a (refuel rate),n/a,n/a,one practice stop taking fuel with the app recording,not established,n/a,refuel rate measures 1.0 L/s +/- 0.1,it does not (stop-count table re-run),open,"§15 'THE REFUEL RATE HAS NEVER BEEN MEASURED'; §18 open row 3",Rev F
2026-09-09,s153-155 (cross-session),n/a (compound pace delta RM vs RH),n/a,n/a,fuel-matched lap pairs; same-session back-to-back not yet run,not established,n/a,a same-session three-compound run reproduces RM about 1.7-1.9 s/lap faster than RH,RM under ~1.0-1.2 s faster,open,"§14; §18 open row 4; §25 row 4; §23 ('12 seconds is ... a tie'); §39 ('Still no compound call')",Rev F -> H
2026-09-10,s156; s157,n/a (short-shift at ~600 rpm below the performance point),n/a,n/a,fuel L/lap; clean-lap median,not established,s154,saves 20-25 % fuel; costs under 1.0 s/lap,> 6.0 L/lap; median > 1.0 s off s154,open,"§19g rows 1-2. Superseded: the test ran ~1000-1100 rpm below (§20c) so these rows were never tested as stated",Rev F
2026-09-10,s157 (within-stint),n/a (short-shift effect on RR wear: Racing Medium),n/a,n/a,HUD wear gauge per lap within one tyre set,combined error 0.0023 (s157 split); control: s154 full-send wear flat with age (+1.7 %),s157 laps 10-14 full send on the same tyres,short-shifting measurably lowers rear-right wear,wear trace matches full send within one tick,confirmed,"§19g row 3; §20e row 4; §22 'The tyre question, ANSWERED' (0.0645 vs 0.0706 = -8.7 %, 2.7x combined error)",Rev F
2026-09-10,s153 -> s156 (between-session),n/a (short-shift effect on RR wear: Racing Hard),n/a,n/a,HUD wear gauge per lap,combined error 0.0008,s153 full send,short-shifting lowers rear-right wear on RH,within one tick of full send,unresolvable,"§20e row 4; §22 ('NOT MEASURABLE': 0.0007 vs 0.0008; between-session, weaker)",Rev F
2026-09-10,s156; s157,n/a (short-shift puts the race on 29 laps not 28),n/a,n/a,race-time arithmetic on the measured lap-time cost,not established,n/a,saving buys a whole extra lap (29 not 28),race pace > ~20 s off plan,refuted,"§19c; §19g row 4; §21 'THIS IS THE NUMBER THAT KILLED THE 29TH LAP' (1.00-1.08 s/lap); §39 reaches 29 by another route, see (b)-R13",Rev G
2026-09-10,s156,n/a (RH short-shift fuel at the fuel-save beep),n/a,n/a,fuel L/lap,not established,s153 full send,RH burns 5.3-5.6 L/lap,burns over 6.0 L/lap,confirmed,"§20e row 1; §21 (5.165 L/lap; 'bigger than predicted'). Scored from the file's figures; saving exceeded the band",Rev G
2026-09-10,s156; s157,n/a (RM short-shift fuel vs RH),n/a,n/a,fuel L/lap,not established,n/a,RM at the same beep burns about the same as RH,compounds differ by more than 0.3 L/lap,confirmed,"§20e row 2; §21 (5.247 vs 5.165). Scored from the file's figures",Rev G
2026-09-10,s157 (within-stint); s153 -> s156,n/a (short-shift lap-time cost),n/a,n/a,best/clean lap within one stint,not established (lap sd 0.918 s elsewhere in the programme),s157 laps 10-14 same tyres,cost lands between 0.7 and 1.5 s/lap,cost > 1.5 s/lap,confirmed,"§20e row 3; §21 (1.00 within-stint; 1.081 between sessions). Scored from the file's figures",Rev G
2026-09-10,s156,n/a (RH reaches 17 laps on one tank when saving),n/a,n/a,fuel remaining,n/a,n/a,RH reaches 17 laps on one tank,it does not,confirmed,"§20e row 5; §21 ('the hard ran 19 laps on one tank, finishing on 1.7 L')",Rev G
2026-09-10,second stint needed,n/a (medium wear saving repeatability),n/a,n/a,within-stint A/B on the gauge,combined error 0.0023,n/a,the medium's 8.7 % wear saving holds over a second stint,a repeat within-stint A/B lands inside 3 %,open,"§25 row 3",Rev G
2026-09-10,s157 L10-14 -> s158 L2-10,arb_r,stiffer,+22.2,steering_deg_per_yaw_rate at neutral mid-corner (lock-per-yaw),9.89 (worst odd/even split in one unchanged session),s157 laps 10-14 (99.55; baseline re-set from 108.22),lock-per-yaw falls by more than 9.89,moves less or rises,unresolvable,"§17 Rev F; §24 Rev G (baseline moved); §28 'THE ROTATION INDEX WAS FOOLED' (fell 20.4 while the rear was sliding; written to the store as unresolvable)",Rev G
2026-09-10,s158 L2-10 vs L12-19,arb_r,stiffer by the +22.2 pp step (the size refuted; the direction confirmed at +11.1 pp - next row),+22.2,driver report; opposite-lock frames per lap; spins per lap,not established,same session laps 12-19 at the +11.1 pp setting (same fuel range),he reports the car finishing corners without extra steering,rear steps out on brake release (then one click),refuted,"§27 'The bracket worked' (197.7 catches/lap; 6 of 9 laps spun); overshoot of the bracket; direction not refuted. §30: the stated falsifier named the wrong symptom",Rev H
2026-09-10,s158 L12-19,arb_r,stiffer (one click),+11.1,driver report; opposite-lock frames per lap; spins,not established,same session laps 2-10 at the +22.2 pp setting,he reports the car finishing corners with less steering,no change or loose rear on brake release,confirmed,"§27 (18.5 catches/lap; 0 of 8 laps spun; driver 'perfect'); §33d ('confirmed', his corner 43.7 -> 5.6 catches/lap)",Rev H
2026-09-10,s158 -> s159,arb_r (wear effect of the one-click setting),stiffer,+11.1,HUD wear gauge RR per lap (RM),gauge tick 0.0278,s154 RM 0.0668 at the previous setting,RM rear-right wear stays within one tick of 0.0668/lap,moves more (all stint lengths re-derived),confirmed,"§32 row 1; §34.1 'WEAR ON THE NEW BAR - HELD' (0.0660 +/- 0.0008)",Rev H
2026-09-10,s159 (race sim),arb_r (catch rate over a stint),stiffer,+11.1,opposite_lock_frames_per_lap,not established,s158 practice 18.5/lap,the 10.7x drop in catches holds over a full stint,catches climb back above ~60/lap as the tyres go off,unresolvable,"§32 row 2; §35 'THE CATCH COUNT DOES NOT SURVIVE A RACE' (metric contaminated by racing: free air 7 vs racing 123)",Rev H
2026-09-10,s159,arb_r (loose rear over 12 laps),stiffer,+11.1,driver report; frame trace at the spin,n/a,n/a,no loose rear over 12 laps,he reports a loose rear (then back one click),confirmed,"§32 row 3; §34.3 (one spin: left pair on the grass first; track limits; 'arb_r is not implicated'). Scored from the file's text",Rev H
2026-09-10,s159,n/a (Racing Medium degradation before ~90 %),n/a,n/a,lap-time trend laps 4-12,+/-0.065 s/lap (trend se),n/a,no degradation on RM before ~90 % worn,a negative trend,confirmed,"§34.2 (-0.043 +/- 0.065 s/lap to 80.6 % worn)",Rev H
2026-09-10,s159,n/a (blind-left exit: track limits),n/a,n/a,off-tarmac frames in the blind left (~3700 m),not established,n/a,the blind-left exit is a repeatable track-limits problem,he runs the line clean over a full stint,open,"§38 row 1",Rev H
2026-09-11,s159,n/a (racing fuel 6.760 L/lap is a tow effect),n/a,n/a,gap_reads (gap ahead); fuel towing vs leading alone,not established,s159 laps 8-12 leading alone,the racing fuel drop is a tow effect,a race led alone also comes in near 6.76,refuted,"§36; §38 row 2; §39 (towing 6.747 vs alone 6.768: tow explains 0.02 of 0.41 L/lap; day-level)",Rev H
2026-09-10,none yet,n/a (free-air catch rate),n/a,n/a,opposite_lock_frames_per_lap split by free air,not established,n/a,in free air on this setting he stays under ~10 catches a lap,a clean-air lap above 30,open,"§38 row 3",Rev H
2026-09-11,s153-159,n/a (driver's hypothesis: random lobby weather = wind),n/a,n/a,acceleration at fixed gear and speed on the main straight; terminal speeds,not established,back straight (94 deg to the main straight),the 9 Sep fuel difference was wind,n/a,unresolvable,"§39 'The wind test' (headwind on 9 Sep supported; rev-limiter and coasting changes are driving; 'Wind and driving cannot be split exactly')",Rev H
2026-09-11,s153-155,n/a (silent 5th-gear beep on 9 Sep explains the limiter time),n/a,n/a,rev-limiter time by gear,not established,n/a,the 9 Sep limiter time came from a silent 5th-gear beep,limiter time is in gears 1-4,refuted,"§39 ('tested and wrong')",Rev H
2026-09-11,none yet,n/a (RM rear-right past 89 % worn),n/a,n/a,15-lap RM saving stint from full,not established,last clean RM lap on file at 89 % (s154 L13),rear-right survives ~97-100 % at the flag,falls away past 90 %,open,"§40 open item 1; §41 ('the single most important run before the race')",Rev H
2026-09-11,s154; s159; s153; s156,n/a (driver claim: lighter second stint wears less),n/a,n/a,heavy half vs light half of a stint on the RR gauge,not established (fuel and tyre age collinear),n/a,tyres wear less with less fuel,no half-stint difference in that direction,unresolvable,"§41 ('this cannot separate them'; -1 / +12 / +2 / +9 %)",Rev H
```

**Notes, 3b**

- arb_r: +2 clicks ÷ 9 = +22.2 pp; one click ÷ 9 = +11.1 pp. The bracket's return leg is the
  −11.1 pp step inside s158 (lap 11 refuel). `is_pit_lap` missed that refuel. The split is known
  only from the fuel jump (§26 lead-in), which is app work.
- §24 re-baselined lock-per-yaw from 108.22 to 99.55. That shift is just inside the 9.89 floor,
  so it is not a finding. §24 also checked that short-shifting does not move the index
  (1.56 < 9.89), which makes it a clean control. The index still fooled the verdict (§28): it
  rewards a loose car. **Never quote it without a stability count beside it.**
- Short-shift rows carry `n/a` keys because the beep is a driving technique. The shift table is
  not a slider and has no range. Steps: ~600 rpm (§19, the Monza A/B size) against ~1,000–1,100 rpm
  actually run (§20c, §21).
- **§26 (the shift-beep re-arm latch)** is a product defect with a stated arithmetic check
  (threshold × 0.95 × ratio step against his real shift rpm). It gets no row. It is app work and
  CLAUDE.md rule 10.
- §16 (the phase deficit: lock-per-yaw 69.9 / 82.6 / 108.2 by phase; front below 0.92 on 19.8 %
  of trail-brake frames) is a measurement that motivated Rev F. It gets no row.
- §13/§14: the compound sweep's measured wear and fuel (RH 0.0498, RM 0.0668, RS 0.1500;
  7.046 L/lap) are measurements, not predictions. The RM stint cap was beaten (lap 13 at 89 %
  normal; lap 14 slow because the tank ran dry). The RS cliffed at 89–100 %.
- §40/§41: the race plan (one stop on RM, fuel-save, 14/15) is the driver's decision. The
  certifier refusal is app work. Neither is a ledger row.

## Items with no percent-of-range delta

Cited by location only; the absolutes are read at the cited section and restated nowhere.

| id | car × circuit | item | where the absolutes are | why no pp |
|---|---|---|---|---|
| a-R1 | RSR × Sardegna | `shift_points` id 1: issued, then the pre-issued 5th point was refuted (§18). There was a one-night hack putting the fuel-save rpm into the performance slot (§20b, "Restore both columns after tonight"). The performance column is back per §26d; **the file never records the fuel-saving column being restored** | §"Shift table — ISSUED 5 Sep"; §18; §20b; §26d | not a slider |
| a-R2 | RSR × Sardegna | the six ratios of the fitted box. `top` and `fg` have ranges, and their rows carry pp | §s130 "Gearbox — issued"; §"Gearbox CONFIRMED" | individual ratios have no range |
| a-R3 | RSR × Sardegna | short-shift depth (~600 rpm planned in §19 against ~1,000–1,100 rpm run in §20–21) | §19a, §19c, §20c, §21 | shift rpm is not a slider |

## Contradictions on file

Surfaced, not averaged (`CLAUDE.md` §4 rule 1). The latest is kept as the outcome; both are cited.

- **R1.** s128: *"His fronts lock. His rears never do"*, from front slip below 0.90 on 15.89 % of
  braking frames. s129: "the front half was misread": that is the ABS working point (RH 0.888).
  Kept: the front reading reports the ABS controller, and the rear finding stands.
- **R2.** s128: "The gearbox is the bigger prize … two of six gears are dead weight". Retracted in
  §"RETRACTED: 6th is never engaged is not a loss". Kept: retracted.
- **R3.** s129: "❌ THE PREDICTION IS FALSIFIED". Then §"Rev B CONFIRMED": the telemetry "was
  BLIND … a blind instrument is not a dissenting witness". Kept: `unresolvable` for the instrument
  and `confirmed` for the driver.
- **R4.** §5.1 reconciled the Rev C gearbox "generator input" and the screen's "Top Speed"
  readout as two different quantities. §"`top` mapped on this car" supersedes that: they were the
  same field and the record was stale. §"The real loss" also stated a position for `top`
  that the probe section shows was wrong. Kept: the probe section.
- **R5.** The s128 Rev A prediction check calls both low body-height zones "straight-line aero
  compression … not a kerb strike". §9 Sep ¶3 corrects the 4,490–4,700 m zone: a loaded corner
  with kerb contact and the lowest reading on file. Kept: ¶3. The prediction's verdict (`confirmed`)
  is unchanged.
- **R6.** s128: "rev limiter firing … the box is too short" (1st). §"RETRACTION: the limiter
  bouncing is SHIFT TIMING". Kept: shift timing.
- **R7.** The 6th-gear display row was "most likely a misread of the screenshot". §"Gearbox
  CONFIRMED": "not a misread and not a game inconsistency", a systematic ×1.060 on two boxes. Kept:
  systematic.
- **R8.** The Rev C, Rev D and Rev E sections say the wear gauge "failed to sample twice/three
  times". §11: "WRONG": s130, s131 and s132 all sampled (13 laps on file). Kept: §11.
- **R9.** Rev A fuel prediction: s128 says "FALSIFIED as a model, **untested as stated**" (there
  was no beep). §21 later measures short-shift burn at 5.165 (RH) and 5.247 (RM) L/lap, inside the
  stated 4.4–5.4 band. It was never re-scored. Kept: the model row `refuted`, the as-stated row
  `open`.
- **R10.** §3: "Fuel does not bind here. The tyre does." §13: "FUEL BINDS HERE. Section 3's
  headline is overturned." §23: once saving, "FUEL STOPS BINDING AND THE TYRE BINDS", which
  "inverts section 13 for the second time". §7's "w ≤ 0.055 ⇒ one stop" also died on fuel, not on
  wear (CLAUDE.md rule 12). Kept: the binding limit depends on the mode. Full send is fuel-bound
  and saving is tyre-bound.
- **R11.** §4: "the cause is CONFOUNDED and I cannot separate them". §10: "That refusal was wrong
  and it was checkable in two minutes": it is fuel, and `tyre_radius_m` is a constant. Kept: §10.
- **R12.** §12 predicts the full-stint rate ≥ 0.0528, with "below 0.0528" as the falsifier. §14
  and §21 report RH s153 at **0.0498**. That appears to fire the falsifier, but the gap is inside
  the gauge's resolution (s153 is 14 laps in the store) and the file never scores it. Kept: `open`, flagged.
- **R13.** §19c: saving "is enough to cross from 28 laps to 29". §21: "it does not buy a lap, and I
  said it would … retracted". §39: "Every plan except RH full send now reaches 29 laps", because
  s158/159 moved the reference lap. Kept: 29 laps are reachable, **but not because of saving**. The
  saving row stays `refuted`.
- **R14.** §15: "RM two-stop, full send" and "Short-shifting makes the RM plan WORSE". §19: "THE
  PLAN IN 15 IS WRONG", because the reasoning was circular: saving relieves the tyre constraint.
  §23 makes no race call. §40 records the driver's decision, one stop on RM with fuel-save. Kept:
  §40.
- **R15.** The Rev E section names `df_r` down or `arb_f` softer as the next moves. §17 chooses
  `arb_r` stiffer instead and argues against `arb_f` softer on the Spa/Daytona transfer. Kept: §17.
  The two candidates stay `open` and were never run.
- **R16.** §17 orders "Rev F, `arb_r`" next. §19f: "THIS MUST RUN BEFORE `arb_r`, and section 17's
  ordering is corrected" (wear stint first). Kept: §19f, and §20d repeats it.
- **R17 (cross-file).** The file header says LSD is "ABSOLUTES … the register has not been re-read
  since". The range register shows the RSR's three LSD axes re-read on v1.71 on 21 Aug
  (0–30 / 0–100 / 0–99). The register itself carries an unresolved one-click disagreement on the
  RSR's lsd_b ceiling (99 against 100 on two sister cars). Kept: the range is available. It only
  matters for the open `lsd_a` sweep row.
- **R18.** The shift point for 5th was pre-issued as "[MEASURED on the old box, ASSUMED across this
  ratio change]". §18: "measured wrong on this one", with every gear from 1 to 5 reporting LIMITER.
  Kept: §18.
- **R19.** §24's falsifier was "the rear steps out on **brake release** … That means one click
  less". §30: "The conclusion was right and the stated symptom was wrong". The real failure was
  lost mid-corner rotation with spins. A literal reading would have kept the overshoot. Kept: §30.
- **R20.** §29: "92 % of it falls in two SLOW corners … a mechanical-grip story". §33 retracts
  it: the 47 km/h "corner" was him already off the road, his corner is a 172 km/h blind left, and
  the rear was loose everywhere. Kept: §33.
- **R21.** §32 lists three open predictions: wear, catches over a stint, and a loose rear. §34
  scores "the three open predictions" as wear, **no degradation**, and a loose rear. The catch
  prediction is scored separately in §35 ("Prediction 2 was not falsified — the metric was
  mis-specified"). Kept: each prediction scored on its own row.
- **R22.** §36: "`unmeasurable_because` the app cannot see proximity to another car"; the tow is
  "the obvious candidate". §39: "It can" (`gap_reads`), and the tow explains 0.02 of 0.41 L/lap.
  Kept: §39, and the tow row is `refuted`.

**Cross-file, doctrine**

- **X1.** Sardegna §13's driver note (10 Sep, *"me not complaining about the car doesn't mean it's
  got the best setup"*) retires "no symptom / no complaint" as evidence. Three earlier `confirmed`
  rows rest partly or wholly on silence: Shelby Rev B row 4 (S3), the Bathurst beep row (B3), and
  Sardegna Rev A's platform row ("Driver reported no harshness", though that row also has a
  body-height measurement). Kept as scored, flagged.
