# GT7 Race Engineer Knowledge Base

This document contains two sections:
1. Gran Turismo 7 game physics and mechanics reference
2. The driver's personal tuning philosophy and driving profile

Both sections must be used together when giving setup advice, race strategy recommendations, or coaching.

---

## PART 1 — GT7 PHYSICS AND MECHANICS REFERENCE

### Tyre Compounds

**Compound hierarchy (fastest to slowest baseline pace):**
Racing Soft (RS) > Racing Medium (RM) > Racing Hard (RH) > Dirt/Snow/Intermediate/Wet

**Optimal operating temperature ranges:**
- Racing Soft: 80–100°C. Below 70°C = significant understeer and reduced braking. Above 110°C = accelerated wear and overheating blistering.
- Racing Medium: 75–100°C. More forgiving heat window than RS.
- Racing Hard: 70–100°C. Slow to come up to temperature; fastest over long stints when fully warmed.
- Intermediate: effective in light rain, loses grip as standing water increases.
- Wet: effective in heavy rain or standing water; dangerous on a drying track.

**Tyre degradation — race vs practice:**
GT7 applies a tyre wear multiplier during races. If set to 3×, the tyre life in race laps is roughly 1/3 of what the compound would last in practice.

Estimated race life before significant pace drop (at 1× multiplier):
- Racing Soft: 10–16 laps
- Racing Medium: 18–25 laps
- Racing Hard: 28–40 laps

At higher wear multipliers, divide these figures accordingly.

**Wheelspin and tyre wear:**
Wheelspin accelerates rear tyre wear 2–4× versus clean traction. Lock-ups under braking accelerate front tyre wear similarly. A driver with 8 wheelspin events per lap on a 25-lap race may see their rear tyres degrade in 60% of the expected stint length.

**Slick tyres in rain:**
On a wet track with heavy rain, slick tyres lose operating temperature and grip within 3–5 laps. At that point the car becomes undriveable at race pace. Switch to Intermediates at the first sign of consistent rain.

---

### Aero and Drag Trade-Offs

**Downforce vs drag relationship:**
Higher aero = more downforce = faster through medium and high-speed corners. However, higher aero also increases drag = lower top speed on straights = higher fuel consumption (engine works harder at peak throttle).

Approximate effect of +100 aero units on rear wing:
- Gain: 0.1–0.4 s/lap in medium/high-speed sections (track dependent)
- Cost: 0.05–0.15 L/lap additional fuel burn
- Cost: 2–8 km/h lower top speed

**Aero/fuel strategic trade-off formula:**
Total race time impact of reducing rear aero:
```
time_saved = laps_saved_from_fewer_stops × pit_stop_loss_secs
time_cost  = aero_lap_time_penalty × total_laps
```
If `time_saved > time_cost`, reducing aero to eliminate a pit stop is strategically viable.

Example: 25-lap race, 1-stop strategy, pit costs 25 s, aero reduction costs 0.3 s/lap.
Eliminating the stop saves 25 s. Aero penalty costs 0.3 × 25 = 7.5 s. Net gain: 17.5 s → take the no-stop with lower aero.

**Front vs rear aero balance:**
More front relative to rear = understeer tendency. More rear relative to front = oversteer tendency. Balance the front and rear so the mechanical balance from suspension and differential is the primary control.

---

### Fuel Load Effect on Lap Time

Each litre of fuel adds approximately 0.015–0.04 s per lap (car-dependent; heavier GT cars are less sensitive than lightweight sports cars).

At 50 litres of fuel versus 10 litres remaining, the lap time difference is approximately 0.8–2.0 s depending on the car.

**Strategic implication:**
Adding more fuel than needed at a pit stop incurs an immediate lap-time penalty for each lap run until the fuel burns down. Over-fuelling by 5 laps worth (e.g., 10 L extra at 2 L/lap) costs approximately 0.03 s × 5 laps × remaining laps at that load = meaningful time. Do not over-fuel.

**Safety margin:**
A 1-lap fuel safety margin is the recommended minimum. Running out of fuel ends the race. A 1-lap buffer costs approximately 0.03 s/lap × remaining laps — a worthwhile insurance premium.

---

### Pit Stop Time Calculation

Total pit stop time = pit lane transit time (typically 15–25 s depending on track) + stationary work time.

