"""Per-corner authoring layer (pure, Qt-free).

The engineering layer already shapes the setup to a track's corner DENSITY. This adds
resolution: it reads the track's reviewed per-corner segments (entry / apex / exit
windows + direction, from the track-modelling pipeline) and derives the CORNER
CHARACTER an engineer would tune to — how tight-vs-open the corners are, how many are
traction-limited on exit, and the direction balance — then shapes mechanical grip,
rear traction and platform accordingly.

Honesty first (the shipped per-corner data has NO speed/radius/braking fields — only
progress windows and direction):
  * corner "openness" is derived from each corner's window width RELATIVE TO the
    track's own median corner — a geometric PROXY for tight-vs-fast, never a measured
    speed. It is therefore confidence-capped at MEDIUM and clearly labelled a proxy.
  * a traction-limited exit is inferred from a corner whose EXIT window is longer than
    its ENTRY window (a long drive-off), again a proxy.
  * when no reviewed segments exist the profile is empty and authoring falls back to
    the existing corner-density behaviour — nothing is invented.

It authors no value the range clamp/validator would not and calls no AI.
"""
from __future__ import annotations

from dataclasses import dataclass, field as _dc_field
from typing import Optional


# Segment types that mark a corner phase (from the track-segment pipeline).
_ENTRY_TYPES = {"corner_entry"}
_APEX_TYPES = {"apex_zone", "corner_apex", "apex"}
_EXIT_TYPES = {"corner_exit"}
_STRAIGHT_TYPES = {"straight"}
_KERB_TYPES = {"kerb_or_bump_candidate", "kerb", "kerb_candidate"}
_BRAKING_TYPES = {"braking_zone"}
_TRACTION_TYPES = {"traction_zone"}

# A corner is "tight" when its window is <= this fraction of the median, "open" when
# >= the upper fraction. Relative to the track's own corners so it works everywhere.
_TIGHT_REL = 0.72
_OPEN_REL = 1.30


@dataclass(frozen=True)
class CornerRecord:
    turn: Optional[int]
    apex_progress: float
    width: float                 # entry_start -> exit_end, fraction of lap
    entry_width: float
    exit_width: float
    direction: str               # "left" / "right" / ""


@dataclass(frozen=True)
class CornerProfile:
    available: bool
    corner_count: int
    tight_fraction: float        # fraction of corners that are tight/slow (proxy)
    open_fraction: float         # fraction that are open/fast (proxy)
    long_exit_fraction: float    # fraction with a traction-limited (long) exit (proxy)
    straight_count: int
    left_count: int
    right_count: int
    kerb_count: int              # kerb/bump candidates around the lap
    braking_count: int
    traction_count: int
    confidence: str              # capped at "medium" (geometric proxy)
    source: str
    notes: list = _dc_field(default_factory=list)

    @property
    def kerb_heavy(self) -> bool:
        # Many kerb/bump zones relative to the corner count → a kerb-heavy circuit.
        return self.kerb_count >= max(6, int(round(1.2 * max(1, self.corner_count))))

    def summary(self) -> str:
        if not self.available:
            return "no reviewed per-corner segments — corner density used instead"
        bits = [f"{self.corner_count} corners "
                f"({self.tight_fraction*100:.0f}% tight / {self.open_fraction*100:.0f}% open, "
                f"{self.long_exit_fraction*100:.0f}% traction-limited exits)"]
        if self.kerb_count:
            bits.append(f"{self.kerb_count} kerb/bump zones")
        if self.straight_count:
            bits.append(f"{self.straight_count} straights")
        return ", ".join(bits) + f" [proxy, {self.confidence}]"


def _num(v) -> Optional[float]:
    try:
        f = float(v)
        return f if f == f and f not in (float("inf"), float("-inf")) else None
    except (TypeError, ValueError):
        return None


