"""Deterministic engineering state-transition + trend rules (Engineering Brain Phase 7).

Phase 7 is a READ-ONLY OBSERVER. This module holds the explicit, documented rules
that turn a per-issue history of valid-lap observations into a Trend and an
IssueStatus. It makes NO engineering decision, selects no experiment, scores no
evidence and mutates nothing — it only classifies what the canonical evidence
already shows.

Transition model (documented):

    UNKNOWN → NEW → ACTIVE → RECOVERING → STABLE → RESOLVED     (recovery path)
    ACTIVE → WORSENING(trend) → (a NEW regression is a fresh ACTIVE issue)
    PROTECTED → DAMAGED → ACTIVE                                (protected path)

Trend uses ONLY comparable (valid) laps; a single exceptional lap can never flip a
trend (window fractions + a minimum-lap gate + hysteresis).

Purity: Qt-free, DB-free, UI-free, network-free, AI-free; never raises; no random,
no wall-clock.
"""
from __future__ import annotations

from enum import Enum
from typing import Optional, Sequence, Tuple


STATE_TRANSITIONS_VERSION = "state_transitions_v1"

# Minimum comparable valid laps before a trend/status can be asserted.
MIN_TREND_LAPS = 3
# Fraction change (early-window vs recent-window affected fraction) that counts as a
# real move. Below this, the trend is UNCHANGED (hysteresis against single laps).
TREND_DELTA = 0.20
# Consecutive recent valid laps clear of the issue to call it RESOLVED.
RESOLVE_CLEAR_LAPS = 3


class Trend(str, Enum):
    IMPROVING = "improving"
    UNCHANGED = "unchanged"
    WORSENING = "worsening"
    FLUCTUATING = "fluctuating"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


class IssueStatus(str, Enum):
    UNKNOWN = "unknown"
    NEW = "new"
    ACTIVE = "active"
    RECOVERING = "recovering"
    STABLE = "stable"
    RESOLVED = "resolved"
    PROTECTED = "protected"
    DAMAGED = "damaged"          # a protected behaviour that started recurring


def _windows(affected: Sequence[bool]) -> Tuple[float, float]:
    """Early-half vs recent-half affected fractions over the valid-lap sequence."""
    n = len(affected)
    half = n // 2
    early = affected[:half] if half else affected[:1]
    recent = affected[half:] if half else affected
    ef = (sum(1 for a in early if a) / len(early)) if early else 0.0
    rf = (sum(1 for a in recent if a) / len(recent)) if recent else 0.0
    return round(ef, 4), round(rf, 4)


def _direction_changes(affected: Sequence[bool]) -> int:
    """Count transitions present↔absent across consecutive valid laps (jitter)."""
    changes = 0
    for i in range(1, len(affected)):
        if affected[i] != affected[i - 1]:
            changes += 1
    return changes


