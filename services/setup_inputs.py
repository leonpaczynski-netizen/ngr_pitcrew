"""Gathering what the setup generators need, without a window (stage 2b).

``SetupBuilderMixin`` assembles these inputs from a mix of context builders, a JSON spec
file, the track domain and two combo boxes. Everything except the combo boxes was
already headless — it just lived on the mixin, so reaching it meant reaching through
``MainWindow``.

This rebuilds the same snapshot from the DB and config directly, replacing
``_build_setup_inputs``, ``_load_car_specs_for_current`` and
``_build_track_tune_profile_for_current``. The two combo reads (drivetrain, gear count)
come from the car's own specs instead, which is where the classic form got its
autofill from anyway.

Never raises: an input that cannot be resolved stays unknown rather than guessed, and
the generators already treat unknown as unknown.
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, Optional, Sequence, Tuple

from services.setup_service import SetupInputs


def _norm(v) -> str:
    return "" if v is None else str(v).strip()


def _car_specs(car: str) -> Dict[str, Any]:
    """The car's spec row from data/car_specs.json ({} when unknown)."""
    if not _norm(car):
        return {}
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "data", "car_specs.json")
    try:
        with open(path, encoding="utf-8") as fh:
            return dict((json.load(fh) or {}).get(car, {}) or {})
    except Exception:
        return {}


def _event_context(db, config: dict):
    """The canonical EventContext, built the same way the classic window builds it."""
    try:
        from data.event_context import build_event_context
        name = _norm((config or {}).get("active_event_id"))
        event = None
        if db is not None and name and hasattr(db, "get_event"):
            try:
                event = db.get_event(name)
            except Exception:
                event = None
        return build_event_context(
            event=event, strategy=(config or {}).get("strategy") or {},
            active_event_id=name or None)
    except Exception:
        return None


def _track_profile(event_ctx):
    """Track-shaped tuning profile, or None so the baseline stays track-neutral."""
    try:
        loc = _norm(getattr(event_ctx, "track_location_id", ""))
        lay = _norm(getattr(event_ctx, "layout_id", ""))
        if not loc or not lay:
            return None
        from data.track_intelligence import resolve_track_layout
        from data.track_model_alignment import (
            find_accepted_model_path, import_accepted_model_json,
        )
        from strategy.track_tune_profile import build_track_tune_profile
        accepted = None
        path = find_accepted_model_path(loc, lay)
        if path is not None:
            accepted = import_accepted_model_json(path)
        return build_track_tune_profile(loc, lay,
                                        seed_layout=resolve_track_layout(loc, lay),
                                        accepted_model=accepted)
    except Exception:
        return None


def _ranges(car: str):
    try:
        from strategy.setup_ranges import resolve_ranges
        return resolve_ranges(car)
    except Exception:
        return None


def _historical_setups(db, car: str, track: str) -> Tuple[dict, ...]:
    """Previously saved setups for this car+track, annotated with the driver's rating.

    Only PROVEN setups should influence a new one, and the rating is what makes a setup
    proven — so an unrated setup is carried without one rather than assumed good.
    """
    if db is None or not _norm(car) or not _norm(track):
        return ()
    setups = []
    try:
        if hasattr(db, "get_setups_for_car_track"):
            setups = list(db.get_setups_for_car_track(car, track) or [])
    except Exception:
        setups = []
    if not setups:
        return ()
    ratings: Dict[str, Any] = {}
    try:
        car_id = int(db.get_car_id(car) or 0) if hasattr(db, "get_car_id") else 0
        if car_id and hasattr(db, "get_recent_feedback"):
            for fb in (db.get_recent_feedback(car_id, track, limit=100) or []):
                sid, rating = fb.get("setup_id"), fb.get("rating")
                if sid and rating:
                    ratings.setdefault(sid, rating)
    except Exception:
        ratings = {}
    out = []
    for s in setups:
        row = dict(s)
        if not row.get("rating") and row.get("setup_id") in ratings:
            row["rating"] = ratings[row["setup_id"]]
        out.append(row)
    return tuple(out)


def build_setup_inputs(db=None, config: Optional[dict] = None) -> SetupInputs:
    """Everything the setup generators need, from the DB + config. Never raises."""
    try:
        return _build(db, config or {})
    except Exception:  # pragma: no cover - defensive
        return SetupInputs()


def _build(db, config: dict) -> SetupInputs:
    ev = _event_context(db, config)
    car = _norm(getattr(ev, "car", "")) or _norm((config.get("strategy") or {}).get("car"))
    track = _norm(getattr(ev, "track", "")) or _norm((config.get("strategy") or {}).get("track"))
    layout = _norm(getattr(ev, "layout_id", ""))

    specs = _car_specs(car)
    snapshot = None
    try:
        from data.analysis_inputs import build_setup_inputs as _freeze
        snapshot = _freeze(event_context=ev, legacy_strategy=config.get("strategy") or {})
    except Exception:
        snapshot = None

    def _snap(attr, default=None):
        return getattr(snapshot, attr, default) if snapshot is not None else default

    allowed = None
    try:
        if snapshot is not None and hasattr(snapshot, "allowed_tuning_or_none"):
            allowed = snapshot.allowed_tuning_or_none()
    except Exception:
        allowed = None

    compounds = ""
    try:
        if snapshot is not None and hasattr(snapshot, "mandatory_compounds_str"):
            compounds = _norm(snapshot.mandatory_compounds_str)
    except Exception:
        compounds = ""

    # The classic form read drivetrain and gear count from two combos that its own car
    # autofill had populated from these specs — so read the specs directly.
    drivetrain = _norm(specs.get("drivetrain"))
    try:
        num_gears = int(specs.get("num_gears") or 0)
    except (TypeError, ValueError):
        num_gears = 0

    return SetupInputs(
        car=car, track=track, layout=layout,
        car_specs=specs, car_class=_norm(specs.get("category")),
        drivetrain=drivetrain, num_gears=num_gears,
        ranges=_ranges(car),
        allowed_tuning=allowed,
        tuning_locked=bool(_snap("tuning_locked", False)),
        tyre_wear_multiplier=_snap("tyre_wear_multiplier"),
        fuel_multiplier=float(getattr(ev, "fuel_multiplier", 1.0) or 1.0),
        refuel_rate_lps=float(getattr(ev, "refuel_rate_lps", 0.0) or 0.0),
        duration_mins=float(_snap("duration_mins", 0) or 0),
        track_profile=_track_profile(ev),
        historical_setups=_historical_setups(db, car, track),
        mandatory_compounds=compounds,
    )
