# Vehicle frequencies, human vibration perception, and one piston

**12 Sep 2026.** Research brief for the re-placement of seven tactile effects
across 25–160 Hz on a single ButtKicker Gamer Pro. Feeds
`docs/RIG-SWEEP_2026-09-12.md` and `docs/RIG-RETUNE_REMOUNT.md`.

Every claim below carries one of four labels. **The labels are the point of the
document** — the rig has twice been retuned on numbers whose provenance nobody
could reconstruct.

| Label | Means |
|---|---|
| **[MEASURED]** | Stated by a standards body, a manufacturer datasheet, or a peer-reviewed measurement. Cited. |
| **[DERIVED]** | Arithmetic I did here, from a formula whose source is cited. Reproducible; check it. |
| **[CONVENTION]** | Engineering or community practice with a stated rationale but no measurement behind it. |
| **[FOLKLORE]** | Circulates widely, no source found. Recorded so nobody re-imports it as fact. |
| **[GAP]** | The literature does not answer this, or I could not reach a primary source. |

---

## 0. The two findings that change the decision

Before the detail, the two results that bear on tonight's open questions.

### 0.1 Almost nothing the rig represents actually lives in 25–160 Hz

Worked out in §1. At racing speed, a V8 fires at 400 Hz, 50 mm kerb ribs strike
at 667 Hz, and 100 mm road texture excites 556 Hz. The phenomena that genuinely
occupy 25–160 Hz are a short list: wheel-hop (10–20 Hz), low engine orders at
low RPM, and the low rotation orders of the wheel.

**So "semantically plausible as the thing it represents" cannot mean physical
fidelity.** For six of the seven effects the rig is not reproducing the real
frequency and could not. What it is doing is operating a *learned code*. That is
exactly what the driver's 130 Hz kerb report is evidence of: he did not say the
kerb felt wrong physically, he said it *named a different thing*. Frequency here
is a symbol, and the constraint on moving a cue is that it must not collide with
a symbol he already holds.

This reframes the whole allocation problem and it is the most useful thing in
this document.

### 0.2 The 96 kg observation cannot be mass loading — it is damping

The coordinator's proposed mechanism was that adding the driver raises the
effective mass `M` the housing is bolted to, so relative displacement
`x_rel = x_piston · (1 + m/M)` falls and the stops are reached later.

**The arithmetic does not support it.** The Gamer Pro's piston is 1 lb =
0.454 kg [MEASURED, manufacturer spec — §5.1]. [DERIVED]:

| Effective mass `M` | factor `(1 + m/M)` | in dB |
|---|---|---|
| 5 kg | 1.091 | +0.75 |
| 20 kg | 1.023 | +0.19 |
| 50 kg | 1.009 | +0.08 |
| 150 kg | 1.003 | +0.03 |

Going from a bare seat-and-frame (call it 20 kg) to seat-frame-plus-driver
(116 kg) changes relative displacement by **0.16 dB**. That is not a repeatable
observation from a seat; it is nothing. The term `m/M` is already negligible
because the piston is light and the rig is not.

**The mechanism that does fit is damping, and it also explains the stiffness
paradox.** Worked through in §5.5. In short: if 60 Hz is a lightly-damped
structural mode of seat-plus-mount, the housing recoils hard at that frequency
and in antiphase with the piston, so relative displacement is the *sum* of the
two motions, not the difference. A seated human is a heavily lossy load; sitting
down damps the mode, shrinks the recoil, and the stops are reached later. And a
stiffer path does not remove a resonance — it **moves it up**, which is precisely
what the sweep recorded (the 40–55 peak went to 60 and narrowed, the 70 Hz null
vanished). The remount moved a lightly-damped mode into the middle of where six
of the seven effects live.

---

## 1. Where real vehicle phenomena actually sit

### 1.1 Engine firing frequency

For a four-stroke, each cylinder fires once per two revolutions, so

    f_firing = (RPM / 60) × (N_cyl / 2)        [Hz]

and the *engine order* of the firing event is `N_cyl / 2` — 2nd order for an
inline-4, 3rd for a V6, 4th for a V8, 6th for a V12. Orders are multiples of
shaft rotation frequency `RPM/60`; four-stroke engines also produce half-orders
because the cycle takes two revolutions. [MEASURED — this is the definition of
engine order, standard across NVH practice; the arithmetic below is DERIVED.]

[DERIVED] Firing frequency, Hz:

| RPM | I4 | V6 | V8 | V10 | V12 |
|---|---|---|---|---|---|
| 800 | 26.7 | 40.0 | 53.3 | 66.7 | 80.0 |
| 2000 | 66.7 | 100 | 133 | 167 | 200 |
| 4000 | 133 | 200 | 267 | 333 | 400 |
| 6000 | 200 | 300 | 400 | 500 | 600 |
| 8000 | 267 | 400 | 533 | 667 | 800 |

**Consequence for the rig.** The engine bed currently sits at 28–34 Hz. For a
Gr.3 V8 at 6000 rpm the real firing frequency is 400 Hz — a factor of twelve
away. The bed is not reproducing firing frequency and cannot: 400 Hz is above
the transducer's rated range and far above the 160 Hz high-cut. Only an idling
I4 (≈27 Hz at 800 rpm) coincides with the band at all.

What 28–34 Hz *is* physically plausible as is a low engine order at racing RPM —
at 7000 rpm, 0.25th order is 29 Hz, 0.5 order is 58 Hz. Half-order content is
real in a four-stroke. [DERIVED, and the plausibility argument is mine, not a
sourced claim — treat as reasoning, not measurement.]

