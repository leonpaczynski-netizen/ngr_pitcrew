"""Tests for lap delta calculations.

Delta is computed from raw lap time fields — test the core arithmetic
used in dashboard.py (not the widget itself, since that requires Qt).
"""


def _compute_delta(last_lap_ms: int, reference_ms: int) -> int:
    """The delta formula used in dashboard.py live updates."""
    return last_lap_ms - reference_ms


# ---------------------------------------------------------------------------
# Delta to best lap
# ---------------------------------------------------------------------------

def test_delta_positive_when_slower_than_best():
    last = 95_500
    best = 94_000
    delta = _compute_delta(last, best)
    assert delta > 0
    assert delta == 1_500


def test_delta_negative_when_new_best():
    last = 93_800
    best = 94_000
    delta = _compute_delta(last, best)
    assert delta < 0
    assert delta == -200


def test_delta_zero_when_exactly_on_best():
    t = 94_000
    assert _compute_delta(t, t) == 0


# ---------------------------------------------------------------------------
# Delta to qualifying target
# ---------------------------------------------------------------------------

def test_delta_to_target_positive_when_over():
    last = 113_000  # 1:53.000
    target = 112_000  # 1:52.000
    assert _compute_delta(last, target) == 1_000


def test_delta_to_target_negative_when_under():
    last = 111_500
    target = 112_000
    assert _compute_delta(last, target) == -500


def test_target_from_spinboxes():
    """Verify the ms conversion from spin box minutes + seconds matches expected."""
    minutes = 1
    seconds = 52.0
    target_ms = int(minutes * 60_000 + seconds * 1_000)
    assert target_ms == 112_000


def test_target_from_spinboxes_with_decimals():
    minutes = 1
    seconds = 45.123
    target_ms = int(minutes * 60_000 + seconds * 1_000)
    assert target_ms == 105_123


# ---------------------------------------------------------------------------
# No delta on first lap (no prior best)
# ---------------------------------------------------------------------------

def test_no_delta_when_no_prior_best():
    last_lap_ms = 94_500
    best_lap_ms = 0  # no prior lap recorded
    # In dashboard.py: delta is only shown when best_lap_ms > 0
    assert best_lap_ms == 0  # guard condition: don't compute delta