def _median(xs: list) -> float:
    ys = sorted(xs)
    n = len(ys)
    if n == 0:
        return 0.0
    return ys[n // 2] if n % 2 else (ys[n // 2 - 1] + ys[n // 2]) / 2.0


def build_corner_profile(segments: list, *, detection_confidence: str = "medium") -> CornerProfile:
    """Build a CornerProfile from reviewed track segments (list of dicts with
    ``segment_type``, ``lap_progress_start/end/mid``, ``turn_number``, ``direction``).

    Groups entry/apex/exit by turn number (falling back to nearest-apex association)
    and derives tight/open/long-exit fractions from window widths relative to the
    track's own median. Empty/degenerate input → ``available=False``."""
    segs = [s for s in (segments or []) if isinstance(s, dict)]
    if not segs:
        return CornerProfile(False, 0, 0.0, 0.0, 0.0, 0, 0, 0, 0, 0, 0, "none",
                             "missing", ["no segments"])

    def _type(s):
        return str(s.get("segment_type") or s.get("type") or "").strip().lower()

    apexes = [s for s in segs if _type(s) in _APEX_TYPES]
    entries = [s for s in segs if _type(s) in _ENTRY_TYPES]
    exits = [s for s in segs if _type(s) in _EXIT_TYPES]
    straights = [s for s in segs if _type(s) in _STRAIGHT_TYPES]
    kerb_count = sum(1 for s in segs if _type(s) in _KERB_TYPES)
    braking_count = sum(1 for s in segs if _type(s) in _BRAKING_TYPES)
    traction_count = sum(1 for s in segs if _type(s) in _TRACTION_TYPES)
    conf = "medium" if str(detection_confidence).lower() in ("high", "medium") else "low"

    if not apexes:
        # No corner-structure segments, but car-behaviour zones (kerb/braking/traction)
        # are still real per-location demands worth authoring to.
        has_demand = bool(kerb_count or braking_count or traction_count)
        return CornerProfile(
            has_demand, 0, 0.0, 0.0, 0.0, len(straights), 0, 0,
            kerb_count, braking_count, traction_count,
            conf if has_demand else "none",
            "reviewed_segments" if has_demand else "no_apex",
            ["no corner-structure segments; using kerb/braking/traction demands only"]
            if has_demand else ["no apex zones in segments"])

    def _by_turn(items):
        out = {}
        for s in items:
            t = s.get("turn_number")
            if t is not None:
                out.setdefault(int(t), s)
        return out

    entry_by_turn = _by_turn(entries)
    exit_by_turn = _by_turn(exits)

    corners: list[CornerRecord] = []
    left = right = 0
    for a in apexes:
        t = a.get("turn_number")
        t = int(t) if t is not None else None
        a_start = _num(a.get("lap_progress_start"))
        a_end = _num(a.get("lap_progress_end"))
        a_mid = _num(a.get("lap_progress_mid")) or a_start or 0.0
        ent = entry_by_turn.get(t)
        ext = exit_by_turn.get(t)
        e_start = _num(ent.get("lap_progress_start")) if ent else a_start
        x_end = _num(ext.get("lap_progress_end")) if ext else a_end
        if e_start is None or x_end is None:
            continue
        # widths (guard lap wrap by ignoring negative spans → use apex window)
        width = x_end - e_start
        if width <= 0:
            width = (a_end - a_start) if (a_end and a_start) else 0.0
        entry_w = (a_mid - e_start) if (a_mid and e_start is not None) else 0.0
        exit_w = (x_end - a_mid) if (x_end and a_mid) else 0.0
        direction = str(a.get("direction") or (ent or {}).get("direction") or "").strip().lower()
        if "left" in direction:
            left += 1
        elif "right" in direction:
            right += 1
        corners.append(CornerRecord(t, a_mid, max(0.0, width),
                                    max(0.0, entry_w), max(0.0, exit_w), direction))

    if not corners:
        has_demand = bool(kerb_count or braking_count or traction_count)
        return CornerProfile(
            has_demand, 0, 0.0, 0.0, 0.0, len(straights), 0, 0,
            kerb_count, braking_count, traction_count,
            conf if has_demand else "none",
            "reviewed_segments" if has_demand else "no_windows",
            ["no usable corner windows"])

    widths = [c.width for c in corners if c.width > 0]
    med = _median(widths) if widths else 0.0
    tight = open_ = 0
    long_exit = 0
    for c in corners:
        if med > 0 and c.width > 0:
            if c.width <= _TIGHT_REL * med:
                tight += 1
            elif c.width >= _OPEN_REL * med:
                open_ += 1
        # traction-limited exit: exit window materially longer than entry window
        if c.exit_width > 0 and c.entry_width > 0 and c.exit_width >= 1.25 * c.entry_width:
            long_exit += 1

    n = len(corners)
    return CornerProfile(
        available=True, corner_count=n,
        tight_fraction=round(tight / n, 3), open_fraction=round(open_ / n, 3),
        long_exit_fraction=round(long_exit / n, 3),
        straight_count=len(straights), left_count=left, right_count=right,
        kerb_count=kerb_count, braking_count=braking_count, traction_count=traction_count,
        confidence=conf, source="reviewed_segments",
        notes=["corner character is a geometric proxy from window widths, not measured "
               "speed — treated as a lower-confidence shaping input"],
    )


def load_reviewed_segments(track_location_id: str, layout_id: str) -> list:
    """Read the newest reviewed-segments file for a layout (read-only), or []. These
    are user/runtime files (may be absent); never raises."""
    if not track_location_id:
        return []
    try:
        import json
        from pathlib import Path
        base = Path(__file__).resolve().parent.parent / "data" / "track_models"
        if not base.is_dir():
            return []
        loc = str(track_location_id).strip()
        lay = str(layout_id or "").strip()
        pattern = f"{loc}__{lay}__reviewed_segments__*.json" if lay else \
                  f"{loc}__*reviewed_segments__*.json"
        matches = sorted(base.glob(pattern))
        if not matches:
            return []
        # Reviewed-segments files are complementary (one holds corner structure —
        # apex/entry/exit — another holds car-behaviour zones — kerb/limiter/braking).
        # Merge them all, deduping by segment_id (newest file wins on a clash).
        merged: dict = {}
        order: list = []
        for m in matches:
            try:
                data = json.loads(m.read_text(encoding="utf-8"))
            except Exception:
                continue
            for i, s in enumerate(data.get("segments") or []):
                if not isinstance(s, dict):
                    continue
                key = s.get("segment_id") or f"{m.name}:{i}"
                if key not in merged:
                    order.append(key)
                merged[key] = s
        return [merged[k] for k in order]
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Map the corner character to engineering intents (returned as plain dicts so the
# engineering layer can wrap them in its EngineeringIntent — keeps this module free
# of a cross-import). Conservative, confidence-scaled, direction-first.
# ---------------------------------------------------------------------------
def corner_profile_intents(profile: CornerProfile, objective: str = "base") -> list:
    """Return [{field, direction, strength, reason, evidence, couples_with}] shaping the
    setup to the corner character. Empty when no reviewed profile exists.

    Authoring is deliberately limited to the RELIABLE per-corner signals — kerb load,
    braking / traction zones, and traction-limited exits (entry/exit asymmetry). The
    tight-vs-open window-width ratio is retained for reporting only; it is too weak a
    proxy for corner SPEED to author suspension stiffness from (no radius/speed data)."""
    if not profile or not profile.available:
        return []
    out: list = []
    # Lower confidence → smaller moves. A proxy never authors a full step.
    base_strength = 0.5 if profile.confidence == "medium" else 0.3

    # Detected braking zones → keep the front supported / stable under braking.
    if profile.braking_count >= 3:
        out.append({"field": "aero_front", "direction": +1, "strength": base_strength,
                    "reason": (f"{profile.braking_count} heavy braking zones — a little more "
                               "front downforce keeps the nose planted and stable under braking"),
                    "evidence": "corners:braking_zones", "couples_with": ("brake_bias",)})

    # Detected traction zones OR traction-limited (long) exits → rear grip on drive-off.
    if profile.traction_count >= 3 or profile.long_exit_fraction >= 0.40:
        _why = (f"{profile.traction_count} traction zones" if profile.traction_count >= 3
                else f"{profile.long_exit_fraction*100:.0f}% of corners have long, "
                     "traction-limited exits")
        out.append({"field": "aero_rear", "direction": +1, "strength": base_strength,
                    "reason": f"{_why} — more rear downforce for drive off the corner",
                    "evidence": "corners:traction", "couples_with": ("toe_rear", "lsd_accel")})

    # Kerb-heavy circuit → carry ride-height margin and compliance so the car rides the
    # kerbs instead of being unsettled by them.
    if profile.kerb_heavy:
        out.append({"field": "ride_height_front", "direction": +1, "strength": base_strength,
                    "reason": (f"{profile.kerb_count} kerb/bump zones around the lap — carry a "
                               "little ride-height margin so the car rides the kerbs cleanly"),
                    "evidence": "corners:kerb_heavy", "couples_with": ("springs_front", "ride_height_rear")})
        out.append({"field": "springs_front", "direction": -1, "strength": base_strength,
                    "reason": "kerb-heavy circuit rewards compliance — a slightly softer front "
                              "spring absorbs the kerbs",
                    "evidence": "corners:kerb_heavy", "couples_with": ("ride_height_front",)})
    return out
