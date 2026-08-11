"""The Race Engineer: three prompts, assembled from what the app already knows.

The app **composes prompts. It never gives setup advice.** There is no tuning
heuristic in this package, no suggested value, no "recommended" anything. The
reasoning happens in the knowledge base the driver pastes into; clipboard is
the whole transport and the app makes no network calls.

The rule the whole package is built on:

> **If the app already knows it, the app fills it in. The driver is only ever
> asked for what the app cannot know.**

Facts from the app, perception from the driver. An empty input field for
something in the store is a bug, and a fabricated value to fill a template is
worse — a zero that means "not measured" gets diagnosed as a real value, which
is the most damaging failure mode in the whole loop. Absent data is omitted or
explicitly labelled as not measured, never defaulted.
"""
from __future__ import annotations

from pitcrew.prompts.build import (
    BRIEF,
    KINDS,
    OUTCOME,
    REFINEMENT,
    Prompt,
    PromptRefused,
    build_prompt,
)
from pitcrew.prompts.context import PromptContext, gather
from pitcrew.prompts.report import DriverReport
from pitcrew.prompts.templates import PROMPT_VERSION, templates

__all__ = [
    "BRIEF", "KINDS", "OUTCOME", "PROMPT_VERSION", "REFINEMENT",
    "DriverReport", "Prompt", "PromptContext", "PromptRefused",
    "build_prompt", "gather", "templates",
]
