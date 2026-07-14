# Setup Brain — Validator-vs-Engineer Architectural Audit

**Question asked:** where does the code still behave like a cautious *validation engine*
instead of an experienced *race engineer*? Grounded in a four-thread code trace
(vehicle, track, driver, objective/coupling). Every claim carries a file:line anchor.

## Executive verdict

The Group 41–64 work made the Setup Brain **safe** (no false gearbox/wheelspin/bottoming
claims, no incomplete-setup-approved, discipline labels, proven-history surfaced,
AI audit-only). It did **not** make it **think**. Concretely, an experienced engineer
starts from *what car, what track, what race, what driver, what has worked* and reasons
in **coupled systems**. The current engine does almost none of that:

- **No vehicle model.** The car is a name + a ranges dict + a drivetrain string + a gear
  count. Power, weight, torque exist for 579 cars (`data/car_specs.json`) but reach only
  AI-prompt text — **never authoring**.
- **One track knob.** Rich track geometry (corner density, straight fraction, elevation,
  per-corner windows, telemetry braking/traction/kerb zones) collapses into a single
  3-value `aero_bias` that moves only front/rear downforce. Gearing-to-the-straight is
  *claimed in docstrings but does not exist*. Elevation is computed and read by nothing.
- **A thin driver layer.** 8 boolean flags → a handful of fixed one-click nudges in the
  baseline path only; two of them cancel each other; **zero** effect on the telemetry path.
- **No objective functions.** Base/Qualifying/Race are one generator + a fixed
  `_SESSION_BIAS_TABLE` of per-field offsets. Qualifying = base values + fixed deltas.
  Race setup values ignore total race time, tyre life and fuel entirely.
- **No coupling.** Every field is decided by its own single-field rule. `setup_arbitration`
  only *annotates* whether already-proposed changes compound — it authors nothing.
- **Defer-instead-of-engineer.** Four conflicting complaints collapse to one "dominant",
  per-field safety contraindications empty the proposed set, and the coherence gate then
  returns `evidence_required` with **no setup at all** — where a real engineer would author
  a balanced compromise.

---

## Gap 1 — No vehicle model

**Evidence.** `data/car_specs.json` holds `power_hp, weight_kg, torque_kgfm, pp_rating,
category, aspiration` for 579 cars (RSR = 509 hp / 1243 kg / Gr.3). `build_baseline_setup`
(`strategy/setup_baseline.py:460-474`) receives only `car, ranges, drivetrain, num_gears,
profile, …`. Power/weight/torque are used **only** to build prompt text
(`strategy/ai_planner.py:1685-1710`, `driving_advisor.py:3248`). No `Vehicle`/`CarModel`
class exists (grep: none). Drivetrain gates the front diff only; `num_gears` drives the gear
sequence; ranges clamp.

**Why it blocks engineering.** An engineer reasons from the car's dynamics: a rear-engined
Porsche is entry-understeer / power-oversteer prone and front-limited on the brakes; a
high power-to-weight car needs traction and gearing priority. None of that is available to
the authoring code, so the RR Porsche is tuned like a generic mid-engine car.

**Root cause.** The car is a label, not a model; dynamics-relevant specs never enter the
authoring signature.

**Correct design.** A pure `VehicleModel` built from the existing specs (drivetrain →
engine location; power_hp/weight_kg → power-to-weight; category) exposing *dynamic
tendencies* (balance tendency, traction priority, braking limitation) that authoring can
reason over. **Implemented** in `strategy/setup_engineering.py`.

## Gap 2 — Track evidence collapses to one aero knob

**Evidence.** `TrackTuneProfile` (`strategy/track_tune_profile.py:35-67`) computes
`lap_length_m, corner_count, corner_density_per_km, longest_straight_m, straight_fraction,
elevation_change_m` — then setup authoring reads only `aero_bias`, `trustworthy`,
`summary()` (`setup_baseline.py:575-581`). `aero_bias ∈ {trim,neutral,add}` moves only
`aero_front/rear` by ±25/50. Elevation is stored and read by nothing. Gearing takes **no**
track input (`_build_gearbox_changes(ranges, num_gears, locked_fields)`,
`setup_baseline.py:234`) despite the docstring claiming it shapes "aero/gearing to the
circuit". Fuji vs a twisty circuit differ **only** in aero.