Stationary time = max(tyre change time, refuel time). GT7 runs tyre change and refuelling in parallel.
- Tyre change: approximately 3–4 seconds (fixed)
- Refuel: `fuel_to_add / refuel_speed_lps` seconds

Example: add 30 L at 10 L/s = 3 s for fuel. Tyre change = 3 s. Both complete in ~3–4 s stationary.

If you need 40 L at 10 L/s = 4 s stationary, plus 20 s pit lane = 24 s total pit stop loss.

---

### Race Strategy Fundamentals

**When is a pit stop worth it?**
A compound change is worth a stop when the pace advantage of a faster compound exceeds the time lost in the pit lane across the remaining stint.

Rule of thumb: a tyre change is beneficial if `(pace_advantage_per_lap × remaining_laps) > pit_stop_cost_s`.

Example: switching from degraded Medium (+1.5 s/lap vs RS) to fresh RS for 12 remaining laps → saves 18 s in pace. Pit costs 22 s. Not worth it. If 18 laps remain: saves 27 s. Worth it.

**Undercut strategy:**
Pitting 1–2 laps earlier than planned to gain track position via fresh tyres while others are still on worn rubber. Effective when the tyre performance cliff is approaching and the pit lane is fast.

**Safety car pit windows:**
When a safety car deploys, the pit cost effectively drops to near zero (track pace matches or exceeds pit lane speed). Almost always worth pitting during a safety car period unless you pitted within the last 3 laps.

**Fuel-save driving:**
Lift-and-coast before braking zones instead of trailing throttle to the braking point. Saves approximately 0.1–0.3 L/lap at a cost of 0.3–0.8 s/lap. Viable when margin exists, unsustainable as a catch-up tactic.

---

### GT7-Specific Setup Mechanics

**Natural Frequency vs Spring Rate:**
GT7 uses natural frequency (Hz) in some menus rather than spring rate directly. Higher Hz = stiffer. Typical road car race setup: 2.0–3.5 Hz front and rear. Slick race cars: 3.0–5.0 Hz. Bumpy circuits: 0.3–0.5 Hz lower than flat-circuit setup.

**Differential behaviour in GT7:**
GT7 uses a torque-sensing (Salisbury-style) limited slip differential.
- Initial torque / preload: acts at all times, even off-throttle. Controls baseline rotation behaviour.
- Acceleration sensitivity: only activates under power. Controls how strongly both wheels lock under throttle.
- Braking sensitivity: activates under deceleration. Controls rear axle behaviour during trail braking and downshifts.

**Anti-roll bar range:**
GT7 ARB values range 1–10. Higher = more resistance to body roll. Stiffer front ARB increases understeer on entry. Stiffer rear ARB increases oversteer on entry (reduces rear compliance).

**Toe:**
Front toe-out: improves turn-in agility, increases tyre scrub and wear if excessive. Toe-in values are negative in GT7 menus.
Rear toe-in: improves straight-line and high-speed stability, reduces low-speed rotation. Typically set positive (toe-in).

**Camber:**
Too much camber = tyre runs on inner shoulder = overheating and accelerated inner wear. In GT7, optimal camber varies by car and track.

**Brake balance:**
GT7 allows in-race brake bias adjustment. Moving forward reduces rear brake force = more stable under braking. Moving rearward increases rotation on corner entry but risks rear lock.

**Transmission — Final Drive:**
Final drive controls the overall gear multiplication. Raising final drive shortens all gears simultaneously. Lowering lengthens all gears. Most useful for adjusting top speed to match track's longest straight.

**Transmission — Individual Ratios:**
Each ratio can be adjusted independently. Critical gears for this driver: 2nd (wheelspin, low-speed exits), 3rd (medium corner exits), and top gear (straight-line speed matching).

---

## PART 2 — DRIVER PERSONAL TUNING PROFILE

The following is the complete personal driving profile for this driver. All AI advice must be tailored to this profile.

---

### Core Driving Style

The driver is a **trail-braking driver** who:
- Brakes firmly in a straight line
- Continues carrying some brake pressure into the corner
- Uses brake release to help rotate the car
- Points the car early so throttle application can begin before the exit kerb
- Does NOT rely solely on steering input to turn — uses brake pressure + weight transfer + steering angle + downshift timing + throttle release together

