"""Deterministic Telemetry Replay harness (Program 2, Phase 46).

Replays a sequence of trustworthy telemetry frames against an INJECTED monotonic clock so the Phase-44
advisory engine can be validated in shadow mode before voice is enabled. It fabricates no production
telemetry - callers supply real captured frames (or test fixtures). Output is deterministic for
identical input.

Supports: injected monotonic time, adjustable playback speed (for tests), pause/resume, lap boundaries,
stale gaps, pit entry/exit, segment transitions, high-workload corner phases, clean/invalid laps, and
context-mismatch injection (a frame flag) for tests.

Purity: Qt-free, DB-free, UI-free, network-free, AI-free; no random, no WALL-CLOCK (time is injected);
deterministic; never raises.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import Enum
from typing import List, Mapping, Optional, Sequence, Tuple

TELEMETRY_REPLAY_VERSION = "telemetry_replay_v1"

# a gap larger than this many simulated seconds between frames marks the resumed frame as stale.
_STALE_GAP_SECONDS = 1.0


def _norm(v) -> str:
    return str(v if v is not None else "").strip()


def _dumps(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str, ensure_ascii=True,
                      allow_nan=False)


def _fp(payload) -> str:
    return f"{TELEMETRY_REPLAY_VERSION}:" + hashlib.sha256(_dumps(payload).encode()).hexdigest()[:24]


class ReplayEventKind(str, Enum):
    FRAME = "frame"
    LAP_BOUNDARY = "lap_boundary"
    PIT_ENTRY = "pit_entry"
    PIT_EXIT = "pit_exit"
    STALE_GAP = "stale_gap"
    SEGMENT_TRANSITION = "segment_transition"


class TelemetryReplayClock:
    """A deterministic injected monotonic clock in simulated seconds scaled by playback speed."""

    def __init__(self, start_monotonic: float = 0.0, playback_speed: float = 1.0):
        self._t = float(start_monotonic)
        self._speed = float(playback_speed) if float(playback_speed) > 0 else 1.0

    def advance(self, sim_seconds: float) -> float:
        self._t += float(sim_seconds) / self._speed
        return self._t

    def now(self) -> float:
        return self._t


@dataclass(frozen=True)
class ReplayCycle:
    index: int
    monotonic: float
    sim_time: float
    frame: dict
    event: str
    is_stale: bool

    def to_dict(self) -> dict:
        return {"index": self.index, "monotonic": self.monotonic, "sim_time": self.sim_time,
                "frame": dict(self.frame), "event": self.event, "is_stale": self.is_stale}


@dataclass(frozen=True)
class TelemetryReplayResult:
    cycles: Tuple[dict, ...]
    lap_count: int
    stale_gap_count: int
    pit_events: int
    input_fingerprint: str
    content_fingerprint: str
    eval_version: str = TELEMETRY_REPLAY_VERSION

    def to_dict(self) -> dict:
        return {"cycles": [dict(c) for c in self.cycles], "lap_count": self.lap_count,
                "stale_gap_count": self.stale_gap_count, "pit_events": self.pit_events,
                "input_fingerprint": self.input_fingerprint,
                "content_fingerprint": self.content_fingerprint, "eval_version": self.eval_version}


def replay_telemetry(frames: Optional[Sequence[Mapping]], *, playback_speed: float = 1.0,
                     start_monotonic: float = 0.0) -> TelemetryReplayResult:
    """Replay ``frames`` deterministically. Each frame may carry ``dt`` (simulated seconds since the
    previous frame; default 0.1), telemetry fields, and flags (``paused``, ``pit``, ``lap``,
    ``segment_type``, ``context_mismatch``). Deterministic; never raises."""
    try:
        fr = [f for f in (frames or []) if isinstance(f, Mapping)]
        clock = TelemetryReplayClock(start_monotonic, playback_speed)
        cycles: List[ReplayCycle] = []
        sim = 0.0
        prev_lap = None
        prev_pit = False
        prev_seg = None
        lap_count = 0
        stale_gaps = 0
        pit_events = 0
        for i, f in enumerate(fr):
            if f.get("paused"):
                # a paused frame advances no time and produces no cycle (resume continues cleanly).
                continue
            dt = float(f.get("dt", 0.1) or 0.0)
            sim += dt
            mono = clock.advance(dt)
            is_stale = bool(f.get("stale")) or (i > 0 and dt > _STALE_GAP_SECONDS)
            event = ReplayEventKind.FRAME
            lap = f.get("lap")
            if lap is not None and lap != prev_lap:
                event = ReplayEventKind.LAP_BOUNDARY
                if prev_lap is not None:
                    lap_count += 1
                prev_lap = lap
            pit = bool(f.get("pit") or f.get("in_pit"))
            if pit and not prev_pit:
                event = ReplayEventKind.PIT_ENTRY
                pit_events += 1
            elif not pit and prev_pit:
                event = ReplayEventKind.PIT_EXIT
                pit_events += 1
            prev_pit = pit
            seg = _norm(f.get("segment_type"))
            if seg and seg != prev_seg and event == ReplayEventKind.FRAME:
                event = ReplayEventKind.SEGMENT_TRANSITION
            prev_seg = seg
            if is_stale:
                event = ReplayEventKind.STALE_GAP
                stale_gaps += 1
            # build the per-cycle frame with telemetry_fresh reflecting staleness.
            frame = {k: v for k, v in f.items() if k not in ("dt", "paused")}
            frame["telemetry_fresh"] = not is_stale
            frame.setdefault("in_pit", pit)
            cycles.append(ReplayCycle(index=i, monotonic=round(mono, 6), sim_time=round(sim, 6),
                                      frame=frame, event=event.value, is_stale=is_stale))
        input_fp = _fp({"frames": [{k: v for k, v in f.items()} for f in fr], "speed": playback_speed})
        content_fp = _fp({"cycles": [(c.index, c.event, c.is_stale,
                                      _norm(c.frame.get("segment_type"))) for c in cycles],
                          "laps": lap_count})
        return TelemetryReplayResult(cycles=tuple(c.to_dict() for c in cycles), lap_count=lap_count,
                                     stale_gap_count=stale_gaps, pit_events=pit_events,
                                     input_fingerprint=input_fp, content_fingerprint=content_fp)
    except Exception:  # pragma: no cover - defensive
        return TelemetryReplayResult(cycles=(), lap_count=0, stale_gap_count=0, pit_events=0,
                                     input_fingerprint=_fp({"e": 1}), content_fingerprint=_fp({"e": 1}))


def replay_versions() -> dict:
    return {"telemetry_replay": TELEMETRY_REPLAY_VERSION}
