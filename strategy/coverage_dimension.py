"""Coverage Dimensions — the visible axes of evidence coverage (Program 2, Phase 27).

Enumerates the dimensions along which a knowledge domain's evidence coverage is assessed, the
coverage-status vocabulary, and the blind-spot severity vocabulary — all as explicit, visible enums
with visible threshold constants. Nothing here decides anything about the car: it only names the
axes and the status/severity labels used by the evidence-coverage assessor.

Doctrine encoded by the vocabulary:
- MISSING is the absence of evidence, NOT a negative result (REGRESSION_ONLY is the negative one);
  the two are distinct statuses and must never be conflated.
- A blind spot is a place where MORE evidence would help — it is NOT a defect or a problem.
- A large DEPENDENT evidence count is never strong coverage (DEPENDENT_EVIDENCE_ONLY).
- One track / car / driver / compound / discipline / version is never multi-context coverage
  (SINGLE_CONTEXT_ONLY).

Purity: Qt-free, DB-free, UI-free, network-free, AI-free; no random, no wall-clock; deterministic.
"""
from __future__ import annotations

from enum import Enum

COVERAGE_DIMENSION_VERSION = "coverage_dimension_v1"

# Minimum distinct contexts for "well covered" vs "adequately covered" on a breadth dimension.
# Visible constants — 1 distinct value is SINGLE_CONTEXT_ONLY, 0 is MISSING.
BREADTH_WELL_COVERED = 3
BREADTH_ADEQUATE = 2
# Minimum genuinely-independent evidence lines for robust (non-dependent) coverage.
MIN_INDEPENDENT_FOR_ROBUST = 2
# Repeated confirmations for "well covered" on the replication dimension.
REPEATED_CONFIRMATION_WELL = 3
REPEATED_CONFIRMATION_ADEQUATE = 2


class CoverageDimension(str, Enum):
    # --- context-breadth dimensions (counted from record contexts) ---
    TRACK_VARIETY = "track_variety"
    LAYOUT_VARIETY = "layout_variety"
    CAR_VARIETY = "car_variety"
    DRIVER_VARIETY = "driver_variety"
    DISCIPLINE_VARIETY = "discipline_variety"
    GT7_VERSION_VARIETY = "gt7_version_variety"
    TYRE_COMPOUND_VARIETY = "tyre_compound_variety"
    CORNER_PHASE_COVERAGE = "corner_phase_coverage"
    CORNER_TYPE_COVERAGE = "corner_type_coverage"
    # --- evidence-quality dimensions (from convergence / independence / re-validation) ---
    INDEPENDENT_REPLICATION = "independent_replication"
    REPEATED_CONFIRMATION = "repeated_confirmation"
    HIGH_CONFIDENCE_EVIDENCE = "high_confidence_evidence"
    REGRESSION_CHECK = "regression_check"
    CONFIRMED_GOOD_VERIFICATION = "confirmed_good_verification"
    CONFLICT_RESOLUTION = "conflict_resolution"
    CONVERGENCE_ACHIEVED = "convergence_achieved"
    TRANSFER_VALIDATION = "transfer_validation"
    REVALIDATION_CURRENCY = "revalidation_currency"


# The breadth dimensions and the record-context key each one counts distinct values of.
BREADTH_DIMENSION_FIELD = {
    CoverageDimension.TRACK_VARIETY: "track",
    CoverageDimension.LAYOUT_VARIETY: "layout_id",
    CoverageDimension.CAR_VARIETY: "car",
    CoverageDimension.DRIVER_VARIETY: "driver",
    CoverageDimension.DISCIPLINE_VARIETY: "discipline",
    CoverageDimension.GT7_VERSION_VARIETY: "gt7_version",
    CoverageDimension.TYRE_COMPOUND_VARIETY: "compound",
}

# Display order (visible, deterministic) — used to order per-dimension rows.
DIMENSION_ORDER = [d.value for d in CoverageDimension]


class CoverageStatus(str, Enum):
    WELL_COVERED = "well_covered"
    ADEQUATELY_COVERED = "adequately_covered"
    PARTIALLY_COVERED = "partially_covered"
    DEPENDENT_EVIDENCE_ONLY = "dependent_evidence_only"
    SINGLE_CONTEXT_ONLY = "single_context_only"
    CONFLICTED_COVERAGE = "conflicted_coverage"
    REGRESSION_ONLY = "regression_only"
    MISSING = "missing"
    UNKNOWN = "unknown"


# Which statuses represent a coverage GAP (a blind spot may be raised). WELL/ADEQUATELY covered are
# not gaps. Visible set. MISSING is a gap but is explicitly NOT a negative result.
GAP_STATUSES = frozenset({
    CoverageStatus.PARTIALLY_COVERED.value, CoverageStatus.DEPENDENT_EVIDENCE_ONLY.value,
    CoverageStatus.SINGLE_CONTEXT_ONLY.value, CoverageStatus.CONFLICTED_COVERAGE.value,
    CoverageStatus.REGRESSION_ONLY.value, CoverageStatus.MISSING.value,
})

# Display priority (lower = shown first). Gaps before covered; unknown last.
COVERAGE_STATUS_PRIORITY = {
    "conflicted_coverage": 0, "regression_only": 1, "dependent_evidence_only": 2,
    "single_context_only": 3, "partially_covered": 4, "missing": 5,
    "adequately_covered": 6, "well_covered": 7, "unknown": 8,
}


class BlindSpotSeverity(str, Enum):
    CRITICAL = "critical"
    MATERIAL = "material"
    MODERATE = "moderate"
    INFORMATIONAL = "informational"
    UNKNOWN = "unknown"


BLIND_SPOT_SEVERITY_PRIORITY = {
    "critical": 0, "material": 1, "moderate": 2, "informational": 3, "unknown": 4,
}


def coverage_dimension_versions() -> dict:
    return {"coverage_dimension": COVERAGE_DIMENSION_VERSION}
