"""PracticeEvidenceBundle — the shared Practice → Strategy hand-off (pure).

Sprint 9 of the determinism rebuild. Before this, Practice Analysis produced a
report the driver had to mentally carry into Strategy; the two halves were only
coupled by a session id round-trip through SQLite, and a missing/wrong id
silently fell back to all-history. This module defines ONE explicit object that
Practice writes and Strategy reads automatically:

  * event/car/track/layout identity + race rules + fuel/tyre multipliers, refuel
    rate, mandatory stops, required compounds;
  * approved race-setup id + applied-in-GT7 checkpoint id;
  * measured evidence (RaceStrategyEvidence), per-compound tyre curves and
    crossovers, cross-lap issue patterns, driver feedback;
  * confidence, missing evidence, provenance (session ids, timestamps), and a
    deterministic change hash used for stale detection.

Strategy Builder consumes ``bundle.strategy_evidence`` directly — no manual
re-entry. ``detect_bundle_staleness`` flags when the setup, checkpoint,
multipliers, track, duration, or refuel rate have moved on since the bundle was
built. Pure: no Qt, no network. Never raises.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Optional, Tuple


def _hash_fields(fields: dict) -> str:
    """Deterministic short hash of the identity/config fields for staleness."""
    parts = []
    for k in sorted(fields):
        parts.append(f"{k}={fields[k]}")
    raw = "|".join(parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


@dataclass(frozen=True)
class PracticeEvidenceBundle:
    # ---- identity / rules ------------------------------------------------- #
    car_id: int
    car_name: str
    track: str
    layout_id: str
    race_laps: int = 0
    race_duration_minutes: float = 0.0
    fuel_multiplier: float = 0.0
    tyre_multiplier: float = 0.0
    refuel_rate_lps: float = 0.0
    mandatory_pit_stops: int = 0
    required_compounds: Tuple[str, ...] = ()
    # ---- setup linkage ---------------------------------------------------- #
    approved_setup_id: str = ""
    applied_checkpoint_id: str = ""
    setup_confirmed_in_gt7: bool = False
    # ---- evidence --------------------------------------------------------- #
    strategy_evidence: object = None        # RaceStrategyEvidence (consumed by strategy)
    compound_curves: dict = field(default_factory=dict)   # {compound: CompoundPerformanceCurve}
    crossovers: Tuple = ()                   # [TyreCrossover]
    cross_lap_patterns: Tuple = ()           # [IssuePersistenceResult]
    per_corner_observations: Tuple = ()
    driver_feedback: object = None
    # ---- provenance ------------------------------------------------------- #
    session_ids: Tuple[int, ...] = ()
    confidence: str = "none"
    missing_evidence: Tuple[str, ...] = ()
    built_at: str = ""
    change_hash: str = ""

    @property
    def is_ready_for_strategy(self) -> bool:
        """True when the bundle carries enough measured evidence to plan a race.

        Requires an evidence object with per-compound pace and a resolvable race
        length. The setup should also be confirmed applied in GT7 (surfaced
        separately so Strategy can warn rather than block).
        """
        ev = self.strategy_evidence
        if ev is None:
            return False
        has_len = (self.race_laps or 0) > 0 or (self.race_duration_minutes or 0) > 0
        has_pace = bool(getattr(ev, "compound_samples", None))
        return bool(has_len and has_pace)

    def compound_is_tested(self, compound: str) -> bool:
        c = self.compound_curves.get(compound)
        return bool(c and getattr(c, "tested", False))


def compute_bundle_change_hash(
    *, track: str, layout_id: str, race_laps: int, race_duration_minutes: float,
    fuel_multiplier: float, tyre_multiplier: float, refuel_rate_lps: float,
    approved_setup_id: str, applied_checkpoint_id: str,
) -> str:
    return _hash_fields({
        "track": track, "layout": layout_id, "laps": race_laps,
        "dur": round(float(race_duration_minutes or 0), 3),
        "fuel_mult": round(float(fuel_multiplier or 0), 4),
        "tyre_mult": round(float(tyre_multiplier or 0), 4),
        "refuel": round(float(refuel_rate_lps or 0), 4),
        "setup": approved_setup_id or "", "checkpoint": applied_checkpoint_id or "",
    })


def build_practice_evidence_bundle(
    *,
    session_result,                    # SessionEvidenceResult (has .evidence, .missing_evidence)
    car_id: int = 0,
    car_name: str = "",
    approved_setup_id: str = "",
    applied_checkpoint_id: str = "",
    setup_confirmed_in_gt7: bool = False,
    compound_curves: Optional[dict] = None,
    crossovers: Tuple = (),
    cross_lap_patterns: Tuple = (),
    per_corner_observations: Tuple = (),
    driver_feedback=None,
    session_ids: Tuple[int, ...] = (),
    built_at: str = "",
) -> PracticeEvidenceBundle:
    """Compose a bundle from an already-built SessionEvidenceResult + analyses.

    The measured evidence (laps, fuel, compound samples, rules, identity) comes
    straight from ``session_result.evidence`` so Strategy reads the same object
    Practice measured. Never raises.
    """
    ev = getattr(session_result, "evidence", None)

    def g(name, default=None):
        return getattr(ev, name, default) if ev is not None else default

    track = str(g("track", "") or "")
    layout_id = str(g("layout_id", "") or "")
    race_laps = int(g("race_laps", 0) or 0)
    race_dur = float(g("race_duration_minutes", 0.0) or 0.0)
    fuel_mult = float(g("fuel_multiplier", 0.0) or 0.0)
    tyre_mult = float(g("tyre_multiplier", 0.0) or 0.0)
    refuel = float(g("refuel_rate_lps", 0.0) or 0.0)
    mandatory = int(g("mandatory_pit_stops", 0) or 0)
    required = tuple(g("required_compounds", ()) or ())

    conf = getattr(session_result, "confidence", None)
    conf_str = getattr(conf, "value", None) or (str(conf) if conf is not None else "none")
    missing = tuple(getattr(session_result, "missing_evidence", ()) or ())

    change_hash = compute_bundle_change_hash(
        track=track, layout_id=layout_id, race_laps=race_laps,
        race_duration_minutes=race_dur, fuel_multiplier=fuel_mult,
        tyre_multiplier=tyre_mult, refuel_rate_lps=refuel,
        approved_setup_id=approved_setup_id, applied_checkpoint_id=applied_checkpoint_id,
    )

    return PracticeEvidenceBundle(
        car_id=int(car_id or g("car_id", 0) or 0), car_name=car_name,
        track=track, layout_id=layout_id, race_laps=race_laps,
        race_duration_minutes=race_dur, fuel_multiplier=fuel_mult,
        tyre_multiplier=tyre_mult, refuel_rate_lps=refuel,
        mandatory_pit_stops=mandatory, required_compounds=required,
        approved_setup_id=approved_setup_id, applied_checkpoint_id=applied_checkpoint_id,
        setup_confirmed_in_gt7=setup_confirmed_in_gt7,
        strategy_evidence=ev, compound_curves=dict(compound_curves or {}),
        crossovers=tuple(crossovers or ()), cross_lap_patterns=tuple(cross_lap_patterns or ()),
        per_corner_observations=tuple(per_corner_observations or ()),
        driver_feedback=driver_feedback, session_ids=tuple(session_ids or ()),
        confidence=conf_str, missing_evidence=missing, built_at=built_at,
        change_hash=change_hash,
    )


# Staleness reason codes -> human text.
_STALE_TEXT = {
    "setup_changed": "the approved setup changed since this practice",
    "checkpoint_changed": "a different setup was confirmed applied in GT7",
    "not_confirmed": "the setup was never confirmed as applied in GT7",
    "fuel_multiplier_changed": "the event fuel multiplier changed",
    "tyre_multiplier_changed": "the event tyre multiplier changed",
    "refuel_changed": "the refuel rate changed",
    "track_changed": "the track changed",
    "layout_changed": "the layout changed",
    "duration_changed": "the race duration/lap count changed",
    "newer_practice": "newer practice data is available",
}


def detect_bundle_staleness(
    bundle: PracticeEvidenceBundle,
    *,
    current_track: str = None,
    current_layout_id: str = None,
    current_race_laps: int = None,
    current_race_duration_minutes: float = None,
    current_fuel_multiplier: float = None,
    current_tyre_multiplier: float = None,
    current_refuel_rate_lps: float = None,
    current_approved_setup_id: str = None,
    current_applied_checkpoint_id: str = None,
    newer_practice_available: bool = False,
) -> Tuple[bool, Tuple[str, ...]]:
    """Return (is_stale, reason_codes). Only compares fields the caller supplies."""
    reasons: list[str] = []

    def changed(cur, was) -> bool:
        return cur is not None and cur != was

    if changed(current_track, bundle.track):
        reasons.append("track_changed")
    if changed(current_layout_id, bundle.layout_id):
        reasons.append("layout_changed")
    if changed(current_race_laps, bundle.race_laps) or \
            changed(current_race_duration_minutes, bundle.race_duration_minutes):
        reasons.append("duration_changed")
    if current_fuel_multiplier is not None and \
            abs(current_fuel_multiplier - bundle.fuel_multiplier) > 1e-9:
        reasons.append("fuel_multiplier_changed")
    if current_tyre_multiplier is not None and \
            abs(current_tyre_multiplier - bundle.tyre_multiplier) > 1e-9:
        reasons.append("tyre_multiplier_changed")
    if current_refuel_rate_lps is not None and \
            abs(current_refuel_rate_lps - bundle.refuel_rate_lps) > 1e-9:
        reasons.append("refuel_changed")
    if changed(current_approved_setup_id, bundle.approved_setup_id):
        reasons.append("setup_changed")
    if changed(current_applied_checkpoint_id, bundle.applied_checkpoint_id):
        reasons.append("checkpoint_changed")
    if not bundle.setup_confirmed_in_gt7:
        reasons.append("not_confirmed")
    if newer_practice_available:
        reasons.append("newer_practice")

    return (len(reasons) > 0, tuple(reasons))


def staleness_text(reason_codes) -> list:
    return [_STALE_TEXT.get(c, c) for c in (reason_codes or ())]
