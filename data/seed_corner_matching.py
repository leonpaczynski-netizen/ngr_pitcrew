"""Seed corner window matching — Layer 1.5 between seed truth and telemetry peaks.

Matches curvature-detected peaks to seed corner progress windows when the seed
defines per-corner expected positions.  Pure computation — no imports from other
project modules, no AI features, no per-segment approval.

Design rules:
  - Strongest curvature peak inside a window wins that window (greedy by curvature).
  - Peaks inside multiple windows each only win one window (greedy assignment).
  - Peaks outside all windows become XP (extra-peak) diagnostics.
  - Windows with no matching peak report NO_CANDIDATE_IN_WINDOW and need a placeholder.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Tuple


# ---------------------------------------------------------------------------
# Match status
# ---------------------------------------------------------------------------

class CornerMatchStatus(str, Enum):
    MATCHED                   = "MATCHED"                    # one candidate confirmed in window
    MULTIPLE_CANDIDATES       = "MULTIPLE_CANDIDATES"        # several in window; strongest selected
    NO_CANDIDATE_IN_WINDOW    = "NO_CANDIDATE_IN_WINDOW"     # no curvature peak in seed window
    SEED_POSITION_UNAVAILABLE = "SEED_POSITION_UNAVAILABLE"  # seed has no progress window data
    PLACEHOLDER_USED          = "PLACEHOLDER_USED"           # position estimated, not detected
    EXTRA_PEAK_SUPPRESSED     = "EXTRA_PEAK_SUPPRESSED"      # XP peak not in any seed window


# ---------------------------------------------------------------------------
# Per-corner match result
# ---------------------------------------------------------------------------

@dataclass
class CornerCandidateMatch:
    """Result of matching one seed corner window to telemetry curvature candidates."""
    seed_corner_id:             str
    matched_candidate_id:       Optional[str]    # e.g. "T1"; None = no match
    candidate_progress_pct:     Optional[float]  # where the matched peak is (0–100)
    expected_apex_progress_pct: Optional[float]  # where seed says apex should be (0–100)
    delta_pct:                  Optional[float]  # |candidate – apex| in pct points
    match_status:               CornerMatchStatus
    confidence:                 float
    notes:                      str = ""


# ---------------------------------------------------------------------------
# Window matching function
# ---------------------------------------------------------------------------

def match_peaks_to_seed_windows(
    peak_progresses: List[float],
    peak_curvatures: List[float],
    window_starts:   List[float],
    window_apexes:   List[float],
    window_ends:     List[float],
    window_ids:      List[str],
) -> Tuple[List[int], List[int], List[CornerCandidateMatch]]:
    """Match curvature peaks to seed corner progress windows.

    Uses a greedy algorithm: strongest curvature peak wins each window.  A peak
    can only be assigned to one window; if a peak falls inside multiple windows
    the strongest curvature pair wins first.

    Args:
        peak_progresses: progress_pct (0–100) for each detected curvature peak.
        peak_curvatures: abs(curvature) for each peak — used as tie-breaker.
        window_starts:   start_progress_pct for each seed corner (0–100).
        window_apexes:   apex_progress_pct for each seed corner (0–100).
        window_ends:     end_progress_pct for each seed corner (0–100).
        window_ids:      corner_id string for each seed corner ("T1", "T2", …).

    Returns:
        official_indices:  list[int], one per seed window.
                           Value = index into peak_* lists, or -1 if no match found.
        extra_indices:     list[int] — peak indices not assigned to any window.
        corner_matches:    list[CornerCandidateMatch], one per seed window.
    """
    n_peaks   = len(peak_progresses)
    n_windows = len(window_starts)

    if n_peaks == 0 or n_windows == 0:
        no_match = [
            CornerCandidateMatch(
                seed_corner_id             = window_ids[wi] if wi < len(window_ids) else f"W{wi}",
                matched_candidate_id       = None,
                candidate_progress_pct     = None,
                expected_apex_progress_pct = window_apexes[wi] if wi < len(window_apexes) else None,
                delta_pct                  = None,
                match_status               = CornerMatchStatus.NO_CANDIDATE_IN_WINDOW,
                confidence                 = 0.0,
                notes                      = "No curvature peaks available",
            )
            for wi in range(n_windows)
        ]
        return [-1] * n_windows, list(range(n_peaks)), no_match

    # ── Step 1: build (pi, wi, curvature) pairs for every peak–window overlap ──
    pairs: List[Tuple[float, int, int]] = []  # (curvature, peak_idx, window_idx)
    for pi in range(n_peaks):
        prog = peak_progresses[pi]
        for wi in range(n_windows):
            if window_starts[wi] <= prog <= window_ends[wi]:
                pairs.append((peak_curvatures[pi], pi, wi))

    # ── Step 2: greedy assignment, strongest curvature first ──────────────────
    pairs.sort(key=lambda t: t[0], reverse=True)
    peak_assigned:   dict[int, int] = {}   # peak_idx  → window_idx
    window_assigned: dict[int, int] = {}   # window_idx → peak_idx

    for _curv, pi, wi in pairs:
        if pi not in peak_assigned and wi not in window_assigned:
            peak_assigned[pi]   = wi
            window_assigned[wi] = pi

    # ── Step 3: build output ──────────────────────────────────────────────────
    official_indices: List[int] = []
    corner_matches:   List[CornerCandidateMatch] = []

    for wi in range(n_windows):
        wid   = window_ids[wi]  if wi < len(window_ids)   else f"W{wi}"
        wst   = window_starts[wi] if wi < len(window_starts) else 0.0
        wend  = window_ends[wi]   if wi < len(window_ends)   else 100.0
        wapex = window_apexes[wi] if wi < len(window_apexes) else 50.0

        # Count how many peaks are in this window (for secondary-candidate detection)
        in_window_count = sum(
            1 for pi in range(n_peaks)
            if wst <= peak_progresses[pi] <= wend
        )

        if wi not in window_assigned:
            official_indices.append(-1)
            corner_matches.append(CornerCandidateMatch(
                seed_corner_id             = wid,
                matched_candidate_id       = None,
                candidate_progress_pct     = None,
                expected_apex_progress_pct = wapex,
                delta_pct                  = None,
                match_status               = CornerMatchStatus.NO_CANDIDATE_IN_WINDOW,
                confidence                 = 0.0,
                notes = (
                    f"No curvature peak in window [{wst:.1f}%–{wend:.1f}%]"
                ),
            ))
        else:
            best_pi = window_assigned[wi]
            official_indices.append(best_pi)
            n_secondary = in_window_count - 1  # all in window minus winner
            status = (
                CornerMatchStatus.MATCHED
                if n_secondary == 0
                else CornerMatchStatus.MULTIPLE_CANDIDATES
            )
            delta = abs(peak_progresses[best_pi] - wapex)
            extra_note = (
                f" ({n_secondary} secondary candidate(s) in window → XP diagnostics)"
                if n_secondary > 0 else ""
            )
            corner_matches.append(CornerCandidateMatch(
                seed_corner_id             = wid,
                matched_candidate_id       = f"peak_{best_pi}",
                candidate_progress_pct     = peak_progresses[best_pi],
                expected_apex_progress_pct = wapex,
                delta_pct                  = delta,
                match_status               = status,
                confidence                 = min(1.0, peak_curvatures[best_pi] / 0.05),
                notes = (
                    f"Apex at {peak_progresses[best_pi]:.1f}% "
                    f"(expected {wapex:.1f}%, Δ={delta:.1f}%)"
                    + extra_note
                ),
            ))

    extra_indices: List[int] = [pi for pi in range(n_peaks) if pi not in peak_assigned]

    return official_indices, extra_indices, corner_matches
