# GT7 Track Modelling Seed File
Generated for NGR Pit Crew as a starting dataset for telemetry-first track modelling.
## What this file is
- A seed catalogue of GT7 track locations and layouts.
- Public layout facts where the supplied/accessed pages exposed them cleanly.
- A modelling contract for later telemetry refinement.
## What this file is not
- It is not a finished engineering model.
- It does not contain GT7 x/y/z coordinate maps. Those must be captured from telemetry.
- It does not claim unverified kerb, camber, banking or corner-phase data.
## Primary tarmac calibration car
- **Porsche 911 RSR (991) '17**
- Class: Gr.3
- Drivetrain: MR
- Power: 509 BHP
- Weight: 1243 kg
- Tyres: RH
## Sources used
- **GT ENG!NE GT7 Track Maps**: https://gt-engine.com/gt7/tracks/track-maps.html
  - Used for: GT7 layout catalogue, track map visual references, layout naming cross-check
- **DG Edge GT7 Tracks Database**: https://www.dg-edge.com/database/tracks
  - Used for: track location list, variant counts, country/type/surface cross-check
- **GT Plus GT7 Tracks / Layouts**: https://gtplus.app/gt7/tracks
  - Used for: track-level facts, layout-level length/corners/elevation/pit delta where accessed, rain/night/24h/reversible flags where accessed
- **GT Plus Porsche 911 RSR (991) '17**: https://gtplus.app/gt7/cars/porsche-911-rsr-%28991%29-17
  - Used for: primary tarmac calibration car profile
## Seed coverage
- Track locations in seed: **41**
- Layout entries in seed: **121**
- Detailed GT Plus layout facts currently included for: Fuji, Mount Panorama, Watkins Glen, Daytona, Deep Forest, High Speed Ring, Road Atlanta, Red Bull Ring, Spa and Trial Mountain.
## Source-count conflicts to review
Some public sites count reverse layouts/variants differently. These are flagged in the YAML/JSON using `source_count_conflict`. Do not treat count conflicts as defects until reviewed.

## Detailed layout seed rows currently populated
| Track | Layout | Length m | Corners | Elevation m | Pit delta s | Rain | Night | 24h |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Daytona International Speedway | Tri-Oval | 4023 | 4 | 10 | 14 | False | True | True |
| Daytona International Speedway | Road Course | 5729 | 12 | 8.4 | 25 | False | True | True |
| Deep Forest Raceway | Full Course | 4253 | 18 | 50 | 15 | False | True | False |
| Deep Forest Raceway | Full Course Reverse | 4253 | 18 | 50 | 15 | False | True | False |
| Fuji International Speedway | Full Course | 4563 | 16 | 40 | 17 | True | False | False |
| Fuji International Speedway | Short Course | 4526 | 14 | 40 | 17 | True | False | False |
| High Speed Ring | Full Course | 4345 | 6 | 8.5 | 10 | True | False | False |
| High Speed Ring | Full Course Reverse | 4345 | 6 | 8.5 | 10 | True | False | False |
| Mount Panorama Circuit | Full Course | 6213 | 23 | 174 | 24 | False | True | True |
| Red Bull Ring | Full Course | 4318 | 10 | 65.5 | 25 | True | True | False |
| Red Bull Ring | Short Track | 2336 | 6 | 32.4 | 25 | True | True | False |
| Michelin Raceway Road Atlanta | Full Course | 4088 | 12 | 38 | 10 | False | True | True |
| Circuit de Spa-Francorchamps | Full Course | 7004 | 21 | 104 | 25 | True | False | False |
| Circuit de Spa-Francorchamps | 24h Layout | 7004 | 21 | 104 | 35 | True | True | True |
| Trial Mountain Circuit | Full Course | 5434 | 15 | 58 | 26 | False | True | False |
| Trial Mountain Circuit | Full Course Reverse | 5434 | 15 | 58 | 26 | False | True | False |
| Watkins Glen International | Long Course | 5423 | 11 | 41.1 | 10 | False | True | False |
| Watkins Glen International | Short Course | 3942 | 7 | 10.7 | 10 | False | True | False |

## Next modelling step
Build the Track Modelling tab so each selected layout can record Porsche 911 RSR calibration laps, build a reference path, auto-detect straights/braking/corner phases, then refine the model from practice laps.
