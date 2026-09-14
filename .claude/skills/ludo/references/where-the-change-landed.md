# Where The Change Landed

Moved out of `SKILL.md` (plan row 2.9), unchanged. The skill keeps the heading and points here.

## Where the change landed — never the lap time alone

**The lap time cannot show a tune working, and that is measured, not an
opinion.** His lap-to-lap sigma is 0.918 s, which puts the whole-lap detection
floor at 1.74 s — above the entire 0.5–1.5 s/lap degradation band and above
every setup effect this project has tried to measure. The audit of 4 Sep 2026
said it outright: no instrument in the app could show a tune working.

**That is an argument about the whole lap and it does not carry to the parts.**
A setup change is almost always local — a spring where the car is loaded, a
diff where it is putting power down, a wing where it is fast. The lap adds that
one effect to nine other corners of noise and then asks you to find it.

The arithmetic, because the opposite is usually assumed. A corner is 3–4×
noisier than a whole lap **in relative terms** — true, and it is exactly why
a per-lap per-corner instruction is refused. But for an effect concentrated in one
place what matters is *absolute* scatter. If ten corners contribute
independently, the lap's 0.918 s is √10 × one corner's, so a corner carries
about 0.29 s. A 0.3 s change is a third of the noise on the lap and all of it
in its own corner. **Cutting the lap up is not a finer version of the same
measurement — it is a better one, for anything not spread evenly around the
circuit.**

### The ladder, cheapest first

```bash
python tools/where_the_change_landed.py --before 129 130 --after 132
python tools/where_the_change_landed.py --before 129 --after 132 --bins
```

1. **Sectors.** Always present, no frames to read. Three numbers with their own
   spread beside them, and a delta inside that spread is printed as
   *inside the scatter* — which is a refusal, not a small finding.
2. **Distance bins** (`--bins`). 100 m at a time, `d/v_after − d/v_before`,
   summing back to the delta as an identity. Each bin is labelled by what the
   car was doing **in the BEFORE run only**, so the classification cannot be
   moved by the thing being measured. This is what separates *drag* from
   *grip* from *the driver adapting*: they all make one slower lap and they
   land in different places.
3. **Corners**, for the phase question — `corners.aggregate_corners` for the
   metrics and `corner_findings.analyse` for trends that clear each corner's
   *own* measured noise floor. `Report.silent` names the corners that cannot
   carry a claim; report those as silent.

### Inconsistency is a finding, not the bar a finding has to clear

**The driver's correction, 5 Sep 2026, and it is the more useful half of
this.** Scatter had one job here — a delta inside it claims nothing — and that
is right as far as it goes and stops one lap short:

> *Why is the car not set up for a certain part of the track? If two sectors
> are close each lap and one has spread, what is in that sector causing it?
> Like the Bus Stop at Daytona and T1. T1 needed `lsd_b`, the Bus Stop needed
> front compression lowered. That could have been identified earlier if laps
> weren't thrown away as noise but actually analysed as to why there is noise.*

**A corner he cannot repeat is a corner where the car is not repeatable** —
a setup finding with a location already attached. And the mean cannot give you
it: a mean over an unrepeatable corner is a confident number describing
nothing that happened. Both of those changes were found late for exactly this
reason.

The tool prints it under `CONSISTENCY`, per sector, either side of the change.
Three things it does before it will say anything:

- **Detrended.** Improvement across a run is ~0.3 s and beats every setup
  effect on file, so a sector getting quicker every lap has a big raw spread
  and a small residual one. Only the residual is about the car.
- **Relative, not absolute.** Sectors are not the same length; ranking raw
  spread puts the longest first by construction.
- **F-tested.** Nine laps a side needs about **3.2×**, six laps about **5.1×**,
  before the extremes are distinguishable. It reports the ratio *and* the p,
  and refuses to rank what it cannot separate. A sector 1.4× another is not
  the answer to anything.

⚠ **Above 10% relative spread, resolve it — never dismiss it.** The driver's
second correction, and it is a rule about your posture, not about a threshold:
*don't dismiss as data error, Ludo should ask, not dismiss. The variability of
data is data to investigate.*

Ten percent of a sector is seconds, which is more than a driver is normally
inconsistent by — so it is **ambiguous**, and both branches matter. It is
either an instrument fault (7% of laps in this archive teleport and speed
integration cannot see it; a sector model can straddle a pit entry; an out-lap
can slip the filter) **or it is the most important finding on the screen** — a
corner the car cannot be driven the same way twice. Those demand opposite
answers, so settle it rather than picking one:

```python
from pitcrew.analysis.distance import teleports   # the instrument half, measured
```

**This fired on real data the day it was written**: session 93's S1 carried 23%
and 18× its neighbours. That is a question, and it has not been answered yet.

Then ask what is physically in that sector — and note that `corner_models` is
`auto-segment` everywhere, so you locate it by **distance into the lap**
(`--bins` ranks it) and describe it, rather than naming a turn the app cannot
honestly name.

### A change is never judged where it was aimed

**The Spa lesson, in his words:** *setting a car up for one section can leave
it vulnerable in other sections, and it is about finding a setup that maximises
driver, car and track.*

A change assessed only in the sector it was meant to fix will look like a
success nearly every time. The tool prints a **TRADE-OFF** line when one sector
improved and another went the other way — counting only movements outside
their own scatter, because a gain inside the noise paying for a loss inside the
noise is two pieces of nothing being traded.

**Sectors do not carry equal leverage, so a trade is not settled by adding it
up.** Measured at Daytona: zone 4 is the highest-leverage exit by 3×, at 0.67 s
per km/h and carrying 1,525 m, while the banking is last at 0.0367 — a risk
corner, not a time corner. Half a tenth bought in a low-leverage place does not
pay for half a tenth lost in a high-leverage one, and it certainly does not pay
for a corner that has become unrepeatable. Say what the trade was and what it
was worth; do not report the net and call it an improvement.

### The traps, and each has been paid for

- **Two sector models is two pieces of road.** GT7 broadcasts no sectors; these
  are the app's own cut, and a rack can hold two sets of lines. The tool
  refuses rather than comparing them. Never hand-compare S2 across runs
  without checking `sector_model`.
- **Out-laps and excursions come out first.** An out-lap's S1 starts in the
  pit box — one read 5.58 s on a 95 s lap. And Daytona T1 read r=−0.86 against
  lap time until two off-track laps came out, when it collapsed to −0.30.
- **The compound is the first confound**, not an afterthought. A softer tyre
  wearing a setup's clothes is the standing trap; the tool warns when the two
  sides differ and tells you the two cannot be separated.
- **Medians do not add up.** The sum of sector medians will not equal the lap
  delta, because the best S1 and the best S2 came from different laps. That
  gap is arithmetic, not an error.
- ⛔ **Never bank per-corner "opportunities" into a lap time.** The bin total
  is an identity — it reconstructs a delta actually driven. A sum of
  best-cases is session scatter, and scatter is a state, never a loss.

### Straights are not a free measurement

A straight looks like the cleanest thing on the circuit and is not. Terminal
speed has a measured floor of **0.56–2.77 km/h** at Daytona, and it is
**confounded by wind**: a +10.9 km/h reading there was wind, proved because the
two straights face 347° and 144° and moved in *opposite* directions. So a
straight-speed claim needs both ends of the circuit, or it needs the wind
checked — and a one-straight gain is not evidence of less drag.

---
