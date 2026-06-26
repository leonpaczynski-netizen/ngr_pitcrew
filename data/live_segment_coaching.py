"""Segment-Aware Live Coaching Rules — Group 17K.

Pure Python, no PyQt6.

Architecture boundary:
  - Reads: data.live_segment_resolver (LiveSegmentResolverResult, LiveSegmentMatch,
           LiveSegmentResolutionStatus, LiveSegmentResolutionConfidence)
  - Reads: data.track_issue_enrichment (EnrichedTelemetryIssue — issue history context)
  - Does NOT own: segment detection, AI prompt building, voice TTS
  - Does NOT write files
  - Does NOT make real AI calls
  - Does NOT invent corner names when segment is unresolved
  - Does NOT use seed-only data as trusted live coaching truth
  - Does NOT treat Porsche calibration behaviour as universal track truth

Design rules:
  - All coaching rules are deterministic — same inputs → same output
  - Cue text uses the segment display_name only when confidence is MEDIUM or above
  - When segment is unresolved: return no_call with suppression_reason, not fake advice
  - When confidence is LOW: return cue at LOW or MEDIUM priority with explicit basis
  - Anti-spam: cooldown by cue_type+segment, max cues per lap, min progress delta
  - Multiple simultaneous cues are suppressed unless config.allow_multi_cue is True
  - Setup implications are NOT spoken as live driving cues (those belong in AI analysis)

Text generation rules:
  - Cue text is driving-technique focused — no setup suggestions, no invented corner names
  - If segment display_name is known: use it in the cue text
  - If not: use generic positional language ("here", "in this section", "at this point")
  - Under 120 characters where possible

Deferred:
  - Text-to-speech / voice announcement integration
  - Real-time track-auto-detection
  - PTT marker capture
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class LiveCoachingCueType(str, Enum):
    BRAKING_STABILITY = "braking_stability"   # earlier/smoother braking
    BRAKE_RELEASE     = "brake_release"        # trail-braking / release timing
    ROTATION          = "rotation"             # corner entry / mid-corner attitude
    THROTTLE_PICKUP   = "throttle_pickup"      # smooth power application on exit
    EXIT_DRIVE        = "exit_drive"           # car square / full throttle sooner
    GEAR_CHOICE       = "gear_choice"          # wrong gear through segment
    SHORT_SHIFT       = "short_shift"          # upshift before limiter
    LIMITER_WARNING   = "limiter_warning"      # hitting rev limit
    FUEL_SAVE         = "fuel_save"            # lift-and-coast opportunity
    KERB_CAUTION      = "kerb_caution"         # high-kerb or bump warning
    TYRE_MANAGEMENT   = "tyre_management"      # tyre-load / heat management
    TRACK_LIMITS      = "track_limits"         # track limits warning
    NO_CALL           = "no_call"              # no cue generated


class LiveCoachingPriority(str, Enum):
    LOW    = "low"
    MEDIUM = "medium"
    HIGH   = "high"
    URGENT = "urgent"


class LiveCoachingSuppressionReason(str, Enum):
    NO_SEGMENT            = "no_segment"            # live segment unresolved
    LOW_CONFIDENCE        = "low_confidence"        # confidence too low to advise
    UNREVIEWED_MODEL      = "unreviewed_model"      # segment model not reviewed
    LOW_ISSUE_CONFIDENCE  = "low_issue_confidence"  # enriched issue match is weak
    UNRESOLVED_ISSUE      = "unresolved_issue"      # enriched issues unresolved
    REJECTED_SEGMENT      = "rejected_segment"      # segment is rejected
    NEEDS_MORE_LAPS       = "needs_more_laps"       # segment not enough calibration
    SEED_ONLY             = "seed_only"             # only seed data available
    COOLDOWN              = "cooldown"              # same cue too recent
    MAX_CUES_REACHED      = "max_cues_reached"      # lap cue limit hit
    NO_MATCHING_RULE      = "no_matching_rule"      # no rule fires for this situation
    DISABLED              = "disabled"              # feature disabled in config


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class LiveCoachingCue:
    """A single actionable driving cue, fully resolved and ready for display."""
    cue_type: LiveCoachingCueType
    priority: LiveCoachingPriority
    text: str
    basis_segment_id: Optional[str] = None
    basis_segment_display_name: str = ""
    basis_segment_type: str = ""
    basis_issue_type: Optional[str] = None
    issue_repetition_count: int = 0    # how many laps exhibited this issue at this segment
    match_confidence: str = "unknown"  # "high"|"medium"|"low"|"unknown"
    created_at_lap: Optional[int] = None
    created_at_progress: Optional[float] = None


@dataclass
class LiveCoachingDecision:
    """Full output of build_live_coaching_decision().

    When suppressed=True, cue is None and suppression_reason gives the reason.
    When suppressed=False, cue is the actionable cue (cue_type != no_call).
    """
    suppressed: bool
    cue: Optional[LiveCoachingCue] = None
    suppression_reason: Optional[LiveCoachingSuppressionReason] = None
    all_candidates: list[LiveCoachingCue] = field(default_factory=list)
    debug_info: dict = field(default_factory=dict)


@dataclass
class LiveCoachingConfig:
    """Tuneable parameters for build_live_coaching_decision()."""
    enable_fuel_save_cues: bool = False     # opt-in: fuel-save cues only when strategy allows
    enable_kerb_cues: bool = True           # show kerb/bump caution cues
    enable_tyre_management_cues: bool = False  # opt-in: usually noisy
    allow_multi_cue: bool = False           # suppress if True: only the highest priority cue fires
    min_progress_delta_between_same_segment_cue: float = 0.10  # 10% lap progress
    suppress_same_cue_for_laps: int = 3    # suppress same cue_type+segment for N laps
    max_cues_per_lap: int = 3              # cap total cues per lap (checked via previous_cues)
    min_issue_repetitions: int = 2         # require issue at ≥ N laps before firing cue
    suppress_on_low_confidence: bool = True    # suppress when confidence is LOW or UNKNOWN
    suppress_on_needs_more_laps: bool = True   # suppress when segment has needs_more_laps


# ---------------------------------------------------------------------------
# Cue text templates
# Key: (issue_type_value, segment_type_value_or_None_for_any)
# Value: (cue_type, base_priority, text_template)
# {segment} → replaced with display_name; removed when display_name unavailable
# ---------------------------------------------------------------------------

_CUE_TEMPLATE_TABLE: list[tuple[str, Optional[str], LiveCoachingCueType, LiveCoachingPriority, str]] = [
    # issue_type, segment_type, cue_type, base_priority, text
    ("brake_lock", "braking_zone",
     LiveCoachingCueType.BRAKING_STABILITY, LiveCoachingPriority.HIGH,
     "Brake a touch earlier into {segment} and release smoother — avoid steering while pressure is still high."),
    ("brake_lock", "corner_entry",
     LiveCoachingCueType.BRAKING_STABILITY, LiveCoachingPriority.MEDIUM,
     "Settle the brakes before rotating into {segment} — lock-up mid-entry unsettles the car."),
    ("brake_lock", None,
     LiveCoachingCueType.BRAKING_STABILITY, LiveCoachingPriority.MEDIUM,
     "Braking too hard here — try a touch earlier and bleed off smoother."),
    ("wheelspin", "apex_zone",
     LiveCoachingCueType.THROTTLE_PICKUP, LiveCoachingPriority.MEDIUM,
     "Unwind the wheel before adding throttle through {segment} — progressive pickup keeps grip."),
    ("wheelspin", "corner_exit",
     LiveCoachingCueType.THROTTLE_PICKUP, LiveCoachingPriority.MEDIUM,
     "Smoother throttle pickup through {segment} — squeeze it in rather than stabbing the pedal."),
    ("wheelspin", "traction_zone",
     LiveCoachingCueType.THROTTLE_PICKUP, LiveCoachingPriority.MEDIUM,
     "Car is spinning the rears through the traction zone — unwind steering before adding power."),
    ("wheelspin", None,
     LiveCoachingCueType.THROTTLE_PICKUP, LiveCoachingPriority.LOW,
     "Progressive on the throttle here — the rears are spinning."),
    ("oversteer", "apex_zone",
     LiveCoachingCueType.ROTATION, LiveCoachingPriority.MEDIUM,
     "Repeated oversteer through {segment} — check if you're trailing the brakes too deep into the apex."),
    ("oversteer", "corner_exit",
     LiveCoachingCueType.ROTATION, LiveCoachingPriority.MEDIUM,
     "Exit oversteer at {segment} — get the car square before going full throttle."),
    ("oversteer", None,
     LiveCoachingCueType.ROTATION, LiveCoachingPriority.LOW,
     "Car is oversteering here — square it up before applying power."),
    ("understeer", "corner_entry",
     LiveCoachingCueType.ROTATION, LiveCoachingPriority.MEDIUM,
     "Understeer into {segment} — try a later apex or a touch more initial rotation."),
    ("understeer", "apex_zone",
     LiveCoachingCueType.ROTATION, LiveCoachingPriority.MEDIUM,
     "Car pushing through {segment} apex — carry less entry speed or wait for the car to settle."),
    ("understeer", None,
     LiveCoachingCueType.ROTATION, LiveCoachingPriority.LOW,
     "Car is understeering here — ease the entry speed or give it more rotation."),
    ("poor_exit_drive", "corner_exit",
     LiveCoachingCueType.EXIT_DRIVE, LiveCoachingPriority.MEDIUM,
     "Straighten the wheel sooner through {segment} and get back to full throttle earlier."),
    ("poor_exit_drive", "traction_zone",
     LiveCoachingCueType.EXIT_DRIVE, LiveCoachingPriority.MEDIUM,
     "Get the car square sooner through the traction zone — power delayed here costs lap time."),
    ("poor_exit_drive", None,
     LiveCoachingCueType.EXIT_DRIVE, LiveCoachingPriority.LOW,
     "Exit drive not clean here — aim to be fully square and on power sooner."),
    ("wrong_gear", "apex_zone",
     LiveCoachingCueType.GEAR_CHOICE, LiveCoachingPriority.MEDIUM,
     "Check your gear through {segment} — one higher may give better drive out."),
    ("wrong_gear", "corner_exit",
     LiveCoachingCueType.GEAR_CHOICE, LiveCoachingPriority.MEDIUM,
     "Gear selection through {segment} exit — try one up if the engine is pulling weak."),
    ("wrong_gear", None,
     LiveCoachingCueType.GEAR_CHOICE, LiveCoachingPriority.LOW,
     "Check your gear here — incorrect ratio is costing exit drive."),
    ("limiter_hit", "straight",
     LiveCoachingCueType.SHORT_SHIFT, LiveCoachingPriority.LOW,
     "Upshift sooner on the straight — hitting the limiter loses time, short shift keeps momentum."),
    ("limiter_hit", None,
     LiveCoachingCueType.LIMITER_WARNING, LiveCoachingPriority.LOW,
     "You're hitting the rev limiter — upshift earlier or check gear ratios."),
    ("fuel_saving_opportunity", "straight",
     LiveCoachingCueType.FUEL_SAVE, LiveCoachingPriority.LOW,
     "Lift-and-coast opportunity on the straight — ease off early to save fuel."),
    ("fuel_saving_opportunity", None,
     LiveCoachingCueType.FUEL_SAVE, LiveCoachingPriority.LOW,
     "Fuel-save opportunity here — consider lifting early."),
    ("tyre_wear_hotspot", None,
     LiveCoachingCueType.TYRE_MANAGEMENT, LiveCoachingPriority.LOW,
     "High tyre load here — ease the inputs to manage wear through this section."),
]

# Lookup: (issue_type, segment_type) → first matching template; most specific first
# None segment_type matches any segment → acts as fallback


def _lookup_cue_template(
    issue_type: str,
    segment_type: str,
) -> Optional[tuple[LiveCoachingCueType, LiveCoachingPriority, str]]:
    """Return the best (cue_type, priority, template) for this issue+segment pair.

    Tries exact segment_type match first; falls back to None (any-segment) match.
    Returns None if no rule exists.
    """
    # Exact match
    for it, st, cue_type, priority, template in _CUE_TEMPLATE_TABLE:
        if it == issue_type and st == segment_type:
            return cue_type, priority, template
    # Any-segment fallback
    for it, st, cue_type, priority, template in _CUE_TEMPLATE_TABLE:
        if it == issue_type and st is None:
            return cue_type, priority, template
    return None


def _format_cue_text(template: str, segment_display_name: str) -> str:
    """Substitute {segment} in template; remove the reference gracefully when name unavailable."""
    if segment_display_name:
        return template.replace("{segment}", segment_display_name)
    # Strip common positional phrases that would read strangely without a name
    text = template
    for phrase in [" into {segment}", " through {segment}", " at {segment}",
                   " for {segment}", " through {segment} ", "{segment} "]:
        text = text.replace(phrase, " ")
    text = text.replace("{segment}", "")
    # Collapse multiple spaces
    while "  " in text:
        text = text.replace("  ", " ")
    return text.strip()


# ---------------------------------------------------------------------------
# Priority ordering for suppression logic
# ---------------------------------------------------------------------------

_PRIORITY_ORDER = [
    LiveCoachingPriority.LOW,
    LiveCoachingPriority.MEDIUM,
    LiveCoachingPriority.HIGH,
    LiveCoachingPriority.URGENT,
]


def _downgrade_priority(p: LiveCoachingPriority, levels: int = 1) -> LiveCoachingPriority:
    idx = _PRIORITY_ORDER.index(p)
    return _PRIORITY_ORDER[max(0, idx - levels)]


# ---------------------------------------------------------------------------
# Confidence helper (uses string values from LiveSegmentResolutionConfidence)
# ---------------------------------------------------------------------------

def _confidence_is_usable(confidence_value: str) -> bool:
    """Return True when confidence is MEDIUM or above."""
    return confidence_value in ("medium", "high")


# ---------------------------------------------------------------------------
# Cooldown helpers
# ---------------------------------------------------------------------------

def _cooldown_suppressed(
    candidate: LiveCoachingCue,
    previous_cues: list[LiveCoachingCue],
    config: LiveCoachingConfig,
    current_lap: Optional[int],
) -> bool:
    """Return True if the candidate cue is suppressed by same-cue cooldown rules.

    Checks:
    1. Same cue_type + basis_segment_id within suppress_same_cue_for_laps laps.
    2. Same cue_type + basis_segment_id within min_progress_delta_between_same_segment_cue.

    NOTE: max_cues_per_lap is checked separately in the main function (Step 7) so
    that the correct suppression_reason is returned (MAX_CUES_REACHED, not COOLDOWN).
    """
    if not previous_cues:
        return False

    # Same cue_type + segment within N laps
    for prev in reversed(previous_cues):
        if (prev.cue_type == candidate.cue_type
                and prev.basis_segment_id == candidate.basis_segment_id
                and prev.basis_segment_id is not None):
            if current_lap is not None and prev.created_at_lap is not None:
                lap_diff = abs(current_lap - prev.created_at_lap)
                if lap_diff < config.suppress_same_cue_for_laps:
                    return True
            # Progress delta check
            if (candidate.created_at_progress is not None
                    and prev.created_at_progress is not None):
                progress_diff = abs(candidate.created_at_progress - prev.created_at_progress)
                if progress_diff < config.min_progress_delta_between_same_segment_cue:
                    return True
    return False


# ---------------------------------------------------------------------------
# Main rule engine
# ---------------------------------------------------------------------------

def build_live_coaching_decision(
    live_segment_result,
    enriched_issues=None,
    current_sample=None,
    config: Optional[LiveCoachingConfig] = None,
    previous_cues: Optional[list[LiveCoachingCue]] = None,
    current_lap: Optional[int] = None,
    current_progress: Optional[float] = None,
) -> LiveCoachingDecision:
    """Build a segment-aware live coaching decision from current position + issue history.

    Arguments:
      live_segment_result: LiveSegmentResolverResult from data.live_segment_resolver
      enriched_issues:     list[EnrichedTelemetryIssue] from data.track_issue_enrichment;
                           may be None or empty if no issue history is available
      current_sample:      duck-typed telemetry sample or LivePosition; informational only
      config:              LiveCoachingConfig; uses defaults if None
      previous_cues:       list of prior LiveCoachingCue objects for cooldown logic
      current_lap:         current lap number (for cooldown and text context)
      current_progress:    current lap progress 0.0–1.0 (for cooldown)

    Returns:
      LiveCoachingDecision with .suppressed, .cue, .suppression_reason, .debug_info

    Never raises.
    """
    if config is None:
        config = LiveCoachingConfig()
    if previous_cues is None:
        previous_cues = []
    enriched_issues = enriched_issues or []

    debug: dict = {}

    try:
        # ── Step 1: Gate on live segment resolution ───────────────────────
        try:
            from data.live_segment_resolver import (
                LiveSegmentResolutionStatus,
                LiveSegmentResolutionConfidence,
            )
            status = live_segment_result.status
            match = live_segment_result.match
            model_source = getattr(live_segment_result, "model_source", "missing")

            if status not in (
                LiveSegmentResolutionStatus.MATCHED,
                LiveSegmentResolutionStatus.MATCHED_NEAREST,
            ) or match is None:
                debug["suppression_reason"] = "no_segment"
                debug["live_segment_status"] = status.value if hasattr(status, "value") else str(status)
                return LiveCoachingDecision(
                    suppressed=True,
                    suppression_reason=LiveCoachingSuppressionReason.NO_SEGMENT,
                    debug_info=debug,
                )

            conf_value = match.confidence.value if hasattr(match.confidence, "value") else str(match.confidence)
            segment_type = match.segment_type
            segment_id = match.segment_id
            segment_display_name = match.display_name or ""

        except Exception as exc:
            debug["error"] = f"live_segment import error: {exc}"
            return LiveCoachingDecision(
                suppressed=True,
                suppression_reason=LiveCoachingSuppressionReason.NO_SEGMENT,
                debug_info=debug,
            )

        # ── Step 2: Gate on segment model quality ─────────────────────────
        if model_source == "seed_only":
            debug["suppression_reason"] = "seed_only"
            return LiveCoachingDecision(
                suppressed=True,
                suppression_reason=LiveCoachingSuppressionReason.SEED_ONLY,
                debug_info=debug,
            )

        # Gate on segment review status from warnings (REJECTED / NEEDS_MORE_LAPS)
        match_warnings_str = " ".join(match.warnings).lower()
        if "rejected" in match_warnings_str:
            debug["suppression_reason"] = "rejected_segment"
            return LiveCoachingDecision(
                suppressed=True,
                suppression_reason=LiveCoachingSuppressionReason.REJECTED_SEGMENT,
                debug_info=debug,
            )
        needs_more_laps_flag = "needs more calibration" in match_warnings_str or "needs_more_laps" in match_warnings_str
        if needs_more_laps_flag and config.suppress_on_needs_more_laps:
            debug["suppression_reason"] = "needs_more_laps"
            return LiveCoachingDecision(
                suppressed=True,
                suppression_reason=LiveCoachingSuppressionReason.NEEDS_MORE_LAPS,
                debug_info=debug,
            )

        # Suppress on low/unknown confidence if configured
        if config.suppress_on_low_confidence and not _confidence_is_usable(conf_value):
            debug["suppression_reason"] = "low_confidence"
            debug["confidence"] = conf_value
            return LiveCoachingDecision(
                suppressed=True,
                suppression_reason=LiveCoachingSuppressionReason.LOW_CONFIDENCE,
                debug_info=debug,
            )

        debug["segment_id"] = segment_id
        debug["segment_type"] = segment_type
        debug["segment_display_name"] = segment_display_name
        debug["confidence"] = conf_value
        debug["model_source"] = model_source

        # ── Step 3: Find matching enriched issues at this segment ─────────
        relevant_issues = _find_relevant_issues(enriched_issues, segment_id, segment_type)
        debug["relevant_issue_count"] = len(relevant_issues)

        if not relevant_issues:
            debug["suppression_reason"] = "no_matching_rule"
            return LiveCoachingDecision(
                suppressed=True,
                suppression_reason=LiveCoachingSuppressionReason.NO_MATCHING_RULE,
                debug_info=debug,
            )

        # ── Step 4: Build candidate cues ─────────────────────────────────
        candidates = _build_candidates(
            relevant_issues,
            segment_id,
            segment_display_name,
            segment_type,
            conf_value,
            current_lap,
            current_progress,
            config,
        )

        if not candidates:
            debug["suppression_reason"] = "no_matching_rule"
            return LiveCoachingDecision(
                suppressed=True,
                suppression_reason=LiveCoachingSuppressionReason.NO_MATCHING_RULE,
                debug_info=debug,
            )

        # ── Step 5: Sort candidates by priority descending ────────────────
        candidates.sort(key=lambda c: _PRIORITY_ORDER.index(c.priority), reverse=True)
        best = candidates[0]
        debug["candidate_count"] = len(candidates)

        # ── Step 6: Cooldown check on best candidate ──────────────────────
        if _cooldown_suppressed(best, previous_cues, config, current_lap):
            debug["suppression_reason"] = "cooldown"
            return LiveCoachingDecision(
                suppressed=True,
                suppression_reason=LiveCoachingSuppressionReason.COOLDOWN,
                all_candidates=candidates,
                debug_info=debug,
            )

        # ── Step 7: Max cues per lap check ────────────────────────────────
        if current_lap is not None:
            cues_this_lap = [c for c in previous_cues if c.created_at_lap == current_lap]
            if len(cues_this_lap) >= config.max_cues_per_lap:
                debug["suppression_reason"] = "max_cues_reached"
                return LiveCoachingDecision(
                    suppressed=True,
                    suppression_reason=LiveCoachingSuppressionReason.MAX_CUES_REACHED,
                    all_candidates=candidates,
                    debug_info=debug,
                )

        # ── Step 8: Return the decision ───────────────────────────────────
        debug["live_coaching_cue_type"] = best.cue_type.value
        debug["live_coaching_priority"] = best.priority.value
        debug["live_coaching_basis_segment"] = segment_id
        return LiveCoachingDecision(
            suppressed=False,
            cue=best,
            suppression_reason=None,
            all_candidates=candidates,
            debug_info=debug,
        )

    except Exception as exc:
        return LiveCoachingDecision(
            suppressed=True,
            suppression_reason=LiveCoachingSuppressionReason.NO_SEGMENT,
            debug_info={"error": f"Unexpected error in build_live_coaching_decision: {exc}"},
        )


# ---------------------------------------------------------------------------
# Issue relevance filter
# ---------------------------------------------------------------------------

def _find_relevant_issues(
    enriched_issues: list,
    segment_id: str,
    segment_type: str,
) -> list:
    """Return enriched issues that are relevant to the current segment.

    Relevance: matched_segment_id == segment_id (exact) OR
               matched_segment_type == segment_type (type fallback if no ID match).
    Excludes UNRESOLVED issues (match_method == "unresolved").
    """
    try:
        from data.track_issue_enrichment import TrackIssueEnrichmentConfidence
        exact = [
            ei for ei in enriched_issues
            if (getattr(ei, "matched_segment_id", None) == segment_id
                and ei.matched_segment_id is not None
                and getattr(ei, "confidence", None) != TrackIssueEnrichmentConfidence.UNRESOLVED)
        ]
        if exact:
            return exact
        # Fallback: same segment type
        return [
            ei for ei in enriched_issues
            if (getattr(ei, "matched_segment_type", None) == segment_type
                and ei.matched_segment_type is not None
                and getattr(ei, "confidence", None) != TrackIssueEnrichmentConfidence.UNRESOLVED)
        ]
    except Exception:
        # If import fails, do best-effort filtering without confidence check
        exact = [
            ei for ei in enriched_issues
            if getattr(ei, "matched_segment_id", None) == segment_id and ei.matched_segment_id is not None
        ]
        if exact:
            return exact
        return [
            ei for ei in enriched_issues
            if getattr(ei, "matched_segment_type", None) == segment_type and ei.matched_segment_type is not None
        ]


# ---------------------------------------------------------------------------
# Candidate builder
# ---------------------------------------------------------------------------

def _build_candidates(
    relevant_issues: list,
    segment_id: str,
    segment_display_name: str,
    segment_type: str,
    confidence_value: str,
    current_lap: Optional[int],
    current_progress: Optional[float],
    config: LiveCoachingConfig,
) -> list[LiveCoachingCue]:
    """Build LiveCoachingCue candidates from relevant enriched issues."""
    # Group issues by issue_type → count unique laps (repetitions)
    from collections import defaultdict
    repetitions: dict[str, set] = defaultdict(set)  # issue_type → set of lap numbers
    issues_by_type: dict[str, list] = defaultdict(list)

    for ei in relevant_issues:
        issue_type = _get_issue_type_value(ei)
        if not issue_type:
            continue
        lap_num = getattr(ei, "raw", None)
        if lap_num is not None:
            lap_num = getattr(lap_num, "lap_num", None)
        if lap_num is not None:
            repetitions[issue_type].add(lap_num)
        issues_by_type[issue_type].append(ei)

    candidates: list[LiveCoachingCue] = []

    for issue_type, rep_laps in repetitions.items():
        rep_count = len(rep_laps)
        if rep_count < config.min_issue_repetitions:
            continue

        # Special gates
        if issue_type == "fuel_saving_opportunity" and not config.enable_fuel_save_cues:
            continue
        if issue_type == "tyre_wear_hotspot" and not config.enable_tyre_management_cues:
            continue

        rule = _lookup_cue_template(issue_type, segment_type)
        if rule is None:
            continue

        cue_type, base_priority, template = rule

        # Special gate for kerb_caution (only if config allows)
        if cue_type == LiveCoachingCueType.KERB_CAUTION and not config.enable_kerb_cues:
            continue

        # Downgrade priority if low confidence
        priority = base_priority
        if confidence_value == "low":
            priority = _downgrade_priority(priority)

        # Build cue text — use segment display name when confidence allows
        use_name = _confidence_is_usable(confidence_value) and bool(segment_display_name)
        text = _format_cue_text(template, segment_display_name if use_name else "")

        cue = LiveCoachingCue(
            cue_type=cue_type,
            priority=priority,
            text=text,
            basis_segment_id=segment_id,
            basis_segment_display_name=segment_display_name,
            basis_segment_type=segment_type,
            basis_issue_type=issue_type,
            issue_repetition_count=rep_count,
            match_confidence=confidence_value,
            created_at_lap=current_lap,
            created_at_progress=current_progress,
        )
        candidates.append(cue)

    return candidates


def _get_issue_type_value(enriched_issue) -> Optional[str]:
    """Extract the string value of issue_type from an EnrichedTelemetryIssue safely."""
    try:
        raw = getattr(enriched_issue, "raw", None)
        if raw is None:
            return None
        issue_type = getattr(raw, "issue_type", None)
        if issue_type is None:
            return None
        return issue_type.value if hasattr(issue_type, "value") else str(issue_type)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Prompt integration helper
# ---------------------------------------------------------------------------

def format_live_coaching_for_prompt(decision: LiveCoachingDecision) -> str:
    """Return a compact prompt block for the coaching decision.

    Returns "" when no actionable cue is available.
    Safe, never raises.

    Format when cue available:
      ## Live Coaching Cue
      Brake a touch earlier into T1 and release smoother — avoid steering while pressure is still high.
      Basis: repeated brake lock at T1 Braking Zone (3 laps). Confidence: high.

    Format when suppressed:
      (empty string — cue suppression does not clutter the prompt)
    """
    try:
        if decision.suppressed or decision.cue is None:
            return ""
        cue = decision.cue
        lines = ["## Live Coaching Cue"]
        lines.append(cue.text)
        basis_parts = []
        if cue.basis_issue_type:
            rep = cue.issue_repetition_count
            rep_str = f"{rep} laps" if rep > 1 else "1 lap"
            issue_label = cue.basis_issue_type.replace("_", " ")
            if cue.basis_segment_display_name:
                basis_parts.append(f"repeated {issue_label} at {cue.basis_segment_display_name} ({rep_str})")
            else:
                basis_parts.append(f"repeated {issue_label} at this segment ({rep_str})")
        if cue.match_confidence:
            basis_parts.append(f"confidence: {cue.match_confidence}")
        if basis_parts:
            lines.append(f"Basis: {'. '.join(basis_parts)}.")
        return "\n".join(lines)
    except Exception:
        return ""


def get_live_coaching_debug_metadata(decision: LiveCoachingDecision) -> dict:
    """Return debug metadata dict suitable for injection into structured_payload."""
    try:
        meta: dict = {
            "live_coaching_cue_included": not decision.suppressed,
        }
        if decision.suppressed:
            meta["live_coaching_suppression_reason"] = (
                decision.suppression_reason.value
                if decision.suppression_reason and hasattr(decision.suppression_reason, "value")
                else str(decision.suppression_reason)
            )
            meta["live_coaching_cue_type"] = "no_call"
            meta["live_coaching_priority"] = None
            meta["live_coaching_basis_segment"] = None
        else:
            c = decision.cue
            meta["live_coaching_cue_type"] = c.cue_type.value if c else "no_call"
            meta["live_coaching_priority"] = c.priority.value if c else None
            meta["live_coaching_basis_segment"] = c.basis_segment_id if c else None
            meta["live_coaching_suppression_reason"] = None
        return meta
    except Exception:
        return {"live_coaching_cue_included": False, "live_coaching_error": "metadata_error"}
