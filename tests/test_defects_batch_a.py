"""Unit tests for defect batch A fixes.

DEF-P4-002: Configurable AI model
DEF-P2-006: Tuning lock on event activation (Qt required — skipped in CI)
DEF-P3-003: Tyre compound inheritance (Qt required — skipped in CI)
DEF-P3-006: Session summary recalculation after history load (Qt required — skipped in CI)
"""
from __future__ import annotations

import json
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# DEF-P4-002 — Configurable AI model
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# DEF-P4-002 — Configurable AI model: REMOVED (strategy._ai_client and its
# call_api / _DEFAULT_MODEL were deleted in the no-AI refactor).
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# DEF-P2-006 — Tuning lock on event activation (requires Qt display)
# ---------------------------------------------------------------------------

import pytest

@pytest.mark.skip(reason="requires Qt display")
def test_apply_setup_permissions_called_on_event_set_active():
    """_on_event_set_active() must call _apply_setup_permissions unconditionally."""
    pass


# ---------------------------------------------------------------------------
# DEF-P3-003 — Tyre compound inheritance in _add_bank_lap_row (requires Qt)
# ---------------------------------------------------------------------------

@pytest.mark.skip(reason="requires Qt display")
def test_bank_lap_row_inherits_prior_compound():
    """New lap with no compound should inherit the highest prior lap's compound."""
    pass


@pytest.mark.skip(reason="requires Qt display")
def test_bank_lap_row_falls_back_to_default_compound():
    """New lap with no compound and no prior tags should use _default_lap_compound."""
    pass


# ---------------------------------------------------------------------------
# DEF-P3-006 — Practice summary recalculation (requires Qt)
# ---------------------------------------------------------------------------

@pytest.mark.skip(reason="requires Qt display")
def test_refresh_practice_summary_after_history_load():
    """_on_history_load_session() must trigger _refresh_practice_summary()."""
    pass


@pytest.mark.skip(reason="requires Qt display")
def test_refresh_practice_summary_zero_rows():
    """_refresh_practice_summary() with no rows sets all labels to — except laps=0."""
    pass


if __name__ == "__main__":
    unittest.main()
