# Porsche 963 '24 — Fuji International Speedway — Enduro Rd4, 26 Sep 2026

**Mode: `initial`** — a car and circuit with no run on file. Written 11 Sep 2026
(plan row 2.7). **Everything below the hub facts is `[DOCTRINE]` or `[ASSUMED]`**;
there is no lap, session or telemetry for this car anywhere in the archive.

**Not yet an event row.** The round becomes an event when he picks it on the
Calendar screen - his act, which writes the hub's regulations, BoP included,
into `events`. Nothing here was written to the database.

---

## 1. What the hub says (read-only, 11 Sep 2026)

| | |
|---|---|
| Series / round | NGR Enduro Series 1, Rd4 - `MULTI_CLASS_MANUFACTURER`, classes Gr.1 / Gr.3 / Gr.4 |
| When | 26 Sep 2026, 11:00 UTC |
| Circuit | Fuji International Speedway - the bare name is the base layout (Full Course) |
| Format | **120 minutes, timed**, rolling start, grid by qualifying |
| Qualifying | 10 minutes, same wear and fuel as the race, 100 L, **no slipstream** (`qualifyingSlipstreamStrength: DISABLED`) |
| Tyres / fuel | wear **3x**, fuel **2x**, refuel **1 L/s**, start on 100 L; no mandatory stop, no required compound change |
| Weather / time | random weather, afternoon, time x12 |
| Assists | ABS and TCS not limited; countersteer and ASM prohibited |
| Damage | heavy |
| **Regulations** | **`bopEnabled: true`**, `tuningAllowed: true`; no power or weight limit stated; **no per-car override for this round** |
| **His class** | **Gr.1** - assigned for this round (`DriverRoundClassAssignment`); it moves between rounds |
| **His car** | **Porsche 963 '24** - Porsche's Gr.1 car on the manufacturer roster; he has made no car choice of his own |

`raceFinishDelaySeconds: 180` is the time after the leader finishes before the
race closes for the rest - **not** the app's `extra_time_s` (hub schema note 7).

## 2. Refused by name — this round runs BoP

The lobby locks these, so a sheet that moves one is not a sheet. **Each is
written "locked by BoP" and never given a value** *[the gearbox lock is the
driver's own report, Spa Enduro, 22 Aug; ECU, restrictor and ballast are
ASSUMED from GT7's BoP - the list errs on the side of refusing]*:

- `top` (maximum speed)
- `fg` (final gear)
- the gear ratios, all of them
- ECU output
- the power restrictor
- ballast (mass and position)

**What survives the lock: the shift table.** One gearbox for the whole event,
so it is measured once, in the first practice run, and issued with
`write_shift_points` for this car and circuit. A table issued before that run is
a guess about ratios nobody has read.

`tuningAllowed: true` leaves suspension, dampers, alignment, the diff, aero and
brake balance open *[ASSUMED - the only evidence is the Spa 992 sheet entered
under BoP; confirm on the settings screen in run 0]* - brake balance is his
trim, recorded and never corrected.

## 3. Rank zero — there is no range record for this car

`range_records` holds four cars (RSR, 992 GT3 R, Huracán, Shelby) and **not the
963**. Every percent-of-range figure starts from it, so **the first deliverable
is the settings screen to read**, on v1.71, entered once on the Car screen: all
22 endpoints, and `game_version` with them. **No slider value is issued before
that** - a Gr.1 prototype's ranges are not a Gr.3 car's, and the Shelby showed
how far a class boundary moves them.

## 4. The field and the board

- **Ten drivers are assigned for this round: 4 Gr.1, 3 Gr.3, 3 Gr.4.**
- **GT7's leaderboard shows eight rows, positions 1-8** (measured at Spa,
  confirmed by the driver). With ten cars, two are always off the screen, and a
  car standing in the pit lane drops toward the cut exactly when its stop
  would be read.
- **The board is overall, not by class, as far as anything on file shows.**
  Whether GT7's race board marks class at all has never been seen here. Until
  it is, George's position is overall, and **no call claims a class position
  or a class gap off the board**.
- `[ASSUMED]` The Gr.1 cars run at the front, so his three class rivals are
  usually on the board while he runs with them; the Gr.4 cars are the likeliest
  two off it. A Gr.1 rival who pits can drop below the cut, so an empty rival
  profile is never "he does not stop".
- Slower-class cars will be lapped. A car he is closing on may be traffic,
  not a rival - a "closing" call is about position only if it is his class.

## 5. The strategy frame — what a plan will have to settle

No burn, wear or lap time exists for this car, so **no plan can certify
yet**. What the hub fixes:

- **Fuel is the whole stop.** At 1 L/s a full tank is 100 s standing; the tyre
  change, where one is taken, comes first and is sequential (`reference_gt7_pit_stop_sequence`).
  **Size the fill from the clock at the stop, never from the plan's stint.**
- The undercut is weak in GT7 (`CLAUDE.md` §5.4), and at these standing times
  it is irrelevant beside the fill.
- Three unknowns decide the stop count, and each is one practice run:
  1. **burn per lap** at race pace from a full tank - measured, never a
     practice figure discounted (Deep Forest's last stint burned *more* than
     practice, 7.92 against 7.84 L/lap); the fill itself is sized from the
     live burn at the hose;
  2. **wear per lap on the gauge**, OBS on, at 3x - measured at the multiplier
     raced, never converted (`CLAUDE.md` §5.2);
  3. **pit loss at Fuji** - the GR3 round's 20 s is declared, not measured.

## 6. The runs that turn this into evidence

**Every run in a lobby with BoP on and the Enduro's settings** (3x wear, 2x
fuel, 1 L/s). BoP changes the power, the weight and the gearbox, so a burn,
a pace or a shift point taken in a time trial or an open lobby is a
different car's. The app records the lobby (`practice_mode`) but not whether
BoP was on - say so in the run plan.

| # | Run | Purpose | Laps |
|---|---|---|---|
| 0 | Settings screen | range record, all 22 endpoints, v1.71 | - |
| 1 | Full tank, race pace, gauge on | burn per lap, wear per lap, the gearbox's shift points | 8-10 |
| 2 | In-lap, stop, out-lap | pit loss and the cold out-lap at Fuji | 3 |
| 3 | Quali sim, 100 L | the 10-minute session's lap on its own fuel | 4-5 |

Then `race plan` mode, against which limit actually binds.