**[GAP]** I did not reach a primary NVH source stating which order dominates the
*seat-track* response for each engine configuration (as opposed to which order
is present). The claim "crossplane V8 is 4th-order dominant, flatplane is not"
circulates widely; I could not verify it against SAE or an OEM paper in the time
available. Do not rely on it.

### 1.2 Road texture excitation

    f = v / λ        v = speed [m/s], λ = surface wavelength [m]

[DERIVED], Hz:

| λ | 100 km/h | 150 km/h | 200 km/h | 250 km/h |
|---|---|---|---|---|
| 50 mm | 556 | 833 | 1111 | 1389 |
| 100 mm | 278 | 417 | 556 | 694 |
| 200 mm | 139 | 208 | 278 | 347 |
| 500 mm | 55.6 | 83.3 | 111 | 139 |
| 1 m | 27.8 | 41.7 | 55.6 | 69.4 |
| 2 m | 13.9 | 20.8 | 27.8 | 34.7 |

**Consequence.** The road bed at 34–41 Hz corresponds to surface wavelengths of
roughly **0.4–1.6 m at racing speed** — that is not "texture", it is
*unevenness*: long-wave undulation, the scale of a patched surface or a
settlement ripple, which is exactly what the suspension actually transmits into
the seat. So the current placement is physically defensible, and for a better
reason than the source comment in `synth.py` gives.

Texture in the paving-engineering sense (macrotexture, ~0.5–50 mm) lands at
**550 Hz and up** and is inaudible to this rig entirely.

**[GAP]** ISO 13473 (road surface texture classification: micro/macro/mega
texture band definitions) and ISO 8608 (vertical road profile PSD, roughness
classes A–H) are the standards that own these wavelength bands. I did not obtain
either document; the 0.5 mm / 50 mm / 500 mm boundaries quoted above come from
general circulation, not from a copy of the standard. **Treat the band names as
[FOLKLORE] until someone reads ISO 13473-1.** The arithmetic `f = v/λ` does not
depend on them.

### 1.3 Tyre cavity resonance

Commonly quoted at 200–250 Hz for a passenger tyre: the first circumferential
acoustic mode of the air column inside the tyre, `f ≈ c / (2π·R_eff)` with `c`
the speed of sound.

**[GAP]** I did not reach a primary source (SAE or peer-reviewed) in the time
available. **However, the conclusion for this rig does not depend on the exact
figure**: any value in the 200–250 Hz region is above the transducer's 200 Hz
rating and far above the 160 Hz high-cut, so tyre cavity resonance is out of
scope for this rig whatever its precise value. Recorded here only so it is not
later "discovered" and allocated a band.

### 1.4 Suspension natural frequencies

Sprung-mass ride frequency and unsprung-mass (wheel-hop) frequency:

    f_ride = (1/2π)·√(k_ride / m_sprung)
    f_hop  = (1/2π)·√((k_spring + k_tyre) / m_unsprung)

[MEASURED, as textbook relations — these are the standard quarter-car results.]
Typical values that circulate are 1–1.5 Hz for a passenger car, 2–3 Hz for a
sports car, 3–5 Hz and above for a downforce car; wheel-hop 10–20 Hz.

**[GAP]** I did not verify those typical ranges against Gillespie or an
equivalent primary text. They are consistent with everything else in the
programme's knowledge base but should be labelled [CONVENTION] until checked.

**Consequence.** Ride frequencies (1–5 Hz) are **below the amplifier's fixed
25 Hz low-cut** and cannot be represented on this rig at all. Wheel-hop at
10–20 Hz is also below it. This is a hard limit of the BKA-PRO, not a tuning
choice — see §5.1. Anything the app wants to say about chassis platform or
bottoming has to be said with a *carrier inside the band*, modulated, rather
than at the true frequency.

That is a real finding for `chassis_load` at 56–66 Hz: it is not a ride
frequency and cannot be. It is a symbol.

### 1.5 Kerbs, ripple strips, expansion joints

    f_strike = v / p        p = rib pitch [m]

[DERIVED], Hz:

| speed | p = 100 mm | p = 250 mm | p = 500 mm |
|---|---|---|---|
| 80 km/h | 222 | 88.9 | 44.4 |
| 100 km/h | 278 | 111 | 55.6 |
| 150 km/h | 417 | 167 | 83.3 |
| 180 km/h | 500 | 200 | 100 |

**[GAP] I did not obtain the FIA circuit design specification for kerb
geometry.** The pitches above are plausible spans, not sourced values. Without
the actual rib pitch the strike-rate arithmetic cannot be closed.

What *can* be said without it: at any plausible rib pitch and any racing speed
the ripple rate lands **above 160 Hz for fine kerbs and in the 45–110 Hz region
only for coarse, widely-spaced ones**. The current `impact` band of 52–60 Hz
therefore corresponds to a ~500 mm feature pitch at 100–110 km/h — physically
that is an expansion joint or a single large kerb element, not a serrated ripple
strip.

A single strike is an impulse: broadband, with its spectrum set by the contact
duration, decaying into whatever structural modes it excites. A short impulse
excites the whole band at once, which is why an impact cue is the one effect
whose *envelope* carries more information than its carrier. [DERIVED from
standard impulse/transient reasoning, not from a cited measurement.]