**What he needs from the car:**
- Strong front-end response under braking
- Rear stability during downshifts
- Progressive rather than sudden rotation
- Enough rear support that the car does not snap when brake pressure is released
- No unexpected rear locking when selecting lower gears

**What hurts his confidence:**
- Rear tyres locking during trail braking
- Car rotating too sharply when brake is released
- A floating rear axle entering medium and high-speed corners
- A setup that feels safe in a straight line but unstable once steering lock is introduced

---

### Ideal Vehicle Balance

Preferred entry behaviour: **Immediate nose response, controlled rotation, stable rear platform.**

| Phase | Preference |
|-------|-----------|
| Straight-line braking | Stable and planted |
| Trail braking | Responsive front, supported rear |
| Turn-in | Sharp and immediate |
| Mid-corner | Neutral with mild rotation |
| Throttle pickup | Progressive rotation |
| Full acceleration | Strong traction and rear stability |
| Kerbs and bumps | Compliant without floating |
| High-speed direction change | Calm rear, precise front |

**Mid-corner**: Wants mildly responsive rather than nervous; neutral to slightly front-positive; stable enough to hold partial throttle; resistant to lift-off oversteer. **Transient balance** matters more than static peak grip — a car can have excellent peak grip and still feel terrible if it reacts unpredictably during throttle or brake transitions.

**Throttle**: Progressive. Feeds throttle once car is pointed, builds power rather than stamps on it. Ideal exit: car finishes rotating as throttle is applied, then settles and drives forward.

---

### Setup Problems — Diagnosis and Fixes

#### Rear locking under braking
Causes: rear brake bias too aggressive; rear diff braking sensitivity too low or too high; insufficient rear rebound control; rear ride height too high; downshifts completed too early; insufficient rear downforce; rear tyres unloaded by excessive forward pitch.

Fix: move brake bias slightly forward; add rear stability via diff braking; increase rear aero where available; reduce excessive rake; calm rear suspension; delay final downshift slightly.

#### Lift-off oversteer
Causes: rear diff initial torque too low; rear braking sensitivity too aggressive or poorly matched; rear toe too neutral or outward; excessive rear roll stiffness; too much rake; rear rebound too stiff; front gripping sharply while rear unloads.

Fix: add small amount of rear toe-in; increase rear diff initial torque slightly; soften rear ARB; reduce rear rebound stiffness; reduce rake; add rear downforce where speed penalty is acceptable.

#### Power oversteer
Particularly affects: high-power road cars; FR cars; undulating exits; second-gear corners; turbo delivery.

Fix: increase acceleration sensitivity enough to lock both driven wheels progressively; increase initial torque slightly; add rear toe-in; soften rear ARB; soften rear compression slightly; lengthen second gear; add rear ballast if genuinely beneficial. Reduce power only after chassis and differential options exhausted.

#### Rear instability over crests and bumps
Problem areas: Bathurst Skyline; Eau Rouge / Raidillon; Road Atlanta elevation changes; Lago Maggiore undulations; fast direction changes.

Fix: suspension that follows the surface; rear rebound not excessively stiff; sufficient ride height to avoid bottoming; softer roll stiffness than a flat-track qualifying setup; stable aero platform; rear differential that does not suddenly unlock.

#### Understeer under throttle
Fix: slightly reduce diff acceleration sensitivity; increase front mechanical grip; reduce excessive rear stiffness; add a little more front downforce if available. The goal is not to make the rear loose — let the car complete the corner while power is being added.

---

### Differential Philosophy

**Initial Torque (GT7 typical starting ranges):**

| Car Type | Starting Range |
|----------|---------------|
| Low-power FR road car | 8-14 |
| High-power FR road car | 12-20 |
| MR race car | 10-18 |
| Porsche / rear-engine | 12-20 |
| Gr.3 race car | 10-18 |
| AWD front LSD | 5-10 |
| AWD rear LSD | 10-18 |

Raise initial torque when the rear feels nervous during small throttle changes.

**Acceleration Sensitivity**: Moderate locking. Too low = inside wheelspin, rear steps out. Too high = power understeer, both tyres break traction together.

**Braking Sensitivity**: Enough lock to keep rear composed without ploughing straight. Fine line between planted entry and rear-locking pirouette. Smooth rear during downshifts and progressive rotation during trail braking.

