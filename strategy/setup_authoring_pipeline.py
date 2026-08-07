"""The ONE from-scratch setup authoring path (pure, Qt-free) — UAT 2026-08-07 A6, A10.

Three places used to author "the same" base setup from different inputs:

  * ``driving_advisor.build_baseline_setup_response`` — the full chain: proven library,
    personal history, engineering intents, chassis seeds, the spring-frequency model,
    driver fit, the anchor, and confidence-gated synthesis;
  * ``setup_authoring.author_full_field_plan`` — the same generator with NONE of the
    chassis seeds, proven seeds, proven gearbox, spring model or anchor. This is what
    fills the Base/Qualifying/Race comparison table, which is why the table disagreed
    with the sheet that actually got applied (camber front 1.0 shown, 2.3 applied);
  * ``ui/setup_builder_ui.py`` — a third, barer call still.

This module is that one path. Everything above now composes ``build_enriched_baseline``,
so the comparison table and the applied sheet are the same numbers by construction
rather than by coincidence.

It also replaces the nine silent ``except Exception: pass`` blocks that used to wrap
the enrichment layers (defect A10). A run where the driver profile, history, proven
library, chassis seeds and spring model all failed was indistinguishable in the
response from a fully-enriched run. Every layer now records a :class:`Degradation`
saying what was lost and what the setup fell back to, and the result carries them so
the Garage can render "I built this without your history, without the proven library
and without a spring model" instead of nothing at all.

Pure: no Qt, no network, no AI, no wall-clock, no randomness. Never raises — a failing
layer degrades the setup and says so; it does not take the response down with it.
"""
from __future__ import annotations

from dataclasses import dataclass, field as _dc_field
from typing import Optional


@dataclass(frozen=True)
class Degradation:
    """One enrichment layer that did not run, and what that costs the setup."""
    layer: str            # short machine key, e.g. "proven_library"
    label: str            # human name of the layer
    impact: str           # what the setup lost
    fallback: str         # what it used instead
    detail: str = ""      # exception text, when there was one

    def as_json(self) -> dict:
        return {"layer": self.layer, "label": self.label, "impact": self.impact,
                "fallback": self.fallback, "detail": self.detail}

    def sentence(self) -> str:
        return f"{self.label}: {self.impact} — {self.fallback}."


class _Degradations:
    """Collector. ``record`` on failure, ``note_absent`` when a layer had nothing to
    contribute (missing evidence is not the same as a broken layer, and the driver
    should be able to tell them apart)."""

    def __init__(self) -> None:
        self._failed: list = []
        self._absent: list = []

    def record(self, layer: str, label: str, impact: str, fallback: str,
               exc: BaseException | None = None) -> None:
        self._failed.append(Degradation(
            layer=layer, label=label, impact=impact, fallback=fallback,
            detail=(f"{type(exc).__name__}: {exc}" if exc is not None else "")))

    def note_absent(self, layer: str, label: str, impact: str, fallback: str) -> None:
        self._absent.append(Degradation(layer=layer, label=label, impact=impact,
                                        fallback=fallback))

    @property
    def failed(self) -> tuple:
        return tuple(self._failed)

    @property
    def absent(self) -> tuple:
        return tuple(self._absent)

    def as_json(self) -> dict:
        return {"failed": [d.as_json() for d in self._failed],
                "absent": [d.as_json() for d in self._absent],
                "headline": self.headline()}

    def headline(self) -> str:
        """One sentence for the top of the Garage sheet, or "" when nothing degraded."""
        if self._failed:
            names = ", ".join(d.label for d in self._failed)
            return (f"Built WITHOUT {names} — a layer failed, so this setup is less "
                    f"informed than it should be. Worth a look at the log.")
        if self._absent:
            names = ", ".join(d.label for d in self._absent)
            return f"Built without {names} — no data for them yet, which is expected."
        return ""


