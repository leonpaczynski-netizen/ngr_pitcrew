"""Corner-level telemetry learning for GT7 VR Dashboard (Group 16).

Detects repeated driving/setup issues at specific corners across multiple
practice laps.  Stores learned patterns by car+track+corner+issue_type so
the AI can verify in later sessions whether a recommended fix worked.

Detection paths:
  PATH A — from event_positions_json in lap_records (always available).
            Detects: brake_lock, rear_wheelspin, rear_oversteer.
  PATH B — from frame dicts in lap_telemetry (when stored).
            Detects: above + poor_drive_out, exit_gear_too_low, exit_gear_too_high,
            early_limiter_on_straight, late_upshift, rear_wheelspin.

Corner IDs use an XZ world-position grid (100 m buckets), giving consistent
IDs across detection paths and between sessions on the same track.

Architecture:
  - Relies on data already in DB — no track map, no auto-detection.
  - The active track is always passed as a parameter from Event Planner.
  - Does NOT import Qt, recorder, or any UI module.
  - Degrades gracefully: returns [] if required data fields are absent.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import datetime, timezone


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
ISSUE_TYPES: frozenset[str] = frozenset({
    "brake_lock",
    "rear_wheelspin",
    "front_understeer",
    "rear_oversteer",
    "exit_instability",
    "tyre_overheat",
    "fuel_loss",
    "traction_loss",
    "poor_drive_out",
    "exit_gear_too_low",
    "exit_gear_too_high",
    "early_limiter_on_straight",
    "late_upshift",
    "early_upshift",
    "unstable_downshift",
    "fuel_inefficient_gear_choice",
    "strong_drive_confirmed",
})

PHASES: frozenset[str] = frozenset({
    "braking",
    "entry",
    "apex",
    "mid_corner",
    "exit",
    "following_straight",
})

# Fix verification status codes
FIX_STATUS_FIXED        = "fixed"
FIX_STATUS_IMPROVED     = "improved"
FIX_STATUS_UNCHANGED    = "unchanged"
FIX_STATUS_WORSE        = "worse"
FIX_STATUS_INSUFFICIENT = "not_enough_data"

# Detection thresholds (conservative)
_MIN_LAP_COUNT          = 3      # min laps with event before flagging as repeated
_MIN_FRACTION           = 0.30   # min fraction of valid laps before flagging
_FIX_THRESHOLD_FIXED    = 0.10   # <= 10 % of previous rate → fixed
_FIX_THRESHOLD_IMPROVED = 0.50   # <= 50 % of previous rate → improved
_FIX_THRESHOLD_WORSE    = 1.50   # >= 150 % of previous rate → worse
_MIN_LAPS_FOR_VERIFY    = 3      # min laps in current session for fix verification

# Setup advice bridge
SETUP_ADVICE_MAP: dict[str, list[str]] = {
    "brake_lock": [
        "Move brake balance toward rear",
        "Reduce front brake bias to ease front lock risk",
        "Increase front compression/rebound damping for braking stability",
        "Advise trail braking — release progressively before turn-in",
        "Differential: increase braking sensitivity",
        "Check front tyre temperatures for overheating under braking",
    ],
    "rear_wheelspin": [
        "Increase LSD acceleration sensitivity",
        "Raise rear ride height slightly to reduce squat on exit",
        "Soften rear compression damping",
        "Increase rear downforce where available",
        "Advise smoother throttle application at corner exit",
        "Test one gear higher at corner exit to reduce torque demand",
    ],
    "poor_drive_out": [
        "Review exit gear — trial one gear higher",
        "Increase LSD acceleration sensitivity for better traction",
        "Soften rear compression to improve squat control",
        "Advise smooth progressive throttle — avoid snap application",
        "Check final drive / gear ratios for corner exit torque",
        "Review tyre temperature — overheating reduces traction",
    ],
    "exit_gear_too_low": [
        "Trial one gear higher at corner exit",
        "Lengthen the relevant gear ratio to reduce wheelspin",
        "Compare exit speed and acceleration across laps after change",
        "Review fuel consumption impact of gear change",
    ],
    "exit_gear_too_high": [
        "Trial one gear lower at corner exit",
        "Shorten the relevant gear ratio for better torque response",
        "Compare exit speed and acceleration before and after",
        "Check if car is below power band on exit",
    ],
    "early_limiter_on_straight": [
        "Lengthen top gear or final drive ratio",
        "Check top speed vs theoretical maximum",
        "Verify fuel consumption remains acceptable at longer ratio",
        "Compare lap time with and without early limiter contact",
    ],
    "rear_oversteer": [
        "Increase rear downforce where available",
        "Soften rear anti-roll bar",
        "Increase rear toe-in slightly",
        "Increase LSD acceleration sensitivity to stabilise corner exit",
        "Advise earlier, smoother throttle application",
        "Check rear tyre temperatures",
    ],
    "front_understeer": [
        "Soften front springs or anti-roll bar",
        "Increase front downforce where available",
        "Reduce front ride height",
        "Advise reducing corner entry speed",
        "Adjust camber / toe for better front contact patch",
    ],
    "tyre_overheat": [
        "Review tyre compound selection",
        "Reduce tyre pressure if too high",
        "Adjust camber for better contact patch",
        "Moderate aggressive throttle/brake inputs at affected corner",
    ],
    "exit_instability": [
        "Increase rear mechanical grip (ride height, springs, LSD)",
        "Reduce rear downforce if causing snap oversteer",
        "Advise earlier throttle application in the corner",
        "Check tyre temperatures for rear overheating",
    ],
    "strong_drive_confirmed": [
        "Good exit drive — maintain current setup and technique",
        "Document gear and throttle pattern for reference",
    ],
    "unstable_downshift": [
        "Shift later into the braking zone",
        "Trial higher minimum gear through this corner",
        "Advise blip throttle technique on downshift",
        "Check differential braking sensitivity",
    ],
    "late_upshift": [
        "Shift earlier to reduce time at rev limiter",
        "Lengthen gear ratio to delay limiter contact",
        "Review fuel economy impact of late upshift",
    ],
    "early_upshift": [
        "Delay upshift to stay in power band",
        "Shorten gear ratio for better torque in the relevant gear",
    ],
    "traction_loss": [
        "Increase LSD acceleration sensitivity",
        "Soften rear compression damping",
        "Advise later, smoother throttle application",
    ],
    "fuel_loss": [
        "Review throttle application pattern at this corner",
        "Consider a higher exit gear to save fuel on exit",
    ],
    "fuel_inefficient_gear_choice": [
        "Test one gear higher through this section",
        "Compare fuel use per lap before and after gear change",
    ],
}


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------
@dataclass
class CornerIssue:
    """Represents a repeated issue detected at a specific corner position."""
    car_id: int
    track: str
    corner_id: str          # XZ positional bucket, e.g. "P500_-200"
    lap_count: int          # number of laps where the issue was detected
    total_laps: int         # total valid laps analysed
    issue_type: str         # from ISSUE_TYPES
    phase: str              # from PHASES
    severity: float         # 0.0 – 1.0
    confidence: float       # 0.0 – 1.0
    evidence: str           # concise human-readable summary
    session_id: int = 0
    detected_at: str = ""


# ---------------------------------------------------------------------------
# Corner ID helpers
# ---------------------------------------------------------------------------
def _corner_id_from_xyz(x: float, z: float, bucket_m: int = 100) -> str:
    """Snap world XZ coordinates to a grid bucket used as corner identifier.

    100 m buckets give good corner separation on real circuits without
    splitting the same corner across multiple buckets.
    """
    bx = round(x / bucket_m) * bucket_m
    bz = round(z / bucket_m) * bucket_m
    return f"P{int(bx)}_{int(bz)}"


# ---------------------------------------------------------------------------
# PATH A: detect from event_positions_json (always available from lap_records)
# ---------------------------------------------------------------------------
def detect_issues_from_lap_records(
    laps: list[dict],
    car_id: int,
    track: str,
    session_id: int = 0,
) -> list[CornerIssue]:
    """Detect repeated corner issues from lap_records event_positions_json.

    Args:
        laps:  list of row dicts from get_session_laps() — must include
               event_positions_json (str or dict).
        car_id, track, session_id: metadata for CornerIssue records.

    Returns sorted list of CornerIssue where the issue appears on at least
    _MIN_LAP_COUNT laps OR at least _MIN_FRACTION of total valid laps.
    Returns [] if there is insufficient data — never fakes results.
    """
    if not laps:
        return []

    total_valid = len(laps)
    # (corner_id, issue_type, phase) → set of lap_num values where detected
    event_map: dict[tuple, set[int]] = {}

    for lap in laps:
        lap_num = int(lap.get("lap_num", 0))
        raw = lap.get("event_positions_json", "{}")
        try:
            positions = json.loads(raw) if isinstance(raw, str) else (raw or {})
        except Exception:
            continue  # malformed JSON — skip lap, don't fake data

        _collect_positions(positions, "lock_up",      "brake_lock",     "braking", lap_num, event_map)
        _collect_positions(positions, "wheelspin",    "rear_wheelspin", "exit",    lap_num, event_map)
        _collect_positions(positions, "oversteer",    "rear_oversteer", "exit",    lap_num, event_map)
        _collect_positions(positions, "over_braking", "brake_lock",     "braking", lap_num, event_map)

    return _threshold_and_build(event_map, total_valid, car_id, track, session_id, source="PATH-A")


def _collect_positions(
    positions: dict,
    key: str,
    issue_type: str,
    phase: str,
    lap_num: int,
    event_map: dict,
) -> None:
    """Helper: extract XZ positions and record (corner_id, issue_type, phase) occurrences."""
    for pos in positions.get(key, []):
        if len(pos) >= 3:
            cid = _corner_id_from_xyz(float(pos[0]), float(pos[2]))
            event_map.setdefault((cid, issue_type, phase), set()).add(lap_num)


def _threshold_and_build(
    event_map: dict[tuple, set[int]],
    total_valid: int,
    car_id: int,
    track: str,
    session_id: int,
    source: str = "",
) -> list[CornerIssue]:
    """Apply conservative thresholds and build CornerIssue list."""
    now_str = datetime.now(timezone.utc).isoformat(timespec="seconds")
    issues: list[CornerIssue] = []

    for (corner_id, issue_type, phase), lap_set in event_map.items():
        unique_laps = len(lap_set)
        fraction = unique_laps / total_valid if total_valid > 0 else 0.0

        if unique_laps < _MIN_LAP_COUNT and fraction < _MIN_FRACTION:
            continue  # one-off or below threshold — not a repeated issue

        severity   = min(1.0, round(unique_laps / 10.0, 2))
        confidence = min(1.0, round(fraction + 0.2, 2))
        src_tag    = f" [{source}]" if source else ""
        evidence   = (
            f"{issue_type.replace('_', ' ')} at corner {corner_id} "
            f"on {unique_laps} of {total_valid} laps ({fraction * 100:.0f}%){src_tag}"
        )
        issues.append(CornerIssue(
            car_id=car_id, track=track, corner_id=corner_id,
            lap_count=unique_laps, total_laps=total_valid,
            issue_type=issue_type, phase=phase,
            severity=severity, confidence=confidence,
            evidence=evidence,
            session_id=session_id, detected_at=now_str,
        ))

    return sorted(issues, key=lambda i: (-i.severity, i.corner_id))


# ---------------------------------------------------------------------------
# PATH B: detect from frame dicts (when lap_telemetry is stored)
# ---------------------------------------------------------------------------
def detect_corner_events_from_frames(frames: list[dict]) -> list[dict]:
    """Scan one lap's frame dicts and return structured corner events.

    Works on dicts produced by json.loads(asdict(TelemetryFrame)).
    Returns [] if frames is empty — never invents data.

    Each returned dict contains:
      corner_id, issue_type, phase, gear, rpm, speed_kmh, wheelspin
    """
    if not frames:
        return []

    events: list[dict] = []
    n = len(frames)

    # ── Corner exit detection ─────────────────────────────────────────────
    for i in range(1, n):
        prev = frames[i - 1]
        curr = frames[i]

        prev_brake = float(prev.get("brake", 0))
        curr_brake = float(curr.get("brake", 0))
        curr_throttle = float(curr.get("throttle", 0))
        speed = float(curr.get("speed_kmh", 0))

        if not (prev_brake > 0.1 and curr_brake < 0.05 and curr_throttle > 0.1 and speed > 15):
            continue

        pos_x = float(curr.get("pos_x", 0))
        pos_z = float(curr.get("pos_z", 0))
        corner_id = _corner_id_from_xyz(pos_x, pos_z)
        gear = int(curr.get("gear", 0))
        rpm  = float(curr.get("rpm", 0))

        wheelspin = _detect_wheelspin_frame(curr, speed)

        hits_limiter_early = any(
            frames[j].get("rev_limiter", False)
            for j in range(i + 1, min(i + 50, n))
        )

        if wheelspin and gear > 0 and gear <= 2:
            issue_type = "exit_gear_too_low"
        elif wheelspin:
            issue_type = "rear_wheelspin"
        elif hits_limiter_early:
            issue_type = "early_limiter_on_straight"
        else:
            issue_type = "poor_drive_out"

        events.append({
            "corner_id": corner_id, "issue_type": issue_type,
            "phase": "exit", "gear": gear, "rpm": round(rpm),
            "speed_kmh": round(speed, 1), "wheelspin": wheelspin,
        })

    # ── Brake lock detection ──────────────────────────────────────────────
    in_lock = False
    for frame in frames:
        speed_kmh = float(frame.get("speed_kmh", 0))
        speed_ms  = speed_kmh / 3.6
        brake     = float(frame.get("brake", 0))

        if speed_ms < 1.4:
            in_lock = False
            continue

        avg_wheel_ms = _avg_wheel_speed_ms(frame)
        is_locking = brake > 0.3 and avg_wheel_ms < speed_ms * 0.5 and speed_ms > 2.0

        if is_locking and not in_lock:
            in_lock = True
            pos_x = float(frame.get("pos_x", 0))
            pos_z = float(frame.get("pos_z", 0))
            events.append({
                "corner_id": _corner_id_from_xyz(pos_x, pos_z),
                "issue_type": "brake_lock", "phase": "braking",
                "gear": int(frame.get("gear", 0)), "rpm": round(float(frame.get("rpm", 0))),
                "speed_kmh": round(speed_kmh, 1), "wheelspin": False,
            })
        elif not is_locking:
            in_lock = False

    return events


def _detect_wheelspin_frame(frame: dict, speed_kmh: float) -> bool:
    """Return True if rear wheels are spinning faster than car speed."""
    wheel_rps  = frame.get("wheel_rps", [])
    tyre_radius = frame.get("tyre_radius", [])
    if len(wheel_rps) < 4 or len(tyre_radius) < 4:
        return False
    car_ms = speed_kmh / 3.6
    if car_ms < 1.0:
        return False
    rear_ms = (
        abs(float(wheel_rps[2])) * float(tyre_radius[2]) * 2 * math.pi +
        abs(float(wheel_rps[3])) * float(tyre_radius[3]) * 2 * math.pi
    ) / 2.0
    return rear_ms > car_ms * 1.3


def _avg_wheel_speed_ms(frame: dict) -> float:
    """Average linear wheel speed in m/s from frame dict."""
    wheel_rps  = frame.get("wheel_rps", [])
    tyre_radius = frame.get("tyre_radius", [])
    if len(wheel_rps) < 4 or len(tyre_radius) < 4:
        return 0.0
    return sum(
        abs(float(wheel_rps[k])) * float(tyre_radius[k]) * 2 * math.pi
        for k in range(4)
    ) / 4.0


def detect_issues_from_frame_data(
    per_lap_events: list[list[dict]],
    car_id: int,
    track: str,
    session_id: int = 0,
) -> list[CornerIssue]:
    """Aggregate per-lap corner events and return repeated issues.

    Args:
        per_lap_events: list (one item per lap) of lists returned by
                        detect_corner_events_from_frames().
    Returns [] when per_lap_events is empty or no threshold is met.
    """
    if not per_lap_events:
        return []

    total_laps = len(per_lap_events)
    event_map: dict[tuple, set[int]] = {}
    gear_map:  dict[tuple, list[int]] = {}

    for lap_idx, lap_events in enumerate(per_lap_events):
        seen_in_lap: set[tuple] = set()
        for ev in lap_events:
            key = (ev["corner_id"], ev["issue_type"], ev["phase"])
            if key not in seen_in_lap:
                event_map.setdefault(key, set()).add(lap_idx)
                gear_map.setdefault(key, []).append(ev.get("gear", 0))
                seen_in_lap.add(key)

    # Skip "strong_drive_confirmed" — it's a positive signal, not an issue
    filtered = {k: v for k, v in event_map.items() if k[1] != "strong_drive_confirmed"}

    # Enrich evidence with gear info for gearing issues
    now_str = datetime.now(timezone.utc).isoformat(timespec="seconds")
    issues: list[CornerIssue] = []
    for (corner_id, issue_type, phase), lap_set in filtered.items():
        unique_laps = len(lap_set)
        fraction = unique_laps / total_laps if total_laps > 0 else 0.0
        if unique_laps < _MIN_LAP_COUNT and fraction < _MIN_FRACTION:
            continue

        severity   = min(1.0, round(unique_laps / 10.0, 2))
        confidence = min(1.0, round(fraction + 0.2, 2))
        gears = gear_map.get((corner_id, issue_type, phase), [])
        gear_note = ""
        if gears:
            avg_gear = sum(gears) / len(gears)
            gear_note = f"; avg gear {avg_gear:.1f}"
        evidence = (
            f"{issue_type.replace('_', ' ')} at corner {corner_id} "
            f"on {unique_laps} of {total_laps} laps ({fraction * 100:.0f}%)"
            f"{gear_note} [PATH-B/frames]"
        )
        issues.append(CornerIssue(
            car_id=car_id, track=track, corner_id=corner_id,
            lap_count=unique_laps, total_laps=total_laps,
            issue_type=issue_type, phase=phase,
            severity=severity, confidence=confidence,
            evidence=evidence,
            session_id=session_id, detected_at=now_str,
        ))

    return sorted(issues, key=lambda i: (-i.severity, i.corner_id))


# ---------------------------------------------------------------------------
# Merge PATH A and PATH B results
# ---------------------------------------------------------------------------
def merge_issues(
    path_a: list[CornerIssue],
    path_b: list[CornerIssue],
) -> list[CornerIssue]:
    """Merge PATH A and PATH B, preferring PATH B for same (corner_id, issue_type)."""
    seen: dict[tuple, CornerIssue] = {}
    for iss in path_a:
        seen[(iss.corner_id, iss.issue_type)] = iss
    for iss in path_b:
        seen[(iss.corner_id, iss.issue_type)] = iss  # PATH B overwrites — richer data
    return sorted(seen.values(), key=lambda i: (-i.severity, i.corner_id))


# ---------------------------------------------------------------------------
# Fix verification
# ---------------------------------------------------------------------------
def verify_fix(
    previous_issues: list[dict],
    current_issues: list[CornerIssue],
) -> dict[str, str]:
    """Compare a previous session's corner issues to the current session.

    Args:
        previous_issues: dicts from get_previous_corner_issues() — must contain
                         corner_id, issue_type, lap_count, total_laps.
        current_issues:  newly detected issues from the current session.

    Returns dict keyed by "corner_id:issue_type" → FIX_STATUS_* constant.
    """
    curr_map: dict[str, CornerIssue] = {
        f"{i.corner_id}:{i.issue_type}": i for i in current_issues
    }
    result: dict[str, str] = {}

    for prev in previous_issues:
        key = f"{prev.get('corner_id', '')}:{prev.get('issue_type', '')}"
        prev_count = max(1, int(prev.get("lap_count", 1)))
        prev_total = max(1, int(prev.get("total_laps", 1)))
        prev_frac  = prev_count / prev_total

        if key not in curr_map:
            result[key] = FIX_STATUS_FIXED
            continue

        curr = curr_map[key]
        if curr.total_laps < _MIN_LAPS_FOR_VERIFY:
            result[key] = FIX_STATUS_INSUFFICIENT
            continue

        curr_frac = curr.lap_count / max(1, curr.total_laps)
        if curr_frac <= prev_frac * _FIX_THRESHOLD_FIXED:
            result[key] = FIX_STATUS_FIXED
        elif curr_frac <= prev_frac * _FIX_THRESHOLD_IMPROVED:
            result[key] = FIX_STATUS_IMPROVED
        elif curr_frac >= prev_frac * _FIX_THRESHOLD_WORSE:
            result[key] = FIX_STATUS_WORSE
        else:
            result[key] = FIX_STATUS_UNCHANGED

    return result


# ---------------------------------------------------------------------------
# AI prompt summary builder
# ---------------------------------------------------------------------------
def build_corner_summary_for_prompt(
    current_issues: list[CornerIssue],
    verifications: dict[str, str] | None = None,
    max_issues: int = 6,
) -> str:
    """Format a concise corner issue summary for AI prompt injection.

    Returns empty string when there are no issues to report.
    Keeps total under ~25 lines to avoid inflating prompt size.
    """
    if not current_issues:
        return ""

    verifications = verifications or {}
    lines = ["## Repeated Corner Issues [detected from telemetry]"]

    shown = 0
    for iss in current_issues:
        if shown >= max_issues:
            break
        key = f"{iss.corner_id}:{iss.issue_type}"
        pct = round(iss.lap_count / max(1, iss.total_laps) * 100)
        sev = "HIGH" if iss.severity >= 0.6 else ("MEDIUM" if iss.severity >= 0.3 else "LOW")
        status = verifications.get(key, "")
        status_str = f" — previously {status.upper()}" if status else ""

        lines.append(
            f"- {iss.issue_type.replace('_', ' ')} at corner {iss.corner_id} "
            f"({iss.lap_count}/{iss.total_laps} laps, {pct}%, severity:{sev}){status_str}"
        )
        advice = SETUP_ADVICE_MAP.get(iss.issue_type, [])
        if advice:
            lines.append(f"  Setup focus: {advice[0]}")
        shown += 1

    remaining = len(current_issues) - shown
    if remaining > 0:
        lines.append(f"  … and {remaining} further minor issue(s)")

    lines.append(
        "(Corner IDs are position-grid references, not named GT7 corners. "
        "Severity and phase derived from telemetry calculations.)"
    )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Public helper
# ---------------------------------------------------------------------------
def get_setup_advice(issue_type: str) -> list[str]:
    """Return setup investigation advice for a given issue type."""
    return SETUP_ADVICE_MAP.get(issue_type, [])