---

### Suspension Preferences

**Anti-roll bars**: Front equal to or one step stiffer than rear for unstable cars. Rear equal to front for planted race cars needing rotation. Rear stiffer than front ONLY when car is fundamentally reluctant to rotate and is already stable.

**Springs**: Enough front stiffness for precision, slightly more rear compliance for traction. Bumpy tracks: softer, particularly rear. High-speed tracks: controlled platform, not rigid.

**Dampers**: Front — enough compression to stop excessive dive, enough rebound to prevent nose springing too quickly after brake release. Rear — AVOID excessive rebound stiffness (fastest way to create lift-off oversteer), moderate compression for traction, rear settles quickly but doesn't snap back.

**Camber** (conservative approach):
| Car Type | Front | Rear |
|----------|-------|------|
| Road car | 1.8–2.5° | 1.2–2.0° |
| Gr.4 | 2.2–2.8° | 1.8–2.4° |
| Gr.3 | 2.5–3.2° | 2.0–2.8° |
| High-downforce | 2.8–3.5° | 2.2–3.0° |

**Toe**: Small front toe-out improves turn-in and responsiveness (too much = nervous). Rear toe-in improves exit stability, lift-off stability, and high-speed confidence. Driver often benefits from slightly more rear toe-in than a pure time-trial setup.

---

### Aerodynamic Balance

Prefers **enough rear aero to stabilise the car, then mechanical changes to recover rotation**. This is preferable to stripping rear aero and trying to tame the resulting instability.

Front downforce → turn-in, high-speed front grip, fast direction changes. Too much front relative to rear → lift-off oversteer, rear instability under trail braking.

Rear downforce → braking stability, high-speed confidence, exit traction, rear tyre consistency.

---

### Brake Bias

Slight front bias preferred. Rearward only when car is extremely stable and reluctant to rotate.

Frontward bias helps with: rear locking, trail-braking stability, downshift control, heavy braking zone confidence.

---

### Transmission Preferences

Slightly longer second gear with closer third-to-fifth spacing for high-power cars. Second and third gear need particular attention — too short causes wheelspin/abrupt delivery; too long kills exit acceleration. Top gear matched to the longest straight.

---

### Tuning by Vehicle Layout

**Front-Engine Rear-Wheel Drive (FR)**
Cars: BMW M6, Toyota Supra, Ferrari 812, Mazda MX-5, classic road cars.
Ideal tune: sharp but not excessively stiff front; softer rear roll stiffness; moderate rear toe-in; progressive LSD acceleration setting; slightly higher initial torque; controlled rake; longer low gears.

**Mid-Engine (MR)**
Cars: Ferrari Gr.3, McLaren, Lamborghini, some prototypes.
Key: car already has excellent rotation — make it MORE PROGRESSIVE, not more extreme. Rear stability first. Moderate initial torque, controlled rear rebound, slight rear toe-in, front brake bias, keep rear downforce healthy.

**Rear-Engine Porsche**
Cars: 911 RSR, GT3 road/race cars.
Tune: strong front response through suspension and aero; stable rear diff under braking; slight frontward brake bias; moderate acceleration lock; enough rear aero for high-speed confidence; careful control of rear ride height.

**Front-Wheel Drive (FWD)**
Tune: strong rotation on brake release; controlled front LSD acceleration; rear suspension used to aid rotation; slightly stiffer rear bar; brake bias used carefully to help entry. Rotation must be created before major throttle application.

**All-Wheel Drive (AWD)**
Cars: Mitsubishi Lancer, Nissan GT-R, some Gr.4 cars.
Tune: lower front differential locking; more rearward torque distribution; moderate rear LSD lock; slightly stronger rear rotation mechanically; controlled front toe-out. Should feel rear-driven in attitude while retaining AWD traction.

---

### Tuning by Track Type

**Tight and Technical** (Tsukuba, Brands Hatch Indy, Lago Maggiore East, Eiger, Suzuka East)
Direction: slight front toe-out, moderate rear toe-in, softer rear ARB, medium diff initial torque, moderate acceleration lock, shorter gearing, enough ride height for kerbs, brake bias slightly forward if rear becomes active.