def detect_trend(affected: Sequence[bool], *, min_laps: int = MIN_TREND_LAPS,
                 delta: float = TREND_DELTA) -> Trend:
    """Classify the trend of an issue over its VALID-lap affected sequence
    (``affected[i]`` = the issue occurred on the i-th valid lap).

    * < ``min_laps`` valid laps → INSUFFICIENT_EVIDENCE.
    * recent-window fraction lower than early by ≥ ``delta`` → IMPROVING.
    * recent-window fraction higher than early by ≥ ``delta`` → WORSENING.
    * many present↔absent flips with no net move → FLUCTUATING.
    * otherwise → UNCHANGED.

    A single exceptional lap cannot flip the trend — the comparison is over window
    fractions, and FLUCTUATING guards a noisy but net-flat sequence.
    """
    seq = list(bool(a) for a in affected)
    if len(seq) < min_laps:
        return Trend.INSUFFICIENT_EVIDENCE
    # Jitter first: a near-alternating sequence has no stable trend, even if the
    # window split happens to show a slope. This also guards against a single lap
    # driving the classification.
    flips = _direction_changes(seq)
    if flips > (len(seq) // 2) + 1:
        return Trend.FLUCTUATING
    half = len(seq) // 2 or 1
    early, recent = seq[:half], seq[half:]
    early_c, recent_c = sum(early), sum(recent)
    early_f = early_c / len(early) if early else 0.0
    recent_f = recent_c / len(recent) if recent else 0.0
    move = recent_f - early_f
    recent_clear = len(recent) - recent_c
    # A real move must be supported by ≥2 laps in the recent window, so a single
    # exceptional lap can never flip the trend: IMPROVING needs ≥2 recent CLEAR laps,
    # WORSENING needs ≥2 recent AFFECTED laps.
    if move <= -delta and recent_clear >= 2:
        return Trend.IMPROVING
    if move >= delta and recent_c >= 2:
        return Trend.WORSENING
    return Trend.UNCHANGED


def _recent_clear(affected: Sequence[bool], k: int) -> bool:
    """True when the last ``k`` valid laps are all clear of the issue."""
    if len(affected) < k:
        return False
    return not any(affected[-k:])


def next_status(
    prev_status: IssueStatus,
    trend: Trend,
    *,
    present_now: bool,
    affected: Sequence[bool],
    is_protected: bool = False,
    total_valid_laps: int = 0,
    first_seen_valid_lap: Optional[int] = None,
    latest_valid_lap: Optional[int] = None,
    new_recent_laps: int = 3,
    resolve_clear_laps: int = RESOLVE_CLEAR_LAPS,
) -> IssueStatus:
    """Deterministic next status from the previous status + trend + presence.

    Recovery path: UNKNOWN → NEW → ACTIVE → RECOVERING → STABLE → RESOLVED.
    Protected path: PROTECTED (good) → DAMAGED (started recurring) → ACTIVE.
    """
    affected = list(bool(a) for a in affected)
    ever = any(affected)

    # --- protected behaviours -------------------------------------------------
    if is_protected:
        if not ever:
            return IssueStatus.PROTECTED
        # a protected behaviour that started recurring is DAMAGED, then ACTIVE if it
        # keeps recurring.
        if present_now and trend == Trend.WORSENING:
            return IssueStatus.ACTIVE
        if present_now:
            return IssueStatus.DAMAGED
        if _recent_clear(affected, resolve_clear_laps):
            return IssueStatus.PROTECTED
        return IssueStatus.DAMAGED

    # --- not enough evidence --------------------------------------------------
    if trend == Trend.INSUFFICIENT_EVIDENCE:
        if not ever:
            return IssueStatus.UNKNOWN
        # seen but too few laps to trend
        return IssueStatus.NEW if present_now else IssueStatus.UNKNOWN

    # --- never observed -------------------------------------------------------
    if not ever:
        return IssueStatus.UNKNOWN

    # --- resolved: clear for the last N valid laps ----------------------------
    if not present_now and _recent_clear(affected, resolve_clear_laps):
        return IssueStatus.RESOLVED

    # --- newly appeared this session (only recently seen) ---------------------
    seen_laps = sum(1 for a in affected if a)
    if (seen_laps <= 1 and present_now
            and total_valid_laps and total_valid_laps <= new_recent_laps):
        return IssueStatus.NEW

    # --- present now: ACTIVE / RECOVERING -------------------------------------
    if present_now:
        if trend == Trend.IMPROVING:
            return IssueStatus.RECOVERING
        return IssueStatus.ACTIVE

    # --- absent now but not yet resolved (recently cleared) -------------------
    if trend == Trend.IMPROVING:
        return IssueStatus.RECOVERING
    # absent + steady with prior presence but not enough clear laps → STABLE-ish;
    # keep ACTIVE until RESOLVE_CLEAR_LAPS is met to avoid premature resolution.
    return IssueStatus.STABLE if _recent_clear(affected, 2) else IssueStatus.ACTIVE