**Why it blocks engineering.** Gearing to the longest straight, ride-height/rake for
elevation and kerbs, and ARB balance for corner type are first-order engineering
decisions. Ignoring them means two very different circuits get the same mechanical setup.

**Root cause.** A rich profile is distilled to a single categorical before it reaches
authoring; the other characteristics are dropped.

**Correct design.** Map the *retained* characteristics into coupled field intents:
straight fraction → gearing + drag; corner density → aero + ARB + mechanical grip;
elevation → ride-height margin. **Implemented** in `strategy/setup_engineering.py`
(gearing via a new `final_drive_bias` into `_build_gearbox_changes`).

## Gap 3 — Driver profile is a thin cosmetic layer

**Evidence.** `DriverProfile` = 8 booleans from substring-matching hardcoded prose
(`strategy/setup_driver_profile.py:51-162`). Only `_PROFILE_BIAS_TABLE`
(`setup_baseline.py:129-141`) turns them into values — fixed one-click nudges in the
baseline path only. `race_values_consistency (+2 lsd_decel)` and `rotation_without_snap
(-2 lsd_decel)` **cancel** for this driver. On the telemetry path the profile changes **no
value** — only confidence/ranking + one `lsd_accel` veto (`setup_rule_engine.py:966-982`).

**Why it blocks engineering.** "This driver wants front bite and a planted rear" should be
a strong authoring input that resolves ambiguous trade-offs, not a ±1 tiebreaker.

**Root cause.** The profile is additive metadata, not a first-class authoring input scaled
to the decision.