**High-Speed Flowing** (Spa, Suzuka, High Speed Ring, Watkins Glen, Fuji)
Direction: more rear downforce, less aggressive front toe-out, slightly firmer platform, stable diff braking, moderate rear toe-in, avoid excessive rake, longer gearing, dampers to prevent floating.

**Bumpy and Undulating** (Bathurst, Road Atlanta, Nordschleife, Deep Forest, Trial Mountain)
Direction: increase ride height slightly; soften springs; reduce rear rebound stiffness; softer ARBs; more rear toe-in; moderate diff initial torque; avoid stiff qualifying setups. A small reduction in peak responsiveness usually produces a large increase in usable pace on these tracks.

**Stop-Start** (Red Bull Ring, Monza, Daytona Road Course, Barcelona)
Direction: slight front brake bias; stable rear diff braking; longer second gear; moderate acceleration lock; reduced drag; mechanical rotation rather than excessive front aero; rear toe-in sufficient for exits.

**Long Endurance** (Spa, Le Mans, Bathurst, Nürburgring, Daytona)
Direction: slightly more rear stability; less aggressive toe; slightly softer suspension; mildly reduced diff locking if tyre wear high; longer gearing for fuel saving; more progressive throttle response; aero aimed at consistency not one-lap rotation.

---

### Qualifying vs Race Setup Philosophy

**Qualifying**: sharper front response, more rotation on entry, slightly stiffer, more aggressive gearing, reduced stability margin, maximum tyre use over 1–2 laps. Typical: one step stiffer rear bar, slightly more front toe-out, slightly less rear toe-in, shorter final drive, more aggressive brake bias.

**Race**: stable rear under trail braking, predictable throttle transitions, better tyre conservation, less wheelspin, reduced steering corrections. Typical: one step softer rear bar, more rear toe-in, slightly more rear downforce, calmer differential, longer low gears, more conservative brake bias, slightly softer damping over long stints.

**"The race car should not feel dull. It should feel less spiky."**

---

### Car-Specific Setup Directions

**Porsche 911 RSR**
Front-positive aero balance without starving rear; slight front brake bias; medium LSD initial torque; moderate acceleration lock; stable braking sensitivity; rear toe-in; enough rear downforce for high-speed commitment; gearbox around smooth torque delivery.
Best circuits: Spa, Watkins Glen, Bathurst, Daytona, Nürburgring GP, Road Atlanta.

**BMW M6 GT3**
Needs help matching this driver's style. Requirements: softer rear roll stiffness; calmer rear damping; more rear toe-in; slightly higher initial torque; stable braking differential; longer low gears; front-end sharpened without creating rear instability; extra care over crests and kerbs. Tune as a large powerful platform, not a lightweight MR car.

**Mitsubishi Lancer Gr.3 / AWD**
Main challenge: rotation. Requirements: lower front LSD acceleration; lower front initial torque; more rearward torque balance; slightly more rear roll stiffness; strong front response; avoid overly locked AWD behaviour; use brake release to rotate before throttle.

**Mazda MX-5**
Soft enough to maintain rear contact; progressive rear differential; strong front response; longer low gearing where wheelspin appears; mild rear toe-in; stable over crests; rotation generated with brake release, not a loose rear bar. The MX-5 rewards this driving style when rear suspension remains compliant.

**High-Power Road Cars** (Ferrari 812, tuned 1980s/90s cars, muscle cars, turbo FR)
Priorities: traction before rotation; longer second gear; moderate-to-high initial torque; controlled acceleration lock; softer rear bar; rear toe-in; reduce power only as final step; ballast used carefully and tested. Make progressive, not merely detuned.

---

### Personal Setup Order (for unfamiliar RWD race car)

1. **Stabilise braking**: brake bias; rear diff braking; ride height and rake; rear aero
2. **Create front response**: front aero; front toe; roll stiffness; camber
3. **Control mid-corner rotation**: ARBs; rear toe; initial torque; dampers
4. **Build exit traction**: acceleration sensitivity; rear suspension; gearing; rear aero
5. **Tune for bumps and kerbs**: ride height; springs; damper rebound; roll bars
6. **Optimise gearbox**: second and third gear; final drive; top speed target
7. **Refine tyre and fuel**: toe; diff lock; aero drag; gear-shift points; brake balance

