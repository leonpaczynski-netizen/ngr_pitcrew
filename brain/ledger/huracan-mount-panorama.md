# Experiment ledger — Huracán GT3 '15 × Mount Panorama

The car and its settings: [`brain/car-state/huracan-mount-panorama.md`](../car-state/huracan-mount-panorama.md) - the only place a value is written. This file holds keys, directions and deltas in percentage points of slider range, never a setting. Conventions: [README](README.md).

Seeded 11 Sep 2026 from the car-state file at `b288d88` 2026-09-08.

This is a new circuit, so the initial sheet deliberately moves a coupled set, measured against the
Daytona race sheet. **None of its rows has a Bathurst control.** Everything is judged in s151,
the first 10 laps ever driven there.

```csv
date,session_ids,key,direction,delta_pct_range,instrument,measured_floor,control,prediction,falsifier,outcome,source,car_state_rev
2026-09-08,s151,rh_f;rh_r;nf_f;nf_r,up;up;softer;softer,rh_f +24.0; rh_r +20.0; nf_f -10.0; nf_r -10.0,suspension-height excursions over the crests; driver report,not established,none (new circuit; baseline is the Daytona race sheet),the car survives Skyline and The Dipper without going light or bottoming,sustained excursions toward the observed minimum over the crests; or the driver reports the car going light,unresolvable,"§'What this predicts' row 1; §s151 'Predictions checked' row 1 ('Recorded as unresolvable on rh_f, direction up'); §'What the mountain actually did' (unloading is downstream of being sideways)",issued sheet 8 Sep
2026-09-08,s151,gearbox (held),held (no change),none (held),rev-limiter frames in 6th on Conrod,not established,none,6th arrives at The Chase off the limiter; on it only with a tow,limiter frames in 6th on Conrod without a tow,confirmed,"§'The gearbox — held'; §s151 row 2 (282.5 km/h at 5,000 m in 6th, no tow, ~311 km/h limiter)",issued sheet 8 Sep
2026-09-08,s151,lsd_b (held),held (no change),none (held),rear slip below 0.90 under braking into The Chase,not established,Daytona: rear lock 0 in 5 laps at the stiffer lsd_b vs 2 in 15 at the current setting,the current lsd_b holds the rear at The Chase; lsd_b up is the pre-loaded answer,rear slip < 0.90 on more than 1 lap in 5,confirmed,"§'What this predicts' row 3; §s151 row 3 (zero frames; 'lsd_b up stays holstered')",issued sheet 8 Sep
2026-09-08,s151,shift_points id 5,held,range unknown,driver report of a late beep,not established,none,the three gears that beep are the right three (the mountain is 1st-3rd work),driver reports the beep arriving late over the mountain,confirmed,"§'What this predicts' row 4; §s151 row 4 ('no report of a late beep; the mountain runs 2nd-4th'); see (b)-B3",issued sheet 8 Sep
2026-09-08,s151,de_f,stiffer,+13.3,mid-corner front/rear slip gap,not established,Daytona gap ~0.011 (other circuit),none stated for de_f alone (front settles on the descent),none stated,unresolvable,"Sheet table de row; §s151 'The balance finding, and why it is NOT attributed' (four things moved at once; named as a candidate for later)",issued sheet 8 Sep
2026-09-08,none yet,ballast position,forward (as run; held),range unknown,none yet,not established,none,more front load might help a front-limited middle or cost traction at Forrest's Elbow,none stated,open,"§'The ballast moved the weight balance forward' ('Logged as a candidate test, not a change'); §s151 ('one of 22 axes never tested on this car')",issued sheet 8 Sep
2026-09-08,none yet,ECU;restrictor,to the highest legal reading,range unknown,GT7 settings-screen power readout,not established,screen readings at two ECU points (6.0 bhp per ECU point),one of two untried ECU/restrictor combinations reads closer to the power limit from below,neither beats the current reading,open,"§'Power landed ... 4 bhp given away' (derived rows; 'Check ... on the screen')",issued sheet 8 Sep
2026-09-08,s151 onward,gear1;gear2,re-cut over the mountain,range unknown,tools/shift_points.py on mountain frames,not established,s151 as the run-as-is baseline,1st/2nd over the mountain are [UNMEASURED]; re-cut after the first run,none stated,open,"§'The gearbox — held' ('Run the box as it stands, then re-cut')",issued sheet 8 Sep
2026-09-08,s151,n/a (traction at The Cutting),n/a,n/a,on-power rear-spin share (646 frames laps 5-10); whole-lap wheelspin,not established; Daytona whole-lap 7.0/5.8/5.5 % as reference,Daytona whole-lap wheelspin,a traction limit not a diff question; 'a question not a change',n/a,open,"§s151 'What he did NOT report — The Cutting'",s151
2026-09-08,none yet,n/a (pit loss),n/a,n/a,measured pit loss,not established,n/a,reference estimate 28-30 s at medium-high confidence,n/a,open,"§'What is silent' ('Measure it')",-
2026-09-08,none yet,n/a (wear rate / stint length / tyre model),n/a,n/a,HUD wear gauge,not established,n/a,none yet ('needs laps'),n/a,open,"§'What is silent'",-
```

