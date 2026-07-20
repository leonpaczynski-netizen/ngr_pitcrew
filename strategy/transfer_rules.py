"""Transfer Rules — the visible, deterministic rules that govern knowledge transfer (Phase 23).

Every rule is a VISIBLE CONSTANT with an explanation of *why it exists* and *what authority
supports it*. Nothing here infers beyond these rules. It also derives a car's engineering
attributes (manufacturer / drivetrain / layout / category) deterministically from the GT7 car
name via visible maps — an unknown attribute stays "unknown" (never guessed).

Purity: Qt-free, DB-free, UI-free, network-free, AI-free; no random, no wall-clock; no ML /
optimisation; deterministic; never raises.
"""
from __future__ import annotations

from typing import Mapping, Tuple

TRANSFER_RULES_VERSION = "transfer_rules_v1"

# --------------------------------------------------------------------------- #
# Car engineering attributes derived from the GT7 car name (all VISIBLE maps).
# GT7 car names begin with the manufacturer; class/drivetrain are keyword-encoded.
# Precedence for drivetrain: explicit registry > keyword > unknown.
# --------------------------------------------------------------------------- #

# Explicit per-car drivetrain registry (mirrors the setup-brain override; extend as needed).
CAR_DRIVETRAIN_REGISTRY = {
    "porsche 911 rsr (991) '17": "rr",
}

# Drivetrain -> engine layout (deterministic). fr=front-engine RWD, mr=mid, rr=rear, ff/awd.
DRIVETRAIN_LAYOUT = {
    "fr": "front_engine", "ff": "front_engine", "mr": "mid_engine",
    "rr": "rear_engine", "awd": "all_wheel",
}

# Car-name keyword -> drivetrain (used only when the registry has no explicit entry).
DRIVETRAIN_KEYWORDS = {
    "rr": ("911", "rsr", "cayman gt4 clubsport"),
    "mr": ("mclaren", "mclaren f1", " mr", "ferrari 458", "lamborghini", "ford gt"),
    "fr": ("gt-r nismo gt3", "amg gt3", "mustang", "corvette"),
    "awd": ("gt-r ", "quattro", "impreza", "lancer evolution"),
}

# Car-name keyword -> race category (gr1/gr2/gr3/gr4/road).
CATEGORY_KEYWORDS = {
    "gr3": ("gr.3", "gr3", "rsr", "gt3", " gt3"),
    "gr4": ("gr.4", "gr4", "gt4", "clubsport"),
    "gr1": ("gr.1", "gr1", "lmp", "vgt", "919 hybrid"),
    "gr2": ("gr.2", "gr2", "super gt", "nsx gt500"),
    "road": ("road car", "'15", "'16"),
}


def _lc(v) -> str:
    return str(v if v is not None else "").strip().lower()


def car_attributes(car_name) -> dict:
    """Derive {manufacturer, drivetrain, layout, category} from a GT7 car name deterministically.
    Unknown attributes are returned as 'unknown' (never guessed). Never raises."""
    name = _lc(car_name)
    if not name:
        return {"manufacturer": "unknown", "drivetrain": "unknown", "layout": "unknown",
                "category": "unknown"}
    manufacturer = name.split()[0] if name.split() else "unknown"
    drivetrain = CAR_DRIVETRAIN_REGISTRY.get(name, "")
    if not drivetrain:
        drivetrain = next((dt for dt, kws in DRIVETRAIN_KEYWORDS.items()
                           if any(kw in name for kw in kws)), "unknown")
    layout = DRIVETRAIN_LAYOUT.get(drivetrain, "unknown")
    category = next((cat for cat, kws in CATEGORY_KEYWORDS.items()
                     if any(kw in name for kw in kws)), "unknown")
    return {"manufacturer": manufacturer, "drivetrain": drivetrain, "layout": layout,
            "category": category}


def _major_version(v) -> str:
    s = _lc(v)
    return s.split(".")[0] if s else ""


# --------------------------------------------------------------------------- #
# Transfer rules — each: id, description (why it exists), authority (what supports it),
# and a predicate over (source_attrs, target_attrs, source_ctx, target_ctx).
# --------------------------------------------------------------------------- #
def _same_known(a: str, b: str) -> bool:
    return bool(a) and a != "unknown" and a == b