This order prevents one adjustment from masking another.

---

### Personal Feedback Vocabulary

Use these terms when the driver describes problems. Map to likely causes immediately.

| What the driver says | Likely meaning |
|---------------------|----------------|
| "Rear is floating" | Insufficient platform control, aero support or rebound balance |
| "Tail is skaty on brakes" | Rear instability under deceleration, downshift or trail braking |
| "Loses rear when I lift" | Lift-off oversteer: low preload, excessive rear stiffness or rake |
| "Loops on acceleration" | Excessive power oversteer, poor diff or gearing |
| "Won't rotate under throttle" | Acceleration LSD too tight or rear too planted |
| "Needs more front bite" | More initial response, front grip or less front diff locking |
| "Breaking traction in a straight line" | Severe wheelspin, diff, gearing or suspension issue |
| "Feels planted but slow" | Too much stability, locking or aero drag |
| "Snaps on corner exit" | Abrupt differential lock, rear stiffness or turbo delivery |
| "Undriveable over bumps" | Excessive spring, bar or rebound stiffness |
| "Front left dying" | Excessive steering angle, camber, front load or entry understeer |

---

### Default Baseline for Unfamiliar RWD Race Car

- Mild front toe-out
- Mild-to-moderate rear toe-in
- Front bar equal to or one step stiffer than rear
- Rear spring slightly softer relative to weight distribution
- Moderate LSD initial torque
- Moderate acceleration sensitivity
- Stable braking sensitivity
- Slight front brake bias
- Conservative rake
- Enough rear downforce to prevent high-speed nervousness
- Second gear long enough to control wheelspin

From there: add rotation with front response and differential tuning; do not remove rear stability too early; preserve compliance on uneven circuits; treat lift-off behaviour as seriously as full-throttle traction.

---

### Final Driving Profile Summary

**Front-end-led, trail-braking driver with smooth throttle application and a strong preference for predictable rear behaviour.**

Fastest when the car allows:
1. Brake deep without rear locking
2. Release brake progressively
3. Rotate nose early
4. Hold stable mid-corner attitude
5. Blend into throttle while car finishes turning
6. Accelerate without wheelspin or sudden oversteer

The ideal car does not feel numb, excessively safe, or artificially understeery. It feels **alive at the front and trustworthy at the rear**.

---

## PART 3 — GT7 VALIDATED TUNING DATA (Flux89 Cheat Sheet v1.2)

This section contains validated GT7 parameter ranges and starting values sourced from the Flux89 GT7 Tuning Cheat Sheet v1.2. Use this as ground truth for all parameter ranges. Where this section conflicts with Part 1 general descriptions, this section takes precedence.

---

### Validated Parameter Ranges

| Parameter | GT7 Range | Typical Start | Notes |
|-----------|-----------|---------------|-------|
| Dampers — Compression F/R | 20–40 | 30 | CARDINAL RULE: must always be lower than Extension |
| Dampers — Extension/Rebound F/R | 30–50 | 40 | CARDINAL RULE: must always be higher than Compression |
| Anti-Roll Bar F/R | 1–10 | 5 F / 4 R | Scale is 1–10, not 1–7 |
| LSD Initial | 5–60 | 10 | Minimum is 5, not 1 |
| LSD Acceleration | 5–60 | 15–25 | Higher = more lock under power |
| LSD Deceleration | 5–60 | 5–10 | Controls braking/trail-braking rotation |
| Springs | 1.00–20.00 Hz | varies by car | GT7 uses Natural Frequency in Hz |
| Ride Height | 60–200 mm | car-dependent | |
| Camber | 0.00 to −5.00° | −1.0 F / −1.5 R | Always enter as negative in GT7 |
| Toe | −2.00 to +2.00° | 0.00 F / +0.05 R | Positive = toe-in |
| Brake Bias | −5 to +5 | 0 | NEGATIVE = more FRONT braking; POSITIVE = more REAR braking |
| Ballast | 0–60 kg | 0 | |
| Ballast Position | −50 to +50 | 0 | −50 = full rear, +50 = full front |
| Power Restrictor | 0–100% | 100 | 100% = unrestricted |

---

### Tuning Order (Flux89 Validated Sequence)

Always tune in this order — each step can mask or be masked by changes in subsequent steps:

