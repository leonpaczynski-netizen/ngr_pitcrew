"""Neutral home for the shared race-strategy value objects.

These dataclasses describe race parameters and strategy options. They are
pure data with no AI, network, or Qt dependencies, and are consumed by the
deterministic strategy stack (``strategy.outcome``, ``strategy.feasibility``,
``strategy.race_strategy_*``) as well as the UI.

Extracted from the former ``strategy.ai_planner`` module during the
determinism rebuild (Sprint 1) so that deterministic modules never import
from an AI-named module.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from strategy.feasibility import DataGap, FeasibilityReport, RejectedStrategy


@dataclass
class RaceParams:
    track: str
    total_laps: int
    tyre_wear_multiplier: float  # 1.0 = normal wear rate, 2.0 = double race wear
    fuel_burn_per_lap: float     # litres
    refuel_speed_lps: float      # litres per second
    pit_loss_secs: float         # fixed time lost per pit stop (lane + work)
    min_mandatory_stops: int = 0                              # 0 = no rule
    mandatory_compounds: list = field(default_factory=list)  # e.g. ["RS", "RM"]
    race_type: str = "lap"       # "lap" or "timed"
    duration_mins: int = 0       # minutes; only used when race_type == "timed"
    tuning_locked: bool = False  # True when Event disallows all tuning
    allowed_tuning: list = field(default_factory=list)  # e.g. ["suspension", "brake_balance"]
    bop: bool = False            # True when Balance of Performance is active
    avail_tyres: list = field(default_factory=list)  # compound codes available, e.g. ["RM", "RH"]
    track_location_id: str = ""   # seed/resolver ID (e.g. "suzuka_circuit"); empty = no Track Intelligence
    layout_id: str = ""           # layout ID (e.g. "suzuka_circuit__full_course"); empty = no Track Intelligence


@dataclass
class StrategyOption:
    rank: int
    name: str
    stints: list[dict]           # [{compound, laps, ref_lap_ms, pace_threshold_ms}, ...]
    estimated_time_s: float
    pit_time_s: float            # total time spent in pit stops
    summary: str
    risks: str
    positives: str = ""
    negatives: str = ""
    estimated_speed_rank: int = 0      # 1 = fastest overall, 2 = second, 3 = third
    tyre_risk: str = ""
    fuel_risk: str = ""
    traffic_risk: str = ""
    undercut_risk: str = ""
    confidence_score: float = 0.0
    why_label: str = ""
    # Deterministic outcome fields (computed by strategy/outcome.py)
    deterministic_time_s: float = 0.0   # deterministic T_race
    delta_vs_fastest_s: float = 0.0     # seconds behind the fastest option (0.0 for fastest)
    outcome_confidence: str = ""        # "high"/"medium"/"low" — based on degradation data coverage
    rank_by_time: int = 0               # 1 = fastest by deterministic time, ascending


@dataclass
class StrategyResult:
    """Container for a full strategy analysis result.

    Wraps a list[StrategyOption] with feasibility metadata and provides
    __iter__/__len__/__getitem__ shims for callers that treat the return
    value as a plain list.
    """
    strategies: list[StrategyOption]
    rejected_strategies: list[RejectedStrategy]
    data_gaps: list[DataGap]
    assumptions: list[str]
    calculation_notes: list[str]
    feasibility: FeasibilityReport

    def __iter__(self):
        return iter(self.strategies)

    def __len__(self) -> int:
        return len(self.strategies)

    def __getitem__(self, index):
        return self.strategies[index]

    def __eq__(self, other) -> bool:
        if isinstance(other, list):
            return self.strategies == other
        if isinstance(other, StrategyResult):
            return self.strategies == other.strategies
        return NotImplemented
