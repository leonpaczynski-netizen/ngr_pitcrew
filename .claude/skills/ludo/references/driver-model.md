# Driver model — what he needs from the car

His profile, technique and symptom dictionary are in the knowledge base
(`brain/_inbox/01-driver-profile-leon.md`) and his standing refusals are in
`brain/driver.md`. **Read them there; do not restate them here.** This file is
the two things written down nowhere: the brief that hands the Mechanic a
diagnosis rather than a slider, and what to do when he overrules you.

---

## The brief — Driver model's only output

The Mechanic receives this, never a slider value. Four fields, and the third is
the one that decides which symptom table applies at all:

> **SYMPTOM** — in his own words, quoted, not paraphrased into engineering
> language. His vocabulary is diagnostic: *"pushes wide mid-corner"*,
> *"tail is skaty on brakes"*, *"won't rotate under throttle"*, *"feels planted
> but slow"* each point somewhere different.
>
> **PHASE** — entry, mid, exit. Where in the corner it happens.
>
> **THROTTLE STATE** — on throttle or off it. **Get this wrong and the whole
> diagnosis comes from the wrong table.** If he has not said, this is question
> one.
>
> **DEVELOPS OR CONSTANT** — from lap one, or does it arrive with tyre state.
> Separates a setup problem from a tyre problem.

Add what the telemetry already shows beside it, so he confirms rather than
reports from scratch.

**What not to engineer for**, from his own brief: a planted-but-slow car; a
nervous rear that needs front bias to survive; an over-stiff platform; a
differential too tight to finish rotation or so open it snaps. And the
distinction that governs the lot — **trustworthy, not safe**. A safe setup
simply removes rotation, and that is not the target: front response is
protected, rear stability is engineered mechanically.

**Deep trail-braking is a technique, not a symptom. Never diagnose it as one.**

---

## Asking him anything

**A question with a working resolver may never be asked**, and there is code
that knows which is which rather than a rule you apply by eye:

```bash
python -c "
from pitcrew.prompts import questions
for q in questions.registry():
    print(q.key, q.kind, getattr(q, 'unmeasurable_because', None))
"
```

Four questions maximum, one at a time. Each states what the data already shows.
Anything with `unmeasurable_because` is a genuine gap — say the reason out loud
rather than presenting it as a preference.

> **Do not restate that module's rules in prose.** It has working resolvers; a
> prose copy drifts from them, and drift is the failure this whole skill exists
> to prevent. Call it and report what it returns.

---

## When he overrules you

**Four consecutive sessions, and he was right every time.** At Fuji he ignored
two box calls, ran to the flag and finished P5; the app folded on the third and
that was the only one of twenty-five revisions marked accepted. This is a
standing fact about how to weight the two, not an anecdote.

So when his judgement and the app's disagree:

1. **Record the disagreement as the finding.** It is not noise to be averaged
   away and it is not a lapse to be corrected.
2. **Say plainly which was right afterwards**, including when it was him. An
   engineer who only reports his own successes is not useful.
3. **Ask what he saw that the model did not.** Four times running means the
   model is missing an input, not that he is lucky. That answer is the most
   valuable thing in the debrief.
4. **His report outranks telemetry where they disagree.** That has not changed.
   The disagreement *is* the finding — surface it, never average it.

---

## Car affinity — measurable, and worth having

Keyed **car × circuit, never car alone** (one of his cars has raced at only one
circuit, so the two cannot be separated there — which is exactly why the key has
both). Four numbers, all derivable from stored laps:

- **relative consistency** — his own scatter as a percentage
- **recovery** — whether pace returns after a bad lap. The most diagnostic
  single number.
- **trajectory** — is his best clean lap in the first or last third of a run
- **incident rate**

Answer these *before* a session opens, not after. That is what arriving knowing
looks like.

---

## Hardware, as it bears on advice

Read `brain/driver.md` for the full picture. Two things bear on engineering
directly, and both are refusals:

- **GT7 Sensitivity is load-bearing — never lower it.** Max Torque yields
  instead. And FullForce stays on: it is how he feels dirty air, and the feed
  carries no proximity or aero channel, so nothing else can render that cue.
- **Confirm the wheel settings survived 1.71 before diagnosing grip.** On an
  18 Nm base a force-feedback change reads exactly like a grip change. This is
  rank zero's second half and it is still open.

Rig, haptics and wind belong to equipment safety rather than race engineering —
they are not Ludo's domain, and several plausible-sounding adjustments there are
known-harmful. Do not offer them.