1. **Aero** — set baseline downforce levels first
2. **Ride Height** — front/rear balance (rake) affects all mechanical grip
3. **Springs** — stiffness determines the baseline platform
4. **Anti-Roll Bars (ARB)** — fine-tune roll stiffness after springs are set
5. **Dampers** — compression and extension control transient behaviour
6. **Camber** — tyre contact patch optimisation
7. **Toe** — directional stability and turn-in
8. **LSD** — power delivery and rotation control
9. **Transmission** — gear ratios matched to track
10. **Brake Bias** — final balance adjustment

---

### Spring Natural Frequency Starting Ranges by Car Type

| Car Type | Front Hz | Rear Hz |
|----------|----------|---------|
| Lightweight road car | 1.20–3.10 | 1.40–3.30 |
| Sports road car | 1.40–3.30 | 1.60–3.50 |
| Gr.4 race car | 2.50–4.00 | 2.80–4.30 |
| Gr.3 race car | 3.00–5.00 | 3.30–5.30 |
| High-downforce prototype | 4.00–7.00 | 4.30–7.30 |

Note: rear spring range always starts and ends slightly higher than front — this is by design.

---

### ARB Starting Values by Drivetrain

| Drivetrain | ARB Front | ARB Rear | Direction |
|------------|-----------|----------|-----------|
| FR (front engine, RWD) | 5 | 4 | Slightly stiffer front for turn-in |
| FF (front engine, FWD) | 3 | 5 | Stiffer rear to aid rotation |
| MR (mid engine, RWD) | 4 | 3 | Neutral; car rotates easily |
| RR (rear engine, RWD) | 5 | 4 | Stiffer front to counter rear-heavy balance |
| AWD | 4 | 4 | Balanced starting point |

---

### LSD Starting Values by Drivetrain

| Drivetrain | Initial | Acceleration | Deceleration |
|------------|---------|--------------|--------------|
| High-power FR (>500 hp) | 12–18 | 25–40 | 5–15 |
| Low-power FR (<500 hp) | 8–12 | 15–25 | 5–10 |
| MR race car | 10–18 | 20–30 | 5–15 |
| Porsche/RR | 12–20 | 20–35 | 5–15 |
| AWD front LSD | 5–10 | 10–20 | 5–10 |
| AWD rear LSD | 10–18 | 20–30 | 5–15 |

---

### Camber Starting Values by Tyre Compound

GT7 camber is entered as negative values (−2.0° means 2° of negative camber).

| Tyre Type | Front | Rear |
|-----------|-------|------|
| Street/Comfort | −1.0 to −2.0° | −0.5 to −1.5° |
| Sport / Semi-slick | −2.0 to −3.0° | −1.5 to −2.5° |
| Racing slick (RS/RM/RH) | −3.0 to −4.0° | −2.5 to −3.5° |

---

### Damper Adjustment Guide

**Cardinal Rule: Extension/Rebound MUST always be set higher than Compression. Never break this.**

| Symptom | Adjustment |
|---------|-----------|
| Car bounces excessively over bumps | Increase Extension front or rear |
| Car feels harsh and rigid | Reduce Compression front or rear |
| Nose dives sharply under braking | Increase front Compression slightly |
| Rear squats under acceleration | Increase rear Compression slightly |
| Understeer on corner entry | Reduce front Extension (allows nose to settle faster) |
| Lift-off oversteer | Reduce rear Extension (prevents rear springing back too fast) |
| Rear unstable over crests | Reduce rear Extension; increase ride height |
| Car feels planted but slow over bumps | Reduce both front and rear to allow more wheel travel |

Starting adjustment increments: ±2 for Compression, ±3 for Extension.

---

### Toe Guide

| Setting | Effect |
|---------|--------|
| Front toe-out (positive value in GT7) | Improves turn-in response; increases tyre scrub at speed |
| Front toe-in (negative value in GT7) | Reduces turn-in but improves straight-line stability |
| Rear toe-in (positive value in GT7) | Increases stability on exit and at high speed; reduces rotation |
| Rear toe-out (negative value in GT7) | Increases rear rotation but risks instability; rarely used |

**Starting points:** Front 0.00° (neutral), Rear +0.05° (mild toe-in). Adjust front toe-out for more rotation; increase rear toe-in for more stability.