TRANSFER_RULES = (
    {"id": "same_manufacturer",
     "why": "cars from the same manufacturer tend to share design philosophy and component "
            "families, so a proven engineering behaviour is more likely to recur",
     "authority": "Phase 18 campaign identity (car) + Phase 22 domain knowledge",
     "predicate": lambda s, t, sc, tc: _same_known(s["manufacturer"], t["manufacturer"])},
    {"id": "same_drivetrain",
     "why": "drivetrain (RR/MR/FR/AWD) governs weight distribution and load transfer, which "
            "most handling knowledge depends on",
     "authority": "setup-brain drivetrain registry + Phase 12 vehicle dynamics",
     "predicate": lambda s, t, sc, tc: _same_known(s["drivetrain"], t["drivetrain"])},
    {"id": "same_layout",
     "why": "engine layout (front/mid/rear) sets the fundamental balance a suspension setup "
            "works around",
     "authority": "derived from drivetrain + Phase 12 vehicle dynamics",
     "predicate": lambda s, t, sc, tc: _same_known(s["layout"], t["layout"])},
    {"id": "same_race_category",
     "why": "same race category (Gr.3/Gr.4/...) implies comparable aero, tyre and regulation "
            "envelopes",
     "authority": "car category + BOP regulation context",
     "predicate": lambda s, t, sc, tc: _same_known(s["category"], t["category"])},
    {"id": "same_suspension_architecture",
     "why": "same manufacturer AND same category is a proxy for a shared suspension "
            "architecture (double-wishbone geometry etc.)",
     "authority": "manufacturer + category (proxy) — no explicit geometry catalogue",
     "predicate": lambda s, t, sc, tc: (_same_known(s["manufacturer"], t["manufacturer"])
                                        and _same_known(s["category"], t["category"]))},
    {"id": "compatible_gt7_version",
     "why": "a different GT7 major version can change physics / BOP, weakening any transfer",
     "authority": "GT7 version context (Phase 1 canonical context key)",
     "predicate": lambda s, t, sc, tc: bool(_major_version(sc.get("gt7_version"))
                                            ) and _major_version(sc.get("gt7_version"))
                                        == _major_version(tc.get("gt7_version"))},
    {"id": "same_driver",
     "why": "driver-technique knowledge is driver-specific; it only transfers to the same driver",
     "authority": "Phase 1 canonical context key (driver)",
     "predicate": lambda s, t, sc, tc: _same_known(_lc(sc.get("driver")), _lc(tc.get("driver")))},
)


def evaluate_rules(source_attrs: Mapping, target_attrs: Mapping,
                   source_ctx: Mapping, target_ctx: Mapping) -> dict:
    """Evaluate every visible transfer rule; return {rule_id: bool} + the satisfied list.
    Deterministic; never raises."""
    s = dict(source_attrs or {})
    t = dict(target_attrs or {})
    sc = dict(source_ctx or {})
    tc = dict(target_ctx or {})
    results = {}
    for rule in TRANSFER_RULES:
        try:
            results[rule["id"]] = bool(rule["predicate"](s, t, sc, tc))
        except Exception:
            results[rule["id"]] = False
    return results


def rule_catalogue() -> Tuple[dict, ...]:
    """The visible rule catalogue (id / why / authority) — no predicates, for display/audit."""
    return tuple({"id": r["id"], "why": r["why"], "authority": r["authority"]}
                 for r in TRANSFER_RULES)


# --------------------------------------------------------------------------- #
# Domain transferability classes — how a domain's knowledge relates to car architecture.
# --------------------------------------------------------------------------- #
# ARCHITECTURE_DEPENDENT : transfers when the cars share architecture (mfr+category+drivetrain).
# HANDLING_DRIVETRAIN    : transfers primarily on shared drivetrain + layout (balance behaviour).
# CAR_TRACK_SPECIFIC     : e.g. gearbox final-drive — car/track specific; does NOT transfer
#                          unless explicitly supported by shared evidence.
# CONTEXT_BOUND          : track/event specific — never transfers across cars.
# DRIVER_SPECIFIC        : transfers only to the same driver.
DOMAIN_TRANSFER_CLASS = {
    "suspension": "architecture_dependent", "springs": "architecture_dependent",
    "anti_roll_bars": "architecture_dependent", "dampers": "architecture_dependent",
    "ride_height": "architecture_dependent", "alignment": "architecture_dependent",
    "differential": "architecture_dependent", "aerodynamics": "architecture_dependent",
    "brake_balance": "architecture_dependent", "tyres": "architecture_dependent",
    "vehicle_balance": "handling_drivetrain", "weight_transfer": "handling_drivetrain",
    "gearbox": "car_track_specific",
    "track_segments": "context_bound", "track_surface": "context_bound", "fuel": "context_bound",
    "driver_technique": "driver_specific",
}

DOMAIN_CLASS_REASON = {
    "architecture_dependent": "this domain's behaviour is set by the car's mechanical "
                              "architecture, so it transfers only between architecturally similar "
                              "cars",
    "handling_drivetrain": "this handling behaviour follows from drivetrain and weight "
                           "distribution, so it transfers between cars sharing them",
    "car_track_specific": "gearing / final-drive knowledge is specific to a car and track and "
                          "does not transfer unless explicitly supported by shared evidence",
    "context_bound": "this knowledge is track / event specific and does not transfer across cars",
    "driver_specific": "driver-technique knowledge is specific to the driver and transfers only "
                       "to the same driver",
}


def domain_transfer_class(domain) -> str:
    return DOMAIN_TRANSFER_CLASS.get(_lc(domain), "architecture_dependent")


def transfer_versions() -> dict:
    return {"transfer_rules": TRANSFER_RULES_VERSION}
