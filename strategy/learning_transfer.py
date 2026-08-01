"""Cross-event learning transfer (Program 3 Phase I / §24).

Decides whether an ACCEPTED learning prior may influence a future event, and at what
strength. Built by EXTENDING the app's existing doctrine — exact context outranks
transfer, broad learning is a prior (not a command), and contradiction *detection*
stays with the existing contradiction machinery — rather than a parallel archetype
system.

Transfer is conservative and explainable. A prior applies only when: its confidence
meets the threshold, the target has the context the prior's layer requires, and no
more-specific prior contradicts it. Exact-context layers apply at full strength;
broader layers apply only as a low-strength prior. More specific valid evidence always
outranks a broad transferable learning.

Pure, deterministic, offline, never raises.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from typing import Mapping, Optional


# Layer specificity, MOST specific first — mirrors the existing ContextRelation
# ordering (exact > same-car-other-track > same-driver-other-car > ... > global).
LAYER_SPECIFICITY = (
    "event",             # exact driver + car + track + layout + event context
    "track_layout",      # exact driver + car + track + layout
    "car_specific",      # exact driver + car
    "track_archetype",   # driver + car + track type
    "vehicle_archetype", # driver + vehicle archetype
    "global_driver",     # global driver tendency
)

# Which layers apply at FULL strength (exact context) vs only as a prior.
_EXACT_LAYERS = frozenset({"event", "track_layout", "car_specific"})

# The target context keys a layer requires to be present before it can apply.
_LAYER_REQUIRES: Mapping[str, tuple] = {
    "event": ("event_id",),
    "track_layout": ("track", "layout"),
    "car_specific": ("car_id",),
    "track_archetype": ("track_archetype",),
    "vehicle_archetype": ("vehicle_archetype",),
    "global_driver": (),          # a global driver tendency always applies to the driver
}


class TransferVerdict(str, enum.Enum):
    APPLIES_EXACT = "applies_exact"                    # exact-context prior, full strength
    APPLIES_AS_PRIOR = "applies_as_prior"              # broad prior, low strength (a prior, not a command)
    SUPPRESSED_BY_MORE_SPECIFIC = "suppressed_by_more_specific"
    EXCLUDED_LOW_CONFIDENCE = "excluded_low_confidence"
    EXCLUDED_CONTEXT_MISSING = "excluded_context_missing"


@dataclass(frozen=True)
class LearningTransfer:
    observation: str
    layer: str
    verdict: TransferVerdict
    strength: float          # 0..1
    explanation: str

    @property
    def applies(self) -> bool:
        return self.verdict in (TransferVerdict.APPLIES_EXACT, TransferVerdict.APPLIES_AS_PRIOR)


def layer_rank(layer: str) -> int:
    """Specificity rank (0 = most specific). Unknown layers rank as broadest."""
    try:
        return LAYER_SPECIFICITY.index(str(layer or "").strip().lower())
    except ValueError:
        return len(LAYER_SPECIFICITY)


def evaluate_learning_transfer(
    prior: Mapping,
    target_context: Mapping,
    *,
    more_specific_contradiction: bool = False,
    confidence_threshold: float = 0.5,
) -> LearningTransfer:
    """Decide whether an accepted prior transfers to ``target_context``.

    ``more_specific_contradiction`` is supplied by the caller (from the existing
    contradiction machinery) when a more-specific prior/evidence disagrees — the broad
    learning is then suppressed rather than averaged. Never raises."""
    try:
        obs = str((prior or {}).get("observation") or "")
        layer = str((prior or {}).get("proposed_layer") or "global_driver").strip().lower()
        conf = float((prior or {}).get("confidence") or 0.0)
        tgt = dict(target_context or {})

        if conf < float(confidence_threshold):
            return LearningTransfer(obs, layer, TransferVerdict.EXCLUDED_LOW_CONFIDENCE, 0.0,
                                    f"confidence {conf:.2f} below threshold {confidence_threshold:.2f}")

        for key in _LAYER_REQUIRES.get(layer, ()):
            if not tgt.get(key):
                return LearningTransfer(
                    obs, layer, TransferVerdict.EXCLUDED_CONTEXT_MISSING, 0.0,
                    f"target lacks '{key}' required by the {layer} layer")

        if more_specific_contradiction:
            return LearningTransfer(
                obs, layer, TransferVerdict.SUPPRESSED_BY_MORE_SPECIFIC, 0.0,
                "a more-specific prior contradicts this — exact evidence outranks a broad prior")

        if layer in _EXACT_LAYERS:
            return LearningTransfer(obs, layer, TransferVerdict.APPLIES_EXACT, conf,
                                    f"exact-context learning ({layer}) applies at full strength")
        return LearningTransfer(
            obs, layer, TransferVerdict.APPLIES_AS_PRIOR, round(conf * 0.5, 3),
            f"broad {layer} learning applies only as a low-strength prior, not a command")
    except Exception:
        return LearningTransfer("", "global_driver", TransferVerdict.EXCLUDED_CONTEXT_MISSING,
                                0.0, "unevaluable")


def rank_priors_for_target(priors, target_context, *, confidence_threshold: float = 0.5) -> list:
    """Evaluate a set of accepted priors against a target, MOST-specific first. Returns a
    list of LearningTransfer. A prior is automatically suppressed when a more-specific
    APPLYING prior shares its observation topic (the specificity cascade)."""
    try:
        ordered = sorted(list(priors or []), key=lambda p: layer_rank(p.get("proposed_layer")))
        results = []
        applied_topics: dict = {}
        for p in ordered:
            topic = str(p.get("observation") or "").strip().lower()
            contradicted = topic in applied_topics  # a more-specific prior already owns this topic
            t = evaluate_learning_transfer(
                p, target_context, more_specific_contradiction=contradicted,
                confidence_threshold=confidence_threshold)
            if t.applies and topic:
                applied_topics.setdefault(topic, t)
            results.append(t)
        return results
    except Exception:
        return []
