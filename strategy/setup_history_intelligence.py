"""Phase 9 — historical successful-setup intelligence (pure, Qt-free).

Retrieves the driver's actual SUCCESSFUL setup *values* (not generic statements
like "prefers progressive throttle") and uses them as a weighted, transparent
prior: the recommendation engine can compare current / historical / recommended
per field and must EXPLAIN any material deviation from a proven value.

Evidence-honest and safe:
  * "successful" = the driver rated the setup ``liked`` (or it carries a strong
    result), never inferred.
  * a scope hierarchy (same car+track+layout > … > neutral) ranks matches; a
    weaker-scoped match never outranks a stronger one.
  * history NEVER overrides legality / safety validation, never invents a value,
    never forces a value against strong contradictory evidence, and never blindly
    copies a whole setup — it only informs and explains (the consumer applies the
    validators/Apply gate as always).

The module authors NO setup values and applies nothing.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

# Scope-hierarchy tiers (lower = stronger evidence).
TIER_SAME_CAR_TRACK_LAYOUT   = 1
TIER_SAME_CAR_SIMILAR_TRACK  = 2
TIER_SAME_CAR_DISCIPLINE     = 3
TIER_SAME_CATEGORY_TRACK     = 4
TIER_DRIVER_PREFERENCE       = 5
TIER_NEUTRAL                 = 6

_TIER_CONFIDENCE = {
    1: "high", 2: "medium", 3: "medium", 4: "low", 5: "low", 6: "none",
}

# Fields worth comparing against history (the levers a proven setup pins down).
_COMPARE_FIELDS = (
    "lsd_initial", "lsd_accel", "lsd_decel",
    "aero_front", "aero_rear", "arb_front", "arb_rear",
    "camber_front", "camber_rear", "toe_front", "toe_rear",
    "brake_bias", "final_drive",
)

# A recommendation that moves a field further than this (absolute) from a STRONG
# historical value is FLAGGED as needing explicit justification. Chosen to reflect
# a materially different setup decision, not a one-click nudge.
_DEVIATION_THRESHOLD = {
    "lsd_initial": 5, "lsd_accel": 5, "lsd_decel": 5,
    "aero_front": 50, "aero_rear": 50, "arb_front": 2, "arb_rear": 2,
    "camber_front": 0.5, "camber_rear": 0.5, "toe_front": 0.1, "toe_rear": 0.1,
    "brake_bias": 2, "final_drive": 0.15,
}


def _norm(s) -> str:
    import re
    return re.sub(r"\s+", " ", re.sub(r"\([^)]*\)", " ", str(s or ""))).strip().lower()


def _discipline(setup: dict) -> str:
    return str(setup.get("setup_type") or setup.get("session") or "").strip()


@dataclass(frozen=True)
class HistoricalSetup:
    """One retrieved historical setup with provenance."""
    label: str
    car: str
    track: str
    layout: str
    discipline: str
    values: dict
    rating: str
    result_quality: str
    scope_tier: int
    recency_rank: int
    confidence: str


@dataclass
class HistoricalFieldComparison:
    field: str
    current: Optional[float]
    historical: Optional[float]
    recommended: Optional[float]
    source: str
    tier: int
    confidence: str
    deviation_flagged: bool
    note: str


def _is_successful(setup: dict, rating_by_setup_id: Optional[dict]) -> bool:
    rating = str(setup.get("rating") or "").strip().lower()
    if not rating and rating_by_setup_id is not None:
        rating = str(rating_by_setup_id.get(setup.get("setup_id"), "") or "").strip().lower()
    if rating == "liked":
        return True
    rq = str(setup.get("result_quality") or "").strip().lower()
    return rq in ("win", "podium")


def find_historical_setups(
    car: str,
    track: str,
    layout: str,
    discipline: str,
    saved_setups: List[dict],
    *,
    rating_by_setup_id: Optional[dict] = None,
    similar_tracks: Optional[set] = None,
    car_category: str = "",
    only_successful: bool = True,
) -> List[HistoricalSetup]:
    """Return successful historical setups, scope-tagged and ranked (strongest scope
    first, then most recent). ``similar_tracks`` is an optional set of track names
    judged similar (e.g. from track_tune_profile characteristics)."""
    car_n = _norm(car)
    track_n = _norm(track)
    layout_n = _norm(layout)
    disc_n = _norm(discipline)
    cat_n = _norm(car_category)
    sim_n = {_norm(t) for t in (similar_tracks or set())}

    out: List[HistoricalSetup] = []
    for idx, s in enumerate(saved_setups or []):
        if only_successful and not _is_successful(s, rating_by_setup_id):
            continue
        s_car = _norm(s.get("name"))
        s_track = _norm(s.get("track"))
        s_layout = _norm(s.get("layout_id") or s.get("layout"))
        s_disc = _norm(_discipline(s))
        s_cat = _norm(s.get("car_category") or s.get("category"))

        tier: Optional[int] = None
        if car_n and s_car == car_n:
            if track_n and s_track == track_n and (not layout_n or s_layout == layout_n):
                tier = TIER_SAME_CAR_TRACK_LAYOUT
            elif s_track in sim_n:
                tier = TIER_SAME_CAR_SIMILAR_TRACK
            elif disc_n and s_disc == disc_n:
                tier = TIER_SAME_CAR_DISCIPLINE
            else:
                tier = TIER_SAME_CAR_DISCIPLINE  # same car is still strong evidence
        elif cat_n and s_cat == cat_n and (s_track == track_n or s_track in sim_n):
            tier = TIER_SAME_CATEGORY_TRACK
        else:
            continue  # unrelated car/track — not evidence for this session

        # Extract only recognised setup values.
        values = {k: s[k] for k in _COMPARE_FIELDS if k in s and isinstance(s[k], (int, float))}
        out.append(HistoricalSetup(
            label=str(s.get("setup_label") or s.get("name") or "setup"),
            car=str(s.get("name") or ""), track=str(s.get("track") or ""),
            layout=str(s.get("layout_id") or s.get("layout") or ""),
            discipline=_discipline(s), values=values,
            rating=str(s.get("rating") or ""), result_quality=str(s.get("result_quality") or ""),
            scope_tier=tier, recency_rank=idx,
            confidence=_TIER_CONFIDENCE.get(tier, "none"),
        ))

    out.sort(key=lambda h: (h.scope_tier, h.recency_rank))
    return out


def build_historical_prior(matches: List[HistoricalSetup]) -> Dict[str, dict]:
    """field -> {value, source, tier, confidence} using the strongest-scoped (then
    most recent) match that carries each field. Never merges across tiers per field."""
    prior: Dict[str, dict] = {}
    for h in matches:  # already sorted strongest-first
        for f, v in h.values.items():
            if f not in prior:
                prior[f] = {"value": float(v), "source": h.label,
                            "tier": h.scope_tier, "confidence": h.confidence,
                            "track": h.track, "discipline": h.discipline}
    return prior


# Fields where a STRONG proven prior should seed the from-scratch baseline. These
# are personal-fit handling geometry the driver has already validated at this
# car+track.
BASELINE_LIFT_FIELDS = frozenset({"camber_front", "camber_rear", "toe_front", "toe_rear"})

# Group 64 — the differential is also a personal-fit lever. A proven same-car LSD
# triplet is a legitimate STARTING WINDOW for the base setup (the driver has already
# validated how they like the diff), even from another track — track-specific demands
# and the discipline bias then adjust it. Aero, brakes, gearing and ride height stay
# with the deterministic/track-driven generator (they are track/strategy, not fit).
BASELINE_LSD_LIFT_FIELDS = frozenset({"lsd_initial", "lsd_accel", "lsd_decel"})

# The full default lift set: personal-fit geometry + differential.
BASELINE_LIFT_FIELDS_ALL = BASELINE_LIFT_FIELDS | BASELINE_LSD_LIFT_FIELDS


def build_baseline_seed_overrides(
    prior: Dict[str, dict],
    *,
    allowed_fields=BASELINE_LIFT_FIELDS_ALL,
    max_tier: int = TIER_SAME_CAR_SIMILAR_TRACK,
) -> Dict[str, dict]:
    """field -> {value, tier, source} for STRONG proven priors in the lift-allowed
    set, to seed the from-scratch baseline from geometry and the differential the
    driver has already validated instead of a generic neutral default.

    Group 64: the default lift set is personal-fit geometry (camber/toe) PLUS the LSD
    triplet (a proven same-car diff is a valid starting window). Aero, brakes, gearing
    and ride height are never lifted — they are track/strategy driven.

    Per-field scope gating: geometry (camber/toe) is track-sensitive and seeds only
    from a same-car same/similar-track prior (tier <= ``max_tier``, default 2). The LSD
    triplet is a personal-fit lever that transfers across tracks, so it also seeds from
    a same-car prior at ANOTHER track (tier <= TIER_SAME_CAR_DISCIPLINE=3) — a legitimate
    starting window that discipline/track demands then adjust. A weak/neutral prior
    (tier >= 4) never moves the base. Never invents a value; never touches a field
    outside ``allowed_fields``."""
    out: Dict[str, dict] = {}
    for f, d in (prior or {}).items():
        if f not in allowed_fields or not isinstance(d, dict):
            continue
        try:
            tier = int(d.get("tier", TIER_NEUTRAL))
        except (TypeError, ValueError):
            continue
        # LSD transfers across tracks (personal-fit); geometry does not.
        _field_max = (TIER_SAME_CAR_DISCIPLINE if f in BASELINE_LSD_LIFT_FIELDS
                      else max_tier)
        if tier > _field_max:
            continue
        try:
            value = float(d.get("value"))
        except (TypeError, ValueError):
            continue
        out[f] = {"value": value, "tier": tier, "source": str(d.get("source", ""))}
    return out


def compare_to_history(
    current_setup: dict,
    recommended_fields: dict,
    prior: Dict[str, dict],
) -> List[HistoricalFieldComparison]:
    """Per-field current / historical / recommended, flagging a recommendation that
    moves materially away from a STRONG (tier ≤ 2) historical value."""
    rows: List[HistoricalFieldComparison] = []
    for f in _COMPARE_FIELDS:
        if f not in prior:
            continue
        hist = prior[f]
        hv = hist["value"]
        cur = current_setup.get(f)
        rec = recommended_fields.get(f)
        cur_f = float(cur) if isinstance(cur, (int, float)) else None
        rec_f = float(rec) if isinstance(rec, (int, float)) else None
        # Flag: recommended exists, prior is strong, and the move from the proven
        # value exceeds the per-field threshold.
        flagged = False
        note = f"proven value {hv:g} ({hist['source']}, {hist['confidence']} confidence)"
        if rec_f is not None and hist["tier"] <= TIER_SAME_CAR_SIMILAR_TRACK:
            if abs(rec_f - hv) >= _DEVIATION_THRESHOLD.get(f, 1e9):
                flagged = True
                note = (f"recommended {rec_f:g} deviates from your proven {hv:g} "
                        f"({hist['source']}) — needs explicit justification")
        rows.append(HistoricalFieldComparison(
            field=f, current=cur_f, historical=hv, recommended=rec_f,
            source=hist["source"], tier=hist["tier"], confidence=hist["confidence"],
            deviation_flagged=flagged, note=note,
        ))
    return rows