### 1.6 Wheel rotation orders — the one family that does fit

    f_1 = v / (2π·R)        R = rolling radius

[DERIVED] at R = 0.33 m:

| speed | 1st order | 2nd | 4th | 10th |
|---|---|---|---|---|
| 100 km/h | 13.4 | 26.8 | 53.6 | 134 |
| 150 km/h | 20.1 | 40.2 | 80.4 | 201 |
| 200 km/h | 26.8 | 53.6 | 107 | 268 |
| 250 km/h | 33.5 | 67.0 | 134 | 335 |

**This is the only phenomenon family that naturally occupies the rig's whole
usable band**, and it is speed-dependent in a way the driver can feel is
correct. Brake judder is driven by disc thickness variation and appears at low
orders of wheel rotation — 1st and 2nd order, so 13–67 Hz at racing speed. Brake
squeal is a different phenomenon entirely, at 1–16 kHz, and is irrelevant here.

**[GAP]** The judder-order and squeal-frequency claims are from general
circulation; I did not reach SAE brake NVH literature. Label [CONVENTION].

**Consequence, and it is a strong one.** A brake cue in the **40–67 Hz** region
is the single most physically honest placement available anywhere in this
system: it is genuinely what 1st/2nd-order judder does at racing speed. The
current `brake_limit` at 40–50 Hz is right for a better reason than "it is the
strongest ten hertz on the rig".

### 1.7 ABS, wheelspin, driveline

**[GAP] — all three.** I did not reach primary sources for:

- ABS pressure modulation rate (commonly quoted 4–20 Hz, with the pump motor
  higher). A Bosch document would settle it. **Not verified.**
- Wheelspin / longitudinal slip oscillation signatures.
- Driveline shuffle (commonly 2–10 Hz) and first driveline torsional mode
  (commonly 40–80 Hz); gear mesh `f = (RPM/60)·N_teeth`, which is the only one
  of these whose formula is not in doubt.

These matter for `driveline` (50 Hz) and `rear_traction` (86–104 Hz) and I am
not going to invent numbers for them. The gear-mesh formula is sound; the rest
needs a second pass.

---

## 2. Human vibration perception

### 2.1 ISO 2631-1 frequency weightings

`Wk` is the vertical (z-axis) weighting for seated whole-body vibration; `Wd` is
the horizontal (x/y) weighting. [MEASURED — ISO 2631-1:1997.]

