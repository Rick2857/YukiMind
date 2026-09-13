"""Generic context contribution contract."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ContextContribution(BaseModel):
    """A domain-neutral context item with explicit selection metadata."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(min_length=1)
    priority: int = 0
    relevance: float = Field(default=0, ge=0, le=1)
    cost: int = Field(ge=0)
    payload: Any
    required: bool = False
    source: str = "core"


class ContextSelection(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    selected: tuple[ContextContribution, ...]
    used_characters: int
    omitted: int
