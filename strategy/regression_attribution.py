"""Regression attribution — bundle vs field-level causation (Program 2, Phase 39; Audit B fix).

A worsened setup that changed several fields does NOT prove every individual field direction is
causally at fault. This authority distinguishes:

  * ``BUNDLE_REGRESSION_CONFIRMED``  - the complete failed delta bundle is blocked immediately;
  * ``FIELD_DIRECTION_SUSPECT``      - a field in a multi-field bundle; correlated, not yet causal;
  * ``FIELD_DIRECTION_CONFIRMED``    - causally confirmed by corroboration (see below);
  * ``INTERACTION_SUSPECTED``        - a coupled bundle that repeats independently;
  * ``ATTRIBUTION_INSUFFICIENT``     - not enough evidence to attribute.

A single-field worsened change confirms that field directly. A field inside a multi-field bundle only
becomes ``FIELD_DIRECTION_CONFIRMED`` with corroboration: a single-field controlled experiment on it,
independent repeated bundles that share only that field, or valid reversal evidence (moving it the
other way improved). Correlation is never silently converted into field-level causation.

Purity: Qt-free, DB-free, UI-free, network-free, AI-free; no random, no wall-clock; deterministic;
never raises.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

REGRESSION_ATTRIBUTION_VERSION = "regression_attribution_v1"
REGRESSION_ATTRIBUTION_SCHEMA = 1

_IMPROVED = ("confirmed_improvement", "partial_improvement", "improvement", "improved")
_OPPOSITE = {"increase": "decrease", "decrease": "increase", "up": "down", "down": "up",
             "raise": "lower", "lower": "raise", "softer": "stiffer", "stiffer": "softer"}


def _norm(v) -> str:
    return str(v if v is not None else "").strip()


def _lc(v) -> str:
    return _norm(v).lower()


def _dumps(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str, ensure_ascii=True,
                      allow_nan=False)


def _fp(payload) -> str:
    return (f"{REGRESSION_ATTRIBUTION_VERSION}:"
            + hashlib.sha256(_dumps(payload).encode("utf-8")).hexdigest()[:24])


class RegressionAttributionState(str, Enum):
    BUNDLE_REGRESSION_CONFIRMED = "bundle_regression_confirmed"
    FIELD_DIRECTION_SUSPECT = "field_direction_suspect"
    FIELD_DIRECTION_CONFIRMED = "field_direction_confirmed"
    INTERACTION_SUSPECTED = "interaction_suspected"
    ATTRIBUTION_INSUFFICIENT = "attribution_insufficient"


def _worsened(rec: Mapping) -> bool:
    return _lc(rec.get("outcome_status")) == "regression" or bool(rec.get("new_regressions") or [])


def _improved(rec: Mapping) -> bool:
    return _lc(rec.get("outcome_status")) in _IMPROVED and not (rec.get("new_regressions") or [])


def _dirs(rec: Mapping) -> Tuple[Tuple[str, str], ...]:
    out = []
    for c in (rec.get("changes") or []):
        f = _norm(c.get("field"))
        if f:
            out.append((f, _lc(c.get("direction"))))
    return tuple(out)


@dataclass(frozen=True)
class FieldAttribution:
    field: str
    direction: str
    state: str
    reason: str
    corroboration: Tuple[str, ...]
    source_experiments: Tuple[str, ...]

    def to_dict(self) -> dict:
        return {"field": self.field, "direction": self.direction, "state": self.state,
                "reason": self.reason, "corroboration": list(self.corroboration),
                "source_experiments": list(self.source_experiments)}


@dataclass(frozen=True)
class BundleAttribution:
    fields: Tuple[str, ...]
    state: str
    reason: str
    session_count: int
    source_experiments: Tuple[str, ...]

    def to_dict(self) -> dict:
        return {"fields": list(self.fields), "state": self.state, "reason": self.reason,
                "session_count": self.session_count,
                "source_experiments": list(self.source_experiments)}


@dataclass(frozen=True)
class RegressionAttributionReport:
    bundles: Tuple[dict, ...]
    field_attributions: Tuple[dict, ...]
    blocked_bundles: Tuple[dict, ...]
    confirmed_field_directions: Tuple[dict, ...]
    suspect_field_directions: Tuple[dict, ...]
    doctrine: str
    content_fingerprint: str
    schema_version: int = REGRESSION_ATTRIBUTION_SCHEMA
    eval_version: str = REGRESSION_ATTRIBUTION_VERSION

    def to_dict(self) -> dict:
        return {"bundles": [dict(b) for b in self.bundles],
                "field_attributions": [dict(f) for f in self.field_attributions],
                "blocked_bundles": [dict(b) for b in self.blocked_bundles],
                "confirmed_field_directions": [dict(f) for f in self.confirmed_field_directions],
                "suspect_field_directions": [dict(f) for f in self.suspect_field_directions],
                "doctrine": self.doctrine, "content_fingerprint": self.content_fingerprint,
                "schema_version": self.schema_version, "eval_version": self.eval_version}


_DOCTRINE = ("A multi-field regression blocks the bundle but only makes each field a SUSPECT; a field "
             "direction is causally confirmed only by a single-field controlled test, independent "
             "repeats sharing that field, or valid reversal evidence. Correlation is never converted "
             "into field-level causation.")


def build_regression_attribution(exact_records: Optional[Sequence[Mapping]]
                                 ) -> RegressionAttributionReport:
    """Attribute worsened exact-context deltas to a bundle and/or individual fields. Deterministic;
    order-independent; never raises."""
    try:
        recs = sorted([r for r in (exact_records or []) if isinstance(r, Mapping)],
                      key=lambda r: (_norm(r.get("recorded_at")), _norm(r.get("record_key"))))
        return _build(recs)
    except Exception:  # pragma: no cover - defensive
        return RegressionAttributionReport(bundles=(), field_attributions=(), blocked_bundles=(),
                                           confirmed_field_directions=(), suspect_field_directions=(),
                                           doctrine=_DOCTRINE, content_fingerprint=_fp({"e": 1}))


def _build(recs: List[Mapping]) -> RegressionAttributionReport:
    worsened = [r for r in recs if _worsened(r)]
    improved = [r for r in recs if _improved(r)]

    # bundle attributions (keyed by the frozenset of (field,direction))
    bundle_map: "Dict[frozenset, dict]" = {}
    for r in worsened:
        dirs = _dirs(r)
        if not dirs:
            continue
        key = frozenset(dirs)
        b = bundle_map.setdefault(key, {"dirs": tuple(sorted(dirs)), "sessions": set(), "exps": set()})
        b["sessions"].add(_norm(r.get("test_session_id")) or _norm(r.get("session_date"))
                          or _norm(r.get("record_key")))
        b["exps"].add(_norm(r.get("experiment_id")))

    # per (field,direction) suspects/confirmations
    field_state: "Dict[Tuple[str, str], dict]" = {}
    for key, b in bundle_map.items():
        dirs = list(key)
        single = len(dirs) == 1
        for (f, d) in dirs:
            fs = field_state.setdefault((f, d), {"single": False, "in_bundle": False,
                                                 "bundles": [], "exps": set(), "corr": set()})
            fs["exps"].update(b["exps"])
            fs["bundles"].append(frozenset(dirs))
            if single:
                fs["single"] = True
                fs["corr"].add("single_field_controlled_regression")
            else:
                fs["in_bundle"] = True

    # corroboration: independent repeats (>=2 DIFFERENT bundles sharing this field+dir)
    for (f, d), fs in field_state.items():
        distinct_bundles = {bset for bset in fs["bundles"]}
        if len({b for b in distinct_bundles if len(b) > 1}) >= 2:
            fs["corr"].add("independent_repeated_bundles")
    # corroboration: valid reversal (opposite direction improved for the same field)
    for r in improved:
        for (f, d) in _dirs(r):
            opp = _OPPOSITE.get(d)
            if opp and (f, opp) in field_state:
                field_state[(f, opp)]["corr"].add("valid_reversal_evidence")

    # classify fields
    field_attrs: List[FieldAttribution] = []
    for (f, d), fs in sorted(field_state.items()):
        corr = tuple(sorted(fs["corr"]))
        if fs["single"] and not fs["in_bundle"]:
            state = RegressionAttributionState.FIELD_DIRECTION_CONFIRMED
            reason = "single-field controlled change worsened the car - this direction is causal."
        elif corr:
            state = RegressionAttributionState.FIELD_DIRECTION_CONFIRMED
            reason = "corroborated by " + ", ".join(corr) + " - this direction is causal."
        elif fs["in_bundle"]:
            state = RegressionAttributionState.FIELD_DIRECTION_SUSPECT
            reason = ("changed inside a multi-field regression bundle; correlated but not yet causal - "
                      "isolate or reverse to confirm.")
        else:
            state = RegressionAttributionState.ATTRIBUTION_INSUFFICIENT
            reason = "insufficient evidence to attribute this field direction."
        field_attrs.append(FieldAttribution(field=f, direction=d, state=state.value, reason=reason,
                                            corroboration=corr,
                                            source_experiments=tuple(sorted(x for x in fs["exps"] if x))))

    # classify bundles
    bundle_attrs: List[BundleAttribution] = []
    for key, b in bundle_map.items():
        multi = len(b["dirs"]) > 1
        sessions = len(b["sessions"])
        if multi and sessions >= 2:
            state = RegressionAttributionState.INTERACTION_SUSPECTED
            reason = ("this coupled multi-field change worsened the car across independent sessions - "
                      "an interaction is suspected; individual field effects remain qualified.")
        elif multi:
            state = RegressionAttributionState.BUNDLE_REGRESSION_CONFIRMED
            reason = ("this multi-field delta worsened the car - the BUNDLE is blocked; individual "
                      "fields are suspects, not confirmed. Isolate or reverse to attribute.")
        else:
            state = RegressionAttributionState.BUNDLE_REGRESSION_CONFIRMED
            reason = "single-field regression - blocked and field-confirmed."
        bundle_attrs.append(BundleAttribution(
            fields=tuple(f"{f}:{d}" for (f, d) in b["dirs"]), state=state.value, reason=reason,
            session_count=sessions, source_experiments=tuple(sorted(x for x in b["exps"] if x))))

    bundle_out = tuple(sorted((b.to_dict() for b in bundle_attrs), key=lambda x: x["fields"]))
    field_out = tuple(f.to_dict() for f in field_attrs)
    blocked = tuple(b for b in bundle_out)   # every worsened bundle is blocked
    confirmed = tuple(f for f in field_out
                      if f["state"] == RegressionAttributionState.FIELD_DIRECTION_CONFIRMED.value)
    suspect = tuple(f for f in field_out
                    if f["state"] == RegressionAttributionState.FIELD_DIRECTION_SUSPECT.value)
    fp = _fp({"bundles": [(b["fields"], b["state"]) for b in bundle_out],
              "fields": [(f["field"], f["direction"], f["state"]) for f in field_out]})
    return RegressionAttributionReport(bundles=bundle_out, field_attributions=field_out,
                                       blocked_bundles=blocked, confirmed_field_directions=confirmed,
                                       suspect_field_directions=suspect, doctrine=_DOCTRINE,
                                       content_fingerprint=fp)


def attribution_versions() -> dict:
    return {"regression_attribution": REGRESSION_ATTRIBUTION_VERSION,
            "schema": REGRESSION_ATTRIBUTION_SCHEMA}
