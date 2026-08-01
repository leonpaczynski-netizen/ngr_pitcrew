"""Program 3 Phase I (model) — cross-event learning transfer (§24).

Conservative + explainable transfer built on the existing doctrine: exact context
outranks transfer, broad learning is a prior not a command, confidence-gated,
more-specific-suppresses-broader.
"""

from strategy.learning_transfer import (
    TransferVerdict, evaluate_learning_transfer, rank_priors_for_target, layer_rank,
)


def _prior(obs="prefers front-end bite", layer="global_driver", confidence=0.8):
    return {"observation": obs, "proposed_layer": layer, "confidence": confidence}


def test_low_confidence_is_excluded():
    t = evaluate_learning_transfer(_prior(confidence=0.3), {"driver_id": "leon"})
    assert t.verdict == TransferVerdict.EXCLUDED_LOW_CONFIDENCE and not t.applies


def test_missing_required_context_is_excluded():
    # a car_specific prior needs car_id in the target
    t = evaluate_learning_transfer(_prior(layer="car_specific"), {"driver_id": "leon"})
    assert t.verdict == TransferVerdict.EXCLUDED_CONTEXT_MISSING and not t.applies


def test_exact_layer_applies_at_full_strength():
    t = evaluate_learning_transfer(_prior(layer="car_specific", confidence=0.8),
                                   {"car_id": 333})
    assert t.verdict == TransferVerdict.APPLIES_EXACT
    assert t.strength == 0.8 and t.applies


def test_broad_layer_applies_only_as_a_low_strength_prior():
    t = evaluate_learning_transfer(_prior(layer="global_driver", confidence=0.8), {})
    assert t.verdict == TransferVerdict.APPLIES_AS_PRIOR
    assert t.strength == 0.4              # halved — a prior, not a command
    assert "not a command" in t.explanation


def test_more_specific_contradiction_suppresses_the_broad_prior():
    t = evaluate_learning_transfer(_prior(layer="global_driver"), {},
                                   more_specific_contradiction=True)
    assert t.verdict == TransferVerdict.SUPPRESSED_BY_MORE_SPECIFIC and not t.applies


def test_specificity_cascade_more_specific_wins():
    """Same topic at two layers: the car-specific prior applies; the global one is
    suppressed by it (exact evidence outranks broad transferable learning)."""
    priors = [
        _prior(obs="prefers front-end bite", layer="global_driver", confidence=0.8),
        _prior(obs="prefers front-end bite", layer="car_specific", confidence=0.8),
    ]
    results = rank_priors_for_target(priors, {"car_id": 333, "driver_id": "leon"})
    by_layer = {r.layer: r for r in results}
    assert by_layer["car_specific"].verdict == TransferVerdict.APPLIES_EXACT
    assert by_layer["global_driver"].verdict == TransferVerdict.SUPPRESSED_BY_MORE_SPECIFIC


def test_layer_rank_order():
    assert layer_rank("event") < layer_rank("car_specific") < layer_rank("global_driver")
    assert layer_rank("unknown-layer") >= layer_rank("global_driver")


def test_exact_context_value_mismatch_excludes_transfer():
    # a car-specific prior for car 333 must NOT transfer to a different car (999)
    prior = {"observation": "stable braking", "proposed_layer": "car_specific",
             "confidence": 0.8, "car_id": 333}
    assert evaluate_learning_transfer(prior, {"car_id": 999}).verdict == \
        TransferVerdict.EXCLUDED_CONTEXT_MISMATCH
    # ... but DOES apply when the car matches
    assert evaluate_learning_transfer(prior, {"car_id": 333}).verdict == \
        TransferVerdict.APPLIES_EXACT
    # when the prior omits the value, presence is sufficient (back-compat)
    prior_noval = {"observation": "x", "proposed_layer": "car_specific", "confidence": 0.8}
    assert evaluate_learning_transfer(prior_noval, {"car_id": 999}).verdict == \
        TransferVerdict.APPLIES_EXACT


def test_never_raises_on_garbage():
    assert evaluate_learning_transfer(None, None) is not None          # type: ignore
    assert rank_priors_for_target(None, None) == []                    # type: ignore