@dataclass(frozen=True)
class BaselineInputs:
    """Everything the one authoring path needs. Only ``car`` and ``ranges`` are
    required; every other field has an honest neutral default so a bare context still
    authors deterministically instead of inventing evidence."""
    car: str
    ranges: dict
    session_type: str = "Race"
    drivetrain: str = ""
    num_gears: int = 0
    profile: object = None
    allowed_tuning: Optional[list] = None
    tuning_locked: bool = False
    car_class: str = ""
    duration_mins: float = 0.0
    tyre_wear_multiplier: Optional[float] = None
    track_profile: object = None
    track_name: str = ""
    layout_id: str = ""
    historical_setups: Optional[list] = None
    #: A pre-built history prior (field -> {value, tier, source}). When supplied it is
    #: used as-is and ``historical_setups`` is not re-derived — callers that already
    #: resolved the prior (setup_authoring's context) must not have it silently dropped.
    history_prior: Optional[dict] = None
    front_weight_dist_override: Optional[float] = None
    ballast_kg: float = 0.0
    ballast_position: float = 0.0
    current_setup: Optional[dict] = None

    def objective(self) -> str:
        from strategy.setup_authoring import objective_from_session_type
        return objective_from_session_type(self.session_type).value


@dataclass(frozen=True)
class EnrichedBaseline:
    """The authored setup plus every artefact the surfaces need, built ONCE."""
    raw_data: dict
    setup_fields: dict
    context: object = None            # SetupEngineeringContext
    synthesis: object = None          # SynthesisResult
    synthesis_primary: Optional[dict] = None
    anchor_set: object = None         # AnchorSet
    car_model: object = None          # CarParameterModel
    corner_profile: object = None
    engineering_reasoning: Optional[dict] = None
    driver_fit_reasoning: object = None
    history_prior: dict = _dc_field(default_factory=dict)
    history_seeds: dict = _dc_field(default_factory=dict)
    proven_seeds: dict = _dc_field(default_factory=dict)
    proven_gearbox: dict = _dc_field(default_factory=dict)
    degradations: object = None       # _Degradations
    resolved_drivetrain: str = ""

    def degradation_json(self) -> dict:
        return (self.degradations.as_json() if self.degradations is not None
                else {"failed": [], "absent": [], "headline": ""})


