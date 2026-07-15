"""Architecture guard: NO generative AI anywhere in production code.

Part of the determinism rebuild (Sprint 1). These tests are the enforcement
gate for Requirement 1 — Pit Crew must operate entirely in-house with no
external AI service, no API key, and no network dependency for core work.

They scan the production source tree (everything except tests/) and fail if
any generative-AI provider, client, endpoint, key, or the removed AI modules
reappear. The word "ai" as a plain substring (e.g. "available", "aim") is NOT
flagged — only real generative-AI markers are.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent

# Directories/files that are NOT production code (docs, tests, caches, venvs).
_EXCLUDE_DIRS = {".git", "__pycache__", "tests", ".venv", "venv", "env",
                 "htmlcov", ".pytest_cache", "docs", "knowledge", "New folder"}


def _production_py_files() -> list[Path]:
    files: list[Path] = []
    for p in _REPO.rglob("*.py"):
        if any(part in _EXCLUDE_DIRS for part in p.relative_to(_REPO).parts):
            continue
        files.append(p)
    return files


# Modules that were removed/renamed in the AI-removal sprint. Importing any of
# their old AI-named paths is a failure. (The deterministic input-plumbing that
# used to live in ``data.ai_context_snapshot`` was renamed to
# ``data.analysis_inputs`` — the old module name must no longer resolve.)
_DELETED_AI_MODULES = [
    "strategy._ai_client",
    "strategy.ai_planner",
    "strategy.corner_verify_ai",
    "strategy.setup_ai_audit",
    "strategy.strategy_orchestrator",
    "strategy.practice_orchestrator",
    "strategy.track_context_prompt",
    "data.ai_context_snapshot",
]

# Real generative-AI markers (regexes). Deliberately specific so benign words
# containing "ai" do not match.
_FORBIDDEN_PATTERNS = [
    (r"\bimport\s+openai\b", "openai import"),
    (r"\bimport\s+anthropic\b", "anthropic SDK import"),
    (r"api\.anthropic\.com", "Anthropic API endpoint"),
    (r"\bcall_api\b", "AI call_api()"),
    (r"x-api-key", "AI API key header"),
    (r"anthropic-version", "Anthropic API header"),
    (r"sk-ant-", "Anthropic API key literal"),
    (r"\bfrom\s+strategy\._ai_client\b", "_ai_client import"),
    (r"\bfrom\s+strategy\.ai_planner\b", "ai_planner import"),
    (r"\bfrom\s+strategy\.corner_verify_ai\b", "corner_verify_ai import"),
    (r"\bfrom\s+strategy\.setup_ai_audit\b", "setup_ai_audit import"),
    (r"\bfrom\s+strategy\.strategy_orchestrator\b", "strategy_orchestrator import"),
    (r"\bfrom\s+strategy\.practice_orchestrator\b", "practice_orchestrator import"),
    (r"\bfrom\s+strategy\.track_context_prompt\b", "track_context_prompt import"),
    (r"""\[\s*['"]anthropic['"]\s*\]""", "config['anthropic'] access"),
]

_COMPILED = [(re.compile(p), label) for p, label in _FORBIDDEN_PATTERNS]


def test_deleted_ai_modules_are_gone_from_disk():
    """The AI-only modules must no longer exist as files."""
    present = []
    for mod in _DELETED_AI_MODULES:
        rel = Path(mod.replace(".", "/") + ".py")
        if (_REPO / rel).exists():
            present.append(str(rel))
    assert not present, f"AI modules still on disk: {present}"


def test_deleted_ai_modules_not_importable():
    """Importing a removed AI module must raise ImportError."""
    import importlib
    for mod in _DELETED_AI_MODULES:
        with pytest.raises(ImportError):
            importlib.import_module(mod)


def test_no_forbidden_ai_markers_in_production():
    """No production source file may contain a generative-AI marker."""
    hits: list[str] = []
    for path in _production_py_files():
        try:
            text = path.read_text(encoding="utf-8")
        except Exception:
            continue
        for line_no, line in enumerate(text.splitlines(), 1):
            for rx, label in _COMPILED:
                if rx.search(line):
                    rel = path.relative_to(_REPO)
                    hits.append(f"{rel}:{line_no}  [{label}]  {line.strip()[:100]}")
    assert not hits, "Generative-AI markers found in production:\n" + "\n".join(hits)


def test_requirements_has_no_ai_sdk():
    """requirements.txt must not declare any LLM SDK."""
    req = (_REPO / "requirements.txt").read_text(encoding="utf-8").lower()
    for pkg in ("openai", "anthropic", "langchain", "llama-index", "cohere"):
        assert pkg not in req, f"requirements.txt still lists AI package: {pkg}"


def test_default_config_has_no_anthropic_block():
    """The default config must not seed an anthropic/api-key section."""
    import config_paths
    default = config_paths.DEFAULT_CONFIG if hasattr(config_paths, "DEFAULT_CONFIG") else {}
    assert "anthropic" not in default, "default config still has an 'anthropic' block"


def test_shared_dataclasses_have_neutral_home():
    """RaceParams/StrategyOption/StrategyResult live in a non-AI module."""
    from strategy.race_params import RaceParams, StrategyOption, StrategyResult  # noqa: F401


def test_deterministic_tyre_degradation_is_pure_and_repeatable():
    """The deterministic tyre-degradation path is import-clean and repeatable."""
    from strategy.tyre_degradation import analyse_tyre_degradation
    seqs = {
        "RS": [98000, 98000, 98000, 100000, 100000],
        "RM": [99000, 99000, 99000, 99000, 99000, 99000, 101500],
    }
    a = analyse_tyre_degradation(seqs, 1.0)
    b = analyse_tyre_degradation(seqs, 1.0)
    assert a == b, "identical inputs must produce identical output"
