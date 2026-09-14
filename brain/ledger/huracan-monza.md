# Experiment ledger — Huracán GT3 '15 × Autodromo Nazionale Monza, Full Course

The car and its settings: [`brain/car-state/huracan-monza.md`](../car-state/huracan-monza.md) - the only place a value is written. This file holds keys, directions and deltas in percentage points of slider range, never a setting. Conventions: [README](README.md).

Seeded 15 Sep 2026 from the Bathurst Rd7 debrief. No Huracán lap at Monza exists yet, so **no row has a Monza control**; run A is the baseline and run A-again is the control for run B.

```csv
date,session_ids,key,direction,delta_pct_range,instrument,measured_floor,control,prediction,falsifier,outcome,source,car_state_rev
2026-09-15,none yet (run A),df_f;df_r,down;down,df_f -60.0; df_r -67.5,speed at a fixed point before the Rettifilo braking board (no tow); handling instruments,not established at Monza; handling instruments did not see the whole wing range at Daytona (4 Sep),Bathurst sheet (other circuit) - none at Monza,more top speed with no change the driver can feel in the Parabolica or Curva Grande,driver reports a loose or nervous rear at high speed; or no top-speed gain,open,"car-state §sheet downforce row; AXIS-REGISTER df row",issued 15 Sep run A
2026-09-15,none yet (run A),ECU;ballast,to the Rd8 limit (550 bhp / 1275 kg),range unknown (regulation),GT7 settings-screen power and weight readout,n/a,Daytona Rd6 SCREEN at the same limits,reads 548 BHP / 1275 kg,screen reads over either limit,open,"car-state §The round; huracan-mount-panorama.md §sheet ECU/ballast rows",issued 15 Sep run A
2026-09-15,none yet (run A),gearbox (held),held,none (held),rev-limiter frames in 6th on the main straight; gear through the chicanes,not established,none,6th stops short of the limiter without a tow and near it with one; 2nd covers each chicane without an upshift between apexes,limiter frames in 6th without a tow; or an upshift between chicane apexes,open,"car-state §The gearbox",issued 15 Sep run A
2026-09-15,none yet (run B vs A and A-again),arb_r,softer,-22.2,[DRIVER REPORT] planted after kerb strikes; kerb-strike upset share and rear-slip-after-strike rate on power (Roggia; Lesmo 2; Ascari exit); time down the next straight,upset share ~0.10-0.14 and rear slip ~0.10-0.13 at 8 clean laps a block (placebo p90; Daytona and Bathurst odd/even; 15 Sep),A-B-A return leg (run A again),the driver reports the car staying planted after kerb strikes; rear slip after strikes on power falls; some drive out of the chicanes is given back,no feel change on B; or B slower down the straights with no feel gain; telemetry most likely 'can't tell' at 8 laps - his report decides,open,"car-state §Why the kerbs are the brief; Daytona arb_r 4->6 kerb hint (+0.09 upset; rear slip 0.084->0.176; inside floor); 02 §10.9 #4; AXIS-REGISTER arb_r row (the cost)",issued 15 Sep run B
```

**Notes**

- `df` −60.0 = −60 ÷ 100 span (front 350–450); −67.5 = −135 ÷ 200 span (rear 500–700). `arb_r` −22.2 = −2 ÷ 9 span (1–10).
- **Not rows, and why:** brake balance forward (`05` §1.5) refused, standing rule; `lsd_a` down (`05` medium-low for kerb exits) refused, REFUTED on this car; compression damping softer — on the floor, and null on the kerb instrument; `de_r` up — REFUTED on this car (balance), though the kerb instrument's only calibration is a rear-rebound change on the Shelby.
- **Candidates not yet tested with the circuit held, for after run B:** springs (`nf`), front rebound (`de_f`), front ride height, ballast position.
- **The disagreement inside run B is expected, and it is the finding if it comes:** at 8 laps the telemetry cannot resolve a change the size of the Daytona hint, so a clear feel report with a "can't tell" instrument is the normal outcome, not a contradiction.