def build_enriched_baseline(inputs: BaselineInputs, *, profile=None) -> EnrichedBaseline:
    """Author the from-scratch baseline through every enrichment layer, once.

    ``profile`` lets a caller inject an already-resolved DriverProfile (the advisor
    resolves an evolved one from the DB); otherwise a fresh one is built.
    """
    deg = _Degradations()
    objective = inputs.objective()

    # ---- car parameter model: legal range / window / anchor / step per field -----
    car_model = None
    drivetrain = (inputs.drivetrain or "").strip()
    try:
        from data.car_parameter_model import resolve_parameter_model
        car_model = resolve_parameter_model(inputs.car, drivetrain=drivetrain)
        if not drivetrain and car_model.drivetrain:
            drivetrain = car_model.drivetrain
    except Exception as exc:
        deg.record("car_model", "the car data model",
                   "no per-car ranges, windows, anchors or step sizes",
                   "falling back to the generic global range table", exc)
    if car_model is not None and car_model.is_archetype_only:
        deg.note_absent("car_capture", "captured GT7 data for this car",
                        "no real slider limits, stock values, gear count or redline",
                        f"using {car_model.archetype} class defaults")

    # ---- driver profile ----------------------------------------------------------
    if profile is None:
        try:
            from strategy.setup_driver_profile import build_driver_profile
            profile = build_driver_profile()
        except Exception as exc:
            deg.record("driver_profile", "your driver profile",
                       "no personal-style shaping", "using a neutral profile", exc)

    # ---- personal history --------------------------------------------------------
    history_prior: dict = {}
    seed_overrides: dict = {}
    if inputs.history_prior:
        history_prior = dict(inputs.history_prior)
        try:
            from strategy.setup_history_intelligence import build_baseline_seed_overrides
            seed_overrides = build_baseline_seed_overrides(history_prior)
        except Exception as exc:
            seed_overrides = {}
            deg.record("history", "your setup history",
                       "the prior was resolved but could not be turned into seeds",
                       "starting from the class position instead", exc)
    elif inputs.historical_setups:
        try:
            from strategy.setup_history_intelligence import (
                find_historical_setups, build_historical_prior,
                build_baseline_seed_overrides,
            )
            matches = find_historical_setups(
                inputs.car, inputs.track_name, inputs.layout_id, inputs.session_type,
                inputs.historical_setups, car_category=inputs.car_class)
            history_prior = build_historical_prior(matches)
            seed_overrides = build_baseline_seed_overrides(history_prior)
        except Exception as exc:
            history_prior, seed_overrides = {}, {}
            deg.record("history", "your setup history",
                       "no seeding from setups you have already run",
                       "starting from the class position instead", exc)
    else:
        deg.note_absent("history", "your setup history",
                        "nothing recorded for this car at this track yet",
                        "starting from the class position")

    # ---- proven-setup library ----------------------------------------------------
    proven_seeds: dict = {}
    proven_gearbox: dict = {}
    try:
        from strategy.proven_setup_library import (
            find_proven_setup, split_seed_and_gearbox,
        )
        proven_fields = find_proven_setup(
            inputs.car, inputs.track_name, inputs.session_type)
        if proven_fields:
            proven_seeds, proven_gearbox = split_seed_and_gearbox(proven_fields)
        else:
            deg.note_absent("proven_library", "the proven-setup library",
                            "no vetted setup for this car at this track",
                            "starting from the class position")
    except Exception as exc:
        proven_seeds, proven_gearbox = {}, {}
        deg.record("proven_library", "the proven-setup library",
                   "a vetted setup for this car+track was not consulted",
                   "starting from the class position instead", exc)

    # ---- reviewed per-corner segments -------------------------------------------
    corner_profile = None
    try:
        from strategy.corner_profile import load_reviewed_segments, build_corner_profile
        loc = getattr(inputs.track_profile, "track_location_id", "") or ""
        lay = getattr(inputs.track_profile, "layout_id", "") or inputs.layout_id or ""
        segs = load_reviewed_segments(loc, lay)
        if segs:
            corner_profile = build_corner_profile(segs)
        else:
            deg.note_absent("corner_profile", "reviewed per-corner segments",
                            "no corner-specific shaping (kerbs, slow-corner density)",
                            "shaping from lap geometry only")
    except Exception as exc:
        corner_profile = None
        deg.record("corner_profile", "reviewed per-corner segments",
                   "no corner-specific shaping", "shaping from lap geometry only", exc)

    # ---- engineering intents + chassis seeds + spring model ----------------------
    eng_bias: dict = {}
    eng_lean: float = 0.0
    eng_reasoning: Optional[dict] = None
    chassis_seeds: dict = {}
    vehicle = None
    try:
        from strategy.setup_engineering import (
            build_vehicle_model, derive_engineering_intents, resolve_car_specs,
            coupling_report, derive_chassis_seeds,
        )
        specs = resolve_car_specs(inputs.car)
        vehicle = build_vehicle_model(inputs.car, drivetrain, inputs.num_gears, specs)
        plan = derive_engineering_intents(
            vehicle, inputs.track_profile, objective, profile,
            corner_profile=corner_profile)
        eng_bias = plan.bias()
        eng_lean = plan.final_drive_lean
        eng_reasoning = plan.as_json()
        eng_reasoning["coupling"] = coupling_report(plan)
        chassis_seeds = derive_chassis_seeds(vehicle, objective)
    except Exception as exc:
        eng_bias, eng_lean, eng_reasoning, chassis_seeds = {}, 0.0, None, {}
        deg.record("engineering_intents", "the engineering-reasoning layer",
                   "no vehicle+track+objective coupling (gearing lean, ride-height "
                   "for elevation, ARB balance, rear-engine stability)",
                   "the class position stands unshaped", exc)

    # The spring model is separate: it fails in a way that MATTERS differently. It
    # returns the flat neutral constants with an "insufficient data" reason when the
    # car has no weight/category/drivetrain data, and those used to be written and
    # then labelled "engineered for car + track + objective" (defect A9). Take it only
    # when it modelled something, and say so when it did not.
    try:
        from strategy.setup_engineering import derive_spring_frequencies
        front_wd = ((inputs.front_weight_dist_override / 100.0)
                    if inputs.front_weight_dist_override else None)
        freq = derive_spring_frequencies(
            vehicle, objective, inputs.track_profile, front_wd,
            ballast_kg=inputs.ballast_kg, ballast_position=inputs.ballast_position)
        modelled = False
        for side, hz, reason in (("springs_front", freq.front_hz, freq.front_reason),
                                 ("springs_rear", freq.rear_hz, freq.rear_reason)):
            low = str(reason).lower()
            if "insufficient data" in low or "neutral fallback" in low:
                continue
            chassis_seeds[side] = hz
            modelled = True
        if not modelled:
            deg.note_absent("spring_model", "the spring-frequency model",
                            "no weight distribution or class data for this car, so "
                            "spring rates are not physics-derived",
                            "using the class spring band instead")
    except Exception as exc:
        deg.record("spring_model", "the spring-frequency model",
                   "spring rates are not physics-derived",
                   "using the class spring band instead", exc)

    # ---- evidence-scaled driver fit ---------------------------------------------
    driver_fit_reasoning = None
    try:
        from strategy.driver_fit import (
            derive_driver_fit, driver_fit_bias, driver_fit_reasoning as _dfr,
        )
        from strategy.setup_baseline import NEUTRAL_SEEDS
        intents = [i for i in derive_driver_fit(profile, NEUTRAL_SEEDS, inputs.ranges)
                   if i.field not in (seed_overrides or {})]
        for f, d in driver_fit_bias(intents).items():
            eng_bias[f] = eng_bias.get(f, 0.0) + d
        if intents:
            driver_fit_reasoning = _dfr(profile, intents)
    except Exception as exc:
        driver_fit_reasoning = None
        deg.record("driver_fit", "driver-style fitting",
                   "the base is not tailored toward your stated style",
                   "using the unfitted class position", exc)

    # ---- the anchor: where every field STARTS ------------------------------------
    anchor_set = None
    anchor_seeds: dict = {}
    anchor_tiers: dict = {}
    try:
        from strategy.setup_anchor import resolve_anchor, TIER_GENERIC
        anchor_set = resolve_anchor(
            inputs.car, inputs.track_name, objective, ranges=inputs.ranges,
            history_prior=history_prior, proven_fields=proven_seeds or None,
            drivetrain=drivetrain, parameter_model=car_model)
        # A GENERIC anchor is the midpoint of a legal range — the absence of a
        # position. Seeding from it would only relabel the old behaviour.
        anchor_seeds = {f: a.value for f, a in anchor_set.anchors.items()
                        if a.tier != TIER_GENERIC}
        anchor_tiers = {f: a.tier for f, a in anchor_set.anchors.items()}
    except Exception as exc:
        anchor_set, anchor_seeds, anchor_tiers = None, {}, {}
        deg.record("anchor", "the anchor resolver",
                   "no starting position per field, so values walk from the midpoint "
                   "of a legal range",
                   "using the flat neutral seed table", exc)

    # ---- author the baseline ------------------------------------------------------
    from strategy.setup_baseline import build_baseline_setup
    raw_data = build_baseline_setup(
        inputs.car, inputs.ranges, drivetrain, inputs.num_gears,
        profile, inputs.allowed_tuning, inputs.tuning_locked,
        session_type=inputs.session_type,
        tyre_wear_multiplier=inputs.tyre_wear_multiplier,
        car_class=inputs.car_class,
        duration_mins=inputs.duration_mins,
        track_profile=inputs.track_profile,
        historical_seed_overrides=seed_overrides or None,
        engineering_bias=eng_bias,
        final_drive_lean=eng_lean,
        chassis_seed_overrides=chassis_seeds or None,
        proven_seed_overrides=proven_seeds or None,
        proven_gearbox=proven_gearbox or None,
        anchor_seed_overrides=anchor_seeds or None,
        anchor_tiers=anchor_tiers or None,
        field_steps=(car_model.steps() if car_model is not None else None),
        car_model=car_model,
    )
    plan = raw_data.get("gearbox_plan") or {}
    if not plan.get("authored") and plan.get("missing"):
        deg.note_absent(
            "gearbox", "gearbox evidence",
            "no gear ratios or final drive were authored — "
            + ", ".join(str(m) for m in plan["missing"]) + " unknown",
            str(plan.get("advice") or "keep the stock gearing"))
    setup_fields = dict(raw_data.get("setup_fields") or {})

    # ---- canonical context + confidence-gated synthesis --------------------------
    context = synthesis = synthesis_primary = None
    try:
        from strategy.setup_engineering_context import build_setup_engineering_context
        from strategy.setup_synthesis import (
            synthesize_setup, reconcile_synthesis_primary,
        )
        context = build_setup_engineering_context(
            car=inputs.car, objective=objective, ranges=inputs.ranges,
            drivetrain=drivetrain, num_gears=inputs.num_gears, profile=profile,
            allowed_tuning=inputs.allowed_tuning, tuning_locked=inputs.tuning_locked,
            track_profile=inputs.track_profile, corner_profile=corner_profile,
            history_prior=history_prior, duration_mins=inputs.duration_mins,
            tyre_wear_multiplier=inputs.tyre_wear_multiplier,
            car_class=inputs.car_class, current_setup=inputs.current_setup,
            track_name=inputs.track_name, proven_fields=proven_seeds or None)
        synthesis = synthesize_setup(context)
        synthesis_primary = reconcile_synthesis_primary(setup_fields, synthesis, context)
        if synthesis_primary.get("overrides") and car_model is not None:
            # Synthesis picks values inside the working window using the field's display
            # precision; snap them onto the car's real increment so it never authors a
            # number the slider cannot reach (defect A7).
            snapped = {}
            for f, v in synthesis_primary["overrides"].items():
                spec = car_model.spec(f)
                snapped[f] = spec.snap(v) if spec is not None else v
            synthesis_primary = dict(synthesis_primary)
            synthesis_primary["overrides"] = snapped
        if synthesis_primary.get("overrides"):
            _apply_overrides(raw_data, synthesis_primary["overrides"],
                             synthesis_primary.get("provenance") or {},
                             anchor_tiers)
            setup_fields = dict(raw_data.get("setup_fields") or {})
    except Exception as exc:
        context = synthesis = synthesis_primary = None
        deg.record("synthesis", "complete-setup synthesis",
                   "no coupled whole-car reasoning toward the objective",
                   "the field-by-field baseline stands", exc)

    return EnrichedBaseline(
        raw_data=raw_data, setup_fields=setup_fields, context=context,
        synthesis=synthesis, synthesis_primary=synthesis_primary,
        anchor_set=anchor_set, car_model=car_model, corner_profile=corner_profile,
        engineering_reasoning=eng_reasoning, driver_fit_reasoning=driver_fit_reasoning,
        history_prior=history_prior, history_seeds=seed_overrides,
        proven_seeds=proven_seeds,
        proven_gearbox=proven_gearbox, degradations=deg,
        resolved_drivetrain=drivetrain,
    )


