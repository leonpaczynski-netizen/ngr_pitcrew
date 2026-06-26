"""Tests for strategy parsing in strategy/ai_planner.py."""
import json
import pytest
from strategy.ai_planner import StrategyOption, _parse_strategies, _strip_fences


# ---------------------------------------------------------------------------
# _strip_fences
# ---------------------------------------------------------------------------

def test_strip_fences_plain_json():
    raw = '{"strategies": []}'
    assert _strip_fences(raw) == raw


def test_strip_fences_markdown_json():
    raw = '```json\n{"strategies": []}\n```'
    result = _strip_fences(raw)
    assert result.startswith("{")


def test_strip_fences_markdown_no_lang():
    raw = '```\n{"strategies": []}\n```'
    result = _strip_fences(raw)
    assert result.startswith("{")


# ---------------------------------------------------------------------------
# _parse_strategies
# ---------------------------------------------------------------------------

def _make_strategy_json(strategies: list[dict]) -> str:
    return json.dumps({"strategies": strategies})


def _safe_strategy(rank=1):
    return {
        "rank": rank,
        "name": "Safe",
        "stints": [{"compound": "Hard", "laps": 25, "ref_lap_ms": 97_000, "pace_threshold_ms": 3000}],
        "estimated_time_s": 2450.0,
        "pit_time_s": 24.5,
        "summary": "Safest route to finish.",
        "risks": "Slightly slower overall.",
        "positives": "Low risk of tyre failure.",
        "negatives": "Sacrifices pace for reliability.",
    }


def test_parse_strategies_valid_json():
    strategies = [
        _safe_strategy(rank=1),
        {**_safe_strategy(rank=2), "name": "Balanced"},
        {**_safe_strategy(rank=3), "name": "Aggressive"},
    ]
    result = _parse_strategies(_make_strategy_json(strategies))
    assert len(result) == 3
    assert result[0].name == "Safe"
    assert result[1].name == "Balanced"
    assert result[2].name == "Aggressive"


def test_parse_strategies_sorted_by_rank():
    strategies = [
        {**_safe_strategy(rank=3), "name": "Aggressive"},
        {**_safe_strategy(rank=1), "name": "Safe"},
        {**_safe_strategy(rank=2), "name": "Balanced"},
    ]
    result = _parse_strategies(_make_strategy_json(strategies))
    assert [o.rank for o in result] == [1, 2, 3]


def test_parse_strategies_reads_positives_negatives():
    s = _safe_strategy(rank=1)
    result = _parse_strategies(_make_strategy_json([s]))
    assert result[0].positives == "Low risk of tyre failure."
    assert result[0].negatives == "Sacrifices pace for reliability."


def test_parse_strategies_strips_fences():
    strategies = [_safe_strategy(rank=1)]
    raw = "```json\n" + _make_strategy_json(strategies) + "\n```"
    result = _parse_strategies(raw)
    assert len(result) == 1


def test_parse_strategies_fallback_on_bad_json():
    with pytest.raises(Exception):
        # Malformed JSON raises — caller must handle
        _parse_strategies("{bad json}")


def test_parse_strategies_empty_strategies():
    result = _parse_strategies('{"strategies": []}')
    assert result == []


def test_parse_strategies_missing_optional_fields():
    s = {
        "rank": 1,
        "name": "Safe",
        "stints": [],
        "estimated_time_s": 0.0,
        "pit_time_s": 0.0,
        "summary": "",
        "risks": "",
        # positives and negatives omitted — should default to ""
    }
    result = _parse_strategies(_make_strategy_json([s]))
    assert result[0].positives == ""
    assert result[0].negatives == ""


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
