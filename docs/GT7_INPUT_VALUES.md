# Which GT7 values you enter into the app

The app **recommends** most setup values for you to copy **into** GT7 (the "Transcribe to
GT7" view). This page is the other direction: the handful of values you read **from** GT7
and type **into** the app so its brain reasons about the real car.

Everything not listed here is either recommended by the app or looked up automatically.

---

## 1. Event (Home → Create / edit events)

| App field | Where in GT7 | Notes |
|---|---|---|
| Car | The car you're racing | Must match GT7's car name for specs to resolve |
| Track / layout | The circuit + layout | |
| Race format | Race regulations | Laps (lap race) **or** minutes (timed race) |

## 2. Gearbox (Garage → full setup sheet → **Transmission (entry)**)

Read from **GT7 → Tuning → Transmission**:

| App field | GT7 value |
|---|---|
| 1st … 8th | Each gear ratio (leave unused gears at 0) |
| Final | Final gear ratio |
| Top speed (km/h) | The "Top Speed" adjustment value |

Race and Qualifying hold **independent** gearing — enter each on its own discipline tab.

## 3. Ballast (Garage → full setup sheet → **Ballast (entry)**)

Read from **GT7 → Tuning → Ballast**:

| App field | GT7 value |
|---|---|
| Ballast (kg) | Ballast weight (0–200 kg) |
| Position | Ballast Positioning (−50 = full front … +50 = full rear) |

The app uses these for balance advice **and** total weight — enter the actual ballast you
run to meet a minimum weight.

## 4. Engine data — for shift strategy (Garage → **Shift Strategy** panel)

Two ways:

- **Calibrate from telemetry** *(preferred)* — drive one clean wide-open-throttle lap,
  then press **Calibrate from telemetry**. The app reads the recorded pull and fills these
  in for you, at higher confidence than hand entry.
- **Enter manually** — read off GT7's **power / torque curve graph** (Car Settings shows
  the dyno-style graph):

| App field | Where on the GT7 graph |
|---|---|
| Peak power RPM | The RPM where the **power (HP)** curve is highest |
| Peak torque RPM | The RPM where the **torque** curve is highest |
| Redline (RPM) | Where the tacho redlines / the rev limiter cuts in |

## 5. Tyre compound (Garage)

Select the compound currently on the car so pace, fuel and degradation are read against
the right tyre.

---

## Not yet enterable (known gap)

GT7 doesn't state peak-power/torque RPM as numbers — you read them off the graph (or
calibrate). And a car tuned with **parts** (e.g. a higher BHP than stock) or run to a
**series minimum weight** differs from the looked-up stock specs: ballast weight is
captured, but a tuned **peak power / minimum-weight (BOP)** figure has no dedicated input
yet. Until it does, the shift-strategy telemetry calibration is the most accurate path for
a modified car, because it measures the real engine rather than trusting stock specs.