def _apply_overrides(raw_data: dict, overrides: dict, provenance: dict,
                     anchor_tiers: Optional[dict] = None) -> None:
    """Write synthesis-authored values into the raw_data in place.

    Mirrors the previous ``_apply_synthesis_primary`` in driving_advisor: the change
    dict AND setup_fields both move, so the sheet and the change list never disagree.

    A synthesised value does NOT get promoted to ENGINEERED (UAT 2026-08-07 defect
    A9). Synthesis reasons over the working windows, and those windows come from the
    anchor — so a synthesised value resting on a class default is still resting on a
    class default, however sophisticated the reasoning on top. The field keeps the tier
    of the evidence underneath it. Marking it otherwise would relabel exactly the
    laundering this phase exists to remove.
    """
    fields = raw_data.setdefault("setup_fields", {})
    changes = raw_data.get("changes") or []
    by_field = {c.get("field"): c for c in changes if c.get("field")}
    tiers = anchor_tiers or {}
    for f, val in (overrides or {}).items():
        fields[f] = val
        ch = by_field.get(f)
        label = str(provenance.get(f, "synthesis"))
        tier = str((ch or {}).get("tier") or tiers.get(f) or "GENERIC")
        if ch is not None:
            ch["to"] = val
            ch["to_clamped"] = val
            ch["source_label"] = f"complete-setup synthesis ({label})"
            ch["tier"] = tier
        else:
            changes.append({
                "field": f, "setting": f, "from": val, "to": val, "to_clamped": val,
                "source_label": f"complete-setup synthesis ({label})",
                "tier": tier, "alignment": "aligned",
                "why": f"authored by complete-setup synthesis ({label})",
            })
    raw_data["changes"] = changes