**Notes, Bathurst (Huracán v1.71 ranges, step ÷ span)**

- rh_f +6 mm ÷ 25 = +24.0 pp and rh_r +6 mm ÷ 30 = +20.0 pp. Both agree with the file's own
  percentages. Rake is held, because both ends moved the same distance.
- nf −0.20 Hz ÷ 2.00 = −10.0 pp at each end. de_f +4 ÷ 30 = +13.3 pp. de_r was held, because
  "`de_r` up was REFUTED 8 Sep" (Daytona).
- The ECU drop and the +10 kg of ballast are regulation-driven: the power and weight limits
  changed between rounds. They are not experiments, and neither has a slider range.
- **Not rows:** the `bb` forward advice from the track reference was refused, with the same
  measured basis as Daytona. The file resolves the rake-vs-clearance tension by argument
  ("Settled. Not a tension."). Decision after s151: NO CHANGE.
- The first-run corrections to "touchy" (it meant *pointed*, not *light*) are driver vocabulary,
  not ledger rows. They are the reason row 1 is `unresolvable` and not `refuted`.

## Items with no percent-of-range delta

Cited by location only; the absolutes are read at the cited section and restated nowhere.

| id | car × circuit | item | where the absolutes are | why no pp |
|---|---|---|---|---|
| a-B1 | Huracán × Mount Panorama | ECU/restrictor combinations to try on the screen, to land at or just under the power limit | §"Power landed … 4 bhp given away" | no range |
| a-B2 | Huracán × Mount Panorama | ballast mass and position (a candidate test of position) | §"The ballast moved the weight balance forward"; sheet table ballast row | no range |
| a-B3 | Huracán × Mount Panorama | 1st/2nd re-cut over the mountain (no values issued yet; will be ratios) | §"The gearbox — held" | gear ratios |
| a-B4 | Huracán × Mount Panorama | shift table `shift_points` id 5 | §"The gearbox — held", last para | shift rpm is not a slider |

## Contradictions on file

Surfaced, not averaged (`CLAUDE.md` §4 rule 1). The latest is kept as the outcome; both are cited.

- **D11 / B1 (cross-file).** Three places call rake against Bathurst clearance a tension to settle
  first: the AXIS-REGISTER ("Settle that tension first"), the Daytona close-out ("in tension with
  the rake finding"), and the Daytona "What does NOT transfer" list. The Bathurst file says "it
  dissolves … Settled. Not a tension": rake is the difference between the ends, clearance is the
  level of both. Kept: the Bathurst file, the latest.

- **B2.** The sheet table says the diff's `lsd_a` is "already inside the reference's 20–28 band".
  **The value on that sheet sits below the band's floor.** The range register also says every
  `05-track-reference.md` LSD band was written against the pre-1.71 5–60 scale, so it "addresses
  a different slider". The justification is wrong twice. The setting's own evidence (the
  instrument cannot separate the two Daytona settings) still stands.
- **B3.** Beep prediction row 4 assumes "the mountain is 1st–3rd work". s151 finds "the mountain
  runs 2nd–4th", and gears 4–6 are silent. The row was scored "Held" on the *absence* of a driver
  report. Sardegna §13's driver note (10 Sep), and the memory `feedback_no_complaint_is_not_a_
  good_setup`, say silence is not a clean bill. Kept: `confirmed` as the file scored it, flagged
  weak, with its premise contradicted.

**Cross-file, doctrine**

- **X1.** Sardegna §13's driver note (10 Sep, *"me not complaining about the car doesn't mean it's
  got the best setup"*) retires "no symptom / no complaint" as evidence. Three earlier `confirmed`
  rows rest partly or wholly on silence: Shelby Rev B row 4 (S3), the Bathurst beep row (B3), and
  Sardegna Rev A's platform row ("Driver reported no harshness", though that row also has a
  body-height measurement). Kept as scored, flagged.
