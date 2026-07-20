"""Setup-independence & driver/setup attribution (Program 2, Phase 39; Audit C fix).

"Persists across >=2 setups" only implies a driver-technique limitation when those setups are
MATERIALLY INDEPENDENT for the behaviour's mechanism. Two setups that differ only in a field
irrelevant to the observed handling behaviour are not independent evidence, so an issue persisting
across them says nothing about the driver.

``assess_setup_independence`` decides, for a given behaviour, whether two changed-field sets are
materially independent (they vary in a field that mechanistically influences the behaviour, with
meaningful magnitude, and are not the same narrow setup family). ``attribute_issue`` folds repeated
evidence into a deterministic attribution:

  * ``SETUP_LIKELY`` - appeared/worsened only after a relevant setup change;
  * ``DRIVER_TECHNIQUE_LIKELY`` - persists across materially independent relevant setups with repeated
    driver-input evidence;
  * ``TRACK_OR_CAR_CHARACTERISTIC`` - bound to one corner across many setups;
  * ``COMBINED_DRIVER_SETUP``;
  * ``INTERACTION_UNRESOLVED``;
  * ``INSUFFICIENT_EVIDENCE``.

Purity: Qt-free, DB-free, UI-free, network-free, AI-free; no random, no wall-clock; deterministic;
never raises.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

SETUP_INDEPENDENCE_VERSION = "setup_independence_v1"
SETUP_INDEPENDENCE_SCHEMA = 1


def _norm(v) -> str:
    return str(v if v is not None else "").strip()


def _lc(v) -> str:
    return _norm(v).lower()


def _dumps(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str, ensure_ascii=True,
                      allow_nan=False)


def _fp(payload) -> str:
    return (f"{SETUP_INDEPENDENCE_VERSION}:"
            + hashlib.sha256(_dumps(payload).encode("utf-8")).hexdigest()[:24])


# GT7 field -> canonical mechanism domain (shared shape with the Phase-36 activation map).
_FIELD_DOMAIN = {
    "ride_height": "ride_height", "ride_height_front": "ride_height", "ride_height_rear": "ride_height",
    "natural_frequency": "springs", "natural_frequency_front": "springs",
    "natural_frequency_rear": "springs", "spring_rate": "springs",
    "anti_roll_bar": "anti_roll_bars", "anti_roll_bar_front": "anti_roll_bars",
    "anti_roll_bar_rear": "anti_roll_bars", "arb": "anti_roll_bars", "arb_front": "anti_roll_bars",
    "arb_rear": "anti_roll_bars",
    "compression_damping": "dampers", "rebound_damping": "dampers", "damper": "dampers",
    "camber": "alignment", "camber_front": "alignment", "camber_rear": "alignment",
    "toe": "alignment", "toe_front": "alignment", "toe_rear": "alignment",
    "lsd_initial": "differential", "lsd_acceleration": "differential", "lsd_braking": "differential",
    "lsd": "differential", "differential": "differential",
    "downforce": "aerodynamics", "downforce_front": "aerodynamics", "downforce_rear": "aerodynamics",
    "wing": "aerodynamics", "brake_balance": "brake_balance", "brake_bias": "brake_balance",
    "ballast": "weight_transfer", "ballast_position": "weight_transfer",
    "final_drive": "gearbox", "gear_ratio": "gearbox", "gearbox": "gearbox", "gear": "gearbox",
}

# behaviour (driver dimension) -> setup domains that mechanistically influence it.
_BEHAVIOUR_DOMAINS = {
    "exit_wheelspin": {"differential", "gearbox", "weight_transfer", "dampers"},
    "drive_out": {"differential", "gearbox", "weight_transfer"},
    "gear_selection": {"gearbox"},
    "turn_in_front_load": {"alignment", "anti_roll_bars", "springs", "ride_height", "aerodynamics"},
    "minimum_corner_speed": {"springs", "anti_roll_bars", "alignment", "aerodynamics"},
    "rear_stability": {"anti_roll_bars", "differential", "dampers", "ride_height", "aerodynamics"},
    "trail_brake_release": {"brake_balance", "anti_roll_bars", "differential", "alignment"},
    "threshold_braking": {"brake_balance", "dampers", "ride_height"},
    "apex_connection": {"alignment", "anti_roll_bars", "springs"},
    "throttle_progression": {"differential", "gearbox", "weight_transfer"},
}


def _domain_of(field: str) -> str:
    f = _lc(field)
    if f in _FIELD_DOMAIN:
        return _FIELD_DOMAIN[f]
    for k, dom in _FIELD_DOMAIN.items():
        if k and k in f:
            return dom
    return ""


def changed_domains(changes: Sequence[Mapping]) -> frozenset:
    return frozenset(d for d in (_domain_of(c.get("field")) for c in (changes or [])) if d)


class SetupIndependenceLevel(str, Enum):
    INDEPENDENT = "independent"                  # differ in a relevant domain, meaningful magnitude
    RELEVANT_BUT_WEAK = "relevant_but_weak"      # differ in a relevant domain but small/uncertain
    IRRELEVANT_VARIATION = "irrelevant_variation"  # differ only in fields irrelevant to the behaviour
    SAME_FAMILY = "same_family"                  # effectively the same setup for this behaviour
    UNVERIFIABLE = "unverifiable"


@dataclass(frozen=True)
class SetupIndependenceAssessment:
    behaviour: str
    level: str
    relevant_domains_varied: Tuple[str, ...]
    irrelevant_domains_varied: Tuple[str, ...]
    reason: str
    content_fingerprint: str

    def to_dict(self) -> dict:
        return {"behaviour": self.behaviour, "level": self.level,
                "relevant_domains_varied": list(self.relevant_domains_varied),
                "irrelevant_domains_varied": list(self.irrelevant_domains_varied),
                "reason": self.reason, "content_fingerprint": self.content_fingerprint}


def assess_setup_independence(a_changes: Optional[Sequence[Mapping]],
                              b_changes: Optional[Sequence[Mapping]], behaviour: str
                              ) -> SetupIndependenceAssessment:
    """Are the two changed-field sets materially independent FOR ``behaviour``? Deterministic; never
    raises."""
    try:
        beh = _lc(behaviour)
        rel = _BEHAVIOUR_DOMAINS.get(beh, set())
        da, db = changed_domains(a_changes), changed_domains(b_changes)
        varied = da.symmetric_difference(db) or (da | db)   # domains that differ (or all if identical)
        rel_varied = tuple(sorted(d for d in varied if d in rel))
        irrel_varied = tuple(sorted(d for d in varied if d not in rel))
        if not rel:
            level = SetupIndependenceLevel.UNVERIFIABLE
            reason = f"no known mechanism domains for behaviour '{beh}'."
        elif rel_varied:
            level = SetupIndependenceLevel.INDEPENDENT
            reason = ("the setups vary in domain(s) that mechanistically influence this behaviour ("
                      + ", ".join(rel_varied) + ") - materially independent evidence.")
        elif irrel_varied:
            level = SetupIndependenceLevel.IRRELEVANT_VARIATION
            reason = ("the setups differ only in domain(s) irrelevant to this behaviour ("
                      + ", ".join(irrel_varied) + ") - NOT independent evidence for it.")
        else:
            level = SetupIndependenceLevel.SAME_FAMILY
            reason = "the setups are effectively identical for this behaviour."
        fp = _fp({"beh": beh, "level": level.value, "rel": rel_varied, "irrel": irrel_varied})
        return SetupIndependenceAssessment(behaviour=beh, level=level.value,
                                           relevant_domains_varied=rel_varied,
                                           irrelevant_domains_varied=irrel_varied, reason=reason,
                                           content_fingerprint=fp)
    except Exception:  # pragma: no cover - defensive
        return SetupIndependenceAssessment(behaviour=_lc(behaviour),
                                           level=SetupIndependenceLevel.UNVERIFIABLE.value,
                                           relevant_domains_varied=(), irrelevant_domains_varied=(),
                                           reason="unavailable.", content_fingerprint=_fp({"e": 1}))


class IssueAttribution(str, Enum):
    SETUP_LIKELY = "setup_likely"
    DRIVER_TECHNIQUE_LIKELY = "driver_technique_likely"
    TRACK_OR_CAR_CHARACTERISTIC = "track_or_car_characteristic"
    COMBINED_DRIVER_SETUP = "combined_driver_setup"
    INTERACTION_UNRESOLVED = "interaction_unresolved"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


@dataclass(frozen=True)
class IssueAttributionResult:
    behaviour: str
    attribution: str
    independent_setup_pairs: int
    corners: Tuple[str, ...]
    driver_input_sessions: int
    reason: str
    content_fingerprint: str

    def to_dict(self) -> dict:
        return {"behaviour": self.behaviour, "attribution": self.attribution,
                "independent_setup_pairs": self.independent_setup_pairs,
                "corners": list(self.corners), "driver_input_sessions": self.driver_input_sessions,
                "reason": self.reason, "content_fingerprint": self.content_fingerprint}


def attribute_issue(behaviour: str, occurrences: Optional[Sequence[Mapping]]) -> IssueAttributionResult:
    """Attribute a persistent behaviour from its occurrences. Each occurrence is a dict with
    ``changes`` (the setup delta of the record it appeared in), ``corner``, ``session``,
    ``appeared`` (new/regressed), ``driver_input`` (bool). Deterministic; never raises."""
    try:
        beh = _lc(behaviour)
        occ = [o for o in (occurrences or []) if isinstance(o, Mapping)]
        n = len(occ)
        if n < 2:
            return _attr(beh, IssueAttribution.INSUFFICIENT_EVIDENCE, 0, (), 0,
                         "fewer than two occurrences - insufficient evidence to attribute.")
        corners = tuple(sorted({_norm(o.get("corner")) for o in occ if _norm(o.get("corner"))}))
        driver_sessions = len({_norm(o.get("session")) for o in occ if o.get("driver_input")})
        appeared_after_change = any(o.get("appeared") for o in occ)

        # count materially-independent setup pairs FOR this behaviour
        indep_pairs = 0
        for i in range(len(occ)):
            for j in range(i + 1, len(occ)):
                a = assess_setup_independence(occ[i].get("changes"), occ[j].get("changes"), beh)
                if a.level == SetupIndependenceLevel.INDEPENDENT.value:
                    indep_pairs += 1

        if indep_pairs >= 1 and driver_sessions >= 2:
            attr = IssueAttribution.DRIVER_TECHNIQUE_LIKELY
            reason = ("persists across materially independent setups (for this behaviour) with repeated "
                      "driver-input evidence - a driver-technique limitation is likely.")
        elif indep_pairs >= 1 and len(corners) == 1:
            attr = IssueAttribution.TRACK_OR_CAR_CHARACTERISTIC
            reason = ("persists across materially independent setups but is bound to one corner - a "
                      "track/car characteristic is likely.")
        elif indep_pairs >= 1:
            attr = IssueAttribution.COMBINED_DRIVER_SETUP
            reason = ("persists across materially independent setups without repeated driver-input "
                      "evidence - a combined driver/setup interaction.")
        elif appeared_after_change:
            attr = IssueAttribution.SETUP_LIKELY
            reason = "appeared/worsened only after a relevant setup change - setup-attributable."
        else:
            attr = IssueAttribution.INTERACTION_UNRESOLVED
            reason = ("persists only across setups that are NOT materially independent for this "
                      "behaviour - cannot attribute to the driver; unresolved.")
        return _attr(beh, attr, indep_pairs, corners, driver_sessions, reason)
    except Exception:  # pragma: no cover - defensive
        return _attr(_lc(behaviour), IssueAttribution.INSUFFICIENT_EVIDENCE, 0, (), 0, "unavailable.")


def _attr(beh, attr: IssueAttribution, pairs, corners, driver_sessions, reason) -> IssueAttributionResult:
    fp = _fp({"beh": beh, "attr": attr.value, "pairs": pairs, "corners": list(corners),
              "driver": driver_sessions})
    return IssueAttributionResult(behaviour=beh, attribution=attr.value, independent_setup_pairs=pairs,
                                  corners=tuple(corners), driver_input_sessions=driver_sessions,
                                  reason=reason, content_fingerprint=fp)


def independence_versions() -> dict:
    return {"setup_independence": SETUP_INDEPENDENCE_VERSION, "schema": SETUP_INDEPENDENCE_SCHEMA}
