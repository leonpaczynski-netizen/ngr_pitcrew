# GT7 Gr.3 TRACK REFERENCE — Competitive League Edition
**Physics baseline: post-1.49 (Update 1.49, July 2024) through current 2026 builds.** Compiled August 2026.

> **🟠 11 Sep 2026 — the 1.71 pass (plan row 2.8).** Three kinds of line in this file no longer hold as written. Each is flagged where it stands.
>
> 1. **Every "LSD acceleration sensitivity: N–M" band is on the v1.70 5–60 scale.** On v1.71 every car in `range_records` reads 0–30 / 0–100 / 0–100, so each band now addresses a different slider. Read a band as a direction only (more or less lock than the car's own baseline), and issue the value in percent of the car's own range (`11`), never as the number printed here.
> 2. **"The undercut is strong / works / is powerful" is re-flagged at every circuit that says it.** In GT7 the undercut is weak: a cold out-lap costs 0.5–1.5 s and the pit delta is long, while the overcut is comparatively strong (`CLAUDE.md` §5.4). The one in-house measurement agrees — a **1.41 s** out-lap on fresh tyres at Deep Forest, 6 Sep. None of these lines was measured; each is an F1 instinct carried into a game where it does not pay.
> 3. **The per-circuit wear figures and the `wearSeverity` grades are refuted where they have been tested.** Deep Forest's "13–16 laps at 1x" measured about three times too pessimistic on the race's wear rate (four on practice's), and its severity 5 ran gentler per kilometre than Red Bull Ring's 3 (`RECONCILIATION` AS4). Measure before using any of them.
>
> The pit-loss figures are still estimates unless a stop has been measured at that circuit; the Deep Forest entry says which of its numbers were measured.

---

## 0. How to read this document

### 0.1 Scope and honesty notes

Before the entries, four things you need to know about the reliability of what follows:

**Lap times are ballparks, not records.** Gr.3 in GT7 is a BoP class, and BoP has been revised repeatedly since 1.49. Community BoP testing puts Gr.3 top-speed brackets roughly in the **265–283 km/h** band depending on car, with mid-engine cars (Mercedes-AMG GT3, Ferrari 458 GT3, Viper GT3-R) generally at the sharp end on most layouts ([GTPlanet Gr.3 BoP Test](https://www.gtplanet.net/forum/threads/gr-3-bop-test.425451/)). Times below assume a competitive-but-human alien-adjacent pace on Racing Mediums, dry, clear, no tow. Expect ±1.5% between the best and worst BoP cars at any given track, and more than that at the aero extremes (Monza, Le Mans, SSRX).

**Pit-lane loss figures are estimates.** GT7 does not publish pit deltas and the community has never systematically measured them post-1.49. The only hard number I could source is **Le Mans at roughly 32 seconds**, derived from a 550 m pit lane at the 60 km/h limit, with forum consensus that **Bathurst, Daytona and Spa are also long** ([GTPlanet pit lane thread](https://www.gtplanet.net/forum/threads/pit-lane.426905/)). Everything else in the "pit loss" lines is my estimate from pit-lane geometry and should be **measured by your league** with a two-car test (one pits, one stays out, compare deltas over the pit lap) before you build strategy on it. I have flagged confidence per track.

**Two of your listed "tracks" are duplicates.** GT7 names them **Michelin Raceway Road Atlanta** and **WeatherTech Raceway Laguna Seca** — those are the same venues as "Road Atlanta" and "Laguna Seca" ([GT7 track list](https://gtplus.app/gt7/tracks)). I have covered each once, under the full name.

**Two of your listed "tracks" are not Gr.3 venues.** **Colorado Springs** and **Lake Louise** are rally surfaces in GT7 — dirt and snow respectively. You cannot run a Gr.3 car on them in any meaningful competitive sense. **Broad Bean Raceway is also not part of Kyoto Driving Park** — it is a separate 1.7 km Japanese original circuit. Details in §3.

**Track lengths and corner counts** throughout are from the [gtplus.app layout database](https://gtplus.app/gt7/tracks/layouts), which matches in-game values.

### 0.2 The GT7 setup levers, and what they actually do post-1.49

You need shared vocabulary before the per-track advice makes sense.

| Lever | GT7 range | Effect | Notes post-1.49 |
|---|---|---|---|
| **Downforce (front / rear)** | Per-car, e.g. 100–300 front, 150–500 rear on many Gr.3 | Rear wing generates far more force per click than the front splitter | Balance by *ratio*, not absolute. Reducing both ends together is the drag lever; moving one end is the balance lever |
| **Natural frequency (springs)** | ~1.20–4.50 Hz | Platform control | 1.49 changed suspension geometry calculations and damper attenuation — cars respond more to spring/damper changes than pre-1.49 |
| **Damper compression / expansion** | 0–100 each end | Transient control | Community convention: **expansion higher than compression**. Baseline ~30 comp / 40 exp; drop compression 2–3 clicks on bumpy tracks |
| **Ride height / rake** | Per-car | Negative rake = top speed, positive rake = turn-in precision | The single most behaviour-changing setting in GT7 per Coach Dave. Bottoming out post-1.49 is genuinely destabilising |
| **Anti-roll bars** | 1–10 | Lateral load transfer split | MR baseline ~6F/3R, FR ~6F/4R; **add roughly +2 both ends on racing tyres** |
| **LSD initial torque** | 5–60 *(v1.70; v1.71 reads 0–30)* | Preload — how locked the diff is off-throttle/neutral | High initial = entry understeer. Keep low (5–15) on turn-in-limited tracks |
| **LSD acceleration sensitivity** | 5–60 *(v1.70; v1.71 reads 0–100)* | Lock under power | The traction lever. FR baseline ~25, MR ~15, RR ~15 — v1.70 numbers, a direction only |
| **LSD braking sensitivity** | 5–60 *(v1.70; v1.71 reads 0–100)* | Lock off-throttle | Stability on entry. MR ~20, RR ~25, FR ~10 — v1.70 numbers, a direction only |
| **Brake balance** | −5 (front) to +5 (rear) on the in-race slider | Entry stability vs rotation | In-race adjustable on most league configs. Front bias for downhill/heavy/slow; rear bias for fast flowing and trail braking |
| **Camber** | Racing tyres: ~−2.0 to −2.5 front, −1.5 to −2.0 rear | Peak lateral grip | Over-camber costs braking and traction and raises inner-shoulder wear |
| **Toe** | Front 0.00, rear +0.05 typical | Stability | Any deviation from zero scrubs and raises wear — significant on high-wear tracks |
| **Gearing** | Final drive + individual ratios | Top speed vs exit | Set final drive to the right extreme first, then walk left to the target top speed |

Sources for the above ranges: [Coach Dave GT7 tuning guide](https://coachdaveacademy.com/tutorials/gran-turismo-7-tuning-explained/), [Flux89 GT7 tuning cheat sheet](https://www.flux89.com/guides/gt7-tuning-cheat-sheet), [DG EDGE brake balance guide](https://www.dg-edge.com/articles/guides-equipment/mastering-brake-balance-in-gran-turismo-7/360).

### 0.3 What 1.49 changed, and why it matters to your league

Update 1.49 shipped a genuinely new physics simulation model. The changes that affect setup work ([GTPlanet 1.49 coverage](https://www.gtplanet.net/gran-turismo-7-update-149-available-20240725/)):

- **Suspension geometry calculations improved** and damper attenuation adjusted — spring and damper changes now produce more coherent, more differentiated results. Pre-1.49 "just go stiff everywhere" setups no longer dominate.
- **Racing tyres got new heating and degradation characteristics.** This is the big one for multi-stop formats. Thermal state now matters within a stint; out-laps and cold-tyre restarts are materially slower, and abusive driving in the first two laps of a stint costs you at the end.
- **Low-speed tyre behaviour adjusted** — hairpin and chicane exits behave differently, generally more progressive.
- **Rolling resistance and wet grip loss changed.**
- **New default suspension and aero settings for all race cars**, and all PP values recalculated. Every leaderboard was reset.

Practical consequence: any GT7 setup sheet or track guide dated before **July 2024** should be treated as directionally useful but numerically obsolete. Tyre-management technique is worth more lap time in a race stint than it was pre-1.49.

### 0.4 Tyre compound reality check

There is **no reliable published lap-time delta or wear-rate table** for GT7 racing hards/mediums/softs. The GTPlanet thread on the subject explicitly concludes that compound comparisons are too car-, setup-, track- and style-dependent to generalise, and community members have called out AI-generated "50–60% worn softs equal fresh mediums" claims as fabricated ([GTPlanet: Racing soft tyres vs medium](https://www.gtplanet.net/forum/threads/racing-soft-tires-vs-medium.427384/)).

The recommended method, which your league should adopt: **one flying lap on fresh softs, one on fresh mediums, then run both until the times converge.** That crossover lap is your strategy input. Do it per track, at your league's wear multiplier.

Working rules of thumb that survive scrutiny: soft is roughly 0.5–0.9 s/lap faster than medium on a ~1:40 lap when both are fresh; medium to hard is a smaller step than soft to medium; and the soft's advantage decays non-linearly, collapsing rather than fading. Stint lengths quoted below are **at 1x wear** unless stated — divide by your multiplier.

For calibration on what leagues and Sport Mode actually run: a recent Gr.3 daily was **Deep Forest, 16 laps, 2x fuel / 5x tyre, mediums-or-softs choice** ([DG EDGE, week 27 2026](https://www.dg-edge.com/articles/news/gt7-daily-races-week-27-2026-autopolis-mount-panorama-deep-forest/701)), while the first week of August 2026 ran **Monza / Red Bull Ring / Tokyo East CW all at 1x with no mandatory stop** ([GTPlanet dailies, 3 Aug 2026](https://www.gtplanet.net/gran-turismo-7-daily-races-running-like-clockwork-20260803/)). Both formats are live in the current meta.

---

# 1. REAL CIRCUITS

---

## 1.1 Nürburgring Grand Prix
**5.1 km · 17 corners · Gr.3 ≈ 1:55–1:57**

**Layout character.** Two circuits bolted together: a slow, stop-start Mercedes Arena complex, and a fast, flowing, aero-dependent back half. Modern-spec, wide, forgiving run-off. The standard league opener because it rewards a balanced car and produces clean racing.

**Downforce: MEDIUM-HIGH.** Full-throttle share is only around 50–55%. The NGK chicane exit through to Turn 1, and the fast Coca-Cola/Bit-Kurve sequence, are all sustained-load corners where aero pays. Only the run down to the Veedol chicane rewards low drag, and it is not long enough to justify trimming out. Run near the top of your car's aero window and lose a little on the straight.

**Dominant corner types & grip priority.** Genuinely mixed, which is why it is a good baseline track. The Mercedes Arena (T2–T5) is 1st–2nd gear hairpin work — pure mechanical grip. The back section (T8 onward, Bit-Kurve, Coca-Cola) is 4th–5th gear sustained load — pure aero platform. **Priority: aero platform first, but do not sacrifice low-speed traction to get it.** If you have to pick, a car that is 0.2 s worse in the Arena and 0.4 s better in the back half wins here.

**Kerbs & elevation.** Elevation change is modest (~40 m) but not flat — Turn 1 climbs, the run to Dunlop descends. Kerb severity is **moderate to high**: the Arena kerbs are usable, but the **Veedol chicane kerbs are launchers** and will pitch the car into the wall if you attack them with a stiff, low car. Implication: do not run minimum ride height. Keep rear compression damping soft enough that the Veedol kerb strike does not unload the rear. Medium-stiff springs; this is not a bumpy track otherwise.

**Braking zones.** Three heavy, two medium. **Turn 1 (Castrol-S)** from top speed on a very slight rise — the rise helps, this is a comfortable stop. **Dunlop hairpin (T5)** heavy and flat. **Veedol chicane (T13)** the heaviest on the lap, from near top speed, flat, with severe kerbs on exit. None are downhill, none are off-camber, none are bumpy. **Brake bias: neutral to one click forward.** This track does not require the forward bias that downhill-braking circuits do, and a slightly rearward setting helps rotate the long Coca-Cola right.

**Traction-limited exits.** Two that matter enormously: **Mercedes Arena exit (T5 onto the short straight)** and **Veedol chicane exit onto the pit straight**. Both are 1st/2nd gear from near-stopped. **LSD acceleration sensitivity: medium — around 20–28 for FR, 15–20 for MR ⚠️ *[v1.70 5–60 scale: a direction, not a number - see the banner]*.** Push it higher and the Veedol exit kerb will spin you; lower and you bog out of the Arena.

**Gearing.** Gear for corner exit, not top speed. **2nd gear should cover the Arena hairpins with a little headroom** so you are not shifting mid-corner. **6th should top out just past the start-finish line into Turn 1 braking** — you should be at or just under the limiter, not bouncing off it for 200 m. There is no straight long enough here for slipstream gearing to pay.

**Tyre wear.** Moderate, and unusually **rear-biased** for a road circuit — the two hard traction exits per lap do the damage, not lateral load. Front wear is even side-to-side because the layout is left/right balanced. Typical stint at 1x: 18–22 laps before the drop-off is costing you real time.

**Pit loss.** Estimated **22–24 s**. Standard modern pit lane, entry after Veedol, exit onto the pit straight. *(Confidence: medium — estimated from geometry.)*

**Top three levers.**
1. **Rear wing level** — sets the entire back-half lap time.
2. **Rear compression damping / ride height combo** for the Veedol kerb.
3. **LSD acceleration sensitivity** — the compromise between the two traction exits and kerb-induced snap.

---

## 1.2 Nürburgring Nordschleife
**20.8 km · 73 corners · Gr.3 ≈ 6:20–6:30**

**Layout character.** The reference. Twenty kilometres of blind, cambered, undulating 1920s road with almost no run-off, three distinct climates of corner, and one 3 km flat-out straight. Community BoP Gr.3 laps have been reported in the **6:23** region even in earlier physics eras ([GTPlanet](https://www.gtplanet.net/forum/threads/6-23-bop-gr3-nordschleife-in-online-game-today.370547/)); post-1.49 pace sits in the low-to-mid 6:20s for the very quick.

**Downforce: MEDIUM.** This is the hardest aero compromise in the game and there is no clean answer. Full-throttle share is high (~60%) because of Döttinger Höhe, but Sector 2 (Kesselchen through Karussell) and the Hatzenbach/Flugplatz complex are heavily aero-dependent. **The correct answer for a race stint is medium-high; the correct answer for a one-lap qualifying run in a slipstream-free session is medium.** If your league runs a rolling start with a tow available on Döttinger, trim 2–3 clicks off the rear.

**Dominant corner types & grip priority.** Everything, but the *character* is fast-to-medium sweepers taken over crests and compressions. Genuine slow hairpins are rare (Adenauer Forst, the Karussell, Brünnchen, Wehrseifen). **Priority: aero platform and, above all, vertical compliance.** A Nordschleife car is not the stiffest car — it is the car that stays flat through Fuchsröhre and Schwedenkreuz without bottoming, and still absorbs Pflanzgarten.

**Kerbs & elevation.** Elevation change is roughly **300 m** — by far the largest in GT7. Kerb severity is **extreme and inconsistent**: the Karussell is a concrete banked drain that will destroy a low, stiff car; Pflanzgarten and Sprunghügel are genuine jumps; Brünnchen compresses hard. Implications, and these are the most important setup notes on this circuit:
- **Ride height must be raised above your track-circuit baseline** — 3–6 clicks. Bottoming at Fuchsröhre or landing from Pflanzgarten on the bump stops post-1.49 will end your lap.
- **Springs softer than a GP-circuit setup**, especially the front.
- **Compression damping notably soft** (drop 3–5 clicks from baseline); **expansion damping firm** so the car settles quickly after the jumps rather than oscillating into the next corner.
- Do not chase positive rake here; the pitch sensitivity over crests will punish you.

**Braking zones.** Around **six genuinely heavy** and a dozen medium. The problems: **Adenauer Forst (downhill, into a compression, off-camber on entry)**, **Bergwerk (heavy, from a fast uphill run, the classic lap-killer)**, **Wehrseifen (steep downhill approach, blind, tightening)**, **Schwedenkreuz-to-Aremberg (fast, slight crest)**, and **Tiergarten/Antoniusbuche at the end of Döttinger Höhe**. Multiple heavy braking zones are downhill or over compressions. **Brake bias: two to three clicks forward** — more than you would use anywhere else. You will lock the rear at Wehrseifen and Adenauer Forst otherwise. If your league allows in-race adjustment, moving one click rearward for the fast Sector 2 and back forward for the Sector 1 downhills is a legitimate technique.

**Traction-limited exits.** **Wehrseifen exit (steep uphill, 1st gear)**, **Bergwerk exit (uphill onto Kesselchen — the single most lap-time-relevant exit on the circuit)**, **Karussell exit (uphill out of the banking)**, and **Hohe Acht/Wippermann**. **LSD acceleration sensitivity: medium-low, 15–22 ⚠️ *[v1.70 5–60 scale: a direction, not a number - see the banner]*.** Counter-intuitive given the uphill traction demands, but the Nordschleife punishes a locked diff on the mid-corner cambered sections far more than it rewards it on the exits. Prioritise the diff not fighting you through Hatzenbach and the Foxhole.

**Gearing.** **Gear for Döttinger Höhe.** 6th should top out roughly 300 m before the Antoniusbuche kink — you want to be on the limiter for a short period only. Critically, **3rd gear must comfortably cover the Karussell and Brünnchen** and **4th must cover Schwedenkreuz and Pflanzgarten** without a shift mid-corner. This is a track where mid-corner upshifts genuinely cost you the car. Spend real time on the intermediate ratios, not just the final drive.

**Tyre wear.** High and **strongly front-biased**, with an asymmetry that depends on direction: the Nordschleife is net **right-hand-heavy through Sector 2 and 3**, so the **front-left is the stint limiter**. Long-radius loaded corners (Schwedenkreuz, Kesselchen, Pflanzgarten, Schwalbenschwanz) do the damage. Expect **3–4 laps at 1x** before front-left degradation is visible in your sector times. This is a fuel-limited circuit as often as a tyre-limited one.

**Pit loss.** Estimated **25–28 s** for the Nordschleife-only configurations. *(Confidence: low — Nordschleife-only pit access differs from the 24h configuration and I found no measured community data. Test it.)*

**Strategy quirks.** Lap time variance between drivers is enormous, so a Nordschleife league race is a reliability contest first. Traffic and blue-flag management is a real strategic factor at 20.8 km. Weather transitions on this circuit are partial — one sector can be wet while another is dry — which makes tyre calls genuinely difficult and is a good reason to run it in a variable-weather endurance slot.

**Top three levers.**
1. **Ride height and compression damping** — the compliance package. Everything else is secondary.
2. **Intermediate gear ratios** (3rd and 4th placement), not the final drive.
3. **Aero level as a race-stint compromise**, biased higher than your one-lap instinct.

---

## 1.3 Nürburgring 24h and Endurance layouts
**24h: 25.4 km · 89 corners · Gr.3 ≈ 7:50–8:00**
**Endurance: 23.9 km · 85 corners · Gr.3 ≈ 7:20–7:30**

**What they are.** The **24h layout** is the GP circuit's Mercedes Arena and back section joined to the Nordschleife, with the additional 24h-race chicanes (notably the Veedol/Yokohama-S variants) — the configuration used for the real N24. The **Endurance layout** is a shorter combination, and is the one Polyphony has used for recent daily races ([racinggames.gg daily guide](https://racinggames.gg/article/gt7-daily-races-a-guide-to-the-eiger-nordwand-grand-valley-nrburgring)).

**Everything in §1.2 applies**, with these deltas:

**Downforce: MEDIUM-HIGH**, one or two clicks more than pure Nordschleife. You are adding the GP circuit's aero-dependent back section and its slow Arena, and removing nothing from the Nordschleife's demands. The Döttinger Höhe drag penalty is amortised over a longer lap.

**Additional braking and traction demands.** The GP section adds two heavy stops (Castrol-S and the GP Veedol chicane) and two more 1st/2nd-gear traction exits. This pushes the LSD compromise slightly toward more acceleration lock — **18–25** rather than 15–22 ⚠️ *[v1.70 5–60 scale: a direction, not a number - see the banner]*.

**Kerbs.** You inherit the GP circuit's launcher kerbs on top of the Nordschleife's Karussell and Pflanzgarten. There is no ride height that is optimal for both; **err toward the Nordschleife setting** since 21 of the 25 km are out there.

**Tyre wear.** Slightly higher than pure Nordschleife because the Arena adds rear-axle traction wear to the front-left lateral wear. Front-left still limits. Around **3 laps at 1x** for a Gr.3 car before meaningful drop-off.

**Pit loss and strategy.** The 24h/Endurance layouts pit into the GP pit complex — estimated **22–25 s**. Because the lap is ~7:50, **pit loss is only ~5% of a lap**, which makes the undercut almost worthless and makes fuel-saving and tyre-life the entire strategy. A one-stop over two laps is the standard daily format. *(Confidence: medium.)*

**Top three levers.** Same as Nordschleife, with **aero level** promoted — the GP section makes the wing pay for itself.

---

## 1.4 Circuit de Spa-Francorchamps
**7.0 km · 21 corners · Gr.3 ≈ 2:16–2:19**

**Layout character.** The best league circuit in the game and the most frequently used. Three completely different sectors: a low-drag Sector 1 (La Source, Eau Rouge/Raidillon, Kemmel), an aero-hungry Sector 2 (Les Combes through Stavelot), and a flat-out Sector 3 (Blanchimont to the Bus Stop). Overtaking is genuinely possible in three places, which is why leagues love it.

**Downforce: MEDIUM-LOW to MEDIUM.** Full-throttle share around 65–70%. This is the classic Spa compromise and it is *strategy-dependent*: if your league has a big grid and a tow down Kemmel, trim the wing and win positions on track. If you are running from the front in clean air, add wing and win it in Pouhon and Stavelot. **Default recommendation for a mixed-format league: two to three clicks below your car's aero midpoint.**

**Dominant corner types & grip priority.** Fast to very fast. **Pouhon (T10–11, a long double-apex downhill left)** and **Blanchimont** are the corners that separate cars, and both are aero-and-platform corners. Only La Source and the Bus Stop are slow. **Priority: aero platform, clearly.** Mechanical grip investment here has poor returns — you only use it twice a lap.

**Kerbs & elevation.** Elevation change ~100 m, dominated by the Eau Rouge/Raidillon climb. Kerb severity: **high at the Bus Stop** (the chicane kerbs are the most punishing on the lap and are unavoidable if you want a good exit) and **high at Les Combes**; low-to-moderate elsewhere. Implications:
- **Ride height is a genuine optimisation problem at Eau Rouge.** Too low and you bottom in the compression and lose the rear on the exit crest; too high and you give up the platform through Pouhon. Set ride height at Eau Rouge, then check it at Pouhon.
- **Front compression damping soft enough** to absorb the Raidillon compression without pitching.
- Rear stiff enough to survive the Bus Stop kerb strike without squatting into oversteer on exit.

**Braking zones.** **Four heavy.** **Les Combes (T5)** is the biggest and is the money overtaking spot — braking uphill, which helps stability and makes it forgiving. **La Source (T1)** is heavy from a downhill approach and is a low-speed hairpin — the trickiest of the four. **Bus Stop chicane (T19)** is heavy from near-top speed with severe kerbs. **Rivage (T8)** is a downhill, tightening, slightly off-camber medium stop that catches people out. **Brake bias: one to two clicks forward.** The downhill entries at La Source and Rivage set the requirement. A rearward bias will bite you at Rivage specifically.

**Traction-limited exits.** **La Source exit is the single most consequential traction event on any circuit in GT7** — it feeds a 1.9 km uphill full-throttle run to Les Combes and a bad exit is worth several tenths *and* your slipstream position. **Bus Stop exit** is second. **LSD acceleration sensitivity: medium-high, 25–32 for FR, 18–24 for MR ⚠️ *[v1.70 5–60 scale: a direction, not a number - see the banner]*.** This is one of the few tracks where erring toward more acceleration lock is correct, because both traction exits feed straights.

**Gearing.** **Gear for slipstream.** 6th should top out **with a tow** at the Les Combes braking board, meaning in clean air you will be slightly short of the limiter — that is correct. Additionally, **4th gear must cover Pouhon** cleanly (no shift at the apex), and **5th must cover Blanchimont**. If you find yourself needing to shift at Pouhon's second apex, redistribute 4th and 5th rather than changing the final drive.

**Tyre wear.** High and **markedly left-side biased**. Spa is a predominantly right-hand circuit at speed — Raidillon, Pouhon, Stavelot, Blanchimont are all sustained rights — so the **front-left is the stint limiter** and the rear-left is second. Expect **12–16 laps at 1x** before the front-left is costing you two-plus tenths. In multi-stop formats the front-left is what dictates your stint length, not fuel.

**Pit loss.** **Long — estimated 28–32 s.** Forum consensus explicitly names Spa among GT7's long pit lanes ([GTPlanet](https://www.gtplanet.net/forum/threads/pit-lane.426905/)). Pit entry is at the Bus Stop, exit is after La Source, so you also give up the La Source exit and Kemmel run on your out-lap. *(Confidence: medium-high on "long", medium on the number.)*

**Strategy quirks.** The long pit lane makes the **overcut relatively strong** at Spa — staying out on degraded tyres in clean air often beats an in-lap/out-lap through a 30 s pit lane. Weather is a live factor: Spa's dynamic weather in GT7 can produce a genuinely split track. Slipstream on Kemmel is powerful enough that a car 1.5 s/lap slower can hold position.

**Top three levers.**
1. **Rear wing level** — the Sector 1 vs Sector 2 trade is the whole setup.
2. **Ride height at Eau Rouge**, cross-checked at Pouhon.
3. **LSD acceleration sensitivity** for the La Source exit.

---
## 1.5 Autodromo Nazionale Monza
**5.8 km · 11 corners (Full) / 9 corners (No Chicane) · Gr.3 ≈ 1:47–1:50 (Full), 1:41–1:44 (No Chicane)**

**Layout character.** Three long straights, three chicanes, two Lesmos, one Parabolica. The lowest-drag circuit in GT7's road-course set and the purest slipstream track. Currently in daily rotation ([GTPlanet, 3 Aug 2026](https://www.gtplanet.net/gran-turismo-7-daily-races-running-like-clockwork-20260803/)).

**Downforce: LOW — the lowest of any road circuit.** Full-throttle share is around 78–80%. Run **minimum or near-minimum rear wing** and trim the front to match. The only corners that ask for aero are Curva Grande and the Parabolica entry, and neither is worth the four-plus km/h per click you pay on the straights. If you find your car undriveable at minimum wing, add front splitter before you add rear wing — the front costs less drag.

**Dominant corner types & grip priority.** **Chicanes.** The Rettifilo (T1–2), Roggia (T4–5) and Ascari (T8–10) define the lap, and all three are about kerb-riding and mechanical grip under braking and on exit. Lesmo 1 and 2 are medium 3rd-gear rights; the Parabolica is a long, decreasing-radius 4th-gear right. **Priority: mechanical grip and kerb compliance, unambiguously.** This is the one high-speed circuit where the aero platform is nearly irrelevant and the low-speed package is everything.

**Kerbs & elevation.** Elevation is effectively **zero** — Monza is flat. Kerb severity is **the highest in GT7**. The sausage kerbs at Rettifilo and Roggia will launch a stiff car into the air and, post-1.49, land it badly. This drives the whole setup:
- **Softer springs than you would run anywhere else at this speed** — the platform is not doing any aero work, so spend the compliance on kerbs.
- **Compression damping notably soft at both ends** (drop 4–6 clicks from baseline).
- **Do not run minimum ride height.** Two to four clicks up. The top-speed cost of a slightly higher car is smaller than the cost of one launched exit at Roggia.
- Consider slightly softer ARBs than baseline — you want diagonal compliance over the kerbs.

**Braking zones.** **Three, all heavy, all flat, all from near-top speed.** The Rettifilo (T1) is the biggest single deceleration event in GT7 Gr.3 racing — roughly 285 km/h to 90 km/h. Roggia and Ascari are both heavy. None are downhill, none are off-camber, none are bumpy — but all three end in a kerb. **Brake bias: one to two clicks forward** for stability into T1, but watch front lockup: Monza's long straights cool the tyres, and the first application at T1 with cooled fronts post-1.49 locks more readily than you expect. If your league allows in-race adjustment, running one click more rearward on cold tyres and forward as they come in is a real technique here.

**Traction-limited exits.** **All three chicane exits, plus the Parabolica.** All are onto long straights, so they are the highest-value exits per unit of time anywhere in GT7. The complication: they are all over kerbs. **LSD acceleration sensitivity: medium-low, 15–22 ⚠️ *[v1.70 5–60 scale: a direction, not a number - see the banner]*.** This is the exception to "traction exits onto straights want more lock" — because the exits are over aggressive kerbs, a locked diff produces snap oversteer on the kerb strike. Take the small bog and keep the car.

**Gearing.** **Gear explicitly for slipstream — this is the most tow-dependent road circuit in GT7.** Set 6th to top out **with a tow** at the Rettifilo braking board; in clean air you should be 200–300 rpm short of the limiter down the main straight. Additionally: **2nd gear must cover all three chicanes** without an upshift between the two apexes, and **4th should carry the Parabolica** cleanly. Getting 2nd right is worth more than getting the final drive right.

**Tyre wear.** **Low to moderate, and rear-biased.** Monza has little sustained lateral load; wear comes from the three traction exits and the Parabolica. Front-right takes more than front-left (Lesmos and Parabolica are rights). Long stints are achievable — **20–25 laps at 1x**.

**Pit loss.** Estimated **20–22 s** — short, straightforward pit lane. *(Confidence: medium.)*

**Strategy quirks.** The dominant one: **slipstream is so powerful that track position is worth less than at any other circuit.** A car 1 s/lap slower will stay attached. Consequences for your league: qualifying matters less; the undercut is strong (short pit loss) ⚠️ *[re-flagged 11 Sep: the undercut is weak in GT7 - see the banner]*; and running in dirty air costs you almost nothing in cornering because you have no aero to lose. Expect large packs and late-race lottery. The **No Chicane variant** removes the Rettifilo and Roggia, converting the circuit into a near-oval — it magnifies every point above, drops the wear further, and is a novelty rather than a serious league layout.

**Top three levers.**
1. **Minimum-drag aero and the matching gearing** (with-tow topping-out).
2. **Kerb compliance package** — soft compression damping, raised ride height, softer springs.
3. **2nd gear ratio placement** for the chicanes.

---

## 1.6 Suzuka Circuit
**5.8 km · 20 corners (Full) · Gr.3 ≈ 1:56–1:59 · East Course 2.2 km, 9 corners**

**Layout character.** The best-designed circuit in the game and the most demanding of a well-balanced car. A figure-of-eight with a rhythm-critical Esses section, two of the hardest corners in sim racing (Degner 2 and 130R), and a slow-corner sequence in the middle that ruins your rhythm on purpose. Used for Online Time Trial #161 (Sep 2025) ([GTPlanet TT index](https://www.gtplanet.net/forum/threads/time-trial-results-and-community-leader-boards.424113/)).

**Downforce: HIGH.** Full-throttle share is only ~55%. The Esses (T3–T7), Degner 1, Spoon entry and 130R all reward every click of wing you can afford. The only cost is the back straight, and the back straight is short by modern standards. **Run at or near your car's maximum aero.** If you are struggling for balance, take it out of the *front* — a rear-heavy aero balance suits Suzuka's fast lefts.

**Dominant corner types & grip priority.** Fast to medium sweepers in sequence. The **Esses** are a linked rhythm section where each corner's exit dictates the next entry — the single largest lap-time differentiator on the circuit. **130R** is a flat-or-nearly-flat 5th-gear left that is entirely a platform-and-aero corner. The hairpin (T11) and the final chicane are the only true slow corners. **Priority: aero platform, decisively.** A Suzuka setup should be one of your stiffer, higher-downforce configurations.

**Kerbs & elevation.** Elevation ~40 m, with meaningful gradient — the Esses climb, Degner descends, the run to the chicane descends. Kerb severity: **moderate in the Esses (usable and necessary), high at Degner 2 and the final chicane.** Degner 2's exit kerb into the wall is the classic Suzuka lap-ender. Implications:
- **Stiffer springs than average** are correct — you need the platform for the Esses and 130R.
- But keep **rear compression damping moderate** for the Degner 2 exit kerb.
- **Slight positive rake** helps the Esses turn-in rhythm; Suzuka rewards a car that changes direction eagerly.
- Ride height can be low — Suzuka is smooth.

**Braking zones.** **Four heavy, two medium.** **The hairpin (T11)** is the biggest and slowest. **Degner 2** is heavy, downhill, and the entry is over a slight crest with the car unloaded — the most dangerous stop on the lap. **The final chicane** is heavy from 130R exit speed and slightly downhill. **Spoon (T13–14)** is a medium-heavy stop into a downhill double-apex left. **Turn 1** is a fast, light, downhill turn-in that most drivers over-brake. **Brake bias: one to two clicks forward** — Degner 2 and the chicane both brake with the car light or descending, and rear lockup at Degner 2 is a wall. Rearward bias is tempting for the Esses but they are not braking corners.

**Traction-limited exits.** **The hairpin exit (T11) is the highest-value exit on the lap** — it feeds a long uphill run through 200R to Spoon. **Spoon exit** onto the back straight is second. **Final chicane exit** onto the pit straight is third. **LSD acceleration sensitivity: medium, 20–28 ⚠️ *[v1.70 5–60 scale: a direction, not a number - see the banner]*.** The hairpin is a long, slow, uphill exit that genuinely wants lock; the constraint is that too much lock ruins the Esses' direction-change.

**Gearing.** **Gear for corner exit and for 130R.** 6th tops out at the end of the back straight before the chicane. Critically: **3rd gear must cover Spoon's second apex** and **the Degner complex**, and **5th must carry 130R without a shift**. A shift at 130R apex will cost you the car post-1.49. The Esses should sit comfortably in 4th throughout — if you are bouncing between 3rd and 4th in the Esses, your ratios are wrong.

**Tyre wear.** **High and front-biased — Suzuka is the hardest circuit in GT7 on front tyres.** The Esses generate continuous, alternating high lateral load with no recovery, and 130R and Spoon add sustained load on top. Because the Esses alternate direction, front wear is relatively **even side-to-side**, which is unusual and makes it a pure front-axle-life problem rather than a one-corner problem. Expect **12–15 laps at 1x**. Manage it by not over-driving the Esses entry in the first three laps of a stint — post-1.49 thermal behaviour punishes early abuse.

**Pit loss.** Estimated **21–23 s**. *(Confidence: medium.)*

**Strategy quirks.** Overtaking is genuinely hard — realistically only T1 and the chicane. That makes **qualifying and track position more valuable at Suzuka than almost anywhere else**, and makes the undercut strong ⚠️ *[re-flagged 11 Sep: the undercut is weak in GT7 - see the banner]*. In multi-stop formats, an aggressive early stop to get clean air is usually correct here even at a small tyre-life cost ⚠️ *[re-flagged 11 Sep: this is the undercut in other words - weak in GT7, and unmeasured here]*. The **East Course** (2.2 km) is a short-format novelty: T1 through the Esses then a link back — it is a mechanical-grip, high-wear sprint layout and not representative.

**Top three levers.**
1. **Aero level and front/rear aero balance** — set it in the Esses.
2. **3rd/4th/5th ratio placement** for Spoon, the Esses and 130R.
3. **Front-tyre-life management setup** — a touch less front camber and neutral toe to extend the stint.

---

## 1.7 Brands Hatch — Grand Prix
**3.9 km · 9 corners · Gr.3 ≈ 1:22–1:24**

**Layout character.** A short, violently undulating circuit with one of the great opening corners and a fast, open GP loop. Deceptively simple corner count hides a lot of blind, committed driving.

**Downforce: MEDIUM-HIGH.** Full-throttle share ~50%. There is no straight worth mentioning; the GP loop (Sheene, Stirling's, Clearways, Clark Curve) is all sustained load. **Run high.** The drag cost is nearly free here.

**Dominant corner types & grip priority.** Medium-fast, with one hairpin. **Paddock Hill Bend (T1)** is the circuit: a downhill, off-camber, blind-apex right taken while still shedding speed, with the road falling away underneath you. **Druids (T2)** is a slow uphill hairpin. Everything after that is 3rd–5th gear commitment. **Priority: aero platform and pitch control**, with just enough mechanical grip for Druids.

**Kerbs & elevation.** Elevation is severe for such a short lap (~40 m over 3.9 km, but concentrated). The **Paddock Hill descent and compression**, the **Dingle Dell dip**, and the **Hawthorn crest** are all vertical events. Kerb severity is **moderate** — the kerbs are old-school and mostly usable — but the **compressions matter more than the kerbs here.** Implications:
- **This is a compliance track disguised as a grip track.** Do not run your stiffest setup.
- **Front compression damping soft** for the Paddock Hill compression; if the front bottoms there the car will understeer off at the exit.
- **Ride height 2–4 clicks up** from a flat-circuit baseline.
- **Expansion damping firm** so the car settles quickly out of Dingle Dell into Stirling's.

**Braking zones.** **Two heavy, two medium.** **Paddock Hill (T1)** — heavy, downhill, off-camber, and you are turning while braking. This is the defining brake-balance problem of the circuit. **Druids (T2)** — heavy, uphill, straightforward. **Surtees** and **Clark Curve** are medium. **Brake bias: two to three clicks forward — one of the most forward settings you should run anywhere.** Paddock Hill unloads the rear axle at exactly the moment you are asking it to both brake and turn; a rearward bias there is a spin.

**Traction-limited exits.** **Druids exit** (downhill, so relatively easy) and, critically, **Clark Curve onto the pit straight** — the only overtaking-relevant exit and the one that sets your lap. **Surtees exit** matters for the run to McLaren. **LSD acceleration sensitivity: medium, 20–26 ⚠️ *[v1.70 5–60 scale: a direction, not a number - see the banner]*.** Nothing extreme — most exits here are loaded and downhill.

**Gearing.** **Gear entirely for corner exit.** 6th is barely used; on many Gr.3 cars you will only touch it briefly on the pit straight. Focus on **2nd for Druids** and **3rd/4th for Surtees, McLaren and Clearways**. A common mistake is running the stock long final drive and finding the car bogged out of Druids.

**Tyre wear.** **High for the lap length, front-biased, and strongly left-side.** Brands GP is dominated by long-radius right-handers (Paddock, Clearways, Clark Curve) — the **front-left is the limiter**. Because the lap is short, degradation per lap looks alarming in percentage terms. **14–18 laps at 1x.**

**Pit loss.** Estimated **18–20 s**. *(Confidence: medium.)* Because the lap is only ~1:23, **pit loss is ~24% of a lap — one of the highest ratios in GT7.** That has real consequences.

**Strategy quirks.** The high pit-loss-to-lap-time ratio makes stops expensive and makes **stint extension attractive**, but Brands' front-left wear works against that — it is a genuine two-sided strategy problem, which makes it an excellent league track. Overtaking is realistically Paddock Hill (brave) and Druids (from a Paddock Hill exit run). Traffic on a 3.9 km lap in a full field is constant.

**Top three levers.**
1. **Brake balance (forward) and front compression damping** — the Paddock Hill package.
2. **Front-left preservation** — front ARB and camber.
3. **Gearing for Druids and Clark Curve exits.**

---

## 1.8 Brands Hatch — Indy
**1.9 km · 5 corners · Gr.3 ≈ 0:44–0:46**

**Layout character.** Paddock Hill, Druids, Graham Hill Bend, Surtees, then straight back to the line via Clearways/Clark Curve. Under 45 seconds. A pure sprint layout.

**Downforce: MEDIUM.** Less than GP — you lose the aero-loaded GP loop, and the short lap makes the straight-line penalty proportionally larger. Two to three clicks below your GP setting.

**Dominant corner types & grip priority.** Same corners as GP minus the loop. **Priority: mechanical grip moves up relative to GP** because Druids and Graham Hill are now a larger share of the lap.

**Kerbs & elevation.** Identical to GP for the shared corners — Paddock Hill compression dominates.

**Braking zones.** **Two: Paddock Hill and Druids.** Both discussed above. **Brake bias two to three clicks forward.**

**Traction-limited exits.** Druids and Clearways. **LSD acceleration: 20–26 ⚠️ *[v1.70 5–60 scale: a direction, not a number - see the banner]*.**

**Gearing.** Very short. 4th or 5th max. Gear tightly around Druids and Clearways exits.

**Tyre wear.** **Severe per lap.** Every corner on this layout is a loaded one; there is no recovery straight. Front-left again. **Around 8–12 laps at 1x** before real drop-off — treat it as a high-wear layout despite the short distance.

**Pit loss.** Estimated **18–20 s** — which is **~42% of a lap time.** This is the most extreme pit-loss ratio of any tarmac layout you would race.

**Strategy quirks.** That ratio changes everything: a mandatory stop at Brands Indy is a huge event, the pit window is narrow, and undercuts barely function because the out-lap on cold tyres costs more than the tyre advantage gains. Lapped traffic appears within ten laps. **Best used for short sprints with no stops, or as a deliberately chaotic reverse-grid race.**

**Top three levers.**
1. **Brake balance forward** for Paddock Hill.
2. **Front-left tyre preservation** — this is the whole race in longer formats.
3. **Short gearing** for the two slow exits.

---

## 1.9 Autódromo José Carlos Pace (Interlagos)
**4.3 km · 15 corners · Gr.3 ≈ 1:31–1:33**

**Layout character.** Counterclockwise, bumpy, short, and built around one long uphill full-throttle run from Junção to Turn 1 that makes it one of the best overtaking circuits in the game.

**Downforce: MEDIUM.** Full-throttle share ~62%. The long uphill run wants low drag, but the Senna S, Ferradura and Mergulho all want load. **Slightly below the aero midpoint** is the standard answer, biased lower if your league is slipstream-heavy.

**Dominant corner types & grip priority.** Medium-speed, with two slow corners. The **Senna S (T1–2)** is a downhill left-right taken in 2nd/3rd; **Descida do Lago (T4–5)** is a fast downhill double-left; **Ferradura (T7)** is a long, tightening, downhill right; **Junção (T12)** is a slow uphill left. **Priority: split — mechanical grip for the Senna S and Junção, compliance for the bumps.** The aero platform matters less here than at most medium-downforce circuits because the surface will not let you use it.

**Kerbs & elevation.** Elevation ~40 m and continuous — Interlagos is either descending or climbing. Kerb severity moderate. **The critical feature is that the surface is bumpy, notably through the Senna S and the Curva do Sol.** Implications:
- **Softer springs and notably soft compression damping** — drop 4–5 clicks. This is the softest setup on your real-circuit list after Tokyo Expressway.
- **Ride height up 2–3 clicks.**
- A stiff Interlagos car skates over the bumps in the Senna S and will not rotate.

**Braking zones.** **Two heavy, three medium.** **Senna S (T1)** is heavy, downhill, bumpy, and you are turning in as you release — the classic Interlagos challenge and the main overtaking spot. **Descida do Lago (T4)** is a medium-heavy downhill stop. **Junção (T12)** is a medium stop but critical for the exit. **Brake bias: two clicks forward.** The T1 entry is downhill *and* bumpy — the two conditions that most demand front bias.

**Traction-limited exits.** **Junção (T12) exit is the highest-value exit on the circuit** — it feeds the 1.2 km uphill full-throttle climb to T1, so every tenth there is compounded and it determines whether you have a tow. **Senna S exit** onto the Curva do Sol is second. **LSD acceleration sensitivity: medium-high, 24–30 ⚠️ *[v1.70 5–60 scale: a direction, not a number - see the banner]*.** Junção is uphill, slow, and feeds a straight — exactly the profile that wants lock.

**Gearing.** **Gear for the uphill run with slipstream.** 6th should top out with a tow just before the T1 braking board. **2nd must cover Junção** cleanly with the uphill load. **3rd must carry Ferradura** without a shift.

**Tyre wear.** **Moderate-high, and heavily right-side biased** — Interlagos is counterclockwise, so the sustained loads (Curva do Sol, Ferradura, Mergulho, Junção) all load the right-hand tyres. The **front-right is the stint limiter**, with the rear-right second from the Junção exits. Expect **14–18 laps at 1x.** The bumps add wear beyond what the corner profile suggests.

**Pit loss.** Estimated **19–21 s**. *(Confidence: medium.)* Pit entry is at Junção, so the in-lap costs you the best part of the circuit.

**Strategy quirks.** The Junção pit entry means an in-lap here is unusually expensive relative to the lap time — factor roughly an extra half-second. The huge tow on the pit straight means **track position is less durable than at other circuits**, so aggressive strategy is rewarded. Excellent for multi-stop formats.

**Top three levers.**
1. **Bump compliance package** — soft compression damping, raised ride height.
2. **LSD acceleration sensitivity** for Junção.
3. **Brake bias forward** for the bumpy downhill T1.

---

## 1.10 Red Bull Ring
**4.3 km · 10 corners (Full) · Gr.3 ≈ 1:24–1:26 · Short Track 2.3 km, 6 corners**

**Layout character.** Ten corners, three of them big braking events, two long uphill straights, and 65 m of elevation crammed into a very short lap. Simple to learn, extremely hard to perfect. Used for Online Time Trials #97 (Aug 2024) and #147 (Jun 2025), and in current daily rotation.

**Downforce: LOW to MEDIUM-LOW.** Full-throttle share ~68%. Two long straights on a 4.3 km lap is a lot of drag exposure, and the corners are mostly point-and-squirt rather than sustained-load. **Run two to four clicks below the midpoint.** The only corners asking for wing are T6/T7 and the T9–T10 sequence.

**Dominant corner types & grip priority.** Predominantly **medium 2nd/3rd-gear corners taken uphill or over crests.** T1 (Niki Lauda) is a 2nd-gear uphill right; T3 (Remus) is a 2nd-gear uphill right; T4 (Schlossgold) is a 3rd-gear right at the top of the climb. T6 and T7 are faster. T9–T10 is a downhill left-right onto the pit straight. **Priority: mechanical grip and traction, clearly.** This is one of the few low-downforce circuits where mechanical grip is still the primary lever, because none of the corners are fast enough to make aero pay.

**Kerbs & elevation.** Elevation ~65 m on a 4.3 km lap — steep, sustained gradients. Kerb severity: **high at T6, T7 and T9–T10**, where the exit kerbs are both severe *and* the track-limits enforcement point. In GT7 you will collect penalties at T9/T10 exit repeatedly. Implications:
- **Medium-stiff springs**, but with **soft rear compression damping** — the T6/T7 exit kerb strikes with the car light on the crest is the main destabilising event.
- **Ride height mid-range**; the gradients load and unload the car meaningfully and a very low car will bottom on the T1 and T3 exits under uphill compression.
- Watch rear ride height specifically: uphill acceleration squats the rear.

**Braking zones.** **Three heavy, all uphill or on a crest.** **T1** from top speed, braking uphill (which helps). **T3 (Remus)** from top speed, braking uphill — the biggest overtaking spot in the game for stopping distance variability. **T4** medium-heavy. None are downhill, none are bumpy. **Brake bias: neutral to one click forward.** Uphill braking loads the front naturally, so you need less forward bias here than on almost any other circuit — and a slightly rearward setting helps rotate the tight T3.

**Traction-limited exits.** **Three, all uphill, all onto straights** — this is a traction circuit. **T1 exit** (uphill onto the run to T3), **T3 exit** (uphill onto the long run to T4 — the most valuable), and **T10 exit** onto the pit straight. **LSD acceleration sensitivity: high for GT7, 28–35 for FR, 22–28 for MR ⚠️ *[v1.70 5–60 scale: a direction, not a number - see the banner]*.** Red Bull Ring rewards diff lock more than almost any other circuit on this list, because all three critical exits are slow, uphill and feed straights.

**Gearing.** **Gear for slipstream.** 6th tops out with a tow at the T3 braking board. **2nd gear must cover T1, T3 and T10** with headroom — a mid-corner upshift at T3 is a common and costly error. This is a track where a very short 2nd and a long 6th, with a big gap between 2nd and 3rd, is defensible.

**Tyre wear.** **Moderate, and rear-biased** — the three uphill traction exits do more damage than the lateral loads. Front-right takes more than front-left (T1, T3, T4, T6 are all rights). Expect **16–20 laps at 1x.** For a short lap this is relatively kind.

**Pit loss.** Estimated **19–20 s**. *(Confidence: medium.)*

**Strategy quirks.** The **slipstream on both straights is very strong** and the braking zones are wide, so overtaking is easy and track position is cheap. This makes Red Bull Ring one of the best circuits for reverse-grid or handicapped formats. In multi-stop races, the undercut works well (short pit loss, big out-lap traction gains on fresh tyres at T1/T3) ⚠️ *[re-flagged 11 Sep: the undercut is weak in GT7, and a fresh-tyre out-lap measured 1.41 s SLOWER at Deep Forest - see the banner]*. Track-limit penalties at T9/T10 are a genuine race-management factor — brief your drivers.

**Top three levers.**
1. **LSD acceleration sensitivity** — the highest-value single setting at this circuit.
2. **2nd gear ratio** for the three slow uphill exits.
3. **Low-drag aero plus with-tow gearing.**

---
## 1.11 Autopolis International Racing Course
**4.7 km · 18 corners (Full) / 3.0 km · 11 corners (Shortcut) · Gr.3 ≈ 1:41–1:44 (Full)**

**Layout character.** A Japanese mountain circuit that is far harder than its reputation: 18 corners, most of them medium-speed, many of them blind over crests, with substantial and constant elevation change. Very little of the lap is spent going in a straight line. In recent daily rotation ([DG EDGE week 27 2026](https://www.dg-edge.com/articles/news/gt7-daily-races-week-27-2026-autopolis-mount-panorama-deep-forest/701)).

**Downforce: HIGH.** Full-throttle share is low, around 45–50%. Almost every corner is a 3rd/4th-gear sweeper where downforce directly converts to speed, and the only straight is the back straight. **Run near maximum.** Autopolis and Suzuka are the two circuits where I would not trim aero for any strategic reason.

**Dominant corner types & grip priority.** **Medium 3rd-gear sweepers, in sequence, mostly blind.** T1 is a fast downhill right; the middle sector is a rhythm section of linked medium corners over crests; there is one genuine hairpin at the end of the back straight. **Priority: aero platform and vertical stability, decisively.** The corners are fast enough for aero to pay but the crests mean you must actually be able to *use* the aero — a car that skips over crests loses more than one with a smaller wing.

**Kerbs & elevation.** Elevation is large and continuous (~50 m) with numerous **blind crests where the car goes light mid-corner.** Kerb severity is **moderate** — Autopolis has modern, fairly flat kerbs. Implications:
- **This is the classic "stiff enough for aero, soft enough for crests" problem.** Set springs medium-stiff, then use damping to solve the crests.
- **Expansion (rebound) damping is the key setting here** — you need the car to extend controllably over the crests and settle immediately. Run expansion notably higher than compression, more than your baseline gap.
- **Ride height slightly up** from a flat-circuit setting to survive the compressions on the far side of the crests.

**Braking zones.** **One very heavy, three medium.** The **hairpin at the end of the back straight** is the only genuine big stop. **T1** is a fast, light, downhill turn-in. The rest are medium, and several are on descents. **Brake bias: one to two clicks forward** — the downhill sections and the crest-unloading argue for it.

**Traction-limited exits.** **Primarily the hairpin exit**, which feeds the run back to the start of the lap. Most other exits are loaded and fast. **LSD acceleration sensitivity: medium-low, 15–22 ⚠️ *[v1.70 5–60 scale: a direction, not a number - see the banner]*.** Autopolis' rhythm sections punish a locked diff — you need the car to change direction repeatedly and a high acceleration setting will push you wide at every linked exit. Take the small hairpin loss. ⚠️ *[The "a locked diff pushes you wide" half is CONTESTED on v1.71 — the one in-house test of lowering accel for a power-on push was refuted (Huracán, Daytona, s145); see `02` §10.5. The traction half stands.]*

**Gearing.** **Gear for the back straight**, with 6th topping out at the hairpin board. Critically, **3rd and 4th must be spaced so the rhythm section can be driven in a single gear per sequence.** Autopolis is a track where drivers lose more time to unnecessary shifting than to ratio choice.

**Tyre wear.** **High and front-biased.** Continuous medium-speed lateral load with no recovery. Autopolis is reasonably direction-balanced, so wear is more even side-to-side than at Barcelona or Spa — it is a front-axle-life problem. Expect **13–16 laps at 1x.**

**Pit loss.** Estimated **21 s**. *(Confidence: low — limited community data.)*

**Strategy quirks.** Overtaking is genuinely difficult — realistically only the hairpin. That makes qualifying valuable and the undercut strong ⚠️ *[re-flagged 11 Sep: the undercut is weak in GT7 - see the banner]*. The **Shortcut Course (3.0 km, 11 corners)** removes the fastest section and becomes a compact technical layout — it is used for one-make and Gr.4 dailies more than Gr.3.

**Top three levers.**
1. **Expansion damping** for the crests — the highest-value setting here.
2. **Maximum usable aero.**
3. **3rd/4th ratio spacing** to eliminate mid-sequence shifts.

---

## 1.12 Fuji International Speedway
**4.6 km · 16 corners (Full) / 4.5 km · 14 corners (Short) · Gr.3 ≈ 1:33–1:36 (Full)**

**Layout character.** A 1.5 km main straight — the longest of any conventional circuit in GT7 outside Le Mans and the ovals — followed by a technical middle sector and a fast final sequence. Two circuits in one lap. Used for Online Time Trial #25.

**Downforce: MEDIUM-LOW.** Full-throttle share ~63%, but heavily concentrated in one place. That concentration matters: 1.5 km of straight means every click of wing costs you a lot at exactly the point where you are overtaking or defending. **Run three to four clicks below your car's midpoint.** The middle sector will feel loose; accept it.

**Dominant corner types & grip priority.** Mixed, leaning medium. **T1 (TGR Corner)** is a heavy 2nd-gear right. The middle sector (T3–T7) is a set of linked medium corners. **Coca-Cola / Dunlop (T8–9)** is a long, loaded right. **The 100R (T10)** is a fast right. **The hairpin (T11)** is slow. **300R (T13)** is fast. **Panasonic (T15–16)** is a slow, tightening double-right onto the main straight. **Priority: mixed, with a strong bias toward the final-sector exit.** Fuji rewards a car set up to be excellent at exactly one corner: the last one.

**Kerbs & elevation.** Elevation is modest (~35 m) with a gentle rise through the middle sector and a descent from 300R. Kerb severity is **moderate** — modern Japanese kerbs, mostly usable, with the exception of the Panasonic exit kerb where you will collect track-limit penalties. Implications: this is a relatively forgiving circuit for suspension. **Medium springs, low ride height, standard damping.** Fuji is where you can run your stiffer, lower baseline without penalty.

**Braking zones.** **Two very heavy, two medium.** **Turn 1** is a genuinely enormous stop — from near top speed at the end of 1.5 km down to around 90 km/h, on a flat, smooth, wide entry. This is the best overtaking opportunity on any real circuit in GT7. **The hairpin (T11)** is heavy. **Coca-Cola** and the **Panasonic entry** are medium. **Brake bias: one click forward.** The T1 stop is flat and smooth so it does not demand much forward bias, and the tyres are cool after the long straight — the same cold-tyre lockup caution as Monza applies.

**Traction-limited exits.** **Panasonic (T16) exit onto the main straight is the highest-value exit at this circuit and one of the highest in GT7** — a tenth there is worth several tenths by the T1 board, plus your slipstream position. **Hairpin exit** is second. **LSD acceleration sensitivity: medium-high, 25–32 ⚠️ *[v1.70 5–60 scale: a direction, not a number - see the banner]*.** Panasonic is a slow, tightening exit onto the longest straight; it wants lock.

**Gearing.** **Gear explicitly for slipstream** — Fuji is second only to Monza in tow dependency. 6th should top out **with a tow** at the T1 board. In clean air you should be short of the limiter. Additionally: **2nd gear must cover Panasonic** with the right exit ratio (this is the most important individual ratio at Fuji), and **4th must carry the 100R and 300R** without shifts.

**Tyre wear.** **Moderate, left-side biased.** Fuji is a predominantly right-handed circuit (Dunlop, 100R, 300R, Panasonic) so the **front-left is the limiter**, with the rear taking traction wear from Panasonic and the hairpin. The long straight gives the tyres a genuine cooling and recovery period each lap, which post-1.49 measurably extends stint life. Expect **18–22 laps at 1x** — relatively kind.

**Pit loss.** Estimated **21–23 s**. *(Confidence: medium.)*

**Strategy quirks.** The main straight makes Fuji a **track-position-cheap** circuit — defending is hard, so aggressive strategy pays ⚠️ *[re-flagged 11 Sep: unmeasured - see the banner]*. The tyre recovery on the straight means fresh-tyre out-laps are unusually strong here, making the **undercut powerful** ⚠️ *[re-flagged 11 Sep: the undercut is weak in GT7 - see the banner; "fresh-tyre out-laps are unusually strong" is unmeasured]*. Fuji is one of the best circuits in GT7 for multi-stop league racing. The **Short Course** removes the middle-sector chicane complex, raising average speed and lowering the downforce requirement further.

**Top three levers.**
1. **2nd gear ratio and LSD acceleration for the Panasonic exit.**
2. **Low-drag aero with with-tow gearing.**
3. **Brake bias / cold-tyre management into T1.**

---

## 1.13 Tsukuba Circuit
**2.0 km · 8 corners · Gr.3 ≈ 0:53–0:55**

**Layout character.** A tiny Japanese club circuit: a short straight, a first-gear hairpin, a technical infield, and a long final loop. Gr.3 cars are absurdly oversized for it, which is precisely why it is entertaining.

**Downforce: irrelevant in the usual sense — set it for BALANCE, not level.** Corner speeds are too low for aero to contribute meaningfully anywhere except the final loop. Many drivers run high wing anyway because the drag cost on a 400 m straight is negligible. **Recommendation: run high downforce and use the front/rear split purely as a balance tool.** There is no strategic reason to trim.

**Dominant corner types & grip priority.** **Slow hairpins and 2nd/3rd-gear corners.** **Priority: mechanical grip, absolutely and exclusively.** Tsukuba is the purest mechanical-grip test in GT7. Springs, ARBs, camber, LSD and tyre temperature are the entire setup.

**Kerbs & elevation.** Elevation is **effectively zero**. Kerbs are **low and usable**, but the surface at the first hairpin exit is where you will find the limit. Implications: **run low ride height and relatively soft springs** — you want maximum mechanical compliance and contact-patch consistency at low speed. There is no aero platform to protect. Soft ARBs relative to your other setups.

**Braking zones.** **One heavy (the first hairpin), two medium.** All flat, all smooth. **Brake bias: neutral to slightly rearward.** Low-speed hairpin entries benefit from rotation, and there is no downhill or bumpy braking to punish it. This is one of the few circuits where a rearward bias is straightforwardly correct.

**Traction-limited exits.** **The first hairpin exit and the final hairpin exit** — both 1st/2nd gear from near-stopped in a 550+ hp car. **LSD acceleration sensitivity: LOW, 12–18 ⚠️ *[v1.70 5–60 scale: a direction, not a number - see the banner]*.** Counter-intuitive, but a Gr.3 car has so much more torque than the corner can absorb that high acceleration lock simply produces wheelspin and snap. Low lock plus disciplined throttle is faster.

**Gearing.** Extremely short. **You will use 3rd and 4th and no more.** Set the final drive well to the short end. Make sure **1st is not so short that you are shifting immediately out of the hairpins** — a common error that costs real time on a 54-second lap.

**Tyre wear.** **Low in absolute terms, high per lap in percentage terms** because of the short lap. Rear-biased from the two hairpin exits. Roughly **20–25 laps at 1x**, but check this at your multiplier — the per-lap number moves fast.

**Pit loss.** Estimated **17–19 s** — which is **over 30% of a lap time.**

**Strategy quirks.** That ratio dominates everything. **A mandatory stop at Tsukuba is a massive strategic event** and the pit window is very tight. Lapped traffic appears within about eight laps of a full-grid race and never goes away. Overtaking is possible only at the first hairpin and requires a significant pace advantage. **Recommendation for your league: use Tsukuba for short no-stop sprints or reverse-grid chaos races, not for serious multi-stop formats** — the pit-loss ratio distorts the racing more than it enriches it.

**Top three levers.**
1. **Mechanical grip package** — springs, ARBs, camber.
2. **LSD acceleration sensitivity (low)** for the hairpin exits.
3. **Short gearing with correct 1st/2nd placement.**

---

## 1.14 Watkins Glen International
**Long Course 5.4 km · 11 corners · Gr.3 ≈ 1:44–1:47 · Short Course 3.9 km, 7 corners**

**Layout character.** A very fast, flowing American road course: a hard first-corner stop, a set of near-flat esses, a long back straight, and — on the Long Course — the "boot" section with the Inner Loop. Only 11 corners over 5.4 km tells you everything. Used for Online Time Trial #32.

**Downforce: MEDIUM-LOW to MEDIUM.** Full-throttle share ~70%. The esses reward aero, but there are two very long full-throttle sections. **Two to three clicks below midpoint** is the standard compromise. The esses will feel like a commitment test at that level; that is correct.

**Dominant corner types & grip priority.** **Fast sweepers.** The esses (T2–T4) are 5th-gear commitment corners; the Chute and the Toe of the Boot are fast; only T1 (the 90), the Bus Stop and the final turn are slow-to-medium. **Priority: aero platform and high-speed stability.** Mechanical grip investment is poorly rewarded — you use it three times a lap.

**Kerbs & elevation.** Elevation ~50 m: the esses climb noticeably and the back straight descends. Kerb severity: **high at the Bus Stop** (the chicane kerbs are severe and unavoidable) and moderate elsewhere. The esses have **compressions at the top of the climb** where the car goes light at high speed. Implications:
- **Medium-stiff springs** for the esses platform.
- **Rear compression damping soft enough for the Bus Stop kerb strike** — a launched Bus Stop exit is a common lap-ender.
- **Ride height not at minimum** — the compression at the top of the esses will bottom a very low car at 250 km/h, which post-1.49 is genuinely destabilising.

**Braking zones.** **Three heavy.** **Turn 1 (the 90)** from top speed, flat, wide — a good overtaking spot. **The Bus Stop** from very high speed, slightly downhill, with severe kerbs — the hardest stop on the lap. **The Inner Loop / Toe of the Boot** on the Long Course. **Brake bias: one to two clicks forward** for the Bus Stop's downhill approach.

**Traction-limited exits.** **Bus Stop exit** (feeds the run to the final corner), **T1 exit** (feeds the esses), and **the final turn onto the pit straight.** **LSD acceleration sensitivity: medium, 22–28 ⚠️ *[v1.70 5–60 scale: a direction, not a number - see the banner]*.** All three exits feed long full-throttle sections, which argues for lock; the Bus Stop kerb argues against. Split the difference.

**Gearing.** **Gear for slipstream** on the back straight — 6th tops out with a tow at the Bus Stop board. **5th must carry the esses** without a shift; if you find yourself shifting in the middle of the esses, your ratios are wrong and you will lose the car. This is the most important gearing note at the Glen.

**Tyre wear.** **Moderate-high, left-side biased.** The Glen is predominantly right-handed at speed (the esses, the Chute, the final loop), so the **front-left is the limiter.** Sustained high-speed lateral load generates significant heat post-1.49. Expect **15–18 laps at 1x.**

**Pit loss.** Estimated **20–22 s**. *(Confidence: medium.)*

**Strategy quirks.** Big slipstream on the back straight and a wide T1 make overtaking realistic — track position is moderately cheap. The **Short Course** removes the boot, cutting a heavy braking zone and the Inner Loop, making it faster-average, lower-downforce and lower-wear. The Short Course is a decent sprint layout; the Long Course is the league standard.

**Top three levers.**
1. **Aero level set in the esses** — commitment there is the lap.
2. **5th gear placement** to cover the esses without shifting.
3. **Rear compression damping** for the Bus Stop kerbs.

---

## 1.15 Daytona International Speedway — Road Course
**5.7 km · 12 corners · Gr.3 ≈ 1:44–1:47**

**Layout character.** Two-thirds of the tri-oval banking plus a technical infield, joined by the Bus Stop chicane. A hybrid that demands two contradictory setups. Used for Online Time Trial #125 (Jan 2025).

**Downforce: LOW.** Full-throttle share ~72%. You spend a huge proportion of the lap on the banking at full throttle where drag is the only thing that matters, and the banking itself supplies enormous mechanical load without any need for wing. **Run low — three to five clicks below midpoint.** The infield will feel under-tyred; that is the correct trade.

**Dominant corner types & grip priority.** Two families. **The banking** (T1–2 and T3–4 of the oval) is flat-out and needs only ride-height survival. **The infield** is 2nd/3rd-gear technical. **The Bus Stop** is a slow chicane. **Priority: mechanical grip for the infield, but the setup is actually dominated by ride-height compliance on the banking.**

**Kerbs & elevation.** Elevation is nominally small but the **banking is 31 degrees**, which produces very large vertical loads and compresses the suspension hard at the transition on and off the banking. Kerb severity: **very high at the Bus Stop.** Implications, and this is the defining Daytona setup problem:
- **Ride height must be raised enough that the car does not bottom on the banking at full speed.** A car that bottoms at the banking transition will snap, and at Daytona speeds that is a wall.
- **Stiff enough springs to resist the banking compression, soft enough dampers to absorb the Bus Stop kerbs.** Resolve this with springs stiff and compression damping moderate rather than the reverse.
- Check the banking exit transition specifically — that is where the car unloads.

**Braking zones.** **Two heavy, three medium.** **The Bus Stop** from full banking speed is the biggest stop and the main overtaking spot — flat but with severe kerbs. **The infield entry (T1 of the road course, the "horseshoe")** is heavy. The rest are medium 2nd/3rd-gear stops. **Brake bias: one click forward.** The Bus Stop entry is flat and stable.

**Traction-limited exits.** **Bus Stop exit onto the banking** (feeds the longest full-throttle section) and the **infield hairpin exits.** **LSD acceleration sensitivity: medium, 22–28 ⚠️ *[v1.70 5–60 scale: a direction, not a number - see the banner]*.** The Bus Stop exit onto the banking is high-value and wants lock; the kerbs argue for restraint.

**Gearing.** **Gear for maximum top speed with slipstream — Daytona has the biggest tow effect of any road layout in GT7.** 6th should top out with a tow on the banking. In clean air you will be well short; accept it, because you will always have a tow in a race. **2nd gear covers the infield hairpins.**

**Tyre wear.** **High, and violently right-side biased.** The banking is a sustained left-hand load at maximum speed — the **right-front and right-rear take enormous, continuous load**. This is the most asymmetric tyre wear in GT7 outside Special Stage Route X and the ovals. The right-front is the stint limiter. Expect **12–15 laps at 1x**, and note that the wear is nearly all on two corners of the car. Asymmetric setup (if your league permits it) genuinely pays here: more right-side camber, less left.

**Pit loss.** **Long — estimated 28–30 s.** Community consensus names Daytona among GT7's long pit lanes ([GTPlanet](https://www.gtplanet.net/forum/threads/pit-lane.426905/)); the pit lane runs the length of the tri-oval. *(Confidence: medium-high on "long".)*

**Strategy quirks.** Long pit loss plus enormous slipstream equals **the overcut is strong and pack racing dominates.** Cars will not break away. Expect a race decided in the final stint. Right-side tyre life is the strategic constraint, not fuel. Excellent endurance-format circuit.

**Top three levers.**
1. **Ride height for banking survival.**
2. **Low-drag aero with with-tow gearing.**
3. **Right-side tyre management** (camber, and driving line on the banking).

---

## 1.16 Daytona International Speedway — Tri-Oval
**4.0 km · 4 corners · Gr.3 ≈ 0:47–0:50 (heavily tow-dependent)**

**Layout character.** The full 2.5-mile banked oval. Flat out.

**Downforce: MINIMUM.** Drag is the entire game. Set both ends to minimum and only add rear if the car is unstable on the banking transitions.

**Dominant corner types & grip priority.** Banked full-throttle turns. **Priority: neither mechanical grip nor aero — ride height and drag.**

**Kerbs & elevation.** No kerbs in play. The 31-degree banking is the only vertical event. **Raise ride height enough to avoid bottoming; stiffen springs to resist the banking compression.** This is the one GT7 layout where a stiff, relatively high car is correct.

**Braking zones.** **None** in normal running. Brake bias irrelevant except for incident recovery.

**Traction-limited exits.** **None.** LSD settings are near-irrelevant; use a low, neutral configuration.

**Gearing.** **Maximum top speed with tow.** Set 6th to top out only in the draft. Nothing else matters.

**Tyre wear.** **Extreme right-side, minimal left-side.** Sustained maximum-speed left-hand load for the entire lap. Right-front is the limiter. **Asymmetric setup is genuinely valuable here if permitted.**

**Pit loss.** Estimated **28–30 s** — roughly **60% of a lap time**, the most extreme ratio anywhere.

**Strategy quirks.** This is a drafting game, not a driving game. Position at the final lap is nearly the only thing that matters, and slipstream physics mean the leader on the last lap is usually not the winner. Use it as a novelty or a deliberate lottery race. Pack management and blocking are the skills.

**Top three levers.** **Drag, gearing, right-side tyre life.** Nothing else moves the needle.

---
## 1.17 WeatherTech Raceway Laguna Seca
**3.6 km · 11 corners · Gr.3 ≈ 1:22–1:24**

*(Your list included this twice, as "Laguna Seca" and "Weathertech Raceway" — it is one venue.)*

**Layout character.** A short, brutally undulating Californian circuit with ~55 m of elevation change concentrated into 3.6 km, and the most famous corner sequence in North American racing.

**Downforce: MEDIUM-HIGH.** Full-throttle share ~50%. There is no straight of consequence and the fast corners (T1, T6 entry, T9) all reward load. **Run high** — drag cost is minimal.

**Dominant corner types & grip priority.** Mixed with heavy slow-corner weighting. **T2 (Andretti hairpin)** is a slow, off-camber-feeling left. **T5** is a medium uphill left. **T6** is a fast uphill right. **T8–8a (the Corkscrew)** is a blind crest followed by a steep left-right plunge. **T9 (Rainey Curve)** is a long, downhill, loaded left. **T11** is a slow left onto the pit straight. **Priority: split, leaning mechanical grip and pitch control.** The Corkscrew and T11 dictate the setup more than the fast corners.

**Kerbs & elevation.** Elevation is the defining feature — the climb from T5 to T8 and the plunge through the Corkscrew to T10 are both severe. Kerb severity: **high at T6 and T11** (severe exit kerbs, also the track-limits points), moderate elsewhere. Implications:
- **The Corkscrew landing is the setup constraint.** You crest T8 with the car light, then land on a steep descent. Too stiff and the car skips and will not turn at 8a; too soft and you bottom on the landing.
- **Front expansion damping firm** so the front extends over the crest and finds the road at 8a.
- **Rear compression damping moderate-soft** for the landing.
- **Ride height 2–3 clicks up** from a flat-circuit setting.
- **Do not run your stiffest springs here** despite the medium-high downforce — this is an elevation track first.

**Braking zones.** **Three heavy, two medium.** **T2 (Andretti)** — heavy, downhill-ish approach, the main overtaking spot. **T5** — uphill, medium-heavy, stable. **T11** — heavy, downhill, and you are turning in — the hardest stop and the one that decides your lap. **T9** is a medium, downhill, committed entry. **Brake bias: two clicks forward.** T11's downhill entry and the general descending character of the second half require it.

**Traction-limited exits.** **T11 exit onto the pit straight is the single most valuable exit** (it feeds the only real straight and the only overtaking approach). **T2 exit** is second. **T6 exit** (uphill) is third. **LSD acceleration sensitivity: medium, 20–28 ⚠️ *[v1.70 5–60 scale: a direction, not a number - see the banner]*.** T11 is slow, downhill-into-flat and feeds a straight — it wants lock — but the Corkscrew and T10 need the car to rotate freely.

**Gearing.** **Short — you will use 5th at most, and 6th possibly not at all.** Gear for exits: **2nd for T2 and T11**, **3rd for T5 and T10**, **4th for T6 and T9.** The main straight is short enough that final-drive optimisation is worth less than getting 2nd right for T11.

**Tyre wear.** **Moderate-high for the lap length, right-side biased** — Laguna Seca is predominantly left-handed (T2, T5, T8, T9, T11), so the **front-right is the limiter.** The elevation adds vertical load cycling that raises wear beyond what the corner speeds suggest. Expect **14–17 laps at 1x.**

**Pit loss.** Estimated **18–20 s** — **~23% of a lap time**, a high ratio.

**Strategy quirks.** Overtaking is realistically T2 only, plus an occasional Corkscrew move that ends in tears. **Track position is expensive**, qualifying matters, and the undercut is strong ⚠️ *[re-flagged 11 Sep: the undercut is weak in GT7 - see the banner]*. Laguna Seca races are usually decided in the first two corners. The high pit-loss ratio argues for one-stop or no-stop formats.

**Top three levers.**
1. **Corkscrew compliance** — front expansion damping and ride height.
2. **Brake bias forward and 2nd gear for T11.**
3. **Front-right tyre preservation.**

---

## 1.18 Mount Panorama Circuit (Bathurst)
**6.2 km · 23 corners · Gr.3 ≈ 2:00–2:03**

**Layout character.** Two circuits joined: a flat, fast, low-drag pit straight and Conrod Straight, and a 1st-to-3rd-gear mountain climb and descent lined entirely with concrete. 174 m of elevation change. The most punishing circuit in GT7 for error. Used for Online Time Trial #69 and regularly in daily rotation.

**Downforce: MEDIUM.** Full-throttle share ~55% but concentrated into two very long straights, one of which (Conrod) is nearly 2 km. The mountain section is slow enough that aero contributes little. **The correct answer is genuinely a compromise at the midpoint or slightly below** — you cannot win both ends and the straights are where you overtake. If your league runs long stints, bias slightly higher for the mountain's tyre-life benefit.

**Dominant corner types & grip priority.** **The mountain is 1st–3rd-gear work over crowned, off-camber, wall-lined road.** Griffins Bend, The Cutting, Reid Park, McPhillamy, Skyline, The Esses, The Dipper, Forrest's Elbow. Only The Chase and the Conrod kink are fast. **Priority: mechanical grip and vertical compliance, decisively.** A stiff, aero-focused Bathurst car is undriveable over the mountain.

**Kerbs & elevation.** Elevation is the largest of any conventional circuit in GT7. Kerb severity: **moderate to high**, but the real hazards are the **road crown and camber changes** — the mountain road is genuinely crowned like a public road and the car goes light and heavy repeatedly. Implications:
- **Softer springs than your aero instinct wants.** This is the key insight at Bathurst.
- **Ride height up 3–5 clicks** — the compression at Forrest's Elbow and the crest at Skyline will both catch a low car.
- **Compression damping soft, expansion damping firm** — you need the car to absorb the compressions and settle quickly between the walls.
- Avoid aggressive rake; pitch sensitivity over Skyline is dangerous.

**Braking zones.** **Three heavy, four medium.** **The Chase (T21–22)** is the biggest: from ~290 km/h at the end of Conrod, **downhill, and slightly bumpy** — the most demanding stop in GT7. **The Cutting (T4)** is heavy and steeply uphill (which helps). **Murray's Corner (T23)** is heavy at the bottom of the descent. **Hell Corner (T1)** and the mountain corners are medium. **Brake bias: two to three clicks forward.** The Chase mandates it — a rearward bias into a downhill, bumpy 290 km/h stop is a wall. If your league permits in-race adjustment, running more forward for the descent and Chase is worthwhile.

**Traction-limited exits.** **Forrest's Elbow (T19) exit onto Conrod Straight is the highest-value corner exit on any GT7 circuit** — it feeds nearly 2 km of full throttle. **Murray's Corner exit** onto the pit straight is second. **The Cutting exit** (steeply uphill) is third. **LSD acceleration sensitivity: medium, 20–28 ⚠️ *[v1.70 5–60 scale: a direction, not a number - see the banner]*.** Forrest's Elbow wants lock; the Esses and Dipper want the car free. If you must err, err toward Forrest's Elbow — but note it is a downhill exit, which reduces the traction demand.

**Gearing.** **Gear for Conrod with slipstream** — 6th tops out with a tow before The Chase braking. Critically: **1st and 2nd must cover the mountain section** with the right spacing, because the mountain corners are so slow that a badly placed 2nd gear costs you at six corners per lap. **3rd should carry Skyline and the Esses.** Bathurst gearing is a genuinely two-part problem and deserves proper time.

**Tyre wear.** **High, and front-biased with a left-side lean.** Bathurst's mountain section is a mix, but the sustained loads (the Conrod kink, The Chase, Reid Park) and the crowned road working the outside tyres put the **front-left under most stress.** Rear wear from the uphill traction exits is also significant. Expect **13–16 laps at 1x.**

**Pit loss.** **Long — estimated 28–30 s.** Named in community discussion among GT7's long pit lanes ([GTPlanet](https://www.gtplanet.net/forum/threads/pit-lane.426905/)). *(Confidence: medium-high on "long".)*

**Strategy quirks.** Long pit loss plus a 2:00 lap makes stops expensive (~25% of a lap). Overtaking is realistically **only at The Chase and Murray's** — the mountain is one car wide and passing there is an incident, not a move. Consequently **track position is very expensive**, qualifying is decisive, and the overcut is strong. Safety-car-free league racing at Bathurst is attritional: the walls will decide the race more than strategy will. Excellent endurance circuit; brutal sprint circuit.

**Top three levers.**
1. **Compliance package for the mountain** — softer springs, raised ride height, soft compression damping.
2. **Brake bias forward for The Chase.**
3. **1st/2nd gear spacing for the mountain section** plus 6th for Conrod.

---

## 1.19 Circuit de Barcelona-Catalunya
**GP 4.7 km · 16 corners · Gr.3 ≈ 1:41–1:44 · No Chicane 4.7 km · 14 corners · ≈ 1:39–1:42 · National 3.0 km · 11 corners**

**Layout character.** The reference test circuit of European motorsport, and it behaves that way: every corner type in one lap, a long main straight, and — critically — two extremely long-radius right-handers that destroy front-left tyres. Used for Online Time Trials #19 and #46.

**Downforce: HIGH.** Full-throttle share ~55%. T3 (a very long, loaded right), T9 (Campsa, blind over a crest), and T12 (a long left) are all sustained-load corners where every click of wing pays. The main straight is long but not long enough to justify trimming. **Run high.**

**Dominant corner types & grip priority.** **Long-radius medium-fast corners** are the signature. T3 in particular is one of the longest-duration corners in GT7. There are only two genuinely slow corners (T5 and T10). **Priority: aero platform, decisively** — Barcelona is where a well-set-up aero car gains the most relative to a mechanical-grip car.

**Kerbs & elevation.** Elevation is moderate (~30 m) with a rise to T3 and a descent from T9. Kerb severity: **high at the T14–15 chicane** (severe, and the exit kerb is a launcher), moderate elsewhere. **T9 (Campsa) is a blind crest taken at high speed** where the car goes light. Implications:
- **Stiff springs, low ride height** — Barcelona is smooth and the aero platform is worth protecting. This is one of your stiffer setups.
- **Except:** enough rear compliance for the chicane kerbs and enough front expansion damping for the Campsa crest.
- The **No Chicane** variant removes the chicane problem entirely and lets you run a stiffer, lower car — and it is the better league layout for that reason plus better racing.

**Braking zones.** **Three heavy, two medium.** **T1** from top speed, flat, wide — the main overtaking spot. **T10 (La Caixa)** heavy, on a descent. **T14 (the chicane)** heavy. **T4 (Repsol)** and **T7** are medium. **Brake bias: one to two clicks forward.** T10's downhill approach sets the requirement.

**Traction-limited exits.** **T16 (the final corner) exit onto the main straight is the most valuable** — and it is a long, loaded, gradually opening right, so it is a *balance* problem more than a pure traction problem. **T10 exit** and **T5 exit** are the true traction events. **LSD acceleration sensitivity: medium, 20–28 ⚠️ *[v1.70 5–60 scale: a direction, not a number - see the banner]*.** The long-radius exits (T3, T9, T12, T16) all suffer from too much lock — it pushes you wide and, crucially, **scrubs the front-left**, which is the thing you cannot afford here.

**Gearing.** **Gear for slipstream on the main straight** — 6th tops out with a tow at the T1 board. **4th must carry T3** without a mid-corner shift (T3 is long enough that a shift there is genuinely disruptive), and **5th must carry T9** over the crest.

**Tyre wear.** **The highest front-left wear of any circuit in GT7, and the stint limiter at this track by a wide margin.** T3 alone is a multi-second sustained right-hand load; add T9, T12 and T16 and the front-left has no recovery. Expect **11–14 laps at 1x** before the front-left costs you meaningful time — shorter than almost anything else on this list. This is the defining strategic fact about Barcelona.

**Pit loss.** Estimated **20–22 s**. *(Confidence: medium.)*

**Strategy quirks.** **Front-left life dictates the entire race.** Practical countermeasures worth testing in your league: a softer front ARB (less load transfer onto the front-left), slightly less front camber than baseline (reduces shoulder wear at the cost of some peak grip), one click of rearward brake bias (frees the front axle), and a lower LSD acceleration setting (less scrub on the long exits). Also: overtaking is realistically T1 and T10 only, and **dirty air is punishing** because the circuit is so aero-dependent — a car following closely through T3 and T9 loses real time and burns its front-left faster. That combination (hard to pass, punished for following) makes Barcelona a strong strategy circuit and a poor pure-pace circuit.

**Top three levers.**
1. **Front-left tyre preservation package** — front ARB, camber, brake bias, LSD acceleration.
2. **Aero level and balance** — set it in T3.
3. **4th/5th gear placement for T3 and Campsa.**

---

## 1.20 Circuit de la Sarthe (Le Mans)
**13.6 km · 38 corners (Full) / 32 corners (No Chicane) · Gr.3 ≈ 3:28–3:34 (Full), 3:20–3:25 (No Chicane) · longest straight 5,700 m**

**Layout character.** Public roads and a permanent circuit joined into a 13.6 km lap with a 5.7 km continuous full-throttle section (the Mulsanne, broken by two chicanes), a fast and technical Porsche Curves section, and a set of slow corners in between ([gtplus.app track data](https://gtplus.app/gt7/tracks/circuit-de-la-sarthe)).

**Downforce: LOW.** Full-throttle share is around 75%, matching or exceeding Monza. **Run near minimum rear wing** with enough front to keep the car turning at the Porsche Curves. The exception: the **No Chicane** variant is even more drag-critical, so trim further there. Note that low downforce at the Porsche Curves is genuinely uncomfortable — that is the price.

**Dominant corner types & grip priority.** Three families. **Slow 90-degree corners** (Mulsanne Corner, Arnage, Tertre Rouge) — mechanical grip. **Chicanes** (two Mulsanne chicanes, the Ford chicanes) — kerb compliance. **Fast sweepers** (the Porsche Curves, Indianapolis entry) — aero platform. **Priority: low drag first, then kerb compliance, then everything else.** Le Mans is the one circuit where the setup is dictated almost entirely by the straights.

**Kerbs & elevation.** Elevation is small (~55 m over 13.6 km, average grade 0.27%) and gently undulating — the Mulsanne has noticeable crests where the car goes light at maximum speed. Kerb severity: **very high at the Ford chicanes** (launchers) and **high at the Mulsanne chicanes.** Implications:
- **Ride height not at minimum** — the Mulsanne crests at 280+ km/h will bottom a very low car and that is a huge accident.
- **Soft compression damping** for the four chicanes.
- **Medium springs.** You have little aero platform to protect, so spend the compliance on kerbs.

**Braking zones.** **Five heavy, plus two chicane stops.** **Mulsanne Corner (the 90-degree right at the end of the straight)** is the single largest deceleration event in GT7 — flat, smooth, wide, and the classic overtaking spot. **The two Mulsanne chicanes** are heavy stops from maximum speed with severe kerbs. **Indianapolis** is a fast right into a slow left, slightly **off-camber on the entry** — genuinely tricky. **Arnage** is a slow 90 with a poor approach. **The Ford chicanes** at the end of the lap. **Brake bias: one to two clicks forward.** Indianapolis' off-camber entry and the cold-brake situation at the first Mulsanne chicane both argue for it.

**Traction-limited exits.** **Mulsanne Corner exit** (feeds the run to Indianapolis), **Arnage exit** (feeds the Porsche Curves), **Ford chicane exit** (feeds the pit straight), and the **two Mulsanne chicane exits** (each feeds a ~1.8 km full-throttle section — extremely high value). **LSD acceleration sensitivity: medium-high, 25–32 ⚠️ *[v1.70 5–60 scale: a direction, not a number - see the banner]*.** Nearly every traction exit at Le Mans feeds a long straight, which is the strongest possible case for lock. Temper it slightly for the chicane kerbs.

**Gearing.** **Gear for absolute maximum top speed, with tow.** Le Mans is the most gearing-sensitive circuit in the game. 6th should top out with a slipstream at the end of the Mulsanne. **The critical secondary constraint: 4th and 5th must be placed to carry the Porsche Curves without a mid-corner shift**, and **2nd must cover Mulsanne Corner and Arnage.** Spend real time here — a badly geared Le Mans car loses multiple seconds per lap.

**Tyre wear.** **Moderate per lap in absolute terms, but each lap is 3:30 — so wear per unit of time is low.** The Porsche Curves generate most of the front-tyre wear (predominantly rights, so front-left), and the slow-corner exits generate rear wear. The long straights allow substantial cooling and recovery, which post-1.49 is a real effect. **Fuel, not tyres, is usually the stint limiter at Le Mans** — check this at your league's fuel multiplier, because it inverts the normal strategic logic.

**Pit loss.** **~32 s** — the best-sourced number in this document, derived from a 550 m pit lane at the 60 km/h limit, with GTPlanet moderator confirmation that Le Mans pit times are modelled on reality ([GTPlanet](https://www.gtplanet.net/forum/threads/pit-lane.426905/)). *(Confidence: high.)*

**Strategy quirks.** Because 32 s is only **~15% of a 3:30 lap**, the undercut is weak and the overcut is weak — pit timing barely matters compared to **fuel-saving and avoiding incidents.** This makes Le Mans a genuinely different strategic problem from every other circuit here: your league should focus on fuel maps, lift-and-coast into Mulsanne Corner and the chicanes, and driver stint discipline. Traffic over 13.6 km is manageable. Weather is a live factor and can be sector-local. **The best endurance venue in GT7.**

**Top three levers.**
1. **Gearing** — top speed with tow, plus Porsche Curves ratio placement.
2. **Minimum-drag aero.**
3. **Fuel strategy and lift-and-coast discipline** (a setup-adjacent lever: gearing affects fuel burn materially here).

---
## 1.21 Willow Springs — Big Willow
**4.0 km · 10 corners · Gr.3 ≈ 1:20–1:23** *(Streets 2.7 km / 14 corners; Horse Thief Mile 1.6 km / 11 corners)*

**Layout character.** "The fastest road in the West" — a 1950s desert circuit that is essentially one continuous sequence of fast, banked, sun-baked sweepers with almost no braking. Used for Online Time Trial #58.

**Downforce: MEDIUM-HIGH.** Full-throttle share is nominally high but almost all of it is *through* corners rather than in a straight line. There is one short straight. **Run high** — the drag cost is nearly free and every corner rewards load.

**Dominant corner types & grip priority.** **Fast sweepers, almost exclusively.** T2 is a fast banked right, T3–4 are fast, T8 (the "Sweeper") is a very long banked right, T9 is a fast downhill left. Only T1 and T4/5 involve meaningful braking. **Priority: aero platform and sustained-load stability.** Mechanical grip barely enters the picture.

**Kerbs & elevation.** Elevation change is significant (~40 m) with a climb to T3 and a descent through T8–9. Kerbs are **old-school and mostly irrelevant** — you do not use them. The critical feature is that **the surface is bumpy and abrasive.** Implications:
- **The stiff/soft conflict is acute:** you want a stiff platform for the sustained aero load, but the bumps mid-corner at 200 km/h will unsettle a stiff car catastrophically.
- **Resolve with medium springs and notably soft compression damping** (drop 4–5 clicks) rather than with springs alone.
- **Ride height 2–3 clicks up.**
- The T8 Sweeper is where you find out if you got it right — a bumpy, banked, minute-long right-hander.

**Braking zones.** **One heavy (T1), one medium (T4/5), one light (T9).** That is it — the fewest genuine braking events of any road circuit here. **Brake bias: neutral to one click forward.** With so little braking, this is a low-priority setting; set it for T1 and forget it.

**Traction-limited exits.** **Very few.** T4/5 exit and T9 exit onto the pit straight. Most exits are fast and loaded. **LSD acceleration sensitivity: low-to-medium, 15–22 ⚠️ *[v1.70 5–60 scale: a direction, not a number - see the banner]*.** Too much lock will push you wide at every sweeper exit and shred the front-left. ⚠️ *[The "a locked diff pushes you wide" half is CONTESTED on v1.71 — the one in-house test of lowering accel for a power-on push was refuted (Huracán, Daytona, s145); see `02` §10.5. The wear half is untouched by it.]*

**Gearing.** **Gear for the sweepers, not for top speed.** 5th and 6th should be placed so that **T2, T3 and T8 are each taken in a single gear at a comfortable rpm** — this is more important than the final drive because you spend most of the lap at part-throttle through fast corners. A car that needs to shift mid-Sweeper is a slow car.

**Tyre wear.** **Severe — among the highest in GT7 relative to lap distance.** Continuous, sustained, high-load lateral cornering on an abrasive surface with no straight to cool the tyres. **Predominantly right-hand corners, so the front-left is destroyed.** Expect **10–14 laps at 1x** before the front-left is significantly off. Post-1.49 thermal modelling makes this worse — the tyres never get a cooling period.

**Pit loss.** Estimated **17–19 s**. *(Confidence: low — limited data.)*

**Strategy quirks.** The combination of **short lap, high wear and short pit loss** makes Big Willow a genuinely strategic circuit despite its simplicity — multi-stop races here reward tyre management heavily. Overtaking is difficult (one real braking zone) so track position is expensive, which pulls against the tyre-life logic. Good league circuit for that tension. **Willow Springs Streets** and **Horse Thief Mile** are tight, technical, mechanical-grip layouts that are the opposite of Big Willow in every respect — treat them as separate circuits, and note they are rarely used for Gr.3.

**Top three levers.**
1. **Front-left tyre preservation** — the whole race.
2. **Compression damping** for the bumpy sweepers.
3. **5th/6th gear placement** to avoid mid-sweeper shifts.

---

## 1.22 Michelin Raceway Road Atlanta
**4.1 km · 12 corners · Gr.3 ≈ 1:20–1:23**

*(Your list included this twice, as "Road Atlanta" and "Michelin Raceway" — one venue.)*

**Layout character.** A fast, hilly Georgian road course with blind crests, a genuinely great esses section, and one of the best corner sequences in North America at T10a/b. Short lap, high average speed.

**Downforce: MEDIUM.** Full-throttle share ~63%. Two long straights argue for trimming; the esses and T1 argue for load. **At or just below midpoint.**

**Dominant corner types & grip priority.** **Fast and medium sweepers with two slow corners.** T1 is a fast downhill right; T3–5 are the esses (blind, over crests, aero-critical); T7 is a slow left; T10a/b is a blind crest into a downhill left-right onto the back straight; T12 is a medium right onto the pit straight. **Priority: aero platform and pitch control.**

**Kerbs & elevation.** Elevation is large (~30 m but sharply profiled) with several **blind crests where the car goes light at speed** — T1, the esses, and above all **T10a, which is a genuine blind crest at the braking point.** Kerb severity: **high at T7 and the chicane**, moderate elsewhere. Implications:
- **Front expansion damping firm** so the front finds the road quickly over the esses crests and at T10a.
- **Medium-stiff springs**, ride height 2–3 clicks up.
- The T10a braking-on-a-crest event is the setup-defining moment.

**Braking zones.** **Three heavy, two medium.** **T5/6** at the bottom of the esses descent — heavy and slightly downhill. **T7** heavy. **T10a** — heavy, **on a blind crest, with the car unloaded** — the hardest and most consequential stop on the lap. **T12** medium. **Brake bias: two clicks forward.** T10a mandates it: braking with an unloaded rear over a crest with a rearward bias is a spin every time.

**Traction-limited exits.** **T7 exit** (feeds the run to T10) and **T12 exit** onto the long pit straight — the highest-value exit. **T10b exit** onto the back straight is third but is fast and loaded, so less traction-critical. **LSD acceleration sensitivity: medium, 22–28 ⚠️ *[v1.70 5–60 scale: a direction, not a number - see the banner]*.**

**Gearing.** Both straights are long. **Gear for the pit straight with tow** (6th topping out at the T1 braking area). **4th must carry the esses** without a shift and **5th must cover T10b** onto the back straight.

**Tyre wear.** **Moderate-high, front-biased.** Road Atlanta is reasonably direction-balanced so side bias is mild, with a slight front-left lean. The crests and compressions add vertical load cycling. Expect **14–17 laps at 1x.**

**Pit loss.** Estimated **19–21 s**. *(Confidence: low-medium.)*

**Strategy quirks.** Overtaking is realistic at T1, T7 and T10a, which for a short lap is generous — track position is relatively cheap and the racing is good. Short pit loss makes the undercut work ⚠️ *[re-flagged 11 Sep: the undercut is weak in GT7 - see the banner]*. **An underrated league circuit** that produces better racing than its profile suggests.

**Top three levers.**
1. **Brake bias forward and front expansion damping** for the T10a crest.
2. **4th gear placement for the esses.**
3. **Aero level** — set it in the esses.

---

## 1.23 Goodwood Motor Circuit
**3.8 km · 7 corners · Gr.3 ≈ 1:16–1:19**
*(Confidence note: GT7 community data on Goodwood in Gr.3 is genuinely thin — it is rarely used in Sport Mode. The lap time is an estimate and the pit-loss figure is a guess. Treat this entry as more inferential than the others.)*

**Layout character.** A flat, fast, almost featureless 1948 airfield perimeter circuit: seven corners, most of them fast, with a slow chicane before the line. Old-school in the truest sense — narrow, grass-lined, and unforgiving.

**Downforce: MEDIUM-LOW.** Full-throttle share is high (~70%) and the corners, while fast, are not the long sustained-load type that make wing pay. **Two to three clicks below midpoint.**

**Dominant corner types & grip priority.** **Fast sweepers plus one slow chicane.** Madgwick (fast right), Fordwater (near-flat), St Mary's (fast, blind, over a crest and slightly off-camber), Lavant (medium right), Woodcote (fast right), then the chicane. **Priority: high-speed stability and aero platform**, except that the chicane is where lap time is actually lost.

**Kerbs & elevation.** Elevation is **minimal** — Goodwood is essentially flat, with a slight crest and dip at St Mary's. Kerb severity: **very high at the chicane** (the chicane kerbs are aggressive and the walls are close), negligible elsewhere. Implications:
- **You can run a low, medium-stiff car** — there is nothing to absorb.
- **Except: keep enough rear compliance for the chicane kerbs**, because that is the only place you will lose the car.
- Slight care at St Mary's where the car goes light.

**Braking zones.** **Two real ones: Lavant and the chicane.** Both flat and smooth. Madgwick and Woodcote are lift-or-brush. **Brake bias: neutral to one click forward.** Low-priority setting here.

**Traction-limited exits.** **The chicane exit onto the pit straight** — essentially the only one that matters. Every other exit is fast and loaded. **LSD acceleration sensitivity: medium, 20–26** ⚠️ *[v1.70 5–60 scale: a direction, not a number - see the banner]*, set entirely for the chicane exit. Keep initial torque low so the car turns at Madgwick and Woodcote.

**Gearing.** **Gear for top speed** — with only one slow corner, the final drive is the dominant choice. **2nd for the chicane**, and make sure **5th/6th carry Woodcote and Madgwick** without shifts.

**Tyre wear.** **High for such a simple circuit, and strongly left-side biased.** Goodwood is almost entirely right-handed (Madgwick, Fordwater, St Mary's, Woodcote) with sustained load and no cooling. **Front-left is the limiter.** Estimated **13–16 laps at 1x** — treat as provisional.

**Pit loss.** Estimated **17–19 s**. *(Confidence: low.)*

**Strategy quirks.** Overtaking is very hard — realistically only into the chicane, and the run-off is grass. The narrow track makes side-by-side racing genuinely risky. **Best used as a short-sprint or novelty circuit**, not as a serious multi-stop venue. If your league wants a "classic" round, this is the one, but expect processional racing.

**Top three levers.**
1. **Chicane exit package** — 2nd gear, LSD acceleration, rear compliance for the kerbs.
2. **Top-speed gearing.**
3. **Front-left preservation.**

---

## 1.24 Circuit Gilles-Villeneuve *(not on your list — worth adding)*
**4.4 km · 14 corners · Gr.3 ≈ 1:41–1:44**

**Layout character.** A flat, walled semi-permanent circuit built from chicanes and short straights. Included because it is a common Sport Mode and league venue and it fills a niche none of your listed tracks do: a low-downforce, chicane-heavy, wall-lined sprint circuit.

**Downforce: LOW to MEDIUM-LOW.** Full-throttle share ~70%. Three long straights, no fast corners of consequence. **Three to four clicks below midpoint.**

**Dominant corner types & grip priority.** **Chicanes and slow-to-medium corners, exclusively.** The hairpin (T10) is the slowest corner; the rest are chicanes and 90-degree turns. **Priority: mechanical grip and kerb compliance**, exactly like Monza.

**Kerbs & elevation.** Elevation is **zero** — the flattest circuit in GT7 after Monza. Kerb severity is **high**: the chicane kerbs must be used and are aggressive, and the walls are immediately behind them (the "Wall of Champions" at the final chicane is modelled). Implications: **soft compression damping, ride height not at minimum, medium springs.** A Monza-style compliance setup.

**Braking zones.** **Four heavy**, all flat and smooth: T1, the T3–4 chicane approach, the hairpin (T10), and the final chicane (T13–14). All are good overtaking spots. **Brake bias: one click forward.**

**Traction-limited exits.** **The hairpin exit onto the back straight** is by far the most valuable, and **the final chicane exit** onto the pit straight is second. **LSD acceleration sensitivity: medium-high, 25–32** ⚠️ *[v1.70 5–60 scale: a direction, not a number - see the banner]* for the hairpin — but watch the final chicane kerb.

**Gearing.** **Gear for slipstream on the back straight**; 6th tops out with a tow at the final chicane. **2nd must cover the hairpin.**

**Tyre wear.** **Moderate, rear-biased** (traction-driven, from the hairpin and chicane exits), with front lockup wear from four heavy stops. Right-side slightly favoured. **17–20 laps at 1x.** Brake and front-tyre lockup is a bigger practical issue than degradation.

**Pit loss.** Estimated **19–21 s**. *(Confidence: low-medium.)*

**Strategy quirks.** Huge slipstream, four passing zones, walls everywhere — **track position is cheap and attrition is high.** Great sprint venue.

**Top three levers.** **Kerb compliance; hairpin exit gearing/LSD; low-drag aero with tow gearing.**

---

## 1.25 Yas Marina Circuit *(not on your list — worth adding)*
**5.3 km · 16 corners · Gr.3 ≈ 1:52–1:56**

**Layout character.** A modern F1 circuit with two enormous back-to-back braking zones, a technical middle sector, and a fast final sequence. Included because leagues use it for night races and it is a genuinely good Gr.3 venue.

**Downforce: MEDIUM-HIGH.** Full-throttle share ~58%. Two long straights, but the final sector (T16 onward) and T2/T3 are aero corners. **At or slightly above midpoint.**

**Dominant corner types & grip priority.** Mixed with a slow-corner weighting — the T5–T8 hairpin complex and the T11–T14 section are 2nd/3rd gear. **Priority: split, leaning mechanical grip and traction** because of the number of slow exits.

**Kerbs & elevation.** Elevation is **minimal**. Kerb severity **moderate** — modern flat kerbs, usable. **Run low and medium-stiff**; Yas Marina is a forgiving suspension circuit.

**Braking zones.** **Three heavy, back-to-back at T5 and T8** (the two longest straights end in slow corners), plus **T11**. All flat, smooth and wide. **Brake bias: one click forward.** Brake temperature and front-tyre lockup are the real issues.

**Traction-limited exits.** **T7 exit** and **T9 exit** (both onto straights), plus **the final corner** onto the pit straight. **LSD acceleration sensitivity: medium-high, 25–32** ⚠️ *[v1.70 5–60 scale: a direction, not a number - see the banner]* — several slow exits feed straights.

**Gearing.** Gear for slipstream on the two long straights. **2nd for the hairpin complex.**

**Tyre wear.** **Moderate, rear-biased** from the slow exits, with heavy front-tyre thermal loading from the big stops. **16–19 laps at 1x.**

**Pit loss.** Estimated **21–23 s**. *(Confidence: low.)*

**Top three levers.** **LSD acceleration for the slow exits; 2nd gear placement; brake bias and front-tyre thermal management.**

---

# 2. ORIGINAL CIRCUITS

---

## 2.1 Dragon Trail — Seaside
**5.2 km · 18 corners · Gr.3 ≈ 1:50–1:53**

**Layout character.** A very long main straight along a Croatian coastline, a fast sweeping middle section, a tunnel, and a tight technical final sequence before the straight. One of the best-designed original circuits in GT7 and a league staple. Used for Online Time Trial #47.

**Downforce: MEDIUM-LOW.** Full-throttle share ~65%, dominated by the very long main straight. The middle sweepers want load, but the straight is long enough that trimming pays. **Two to three clicks below midpoint**, more if your league is slipstream-heavy.

**Dominant corner types & grip priority.** **Fast sweepers in the middle, tight technical at the end.** The long left-hand coastal sweep and the tunnel section are high-load; the final chicane-and-hairpin complex is 2nd gear. **Priority: split, with the deciding factor being that the final complex feeds the main straight** — set the car up to be excellent there and accept a compromise in the sweepers.

**Kerbs & elevation.** Elevation is moderate with a descent to the harbour section and a climb back. Kerb severity: **high at the final chicane** — these kerbs are severe and the concrete barriers are immediately outside them. Implications:
- **Rear compression damping soft** for the final chicane kerb.
- **Medium springs, ride height 1–2 clicks up.**
- The final chicane is the only place the suspension setup is genuinely tested.

**Braking zones.** **Three heavy.** **Turn 1** at the end of the long straight — the biggest stop and the primary overtaking spot, flat and wide. **The hairpin** in the second half. **The final chicane**, from high speed. **Brake bias: one click forward.**

**Traction-limited exits.** **The final chicane exit onto the main straight is decisive** — it determines your entire straight-line speed and slipstream position. **The hairpin exit** is second. **LSD acceleration sensitivity: medium-high, 24–30** ⚠️ *[v1.70 5–60 scale: a direction, not a number - see the banner]* for the final chicane exit, tempered by the kerb risk.

**Gearing.** **Gear for slipstream** — 6th tops out with a tow at the T1 board. **2nd covers the final chicane and the hairpin.**

**Tyre wear.** **Moderate, with a right-side lean** from the long left-hand coastal sweeps loading the right side; note the layout mixes direction, so side bias is milder than at Barcelona or Spa. Rear wear from the two traction exits. The long straight provides genuine cooling. **17–20 laps at 1x.**

**Pit loss.** Estimated **20–22 s**. *(Confidence: low-medium.)*

**Strategy quirks.** Enormous slipstream on the main straight makes **track position cheap** and produces excellent racing. Short-ish pit loss makes the undercut viable ⚠️ *[re-flagged 11 Sep: the undercut is weak in GT7 - see the banner]*. **One of the best all-round league circuits in GT7** — it works for both sprint and multi-stop formats.

**Top three levers.**
1. **Final chicane exit package** — 2nd gear, LSD acceleration, kerb compliance.
2. **Low-drag aero with with-tow gearing.**
3. **Aero balance for the middle sweepers** (the secondary compromise).

---

## 2.2 Dragon Trail — Gardens
**4.4 km · 17 corners · Gr.3 ≈ 1:36–1:39**

**Layout character.** Shares the main straight and Turn 1 with Seaside, then diverts inland into a substantially more technical, more undulating layout including a banked corner and a steep descent-and-climb.

**Downforce: MEDIUM-HIGH.** Full-throttle share drops to ~55% — you keep the long straight but add far more corners. **At or slightly above midpoint**, notably more than Seaside.

**Dominant corner types & grip priority.** **Medium 3rd-gear corners with elevation, plus a banked section.** More linked, more technical, less flowing than Seaside. **Priority: mechanical grip and vertical compliance**, a genuine inversion of Seaside's priorities despite the shared start.

**Kerbs & elevation.** **Elevation change is significantly greater than Seaside's** — the inland section drops and climbs sharply, and there is a compression at the bottom. Kerbs moderate. Implications:
- **Softer than your Seaside setup** — compression damping down 2–3 clicks, ride height up 2–3.
- The descent-to-compression sequence is where a stiff, low car will bottom.
- The banked corner rewards a car that can accept load without bottoming.

**Braking zones.** **Two heavy (T1 and the descent-section entry), three medium.** Several are on gradients. **Brake bias: two clicks forward** — the downhill entries demand more than Seaside does.

**Traction-limited exits.** **The final corner onto the main straight**, plus two or three slow inland exits. **LSD acceleration sensitivity: medium, 20–26** ⚠️ *[v1.70 5–60 scale: a direction, not a number - see the banner]* — the linked technical section punishes too much lock.

**Gearing.** **Gear for the main straight** but with more attention to 2nd and 3rd than at Seaside, because you use them far more often.

**Tyre wear.** **Moderate-high, front-biased.** More corners, more elevation-driven vertical loading, less straight-line recovery than Seaside. **15–18 laps at 1x.**

**Pit loss.** Estimated **20 s**. *(Confidence: low.)*

**Strategy quirks.** Harder to overtake than Seaside (fewer big braking zones, narrower inland section) so track position is more valuable. Good contrast round if your league runs both Dragon Trail layouts in a season.

**Top three levers.** **Compliance for the inland descent; brake bias forward; 2nd/3rd gear placement.**

---
## 2.3 Trial Mountain Circuit
**5.4 km · 15 corners · Gr.3 ≈ 1:47–1:50**

**Layout character.** The classic Gran Turismo original, rebuilt and widened for GT7: a long main straight, two tunnels, a substantial climb and descent, a fast esses section, and a tight final chicane.

**Downforce: MEDIUM-HIGH.** Full-throttle share ~55%. The main straight is long but the middle of the lap is a continuous sequence of medium-fast corners with elevation. **At or slightly above midpoint.**

**Dominant corner types & grip priority.** **Medium-fast sweepers with substantial elevation**, plus one uphill double-apex right and a slow final chicane. **Priority: aero platform with real vertical compliance** — the Trial Mountain problem is that you need the platform for the esses and the compliance for the elevation.

**Kerbs & elevation.** **Elevation is large** (the climb after the first tunnel and the descent through the esses). Kerb severity: **high at the final chicane** (severe, and it is the last thing before the main straight so mistakes are expensive). Implications:
- **Medium-stiff springs, ride height 2–3 clicks up.**
- **Expansion damping firm** for the crests on the climb.
- **Rear compression soft** for the final chicane kerbs.

**Braking zones.** **Three heavy.** **Turn 1** at the end of the main straight (heavy, flat, the main overtaking spot). **The corner after the first tunnel** (the tunnel exit is dark-to-light and the braking point is deceptive). **The final chicane.** **Brake bias: one to two clicks forward** for the descending sections.

**Traction-limited exits.** **The final chicane exit onto the main straight** is decisive. **The uphill double-apex exit** is second and genuinely traction-limited because it is a slow, steep, uphill exit. **LSD acceleration sensitivity: medium, 22–28 ⚠️ *[v1.70 5–60 scale: a direction, not a number - see the banner]*.**

**Gearing.** **Gear for the main straight with tow.** **2nd for the final chicane**, **3rd for the uphill double-apex.**

**Tyre wear.** **Moderate-high, front-biased**, direction-balanced (Trial Mountain mixes lefts and rights well). Elevation adds vertical loading. **15–18 laps at 1x.**

**Pit loss.** Estimated **20–22 s**. *(Confidence: low.)*

**Strategy quirks.** The widening in the GT7 remake made overtaking substantially more viable than in previous games — Turn 1 and the post-tunnel braking zone both work. Solid all-round league circuit.

**Top three levers.** **Final chicane exit; ride height/expansion damping for the elevation; aero level set in the esses.**

---

## 2.4 Deep Forest Raceway
**4.3 km · 18 corners · Gr.3 ≈ 1:26–1:29**

**Layout character.** A narrow, fast, flowing forest circuit with tunnels, meaningful elevation, and a long banked final corner onto the pit straight. Eighteen corners in 4.3 km makes it dense. In current daily rotation as a Gr.3 tyre-strategy race (16 laps, 2x fuel, 5x tyre — [DG EDGE](https://www.dg-edge.com/articles/news/gt7-daily-races-week-27-2026-autopolis-mount-panorama-deep-forest/701)).

**Downforce: MEDIUM-HIGH.** Full-throttle share ~55%. Almost every corner is a 3rd/4th-gear sweeper and the banked final corner is a sustained-load corner. **Run high** — the straight is not long enough to justify trimming.

**Dominant corner types & grip priority.** **Fast and medium sweepers, linked, with two hairpins.** The banked final corner is the signature. **Priority: aero platform**, with enough mechanical grip for the hairpins.

**Kerbs & elevation.** Elevation is substantial (climb through the forest, descent to the tunnels). Kerb severity: **low to moderate** — Deep Forest's kerbs are relatively benign, which is welcome given how narrow it is. The **banked final corner loads the suspension hard** and is where ride height matters. Implications:
- **Medium-stiff springs**; you can run relatively low.
- **Check ride height at the banked final corner specifically** — bottoming there costs you the pit straight.
- **Expansion damping moderate-firm** for the elevation crests.

**Braking zones.** **Two heavy, three medium.** The braking zone at the end of the pit straight and the hairpin. Several medium stops are on descents. **Brake bias: one to two clicks forward.**

**Traction-limited exits.** **The banked final corner exit onto the pit straight** — but note it is *banked*, which supplies grip, so it is less traction-limited than it looks. **The two hairpin exits** are the true traction events. **LSD acceleration sensitivity: medium, 20–26** ⚠️ *[v1.70 5–60 scale: a direction, not a number - see the banner]* — the linked sweeper sections punish high lock.

**Gearing.** **Gear for the pit straight**, with **4th carrying the linked sweeper sections** and **2nd for the hairpins.** Deep Forest rewards a car that can run whole sequences in one gear.

**Tyre wear.** *The reference said:* high and front-biased, 13–16 laps at 1x, the medium-vs-soft crossover the whole race at 5x. **⚠️ Measured in house on v1.71, and it does not hold** — Ford Shelby GT350R '16 at 2x, session 134, HUD gauge, five readings, monotone on all four wheels:

| wheel | %/lap | %/km | stint at `0.85/w` |
|---|---:|---:|---:|
| Front left | 2.215 | 0.521 | 38.4 laps |
| **Front right** | **2.808** | **0.660** | **30.3 laps** ← the limit |
| Rear left | 1.967 | 0.462 | 43.2 laps |
| Rear right | 2.778 | 0.653 | 30.6 laps |

30.3 laps at 2x on the practice rate, against the reference's 6.5–8 *[ASSUMED: its 13–16 laps at 1x halved for 2x, `CLAUDE.md` §5.2]* — about four times (`RECONCILIATION` AS4). **The race wore faster:** the front-right took 41.7 % in 12 laps and 25.0 % in 7 (session 138) — **3.47 and 3.57 %/lap, about a quarter above practice**, which puts the set at **about 24 laps** at `0.85/w`. Still about three times the reference, and **the rate to plan a race on**. And **gentler per kilometre than Red Bull Ring** (0.90–1.35 %/km at 2x on the same car), which is graded 3 against Deep Forest's 5, so the grade is anti-predictive here. The part that held: the circuit is direction-balanced — the front/rear split is 5.9 % and the front-right leads the front-left by only 1.27x. In the race the tyre did not bind over the 12 + 7 laps run. **One car, a Gr.N road car on its own setup; no Gr.3 car has been measured here.**

**Pit loss.** Estimated **19–20 s**. *(Confidence: low-medium.)* **Not measured in house:** the Round 6 event carries 20 s with no source recorded. What the one race here did show is the two costs of a stop that are not the lane: **standing time for fuel** — 19.73 L left at the flag *[MEASURED]* at the league's declared 2.0 L/s is **9.9 s stood still** *[DERIVED]*, against an 8 s gap to the place ahead — and a **1.41 s** cold out-lap on fresh tyres *[MEASURED, one lap: lap 14 against the stint-2 median; whether it carries pit-exit time is unverified]*, on top of about 3 s for the tyre change itself *[his figure]*.

**Strategy quirks.** **Deep Forest is narrow — overtaking is genuinely hard** and track position is expensive. *The reference said the undercut is unusually strong here - **re-flagged 11 Sep:*** the undercut is weak in GT7 (banner), and the one stop measured here paid 1.41 s on the out-lap plus the change. Stint 2 then ran about 1.0 s/lap quicker, but he stopped coasting and short-shifting at the same time, so **what the tyres bought is unresolvable, not zero**. Size the fill from the clock at the stop. **Take tyres when the gauge's worst wheel plus the laps left at the race rate would pass 85 %** — at 3.5 %/lap a set reading 42 % has about 12 laps left in it, not 18.

**Top three levers.**
1. **Front tyre life** — the stint is the race. ⚠️ *Not at 2x on the one car measured: about 24 laps at the race rate against a 20-lap race, and the fill decided that race, not the tyre. On a longer format it binds again — count it at the race rate.*
2. **Aero level**, set in the linked sweepers.
3. **Ride height at the banked final corner.**

---

## 2.5 Grand Valley — Highway 1
**5.1 km · 18 corners · Gr.3 ≈ 1:51–1:55** *(Grand Valley South: 3.1 km, 10 corners, ≈ 1:07–1:10)*

**Layout character.** The GT7 rebuild relocates Grand Valley to the Big Sur coast of California. It is now **narrower — roughly a two-lane road — with tight track limits and cliffs**, which materially changed the racing: three-wide is not viable and the margins are small ([GTPlanet: how Grand Valley changed for GT7](https://www.gtplanet.net/grand-valley-how-gran-turismos-legendary-circuit-has-changed-for-gt7/)). Sector 1 is an uphill left into a hairpin, then long serpentine descents to a second hairpin. Sector 2 has a tightening double-left, a double-right and a tunnel. Sector 3 was the most heavily revised: a much sharper 180-degree tunnel bend followed immediately by a chicane, then a right-over-bridge, left-into-tunnel, right onto the main straight.

**Downforce: MEDIUM.** Full-throttle share ~55%. There is a decent main straight but the lap is dominated by medium-speed corners and the serpentine descents. **At midpoint.**

**Dominant corner types & grip priority.** **Medium-speed corners and two hairpins, with long linked serpentine sections.** The tightening-radius double-left in Sector 2 and the sharpened 180 in Sector 3 are the technical highlights. **Priority: mechanical grip and compliance.** The narrowness means car placement precision matters more than outright cornering load.

**Kerbs & elevation.** **Elevation is large and continuous** — the circuit is essentially always climbing or descending. Kerbs are **moderate** but the track limits are tight and the barriers are close, so running wide is expensive. Implications:
- **Medium springs and soft-ish compression damping** — the descents and compressions need absorbing.
- **Ride height 2–3 clicks up.**
- Because the road is narrow and cambered, a car with too much rake will feel nervous on the descents; keep rake modest.

**Braking zones.** **Two heavy (the two hairpins), three to four medium**, several on descents. The **Sector 3 tunnel 180 followed immediately by a chicane** is the hardest sequence — you brake, turn 180 degrees, and immediately have to change direction twice. **Brake bias: two clicks forward** for the descending entries.

**Traction-limited exits.** **Both hairpin exits** and **the final right onto the main straight.** **LSD acceleration sensitivity: medium, 20–28 ⚠️ *[v1.70 5–60 scale: a direction, not a number - see the banner]*.** The hairpins want lock; the serpentines want the car free.

**Gearing.** **2nd for the hairpins and the tunnel 180.** 6th for the main straight. Grand Valley is a mid-gear circuit — 3rd and 4th spacing matters through the serpentines.

**Tyre wear.** **Moderate-high, front-biased.** Continuous direction changes on a cambered narrow road. Reasonably direction-balanced. **15–18 laps at 1x.**

**Pit loss.** Estimated **21 s**. *(Confidence: low.)*

**Strategy quirks.** **The narrowness is the defining strategic fact.** Overtaking is difficult and side-by-side racing risks a barrier. Track position is expensive; qualifying matters; and the undercut is strong ⚠️ *[re-flagged 11 Sep: the undercut is weak in GT7 - see the banner]*. Your league should expect more incidents here than at a modern permanent circuit, and should consider it a "precision" round rather than a "racing" round. The **South layout** (3.1 km) is a short sprint version using Sector 1 and a link — mechanical-grip-biased, high wear per lap, big pit-loss ratio.

**Top three levers.** **Compliance for the descents; brake bias forward; 2nd gear for the hairpins and the tunnel 180.**

---

## 2.6 Alsace — Village
**5.4 km · 17 corners · Gr.3 ≈ 2:07–2:12** *(Alsace Test Course: 2.1 km, 7 corners)*

**Layout character.** A long point-to-point-feeling French countryside road circuit: narrow, lined with barriers and hay bales, with a substantial climb, a fast descent, blind crests, and a village section. Feels like a rally stage run on tarmac.

**Downforce: MEDIUM.** Full-throttle share ~50%. Some genuinely fast sections, but the lap is dominated by medium corners on a narrow road. **At or just above midpoint** — but note that with the road this narrow you cannot always *use* high cornering speed.

**Dominant corner types & grip priority.** **Medium-speed corners with blind crests and camber changes**, plus a slow village section. **Priority: mechanical grip and vertical compliance, decisively.** Alsace is one of the least aero-rewarding of the "medium downforce" circuits because so much of the lap is spent on a bumpy, cambered, narrow road where the platform is never settled.

**Kerbs & elevation.** **Elevation is large** with a long climb and a fast descent. The road is **cambered and crowned like a real country road**, and there are blind crests. Kerbs are minimal — the hazards are barriers and hay bales. Implications:
- **Soft. This is one of your softest setups.** Compression damping down 4–5 clicks, springs medium-soft, ride height up 3–4 clicks.
- **Expansion damping firm** for the crests.
- A stiff Alsace car will skip over the crowned surface and refuse to turn.

**Braking zones.** **Two heavy, four to five medium**, many on descents or over crests. **Brake bias: two to three clicks forward** — Alsace has more downhill and crest braking than almost anything else in GT7 outside the Nordschleife.

**Traction-limited exits.** **Several slow, uphill exits in the village and climb sections.** **LSD acceleration sensitivity: medium, 20–26** ⚠️ *[v1.70 5–60 scale: a direction, not a number - see the banner]* — the narrow road means too much lock pushes you into the barriers.

**Gearing.** Gear for corner exit, not top speed. **2nd and 3rd are the working gears** and their spacing matters more than the final drive.

**Tyre wear.** **High and front-biased.** Continuous medium-speed cornering on a cambered surface, plus vertical loading from the crests. Direction-balanced. **13–16 laps at 1x.**

**Pit loss.** Estimated **22 s**. *(Confidence: low.)*

**Strategy quirks.** **Overtaking is very difficult** — narrow, barriered, few big braking zones. Track position is highly valuable and the racing tends to be processional unless there is a large pace spread. Best used for endurance formats where strategy and consistency can shuffle the order, rather than sprints. Attrition is high.

**Top three levers.** **Soft compliance package; brake bias forward; 2nd/3rd gear spacing.**

---

## 2.7 Broad Bean Raceway
**1.7 km · 5 corners · Gr.3 ≈ 0:45–0:50 (estimate)**

**Important corrections.** Broad Bean Raceway is **a separate Japanese original circuit, not part of Kyoto Driving Park** ([GT7 track list](https://gtplus.app/gt7/tracks)). It is also **genuinely thin on data** — it appears infrequently in Sport Mode. The most recent appearance I could find was a June 2026 daily race using the **Toyota Sports 800 '65 (43 hp), 6 laps**, an event about momentum and drafting rather than pace ([GTPlanet, 8 June 2026](https://www.gtplanet.net/gran-turismo-7-daily-races-where-have-you-bean-20260608/)). I found **no Gr.3 lap time data at all**, and no track guide covering corner-by-corner detail.

**What can be said with confidence.** It is 1.7 km with 5 corners — a very small, low-speed circuit, closer to a kart track in scale than a race circuit. A Gr.3 car is enormously oversized for it.

**Inferred guidance (treat as provisional):**
- **Downforce: irrelevant in level, set for balance.** Corner speeds are far too low for aero to contribute. Run high because drag is free.
- **Priority: mechanical grip, exclusively.**
- **Setup: low ride height, soft-ish springs, soft ARBs** — a Tsukuba-style maximum-mechanical-grip configuration.
- **Brake bias: neutral to slightly rearward** for rotation in the slow corners.
- **LSD acceleration sensitivity: LOW, 12–18** ⚠️ *[v1.70 5–60 scale: a direction, not a number - see the banner]* — a Gr.3 car has vastly more torque than these corners can absorb.
- **Gearing: extremely short.** 3rd or 4th maximum.
- **Tyre wear:** low in absolute terms, high per lap; rear-biased from traction.
- **Pit loss:** likely 15–18 s, which is **30–40% of a lap time** — an extreme ratio.

**Recommendation for your league: do not use Broad Bean Raceway for Gr.3.** The car/track scale mismatch, the extreme pit-loss ratio and the near-impossibility of overtaking make it unsuitable for competitive Gr.3 racing. It is a fine one-make circuit for low-power cars.

---

## 2.8 Kyoto Driving Park — Yamagiwa / Miyabi
**Yamagiwa 4.9 km · 15 corners · Gr.3 ≈ 1:47–1:51 · Miyabi 2.0 km · 7 corners · Yamagiwa + Miyabi 6.8 km · 19 corners ≈ 2:30–2:36**

**Layout character.** A Japanese mountain-and-garden complex. **Yamagiwa** is a fast, wide, sweeping mountain circuit with substantial elevation and long high-speed corners — genuinely one of the better original layouts for Gr.3. **Miyabi** is a slow, narrow, ornamental garden loop that is essentially a different sport. The **combined** layout runs both, which produces a schizophrenic setup problem.

**Downforce (Yamagiwa): MEDIUM-HIGH.** Full-throttle share ~58%. The long sweepers reward load heavily. **At or above midpoint.**
**Downforce (Miyabi): irrelevant in level.** Too slow.
**Downforce (combined): MEDIUM-HIGH**, set for Yamagiwa — it is 72% of the combined lap.

**Dominant corner types & grip priority.** **Yamagiwa: fast and medium sweepers**, aero platform priority. **Miyabi: slow, tight, mechanical grip only.** For the combined layout, **set the car for Yamagiwa and drive around Miyabi's deficiencies.**

**Kerbs & elevation.** Yamagiwa has **substantial elevation** and fast crests; kerbs are moderate. Miyabi is flat and narrow with close barriers. Implications: **medium-stiff springs, ride height 2 clicks up, firm expansion damping** for the Yamagiwa crests.

**Braking zones.** Yamagiwa: **two heavy, three medium**, several on gradients. Miyabi: several slow, light stops. **Brake bias: one to two clicks forward.**

**Traction-limited exits.** Yamagiwa's slow-corner exits (two or three) and, on the combined layout, everything in Miyabi. **LSD acceleration sensitivity: medium, 20–26 ⚠️ *[v1.70 5–60 scale: a direction, not a number - see the banner]*.** On the combined layout, err lower — Miyabi will punish lock.

**Gearing.** Yamagiwa's main straight sets 6th. **3rd/4th must carry the mountain sweepers.** On the combined layout, ensure **2nd covers Miyabi's tight corners** without being so short that Yamagiwa suffers.

**Tyre wear.** **Yamagiwa: moderate-high, front-biased**, from sustained sweeper load. **Combined: higher**, because Miyabi adds low-speed scrub with no cooling. **14–17 laps at 1x** for Yamagiwa; **12–15** combined.

**Pit loss.** Estimated **21–23 s**. *(Confidence: low.)*

**Strategy quirks.** Yamagiwa is wide and produces decent racing. Miyabi is a single-file procession. **Recommendation: use Yamagiwa for Gr.3 league racing; avoid Miyabi and the combined layout** unless you specifically want a "two-circuits-in-one" setup challenge, which is admittedly an interesting league gimmick for one round.

**Top three levers (Yamagiwa).** **Aero level; expansion damping for the crests; 3rd/4th ratio placement for the sweepers.**

---

## 2.9 Tokyo Expressway
**Central CW 4.4 km · 13 corners ≈ 1:29–1:33 · Central CCW 4.4 km · 14 corners**
**East CW 7.3 km · 13 corners ≈ 2:23–2:28 · East CCW 7.2 km · 13 corners**
**South CW 5.2 km · 17 corners ≈ 1:47–1:52 · South CCW 6.6 km · 16 corners**

**Layout character.** Elevated urban expressway loops through Tokyo at night. Concrete walls on both sides for essentially the entire lap, no run-off anywhere, long full-throttle sections, banked sweepers, and a genuinely bumpy surface with expansion joints. **East Clockwise is the most-used Gr.3 layout** and was in daily rotation in August 2026 at 10 laps, 1x/1x ([GTPlanet](https://www.gtplanet.net/gran-turismo-7-daily-races-running-like-clockwork-20260803/)).

**Downforce: LOW to MEDIUM-LOW.** Full-throttle share is high (~70% on East). The corners are mostly fast sweepers where the banking supplies load. **Three to four clicks below midpoint.** Note the caveat: with walls this close, a nervous low-downforce car is a liability — do not trim past the point where the car is stable over the joints.

**Dominant corner types & grip priority.** **Fast banked sweepers and medium 3rd/4th-gear corners**, with a small number of tight turns at the loop ends. **Priority: compliance and stability over everything.** Tokyo is the clearest case in GT7 where neither "mechanical grip" nor "aero platform" is the right frame — **vertical compliance is the frame.**

**Kerbs & elevation.** Elevation is modest but the expressway **rises and falls continuously** and there are crests where the car goes light at 250+ km/h. There are **effectively no kerbs** — there are walls. The critical feature is the **bumpy surface and expansion joints**, which hit the car at maximum speed. Implications, and this is the single most important setup note for Tokyo:
- **Ride height is the number one setting.** A car that bottoms on an expansion joint at 260 km/h next to a concrete wall will end your race. **Raise it 4–6 clicks above your circuit baseline.**
- **Compression damping soft** (down 4–6 clicks).
- **Springs medium-soft.** Resist the urge to stiffen for the banked corners.
- **Keep rake modest** — pitch changes over the crests are dangerous here.

**Braking zones.** **Few but severe.** On East CW, two to three heavy stops, all from very high speed and all into wall-lined corners. Some are on gradients. **Brake bias: two clicks forward** — you are braking from high speed on an uneven surface with the car occasionally light, which is the profile that most demands front bias. Rear lockup here means a wall.

**Traction-limited exits.** **The tight turns at the loop ends** — typically two per lap. They are slow, wall-lined and feed long straights, so they are high-value. **LSD acceleration sensitivity: medium-high, 24–30** ⚠️ *[v1.70 5–60 scale: a direction, not a number - see the banner]*, but be aware that a locked diff over a bumpy exit next to a wall is a specific risk. Test it.

**Gearing.** **Gear for top speed with slipstream** — Tokyo has a very large tow effect. 6th tops out with a tow before the main braking zone. **2nd for the loop-end turns.**

**Tyre wear.** **Low to moderate — one of the kinder circuits.** Few slow corners, few big traction events, and long straights for cooling. The **bumps do add front-tyre wear** beyond what the corner profile suggests, and the banked sweepers load one side. **20–24 laps at 1x** on East CW.

**Pit loss.** Estimated **22–25 s** — Tokyo's pit lanes are long. *(Confidence: low — verify.)*

**Strategy quirks.** **Walls plus close racing equals high attrition** — this is a survival circuit and finishing is worth more than pace. The huge slipstream makes track position cheap. Low tyre wear means most league races here should be **no-stop sprints**; a mandatory stop at Tokyo mostly just adds a random element. The counter-clockwise variants are less used and generally regarded as less good. The **Central** loops are short and tight; **South** is a middle ground.

**Top three levers.**
1. **Ride height** — the highest-value single setting at any GT7 circuit.
2. **Compression damping.**
3. **Low-drag aero with with-tow gearing** — but not past the stability limit.

---
## 2.10 Special Stage Route X
**30.3 km · 2 corners · Gr.3 ≈ 6:45–7:15 (heavily draft-dependent)**

**Layout character.** A 30 km banked oval test facility. Two corners. It exists for top-speed testing and drafting.

**Downforce: MINIMUM.** Drag is the only variable that matters.

**Dominant corner types & grip priority.** Two banked full-throttle turns. **Neither mechanical grip nor aero platform is relevant.** Ride height and drag are the setup.

**Kerbs & elevation.** No kerbs, minimal elevation. **Raise ride height to avoid bottoming on the banking; stiffen springs to resist the banking compression.**

**Braking zones.** **None.** Brake balance irrelevant.

**Traction-limited exits.** **None.** LSD settings irrelevant — use a neutral configuration.

**Gearing.** **Maximum top speed with tow.** This is the entire setup. Nothing else.

**Tyre wear.** Very low per kilometre, but **one-sided** — sustained banked load on the same side for 30 km. Long stints are trivially achievable.

**Pit loss.** Irrelevant relative to a ~7-minute lap.

**Strategy quirks.** This is a drafting exercise. **Not a league circuit.** Use for a novelty round, a top-speed shootout, or a deliberately silly season finale.

**Top three levers.** **Drag, gearing, ride height on the banking.** Nothing else exists.

---

## 2.11 Blue Moon Bay Speedway
**Full Course (oval) 3.2 km · 3 corners · Gr.3 ≈ 0:42–0:48 (draft-dependent)**
**Infield A 3.4 km · 10 corners · Infield B 2.9 km · 5 corners**

**Layout character.** A banked American-style superspeedway with two infield road-course variants.

**Downforce (oval): MINIMUM.** Drag only.
**Downforce (infield layouts): LOW to MEDIUM-LOW.** You keep a substantial banked full-throttle section but add technical corners — the compromise is real but the banking dominates.

**Dominant corner types & grip priority.** **Oval: banked full-throttle.** **Infield: slow-to-medium corners.** For the infield layouts, **the setup is dominated by ride-height survival on the banking**, exactly as at Daytona, with mechanical grip a distant second.

**Kerbs & elevation.** The banking is the only vertical event; the infield is flat with moderate kerbs. **Raise ride height for the banking; stiff enough springs to resist banking compression.**

**Braking zones.** **Oval: none.** **Infield A: two to three medium stops** from banking speed into the infield — these are the only real braking events and they are from very high speed with cold-ish brakes. **Brake bias: one click forward.**

**Traction-limited exits.** **Infield exits onto the banking** — high value because they feed the full-throttle section. **LSD acceleration sensitivity: medium, 22–28** ⚠️ *[v1.70 5–60 scale: a direction, not a number - see the banner]* on the infield layouts; irrelevant on the oval.

**Gearing.** **Oval: maximum top speed with tow.** **Infield: gear for the banking top speed, with 2nd covering the infield's slowest corner.**

**Tyre wear.** **Right side only, and heavily.** Banked left-hand load dominates. Right-front is the limiter on all three layouts. **Asymmetric setup pays if permitted.** Low absolute wear on the oval; moderate on the infield layouts.

**Pit loss.** Estimated **20–24 s**. *(Confidence: low.)* On the oval that is **~50% of a lap time.**

**Strategy quirks.** The oval is a pure drafting lottery. **Infield A is the only Blue Moon Bay layout worth serious league consideration** — it produces a genuine oval/road hybrid where slipstream on the banking and traction out of the infield both matter, and it is short enough for large grids. Expect pack racing.

**Top three levers.** **Ride height for the banking; drag and gearing; right-side tyre management.**

---

## 2.12 Sardegna — Road Track
**Layout A 5.1 km · 15 corners · Gr.3 ≈ 1:50–1:54 · Layout B 3.9 km · 13 corners · Layout C 2.7 km · 10 corners**
*(Sardegna — Windmills, 3.3 km, is the dirt/rally version and is not a Gr.3 venue.)*

**Layout character.** A wide, flowing, undulating Mediterranean road course with a long back straight, a slow hairpin, and a set of genuinely good medium-fast corners. Underused by leagues and shouldn't be — it is wide enough for real racing.

**Downforce: MEDIUM.** Full-throttle share ~58%. A decent straight balanced against sustained-load sweepers. **At midpoint.**

**Dominant corner types & grip priority.** **Medium-fast sweepers with elevation, plus one or two slow corners.** **Priority: aero platform with compliance for the undulation** — a balanced setup circuit, which is part of what makes it useful as a league round.

**Kerbs & elevation.** **Elevation is substantial and continuous.** Kerbs are **moderate and usable** — modern-style. Implications: **medium springs, ride height 2 clicks up, firm expansion damping** for the crests. Nothing extreme.

**Braking zones.** **Two heavy (the hairpin and the end of the back straight), three medium**, some on gradients. **Brake bias: one to two clicks forward.**

**Traction-limited exits.** **The hairpin exit** onto the straight, plus one or two slower exits. **LSD acceleration sensitivity: medium, 22–28 ⚠️ *[v1.70 5–60 scale: a direction, not a number - see the banner]*.**

**Gearing.** **Gear for the back straight with tow.** **2nd for the hairpin**, **4th for the sweepers.**

**Tyre wear.** **Moderate, front-biased**, direction-reasonably-balanced. The straight gives cooling. **16–19 laps at 1x.**

**Pit loss.** Estimated **20–22 s**. *(Confidence: low.)*

**Strategy quirks.** **Wide track and a big braking zone at the end of the straight make overtaking genuinely viable** — track position is cheap and the racing is good. This is an underrated league circuit; if your season needs a round that produces clean, close Gr.3 racing without extreme setup demands, **Sardegna A is one of the best choices in the game.** Layouts B and C are shorter sprint versions with progressively higher pit-loss ratios.

**Top three levers.** **Aero level; expansion damping for the undulation; hairpin exit gearing and LSD.**

---

## 2.13 Eiger Nordwand
**2.4 km · 11 corners · Gr.3 ≈ 1:00–1:05**

**Layout character.** A short alpine circuit beneath the Eiger north face, returned to the series in update 1.49. The defining feature per Polyphony's own daily-race framing is a **quadruple hairpin switchback section plus seven other tricky corners, with significant camber and gradient changes** ([racinggames.gg](https://racinggames.gg/article/gt7-daily-races-a-guide-to-the-eiger-nordwand-grand-valley-nrburgring)). Narrow, short, and steep.

**Downforce: irrelevant in level — set for balance.** Corner speeds are too low. Run high; drag is free.

**Dominant corner types & grip priority.** **Slow hairpins, in sequence, on a gradient.** **Priority: mechanical grip and traction, exclusively.** Eiger is a low-speed grip and diff exercise.

**Kerbs & elevation.** **Gradient and camber changes are the defining feature** — the switchbacks are on a steep slope, so you are alternately climbing and descending with the camber working for and against you. Kerbs are moderate. Implications:
- **Low ride height is fine (it is not bumpy), but the gradient changes load and unload the car.**
- **Soft-ish springs and soft ARBs** for maximum mechanical grip.
- **Watch rear ride height under uphill acceleration squat.**

**Braking zones.** **Four to five, all slow, several downhill.** Downhill braking into a 1st-gear hairpin is the recurring event. **Brake bias: two to three clicks forward** — the downhill hairpin entries demand it, and this is one of the settings that most affects your Eiger lap time.

**Traction-limited exits.** **Every hairpin exit, several uphill.** A Gr.3 car exiting a 1st-gear uphill hairpin with 550 hp is completely traction-limited. **LSD acceleration sensitivity: LOW, 12–20 ⚠️ *[v1.70 5–60 scale: a direction, not a number - see the banner]*.** As at Tsukuba, more lock produces more wheelspin, not more drive. This is the single most important setting at Eiger.

**Gearing.** **Very short.** 1st and 2nd are the working gears; you may not reach 4th. **Make sure 1st is not so short that you are shifting immediately out of every hairpin.**

**Tyre wear.** **Rear-biased and significant per lap** — repeated 1st-gear traction events. Low in absolute terms. **15–20 laps at 1x**, but check at your multiplier given the ~1:02 lap.

**Pit loss.** Estimated **16–18 s** — **~28% of a lap time.**

**Strategy quirks.** **Overtaking is close to impossible** — narrow, switchbacks, no straight. Track position is everything and the racing is a procession. **Recommendation: not a serious Gr.3 league circuit.** It works well for low-power one-makes (as Polyphony uses it) but Gr.3 cars are too big and too fast for it. Use for a novelty sprint at most.

**Top three levers.** **LSD acceleration (low); brake bias (forward); short gearing with correct 1st/2nd placement.**

---

## 2.14 High Speed Ring
**4.3 km · 6 corners · Gr.3 ≈ 1:20–1:24**

**Layout character.** The original Gran Turismo beginner circuit: six corners, most of them fast and banked, one hairpin, and a long main straight. Essentially a road-course-shaped oval.

**Downforce: LOW.** Full-throttle share ~78%. Almost all corners are flat or near-flat for a Gr.3 car. **Near minimum**, with just enough to keep the car stable through the banked sweepers.

**Dominant corner types & grip priority.** **Fast banked sweepers plus one hairpin and a final chicane-ish sequence.** **Priority: low drag and stability; mechanical grip only matters at the hairpin.**

**Kerbs & elevation.** Elevation is modest. Kerbs are **low and usable.** The banked sections load the car. Implications: **run low and medium-stiff** — HSR is smooth and there is nothing to absorb. Check ride height on the banked sweeper.

**Braking zones.** **One heavy (the hairpin), one medium (the final sequence).** That is it. **Brake bias: neutral to one click forward** — a low-priority setting.

**Traction-limited exits.** **The hairpin exit** and **the final corner onto the main straight.** **LSD acceleration sensitivity: medium, 22–28 ⚠️ *[v1.70 5–60 scale: a direction, not a number - see the banner]*.**

**Gearing.** **Gear for maximum top speed with tow** — HSR is one of the biggest slipstream circuits in GT7. **2nd for the hairpin.**

**Tyre wear.** **Low.** Few traction events, mostly loaded fast corners, long straight for cooling. Slight right-side bias. **22–26 laps at 1x** — among the kindest circuits in the game.

**Pit loss.** Estimated **18–20 s**. *(Confidence: low.)*

**Strategy quirks.** **Massive slipstream, easy overtaking at the hairpin, and very low tyre wear** make High Speed Ring a pure-pace-and-draft circuit. Track position is nearly worthless. Excellent for close, low-attrition racing and for large grids; poor for strategic racing since there is nothing to strategise about. **Use it for sprints and for reverse-grid entertainment rounds.**

**Top three levers.** **Drag and top-speed gearing; hairpin exit (2nd gear + LSD); ride height on the banking.**

---

## 2.15 Autodrome Lago Maggiore
**Full Course 5.8 km · 17 corners · Gr.3 ≈ 1:56–2:00**
**West 4.2 km · 13 corners · East 3.6 km · 11 corners · West End 2.4 km · 10 corners · East End 2.0 km · 8 corners · Centre 1.7 km · 8 corners**

**Layout character.** A wide, modern, purpose-built Italian lakeside circuit with a genuinely good mix of fast sweepers and a technical infield, plus six layout permutations. Flat by GT7 standards. Used for Online Time Trial #36 (West End). Underrated as a league venue.

**Downforce: MEDIUM-HIGH.** Full-throttle share ~55% on the full course. Several long, sustained-load corners. **At or above midpoint.**

**Dominant corner types & grip priority.** **Medium-fast sweepers with a technical infield section.** A genuinely balanced circuit. **Priority: aero platform**, with enough mechanical grip for the infield.

**Kerbs & elevation.** Elevation is **modest** — Lago Maggiore is one of the flatter GT7 circuits. Kerbs are **modern and flat: fully usable, low risk.** Implications: **run low and medium-stiff.** This is one of the easiest circuits in GT7 to set a car up for, which is exactly why it is a good "control" round in a league season — results reflect driving, not setup depth.

**Braking zones.** **Three heavy, three medium**, all flat, smooth and wide. **Brake bias: neutral to one click forward.**

**Traction-limited exits.** **Two or three infield exits**, plus the final corner onto the pit straight. **LSD acceleration sensitivity: medium, 22–28 ⚠️ *[v1.70 5–60 scale: a direction, not a number - see the banner]*.**

**Gearing.** **Gear for the main straight with tow.** **3rd/4th must carry the sweepers** without mid-corner shifts.

**Tyre wear.** **Moderate, front-biased**, direction-balanced. **16–19 laps at 1x.**

**Pit loss.** Estimated **20–22 s**. *(Confidence: low.)*

**Strategy quirks.** **Wide track, multiple braking zones, good run-off — overtaking is easy and attrition is low.** Track position is cheap. The six layouts give you a full season's worth of variety from one venue: West End is a compact sprint layout, East is medium, Full is the league standard. Excellent, low-drama league circuit.

**Top three levers.** **Aero level set in the sweepers; 3rd/4th ratio placement; LSD acceleration for the infield exits.**

---

## 2.16 Circuit de Sainte-Croix
**Layout A 9.5 km · 19 corners · Gr.3 ≈ 3:15–3:25**
**Layout B 7.1 km · 14 corners · ≈ 2:25–2:35 · Layout C 10.8 km · 24 corners · ≈ 3:45–3:55**
*(Confidence note: Sainte-Croix appears rarely in Sport Mode and community data is thin. Lap times are estimates from length and layout character.)*

**Layout character.** An enormous, wide, flowing French road circuit in the Verdon region — long straights, very fast sweepers, big elevation, and a lot of space. Layouts A, B and C are genuinely different circuits rather than trims of one another. The scale is closer to Le Mans than to a permanent circuit.

**Downforce: MEDIUM to MEDIUM-LOW.** Full-throttle share is high (~68%) because of the long straights, but there are enough fast sweepers that trimming to minimum hurts. **Two to three clicks below midpoint.**

**Dominant corner types & grip priority.** **Fast and medium-fast sweepers with substantial elevation**, plus a handful of slow corners. **Priority: aero platform and high-speed stability**, with vertical compliance for the elevation.

**Kerbs & elevation.** **Elevation is large.** Kerbs are **moderate** and the track is wide with real run-off — this is a forgiving circuit by original-track standards. Implications: **medium-stiff springs, ride height 2–3 clicks up, expansion damping firm** for the crests.

**Braking zones.** **Three to four heavy on Layout A**, several approached at very high speed, some on gradients. **Brake bias: one to two clicks forward.**

**Traction-limited exits.** **Two or three slow exits feeding long straights** — high value. **LSD acceleration sensitivity: medium-high, 24–30 ⚠️ *[v1.70 5–60 scale: a direction, not a number - see the banner]*.**

**Gearing.** **Gear for the longest straight with tow.** **4th/5th must carry the fast sweepers.**

**Tyre wear.** **Moderate per lap, low per unit of time** — like Le Mans, the long laps and long straights mean tyres get real recovery. Front-biased. **On Layout A expect fuel to be at least as limiting as tyres**; verify at your league's multipliers.

**Pit loss.** Estimated **24–28 s**. *(Confidence: very low.)* As a fraction of a 3:20 lap that is only ~13%, which makes pit timing relatively unimportant.

**Strategy quirks.** **The most under-used good endurance circuit in GT7.** Wide, fast, forgiving, long laps, low pit-loss ratio, fuel-relevant. If your league wants a Le Mans-style round without Le Mans' drag extremes, **Sainte-Croix Layout A is the answer.** Layout C is longer and more technical; Layout B is the sprint option.

**Top three levers.** **Aero level (the straight-vs-sweeper trade); gearing for the long straight; fuel strategy on Layout A.**

---

## 2.17 Circuits on your list that are NOT Gr.3 venues

**Colorado Springs — Lake (3.0 km, 15 corners).** This is a **dirt/rally circuit** in GT7, categorised with the rally tracks alongside Fishermans Ranch and the Barcelona rallycross layout ([Coach Dave GT7 track list](https://coachdaveacademy.com/tutorials/all-tracks-in-gran-turismo-7/)). Gr.3 cars cannot be raced here in any competitive sense — the surface requires dirt tyres and the class is not eligible. **Exclude from your calendar.**

**Lake Louise (Tri-Oval 3.1 km, Short Track 2.6 km, Long Track 3.7 km).** This is a **snow/ice circuit**. Same conclusion: **not a Gr.3 venue. Exclude.**

If your league wants a "wildcard" round on either, it has to be a different class entirely (rally cars on dirt/snow tyres), which is a separate championship, not a Gr.3 round.

**Also worth noting for completeness:** **Fishermans Ranch** (6.9 km, 40 corners) is dirt; **Northern Isle Speedway** (0.9 km oval) is a tarmac short oval but far too small for Gr.3 — it is a stock-car novelty venue.

---
# 3. SUMMARY MATRIX

Ratings are relative to the GT7 Gr.3 field, not absolute. **DF** = downforce requirement. **Mech** = mechanical-grip priority (how much of your setup budget should go to springs/ARBs/diff/camber rather than aero platform). **Wear** and **Braking** are 1–5, where 5 is most severe. **Pit%** is estimated pit loss as a percentage of one lap — the number that determines how strategically expensive a stop is.

## 3.1 Real circuits

| Circuit | Length | Corners | Gr.3 lap | DF | Mech | Wear | Braking | Wear axle/side | Pit% |
|---|---|---|---|---|---|---|---|---|---|
| Nürburgring GP | 5.1 km | 17 | 1:55–1:57 | Med-High | Med | 3 | 3 | Rear (traction) | ~20% |
| Nürburgring Nordschleife | 20.8 km | 73 | 6:20–6:30 | Med | High | 4 | 5 | Front-left | ~7% |
| Nürburgring 24h | 25.4 km | 89 | 7:50–8:00 | Med-High | High | 4 | 5 | Front-left | ~5% |
| Nürburgring Endurance | 23.9 km | 85 | 7:20–7:30 | Med-High | High | 4 | 5 | Front-left | ~5% |
| Spa-Francorchamps | 7.0 km | 21 | 2:16–2:19 | Med-Low | Low | 4 | 4 | Front-left | ~22% |
| Monza (Full) | 5.8 km | 11 | 1:47–1:50 | **Low** | **High** | 2 | **5** | Rear + front-right | ~19% |
| Monza (No Chicane) | 5.8 km | 9 | 1:41–1:44 | **Low** | Med | 2 | 3 | Front-right | ~20% |
| Suzuka | 5.8 km | 20 | 1:56–1:59 | **High** | Low | **5** | 4 | Front (both) | ~19% |
| Brands Hatch GP | 3.9 km | 9 | 1:22–1:24 | Med-High | Med | 4 | 4 | Front-left | **~24%** |
| Brands Hatch Indy | 1.9 km | 5 | 0:44–0:46 | Med | Med-High | **5** | 4 | Front-left | **~42%** |
| Interlagos | 4.3 km | 15 | 1:31–1:33 | Med | Med-High | 3 | 4 | Front-right | ~22% |
| Red Bull Ring | 4.3 km | 10 | 1:24–1:26 | Low | **High** | 3 | 4 | Rear + front-right | ~23% |
| Autopolis (Full) | 4.7 km | 18 | 1:41–1:44 | **High** | Low | 4 | 3 | Front (both) | ~21% |
| Fuji (Full) | 4.6 km | 16 | 1:33–1:36 | Med-Low | Med | 2 | **5** | Front-left | ~24% |
| Tsukuba | 2.0 km | 8 | 0:53–0:55 | n/a (balance) | **High** | 3 | 3 | Rear | **~33%** |
| Watkins Glen Long | 5.4 km | 11 | 1:44–1:47 | Med-Low | Low | 3 | 4 | Front-left | ~20% |
| Daytona Road | 5.7 km | 12 | 1:44–1:47 | **Low** | Med | 4 | 4 | **Right side** | ~28% |
| Daytona Tri-Oval | 4.0 km | 4 | 0:47–0:50 | **Min** | n/a | 3 | 1 | **Right side** | **~60%** |
| WeatherTech Laguna Seca | 3.6 km | 11 | 1:22–1:24 | Med-High | Med-High | 4 | 4 | Front-right | ~23% |
| Mount Panorama | 6.2 km | 23 | 2:00–2:03 | Med | **High** | 4 | **5** | Front-left + rear | ~24% |
| Barcelona-Catalunya GP | 4.7 km | 16 | 1:41–1:44 | **High** | Low | **5** | 4 | **Front-left (extreme)** | ~21% |
| Barcelona No Chicane | 4.7 km | 14 | 1:39–1:42 | **High** | Low | **5** | 3 | **Front-left (extreme)** | ~21% |
| Circuit de la Sarthe | 13.6 km | 38 | 3:28–3:34 | **Low** | Med | 3 | **5** | Front-left; fuel-limited | ~15% |
| Sarthe No Chicane | 13.6 km | 32 | 3:20–3:25 | **Min** | Med | 3 | 4 | Front-left; fuel-limited | ~16% |
| Willow Springs Big Willow | 4.0 km | 10 | 1:20–1:23 | Med-High | Low | **5** | 2 | **Front-left** | ~22% |
| Michelin Rwy Road Atlanta | 4.1 km | 12 | 1:20–1:23 | Med | Med | 3 | 4 | Front-left | ~25% |
| Goodwood | 3.8 km | 7 | 1:16–1:19 | Med-Low | Low | 4 | 2 | Front-left | ~23% |
| Gilles-Villeneuve | 4.4 km | 14 | 1:41–1:44 | Low | **High** | 3 | **5** | Rear (traction) | ~20% |
| Yas Marina | 5.3 km | 16 | 1:52–1:56 | Med-High | Med-High | 3 | **5** | Rear (traction) | ~19% |

## 3.2 Original circuits

| Circuit | Length | Corners | Gr.3 lap | DF | Mech | Wear | Braking | Wear axle/side | Pit% |
|---|---|---|---|---|---|---|---|---|---|
| Dragon Trail Seaside | 5.2 km | 18 | 1:50–1:53 | Med-Low | Med | 3 | 4 | Front + rear (balanced) | ~19% |
| Dragon Trail Gardens | 4.4 km | 17 | 1:36–1:39 | Med-High | Med-High | 4 | 3 | Front (both) | ~21% |
| Trial Mountain | 5.4 km | 15 | 1:47–1:50 | Med-High | Med | 3 | 4 | Front (both) | ~20% |
| Deep Forest | 4.3 km | 18 | 1:26–1:29 | Med-High | Med | **5** | 3 | Front (both) | ~23% |
| Grand Valley Highway 1 | 5.1 km | 18 | 1:51–1:55 | Med | **High** | 4 | 4 | Front (both) | ~19% |
| Grand Valley South | 3.1 km | 10 | 1:07–1:10 | Med | **High** | 4 | 3 | Front (both) | ~30% |
| Alsace Village | 5.4 km | 17 | 2:07–2:12 | Med | **High** | 4 | 4 | Front (both) | ~17% |
| Broad Bean Raceway | 1.7 km | 5 | ~0:45–0:50 *(est)* | n/a (balance) | **High** | 3 | 2 | Rear | **~35%** |
| Kyoto Yamagiwa | 4.9 km | 15 | 1:47–1:51 | Med-High | Low | 4 | 3 | Front (both) | ~20% |
| Kyoto Miyabi | 2.0 km | 7 | ~0:58–1:03 *(est)* | n/a (balance) | **High** | 3 | 2 | Rear | ~30% |
| Kyoto Yamagiwa+Miyabi | 6.8 km | 19 | 2:30–2:36 | Med-High | Med-High | 4 | 3 | Front + rear | ~14% |
| Tokyo Expressway East CW | 7.3 km | 13 | 2:23–2:28 | Low | Med *(compliance)* | 2 | 4 | Front (bump-driven) | ~17% |
| Tokyo Expressway Central CW | 4.4 km | 13 | 1:29–1:33 | Low | Med *(compliance)* | 2 | 4 | Front (bump-driven) | ~26% |
| Tokyo Expressway South CW | 5.2 km | 17 | 1:47–1:52 | Med-Low | Med *(compliance)* | 3 | 4 | Front (bump-driven) | ~22% |
| Special Stage Route X | 30.3 km | 2 | 6:45–7:15 | **Min** | n/a | 1 | 1 | One side only | ~5% |
| Blue Moon Bay (oval) | 3.2 km | 3 | 0:42–0:48 | **Min** | n/a | 2 | 1 | **Right side** | **~50%** |
| Blue Moon Bay Infield A | 3.4 km | 10 | ~1:15–1:20 *(est)* | Low | Med | 3 | 3 | **Right side** | ~28% |
| Sardegna Road Track A | 5.1 km | 15 | 1:50–1:54 | Med | Med | 3 | 4 | Front (both) | ~19% |
| Eiger Nordwand | 2.4 km | 11 | 1:00–1:05 | n/a (balance) | **High** | 3 | 4 | Rear (traction) | ~28% |
| High Speed Ring | 4.3 km | 6 | 1:20–1:24 | **Low** | Low | **1** | 2 | Right side (mild) | ~23% |
| Lago Maggiore Full | 5.8 km | 17 | 1:56–2:00 | Med-High | Med | 3 | 3 | Front (both) | ~18% |
| Lago Maggiore West End | 2.4 km | 10 | ~0:52–0:57 *(est)* | Med | Med-High | 3 | 3 | Front (both) | ~35% |
| Sainte-Croix A | 9.5 km | 19 | 3:15–3:25 *(est)* | Med-Low | Low | 3 | 4 | Front; fuel-relevant | ~13% |
| Sainte-Croix B | 7.1 km | 14 | 2:25–2:35 *(est)* | Med-Low | Low | 3 | 4 | Front | ~17% |
| Sainte-Croix C | 10.8 km | 24 | 3:45–3:55 *(est)* | Med | Med | 3 | 4 | Front | ~11% |
| Colorado Springs Lake | 3.0 km | 15 | — | **DIRT — not a Gr.3 venue** | — | — | — | — | — |
| Lake Louise (all) | 2.6–3.7 km | 3–11 | — | **SNOW — not a Gr.3 venue** | — | — | — | — | — |

## 3.3 Quick-scan groupings for calendar design

**Lowest downforce (trim aggressively, gear for tow):** Monza, Le Mans, Daytona (both), SSRX, Blue Moon Bay, High Speed Ring, Tokyo Expressway, Red Bull Ring, Gilles-Villeneuve.

**Highest downforce (max wing, aero platform setups):** Suzuka, Barcelona (both), Autopolis, Deep Forest, Lago Maggiore, Nürburgring GP, Dragon Trail Gardens, Kyoto Yamagiwa.

**Mechanical-grip-dominant (spend the setup budget on springs/ARB/diff, not wing):** Tsukuba, Eiger, Broad Bean, Kyoto Miyabi, Monza, Gilles-Villeneuve, Red Bull Ring, Bathurst, Grand Valley, Alsace.

**Compliance-dominant (ride height and damping are the whole setup):** Tokyo Expressway, Nordschleife, Bathurst, Interlagos, Alsace, Monza, Willow Springs, Daytona.

**Tyre-limited — build multi-stop races here:** Barcelona, Suzuka, Willow Springs Big Willow, Deep Forest, Brands Hatch Indy, Spa, Daytona Road, Bathurst.

**Fuel-limited before tyre-limited:** Le Mans, Sainte-Croix A/C, Nürburgring 24h/Endurance, SSRX.

**Track position cheap (overtaking easy — good for reverse grids and large fields):** Monza, Fuji, Red Bull Ring, High Speed Ring, Daytona, Dragon Trail Seaside, Lago Maggiore, Sardegna, Gilles-Villeneuve, Watkins Glen.

**Track position expensive (qualifying decides the race — use for championship-defining rounds or short-field races):** Deep Forest, Suzuka, Barcelona, Bathurst, Laguna Seca, Alsace, Grand Valley, Autopolis, Eiger, Goodwood.

**Highest pit-loss ratio (a stop is a huge event — avoid mandatory stops):** Daytona Tri-Oval, Blue Moon Bay oval, Brands Hatch Indy, Broad Bean, Lago Maggiore West End, Tsukuba, Grand Valley South.

**Lowest pit-loss ratio (stops are cheap — strategy is about tyres and fuel, not timing):** Nürburgring 24h/Endurance, Nordschleife, SSRX, Sainte-Croix C, Le Mans, Kyoto combined.

---

# 4. Recommended league calendar archetypes

Three ready-made season shapes, using the above.

**Sprint championship (8 rounds, no stops, 12–20 min races).** Monza · Red Bull Ring · Brands Hatch GP · Fuji · Dragon Trail Seaside · Laguna Seca · High Speed Ring · Interlagos. Rationale: mixes low- and high-downforce, mixes cheap and expensive track position, keeps tyre wear off the critical path, and every round has at least one real overtaking zone.

**Multi-stop championship (6 rounds, 40–60 min, mandatory stops).** Spa · Barcelona GP · Suzuka · Deep Forest · Bathurst · Watkins Glen Long. Rationale: all are tyre-limited with meaningful front-axle degradation, all have non-trivial pit loss, and the mix of easy-pass (Spa, Watkins Glen) and hard-pass (Barcelona, Deep Forest, Bathurst) circuits means both pace and strategy get rewarded across the season.

**Endurance championship (4 rounds, 90 min+).** Le Mans · Nürburgring 24h · Sainte-Croix A · Sardegna A (or Lago Maggiore Full). Rationale: long laps, low pit-loss ratios, fuel relevance, and enough width and run-off that a two-hour race is survivable. Le Mans and the Nürburgring 24h are the two genuine blue-riband events in GT7.

---

# 5. Caveats worth restating

- **Lap times are ballparks**, BoP-dependent, and drift with every Polyphony BoP revision. Re-baseline each season.
- **Pit-loss figures are estimates** except Le Mans (~32 s, well-sourced). Bathurst, Daytona and Spa are confirmed "long" by community consensus but not measured. **Measure them.** The Pit% column in the matrix is the number that will most change your strategy, and it is the number I am least confident about.
- **Tyre stint lengths are at 1x** and assume Racing Mediums and a clean, tyre-aware driving style. Post-1.49 thermal modelling means an aggressive first two laps of a stint measurably shortens it — this is a driver-coaching point as much as a setup point.
- **Broad Bean Raceway, Goodwood, Sainte-Croix and the Blue Moon Bay infield layouts have genuinely thin GT7 community data.** Those entries lean on layout geometry and transferable real-world engineering rather than observed GT7 Gr.3 running. I have flagged them individually; treat their numbers as hypotheses to test, not facts.
- **Colorado Springs and Lake Louise are rally surfaces** and cannot host Gr.3 racing. **Michelin Raceway = Road Atlanta** and **WeatherTech Raceway = Laguna Seca** — one venue each.

---

## Sources

- [Complete GT7 track layout list — gtplus.app](https://gtplus.app/gt7/tracks/layouts) — lengths and corner counts for all 84 layouts
- [Complete GT7 track list — gtplus.app](https://gtplus.app/gt7/tracks) — official track naming
- [Circuit de la Sarthe in GT7 — gtplus.app](https://gtplus.app/gt7/tracks/circuit-de-la-sarthe) — Le Mans length, straight length, gradient
- [GT7 Update 1.49 Now Available: Eiger Nordwand, New Physics, & More — GTPlanet](https://www.gtplanet.net/gran-turismo-7-update-149-available-20240725/) — 1.49 physics model changes
- [Gran Turismo 7 Update 1.49 Arrives July 25, With New Physics Model — GTPlanet](https://www.gtplanet.net/gran-turismo-7-update-149-preview-20240724/)
- [Update Details (1.49) — gran-turismo.com](https://www.gran-turismo.com/us/gt7/news/00_3114934.html)
- [Pit lane — GTPlanet forum](https://www.gtplanet.net/forum/threads/pit-lane.426905/) — Le Mans ~32 s pit loss; Bathurst/Daytona/Spa noted as long
- [Gr.3 BoP Test — GTPlanet forum](https://www.gtplanet.net/forum/threads/gr-3-bop-test.425451/) — Gr.3 top-speed brackets 265–283 km/h, car-by-track variability
- [Racing soft tires vs medium — GTPlanet forum](https://www.gtplanet.net/forum/threads/racing-soft-tires-vs-medium.427384/) — compound testing methodology; absence of reliable published deltas
- [Time Trial — Results and Community Leader Boards — GTPlanet](https://www.gtplanet.net/forum/threads/time-trial-results-and-community-leader-boards.424113/) — Gr.3 Online Time Trial venue history
- [6:23 BOP Gr3 Nordschleife — GTPlanet](https://www.gtplanet.net/forum/threads/6-23-bop-gr3-nordschleife-in-online-game-today.370547/)
- [Gran Turismo 7 Tuning Guide: Every Setting Explained (2026) — Coach Dave Academy](https://coachdaveacademy.com/tutorials/gran-turismo-7-tuning-explained/) — tuning hierarchy, rake, LSD, brake bias, gearing
- [Flux89 GT7 Tuning Cheat Sheet](https://www.flux89.com/guides/gt7-tuning-cheat-sheet) — downforce/spring/ARB/damper/camber/toe/LSD baseline ranges
- [Mastering Brake Balance in Gran Turismo 7 — DG EDGE](https://www.dg-edge.com/articles/guides-equipment/mastering-brake-balance-in-gran-turismo-7/360) — −5/+5 slider, per-drivetrain values, track-type guidance
- [How To Tune in Gran Turismo 7 — SimRacingSetup](https://simracingsetup.com/gran-turismo/how-to-tune-in-gran-turismo-7/)
- [Complete Gran Turismo 7 Track List — Coach Dave Academy](https://coachdaveacademy.com/tutorials/all-tracks-in-gran-turismo-7/) — rally vs tarmac surface classification
- [Grand Valley: How Gran Turismo's Legendary Circuit Has Changed for GT7 — GTPlanet](https://www.gtplanet.net/grand-valley-how-gran-turismos-legendary-circuit-has-changed-for-gt7/) — Highway 1 sector-by-sector layout analysis
- [GT7 Daily Races Week 27/2026: Autopolis, Mount Panorama, Deep Forest — DG EDGE](https://www.dg-edge.com/articles/news/gt7-daily-races-week-27-2026-autopolis-mount-panorama-deep-forest/701) — Deep Forest Gr.3 16 laps, 2x fuel/5x tyre
- [Gran Turismo 7 Daily Races: Running Like Clockwork — GTPlanet (3 Aug 2026)](https://www.gtplanet.net/gran-turismo-7-daily-races-running-like-clockwork-20260803/) — current Monza/Red Bull Ring/Tokyo East rotation, 1x multipliers
- [Gran Turismo 7 Daily Races: Where Have You Bean? — GTPlanet (8 Jun 2026)](https://www.gtplanet.net/gran-turismo-7-daily-races-where-have-you-bean-20260608/) — Broad Bean Raceway usage
- [GT7 Daily Races guide: Eiger Nordwand, Grand Valley, Nürburgring — RacingGames](https://racinggames.gg/article/gt7-daily-races-a-guide-to-the-eiger-nordwand-grand-valley-nrburgring) — Eiger quadruple-hairpin description, Nürburgring Endurance format
- [Gran Turismo 7 Tracks Database — DG EDGE](https://www.dg-edge.com/database/tracks)
- [Gran Turismo Wiki — GT7 Track List](https://gran-turismo.fandom.com/wiki/Gran_Turismo_7/Track_List)