**Correct design — DELIVERED (`strategy/driver_fit.py`).** Each preference is a DIRECTION +
a COMFORT THRESHOLD (fraction of the car's range); the nudge fires only when the current
value actively VIOLATES the preference, scaled by how far past the threshold it sits, by
strength, and by the field's range — and is ZERO once the car is on the driver's side (don't
fix what fits). Opposing preferences net-resolve into a comfort band (e.g. rotation-without-
snap vs consistency on the braking diff). Wired into baseline/discipline authoring (against
the neutral seed; proven-history-seeded fields are excluded so it never double-counts a
validated value) AND the telemetry path (composed into the balance set for fields the solver
neither moved nor deferred; plus an advisory `driver_fit_reasoning` surface). This closes the
"zero on the telemetry path" finding.

## Gap 4 — No objective functions (Base/Quali/Race are a delta table)

**Evidence.** Discipline differentiation is `_SESSION_BIAS_TABLE`
(`setup_baseline.py:415-428`) — fixed per-field offsets added to the neutral seed. No
function scores a candidate against "minimise total race time" or "max one-lap grip".
`setup_authoring.py` only attaches human-readable justifications
(`_OBJECTIVE_FIELD_REASON`, `:177-197`). `tyre_wear_multiplier`/`car_class` are accepted
and unused (`setup_baseline.py:502-506`). Race total-race-time reasoning lives only in the
Strategy Brain and never touches setup values (`race_time_reasoning.py:11-12` "authors NO
setup values").

**Why it blocks engineering.** A race setup that ignores tyre longevity and fuel is not a
race setup. Qualifying = race + offsets is theatre, not one-lap optimisation.

**Root cause.** Objectives are encoded as static offset tables, not as scoring the setup
against a discipline goal.

**Correct design.** Make the objective a first-class input to the engineering layer:
qualifying favours peak grip/rotation and ignores tyre wear; race favours traction,
consistency, tyre protection (esp. the RR rear) and drag/fuel. **Implemented** — objective
shapes the engineering intents (e.g. race protects the RR rear tyre, quali sharpens).

## Gap 5 — No coupling (parameter independence)

**Evidence.** Each rule authors one field (`setup_rule_engine.py:689-789`); nothing
cascades. `setup_arbitration.py` only *flags* whether ≥2 already-proposed aero/ARB changes
compound on the front/rear axis ("authors NO setup values", `:12`).

**Why it blocks engineering.** Changing rear LSD/aero without also reviewing rear toe, ARB,
ride height is not how a car is built. Systems interact.

**Root cause.** A single-field rule engine with post-hoc conflict flagging, no systems
model.

**Correct design.** Engineering intents carry `couples_with` links and a coupling pass
emits the cascade (e.g. rear-traction intent → rear-toe-in for stability under power).
**Implemented (foundation)** in `strategy/setup_engineering.py`.

## Gap 6 — Defer-instead-of-engineer on multi-complaint feedback

**Evidence.** Multiple complaints collapse to one `dominant`
(`setup_diagnosis._derive_dominant_problem`, `issues[0]`); per-field safety
contraindications empty `_plan.proposed`; the coherence gate
(`driving_advisor.py:633-674`) then zeroes all changes to `evidence_required`. No
balanced-compromise authoring.

**Why it blocks engineering.** Entry understeer + mid push + power oversteer + rear-brake
instability is a *coherent balance problem* an engineer solves with a coordinated set
(free the front in, plant the rear out, move brake bias, protect the rears) — not "come
back with more evidence."

**Root cause.** Isolated single-field safety gating with no whole-car compromise layer, and
a coherence gate that treats "no single dominant fix" as "no setup".

**Correct design — DELIVERED (`strategy/setup_balance_solver.py`).** Given the confirmed
complaint set, `solve_balance` authors a conservative coordinated compromise: free the
front (soften front bar, front toe-out, more front aero), plant the rear (more rear aero
+ toe-in, softer rear bar), move brake bias forward — with a trade-off note and a test
protocol. It respects every safety invariant it knows about (brake bias only forward under
instability; LSD accel never increased when the rear is loose — left to a test; ambiguous
LSD braking left to a test). The moves flow through the SAME
`validate_setup_engineering_structured` funnel and Apply gate, and the result is a new
apply-eligible `balance_recommendation` status, honestly framed as a *balance change to
test*. Wired into `build_combined_setup_response`: when ≥2 conflicting complaints would
otherwise defer to `evidence_required`/partial, the app now authors a real setup instead.

---

## Priority & delivery

| # | Gap | Leverage | This increment |
|---|-----|----------|----------------|
| 1 | No vehicle model | High | **Done** — `VehicleModel` |
| 2 | Track → one aero knob | **Highest** | **Done** — track drives gearing, ride-height, ARB, balance |
| 4 | No objective functions | High | **Done (reasoning)** — objective shapes intents |
| 5 | No coupling | High | **Foundation** — intent `couples_with` + cascade |
| 3 | Thin driver layer | Medium | **Done** — evidence-scaled driver-fit, reaches the telemetry path |
| 6 | Defer instead of engineer | High | **Done** — balance solver authors a coordinated setup |

The implementation is `strategy/setup_engineering.py` (pure, first-principles, direction +
reason + coupling + evidence, conservatively bounded, safety-clamped through the existing
pipeline). It is wired into the deterministic baseline/discipline authoring — it authors no
value the range/legality validators would not, calls no AI, and never auto-applies.

## Per-corner authoring — DELIVERED (`strategy/corner_profile.py`)

Adds resolution beyond corner *density*: `load_reviewed_segments` merges the track's
reviewed per-corner segment files (corner entry/apex/exit windows + direction, plus
car-behaviour zones — kerb/bump, braking, traction, limiter), and `build_corner_profile`
derives the corner character. **Honesty:** the shipped per-corner data has NO speed/radius,
so the tight-vs-open window-width ratio is kept for *reporting only* — the layer authors
only on the RELIABLE signals: **kerb load** (→ ride-height margin + front compliance),
**braking zones** (→ front support under braking), **traction zones / traction-limited
exits** (→ rear downforce for drive-off). Confidence is capped at MEDIUM (a proxy) and the
per-corner note is surfaced. Wired into the engineering layer (it supersedes the coarse
corner-density mechanical-grip heuristic when present). Real result: Fuji's 24 detected
kerb/bump zones now lift ride height and soften the front spring for compliance.
