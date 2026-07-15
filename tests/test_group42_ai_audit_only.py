"""
Group 42 — Setup constants: rejected-advisory status routing.

The AI audit layer (build_audit_prompt / parse_audit_response /
map_audit_to_finaliser) was removed with the generative-AI purge, so the
acceptance tests that exercised it (AC9-AC12) are gone. AC14 survives because
it guards a deterministic invariant that still holds: the rejected-advisory
status must never be treated as an approved status.

All tests are pure/offline — no network, no Qt event loop.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from strategy._setup_constants import APPROVED_STATUSES, AI_AUDIT_REJECTED_ADVISORY


# ===========================================================================
# AC14 — AI_AUDIT_REJECTED_ADVISORY not in APPROVED_STATUSES
# ===========================================================================

class TestAC14AuditRejectedAdvisory:
    """AC14: AI_AUDIT_REJECTED_ADVISORY is not in APPROVED_STATUSES."""

    def test_ai_audit_rejected_advisory_not_in_approved_statuses(self):
        """AI_AUDIT_REJECTED_ADVISORY must NOT be in APPROVED_STATUSES."""
        assert AI_AUDIT_REJECTED_ADVISORY not in APPROVED_STATUSES, (
            f"AC14 FAIL: AI_AUDIT_REJECTED_ADVISORY ({AI_AUDIT_REJECTED_ADVISORY!r}) "
            f"must not be in APPROVED_STATUSES {APPROVED_STATUSES}"
        )

    def test_ai_audit_rejected_advisory_is_string(self):
        """AI_AUDIT_REJECTED_ADVISORY must be a non-empty string."""
        assert isinstance(AI_AUDIT_REJECTED_ADVISORY, str)
        assert len(AI_AUDIT_REJECTED_ADVISORY) > 0

    def test_ai_audit_rejected_advisory_value(self):
        """The constant must have the expected value."""
        assert AI_AUDIT_REJECTED_ADVISORY == "ai_audit_rejected_advisory", (
            f"Expected 'ai_audit_rejected_advisory', got {AI_AUDIT_REJECTED_ADVISORY!r}"
        )

    def test_approved_statuses_content(self):
        """APPROVED_STATUSES must contain approved and approved_with_warnings but not advisory."""
        assert "approved" in APPROVED_STATUSES, "APPROVED_STATUSES must contain 'approved'"
        assert "approved_with_warnings" in APPROVED_STATUSES
        assert "fallback_generated" in APPROVED_STATUSES
        assert AI_AUDIT_REJECTED_ADVISORY not in APPROVED_STATUSES
