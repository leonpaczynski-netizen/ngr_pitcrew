"""Tests for the StrategyOption dataclass (moved to strategy.race_params).

The generative-AI strategy parser (_parse_strategies / _strip_fences from the
old strategy.ai_planner) was removed. The deterministic StrategyOption field
guard survives — its optional positives/negatives fields must default to "".
"""
from strategy.race_params import StrategyOption


# ---------------------------------------------------------------------------
# StrategyOption dataclass
# ---------------------------------------------------------------------------

def test_strategy_option_defaults():
    opt = StrategyOption(
        rank=1,
        name="Safe",
        stints=[],
        estimated_time_s=0.0,
        pit_time_s=0.0,
        summary="",
        risks="",
    )
    assert opt.positives == ""
    assert opt.negatives == ""