ISO 2631-1 applies **similar weighting from 4 to 8 Hz**, the region where the
seated body is most sensitive to vertical vibration, and that region coincides
with the primary resonance of the abdomen and thoracic cavity.
([DADiSP ISO 2631 module documentation](https://www.dadisp.com/iso26311.htm),
which reproduces the standard's weighting tables.)

The actual filter realisations — poles, zeros, tolerances — live in **ISO 8041**,
not in ISO 2631-1. ([ISO 8041-1:2017](https://www.iso.org/standard/70648.html);
a preview of the standard is at
[iteh.ai](https://cdn.standards.iteh.ai/samples/70648/e65496c7c6f4476c999478b53066147a/ISO-8041-1-2017.pdf).)
Band-limiting corner frequencies are set one-third octave outside the nominal
range of each weighting.

**Consequence, and it is uncomfortable.** `Wk` peaks at 4–8 Hz. **The entire
usable band of this rig — 25–160 Hz — is on the falling skirt of the human
whole-body sensitivity curve.** The amplifier's fixed 25 Hz low-cut removes
every frequency the seated body is actually most sensitive to. That is not a
defect to fix; it is a permanent property of this hardware, and it is why the
rig needs real level to be felt at all.

**[GAP]** I did not obtain the numerical weighting table or the asymptotic
slopes from the standard itself. The "4–8 Hz" statement above is sourced; the
precise peak, the band edges and the roll-off rates are not.

### 2.2 Seated whole-body resonance

The principal resonance of the seated human body in vertical vibration is
**between 4 and 6 Hz** in driving-point apparent mass, with Fairley and Griffin
(1989) the standard reference, and it appears consistently in seat-to-head and
seat-to-spine transmissibility as well. A second resonance is reported between
**8 and 12 Hz**. [MEASURED.]

Critically, **the resonance is not fixed**: it falls from about 6 Hz to about
4 Hz as vibration magnitude rises from 0.25 to 2.0 m/s² RMS, and it rises with a
backrest, an erect posture, and especially with increased muscle tension.
([Resonance behaviour of the seated human body and effects of posture, *Journal
of Biomechanics*](https://www.sciencedirect.com/science/article/abs/pii/S0021929097001267);
[Fairley & Griffin, The apparent mass of the seated human body: vertical
vibration, *J. Biomech.*](https://www.sciencedirect.com/science/article/abs/pii/0021929089900316).)

Two consequences, and the second is the one that matters tonight:

1. A driver braced against 18 Nm of wheel torque and cornering load is a
   *different* mechanical load from a driver sitting still. Any calibration taken
   at rest is taken on the wrong body. This is worth knowing before the next
   perception-threshold run.
2. **A seated human is a large, lossy, nonlinear mechanical load**, and the
   apparent-mass literature is the evidence for it. That is the foundation of
   the damping explanation in §5.5.

**[GAP]** Apparent mass at 60 Hz specifically. The literature above is dominated
by the 0–20 Hz range because that is what ISO 2631 cares about. One search
result referenced apparent mass measured to 100 Hz, but I did not obtain it. The
magnitude of the driver's damping contribution at 60 Hz is therefore **not
quantified here** — which is exactly why §5.6 proposes measuring it rather than
assuming it.

### 2.3 Vibrotactile receptor channels

The four-channel model (Bolanowski, Gescheider, Verrillo & Checkosky) holds that
touch is mediated by four psychophysically separable channels: P (Pacinian),
NP I, NP II, NP III. [MEASURED.]

The **Pacinian channel peaks at 250–300 Hz**, extending roughly 200–400 Hz, with
sensitivity falling rapidly outside that range.
([Vibrotactile Sensitivity and the Frequency Response of the Pacinian
Corpuscle](https://www.researchgate.net/publication/272013262_Vibrotactile_Sensitivity_and_the_Frequency_Response_of_the_Pacinian_Corpuscle).)
Gescheider's forward-masking work supports a triplex/multi-channel account of
cutaneous mechanoreception
([Vibrotactile forward masking: psychophysical evidence for a triplex theory of
cutaneous mechanoreception](https://pubmed.ncbi.nlm.nih.gov/4031252/)).

**Consequence.** The rig's band, 25–160 Hz, sits **below the Pacinian optimum**
and spans the transition between non-Pacinian and Pacinian mediation. There is
no frequency in this rig's range where the skin is most sensitive. Again: not
fixable, but it explains why the rig needs level.

**[GAP]** I did not obtain the absolute threshold curves in dB re 1 µm, nor the
−12 dB/octave Pacinian low-frequency slope, from a primary source. Also note
that the vibrotactile channel literature is overwhelmingly **fingertip and
thenar eminence**, not buttocks-through-a-seat-shell. How well it transfers is
itself a [GAP].

### 2.4 Difference limens

Vibrotactile **frequency** discrimination ranges from **3% to 50%** depending on
experimental conditions, and mostly follows Weber's law.
([Dissociation of Vibrotactile Frequency Discrimination Performances for
Supra-Threshold and Near-Threshold
Vibrations](https://link.springer.com/chapter/10.1007/978-3-642-31404-9_14).)
**Amplitude** discrimination also follows Weber's law, near-linearly with
magnitude
([Vibrotactile amplitude discrimination capacity parallels magnitude changes in
somatosensory cortex and follows Weber's Law](https://pubmed.ncbi.nlm.nih.gov/18651137/)).
Near threshold, discrimination is very poor — of order 20 dB.

**Consequence, and it is a design constraint.** A frequency JND that can be as
poor as 50% means **two cues one-third of an octave apart may not be
discriminable as different frequencies at all.** The current plan has
`brake_limit` at 40–50, `driveline` at 50, and `impact` at 52–60. Those centres
are within 20% of each other. On the frequency axis alone, **they are the same
cue.** Whatever separates them in practice, it is not their carrier frequency.

The usable dynamic range measured on this rig (17–25.5 dB depending on
frequency) against a supra-threshold intensity JND gives only a modest number of
distinguishable levels — and near the perception floor, where the JND degrades
toward 20 dB, effectively **one**.

### 2.5 Amplitude modulation rate

**[GAP] — largely unfilled.** I did not reach primary sources on AM-rate
perception, the flutter/roughness transition, or the useful range of AM rates.
`transducer.AM_RANGE_HZ = (5.0, 16.0)` and the source comment claiming fusion
above ~20 Hz are therefore **[FOLKLORE] within this codebase** — plausible,
consistent with the auditory analogue, and unsourced.

This is the highest-value remaining gap, because §3 concludes that **modulation
and rhythm are the axis that actually works**, and the app's modulation range is
currently set by an unsourced number.

---

## 3. Masking, and what actually separates two cues on one piston

This is the decision section.

### 3.1 Masking is channel-bound, not narrowband

Gescheider's masking work found that remote-site masking was effective **only
when masker and test stimulus were both within the frequency range of the
Pacinian system**, and that **cross-channel masking did not occur**. [MEASURED.]
Using a very small (0.01 cm²) contactor to eliminate Pacinian involvement, the
results supported detection being determined by two separate populations of
non-Pacinian receptors.
([Vibrotactile masking: effects of one- and two-site
stimulation](https://www.researchgate.net/publication/225520277_Vibrotactile_masking_Effects_of_oneand_two-site_stimulation);
[Gescheider, forward masking / triplex theory](https://pubmed.ncbi.nlm.nih.gov/4031252/).)

**What this means for the rig:** masking is organised by *channel*, and the
rig's whole band falls within roughly one to two channels. There is no
"put it in a different critical band" move available inside 25–160 Hz, because
the channel boundary that would buy real immunity is up at the Pacinian
transition, outside the band.

**[GAP]** I did not find a paper that measures tactile masking *tuning width* in
octaves and states whether auditory-style critical bands exist in touch. The
strong form of the claim — "tactile masking is broadly tuned, there are no
narrow critical bands" — remains **unverified**, though the channel-bound result
above points that way.

### 3.2 The tactile system does resolve spectrum — but the lowest component wins

This is the most decision-relevant paper I found, and it **refutes** the
assumption I started with.

Le et al. (2023) presented complex vibrotactile signals of 2–4 superimposed pure
tones to the fingertip via a voice-coil actuator and asked, in a 3AFC task,
whether participants could detect that one component had been removed.
([Tactile Sensitivity to the Frequency Spectrum of Complex Vibrotactile Signals,
bioRxiv](https://www.biorxiv.org/content/10.1101/2023.11.10.566309v1.full).)
[MEASURED.] Findings:

- Removing the **lowest** tone was detected at **87.8%** (SD 32).
- Removing the **highest** tone was detected at only **55.9%** (SD 49) — barely
  above the 33% chance level of a 3AFC task.
- Discriminability of a missing tone is well predicted by **its ratio to the
  lowest pure tone**, sigmoidal, R² = 0.78.
- **No significant effect of complexity** — going from 2 to 4 components did not
  change how salient an individual component was.

Independently, Bernard, Thoret, Huloux & Ystad found that for noisy vibrations,
after intensity equalisation, **"the balance between low and high frequencies was
the most important cue"** — the perception of a complex vibration is driven by
its low/high spectral balance rather than by its resolved components.
([The high/low frequency balance drives the perception of noisy vibrations,
arXiv:2311.10644](https://arxiv.org/abs/2311.10644).) [MEASURED.]

**Three consequences, and they are the core of the recommendation:**

1. **The tactile system is not spectrally blind.** Two simultaneous components
   can be resolved, so the seven-effects-on-one-piston plan is not doomed.
2. **But salience is set by the ratio to the lowest component present.** A
   high-frequency cue competing against a permanently-present low-frequency bed
   is at a structural disadvantage *that raising its own level only partly
   fixes*. The low component sets the reference.
3. **"No effect of complexity" is good news**: the seventh simultaneous effect
   is not categorically worse than the second. The problem is not the count, it
   is the spectral balance.

**Point 2 is in direct tension with the current profile.** `engine` (28–34) and
`road` (34–41) are the two always-on beds, and they are the **lowest two bands in
the plan**. By Le et al., they are therefore the components that set salience for
everything above them, for the whole of every lap. The existing ducking
mechanism is the right instinct and this is the measurement that justifies it —
but it also argues that the *resting* balance, not just the ducked balance,
should be reconsidered: an always-on bed placed below every event cue is the
worst position it can occupy.

### 3.3 What actually separates cues: rhythm, not frequency

The Tactons literature is unambiguous and it is the most directly applicable
body of work available.

- Participants identify **three different rhythms at 93% accuracy**
  (Brown, Brewster & Purchase, 2005). Another reported rhythm-recognition figure
  is **90.97%**. [MEASURED.]
- Tactons encoding **two** dimensions — rhythm plus vibrotactile "roughness" —
  are identified at around **70%**. [MEASURED.]
- The capacity to perceive vibrotactile frequency appears **largely attributable
  to temporal cues rather than spectral properties**, the tactile system being
  relatively insensitive to waveform variation.

([Brewster & Brown, *Tactons: structured tactile messages for non-visual
information display*](http://eprints.gla.ac.uk/3443/1/tactons_aussi.pdf);
[Brown, Brewster & Purchase, *Multidimensional Tactons for Non-Visual
Information Display*](http://www.cs.columbia.edu/~coms6998-11/papers/Brown_MobHCI06.pdf) —
note I could not extract the full text of the second PDF; the percentages above
come from secondary summaries of it and should be re-checked against the paper.)

**The direct answer to the brief's central question.** How much frequency
separation do two simultaneous cues need to stay distinguishable on one
actuator? **The literature does not give a number, and the reason it does not is
that frequency is the wrong axis to be asking about.** Frequency JND is 3–50%,
masking is channel-bound rather than narrowband, salience is set by the lowest
component, and identification accuracy on the rhythm axis (90%+) is far above
anything reported for frequency or amplitude. [GAP on the number; [MEASURED] on
why the number is the wrong thing to want.]

**Design consequence:** separation between the seven effects should be carried
primarily by **envelope — onset, rhythm, duration, modulation** — and only
secondarily by carrier frequency. Frequency's real job here is *semantic
labelling* (§0.1), not discrimination.

Which is, notably, what the rig already does for `brake_limit` (7 Hz pulse
regulating, 16 Hz at lock) and what it does not do for `driveline`, `impact` and
`chassis_load`, whose carriers are 50, 52–60 and 56–66 — indistinguishable by
frequency per §2.4, and therefore distinguishable only if their envelopes differ
sharply.

### 3.4 Temporal masking

**[GAP].** Forward and backward masking exist in vibrotaction and Gescheider's
forward-masking paper is cited above, but I did not obtain the decay time
constants, tactile gap-detection thresholds, or temporal-order thresholds. These
matter for deciding how close in *time* two events can be and still both
register — which, given §3.3, is the axis the design now depends on. **This is
the second highest-value remaining gap.**

---

## 4. Established practice in sim racing

**[GAP] — essentially unfilled, and honestly so.**

I did not reach SimHub's official documentation or source, so I cannot state
whether SimHub ships stated default frequencies per effect or leaves frequency
entirely to the user. `synth.py` records that the current profile's gains and
frequencies "come straight from his SimHub profile", which means **the app's
present band allocation is inherited from a user-authored profile, not from any
published SimHub default.**

The widely circulated community frequency maps (engine low, road mid, slip high,
ABS pulsed) are **[FOLKLORE]** as far as this document is concerned: they
circulate on forums and in shared profiles, and I found no published measurement
or stated rationale behind any of them. They should not be cited as
justification for a band choice.

The NVH band vocabulary — "ride", "shake", "harshness", "boom", "roughness" —
is **[CONVENTION]**; I did not reach a primary source defining the numeric
boundaries.

**What this section would need:** the SimHub wiki/repository, and one NVH text.
Neither is hard to get; I ran out of time before the rig physics, which was the
more decision-critical half.

---

## 5. Inertial shaker physics — and what actually happened to this rig

### 5.1 The hardware, from the manufacturer

[MEASURED — official specifications.]

**ButtKicker Gamer Pro transducer**
([thebuttkicker.com](https://thebuttkicker.com/products/buttkicker-gamer-pro)):

| Parameter | Value |
|---|---|
| Frequency response | **5–200 Hz** |
| Piston weight | **1 lb (0.454 kg)** |
| Nominal impedance | 2 Ω |
| Power handling | 75 W min / 250 W max |
| Dimensions | 8.25 × 4.75 × 4.5 in |
| Unit weight | 4.9 lb |

**BKA-PRO amplifier**
([Owner's manual](https://manuals.plus/buttkicker/bka-pro-power-amplifier-manual)):

| Parameter | Value |
|---|---|
| Frequency response | 10–300 Hz, −3 dB |
| **Low-cut filter** | **25 Hz, −3 dB, fixed, −12 dB/octave** |
| **High-cut filter** | **user-selectable 40 Hz or 160 Hz, −3 dB, −12 dB/octave** |
| Power output | 150 W @ 2 Ω |

This confirms the rig description exactly, and adds one fact that was not in the
project's notes: **the high-cut is a two-position switch, 40 Hz or 160 Hz — not a
continuous control.** 160 Hz is the only usable position for a seven-effect plan.

**Mounting orientation: [GAP], and it is the manufacturer's gap.** Neither the
amplifier manual nor the Gamer Pro product page states any mounting-orientation
requirement or preference. The product page describes a universal clamp for
posts and tubing and mentions no orientation restriction. **Guitammer publishes
no guidance on vertical versus horizontal mounting.** That is worth recording
plainly: the decision this rig is facing is one the manufacturer does not
address.

### 5.2 The governing model

An inertial shaker is a mass `m` on a suspension of stiffness `k` and damping
`c`, inside a housing bolted to a structure. The voice coil pushes the mass; the
reaction pushes the housing. Delivered force is `F = −m·a_mass`.

Three regimes, separated by the suspension resonance `f₀ = (1/2π)√(k/m)`:

| Region | Behaviour | Delivered force | Mass displacement |
|---|---|---|---|
| `f ≪ f₀` | stiffness-controlled | falls as `f²` | roughly flat |
| `f ≈ f₀` | resonance | peak | **peak**, amplified by Q |
| `f ≫ f₀` | mass-controlled | roughly flat | falls as `1/f²` |

Above resonance a roughly constant force proportional to the actuator force is
delivered; below resonance the proof mass moves *with* the housing and little
relative motion is created, while at resonance the mass moves with maximum
amplitude. ([Inertial mass actuator block force frequency
response](https://www.researchgate.net/figure/nertial-mass-actuator-and-its-block-force-frequency-response-function_fig1_266655305).)
[MEASURED as established theory.]

**The key structural fact: excursion demand peaks at `f₀` and falls away on both
sides.** End-stop knock, which is what happens when demanded excursion exceeds
available travel, therefore appears **first at `f₀`**.

### 5.3 Static sag when the motion axis is vertical

Mount the unit with its motion axis vertical and the mass sags under its own
weight by `δ = m·g/k`. Substituting `k = m·(2πf₀)²`:

> **δ = g / (2πf₀)²**

The mass cancels. Sag is a function of the suspension resonance **alone**. This
is the standard static-deflection relation used throughout vibration-isolator
selection, usually written `f_n ≈ 15.76/√δ` with δ in mm
([vibration isolation mount selection guide](https://vibromera.eu/example/how-to-isolate-vibration-in-industrial-equipment-calculations-selection-of-mounts-resonance-zones-and-installation-practice/);
also [Arup, Resonant Frequency from Static
Deflection](https://strutt.arup.com/help/Vibration/ResFreqFromStaticDef.htm)).
[MEASURED as a standard relation.] [DERIVED] — and the two forms agree exactly:

| `f₀` | sag `δ` | check: 15.76/√δ |
|---|---|---|
| **5 Hz** | **9.94 mm** | 5.00 Hz |
| **8 Hz** | **3.88 mm** | 8.00 Hz |
| **10 Hz** | **2.48 mm** | 10.00 Hz |
| 15 Hz | 1.10 mm | 15.00 Hz |
| 20 Hz | 0.62 mm | 20.00 Hz |
| 30 Hz | 0.28 mm | 30.00 Hz |
| **60 Hz** | **0.069 mm** | 60.00 Hz |

Headroom lost when sag eats one-sided travel is `20·log₁₀(x_max/(x_max − δ))`.
[DERIVED]:

| Loss | requires δ to be this fraction of one-sided travel |
|---|---|
| 1 dB | 10.9% |
| 3 dB | 29.2% |
| 6 dB | 49.9% |
| **9 dB** | **64.5%** |
| **12 dB** | **74.9%** |

Horizontal mounting has **zero** gravity offset — gravity acts perpendicular to
the motion axis — so the mass stays centred and keeps its full symmetric travel.
Inverting a vertical mount does not help: the offset is the same magnitude
toward the other stop.

### 5.4 The resonance cannot be 60 Hz — and that settles the sag question

Put the published spec against the sag table.

**The Gamer Pro is rated 5–200 Hz.** Below `f₀` an inertial shaker's delivered
force falls at 12 dB/octave. If `f₀` were 60 Hz, then at 5 Hz — 3.58 octaves
below — output would be down roughly **43 dB**. No manufacturer rates a
transducer to a frequency where it delivers 0.7% of its mid-band force.

> **A published 5 Hz lower limit is only consistent with a suspension resonance
> at or below roughly 5–10 Hz.** [DERIVED from the manufacturer's own spec plus
> standard inertial-shaker theory.]

And then the sag follows immediately:

> **`f₀` ≈ 5–10 Hz implies gravity sag of 2.5–9.9 mm.**

Against plausible one-sided travel for a unit of this size, that is not a
fraction of the travel — **it is plausibly all of it.** A 9.9 mm sag would park
the piston hard against the lower stop before any signal is applied.

**Conversely, if `f₀` really were 60 Hz, sag would be 0.069 mm**, and by the
headroom table a 9–12 dB loss would require total one-sided travel of about
0.1 mm. That is not a credible figure for a 1 lb piston in a 4.5-inch housing.

**Conclusion [DERIVED]:** the coordinator's working hypothesis is supported. The
shaker's suspension resonance is low — below the amplifier's 25 Hz low-cut, and
therefore never directly excited — **the 60 Hz feature is not the piston's
resonance**, and gravity sag is large enough to explain the remount's headroom
cost. The sweep document's attribution of 60 Hz to "the transducer's own
reaction-mass resonance" should be corrected.

### 5.5 What the 60 Hz feature is, and why the driver's mass changes it

If 60 Hz is not the piston resonance it must be a **structural mode of seat plus
mount**. Four independent observations fit that and nothing else:

1. **It moved when the structure changed.** The peak was at 40–55 Hz on the
   compliant (weak-axis) path and is at 60 Hz and narrower on the stiff-axis
   path. A piston's own `f₀` does not move when you re-bolt the housing; a
   structural mode does, and **stiffer means higher**, which is the direction
   observed. The 70 Hz null vanishing is the same mode structure rearranging.
2. **It is sharp and high-Q** — the acoustic sweep put the 60 Hz fundamental
   18 dB above its neighbours at identical drive. That is resonant gain.
3. **It is impulsive** — kurtosis 14.7 at 60 Hz versus 4.6 at 85 Hz. Knock, not
   buzz.
4. **A 96 kg driver changes it.** A structural mode is retuned and damped by
   adding a large lossy mass to the seat shell. A gravity sag cannot be changed
   by sitting down at all.

**Why the housing resonance makes knock worse, not better.** Knock depends on
*relative* displacement between piston and housing. At a structural resonance
the housing recoils with large amplitude and — driven by the reaction of the
piston — in antiphase with it, so the two motions **add**:
`|x_rel| = |x_piston| + |x_housing|`. Damping the structure shrinks `x_housing`
and so shrinks `x_rel`. **That is the mechanism behind the 96 kg observation,
and it is damping, not inertia.**

The inertial route the coordinator proposed — `x_rel = x_piston·(1 + m/M)` — is
correct algebra but numerically dead here: with `m` = 0.454 kg, the whole term
changes by **0.16 dB** between a bare rig and a rig with a 96 kg driver in it
(§0.2). It cannot produce a repeatable observation from the seat. The seated
human's value here is that it is **lossy**, which the apparent-mass literature
(§2.2) establishes, not that it is heavy.

**And this resolves the stiffness paradox.** Stiffening the path did not reduce
recoil, because stiffening does not remove a resonance — it relocates it. The
weak-axis mount put its modes at 40–55 Hz with an antiresonance at 70; the
stiff-axis mount put a sharper mode at 60 Hz, **in the middle of where six of
the seven effects live** (engine 28–34, road 34–41, brake 40–50, driveline 50,
impact 52–60, chassis_load 56–66). The remount did not make the structure worse
in general; it moved the one bad frequency into the worst possible place.

**So the remount cost two separate things at once, and they were confounded by a
single action:**

- **Gravity sag** (from the orientation change) — a broadband loss of travel,
  and the credible source of the 9–12 dB.
- **Mode relocation** (from the axis change) — a narrowband amplification of
  relative displacement at 60 Hz, and the source of the knock *centre*.

One action changed both variables. That is why the rig's own notes could not
decide between them, and it is why §5.6 separates them.

**One caveat on the 9–12 dB figure itself.** The August reference was taken at
amp 50 (its maximum, per `transducer.py`) and the September comparison at amp 35.
The sweep document states "same amp"; the amp setting differed. The *direction*
is robust — a lower total drive now knocks — but the *magnitude* folds in an
uncalibrated pot taper. Treat 9–12 dB as an upper bound until re-measured at a
matched amp setting.

### 5.6 The discriminating measurements

Four, in ascending order of effort. The first two settle it.

**A. Measure the sag directly. Five minutes, no acoustics, decisive.**
Unbolt the unit. Rest it horizontal on foam, and measure the piston's rest
position relative to the housing with a depth gauge or calipers. Stand it
vertical on foam and measure again. The difference *is* δ.

| If δ measures | then `f₀` is | and gravity sag is |
|---|---|---|
| ~10 mm | 5 Hz | the whole story — the piston sits on the stop |
| ~2.5 mm | 10 Hz | a major, probably dominant, cost |
| ~1 mm | 15 Hz | significant against 1.5–2 mm of travel |
| unmeasurable | ≥40 Hz | not the mechanism; look elsewhere |

This single static reading discriminates between every hypothesis in §5.4 and
needs no sweep at all. **Do this one first.**

**B. The driver-mass sweep — settles whether 60 Hz is structural.**
Sweep 30–140 Hz at fixed level, acoustically, with and without the 96 kg driver.

> **The discriminator is frequency shift, not level.** If the 60 Hz peak **moves
> down and broadens** with the driver in the seat, it is a structural mode of
> seat-plus-mount and §5.5 is confirmed. If it **stays at 60 Hz** and only its
> level changes, the structural story is wrong and the piston resonance needs
> re-examining.

You already have the equipment and the method — use the same normalise-against-
own-fundamental technique from the 12 Sep sweep, since it survived its negative
control. Track the peak *frequency* and the −3 dB width, not just the amplitude.

**C. Orientation on foam — isolates gravity from structure.**
With the unit free-standing on foam (frame removed from the problem entirely),
find the knock threshold at 40 and 60 Hz, horizontal then vertical. Any
difference is **purely** the gravity offset, because nothing else changed. This
un-confounds the remount.

**D. Free-air `f₀` by impedance sweep — the definitive number.**
Drive the unit through a known series resistor and sweep 3–100 Hz, measuring
voltage across the driver and across the resistor. `|Z|` peaks at `f₀`. Do it
free (on foam) and again bolted, and vertical versus horizontal — a sag large
enough to push the coil into a nonlinear region will shift `f₀` between
orientations, which is itself a useful reading. This gives the actual number
instead of the inference in §5.4.

**Re-measure the 9–12 dB at a matched amp setting** while you are there (§5.5).

---

## 6. What this implies for the seven effects

Offered as reasoning from the findings above, **not** as a recommendation the
sources make. The allocation decision is the engineer's.

1. **Frequency is a semantic label here, not a discrimination axis.** §0.1, §2.4
   and §3.3 all converge on it. The driver's "130 Hz reads as ABS or traction
   control" is not a quirk to work around — it is the system working as the
   literature says it does, and it is the *only* strong evidence on file about
   what any of these frequencies mean to him. Treat his learned map as data and
   re-place around it.

2. **Carry separation on the envelope.** Rhythm identification runs above 90%;
   frequency JND runs 3–50% and amplitude JND degrades to ~20 dB near threshold.
   `driveline` (50), `impact` (52–60) and `chassis_load` (56–66) are effectively
   one carrier. If they must stay where they are, their **onsets, durations and
   modulation must differ sharply** or they will not be three cues.

3. **The always-on beds are in the worst place they could be.** Le et al. found
   salience is set by the ratio to the *lowest* component present, and `engine`
   (28–34) and `road` (34–41) are the lowest bands and are on for the whole lap.
   Ducking is the right mechanism and is now justified by measurement rather
   than instinct — but moving a bed *above* the event cues, rather than below
   them, is worth considering on the same evidence.

4. **40–67 Hz is the most physically honest region on the rig**, because 1st and
   2nd-order wheel rotation genuinely lands there at racing speed (§1.6). It is
   the natural home for anything rotational — brake judder, wheel state. It is
   also where the 60 Hz structural mode sits, which is the conflict.

5. **The 120 Hz region is the rig's best real estate and it is nearly empty.**
   25.5 dB of usable range, no knock at −3 dBFS, and measurably clean in the
   acoustic sweep. Only `rear_traction` (86–104) is anywhere near it, and 85–100
   is the rattle band. The obvious move is to migrate cues upward — with the
   explicit constraint from finding 1 that the driver has already assigned 130 Hz
   a meaning, so the migration must respect the map he has, not overwrite it.

6. **Do not fix the spectral plan before §5.6-A and §5.6-B.** If the 60 Hz
   feature is structural, it can be *moved* by changing the mount — a far better
   outcome than designing a permanent 52–70 Hz no-go band into the profile. The
   measurement is cheaper than the redesign.

---

## 7. Coverage — what this document does not answer

Stated plainly, per the brief. These are gaps, not conclusions.

**Not verified against a primary source:**
- Dominant engine order per cylinder configuration (§1.1)
- ISO 13473 texture classes and ISO 8608 roughness classes (§1.2)
- Tyre cavity resonance — though the conclusion is robust regardless (§1.3)
- Typical sprung/unsprung frequency ranges (§1.4)
- FIA kerb geometry and rib pitch (§1.5)
- ABS modulation rate; wheelspin signatures; driveline shuffle and torsional
  modes (§1.7)
- Brake judder order and squeal band (§1.6)
- ISO 2631-1 numerical weighting table, peak, band edges, slopes (§2.1)
- Seated apparent mass **at 60 Hz** — directly relevant to §5.5 (§2.2)
- Vibrotactile absolute threshold curves (§2.3)
- AM-rate perception and the flutter/roughness transition — **the app's
  `AM_RANGE_HZ = (5, 16)` is unsourced** (§2.5)
- Tactile masking tuning width / whether critical bands exist (§3.1)
- Temporal masking time constants, gap detection, temporal order (§3.4)
- SimHub defaults and any stated rationale; NVH band definitions (§4)

**Answered by the literature as "wrong question":**
- How much frequency separation two simultaneous cues need. No number exists,
  and §3.3 explains why the number is not the thing to want.

**The two gaps most worth closing next**, because the current design rests on
them: **AM-rate perception** (§2.5) and **temporal masking** (§3.4). Both feed
the envelope axis, which §3.3 identifies as the one that actually works.
