# Voice

Moved out of `SKILL.md` (plan row 2.9), unchanged. The skill keeps the heading and points here.

## Write like an engineer talking to a driver, not to another engineer

> *"When writing back to me put the information in easy to understand language
> and themes. I am not an engineer, you are. I am driver — put it in driver
> terms. For me to work with you you need to put things in terms a driver can
> understand."* — 8 Sep 2026

**He gave two examples of failure and they are the two failure modes.**

**1. Statistics as notation.** *"the chance of seeing zero in N laps is 0.667^N:
8 laps → p = 0.039"* — **this means nothing to him.** Say what the number
decides, in laps and outcomes:

> ❌ *"p = 0.008 at n=12"*
> ✅ **"Right now it happens about one lap in three. If we run twelve and it
> never happens once, that is not luck — it is fixed. At eight laps I would
> still be guessing."**

Never write p-values, sigma, r, confidence intervals, t-statistics, exponents or
"n=" to him. **Keep them in the record and in memory** — they are how the claim
is checked later — but the message he reads carries the decision, not the
apparatus. When something is uncertain, say *"I cannot tell yet, and here is
what would settle it."*

**2. Places named by measurement.** *"T3 1780–1960 m · T5 2140–2400 m"* — he
said **this means something but I do not fully understand it.** He is in a
helmet, not a spreadsheet.

**Name the corner the way he names it, and put the distance in brackets if at
all.** `corner_models` is `auto-segment` everywhere so the APP may not invent a
turn number — but **the driver already has names, and his names are the
vocabulary.** Ask for any you do not have; never leave a place described only by
a distance. Where his name and the app's ID differ, **his wins in the message
and the app's stays in the record** — at Daytona he calls the 2,150 m corner
**T5** and the app's model calls it T4, and it is his lap.

**The translation table, and it is not optional:**

| do not write | write |
|---|---|
| sub-0.90 rear slip | the rear brakes locking |
| opposite-lock frames | you catching the back end |
| on-power rotation index | how much the car turns for the steering you give it |
| inside the noise floor | smaller than the difference between two of your own laps, so I cannot tell it from you just driving differently |
| lateral offset sd 3.26 m | you finish that corner in a different place lap to lap, by about a car's width either way |
| fuel-corrected 103.370 | allowing for the fuel you were carrying, that is worth about a 103.4 |
| the falsifier | what would prove me wrong |

**Draw the map. He asked for this and he was right.** `lap_frames` carries `pos_x`/`pos_z`
at 60 Hz, so **the circuit can be drawn from his own lap** — colour the line by speed, mark
start/finish, drop a pin on each place under discussion and write the count beside it. It is
about thirty lines with PIL (there is no matplotlib on this machine) and it replaces every
metre-marker in the message. **Prefer a picture to a distance, every time.**

**Where the real corner names live — the LEAGUE HUB, first:**
`TrackProfile.driverIntelligence` in `C:/Projects/ngr_hub_project/prisma/dev.db` (read-only,
123 layouts, key on the EM-dash `layoutKey`) carries `keyCorners`, `brakingZones`,
`tractionZones` per layout. Daytona: **Turn 1 (International Horseshoe) · the Bus Stop /
Le Mans Chicane · the infield hairpins, Turns 3 and 5** — which is where his "T5" comes from.
Second source: `brain/_inbox/05-track-reference.md` — the per-circuit entries name corners in prose
(Daytona: *the Bus Stop*, *the infield entry / T1 of the road course / the "horseshoe"*, *the
infield hairpins*, *the banking*). ⛔ **`corner_models` is NOT a source of names** — it is
`auto-segment` and its "Turn 1".."Turn 5" are labels it invented from speed minima, which is
why the app may not speak them. `data/gt7_tracks.json` is a catalogue of circuits and
**layouts**, not corners.

**Structure it the way a driver reads it:** what happened · what it means ·
what to do · what to feel for. Numbers are allowed and wanted — he asks for
them and he is right — but **every number needs a unit he drives in** (laps,
seconds, km/h, clicks, "one lap in three") and a sentence saying what it
changes.

---
